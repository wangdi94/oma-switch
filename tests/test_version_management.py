"""Tests for version management functions in oma_switch.cli.

Covers: _get_version_dir, _create_version_snapshot, _rotate_versions,
_list_versions, _create_version_metadata, _validate_version_metadata,
_load_version_metadata.
"""

import sys
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

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

    # Also patch version module's CONFIG_DIR since version functions now live there
    monkeypatch.setattr(version_mod, "CONFIG_DIR", fake_config_dir)

    return fake_home


@pytest.fixture
def mock_incrementing_datetime():
    """Mock datetime.now() 返回递增的时间戳，避免同一秒内文件名冲突"""
    base = datetime(2026, 1, 1, 0, 0, 0)
    counter = [0]

    class _MockDatetime:
        @staticmethod
        def now(tz=None):
            result = base + timedelta(seconds=counter[0])
            counter[0] += 1
            return result

    with patch.object(cli, "datetime", _MockDatetime), \
         patch.object(version_mod, "datetime", _MockDatetime):
        yield


# ── Helpers ────────────────────────────────────────────────────────


def _make_test_file(config_dir: Path, name: str, data: dict) -> Path:
    """创建一个测试用 JSON 文件"""
    filepath = config_dir / name
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return filepath


# ── _get_version_dir 测试 ─────────────────────────────────────────


