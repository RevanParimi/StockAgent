"""Step 8.5 wiring: today_tags, Step-7 claim emphasis, dossier curator.

Covers Task 10 of docs/superpowers/plans/2026-06-11-ticker-dossier.md:
- tag_events()/calendar_day_tags() drive Step-7 emphasis (contract check).
- _revise_remaining_forecasts(ticker_ledger=..., today_tags=...) applies
  apply_lesson_emphasis() to remaining forecasts' predicted_agent_scores.
- run_daily_review() persists event_tags on the FeedbackEntry and writes
  a TickerDossier via DossierCurator (Step 8.5), without blocking Step 9.
"""
import json
from datetime import date

import pytest

from backend.shared.schemas.feedback import (
    DailyForecast,
    LearningLedger,
    Lesson,
    PredictionEnvelope,
    RevisedContext,
    tag_events,
)
from core.intelligence.rl.algorithms.lesson_emphasis import apply_lesson_emphasis
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.workflows.daily_review import _revise_remaining_forecasts


def test_tag_events_drives_step7_emphasis_contract():
    # The same context string must produce tags that fire a tagged lesson.
    ctx = "RBI surprise hold pressured autos; FII outflow 2200Cr"
    tags = tag_events(ctx)
    lesson = Lesson(lesson_id="L1", date_learned="2026-06-11", category="macro",
                     pattern="rbi", observation="o", rule="r", confidence=0.8,
                     occurrences=2, last_seen="2026-06-11",
                     trigger_tags=["central_bank_event"], prioritise_agents=["risk_macro"])
    ledger = LearningLedger(ticker="T", sector="automobile",
                             last_updated="2026-06-11", lessons=[lesson])
    out = apply_lesson_emphasis({"risk_macro": 0.5}, ledger, tags)
    assert out["risk_macro"] > 0.5


def _make_envelope(ticker: str, cycle_id: str) -> PredictionEnvelope:
    return PredictionEnvelope(
        ticker=ticker, sector="automobile", cycle_id=cycle_id,
        generated_at="2026-06-01T00:00:00", base_close=100.0,
        daily_forecasts=[
            DailyForecast(day=1, date="2026-06-10", predicted_close=100.0,
                           predicted_verdict="NEUTRAL",
                           predicted_agent_scores={"risk_macro": 0.5, "sales_demand": 0.5},
                           confidence=0.5),
            DailyForecast(day=2, date="2026-06-11", predicted_close=101.0,
                           predicted_verdict="NEUTRAL",
                           predicted_agent_scores={"risk_macro": 0.5, "sales_demand": 0.5},
                           confidence=0.5),
        ],
    )


def _tagged_ledger(ticker: str) -> LearningLedger:
    lesson = Lesson(lesson_id="L1", date_learned="2026-06-01", category="macro",
                     pattern="rbi_day", observation="o", rule="r", confidence=0.8,
                     occurrences=3, last_seen=date.today().isoformat(),
                     trigger_tags=["central_bank_event"],
                     prioritise_agents=["risk_macro"], discount_agents=["sales_demand"])
    return LearningLedger(ticker=ticker, sector="automobile",
                           last_updated="2026-06-11", lessons=[lesson])


def test_revise_remaining_forecasts_applies_lesson_emphasis(tmp_path):
    """Step-7: ticker_ledger + today_tags must boost/dampen remaining forecasts'
    predicted_agent_scores via apply_lesson_emphasis()."""
    store = PredictionStore("TESTX", sector="automobile", base_dir=tmp_path)
    cycle_id = store.current_cycle_id()
    store.save_envelope(_make_envelope("TESTX", cycle_id))

    _revise_remaining_forecasts(
        ticker="TESTX", store=store, reviewed_date="2026-06-10",
        new_weights={"risk_macro": 1.0, "sales_demand": 1.0},
        revised_context=RevisedContext(),
        ticker_ledger=_tagged_ledger("TESTX"),
        today_tags=["central_bank_event"],
    )

    out = store.load_envelope(cycle_id)
    remaining = out.get_forecast("2026-06-11")
    assert remaining.predicted_agent_scores["risk_macro"] == pytest.approx(0.53)
    assert remaining.predicted_agent_scores["sales_demand"] == pytest.approx(0.47)


