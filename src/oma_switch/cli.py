#!/usr/bin/env python3
"""
OMA (Oh-My-Agent) 配置文件切换工具
用于管理 opencode 的 oh-my-openagent.json 配置文件

快速模式（默认）：按模板中的模型分类（主/强/中/弱/多模态等）进行查看、创建、比较
详细模式（--detail）：完整的 JSON 操作（编辑/全文查看/系统 diff）
"""

import hashlib
import json
import os
import re
import readline  # 启用 input() 的行编辑功能（方向键、历史记录等）
import sys
import copy
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

try:
    from thefuzz import fuzz as _fuzz
    HAS_THEFUZZ = True
except ImportError:
    HAS_THEFUZZ = False

CONFIG_DIR = Path.home() / ".config" / "oma-switch"
PROFILES_DIR = CONFIG_DIR / "profiles"
CONFIG_FILE = CONFIG_DIR / "config.json"
TEMPLATE_FILE = CONFIG_DIR / "template.json"
OMA_CONFIG = Path.home() / ".config" / "opencode" / "oh-my-openagent.json"
FALLBACKS_DIR = CONFIG_DIR / "fallbacks"
HISTORY_FILE = CONFIG_DIR / "history.json"

# DCP (Dynamic Context Pruning) 插件配置
OPENCODE_DIR = Path.home() / ".config" / "opencode"
DCP_CONFIG_FILE = OPENCODE_DIR / "dcp.jsonc"

from .display import *  # noqa: F403,E402
from .io_utils import _atomic_write_json  # noqa: F401
from .version import *  # noqa: F403,E402
from .config_io import *  # noqa: F403,E402
from .history import *  # noqa: F403
from .template import *  # noqa: F403
from .dcp import *  # noqa: F403
from .models import *  # noqa: F403
from .prompt import *  # noqa: F403
from .cli_helpers import *  # noqa: F403,F401


# ── 命令实现 ──────────────────────────────────────────────────────


def cmd_add(args: List[str]) -> None:
    """添加配置文件"""
    if len(args) < 2:
        print_error("用法: oma-switch add <filepath> <name>")
        print_info("filepath: 要添加的配置文件路径")
        print_info("name: 配置文件名称")
        sys.exit(1)

    filepath = Path(args[0]).expanduser().resolve()
    name = args[1]

    if not filepath.exists():
        print_error(f"文件不存在: {filepath}")
        sys.exit(1)

    if not is_valid_json(filepath):
        print_error(f"文件不是有效的 JSON 格式: {filepath}")
        sys.exit(1)

    config = load_config()
    if name in config["profiles"]:
        print_error(f"配置文件 '{name}' 已存在")
        sys.exit(1)

    shutil.copy2(filepath, get_profile_path(name))
    config["profiles"][name] = {
        "created": datetime.now().isoformat(),
        "description": "",
        "dcp_enabled": True,
    }
    save_config(config)

    try:
        filepath.unlink()
        print_success(f"已添加配置文件 '{name}' (原文件已删除)")
    except OSError as e:
        print_success(f"已添加配置文件 '{name}'")
        print_warning(f"无法删除原文件: {e}")


def cmd_rm(args: List[str]) -> None:
    """删除配置文件"""
    if not args:
        print_error("用法: oma-switch rm <name>")
        sys.exit(1)

    name = args[0]
    config = load_config()

    if name not in config["profiles"]:
        print_error(f"配置文件 '{name}' 不存在")
        sys.exit(1)

    response = input(f"确定要删除配置文件 '{name}' 吗? (y/N): ").strip().lower()
    if response != 'y':
        print_info("已取消")
        return

    profile_path = get_profile_path(name)
    if profile_path.exists():
        profile_path.unlink()

    if config.get("current") == name:
        config["current"] = None

    del config["profiles"][name]
    save_config(config)
    print_success(f"已删除配置文件 '{name}'")


