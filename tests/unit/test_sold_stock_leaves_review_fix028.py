"""FIX-028 — a sold stock leaves the daily review.

Nothing is faked between the executor and the managed file: the real
`execute_advice` trades real portfolio files, and the real promotion reads and
writes a real managed_tickers.json in the test's own folder. Only prices,
NSE's surveillance report (conftest: all clear) and the clock are fixed.

What each test expects is worked by hand from its own fixture:
- a full exit takes a `held` entry off the list (enabled false, sector kept),
  so the daily review's cohort no longer has it; a TRIM that leaves shares, a
  stock another portfolio holds, a stock on a user's own watchlist (kept as a
  weekly `watchlist` entry) and a `manual` entry are not taken off;
- a re-buy re-enables the entry under its old sector, and the cohort has it
  again;
- a sale's room is free before the same run's buy asks for it;
- a buy the list's cap keeps out is named on its digest row, in the digest's
  text and in the morning brief, every run until it gets an entry;
- the release never guesses: an unreadable portfolio releases nothing (and is
  not quarantined), no managed file means nothing is written, the portfolios
  are read under the list's lock, a promotion waits for that lock, and a save
  that fails leaves the old list whole.
"""
from __future__ import annotations

import json
import threading
from datetime import date

import pytest

import services.api.log_buffer as lb
from backend.shared.schemas.discovery import ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord, Holding, WatchlistItem
from core.config import settings
from core.portfolio import autopilot as ap
from core.portfolio import promotion
from core.portfolio.pricing import SessionClose
from core.portfolio.store import PortfolioStore

