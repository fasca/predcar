"""Silver schemas (SPEC §3) and their invariants (SPEC §8)."""

from __future__ import annotations

from enum import StrEnum

import polars as pl


class Status(StrEnum):
    LICENSED = "licensed"
    SORN = "sorn"


FLEET_STOCK_SCHEMA: dict[str, pl.DataType] = {
    "country": pl.Utf8,
    "period": pl.Date,
    "make_raw": pl.Utf8,
    "model_gen_raw": pl.Utf8,  # DfT GenModel level; null for sources without it
    "model_raw": pl.Utf8,
    "make": pl.Utf8,
    "model_gen": pl.Utf8,
    "generation": pl.Utf8,
    "year_first_reg": pl.Int32,
    "year_manufacture": pl.Int32,  # build year when the source has it (VEH0124); else null
    "status": pl.Utf8,
    "count": pl.Int64,
    "source": pl.Utf8,
    "source_file": pl.Utf8,
}

FLEET_NEW_REG_SCHEMA: dict[str, pl.DataType] = {
    "country": pl.Utf8,
    "period": pl.Date,
    "make_raw": pl.Utf8,
    "model_gen_raw": pl.Utf8,
    "model_raw": pl.Utf8,
    "make": pl.Utf8,
    "model_gen": pl.Utf8,
    "generation": pl.Utf8,
    "count": pl.Int64,
    "source": pl.Utf8,
    "source_file": pl.Utf8,
}

# Columns that identify one observation; duplicates mean the parser double-counted.
FLEET_STOCK_KEY = [
    "country",
    "period",
    "make_raw",
    "model_gen_raw",
    "model_raw",
    "year_first_reg",
    "year_manufacture",
    "status",
    "source_file",
]
FLEET_NEW_REG_KEY = ["country", "period", "make_raw", "model_gen_raw", "model_raw", "source_file"]

_REQUIRED_NON_NULL = [
    "country",
    "period",
    "make_raw",
    "model_raw",
    "count",
    "source",
    "source_file",
]


class SchemaError(ValueError):
    """A dataframe does not match a silver schema."""


class InvariantError(ValueError):
    """A silver dataframe violates a data invariant."""


def conform(df: pl.DataFrame, schema: dict[str, pl.DataType]) -> pl.DataFrame:
    """Select schema columns in order, adding missing nullable ones, and cast dtypes.

    Args:
        df: Input frame; extra columns are dropped.
        schema: Target column → dtype mapping.

    Returns:
        A frame with exactly the schema's columns and dtypes.

    Raises:
        SchemaError: when a required (non-null) column is absent or a cast fails.
    """
    missing_required = [c for c in _REQUIRED_NON_NULL if c in schema and c not in df.columns]
    if missing_required:
        raise SchemaError(f"missing required columns: {missing_required}")
    exprs = [
        (pl.col(name) if name in df.columns else pl.lit(None)).cast(dtype, strict=True).alias(name)
        for name, dtype in schema.items()
    ]
    try:
        return df.select(exprs)
    except pl.exceptions.InvalidOperationError as exc:
        raise SchemaError(f"cast failed: {exc}") from exc


def check_fleet_stock(df: pl.DataFrame) -> None:
    """Enforce fleet_stock invariants; raise InvariantError with a precise message."""
    _check_common(df, FLEET_STOCK_SCHEMA, FLEET_STOCK_KEY)
    bad_status = df.filter(
        pl.col("status").is_not_null() & ~pl.col("status").is_in([s.value for s in Status])
    )
    if bad_status.height:
        raise InvariantError(f"unknown status values: {bad_status['status'].unique().to_list()}")


def check_fleet_new_reg(df: pl.DataFrame) -> None:
    """Enforce fleet_new_reg invariants."""
    _check_common(df, FLEET_NEW_REG_SCHEMA, FLEET_NEW_REG_KEY)


def _check_common(df: pl.DataFrame, schema: dict[str, pl.DataType], key: list[str]) -> None:
    if list(df.columns) != list(schema):
        raise SchemaError(f"columns {df.columns} != schema {list(schema)}")
    for name, dtype in schema.items():
        if df.schema[name] != dtype:
            raise SchemaError(f"column {name}: dtype {df.schema[name]} != {dtype}")
    for name in _REQUIRED_NON_NULL:
        if name in schema and df[name].null_count():
            raise InvariantError(f"column {name} has {df[name].null_count()} nulls")
    negative = df.filter(pl.col("count") < 0).height
    if negative:
        raise InvariantError(f"{negative} rows with negative count")
    dupes = df.group_by(key).len().filter(pl.col("len") > 1)
    if dupes.height:
        raise InvariantError(f"{dupes.height} duplicated keys, e.g. {dupes.row(0)}")
