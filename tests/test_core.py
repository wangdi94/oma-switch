"""Tests for core functions in oma_switch.cli.

Covers: load_config, save_config, load_profile_json, check_template_profile,
merge_to_oma_config.
"""

import sys
import json
import pytest
from pathlib import Path

sys.path.insert(0, "src")

import oma_switch.cli as cli


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    """Patch Path.home() AND all module-level config constants to a tmp directory.

    The conftest version only patches Path.home(), but cli.py's module-level
    constants (CONFIG_DIR, CONFIG_FILE, OMA_CONFIG, ...) are already evaluated
    at import time. This fixture patches them too.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    # Create directory structure
    fake_config_dir = fake_home / ".config" / "oma-switch"
    fake_profiles_dir = fake_config_dir / "profiles"
    fake_opencode_dir = fake_home / ".config" / "opencode"
    fake_config_dir.mkdir(parents=True)
    fake_profiles_dir.mkdir(parents=True)
    fake_opencode_dir.mkdir(parents=True)

    # Patch module-level constants
    monkeypatch.setattr(cli, "CONFIG_DIR", fake_config_dir)
    monkeypatch.setattr(cli, "PROFILES_DIR", fake_profiles_dir)
    monkeypatch.setattr(cli, "CONFIG_FILE", fake_config_dir / "config.json")
    monkeypatch.setattr(cli, "TEMPLATE_FILE", fake_config_dir / "template.json")
    monkeypatch.setattr(cli, "OMA_CONFIG", fake_opencode_dir / "oh-my-openagent.json")
    monkeypatch.setattr(cli, "OPENCODE_DIR", fake_opencode_dir)
    monkeypatch.setattr(cli, "DCP_CONFIG_FILE", fake_opencode_dir / "dcp.jsonc")

    return fake_home


# ── Helpers ────────────────────────────────────────────────────────

SMALL_TEMPLATE = {
    "test_group": {
        ("agents", "sisyphus"),
        ("agents", "oracle"),
    },
}


def _make_valid_profile(
    main_model="gpt-4",
    strong_model="claude-3",
    mid_model="gpt-3.5",
    weak_model="gpt-3.5-turbo",
    multi_model="gpt-4-vision",
):
    """Build a profile that passes check_template_profile with DEFAULT_TEMPLATE_GROUPS."""
    return {
        "agents": {
            "sisyphus": {"model": main_model},
            "hephaestus": {"model": main_model},
            "prometheus": {"model": main_model},
            "atlas": {"model": main_model},
            "oracle": {"model": strong_model},
            "metis": {"model": strong_model},
            "momus": {"model": strong_model},
            "plan": {"model": strong_model},
            "sisyphus-junior": {"model": mid_model},
            "explore": {"model": weak_model},
            "librarian": {"model": weak_model},
            "multimodal-looker": {"model": multi_model},
        },
        "categories": {
            "ultrabrain": {"model": strong_model},
            "artistry": {"model": strong_model},
            "deep": {"model": mid_model},
            "visual-engineering": {"model": mid_model},
            "writing": {"model": mid_model},
            "unspecified-high": {"model": mid_model},
            "quick": {"model": weak_model},
            "unspecified-low": {"model": weak_model},
        },
    }


# ── load_config / save_config ─────────────────────────────────────


def test_load_config_returns_default_when_missing(isolated_config_dir):
    """load_config returns default structure when CONFIG_FILE doesn't exist."""
    result = cli.load_config()
    assert result == {"current": None, "profiles": {}}


def test_save_and_load_config_roundtrip(isolated_config_dir):
    """save_config then load_config returns the same data (plus current_fallback default)."""
    data = {
        "current": "test-profile",
        "profiles": {
            "test-profile": {"created": "2026-01-01", "description": "test"}
        },
    }
    cli.save_config(data)
    loaded = cli.load_config()
    # load_config adds current_fallback default via setdefault
    expected = {**data, "current_fallback": ""}
    assert loaded == expected


def test_save_config_creates_file(isolated_config_dir):
    """save_config creates the config file on disk."""
    assert not cli.CONFIG_FILE.exists()
    cli.save_config({"current": None, "profiles": {}})
    assert cli.CONFIG_FILE.exists()
    content = json.loads(cli.CONFIG_FILE.read_text(encoding="utf-8"))
    assert content == {"current": None, "profiles": {}}


def test_load_config_corrupted_returns_default(isolated_config_dir):
    """load_config returns default when file contains invalid JSON."""
    cli.CONFIG_FILE.write_text("NOT_JSON{{{", encoding="utf-8")
    result = cli.load_config()
    assert result == {"current": None, "profiles": {}}


# ── load_profile_json ─────────────────────────────────────────────


