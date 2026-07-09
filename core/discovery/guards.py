"""
Compass Phase B — threshold gates on the post-rank shortlist (spec §6.1/§9.1).

Bhavcopy-derived gates (liquidity, series, price, circuit streaks) run from
the EOD window — free for any number of symbols. Per-symbol gates
(surveillance/suspension via NSE meta, float mcap via yfinance) run only on
the shortlist. A gate whose data source is unavailable DEGRADES (symbol kept,
check recorded in degraded_checks) rather than silently passing or failing —
spec §8: "the brief says which signals are dark".

Promoter-pledge (< DISCOVERY_MAX_PLEDGE_PCT) has no free data source yet and
ships DARK: always reported in degraded_checks, never evaluated (v1).
"""
from __future__ import annotations

import logging

import pandas as pd

from core.config import settings
from services.data.fetchers.surveillance import float_mcap_cr, get_symbol_meta

logger = logging.getLogger(__name__)


def _upper_circuit_streak(sym_win: pd.DataFrame) -> int:
    """Trailing consecutive sessions that look like upper-circuit days:
    close == high AND daily gain >= 9.5% (10%/5% bands land under this
    with float noise; a 3+ streak is the operator pattern we exclude)."""
    streak = 0
    for _, row in sym_win.sort_values("date").iloc[::-1].iterrows():
        prev = row["prev_close"]
        if prev and prev > 0:
            gain = (row["close"] - prev) / prev * 100.0
        else:
            gain = 0.0
        if row["close"] >= row["high"] * 0.999 and gain >= 9.5:
            streak += 1
        else:
            break
    return streak


def apply_guards(
    shortlist: list[str], window: pd.DataFrame
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Returns (passed_in_input_order, rejected {sym: [gates]}, degraded_checks)."""
    passed: list[str] = []
    rejected: dict[str, list[str]] = {}
    degraded: list[str] = ["promoter_pledge"]     # dark guard, v1 (spec §6.1)

    by_symbol = {s: g for s, g in window.groupby("symbol")} if not window.empty else {}

    for sym in shortlist:
        gates: list[str] = []
        sym_win = by_symbol.get(sym)
        if sym_win is None or sym_win.empty:
            rejected[sym] = ["no_eod_history"]
            continue
        sym_win = sym_win.sort_values("date")
        latest = sym_win.iloc[-1]

        if latest["series"] in ("BE", "BZ"):
            gates.append("t2t_series")
        if latest["close"] < settings.DISCOVERY_MIN_PRICE:
            gates.append("below_min_price")

        median_tv = sym_win.tail(60)["traded_value_cr"].median()
        if pd.isna(median_tv) or median_tv < settings.DISCOVERY_LIQUIDITY_FLOOR_CR:
            gates.append("low_liquidity")

        if _upper_circuit_streak(sym_win.tail(20)) > settings.DISCOVERY_CIRCUIT_STREAK_MAX:
            gates.append("upper_circuit_streak")

        meta = get_symbol_meta(sym)
        if meta["degraded"]:
            degraded.append(f"surveillance:{sym}")
        else:
            surv = (meta["surveillance"] or "").upper()
            if "ASM" in surv or "GSM" in surv:
                gates.append("surveillance_asm_gsm")
            if meta["suspended"]:
                gates.append("suspended")

        fmcap = float_mcap_cr(sym)
        if fmcap is None:
            degraded.append(f"float_mcap:{sym}")
        elif fmcap < settings.DISCOVERY_FLOAT_MCAP_FLOOR_CR:
            gates.append("low_float_mcap")

        if gates:
            rejected[sym] = gates
        else:
            passed.append(sym)

    logger.info("[discovery.guards] %d passed / %d rejected / %d degraded checks",
                len(passed), len(rejected), len(degraded))
    return passed, rejected, degraded
