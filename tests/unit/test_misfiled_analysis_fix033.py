"""FIX-033 — a deep dive's idea is the company it was asked about.

On Sat 14 Nov 2026 the deep dive asked about DEEPA (Deepak Automobiles). The
orchestrator sent "DEEPA" to a model as free text, the model answered
DEEPAKNTR (Deepak Nitrite), and the shelf filed Deepak Nitrite's BUY (0.64)
under DEEPA. Tue 17 Nov's run bought 308 DEEPA on that case (B-32 read).

Every expected value below is worked by hand from the fixture, never asked
of the code under test.

1. An exact NSE symbol is analysed as itself: no model is asked (the
   transport raises if called); an unlisted one stops; free text still goes
   to the model (the defect's own path, kept for the chat and Analyze box).
2. A dive whose report is of another company keeps no idea and no memo
   entry, is counted and logged with both symbols; the shelf, the candidate
   list (shelf and watchlist), a SWITCH leg and deployment each refuse an
   idea whose analysis is of another symbol (planted rows).
3. A holding a BUY of which names another symbol's analysis is EXITed at the
   next review, under either exit rule, whatever the stop or forecast says,
   with "bought on DEEPAKNTR's analysis, not DEEPA's" in the ledger.
4. Ideas shelved before FIX-033 are read against the score history: DEEPA's
   is refused from the first review and dropped by the weekly run.

Independent invariants: `analysed_elsewhere` against a reverse-scan oracle
over random ledgers; the candidate list offers a planted idea exactly when
its analysed symbol is unknown or its own, over every (analysed, held) shape.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.discovery.deep_dive as dd
import tests.unit.test_deploy_idle_cash_sa049 as story
import tests.unit.test_idea_supply_pr004 as pr004
from backend.shared.pipeline.no_analysis import UnlistedSymbol
from backend.shared.schemas.discovery import DeepDiveResult, DiscoveryCandidate, Shelf, ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord, Holding, TransactionRecord, WatchlistItem
from core.config import settings
from core.discovery import shelf as shelf_mod
from core.discovery.candidates import buy_candidates
from core.portfolio import autopilot as ap
from core.portfolio.advisor import (
    AdvisorSignals, ExitEvidence, analysed_elsewhere, decide, explain_triggers)
from core.portfolio.results import EXIT_REASONS
from tests.unit.test_deploy_idle_cash_sa049 import _pinned  # noqa: F401  (autouse)
from tests.unit.test_idea_supply_pr004 import shelf  # noqa: F401  (a fixture)

DIVE_DAY = date(2026, 11, 14)                # the Saturday of the misfiled dive
SAT_28 = date(2026, 11, 28)
WRONG = "the analysis is of DEEPAKNTR, not DEEPA"
BOUGHT = "bought on DEEPAKNTR's analysis, not DEEPA's"
# Deepak Nitrite's thesis, longer than the 800 characters an idea keeps.
NITRITE = ("Deepak Nitrite Ltd: phenol-acetone spreads recovering, ₹1,508 then ₹1,602; "
           * 12).strip()
AUTOMOBILES = "Deepak Automobiles Ltd: key managerial resignation; neutral."


# ---------------------------------------------------------------------------
# 1. The orchestrator: an exact symbol is never resolved by a model
# ---------------------------------------------------------------------------

class _Transport:
    """A model transport that answers DEEPAKNTR for anything, and counts."""

    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        body = json.dumps({"ticker": "DEEPAKNTR", "company_name": "Deepak Nitrite Ltd",
                           "exchange": "NSE"})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=body))],
                               usage=None)


@pytest.fixture
def orch(monkeypatch):
    """A generic orchestrator that tracks nothing, whose model transport
    counts calls, with Yahoo answering a price for any symbol and the web
    search refused."""
    import backend.shared.pipeline.base_orchestrator as bo
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    with patch.object(bo, "get_llm_client", return_value=MagicMock()):
        o = GenericSectorOrchestrator()
    o._llm = _Transport()
    monkeypatch.setattr(o, "_managed_tickers", lambda: set())
    monkeypatch.setattr(o, "_tracked_tickers", lambda: set())
    monkeypatch.setattr(o, "_yf_info", lambda t: {"longName": f"{t} Ltd",
                                                  "regularMarketPrice": 100.0})
    monkeypatch.setattr(bo, "log_llm_call", lambda **kw: None)
    monkeypatch.setattr("services.data.fetchers.news.search_serper",
                        lambda *a, **k: pytest.fail("no web search for an exact symbol"))
    return o


def _listing(monkeypatch, listing):
    monkeypatch.setattr("services.data.fetchers.bhavcopy.load_listing", lambda: listing)


def test_the_defect_free_text_deepa_resolves_to_deepak_nitrite(orch, monkeypatch):
    """The 14 Nov path, still the chat's: "DEEPA" as free text goes to the
    model, which answers DEEPAKNTR. One model call."""
    _listing(monkeypatch, pr004.companies("DEEPA", "DEEPAKNTR"))
    query = orch._resolve_ticker("DEEPA")
    assert (query.ticker, orch._llm.calls) == ("DEEPAKNTR", 1)


def test_an_exact_listed_symbol_makes_no_model_call(orch, monkeypatch):
    """DEEPA is listed and neither managed nor tracked: analysed as DEEPA,
    zero model calls."""
    _listing(monkeypatch, pr004.companies("DEEPA", "DEEPAKNTR"))
    query = orch._resolve_ticker("deepa ", exact=True)
    assert (query.ticker, orch._llm.calls) == ("DEEPA", 0)


def test_an_unlisted_exact_symbol_stops_without_a_model(orch, monkeypatch):
    _listing(monkeypatch, pr004.companies("DEEPAKNTR"))
    with pytest.raises(UnlistedSymbol, match="DEEPA is not an NSE-listed symbol"):
        orch._resolve_ticker("DEEPA", exact=True)
    assert orch._llm.calls == 0


def test_with_no_listing_cached_yahoo_decides(orch, monkeypatch):
    """No listing: a symbol Yahoo prices is taken as itself; one it does not
    price stops. No model either way."""
    _listing(monkeypatch, None)
    assert orch._resolve_ticker("DEEPA", exact=True).ticker == "DEEPA"
    monkeypatch.setattr(orch, "_yf_info", lambda t: {})
    with pytest.raises(UnlistedSymbol):
        orch._resolve_ticker("DEEPA", exact=True)
    assert orch._llm.calls == 0


def test_analyse_passes_exact_only_when_asked(monkeypatch):
    """`analyse(..., exact_symbol=True)` asks the resolver for the exact
    symbol; a plain `analyse` (the Analyze box, the chat) does not."""
    from tests.unit.test_sector_naming_fix026 import _quiet_orchestrator
    from backend.shared.schemas.pipeline import StockQuery
    o, _ = _quiet_orchestrator(monkeypatch, None)
    seen = []
    monkeypatch.setattr(o, "_resolve_ticker", lambda user_input, run_id="", **kw:
                        seen.append(kw) or StockQuery(ticker="NEWDRUG", company_name="N"))
    o.analyse("NEWDRUG", exact_symbol=True)
    o.analyse("NEWDRUG")
    assert seen == [{"exact": True}, {}]


def test_the_forecast_paper_lane_and_daily_review_pass_the_exact_symbol(monkeypatch):
    """The monthly forecast, a re-forecast and the paper lane (one helper),
    and the daily review's re-run, ask for the exact symbol."""
    import core.intelligence.rl.workflows.daily_review as dr
    import core.intelligence.rl.workflows.generate_forecast as gf
    import core.intelligence.rl.workflows.sector_router as router
    asked = []

    class _O:
        def set_aggregator_weights(self, weights, ticker):
            pass

        def analyse(self, ticker, exact_symbol=False):
            asked.append((ticker, exact_symbol))
            return SimpleNamespace(weighted_agent_scores={})
    monkeypatch.setattr(gf, "get_orchestrator", lambda sector: _O())
    monkeypatch.setattr(router, "get_orchestrator", lambda sector: _O())
    gf._run_orchestrator_analysis("DEEPA", "generic", {"a": 1.0})
    dr._run_todays_agent_scores("DEEPA", "generic")
    assert asked == [("DEEPA", True), ("DEEPA", True)]


