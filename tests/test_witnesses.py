"""Snapshot tests on the five control models of SPEC §8.

Two independent layers:

* mapping — the real labels of the evidence bundle are replayed through the *current* rules
  and must resolve to the witness (and the trim labels must not);
* gold — the bundle's indicators and scores must stay within wide bounds and satisfy the
  structural invariants (EU = GB + NL, generation-level series, four score components).

Neither layer needs the network or a ``data/`` directory: ``reports/<date>/`` is committed.
"""

from __future__ import annotations

import polars as pl
import pytest
from conftest import stock_frame
from witnesses import WITNESSES, Witness, witness_id

from predcar import normalize as n
from predcar import score as sc
from predcar.paths import MAPPING_DIR

pytestmark = pytest.mark.parametrize("w", WITNESSES, ids=witness_id)


@pytest.fixture(scope="module")
def rules() -> tuple[dict[str, str], list[n.ModelRule]]:
    return (
        n.load_makes(MAPPING_DIR / "makes.csv"),
        n.load_models(MAPPING_DIR / "models.csv"),
    )


def _resolve(w: Witness, labels: tuple[str, ...], rules, year: int | None) -> pl.DataFrame:
    makes, model_rules = rules
    rows = [{"make_raw": w.make, "model_raw": label, "year_first_reg": year} for label in labels]
    return n.apply(stock_frame(rows), makes, model_rules)


# --------------------------------------------------------------------------- mapping layer


def test_witness_is_a_declared_target(w: Witness) -> None:
    targets = {
        (t.make, t.model_gen, t.generation): t
        for t in n.load_targets(MAPPING_DIR / "target_models.csv")
    }
    target = targets.get((w.make, w.model_gen, w.generation))
    assert target is not None, f"{witness_id(w)} is not in mapping/target_models.csv"
    assert target.segment == w.segment
    assert target.year_from <= w.build_year <= target.year_to


def test_witness_sample_labels_resolve(w: Witness, rules) -> None:
    out = _resolve(w, w.sample_labels, rules, w.build_year)
    assert out["model_gen"].to_list() == [w.model_gen] * len(w.sample_labels)
    assert out["generation"].to_list() == [w.generation] * len(w.sample_labels)


def test_witness_forbidden_labels_do_not_resolve(w: Witness, rules) -> None:
    out = _resolve(w, w.forbidden_labels, rules, w.build_year)
    assert all(mg != w.model_gen for mg in out["model_gen"].to_list())


def test_every_real_label_of_the_witness_is_expected(
    w: Witness, real_labels_mapped: pl.DataFrame
) -> None:
    """Nothing unexpected in the bundle resolves to the witness."""
    got = real_labels_mapped.filter(
        (pl.col("make") == w.make) & (pl.col("model_gen") == w.model_gen)
    )
    assert got.height > 0, f"no real label maps to {w.make} {w.model_gen}"
    for label in got["model_raw"].to_list():
        assert label not in w.forbidden_labels


def test_generation_uses_build_year(w: Witness, rules) -> None:
    """An import registered long after it was built keeps its build-year generation.

    The contrast is asserted too: without the build year, a year-ranged witness (BMW M3)
    lands in another generation, while a label-discriminant one is unaffected.
    """
    makes, model_rules = rules
    label = w.sample_labels[0]
    base = {"make_raw": w.make, "model_raw": label, "year_first_reg": 2018}

    with_build = stock_frame([base]).with_columns(
        pl.lit(w.build_year, dtype=pl.Int32).alias("year_manufacture")
    )
    assert n.apply(with_build, makes, model_rules)["generation"].to_list() == [w.generation]

    without_build = n.apply(stock_frame([base]), makes, model_rules)
    assert without_build["generation"].to_list() == [w.generation_without_build_year]


# --------------------------------------------------------------------------- gold layer


def _gold_rows(w: Witness, df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(
        (pl.col("make") == w.make)
        & (pl.col("model_gen") == w.model_gen)
        & (pl.col("generation") == w.generation)
    )


def test_witness_stock_orders_of_magnitude(w: Witness, gold: dict[str, pl.DataFrame]) -> None:
    rows = _gold_rows(w, gold["indicators"])
    stock = {r["country"]: r["stock"] for r in rows.iter_rows(named=True)}
    assert {"GB", "NL", "EU"} <= set(stock), f"missing countries for {witness_id(w)}: {stock}"
    assert w.gb_stock[0] <= stock["GB"] <= w.gb_stock[1], f"GB stock {stock['GB']} out of bounds"
    assert w.nl_stock[0] <= stock["NL"] <= w.nl_stock[1], f"NL stock {stock['NL']} out of bounds"
    assert stock["EU"] == stock["GB"] + stock["NL"]


def test_witness_series_are_generation_level(w: Witness, gold: dict[str, pl.DataFrame]) -> None:
    """A broken generation resolution makes the witness fall back to the generic model."""
    rows = _gold_rows(w, gold["indicators"])
    by_country = {r["country"]: r for r in rows.iter_rows(named=True)}
    assert by_country["GB"]["level"] == "generation"
    assert by_country["GB"]["series"] == "VEH0124"
    assert by_country["NL"]["series"] == "RDW"
    assert by_country["GB"]["history_years"] >= 5
    for country in ("GB", "NL", "EU"):
        assert 0 < by_country[country]["survival"] <= 1


def test_witness_score_has_every_component(w: Witness, gold: dict[str, pl.DataFrame]) -> None:
    rows = _gold_rows(w, gold["scores"]).filter(pl.col("level") == "europe")
    assert rows.height == 1, f"expected one europe score row for {witness_id(w)}"
    row = rows.to_dicts()[0]
    assert row["weight_coverage"] == pytest.approx(1.0)
    assert set(row["components_available"].split("|")) == set(sc.COMPONENTS)
    assert 0 < row["score"] < 1
    assert 1 <= row["rank"] <= gold["scores"].height
    assert 0 < row["sorn_ratio"] < 1
    assert row["recent_inflection_point"] in (0.0, 1.0)


def test_witness_gb_stock_declines(w: Witness, gold: dict[str, pl.DataFrame]) -> None:
    """A 1990-2015 model must be shrinking over the observed GB window."""
    series = (
        _gold_rows(w, gold["stock_series"])
        .filter((pl.col("country") == "GB") & (pl.col("series") == "VEH0124"))
        .sort("year")
    )
    assert series.height >= 5, f"only {series.height} GB points for {witness_id(w)}"
    stock = series["stock"].to_list()
    assert stock[-1] < stock[0], f"{witness_id(w)} GB stock is not declining: {stock}"
