"""SA-048 — realistic trading costs and tax in paper P&L: invariant tests.

Every expected figure is worked by hand in the comments from the rates below,
never read back from core/portfolio/costs.py. The rates are an NSE equity
delivery trade at a zero-brokerage broker, as checked on 2026-10-31 (sources
in config.yaml, `portfolio.costs` and `portfolio.tax`):

- STT 0.1% of the buy and of the sell value, value and tax to the rupee;
- stamp duty 0.015% of the buy value;
- NSE transaction charge 0.00307% and SEBI fee 0.0001% of each side;
- GST 18% of brokerage + NSE charge + SEBI fee (each rounded to the paisa);
- DP charge ₹15.34 per scrip sold, GST included; brokerage 0.

Tax: short-term (held 12 months or less) 20%, long-term 12.5% above
₹1,25,000 a financial year, cess 4% of the tax. STT is not deductible from a
gain; the other charges are.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.api.routes.portfolio_api as papi
from backend.shared.schemas.portfolio import AdviceRecord, Holding, TradeCosts, TransactionRecord
from core.config import settings
from core.portfolio import autopilot as ap
from core.portfolio import costs
from core.portfolio import results as R
from core.portfolio.store import PortfolioStore
from tests.unit.test_decision_gate_portfolio_sa003 import gate_mode  # noqa: F401 — fixture

D = date(2026, 9, 25)                          # a Friday
CHECKED = {"as_of": "2026-10-31", "brokerage_pct": 0.0, "brokerage_max_inr": 0.0,
           "stt_pct": 0.1, "stamp_duty_buy_pct": 0.015, "exchange_fee_pct": 0.00307,
           "sebi_fee_pct": 0.0001, "gst_pct": 18.0, "dp_charge_inr": 15.34}
CHECKED_TAX = {"as_of": "2026-10-31", "short_term_pct": 20.0, "long_term_pct": 12.5,
               "long_term_exemption_inr": 125000, "long_term_after_months": 12,
               "cess_pct": 4.0}
NONE_CHARGED = TradeCosts(rates_as_of="test")   # a row recorded with no charges


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    """The checked rates, a frozen executor clock, no promotion writes."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", dict(CHECKED))
    monkeypatch.setattr(settings, "PORTFOLIO_TAX", dict(CHECKED_TAX))
    monkeypatch.setattr(settings, "ADVISOR_MAX_POSITION_PCT", 10.0)
    monkeypatch.setattr(settings, "ADVISOR_MAX_SECTOR_PCT", 30.0)
    monkeypatch.setattr(settings, "AUTOPILOT_MIN_CASH_FLOOR", 10000.0)
    monkeypatch.setattr(ap, "_today_ist", lambda: D)
    monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})


