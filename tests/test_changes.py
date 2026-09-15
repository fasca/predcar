"""The « Évolutions » diff: what counts as a change between two published rankings."""

import polars as pl

from predcar import changes
from predcar.config import load_score_config

CFG = load_score_config()  # rarity thresholds [500, 100, 20], alerts.top_n 50


def _ranking(rows: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "rank": rank,
                "make": "M",
                "model_gen": model,
                "generation": "G1",
                "stock": stock,
                "inflection_year": infl,
            }
            for rank, model, stock, infl in rows
        ],
        schema={
            "rank": pl.Int64,
            "make": pl.Utf8,
            "model_gen": pl.Utf8,
            "generation": pl.Utf8,
            "stock": pl.Int64,
            "inflection_year": pl.Int64,
        },
    )


def test_each_kind_is_detected_once() -> None:
    previous = _ranking(
        [
            (1, "STABLE", 300, 2020),  # unchanged: nothing reported
            (2, "GONE", 900, None),  # leaves the ranking
            (60, "CLIMBS", 700, None),  # enters the top 50
            (10, "DROPS", 700, None),  # leaves the top 50
            (20, "RARER", 120, None),  # crosses under 100
            (30, "TURNS", 800, None),  # gains an inflection year
        ]
    )
    current = _ranking(
        [
            (1, "STABLE", 290, 2020),
            (3, "NEW", 50, None),  # published for the first time
            (40, "CLIMBS", 690, None),
            (70, "DROPS", 690, None),
            (21, "RARER", 95, None),
            (31, "TURNS", 790, 2025),
        ]
    )
    out = changes.compare(previous, current, CFG)
    got = {(r["kind"], r["model_gen"]) for r in out.iter_rows(named=True)}
    assert got == {
        ("published", "NEW"),
        ("unpublished", "GONE"),
        ("top_in", "CLIMBS"),
        ("top_out", "DROPS"),
        ("tier_down", "RARER"),
        ("inflection", "TURNS"),
    }
    rarer = out.filter(pl.col("kind") == "tier_down").row(0, named=True)
    assert (rarer["before"], rarer["after"]) == ("<500", "<100")
    # display order follows KINDS, then current rank
    assert out["kind"].to_list() == [
        "published",
        "unpublished",
        "tier_down",
        "inflection",
        "top_in",
        "top_out",
    ]


def test_a_rank_move_alone_is_not_a_change() -> None:
    """Adding targets shifts every rank; that is noise, not news."""
    previous = _ranking([(5, "A", 300, None), (6, "B", 300, None)])
    current = _ranking([(25, "A", 300, None), (26, "B", 300, None)])
    assert changes.compare(previous, current, CFG).height == 0


def test_tier_up_is_not_reported_and_top_n_comes_from_config() -> None:
    previous = _ranking([(2, "A", 90, None)])
    current = _ranking([(80, "A", 150, None)])  # rarer → less rare: not a tier_down
    out = changes.compare(previous, current, CFG)
    assert out["kind"].to_list() == ["top_out"]
    assert f"top {CFG.alerts.top_n}" in out["detail"][0]


def test_identical_rankings_produce_an_empty_frame_with_the_schema() -> None:
    r = _ranking([(1, "A", 300, None)])
    out = changes.compare(r, r, CFG)
    assert out.height == 0 and list(out.columns) == list(changes.CHANGES_SCHEMA)
