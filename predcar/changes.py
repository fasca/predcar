"""What changed between two published rankings — the site's « Évolutions » page and feed.

The project has no user accounts and no mailing list. Its alert is a diff: the quarterly
refresh commits a new evidence bundle, the site is rebuilt from the two latest ones, and a
reader subscribed to the Atom feed sees what moved. Everything is computed from
``gold/ranking.csv``, which every committed bundle carries.

A raw rank move is deliberately **not** a change: as soon as targets are added, every rank
shifts and the signal is noise. Entering or leaving the top N is.
"""

from __future__ import annotations

import polars as pl

from predcar.config import ScoreConfig
from predcar.metrics import rarity_tier

KEY = ["make", "model_gen", "generation"]

# In display order.
KINDS = ("published", "unpublished", "tier_down", "inflection", "top_in", "top_out")

CHANGES_SCHEMA = {
    "kind": pl.Utf8,
    "make": pl.Utf8,
    "model_gen": pl.Utf8,
    "generation": pl.Utf8,
    "rank": pl.Int32,  # current rank, null when the target left the ranking
    "before": pl.Utf8,
    "after": pl.Utf8,
    "detail": pl.Utf8,
}


def _tier_rank(tier: str, thresholds: list[int]) -> int:
    """Position of a tier label in the ordered thresholds; lower = rarer."""
    labels = [f"<{t}" for t in sorted(thresholds)] + [f">={max(thresholds)}"]
    return labels.index(tier)


def compare(previous: pl.DataFrame, current: pl.DataFrame, cfg: ScoreConfig) -> pl.DataFrame:
    """One row per reportable change from ``previous`` to ``current`` ranking.

    Args:
        previous: ``ranking.csv`` of the earlier bundle.
        current: ``ranking.csv`` of the later bundle.
        cfg: ``alerts.top_n`` and ``rarity.thresholds`` come from here, never from code.

    Returns:
        Rows sorted by kind (``KINDS`` order) then current rank.
    """
    thresholds = cfg.rarity.thresholds
    top_n = cfg.alerts.top_n
    cols = [*KEY, "rank", "stock", "inflection_year"]
    prev = previous.select(cols).rename(
        {c: f"{c}_prev" for c in ("rank", "stock", "inflection_year")}
    )
    cur = current.select(cols)
    joined = prev.join(cur, on=KEY, how="full", coalesce=True)
    rows: list[dict] = []

    def add(kind: str, r: dict, before: str, after: str, detail: str) -> None:
        rows.append(
            {
                "kind": kind,
                "make": r["make"],
                "model_gen": r["model_gen"],
                "generation": r["generation"],
                "rank": r.get("rank"),
                "before": before,
                "after": after,
                "detail": detail,
            }
        )

    for r in joined.iter_rows(named=True):
        in_prev, in_cur = r["rank_prev"] is not None, r["rank"] is not None
        if in_cur and not in_prev:
            add("published", r, "", f"rang {r['rank']}", f"parc {r['stock']}")
            continue
        if in_prev and not in_cur:
            add("unpublished", r, f"rang {r['rank_prev']}", "", "sortie du classement")
            continue
        # present in both
        tier_prev = rarity_tier(int(r["stock_prev"]), thresholds)
        tier_cur = rarity_tier(int(r["stock"]), thresholds)
        if _tier_rank(tier_cur, thresholds) < _tier_rank(tier_prev, thresholds):
            add("tier_down", r, tier_prev, tier_cur, f"parc {r['stock_prev']} → {r['stock']}")
        if r["inflection_year_prev"] is None and r["inflection_year"] is not None:
            add(
                "inflection",
                r,
                "",
                str(r["inflection_year"]),
                "attrition passée sous la médiane des pairs",
            )
        if r["rank_prev"] > top_n >= r["rank"]:
            add(
                "top_in",
                r,
                f"rang {r['rank_prev']}",
                f"rang {r['rank']}",
                f"entre dans le top {top_n}",
            )
        elif r["rank"] > top_n >= r["rank_prev"]:
            add("top_out", r, f"rang {r['rank_prev']}", f"rang {r['rank']}", f"sort du top {top_n}")

    if not rows:
        return pl.DataFrame(schema=CHANGES_SCHEMA)
    order = {k: i for i, k in enumerate(KINDS)}
    out = pl.DataFrame(rows, schema=CHANGES_SCHEMA)
    return (
        out.with_columns(pl.col("kind").replace_strict(order, return_dtype=pl.Int32).alias("_k"))
        .sort("_k", "rank", nulls_last=True)
        .drop("_k")
    )
