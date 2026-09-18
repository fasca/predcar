import re
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from test_metrics import _population

from predcar import metrics, site
from predcar import score as sc
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
    # split on the unpublished block itself: the page carries other <details> sections
    index = written["index"].read_text(encoding="utf-8")
    ranking_table, unpublished_list = index.split('<details class="unpublished"')
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
        real = gold_dir / "ranking.csv"
        if real.is_file():
            (out / "ranking.csv").write_bytes(real.read_bytes())
        else:
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


def test_ranking_page_explains_how_to_read_it(gold: tuple[Path, Path], tmp_path: Path) -> None:
    """A ranking without the sign and scale of its columns is not readable.

    Every column of the table must be named in the help block, and the component legend must
    use the very same short labels as the bars, or the legend explains nothing.
    """
    out = tmp_path / "dist"
    _build(gold, out)
    index = (out / "index.html").read_text(encoding="utf-8")

    assert "Comment lire ce tableau" in index
    for column in ("Rang", "Années", "Pays", "Parc", "Attrition/an", "Score", "Composantes"):
        assert f"<dt>{column}</dt>" in index, column
    # the sign of attrition is the one thing a reader cannot guess
    assert "négative" in index and "le parc augmente" in index
    # a missing component is excluded, never counted as zero — said on the page, not only in docs
    assert "jamais comptée 0" in index

    legend = re.search(r"howto-legend.*?</ul>", index, re.S)
    assert legend is not None
    row = re.search(r'<td class="components">.*?</td>', index, re.S)
    assert row is not None
    bars = re.findall(r'class="lbl">([^<]*)<', row.group(0))
    legend_labels = re.findall(r'class="lbl">([^<]*)<', legend.group(0))
    assert bars, "no component bar in the table"
    assert set(bars) <= set(legend_labels), (bars, legend_labels)


