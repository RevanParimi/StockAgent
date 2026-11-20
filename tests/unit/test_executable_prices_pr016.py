"""PR-016 — what the book earns at prices that could really be had: invariant tests.

Every expected figure is worked out by hand in the comments, never read back
from the implementation. The NSE calendar is pinned (no holidays), so the
sessions are the weekdays of a calendar: Mon 2 Mar 2026 to Fri 6 Mar, Sunday
8 Mar ends ISO week 2026-W10. A run at 16:30 IST is 11:00 UTC.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

import core.intelligence.rl.nse_calendar as cal
from backend.shared.schemas.portfolio import AppliedCorpAction, TradeCosts, TransactionRecord
from core.portfolio import executable as X
from core.portfolio import results as R
from core.portfolio.corp_actions import ActionRecord
from core.portfolio.store import PortfolioStore
from services.data.stores.eod_store import EodStore


@pytest.fixture(autouse=True)
def _no_holidays(monkeypatch):
    monkeypatch.setattr(cal, "_NSE_HOLIDAYS", frozenset())


MON, TUE, WED, THU, FRI = (date(2026, 3, d) for d in (2, 3, 4, 5, 6))
SUN = date(2026, 3, 8)
_SEQ = [0]


def at(day: date, hh: int, mm: int = 0) -> str:
    """A UTC timestamp for hh:mm IST on `day`."""
    ist = datetime(day.year, day.month, day.day, hh, mm, tzinfo=cal.IST)
    return ist.astimezone(timezone.utc).isoformat()


def tx(day, sym, side, qty, price, *, after=None, run=None, source="autopilot", costs=None,
       user="u1"):
    _SEQ[0] += 1
    run = run or at(cal.next_trading_day(day), 16, 30)
    return TransactionRecord(
        txn_id=f"x{_SEQ[0]}", date=day.isoformat(), ts=run, user_id=user, symbol=sym,
        side=side, qty=qty, price=price, value=round(qty * price, 2), cash_before=0.0,
        cash_after=0.0, holding_qty_after=(qty if side == "BUY" else 0.0) if after is None
        else after, source=source, verdict="" if side == "BUY" else "EXIT", costs=costs)


class Panel:
    """A fake EOD panel: {(symbol, day): (open, close)} and the days on disk."""

    def __init__(self, bars: dict, days=None):
        self.bars = dict(bars)
        self.days = set(days) if days is not None else {d for _s, d in bars}

    def __call__(self, symbol, day):
        if day not in self.days:
            return X.PanelBar(None, None, False)
        hit = self.bars.get((symbol, day))
        return X.PanelBar(*hit, True) if hit else X.PanelBar(None, None, True)


DIVIDEND_LONG_AGO = ActionRecord(covers_from="2020-08-01", rows=1)


def actions(*acts, covers_from="2020-08-01", basis_changes=()):
    return lambda symbol: ActionRecord(actions=tuple(acts), covers_from=covers_from,
                                       rows=len(acts) + 1, basis_changes=basis_changes)


def split(ex: date, ratio: float, sym="AAA", kind="split"):
    return AppliedCorpAction(key=f"{sym}|{ex}|{kind}", ex_date=ex.isoformat(), kind=kind,
                             desc=kind, ratio=ratio, applied_on=ex.isoformat())


def no_actions(symbol):
    return DIVIDEND_LONG_AGO


# -- 1. The card's example -----------------------------------------------------------------

def test_the_cards_example_books_at_100_and_could_have_paid_102_or_104():
    """Monday closes at ₹100. Tuesday opens at ₹102 and closes at ₹103.
    Wednesday opens at ₹104. Tuesday's 16:30 run books a BUY at ₹100 (dated
    Monday). A person pays ₹102 at the next open (+2%), ₹104 as the job runs
    now (+4%)."""
    panel = Panel({("AAA", MON): (99.0, 100.0), ("AAA", TUE): (102.0, 103.0),
                   ("AAA", WED): (104.0, 105.0)})
    t = tx(MON, "AAA", "BUY", 10, 100.0, run=at(TUE, 16, 30))
    row = X.price_trade(t, panel=panel, corp_actions=no_actions, today=SUN)
    assert row["booked_is_session_close"] is True
    assert row["open_next"]["session"] == "2026-03-03"
    assert row["open_next"]["open"] == 102.0 and row["open_next"]["status"] == X.PRICED
    assert row["open_next"]["gap_pct"] == pytest.approx(2.0)
    assert row["open_as_run"]["session"] == "2026-03-04"
    assert row["open_as_run"]["open"] == 104.0
    assert row["open_as_run"]["gap_pct"] == pytest.approx(4.0)
    assert X.settled(row)


def test_the_run_decides_which_open_it_could_still_act_at():
    """A run at 16:30 acts at the next session's open; one at 08:30 IST on a
    trading day at that day's open (the pre-open auction starts at 09:00);
    one at 09:05 at the next day's; one on Saturday at Monday's. Never before
    the open after the booked close: a run at 08:30 on the booked day itself
    still gets Tuesday's open."""
    s = X.first_session_after_run
    assert s(datetime(2026, 3, 3, 16, 30, tzinfo=cal.IST)) == WED
    assert s(datetime(2026, 3, 4, 8, 30, tzinfo=cal.IST)) == WED
    assert s(datetime(2026, 3, 4, 9, 5, tzinfo=cal.IST)) == THU
    assert s(datetime(2026, 3, 7, 10, 0, tzinfo=cal.IST)) == date(2026, 3, 9)
    bars = {("AAA", d): (100.0 + i, 100.0) for i, d in enumerate((MON, TUE, WED, THU, FRI))}
    early = tx(MON, "AAA", "BUY", 1, 100.0, run=at(MON, 8, 30))
    row = X.price_trade(early, panel=Panel(bars), corp_actions=no_actions, today=SUN)
    assert row["open_as_run"]["session"] == "2026-03-03" == row["open_next"]["session"]
    late = tx(MON, "AAA", "BUY", 1, 100.0, run=at(WED, 8, 30))   # a retry on Wednesday
    row = X.price_trade(late, panel=Panel(bars), corp_actions=no_actions, today=SUN)
    assert (row["open_next"]["session"], row["open_as_run"]["session"]) == (
        "2026-03-03", "2026-03-04")


