"""PR-002 — the weekly results scorecard: invariant tests.

Every expected figure is worked out by hand in the comments, never read back
from the implementation. The NSE calendar is pinned per test (no holidays
unless a test names one), so each session count can be checked by counting
weekdays on a calendar.
"""
from __future__ import annotations

import json
import random
import threading
from datetime import date, timedelta

import pytest

import core.intelligence.rl.nse_calendar as cal
from backend.shared.schemas.audit import AuditOutcome
from backend.shared.schemas.portfolio import Holding, TransactionRecord
from core.audit.store import AuditOutcomeStore
from core.portfolio import results as R
from core.portfolio.store import PortfolioStore


@pytest.fixture(autouse=True)
def _no_holidays(monkeypatch):
    monkeypatch.setattr(cal, "_NSE_HOLIDAYS", frozenset())


_SEQ = [0]


def _tx(day, sym, side, qty, price, after, user="u1", **kw):
    _SEQ[0] += 1
    return TransactionRecord(
        txn_id=f"t{_SEQ[0]}", date=day, ts=f"{day}T10:00:00+00:00", user_id=user,
        symbol=sym, side=side, qty=qty, price=price, value=round(qty * price, 2),
        cash_before=0.0, cash_after=0.0, holding_qty_after=after, **kw)


def buy(day, sym, qty=10, price=100.0, after=None, source="autopilot", user="u1"):
    return _tx(day, sym, "BUY", qty, price, qty if after is None else after,
               source=source, user=user)


def sell(day, sym, pnl_pct, *, qty=10, cost=100.0, after=0.0, verdict="EXIT",
         triggers=("thesis_break",), ref=None, source="autopilot", user="u1"):
    price = cost * (1 + pnl_pct / 100.0)
    if ref is None:
        ref = f"{day}|{sym}|h" if verdict else ""
    return _tx(day, sym, "SELL", qty, price, after, user=user,
               realized_pnl=round((price - cost) * qty, 2), cost_basis=cost,
               verdict=verdict, triggers=list(triggers), advice_ref=ref, source=source)


def manual_sell(day, sym, pnl_pct, **kw):
    return sell(day, sym, pnl_pct, verdict="", triggers=(), source="manual", **kw)


def grade(ref, horizon, excess, *, lane="advice", user="u1"):
    issued, sym = ref.split("|")[:2]
    return AuditOutcome(
        ref=ref, lane=lane, user_id=user, symbol=sym, verdict="EXIT", issued_on=issued,
        horizon_td=horizon, graded_on=issued, entry_close=100.0, exit_close=100.0,
        return_pct=0.0, bench_entry=1.0, bench_exit=1.0, bench_pct=0.0,
        excess_pct=excess, correct=excess < 0, graded_at="2026-01-01T00:00:00+00:00")


def point(day, equity, capital, market_value=None):
    return {"date": day, "total_equity": equity, "capital_in": capital,
            "cash": equity - (market_value or 0.0),
            "market_value": equity if market_value is None else market_value}


def flat_nifty(day):
    return 100.0


def row_for(sunday, *, txns=(), points=(), audit_rows=(), close_on=flat_nifty,
            holdings=0):
    return R.build_row(week=R.covered_week(sunday), txns=list(txns),
                       points=list(points), audit_rows=list(audit_rows),
                       close_on=close_on, holdings=holdings,
                       computed_at="2026-01-01T00:00:00+00:00")


def flag(row, flag_id):
    return next(f for f in row["red_flags"] if f["id"] == flag_id)


W10 = date(2026, 3, 8)          # Sunday; week 2026-W10 is Mon 2 Mar - Sun 8 Mar


# -- the week a scorecard covers ------------------------------------------------

@pytest.mark.parametrize("on, key", [
    (date(2026, 3, 8), "2026-W10"),    # Sunday: its own week (Mon-Fri sessions are over)
    (date(2026, 3, 7), "2026-W10"),    # Saturday: the same
    (date(2026, 3, 9), "2026-W10"),    # Monday: the week before, never half a week
    (date(2026, 3, 13), "2026-W10"),   # Friday: still the week before
    (date(2026, 3, 14), "2026-W11"),
    (date(2027, 1, 3), "2026-W53"),    # 2026 has 53 ISO weeks (1 Jan 2026 is a Thursday)
])
def test_covered_week(on, key):
    assert R.covered_week(on).key == key


# -- closed trades ------------------------------------------------------------------

REVIEW_SALES = [7.6, 2.5, -9.9, -13.3, -12.4, -12.0, 0.1, 19.8]   # review section 11


