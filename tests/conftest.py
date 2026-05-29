"""
pytest fixtures for oma-switch tests.

Provides isolated config directory mocking and sample data fixtures
for testing without touching real user configuration.
"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    """
    Mock Path.home() to return a tmp directory so all config operations
    use an isolated location instead of ~/.config/oma-switch.

    Returns the fake home directory Path.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    return fake_home


@pytest.fixture
def sample_fallback_data():
    """
    Return a valid fallback config dict matching the expected structure
    for oma-switch fallback chain configurations.
    """
    return {
        "主模型": {"fallback_models": ["model-a", "model-b"]},
        "强模型": {"fallback_models": [{"model": "x", "variant": "max"}]},
        "中模型": {"fallback_models": []},
        "弱模型": {"fallback_models": ["model-c"]},
        "多模态模型": {"fallback_models": ["model-d"]},
    }


@pytest.fixture
def tmp_profiles_dir(tmp_path):
    """
    Return a temporary profiles directory Path.
    """
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    return profiles_dir


@pytest.fixture
def tmp_fallbacks_dir(tmp_path):
    """
    Return a temporary fallbacks directory Path.
    """
    fallbacks_dir = tmp_path / "fallbacks"
    fallbacks_dir.mkdir()
    return fallbacks_dir