class TestGetVersionDir:
    """测试 _get_version_dir 函数"""

    def test_creates_version_dir(self, isolated_config_dir):
        """验证版本目录被正确创建"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = config_dir / "test-profile.json"

        version_dir = cli._get_version_dir(filepath)

        assert version_dir.exists()
        assert version_dir.is_dir()
        assert version_dir == config_dir / ".versions" / "test-profile.json"

    def test_creates_nested_structure(self, isolated_config_dir):
        """验证嵌套目录结构被正确创建"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = config_dir / "profiles" / "deep-nested.json"

        version_dir = cli._get_version_dir(filepath)

        assert version_dir.exists()
        assert version_dir.name == "deep-nested.json"

    def test_idempotent(self, isolated_config_dir):
        """验证重复调用不会出错"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = config_dir / "idempotent.json"

        dir1 = cli._get_version_dir(filepath)
        dir2 = cli._get_version_dir(filepath)

        assert dir1 == dir2
        assert dir1.exists()


# ── _create_version_snapshot 测试 ──────────────────────────────────


class TestCreateVersionSnapshot:
    """测试 _create_version_snapshot 函数"""

    def test_creates_snapshot(self, isolated_config_dir):
        """验证快照文件被正确创建"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "snapshot-test.json", {"key": "value"})

        cli._create_version_snapshot(filepath, "test_operation")

        version_dir = config_dir / ".versions" / "snapshot-test.json"
        snapshot_files = [
            p for p in version_dir.glob("snapshot-test.*.json")
            if not p.name.endswith(".meta.json")
        ]
        assert len(snapshot_files) == 1

    def test_creates_metadata_file(self, isolated_config_dir):
        """验证元数据文件被正确创建"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "meta-test.json", {"data": 123})

        cli._create_version_snapshot(filepath, "switch", ["profile-a"])

        version_dir = config_dir / ".versions" / "meta-test.json"
        meta_files = list(version_dir.glob("meta-test.*.meta.json"))
        assert len(meta_files) == 1

        with open(meta_files[0], "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["operation"] == "switch"
        assert meta["command_args"] == ["profile-a"]
        assert "timestamp" in meta
        assert "file_hash" in meta
        assert meta["file_hash"].startswith("sha256:")

    def test_no_snapshot_for_nonexistent_file(self, isolated_config_dir):
        """验证不存在的文件不会创建快照"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = config_dir / "nonexistent.json"

        cli._create_version_snapshot(filepath, "test")

        versions_dir = config_dir / ".versions"
        assert not versions_dir.exists() or not any(versions_dir.iterdir())

    def test_snapshot_preserves_content(self, isolated_config_dir):
        """验证快照保留原始文件内容"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        original_data = {"agents": {"sisyphus": {"model": "gpt-4"}}}
        filepath = _make_test_file(config_dir, "preserve-test.json", original_data)

        cli._create_version_snapshot(filepath, "create")

        version_dir = config_dir / ".versions" / "preserve-test.json"
        snapshot_files = [
            p for p in version_dir.glob("preserve-test.*.json")
            if not p.name.endswith(".meta.json")
        ]
        assert len(snapshot_files) == 1

        with open(snapshot_files[0], "r", encoding="utf-8") as f:
            snapshot_data = json.load(f)
        assert snapshot_data == original_data


# ── _rotate_versions 测试 ─────────────────────────────────────────


class TestRotateVersions:
    """测试 _rotate_versions 函数"""

    def test_no_rotation_when_under_limit(self, isolated_config_dir, mock_incrementing_datetime):
        """验证未超限时不删除任何版本"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "rotate-test.json", {"v": 1})

        # 创建 5 个快照（低于默认限制 10）
        for i in range(5):
            cli._create_version_snapshot(filepath, f"op-{i}")

        cli._rotate_versions(filepath)

        version_dir = config_dir / ".versions" / "rotate-test.json"
        version_files = [
            p for p in version_dir.glob("rotate-test.*.json")
            if not p.name.endswith(".meta.json")
        ]
        assert len(version_files) == 5

    def test_rotation_deletes_oldest(self, isolated_config_dir, mock_incrementing_datetime):
        """验证轮转删除最旧的版本"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "rotate-old.json", {"v": 1})

        # 创建 12 个快照（超过默认限制 10）
        for i in range(12):
            cli._create_version_snapshot(filepath, f"op-{i}")

        cli._rotate_versions(filepath)

        version_dir = config_dir / ".versions" / "rotate-old.json"
        version_files = [
            p for p in version_dir.glob("rotate-old.*.json")
            if not p.name.endswith(".meta.json")
        ]
        assert len(version_files) == 10

    def test_rotation_with_custom_limit(self, isolated_config_dir, mock_incrementing_datetime):
        """验证自定义限制正常工作"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "rotate-custom.json", {"v": 1})

        for i in range(8):
            cli._create_version_snapshot(filepath, f"op-{i}")

        cli._rotate_versions(filepath, max_versions=5)

        version_dir = config_dir / ".versions" / "rotate-custom.json"
        version_files = [
            p for p in version_dir.glob("rotate-custom.*.json")
            if not p.name.endswith(".meta.json")
        ]
        assert len(version_files) == 5

    def test_rotation_deletes_meta_files(self, isolated_config_dir, mock_incrementing_datetime):
        """验证轮转同时删除对应的元数据文件"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "rotate-meta.json", {"v": 1})

        for i in range(12):
            cli._create_version_snapshot(filepath, f"op-{i}")

        cli._rotate_versions(filepath)

        version_dir = config_dir / ".versions" / "rotate-meta.json"
        meta_files = list(version_dir.glob("rotate-meta.*.meta.json"))
        version_files = [
            p for p in version_dir.glob("rotate-meta.*.json")
            if not p.name.endswith(".meta.json")
        ]
        assert len(meta_files) == len(version_files) == 10


# ── _list_versions 测试 ───────────────────────────────────────────


class TestListVersions:
    """测试 _list_versions 函数"""

    def test_empty_when_no_versions(self, isolated_config_dir):
        """验证无版本时返回空列表"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = config_dir / "no-versions.json"

        versions = cli._list_versions(filepath)
        assert versions == []

    def test_empty_when_no_version_dir(self, isolated_config_dir):
        """验证版本目录不存在时返回空列表"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = config_dir / "no-dir.json"

        versions = cli._list_versions(filepath)
        assert versions == []

    def test_lists_all_versions(self, isolated_config_dir, mock_incrementing_datetime):
        """验证列出所有版本"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "list-test.json", {"v": 1})

        for i in range(3):
            cli._create_version_snapshot(filepath, f"op-{i}")

        versions = cli._list_versions(filepath)
        assert len(versions) == 3

    def test_versions_sorted_descending(self, isolated_config_dir, mock_incrementing_datetime):
        """验证版本按时间戳降序排序"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "sort-test.json", {"v": 1})

        for i in range(5):
            cli._create_version_snapshot(filepath, f"op-{i}")

        versions = cli._list_versions(filepath)
        timestamps = [v["timestamp"] for v in versions]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_version_metadata_populated(self, isolated_config_dir):
        """验证版本元数据被正确填充"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "meta-pop.json", {"data": "test"})

        cli._create_version_snapshot(filepath, "edit", ["arg1"])

        versions = cli._list_versions(filepath)
        assert len(versions) == 1
        ver = versions[0]
        assert ver["operation"] == "edit"
        assert ver["command_args"] == ["arg1"]
        assert "file_hash" in ver
        assert "file_size" in ver
        assert "timestamp" in ver

    def test_handles_corrupt_meta_file(self, isolated_config_dir):
        """验证损坏的元数据文件不会导致崩溃"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "corrupt-meta.json", {"v": 1})

        cli._create_version_snapshot(filepath, "test")

        # 损坏元数据文件
        version_dir = config_dir / ".versions" / "corrupt-meta.json"
        meta_files = list(version_dir.glob("corrupt-meta.*.meta.json"))
        assert len(meta_files) == 1
        with open(meta_files[0], "w") as f:
            f.write("not valid json {{{")

        versions = cli._list_versions(filepath)
        assert len(versions) == 1
        # 应该优雅降级，用默认值
        assert versions[0]["operation"] == ""


# ── _create_version_metadata 测试 ─────────────────────────────────


class TestCreateVersionMetadata:
    """测试 _create_version_metadata 函数"""

    def test_returns_correct_structure(self, isolated_config_dir):
        """验证返回正确的元数据结构"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "struct-test.json", {"key": "val"})

        meta = cli._create_version_metadata(filepath, "switch", ["profile-a"])

        assert "timestamp" in meta
        assert meta["operation"] == "switch"
        assert meta["command_args"] == ["profile-a"]
        assert "file_path" in meta
        assert "file_size" in meta
        assert "file_hash" in meta
        assert meta["file_size"] > 0
        assert meta["file_hash"].startswith("sha256:")

    def test_nonexistent_file_metadata(self, isolated_config_dir):
        """验证不存在文件的元数据"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = config_dir / "nonexistent.json"

        meta = cli._create_version_metadata(filepath, "create")

        assert meta["file_size"] == 0
        assert meta["file_hash"] == ""
        assert meta["operation"] == "create"

    def test_default_command_args(self, isolated_config_dir):
        """验证默认 command_args 为空列表"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "default-args.json", {})

        meta = cli._create_version_metadata(filepath, "test")
        assert meta["command_args"] == []

    def test_timestamp_is_iso8601(self, isolated_config_dir):
        """验证时间戳是 ISO 8601 格式"""
        from datetime import datetime

        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "timestamp-test.json", {})

        meta = cli._create_version_metadata(filepath, "test")

        # 应该能被 fromisoformat 解析
        dt = datetime.fromisoformat(meta["timestamp"])
        assert dt is not None


