from datetime import date
from pathlib import Path

import polars as pl
import pytest

from predcar import normalize as n
from predcar import raw, schemas
from predcar.ingest import dft, rdw
from predcar.paths import MAPPING_DIR

RULES = [
    n.ModelRule(
        make="BMW",
        model_raw_regex=r"^M3\b",
        year_from=1992,
        year_to=1999,
        model_gen="M3",
        generation="E36",
    ),
    n.ModelRule(
        make="BMW",
        model_raw_regex=r"^M3\b",
        year_from=2000,
        year_to=2006,
        model_gen="M3",
        generation="E46",
    ),
    n.ModelRule(make="BMW", model_raw_regex=r"^M3 CSL", model_gen="M3", generation="E46"),
    n.ModelRule(make="BMW", model_raw_regex=r"^3[0-9][0-9]", model_gen="3 SERIES"),
    n.ModelRule(make="HONDA", model_raw_regex=r"^S ?2000", model_gen="S2000", generation="AP1_AP2"),
]
MAKES = {"BMW": "BMW", "HONDA": "HONDA", "BAYERISCHE MOTOREN WERKE": "BMW"}


def _stock(rows: list[dict]) -> pl.DataFrame:
    base = {
        "country": "GB",
        "period": date(2024, 6, 30),
        "make_raw": "BMW",
        "model_gen_raw": None,
        "model_raw": "M3",
        "make": None,
        "model_gen": None,
        "generation": None,
        "year_first_reg": None,
        "status": "licensed",
        "count": 1,
        "source": "t",
        "source_file": "t.csv",
    }
    return schemas.conform(pl.DataFrame([{**base, **r} for r in rows]), schemas.FLEET_STOCK_SCHEMA)


# --------------------------------------------------------------------------- apply


def test_apply_resolves_year_ranges_and_label_only_rules() -> None:
    df = _stock(
        [
            {"model_raw": "M3", "year_first_reg": 2003},  # ranged rule → E46
            {"model_raw": "M3", "year_first_reg": 1995},  # ranged rule → E36
            {"model_raw": "M3", "year_first_reg": None},  # only ranged → model_gen, no gen
            {"model_raw": "M3 CSL", "year_first_reg": None},  # label-only → E46
            {"model_raw": "M3", "year_first_reg": 2010},  # out of every range → unmapped
            {"model_raw": "330I SE", "year_first_reg": None},  # catch-all
            {"model_raw": "X5", "year_first_reg": None},  # no rule
            {"make_raw": "BAYERISCHE MOTOREN WERKE", "model_raw": "M3", "year_first_reg": 2001},
            {"make_raw": "HONDA", "model_raw": "S2000", "year_first_reg": 2004},
            {"make_raw": "UNKNOWN", "model_raw": "THING", "year_first_reg": None},
        ]
    )
    out = n.apply(df, MAKES, RULES)
    assert out.columns == df.columns
    assert out["make"].to_list() == ["BMW"] * 8 + ["HONDA", "UNKNOWN"]  # identity fallback
    assert out["model_gen"].to_list() == [
        "M3",
        "M3",
        "M3",
        "M3",
        None,
        "3 SERIES",
        None,
        "M3",
        "S2000",
        None,
    ]
    assert out["generation"].to_list() == [
        "E46",
        "E36",
        None,
        "E46",
        None,
        None,
        None,
        "E46",
        "AP1_AP2",
        None,
    ]


def test_apply_works_without_year_column() -> None:
    df = _stock([{"model_raw": "M3 CSL"}]).drop("year_first_reg", "status")
    out = n.apply(df, MAKES, RULES)
    assert out.columns == df.columns
    assert out.row(0, named=True)["generation"] == "E46"


def test_apply_rejects_conflicting_model_gen() -> None:
    rules = RULES + [n.ModelRule(make="BMW", model_raw_regex=r"CSL", model_gen="M3 CSL")]
    with pytest.raises(n.MappingError, match="conflicting"):
        n.apply(_stock([{"model_raw": "M3 CSL"}]), MAKES, rules)


def test_apply_rejects_conflicting_generation() -> None:
    rules = RULES + [
        n.ModelRule(
            make="BMW",
            model_raw_regex=r"^M3\b",
            year_from=2003,
            year_to=2003,
            model_gen="M3",
            generation="E46_LCI",
        )
    ]
    with pytest.raises(n.MappingError, match="conflicting"):
        n.apply(_stock([{"model_raw": "M3", "year_first_reg": 2003}]), MAKES, rules)


