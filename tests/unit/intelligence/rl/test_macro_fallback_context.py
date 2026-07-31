"""
F2 — market-wide fallback context when a ticker has no company news.

When get_news_context comes back blind, the FeedbackAgent used to see nothing
at all under MARKET CONTEXT TODAY. Its prompt forbids citing factors that are
not in the context and caps external_shock at 20% of days, so an unexplained
large move had nowhere to go but model_bias / direction_flip — a full 1.0x
weight penalty, plus permanent lessons written off that blindness (2026-07-30:
12 of 16 tickers). The macro news cache is already fetched 4x a day and costs
nothing to read, so on blind tickers only, its HIGH/MEDIUM items are injected
as clearly-labelled market-wide context.

Full-loop smoke tests — same seam stack as test_news_availability_telemetry.py.
"""
import json
from datetime import date

import pytest

from backend.shared.schemas.feedback import DailyForecast, PredictionEnvelope
from core.intelligence.rl.stores.prediction_store import PredictionStore

MACRO_HEADER = "[MARKET-WIDE CONTEXT — company-specific news unavailable]"


def _seed_envelope(ticker: str, store: PredictionStore, cycle_id: str) -> None:
    store.save_envelope(PredictionEnvelope(
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
    ))


def _run_review(
    ticker: str,
    tmp_path,
    monkeypatch,
    *,
    news_fn,
    macro_block="• [2026-06-10] [HIGH] RBI holds repo rate — Rate unchanged at 6.0%. [tags: rbi]",
    macro_raises=False,
    fallback_enabled=None,
) -> tuple[dict, list[tuple[str, str]]]:
    """Run the full loop and return (summary, [(system_prompt, user_prompt), ...])."""
    sector = "automobile"
    review_date = date(2026, 6, 10)

    store = PredictionStore(ticker, sector=sector, base_dir=tmp_path)
    _seed_envelope(ticker, store, store.cycle_id_for(review_date))

    import core.intelligence.rl.workflows.daily_review as dr
    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    if fallback_enabled is not None:
        monkeypatch.setattr(dr.settings, "RL_MACRO_FALLBACK_CONTEXT_ENABLED", fallback_enabled)
    monkeypatch.setattr(dr, "_fetch_actual_close", lambda t, d: 100.1)
    monkeypatch.setattr(dr, "get_price_history", lambda *a, **k: None)

    from core.schemas.feedback import RegimeSnapshot
    monkeypatch.setattr(dr.RegimeDetector, "detect", lambda self, d, s: RegimeSnapshot())

    import services.data.fetchers.news as news_mod
    monkeypatch.setattr(news_mod, "get_news_context", news_fn)

    # The seam under test: the macro cache read.
    import services.background.macro_news_cache as macro_mod

    calls: list[dict] = []

    class _StubCache:
        def get_for_daily_review(self, max_items: int = 5, for_date=None) -> str:
            calls.append({"max_items": max_items, "for_date": for_date})
            if macro_raises:
                raise RuntimeError("macro feed unreadable")
            return macro_block

    monkeypatch.setattr(macro_mod, "MacroNewsCache", _StubCache)

    import services.data.fetchers.nse_market as nse_mkt_mod
    monkeypatch.setattr(nse_mkt_mod, "get_nse_market_data", lambda *a, **k: {"error": "skipped"})

    from backend.shared.schemas.feedback import OffMarketSignals
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(offmarket_mod.OffMarketFetcher, "fetch_all",
                        lambda self, t, d: OffMarketSignals(date=d, ticker=t))

    import core.intelligence.rl.algorithms.factor_regime as factor_regime_mod
    monkeypatch.setattr(factor_regime_mod, "get_factor_regime", lambda *a, **k: None)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    prompts: list[tuple[str, str]] = []
    fb_payload = json.dumps({
        "primary_miss_agent": "", "miss_type": "magnitude",
        "missed_factors": [], "over_weighted_factors": [], "agent_score_drift": {},
        "new_lessons": [],
        "revised_context": {"headline": "Quiet session, thesis intact.",
                            "horizon_confidence_adjustment": 0.0},
    })

    def _capture(self, system_prompt, user_prompt, *a, **k):
        prompts.append((system_prompt, user_prompt))
        return fb_payload

    monkeypatch.setattr(FeedbackAgent, "_call_llm", _capture)

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
        "direction": "FLAT", "confidence": 0.5, "predicted_close": 100.1,
        "rationale": "Quiet session, no strong catalysts.",
    })
    monkeypatch.setattr(control_lane_mod, "_call_llm",
                        lambda *a, **k: (control_payload, "test-control-model"))

    summary = dr.run_daily_review(ticker, review_date, sector=sector)
    summary["_macro_cache_calls"] = calls
    return summary, prompts