def test_closed_trades_match_the_reviews_hand_figures():
    """Review section 11: 4 wins averaging +7.5%, 4 losses averaging -11.9%,
    so expectancy is 0.5 x 7.5 - 0.5 x 11.9 = -2.2% per trade."""
    txns = []
    for i, pnl in enumerate(REVIEW_SALES):
        sym = f"S{i}"
        txns += [buy("2026-01-05", sym), sell("2026-02-0%d" % (i % 5 + 2), sym, pnl)]
    s = R.trade_stats(R.closed_trades(txns))
    assert (s["count"], s["known"], s["wins"], s["losses"]) == (8, 8, 4, 4)
    assert s["win_rate_pct"] == pytest.approx(50.0)
    assert s["avg_win_pct"] == pytest.approx(7.5)        # (7.6+2.5+0.1+19.8)/4
    assert s["avg_loss_pct"] == pytest.approx(-11.9)     # -(9.9+13.3+12.4+12.0)/4
    assert s["expectancy_pct"] == pytest.approx(-2.2)
    assert s["basis"] == "before costs"


def test_an_open_position_is_never_a_closed_trade():
    """A TRIM leaves the position open: it is not a trade yet, even though the
    TRIM alone made +20%. When the rest is sold at -10%, the ONE trade is
    (5 x 20 - 5 x 10) / (10 x 100) = +5%."""
    txns = [buy("2026-03-02", "OPEN", qty=10, price=100.0),
            sell("2026-03-03", "OPEN", 20.0, qty=5, after=5.0, verdict="TRIM")]
    assert R.closed_trades(txns) == []
    assert R.trade_stats(R.closed_trades(txns))["count"] == 0
    txns.append(sell("2026-03-05", "OPEN", -10.0, qty=5, after=0.0))
    [trade] = R.closed_trades(txns)
    assert trade.pnl_pct == pytest.approx(5.0)
    assert (trade.opened, trade.closed) == (date(2026, 3, 2), date(2026, 3, 5))


def test_a_rebought_stock_is_a_new_trade():
    txns = [buy("2026-03-02", "AGAIN"), sell("2026-03-03", "AGAIN", 10.0),
            buy("2026-03-04", "AGAIN"), sell("2026-03-05", "AGAIN", -4.0)]
    trades = R.closed_trades(txns)
    assert [round(t.pnl_pct, 6) for t in trades] == [10.0, -4.0]
    assert trades[1].opened == date(2026, 3, 4)


def test_a_sale_with_no_recorded_cost_is_counted_not_guessed():
    old = _tx("2026-03-03", "OLD", "SELL", 4, 50.0, 0.0, realized_pnl=0.0,
              verdict="EXIT", advice_ref="2026-03-03|OLD|h", source="autopilot")
    s = R.trade_stats(R.closed_trades([old, buy("2026-03-02", "NEW"),
                                       sell("2026-03-04", "NEW", 6.0)]))
    assert (s["count"], s["known"], s["unknown"]) == (2, 1, 1)
    assert s["expectancy_pct"] == pytest.approx(6.0)
    text = R._trades_line("Since the start", s)
    assert "1 earlier trade with no recorded cost not counted" in text


def _random_ledger(rng):
    """Random BUY / ADD / TRIM / EXIT sequences over four symbols, some sales
    without a cost basis. Returns (txns, closed segments recomputed directly)."""
    txns, qty, segs, current = [], {}, [], {}
    day = date(2026, 1, 5)
    for _ in range(rng.randint(1, 40)):
        day += timedelta(days=1)
        sym = rng.choice("ABCD")
        held = qty.get(sym, 0)
        if held == 0 or rng.random() < 0.25:
            n = rng.randint(1, 20)
            qty[sym] = held + n
            txns.append(buy(day.isoformat(), sym, qty=n, after=held + n))
            current.setdefault(sym, [])
            continue
        n = held if rng.random() < 0.5 else rng.randint(1, held)
        cost = rng.choice([None, round(rng.uniform(50, 150), 2)])
        realized = round(rng.uniform(-500, 500), 2)
        qty[sym] = held - n
        t = _tx(day.isoformat(), sym, "SELL", n, 100.0, float(held - n),
                realized_pnl=realized, cost_basis=cost, verdict="EXIT",
                advice_ref=f"{day}|{sym}|{len(txns)}", source="autopilot")
        txns.append(t)
        current[sym].append(t)
        if qty[sym] == 0:
            segs.append((sym, current.pop(sym)))
    return txns, segs, current


@pytest.mark.parametrize("seed", range(300))
def test_trade_stats_agree_with_a_direct_recomputation(seed):
    rng = random.Random(seed)
    txns, segs, still_open = _random_ledger(rng)
    trades = R.closed_trades(txns)
    s = R.trade_stats(trades)

    # one trade per fully sold position, in closing order
    assert [t.symbol for t in trades] == [sym for sym, _ in segs]
    expected = []
    for _, sales_ in segs:
        if all(t.cost_basis for t in sales_):
            expected.append(sum(t.realized_pnl for t in sales_)
                            / sum(t.cost_basis * t.qty for t in sales_) * 100)
        else:
            expected.append(None)
    assert [t.pnl_pct for t in trades] == pytest.approx(expected)

    known = [p for p in expected if p is not None]
    assert s["count"] == len(segs) and s["known"] == len(known)
    assert s["wins"] == sum(p > 0 for p in known)
    assert s["wins"] + s["losses"] == s["known"]
    if known:
        assert s["expectancy_pct"] == pytest.approx(sum(known) / len(known))
        assert s["win_rate_pct"] == pytest.approx(s["wins"] / len(known) * 100)
        # the card's own formula: win rate x average win - loss rate x average loss
        rate = s["wins"] / len(known)
        card = (rate * (s["avg_win_pct"] or 0.0)
                - (1 - rate) * -(s["avg_loss_pct"] or 0.0))
        assert s["expectancy_pct"] == pytest.approx(card)
    else:
        assert s["expectancy_pct"] is None

    # no realized rupee is lost or counted twice: closed trades plus the
    # sales of positions still open add up to every sale in the ledger
    open_realized = sum(t.realized_pnl for ts in still_open.values() for t in ts)
    assert sum(t.realized for t in trades) + open_realized == pytest.approx(
        sum(t.realized_pnl for t in txns if t.side == "SELL"))