# ---------------------------------------------------------------------------
# 2. The deep dive keeps a result only about the stock asked for
# ---------------------------------------------------------------------------

@pytest.fixture
def dive_world(tmp_path, monkeypatch):
    """run_deep_dives over DEEPA and GOOD, both listed companies, nothing
    managed or shelved; the analyst answers DEEPA's question with Deepak
    Nitrite's report (the 14 Nov answer) and GOOD's with GOOD's."""
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "disc"))
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(dd, "load_managed_tickers", lambda: [])
    monkeypatch.setattr(dd, "market_classification", lambda s: {"sector": "", "industry": ""})
    window = pr004._eod_window(["DEEPA", "GOOD"], days=30, end=date(2026, 11, 13), close=200.0)
    monkeypatch.setattr(dd, "EodStore", lambda: SimpleNamespace(
        load_window=lambda end, sessions: window))
    answers = {"DEEPA": ("DEEPAKNTR", NITRITE), "GOOD": ("GOOD", "Good Ltd: margins up.")}
    asked = []

    class _O:
        def analyse(self, symbol, sector_question=None, exact_symbol=False):
            asked.append((symbol, exact_symbol))
            ticker, thesis = answers[symbol]
            return SimpleNamespace(
                ticker=ticker, final_score=0.64, verdict="BUY", model_verdict="BUY", investment_thesis=thesis,
                decision_gate=SimpleNamespace(status="actionable", run_id=f"r-{symbol}",
                                              reasons=[]),
                sector_answer={"key": "chemicals", "reason": "chemicals", "yahoo_fits": None})
    monkeypatch.setattr(dd, "get_orchestrator", lambda route: _O())
    return SimpleNamespace(answers=answers, asked=asked)