# --------------------------------------------------------------------------- rules


def test_model_rule_validation() -> None:
    with pytest.raises(ValueError, match="invalid regex"):
        n.ModelRule(make="X", model_raw_regex="(", model_gen="Y")
    with pytest.raises(ValueError, match="both set"):
        n.ModelRule(make="X", model_raw_regex="a", year_from=2000, model_gen="Y")
    with pytest.raises(ValueError, match="year_from > year_to"):
        n.ModelRule(make="X", model_raw_regex="a", year_from=2001, year_to=2000, model_gen="Y")


def test_load_files_reject_bad_headers(tmp_path: Path) -> None:
    (tmp_path / "makes.csv").write_text("alias,brand\nBMW,BMW\n")
    with pytest.raises(n.MappingError, match="alias,make"):
        n.load_makes(tmp_path / "makes.csv")
    with pytest.raises(n.MappingError, match="missing mapping file"):
        n.load_models(tmp_path / "models.csv")


# --------------------------------------------------------------------------- coverage


TARGETS = [
    n.TargetModel(
        make="BMW",
        model_gen="M3",
        generation="E46",
        segment="SPORTIVE",
        year_from=2000,
        year_to=2006,
    )
]


def test_coverage_and_unmapped_report() -> None:
    df = n.apply(
        _stock(
            [
                {"model_raw": "M3", "year_first_reg": 2003, "count": 90},
                {"model_raw": "X5", "count": 10},
                {"country": "NL", "model_raw": "X5", "count": 5},
                {"make_raw": "HONDA", "model_raw": "S2000", "count": 1000},  # not a target make
            ]
        ),
        MAKES,
        RULES,
    )
    cov = n.coverage(df, TARGETS)
    assert cov.select("country", "coverage").rows() == [("GB", 0.9), ("NL", 0.0)]
    report = n.unmapped_report(df, TARGETS, top=10)
    assert report.select("country", "model_raw", "count").rows() == [
        ("GB", "X5", 10),
        ("NL", "X5", 5),
    ]


def test_check_targets_have_rules() -> None:
    n.check_targets_have_rules(TARGETS, RULES)
    with pytest.raises(n.MappingError, match="no rule"):
        n.check_targets_have_rules(
            TARGETS
            + [
                n.TargetModel(
                    make="BMW",
                    model_gen="M1",
                    generation="E26",
                    segment="SUPERCAR",
                    year_from=1978,
                    year_to=1981,
                )
            ],
            RULES,
        )


# --------------------------------------------------------------------------- repo mapping files


def test_repo_mapping_files_are_valid_and_cover_targets() -> None:
    rules = n.load_models(MAPPING_DIR / n.MODELS_FILE)
    targets = n.load_targets(MAPPING_DIR / n.TARGETS_FILE)
    n.load_makes(MAPPING_DIR / n.MAKES_FILE)
    n.check_targets_have_rules(targets, rules)
    assert len(targets) >= 150