def test_revise_remaining_forecasts_no_tags_unchanged(tmp_path):
    """Without today_tags, predicted_agent_scores are left untouched (still
    only re-weighted by the existing composite blend, not claim emphasis)."""
    store = PredictionStore("TESTY", sector="automobile", base_dir=tmp_path)
    cycle_id = store.current_cycle_id()
    store.save_envelope(_make_envelope("TESTY", cycle_id))

    _revise_remaining_forecasts(
        ticker="TESTY", store=store, reviewed_date="2026-06-10",
        new_weights={"risk_macro": 1.0, "sales_demand": 1.0},
        revised_context=RevisedContext(),
        ticker_ledger=_tagged_ledger("TESTY"),
        today_tags=None,
    )

    out = store.load_envelope(cycle_id)
    remaining = out.get_forecast("2026-06-11")
    assert remaining.predicted_agent_scores == {"risk_macro": 0.5, "sales_demand": 0.5}


# ---------------------------------------------------------------------------
# Full run_daily_review() smoke test — Step 8.5 dossier persistence
# ---------------------------------------------------------------------------

def test_run_daily_review_writes_dossier_and_event_tags(tmp_path, monkeypatch):
    """Full-loop smoke test: run_daily_review() on a quiet (direction-correct,
    near-zero-error) day must:
      - persist event_tags on the FeedbackEntry,
      - write {ticker}_dossier.json with >=1 observation via DossierCurator,
      - complete Step 9 without raising even though Step 8.5 ran.
    """
    ticker, sector = "TESTZ", "automobile"
    review_date = date(2026, 6, 10)
    date_str = review_date.isoformat()

    store = PredictionStore(ticker, sector=sector, base_dir=tmp_path)
    cycle_id = store.current_cycle_id()
    store.save_envelope(_make_envelope(ticker, cycle_id))

    # --- Monkeypatch all network/LLM-touching boundaries (non-deterministic / slow) ---
    import core.intelligence.rl.workflows.daily_review as dr

    # run_daily_review constructs its own PredictionStore(ticker, sector=sector)
    # without base_dir — redirect settings.PREDICTION_DATA_DIR so it lands in
    # the same tmp_path as our setup store.
    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(tmp_path))

    # Step 2: actual close — direction-correct, near-zero error (NEUTRAL verdict
    # is always direction_correct regardless, but keep the error tiny too).
    monkeypatch.setattr(dr, "_fetch_actual_close", lambda t, d: 100.1)

    # Volume context (non-fatal try/except around get_price_history).
    monkeypatch.setattr(dr, "get_price_history", lambda *a, **k: None)

    # Step 0: regime detection — default NORMAL snapshot, no yfinance calls.
    from core.schemas.feedback import RegimeSnapshot
    monkeypatch.setattr(dr.RegimeDetector, "detect", lambda self, d, s: RegimeSnapshot())

    # News context (Serper) — return a fixed string, no network call.
    import services.data.fetchers.news as news_mod
    monkeypatch.setattr(news_mod, "get_news_context", lambda *a, **k: "Quiet session.")

    # NSE market intelligence (FII/DII) — degrade to "error" so the block is skipped.
    import services.data.fetchers.nse_market as nse_mkt_mod
    monkeypatch.setattr(nse_mkt_mod, "get_nse_market_data", lambda *a, **k: {"error": "skipped"})

    # G4 off-market signals — fetch_all returns an empty signals object (no `nse` pkg calls).
    from backend.shared.schemas.feedback import OffMarketSignals
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(
        offmarket_mod.OffMarketFetcher, "fetch_all",
        lambda self, t, d: OffMarketSignals(date=d, ticker=t),
    )

    # Factor regime (IIMA) — avoid network/CSV fetch.
    import core.intelligence.rl.algorithms.factor_regime as factor_regime_mod
    monkeypatch.setattr(factor_regime_mod, "get_factor_regime", lambda *a, **k: None)

    # FeedbackAgent LLM call — fixed "no new lessons, hit day" payload.
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    fb_payload = json.dumps({
        "primary_miss_agent": "", "miss_type": "magnitude",
        "missed_factors": [], "over_weighted_factors": [], "agent_score_drift": {},
        "new_lessons": [],
        "revised_context": {"headline": "Quiet session, thesis intact.",
                             "horizon_confidence_adjustment": 0.0},
    })
    monkeypatch.setattr(FeedbackAgent, "_call_llm", lambda self, *a, **k: fb_payload)

    # DossierCurator LLM call — seed one observation.
    from core.intelligence.rl.agents.dossier_curator import DossierCurator
    dossier_payload = {
        "event_tags_today": [], "new_observations": [
            {"observation": "seeded obs", "tags": [], "materiality": 0.9}],
        "signature_updates": [], "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    monkeypatch.setattr(DossierCurator, "_call_llm",
                         lambda self, *a, **k: json.dumps(dossier_payload))

    # Step 10: Control lane LLM call — fixed prediction payload.
    import core.intelligence.rl.agents.control_lane as control_lane_mod
    control_payload = json.dumps({
        "direction": "FLAT", "confidence": 0.5, "predicted_close": 100.1,
        "rationale": "Quiet session, no strong catalysts.",
    })
    monkeypatch.setattr(
        control_lane_mod, "_call_llm",
        lambda *a, **k: (control_payload, "test-control-model"))

    # --- Run ---
    summary = dr.run_daily_review(ticker, review_date, sector=sector)

    assert summary["status"] == "completed"

    # event_tags persisted on the FeedbackEntry. June 10 falls in the monsoon
    # window (calendar_day_tags), and the mocked news context yields no
    # keyword-based tags, so today_tags == ["monsoon"].
    feedback_log = store.load_feedback_log(cycle_id)
    entry = next(e for e in feedback_log.entries if e.date == date_str)
    assert entry.event_tags == ["monsoon"]

    # claims_fired: empty list — no tagged lessons match "monsoon" in this fixture.
    assert entry.claims_fired == []

    # Step 8.5 — dossier written with >=1 observation.
    dossier = store.load_dossier()
    assert dossier is not None
    todays_obs = [o for o in dossier.observations if o.date == date_str]
    assert len(todays_obs) >= 1
    assert todays_obs[0].observation == "seeded obs"

    # Step 10 — control log written with 1 prediction for the next trading day.
    control_log = store.load_control_log(cycle_id)
    assert len(control_log.entries) == 1
    prediction = control_log.entries[0]
    assert prediction.date == "2026-06-11"
    assert prediction.made_on == date_str
    assert prediction.predicted_direction == "FLAT"
    assert prediction.model == "test-control-model"


