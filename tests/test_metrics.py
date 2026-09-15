import math
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from predcar import metrics, schemas
from predcar import score as sc
from predcar.config import load_score_config
from predcar.normalize import TargetModel

CFG = load_score_config()


def _target(model_gen: str, generation: str = "G1", segment: str = "SPORTIVE") -> TargetModel:
    return TargetModel(
        make="M",
        model_gen=model_gen,
        generation=generation,
        segment=segment,
        year_from=1998,
        year_to=2002,
    )


def _row(**kw) -> dict:
    base = {
        "country": "GB",
        "period": date(2020, 12, 31),
        "make_raw": "M",
        "model_gen_raw": None,
        "model_raw": "X",
        "make": "M",
        "model_gen": "A",
        "generation": None,
        "year_first_reg": None,
        "status": "licensed",
        "count": 100,
        "source": "uk_dft",
        "source_file": "df_VEH0124_AM.csv",
    }
    return {**base, **kw}


def _stock(rows: list[dict]) -> pl.DataFrame:
    return schemas.conform(pl.DataFrame(rows), schemas.FLEET_STOCK_SCHEMA)


def _new_reg(rows: list[dict]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schemas.FLEET_NEW_REG_SCHEMA)
    base = {
        "country": "GB",
        "make_raw": "M",
        "model_gen_raw": None,
        "model_raw": "X",
        "make": "M",
        "generation": None,
        "source": "uk_dft",
        "source_file": "df_VEH0160_GB.csv",
    }
    return schemas.conform(
        pl.DataFrame([{**base, **r} for r in rows]), schemas.FLEET_NEW_REG_SCHEMA
    )


def _gen_series(model_gen: str, start: int, rate: float, years=range(2014, 2024)) -> list[dict]:
    """VEH0124-style generation-level series decaying geometrically."""
    return [
        _row(
            model_gen=model_gen,
            generation="G1",
            year_first_reg=2000,
            period=date(y, 12, 31),
            count=int(round(start * (1 - rate) ** (y - 2014))),
        )
        for y in years
    ]


# --------------------------------------------------------------------------- helpers


def test_series_of() -> None:
    assert metrics.series_of("df_VEH0120_GB.csv") == "VEH0120"
    assert metrics.series_of("df_VEH0124_NZ.csv") == "VEH0124"
    assert metrics.series_of("gekentekende_voertuigen_agg.json") == "RDW"
    with pytest.raises(ValueError):
        metrics.series_of("mystery.csv")


def test_annual_stock_keeps_last_period_and_splits_sorn() -> None:
    df = _stock(
        [
            _row(source_file="df_VEH0120_GB.csv", period=date(2020, 6, 30), count=500),
            _row(source_file="df_VEH0120_GB.csv", period=date(2020, 12, 31), count=400),
            _row(
                source_file="df_VEH0120_GB.csv", period=date(2020, 12, 31), status="sorn", count=100
            ),
            _row(model_gen=None, source_file="df_VEH0120_GB.csv", count=999),  # unmapped → ignored
        ]
    )
    out = metrics.annual_stock(df)
    assert out.height == 1
    assert out.row(0, named=True) == {
        "country": "GB",
        "series": "VEH0120",
        "make": "M",
        "model_gen": "A",
        "generation": None,
        "year": 2020,
        "period": date(2020, 12, 31),
        "stock": 400,
        "sorn": 100,
    }


@pytest.mark.parametrize(
    ("stocks", "expected_last"),
    [
        ([1000, 500, 250, 125, 62], math.log(2)),  # halving every year, smoothed = ln 2
        ([100, 100, 100, 100], 0.0),
    ],
)
def test_attrition_math(stocks: list[int], expected_last: float) -> None:
    years = list(range(2010, 2010 + len(stocks)))
    out = metrics.attrition(years, stocks, smoothing_years=3)
    assert out[:3] == [None, None, None]  # first year + 2 warm-up years
    assert out[3] == pytest.approx(expected_last, rel=1e-2)


