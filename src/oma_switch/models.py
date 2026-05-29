#!/usr/bin/env python3
"""
Models module for oma-switch.

Contains model collection, analysis, and search functions.
"""

import json
from typing import Dict, List, Optional, Tuple

from .constants import HAS_THEFUZZ, _fuzz, PROFILES_DIR, OMA_CONFIG, FALLBACKS_DIR
from .history import get_model_frequency, get_category_frequency, get_category_aware_scores
from .template import parse_model_with_variant
from .display import print_warning


def collect_all_models() -> List[str]:
    """从所有 profile、当前 OMA 配置和 fallback 配置中提取所有不重复的模型名"""
    models = set()

    if PROFILES_DIR.exists():
        for f in sorted(PROFILES_DIR.glob("*.json")):
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    profile = json.load(fh)
                for section in ("agents", "categories"):
                    for value in profile.get(section, {}).values():
                        if isinstance(value, dict) and "model" in value:
                            models.add(value["model"])
            except (json.JSONDecodeError, IOError) as e:
                print_warning(f"读取配置文件 {f.name} 失败: {e}")

    if OMA_CONFIG.exists():
        try:
            with open(OMA_CONFIG, 'r', encoding='utf-8') as f:
                profile = json.load(f)
            for section in ("agents", "categories"):
                for value in profile.get(section, {}).values():
                    if isinstance(value, dict) and "model" in value:
                        models.add(value["model"])
        except (json.JSONDecodeError, IOError) as e:
            print_warning(f"读取 OMA 配置失败: {e}")

    if FALLBACKS_DIR.exists():
        for f in sorted(FALLBACKS_DIR.glob("*.json")):
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    fallback = json.load(fh)
                for category_data in fallback.values():
                    if isinstance(category_data, dict):
                        for item in category_data.get("fallback_models", []):
                            if isinstance(item, dict):
                                models.add(item.get("model", ""))
                            elif isinstance(item, str):
                                models.add(item)
            except (json.JSONDecodeError, IOError) as e:
                print_warning(f"读取 fallback 文件 {f.name} 失败: {e}")

    return sorted(models)


def collect_models_enriched(category: Optional[str] = None) -> List[Tuple[str, Optional[str], int]]:
    """从所有来源收集模型，返回 (model, variant, frequency) 列表。

    category 为 None 时按 frequency DESC, model ASC 排序。
    category 有值时按上下文感知评分（total*0.4 + cat_count*0.6）排序。
    同一模型从多个来源收集时取最高频率，保留有 variant 的版本。
    """
    model_map: Dict[str, Tuple[Optional[str], int]] = {}

    def _add_model(model: str, variant: Optional[str] = None) -> None:
        freq = get_model_frequency(model)
        if model in model_map:
            existing_variant, _existing_freq = model_map[model]
            new_variant = variant if variant is not None else existing_variant
            model_map[model] = (new_variant, freq)
        else:
            model_map[model] = (variant, freq)

    # 从 profiles 收集
    if PROFILES_DIR.exists():
        for f in PROFILES_DIR.glob("*.json"):
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    profile = json.load(fh)
                for section in ("agents", "categories"):
                    for value in profile.get(section, {}).values():
                        if isinstance(value, dict) and "model" in value:
                            _add_model(value["model"], value.get("variant"))
            except (json.JSONDecodeError, IOError):
                pass

    # 从 OMA_CONFIG 收集
    if OMA_CONFIG.exists():
        try:
            with open(OMA_CONFIG, 'r', encoding='utf-8') as f:
                profile = json.load(f)
            for section in ("agents", "categories"):
                for value in profile.get(section, {}).values():
                    if isinstance(value, dict) and "model" in value:
                        _add_model(value["model"], value.get("variant"))
        except (json.JSONDecodeError, IOError):
            pass

    # 从 fallbacks 收集
    if FALLBACKS_DIR.exists():
        for f in FALLBACKS_DIR.glob("*.json"):
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    fallback = json.load(fh)
                for category_data in fallback.values():
                    if isinstance(category_data, dict):
                        for item in category_data.get("fallback_models", []):
                            if isinstance(item, dict):
                                _add_model(item.get("model", ""), item.get("variant"))
                            elif isinstance(item, str):
                                model, variant = parse_model_with_variant(item)
                                _add_model(model, variant)
            except (json.JSONDecodeError, IOError):
                pass

    result = [(model, variant, freq) for model, (variant, freq) in model_map.items()]
    if category is not None:
        scores = get_category_aware_scores([m for m, _v, _f in result], category)
        result.sort(key=lambda x: (-scores.get(x[0], 0.0), x[0]))
    else:
        result.sort(key=lambda x: (-x[2], x[0]))
    return result


