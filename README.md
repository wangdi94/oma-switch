# oma-switch

OMA (Oh-My-Agent) 配置文件切换工具 — 管理 opencode 的 `oh-my-openagent.json` 配置。

支持按模板中的模型分类（主模型 / 强模型 / 中模型 / 弱模型 / 多模态模型等）快速查看、创建、编辑、切换、比较配置。

## 安装

### 方法一：pip 安装（推荐）

```bash
pip install .
```

或从任意位置：

```bash
pip install /path/to/oma-switch
```

安装后即可使用 `oma-switch` 命令。

### 方法二：直接安装脚本

```bash
./install.sh
```

## 使用

```
oma-switch <command> [args...] [--detail]
```

### 管理命令

| 命令 | 说明 |
|------|------|
| `list` | 列出所有配置文件 |
| `switch <name>` | 切换到指定配置 |
| `view [name]` | 查看配置（默认当前） |
| `create <name>` | 创建新配置 |
| `edit <name>` | 编辑配置 |
| `diff <name1> [name2]` | 比较配置 |
| `add <filepath> <name>` | 添加已有配置 |
| `rm <name>` | 删除配置 |
| `rename <name> <newname>` | 重命名 |
| `backup` | 备份当前配置 |

### Fallback 链管理

Fallback 链允许为每个模型分类（主/强/中/弱/多模态）配置备用模型序列。当主模型不可用时，系统会自动尝试 fallback 链中的下一个模型。

| 命令 | 说明 |
|------|------|
| `fallback create <name>` | 创建新的 fallback 配置 |
| `fallback list` | 列出所有 fallback 配置 |
| `fallback switch <name>` | 切换到指定 fallback 配置 |
| `fallback view [name]` | 查看 fallback 配置（默认当前） |
| `fallback edit <name>` | 编辑 fallback 配置 |
| `fallback diff <name1> [name2]` | 比较 fallback 配置 |
| `fallback rm <name>` | 删除 fallback 配置 |

**特性**：
- 每个分类独立配置 fallback 模型链（最多 5 个模型）
- 支持 `model[variant]` 语法（如 `gpt-4o[max]`）
- 切换 profile 时保留当前 fallback 配置
- 切换 fallback 时不影响主模型选择

### DCP 集成

DCP (Dynamic Context Pruning) 是 opencode 的插件，oma-switch 支持为每个配置文件独立绑定 DCP 开关。

| 命令 | 说明 |
|------|------|
| `dcp bind <name> <on\|off>` | 绑定配置文件的 DCP 状态 |
| `dcp show [name]` | 显示配置文件的 DCP 绑定状态 |
| `dcp edit <name>` | 交互式编辑 DCP 绑定 |
| `dcp set <on\|off>` | 直接设置 DCP 状态 |

**特性**：
- 每个配置文件独立维护 DCP 启用/禁用状态
- 切换配置时自动应用对应的 DCP 状态
- 支持全局 DCP 状态覆盖

### 快速模式 vs 详细模式

`view`、`create`、`edit`、`diff` 命令支持两种模式：

- **快速模式（默认）**：按模板中的模型分类（主模型 / 强模型 / 中模型 / 弱模型 / 多模态模型等）维度操作
- **详细模式（`--detail`）**：完整的 JSON 编辑 / 查看 / diff

## 开发

### 安装开发依赖

```bash
pip install -e .           # 可编辑安装
```

### 运行测试

```bash
pytest tests/ -v           # 运行所有测试（98 个）
pytest tests/test_core.py  # 运行特定测试文件
```

### 项目结构

```
src/oma_switch/
├── __init__.py        # 版本定义
├── __main__.py        # python -m 入口
└── cli.py             # 所有业务逻辑（2442 行）
```

### 代码约定

- 近零依赖（主要用标准库，thefuzz[speedup] 用于模糊搜索，可选，有 difflib fallback）
- 中文化 UI（终端输出、错误信息）
- 手动 CLI 解析（`sys.argv` + 字典分派）
- 函数命名：`cmd_*`（公开命令），`_*`（内部辅助）

## 配置存储

```
~/.config/oma-switch/
├── config.json              # 配置元数据（当前配置、当前 fallback 等）
├── template.json            # 模板定义（可选，有内置默认值）
├── history.json             # 模型使用频率记录（用于智能排序）
├── profiles/                # 配置文件的 JSON 存储
│   ├── <name>.json
│   └── ...
└── fallbacks/               # Fallback 链配置存储
    ├── <name>.json
    └── ...
```

目标 opencode 配置路径：`~/.config/opencode/oh-my-openagent.json`
DCP 配置路径：`~/.config/opencode/dcp.jsonc`
