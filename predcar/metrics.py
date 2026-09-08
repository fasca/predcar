"""Indicators (SPEC §5) computed from the normalized silver tables.

Levels
------
Two families of series describe the same fleet and must never be summed together:

* ``VEH0124`` (GB, annual, by first-registration year) and ``RDW`` (NL, monthly snapshots,
  by first-admission year) resolve to the **generation** level.
* ``VEH0120`` (GB, quarterly, no year, licensed + SORN) resolves to the **model_gen** level
  and is the only series carrying SORN.

For each target generation and country, stock and attrition come from the generation-level
series when it exists, otherwise from the model_gen-level series (``level`` is recorded).
The SORN ratio is always model_gen level (GB only). Cumulative sales come from
``fleet_new_reg`` (VEH0160, model_gen level, 2001+) restricted to the generation's years.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import polars as pl

from predcar.config import ScoreConfig
from predcar.normalize import TargetModel

logger = logging.getLogger(__name__)

GEN_LEVEL_SERIES = ("VEH0124", "RDW")
MODEL_LEVEL_SERIES = ("VEH0120", "RDW")
SORN_SERIES = "VEH0120"
EUROPE = "EU"


def series_of(source_file: str) -> str:
    """Series family of a silver row, from its raw file name."""
    name = source_file.upper()
    for key in ("VEH0120", "VEH0124", "VEH0160"):
        if key in name:
            return key
    if "GEKENTEKENDE" in name or "RDW" in name:
        return "RDW"
    raise ValueError(f"unknown series for source_file {source_file!r}")


# --------------------------------------------------------------------------- annual series


def annual_stock(stock: pl.DataFrame) -> pl.DataFrame:
    """End-of-year stock per (country, series, model_gen, generation, year).

    ``stock`` = vehicles in circulation (every status except ``sorn``), ``sorn`` = SORN
    count (0 where the source has no such status). For quarterly/monthly series the last
    period of each year is kept.
    """
    df = (
        stock.filter(pl.col("model_gen").is_not_null())
        .with_columns(
            pl.col("source_file").map_elements(series_of, return_dtype=pl.Utf8).alias("series"),
            pl.col("period").dt.year().alias("year"),
            (pl.col("status") == "sorn").fill_null(False).alias("is_sorn"),
        )
        .group_by("country", "series", "model_gen", "generation", "year", "period")
        .agg(
            pl.col("count").filter(~pl.col("is_sorn")).sum().alias("stock"),
            pl.col("count").filter(pl.col("is_sorn")).sum().alias("sorn"),
        )
    )
    keys = ["country", "series", "model_gen", "generation", "year"]
    # window filter rather than a join: joins do not match null generations
    return (
        df.filter(pl.col("period") == pl.col("period").max().over(keys))
        .select(*keys, "period", "stock", "sorn")
        .sort(keys)
    )


def annual_new_reg(new_reg: pl.DataFrame) -> pl.DataFrame:
    """New registrations per (country, model_gen, year)."""
    return (
        new_reg.filter(pl.col("model_gen").is_not_null())
        .with_columns(pl.col("period").dt.year().alias("year"))
        .group_by("country", "model_gen", "year")
        .agg(pl.col("count").sum().alias("new_reg"))
        .sort("country", "model_gen", "year")
    )


# --------------------------------------------------------------------------- per target


@dataclass(frozen=True)
class TargetSeries:
    """Annual series chosen for one (target, country), with the level it comes from."""

    country: str
    level: str  # "generation" | "model_gen"
    series: str
    years: list[int]
    stock: list[int]


def select_series(
    annual: pl.DataFrame,
    target: TargetModel,
    country: str,
    sole_generation: bool = True,
) -> TargetSeries | None:
    """Generation-level series if present, else the model_gen-level series.

    The model_gen-level fallback (all generations summed) is only meaningful when the target
    is the sole target generation of its model_gen; otherwise it would credit every
    generation with the whole model's stock, so ``None`` is returned instead.
    """
    base = annual.filter((pl.col("country") == country) & (pl.col("model_gen") == target.model_gen))
    gen = base.filter(
        (pl.col("generation") == target.generation) & pl.col("series").is_in(GEN_LEVEL_SERIES)
    )
    if gen.height:
        # one series only: prefer the one with the most years
        best = gen.group_by("series").len().sort("len", descending=True)["series"][0]
        rows = gen.filter(pl.col("series") == best).sort("year")
        return TargetSeries(
            country, "generation", best, rows["year"].to_list(), rows["stock"].to_list()
        )
    model = base.filter(pl.col("series").is_in(MODEL_LEVEL_SERIES))
    if not model.height or not sole_generation:
        return None
    best = model.group_by("series").len().sort("len", descending=True)["series"][0]
    rows = (
        model.filter(pl.col("series") == best)
        .group_by("year")
        .agg(pl.col("stock").sum())
        .sort("year")
    )
    return TargetSeries(country, "model_gen", best, rows["year"].to_list(), rows["stock"].to_list())


def attrition(years: list[int], stock: list[int], smoothing_years: int) -> list[float | None]:
    """Annual attrition −Δln(Stock)/Δt per year, then rolling mean over ``smoothing_years``.

    The first year and any year adjacent to a zero stock get None. The smoothed value at
    year i is the mean of the last ``smoothing_years`` raw values when all are defined.
    """
    raw: list[float | None] = [None]
    for i in range(1, len(years)):
        s0, s1, dt = stock[i - 1], stock[i], years[i] - years[i - 1]
        raw.append(-(math.log(s1) - math.log(s0)) / dt if s0 > 0 and s1 > 0 and dt > 0 else None)
    smoothed: list[float | None] = []
    for i in range(len(raw)):
        window = raw[max(0, i - smoothing_years + 1) : i + 1]
        ok = len(window) == smoothing_years and all(v is not None for v in window)
        smoothed.append(sum(window) / smoothing_years if ok else None)  # type: ignore[arg-type]
    return smoothed


def mid_year(target: TargetModel) -> int:
    return (target.year_from + target.year_to) // 2


def age_bucket(year: int, target: TargetModel, bucket_years: int) -> int:
    return (year - mid_year(target)) // bucket_years


def rarity_tier(stock: int, thresholds: list[int]) -> str:
    """Label from the SPEC thresholds, e.g. ``<20``, ``<100``, ``<500`` or ``>=500``."""
    for t in sorted(thresholds):
        if stock < t:
            return f"<{t}"
    return f">={max(thresholds)}"


def sorn_ratio(annual: pl.DataFrame, target: TargetModel, country: str) -> float | None:
    """SORN / (SORN + licensed) at the latest period of the SORN-carrying series (model_gen)."""
    rows = annual.filter(
        (pl.col("country") == country)
        & (pl.col("model_gen") == target.model_gen)
        & (pl.col("series") == SORN_SERIES)
    )
    if not rows.height:
        return None
    latest = rows.filter(pl.col("year") == rows["year"].max())
    licensed, sorn = latest["stock"].sum(), latest["sorn"].sum()
    return sorn / (sorn + licensed) if sorn + licensed > 0 else None


def cumulative_sales(new_reg_annual: pl.DataFrame, target: TargetModel, country: str) -> int | None:
    """New registrations of the model_gen inside the generation's production years."""
    rows = new_reg_annual.filter(
        (pl.col("country") == country)
        & (pl.col("model_gen") == target.model_gen)
        & pl.col("year").is_between(target.year_from, target.year_to)
    )
    return int(rows["new_reg"].sum()) if rows.height else None