def fuzzy_match_models(query: str, candidates: List[str], limit: int = -1) -> List[str]:
    """模糊匹配模型名。

    如果 HAS_THEFUZZ，使用 partial_ratio 评分；否则使用 difflib。
    前缀匹配的候选排在最前。
    """
    if not query or not candidates:
        return []

    matches: List[str] = []
    if HAS_THEFUZZ:
        scored: List[Tuple[str, int]] = []
        for c in candidates:
            score = _fuzz.partial_ratio(query.lower(), c.lower())
            if score >= 60:
                scored.append((c, score))
        scored.sort(key=lambda x: -x[1])
        matches = [c for c, _ in scored]
    else:
        import difflib
        matches = list(difflib.get_close_matches(query, candidates, n=10, cutoff=0.6))

    prefix_matches = sorted(
        [c for c in candidates if c.lower().startswith(query.lower())],
        key=lambda c: (len(c), c.lower()),
    )
    non_prefix = [m for m in matches if m not in prefix_matches]
    matches = prefix_matches + non_prefix

    if limit > 0:
        matches = matches[:limit]
    return matches


def filter_models_by_category(models: List[str], category: str) -> List[str]:
    """过滤出在指定分类下有使用记录的模型。

    .. deprecated::
        此函数已弃用，无调用者。请使用 collect_models_enriched(category) 代替。
    """
    import warnings
    warnings.warn(
        "filter_models_by_category 已弃用，请使用 collect_models_enriched(category) 代替",
        DeprecationWarning,
        stacklevel=2,
    )
    return [m for m in models if get_category_frequency(m, category) > 0]


def parse_model_vendor_name(model: str) -> Tuple[str, str]:
    """解析 vendor/model 格式，返回 (vendor, model_name)，均不含 variant。

    例如:
      "xiaomi-token-plan-sgp/deepseek-v4-pro"       → ("xiaomi-token-plan-sgp", "deepseek-v4-pro")
      "openai/gpt-4o[max]"                           → ("openai", "gpt-4o")
      "gpt-4o"                                        → ("", "gpt-4o")
    """
    model_part, _variant = parse_model_with_variant(model)
    if "/" in model_part:
        vendor, name = model_part.split("/", 1)
        return vendor, name
    return "", model_part


def recommend_cross_vendor_models(model_name: str, all_models: List[str]) -> List[str]:
    """查找同模型名不同供应商的推荐模型。

    解析 model_name 获取 (vendor, model_part)，
    对 all_models 中每个模型解析后比较 model_part，
    返回 model_part 相同但 vendor 不同的模型列表，
    按 get_model_frequency() 降序排列。
    """
    target_vendor, target_model = parse_model_vendor_name(model_name)
    if not target_model:
        return []

    recommendations: List[Tuple[str, int]] = []
    for m in all_models:
        v, name = parse_model_vendor_name(m)
        if name == target_model and v != target_vendor:
            freq = get_model_frequency(m)
            recommendations.append((m, freq))

    recommendations.sort(key=lambda x: -x[1])
    return [m for m, _freq in recommendations]