# -- 2. The invariant: never a bar on or before the booked close ---------------------------

@pytest.mark.parametrize("seed", range(8))
def test_a_real_price_never_comes_from_a_bar_on_or_before_the_booked_close(seed):
    """Random ledgers, runs at any hour from the booked day to five days on
    (before the pre-open, during the session, after the close, at weekends).
    Every bar's open encodes its own day, and the booked day's open is a
    sentinel. Every price taken is the open of a session after the booked
    one, exactly as the panel has it (no corporate action), and the
    as-run session is never before the next-open one."""
    rng = random.Random(seed)
    days = [date(2026, 2, 2) + timedelta(days=i) for i in range(50)]
    sessions = [d for d in days if cal.is_trading_day(d)]
    bars = {}
    for sym in ("AAA", "BBB", "CCC"):
        for d in sessions:
            bars[(sym, d)] = (1000.0 + d.toordinal() % 1000, 500.0 + d.toordinal() % 500)
    today = days[-1] + timedelta(days=1)
    for _ in range(60):
        booked = rng.choice(sessions[:-8])
        sym = rng.choice(("AAA", "BBB", "CCC"))
        panel = Panel({**bars, (sym, booked): (999999.0, bars[(sym, booked)][1])})
        run_day = booked + timedelta(days=rng.randint(0, 5))
        run = at(run_day, rng.randint(0, 23), rng.choice((0, 15, 59)))
        price = rng.choice((bars[(sym, booked)][1], 123.0))
        t = tx(booked, sym, rng.choice(("BUY", "SELL")), 5, price, run=run)
        row = X.price_trade(t, panel=panel, corp_actions=no_actions, today=today)
        seen = []
        for kind in X.KINDS:
            p = row[kind]
            assert p["status"] == X.PRICED, (kind, p)
            session = date.fromisoformat(p["session"])
            assert session > booked
            assert p["open"] == bars[(sym, session)][0] != 999999.0
            seen.append(session)
        assert seen[1] >= seen[0]


def test_a_session_on_or_before_the_booked_close_is_refused_outright():
    t = tx(TUE, "AAA", "BUY", 1, 100.0)
    for session in (MON, TUE):
        p = X.price_at(t, session, booked=TUE, decided=TUE,
                       panel=Panel({("AAA", MON): (1.0, 1.0), ("AAA", TUE): (1.0, 1.0)}),
                       record=lambda: DIVIDEND_LONG_AGO, today=SUN)
        assert p["status"] == X.NO_PRICE and p["open"] is None


