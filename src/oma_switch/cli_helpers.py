#!/usr/bin/env python3
"""
CLI 工具函数模块：编辑器调用、配置检测、参数解析、配置合并等辅助功能。
"""

import copy
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .constants import OMA_CONFIG
from .config_io import load_config, save_config, load_profile_json, get_profile_path
from .io_utils import _atomic_write_json
from .version import _create_version_snapshot, _rotate_versions
from .template import load_template
from .display import *  # noqa: F403


def merge_to_oma_config(source_profile: Dict[str, Any]) -> None:
    """将 source_profile 中的 agents 和 categories 合并到 OMA_CONFIG，保留其他字段。

    只更新以下顶层键：
    - agents
    - categories
    其他顶层键（$schema, background, permissions 等）保持不变。
    如果 OMA_CONFIG 不存在，则以 source_profile 为基础创建。
    """
    current = {}
    if OMA_CONFIG.exists():
        try:
            with open(OMA_CONFIG, 'r', encoding='utf-8') as f:
                current = json.load(f)
        except (json.JSONDecodeError, IOError):
            print_warning("OMA 配置文件损坏，将使用新配置")

    for key in ("agents", "categories"):
        if key in source_profile:
            current[key] = copy.deepcopy(source_profile[key])

    _create_version_snapshot(OMA_CONFIG, "merge_to_oma_config")
    _atomic_write_json(OMA_CONFIG, current)
    _rotate_versions(OMA_CONFIG)


def merge_fallback_to_oma_config(fallback_data: Dict[str, Any]) -> None:
    """将 fallback_models 字段级注入到 OMA 配置中，保留所有现有字段。

    与 merge_to_oma_config 不同，此函数不替换整个 agents/categories 节，
    而是在每个条目中设置/移除 fallback_models 字段。

    参数:
        fallback_data: 分类 → {"fallback_models": [...]} 的映射
    """
    current: Dict[str, Any] = {}
    if OMA_CONFIG.exists():
        try:
            with open(OMA_CONFIG, 'r', encoding='utf-8') as f:
                current = json.load(f)
        except (json.JSONDecodeError, IOError):
            print_warning("OMA 配置文件损坏，将使用新配置")

    template = load_template()
    any_active = False

    for category_label, cat_data in fallback_data.items():
        chain = cat_data.get("fallback_models", [])
        entries = template.get(category_label, set())

        for section, key in entries:
            if section not in current:
                current[section] = {}
            if key not in current[section]:
                current[section][key] = {}

            entry = current[section][key]
            if chain:
                entry["fallback_models"] = copy.deepcopy(chain)
                any_active = True
            else:
                entry.pop("fallback_models", None)

    current["model_fallback"] = any_active

    _create_version_snapshot(OMA_CONFIG, "merge_fallback_to_oma_config")
    _atomic_write_json(OMA_CONFIG, current)
    _rotate_versions(OMA_CONFIG)


def open_editor(filepath: Path) -> bool:
    editor = os.environ.get('EDITOR', os.environ.get('VISUAL', 'vim'))
    try:
        result = subprocess.run([editor, str(filepath)], check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        print_error(f"找不到编辑器: {editor}")
        return False


def check_current_unrecorded() -> None:
    if not OMA_CONFIG.exists():
        return

    config = load_config()
    current_name = config.get("current")

    if current_name and current_name in config["profiles"]:
        profile_path = get_profile_path(current_name)
        if profile_path.exists():
            return

    print_warning("当前 OMA 配置文件未被记录")
    response = input("是否要记录当前配置文件? (y/N): ").strip().lower()
    if response == 'y':
        name = input("请输入配置文件名称: ").strip()
        if not name:
            print_error("名称不能为空")
            return
        if name in config["profiles"]:
            print_error(f"配置文件 '{name}' 已存在")
            return

        shutil.copy2(OMA_CONFIG, get_profile_path(name))
        config["current"] = name
        config["profiles"][name] = {
            "created": datetime.now().isoformat(),
            "description": ""
        }
        save_config(config)
        print_success(f"已记录当前配置文件为 '{name}'")


def parse_flag(args: List[str], flag: str = "--detail") -> Tuple[bool, List[str]]:
    """从参数列表中提取标志，返回 (has_flag, remaining_args)"""
    has = False
    remaining = []
    for arg in args:
        if arg == flag:
            has = True
        else:
            remaining.append(arg)
    return has, remaining


def get_profile_or_current(name: str = None) -> Tuple[str, Dict, str]:
    """
    获取 profile 数据。
    返回: (name, profile_dict, error_msg)
    如果出错，error_msg 非空，name 和 profile_dict 无意义。
    """
    config = load_config()

    if not name:
        name = config.get("current")
        if not name:
            return None, None, "当前没有激活的配置文件"
    elif name not in config["profiles"]:
        return None, None, f"配置文件 '{name}' 不存在"

    profile = load_profile_json(name)
    if profile is None:
        return None, None, f"配置文件 '{name}' 文件丢失或格式错误"

    return name, profile, None
