"""``predcar export``: a git-friendly evidence bundle of one pipeline run.

The development environment cannot reach the data sources, so the parsers, mapping rules and
indicators were written against presumed schemas. This bundle, produced on a connected
machine and committed to the repository, is what lets a remote reviewer validate and fix
them: raw-file *evidence* (verbatim heads, column profiles), silver summaries, every
distinct label of the target makes, the full unmapped report, coverage, anomaly checks and
the gold tables as CSV.

Everything is best-effort: a missing stage (no silver yet, coverage gate failed…) is
recorded in ``manifest.json`` under ``errors`` and the rest is still written. No raw payload
is copied (size); no personal data exists upstream.
"""

from __future__ import annotations

import gzip
import json
import logging
import platform
import re
import shutil
import subprocess
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

import polars as pl

from predcar import __version__, metrics, raw
from predcar.normalize import TARGETS_FILE, TargetModel, load_targets
from predcar.paths import CONFIG_DIR, GOLD_DIR, MAPPING_DIR, RAW_DIR, ROOT, SILVER_DIR

logger = logging.getLogger(__name__)

HEAD_LINES = 60
MAX_DISTINCT = 60
SAMPLE_JSON_ROWS = 40
GZIP_ABOVE_BYTES = 20 * 1024 * 1024
SUPPRESSION_MARKERS = ("[c]", "[x]", "[z]", "[low]", ":", "-", "")
_QUARTER_RE = re.compile(r"^\d{4}\s*Q[1-4]$")
_YEAR_RE = re.compile(r"^\d{4}$")


class Bundle:
    """Accumulates files and errors for one export run."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.files: list[str] = []
        self.errors: dict[str, str] = {}
        # stage → "ok" | "absent" (nothing to export) | "failed" (see errors)
        self.stages: dict[str, str] = {}
        self.counts: dict[str, int | float | None] = {}

    def path(self, *parts: str) -> Path:
        p = self.out_dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write_json(self, rel: str, data: object) -> None:
        p = self.path(rel)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        self.files.append(rel)

    def write_csv(self, rel: str, df: pl.DataFrame) -> None:
        """CSV, gzip-compressed above GZIP_ABOVE_BYTES so the bundle stays committable."""
        p = self.path(rel)
        df.write_csv(p)
        if p.stat().st_size > GZIP_ABOVE_BYTES:
            with p.open("rb") as src, gzip.open(str(p) + ".gz", "wb") as dst:
                shutil.copyfileobj(src, dst)
            p.unlink()
            rel += ".gz"
        self.files.append(rel)

    def write_text(self, rel: str, text: str) -> None:
        self.path(rel).write_text(text, encoding="utf-8")
        self.files.append(rel)

    def step(self, name: str):
        """Context manager: record an exception under ``name`` instead of aborting."""
        bundle = self

        class _Step:
            def __enter__(self) -> None:
                return None

            def __exit__(self, exc_type, exc, tb) -> bool:
                if exc is not None:
                    bundle.errors[name] = f"{exc_type.__name__}: {exc}"
                    logger.warning("export step %s failed: %s", name, exc)
                return True

        return _Step()


# --------------------------------------------------------------------------- raw evidence


def profile_csv(path: Path) -> dict:
    """Column-level evidence for a wide CSV: names, row count, low-cardinality values,
    suppression-marker frequencies, detected period headers."""
    df = pl.read_csv(path, infer_schema_length=0, encoding="utf8-lossy")
    cols = [c.strip() for c in df.columns]
    df = df.rename(dict(zip(df.columns, cols, strict=True)))
    quarters = [c for c in cols if _QUARTER_RE.match(c)]
    years = [c for c in cols if _YEAR_RE.match(c)]
    id_cols = [c for c in cols if c not in quarters and c not in years]
    distinct: dict[str, list[str]] = {}
    for c in id_cols:
        n = df[c].n_unique()
        if n <= MAX_DISTINCT:
            distinct[c] = sorted(v for v in df[c].unique().to_list() if v is not None)
        else:
            distinct[c] = [f"<{n} distinct>"]
    markers: dict[str, int] = {}
    period_cols = quarters + years
    if period_cols:
        stacked = df.select(period_cols).unpivot()["value"].str.strip_chars()
        for m in SUPPRESSION_MARKERS:
            n = int((stacked == m).sum())
            if n:
                markers[m or "<blank>"] = n
        non_numeric = stacked.filter(
            ~stacked.str.replace_all(",", "").str.contains(r"^-?\d+$") & stacked.is_not_null()
        )
        markers["<other non-numeric>"] = int(
            non_numeric.filter(~non_numeric.is_in(list(SUPPRESSION_MARKERS))).len()
        )
    return {
        "file": path.name,
        "rows": df.height,
        "columns": cols,
        "id_columns": id_cols,
        "quarter_columns": quarters if len(quarters) <= 6 else quarters[:4] + ["…"] + quarters[-2:],
        "n_quarter_columns": len(quarters),
        "year_columns": years,
        "distinct_values": distinct,
        "value_markers": markers,
    }


def profile_json(path: Path) -> dict:
    """Evidence for an aggregated API dump: keys, row count, sample rows, top makes."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        return {"file": path.name, "type": type(rows).__name__}
    keys: dict[str, int] = {}
    for r in rows:
        for k in r:
            keys[k] = keys.get(k, 0) + 1
    sample = rows[:SAMPLE_JSON_ROWS]
    makes: dict[str, int] = {}
    for r in rows:
        m = str(r.get("merk", ""))
        makes[m] = makes.get(m, 0) + 1
    top_makes = sorted(makes.items(), key=lambda kv: -kv[1])[:40]
    return {
        "file": path.name,
        "rows": len(rows),
        "keys": keys,
        "value_types": {k: sorted({type(r.get(k)).__name__ for r in sample}) for k in keys},
        "sample": sample,
        "top_makes": top_makes,
    }