# -- sold too early ---------------------------------------------------------------

def _five_sales():
    """S1-S5 on Mondays; 10 sessions = 2 weeks, 30 sessions = 6 weeks later.

    S1 5 Jan  : 10s matures 19 Jan (+2.0 beat), 30s 16 Feb (+5.0 beat)
    S2 12 Jan : 10s 26 Jan (-1.0),               30s 23 Feb (+3.0 beat)
    S3 19 Jan : 10s 2 Feb  (-2.0),               30s 2 Mar  (-4.0)
    S4 2 Feb  : 10s 16 Feb (+1.0 beat),          30s 16 Mar: PENDING on 8 Mar,
                although a +9.0 grade sits in the store already
    S5 9 Feb  : 10s 23 Feb, no grade (ungraded), 30s 23 Mar: pending
    A manual sale on 7 Jan is not the advisor's and is never graded.
    """
    days = ["2026-01-05", "2026-01-12", "2026-01-19", "2026-02-02", "2026-02-09"]
    verdicts = ["EXIT", "EXIT", "SWITCH", "TRIM", "EXIT"]
    txns, refs = [], []
    for i, (d, v) in enumerate(zip(days, verdicts), start=1):
        txns.append(buy("2025-12-01", f"S{i}"))
        txns.append(sell(d, f"S{i}", 1.0, verdict=v,
                         after=5.0 if v == "TRIM" else 0.0, qty=10 if v != "TRIM" else 5))
        refs.append(f"{d}|S{i}|h")
    txns += [buy("2025-12-01", "MAN"), manual_sell("2026-01-07", "MAN", 3.0)]
    grades = [grade(refs[0], 10, 2.0), grade(refs[0], 30, 5.0),
              grade(refs[1], 10, -1.0), grade(refs[1], 30, 3.0),
              grade(refs[2], 10, -2.0), grade(refs[2], 30, -4.0),
              grade(refs[3], 10, 1.0), grade(refs[3], 30, 9.0),     # 30s: from the future
              grade("2026-01-07|MAN|", 10, 50.0)]                    # no such advisor sale
    return txns, grades


def test_sold_too_early_by_horizon_with_pending_and_ungraded():
    txns, grades = _five_sales()
    row = row_for(W10, txns=txns, audit_rows=grades)       # nothing is held
    by_h = {r["horizon_td"]: r for r in row["sold_too_early"]["since_start"]}
    assert {k: by_h[10][k] for k in ("sales", "graded", "beat", "ungraded", "pending")} \
        == {"sales": 5, "graded": 4, "beat": 2, "ungraded": 1, "pending": 0}
    assert by_h[10]["share_pct"] == 50.0
    # S4's +9.0 matures on 16 Mar: pending, never a win, whatever the store holds
    assert {k: by_h[30][k] for k in ("sales", "graded", "beat", "ungraded", "pending")} \
        == {"sales": 5, "graded": 3, "beat": 2, "ungraded": 0, "pending": 2}
    assert by_h[30]["share_pct"] == pytest.approx(66.67)
    line = next(l for l in row["lines"] if l.get("label") == "Sold too early")["text"]
    assert "at 30 sessions 2 of 3 (67%)" in line and "at 10 sessions 2 of 4 (50%)" in line
    assert "2 still short of 30 sessions" in line
    assert "1 past 10 sessions with no grade" in line


def test_horizons_count_exchange_sessions_not_calendar_days(monkeypatch):
    """Sold Fri 16 Jan. Ten sessions end Fri 30 Jan; with Mon 26 Jan a
    holiday they end Mon 2 Feb, after the week of 26 Jan is over."""
    txns = [buy("2026-01-01", "HOL"), sell("2026-01-16", "HOL", 1.0)]
    grades = [grade("2026-01-16|HOL|h", 10, 4.0)]
    sunday = date(2026, 2, 1)
    plain = row_for(sunday, txns=txns, audit_rows=grades)
    assert plain["sold_too_early"]["since_start"][0]["graded"] == 1
    monkeypatch.setattr(cal, "_NSE_HOLIDAYS", frozenset({date(2026, 1, 26)}))
    held_over = row_for(sunday, txns=txns, audit_rows=grades)
    first = held_over["sold_too_early"]["since_start"][0]
    assert (first["graded"], first["pending"]) == (0, 1)


