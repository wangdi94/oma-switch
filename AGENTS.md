# oma-switch

**Generated:** 2026-05-29
**Commit:** fac4cf4
**Branch:** master

## OVERVIEW

Python CLI 工具，管理 opencode 的 `oh-my-openagent.json` 配置。按模板中的模型分类（主/强/中/弱/多模态）快速查看、创建、编辑、切换、比较配置。每个配置独立绑定 DCP 开关。支持 fallback 链管理（每分类独立配置 fallback 模型链）。

栈：Python ≥3.10 + 标准库 + thefuzz[speedup]（模糊搜索，可选，有 difflib fallback）+ pytest（开发依赖）。

## STRUCTURE

```
oma-switch/
├── pyproject.toml         # [build-system] + [tool.pytest.ini_options]
├── setup.py               # 所有元数据+入口点（传统模式）
├── install.sh             # pip install 包装
├── src/oma_switch/
│   ├── __init__.py        # v2.1.0
│   ├── __main__.py        # python -m 入口 → cli.main
│   └── cli.py             # 2442行单体：全部逻辑
├── tests/                 # 98 个测试（12 个文件）
│   ├── conftest.py        # 隔离 fixtures（isolated_config_dir 等）
│   ├── test_core.py       # 核心功能基线测试
│   ├── test_cmd_fallback.py  # fallback 命令测试（最大）
│   ├── test_fallback_*.py    # fallback 子功能测试
│   └── test_integration.py   # 端到端集成测试
├── .omo/                  # 工作会话记录
└── .sisyphus/             # agent 上下文
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| 配置管理 | `cli.py` | 20+ 个 `cmd_*` 函数，字典调度（无 argparse） |
| 模板 | `cli.py` L282-453 | `DEFAULT_TEMPLATE_GROUPS` + load/save/check |
| DCP 管理 | `cli.py` L75-153 | get/save/update/bind/show/edit/set |
| Fallback 管理 | `cli.py` L181-845, L1198-1582 | merge/generate/display/prompt + 7 个 cmd |
| 配置文件 I/O | `cli.py` L69-320 | JSON 读写、目录保证、profile/fallback 加载 |
| 模型选择 | `cli.py` L647-798 | 交互式 prompt + 解析 `model[variant]` |
| 入口 | `__init__.py` `__main__.py` `setup.py` | 全部汇聚到 `cli.main()` |
| 测试 | `tests/` | pytest，98 个测试，隔离 fixtures |

## KEY FUNCTIONS

| Symbol | Location | Role |
|--------|----------|------|
| `main()` | cli.py:2400 | CLI 入口，sys.argv 解析 + 命令分派 |
| `cmd_switch(name)` | cli.py:1585 | 切换配置 + DCP + 重注入 fallback |
| `cmd_create/edit/list/view/diff/...` | cli.py:955-1629 | 配置管理命令 |
| `cmd_fallback(args)` | cli.py:2350 | fallback 子命令分派器 |
| `cmd_fallback_create/list/switch/view/edit/diff/rm` | cli.py:1198-1582 | 7 个 fallback 命令 |
| `merge_to_oma_config(source)` | cli.py:156 | 浅替换 agents+categories |
| `merge_fallback_to_oma_config(data)` | cli.py:181 | 字段级深合并：仅注入 fallback_models |
| `validate_fallback_config(data)` | cli.py:481 | 验证 fallback 配置格式 |
| `update_dcp_state(enable)` | cli.py:96 | 用正则修改 dcp.jsonc 的 enabled 字段 |
| `check_template_profile(profile)` | cli.py:453 | 验证配置是否符合模板约束 |
| `collect_all_models()` | cli.py:647 | 从所有 profile 提取不重复模型名 |
| `collect_models_enriched(category)` | cli.py | 收集所有模型含 variant+频率，按频率排序 |
| `record_model_usage(model, category)` | cli.py | 记录模型使用频率到 history.json |
| `fuzzy_match_models(query, candidates)` | cli.py | 模糊搜索（thefuzz/difflib） |
| `recommend_cross_vendor_models(model, all_models)` | cli.py | 跨供应商同模型推荐 |
| `get_category_aware_scores(models, category)` | cli.py | 分类感知排序分数 |
| `prompt_select_fallback_models(...)` | cli.py:733 | 交互式选择 fallback 模型链 |
| `generate_fallback_from_types(...)` | cli.py:831 | 从用户选择生成 fallback 配置 |

## CONVENTIONS（与标准 Python 的偏差）

- **近零依赖**：主要用标准库，thefuzz[speedup] 用于模糊搜索（可选，有 difflib fallback）
- **单体文件**：不拆分模块，2442 行全在 `cli.py`
- **手动 CLI**：不用 argparse/click，`sys.argv` + 字典分派
- **src 布局**：包在 `src/oma_switch/`，`setup.py` 用 `find_packages(where="src")`
- **配置存储**：JSON 文件在 `~/.config/oma-switch/`（profiles/, fallbacks/, config.json, template.json, history.json）
- **目标文件**：`~/.config/opencode/oh-my-openagent.json`
- **中文化 UI**：终端输出、提示、错误信息均为中文
- **函数命名**：公开命令 `cmd_*`，内部辅助 `_*`
- **类型注解**：使用 `typing` 但广泛使用 `Dict[str, Any]`
- **版本号**：两处硬编码 (`setup.py` + `__init__.py`)
- **测试**：pytest + `isolated_config_dir` fixture（monkeypatch Path.home()）

## ANTI-PATTERNS

1. **`except ...: pass` 吞异常**（`collect_all_models()` L660, L671）— 已修复，改为 `print_warning` 提示
2. **`Dict[str, Any]` 逃逸类型检查** — 20 处，未用 TypedDict
3. **无 CI** — 无 .github/workflows、Makefile
4. **`dcp-config` 已废弃但保留** — 向后兼容，应迁移到 `dcp bind`
5. **脆弱的 JSONC 解析** — 用正则去注释（L82-83），嵌套/字符串内注释会损坏
6. **破坏性 JSON 恢复** — `load_config()` 损坏时返回空 dict，下次 save 会覆盖

## COMMANDS

```bash
pip install .              # 安装
pip install -e .           # 可编辑安装（开发）
python -m oma_switch       # python -m 方式运行
oma-switch list            # CLI 方式运行
pytest tests/ -v           # 运行测试（98 个）
```

## NOTES

- `pyproject.toml` 仅有 `[build-system]`，元数据在 `setup.py` — 尚未迁移到 PEP 621
- 构建产物 `build/` 在 `.gitignore` 中，剩余文件可清理
- `.pytest_cache/` `.omo/` `.sisyphus/` 未在 `.gitignore` 中
- Fallback 和 Profile 完全独立：切换 profile 保留 fallback，切换 fallback 不动 model
- 版本号双重硬编码：`setup.py` 和 `__init__.py` 各维护一份，需手动同步
- 测试中 `isolated_config_dir` fixture 有多个版本，需注意 monkeypatch 范围
- 无 CI/CD 配置，无自动测试、lint、发布流水线
- 无代码质量工具配置（无 mypy、ruff、black 等）
- `history.json` 记录模型使用频率，位于 `~/.config/oma-switch/history.json`，用于智能排序
- thefuzz 降级：`HAS_THEFUZZ` 标志（cli.py L22-26），不可用时自动回退到 difflib
