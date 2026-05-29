#!/usr/bin/env python3
"""
版本管理模块：版本快照、轮转、列表、恢复等功能。
"""

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from .constants import CONFIG_DIR
from .display import (
    Colors,
    print_color,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from .io_utils import _atomic_write_json
from .types import VersionMetadata

__all__ = [
    "_get_version_dir",
    "_create_version_snapshot",
    "_rotate_versions",
    "_list_versions",
    "_recover_from_versions",
    "_create_version_metadata",
    "_validate_version_metadata",
    "_load_version_metadata",
    "_show_restore_list",
    "_show_file_versions",
    "_restore_version",
    "cmd_restore",
]


# ---------- 版本管理核心 ----------


def _get_version_dir(filepath: Path) -> Path:
    """根据文件路径返回对应的版本目录，结构: ~/.config/oma-switch/.versions/<filename>"""
    version_dir = CONFIG_DIR / ".versions" / filepath.name
    version_dir.mkdir(parents=True, exist_ok=True)
    return version_dir


def _create_version_metadata(
    filepath: Path, operation: str, command_args: Optional[List[str]] = None
) -> VersionMetadata:
    """创建版本元数据字典

    参数：
        filepath: 目标文件路径
        operation: 操作名称（如 'switch', 'edit', 'create'）
        command_args: 命令参数列表

    返回：
        包含版本元数据的字典，格式：
        {
            "timestamp": "2026-05-29T12:00:00",
            "operation": "switch",
            "command_args": ["my-profile"],
            "file_path": "~/.config/oma-switch/config.json",
            "file_size": 1234,
            "file_hash": "sha256:abc123..."
        }
    """
    timestamp = datetime.now().isoformat()

    if filepath.exists():
        file_size = filepath.stat().st_size
        file_hash = "sha256:" + hashlib.sha256(filepath.read_bytes()).hexdigest()
    else:
        file_size = 0
        file_hash = ""

    return {
        "timestamp": timestamp,
        "operation": operation,
        "command_args": command_args or [],
        "file_path": str(filepath),
        "file_size": file_size,
        "file_hash": file_hash,
    }


def _validate_version_metadata(metadata: VersionMetadata) -> bool:
    """验证版本元数据格式

    检查必需字段是否存在，timestamp 是否为 ISO 8601 格式，
    file_hash 是否以 'sha256:' 开头（或为空字符串）。

    返回 True 表示有效，False 表示无效。
    """
    required_fields = ["timestamp", "operation", "file_path", "file_size", "file_hash"]
    for field in required_fields:
        if field not in metadata:
            return False

    timestamp = metadata.get("timestamp", "")
    if not isinstance(timestamp, str) or not timestamp:
        return False

    # ISO 8601: 2026-05-29T12:00:00[.123456]  紧凑: 20260529_120000
    _TS_RE = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        r"(\.\d+)?"
        r"([+-]\d{2}:\d{2}|Z)?$"
        r"|^\d{8}_\d{6}$"
    )
    if not _TS_RE.match(timestamp):
        return False

    # 验证 file_hash
    file_hash = metadata.get("file_hash", "")
    if file_hash and not file_hash.startswith("sha256:"):
        return False

    # 验证 file_size 为非负整数
    file_size = metadata.get("file_size")
    if not isinstance(file_size, int) or file_size < 0:
        return False

    # 验证 operation 和 file_path 为字符串
    if not isinstance(metadata.get("operation"), str):
        return False
    if not isinstance(metadata.get("file_path"), str):
        return False

    return True