class _FlatNifty:
    def preload(self, start, end):
        return True

    def close_on(self, d):
        return 100.0


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(papi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(papi, "promote_symbol", lambda *a, **k: {"status": "test"})
    monkeypatch.setattr(papi, "demote_symbol", lambda *a, **k: False)
    monkeypatch.setattr(papi, "_benchmark", _FlatNifty)
    monkeypatch.setattr(papi, "_stock_closes", lambda: (lambda symbol, d: 100.0))
    app = FastAPI()
    app.include_router(papi.router)
    return TestClient(app)


def _account(base, cash, holdings=(), capital_in=None, user="primary"):
    s = PortfolioStore(user_id=user, base_dir=str(base))
    p = s.load()
    p.holdings = list(holdings)
    p.cash_deployable, p.autopilot = cash, True
    p.capital_in = capital_in if capital_in is not None else cash + sum(
        h.adj_qty * h.adj_avg_price for h in holdings)
    s.save(p)
    return s


def _h(sym, qty, cost, sector="power", bought="2026-06-01"):
    return Holding(symbol=sym, sector=sector, qty=qty, avg_buy_price=cost,
                   adj_avg_price=cost, adj_qty=qty, buy_date=bought)


def _advice(sym, verdict, close, day=D, confidence=0.6):
    return AdviceRecord(date=day.isoformat(), user_id="primary", symbol=sym, verdict=verdict,
                        close=close, unrealised_pnl_pct=0.0, stop_pct=12.0,
                        confidence=confidence, rationale_hash=f"{verdict}{sym}{day}")


def _row(day, sym, side, qty, price, *, after, cost_basis=None, realized=0.0,
         charges=NONE_CHARGED, tid=None):
    value = round(qty * price, 2)
    return TransactionRecord(
        txn_id=tid or f"{sym}-{side}-{day}", date=day, ts=f"{day}T10:00:00+00:00",
        user_id="primary", symbol=sym, side=side, qty=qty, price=price, value=value,
        cash_before=0.0, cash_after=0.0, holding_qty_after=after,
        realized_pnl=realized, cost_basis=cost_basis, costs=charges)


# ---------------------------------------------------------------------------
# One charge at a time, and the ACMESOLAR round trip
# ---------------------------------------------------------------------------

def test_each_charge_on_the_acmesolar_buy_and_sale_by_hand():
    """509 at ₹372.88 = ₹1,89,795.92 bought; 509 at ₹446.65 = ₹2,27,344.85 sold.

    Buy:  STT 0.1% of ₹1,89,796 = 189.796 -> ₹190; stamp 0.015% = 28.4694 ->
          ₹28.47; NSE 0.00307% = 5.8267 -> ₹5.83; SEBI 0.0001% = 0.1898 ->
          ₹0.19; GST 18% of (0 + 5.83 + 0.19) = 1.0836 -> ₹1.08. ₹225.57.
    Sale: STT 0.1% of ₹2,27,345 = 227.345 -> ₹227; NSE 6.9795 -> ₹6.98; SEBI
          0.2273 -> ₹0.23; GST 18% of 7.21 = 1.2978 -> ₹1.30; DP ₹15.34. ₹250.85.
    Round trip ₹476.42 (the card's estimate: about ₹477)."""
    buy = costs.trade_costs("BUY", 189_795.92)
    sell = costs.trade_costs("SELL", 227_344.85)
    assert (buy.stt, buy.stamp_duty, buy.exchange_fee, buy.sebi_fee, buy.gst,
            buy.dp_charge, buy.brokerage) == (190.0, 28.47, 5.83, 0.19, 1.08, 0.0, 0.0)
    assert buy.total == pytest.approx(225.57, abs=1e-9)
    assert (sell.stt, sell.stamp_duty, sell.exchange_fee, sell.sebi_fee, sell.gst,
            sell.dp_charge, sell.brokerage) == (227.0, 0.0, 6.98, 0.23, 1.30, 15.34, 0.0)
    assert sell.total == pytest.approx(250.85, abs=1e-9)
    assert buy.rates_as_of == sell.rates_as_of == "2026-10-31"
    assert not buy.estimated and not sell.estimated


def test_a_percentage_broker_is_capped_and_its_brokerage_carries_gst(monkeypatch):
    """0.5% brokerage capped at ₹20 an order on ₹1,00,000: 500 -> ₹20. GST 18%
    of (20 + NSE 3.07 + SEBI 0.10) = 18% of 23.17 = 4.1706 -> ₹4.17. STT ₹100,
    stamp ₹15. ₹142.34."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS",
                        {**CHECKED, "brokerage_pct": 0.5, "brokerage_max_inr": 20.0})
    c = costs.trade_costs("BUY", 100_000.0)
    assert (c.brokerage, c.exchange_fee, c.sebi_fee, c.gst, c.stt, c.stamp_duty) == (
        20.0, 3.07, 0.10, 4.17, 100.0, 15.0)
    assert c.total == pytest.approx(142.34, abs=1e-9)


def test_stt_rounds_value_and_tax_to_the_rupee():
    """₹499.40 -> value ₹499 -> STT 0.499 -> ₹0; ₹500.00 -> 0.5 -> ₹1 (half up);
    ₹1,499.60 -> ₹1,500 -> 1.5 -> ₹2."""
    assert [costs.trade_costs("BUY", v).stt for v in (499.40, 500.0, 1499.60)] == [0.0, 1.0, 2.0]


def test_the_acmesolar_round_trip_through_the_app_records_and_reconciles(client, tmp_path):
    """Added by hand at ₹372.88 on 3 Aug, then EXITed by the autopilot at ₹446.65.

    Add: no cash moves; capital_in rises by ₹1,89,795.92 + ₹225.57.
    Exit: cash rises by ₹2,27,344.85 − ₹250.85 = ₹2,27,094.00.
    Realized (before costs) 509 × 73.77 = ₹37,548.93; net of costs
    37,548.93 − 476.42 = ₹37,072.51, which is also equity − capital_in.
    Tax (short-term, FY 2026-27): gain = 2,27,344.85 − (250.85 − 227 STT) −
    1,89,795.92 − (225.57 − 190 STT) = ₹37,489.51; 20% = 7,497.902 ->
    ₹7,497.90; cess 4% = 299.916 -> ₹299.92; ₹7,797.82."""
    s = _account(tmp_path, cash=100_000.0)
    r = client.post("/portfolio/holdings", json={
        "symbol": "ACMESOLAR", "sector": "power", "qty": 509,
        "buy_date": "2026-08-03", "price": 372.88})
    assert r.status_code == 200 and r.json()["transaction"]["costs"]["total"] == 225.57
    p = s.load()
    assert p.cash_deployable == 100_000.0
    assert p.capital_in == pytest.approx(100_000.0 + 189_795.92 + 225.57, abs=1e-6)

    txns = ap.execute_advice(s, s.load(), [_advice("ACMESOLAR", "EXIT", 446.65)],
                             {"ACMESOLAR": 446.65}, D)
    sell = txns[0]
    assert sell.costs.total == 250.85 and sell.realized_pnl == pytest.approx(37_548.93)
    assert sell.cash_before == 100_000.0
    assert sell.cash_after == pytest.approx(100_000.0 + 227_344.85 - 250.85, abs=1e-6)
    assert s.load().cash_deployable == pytest.approx(327_094.00, abs=1e-6)

    d = client.get("/portfolio/performance").json()
    assert d["realized_pnl"] == pytest.approx(37_548.93)      # keeps its meaning
    assert d["realized"] == {"gross": 37_548.93, "costs": 476.42,
                             "net_of_costs": 37_072.51, "estimated_costs": 0.0}
    assert d["costs"] == {"charged": 476.42, "estimated": 0.0, "on_open_positions": 0.0,
                          "rates_as_of": "2026-10-31"}
    assert d["total_equity"] - d["capital_in"] == pytest.approx(37_072.51, abs=0.005)
    assert d["unrealized_pnl"] == pytest.approx(0.0, abs=0.005)   # nothing held
    (year,) = d["tax_estimate"]["years"]
    assert year["year"] == "2026-27"
    assert year["short_term"] == {"gains": 37_489.51, "losses": 0.0}
    assert (year["tax"], year["cess"], year["total"]) == (7_497.90, 299.92, 7_797.82)
    assert d["tax_estimate"]["total"] == 7_797.82
    # In hand: 37,548.93 − 476.42 − 7,797.82 = ₹29,274.69 (card: about ₹29,660,
    # before the cess and with STT wrongly deducted).
    assert d["realized"]["net_of_costs"] - d["tax_estimate"]["total"] == pytest.approx(29_274.69)


def test_a_switch_spends_the_sale_net_of_its_costs_and_pays_the_buy_costs(tmp_path, monkeypatch):
    """OLD (100 at ₹100, 1% of a ₹10 L account) is SWITCHed into NEW at ₹50.
    Sale ₹10,000: STT ₹10, NSE ₹0.31, SEBI ₹0.01, GST 18% of 0.32 = ₹0.06,
    DP ₹15.34: ₹25.72, so ₹9,974.28 is asked for: floor(9,974.28 / 50) = 199
    shares (₹9,950). Buy ₹9,950: STT ₹10 (9.95 -> 10), stamp 1.4925 -> ₹1.49,
    NSE 0.3055 -> ₹0.31, SEBI 0.00995 -> ₹0.01, GST ₹0.06: ₹11.87.
    Cash 9,90,000 + 10,000 − 25.72 − 9,950 − 11.87 = ₹9,90,012.41."""
    from core.portfolio.pricing import SessionClose
    from backend.shared.schemas.discovery import ShelfIdea
    monkeypatch.setattr(ap, "session_close",
                        lambda sym, day: (SessionClose(50.0, day, "agree"), day))
    monkeypatch.setattr(ap, "symbol_identity_issue", lambda sym, session: "")
    idea = ShelfIdea(symbol="NEW", sector="it_sector", conviction=0.9, entry_low=45.0,
                     entry_high=55.0, invalidation_level=40.0, thesis="t", added=D.isoformat())
    s = _account(tmp_path, cash=990_000.0, holdings=[_h("OLD", 100, 100.0)])
    rec = _advice("OLD", "SWITCH", 100.0)
    rec.switch_candidate = "NEW"
    txns = ap.execute_advice(s, s.load(), [rec], {"OLD": 100.0}, D,
                             sector_lookup={"NEW": "it_sector"}, shelf_index={"NEW": idea})
    sell, buy = txns
    assert sell.costs.total == pytest.approx(25.72, abs=1e-9)
    assert buy.qty == 199 and buy.costs.total == pytest.approx(11.87, abs=1e-9)
    assert buy.cash_before == sell.cash_after
    assert s.load().cash_deployable == pytest.approx(990_012.41, abs=1e-6)


def test_the_227k_switch_through_the_pipeline_pays_its_costs_and_says_so(
        tmp_path, monkeypatch, gate_mode):
    """SA-050's ₹2.27 L switch (its _pipeline_day: ACMESOLAR 1,000 at ₹227,
    ITCO 500 at ₹1,000, ₹2,73,000 cash, NEWPHARMA at ₹530) on these rates.
    Sale ₹2,27,000: STT ₹227, NSE 6.9689 -> ₹6.97, SEBI 0.227 -> ₹0.23, GST
    18% of 7.20 = 1.296 -> ₹1.30, DP ₹15.34: ₹250.84. Cash ₹4,99,749.16 and
    equity ₹9,99,749.16, so the 10% cap is ₹99,974.92: 188 at ₹530 = ₹99,640.
    Their charges: STT 99.64 -> ₹100, stamp 14.946 -> ₹14.95, NSE 3.0589 ->
    ₹3.06, SEBI 0.0996 -> ₹0.10, GST 18% of 3.16 = 0.5688 -> ₹0.57: ₹118.68.
    After them the cap is 10% of ₹9,99,630.48 = ₹99,963.05, still above
    ₹99,640. Of the ₹2,26,749.16 proceeds, ₹1,27,109.16 stays; cash ends at
    4,99,749.16 − 99,640 − 118.68 = ₹3,99,990.48. The alerts say so."""
    from tests.unit.test_sizing_rule_sa050 import _pipeline_day
    reg = tmp_path / "instruments.yaml"
    reg.write_text("version: 1\ninstruments: {}\n", encoding="utf-8")
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(reg))
    gate_mode("record")
    _, txns, emitted = _pipeline_day(tmp_path, monkeypatch, cand_price=530.0)
    sell, buy = txns
    assert (sell.costs.total, buy.qty, buy.costs.total) == (250.84, 188.0, 118.68)
    assert buy.note == ("switch from ACMESOLAR; capped by the 10% position cap: "
                        "₹1,27,109 of the ₹2,26,749 proceeds stay in cash")
    assert buy.cash_after == pytest.approx(399_990.48, abs=1e-6)
    assert [e.message for e in emitted if e.kind == "autopilot_trade"] == [
        "SELL 1000 ACMESOLAR @ ₹227.00 (realized ₹-33,000.00 before costs); costs ₹250.84",
        "BUY 188 NEWPHARMA @ ₹530.00; costs ₹118.68"]


# ---------------------------------------------------------------------------
# Rates: from config, dated; a recorded trade never changes
# ---------------------------------------------------------------------------

def test_config_carries_every_rate_with_its_check_date():
    """Read config.yaml itself: each rate is there, dated, and is the rate this
    file's hand figures use (changing one is a reviewed edit of both)."""
    cfg = yaml.safe_load(Path(__file__).resolve().parents[2].joinpath("config.yaml")
                         .read_text(encoding="utf-8"))["portfolio"]
    assert cfg["costs"] == CHECKED
    assert cfg["tax"] == CHECKED_TAX
    for block in (cfg["costs"], cfg["tax"]):
        assert date.fromisoformat(block["as_of"]) <= date.today()


