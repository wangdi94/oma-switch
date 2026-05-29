#!/usr/bin/env python3
"""
模板管理模块：模板定义、加载/保存、验证、摘要、同步。
"""

import copy
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import CONFIG_DIR, TEMPLATE_FILE
from .display import (
    Colors,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from .io_utils import _atomic_write_json
from .version import _create_version_snapshot, _rotate_versions
from .config_io import (
    get_profile_path,
    is_valid_json,
    load_config,
    load_profile_json,
    save_config,
)

__all__ = [
    "DEFAULT_TEMPLATE_GROUPS",
    "parse_model_with_variant",
    "_template_to_json",
    "_template_from_json",
    "load_template",
    "save_template",
    "check_template_profile",
    "validate_fallback_config",
    "get_template_summary",
    "print_type_summary",
    "_format_fallback_item",
    "get_fallback_summary",
    "print_fallback_summary",
    "sync_profiles_after_template_change",
    "cmd_template",
]


# ── 模型分析相关函数 ──────────────────────────────────────────────

def parse_model_with_variant(model_str: str) -> Tuple[str, Optional[str]]:
    """解析 'model[variant]' 格式，返回 (model, variant)。
    
    例如:
      "deepseek-v4-pro[max]" → ("deepseek-v4-pro", "max")
      "gemini-3-pro"          → ("gemini-3-pro", None)
    """
    import re
    stripped = model_str.strip()
    match = re.match(r'^(.+?)\s*\[(\w+)\]\s*$', stripped)
    if match:
        return match.group(1).strip(), match.group(2).lower()
    return stripped, None


# ── 模板定义 ─────────────────────────────────────────────────────
# 默认模板（内置），使用 MappingProxyType 保护不被意外修改
DEFAULT_TEMPLATE_GROUPS: Any = types.MappingProxyType({
    "主模型": frozenset({
        ("agents", "sisyphus"),
        ("agents", "hephaestus"),
        ("agents", "prometheus"),
        ("agents", "atlas"),
    }),
    "强模型": frozenset({
        ("agents", "oracle"),
        ("agents", "metis"),
        ("agents", "momus"),
        ("agents", "plan"),
        ("categories", "ultrabrain"),
        ("categories", "artistry"),
    }),
    "中模型": frozenset({
        ("agents", "sisyphus-junior"),
        ("categories", "deep"),
        ("categories", "visual-engineering"),
        ("categories", "writing"),
        ("categories", "unspecified-high"),
    }),
    "弱模型": frozenset({
        ("agents", "explore"),
        ("agents", "librarian"),
        ("categories", "quick"),
        ("categories", "unspecified-low"),
    }),
    "多模态模型": frozenset({
        ("agents", "multimodal-looker"),
    }),
})


def _template_to_json(template: Dict[str, set]) -> dict:
    """将内部模板格式转为可序列化的 JSON 格式"""
    return {
        type_label: sorted([list(entry) for entry in entries])
        for type_label, entries in template.items()
    }


def _template_from_json(data: dict) -> Dict[str, set]:
    """将 JSON 格式转为内部模板格式"""
    result = {}
    for type_label, entries in data.items():
        result[type_label] = {tuple(entry) for entry in entries}
    return result


def load_template() -> Dict[str, set]:
    """加载模板：优先使用用户自定义模板，否则使用默认模板"""
    if TEMPLATE_FILE.exists():
        try:
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return _template_from_json(data)
        except (json.JSONDecodeError, IOError):
            print_warning("模板文件损坏，使用默认模板")
    return copy.deepcopy(dict(DEFAULT_TEMPLATE_GROUPS))


def save_template(template: Dict[str, set]) -> None:
    """保存用户自定义模板到文件"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _create_version_snapshot(TEMPLATE_FILE, "save_template")
    _atomic_write_json(TEMPLATE_FILE, _template_to_json(template))
    _rotate_versions(TEMPLATE_FILE)


def check_template_profile(profile: dict, template: Optional[Dict[str, set]] = None) -> bool:
    """
    检查 profile 是否满足模板要求：
    - 模板中定义的所有条目（agents + categories）都存在
    - 每个角色组（强/弱/多模态）内的所有条目使用同一个模型

    参数:
        profile: 待检查的 profile
        template: 要匹配的模板，默认使用当前模板
    """
    if not isinstance(profile, dict):
        return False

    if template is None:
        template = load_template()
    for type_label, entries in template.items():
        models = set()
        for section, key in entries:
            entry = profile.get(section, {}).get(key)
            if not isinstance(entry, dict) or "model" not in entry:
                return False
            models.add(entry["model"])
        if len(models) != 1:
            return False

    return True


def validate_fallback_config(data: dict) -> Tuple[bool, str]:
    """
    验证 fallback 配置的格式是否合法。

    校验规则：
    - 顶级键必须是模板分类标签（主模型/强模型/中模型/弱模型/多模态模型）
    - 每个值必须包含 fallback_models 键
    - fallback_models 必须是列表
    - 列表中每个对象必须包含 model 键
    - 每个链最多 5 个模型
    - 链内不允许重复模型

    返回:
        (True, "") 验证通过
        (False, error_message) 验证失败，附带错误描述
    """
    valid_categories = set(DEFAULT_TEMPLATE_GROUPS.keys())

    for category, value in data.items():
        if category not in valid_categories:
            return False, f"unknown category: {category}"

        if not isinstance(value, dict) or "fallback_models" not in value:
            return False, f"missing fallback_models in category: {category}"

        models = value["fallback_models"]
        if not isinstance(models, list):
            return False, f"fallback_models must be a list in category: {category}"

        if len(models) > 5:
            return False, f"too many models in category: {category}, max is 5"

        seen: list = []
        for item in models:
            if isinstance(item, dict):
                if "model" not in item:
                    return False, f"object item missing 'model' key in category: {category}"
                model_str = str(item["model"])
            else:
                model_str = str(item)
            if model_str in seen:
                return False, f"duplicate model in category: {category}"
            seen.append(model_str)

    return True, ""


def get_template_summary(profile: dict) -> Tuple[Dict, Dict]:
    """
    按模板分组获取摘要。
    仅在 profile 通过 check_template_profile 后调用。
    返回: (summary, current_models)
    - summary: {类型: {模型名: [(section, key), ...]}}
    - current_models: {类型: (模型名, variant)} — variant 为 Optional[str]
    """
    summary = {}
    current_models = {}

    template = load_template()
    for type_label, entries in template.items():
        section, key = next(iter(entries))
        entry = profile.get(section, {}).get(key, {})
        common_model = entry.get("model", "")
        common_variant = entry.get("variant")

        summary[type_label] = {common_model: list(entries)}
        current_models[type_label] = (common_model, common_variant)

    return summary, current_models


def print_type_summary(summary: Dict, title: str = None, current_models: Dict = None) -> None:
    """打印格式化的模型分类摘要。
    
    current_models: {类型: (模型名, variant)} — 用于显示 variant 信息
    """
    if title:
        print_info(title)
        print()

    template = load_template()
    for t in template:
        if t not in summary:
            continue
        entries = summary[t]
        for model, keys in entries.items():
            agent_keys = [k for s, k in keys if s == "agents"]
            cat_keys = [k for s, k in keys if s == "categories"]
            parts = []
            if agent_keys:
                parts.append(f"agents: {', '.join(sorted(agent_keys))}")
            if cat_keys:
                parts.append(f"categories: {', '.join(sorted(cat_keys))}")
            # 显示 model 名称，如果有 variant 则附加 [variant=xxx]
            model_display = model
            if current_models and t in current_models:
                _, variant = current_models[t]
                if variant:
                    model_display = f"{model} [variant={variant}]"
            print(f"  {Colors.BOLD}{t}{Colors.NC}:")
            print(f"    {Colors.CYAN}{model_display}{Colors.NC}")
            for p in parts:
                print(f"      {p}")
        print()


def _format_fallback_item(item: Any) -> str:
    """格式化 fallback 链中的单个条目。
    
    字符串条目直接返回；字典条目格式化为 'model [variant=xxx]'。
    """
    if isinstance(item, dict):
        model = item.get("model", "")
        variant = item.get("variant")
        if variant:
            return f"{model} [variant={variant}]"
        return str(model)
    return str(item)


def get_fallback_summary(fallback_data: Dict) -> Dict[str, List[str]]:
    """
    从 fallback 配置中提取每类的显示链。
    
    参数:
        fallback_data: fallback 配置字典，格式如:
            {"主模型": {"fallback_models": ["model-a", ...]}, ...}
    
    返回:
        {category_label: [model_strings]}
        每个 model_string 已格式化（字典条目显示为 model [variant=xxx]）
    """
    summary: Dict[str, List[str]] = {}
    for category, value in fallback_data.items():
        models = value.get("fallback_models", []) if isinstance(value, dict) else []
        summary[category] = [_format_fallback_item(item) for item in models]
    return summary


def print_fallback_summary(summary: Dict[str, List[str]], title: str = None) -> None:
    """打印格式化的 fallback 链摘要。
    
    显示格式:
        主模型:
          fallback: model-a → model-b → model-c
        强模型:
          fallback: (none)
    """
    if title:
        print_info(title)
        print()

    template = load_template()
    for category in template:
        if category not in summary:
            continue
        chain = summary[category]
        print(f"  {Colors.BOLD}{category}{Colors.NC}:")
        if chain:
            chain_str = f" → ".join(chain)
            print(f"    fallback: {Colors.CYAN}{chain_str}{Colors.NC}")
        else:
            print(f"    fallback: {Colors.GRAY}(none){Colors.NC}")
    print()


def sync_profiles_after_template_change(old_template: Dict[str, set], new_template: Dict[str, set]) -> int:
    """同步所有 profiles 到新模板。返回更新的 profile 数量。"""
    config = load_config()
    updated = 0

    old_entry_to_group = {}
    for group, entries in old_template.items():
        for entry in entries:
            old_entry_to_group[entry] = group

    for name in config.get("profiles", {}):
        profile = load_profile_json(name)
        if profile is None:
            continue

        # 跳过不满足旧模板的 profile（如 --detail 模式创建的），
        # 避免对这些 profile 误加空条目并错误计数
        if not check_template_profile(profile, old_template):
            continue

        changed = False
        for group, entries in new_template.items():
            for section, key in entries:
                if section not in profile:
                    profile.setdefault(section, {})
                if key not in profile[section]:
                    profile[section][key] = {"model": ""}
                    changed = True

                old_group = old_entry_to_group.get((section, key))
                if old_group and old_group != group:
                    old_model = profile.get(section, {}).get(key, {}).get("model", "")
                    group_models = set()
                    for s, k in new_template.get(group, set()):
                        m = profile.get(s, {}).get(k, {}).get("model")
                        if m:
                            group_models.add(m)
                    group_models.discard("")
                    if group_models:
                        profile[section][key]["model"] = sorted(group_models)[0]
                    else:
                        profile[section][key]["model"] = old_model
                    changed = True

        if changed:
            profile_path = get_profile_path(name)
            _create_version_snapshot(profile_path, "sync_profiles")
            _atomic_write_json(profile_path, profile)
            _rotate_versions(profile_path)
            updated += 1

    return updated


def cmd_template(args: List[str]) -> None:
    """查看或编辑模板"""
    # 延迟导入避免循环依赖
    from .cli import open_editor

    if not args:
        template = load_template()
        is_custom = TEMPLATE_FILE.exists()

        if is_custom:
            print_info("当前模板 (自定义):")
        else:
            print_info("当前模板 (默认):")

        print()
        for type_label, entries in template.items():
            agent_keys = sorted([k for s, k in entries if s == "agents"])
            cat_keys = sorted([k for s, k in entries if s == "categories"])
            print(f"  {Colors.BOLD}{type_label}{Colors.NC}:")
            if agent_keys:
                print(f"    agents: {', '.join(agent_keys)}")
            if cat_keys:
                print(f"    categories: {', '.join(cat_keys)}")
        print()

        print_dim(f"模板文件: {TEMPLATE_FILE}")
        if is_custom:
            print_dim("使用 'oma-switch template reset' 恢复默认模板")
        else:
            print_dim("使用 'oma-switch template edit' 自定义模板")
        return

    subcommand = args[0]

    if subcommand == "edit":
        template = load_template()
        json_data = _template_to_json(template)

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _create_version_snapshot(TEMPLATE_FILE, "cmd_template")
        _atomic_write_json(TEMPLATE_FILE, json_data)
        _rotate_versions(TEMPLATE_FILE)

        print_info("正在编辑模板...")
        if open_editor(TEMPLATE_FILE):
            if is_valid_json(TEMPLATE_FILE):
                try:
                    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                        new_data = json.load(f)
                    new_template = _template_from_json(new_data)

                    updated = sync_profiles_after_template_change(template, new_template)
                    save_template(new_template)

                    print_success(f"模板已更新，同步了 {updated} 个配置文件")
                except (json.JSONDecodeError, KeyError, ValueError, IOError) as e:
                    print_error(f"模板格式错误: {e}")
                    if template != DEFAULT_TEMPLATE_GROUPS:
                        save_template(template)
                        print_info("已恢复之前的模板")
                    else:
                        TEMPLATE_FILE.unlink(missing_ok=True)
                        print_info("已恢复默认模板")
            else:
                print_error("模板文件格式错误，已恢复")
                if template != DEFAULT_TEMPLATE_GROUPS:
                    save_template(template)
                else:
                    TEMPLATE_FILE.unlink(missing_ok=True)
        else:
            print_error("编辑失败")
        return

    if subcommand == "reset":
        if TEMPLATE_FILE.exists():
            old_template = load_template()
            try:
                updated = sync_profiles_after_template_change(old_template, DEFAULT_TEMPLATE_GROUPS)
                TEMPLATE_FILE.unlink()
                print_success(f"已恢复默认模板，同步了 {updated} 个配置文件")
            except IOError as e:
                print_error(f"同步配置文件失败: {e}")
                print_warning("模板文件未删除，配置可能不一致")
        else:
            print_info("当前使用的就是默认模板")
        return

    if subcommand == "diff":
        template = load_template()
        is_custom = TEMPLATE_FILE.exists()

        if not is_custom:
            print_info("当前使用默认模板，没有差异可比较")
            return

        print_info("自定义模板 vs 默认模板:")
        print()

        all_groups = set(template.keys()) | set(DEFAULT_TEMPLATE_GROUPS.keys())
        for group in sorted(all_groups):
            custom_entries = template.get(group, set())
            default_entries = DEFAULT_TEMPLATE_GROUPS.get(group, set())

            added = custom_entries - default_entries
            removed = default_entries - custom_entries

            if not added and not removed:
                continue

            print(f"  {Colors.BOLD}{group}{Colors.NC}:")
            for section, key in sorted(added):
                print(f"    {Colors.GREEN}+ {section}.{key}{Colors.NC}")
            for section, key in sorted(removed):
                print(f"    {Colors.RED}- {section}.{key}{Colors.NC}")
            print()
        return

    print_error(f"未知子命令: {subcommand}")
    print_info("用法: oma-switch template [edit|reset|diff]")
    sys.exit(1)
