#!/usr/bin/env python3
"""OMA 配置文件切换工具 - 管理 opencode 的 oh-my-openagent.json 配置"""
from .constants import *  # noqa: F403
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
from .commands import *  # noqa: F403,F401
from .fallback_cmds import *  # noqa: F403


def cmd_help() -> None:
    """显示帮助信息"""
    print("""
OMA 配置文件切换工具 (v2.0)

用法: oma-switch <command> [args...] [--detail]

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
    create [--detail] <name>  创建新配置
    view [--detail] [name]    查看配置文件
    diff [--detail] <name1> [name2]  比较配置文件

快速模式的模型分类:
  主模型            → sisyphus, hephaestus, prometheus, atlas
  强模型（Pro）      → oracle, metis, momus, plan, ultrabrain, artistry
  中模型（Standard） → sisyphus-junior, deep, visual-engineering, writing, unspecified-high
  弱模型（Flash）    → explore, librarian, quick, unspecified-low
  多模态模型         → multimodal-looker

配置文件存储位置: ~/.config/oma-switch/profiles/

DCP 插件管理:
  dcp                                   查看 DCP 配置摘要
  dcp show                              显示完整 DCP 配置
  dcp on|off                            启用/禁用 DCP
  dcp bind [name]                       查看配置的 DCP 绑定
  dcp bind <name> on|off                设置配置的 DCP 绑定
  dcp edit                              交互式编辑 DCP 插件参数
  dcp set <key> <value>                 快速设置 DCP 插件参数

Fallback 链管理:
  fallback create <name>        创建新的 fallback 链
  fallback list                 列出所有 fallback 链
  fallback switch <name>        切换到指定 fallback 链
  fallback view [name]          查看 fallback 链详情
  fallback edit <name>          编辑 fallback 链
  fallback diff <name1> [name2] 比较 fallback 链
  fallback rm <name>            删除 fallback 链
""")


def main() -> None:
    """主函数"""
    ensure_dirs()
    check_current_unrecorded()
    if len(sys.argv) < 2:
        cmd_help()
        sys.exit(0)
    command, args = sys.argv[1], sys.argv[2:]
    commands = {
        "add": cmd_add, "rm": cmd_rm, "edit": cmd_edit, "create": cmd_create,
        "view": cmd_view, "rename": cmd_rename, "list": cmd_list,
        "switch": cmd_switch, "diff": cmd_diff, "backup": cmd_backup,
        "template": cmd_template, "dcp-config": cmd_dcp_config, "dcp": cmd_dcp,
        "fallback": cmd_fallback, "restore": cmd_restore, "help": cmd_help,
    }
    if command in commands:
        commands[command]() if command == "help" else commands[command](args)
    else:
        print_error(f"未知命令: {command}")
        cmd_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
