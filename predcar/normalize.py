"""Make/model normalization (SPEC §4): silver raw labels → canonical make, model_gen, generation.

Rules live in ``mapping/``:

* ``makes.csv``  — ``alias,make``: raw make label → canonical make (identity when absent).
* ``models.csv`` — ``make,model_raw_regex,year_from,year_to,model_gen,generation``: a rule
  matches when the canonical make equals ``make`` and the regex (case-insensitive) matches
  ``model_raw``. A rule with a year range applies only when ``year_first_reg`` falls in it;
  a rule without range applies whatever the year (the label alone is discriminant). Rows
  without a year that only match ranged rules get the ``model_gen`` but no ``generation``.
* ``target_models.csv`` — the hand-picked target list; its makes define the coverage gate.

Ambiguous rules (two different model_gen, or two generations, for one row) are a mapping
bug and raise MappingError rather than picking one silently.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import polars as pl
from pydantic import BaseModel, Field, field_validator, model_validator

from predcar.paths import MAPPING_DIR, SILVER_DIR

logger = logging.getLogger(__name__)

MAKES_FILE = "makes.csv"
MODELS_FILE = "models.csv"
TARGETS_FILE = "target_models.csv"


class MappingError(ValueError):
    """A mapping file is malformed or rules are ambiguous for some rows."""


class CoverageError(RuntimeError):
    """A country's target-make fleet is mapped below the configured threshold."""


class ModelRule(BaseModel):
    make: str
    model_raw_regex: str
    year_from: int | None = None
    year_to: int | None = None
    model_gen: str
    generation: str | None = None

    @field_validator("make", "model_gen", "generation", mode="before")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        return str(value).strip().upper()

    @field_validator("model_raw_regex")
    @classmethod
    def _compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regex {value!r}: {exc}") from exc
        return value

    @model_validator(mode="after")
    def _range_is_consistent(self) -> ModelRule:
        if (self.year_from is None) != (self.year_to is None):
            raise ValueError("year_from and year_to must be both set or both empty")
        if self.year_from is not None and self.year_from > self.year_to:  # type: ignore[operator]
            raise ValueError("year_from > year_to")
        return self

    @property
    def ranged(self) -> bool:
        return self.year_from is not None


class TargetModel(BaseModel):
    make: str
    model_gen: str
    generation: str
    segment: str
    year_from: int = Field(ge=1950)
    year_to: int = Field(ge=1950)

    @field_validator("make", "model_gen", "generation", "segment", mode="before")
    @classmethod
    def _upper(cls, value: str) -> str:
        return str(value).strip().upper()


# --------------------------------------------------------------------------- loading


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.is_file():
        raise MappingError(f"missing mapping file {path}")
    return pl.read_csv(path, infer_schema_length=0).fill_null("")


def load_makes(path: Path) -> dict[str, str]:
    """alias → canonical make, both upper-cased and stripped."""
    df = _read_csv(path)
    if set(df.columns) != {"alias", "make"}:
        raise MappingError(f"{path}: expected columns alias,make, got {df.columns}")
    makes = {}
    for alias, make in df.iter_rows():
        key = alias.strip().upper()
        if key in makes and makes[key] != make.strip().upper():
            raise MappingError(f"{path}: alias {key!r} maps to two makes")
        makes[key] = make.strip().upper()
    return makes


def load_models(path: Path) -> list[ModelRule]:
    """Validated model rules, in file order."""
    df = _read_csv(path)
    expected = set(ModelRule.model_fields)
    if set(df.columns) != expected:
        raise MappingError(f"{path}: expected columns {sorted(expected)}, got {df.columns}")
    rules = []
    for i, row in enumerate(df.iter_rows(named=True), start=2):
        try:
            rules.append(ModelRule.model_validate({k: (v or None) for k, v in row.items()}))
        except ValueError as exc:
            raise MappingError(f"{path}:{i}: {exc}") from exc
    return rules


def load_targets(path: Path) -> list[TargetModel]:
    df = _read_csv(path)
    expected = set(TargetModel.model_fields)
    if set(df.columns) != expected:
        raise MappingError(f"{path}: expected columns {sorted(expected)}, got {df.columns}")
    targets = []
    for i, row in enumerate(df.iter_rows(named=True), start=2):
        try:
            targets.append(TargetModel.model_validate(row))
        except ValueError as exc:
            raise MappingError(f"{path}:{i}: {exc}") from exc
    return targets


