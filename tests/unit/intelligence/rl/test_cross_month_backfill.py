"""Cross-month backfill (2026-07-02): recover reviews for a past month.

Context: the RL loop was dead 2026-06-12 → 2026-07-02. The June envelope has
forecast rows through Jul 14, but reviews always resolved cycle_id from
date.today(), so June dates could never be scored once July started. These
tests cover the pieces that fix that:

  - PredictionStore.cycle_id_for(date)  — cycle derived from the review date
  - daily_review._resolve_cycle_and_forecast — previous-month envelope fallback
  - scheduler_api._trading_days_for_backfill(month=...) — past-month windows
  - run_logger.log_llm_call — mirrors every pipeline call into telemetry.db
"""
from datetime import date, timedelta

import pytest

from backend.shared.schemas.feedback import DailyForecast, PredictionEnvelope
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.workflows.daily_review import _resolve_cycle_and_forecast


def _make_store(tmp_path, ticker="MARUTI") -> PredictionStore:
    return PredictionStore(ticker, sector="automobile", base_dir=str(tmp_path))


def _envelope(ticker: str, cycle_id: str, dates: list[str]) -> PredictionEnvelope:
    return PredictionEnvelope(
        ticker=ticker,
        cycle_id=cycle_id,
        generated_at="2026-06-02T10:00:00+05:30",
        base_close=14000.0,
        daily_forecasts=[
            DailyForecast(day=i + 1, date=d, predicted_close=14000.0 + i,
                          predicted_verdict="NEUTRAL")
            for i, d in enumerate(dates)
        ],
    )


# ---------------------------------------------------------------------------
# PredictionStore.cycle_id_for
# ---------------------------------------------------------------------------

def test_cycle_id_for_uses_target_month(tmp_path):
    store = _make_store(tmp_path)
    assert store.cycle_id_for(date(2026, 6, 15)) == "MARUTI_2026-06"
    assert store.cycle_id_for(date(2026, 7, 1)) == "MARUTI_2026-07"
    assert store.cycle_id_for(date(2025, 12, 31)) == "MARUTI_2025-12"


def test_current_cycle_id_still_today(tmp_path):
    store = _make_store(tmp_path)
    assert store.current_cycle_id() == store.cycle_id_for(date.today())


# ---------------------------------------------------------------------------
# daily_review._resolve_cycle_and_forecast
# ---------------------------------------------------------------------------

def test_resolve_prefers_own_month_envelope(tmp_path):
    store = _make_store(tmp_path)
    store.save_envelope(_envelope("MARUTI", "MARUTI_2026-06", ["2026-06-15"]))
    cycle_id, envelope, forecast = _resolve_cycle_and_forecast(store, date(2026, 6, 15))
    assert cycle_id == "MARUTI_2026-06"
    assert envelope is not None and forecast is not None
    assert forecast.date == "2026-06-15"


def test_resolve_falls_back_to_previous_month_envelope(tmp_path):
    # June envelope carries rows into July; no July envelope row for Jul 1.
    store = _make_store(tmp_path)
    store.save_envelope(_envelope("MARUTI", "MARUTI_2026-06",
                                  ["2026-06-30", "2026-07-01", "2026-07-02"]))
    store.save_envelope(_envelope("MARUTI", "MARUTI_2026-07",
                                  ["2026-07-03", "2026-07-06"]))
    cycle_id, envelope, forecast = _resolve_cycle_and_forecast(store, date(2026, 7, 1))
    assert cycle_id == "MARUTI_2026-06"
    assert forecast is not None and forecast.date == "2026-07-01"


def test_resolve_no_row_anywhere_returns_none_forecast(tmp_path):
    store = _make_store(tmp_path)
    store.save_envelope(_envelope("MARUTI", "MARUTI_2026-07", ["2026-07-03"]))
    cycle_id, envelope, forecast = _resolve_cycle_and_forecast(store, date(2026, 7, 19))
    assert cycle_id == "MARUTI_2026-07"   # own month kept for the skip report
    assert envelope is not None
    assert forecast is None


def test_resolve_no_envelope_at_all(tmp_path):
    store = _make_store(tmp_path)
    cycle_id, envelope, forecast = _resolve_cycle_and_forecast(store, date(2026, 7, 1))
    assert cycle_id == "MARUTI_2026-07"
    assert envelope is None and forecast is None


# ---------------------------------------------------------------------------
# scheduler_api._trading_days_for_backfill
# ---------------------------------------------------------------------------

def test_backfill_days_default_is_current_month(monkeypatch):
    from services.api.routes import scheduler_api
    days = scheduler_api._trading_days_for_backfill(None)
    today = date.today()
    assert all(d.month == today.month and d.year == today.year for d in days)
    assert all(d < today for d in days)