@pytest.mark.parametrize("block,key", [("PORTFOLIO_COSTS", "stt_pct"),
                                       ("PORTFOLIO_COSTS", "as_of"),
                                       ("PORTFOLIO_TAX", "cess_pct")])
def test_a_missing_rate_fails_loudly_and_trades_nothing(tmp_path, monkeypatch, block, key):
    """No rate never means no charge: the trade is refused and nothing is
    written."""
    rates = dict(CHECKED if block == "PORTFOLIO_COSTS" else CHECKED_TAX)
    del rates[key]
    monkeypatch.setattr(settings, block, rates)
    if block == "PORTFOLIO_TAX":
        with pytest.raises(ValueError, match=key):
            costs.tax_estimate([])
        return
    s = _account(tmp_path, cash=1_000.0, holdings=[_h("MARUTI", 10, 100.0)])
    before = s.load()
    with pytest.raises(ValueError, match=key):
        ap.execute_advice(s, s.load(), [_advice("MARUTI", "EXIT", 110.0)], {"MARUTI": 110.0}, D)
    assert s.load_transactions() == []
    assert s.load().model_dump() == before.model_dump()


def test_a_rate_change_never_changes_a_recorded_trade(tmp_path, monkeypatch):
    """A sale of 10 at ₹110 (₹1,100) pays ₹16.38 (STT ₹1, NSE ₹0.03, GST
    ₹0.01, DP ₹15.34). Doubling STT and raising the DP charge afterwards leaves
    that row, and every figure read from it, as recorded. A row from before
    costs were charged (220 sold, no costs) is estimated at the rates of the
    day: ₹15.35 before (STT 0.22 -> ₹0, NSE ₹0.01, DP ₹15.34), ₹20.01 after
    (STT 0.44 -> ₹0, NSE ₹0.01, DP ₹20.00)."""
    s = _account(tmp_path, cash=1_000.0, holdings=[_h("MARUTI", 10, 100.0)])
    old = _row("2026-07-13", "TCS", "SELL", 2, 110.0, after=0.0, realized=20.0,
               charges=None, tid="old")
    s.append_transaction(old)
    ap.execute_advice(s, s.load(), [_advice("MARUTI", "EXIT", 110.0)], {"MARUTI": 110.0}, D)
    before = costs.cost_summary(s.load_transactions())
    assert before["costs"] == {"charged": 16.38, "estimated": 15.35,
                               "on_open_positions": 0.0, "rates_as_of": "2026-10-31"}

    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", {
        **CHECKED, "stt_pct": 0.2, "dp_charge_inr": 20.0, "as_of": "2027-04-01"})
    rows = s.load_transactions()
    sale = next(t for t in rows if t.symbol == "MARUTI")
    assert costs.costs_of(sale).total == 16.38
    assert costs.costs_of(sale).rates_as_of == "2026-10-31"
    after = costs.cost_summary(rows)
    assert after["costs"]["charged"] == 16.38
    assert after["costs"]["estimated"] == 20.01
    assert costs.costs_of(next(t for t in rows if t.txn_id == "old")).rates_as_of == "2027-04-01"