def test_a_dive_about_another_company_shelves_nothing(dive_world, caplog):
    """DEEPA's report is DEEPAKNTR's: no result, no memo entry, counted as a
    call, logged with both symbols. GOOD is kept, stamped GOOD."""
    tally: dict = {}
    cands = [DiscoveryCandidate(symbol=s, close=200.0, composite=0.5) for s in ("DEEPA", "GOOD")]
    with caplog.at_level(logging.WARNING, logger="core.discovery.deep_dive"):
        results = dd.run_deep_dives(cands, on=DIVE_DAY, max_n=10, tally=tally,
                                    listing=pr004.companies("DEEPA", "GOOD", "DEEPAKNTR"))
    assert [(r.symbol, r.analysed_symbol) for r in results] == [("GOOD", "GOOD")]
    assert dive_world.asked == [("DEEPA", True), ("GOOD", True)]
    assert tally["other_company"] == {"DEEPA": "DEEPAKNTR"} and tally["calls"] == 2
    assert f"DEEPA: {WRONG}; not shelved" in caplog.text
    store = shelf_mod.ShelfStore()
    store.record_dives(results, on=DIVE_DAY)
    assert store.recently_dived(DIVE_DAY) == {"GOOD"}
    store.apply_deep_dives(results, on=DIVE_DAY)
    assert [(i.symbol, i.analysed_symbol) for i in store.load().ideas] == [("GOOD", "GOOD")]


def test_a_report_that_names_no_symbol_is_refused_too(dive_world):
    dive_world.answers["GOOD"] = ("", "no name")
    tally: dict = {}
    results = dd.run_deep_dives([DiscoveryCandidate(symbol="GOOD", close=200.0, composite=0.5)],
                                on=DIVE_DAY, max_n=10, tally=tally,
                                listing=pr004.companies("GOOD"))
    assert results == [] and tally["other_company"] == {"GOOD": "?"}


def test_the_exchange_suffix_is_not_another_company(dive_world):
    """A report ticker "GOOD.NS" is GOOD."""
    dive_world.answers["GOOD"] = ("GOOD.NS", "Good Ltd")
    results = dd.run_deep_dives([DiscoveryCandidate(symbol="GOOD", close=200.0, composite=0.5)],
                                on=DIVE_DAY, max_n=10, listing=pr004.companies("GOOD"))
    assert [(r.symbol, r.analysed_symbol) for r in results] == [("GOOD", "GOOD")]


def _misdive(symbol="DEEPA", analysed="DEEPAKNTR", on=DIVE_DAY.isoformat()):
    return pr004.dive(symbol, 0.64, key="chemicals", on=on, close=200.0).model_copy(
        update={"analysed_symbol": analysed})


def test_the_shelf_refuses_a_planted_dive_about_another_company(shelf):
    out = shelf.apply_deep_dives([_misdive(), _misdive("GOOD", "GOOD")], on=DIVE_DAY)
    assert (out["added"], out["other_company"], out["skipped"]) == (["GOOD"], ["DEEPA"],
                                                                    ["DEEPA"])


def test_a_re_dive_about_another_company_drops_the_idea(shelf):
    shelf.save(Shelf(ideas=[pr004._idea("DEEPA", "2026-11-14")]))
    out = shelf.apply_redives([_misdive(on=SAT_28.isoformat())], on=SAT_28)
    assert out["dropped"] == {"DEEPA": f"re-dive 2026-11-28: {WRONG}"}
    assert [i.status for i in shelf.load().ideas] == ["dropped"]


def test_a_re_dive_of_the_stock_itself_stamps_a_legacy_idea(shelf):
    shelf.save(Shelf(ideas=[pr004._idea("GOOD", "2026-11-14")]))
    shelf.apply_redives([_misdive("GOOD", "GOOD", on=SAT_28.isoformat())], on=SAT_28)
    assert [(i.status, i.analysed_symbol) for i in shelf.load().ideas] == [("active", "GOOD")]


