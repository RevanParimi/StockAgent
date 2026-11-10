"""SA-050 — one sizing and entry rule for every autopilot buy.

Every expected figure below is worked by hand in the comments from the
fixture's own numbers: total equity is holdings at their marks plus cash, a
cash-paid buy leaves it unchanged, so the room under a cap is
cap × equity − current value. Nothing here asks the sizing module what the
answer should be.

Caps: position 10% (`advisor.max_position_pct`), sector 30%
(`advisor.max_sector_pct`), cash floor ₹10,000 (`autopilot.min_cash_floor`).
"""
from __future__ import annotations

import logging
import random
from datetime import date
from types import SimpleNamespace

import pytest

from backend.shared.schemas.discovery import Shelf, ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.config import settings
from core.portfolio import autopilot as ap
from core.portfolio import sizing
from core.portfolio.advisor import build_signals, decide
from core.portfolio.pricing import SessionClose
from core.portfolio.store import PortfolioStore
from tests.unit.test_decision_gate_portfolio_sa003 import gate_mode  # noqa: F401 — fixture

D = date(2026, 7, 13)                       # a Monday
CONFIGURED_COSTS = dict(settings.PORTFOLIO_COSTS)
# The worked examples here are the sizing rule's arithmetic, before trading
# costs. SA-048's charges are pinned by test_trading_costs_sa048.py; the
# property test below runs on the configured rates.
NO_COSTS = {**CONFIGURED_COSTS, "brokerage_pct": 0.0, "stt_pct": 0.0,
            "stamp_duty_buy_pct": 0.0, "exchange_fee_pct": 0.0, "sebi_fee_pct": 0.0,
            "dp_charge_inr": 0.0}


