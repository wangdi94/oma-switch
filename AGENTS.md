# oma-switch

**Generated:** 2026-05-26
**Commit:** 3978d2f
**Branch:** master

## OVERVIEW

Python CLI 工具，管理 opencode 的 `oh-my-openagent.json` 配置。按模板中的模型分类（主/强/中/弱/多模态）快速查看、创建、编辑、切换、比较配置。每个配置独立绑定 DCP 开关。

栈：Python ≥3.10 + 标准库（零第三方依赖）。

## STRUCTURE

```
oma-switch/
├── pyproject.toml         # 仅 [build-system]，无 [project]
├── setup.py               # 所有元数据+入口点（传统模式）
├── install.sh             # pip install 包装
├── src/oma_switch/
│   ├── __init__.py        # v2.0.0
│   ├── __main__.py        # python -m 入口 → cli.main
│   └── cli.py             # 1760行单体：全部逻辑
├── .omo/                  # 工作会话记录
└── .sisyphus/             # agent 上下文
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| 配置管理 | `cli.py` | 12 个 `cmd_*` 函数，字典调度（无 argparse） |
| 模板 | `cli.py` `∼290-430` | `DEFAULT_TEMPLATE_GROUPS` + load/save/check |
| DCP 管理 | `cli.py` `∼73-1480` | get/save/update/bind/show/edit/set |
| 配置文件 I/O | `cli.py` `∼68-215` | JSON 读写、目录保证、profile 加载 |
| 模型选择 | `cli.py` `∼468-527` | 交互式 prompt + 解析 `model[variant]` |
| 入口 | `__init__.py` `__main__.py` `setup.py` | 全部汇聚到 `cli.main()` |

## KEY FUNCTIONS

| Symbol | Location | Role |
|--------|----------|------|
| `main()` | cli.py:1719 | CLI 入口，sys.argv 解析 + 命令分派 |
| `cmd_switch(name)` | cli.py:971 | 切换配置 + 应用配置绑定的 DCP 状态 |
| `cmd_create/dcp/edit/list/view/diff/...` | cli.py:584-1648 | 12 个命令实现 |
| `update_dcp_state(enable)` | cli.py:94 | 用正则修改 dcp.jsonc 的 enabled 字段 |
| `get_dcp_config()` | cli.py:73 | 读取 dcp.jsonc（去注释） |
| `_apply_profile_dcp(config, name)` | cli.py:147 | 切换时按配置绑定设置 DCP |
| `check_template_profile(profile)` | cli.py:351 | 验证配置是否符合模板约束 |
| `merge_to_oma_config(source)` | cli.py:154 | 合并 agents+categories 到目标 JSON |

## CONVENTIONS（与标准 Python 的偏差）

- **零依赖**：全部用标准库，无第三方包
- **单体文件**：不拆分模块，1760 行全在 `cli.py`
- **手动 CLI**：不用 argparse/click，`sys.argv` + 字典分派
- **src 布局**：包在 `src/oma_switch/`，`setup.py` 用 `find_packages(where="src")`
- **配置存储**：JSON 文件在 `~/.config/oma-switch/`，目标文件在 `~/.config/opencode/`
- **中文化 UI**：终端输出、提示、错误信息均为中文
- **函数命名**：公开命令 `cmd_*`，内部辅助 `_*`
- **类型注解**：使用 `typing` 但广泛使用 `Dict[str, Any]`
- **版本号**：两处硬编码 (`setup.py` + `__init__.py`)

## ANTI-PATTERNS

1. **`except ...: pass` 吞异常**（`collect_all_models()` 中 2 处）— 损坏 JSON 时无声跳过
2. **`Dict[str, Any]` 逃逸类型检查** — 10 处，未用 TypedDict
3. **无测试** — 整个项目零测试文件
4. **无 CI** — 无 .github/workflows、Makefile

## COMMANDS

```bash
pip install .              # 安装
pip install -e .           # 可编辑安装（开发）
python -m oma_switch       # python -m 方式运行
oma-switch list            # CLI 方式运行
```

## NOTES

- `dcp-config` 命令已废弃，改用 `oma-switch dcp bind`
- `pyproject.toml` 仅有 `[build-system]`，元数据在 `setup.py` — 尚未迁移到 PEP 621
- 构建产物 `build/` 在 `.gitignore` 中，剩余文件可清理
- `.pytest_cache/` `.omo/` `.sisyphus/` 未在 `.gitignore` 中