# --------------------------------------------------------------------------- apply


def _candidates(pairs: pl.DataFrame, rules: list[ModelRule]) -> pl.DataFrame:
    """For each unique (make, model_raw) pair, every rule whose make and regex match."""
    by_make: dict[str, list[tuple[re.Pattern[str], ModelRule]]] = {}
    for rule in rules:
        by_make.setdefault(rule.make, []).append((re.compile(rule.model_raw_regex, re.I), rule))
    out: list[dict] = []
    for make, model_raw in pairs.iter_rows():
        for pattern, rule in by_make.get(make, []):
            if model_raw is not None and pattern.search(model_raw):
                out.append(
                    {
                        "make": make,
                        "model_raw": model_raw,
                        "cand_model_gen": rule.model_gen,
                        "cand_generation": rule.generation,
                        "year_from": rule.year_from,
                        "year_to": rule.year_to,
                    }
                )
    schema = {
        "make": pl.Utf8,
        "model_raw": pl.Utf8,
        "cand_model_gen": pl.Utf8,
        "cand_generation": pl.Utf8,
        "year_from": pl.Int32,
        "year_to": pl.Int32,
    }
    return pl.DataFrame(out, schema=schema)


def apply(df: pl.DataFrame, makes: dict[str, str], rules: list[ModelRule]) -> pl.DataFrame:
    """Fill ``make``, ``model_gen`` and ``generation`` on a silver frame.

    Args:
        df: fleet_stock or fleet_new_reg frame (``year_first_reg`` optional).
        makes: alias → canonical make.
        rules: model rules.

    Returns:
        Same columns and row order, with the three normalized columns filled where a rule
        matches (null otherwise).

    Raises:
        MappingError: when rules resolve one row to several model_gen or generations.
    """
    has_year = "year_first_reg" in df.columns
    rows = df.with_row_index("_rid").with_columns(
        pl.col("make_raw")
        .replace_strict(makes, default=pl.col("make_raw"), return_dtype=pl.Utf8)
        .alias("make")
    )
    if not has_year:
        rows = rows.with_columns(pl.lit(None, dtype=pl.Int32).alias("year_first_reg"))

    cands = _candidates(rows.select("make", "model_raw").unique(), rules)
    joined = rows.select("_rid", "make", "model_raw", "year_first_reg").join(
        cands, on=["make", "model_raw"], how="inner"
    )
    year = pl.col("year_first_reg")
    applicable = pl.col("year_from").is_null() | (
        year.is_not_null() & (year >= pl.col("year_from")) & (year <= pl.col("year_to"))
    )
    # A ranged rule whose range excludes a known year is not a candidate at all.
    excluded = pl.col("year_from").is_not_null() & year.is_not_null() & ~applicable
    joined = joined.filter(~excluded).with_columns(
        pl.when(applicable).then(pl.col("cand_generation")).otherwise(None).alias("gen_ok")
    )
    resolved = joined.group_by("_rid").agg(
        pl.col("cand_model_gen").unique().alias("model_gens"),
        pl.col("gen_ok").drop_nulls().unique().alias("generations"),
    )
    ambiguous = resolved.filter(
        (pl.col("model_gens").list.len() > 1) | (pl.col("generations").list.len() > 1)
    )
    if ambiguous.height:
        sample = (
            ambiguous.join(rows.select("_rid", "make", "model_raw", "year_first_reg"), on="_rid")
            .select("make", "model_raw", "year_first_reg", "model_gens", "generations")
            .head(5)
            .to_dicts()
        )
        raise MappingError(f"{ambiguous.height} rows match conflicting rules, e.g. {sample}")
    resolved = resolved.select(
        "_rid",
        pl.col("model_gens").list.first().alias("model_gen"),
        pl.col("generations").list.first().alias("generation"),
    )
    out = (
        rows.drop("model_gen", "generation")
        .join(resolved, on="_rid", how="left")
        .sort("_rid")
        .drop("_rid")
    )
    if not has_year:
        out = out.drop("year_first_reg")
    return out.select(df.columns)


