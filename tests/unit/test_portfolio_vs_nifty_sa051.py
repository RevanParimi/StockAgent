"""SA-051 — the portfolio against the Nifty, with honest labels: invariant tests.

Every expected figure is worked out by hand in the comments, never read back
from the implementation. The money-weighted rule the card fixes: each deposit
buys Nifty units at its own day's close, idle cash counts against the
portfolio, and a holding that arrives without cash (Add holding with an
earlier buy date or a typed price, a CSV import) is money in at its value on
the day it arrives, not at its cost (PR-002 review, F1). Deposits keep their
own dates however long the value history grows (F2).

The NSE calendar is pinned (no holidays unless a test names one). Clocks are
frozen per step, so an add and a valuation happen in a stated order.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.intelligence.rl.nse_calendar as cal
import services.api.routes.portfolio_api as papi
from backend.shared.schemas.portfolio import Holding, TransactionRecord
from core.audit import benchmark as B
from core.config import settings
from core.portfolio import autopilot, retention
from core.portfolio import results as R
from core.portfolio.reconcile import reconcile
from core.portfolio.store import PortfolioStore, import_csv

IST = timezone(timedelta(hours=5, minutes=30))
W10 = date(2026, 3, 8)        # Sunday; week 2026-W10 is Mon 2 Mar - Sun 8 Mar


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    # The figures here are the comparison's arithmetic before trading costs.
    # SA-048's tests put a manual add's charges into capital_in and the
    # Nifty's money in (test_trading_costs_sa048.py).
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", {
        **settings.PORTFOLIO_COSTS, "brokerage_pct": 0.0, "stt_pct": 0.0,
        "stamp_duty_buy_pct": 0.0, "exchange_fee_pct": 0.0, "sebi_fee_pct": 0.0,
        "dp_charge_inr": 0.0})
    monkeypatch.setattr(cal, "_NSE_HOLIDAYS", frozenset())
    B._range_cache.clear()
    yield
    B._range_cache.clear()


class Clock:
    """One frozen moment for the add route and the value-point writer."""

    def __init__(self, monkeypatch):
        clock = self
        self.now = datetime(2026, 1, 1, tzinfo=IST)

        class FrozenDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.now.astimezone(tz) if tz else clock.now.replace(tzinfo=None)

        monkeypatch.setattr(papi, "datetime", FrozenDT)
        monkeypatch.setattr(autopilot, "_now_iso",
                            lambda: clock.now.astimezone(timezone.utc).isoformat())
        monkeypatch.setattr(autopilot, "_today_ist", lambda: clock.now.astimezone(IST).date())

    def at(self, day: str, hhmm: str) -> None:
        self.now = datetime.fromisoformat(f"{day}T{hhmm}:00+05:30")


class FakeNifty:
    """BenchmarkSeries' surface over a dict of closes; `fail` = the download failed."""

    closes: dict = {}
    fail = False
    preloads: list = []

    def preload(self, start, end):
        FakeNifty.preloads.append((start, end))
        return not FakeNifty.fail

    def close_on(self, d):
        if FakeNifty.fail or d not in FakeNifty.closes:
            raise B.BenchmarkUnavailableError(f"no close on {d}")
        return FakeNifty.closes[d]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(papi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(papi, "promote_symbol", lambda *a, **k: {"status": "test"})
    monkeypatch.setattr(papi, "demote_symbol", lambda *a, **k: False)
    monkeypatch.setattr(papi, "_benchmark", FakeNifty)
    monkeypatch.setattr(papi, "_stock_closes", lambda: STOCK.__getitem__)
    FakeNifty.closes, FakeNifty.fail, FakeNifty.preloads = {}, False, []
    STOCK.clear()
    app = FastAPI()
    app.include_router(papi.router)
    app.dependency_overrides[papi.get_current_user] = lambda: {"user_id": "primary",
                                                               "role": "owner"}
    return TestClient(app)


STOCK: dict = {}       # (symbol, day) -> close, for the arrivals' valuation


def cash_account(tmp_path, cash=1_000_000.0) -> PortfolioStore:
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    p.cash_deployable, p.capital_in, p.autopilot = cash, cash, True
    s.save(p)
    return s


def point(day, equity, capital, market_value=0.0, recorded=True):
    p = {"date": day, "market_value": market_value, "cash": equity - market_value,
         "total_equity": equity, "capital_in": capital}
    if recorded:
        p["recorded_at"] = f"{day}T11:30:00+00:00"       # 17:00 IST
    return p


def _tx(day, sym, side, qty, price, after, **kw):
    return TransactionRecord(
        txn_id=kw.pop("txn_id", f"{day}-{sym}-{side}-{after}"), date=day,
        ts=kw.pop("ts", f"{day}T10:00:00+00:00"), user_id="primary", symbol=sym,
        side=side, qty=qty, price=price, value=round(qty * price, 2),
        cash_before=kw.pop("cash_before", 0.0), cash_after=kw.pop("cash_after", 0.0),
        holding_qty_after=after, **kw)


# -- AC1: two deposits on different days, a hand-built Nifty --------------------

TWO_DEPOSITS = [point("2026-01-05", 1_000_000.0, 1_000_000.0),
                point("2026-01-19", 1_210_000.0, 1_200_000.0),     # +₹2,00,000 in
                point("2026-02-06", 1_240_000.0, 1_200_000.0)]
TWO_CLOSES = {date(2026, 1, 5): 100.0, date(2026, 1, 19): 125.0, date(2026, 2, 6): 110.0}


def test_two_deposits_through_the_performance_endpoint(client, tmp_path):
    """₹10,00,000 on 5 Jan at Nifty 100 buys 10,000 units; ₹2,00,000 on 19 Jan
    at 125 buys 1,600. The line: 10,000 × 100 = ₹10,00,000; 11,600 × 125 =
    ₹14,50,000; 11,600 × 110 = ₹12,76,000 on 6 Feb. Since the start the
    portfolio made (12,40,000 − 12,00,000) / 12,00,000 = +3.33% and the
    Nifty (12,76,000 − 12,00,000) / 12,00,000 = +6.33%: 3.0 points and
    ₹36,000 behind."""
    s = cash_account(tmp_path)
    for p in TWO_DEPOSITS:
        s.append_value_point(p)
    FakeNifty.closes = dict(TWO_CLOSES)
    d = client.get("/portfolio/performance").json()
    assert [h["nifty_value"] for h in d["history"]] == [1_000_000.0, 1_450_000.0, 1_276_000.0]
    v = d["vs_nifty"]
    assert v["available"] is True
    assert (v["portfolio_value"], v["nifty_value"]) == (1_240_000.0, 1_276_000.0)
    assert v["portfolio_pct"] == pytest.approx(3.33, abs=0.005)
    assert v["nifty_pct"] == pytest.approx(6.33, abs=0.005)
    assert v["gap_points"] == pytest.approx(-3.0, abs=0.005)
    assert v["gap_inr"] == pytest.approx(-36_000.0)
    assert v["deposits"] == 1_200_000.0 and v["first_deposit"] == "2026-01-05"
    # one download covers every value point's date
    assert FakeNifty.preloads == [(date(2026, 1, 5), date(2026, 2, 6))]


def test_a_range_counts_a_deposit_as_money_in_not_a_gain():
    """Over the 3 points (5 Jan to 6 Feb) the ₹2,00,000 deposit is a flow:
    (12,40,000 − 10,00,000 − 2,00,000) / 12,00,000 = +3.33%, not the +24% of
    12,40,000 / 10,00,000. Over the last 2 (19 Jan to 6 Feb) no money moved:
    12,40,000 / 12,10,000 − 1 = +2.48%, and the Nifty 110 / 125 − 1 = −12.0%."""
    m = R.portfolio_vs_nifty(TWO_DEPOSITS, [], close_on=TWO_CLOSES.__getitem__,
                             stock_close_on=None, ranges={"three": 3, "two": 2})
    three, two = m["ranges"]["three"], m["ranges"]["two"]
    assert (three["from"], three["deposits"]) == ("2026-01-05", 200_000.0)
    assert three["portfolio_pct"] == pytest.approx(3.33, abs=0.005)
    assert three["nifty_pct"] == pytest.approx(6.33, abs=0.005)
    assert (two["from"], two["deposits"]) == ("2026-01-19", 0)
    assert two["portfolio_pct"] == pytest.approx(2.48, abs=0.005)
    assert two["nifty_pct"] == pytest.approx(-12.0, abs=0.005)


def test_idle_cash_counts_against_the_portfolio_on_the_screen(client, tmp_path):
    """All ₹10,00,000 left in cash while the Nifty goes 100 → 110: the
    portfolio is level at ₹10,00,000 and the same deposit in the Nifty is
    ₹11,00,000, so it is ₹1,00,000 and 10 points behind. Comparing only the
    invested part (nothing) would hide that."""
    s = cash_account(tmp_path)
    s.append_value_point(point("2026-01-05", 1_000_000.0, 1_000_000.0))
    s.append_value_point(point("2026-02-06", 1_000_000.0, 1_000_000.0))
    FakeNifty.closes = {date(2026, 1, 5): 100.0, date(2026, 2, 6): 110.0}
    v = client.get("/portfolio/performance").json()["vs_nifty"]
    assert (v["portfolio_pct"], v["nifty_pct"], v["gap_inr"]) == (0.0, 10.0, -100_000.0)


def test_a_long_history_keeps_the_opening_deposit_on_its_day(client, tmp_path):
    """405 daily points from 5 Jan, ₹10,00,000 in on the first and nothing
    after: the chart gets the last 400, but the comparison reads every point,
    so the deposit is dated 5 Jan (Nifty 100), not the first point sent."""
    s = cash_account(tmp_path)
    day = date(2026, 1, 5)
    for i in range(405):
        s.append_value_point(point(day.isoformat(), 1_000_000.0, 1_000_000.0))
        FakeNifty.closes[day] = 100.0 + i
        day += timedelta(days=1)
    d = client.get("/portfolio/performance").json()
    assert len(d["history"]) == 400
    v = d["vs_nifty"]
    assert v["first_deposit"] == "2026-01-05"
    assert v["nifty_value"] == pytest.approx(10_000 * 504.0)       # 10,000 units × the last close
    assert v["nifty_pct"] == pytest.approx(404.0)


def test_an_unavailable_benchmark_reads_unavailable_with_no_line(client, tmp_path):
    s = cash_account(tmp_path)
    for p in TWO_DEPOSITS:
        s.append_value_point(p)
    FakeNifty.fail = True
    d = client.get("/portfolio/performance").json()
    assert d["vs_nifty"]["available"] is False
    assert "Nifty" in d["vs_nifty"]["reason"]
    assert all(h["nifty_value"] is None for h in d["history"])      # no flat line
    assert d["ranges"] and all(not r["available"] for r in d["ranges"].values())


def test_one_missing_close_leaves_a_gap_never_a_carried_value():
    closes = dict(TWO_CLOSES)
    del closes[date(2026, 1, 19)]          # the deposit day has no close
    line = R.nifty_line(TWO_DEPOSITS, R.capital_flows(TWO_DEPOSITS), closes.__getitem__)
    # 10,000 units on 5 Jan; the 19 Jan deposit cannot buy units, so every
    # later value is unknown rather than 10,000 units carried on.
    assert line == [1_000_000.0, None, None]


# -- F1: a holding that arrives without cash ----------------------------------------

FRIDAYS = ["2026-01-30", "2026-02-06", "2026-02-13", "2026-02-20", "2026-02-27", "2026-03-06"]
NIFTY = {date(2026, 1, 30): 100.0, date(2026, 2, 6): 100.0, date(2026, 2, 13): 102.0,
         date(2026, 2, 20): 105.0, date(2026, 2, 27): 107.0, date(2026, 3, 6): 110.0}


def _backdated_add_timeline(client, tmp_path, monkeypatch, *, add_at: str):
    """₹10 L of idle cash from 30 Jan; on Fri 20 Feb the owner adds 1,000
    ACME through the real route, buy date 3 Feb 2025, priced by the route at
    that day's ₹50. ACME is ₹150 from 20 Feb on. The 17:00 review records a
    value point each Friday through the real writer."""
    clock = Clock(monkeypatch)
    s = cash_account(tmp_path)
    monkeypatch.setattr(papi, "close_on", lambda sym, d: 50.0)

    def add():
        clock.at("2026-02-20", add_at)
        r = client.post("/portfolio/holdings", json={
            "symbol": "ACME", "sector": "pharma", "qty": 1000, "buy_date": "2025-02-03"})
        assert r.status_code == 200 and r.json()["transaction"]["value"] == 50_000.0

    for day in FRIDAYS:
        if day == "2026-02-20" and add_at < "17:00":
            add()
        clock.at(day, "17:00")
        held = {h.symbol: 150.0 for h in s.load().holdings}
        autopilot.record_value_point(s, s.load(), held, date.fromisoformat(day))
        if day == "2026-02-20" and add_at >= "17:00":
            add()
    return s


def _row(store, stock_close_on):
    return R.weekly_scorecard("primary", W10, store=store, close_on=NIFTY.__getitem__,
                              stock_close_on=stock_close_on, today=W10)


def _flag(row, flag_id):
    return next(f for f in row["red_flags"] if f["id"] == flag_id)


def test_a_backdated_add_is_valued_on_the_day_it_arrives(client, tmp_path, monkeypatch):
    """The card's acceptance. The add (11:00) is in the 20 Feb valuation
    (17:00), so it is money in at 1,000 × ₹150 = ₹1,50,000 on 20 Feb, when
    the Nifty is 105. Last 4 weeks, from the 6 Feb point: the portfolio
    (11,50,000 − 10,00,000 − 1,50,000) / 11,50,000 = 0.0%; the Nifty
    (10,000 + 1,50,000 / 105) × 110 = ₹12,57,142.86, so (12,57,142.86 −
    11,50,000) / 11,50,000 = +9.32%. At its ₹50,000 cost it read +9.52%
    against +9.75% and the flag stayed clear."""
    s = _backdated_add_timeline(client, tmp_path, monkeypatch, add_at="11:00")
    assert s.load().capital_in == 1_050_000.0            # capital_added stays at cost
    row = _row(s, lambda sym, d: {("ACME", date(2026, 2, 20)): 150.0}[(sym, d)])
    window = row["vs_nifty"]["last_4_weeks"]
    assert (window["portfolio_pct"], window["nifty_pct"]) == (0.0, 9.32)
    assert window["deposits"] == 150_000.0
    assert _flag(row, "behind_nifty")["status"] == R.FIRED


def test_an_add_after_the_review_arrives_in_the_next_valuation(client, tmp_path, monkeypatch):
    """Added at 19:00, after the 20 Feb valuation: the 27 Feb point is the
    first that holds it, so it buys the Nifty at 107. The portfolio 0.0%; the
    Nifty (10,000 + 1,50,000 / 107) × 110 = ₹12,54,205.61, (12,54,205.61 −
    11,50,000) / 11,50,000 = +9.06%. Dated 20 Feb instead, the 20 Feb point
    (which does not hold it) would have carried ₹1,00,000 of money in."""
    s = _backdated_add_timeline(client, tmp_path, monkeypatch, add_at="19:00")
    row = _row(s, lambda sym, d: {("ACME", date(2026, 2, 27)): 150.0}[(sym, d)])
    window = row["vs_nifty"]["last_4_weeks"]
    assert (window["portfolio_pct"], window["nifty_pct"]) == (0.0, 9.06)
    assert _flag(row, "behind_nifty")["status"] == R.FIRED


def test_no_close_on_the_arrival_day_reads_could_not_check(client, tmp_path, monkeypatch):
    s = _backdated_add_timeline(client, tmp_path, monkeypatch, add_at="11:00")

    def no_close(sym, d):
        raise LookupError(f"no close for {sym} on {d}")

    row = _row(s, no_close)
    f = _flag(row, "behind_nifty")
    assert f["status"] == R.UNKNOWN
    assert "no close for ACME on 20 Feb, the day it was added" in f["sentence"]
    assert row["vs_nifty"]["since_start"]["available"] is False
    # W10 (from the 27 Feb point) had no money in: the Nifty's own move,
    # 110 / 107 − 1 = +2.80%, against the portfolio's 0.0%.
    week = row["vs_nifty"]["week"]
    assert (week["available"], week["portfolio_pct"], week["nifty_pct"]) == (True, 0.0, 2.8)


def test_an_add_on_a_review_day_before_points_had_a_time_is_not_guessed(
        client, tmp_path, monkeypatch):
    """Points written before SA-051 have no recorded_at: one dated the add's
    own day may or may not hold it, so the windows it touches say so."""
    s = _backdated_add_timeline(client, tmp_path, monkeypatch, add_at="11:00")
    path = tmp_path / "primary" / "value_history.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    path.write_text("".join(json.dumps({k: v for k, v in r.items() if k != "recorded_at"})
                            + "\n" for r in rows), encoding="utf-8")
    row = _row(s, lambda sym, d: 150.0)
    f = _flag(row, "behind_nifty")
    assert f["status"] == R.UNKNOWN
    assert "could not tell whether ACME, added on 20 Feb, was in that day's valuation" \
        in f["sentence"]


