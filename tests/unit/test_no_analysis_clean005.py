"""CLEAN-005 step 1: a failed analysis is "no analysis", never a backup analysis.

Independent invariants, each through the real orchestrator and the real
one-call analyst, with only the model's transport replaced. Four ways the model
call fails: it times out on every attempt, its answer is not JSON, its answer
names none of the sector's dimensions, or every retry fails.

1. No caller books a buy, a sell, a size change, a forecast or a grade from an
   analysis that scored nothing: the run raises AnalysisUnavailable before the
   aggregator, writes no score row, no analysis log, no run summary and no
   gate decision; the 16:30 review writes nothing that learns or advises; the
   forecast writes no envelope; a re-forecast leaves the envelope byte-
   identical; the deep dive mints no idea.
2. A scheduled caller skips the stock, carries on with the others, and the
   failure is logged once.
3. The on-demand routes say plainly that today's analysis could not be
   produced, with no verdict and no score.
4. The day's count is GET /scheduler/status's `analyses_failed_today`, in IST.

The boundary: an answer missing one dimension is still an analysis (the gate
judges it), so this card does not widen what counts as a failure.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai
import pytest

import backend.shared.pipeline.base_orchestrator as bo_mod
import backend.shared.pipeline.signal_aggregator as sa_mod
import backend.shared.pipeline.unified_analyst as ua_mod
from backend.shared.pipeline.no_analysis import (
    AnalysisUnavailable,
    scored_nothing,
    why_nothing,
)
from backend.shared.pipeline.unified_analyst import DIMENSIONS
from core.config import settings
from core.schemas.pipeline import AgentOutput, StockQuery
from services.data.stores import analysis_failures as af

TICKER_A = "QFAILCO"

MODES = {
    # mode: words the recorded reason must contain
    "timeout": "timed out on all 3 attempts",
    "unparseable": "could not be read",
    "missing_sections": "no dimension scored",
    "exhausted_retry": "failed after 3 attempts (ConnectionResetError)",
}


# ---------------------------------------------------------------------------
# The harness: the real orchestrator and analyst, the model's transport faked
# ---------------------------------------------------------------------------

class _Completions:
    def __init__(self, state):
        self.state = state

    def create(self, **kw):
        self.state.model_calls += 1
        mode = self.state.mode
        if mode == "timeout":
            raise openai.APITimeoutError(request=httpx.Request("POST", "https://llm.invalid/v1"))
        if mode == "exhausted_retry":
            raise ConnectionResetError("connection reset by peer")
        if mode == "unparseable":
            content = "Sure! My view: buy it. (no JSON here)"
        elif mode == "missing_sections":
            content = json.dumps({"overall": {"score": 0.9, "summary": "strong"}})
        elif mode == "one_missing":
            dims = list(DIMENSIONS["automobile"])[1:]
            content = json.dumps({d: {"score": 0.7, "summary": f"{d} ok"} for d in dims})
        else:
            raise AssertionError(f"unknown mode {mode}")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None)


class _ReachedAggregator(Exception):
    """The run went on to aggregation: it was an analysis."""


def _bundle(*a, **k):
    return SimpleNamespace(
        api_calls_made={"serper": 3}, has_real_data=True,
        section_status={"company_news": "ok", "fundamentals": "ok", "technicals": "ok"},
        section_provenance={}, company_search=None,
        to_prompt_text=lambda: "=== DATA ===\nnothing of note",
    )


@pytest.fixture
def failing(monkeypatch):
    """Install the faked model transport and record every side effect a
    verdict feeds. `state.mode` picks the failure; the orchestrators the
    application builds itself (sector router, registry) all get it."""
    state = SimpleNamespace(mode="timeout", model_calls=0, aggregator_calls=0,
                            score_rows=[], analysis_logs=[], run_summaries=[],
                            legacy_runs=0)
    monkeypatch.setattr(ua_mod, "get_llm_client",
                        lambda: SimpleNamespace(chat=SimpleNamespace(
                            completions=_Completions(state))))
    monkeypatch.setattr(ua_mod, "time", SimpleNamespace(time=lambda: 0.0,
                                                        sleep=lambda s: None))
    monkeypatch.setattr(ua_mod, "log_llm_call", lambda *a, **k: None)
    monkeypatch.setattr("services.data.context.bundle_builder.build_sector_bundle", _bundle)
    monkeypatch.setattr(bo_mod, "get_llm_client", lambda: MagicMock())
    monkeypatch.setattr(sa_mod, "get_llm_client", lambda: MagicMock())

    def _resolve(self, user_input, run_id=""):
        t = user_input.strip().upper()
        return StockQuery(ticker=t, company_name=f"{t} Ltd", nse_data={})
    monkeypatch.setattr(bo_mod.BaseSectorOrchestrator, "_resolve_ticker", _resolve)
    monkeypatch.setattr(bo_mod.BaseSectorOrchestrator, "_prefetch_nse_data",
                        lambda self, q: None)
    monkeypatch.setattr(bo_mod.BaseSectorOrchestrator, "_load_learned_weights",
                        lambda self, t: None)

    def _aggregate(self, **kw):
        state.aggregator_calls += 1
        raise _ReachedAggregator(kw.get("ticker"))
    monkeypatch.setattr(sa_mod.SignalAggregator, "run", _aggregate)

    monkeypatch.setattr(bo_mod.BaseSectorOrchestrator, "_record_score_history",
                        lambda self, report: state.score_rows.append(report))
    monkeypatch.setattr(bo_mod, "log_analysis", lambda **kw: state.analysis_logs.append(kw))
    monkeypatch.setattr(bo_mod, "log_run_summary", lambda **kw: state.run_summaries.append(kw))
    if hasattr(bo_mod.BaseSectorOrchestrator, "_run_via_graph"):
        def _legacy(self, *a, **k):
            state.legacy_runs += 1
            raise AssertionError("the legacy worker pool ran")
        monkeypatch.setattr(bo_mod.BaseSectorOrchestrator, "_run_via_graph", _legacy)
    return state


def _orchestrator():
    from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator
    return AutomobileAgentOrchestrator()


def _failure_rows() -> list[dict]:
    """The failure record, read with plain JSON (not the code under test)."""
    p = Path("data") / "rl" / "analysis_failures.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]


def _gate_rows() -> list[dict]:
    from backend.shared.pipeline import decision_gate as dg
    p = Path(dg._path())
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]


def _warnings(caplog) -> list[logging.LogRecord]:
    """WARNING and above that name the stock's skip (the one log line)."""
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and "No analysis for" in r.getMessage()]


