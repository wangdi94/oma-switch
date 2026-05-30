"""
Tests for merge_fallback_to_oma_config function.

Verifies field-level deep merge that injects fallback_models into OMA config
entries without replacing existing fields.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")

import oma_switch.cli as cli
import oma_switch.cli_helpers as cli_helpers_mod
import oma_switch.config_io as config_io_mod

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    fake_config_dir = fake_home / ".config" / "oma-switch"
    fake_profiles_dir = fake_config_dir / "profiles"
    fake_opencode_dir = fake_home / ".config" / "opencode"
    fake_config_dir.mkdir(parents=True)
    fake_profiles_dir.mkdir(parents=True)
    fake_opencode_dir.mkdir(parents=True)

    monkeypatch.setattr(cli, "CONFIG_DIR", fake_config_dir)
    monkeypatch.setattr(cli, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(cli, "CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr(cli, "TEMPLATE_FILE", fake_config_dir / "template.json")
    monkeypatch.setattr(cli, "OMA_CONFIG", fake_opencode_dir / "oh-my-openagent.json")
    monkeypatch.setattr(cli_helpers_mod, "OMA_CONFIG", fake_opencode_dir / "oh-my-openagent.json")
    monkeypatch.setattr(cli, "OPENCODE_DIR", fake_opencode_dir)
    monkeypatch.setattr(cli, "DCP_CONFIG_FILE", fake_opencode_dir / "dcp.jsonc")

    monkeypatch.setattr(config_io_mod, "CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr(config_io_mod, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(config_io_mod, "FALLBACKS_DIR", fake_config_dir / "fallbacks")

    return fake_home


SMALL_TEMPLATE = {
    "主模型": {("agents", "sisyphus"), ("agents", "hephaestus")},
    "强模型": {("agents", "oracle")},
}


def _write_oma_config(data: dict) -> None:
    cli.OMA_CONFIG.write_text(json.dumps(data), encoding="utf-8")


def _read_oma_config() -> dict:
    return json.loads(cli.OMA_CONFIG.read_text(encoding="utf-8"))


def _monkeypatch_template(monkeypatch):
    monkeypatch.setattr(cli, "load_template", lambda: SMALL_TEMPLATE)
    monkeypatch.setattr(cli_helpers_mod, "load_template", lambda: SMALL_TEMPLATE)


# ── Tests ─────────────────────────────────────────────────────────


def test_inject_fallback_models(isolated_config_dir, monkeypatch):
    _monkeypatch_template(monkeypatch)
    existing = {
        "agents": {
            "sisyphus": {"model": "gpt-4"},
            "hephaestus": {"model": "gpt-4"},
            "oracle": {"model": "claude-3"},
        },
    }
    _write_oma_config(existing)

    fallback_data = {
        "主模型": {"fallback_models": ["model-a", "model-b"]},
        "强模型": {"fallback_models": []},
    }
    cli.merge_fallback_to_oma_config(fallback_data)

    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == ["model-a", "model-b"]
    assert result["agents"]["hephaestus"]["fallback_models"] == ["model-a", "model-b"]
    assert "fallback_models" not in result["agents"]["oracle"]


def test_preserves_model(isolated_config_dir, monkeypatch):
    _monkeypatch_template(monkeypatch)
    existing = {
        "agents": {
            "sisyphus": {"model": "gpt-4", "temperature": 0.7},
            "hephaestus": {"model": "gpt-4"},
            "oracle": {"model": "claude-3"},
        },
    }
    _write_oma_config(existing)

    fallback_data = {
        "主模型": {"fallback_models": ["model-x"]},
    }
    cli.merge_fallback_to_oma_config(fallback_data)

    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["model"] == "gpt-4"
    assert result["agents"]["sisyphus"]["temperature"] == 0.7
    assert result["agents"]["hephaestus"]["model"] == "gpt-4"


def test_empty_removes_key(isolated_config_dir, monkeypatch):
    _monkeypatch_template(monkeypatch)
    existing = {
        "agents": {
            "sisyphus": {"model": "gpt-4", "fallback_models": ["old-model"]},
            "hephaestus": {"model": "gpt-4"},
            "oracle": {"model": "claude-3"},
        },
    }
    _write_oma_config(existing)

    fallback_data = {
        "主模型": {"fallback_models": []},
    }
    cli.merge_fallback_to_oma_config(fallback_data)

    result = _read_oma_config()
    assert "fallback_models" not in result["agents"]["sisyphus"]
    assert result["agents"]["sisyphus"]["model"] == "gpt-4"


def test_model_fallback_flag(isolated_config_dir, monkeypatch):
    _monkeypatch_template(monkeypatch)
    existing = {"agents": {"sisyphus": {"model": "gpt-4"}, "oracle": {"model": "claude-3"}}}
    _write_oma_config(existing)

    fallback_data = {
        "主模型": {"fallback_models": ["model-a"]},
        "强模型": {"fallback_models": []},
    }
    cli.merge_fallback_to_oma_config(fallback_data)

    result = _read_oma_config()
    assert result["model_fallback"] is True


def test_partial_fallback(isolated_config_dir, monkeypatch):
    _monkeypatch_template(monkeypatch)
    existing = {"agents": {"sisyphus": {"model": "gpt-4"}, "oracle": {"model": "claude-3"}}}
    _write_oma_config(existing)

    fallback_data = {
        "主模型": {"fallback_models": ["model-a"]},
        "强模型": {"fallback_models": []},
    }
    cli.merge_fallback_to_oma_config(fallback_data)

    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == ["model-a"]
    assert "fallback_models" not in result["agents"]["oracle"]
    assert result["model_fallback"] is True


def test_no_oma_config(isolated_config_dir, monkeypatch):
    _monkeypatch_template(monkeypatch)
    assert not cli.OMA_CONFIG.exists()

    fallback_data = {
        "主模型": {"fallback_models": ["model-a"]},
    }
    cli.merge_fallback_to_oma_config(fallback_data)

    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == ["model-a"]
    assert result["agents"]["hephaestus"]["fallback_models"] == ["model-a"]
    assert result["model_fallback"] is True


def test_model_fallback_false(isolated_config_dir, monkeypatch):
    _monkeypatch_template(monkeypatch)
    existing = {"agents": {"sisyphus": {"model": "gpt-4"}, "oracle": {"model": "claude-3"}}}
    _write_oma_config(existing)

    fallback_data = {
        "主模型": {"fallback_models": []},
        "强模型": {"fallback_models": []},
    }
    cli.merge_fallback_to_oma_config(fallback_data)

    result = _read_oma_config()
    assert result["model_fallback"] is False


# ── Tests for fallback chain filtering ────────────────────────────


def test_get_model_name_string():
    assert cli_helpers_mod._get_model_name("vendor/model") == "vendor/model"


def test_get_model_name_dict():
    assert cli_helpers_mod._get_model_name({"model": "vendor/model", "variant": "max"}) == "vendor/model"


def test_get_model_name_dict_no_model():
    assert cli_helpers_mod._get_model_name({"variant": "max"}) == ""


def test_filter_chain_removes_current_model():
    chain = ["model-a", "model-b", "model-c"]
    assert cli_helpers_mod._filter_chain_by_current_model(chain, "model-b") == ["model-a", "model-c"]


def test_filter_chain_removes_current_model_dict_format():
    chain = [
        "model-a",
        {"model": "model-b", "variant": "max"},
        "model-c",
    ]
    assert cli_helpers_mod._filter_chain_by_current_model(chain, "model-b") == ["model-a", "model-c"]


def test_filter_chain_keeps_all_when_not_in_chain():
    chain = ["model-a", "model-b"]
    assert cli_helpers_mod._filter_chain_by_current_model(chain, "model-x") == ["model-a", "model-b"]


def test_filter_chain_empty_model():
    chain = ["model-a", "model-b"]
    assert cli_helpers_mod._filter_chain_by_current_model(chain, "") == ["model-a", "model-b"]


def test_filter_chain_none_model():
    chain = ["model-a", "model-b"]
    assert cli_helpers_mod._filter_chain_by_current_model(chain, None) == ["model-a", "model-b"]


def test_merge_fallback_filters_current_model(isolated_config_dir, monkeypatch):
    _monkeypatch_template(monkeypatch)
    existing = {
        "agents": {
            "sisyphus": {"model": "model-a"},
            "hephaestus": {"model": "model-b"},
            "oracle": {"model": "model-c"},
        },
    }
    _write_oma_config(existing)

    fallback_data = {
        "主模型": {"fallback_models": ["model-a", "model-x", "model-y"]},
    }
    cli.merge_fallback_to_oma_config(fallback_data)

    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == ["model-x", "model-y"]
    assert result["agents"]["hephaestus"]["fallback_models"] == ["model-a", "model-x", "model-y"]


def test_merge_fallback_filters_dict_format(isolated_config_dir, monkeypatch):
    _monkeypatch_template(monkeypatch)
    existing = {
        "agents": {
            "sisyphus": {"model": "model-a"},
            "hephaestus": {"model": "model-a"},
            "oracle": {"model": "model-c"},
        },
    }
    _write_oma_config(existing)

    fallback_data = {
        "主模型": {
            "fallback_models": [
                "model-a",
                {"model": "model-b", "variant": "max"},
                "model-x",
            ]
        },
    }
    cli.merge_fallback_to_oma_config(fallback_data)

    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == [
        {"model": "model-b", "variant": "max"},
        "model-x",
    ]