def test_attrition_handles_gaps_and_zero_stock() -> None:
    out = metrics.attrition([2010, 2012, 2013, 2014], [100, 81, 0, 10], smoothing_years=2)
    assert out[1] is None  # only one raw point so far
    assert out[2] is None and out[3] is None  # zero stock breaks the window


def test_select_series_prefers_generation_then_falls_back() -> None:
    annual = metrics.annual_stock(
        _stock(
            _gen_series("A", 1000, 0.1)
            + [
                _row(
                    model_gen="A",
                    source_file="df_VEH0120_GB.csv",
                    period=date(2023, 12, 31),
                    count=5000,
                )
            ]
            + [
                _row(
                    model_gen="B",
                    generation="G1",
                    source_file="df_VEH0120_GB.csv",
                    period=date(2023, 12, 31),
                    count=7,
                ),
                _row(
                    model_gen="B",
                    source_file="df_VEH0120_GB.csv",
                    period=date(2023, 12, 31),
                    count=70,
                ),
            ]
        )
    )
    a = metrics.select_series(annual, _target("A"), "GB")
    assert (
        a is not None and a.level == "generation" and a.series == "VEH0124" and len(a.years) == 10
    )
    b = metrics.select_series(annual, _target("B"), "GB")
    assert b is not None and b.level == "model_gen" and b.stock == [77]  # summed over generations
    assert metrics.select_series(annual, _target("Z"), "GB") is None
    # model-level fallback refused when the model_gen has several target generations
    assert metrics.select_series(annual, _target("B"), "GB", sole_generation=False) is None


def test_multi_generation_model_without_generation_data_gets_no_series() -> None:
    stock = _stock(
        [
            _row(
                model_gen="M",
                source_file="df_VEH0120_GB.csv",
                period=date(y, 12, 31),
                count=1000 - y,
            )
            for y in range(2014, 2024)
        ]
    )
    targets = [_target("M", "G1"), _target("M", "G2")]
    ind, _ = metrics.compute_indicators(stock, _new_reg([]), targets, CFG)
    assert ind.height == 0


def test_sorn_ratio_and_cumulative_sales_and_tier() -> None:
    annual = metrics.annual_stock(
        _stock(
            [
                _row(source_file="df_VEH0120_GB.csv", count=300),
                _row(source_file="df_VEH0120_GB.csv", status="sorn", count=100),
                _row(
                    source_file="df_VEH0120_GB.csv", generation="G1", count=100
                ),  # label-only gen row
            ]
        )
    )
    assert metrics.sorn_ratio(annual, _target("A"), "GB") == pytest.approx(0.2)
    assert metrics.sorn_ratio(annual, _target("A"), "NL") is None
    nr = metrics.annual_new_reg(
        _new_reg(
            [
                {"model_gen": "A", "period": date(1997, 12, 31), "count": 50},  # before generation
                {"model_gen": "A", "period": date(2000, 3, 31), "count": 30},
                {"model_gen": "A", "period": date(2001, 3, 31), "count": 20},
            ]
        )
    )
    assert metrics.cumulative_sales(nr, _target("A"), "GB") == 50
    assert metrics.cumulative_sales(nr, _target("A"), "NL") is None
    assert metrics.rarity_tier(19, [500, 100, 20]) == "<20"
    assert metrics.rarity_tier(99, [500, 100, 20]) == "<100"
    assert metrics.rarity_tier(500, [500, 100, 20]) == ">=500"


# --------------------------------------------------------------------------- indicators