# -- 3. Splits and other corporate actions ---------------------------------------------------

def test_a_split_on_the_next_session_is_not_a_50_percent_gap():
    """Booked at Monday's NSE close, ₹100. A 1:2 split (ratio 2) goes ex on
    Tuesday, which opens at ₹51: ₹102 in Monday's shares, +2%, not −49%.
    Wednesday opens at ₹52: ₹104, +4%."""
    panel = Panel({("AAA", MON): (99.0, 100.0), ("AAA", TUE): (51.0, 51.5),
                   ("AAA", WED): (52.0, 52.5)})
    t = tx(MON, "AAA", "BUY", 10, 100.0, run=at(TUE, 16, 30))
    row = X.price_trade(t, panel=panel, corp_actions=actions(split(TUE, 2.0)), today=SUN)
    assert row["open_next"]["raw_open"] == 51.0
    assert row["open_next"]["open"] == pytest.approx(102.0)
    assert row["open_next"]["gap_pct"] == pytest.approx(2.0)
    assert "split ex 2026-03-03" in row["open_next"]["basis"]
    assert row["open_as_run"]["open"] == pytest.approx(104.0)


def test_a_booked_price_that_may_already_be_adjusted_has_no_price_across_the_split():
    """The same split, but the book holds ₹50: not Monday's NSE close (₹100),
    so the run, on Tuesday after the ex-date, may have read a close already
    halved. ₹51 cannot be put in its basis: no price, for good, never +2% or
    −49%."""
    panel = Panel({("AAA", MON): (99.0, 100.0), ("AAA", TUE): (51.0, 51.5),
                   ("AAA", WED): (52.0, 52.5)})
    t = tx(MON, "AAA", "BUY", 10, 50.0, run=at(TUE, 16, 30))
    row = X.price_trade(t, panel=panel, corp_actions=actions(split(TUE, 2.0)), today=SUN)
    for kind in X.KINDS:
        assert row[kind]["status"] == X.NO_PRICE and row[kind]["open"] is None
        assert "either side" in row[kind]["no_price"]
    assert X.settled(row)


def test_a_split_after_the_run_is_converted_even_when_the_booked_close_is_unconfirmed():
    """Monday's file is missing, so the booked ₹100 cannot be checked. The
    split goes ex on Wednesday, after Tuesday's run: Tuesday's open (₹102)
    needs nothing, Wednesday's ₹52 is ₹104 in the old shares."""
    panel = Panel({("AAA", TUE): (102.0, 103.0), ("AAA", WED): (52.0, 52.5)})
    t = tx(MON, "AAA", "BUY", 10, 100.0, run=at(TUE, 16, 30))
    row = X.price_trade(t, panel=panel, corp_actions=actions(split(WED, 2.0)), today=SUN)
    assert row["booked_is_session_close"] is False
    assert row["open_next"]["open"] == 102.0 and row["open_next"]["basis"] == ""
    assert row["open_as_run"]["open"] == pytest.approx(104.0)


def test_a_demerger_an_empty_list_or_a_registry_break_give_no_price_for_good(monkeypatch):
    panel = Panel({("AAA", MON): (99.0, 100.0), ("AAA", TUE): (70.0, 70.0),
                   ("AAA", WED): (71.0, 71.0)})
    t = tx(MON, "AAA", "BUY", 10, 100.0)
    demerged = actions(basis_changes=(("2026-03-03", "demerger"),))
    row = X.price_trade(t, panel=panel, corp_actions=demerged, today=SUN)
    assert row["open_next"]["status"] == X.NO_PRICE and "demerger" in row["open_next"]["no_price"]
    empty = lambda s: ActionRecord()        # NSE lists nothing for the stock
    row = X.price_trade(t, panel=panel, corp_actions=empty, today=SUN)
    assert row["open_next"]["status"] == X.NO_PRICE and "empty" in row["open_next"]["no_price"]
    monkeypatch.setattr(X, "registry_break",
                        lambda s, a, b: "the instrument registry says the price basis changed")
    row = X.price_trade(t, panel=panel, corp_actions=no_actions, today=SUN)
    assert row["open_next"]["status"] == X.NO_PRICE
    assert "registry" in row["open_next"]["no_price"]