MON = date(2026, 7, 13)            # the session the sale is booked at
SAT = "2026-07-18"                 # the re-dive after the sale
NEXT_MON = date(2026, 7, 20)       # the session the re-buy is booked at
TODAY = date(2026, 7, 31)          # the executor refuses a review day after today


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    """A managed file and the portfolios in this test's own folder; the
    autopilot on, deployment off, the data gate recording, no caps in the way."""
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    monkeypatch.setattr(lb, "_MANAGED_TICKERS_PATH", tmp_path / "data" / "managed_tickers.json")
    for name, value in {
        "PORTFOLIO_DATA_DIR": str(tmp_path / "pf"), "AUTOPILOT_ENABLED": True,
        "AUTOPILOT_DEPLOY_IDLE_CASH": False, "AUTOPILOT_TRIM_PCT": 25.0,
        "DECISION_GATE_MODE": "record", "ADVISOR_MAX_POSITION_PCT": 100.0,
        "ADVISOR_MAX_SECTOR_PCT": 100.0, "AUTOPILOT_MIN_CASH_FLOOR": 0.0,
        "PORTFOLIO_MAX_MANAGED_TICKERS": 40, "DISCOVERY_REDIVE_AFTER_DAYS": 30,
        "DISCOVERY_STALE_DAYS": 60, "PORTFOLIO_OVERRIDES": {},
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(ap, "_today_ist", lambda: TODAY)
    # The run after MON's close, 17:00 IST on Tue 14 Jul: a sale's stamp dates
    # it (shelf.sale_day), so it must not be the real clock's day (FIX-029).
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-07-14T11:30:00+00:00")
    monkeypatch.setattr(promotion, "resolve_company_name", lambda sym: f"{sym} Ltd")
    monkeypatch.setattr(ap, "session_close",
                        lambda sym, d: (SessionClose(100.0, d, "agree"), d))
    return tmp_path


def _write_managed(*entries: dict) -> None:
    lb._MANAGED_TICKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lb._MANAGED_TICKERS_PATH.write_text(json.dumps(list(entries), indent=2), encoding="utf-8")


def _managed() -> dict[str, dict]:
    return {t["sym"]: t for t in json.loads(lb._MANAGED_TICKERS_PATH.read_text(encoding="utf-8"))}


def _manual(sym: str, sector: str = "automobile", **extra) -> dict:
    """An original-universe entry: no origin, as the seed writes it."""
    return {"sym": sym, "name": sym, "sector": sector, "enabled": True, **extra}


def _held(sym: str, sector: str = "pharma", enabled: bool = True) -> dict:
    return {"sym": sym, "name": sym, "sector": sector, "enabled": enabled, "origin": "held",
            "cadence": "daily", "promoted_at": "2026-07-01"}


def _h(sym: str, qty: float, sector: str = "pharma") -> Holding:
    return Holding(symbol=sym, sector=sector, qty=qty, avg_buy_price=100.0,
                   adj_avg_price=100.0, adj_qty=qty, buy_date="2026-06-01")


def _portfolio(tmp_path, name: str, holdings=(), watchlist=(), autopilot=True) -> PortfolioStore:
    s = PortfolioStore(user_id=name, base_dir=str(tmp_path / "pf"))
    p = s.load()
    p.holdings, p.watchlist = list(holdings), list(watchlist)
    p.cash_deployable, p.capital_in, p.autopilot = 100_000.0, 200_000.0, autopilot
    s.save(p)
    return s


def _advice(sym: str, verdict: str, on: date = MON, switch: str = "") -> AdviceRecord:
    return AdviceRecord(date=on.isoformat(), user_id="u", symbol=sym, verdict=verdict,
                        close=100.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                        switch_candidate=switch, rationale_hash=f"{sym}-{verdict}")


def _run(store: PortfolioStore, advice, on: date = MON, ideas=(), report=None):
    ideas = list(ideas)
    return ap.execute_advice(store, store.load(), list(advice), {}, on,
                             sector_lookup={i.symbol: i.sector for i in ideas},
                             shelf_index={i.symbol: i for i in ideas}, report=report)


def _cohort() -> list[tuple[str, str]]:
    """What the scheduled daily review and the monthly forecast run on
    (scheduler.py and the scheduler API both read this list)."""
    from services.api.routes.scheduler_api import _resolve_tickers
    rows = [(e["sym"], e["sector"]) for e in lb.get_active_tickers_with_sector()]
    assert [(e["sym"], e["sector"]) for e in _resolve_tickers(None)] == rows
    return rows


def _idea(sym: str, sector: str, dived: str = SAT) -> ShelfIdea:
    return ShelfIdea(symbol=sym, sector=sector, added=dived, dived=dived, conviction=0.8,
                     verdict="BUY", data_gate="actionable", entry_low=96.0, entry_high=104.0,
                     invalidation_level=90.0, thesis=f"why {sym}")


# ---------------------------------------------------------------------------
# A full exit, and what is not one
# ---------------------------------------------------------------------------

def test_a_full_exit_takes_the_stock_off_the_daily_review(world):
    """u holds BACK (10) and MARUTI (5); the list has MARUTI (original
    universe) and BACK (held, pharma). EXIT BACK: no portfolio holds it, and
    the only watchlist entry is the autopilot's own exit, so BACK is disabled,
    keeping its sector, origin and cadence; MARUTI is untouched. The cohort
    goes from [MARUTI, BACK] to [MARUTI]."""
    _write_managed(_manual("MARUTI"), _held("BACK"))
    s = _portfolio(world, "u", [_h("BACK", 10), _h("MARUTI", 5, "automobile")])
    assert _cohort() == [("MARUTI", "automobile"), ("BACK", "pharma")]
    sold = _run(s, [_advice("BACK", "EXIT")])
    assert [(t.side, t.symbol, t.qty) for t in sold] == [("SELL", "BACK", 10.0)]
    assert [(w.symbol, w.source) for w in s.load().watchlist] == [("BACK", "autopilot")]
    back = _managed()["BACK"]
    assert (back["enabled"], back["sector"], back["origin"], back["cadence"]) == \
        (False, "pharma", "held", "daily")
    assert _managed()["MARUTI"]["enabled"] is True
    assert _cohort() == [("MARUTI", "automobile")]


def test_a_trim_that_leaves_shares_keeps_the_review(world):
    """TRIM at 25% of 10 shares sells floor(2.5) = 2 and keeps 8: still held."""
    _write_managed(_held("BACK"))
    s = _portfolio(world, "u", [_h("BACK", 10)])
    sold = _run(s, [_advice("BACK", "TRIM")])
    assert [(t.side, t.qty, t.note) for t in sold] == [("SELL", 2.0, "")]
    assert _managed()["BACK"]["enabled"] is True
    assert _cohort() == [("BACK", "pharma")]


def test_a_trim_that_sells_the_last_share_releases_it(world):
    """One share: TRIM sells max(1, floor(0.25)) = 1, `trim_to_zero`. No
    portfolio holds BACK afterwards, so it leaves as a full exit would. (The
    list keeps an original-universe entry, as production's does: the
    scheduler API reviews five fixed tickers when no entry is enabled.)"""
    _write_managed(_manual("MARUTI"), _held("BACK"))
    s = _portfolio(world, "u", [_h("BACK", 1)])
    sold = _run(s, [_advice("BACK", "TRIM")])
    assert [(t.side, t.qty, t.note) for t in sold] == [("SELL", 1.0, "trim_to_zero")]
    assert _managed()["BACK"]["enabled"] is False
    assert _cohort() == [("MARUTI", "automobile")]


def test_a_stock_another_portfolio_holds_stays(world):
    """u exits BACK; v still holds 3 shares (autopilot off), so it stays."""
    _write_managed(_held("BACK"))
    s = _portfolio(world, "u", [_h("BACK", 10)])
    _portfolio(world, "v", [_h("BACK", 3)], autopilot=False)
    _run(s, [_advice("BACK", "EXIT")])
    assert _managed()["BACK"]["enabled"] is True and _managed()["BACK"]["origin"] == "held"


@pytest.mark.parametrize("owner,source,kept", [
    ("v", "user", True),           # another user added it on the home page
    ("v", "discovery", True),      # another user promoted it from the shelf
    ("u", "user", True),           # the seller's own user-added item
    ("v", "autopilot", False),     # another portfolio's autopilot exit is not a user's own
])
def test_a_users_own_watchlist_keeps_it_as_a_weekly_watchlist_entry(world, owner, source, kept):
    """A watchlist item the user (or the shelf, at the user's word) put there
    keeps the stock managed, as a `watchlist` entry: weekly, and evictable at
    the cap like any other. The autopilot's own exit item does not."""
    _write_managed(_held("BACK"))
    item = WatchlistItem(symbol="BACK", sector="pharma", added="2026-07-01", source=source)
    s = _portfolio(world, "u", [_h("BACK", 10)], watchlist=[item] if owner == "u" else [])
    _portfolio(world, "v", [], watchlist=[item] if owner == "v" else [], autopilot=False)
    _run(s, [_advice("BACK", "EXIT")])
    back = _managed()["BACK"]
    if kept:
        assert (back["enabled"], back["origin"], back["cadence"]) == (True, "watchlist", "weekly")
    else:
        assert (back["enabled"], back["origin"]) == (False, "held")


def test_a_manual_entry_is_never_taken_off(world):
    """MARUTI (no origin, the seed's shape) and TCS (origin "manual") are the
    original universe: sold outright, both stay enabled."""
    _write_managed(_manual("MARUTI"), _manual("TCS", "it_sector", origin="manual"))
    s = _portfolio(world, "u", [_h("MARUTI", 5, "automobile"), _h("TCS", 5, "it_sector")])
    sold = _run(s, [_advice("MARUTI", "EXIT"), _advice("TCS", "EXIT")])
    assert sorted(t.symbol for t in sold) == ["MARUTI", "TCS"]
    assert {k: v["enabled"] for k, v in _managed().items()} == {"MARUTI": True, "TCS": True}


def test_a_stock_sold_before_this_change_leaves_on_the_next_run(world):
    """OLDSOLD was sold weeks ago and stayed enabled. A run with no advice and
    no trade still sets the list to follow the holdings: OLDSOLD leaves, the
    held KEEP stays."""
    _write_managed(_held("OLDSOLD"), _held("KEEP"))
    s = _portfolio(world, "u", [_h("KEEP", 4)])
    assert _run(s, []) == []
    assert {k: v["enabled"] for k, v in _managed().items()} == {"OLDSOLD": False, "KEEP": True}


@pytest.mark.parametrize("entry,after", [
    (None, {"enabled": True, "origin": "held", "cadence": "daily", "sector": "pharma"}),
    (_held("HELD", enabled=False), {"enabled": True, "origin": "held", "cadence": "daily"}),
    ({**_held("HELD"), "origin": "watchlist", "cadence": "weekly"},
     {"enabled": True, "origin": "held", "cadence": "daily"}),
    (_manual("HELD", "pharma", enabled=False), {"enabled": False, "origin": None}),
], ids=["no entry", "disabled held entry", "watchlist entry", "original entry disabled by hand"])
def test_a_holding_the_list_waits_for_is_promoted_on_a_run_with_no_trade(world, entry, after):
    """u holds HELD; a run with no advice. With no entry (the cap refused it
    earlier) it is promoted; a disabled held entry is re-enabled; a watchlist
    entry, which the cap may evict, becomes held. An original entry is only
    disabled by the owner, and stays so: only a buy re-enables one."""
    _write_managed(_manual("MARUTI"), *([entry] if entry else []))
    s = _portfolio(world, "u", [_h("HELD", 4)])
    assert _run(s, []) == []
    got = _managed()["HELD"]
    assert {k: got.get(k) for k in after} == after


def test_the_portfolio_just_saved_counts_wherever_it_is_stored(world, caplog):
    """u's store sits outside the data folder the release scans, so only the
    executor's own copy says u holds KEEP: the release leaves KEEP alone (it
    is never disabled, not even until the retry re-enables it) and GONE,
    which nobody holds, leaves."""
    _write_managed(_held("KEEP"), _held("GONE"))
    s = PortfolioStore(user_id="u", base_dir=str(world / "elsewhere"))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = [_h("KEEP", 4)], 1000.0, 1000.0, True
    s.save(p)
    assert promotion.release_unheld(s.load()) == {"released": ["GONE"], "to_watchlist": []}
    _write_managed(_held("KEEP"), _held("GONE"))
    caplog.set_level("INFO", logger="core.portfolio.promotion")
    caplog.clear()
    assert _run(s, []) == []
    assert {k: v["enabled"] for k, v in _managed().items()} == {"KEEP": True, "GONE": False}
    assert [r.getMessage() for r in caplog.records if "no portfolio holds" in r.getMessage()] == \
        ["[promotion] no portfolio holds ['GONE']: disabled ['GONE']; kept for a user's watchlist "
         "(weekly) none"]


# ---------------------------------------------------------------------------
# The re-buy
# ---------------------------------------------------------------------------

def test_a_re_buy_re_enables_it_under_its_old_sector(world):
    """Mon 13 Jul: u exits BACK (pharma) and it leaves the list. Sat 18 Jul
    re-dives it and the dive names "chemicals". Mon 20 Jul: the real
    candidate list offers BACK under its managed sector, pharma (a disabled
    entry still names it), and u switches OLD into it. The executor's
    promotion re-enables the old entry, still pharma, held, daily, and the
    cohort has it again."""
    from core.discovery.candidates import buy_candidates
    _write_managed(_held("BACK"), _held("OLD", "fmcg"))
    s = _portfolio(world, "u", [_h("BACK", 10), _h("OLD", 10, "fmcg")])
    _run(s, [_advice("BACK", "EXIT")])
    assert _managed()["BACK"]["enabled"] is False
    assert _cohort() == [("OLD", "fmcg")]

    offered, why_not = buy_candidates(s.load(), NEXT_MON, [_idea("BACK", "chemicals")])
    assert why_not == {} and [(i.symbol, i.sector) for i in offered] == [("BACK", "pharma")]
    bought = _run(s, [_advice("OLD", "SWITCH", on=NEXT_MON, switch="BACK")],
                  on=NEXT_MON, ideas=offered)
    assert [(t.side, t.symbol) for t in bought] == [("SELL", "OLD"), ("BUY", "BACK")]
    back = _managed()["BACK"]
    assert (back["enabled"], back["sector"], back["origin"], back["cadence"]) == \
        (True, "pharma", "held", "daily")
    assert _managed()["OLD"]["enabled"] is False
    assert _cohort() == [("BACK", "pharma")]


def test_a_sales_room_is_free_before_the_same_runs_buy(world, monkeypatch):
    """Cap 3, full: MARUTI (original), OLD and X (held). SWITCH OLD -> NEW.
    Released first, OLD frees a place (2 enabled), so NEW is promoted (3).
    Promoted first, NEW would meet 3 enabled with nothing evictable."""
    monkeypatch.setattr(settings, "PORTFOLIO_MAX_MANAGED_TICKERS", 3)
    _write_managed(_manual("MARUTI"), _held("OLD", "fmcg"), _held("X"))
    s = _portfolio(world, "u", [_h("OLD", 10, "fmcg"), _h("X", 5)])
    report: dict = {}
    txns = _run(s, [_advice("OLD", "SWITCH", switch="NEW")], ideas=[_idea("NEW", "pharma", "2026-07-08")],
                report=report)
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "OLD"), ("BUY", "NEW")]
    assert {k: v["enabled"] for k, v in _managed().items()} == \
        {"MARUTI": True, "OLD": False, "X": True, "NEW": True}
    assert "not_reviewed" not in report