def test_a_crash_after_the_ledger_write_never_charges_twice(tmp_path, monkeypatch):
    """The charges live on the trade's own row, so the txn_id dedupe that stops
    a re-run selling twice also stops it charging twice. A save that fails
    after the append leaves one recorded charge and cash untouched; the re-run
    skips the sale, so cash is never charged at all, let alone twice (the
    ledger is ahead of portfolio.json, flagged for reconciliation as before)."""
    s = _account(tmp_path, cash=1_000.0, holdings=[_h("MARUTI", 10, 100.0)])
    real_save = PortfolioStore.save

    def crash(self, p):
        raise OSError("disk full")

    monkeypatch.setattr(PortfolioStore, "save", crash)
    with pytest.raises(OSError):
        ap.execute_advice(s, s.load(), [_advice("MARUTI", "EXIT", 110.0)], {"MARUTI": 110.0}, D)
    monkeypatch.setattr(PortfolioStore, "save", real_save)
    assert [t.costs.total for t in s.load_transactions()] == [16.38]
    assert s.load().cash_deployable == 1_000.0

    assert ap.execute_advice(s, s.load(), [_advice("MARUTI", "EXIT", 110.0)],
                             {"MARUTI": 110.0}, D) == []
    assert [t.costs.total for t in s.load_transactions()] == [16.38]
    assert s.load().cash_deployable == 1_000.0


