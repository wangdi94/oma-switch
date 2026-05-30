# oma-switch

**Generated:** 2026-05-30
**Commit:** 23a8420
**Branch:** dev

## OVERVIEW

Python CLI 工具，管理 opencode 的 `oh-my-openagent.json` 配置。按模板中的模型分类（主/强/中/弱/多模态）快速查看、创建、编辑、切换、比较配置。每个配置独立绑定 DCP 开关。支持 fallback 链管理（每分类独立配置 fallback 模型链）。

栈：Python ≥3.10 + 标准库 + thefuzz[speedup]（模糊搜索，可选，有 difflib fallback）+ pytest（开发依赖）。

## STRUCTURE

```
oma-switch/
├── pyproject.toml         # [build-system] + [tool.pytest] + [tool.ruff] + [tool.mypy] + [tool.coverage]
├── setup.py               # 元数据+入口点（从 __init__.py 动态读取版本）
├── .pre-commit-config.yaml # ruff + mypy + pytest hooks
├── .github/workflows/test.yml  # CI: Python 3.10-3.12 matrix
├── src/oma_switch/
│   ├── __init__.py        # v2.1.0
│   ├── __main__.py        # python -m 入口 → cli.main
│   ├── cli.py             # 108行：re-export 薄层 + main() + cmd_help()
│   ├── constants.py       # 27行：路径常量 + HAS_THEFUZZ
│   ├── display.py         # 48行：Colors + print_* 函数
│   ├── io_utils.py        # 34行：_atomic_write_json
│   ├── version.py         # 459行：版本管理 + 恢复命令
│   ├── config_io.py       # 136行：配置加载/保存 + profiles/fallbacks I/O
│   ├── history.py         # 88行：模型使用频率记录
│   ├── template.py        # 522行：模板管理 + 验证 + 显示
│   ├── dcp.py             # 448行：DCP 管理 + 命令
│   ├── models.py          # 201行：模型收集/搜索/分析
│   ├── prompt.py          # 313行：交互式模型选择 + Fallback 生成
│   ├── cli_helpers.py     # 166行：工具函数 + 配置合并
│   ├── commands.py        # 665行：profile 管理命令（cmd_*）
│   ├── fallback_cmds.py   # 384行：Fallback 命令 + 调度器
│   └── types.py           # 132行：TypedDict 类型定义
├── tests/                 # 223 个测试（15 个文件）
│   ├── conftest.py        # 隔离 fixtures（isolated_config_dir 等）
│   ├── test_core.py       # 核心功能基线测试
│   ├── test_cmd_fallback.py  # fallback 命令测试（最大）
│   ├── test_fallback_*.py    # fallback 子功能测试
│   ├── test_integration.py   # 端到端集成测试
│   ├── test_atomic_write.py  # 原子写入测试（18 个）
│   ├── test_version_management.py  # 版本管理测试（37 个）
│   └── test_restore.py     # 恢复命令测试（20 个）
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| CLI 入口 + 命令分派 | `cli.py` | `main()` + 命令字典，re-export 所有公开符号 |
| Profile 管理命令 | `commands.py` | `cmd_add/rm/edit/create/view/rename/list/switch/diff/backup` |
| Fallback 命令 | `fallback_cmds.py` | `cmd_fallback_*` + 调度器 + 帮助 |
| 配置文件 I/O | `config_io.py` | `load_config/save_config/load_profile_json/load_fallback_json` |
| 模板管理 | `template.py` | `DEFAULT_TEMPLATE_GROUPS` + load/save/check/validate |
| DCP 管理 | `dcp.py` | `get_dcp_config/save_dcp_config/update_dcp_state/cmd_dcp` |
| 版本管理 | `version.py` | `_create_version_snapshot/_rotate_versions/_list_versions/cmd_restore` |
| 原子写入 | `io_utils.py` | `_atomic_write_json`: write-to-temp + fsync + rename |
| 模型分析 | `models.py` | `collect_all_models/collect_models_enriched/fuzzy_match_models` |
| 交互式提示 | `prompt.py` | `prompt_select_model/prompt_select_fallback_models/generate_*` |
| 类型定义 | `types.py` | `OmaSwitchConfig/VersionMetadata/FallbackData/DcpConfig` TypedDict |
| 工具函数 | `cli_helpers.py` | `open_editor/parse_flag/get_profile_or_current/merge_*_to_oma_config` |
| 常量 | `constants.py` | 路径常量 + `HAS_THEFUZZ` 标志 |
| 显示 | `display.py` | `Colors` 类 + `print_*` 函数 |
| 历史 | `history.py` | `load_history/save_history/record_model_usage/get_*_frequency` |
| 测试 | `tests/` | pytest，223 个测试，`isolated_config_dir` fixture |

## KEY FUNCTIONS

| Symbol | Location | Role |
|--------|----------|------|
| `main()` | cli.py | CLI 入口，sys.argv 解析 + 命令分派 |
| `cmd_switch(name)` | commands.py | 切换配置 + DCP + 重注入 fallback |
| `cmd_create/edit/list/view/diff/...` | commands.py | 配置管理命令 |
| `cmd_restore(args)` | version.py | 恢复历史版本（0/1/2 参数模式） |
| `cmd_fallback(args)` | fallback_cmds.py | fallback 子命令分派器 |
| `_atomic_write_json(filepath, data)` | io_utils.py | 原子性 JSON 写入（temp+fsync+rename） |
| `_create_version_snapshot(filepath, operation)` | version.py | 写入前创建版本快照 |
| `merge_to_oma_config(source)` | cli_helpers.py | 浅替换 agents+categories |
| `merge_fallback_to_oma_config(data)` | cli_helpers.py | 字段级深合并：仅注入 fallback_models |
| `validate_fallback_config(data)` | template.py | 验证 fallback 配置格式 |
| `update_dcp_state(enable)` | dcp.py | 用正则修改 dcp.jsonc 的 enabled 字段 |
| `check_template_profile(profile)` | template.py | 验证配置是否符合模板约束 |
| `collect_models_enriched(category)` | models.py | 收集所有模型含 variant+频率，按频率排序 |
| `fuzzy_match_models(query, candidates)` | models.py | 模糊搜索（thefuzz/difflib） |
| `prompt_select_fallback_models(...)` | prompt.py | 交互式选择 fallback 模型链 |
| `generate_fallback_from_types(...)` | prompt.py | 从用户选择生成 fallback 配置 |
| `_load_json_with_recovery(filepath, display_name)` | config_io.py | 统一的 JSON 加载+损坏恢复逻辑 |

## CONVENTIONS（与标准 Python 的偏差）

- **近零依赖**：主要用标准库，thefuzz[speedup] 用于模糊搜索（可选，有 difflib fallback）
- **模块化拆分**：3745 行 → 17 个模块（27-665 行/个）
- **手动 CLI**：不用 argparse/click，`sys.argv` + 字典分派
- **src 布局**：包在 `src/oma_switch/`，`setup.py` 用 `find_packages(where="src")`
- **配置存储**：JSON 文件在 `~/.config/oma-switch/`（profiles/, fallbacks/, config.json, template.json, history.json）
- **版本存储**：`~/.config/oma-switch/.versions/<filename>/`（每个文件独立版本目录）
- **目标文件**：`~/.config/opencode/oh-my-openagent.json`
- **中文化 UI**：终端输出、提示、错误信息均为中文
- **函数命名**：公开命令 `cmd_*`，内部辅助 `_*`
- **类型注解**：使用 TypedDict（types.py）+ `Dict[str, Any]` 混合
- **版本号**：单一来源 `__init__.py`，`setup.py` 动态读取
- **测试**：pytest + `isolated_config_dir` fixture（monkeypatch Path.home() + 所有模块常量）
- **工具链**：ruff（lint+format）+ mypy（type check）+ pre-commit + pytest-cov + GitHub Actions CI

## ANTI-PATTERNS（已修复）

1. ~~**`Dict[str, Any]` 逃逸类型检查**~~ → 已添加 4 个 TypedDict（types.py）
2. ~~**无 CI**~~ → 已添加 `.github/workflows/test.yml`（Python 3.10-3.12 matrix）
3. ~~**`dcp-config` 已废弃但保留**~~ → 已删除 `cmd_dcp_config`
4. ~~**脆弱的 JSONC 解析**~~ → 已修复正则（跳过引号内的 `//`）
5. ~~**版本号双重硬编码**~~ → `setup.py` 从 `__init__.py` 动态读取