# ---------------------------------------------------------------------------
# A buy the cap keeps out
# ---------------------------------------------------------------------------

def test_a_buy_the_cap_keeps_out_is_named_in_the_digest_and_the_brief(world, monkeypatch):
    """Through the real 16:30 pipeline, deployment on, ₹12 L in cash and no
    holdings. NEWCO (dived Wed 8 Jul, ₹1,000) qualifies and is bought with
    80% x 12,00,000 / 12 = ₹80,000: 80 shares. The list's cap is 3 and A1-A3
    (original universe) fill it, so NEWCO gets no entry. Its digest row, the
    digest's text and the morning brief say so; NEWCO has no advice today, so
    its verdict is NO_DATA, which the brief would otherwise leave out. The
    next run, with nothing changed, says so again. When A3 is switched off
    by hand, the run after promotes NEWCO and the note is gone."""
    import core.delivery.brief as br
    import core.portfolio.pipeline as pipeline
    import tests.unit.test_deploy_idle_cash_sa049 as story
    from core.portfolio.digest_text import render_digest_text
    for name, value in {
        "PORTFOLIO_COSTS": story.NO_COSTS, "ADVISOR_MAX_POSITION_PCT": 10.0,
        "ADVISOR_MAX_SECTOR_PCT": 30.0, "AUTOPILOT_MIN_CASH_FLOOR": 10_000.0,
        "AUTOPILOT_DEPLOY_IDLE_CASH": True, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY": 2,
        "AUTOPILOT_DEPLOY_TARGET_PCT": dict(story.TARGETS), "PORTFOLIO_MIN_HOLDINGS": 10,
        "PORTFOLIO_TARGET_HOLDINGS": 12, "PORTFOLIO_MAX_HOLDINGS": 15,
        "PORTFOLIO_MAX_MANAGED_TICKERS": 3,
    }.items():
        monkeypatch.setattr(settings, name, value)
    story._regime(monkeypatch, "NORMAL")
    story._report(monkeypatch)
    monkeypatch.setattr(ap, "_today_ist", lambda: TODAY)
    _write_managed(_manual("A1"), _manual("A2"), _manual("A3"))
    idea = story._idea("NEWCO", 1000.0, 0.8, "pharma")
    store, _ = story._pipeline_world(world, monkeypatch, [], 1_200_000.0, [idea],
                                     {"NEWCO": 1000.0})
    why = "no daily review or forecast: managed-ticker cap 3 reached"

    pipeline.run_post_review_pipeline(MON)
    assert story._buys(store.load_transactions()) == [("NEWCO", 80.0, 1000.0)]
    assert "NEWCO" not in _managed()
    row = next(r for r in store.load_latest_digest()["holdings"] if r["symbol"] == "NEWCO")
    assert (row["verdict"], row["not_reviewed"]) == ("NO_DATA", why)
    assert f"NO_DATA: NEWCO — no advisor run for this holding today ({why})" in \
        render_digest_text(store.load_latest_digest())
    for name in ("_narrate_brief",):
        monkeypatch.setattr(br, name, lambda b: "h")
    monkeypatch.setattr(br, "_read_regime", lambda: {})
    monkeypatch.setattr(br, "_overnight_items", lambda on, recent: ([], {}))
    monkeypatch.setattr(br, "_shelf_events_since", lambda since: [])
    monkeypatch.setattr(br, "_earnings_soon", lambda symbols, on: [])
    monkeypatch.setattr(br, "_ipo_watch", lambda on=None: [])
    monkeypatch.setattr(br, "_before_the_open", lambda on: [])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])
    brief = br.build_morning_brief("u", date(2026, 7, 14), store=store)
    assert [(f["symbol"], f["reason"]) for f in brief["advisor_flags"]] == \
        [("NEWCO", f"no advisor run for this holding today ({why})")]

    pipeline.run_post_review_pipeline(date(2026, 7, 14))
    row = next(r for r in store.load_latest_digest()["holdings"] if r["symbol"] == "NEWCO")
    assert row["not_reviewed"] == why

    entries = list(_managed().values())
    entries[2]["enabled"] = False
    _write_managed(*entries)
    pipeline.run_post_review_pipeline(date(2026, 7, 15))
    assert (_managed()["NEWCO"]["enabled"], _managed()["NEWCO"]["origin"]) == (True, "held")
    row = next(r for r in store.load_latest_digest()["holdings"] if r["symbol"] == "NEWCO")
    assert "not_reviewed" not in row


