"""
F3 — lessons record the evidence they were learned from.

A Lesson used to store its conclusion only (pattern / observation / rule). When
a later audit asked "was this learned from a real event or invented on a
newsless day?", nothing in the ledger could answer. `Lesson.evidence` keeps the
dated headlines that were in front of the agent when the lesson was written.

Additive and optional: ledgers written before F3 must load unchanged, and the
kill switch restores pre-F3 behaviour exactly.

Full-loop harness = same seam stack as test_macro_fallback_context.py.
"""
import json
from datetime import date

from backend.shared.schemas.feedback import (
    DailyForecast, FeedbackAgentOutput, LearningLedger, Lesson,
    PredictionEnvelope, RawLesson, RevisedContext,
)
from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
from core.intelligence.rl.stores.prediction_store import PredictionStore

_CONTEXT = (
    "• [Date: 2026-06-10] [Mint] Maruti Q1 profit up 12%: SUV mix drove margins.\n"
    "• [Date: 2026-06-09] Maruti hikes prices: 2% across variants.\n"
)


def _agent() -> FeedbackAgent:
    return FeedbackAgent.__new__(FeedbackAgent)     # no LLM client needed for merges


def _output(**kw) -> FeedbackAgentOutput:
    raw = RawLesson(category="macro", pattern="suv_mix_margin", observation="o",
                    rule="r", confidence=0.7, scope="stock_specific")
    return FeedbackAgentOutput(
        primary_miss_agent="risk_macro", miss_type="model_bias",
        missed_factors=[], over_weighted_factors=[], agent_score_drift={},
        new_lessons=[kw.pop("raw_lesson", raw)],
        revised_context=RevisedContext(headline="h"), **kw,
    )


def _ledger() -> LearningLedger:
    return LearningLedger(ticker="MARUTI", sector="automobile", last_updated="2026-06-10")


# --------------------------------------------------------------------------
# Writer: new lessons
# --------------------------------------------------------------------------

def test_new_lesson_records_the_headlines_it_was_learned_from():
    updated, _ids = _agent().merge_lessons_into_ledger(
        _output(), _ledger(), market_context=_CONTEXT)

    lesson = updated.find_by_pattern("suv_mix_margin")
    assert lesson is not None
    assert len(lesson.evidence) == 2
    assert lesson.evidence[0].startswith("2026-06-10 — ")
    assert "Maruti Q1 profit up 12%" in lesson.evidence[0]


def test_new_lesson_has_no_evidence_when_the_day_was_blind():
    """A newsless day must record NO provenance rather than a fabricated one."""
    updated, _ids = _agent().merge_lessons_into_ledger(
        _output(), _ledger(), market_context="Market context unavailable.")

    assert updated.find_by_pattern("suv_mix_margin").evidence == []


def test_market_context_defaults_to_empty_for_existing_callers():
    """The parameter is optional — callers that never pass it still work."""
    updated, _ids = _agent().merge_lessons_into_ledger(_output(), _ledger())

    assert updated.find_by_pattern("suv_mix_margin").evidence == []


# --------------------------------------------------------------------------
# Writer: reinforced lessons
# --------------------------------------------------------------------------

def test_reinforced_lesson_appends_todays_evidence():
    ledger = _ledger()
    ledger.lessons.append(Lesson(
        lesson_id="L001", date_learned="2026-06-01", category="macro",
        pattern="suv_mix_margin", observation="o", rule="r",
        evidence=["2026-06-01 — Maruti May sales beat"],
    ))

    updated, _ids = _agent().merge_lessons_into_ledger(
        _output(), ledger, market_context=_CONTEXT)

    evidence = updated.find_by_pattern("suv_mix_margin").evidence
    assert evidence[0] == "2026-06-01 — Maruti May sales beat"   # history kept
    assert any("Maruti Q1 profit up 12%" in e for e in evidence)


def test_reinforced_lesson_does_not_duplicate_evidence_it_already_has():
    ledger = _ledger()
    ledger.lessons.append(Lesson(
        lesson_id="L001", date_learned="2026-06-01", category="macro",
        pattern="suv_mix_margin", observation="o", rule="r",
        evidence=["2026-06-10 — [Mint] Maruti Q1 profit up 12%: SUV mix drove margins."],
    ))

    updated, _ids = _agent().merge_lessons_into_ledger(
        _output(), ledger, market_context=_CONTEXT)

    evidence = updated.find_by_pattern("suv_mix_margin").evidence
    assert len(evidence) == len(set(evidence))
    assert len(evidence) == 2                # the dup plus one genuinely new line


