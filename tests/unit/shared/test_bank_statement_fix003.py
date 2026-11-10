"""
tests/unit/shared/test_bank_statement_fix003.py
================================================
FIX-003 — a bank's income statement reads as complete.

Measured (SA-003 enforce decision, 1 Oct): a bank's statement has interest
income and net interest income and no operating-income, EBIT or gross-profit
row. `get_financials` substituted zeros for the operating line, the section
became `fallback`, and the gate abstained on every analysis of YESBANK,
IDFCFIRSTB, RBLBANK and FEDERALBNK (17 of 78, 22%). The prompt showed an
EBITDA margin of 0.0%.

The invariant is a table of statement shapes against the status each one
MEANS, written by hand: a fresh bank statement with revenue is complete; a
statement missing a line its format reports is not. Row names and newest-
quarter figures are the ones yfinance returned for these listings on 2 Oct
(a read-only probe; the older quarters are made up). Every provider is
patched by the SA-002 fixtures, and their autouse guard fails any
non-loopback connection.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import backend.shared.pipeline.decision_gate as dg
from core.config import settings
from services.data.context import fetch_result as fr
from services.data.fetchers.fundamentals import get_fundamentals_result, get_peer_margins
from tests.unit.shared.test_data_health_contract import (  # noqa: F401  (fixtures)
    TODAY,
    _no_network,
    _quarter_ends,
    _run,
    fresh_db,
    health_log,
    market,
)

CR = 1e7                                   # rupees in a crore
FRESH = TODAY - timedelta(days=30)         # inside every freshness bound
OLD = TODAY - timedelta(days=300)          # outside the default 200-day bound


def _series(newest: float, step: float = 0.02) -> list[float]:
    """Five quarters, newest first, each older one `step` smaller."""
    return [round(newest * (1 - step * i), 2) for i in range(5)]


def _bank(revenue: float, interest_income: float, nii: float, pretax: float) -> dict:
    """A bank's quarterly statement as yfinance lists it (YES Bank's row set).
    'Operating Expense' and 'Operating Revenue' are present, as for the real
    banks: neither is an operating-income row."""
    return {
        "Total Revenue": _series(revenue),
        "Operating Revenue": _series(revenue),
        "Interest Income": _series(interest_income),
        "Interest Expense": _series(interest_income - nii),
        "Net Interest Income": _series(nii),
        "Operating Expense": _series(revenue * 0.5),
        "Pretax Income": _series(pretax),
        "Net Income": _series(pretax * 0.75),
    }


# Newest-quarter figures (₹ Cr, quarter ended 30 Jun 2026), from the 2 Oct probe.
BANKS = {
    "YESBANK": _bank(4655.98, 8054.49, 2785.48, 1311.05),
    "IDFCFIRSTB": _bank(8283.72, 11051.09, 5974.12, 1481.55),
    "RBLBANK": _bank(2577.29, 3840.24, 1655.25, 309.71),
    "FEDERALBNK": _bank(4405.53, 7861.58, 3324.00, 1741.00),
}
YES = BANKS["YESBANK"]

# PAYTM: EBIT and net interest income, no interest income row. TCS: both
# interest rows beside its operating rows. Both are standard statements.
PAYTM = {"Total Revenue": _series(2448.0), "Operating Revenue": _series(2448.0),
         "Operating Income": _series(72.0), "EBIT": _series(254.0),
         "Gross Profit": _series(753.0), "Net Interest Income": _series(-7.0),
         "Interest Expense": _series(7.0), "Pretax Income": _series(247.0)}
TCS = {"Total Revenue": _series(72275.0), "Operating Income": _series(17317.0),
       "EBIT": _series(18217.0), "Gross Profit": _series(28784.0),
       "Interest Income": _series(150.0), "Interest Expense": _series(423.0),
       "Net Interest Income": _series(-273.0), "Pretax Income": _series(17944.0)}


def _without(rows: dict, *names: str) -> dict:
    return {k: v for k, v in rows.items() if k not in names}


def _with(rows: dict, **extra: list[float]) -> dict:
    return {**rows, **{k.replace("_", " "): v for k, v in extra.items()}}


def _frame(rows: dict, newest: date = FRESH,
           blank: dict[str, list[int]] | None = None) -> pd.DataFrame:
    """The statement as yfinance returns it: rows by name, quarter-end
    columns newest first, figures in rupees. `blank` maps a row to the
    quarter indexes (0 = newest) that are NaN, as yfinance lists an announced
    quarter before its figures exist."""
    ends = [pd.Timestamp(d) for d in _quarter_ends(newest)]
    df = pd.DataFrame({k: [v * CR for v in vals] for k, vals in rows.items()}, index=ends).T
    for row, quarters in (blank or {}).items():
        for i in quarters:
            df.loc[row, ends[i]] = np.nan
    return df


OK, STALE, FALLBACK = fr.STATUS_OK, fr.STATUS_STALE, fr.STATUS_FALLBACK

# case, statement rows, newest quarter end, blank cells, expected status, bank format?
SHAPES = [
    ("bank: YES Bank's shape, fresh", YES, FRESH, None, OK, True),
    ("bank: newest quarter 300 days old", YES, OLD, None, STALE, True),
    ("bank: no revenue row", _without(YES, "Total Revenue", "Operating Revenue"), FRESH, None,
     FALLBACK, True),
    ("bank: newest revenue blank", YES, FRESH, {"Total Revenue": [0]}, FALLBACK, True),
    ("bank: newest net interest income blank", YES, FRESH, {"Net Interest Income": [0]},
     FALLBACK, True),
    ("bank: newest quarter listed, every figure blank", YES, FRESH, {r: [0] for r in YES},
     FALLBACK, True),
    ("bank: only an older net interest income blank", YES, FRESH,
     {"Net Interest Income": [2]}, OK, True),
    ("non-bank: no operating row, no interest rows",
     {"Total Revenue": _series(1000.0), "Pretax Income": _series(120.0),
      "Net Income": _series(90.0)}, FRESH, None, FALLBACK, False),
    ("interest income without net interest income, no operating row",
     _without(YES, "Net Interest Income"), FRESH, None, FALLBACK, False),
    ("net interest income without interest income, no operating row",
     _without(YES, "Interest Income"), FRESH, None, FALLBACK, False),
    ("PAYTM's shape: EBIT beside net interest income", PAYTM, FRESH, None, OK, False),
    ("TCS's shape: both interest rows beside operating rows", TCS, FRESH, None, OK, False),
    ("bank rows plus a gross-profit row", _with(YES, Gross_Profit=_series(2000.0)), FRESH, None,
     OK, False),
    ("bank rows plus an EBIT row", _with(YES, EBIT=_series(1500.0)), FRESH, None, OK, False),
    ("standard: revenue and operating income",
     {"Total Revenue": _series(1000.0), "Operating Income": _series(200.0)}, FRESH, None, OK,
     False),
]


class TestStatementShapes:
    """The card's independent invariant: a shape table against the statuses
    each shape means. Run under three tickers, because the shape decides,
    never the ticker or its sector: a bank shape under TATAMOTORS is a bank,
    and PAYTM's shape under YESBANK is not."""

    @pytest.mark.parametrize("ticker", ["YESBANK", "PAYTM", "TATAMOTORS"])
    @pytest.mark.parametrize("case,rows,newest,blank,expected,bank",
                             SHAPES, ids=[s[0] for s in SHAPES])
    def test_status_follows_the_statement_shape(self, market, ticker, case, rows, newest, blank,
                                                expected, bank):
        market.statement[ticker] = _frame(rows, newest, blank)
        res = get_fundamentals_result(ticker)

        assert res.status == expected, (case, res.status, res.reason)
        assert res.text.startswith(f"=== Fundamentals: {ticker} ===")
        named = "bank-format statement" in (res.reason or "")
        assert named is bank, (case, res.reason)
        if bank:
            # No invented zero: the operating line and its margin are absent
            # by format, so the prompt says so instead of showing 0.0.
            assert "EBITDA" not in res.text, case
            assert "Operating margin: not reported" in res.text, case
            assert "Net interest income (quarterly):" in res.text, case
        else:
            assert "EBITDA Margin:" in res.text and "Net interest income" not in res.text, case

    def test_the_cases_are_not_vacuous(self):
        """Every bank case lacks every row operating income is read from;
        each non-bank case lacks a bank row or has an operating row."""
        operating = {"Operating Income", "EBIT", "Gross Profit"}
        for case, rows, _n, _b, _e, bank in SHAPES:
            has_bank_rows = {"Interest Income", "Net Interest Income"} <= set(rows)
            assert bank is (has_bank_rows and not operating & set(rows)), case


