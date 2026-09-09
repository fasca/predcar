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
