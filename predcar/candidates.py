"""Propose models that shrink like targets but are not in ``mapping/target_models.csv``.

The target list is an editorial decision: a target is a *generation* with production years,
which the registers do not carry. This module therefore never writes to the target list. It
reads the long model-level history (VEH0120 for GB), finds mapped models whose fleet fell from
its peak the way collector cars do, and writes a proposal the user curates by hand.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from predcar import metrics
from predcar.config import CandidatesConfig
from predcar.normalize import TargetModel
from predcar.paths import REPORTS_DIR

logger = logging.getLogger(__name__)

CANDIDATES_FILE = "candidates.csv"

CANDIDATES_SCHEMA = {
    "make": pl.Utf8,
    "model_gen": pl.Utf8,
    "peak_year": pl.Int32,
    "stock_peak": pl.Int64,
    "year_now": pl.Int32,
    "stock_now": pl.Int64,
    "loss": pl.Float64,
    "existing_targets_of_make": pl.Utf8,
}


def find(
    stock: pl.DataFrame,
    targets: list[TargetModel],
    cfg: CandidatesConfig,
    unknown_labels: tuple[str, ...] = (),
) -> pl.DataFrame:
    """Models of the configured series that lost at least ``cfg.loss_min`` of their peak fleet.

    Args:
        stock: normalized silver ``fleet_stock`` (``make``/``model_gen`` filled).
        targets: the current target list; its ``(make, model_gen)`` pairs are excluded.
        cfg: thresholds (``config/mapping.yaml: candidates``).
        unknown_labels: ``model_raw`` values meaning "unknown model", never candidates.

    Returns:
        One row per candidate ``(make, model_gen)``, most depleted first. ``stock`` is the
        fleet in circulation (every status but SORN) at the last period of each year;
        ``loss = 1 − stock_now / stock_peak``. ``existing_targets_of_make`` lists the
        targets the make already has, so a base model whose sporty version is already a target
        (``306`` next to ``306 S16 MK1``) is recognisable at a glance.
    """
    annual = metrics.annual_stock(stock)
    scoped = (
        annual.filter((pl.col("country") == cfg.country.upper()) & (pl.col("series") == cfg.series))
        .group_by("make", "model_gen", "year")
        .agg(pl.col("stock").sum())
    )
    if not scoped.height:
        return pl.DataFrame(schema=CANDIDATES_SCHEMA)

    already = {(t.make, t.model_gen) for t in targets}
    unknown = {u.upper() for u in unknown_labels}
    by_make: dict[str, list[str]] = {}
    for t in targets:
        by_make.setdefault(t.make, []).append(f"{t.model_gen} {t.generation}")

    keys = ["make", "model_gen"]
    peak = (
        scoped.filter(pl.col("stock") == pl.col("stock").max().over(keys))
        .group_by(keys)
        .agg(pl.col("year").min().alias("peak_year"), pl.col("stock").first().alias("stock_peak"))
    )
    now = scoped.filter(pl.col("year") == pl.col("year").max().over(keys)).select(
        *keys, pl.col("year").alias("year_now"), pl.col("stock").alias("stock_now")
    )
    out = (
        peak.join(now, on=keys)
        .with_columns((1 - pl.col("stock_now") / pl.col("stock_peak")).alias("loss"))
        .filter(
            ~pl.col("model_gen").str.contains(cfg.exclude_model_gen)
            & ~pl.col("model_gen").str.to_uppercase().is_in(list(unknown))
            & (pl.col("stock_peak") >= cfg.stock_peak_min)
            & (pl.col("stock_now") <= cfg.stock_now_max)
            & (pl.col("loss") >= cfg.loss_min)
        )
    )
    rows = [
        {
            **r,
            "existing_targets_of_make": ", ".join(sorted(by_make.get(r["make"], []))),
        }
        for r in out.iter_rows(named=True)
        if (r["make"], r["model_gen"]) not in already
    ]
    if not rows:
        return pl.DataFrame(schema=CANDIDATES_SCHEMA)
    return (
        pl.DataFrame(rows)
        .select(list(CANDIDATES_SCHEMA))
        .cast(CANDIDATES_SCHEMA)
        .sort("loss", "stock_now", descending=[True, False])
    )


def write(candidates: pl.DataFrame, out_dir: Path | None = None) -> Path:
    """Write the proposal to ``reports/<YYYY-MM-DD>/candidates.csv`` and return its path."""
    out_dir = out_dir or REPORTS_DIR / datetime.now(UTC).date().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / CANDIDATES_FILE
    candidates.write_csv(path)
    logger.info("%d candidate(s) written to %s", candidates.height, path)
    return path
