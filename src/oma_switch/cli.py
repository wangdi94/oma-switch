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


def prompt_select_model(
    type_label: str,
    all_models: List[str],
    current = None
) -> Tuple[str, Optional[str]]:
    """交互式提示用户选择一个模型，返回 (model, variant)。

    current 可以是 (model, variant) 元组或纯字符串（向后兼容）。
    用户可以通过编号选择现有模型，也可以输入 model[variant] 格式。
    支持模糊搜索：输入非数字文本时过滤模型列表。

    all_models 参数保留向后兼容：如果提供且非空则使用，否则使用 collect_models_enriched。
    """
    if isinstance(current, tuple):
        current_model, current_variant = current
    else:
        current_model, current_variant = current, None

    if all_models:
        enriched_models: List[Tuple[str, Optional[str], int]] = [
            (m, None, get_model_frequency(m)) for m in all_models
        ]
    else:
        enriched_models = collect_models_enriched(category=type_label)

    if not enriched_models:
        print_warning("当前无可用模型，请先创建配置或添加已有配置")
        return (None, None)

    def _display_models(models: List[Tuple[str, Optional[str], int]]) -> None:
        print(f"    可用模型:")
        for i, (m, v, _f) in enumerate(models, 1):
            marker = " (当前)" if m == current_model else ""
            variant_str = f" [{v}]" if v else ""
            print(f"      [{i}] {m}{variant_str}{marker}")

    print(f"  {Colors.BOLD}{type_label}{Colors.NC}")
    if current_model:
        if current_variant:
            print(f"    当前: {Colors.CYAN}{current_model} [variant={current_variant}]{Colors.NC}")
        else:
            print(f"    当前: {Colors.CYAN}{current_model}{Colors.NC}")

    display_list = enriched_models
    _display_models(display_list)

    while True:
        prompt_text = f"  请输入{type_label}（编号/模型名[variant]/搜索"
        if current_model:
            prompt_text += "/留空=当前值"
        prompt_text += "）: "
        choice = input(prompt_text).strip()

        if not choice:
            if current_model:
                return current_model, current_variant
            elif enriched_models:
                print_warning(f"未选择{type_label}，使用第一个可用模型")
                chosen = enriched_models[0]
                record_model_usage(chosen[0], type_label)
                return chosen[0], chosen[1]
            else:
                return "", None

        if choice.isdigit():
            if choice == "0":
                print_warning("编号从 1 开始，请重新输入")
                continue
            idx = int(choice) - 1
            if 0 <= idx < len(display_list):
                chosen = display_list[idx]
                record_model_usage(chosen[0], type_label)
                return chosen[0], chosen[1]
            print_warning("无效编号，请重新选择")
            continue

        model_names = [m for m, _v, _f in enriched_models]
        parsed_model, parsed_variant = parse_model_with_variant(choice)
        if parsed_variant is not None:
            record_model_usage(parsed_model, type_label)
            return parsed_model, parsed_variant

        matches = fuzzy_match_models(choice, model_names)
        if matches:
            match_set = set(matches)
            filtered = [(m, v, f) for m, v, f in enriched_models if m in match_set]
            display_list = filtered
            print(f"    搜索 '{choice}' 的结果 ({len(filtered)} 个):")
            _display_models(display_list)
        else:
            print_warning("未找到匹配的模型，请重新输入")
            display_list = enriched_models
            _display_models(display_list)


MAX_FALLBACK_MODELS = 5