# ---------------------------------------------------------------------------
# 2. Every buy door refuses a planted idea about another company
# ---------------------------------------------------------------------------

def _planted(analysed="DEEPAKNTR", symbol="DEEPA"):
    return story._idea(symbol, 1000.0, 0.80, "pharma", analysed_symbol=analysed)


def test_the_candidate_list_leaves_it_out_held_or_not():
    """DEEPA (of DEEPAKNTR) is excluded with the reason; GOOD (its own) and
    OLD (shelved before FIX-033, unknown) are offered, in shelf order."""
    ideas = [_planted(), _planted("GOOD", "GOOD"), _planted("", "OLD")]
    pf = SimpleNamespace(holdings=[], watchlist=[])
    offered, excluded = buy_candidates(pf, story.D, ideas, managed={})
    assert [i.symbol for i in offered] == ["GOOD", "OLD"] and excluded == {"DEEPA": WRONG}
    held = SimpleNamespace(holdings=[story._h("DEEPA", 10, 1000.0, "pharma")], watchlist=[])
    offered, excluded = buy_candidates(held, story.D, ideas, managed={})
    assert excluded == {"DEEPA": WRONG}


@pytest.mark.parametrize("analysed,held", [(a, h) for a in ("", "X", "x.NS", "Y") for h in (0, 1)])
def test_the_list_offers_it_exactly_when_its_analysis_is_its_own(analysed, held):
    """Over every shape: X is offered iff its analysed symbol is unknown or
    X itself (after the suffix), held or not (a held X is offered, as
    before; each door then says "already held")."""
    pf = SimpleNamespace(holdings=[story._h("X", 1, 1000.0, "pharma")] if held else [],
                         watchlist=[])
    offered, excluded = buy_candidates(pf, story.D, [_planted(analysed, "X")], managed={})
    own = analysed.upper().removesuffix(".NS") in ("", "X")
    assert ([i.symbol for i in offered] == ["X"]) is own
    assert (excluded == {} if own else excluded == {"X": f"the analysis is of {analysed}, not X"})


def test_the_watchlist_door_reads_the_rows_own_symbol(monkeypatch):
    """A watchlist DEEPA whose newest BUY row (16:30 IST Fri 10 Jul, 0.80,
    actionable) is DEEPAKNTR's is not offered; the same row as DEEPA's is."""
    for name, value in {"DISCOVERY_WATCHLIST_BUYS": True, "DISCOVERY_STALE_DAYS": 60,
                        "DISCOVERY_REDIVE_AFTER_DAYS": 30,
                        "DISCOVERY_MIN_CONVICTION": 0.55}.items():
        monkeypatch.setattr(settings, name, value)
    pf = SimpleNamespace(holdings=[], watchlist=[WatchlistItem(
        symbol="DEEPA", sector="automobile", added="2026-07-01", source="user")])
    window = pr004._eod_window(["DEEPA"], days=60, end=date(2026, 7, 12), close=500.0)

    def run(ticker):
        return buy_candidates(pf, story.D, [], window=window, managed={},
                              listing=pr004.companies("DEEPA"),
                              analysis_before=lambda s, before: {**pr004.record(), "ticker": ticker})
    assert run("DEEPAKNTR") == ([], {"DEEPA": WRONG})
    offered, excluded = run("DEEPA")
    assert [(i.symbol, i.analysed_symbol) for i in offered] == [("DEEPA", "DEEPA")]


