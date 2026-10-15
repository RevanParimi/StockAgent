"""FIX-010: every analysis writes the score history again; screens name only the viewer's stocks.

From 21 Apr 2026 (ce1eeb5) nothing called ScoreStore.save, so production's score
history held no row while 1,082 analyses were logged (probe of 15 Oct). These
tests pin the repair and what restoring the write would otherwise expose:

1. The write: one real orchestrator.analyse() (real aggregator and decision
   gate; LLM, analyst and providers stubbed, as in the SA-003 tests) leaves
   exactly one row with the verdict the run returns. A failed write is a
   warning, never a failed analysis. Every sector orchestrator inherits that
   exit, and it is the only writer.
2. Who sees which stocks: the owner holds QOWNHOLD, the member holds QMEMHOLD,
   QASKED was analysed only because someone asked, QMANAGED is a managed
   ticker and QSHELF a shelf idea. Every one changed verdict. The expected
   names per viewer come from that table: the owner sees QOWNHOLD, QMANAGED
   and QSHELF; the member QMEMHOLD, QMANAGED and QSHELF; an anonymous request
   (sign-in required) QMANAGED and QSHELF; nobody sees QASKED in a list.
   Checked on /ui/learnings, /ui/search, the chat's context and history tool,
   /ui/bootstrap, /ui/market/summary and /analytics/sector-comparison.
3. The writer's agent scores ({"raw", "weight", "weighted"} per agent) no
   longer break Home's "This month" votes (they made /ui/bootstrap fail).
4. A watched stock outside the built-in universe shows its analysis.
5. The empty case is dated (`since`).
6. The backfill script: dry run, apply, idempotence, the live-row cut-off,
   the cap, the marker, remove.

The score rows are written by the real writer (ScoreStore.save). Nothing
leaves the process (tests/hermetic.py; yfinance replaced by a module that
raises).
"""
from __future__ import annotations

import ast
import importlib.util
import json
import logging
import sqlite3
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.shared.schemas.discovery import Shelf, ShelfIdea
from backend.shared.schemas.portfolio import Holding, Portfolio, WatchlistItem
from core.config import settings
from core.schemas.pipeline import AgentOutput
from tests.unit.shared.test_data_health_contract import (  # noqa: F401 — fixtures
    _AutoOrchestrator,
    _query,
    fresh_db,
    market,
)
from tests.unit.shared.test_decision_gate_sa003 import (  # noqa: F401 — fixtures
    NINE,
    _price_source_404,
    gate_mode,
    no_network,
)

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. The write, through the real orchestrator exit
# ---------------------------------------------------------------------------

def _analyse(monkeypatch, tmp_path, *, score=0.9, llm_verdict="STRONG BUY", logged=None, run_async=False):
    """One real orchestrator.analyse() (or analyse_async()) for TATAMOTORS (the
    SA-003 harness), with log_run_summary recorded into `logged` instead of
    telemetry.db."""
    import backend.shared.pipeline.base_orchestrator as bo_mod
    import backend.shared.pipeline.signal_aggregator as sa_mod
    import services.data.stores.data_health as dh

    monkeypatch.setattr(dh, "DATA_HEALTH_LOG", tmp_path / "data_health.jsonl")
    monkeypatch.setattr(sa_mod.settings, "RL_HARD_BIND_VERDICT_ENABLED", False)
    monkeypatch.setattr(bo_mod, "log_run_summary",
                        lambda **kw: (logged if logged is not None else []).append(kw))
    for name in ("log_run_api_usage", "log_analysis"):
        monkeypatch.setattr(bo_mod, name, lambda *a, **k: None)
    monkeypatch.setattr(sa_mod, "log_llm_call", lambda *a, **k: None)
    monkeypatch.setattr("backend.shared.pipeline.verdict_shadow.log_verdict_shadow",
                        lambda *a, **k: None)
    with patch("backend.shared.pipeline.base_orchestrator.get_llm_client", return_value=MagicMock()), \
         patch("backend.shared.pipeline.signal_aggregator.get_llm_client", return_value=MagicMock()):
        orch = _AutoOrchestrator()
    orch.set_aggregator_weights({d: 1.0 / len(NINE) for d in NINE}, "TATAMOTORS")
    analyst = MagicMock()
    analyst.run.return_value = {d: AgentOutput(agent=d, ticker="TATAMOTORS", overall_score=score) for d in NINE}
    analyst._last_prompt_tokens = analyst._last_completion_tokens = 0
    verdict_json = json.dumps({"final_score": score, "verdict": llm_verdict, "conviction_drivers": ["x"],
                               "top_risks": [], "investment_thesis": "t", "executive_summary": "s"})
    with patch.object(orch, "_resolve_ticker", return_value=_query("TATAMOTORS")), \
         patch.object(orch, "_prefetch_nse_data"), \
         patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=analyst), \
         patch.object(sa_mod.SignalAggregator, "_call_llm", return_value=verdict_json):
        if run_async:
            import asyncio
            return asyncio.run(orch.analyse_async("TATAMOTORS"))
        return orch.analyse("TATAMOTORS")


