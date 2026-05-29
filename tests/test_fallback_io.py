"""
Tests for fallback I/O functions in cli.py.

Covers round-trip save/load, missing files, empty directories,
listing, deletion, and invalid JSON handling.
"""

import pytest
from pathlib import Path
from oma_switch.cli import (
    FALLBACKS_DIR,
    get_fallback_path,
    load_fallback_json,
    save_fallback_json,
    list_fallback_names,
    delete_fallback_json,
)


@pytest.fixture(autouse=True)
def _patch_fallbacks_dir(tmp_path, monkeypatch):
    """Point FALLBACKS_DIR to a tmp directory for all tests."""
    fake_dir = tmp_path / "fallbacks"
    fake_dir.mkdir()
    monkeypatch.setattr("oma_switch.cli.FALLBACKS_DIR", fake_dir)
    monkeypatch.setattr("oma_switch.config_io.FALLBACKS_DIR", fake_dir)
    return fake_dir


def test_round_trip(sample_fallback_data):
    """save then load returns same data."""
    save_fallback_json("test-config", sample_fallback_data)
    loaded = load_fallback_json("test-config")
    assert loaded == sample_fallback_data


def test_missing_file():
    """load nonexistent name returns None."""
    result = load_fallback_json("nonexistent")
    assert result is None


def test_empty_dir():
    """list_fallback_names returns [] for empty dir."""
    names = list_fallback_names()
    assert names == []


def test_list_after_save():
    """save 2 fallbacks, list returns both names (sorted)."""
    save_fallback_json("beta", {"data": "b"})
    save_fallback_json("alpha", {"data": "a"})
    names = list_fallback_names()
    assert names == ["alpha", "beta"]


def test_delete_existing():
    """delete returns True, file gone."""
    save_fallback_json("to-delete", {"data": "x"})
    result = delete_fallback_json("to-delete")
    assert result is True
    assert load_fallback_json("to-delete") is None


def test_delete_nonexistent():
    """delete returns False."""
    result = delete_fallback_json("nonexistent")
    assert result is False


def test_invalid_json(tmp_path):
    """load file with bad JSON returns None."""
    # Write directly to the patched FALLBACKS_DIR
    fake_dir = tmp_path / "fallbacks"
    bad_file = fake_dir / "bad.json"
    bad_file.write_text("{invalid json content", encoding="utf-8")
    result = load_fallback_json("bad")
    assert result is None