# ---------------------------------------------------------------------------
# Before SA-048: estimated, never zero
# ---------------------------------------------------------------------------

def test_a_trade_from_before_costs_reads_as_estimated_never_as_free(client, tmp_path):
    """The seed SELL (2 at ₹110, realized ₹20) has no costs: ₹15.35 estimated
    (STT ₹0, NSE ₹0.01, SEBI ₹0, GST ₹0, DP ₹15.34). A dividend has none. Those
    costs were never taken from cash, so they are listed apart, and unrealized
    P&L is unchanged: total 0 − realized 20 + charged 0 = −20."""
    s = _account(tmp_path, cash=10_000.0, holdings=[_h("MARUTI", 10, 100.0)],
                 capital_in=11_000.0)
    s.append_transaction(_row("2026-07-13", "MARUTI", "SELL", 2, 110.0, after=8.0,
                              realized=20.0, charges=None, tid="t1"))
    s.append_transaction(_row("2026-07-14", "MARUTI", "DIV", 0, 5.0, after=8.0,
                              charges=None, tid="d1"))
    s.append_value_point({"date": "2026-07-14", "market_value": 1000.0, "cash": 10_000.0,
                          "total_equity": 11_000.0, "capital_in": 11_000.0,
                          "day_change_pct": None})
    rows = client.get("/portfolio/transactions").json()["transactions"]
    by_id = {r["txn_id"]: r for r in rows}
    assert by_id["t1"]["costs"]["estimated"] is True
    assert by_id["t1"]["costs"]["total"] == 15.35 and by_id["t1"]["costs"]["dp_charge"] == 15.34
    assert by_id["d1"]["costs"] is None
    assert PortfolioStore(user_id="primary", base_dir=str(tmp_path)) \
        .load_transactions()[0].costs is None                 # the ledger is not rewritten

    d = client.get("/portfolio/performance").json()
    assert d["realized"] == {"gross": 20.0, "costs": 15.35, "net_of_costs": 4.65,
                             "estimated_costs": 15.35}
    assert d["costs"]["charged"] == 0.0 and d["costs"]["estimated"] == 15.35
    assert d["unrealized_pnl"] == pytest.approx(-20.0)


# ---------------------------------------------------------------------------
# Realized net of costs: a position's buy charges follow the shares sold
# ---------------------------------------------------------------------------

def test_buy_charges_follow_the_shares_sold_across_a_trim_and_a_split():
    """Bought 100 (charges ₹40) and 50 more (₹20): ₹60 pooled on 150 shares.
    A 2:1 split makes it 300. TRIM 75 of 300 carries 75/300 of ₹60 = ₹15; the
    EXIT of the last 225 carries the remaining ₹45. Each sale's own charges are
    ₹10. Net: 500 − 10 − 15 = ₹475 and 900 − 10 − 45 = ₹845."""
    rows = [
        _row("2026-05-04", "X", "BUY", 100, 10.0, after=100, charges=TradeCosts(total=40.0)),
        _row("2026-05-05", "X", "BUY", 50, 10.0, after=150, charges=TradeCosts(total=20.0)),
        _row("2026-06-01", "X", "SELL", 75, 12.0, after=225, cost_basis=5.0, realized=500.0,
             charges=TradeCosts(total=10.0)),
        _row("2026-06-02", "X", "SELL", 225, 9.0, after=0, cost_basis=5.0, realized=900.0,
             charges=TradeCosts(total=10.0)),
    ]
    sales, still_open = costs.sale_costs(rows)
    assert [(s.own, s.carried, s.net) for s in sales] == [(10.0, 15.0, 475.0),
                                                          (10.0, 45.0, 845.0)]
    assert still_open == {}
    summary = costs.cost_summary(rows)
    assert summary["realized"] == {"gross": 1400.0, "costs": 80.0, "net_of_costs": 1320.0,
                                   "estimated_costs": 0.0}


