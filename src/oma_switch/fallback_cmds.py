"""
Fallback 链管理命令
从 cli.py 提取的 fallback 相关命令函数
"""

import sys
from typing import Dict, List, Any, cast

from .display import print_error, print_info, print_warning, print_success, print_color, Colors
from .config_io import (
    load_fallback_json, save_fallback_json, delete_fallback_json,
    list_fallback_names, load_config, get_current_fallback,
    set_current_fallback, clear_current_fallback_if_deleted
)
from .template import (
    load_template, validate_fallback_config,
    get_fallback_summary, print_fallback_summary
)
from .models import collect_all_models
from .prompt import prompt_select_fallback_models, generate_fallback_from_types
from .cli_helpers import merge_fallback_to_oma_config


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
    existing_dict = cast(Dict[str, Any], existing)
    for type_label in tpl:
        current_chain = existing_dict.get(type_label, {}).get("fallback_models", [])
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
        merge_fallback_to_oma_config(cast(Dict[str, Any], new_config))
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

    merge_fallback_to_oma_config(cast(Dict[str, Any], fallback_data))

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
    print(" oma-switch fallback list                   列出所有 fallback 链")
    print("  oma-switch fallback switch <name>          切换到指定 fallback 链")
    print("  oma-switch fallback view [name]            查看 fallback 链详情")
    print("  oma-switch fallback edit <name>            编辑 fallback 链")
    print("  oma-switch fallback diff <name1> [name2]   比较 fallback 链")
    print("  oma-switch fallback rm <name>              删除 fallback 链")