@pytest.fixture(autouse=True)
def _pinned(monkeypatch, tmp_path):
    """The caps this file's arithmetic assumes, no trading costs, a frozen
    clock, no managed-ticker writes, and an empty instrument registry (every
    symbol resolves)."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", NO_COSTS)
    monkeypatch.setattr(settings, "ADVISOR_MAX_POSITION_PCT", 10.0)
    monkeypatch.setattr(settings, "ADVISOR_MAX_SECTOR_PCT", 30.0)
    monkeypatch.setattr(settings, "AUTOPILOT_MIN_CASH_FLOOR", 10000.0)
    monkeypatch.setattr(settings, "AUTOPILOT_ADD_TRANCHE_PCT", 25.0)
    monkeypatch.setattr(ap, "_today_ist", lambda: D)
    monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})
    reg = tmp_path / "instruments.yaml"
    reg.write_text("version: 1\ninstruments: {}\n", encoding="utf-8")
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(reg))


def _h(sym, qty, cost, sector):
    return Holding(symbol=sym, sector=sector, qty=qty, avg_buy_price=cost,
                   adj_avg_price=cost, adj_qty=qty, buy_date="2026-06-01")


def _store(tmp_path, holdings, cash, name="u"):
    s = PortfolioStore(user_id=name, base_dir=str(tmp_path / "pf"))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = holdings, cash, 1_000_000.0, True
    s.save(p)
    return s


def _idea(sym, lo, hi, inval, sector="pharma"):
    return ShelfIdea(symbol=sym, sector=sector, added="2026-07-01", conviction=0.9,
                     entry_low=lo, entry_high=hi, invalidation_level=inval,
                     data_gate="actionable")


def _switch(sym, cand, close):
    return AdviceRecord(date=D.isoformat(), user_id="u", symbol=sym, verdict="SWITCH",
                        close=close, unrealised_pnl_pct=-13.0, stop_pct=12.0,
                        confidence=0.5, switch_candidate=cand,
                        triggers=["stop_breach", "switch_candidate_available"],
                        rationale_hash=f"sw{sym}")


def _add(sym, close, confidence=0.6):
    return AdviceRecord(date=D.isoformat(), user_id="u", symbol=sym, verdict="ADD",
                        close=close, unrealised_pnl_pct=2.0, stop_pct=12.0,
                        confidence=confidence, triggers=["add_bullish_healthy"],
                        rationale_hash=f"add{sym}")


def _prices(monkeypatch, prices):
    monkeypatch.setattr(ap, "session_close",
                        lambda sym, d: (SessionClose(prices[sym], d, "agree"), d))


def _run(store, advice, closes, ideas=(), sectors=None):
    return ap.execute_advice(store, store.load(), advice, closes, D,
                             sector_lookup=sectors or {i.symbol: i.sector for i in ideas},
                             shelf_index={i.symbol: i for i in ideas})


def _sides(txns):
    return [(t.side, t.symbol, t.qty) for t in txns]


# ---------------------------------------------------------------------------
# The card's acceptance fixtures
# ---------------------------------------------------------------------------

def test_the_227k_switch_buys_at_most_the_10pct_position(tmp_path, monkeypatch):
    """Card: a holding worth ₹2.27 L (22.7% of a ₹10 L portfolio) is sold and
    switched. Before SA-050 the whole proceeds bought the new stock.

    Equity = ACMESOLAR 1,000 × 227 (2,27,000) + ITCO 500 × 1,000 (5,00,000)
             + cash 2,73,000 = 10,00,000.
    10% cap = 1,00,000; NEWPHARMA has no position, so room = 1,00,000.
    Sector pharma 30% = 3,00,000 room; cash after the sale 5,00,000 − floor
    10,000 = 4,90,000 room; proceeds 2,27,000. Tightest: the position cap.
    floor(1,00,000 / 530) = 188 shares = 99,640; left 2,27,000 − 99,640 = 1,27,360.
    (The old rule: floor(min(2,27,000, 4,90,000) / 530) = 428 shares, 22.7%.)
    """
    s = _store(tmp_path, [_h("ACMESOLAR", 1000, 260.0, "power"),
                          _h("ITCO", 500, 1000.0, "it_sector")], cash=273_000.0)
    _prices(monkeypatch, {"NEWPHARMA": 530.0})
    closes = {"ACMESOLAR": 227.0, "ITCO": 1000.0}
    txns = _run(s, [_switch("ACMESOLAR", "NEWPHARMA", 227.0)], closes,
                ideas=[_idea("NEWPHARMA", 500.0, 540.0, 470.0)])

    assert _sides(txns) == [("SELL", "ACMESOLAR", 1000.0), ("BUY", "NEWPHARMA", 188.0)]
    buy = txns[1]
    assert buy.note == ("switch from ACMESOLAR; capped by the 10% position cap: "
                        "₹1,27,360 of the ₹2,27,000 proceeds stay in cash")
    p = s.load()
    assert p.cash_deployable == pytest.approx(273_000 + 227_000 - 99_640)   # 4,00,360
    newpharma = next(h for h in p.holdings if h.symbol == "NEWPHARMA")
    assert newpharma.adj_qty * 530.0 / 1_000_000 <= 0.10                   # 9.964%


def test_a_buy_that_would_push_its_sector_over_the_cap_is_reduced(tmp_path, monkeypatch):
    """Equity = BANKA 1,000 × 250 (2,50,000) + ACMESOLAR 1,000 × 100
    (1,00,000) + cash 6,50,000 = 10,00,000. NEWBANK is banking.
    Rooms: proceeds 1,00,000; position 1,00,000; banking 3,00,000 − 2,50,000
    = 50,000; cash 7,50,000 − 10,000. Tightest: the sector cap.
    floor(50,000 / 400) = 125 shares = 50,000; banking then 3,00,000 = 30.0%.
    """
    s = _store(tmp_path, [_h("BANKA", 1000, 250.0, "banking"),
                          _h("ACMESOLAR", 1000, 120.0, "power")], cash=650_000.0)
    _prices(monkeypatch, {"NEWBANK": 400.0})
    txns = _run(s, [_switch("ACMESOLAR", "NEWBANK", 100.0)],
                {"BANKA": 250.0, "ACMESOLAR": 100.0},
                ideas=[_idea("NEWBANK", 380.0, 420.0, 350.0, sector="banking")])

    assert _sides(txns) == [("SELL", "ACMESOLAR", 1000.0), ("BUY", "NEWBANK", 125.0)]
    assert txns[1].note == ("switch from ACMESOLAR; capped by the 30% cap on banking: "
                            "₹50,000 of the ₹1,00,000 proceeds stay in cash")
    p = s.load()
    banking = sum(h.adj_qty * {"BANKA": 250.0, "NEWBANK": 400.0}[h.symbol]
                  for h in p.holdings if h.sector == "banking")
    assert banking == pytest.approx(300_000.0)
    assert p.cash_deployable == pytest.approx(650_000 + 100_000 - 50_000)


def test_a_sector_buy_under_one_share_is_skipped_and_the_sell_says_why(tmp_path, monkeypatch):
    """BANKA 1,000 × 299.80 = 2,99,800; ACMESOLAR 1,00,000; cash 6,00,200;
    equity 10,00,000. Banking room 3,00,000 − 2,99,800 = 200 < one share at
    400, so nothing is bought and all 1,00,000 of proceeds stay in cash."""
    s = _store(tmp_path, [_h("BANKA", 1000, 299.80, "banking"),
                          _h("ACMESOLAR", 1000, 120.0, "power")], cash=600_200.0)
    _prices(monkeypatch, {"NEWBANK": 400.0})
    txns = _run(s, [_switch("ACMESOLAR", "NEWBANK", 100.0)],
                {"BANKA": 299.80, "ACMESOLAR": 100.0},
                ideas=[_idea("NEWBANK", 380.0, 420.0, 350.0, sector="banking")])

    assert _sides(txns) == [("SELL", "ACMESOLAR", 1000.0)]
    assert txns[0].note == ("exit_full; buy leg skipped: NEWBANK: the 30% cap on banking "
                            "leaves room for less than one share at ₹400; "
                            "₹1,00,000 stays in cash")
    assert ap.switch_skip_reason(txns[0].note).startswith("NEWBANK: the 30% cap on banking")
    assert s.load().cash_deployable == pytest.approx(700_200.0)


def test_an_add_into_a_full_sector_is_skipped_and_logged(tmp_path, monkeypatch, caplog):
    """BANKA 2,50,000 + BANKB 50,000 (both banking) + cash 7,00,000 =
    10,00,000. BANKB is 5%, so the position cap leaves 50,000 of room, but
    banking is at 30.0% already: BANKB's tranche (12,500) has no sector room.
    No transaction; the reason is logged as every ADD skip is."""
    s = _store(tmp_path, [_h("BANKA", 1000, 250.0, "banking"),
                          _h("BANKB", 500, 100.0, "banking")], cash=700_000.0)
    with caplog.at_level(logging.INFO, logger="core.portfolio.autopilot"):
        txns = _run(s, [_add("BANKB", 100.0)], {"BANKA": 250.0, "BANKB": 100.0})
    assert txns == []
    assert "ADD BANKB skipped: the 30% cap on banking leaves room for less than one share" \
        in caplog.text


def test_the_cash_floor_is_kept(tmp_path, monkeypatch):
    """ACME 10 × 110 = 1,100 is switched; cash 9,500, below the floor
    already. Equity 10,600. Rooms: proceeds 1,100; position 1,060; realty
    3,180; cash 9,500 + 1,100 − 10,000 = 600. floor(600 / 200) = 3 shares;
    cash ends at exactly 10,000; 1,100 − 600 = 500 left."""
    s = _store(tmp_path, [_h("ACME", 10, 125.0, "power")], cash=9_500.0)
    _prices(monkeypatch, {"NEWCO": 200.0})
    txns = _run(s, [_switch("ACME", "NEWCO", 110.0)], {"ACME": 110.0},
                ideas=[_idea("NEWCO", 190.0, 210.0, 170.0, sector="realty")])
    assert _sides(txns) == [("SELL", "ACME", 10.0), ("BUY", "NEWCO", 3.0)]
    assert txns[1].note == ("switch from ACME; capped by the ₹10,000 cash floor: "
                            "₹500 of the ₹1,100 proceeds stay in cash")
    assert s.load().cash_deployable == pytest.approx(10_000.0)


def test_under_one_share_after_the_floor_is_skipped(tmp_path, monkeypatch):
    """Cash 9,050 + 1,100 − 10,000 = 150 of room, under one share at 200."""
    s = _store(tmp_path, [_h("ACME", 10, 125.0, "power")], cash=9_050.0)
    _prices(monkeypatch, {"NEWCO": 200.0})
    txns = _run(s, [_switch("ACME", "NEWCO", 110.0)], {"ACME": 110.0},
                ideas=[_idea("NEWCO", 190.0, 210.0, 170.0, sector="realty")])
    assert _sides(txns) == [("SELL", "ACME", 10.0)]
    assert "buy leg skipped: NEWCO: the ₹10,000 cash floor leaves room for less than " \
           "one share at ₹200; ₹1,100 stays in cash" in txns[0].note
    assert s.load().cash_deployable == pytest.approx(10_150.0)


def test_add_keeps_todays_behaviour_when_no_cap_binds(tmp_path):
    """Characterization. MARUTI 100 × 100 = 10,000; PADDING 50 × 4,000 =
    2,00,000 (pharma); cash 1,00,000; equity 3,10,000. Tranche 25% × 10,000
    = 2,500; rooms: position 31,000 − 10,000; automobile 93,000 − 10,000;
    cash 90,000. The tranche binds, as it did before SA-050: 25 shares, the
    note unchanged."""
    s = _store(tmp_path, [_h("MARUTI", 100, 100.0, "automobile"),
                          _h("PADDING", 50, 4000.0, "pharma")], cash=100_000.0)
    txns = _run(s, [_add("MARUTI", 100.0)], {"MARUTI": 100.0, "PADDING": 4000.0})
    assert _sides(txns) == [("BUY", "MARUTI", 25.0)]
    assert txns[0].note == "add_tranche"
    assert s.load().cash_deployable == pytest.approx(97_500.0)


def test_an_add_is_trimmed_to_the_position_cap_and_says_so(tmp_path):
    """MARUTI 90 × 100 = 9,000 (9%); PADDING 10 × 4,000 = 40,000; cash
    51,000; equity 1,00,000. Tranche 2,250; position room 10,000 − 9,000 =
    1,000 → 10 shares; MARUTI ends at exactly 10%; 1,250 of the tranche left."""
    s = _store(tmp_path, [_h("MARUTI", 90, 100.0, "automobile"),
                          _h("PADDING", 10, 4000.0, "pharma")], cash=51_000.0)
    txns = _run(s, [_add("MARUTI", 100.0)], {"MARUTI": 100.0, "PADDING": 4000.0})
    assert _sides(txns) == [("BUY", "MARUTI", 10.0)]
    assert txns[0].note == ("add_tranche; capped by the 10% position cap: "
                            "₹1,250 of the ₹2,250 tranche stay in cash")


# ---------------------------------------------------------------------------
# The production baseline (product review section 11, 11 Oct)
# ---------------------------------------------------------------------------

class _NoArtifacts:
    def __init__(self, *a, **k):
        pass

    def cycle_id_for(self, d):
        return "X_2026-10"

    def load_envelope(self, cid):
        return None

    def load_feedback_log(self, cid):
        return None


def _oct11():
    """FEDERALBNK 406 at ₹330, WELCORP 21 at ₹2,640.40, cash ₹8,09,297."""
    from backend.shared.schemas.portfolio import Portfolio
    holdings = [_h("FEDERALBNK", 406, 355.44, "banking"),
                _h("WELCORP", 21, 2553.60, "capital_goods")]
    return Portfolio(user_id="u", holdings=holdings, cash_deployable=809_297.0,
                     autopilot=True), {"FEDERALBNK": 330.0, "WELCORP": 2640.40}


def test_oct11_weights_are_shares_of_total_equity_and_unlock_add():
    """Equity = 406 × 330 (1,33,980) + 21 × 2,640.40 (55,448.40) + 8,09,297
    = 9,98,725.40. FEDERALBNK 1,33,980 / 9,98,725.40 = 13.42%; WELCORP
    55,448.40 / 9,98,725.40 = 5.55%. (Before SA-050 the advisor divided by the
    holdings' cost, 1,44,308.64 + 53,625.60: 72.9% and 27.1%, so neither could
    ADD and FEDERALBNK carried SECTOR_CONCENTRATION_HIGH.)"""
    portfolio, marks = _oct11()
    sig = {h.symbol: build_signals(h, portfolio, D, _NoArtifacts(), {"events": {}},
                                   marks[h.symbol], marks=marks)
           for h in portfolio.holdings}
    equity = 133_980 + 55_448.40 + 809_297
    assert sig["FEDERALBNK"].position_weight_pct == pytest.approx(133_980 / equity * 100)
    assert sig["WELCORP"].position_weight_pct == pytest.approx(55_448.40 / equity * 100)
    assert sig["FEDERALBNK"].sector_weight_pct == pytest.approx(133_980 / equity * 100)
    assert round(sig["FEDERALBNK"].position_weight_pct, 1) == 13.4
    assert round(sig["WELCORP"].position_weight_pct, 1) == 5.6

    healthy = dict(envelope_direction="UP", direction_accuracy_7d=0.8, confidence=0.6)
    welcorp = decide(sig["WELCORP"].model_copy(update=healthy), portfolio.holdings[1],
                     "balanced")
    federal = decide(sig["FEDERALBNK"].model_copy(update=healthy), portfolio.holdings[0],
                     "balanced")
    assert welcorp.verdict == "ADD"
    assert federal.verdict == "HOLD"
    assert federal.notes == ["POSITION_LARGE"]         # one holding over 10%, no sector note
    assert "SECTOR_CONCENTRATION_HIGH" not in welcorp.notes + federal.notes


def test_oct11_welcorp_add_executes_through_the_shared_rule(tmp_path):
    """Tranche 25% × 55,448.40 = 13,862.10 → floor(13,862.10 / 2,640.40) = 5
    shares (13,202). Position room 99,872.54 − 55,448.40 = 44,424.14 and
    capital_goods room 2,99,617.62 − 55,448.40 do not bind."""
    portfolio, marks = _oct11()
    s = _store(tmp_path, portfolio.holdings, cash=809_297.0)
    txns = _run(s, [_add("WELCORP", 2640.40)], dict(marks))
    assert _sides(txns) == [("BUY", "WELCORP", 5.0)]
    assert txns[0].note == "add_tranche"


def test_the_welcorp_switch_34pct_above_its_band_is_not_bought(tmp_path, monkeypatch):
    """WELCORP was shelved with the band ₹1,817–₹1,911 and bought by a SWITCH
    at ₹2,553.60: 2,553.60 / 1,911 − 1 = 33.6% above. The buy is skipped;
    the SELL records the reason and that its ₹1,00,000 stays in cash."""
    s = _store(tmp_path, [_h("ACMESOLAR", 100, 1200.0, "power")], cash=900_000.0)
    _prices(monkeypatch, {"WELCORP": 2553.60})
    txns = _run(s, [_switch("ACMESOLAR", "WELCORP", 1000.0)], {"ACMESOLAR": 1000.0},
                ideas=[_idea("WELCORP", 1817.0, 1911.0, 1700.0, sector="capital_goods")])
    assert _sides(txns) == [("SELL", "ACMESOLAR", 100.0)]
    assert txns[0].note == ("exit_full; buy leg skipped: WELCORP: 33.6% above entry band "
                            "(₹1,817–₹1,911); needs a fresh deep dive; "
                            "₹1,00,000 stays in cash")
    p = s.load()
    assert p.cash_deployable == pytest.approx(1_000_000.0)
    assert not any(h.symbol == "WELCORP" for h in p.holdings)


# ---------------------------------------------------------------------------
# The entry rule
# ---------------------------------------------------------------------------

BAND = _idea("WELCORP", 1817.0, 1911.0, 1700.0)


@pytest.mark.parametrize("price, allowed, note", [
    (1911.00, True, ""),                                       # top of the band
    (1911.50, False, "0.0% above entry band (₹1,817–₹1,911); needs a fresh deep dive"),
    (1817.00, True, ""),                                       # bottom of the band
    # 1 − 1,750 / 1,817 = 3.69%
    (1750.00, True, "3.7% below entry band (₹1,817–₹1,911): cheaper than planned"),
    (1700.00, False, "at or below its invalidation level ₹1,700; "
                     "the idea's case no longer holds"),
    (1650.00, False, "at or below its invalidation level ₹1,700; "
                     "the idea's case no longer holds"),
])
def test_entry_check_against_the_band(price, allowed, note):
    assert sizing.entry_check(price, BAND) == (allowed, note)


def test_a_destination_without_a_band_is_refused():
    assert sizing.entry_check(100.0, None)[0] is False
    assert sizing.entry_check(100.0, _idea("X", 0.0, 0.0, 0.0)) == (
        False, "no entry band on record; needs a fresh deep dive")


def test_a_below_band_buy_says_it_was_cheaper_than_planned(tmp_path, monkeypatch):
    s = _store(tmp_path, [_h("ACMESOLAR", 100, 1200.0, "power")], cash=900_000.0)
    _prices(monkeypatch, {"WELCORP": 1750.0})
    txns = _run(s, [_switch("ACMESOLAR", "WELCORP", 1000.0)], {"ACMESOLAR": 1000.0},
                ideas=[_idea("WELCORP", 1817.0, 1911.0, 1700.0, sector="capital_goods")])
    # proceeds 1,00,000 = the 10% room (tie: the request wins, no cap note);
    # floor(1,00,000 / 1,750) = 57 shares
    assert _sides(txns) == [("SELL", "ACMESOLAR", 100.0), ("BUY", "WELCORP", 57.0)]
    assert txns[1].note == ("switch from ACMESOLAR; 3.7% below entry band "
                            "(₹1,817–₹1,911): cheaper than planned")


def test_a_destination_missing_from_the_shelf_is_not_bought(tmp_path, monkeypatch):
    s = _store(tmp_path, [_h("ACME", 10, 125.0, "power")], cash=20_000.0)
    _prices(monkeypatch, {"NEWCO": 200.0})
    txns = _run(s, [_switch("ACME", "NEWCO", 110.0)], {"ACME": 110.0},
                sectors={"NEWCO": "realty"})
    assert _sides(txns) == [("SELL", "ACME", 10.0)]
    assert "not an active shelf idea with an entry band" in txns[0].note


# ---------------------------------------------------------------------------
# Property: no autopilot buy breaches a cap, the floor or its band
# ---------------------------------------------------------------------------

SECTORS = ["banking", "pharma", "power", "it_sector"]


def _equity(holdings, cash, marks):
    return sum(h.adj_qty * marks.get(h.symbol, h.adj_avg_price) for h in holdings) + cash


def test_property_random_portfolios_never_breach_caps_floor_or_band(tmp_path, monkeypatch):
    """300 seeded random portfolios and advice days. After each run, checked
    with this test's own arithmetic:
      - every symbol the autopilot bought is at most 10% of total equity, and
        its sector at most 30%;
      - when anything was bought, cash is at or above the floor;
      - every buy that opened a position has a shelf idea, and its price is at
        or below entry_high and above invalidation_level;
      - total equity at the run's marks falls by exactly the run's trading
        costs (sales and buys happen at the marks; cash is rounded to the
        paisa), and every trade's costs are positive.
    The caps and the floor are checked after those costs: the configured
    rates are on (SA-048).
    The counters prove the cases were exercised, not vacuously true."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", CONFIGURED_COSTS)
    floor = 10_000.0
    seen = {"buys": 0, "capped": 0, "band_skips": 0, "new_positions": 0}
    for seed in range(300):
        rng = random.Random(seed)
        holdings, marks = [], {}
        for i in range(rng.randint(1, 6)):
            cost = rng.uniform(50, 3000)
            h = _h(f"H{i}", float(rng.randint(1, 2000)), round(cost, 2), rng.choice(SECTORS))
            holdings.append(h)
            marks[h.symbol] = round(cost * rng.uniform(0.6, 1.5), 2)
        cash = round(rng.uniform(0, 1_500_000), 2)
        prices, ideas, advice = {}, [], []
        for h in holdings:
            kind = rng.choice(["HOLD", "ADD", "ADD", "SWITCH", "SWITCH", "EXIT", "TRIM"])
            if kind == "ADD":
                advice.append(_add(h.symbol, marks[h.symbol], confidence=rng.random()))
            elif kind == "SWITCH":
                cand = f"C{h.symbol}"
                prices[cand] = round(rng.uniform(50, 3000), 2)
                hi = round(prices[cand] * rng.uniform(0.8, 1.2), 2)
                lo = round(hi * 0.95, 2)
                inval = round(lo * rng.uniform(0.85, 1.0), 2)
                if rng.random() < 0.85:                       # some have no shelf idea
                    ideas.append(_idea(cand, lo, hi, inval, sector=rng.choice(SECTORS)))
                advice.append(_switch(h.symbol, cand, marks[h.symbol]))
            elif kind in ("EXIT", "TRIM"):
                advice.append(AdviceRecord(
                    date=D.isoformat(), user_id="u", symbol=h.symbol, verdict=kind,
                    close=marks[h.symbol], unrealised_pnl_pct=0.0, stop_pct=12.0,
                    rationale_hash=f"{kind}{h.symbol}"))
        _prices(monkeypatch, prices)
        s = _store(tmp_path, holdings, cash, name=f"u{seed}")
        before = s.load()
        closes = dict(marks)
        txns = _run(s, advice, closes, ideas=ideas,
                    sectors={i.symbol: i.sector for i in ideas})
        after = s.load()
        run_marks = {**closes, **prices}
        eq_before = _equity(before.holdings, before.cash_deployable, run_marks)
        eq_after = _equity(after.holdings, after.cash_deployable, run_marks)
        charged = sum(t.costs.total for t in txns)
        assert all(t.costs.total > 0 for t in txns), seed
        assert eq_after == pytest.approx(eq_before - charged, abs=0.01 * (len(txns) + 1)), seed

        held_before = {h.symbol for h in before.holdings}
        idea_of = {i.symbol: i for i in ideas}
        sector_of = {h.symbol: h.sector for h in after.holdings}
        buys = [t for t in txns if t.side == "BUY"]
        for t in buys:
            assert t.qty >= 1 and t.qty == int(t.qty), seed
            pos = sum(h.adj_qty * run_marks[h.symbol] for h in after.holdings
                      if h.symbol == t.symbol)
            sec = sum(h.adj_qty * run_marks.get(h.symbol, h.adj_avg_price)
                      for h in after.holdings if h.sector == sector_of[t.symbol])
            assert pos <= 0.10 * eq_after + 1e-6, (seed, t.symbol, pos, eq_after)
            assert sec <= 0.30 * eq_after + 1e-6, (seed, t.symbol, sec, eq_after)
            if t.symbol not in held_before:
                idea = idea_of[t.symbol]
                assert idea.invalidation_level < t.price <= idea.entry_high, (seed, t.symbol)
                seen["new_positions"] += 1
            seen["capped"] += "capped by" in t.note
        if buys:
            assert after.cash_deployable >= floor - 0.005, seed
        seen["buys"] += len(buys)
        seen["band_skips"] += sum("entry band" in t.note or "invalidation" in t.note
                                  for t in txns if t.side == "SELL")
    assert seen["buys"] > 100 and seen["new_positions"] > 30
    assert seen["capped"] > 20 and seen["band_skips"] > 20, seen