def _window_sales(results, *, older_beat=True):
    """len(results) sales on consecutive weekdays from Mon 5 Jan; each 30-session
    horizon ends 6 weeks later (16-27 Feb), inside the 8 weeks to 8 Mar
    (12 Jan - 8 Mar). One older sale (24 Nov, horizon ending 5 Jan, before the
    window) beat the Nifty and must not count. `results`: excess or None
    (matured with no grade)."""
    txns, grades = [], []
    day = date(2026, 1, 5)
    for i, ex in enumerate(results):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        sym = f"W{i}"
        txns += [buy("2025-11-03", sym), sell(day.isoformat(), sym, 1.0)]
        if ex is not None:
            grades.append(grade(f"{day.isoformat()}|{sym}|h", 30, ex))
        day += timedelta(days=1)
    txns += [buy("2025-11-03", "OLD"), sell("2025-11-24", "OLD", 1.0)]
    if older_beat:
        grades.append(grade("2025-11-24|OLD|h", 30, 8.0))
    return txns, grades


@pytest.mark.parametrize("results, status", [
    ([1.0] * 7 + [-1.0] * 3, R.FIRED),             # 7 of 10 = 70% > 60%
    ([1.0] * 6 + [-1.0] * 4, R.CLEAR),             # 6 of 10 = 60%: not above
    ([1.0] * 8, R.FIRED),                          # 8 sales, the minimum
    ([1.0] * 7, R.NOT_ENOUGH),                     # 7 sales: one short of 8
    ([1.0] * 4 + [-1.0] * 3 + [None] * 3, R.UNKNOWN),
    ([1.0] * 7 + [-1.0] * 2 + [None], R.FIRED),    # 7 of 10 even if the missing one lost
    ([1.0] * 3 + [-1.0] * 5 + [None] * 2, R.CLEAR),   # 5 of 10 even if both missing beat
])
def test_sold_too_early_flag(results, status):
    txns, grades = _window_sales(results)
    f = flag(row_for(W10, txns=txns, audit_rows=grades), "sold_too_early")
    assert f["status"] == status
    assert f["sales"] == len(results)          # the 24 Nov sale is outside the window


def test_missing_grades_cannot_silence_the_sold_too_early_flag():
    """4 of the 7 graded beat the Nifty (57%), so skipping the 3 ungraded sales
    would read "clear". Counted as beating it, they make 7 of 10 (70%): the
    flag cannot be cleared, and the email says so at the top."""
    txns, grades = _window_sales([1.0] * 4 + [-1.0] * 3 + [None] * 3)
    row = row_for(W10, txns=txns, audit_rows=grades)
    f = flag(row, "sold_too_early")
    assert f["status"] == R.UNKNOWN and f["ungraded"] == 3
    assert "between 40% and 70%" in f["sentence"]
    text = R.render_scorecard_text(row)
    assert text[1].startswith("COULD NOT CHECK: Selling too early")


# -- exit reasons and the thesis_break flag ----------------------------------------

def test_thesis_break_flag_and_window():
    """Window: the 4 weeks to Sun 8 Mar, from Mon 9 Feb."""
    def ledger(n_thesis, n_other, manual=0):
        txns = [buy("2026-01-01", "PRE"),
                sell("2026-02-06", "PRE", 1.0)]             # thesis_break, before the window
        for i in range(n_thesis):
            txns += [buy("2026-01-01", f"T{i}"), sell("2026-02-1%d" % i, f"T{i}", -2.0)]
        for i in range(n_other):
            txns += [buy("2026-01-01", f"O{i}"),
                     sell("2026-02-2%d" % i, f"O{i}", -9.0, triggers=("stop_breach",))]
        for i in range(manual):
            txns += [buy("2026-01-01", f"M{i}"), manual_sell("2026-03-0%d" % (i + 2), f"M{i}", 1.0)]
        return txns

    assert flag(row_for(W10, txns=ledger(3, 1)), "thesis_break")["status"] == R.FIRED   # 75%
    assert flag(row_for(W10, txns=ledger(2, 2)), "thesis_break")["status"] == R.CLEAR   # 50%
    # your own sales do not dilute the advisor's share: still 3 of 4
    f = flag(row_for(W10, txns=ledger(3, 1, manual=2)), "thesis_break")
    assert (f["status"], f["sales"], f["thesis_break"]) == (R.FIRED, 4, 3)
    assert flag(row_for(W10, txns=ledger(0, 0)), "thesis_break")["status"] == R.NOT_ENOUGH

    reasons = row_for(W10, txns=ledger(3, 1, manual=2))["exit_reasons"]["last_4_weeks"]
    assert reasons["sales"] == 6
    assert [(r["label"], r["count"]) for r in reasons["reasons"]] == [
        ("the thesis broke", 3), ("sold by you", 2), ("the stop was breached", 1)]


# -- you vs the Nifty -------------------------------------------------------------

