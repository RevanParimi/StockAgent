"""SA-004 integration — the persisted job outcome agrees with the feedback store.

The scheduled job runs the REAL run_daily_review over real PredictionStores
(LLM agents, price and news sources faked; network refused). Afterwards the
record in scheduler_job_outcomes.json is checked against the feedback rows
actually stored: a ticker counts as output if and only if a FeedbackEntry
dated the review session exists for it. The 2026-09-08 production record
failed exactly this check (produced=20, 19 feedback rows).

Cohort (Tue 15 Sep, reviewed on Wed 16 Sep):
    GOOD1, GOOD2  actionable forecast row, fresh close        -> completed
    PREGATE       row issued before the data gate (gate "")   -> degraded in
                  record mode (it learns), data_gated in enforce (it does not)
    NOENV         no envelope for the cycle                   -> skipped
    NOCLOSE       no close for the session                    -> skipped
    BOOM          the close fetch raises                      -> failed
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import DailyForecast, PredictionEnvelope
from tests.unit.intelligence.rl.test_learning_mode_sa039 import no_network  # noqa: F401
from tests.unit.intelligence.rl.test_shock_path import _fb_output, _patch_common

SECTOR = "automobile"
TODAY = datetime(2026, 9, 16, 16, 30)
REVIEW = date(2026, 9, 15)
CYCLE_MONTH = "2026-09"
ENVELOPED = {"GOOD1": "actionable", "GOOD2": "actionable", "PREGATE": "",
             "NOCLOSE": "actionable", "BOOM": "actionable"}
TICKERS = ["GOOD1", "GOOD2", "PREGATE", "NOENV", "NOCLOSE", "BOOM"]


def _envelope(ticker: str, gate: str) -> PredictionEnvelope:
    scores = {"risk_macro": 0.5, "sales_demand": 0.5}
    return PredictionEnvelope(
        ticker=ticker, sector=SECTOR, cycle_id=f"{ticker}_{CYCLE_MONTH}",
        generated_at="2026-09-01T09:00:00", base_close=100.0,
        daily_forecasts=[
            DailyForecast(day=d, date=f"2026-09-{14 + d}", predicted_close=100.0 + d,
                          predicted_verdict="BUY", predicted_agent_scores=scores,
                          confidence=0.5, data_gate=gate, source_run_id="month-run")
            for d in (1, 2)
        ],
    )


@pytest.fixture
def scheduled(tmp_path, monkeypatch, no_network):  # noqa: F811
    import core.delivery.alerts as al
    import core.intelligence.rl.nse_calendar as cal
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    import core.intelligence.rl.workflows.daily_review as dr
    import core.portfolio.pipeline as pl
    import services.data.stores.job_outcomes as jo
    import services.scheduler.python.scheduler as sch
    from backend.shared.pipeline import decision_gate as dg
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    from core.schemas.feedback import RegimeSnapshot

    for ticker, gate in ENVELOPED.items():
        PredictionStore(ticker, sector=SECTOR, base_dir=tmp_path).save_envelope(
            _envelope(ticker, gate))

    _patch_common(dr, monkeypatch, tmp_path)

    def _close(ticker, day):
        if ticker == "BOOM":
            raise RuntimeError("price source down")
        if ticker == "NOCLOSE":
            return dr.SessionClose(None, None, "none")
        return dr.SessionClose(98.0, day, "agree")
    monkeypatch.setattr(dr, "_fetch_session_close", _close)
    monkeypatch.setattr(offmarket_mod.OffMarketFetcher, "__init__",
                        lambda self: setattr(self, "_nse", None))
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", False)
    monkeypatch.setattr(dr.settings, "REGIME_MULTIPLIERS", {})
    monkeypatch.setattr(dr.RegimeDetector, "detect",
                        lambda self, d, s: RegimeSnapshot(multipliers={}))
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: False)
    monkeypatch.setattr(FeedbackAgent, "run",
                        lambda self, fb_input, ledger: _fb_output("model_bias"))

    monkeypatch.setattr(cal, "now_ist", lambda: TODAY)
    monkeypatch.setattr(pl, "run_post_review_pipeline", lambda d: {"status": "completed"})
    alerts: list = []
    monkeypatch.setattr(al, "emit_alerts_broadcast",
                        lambda events, **kw: alerts.extend(events) or {"emitted": len(events)})
    monkeypatch.setattr(sch, "get_active_tickers_with_sector",
                        lambda: [{"sym": t, "sector": SECTOR} for t in TICKERS])
    monkeypatch.setattr(sch, "get_disabled_tickers", lambda: [])
    dg._warned.clear()

    def run(gate_mode: str = "record") -> dict:
        monkeypatch.setattr(dr.settings, "DECISION_GATE_MODE", gate_mode)
        sch.AutomobileScheduler()._daily_review_job()
        return jo.load_job_outcomes()["daily_review"]

    run.alerts = alerts
    run.no_network = no_network
    return run


def _stored_feedback_ids(tmp_path) -> list[str]:
    """ticker|date for every stored FeedbackEntry dated the review session —
    one row per (ticker, date), since append_feedback_entry replaces by date."""
    ids = []
    for ticker in TICKERS:
        log = PredictionStore(ticker, sector=SECTOR, base_dir=tmp_path).load_feedback_log(
            f"{ticker}_{CYCLE_MONTH}")
        ids += [f"{ticker}|{e.date}" for e in log.entries if e.date == REVIEW.isoformat()]
    return ids


def _recorded_output_ids(rec: dict) -> list[str]:
    return sorted(f"{t}|{rec['review_date']}" for t, v in rec["by_ticker"].items()
                  if v["outcome"] in ("completed", "degraded"))


def test_persisted_outcome_matches_stored_feedback(scheduled, tmp_path):
    rec = scheduled("record")

    stored = _stored_feedback_ids(tmp_path)
    assert sorted(stored) == _recorded_output_ids(rec) == [
        "GOOD1|2026-09-15", "GOOD2|2026-09-15", "PREGATE|2026-09-15"]
    assert rec["produced"] == len(stored) == 3
    assert rec["expected"] == rec["required"] == 6
    assert {t: v["outcome"] for t, v in rec["by_ticker"].items()} == {
        "GOOD1": "completed", "GOOD2": "completed", "PREGATE": "degraded",
        "NOENV": "skipped", "NOCLOSE": "skipped", "BOOM": "failed"}
    assert rec["missing"] == {"NOENV": "skipped: no_envelope",
                              "NOCLOSE": "skipped: no_actual_data",
                              "BOOM": "failed: exception: RuntimeError"}
    assert rec["by_ticker"]["PREGATE"]["reason"] == "data gate: forecast_row"
    assert (rec["status"], rec["pipeline_ok"]) == ("partial", False)
    assert [e.kind for e in scheduled.alerts] == ["job_partial_output_daily_review"]
    assert "3/6" in scheduled.alerts[0].message
    assert scheduled.no_network == []


def test_a_rerun_of_the_session_does_not_double_count(scheduled, tmp_path):
    """The Fri 2 Oct / Mon 5 Oct shape: the same session reviewed twice."""
    first = scheduled("record")
    second = scheduled("record")

    stored = _stored_feedback_ids(tmp_path)
    assert len(stored) == len(set(stored)) == 3            # one row per ticker-date
    assert second["produced"] == first["produced"] == len(stored)
    assert _recorded_output_ids(second) == sorted(stored)
    assert (second["attempted"], second["runs"], len(second["retried"])) == (12, 2, 6)


def test_enforce_stops_the_pre_gate_row_and_the_record_says_so(scheduled, tmp_path):
    rec = scheduled("enforce")

    stored = _stored_feedback_ids(tmp_path)
    assert sorted(stored) == _recorded_output_ids(rec) == [
        "GOOD1|2026-09-15", "GOOD2|2026-09-15"]
    assert rec["by_ticker"]["PREGATE"] == {
        "outcome": "data_gated", "reason": "data gate: forecast_row",
        "attempts": 1, "this_run": "data_gated"}
    assert (rec["produced"], rec["data_gated"]) == (2, 1)