def prompt_select_fallback_models(
    type_label: str,
    all_models: List[str],
    current: Optional[List] = None,
) -> List:
    """交互式提示用户选择 fallback 模型链，返回选中的模型列表。

    current 可以是字符串列表或包含 variant 的字典列表（向后兼容）。
    用户可以通过逗号分隔的编号或模型名选择多个模型，支持 model[variant] 格式。
    空输入在有当前值时保留当前链，在无当前值时清空链（返回 []）。最多选择 MAX_FALLBACK_MODELS 个模型。
    模型按分类分组展示，支持搜索过滤，记录使用历史。
    """
    if current is None:
        current = []

    print(f"  {Colors.BOLD}{type_label} Fallback 链{Colors.NC}")
    if current:
        display_items = []
        for item in current:
            if isinstance(item, dict):
                m = item.get("model", "")
                v = item.get("variant")
                display_items.append(f"{m}[{v}]" if v else m)
            else:
                display_items.append(str(item))
        print(f"    当前: {Colors.CYAN}{', '.join(display_items)}{Colors.NC}")
    else:
        print(f"    当前: {Colors.GRAY}(空){Colors.NC}")

    enriched = collect_models_enriched(type_label)
    if not enriched:
        enriched = [(m, None, 0) for m in all_models]
    model_names = [m for m, _v, _f in enriched]

    last_used = None
    best_freq = 0
    for model, _v, _f in enriched:
        cat_freq = get_category_frequency(model, type_label)
        if cat_freq > best_freq:
            best_freq = cat_freq
            last_used = model

    def _display_grouped(models_enriched: List[Tuple[str, Optional[str], int]]) -> List[str]:
        print(f"    可用模型（最多选 {MAX_FALLBACK_MODELS} 个）:")
        indexed: List[str] = []
        idx = 1
        categorized_set: set = set()

        for category in DEFAULT_TEMPLATE_GROUPS:
            cat_models = [
                (m, v, f) for m, v, f in models_enriched
                if get_category_frequency(m, category) > 0
            ]
            if cat_models:
                print(f"      {Colors.GRAY}── {category} ──{Colors.NC}")
                for model, variant, _freq in cat_models:
                    var_str = f" [{variant}]" if variant else ""
                    last_str = f" {Colors.YELLOW}(上次){Colors.NC}" if model == last_used else ""
                    print(f"      [{idx}] {model}{var_str}{last_str}")
                    indexed.append(model)
                    categorized_set.add(model)
                    idx += 1

        other_models = [
            (m, v, f) for m, v, f in models_enriched
            if m not in categorized_set
        ]
        if other_models:
            print(f"      {Colors.GRAY}── 其他 ──{Colors.NC}")
            for model, variant, _freq in other_models:
                var_str = f" [{variant}]" if variant else ""
                last_str = f" {Colors.YELLOW}(上次){Colors.NC}" if model == last_used else ""
                print(f"      [{idx}] {model}{var_str}{last_str}")
                indexed.append(model)
                idx += 1

        return indexed

    def _apply_selection(parts: List[str], indexed: List[str]) -> List:
        selected: List = []
        for part in parts:
            if part.isdigit():
                i = int(part) - 1
                if 0 <= i < len(indexed):
                    selected.append(indexed[i])
                else:
                    print_warning(f"无效编号: {part}，已跳过")
            else:
                model, variant = parse_model_with_variant(part)
                if variant:
                    selected.append({"model": model, "variant": variant})
                else:
                    selected.append(model)
        return selected

    def _truncate_and_record(selected: List) -> List:
        if len(selected) > MAX_FALLBACK_MODELS:
            print_warning(
                f"最多只能选择 {MAX_FALLBACK_MODELS} 个 fallback 模型，"
                f"已截取前 {MAX_FALLBACK_MODELS} 个"
            )
            selected = selected[:MAX_FALLBACK_MODELS]
        for item in selected:
            m = item.get("model", item) if isinstance(item, dict) else item
            record_model_usage(m, "fallback")
        return selected

    indexed_models = _display_grouped(enriched)

    if current:
        prompt_text = (
            f"  请输入{type_label} fallback 模型"
            f"（逗号分隔的编号/模型名[variant]，留空=保留当前）: "
        )
    else:
        prompt_text = (
            f"  请输入{type_label} fallback 模型"
            f"（逗号分隔的编号/模型名[variant]，留空=清空）: "
        )

    while True:
        choice = input(prompt_text).strip()

        if not choice:
            return list(current) if current else []

        parts = [p.strip() for p in choice.split(",") if p.strip()]

        if len(parts) == 1 and not parts[0].isdigit():
            query = parts[0]
            if any(c in query for c in "-.[]/"):
                model, variant = parse_model_with_variant(query)
                selected = [{"model": model, "variant": variant}] if variant else [model]
                return _truncate_and_record(selected)

            matches = fuzzy_match_models(query, model_names)
            if matches:
                print(f"    {Colors.GRAY}搜索 '{query}' 的结果:{Colors.NC}")
                match_set = set(matches)
                filtered = [(m, v, f) for m, v, f in enriched if m in match_set]
                filtered_indexed = _display_grouped(filtered)

                inner = input(f"  请选择（逗号分隔编号，留空=取消搜索）: ").strip()
                if not inner:
                    indexed_models = _display_grouped(enriched)
                    continue

                inner_parts = [p.strip() for p in inner.split(",") if p.strip()]
                selected = _apply_selection(inner_parts, filtered_indexed)
                return _truncate_and_record(selected)
            else:
                print_warning(f"未找到匹配 '{query}' 的模型")
                continue

        selected = _apply_selection(parts, indexed_models)
        return _truncate_and_record(selected)


def generate_profile_from_types(
    template: dict,
    model_map: Dict[str, Tuple[str, Optional[str]]]
) -> dict:
    """
    根据模板生成新 profile。
    model_map: {类型: (新模型名, variant)}
    按模板分组替换各角色的 model 和 variant。
    如果模板中的条目在 profile 中不存在，则自动创建。
    """
    new_profile = copy.deepcopy(template)
    tpl = load_template()
    for type_label, entries in tpl.items():
        model_info = model_map.get(type_label)
        if model_info:
            new_model, variant = model_info
            for section, key in entries:
                if section not in new_profile:
                    new_profile[section] = {}
                if key not in new_profile[section]:
                    new_profile[section][key] = {}
                
                new_profile[section][key]["model"] = new_model
                if variant:
                    new_profile[section][key]["variant"] = variant
                else:
                    new_profile[section][key].pop("variant", None)
    return new_profile


def generate_fallback_from_types(
    fallback_choices: Dict[str, List]
) -> Dict[str, Any]:
    """
    根据用户选择的 fallback 模型列表生成完整的 fallback 配置字典。
    fallback_choices: {类型标签: [模型名或{model, variant}字典, ...]}
    按模板结构输出: {类型标签: {"fallback_models": [...]}}
    未指定的类型默认为 {"fallback_models": []}。
    """
    tpl = load_template()
    result: Dict[str, Any] = {}
    for type_label in tpl:
        chain = fallback_choices.get(type_label, [])
        result[type_label] = {"fallback_models": list(chain)}
    return result


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