DEPOSIT_POINTS = [point("2026-01-05", 1000.0, 1000.0),     # deposit 1000, Nifty 100
                  point("2026-01-19", 1520.0, 1500.0),     # deposit 500, Nifty 125
                  point("2026-02-06", 1600.0, 1500.0)]     # Nifty 110
DEPOSIT_CLOSES = {date(2026, 1, 5): 100.0, date(2026, 1, 19): 125.0,
                  date(2026, 2, 6): 110.0}


def test_two_deposits_buy_the_nifty_on_their_own_days():
    """1000 at 100 buys 10 units; 500 at 125 buys 4. At 110 the 14 units are
    worth 1540. The portfolio's 1600 on 1500 deposited is +6.67%; the Nifty's
    1540 is +2.67%: 4.0 points ahead."""
    deposits = R.deposits_from_values(DEPOSIT_POINTS)
    assert deposits == [(date(2026, 1, 5), 1000.0), (date(2026, 1, 19), 500.0)]
    assert R.nifty_equivalent(deposits, DEPOSIT_CLOSES.__getitem__,
                              date(2026, 2, 6)) == pytest.approx(1540.0)
    m = R.vs_nifty(DEPOSIT_POINTS, DEPOSIT_CLOSES.__getitem__, end=date(2026, 2, 8))
    assert m["available"] and m["nifty_value"] == pytest.approx(1540.0)
    assert m["portfolio_pct"] == pytest.approx(100 / 15)
    assert m["nifty_pct"] == pytest.approx(40 / 15)
    assert m["gap_points"] == pytest.approx(4.0)


def test_a_deposit_inside_the_period_is_a_flow_not_a_gain():
    """From the 5 Jan point (1000; Nifty 10 units = 1000) to 6 Feb, with the
    500 deposit in between: (1600 - 1000 - 500) / (1000 + 500) = +6.67% and
    (1540 - 1000 - 500) / 1500 = +2.67%. Read as a gain, the deposit would
    have made it +60%."""
    m = R.vs_nifty(DEPOSIT_POINTS, DEPOSIT_CLOSES.__getitem__,
                   end=date(2026, 2, 8), start=date(2026, 1, 12))
    assert m["from"] == "2026-01-05" and m["deposits"] == 500.0
    assert m["portfolio_pct"] == pytest.approx(100 / 15)
    assert m["nifty_pct"] == pytest.approx(40 / 15)


def _cash_only_points():
    # 1000 deposited on Fri 30 Jan and left in cash; Fridays to 6 Mar
    return [point(d, 1000.0, 1000.0, market_value=0.0) for d in
            ("2026-01-30", "2026-02-06", "2026-02-13", "2026-02-20", "2026-02-27",
             "2026-03-06")]


def test_idle_cash_counts_against_the_portfolio():
    """All cash while the Nifty rises 10% from the 6 Feb close: 0% against
    +10% over the 4 weeks from Mon 9 Feb, 10 points behind, so the flag fires."""
    closes = {date(2026, 1, 30): 100.0, date(2026, 2, 6): 100.0,
              date(2026, 2, 27): 105.0, date(2026, 3, 6): 110.0}
    row = row_for(W10, points=_cash_only_points(), close_on=closes.__getitem__)
    window = row["vs_nifty"]["last_4_weeks"]
    assert (window["portfolio_pct"], window["nifty_pct"]) == (0.0, 10.0)
    assert flag(row, "behind_nifty")["status"] == R.FIRED
    assert row["breadth"]["invested_pct"] == 0.0


def test_a_missing_nifty_close_reads_unavailable_never_flat():
    def no_close(d):
        from core.audit.benchmark import BenchmarkUnavailableError
        raise BenchmarkUnavailableError(f"no close on {d}")

    row = row_for(W10, points=_cash_only_points(), close_on=no_close)
    for key in ("week", "last_4_weeks", "since_start"):
        assert row["vs_nifty"][key]["available"] is False
    assert flag(row, "behind_nifty")["status"] == R.UNKNOWN
    text = "\n".join(R.render_scorecard_text(row))
    assert "this week unavailable" in text and "since the start unavailable" in text
    assert "+0.0% against" not in text and "level" not in text
    assert "COULD NOT CHECK: Behind the Nifty" in text


def test_a_week_with_no_valuation_is_not_a_flat_week():
    """The last valuation is Fri 27 Feb; nothing was recorded in W10. The week
    must not compare 27 Feb with itself (0% against 0%)."""
    points = _cash_only_points()[:-1]
    row = row_for(W10, points=points, close_on=flat_nifty)
    assert row["vs_nifty"]["week"]["available"] is False
    assert row["vs_nifty"]["stale"] is True
    assert flag(row, "behind_nifty")["status"] == R.UNKNOWN
    assert "No valuation was recorded this week; the last was on 27 Feb." in \
        next(l for l in row["lines"] if l.get("label") == "You vs the Nifty")["text"]


@pytest.mark.parametrize("gap, status", [(-3.01, R.FIRED), (-3.0, R.CLEAR), (2.0, R.CLEAR)])
def test_behind_the_nifty_boundary(gap, status):
    window = {"available": True, "portfolio_pct": gap, "nifty_pct": 0.0, "gap_points": gap}
    assert R.behind_nifty_flag(window, stale=False)["status"] == status


