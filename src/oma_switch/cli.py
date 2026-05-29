#!/usr/bin/env python3
"""
OMA (Oh-My-Agent) 配置文件切换工具
用于管理 opencode 的 oh-my-openagent.json 配置文件

快速模式（默认）：按模板中的模型分类（主/强/中/弱/多模态等）进行查看、创建、比较
详细模式（--detail）：完整的 JSON 操作（编辑/全文查看/系统 diff）
"""

import json
import os
import re
import readline  # 启用 input() 的行编辑功能（方向键、历史记录等）
import sys
import copy
import shutil
import subprocess
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


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    PURPLE = "\033[0;35m"
    CYAN = "\033[0;36m"
    GRAY = "\033[0;90m"
    BOLD = "\033[1m"
    NC = "\033[0m"


def print_color(color: str, message: str) -> None:
    print(f"{color}{message}{Colors.NC}")


def print_error(message: str) -> None:
    print_color(Colors.RED, f"错误: {message}")


def print_success(message: str) -> None:
    print_color(Colors.GREEN, f"✓ {message}")


def print_warning(message: str) -> None:
    print_color(Colors.YELLOW, f"⚠ {message}")


def print_info(message: str) -> None:
    print_color(Colors.BLUE, f"ℹ {message}")


def print_dim(message: str) -> None:
    print_color(Colors.GRAY, message)


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    FALLBACKS_DIR.mkdir(parents=True, exist_ok=True)


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
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


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


