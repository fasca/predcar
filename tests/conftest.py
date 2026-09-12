from datetime import date
from pathlib import Path

import polars as pl
import pytest

from predcar import export, schemas
from predcar import normalize as n
from predcar.paths import MAPPING_DIR

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def stock_frame(rows: list[dict]) -> pl.DataFrame:
    """A minimal fleet_stock frame; every field of ``base`` is overridable per row."""
    base = {
        "country": "GB",
        "period": date(2024, 6, 30),
        "make_raw": "BMW",
        "model_gen_raw": None,
        "model_raw": "M3",
        "make": None,
        "model_gen": None,
        "generation": None,
        "year_first_reg": None,
        "status": "licensed",
        "count": 1,
        "source": "t",
        "source_file": "t.csv",
    }
    return schemas.conform(pl.DataFrame([{**base, **r} for r in rows]), schemas.FLEET_STOCK_SCHEMA)


# --------------------------------------------------------------- committed evidence bundle
#
# reports/<date>/ is versioned, so these fixtures give the test suite real data without
# network access or a data/ directory. The bundle is an *input corpus*, never an oracle for
# the mapping: its stored ``model_gen`` / ``generation`` columns were produced by whatever
# rules existed the day it was exported. Tests replay the current rules on ``model_raw``.


@pytest.fixture(scope="session")
def report() -> Path:
    bundle = export.latest_report()
    assert bundle is not None, "no evidence bundle in reports/ — run `make export` and commit it"
    return bundle


@pytest.fixture(scope="session")
def real_labels(report: Path) -> pl.DataFrame:
    """Every distinct raw label of the target makes, from the latest bundle."""
    path = report / "silver" / "labels_target_makes.csv"
    assert path.is_file(), f"{path} missing from the evidence bundle"
    return pl.read_csv(path, infer_schema_length=0)


@pytest.fixture(scope="session")
def real_labels_mapped(real_labels: pl.DataFrame) -> pl.DataFrame:
    """The real (make_raw, model_raw) pairs resolved by the *current* mapping rules."""
    makes = n.load_makes(MAPPING_DIR / "makes.csv")
    rules = n.load_models(MAPPING_DIR / "models.csv")
    pairs = real_labels.select("make_raw", "model_raw").unique()
    df = stock_frame(
        [{"make_raw": mk, "model_raw": ml} for mk, ml in pairs.iter_rows() if ml is not None]
    )
    mapped = n.apply(df, makes, rules)
    return mapped.select("make_raw", "make", "model_raw", "model_gen", "generation")


@pytest.fixture(scope="session")
def gold(report: Path) -> dict[str, pl.DataFrame]:
    """The bundle's gold CSVs, or skip when the export had no gold stage."""
    out = {}
    for name in ("indicators", "scores", "stock_series"):
        path = report / "gold" / f"{name}.csv"
        if not path.is_file():
            pytest.skip(f"evidence bundle {report.name} has no gold/{name}.csv")
        out[name] = pl.read_csv(path)
    return out