def cmd_edit(args: List[str]) -> None:
    """
    编辑配置文件。

    快速模式（默认）：
      - 交互式修改各分类模型，自动生成新配置
    详细模式（--detail）：
      - 打开编辑器编辑完整 JSON（原行为）
    """
    has_detail, remaining_args = parse_flag(args, "--detail")

    if not remaining_args:
        print_error("用法: oma-switch edit [--detail] <name>")
        sys.exit(1)

    name = remaining_args[0]
    config = load_config()

    if name not in config["profiles"]:
        print_error(f"配置文件 '{name}' 不存在")
        sys.exit(1)

    profile_path = get_profile_path(name)
    if not profile_path.exists():
        print_error(f"配置文件 '{name}' 不存在")
        sys.exit(1)

    profile = load_profile_json(name)
    if profile is None:
        print_error(f"配置文件 '{name}' 格式错误")
        sys.exit(1)

    if has_detail:
        print_info(f"正在编辑配置文件 '{name}' (详细模式)...")
        if open_editor(profile_path):
            if is_valid_json(profile_path):
                print_success(f"配置文件 '{name}' 已更新")
                config["profiles"][name]["modified"] = datetime.now().isoformat()
                save_config(config)
                if config.get("current") == name:
                    edited_profile = load_profile_json(name)
                    if edited_profile:
                        merge_to_oma_config(edited_profile)
                        print_info("已同步到 OMA 配置文件")
            else:
                print_error("配置文件格式错误，已恢复")
        else:
            print_error("编辑失败")
        return

    if not check_template_profile(profile):
        print_warning(f"配置文件 '{name}' 不符合模板结构，按详细模式编辑")
        print_info(f"正在编辑配置文件 '{name}' (详细模式)...")
        if open_editor(profile_path):
            if is_valid_json(profile_path):
                print_success(f"配置文件 '{name}' 已更新")
                config["profiles"][name]["modified"] = datetime.now().isoformat()
                save_config(config)
                if config.get("current") == name:
                    edited_profile = load_profile_json(name)
                    if edited_profile:
                        merge_to_oma_config(edited_profile)
                        print_info("已同步到 OMA 配置文件")
            else:
                print_error("配置文件格式错误，已恢复")
        else:
            print_error("编辑失败")
        return

    print_info(f"正在编辑配置文件 '{name}' (快速模式)")
    print()

    summary, current_models = get_template_summary(profile)
    all_models = collect_all_models()

    print_type_summary(summary, "当前模板结构:", current_models)

    model_map = {}
    for type_label in load_template():
        model_info = prompt_select_model(type_label, all_models, current_models.get(type_label))
        model_map[type_label] = model_info
    new_profile = generate_profile_from_types(profile, model_map)

    if not check_template_profile(new_profile):
        print_error("编辑后的配置不满足模板约束（请确保同一分组内所有 agent/category 使用相同模型）")
        return

    _create_version_snapshot(profile_path, "cmd_edit")
    _atomic_write_json(profile_path, new_profile)
    _rotate_versions(profile_path)

    config["profiles"][name]["modified"] = datetime.now().isoformat()
    save_config(config)

    if config.get("current") == name:
        merge_to_oma_config(new_profile)
        print_info("已同步到 OMA 配置文件")

    print()
    print_success(f"配置文件 '{name}' 已更新")

    new_summary, new_current = get_template_summary(new_profile)
    print_type_summary(new_summary, "更新后配置:", new_current)


def cmd_create(args: List[str]) -> None:
    """
    创建新配置文件。

    快速模式（默认）：
      - 以当前配置为模板，交互式指定各分类模型
      - 自动生成新配置文件
    详细模式（--detail）：
      - 复制当前配置并打开编辑器编辑（原行为）
    """
    has_detail, remaining_args = parse_flag(args, "--detail")

    if not remaining_args:
        print_error("用法: oma-switch create [--detail] <name>")
        sys.exit(1)

    name = remaining_args[0]
    config = load_config()

    if name in config["profiles"]:
        print_error(f"配置文件 '{name}' 已存在")
        sys.exit(1)

    if not OMA_CONFIG.exists():
        print_error("当前 OMA 配置文件不存在")
        sys.exit(1)

    with open(OMA_CONFIG, 'r', encoding='utf-8') as f:
        current_profile = json.load(f)

    if has_detail:
        profile_path = get_profile_path(name)
        shutil.copy2(OMA_CONFIG, profile_path)

        print_info(f"正在创建新配置文件 '{name}' (详细模式)...")
        if open_editor(profile_path):
            if is_valid_json(profile_path):
                config["profiles"][name] = {
                    "created": datetime.now().isoformat(),
                    "description": "",
                    "dcp_enabled": True,
                }
                save_config(config)
                print_success(f"已创建配置文件 '{name}'")
            else:
                profile_path.unlink()
                print_error("配置文件格式错误，已取消创建")
        else:
            profile_path.unlink()
            print_error("创建失败")
        return

    print_info(f"正在创建新配置文件 '{name}' (快速模式)")
    print("基于当前配置文件模板，指定各分类模型:")
    print()

    summary, current_models = get_template_summary(current_profile)
    all_models = collect_all_models()

    print_type_summary(summary, "当前模板结构:", current_models)

    model_map = {}
    for type_label in load_template():
        model_info = prompt_select_model(type_label, all_models, current_models.get(type_label))
        model_map[type_label] = model_info
    new_profile = generate_profile_from_types(current_profile, model_map)

    if not check_template_profile(new_profile):
        print_error("生成的配置不满足模板约束（请确保同一分组内所有 agent/category 使用相同模型）")
        return

    profile_path = get_profile_path(name)
    _create_version_snapshot(profile_path, "cmd_create")
    _atomic_write_json(profile_path, new_profile)
    _rotate_versions(profile_path)

    config["profiles"][name] = {
        "created": datetime.now().isoformat(),
        "description": "",
        "dcp_enabled": True,
    }
    save_config(config)

    print()
    print_success(f"已创建配置文件 '{name}'")

    new_summary, new_current = get_template_summary(new_profile)
    print_type_summary(new_summary, "新配置摘要:", new_current)