def test_behind_the_nifty_needs_four_weeks_of_history():
    points = [point("2026-02-20", 1000.0, 1000.0), point("2026-03-06", 900.0, 1000.0)]
    f = flag(row_for(W10, points=points), "behind_nifty")
    assert f["status"] == R.NOT_ENOUGH


# -- holding period ---------------------------------------------------------------

@pytest.mark.parametrize("bought, sessions, status", [
    ("2026-03-03", 9, R.FIRED),     # Tue 3 Mar -> Mon 16 Mar: 4,5,6,9-13,16 = 9 sessions
    ("2026-03-02", 10, R.CLEAR),    # Mon 2 Mar -> Mon 16 Mar: 10 sessions, not under 10
])
def test_holding_period_flag(bought, sessions, status):
    txns = [buy(bought, "HP"), sell("2026-03-16", "HP", 1.0)]
    row = row_for(date(2026, 3, 22), txns=txns)
    assert row["holding_period"]["median_sessions"] == sessions
    assert flag(row, "holding_period")["status"] == status


@pytest.mark.parametrize("known, status", [
    ([12, 14], R.CLEAR),     # with the unknown at 0 sessions the median is still 12
    ([5, 6], R.FIRED),       # with the unknown held for ever the median is still 6
    ([5], R.UNKNOWN),        # 2.5 or for ever: cannot say
])
def test_an_unknown_purchase_date_cannot_silence_the_holding_flag(known, status):
    stats = {"closed": len(known) + 1, "known": len(known), "unknown": 1,
             "median_sessions": None, "sessions": known}
    assert R.holding_period_flag(stats)["status"] == status


# -- expectancy flag --------------------------------------------------------------

@pytest.mark.parametrize("third, status", [
    (4.0, R.FIRED),     # since-start: -10 (22 Feb), -2.5 (1 Mar), -0.33 (8 Mar)
    (5.0, R.CLEAR),     # ... and (-10 + 5 + 5) / 3 = 0.0 on 8 Mar: not below 0
])
def test_expectancy_flag(third, status):
    txns = [buy("2026-01-05", "E1"), sell("2026-02-16", "E1", -10.0),
            buy("2026-01-05", "E2"), sell("2026-02-23", "E2", 5.0),
            buy("2026-01-05", "E3"), sell("2026-03-02", "E3", third)]
    assert flag(row_for(W10, txns=txns), "expectancy")["status"] == status


def test_expectancy_flag_needs_three_week_ends_with_trades():
    txns = [buy("2026-01-05", "E2"), sell("2026-02-23", "E2", -5.0),
            buy("2026-01-05", "E3"), sell("2026-03-02", "E3", -4.0)]
    assert flag(row_for(W10, txns=txns), "expectancy")["status"] == R.NOT_ENOUGH


# -- breadth floor (configured by SA-049) -----------------------------------------

@pytest.mark.parametrize("configured, floor", [(None, None), (10, {"min_holdings": 10}),
                                                ("ten", None)])
def test_the_breadth_floor_is_shown_only_once_configured(monkeypatch, configured, floor):
    import backend.shared.config.settings.loader as loader
    monkeypatch.setattr(loader, "cfg", lambda path, fallback=None, env=None:
                        configured if path == "portfolio.min_holdings" else fallback)
    assert R._floor() == floor
    row = R.build_row(week=R.covered_week(W10), txns=[], points=[point("2026-03-06", 100.0, 100.0)],
                      audit_rows=[], close_on=flat_nifty, holdings=2, floor=R._floor())
    text = next(l for l in row["lines"] if l.get("label") == "Breadth")["text"]
    assert ("Floor: 10 holdings." in text) is (floor is not None)
    assert text.startswith("2 holdings, 100% of the money invested (6 Mar).")


# -- storage: idempotent by week key, per user ------------------------------------

def _seed_user(tmp_path, user="u1", ref_suffix="h"):
    store = PortfolioStore(user_id=user, base_dir=str(tmp_path))
    p = store.load()
    p.holdings = [Holding(symbol="KEEP", sector="it", qty=1, avg_buy_price=10.0,
                          adj_avg_price=10.0, adj_qty=1, buy_date="2026-01-02")]
    p.cash_deployable, p.capital_in = 900.0, 1000.0
    store.save(p)
    for t in (buy("2026-01-02", "AAA", user=user),
              sell("2026-01-05", "AAA", 10.0, user=user,
                   ref=f"2026-01-05|AAA|{ref_suffix}")):
        store.append_transaction(t)
    for pt in (point("2026-01-02", 1000.0, 1000.0), point("2026-03-06", 1010.0, 1000.0)):
        store.append_value_point(pt)
    return store