def _population() -> tuple[pl.DataFrame, pl.DataFrame, list[TargetModel]]:
    """A slow-decaying model among three fast-decaying peers, plus a lonely COUPE."""
    rows = (
        _gen_series("SLOW", 2000, 0.03)
        + _gen_series("FAST1", 2000, 0.20)
        + _gen_series("FAST2", 3000, 0.20)
        + _gen_series("FAST3", 4000, 0.20)
        + _gen_series("LONELY", 500, 0.10)
        # VEH0120 model-level rows with SORN for SLOW only
        + [
            _row(
                model_gen="SLOW",
                source_file="df_VEH0120_GB.csv",
                period=date(2023, 12, 31),
                count=800,
            ),
            _row(
                model_gen="SLOW",
                source_file="df_VEH0120_GB.csv",
                period=date(2023, 12, 31),
                status="sorn",
                count=200,
            ),
        ]
        # NL snapshot for SLOW
        + [
            _row(
                country="NL",
                model_gen="SLOW",
                generation="G1",
                year_first_reg=2000,
                status=None,
                source="nl_rdw",
                source_file="gekentekende_voertuigen_agg.json",
                period=date(2026, 9, 8),
                count=150,
            )
        ]
    )
    targets = [_target(m) for m in ("SLOW", "FAST1", "FAST2", "FAST3")] + [
        _target("LONELY", segment="COUPE")
    ]
    new_reg = _new_reg([{"model_gen": "SLOW", "period": date(2001, 12, 31), "count": 5000}])
    return _stock(rows), new_reg, targets


def test_compute_indicators_relative_attrition_and_inflection() -> None:
    stock, new_reg, targets = _population()
    ind, series = metrics.compute_indicators(stock, new_reg, targets, CFG)
    slow = ind.filter((pl.col("model_gen") == "SLOW") & (pl.col("country") == "GB")).row(
        0, named=True
    )
    assert slow["level"] == "generation" and slow["history_years"] == 7
    assert slow["attrition"] == pytest.approx(-math.log(0.97), rel=1e-2)
    assert slow["relative_attrition"] < 0  # disappears slower than peers
    assert slow["inflection_year"] == 2017  # first smoothed year, below ever since
    assert slow["sorn_ratio"] == pytest.approx(0.2)
    assert slow["cumulative_sales"] == 5000 and slow["survival"] == pytest.approx(
        slow["stock"] / 5000
    )
    fast = ind.filter((pl.col("model_gen") == "FAST1") & (pl.col("country") == "GB")).row(
        0, named=True
    )
    assert fast["relative_attrition"] > 0 and fast["inflection_year"] is None
    lonely = ind.filter(pl.col("model_gen") == "LONELY").row(0, named=True)
    assert lonely["relative_attrition"] is None and lonely["n_peers"] < CFG.peers.min_peers
    nl = ind.filter(pl.col("country") == "NL").row(0, named=True)
    assert nl["stock"] == 150 and nl["attrition"] is None and nl["sorn_ratio"] is None
    assert series.filter(pl.col("model_gen") == "SLOW").height == 11  # 10 GB years + 1 NL


def test_aggregate_europe_sums_stock_and_keeps_gb_sorn() -> None:
    stock, new_reg, targets = _population()
    ind, _ = metrics.compute_indicators(stock, new_reg, targets, CFG)
    eu = metrics.aggregate_europe(ind, CFG.rarity.thresholds)
    slow = eu.filter(pl.col("model_gen") == "SLOW").row(0, named=True)
    gb = ind.filter((pl.col("model_gen") == "SLOW") & (pl.col("country") == "GB")).row(
        0, named=True
    )
    assert slow["country"] == "EU" and slow["stock"] == gb["stock"] + 150
    assert slow["sorn_ratio"] == pytest.approx(0.2)
    assert slow["relative_attrition"] == pytest.approx(gb["relative_attrition"])  # NL has none
    assert eu.height == 5
    lonely = eu.filter(pl.col("model_gen") == "LONELY").row(0, named=True)
    assert lonely["relative_attrition"] is None  # null, never NaN


# --------------------------------------------------------------------------- score


