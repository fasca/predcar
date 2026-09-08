"""Typer CLI: ``predcar fetch uk``, ``predcar ingest uk``, ``predcar validate``."""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl
import typer

from predcar import normalize as normalize_mod
from predcar import raw, schemas
from predcar.config import load_mapping_config, load_sources_config
from predcar.ingest import dft, rdw
from predcar.paths import MAPPING_DIR, SILVER_DIR

app = typer.Typer(help="predcar data pipeline", no_args_is_help=True)
fetch_app = typer.Typer(help="Download raw files into data/raw/<source>/<date>/")
ingest_app = typer.Typer(help="Parse the latest raw snapshot into data/silver/")
app.add_typer(fetch_app, name="fetch")
app.add_typer(ingest_app, name="ingest")


@app.callback()
def _setup(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@fetch_app.command("uk")
def fetch_uk() -> None:
    """Archive DfT VEH0120 / VEH0124 / VEH0160 CSVs with checksums."""
    for path in dft.fetch(load_sources_config()):
        typer.echo(path)


@fetch_app.command("nl")
def fetch_nl() -> None:
    """Archive one aggregated RDW snapshot (make × model × first-use year), never per vehicle."""
    typer.echo(rdw.fetch(load_sources_config()))


@ingest_app.command("uk")
def ingest_uk(
    snapshot: Path | None = typer.Option(None, help="Raw snapshot dir (default: latest)"),
) -> None:
    """Unpivot the DfT tables into silver fleet_stock / fleet_new_reg Parquet files."""
    snapshot = snapshot or raw.latest_snapshot(dft.SOURCE)
    for name, path in dft.ingest(snapshot).items():
        typer.echo(f"{name}: {path}")


@ingest_app.command("nl")
def ingest_nl(
    snapshot: Path | None = typer.Option(None, help="Raw snapshot dir (default: latest)"),
) -> None:
    """Parse one RDW snapshot into silver fleet_stock_nl_rdw_<date>.parquet."""
    snapshot = snapshot or raw.latest_snapshot(rdw.SOURCE)
    typer.echo(rdw.ingest(snapshot))


@app.command()
def normalize(
    min_coverage: float | None = typer.Option(
        None, help="Override config/mapping.yaml (0 to explore without failing)"
    ),
    silver_dir: Path = typer.Option(SILVER_DIR),
    mapping_dir: Path = typer.Option(MAPPING_DIR),
) -> None:
    """Apply mapping/ to every ingested silver file; fail if target-make coverage < threshold."""
    cfg = load_mapping_config()
    threshold = cfg.min_coverage if min_coverage is None else min_coverage
    try:
        written = normalize_mod.normalize(
            silver_dir, mapping_dir, threshold, cfg.report_top_unmapped
        )
    except normalize_mod.CoverageError as exc:
        raise typer.Exit(code=2) from _echo_error(exc)
    for name, path in written.items():
        typer.echo(f"{name}: {path}")


def _echo_error(exc: Exception) -> Exception:
    typer.echo(f"ERROR: {exc}", err=True)
    return exc


@app.command()
def validate(silver_dir: Path = typer.Option(SILVER_DIR)) -> None:
    """Re-run silver invariants on every Parquet file in data/silver/."""
    checks = {
        "fleet_stock": schemas.check_fleet_stock,
        "fleet_new_reg": schemas.check_fleet_new_reg,
    }
    files = sorted(silver_dir.glob("*.parquet"))
    if not files:
        raise typer.BadParameter(f"no parquet file in {silver_dir}")
    for path in files:
        prefix = next((p for p in checks if path.name.startswith(p)), None)
        if prefix is None:
            typer.echo(f"{path.name}: no known schema, skipped")
            continue
        checks[prefix](pl.read_parquet(path))
        typer.echo(f"{path.name}: OK")