def test_rerunning_a_week_rewrites_and_appends_nothing(tmp_path):
    store = _seed_user(tmp_path)
    AuditOutcomeStore(user_id="u1", base_dir=str(tmp_path)).append(
        grade("2026-01-05|AAA|h", 30, 5.0))
    first = R.weekly_scorecard("u1", W10, store=store, close_on=flat_nifty,
                               today=date(2026, 3, 8))
    path = tmp_path / "u1" / "weekly_scorecard.jsonl"
    before = path.read_bytes()
    assert before.count(b"\n") == 1 and first["week"] == "2026-W10"
    assert first["breadth"]["holdings"] == 1            # the latest week: holdings known

    # new facts arrive; the stored week does not change
    store.append_transaction(sell("2026-03-04", "KEEP", -50.0, qty=1, cost=10.0))
    AuditOutcomeStore(user_id="u1", base_dir=str(tmp_path)).append(
        grade("2026-01-05|AAA|h", 10, -3.0))
    for on in (W10, date(2026, 3, 7), date(2026, 3, 11)):   # Sun, Sat, a Wednesday after
        again = R.weekly_scorecard("u1", on, store=store, close_on=flat_nifty,
                                   today=date(2026, 3, 11))
        assert again == first
    assert path.read_bytes() == before


def test_an_unfinished_week_is_never_stored(tmp_path):
    store = _seed_user(tmp_path)
    row = R.weekly_scorecard("u1", date(2026, 3, 8), store=store, close_on=flat_nifty,
                             today=date(2026, 3, 6))       # Friday: the week is not over
    assert row["provisional"] is True
    assert store.load_scorecards() == []


def test_concurrent_runs_store_one_row(tmp_path):
    store = _seed_user(tmp_path)
    row = row_for(W10)
    results = []

    def run():
        results.append(PortfolioStore(user_id="u1", base_dir=str(tmp_path))
                       .append_scorecard_once(dict(row))[1])

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False] * 7 + [True]
    assert len(store.load_scorecards()) == 1


def test_a_members_scorecard_reads_only_the_members_ledger(tmp_path):
    """The member's sale carries the very ref the owner's grade is keyed on,
    and the owner is the default user (the auditor's only user today). The
    member's scorecard must still find no grade: it never opens the owner's
    auditor file (the FIX-005 rule: a viewer reads only their own)."""
    owner = _seed_user(tmp_path, user="primary")
    member = PortfolioStore(user_id="member", base_dir=str(tmp_path))
    member.append_transaction(buy("2026-01-02", "MEMCO", user="member"))
    member.append_transaction(sell("2026-01-05", "MEMCO", -4.0, user="member",
                                   ref="2026-01-05|AAA|h"))
    AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path)).append(
        grade("2026-01-05|AAA|h", 30, 5.0, user="primary"))

    mine = R.weekly_scorecard("member", W10, store=member, close_on=flat_nifty,
                              today=date(2026, 3, 8))
    theirs = R.weekly_scorecard("primary", W10, store=owner, close_on=flat_nifty,
                                today=date(2026, 3, 8))
    m30 = mine["sold_too_early"]["since_start"][1]
    o30 = theirs["sold_too_early"]["since_start"][1]
    assert (m30["graded"], m30["ungraded"]) == (0, 1)
    assert (o30["graded"], o30["beat"]) == (1, 1)
    assert mine["closed_trades"]["since_start"]["expectancy_pct"] == -4.0
    assert theirs["closed_trades"]["since_start"]["expectancy_pct"] == 10.0
    assert mine["vs_nifty"]["since_start"]["available"] is False   # no member valuations
    assert len(member.load_scorecards()) == 1 and len(owner.load_scorecards()) == 1


# -- the Sunday weekly review, end to end (transports blocked) ---------------------

@pytest.fixture()
def weekly_env(tmp_path, monkeypatch):
    """The real weekly job for one user. No network: the Nifty is a fixed
    series, delivery is captured, the headline is the deterministic fallback."""
    import core.delivery.weekly as wk
    monkeypatch.setattr(wk.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wk, "active_user_ids", lambda: ["u1"])
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: {})
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    monkeypatch.setattr(wk, "_shelf_by_symbol", lambda: {})
    monkeypatch.setattr(wk, "_safe_weekly_ipos", lambda on: [])
    monkeypatch.setattr(wk, "_narrate_weekly", wk._fallback_headline)
    closes = {date(2026, 1, 30): 100.0, date(2026, 2, 6): 100.0,
              date(2026, 2, 27): 105.0, date(2026, 3, 6): 110.0}
    monkeypatch.setattr(wk, "_benchmark_close_fn", lambda: closes.__getitem__)
    monkeypatch.setattr(R, "_today", lambda: date(2026, 3, 8))
    sent = []
    monkeypatch.setattr(wk, "deliver",
                        lambda title, body, **kw: sent.append(body) or {"delivered": True})
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    for pt in _cash_only_points():                 # idle cash, Nifty +10%: a red flag
        store.append_value_point(pt)
    store.append_transaction(buy("2026-01-05", "SOLD"))
    store.append_transaction(sell("2026-03-03", "SOLD", 12.0,
                                  triggers=("trailing_stop_breach",)))
    return wk, store, sent


