"""PR-036 — ₹1 crore of paper capital, 25 positions aimed for, 30 at most.

The settings ship in config.yaml; nothing in the sizing or deployment code
changes. These tests run SA-049's real executor (`execute_advice`) with the
settings read from config.yaml, not pinned to the card's numbers, and check
the result against the card's numbers written here. Every expected figure is
worked by hand in the docstring from the fixture's own numbers.

The card's numbers (owner, 17 Nov 2026; PR-035's read, 18 Nov 2026):
- 80% of equity invested in calm regimes, 50% in RISK_OFF, none in a crisis;
- a position asks for 80% ÷ 25 = 3.2% of equity: ₹3,20,000 of ₹1 crore;
- at most 30 holdings, at least 20 aimed for (reported, never forcing a buy);
- at most 5 new positions a day;
- caps 10% a position and 30% a sector, of total equity after the trade;
  every buy leaves ₹10,000 in cash.

Independent invariants:
- the shipped values, each named once;
- the card's example by hand: ₹1 crore at ₹1,100 a share opens 5 positions a
  day, 290 shares each, and a 26th on the sixth day because whole shares leave
  25 of them ₹25,000 short of the target; in RISK_OFF buying stops at 16;
  six ideas on an eight-holding book are reported against the 20 aimed for;
- a property test at ₹1 crore over random books, idea lists, prices and
  regimes, eight sessions each: never more than 30 holdings or 5 new a day,
  no cap breached, cash at or above its floor, invested past the regime's
  target by at most one position, and nothing ever sold.
"""
from __future__ import annotations

import random

import pytest

from backend.shared.config.settings.loader import cfg
from core.config import settings
from core.portfolio import autopilot as ap
import tests.unit.test_deploy_idle_cash_sa049 as story
from tests.unit.test_deploy_idle_cash_sa049 import _pinned  # noqa: F401  (autouse)

CRORE = 10_000_000.0
FLOOR = 10_000.0
ASK_SHARE = 0.80 / 25            # the card: a position asks for 3.2% of equity
CARD = {"min": 20, "target": 25, "max": 30, "per_day": 5, "position_pct": 10.0,
        "sector_pct": 30.0, "calm": 80.0, "risk_off": 50.0}


@pytest.fixture(autouse=True)
def _shipped(_pinned, monkeypatch):
    """SA-049's harness (a frozen clock, a NORMAL regime, a clear surveillance
    report, no managed-ticker writes), then the breadth, caps and floor as
    config.yaml ships them, in place of that file's pinned values."""
    for name, path in (("AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", "autopilot.deploy_max_new_per_day"),
                       ("PORTFOLIO_MIN_HOLDINGS", "portfolio.min_holdings"),
                       ("PORTFOLIO_TARGET_HOLDINGS", "portfolio.target_holdings"),
                       ("PORTFOLIO_MAX_HOLDINGS", "portfolio.max_holdings"),
                       ("ADVISOR_MAX_POSITION_PCT", "advisor.max_position_pct"),
                       ("ADVISOR_MAX_SECTOR_PCT", "advisor.max_sector_pct"),
                       ("AUTOPILOT_MIN_CASH_FLOOR", "autopilot.min_cash_floor")):
        monkeypatch.setattr(settings, name, cfg(path))
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_TARGET_PCT",
                        {k: float(v) for k, v in cfg("autopilot.deploy_target_invested_pct").items()})


def test_the_shipped_values_are_the_cards():
    assert (cfg("portfolio.min_holdings"), cfg("portfolio.target_holdings"),
            cfg("portfolio.max_holdings")) == (CARD["min"], CARD["target"], CARD["max"])
    assert cfg("autopilot.deploy_max_new_per_day") == CARD["per_day"]
    # every holding keeps its daily review: 30 holdings + 16 original entries = 46
    assert cfg("portfolio.max_managed_tickers") == 60
    # held first, then watched, then the shelf's ideas
    assert cfg("events.max_symbols") == 90
    # unchanged by PR-036: the caps, the floor and the regime shares
    assert (cfg("advisor.max_position_pct"), cfg("advisor.max_sector_pct"),
            cfg("autopilot.min_cash_floor")) == (CARD["position_pct"], CARD["sector_pct"], FLOOR)
    shares = cfg("autopilot.deploy_target_invested_pct")
    assert (shares["NORMAL"], shares["RISK_OFF"], shares["MACRO_CRISIS"]) == (80, 50, 0)