# ---------------------------------------------------------------------------
# End to end: a switch through run_post_review_pipeline
# ---------------------------------------------------------------------------

def _pipeline_day(tmp_path, monkeypatch, cand_price, holdings=None, cash=273_000.0,
                  prices=None):
    """The ₹2.27 L switch from the first test, through the real advisor,
    pipeline and autopilot. ACMESOLAR cost 260, close 227: −12.7% against the
    12% stop (mid-cap floor with no ATR), so EXIT; NEWPHARMA (pharma, 0% of
    equity, conviction 0.9 against confidence 0.5) is the SWITCH destination."""
    import core.delivery.alerts as alerts_mod
    import core.delivery.channels as channels_mod
    import core.portfolio.pipeline as pipeline

    monkeypatch.setenv("ATLAS_ENABLED", "false")
    holdings = holdings or [_h("ACMESOLAR", 1000, 260.0, "power"),
                            _h("ITCO", 500, 1000.0, "it_sector")]
    store = _store(tmp_path, holdings, cash=cash)
    prices = prices or {"ACMESOLAR": 227.0, "ITCO": 1000.0, "NEWPHARMA": cand_price}
    quote = lambda sym, d: (SessionClose(prices[sym], d, "agree"), d)  # noqa: E731
    monkeypatch.setattr(pipeline, "session_close", quote)
    monkeypatch.setattr(ap, "session_close", quote)
    monkeypatch.setattr(pipeline.settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"))
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: {"applied": 0})
    monkeypatch.setattr(pipeline, "refresh_events_calendar", lambda syms: {"events": {}})
    monkeypatch.setattr(pipeline, "get_price_history", lambda t, years=1: None)
    monkeypatch.setattr(pipeline, "narrate", lambda rec, sig: "n")
    monkeypatch.setattr(pipeline, "VerdictStore", _NoArtifacts)
    monkeypatch.setattr("core.discovery.shelf.ShelfStore.load", lambda self: Shelf(
        ideas=[_idea("NEWPHARMA", 500.0, 540.0, 470.0)]))
    emitted = []
    monkeypatch.setattr(alerts_mod, "emit_alerts",
                        lambda events, **k: emitted.extend(events) or {"emitted": 0})
    monkeypatch.setattr(channels_mod, "deliver", lambda *a, **k: {"delivered": False})

    result = pipeline.run_post_review_pipeline(D)
    assert result["status"] == "completed" and result["advice"] == len(holdings)
    advice = {a.symbol: a for a in store.load_advice()}
    return advice, store.load_transactions(), emitted


