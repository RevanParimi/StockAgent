"""PR-013 — where losses come from and what waiting costs: invariant tests.

Every expected figure is worked out by hand in the comments, never read back
from the implementation. The NSE calendar is pinned (no holidays), so each
session count can be checked by counting weekdays on a calendar. The pace
arithmetic is checked against the real switch gate (`gate_look` through
`scorecard_block`), week by week, not against a copy of its formula.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

import core.intelligence.rl.nse_calendar as cal
from backend.shared.schemas.portfolio import AppliedCorpAction, TradeCosts, TransactionRecord
from core.portfolio import exit_shadow as xs
from core.portfolio import results as R
from core.portfolio.corp_actions import ActionRecord
from core.portfolio.pricing import SessionClose
from core.portfolio.store import PortfolioStore


@pytest.fixture(autouse=True)
def _no_holidays(monkeypatch):
    monkeypatch.setattr(cal, "_NSE_HOLIDAYS", frozenset())


_SEQ = [0]


def _tx(day, sym, side, qty, price, after, user="u1", costs=None, **kw):
    _SEQ[0] += 1
    return TransactionRecord(
        txn_id=f"t{_SEQ[0]}", date=day, ts=f"{day}T10:00:00+00:00", user_id=user,
        symbol=sym, side=side, qty=qty, price=price, value=round(qty * price, 2),
        cash_before=0.0, cash_after=0.0, holding_qty_after=after,
        costs=None if costs is None else TradeCosts(total=costs), **kw)


def buy(day, sym, qty=10, price=100.0, after=None, costs=None, source="autopilot", user="u1"):
    return _tx(day, sym, "BUY", qty, price, qty if after is None else after,
               source=source, user=user, costs=costs)


def sell(day, sym, pnl_pct, *, qty=10, cost=100.0, after=0.0, verdict="EXIT",
         triggers=("thesis_break",), source="autopilot", costs=None, user="u1",
         cost_basis=True):
    price = cost * (1 + pnl_pct / 100.0)
    ref = f"{day}|{sym}|h" if verdict else ""
    return _tx(day, sym, "SELL", qty, price, after, user=user, costs=costs,
               realized_pnl=round((price - cost) * qty, 2),
               cost_basis=cost if cost_basis else None,
               verdict=verdict, triggers=list(triggers), advice_ref=ref, source=source)


def flat_nifty(day):
    return 100.0


W10 = date(2026, 3, 8)          # Sunday; week 2026-W10 is Mon 2 Mar - Sun 8 Mar
# The 13 weeks ending W10 start Monday 8 Dec 2025 (2 Mar minus 12 weeks).


def _row(sunday, txns, **kw):
    return R.build_row(week=R.covered_week(sunday), txns=list(txns), points=[],
                       audit_rows=[], close_on=flat_nifty, holdings=0,
                       computed_at="2026-01-01T00:00:00+00:00", **kw)


def _by(block):
    return {r["label"]: r for r in block["reasons"]}


# -- 1. Closed trades by exit reason ----------------------------------------------------

REVIEW_TRADES = [   # (symbol, result %, verdict, triggers): review section 11's eight results
    ("S1", -13.3, "EXIT", ("stop_breach",)),
    ("S2", -12.4, "EXIT", ("stop_breach",)),
    ("S3", -12.0, "EXIT", ("trailing_stop_breach", "stop_breach")),   # two reasons: stop
    ("S4", -9.9, "EXIT", ("thesis_break",)),
    ("S5", 19.8, "EXIT", ("trailing_stop_breach",)),
    ("S6", 7.6, "EXIT", ("trailing_stop_breach",)),
    ("S7", 2.5, "EXIT", ("case_broken",)),
    ("S8", 0.1, "SWITCH", ("thesis_break", "switch_candidate_available")),
]


def _review_ledger():
    txns = []
    for i, (sym, pnl, verdict, triggers) in enumerate(REVIEW_TRADES):
        txns += [buy("2026-01-05", sym),
                 sell(f"2026-02-{i + 2:02d}", sym, pnl, verdict=verdict, triggers=triggers)]
    return txns


def test_by_reason_matches_the_hand_count():
    """All eight close inside the 13 weeks. In total: 4 wins averaging
    (19.8 + 7.6 + 2.5 + 0.1) / 4 = +7.5, 4 losses averaging
    -(13.3 + 12.4 + 12.0 + 9.9) / 4 = -11.9, -2.2% a trade (the review's).
    Stop: S1, S2 and S3 (S3 also named the trailing stop; the advisor checks
    the stop first): 3 lost, -(13.3 + 12.4 + 12.0) / 3 = -12.5667.
    Trailing stop: S5, S6, 2 won, (19.8 + 7.6) / 2 = +13.7. Price-path exit:
    S4, -9.9. Case broken: S7, +2.5. SWITCH sale: S8, +0.1, though its
    triggers include thesis_break."""
    row = _row(W10, _review_ledger())
    block = row["by_reason"]["last_13_weeks"]
    assert block["from"] == "2025-12-08"
    total = block["all"]
    assert (total["count"], total["wins"], total["losses"]) == (8, 4, 4)
    assert total["avg_win_pct"] == pytest.approx(7.5)
    assert total["avg_loss_pct"] == pytest.approx(-11.9)
    assert total["expectancy_pct"] == pytest.approx(-2.2)
    by = _by(block)
    assert set(by) == {"stop", "trailing stop", "price-path exit", "case broken",
                       "SWITCH sale"}
    stop = by["stop"]
    assert (stop["count"], stop["wins"], stop["losses"]) == (3, 0, 3)
    assert stop["avg_loss_pct"] == pytest.approx(-12.57)    # the row keeps 2 decimals
    assert stop["avg_win_pct"] is None
    assert (by["trailing stop"]["count"], by["trailing stop"]["wins"]) == (2, 2)
    assert by["trailing stop"]["avg_win_pct"] == pytest.approx(13.7)
    assert by["price-path exit"]["expectancy_pct"] == pytest.approx(-9.9)
    assert by["case broken"]["expectancy_pct"] == pytest.approx(2.5)
    assert by["SWITCH sale"]["expectancy_pct"] == pytest.approx(0.1)
    assert block["several_triggers"] == 1      # S3; S8 is a SWITCH, counted under its verdict
    # Every trade under exactly one reason: the counts add up to the total.
    assert sum(r["count"] for r in block["reasons"]) == total["count"]
    # The order: most trades first, then by name.
    assert [r["label"] for r in block["reasons"]] == [
        "stop", "trailing stop", "case broken", "price-path exit", "SWITCH sale"]


def test_by_reason_line_in_plain_words():
    row = _row(W10, _review_ledger())
    line = next(l for l in row["lines"] if l.get("label") == "By exit reason")
    assert line["text"] == (
        "Last 13 weeks: 8 closed trades, -2.2% a trade (4 won, average +7.5%; 4 lost, "
        "average -11.9%). By reason: stop 3, -12.6% a trade (0 won; 3 lost, average -12.6%); "
        "trailing stop 2, +13.7% a trade (2 won, average +13.7%; 0 lost); case broken 1, "
        "+2.5% a trade (1 won, average +2.5%; 0 lost); price-path exit 1, -9.9% a trade "
        "(0 won; 1 lost, average -9.9%); SWITCH sale 1, +0.1% a trade (1 won, average "
        "+0.1%; 0 lost). 1 was sold on more than one reason, counted once, under the first "
        "the advisor checks. Since the start: the same trades. Before costs.")
    text = R.render_scorecard_text(row)
    assert any(t.startswith("By exit reason: Last 13 weeks: 8 closed trades") for t in text)


def test_a_trade_with_no_trigger_is_other_never_dropped_and_each_edge_has_one_reason():
    """E1: an EXIT with no trigger code is "other". E2: your own sale.
    E3: a TRIM (+20% on 5) then an EXIT on the stop (-10% on 5) is ONE trade,
    (100 - 50) / 1000 = +5%, under the stop: the closing sale's reason.
    E4: a TRIM that sold the last share is "TRIM". E5: an EXIT on a code with
    no name here keeps its own words. E6: shock and crisis together: the
    advisor checks the shock first. E7 closed on 1 Dec 2025, before the 13
    weeks: since the start only. E8: a sale with no recorded cost is counted
    under its reason, as unknown, never dropped."""
    txns = [
        buy("2026-01-05", "E1"), sell("2026-02-02", "E1", -3.0, triggers=()),
        buy("2026-01-05", "E2"), sell("2026-02-03", "E2", 4.0, verdict="", triggers=(),
                                      source="manual"),
        buy("2026-01-05", "E3", qty=10),
        sell("2026-02-04", "E3", 20.0, qty=5, after=5.0, verdict="TRIM",
             triggers=("trim_profit_confidence_decline",)),
        sell("2026-02-05", "E3", -10.0, qty=5, after=0.0, triggers=("stop_breach",)),
        buy("2026-01-05", "E4"), sell("2026-02-06", "E4", 6.0, verdict="TRIM",
                                      triggers=("trim_profit_reversion_elevated",)),
        buy("2026-01-05", "E5"), sell("2026-02-09", "E5", -1.0, triggers=("new_rule",)),
        buy("2026-01-05", "E6"), sell("2026-02-10", "E6", -2.0,
                                      triggers=("crisis_regime_bearish", "shock_reforecast")),
        buy("2025-11-03", "E7"), sell("2025-12-01", "E7", -5.0, triggers=("stop_breach",)),
        buy("2026-01-05", "E8"), sell("2026-02-11", "E8", -7.0, cost_basis=False,
                                      triggers=("thesis_break",)),
    ]
    row = _row(W10, txns)
    recent = _by(row["by_reason"]["last_13_weeks"])
    assert {k: v["count"] for k, v in recent.items()} == {
        "other (no reason recorded)": 1, "sold by you": 1, "stop": 1, "TRIM": 1,
        "new rule": 1, "shock": 1, "price-path exit": 1}
    assert recent["stop"]["expectancy_pct"] == pytest.approx(5.0)      # E3, one trade
    assert recent["other (no reason recorded)"]["expectancy_pct"] == pytest.approx(-3.0)
    assert (recent["price-path exit"]["known"], recent["price-path exit"]["unknown"]) == (0, 1)
    assert row["by_reason"]["last_13_weeks"]["all"]["count"] == 7
    since = _by(row["by_reason"]["since_start"])
    assert since["stop"]["count"] == 2                                 # E3 and E7
    assert since["stop"]["expectancy_pct"] == pytest.approx(0.0)       # (5 - 5) / 2
    line = next(l for l in row["lines"] if l.get("label") == "By exit reason")["text"]
    assert "Since the start: 8 closed trades" in line
    assert "price-path exit 1, no recorded cost" in line


def test_property_every_closed_trade_has_exactly_one_reason_whatever_its_trigger_order():
    """Random ledgers: the per-reason counts always add up to the closed
    trades, each trade's reason is one of the named ones, its own code or
    "other", and shuffling a sale's triggers never moves a trade."""
    rng = random.Random(13)
    codes = [c for c, _ in R.EXIT_REASONS] + ["new_rule", "switch_candidate_available"]
    for _ in range(200):
        txns, shuffled = [], []
        for i in range(rng.randint(1, 12)):
            sym = f"R{i}"
            verdict = rng.choice(["EXIT", "EXIT", "SWITCH", "TRIM", ""])
            trig = tuple(rng.sample(codes, rng.randint(0, 3)))
            day = f"2026-02-{rng.randint(2, 27):02d}"
            pnl = rng.uniform(-20, 20)
            kw = dict(verdict=verdict, triggers=trig,
                      source="manual" if not verdict else "autopilot")
            txns += [buy("2026-01-05", sym), sell(day, sym, pnl, **kw)]
            mixed = tuple(rng.sample(trig, len(trig)))
            shuffled += [buy("2026-01-05", sym), sell(day, sym, pnl, **dict(kw, triggers=mixed))]
        trades = R.closed_trades(txns)
        block = R.results_by_reason(trades, None, W10)
        assert sum(r["count"] for r in block["reasons"]) == len(trades)
        names = set(R.REASON_LABELS) | set(codes)
        assert all(R.trade_reason(t) in names for t in trades)
        assert ([R.trade_reason(t) for t in trades]
                == [R.trade_reason(t) for t in R.closed_trades(shuffled)])


# -- 2. Bought back after a sale ---------------------------------------------------------

def test_buy_backs_and_their_charges_from_the_ledger_alone():
    """The 4 weeks ending W10 start Mon 9 Feb 2026.
    A: sold 20 Jan (charges 150), bought 16 Feb (120): a buy-back, 270.
    B: a TRIM leaves shares, then a top-up: not a buy-back.
    C: your own sale 2 Feb (60), bought 3 Feb (40): 100, before the 4 weeks.
    D: rows from before charges were recorded, bought again 2 Mar: no charge.
    A again: sold 3 Mar (90), bought 4 Mar (70): 160.
    Last 4 weeks: A, D, A = 3 in 2 stocks, 270 + 160 = 430, 1 with none.
    Since the start: 4 in 3 stocks, 530, 1 with none."""
    txns = [
        buy("2026-01-05", "A", costs=100.0),
        sell("2026-01-20", "A", 5.0, costs=150.0, triggers=("stop_breach",)),
        buy("2026-02-16", "A", costs=120.0),
        buy("2026-01-05", "B"), sell("2026-02-10", "B", 10.0, qty=5, after=5.0, verdict="TRIM",
                                     triggers=("trim_profit_confidence_decline",)),
        buy("2026-02-12", "B", qty=5, after=10.0),
        buy("2026-01-05", "C"), sell("2026-02-02", "C", 1.0, verdict="", triggers=(),
                                     source="manual", costs=60.0),
        buy("2026-02-03", "C", costs=40.0, source="manual"),
        buy("2026-01-05", "D"), sell("2026-01-06", "D", -1.0),
        buy("2026-03-02", "D", costs=55.0),
        sell("2026-03-03", "A", 2.0, costs=90.0), buy("2026-03-04", "A", costs=70.0),
    ]
    backs = R.buy_backs(txns)
    assert [(b["symbol"], b["sold_on"], b["bought_on"], b["charges"]) for b in backs] == [
        ("C", "2026-02-02", "2026-02-03", 100.0), ("A", "2026-01-20", "2026-02-16", 270.0),
        ("D", "2026-01-06", "2026-03-02", None), ("A", "2026-03-03", "2026-03-04", 160.0)]
    assert backs[0]["sold_by"] == "you"
    row = _row(W10, txns)
    recent, start = row["bought_back"]["last_4_weeks"], row["bought_back"]["since_start"]
    assert (recent["count"], recent["stocks"], recent["charges"], recent["no_charges"]) == (
        3, 2, 430.0, 1)
    assert (start["count"], start["stocks"], start["charges"], start["no_charges"]) == (
        4, 3, 530.0, 1)
    line = next(l for l in row["lines"] if l.get("label") == "Bought back")["text"]
    assert line == ("Last 4 weeks: 3 (2 stocks), ₹430 of charges on those sales and buys back, "
                    "1 with none recorded. Since the start: 4 (3 stocks), ₹530 of charges on "
                    "those sales and buys back, 1 with none recorded. Each is a stock bought "
                    "again after a sale emptied its position.")


def test_no_buy_back_says_so():
    row = _row(W10, _review_ledger())
    line = next(l for l in row["lines"] if l.get("label") == "Bought back")["text"]
    assert line == "No stock has been bought again after a sale emptied its position."


def test_no_closed_trade_says_so():
    row = _row(W10, [buy("2026-01-05", "HELD")])
    line = next(l for l in row["lines"] if l.get("label") == "By exit reason")["text"]
    assert line == "No closed trades yet."


# -- 3. What waiting cost ----------------------------------------------------------------
# Decided Tue 1 Sep 2026. Sessions after it: Sep 2-4 are 1-3, Sep 7-11 4-8,
# Sep 14-18 9-13, Sep 21-25 14-18, Sep 28-30 19-21, Oct 1-2 22-23, Oct 5-9
# 24-28, Oct 12 29, Oct 13 30. So 10 sessions end Tue 15 Sep, 30 Tue 13 Oct.

D1 = date(2026, 9, 1)
D2 = date(2026, 10, 1)          # the second holding of AAA, bought again on 20 Sep
AS_OF = date(2026, 10, 18)      # a Sunday: both horizons of D1 have ended; D2's 30 has not


def _shadow(day, symbol, *, legacy="EXIT", evidence="HOLD", buy_date="2026-08-03",
            disagree=True, close=100.0):
    return {"date": day.isoformat(), "symbol": symbol, "close": close, "mode": "shadow",
            "buy_date": buy_date, "price_bar_date": "",
            "legacy_verdict": legacy, "evidence_verdict": evidence,
            "disagree": disagree, "benchmark": "cash" if disagree else ""}


def _days(start, end):
    d, out = start, []
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def _series(base, special, *, drop=()):
    """A close on every calendar day from 1 Aug to 31 Oct at `base`, except
    `special` days, and none on the `drop` days."""
    closes = {d: base for d in _days(date(2026, 8, 1), date(2026, 10, 31))}
    closes.update(special)
    for d in drop:
        closes.pop(d)
    return closes


SERIES = {
    # D1's close 100; session 7 (10 Sep) 92: -8% within 10; session 25 (6 Oct) 88:
    # -12% within 30. 14 Oct, the 31st session, 80: after the horizon. 31 Aug, before
    # the decision, 50. D2 (1 Oct) closes 100; its 10 sessions (2-15 Oct) hold 6 Oct's
    # 88 and 14 Oct's 80: -20%.
    "AAA": _series(100.0, {date(2026, 9, 10): 92.0, date(2026, 10, 6): 88.0,
                           date(2026, 10, 14): 80.0, date(2026, 8, 31): 50.0}),
    "BBB": _series(210.0, {D1: 200.0}),                      # never below 200: 0
    # 50 on the day; 4 Sep 48.5 (-3%); 9 Oct 45 (-10%).
    "CCC": _series(50.0, {date(2026, 9, 4): 48.5, date(2026, 10, 9): 45.0}),
    "DDD": _series(100.0, {date(2026, 9, 3): 10.0}),         # the evidence rule SOLD it
    "EEE": _series(100.0, {date(2026, 9, 3): 10.0}),         # the rules agreed
    # 3 Sep 95: -5% within 10; a bonus ex 21 Sep falls inside the 30 sessions only.
    "FFF": _series(100.0, {date(2026, 9, 3): 95.0}),
    "GGG": _series(100.0, {}, drop=(date(2026, 9, 8),)),     # no close for session 5
}


def _actions(symbol):
    if symbol == "FFF":
        bonus = AppliedCorpAction(key="FFF|2026-09-21|bonus", ex_date="2026-09-21",
                                  kind="bonus", desc="Bonus 1:1", ratio=2.0,
                                  applied_on="2026-09-21")
        return ActionRecord(actions=(bonus,), covers_from="2000-01-01", rows=3)
    return ActionRecord(covers_from="2000-01-01", rows=3)


def _series_on(asked):
    def lookup(symbol, since):
        asked.append((symbol, since))
        return sorted((d, c) for d, c in SERIES[symbol].items() if d >= since)
    return lookup


def _waiting_rows():
    return [
        _shadow(D1, "AAA"), _shadow(D1 + timedelta(days=1), "AAA"),   # a later day: not counted
        _shadow(D1, "BBB", close=200.0), _shadow(D1, "CCC", close=50.0),
        _shadow(D1, "DDD", legacy="HOLD", evidence="EXIT"),
        _shadow(D1, "EEE", legacy="HOLD", evidence="HOLD", disagree=False),
        _shadow(D1, "FFF"), _shadow(D1, "GGG"),
        _shadow(D2, "AAA", buy_date="2026-09-20"),                   # bought again: its own
    ]


def test_waiting_cost_by_hand(caplog):
    """Kept: AAA (twice: two holdings), BBB, CCC, FFF, GGG = 6. DDD (the
    evidence rule sold it) and EEE (no disagreement) are not kept, and
    AAA's later day is the same decision.
    Within 10 sessions: AAA -8, BBB 0, CCC -3, FFF -5, AAA again -20:
    sorted -20, -8, -5, -3, 0, median -5, worst -20 (AAA); GGG has no close
    for 8 Sep: no result.
    Within 30: AAA -12 (14 Oct's 80 is after the horizon), BBB 0, CCC -10:
    median -10, worst -12 (AAA); FFF's bonus and GGG's gap: no result; AAA
    again ends 12 Nov: pending."""
    import logging
    caplog.set_level(logging.INFO, logger="core.portfolio.exit_shadow")
    asked: list = []
    block = xs.waiting_cost(_waiting_rows(), as_of=AS_OF, stock_series=_series_on(asked),
                            corp_actions=_actions)
    assert "GGG 2026-09-01 @10td: no result (no close on 2026-09-08)" in caplog.text
    assert "FFF 2026-09-01 @30td: no result (NSE lists a bonus ex 2026-09-21)" in caplog.text
    assert block["kept"] == 6
    h10, h30 = block["horizons"]
    assert (h10["horizon_td"], h10["graded"], h10["pending"], h10["no_result"]) == (10, 5, 0, 1)
    assert h10["median_fall_pct"] == pytest.approx(-5.0)
    assert (h10["worst_fall_pct"], h10["worst_symbol"]) == (pytest.approx(-20.0), "AAA")
    assert h10["never_below"] == 1 and h10["no_result_symbols"] == ["GGG"]
    assert (h30["graded"], h30["pending"], h30["no_result"]) == (3, 1, 2)
    assert h30["median_fall_pct"] == pytest.approx(-10.0)
    assert (h30["worst_fall_pct"], h30["worst_symbol"]) == (pytest.approx(-12.0), "AAA")
    assert h30["no_result_symbols"] == ["FFF", "GGG"]
    # Each stock's series is read once, from its first decision's close.
    assert sorted(asked) == sorted({(s, D1) for s in ("AAA", "BBB", "CCC", "FFF", "GGG")})


def test_waiting_cost_reads_no_close_after_a_horizon_and_shows_a_pending_one():
    """On Mon 12 Oct D1's 30 sessions (13 Oct) have not ended: pending, and
    the 6 Oct low is not shown at 30. On Wed 14 Oct the 30 have ended and the
    14 Oct close of 80 (the 31st session) is still not read: -12, not -20.
    A decision after the look is not counted at all."""
    rows = [_shadow(D1, "AAA"), _shadow(date(2026, 10, 20), "BBB", close=200.0)]
    early = xs.waiting_cost(rows, as_of=date(2026, 10, 12), stock_series=_series_on([]),
                            corp_actions=_actions)
    assert early["kept"] == 1
    assert [(h["graded"], h["pending"]) for h in early["horizons"]] == [(1, 0), (0, 1)]
    late = xs.waiting_cost(rows, as_of=date(2026, 10, 14), stock_series=_series_on([]),
                           corp_actions=_actions)
    assert late["horizons"][1]["worst_fall_pct"] == pytest.approx(-12.0)
    assert late["kept"] == 1


@pytest.mark.parametrize("record, why", [
    (None, "could not be read"),
    (ActionRecord(rows=0), "is empty"),
    (ActionRecord(rows=4), "holds no dated row"),
    (ActionRecord(covers_from="2026-09-15", rows=2), "starts 2026-09-15"),
    (ActionRecord(covers_from="2000-01-01", rows=2, unparsed=("2026-09-03",)),
     "bonus or split ex 2026-09-03"),
    (ActionRecord(covers_from="2000-01-01", rows=2,
                  basis_changes=(("2026-09-03", "demerger"),)), "demerger ex 2026-09-03"),
])
def test_a_price_basis_that_cannot_be_trusted_is_no_result_never_a_fall(record, why, caplog):
    """A demerger read as a price would be a 40% "fall"; a list that cannot
    rule one out gives no result either, and the log says why."""
    import logging
    caplog.set_level(logging.INFO, logger="core.portfolio.exit_shadow")
    series = {d: 100.0 for d in _days(date(2026, 8, 1), date(2026, 10, 31))}
    series.update({date(2026, 9, 3): 60.0})
    block = xs.waiting_cost([_shadow(D1, "XXX")], as_of=AS_OF,
                            stock_series=lambda s, since: sorted(series.items()),
                            corp_actions=lambda s: record)
    assert [(h["graded"], h["no_result"]) for h in block["horizons"]] == [(0, 1), (0, 1)]
    assert why in caplog.text


def test_a_failed_series_is_no_result():
    def boom(symbol, since):
        raise RuntimeError("Yahoo down")
    block = xs.waiting_cost([_shadow(D1, "AAA")], as_of=AS_OF, stock_series=boom,
                            corp_actions=_actions)
    assert [(h["graded"], h["no_result"]) for h in block["horizons"]] == [(0, 1), (0, 1)]
    empty = xs.waiting_cost([_shadow(D1, "AAA")], as_of=AS_OF, stock_series=None,
                            corp_actions=_actions)
    assert [h["no_result"] for h in empty["horizons"]] == [1, 1]


def test_waiting_line_in_plain_words():
    week = R.covered_week(AS_OF)
    row = R.build_row(week=week, txns=[], points=[], audit_rows=[], close_on=flat_nifty,
                      holdings=0, computed_at="2026-01-01T00:00:00+00:00",
                      exit_shadow_rows=_waiting_rows(), corp_actions=_actions,
                      stock_quote_on=lambda s, d: SessionClose(100.0, d, "nse"),
                      stock_series_on=_series_on([]))
    line = next(l for l in row["lines"] if l.get("label") == "What waiting cost")["text"]
    assert line == (
        "The evidence rule kept 6 holdings the price-path rule sold. Their lowest close after "
        "the decision, against its close: within 10 sessions, median -5.0% and worst -20.0% "
        "(AAA), over 5; within 30 sessions, median -10.0% and worst -12.0% (AAA), over 3. "
        "1 with no result at 10 sessions (a close missing or a corporate action: GGG); "
        "1 short of 30 sessions; 2 with no result at 30 sessions (a close missing or a "
        "corporate action: FFF, GGG).")
    labels = [l.get("label") for l in row["lines"]]
    assert labels.index("Exit rule test") < labels.index("What waiting cost") \
        < labels.index("Decision pace")


def test_no_kept_decision_says_so_and_no_shadow_row_shows_no_line():
    rows = [_shadow(D1, "DDD", legacy="HOLD", evidence="EXIT")]
    row = R.build_row(week=R.covered_week(AS_OF), txns=[], points=[], audit_rows=[],
                      close_on=flat_nifty, holdings=0, exit_shadow_rows=rows,
                      corp_actions=_actions,
                      stock_quote_on=lambda s, d: SessionClose(100.0, d, "nse"),
                      stock_series_on=_series_on([]))
    line = next(l for l in row["lines"] if l.get("label") == "What waiting cost")["text"]
    assert line == ("No decision yet in which the evidence rule kept a stock the price-path "
                    "rule sold.")
    bare = R.build_row(week=R.covered_week(AS_OF), txns=[], points=[], audit_rows=[],
                       close_on=flat_nifty, holdings=0, exit_shadow_rows=[])
    assert not {"What waiting cost", "Decision pace"} & {l.get("label") for l in bare["lines"]}


# -- 4. The decision pace ----------------------------------------------------------------

def test_pace_by_hand_when_the_count_binds():
    """The look on Sun 29 Nov 2026 (week Mon 23 - Sun 29 Nov); the 4 weeks run
    from Mon 2 Nov. Decisions on 2 Oct, 15 Oct, 4, 11, 18 and 25 Nov: 4 in the
    4 weeks, 1 a week. 9 more are needed for 15: the 9th comes 63 days after
    29 Nov, on Sun 31 Jan 2027, 121 days after the first (>= 56). Its 30th
    session: Feb 1-5, 8-12, 15-19, 22-26, Mar 1-5, 8-12 -> Fri 12 Mar 2027,
    in the week of Mon 8 Mar. Two passing looks in a row: the week of 15 Mar."""
    days = [date(2026, 10, 2), date(2026, 10, 15), date(2026, 11, 4), date(2026, 11, 11),
            date(2026, 11, 18), date(2026, 11, 25)]
    rows = [_shadow(d, f"P{i}") for i, d in enumerate(days)]
    pace = xs.gate_pace(rows, week_monday=date(2026, 11, 23), as_of=date(2026, 11, 29))
    assert (pace["recent"], pace["per_week"], pace["decisions"]) == (4, 1.0, 6)
    assert (pace["first_pass_week"], pace["recommend_week"]) == ("2027-03-08", "2027-03-15")
    assert pace["already"] is False
    assert R._pace_line(pace) == (
        "1 decision a week over the last 4 weeks (4); 6 in all since 2 Oct. At this pace the "
        "gate can first pass in the week of 8 Mar 2027, and two weeks running in the week of "
        "15 Mar 2027 (arithmetic, not a forecast).")


def test_pace_by_hand_when_the_eight_week_span_binds():
    """20 decisions, two on each weekday 16-27 Nov 2026: 5 a week. The 15th
    to the 20th are within 11 days of the first, short of 56. A later one
    must come on or after 11 Jan 2027 (16 Nov + 56): the m-th later one comes
    ceil(7m / 5) days after 29 Nov; m = 30 gives 42 days (10 Jan), m = 31
    gives 44 (Tue 12 Jan 2027). Its 30th session: Jan 13-15, 18-22, 25-29,
    Feb 1-5, 8-12, 15-19, 22, 23 -> Tue 23 Feb, the week of Mon 22 Feb."""
    weekdays = [d for d in _days(date(2026, 11, 16), date(2026, 11, 27)) if d.weekday() < 5]
    rows = [_shadow(d, f"Q{i}{j}") for i, d in enumerate(weekdays) for j in range(2)]
    pace = xs.gate_pace(rows, week_monday=date(2026, 11, 23), as_of=date(2026, 11, 29))
    assert (pace["recent"], pace["per_week"]) == (20, 5.0)
    assert (pace["first_pass_week"], pace["recommend_week"]) == ("2027-02-22", "2027-03-01")


def test_pace_rounds_a_later_decision_up_to_a_whole_day():
    """12 decisions: 1 Sep, 13 Nov and the ten weekdays 16-27 Nov; 11 in the 4
    weeks from 2 Nov, 2.75 a week. The 15th is the 3rd later one: 7 x 3 / 2.75
    = 7.6 days, so the 8th day, Mon 7 Dec (not Sun 6 Dec). Its 30th session:
    Dec 8-11, 14-18, 21-25, 28 Dec-1 Jan, Jan 4-8, 11-15, Mon 18 Jan 2027.
    From Sun 6 Dec it would be Fri 15 Jan, a week earlier."""
    days = ([date(2026, 9, 1), date(2026, 11, 13)]
            + [d for d in _days(date(2026, 11, 16), date(2026, 11, 27)) if d.weekday() < 5])
    rows = [_shadow(d, f"C{i}") for i, d in enumerate(days)]
    pace = xs.gate_pace(rows, week_monday=date(2026, 11, 23), as_of=date(2026, 11, 29))
    assert (pace["recent"], pace["per_week"], pace["decisions"]) == (11, 2.75, 12)
    assert (pace["first_pass_week"], pace["recommend_week"]) == ("2027-01-18", "2027-01-25")


def test_pace_with_no_recent_decision_gives_no_date_and_counts_one_per_holding():
    rows = [_shadow(date(2026, 9, 1), "OLD"), _shadow(date(2026, 9, 2), "OLD"),
            _shadow(date(2026, 9, 3), "OLD", disagree=False, legacy="HOLD")]
    pace = xs.gate_pace(rows, week_monday=date(2026, 11, 23), as_of=date(2026, 11, 29))
    assert (pace["recent"], pace["decisions"], pace["first_pass_week"]) == (0, 1, None)
    assert R._pace_line(pace).endswith("No decision in the last 4 weeks, so no date can be "
                                       "given.")
    nothing = xs.gate_pace([], week_monday=date(2026, 11, 23), as_of=date(2026, 11, 29))
    assert (nothing["decisions"], nothing["first"], nothing["first_pass_week"]) == (0, None, None)


def _passing_quote(symbol, day):
    return SessionClose(105.0, day, "nse")       # kept and rose 5% against cash: right, +5


def _no_actions(symbol):
    return ActionRecord(covers_from="2000-01-01", rows=1)


def _gate_weeks(rows, first_sunday, last_sunday):
    """The real gate, Sunday by Sunday: the first week it passes and the first
    week it recommends (two passing looks in a row)."""
    first_pass = first_rec = None
    previous = None
    sunday = first_sunday
    while sunday <= last_sunday and first_rec is None:
        block = xs.scorecard_block(rows, as_of=sunday, stock_quote_on=_passing_quote,
                                   bench_close_on=flat_nifty, corp_actions=_no_actions,
                                   previous_look=previous)
        if block["gate"]["status"] == xs.PASS and first_pass is None:
            first_pass = sunday - timedelta(days=6)
        if block["recommend"]:
            first_rec = sunday - timedelta(days=6)
        previous = block["gate"]
        sunday += timedelta(weeks=1)
    return first_pass, first_rec


def test_property_the_pace_arithmetic_matches_the_real_gate():
    """Random sets of 15 to 22 decisions, every one right and +5, so only the
    count, the span and the maturity can hold the gate back. Read on the
    Sunday of the last decision's week, the arithmetic's first passing week
    and first recommending week are the weeks the real gate first passes and
    first recommends."""
    rng = random.Random(2026)
    weekdays = [d for d in _days(date(2026, 6, 1), date(2026, 10, 30)) if d.weekday() < 5]
    checked = 0
    while checked < 25:
        n = rng.randint(15, 22)
        days = sorted(rng.sample(weekdays[: rng.randint(60, len(weekdays))], n))
        if (days[-1] - days[0]).days < xs.GATE_MIN_SPAN_DAYS:
            continue
        rows = [_shadow(d, f"G{i}") for i, d in enumerate(days)]
        week = R.week_of(days[-1])
        pace = xs.gate_pace(rows, week_monday=week.monday, as_of=week.sunday)
        first_pass, first_rec = _gate_weeks(rows, week.sunday, week.sunday + timedelta(weeks=12))
        assert pace["first_pass_week"] == first_pass.isoformat(), days
        assert pace["recommend_week"] == first_rec.isoformat(), days
        checked += 1


def test_pace_says_already_once_the_gate_has_its_decisions():
    days = [date(2026, 6, 1) + timedelta(days=4 * i) for i in range(16)]   # 1 Jun - 30 Jul
    rows = [_shadow(d, f"A{i}") for i, d in enumerate(days)]
    pace = xs.gate_pace(rows, week_monday=date(2026, 11, 23), as_of=date(2026, 11, 29))
    assert pace["already"] is True
    assert R._pace_line(pace).endswith("The gate already has the decisions it needs to judge.")


# -- 5. Whose trades, and what the lines change ------------------------------------------

def test_a_member_sees_only_their_own_round_trips_and_the_lines_write_only_the_scorecard(tmp_path):
    """The owner's ledger has a stop-loss trade and a buy-back; the member's
    has one trade sold by hand. Each scorecard counts its own only, and
    building it changes no ledger: the only files that change are the
    scorecard's own and, since PR-016, the executable-price side file."""
    owner = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    for t in (buy("2026-01-05", "OWN", costs=10.0, user="primary"),
              sell("2026-02-02", "OWN", -8.0, triggers=("stop_breach",), costs=12.0,
                   user="primary"),
              buy("2026-02-16", "OWN", costs=11.0, user="primary")):
        owner.append_transaction(t)
    member = PortfolioStore(user_id="member", base_dir=str(tmp_path))
    for t in (buy("2026-01-05", "MEM", user="member"),
              sell("2026-02-03", "MEM", 3.0, verdict="", triggers=(), source="manual",
                   user="member")):
        member.append_transaction(t)

    def snapshot():
        return {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*")
                if p.is_file()}
    before = snapshot()
    theirs = R.weekly_scorecard("primary", W10, store=owner, close_on=flat_nifty,
                                today=W10, stock_series_on=lambda s, d: [])
    mine = R.weekly_scorecard("member", W10, store=member, close_on=flat_nifty,
                              today=W10, stock_series_on=lambda s, d: [])
    assert {r["label"] for r in theirs["by_reason"]["since_start"]["reasons"]} == {"stop"}
    assert theirs["bought_back"]["since_start"]["count"] == 1
    assert {r["label"] for r in mine["by_reason"]["since_start"]["reasons"]} == {"sold by you"}
    assert mine["bought_back"]["since_start"]["count"] == 0
    after = snapshot()
    changed = {p for p in after if before.get(p) != after[p]}
    assert changed and all(p.name.startswith(("weekly_scorecard.", "executable_prices."))
                           for p in changed)
    assert all(before[p] == after[p] for p in before)