_BLIND = lambda *a, **k: "Market context unavailable."          # noqa: E731
_HAS_NEWS = lambda *a, **k: "Maruti Q1 profit up 12% on SUV mix."  # noqa: E731


def test_macro_context_injected_when_ticker_news_blind(tmp_path, monkeypatch):
    """The 12/16 case: no company news, but the macro feed knows what happened."""
    summary, prompts = _run_review("TESTMACRO1", tmp_path, monkeypatch, news_fn=_BLIND)

    assert summary["status"] == "completed"
    assert summary["news_available"] is False
    _sys, user = prompts[0]
    assert MACRO_HEADER in user
    assert "RBI holds repo rate" in user


def test_macro_context_not_injected_when_company_news_present(tmp_path, monkeypatch):
    """Company news wins — market-wide filler would only dilute it."""
    summary, prompts = _run_review("TESTMACRO2", tmp_path, monkeypatch, news_fn=_HAS_NEWS)

    assert summary["news_available"] is True
    _sys, user = prompts[0]
    assert MACRO_HEADER not in user
    assert "RBI holds repo rate" not in user


def test_macro_context_skipped_when_disabled(tmp_path, monkeypatch):
    """Kill switch: config.yaml flag off ⇒ byte-identical to pre-F2 behaviour."""
    _summary, prompts = _run_review(
        "TESTMACRO3", tmp_path, monkeypatch, news_fn=_BLIND, fallback_enabled=False,
    )

    _sys, user = prompts[0]
    assert MACRO_HEADER not in user


def test_no_header_when_macro_cache_is_empty(tmp_path, monkeypatch):
    """An empty feed must not produce an empty, misleading header block."""
    _summary, prompts = _run_review(
        "TESTMACRO4", tmp_path, monkeypatch, news_fn=_BLIND, macro_block="",
    )

    _sys, user = prompts[0]
    assert MACRO_HEADER not in user


def test_macro_cache_failure_is_non_fatal(tmp_path, monkeypatch):
    """A broken macro feed degrades to pre-F2 blindness, never a failed review."""
    summary, prompts = _run_review(
        "TESTMACRO5", tmp_path, monkeypatch, news_fn=_BLIND, macro_raises=True,
    )

    assert summary["status"] == "completed"
    _sys, user = prompts[0]
    assert MACRO_HEADER not in user


def test_macro_context_is_read_for_the_reviewed_date(tmp_path, monkeypatch):
    """
    Backfills review past days (CLI --date, the scheduler_api backfill route).
    The macro read must be anchored to the day under review, or a June review
    gets July's headlines — the precise contamination this fix exists to remove.
    """
    summary, _prompts = _run_review("TESTMACRO7", tmp_path, monkeypatch, news_fn=_BLIND)

    assert summary["_macro_cache_calls"], "macro cache was never consulted"
    assert summary["_macro_cache_calls"][0]["for_date"] == date(2026, 6, 10)


def test_injected_macro_context_is_labelled_market_wide_not_company(tmp_path, monkeypatch):
    """
    Attribution honesty: the agent must be able to tell that this evidence is
    market-wide, so it cannot be written up as a stock-specific lesson.
    """
    _summary, prompts = _run_review("TESTMACRO6", tmp_path, monkeypatch, news_fn=_BLIND)

    _sys, user = prompts[0]
    header_line = next(ln for ln in user.splitlines() if MACRO_HEADER in ln)
    assert "company-specific news unavailable" in header_line