def test_normalize_and_composite() -> None:
    stock, new_reg, targets = _population()
    ind, _ = metrics.compute_indicators(stock, new_reg, targets, CFG)
    scores = sc.composite(
        sc.normalize_components(metrics.aggregate_europe(ind, CFG.rarity.thresholds), CFG), CFG
    )
    by = {r["model_gen"]: r for r in scores.iter_rows(named=True)}

    assert by["SLOW"]["conservation"] == 1.0 and by["SLOW"]["recent_inflection_point"] == 0.0
    assert by["FAST1"]["recent_inflection_point"] == 0.0 and by["FAST1"]["conservation"] < 1.0
    assert min(r["rarity"] for r in by.values()) == pytest.approx(0.0)
    assert max(r["rarity"] for r in by.values()) == pytest.approx(1.0)
    assert by["SLOW"]["weight_coverage"] == pytest.approx(1.0)
    assert by["FAST1"]["weight_coverage"] == pytest.approx(0.8)  # no SORN rows
    assert by["FAST1"]["components_available"] == [
        "rarity",
        "conservation",
        "recent_inflection_point",
    ]
    # LONELY: no peers → conservation and inflection missing → 0.35 < 0.60 → not published
    assert by["LONELY"]["weight_coverage"] == pytest.approx(0.35) and by["LONELY"]["score"] is None
    assert by["LONELY"]["rank"] is None
    published = [r for r in by.values() if r["score"] is not None]
    assert all(0 <= r["score"] <= 1 for r in published)
    assert sorted(r["rank"] for r in published) == [1, 2, 3, 4]
    # renormalization: FAST1 score = weighted mean over its three components
    f = by["FAST1"]
    w = CFG.weights
    expected = (
        w.rarity * f["rarity"]
        + w.conservation * f["conservation"]
        + w.recent_inflection_point * f["recent_inflection_point"]
    ) / 0.8
    assert f["score"] == pytest.approx(expected)


def test_score_pipeline_writes_gold(tmp_path: Path) -> None:
    stock, new_reg, targets = _population()
    silver, gold, mapping = tmp_path / "silver", tmp_path / "gold", tmp_path / "mapping"
    silver.mkdir()
    mapping.mkdir()
    stock.write_parquet(silver / "fleet_stock.parquet")
    new_reg.write_parquet(silver / "fleet_new_reg.parquet")
    (mapping / "target_models.csv").write_text(
        "make,model_gen,generation,segment,year_from,year_to\n"
        + "".join(
            f"{t.make},{t.model_gen},{t.generation},{t.segment},{t.year_from},{t.year_to}\n"
            for t in targets
        )
    )
    written = sc.score(silver, gold, mapping, CFG)
    assert set(written) == {
        "series",
        "reference",
        "projection",
        "indicators",
        "scores",
        "cohorts",
        "ranking",
    }
    ranking = pl.read_csv(written["ranking"])
    assert ranking.columns[:6] == ["rank", "make", "model_gen", "generation", "segment", "score"]
    top = ranking.filter(pl.col("rank") == 1)
    assert top["score"][0] == ranking["score"].max()
    indicators = pl.read_parquet(written["indicators"])
    assert set(indicators["country"].to_list()) == {"GB", "NL", "EU"}


def test_score_requires_normalized_input(tmp_path: Path) -> None:
    with pytest.raises(sc.ScoreError, match="normalize"):
        sc.score(tmp_path, tmp_path / "gold", tmp_path, CFG)


# --------------------------------------------------------------------------- review fixes


