"""Tests for validate_fallback_config function."""

import pytest
from oma_switch.cli import validate_fallback_config


class TestValidateFallbackConfig:
    """validate_fallback_config 的测试用例。"""

    def test_valid_config(self):
        """完整合法配置应返回 (True, "")。"""
        data = {
            "主模型": {"fallback_models": ["model-a", "model-b"]},
            "强模型": {"fallback_models": [{"model": "x", "variant": "max"}]},
            "中模型": {"fallback_models": []},
            "弱模型": {"fallback_models": ["model-c"]},
            "多模态模型": {"fallback_models": ["model-d"]},
        }
        ok, msg = validate_fallback_config(data)
        assert ok is True
        assert msg == ""

    def test_invalid_category(self):
        """未知分类键应返回 (False, "unknown category: invalid")。"""
        data = {"invalid": {"fallback_models": ["m"]}}
        ok, msg = validate_fallback_config(data)
        assert ok is False
        assert "unknown category" in msg
        assert "invalid" in msg

    def test_missing_fallback_models(self):
        """值中缺少 fallback_models 键应返回错误。"""
        data = {"主模型": {"other_key": "value"}}
        ok, msg = validate_fallback_config(data)
        assert ok is False
        assert "fallback_models" in msg

    def test_non_list_fallback_models(self):
        """fallback_models 不是列表时应返回错误。"""
        data = {"主模型": {"fallback_models": "not-a-list"}}
        ok, msg = validate_fallback_config(data)
        assert ok is False
        assert "list" in msg

    def test_max_length(self):
        """超过 5 个模型应返回错误。"""
        data = {"主模型": {"fallback_models": ["m1", "m2", "m3", "m4", "m5", "m6"]}}
        ok, msg = validate_fallback_config(data)
        assert ok is False
        assert "5" in msg

    def test_duplicate_models(self):
        """链内重复模型应返回错误。"""
        data = {"主模型": {"fallback_models": ["model-a", "model-a"]}}
        ok, msg = validate_fallback_config(data)
        assert ok is False
        assert "duplicate" in msg

    def test_empty_config(self):
        """空字典应视为合法（允许部分配置）。"""
        ok, msg = validate_fallback_config({})
        assert ok is True
        assert msg == ""

    def test_object_items_with_model(self):
        """含 model 键的对象列表项应合法。"""
        data = {
            "强模型": {
                "fallback_models": [
                    {"model": "gpt-4o", "variant": "max"},
                    {"model": "claude-3.5", "temperature": 0.7},
                ]
            }
        }
        ok, msg = validate_fallback_config(data)
        assert ok is True
        assert msg == ""
