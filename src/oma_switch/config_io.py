#!/usr/bin/env python3
"""
配置文件 I/O 模块：配置文件读写、profile/fallback 文件管理。
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from .types import FallbackData, OmaSwitchConfig

from .constants import CONFIG_FILE, FALLBACKS_DIR, PROFILES_DIR
from .display import print_error, print_warning
from .io_utils import _atomic_write_json
from .version import _create_version_snapshot, _recover_from_versions, _rotate_versions


def _default_config() -> OmaSwitchConfig:
    return {"current": None, "profiles": {}, "current_fallback": ""}


def load_config() -> OmaSwitchConfig:
    if not CONFIG_FILE.exists():
        return _default_config()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = cast(OmaSwitchConfig, json.load(f))
            config.setdefault("current_fallback", "")
            return config
    except json.JSONDecodeError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupted_path = CONFIG_FILE.with_suffix(f".json.corrupted.{ts}")
        try:
            shutil.move(str(CONFIG_FILE), str(corrupted_path))
        except OSError:
            pass
        print_warning(f"配置文件已损坏，已保存为: {corrupted_path.name}")
        recovered = _recover_from_versions(CONFIG_FILE)
        if recovered is not None:
            print_warning(f"已从版本历史恢复配置")
            recovered.setdefault("current_fallback", "")
            return cast(OmaSwitchConfig, recovered)
        print_error("无法从版本历史恢复配置，请手动恢复或重新创建")
        return _default_config()


def save_config(config: OmaSwitchConfig) -> None:
    _create_version_snapshot(CONFIG_FILE, "save_config")
    _atomic_write_json(CONFIG_FILE, cast(Dict[str, Any], config))
    _rotate_versions(CONFIG_FILE)


def get_current_fallback(config: OmaSwitchConfig) -> str:
    """获取当前回退链名称"""
    return config.get("current_fallback", "")


def set_current_fallback(config: OmaSwitchConfig, name: str) -> None:
    """设置当前回退链名称并保存"""
    config["current_fallback"] = name
    save_config(config)


def clear_current_fallback_if_deleted(config: OmaSwitchConfig, deleted_name: str) -> bool:
    """如果当前回退链被删除则清空，返回是否清空"""
    if config.get("current_fallback") == deleted_name:
        config["current_fallback"] = ""
        save_config(config)
        return True
    return False


def get_profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{name}.json"


def is_valid_json(filepath: Path) -> bool:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, FileNotFoundError):
        return False


def load_profile_json(name: str) -> Optional[Dict[str, Any]]:
    """加载配置文件，返回 None 如果不存在或无效"""
    path = get_profile_path(name)
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupted_path = path.with_suffix(f".json.corrupted.{ts}")
        try:
            shutil.move(str(path), str(corrupted_path))
        except OSError:
            pass
        print_warning(f"配置文件损坏 [{name}]，已保存为: {corrupted_path.name}")
        recovered = _recover_from_versions(path)
        if recovered is not None:
            print_warning(f"已从版本历史恢复配置 [{name}]")
            return recovered
        print_error(f"无法从版本历史恢复配置 [{name}]，请手动恢复")
        return None


def get_fallback_path(name: str) -> Path:
    return FALLBACKS_DIR / f"{name}.json"


def load_fallback_json(name: str) -> Optional[FallbackData]:
    path = get_fallback_path(name)
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return cast(FallbackData, json.load(f))
    except json.JSONDecodeError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupted_path = path.with_suffix(f".json.corrupted.{ts}")
        try:
            shutil.move(str(path), str(corrupted_path))
        except OSError:
            pass
        print_warning(f"Fallback 配置文件损坏 [{name}]，已保存为: {corrupted_path.name}")
        recovered = _recover_from_versions(path)
        if recovered is not None:
            print_warning(f"已从版本历史恢复 Fallback 配置 [{name}]")
            return cast(FallbackData, recovered)
        print_error(f"无法从版本历史恢复 Fallback 配置 [{name}]，请手动恢复")
        return None


def save_fallback_json(name: str, data: FallbackData) -> None:
    FALLBACKS_DIR.mkdir(parents=True, exist_ok=True)
    _create_version_snapshot(get_fallback_path(name), "save_fallback_json")
    _atomic_write_json(get_fallback_path(name), cast(Dict[str, Any], data))
    _rotate_versions(get_fallback_path(name))


def list_fallback_names() -> List[str]:
    if not FALLBACKS_DIR.exists():
        return []
    return sorted(p.stem for p in FALLBACKS_DIR.glob("*.json"))


def delete_fallback_json(name: str) -> bool:
    path = get_fallback_path(name)
    if path.exists():
        path.unlink()
        return True
    return False