# ---------------------------------------------------------------------------
# The pure helpers
# ---------------------------------------------------------------------------

def test_scored_nothing_means_no_measured_dimension():
    ok = AgentOutput(agent="a", ticker="X", overall_score=0.7)
    bad = AgentOutput(agent="b", ticker="X", overall_score=0.5, error="missing_in_unified_response")
    assert scored_nothing({}) and scored_nothing(None)
    assert scored_nothing({"a": bad, "b": bad})
    assert not scored_nothing({"a": ok, "b": bad})
    assert "2 of 2 failed" in why_nothing({"a": bad, "b": bad}, None)
    assert why_nothing({}, "the model call timed out on all 3 attempts").startswith("the model")


def test_the_users_message_has_no_verdict_and_no_score():
    msg = AnalysisUnavailable("MARUTI", "automobile", "x").user_message()
    assert "MARUTI" in msg and "could not be produced" in msg
    for word in ("BUY", "SELL", "HOLD", "score=", "0."):
        assert word not in msg


# ---------------------------------------------------------------------------
# 1. The orchestrator: no analysis, nothing a verdict feeds is written
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("run_async", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("mode", list(MODES))
def test_a_run_that_scored_nothing_is_no_analysis(failing, caplog, mode, run_async):
    failing.mode = mode
    orch = _orchestrator()
    caplog.set_level(logging.WARNING)

    with pytest.raises(AnalysisUnavailable) as raised:
        if run_async:
            asyncio.run(orch.analyse_async(TICKER_A))
        else:
            orch.analyse(TICKER_A)

    failure = raised.value
    assert (failure.ticker, failure.sector) == (TICKER_A, "automobile")
    assert MODES[mode] in failure.reason
    assert failing.model_calls == (3 if mode in ("timeout", "exhausted_retry") else 1)
    # Nothing a verdict feeds: no aggregation, no score row, no analysis log,
    # no run summary, no gate decision, no backup analysis.
    assert failing.aggregator_calls == 0
    assert (failing.score_rows, failing.analysis_logs, failing.run_summaries) == ([], [], [])
    assert [r for r in _gate_rows() if r.get("ticker") == TICKER_A] == []
    assert failing.legacy_runs == 0
    # Counted once, logged once.
    [row] = _failure_rows()
    assert (row["ticker"], row["sector"], row["run_id"]) == (TICKER_A, "automobile", failure.run_id)
    assert MODES[mode] in row["reason"]
    assert af.failed_count_today() == 1
    assert len(_warnings(caplog)) == 1


def test_no_score_row_reaches_the_score_store(monkeypatch):
    """The same invariant read from the store itself: the real score writer,
    analysis log and aggregator stay in place (only the model's transport and
    the inputs are faked), and the score database holds no row for the stock."""
    monkeypatch.setattr(ua_mod, "get_llm_client",
                        lambda: SimpleNamespace(chat=SimpleNamespace(
                            completions=_Completions(SimpleNamespace(mode="unparseable",
                                                                     model_calls=0)))))
    monkeypatch.setattr(ua_mod, "log_llm_call", lambda *a, **k: None)
    monkeypatch.setattr("services.data.context.bundle_builder.build_sector_bundle", _bundle)
    monkeypatch.setattr(bo_mod, "get_llm_client", lambda: MagicMock())
    monkeypatch.setattr(sa_mod, "get_llm_client", lambda: MagicMock())
    monkeypatch.setattr(bo_mod.BaseSectorOrchestrator, "_resolve_ticker",
                        lambda self, u, run_id="": StockQuery(ticker=u, company_name="Q Ltd",
                                                              nse_data={}))
    monkeypatch.setattr(bo_mod.BaseSectorOrchestrator, "_prefetch_nse_data", lambda self, q: None)
    monkeypatch.setattr(bo_mod.BaseSectorOrchestrator, "_resolve_weights_for", lambda self, t: None)

    with pytest.raises(AnalysisUnavailable):
        _orchestrator().analyse(TICKER_A)

    db = Path(settings.SCORE_DB_PATH)
    if db.exists():
        with sqlite3.connect(db) as c:
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
            if "score_history" in tables:
                assert c.execute("SELECT COUNT(*) FROM score_history WHERE ticker = ?",
                                 (TICKER_A,)).fetchone()[0] == 0


def test_an_answer_missing_one_dimension_is_still_an_analysis(failing):
    """The boundary: eight of nine dimensions scored goes on to aggregation
    and the gate, as before. No failure is counted."""
    failing.mode = "one_missing"
    with pytest.raises(_ReachedAggregator):
        _orchestrator().analyse(TICKER_A)
    assert failing.aggregator_calls == 1
    assert _failure_rows() == []


def test_the_backup_analysis_is_off_by_default():
    assert settings.UNIFIED_ANALYST_FALLBACK_LEGACY is False


# ---------------------------------------------------------------------------
# 2. The scheduled callers
# ---------------------------------------------------------------------------

def _review_with_failing_analysis(tmp_path, monkeypatch):
    """One real run_daily_review whose re-run goes through the real sector
    router to the real orchestrator (the SA-003 store: direction wrong, so
    the review re-runs the analysis)."""
    import core.intelligence.rl.workflows.daily_review as dr
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    from core.schemas.feedback import (
        DailyFeedbackLog, FeedbackEntry, RegimeSnapshot, WeightMemory)
    from tests.unit.intelligence.rl.test_learning_mode_sa039 import (
        AUTOMOBILE_DEFAULTS, AUTOMOBILE_LEARNED)
    from tests.unit.intelligence.rl.test_shock_path import (
        REVIEW_DATE, SECTOR, TICKER, _patch_common, _setup_store)

    store, cycle_id = _setup_store(tmp_path)
    env = store.load_envelope(cycle_id)
    for row in env.daily_forecasts:                  # an actionable month-start row
        row.data_gate, row.source_run_id = "actionable", "month-run"
    store.save_envelope(env)
    store.save_weight_memory(WeightMemory(
        ticker=TICKER, sector=SECTOR, last_updated="2026-09-23", weight_version=41,
        current_weights=dict(AUTOMOBILE_LEARNED), base_weights=dict(AUTOMOBILE_DEFAULTS)))
    store.save_feedback_log(DailyFeedbackLog(ticker=TICKER, cycle_id=cycle_id, entries=[
        FeedbackEntry(day=0, date=(REVIEW_DATE - timedelta(days=d)).isoformat(),
                      predicted_close=100.0, actual_close=97.0, price_error_pct=-3.0,
                      predicted_verdict="BUY", actual_direction="DOWN",
                      direction_correct=False,
                      predicted_agent_scores={"risk_macro": 0.8, "sales_demand": 0.8})
        for d in (2, 1)]))
    real_rerun = dr._run_todays_agent_scores
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    monkeypatch.setattr(dr, "_run_todays_agent_scores", real_rerun)   # the real re-run
    monkeypatch.setattr(dr, "_fetch_session_close",
                        lambda t, d: dr.SessionClose(98.0, REVIEW_DATE, "agree"))
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(offmarket_mod.OffMarketFetcher, "__init__",
                        lambda self: setattr(self, "_nse", None))
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", False)
    monkeypatch.setattr(dr.settings, "REGIME_MULTIPLIERS", {})
    monkeypatch.setattr(dr.RegimeDetector, "detect",
                        lambda self, d, s: RegimeSnapshot(multipliers={}))
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: False)
    feedback_calls: list = []
    monkeypatch.setattr(FeedbackAgent, "run",
                        lambda self, fb_input, ledger: feedback_calls.append(fb_input))
    return dr, store, TICKER, REVIEW_DATE, SECTOR, feedback_calls