def test_the_sunday_review_leads_with_the_scorecard(weekly_env):
    wk, store, sent = weekly_env
    assert wk.run_weekly_review(on=W10) == {"status": "completed", "users": 1,
                                            "date": "2026-03-08"}
    [body] = sent
    lines = body.splitlines()
    assert lines[0] == "Weekly review — 2026-03-08"
    assert lines[1] == "Results for 2 Mar – 6 Mar 2026 (2026-W10)"
    assert lines[2].startswith("RED FLAG: Behind the Nifty: over the last 4 weeks the "
                               "portfolio made +0.0% against +10.0%")
    assert "Closed trades: This week: 1 trade · 1 won (100%)" in body
    assert body.index("RED FLAG") < body.index("1 red flag this week")   # headline after
    assert "judged calls right" not in body                           # the old scoreboard

    saved = store.load_latest_weekly()
    assert saved["scorecard"]["week"] == "2026-W10" and "scoreboard" not in saved
    assert [r["week"] for r in store.load_scorecards()] == ["2026-W10"]

    wk.run_weekly_review(on=W10)                   # the same Sunday again
    assert len(store.load_scorecards()) == 1
    assert sent[1].splitlines()[1:6] == lines[1:6]


def test_a_failed_scorecard_is_said_not_skipped(weekly_env, monkeypatch):
    wk, store, sent = weekly_env

    def boom(*a, **k):
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(wk, "weekly_scorecard", boom)
    wk.run_weekly_review(on=W10)
    assert sent[0].splitlines()[1] == "Results: could not be computed this week."
    assert store.load_latest_weekly()["scorecard"] is None


# -- GET /portfolio/scorecard ------------------------------------------------------

@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from core.config import settings
    from services.data.stores import user_store
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"), raising=False)
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    from services.api.routes.auth_api import router as auth_router
    from services.api.routes.portfolio_api import router as pf_router
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(pf_router)
    return TestClient(app)


def _signup(client):
    owner = client.post("/auth/signup", json={
        "email": "me@x.com", "password": "hunter2longer", "display_name": "O",
        "invite_code": None, "remember_me": True, "consent": True}).json()["token"]
    code = client.post("/auth/invites",
                       headers={"Authorization": f"Bearer {owner}"}).json()["code"]
    member = client.post("/auth/signup", json={
        "email": "f@x.com", "password": "hunter2longer", "display_name": "F",
        "invite_code": code, "remember_me": True, "consent": True}).json()["token"]
    return owner, member


def test_the_endpoint_returns_only_the_callers_rows(auth_client, tmp_path):
    owner_tok, member_tok = _signup(auth_client)
    ids = {}
    for name, tok in (("owner", owner_tok), ("member", member_tok)):
        ids[name] = auth_client.get(
            "/portfolio", headers={"Authorization": f"Bearer {tok}"}).json()["user_id"]
    base = str(tmp_path / "pf")
    for week in ("2026-W09", "2026-W10"):
        PortfolioStore(user_id=ids["owner"], base_dir=base).append_scorecard_once(
            {"week": week, "who": "owner"})
    PortfolioStore(user_id=ids["member"], base_dir=base).append_scorecard_once(
        {"week": "2026-W10", "who": "member"})

    r = auth_client.get("/portfolio/scorecard?user_id=" + ids["owner"],
                        headers={"Authorization": f"Bearer {member_tok}"})
    assert r.status_code == 200
    assert r.json()["rows"] == [{"week": "2026-W10", "who": "member"}]
    r = auth_client.get("/portfolio/scorecard",
                        headers={"Authorization": f"Bearer {owner_tok}"})
    assert [row["week"] for row in r.json()["rows"]] == ["2026-W10", "2026-W09"]
    assert {row["who"] for row in r.json()["rows"]} == {"owner"}


def test_the_endpoint_needs_a_signed_in_user(auth_client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    assert auth_client.get("/portfolio/scorecard").status_code == 401


# -- your own sale is stamped with its cost ----------------------------------------

def test_a_manual_sale_records_its_cost_so_its_result_counts(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import services.api.routes.portfolio_api as papi
    monkeypatch.setattr(papi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(papi, "promote_symbol", lambda *a, **k: {"status": "test"})
    monkeypatch.setattr(papi, "demote_symbol", lambda *a, **k: False)
    monkeypatch.setattr(papi, "close_on", lambda symbol, d: 90.0)
    store = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = store.load()
    p.holdings = [Holding(symbol="MINE", sector="it", qty=10, avg_buy_price=100.0,
                          adj_avg_price=100.0, adj_qty=10, buy_date="2026-03-02")]
    p.cash_deployable, p.capital_in = 0.0, 1000.0
    store.save(p)
    app = FastAPI()
    app.include_router(papi.router)
    r = TestClient(app).delete("/portfolio/holdings/MINE")
    assert r.status_code == 200
    txn = r.json()["transaction"]
    assert (txn["cost_basis"], txn["pnl_pct"], txn["realized_pnl"]) == (100.0, -10.0, -100.0)
    [trade] = R.closed_trades(store.load_transactions())
    assert trade.pnl_pct == pytest.approx(-10.0) and trade.source == "manual"