def _rows(ticker):
    """Every stored row for a ticker, oldest first, read with plain SQL (not the code under test)."""
    path = Path(settings.SCORE_DB_PATH)
    if not path.exists():
        return []
    with sqlite3.connect(path) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(
            "SELECT * FROM score_history WHERE ticker = ? ORDER BY id", (ticker,))]


def test_each_analysis_writes_one_row_with_the_verdict_it_returns(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    gate_mode("record")
    assert _rows("TATAMOTORS") == []
    first = _analyse(monkeypatch, tmp_path)
    rows = _rows("TATAMOTORS")
    assert len(rows) == 1
    assert rows[0]["verdict"] == first.verdict == "STRONG BUY"
    assert rows[0]["final_score"] == pytest.approx(first.final_score)
    # each agent's own score, as the writer stores it
    raw = {k: v["raw"] for k, v in json.loads(rows[0]["agent_scores"]).items()}
    assert set(raw) == set(NINE) and set(raw.values()) == {0.9}

    _analyse(monkeypatch, tmp_path, score=0.3, llm_verdict="SELL")
    rows = _rows("TATAMOTORS")
    assert [r["verdict"] for r in rows] == ["STRONG BUY", "SELL"], "a second analysis is a second row"
    assert rows[1]["run_at"] > rows[0]["run_at"]
    assert no_network == []


def test_the_async_exit_writes_its_row_too(market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    # /analyse, the stream and the chat use analyse_async: a second exit, same rule
    gate_mode("record")
    report = _analyse(monkeypatch, tmp_path, score=0.3, llm_verdict="SELL", run_async=True)
    assert [(r["verdict"], r["final_score"]) for r in _rows("TATAMOTORS")] == [("SELL", pytest.approx(report.final_score))]
    assert report.verdict == "SELL"
    assert no_network == []


def test_the_row_holds_the_verdict_after_the_decision_gate(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    _price_source_404(market)
    gate_mode("enforce")
    report = _analyse(monkeypatch, tmp_path)
    assert report.verdict == "INSUFFICIENT DATA"
    assert [r["verdict"] for r in _rows("TATAMOTORS")] == ["INSUFFICIENT DATA"], \
        "the withheld STRONG BUY is never recorded as the run's verdict"


def test_a_failed_write_is_a_warning_and_never_fails_the_analysis(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network, caplog):
    from services.data.stores.score_store import ScoreStore
    gate_mode("record")

    def locked(self, report):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(ScoreStore, "save", locked)
    logged: list[dict] = []
    with caplog.at_level(logging.WARNING):
        report = _analyse(monkeypatch, tmp_path, logged=logged)
    assert report.verdict == "STRONG BUY"
    assert len(logged) == 1 and logged[0]["verdict"] == "STRONG BUY", "the run log still has the run"
    assert any("score history not written for TATAMOTORS" in r.getMessage() for r in caplog.records)


def test_every_sector_orchestrator_ends_at_the_one_writer():
    from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
    from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator
    from backend.sectors.banking_bfsi.pipeline.orchestrator import BankingAgentOrchestrator
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    from backend.sectors.it_sector.pipeline.orchestrator import ITAgentOrchestrator
    from backend.sectors.renewable_energy.pipeline.orchestrator import RenewableAgentOrchestrator
    for cls in (AutomobileAgentOrchestrator, BankingAgentOrchestrator, GenericSectorOrchestrator,
                ITAgentOrchestrator, RenewableAgentOrchestrator):
        assert issubclass(cls, BaseSectorOrchestrator), cls
        for klass in cls.__mro__[: cls.__mro__.index(BaseSectorOrchestrator)]:
            assert "analyse" not in vars(klass) and "analyse_async" not in vars(klass), \
                f"{klass.__name__} overrides the analysis exit"
    # ...and the registry hands out only those classes
    from backend.sectors import get_orchestrator
    for sector in ("automobile", "banking_bfsi", "it_sector", "renewable_energy", "generic", "unknown"):
        assert issubclass(get_orchestrator(sector), BaseSectorOrchestrator), sector


def _production_sources():
    for top in ("core", "services", "src", "scripts"):
        yield from (p for p in (REPO / top).rglob("*.py") if "__pycache__" not in p.parts)


def test_the_base_orchestrator_is_the_only_writer_of_the_score_history():
    writers = set()
    for path in _production_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "ScoreStore" in text and ".save(" in text:
            writers.add(path.relative_to(REPO).as_posix())
    assert writers - {"services/data/stores/score_store.py"} == {"src/backend/shared/pipeline/base_orchestrator.py"}


# A list-shaped read of the store names whatever stocks are in it. Each one is
# filtered by _only_visible, except these, which are keyed to stocks the
# caller named or to the built-in universe:
KEYED_READS = {
    ("services/api/routes/ui_data.py", "_gather_ticker_data"),   # the 8 built-in tickers; bootstrap filters the rest
    ("services/api/routes/ui_data.py", "get_watchlist"),          # looked up by the viewer's own symbols
    ("services/scheduler/run_schedule.py", "cmd_latest"),         # the operator's CLI on the server
}


def test_every_list_shaped_read_of_the_score_history_is_filtered():
    unfiltered = []
    for path in _production_sources():
        rel = path.relative_to(REPO).as_posix()
        if rel == "services/data/stores/score_store.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("get_all_latest", "get_by_date_range")):
                continue
            up, filtered, func = node, False, None
            while up in parents:
                up = parents[up]
                if isinstance(up, ast.Call) and getattr(up.func, "id", None) == "_only_visible":
                    filtered = True
                if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)) and func is None:
                    func = up.name
            if not filtered and (rel, func) not in KEYED_READS:
                unfiltered.append(f"{rel}:{node.lineno} in {func}")
    assert unfiltered == []


# ---------------------------------------------------------------------------
# 2. Who sees which stocks
# ---------------------------------------------------------------------------

OWNER_OWN, MEMBER_OWN, ASKED, MANAGED, SHELF = "QOWNHOLD", "QMEMHOLD", "QASKED", "QMANAGED", "QSHELF"
PRIVATE = {OWNER_OWN, MEMBER_OWN, ASKED}
EXPECTED = {"owner": {OWNER_OWN, MANAGED, SHELF}, "member": {MEMBER_OWN, MANAGED, SHELF},
            "anonymous": {MANAGED, SHELF}}
# Each stock's two runs: (hours ago, verdict, score, its agents' raw scores)
RUNS = {
    OWNER_OWN: [(70, "SELL", 0.30, 0.31), (2, "BUY", 0.70, 0.71)],
    MEMBER_OWN: [(69, "BUY", 0.66, 0.62), (3, "SELL", 0.32, 0.33)],
    ASKED: [(68, "NEUTRAL", 0.50, 0.52), (4, "STRONG BUY", 0.88, 0.86)],
    MANAGED: [(67, "SELL", 0.35, 0.41), (5, "NEUTRAL", 0.51, 0.47)],
    SHELF: [(66, "NEUTRAL", 0.49, 0.55), (6, "BUY", 0.68, 0.65)],
    # a shelf idea since dropped: no longer shared, and nobody's own
    "QDROPPED": [(65, "BUY", 0.60, 0.50), (7, "SELL", 0.40, 0.45)],
}


class _Clock:
    now = datetime(2026, 1, 1)


class _FakeDT(datetime):
    @classmethod
    def utcnow(cls):
        return _Clock.now


def _report(sym, verdict, score, raw, thesis="lithium supply"):
    ws = types.SimpleNamespace(raw=raw, weight=0.5, weighted=raw / 2)
    return types.SimpleNamespace(
        ticker=sym, company_name=f"{sym} Ltd", final_score=score, verdict=verdict,
        weighted_agent_scores={"fundamentals": ws, "sentiment": ws},
        investment_thesis=f"{sym} thesis: {thesis}", conviction_drivers=[f"{sym} driver"],
        top_risks=[], model_dump=lambda: {}, model_dump_json=lambda: "{}")


def _holding(symbol):
    return Holding(symbol=symbol, sector="Test", qty=1, avg_buy_price=100.0, adj_avg_price=100.0,
                   adj_qty=1, buy_date="2026-09-01")


@pytest.fixture(params=["atlas-off", "atlas-on"])
def world(request, tmp_path, monkeypatch):
    from core.discovery.shelf import ShelfStore
    from core.portfolio.store import PortfolioStore
    from services.api.routes import analytics, ui_data
    from services.data.stores import atlas_store, score_store, user_store
    from services.data.stores.score_store import ScoreStore

    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "portfolios"))
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "discovery"))
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    monkeypatch.setattr(atlas_store, "enabled", lambda: False)
    owner = user_store.create_user("owner-fix010@example.invalid", "pw-fix010-0", "Owner", role="owner",
                                   user_id=settings.PORTFOLIO_DEFAULT_USER_ID)
    member = user_store.create_user("member-fix010@example.invalid", "pw-fix010-1", "Member")
    PortfolioStore(user_id=owner["user_id"]).save(Portfolio(user_id=owner["user_id"],
                                                            holdings=[_holding(OWNER_OWN)]))
    PortfolioStore(user_id=member["user_id"]).save(Portfolio(
        user_id=member["user_id"], holdings=[_holding(MEMBER_OWN)],
        watchlist=[WatchlistItem(symbol="QMEMWATCH", added="2026-10-01"),
                   WatchlistItem(symbol="QNEVER", added="2026-10-01")]))
    ShelfStore().save(Shelf(ideas=[ShelfIdea(symbol=SHELF, sector="Test", added="2026-10-01", conviction=0.7),
                                   ShelfIdea(symbol="QDROPPED", sector="Test", added="2026-10-01",
                                             conviction=0.7, status="dropped")]))
    Path("data").mkdir(exist_ok=True)
    Path("data/managed_tickers.json").write_text(json.dumps(
        [{"sym": MANAGED, "name": "Managed", "sector": "generic", "enabled": True}]), encoding="utf-8")
    if request.param == "atlas-off":
        Path("data/watchlist.json").write_text(json.dumps(["QMEMWATCH", "QNEVER"]), encoding="utf-8")

    store = ScoreStore(db_path=str(tmp_path / "scores.db"))
    monkeypatch.setattr(score_store, "datetime", _FakeDT)
    real_now = datetime.utcnow()
    for sym, runs in RUNS.items():
        for hours, verdict, score, raw in runs:
            _Clock.now = real_now - timedelta(hours=hours)
            store.save(_report(sym, verdict, score, raw))
    _Clock.now = real_now - timedelta(hours=1)
    store.save(_report("QMEMWATCH", "BUY", 0.64, 0.6, thesis="tyres"))
    monkeypatch.setattr(score_store, "datetime", datetime)
    monkeypatch.setattr(ui_data, "_score_store", lambda: store)
    monkeypatch.setattr(analytics, "_try_import_score_store", lambda: store)

    no_misses = type("PS", (), {"__init__": lambda self, ticker, sector: None,
                                "current_cycle_id": lambda self: "c", "load_feedback_log": lambda self, c: None})
    from core.intelligence.rl.stores import prediction_store
    monkeypatch.setattr(prediction_store, "PredictionStore", no_misses)
    yf = types.ModuleType("yfinance")

    class _Ticker:
        def __init__(self, sym):
            self.sym = sym

        def history(self, *a, **k):
            raise ConnectionError("no market in this test")
    yf.Ticker = _Ticker
    yf.download = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("no market in this test"))
    monkeypatch.setitem(sys.modules, "yfinance", yf)
    if request.param == "atlas-on":
        monkeypatch.setattr(atlas_store, "enabled", lambda: True)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(ui_data.router)
    app.include_router(analytics.router)
    tokens = {"owner": user_store.create_session(owner["user_id"], True),
              "member": user_store.create_session(member["user_id"], True)}
    return types.SimpleNamespace(client=TestClient(app), store=store, ids={
        "owner": owner["user_id"], "member": member["user_id"], "anonymous": None},
        headers={"owner": {"Authorization": f"Bearer {tokens['owner']}"},
                 "member": {"Authorization": f"Bearer {tokens['member']}"}, "anonymous": {}},
        mode=request.param)