def test_load_profile_json_missing_file(isolated_config_dir):
    """load_profile_json returns None for a nonexistent file."""
    assert cli.load_profile_json("nonexistent") is None


def test_load_profile_json_invalid_json(isolated_config_dir):
    """load_profile_json returns None for invalid JSON content."""
    path = cli.PROFILES_DIR / "bad.json"
    path.write_text("{invalid json!!!", encoding="utf-8")
    assert cli.load_profile_json("bad") is None


def test_load_profile_json_valid(isolated_config_dir):
    """load_profile_json returns parsed dict for valid JSON."""
    data = {"agents": {"sisyphus": {"model": "gpt-4"}}, "categories": {}}
    path = cli.PROFILES_DIR / "good.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert cli.load_profile_json("good") == data


# ── check_template_profile ────────────────────────────────────────


def test_check_template_profile_valid(isolated_config_dir):
    """Valid profile matching small template returns True."""
    profile = {
        "agents": {
            "sisyphus": {"model": "gpt-4"},
            "oracle": {"model": "gpt-4"},
        },
    }
    assert cli.check_template_profile(profile, template=SMALL_TEMPLATE) is True


def test_check_template_profile_missing_entry(isolated_config_dir):
    """Profile missing a required template entry returns False."""
    profile = {"agents": {"sisyphus": {"model": "gpt-4"}}}  # missing oracle
    assert cli.check_template_profile(profile, template=SMALL_TEMPLATE) is False


def test_check_template_profile_mixed_models(isolated_config_dir):
    """Profile with different models in same group returns False."""
    profile = {
        "agents": {
            "sisyphus": {"model": "gpt-4"},
            "oracle": {"model": "claude-3"},
        },
    }
    assert cli.check_template_profile(profile, template=SMALL_TEMPLATE) is False


def test_check_template_profile_not_dict(isolated_config_dir):
    """Non-dict profile argument returns False."""
    assert cli.check_template_profile("not a dict", template=SMALL_TEMPLATE) is False  # type: ignore[arg-type]


def test_check_template_profile_valid_full_template(isolated_config_dir):
    """Full profile matching DEFAULT_TEMPLATE_GROUPS returns True."""
    profile = _make_valid_profile()
    assert cli.check_template_profile(profile) is True


# ── merge_to_oma_config ──────────────────────────────────────────


def test_merge_to_oma_config_preserves_existing_fields(isolated_config_dir):
    """merge_to_oma_config preserves $schema, background, permissions."""
    existing = {
        "$schema": "http://example.com/schema.json",
        "background": "some-bg",
        "permissions": {"allow": ["*"]},
        "agents": {"old_agent": {"model": "old"}},
        "categories": {"old_cat": {"model": "old"}},
    }
    cli.OMA_CONFIG.write_text(json.dumps(existing), encoding="utf-8")

    source = {
        "agents": {"new_agent": {"model": "new"}},
        "categories": {"new_cat": {"model": "new"}},
    }
    cli.merge_to_oma_config(source)

    result = json.loads(cli.OMA_CONFIG.read_text(encoding="utf-8"))
    assert result["$schema"] == "http://example.com/schema.json"
    assert result["background"] == "some-bg"
    assert result["permissions"] == {"allow": ["*"]}
    assert result["agents"] == {"new_agent": {"model": "new"}}
    assert result["categories"] == {"new_cat": {"model": "new"}}


def test_merge_to_oma_config_creates_if_missing(isolated_config_dir):
    """merge_to_oma_config creates OMA_CONFIG when it doesn't exist."""
    assert not cli.OMA_CONFIG.exists()
    source = {"agents": {"a": {"model": "m"}}, "categories": {"c": {"model": "m"}}}
    cli.merge_to_oma_config(source)
    result = json.loads(cli.OMA_CONFIG.read_text(encoding="utf-8"))
    assert result["agents"] == {"a": {"model": "m"}}
    assert result["categories"] == {"c": {"model": "m"}}


def test_merge_to_oma_config_only_replaces_agents_categories(isolated_config_dir):
    """merge_to_oma_config only replaces agents/categories, keeps other keys."""
    existing = {
        "settings": {"key": "val"},
        "custom_field": [1, 2, 3],
        "agents": {},
        "categories": {},
    }
    cli.OMA_CONFIG.write_text(json.dumps(existing), encoding="utf-8")

    source = {"agents": {"x": {"model": "y"}}}
    cli.merge_to_oma_config(source)

    result = json.loads(cli.OMA_CONFIG.read_text(encoding="utf-8"))
    assert result["settings"] == {"key": "val"}
    assert result["custom_field"] == [1, 2, 3]
    assert result["agents"] == {"x": {"model": "y"}}
    # categories unchanged (source didn't have it)
    assert result["categories"] == {}
