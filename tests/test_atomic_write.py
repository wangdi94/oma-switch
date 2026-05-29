"""Tests for _atomic_write_json in oma_switch.cli.

Covers: normal write, failure/cleanup, permission preservation, JSON formatting.
"""

import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, "src")

import oma_switch.cli as cli
import oma_switch.config_io as config_io_mod
import oma_switch.version as version_mod


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

    monkeypatch.setattr(config_io_mod, "CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr(config_io_mod, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(config_io_mod, "FALLBACKS_DIR", fake_fallbacks_dir)

    return fake_home


# ── Tests ──────────────────────────────────────────────────────────


class TestAtomicWriteJsonNormal:
    """正常写入场景。"""

    def test_write_creates_file_with_correct_content(self, isolated_config_dir):
        """写入 JSON 数据，验证文件内容正确。"""
        target = isolated_config_dir / "test_output.json"
        data = {"key": "value", "nested": {"a": 1, "b": [2, 3]}}

        cli._atomic_write_json(target, data)

        assert target.exists()
        with open(target, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data

    def test_write_empty_dict(self, isolated_config_dir):
        """空字典写入。"""
        target = isolated_config_dir / "empty.json"
        cli._atomic_write_json(target, {})

        with open(target, "r") as f:
            assert json.load(f) == {}

    def test_write_overwrites_existing_file(self, isolated_config_dir):
        """覆盖已有文件。"""
        target = isolated_config_dir / "overwrite.json"
        target.write_text('{"old": true}')

        cli._atomic_write_json(target, {"new": True})

        with open(target, "r") as f:
            loaded = json.load(f)
        assert loaded == {"new": True}

    def test_write_special_characters(self, isolated_config_dir):
        """包含特殊字符（中文、emoji、换行）。"""
        target = isolated_config_dir / "special.json"
        data = {"中文": "值", "emoji": "🎉", "newline": "a\nb\tc"}

        cli._atomic_write_json(target, data)

        with open(target, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data

    def test_write_indent_format(self, isolated_config_dir):
        """验证 indent 参数生效。"""
        target = isolated_config_dir / "indent.json"
        data = {"a": 1, "b": 2}

        cli._atomic_write_json(target, data, indent=4)

        content = target.read_text(encoding="utf-8")
        assert "    " in content  # 4-space indent
        assert json.loads(content) == data

    def test_write_ensure_ascii_true(self, isolated_config_dir):
        """验证 ensure_ascii=True 将中文转义为 \\uXXXX。"""
        target = isolated_config_dir / "ascii.json"
        data = {"中文": "值"}

        cli._atomic_write_json(target, data, ensure_ascii=True)

        content = target.read_text(encoding="utf-8")
        assert "\\u" in content  # 中文被转义
        assert json.loads(content) == data  # 但解析后等价

    def test_write_ensure_ascii_false(self, isolated_config_dir):
        """验证 ensure_ascii=False 保留原始字符。"""
        target = isolated_config_dir / "utf8.json"
        data = {"中文": "值"}

        cli._atomic_write_json(target, data, ensure_ascii=False)

        content = target.read_text(encoding="utf-8")
        assert "中文" in content

    def test_nested_complex_structure(self, isolated_config_dir):
        """复杂嵌套结构。"""
        target = isolated_config_dir / "complex.json"
        data = {
            "list": [1, "two", {"three": 3}],
            "null_val": None,
            "bool_val": True,
        }

        cli._atomic_write_json(target, data)

        with open(target, "r") as f:
            assert json.load(f) == data


class TestAtomicWriteJsonFailure:
    """写入失败场景。"""

    def test_write_failure_raises_exception(self, isolated_config_dir):
        """模拟写入失败，验证异常被抛出。"""
        target = isolated_config_dir / "fail.json"

        with patch("oma_switch.cli.os.fsync", side_effect=OSError("fsync failed")):
            with pytest.raises(OSError, match="fsync failed"):
                cli._atomic_write_json(target, {"data": 1})

    def test_write_failure_preserves_original_file(self, isolated_config_dir):
        """写入失败时，目标文件保持不变。"""
        target = isolated_config_dir / "preserve.json"
        original_content = '{"original": true}'
        target.write_text(original_content)

        with patch("oma_switch.cli.os.fsync", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                cli._atomic_write_json(target, {"should_not": "exist"})

        assert target.read_text() == original_content

    def test_write_failure_no_target_preserves_no_file(self, isolated_config_dir):
        """目标文件不存在时写入失败，不会残留文件。"""
        target = isolated_config_dir / "no残留.json"

        with patch("oma_switch.cli.os.fsync", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                cli._atomic_write_json(target, {"data": 1})

        assert not target.exists()


class TestAtomicWriteJsonTempCleanup:
    """临时文件清理。"""

    def test_no_temp_file_after_success(self, isolated_config_dir):
        """成功写入后，目录下不应有 .tmp 文件。"""
        target = isolated_config_dir / "clean.json"
        cli._atomic_write_json(target, {"ok": True})

        tmp_files = list(isolated_config_dir.glob("*.tmp"))
        assert tmp_files == []

    def test_no_temp_file_after_failure(self, isolated_config_dir):
        """写入失败后，.tmp 文件应被清理。"""
        target = isolated_config_dir / "clean_fail.json"

        with patch("oma_switch.cli.os.fsync", side_effect=OSError("fail")):
            with pytest.raises(OSError):
                cli._atomic_write_json(target, {"data": 1})

        tmp_files = list(isolated_config_dir.glob("*.tmp"))
        assert tmp_files == []


class TestAtomicWriteJsonPermissions:
    """文件权限保留。"""

    def test_permissions_preserved_on_existing_file(self, isolated_config_dir):
        """写入后保留原文件权限。"""
        target = isolated_config_dir / "perms.json"
        target.write_text('{"old": 1}')
        # 设置特定权限（仅 owner 读写）
        os.chmod(target, 0o600)

        cli._atomic_write_json(target, {"new": 1})

        mode = stat.S_IMODE(os.stat(target).st_mode)
        assert mode == 0o600

    def test_new_file_gets_default_permissions(self, isolated_config_dir):
        """新文件使用系统默认 umask 权限。"""
        target = isolated_config_dir / "new_perms.json"

        cli._atomic_write_json(target, {"data": 1})

        # 新文件应该存在且可读
        assert target.exists()
        assert os.access(target, os.R_OK)

    def test_permissions_various(self, isolated_config_dir):
        """不同权限值均被保留。"""
        target = isolated_config_dir / "perms_various.json"
        target.write_text("{}")

        for mode in [0o644, 0o600, 0o400, 0o755]:
            os.chmod(target, mode)
            cli._atomic_write_json(target, {"mode": oct(mode)})
            actual = stat.S_IMODE(os.stat(target).st_mode)
            assert actual == mode, f"Expected {oct(mode)}, got {oct(actual)}"


class TestAtomicWriteJsonIdempotent:
    """幂等性和一致性。"""

    def test_multiple_writes_same_content(self, isolated_config_dir):
        """多次写入相同内容，结果一致。"""
        target = isolated_config_dir / "idem.json"
        data = {"version": 1, "items": ["a", "b"]}

        for _ in range(3):
            cli._atomic_write_json(target, data)

        with open(target, "r") as f:
            assert json.load(f) == data

    def test_sequential_writes_update_content(self, isolated_config_dir):
        """连续写入不同内容，文件始终是最新的。"""
        target = isolated_config_dir / "seq.json"

        for i in range(5):
            cli._atomic_write_json(target, {"i": i})

        with open(target, "r") as f:
            assert json.load(f) == {"i": 4}