def _named(text: str) -> set[str]:
    return {s for s in (OWNER_OWN, MEMBER_OWN, ASKED, MANAGED, SHELF, "QDROPPED") if s in text}


@pytest.mark.parametrize("who", ["owner", "member", "anonymous"])
def test_verdict_changes_name_only_the_viewer_s_stocks(world, who):
    body = world.client.get("/ui/learnings", headers=world.headers[who]).json()
    assert {i["sym"] for i in body["items"] if i["kind"] != "forecast-miss"} == EXPECTED[who]
    assert _named(json.dumps(body)) == EXPECTED[who]


@pytest.mark.parametrize("who", ["owner", "member", "anonymous"])
def test_search_by_thesis_text_names_only_the_viewer_s_stocks(world, who):
    body = world.client.get("/ui/search", params={"q": "lithium"}, headers=world.headers[who]).json()
    assert {r["sym"] for r in body["results"] if r["type"] == "thesis"} == EXPECTED[who]


@pytest.mark.parametrize("who", ["owner", "member"])
def test_the_chat_context_and_history_tool_name_only_the_caller_s_stocks(world, who):
    from services.api.routes import ui_data
    uid = world.ids[who]
    assert _named(ui_data._ctx_current_verdicts(uid)) == EXPECTED[who]
    import asyncio
    history = asyncio.run(ui_data._dispatch_chat_tool("get_analysis_history", {"days": 7}, user_id=uid))
    assert _named(history) == EXPECTED[who]
    with patch.object(ui_data, "_nse_market_context", return_value="MARKET"), \
         patch.object(ui_data, "_get_macro_context_for_intent", return_value=""):
        assert _named(ui_data._build_chat_context("hello", user_id=uid)) == EXPECTED[who]