# ── _validate_version_metadata 测试 ───────────────────────────────


class TestValidateVersionMetadata:
    """测试 _validate_version_metadata 函数"""

    def test_valid_metadata(self):
        """验证有效元数据通过验证"""
        meta = {
            "timestamp": "2026-05-29T12:00:00",
            "operation": "switch",
            "command_args": ["profile-a"],
            "file_path": "~/.config/oma-switch/config.json",
            "file_size": 1234,
            "file_hash": "sha256:abc123def456",
        }
        assert cli._validate_version_metadata(meta) is True

    def test_valid_metadata_empty_hash(self):
        """验证空 file_hash 通过验证"""
        meta = {
            "timestamp": "2026-05-29T12:00:00",
            "operation": "create",
            "command_args": [],
            "file_path": "/tmp/test.json",
            "file_size": 0,
            "file_hash": "",
        }
        assert cli._validate_version_metadata(meta) is True

    def test_missing_required_field(self):
        """验证缺少必需字段时返回 False"""
        meta = {
            "timestamp": "2026-05-29T12:00:00",
            "operation": "switch",
            # 缺少 file_path, file_size, file_hash
        }
        assert cli._validate_version_metadata(meta) is False

    def test_invalid_timestamp_format(self):
        """验证无效时间戳格式返回 False"""
        meta = {
            "timestamp": "not-a-timestamp",
            "operation": "switch",
            "command_args": [],
            "file_path": "/tmp/test.json",
            "file_size": 100,
            "file_hash": "sha256:abc",
        }
        assert cli._validate_version_metadata(meta) is False

    def test_empty_timestamp(self):
        """验证空时间戳返回 False"""
        meta = {
            "timestamp": "",
            "operation": "switch",
            "command_args": [],
            "file_path": "/tmp/test.json",
            "file_size": 100,
            "file_hash": "sha256:abc",
        }
        assert cli._validate_version_metadata(meta) is False

    def test_invalid_hash_prefix(self):
        """验证非 sha256: 前缀的 hash 返回 False"""
        meta = {
            "timestamp": "2026-05-29T12:00:00",
            "operation": "switch",
            "command_args": [],
            "file_path": "/tmp/test.json",
            "file_size": 100,
            "file_hash": "md5:abc123",
        }
        assert cli._validate_version_metadata(meta) is False

    def test_negative_file_size(self):
        """验证负数 file_size 返回 False"""
        meta = {
            "timestamp": "2026-05-29T12:00:00",
            "operation": "switch",
            "command_args": [],
            "file_path": "/tmp/test.json",
            "file_size": -1,
            "file_hash": "sha256:abc",
        }
        assert cli._validate_version_metadata(meta) is False

    def test_non_int_file_size(self):
        """验证非整数 file_size 返回 False"""
        meta = {
            "timestamp": "2026-05-29T12:00:00",
            "operation": "switch",
            "command_args": [],
            "file_path": "/tmp/test.json",
            "file_size": "not-a-number",
            "file_hash": "sha256:abc",
        }
        assert cli._validate_version_metadata(meta) is False

    def test_non_string_operation(self):
        """验证非字符串 operation 返回 False"""
        meta = {
            "timestamp": "2026-05-29T12:00:00",
            "operation": 123,
            "command_args": [],
            "file_path": "/tmp/test.json",
            "file_size": 100,
            "file_hash": "sha256:abc",
        }
        assert cli._validate_version_metadata(meta) is False

    def test_non_string_file_path(self):
        """验证非字符串 file_path 返回 False"""
        meta = {
            "timestamp": "2026-05-29T12:00:00",
            "operation": "switch",
            "command_args": [],
            "file_path": 12345,
            "file_size": 100,
            "file_hash": "sha256:abc",
        }
        assert cli._validate_version_metadata(meta) is False

    def test_empty_dict(self):
        """验证空字典返回 False"""
        assert cli._validate_version_metadata({}) is False


