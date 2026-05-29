"""Tests for cmd_fallback_list, cmd_fallback_create, cmd_fallback_view, cmd_fallback_diff, and cmd_fallback_edit commands."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import oma_switch.cli as cli
import oma_switch.cli_helpers as cli_helpers_mod
from oma_switch.cli import (
    cmd_fallback,
    cmd_fallback_create,
    cmd_fallback_diff,
    cmd_fallback_edit,
    cmd_fallback_list,
    cmd_fallback_rm,
    cmd_fallback_switch,
    cmd_fallback_view,
    cmd_list,
    cmd_switch,
    load_config,
    load_fallback_json,
    save_config,
    save_fallback_json,
    validate_fallback_config,
)


@pytest.fixture(autouse=True)
def _patch_dirs(tmp_path, monkeypatch):
    """Point FALLBACKS_DIR, PROFILES_DIR, and CONFIG_FILE to tmp dirs."""
    fake_fallbacks = tmp_path / "fallbacks"
    fake_fallbacks.mkdir()
    monkeypatch.setattr("oma_switch.cli.FALLBACKS_DIR", fake_fallbacks)
    monkeypatch.setattr("oma_switch.config_io.FALLBACKS_DIR", fake_fallbacks)

    fake_profiles = tmp_path / "profiles"
    fake_profiles.mkdir()
    monkeypatch.setattr("oma_switch.cli.PROFILES_DIR", fake_profiles)
    monkeypatch.setattr("oma_switch.config_io.PROFILES_DIR", fake_profiles)

    fake_config_dir = tmp_path / "config"
    fake_config_dir.mkdir()
    fake_config_file = fake_config_dir / "config.json"
    monkeypatch.setattr("oma_switch.cli.CONFIG_FILE", fake_config_file)
    monkeypatch.setattr("oma_switch.config_io.CONFIG_FILE", fake_config_file)

    return fake_fallbacks, fake_config_file


def test_list(tmp_path, monkeypatch, capsys, sample_fallback_data):
    """2 fallbacks exist, one is current → output shows both names, one with '*'."""
    fake_fallbacks, fake_config_file = tmp_path / "fallbacks", tmp_path / "config" / "config.json"

    save_fallback_json("alpha", sample_fallback_data)
    save_fallback_json("beta", sample_fallback_data)

    config = {"current": None, "profiles": {}, "current_fallback": "alpha"}
    fake_config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_config_file, "w") as f:
        json.dump(config, f)

    monkeypatch.setattr("oma_switch.cli.CONFIG_FILE", fake_config_file)
    monkeypatch.setattr("oma_switch.cli.FALLBACKS_DIR", fake_fallbacks)
    monkeypatch.setattr("oma_switch.config_io.CONFIG_FILE", fake_config_file)
    monkeypatch.setattr("oma_switch.config_io.FALLBACKS_DIR", fake_fallbacks)

    cmd_fallback_list([])

    captured = capsys.readouterr()
    assert "alpha" in captured.out
    assert "beta" in captured.out
    assert "*" in captured.out
    assert "alpha *" in captured.out or "alpha*" in captured.out


def test_list_empty(capsys):
    """No fallback files → output contains '暂无'."""
    cmd_fallback_list([])

    captured = capsys.readouterr()
    assert "暂无" in captured.out


# ── cmd_fallback_create tests ──────────────────────────────────────

MOCK_TEMPLATE = {
    "主模型": {("agents", "sisyphus")},
    "强模型": {("agents", "oracle")},
    "中模型": {("agents", "sisyphus-junior")},
    "弱模型": {("agents", "explore")},
    "多模态模型": {("agents", "multimodal-looker")},
}

MOCK_MODELS = ["model-a", "model-b", "model-c"]
MOCK_ENRICHED = [(m, None, 0) for m in MOCK_MODELS]


@patch("oma_switch.cli.collect_models_enriched", return_value=MOCK_ENRICHED)
@patch("oma_switch.cli.collect_all_models", return_value=MOCK_MODELS)
@patch("oma_switch.cli.load_template", return_value=MOCK_TEMPLATE)
def test_create(mock_template, mock_collect, mock_enriched, monkeypatch, capsys):
    """Create a fallback config with mocked inputs, verify file and content."""
    inputs = iter(["1", "1", "1", "1", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    cmd_fallback_create(["my-fb"])

    # File should exist and be valid
    loaded = load_fallback_json("my-fb")
    assert loaded is not None

    # Should pass validation
    ok, err = validate_fallback_config(loaded)
    assert ok, f"Validation failed: {err}"

    # Each category should have model-a
    for category in MOCK_TEMPLATE:
        assert category in loaded
        models = loaded[category]["fallback_models"]
        assert len(models) == 1
        assert models[0] == "model-a"

    # Success message printed
    out = capsys.readouterr().out
    assert "已创建 fallback 配置 'my-fb'" in out


@patch("oma_switch.cli.collect_all_models", return_value=MOCK_MODELS)
@patch("oma_switch.cli.load_template", return_value=MOCK_TEMPLATE)
def test_create_duplicate(mock_template, mock_collect, monkeypatch, capsys):
    """Creating with duplicate name should error with '已存在'."""
    inputs1 = iter(["1", "1", "1", "1", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs1))
    cmd_fallback_create(["dup-fb"])

    with pytest.raises(SystemExit) as exc_info:
        cmd_fallback_create(["dup-fb"])

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "已存在" in out


def test_create_empty_name(capsys):
    """Empty name should error immediately."""
    with pytest.raises(SystemExit) as exc_info:
        cmd_fallback_create([""])

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "不能为空" in out


def test_create_no_args(capsys):
    """No arguments should show usage and exit."""
    with pytest.raises(SystemExit) as exc_info:
        cmd_fallback_create([])

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "用法" in out


@patch("oma_switch.cli.collect_all_models", return_value=MOCK_MODELS)
@patch("oma_switch.cli.load_template", return_value=MOCK_TEMPLATE)
def test_create_does_not_set_current(mock_template, mock_collect, monkeypatch):
    """Created fallback should NOT be set as current."""
    inputs = iter(["1", "1", "1", "1", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    cmd_fallback_create(["no-current"])

    loaded = load_fallback_json("no-current")
    assert loaded is not None


def test_view_named(capsys, sample_fallback_data):
    """指定名称查看 fallback 配置，应显示分类名称。"""
    save_fallback_json("my-chain", sample_fallback_data)

    cmd_fallback_view(["my-chain"])

    output = capsys.readouterr().out
    assert "主模型" in output
    assert "强模型" in output
    assert "中模型" in output
    assert "弱模型" in output
    assert "多模态模型" in output


def test_view_no_current(tmp_path, monkeypatch, capsys):
    """没有当前 fallback 且不提供名称，应显示错误信息。"""
    config = load_config()
    config["current_fallback"] = ""
    save_config(config)

    cmd_fallback_view([])

    output = capsys.readouterr().out
    assert "当前没有激活的 fallback 配置" in output


# ── cmd_fallback_diff tests ──────────────────────────────────────

MOCK_TEMPLATE_FOR_DIFF = {
    "主模型": {("agents", "sisyphus")},
    "强模型": {("agents", "oracle")},
    "中模型": {("agents", "sisyphus-junior")},
    "弱模型": {("agents", "explore")},
    "多模态模型": {("agents", "multimodal-looker")},
}


@patch("oma_switch.cli.load_template", return_value=MOCK_TEMPLATE_FOR_DIFF)
def test_diff(mock_template, capsys):
    """Two fallbacks with different chains → output shows '不同' for differing categories."""
    data_a = {
        "主模型": {"fallback_models": ["model-a"]},
        "强模型": {"fallback_models": ["model-b"]},
        "中模型": {"fallback_models": []},
        "弱模型": {"fallback_models": ["model-c"]},
        "多模态模型": {"fallback_models": []},
    }
    data_b = {
        "主模型": {"fallback_models": ["model-x"]},
        "强模型": {"fallback_models": ["model-b"]},
        "中模型": {"fallback_models": []},
        "弱模型": {"fallback_models": ["model-c"]},
        "多模态模型": {"fallback_models": []},
    }
    save_fallback_json("chain-a", data_a)
    save_fallback_json("chain-b", data_b)

    cmd_fallback_diff(["chain-a", "chain-b"])

    output = capsys.readouterr().out
    # 主模型 differs
    assert "主模型" in output
    assert "不同" in output
    assert "model-a" in output
    assert "model-x" in output
    # 强模型 same → 一致
    assert "一致" in output


@patch("oma_switch.cli.load_template", return_value=MOCK_TEMPLATE_FOR_DIFF)
def test_diff_same(mock_template, capsys):
    """Two identical fallbacks → output shows '一致' for all categories."""
    data = {
        "主模型": {"fallback_models": ["model-a"]},
        "强模型": {"fallback_models": ["model-b"]},
        "中模型": {"fallback_models": []},
        "弱模型": {"fallback_models": ["model-c"]},
        "多模态模型": {"fallback_models": ["model-d"]},
    }
    save_fallback_json("same-1", data)
    save_fallback_json("same-2", data)

    cmd_fallback_diff(["same-1", "same-2"])

    output = capsys.readouterr().out
    assert "不同" not in output
    assert output.count("一致") == 5  # 5 categories all match


# ── cmd_fallback_switch tests ──────────────────────────────────────

SWITCH_TEMPLATE = {
    "主模型": {("agents", "sisyphus"), ("agents", "hephaestus")},
    "强模型": {("agents", "oracle")},
}


def _write_oma_config(data: dict) -> None:
    cli.OMA_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    cli.OMA_CONFIG.write_text(json.dumps(data), encoding="utf-8")


def _read_oma_config() -> dict:
    return json.loads(cli.OMA_CONFIG.read_text(encoding="utf-8"))


@pytest.fixture
def switch_setup(tmp_path, monkeypatch):
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
    monkeypatch.setattr(cli, "load_template", lambda: SWITCH_TEMPLATE)
    monkeypatch.setattr(cli_helpers_mod, "OMA_CONFIG", fake_opencode_dir / "oh-my-openagent.json")
    monkeypatch.setattr(cli_helpers_mod, "load_template", lambda: SWITCH_TEMPLATE)

    monkeypatch.setattr("oma_switch.config_io.CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr("oma_switch.config_io.PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr("oma_switch.config_io.FALLBACKS_DIR", fake_fallbacks_dir)

    config = {"current": None, "profiles": {}, "current_fallback": ""}
    with open(fake_config_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f)

    return fake_home


def test_switch(switch_setup):
    existing_oma = {
        "agents": {
            "sisyphus": {"model": "gpt-4"},
            "hephaestus": {"model": "gpt-4"},
            "oracle": {"model": "claude-3"},
        },
    }
    _write_oma_config(existing_oma)

    fallback_data = {
        "主模型": {"fallback_models": ["model-a", "model-b"]},
        "强模型": {"fallback_models": ["model-c"]},
    }
    cli.save_fallback_json("my-chain", fallback_data)

    cmd_fallback_switch(["my-chain"])

    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["fallback_models"] == ["model-a", "model-b"]
    assert result["agents"]["hephaestus"]["fallback_models"] == ["model-a", "model-b"]
    assert result["agents"]["oracle"]["fallback_models"] == ["model-c"]
    assert result["agents"]["sisyphus"]["model"] == "gpt-4"
    assert result["agents"]["oracle"]["model"] == "claude-3"
    assert result["model_fallback"] is True

    config = load_config()
    assert config["current_fallback"] == "my-chain"
    assert config["current"] is None


def test_switch_nonexistent(switch_setup, capsys):
    with pytest.raises(SystemExit) as exc_info:
        cmd_fallback_switch(["nonexistent"])

    assert exc_info.value.code == 1
    output = capsys.readouterr().out
    assert "不存在" in output


def test_switch_empty_chain(switch_setup):
    existing_oma = {
        "agents": {
            "sisyphus": {"model": "gpt-4", "fallback_models": ["old-model"]},
            "hephaestus": {"model": "gpt-4"},
            "oracle": {"model": "claude-3"},
        },
    }
    _write_oma_config(existing_oma)

    fallback_data = {
        "主模型": {"fallback_models": []},
        "强模型": {"fallback_models": []},
    }
    cli.save_fallback_json("empty-chain", fallback_data)

    cmd_fallback_switch(["empty-chain"])

    result = _read_oma_config()
    assert "fallback_models" not in result["agents"]["sisyphus"]
    assert result["agents"]["sisyphus"]["model"] == "gpt-4"
    assert result["model_fallback"] is False

    config = load_config()
    assert config["current_fallback"] == "empty-chain"


# ── cmd_fallback_rm tests ────────────────────────────────────────


def test_rm(tmp_path, monkeypatch, capsys, sample_fallback_data):
    fake_fallbacks, fake_config_file = tmp_path / "fallbacks", tmp_path / "config" / "config.json"

    save_fallback_json("to-delete", sample_fallback_data)
    save_fallback_json("other", sample_fallback_data)

    config = {"current": None, "profiles": {}, "current_fallback": "other"}
    fake_config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_config_file, "w") as f:
        json.dump(config, f)

    monkeypatch.setattr("oma_switch.cli.CONFIG_FILE", fake_config_file)
    monkeypatch.setattr("oma_switch.cli.FALLBACKS_DIR", fake_fallbacks)
    monkeypatch.setattr("oma_switch.config_io.CONFIG_FILE", fake_config_file)
    monkeypatch.setattr("oma_switch.config_io.FALLBACKS_DIR", fake_fallbacks)

    monkeypatch.setattr("builtins.input", lambda _: "y")

    cmd_fallback_rm(["to-delete"])

    assert load_fallback_json("to-delete") is None
    assert load_fallback_json("other") is not None
    reloaded = load_config()
    assert reloaded["current_fallback"] == "other"
    out = capsys.readouterr().out
    assert "已删除 fallback 配置 'to-delete'" in out


def test_rm_current(tmp_path, monkeypatch, capsys, sample_fallback_data):
    fake_fallbacks, fake_config_file = tmp_path / "fallbacks", tmp_path / "config" / "config.json"

    save_fallback_json("current-one", sample_fallback_data)

    config = {"current": None, "profiles": {}, "current_fallback": "current-one"}
    fake_config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_config_file, "w") as f:
        json.dump(config, f)

    monkeypatch.setattr("oma_switch.cli.CONFIG_FILE", fake_config_file)
    monkeypatch.setattr("oma_switch.cli.FALLBACKS_DIR", fake_fallbacks)
    monkeypatch.setattr("oma_switch.config_io.CONFIG_FILE", fake_config_file)
    monkeypatch.setattr("oma_switch.config_io.FALLBACKS_DIR", fake_fallbacks)

    monkeypatch.setattr("builtins.input", lambda _: "y")

    cmd_fallback_rm(["current-one"])

    assert load_fallback_json("current-one") is None
    reloaded = load_config()
    assert reloaded["current_fallback"] == ""
    out = capsys.readouterr().out
    assert "已自动取消激活" in out
    assert "已删除 fallback 配置 'current-one'" in out


# ── cmd_fallback_edit tests ──────────────────────────────────────

EDIT_INITIAL_DATA = {
    "主模型": {"fallback_models": ["model-a"]},
    "强模型": {"fallback_models": []},
    "中模型": {"fallback_models": []},
    "弱模型": {"fallback_models": []},
    "多模态模型": {"fallback_models": []},
}


@patch("oma_switch.cli.collect_models_enriched", return_value=MOCK_ENRICHED)
@patch("oma_switch.cli.collect_all_models", return_value=MOCK_MODELS)
@patch("oma_switch.cli.load_template", return_value=MOCK_TEMPLATE)
def test_edit_current(mock_template, mock_collect, mock_enriched, tmp_path, monkeypatch, capsys):
    """编辑当前 fallback → 文件已更新 + OMA 配置同步"""
    fake_config_file = tmp_path / "config" / "config.json"

    fake_oma = tmp_path / "opencode" / "oh-my-openagent.json"
    fake_oma.parent.mkdir(parents=True)
    fake_oma.write_text(
        json.dumps({"agents": {"sisyphus": {"model": "model-x"}}}), encoding="utf-8"
    )
    monkeypatch.setattr("oma_switch.cli.OMA_CONFIG", fake_oma)
    monkeypatch.setattr("oma_switch.cli_helpers.OMA_CONFIG", fake_oma)

    save_fallback_json("my-fb", EDIT_INITIAL_DATA)

    config = {"current": None, "profiles": {}, "current_fallback": "my-fb"}
    with open(fake_config_file, "w") as f:
        json.dump(config, f)

    inputs = iter(["2", "2", "2", "2", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    cmd_fallback_edit(["my-fb"])

    loaded = load_fallback_json("my-fb")
    assert loaded is not None
    for cat in MOCK_TEMPLATE:
        assert loaded[cat]["fallback_models"] == ["model-b"]

    oma = json.loads(fake_oma.read_text(encoding="utf-8"))
    assert oma["agents"]["sisyphus"]["fallback_models"] == ["model-b"]

    out = capsys.readouterr().out
    assert "已更新 fallback 配置 'my-fb'" in out
    assert "已同步到 OMA 配置文件" in out


@patch("oma_switch.cli.collect_models_enriched", return_value=MOCK_ENRICHED)
@patch("oma_switch.cli.collect_all_models", return_value=MOCK_MODELS)
@patch("oma_switch.cli.load_template", return_value=MOCK_TEMPLATE)
def test_edit_non_current(
    mock_template, mock_collect, mock_enriched, tmp_path, monkeypatch, capsys
):
    """编辑非当前 fallback → 文件已更新 + OMA 配置不变"""
    fake_config_file = tmp_path / "config" / "config.json"

    fake_oma = tmp_path / "opencode" / "oh-my-openagent.json"
    fake_oma.parent.mkdir(parents=True)
    fake_oma.write_text(
        json.dumps({"agents": {"sisyphus": {"model": "model-x"}}}), encoding="utf-8"
    )
    monkeypatch.setattr("oma_switch.cli.OMA_CONFIG", fake_oma)
    monkeypatch.setattr("oma_switch.cli_helpers.OMA_CONFIG", fake_oma)

    save_fallback_json("my-fb", EDIT_INITIAL_DATA)

    config = {"current": None, "profiles": {}, "current_fallback": "other"}
    with open(fake_config_file, "w") as f:
        json.dump(config, f)

    inputs = iter(["2", "2", "2", "2", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    cmd_fallback_edit(["my-fb"])

    loaded = load_fallback_json("my-fb")
    assert loaded is not None
    for cat in MOCK_TEMPLATE:
        assert loaded[cat]["fallback_models"] == ["model-b"]

    oma = json.loads(fake_oma.read_text(encoding="utf-8"))
    assert "fallback_models" not in oma["agents"]["sisyphus"]

    out = capsys.readouterr().out
    assert "已更新 fallback 配置 'my-fb'" in out
    assert "已同步到 OMA 配置文件" not in out


# ── cmd_fallback dispatch tests ──────────────────────────────────


def test_fallback_dispatch_list(capsys):
    """cmd_fallback(['list']) should dispatch without error."""
    cmd_fallback(["list"])
    captured = capsys.readouterr()
    assert captured.out  # non-empty output (either "暂无" or listing)


def test_fallback_dispatch_help(capsys):
    """cmd_fallback(['help']) should print help info."""
    cmd_fallback(["help"])
    captured = capsys.readouterr()
    assert "Fallback 链管理" in captured.out


def test_fallback_dispatch_no_args(capsys):
    """cmd_fallback([]) should print help (no crash)."""
    cmd_fallback([])
    captured = capsys.readouterr()
    assert "Fallback 链管理" in captured.out


def test_fallback_dispatch_unknown(capsys):
    """cmd_fallback(['bogus']) should error about unknown subcommand."""
    cmd_fallback(["bogus"])
    captured = capsys.readouterr()
    assert "未知子命令" in captured.out


# ── cmd_list fallback display tests ─────────────────────────────


def test_list_shows_fallback(tmp_path, monkeypatch, capsys):
    """cmd_list should display the current fallback name at the end."""
    config = {"current": None, "profiles": {}, "current_fallback": "my-chain"}
    fake_config_file = tmp_path / "config" / "config.json"
    fake_config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_config_file, "w") as f:
        json.dump(config, f)
    monkeypatch.setattr("oma_switch.cli.CONFIG_FILE", fake_config_file)
    monkeypatch.setattr("oma_switch.config_io.CONFIG_FILE", fake_config_file)

    cmd_list([])

    output = capsys.readouterr().out
    assert "my-chain" in output


def test_list_shows_fallback_unset(tmp_path, monkeypatch, capsys):
    """cmd_list should display '(未设置)' when no fallback is set."""
    config = {"current": None, "profiles": {}, "current_fallback": ""}
    fake_config_file = tmp_path / "config" / "config.json"
    fake_config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_config_file, "w") as f:
        json.dump(config, f)
    monkeypatch.setattr("oma_switch.cli.CONFIG_FILE", fake_config_file)
    monkeypatch.setattr("oma_switch.config_io.CONFIG_FILE", fake_config_file)

    cmd_list([])

    output = capsys.readouterr().out
    assert "未设置" in output


# ── cmd_switch fallback re-injection tests ────────────────────────


def _setup_profile_for_switch(switch_setup, profile_name="test-profile"):
    """Helper: create a profile file and register it in config."""
    profile_data = {
        "agents": {
            "sisyphus": {"model": "new-model"},
            "hephaestus": {"model": "new-model"},
            "oracle": {"model": "new-claude"},
        },
    }
    profile_path = cli.PROFILES_DIR / f"{profile_name}.json"
    profile_path.write_text(json.dumps(profile_data), encoding="utf-8")

    config = load_config()
    config["profiles"][profile_name] = {"last_used": None}
    save_config(config)

    return profile_path


def test_switch_profile_preserves_fallback(switch_setup):
    """Profile switch with current fallback → fallback_models re-injected into OMA config."""
    _setup_profile_for_switch(switch_setup)

    fallback_data = {
        "主模型": {"fallback_models": ["fb-model-a", "fb-model-b"]},
        "强模型": {"fallback_models": ["fb-model-c"]},
    }
    save_fallback_json("my-chain", fallback_data)

    config = load_config()
    config["current_fallback"] = "my-chain"
    save_config(config)

    existing_oma = {
        "agents": {
            "sisyphus": {"model": "old-model"},
            "oracle": {"model": "old-claude"},
        },
    }
    _write_oma_config(existing_oma)

    cmd_switch(["test-profile"])

    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["model"] == "new-model"
    assert result["agents"]["sisyphus"]["fallback_models"] == ["fb-model-a", "fb-model-b"]
    assert result["agents"]["hephaestus"]["fallback_models"] == ["fb-model-a", "fb-model-b"]
    assert result["agents"]["oracle"]["fallback_models"] == ["fb-model-c"]
    assert result["model_fallback"] is True


def test_switch_profile_no_fallback(switch_setup, capsys):
    """Profile switch with no current fallback → no error, no fallback_models in OMA config."""
    _setup_profile_for_switch(switch_setup, "no-fb-profile")

    config = load_config()
    config["current_fallback"] = ""
    save_config(config)

    existing_oma = {
        "agents": {
            "sisyphus": {"model": "old-model", "fallback_models": ["stale-fb"]},
            "oracle": {"model": "old-claude"},
        },
    }
    _write_oma_config(existing_oma)

    cmd_switch(["no-fb-profile"])

    result = _read_oma_config()
    assert result["agents"]["sisyphus"]["model"] == "new-model"
    assert "fallback_models" not in result["agents"]["sisyphus"]
    assert "model_fallback" not in result

    out = capsys.readouterr().out
    assert "已切换到配置文件 'no-fb-profile'" in out