def test_an_unread_nse_list_waits_and_is_not_written(tmp_path):
    panel = Panel({("AAA", MON): (99.0, 100.0), ("AAA", TUE): (102.0, 102.0),
                   ("AAA", WED): (104.0, 104.0)})
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    t = tx(MON, "AAA", "BUY", 10, 100.0)
    rows = X.refresh(store, [t], panel=panel, corp_actions=lambda s: None, today=SUN)
    assert rows[0]["open_next"]["status"] == X.PENDING
    assert "could not be read" in rows[0]["open_next"]["no_price"]
    assert store.load_executable_prices() == []


# -- 4. Missing bars: no price, counted, nothing guessed ---------------------------------------

def test_a_missing_bar_is_no_price_on_the_row_and_a_count_on_the_line(tmp_path):
    """Tuesday's file is there but has no bar for AAA (not traded): the
    next-open price is "no price", written, and the line counts it."""
    panel = Panel({("AAA", MON): (99.0, 100.0), ("AAA", WED): (104.0, 104.0),
                   ("ZZZ", TUE): (5.0, 5.0)})
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    t = tx(MON, "AAA", "BUY", 10, 100.0, run=at(TUE, 16, 30))
    rows = X.refresh(store, [t], panel=panel, corp_actions=no_actions, today=SUN)
    nxt = rows[0]["open_next"]
    assert nxt["status"] == X.NO_PRICE and nxt["open"] is None
    assert nxt["no_price"] == "no bar for AAA on 2026-03-03"
    assert [r["txn_id"] for r in store.load_executable_prices()] == [t.txn_id]
    block = X.scorecard_block([t], rows, end=SUN, since_start={"available": False,
                                                               "reason": "no valuation"})
    assert (block["open_next"]["priced"], block["open_next"]["no_price"]) == (0, 1)
    text = X.line_text(block)
    assert "1 with no price at the next open" in text
    assert "kept at its booked close" in text and text.endswith("1 trade; 1 with no price "
                                                                "at the next open, each kept "
                                                                "at its booked close.")


def test_a_missing_day_file_waits_a_week_then_is_no_price():
    """The daily sync re-reads 7 days back: a file missing 3 days after its
    session may still come (pending); 8 days after, it will not (no price)."""
    panel = Panel({("AAA", MON): (99.0, 100.0)}, days={MON})
    t = tx(MON, "AAA", "BUY", 10, 100.0, run=at(TUE, 16, 30))
    row = X.price_trade(t, panel=panel, corp_actions=no_actions, today=TUE + timedelta(days=3))
    assert row["open_next"]["status"] == X.PENDING and not X.settled(row)
    row = X.price_trade(t, panel=panel, corp_actions=no_actions, today=TUE + timedelta(days=8))
    assert row["open_next"]["status"] == X.NO_PRICE
    assert row["open_next"]["no_price"] == "the EOD panel has no file for 2026-03-03"


def test_a_session_not_over_yet_is_pending():
    panel = Panel({("AAA", THU): (99.0, 100.0), ("AAA", FRI): (101.0, 101.0)})
    t = tx(THU, "AAA", "BUY", 10, 100.0, run=at(FRI, 16, 30))
    row = X.price_trade(t, panel=panel, corp_actions=no_actions, today=date(2026, 3, 8))
    assert row["open_next"]["status"] == X.PRICED
    assert row["open_as_run"]["session"] == "2026-03-09"
    assert row["open_as_run"]["status"] == X.PENDING and not X.settled(row)


# -- 5. The side file: once per transaction, the ledger untouched -----------------------------

def test_running_twice_adds_no_row_and_a_pending_row_is_written_once_settled(tmp_path):
    bars = {("AAA", MON): (99.0, 100.0), ("AAA", TUE): (102.0, 103.0),
            ("AAA", WED): (104.0, 105.0), ("BBB", THU): (50.0, 50.0),
            ("BBB", FRI): (51.0, 51.0)}
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    a = tx(MON, "AAA", "BUY", 10, 100.0, run=at(TUE, 16, 30))
    b = tx(THU, "BBB", "BUY", 10, 50.0, run=at(FRI, 16, 30))   # as-run: Mon 9 Mar
    X.refresh(store, [a, b], panel=Panel(bars), corp_actions=no_actions, today=SUN)
    X.refresh(store, [a, b], panel=Panel(bars), corp_actions=no_actions, today=SUN)
    assert [r["txn_id"] for r in store.load_executable_prices()] == [a.txn_id]
    later = {**bars, ("BBB", date(2026, 3, 9)): (52.0, 52.0)}
    rows = X.refresh(store, [a, b], panel=Panel(later), corp_actions=no_actions,
                     today=date(2026, 3, 15))
    assert [r["txn_id"] for r in store.load_executable_prices()] == [a.txn_id, b.txn_id]
    assert rows[1]["open_as_run"]["open"] == 52.0
    first = store.load_executable_prices()[0]
    X.refresh(store, [a, b], panel=Panel({}), corp_actions=no_actions, today=date(2026, 3, 30))
    assert store.load_executable_prices()[0] == first       # a stored row is never rewritten
    assert len(store.load_executable_prices()) == 2
    assert store.append_executable_prices_once([dict(first)]) == 0