@pytest.mark.parametrize("mode", ["record", "enforce"])
def test_pipeline_switch_is_capped_end_to_end(tmp_path, monkeypatch, gate_mode, mode):
    gate_mode(mode)
    advice, txns, _ = _pipeline_day(tmp_path, monkeypatch, cand_price=530.0)
    assert (advice["ACMESOLAR"].verdict, advice["ACMESOLAR"].switch_candidate) == \
        ("SWITCH", "NEWPHARMA")
    # ITCO is 5,00,000 of 10,00,000: one position over 10%, its sector over 30%
    assert {"POSITION_LARGE", "SECTOR_CONCENTRATION_HIGH"} <= set(advice["ITCO"].notes)
    assert _sides(txns) == [("SELL", "ACMESOLAR", 1000.0), ("BUY", "NEWPHARMA", 188.0)]
    assert txns[1].note == ("switch from ACMESOLAR; capped by the 10% position cap: "
                            "₹1,27,360 of the ₹2,27,000 proceeds stay in cash")


def test_pipeline_weights_use_every_holdings_close(tmp_path, monkeypatch, gate_mode):
    """BIG 100 at cost 2,000 now closes at 1,000 (1,00,000); SMALL 100 at
    1,040 (1,04,000); cash 7,96,000; equity 10,00,000, so SMALL is 10.4%,
    over the cap. Valuing BIG at its cost instead would make equity 11,00,000
    and SMALL 9.45%, no note: the weights need every holding's own close."""
    gate_mode("record")
    advice, _, _ = _pipeline_day(
        tmp_path, monkeypatch, cand_price=530.0, cash=796_000.0,
        holdings=[_h("BIG", 100, 2000.0, "power"), _h("SMALL", 100, 1040.0, "pharma")],
        prices={"BIG": 1000.0, "SMALL": 1040.0, "NEWPHARMA": 530.0})
    assert advice["SMALL"].notes == ["POSITION_LARGE"]
    assert advice["BIG"].verdict == "EXIT"          # pharma is not underweight: no switch


