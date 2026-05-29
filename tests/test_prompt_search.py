"""
Tests for intelligent model collection, sorting, and fuzzy search.

Covers: collect_models_enriched, fuzzy_match_models,
and the updated collect_all_models with fallback scanning and warning.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from oma_switch import cli
from oma_switch import prompt as prompt_mod
from oma_switch import history as history_mod


@pytest.fixture(autouse=True)
def history_env(tmp_path, monkeypatch):
    """Set up isolated history file for each test."""
    history_path = tmp_path / "history.json"
    monkeypatch.setattr(history_mod, "HISTORY_FILE", history_path)
    return history_path


@pytest.fixture
def profile_env(isolated_config_dir, monkeypatch):
    """Set up isolated profiles directory with test data."""
    profiles_dir = isolated_config_dir / ".config" / "oma-switch" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
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
    fallbacks_dir.mkdir(parents=True, exist_ok=True)
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


# ---------- parse_model_vendor_name ----------


class TestParseModelVendorName:
    def test_parse_model_vendor_name_normal(self):
        """Normal vendor/model parsing."""
        vendor, name = cli.parse_model_vendor_name("openai/gpt-4o")
        assert vendor == "openai"
        assert name == "gpt-4o"

    def test_parse_model_vendor_name_with_variant(self):
        """vendor/model[variant] strips variant."""
        vendor, name = cli.parse_model_vendor_name("xiaomi-token-plan-sgp/deepseek-v4-pro[max]")
        assert vendor == "xiaomi-token-plan-sgp"
        assert name == "deepseek-v4-pro"

    def test_parse_model_vendor_name_no_slash(self):
        """No slash → empty vendor, whole string as model name."""
        vendor, name = cli.parse_model_vendor_name("gpt-4o")
        assert vendor == ""
        assert name == "gpt-4o"


# ---------- recommend_cross_vendor_models ----------


class TestRecommendCrossVendorModels:
    def test_recommend_cross_vendor_exact_match(self, history_env):
        """Same model name from different vendor is recommended."""
        all_models = [
            "openai/gpt-4o",
            "azure-openai/gpt-4o",
            "openai/gpt-4o-mini",
            "deepseek/deepseek-v4-pro",
        ]
        result = cli.recommend_cross_vendor_models("openai/gpt-4o", all_models)

        assert "azure-openai/gpt-4o" in result
        assert "openai/gpt-4o" not in result
        assert "openai/gpt-4o-mini" not in result

    def test_recommend_cross_vendor_no_match(self, history_env):
        """No matches returns empty list."""
        all_models = [
            "openai/gpt-4o",
            "deepseek/deepseek-v4-pro",
        ]
        result = cli.recommend_cross_vendor_models("openai/gpt-4o", all_models)

        assert result == []

    def test_recommend_cross_vendor_same_vendor_excluded(self, history_env):
        """Same vendor models are not recommended."""
        all_models = [
            "openai/gpt-4o",
            "openai/gpt-4o-turbo",
            "azure-openai/gpt-4o",
        ]
        result = cli.recommend_cross_vendor_models("openai/gpt-4o", all_models)

        assert result == ["azure-openai/gpt-4o"]

    def test_recommend_cross_vendor_sorted_by_frequency(self, history_env):
        """Results sorted by frequency descending."""
        cli.record_model_usage("other-vendor/gpt-4o")
        cli.record_model_usage("other-vendor/gpt-4o")
        cli.record_model_usage("another-vendor/gpt-4o")

        all_models = [
            "openai/gpt-4o",
            "other-vendor/gpt-4o",
            "another-vendor/gpt-4o",
        ]
        result = cli.recommend_cross_vendor_models("openai/gpt-4o", all_models)

        assert result[0] == "other-vendor/gpt-4o"  # freq=2
        assert result[1] == "another-vendor/gpt-4o"  # freq=1


# ---------- get_category_aware_scores + category-aware sorting ----------


class TestCategoryAwareScores:
    def test_category_aware_score_higher_for_category_match(self, history_env):
        """模型在特定分类下使用次数多时，该分类下评分更高。"""
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="强模型")
        cli.record_model_usage("claude-sonnet", category="强模型")
        cli.record_model_usage("claude-sonnet", category="强模型")

        scores = cli.get_category_aware_scores(["gpt-4o", "claude-sonnet"], "主模型")
        assert scores["gpt-4o"] > scores["claude-sonnet"]

    def test_collect_models_enriched_with_category(self, profile_env, history_env):
        """传入 category 时按上下文感知评分排序。"""
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("claude-sonnet", category="强模型")
        cli.record_model_usage("claude-sonnet", category="强模型")
        cli.record_model_usage("claude-sonnet", category="强模型")

        result = cli.collect_models_enriched(category="主模型")
        model_names = [m for m, _v, _f in result]
        assert model_names.index("gpt-4o") < model_names.index("claude-sonnet")

    def test_category_aware_score_zero_for_unknown(self, history_env):
        """不在历史中的模型评分为 0.0。"""
        scores = cli.get_category_aware_scores(["unknown-model"], "主模型")
        assert scores["unknown-model"] == 0.0


# ---------- prompt_select_model ----------


class TestPromptSelectModel:
    def test_prompt_select_by_number(self, profile_env, history_env, capsys):
        """输入编号选择模型。"""
        with patch("builtins.input", return_value="1"):
            model, variant = cli.prompt_select_model("主模型", [])

        assert model == "claude-sonnet"
        assert variant is None

    def test_prompt_shows_variant_in_list(self, profile_env, history_env, capsys):
        """列表中显示变体标注。"""
        with patch("builtins.input", return_value="1"):
            cli.prompt_select_model("主模型", [])

        output = capsys.readouterr().out
        assert "[max]" in output

    def test_prompt_records_usage_on_select(self, profile_env, history_env):
        """选择模型后记录使用历史。"""
        with patch("builtins.input", return_value="1"):
            model, _ = cli.prompt_select_model("主模型", [])

        history = cli.load_history()
        assert model in history.get("models", {})
        assert history["models"][model]["count"] >= 1
        assert history["models"][model]["categories"].get("主模型", 0) >= 1

    def test_prompt_manual_variant_input(self, profile_env, history_env):
        """手动输入 model[variant] 格式。"""
        with patch("builtins.input", return_value="my-model[max]"):
            model, variant = cli.prompt_select_model("主模型", [])

        assert model == "my-model"
        assert variant == "max"

    def test_prompt_search_filter(self, profile_env, history_env, capsys):
        """搜索输入过滤模型列表，然后选择。"""
        with patch("builtins.input", side_effect=["claude", "1"]):
            model, variant = cli.prompt_select_model("主模型", [])

        output = capsys.readouterr().out
        assert "搜索 'claude' 的结果" in output
        assert model == "claude-sonnet"

    def test_prompt_empty_model_list(self, isolated_config_dir, history_env, monkeypatch, capsys):
        """无可用模型时返回 (None, None)。"""
        monkeypatch.setattr(cli, "OMA_CONFIG", isolated_config_dir / "nonexistent.json")
        monkeypatch.setattr(cli, "PROFILES_DIR", isolated_config_dir / "empty_profiles")
        monkeypatch.setattr(cli, "FALLBACKS_DIR", isolated_config_dir / "empty_fallbacks")
        model, variant = cli.prompt_select_model("主模型", [])

        assert model is None
        assert variant is None
        output = capsys.readouterr().out
        assert "当前无可用模型" in output


# ---------- prompt_select_fallback_models ----------


class TestPromptSelectFallbackModels:
    def test_fallback_prompt_grouped_display(self, profile_env, fallback_env, history_env, capsys):
        """输出包含分类分组标题。"""
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("claude-sonnet", category="强模型")
        cli.record_model_usage("model-a", category="主模型")

        with patch("builtins.input", return_value="1"):
            cli.prompt_select_fallback_models("主模型", [])

        output = capsys.readouterr().out
        assert "── 主模型 ──" in output

    def test_fallback_prompt_remembers_last(self, profile_env, fallback_env, history_env, capsys):
        """上次使用频率最高的模型标记 (上次)。"""
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("claude-sonnet", category="主模型")

        with patch("builtins.input", return_value="1"):
            cli.prompt_select_fallback_models("主模型", [])

        output = capsys.readouterr().out
        assert "(上次)" in output

    def test_fallback_prompt_search_filter(self, profile_env, fallback_env, history_env, capsys):
        """单个非数字输入触发搜索过滤。"""
        cli.record_model_usage("gpt-4o", category="主模型")
        cli.record_model_usage("claude-sonnet", category="强模型")

        with patch("builtins.input", side_effect=["gpt", "1"]):
            result = cli.prompt_select_fallback_models("主模型", [])

        output = capsys.readouterr().out
        assert "搜索 'gpt' 的结果" in output
        assert any(
            (isinstance(r, str) and "gpt-4o" in r) or
            (isinstance(r, dict) and r.get("model") == "gpt-4o")
            for r in result
        )

    def test_fallback_prompt_records_usage(self, profile_env, fallback_env, history_env):
        """选择后调用 record_model_usage 记录 fallback 类别。"""
        cli.record_model_usage("gpt-4o", category="主模型")

        with patch("builtins.input", return_value="1"):
            result = cli.prompt_select_fallback_models("主模型", [])

        assert len(result) >= 1
        history = cli.load_history()
        for item in result:
            model = item.get("model", item) if isinstance(item, dict) else item
            assert history["models"][model]["categories"].get("fallback", 0) >= 1

    def test_fallback_prompt_max_limit(self, profile_env, fallback_env, history_env, capsys):
        """选择超过 5 个模型时截断并输出警告。"""
        # 构造 6 个可用模型以触发上限截断逻辑
        dummy_models = [
            ("m1", None, 0), ("m2", None, 1), ("m3", None, 2),
            ("m4", None, 3), ("m5", None, 4), ("m6", None, 5),
        ]

        with patch("builtins.input", return_value="1,2,3,4,5,6"), \
             patch.object(prompt_mod, "collect_models_enriched", return_value=dummy_models):
            result = cli.prompt_select_fallback_models("主模型", [])

        assert len(result) == 5
        output = capsys.readouterr().out
        assert "最多只能选择 5 个" in output


# ---------- Edge case tests (T10) ----------


class TestEdgeCases:
    def test_prompt_input_zero(self, profile_env, history_env, capsys):
        """输入 0 时显示 '编号从 1 开始' 并重新提示，不崩溃。"""
        with patch("builtins.input", side_effect=["0", "1"]):
            model, variant = cli.prompt_select_model("主模型", [])

        output = capsys.readouterr().out
        assert "编号从 1 开始" in output
        # 应该成功选择第一个模型
        assert model is not None

    def test_parse_variant_unclosed_bracket(self):
        """未闭合的括号应作为普通模型名返回。"""
        model, variant = cli.parse_model_with_variant("model[xxx")
        assert model == "model[xxx"
        assert variant is None

    def test_fuzzy_match_difflib_degradation(self):
        """HAS_THEFUZZ=False 时 difflib 后备仍能正常匹配。"""
        with patch("oma_switch.cli.HAS_THEFUZZ", False):
            candidates = ["gpt-4o", "gpt-4o-mini", "claude-sonnet", "deepseek-v4-pro"]
            # 精确匹配
            result = cli.fuzzy_match_models("gpt-4o", candidates)
            assert "gpt-4o" in result
            # 前缀匹配
            result = cli.fuzzy_match_models("gpt", candidates)
            assert any("gpt" in m for m in result)
            # 空查询
            assert cli.fuzzy_match_models("", candidates) == []
            # 空候选
            assert cli.fuzzy_match_models("gpt", []) == []

    def test_empty_history_alphabetical_sort(self, profile_env, history_env):
        """历史为空时，所有模型频率为 0，按字母顺序排序。"""
        # 不记录任何使用历史
        result = cli.collect_models_enriched()
        model_names = [m for m, _v, _f in result]
        frequencies = [f for _m, _v, f in result]

        # 所有频率应为 0
        assert all(f == 0 for f in frequencies)
        # 应按字母顺序排序
        assert model_names == sorted(model_names, key=str.lower)