def test_seed_manual_and_dividend_rows_get_no_row():
    panel = Panel({("AAA", d): (100.0, 100.0) for d in (MON, TUE, WED)})
    for t in (tx(MON, "AAA", "BUY", 10, 100.0, source="manual"),
              tx(MON, "AAA", "BUY", 10, 100.0, source="seed")):
        assert X.price_trade(t, panel=panel, corp_actions=no_actions, today=SUN) is None
    div = tx(MON, "AAA", "BUY", 10, 100.0).model_copy(update={"side": "DIV", "qty": 0.0})
    assert X.price_trade(div, panel=panel, corp_actions=no_actions, today=SUN) is None


def _book(tmp_path):
    """The hand-worked book of section 6, in a store."""
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.append_value_point({"date": "2026-03-02", "total_equity": 100000.0,
                              "capital_in": 100000.0, "cash": 100000.0, "market_value": 0.0})
    store.append_value_point({"date": "2026-03-05", "total_equity": 105000.0,
                              "capital_in": 100000.0, "cash": 105000.0, "market_value": 0.0})
    txns = [tx(MON, "AAA", "BUY", 100, 100.0, run=at(TUE, 16, 30)),
            tx(TUE, "BBB", "BUY", 50, 200.0, run=at(WED, 16, 30)),
            tx(WED, "AAA", "SELL", 100, 110.0, run=at(THU, 16, 30))]
    for t in txns:
        store.append_transaction(t)
    return store, txns


BOOK_PANEL = Panel({("AAA", MON): (98.0, 100.0), ("AAA", TUE): (102.0, 101.0),
                    ("AAA", WED): (104.0, 110.0), ("AAA", THU): (108.9, 108.0),
                    ("AAA", FRI): (107.8, 107.0), ("BBB", TUE): (199.0, 200.0),
                    ("BBB", WED): (199.6, 199.0), ("BBB", THU): (198.0, 197.0)})


def test_the_weekly_scorecard_leaves_the_ledger_bytes_unchanged(tmp_path):
    store, _txns = _book(tmp_path)
    ledger = tmp_path / "u1" / "transactions.jsonl"
    before = ledger.read_bytes()
    row = R.weekly_scorecard("u1", SUN, store=store, close_on=lambda d: 100.0, today=SUN,
                             panel_on=BOOK_PANEL, corp_actions=no_actions,
                             stock_series_on=lambda s, d: [])
    assert ledger.read_bytes() == before
    assert len(store.load_executable_prices()) == 3
    again = R.weekly_scorecard("u1", SUN, store=store, close_on=lambda d: 100.0, today=SUN,
                               panel_on=BOOK_PANEL, corp_actions=no_actions,
                               stock_series_on=lambda s, d: [])
    assert again == row and len(store.load_executable_prices()) == 3
    assert ledger.read_bytes() == before


# -- 6. The book at each price, and the line ----------------------------------------------------