def test_backfill_days_past_month_full_window():
    from services.api.routes import scheduler_api
    days = scheduler_api._trading_days_for_backfill("2026-06")
    assert days[0] >= date(2026, 6, 1)
    assert days[-1] <= date(2026, 6, 30)
    assert all(d.weekday() < 5 for d in days)     # no weekends
    assert len(days) >= 18                        # June 2026 has 20+ weekdays
    # The dead-scheduler window Jun 13-30 must be recoverable
    assert any(d >= date(2026, 6, 15) for d in days)


def test_backfill_days_bad_month_raises():
    from services.api.routes import scheduler_api
    with pytest.raises((ValueError, IndexError)):
        scheduler_api._trading_days_for_backfill("junk")


# ---------------------------------------------------------------------------
# scheduler_api._has_feedback_entry — skip_existing recovery mode
# ---------------------------------------------------------------------------

def test_has_feedback_entry_checks_own_and_previous_cycle(tmp_path, monkeypatch):
    from backend.shared.schemas.feedback import DailyFeedbackLog, FeedbackEntry
    from services.api.routes import scheduler_api
    from core.config import settings

    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    store = _make_store(tmp_path)

    def _entry(d):
        return FeedbackEntry(day=1, date=d, predicted_close=1.0, actual_close=1.0,
                             price_error_pct=0.0, predicted_verdict="NEUTRAL",
                             actual_direction="FLAT", direction_correct=True)

    # Jul 1 entry lives in the JUNE cycle log (cross-month fallback wrote it there)
    store.save_feedback_log(DailyFeedbackLog(
        ticker="MARUTI", cycle_id="MARUTI_2026-06",
        entries=[_entry("2026-06-10"), _entry("2026-07-01")]))

    assert scheduler_api._has_feedback_entry("MARUTI", date(2026, 6, 10)) is True
    assert scheduler_api._has_feedback_entry("MARUTI", date(2026, 7, 1)) is True   # prev-cycle hit
    assert scheduler_api._has_feedback_entry("MARUTI", date(2026, 6, 20)) is False


# ---------------------------------------------------------------------------
# scheduler_api._resolve_tickers — managed_tickers.json is the source of truth
# ---------------------------------------------------------------------------

def test_resolve_tickers_uses_managed_list(monkeypatch):
    import services.api.log_buffer as log_buffer
    from services.api.routes import scheduler_api

    managed = [
        {"sym": "OLAELEC", "sector": "automobile"},
        {"sym": "YESBANK", "sector": "banking_bfsi"},
        {"sym": "SUZLON", "sector": "renewable_energy"},
    ]
    monkeypatch.setattr(log_buffer, "get_active_tickers_with_sector", lambda: managed)

    entries = scheduler_api._resolve_tickers(None)
    assert entries == managed
    # ticker param narrows to the managed entry WITH its sector
    assert scheduler_api._resolve_tickers("yesbank") == [
        {"sym": "YESBANK", "sector": "banking_bfsi"}]
    # unknown ticker falls back to automobile
    assert scheduler_api._resolve_tickers("MARUTI") == [
        {"sym": "MARUTI", "sector": "automobile"}]


def test_resolve_tickers_falls_back_to_scheduler_tickers(monkeypatch):
    import services.api.log_buffer as log_buffer
    from services.api.routes import scheduler_api
    from core.config import settings

    monkeypatch.setattr(log_buffer, "get_active_tickers_with_sector", lambda: [])
    entries = scheduler_api._resolve_tickers(None)
    assert [e["sym"] for e in entries] == list(settings.SCHEDULER_TICKERS)
    assert all(e["sector"] == "automobile" for e in entries)


# ---------------------------------------------------------------------------
# run_logger → telemetry.db mirror
# ---------------------------------------------------------------------------

def test_run_logger_mirrors_into_sqlite(tmp_path, monkeypatch):
    import sqlite3
    import services.data.stores.log_store as log_store
    import services.data.stores.run_logger as run_logger

    db_path = tmp_path / "telemetry.db"
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(log_store, "_conn", None)
    monkeypatch.setattr(run_logger, "AGENT_CALLS_LOG", tmp_path / "agent_calls.jsonl")
    try:
        run_logger.log_llm_call(
            run_id="r1", ticker="MARUTI", phase="agent", agent_name="sales_demand",
            model="deepseek/deepseek-v4-flash", prompt_tokens=1000,
            completion_tokens=200, duration_ms=1234.5, cost_usd=0.0002,
        )
        run_logger.log_llm_call(
            run_id="r1", ticker="MARUTI", phase="aggregation", agent_name=None,
            model="qwen/qwen3.7-max", prompt_tokens=5000,
            completion_tokens=900, duration_ms=9000.0, cost_usd=0.004,
            error="Parse error: Expecting value",
        )
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT caller, model, success FROM llm_calls ORDER BY id").fetchall()
        assert rows == [
            ("agent:sales_demand", "deepseek/deepseek-v4-flash", 1),
            ("aggregation:MARUTI", "qwen/qwen3.7-max", 0),
        ]
    finally:
        if log_store._conn is not None:
            log_store._conn.close()
            log_store._conn = None
