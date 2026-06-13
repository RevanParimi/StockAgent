"""
Weekly research-loop scheduler job (RL Phase 4, spec
docs/superpowers/specs/2026-06-13-research-loop-design.md section 5).

`AutomobileScheduler._research_loop_job` iterates the managed-tickers helper
(`_active_tickers` + `_sector_for`, the same pattern `_event_ingest_job` uses)
and calls `QuestionResearcher().run(ticker, sector)` for each, non-fatal per
ticker. Gated on settings.RL_RESEARCH_LOOP_ENABLED — flag off means the job
body returns without calling `run` at all.
"""
import core.intelligence.rl.agents.question_researcher as qr_mod
import services.scheduler.python.scheduler as sched


def _scheduler():
    return sched.AutomobileScheduler.__new__(sched.AutomobileScheduler)


def test_research_job_calls_run_per_ticker_with_sector(monkeypatch):
    monkeypatch.setattr(sched, "_active_tickers", lambda: ["MARUTI", "TVSMOTOR"])
    monkeypatch.setattr(sched.settings, "RL_RESEARCH_LOOP_ENABLED", True)

    calls = []

    def fake_run(self, ticker, sector):
        calls.append((ticker, sector))
        return {"selected": 1, "answered": 1, "partial": 0, "expired": 0}

    monkeypatch.setattr(qr_mod.QuestionResearcher, "run", fake_run)

    _scheduler()._research_loop_job()

    assert calls == [("MARUTI", "automobile"), ("TVSMOTOR", "automobile")]


def test_research_job_non_fatal_when_one_ticker_raises(monkeypatch):
    monkeypatch.setattr(sched, "_active_tickers", lambda: ["MARUTI", "TVSMOTOR"])
    monkeypatch.setattr(sched.settings, "RL_RESEARCH_LOOP_ENABLED", True)

    calls = []

    def fake_run(self, ticker, sector):
        calls.append(ticker)
        if ticker == "MARUTI":
            raise RuntimeError("boom")
        return {"selected": 0, "answered": 0, "partial": 0, "expired": 0}

    monkeypatch.setattr(qr_mod.QuestionResearcher, "run", fake_run)

    # Must not raise, and must still process the second ticker.
    _scheduler()._research_loop_job()

    assert calls == ["MARUTI", "TVSMOTOR"]


def test_research_job_noop_when_flag_disabled(monkeypatch):
    monkeypatch.setattr(sched, "_active_tickers", lambda: ["MARUTI", "TVSMOTOR"])
    monkeypatch.setattr(sched.settings, "RL_RESEARCH_LOOP_ENABLED", False)

    calls = []

    def fake_run(self, ticker, sector):
        calls.append(ticker)
        return {"selected": 0, "answered": 0, "partial": 0, "expired": 0}

    monkeypatch.setattr(qr_mod.QuestionResearcher, "run", fake_run)

    _scheduler()._research_loop_job()

    assert calls == []
