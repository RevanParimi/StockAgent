"""
Control lane (the "duel") — Step 10 of run_daily_review.

Covers docs/superpowers/specs/2026-06-12-monthly-scorecard-baseline-duel-design.md
section 2.3:
  - Scoring fills the right (and only the right) ControlLog entry.
  - Prediction is appended for the next trading day, made_on == review_date.
  - Month-boundary rollover writes the prediction to the NEXT month's log.
  - LLM failure: scoring still applies, no new entry, no exception.
  - Invalid LLM direction: no entry appended.
  - Flag gating is tested at the daily_review call-site (see
    test_daily_review_dossier.py) — run_control_lane_step itself has no flag
    check (the gate lives in daily_review.run_daily_review).
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from backend.shared.schemas.scorecard import ControlPrediction, ControlLog
from core.intelligence.rl.agents.control_lane import run_control_lane_step
from core.intelligence.rl.stores.prediction_store import PredictionStore


TICKER = "TESTC"
SECTOR = "automobile"


def _store(tmp_path) -> PredictionStore:
    return PredictionStore(TICKER, sector=SECTOR, base_dir=tmp_path)


def _seed_log(store: PredictionStore, cycle_id: str, entries: list[ControlPrediction]) -> None:
    log = ControlLog(ticker=TICKER, sector=SECTOR, cycle_id=cycle_id, entries=entries)
    store.save_control_log(log)


def _patch_llm(monkeypatch, payload: dict | str, model: str = "test-model"):
    """Monkeypatch core.intelligence.rl.agents.control_lane._call_llm."""
    import core.intelligence.rl.agents.control_lane as cl

    raw = payload if isinstance(payload, str) else json.dumps(payload)

    def fake_call_llm(system_prompt, user_prompt):
        return raw, model

    monkeypatch.setattr(cl, "_call_llm", fake_call_llm)


# ---------------------------------------------------------------------------
# (a) Scoring fills the right entry
# ---------------------------------------------------------------------------

def test_scoring_fills_correct_for_up(tmp_path, monkeypatch):
    store = _store(tmp_path)
    cycle_id = store.current_cycle_id()
    review_date = date(2026, 6, 10)

    _seed_log(store, cycle_id, [
        ControlPrediction(date="2026-06-10", made_on="2026-06-09",
                           predicted_direction="UP", confidence=0.6, model="m"),
        # not-yet-due entry for a later date — must remain untouched
        ControlPrediction(date="2026-06-11", made_on="2026-06-10",
                           predicted_direction="DOWN", confidence=0.5, model="m"),
    ])

    _patch_llm(monkeypatch, {
        "direction": "FLAT", "confidence": 0.5, "predicted_close": None, "rationale": "r",
    })

    run_control_lane_step(
        store, TICKER, SECTOR, review_date,
        actual_close=105.0, actual_direction="UP", market_context="ctx",
    )

    log = store.load_control_log(cycle_id)
    scored = next(e for e in log.entries if e.date == "2026-06-10")
    assert scored.actual_direction == "UP"
    assert scored.correct is True

    untouched = next(e for e in log.entries if e.date == "2026-06-11")
    assert untouched.correct is None
    assert untouched.actual_direction == ""


def test_scoring_fills_correct_for_down_mismatch(tmp_path, monkeypatch):
    store = _store(tmp_path)
    cycle_id = store.current_cycle_id()
    review_date = date(2026, 6, 10)

    _seed_log(store, cycle_id, [
        ControlPrediction(date="2026-06-10", made_on="2026-06-09",
                           predicted_direction="DOWN", confidence=0.6, model="m"),
    ])

    _patch_llm(monkeypatch, {
        "direction": "FLAT", "confidence": 0.5, "predicted_close": None, "rationale": "r",
    })

    run_control_lane_step(
        store, TICKER, SECTOR, review_date,
        actual_close=105.0, actual_direction="UP", market_context="ctx",
    )

    log = store.load_control_log(cycle_id)
    scored = next(e for e in log.entries if e.date == "2026-06-10")
    assert scored.actual_direction == "UP"
    assert scored.correct is False


# ---------------------------------------------------------------------------
# (b) Prediction appended with date == next trading day, made_on == review_date
# ---------------------------------------------------------------------------

def test_prediction_appended_for_next_trading_day(tmp_path, monkeypatch):
    store = _store(tmp_path)
    cycle_id = store.current_cycle_id()
    review_date = date(2026, 6, 10)  # Wednesday -> next trading day = Thursday 06-11

    _patch_llm(monkeypatch, {
        "direction": "UP", "confidence": 0.7, "predicted_close": 110.5,
        "rationale": "Momentum continues.",
    }, model="control-model")

    run_control_lane_step(
        store, TICKER, SECTOR, review_date,
        actual_close=105.0, actual_direction="UP", market_context="ctx",
    )

    log = store.load_control_log(cycle_id)
    new_entry = next(e for e in log.entries if e.date == "2026-06-11")
    assert new_entry.made_on == "2026-06-10"
    assert new_entry.predicted_direction == "UP"
    assert new_entry.confidence == pytest.approx(0.7)
    assert new_entry.predicted_close == pytest.approx(110.5)
    assert new_entry.rationale == "Momentum continues."
    assert new_entry.model == "control-model"
    assert new_entry.correct is None


def test_rationale_truncated_to_200_chars(tmp_path, monkeypatch):
    store = _store(tmp_path)
    cycle_id = store.current_cycle_id()
    review_date = date(2026, 6, 10)

    long_rationale = "x" * 500
    _patch_llm(monkeypatch, {
        "direction": "FLAT", "confidence": 1.5, "predicted_close": None,
        "rationale": long_rationale,
    })

    run_control_lane_step(
        store, TICKER, SECTOR, review_date,
        actual_close=105.0, actual_direction="UP", market_context="ctx",
    )

    log = store.load_control_log(cycle_id)
    new_entry = next(e for e in log.entries if e.date == "2026-06-11")
    assert len(new_entry.rationale) == 200
    # confidence clamped to 1.0
    assert new_entry.confidence == 1.0


# ---------------------------------------------------------------------------
# (c) Month-boundary: prediction lands in NEXT month's control log file
# ---------------------------------------------------------------------------

def test_month_boundary_writes_to_next_month_log(tmp_path, monkeypatch):
    store = _store(tmp_path)
    review_date = date(2026, 5, 29)  # last trading day of May -> next = 2026-06-01

    # Force current_cycle_id() to the review month so scoring looks in the
    # right place, independent of the real "today" the test runs on.
    monkeypatch.setattr(store, "current_cycle_id", lambda: f"{TICKER}_2026-05")

    _patch_llm(monkeypatch, {
        "direction": "DOWN", "confidence": 0.4, "predicted_close": 99.0,
        "rationale": "Month-end profit booking expected.",
    }, model="control-model")

    run_control_lane_step(
        store, TICKER, SECTOR, review_date,
        actual_close=100.0, actual_direction="UP", market_context="ctx",
    )

    # May log has no entries to score (none seeded) — should remain empty/unscored.
    may_log = store.load_control_log(f"{TICKER}_2026-05")
    assert all(e.date != "2026-06-01" for e in may_log.entries)

    # June log gets the new prediction.
    june_log = store.load_control_log(f"{TICKER}_2026-06")
    new_entry = next(e for e in june_log.entries if e.date == "2026-06-01")
    assert new_entry.made_on == "2026-05-29"
    assert new_entry.predicted_direction == "DOWN"

    # File on disk: TESTC_2026-06_control_log.json
    expected_path = store._control_log_path("TESTC_2026-06")
    assert expected_path.exists()


# ---------------------------------------------------------------------------
# (d) LLM failure -> scoring still applied, no new entry, no exception
# ---------------------------------------------------------------------------

def test_llm_failure_scoring_still_applied(tmp_path, monkeypatch):
    store = _store(tmp_path)
    cycle_id = store.current_cycle_id()
    review_date = date(2026, 6, 10)

    _seed_log(store, cycle_id, [
        ControlPrediction(date="2026-06-10", made_on="2026-06-09",
                           predicted_direction="UP", confidence=0.6, model="m"),
    ])

    import core.intelligence.rl.agents.control_lane as cl

    def boom(system_prompt, user_prompt):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(cl, "_call_llm", boom)

    # Must not raise.
    run_control_lane_step(
        store, TICKER, SECTOR, review_date,
        actual_close=105.0, actual_direction="UP", market_context="ctx",
    )

    log = store.load_control_log(cycle_id)
    scored = next(e for e in log.entries if e.date == "2026-06-10")
    assert scored.correct is True  # scoring half succeeded

    # No new entry for the next trading day.
    assert all(e.date != "2026-06-11" for e in log.entries)


# ---------------------------------------------------------------------------
# (e) Invalid LLM direction -> no entry appended
# ---------------------------------------------------------------------------

def test_invalid_direction_discarded(tmp_path, monkeypatch):
    store = _store(tmp_path)
    cycle_id = store.current_cycle_id()
    review_date = date(2026, 6, 10)

    _seed_log(store, cycle_id, [
        ControlPrediction(date="2026-06-10", made_on="2026-06-09",
                           predicted_direction="UP", confidence=0.6, model="m"),
    ])

    _patch_llm(monkeypatch, {
        "direction": "SIDEWAYS", "confidence": 0.5, "predicted_close": None, "rationale": "r",
    })

    run_control_lane_step(
        store, TICKER, SECTOR, review_date,
        actual_close=105.0, actual_direction="UP", market_context="ctx",
    )

    log = store.load_control_log(cycle_id)
    # Scoring still applied.
    scored = next(e for e in log.entries if e.date == "2026-06-10")
    assert scored.correct is True

    # No new entry for the next trading day.
    assert all(e.date != "2026-06-11" for e in log.entries)


# ---------------------------------------------------------------------------
# (f) Flag off — gate lives in daily_review.run_daily_review.
#
# run_control_lane_step itself does not check RL_CONTROL_LANE_ENABLED (the
# spec gates the call-site, Step 10, on the flag). This is verified at the
# daily_review level in test_daily_review_dossier.py via monkeypatching
# run_control_lane_step and asserting it is/isn't called depending on the
# flag. See that file for the gate test.
# ---------------------------------------------------------------------------
