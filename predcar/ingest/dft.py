"""UK DfT/DVLA vehicle licensing statistics (VEH0120, VEH0124, VEH0160) → silver.

The three tables share one "wide" layout: identification columns followed by one column
per period (quarter or year). This module resolves the asset URLs from the GOV.UK
landing page, archives the CSVs, unpivots them and conforms them to the silver schemas.

The expected layout is documented in docs/sources/dft_uk.md. Any drift (missing id
column, no period column, unknown licence status) raises DftSchemaError instead of
silently producing wrong numbers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import httpx
import polars as pl

from predcar import raw, schemas
from predcar.config import SourcesConfig
from predcar.paths import SILVER_DIR

logger = logging.getLogger(__name__)

SOURCE = "uk_dft"
COUNTRY = "GB"
BODY_TYPE_CARS = "Cars"

_QUARTER_RE = re.compile(r"^(\d{4})\s*Q([1-4])$")
_YEAR_RE = re.compile(r"^(\d{4})$")
_INT_RE = re.compile(r"^-?\d+$")
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}

# Raw licence status labels → silver Status. "Total" rows are checked then dropped.
_STATUS_MAP = {"licensed": schemas.Status.LICENSED, "sorn": schemas.Status.SORN}
_TOTAL_LABELS = {"total", "all"}
# Aggregation over the raw columns the silver schema does not keep (Fuel, YearOfManufacture).
_AGG = [pl.col("count").sum(), pl.col("source").first()]


class DftSchemaError(ValueError):
    """The raw file does not have the documented layout."""


@dataclass(frozen=True)
class DftTable:
    """Layout of one DfT wide table."""

    name: str
    filename: str
    kind: Literal["stock", "new_reg"]
    id_columns: tuple[str, ...]
    period_kind: Literal["quarter", "year"]
    status_column: str | None = None
    default_status: schemas.Status | None = None
    year_first_reg_column: str | None = None


TABLES: dict[str, DftTable] = {
    "VEH0120": DftTable(
        name="VEH0120",
        filename="df_VEH0120_GB.csv",
        kind="stock",
        id_columns=("BodyType", "Make", "GenModel", "Model", "Fuel", "LicenceStatus"),
        period_kind="quarter",
        status_column="LicenceStatus",
    ),
    "VEH0124_AM": DftTable(
        name="VEH0124_AM",
        filename="df_VEH0124_AM.csv",
        kind="stock",
        id_columns=(
            "BodyType",
            "Make",
            "GenModel",
            "Model",
            "Fuel",
            "YearFirstUsed",
            "YearOfManufacture",
        ),
        period_kind="year",
        default_status=schemas.Status.LICENSED,
        year_first_reg_column="YearFirstUsed",
    ),
    "VEH0124_NZ": DftTable(
        name="VEH0124_NZ",
        filename="df_VEH0124_NZ.csv",
        kind="stock",
        id_columns=(
            "BodyType",
            "Make",
            "GenModel",
            "Model",
            "Fuel",
            "YearFirstUsed",
            "YearOfManufacture",
        ),
        period_kind="year",
        default_status=schemas.Status.LICENSED,
        year_first_reg_column="YearFirstUsed",
    ),
    "VEH0160": DftTable(
        name="VEH0160",
        filename="df_VEH0160_GB.csv",
        kind="new_reg",
        id_columns=("BodyType", "Make", "GenModel", "Model", "Fuel"),
        period_kind="quarter",
    ),
}


# --------------------------------------------------------------------------- fetch


def resolve_asset_urls(page_html: str, filenames: list[str]) -> dict[str, str]:
    """Find the download URL of each expected file name in the GOV.UK landing page.

    Args:
        page_html: HTML of the statistical-data-sets page.
        filenames: File names to look for (e.g. ``df_VEH0120_GB.csv``).

    Returns:
        filename → absolute URL.

    Raises:
        DftSchemaError: when a file name is not linked from the page.
    """
    found: dict[str, str] = {}
    for name in filenames:
        pattern = re.compile(r'href="([^"]*?/' + re.escape(name) + r')"')
        match = pattern.search(page_html)
        if not match:
            raise DftSchemaError(f"{name} not linked from the DfT landing page")
        url = match.group(1)
        found[name] = url if url.startswith("http") else "https://www.gov.uk" + url
    return found


def fetch(
    sources: SourcesConfig, client: httpx.Client | None = None, root: Path | None = None
) -> list[Path]:
    """Archive every configured DfT CSV into today's raw snapshot."""
    own_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=120)
    try:
        page = client.get(str(sources.uk_dft.page_url))
        page.raise_for_status()
        urls = resolve_asset_urls(page.text, sources.uk_dft.files)
        return [raw.archive(SOURCE, url, name, client, root) for name, url in urls.items()]
    finally:
        if own_client:
            client.close()