def _tree(root) -> dict[str, str]:
    """SHA-256 of every file under root except the market-wide regime state
    and the failure record itself (both asserted on their own)."""
    skip = {"_regime_state.json", "analysis_failures.jsonl"}
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file() and p.name not in skip}


@pytest.mark.parametrize("mode", ["timeout", "missing_sections"])
def test_the_1630_review_skips_the_stock_and_writes_nothing(failing, tmp_path, monkeypatch,
                                                            caplog, mode):
    from core.intelligence.rl.workflows import review_outcomes as ro
    failing.mode = mode
    dr, store, ticker, review_date, sector, feedback_calls = \
        _review_with_failing_analysis(tmp_path, monkeypatch)
    before = _tree(tmp_path)
    caplog.set_level(logging.WARNING)

    summary = dr.run_daily_review(ticker, review_date, sector=sector)

    assert summary["status"] == "no_analysis"
    assert MODES[mode] in summary["reason"]
    assert ro.classify(ticker, review_date.isoformat(), summary) == \
        ro.ReviewOutcome(ticker, ro.SKIPPED, "no_analysis")
    # Nothing graded, learned or advised: every file is byte-identical and
    # no new file appeared (feedback log, weights, observations, ledgers,
    # dossier, envelope); the feedback agent never ran.
    assert _tree(tmp_path) == before
    assert store.load_weight_memory().weight_version == 41
    assert feedback_calls == []
    assert failing.aggregator_calls == 0
    assert [r["ticker"] for r in _failure_rows()] == [ticker]
    assert len(_warnings(caplog)) == 1