## COMMANDS

```bash
pip install .              # 安装
pip install -e .           # 可编辑安装（开发）
python -m oma_switch       # python -m 方式运行
oma-switch list            # CLI 方式运行
oma-switch restore         # 查看可恢复的历史版本
pytest tests/ -v           # 运行测试（223 个）
ruff check src/oma_switch/ # lint 检查
pre-commit run --all-files # 运行所有 hooks
```

## NOTES

- Fallback 和 Profile 完全独立：切换 profile 保留 fallback，切换 fallback 不动 model
- 测试中 `isolated_config_dir` fixture 需要 monkeypatch 所有模块的路径常量（constants, cli, config_io, version 等）
- `history.json` 记录模型使用频率，位于 `~/.config/oma-switch/history.json`，用于智能排序
- thefuzz 降级：`HAS_THEFUZZ` 标志（constants.py），不可用时自动回退到 difflib
- 版本管理：每次写入前自动快照，保留最近 10 个版本，支持元数据（时间戳/哈希/操作名）
- 损坏恢复：`_load_json_with_recovery()` 统一处理，损坏时保留 `.corrupted.<ts>` 文件
- 原子写入：所有 JSON 写操作使用 write-to-temp + fsync + rename
- `DEFAULT_TEMPLATE_GROUPS` 使用 `MappingProxyType` 保护，防止意外修改
- `filter_models_by_category()` 已弃用（无调用者），使用 `collect_models_enriched(category)` 代替
