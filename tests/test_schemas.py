from datetime import date

import polars as pl
import pytest

from predcar import schemas


def _stock_row(**overrides) -> dict:
    row = {
        "country": "GB",
        "period": date(2024, 6, 30),
        "make_raw": "BMW",
        "model_gen_raw": "M3",
        "model_raw": "M3 E46",
        "make": None,
        "model_gen": None,
        "generation": None,
        "year_first_reg": None,
        "status": "licensed",
        "count": 10,
        "source": "uk_dft",
        "source_file": "f.csv",
    }
    row.update(overrides)
    return row


def _stock(rows: list[dict]) -> pl.DataFrame:
    return schemas.conform(pl.DataFrame(rows), schemas.FLEET_STOCK_SCHEMA)


def test_conform_adds_missing_nullable_columns_and_casts() -> None:
    df = pl.DataFrame(
        {
            "country": ["GB"],
            "period": [date(2024, 6, 30)],
            "make_raw": ["BMW"],
            "model_raw": ["M3"],
            "count": ["10"],
            "source": ["uk_dft"],
            "source_file": ["f.csv"],
        }
    )
    out = schemas.conform(df, schemas.FLEET_STOCK_SCHEMA)
    assert list(out.columns) == list(schemas.FLEET_STOCK_SCHEMA)
    assert out.schema["count"] == pl.Int64
    assert out["generation"].null_count() == 1


def test_conform_rejects_missing_required_column() -> None:
    with pytest.raises(schemas.SchemaError, match="count"):
        schemas.conform(pl.DataFrame({"country": ["GB"]}), schemas.FLEET_STOCK_SCHEMA)


def test_check_fleet_stock_accepts_valid_frame() -> None:
    schemas.check_fleet_stock(_stock([_stock_row(), _stock_row(status="sorn")]))


def test_negative_count_is_rejected() -> None:
    with pytest.raises(schemas.InvariantError, match="negative"):
        schemas.check_fleet_stock(_stock([_stock_row(count=-1)]))


def test_duplicate_key_is_rejected() -> None:
    with pytest.raises(schemas.InvariantError, match="duplicated"):
        schemas.check_fleet_stock(_stock([_stock_row(), _stock_row(count=99)]))


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(schemas.InvariantError, match="status"):
        schemas.check_fleet_stock(_stock([_stock_row(status="Total")]))


def test_wrong_column_order_is_a_schema_error() -> None:
    df = _stock([_stock_row()])
    df = df.select(df.columns[::-1])
    with pytest.raises(schemas.SchemaError):
        schemas.check_fleet_stock(df)
