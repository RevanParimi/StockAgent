# tests/unit/intelligence/rl/test_hard_bind_daily_review.py
"""AUD-117 Binding 2 — daily_review grades direction_correct against the FRESH
daily verdict (the threshold verdict under Binding 1) from the same orchestrator
re-run, not the frozen month-start predicted_verdict. Skip-rerun days keep the
frozen fallback. Flag OFF => unchanged."""
from __future__ import annotations

from types import SimpleNamespace

from tests.unit.intelligence.rl.test_shock_path import (
    TICKER, SECTOR, REVIEW_DATE,
    _patch_common, _setup_store, _fb_output,
)


def _stub_fresh_report(dr, monkeypatch, verdict):
    """Replace _run_todays_agent_scores with a stub that returns fixed scores AND
    populates the capture out-param with a fresh report carrying `verdict`
    (mimics orchestrator.analyse without a real LLM run)."""
    def _stub(*a, **k):
        cap = k.get("capture")
        if cap is not None:
            cap["report"] = SimpleNamespace(verdict=verdict)
        return {"risk_macro": 0.5, "sales_demand": 0.5}
    monkeypatch.setattr(dr, "_run_todays_agent_scores", _stub)


def _quiet_feedback(dr, monkeypatch):
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run",
                        lambda self, fb_input, ledger: _fb_output("magnitude"))
    monkeypatch.setattr(dr, "regenerate_envelope", lambda **kw: None)
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: None)


def test_flag_on_grades_against_fresh_bound_verdict(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr
    store, cycle_id = _setup_store(tmp_path, verdict="BUY")       # frozen = BUY
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)   # -2% => DOWN
    _quiet_feedback(dr, monkeypatch)
    monkeypatch.setattr(dr.settings, "RL_HARD_BIND_VERDICT_ENABLED", True)
    _stub_fresh_report(dr, monkeypatch, verdict="STRONG SELL")    # correct on DOWN

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["direction_correct"] is True                  # graded on STRONG SELL
    entry = store.load_feedback_log(cycle_id).get_entry(REVIEW_DATE.isoformat())
    assert entry.graded_verdict == "STRONG SELL"
    assert entry.direction_correct is True
    assert entry.predicted_verdict == "BUY"                      # frozen thesis NOT rewritten


def test_flag_off_grades_against_frozen_verdict(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr
    store, cycle_id = _setup_store(tmp_path, verdict="BUY")
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)   # DOWN
    _quiet_feedback(dr, monkeypatch)
    monkeypatch.setattr(dr.settings, "RL_HARD_BIND_VERDICT_ENABLED", False)
    _stub_fresh_report(dr, monkeypatch, verdict="STRONG SELL")    # would flip it IF read

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["direction_correct"] is False                 # frozen BUY vs DOWN = wrong
    entry = store.load_feedback_log(cycle_id).get_entry(REVIEW_DATE.isoformat())
    assert entry.graded_verdict == "BUY"                         # == frozen predicted_verdict


def test_flag_on_skip_rerun_falls_back_to_frozen(tmp_path, monkeypatch):
    """Direction correct + tiny error => orchestrator re-run skipped => no fresh
    report => grading falls back to the frozen envelope verdict."""
    import core.intelligence.rl.workflows.daily_review as dr
    store, cycle_id = _setup_store(tmp_path, verdict="BUY")
    _patch_common(dr, monkeypatch, tmp_path, actual_close=101.0)  # +1% => UP => BUY correct
    _quiet_feedback(dr, monkeypatch)
    monkeypatch.setattr(dr.settings, "RL_HARD_BIND_VERDICT_ENABLED", True)
    monkeypatch.setattr(dr.settings, "RL_AGENT_RERUN_THRESHOLD_PCT", 5.0)  # |1%|<5% => skip
    _stub_fresh_report(dr, monkeypatch, verdict="STRONG SELL")    # never consulted on skip

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["direction_correct"] is True                  # frozen BUY vs UP = correct
    entry = store.load_feedback_log(cycle_id).get_entry(REVIEW_DATE.isoformat())
    assert entry.graded_verdict == "BUY"                         # frozen fallback, no re-run
