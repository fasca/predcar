"""KBA FZ 2 ingestion.

Fixtures are cut from the real workbooks (2024 and 2020), keeping their header block, a few
manufacturer groups and their subtotals, so the two header layouts are both exercised on
genuine rows rather than on an imagined schema.
"""

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from openpyxl import Workbook

from predcar import raw, schemas
from predcar.config import load_sources_config
from predcar.ingest import kba

INLINE = "kba_fz2_header_inline.xlsx"  # 2024 layout: every label on one header row
SPLIT = "kba_fz2_header_split.xlsx"  # 2020 layout: Insgesamt one row above Hersteller
SHEET = "FZ 2.2"


def _sheet(fixtures: Path, name: str) -> pl.DataFrame:
    return kba.read_sheet(fixtures / name, SHEET)


def _write_sheet(path: Path, rows: list[list[object]]) -> Path:
    book = Workbook()
    book.remove(book.active)
    sheet = book.create_sheet(SHEET)
    for row in rows:
        sheet.append(row)
    book.save(path)
    return path


# --------------------------------------------------------------------------- header


@pytest.mark.parametrize("name", [INLINE, SPLIT])
def test_header_is_located_whatever_its_row(fixtures: Path, name: str) -> None:
    """The header row moved between vintages, so it is searched for, never assumed."""
    columns, first_row = kba.header_columns(_sheet(fixtures, name))
    assert set(columns) == set(kba.REQUIRED_COLUMNS)
    assert first_row > 0


@pytest.mark.parametrize("name", [INLINE, SPLIT])
def test_both_layouts_parse_to_the_same_shape(fixtures: Path, name: str) -> None:
    stock = kba.parse_sheet(_sheet(fixtures, name), date(2024, 1, 1))
    assert list(stock.columns) == list(schemas.FLEET_STOCK_SCHEMA)
    assert stock.height > 0
    schemas.check_fleet_stock(stock)


def test_missing_required_column_is_an_error(tmp_path: Path) -> None:
    path = _write_sheet(
        tmp_path / "broken.xlsx",
        [["Hersteller", "Handelsname", "Typ"], ["ALPINA", "B3", "ABK"]],
    )
    with pytest.raises(kba.KbaSchemaError, match="Insgesamt"):
        kba.header_columns(kba.read_sheet(path, SHEET))


def test_header_without_any_data_row_is_an_error(tmp_path: Path) -> None:
    path = _write_sheet(
        tmp_path / "empty.xlsx",
        [["Hersteller", "Handelsname", "Insgesamt"], ["ALPINA", "B3", "-"]],
    )
    with pytest.raises(kba.KbaSchemaError, match="no data row"):
        kba.header_columns(kba.read_sheet(path, SHEET))


# --------------------------------------------------------------------------- parsing


def test_labels_are_carried_forward_within_a_manufacturer(fixtures: Path) -> None:
    """Group labels are written once; every parsed row must still carry make and model."""
    stock = kba.parse_sheet(_sheet(fixtures, INLINE), date(2024, 1, 1))
    assert stock["make_raw"].null_count() == 0
    assert stock["model_raw"].null_count() == 0
    assert stock["make_raw"].unique().len() >= 2


def test_trade_name_does_not_leak_across_manufacturers(tmp_path: Path) -> None:
    """A new manufacturer opening without a trade name must not inherit the previous one's.

    Real case: in the 2019 file the Audi block opens with rows that have no trade name, right
    after the Aston Martin block — forward-filling across the boundary credited Audi rows to
    an Aston Martin model.
    """
    path = _write_sheet(
        tmp_path / "boundary.xlsx",
        [
            ["Hersteller", "Handelsname", "Insgesamt"],
            [None, None, None],
            ["ASTON MARTIN (UK)", "DB11", 100],
            ["AUDI (D)", None, 50],
            [None, None, 30],
            [None, "A4", 20],
            ["INSGESAMT", None, 200],
        ],
    )
    stock = kba.parse_sheet(kba.read_sheet(path, SHEET), date(2024, 1, 1))
    audi = stock.filter(pl.col("make_raw") == "AUDI (D)")
    assert "DB11" not in audi["model_raw"].to_list()
    assert kba.MODEL_MISSING in audi["model_raw"].to_list()
    # the nameless rows are labelled, never dropped: their vehicles stay in the total
    assert int(stock["count"].sum()) == 200


