"""Compass Phase A — event-triggered post-review pipeline + EOD digest."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.portfolio.digest import build_digest
from core.portfolio.store import PortfolioStore
import core.delivery.alerts as alerts_mod
import core.delivery.channels as channels_mod
import core.portfolio.pipeline as pipeline

REVIEW_DATE = date(2026, 7, 6)


def _holding(symbol="MARUTI", price=12000.0, qty=10) -> Holding:
    return Holding(
        symbol=symbol, sector="automobile", qty=qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=qty, buy_date="2026-01-05",
    )


def _advice(symbol="MARUTI", verdict="HOLD") -> AdviceRecord:
    return AdviceRecord(
        date="2026-07-06", user_id="u", symbol=symbol, verdict=verdict,
        close=13000.0, unrealised_pnl_pct=8.33, stop_pct=10.0,
        narrative="Thesis intact.",
    )


def test_build_digest_totals_and_escalations():
    p = Portfolio(user_id="u", holdings=[_holding()])
    d = build_digest("u", REVIEW_DATE, [_advice(verdict="TRIM")], p, {"MARUTI": 13000.0})
    assert d["date"] == "2026-07-06"
    assert d["portfolio_value"] == pytest.approx(130000.0)
    assert d["cost_basis"] == pytest.approx(120000.0)
    assert d["total_pnl_pct"] == pytest.approx(130000.0 / 120000.0 * 100 - 100)
    assert d["escalations"] == ["MARUTI"]
    assert d["holdings"][0]["verdict"] == "TRIM"


def test_build_digest_missing_close_excluded_from_totals():
    p = Portfolio(user_id="u", holdings=[_holding(), _holding(symbol="NOPRICE")])
    d = build_digest("u", REVIEW_DATE, [_advice()], p, {"MARUTI": 13000.0})
    assert d["cost_basis"] == pytest.approx(120000.0)     # only the priced holding
    assert d["total_pnl_pct"] == pytest.approx(130000.0 / 120000.0 * 100 - 100)


def test_pipeline_skips_non_trading_day(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: False)
    result = pipeline.run_post_review_pipeline(REVIEW_DATE)
    assert result["status"] == "not_trading_day"


def test_pipeline_end_to_end(monkeypatch, tmp_path):
    # One user, one holding; every external surface faked.
    store = PortfolioStore(user_id="u", base_dir=str(tmp_path))
    store.add_holding(_holding())

    monkeypatch.setattr(pipeline.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: {"applied": 0, "symbols": []})
    monkeypatch.setattr(pipeline, "refresh_events_calendar", lambda syms, cache_path=None: {"events": {}})
    monkeypatch.setattr(pipeline, "load_events_calendar", lambda cache_path=None: {"events": {}})
    monkeypatch.setattr(pipeline, "close_on", lambda sym, d: 13000.0)
    monkeypatch.setattr(pipeline, "get_price_history", lambda t, years=1: None)
    monkeypatch.setattr(pipeline, "narrate", lambda rec, sig: "Thesis intact.")
    # Step 5 delivery is real by default (delivery.enabled: true) — keep hermetic
    # regardless of what verdict the advisor computes (see test_delivery_alerts.py
    # for emit_alerts' own dedupe/persist behaviour).
    monkeypatch.setattr(alerts_mod, "emit_alerts", lambda *a, **k: {"emitted": 0})
    delivered_kwargs = {}
    monkeypatch.setattr(channels_mod, "deliver",
                        lambda *a, **k: delivered_kwargs.update(k) or {"delivered": False})

    class _FakePredStore:
        def __init__(self, ticker, sector=None):
            pass
        def cycle_id_for(self, d):
            return "X_2026-07"
        def load_envelope(self, cid):
            return None
        def load_feedback_log(self, cid):
            return None
    monkeypatch.setattr(pipeline, "PredictionStore", _FakePredStore)

    result = pipeline.run_post_review_pipeline(REVIEW_DATE)
    assert result["status"] == "completed"
    assert result["users"] == 1 and result["advice"] == 1

    # Ledger got the record with the user id filled in
    records = store.load_advice()
    assert len(records) == 1 and records[0].user_id == "u"
    assert records[0].narrative == "Thesis intact."
    # Digest persisted
    digest = store.load_latest_digest()
    assert digest is not None and digest["date"] == REVIEW_DATE.isoformat()
    assert delivered_kwargs.get("url") == "/#/inbox/digest"


def test_pipeline_holding_failure_is_non_fatal(monkeypatch, tmp_path):
    store = PortfolioStore(user_id="u", base_dir=str(tmp_path))
    store.add_holding(_holding(symbol="GOODSTK"))
    store.add_holding(_holding(symbol="BADSTK"))

    monkeypatch.setattr(pipeline.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: {"applied": 0, "symbols": []})
    monkeypatch.setattr(pipeline, "refresh_events_calendar", lambda syms, cache_path=None: {"events": {}})
    monkeypatch.setattr(pipeline, "load_events_calendar", lambda cache_path=None: {"events": {}})
    monkeypatch.setattr(pipeline, "get_price_history", lambda t, years=1: None)
    monkeypatch.setattr(pipeline, "narrate", lambda rec, sig: "")
    monkeypatch.setattr(alerts_mod, "emit_alerts", lambda *a, **k: {"emitted": 0})
    monkeypatch.setattr(channels_mod, "deliver", lambda *a, **k: {"delivered": False})

    def close_or_boom(sym, d):
        if sym == "BADSTK":
            raise RuntimeError("no price")
        return 13000.0
    monkeypatch.setattr(pipeline, "close_on", close_or_boom)

    class _FakePredStore:
        def __init__(self, ticker, sector=None):
            pass
        def cycle_id_for(self, d):
            return "X_2026-07"
        def load_envelope(self, cid):
            return None
        def load_feedback_log(self, cid):
            return None
    monkeypatch.setattr(pipeline, "PredictionStore", _FakePredStore)

    result = pipeline.run_post_review_pipeline(REVIEW_DATE)
    assert result["status"] == "completed"
    assert result["advice"] == 1          # GOODSTK advised, BADSTK skipped
