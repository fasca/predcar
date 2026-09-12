import re
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from test_metrics import _population

from predcar import score as sc
from predcar import site
from predcar.config import load_score_config
from predcar.paths import DOCS_DIR, SITE_DIR

CFG = load_score_config()


@pytest.fixture(scope="module")
def gold(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Gold tables of the synthetic population, plus the matching target list."""
    stock, new_reg, targets = _population()
    root = tmp_path_factory.mktemp("gold")
    silver, gold_dir, mapping = root / "silver", root / "gold", root / "mapping"
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
    sc.score(silver, gold_dir, mapping, CFG)
    return gold_dir, mapping


def _build(gold: tuple[Path, Path], out: Path) -> dict[str, Path]:
    return site.build(
        gold[0],
        out,
        gold[1],
        SITE_DIR / "templates",
        SITE_DIR / "static",
        DOCS_DIR / "methodology.md",
        CFG,
        built_on=date(2026, 9, 9),
    )


def test_slugify() -> None:
    assert site.slugify("ALFA ROMEO", "147 GTA", "937") == "alfa-romeo-147-gta-937"
    assert site.slugify("CITROËN", "SAXO VTS", "MK1/MK2") == "citroen-saxo-vts-mk1-mk2"


def test_formatters_are_french_and_null_safe() -> None:
    assert site.fmt_int(12345) == "12\u202f345"  # narrow no-break space
    assert site.fmt_pct(0.0523) == "5,2\u202f%"
    assert site.fmt_num(0.4783, 3) == "0,478"
    assert site.fmt_int(None) == site.fmt_pct(None) == site.fmt_num(None) == "—"


def test_build_renders_every_page(gold: tuple[Path, Path], tmp_path: Path) -> None:
    written = _build(gold, tmp_path / "dist")
    scores = pl.read_parquet(gold[0] / "scores.parquet")
    index = written["index"].read_text(encoding="utf-8")
    published = scores.filter(pl.col("score").is_not_null())
    # every target with data has a page; the ranking table lists published rows only
    pages = sorted(p.name for p in written["models"].glob("*.html"))
    assert len(pages) == scores.height
    for r in published.iter_rows(named=True):
        slug = site.slugify(r["make"], r["model_gen"], r["generation"])
        assert f"{slug}.html" in index
        page = (written["models"] / f"{slug}.html").read_text(encoding="utf-8")
        assert f"Rang <strong>{r['rank']}</strong>" in page
        assert "chart-stock" in page and '"stock": [' in page
        assert "2026-09-09" in page
    assert index.count("<tr data-segment") == published.height
    assert "Top 50 seulement" in index and 'id="f-segment"' in index
    # the methodology page carries the config values and the rendered markdown
    methodology = written["methodology"].read_text(encoding="utf-8")
    assert "<table>" in methodology and "0,35" in methodology
    assert "Kaplan-Meier" in methodology
    assert written["ranking_csv"].is_file()
    assert (tmp_path / "dist" / ".nojekyll").is_file()
    assert (tmp_path / "dist" / "static" / "app.js").is_file()


def test_unpublished_target_has_page_but_no_rank(gold: tuple[Path, Path], tmp_path: Path) -> None:
    written = _build(gold, tmp_path / "dist")
    scores = pl.read_parquet(gold[0] / "scores.parquet")
    unpublished = scores.filter(pl.col("score").is_null())
    assert unpublished.height > 0, "the synthetic population should contain an unpublished target"
    r = unpublished.row(0, named=True)
    slug = site.slugify(r["make"], r["model_gen"], r["generation"])
    page = (written["models"] / f"{slug}.html").read_text(encoding="utf-8")
    assert "Score non publié" in page
    ranking_table, unpublished_list = written["index"].read_text(encoding="utf-8").split("<details")
    assert f"{slug}.html" not in ranking_table
    assert f"{slug}.html" in unpublished_list


def test_build_rejects_missing_gold(tmp_path: Path) -> None:
    with pytest.raises(site.SiteError, match="predcar score"):
        site.build(tmp_path / "nowhere", tmp_path / "dist")


def test_embedded_json_cannot_close_the_script_tag(gold: tuple[Path, Path], tmp_path: Path) -> None:
    written = _build(gold, tmp_path / "dist")
    for page in written["models"].glob("*.html"):
        body = page.read_text(encoding="utf-8")
        payload = body.split('<script id="charts-data" type="application/json">')[1]
        assert "</" not in payload.split("</script>")[0]


def test_model_page_cites_the_sales_series_behind_survival(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    written = _build(gold, tmp_path / "dist")
    indicators = pl.read_parquet(gold[0] / "indicators.parquet")
    with_sales = indicators.filter(pl.col("cumulative_sales").is_not_null()).row(0, named=True)
    # a target without sales in any country, so its page must not cite VEH0160 at all
    without = (
        indicators.group_by("make", "model_gen", "generation")
        .agg(pl.col("cumulative_sales").is_null().all().alias("no_sales"))
        .filter(pl.col("no_sales"))
        .row(0, named=True)
    )
    for r, expected in ((with_sales, True), (without, False)):
        slug = site.slugify(r["make"], r["model_gen"], r["generation"])
        page = (written["models"] / f"{slug}.html").read_text(encoding="utf-8")
        assert ("DfT VEH0160" in page) is expected


# ----------------------------------------------------------------- building from a bundle


def _bundle(root: Path, day: str, gold_dir: Path, *, complete: bool = True) -> Path:
    """Write a ``reports/<day>/gold/`` bundle of CSVs, as ``predcar export`` does."""
    out = root / day / "gold"
    out.mkdir(parents=True)
    # export.py exports every gold/*.parquet, cohorts.parquet included.
    for parquet in sorted(gold_dir.glob("*.parquet")):
        name = parquet.stem
        df = pl.read_parquet(parquet)
        # export.py joins list columns with "|" — CSV has no nested type.
        lists = [c for c, dt in df.schema.items() if dt == pl.List(pl.String)]
        df.with_columns(pl.col(c).list.join("|") for c in lists).write_csv(out / f"{name}.csv")
    if complete:
        (out / "ranking.csv").write_text("rank,make\n1,X\n", encoding="utf-8")
    return out


def test_resolve_gold_dir_picks_the_latest_complete_bundle(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    """A newer bundle whose score step failed must not shadow the last usable one."""
    reports = tmp_path / "reports"
    _bundle(reports, "2026-06-30", gold[0])
    _bundle(reports, "2026-09-12", gold[0], complete=False)  # no gold/ranking.csv
    (reports / "not-a-date").mkdir()

    resolved, bundle_date = site.resolve_gold_dir(None, reports)
    assert resolved == reports / "2026-06-30" / "gold"
    assert bundle_date == date(2026, 6, 30)


def test_resolve_gold_dir_without_any_bundle_says_what_to_run(tmp_path: Path) -> None:
    with pytest.raises(site.SiteError, match="make export"):
        site.resolve_gold_dir(None, tmp_path / "reports")


def test_build_from_a_csv_bundle_matches_the_parquet_build(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    """The CSV of a bundle and the Parquet of a run must render the same pages."""
    reports = tmp_path / "reports"
    _bundle(reports, "2026-09-12", gold[0])
    from_parquet = tmp_path / "from-parquet"
    from_csv = tmp_path / "from-csv"
    _build(gold, from_parquet)
    site.build(
        None,
        from_csv,
        gold[1],
        SITE_DIR / "templates",
        SITE_DIR / "static",
        DOCS_DIR / "methodology.md",
        CFG,
        built_on=date(2026, 9, 9),
        reports_dir=reports,
    )
    pages = sorted(p.name for p in (from_parquet / "modeles").iterdir())
    assert pages == sorted(p.name for p in (from_csv / "modeles").iterdir())
    for name in ("index.html", *pages[:3]):
        rel = name if name == "index.html" else f"modeles/{name}"
        assert (from_parquet / rel).read_text() == (from_csv / rel).read_text(), rel


def test_bundle_date_is_the_refresh_date(gold: tuple[Path, Path], tmp_path: Path) -> None:
    """SPEC §6 asks for the date of the data, not the date of the rendering run."""
    reports = tmp_path / "reports"
    _bundle(reports, "2026-09-12", gold[0])
    out = tmp_path / "dist"
    site.build(
        None,
        out,
        gold[1],
        SITE_DIR / "templates",
        SITE_DIR / "static",
        DOCS_DIR / "methodology.md",
        CFG,
        reports_dir=reports,
    )
    assert "2026-09-12" in (out / "index.html").read_text(encoding="utf-8")


def test_csv_reading_never_imputes_a_missing_component_as_zero(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    """An empty CSV field is null; a 0 would silently enter the weighted score."""
    reports = tmp_path / "reports"
    bundle = _bundle(reports, "2026-09-12", gold[0])
    scores = site._read_table(bundle, "scores")
    reference = pl.read_parquet(gold[0] / "scores.parquet")
    for column in ("score", "conservation", "relative_attrition", "inflection_year"):
        assert scores[column].null_count() == reference[column].null_count(), column
    assert scores.schema["components_available"] == pl.List(pl.String)


def test_no_page_links_to_an_absolute_path(gold: tuple[Path, Path], tmp_path: Path) -> None:
    """GitHub Pages serves the site under /<repo>/: absolute paths would 404 there."""
    out = tmp_path / "dist"
    _build(gold, out)
    pattern = re.compile(r'(?:href|src)="/')
    for page in [out / "index.html", out / "methodologie.html", *(out / "modeles").iterdir()]:
        assert not pattern.search(page.read_text(encoding="utf-8")), page.name


def test_single_observation_cohort_is_named_not_drawn_at_100_percent() -> None:
    """A lone point normalized by itself reads 100 % — "nothing lost yet". Never drawn."""
    cohorts = pl.DataFrame(
        {
            "country": ["GB", "GB", "NL"],
            "series": ["VEH0124", "VEH0124", "RDW"],
            "cohort": [2003, 2003, 2003],
            "year": [2024, 2025, 2026],
            "retention": [1.0, 0.9, 1.0],
        }
    )
    traces, skipped = site._cohort_traces(cohorts)
    assert [t["label"] for t in traces] == ["Royaume-Uni 2003"]
    assert skipped == ["Pays-Bas (RDW)"]
    assert all(len(t["years"]) >= 2 for t in traces)


def test_csv_identity_columns_survive_numeric_looking_model_names(tmp_path: Path) -> None:
    """ "147" then "147 GTA": type inference reads the first rows as integers and then fails.

    This is the CSV twin of the mapping lesson about numeric labels (205 GTI, 306 S16, 911).
    """
    gold = tmp_path / "gold"
    gold.mkdir()
    rows = [{"make": "ALFA ROMEO", "model_gen": "147", "generation": "937", "stock": 10}] * 120
    rows.append({"make": "ALFA ROMEO", "model_gen": "147 GTA", "generation": "937", "stock": 3})
    pl.DataFrame(rows).write_csv(gold / "cohorts.csv")

    df = site._read_table(gold, "cohorts")
    assert df.schema["model_gen"] == pl.String
    assert df["model_gen"].to_list()[-1] == "147 GTA"