def test_an_unvalued_flow_before_a_period_matters_only_if_money_moves_in_it():
    """₹10,00,000 on 5 Jan (Nifty 100), an arrival on 19 Jan that could not
    be valued, then the period from the 19 Jan point to 6 Feb. With no money
    in during the period the Nifty side's units are constant whatever they
    are: 110 / 125 − 1 = −12.0%. With ₹2,00,000 more on 2 Feb its weight
    against the unknown units decides the Nifty figure: unavailable."""
    pts = [point("2026-01-05", 1_000_000.0, 1_000_000.0),
           point("2026-01-19", 1_210_000.0, 1_050_000.0),
           point("2026-02-06", 1_240_000.0, 1_050_000.0)]
    closes = {date(2026, 1, 5): 100.0, date(2026, 1, 19): 125.0,
              date(2026, 2, 2): 118.0, date(2026, 2, 6): 110.0}
    flows = [R.Flow(date(2026, 1, 5), 1_000_000.0), R.Flow(date(2026, 1, 19), None, "why")]
    quiet = R.vs_nifty(pts, closes.__getitem__, end=date(2026, 2, 6),
                       start=date(2026, 1, 20), flows=flows)
    assert quiet["available"] is True and quiet["nifty_value"] is None
    assert quiet["nifty_pct"] == pytest.approx(-12.0)
    assert quiet["portfolio_pct"] == pytest.approx((1_240_000 / 1_210_000 - 1) * 100)
    busy = R.vs_nifty(pts, closes.__getitem__, end=date(2026, 2, 6), start=date(2026, 1, 20),
                      flows=flows + [R.Flow(date(2026, 2, 2), 200_000.0)])
    assert busy == {"available": False, "reason": "why", "to": "2026-02-06"}
    assert R.vs_nifty(pts, closes.__getitem__, end=date(2026, 2, 6),
                      flows=flows)["available"] is False          # since the start


