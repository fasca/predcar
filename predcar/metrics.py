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

from predcar.config import ScoreConfig, WeibullConfig
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
    # KBA FZ 2.2 (Germany). Recognised so the German silver rows can coexist with the rest,
    # but deliberately absent from GEN_LEVEL_SERIES and MODEL_LEVEL_SERIES: the vintages are
    # ingested, not yet scored. Adding it to MODEL_LEVEL_SERIES is what will turn Germany
    # into a model_gen-level series, once mapping/models.csv covers the German labels.
    if "FZ2" in name:
        return "FZ2"
    raise ValueError(f"unknown series for source_file {source_file!r}")


# --------------------------------------------------------------------------- weibull projection

PROJECTION_SCHEMA = {
    "make": pl.Utf8,
    "model_gen": pl.Utf8,
    "generation": pl.Utf8,
    "country": pl.Utf8,
    "horizon": pl.Int32,
    "year": pl.Int32,
    "stock_now": pl.Int64,
    "stock_projected": pl.Int64,
    "low": pl.Int64,
    "high": pl.Int64,
    "k_median": pl.Float64,
    "lambda_median": pl.Float64,
    "cohorts_fitted": pl.Int32,
    "cohorts_total": pl.Int32,
}

# A cohort whose retention climbs by more than this between two observations is being fed
# by imports or re-registrations (SPEC §8 logs those as anomalies): it is not a survival curve.
_RISE_TOLERANCE = 0.05


# Shape grid for the conditional fit: k below 0.3 or above 8 is not a survival curve.
_K_GRID = [0.3 + i * 0.05 for i in range(155)]
# Scale (years) outside this range means the fit found no meaningful decline.
_LAMBDA_YEARS = (2.0, 150.0)


def fit_weibull(ages: list[int], retentions: list[float]) -> tuple[float, float, float] | None:
    """Fit a Weibull survival to a cohort observed from age ``t₀``, not from birth.

    The registers start in 2014, when most cohorts were already ten years old and partly
    gone, so ``retention`` is survival **relative to the first observation**, not to the
    number built. The model is therefore the conditional survival

        R(t) / R(t₀) = exp(−((t/λ)^k − (t₀/λ)^k))

    Fitting the unconditional form instead forces the curve through 1 at age t₀ and returns a
    steep, meaningless ``k ≈ 4`` for every model. For a fixed ``k`` the scale has a closed form
    (least squares through the origin on ``−ln R`` against ``t^k − t₀^k``), so ``k`` is found
    by a fine grid and ``λ`` follows — no numerical optimiser, no new dependency.

    Returns:
        ``(k, λ, s)`` with ``s`` the residual standard deviation of ``ln(−ln R)``, or None with
        fewer than two usable points (``0 < R < 1`` after ``t₀``) or when no decline fits.
    """
    if not ages or ages[0] <= 0:
        return None
    t0 = ages[0]
    r0 = retentions[0]
    if r0 is None or r0 <= 0:
        return None
    pts = [
        (a, -math.log(r / r0))
        for a, r in zip(ages[1:], retentions[1:], strict=True)
        if r is not None and 0 < r < r0 and a > t0
    ]
    if len(pts) < 2:
        return None
    best: tuple[float, float, float] | None = None
    for k in _K_GRID:
        xs = [a**k - t0**k for a, _ in pts]
        sxx = sum(x * x for x in xs)
        if sxx <= 0:
            continue
        inv_lam_k = sum(x * y for x, (_, y) in zip(xs, pts, strict=True)) / sxx
        if inv_lam_k <= 0:
            continue
        sse = sum((y - x * inv_lam_k) ** 2 for x, (_, y) in zip(xs, pts, strict=True))
        if best is None or sse < best[0]:
            best = (sse, k, inv_lam_k)
    if best is None:
        return None
    _, k, inv_lam_k = best
    lam = inv_lam_k ** (-1 / k)
    # A best fit sitting on the grid boundary, or a scale outside a car's lifetime, is not a
    # survival curve — it is noise or a flat series. Report nothing rather than a number.
    if k <= _K_GRID[0] or k >= _K_GRID[-1] or not _LAMBDA_YEARS[0] <= lam <= _LAMBDA_YEARS[1]:
        return None
    resid = [
        math.log(y) - math.log(x * inv_lam_k)
        for x, (_, y) in zip([a**k - t0**k for a, _ in pts], pts, strict=True)
        if y > 0 and x * inv_lam_k > 0
    ]
    n = len(resid)
    s = math.sqrt(sum(r * r for r in resid) / (n - 2)) if n > 2 else 0.0
    return k, lam, s