class TestNoInventedZero:
    def test_a_bank_statement_reads_as_its_figures(self, market, monkeypatch):
        """YES Bank's June quarter, expected text written from the fixture's
        figures by hand: revenue and net interest income per quarter, growth
        from the revenue line, and no operating figure or margin."""
        monkeypatch.setattr(settings, "FINANCIALS_LOOKBACK_QUARTERS", 4)
        market.statement["YESBANK"] = _frame(YES)
        q = [d.isoformat() for d in _quarter_ends(FRESH)]

        res = get_fundamentals_result("YESBANK")

        assert res.status == OK and res.as_of == q[0], res
        assert res.text.splitlines()[:4] == [
            "=== Fundamentals: YESBANK ===",
            f"Revenue (quarterly): {q[0]}: ₹4655.98Cr | {q[1]}: ₹4562.86Cr | "
            f"{q[2]}: ₹4469.74Cr | {q[3]}: ₹4376.62Cr",
            f"Net interest income (quarterly): {q[0]}: ₹2785.48Cr | {q[1]}: ₹2729.77Cr | "
            f"{q[2]}: ₹2674.06Cr | {q[3]}: ₹2618.35Cr",
            # QoQ 4655.98 / 4562.86 - 1 = +2.04%; "YoY" is the code's newest vs
            # oldest read quarter, 4655.98 / 4376.62 - 1 = +6.38%.
            "Revenue QoQ: +2.0% | Revenue YoY: +6.4% | "
            "Operating margin: not reported (bank-format statement, no operating-income line)",
        ]

    def test_a_standard_statement_reads_exactly_as_before(self, market, monkeypatch):
        """SA-002's text is unchanged for every other statement: revenue
        1000/900/850/800 Cr and operating income 200/180/170/160 Cr give a
        20.0% margin, QoQ +11.1%, and +25.0% against the oldest quarter."""
        monkeypatch.setattr(settings, "FINANCIALS_LOOKBACK_QUARTERS", 4)
        market.statement["TATAMOTORS"] = _frame(
            {"Total Revenue": [1000.0, 900.0, 850.0, 800.0, 750.0],
             "Operating Income": [200.0, 180.0, 170.0, 160.0, 150.0]})
        q = [d.isoformat() for d in _quarter_ends(FRESH)]

        res = get_fundamentals_result("TATAMOTORS")

        assert res.status == OK and res.reason is None, res
        assert res.text.splitlines()[:4] == [
            "=== Fundamentals: TATAMOTORS ===",
            f"Revenue (quarterly): {q[0]}: ₹1000.0Cr | {q[1]}: ₹900.0Cr | "
            f"{q[2]}: ₹850.0Cr | {q[3]}: ₹800.0Cr",
            f"EBITDA  (quarterly): {q[0]}: ₹200.0Cr | {q[1]}: ₹180.0Cr | "
            f"{q[2]}: ₹170.0Cr | {q[3]}: ₹160.0Cr",
            "Revenue QoQ: +11.1% | Revenue YoY: +25.0% | EBITDA Margin: 20.0%",
        ]

    def test_the_structured_result_carries_no_operating_figure(self, market):
        """`get_financials` returns None, not 0.0, where a bank has no line."""
        from services.data.fetchers.fundamentals import get_financials
        market.statement["YESBANK"] = _frame(YES)
        fin = get_financials("YESBANK")
        assert fin["statement_format"] == "bank"
        assert fin["quarterly_ebitda_cr"] is None and fin["ebitda_margin_pct"] is None
        assert fin["missing_rows"] == [] and fin["missing_values"] == {}
        assert fin["quarterly_net_interest_income_cr"][0][1] == 2785.48

    def test_peer_margins_leave_a_bank_out_rather_than_show_zero(self, market):
        market.statement["YESBANK"] = _frame(YES)
        market.statement["MARUTI"] = _frame(
            {"Total Revenue": _series(1000.0), "Operating Income": _series(200.0)})
        assert get_peer_margins(["YESBANK", "MARUTI"]) == {"MARUTI": 20.0}