def cmd_view(args: List[str]) -> None:
    """
    查看配置文件。

快速模式（默认）：按模板分组显示
   详细模式（--detail）：显示完整 JSON（原行为）
    """
    has_detail, remaining_args = parse_flag(args, "--detail")

    config = load_config()
    name, profile, err = None, None, None

    if remaining_args:
        name = remaining_args[0]
        name, profile, err = get_profile_or_current(name)
    else:
        name, profile, err = get_profile_or_current()

    if err:
        if remaining_args:
            print_error(err)
        elif OMA_CONFIG.exists():
            print_warning(err)
            print_info("当前 OMA 配置文件内容:")
            with open(OMA_CONFIG, 'r', encoding='utf-8') as f:
                print(f.read())
        else:
            print_error(err)
        return

    if not has_detail and check_template_profile(profile):
        summary, current_models = get_template_summary(profile)
        print_type_summary(summary, f"配置文件 '{name}' (快速模式):", current_models)
        oma_config = load_config()
        profile_meta = oma_config.get("profiles", {}).get(name, {})
        dcp_enabled = _get_profile_dcp_enabled(profile_meta)
        dcp_str = f"{Colors.GREEN}✓ 启用{Colors.NC}" if dcp_enabled else f"{Colors.RED}✗ 禁用{Colors.NC}"
        print(f"  {Colors.BOLD}DCP{Colors.NC}:           {dcp_str}")
        print()
        return

    if not has_detail and not check_template_profile(profile):
        print_warning(f"配置文件 '{name}' 不符合模板结构，按详细模式显示")

    print_info(f"配置文件 '{name}' 的内容:")
    profile_path = get_profile_path(name)
    with open(profile_path, 'r', encoding='utf-8') as f:
        print(f.read())


def cmd_fallback_create(args: List[str]) -> None:
    """
    创建新的 fallback 配置。

    用法: oma-switch fallback create <name>

    流程:
      1. 验证名称（非空、不重复）
      2. 收集所有可用模型
      3. 为每个模板分类交互式选择 fallback 链
      4. 生成并验证配置
      5. 保存并打印摘要
    """
    if not args:
        print_error("用法: oma-switch fallback create <name>")
        sys.exit(1)

    name = args[0].strip()
    if not name:
        print_error("名称不能为空")
        sys.exit(1)

    existing = load_fallback_json(name)
    if existing is not None:
        print_error(f"Fallback 配置 '{name}' 已存在")
        sys.exit(1)

    print_info(f"正在创建 fallback 配置 '{name}'")
    print()

    all_models = collect_all_models()

    tpl = load_template()
    fallback_choices: Dict[str, List] = {}
    for type_label in tpl:
        selected = prompt_select_fallback_models(type_label, all_models)
        fallback_choices[type_label] = selected

    config = generate_fallback_from_types(fallback_choices)

    ok, err = validate_fallback_config(config)
    if not ok:
        print_error(f"生成的 fallback 配置无效: {err}")
        sys.exit(1)

    save_fallback_json(name, config)

    print()
    print_success(f"已创建 fallback 配置 '{name}'")
    summary = get_fallback_summary(config)
    print_fallback_summary(summary, "Fallback 链摘要:")