# ---------------------------------------------------------------------------
# Regression test for bc1d8ee — external_shock rate-cap NameError fix
# ---------------------------------------------------------------------------

def test_run_daily_review_external_shock_wrong_direction_no_crash(tmp_path, monkeypatch):
    """Guards the bc1d8ee hoist: before that fix, the external_shock rate-cap
    block referenced `feedback_log` ~36 lines before it was loaded, raising
    NameError on every (miss_type="external_shock", direction wrong) day.

    Reuses the same seam stack as
    test_run_daily_review_writes_dossier_and_event_tags, but:
      - the envelope's review-day forecast has predicted_verdict="BUY" so a
        falling actual close makes direction_correct=False, and
      - FeedbackAgent.run is monkeypatched directly to return
        miss_type="external_shock" with direction wrong — exactly the
        condition that entered the buggy block.

    Asserts the review completes without raising (status == "completed").
    """
    ticker, sector = "TESTSHOCK", "automobile"
    review_date = date(2026, 6, 10)
    date_str = review_date.isoformat()

    # BUY verdict + falling actual close (98.0 vs predicted 100.0) => DOWN
    # actual direction => direction_correct=False for a BUY verdict.
    envelope = PredictionEnvelope(
        ticker=ticker, sector=sector, cycle_id=f"{ticker}_2026-06",
        generated_at="2026-06-01T00:00:00", base_close=100.0,
        daily_forecasts=[
            DailyForecast(day=1, date="2026-06-10", predicted_close=100.0,
                           predicted_verdict="BUY",
                           predicted_agent_scores={"risk_macro": 0.5, "sales_demand": 0.5},
                           confidence=0.5),
            DailyForecast(day=2, date="2026-06-11", predicted_close=101.0,
                           predicted_verdict="BUY",
                           predicted_agent_scores={"risk_macro": 0.5, "sales_demand": 0.5},
                           confidence=0.5),
        ],
    )

    store = PredictionStore(ticker, sector=sector, base_dir=tmp_path)
    cycle_id = store.current_cycle_id()
    store.save_envelope(envelope)

    import core.intelligence.rl.workflows.daily_review as dr

    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(tmp_path))

    # Falling actual close => actual_direction="DOWN" => direction_correct=False
    # for the BUY verdict above.
    monkeypatch.setattr(dr, "_fetch_actual_close", lambda t, d: 98.0)
    monkeypatch.setattr(dr, "get_price_history", lambda *a, **k: None)

    from core.schemas.feedback import RegimeSnapshot
    monkeypatch.setattr(dr.RegimeDetector, "detect", lambda self, d, s: RegimeSnapshot())

    import services.data.fetchers.news as news_mod
    monkeypatch.setattr(news_mod, "get_news_context", lambda *a, **k: "Quiet session.")

    import services.data.fetchers.nse_market as nse_mkt_mod
    monkeypatch.setattr(nse_mkt_mod, "get_nse_market_data", lambda *a, **k: {"error": "skipped"})

    from backend.shared.schemas.feedback import OffMarketSignals
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(
        offmarket_mod.OffMarketFetcher, "fetch_all",
        lambda self, t, d: OffMarketSignals(date=d, ticker=t),
    )

    import core.intelligence.rl.algorithms.factor_regime as factor_regime_mod
    monkeypatch.setattr(factor_regime_mod, "get_factor_regime", lambda *a, **k: None)

    # FeedbackAgent.run mocked directly — return miss_type="external_shock"
    # with direction wrong, the exact condition that hit the buggy line.
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    from core.schemas.feedback import FeedbackAgentOutput, RevisedContext as _RevisedContext
    fb_output = FeedbackAgentOutput(
        primary_miss_agent="risk_macro",
        miss_type="external_shock",
        missed_factors=[], over_weighted_factors=[], agent_score_drift={},
        new_lessons=[],
        revised_context=_RevisedContext(headline="Unforeseeable shock.",
                                         horizon_confidence_adjustment=0.0),
    )
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: fb_output)

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
        "direction": "FLAT", "confidence": 0.5, "predicted_close": 98.0,
        "rationale": "Unforeseeable shock, no continuation expected.",
    })
    monkeypatch.setattr(
        control_lane_mod, "_call_llm",
        lambda *a, **k: (control_payload, "test-control-model"))

    # Living Envelope (RL Phase 2.5): miss_type="external_shock" with
    # direction_correct=False now fires the reforecast trigger block, which
    # would otherwise call regenerate_envelope() -> get_orchestrator(sector)
    # .analyse(ticker) -- a real 9-agent LLM pipeline. Short-circuit it here;
    # this test only cares that run_daily_review() completes without raising.
    monkeypatch.setattr(dr, "regenerate_envelope", lambda **kwargs: None)

    # _run_todays_agent_scores() also calls get_orchestrator(sector).analyse()
    # whenever direction_correct is False -- short-circuit for the same reason.
    monkeypatch.setattr(
        dr, "_run_todays_agent_scores",
        lambda *a, **k: {"risk_macro": 0.5, "sales_demand": 0.5},
    )

    # --- Run: must not raise (NameError pre-bc1d8ee) ---
    summary = dr.run_daily_review(ticker, review_date, sector=sector)

    assert summary["status"] == "completed"
    assert summary["direction_correct"] is False
    assert summary["miss_type"] == "external_shock"