def test_an_add_not_yet_valued_moves_nothing():
    """Added after the last valuation: no point holds it and capital_in in
    the points has not risen, so the flows are the opening deposit alone."""
    pts = [point("2026-02-20", 1_000_000.0, 1_000_000.0)]
    add = _tx("2025-02-03", "ACME", "BUY", 1000, 50.0, 1000, source="manual",
              ts="2026-02-20T13:30:00+00:00", cash_before=1e6, cash_after=1e6)
    assert R.capital_flows(pts, [add], lambda s, d: 150.0) == [
        R.Flow(date(2026, 2, 20), 1_000_000.0)]


def test_only_holdings_that_arrived_without_cash_are_arrivals():
    rows = [
        _tx("2026-01-05", "SEEDCO", "BUY", 10, 100.0, 10, source="seed",
            cash_before=1e6, cash_after=1e6 - 1000),
        _tx("2026-01-06", "AUTOCO", "BUY", 10, 100.0, 10, source="autopilot",
            cash_before=999_000.0, cash_after=998_000.0),
        _tx("2025-02-03", "ACME", "BUY", 1000, 50.0, 1000, source="manual",
            ts="2026-02-20T05:30:00+00:00", cash_before=998_000.0, cash_after=998_000.0),
        _tx("2026-01-07", "AUTOCO", "SELL", 10, 110.0, 0, source="manual",
            cash_before=998_000.0, cash_after=999_100.0),
        # Neither is fresh capital: a manual buy that paid cash, and an
        # autopilot row whose cash fields were never filled (old fixtures).
        _tx("2026-01-08", "PAIDCO", "BUY", 10, 100.0, 10, source="manual",
            cash_before=999_100.0, cash_after=998_100.0),
        _tx("2026-01-09", "ZEROCO", "BUY", 10, 100.0, 10, source="autopilot"),
    ]
    got = R.in_kind_arrivals(rows + rows[2:3])           # a duplicated row counts once
    assert [(a.symbol, a.day, a.cost) for a in got] == [("ACME", date(2026, 2, 20), 50_000.0)]