def test_the_monthly_forecast_writes_no_envelope(failing, tmp_path, monkeypatch):
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from core.intelligence.rl.workflows import generate_forecast as gf
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf, "_fetch_actual_close", lambda ticker: 100.0)

    with pytest.raises(AnalysisUnavailable):
        gf.generate_forecast(TICKER_A, sector="automobile")

    store = PredictionStore(TICKER_A, sector="automobile", base_dir=str(tmp_path))
    assert store.load_envelope(store.current_cycle_id()) is None
    assert failing.aggregator_calls == 0


def test_a_reforecast_leaves_the_envelope_intact_and_logs_once(failing, tmp_path,
                                                               monkeypatch, caplog):
    from datetime import date

    from core.intelligence.rl.workflows import generate_forecast as gf
    from tests.unit.intelligence.rl.test_decision_gate_learning_sa003 import _seed_envelope
    today = date.today()
    store = _seed_envelope(tmp_path, today)
    path = store._envelope_path(store.cycle_id_for(today))
    before = path.read_bytes()
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    from tests.unit.intelligence.rl.test_shock_path import SECTOR, TICKER
    caplog.set_level(logging.WARNING)

    env = gf.regenerate_envelope(ticker=TICKER, sector=SECTOR, review_date=today,
                                 reason="test", trigger="external_shock")

    assert env is None
    assert path.read_bytes() == before
    assert len(_warnings(caplog)) == 1
    assert not [r for r in caplog.records if "unhandled failure" in r.getMessage()]


