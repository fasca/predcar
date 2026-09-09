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


def test_apply_strips_leading_make_label_before_matching() -> None:
    """RDW labels carry the make (``HONDA S2000``, ``ALFA GIULIETTA``); DfT labels do not."""
    df = _stock(
        [
            {"make_raw": "HONDA", "model_raw": "HONDA S2000"},
            {"make_raw": "BAYERISCHE MOTOREN WERKE", "model_raw": "BMW M3 CSL"},
            {"make_raw": "BMW", "model_raw": "BMW"},  # nothing left: label kept, no match
        ]
    )
    out = n.apply(df, MAKES, RULES)
    assert out["model_gen"].to_list() == ["S2000", "M3", None]
    assert out["model_raw"].to_list() == ["HONDA S2000", "BMW M3 CSL", "BMW"]  # raw untouched


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


def test_every_target_label_resolves_to_itself_without_conflict() -> None:
    """A target's own name (e.g. ``POLO GTI``, ``NSX``) must not also hit a catch-all rule.

    Labels that no rule matches are skipped (the name is not a real source label); labels
    that match must resolve to the target's model_gen, and never raise MappingError.
    """
    makes = n.load_makes(MAPPING_DIR / n.MAKES_FILE)
    rules = n.load_models(MAPPING_DIR / n.MODELS_FILE)
    targets = n.load_targets(MAPPING_DIR / n.TARGETS_FILE)
    rows = [
        {
            "make_raw": t.make,
            "model_raw": t.model_gen.replace("_", " "),
            "year_first_reg": (t.year_from + t.year_to) // 2,
            "count": i,
        }
        for i, t in enumerate(targets)
    ]
    out = n.apply(_stock(rows), makes, rules)  # raises MappingError on any conflict
    resolved = out.filter(pl.col("model_gen").is_not_null())
    wrong = [
        (t.make, t.model_gen, got)
        for t, got in zip(targets, out["model_gen"].to_list(), strict=True)
        if got is not None and got != t.model_gen
    ]
    assert not wrong, wrong
    assert resolved.height >= 0.8 * len(targets)


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
        ("HONDA", "NSX", 1995, "NSX", "NA1_NA2"),
        ("VOLKSWAGEN", "POLO GTI", 2007, "POLO GTI", "9N"),
        ("VOLKSWAGEN", "SCIROCCO", 2010, "SCIROCCO", "MK3"),
        ("MERCEDES-BENZ", "S 500", 2000, "S-CLASS", "W220"),
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
    # nothing published on failure: no partial or stale output set
    assert not list(silver.glob("fleet_stock.parquet"))
    assert not list(silver.glob("fleet_new_reg.parquet"))
    assert not list(silver.glob("mapping_coverage.parquet"))
    # exploration mode: same mapping, no gate
    written = n.normalize(silver, mapping, min_coverage=0.0)
    assert set(written) == {"fleet_stock", "fleet_new_reg", "mapping_coverage"}


# --------------------------------------------------------------------------- real-data fixes


@pytest.mark.parametrize(
    ("make_raw", "model_raw", "year", "model_gen", "generation"),
    [
        ("FORD", "FIESTA ST-LINE TURBO", 2019, "FIESTA", None),  # ST-LINE is a trim, not an ST
        ("FORD", "FIESTA ST-3 TURBO", 2015, "FIESTA ST", "MK7"),
        ("FORD", "FOCUS ST170", 2003, "FOCUS ST", "MK1"),
        ("FORD", "FOCUS STYLE 100", 2009, "FOCUS", None),
        ("FORD", "PUMA", 2010, "PUMA", None),  # year outside every generation → model only
        ("HONDA", "CIVIC TYPE-R", 2003, "CIVIC TYPE R", "EP3"),  # DfT writes the hyphen
        ("HONDA", "CIVIC TYPE-S GT", 2008, "CIVIC", None),
        ("RENAULT", "CLIO DYNAMIQUE 16V", 2004, "CLIO", None),  # 16V engine trim, not the MK1
        ("RENAULT", "CLIO 16V", 1993, "CLIO 16V", "MK1"),
        ("CITROEN", "SAXO VTR", 1999, "SAXO", None),
        ("CITROEN", "SAXO VTS", 1999, "SAXO VTS", "S0"),
        ("PEUGEOT", "306 XSI", 1995, "306", None),
        ("FIAT", "PUNTO HGT 16V", 2001, "PUNTO HGT", None),
        ("MITSUBISHI", "LANCER EVO VI", 2005, "LANCER EVOLUTION", "V_VI"),  # label beats year
        ("MITSUBISHI", "LANCER EVO I.V.", None, "LANCER EVOLUTION", "I_IV"),
        ("MITSUBISHI", "LANCER EVOLUTION GSR", 2005, "LANCER EVOLUTION", "VII_IX"),
        ("VAUXHALL", "CORSA GSI 16V", 2001, "CORSA GSI", None),
        ("SAAB", "09-MAR", 2005, "9-3", None),  # Excel-mangled "9-3" in the DfT file
        ("MERCEDES", "300 SL AUTO", 1986, "SL", "R107"),
        ("MERCEDES", "190 SL", None, "SL", None),
    ],
)
def test_repo_rules_on_real_labels_from_first_export(
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


def test_generation_uses_build_year_before_first_registration_year() -> None:
    """A 1999 Skyline imported and first registered in GB in 2010 stays an R34."""
    rules = [
        n.ModelRule(
            make="NISSAN",
            model_raw_regex=r"^SKYLINE",
            year_from=1999,
            year_to=2002,
            model_gen="SKYLINE GT-R",
            generation="R34",
        ),
        n.ModelRule(
            make="NISSAN",
            model_raw_regex=r"^SKYLINE",
            year_from=2007,
            year_to=2022,
            model_gen="SKYLINE GT-R",
            generation="R35",
        ),
    ]
    df = _stock([{"make_raw": "NISSAN", "model_raw": "SKYLINE GT-R", "year_first_reg": 2010}])
    assert n.apply(df, {}, rules)["generation"][0] == "R35"  # no build year → registration
    df = df.with_columns(pl.lit(1999, dtype=pl.Int32).alias("year_manufacture"))
    assert n.apply(df, {}, rules)["generation"][0] == "R34"


def test_coverage_excludes_source_unknown_labels() -> None:
    df = n.apply(
        _stock(
            [
                {"model_raw": "M3", "year_first_reg": 2003, "count": 90},
                {"model_raw": "MODEL MISSING", "count": 900},  # source says unknown: never mappable
                {"model_raw": "X5", "count": 10},
            ]
        ),
        MAKES,
        RULES,
    )
    cov = n.coverage(df, TARGETS, ("MODEL MISSING",))
    assert cov.select("total", "mapped", "unknown", "coverage").rows() == [(100, 90, 900, 0.9)]
    assert n.coverage(df, TARGETS)["coverage"][0] == pytest.approx(0.09)
    report = n.unmapped_report(df, TARGETS, 10, ("MODEL MISSING",))
    assert report["model_raw"].to_list() == ["X5"]