def test_two_makes_sharing_a_model_gen_are_never_merged() -> None:
    rows = [
        _row(
            make_raw="ALFA",
            make="ALFA ROMEO",
            model_gen="SPIDER",
            source_file="df_VEH0120_GB.csv",
            count=900,
        ),
        _row(
            make_raw="ALFA",
            make="ALFA ROMEO",
            model_gen="SPIDER",
            source_file="df_VEH0120_GB.csv",
            status="sorn",
            count=100,
        ),
        _row(
            make_raw="RENAULT",
            make="RENAULT",
            model_gen="SPIDER",
            source_file="df_VEH0120_GB.csv",
            count=50,
        ),
        _row(
            make_raw="RENAULT",
            make="RENAULT",
            model_gen="SPIDER",
            source_file="df_VEH0120_GB.csv",
            status="sorn",
            count=50,
        ),
    ]
    alfa = TargetModel(
        make="ALFA ROMEO",
        model_gen="SPIDER",
        generation="916",
        segment="ROADSTER",
        year_from=1995,
        year_to=2005,
    )
    renault = TargetModel(
        make="RENAULT",
        model_gen="SPIDER",
        generation="SPIDER",
        segment="ROADSTER",
        year_from=1996,
        year_to=1999,
    )
    new_reg = _new_reg(
        [
            {
                "make": "ALFA ROMEO",
                "model_gen": "SPIDER",
                "period": date(2001, 12, 31),
                "count": 1000,
            },
            {"make": "RENAULT", "model_gen": "SPIDER", "period": date(1998, 12, 31), "count": 10},
        ]
    )
    ind, _ = metrics.compute_indicators(_stock(rows), new_reg, [alfa, renault], CFG)
    by = {r["make"]: r for r in ind.iter_rows(named=True)}
    assert by["ALFA ROMEO"]["stock"] == 900 and by["ALFA ROMEO"]["sorn_ratio"] == pytest.approx(0.1)
    assert by["RENAULT"]["stock"] == 50 and by["RENAULT"]["sorn_ratio"] == pytest.approx(0.5)
    assert by["ALFA ROMEO"]["cumulative_sales"] == 1000 and by["RENAULT"]["cumulative_sales"] == 10


def test_europe_keeps_unavailable_sales_null() -> None:
    stock = _stock(_gen_series("A", 1000, 0.1))
    ind, _ = metrics.compute_indicators(stock, _new_reg([]), [_target("A")], CFG)
    assert ind["cumulative_sales"][0] is None
    eu = metrics.aggregate_europe(ind, CFG.rarity.thresholds)
    assert eu["cumulative_sales"][0] is None  # not 0


def test_inflection_run_resets_across_a_missing_year() -> None:
    """SLOW's series has no 2019 row: the run below the peer median restarts in 2020+."""
    rows = [r for r in _gen_series("SLOW", 2000, 0.03) if r["period"].year != 2019]
    rows += (
        _gen_series("FAST1", 2000, 0.2)
        + _gen_series("FAST2", 3000, 0.2)
        + _gen_series("FAST3", 4000, 0.2)
    )
    targets = [_target(m) for m in ("SLOW", "FAST1", "FAST2", "FAST3")]
    ind, _ = metrics.compute_indicators(_stock(rows), _new_reg([]), targets, CFG)
    slow = ind.filter(pl.col("model_gen") == "SLOW").row(0, named=True)
    assert slow["inflection_year"] is not None and slow["inflection_year"] >= 2020


def test_ranking_export_excludes_unpublished_rows(tmp_path: Path) -> None:
    stock, new_reg, targets = _population()
    silver, gold, mapping = tmp_path / "silver", tmp_path / "gold", tmp_path / "mapping"
    silver.mkdir()
    mapping.mkdir()
    stock.write_parquet(silver / "fleet_stock.parquet")
    new_reg.write_parquet(silver / "fleet_new_reg.parquet")
    (mapping / "target_models.csv").write_text(
        "make,model_gen,generation,segment,year_from,year_to\n"
        + "".join(
            f"{t.make},{t.model_gen},{t.generation},{t.segment},{t.year_from},{t.year_to}\n"
            for t in targets
        )
    )
    written = sc.score(silver, gold, mapping, CFG)
    ranking = pl.read_csv(written["ranking"])
    scores = pl.read_parquet(written["scores"])
    assert ranking.height == scores.filter(pl.col("score").is_not_null()).height
    assert "LONELY" not in ranking["model_gen"].to_list()
    assert "make" in ranking.columns


# --------------------------------------------------------------------------- real-data fixes


def test_attrition_uses_real_time_between_observations() -> None:
    """A Q1 point after a Q4 point is a quarter, not a year: the same loss over 3 months is
    an annual rate four times higher, and a 2-year gap halves it."""
    periods = [date(2020, 12, 31), date(2021, 12, 31), date(2022, 3, 31)]
    out = metrics.attrition(periods, [1000, 900, 810], smoothing_years=1)
    assert out[1] == pytest.approx(-math.log(0.9), rel=1e-3)
    assert out[2] == pytest.approx(-math.log(0.9) / (90 / 365.25), rel=1e-3)
    assert metrics.attrition([2020, 2022], [1000, 810], 1)[1] == pytest.approx(-math.log(0.81) / 2)


