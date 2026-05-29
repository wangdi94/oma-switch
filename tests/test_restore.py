"""Tests for restore commands in oma_switch.cli.

Covers: cmd_restore, _show_restore_list, _show_file_versions, _restore_version.
"""

import sys
import json
import pytest
from pathlib import Path

sys.path.insert(0, "src")

import oma_switch.cli as cli
import oma_switch.version as version_mod


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    """Patch Path.home() AND all module-level config constants to a tmp directory."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    fake_config_dir = fake_home / ".config" / "oma-switch"
    fake_profiles_dir = fake_config_dir / "profiles"
    fake_fallbacks_dir = fake_config_dir / "fallbacks"
    fake_opencode_dir = fake_home / ".config" / "opencode"
    fake_config_dir.mkdir(parents=True)
    fake_profiles_dir.mkdir(parents=True)
    fake_fallbacks_dir.mkdir(parents=True)
    fake_opencode_dir.mkdir(parents=True)

    monkeypatch.setattr(cli, "CONFIG_DIR", fake_config_dir)
    monkeypatch.setattr(cli, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(cli, "FALLBACKS_DIR", fake_fallbacks_dir)
    monkeypatch.setattr(cli, "CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr(cli, "TEMPLATE_FILE", fake_config_dir / "template.json")
    monkeypatch.setattr(cli, "HISTORY_FILE", fake_config_dir / "history.json")
    monkeypatch.setattr(cli, "OMA_CONFIG", fake_opencode_dir / "oh-my-openagent.json")
    monkeypatch.setattr(cli, "OPENCODE_DIR", fake_opencode_dir)
    monkeypatch.setattr(cli, "DCP_CONFIG_FILE", fake_opencode_dir / "dcp.jsonc")

    monkeypatch.setattr(version_mod, "CONFIG_DIR", fake_config_dir)

    return fake_home


# ── Helpers ────────────────────────────────────────────────────────


def _create_fake_version(filepath: Path, data: dict, timestamp: str, operation: str = "test_op") -> None:
    """Create a fake version snapshot (file + metadata) in the versions directory."""
    version_dir = cli.CONFIG_DIR / ".versions" / filepath.name
    version_dir.mkdir(parents=True, exist_ok=True)

    version_file = version_dir / f"{filepath.stem}.{timestamp}{filepath.suffix}"
    version_file.write_text(json.dumps(data), encoding="utf-8")

    meta_file = version_dir / f"{filepath.stem}.{timestamp}.meta.json"
    meta = {
        "timestamp": timestamp,
        "operation": operation,
        "command_args": [],
        "file_path": str(filepath),
        "file_size": version_file.stat().st_size,
        "file_hash": "sha256:abc123",
    }
    meta_file.write_text(json.dumps(meta), encoding="utf-8")


# ── _show_restore_list ────────────────────────────────────────────


def test_show_restore_list_no_versions_dir(isolated_config_dir, capsys):
    """_show_restore_list warns when .versions dir doesn't exist."""
    cli._show_restore_list()
    captured = capsys.readouterr()
    assert "没有找到任何版本历史" in captured.out


def test_show_restore_list_empty_versions_dir(isolated_config_dir, capsys):
    """_show_restore_list warns when .versions dir is empty."""
    versions_dir = cli.CONFIG_DIR / ".versions"
    versions_dir.mkdir(exist_ok=True)

    cli._show_restore_list()
    captured = capsys.readouterr()
    assert "没有找到任何版本历史" in captured.out


def test_show_restore_list_with_versions(isolated_config_dir, capsys):
    """_show_restore_list displays file names and version counts."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    _create_fake_version(target, {"key": "v1"}, "20260101_120000", "create")
    _create_fake_version(target, {"key": "v2"}, "20260101_130000", "edit")

    cli._show_restore_list()
    captured = capsys.readouterr()
    assert "可恢复的文件" in captured.out
    assert "test.json" in captured.out
    assert "2 个版本" in captured.out


# ── _show_file_versions ───────────────────────────────────────────


def test_show_file_versions_no_versions(isolated_config_dir, capsys):
    """_show_file_versions warns when file has no version history."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    cli._show_file_versions(target)
    captured = capsys.readouterr()
    assert "没有版本历史" in captured.out


def test_show_file_versions_with_versions(isolated_config_dir, capsys):
    """_show_file_versions lists versions with timestamps and operations."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    _create_fake_version(target, {"key": "v1"}, "20260101_120000", "create")
    _create_fake_version(target, {"key": "v2"}, "20260101_130000", "edit")

    cli._show_file_versions(target)
    captured = capsys.readouterr()
    assert "test.json 的版本历史" in captured.out
    assert "20260101_130000" in captured.out  # newest first
    assert "20260101_120000" in captured.out
    assert "edit" in captured.out
    assert "create" in captured.out


# ── _restore_version ──────────────────────────────────────────────


def test_restore_version_no_history(isolated_config_dir):
    """_restore_version returns False when file has no version history."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    assert cli._restore_version(target, "1") is False


def test_restore_version_invalid_index(isolated_config_dir):
    """_restore_version returns False for out-of-range index."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    _create_fake_version(target, {"key": "v1"}, "20260101_120000")

    assert cli._restore_version(target, "99") is False


def test_restore_version_not_found(isolated_config_dir):
    """_restore_version returns False for non-existent timestamp."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    _create_fake_version(target, {"key": "v1"}, "20260101_120000")

    assert cli._restore_version(target, "nonexistent_timestamp") is False


