"""NL RDW open data (dataset m9d7-ebf2, Gekentekende voertuigen) → silver fleet_stock.

The dataset is a per-vehicle snapshot of the *current* Dutch fleet with no history, so we
build our own history: one aggregated snapshot per month archived under
``data/raw/nl_rdw/<YYYY-MM-DD>/``. Aggregation happens server-side (SoQL ``$group``) so no
per-vehicle row, and never the ``kenteken`` (licence plate), reaches this repository.

Expected layout is documented in docs/sources/rdw_nl.md; drift raises RdwSchemaError.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import polars as pl

from predcar import raw, schemas
from predcar.config import SourcesConfig
from predcar.paths import SILVER_DIR

logger = logging.getLogger(__name__)

SOURCE = "nl_rdw"
COUNTRY = "NL"
DATA_FILE = "gekentekende_voertuigen_agg.json"
QUERY_FILE = "query.json"
PAGE_SIZE = 50_000
FORBIDDEN_FIELDS = frozenset({"kenteken"})

# Column aliases returned by the aggregated query.
COL_MAKE = "merk"
COL_MODEL = "handelsbenaming"
COL_YEAR = "jaar"
COL_COUNT = "n"
EXPECTED_COLUMNS = (COL_MAKE, COL_MODEL, COL_YEAR, COL_COUNT)


class RdwSchemaError(ValueError):
    """The API response does not have the documented layout."""


def build_query(limit: int = PAGE_SIZE, offset: int = 0) -> dict[str, str]:
    """SoQL parameters counting the current passenger-car fleet by make, model, first-use year.

    Raises:
        RdwSchemaError: if a forbidden (personal) field sneaks into the projection.
    """
    params = {
        "$select": (
            f"{COL_MAKE},{COL_MODEL},"
            f"substring(datum_eerste_toelating,1,4) as {COL_YEAR},count(*) as {COL_COUNT}"
        ),
        "$where": "voertuigsoort='Personenauto'",
        "$group": f"{COL_MAKE},{COL_MODEL},{COL_YEAR}",
        "$order": f"{COL_MAKE},{COL_MODEL},{COL_YEAR}",
        "$limit": str(limit),
        "$offset": str(offset),
    }
    projected = params["$select"].lower()
    if any(field in projected for field in FORBIDDEN_FIELDS):
        raise RdwSchemaError(f"query projects a forbidden field: {params['$select']}")
    return params


def fetch_rows(
    api_url: str, client: httpx.Client, page_size: int = PAGE_SIZE
) -> list[dict[str, str]]:
    """Page through the aggregated query with ``$limit``/``$offset`` until a short page."""
    rows: list[dict[str, str]] = []
    offset = 0
    while True:
        resp = client.get(api_url, params=build_query(page_size, offset))
        resp.raise_for_status()
        page = resp.json()
        if not isinstance(page, list):
            raise RdwSchemaError(f"expected a JSON array, got {type(page).__name__}")
        rows.extend(page)
        logger.info("rdw: page offset=%d rows=%d", offset, len(page))
        if len(page) < page_size:
            return rows
        offset += page_size


def fetch(
    sources: SourcesConfig, client: httpx.Client | None = None, root: Path | None = None
) -> Path:
    """Archive one aggregated snapshot (rows + the exact query) into today's raw directory."""
    own_client = client is None
    client = client or httpx.Client(timeout=120)
    try:
        rows = fetch_rows(str(sources.nl_rdw.api_url), client)
    finally:
        if own_client:
            client.close()
    directory = raw.snapshot_dir(SOURCE, root=root)
    data_path = directory / DATA_FILE
    if data_path.exists():
        raise raw.RawArchiveError(f"{data_path} already exists; raw snapshots are immutable")
    data_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (directory / QUERY_FILE).write_text(
        json.dumps(
            {
                "api_url": str(sources.nl_rdw.api_url),
                "params": build_query(),
                "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "rows": len(rows),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    raw.register_file(directory, DATA_FILE, str(sources.nl_rdw.api_url))
    raw.register_file(directory, QUERY_FILE)
    return data_path


def parse_rows(rows: list[dict], period: date) -> pl.DataFrame:
    """Turn aggregated API rows into silver ``fleet_stock`` rows for one snapshot date.

    ``jaar`` outside 1900..period.year (or non-numeric) becomes null and the counts are
    summed into the null-year bucket; the number of affected rows is logged.

    Raises:
        RdwSchemaError: when expected columns are absent or ``n`` is not an integer.
    """
    if not rows:
        raise RdwSchemaError("empty response: refusing to write an empty snapshot")
    df = pl.DataFrame(rows, schema={c: pl.Utf8 for c in EXPECTED_COLUMNS}, strict=False)
    missing = [
        c for c in EXPECTED_COLUMNS if c not in df.columns or df[c].null_count() == df.height
    ]
    if missing:
        raise RdwSchemaError(f"missing columns {missing} in rows like {rows[0]}")

    count = pl.col(COL_COUNT).str.strip_chars().cast(pl.Int64, strict=False)
    if df.select(count.is_null().sum()).item():
        raise RdwSchemaError(f"non-integer {COL_COUNT} values in response")
    year = pl.col(COL_YEAR).str.strip_chars().cast(pl.Int32, strict=False)
    valid_year = year.is_between(1900, period.year)
    df = df.with_columns(
        count.alias("count"),
        pl.when(valid_year).then(year).otherwise(None).alias("year_first_reg"),
    )
    bad_years = df.filter(pl.col("year_first_reg").is_null()).height
    if bad_years:
        logger.info("rdw: %d rows with unusable %s bucketed as null year", bad_years, COL_YEAR)

    out = (
        df.with_columns(
            pl.col(COL_MAKE).str.strip_chars().str.to_uppercase().alias("make_raw"),
            pl.col(COL_MODEL).str.strip_chars().str.to_uppercase().alias("model_raw"),
            pl.lit(None, dtype=pl.Utf8).alias("model_gen_raw"),
            pl.lit(None, dtype=pl.Utf8).alias("status"),
            pl.lit(COUNTRY).alias("country"),
            pl.lit(period).alias("period"),
            pl.lit(SOURCE).alias("source"),
            pl.lit(DATA_FILE).alias("source_file"),
        )
        .group_by(schemas.FLEET_STOCK_KEY)
        .agg(pl.col("count").sum(), pl.col("source").first())
        .with_columns(pl.lit(None).alias(c) for c in ("make", "model_gen", "generation"))
    )
    return schemas.conform(out, schemas.FLEET_STOCK_SCHEMA).sort(schemas.FLEET_STOCK_KEY)


def ingest(snapshot: Path, out_dir: Path = SILVER_DIR) -> Path:
    """Parse one raw RDW snapshot into ``fleet_stock_nl_rdw_<date>.parquet``.

    The snapshot directory name (``YYYY-MM-DD``) is the observation period.
    """
    raw.verify(snapshot)
    data_path = snapshot / DATA_FILE
    if DATA_FILE not in raw.read_manifest(snapshot) or not data_path.is_file():
        raise raw.RawArchiveError(f"incomplete RDW snapshot {snapshot}: missing {DATA_FILE}")
    period = date.fromisoformat(snapshot.name)
    rows = json.loads(data_path.read_text(encoding="utf-8"))
    stock = parse_rows(rows, period)
    schemas.check_fleet_stock(stock)
    logger.info("rdw %s: %d silver rows", period, stock.height)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"fleet_stock_nl_rdw_{period.isoformat()}.parquet"
    stock.write_parquet(out)
    return out
