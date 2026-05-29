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
    将 cli.py 的所有模块级路径常量替换到临时目录，确保测试不会
    污染用户真实的 ~/.config/oma-switch/ 和 ~/.config/opencode/ 配置。

    只 mock Path.home() 是不够的——模块级常量（CONFIG_FILE 等）在
    import 时已经解析到真实路径，必须在它们被使用前 monkeypatch 掉。

    Returns the fake home directory Path.
    """
    import oma_switch.constants as constants
    import oma_switch.cli as cli
    import oma_switch.config_io as config_io_mod
    import oma_switch.history as history_mod
    import oma_switch.version as version_mod
    import oma_switch.models as models_mod

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    # 用临时目录重建完整的配置目录结构
    fake_config_dir = fake_home / ".config" / "oma-switch"
    fake_profiles_dir = fake_config_dir / "profiles"
    fake_fallbacks_dir = fake_config_dir / "fallbacks"
    fake_opencode_dir = fake_home / ".config" / "opencode"
    fake_config_dir.mkdir(parents=True)
    fake_profiles_dir.mkdir(parents=True)
    fake_fallbacks_dir.mkdir(parents=True)
    fake_opencode_dir.mkdir(parents=True)

    monkeypatch.setattr(constants, "CONFIG_DIR", fake_config_dir)
    monkeypatch.setattr(constants, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(constants, "FALLBACKS_DIR", fake_fallbacks_dir)
    monkeypatch.setattr(constants, "CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr(constants, "TEMPLATE_FILE", fake_config_dir / "template.json")
    monkeypatch.setattr(constants, "HISTORY_FILE", fake_config_dir / "history.json")
    monkeypatch.setattr(history_mod, "HISTORY_FILE", fake_config_dir / "history.json")
    monkeypatch.setattr(constants, "OMA_CONFIG", fake_opencode_dir / "oh-my-openagent.json")
    monkeypatch.setattr(constants, "OPENCODE_DIR", fake_opencode_dir)
    monkeypatch.setattr(constants, "DCP_CONFIG_FILE", fake_opencode_dir / "dcp.jsonc")

    monkeypatch.setattr(cli, "CONFIG_DIR", fake_config_dir)
    monkeypatch.setattr(cli, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(cli, "FALLBACKS_DIR", fake_fallbacks_dir)
    monkeypatch.setattr(cli, "CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr(cli, "TEMPLATE_FILE", fake_config_dir / "template.json")
    monkeypatch.setattr(cli, "HISTORY_FILE", fake_config_dir / "history.json")
    monkeypatch.setattr(cli, "OMA_CONFIG", fake_opencode_dir / "oh-my-openagent.json")
    monkeypatch.setattr(cli, "OPENCODE_DIR", fake_opencode_dir)
    monkeypatch.setattr(cli, "DCP_CONFIG_FILE", fake_opencode_dir / "dcp.jsonc")

    monkeypatch.setattr(models_mod, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(models_mod, "FALLBACKS_DIR", fake_fallbacks_dir)
    monkeypatch.setattr(models_mod, "OMA_CONFIG", fake_opencode_dir / "oh-my-openagent.json")

    monkeypatch.setattr(version_mod, "CONFIG_DIR", fake_config_dir)

    monkeypatch.setattr(config_io_mod, "CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr(config_io_mod, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(config_io_mod, "FALLBACKS_DIR", fake_fallbacks_dir)

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