def test_market_wide_screens_name_only_shared_stocks_and_survive_the_writer_s_agent_scores(world):
    shared = {MANAGED, SHELF}
    r = world.client.get("/ui/bootstrap", headers=world.headers["member"])
    assert r.status_code == 200, r.text[:300]        # the writer's per-agent objects once crashed it
    boot = r.json()
    for pane in ("MARKET_TODAY", "MARKET_MONTH"):
        assert _named(json.dumps(boot[pane])) <= shared, pane
        assert "QMEMWATCH" not in json.dumps(boot[pane]), pane
    # "This month" votes: each agent's mean raw score over the shared stocks' runs
    # in the 31-day window (two runs each), from the fixture table
    raws = [raw for sym in shared for _, _, _, raw in RUNS[sym]]
    want = round(sum(raws) / len(raws), 2)
    assert {v["n"]: v["v"] for v in boot["MARKET_MONTH"]["agentVotes"]} == {"Fundamentals": want, "Sentiment": want}

    summary = world.client.get("/ui/market/summary").json()
    assert _named(json.dumps(summary)) <= shared
    latest = [RUNS[sym][-1][3] for sym in shared]
    assert {v["n"]: v["v"] for v in summary["month"]["agentVotes"]} == {
        "Fundamentals": round(sum(latest) / len(latest), 2), "Sentiment": round(sum(latest) / len(latest), 2)}

    comparison = world.client.get("/analytics/sector-comparison").json()
    assert _named(json.dumps(comparison)) <= shared


