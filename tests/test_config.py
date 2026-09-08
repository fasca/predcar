from pathlib import Path

import pytest
import yaml

from predcar.config import load_score_config, load_sources_config


def test_repo_score_config_is_valid() -> None:
    cfg = load_score_config()
    assert cfg.version == 1
    assert abs(sum(cfg.weights.as_dict().values()) - 1.0) < 1e-9
    assert 0 < cfg.min_weight_coverage <= 1


def test_weights_must_sum_to_one(tmp_path: Path) -> None:
    cfg = load_score_config().model_dump()
    cfg["weights"]["rarity"] = 0.9
    path = tmp_path / "score.yaml"
    path.write_text(yaml.safe_dump(cfg))
    with pytest.raises(ValueError, match="sum to 1"):
        load_score_config(path)


def test_sources_config_lists_dft_files() -> None:
    src = load_sources_config()
    assert "df_VEH0120_GB.csv" in src.uk_dft.files
    assert src.nl_rdw.dataset_id == "m9d7-ebf2"
