"""PI Prospect P1 — realised post-listing curves from the bhavcopy tape.

Everything here is measured against the ISSUE PRICE, not the first close.
An IPO's defining number is the listing-day move from what subscribers paid
to what the market said it was worth; anchoring on the first close throws
that away and turns Ola and Ather into the same kind of animal.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from core.ipo.history import HORIZONS_TD


def symbol_sessions(window: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """That symbol's EQ sessions, oldest first. Empty frame if it never traded."""
    if window is None or window.empty:
        return pd.DataFrame(columns=["symbol", "series", "date", "open", "close"])
    mask = (window["symbol"] == symbol) & (window["series"] == "EQ")
    return window[mask].sort_values("date").reset_index(drop=True)


def compute_outcomes(
    sessions: pd.DataFrame,
    issue_price: float | None,
    index_pct: Callable[[str, str], float],
) -> tuple[dict[str, float], dict[str, float], int]:
    """(outcomes, excess, sessions_available).

    `index_pct(start_iso, end_iso)` returns the benchmark's percent change over
    the same two calendar dates. Injected rather than imported so the maths is
    testable without a network and so the caller can fetch the index ONCE for
    the whole backfill instead of per row.

    A horizon the symbol has not yet reached is ABSENT from the dict. Zero
    would be indistinguishable from a flat outcome.
    """
    n = len(sessions)
    outcomes: dict[str, float] = {}
    excess: dict[str, float] = {}
    if n == 0 or not issue_price or issue_price <= 0:
        return outcomes, excess, n

    first_date = str(sessions["date"].iloc[0])
    for td in HORIZONS_TD:
        if n < td:
            continue
        row = sessions.iloc[td - 1]
        close = float(row["close"])
        pct = (close / issue_price - 1.0) * 100.0
        outcomes[str(td)] = round(pct, 4)
        try:
            bench = index_pct(first_date, str(row["date"]))
        except Exception:
            continue          # no benchmark for this date: excess stays absent
        excess[str(td)] = round(pct - bench, 4)
    return outcomes, excess, n