def cmd_rename(args: List[str]) -> None:
    """重命名配置文件"""
    if len(args) < 2:
        print_error("用法: oma-switch rename <name> <newname>")
        sys.exit(1)

    name, newname = args[0], args[1]
    config = load_config()

    if name not in config["profiles"]:
        print_error(f"配置文件 '{name}' 不存在")
        sys.exit(1)

    if newname in config["profiles"]:
        print_error(f"配置文件 '{newname}' 已存在")
        sys.exit(1)

    old_path = get_profile_path(name)
    new_path = get_profile_path(newname)
    old_path.rename(new_path)

    config["profiles"][newname] = config["profiles"][name]
    config["profiles"][newname]["renamed"] = datetime.now().isoformat()
    del config["profiles"][name]

    if config.get("current") == name:
        config["current"] = newname

    save_config(config)
    print_success(f"已将配置文件 '{name}' 重命名为 '{newname}'")


def _show_fallback_status(config: Dict[str, Any]) -> None:
    fallback = get_current_fallback(config)
    if fallback:
        print_info(f"当前 Fallback: {Colors.GREEN}{fallback}{Colors.NC}")
    else:
        print_info("当前 Fallback: (未设置)")


def cmd_list(args: List[str]) -> None:
    """列出所有配置文件"""
    config = load_config()
    current = config.get("current")

    if not config["profiles"]:
        print_warning("没有可用的配置文件")
        print_info("使用 'oma-switch create <name>' 创建新配置文件")
        _show_fallback_status(config)
        return

    print_info("可用的配置文件:")
    print("-" * 80)

    for name in sorted(config["profiles"].keys()):
        is_current = name == current
        marker = " *" if is_current else ""
        color = Colors.GREEN if is_current else Colors.NC

        profile_meta = config["profiles"].get(name, {})
        dcp_enabled = _get_profile_dcp_enabled(profile_meta)
        dcp_icon = f"{Colors.GREEN}DCP{Colors.NC}" if dcp_enabled else f"{Colors.RED}dcp{Colors.NC}"

        profile_path = get_profile_path(name)
        if not profile_path.exists():
            print(f"{color}  [{dcp_icon}] {name}{marker} (文件丢失){Colors.NC}")
            continue

        profile = load_profile_json(name)
        if profile and check_template_profile(profile):
            summary, current_models = get_template_summary(profile)
            print(f"{color}  [{dcp_icon}] {name}{marker}{Colors.NC}")
            for type_label in load_template():
                model, variant = current_models.get(type_label, ("—", None))
                variant_str = f' [variant={variant}]' if variant else ''
                print(f"     {type_label}: {Colors.CYAN}{model}{Colors.NC}{variant_str}")
        else:
            print(f"{color}  [{dcp_icon}] {name}{marker}{Colors.NC}")

    print("-" * 80)
    print_info("* 表示当前使用的配置文件")
    _show_fallback_status(config)


def cmd_fallback_list(args: List[str]) -> None:
    """列出所有 fallback 配置"""
    names = list_fallback_names()

    if not names:
        print_warning("暂无 fallback 配置")
        return

    config = load_config()
    current = get_current_fallback(config)

    print_info("可用的 fallback 配置:")
    print("-" * 80)

    for name in names:
        is_current = name == current
        marker = " *" if is_current else ""
        color = Colors.GREEN if is_current else Colors.NC

        data = load_fallback_json(name)
        if data is None:
            print(f"{color}  {name}{marker} (文件损坏){Colors.NC}")
            continue

        summary = get_fallback_summary(data)
        parts = []
        for cat, chain in summary.items():
            parts.append(f"{cat}({len(chain)})")
        detail = "  ".join(parts)
        print(f"{color}  {name}{marker}{Colors.NC}  {Colors.GRAY}{detail}{Colors.NC}")

    print("-" * 80)
    print_info("* 表示当前使用的 fallback 配置")


def cmd_fallback_view(args: List[str]) -> None:
    """
    查看 fallback 配置。

    用法: oma-switch fallback view [name]
    默认查看当前激活的 fallback 配置。
    """
    config = load_config()

    if args:
        name = args[0]
    else:
        name = get_current_fallback(config)

    if not name:
        print_error("当前没有激活的 fallback 配置")
        return

    data = load_fallback_json(name)
    if data is None:
        print_error(f"fallback '{name}' 不存在")
        return

    summary = get_fallback_summary(data)
    print_fallback_summary(summary, title=f"Fallback 配置 '{name}':")