def test_restore_version_user_cancel(isolated_config_dir, monkeypatch):
    """_restore_version returns False when user declines confirmation."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    _create_fake_version(target, {"key": "v1"}, "20260101_120000")

    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert cli._restore_version(target, "1") is False


def test_restore_version_success_by_index(isolated_config_dir, monkeypatch):
    """_restore_version restores file content by version index."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    _create_fake_version(target, {"key": "restored_value"}, "20260101_120000", "create")

    monkeypatch.setattr("builtins.input", lambda _: "y")
    result = cli._restore_version(target, "1")
    assert result is True

    restored = json.loads(target.read_text(encoding="utf-8"))
    assert restored == {"key": "restored_value"}


def test_restore_version_success_by_timestamp(isolated_config_dir, monkeypatch):
    """_restore_version restores file by timestamp when version_id isn't numeric."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    # Must use a timestamp with non-digit chars (e.g., hyphens/colons) so int()
    # raises ValueError and the timestamp matching branch is reached.
    # Standard %Y%m%d_%H%M%S format is parseable by int() in Python 3.6+,
    # which means the timestamp branch is effectively dead code for that format.
    _create_fake_version(target, {"key": "ts_restored"}, "2026-01-01_12:00:00", "create")

    monkeypatch.setattr("builtins.input", lambda _: "y")
    result = cli._restore_version(target, "2026-01-01_12:00:00")
    assert result is True

    restored = json.loads(target.read_text(encoding="utf-8"))
    assert restored == {"key": "ts_restored"}


def test_restore_version_creates_backup_before_restore(isolated_config_dir, monkeypatch):
    """_restore_version creates a pre_restore snapshot before overwriting."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    target.write_text(json.dumps({"key": "original"}), encoding="utf-8")

    _create_fake_version(target, {"key": "v1"}, "20260101_120000", "create")

    monkeypatch.setattr("builtins.input", lambda _: "y")
    cli._restore_version(target, "1")

    # Check that a pre_restore version was created
    version_dir = cli.CONFIG_DIR / ".versions" / target.name
    meta_files = list(version_dir.glob("*.meta.json"))
    operations = []
    for mf in meta_files:
        meta = json.loads(mf.read_text(encoding="utf-8"))
        operations.append(meta.get("operation", ""))
    assert "pre_restore" in operations


def test_restore_version_user_yes_input(isolated_config_dir, monkeypatch):
    """_restore_version accepts 'yes' as confirmation."""
    target = cli.CONFIG_DIR / "profiles" / "test.json"
    _create_fake_version(target, {"key": "yes_val"}, "20260101_120000")

    monkeypatch.setattr("builtins.input", lambda _: "yes")
    result = cli._restore_version(target, "1")
    assert result is True

    restored = json.loads(target.read_text(encoding="utf-8"))
    assert restored == {"key": "yes_val"}


# ── cmd_restore ───────────────────────────────────────────────────


def test_cmd_restore_no_args_shows_list(isolated_config_dir, capsys):
    """cmd_restore with no args calls _show_restore_list."""
    cli.cmd_restore([])
    captured = capsys.readouterr()
    # Without .versions dir, should warn about no history
    assert "没有找到任何版本历史" in captured.out


def test_cmd_restore_single_arg_shows_versions(isolated_config_dir, capsys):
    """cmd_restore with one arg calls _show_file_versions."""
    target = cli.CONFIG_DIR / "profiles" / "config.json"
    _create_fake_version(target, {"data": 1}, "20260101_120000", "create")

    cli.cmd_restore(["config.json"])
    captured = capsys.readouterr()
    assert "config.json 的版本历史" in captured.out


def test_cmd_restore_two_args_restores_version(isolated_config_dir, monkeypatch):
    """cmd_restore with two args calls _restore_version."""
    target = cli.CONFIG_DIR / "profiles" / "config.json"
    _create_fake_version(target, {"data": "restored"}, "20260101_120000", "create")

    monkeypatch.setattr("builtins.input", lambda _: "y")
    cli.cmd_restore(["config.json", "1"])

    restored = json.loads(target.read_text(encoding="utf-8"))
    assert restored == {"data": "restored"}


def test_cmd_restore_file_not_found(isolated_config_dir, monkeypatch):
    """cmd_restore exits with error when file doesn't exist."""
    with pytest.raises(SystemExit):
        cli.cmd_restore(["nonexistent.json"])


def test_cmd_restore_finds_in_profiles_dir(isolated_config_dir, capsys):
    """cmd_restore resolves filename in profiles/ directory."""
    target = cli.PROFILES_DIR / "my_profile.json"
    _create_fake_version(target, {"p": 1}, "20260101_120000", "create")

    cli.cmd_restore(["my_profile.json"])
    captured = capsys.readouterr()
    assert "my_profile.json 的版本历史" in captured.out


def test_cmd_restore_finds_in_fallbacks_dir(isolated_config_dir, capsys):
    """cmd_resolve resolves filename in fallbacks/ directory."""
    target = cli.FALLBACKS_DIR / "my_fallback.json"
    _create_fake_version(target, {"f": 1}, "20260101_120000", "create")

    cli.cmd_restore(["my_fallback.json"])
    captured = capsys.readouterr()
    assert "my_fallback.json 的版本历史" in captured.out


def test_cmd_restore_finds_via_versions_dir(isolated_config_dir, capsys):
    """cmd_restore resolves file when only .versions entry exists (file may not exist)."""
    target = cli.CONFIG_DIR / "config.json"
    _create_fake_version(target, {"c": 1}, "20260101_120000", "create")
    # Delete the actual file but keep versions
    target.unlink(missing_ok=True)

    cli.cmd_restore(["config.json"])
    captured = capsys.readouterr()
    # Should still find via versions dir and show version list
    assert "config.json 的版本历史" in captured.out