def test_a_switch_leg_refuses_it_and_keeps_the_proceeds(tmp_path, monkeypatch):
    """Y (100 × ₹1,000) is switched by hand into the planted DEEPA: Y is sold,
    nothing bought, ₹1,00,000 stays in cash, said on the SELL. The control
    (DEEPA's own analysis) buys DEEPA up to the 10% cap of equity ₹9,00,000
    (₹8,00,000 cash + Y's ₹1,00,000): ₹90,000 / ₹1,000 = 90 shares, its row
    naming DEEPA's analysis."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    story._prices(monkeypatch, {"DEEPA": 1000.0})
    switch = AdviceRecord(date=story.D.isoformat(), user_id="u", symbol="Y", verdict="SWITCH",
                          close=1000.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                          rationale_hash="x", switch_candidate="DEEPA")
    s = story._store(tmp_path / "a", [story._h("Y", 100, 1000.0, "it_sector")], cash=800_000.0)
    txns, _ = story._run(s, [_planted()], {"Y": 1000.0}, advice=[switch])
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "Y")]
    assert ap.switch_skip_reason(txns[0].note) == f"DEEPA: {WRONG}; ₹1,00,000 stays in cash"
    s = story._store(tmp_path / "b", [story._h("Y", 100, 1000.0, "it_sector")], cash=800_000.0)
    txns, _ = story._run(s, [_planted("DEEPA")], {"Y": 1000.0}, advice=[switch])
    assert [(t.side, t.symbol, t.qty, t.analysed_symbol) for t in txns] == [
        ("SELL", "Y", 100.0, ""), ("BUY", "DEEPA", 90.0, "DEEPA")]


def test_deployment_refuses_it_and_says_why(tmp_path, monkeypatch):
    """₹10 L cash, the planted DEEPA alone: nothing bought, the outcome says
    why. The control buys, and its row names DEEPA's analysis."""
    story._prices(monkeypatch, {"DEEPA": 1000.0})
    s = story._store(tmp_path / "a", [], cash=1_000_000.0)
    txns, record = story._run(s, [_planted()], {})
    assert txns == []
    assert story._outcomes(record)["DEEPA"] == ("other_company", WRONG)
    assert "1 idea whose analysis is of another company" in record["reasons"]
    s = story._store(tmp_path / "b", [], cash=1_000_000.0)
    txns, _ = story._run(s, [_planted("DEEPA")], {})
    assert [(t.symbol, t.analysed_symbol) for t in txns] == [("DEEPA", "DEEPA")]


# ---------------------------------------------------------------------------
# 4. Ideas shelved before FIX-033, read against the score history
# ---------------------------------------------------------------------------

def _rows(*pairs, run_at="2026-11-14T07:09:00"):
    """Score-history rows of the dive day: (ticker, thesis). 07:09 UTC is
    12:39 IST on Sat 14 Nov, the B-32 read's time for DEEPAKNTR."""
    return [{"ticker": t, "thesis": th[:800], "run_at": run_at} for t, th in pairs]


def _legacy(symbol, thesis):
    return ShelfIdea(symbol=symbol, sector="chemicals", added="2026-11-14", conviction=0.64,
                     verdict="BUY", model_verdict="BUY", thesis=thesis[:800], dived="2026-11-14",
                     data_gate="actionable")


def test_history_identity_is_the_one_row_whose_thesis_the_idea_keeps():
    """DEEPA's idea keeps the first 800 characters of Deepak Nitrite's
    thesis: the row with that thesis is DEEPAKNTR's. DEEPA's own row
    (Deepak Automobiles, NEUTRAL) has another thesis."""
    rows = _rows(("DEEPAKNTR", NITRITE), ("DEEPA", AUTOMOBILES))
    assert len(NITRITE) > 800
    assert shelf_mod.history_identity(_legacy("DEEPA", NITRITE), rows) == "DEEPAKNTR"
    assert shelf_mod.history_identity(_legacy("DEEPA", AUTOMOBILES), rows) == "DEEPA"
    # Two symbols with the same thesis, none, or an idea with no thesis: "".
    assert shelf_mod.history_identity(
        _legacy("DEEPA", NITRITE), rows + _rows(("OTHER", NITRITE))) == ""
    assert shelf_mod.history_identity(_legacy("DEEPA", "unmatched"), rows) == ""
    assert shelf_mod.history_identity(_legacy("DEEPA", " "), rows) == ""


def test_the_day_bounds_are_the_ist_day_and_the_next():
    """Sat 14 Nov 00:00 IST = Fri 13 Nov 18:30 UTC; the end is Mon 16 Nov
    00:00 IST less a microsecond = Sun 15 Nov 18:29:59.999999 UTC."""
    assert shelf_mod._thesis_day_bounds(DIVE_DAY) == ("2026-11-13T18:30:00",
                                                      "2026-11-15T18:29:59.999999")


def test_the_score_history_is_read_between_those_bounds(tmp_path, monkeypatch):
    """The real store: a row at 07:09 UTC on 14 Nov is read; one at 18:29 UTC
    on 13 Nov (23:59 IST, the Friday) is not."""
    from services.data.stores.score_store import ScoreStore
    path = str(tmp_path / "scores.db")
    store = ScoreStore(db_path=path)
    with store._conn() as conn:
        for ticker, run_at in (("DEEPAKNTR", "2026-11-14T07:09:00"),
                               ("FRIDAY", "2026-11-13T18:29:00")):
            conn.execute("INSERT INTO score_history (ticker, company_name, run_at, final_score, "
                         "verdict, agent_scores, investment_thesis, conviction_drivers, "
                         "top_risks, report_json) VALUES (?, ?, ?, 0.6, 'BUY', '{}', ?, '[]', "
                         "'[]', '{}')", (ticker, ticker, run_at, NITRITE))
    monkeypatch.setattr("services.data.stores.score_store.ScoreStore",
                        lambda: ScoreStore(db_path=path))
    rows = shelf_mod.score_rows_on(DIVE_DAY)
    assert rows == [{"ticker": "DEEPAKNTR", "thesis": NITRITE[:800]}]
    # The store's cut and the idea's are the same 800 characters.
    assert shelf_mod.history_identity(_legacy("DEEPA", NITRITE), rows) == "DEEPAKNTR"


