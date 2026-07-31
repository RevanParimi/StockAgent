"""
F5 — news-availability telemetry on the daily review.

The 2026-07-30 16:30 IST prod run reviewed 16 tickers with 12 of them
"News context unavailable", and nothing but a WARNING line recorded it: there
was no metric, so the blindness was invisible to the scheduler, to
/scheduler/status and to any A/B measurement of the F1 query fix.

run_daily_review() therefore reports whether the FeedbackAgent actually saw
company news for this ticker; the scheduler aggregates the flag per run.
Full-loop smoke tests (same seam stack as test_daily_review_dossier.py) —
the news block has no smaller seam than the workflow itself.
"""
import json
from datetime import date

import pytest

from backend.shared.schemas.feedback import DailyForecast, PredictionEnvelope
from core.intelligence.rl.stores.prediction_store import PredictionStore


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


def _run_review_with_news(news_fn, ticker: str, tmp_path, monkeypatch) -> dict:
    """Run the full loop on a quiet day, with get_news_context swapped out."""
    sector = "automobile"
    review_date = date(2026, 6, 10)

    store = PredictionStore(ticker, sector=sector, base_dir=tmp_path)
    _seed_envelope(ticker, store, store.cycle_id_for(review_date))

    import core.intelligence.rl.workflows.daily_review as dr
    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dr, "_fetch_actual_close", lambda t, d: 100.1)
    monkeypatch.setattr(dr, "get_price_history", lambda *a, **k: None)

    from core.schemas.feedback import RegimeSnapshot
    monkeypatch.setattr(dr.RegimeDetector, "detect", lambda self, d, s: RegimeSnapshot())

    # The seam under test.
    import services.data.fetchers.news as news_mod
    monkeypatch.setattr(news_mod, "get_news_context", news_fn)

    import services.data.fetchers.nse_market as nse_mkt_mod
    monkeypatch.setattr(nse_mkt_mod, "get_nse_market_data", lambda *a, **k: {"error": "skipped"})

    from backend.shared.schemas.feedback import OffMarketSignals
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(offmarket_mod.OffMarketFetcher, "fetch_all",
                        lambda self, t, d: OffMarketSignals(date=d, ticker=t))

    import core.intelligence.rl.algorithms.factor_regime as factor_regime_mod
    monkeypatch.setattr(factor_regime_mod, "get_factor_regime", lambda *a, **k: None)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    fb_payload = json.dumps({
        "primary_miss_agent": "", "miss_type": "magnitude",
        "missed_factors": [], "over_weighted_factors": [], "agent_score_drift": {},
        "new_lessons": [],
        "revised_context": {"headline": "Quiet session, thesis intact.",
                            "horizon_confidence_adjustment": 0.0},
    })
    monkeypatch.setattr(FeedbackAgent, "_call_llm", lambda self, *a, **k: fb_payload)

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

    return dr.run_daily_review(ticker, review_date, sector=sector)


def test_summary_reports_news_available_when_context_fetched(tmp_path, monkeypatch):
    summary = _run_review_with_news(
        lambda *a, **k: "Maruti Suzuki Q1 profit up 12% on SUV mix.",
        "TESTNEWS1", tmp_path, monkeypatch,
    )
    assert summary["status"] == "completed"
    assert summary["news_available"] is True


@pytest.mark.parametrize("blind_fn, label", [
    (lambda *a, **k: "Market context unavailable.", "sentinel"),
    (lambda *a, **k: "", "empty_string"),
])
def test_summary_reports_news_blind_when_context_missing(
    blind_fn, label, tmp_path, monkeypatch,
):
    """The 12/16 prod case: Serper returned nothing, FeedbackAgent ran blind."""
    summary = _run_review_with_news(blind_fn, f"TESTBLIND_{label}", tmp_path, monkeypatch)
    assert summary["status"] == "completed"
    assert summary["news_available"] is False


def test_summary_reports_news_blind_when_fetch_raises(tmp_path, monkeypatch):
    """A fetcher exception is blindness too — not an absent metric."""
    def boom(*a, **k):
        raise RuntimeError("serper 500")

    summary = _run_review_with_news(boom, "TESTBLIND_RAISE", tmp_path, monkeypatch)
    assert summary["status"] == "completed"
    assert summary["news_available"] is False
