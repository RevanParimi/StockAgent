import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_load_profile_missing_returns_defaults(tmp_path):
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import load_profile
        profile = load_profile("nonexistent-session")
    assert profile["detected_tier"] == "active"
    assert profile["sessions_seen"] == 0
    assert profile["topics_seen"] == []


def test_save_and_reload_profile(tmp_path):
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import save_profile, load_profile
        save_profile("sess-1", tier="expert", tier_confidence=0.9, topics=["Nifty", "VIX"])
        profile = load_profile("sess-1")
    assert profile["detected_tier"] == "expert"
    assert profile["tier_confidence"] == 0.9
    assert "Nifty" in profile["topics_seen"]
    assert profile["sessions_seen"] == 1


def test_save_increments_sessions(tmp_path):
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import save_profile, load_profile
        save_profile("sess-2", tier="casual", tier_confidence=0.7, topics=[])
        save_profile("sess-2", tier="active", tier_confidence=0.8, topics=["Sensex"])
        profile = load_profile("sess-2")
    assert profile["sessions_seen"] == 2


def test_save_merges_topics(tmp_path):
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import save_profile, load_profile
        save_profile("sess-3", tier="active", tier_confidence=0.7, topics=["Nifty"])
        save_profile("sess-3", tier="active", tier_confidence=0.7, topics=["Sensex"])
        profile = load_profile("sess-3")
    assert "Nifty" in profile["topics_seen"]
    assert "Sensex" in profile["topics_seen"]


def test_corrupt_profile_returns_defaults(tmp_path):
    prof_path = tmp_path / "bad-session.json"
    prof_path.write_text("not valid json")
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import load_profile
        profile = load_profile("bad-session")
    assert profile["detected_tier"] == "active"