def test_the_line_carries_the_book_at_each_price_and_its_n(tmp_path):
    """₹1,00,000 deposited Monday; the last valuation, Thursday, is ₹1,05,000:
    +5.0% at the booked closes, and the Nifty is flat, so the lead is +5.0.

    Next open: AAA's buy pays ₹102, not ₹100 (100 shares, −₹200 of cash);
    BBB's ₹199.60, not ₹200 (50 shares, +₹20); AAA's sale gets ₹108.90, not
    ₹110 (−₹110). −₹290: (1,05,000 − 290 − 1,00,000) / 1,00,000 = +4.71%.
    Open after the run: ₹104 (−₹400), ₹198 (+₹100), ₹107.80 (−₹220): −₹520,
    +4.48%. Buys cost (+2.0% − 0.2%) / 2 = 0.9% more on average; the sale
    brought 1.0% less. No charges were taken from cash (rows written without
    costs), so the costs do not move."""
    store, txns = _book(tmp_path)
    rows = X.refresh(store, txns, panel=BOOK_PANEL, corp_actions=no_actions, today=SUN)
    row = R.build_row(week=R.covered_week(SUN), txns=txns,
                      points=store.load_value_history(limit=100), audit_rows=[],
                      close_on=lambda d: 100.0, holdings=1, computed_at="x",
                      executable_rows=rows)
    ex = row["executable"]
    assert ex["trades"] == 3
    assert ex["paper"]["book_pct"] == 5.0
    assert ex["open_next"]["cash_effect_inr"] == -290.0
    assert ex["open_next"]["book_pct"] == 4.71 and ex["open_next"]["lead_points"] == 4.71
    assert ex["open_as_run"]["cash_effect_inr"] == -520.0
    assert ex["open_as_run"]["book_pct"] == 4.48
    assert ex["open_next"]["buy_gap_pct"] == 0.9 and ex["open_next"]["sell_shortfall_pct"] == 1.0
    line = next(l for l in row["lines"] if l.get("label") == "At prices that could be had")
    assert line["text"] == (
        "the paper book is +4.7% since the start at the next session's open and +4.5% at the "
        "open after the run (+5.0% at the booked closes). At the next open buys cost 0.9% "
        "more on average (2) and sells brought 1.0% less (1). 3 trades.")
    # AAA's round trip: 11,000 / 10,000 = +10.0% booked; 10,890 / 10,200 = +6.76%
    # at the next opens: it loses 3.24 points. One round trip is too few.
    assert ex["round_trips"] == {"closed": 1, "priced": 1, "mean_loss_points": 3.24}
    flag = next(f for f in row["red_flags"] if f["id"] == "paper_prices")
    assert flag["status"] == R.NOT_ENOUGH
    assert flag["sentence"] == ("Paper prices: too few to judge (1 round trip and 3 trades "
                                "priced at the next session's open; the rule needs 30 of each).")
    checks = [l for l in row["lines"] if l["kind"] == "check"]
    assert any(l["text"] == flag["sentence"] for l in checks)
    email = R.render_scorecard_text(row)
    assert "At prices that could be had: the paper book is +4.7%" in "\n".join(email)


def test_a_trade_after_the_last_valuation_counts_on_the_line_but_does_not_move_the_book(
        tmp_path):
    """A fourth trade dated Friday, after Thursday's valuation: BBB sold at
    ₹200, opening ₹190 on Monday 9 Mar (−₹500 at the next open). The
    valuation does not hold it yet, so the book stays at +4.71%; the sale
    is one of the trades and its 5.0% shortfall is in the average:
    (1.0% + 5.0%) / 2 = 3.0%."""
    store, txns = _book(tmp_path)
    late = tx(FRI, "BBB", "SELL", 50, 200.0, run=at(date(2026, 3, 9), 16, 30))
    txns = txns + [late]
    panel = Panel({**BOOK_PANEL.bars, ("BBB", date(2026, 3, 9)): (190.0, 190.0),
                   ("BBB", date(2026, 3, 10)): (190.0, 190.0)})
    rows = X.refresh(store, txns, panel=panel, corp_actions=no_actions,
                     today=date(2026, 3, 15))
    since = R.vs_nifty(store.load_value_history(limit=100), lambda d: 100.0,
                       end=date(2026, 3, 15))
    block = X.scorecard_block(txns, rows, end=date(2026, 3, 15), since_start=since)
    assert block["trades"] == 4 and block["open_next"]["sells"] == 2
    assert block["open_next"]["cash_effect_inr"] == pytest.approx(-290.0)
    assert round(block["open_next"]["book_pct"], 2) == 4.71
    assert block["open_next"]["sell_shortfall_pct"] == pytest.approx(3.0)