# ---------------------------------------------------------------------------
# The release never guesses
# ---------------------------------------------------------------------------

def test_an_unreadable_portfolio_releases_nothing_and_is_left_as_it_is(world):
    """v's portfolio.json is torn. Read as empty it would say v holds
    nothing, so u's exit of BACK releases nothing, and v's file is neither
    quarantined nor rewritten."""
    _write_managed(_held("BACK"))
    s = _portfolio(world, "u", [_h("BACK", 10)])
    torn = world / "pf" / "v" / "portfolio.json"
    torn.parent.mkdir(parents=True)
    torn.write_bytes(b'{"user_id": "v", "holdings": [{"symbol": "BA')
    _run(s, [_advice("BACK", "EXIT")])
    assert _managed()["BACK"]["enabled"] is True
    assert torn.read_bytes() == b'{"user_id": "v", "holdings": [{"symbol": "BA'
    assert sorted(p.name for p in torn.parent.iterdir()) == ["portfolio.json"]


def test_with_no_managed_file_a_sale_writes_none(world):
    """The release only narrows a list: with no file there is nothing to
    narrow, and it neither seeds one nor takes the lock (which would create
    the data folder)."""
    s = _portfolio(world, "u", [_h("BACK", 10)])
    _run(s, [_advice("BACK", "EXIT")])
    assert not (world / "data").exists()


