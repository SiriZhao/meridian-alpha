from pathlib import Path

import pytest

from meridian.config import load_policies

ROOT = Path(__file__).parents[1]


def copied_policies(tmp_path: Path) -> Path:
    destination = tmp_path / "policies"
    destination.mkdir()
    for source in (ROOT / "policies").iterdir():
        (destination / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def test_malformed_yaml_fails_fast(tmp_path: Path) -> None:
    directory = copied_policies(tmp_path)
    (directory / "risk.yaml").write_text("max_position_weight: [", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed YAML"):
        load_policies(directory)


def test_impossible_weight_capacity_fails_fast(tmp_path: Path) -> None:
    directory = copied_policies(tmp_path)
    risk = directory / "risk.yaml"
    risk.write_text(
        risk.read_text(encoding="utf-8")
        .replace("max_position_weight: 0.10", "max_position_weight: 0.01")
        .replace("max_number_positions: 10", "max_number_positions: 1"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="position capacity"):
        load_policies(directory)


def test_missing_model_setting_fails_fast(tmp_path: Path) -> None:
    directory = copied_policies(tmp_path)
    (directory / "models.yaml").write_text("example_defaults: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid policy"):
        load_policies(directory)