def export_raw(bundle: Bundle, raw_dir: Path) -> None:
    """Verbatim heads + profiles of every archived raw file, plus its manifest."""
    if not raw_dir.is_dir():
        return
    for source_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        for snapshot in sorted(p for p in source_dir.iterdir() if p.is_dir()):
            manifest = raw.read_manifest(snapshot)
            rel = f"raw/{source_dir.name}/{snapshot.name}"
            bundle.write_json(f"{rel}/MANIFEST.json", manifest)
            for name in manifest:
                path = snapshot / name
                if not path.is_file():
                    bundle.errors[f"{rel}/{name}"] = "listed in manifest but missing on disk"
                    continue
                with bundle.step(f"{rel}/{name}"):
                    if path.suffix.lower() == ".csv":
                        with path.open(encoding="utf-8", errors="replace") as fh:
                            head = "".join(next(fh, "") for _ in range(HEAD_LINES))
                        bundle.write_text(f"{rel}/{name}.head.csv", head)
                        bundle.write_json(f"{rel}/{name}.profile.json", profile_csv(path))
                    elif path.suffix.lower() == ".json" and name != raw.MANIFEST_NAME:
                        bundle.write_json(f"{rel}/{name}.profile.json", profile_json(path))


# --------------------------------------------------------------------------- silver


