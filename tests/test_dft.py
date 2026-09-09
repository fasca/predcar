import json
from datetime import date
from pathlib import Path

import httpx
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


def test_total_check_skips_groups_with_a_suppressed_status(fixtures: Path) -> None:
    df = dft.read_wide_csv(fixtures / "df_VEH0120_GB.csv")
    # S2000 SORN suppressed in 2024 Q2 while Total stays numeric: valid source data.
    df = df.with_columns(
        pl.when((pl.col("GenModel") == "S2000") & (pl.col("LicenceStatus") == "SORN"))
        .then(pl.lit("[c]"))
        .otherwise(pl.col("2024 Q2"))
        .alias("2024 Q2")
    )
    out = dft.parse_table(df, dft.TABLES["VEH0120"])
    s2000_q2 = out.filter(
        (pl.col("model_raw") == "S2000") & (pl.col("period") == date(2024, 6, 30))
    )
    assert s2000_q2["status"].to_list() == ["licensed"]


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

    assert set(out["status"].to_list()) == {"licensed", "sorn"}
    e46_2001 = out.filter((pl.col("model_raw") == "M3 E46") & (pl.col("year_first_reg") == 2001))
    # the build year is kept (one row per year_first_reg × year_manufacture × period)
    assert sorted(e46_2001["year_manufacture"].unique().to_list()) == [2000, 2001]
    per_period = (
        e46_2001.group_by("period", "status").agg(pl.col("count").sum()).sort("period", "status")
    )
    assert per_period.filter(pl.col("status") == "licensed")["count"].to_list() == [342, 320]
    assert per_period.filter(pl.col("status") == "sorn")["count"].to_list() == [38, 40]
    # [z] / [low] markers dropped, never imputed as 0
    assert out.filter(pl.col("year_first_reg") == 1995).height == 0
    assert out.filter(pl.col("year_first_reg") == 2002).height == 1
    # "[x]" year of first use is kept as the null-year bucket
    unknown = out.filter(pl.col("year_first_reg").is_null())
    assert unknown["count"].to_list() == [3, 3]


def test_veh0124_total_check_is_per_cohort(fixtures: Path) -> None:
    """A SORN cell suppressed on one cohort must not invalidate the Total of another."""
    df = dft.read_wide_csv(fixtures / "df_VEH0124_AM.csv")
    # Totals are per cohort *and* build year, like every other row of the table.
    e46 = df.filter((pl.col("Model") == "M3 E46") & (pl.col("YearFirstUsed") == "2001"))
    totals = (
        e46.with_columns(pl.col("2023").cast(pl.Int64), pl.col("2022").cast(pl.Int64))
        .group_by("BodyType", "Make", "GenModel", "Model", "YearFirstUsed", "YearManufacture")
        .agg(pl.col("2023").sum().cast(pl.Utf8), pl.col("2022").sum().cast(pl.Utf8))
        .with_columns(pl.lit("Total").alias("LicenceStatus"))
        .select(df.columns)
    )
    out = dft.parse_table(pl.concat([df, totals]), dft.TABLES["VEH0124_AM"])
    assert "total" not in out["status"].to_list()
    bad = totals.with_columns(pl.lit("361").alias("2023"))
    with pytest.raises(schemas.InvariantError, match="licensed \\+ SORN != total"):
        dft.parse_table(pl.concat([df, bad]), dft.TABLES["VEH0124_AM"])


# --------------------------------------------------------------------------- VEH0160


def test_veh0160_new_registrations_sum_over_fuel(fixtures: Path) -> None:
    df = dft.read_wide_csv(fixtures / "df_VEH0160_GB.csv")
    out = dft.parse_table(df, dft.TABLES["VEH0160"])
    schemas.check_fleet_new_reg(out)

    g80 = out.filter(pl.col("model_raw") == "M3 G80").sort("period")
    assert g80["count"].to_list() == [98, 125]  # Q1: 95+3, Q2: 120+5
    assert "CBR 600" not in out["model_raw"].to_list()


# --------------------------------------------------------------------------- ingest


ALL_FILES = tuple(t.filename for t in dft.TABLES.values())


def _snapshot(fixtures: Path, tmp_path: Path, files: tuple[str, ...] = ALL_FILES) -> Path:
    snapshot = tmp_path / "raw" / "uk_dft" / "2026-09-08"
    snapshot.mkdir(parents=True)
    for name in files:
        (snapshot / name).write_bytes((fixtures / name).read_bytes())
        raw.register_file(snapshot, name)
    return snapshot


def test_ingest_snapshot_end_to_end(fixtures: Path, tmp_path: Path) -> None:
    snapshot = _snapshot(fixtures, tmp_path)
    written = dft.ingest(snapshot, tmp_path / "silver")
    assert set(written) == {"fleet_stock", "fleet_new_reg"}

    stock = pl.read_parquet(written["fleet_stock"])
    schemas.check_fleet_stock(stock)
    assert set(stock["source_file"].to_list()) == {
        "df_VEH0120_GB.csv",
        "df_VEH0124_AM.csv",
        "df_VEH0124_NZ.csv",
    }
    manifest = json.loads((snapshot / raw.MANIFEST_NAME).read_text())
    assert len(manifest) == len(ALL_FILES)


def test_ingest_refuses_incomplete_snapshot(fixtures: Path, tmp_path: Path) -> None:
    snapshot = _snapshot(fixtures, tmp_path, ALL_FILES[:-1])
    with pytest.raises(raw.RawArchiveError, match="incomplete.*df_VEH0160_GB.csv"):
        dft.ingest(snapshot, tmp_path / "silver")


def test_ingest_refuses_file_missing_from_manifest(fixtures: Path, tmp_path: Path) -> None:
    snapshot = _snapshot(fixtures, tmp_path, ALL_FILES[:-1])
    (snapshot / ALL_FILES[-1]).write_bytes((fixtures / ALL_FILES[-1]).read_bytes())
    with pytest.raises(raw.RawArchiveError, match="incomplete"):
        dft.ingest(snapshot, tmp_path / "silver")


def test_ingest_refuses_tampered_snapshot(fixtures: Path, tmp_path: Path) -> None:
    snapshot = _snapshot(fixtures, tmp_path)
    (snapshot / "df_VEH0160_GB.csv").write_text("BodyType\nCars\n")
    with pytest.raises(raw.RawArchiveError):
        dft.ingest(snapshot, tmp_path / "silver")


# --------------------------------------------------------------------------- fetch


def test_fetch_resolves_page_and_archives_every_file(fixtures: Path, tmp_path: Path) -> None:
    from predcar.config import load_sources_config

    page = (fixtures / "dft_landing_page.html").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".csv"):
            return httpx.Response(200, content=b"BodyType,Make\nCars,BMW\n")
        return httpx.Response(200, text=page)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    written = dft.fetch(load_sources_config(), client, root=tmp_path)
    assert sorted(p.name for p in written) == sorted(ALL_FILES)
    snapshot = written[0].parent
    assert set(raw.read_manifest(snapshot)) == set(ALL_FILES)
    raw.verify(snapshot)
