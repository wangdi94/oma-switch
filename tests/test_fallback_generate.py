"""Tests for generate_fallback_from_types function."""

import copy
from unittest.mock import patch

from oma_switch.cli import generate_fallback_from_types

# 模板中的 5 个分类标签
ALL_CATEGORIES = ["主模型", "强模型", "中模型", "弱模型", "多模态模型"]

# 简化模板用于 monkeypatch
MOCK_TEMPLATE = {
    "主模型": {("agents", "prometheus")},
    "强模型": {("agents", "oracle")},
    "中模型": {("agents", "sisyphus-junior")},
    "弱模型": {("agents", "explore")},
    "多模态模型": {("agents", "multimodal-looker")},
}


class TestGenerateFallbackFromTypes:
    """generate_fallback_from_types 的测试用例。"""

    @patch("oma_switch.cli.load_template", return_value=copy.deepcopy(MOCK_TEMPLATE))
    def test_full_generation(self, mock_load):
        """所有 5 个分类都有 fallback 链 → 输出包含全部 5 个 key 且值正确。"""
        choices = {
            "主模型": ["model-a", "model-b"],
            "强模型": [{"model": "x", "variant": "max"}],
            "中模型": ["model-c"],
            "弱模型": ["model-d", "model-e"],
            "多模态模型": ["model-f"],
        }
        result = generate_fallback_from_types(choices)

        # 结果应包含全部 5 个分类
        assert set(result.keys()) == set(ALL_CATEGORIES)

        # 每个分类的 fallback_models 与输入一致
        assert result["主模型"]["fallback_models"] == ["model-a", "model-b"]
        assert result["强模型"]["fallback_models"] == [{"model": "x", "variant": "max"}]
        assert result["中模型"]["fallback_models"] == ["model-c"]
        assert result["弱模型"]["fallback_models"] == ["model-d", "model-e"]
        assert result["多模态模型"]["fallback_models"] == ["model-f"]

    @patch("oma_switch.cli.load_template", return_value=copy.deepcopy(MOCK_TEMPLATE))
    def test_partial_defaults(self, mock_load):
        """仅指定 2 个分类，其余默认为 fallback_models=[]。"""
        choices = {
            "主模型": ["model-a"],
            "弱模型": ["model-c"],
        }
        result = generate_fallback_from_types(choices)

        assert set(result.keys()) == set(ALL_CATEGORIES)
        assert result["主模型"]["fallback_models"] == ["model-a"]
        assert result["弱模型"]["fallback_models"] == ["model-c"]
        # 未指定的分类默认为空列表
        assert result["强模型"]["fallback_models"] == []
        assert result["中模型"]["fallback_models"] == []
        assert result["多模态模型"]["fallback_models"] == []

    @patch("oma_switch.cli.load_template", return_value=copy.deepcopy(MOCK_TEMPLATE))
    def test_empty_input(self, mock_load):
        """空字典输入 → 所有分类的 fallback_models 均为 []。"""
        result = generate_fallback_from_types({})

        assert set(result.keys()) == set(ALL_CATEGORIES)
        for cat in ALL_CATEGORIES:
            assert result[cat]["fallback_models"] == []

    @patch("oma_switch.cli.load_template", return_value=copy.deepcopy(MOCK_TEMPLATE))
    def test_returns_dict_not_reference(self, mock_load):
        """返回值应为独立字典，不与输入共享引用。"""
        chain = ["model-a"]
        choices = {"主模型": chain}
        result = generate_fallback_from_types(choices)

        # 修改输入不应影响结果
        chain.append("model-b")
        assert result["主模型"]["fallback_models"] == ["model-a"]

    @patch("oma_switch.cli.load_template", return_value=copy.deepcopy(MOCK_TEMPLATE))
    def test_structure_keys(self, mock_load):
        """每个分类的值都是含 fallback_models 键的字典。"""
        result = generate_fallback_from_types({})
        for cat in ALL_CATEGORIES:
            assert isinstance(result[cat], dict)
            assert "fallback_models" in result[cat]
            assert isinstance(result[cat]["fallback_models"], list)
