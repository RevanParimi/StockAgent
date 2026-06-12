"""
tests/unit/intelligence/regime/test_sticky_regime.py
=====================================================
Living Envelope (RL Phase 2.5) — Component 1: Sticky regime hysteresis.

Covers core/intelligence/regime/state.py:
  - enter-immediately on a severe detection (RISK_OFF / MACRO_CRISIS)
  - persistence across calls (state file written + reloaded)
  - exit after exactly RL_REGIME_CALM_DAYS consecutive milder detections
  - calm_streak resets on severe re-detection
  - same-day repeat calls are idempotent (no double-increment)
  - corrupt state file -> fresh start from detected label
  - RL_REGIME_STICKY_ENABLED == False -> passthrough, no disk IO at all
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.intelligence.regime.state import RegimeState, update_sticky_regime


@pytest.fixture(autouse=True)
def _redirect_state_file(tmp_path, monkeypatch):
    """Redirect settings.PREDICTION_DATA_DIR to tmp_path for every test."""
    monkeypatch.setattr("core.config.settings.PREDICTION_DATA_DIR", str(tmp_path))
    return tmp_path


def _state_file(tmp_path: Path) -> Path:
    return tmp_path / "_regime_state.json"


# ---------------------------------------------------------------------------
# Enter immediately
# ---------------------------------------------------------------------------

def test_enters_macro_crisis_immediately(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", True)

    state = update_sticky_regime("MACRO_CRISIS", "2026-06-01")

    assert state == RegimeState(label="MACRO_CRISIS", since="2026-06-01", calm_streak=0)


def test_enters_risk_off_immediately_from_normal(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", True)

    # Day 1: NORMAL baseline
    update_sticky_regime("NORMAL", "2026-06-01")
    # Day 2: RISK_OFF detected -> enter immediately
    state = update_sticky_regime("RISK_OFF", "2026-06-02")

    assert state == RegimeState(label="RISK_OFF", since="2026-06-02", calm_streak=0)


# ---------------------------------------------------------------------------
# Persistence across calls
# ---------------------------------------------------------------------------

def test_state_persists_across_calls(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", True)
    tmp_path = _redirect_state_file

    update_sticky_regime("MACRO_CRISIS", "2026-06-01")
    assert _state_file(tmp_path).exists()

    # A second, independent call (simulating a new process) should read the
    # persisted sticky label rather than starting fresh.
    state = update_sticky_regime("NORMAL", "2026-06-02")

    assert state.label == "MACRO_CRISIS"  # still sticky — only 1 calm day so far
    assert state.calm_streak == 1


# ---------------------------------------------------------------------------
# Exit after RL_REGIME_CALM_DAYS consecutive milder detections
# ---------------------------------------------------------------------------

def test_exits_after_exactly_calm_days(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", True)
    monkeypatch.setattr("core.config.settings.RL_REGIME_CALM_DAYS", 3)

    # Enter MACRO_CRISIS
    update_sticky_regime("MACRO_CRISIS", "2026-06-01")

    # Calm day 1
    s1 = update_sticky_regime("NORMAL", "2026-06-02")
    assert s1.label == "MACRO_CRISIS"
    assert s1.calm_streak == 1

    # Calm day 2
    s2 = update_sticky_regime("NORMAL", "2026-06-03")
    assert s2.label == "MACRO_CRISIS"
    assert s2.calm_streak == 2

    # Calm day 3 -> exits to milder label
    s3 = update_sticky_regime("NORMAL", "2026-06-04")
    assert s3.label == "NORMAL"
    assert s3.calm_streak == 0
    assert s3.since == "2026-06-04"


# ---------------------------------------------------------------------------
# Streak resets on severe re-detection
# ---------------------------------------------------------------------------

def test_calm_streak_resets_on_severe_redetection(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", True)
    monkeypatch.setattr("core.config.settings.RL_REGIME_CALM_DAYS", 3)

    update_sticky_regime("MACRO_CRISIS", "2026-06-01")
    s1 = update_sticky_regime("NORMAL", "2026-06-02")
    assert s1.calm_streak == 1

    s2 = update_sticky_regime("NORMAL", "2026-06-03")
    assert s2.calm_streak == 2

    # Severe re-detection resets the streak
    s3 = update_sticky_regime("MACRO_CRISIS", "2026-06-04")
    assert s3.label == "MACRO_CRISIS"
    assert s3.calm_streak == 0

    # Calm streak must restart from zero afterwards
    s4 = update_sticky_regime("NORMAL", "2026-06-05")
    assert s4.label == "MACRO_CRISIS"
    assert s4.calm_streak == 1


def test_risk_off_to_macro_crisis_escalation(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", True)

    update_sticky_regime("RISK_OFF", "2026-06-01")
    # Escalation to MACRO_CRISIS should enter immediately, resetting since/streak
    state = update_sticky_regime("MACRO_CRISIS", "2026-06-02")

    assert state == RegimeState(label="MACRO_CRISIS", since="2026-06-02", calm_streak=0)


# ---------------------------------------------------------------------------
# Same-day idempotence
# ---------------------------------------------------------------------------

def test_same_day_repeat_calls_are_idempotent(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", True)
    monkeypatch.setattr("core.config.settings.RL_REGIME_CALM_DAYS", 3)

    update_sticky_regime("MACRO_CRISIS", "2026-06-01")

    s1 = update_sticky_regime("NORMAL", "2026-06-02")
    assert s1.calm_streak == 1

    # Repeat call for the SAME date must not increment calm_streak again
    s2 = update_sticky_regime("NORMAL", "2026-06-02")
    assert s2.calm_streak == 1
    assert s2.label == "MACRO_CRISIS"

    s3 = update_sticky_regime("NORMAL", "2026-06-02")
    assert s3.calm_streak == 1


# ---------------------------------------------------------------------------
# Corrupt / missing state file
# ---------------------------------------------------------------------------

def test_corrupt_state_file_recovers_fresh(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", True)
    tmp_path = _redirect_state_file

    state_file = _state_file(tmp_path)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{not valid json", encoding="utf-8")

    state = update_sticky_regime("RISK_OFF", "2026-06-01")

    assert state == RegimeState(label="RISK_OFF", since="2026-06-01", calm_streak=0)


def test_missing_state_file_starts_fresh(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", True)
    tmp_path = _redirect_state_file

    assert not _state_file(tmp_path).exists()

    state = update_sticky_regime("NORMAL", "2026-06-01")

    assert state == RegimeState(label="NORMAL", since="2026-06-01", calm_streak=0)
    assert _state_file(tmp_path).exists()


# ---------------------------------------------------------------------------
# Flag off -> passthrough, no disk IO
# ---------------------------------------------------------------------------

def test_flag_off_passthrough_no_disk_io(_redirect_state_file, monkeypatch):
    monkeypatch.setattr("core.config.settings.RL_REGIME_STICKY_ENABLED", False)
    tmp_path = _redirect_state_file

    state = update_sticky_regime("MACRO_CRISIS", "2026-06-01")

    assert state == RegimeState(label="MACRO_CRISIS", since="2026-06-01", calm_streak=0)
    assert not _state_file(tmp_path).exists()

    # Repeated calls also never create the file
    update_sticky_regime("RISK_OFF", "2026-06-02")
    assert not _state_file(tmp_path).exists()