def cmd_fallback_edit(args: List[str]) -> None:
    """
    编辑现有 fallback 配置。

    用法: oma-switch fallback edit <name>

    流程:
      1. 加载现有 fallback 配置
      2. 显示当前摘要
      3. 为每个模板分类交互式修改 fallback 链
      4. 生成并验证新配置
      5. 保存，若是当前 fallback 则重新注入 OMA 配置
    """
    if not args:
        print_error("用法: oma-switch fallback edit <name>")
        sys.exit(1)

    name = args[0].strip()
    if not name:
        print_error("名称不能为空")
        sys.exit(1)

    existing = load_fallback_json(name)
    if existing is None:
        print_error(f"fallback '{name}' 不存在")
        sys.exit(1)

    print_info(f"正在编辑 fallback 配置 '{name}'")
    print()

    summary = get_fallback_summary(existing)
    print_fallback_summary(summary, "当前 Fallback 链:")

    all_models = collect_all_models()

    tpl = load_template()
    fallback_choices: Dict[str, List] = {}
    for type_label in tpl:
        current_chain = existing.get(type_label, {}).get("fallback_models", [])
        selected = prompt_select_fallback_models(type_label, all_models, current_chain)
        fallback_choices[type_label] = selected

    new_config = generate_fallback_from_types(fallback_choices)

    ok, err = validate_fallback_config(new_config)
    if not ok:
        print_error(f"生成的 fallback 配置无效: {err}")
        sys.exit(1)

    save_fallback_json(name, new_config)

    config = load_config()
    if get_current_fallback(config) == name:
        merge_fallback_to_oma_config(new_config)
        print_info("已同步到 OMA 配置文件")

    print()
    print_success(f"已更新 fallback 配置 '{name}'")
    new_summary = get_fallback_summary(new_config)
    print_fallback_summary(new_summary, "更新后 Fallback 链:")


def cmd_fallback_diff(args: List[str]) -> None:
    """
    比较 fallback 配置差异。

    用法: oma-switch fallback diff <name1> [name2]
    如果只提供一个参数，将与当前 fallback 配置比较。
    """
    if not args:
        print_error("用法: oma-switch fallback diff <name1> [name2]")
        print_info("如果只提供一个参数，将与当前 fallback 配置比较")
        return

    config = load_config()
    name1 = args[0]
    name2 = args[1] if len(args) > 1 else get_current_fallback(config)

    if not name2:
        print_error("未指定第二个 fallback 配置且无当前 fallback 配置")
        return

    data1 = load_fallback_json(name1)
    if data1 is None:
        print_error(f"fallback '{name1}' 不存在")
        return

    data2 = load_fallback_json(name2)
    if data2 is None:
        print_error(f"fallback '{name2}' 不存在")
        return

    summary1 = get_fallback_summary(data1)
    summary2 = get_fallback_summary(data2)

    print_info(f"比较 '{name1}' 和 '{name2}':")
    print()

    for category in load_template():
        chain1 = summary1.get(category, [])
        chain2 = summary2.get(category, [])

        if chain1 == chain2:
            status = f"{Colors.GREEN}一致{Colors.NC}"
            print(f"  {Colors.BOLD}{category}{Colors.NC}: {status}")
        else:
            status = f"{Colors.YELLOW}不同{Colors.NC}"
            print(f"  {Colors.BOLD}{category}{Colors.NC}: {status}")
            chain_str1 = " → ".join(chain1) if chain1 else "(空)"
            chain_str2 = " → ".join(chain2) if chain2 else "(空)"
            print(f"    {name1}: {Colors.CYAN}{chain_str1}{Colors.NC}")
            print(f"    {name2}: {Colors.CYAN}{chain_str2}{Colors.NC}")

    print()


def cmd_fallback_switch(args: List[str]) -> None:
    """
    切换 fallback 配置。

    用法: oma-switch fallback switch <name>

    流程:
      1. 验证 fallback 配置存在
      2. 加载并验证配置格式
      3. 注入 fallback_models 到 OMA 配置
      4. 更新 config.json 中的 current_fallback
      5. 打印成功消息
    """
    if not args:
        print_error("用法: oma-switch fallback switch <name>")
        sys.exit(1)

    name = args[0].strip()
    if not name:
        print_error("名称不能为空")
        sys.exit(1)

    fallback_data = load_fallback_json(name)
    if fallback_data is None:
        print_error(f"Fallback 配置 '{name}' 不存在")
        sys.exit(1)

    ok, err = validate_fallback_config(fallback_data)
    if not ok:
        print_error(f"Fallback 配置 '{name}' 格式无效: {err}")
        sys.exit(1)

    merge_fallback_to_oma_config(fallback_data)

    config = load_config()
    set_current_fallback(config, name)

    print_success(f"已切换到 fallback 配置 '{name}'")
    summary = get_fallback_summary(fallback_data)
    print_fallback_summary(summary, "当前 Fallback 链:")