def test_a_watched_stock_outside_the_built_in_universe_shows_its_analysis(world):
    rows = {t["sym"]: t for t in world.client.get("/ui/watchlist", headers=world.headers["member"]).json()["tickers"]}
    assert rows["QMEMWATCH"]["hasData"] is True
    assert (rows["QMEMWATCH"]["score"], rows["QMEMWATCH"]["verdict"]) == (0.64, "BUY")
    assert rows["QMEMWATCH"]["price"] == 0.0, "no price is fetched for it"
    assert rows["QNEVER"]["hasData"] is False, "a stock with no analysis is still 'Not analysed'"


def test_with_no_change_the_list_says_since_when_it_has_looked(world, monkeypatch):
    # After clearing, two single runs: the member's watched QMEMWATCH (an hour ago)
    # and the shared QSHELF nine days ago. No change, and since is the OLDER one.
    from services.data.stores import score_store
    with sqlite3.connect(world.store._db_path) as c:
        c.execute("DELETE FROM score_history WHERE ticker != 'QMEMWATCH'")
    monkeypatch.setattr(score_store, "datetime", _FakeDT)
    _Clock.now = datetime.utcnow() - timedelta(days=9)
    world.store.save(_report(SHELF, "BUY", 0.6, 0.6))
    monkeypatch.setattr(score_store, "datetime", datetime)
    with sqlite3.connect(world.store._db_path) as c:
        runs = dict(c.execute("SELECT ticker, run_at FROM score_history").fetchall())
    assert runs[SHELF][:10] < runs["QMEMWATCH"][:10]
    body = world.client.get("/ui/learnings", headers=world.headers["member"]).json()
    assert body == {"items": [], "since": runs[SHELF][:10]}
    # the owner sees the shared QSHELF too
    assert world.client.get("/ui/learnings", headers=world.headers["owner"]).json() == {
        "items": [], "since": runs[SHELF][:10]}
    with sqlite3.connect(world.store._db_path) as c:
        c.execute("DELETE FROM score_history WHERE ticker = ?", (SHELF,))
    owner = world.client.get("/ui/learnings", headers=world.headers["owner"]).json()
    if world.mode == "atlas-on":
        # the owner does not watch QMEMWATCH: nothing to look at, so no date
        assert owner == {"items": [], "since": None}
    else:
        # one user: the global watchlist is the owner's too
        assert owner == {"items": [], "since": runs["QMEMWATCH"][:10]}


