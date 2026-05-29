#!/usr/bin/env python3
"""
模型使用历史模块：记录、查询、评分模型使用频率。
"""

import json
from typing import Any, Dict, List, Optional

from .constants import HISTORY_FILE
from .display import print_warning
from .io_utils import _atomic_write_json
from .version import _create_version_snapshot, _rotate_versions

__all__ = [
    "load_history",
    "save_history",
    "record_model_usage",
    "get_model_frequency",
    "get_category_frequency",
    "get_category_aware_scores",
]


# ---------- 模型使用历史 ----------


def load_history() -> Dict[str, Any]:
    """加载模型使用历史记录"""
    if not HISTORY_FILE.exists():
        return {"models": {}}
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print_warning("历史记录文件损坏，将重新创建")
        return {"models": {}}


def save_history(history: Dict[str, Any]) -> None:
    """保存模型使用历史记录"""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _create_version_snapshot(HISTORY_FILE, "save_history")
    _atomic_write_json(HISTORY_FILE, history)
    _rotate_versions(HISTORY_FILE)


def record_model_usage(model: str, category: Optional[str] = None) -> None:
    """记录一次模型使用"""
    history = load_history()
    models = history.setdefault("models", {})
    entry = models.setdefault(model, {"count": 0, "categories": {}})
    entry["count"] = entry.get("count", 0) + 1
    if category:
        cats = entry.setdefault("categories", {})
        cats[category] = cats.get(category, 0) + 1
    save_history(history)


def get_model_frequency(model: str) -> int:
    """获取模型总使用次数"""
    history = load_history()
    entry = history.get("models", {}).get(model)
    if entry is None:
        return 0
    return entry.get("count", 0)


def get_category_frequency(model: str, category: str) -> int:
    """获取模型在特定分类下的使用次数"""
    history = load_history()
    entry = history.get("models", {}).get(model)
    if entry is None:
        return 0
    return entry.get("categories", {}).get(category, 0)


def get_category_aware_scores(models: List[str], category: str) -> Dict[str, float]:
    """为每个模型计算上下文感知评分。

    score = total * 0.4 + category_count * 0.6
    模型不在历史中时 score 为 0.0。
    """
    scores: Dict[str, float] = {}
    for model in models:
        total = get_model_frequency(model)
        cat_count = get_category_frequency(model, category)
        scores[model] = total * 0.4 + cat_count * 0.6
    return scores