# ---------------------------------------------------------------------------
# The tax estimate, per financial year
# ---------------------------------------------------------------------------

def _sale(sym, bought, sold, qty, buy_px, sell_px):
    return [_row(bought, sym, "BUY", qty, buy_px, after=qty),
            _row(sold, sym, "SELL", qty, sell_px, after=0.0, cost_basis=buy_px,
                 realized=round((sell_px - buy_px) * qty, 2))]


def _year(est, fy):
    return next(y for y in est["years"] if y["year"] == fy)


def test_a_year_of_mixed_gains_and_losses_nets_and_exempts_once():
    """FY 2026-27, no charges recorded (each row carries zero costs):
      A long  1,000 sh ₹100 -> ₹400 (Apr 2025 -> Jun 2026): +3,00,000
      B long  50 sh ₹200 -> ₹100 (May 2025 -> Jul 2026):    −5,000
      E long  10 sh ₹100 -> ₹200 (Jan 2025 -> Oct 2026):    +1,000
      C short 10 sh ₹1,000 -> ₹1,500 (Apr -> Aug 2026):     +5,000
      D short 20 sh ₹500 -> ₹300 (May -> Sep 2026):         −4,000
    Short net 1,000. Long net 2,96,000, exempt 1,25,000 once: 1,71,000 taxable.
    Tax 1,000 × 20% + 1,71,000 × 12.5% = 200 + 21,375 = ₹21,575; cess ₹863;
    ₹22,438."""
    rows = (_sale("A", "2025-04-01", "2026-06-01", 1000, 100.0, 400.0)
            + _sale("B", "2025-05-01", "2026-07-01", 50, 200.0, 100.0)
            + _sale("E", "2025-01-15", "2026-10-01", 10, 100.0, 200.0)
            + _sale("C", "2026-04-10", "2026-08-10", 10, 1000.0, 1500.0)
            + _sale("D", "2026-05-01", "2026-09-01", 20, 500.0, 300.0))
    y = _year(costs.tax_estimate(rows), "2026-27")
    assert y["short_term"] == {"gains": 5_000.0, "losses": 4_000.0}
    assert y["long_term"] == {"gains": 301_000.0, "losses": 5_000.0}
    assert (y["short_term_taxable"], y["long_term_exemption_used"], y["long_term_taxable"]) == (
        1_000.0, 125_000.0, 171_000.0)
    assert (y["tax"], y["cess"], y["total"]) == (21_575.0, 863.0, 22_438.0)
    assert y["sales"] == 5 and y["sales_without_cost_basis"] == 0


def test_a_year_that_nets_to_a_loss_owes_nothing():
    """FY 2027-28: F short −3,000 (₹1,000 -> ₹700, Apr -> Jun 2027); G long
    +2,000 (₹100 -> ₹300, Jan 2026 -> May 2027). The short-term loss offsets
    the long-term gain: max(0, 2,000 − 3,000) = 0. Tax ₹0."""
    rows = (_sale("F", "2027-04-05", "2027-06-01", 10, 1000.0, 700.0)
            + _sale("G", "2026-01-05", "2027-05-03", 10, 100.0, 300.0))
    y = _year(costs.tax_estimate(rows), "2027-28")
    assert (y["short_term_taxable"], y["long_term_taxable"], y["total"]) == (0.0, 0.0, 0.0)


def test_a_long_term_loss_never_offsets_a_short_term_gain():
    """FY 2028-29: H short +1,000; I long −5,000. The year nets to −4,000, but
    a long-term loss sets off only against long-term gains, so the short-term
    gain is taxed: 1,000 × 20% = ₹200, cess ₹8, ₹208. (The card's "0 when the
    year's net is a loss" holds except in this case; the long-term loss would
    be carried forward, which the estimate does not model.)"""
    rows = (_sale("H", "2028-04-03", "2028-06-01", 10, 100.0, 200.0)
            + _sale("I", "2027-01-04", "2028-07-03", 10, 1000.0, 500.0))
    y = _year(costs.tax_estimate(rows), "2028-29")
    assert y["long_term"] == {"gains": 0.0, "losses": 5_000.0}
    assert (y["short_term_taxable"], y["long_term_taxable"]) == (1_000.0, 0.0)
    assert y["long_term_exemption_used"] == 0.0            # nothing long-term to exempt
    assert (y["tax"], y["cess"], y["total"]) == (200.0, 8.0, 208.0)


