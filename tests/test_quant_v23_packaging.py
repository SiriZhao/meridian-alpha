"""Offline source generation cannot contaminate policy directories with locks."""
import importlib.util
from pathlib import Path

import pytest


def test_source_generator_preserves_content_and_creates_no_lock_directory(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'scripts/package_quant_v23.py'
    spec = importlib.util.spec_from_file_location('v23_packager', source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / 'policy.yaml'
    module.seal_source_file(path, 'authority: SHADOW_ONLY\n')
    module.seal_source_file(path, 'authority: SHADOW_ONLY\n')
    with pytest.raises(ValueError, match='DIFFERENT_CONTENT'):
        module.seal_source_file(path, 'authority: LIVE\n')
    assert list(tmp_path.iterdir()) == [path]
    assert path.read_text() == 'authority: SHADOW_ONLY\n'