def export_silver(bundle: Bundle, silver_dir: Path, mapping_dir: Path) -> None:
    """Summaries, every distinct label of target makes, full unmapped report, coverage."""
    files = sorted(silver_dir.glob("*.parquet")) if silver_dir.is_dir() else []
    if not files:
        return
    summary = []
    for p in files:
        with bundle.step(f"silver/{p.name}"):
            df = pl.read_parquet(p)
            row: dict = {"file": p.name, "rows": df.height, "columns": df.columns}
            if "period" in df.columns:
                row["period_min"], row["period_max"] = df["period"].min(), df["period"].max()
            if "country" in df.columns:
                row["countries"] = sorted(df["country"].unique().to_list())
            if "status" in df.columns:
                row["statuses"] = sorted(str(v) for v in df["status"].unique().to_list())
            if "count" in df.columns:
                row["count_sum"] = int(df["count"].sum())
            if "make_raw" in df.columns:
                row["distinct_make_raw"] = df["make_raw"].n_unique()
                row["distinct_model_raw"] = df["model_raw"].n_unique()
            if "model_gen" in df.columns and "count" in df.columns:
                mapped = df.filter(pl.col("model_gen").is_not_null())["count"].sum()
                row["mapped_share"] = (mapped / df["count"].sum()) if df["count"].sum() else None
            summary.append(row)
    bundle.write_json("silver/summary.json", summary)

    with bundle.step("silver/labels"):
        targets = load_targets(mapping_dir / TARGETS_FILE)
        target_makes = sorted({t.make for t in targets})
        stock_path = silver_dir / "fleet_stock.parquet"
        stock = (
            pl.read_parquet(stock_path)
            if stock_path.is_file()
            else pl.concat([pl.read_parquet(p) for p in files if p.name.startswith("fleet_stock_")])
        )
        key = [
            "country",
            "make_raw",
            "make",
            "model_gen_raw",
            "model_raw",
            "model_gen",
            "generation",
        ]
        labels = (
            stock.filter(pl.col("make").is_in(target_makes))
            .group_by(key)
            .agg(pl.col("count").sum(), pl.col("source_file").unique().sort().str.join("|"))
            .sort("country", "make", "count", descending=[False, False, True])
        )
        bundle.write_csv("silver/labels_target_makes.csv", labels)
        bundle.counts["labels_target_makes"] = labels.height
        unmapped = labels.filter(pl.col("model_gen").is_null()).sort("count", descending=True)
        bundle.write_csv("silver/unmapped_target_makes.csv", unmapped)
        bundle.counts["unmapped_rows"] = unmapped.height
        bundle.counts["unmapped_count"] = int(unmapped["count"].sum()) if unmapped.height else 0
        other_makes = (
            stock.filter(~pl.col("make").is_in(target_makes))
            .group_by("country", "make_raw", "make")
            .agg(pl.col("count").sum())
            .sort("count", descending=True)
        )
        bundle.write_csv("silver/other_makes.csv", other_makes)
    cov = silver_dir / "mapping_coverage.parquet"
    if cov.is_file():
        bundle.write_csv("silver/coverage.csv", pl.read_parquet(cov))


# --------------------------------------------------------------------------- anomalies


def anomalies(
    stock: pl.DataFrame,
    targets: list[TargetModel] | None = None,
    rise_threshold: float = 0.05,
    jump_threshold: float = 1.0,
) -> pl.DataFrame:
    """Data-quality signals on the annual series (never rejections, SPEC §8).

    * ``cohort_rise``: a generation-level stock rising by more than ``rise_threshold``
      year over year (imports / re-registrations, to document).
    * ``stock_jump``: |Δln stock| above ``jump_threshold`` between consecutive years
      (likely a source glitch or a label change).

    Only genuine cohorts are examined: generation-level series (VEH0124, RDW; never the
    label-derived generation rows of VEH0120) and, when ``targets`` is given, only years
    after the generation's production (``year_to`` + 1), so a new model's ramp-up is never
    reported as an anomaly.
    """
    annual = metrics.annual_stock(stock).filter(
        pl.col("series").is_in(metrics.GEN_LEVEL_SERIES) & pl.col("generation").is_not_null()
    )
    keys = ["country", "series", "make", "model_gen", "generation"]
    df = (
        annual.sort(*keys, "year")
        .with_columns(
            pl.col("stock").shift(1).over(keys).alias("prev_stock"),
            pl.col("year").shift(1).over(keys).alias("prev_year"),
        )
        .filter(
            pl.col("prev_stock").is_not_null() & (pl.col("prev_stock") > 0) & (pl.col("stock") > 0)
        )
        .with_columns(
            (pl.col("stock") / pl.col("prev_stock") - 1).alias("change"),
            (pl.col("stock").cast(pl.Float64).log() - pl.col("prev_stock").cast(pl.Float64).log())
            .abs()
            .alias("abs_dln"),
        )
    )
    if targets is not None:
        # Compare consecutive years on the full series, then keep only post-production years.
        ends = pl.DataFrame(
            [
                {
                    "make": t.make,
                    "model_gen": t.model_gen,
                    "generation": t.generation,
                    "year_to": t.year_to,
                }
                for t in targets
            ],
            schema={
                "make": pl.Utf8,
                "model_gen": pl.Utf8,
                "generation": pl.Utf8,
                "year_to": pl.Int32,
            },
        )
        df = (
            df.join(ends, on=["make", "model_gen", "generation"], how="inner")
            .filter(pl.col("year") > pl.col("year_to") + 1)
            .drop("year_to")
        )
    rises = df.filter(pl.col("change") > rise_threshold).with_columns(
        pl.lit("cohort_rise").alias("anomaly")
    )
    jumps = df.filter(pl.col("abs_dln") > jump_threshold).with_columns(
        pl.lit("stock_jump").alias("anomaly")
    )
    cols = ["anomaly", *keys, "prev_year", "year", "prev_stock", "stock", "change"]
    return pl.concat([rises.select(cols), jumps.select(cols)]).sort(
        "anomaly", "country", "change", descending=[False, False, True]
    )


