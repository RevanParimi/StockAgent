"""PI Prospect P1 — outcome-curve maths against a synthetic tape."""
import pandas as pd

from core.ipo.outcomes import compute_outcomes, symbol_sessions


def _tape(symbol: str, closes: list[float], start="2026-06-15") -> pd.DataFrame:
    days = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({
        "symbol": [symbol] * len(closes),
        "series": ["EQ"] * len(closes),
        "date": [d.date().isoformat() for d in days],
        "open": closes, "close": closes,
    })


def test_returns_are_measured_against_issue_price_not_first_close():
    """A 'listing pop' is issue price to market. Measuring from the first
    close would silently discard the entire listing-day move - the single
    most important number in the whole dataset."""
    tape = _tape("NEWCO", [400.0, 410.0, 420.0, 430.0, 440.0])
    sessions = symbol_sessions(tape, "NEWCO")
    outcomes, _excess, n = compute_outcomes(sessions, issue_price=200.0,
                                            index_pct=lambda a, b: 0.0)
    assert n == 5
    assert outcomes["1"] == 100.0          # 400 vs 200 issue price
    assert outcomes["5"] == 120.0          # 440 vs 200


def test_immature_horizons_are_absent_not_zero():
    tape = _tape("NEWCO", [400.0, 410.0])
    outcomes, _e, n = compute_outcomes(symbol_sessions(tape, "NEWCO"),
                                       issue_price=200.0,
                                       index_pct=lambda a, b: 0.0)
    assert n == 2
    assert "1" in outcomes
    assert "5" not in outcomes and "252" not in outcomes


def test_excess_subtracts_the_index_over_the_same_dates():
    tape = _tape("NEWCO", [220.0, 220.0, 220.0, 220.0, 220.0])
    outcomes, excess, _n = compute_outcomes(
        symbol_sessions(tape, "NEWCO"), issue_price=200.0,
        index_pct=lambda a, b: 4.0,        # index +4% over the same window
    )
    assert outcomes["5"] == 10.0
    assert excess["5"] == 6.0


def test_only_eq_series_rows_count():
    tape = pd.concat([_tape("NEWCO", [400.0, 410.0]),
                      pd.DataFrame({"symbol": ["NEWCO"], "series": ["BE"],
                                    "date": ["2026-06-17"], "open": [999.0],
                                    "close": [999.0]})])
    assert len(symbol_sessions(tape, "NEWCO")) == 2


def test_zero_or_missing_issue_price_yields_no_outcomes():
    tape = _tape("NEWCO", [400.0, 410.0])
    outcomes, excess, _n = compute_outcomes(symbol_sessions(tape, "NEWCO"),
                                            issue_price=0.0,
                                            index_pct=lambda a, b: 0.0)
    assert outcomes == {} and excess == {}