def test_sorn_ratio_prefers_generation_level() -> None:
    annual = metrics.annual_stock(
        _stock(
            [
                # VEH0124: generation G1 of model A, with SORN
                _row(generation="G1", count=90),
                _row(generation="G1", status="sorn", count=10),
                # VEH0120: whole model A (all generations), much more SORN
                _row(source_file="df_VEH0120_GB.csv", count=500),
                _row(source_file="df_VEH0120_GB.csv", status="sorn", count=500),
            ]
        )
    )
    assert metrics.sorn_ratio(annual, _target("A", "G1"), "GB") == pytest.approx(0.1)
    assert metrics.sorn_ratio(annual, _target("A", "G2"), "GB") == pytest.approx(0.5)  # fallback


def test_cohort_retention_is_relative_to_the_cohort_peak() -> None:
    t = _target("A")
    rows = []
    for year, n in [(2018, 100), (2019, 90), (2020, 81)]:
        rows.append(
            _row(
                period=date(year, 12, 31),
                generation="G1",
                year_first_reg=2005,
                count=n,
                status="licensed",
            )
        )
        rows.append(
            _row(
                period=date(year, 12, 31),
                generation="G1",
                year_first_reg=2005,
                count=5,
                status="sorn",
            )
        )
    # a second cohort observed once, and a model_gen-level row without a cohort (ignored)
    rows.append(_row(period=date(2020, 12, 31), generation="G1", year_first_reg=2006, count=40))
    rows.append(_row(period=date(2020, 12, 31), generation=None, source_file="df_VEH0120_GB.csv"))
    out = metrics.cohort_retention(_stock(rows), [t])
    c2005 = out.filter(pl.col("cohort") == 2005).sort("year")
    assert c2005["stock"].to_list() == [100, 90, 81]  # SORN excluded
    assert c2005["retention"].to_list() == pytest.approx([1.0, 0.9, 0.81])
    assert out.filter(pl.col("cohort") == 2006)["retention"].to_list() == [1.0]
    assert out.filter(pl.col("cohort").is_null()).height == 0
    assert metrics.cohort_retention(_stock(rows), []).height == 0


def test_reference_stock_covers_models_not_generations() -> None:
    """A series with no first-registration year informs, it does not score.

    Germany publishes its fleet by trade name only. Splitting it between generations is
    impossible, so the figure is published per model with the number of target generations it
    covers — never fed to rarity, which compares targets to one another.
    """
    targets = [_target("M3", "E36"), _target("M3", "E46"), _target("RS2", "B4")]
    stock = _stock(
        [
            _row(country="DE", period=date(2025, 1, 1), model_gen="M3", source_file="fz2.xlsx"),
            _row(
                country="DE",
                period=date(2026, 1, 1),
                model_gen="M3",
                source_file="fz2.xlsx",
                count=90,
            ),
            _row(
                country="DE",
                period=date(2026, 1, 1),
                model_gen="RS2",
                source_file="fz2.xlsx",
                count=7,
            ),
            # a scored series must never appear here
            _row(country="GB", model_gen="M3", generation="E46", count=500),
        ]
    )
    out = metrics.reference_stock(stock, targets)
    assert out["series"].unique().to_list() == ["FZ2"]
    assert out["country"].unique().to_list() == ["DE"]
    # the whole series is published, not just its last point
    m3 = out.filter(pl.col("model_gen") == "M3").sort("year")
    assert m3["year"].to_list() == [2025, 2026]
    assert m3["stock"].to_list() == [100, 90]
    assert m3["target_generations"].unique().to_list() == [2]
    rs2 = out.filter(pl.col("model_gen") == "RS2")
    assert rs2["target_generations"].to_list() == [1]


def test_reference_stock_is_empty_without_such_a_series() -> None:
    assert metrics.reference_stock(_stock([_row()]), [_target("A")]).height == 0


