"""
Tests for intelligent model collection, sorting, and fuzzy search.

Covers: collect_models_enriched, fuzzy_match_models, filter_models_by_category,
and the updated collect_all_models with fallback scanning and warning.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from oma_switch import cli


@pytest.fixture(autouse=True)
def history_env(tmp_path, monkeypatch):
    """Set up isolated history file for each test."""
    history_path = tmp_path / "history.json"
    monkeypatch.setattr(cli, "HISTORY_FILE", history_path)
    return history_path


@pytest.fixture
def profile_env(isolated_config_dir, monkeypatch):
    """Set up isolated profiles directory with test data."""
    profiles_dir = isolated_config_dir / ".config" / "oma-switch" / "profiles"
    profiles_dir.mkdir(parents=True)
    monkeypatch.setattr(cli, "PROFILES_DIR", profiles_dir)

    profile1 = {
        "agents": {
            "sisyphus": {"model": "gpt-4o"},
            "oracle": {"model": "claude-sonnet"},
        },
        "categories": {},
    }
    profile2 = {
        "agents": {},
        "categories": {
            "ultrabrain": {"model": "gpt-4o", "variant": "max"},
        },
    }

    (profiles_dir / "p1.json").write_text(json.dumps(profile1), encoding="utf-8")
    (profiles_dir / "p2.json").write_text(json.dumps(profile2), encoding="utf-8")

    return profiles_dir


@pytest.fixture
def fallback_env(isolated_config_dir, monkeypatch):
    """Set up isolated fallbacks directory with test data."""
    fallbacks_dir = isolated_config_dir / ".config" / "oma-switch" / "fallbacks"
    fallbacks_dir.mkdir(parents=True)
    monkeypatch.setattr(cli, "FALLBACKS_DIR", fallbacks_dir)

    fallback_data = {
        "主模型": {
            "fallback_models": ["model-a", {"model": "model-b", "variant": "pro"}]
        },
        "强模型": {"fallback_models": ["model-c"]},
    }
    (fallbacks_dir / "test.json").write_text(
        json.dumps(fallback_data), encoding="utf-8"
    )

    return fallbacks_dir


# ---------- collect_models_enriched ----------


class TestCollectModelsEnriched:
    def test_returns_tuples_with_frequency(self, profile_env, history_env):
        """collect_models_enriched returns (model, variant, frequency) tuples."""
        cli.record_model_usage("gpt-4o")
        cli.record_model_usage("gpt-4o")
        cli.record_model_usage("claude-sonnet")

        result = cli.collect_models_enriched()

        gpt = next(r for r in result if r[0] == "gpt-4o")
        claude = next(r for r in result if r[0] == "claude-sonnet")

        assert gpt[2] == 2  # frequency
        assert claude[2] == 1

    def test_sorted_by_frequency_desc(self, profile_env, history_env):
        """Results sorted by frequency descending."""
        cli.record_model_usage("gpt-4o")
        cli.record_model_usage("gpt-4o")
        cli.record_model_usage("gpt-4o")
        cli.record_model_usage("claude-sonnet")

        result = cli.collect_models_enriched()

        assert result[0][0] == "gpt-4o"
        assert result[1][0] == "claude-sonnet"

    def test_same_frequency_tiebreaker_model_asc(self, profile_env, history_env):
        """Same frequency models sorted alphabetically."""
        cli.record_model_usage("gpt-4o")
        cli.record_model_usage("claude-sonnet")

        result = cli.collect_models_enriched()

        assert result[0][0] == "claude-sonnet"
        assert result[1][0] == "gpt-4o"

    def test_collects_from_fallbacks(self, profile_env, fallback_env, history_env):
        """Models from fallback configs are also collected."""
        result = cli.collect_models_enriched()
        model_names = [r[0] for r in result]

        assert "model-a" in model_names
        assert "model-b" in model_names
        assert "model-c" in model_names

    def test_variant_from_fallback_dict(self, profile_env, fallback_env, history_env):
        """Variant extracted from fallback dict entries."""
        result = cli.collect_models_enriched()
        model_b = next(r for r in result if r[0] == "model-b")

        assert model_b[1] == "pro"

    def test_deduplicate_same_model(self, profile_env, history_env):
        """Same model from multiple sources deduplicated."""
        result = cli.collect_models_enriched()
        model_names = [r[0] for r in result]

        # gpt-4o appears in p1 and p2, should only appear once
        assert model_names.count("gpt-4o") == 1


# ---------- fuzzy_match_models ----------


class TestFuzzyMatchModels:
    def test_exact_match(self):
        """Exact match returns the model."""
        result = cli.fuzzy_match_models("gpt-4o", ["gpt-4o", "claude-sonnet"])
        assert "gpt-4o" in result

    def test_prefix_match_first(self):
        """Prefix matches are prioritized first."""
        candidates = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "claude-sonnet"]
        result = cli.fuzzy_match_models("gpt-4o", candidates)

        assert result[0] == "gpt-4o"

    def test_empty_query_returns_empty(self):
        """Empty query returns empty list."""
        assert cli.fuzzy_match_models("", ["gpt-4o"]) == []

    def test_empty_candidates_returns_empty(self):
        """Empty candidates returns empty list."""
        assert cli.fuzzy_match_models("gpt-4o", []) == []

    def test_limit_parameter(self):
        """Limit parameter restricts results."""
        candidates = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        result = cli.fuzzy_match_models("gpt", candidates, limit=2)

        assert len(result) <= 2

    @patch("oma_switch.cli.HAS_THEFUZZ", False)
    def test_difflib_fallback(self):
        """When HAS_THEFUZZ is False, uses difflib as fallback."""
        candidates = ["gpt-4o", "gpt-4o-mini", "claude-sonnet"]
        result = cli.fuzzy_match_models("gpt-4o", candidates)

        assert "gpt-4o" in result


# ---------- filter_models_by_category ----------


class TestFilterModelsByCategory:
    def test_filters_by_category(self, history_env):
        """Only models with usage in category are returned."""
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("claude-sonnet", category="强模型")

        models = ["gpt-4o", "claude-sonnet", "gemini-pro"]
        result = cli.filter_models_by_category(models, "主模型")

        assert result == ["gpt-4o"]

    def test_no_usage_returns_empty(self, history_env):
        """Models without category usage are filtered out."""
        cli.record_model_usage("gpt-4o")  # no category

        result = cli.filter_models_by_category(["gpt-4o"], "主模型")
        assert result == []


# ---------- collect_all_models (updated) ----------


class TestCollectAllModelsUpdated:
    def test_collects_from_fallbacks(self, profile_env, fallback_env):
        """collect_all_models now includes models from fallbacks."""
        result = cli.collect_all_models()

        assert "model-a" in result
        assert "model-b" in result
        assert "model-c" in result

    def test_warns_on_corrupt_profile(self, profile_env, capsys):
        """Corrupt profile triggers warning instead of silent skip."""
        corrupt_dir = cli.PROFILES_DIR
        (corrupt_dir / "corrupt.json").write_text("NOT JSON {{{", encoding="utf-8")

        result = cli.collect_all_models()

        # Should still return valid models
        assert "gpt-4o" in result

        # Should have printed warning
        captured = capsys.readouterr()
        assert "⚠" in captured.out