def test_the_switch_underweight_test_reads_market_shares(tmp_path, monkeypatch, gate_mode):
    """ACMESOLAR 1,000 at cost 100 now closes at 50 (stop breached): power
    is ₹50,000. PHARMACO 600 at 100: pharma is ₹60,000. NEWPHARMA (pharma) is
    a destination only if pharma is strictly below power. At market it is not
    (60,000 against 50,000), so the advisor exits without a switch; at cost
    (60,000 against 1,00,000) it would have bought more pharma."""
    gate_mode("record")
    advice, txns, _ = _pipeline_day(
        tmp_path, monkeypatch, cand_price=530.0, cash=200_000.0,
        holdings=[_h("ACMESOLAR", 1000, 100.0, "power"),
                  _h("PHARMACO", 600, 100.0, "pharma")],
        prices={"ACMESOLAR": 50.0, "PHARMACO": 100.0, "NEWPHARMA": 530.0})
    assert (advice["ACMESOLAR"].verdict, advice["ACMESOLAR"].switch_candidate) == ("EXIT", "")
    assert not any(t.side == "BUY" for t in txns)


@pytest.mark.parametrize("position, sector, notes", [
    (10.0, 30.0, []),                                   # at a cap is allowed, so no note
    (10.01, 30.0, ["POSITION_LARGE"]),
    (5.0, 30.01, ["SECTOR_CONCENTRATION_HIGH"]),
])
def test_the_notes_mark_weights_over_the_caps(position, sector, notes):
    from core.portfolio.advisor import AdvisorSignals
    sig = AdvisorSignals(symbol="X", sector="banking", close=100.0, atr_stop_pct=12.0,
                         unrealised_pnl_pct=0.0, holding_age_days=30,
                         position_weight_pct=position, sector_weight_pct=sector)
    assert decide(sig, _h("X", 1, 100.0, "banking"), "balanced").notes == notes


