#!/usr/bin/env python3
"""
Display utilities: color output, print helpers, directory setup.
"""

from .constants import CONFIG_DIR, FALLBACKS_DIR, PROFILES_DIR


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    PURPLE = "\033[0;35m"
    CYAN = "\033[0;36m"
    GRAY = "\033[0;90m"
    BOLD = "\033[1m"
    NC = "\033[0m"


def print_color(color: str, message: str) -> None:
    print(f"{color}{message}{Colors.NC}")


def print_error(message: str) -> None:
    print_color(Colors.RED, f"错误: {message}")


def print_success(message: str) -> None:
    print_color(Colors.GREEN, f"✓ {message}")


def print_warning(message: str) -> None:
    print_color(Colors.YELLOW, f"⚠ {message}")


def print_info(message: str) -> None:
    print_color(Colors.BLUE, f"ℹ {message}")


def print_dim(message: str) -> None:
    print_color(Colors.GRAY, message)


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    FALLBACKS_DIR.mkdir(parents=True, exist_ok=True)
