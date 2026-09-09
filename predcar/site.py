"""Static site generator (SPEC §6): ranking, one page per target, methodology, CSV export.

Everything is rendered from ``data/gold/`` only (never from silver or raw), with Jinja2
templates in ``site/templates/`` and static assets in ``site/static/``. Charts use Plotly.js
loaded from its CDN; the data of every chart is embedded in the page as JSON so the site is
fully static and hostable on GitHub Pages.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import markdown
import polars as pl
from jinja2 import Environment, FileSystemLoader, select_autoescape

from predcar import metrics
from predcar.config import ScoreConfig, load_score_config
from predcar.normalize import TARGETS_FILE, TargetModel, load_targets
from predcar.paths import DOCS_DIR, GOLD_DIR, MAPPING_DIR, SITE_DIR, SITE_DIST_DIR
from predcar.score import COMPONENTS

logger = logging.getLogger(__name__)

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"
MODELS_DIR = "modeles"

COMPONENT_LABELS = {
    "rarity": "Rareté",
    "conservation": "Conservation",
    "sorn_ratio": "Ratio SORN",
    "recent_inflection_point": "Inflexion récente",
}
COMPONENT_SHORT = {
    "rarity": "R",
    "conservation": "C",
    "sorn_ratio": "SORN",
    "recent_inflection_point": "Infl.",
}
# scores.parquet column carrying the normalized 0–1 value of each component
COMPONENT_COLUMNS = {
    "rarity": "rarity",
    "conservation": "conservation",
    "sorn_ratio": "sorn_ratio_c",
    "recent_inflection_point": "recent_inflection_point",
}
COUNTRY_LABELS = {"GB": "Royaume-Uni", "NL": "Pays-Bas", metrics.EUROPE: "Europe"}
SERIES_INFO = {
    "VEH0120": {
        "name": "DfT VEH0120",
        "detail": "parc trimestriel par modèle générique, Licensed / SORN",
        "url": "https://www.gov.uk/government/statistical-data-sets/"
        "vehicle-licensing-statistics-data-files",
        "licence": "OGL v3",
    },
    "VEH0124": {
        "name": "DfT VEH0124",
        "detail": "parc annuel par année de première immatriculation et de fabrication",
        "url": "https://www.gov.uk/government/statistical-data-sets/"
        "vehicle-licensing-statistics-data-files",
        "licence": "OGL v3",
    },
    "VEH0160": {
        "name": "DfT VEH0160",
        "detail": "immatriculations neuves trimestrielles",
        "url": "https://www.gov.uk/government/statistical-data-sets/"
        "vehicle-licensing-statistics-data-files",
        "licence": "OGL v3",
    },
    "RDW": {
        "name": "RDW « Gekentekende voertuigen » (m9d7-ebf2)",
        "detail": "snapshot mensuel agrégé côté API, jamais par véhicule",
        "url": "https://opendata.rdw.nl/resource/m9d7-ebf2.json",
        "licence": "CC0",
    },
}


class SiteError(RuntimeError):
    """The site cannot be built (missing gold tables)."""


# --------------------------------------------------------------------------- formatting


def slugify(*parts: str) -> str:
    """URL-safe identifier of a target: ``bmw-m3-e46``."""
    text = "-".join(parts).lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-")


def fmt_int(value: float | int | None) -> str:
    """``12345`` → ``12 345`` (narrow no-break space); ``—`` when null."""
    if value is None:
        return "—"
    return f"{int(round(value)):,}".replace(",", " ")


def fmt_pct(value: float | None, digits: int = 1) -> str:
    """``0.0523`` → ``5,2 %``; ``—`` when null."""
    if value is None:
        return "—"
    return f"{100 * value:.{digits}f}".replace(".", ",") + " %"


def fmt_num(value: float | None, digits: int = 2) -> str:
    """Decimal with a French comma; ``—`` when null."""
    if value is None:
        return "—"
    return f"{value:.{digits}f}".replace(".", ",")


def fmt_year(value: int | None) -> str:
    return "—" if value is None else str(int(value))


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class Gold:
    """The gold tables a site build reads."""

    scores: pl.DataFrame
    indicators: pl.DataFrame
    series: pl.DataFrame
    cohorts: pl.DataFrame
    targets: dict[tuple[str, str, str], TargetModel]


def load_gold(gold_dir: Path, mapping_dir: Path) -> Gold:
    """Read ``data/gold/`` (``cohorts.parquet`` optional) and the target list."""
    paths = {n: gold_dir / f"{n}.parquet" for n in ("scores", "indicators", "stock_series")}
    missing = [str(p) for p in paths.values() if not p.is_file()]
    if missing:
        raise SiteError(f"missing gold tables {missing}: run `predcar score` first")
    cohorts_path = gold_dir / "cohorts.parquet"
    cohorts = (
        pl.read_parquet(cohorts_path)
        if cohorts_path.is_file()
        else pl.DataFrame(schema=metrics._COHORTS_SCHEMA)
    )
    targets = {
        (t.make, t.model_gen, t.generation): t for t in load_targets(mapping_dir / TARGETS_FILE)
    }
    return Gold(
        scores=pl.read_parquet(paths["scores"]),
        indicators=pl.read_parquet(paths["indicators"]),
        series=pl.read_parquet(paths["stock_series"]),
        cohorts=cohorts,
        targets=targets,
    )


def _key(row: dict) -> tuple[str, str, str]:
    return (row["make"], row["model_gen"], row["generation"])


def _decade(target: TargetModel | None) -> int | None:
    return None if target is None else (target.year_from // 10) * 10


def _components(row: dict, cfg: ScoreConfig) -> list[dict]:
    """Every score component with its weight, value and contribution — the *why*."""
    weights = cfg.weights.as_dict()
    out = []
    for name in COMPONENTS:
        value = row.get(COMPONENT_COLUMNS[name])
        out.append(
            {
                "name": name,
                "label": COMPONENT_LABELS[name],
                "short": COMPONENT_SHORT[name],
                "weight": weights[name],
                "value": value,
                "available": value is not None,
            }
        )
    coverage = row.get("weight_coverage") or 0.0
    for c in out:
        c["contribution"] = (
            c["value"] * c["weight"] / coverage if c["available"] and coverage else None
        )
    return out


def ranking_rows(gold: Gold, cfg: ScoreConfig) -> list[dict]:
    """One dict per scored target (published or not), sorted by rank then name."""
    countries = (
        gold.indicators.filter(pl.col("country") != metrics.EUROPE)
        .group_by(metrics.TARGET_KEY)
        .agg(pl.col("country").unique().sort().alias("countries"))
    )
    lookup = {_key(r): r["countries"] for r in countries.iter_rows(named=True)}
    rows = []
    for r in gold.scores.sort("rank", "make", "model_gen", "generation", nulls_last=True).iter_rows(
        named=True
    ):
        target = gold.targets.get(_key(r))
        rows.append(
            {
                **r,
                "slug": slugify(*_key(r)),
                "target": target,
                "decade": _decade(target),
                "countries": lookup.get(_key(r), []),
                "components": _components(r, cfg),
                "published": r["score"] is not None,
            }
        )
    return rows


def _series_traces(series: pl.DataFrame, column: str) -> list[dict]:
    traces = []
    for country in sorted(series["country"].unique().to_list()):
        df = series.filter((pl.col("country") == country) & pl.col(column).is_not_null())
        df = df.sort("year")
        if not df.height:
            continue
        traces.append(
            {
                "country": country,
                "label": COUNTRY_LABELS.get(country, country),
                "series": df["series"][0],
                "level": df["level"][0],
                "years": df["year"].to_list(),
                "values": df[column].to_list(),
            }
        )
    return traces


def _cohort_traces(cohorts: pl.DataFrame) -> list[dict]:
    """Retention curves by (country, cohort) with at least two observations."""
    traces = []
    grouped = cohorts.group_by("country", "cohort").agg(
        pl.col("year").sort().alias("years"),
        pl.col("retention").sort_by("year").alias("values"),
        pl.col("series").first(),
    )
    for r in grouped.sort("country", "cohort").iter_rows(named=True):
        if len(r["years"]) < 2:
            continue
        traces.append(
            {
                "country": r["country"],
                "label": f"{COUNTRY_LABELS.get(r['country'], r['country'])} {r['cohort']}",
                "years": r["years"],
                "values": r["values"],
            }
        )
    return traces


def model_context(row: dict, gold: Gold, cfg: ScoreConfig) -> dict:
    """Everything the model page shows for one target."""
    key = _key(row)
    match = (
        (pl.col("make") == key[0])
        & (pl.col("model_gen") == key[1])
        & (pl.col("generation") == key[2])
    )
    indicators = gold.indicators.filter(match)
    series = gold.series.filter(match)
    cohorts = gold.cohorts.filter(match)
    by_country = [
        {
            **r,
            "label": COUNTRY_LABELS.get(r["country"], r["country"]),
            "peer_median": (
                r["attrition"] - r["relative_attrition"]
                if r["attrition"] is not None and r["relative_attrition"] is not None
                else None
            ),
        }
        for r in indicators.filter(pl.col("country") != metrics.EUROPE)
        .sort("country")
        .iter_rows(named=True)
    ]
    sources = []
    for c in by_country:
        cited = set(c["series"].split("+"))
        # cumulative sales (survival denominator) come from VEH0160, not from the stock series
        if c["cumulative_sales"] is not None:
            cited.add(metrics.SALES_SERIES)
        for s in sorted(cited):
            info = SERIES_INFO.get(s, {"name": s, "detail": "", "url": "", "licence": ""})
            sources.append({**info, "country": c["label"], "latest_year": c["latest_year"]})
    charts = {
        "stock": _series_traces(series, "stock"),
        "attrition": _series_traces(series, "attrition"),
        "retention": _cohort_traces(cohorts),
    }
    return {
        "row": row,
        "target": row["target"],
        "by_country": by_country,
        "sources": sources,
        "charts_json": json.dumps(charts, ensure_ascii=False).replace("</", "<\\/"),
        "has_retention": bool(charts["retention"]),
        "min_weight_coverage": cfg.min_weight_coverage,
    }


# --------------------------------------------------------------------------- rendering


def _environment(templates_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        {"fmt_int": fmt_int, "fmt_pct": fmt_pct, "fmt_num": fmt_num, "fmt_year": fmt_year}
    )
    return env


def render_methodology(path: Path) -> str:
    """``docs/methodology.md`` → HTML fragment (tables and fenced code supported)."""
    text = path.read_text(encoding="utf-8")
    # The document's H1 is rendered by the page template
    text = re.sub(r"\A# .*\n", "", text)
    return markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])


def build(
    gold_dir: Path = GOLD_DIR,
    out_dir: Path = SITE_DIST_DIR,
    mapping_dir: Path = MAPPING_DIR,
    templates_dir: Path = SITE_DIR / "templates",
    static_dir: Path = SITE_DIR / "static",
    methodology_path: Path = DOCS_DIR / "methodology.md",
    cfg: ScoreConfig | None = None,
    built_on: date | None = None,
) -> dict[str, Path]:
    """Render the whole site into ``out_dir`` (emptied first).

    Returns:
        Paths of the entry points: ``index``, ``methodology``, ``ranking_csv`` and the
        ``models`` directory.
    """
    cfg = cfg or load_score_config()
    built_on = built_on or date.today()
    gold = load_gold(gold_dir, mapping_dir)
    rows = ranking_rows(gold, cfg)
    env = _environment(templates_dir)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / MODELS_DIR).mkdir(parents=True)
    shutil.copytree(static_dir, out_dir / "static")
    (out_dir / ".nojekyll").touch()

    latest_year = gold.indicators["latest_year"].max() if gold.indicators.height else None
    base = {
        "built_on": built_on,
        "latest_year": latest_year,
        "plotly_cdn": PLOTLY_CDN,
        "models_dir": MODELS_DIR,
        "weights": cfg.weights.as_dict(),
        "component_labels": COMPONENT_LABELS,
        "country_labels": COUNTRY_LABELS,
        "cfg": cfg,
    }
    published = [r for r in rows if r["published"]]
    unpublished = [r for r in rows if not r["published"]]
    (out_dir / "index.html").write_text(
        env.get_template("index.html").render(
            **base,
            root="./",
            rows=published,
            unpublished=unpublished,
            segments=sorted({r["segment"] for r in rows}),
            decades=sorted({r["decade"] for r in rows if r["decade"] is not None}),
            countries=sorted({c for r in rows for c in r["countries"]}),
        ),
        encoding="utf-8",
    )
    template = env.get_template("model.html")
    for r in rows:
        (out_dir / MODELS_DIR / f"{r['slug']}.html").write_text(
            template.render(**base, root="../", **model_context(r, gold, cfg)), encoding="utf-8"
        )
    (out_dir / "methodologie.html").write_text(
        env.get_template("methodology.html").render(
            **base, root="./", body=render_methodology(methodology_path)
        ),
        encoding="utf-8",
    )
    ranking_csv = gold_dir / "ranking.csv"
    if ranking_csv.is_file():
        shutil.copy(ranking_csv, out_dir / "ranking.csv")
    logger.info("site built in %s: %d targets, %d published", out_dir, len(rows), len(published))
    return {
        "index": out_dir / "index.html",
        "methodology": out_dir / "methodologie.html",
        "ranking_csv": out_dir / "ranking.csv",
        "models": out_dir / MODELS_DIR,
    }