def test_reading_the_shelf_stamps_copies_and_the_list_refuses_deepa():
    """Three legacy ideas of 14 Nov: DEEPA (Nitrite's thesis), GOOD (its own),
    ODD (no row). Read once for the day; the stored ideas are untouched; the
    list then refuses DEEPA alone."""
    reads = []
    rows = _rows(("DEEPAKNTR", NITRITE), ("GOOD", "Good Ltd: margins up."))
    ideas = [_legacy("DEEPA", NITRITE), _legacy("GOOD", "Good Ltd: margins up."),
             _legacy("ODD", "odd")]
    read = shelf_mod.with_history_identity(ideas, lambda day: reads.append(day) or rows)
    assert reads == [DIVE_DAY]
    assert [i.analysed_symbol for i in read] == ["DEEPAKNTR", "GOOD", ""]
    assert [i.analysed_symbol for i in ideas] == ["", "", ""]
    for i in read:
        i.sector_reading = story._idea("Z", 1.0).sector_reading.model_copy(
            update={"answer": "chemicals"})
    offered, excluded = buy_candidates(SimpleNamespace(holdings=[], watchlist=[]),
                                       date(2026, 11, 17), read, managed={})
    assert excluded == {"DEEPA": WRONG}


def test_an_unread_history_leaves_the_ideas_as_they_were():
    def boom(day):
        raise RuntimeError("database is locked")
    ideas = [_legacy("DEEPA", NITRITE)]
    assert shelf_mod.with_history_identity(ideas, boom) == ideas


def test_the_weekly_run_drops_deepa_and_forgets_its_dive(shelf):
    """verify_analyses: DEEPA dropped with the reason and gone from the dive
    memo; GOOD stamped; ODD left unverified. A second run changes nothing."""
    shelf.save(Shelf(ideas=[_legacy("DEEPA", NITRITE), _legacy("GOOD", "Good Ltd: margins up."),
                            _legacy("ODD", "odd")]))
    shelf.record_dives([_misdive(), _misdive("GOOD", "GOOD"), _misdive("ODD", "")], on=DIVE_DAY)
    rows = _rows(("DEEPAKNTR", NITRITE), ("GOOD", "Good Ltd: margins up."))
    out = shelf.verify_analyses(lambda day: rows)
    why = "its deep dive of 2026-11-14 analysed DEEPAKNTR, not DEEPA"
    assert out == {"verified": ["GOOD"], "dropped": {"DEEPA": why}, "unverified": ["ODD"]}
    assert [(i.symbol, i.status, i.analysed_symbol) for i in shelf.load().ideas] == [
        ("DEEPA", "dropped", "DEEPAKNTR"), ("GOOD", "active", "GOOD"), ("ODD", "active", "")]
    assert shelf.recently_dived(DIVE_DAY) == {"GOOD", "ODD"}
    events = [json.loads(line) for line in shelf._events_path.read_text().splitlines()]
    assert {"event": "dropped", "symbol": "DEEPA", "detail": why}.items() <= events[-1].items()
    assert shelf.verify_analyses(lambda day: rows) == {
        "verified": [], "dropped": {}, "unverified": ["ODD"]}


def test_the_weekly_run_calls_the_check_before_the_re_dives(monkeypatch):
    """The discovery run's hygiene: verify_analyses, then redive_due."""
    import inspect
    import core.discovery as disc
    src = inspect.getsource(disc)
    assert src.index("verify_analyses()") < src.index("redive_due(on, sold)")


@pytest.mark.parametrize("history,bought", [
    (True, [("GOOD", 66.0, "GOOD")]),
    (False, [("DEEPA", 66.0, ""), ("GOOD", 66.0, "")])])