def _conditional_ratio(k: float, lam: float, t0: int, t: float, shift: float = 0.0) -> float:
    """``R(t)/R(t₀)`` under the fitted Weibull, with ``ln(−ln)`` shifted for the band."""
    h = (t / lam) ** k - (t0 / lam) ** k
    if h <= 0:
        return 1.0
    return math.exp(-math.exp(math.log(h) + shift))


def _settled(ages: list[int], retentions: list[float]) -> tuple[list[int], list[float]] | None:
    """Drop a young cohort's partial first year, then refuse any later rise (imports).

    A cohort first seen the year it was registered is still filling up: its second point can
    legitimately exceed the first. Past that, retention can only fall — a rise above the
    tolerance means imports or re-registrations, and the curve is not a survival curve.
    """
    start = 1 if len(retentions) > 1 and retentions[1] > retentions[0] else 0
    ages, retentions = ages[start:], retentions[start:]
    if any(b > a * (1 + _RISE_TOLERANCE) for a, b in zip(retentions, retentions[1:], strict=False)):
        return None
    return ages, retentions


def weibull_projection(
    cohorts: pl.DataFrame, targets: list[TargetModel], cfg: WeibullConfig
) -> pl.DataFrame:
    """Project each target's national stock ``horizon`` years ahead from its cohort curves.

    Per (target, country, cohort): fit a Weibull on the retention curve, then scale the
    cohort's current stock by ``R(age + h) / R(age)``. Cohorts too short to fit, or whose
    retention rises (imports), are left out and counted, never imputed. The band is the same
    projection with the linearised fit shifted by ±2 residual standard deviations: an
    **indicative** interval, not a formal confidence interval, and the page says so.

    A projection is a statistical extrapolation of what the registers already show; it is
    published beside the score and never enters it.

    Returns:
        One row per (target, country, horizon) with at least ``cfg.min_cohorts`` fitted
        cohorts; ``stock_now`` is the current stock of the fitted cohorts only, so that
        ``stock_projected / stock_now`` reads as a ratio over the same population.
    """
    if not cohorts.height or not targets:
        return pl.DataFrame(schema=PROJECTION_SCHEMA)
    wanted = {(t.make, t.model_gen, t.generation) for t in targets}
    rows: list[dict] = []
    keys = ["make", "model_gen", "generation", "country"]
    for key, group in cohorts.sort("cohort", "year").group_by(keys, maintain_order=True):
        make, model_gen, generation, country = key  # type: ignore[misc]
        if (make, model_gen, generation) not in wanted:
            continue
        fitted: list[tuple[float, float, float, int, int, int]] = []  # k, lam, s, age, stock, yr
        total = 0
        for _, c in group.group_by("cohort", maintain_order=True):
            total += 1
            keep = [i for i, r in enumerate(c["retention"].to_list()) if r is not None and r > 0]
            if len(keep) < cfg.min_points:
                continue
            ages = [int(a) for a in (c["year"] - c["cohort"]).gather(keep).to_list()]
            rets = [float(r) for r in c["retention"].gather(keep).to_list()]
            settled = _settled(ages, rets)
            if settled is None or len(settled[0]) < cfg.min_points:
                continue
            fit = fit_weibull(*settled)
            if fit is None:
                continue
            fitted.append((*fit, ages[-1], int(c["stock"][-1]), int(c["year"][-1])))
        if len(fitted) < cfg.min_cohorts:
            continue
        latest_year = max(f[5] for f in fitted)
        ks = sorted(f[0] for f in fitted)
        lams = sorted(f[1] for f in fitted)
        for h in cfg.horizons:
            now = proj = low = high = 0.0
            for k, lam, s, age, stock, _ in fitted:
                # survival from today's age to age + h, conditional on being alive today
                now += stock
                proj += stock * _conditional_ratio(k, lam, age, age + h)
                # +2s on ln(-ln R) means a larger -ln R, i.e. a lower retention
                low += stock * _conditional_ratio(k, lam, age, age + h, +2 * s)
                high += stock * _conditional_ratio(k, lam, age, age + h, -2 * s)
            rows.append(
                {
                    "make": make,
                    "model_gen": model_gen,
                    "generation": generation,
                    "country": country,
                    "horizon": h,
                    "year": latest_year + h,
                    "stock_now": round(now),
                    "stock_projected": round(proj),
                    "low": round(low),
                    "high": round(high),
                    "k_median": ks[len(ks) // 2],
                    "lambda_median": lams[len(lams) // 2],
                    "cohorts_fitted": len(fitted),
                    "cohorts_total": total,
                }
            )
    if not rows:
        return pl.DataFrame(schema=PROJECTION_SCHEMA)
    return pl.DataFrame(rows, schema=PROJECTION_SCHEMA).sort(keys + ["horizon"])


# --------------------------------------------------------------------------- annual series


# Series that describe a national fleet at model_gen level only, with no year of first
# registration: they cannot be split by generation, so they inform but never score.
REFERENCE_SERIES = ("FZ2",)

REFERENCE_SCHEMA = {
    "make": pl.Utf8,
    "model_gen": pl.Utf8,
    "country": pl.Utf8,
    "series": pl.Utf8,
    "year": pl.Int32,
    "stock": pl.Int64,
    "target_generations": pl.Int32,
}


def reference_stock(stock: pl.DataFrame, targets: list[TargetModel]) -> pl.DataFrame:
    """Annual national stock per (make, model_gen) for the series that cannot be scored.

    Germany (KBA FZ 2.2) publishes its fleet by trade name with **no first-registration year**,
    so a model's stock cannot be split between its generations. Feeding it to the score would
    bias the ranking: only the 23 % of targets that are the sole target generation of their
    model would gain German vehicles, and rarity — 35 % of the score — is computed by comparing
    targets to one another. An Audi S3 would look far less rare than an RS4 B5 because we have
    more data on it, not because it is.

    So the figure is published alongside the score, never inside it, with the number of target
    generations it covers so the page can say what it does and does not mean.

    The whole series is published, not just its last point: the German vintages are annual
    and consecutive since 2019, so the page can show how a model's national fleet moved even
    though that movement cannot be attributed to one generation.

    Returns:
        One row per (make, model_gen, country, year) present in both the targets and the
        reference series.
    """
    if not targets:
        return pl.DataFrame(schema=REFERENCE_SCHEMA)
    counts: dict[tuple[str, str], int] = {}
    for target in targets:
        counts[(target.make, target.model_gen)] = counts.get((target.make, target.model_gen), 0) + 1
    wanted = pl.DataFrame(
        [
            {"make": make, "model_gen": model_gen, "target_generations": n}
            for (make, model_gen), n in counts.items()
        ],
        schema={"make": pl.Utf8, "model_gen": pl.Utf8, "target_generations": pl.Int32},
    )
    rows = (
        stock.filter(pl.col("model_gen").is_not_null())
        .with_columns(
            pl.col("source_file").map_elements(series_of, return_dtype=pl.Utf8).alias("series")
        )
        .filter(pl.col("series").is_in(REFERENCE_SERIES))
    )
    if not rows.height:
        return pl.DataFrame(schema=REFERENCE_SCHEMA)
    keys = ["make", "model_gen", "country", "series"]
    annual = (
        rows.with_columns(pl.col("period").dt.year().alias("year"))
        .group_by(*keys, "year")
        .agg(pl.col("count").sum().alias("stock"))
    )
    return (
        annual.join(wanted, on=["make", "model_gen"], how="inner")
        .select(list(REFERENCE_SCHEMA))
        .cast(REFERENCE_SCHEMA)
        .sort("make", "model_gen", "country", "year")
    )


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


def rarity_tier_expr(stock: pl.Expr, thresholds: list[int]) -> pl.Expr:
    """Column version of :func:`rarity_tier`: the label of ``stock`` for every row."""
    expr: pl.Expr = pl.lit(f">={max(thresholds)}")
    for t in sorted(thresholds, reverse=True):
        expr = pl.when(stock < t).then(pl.lit(f"<{t}")).otherwise(expr)
    return expr


def aggregate_europe(indicators: pl.DataFrame, thresholds: list[int]) -> pl.DataFrame:
    """One row per target: stock summed over countries, attrition stock-weighted, SORN from GB,
    inflection = the most recent country inflection, survival stock-weighted, rarity tier from
    the summed stock (``thresholds`` = ``rarity.thresholds``).

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
        .with_columns(rarity_tier_expr(pl.col("stock"), thresholds).alias("rarity_tier"))
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