def _book(tmp_path, monkeypatch, n_ideas, price):
    """₹1 crore, all cash, no costs; n ideas at `price`, each in its own sector,
    convictions descending."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", story.NO_COSTS)
    s = story._store(tmp_path, [], cash=CRORE, capital_in=CRORE)
    ideas = [story._idea(f"I{k:02d}", price, round(0.95 - k * 0.01, 2), f"sector{k:02d}")
             for k in range(n_ideas)]
    story._prices(monkeypatch, {i.symbol: price for i in ideas})
    return s, ideas


def test_one_crore_opens_five_a_day_and_a_26th_on_the_sixth_day(tmp_path, monkeypatch):
    """Equity ₹1,00,00,000 in NORMAL: target 80% = ₹80,00,000. A position asks
    for 80% × ₹1 crore ÷ 25 = ₹3,20,000: floor(3,20,000 / 1,100) = 290 shares
    = ₹3,19,000 (3.19% of equity). Thirty ideas at ₹1,100.
      days 1-5: 5 a day, the daily limit; 25 holdings, ₹79,75,000 (79.75%),
                ₹25,000 short of the target;
      day 6:    one more, the 26th: ₹82,94,000 (82.94%), target reached;
      day 7:    nothing; cash ₹1 crore − ₹82,94,000 = ₹17,06,000.
    Day 1's record: 5 holdings, below the 20 aimed for, behind the daily limit."""
    s, ideas = _book(tmp_path, monkeypatch, 30, 1100.0)
    days = story._weekdays(story.D, 7)
    per_day, records = [], []
    for on in days:
        held = {h.symbol: 1100.0 for h in s.load().holdings}
        txns, rec = story._run(s, ideas, held, on=on)
        assert all(t.side == "BUY" for t in txns)
        per_day.append([(t.symbol, t.qty) for t in txns])
        records.append(rec)

    assert [len(d) for d in per_day] == [5, 5, 5, 5, 5, 1, 0]
    assert all(qty == 290.0 for d in per_day for _, qty in d)
    assert [sym for d in per_day for sym, _ in d] == [f"I{k:02d}" for k in range(26)]
    p = s.load()
    assert len(p.holdings) == 26 and p.cash_deployable == 1_706_000.0

    first = records[0]
    assert (first["position_inr"], first["target_inr"], first["max_holdings"],
            first["min_holdings"]) == (320_000.0, 8_000_000.0, 30, 20)
    assert first["reasons"][0] == "5 new positions today, the daily limit of 5"
    assert first["reasons"][1].startswith("5 holdings, below the 20 aimed for")
    assert [r["invested_after_pct"] for r in records] == [16.0, 31.9, 47.9, 63.8, 79.8, 82.9, 82.9]
    assert records[5]["reasons"][0] == ("regime NORMAL, target reached: 82.9% invested against "
                                        "a target of 80.0% (₹80,00,000)")
    assert records[6]["bought"] == []


def test_in_risk_off_one_crore_stops_at_sixteen(tmp_path, monkeypatch):
    """RISK_OFF: target 50% = ₹50,00,000; a position still asks for ₹3,20,000
    = 320 shares at ₹1,000. Fifteen positions are ₹48,00,000, below the target,
    so a 16th opens: ₹51,20,000 (51.2%). 5, 5, 5, then 1; nothing on day 5.
    The soft minimum is not in force outside calm regimes."""
    s, ideas = _book(tmp_path, monkeypatch, 30, 1000.0)
    story._regime(monkeypatch, "RISK_OFF")
    counts = []
    for on in story._weekdays(story.D, 5):
        held = {h.symbol: 1000.0 for h in s.load().holdings}
        txns, rec = story._run(s, ideas, held, on=on)
        assert all(t.side == "BUY" and t.qty == 320.0 for t in txns)
        assert rec["min_holdings"] == 0
        counts.append(len(txns))
    assert counts == [5, 5, 5, 1, 0]
    assert len(s.load().holdings) == 16 and s.load().cash_deployable == 4_880_000.0