def test_the_first_review_after_the_deploy_refuses_the_legacy_idea(tmp_path, monkeypatch,
                                                                   history, bought):
    """The real pipeline on Mon 13 Jul, ₹10 L cash, the shelf holding DEEPA
    (Nitrite's thesis) and GOOD (its own), both legacy, both ₹1,000 in band.
    The score history shows DEEPA's thesis is DEEPAKNTR's: deployment buys
    GOOD only, a new position's 80% of equity / 12 = ₹66,667, so 66 shares.
    Control, no history rows: both are bought (2 a day), DEEPA first at
    0.90, so the history read is what refuses it."""
    import core.portfolio.pipeline as pipeline
    from core.intelligence.regime import state
    monkeypatch.setattr(ap, "_today_ist", lambda: story.D)
    deepa = story._idea("DEEPA", 1000.0, 0.90, "pharma").model_copy(
        update={"thesis": NITRITE[:800]})
    good = story._idea("GOOD", 1000.0, 0.80, "fmcg").model_copy(
        update={"thesis": "Good Ltd: margins up."})
    store, _ = story._pipeline_world(tmp_path, monkeypatch, [], 1_000_000.0, [deepa, good],
                                     {"DEEPA": 1000.0, "GOOD": 1000.0})
    rows = _rows(("DEEPAKNTR", NITRITE), ("GOOD", "Good Ltd: margins up."),
                 run_at="2026-07-08T07:00:00")
    monkeypatch.setattr(shelf_mod, "score_rows_on", lambda day: rows if history else [])
    state.update_sticky_regime("NORMAL", story.D.isoformat())
    pipeline.run_post_review_pipeline(story.D)
    buys = [(t.symbol, t.qty, t.analysed_symbol) for t in store.load_transactions()
            if t.side == "BUY"]
    assert buys == bought


# ---------------------------------------------------------------------------
# 3. A holding bought on another company's analysis is sold
# ---------------------------------------------------------------------------

def _txn(n, symbol, side, qty_after, analysed=""):
    return TransactionRecord(
        txn_id=f"t{n}", date="2026-11-17", ts="2026-11-17T11:00:00+00:00", user_id="u",
        symbol=symbol, side=side, qty=1.0, price=1.0, value=1.0, cash_before=0.0,
        cash_after=0.0, holding_qty_after=qty_after, analysed_symbol=analysed)


def test_analysed_elsewhere_follows_the_open_position():
    """Bought on DEEPAKNTR's analysis: named. A top-up naming nothing and a
    trim leaving shares keep it; the sale to zero clears it; a new buy on
    DEEPA's own analysis names nothing."""
    ledger = [_txn(1, "DEEPA", "BUY", 308.0, "DEEPAKNTR")]
    assert analysed_elsewhere(ledger) == {"DEEPA": BOUGHT}
    ledger += [_txn(2, "DEEPA", "BUY", 320.0), _txn(3, "DEEPA", "SELL", 300.0)]
    assert analysed_elsewhere(ledger) == {"DEEPA": BOUGHT}
    ledger += [_txn(4, "DEEPA", "SELL", 0.0)]
    assert analysed_elsewhere(ledger) == {}
    ledger += [_txn(5, "DEEPA", "BUY", 10.0, "deepa.NS")]
    assert analysed_elsewhere(ledger) == {}


def test_analysed_elsewhere_against_an_oracle():
    """500 random ledgers over A, B, C: a symbol is named exactly when, after
    its last sale to zero (found scanning backwards), some BUY names an
    analysed symbol other than "" and itself."""
    rng = random.Random(33)
    for _ in range(500):
        ledger = []
        for n in range(rng.randint(0, 12)):
            sym = rng.choice("ABC")
            side = rng.choice(["BUY", "BUY", "SELL"])
            after = 0.0 if side == "SELL" and rng.random() < 0.5 else 5.0
            analysed = rng.choice(["", sym, "Z", f"{sym}.NS"]) if side == "BUY" else ""
            ledger.append(_txn(n, sym, side, after, analysed))
        oracle = {}
        for sym in "ABC":
            rows = [t for t in ledger if t.symbol == sym]
            last_flat = max((k for k, t in enumerate(rows)
                             if t.side == "SELL" and t.holding_qty_after == 0.0), default=-1)
            others = [t.analysed_symbol for t in rows[last_flat + 1:] if t.side == "BUY"
                      and t.analysed_symbol not in ("", sym, f"{sym}.NS")]
            if others:
                oracle[sym] = f"bought on {others[-1]}'s analysis, not {sym}'s"
        assert analysed_elsewhere(ledger) == oracle