@pytest.mark.parametrize("name", [INLINE, SPLIT])
def test_totals_are_excluded_and_the_sum_matches_the_sheet(fixtures: Path, name: str) -> None:
    """The decisive check: keeping a subtotal doubles the fleet, dropping rows shrinks it."""
    sheet = _sheet(fixtures, name)
    columns, _ = kba.header_columns(sheet)
    declared = kba.sheet_total(sheet, columns)
    stock = kba.parse_sheet(sheet, date(2024, 1, 1))
    assert declared is not None
    assert int(stock["count"].sum()) == declared
    labels = set(stock["make_raw"]) | set(stock["model_raw"])
    assert not any("ZUSAMMEN" in label or "INSGESAMT" in label for label in labels)
    assert not any(label.startswith(kba.FOOTER_PREFIX) for label in labels)


def test_misspelt_subtotal_is_still_excluded(tmp_path: Path) -> None:
    """The 2019 sheet spells one subtotal "CITROEN (F) ZSAMMEN"."""
    path = _write_sheet(
        tmp_path / "typo.xlsx",
        [
            ["Hersteller", "Handelsname", "Insgesamt"],
            [None, None, None],
            ["CITROEN (F)", "C3", 60],
            [None, "C4", 40],
            ["CITROEN (F) ZSAMMEN", None, 100],
            ["INSGESAMT", None, 100],
        ],
    )
    stock = kba.parse_sheet(kba.read_sheet(path, SHEET), date(2024, 1, 1))
    assert int(stock["count"].sum()) == 100


def test_double_counted_total_is_refused(tmp_path: Path) -> None:
    """An unrecognised aggregate row must fail the vintage, not inflate the fleet."""
    path = _write_sheet(
        tmp_path / "excess.xlsx",
        [
            ["Hersteller", "Handelsname", "Insgesamt"],
            [None, None, None],
            ["OPEL", "CORSA", 60],
            [None, "ASTRA", 40],
            [None, None, 100],  # unlabelled aggregate, as seen in the 2019 sheet
            ["INSGESAMT", None, 100],
        ],
    )
    with pytest.raises(kba.KbaSchemaError, match="counted twice"):
        kba.parse_sheet(kba.read_sheet(path, SHEET), date(2024, 1, 1))


def test_small_shortfall_is_accepted_and_reported(tmp_path: Path) -> None:
    """The KBA suppresses small counts but still totals them: a shortfall is expected."""
    path = _write_sheet(
        tmp_path / "shortfall.xlsx",
        [
            ["Hersteller", "Handelsname", "Insgesamt"],
            [None, None, None],
            ["OPEL", "CORSA", 999],
            [None, "ASTRA", "."],  # suppressed count
            ["INSGESAMT", None, 1000],
        ],
    )
    stock = kba.parse_sheet(kba.read_sheet(path, SHEET), date(2024, 1, 1))
    assert int(stock["count"].sum()) == 999


def test_large_shortfall_is_refused(tmp_path: Path) -> None:
    path = _write_sheet(
        tmp_path / "gap.xlsx",
        [
            ["Hersteller", "Handelsname", "Insgesamt"],
            [None, None, None],
            ["OPEL", "CORSA", 100],
            ["INSGESAMT", None, 1000],
        ],
    )
    with pytest.raises(kba.KbaSchemaError, match="too many rows were dropped"):
        kba.parse_sheet(kba.read_sheet(path, SHEET), date(2024, 1, 1))


def test_variants_of_one_trade_name_are_summed(tmp_path: Path) -> None:
    """One row per (manufacturer, trade name): engine and body variants are aggregated."""
    path = _write_sheet(
        tmp_path / "variants.xlsx",
        [
            ["Hersteller", "Handelsname", "Insgesamt"],
            [None, None, None],
            ["ALPINA", "B3", 10],
            [None, None, 20],
            [None, None, 30],
            ["INSGESAMT", None, 60],
        ],
    )
    stock = kba.parse_sheet(kba.read_sheet(path, SHEET), date(2024, 1, 1))
    assert stock.height == 1
    assert stock["count"][0] == 60


def test_unknown_model_label_is_kept(fixtures: Path) -> None:
    """ "SONSTIGE/NICHT GETYPT" is the source saying the model is unknown: never dropped."""
    stock = kba.parse_sheet(_sheet(fixtures, INLINE), date(2024, 1, 1))
    assert any(label in kba.UNKNOWN_MODELS for label in stock["model_raw"])


def test_silver_shape_matches_a_snapshot_source(fixtures: Path) -> None:
    """No first-registration year, no status: Germany is a model_gen-level series."""
    stock = kba.parse_sheet(_sheet(fixtures, INLINE), date(2024, 1, 1))
    assert stock["country"].unique().to_list() == ["DE"]
    assert stock["period"].unique().to_list() == [date(2024, 1, 1)]
    for column in ("year_first_reg", "year_manufacture", "status", "model_gen_raw"):
        assert stock[column].null_count() == stock.height, column


