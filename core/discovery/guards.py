"""
Compass Phase B — threshold gates on the post-rank shortlist (spec §6.1/§9.1).

Bhavcopy-derived gates (liquidity, series, price, circuit streaks) run from
the EOD window — free for any number of symbols. The other gates run only on
the shortlist. A gate whose data source is unavailable DEGRADES (symbol kept,
check recorded in degraded_checks) rather than silently passing or failing —
spec §8: "the brief says which signals are dark".

Surveillance and suspension (FIX-011): NSE's daily Surveillance Indicator
report, read once a run (services/data/fetchers/surveillance.py), as of the
window's latest session or at most 7 days before it. A symbol under GSM or
long- or short-term ASM, at any stage, is rejected (`surveillance_asm_gsm`);
one whose status is not active ("S", suspended) is rejected (`suspended`). A
symbol the report does not list is kept and recorded as
`surveillance:<SYMBOL>`. No report means the one check `surveillance`: the
gates are dark for the run and every symbol passes them, so the screen says
so and the watchdog (`discovery_guard_sources`) warns when it lasts a week.
Example: on 29 Oct 2026 A2Z Infra was under long-term ASM stage I, so it is
rejected; Maruti was under no measure.

One check, not one per symbol: a per-symbol source (the report's listing,
float mcap, the pledge rows) that answered for no symbol reaching the
per-symbol gates is recorded once, as `surveillance`, `float_mcap` or
`promoter_pledge`, instead of `<source>:<SYMBOL>` for each.

Promoter pledge: NSE's pledge data (services/data/fetchers/nse_disclosures.py)
gives each company's promoter shares pledged as a % of the promoter holding,
for the latest quarter filed. More than DISCOVERY_MAX_PLEDGE_PCT (25) rejects
the symbol (`promoter_pledge_high`): a lender can sell pledged shares when the
price falls. A symbol NSE has no pledge row for, more than one row for (the
rows carry a company name, not a symbol, so which is which cannot be told),
whose row is for a quarter that ended more than 200 days before the screen's
latest session, or whose call failed, is kept and recorded as
`promoter_pledge:<SYMBOL>`. A quarter's pattern is due within 21 days of its
end, so the latest due quarter is at most about 112 days old; 200 days allows
one late quarter more. With no NSE client, or the guard off
(`discovery.pledge_guard`), the one check `promoter_pledge` is recorded.
Example: A2Z Infra's promoters had pledged 99.68% of their shares at 30 Sep
2026, so it is rejected; Maruti's 0.00% passes. On 23 Oct 2026 a row for 31
Mar 2026 (206 days) is unknown, one for 30 Jun 2026 (115 days) is used.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from core.config import settings
from core.events.disclosures import pledged_share_of_promoter
from services.data.fetchers.nse_disclosures import pledge_snapshots
from services.data.fetchers.surveillance import float_mcap_cr, surveillance_list

logger = logging.getLogger(__name__)

_PLEDGE_MAX_AGE_DAYS = 200
# Per-symbol sources whose per-symbol checks collapse into one when every
# symbol degrades (the watchdog reads these names from the persisted screens).
GUARD_SOURCES = ("surveillance", "float_mcap", "promoter_pledge")


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


def _one_check_per_dark_source(degraded: list[str], checked: list[str]) -> list[str]:
    """`degraded` with each GUARD_SOURCES source that degraded for every
    symbol in `checked` recorded once, as `<source>`, in place of its
    per-symbol `<source>:<SYMBOL>` checks."""
    if not checked:
        return degraded
    for source in GUARD_SOURCES:
        per_symbol = {f"{source}:{s}" for s in checked}
        if per_symbol <= set(degraded):
            degraded = [d for d in degraded if d not in per_symbol]
            if source not in degraded:
                degraded.append(source)
    return degraded


def apply_guards(
    shortlist: list[str], window: pd.DataFrame
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Returns (passed_in_input_order, rejected {sym: [gates]}, degraded_checks)."""
    passed: list[str] = []
    rejected: dict[str, list[str]] = {}
    degraded: list[str] = []
    pledges = pledge_snapshots(list(shortlist)) if settings.DISCOVERY_PLEDGE_GUARD else {}
    if not pledges:
        degraded.append("promoter_pledge")

    by_symbol = {s: g for s, g in window.groupby("symbol")} if not window.empty else {}
    session = pd.to_datetime(window["date"]).max().date() if not window.empty else None
    oldest_quarter = ((session - timedelta(days=_PLEDGE_MAX_AGE_DAYS)).isoformat()
                      if session else date.max.isoformat())
    surveillance = None
    if session and shortlist:
        surveillance, as_of = surveillance_list(session)
        if surveillance is None:
            degraded.append("surveillance")
        else:
            logger.info("[discovery.guards] surveillance report as of %s", as_of)

    checked: list[str] = []
    for sym in shortlist:
        gates: list[str] = []
        sym_win = by_symbol.get(sym)
        if sym_win is None or sym_win.empty:
            rejected[sym] = ["no_eod_history"]
            continue
        checked.append(sym)
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

        if surveillance is not None:
            listed = surveillance.get(sym)
            if listed is None:
                degraded.append(f"surveillance:{sym}")
            else:
                if listed.get("measures"):
                    gates.append("surveillance_asm_gsm")
                if listed.get("status") != "A":
                    gates.append("suspended")

        fmcap = float_mcap_cr(sym)
        if fmcap is None:
            degraded.append(f"float_mcap:{sym}")
        elif fmcap < settings.DISCOVERY_FLOAT_MCAP_FLOOR_CR:
            gates.append("low_float_mcap")

        if pledges:
            rows = pledges.get(sym) or []
            # NSE answers one row for a listed company and none for anything
            # else; more than one cannot be told apart (rows carry no symbol).
            pledged = pledged_share_of_promoter(rows) if len(rows) == 1 else None
            if pledged is None or (pledged[1] or "") < oldest_quarter:
                degraded.append(f"promoter_pledge:{sym}")
            elif pledged[0] > settings.DISCOVERY_MAX_PLEDGE_PCT:
                gates.append("promoter_pledge_high")

        if gates:
            rejected[sym] = gates
        else:
            passed.append(sym)

    degraded = _one_check_per_dark_source(degraded, checked)
    logger.info("[discovery.guards] %d passed / %d rejected / %d degraded checks",
                len(passed), len(rejected), len(degraded))
    return passed, rejected, degraded