def test_few_ideas_are_reported_against_the_twenty_aimed_for(tmp_path, monkeypatch):
    """₹1 crore: 8 holdings of 320 shares at ₹1,000 (₹25,60,000) and ₹74,40,000
    cash; 6 ideas at ₹1,000. Five are bought, the daily limit; 13 holdings are
    below the 20 aimed for, and 13 + the 1 waiting is still short of 20, so the
    record names the ideas: "only 6 qualifying ideas". Cash ₹74,40,000 − 5 ×
    ₹3,20,000 = ₹58,40,000."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", story.NO_COSTS)
    held = [story._h(f"H{k}", 320, 1000.0, f"held{k}") for k in range(8)]
    s = story._store(tmp_path, held, cash=7_440_000.0, capital_in=CRORE)
    ideas = [story._idea(f"I{k}", 1000.0, round(0.9 - k * 0.01, 2), f"sector{k}")
             for k in range(6)]
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = story._run(s, ideas, {h.symbol: 1000.0 for h in held})
    assert [(t.symbol, t.qty) for t in txns] == [(f"I{k}", 320.0) for k in range(5)]
    assert rec["reasons"] == ["5 new positions today, the daily limit of 5",
                              "13 holdings, below the 20 aimed for: only 6 qualifying ideas",
                              "1 idea qualifying but not bought today"]
    assert s.load().cash_deployable == 5_840_000.0


REGIMES = (["NORMAL", "RISK_ON", "MOMENTUM_EXTENDED", "OVERSOLD"] * 3
           + ["RISK_OFF"] * 3 + ["MACRO_CRISIS", None])
# Half the stocks are banks, so the 30% sector cap binds on full books.
SECTORS = ["banking_bfsi"] * 6 + ["pharma"] * 2 + ["it_sector", "power", "metals", "fmcg"]


def test_property_one_crore_over_eight_sessions_keeps_every_rule(tmp_path, monkeypatch):
    """120 seeded books at about ₹1 crore (0 to 30 holdings already held, the
    rest in cash), eight sessions each at the configured trading costs, with
    prices drifting, a random regime and a random list of up to 40 ideas each
    session. After every run, by this test's own arithmetic at the run's
    marks:
      - at most 30 holdings, at most 5 new positions, and no SELL: every
        holding held before keeps its shares;
      - no BUY in MACRO_CRISIS or without a regime;
      - every BUY asks for at most 3.2% of the run's starting equity, and after
        it its position is at most 10% and its sector at most 30% of equity;
      - after any BUY cash is at or above ₹10,000;
      - invested passes the regime's target (80% calm, 50% RISK_OFF) by at most
        one position, unless it already stood above it.
    The counters prove each stop was reached."""
    seen = {"buys": 0, "crisis_or_none": 0, "target": 0, "limit": 0, "max": 0,
            "risk_off_buys": 0, "full_books": 0, "sector_capped": 0}
    for seed in range(120):
        rng = random.Random(seed)
        sector_of, price = {}, {}
        holdings = []
        for i in range(rng.choice([0, 3, 5, 11, 24, 29, 30])):
            sym = f"H{i}"
            price[sym] = round(rng.uniform(50, 3000), 2)
            sector_of[sym] = rng.choice(SECTORS)
            qty = float(max(1, int(rng.uniform(20_000, 300_000) / price[sym])))
            holdings.append(story._h(sym, qty, price[sym], sector_of[sym]))
        spent = sum(h.adj_qty * h.adj_avg_price for h in holdings)
        cash = round(max(CRORE - spent, rng.uniform(0, 50_000)), 2)
        pool = [f"C{k}" for k in range(60)]
        for sym in pool:
            price[sym] = round(rng.uniform(20, 120_000), 2)
            sector_of[sym] = rng.choice(SECTORS)
        s = story._store(tmp_path, holdings, cash, name=f"cr{seed}", capital_in=CRORE)

        for on in story._weekdays(story.D, 8):
            for sym in price:
                price[sym] = round(price[sym] * rng.uniform(0.95, 1.06), 2)
            regime = rng.choice(REGIMES)
            story._regime(monkeypatch, regime)
            ideas = []
            for sym in rng.sample(pool, rng.randint(0, 40)):
                p = price[sym]
                lo, hi = p * rng.uniform(0.85, 1.0), p * rng.uniform(0.92, 1.2)
                ideas.append(story._idea(sym, p, round(rng.uniform(0.5, 0.95), 2),
                                         sector_of[sym],
                                         gate=rng.choice(["actionable"] * 5 + ["abstain"]),
                                         lo=round(lo, 2), hi=round(hi, 2),
                                         inval=round(lo * rng.uniform(0.8, 0.99), 2)))
            story._prices(monkeypatch, {i.symbol: price[i.symbol] for i in ideas})
            before = s.load()
            marks = {h.symbol: price[h.symbol] for h in before.holdings}
            inv0 = sum(h.adj_qty * marks[h.symbol] for h in before.holdings)
            eq0 = inv0 + before.cash_deployable
            ask = ASK_SHARE * eq0
            share = {None: 0.0, "MACRO_CRISIS": 0.0, "RISK_OFF": CARD["risk_off"]}.get(
                regime, CARD["calm"])
            target = min(share / 100.0 * eq0, max(0.0, eq0 - FLOOR))

            txns, rec = story._run(s, ideas, dict(marks), on=on)
            after = s.load()
            buys = [t for t in txns if t.side == "BUY"]
            ctx = (seed, on.isoformat(), regime)

            assert all(t.side == "BUY" for t in txns), ctx
            assert len(after.holdings) <= CARD["max"], ctx
            assert len(buys) <= CARD["per_day"], ctx
            qty_after = {h.symbol: h.adj_qty for h in after.holdings}
            for h in before.holdings:
                assert qty_after.get(h.symbol) == h.adj_qty, ctx
            if regime in (None, "MACRO_CRISIS"):
                seen["crisis_or_none"] += 1
                assert not buys, ctx
            if buys:
                eq_after = sum(h.adj_qty * price[h.symbol] for h in after.holdings) \
                    + after.cash_deployable
                for t in buys:
                    assert t.symbol not in marks, ctx
                    assert t.qty * t.price <= ask + 1e-6, ctx
                    pos = qty_after[t.symbol] * price[t.symbol]
                    sec = sum(h.adj_qty * price[h.symbol] for h in after.holdings
                              if sector_of[h.symbol] == sector_of[t.symbol])
                    assert pos <= CARD["position_pct"] / 100 * eq_after + 1e-6, ctx
                    assert sec <= CARD["sector_pct"] / 100 * eq_after + 1e-6, ctx
                assert after.cash_deployable >= FLOOR - 0.005, ctx
                inv_after = sum(h.adj_qty * price[h.symbol] for h in after.holdings)
                assert inv_after <= max(target, inv0) + ask + 1e-6, ctx
                seen["risk_off_buys"] += len(buys) * (regime == "RISK_OFF")
            seen["buys"] += len(buys)
            seen["full_books"] += len(after.holdings) == CARD["max"]
            if rec is not None:
                assert abs(rec["position_inr"] - round(ask, 2)) <= 0.01, ctx
                first = rec["reasons"][0]
                seen["target"] += "target reached" in first
                seen["limit"] += "the daily limit of 5" in first
                seen["max"] += "the maximum of 30" in first
                # the sector cap reads "the 30% cap on banking_bfsi"
                seen["sector_capped"] += sum(o["outcome"] == "size" and "% cap on " in o["why"]
                                             for o in rec["ideas"])
                seen["sector_capped"] += sum("capped by the 30% cap on " in t.note
                                             for t in buys)
    assert seen["buys"] > 500 and seen["crisis_or_none"] > 50, seen
    assert seen["target"] > 50 and seen["limit"] > 50 and seen["max"] > 10, seen
    assert seen["risk_off_buys"] > 20 and seen["full_books"] > 10, seen
    assert seen["sector_capped"] > 10, seen
