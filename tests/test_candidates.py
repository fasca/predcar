"""``predcar candidates``: a proposal list, never a write to the target list."""

from datetime import date
from pathlib import Path

import polars as pl

from predcar import candidates, schemas
from predcar.config import CandidatesConfig
from predcar.normalize import TargetModel

CFG = CandidatesConfig(
    series="VEH0120",
    country="GB",
    stock_peak_min=500,
    stock_now_max=20000,
    loss_min=0.5,
    exclude_model_gen="^(OTHER|LEGACY)",
)
TARGET = TargetModel(
    make="M", model_gen="A GTI", generation="MK1", segment="GTI", year_from=1990, year_to=1995
)


def _rows(model_gen: str, series: list[int], make: str = "M") -> list[dict]:
    return [
        {
            "country": "GB",
            "period": date(2014 + i, 12, 31),
            "make_raw": make,
            "model_gen_raw": None,
            "model_raw": model_gen,
            "make": make,
            "model_gen": model_gen,
            "generation": None,
            "year_first_reg": None,
            "status": "licensed",
            "count": n,
            "source": "uk_dft",
            "source_file": "df_VEH0120_GB.csv",
        }
        for i, n in enumerate(series)
    ]


def _stock(*groups: list[dict]) -> pl.DataFrame:
    return schemas.conform(pl.DataFrame([r for g in groups for r in g]), schemas.FLEET_STOCK_SCHEMA)


def test_only_the_depleted_non_target_model_is_proposed() -> None:
    stock = _stock(
        _rows("A GTI", [1000, 800, 600]),  # already a target: excluded
        _rows("A", [2000, 1500, 900, 600]),  # candidate: −70 % from peak
        _rows("B", [1000, 950, 900]),  # stable: not a candidate
        _rows("OTHER", [5000, 2000, 500]),  # catch-all: excluded by regex
        _rows("MODEL MISSING", [3000, 1000, 100]),  # unknown label: excluded
        _rows("C", [300, 100]),  # never had a fleet: below stock_peak_min
    )
    out = candidates.find(stock, [TARGET], CFG, unknown_labels=("MODEL MISSING",))
    assert out["model_gen"].to_list() == ["A"]
    row = out.row(0, named=True)
    assert (row["peak_year"], row["stock_peak"]) == (2014, 2000)
    assert (row["year_now"], row["stock_now"]) == (2017, 600)
    assert row["loss"] == 0.7
    # the sporty version being a target already is visible next to the base model
    assert row["existing_targets_of_make"] == "A GTI MK1"


def test_peak_is_the_maximum_not_the_first_year() -> None:
    """A model still selling in 2014 peaks later; the loss is measured from that peak."""
    stock = _stock(_rows("A", [400, 900, 1200, 700, 300]))
    row = candidates.find(stock, [], CFG).row(0, named=True)
    assert (row["peak_year"], row["stock_peak"]) == (2016, 1200)
    assert row["loss"] == 0.75


def test_sorn_is_not_in_circulation() -> None:
    rows = _rows("A", [1000, 400])
    rows.append({**rows[1], "status": "sorn", "count": 500})  # parked, not on the road
    out = candidates.find(_stock(rows), [], CFG)
    assert out.row(0, named=True)["stock_now"] == 400


def test_other_countries_and_series_are_ignored() -> None:
    nl = [
        {**r, "country": "NL", "source_file": "gekentekende_voertuigen_agg.json"}
        for r in _rows("A", [1000, 100])
    ]
    assert candidates.find(_stock(nl), [], CFG).height == 0


def test_write_produces_the_csv_in_the_dated_report(tmp_path: Path) -> None:
    out = candidates.find(_stock(_rows("A", [1000, 100])), [], CFG)
    path = candidates.write(out, tmp_path / "2026-09-14")
    assert path == tmp_path / "2026-09-14" / candidates.CANDIDATES_FILE
    assert pl.read_csv(path)["model_gen"].to_list() == ["A"]