def test_arrival_day_is_the_ist_date_of_the_add():
    """23:50 UTC on 19 Feb is 05:20 IST on 20 Feb."""
    add = _tx("2025-02-03", "ACME", "BUY", 1, 50.0, 1, source="manual",
              ts="2026-02-19T23:50:00+00:00", cash_before=5.0, cash_after=5.0)
    assert R.in_kind_arrivals([add])[0].day == date(2026, 2, 20)


# -- F2: deposits keep their dates through retention ------------------------------------

def _write_history(tmp_path, points):
    d = tmp_path / "portfolio" / "primary"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "value_history.jsonl"
    path.write_text("".join(json.dumps(p) + "\n" for p in points), encoding="utf-8")
    return path


@pytest.fixture
def retention_dir(tmp_path, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "portfolio"))
    return tmp_path


def test_the_prune_keeps_since_the_start_honest(retention_dir, monkeypatch):
    """PR-002's probe C: ₹1,000 on Mon 5 Jan at Nifty 100 in a stock that
    tracks the index; both make +32% by Fri 6 Mar (Nifty 132). With 2 points
    kept, the old prune turned the 2 Feb point's ₹1,000 into an opening
    deposit at Nifty 120: +32% against +10%. Kept with its own date, it is
    +32% against +32%."""
    days = ["2026-01-05", "2026-01-19", "2026-02-02", "2026-02-16", "2026-03-06"]
    nifty = dict(zip(map(date.fromisoformat, days), (100.0, 110.0, 120.0, 126.0, 132.0)))
    pts = [point(d, 10.0 * n, 1000.0, market_value=10.0 * n) for d, n in
           zip(days, nifty.values())]
    path = _write_history(retention_dir, pts)
    monkeypatch.setattr(retention, "_value_history_cap", lambda: 2)
    assert retention._prune_value_history() == 1
    kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [p["date"] for p in kept] == ["2026-01-05", "2026-02-16", "2026-03-06"]
    m = R.vs_nifty(kept, nifty.__getitem__, end=date(2026, 3, 6), flows=R.capital_flows(kept))
    assert (round(m["portfolio_pct"], 6), round(m["nifty_pct"], 6)) == (32.0, 32.0)
    assert retention._prune_value_history() == 0        # nothing left to trim


