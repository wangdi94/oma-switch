#!/usr/bin/env python3
"""
DCP (Dynamic Context Pruning) 插件管理模块。

管理 DCP 插件配置和配置文件绑定状态。
"""

import json
import re
from typing import Any, Dict, List, Optional

from .types import OmaSwitchConfig, ProfileMeta

from .constants import DCP_CONFIG_FILE, OPENCODE_DIR
from .config_io import load_config, save_config
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

__all__ = [
    "get_dcp_config",
    "save_dcp_config",
    "update_dcp_state",
    "_get_profile_dcp_enabled",
    "_set_profile_dcp_enabled",
    "_apply_profile_dcp",
    "cmd_dcp_config",
    "_dcp_show",
    "_dcp_edit",
    "_dcp_set",
    "_dcp_bind_show",
    "_dcp_bind_set",
    "cmd_dcp",
]


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
    _atomic_write_json(DCP_CONFIG_FILE, config)


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


def _get_profile_dcp_enabled(profile_meta: ProfileMeta) -> bool:
    """获取配置文件的 DCP 绑定状态，默认启用"""
    return profile_meta.get("dcp_enabled", True)  # type: ignore[return-value]


def _set_profile_dcp_enabled(config: OmaSwitchConfig, name: str, enabled: bool) -> None:
    """设置配置文件的 DCP 绑定状态并保存"""
    if name in config.get("profiles", {}):
        config["profiles"][name]["dcp_enabled"] = enabled
        save_config(config)


def _apply_profile_dcp(config: OmaSwitchConfig, name: str) -> None:
    """切换配置时应用 DCP 状态"""
    profile_meta = config.get("profiles", {}).get(name, {})
    dcp_enabled = _get_profile_dcp_enabled(profile_meta)
    update_dcp_state(dcp_enabled)


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
