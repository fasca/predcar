"""DE KBA FZ 2 workbook → silver fleet_stock (sheet FZ 2.2, model-level German fleet).

FZ 2.2 is "Bestand an Personenkraftwagen nach Herstellern, Handelsnamen und ausgewählten
Merkmalen": the German car fleet at 1 January, by manufacturer and trade name. It is the
German equivalent of the DfT GenModel/Model pair, and the only KBA table at model level —
FZ 17 is make-level only, and the FZ 10 named in early drafts of the spec does not exist.

The table carries **no first-registration year**, so it yields no cohorts and no generations:
Germany is a model_gen-level series, like VEH0120.

Observed layout is documented in docs/sources/kba_de.md; drift raises KbaSchemaError.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import fastexcel
import httpx
import polars as pl

from predcar import raw, schemas
from predcar.config import SourcesConfig
from predcar.paths import SILVER_DIR

logger = logging.getLogger(__name__)

SOURCE = "de_kba"
COUNTRY = "DE"
DATA_FILE = "fz2.xlsx"
DEFAULT_SHEET = "FZ 2.2"

COL_MAKE = "Hersteller"
COL_MODEL = "Handelsname"
COL_COUNT = "Insgesamt"
REQUIRED_COLUMNS = (COL_MAKE, COL_MODEL, COL_COUNT)

# Header labels sit on two rows and move between vintages (row 8 or 9 in the workbook), so
# they are searched for rather than assumed. Scanning a few more rows than observed is free.
HEADER_SCAN_ROWS = 15

# Aggregate rows that would double-count the fleet if kept: the grand total (INSGESAMT) and
# the per-manufacturer subtotal (ZUSAMMEN). Their placement changed between vintages — the
# subtotal is appended to the manufacturer ("VOLKSWAGEN (D) ZUSAMMEN", empty trade name) up
# to 2024, and sits alone in the trade-name column from 2026 — so both columns are tested.
# Keeping them silently doubled the German fleet: ~96 M vehicles instead of ~49 M.
# The spelling is not reliable either: the 2019 file contains "CITROEN (F) ZSAMMEN".
TOTAL_LABELS = ("INSGESAMT", "ZUSAMMEN")
_TOTAL_RE = r"(?i)^(.*\s)?(INSGESAMT|ZU?SAMMEN)$"
# The grand total is published in the sheet and the parsed rows are checked against it, but
# the check is asymmetric. Detail rows *above* the total mean an aggregate row was counted
# twice — always a parser bug. Detail rows *below* it are expected: the KBA suppresses small
# counts ("." = value unknown or confidential) while still counting them in the total, which
# is 0.3 % of the fleet in 2026. Only a large shortfall means rows were wrongly dropped.
TOTAL_EXCESS_TOLERANCE = 0.001
TOTAL_SHORTFALL_TOLERANCE = 0.02
FOOTER_PREFIX = "©"

# The source itself says the model is unknown (config/mapping.yaml: unknown_labels).
UNKNOWN_MODELS = ("SONSTIGE/NICHT GETYPT", "SONSTIGE HERSTELLER")
# A manufacturer can open with rows carrying no trade name at all (old, untyped models).
# They are labelled, never dropped: their vehicles exist and must stay in the total.
MODEL_MISSING = "(MISSING)"


class KbaSchemaError(RuntimeError):
    """The FZ 2 workbook does not have the documented layout."""


# --------------------------------------------------------------------------- fetch


def fetch(
    cfg: SourcesConfig,
    year: int,
    client: httpx.Client | None = None,
    root: Path | None = None,
) -> Path:
    """Archive one FZ 2 vintage under ``data/raw/de_kba/<year>-01-01/``.

    The file name convention changed between vintages, so each candidate URL is tried in
    turn and the first one that exists wins; its resolved URL is recorded in the manifest.

    Args:
        cfg: source registry (``config/sources.yaml``).
        year: vintage, i.e. the 1 January the stock refers to.
        client: HTTP client, for tests.
        root: raw archive root, for tests.

    Returns:
        Path of the archived workbook.

    Raises:
        KbaSchemaError: when the year is outside the declared range.
        httpx.HTTPStatusError: when no candidate URL could be downloaded.
    """
    source = cfg.de_kba
    if not source.first_year <= year <= source.last_year:
        raise KbaSchemaError(
            f"year {year} outside the declared KBA range "
            f"{source.first_year}..{source.last_year}; check config/sources.yaml"
        )
    directory = raw.snapshot_dir(SOURCE, day=date(year, 1, 1), root=root)
    candidates = source.urls(year)
    last_error: httpx.HTTPStatusError | None = None
    for url in candidates:
        try:
            raw.download(url, directory / DATA_FILE, client)
        except httpx.HTTPStatusError as exc:
            last_error = exc
            logger.debug("kba %d: %s -> HTTP %s", year, url, exc.response.status_code)
            continue
        raw.register_file(directory, DATA_FILE, url)
        logger.info("kba %d: archived %s", year, url)
        return directory / DATA_FILE
    assert last_error is not None  # candidates is non-empty (file_patterns has min_length=1)
    raise last_error


# --------------------------------------------------------------------------- parsing


def _text(value: object) -> str:
    return "" if value is None else str(value).replace("\n", " ").strip()


def header_columns(sheet: pl.DataFrame) -> tuple[dict[str, int], int]:
    """Locate the required columns and the first data row of a raw FZ 2.2 sheet.

    The header spans two rows and its position moved between vintages (``Insgesamt`` sits one
    row above ``Hersteller`` in 2019-2021, on the same row from 2022 on), so every label is
    searched for independently. Data starts at the first row below the header whose count
    cell holds an integer — the row of sub-headings in between is skipped that way.

    Args:
        sheet: the sheet read with ``has_header=False``, values as text.

    Returns:
        Column index per required label, and the index of the first data row.

    Raises:
        KbaSchemaError: when a required label is missing, or no data row follows.
    """
    found: dict[str, int] = {}
    header_row = -1
    for i in range(min(HEADER_SCAN_ROWS, sheet.height)):
        for j, value in enumerate(sheet.row(i)):
            label = _text(value)
            if label in REQUIRED_COLUMNS and label not in found:
                found[label] = j
                header_row = max(header_row, i)
    missing = [c for c in REQUIRED_COLUMNS if c not in found]
    if missing:
        raise KbaSchemaError(
            f"missing column(s) {missing} in the first {HEADER_SCAN_ROWS} rows of the sheet; "
            f"the KBA layout changed, see docs/sources/kba_de.md"
        )
    count_column = found[COL_COUNT]
    for i in range(header_row + 1, sheet.height):
        if _text(sheet.row(i)[count_column]).replace(" ", "").isdigit():
            return found, i
    raise KbaSchemaError(f"no data row with an integer {COL_COUNT} below row {header_row}")


def sheet_total(sheet: pl.DataFrame, columns: dict[str, int]) -> int | None:
    """The grand total (``INSGESAMT``) published in the sheet, or None when absent."""
    names = sheet.columns
    make_col, model_col, count_col = (
        names[columns[COL_MAKE]],
        names[columns[COL_MODEL]],
        names[columns[COL_COUNT]],
    )
    for row in sheet.select(make_col, model_col, count_col).reverse().iter_rows():
        labels = {_text(row[0]).upper(), _text(row[1]).upper()}
        digits = _text(row[2]).replace(" ", "")
        if TOTAL_LABELS[0] in labels and digits.isdigit():
            return int(digits)
    return None


def parse_sheet(sheet: pl.DataFrame, period: date) -> pl.DataFrame:
    """Turn a raw FZ 2.2 sheet into silver ``fleet_stock`` rows for one vintage.

    ``Hersteller`` and ``Handelsname`` are only written on the first row of each group, so
    both are forward-filled. Rows are then aggregated over the technical variants
    (Typ-Schl.-Nr. × kW × fuel × body), giving one row per (manufacturer, trade name).

    Raises:
        KbaSchemaError: when the layout is unusable or every row was dropped.
    """
    columns, first_row = header_columns(sheet)
    names = sheet.columns

    def cell(label: str) -> pl.Expr:
        """The column holding ``label``, as trimmed text, empty cells becoming null."""
        expr = pl.col(names[columns[label]]).cast(pl.Utf8).str.strip_chars()
        return pl.when(expr.str.len_chars() > 0).then(expr).otherwise(None)

    df = sheet.slice(first_row).select(
        cell(COL_MAKE).alias("make_raw"),
        cell(COL_MODEL).alias("model_raw"),
        cell(COL_COUNT).alias("count"),
    )
    # Group labels are written once, on the first row of their group. The trade name is only
    # carried forward **within** a manufacturer: the first rows of a new manufacturer can have
    # no trade name at all, and would otherwise inherit the previous manufacturer's model.
    df = df.with_columns(
        pl.col("make_raw").forward_fill().str.to_uppercase(),
        pl.col("count").str.replace_all(r"\s", "").cast(pl.Int64, strict=False),
    ).with_columns(
        pl.col("model_raw").forward_fill().over("make_raw").str.to_uppercase(),
    )
    dropped = df.filter(pl.col("count").is_null()).height
    if dropped:
        # Suppression markers (".", "-", "/", "( )") and the trailing copyright line.
        logger.info("kba %s: dropped %d rows without an integer count", period, dropped)
    # fill_null(False): a null label is not a total, and Kleene logic would otherwise turn the
    # whole row filter null and silently drop it.
    totals = pl.col("make_raw").str.contains(_TOTAL_RE).fill_null(False) | pl.col(
        "model_raw"
    ).str.contains(_TOTAL_RE).fill_null(False)
    subtotal_rows = df.filter(totals).height
    df = df.filter(
        pl.col("count").is_not_null()
        & pl.col("make_raw").is_not_null()
        & ~totals
        & ~pl.col("make_raw").str.starts_with(FOOTER_PREFIX)
    )
    nameless = df.filter(pl.col("model_raw").is_null()).height
    if nameless:
        logger.info(
            "kba %s: %d rows without a trade name labelled %s", period, nameless, MODEL_MISSING
        )
    df = df.with_columns(pl.col("model_raw").fill_null(MODEL_MISSING))
    logger.debug("kba %s: %d total/subtotal rows excluded", period, subtotal_rows)
    if not df.height:
        raise KbaSchemaError(f"no usable row left for {period}: refusing to write an empty vintage")

    # The sheet publishes its own grand total. Checking against it is the only way to catch a
    # subtotal that slipped through — the 2019 sheet carries unlabelled aggregate rows, and
    # keeping them silently inflated the German fleet by millions of vehicles.
    declared = sheet_total(sheet, columns)
    parsed = int(df["count"].sum())
    if declared is not None:
        gap = parsed - declared
        if gap > declared * TOTAL_EXCESS_TOLERANCE:
            raise KbaSchemaError(
                f"{period}: parsed {parsed:,} vehicles but the sheet declares {declared:,} "
                f"(+{gap:,}); an aggregate row was counted twice — the layout has totals this "
                f"parser does not recognise, see docs/sources/kba_de.md"
            )
        if -gap > declared * TOTAL_SHORTFALL_TOLERANCE:
            raise KbaSchemaError(
                f"{period}: parsed {parsed:,} vehicles but the sheet declares {declared:,} "
                f"({gap:,}); too many rows were dropped to trust this vintage"
            )
        if gap:
            logger.info(
                "kba %s: %d vehicles (%.2f%%) counted in the total but not detailed "
                "(suppressed counts)",
                period,
                -gap,
                -100 * gap / declared,
            )

    out = (
        df.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("model_gen_raw"),
            pl.lit(None, dtype=pl.Int32).alias("year_first_reg"),
            pl.lit(None, dtype=pl.Int32).alias("year_manufacture"),
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


def read_sheet(path: Path, sheet_name: str) -> pl.DataFrame:
    """Read one worksheet as raw text cells, without interpreting a header row.

    fastexcel is called directly rather than through ``pl.read_excel``: the header block
    spans several rows and must be inspected as data, and every cell is wanted as text so
    nothing is silently coerced. Going through Polars would also emit a FutureWarning on
    every read with this version.
    """
    sheet = fastexcel.read_excel(str(path)).load_sheet(sheet_name, header_row=None, dtypes="string")
    return sheet.to_polars()


def ingest(
    snapshot: Path,
    out_dir: Path = SILVER_DIR,
    sheet_name: str | None = None,
) -> Path:
    """Parse one archived FZ 2 vintage into ``fleet_stock_de_kba_<year>.parquet``.

    The snapshot directory name (``YYYY-01-01``) is the observation period.
    """
    raw.verify(snapshot)
    workbook = raw.resolve(snapshot, DATA_FILE)
    if workbook is None:
        raise raw.RawArchiveError(f"incomplete KBA snapshot {snapshot}: missing {DATA_FILE}")
    period = date.fromisoformat(snapshot.name)
    stock = parse_sheet(read_sheet(workbook, sheet_name or DEFAULT_SHEET), period)
    schemas.check_fleet_stock(stock)
    logger.info(
        "kba %s: %d silver rows, %d vehicles", period, stock.height, int(stock["count"].sum())
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"fleet_stock_de_kba_{period.year}.parquet"
    stock.write_parquet(out)
    return out