@pytest.mark.parametrize("seed", range(40))
def test_the_prune_never_moves_a_deposit(retention_dir, monkeypatch, seed):
    """Random histories with deposits on random days: the deposits (date and
    amount) and the since-start comparison are the same before and after any
    cap, and the last `cap` points are kept as they were."""
    rnd = random.Random(seed)
    day, capital, pts = date(2026, 1, 5), 0.0, []
    for _ in range(rnd.randint(3, 40)):
        if not pts or rnd.random() < 0.15:
            capital += rnd.choice([1000.0, 2500.0, 50_000.0, 123.45])
        pts.append(point(day.isoformat(), capital * rnd.uniform(0.8, 1.3), capital))
        day += timedelta(days=rnd.choice([1, 1, 3]))
    cap = rnd.randint(1, len(pts) + 2)
    path = _write_history(retention_dir, pts)
    monkeypatch.setattr(retention, "_value_history_cap", lambda: cap)
    retention._prune_value_history()
    kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert R.capital_flows(kept) == R.capital_flows(pts)
    assert kept[-min(cap, len(pts)):] == pts[-min(cap, len(pts)):]
    closes = {date.fromisoformat(p["date"]): 100.0 + i for i, p in enumerate(pts)}
    end = date.fromisoformat(pts[-1]["date"])
    assert R.vs_nifty(kept, closes.__getitem__, end=end) == \
        R.vs_nifty(pts, closes.__getitem__, end=end)


