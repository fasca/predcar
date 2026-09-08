import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from predcar import raw, schemas
from predcar.ingest import dft

# --------------------------------------------------------------------------- URLs


def test_resolve_asset_urls_absolute_and_relative(fixtures: Path) -> None:
    html = (fixtures / "dft_landing_page.html").read_text()
    urls = dft.resolve_asset_urls(html, [t.filename for t in dft.TABLES.values()])
    assert urls["df_VEH0120_GB.csv"].endswith("/abc123/df_VEH0120_GB.csv")
    assert urls["df_VEH0124_AM.csv"] == "https://www.gov.uk/media/def456/df_VEH0124_AM.csv"


def test_resolve_asset_urls_missing_file_fails(fixtures: Path) -> None:
    html = (fixtures / "dft_landing_page.html").read_text()
    with pytest.raises(dft.DftSchemaError, match="df_VEH9999_GB.csv"):
        dft.resolve_asset_urls(html, ["df_VEH9999_GB.csv"])


# --------------------------------------------------------------------------- periods


@pytest.mark.parametrize(
    ("label", "kind", "expected"),
    [
        ("2024 Q2", "quarter", date(2024, 6, 30)),
        ("1994Q4", "quarter", date(1994, 12, 31)),
        (" 2023 Q1 ", "quarter", date(2023, 3, 31)),
        ("2023", "year", date(2023, 12, 31)),
        ("Make", "quarter", None),
        ("2023", "quarter", None),
        ("2024 Q2", "year", None),
        ("2024 Q5", "quarter", None),
    ],
)
def test_parse_period(label: str, kind: str, expected: date | None) -> None:
    assert dft.parse_period(label, kind) == expected


# --------------------------------------------------------------------------- VEH0120


def test_veh0120_unpivot_cars_only_with_status(fixtures: Path) -> None:
    df = dft.read_wide_csv(fixtures / "df_VEH0120_GB.csv")
    out = dft.parse_table(df, dft.TABLES["VEH0120"])
    schemas.check_fleet_stock(out)

    assert out["make_raw"].unique().sort().to_list() == ["BMW", "HONDA"]  # no motorcycles
    assert set(out["status"].unique().to_list()) == {"licensed", "sorn"}  # Total dropped
    assert out["year_first_reg"].null_count() == out.height

    e46 = out.filter(pl.col("model_raw") == "M3 E46").sort("period", "status")
    assert e46.filter(pl.col("period") == date(2024, 6, 30))["count"].to_list() == [1200, 300]
    # "[c]" suppressed values are dropped, not zeroed
    csl = out.filter(pl.col("model_raw") == "M3 CSL")
    assert date(2023, 12, 31) not in csl["period"].to_list()
    assert csl.height == 4


def test_veh0120_total_mismatch_is_an_invariant_error(fixtures: Path) -> None:
    df = dft.read_wide_csv(fixtures / "df_VEH0120_GB.csv")
    df = df.with_columns(
        pl.when(pl.col("LicenceStatus") == "Total")
        .then(pl.lit("1"))
        .otherwise(pl.col("2024 Q2"))
        .alias("2024 Q2")
    )
    with pytest.raises(schemas.InvariantError, match="licensed \\+ SORN != total"):
        dft.parse_table(df, dft.TABLES["VEH0120"])


def test_unknown_status_label_fails_loudly(fixtures: Path) -> None:
    df = dft.read_wide_csv(fixtures / "df_VEH0120_GB.csv")
    df = df.with_columns(pl.col("LicenceStatus").str.replace("SORN", "Untaxed"))
    with pytest.raises(dft.DftSchemaError, match="untaxed"):
        dft.parse_table(df, dft.TABLES["VEH0120"])


def test_missing_id_column_fails_loudly(fixtures: Path) -> None:
    df = dft.read_wide_csv(fixtures / "df_VEH0120_GB.csv").drop("GenModel")
    with pytest.raises(dft.DftSchemaError, match="GenModel"):
        dft.parse_table(df, dft.TABLES["VEH0120"])


def test_no_period_column_fails_loudly(fixtures: Path) -> None:
    df = dft.read_wide_csv(fixtures / "df_VEH0120_GB.csv")
    df = df.rename({"2024 Q2": "a", "2024 Q1": "b", "2023 Q4": "c"})
    with pytest.raises(dft.DftSchemaError, match="no quarter columns"):
        dft.parse_table(df, dft.TABLES["VEH0120"])


# --------------------------------------------------------------------------- VEH0124


def test_veh0124_cohorts_sum_over_manufacture_year(fixtures: Path) -> None:
    df = dft.read_wide_csv(fixtures / "df_VEH0124_AM.csv")
    out = dft.parse_table(df, dft.TABLES["VEH0124_AM"])
    schemas.check_fleet_stock(out)

    assert set(out["status"].to_list()) == {"licensed"}
    e46_2001 = out.filter((pl.col("model_raw") == "M3 E46") & (pl.col("year_first_reg") == 2001))
    assert e46_2001.sort("period")["count"].to_list() == [342, 320]  # 320+22, 300+20... sorted
    # [z] / [low] markers dropped
    assert out.filter(pl.col("year_first_reg") == 1995).height == 0
    assert out.filter(pl.col("year_first_reg") == 2002).height == 1


# --------------------------------------------------------------------------- VEH0160


def test_veh0160_new_registrations_sum_over_fuel(fixtures: Path) -> None:
    df = dft.read_wide_csv(fixtures / "df_VEH0160_GB.csv")
    out = dft.parse_table(df, dft.TABLES["VEH0160"])
    schemas.check_fleet_new_reg(out)

    g80 = out.filter(pl.col("model_raw") == "M3 G80").sort("period")
    assert g80["count"].to_list() == [98, 125]  # Q1: 95+3, Q2: 120+5
    assert "CBR 600" not in out["model_raw"].to_list()


# --------------------------------------------------------------------------- ingest


def test_ingest_snapshot_end_to_end(fixtures: Path, tmp_path: Path) -> None:
    snapshot = tmp_path / "raw" / "uk_dft" / "2026-09-08"
    snapshot.mkdir(parents=True)
    for name in ("df_VEH0120_GB.csv", "df_VEH0124_AM.csv", "df_VEH0160_GB.csv"):
        (snapshot / name).write_bytes((fixtures / name).read_bytes())
        raw.register_file(snapshot, name)

    written = dft.ingest(snapshot, tmp_path / "silver")
    assert set(written) == {"fleet_stock", "fleet_new_reg"}

    stock = pl.read_parquet(written["fleet_stock"])
    schemas.check_fleet_stock(stock)
    assert set(stock["source_file"].to_list()) == {"df_VEH0120_GB.csv", "df_VEH0124_AM.csv"}
    manifest = json.loads((snapshot / raw.MANIFEST_NAME).read_text())
    assert len(manifest) == 3


def test_ingest_refuses_tampered_snapshot(fixtures: Path, tmp_path: Path) -> None:
    snapshot = tmp_path / "raw" / "uk_dft" / "2026-09-08"
    snapshot.mkdir(parents=True)
    (snapshot / "df_VEH0160_GB.csv").write_bytes((fixtures / "df_VEH0160_GB.csv").read_bytes())
    raw.register_file(snapshot, "df_VEH0160_GB.csv")
    (snapshot / "df_VEH0160_GB.csv").write_text("BodyType\nCars\n")
    with pytest.raises(raw.RawArchiveError):
        dft.ingest(snapshot, tmp_path / "silver")