class TestTheGateFollows:
    """End to end through the real bundle, health record and gate: on the four
    banks' shapes nothing essential is unusable, so the gate does not abstain
    for fundamentals. The counterpart keeps it honest: SA-002's fallback still
    reaches the gate for a statement that is really missing a line."""

    @pytest.mark.parametrize("ticker", sorted(BANKS))
    def test_a_bank_run_has_no_unusable_essential_section(self, market, health_log, fresh_db,
                                                          ticker):
        market.statement[ticker] = _frame(BANKS[ticker], TODAY - timedelta(days=88))

        bundle, record, payload = _run(ticker)
        gate = dg.gate_from_health_row(record)

        assert bundle.section_status["fundamentals"] == OK
        assert "Net interest income (quarterly):" in bundle.sections["fundamentals"]
        assert "EBITDA" not in bundle.sections["fundamentals"]
        assert record["essential_unusable"] == {}, record["health_reasons"]
        assert payload["data_health"]["essential_unusable"] == {}
        assert gate.status in (dg.ACTIONABLE, dg.DEGRADED), gate.reasons
        assert not any("fundamentals" in r for r in gate.reasons), gate.reasons

    def test_a_statement_missing_its_operating_line_still_abstains(self, market, health_log,
                                                                   fresh_db):
        market.statement["TATAMOTORS"] = _frame(
            {"Total Revenue": _series(1000.0), "Pretax Income": _series(120.0)},
            TODAY - timedelta(days=88))

        bundle, record, _payload = _run("TATAMOTORS")
        gate = dg.gate_from_health_row(record)

        assert bundle.section_status["fundamentals"] == FALLBACK
        assert record["essential_unusable"] == {"fundamentals": FALLBACK}
        assert gate.status == dg.ABSTAIN
        assert "essential fundamentals=fallback" in gate.reasons