# -- The closed-trade record ----------------------------------------------------------

def test_the_closed_trade_record_matches_the_hand_figures(client, tmp_path):
    """The card's example: 6 wins of +3% and 4 losses of −10% on a ₹100
    cost. Win rate 60%; expectancy 0.6 × 3 − 0.4 × 10 = −2.2% per trade. An
    open position (BUY only) and a TRIM that leaves shares are not trades."""
    s = cash_account(tmp_path)
    for i in range(10):
        pct = 3.0 if i < 6 else -10.0
        sym = f"S{i}"
        s.append_transaction(_tx("2026-01-05", sym, "BUY", 10, 100.0, 10))
        s.append_transaction(_tx("2026-02-02", sym, "SELL", 10, 100.0 + pct, 0.0,
                                 realized_pnl=10 * pct, cost_basis=100.0))
    s.append_transaction(_tx("2026-01-05", "OPEN", "BUY", 10, 100.0, 10))
    s.append_transaction(_tx("2026-01-05", "PART", "BUY", 10, 100.0, 10))
    s.append_transaction(_tx("2026-02-02", "PART", "SELL", 4, 150.0, 6.0,
                             realized_pnl=200.0, cost_basis=100.0))
    ct = client.get("/portfolio/performance").json()["closed_trades"]
    assert (ct["count"], ct["wins"], ct["losses"]) == (10, 6, 4)
    assert ct["win_rate_pct"] == pytest.approx(60.0)
    assert ct["avg_win_pct"] == pytest.approx(3.0)
    assert ct["avg_loss_pct"] == pytest.approx(-10.0)
    assert ct["expectancy_pct"] == pytest.approx(-2.2)
    assert ct["basis"] == "before costs"


def test_no_comparison_or_record_without_cash_accounting(client, tmp_path, monkeypatch):
    """A manual portfolio records no deposit and no sale, so there is
    nothing to compare: no record and an unavailable comparison, never zeros."""
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    s.add_holding(Holding(symbol="TCS", sector="it", qty=1, avg_buy_price=100.0,
                          adj_avg_price=100.0, adj_qty=1, buy_date="2026-01-05"))
    monkeypatch.setattr(papi, "close_on", lambda sym, d: 120.0)
    d = client.get("/portfolio/performance").json()
    assert d["market_value"] == 120.0
    assert d["closed_trades"] is None
    assert d["vs_nifty"]["available"] is False
    assert (d["in_stocks_pct"], d["cash_pct"]) == (None, None)


# -- Labels: shares of total equity ---------------------------------------------------

def test_in_stocks_and_cash_are_shares_of_total_equity(client, tmp_path):
    """₹1,90,000 in stocks and ₹8,10,000 cash: 19.0% and 81.0% of ₹10,00,000."""
    s = cash_account(tmp_path, cash=810_000.0)
    s.append_value_point(point("2026-02-06", 1_000_000.0, 1_000_000.0, market_value=190_000.0))
    FakeNifty.closes = {date(2026, 2, 6): 100.0}
    d = client.get("/portfolio/performance").json()
    assert (d["market_value"], d["cash"], d["total_equity"]) == (190_000.0, 810_000.0, 1_000_000.0)
    assert (d["in_stocks_pct"], d["cash_pct"]) == (19.0, 81.0)


@pytest.mark.parametrize("seed", range(200))
def test_the_two_shares_always_add_to_100(seed):
    rnd = random.Random(seed)
    mv = rnd.choice([0.0, rnd.uniform(0, 1e7), 1.0 / 3.0, 0.01])
    cash = rnd.choice([0.0, rnd.uniform(0, 1e7), 2.0 / 3.0, 0.01])
    if mv + cash <= 0:
        cash = 1.0
    stocks, cash_pct = papi._equity_shares(mv, cash)
    shown = float(f"{stocks:.1f}") + float(f"{cash_pct:.1f}")
    assert shown == pytest.approx(100.0, abs=1e-9)
    assert 0.0 <= stocks <= 100.0 and 0.0 <= cash_pct <= 100.0


@pytest.mark.parametrize("mv, cash", [(5, 9995), (35, 9965), (65, 9935), (135, 9865)])
def test_the_two_shares_add_to_100_at_rounding_edges(mv, cash):
    """₹5 in stocks and ₹9,995 cash: rounded apart, 0.05% and 99.95% read
    0.1% and 100.0%, which add to 100.1%."""
    stocks, cash_pct = papi._equity_shares(float(mv), float(cash))
    assert float(f"{stocks:.1f}") + float(f"{cash_pct:.1f}") == pytest.approx(100.0, abs=1e-9)


def test_every_holding_price_carries_its_date(client, tmp_path, monkeypatch):
    from core.intelligence.rl.workflows.daily_review import SessionClose
    s = cash_account(tmp_path)
    s.add_holding(Holding(symbol="WELCORP", sector="metals", qty=10, avg_buy_price=2600.0,
                          adj_avg_price=2600.0, adj_qty=10, buy_date="2026-09-01"))
    # The bar is Friday's: the fetch fell back from Monday to the last session.
    monkeypatch.setattr(papi, "session_close", lambda sym, d: (
        SessionClose(2832.4, date(2026, 10, 16), "test"), date(2026, 10, 19)))
    row = client.get("/portfolio").json()["holdings"][0]
    assert (row["last_close"], row["last_close_date"], row["buy_date"]) == \
        (2832.4, "2026-10-16", "2026-09-01")