def test_the_monthly_job_carries_on_with_the_next_stock(monkeypatch, caplog):
    """The scheduler's monthly forecast: the failed stock is skipped without
    a second log line, the next one is forecast."""
    from core.intelligence.rl.workflows import generate_forecast as gf
    from services.scheduler.python import scheduler as sch
    done: list[str] = []

    def _forecast(ticker, sector="automobile"):
        if ticker == "QFAIL":
            raise AnalysisUnavailable(ticker, sector, "the model call timed out on all 3 attempts")
        done.append(ticker)
        return SimpleNamespace(cycle_id="2026-12", daily_forecasts=[1], base_close=1.0,
                               weight_version_used=1)
    monkeypatch.setattr(gf, "generate_forecast", _forecast)
    monkeypatch.setattr(sch, "get_active_tickers_with_sector",
                        lambda: [{"sym": "QFAIL", "sector": "automobile"},
                                 {"sym": "QNEXT", "sector": "automobile"}])
    caplog.set_level(logging.WARNING)
    job = sch.AutomobileScheduler.__new__(sch.AutomobileScheduler)

    job._monthly_forecast_job()

    assert done == ["QNEXT"]
    assert not [r for r in caplog.records if "QFAIL" in r.getMessage()]


def test_the_deep_dive_mints_no_idea_and_carries_on(failing, monkeypatch):
    import core.discovery.deep_dive as dd
    from tests.unit.test_idea_supply_pr004 import Analyst, _eod_window, cand, companies
    from datetime import date
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", "disc")
    monkeypatch.setattr(dd, "load_managed_tickers", lambda: [])
    window = _eod_window(["QOK1", "QFAILCO", "QOK2"], days=3)

    class _Store:
        def load_window(self, end, sessions):
            return window
    monkeypatch.setattr(dd, "EodStore", _Store)
    monkeypatch.setattr(dd, "market_classification", lambda s: {"sector": "", "industry": ""})
    stub = Analyst()
    real = {}

    def _route(sector):
        o = stub.orchestrator(sector)

        class _O:
            def analyse(self, symbol, sector_question=None):
                if symbol == TICKER_A:
                    real.setdefault("o", _orchestrator())
                    return real["o"].analyse(symbol, sector_question=sector_question)
                return o.analyse(symbol, sector_question)
        return _O()
    monkeypatch.setattr(dd, "get_orchestrator", _route)
    tally: dict = {}

    results = dd.run_deep_dives([cand("QOK1"), cand(TICKER_A), cand("QOK2")],
                                on=date(2026, 11, 20), max_n=5,
                                listing=companies("QOK1", TICKER_A, "QOK2"), tally=tally)

    assert [r.symbol for r in results] == ["QOK1", "QOK2"]
    assert tally["calls"] == 3                       # the failed call still spent budget
    assert [r["ticker"] for r in _failure_rows()] == [TICKER_A]


