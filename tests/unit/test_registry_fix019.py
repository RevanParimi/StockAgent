"""FIX-019: the instrument registry records five configured codes NSE renamed, so the close and
NSE's corporate-action list are asked for under the code NSE trades each one under today.

Every fact below is NSE's public record, read on 30 Oct 2026, not the registry's text: the
renamed code, the effective date and the circular from NSE's symbol-change list and the
company's filings; the same ISIN under both codes in NSE's equity list and bhavcopy. Through
the shipped config/instruments.yaml:

- each ticker resolves on every date, before the rename included, to the new code for Yahoo
  and for NSE, and keeps one price basis (its own), so a close before the rename and one after
  it compare, and no rename joins two bases;
- the rename segment cites NSE's circular;
- grading a decision on the ticker reads NSE's list under the new code, once, and grades a
  split it holds (FIX-016's market model: NSE knows only the codes it lists, as it answered
  "ZOMATO" and "LTIM" with nothing on 29 Oct 2026); without the entry the same decision has
  no result.

It also records, at the owner's word, two configured codes that no longer trade: GATI and
INOXLEISUR, each suspended by NSE for its amalgamation. From the day trading stopped each is
`delisted`, keeps its one basis, names no successor, and the gate abstains on it; GATI's
earlier rename to ACLGATI is resolved like the five.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from core.intelligence.rl.nse_calendar import trading_days_after, trading_days_ago
from core.portfolio import exit_shadow as xs
from tests.unit.test_exit_fix016 import _Market, _nse_row, _real_rows

SHIPPED = Path(__file__).resolve().parents[2] / "config" / "instruments.yaml"

# (configured ticker, NSE code today, effective date, NSE circular, its date), from NSE's
# symbolchange.csv and the circulars attached to each company's "Name and Symbol Change" filing.
RENAMES = [
    ("PVR", "PVRINOX", date(2023, 5, 12), "NSE/CML/56638", "2023-05-08"),
    ("MCDOWELL-N", "UNITDSPR", date(2024, 6, 7), "NSE/CML/62353", "2024-06-06"),
    ("ZOMATO", "ETERNAL", date(2025, 4, 9), "NSE/CML/67420", "2025-04-03"),
    ("LTIM", "LTM", date(2026, 2, 27), "NSE/CML/72948", "2026-02-23"),
    ("ICICIPRULI", "ICICILIFE", date(2026, 10, 23), "NSE/CML/76967", "2026-10-16"),
]
IDS = [r[0] for r in RENAMES]

# (configured ticker, its last NSE code, the first day it did not trade, NSE's notice date), from
# NSE's "Suspension of Trading" notices, each "on account of the Scheme of Amalgamation".
DELISTED = [
    ("GATI", "ACLGATI", date(2025, 11, 12), "2025-11-06"),
    ("INOXLEISUR", "INOXLEISUR", date(2023, 2, 17), "2023-02-14"),
]


@pytest.fixture
def shipped(monkeypatch):
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(SHIPPED))


@pytest.mark.parametrize("ticker, code, effective, circular, issued", RENAMES, ids=IDS)
def test_a_renamed_code_is_asked_for_under_nses_code_on_every_date(
        shipped, ticker, code, effective, circular, issued):
    from backend.shared.data import instruments
    from backend.shared.data.fetchers.symbol_resolver import (
        identity_break, nse_symbol, resolve_identity,
    )
    for on in (effective - timedelta(days=400), effective - timedelta(days=1), effective,
               date(2026, 10, 30)):
        ident = resolve_identity(ticker, on)
        assert (ident.status, ident.symbol, ident.basis, ident.source, nse_symbol(ticker, on)) == (
            "resolved", f"{code}.NS", ticker, "registry", code), on
    assert [resolve_identity(ticker, on).via for on in (effective - timedelta(days=1), effective)] \
        == ["listing", "rename"]
    assert identity_break(ticker, effective - timedelta(days=30), effective + timedelta(days=30)) == ""
    assert instruments.registry_bases(ticker, date(2000, 1, 1), date(2100, 1, 1)) == {ticker}
    assert instruments.segment_on(ticker, effective).evidence == (
        {"source": "NSE circular", "ref": circular, "date": issued},)


@pytest.mark.parametrize("ticker, code, stopped, notice", DELISTED, ids=[d[0] for d in DELISTED])
def test_a_code_that_no_longer_trades_is_delisted_from_the_day_trading_stopped(
        shipped, ticker, code, stopped, notice):
    from backend.shared.data import instruments
    from backend.shared.data.fetchers.symbol_resolver import nse_symbol, resolve_identity
    from backend.shared.pipeline import decision_gate as dg
    last_day = resolve_identity(ticker, stopped - timedelta(days=1))
    assert (last_day.status, last_day.symbol, last_day.basis) == ("resolved", f"{code}.NS", ticker)
    for on in (stopped, date(2026, 10, 30)):
        ident = resolve_identity(ticker, on)
        assert (ident.status, ident.symbol, ident.basis, ident.source, nse_symbol(ticker, on)) == (
            "delisted", f"{code}.NS", ticker, "registry", code), on
        assert ident.reasons[0].endswith("the code no longer trades")
        gate = dg.apply_identity(dg.DecisionGate(status="actionable", run_id="r1"), ident)
        assert gate.status == "abstain"
        assert gate.reasons[0].startswith("identity delisted: NSE suspended trading in")
    assert instruments.registry_bases(ticker, date(2000, 1, 1), date(2100, 1, 1)) == {ticker}
    segment = instruments.segment_on(ticker, stopped)
    assert segment.successors == ()
    assert [(e["source"], e["date"]) for e in segment.evidence] == [("NSE notice", notice)]


def test_gati_traded_as_aclgati_from_its_rename_until_its_suspension(shipped):
    from backend.shared.data import instruments
    from backend.shared.data.fetchers.symbol_resolver import identity_break, resolve_identity
    renamed = date(2023, 11, 30)
    assert [(i.status, i.symbol, i.via) for i in (resolve_identity("GATI", renamed - timedelta(days=1)),
                                                  resolve_identity("GATI", renamed),
                                                  resolve_identity("GATI", date(2025, 11, 11)))] == [
        ("resolved", "ACLGATI.NS", "listing"), ("resolved", "ACLGATI.NS", "rename"),
        ("resolved", "ACLGATI.NS", "rename")]
    assert identity_break("GATI", renamed - timedelta(days=30), renamed + timedelta(days=30)) == ""
    assert instruments.segment_on("GATI", renamed).evidence == (
        {"source": "NSE circular", "ref": "NSE/CML/59502", "date": "2023-11-24"},)


@pytest.mark.parametrize("ticker, code, effective, circular, issued", RENAMES, ids=IDS)
def test_grading_reads_the_list_under_nses_code_and_grades_a_split_it_holds(
        monkeypatch, ticker, code, effective, circular, issued):
    """The evidence rule sells the stock at ₹2,500 five sessions before the rename (ten after
    it for those renamed long ago); it stays flat in real terms, and three sessions later it
    splits from Rs 10 to Rs 2 a share, so NSE's raw close is ₹500. By hand: ₹500 is ₹2,500 in
    the old shares, a return of 0, and the sale was wrong with 0 at both horizons."""
    from services.data.fetchers import corporate_events
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(SHIPPED))
    market = _Market()
    decided = (trading_days_ago(effective, 5) if effective.year == 2026
               else trading_days_after(date(2026, 6, 1), 10))
    rows = [dict(r, symbol=ticker, close=2500.0)
            for r in _real_rows(market, [(True, 0.0)], start=decided)]
    assert rows[0]["date"] == decided.isoformat()
    ex = trading_days_after(decided, 3)
    market.value = {code: lambda d: 2500.0}
    market.actions[code] = [(ex, 5.0, _nse_row("split", ex))]
    quotes, actions = market.install(monkeypatch)
    reads = []
    real_read = corporate_events.read_corp_actions
    monkeypatch.setattr(corporate_events, "read_corp_actions",
                        lambda s: reads.append(s) or real_read(s))
    grades = xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                    bench_close_on=lambda d: 1000.0, corp_actions=actions)
    assert reads == [code]
    assert [(g["status"], g["return_pct"], g["right"], g["result_pct"], g["basis"])
            for g in grades] == [
        ("graded", 0.0, False, 0.0, f"×5 for the split ex {ex.isoformat()}")] * 2

    # Without the entry (the suite's empty registry) the app asks for its own code, which
    # NSE and Yahoo no longer answer: the same decision has no result at either horizon.
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH",
                       str(Path(__file__).resolve().parents[1] / "fixtures" / "instruments_empty.yaml"))
    quotes, actions = market.install(monkeypatch)
    grades = xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                    bench_close_on=lambda d: 1000.0, corp_actions=actions)
    assert [g["status"] for g in grades] == ["ungraded"] * 2