# -- The value point records when it was taken; CSV imports reach the ledger ---------

def test_a_value_point_records_when_it_was_taken(tmp_path, monkeypatch):
    clock = Clock(monkeypatch)
    s = cash_account(tmp_path)
    clock.at("2026-02-20", "17:05")
    p = autopilot.record_value_point(s, s.load(), {}, date(2026, 2, 20))
    assert p["recorded_at"] == "2026-02-20T11:35:00+00:00"


def test_the_pipeline_takes_the_value_point_under_the_users_lock(monkeypatch):
    """An add holds the user's lock from its ledger row to its save. The
    valuation takes the same lock, so it holds the add whole or not at all,
    and its recorded_at is after the add's ts exactly when it holds it."""
    from unittest.mock import patch

    import core.portfolio.pipeline as pl
    from backend.shared.schemas.portfolio import AdviceRecord, Portfolio
    from core.portfolio.pricing import SessionClose

    day = date(2026, 7, 13)
    monkeypatch.setattr(autopilot, "_today_ist", lambda: day)
    events: list[str] = []
    portfolio = Portfolio(user_id="t1", holdings=[Holding(
        symbol="MARUTI", sector="automobile", qty=10, avg_buy_price=100.0,
        adj_avg_price=100.0, adj_qty=10, buy_date="2026-06-01")])
    advice = AdviceRecord(date=day.isoformat(), user_id="t1", symbol="MARUTI",
                          verdict="HOLD", close=110.0, unrealised_pnl_pct=10.0, stop_pct=8.0)
    with patch.object(pl, "active_user_ids", return_value=["t1"]), \
         patch.object(pl, "PortfolioStore") as MockStore, \
         patch.object(pl, "sync_corp_actions"), \
         patch.object(pl, "refresh_events_calendar", return_value={}), \
         patch.object(pl, "session_close", return_value=(SessionClose(110.0, day, "agree"), day)), \
         patch.object(pl, "get_price_history", side_effect=Exception("skip")), \
         patch.object(pl, "build_signals"), \
         patch.object(pl, "gated_decide", return_value=(advice, None)), \
         patch.object(pl, "narrate", return_value="n"), \
         patch("core.portfolio.autopilot.execute_advice", return_value=[]), \
         patch("core.portfolio.autopilot.record_value_point",
               side_effect=lambda *a, **k: events.append("point")), \
         patch.object(pl, "is_trading_day", return_value=True):
        store = MockStore.return_value
        store.load.return_value = portfolio
        store.locked.return_value.__enter__.side_effect = lambda *a: events.append("lock")
        store.locked.return_value.__exit__.side_effect = lambda *a: events.append("unlock")
        assert pl.run_post_review_pipeline(day)["status"] == "completed"
    i = events.index("point")
    assert events[i - 1:i + 2] == ["lock", "point", "unlock"], events


def test_a_csv_import_writes_the_add_rows_and_reconciles(tmp_path):
    """Two rows on a ₹10 L cash account: 10 TCS at a typed ₹3,000 bought in
    2025, and 5 INFY priced at its buy date's ₹1,500. capital_in rises by
    ₹30,000 + ₹7,500; cash does not move; each position gets the same kind of
    ledger row as Add holding, so the ledger nets both quantities (before,
    reconcile reported them as drift) and both are arrivals to value."""
    s = cash_account(tmp_path)
    text = ("symbol,sector,qty,avg_buy_price,buy_date\n"
            "TCS,it,10,3000,2025-03-03\n"
            "INFY,it,5,,2026-02-02\n"
            "BAD,it,zero,1,2026-02-02\n")
    out = import_csv(text, user_id="primary", base_dir=str(tmp_path),
                     price_lookup=lambda sym, d: 1500.0)
    assert out["imported"] == 2 and [e["row"] for e in out["errors"]] == [4]
    p = s.load()
    assert (p.capital_in, p.cash_deployable) == (1_037_500.0, 1_000_000.0)
    rows = s.load_transactions()
    assert [(t.symbol, t.side, t.source, t.qty, t.value, t.cash_before, t.cash_after)
            for t in rows] == [("TCS", "BUY", "manual", 10, 30_000.0, 1e6, 1e6),
                               ("INFY", "BUY", "manual", 5, 7_500.0, 1e6, 1e6)]
    assert reconcile(s)["status"] == "clean"
    assert [a.symbol for a in R.in_kind_arrivals(rows)] == ["TCS", "INFY"]


def test_a_csv_import_without_cash_accounting_writes_no_rows(tmp_path):
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    out = import_csv("symbol,sector,qty,avg_buy_price,buy_date\nTCS,it,10,3000,2025-03-03\n",
                     user_id="primary", base_dir=str(tmp_path))
    assert out["imported"] == 1
    assert s.load_transactions() == [] and s.load().capital_in == 0.0