def test_years_are_april_to_march_and_twelve_months_is_still_short_term():
    """Bought 2 Jun 2025: sold 2 Jun 2026 is held exactly 12 months, short;
    sold 3 Jun 2026 is long. 31 Mar 2026 is FY 2025-26, 1 Apr 2026 is 2026-27."""
    rows = (_sale("S", "2025-06-02", "2026-06-02", 10, 100.0, 200.0)
            + _sale("L", "2025-06-02", "2026-06-03", 10, 100.0, 200.0)
            + _sale("M", "2026-01-05", "2026-03-31", 10, 100.0, 150.0))
    est = costs.tax_estimate(rows)
    assert [y["year"] for y in est["years"]] == ["2025-26", "2026-27"]
    y = _year(est, "2026-27")
    assert y["short_term"]["gains"] == 1_000.0 and y["long_term"]["gains"] == 1_000.0
    assert _year(est, "2025-26")["short_term"]["gains"] == 500.0


def test_the_oldest_shares_are_sold_first_and_a_split_keeps_their_date():
    """X: 10 bought 10 Jan 2025 at ₹100, 10 more 1 Mar 2026 at ₹200 (average
    ₹150). Sell 15 at ₹300 on 16 Mar 2026 (FY 2025-26): gain 15 × 150 = 2,250;
    the 10 old shares are long-term (1,500), 5 new ones short (750). Sell the
    last 5 at ₹300 on 4 May 2026 (FY 2026-27): +750, short (the new lot).
    Sold newest first, FY 2025-26 would read short 1,500 / long 750.
    S: 10 bought 10 Jan 2025, split 2:1, 20 sold 2 Mar 2026 at ₹600 against
    ₹500: +2,000, all long (FY 2025-26), the split shares keeping their date.
    FY 2025-26: short 750; long 1,500 + 2,000 = 3,500, exempt: tax 150, cess 6, ₹156.
    FY 2026-27: short 750: tax 150, cess 6, ₹156."""
    rows = [_row("2025-01-10", "X", "BUY", 10, 100.0, after=10),
            _row("2026-03-01", "X", "BUY", 10, 200.0, after=20),
            _row("2026-03-16", "X", "SELL", 15, 300.0, after=5, cost_basis=150.0, realized=2250.0),
            _row("2026-05-04", "X", "SELL", 5, 300.0, after=0, cost_basis=150.0, realized=750.0),
            _row("2025-01-10", "S", "BUY", 10, 1000.0, after=10),
            _row("2026-03-02", "S", "SELL", 20, 600.0, after=0, cost_basis=500.0, realized=2000.0)]
    est = costs.tax_estimate(rows)
    s = _year(est, "2025-26")
    assert s["short_term"]["gains"] == 750.0 and s["long_term"]["gains"] == 3_500.0
    assert (s["long_term_exemption_used"], s["tax"], s["cess"], s["total"]) == (
        3_500.0, 150.0, 6.0, 156.0)
    y = _year(est, "2026-27")
    assert y["short_term"]["gains"] == 750.0 and y["long_term"]["gains"] == 0.0
    assert (y["tax"], y["cess"], y["total"]) == (150.0, 6.0, 156.0)


def test_a_sale_with_no_purchase_on_record_counts_as_short_term():
    """N was held before the ledger began: 10 sold at ₹200 against ₹100 is
    +1,000, taxed at the short-term rate (never read low for want of a date),
    and counted."""
    rows = [_row("2026-05-01", "N", "SELL", 10, 200.0, after=0, cost_basis=100.0,
                 realized=1000.0)]
    y = _year(costs.tax_estimate(rows), "2026-27")
    assert y["short_term"]["gains"] == 1_000.0 and y["sales_without_purchase_date"] == 1
    assert y["total"] == 208.0


# ---------------------------------------------------------------------------
# A manual add's charges are money in
# ---------------------------------------------------------------------------