def test_an_unreadable_portfolio_names_only_shared_stocks(world, monkeypatch):
    from core.portfolio import store as portfolio_store

    def broken(self):
        raise OSError("disk error (test)")
    monkeypatch.setattr(portfolio_store.PortfolioStore, "load", broken)
    body = world.client.get("/ui/learnings", headers=world.headers["member"]).json()
    # own holdings unreadable: only the shared stocks' changes (the global watchlist
    # of single-user mode holds no change), never a fallback to every stock
    assert {i["sym"] for i in body["items"]} == {MANAGED, SHELF}


# ---------------------------------------------------------------------------
# 6. The backfill script
# ---------------------------------------------------------------------------

def _backfill_module():
    spec = importlib.util.spec_from_file_location("backfill_score_history",
                                                  REPO / "scripts" / "backfill_score_history.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def backfill_dbs(tmp_path, monkeypatch):
    from services.data.stores import log_store
    from services.data.stores.score_store import ScoreStore
    score_db, tele_db = tmp_path / "scores.db", tmp_path / "telemetry.db"
    ScoreStore(db_path=str(score_db))
    with sqlite3.connect(tele_db) as c:
        c.executescript(log_store._SCHEMA)
    monkeypatch.setenv("SCORE_BACKFILL_SCORE_DB", str(score_db))
    monkeypatch.setenv("SCORE_BACKFILL_TELEMETRY_DB", str(tele_db))
    return score_db, tele_db


def _log_run(tele_db, n, ts, ticker, verdict, score, agents=None):
    with sqlite3.connect(tele_db) as c:
        c.execute("INSERT INTO run_summaries (ts, run_id, ticker, company_name, duration_seconds, final_score, "
                  "verdict, agent_scores) VALUES (?, ?, ?, ?, 1.0, ?, ?, ?)",
                  (ts, f"r{n:04d}", ticker, f"{ticker} Ltd", score, verdict, json.dumps(agents or {})))


def _history(score_db):
    with sqlite3.connect(score_db) as c:
        return c.execute("SELECT ticker, run_at, verdict, final_score, agent_scores, report_json "
                         "FROM score_history ORDER BY ticker, run_at").fetchall()


def test_backfill_dry_run_apply_idempotence_cut_off_cap_and_remove(backfill_dbs):
    score_db, tele_db = backfill_dbs
    mod = _backfill_module()
    n = 0
    # QA: two runs, a run with no verdict, one with no score, one with an unreadable time
    for ts, v, s in (("2026-09-01T11:00:00.250000+00:00", "BUY", 0.6), ("2026-09-02T11:00:00+00:00", "SELL", 0.4),
                     ("2026-09-03T11:00:00+00:00", None, 0.5), ("2026-09-04T11:00:00+00:00", "BUY", None),
                     ("not a time", "BUY", 0.5)):
        n += 1
        _log_run(tele_db, n, ts, "QA", v, s, {"fundamentals": 0.61})
    # QB: a live row already recorded on 5 Sep; the run log has runs before and after it
    with sqlite3.connect(score_db) as c:
        c.execute("INSERT INTO score_history (ticker, company_name, run_at, final_score, verdict, agent_scores, "
                  "investment_thesis, conviction_drivers, top_risks, report_json) "
                  "VALUES ('QB', 'QB Ltd', '2026-09-05T11:00:00', 0.5, 'NEUTRAL', '{}', 't', '[]', '[]', '{}')")
    for ts in ("2026-09-04T11:00:00+00:00", "2026-09-05T11:00:00+00:00", "2026-09-06T11:00:00+00:00"):
        n += 1
        _log_run(tele_db, n, ts, "QB", "BUY", 0.6)
    # QC: 95 runs, more than the 90 a stock keeps
    for k in range(95):
        n += 1
        _log_run(tele_db, n, f"2026-06-01T11:00:00+00:00".replace("06-01", f"{6 + k // 28:02d}-{1 + k % 28:02d}"),
                 "QC", "NEUTRAL" if k % 2 else "BUY", 0.5)
    before = _history(score_db)

    dry = mod.run("dry-run")
    assert _history(score_db) == before, "a dry run writes nothing"
    assert (dry["would_insert"], dry["skipped_no_verdict_or_score"], dry["skipped_bad_time"],
            dry["skipped_at_or_after_live_rows"], dry["skipped_over_cap"]) == (2 + 1 + 90, 2, 1, 2, 5)
    assert dry["stocks"] == 3 and "backup" not in dry

    applied = mod.run("apply")
    assert applied["inserted"] == 93 and Path(score_db.parent / applied["backup"]).exists()
    rows = _history(score_db)
    qa = [r for r in rows if r[0] == "QA"]
    assert [(r[1], r[2], r[3]) for r in qa] == [("2026-09-01T11:00:00.250000", "BUY", 0.6),
                                                ("2026-09-02T11:00:00", "SELL", 0.4)], \
        "naive UTC, the format ScoreStore.save writes"
    assert json.loads(qa[0][4]) == {"fundamentals": {"raw": 0.61}}
    assert json.loads(qa[0][5]) == {"backfill": "run_summaries", "run_id": "r0001"}
    assert [r[1] for r in rows if r[0] == "QB"] == ["2026-09-04T11:00:00", "2026-09-05T11:00:00"], \
        "only runs before the first live row; the live row stays"
    qc = [r[1] for r in rows if r[0] == "QC"]
    assert len(qc) == 90 and min(qc) > "2026-06-05", "the newest 90 kept"

    again = mod.run("apply")
    assert again["would_insert"] == 0 and "inserted" not in again and _history(score_db) == rows

    removed = mod.run("remove")
    assert removed["removed"] == 93
    assert _history(score_db) == before, "remove deletes exactly the backfilled rows"
