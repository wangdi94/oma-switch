"""Tests for get_fallback_summary and print_fallback_summary functions."""

import pytest
from io import StringIO
from unittest.mock import patch

from oma_switch.cli import get_fallback_summary, print_fallback_summary, Colors


class TestGetFallbackSummary:
    """get_fallback_summary 的测试用例。"""

    def test_summary_extraction(self, sample_fallback_data):
        """应返回含 5 个键的字典，每个键对应正确的模型链。"""
        result = get_fallback_summary(sample_fallback_data)

        assert isinstance(result, dict)
        assert len(result) == 5
        assert set(result.keys()) == {
            "主模型", "强模型", "中模型", "弱模型", "多模态模型"
        }

        # 主模型: 两个字符串条目
        assert result["主模型"] == ["model-a", "model-b"]
        # 强模型: 字典条目，含 variant
        assert result["强模型"] == ["x [variant=max]"]
        # 中模型: 空链
        assert result["中模型"] == []
        # 弱模型/多模态: 单个字符串
        assert result["弱模型"] == ["model-c"]
        assert result["多模态模型"] == ["model-d"]

    def test_empty_chain_returns_empty_list(self):
        """空 fallback_models 应返回空列表。"""
        data = {
            "主模型": {"fallback_models": []},
            "强模型": {"fallback_models": []},
            "中模型": {"fallback_models": []},
            "弱模型": {"fallback_models": []},
            "多模态模型": {"fallback_models": []},
        }
        result = get_fallback_summary(data)
        for category, chain in result.items():
            assert chain == [], f"{category} 应为空列表"

    def test_variant_display(self):
        """字典条目 {'model':'x','variant':'max'} 应格式化为 'x [variant=max]'。"""
        data = {
            "主模型": {"fallback_models": [
                {"model": "x", "variant": "max"},
                {"model": "y", "variant": None},
                "plain-model",
            ]},
            "强模型": {"fallback_models": []},
            "中模型": {"fallback_models": []},
            "弱模型": {"fallback_models": []},
            "多模态模型": {"fallback_models": []},
        }
        result = get_fallback_summary(data)
        assert result["主模型"][0] == "x [variant=max]"
        # variant=None 的字典条目不附加 variant 后缀
        assert result["主模型"][1] == "y"
        # 字符串条目原样返回
        assert result["主模型"][2] == "plain-model"

    def test_missing_fallback_models_key(self):
        """值中无 fallback_models 键时应返回空列表。"""
        data = {
            "主模型": {"other_key": "value"},
            "强模型": {},
            "中模型": {"fallback_models": ["m1"]},
            "弱模型": {"fallback_models": []},
            "多模态模型": {"fallback_models": []},
        }
        result = get_fallback_summary(data)
        assert result["主模型"] == []
        assert result["强模型"] == []
        assert result["中模型"] == ["m1"]


class TestPrintFallbackSummary:
    """print_fallback_summary 的测试用例。"""

    def test_empty_chain_display(self, capsys):
        """空链应显示 '(none)'。"""
        summary = {
            "主模型": [],
            "强模型": [],
            "中模型": [],
            "弱模型": [],
            "多模态模型": [],
        }
        print_fallback_summary(summary)
        output = capsys.readouterr().out

        assert "(none)" in output

    def test_chain_display_with_arrow(self, capsys):
        """多模型链应以 '→' 连接显示。"""
        summary = {
            "主模型": ["model-a", "model-b", "model-c"],
            "强模型": ["model-x"],
            "中模型": [],
            "弱模型": [],
            "多模态模型": [],
        }
        print_fallback_summary(summary)
        output = capsys.readouterr().out

        assert "model-a → model-b → model-c" in output
        assert "model-x" in output

    def test_title_display(self, capsys):
        """传入 title 时应先显示标题。"""
        summary = {
            "主模型": ["m1"],
            "强模型": [],
            "中模型": [],
            "弱模型": [],
            "多模态模型": [],
        }
        print_fallback_summary(summary, title="Fallback 配置")
        output = capsys.readouterr().out

        assert "Fallback 配置" in output

    def test_variant_in_display(self, capsys):
        """含 variant 的条目应正确显示。"""
        summary = {
            "主模型": ["x [variant=max]", "model-b"],
            "强模型": [],
            "中模型": [],
            "弱模型": [],
            "多模态模型": [],
        }
        print_fallback_summary(summary)
        output = capsys.readouterr().out

        assert "x [variant=max]" in output
        assert "x [variant=max] → model-b" in output