def test_the_portfolios_are_read_under_the_lists_lock(world, monkeypatch):
    """A promotion saved after its portfolio's buy must not be undone by a
    release that read the portfolios before the buy: so the release reads
    them while it holds the lock the promotion needs."""
    _write_managed(_held("BACK"))
    _portfolio(world, "u", [])
    seen = []
    real = promotion._portfolios_now

    def spy(current=None):
        seen.append(lb.managed_tickers_lock().is_locked)
        return real(current)
    monkeypatch.setattr(promotion, "_portfolios_now", spy)
    assert promotion.release_unheld() == {"released": ["BACK"], "to_watchlist": []}
    assert seen == [True]


def test_a_promotion_waits_for_the_lists_lock(world):
    """While another thread holds the lock, promote_symbol does not write;
    once it is let go, the promotion lands on the list as it then stands."""
    _write_managed(_manual("MARUTI"))
    held, started, done = threading.Event(), threading.Event(), threading.Event()
    release = threading.Event()

    def holder():
        with lb.managed_tickers_lock():
            held.set()
            release.wait(10)

    def promoter():
        started.set()
        promotion.promote_symbol("NEW", "pharma", origin="held")
        done.set()
    t1 = threading.Thread(target=holder)
    t1.start()
    assert held.wait(10)
    t2 = threading.Thread(target=promoter)
    t2.start()
    assert started.wait(10)
    assert not done.wait(0.5)
    assert set(_managed()) == {"MARUTI"}
    release.set()
    t1.join(10)
    t2.join(10)
    assert done.is_set() and set(_managed()) == {"MARUTI", "NEW"}


def test_a_save_that_fails_leaves_the_old_list_whole(world, monkeypatch):
    """The list is written to a temp file and renamed over the old one. A
    rename that fails leaves the old list byte for byte, and no temp file;
    a torn list would have been replaced by the five-ticker seed."""
    import core.utils.atomic_io as aio
    _write_managed(_held("BACK"))
    before = lb._MANAGED_TICKERS_PATH.read_bytes()

    def refuse(src, dst):
        raise PermissionError("held open")
    monkeypatch.setattr(aio, "replace_with_retry", refuse)
    with pytest.raises(PermissionError):
        lb.save_managed_tickers([_held("BACK", enabled=False)])
    assert lb._MANAGED_TICKERS_PATH.read_bytes() == before
    assert sorted(p.name for p in lb._MANAGED_TICKERS_PATH.parent.iterdir()
                  if not p.name.endswith(".lock")) == ["managed_tickers.json"]
