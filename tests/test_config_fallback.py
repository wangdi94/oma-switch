"""
Tests for current_fallback config support.

Verifies backward compatibility, get/set/clear helpers for the
current_fallback field in config.json.
"""

import json
import pytest
from pathlib import Path
from oma_switch.cli import (
    load_config,
    save_config,
    get_current_fallback,
    set_current_fallback,
    clear_current_fallback_if_deleted,
    CONFIG_FILE,
    ensure_dirs,
)


class TestLoadConfigFallback:
    """load_config handles missing current_fallback field (backward compat)."""

    def test_backward_compat(self, isolated_config_dir):
        """Config without current_fallback field returns current_fallback=''."""
        ensure_dirs()
        old_config = {"current": "my-profile", "profiles": {}}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(old_config, f)

        result = load_config()

        assert result["current_fallback"] == ""
        assert result["current"] == "my-profile"

    def test_load_preserves_existing_fallback(self, isolated_config_dir):
        """Config with current_fallback preserves its value."""
        ensure_dirs()
        config = {"current": "p1", "profiles": {}, "current_fallback": "chain-a"}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f)

        result = load_config()

        assert result["current_fallback"] == "chain-a"


class TestGetCurrentFallback:
    """get_current_fallback returns the correct value."""

    def test_get_current_fallback(self):
        config = {"current_fallback": "my-chain"}
        assert get_current_fallback(config) == "my-chain"

    def test_get_current_fallback_missing(self):
        config = {}
        assert get_current_fallback(config) == ""


class TestSetCurrentFallback:
    """set_current_fallback persists value to disk."""

    def test_set_current_fallback(self, isolated_config_dir):
        ensure_dirs()
        config = {"current": None, "profiles": {}, "current_fallback": ""}
        save_config(config)

        set_current_fallback(config, "my-chain")

        # Re-read from disk to verify persistence
        reloaded = load_config()
        assert reloaded["current_fallback"] == "my-chain"


class TestClearCurrentFallbackIfDeleted:
    """clear_current_fallback_if_deleted clears only when matching."""

    def test_clear_matching(self, isolated_config_dir):
        ensure_dirs()
        config = {"current": None, "profiles": {}, "current_fallback": "chain-a"}
        save_config(config)

        result = clear_current_fallback_if_deleted(config, "chain-a")

        assert result is True
        assert config["current_fallback"] == ""
        # Verify persisted
        reloaded = load_config()
        assert reloaded["current_fallback"] == ""

    def test_clear_non_matching(self, isolated_config_dir):
        ensure_dirs()
        config = {"current": None, "profiles": {}, "current_fallback": "chain-a"}
        save_config(config)

        result = clear_current_fallback_if_deleted(config, "chain-b")

        assert result is False
        assert config["current_fallback"] == "chain-a"
        # Verify persisted value unchanged
        reloaded = load_config()
        assert reloaded["current_fallback"] == "chain-a"