# ---------------------------------------------------------------------------
# 3. The on-demand routes
# ---------------------------------------------------------------------------

def _no_verdict_anywhere(text: str) -> None:
    for word in ('"verdict"', '"final_score"', "STRONG BUY", "BUY (", "SELL (", "score="):
        assert word not in text


@pytest.mark.parametrize("mode", list(MODES))
def test_post_analyse_says_so_plainly(failing, monkeypatch, mode):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from services.api import auth
    from services.api.routes import analyse as route
    failing.mode = mode
    monkeypatch.setattr(route, "check_analyse_quota", lambda user: None)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "m1", "role": "member"}

    r = TestClient(app).post("/analyse", json={"ticker": TICKER_A, "sector": "automobile"})

    assert r.status_code == 503
    assert "could not be produced" in r.json()["detail"] and TICKER_A in r.json()["detail"]
    _no_verdict_anywhere(r.text)


def test_the_stream_says_so_plainly(failing, monkeypatch):
    from services.api.routes import stream
    failing.mode = "unparseable"
    monkeypatch.setattr(stream, "detect_sector", lambda t: "automobile")
    published: list[str] = []
    monkeypatch.setattr(stream, "_publish", lambda run, msg: published.append(msg))
    run = stream._TickerRun(TICKER_A)

    asyncio.run(stream._run_pipeline(run))

    [msg] = published
    event = json.loads(msg)
    assert event["event"] == "error" and event["no_analysis"] is True
    assert "could not be produced" in event["detail"]
    _no_verdict_anywhere(msg)


def test_the_chat_tool_quotes_no_verdict(failing, monkeypatch):
    from services.api.routes import ui_data
    failing.mode = "timeout"
    monkeypatch.setattr(ui_data, "_score_store",
                        lambda: SimpleNamespace(get_latest=lambda t: None))
    monkeypatch.setattr("backend.sectors.detect_sector", lambda t: "automobile")

    text = asyncio.run(ui_data._chat_tool_run_agent_analysis(TICKER_A))

    assert "could not be produced" in text
    _no_verdict_anywhere(text)


# ---------------------------------------------------------------------------
# 4. The day's count, where the owner looks
# ---------------------------------------------------------------------------

def test_the_count_is_by_ist_day(monkeypatch):
    # 20 Nov 20:00 UTC is 21 Nov 01:30 IST: it counts on the 21st, not the 20th.
    clock = {"now": datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(af, "_now", lambda: clock["now"])
    af.record_analysis_failure("automobile", "QA", "r")
    clock["now"] = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)       # 23:30 IST, 20th
    af.record_analysis_failure("generic", "QB", "r")
    assert af.failed_count_today() == 1
    clock["now"] = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)        # 08:30 IST, 21st
    assert af.failed_count_today() == 1
    assert [r["ist_date"] for r in _failure_rows()] == ["2026-11-21", "2026-11-20"]


def test_an_unreadable_record_counts_nothing_and_raises_nothing():
    p = Path("data") / "rl" / "analysis_failures.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not json\n{\"ist_date\": 5}\n", encoding="utf-8")
    assert af.failed_count_today() == 0


def test_the_status_page_shows_the_count_in_the_fallback_slot(monkeypatch):
    import inspect

    from services.api.routes import scheduler_api
    src = inspect.getsource(scheduler_api)
    assert '"analyses_failed_today":    failed_count_today()' in src
    assert "fallback_events_today" not in src
