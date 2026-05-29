#!/usr/bin/env python3
"""
TypedDict 定义模块：为 oma-switch 核心数据结构提供类型注解。

包含 4 个主要 TypedDict：
- OmaSwitchConfig: config.json 主配置结构
- VersionMetadata: 版本快照元数据
- FallbackData: fallback 链配置文件结构
- DcpConfig: DCP 插件配置结构
"""

from typing import Dict, List, Optional, TypedDict, Union


# ── Profile 元数据 ────────────────────────────────────────────────


class ProfileMeta(TypedDict, total=False):
    """存储在 config.json 中的单个 profile 元数据。

    created/description/dcp_enabled 在添加时设置，
    modified/last_used/renamed 在操作时按需添加。
    """

    created: str
    description: str
    dcp_enabled: bool
    modified: str
    last_used: str
    renamed: str


# ── 主配置 ────────────────────────────────────────────────────────


class OmaSwitchConfig(TypedDict):
    """config.json 主配置结构。

    字段：
        current: 当前激活的 profile 名称，None 表示无激活 profile
        profiles: profile 名称 → 元数据的映射
        current_fallback: 当前激活的 fallback 链名称，空字符串表示未设置
    """

    current: Optional[str]
    profiles: Dict[str, ProfileMeta]
    current_fallback: str


# ── 版本元数据 ────────────────────────────────────────────────────


class VersionMetadata(TypedDict):
    """版本快照元数据，存储在 .versions/<filename>/*.meta.json 中。

    字段：
        timestamp: ISO 8601 格式时间戳
        operation: 触发快照的操作名称（如 'switch', 'edit', 'save_config'）
        command_args: 命令参数列表
        file_path: 原始文件路径
        file_size: 文件大小（字节）
        file_hash: SHA-256 哈希（格式 'sha256:...'），文件不存在时为空字符串
    """

    timestamp: str
    operation: str
    command_args: List[str]
    file_path: str
    file_size: int
    file_hash: str


# ── Fallback 配置 ─────────────────────────────────────────────────


class FallbackModelItem(TypedDict):
    """fallback 链中的单个模型条目（带 variant）。"""

    model: str


class FallbackModelItemWithVariant(TypedDict):
    """fallback 链中的单个模型条目（带 variant）。"""

    model: str
    variant: str


class FallbackCategory(TypedDict):
    """fallback 配置中单个分类的数据。

    fallback_models 列表中每个元素可以是：
    - 字符串（纯模型名）
    - 字典（包含 model 和可选 variant）
    """

    fallback_models: List[Union[str, FallbackModelItem, FallbackModelItemWithVariant]]


class FallbackData(TypedDict, total=False):
    """完整的 fallback 配置文件结构。

    顶级键为模板分类标签，每个值为 FallbackCategory。
    total=False 因为配置文件可能只包含部分分类。
    """

    主模型: FallbackCategory
    强模型: FallbackCategory
    中模型: FallbackCategory
    弱模型: FallbackCategory
    多模态模型: FallbackCategory


# ── DCP 配置 ──────────────────────────────────────────────────────


class _DcpConfigRequired(TypedDict):
    """DCP 配置必需字段。"""

    enabled: bool


class DcpConfig(_DcpConfigRequired, total=False):
    """DCP (Dynamic Context Pruning) 插件配置。

    enabled 为必需字段，其余为可选。
    嵌套对象（compress, turnProtection, strategies）在运行时为 dict，
    此处不展开定义以保持灵活性。
    """

    debug: bool
    pruneNotification: str
    pruneNotificationType: str