def cmd_fallback_rm(args: List[str]) -> None:
    """删除 fallback 配置。用法: oma-switch fallback rm <name>"""
    if not args:
        print_error("用法: oma-switch fallback rm <name>")
        sys.exit(1)

    name = args[0].strip()
    if not name:
        print_error("名称不能为空")
        sys.exit(1)

    existing = load_fallback_json(name)
    if existing is None:
        print_error(f"Fallback 配置 '{name}' 不存在")
        sys.exit(1)

    response = input(f"确定要删除 fallback '{name}' 吗? (y/N): ").strip().lower()
    if response != 'y':
        print_info("已取消")
        return

    delete_fallback_json(name)

    config = load_config()
    if clear_current_fallback_if_deleted(config, name):
        print_warning(f"Fallback '{name}' 是当前正在使用的配置，已自动取消激活")

    print_success(f"已删除 fallback 配置 '{name}'")


def cmd_switch(args: List[str]) -> None:
    """切换配置文件"""
    if not args:
        print_error("用法: oma-switch switch <name>")
        sys.exit(1)

    name = args[0]
    config = load_config()

    if name not in config["profiles"]:
        print_error(f"配置文件 '{name}' 不存在")
        sys.exit(1)

    profile_path = get_profile_path(name)
    if not profile_path.exists():
        print_error(f"配置文件 '{name}' 文件丢失")
        sys.exit(1)

    profile = load_profile_json(name)
    if profile is None:
        print_error(f"配置文件 '{name}' 格式错误")
        sys.exit(1)

    if OMA_CONFIG.exists():
        backup_path = OMA_CONFIG.with_suffix('.json.backup')
        if backup_path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            archived = OMA_CONFIG.with_suffix(f'.json.backup.{ts}')
            shutil.move(str(backup_path), str(archived))
        shutil.copy2(OMA_CONFIG, backup_path)

    merge_to_oma_config(profile)
    config["current"] = name
    config["profiles"][name]["last_used"] = datetime.now().isoformat()
    save_config(config)

    _apply_profile_dcp(config, name)

    # Re-inject current fallback if set (profile switch replaces agents/categories)
    current_fallback = get_current_fallback(config)
    if current_fallback:
        fallback_data = load_fallback_json(current_fallback)
        if fallback_data is not None:
            merge_fallback_to_oma_config(fallback_data)

    print_success(f"已切换到配置文件 '{name}'")


