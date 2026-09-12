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

A target is identified by ``(make, model_gen, generation)``: two makes may share a
``model_gen`` label (ALFA ROMEO SPIDER, RENAULT SPIDER) and are never merged.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date

import polars as pl

from predcar.config import ScoreConfig
from predcar.normalize import TargetModel

logger = logging.getLogger(__name__)

GEN_LEVEL_SERIES = ("VEH0124", "RDW")
MODEL_LEVEL_SERIES = ("VEH0120", "RDW")
SORN_SERIES = "VEH0120"
SALES_SERIES = "VEH0160"  # fleet_new_reg: cumulative sales, survival denominator
EUROPE = "EU"
TARGET_KEY = ["make", "model_gen", "generation"]


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
    """End-of-year stock per (country, series, make, model_gen, generation, year).

    ``stock`` = vehicles in circulation (every status except ``sorn``), ``sorn`` = SORN
    count (0 where the source has no such status). For quarterly/monthly series the last
    period of each year is kept.
    """
    keys = ["country", "series", "make", "model_gen", "generation", "year"]
    df = (
        stock.filter(pl.col("model_gen").is_not_null())
        .with_columns(
            pl.col("source_file").map_elements(series_of, return_dtype=pl.Utf8).alias("series"),
            pl.col("period").dt.year().alias("year"),
            (pl.col("status") == "sorn").fill_null(False).alias("is_sorn"),
        )
        .group_by(*keys, "period")
        .agg(
            pl.col("count").filter(~pl.col("is_sorn")).sum().alias("stock"),
            pl.col("count").filter(pl.col("is_sorn")).sum().alias("sorn"),
        )
    )
    # window filter rather than a join: joins do not match null generations
    return (
        df.filter(pl.col("period") == pl.col("period").max().over(keys))
        .select(*keys, "period", "stock", "sorn")
        .sort(keys)
    )


COHORTS_SCHEMA = {
    "make": pl.Utf8,
    "model_gen": pl.Utf8,
    "generation": pl.Utf8,
    "country": pl.Utf8,
    "series": pl.Utf8,
    "cohort": pl.Int32,
    "year": pl.Int32,
    "stock": pl.Int64,
    "retention": pl.Float64,
}


def cohort_retention(stock: pl.DataFrame, targets: list[TargetModel]) -> pl.DataFrame:
    """Aggregated retention curves per (target, country, first-registration cohort).

    ``retention(cohort, year) = stock(cohort, year) / max stock observed for the cohort``
    (SPEC §5: retention curves, not Kaplan-Meier). Only the generation-level series carry a
    cohort year (VEH0124, RDW); end-of-year values as in :func:`annual_stock`.
    """
    if not targets:
        return pl.DataFrame(schema=COHORTS_SCHEMA)
    keys = ["country", "series", "make", "model_gen", "generation", "cohort", "year"]
    wanted = pl.DataFrame(
        [{"make": t.make, "model_gen": t.model_gen, "generation": t.generation} for t in targets]
    ).unique()
    df = (
        stock.filter(
            pl.col("model_gen").is_not_null()
            & pl.col("generation").is_not_null()
            & pl.col("year_first_reg").is_not_null()
        )
        .with_columns(
            pl.col("source_file").map_elements(series_of, return_dtype=pl.Utf8).alias("series"),
            pl.col("period").dt.year().alias("year"),
            pl.col("year_first_reg").alias("cohort"),
            (pl.col("status") == "sorn").fill_null(False).alias("is_sorn"),
        )
        .filter(pl.col("series").is_in(GEN_LEVEL_SERIES))
        .join(wanted, on=TARGET_KEY, how="inner")
        .group_by(*keys, "period")
        .agg(pl.col("count").filter(~pl.col("is_sorn")).sum().alias("stock"))
        .filter(pl.col("period") == pl.col("period").max().over(keys))
    )
    peak = pl.col("stock").max().over(keys[:-1])
    return (
        df.with_columns(
            pl.when(peak > 0).then(pl.col("stock") / peak).otherwise(None).alias("retention")
        )
        .select(list(COHORTS_SCHEMA))
        .cast(COHORTS_SCHEMA)
        .sort(keys)
    )