def get_dcp_config() -> Dict[str, Any]:
    """获取 DCP 插件配置"""
    if not DCP_CONFIG_FILE.exists():
        return {"enabled": False}
    try:
        with open(DCP_CONFIG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            content = re.sub(r'//.*?\n', '\n', content)
            content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
            return json.loads(content)
    except (json.JSONDecodeError, IOError):
        return {"enabled": False}


def save_dcp_config(config: Dict[str, Any]) -> None:
    """保存 DCP 插件配置"""
    OPENCODE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DCP_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def update_dcp_state(enable: bool) -> None:
    """更新 DCP 插件状态（仅修改 enabled 字段，保留其他配置）"""
    state = "启用" if enable else "禁用"
    value = "true" if enable else "false"

    if not DCP_CONFIG_FILE.exists():
        OPENCODE_DIR.mkdir(parents=True, exist_ok=True)
        with open(DCP_CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(f'{{\n  "enabled": {value}\n}}\n')
        print_info(f"DCP 插件已{state}")
        return

    with open(DCP_CONFIG_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # 替换 "enabled": true/false，保留文件其余内容不变
    new_content, count = re.subn(
        r'("enabled"\s*:\s*)(true|false)',
        rf'\g<1>{value}',
        content,
        count=1,
    )

    if count == 0:
        # enabled 字段不存在，尝试在第一个 { 后插入
        new_content, count = re.subn(
            r'(\{)',
            rf'{{\n  "enabled": {value},',
            content,
            count=1,
        )

    if count > 0:
        with open(DCP_CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(new_content)
    else:
        print_error("无法更新 DCP 配置：文件格式异常")

    print_info(f"DCP 插件已{state}")


def _get_profile_dcp_enabled(profile_meta: Dict[str, Any]) -> bool:
    """获取配置文件的 DCP 绑定状态，默认启用"""
    return profile_meta.get("dcp_enabled", True)


def _set_profile_dcp_enabled(config: Dict[str, Any], name: str, enabled: bool) -> None:
    """设置配置文件的 DCP 绑定状态并保存"""
    if name in config.get("profiles", {}):
        config["profiles"][name]["dcp_enabled"] = enabled
        save_config(config)


def _apply_profile_dcp(config: Dict[str, Any], name: str) -> None:
    """切换配置时应用 DCP 状态"""
    profile_meta = config.get("profiles", {}).get(name, {})
    dcp_enabled = _get_profile_dcp_enabled(profile_meta)
    update_dcp_state(dcp_enabled)


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

    with open(OMA_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(current, f, indent=2, ensure_ascii=False)


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

    with open(OMA_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(current, f, indent=2, ensure_ascii=False)


def load_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {"current": None, "profiles": {}}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            config.setdefault("current_fallback", "")
            return config
    except json.JSONDecodeError:
        print_error("配置文件损坏，将重新创建")
        return {"current": None, "profiles": {}}


def save_config(config: Dict[str, Any]) -> None:
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_current_fallback(config: Dict[str, Any]) -> str:
    """获取当前回退链名称"""
    return config.get("current_fallback", "")


def set_current_fallback(config: Dict[str, Any], name: str) -> None:
    """设置当前回退链名称并保存"""
    config["current_fallback"] = name
    save_config(config)


def clear_current_fallback_if_deleted(config: Dict[str, Any], deleted_name: str) -> bool:
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
    """Load a profile by name, return None if missing/invalid."""
    path = get_profile_path(name)
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def get_fallback_path(name: str) -> Path:
    return FALLBACKS_DIR / f"{name}.json"


def load_fallback_json(name: str) -> Optional[Dict[str, Any]]:
    path = get_fallback_path(name)
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def save_fallback_json(name: str, data: Dict[str, Any]) -> None:
    FALLBACKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(get_fallback_path(name), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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


# ── 模型分析相关函数 ──────────────────────────────────────────────

def parse_model_with_variant(model_str: str) -> Tuple[str, Optional[str]]:
    """解析 'model[variant]' 格式，返回 (model, variant)。
    
    例如:
      "deepseek-v4-pro[max]" → ("deepseek-v4-pro", "max")
      "gemini-3-pro"          → ("gemini-3-pro", None)
    """
    stripped = model_str.strip()
    match = re.match(r'^(.+?)\s*\[(\w+)\]\s*$', stripped)
    if match:
        return match.group(1).strip(), match.group(2).lower()
    return stripped, None

# ── 模板定义 ─────────────────────────────────────────────────────
# 默认模板（内置）
DEFAULT_TEMPLATE_GROUPS: Dict[str, set] = {
    "主模型": {
        ("agents", "sisyphus"),
        ("agents", "hephaestus"),
        ("agents", "prometheus"),
        ("agents", "atlas"),
    },
    "强模型": {
        ("agents", "oracle"),
        ("agents", "metis"),
        ("agents", "momus"),
        ("agents", "plan"),
        ("categories", "ultrabrain"),
        ("categories", "artistry"),
    },
    "中模型": {
        ("agents", "sisyphus-junior"),
        ("categories", "deep"),
        ("categories", "visual-engineering"),
        ("categories", "writing"),
        ("categories", "unspecified-high"),
    },
    "弱模型": {
        ("agents", "explore"),
        ("agents", "librarian"),
        ("categories", "quick"),
        ("categories", "unspecified-low"),
    },
    "多模态模型": {
        ("agents", "multimodal-looker"),
    },
}


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
    return copy.deepcopy(DEFAULT_TEMPLATE_GROUPS)


def save_template(template: Dict[str, set]) -> None:
    """保存用户自定义模板到文件"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(_template_to_json(template), f, indent=2, ensure_ascii=False)


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


def collect_all_models() -> List[str]:
    """从所有 profile 和当前 OMA 配置中提取所有不重复的模型名"""
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
            except (json.JSONDecodeError, IOError):
                pass

    if OMA_CONFIG.exists():
        try:
            with open(OMA_CONFIG, 'r', encoding='utf-8') as f:
                profile = json.load(f)
            for section in ("agents", "categories"):
                for value in profile.get(section, {}).values():
                    if isinstance(value, dict) and "model" in value:
                        models.add(value["model"])
        except (json.JSONDecodeError, IOError):
            pass

    return sorted(models)


def prompt_select_model(
    type_label: str,
    all_models: List[str],
    current = None
) -> Tuple[str, Optional[str]]:
    """交互式提示用户选择一个模型，返回 (model, variant)。
    
    current 可以是 (model, variant) 元组或纯字符串（向后兼容）。
    用户可以通过编号选择现有模型，也可以输入 model[variant] 格式。
    """
    # 兼容旧格式（纯字符串，无 variant）
    if isinstance(current, tuple):
        current_model, current_variant = current
    else:
        current_model, current_variant = current, None

    print(f"  {Colors.BOLD}{type_label}{Colors.NC}")
    if current_model:
        if current_variant:
            print(f"    当前: {Colors.CYAN}{current_model} [variant={current_variant}]{Colors.NC}")
        else:
            print(f"    当前: {Colors.CYAN}{current_model}{Colors.NC}")
    print(f"    可用模型:")
    for i, m in enumerate(all_models, 1):
        marker = " (当前)" if m == current_model else ""
        print(f"      [{i}] {m}{marker}")

    prompt_text = f"  请输入{type_label}（编号/模型名[variant]"
    if current_model:
        prompt_text += "/留空=当前值"
    prompt_text += "）: "
    choice = input(prompt_text).strip()

    if not choice:
        if current_model:
            return current_model, current_variant
        elif all_models:
            print_warning(f"未选择{type_label}，使用第一个可用模型")
            return all_models[0], None
        else:
            return "", None

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(all_models):
            return all_models[idx], None
        print_warning("无效编号，使用当前值")
        return current_model or choice, current_variant

    # 解析模型名中可能的 [variant] 后缀
    return parse_model_with_variant(choice)


MAX_FALLBACK_MODELS = 5


def prompt_select_fallback_models(
    type_label: str,
    all_models: List[str],
    current: Optional[List] = None,
) -> List:
    """交互式提示用户选择 fallback 模型链，返回选中的模型列表。

    current 可以是字符串列表或包含 variant 的字典列表（向后兼容）。
    用户可以通过逗号分隔的编号或模型名选择多个模型，支持 model[variant] 格式。
    空输入会清空链（返回 []）。最多选择 MAX_FALLBACK_MODELS 个模型。
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

    print(f"    可用模型（最多选 {MAX_FALLBACK_MODELS} 个）:")
    for i, m in enumerate(all_models, 1):
        print(f"      [{i}] {m}")

    prompt_text = (
        f"  请输入{type_label} fallback 模型"
        f"（逗号分隔的编号/模型名[variant]，留空=清空）: "
    )
    choice = input(prompt_text).strip()

    if not choice:
        return []

    parts = [p.strip() for p in choice.split(",") if p.strip()]
    selected: List = []

    for part in parts:
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(all_models):
                selected.append(all_models[idx])
            else:
                print_warning(f"无效编号: {part}，已跳过")
        else:
            model, variant = parse_model_with_variant(part)
            if variant:
                selected.append({"model": model, "variant": variant})
            else:
                selected.append(model)

    if len(selected) > MAX_FALLBACK_MODELS:
        print_warning(
            f"最多只能选择 {MAX_FALLBACK_MODELS} 个 fallback 模型，"
            f"已截取前 {MAX_FALLBACK_MODELS} 个"
        )
        selected = selected[:MAX_FALLBACK_MODELS]

    return selected


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

    with open(profile_path, 'w', encoding='utf-8') as f:
        json.dump(new_profile, f, indent=2, ensure_ascii=False)

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
    with open(profile_path, 'w', encoding='utf-8') as f:
        json.dump(new_profile, f, indent=2, ensure_ascii=False)

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


def cmd_dcp_config(args: List[str]) -> None:
    """配置 DCP 插件（已废弃，请使用 'oma-switch dcp bind'）"""
    print_warning("'dcp-config' 命令已废弃，请使用 'oma-switch dcp bind'")
    print_info("示例:")
    print_info("  oma-switch dcp bind <name> on     # 启用配置的 DCP")
    print_info("  oma-switch dcp bind <name> off    # 禁用配置的 DCP")
    print_info("  oma-switch dcp bind               # 查看当前配置的 DCP 绑定")
    print_info("  oma-switch dcp on                 # 启用 DCP（同步到当前配置）")


# ── 完整 DCP 管理命令 ─────────────────────────────────────────────


def _dcp_show() -> None:
    """显示 DCP 完整配置（格式化）"""
    config = get_dcp_config()

    print_info("当前 DCP (Dynamic Context Pruning) 配置:")
    print()

    enabled_str = (
        f"{Colors.GREEN}✓ 已启用{Colors.NC}"
        if config.get("enabled", False)
        else f"{Colors.RED}✗ 已禁用{Colors.NC}"
    )
    print(f"  状态:          {enabled_str}")
    print(f"  Debug:         {config.get('debug', False)}")
    print(f"  修剪通知:      {config.get('pruneNotification', 'detailed')}")
    print(f"  通知类型:      {config.get('pruneNotificationType', 'toast')}")
    print()

    compress = config.get("compress", {})
    print_color(Colors.BOLD, "  压缩设置:")
    print(f"    最大上下文:   {compress.get('maxContextLimit', '30%')}")
    print(f"    最小上下文:   {compress.get('minContextLimit', '15%')}")
    print()

    tp = config.get("turnProtection", {})
    print_color(Colors.BOLD, "  轮次保护:")
    tp_en = (
        f"{Colors.GREEN}✓ 开启{Colors.NC}"
        if tp.get("enabled", False)
        else f"{Colors.RED}✗ 关闭{Colors.NC}"
    )
    print(f"    状态:         {tp_en}")
    print(f"    轮次:         {tp.get('turns', 4)}")
    print()

    strategies = config.get("strategies", {})
    print_color(Colors.BOLD, "  策略:")

    dedup = strategies.get("deduplication", {})
    dedup_en = (
        f"{Colors.GREEN}✓ 开启{Colors.NC}"
        if dedup.get("enabled", True)
        else f"{Colors.RED}✗ 关闭{Colors.NC}"
    )
    print(f"    去重:         {dedup_en}")

    purge = strategies.get("purgeErrors", {})
    purge_en = (
        f"{Colors.GREEN}✓ 开启{Colors.NC}"
        if purge.get("enabled", True)
        else f"{Colors.RED}✗ 关闭{Colors.NC}"
    )
    print(f"    错误清理:     {purge_en}  (轮次: {purge.get('turns', 4)})")
    print()

    oma_config = load_config()
    current_profile = oma_config.get("current")
    if current_profile:
        profile_meta = oma_config.get("profiles", {}).get(current_profile, {})
        dcp_enabled = _get_profile_dcp_enabled(profile_meta)
        bind_str = (
            f"{Colors.GREEN}✓ 绑定启用{Colors.NC}"
            if dcp_enabled
            else f"{Colors.RED}✗ 绑定禁用{Colors.NC}"
        )
        print(f"  配置绑定:      {bind_str}  ({current_profile})")
    print()

    print_dim(f"DCP 配置文件: {DCP_CONFIG_FILE}")
    print_dim(f"提示: 使用 'oma-switch dcp edit' 交互式修改，或 'oma-switch dcp set <key> <value>' 快速修改")


def _dcp_edit() -> None:
    """交互式编辑 DCP 完整配置"""
    config = get_dcp_config()

    print_info("DCP 配置编辑 (留空保持当前值)")
    print()

    current = config.get("enabled", False)
    choice = input(f"  启用 DCP [true/false] (当前: {current}): ").strip().lower()
    if choice in ("true", "false"):
        config["enabled"] = choice == "true"

    current = config.get("debug", False)
    choice = input(f"  Debug 模式 [true/false] (当前: {current}): ").strip().lower()
    if choice in ("true", "false"):
        config["debug"] = choice == "true"

    current = config.get("pruneNotification", "detailed")
    choice = input(f"  修剪通知方式 [detailed/minimal/none] (当前: {current}): ").strip().lower()
    if choice in ("detailed", "minimal", "none"):
        config["pruneNotification"] = choice

    current = config.get("pruneNotificationType", "toast")
    choice = input(f"  通知类型 [toast/status/none] (当前: {current}): ").strip().lower()
    if choice in ("toast", "status", "none"):
        config["pruneNotificationType"] = choice

    compress = config.setdefault("compress", {})
    current = compress.get("maxContextLimit", "30%")
    choice = input(f"  最大上下文限制 (当前: {current}): ").strip()
    if choice:
        compress["maxContextLimit"] = choice

    current = compress.get("minContextLimit", "15%")
    choice = input(f"  最小上下文限制 (当前: {current}): ").strip()
    if choice:
        compress["minContextLimit"] = choice

    tp = config.setdefault("turnProtection", {})
    current = tp.get("enabled", False)
    choice = input(f"  轮次保护 [true/false] (当前: {current}): ").strip().lower()
    if choice in ("true", "false"):
        tp["enabled"] = choice == "true"

    current = tp.get("turns", 4)
    choice = input(f"  轮次保护轮次数 (当前: {current}): ").strip()
    if choice:
        try:
            tp["turns"] = int(choice)
        except ValueError:
            print_warning(f"无效数字: {choice}，保持原值 {current}")

    strategies = config.setdefault("strategies", {})
    dedup = strategies.setdefault("deduplication", {})
    current = dedup.get("enabled", True)
    choice = input(f"  去重策略 [true/false] (当前: {current}): ").strip().lower()
    if choice in ("true", "false"):
        dedup["enabled"] = choice == "true"

    purge = strategies.setdefault("purgeErrors", {})
    current = purge.get("enabled", True)
    choice = input(f"  错误清理策略 [true/false] (当前: {current}): ").strip().lower()
    if choice in ("true", "false"):
        purge["enabled"] = choice == "true"

    current = purge.get("turns", 4)
    choice = input(f"  错误清理轮次 (当前: {current}): ").strip()
    if choice:
        try:
            purge["turns"] = int(choice)
        except ValueError:
            print_warning(f"无效数字: {choice}，保持原值 {current}")

    save_dcp_config(config)
    print()
    print_success("DCP 配置已更新")
    print_info("使用 'oma-switch dcp' 查看更新后的配置")


def _dcp_set(args: List[str]) -> None:
    """快速设置 DCP 参数: oma-switch dcp set <key> <value>"""
    if len(args) < 2:
        print_error("用法: oma-switch dcp set <key> <value>")
        print_info("示例:")
        print_info("  oma-switch dcp set enabled true")
        print_info("  oma-switch dcp set compress.maxContextLimit 40%")
        print_info("  oma-switch dcp set turnProtection.enabled true")
        print_info("  oma-switch dcp set strategies.purgeErrors.turns 8")
        return

    key_path = args[0]
    value_raw = " ".join(args[1:])
    config = get_dcp_config()

    keys = key_path.split(".")
    parent = config
    for k in keys[:-1]:
        if k not in parent or not isinstance(parent[k], dict):
            parent[k] = {}
        parent = parent[k]

    last_key = keys[-1]

    if value_raw.lower() in ("true", "false"):
        parsed_value = value_raw.lower() == "true"
    else:
        try:
            if "." in value_raw:
                parsed_value = float(value_raw)
            else:
                parsed_value = int(value_raw)
        except ValueError:
            parsed_value = value_raw

    parent[last_key] = parsed_value
    save_dcp_config(config)
    print_success(
        f"已设置 DCP 参数: {key_path} = {json.dumps(parsed_value, ensure_ascii=False)}"
    )


def _dcp_bind_show(name: Optional[str] = None) -> None:
    """显示一个配置文件的 DCP 绑定状态"""
    oma_config = load_config()
    if not name:
        name = oma_config.get("current")
        if not name:
            print_error("当前没有激活的配置文件")
            return

    if name not in oma_config.get("profiles", {}):
        print_error(f"配置文件 '{name}' 不存在")
        return

    profile_meta = oma_config["profiles"][name]
    dcp_enabled = _get_profile_dcp_enabled(profile_meta)
    bind_str = (
        f"{Colors.GREEN}✓ 启用{Colors.NC}"
        if dcp_enabled
        else f"{Colors.RED}✗ 禁用{Colors.NC}"
    )
    print_info(f"配置文件 '{name}' 的 DCP 绑定: {bind_str}")


def _dcp_bind_set(name: str, enabled: bool) -> None:
    """设置一个配置文件的 DCP 绑定状态"""
    oma_config = load_config()
    if name not in oma_config.get("profiles", {}):
        print_error(f"配置文件 '{name}' 不存在")
        return

    _set_profile_dcp_enabled(oma_config, name, enabled)
    state = "启用" if enabled else "禁用"
    print_success(f"配置文件 '{name}' 的 DCP 已{state}")

    # 如果是当前配置，立即应用
    if oma_config.get("current") == name:
        update_dcp_state(enabled)


def cmd_dcp(args: List[str]) -> None:
    """DCP (Dynamic Context Pruning) 插件全面管理命令"""
    if not args:
        _dcp_show()
        return

    if args[0] in ("help", "--help", "-h"):
        print_info("DCP (Dynamic Context Pruning) 插件管理")
        print()
        print_color(Colors.BOLD, "说明:")
        print("  每个配置文件独立绑定 DCP 开关，切换配置时自动应用。")
        print("  新建的配置文件默认启用 DCP。")
        print()
        print_color(Colors.BOLD, "用法:")
        print("  oma-switch dcp [help]                 查看此帮助信息")
        print("  oma-switch dcp show                   显示完整 DCP 配置")
        print("  oma-switch dcp on|enable              立即启用 DCP（更新当前配置绑定）")
        print("  oma-switch dcp off|disable            立即禁用 DCP（更新当前配置绑定）")
        print("  oma-switch dcp bind [name]            查看配置的 DCP 绑定")
        print("  oma-switch dcp bind <name> on|off     设置配置的 DCP 绑定")
        print("  oma-switch dcp edit                   交互式编辑 DCP 插件参数")
        print("  oma-switch dcp set <key> <value>      快速设置 DCP 插件参数")
        print()
        print_color(Colors.BOLD, "dcp set 支持的键路径:")
        print("  enabled                         启用/禁用")
        print("  debug                           Debug 模式")
        print("  pruneNotification               修剪通知方式 (detailed/minimal/none)")
        print("  pruneNotificationType           通知类型 (toast/status/none)")
        print("  compress.maxContextLimit         最大上下文限制 (如 30%)")
        print("  compress.minContextLimit         最小上下文限制 (如 15%)")
        print("  turnProtection.enabled           轮次保护开关")
        print("  turnProtection.turns             轮次保护轮次")
        print("  strategies.deduplication.enabled  去重策略开关")
        print("  strategies.purgeErrors.enabled    错误清理策略开关")
        print("  strategies.purgeErrors.turns      错误清理轮次")
        print()
        print_dim("示例:")
        print_dim("  oma-switch dcp                              # 查看摘要")
        print_dim("  oma-switch dcp show                         # 完整配置")
        print_dim("  oma-switch dcp on                           # 启用（同步到当前配置）")
        print_dim("  oma-switch dcp bind main                    # 查看 main 的 DCP 绑定")
        print_dim("  oma-switch dcp bind main off                # 关闭 main 的 DCP")
        print_dim("  oma-switch dcp edit                         # 交互式修改")
        return

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand == "show":
        _dcp_show()
    elif subcommand in ("on", "enable"):
        update_dcp_state(True)
        oma_config = load_config()
        current = oma_config.get("current")
        if current:
            _set_profile_dcp_enabled(oma_config, current, True)
            print_dim(f"已同步到当前配置文件 '{current}' 的 DCP 绑定")
    elif subcommand in ("off", "disable"):
        update_dcp_state(False)
        oma_config = load_config()
        current = oma_config.get("current")
        if current:
            _set_profile_dcp_enabled(oma_config, current, False)
            print_dim(f"已同步到当前配置文件 '{current}' 的 DCP 绑定")
    elif subcommand == "bind":
        if not sub_args:
            _dcp_bind_show()
        elif len(sub_args) == 1:
            _dcp_bind_show(sub_args[0])
        elif len(sub_args) == 2:
            val = sub_args[1].lower()
            if val in ("on", "enable", "true", "1"):
                _dcp_bind_set(sub_args[0], True)
            elif val in ("off", "disable", "false", "0"):
                _dcp_bind_set(sub_args[0], False)
            else:
                print_error("用法: oma-switch dcp bind <name> on|off")
        else:
            print_error("用法: oma-switch dcp bind [name] [on|off]")
    elif subcommand == "edit":
        _dcp_edit()
    elif subcommand == "set":
        _dcp_set(sub_args)
    else:
        print_error(f"未知子命令: {subcommand}")
        print_info("使用 'oma-switch dcp help' 查看帮助")


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
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
            updated += 1

    return updated


def cmd_template(args: List[str]) -> None:
    """查看或编辑模板"""
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
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

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
