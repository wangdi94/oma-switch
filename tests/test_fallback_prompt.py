"""Tests for prompt_select_fallback_models() in oma_switch.cli."""

import sys
import pytest

sys.path.insert(0, "src")

import oma_switch.cli as cli
from oma_switch.cli import prompt_select_fallback_models


MODELS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]


def test_select_by_number(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "1,3")
    result = prompt_select_fallback_models("主模型", MODELS)
    assert result == ["alpha", "gamma"]


def test_select_by_name(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "gpt-4o,claude-opus")
    result = prompt_select_fallback_models("主模型", MODELS)
    assert result == ["gpt-4o", "claude-opus"]


def test_empty_clears(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "")
    result = prompt_select_fallback_models("主模型", MODELS, current=["a", "b"])
    assert result == []


def test_max_five(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "1,2,3,4,5,6")
    result = prompt_select_fallback_models("主模型", MODELS)
    assert len(result) == 5
    assert result == ["alpha", "beta", "gamma", "delta", "epsilon"]


def test_variant_syntax(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "gpt-4o[max]")
    result = prompt_select_fallback_models("主模型", MODELS)
    assert result == [{"model": "gpt-4o", "variant": "max"}]


def test_mixed_numbers_and_names(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "1,claude-opus,3")
    result = prompt_select_fallback_models("主模型", MODELS)
    assert result == ["alpha", "claude-opus", "gamma"]


def test_invalid_number_skipped(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "1,99,3")
    result = prompt_select_fallback_models("主模型", MODELS)
    assert result == ["alpha", "gamma"]


def test_current_displayed(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "")
    prompt_select_fallback_models("主模型", MODELS, current=["x", "y"])
    captured = capsys.readouterr()
    assert "x, y" in captured.out


def test_current_dict_variant_displayed(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "")
    prompt_select_fallback_models(
        "主模型", MODELS,
        current=[{"model": "gpt-4o", "variant": "max"}],
    )
    captured = capsys.readouterr()
    assert "gpt-4o[max]" in captured.out