def annual_new_reg(new_reg: pl.DataFrame) -> pl.DataFrame:
    """New registrations per (country, make, model_gen, year)."""
    return (
        new_reg.filter(pl.col("model_gen").is_not_null())
        .with_columns(pl.col("period").dt.year().alias("year"))
        .group_by("country", "make", "model_gen", "year")
        .agg(pl.col("count").sum().alias("new_reg"))
        .sort("country", "make", "model_gen", "year")
    )


def _for_target(df: pl.DataFrame, target: TargetModel, country: str) -> pl.DataFrame:
    return df.filter(
        (pl.col("country") == country)
        & (pl.col("make") == target.make)
        & (pl.col("model_gen") == target.model_gen)
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
    periods: list[date]  # actual observation dates (a partial year is a shorter Δt)


def select_series(
    annual: pl.DataFrame,
    target: TargetModel,
    country: str,
    sole_generation: bool = True,
) -> TargetSeries | None:
    """Generation-level series if present, else the model_gen-level series.

    The model_gen-level fallback (all generations summed) is only meaningful when the target
    is the sole target generation of its (make, model_gen); otherwise it would credit every
    generation with the whole model's stock, so ``None`` is returned instead.
    """
    base = _for_target(annual, target, country)
    gen = base.filter(
        (pl.col("generation") == target.generation) & pl.col("series").is_in(GEN_LEVEL_SERIES)
    )
    if gen.height:
        best = gen.group_by("series").len().sort("len", descending=True)["series"][0]
        rows = gen.filter(pl.col("series") == best).sort("year")
        return TargetSeries(
            country,
            "generation",
            best,
            rows["year"].to_list(),
            rows["stock"].to_list(),
            rows["period"].to_list(),
        )
    model = base.filter(pl.col("series").is_in(MODEL_LEVEL_SERIES))
    if not model.height or not sole_generation:
        return None
    best = model.group_by("series").len().sort("len", descending=True)["series"][0]
    rows = (
        model.filter(pl.col("series") == best)
        .group_by("year")
        .agg(pl.col("stock").sum(), pl.col("period").max())
        .sort("year")
    )
    return TargetSeries(
        country,
        "model_gen",
        best,
        rows["year"].to_list(),
        rows["stock"].to_list(),
        rows["period"].to_list(),
    )


def attrition(
    periods: list[int] | list[date], stock: list[int], smoothing_years: int
) -> list[float | None]:
    """Annual attrition −Δln(Stock)/Δt per observation, then rolling mean over
    ``smoothing_years`` observations.

    ``periods`` are years (Δt in whole years) or observation dates (Δt in fractional
    years, so a partial current year — e.g. a Q1 quarter after a Q4 — is not read as a
    full year of losses). The first observation and any observation adjacent to a zero
    stock get None. The smoothed value at i is the mean of the last ``smoothing_years``
    raw values when all are defined.
    """
    raw: list[float | None] = [None]
    for i in range(1, len(periods)):
        s0, s1 = stock[i - 1], stock[i]
        p0, p1 = periods[i - 1], periods[i]
        dt = (p1 - p0).days / 365.25 if isinstance(p1, date) else p1 - p0
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
    """SORN / (SORN + licensed) at the latest period, generation level when a SORN-carrying
    generation series exists (VEH0124), else model_gen level (VEH0120, all generations)."""
    base = _for_target(annual, target, country)
    gen = base.filter(
        (pl.col("generation") == target.generation)
        & pl.col("series").is_in(GEN_LEVEL_SERIES)
        & (pl.col("sorn") > 0)
    )
    rows = gen if gen.height else base.filter(pl.col("series") == SORN_SERIES)
    if not rows.height:
        return None
    latest = rows.filter(pl.col("year") == rows["year"].max())
    licensed, sorn = latest["stock"].sum(), latest["sorn"].sum()
    return sorn / (sorn + licensed) if sorn + licensed > 0 else None


def cumulative_sales(new_reg_annual: pl.DataFrame, target: TargetModel, country: str) -> int | None:
    """New registrations of the (make, model_gen) inside the generation's production years."""
    rows = _for_target(new_reg_annual, target, country).filter(
        pl.col("year").is_between(target.year_from, target.year_to)
    )
    return int(rows["new_reg"].sum()) if rows.height else None


# --------------------------------------------------------------------------- indicators

_SERIES_SCHEMA = {
    "make": pl.Utf8,
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
}
_INDICATORS_SCHEMA = {
    "make": pl.Utf8,
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
}


def compute_indicators(
    stock: pl.DataFrame,
    new_reg: pl.DataFrame,
    targets: list[TargetModel],
    cfg: ScoreConfig,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """All indicators per (target, country) plus the annual series used.

    Returns:
        ``(indicators, series)``. ``indicators`` has one row per (make, model_gen,
        generation, country) with nullable components; ``series`` the yearly
        stock/attrition used.
    """
    annual = annual_stock(stock)
    new_reg_annual = annual_new_reg(new_reg)
    countries = sorted(annual["country"].unique().to_list())
    generations_per_model: dict[tuple[str, str], int] = {}
    for t in targets:
        key = (t.make, t.model_gen)
        generations_per_model[key] = generations_per_model.get(key, 0) + 1

    # 1. per-target series + attrition
    series_rows: list[dict] = []
    picked: list[tuple[TargetModel, TargetSeries, list[float | None]]] = []
    for t in targets:
        for c in countries:
            ts = select_series(annual, t, c, generations_per_model[(t.make, t.model_gen)] == 1)
            if ts is None:
                continue
            att = attrition(ts.periods, ts.stock, cfg.attrition.smoothing_years)
            picked.append((t, ts, att))
            for y, s, a in zip(ts.years, ts.stock, att, strict=True):
                series_rows.append(
                    {
                        "make": t.make,
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
    series = pl.DataFrame(series_rows, schema=_SERIES_SCHEMA)

    # 2. peer medians: same country, segment and age bucket, pooled over years and models.
    # n_peers counts distinct models, not observations: a model alone in its segment
    # must not be compared with itself.
    peers = (
        series.filter(pl.col("attrition").is_not_null())
        .group_by("country", "segment", "age_bucket")
        .agg(
            pl.col("attrition").median().alias("peer_median"),
            pl.struct(*TARGET_KEY).n_unique().alias("n_peers"),
        )
    )
    peer_lookup = {
        (r["country"], r["segment"], r["age_bucket"]): (r["peer_median"], r["n_peers"])
        for r in peers.iter_rows(named=True)
    }

    # 3. indicators per (target, country)
    out: list[dict] = []
    for t, ts, att in picked:
        c = ts.country
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
                "make": t.make,
                "model_gen": t.model_gen,
                "generation": t.generation,
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
    indicators = pl.DataFrame(out, schema=_INDICATORS_SCHEMA)
    return indicators.sort(*TARGET_KEY, "country"), series


def _inflection_year(
    t: TargetModel,
    ts: TargetSeries,
    att: list[float | None],
    country: str,
    peer_lookup: dict,
    cfg: ScoreConfig,
) -> int | None:
    """First year of the trailing run of *consecutive* years where attrition is below the
    peer median at the same age.

    A missing year (gap in the series) or a missing attrition value resets the run. None
    when the latest year is not below its peers (no ongoing "collectorisation").
    """
    start: int | None = None
    prev_year: int | None = None
    for y, a in zip(ts.years, att, strict=True):
        gap = prev_year is not None and y != prev_year + 1
        prev_year = y
        if a is None or gap:
            start = None
        if a is None:
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
    inflection = the most recent country inflection, survival stock-weighted.

    A value missing in every country stays null (never NaN, never 0).
    """
    if not indicators.height:
        return indicators.clear()
    w = pl.col("stock")
    return (
        indicators.group_by(*TARGET_KEY, "segment")
        .agg(
            pl.lit(EUROPE).alias("country"),
            pl.lit("europe").alias("level"),
            pl.col("series").unique().sort().str.join("+").alias("series"),
            pl.col("latest_year").max(),
            w.sum().alias("stock"),
            _nullable_sum("cumulative_sales").alias("cumulative_sales"),
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


def _nullable_sum(col: str) -> pl.Expr:
    """Sum that stays null when every value is null (Polars' sum of all-null is 0)."""
    return pl.when(pl.col(col).is_not_null().any()).then(pl.col(col).sum()).otherwise(None)


def _weighted(col: str, w: pl.Expr) -> pl.Expr:
    """Stock-weighted mean over countries where the value exists; null (not NaN) if none."""
    mask = pl.col(col).is_not_null()
    total_w = w.filter(mask).sum()
    return pl.when(total_w > 0).then((pl.col(col) * w).filter(mask).sum() / total_w).otherwise(None)
