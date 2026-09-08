import gzip
import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from predcar import export, raw, schemas
from predcar import normalize as n
from predcar import score as sc
from predcar.config import load_score_config
from predcar.ingest import dft, rdw
from predcar.paths import CONFIG_DIR, MAPPING_DIR


def _pipeline(fixtures: Path, tmp_path: Path) -> dict[str, Path]:
    """raw → silver → normalize → score on the fixtures, all under tmp_path."""
    raw_dir, silver, gold = tmp_path / "raw", tmp_path / "silver", tmp_path / "gold"
    snap = raw_dir / "uk_dft" / "2026-09-08"
    snap.mkdir(parents=True)
    for t in dft.TABLES.values():
        (snap / t.filename).write_bytes((fixtures / t.filename).read_bytes())
        raw.register_file(snap, t.filename, "https://example.org/" + t.filename)
    dft.ingest(snap, silver)
    snap = raw_dir / "nl_rdw" / "2026-09-08"
    snap.mkdir(parents=True)
    (snap / rdw.DATA_FILE).write_bytes((fixtures / "rdw_agg_page.json").read_bytes())
    (snap / rdw.QUERY_FILE).write_text("{}")
    raw.register_file(snap, rdw.DATA_FILE)
    raw.register_file(snap, rdw.QUERY_FILE)
    rdw.ingest(snap, silver)
    n.normalize(silver, MAPPING_DIR, min_coverage=0.0)
    sc.score(silver, gold, MAPPING_DIR, load_score_config())
    return {"raw": raw_dir, "silver": silver, "gold": gold}


def test_export_full_bundle(fixtures: Path, tmp_path: Path) -> None:
    dirs = _pipeline(fixtures, tmp_path)
    out = export.export(
        tmp_path / "report", dirs["raw"], dirs["silver"], dirs["gold"], MAPPING_DIR, CONFIG_DIR
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["errors"] == {}
    assert manifest["stages"] == {"raw": "ok", "silver": "ok", "gold": "ok"}
    files = set(manifest["files"])
    assert {
        "raw/uk_dft/2026-09-08/df_VEH0120_GB.csv.head.csv",
        "raw/uk_dft/2026-09-08/df_VEH0120_GB.csv.profile.json",
        "raw/uk_dft/2026-09-08/MANIFEST.json",
        "raw/nl_rdw/2026-09-08/gekentekende_voertuigen_agg.json.profile.json",
        "silver/summary.json",
        "silver/labels_target_makes.csv",
        "silver/unmapped_target_makes.csv",
        "silver/coverage.csv",
        "silver/other_makes.csv",
        "gold/anomalies.csv",
        "gold/indicators.csv",
        "gold/scores.csv",
        "gold/ranking.csv",
    } <= files
    assert manifest["config"].keys() >= {"score.yaml", "mapping.yaml"}
    assert manifest["versions"]["polars"]
    # verbatim head: first line is the exact source header
    head = (out / "raw/uk_dft/2026-09-08/df_VEH0120_GB.csv.head.csv").read_text().splitlines()
    assert head[0] == (fixtures / "df_VEH0120_GB.csv").read_text().splitlines()[0]
    profile = json.loads((out / "raw/uk_dft/2026-09-08/df_VEH0120_GB.csv.profile.json").read_text())
    assert profile["id_columns"] == [
        "BodyType",
        "Make",
        "GenModel",
        "Model",
        "Fuel",
        "LicenceStatus",
    ]
    assert profile["n_quarter_columns"] == 3
    assert profile["distinct_values"]["LicenceStatus"] == ["Licensed", "SORN", "Total"]
    assert profile["value_markers"]["[c]"] == 3
    rdw_profile = json.loads(
        (out / "raw/nl_rdw/2026-09-08/gekentekende_voertuigen_agg.json.profile.json").read_text()
    )
    assert set(rdw_profile["keys"]) == {"merk", "handelsbenaming", "jaar", "n"}
    assert rdw_profile["rows"] == 7 and rdw_profile["value_types"]["n"] == ["str"]
    labels = pl.read_csv(out / "silver/labels_target_makes.csv")
    assert labels.height == manifest["counts"]["labels_target_makes"] > 0
    assert set(labels.columns) >= {"country", "make_raw", "model_raw", "model_gen", "count"}


def test_export_is_best_effort_on_empty_dirs(tmp_path: Path) -> None:
    out = export.export(
        tmp_path / "report",
        tmp_path / "raw",
        tmp_path / "silver",
        tmp_path / "gold",
        MAPPING_DIR,
        CONFIG_DIR,
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["files"] == ["manifest.json"] or manifest["files"] == []
    assert manifest["errors"] == {}
    # a stage that had nothing to export is distinguishable from one that succeeded
    assert manifest["stages"] == {"raw": "absent", "silver": "absent", "gold": "absent"}


def test_export_records_step_errors_instead_of_aborting(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    silver.mkdir()
    (silver / "fleet_stock_broken.parquet").write_bytes(b"not a parquet file")
    out = export.export(
        tmp_path / "report", tmp_path / "raw", silver, tmp_path / "gold", MAPPING_DIR, CONFIG_DIR
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert any(k.startswith("silver/") for k in manifest["errors"])
    assert (out / "silver/summary.json").exists()


def test_export_replaces_a_previous_bundle(tmp_path: Path) -> None:
    out = tmp_path / "report"
    out.mkdir()
    (out / "stale.txt").write_text("old")
    export.export(
        out, tmp_path / "raw", tmp_path / "silver", tmp_path / "gold", MAPPING_DIR, CONFIG_DIR
    )
    assert not (out / "stale.txt").exists()


def test_large_csv_is_gzipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "GZIP_ABOVE_BYTES", 10)
    bundle = export.Bundle(tmp_path)
    bundle.write_csv("x.csv", pl.DataFrame({"a": list(range(100))}))
    assert bundle.files == ["x.csv.gz"] and not (tmp_path / "x.csv").exists()
    with gzip.open(tmp_path / "x.csv.gz", "rt") as fh:
        assert fh.readline().strip() == "a"


def _row(**kw) -> dict:
    base = {
        "country": "GB",
        "period": date(2020, 12, 31),
        "make_raw": "M",
        "model_gen_raw": None,
        "model_raw": "X",
        "make": "M",
        "model_gen": "A",
        "generation": "G1",
        "year_first_reg": 2000,
        "status": "licensed",
        "count": 100,
        "source": "uk_dft",
        "source_file": "df_VEH0124_AM.csv",
    }
    return {**base, **kw}


def test_anomalies_flag_cohort_rises_and_jumps() -> None:
    stock = schemas.conform(
        pl.DataFrame(
            [
                _row(period=date(2020, 12, 31), count=100),
                _row(period=date(2021, 12, 31), count=120),  # +20 % → cohort_rise
                _row(period=date(2022, 12, 31), count=118),  # -1.7 % → nothing
                _row(period=date(2023, 12, 31), count=10),  # |Δln| ≈ 2.5 → stock_jump
                _row(
                    model_gen="B",
                    generation=None,
                    source_file="df_VEH0120_GB.csv",
                    period=date(2020, 12, 31),
                    count=50,
                ),
                _row(
                    model_gen="B",
                    generation=None,
                    source_file="df_VEH0120_GB.csv",
                    period=date(2021, 12, 31),
                    count=60,
                ),  # rise but no generation → ignored
            ]
        ),
        schemas.FLEET_STOCK_SCHEMA,
    )
    out = export.anomalies(stock)
    assert out.select("anomaly", "year").rows() == [("cohort_rise", 2021), ("stock_jump", 2023)]