# --------------------------------------------------------------------------- ingest


def test_ingest_end_to_end(fixtures: Path, tmp_path: Path) -> None:
    snapshot = tmp_path / "raw" / kba.SOURCE / "2024-01-01"
    snapshot.mkdir(parents=True)
    (snapshot / kba.DATA_FILE).write_bytes((fixtures / INLINE).read_bytes())
    raw.register_file(snapshot, kba.DATA_FILE, "https://example.org/fz2_2024.xlsx")

    out = kba.ingest(snapshot, tmp_path / "silver")
    assert out.name == "fleet_stock_de_kba_2024.parquet"
    stock = pl.read_parquet(out)
    schemas.check_fleet_stock(stock)
    assert stock["source"].unique().to_list() == [kba.SOURCE]


def test_ingest_refuses_a_snapshot_without_its_payload(tmp_path: Path) -> None:
    snapshot = tmp_path / "raw" / kba.SOURCE / "2024-01-01"
    snapshot.mkdir(parents=True)
    (snapshot / kba.DATA_FILE).write_text("x")
    raw.register_file(snapshot, kba.DATA_FILE)
    (snapshot / kba.DATA_FILE).unlink()
    with pytest.raises(raw.RawArchiveError):
        kba.ingest(snapshot, tmp_path / "silver")


# --------------------------------------------------------------------------- fetch


def test_fetch_rejects_a_year_outside_the_declared_range() -> None:
    cfg = load_sources_config()
    with pytest.raises(kba.KbaSchemaError, match="outside the declared"):
        kba.fetch(cfg, cfg.de_kba.first_year - 1)


def test_source_urls_cover_both_naming_conventions() -> None:
    cfg = load_sources_config()
    urls = cfg.de_kba.urls(2020)
    assert len(urls) == 2
    assert any(u.endswith("fz2_2020.xlsx?__blob=publicationFile") for u in urls)
    assert any(u.endswith("fz2_2020_xlsx.xlsx?__blob=publicationFile") for u in urls)


def test_unlabelled_aggregate_row_is_excluded(tmp_path: Path) -> None:
    """The 2019 sheet publishes Audi's subtotal without its label: 3 124 094 vehicles.

    Such a row has a count but no make, no trade name **and** no technical column. A real
    variant row always carries a Typ-Schl.-Nr., a power rating or a fuel type, so the two
    cannot be confused — which is what makes the exclusion safe.
    """
    path = _write_sheet(
        tmp_path / "aggregate.xlsx",
        [
            ["Hersteller", "Handelsname", "Typ-Schl.-Nr.", "kW", "Kraftstoffart", "Insgesamt"],
            [None, None, None, None, None, None],
            ["AUDI (D)", "A4", "8E", 130, "B", 60],
            [None, None, "8H", 120, "D", 40],  # a real variant: no labels but technical columns
            [None, None, None, None, None, 100],  # the unlabelled subtotal
            ["AUDI (H)", "TT", "8J", 147, "B", 25],
            ["INSGESAMT", None, None, None, None, 125],
        ],
    )
    stock = kba.parse_sheet(kba.read_sheet(path, SHEET), date(2019, 1, 1))
    assert int(stock["count"].sum()) == 125
    # the variant row is kept and merged into its model
    audi = stock.filter(pl.col("make_raw") == "AUDI (D)")
    assert int(audi["count"].sum()) == 100


def test_subtotal_misspelt_with_a_trailing_m_is_excluded(tmp_path: Path) -> None:
    """The 2021 and 2022 sheets spell one subtotal "HYUNDAI MOTOR (ROK) ZUSAMMEM"."""
    path = _write_sheet(
        tmp_path / "typo_m.xlsx",
        [
            ["Hersteller", "Handelsname", "Typ-Schl.-Nr.", "Insgesamt"],
            [None, None, None, None],
            ["HYUNDAI MOTOR (ROK)", "I30", "ABC", 70],
            [None, "TUCSON", "ABD", 30],
            ["HYUNDAI MOTOR (ROK) ZUSAMMEM", None, None, 100],
            ["INSGESAMT", None, None, 100],
        ],
    )
    stock = kba.parse_sheet(kba.read_sheet(path, SHEET), date(2021, 1, 1))
    assert int(stock["count"].sum()) == 100
    assert not any("ZUSAMME" in label for label in stock["make_raw"])