# --------------------------------------------------------------------------- coverage


def coverage(df: pl.DataFrame, targets: list[TargetModel]) -> pl.DataFrame:
    """Per country: share of the target-make fleet (by count) resolved to a model_gen."""
    target_makes = sorted({t.make for t in targets})
    scoped = df.filter(pl.col("make").is_in(target_makes))
    return (
        scoped.group_by("country")
        .agg(
            pl.col("count").sum().alias("total"),
            pl.col("count").filter(pl.col("model_gen").is_not_null()).sum().alias("mapped"),
        )
        .with_columns((pl.col("mapped") / pl.col("total")).alias("coverage"))
        .sort("country")
    )


def unmapped_report(df: pl.DataFrame, targets: list[TargetModel], top: int) -> pl.DataFrame:
    """Largest unmapped (country, make, model_raw) groups of target makes, to extend models.csv."""
    target_makes = sorted({t.make for t in targets})
    return (
        df.filter(pl.col("make").is_in(target_makes) & pl.col("model_gen").is_null())
        .group_by("country", "make", "model_raw")
        .agg(pl.col("count").sum())
        .sort("count", descending=True)
        .head(top)
    )


def check_targets_have_rules(targets: list[TargetModel], rules: list[ModelRule]) -> None:
    """Every target (make, model_gen, generation) must be produced by at least one rule."""
    produced = {(r.make, r.model_gen, r.generation) for r in rules}
    missing = [
        f"{t.make} {t.model_gen} {t.generation}"
        for t in targets
        if (t.make, t.model_gen, t.generation) not in produced
    ]
    if missing:
        raise MappingError(f"{len(missing)} target models have no rule in {MODELS_FILE}: {missing}")


# --------------------------------------------------------------------------- pipeline


def normalize(
    silver_dir: Path = SILVER_DIR,
    mapping_dir: Path = MAPPING_DIR,
    min_coverage: float = 0.95,
    report_top: int = 30,
) -> dict[str, Path]:
    """Map every ingested silver file and write ``fleet_stock.parquet`` / ``fleet_new_reg.parquet``.

    Raises:
        CoverageError: when any country's target-make coverage is below ``min_coverage``.
    """
    makes = load_makes(mapping_dir / MAKES_FILE)
    rules = load_models(mapping_dir / MODELS_FILE)
    targets = load_targets(mapping_dir / TARGETS_FILE)
    check_targets_have_rules(targets, rules)

    # Stage everything in memory; nothing is written until the coverage gate has passed,
    # so a failed run never leaves outputs from different mapping runs side by side.
    staged: dict[str, pl.DataFrame] = {}
    coverage_frames: list[pl.DataFrame] = []
    for table in ("fleet_stock", "fleet_new_reg"):
        files = sorted(p for p in silver_dir.glob(f"{table}_*.parquet"))
        if not files:
            logger.warning("%s: no ingested file in %s, skipped", table, silver_dir)
            continue
        mapped = apply(pl.concat([pl.read_parquet(p) for p in files]), makes, rules)
        cov = coverage(mapped, targets)
        for country, total, n_mapped, share in cov.iter_rows():
            logger.info(
                "%s %s: %.1f%% of target-make fleet mapped (%d/%d)",
                table,
                country,
                100 * share,
                n_mapped,
                total,
            )
        coverage_frames.append(cov.with_columns(pl.lit(table).alias("table")))
        staged[table] = mapped
        if table == "fleet_stock":
            report = unmapped_report(mapped, targets, report_top)
            if report.height:
                logger.info("top unmapped target-make rows:\n%s", report)
            below = cov.filter(pl.col("coverage") < min_coverage)
            if below.height:
                raise CoverageError(
                    f"fleet_stock coverage below {min_coverage:.0%} for "
                    f"{below.select('country', 'coverage').to_dicts()}; extend {MODELS_FILE} "
                    f"(see the unmapped report above)"
                )
    if coverage_frames:
        staged["mapping_coverage"] = pl.concat(coverage_frames)

    written: dict[str, Path] = {}
    for name, frame in staged.items():
        written[name] = silver_dir / f"{name}.parquet"
        frame.write_parquet(written[name])
    return written