def test_reference_series_is_not_scored() -> None:
    """The guard that keeps Germany out of the score: FZ2 in neither series list."""
    for series in metrics.REFERENCE_SERIES:
        assert series not in metrics.GEN_LEVEL_SERIES
        assert series not in metrics.MODEL_LEVEL_SERIES


# --------------------------------------------------------------------------- weibull


def _weibull_points(k: float, lam: float, ages: list[int]) -> list[float]:
    return [math.exp(-((a / lam) ** k)) for a in ages]


def test_fit_weibull_recovers_the_parameters_of_a_clean_curve() -> None:
    """Linearised least squares on exact Weibull points must return k and λ."""
    ages = list(range(1, 13))
    k, lam, s = metrics.fit_weibull(ages, _weibull_points(1.5, 20.0, ages))
    assert k == pytest.approx(1.5, rel=1e-6)
    assert lam == pytest.approx(20.0, rel=1e-6)
    assert s == pytest.approx(0.0, abs=1e-9)


def test_fit_weibull_skips_undefined_points_and_needs_two() -> None:
    assert metrics.fit_weibull([1, 2, 3], [1.0, 1.0, 0.0]) is None  # nothing in (0, 1)
    assert metrics.fit_weibull([1, 2], [1.0, 0.5]) is None  # a single usable point
    assert metrics.fit_weibull([1, 2, 3], [0.5, 0.6, 0.7]) is None  # rising: k <= 0


def _cohort_frame(rows: list[dict]) -> pl.DataFrame:
    base = {"make": "M", "model_gen": "A", "generation": "G1", "country": "GB", "series": "VEH0124"}
    return pl.DataFrame([{**base, **r} for r in rows]).cast(metrics.COHORTS_SCHEMA)


def _cfg(**kw) -> "metrics.WeibullConfig":
    from predcar.config import WeibullConfig

    return WeibullConfig(**{"horizons": [5, 10], "min_points": 5, "min_cohorts": 1, **kw})


def _cohort_rows(cohort: int, years: list[int], k: float, lam: float, peak: int) -> list[dict]:
    ages = [y - cohort for y in years]
    rets = _weibull_points(k, lam, ages)
    return [
        {"cohort": cohort, "year": y, "stock": round(peak * r), "retention": r}
        for y, r in zip(years, rets, strict=True)
    ]


def test_projection_scales_current_stock_by_the_fitted_survival_ratio() -> None:
    """One clean cohort: the projection is stock × R(age+h)/R(age), checked by hand."""
    k, lam, peak = 1.5, 20.0, 1000
    years = list(range(2015, 2027))  # cohort 2014, ages 1..12
    cohorts = _cohort_frame(_cohort_rows(2014, years, k, lam, peak))
    out = metrics.weibull_projection(cohorts, [_target("A")], _cfg())
    assert out["horizon"].to_list() == [5, 10]
    age = 12
    stock_now = round(peak * math.exp(-((age / lam) ** k)))
    for row in out.iter_rows(named=True):
        expected = (
            stock_now
            * math.exp(-(((age + row["horizon"]) / lam) ** k))
            / math.exp(-((age / lam) ** k))
        )
        assert row["stock_now"] == stock_now
        assert row["stock_projected"] == round(expected)
        assert row["low"] <= row["stock_projected"] <= row["high"]
        assert row["year"] == 2026 + row["horizon"]
        assert row["k_median"] == pytest.approx(k, rel=1e-6)
        assert row["lambda_median"] == pytest.approx(lam, rel=1e-6)
        assert (row["cohorts_fitted"], row["cohorts_total"]) == (1, 1)


def test_projection_excludes_short_and_rising_cohorts_but_counts_them() -> None:
    good = _cohort_rows(2014, list(range(2015, 2027)), 1.5, 20.0, 1000)
    short = _cohort_rows(2020, list(range(2021, 2025)), 1.5, 20.0, 500)  # 4 points
    rising = [
        {"cohort": 2010, "year": y, "stock": s, "retention": r}
        for y, s, r in [
            (2018, 80, 0.8),
            (2019, 70, 0.7),
            (2020, 60, 0.6),
            (2021, 90, 0.9),
            (2022, 100, 1.0),
            (2023, 95, 0.95),
        ]
    ]
    out = metrics.weibull_projection(_cohort_frame(good + short + rising), [_target("A")], _cfg())
    assert out.height == 2
    assert out["cohorts_fitted"].unique().to_list() == [1]
    assert out["cohorts_total"].unique().to_list() == [3]