def test_charged_costs_follow_the_real_price_at_the_same_rates():
    """At brokerage 1% and nothing else: a BUY of 100 at ₹100 booked and
    ₹102 real pays ₹200 more and ₹102 − ₹100 = ₹2 more brokerage (−₹202);
    a SELL of 100 at ₹110 booked and ₹108 real gets ₹200 less and pays ₹2
    less brokerage (−₹198). A row whose costs were never charged moves by
    the price alone."""
    rates = {"as_of": "2026-01-01", "brokerage_pct": 1.0, "brokerage_max_inr": 0.0,
             "stt_pct": 0.0, "stamp_duty_buy_pct": 0.0, "exchange_fee_pct": 0.0,
             "sebi_fee_pct": 0.0, "gst_pct": 0.0, "dp_charge_inr": 0.0}
    paid = TradeCosts(brokerage=100.0, total=100.0)
    assert X.cash_effect(tx(MON, "A", "BUY", 100, 100.0, costs=paid), 102.0, rates) == -202.0
    assert X.cash_effect(tx(MON, "A", "SELL", 100, 110.0, costs=paid), 108.0, rates) == -198.0
    est = TradeCosts(total=100.0, estimated=True)
    assert X.cash_effect(tx(MON, "A", "BUY", 100, 100.0, costs=est), 102.0, rates) == -200.0
    assert X.cash_effect(tx(MON, "A", "BUY", 100, 100.0), 102.0, rates) == -200.0


def test_a_price_from_after_the_week_is_still_waiting_in_that_weeks_row():
    """Friday 27 Feb's run books Thursday 26 Feb; its as-run open is Monday
    2 Mar's. The row for the week ending Sunday 1 Mar counts it as waiting,
    though the side file has the price now."""
    thu = date(2026, 2, 26)
    t = tx(thu, "AAA", "BUY", 10, 100.0, run=at(date(2026, 2, 27), 16, 30))
    panel = Panel({("AAA", thu): (99.0, 100.0), ("AAA", date(2026, 2, 27)): (101.0, 101.0),
                   ("AAA", MON): (103.0, 103.0)})
    row = X.price_trade(t, panel=panel, corp_actions=no_actions, today=SUN)
    assert X.settled(row)
    block = X.scorecard_block([t], [row], end=date(2026, 3, 1), since_start={})
    assert (block["open_next"]["priced"], block["open_as_run"]["pending"]) == (1, 1)
    assert "1 waiting at the open after the run" in X.line_text(block)


# -- 7. The rule --------------------------------------------------------------------------------

def _trips(n, *, buy_real=100.0, sell_real=100.0, start=date(2025, 6, 2)):
    """n round trips, each BUY 10 at ₹100 and SELL 10 at ₹100, priced at
    the given real opens."""
    txns, rows, d = [], [], start
    for i in range(n):
        sell_day = cal.next_trading_day(d)
        for t, real in ((tx(d, f"S{i}", "BUY", 10, 100.0), buy_real),
                        (tx(sell_day, f"S{i}", "SELL", 10, 100.0), sell_real)):
            txns.append(t)
            p = {"session": cal.next_trading_day(_d(t.date)).isoformat(), "status": X.PRICED,
                 "open": real}
            rows.append({"txn_id": t.txn_id, "open_next": p, "open_as_run": p})
        d = cal.next_trading_day(sell_day)
    return txns, rows


def _d(iso):
    return date.fromisoformat(iso)


def _since(lead, deposits=1_000_000.0, nifty=2.0):
    value = deposits * (1 + (nifty + lead) / 100.0)
    return {"available": True, "to": "2026-03-06", "portfolio_value": value,
            "deposits": deposits, "nifty_pct": nifty, "portfolio_pct": nifty + lead,
            "gap_points": lead}


@pytest.mark.parametrize("buy_real,sell_real,status", [
    (100.6, 100.0, R.FIRED),     # 1,000 / 1,006: each trip loses 0.60 points
    (100.4, 100.0, R.CLEAR),     # 1,000 / 1,004: 0.40 points
    (100.0, 99.5, R.CLEAR),      # 995 / 1,000: exactly 0.50 points, not more than 0.5
])
def test_the_round_trip_test_at_30(buy_real, sell_real, status):
    txns, rows = _trips(30, buy_real=buy_real, sell_real=sell_real)
    block = X.scorecard_block(txns, rows, end=SUN, since_start=_since(10.0))
    assert block["round_trips"]["priced"] == 30
    flag = X.rule_flag(block)
    assert flag["tests"]["round_trips"] == status and flag["status"] == status
    if status == R.FIRED:
        assert "Open a card to book trades at the next session's open" in flag["sentence"]
        assert "round trips lose 0.60 points on average" in flag["sentence"]
    else:
        assert flag["sentence"].startswith("Paper prices are close enough: round trips lose")