# --------------------------------------------------------------------------- parse


def parse_period(label: str, kind: Literal["quarter", "year"]) -> date | None:
    """Turn a column header into the period end date, or None if not a period column."""
    label = label.strip()
    if kind == "quarter":
        match = _QUARTER_RE.match(label)
        if not match:
            return None
        year, quarter = int(match.group(1)), int(match.group(2))
        month, day = _QUARTER_END[quarter]
        return date(year, month, day)
    match = _YEAR_RE.match(label)
    return date(int(match.group(1)), 12, 31) if match else None


def period_columns(columns: list[str], kind: Literal["quarter", "year"]) -> dict[str, date]:
    """Map each period column header to its end date."""
    return {c: d for c in columns if (d := parse_period(c, kind)) is not None}


def read_wide_csv(path: Path) -> pl.DataFrame:
    """Read a DfT CSV with every column as text and trimmed headers."""
    df = pl.read_csv(path, infer_schema_length=0, encoding="utf8-lossy")
    return df.rename({c: c.strip() for c in df.columns})


def _clean_count(col: pl.Expr) -> pl.Expr:
    """Parse counts; suppression markers ([c], [x], [z], ':', '-', '') become null."""
    cleaned = col.str.strip_chars().str.replace_all(",", "")
    return (
        pl.when(cleaned.str.contains(_INT_RE.pattern))
        .then(cleaned.cast(pl.Int64, strict=False))
        .otherwise(None)
    )


def parse_table(df: pl.DataFrame, table: DftTable) -> pl.DataFrame:
    """Unpivot one wide DfT table into the matching silver schema (cars only, unmapped).

    Rows with a suppressed or missing count are dropped and logged. Counts are summed
    over the columns the silver schema does not keep (Fuel, YearOfManufacture, Model
    case variants).

    Raises:
        DftSchemaError: on missing id columns, no period columns or unknown status.
    """
    missing = [c for c in table.id_columns if c not in df.columns]
    if missing:
        raise DftSchemaError(f"{table.name}: missing id columns {missing}; got {df.columns}")
    periods = period_columns(df.columns, table.period_kind)
    if not periods:
        raise DftSchemaError(f"{table.name}: no {table.period_kind} columns in {df.columns}")

    long = (
        df.filter(pl.col("BodyType").str.strip_chars() == BODY_TYPE_CARS)
        .unpivot(
            on=list(periods),
            index=list(table.id_columns),
            variable_name="period_label",
            value_name="count_raw",
        )
        .with_columns(
            pl.col("period_label").replace_strict(periods, return_dtype=pl.Date).alias("period"),
            _clean_count(pl.col("count_raw")).alias("count"),
        )
    )
    dropped = long.filter(pl.col("count").is_null()).height
    if dropped:
        logger.info("%s: dropped %d suppressed/blank values", table.name, dropped)
    long = long.filter(pl.col("count").is_not_null())

    long = long.with_columns(
        pl.col("Make").str.strip_chars().str.to_uppercase().alias("make_raw"),
        pl.col("GenModel").str.strip_chars().str.to_uppercase().alias("model_gen_raw"),
        pl.col("Model").str.strip_chars().str.to_uppercase().alias("model_raw"),
        pl.lit(COUNTRY).alias("country"),
        pl.lit(SOURCE).alias("source"),
        pl.lit(table.filename).alias("source_file"),
    )

    if table.kind == "new_reg":
        out = long.group_by(schemas.FLEET_NEW_REG_KEY).agg(_AGG)
        out = out.with_columns(pl.lit(None).alias(c) for c in ("make", "model_gen", "generation"))
        return schemas.conform(out, schemas.FLEET_NEW_REG_SCHEMA).sort(schemas.FLEET_NEW_REG_KEY)

    long = _with_status(long, table)
    if table.year_first_reg_column:
        long = long.with_columns(
            pl.col(table.year_first_reg_column).cast(pl.Int32, strict=False).alias("year_first_reg")
        )
    else:
        long = long.with_columns(pl.lit(None, dtype=pl.Int32).alias("year_first_reg"))
    out = long.group_by(schemas.FLEET_STOCK_KEY).agg(_AGG)
    out = out.with_columns(pl.lit(None).alias(c) for c in ("make", "model_gen", "generation"))
    return schemas.conform(out, schemas.FLEET_STOCK_SCHEMA).sort(schemas.FLEET_STOCK_KEY)