def cmd_diff(args: List[str]) -> None:
    """
    比较配置文件差异。

快速模式（默认）：比较各分类模型的差异
   详细模式（--detail）：系统 diff 命令（原行为）
    """
    has_detail, remaining_args = parse_flag(args, "--detail")

    if not remaining_args:
        print_error("用法: oma-switch diff [--detail] <name1> [name2]")
        print_info("如果只提供一个参数，将与当前配置比较")
        sys.exit(1)

    config = load_config()
    name1 = remaining_args[0]
    name2 = remaining_args[1] if len(remaining_args) > 1 else config.get("current")

    if name1 not in config["profiles"]:
        print_error(f"配置文件 '{name1}' 不存在")
        sys.exit(1)
    if name2 and name2 not in config["profiles"]:
        print_error(f"配置文件 '{name2}' 不存在")
        sys.exit(1)

    profile1 = load_profile_json(name1)
    if profile1 is None:
        print_error(f"配置文件 '{name1}' 文件丢失或格式错误")
        sys.exit(1)

    profile2 = None
    if name2:
        profile2 = load_profile_json(name2)
        if profile2 is None:
            print_error(f"配置文件 '{name2}' 文件丢失或格式错误")
            sys.exit(1)
    else:
        if not OMA_CONFIG.exists():
            print_error("当前 OMA 配置文件不存在")
            sys.exit(1)
        with open(OMA_CONFIG, 'r', encoding='utf-8') as f:
            profile2 = json.load(f)

    if not has_detail and check_template_profile(profile1) and check_template_profile(profile2):
        summary1, current1 = get_template_summary(profile1)
        summary2, current2 = get_template_summary(profile2)

        label2 = name2 or "当前配置"
        print_info(f"比较 '{name1}' 和 '{label2}' (快速模式):")
        print()

        for t in load_template():
            m1, v1 = current1.get(t, ("—", None))
            m2, v2 = current2.get(t, ("—", None))
            if m1 == m2 and v1 == v2:
                status = f"{Colors.GREEN}一致{Colors.NC}"
            else:
                status = f"{Colors.YELLOW}不同{Colors.NC}"

            print(f"  {Colors.BOLD}{t}{Colors.NC}: {status}")
            print(f"    {name1}: {Colors.CYAN}{m1}{Colors.NC}{' [variant=' + v1 + ']' if v1 else ''}")

            if t in summary1:
                agent_keys1 = [k for s, k in summary1[t].get(m1, []) if s == "agents"]
                cat_keys1 = [k for s, k in summary1[t].get(m1, []) if s == "categories"]
                parts1 = []
                if agent_keys1:
                    parts1.append(f"agents: {', '.join(sorted(agent_keys1))}")
                if cat_keys1:
                    parts1.append(f"categories: {', '.join(sorted(cat_keys1))}")
                for p in parts1:
                    print(f"      {p}")

            print(f"    {label2}: {Colors.CYAN}{m2}{Colors.NC}{' [variant=' + v2 + ']' if v2 else ''}")
            if t in summary2:
                agent_keys2 = [k for s, k in summary2[t].get(m2, []) if s == "agents"]
                cat_keys2 = [k for s, k in summary2[t].get(m2, []) if s == "categories"]
                parts2 = []
                if agent_keys2:
                    parts2.append(f"agents: {', '.join(sorted(agent_keys2))}")
                if cat_keys2:
                    parts2.append(f"categories: {', '.join(sorted(cat_keys2))}")
                for p in parts2:
                    print(f"      {p}")
            print()
        return

    if not has_detail:
        if not check_template_profile(profile1):
            print_warning(f"配置文件 '{name1}' 不符合模板结构，按详细模式比较")
        elif profile2 and not check_template_profile(profile2):
            label2 = name2 or "当前配置"
            print_warning(f"配置文件 '{label2}' 不符合模板结构，按详细模式比较")

    if name2:
        path1 = get_profile_path(name1)
        path2 = get_profile_path(name2)
        print_info(f"比较 '{name1}' 和 '{name2}':")
    else:
        path1 = get_profile_path(name1)
        path2 = OMA_CONFIG
        print_info(f"比较 '{name1}' 和当前配置:")

    try:
        subprocess.run(['diff', '--color=auto', str(path1), str(path2)])
    except FileNotFoundError:
        with open(path1, 'r') as f1, open(path2, 'r') as f2:
            lines1 = f1.readlines()
            lines2 = f2.readlines()
        max_len = max(len(lines1), len(lines2))
        for i in range(max_len):
            l1 = lines1[i].rstrip() if i < len(lines1) else ""
            l2 = lines2[i].rstrip() if i < len(lines2) else ""
            if l1 != l2:
                print(f"行 {i + 1}:")
                print(f"  {name1}: {l1}")
                print(f"  {name2 or 'current'}: {l2}")


def cmd_backup(args: List[str]) -> None:
    """备份当前配置"""
    if not OMA_CONFIG.exists():
        print_error("当前 OMA 配置文件不存在")
        sys.exit(1)

    _create_version_snapshot(OMA_CONFIG, "cmd_backup", args)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    backup_path = PROFILES_DIR / f"{backup_name}.json"

    shutil.copy2(OMA_CONFIG, backup_path)

    config = load_config()
    config["profiles"][backup_name] = {
        "created": datetime.now().isoformat(),
        "description": f"自动备份于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "dcp_enabled": True,
    }
    save_config(config)

    print_success(f"已创建备份: {backup_name}")