def test_evidence_is_capped_so_a_long_lived_lesson_cannot_grow_without_bound(monkeypatch):
    import core.intelligence.rl.agents.feedback_agent as fa
    monkeypatch.setattr(fa.settings, "RL_LESSON_EVIDENCE_MAX_ITEMS", 2)

    ledger = _ledger()
    ledger.lessons.append(Lesson(
        lesson_id="L001", date_learned="2026-06-01", category="macro",
        pattern="suv_mix_margin", observation="o", rule="r",
        evidence=["2026-05-01 — oldest", "2026-05-02 — older"],
    ))

    updated, _ids = _agent().merge_lessons_into_ledger(
        _output(), ledger, market_context=_CONTEXT)

    evidence = updated.find_by_pattern("suv_mix_margin").evidence
    assert len(evidence) == 2
    assert "oldest" not in " ".join(evidence)         # oldest evicted first
    assert any("Maruti Q1 profit up 12%" in e for e in evidence)


# --------------------------------------------------------------------------
# Kill switch + backward compatibility
# --------------------------------------------------------------------------

def test_kill_switch_restores_pre_f3_behaviour(monkeypatch):
    import core.intelligence.rl.agents.feedback_agent as fa
    monkeypatch.setattr(fa.settings, "RL_PROVENANCE_ENABLED", False)

    updated, _ids = _agent().merge_lessons_into_ledger(
        _output(), _ledger(), market_context=_CONTEXT)

    assert updated.find_by_pattern("suv_mix_margin").evidence == []


def test_pre_f3_ledger_json_still_loads():
    """Ledgers on the prod volume have no `evidence` key — they must not break."""
    legacy = {
        "ticker": "MARUTI", "sector": "automobile", "last_updated": "2026-06-01",
        "lessons": [{
            "lesson_id": "L001", "date_learned": "2026-05-01", "category": "macro",
            "pattern": "rbi_day", "observation": "o", "rule": "r",
            "confidence": 0.6, "occurrences": 3,
        }],
    }

    ledger = LearningLedger.model_validate(json.loads(json.dumps(legacy)))

    assert ledger.lessons[0].evidence == []


def test_evidence_survives_a_json_round_trip():
    lesson = Lesson(lesson_id="L001", date_learned="2026-06-10", category="macro",
                    pattern="p", observation="o", rule="r",
                    evidence=["2026-06-10 — a dated headline"])

    reloaded = Lesson.model_validate(json.loads(lesson.model_dump_json()))

    assert reloaded.evidence == ["2026-06-10 — a dated headline"]


# --------------------------------------------------------------------------
# Provenance must survive propagation to the shared ledgers
# --------------------------------------------------------------------------

def _lesson_with_evidence(evidence: list[str], lesson_id="L001") -> Lesson:
    return Lesson(lesson_id=lesson_id, date_learned="2026-06-10", category="macro",
                  pattern="suv_mix_margin", observation="o", rule="r",
                  scope="sector_wide", evidence=evidence)


def test_propagated_shared_lesson_keeps_its_evidence():
    """A sector/market lesson is the one other tickers inherit — it needs its
    provenance more than the ticker-local copy, not less."""
    from core.intelligence.rl.stores.ledger_propagator import propagate_lesson_to_ledger

    shared = LearningLedger(ticker="SECTOR", sector="automobile",
                            last_updated="2026-06-10")

    propagate_lesson_to_ledger(
        _lesson_with_evidence(["2026-06-10 — Maruti Q1 profit up 12%"]),
        shared, source_ticker="MARUTI")

    assert shared.lessons[0].evidence == ["2026-06-10 — Maruti Q1 profit up 12%"]


