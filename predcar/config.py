"""Typed access to config/score.yaml and config/sources.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, HttpUrl, model_validator

from predcar.paths import CONFIG_DIR


class ScoreWeights(BaseModel):
    rarity: float
    conservation: float
    sorn_ratio: float
    recent_inflection_point: float

    def as_dict(self) -> dict[str, float]:
        return self.model_dump()


class RarityConfig(BaseModel):
    thresholds: list[int] = Field(min_length=1)


class AttritionConfig(BaseModel):
    smoothing_years: int = Field(ge=1)
    min_history_years: int = Field(ge=1)


class InflectionConfig(BaseModel):
    recent_years: int = Field(ge=1)


class ScoreConfig(BaseModel):
    version: int
    weights: ScoreWeights
    min_weight_coverage: float = Field(gt=0, le=1)
    rarity: RarityConfig
    attrition: AttritionConfig
    inflection: InflectionConfig

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> ScoreConfig:
        total = sum(self.weights.as_dict().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"score weights must sum to 1, got {total:.4f}")
        return self


class MappingConfig(BaseModel):
    min_coverage: float = Field(gt=0, le=1)
    report_top_unmapped: int = Field(ge=1)


class UkDftSource(BaseModel):
    licence: str
    page_url: HttpUrl
    files: list[str] = Field(min_length=1)


class NlRdwSource(BaseModel):
    licence: str
    dataset_id: str
    api_url: HttpUrl


class SourcesConfig(BaseModel):
    uk_dft: UkDftSource
    nl_rdw: NlRdwSource


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at top level")
    return data


def load_score_config(path: Path | None = None) -> ScoreConfig:
    """Load and validate the score configuration.

    Args:
        path: YAML file; defaults to config/score.yaml.

    Returns:
        Validated ScoreConfig.
    """
    return ScoreConfig.model_validate(_load_yaml(path or CONFIG_DIR / "score.yaml"))


def load_sources_config(path: Path | None = None) -> SourcesConfig:
    """Load and validate the data source registry (config/sources.yaml)."""
    return SourcesConfig.model_validate(_load_yaml(path or CONFIG_DIR / "sources.yaml"))


def load_mapping_config(path: Path | None = None) -> MappingConfig:
    """Load and validate the normalization thresholds (config/mapping.yaml)."""
    return MappingConfig.model_validate(_load_yaml(path or CONFIG_DIR / "mapping.yaml"))