def export_gold(bundle: Bundle, silver_dir: Path, gold_dir: Path, mapping_dir: Path) -> None:
    stock_path = silver_dir / "fleet_stock.parquet"
    if stock_path.is_file():
        with bundle.step("gold/anomalies"):
            targets = load_targets(mapping_dir / TARGETS_FILE)
            anom = anomalies(pl.read_parquet(stock_path), targets)
            bundle.write_csv("gold/anomalies.csv", anom)
            bundle.counts["anomalies"] = anom.height
    if not gold_dir.is_dir():
        return
    for p in sorted(gold_dir.glob("*.parquet")):
        with bundle.step(f"gold/{p.name}"):
            df = pl.read_parquet(p)
            list_cols = [c for c, t in df.schema.items() if t == pl.List(pl.Utf8)]
            df = df.with_columns(pl.col(c).list.join("|") for c in list_cols)
            bundle.write_csv(f"gold/{p.stem}.csv", df)
            bundle.counts[f"gold_{p.stem}_rows"] = df.height
    ranking = gold_dir / "ranking.csv"
    if ranking.is_file():
        shutil.copy(ranking, bundle.path("gold", "ranking.csv"))
        bundle.files.append("gold/ranking.csv")


# --------------------------------------------------------------------------- manifest


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _versions() -> dict[str, str]:
    out = {
        "predcar": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    for pkg in ("polars", "duckdb", "pydantic", "typer", "httpx"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "missing"
    return out


def export(
    out_dir: Path | None = None,
    raw_dir: Path = RAW_DIR,
    silver_dir: Path = SILVER_DIR,
    gold_dir: Path = GOLD_DIR,
    mapping_dir: Path = MAPPING_DIR,
    config_dir: Path = CONFIG_DIR,
) -> Path:
    """Write the evidence bundle and return its directory (default ``reports/<YYYY-MM-DD>/``)."""
    day = datetime.now(UTC).date().isoformat()
    out_dir = out_dir or ROOT / "reports" / day
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    bundle = Bundle(out_dir)

    for name, run in (
        ("raw", lambda: export_raw(bundle, raw_dir)),
        ("silver", lambda: export_silver(bundle, silver_dir, mapping_dir)),
        ("gold", lambda: export_gold(bundle, silver_dir, gold_dir, mapping_dir)),
    ):
        before = len(bundle.files)
        with bundle.step(name):
            run()
        if name in bundle.errors:
            bundle.stages[name] = "failed"
        elif len(bundle.files) == before:
            bundle.stages[name] = "absent"
        else:
            bundle.stages[name] = "ok"

    configs = {}
    for name in ("score.yaml", "mapping.yaml", "sources.yaml"):
        p = config_dir / name
        if p.is_file():
            configs[name] = p.read_text(encoding="utf-8")
    manifest = {
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git": {
            "sha": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(_git("status", "--porcelain")),
        },
        "versions": _versions(),
        "config": configs,
        "stages": bundle.stages,
        "counts": bundle.counts,
        "errors": bundle.errors,
        "files": sorted(bundle.files),
    }
    bundle.write_json("manifest.json", manifest)
    logger.info(
        "export written to %s (%d files, %d errors)", out_dir, len(bundle.files), len(bundle.errors)
    )
    return out_dir