def _with_status(long: pl.DataFrame, table: DftTable) -> pl.DataFrame:
    """Map the raw licence status column, checking Total = Licensed + SORN when present."""
    if table.status_column is None:
        return long.with_columns(pl.lit(table.default_status).alias("status"))
    key = pl.col(table.status_column).str.strip_chars().str.to_lowercase()
    labels = set(long.select(key.alias("k"))["k"].unique().to_list())
    unknown = labels - set(_STATUS_MAP) - _TOTAL_LABELS
    if unknown:
        raise DftSchemaError(f"{table.name}: unknown licence status values {sorted(unknown)}")
    long = long.with_columns(key.alias("status_key"))
    totals = long.filter(pl.col("status_key").is_in(list(_TOTAL_LABELS)))
    if totals.height:
        _check_totals(long, totals, table)
        long = long.filter(~pl.col("status_key").is_in(list(_TOTAL_LABELS)))
    return long.with_columns(
        pl.col("status_key")
        .replace_strict({k: v.value for k, v in _STATUS_MAP.items()}, return_dtype=pl.Utf8)
        .alias("status")
    ).drop("status_key")


def _check_totals(long: pl.DataFrame, totals: pl.DataFrame, table: DftTable) -> None:
    group = ["make_raw", "model_gen_raw", "model_raw", "period"]
    # A suppressed Licensed or SORN cell has already been dropped: only groups where every
    # component status is visible can be compared with their Total.
    parts = (
        long.filter(pl.col("status_key").is_in(list(_STATUS_MAP)))
        .group_by(group)
        .agg(
            pl.col("count").sum().alias("parts"),
            pl.col("status_key").n_unique().alias("n_status"),
        )
        .filter(pl.col("n_status") == len(_STATUS_MAP))
        .drop("n_status")
    )
    tot = totals.group_by(group).agg(pl.col("count").sum().alias("total"))
    mismatch = parts.join(tot, on=group, how="inner").filter(pl.col("parts") != pl.col("total"))
    if mismatch.height:
        raise schemas.InvariantError(
            f"{table.name}: licensed + SORN != total for {mismatch.height} groups, "
            f"e.g. {mismatch.row(0, named=True)}"
        )


# --------------------------------------------------------------------------- ingest


def ingest(snapshot: Path, out_dir: Path = SILVER_DIR) -> dict[str, Path]:
    """Parse every DfT file present in a raw snapshot and write silver Parquet files.

    Args:
        snapshot: ``data/raw/uk_dft/<date>/`` directory (manifest is verified first).
        out_dir: Silver directory.

    Returns:
        Table name (``fleet_stock`` / ``fleet_new_reg``) → written Parquet path.
    """
    raw.verify(snapshot)
    _require_complete(snapshot)
    stocks: list[pl.DataFrame] = []
    new_regs: list[pl.DataFrame] = []
    for table in TABLES.values():
        parsed = parse_table(read_wide_csv(snapshot / table.filename), table)
        logger.info("%s: %d silver rows", table.name, parsed.height)
        (new_regs if table.kind == "new_reg" else stocks).append(parsed)

    out_dir.mkdir(parents=True, exist_ok=True)
    stock = pl.concat(stocks)
    schemas.check_fleet_stock(stock)
    new_reg = pl.concat(new_regs)
    schemas.check_fleet_new_reg(new_reg)
    written = {
        "fleet_stock": out_dir / "fleet_stock_uk_dft.parquet",
        "fleet_new_reg": out_dir / "fleet_new_reg_uk_dft.parquet",
    }
    stock.write_parquet(written["fleet_stock"])
    new_reg.write_parquet(written["fleet_new_reg"])
    return written


def _require_complete(snapshot: Path) -> None:
    """Every DfT table must be on disk and in the manifest; a partial fetch is not ingested."""
    manifest = raw.read_manifest(snapshot)
    missing = [
        t.filename
        for t in TABLES.values()
        if t.filename not in manifest or not (snapshot / t.filename).is_file()
    ]
    if missing:
        raise raw.RawArchiveError(
            f"incomplete DfT snapshot {snapshot}: missing {missing}; re-run fetch"
        )