def _load_version_metadata(version_path: Path) -> Optional[VersionMetadata]:
    """加载版本元数据文件

    参数：
        version_path: 元数据文件路径

    返回：
        成功时返回元数据字典；文件不存在或格式错误时返回 None
    """
    if not version_path.exists():
        return None

    try:
        with open(version_path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    if not _validate_version_metadata(data):  # type: ignore[arg-type]
        return None

    return cast(VersionMetadata, data)


def _create_version_snapshot(
    filepath: Path, operation: str, command_args: Optional[List[str]] = None
) -> None:
    """在写入前创建版本快照"""
    if not filepath.exists():
        return

    version_dir = _get_version_dir(filepath)
    ts_short = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = filepath.stem
    suffix = filepath.suffix or ".json"

    version_filename = f"{stem}.{ts_short}{suffix}"
    version_path = version_dir / version_filename
    shutil.copy2(filepath, version_path)

    meta = _create_version_metadata(filepath, operation, command_args)
    meta_path = version_dir / f"{stem}.{ts_short}.meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def _rotate_versions(filepath: Path, max_versions: int = 10) -> None:
    """按时间戳排序版本文件，删除超过 max_versions 的最旧版本"""
    version_dir = _get_version_dir(filepath)
    stem = filepath.stem
    suffix = filepath.suffix or ".json"

    version_files = [
        p
        for p in version_dir.glob(f"{stem}.*{suffix}")
        if not p.name.endswith(".meta.json") and p.is_file()
    ]
    if len(version_files) <= max_versions:
        return

    version_files.sort(key=lambda p: p.name)
    to_delete = version_files[: len(version_files) - max_versions]

    for vf in to_delete:
        vf.unlink(missing_ok=True)
        meta_file = vf.with_suffix(".meta.json")
        meta_file.unlink(missing_ok=True)


def _list_versions(filepath: Path) -> List[VersionMetadata]:
    """列出指定文件的所有版本，按时间戳降序排序"""
    version_dir = CONFIG_DIR / ".versions" / filepath.name
    if not version_dir.exists():
        return []

    stem = filepath.stem
    suffix = filepath.suffix or ".json"

    version_files = [
        p
        for p in version_dir.glob(f"{stem}.*{suffix}")
        if not p.name.endswith(".meta.json") and p.is_file()
    ]

    versions: List[VersionMetadata] = []
    for vf in version_files:
        name_parts = vf.name.rsplit(".", 1)[0]
        timestamp = name_parts.replace(f"{stem}.", "", 1)

        meta_file = vf.with_suffix(".meta.json")
        meta = _load_version_metadata(meta_file)

        versions.append(
            {
                "timestamp": meta.get("timestamp", timestamp) if meta else timestamp,
                "file_path": str(vf),
                "operation": meta.get("operation", "") if meta else "",
                "command_args": meta.get("command_args", []) if meta else [],
                "file_size": meta.get("file_size", vf.stat().st_size if vf.exists() else 0)
                if meta
                else (vf.stat().st_size if vf.exists() else 0),
                "file_hash": meta.get("file_hash", "") if meta else "",
            }
        )

    # 按时间戳降序排序（最新在前）
    versions.sort(key=lambda v: v["timestamp"], reverse=True)
    return versions


def _recover_from_versions(filepath: Path) -> Optional[Dict[str, Any]]:
    """从版本历史恢复最新有效版本"""
    versions = _list_versions(filepath)
    for ver in versions:
        ver_path = Path(ver["file_path"])
        if not ver_path.exists():
            continue
        try:
            with open(ver_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, IOError):
            continue
    return None


# ---------- 版本恢复 ----------


def _show_restore_list() -> None:
    """显示所有可恢复的文件和版本数量"""
    versions_dir = CONFIG_DIR / ".versions"
    if not versions_dir.exists():
        print_warning("没有找到任何版本历史")
        return

    file_dirs = sorted([d for d in versions_dir.iterdir() if d.is_dir()])
    if not file_dirs:
        print_warning("没有找到任何版本历史")
        return

    print_info("可恢复的文件:")
    print()
    for file_dir in file_dirs:
        version_files = [
            p for p in file_dir.iterdir() if p.is_file() and not p.name.endswith(".meta.json")
        ]
        count = len(version_files)
        if count > 0:
            print(f"  {Colors.BOLD}{file_dir.name}{Colors.NC} ({count} 个版本)")
    print()
    print_dim("使用 'oma-switch restore <file>' 查看指定文件的版本列表")


def _show_file_versions(filepath: Path) -> None:
    """显示指定文件的版本列表"""
    versions = _list_versions(filepath)
    if not versions:
        print_warning(f"文件 {filepath.name} 没有版本历史")
        return

    print_info(f"{filepath.name} 的版本历史:")
    print()
    for i, ver in enumerate(versions, 1):
        ts = ver.get("timestamp", "未知时间")
        op = ver.get("operation", "未知操作")
        size = ver.get("file_size", 0)
        size_str = f"{size:,}" if size > 0 else "未知"
        print(f"  [{i}] {Colors.BOLD}{ts}{Colors.NC} - {op} ({size_str} 字节)")
    print()
    print_dim("使用 'oma-switch restore <file> <版本号>' 恢复指定版本")


def _restore_version(filepath: Path, version_id: str) -> bool:
    """恢复指定版本

    参数：
        filepath: 目标文件路径
        version_id: 版本标识（支持序号或时间戳）

    返回：
        是否成功恢复
    """
    versions = _list_versions(filepath)
    if not versions:
        print_error(f"文件 {filepath.name} 没有版本历史")
        return False

    target_version = None
    try:
        idx = int(version_id) - 1
        if 0 <= idx < len(versions):
            target_version = versions[idx]
        else:
            print_error(f"版本序号 {version_id} 超出范围 (1-{len(versions)})")
            return False
    except ValueError:
        for ver in versions:
            if ver.get("timestamp") == version_id:
                target_version = ver
                break
        if target_version is None:
            print_error(f"未找到版本: {version_id}")
            print_info("使用 'oma-switch restore <file>' 查看可用版本")
            return False

    ver_path = Path(target_version["file_path"])
    if not ver_path.exists():
        print_error(f"版本文件不存在: {ver_path}")
        return False

    try:
        with open(ver_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print_error(f"版本文件读取失败: {e}")
        return False

    ts = target_version.get("timestamp", "未知时间")
    op = target_version.get("operation", "未知操作")
    size = target_version.get("file_size", 0)

    print()
    print_color(Colors.BOLD, "将要恢复的版本:")
    print(f"  时间:   {ts}")
    print(f"  操作:   {op}")
    print(f"  大小:   {size:,} 字节")
    print()

    if isinstance(data, dict):
        print_color(Colors.BOLD, "  内容摘要:")
        for key in list(data.keys())[:8]:
            val = data[key]
            if isinstance(val, str) and len(val) > 60:
                val = val[:57] + "..."
            elif isinstance(val, (dict, list)):
                val = f"[{type(val).__name__}, {len(val)} 项]"
            print(f"    {key}: {val}")
        print()

    try:
        confirm = input(f"{Colors.YELLOW}确认恢复此版本？(y/N): {Colors.NC}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        print_warning("已取消恢复")
        return False

    if confirm not in ("y", "yes"):
        print_warning("已取消恢复")
        return False

    if filepath.exists():
        _create_version_snapshot(filepath, "pre_restore")
        _rotate_versions(filepath)

    try:
        _atomic_write_json(filepath, data)
        print_success(f"已恢复 {filepath.name} 到版本 {ts}")
        return True
    except Exception as e:
        print_error(f"恢复失败: {e}")
        return False


def cmd_restore(args: List[str]) -> None:
    """恢复历史版本命令

    用法:
        oma-switch restore                  显示所有可恢复的文件和版本列表
        oma-switch restore <file>           显示指定文件的版本列表
        oma-switch restore <file> <version> 恢复指定版本
    """
    if not args:
        _show_restore_list()
        return

    filename = args[0]

    filepath: Optional[Path] = None
    candidates = [
        CONFIG_DIR / filename,
        CONFIG_DIR / "profiles" / filename,
        CONFIG_DIR / "fallbacks" / filename,
        Path(filename),
    ]
    for candidate in candidates:
        if candidate.exists():
            filepath = candidate
            break

    if filepath is None:
        versions_dir = CONFIG_DIR / ".versions"
        if versions_dir.exists():
            for d in versions_dir.iterdir():
                if d.is_dir() and d.name == filename:
                    meta_files = sorted(d.glob("*.meta.json"), reverse=True)
                    for meta_file in meta_files:
                        try:
                            with open(meta_file, "r", encoding="utf-8") as f:
                                meta = json.load(f)
                            if "file_path" in meta:
                                filepath = Path(meta["file_path"])
                                break
                        except (json.JSONDecodeError, IOError):
                            continue

                    if filepath is None:
                        filepath = CONFIG_DIR / filename
                    break

    if filepath is None:
        print_error(f"未找到文件: {filename}")
        print_info("使用 'oma-switch restore' 查看可恢复的文件列表")
        sys.exit(1)

    if len(args) >= 2:
        version_id = args[1]
        _restore_version(filepath, version_id)
    else:
        _show_file_versions(filepath)