def test_29_round_trips_are_too_few_whatever_they_lose():
    txns, rows = _trips(29, buy_real=110.0)
    flag = X.rule_flag(X.scorecard_block(txns, rows, end=SUN, since_start=_since(10.0)))
    assert flag["status"] == R.NOT_ENOUGH
    assert "29 round trips and 58 trades" in flag["sentence"]


def test_the_lead_over_the_nifty_changing_sign_fires_the_rule():
    """30 round trips, each buy paying ₹100.40 for ten shares: ₹4 a trip,
    ₹120 in all, on ₹10,00,000 deposited, 0.012 points of the book. A paper
    lead of +0.01 points becomes −0.002: the sign changes at both prices,
    though each trip loses only 0.40 points. A lead of +0.10 keeps its sign."""
    txns, rows = _trips(30, buy_real=100.4)
    flag = X.rule_flag(X.scorecard_block(txns, rows, end=SUN, since_start=_since(0.01)))
    assert flag["tests"] == {"round_trips": R.CLEAR, "open_next": R.FIRED,
                             "open_as_run": R.FIRED}
    assert flag["status"] == R.FIRED
    assert "the lead over the Nifty is +0.0 points at the booked closes" in flag["sentence"]
    flag = X.rule_flag(X.scorecard_block(txns, rows, end=SUN, since_start=_since(0.10)))
    assert flag["status"] == R.CLEAR


def test_a_sign_change_on_fewer_than_30_trades_is_too_few_to_judge():
    """5 round trips (10 trades), each buy ₹4 dearer: ₹20 on ₹10,00,000 is
    0.002 points, so a +0.001-point lead becomes −0.001. The sign changes,
    but the rule needs 30 trades priced before the lead test counts."""
    txns, rows = _trips(5, buy_real=100.4)
    block = X.scorecard_block(txns, rows, end=SUN, since_start=_since(0.001))
    assert block["open_next"]["lead_points"] < 0
    flag = X.rule_flag(block)
    assert flag["tests"]["open_next"] == R.NOT_ENOUGH == flag["status"]
    assert "5 round trips and 10 trades" in flag["sentence"]


def test_without_a_nifty_comparison_the_lead_cannot_be_checked():
    txns, rows = _trips(30, buy_real=100.4)
    flag = X.rule_flag(X.scorecard_block(txns, rows, end=SUN, since_start={
        "available": False, "reason": "no Nifty close for a needed day"}))
    assert flag["status"] == R.UNKNOWN
    assert flag["sentence"] == ("Paper prices: could not check (no Nifty close for a needed "
                                "day).")


# -- 8. The panel seam ---------------------------------------------------------------------------

def test_the_panel_reads_the_days_own_file_its_equity_series_and_the_nse_code(tmp_path,
                                                                              monkeypatch):
    eod = EodStore(base_dir=str(tmp_path))
    base = {"date": "2026-03-03", "prev_close": 1.0, "high": 1.0, "low": 1.0, "volume": 1.0,
            "traded_value_cr": 1.0, "delivery_qty": 1.0, "delivery_pct": 1.0}
    eod.save_day(TUE, pd.DataFrame([
        {**base, "symbol": "ABC", "series": "BE", "open": 10.0, "close": 10.5},
        {**base, "symbol": "ABC", "series": "EQ", "open": 11.0, "close": 11.5},
        {**base, "symbol": "NEWCODE", "series": "EQ", "open": 20.0, "close": 21.0},
        {**base, "symbol": "NAN", "series": "EQ", "open": float("nan"), "close": 5.0},
    ]))
    eod.save_day(WED, pd.DataFrame([{**base, "date": "2026-03-04", "symbol": "ABC",
                                     "series": "EQ", "open": 12.0, "close": 12.5}]))
    from backend.shared.data.fetchers import symbol_resolver
    monkeypatch.setattr(symbol_resolver, "nse_symbol",
                        lambda s, on=None: "NEWCODE" if s == "OLDCODE" else s)
    panel = X.panel_fn(eod)
    assert panel("ABC", TUE) == X.PanelBar(11.0, 11.5, True)
    assert panel("OLDCODE", TUE) == X.PanelBar(20.0, 21.0, True)
    assert panel("NAN", TUE) == X.PanelBar(None, 5.0, True)
    assert panel("XYZ", TUE) == X.PanelBar(None, None, True)
    assert panel("ABC", MON) == X.PanelBar(None, None, False)   # never an earlier day's file
    assert panel("ABC", WED) == X.PanelBar(12.0, 12.5, True)
    assert eod.load_day(MON) is None
