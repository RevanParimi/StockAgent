"""
F5 — the daily review job must publish how many tickers ran news-blind.

Per-ticker blindness was already logged one WARNING at a time; nothing
aggregated it, so "12 of 16 blind" (prod, 2026-07-30) could only be found by
grepping deploy logs. The job now emits one summary line and persists the
counts in the job outcome that GET /scheduler/status serves.
"""
import logging

import pytest

_SCHED_LOGGER = "services.scheduler.python.scheduler"


@pytest.fixture
def sched_env(monkeypatch):
    """Seam the daily review job down to its bookkeeping: no LLMs, no pipeline."""
    import services.scheduler.python.scheduler as sch
    import core.intelligence.rl.workflows.daily_review as dr
    import core.portfolio.pipeline as pl
    import services.data.stores.job_outcomes as jo

    recorded: dict = {}
    monkeypatch.setattr(pl, "run_post_review_pipeline", lambda d: {"status": "completed"})
    monkeypatch.setattr(jo, "record_job_outcome",
                        lambda job, **fields: recorded.update(job=job, **fields))

    def _configure(news_by_ticker: dict[str, object]):
        monkeypatch.setattr(
            sch, "get_active_tickers_with_sector",
            lambda: [{"sym": t, "sector": "automobile"} for t in news_by_ticker],
        )

        def _review(ticker, review_date, sector=None):
            flag = news_by_ticker[ticker]
            summary = {"status": "completed"}
            if flag is not None:          # None => early return, key absent
                summary["news_available"] = flag
            return summary

        monkeypatch.setattr(dr, "run_daily_review", _review)
        return sch

    return _configure, recorded


def test_job_outcome_carries_news_fetched_and_blind_counts(sched_env):
    configure, recorded = sched_env
    sch = configure({"MARUTI": True, "INFY": False, "TCS": False})

    sch.AutomobileScheduler()._daily_review_job()

    assert recorded["job"] == "daily_review"
    assert recorded["news_fetched"] == 1
    assert recorded["news_blind"] == 2


def test_job_logs_one_news_context_summary_line(sched_env, caplog):
    configure, _recorded = sched_env
    sch = configure({"MARUTI": True, "INFY": False, "TCS": False})

    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        sch.AutomobileScheduler()._daily_review_job()

    lines = [r.getMessage() for r in caplog.records if "news_context:" in r.getMessage()]
    assert len(lines) == 1
    assert "1 fetched / 2 blind of 3" in lines[0]


def test_reviews_without_the_flag_are_not_counted(sched_env):
    """Early returns (no_envelope / no_actual_data) never reach the news fetch —
    they must not be scored as 'blind' and inflate the metric."""
    configure, recorded = sched_env
    sch = configure({"MARUTI": True, "INFY": None})

    sch.AutomobileScheduler()._daily_review_job()

    assert recorded["news_fetched"] == 1
    assert recorded["news_blind"] == 0


def test_all_blind_day_is_recorded_not_swallowed(sched_env, caplog):
    configure, recorded = sched_env
    sch = configure({"MARUTI": False, "INFY": False})

    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        sch.AutomobileScheduler()._daily_review_job()

    assert recorded["news_fetched"] == 0 and recorded["news_blind"] == 2
    assert any("0 fetched / 2 blind of 2" in r.getMessage() for r in caplog.records)
