"""
Tests for model usage history infrastructure.

Covers: load_history, save_history, record_model_usage,
get_model_frequency, get_category_frequency.
"""

import json

import pytest

# Import after isolated_config_dir monkeypatch is applied
from oma_switch import cli
from oma_switch import history as history_mod


@pytest.fixture(autouse=True)
def history_env(tmp_path, monkeypatch):
    """Set up isolated history file for each test."""
    history_path = tmp_path / "history.json"
    monkeypatch.setattr(history_mod, "HISTORY_FILE", history_path)
    return history_path


# ---------- load_history ----------


class TestLoadHistory:
    def test_no_file_returns_empty(self, history_env):
        """load_history returns empty dict when file doesn't exist."""
        result = cli.load_history()
        assert result == {"models": {}}

    def test_corrupt_file_returns_empty(self, history_env):
        """load_history returns empty dict and warns on corrupt JSON."""
        history_env.write_text("NOT VALID JSON {{{", encoding="utf-8")
        result = cli.load_history()
        assert result == {"models": {}}


# ---------- save_history ----------


class TestSaveHistory:
    def test_save_creates_file(self, history_env):
        """save_history creates the file with correct JSON."""
        data = {"models": {"gpt-4o": {"count": 3, "categories": {"主模型": 3}}}}
        cli.save_history(data)
        assert history_env.exists()
        loaded = json.loads(history_env.read_text(encoding="utf-8"))
        assert loaded == data

    def test_save_roundtrip(self, history_env):
        """save_history then load_history returns same data."""
        data = {"models": {"claude-sonnet": {"count": 1, "categories": {}}}}
        cli.save_history(data)
        result = cli.load_history()
        assert result == data


# ---------- record_model_usage ----------


class TestRecordModelUsage:
    def test_new_model_creates_entry(self, history_env):
        """Recording a new model creates entry with count=1."""
        cli.record_model_usage("gpt-4o")
        history = cli.load_history()
        assert history["models"]["gpt-4o"]["count"] == 1
        assert history["models"]["gpt-4o"]["categories"] == {}

    def test_existing_model_increments(self, history_env):
        """Recording same model again increments count."""
        cli.record_model_usage("gpt-4o")
        cli.record_model_usage("gpt-4o")
        cli.record_model_usage("gpt-4o")
        history = cli.load_history()
        assert history["models"]["gpt-4o"]["count"] == 3

    def test_with_category(self, history_env):
        """Recording with category tracks category-specific count."""
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="强模型")
        history = cli.load_history()
        assert history["models"]["gpt-4o"]["count"] == 3
        assert history["models"]["gpt-4o"]["categories"]["主模型"] == 2
        assert history["models"]["gpt-4o"]["categories"]["强模型"] == 1


# ---------- get_model_frequency ----------


class TestGetModelFrequency:
    def test_returns_count(self, history_env):
        """get_model_frequency returns total count for known model."""
        cli.record_model_usage("gpt-4o")
        cli.record_model_usage("gpt-4o")
        assert cli.get_model_frequency("gpt-4o") == 2

    def test_unknown_model_returns_zero(self, history_env):
        """get_model_frequency returns 0 for unknown model."""
        assert cli.get_model_frequency("nonexistent") == 0


# ---------- get_category_frequency ----------


class TestGetCategoryFrequency:
    def test_returns_category_count(self, history_env):
        """get_category_frequency returns category-specific count."""
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="强模型")
        assert cli.get_category_frequency("gpt-4o", "主模型") == 2
        assert cli.get_category_frequency("gpt-4o", "强模型") == 1

    def test_unknown_category_returns_zero(self, history_env):
        """get_category_frequency returns 0 for unknown category."""
        cli.record_model_usage("gpt-4o")
        assert cli.get_category_frequency("gpt-4o", "不存在的分类") == 0