@pytest.mark.parametrize(
    ("make_raw", "model_raw", "year", "model_gen", "generation"),
    [
        ("BMW", "M3", 2003, "M3", "E46"),
        ("PEUGEOT", "205 GTI 1.9", 1990, "205 GTI", "MK1"),
        ("HONDA", "S2000", 2005, "S2000", "AP1_AP2"),
        ("RENAULT", "CLIO WILLIAMS", 1994, "CLIO WILLIAMS", "MK1"),
        ("AUDI", "RS2 AVANT", 1995, "RS2", "B4"),
        ("BMW", "M340I", 2020, "3 SERIES", None),
        ("BMW", "M3 CSL", None, "M3", "E46"),
        ("BMW", "M3", None, "M3", None),
        ("VOLKSWAGEN", "GOLF R-LINE", 2015, "GOLF", None),
        ("VW", "GOLF R", 2015, "GOLF R", "MK7"),
        ("VAUXHALL", "ASTRA VXR", 2008, "ASTRA OPC", "H"),
        ("MERCEDES", "SLK 200", 2008, "SLK", "R171"),
        ("MERCEDES-BENZ", "SL 500", 1995, "SL", "R129"),
        ("MERCEDES-BENZ", "C 63 AMG", 2010, "C63 AMG", "W204"),
        ("RENAULT", "CLIO RS 200", 2010, "CLIO RS", "MK3"),
        ("PEUGEOT", "206 GTI 180", 2004, "206 GTI", "MK1"),
        ("PORSCHE", "911 CARRERA", 2001, "911", "996"),
        ("PORSCHE", "CARRERA GT", 2005, "CARRERA GT", "980"),
        ("FORD", "PUMA", 1999, "PUMA", "MK1"),
        ("FORD", "FOCUS ST-3", 2008, "FOCUS ST", "MK2"),
        ("MAZDA", "MX-5", 2001, "MX-5", "NB"),
    ],
)
def test_repo_rules_on_witness_labels(
    make_raw: str, model_raw: str, year: int | None, model_gen: str, generation: str | None
) -> None:
    makes = n.load_makes(MAPPING_DIR / n.MAKES_FILE)
    rules = n.load_models(MAPPING_DIR / n.MODELS_FILE)
    out = n.apply(
        _stock([{"make_raw": make_raw, "model_raw": model_raw, "year_first_reg": year}]),
        makes,
        rules,
    )
    assert (out["model_gen"][0], out["generation"][0]) == (model_gen, generation)


# --------------------------------------------------------------------------- pipeline


def _ingest_fixtures(fixtures: Path, tmp_path: Path) -> Path:
    silver = tmp_path / "silver"
    snap = tmp_path / "raw" / "uk_dft" / "2026-09-08"
    snap.mkdir(parents=True)
    for t in dft.TABLES.values():
        (snap / t.filename).write_bytes((fixtures / t.filename).read_bytes())
        raw.register_file(snap, t.filename)
    dft.ingest(snap, silver)
    snap = tmp_path / "raw" / "nl_rdw" / "2026-09-08"
    snap.mkdir(parents=True)
    (snap / rdw.DATA_FILE).write_bytes((fixtures / "rdw_agg_page.json").read_bytes())
    (snap / rdw.QUERY_FILE).write_text("{}")
    raw.register_file(snap, rdw.DATA_FILE)
    raw.register_file(snap, rdw.QUERY_FILE)
    rdw.ingest(snap, silver)
    return silver


def test_normalize_end_to_end_with_repo_mapping(fixtures: Path, tmp_path: Path) -> None:
    silver = _ingest_fixtures(fixtures, tmp_path)
    written = n.normalize(silver, MAPPING_DIR, min_coverage=0.95)
    stock = pl.read_parquet(written["fleet_stock"])
    schemas.check_fleet_stock(stock)
    assert set(stock["country"].to_list()) == {"GB", "NL"}
    assert stock["model_gen"].null_count() == 0
    cov = pl.read_parquet(written["mapping_coverage"])
    assert cov.filter(pl.col("table") == "fleet_stock")["coverage"].min() == 1.0
    new_reg = pl.read_parquet(written["fleet_new_reg"])
    g80 = new_reg.filter(pl.col("model_raw") == "M3 G80")
    assert g80["model_gen"].unique().to_list() == ["M3"] and g80.height == 2


def test_normalize_fails_below_coverage(fixtures: Path, tmp_path: Path) -> None:
    silver = _ingest_fixtures(fixtures, tmp_path)
    mapping = tmp_path / "mapping"
    mapping.mkdir()
    (mapping / n.MAKES_FILE).write_text("alias,make\nBMW,BMW\n")
    (mapping / n.MODELS_FILE).write_text(
        "make,model_raw_regex,year_from,year_to,model_gen,generation\n"
        "BMW,^M3 CSL,,,M3,E46\nHONDA,^S2000,,,S2000,AP1_AP2\n"
    )
    (mapping / n.TARGETS_FILE).write_text(
        "make,model_gen,generation,segment,year_from,year_to\n"
        "BMW,M3,E46,SPORTIVE,2000,2006\nHONDA,S2000,AP1_AP2,ROADSTER,1999,2009\n"
    )
    with pytest.raises(n.CoverageError, match="below 95%"):
        n.normalize(silver, mapping, min_coverage=0.95)
    # exploration mode: same mapping, no gate
    n.normalize(silver, mapping, min_coverage=0.0)