# --------------------------------------------------------------------------- indicators


def compute_indicators(
    stock: pl.DataFrame,
    new_reg: pl.DataFrame,
    targets: list[TargetModel],
    cfg: ScoreConfig,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """All indicators per (target, country) plus the annual series used.

    Returns:
        ``(indicators, series)``. ``indicators`` has one row per (model_gen, generation,
        country) with nullable components; ``series`` the yearly stock/attrition used.
    """
    annual = annual_stock(stock)
    new_reg_annual = annual_new_reg(new_reg)
    countries = sorted(annual["country"].unique().to_list())
    generations_per_model: dict[str, int] = {}
    for t in targets:
        generations_per_model[t.model_gen] = generations_per_model.get(t.model_gen, 0) + 1

    # 1. per-target series + attrition
    series_rows: list[dict] = []
    picked: dict[tuple[str, str, str], tuple[TargetModel, TargetSeries, list[float | None]]] = {}
    for t in targets:
        for c in countries:
            ts = select_series(annual, t, c, generations_per_model[t.model_gen] == 1)
            if ts is None:
                continue
            att = attrition(ts.years, ts.stock, cfg.attrition.smoothing_years)
            picked[(t.model_gen, t.generation, c)] = (t, ts, att)
            for y, s, a in zip(ts.years, ts.stock, att, strict=True):
                series_rows.append(
                    {
                        "model_gen": t.model_gen,
                        "generation": t.generation,
                        "segment": t.segment,
                        "country": c,
                        "level": ts.level,
                        "series": ts.series,
                        "year": y,
                        "stock": s,
                        "attrition": a,
                        "age_bucket": age_bucket(y, t, cfg.peers.age_bucket_years),
                    }
                )
    series = pl.DataFrame(
        series_rows,
        schema={
            "model_gen": pl.Utf8,
            "generation": pl.Utf8,
            "segment": pl.Utf8,
            "country": pl.Utf8,
            "level": pl.Utf8,
            "series": pl.Utf8,
            "year": pl.Int32,
            "stock": pl.Int64,
            "attrition": pl.Float64,
            "age_bucket": pl.Int32,
        },
    )

    # 2. peer medians: same country, segment and age bucket, pooled over years and models
    # n_peers counts distinct models, not observations: a model alone in its segment
    # must not be compared with itself.
    peers = (
        series.filter(pl.col("attrition").is_not_null())
        .group_by("country", "segment", "age_bucket")
        .agg(
            pl.col("attrition").median().alias("peer_median"),
            pl.struct("model_gen", "generation").n_unique().alias("n_peers"),
        )
    )
    peer_lookup = {
        (r["country"], r["segment"], r["age_bucket"]): (r["peer_median"], r["n_peers"])
        for r in peers.iter_rows(named=True)
    }

    # 3. indicators per (target, country)
    out: list[dict] = []
    for (model_gen, generation, c), (t, ts, att) in picked.items():
        latest_year, latest_stock = ts.years[-1], ts.stock[-1]
        n_points = sum(a is not None for a in att)
        history_ok = n_points >= cfg.attrition.min_history_years
        att_latest = att[-1] if history_ok else None
        rel, inflection, n_peers = None, None, 0
        if att_latest is not None:
            med, n_peers = peer_lookup.get(
                (c, t.segment, age_bucket(latest_year, t, cfg.peers.age_bucket_years)), (None, 0)
            )
            if med is not None and n_peers >= cfg.peers.min_peers:
                rel = att_latest - med
                inflection = _inflection_year(t, ts, att, c, peer_lookup, cfg)
        sales = cumulative_sales(new_reg_annual, t, c)
        denom = max(sales or 0, max(ts.stock))
        out.append(
            {
                "model_gen": model_gen,
                "generation": generation,
                "segment": t.segment,
                "country": c,
                "level": ts.level,
                "series": ts.series,
                "latest_year": latest_year,
                "stock": latest_stock,
                "rarity_tier": rarity_tier(latest_stock, cfg.rarity.thresholds),
                "cumulative_sales": sales,
                "survival": latest_stock / denom if denom > 0 else None,
                "history_years": n_points,
                "attrition": att_latest,
                "relative_attrition": rel,
                "n_peers": n_peers,
                "inflection_year": inflection,
                "sorn_ratio": sorn_ratio(annual, t, c),
            }
        )
    indicators = pl.DataFrame(
        out,
        schema={
            "model_gen": pl.Utf8,
            "generation": pl.Utf8,
            "segment": pl.Utf8,
            "country": pl.Utf8,
            "level": pl.Utf8,
            "series": pl.Utf8,
            "latest_year": pl.Int32,
            "stock": pl.Int64,
            "rarity_tier": pl.Utf8,
            "cumulative_sales": pl.Int64,
            "survival": pl.Float64,
            "history_years": pl.Int32,
            "attrition": pl.Float64,
            "relative_attrition": pl.Float64,
            "n_peers": pl.Int32,
            "inflection_year": pl.Int32,
            "sorn_ratio": pl.Float64,
        },
    )
    return indicators.sort("model_gen", "generation", "country"), series


def _inflection_year(
    t: TargetModel,
    ts: TargetSeries,
    att: list[float | None],
    country: str,
    peer_lookup: dict,
    cfg: ScoreConfig,
) -> int | None:
    """First year of the trailing run where attrition is below the peer median at same age.

    None when the latest year is not below its peers (no ongoing "collectorisation").
    """
    start: int | None = None
    for y, a in zip(ts.years, att, strict=True):
        if a is None:
            start = None
            continue
        med, n = peer_lookup.get(
            (country, t.segment, age_bucket(y, t, cfg.peers.age_bucket_years)), (None, 0)
        )
        below = med is not None and n >= cfg.peers.min_peers and a < med
        if below:
            start = y if start is None else start
        else:
            start = None
    return start


# --------------------------------------------------------------------------- Europe


def aggregate_europe(indicators: pl.DataFrame) -> pl.DataFrame:
    """One row per target: stock summed over countries, attrition stock-weighted, SORN from GB,
    inflection = the most recent country inflection, survival stock-weighted."""
    if not indicators.height:
        return indicators.clear()
    w = pl.col("stock")
    eu = (
        indicators.group_by("model_gen", "generation", "segment")
        .agg(
            pl.lit(EUROPE).alias("country"),
            pl.lit("europe").alias("level"),
            pl.col("series").unique().sort().str.join("+").alias("series"),
            pl.col("latest_year").max(),
            w.sum().alias("stock"),
            pl.col("cumulative_sales").sum().alias("cumulative_sales"),
            _weighted("survival", w).alias("survival"),
            pl.col("history_years").max(),
            _weighted("attrition", w).alias("attrition"),
            _weighted("relative_attrition", w).alias("relative_attrition"),
            pl.col("n_peers").max(),
            pl.col("inflection_year").max().alias("inflection_year"),
            pl.col("sorn_ratio").filter(pl.col("country") == "GB").first().alias("sorn_ratio"),
        )
        .with_columns(pl.lit(None, dtype=pl.Utf8).alias("rarity_tier"))
        .select(indicators.columns)
    )
    return eu


def _weighted(col: str, w: pl.Expr) -> pl.Expr:
    """Stock-weighted mean over countries where the value exists; null (not NaN) if none."""
    mask = pl.col(col).is_not_null()
    total_w = w.filter(mask).sum()
    return pl.when(total_w > 0).then((pl.col(col) * w).filter(mask).sum() / total_w).otherwise(None)
