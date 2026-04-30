# oma-switch

OMA (Oh-My-Agent) 配置文件切换工具 — 管理 opencode 的 `oh-my-openagent.json` 配置。

支持按四类模型（强模型 / 中模型 / 弱模型 / 多模态模型）快速查看、创建、编辑、切换、比较配置。

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

### 快速模式 vs 详细模式

`view`、`create`、`edit`、`diff` 命令支持两种模式：

- **快速模式（默认）**：按四类模型（强模型 / 中模型 / 弱模型 / 多模态模型）维度操作
- **详细模式（`--detail`）**：完整的 JSON 编辑 / 查看 / diff

## 配置存储

```
~/.config/oma-switch/
├── config.json              # 配置元数据
└── profiles/                # 配置文件的 JSON 存储
    ├── <name>.json
    └── ...
```

目标 opencode 配置路径：`~/.config/opencode/oh-my-openagent.json`
