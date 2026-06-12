"""
Weekly event-ingest scheduler job (spec docs/superpowers/specs/2026-06-12-event-ingestion-design.md, section 6).

`AutomobileScheduler._event_ingest_job` iterates the managed-tickers helper
(`_active_tickers` + `_sector_for`, the same pattern `_ledger_cleanup_job`
uses) and calls `EventIngestor().run(ticker, sector)` for each, non-fatal per
ticker. Gated on settings.RL_EVENT_INGEST_ENABLED — when the flag is off the
job body must return without calling `run` at all.
"""
import core.intelligence.rl.agents.event_ingestor as event_ingestor_mod
import services.scheduler.python.scheduler as sched


def _scheduler():
    return sched.AutomobileScheduler.__new__(sched.AutomobileScheduler)


def test_event_ingest_job_calls_run_per_ticker_with_sector(monkeypatch):
    monkeypatch.setattr(sched, "_active_tickers", lambda: ["MARUTI", "TVSMOTOR"])
    monkeypatch.setattr(sched.settings, "RL_EVENT_INGEST_ENABLED", True)

    calls = []

    def fake_run(self, ticker, sector, lookback_days=None):
        calls.append((ticker, sector))
        return 1

    monkeypatch.setattr(event_ingestor_mod.EventIngestor, "run", fake_run)

    scheduler = _scheduler()
    scheduler._event_ingest_job()

    assert calls == [("MARUTI", "automobile"), ("TVSMOTOR", "automobile")]


def test_event_ingest_job_non_fatal_when_one_ticker_raises(monkeypatch):
    monkeypatch.setattr(sched, "_active_tickers", lambda: ["MARUTI", "TVSMOTOR"])
    monkeypatch.setattr(sched.settings, "RL_EVENT_INGEST_ENABLED", True)

    calls = []

    def fake_run(self, ticker, sector, lookback_days=None):
        calls.append(ticker)
        if ticker == "MARUTI":
            raise RuntimeError("boom")
        return 2

    monkeypatch.setattr(event_ingestor_mod.EventIngestor, "run", fake_run)

    scheduler = _scheduler()
    # Must not raise, and must still process the second ticker.
    scheduler._event_ingest_job()

    assert calls == ["MARUTI", "TVSMOTOR"]


def test_event_ingest_job_noop_when_flag_disabled(monkeypatch):
    monkeypatch.setattr(sched, "_active_tickers", lambda: ["MARUTI", "TVSMOTOR"])
    monkeypatch.setattr(sched.settings, "RL_EVENT_INGEST_ENABLED", False)

    calls = []

    def fake_run(self, ticker, sector, lookback_days=None):
        calls.append(ticker)
        return 1

    monkeypatch.setattr(event_ingestor_mod.EventIngestor, "run", fake_run)

    scheduler = _scheduler()
    scheduler._event_ingest_job()

    assert calls == []