def test_every_ranking_column_header_carries_a_tooltip(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    """Hovering a header is the shortest path to its meaning; only Modèle is self-evident."""
    out = tmp_path / "dist"
    _build(gold, out)
    index = (out / "index.html").read_text(encoding="utf-8")
    table = re.search(r'<table id="ranking".*?</thead>', index, re.S)
    assert table is not None
    headers = re.findall(r"<th\b([^>]*)>([^<]*)</th>", table.group(0))
    untitled = [label for attrs, label in headers if "title=" not in attrs]
    assert untitled == ["Modèle"], untitled


def test_model_page_says_what_the_peer_median_is_for(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    """The per-country table is a comparison; without that, its numbers are just numbers."""
    out = tmp_path / "dist"
    _build(gold, out)
    page = next((out / "modeles").iterdir()).read_text(encoding="utf-8")
    assert "Médiane des pairs" in page
    assert "même segment et du même âge" in page


def test_model_page_marks_the_national_reference_as_outside_the_score(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    """Showing a national fleet without saying it is excluded would mislead.

    The German fleet cannot be split by generation, so it is published beside the score. The
    page must say so, and say how many generations the figure covers.
    """
    gold_dir, mapping = gold
    reference = pl.DataFrame(
        {
            "make": ["M"],
            "model_gen": [pl.read_parquet(gold_dir / "scores.parquet")["model_gen"][0]],
            "country": ["DE"],
            "series": ["FZ2"],
            "year": [2026],
            "stock": [12345],
            "target_generations": [3],
        },
        schema=metrics.REFERENCE_SCHEMA,
    )
    reference.write_parquet(gold_dir / "reference_stock.parquet")
    out = tmp_path / "dist"
    try:
        _build(gold, out)
        pages = "\n".join(p.read_text(encoding="utf-8") for p in (out / "modeles").iterdir())
    finally:
        (gold_dir / "reference_stock.parquet").unlink()
    flat = re.sub(r"\s+", " ", pages)
    assert "Parc national, hors score" in flat
    assert "n'entrent ni dans l'attrition, ni dans le score" in flat
    assert "Allemagne" in flat and "KBA FZ 2.2" in flat
    assert "modèle complet, sans répartition vérifiable" in flat
    assert "3 générations cibles dans le périmètre" in flat
    assert ">cette génération</td>" not in flat


def test_score_table_scrolls_inside_its_card_on_mobile(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    out = tmp_path / "dist"
    _build(gold, out)
    page = next((out / "modeles").iterdir()).read_text(encoding="utf-8")
    assert '<div class="table-wrap">\n  <table class="components-table">' in page


def test_model_page_has_no_reference_section_without_the_table(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    out = tmp_path / "dist"
    _build(gold, out)
    pages = "\n".join(p.read_text(encoding="utf-8") for p in (out / "modeles").iterdir())
    assert "Parc national, hors score" not in pages


def test_reference_section_shows_the_trend_over_the_series(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    """Eight consecutive German vintages: the page shows the move, not just the last point."""
    gold_dir, _ = gold
    model = pl.read_parquet(gold_dir / "scores.parquet")["model_gen"][0]
    pl.DataFrame(
        {
            "make": ["M", "M"],
            "model_gen": [model, model],
            "country": ["DE", "DE"],
            "series": ["FZ2", "FZ2"],
            "year": [2019, 2026],
            "stock": [1000, 1250],
            "target_generations": [1, 1],
        },
        schema=metrics.REFERENCE_SCHEMA,
    ).write_parquet(gold_dir / "reference_stock.parquet")
    out = tmp_path / "dist"
    try:
        _build(gold, out)
        pages = "\n".join(p.read_text(encoding="utf-8") for p in (out / "modeles").iterdir())
    finally:
        (gold_dir / "reference_stock.parquet").unlink()
    flat = re.sub(r"\s+", " ", pages)
    assert "1 250" in flat  # the latest point, French thousands separator
    assert "+25,0 % depuis 2019" in flat


def _projection_frame(model: str, horizons: list[int]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "make": ["M"] * len(horizons),
            "model_gen": [model] * len(horizons),
            "generation": ["G1"] * len(horizons),
            "country": ["GB"] * len(horizons),
            "horizon": horizons,
            "year": [2026 + h for h in horizons],
            "stock_now": [1000] * len(horizons),
            "stock_projected": [700, 450][: len(horizons)],
            "low": [500, 250][: len(horizons)],
            "high": [850, 650][: len(horizons)],
            "k_median": [1.2] * len(horizons),
            "lambda_median": [18.5] * len(horizons),
            "cohorts_fitted": [4] * len(horizons),
            "cohorts_total": [6] * len(horizons),
        },
        schema=metrics.PROJECTION_SCHEMA,
    )


def test_model_page_shows_the_projection_and_says_it_is_outside_the_score(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    """A projection shown without its caveats would read as a forecast of value."""
    gold_dir, _ = gold
    scores = pl.read_parquet(gold_dir / "scores.parquet")
    row = scores.filter(pl.col("generation") == "G1").row(0, named=True)
    _projection_frame(row["model_gen"], [5, 10]).write_parquet(gold_dir / "projection.parquet")
    out = tmp_path / "dist"
    try:
        _build(gold, out)
        page = (out / "modeles" / f"{site.slugify('M', row['model_gen'], 'G1')}.html").read_text(
            encoding="utf-8"
        )
    finally:
        (gold_dir / "projection.parquet").unlink()
    flat = re.sub(r"\s+", " ", page)
    assert "Projection à 5 et 10 ans" in flat
    assert "ni une prédiction de valeur, ni une composante du score" in flat
    assert "2031 (+5)" in flat and "700" in flat and "500 – 850" in flat
    assert "-30,0 %" in flat and "4 / 6" in flat


def test_model_page_explains_an_absent_projection(gold: tuple[Path, Path], tmp_path: Path) -> None:
    """No table, but the reader learns why: the threshold, and that imports break the curve."""
    out = tmp_path / "dist"
    _build(gold, out)
    pages = "\n".join(p.read_text(encoding="utf-8") for p in (out / "modeles").iterdir())
    flat = re.sub(r"\s+", " ", pages)
    assert "Pas de projection : il faut au moins" in flat
    assert "<table" not in re.search(
        r'<section class="projection">.*?</section>', flat, re.S
    ).group(0)


# ------------------------------------------------------------------ évolutions and feed


def _bundle_pair(tmp_path: Path, gold_dir: Path) -> Path:
    """Two bundles: the older one lacks the last published target and one inflection."""
    reports = tmp_path / "reports"
    newer = _bundle(reports, "2026-09-14", gold_dir)
    older = reports / "2026-09-13" / "gold"
    older.mkdir(parents=True)
    ranking = pl.read_csv(
        newer / "ranking.csv",
        schema_overrides={"make": pl.String, "model_gen": pl.String, "generation": pl.String},
    )
    ranking.head(ranking.height - 1).with_columns(
        pl.lit(None, dtype=pl.Int64).alias("inflection_year")
    ).write_csv(older / "ranking.csv")
    for name in ("indicators", "scores", "stock_series"):
        (older / f"{name}.csv").write_bytes((newer / f"{name}.csv").read_bytes())
    return reports


def _build_from(reports: Path, gold: tuple[Path, Path], out: Path) -> None:
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


def test_evolutions_page_and_feed_list_what_changed(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    import xml.etree.ElementTree as ET

    reports = _bundle_pair(tmp_path, gold[0])
    out = tmp_path / "dist"
    _build_from(reports, gold, out)

    page = (out / "evolutions.html").read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", page)
    assert (
        "Entre le bundle du <strong>2026-09-13</strong> et celui du <strong>2026-09-14</strong>"
        in flat
    )
    assert "Nouvelles au classement" in flat  # the target dropped from the older bundle
    assert "Point d'inflexion apparu" in flat or "inflection" not in flat
    assert 'href="modeles/' in page  # every change links to its model page

    feed = ET.parse(out / "feed.xml").getroot()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = feed.findall("a:entry", ns)
    assert len(entries) == 1
    assert "2026-09-14" in entries[0].find("a:title", ns).text
    assert entries[0].find("a:id", ns).text.endswith("/2026-09-14")
    # nav and discovery link
    index = (out / "index.html").read_text(encoding="utf-8")
    assert 'type="application/atom+xml"' in index and "evolutions.html" in index


def test_evolutions_page_explains_itself_with_a_single_bundle(
    gold: tuple[Path, Path], tmp_path: Path
) -> None:
    import xml.etree.ElementTree as ET

    reports = tmp_path / "reports"
    _bundle(reports, "2026-09-14", gold[0])
    out = tmp_path / "dist"
    _build_from(reports, gold, out)
    page = (out / "evolutions.html").read_text(encoding="utf-8")
    assert "Il faut deux bundles" in page
    feed = ET.parse(out / "feed.xml").getroot()
    assert feed.findall("{http://www.w3.org/2005/Atom}entry") == []
