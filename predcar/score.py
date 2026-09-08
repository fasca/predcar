"""Score v1 (SPEC §5): weighted, renormalized composite of 0–1 components.

Components, all oriented "higher = more collector":

* ``rarity``   — log min-max of the current stock across the scored population (1 = rarest)
* ``conservation`` — rank of −relative_attrition across the population (1 = disappears
  slowest vs. peers)
* ``sorn_ratio`` — SORN / (SORN + licensed), already 0–1 (GB only)
* ``recent_inflection_point`` — 1 if the inflection year is < ``recent_years`` ago, else 0

A missing component is excluded and the remaining weights renormalized to 1; the score is
published only when the available weight sum ≥ ``min_weight_coverage``.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import polars as pl

from predcar import metrics
from predcar.config import ScoreConfig, load_score_config
from predcar.normalize import TARGETS_FILE, load_targets
from predcar.paths import GOLD_DIR, MAPPING_DIR, SILVER_DIR

logger = logging.getLogger(__name__)

COMPONENTS = ("rarity", "conservation", "sorn_ratio", "recent_inflection_point")


class ScoreError(RuntimeError):
    """Scoring cannot run (missing normalized inputs)."""


# --------------------------------------------------------------------------- normalization


def normalize_components(eu: pl.DataFrame, cfg: ScoreConfig) -> pl.DataFrame:
    """Add the four 0–1 components (nullable) to the Europe indicators frame."""
    stock = pl.col("stock").clip(lower_bound=1).cast(pl.Float64).log()
    lo, hi = stock.min(), stock.max()
    rarity = pl.when(hi > lo).then((hi - stock) / (hi - lo)).otherwise(1.0)

    cons_raw = -pl.col("relative_attrition")
    n_avail = cons_raw.is_not_null().sum()
    conservation = (
        pl.when(cons_raw.is_null())
        .then(None)
        .when(n_avail <= 1)
        .then(1.0)
        .otherwise((cons_raw.rank(method="average") - 1) / (n_avail - 1))
    )
    recent = (
        pl.when(pl.col("inflection_year").is_null())
        .then(None)
        .when(pl.col("latest_year") - pl.col("inflection_year") < cfg.inflection.recent_years)
        .then(1.0)
        .otherwise(0.0)
    )
    # A target with peers but no ongoing inflection has a defined component = 0, not null.
    recent = pl.when(pl.col("relative_attrition").is_not_null()).then(recent.fill_null(0.0))
    return eu.with_columns(
        rarity.alias("rarity"),
        conservation.alias("conservation"),
        pl.col("sorn_ratio").alias("sorn_ratio_component"),
        recent.alias("recent_inflection_point"),
    ).rename({"sorn_ratio_component": "sorn_ratio_c"})


def composite(df: pl.DataFrame, cfg: ScoreConfig) -> pl.DataFrame:
    """Weighted score with renormalized weights and the publication gate."""
    weights = cfg.weights.as_dict()
    cols = {
        "rarity": "rarity",
        "conservation": "conservation",
        "sorn_ratio": "sorn_ratio_c",
        "recent_inflection_point": "recent_inflection_point",
    }
    avail = [pl.col(cols[c]).is_not_null().cast(pl.Float64) * weights[c] for c in COMPONENTS]
    weight_cov = sum(avail[1:], avail[0])
    weighted = [pl.col(cols[c]).fill_null(0.0) * weights[c] for c in COMPONENTS]
    total = sum(weighted[1:], weighted[0])
    available = pl.concat_list(
        [pl.when(pl.col(cols[c]).is_not_null()).then(pl.lit(c)) for c in COMPONENTS]
    ).list.drop_nulls()
    out = df.with_columns(
        weight_cov.alias("weight_coverage"),
        available.alias("components_available"),
    ).with_columns(
        pl.when(pl.col("weight_coverage") >= cfg.min_weight_coverage)
        .then(total / pl.col("weight_coverage"))
        .otherwise(None)
        .alias("score")
    )
    return out.with_columns(
        pl.col("score").rank(method="min", descending=True).cast(pl.Int32).alias("rank")
    ).sort("rank", "make", "model_gen", "generation", nulls_last=True)


# --------------------------------------------------------------------------- pipeline


def score(
    silver_dir: Path = SILVER_DIR,
    gold_dir: Path = GOLD_DIR,
    mapping_dir: Path = MAPPING_DIR,
    cfg: ScoreConfig | None = None,
) -> dict[str, Path]:
    """Compute indicators and scores from the normalized silver tables into ``gold/``."""
    cfg = cfg or load_score_config()
    stock_path, new_reg_path = (
        silver_dir / "fleet_stock.parquet",
        silver_dir / "fleet_new_reg.parquet",
    )
    if not stock_path.is_file():
        raise ScoreError(f"{stock_path} missing: run `predcar normalize` first")
    stock = pl.read_parquet(stock_path)
    new_reg = (
        pl.read_parquet(new_reg_path)
        if new_reg_path.is_file()
        else stock.clear().select("country", "period", "model_gen", "count")
    )
    targets = load_targets(mapping_dir / TARGETS_FILE)

    indicators, series = metrics.compute_indicators(stock, new_reg, targets, cfg)
    eu = metrics.aggregate_europe(indicators)
    scores = composite(normalize_components(eu, cfg), cfg)
    published = scores.filter(pl.col("score").is_not_null()).height
    logger.info(
        "%d targets with data, %d scored (weight coverage ≥ %.0f%%)",
        eu.height,
        published,
        100 * cfg.min_weight_coverage,
    )

    gold_dir.mkdir(parents=True, exist_ok=True)
    written = {
        "series": gold_dir / "stock_series.parquet",
        "indicators": gold_dir / "indicators.parquet",
        "scores": gold_dir / "scores.parquet",
        "ranking": gold_dir / "ranking.csv",
    }
    series.write_parquet(written["series"])
    pl.concat([indicators, eu]).write_parquet(written["indicators"])
    scores.write_parquet(written["scores"])
    # ranking.csv is the public export: only targets that passed the publication gate
    scores.filter(pl.col("score").is_not_null()).select(
        "rank",
        "make",
        "model_gen",
        "generation",
        "segment",
        "score",
        "weight_coverage",
        "stock",
        "rarity",
        "conservation",
        "sorn_ratio",
        "recent_inflection_point",
        "relative_attrition",
        "inflection_year",
        "latest_year",
        pl.col("components_available").list.join("|"),
    ).write_csv(written["ranking"])
    return written


def is_finite(x: float | None) -> bool:
    return x is not None and math.isfinite(x)
