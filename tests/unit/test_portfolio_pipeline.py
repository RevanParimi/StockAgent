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
    monkeypatch.setattr(pipeline, "VerdictStore", _FakePredStore)  # Atlas C2 plane-boundary swap

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
    monkeypatch.setattr(pipeline, "VerdictStore", _FakePredStore)  # Atlas C2 plane-boundary swap

    result = pipeline.run_post_review_pipeline(REVIEW_DATE)
    assert result["status"] == "completed"
    assert result["advice"] == 1          # GOODSTK advised, BADSTK skipped


# -- the SWITCH alert has to carry the case too (2026-08-20) ----------------

def test_advice_alert_fields_state_the_case_for_a_switch():
    from backend.shared.schemas.portfolio import AdviceRecord
    from core.portfolio.pipeline import advice_alert_fields

    rec = AdviceRecord(date="2026-08-18", user_id="u", symbol="TATAMOTORS",
                       verdict="SWITCH", close=642.0, unrealised_pnl_pct=-8.7,
                       stop_pct=6.0, confidence=0.42, switch_candidate="NEWCO",
                       triggers=["stop_breach", "switch_candidate_available"],
                       narrative="The JLR demand warning broke the thesis.")

    class _Idea:
        symbol, sector, conviction = "NEWCO", "pharma", 0.81
        thesis = "Margin inflection on the API ramp."
        entry_low = entry_high = invalidation_level = 0.0

    f = advice_alert_fields(rec, {"NEWCO": _Idea()})
    assert f["title"] == "Switch — TATAMOTORS"
    assert f["headline"] == "The JLR demand warning broke the thesis."
    assert "-8.7%" in f["status"] and "6.0%" in f["status"]
    assert "NEWCO" in f["next_step"]
    assert "Margin inflection on the API ramp." in f["next_step"]


def test_advice_alert_falls_back_to_triggers_without_a_narrative():
    from backend.shared.schemas.portfolio import AdviceRecord
    from core.portfolio.pipeline import advice_alert_fields

    rec = AdviceRecord(date="2026-08-18", user_id="u", symbol="TATAMOTORS",
                       verdict="EXIT", close=642.0, unrealised_pnl_pct=-8.7,
                       stop_pct=6.0, triggers=["stop_breach"])
    f = advice_alert_fields(rec, {})
    assert "stop was breached" in f["headline"]
    assert f["next_step"] == ""          # no candidate, nothing to point at


def test_advice_alert_switch_survives_a_destination_off_the_shelf():
    from backend.shared.schemas.portfolio import AdviceRecord
    from core.portfolio.pipeline import advice_alert_fields

    rec = AdviceRecord(date="2026-08-18", user_id="u", symbol="TATAMOTORS",
                       verdict="SWITCH", close=642.0, unrealised_pnl_pct=-8.7,
                       stop_pct=6.0, switch_candidate="GONE",
                       triggers=["stop_breach"])
    f = advice_alert_fields(rec, {})
    assert f["next_step"] == "Replacement idea: GONE."


# -- switch-evaluation capture (2026-08-20) --------------------------------

def _sig(symbol="OLDCO", sector="automobile", confidence=0.5):
    from core.portfolio.advisor import AdvisorSignals
    return AdvisorSignals(symbol=symbol, sector=sector, close=100.0,
                          atr_stop_pct=12.0, unrealised_pnl_pct=-15.0,
                          holding_age_days=100, confidence=confidence)


def _shelf(symbol, sector, conviction):
    from backend.shared.schemas.discovery import ShelfIdea
    return ShelfIdea(symbol=symbol, sector=sector, added="2026-07-01",
                     conviction=conviction)


def _switch_advice(symbol="OLDCO", verdict="HOLD"):
    from backend.shared.schemas.portfolio import AdviceRecord
    return AdviceRecord(date="2026-08-20", user_id="u1", symbol=symbol,
                        verdict=verdict, close=100.0, unrealised_pnl_pct=-15.0,
                        stop_pct=12.0, rationale_hash="hash1")


def test_capture_produces_one_row_per_candidate_with_both_prices():
    from datetime import date
    from core.portfolio.pipeline import capture_switch_evaluations
    rows = capture_switch_evaluations(
        _switch_advice(), _sig(), [_shelf("NEWCO", "pharma", 0.9)],
        {"automobile": 60.0, "pharma": 5.0}, {"OLDCO"},
        {"NEWCO": 250.0}, "u1", date(2026, 8, 20))
    assert len(rows) == 1
    r = rows[0]
    assert r.origin == "OLDCO" and r.candidate == "NEWCO"
    assert r.origin_close == 100.0 and r.candidate_close == 250.0
    assert r.decision == "taken"
    assert r.rationale_hash == "hash1"
    assert r.origin_verdict == "HOLD"


def test_capture_happens_for_a_HOLD_not_only_an_EXIT():
    """The whole reframe: evidence must accrue at the rate the rule EVALUATES,
    and it evaluates on every holding every run."""
    from datetime import date
    from core.portfolio.pipeline import capture_switch_evaluations
    rows = capture_switch_evaluations(
        _switch_advice(verdict="HOLD"), _sig(), [_shelf("NEWCO", "pharma", 0.9)],
        {"automobile": 60.0, "pharma": 5.0}, {"OLDCO"},
        {"NEWCO": 250.0}, "u1", date(2026, 8, 20))
    assert rows and rows[0].origin_verdict == "HOLD"


def test_an_unpriceable_candidate_is_dropped_not_guessed():
    from datetime import date
    from core.portfolio.pipeline import capture_switch_evaluations
    rows = capture_switch_evaluations(
        _switch_advice(), _sig(), [_shelf("NEWCO", "pharma", 0.9),
                            _shelf("NOPRICE", "metals", 0.9)],
        {"automobile": 60.0, "pharma": 5.0, "metals": 5.0}, {"OLDCO"},
        {"NEWCO": 250.0}, "u1", date(2026, 8, 20))
    assert [r.candidate for r in rows] == ["NEWCO"]


def test_capture_is_a_no_op_when_the_flag_is_off(monkeypatch):
    from datetime import date
    import core.portfolio.pipeline as pl
    monkeypatch.setattr(pl, "_switch_eval_enabled", lambda: False)
    rows = pl.capture_switch_evaluations(
        _switch_advice(), _sig(), [_shelf("NEWCO", "pharma", 0.9)],
        {"automobile": 60.0, "pharma": 5.0}, {"OLDCO"},
        {"NEWCO": 250.0}, "u1", date(2026, 8, 20))
    assert rows == []