def test_projection_requires_min_cohorts() -> None:
    cohorts = _cohort_frame(_cohort_rows(2014, list(range(2015, 2027)), 1.5, 20.0, 1000))
    assert metrics.weibull_projection(cohorts, [_target("A")], _cfg(min_cohorts=2)).height == 0
    assert metrics.weibull_projection(cohorts, [_target("B")], _cfg()).height == 0  # not a target


def test_projection_is_not_a_score_input() -> None:
    """The guard: nothing in score.py reads projection columns."""
    import inspect

    from predcar import score as sc

    src = inspect.getsource(sc)
    assert "projection" in src  # it is written…
    assert "stock_projected" not in src and "k_median" not in src  # …never read


def test_fit_weibull_recovers_parameters_when_observed_from_age_ten() -> None:
    """The registers start in 2014: a 2004 cohort is first seen at age 10, already depleted.

    Retention is then survival *relative to that first observation*. An unconditional fit
    forces R = 1 at age 10 and returns k ≈ 4 for every model — the bug this test exists for.
    The conditional model must recover the true k and λ from the partial window.
    """
    k, lam = 1.5, 20.0
    ages = list(range(10, 22))
    true = _weibull_points(k, lam, ages)
    observed = [r / true[0] for r in true]  # normalised at the first observation
    fk, flam, s = metrics.fit_weibull(ages, observed)
    assert fk == pytest.approx(k, abs=0.03)  # grid step is 0.05
    assert flam == pytest.approx(lam, rel=0.03)
    assert s < 0.05


def test_fit_weibull_uses_the_first_point_as_the_conditioning_age() -> None:
    """A rising first point is not a peak; the fit conditions on it, it does not skip it."""
    assert metrics.fit_weibull([], []) is None
    assert metrics.fit_weibull([0, 1, 2], [1.0, 0.9, 0.8]) is None  # age 0 undefined


def test_fit_weibull_refuses_degenerate_fits() -> None:
    """A flat series drives λ to zero on the grid edge: nothing, rather than a number."""
    ages = list(range(10, 22))
    flat = [1.0, 0.999, 0.998, 0.997, 0.996, 0.995, 0.994, 0.993, 0.992, 0.991, 0.990, 0.989]
    fit = metrics.fit_weibull(ages, flat)
    assert fit is None or (metrics._LAMBDA_YEARS[0] <= fit[1] <= metrics._LAMBDA_YEARS[1])


def test_settled_allows_a_young_cohort_to_fill_up_but_not_a_later_import() -> None:
    ages, rets = metrics._settled([1, 2, 3, 4], [0.7, 1.0, 0.9, 0.8])  # type: ignore[misc]
    assert ages == [2, 3, 4] and rets == [1.0, 0.9, 0.8]
    assert metrics._settled([10, 11, 12, 13], [1.0, 0.8, 0.9, 0.7]) is None  # rise after year 2
    assert metrics._settled([10, 11, 12], [1.0, 0.8, 0.82]) is not None  # within tolerance


def test_europe_row_carries_a_rarity_tier() -> None:
    """The EU line is what the ranking publishes; its tier must come from the EU stock."""
    cfg = load_score_config()
    stock, new_reg, targets = _population()
    indicators, _ = metrics.compute_indicators(stock, new_reg, targets, cfg)
    eu = metrics.aggregate_europe(indicators, cfg.rarity.thresholds)
    assert eu["rarity_tier"].null_count() == 0
    row = eu.row(0, named=True)
    assert row["rarity_tier"] == metrics.rarity_tier(int(row["stock"]), cfg.rarity.thresholds)