# ── _load_version_metadata 测试 ───────────────────────────────────


class TestLoadVersionMetadata:
    """测试 _load_version_metadata 函数"""

    def test_loads_valid_metadata(self, isolated_config_dir):
        """验证加载有效的元数据文件"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        meta_data = {
            "timestamp": "2026-05-29T12:00:00",
            "operation": "switch",
            "command_args": ["profile-a"],
            "file_path": "~/.config/oma-switch/config.json",
            "file_size": 1234,
            "file_hash": "sha256:abc123",
        }
        meta_path = config_dir / "test.meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=2)

        result = cli._load_version_metadata(meta_path)

        assert result is not None
        assert result["operation"] == "switch"
        assert result["command_args"] == ["profile-a"]

    def test_returns_none_for_nonexistent_file(self, isolated_config_dir):
        """验证不存在的文件返回 None"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        meta_path = config_dir / "nonexistent.meta.json"

        result = cli._load_version_metadata(meta_path)
        assert result is None

    def test_returns_none_for_invalid_json(self, isolated_config_dir):
        """验证无效 JSON 返回 None"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        meta_path = config_dir / "invalid.meta.json"
        with open(meta_path, "w") as f:
            f.write("not valid json {{{")

        result = cli._load_version_metadata(meta_path)
        assert result is None

    def test_returns_none_for_invalid_metadata_format(self, isolated_config_dir):
        """验证格式错误的元数据返回 None"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        meta_path = config_dir / "bad-format.meta.json"
        with open(meta_path, "w") as f:
            json.dump({"key": "value"}, f)

        result = cli._load_version_metadata(meta_path)
        assert result is None

    def test_roundtrip_create_and_load(self, isolated_config_dir):
        """验证创建快照后能正确加载元数据"""
        config_dir = isolated_config_dir / ".config" / "oma-switch"
        filepath = _make_test_file(config_dir, "roundtrip.json", {"test": True})

        cli._create_version_snapshot(filepath, "test_op", ["arg1", "arg2"])

        version_dir = config_dir / ".versions" / "roundtrip.json"
        meta_files = list(version_dir.glob("roundtrip.*.meta.json"))
        assert len(meta_files) == 1

        result = cli._load_version_metadata(meta_files[0])
        assert result is not None
        assert result["operation"] == "test_op"
        assert result["command_args"] == ["arg1", "arg2"]
        assert result["file_hash"].startswith("sha256:")