def test_pipeline_switch_above_band_alerts_with_the_reason(tmp_path, monkeypatch, gate_mode):
    """800 / 540 − 1 = 48.1% above the band: sold, not bought, and the
    switch_buy_skipped alert names why."""
    gate_mode("record")
    _, txns, emitted = _pipeline_day(tmp_path, monkeypatch, cand_price=800.0)
    assert _sides(txns) == [("SELL", "ACMESOLAR", 1000.0)]
    skipped = [e for e in emitted if e.kind == "switch_buy_skipped"]
    assert len(skipped) == 1 and skipped[0].symbol == "NEWPHARMA"
    assert skipped[0].message == (
        "SWITCH ACMESOLAR→NEWPHARMA: sold but the buy leg was skipped: NEWPHARMA: "
        "48.1% above entry band (₹500–₹540); needs a fresh deep dive; "
        "₹2,27,000 stays in cash")


# ---------------------------------------------------------------------------
# The weekly review reads the same weights
# ---------------------------------------------------------------------------

def test_weekly_allocation_is_a_share_of_total_equity(tmp_path, monkeypatch):
    """The 11 Oct shape: banking 13.415%, capital_goods 5.552%, cash
    8,09,297 / 9,98,725.40 = 81.03%, stored once at one decimal (13.4, 5.6,
    81.0; rounding twice showed 5.552 as 5.5). No sector is over 30%, so
    nothing is flagged (before SA-050: banking 70.7% of the holdings'
    value, flagged)."""
    import core.delivery.weekly as wk
    portfolio, marks = _oct11()
    store = _store(tmp_path, portfolio.holdings, cash=809_297.0)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: dict(marks))
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    monkeypatch.setattr(wk, "_safe_scorecard", lambda *a, **k: None)
    review = wk.build_weekly_review("u", D, store=store)
    alloc = {a["sector"]: a["weight_pct"] for a in review["allocation"]}
    assert alloc == {"banking": 13.4, "capital_goods": 5.6}
    assert review["cash_pct"] == 81.0
    assert review["concentration_flags"] == []
    assert "cash: 81.0%" in wk.render_weekly_text(review)