def _held(pnl=5.0, envelope="UP", other=BOUGHT):
    """DEEPA at +5% with a rising path, healthy accuracy and a small weight:
    with no other fact the advisor ADDs."""
    holding = Holding(symbol="DEEPA", sector="chemicals", qty=308, avg_buy_price=211.86,
                      adj_avg_price=211.86, adj_qty=308, buy_date="2026-11-17")
    sig = AdvisorSignals(symbol="DEEPA", sector="chemicals", close=222.45, atr_stop_pct=12.0,
                         unrealised_pnl_pct=pnl, holding_age_days=6, envelope_direction=envelope,
                         direction_accuracy_7d=0.9, position_weight_pct=1.0,
                         bought_on_other=other)
    return holding, sig


@pytest.mark.parametrize("rule", ["legacy", "evidence"])
def test_the_advisor_exits_it_whatever_the_stop_or_forecast_says(rule):
    """Control: without the fact, ADD. With it, EXIT under either rule, the
    trigger first, the reason on the record; the evidence rule's minimum
    hold (6 days, 4 sessions) does not hold it."""
    holding, sig = _held(other="")
    assert decide(sig, holding, "balanced", exit_rule=rule,
                  evidence=ExitEvidence(sessions_held=4)).verdict == "ADD"
    holding, sig = _held()
    rec = decide(sig, holding, "balanced", exit_rule=rule, evidence=ExitEvidence(sessions_held=4))
    assert (rec.verdict, rec.triggers[0], rec.bought_on_other) == (
        "EXIT", "bought_on_other_analysis", BOUGHT)


def test_an_unreconciled_identity_still_holds_first():
    """SA-008's hold (the close is not this holding's price basis) comes
    before every verdict, this one included: an operator reconciles first."""
    holding, sig = _held()
    rec = decide(sig, holding, "balanced", identity_hold="demerged")
    assert (rec.verdict, rec.notes) == ("HOLD", ["IDENTITY"])


def test_the_reason_is_told_in_fixed_words_never_by_the_model(monkeypatch):
    from core.portfolio import narrator
    monkeypatch.setattr(settings, "ADVISOR_NARRATE", True)
    monkeypatch.setattr(narrator, "get_llm_client",
                        lambda: pytest.fail("the model narrates no misfiled sale"))
    holding, sig = _held()
    rec = decide(sig, holding, "balanced")
    assert narrator.narrate(rec, sig) == (
        f"EXIT — {BOUGHT} Your position: +5.0% vs a 12.0% stop.")
    assert explain_triggers(["bought_on_other_analysis"]) == \
        "It was bought on another company's analysis."
    assert EXIT_REASONS[0] == ("bought_on_other_analysis", "another company's analysis")


def test_the_next_review_sells_it_with_the_reason_in_the_ledger(tmp_path, monkeypatch):
    """The real pipeline: DEEPA, 100 bought at ₹1,000 on DEEPAKNTR's analysis,
    closes at ₹1,050 (+5%, no stop near). The review sells all 100 at ₹1,050
    and the SELL row's reason names both symbols. GOOD, bought on its own
    analysis, is held."""
    import core.portfolio.pipeline as pipeline
    from core.portfolio.narrator import narrate
    from core.intelligence.regime import state
    monkeypatch.setattr(ap, "_today_ist", lambda: story.D)
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    monkeypatch.setattr(settings, "ADVISOR_NARRATE", False)     # GOOD: no model in tests
    store, _ = story._pipeline_world(
        tmp_path, monkeypatch, [story._h("DEEPA", 100, 1000.0, "chemicals"),
                                story._h("GOOD", 100, 1000.0, "fmcg")], 800_000.0, [],
        {"DEEPA": 1050.0, "GOOD": 1050.0})
    monkeypatch.setattr(pipeline, "narrate", narrate)
    for n, (sym, analysed) in enumerate((("DEEPA", "DEEPAKNTR"), ("GOOD", "GOOD"))):
        store.append_transaction(TransactionRecord(
            txn_id=f"b{n}", date="2026-07-07", ts="2026-07-07T11:00:00+00:00", user_id="u",
            symbol=sym, side="BUY", qty=100.0, price=1000.0, value=100_000.0,
            cash_before=1_000_000.0 - n * 100_000.0, cash_after=900_000.0 - n * 100_000.0,
            holding_qty_after=100.0, verdict="DEPLOY", analysed_symbol=analysed))
    state.update_sticky_regime("NORMAL", story.D.isoformat())
    pipeline.run_post_review_pipeline(story.D)
    sells = [t for t in store.load_transactions() if t.side == "SELL"]
    assert [(t.symbol, t.qty, t.price, t.triggers) for t in sells] == [
        ("DEEPA", 100.0, 1050.0, ["bought_on_other_analysis"])]
    assert sells[0].reason.startswith(f"EXIT — {BOUGHT}")
    assert [h.symbol for h in store.load().holdings] == ["GOOD"]
