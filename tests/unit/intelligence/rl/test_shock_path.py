"""
tests/unit/intelligence/rl/test_shock_path.py
================================================
Living Envelope (RL Phase 2.5), Component 3 — daily_review trigger wiring.

Covers docs/superpowers/specs/2026-06-13-living-envelope-design.md §4.2/§4.3:
  - external_shock trigger: FeedbackAgent miss_type == "external_shock" AND
    direction wrong (post rate-cap) -> regenerate_envelope(trigger="external_shock").
  - thesis_break trigger: ThesisReviewer ran and
    horizon_confidence_multiplier <= RL_REFORECAST_THESIS_MULT_THRESHOLD
    -> regenerate_envelope(trigger="thesis_break").
  - regime_flip trigger: sticky regime TRANSITIONED into MACRO_CRISIS today
    -> regenerate_envelope(trigger="regime_flip").
  - 20% external_shock rate-cap reclassification (pinned) -> reclassified
    miss_type no longer satisfies the external_shock trigger condition.
  - On successful regeneration, Step 7 (_revise_remaining_forecasts) is
    skipped; on regenerate_envelope() returning None, Step 7 runs as usual.
  - RL_REFORECAST_ENABLED=False -> trigger block never calls
    regenerate_envelope, regardless of conditions.
  - An exception inside the trigger block never crashes run_daily_review.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from core.schemas.feedback import (
    DailyForecast,
    FeedbackEntry,
    MissAnalysis,
    PredictionEnvelope,
    RevisedContext,
)
from core.intelligence.rl.stores.prediction_store import PredictionStore


TICKER = "TESTSHOCK"
SECTOR = "automobile"
REVIEW_DATE = date(2026, 6, 10)
DATE_STR = REVIEW_DATE.isoformat()


def _make_envelope(ticker: str = TICKER, verdict: str = "BUY") -> PredictionEnvelope:
    """2-day BUY-verdict envelope: day 1 = review date, day 2 = "tomorrow"."""
    return PredictionEnvelope(
        ticker=ticker, sector=SECTOR, cycle_id=f"{ticker}_2026-06",
        generated_at="2026-06-01T00:00:00", base_close=100.0,
        daily_forecasts=[
            DailyForecast(day=1, date="2026-06-10", predicted_close=100.0,
                           predicted_verdict=verdict,
                           predicted_agent_scores={"risk_macro": 0.5, "sales_demand": 0.5},
                           confidence=0.5),
            DailyForecast(day=2, date="2026-06-11", predicted_close=101.0,
                           predicted_verdict=verdict,
                           predicted_agent_scores={"risk_macro": 0.5, "sales_demand": 0.5},
                           confidence=0.5),
        ],
    )


def _regenerated_envelope(ticker: str = TICKER) -> PredictionEnvelope:
    """What a successful regenerate_envelope() call would return."""
    env = _make_envelope(ticker)
    env.reforecast_count = 1
    return env


def _patch_common(dr, monkeypatch, tmp_path, actual_close: float = 98.0):
    """Common seam stack shared by all trigger tests.

    actual_close=98.0 (vs predicted_close=100.0 for the BUY day-1 forecast)
    => actual_direction="DOWN" => direction_correct=False.
    """
    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dr, "_fetch_actual_close", lambda t, d: actual_close)
    monkeypatch.setattr(dr, "get_price_history", lambda *a, **k: None)

    # When direction is wrong (the common case in these shock-path tests),
    # _should_skip_agent_rerun() is False and run_daily_review() would call
    # _run_todays_agent_scores() -> get_orchestrator(sector).analyse(ticker),
    # which makes real (slow) LLM calls across all 9 agents. Short-circuit it
    # with a fixed score dict so these tests stay fast and deterministic.
    monkeypatch.setattr(dr, "_run_todays_agent_scores", lambda *a, **k: {"risk_macro": 0.5, "sales_demand": 0.5})

    from core.schemas.feedback import RegimeSnapshot
    monkeypatch.setattr(dr.RegimeDetector, "detect", lambda self, d, s: RegimeSnapshot())

    import services.data.fetchers.news as news_mod
    monkeypatch.setattr(news_mod, "get_news_context", lambda *a, **k: "Quiet session.")

    import services.data.fetchers.nse_market as nse_mkt_mod
    monkeypatch.setattr(nse_mkt_mod, "get_nse_market_data", lambda *a, **k: {"error": "skipped"})

    from core.schemas.feedback import OffMarketSignals
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(
        offmarket_mod.OffMarketFetcher, "fetch_all",
        lambda self, t, d: OffMarketSignals(date=d, ticker=t),
    )

    import core.intelligence.rl.algorithms.factor_regime as factor_regime_mod
    monkeypatch.setattr(factor_regime_mod, "get_factor_regime", lambda *a, **k: None)

    from core.intelligence.rl.agents.dossier_curator import DossierCurator
    dossier_payload = {
        "event_tags_today": [], "new_observations": [],
        "signature_updates": [], "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    monkeypatch.setattr(DossierCurator, "_call_llm",
                         lambda self, *a, **k: json.dumps(dossier_payload))

    import core.intelligence.rl.agents.control_lane as control_lane_mod
    control_payload = json.dumps({
        "direction": "FLAT", "confidence": 0.5, "predicted_close": actual_close,
        "rationale": "Test control prediction.",
    })
    monkeypatch.setattr(
        control_lane_mod, "_call_llm",
        lambda *a, **k: (control_payload, "test-control-model"))


def _fb_output(miss_type: str, primary_miss_agent: str = "risk_macro"):
    from core.schemas.feedback import FeedbackAgentOutput
    return FeedbackAgentOutput(
        primary_miss_agent=primary_miss_agent,
        miss_type=miss_type,
        missed_factors=[], over_weighted_factors=[], agent_score_drift={},
        new_lessons=[],
        revised_context=RevisedContext(headline="Test.", horizon_confidence_adjustment=0.0),
    )


def _setup_store(tmp_path, ticker=TICKER, verdict="BUY"):
    store = PredictionStore(ticker, sector=SECTOR, base_dir=tmp_path)
    cycle_id = store.current_cycle_id()
    store.save_envelope(_make_envelope(ticker, verdict))
    return store, cycle_id


# ---------------------------------------------------------------------------
# external_shock trigger
# ---------------------------------------------------------------------------

def test_external_shock_trigger_fires_regenerate_envelope(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr

    store, cycle_id = _setup_store(tmp_path)
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", True)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: _fb_output("external_shock"))

    calls = []
    def _fake_regenerate(**kwargs):
        calls.append(kwargs)
        return _regenerated_envelope()
    monkeypatch.setattr(dr, "regenerate_envelope", _fake_regenerate)

    revise_calls = []
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: revise_calls.append(kw))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["status"] == "completed"
    assert len(calls) == 1
    assert calls[0]["trigger"] == "external_shock"
    assert calls[0]["ticker"] == TICKER
    assert calls[0]["sector"] == SECTOR
    assert calls[0]["review_date"] == REVIEW_DATE

    # Step 7 skipped on successful regeneration.
    assert revise_calls == []

    assert summary["reforecast_fired"] is True
    assert summary["reforecast_trigger"] == "external_shock"
    assert summary["reforecast_count"] == 1


# ---------------------------------------------------------------------------
# thesis_break trigger
# ---------------------------------------------------------------------------

def test_thesis_break_trigger_fires_regenerate_envelope(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr

    store, cycle_id = _setup_store(tmp_path)
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_THESIS_MULT_THRESHOLD", 0.5)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    # miss_type="direction_flip" (not external_shock) so external_shock
    # trigger does not preempt thesis_break.
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: _fb_output("direction_flip"))

    # Force ThesisReviewer to run and report a broken thesis.
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    from core.schemas.feedback import ThesisReview
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: True)
    monkeypatch.setattr(
        ThesisReviewer, "review",
        lambda self, **kw: ThesisReview(
            thesis_intact=False,
            horizon_confidence_multiplier=0.3,
            assumptions_invalidated=["demand assumption broke"],
        ),
    )

    calls = []
    def _fake_regenerate(**kwargs):
        calls.append(kwargs)
        return _regenerated_envelope()
    monkeypatch.setattr(dr, "regenerate_envelope", _fake_regenerate)

    revise_calls = []
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: revise_calls.append(kw))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["status"] == "completed"
    assert len(calls) == 1
    assert calls[0]["trigger"] == "thesis_break"
    assert revise_calls == []
    assert summary["reforecast_fired"] is True
    assert summary["reforecast_trigger"] == "thesis_break"


# ---------------------------------------------------------------------------
# regime_flip trigger
# ---------------------------------------------------------------------------

def test_regime_flip_trigger_fires_regenerate_envelope(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr

    store, cycle_id = _setup_store(tmp_path)
    # NEUTRAL-equivalent: use a small price move so direction_correct stays
    # True and neither external_shock nor thesis_break can preempt regime_flip.
    _patch_common(dr, monkeypatch, tmp_path, actual_close=100.1)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", True)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: _fb_output("magnitude"))

    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: False)

    # Sticky regime: prior=NORMAL, today's detection sticks to MACRO_CRISIS.
    from core.intelligence.regime.state import RegimeState
    monkeypatch.setattr(dr, "_read_state", lambda path: RegimeState(label="NORMAL", since="2026-06-01", calm_streak=0))
    monkeypatch.setattr(dr, "update_sticky_regime", lambda detected, today: RegimeState(label="MACRO_CRISIS", since=today, calm_streak=0))

    calls = []
    def _fake_regenerate(**kwargs):
        calls.append(kwargs)
        return _regenerated_envelope()
    monkeypatch.setattr(dr, "regenerate_envelope", _fake_regenerate)

    revise_calls = []
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: revise_calls.append(kw))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["status"] == "completed"
    assert len(calls) == 1
    assert calls[0]["trigger"] == "regime_flip"
    assert revise_calls == []
    assert summary["reforecast_fired"] is True
    assert summary["reforecast_trigger"] == "regime_flip"
    assert summary["regime_label"] == "MACRO_CRISIS"
    assert summary["regime_label_raw"] == "NORMAL"


def test_regime_flip_does_not_fire_when_no_prior_state(tmp_path, monkeypatch):
    """First-ever run (no persisted sticky-regime state) must NOT be treated
    as a transition into MACRO_CRISIS, even if today's sticky label is
    MACRO_CRISIS — there is no prior label to compare against."""
    import core.intelligence.rl.workflows.daily_review as dr

    store, cycle_id = _setup_store(tmp_path)
    _patch_common(dr, monkeypatch, tmp_path, actual_close=100.1)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", True)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: _fb_output("magnitude"))

    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: False)

    from core.intelligence.regime.state import RegimeState
    monkeypatch.setattr(dr, "_read_state", lambda path: None)
    monkeypatch.setattr(dr, "update_sticky_regime", lambda detected, today: RegimeState(label="MACRO_CRISIS", since=today, calm_streak=0))

    calls = []
    monkeypatch.setattr(dr, "regenerate_envelope", lambda **kwargs: calls.append(kwargs) or _regenerated_envelope())

    revise_calls = []
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: revise_calls.append(kw))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["status"] == "completed"
    assert calls == []
    assert summary["reforecast_fired"] is False
    assert summary["reforecast_trigger"] is None
    # Step 7 runs as usual since no trigger fired.
    assert len(revise_calls) == 1


# ---------------------------------------------------------------------------
# 20% external_shock rate-cap reclassification (pinned regression)
# ---------------------------------------------------------------------------

def test_rate_capped_external_shock_does_not_fire_trigger(tmp_path, monkeypatch):
    """When >20% of prior penalizable days were already classified
    external_shock, today's external_shock is reclassified to
    direction_flip BEFORE the trigger block runs — so the external_shock
    trigger condition (fb_output.miss_type == "external_shock") is no
    longer satisfied for today."""
    import core.intelligence.rl.workflows.daily_review as dr
    from core.schemas.feedback import DailyFeedbackLog, FeedbackEntry, MissAnalysis

    store, cycle_id = _setup_store(tmp_path)

    # Seed 5 prior entries, 2/5 = 40% already external_shock (> 20% cap).
    prior_entries = []
    for i, mt in enumerate(["external_shock", "external_shock", "magnitude", "magnitude", "magnitude"]):
        prior_entries.append(FeedbackEntry(
            day=i + 1, date=f"2026-06-{i+1:02d}",
            predicted_close=100.0, actual_close=100.0, price_error_pct=0.0,
            predicted_verdict="BUY", actual_direction="UP", direction_correct=True,
            miss_analysis=MissAnalysis(
                primary_miss_agent="risk_macro", miss_type=mt,
                missed_factors=[], over_weighted_factors=[], agent_score_drift={},
            ),
        ))
    log = DailyFeedbackLog(ticker=TICKER, sector=SECTOR, cycle_id=cycle_id, entries=prior_entries)
    store.save_feedback_log(log)

    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", True)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: _fb_output("external_shock"))

    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: False)

    calls = []
    monkeypatch.setattr(dr, "regenerate_envelope", lambda **kwargs: calls.append(kwargs) or _regenerated_envelope())

    revise_calls = []
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: revise_calls.append(kw))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["status"] == "completed"
    # Pin the rate-cap reclassification itself.
    assert summary["miss_type"] == "direction_flip"
    # external_shock trigger must NOT fire (miss_type no longer "external_shock").
    assert calls == []
    assert summary["reforecast_fired"] is False
    assert summary["reforecast_trigger"] is None
    assert len(revise_calls) == 1


# ---------------------------------------------------------------------------
# regenerate_envelope() returns None -> Step 7 runs as usual
# ---------------------------------------------------------------------------

def test_trigger_fires_but_regenerate_returns_none_step7_runs(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr

    store, cycle_id = _setup_store(tmp_path)
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", True)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: _fb_output("external_shock"))

    calls = []
    monkeypatch.setattr(dr, "regenerate_envelope", lambda **kwargs: calls.append(kwargs) or None)

    revise_calls = []
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: revise_calls.append(kw))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["status"] == "completed"
    assert len(calls) == 1
    assert calls[0]["trigger"] == "external_shock"
    # regenerate_envelope returned None -> Step 7 proceeds normally.
    assert len(revise_calls) == 1
    assert summary["reforecast_fired"] is False
    assert summary["reforecast_count"] is None
    # reforecast_trigger is still recorded even though regeneration didn't happen.
    assert summary["reforecast_trigger"] == "external_shock"


# ---------------------------------------------------------------------------
# RL_REFORECAST_ENABLED=False -> trigger block never calls regenerate_envelope
# ---------------------------------------------------------------------------

def test_reforecast_disabled_never_calls_regenerate(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr

    store, cycle_id = _setup_store(tmp_path)
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", False)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: _fb_output("external_shock"))

    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    from core.schemas.feedback import ThesisReview
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: True)
    monkeypatch.setattr(
        ThesisReviewer, "review",
        lambda self, **kw: ThesisReview(thesis_intact=False, horizon_confidence_multiplier=0.3),
    )

    calls = []
    monkeypatch.setattr(dr, "regenerate_envelope", lambda **kwargs: calls.append(kwargs) or _regenerated_envelope())

    revise_calls = []
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: revise_calls.append(kw))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["status"] == "completed"
    assert calls == []
    assert summary["reforecast_fired"] is False
    assert summary["reforecast_trigger"] is None
    assert len(revise_calls) == 1


# ---------------------------------------------------------------------------
# Exception inside trigger block never crashes run_daily_review
# ---------------------------------------------------------------------------

def test_trigger_block_exception_is_non_fatal(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr

    store, cycle_id = _setup_store(tmp_path)
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", True)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: _fb_output("external_shock"))

    def _boom(**kwargs):
        raise RuntimeError("regenerate boom")
    monkeypatch.setattr(dr, "regenerate_envelope", _boom)

    revise_calls = []
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: revise_calls.append(kw))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["status"] == "completed"
    assert summary["reforecast_fired"] is False
    # Step 7 still runs because reforecast_envelope stayed None after the
    # exception was swallowed.
    assert len(revise_calls) == 1