def cmd_help() -> None:
    """显示帮助信息"""
    help_text = f"""
OMA 配置文件切换工具 (v2.0)

用法: oma-switch <command> [args...] [--detail]

快速模式（默认）与详细模式（--detail）:
  view, create, diff 命令支持两种模式。

   快速模式（默认）：按模板中的模型分类（强/中/弱/多模态等）维度操作
   详细模式（--detail）：完整的 JSON 编辑/查看/diff（原行为）

   快速模式只适用于符合模板结构（agents + categories）的配置文件。
   不满足时，view/diff 自动降级到详细模式，create 会询问是否进入详细模式。

命令:
    管理相关:
      add <filepath> <name>    添加配置文件到可用列表
      rm <name>                删除配置文件
      rename <name> <newname>  重命名配置文件
      list                     列出所有配置文件
      switch <name>            切换到指定配置文件
      backup                   备份当前配置
      restore [file] [version] 恢复历史版本
      template [edit|reset|diff] 查看/编辑/重置/比较模板
      dcp [subcommand]         管理 DCP 插件（每个配置独立绑定）

   支持双模式（快速/详细）:
     edit [--detail] <name>    编辑配置文件
       - 快速模式: 交互式修改各分类模型，自动生成
       - 详细模式: 打开编辑器编辑完整 JSON

     create [--detail] <name>  创建新配置
       - 快速模式: 指定各分类模型自动生成
       - 详细模式: 复制当前配置并打开编辑器

     view [--detail] [name]    查看配置文件
       - 快速模式: 按模板分组显示
       - 详细模式: 显示完整 JSON

     diff [--detail] <name1> [name2]  比较配置文件
       - 快速模式: 比较各分类模型差异
       - 详细模式: 系统 diff 命令

快速模式的模型分类:
   主模型            → sisyphus, hephaestus, prometheus, atlas
   强模型（Pro）      → oracle, metis, momus, plan, ultrabrain, artistry
   中模型（Standard） → sisyphus-junior, deep, visual-engineering, writing, unspecified-high
   弱模型（Flash）    → explore, librarian, quick, unspecified-low
   多模态模型         → multimodal-looker

配置文件存储位置: ~/.config/oma-switch/profiles/

DCP 插件管理（每个配置独立绑定）:
  dcp                                   查看 DCP 配置摘要
  dcp show                              显示完整 DCP 配置
  dcp on|off                            启用/禁用 DCP（同步到当前配置）
  dcp bind [name]                       查看配置的 DCP 绑定
  dcp bind <name> on|off                设置配置的 DCP 绑定
  dcp edit                              交互式编辑 DCP 插件参数
  dcp set <key> <value>                 快速设置 DCP 插件参数
  dcp-config [models...]                已废弃（请使用 dcp bind）

Fallback 链管理:
  fallback create <name>        创建新的 fallback 链
  fallback list                 列出所有 fallback 链
  fallback switch <name>        切换到指定 fallback 链
  fallback view [name]          查看 fallback 链详情
  fallback edit <name>          编辑 fallback 链
  fallback diff <name1> [name2] 比较 fallback 链
  fallback rm <name>            删除 fallback 链
"""
    print(help_text)


def cmd_fallback(args: List[str]) -> None:
    """Fallback 链管理命令"""
    if not args:
        _fallback_help()
        return

    if args[0] in ("help", "--help", "-h"):
        _fallback_help()
        return

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand == "create":
        cmd_fallback_create(sub_args)
    elif subcommand == "list":
        cmd_fallback_list(sub_args)
    elif subcommand == "switch":
        cmd_fallback_switch(sub_args)
    elif subcommand == "view":
        cmd_fallback_view(sub_args)
    elif subcommand == "edit":
        cmd_fallback_edit(sub_args)
    elif subcommand == "diff":
        cmd_fallback_diff(sub_args)
    elif subcommand == "rm":
        cmd_fallback_rm(sub_args)
    else:
        print_error(f"未知子命令: {subcommand}")
        print_info("使用 'oma-switch fallback help' 查看帮助")


def _fallback_help() -> None:
    """显示 fallback 帮助信息"""
    print_info("Fallback 链管理")
    print()
    print_color(Colors.BOLD, "说明:")
    print("  管理模型 fallback 链配置。切换时自动写入 oh-my-openagent.json 的 fallback_models 字段。")
    print()
    print_color(Colors.BOLD, "用法:")
    print("  oma-switch fallback [help]                 查看此帮助信息")
    print("  oma-switch fallback create <name>          创建新的 fallback 链")
    print("  oma-switch fallback list                   列出所有 fallback 链")
    print("  oma-switch fallback switch <name>          切换到指定 fallback 链")
    print("  oma-switch fallback view [name]            查看 fallback 链详情")
    print("  oma-switch fallback edit <name>            编辑 fallback 链")
    print("  oma-switch fallback diff <name1> [name2]   比较 fallback 链")
    print("  oma-switch fallback rm <name>              删除 fallback 链")


def main() -> None:
    """主函数"""
    ensure_dirs()
    check_current_unrecorded()

    if len(sys.argv) < 2:
        cmd_help()
        sys.exit(0)

    command = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "add": cmd_add,
        "rm": cmd_rm,
        "edit": cmd_edit,
        "create": cmd_create,
        "view": cmd_view,
        "rename": cmd_rename,
        "list": cmd_list,
        "switch": cmd_switch,
        "diff": cmd_diff,
        "backup": cmd_backup,
        "template": cmd_template,
        "dcp-config": cmd_dcp_config,
        "dcp": cmd_dcp,
        "fallback": cmd_fallback,
        "restore": cmd_restore,
        "help": cmd_help,
    }

    if command in commands:
        if command == "help":
            commands[command]()
        else:
            commands[command](args)
    else:
        print_error(f"未知命令: {command}")
        cmd_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
