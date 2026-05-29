#!/usr/bin/env python3
"""
Constants module for oma-switch.

Contains all module-level path constants and thefuzz availability flag.
"""

from pathlib import Path

try:
    from thefuzz import fuzz as _fuzz  # noqa: F401

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
