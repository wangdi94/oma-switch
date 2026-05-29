"""End-to-end integration tests for profile + fallback independence.

Tests verify that profile switching and fallback management work correctly
together, ensuring proper state isolation and cross-feature interactions.
"""

import json
import pytest
from pathlib import Path

import oma_switch.cli as cli
from oma_switch.cli import (
    cmd_fallback_switch,
    cmd_switch,
    cmd_fallback_rm,
    cmd_fallback_edit,
    FALLBACKS_DIR,
    CONFIG_FILE,
    PROFILES_DIR,
    OMA_CONFIG,
    save_fallback_json,
    load_fallback_json,
    save_config,
    load_config,
)


# ── Fixture ────────────────────────────────────────────────────────


@pytest.fixture
def integration_setup(tmp_path, monkeypatch):
    """Comprehensive isolated environment for integration tests.
    
    Patches all module-level constants to tmp directories.
    Returns (fake_home, fake_oma_config) tuple.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    fake_config_dir = fake_home / ".config" / "oma-switch"
    fake_profiles_dir = fake_config_dir / "profiles"
    fake_fallbacks_dir = fake_config_dir / "fallbacks"
    fake_opencode_dir = fake_home / ".config" / "opencode"
    fake_config_dir.mkdir(parents=True)
    fake_profiles_dir.mkdir(parents=True)
    fake_fallbacks_dir.mkdir(parents=True)
    fake_opencode_dir.mkdir(parents=True)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(cli, "CONFIG_DIR", fake_config_dir)
    monkeypatch.setattr(cli, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(cli, "FALLBACKS_DIR", fake_fallbacks_dir)
    monkeypatch.setattr(cli, "CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr(cli, "TEMPLATE_FILE", fake_config_dir / "template.json")
    monkeypatch.setattr(cli, "OMA_CONFIG", fake_opencode_dir / "oh-my-openagent.json")
    monkeypatch.setattr(cli, "OPENCODE_DIR", fake_opencode_dir)
    monkeypatch.setattr(cli, "DCP_CONFIG_FILE", fake_opencode_dir / "dcp.jsonc")

    config = {"current": None, "profiles": {}, "current_fallback": ""}
    with open(fake_config_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f)

    fake_oma = fake_opencode_dir / "oh-my-openagent.json"
    return fake_home, fake_oma


TEST_TEMPLATE = {
    "主模型": {("agents", "sisyphus"), ("agents", "hephaestus")},
    "强模型": {("agents", "oracle")},
    "中模型": {("agents", "sisyphus-junior")},
    "弱模型": {("agents", "explore")},
    "多模态模型": {("agents", "multimodal-looker")},
}


# ── Helper Functions ──────────────────────────────────────────────


def _create_profile(name: str, profile_data: dict) -> None:
    """Register a profile file and add it to config."""
    profile_path = cli.PROFILES_DIR / f"{name}.json"
    profile_path.write_text(json.dumps(profile_data), encoding="utf-8")

    config = load_config()
    config["profiles"][name] = {"created": "2026-01-01", "description": ""}
    save_config(config)


def _write_oma_config(data: dict) -> None:
    """Write a mock OMA config file."""
    cli.OMA_CONFIG.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read_oma_config() -> dict:
    """Read the current OMA config file."""
    return json.loads(cli.OMA_CONFIG.read_text(encoding="utf-8"))


def _make_profile(main_model="gpt-4", strong_model="claude-3", mid_model="gpt-3.5", 
                  weak_model="gpt-3.5-turbo", multi_model="gpt-4-vision"):
    """Build a valid profile dict matching TEST_TEMPLATE."""
    return {
        "agents": {
            "sisyphus": {"model": main_model},
            "hephaestus": {"model": main_model},
            "oracle": {"model": strong_model},
            "sisyphus-junior": {"model": mid_model},
            "explore": {"model": weak_model},
            "multimodal-looker": {"model": multi_model},
        },
    }


def _make_fallback(primary="model-a", secondary="model-b"):
    """Build a fallback config dict with specified models."""
    return {
        "主模型": {"fallback_models": [primary]},
        "强模型": {"fallback_models": [secondary]},
        "中模型": {"fallback_models": []},
        "弱模型": {"fallback_models": [primary, secondary]},
        "多模态模型": {"fallback_models": []},
    }


# ── Integration Tests ─────────────────────────────────────────────


@pytest.mark.usefixtures("integration_setup")
def test_create_fallback_switch_verify(monkeypatch, capsys):
    """Create fallback → switch fallback → verify OMA config has fallback_models."""
    monkeypatch.setattr(cli, "load_template", lambda: TEST_TEMPLATE)

    # 1. Create fallback file directly (bypassing interactive create)
    fallback_data = _make_fallback("deepseek-v4", "gemini-3-pro")
    save_fallback_json("my-fallback", fallback_data)

    # Verify file exists
    loaded = load_fallback_json("my-fallback")
    assert loaded is not None
    assert loaded["主模型"]["fallback_models"] == ["deepseek-v4"]

    # 2. Switch fallback → inject into OMA config
    existing_oma = {
        "agents": {
            "sisyphus": {"model": "gpt-4"},
            "oracle": {"model": "claude-3"},
        },
    }
    _write_oma_config(existing_oma)

    cmd_fallback_switch(["my-fallback"])

    # 3. Verify OMA config has fallback_models
    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == ["deepseek-v4"]
    assert result["agents"]["oracle"]["fallback_models"] == ["gemini-3-pro"]
    assert result["model_fallback"] is True

    # 4. Verify config.json tracks current fallback
    config = load_config()
    assert config["current_fallback"] == "my-fallback"

    out = capsys.readouterr().out
    assert "已切换到 fallback 配置 'my-fallback'" in out


@pytest.mark.usefixtures("integration_setup")
def test_profile_switch_preserves_fallback(monkeypatch, capsys):
    """Create fallback → switch fallback → switch profile → verify fallback persists."""
    monkeypatch.setattr(cli, "load_template", lambda: TEST_TEMPLATE)

    # Setup: register two profiles
    profile_a = _make_profile(main_model="gpt-4")
    profile_b = _make_profile(main_model="claude-3")
    _create_profile("profile-a", profile_a)
    _create_profile("profile-b", profile_b)

    # Switch to profile-a
    existing_oma = {
        "agents": {
            "sisyphus": {"model": "old-model"},
            "oracle": {"model": "old-claude"},
        },
    }
    _write_oma_config(existing_oma)
    cmd_switch(["profile-a"])

    # Set fallback and switch it
    fallback_data = _make_fallback("fb-model-1", "fb-model-2")
    save_fallback_json("my-chain", fallback_data)
    config = load_config()
    config["current_fallback"] = "my-chain"
    save_config(config)

    # Now switch to profile-b → should re-inject fallback
    cmd_switch(["profile-b"])

    result = _read_oma_config()
    # Profile models should be updated
    assert result["agents"]["sisyphus"]["model"] == "claude-3"
    # Fallback should persist
    assert result["agents"]["sisyphus"]["fallback_models"] == ["fb-model-1"]
    assert result["agents"]["oracle"]["fallback_models"] == ["fb-model-2"]
    assert result["model_fallback"] is True

    # Verify config.json state
    config = load_config()
    assert config["current"] == "profile-b"
    assert config["current_fallback"] == "my-chain"


@pytest.mark.usefixtures("integration_setup")
def test_edit_fallback_updates_oma(monkeypatch, capsys):
    """Switch fallback → edit fallback → verify OMA config updated."""
    monkeypatch.setattr(cli, "load_template", lambda: TEST_TEMPLATE)
    monkeypatch.setattr(cli, "collect_all_models", lambda: ["model-a", "model-b", "model-c"])

    # Setup: create fallback, switch it, create OMA config
    fallback_data = _make_fallback("model-a", "model-b")
    save_fallback_json("edit-target", fallback_data)

    existing_oma = {
        "agents": {
            "sisyphus": {"model": "gpt-4"},
            "oracle": {"model": "claude-3"},
        },
    }
    _write_oma_config(existing_oma)

    cmd_fallback_switch(["edit-target"])

    # Verify initial state
    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == ["model-a"]

    # Edit fallback (change all categories to model-b)
    inputs = iter(["2", "2", "2", "2", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    cmd_fallback_edit(["edit-target"])

    # Verify OMA config updated with new fallback
    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == ["model-b"]
    assert result["agents"]["oracle"]["fallback_models"] == ["model-b"]

    # Verify fallback file updated
    loaded = load_fallback_json("edit-target")
    for cat in TEST_TEMPLATE:
        assert loaded[cat]["fallback_models"] == ["model-b"]


@pytest.mark.usefixtures("integration_setup")
def test_delete_current_fallback_clears(monkeypatch, capsys):
    """Delete current fallback → verify config.json cleared."""
    monkeypatch.setattr(cli, "load_template", lambda: TEST_TEMPLATE)

    # Setup: create and switch a fallback
    fallback_data = _make_fallback()
    save_fallback_json("to-delete", fallback_data)

    config = load_config()
    config["current_fallback"] = "to-delete"
    save_config(config)

    # Delete with confirmation
    monkeypatch.setattr("builtins.input", lambda _: "y")
    cmd_fallback_rm(["to-delete"])

    # Verify fallback file deleted
    assert load_fallback_json("to-delete") is None

    # Verify config.json cleared
    config = load_config()
    assert config["current_fallback"] == ""

    out = capsys.readouterr().out
    assert "已自动取消激活" in out
    assert "已删除 fallback 配置 'to-delete'" in out


@pytest.mark.usefixtures("integration_setup")
def test_empty_fallback_chain_removes_key(monkeypatch, capsys):
    """Switch to empty chain → verify fallback_models removed."""
    monkeypatch.setattr(cli, "load_template", lambda: TEST_TEMPLATE)

    # Setup: OMA config with existing fallback_models
    existing_oma = {
        "agents": {
            "sisyphus": {"model": "gpt-4", "fallback_models": ["old-fallback"]},
            "oracle": {"model": "claude-3"},
        },
    }
    _write_oma_config(existing_oma)

    # Create empty fallback chain
    empty_fallback = {
        "主模型": {"fallback_models": []},
        "强模型": {"fallback_models": []},
        "中模型": {"fallback_models": []},
        "弱模型": {"fallback_models": []},
        "多模态模型": {"fallback_models": []},
    }
    save_fallback_json("empty-chain", empty_fallback)

    # Switch to empty chain
    cmd_fallback_switch(["empty-chain"])

    # Verify fallback_models removed from OMA config
    result = _read_oma_config()
    assert "fallback_models" not in result["agents"]["sisyphus"]
    assert result["agents"]["sisyphus"]["model"] == "gpt-4"  # Model preserved
    assert result["model_fallback"] is False

    # Config tracks the empty chain as current
    config = load_config()
    assert config["current_fallback"] == "empty-chain"


@pytest.mark.usefixtures("integration_setup")
def test_profile_fallback_independence(monkeypatch, capsys):
    """Create profile + create fallback → switch both → verify both applied correctly."""
    monkeypatch.setattr(cli, "load_template", lambda: TEST_TEMPLATE)

    # Setup: create a profile with specific models
    profile_data = _make_profile(
        main_model="deepseek-v4-pro",
        strong_model="qwen-max",
        mid_model="deepseek-v3",
        weak_model="glm-4-flash",
        multi_model="gpt-4o",
    )
    _create_profile("custom-profile", profile_data)

    # Create a fallback with different models
    fallback_data = {
        "主模型": {"fallback_models": ["fallback-main-1", "fallback-main-2"]},
        "强模型": {"fallback_models": ["fallback-strong-1"]},
        "中模型": {"fallback_models": []},
        "弱模型": {"fallback_models": ["fallback-weak-1"]},
        "多模态模型": {"fallback_models": []},
    }
    save_fallback_json("custom-fallback", fallback_data)

    # Start with empty OMA config
    _write_oma_config({"agents": {}, "categories": {}})

    # Switch fallback first
    cmd_fallback_switch(["custom-fallback"])

    # Verify fallback applied
    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == ["fallback-main-1", "fallback-main-2"]
    assert result["agents"]["oracle"]["fallback_models"] == ["fallback-strong-1"]
    assert result["agents"]["explore"]["fallback_models"] == ["fallback-weak-1"]

    # Now switch profile → should update models AND re-inject fallback
    cmd_switch(["custom-profile"])

    result = _read_oma_config()
    # Profile models should be applied
    assert result["agents"]["sisyphus"]["model"] == "deepseek-v4-pro"
    assert result["agents"]["oracle"]["model"] == "qwen-max"
    assert result["agents"]["sisyphus-junior"]["model"] == "deepseek-v3"
    assert result["agents"]["explore"]["model"] == "glm-4-flash"
    assert result["agents"]["multimodal-looker"]["model"] == "gpt-4o"

    # Fallback should still be present
    assert result["agents"]["sisyphus"]["fallback_models"] == ["fallback-main-1", "fallback-main-2"]
    assert result["agents"]["oracle"]["fallback_models"] == ["fallback-strong-1"]
    assert result["agents"]["explore"]["fallback_models"] == ["fallback-weak-1"]
    assert result["model_fallback"] is True

    # Both are tracked in config
    config = load_config()
    assert config["current"] == "custom-profile"
    assert config["current_fallback"] == "custom-fallback"

    # Verify independence: delete fallback, profile should survive
    monkeypatch.setattr("builtins.input", lambda _: "y")
    cmd_fallback_rm(["custom-fallback"])

    config = load_config()
    assert config["current"] == "custom-profile"
    assert config["current_fallback"] == ""
    assert load_fallback_json("custom-fallback") is None