def test_a_manual_add_is_still_an_arrival_and_its_charges_are_money_in():
    """₹10 L opening. 100 shares added at ₹500 (₹50,000, charges ₹59.38:
    STT ₹50, stamp ₹7.50, NSE 1.535 -> ₹1.54, SEBI ₹0.05, GST 18% of 1.59 =
    ₹0.29) raise capital_in by ₹50,059.38 with no cash moved. Worth ₹600 a
    share in the next valuation, the arrival is money in at 100 × 600 = ₹60,000
    plus the ₹59.38 its purchase cost."""
    charges = costs.trade_costs("BUY", 50_000.0)
    assert charges.total == pytest.approx(59.38, abs=1e-9)
    add = TransactionRecord(txn_id="a1", date="2026-02-02", ts="2026-02-02T06:00:00+00:00",
                            user_id="primary", symbol="ACME", side="BUY", qty=100,
                            price=500.0, value=50_000.0, cash_before=1e6, cash_after=1e6,
                            holding_qty_after=100, source="manual", costs=charges)
    points = [{"date": "2026-01-30", "capital_in": 1_000_000.0, "total_equity": 1e6,
               "recorded_at": "2026-01-30T12:00:00+00:00"},
              {"date": "2026-02-02", "capital_in": 1_050_059.38, "total_equity": 1_060_000.0,
               "recorded_at": "2026-02-02T12:00:00+00:00"}]
    flows = R.capital_flows(points, [add], stock_close_on=lambda sym, d: 600.0)
    assert [(f.day, round(f.amount, 2)) for f in flows] == [
        (date(2026, 1, 30), 1_000_000.0), (date(2026, 2, 2), 60_059.38)]


# ---------------------------------------------------------------------------
# Property: random trading days reconcile cash, equity and costs
# ---------------------------------------------------------------------------

def test_property_random_days_reconcile_cash_equity_and_costs(tmp_path, monkeypatch):
    """150 seeded accounts, each traded by the real executor over 2-6 sessions
    of random ADD / TRIM / EXIT / HOLD advice at drifting closes. Checked with
    this test's own arithmetic:
      - every row: costs ≥ 0, total = the sum of its parts, and cash_after =
        cash_before − value − costs (BUY) or + value − costs (SELL);
      - the ledger replayed from the opening cash gives the account's cash;
      - equity − capital_in = realized (before costs) + unrealized − charged;
      - the charges on sales plus those still carried by open positions are
        every charge taken from cash."""
    days = [date(2026, 7, 13) + timedelta(days=i) for i in range(12)]
    days = [d for d in days if d.weekday() < 5]
    seen = {"BUY": 0, "SELL": 0, "partial": 0}
    for seed in range(150):
        rng = random.Random(seed)
        holdings, marks = [], {}
        for i in range(rng.randint(1, 5)):
            cost = round(rng.uniform(20, 3000), 2)
            holdings.append(_h(f"S{i}", float(rng.randint(1, 150)), cost,
                               sector=rng.choice(["power", "it", "pharma"])))
            marks[f"S{i}"] = cost
        cash0 = round(rng.uniform(15_000, 2_000_000), 2)
        s = _account(tmp_path, cash=cash0, holdings=holdings, user=f"u{seed}")
        capital_in = s.load().capital_in
        for day in days[:rng.randint(2, 6)]:
            monkeypatch.setattr(ap, "_today_ist", lambda d=day: d)
            marks = {k: round(v * rng.uniform(0.9, 1.12), 2) for k, v in marks.items()}
            advice = [_advice(h.symbol, rng.choice(["HOLD", "ADD", "ADD", "ADD", "TRIM", "EXIT"]),
                              marks[h.symbol], day=day, confidence=rng.random())
                      for h in s.load().holdings]
            for t in ap.execute_advice(s, s.load(), advice, dict(marks), day):
                c = t.costs
                parts = (c.brokerage + c.stt + c.exchange_fee + c.sebi_fee + c.stamp_duty
                         + c.gst + c.dp_charge)
                assert c.total >= 0 and c.total == pytest.approx(parts, abs=1e-9), seed
                sign = -1 if t.side == "BUY" else 1
                assert t.cash_after == pytest.approx(
                    t.cash_before + sign * t.qty * t.price - c.total, abs=0.006), (seed, t)
                seen[t.side] += 1
                seen["partial"] += t.side == "SELL" and t.holding_qty_after > 0
        ledger = s.load_transactions(limit=100_000)
        p = s.load()
        replay = cash0 + sum((-1 if t.side == "BUY" else 1) * t.qty * t.price - t.costs.total
                             for t in ledger)
        assert p.cash_deployable == pytest.approx(replay, abs=0.006 * (len(ledger) + 1)), seed
        equity = p.cash_deployable + sum(h.adj_qty * marks[h.symbol] for h in p.holdings)
        realized = sum(t.realized_pnl for t in ledger)
        unrealized = sum((marks[h.symbol] - h.adj_avg_price) * h.adj_qty for h in p.holdings)
        charged = sum(t.costs.total for t in ledger)
        assert equity - capital_in == pytest.approx(
            realized + unrealized - charged, abs=0.02 * (len(ledger) + 1)), seed
        summary = costs.cost_summary(ledger)
        assert summary["costs"]["charged"] == pytest.approx(charged, abs=0.01)
        assert summary["realized"]["costs"] + summary["costs"]["on_open_positions"] == \
            pytest.approx(charged, abs=0.01 * (len(ledger) + 1)), seed
        assert summary["realized"]["gross"] == pytest.approx(realized, abs=0.01)
    assert seen["BUY"] > 100 and seen["SELL"] > 200 and seen["partial"] > 50, seen
