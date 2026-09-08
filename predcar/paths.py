"""Project paths. Override the root with the PREDCAR_ROOT environment variable."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("PREDCAR_ROOT", Path(__file__).resolve().parent.parent))
CONFIG_DIR = ROOT / "config"
MAPPING_DIR = ROOT / "mapping"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
