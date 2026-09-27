"""SA-003 — no new risk on missing, unresolved or stale essential data.

Independent invariants:

- End to end (the card's fixture): provider no-data -> real bundle -> real
  aggregator verdict -> real month-start forecast -> real advisor pipeline ->
  real autopilot. In record mode the chain reproduces F08: the abstained
  STRONG BUY becomes an UP envelope, an ADD and a BUY. In enforce mode the
  same providers produce no envelope and no new-risk transaction. With
  healthy providers, enforce still buys — the gate is not a rule that never
  passes.
- ADD and a SWITCH's buy leg need a close dated the review session and a
  forecast issued on actionable data. A close from the previous day's bar
  is not fresh: that is the exact boundary.
- Risk reduction is specified: EXIT and TRIM fire and execute on a stale
  close or an unverified forecast, and the advice records what they rest on.
- Every withheld action is recorded on the user's own advice record with its
  reasons and source run ids (no user id reaches the shared gate log).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend.shared.schemas.discovery import Shelf, ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord, Holding
# Bound at import: the SA-002 `market` fixture replaces the class at its source
# module while a test runs (the bundle's dossier read), and the forecast and
# the advisor must use the real store here.
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.portfolio.advisor import (
    AdvisorSignals,
    data_gate_blocks,
    decide,
    evaluate_switch_candidates,
    forecast_rows_gate,
)
from core.portfolio.pricing import SessionClose
from core.portfolio.store import PortfolioStore
from tests.unit.shared.test_decision_gate_sa003 import (  # noqa: F401 — fixtures
    _analyse,
    _price_source_404,
    fresh_db,
    gate_mode,
    market,
    no_network,
)

TODAY = date.today()


def _holding(symbol="TATAMOTORS", qty=10.0, price=100.0, sector="automobile"):
    return Holding(symbol=symbol, sector=sector, qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date="2026-06-01")


def _add_signals(**over) -> AdvisorSignals:
    """Everything an ADD needs: UP envelope, healthy accuracy, small weight,
    no stop breach, no profit to trim."""
    base = dict(symbol="TATAMOTORS", sector="automobile", close=100.0, atr_stop_pct=8.0,
                unrealised_pnl_pct=0.0, holding_age_days=100, envelope_direction="UP",
                direction_accuracy_7d=0.8, position_weight_pct=2.0, confidence=0.6,
                forecast_gate="actionable", forecast_run_ids=["month-run"])
    base.update(over)
    return AdvisorSignals(**base)


# ---------------------------------------------------------------------------
# The advisor rule (pure)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("statuses, expected", [
    ([], "none"), (["actionable"] * 3, "actionable"), (["actionable", "degraded"], "degraded"),
    (["actionable", ""], ""), (["", "abstain"], "abstain"), (["degraded", "abstain"], "abstain"),
])
def test_forecast_rows_gate_is_the_worst_row(statuses, expected):
    assert forecast_rows_gate(statuses) == expected


@pytest.mark.parametrize("signals, reason_part", [
    (_add_signals(price_fresh=False, price_bar_date="2026-09-24"), "from bar 2026-09-24"),
    (_add_signals(forecast_gate="abstain"), "with data gate abstain"),
    (_add_signals(forecast_gate=""), "before the data gate existed"),
    (_add_signals(forecast_gate="none"), "no forecast rows"),
])
def test_add_is_blocked_on_unverified_inputs(signals, reason_part):
    reasons, _ = data_gate_blocks(signals)
    assert any(reason_part in r for r in reasons), reasons
    rec = decide(signals, _holding(), "moderate", add_blocks=reasons)
    assert rec.verdict == "HOLD" and "DATA_GATE" in rec.notes
    assert decide(signals, _holding(), "moderate").verdict == "ADD"    # ungated control


def test_verified_inputs_block_nothing():
    assert data_gate_blocks(_add_signals()) == ([], {})
    assert data_gate_blocks(_add_signals(forecast_gate="degraded")) == ([], {})


@pytest.mark.parametrize("over, verdict, trigger", [
    # EXIT: the stop is breached on the last available close.
    (dict(unrealised_pnl_pct=-12.0), "EXIT", "stop_breach"),
    # TRIM: in profit while confidence falls.
    (dict(unrealised_pnl_pct=30.0, confidence_trend=-0.2), "TRIM",
     "trim_profit_confidence_decline"),
])
def test_risk_reduction_is_never_blocked(over, verdict, trigger):
    """Missing data must not trap a position: EXIT/TRIM fire on a stale close
    and an abstained forecast exactly as on verified ones."""
    signals = _add_signals(price_fresh=False, price_bar_date="2026-09-24",
                           forecast_gate="abstain", holding_age_days=400, **over)
    reasons, _ = data_gate_blocks(signals)
    assert reasons
    rec = decide(signals, _holding(), "moderate", add_blocks=reasons)
    assert rec.verdict == verdict and trigger in rec.triggers
    assert "DATA_GATE" not in rec.notes


def _idea(symbol, conviction=0.9, sector="realty", data_gate="actionable"):
    return ShelfIdea(symbol=symbol, sector=sector, added="2026-09-01",
                     conviction=conviction, data_gate=data_gate)


def test_a_blocked_switch_destination_falls_back_to_the_next_or_plain_exit():
    exiting = _add_signals(unrealised_pnl_pct=-12.0, sector="automobile", confidence=0.3)
    weights = {"automobile": 60.0, "realty": 5.0, "pharma": 5.0}
    ideas = [_idea("LODHA", 0.95), _idea("SUNPHARMA", 0.9, sector="pharma")]

    ungated = decide(exiting, _holding(), "moderate", shelf_ideas=ideas, sector_weights=weights)
    assert (ungated.verdict, ungated.switch_candidate) == ("SWITCH", "LODHA")

    one = decide(exiting, _holding(), "moderate", shelf_ideas=ideas, sector_weights=weights,
                 blocked_candidates={"LODHA": "no close dated the review session"})
    assert (one.verdict, one.switch_candidate) == ("SWITCH", "SUNPHARMA")

    both = decide(exiting, _holding(), "moderate", shelf_ideas=ideas, sector_weights=weights,
                  blocked_candidates={"LODHA": "x", "SUNPHARMA": "y"})
    assert both.verdict == "EXIT" and "DATA_GATE" in both.notes   # the sell still happens

    _, rows = evaluate_switch_candidates(exiting, ideas, weights,
                                         blocked={"LODHA": "x", "SUNPHARMA": "y"})
    assert [r["reason"] for r in rows] == ["data_gate", "data_gate"]


def test_shelf_ideas_from_before_the_gate_and_stale_candidates_are_blocked():
    ideas = [_idea("OLDIDEA", data_gate=""), _idea("ABSTAINED", data_gate="abstain"),
             _idea("STALE"), _idea("NOQUOTE"), _idea("GOOD")]
    _, blocked = data_gate_blocks(_add_signals(), ideas,
                                  candidate_fresh={"STALE": False, "GOOD": True})
    assert set(blocked) == {"OLDIDEA", "ABSTAINED", "STALE"}
    # NOQUOTE: never priced here; the autopilot checks its session price.


def test_gated_decide_record_keeps_the_add_and_says_it_would_block(gate_mode):
    from core.portfolio.pipeline import gated_decide
    signals = _add_signals(forecast_gate="abstain", forecast_run_ids=["month-run"])

    gate_mode("record")
    rec, passed = gated_decide(signals, _holding(), "moderate", shelf_ideas=[],
                               sector_weights={}, held_symbols={"TATAMOTORS"},
                               candidate_fresh={})
    assert rec.verdict == "ADD" and passed is None
    assert rec.data_gate["enforced"] is False and rec.data_gate["blocked"] == "ADD"
    assert rec.data_gate["gated_verdict"] == "HOLD"
    assert rec.data_gate["source_run_ids"] == ["month-run"]

    gate_mode("enforce")
    rec, _ = gated_decide(signals, _holding(), "moderate", shelf_ideas=[],
                          sector_weights={}, held_symbols={"TATAMOTORS"}, candidate_fresh={})
    assert rec.verdict == "HOLD" and "DATA_GATE" in rec.notes
    assert rec.data_gate["enforced"] is True and rec.data_gate["blocked"] == "ADD"
    assert any("month-run" in r for r in rec.data_gate["reasons"])


def test_an_exit_on_a_stale_close_is_annotated_not_blocked(gate_mode):
    from core.portfolio.pipeline import gated_decide
    gate_mode("enforce")
    signals = _add_signals(unrealised_pnl_pct=-12.0, price_fresh=False,
                           price_bar_date="2026-09-24")
    rec, _ = gated_decide(signals, _holding(), "moderate", shelf_ideas=[], sector_weights={},
                          held_symbols={"TATAMOTORS"}, candidate_fresh={})
    assert rec.verdict == "EXIT"
    assert rec.data_gate["blocked"] is None and rec.data_gate["price_bar_date"] == "2026-09-24"
    assert "never blocked" in rec.data_gate["note"]


# ---------------------------------------------------------------------------
# The executor's own last check on a SWITCH buy leg
# ---------------------------------------------------------------------------

def _switch_store(tmp_path):
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = (
        [_holding()], 20000.0, 100000.0, True)
    s.save(p)
    return s


@pytest.mark.parametrize("mode, bar_offset, bought", [
    ("enforce", 0, True), ("enforce", 1, False), ("record", 1, True),
])
def test_switch_buy_leg_needs_the_sessions_close(tmp_path, monkeypatch, gate_mode,
                                                 mode, bar_offset, bought):
    import core.portfolio.autopilot as ap
    review = date(2026, 7, 13)                      # a Monday
    monkeypatch.setattr(ap, "_today_ist", lambda: review)
    monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(ap, "session_close", lambda sym, d: (
        SessionClose(200.0, review - timedelta(days=bar_offset), "agree"), review))
    gate_mode(mode)
    s = _switch_store(tmp_path)
    switch = AdviceRecord(date=review.isoformat(), user_id="t1", symbol="TATAMOTORS",
                          verdict="SWITCH", close=110.0, unrealised_pnl_pct=-9.0,
                          stop_pct=8.0, confidence=0.4, switch_candidate="LODHA",
                          triggers=["stop_breach", "switch_candidate_available"],
                          rationale_hash="sw1")

    txns = ap.execute_advice(s, s.load(), [switch], {"TATAMOTORS": 110.0}, review,
                             sector_lookup={"LODHA": "realty"})

    sides = [(t.side, t.symbol) for t in txns]
    assert ("SELL", "TATAMOTORS") in sides                     # the exit always executes
    assert (("BUY", "LODHA") in sides) is bought


# ---------------------------------------------------------------------------
# End to end: provider no-data -> bundle -> verdict -> forecast -> advice -> executor
# ---------------------------------------------------------------------------

BIG = "BIGCO"


def _chain(market, monkeypatch, tmp_path, *, tatamotors_bar=None, then_mode=None):
    """Analyse TATAMOTORS through the real orchestrator, build its month
    envelope with the real generate_forecast, then run the real post-review
    pipeline and autopilot for one user holding a small TATAMOTORS position
    (2% of the book, so an ADD is allowed) and a large BIGCO one.

    `then_mode` switches the gate between the forecast and the pipeline (the
    switch flipped with a record-era envelope still live).

    Returns (report, forecast_error, advice_by_symbol, transactions).
    """
    import core.portfolio.autopilot as ap
    import core.portfolio.pipeline as pipeline
    from core.config import settings
    from core.intelligence.rl.workflows import generate_forecast as gf
    from core.schemas.feedback import DailyFeedbackLog, FeedbackEntry

    monkeypatch.setenv("ATLAS_ENABLED", "false")          # fan out by directory scan
    pred_dir, port_dir = tmp_path / "predictions", tmp_path / "portfolio"
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(pred_dir))
    monkeypatch.setattr(pipeline.settings, "PORTFOLIO_DATA_DIR", str(port_dir))

    # 1-3. providers -> bundle -> aggregator verdict (tests/unit/shared/...)
    report = _analyse(market, monkeypatch, tmp_path)

    # 4. the month-start forecast built on that report
    monkeypatch.setattr(gf, "_run_orchestrator_analysis", lambda t, s, w: report)
    monkeypatch.setattr(gf, "_fetch_actual_close", lambda ticker: 100.0)
    monkeypatch.setattr(gf, "_compute_forecast_profile", lambda *a, **k: (None, "NORMAL"))
    monkeypatch.setattr(gf, "_fetch_fno_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(gf, "PromptEnhancer", type("E", (), {"enhance": lambda s, *a, **k: {}}))
    forecast_error = None
    try:
        gf.generate_forecast("TATAMOTORS", sector="automobile")
    except gf.InsufficientDataError as exc:
        forecast_error = exc
    # Five correct calls this cycle: the accuracy an ADD needs.
    store = PredictionStore("TATAMOTORS", sector="automobile", base_dir=str(pred_dir))
    store.save_feedback_log(DailyFeedbackLog(
        ticker="TATAMOTORS", cycle_id=store.cycle_id_for(TODAY), entries=[
            FeedbackEntry(day=i, date=(TODAY - timedelta(days=i)).isoformat(),
                          predicted_close=100.0, actual_close=101.0, price_error_pct=1.0,
                          predicted_verdict="BUY", actual_direction="UP",
                          direction_correct=True)
            for i in range(5, 0, -1)]))

    # 5-6. the user, the pipeline and the executor
    user = PortfolioStore(user_id="u", base_dir=str(port_dir))
    p = user.load()
    p.holdings = [_holding(qty=10.0, price=100.0), _holding(BIG, qty=50.0, price=1000.0)]
    p.cash_deployable, p.capital_in, p.autopilot = 50000.0, 100000.0, True
    user.save(p)
    bars = {"TATAMOTORS": tatamotors_bar or TODAY, BIG: TODAY}
    closes = {"TATAMOTORS": 100.0, BIG: 1000.0}
    monkeypatch.setattr(pipeline, "session_close", lambda sym, d: (
        SessionClose(closes[sym], bars[sym], "agree"), d))
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: {"applied": 0})
    monkeypatch.setattr(pipeline, "refresh_events_calendar", lambda syms: {"events": {}})
    monkeypatch.setattr(pipeline, "get_price_history", lambda t, years=1: None)
    monkeypatch.setattr(pipeline, "narrate", lambda rec, sig: "n")
    monkeypatch.setattr("core.discovery.shelf.ShelfStore.load", lambda self: Shelf())
    monkeypatch.setattr("core.delivery.alerts.emit_alerts", lambda *a, **k: {"emitted": 0})
    monkeypatch.setattr("core.delivery.channels.deliver", lambda *a, **k: {"delivered": False})
    monkeypatch.setattr(ap, "_today_ist", lambda: TODAY)
    if then_mode is not None:
        monkeypatch.setattr(settings, "DECISION_GATE_MODE", then_mode)

    result = pipeline.run_post_review_pipeline(TODAY)
    assert result["status"] == "completed" and result["advice"] == 2
    advice = {a.symbol: a for a in user.load_advice()}
    return report, forecast_error, advice, user.load_transactions()


def _buys(txns):
    return [(t.symbol, t.qty) for t in txns if t.side == "BUY"]


def test_record_mode_reproduces_f08_a_withheld_strong_buy_becomes_a_buy(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """The control that makes the enforce test meaningful: this fixture does
    reach a new-risk transaction when nothing enforces the gate."""
    _price_source_404(market)
    gate_mode("record")

    report, forecast_error, advice, txns = _chain(market, monkeypatch, tmp_path)

    assert report.verdict == "STRONG BUY" and report.decision_gate.status == "abstain"
    assert forecast_error is None                              # envelope built on it
    assert advice["TATAMOTORS"].verdict == "ADD"
    assert advice["TATAMOTORS"].data_gate["blocked"] == "ADD"   # ... and said so
    assert advice["TATAMOTORS"].data_gate["enforced"] is False
    assert _buys(txns) == [("TATAMOTORS", 2.0)]                 # 25% tranche of ₹1,000 at ₹100
    assert no_network == []


def test_enforce_provider_no_data_produces_no_new_risk_transaction(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """The card's fixture: provider no-data -> bundle -> verdict -> advice ->
    executor produces no new-risk transaction."""
    _price_source_404(market)
    gate_mode("enforce")

    report, forecast_error, advice, txns = _chain(market, monkeypatch, tmp_path)

    assert report.verdict == "INSUFFICIENT DATA"
    assert isinstance(forecast_error, Exception)               # no envelope built
    assert report.decision_gate.run_id in str(forecast_error)
    assert advice["TATAMOTORS"].verdict == "HOLD"
    assert _buys(txns) == []
    gate_log = [json.loads(line) for line in
                (tmp_path / "decision_gate.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["consumer"] for r in gate_log] == ["analysis", "forecast"]
    assert {r["source_run_id"] for r in gate_log} == {report.decision_gate.run_id}
    assert all("user_id" not in r for r in gate_log)          # ticker-level only
    assert no_network == []


def test_enforce_blocks_an_add_on_an_envelope_built_before_enforcement(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """The switch flips mid-month: the envelope was built (in record mode) on
    an abstained analysis. Its rows say so, and the advisor will not add."""
    _price_source_404(market)
    gate_mode("record")

    report, forecast_error, advice, txns = _chain(market, monkeypatch, tmp_path,
                                                  then_mode="enforce")

    assert forecast_error is None                  # built while recording
    latest = advice["TATAMOTORS"]
    assert latest.verdict == "HOLD" and "DATA_GATE" in latest.notes
    assert latest.data_gate["enforced"] is True and latest.data_gate["blocked"] == "ADD"
    assert latest.data_gate["source_run_ids"] == [report.decision_gate.run_id]
    assert _buys(txns) == []
    assert no_network == []


def test_enforce_healthy_providers_still_buy(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    gate_mode("enforce")
    report, forecast_error, advice, txns = _chain(market, monkeypatch, tmp_path)
    assert report.decision_gate.status == "actionable"
    assert forecast_error is None
    assert advice["TATAMOTORS"].verdict == "ADD" and advice["TATAMOTORS"].data_gate is None
    assert _buys(txns) == [("TATAMOTORS", 2.0)]
    assert no_network == []


def test_enforce_a_carried_forward_close_blocks_the_add(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """Healthy analysis, but the holding's close is yesterday's bar."""
    gate_mode("enforce")
    _, _, advice, txns = _chain(market, monkeypatch, tmp_path,
                                tatamotors_bar=TODAY - timedelta(days=1))
    assert advice["TATAMOTORS"].verdict == "HOLD"
    assert advice["TATAMOTORS"].data_gate["price_bar_date"] == \
        (TODAY - timedelta(days=1)).isoformat()
    assert _buys(txns) == []
    assert no_network == []