def test_shared_lesson_confirmed_by_another_ticker_gains_that_evidence():
    from core.intelligence.rl.stores.ledger_propagator import propagate_lesson_to_ledger

    shared = LearningLedger(ticker="SECTOR", sector="automobile",
                            last_updated="2026-06-10",
                            lessons=[_lesson_with_evidence(["2026-06-09 — Maruti note"])])

    propagate_lesson_to_ledger(
        _lesson_with_evidence(["2026-06-10 — Tata Motors JLR volumes"], lesson_id="L009"),
        shared, source_ticker="TATAMOTORS")

    evidence = shared.lessons[0].evidence
    assert "2026-06-09 — Maruti note" in evidence
    assert "2026-06-10 — Tata Motors JLR volumes" in evidence


# --------------------------------------------------------------------------
# Full loop — proves daily_review actually hands the context to the merge
# --------------------------------------------------------------------------

def test_daily_review_persists_evidence_on_the_lesson_it_writes(tmp_path, monkeypatch):
    ticker, sector = "TESTEVID1", "automobile"
    review_date = date(2026, 6, 10)

    store = PredictionStore(ticker, sector=sector, base_dir=tmp_path)
    store.save_envelope(PredictionEnvelope(
        ticker=ticker, sector=sector, cycle_id=store.cycle_id_for(review_date),
        generated_at="2026-06-01T00:00:00", base_close=100.0,
        daily_forecasts=[
            DailyForecast(day=1, date="2026-06-10", predicted_close=100.0,
                          predicted_verdict="NEUTRAL",
                          predicted_agent_scores={"risk_macro": 0.5, "sales_demand": 0.5},
                          confidence=0.5),
        ],
    ))

    import core.intelligence.rl.workflows.daily_review as dr
    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dr, "_fetch_actual_close", lambda t, d: 100.1)
    monkeypatch.setattr(dr, "get_price_history", lambda *a, **k: None)

    from core.schemas.feedback import RegimeSnapshot
    monkeypatch.setattr(dr.RegimeDetector, "detect", lambda self, d, s: RegimeSnapshot())

    import services.data.fetchers.news as news_mod
    monkeypatch.setattr(news_mod, "get_news_context", lambda *a, **k: _CONTEXT)

    import services.data.fetchers.nse_market as nse_mkt_mod
    monkeypatch.setattr(nse_mkt_mod, "get_nse_market_data", lambda *a, **k: {"error": "skipped"})

    from backend.shared.schemas.feedback import OffMarketSignals
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(offmarket_mod.OffMarketFetcher, "fetch_all",
                        lambda self, t, d: OffMarketSignals(date=d, ticker=t))

    import core.intelligence.rl.algorithms.factor_regime as factor_regime_mod
    monkeypatch.setattr(factor_regime_mod, "get_factor_regime", lambda *a, **k: None)

    fb_payload = json.dumps({
        "primary_miss_agent": "", "miss_type": "model_bias",
        "missed_factors": [], "over_weighted_factors": [], "agent_score_drift": {},
        "new_lessons": [{"category": "macro", "pattern": "suv_mix_margin",
                         "observation": "o", "rule": "r", "confidence": 0.7,
                         "scope": "stock_specific"}],
        "revised_context": {"headline": "h", "horizon_confidence_adjustment": 0.0},
    })
    monkeypatch.setattr(FeedbackAgent, "_call_llm", lambda self, *a, **k: fb_payload)

    from core.intelligence.rl.agents.dossier_curator import DossierCurator
    monkeypatch.setattr(DossierCurator, "_call_llm", lambda self, *a, **k: json.dumps({
        "event_tags_today": [], "new_observations": [], "signature_updates": [],
        "guidance_updates": [], "catalyst_updates": [], "thesis_update": None,
        "flow_note": "", "open_question_updates": [],
    }))

    import core.intelligence.rl.agents.control_lane as control_lane_mod
    monkeypatch.setattr(control_lane_mod, "_call_llm", lambda *a, **k: (json.dumps({
        "direction": "FLAT", "confidence": 0.5, "predicted_close": 100.1,
        "rationale": "Quiet session.",
    }), "test-control-model"))

    summary = dr.run_daily_review(ticker, review_date, sector=sector)
    assert summary["status"] == "completed"

    ticker_ledger, _sector, _market = PredictionStore(
        ticker, sector=sector, base_dir=tmp_path).load_all_ledgers()
    lesson = ticker_ledger.find_by_pattern("suv_mix_margin")
    assert lesson is not None
    assert any("Maruti Q1 profit up 12%" in e for e in lesson.evidence)
