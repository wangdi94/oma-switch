#!/usr/bin/env python3
"""
Prompt module for oma-switch.

Contains interactive prompt functions and generation functions.
"""

import copy
from typing import Any, Dict, List, Optional, Tuple

from .types import FallbackData

from .display import Colors, print_warning
from .history import get_category_frequency, get_model_frequency, record_model_usage
from .models import collect_models_enriched, fuzzy_match_models
from .template import DEFAULT_TEMPLATE_GROUPS, load_template, parse_model_with_variant


def prompt_select_model(
    type_label: str,
    all_models: List[str],
    current=None,
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
    model_map: Dict[str, Tuple[str, Optional[str]]],
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
    fallback_choices: Dict[str, List],
) -> FallbackData:
    """
    根据用户选择的 fallback 模型列表生成完整的 fallback 配置字典。
    fallback_choices: {类型标签: [模型名或{model, variant}字典, ...]}
    按模板结构输出: {类型标签: {"fallback_models": [...]}}
    未指定的类型默认为 {"fallback_models": []}。
    """
    from .types import FallbackCategory
    tpl = load_template()
    result: FallbackData = {}
    for type_label in tpl:
        chain = fallback_choices.get(type_label, [])
        result[type_label] = {"fallback_models": list(chain)}  # type: ignore[literal-required]
    return result
