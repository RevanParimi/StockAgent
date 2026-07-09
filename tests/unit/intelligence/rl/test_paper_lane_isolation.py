"""Compass Phase B — PAPER-LANE ISOLATION invariant (spec §6.3).

'Paper review never touches sector/market ledger or weight memory files' —
plus: never writes global regime state, never fires re-forecasts, never runs
the control lane, and stores everything under PAPER_PREDICTION_DATA_DIR.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from core.schemas.feedback import DailyForecast, PredictionEnvelope, RevisedContext
from core.intelligence.rl.stores.prediction_store import PredictionStore

TICKER = "PAPERCO"
SECTOR = "pharma"
REVIEW_DATE = date.today()
DATE_STR = REVIEW_DATE.isoformat()


def _make_envelope() -> PredictionEnvelope:
    return PredictionEnvelope(
        ticker=TICKER, sector=SECTOR,
        cycle_id=f"{TICKER}_{REVIEW_DATE.year}-{REVIEW_DATE.month:02d}",
        generated_at=f"{REVIEW_DATE.replace(day=1).isoformat()}T00:00:00",
        base_close=100.0,
        daily_forecasts=[
            DailyForecast(day=1, date=DATE_STR, predicted_close=100.0,
                          predicted_verdict="BUY",
                          predicted_agent_scores={"risk": 0.5, "fundamentals": 0.5},
                          confidence=0.5),
            DailyForecast(day=2, date=(REVIEW_DATE + timedelta(days=1)).isoformat(),
                          predicted_close=101.0, predicted_verdict="BUY",
                          predicted_agent_scores={"risk": 0.5, "fundamentals": 0.5},
                          confidence=0.5),
        ],
    )


def _fb_output(miss_type: str = "direction_flip"):
    from core.schemas.feedback import FeedbackAgentOutput
    return FeedbackAgentOutput(
        primary_miss_agent="risk", miss_type=miss_type,
        missed_factors=[], over_weighted_factors=[], agent_score_drift={},
        new_lessons=[],
        revised_context=RevisedContext(headline="Test.",
                                       horizon_confidence_adjustment=0.0),
    )


def _patch_common(dr, monkeypatch, actual_close: float = 98.0):
    # Same seam stack as test_shock_path._patch_common, minus PREDICTION_DATA_DIR
    # (this test controls both roots explicitly).
    monkeypatch.setattr(dr, "_fetch_actual_close", lambda t, d: actual_close)
    monkeypatch.setattr(dr, "get_price_history", lambda *a, **k: None)
    monkeypatch.setattr(dr, "_run_todays_agent_scores",
                        lambda *a, **k: {"risk": 0.5, "fundamentals": 0.5})
    from core.schemas.feedback import RegimeSnapshot
    monkeypatch.setattr(dr.RegimeDetector, "detect", lambda self, d, s: RegimeSnapshot())
    import services.data.fetchers.news as news_mod
    monkeypatch.setattr(news_mod, "get_news_context", lambda *a, **k: "Quiet session.")
    import services.data.fetchers.nse_market as nse_mkt_mod
    monkeypatch.setattr(nse_mkt_mod, "get_nse_market_data", lambda *a, **k: {"error": "skipped"})
    from core.schemas.feedback import OffMarketSignals
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(offmarket_mod.OffMarketFetcher, "fetch_all",
                        lambda self, t, d: OffMarketSignals(date=d, ticker=t))
    import core.intelligence.rl.algorithms.factor_regime as factor_regime_mod
    monkeypatch.setattr(factor_regime_mod, "get_factor_regime", lambda *a, **k: None)
    import core.intelligence.rl.workflows.month_end_validation as mev
    monkeypatch.setattr(mev, "_is_last_trading_day_of_month", lambda d: False)
    monkeypatch.setattr(dr.settings, "RL_DOSSIER_ENABLED", False)
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run",
                        lambda self, fb_input, ledger: _fb_output())
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: False)


def test_paper_review_full_isolation(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr

    real_root = tmp_path / "real"
    paper_root = tmp_path / "paper"
    real_root.mkdir()
    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(real_root))
    monkeypatch.setattr(dr.settings, "PAPER_PREDICTION_DATA_DIR", str(paper_root))
    _patch_common(dr, monkeypatch)

    # Seed the PAPER store with an envelope (as paper_lane.ensure_paper_envelope would).
    paper_store = PredictionStore(TICKER, sector=SECTOR, base_dir=str(paper_root))
    paper_store.save_envelope(_make_envelope())

    # Spies on every isolation seam.
    adapter_calls, propagate_calls, regime_calls, reforecast_calls, control_calls = \
        [], [], [], [], []
    monkeypatch.setattr(dr.WeightAdapter, "update",
                        lambda self, **kw: adapter_calls.append(kw))
    monkeypatch.setattr(dr, "propagate_lessons",
                        lambda **kw: propagate_calls.append(kw))
    monkeypatch.setattr(dr, "update_sticky_regime",
                        lambda *a, **kw: regime_calls.append(a))
    monkeypatch.setattr(dr, "regenerate_envelope",
                        lambda **kw: reforecast_calls.append(kw))
    import core.intelligence.rl.agents.control_lane as cl
    monkeypatch.setattr(cl, "run_control_lane_step",
                        lambda *a, **kw: control_calls.append(a))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR, paper=True)

    assert summary["status"] == "completed"
    assert summary["paper"] is True

    # THE invariant: no weight training, no shared-ledger writes, no global
    # regime writes, no re-forecast, no control lane.
    assert adapter_calls == []
    assert propagate_calls == []
    assert regime_calls == []
    assert reforecast_calls == []
    assert control_calls == []

    # Nothing appeared under the REAL prediction root.
    assert list(real_root.rglob("*")) == []

    # The paper store DID get the local feedback log (per-idea learning only).
    cycle_id = paper_store.current_cycle_id()
    log = paper_store.load_feedback_log(cycle_id)
    assert len(log.entries) == 1 and log.entries[0].date == DATE_STR

    # And no weight-memory file exists even in the paper root (no writes at all).
    assert not list(paper_root.rglob("*weight_memory*"))


def test_paper_false_still_trains(tmp_path, monkeypatch):
    """Guard the guard: a NON-paper review still calls the WeightAdapter."""
    import core.intelligence.rl.workflows.daily_review as dr

    real_root = tmp_path / "real"
    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(real_root))
    _patch_common(dr, monkeypatch)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", False)
    monkeypatch.setattr(dr.settings, "RL_CONTROL_LANE_ENABLED", False)

    store = PredictionStore(TICKER, sector=SECTOR, base_dir=str(real_root))
    store.save_envelope(_make_envelope())

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)
    assert summary["status"] == "completed"
    assert summary["paper"] is False
    assert list(real_root.rglob("*weight_memory*"))     # weights were saved


def test_generate_forecast_paper_uses_paper_root(monkeypatch, tmp_path):
    """generate_forecast(paper=True) builds its store on the paper root."""
    import core.intelligence.rl.workflows.generate_forecast as gf

    captured = {}
    real_init = gf.PredictionStore.__init__

    def spy_init(self, ticker, sector=None, base_dir=None):
        captured["base_dir"] = base_dir
        real_init(self, ticker, sector=sector, base_dir=base_dir)

    monkeypatch.setattr(gf.PredictionStore, "__init__", spy_init)
    monkeypatch.setattr(gf.settings, "PAPER_PREDICTION_DATA_DIR", str(tmp_path))
    # Abort right after store construction — we only test root selection.
    monkeypatch.setattr(gf, "get_sector_weights",
                        lambda s: (_ for _ in ()).throw(RuntimeError("stop-here")))
    with pytest.raises(RuntimeError, match="stop-here"):
        gf.generate_forecast("PAPERCO", sector="pharma", paper=True)
    assert captured["base_dir"] == str(tmp_path)


def test_generate_forecast_paper_never_persists_weight_memory(monkeypatch, tmp_path):
    """Spec §6.3 check: no *weight_memory* files ever land in the paper root —
    the non-paper path bootstraps + saves defaults, the paper path must not."""
    import core.intelligence.rl.workflows.generate_forecast as gf

    monkeypatch.setattr(gf.settings, "PAPER_PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf, "get_sector_weights",
                        lambda s: {"risk": 0.5, "fundamentals": 0.5})
    # Abort right after the weights block — the next call in the flow.
    monkeypatch.setattr(gf, "_run_orchestrator_analysis",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop-here")))

    with pytest.raises(RuntimeError, match="stop-here"):
        gf.generate_forecast("PAPERCO", sector="pharma", paper=True)

    assert not list(tmp_path.rglob("*weight_memory*"))