# -- The Nifty download: one per range, same closes as one per date -----------------

def _bars(days_closes):
    return pd.DataFrame({("Close", "^NSEI"): list(days_closes.values())},
                        index=pd.DatetimeIndex([pd.Timestamp(d) for d in days_closes]))


@pytest.mark.parametrize("seed", range(25))
def test_a_preloaded_range_gives_the_per_date_closes(monkeypatch, seed):
    """Bars on random weekdays (a missing weekday is an unscheduled closure),
    one named holiday. Every calendar day of the range gets the same close
    from one download as from its own fetch: the day's session, or the last
    close before it, never one after."""
    rnd = random.Random(seed)
    holiday = date(2026, 1, 26)
    monkeypatch.setattr(cal, "_NSE_HOLIDAYS", frozenset({holiday}))
    bars, d = {}, date(2025, 12, 15)
    while d <= date(2026, 3, 15):
        if d.weekday() < 5 and d != holiday and rnd.random() > 0.15:
            # each close names its own day, so the day a close came from is known
            bars[d.isoformat()] = 20000.0 + d.toordinal() % 10000
        d += timedelta(days=1)
    day_of = {v: date.fromisoformat(k) for k, v in bars.items()}
    frame = _bars(bars)
    calls = []

    def download(ticker, start, end, **kw):
        calls.append((start, end))
        lo, hi = pd.Timestamp(start), pd.Timestamp(end)
        return frame[(frame.index >= lo) & (frame.index < hi)]

    monkeypatch.setattr("yfinance.download", download)
    start, end = date(2026, 1, 5), date(2026, 3, 6)
    loaded = B.BenchmarkSeries("^NSEI")
    assert loaded.preload(start, end) is True
    assert len(calls) == 1
    d = start
    while d <= end:
        try:
            expected = B.BenchmarkSeries("^NSEI").close_on(d)
        except B.BenchmarkUnavailableError:
            expected = None
        try:
            got = loaded.close_on(d)
        except B.BenchmarkUnavailableError:
            got = None
        assert got == expected, d
        if got is not None:
            assert day_of[got] <= d, f"{d} got the close of the later {day_of[got]}"
            assert (d - day_of[got]).days <= 17       # walkback 10 days + 7-day window
        d += timedelta(days=1)


def test_a_range_whose_last_session_lags_is_asked_again(monkeypatch):
    """Fri 6 Feb's Nifty bar is not out yet: 6 Feb stands on Thursday's close
    for this load only. Once the bar is out, the next load uses it, and that
    range is then reused for the hour without another download."""
    bars = {"2026-02-02": 100.0, "2026-02-03": 101.0, "2026-02-04": 102.0, "2026-02-05": 103.0}
    calls = []

    def download(ticker, start, end, **kw):
        calls.append(1)
        f = _bars(bars)
        return f[(f.index >= pd.Timestamp(start)) & (f.index < pd.Timestamp(end))]

    monkeypatch.setattr("yfinance.download", download)
    span = (date(2026, 2, 2), date(2026, 2, 6))
    first = B.BenchmarkSeries("^NSEI")
    first.preload(*span)
    assert first.close_on(date(2026, 2, 6)) == 103.0
    bars["2026-02-06"] = 104.0
    second = B.BenchmarkSeries("^NSEI")
    second.preload(*span)
    assert second.close_on(date(2026, 2, 6)) == 104.0
    third = B.BenchmarkSeries("^NSEI")
    third.preload(*span)
    assert third.close_on(date(2026, 2, 6)) == 104.0
    assert len(calls) == 2


def test_only_a_past_days_stock_close_is_kept(monkeypatch):
    import core.portfolio.pricing as pricing
    calls = []
    monkeypatch.setattr(pricing, "close_on", lambda s, d: calls.append((s, d)) or 150.0)
    monkeypatch.setattr(R, "_today", lambda: date(2026, 2, 20))
    R._cached_stock_close.cache_clear()
    look = R.stock_close_fn()
    for _ in range(2):
        assert look("ACME", date(2026, 2, 19)) == 150.0      # past: fetched once
        assert look("ACME", date(2026, 2, 20)) == 150.0      # today: may not be final
    assert calls == [("ACME", date(2026, 2, 19)), ("ACME", date(2026, 2, 20)),
                     ("ACME", date(2026, 2, 20))]
    R._cached_stock_close.cache_clear()


def test_after_a_failed_preload_no_date_in_range_fetches(monkeypatch):
    calls = []

    def download(*a, **kw):
        calls.append(1)
        raise ConnectionError("offline")

    monkeypatch.setattr("yfinance.download", download)
    s = B.BenchmarkSeries("^NSEI")
    assert s.preload(date(2026, 1, 5), date(2026, 2, 6)) is False
    with pytest.raises(B.BenchmarkUnavailableError):
        s.close_on(date(2026, 1, 20))
    assert len(calls) == 1
