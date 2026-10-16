"""Weekly results scorecard: one row per ISO week, in plain words.

Is the portfolio making money, were its sales good, and did anything cross a
red line? Every figure comes from a ledger the system already keeps:

- **Closed trades** from transactions.jsonl, as round trips. A position counts
  once, on the day its last share is sold, with every sale of it (TRIMs
  included) in its result. An open position is never a closed trade.
- **Sold too early** from the nightly auditor's advice-lane grades
  (advice_outcomes.jsonl), joined to each advisor sale by its advice_ref. A
  sale stays in the denominator whether or not the stock is still held: the
  old 28-day scoreboard priced only current holdings and so dropped every
  stock it had sold.
- **You vs the Nifty** from value_history.jsonl. Every rise in capital_in is a
  deposit, and the same deposit buys Nifty units at that day's close. Cash the
  portfolio leaves idle therefore counts against it, as it would for a
  person who kept it in an index fund.

The red-flag rules below were predeclared on 11-12 Oct 2026, before any
scorecard existed. Changing one is a reviewed code change, never a setting
tuned after seeing a result. A flag reports; it changes no decision.

Missing data never reads as "clear". Where a flag's population has members
with no figure (a matured sale with no grade, a closed position with no
purchase date), the flag fires only if it is crossed even when every missing
member is counted in the portfolio's favour, reads clear only if it holds even
when they all count against it, and otherwise says it could not be checked.
A missing Nifty close reads "unavailable", never a flat line.

Pure apart from the trigger wording import: no clock, no network, no files.
The I/O wrapper is `weekly_scorecard` at the bottom.
"""
from __future__ import annotations

import logging
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable

from core.intelligence.rl.nse_calendar import trading_dates, trading_days_after

logger = logging.getLogger(__name__)

# -- Predeclared red-flag rules (fixed 11-12 Oct 2026, before any result) -----
EXPECTANCY_WEEKS = 3            # since-start expectancy below 0 at this many week ends running
SOLD_EARLY_HORIZON_TD = 30      # the flag reads 30 sessions, an investor's six weeks
SOLD_EARLY_SHOWN_TD = (10, 30)  # the line shows 10 sessions beside it
SOLD_EARLY_SHARE_PCT = 60.0     # flag when MORE than this share of sold stocks beat the Nifty
SOLD_EARLY_WINDOW_WEEKS = 8     # over sales whose 30 sessions ended in the trailing 8 weeks
SOLD_EARLY_MIN_SALES = 8        # ... with at least 8 of them
THESIS_SHARE_PCT = 50.0         # thesis_break above this share of the advisor's sales
THESIS_WINDOW_WEEKS = 4
NIFTY_GAP_POINTS = 3.0          # behind the money-weighted Nifty by MORE than this
NIFTY_WINDOW_WEEKS = 4
MIN_HOLD_SESSIONS = 10          # median sessions held, positions closed this week

SELL_VERDICTS = ("EXIT", "SWITCH", "TRIM")
_FLAT_QTY = 1e-9

FIRED, CLEAR, UNKNOWN, NOT_ENOUGH = "fired", "clear", "unknown", "not_enough"


# -- Weeks ---------------------------------------------------------------------

@dataclass(frozen=True)
class Week:
    key: str          # ISO week, "2026-W42"
    monday: date
    sunday: date

    def window_start(self, weeks: int) -> date:
        """Monday of the window of `weeks` ISO weeks that ends with this one."""
        return self.monday - timedelta(weeks=weeks - 1)

    @property
    def saturday(self) -> date:
        return self.monday + timedelta(days=5)


def week_of(d: date) -> Week:
    monday = d - timedelta(days=d.weekday())
    year, number, _ = monday.isocalendar()
    return Week(f"{year}-W{number:02d}", monday, monday + timedelta(days=6))


def covered_week(on: date) -> Week:
    """The week a scorecard built on `on` describes: the latest week whose
    sessions are over. Saturday and Sunday describe their own week; a weekday
    describes the week before. So a mid-week manual run never stores half a
    week under a key that is then never rewritten."""
    return week_of(on) if on.weekday() >= 5 else week_of(on - timedelta(days=7))


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


# -- Closed trades (round trips) -------------------------------------------------

@dataclass(frozen=True)
class Trade:
    symbol: str
    opened: date | None      # None: opened before the ledger knew it (e.g. a CSV import)
    closed: date
    realized: float
    cost: float | None       # cost of every share sold; None when a sale carried none
    source: str

    @property
    def pnl_pct(self) -> float | None:
        if self.cost is None or self.cost <= 0:
            return None
        return self.realized * 100.0 / self.cost


def _in_order(txns: Iterable) -> list:
    """Dates ascending; the ledger's own order within a day (a run sells
    before it buys)."""
    dated = [(d, i, t) for i, t in enumerate(txns) if (d := _day(t.date)) is not None]
    return [t for _, _, t in sorted(dated, key=lambda x: (x[0], x[1]))]


def closed_trades(txns: Iterable) -> list[Trade]:
    """Every position fully sold, in closing order.

    The result is the sum of every sale's realized P&L over the sum of every
    sold share's cost basis, so a TRIM followed by an EXIT is one trade. A
    sale with no cost basis (rows written before cost stamping) makes the
    trade's result unknown: shown as a count, never guessed."""
    open_positions: dict[str, dict] = {}
    out: list[Trade] = []
    for t in _in_order(txns):
        if t.side == "BUY":
            open_positions.setdefault(
                t.symbol, {"opened": _day(t.date), "realized": 0.0, "cost": 0.0})
            continue
        if t.side != "SELL":
            continue
        pos = open_positions.setdefault(
            t.symbol, {"opened": None, "realized": 0.0, "cost": 0.0})
        pos["realized"] += float(t.realized_pnl or 0.0)
        if pos["cost"] is not None and t.cost_basis and t.cost_basis > 0 and t.qty > 0:
            pos["cost"] += float(t.cost_basis) * float(t.qty)
        else:
            pos["cost"] = None
        if float(t.holding_qty_after) <= _FLAT_QTY:
            out.append(Trade(symbol=t.symbol, opened=pos["opened"], closed=_day(t.date),
                             realized=pos["realized"], cost=pos["cost"],
                             source=t.source))
            del open_positions[t.symbol]
    return out


def trade_stats(trades: Iterable[Trade]) -> dict:
    """Count, win rate, average win, average loss and expectancy.

    A win is a result above zero. Expectancy = win rate × average win − loss
    rate × average loss (the loss as a size). That is exactly the mean result
    per trade, which is how it is computed: the product form can leave -9e-16
    where the answer is 0, and the red flag asks "below 0". Before costs:
    brokerage, taxes and slippage are not charged."""
    trades = list(trades)
    known = [t.pnl_pct for t in trades if t.pnl_pct is not None]
    wins = [p for p in known if p > 0]
    losses = [p for p in known if p <= 0]
    stats = {"count": len(trades), "known": len(known),
             "unknown": len(trades) - len(known),
             "wins": len(wins), "losses": len(losses), "win_rate_pct": None,
             "avg_win_pct": None, "avg_loss_pct": None, "expectancy_pct": None,
             "basis": "before costs"}
    if not known:
        return stats
    stats.update(
        win_rate_pct=len(wins) * 100.0 / len(known),
        avg_win_pct=sum(wins) / len(wins) if wins else None,
        avg_loss_pct=sum(losses) / len(losses) if losses else None,
        expectancy_pct=sum(known) / len(known),
    )
    return stats


# -- Sales and the auditor's grades ---------------------------------------------

@dataclass(frozen=True)
class Sale:
    on: date
    symbol: str
    ref: str                 # advice_ref; "" for your own sales
    verdict: str             # EXIT / SWITCH / TRIM; "" for your own sales
    triggers: tuple[str, ...]
    source: str

    @property
    def by_advisor(self) -> bool:
        return self.verdict in SELL_VERDICTS


def sales(txns: Iterable) -> list[Sale]:
    """Every SELL row, one per advice call (a ref is sold once)."""
    out: list[Sale] = []
    seen: set[str] = set()
    for t in _in_order(txns):
        if t.side != "SELL":
            continue
        ref = (t.advice_ref or "").strip()
        if ref:
            if ref in seen:
                continue
            seen.add(ref)
        out.append(Sale(on=_day(t.date), symbol=t.symbol, ref=ref,
                        verdict=t.verdict or "", triggers=tuple(t.triggers or ()),
                        source=t.source))
    return out


def advice_grades(rows: Iterable) -> dict[tuple[str, int], float]:
    """(ref, horizon) -> excess return over the Nifty, advice lane only."""
    out: dict[tuple[str, int], float] = {}
    for r in rows:
        if r.lane == "advice":
            out.setdefault((r.ref, int(r.horizon_td)), float(r.excess_pct))
    return out


def sold_too_early(all_sales: Iterable[Sale], grades: dict, horizon: int, *,
                   as_of: date, matured_from: date | None = None) -> dict:
    """How often the stock the advisor sold beat the Nifty `horizon` sessions on.

    Population: every advisor sale up to `as_of`, held or not. With
    `matured_from`, only sales whose horizon ended in [matured_from, as_of].
    A sale whose horizon has not ended is pending, never a win or a loss; one
    whose horizon ended without a grade is counted as ungraded."""
    counts = {"horizon_td": horizon, "sales": 0, "pending": 0, "graded": 0,
              "beat": 0, "ungraded": 0, "share_pct": None,
              "median_excess_points": None}
    excess: list[float] = []
    for s in all_sales:
        if not s.by_advisor or s.on > as_of:
            continue
        matured = trading_days_after(s.on, horizon)
        if matured_from is not None and not (matured_from <= matured <= as_of):
            continue
        counts["sales"] += 1
        if matured > as_of:
            counts["pending"] += 1
            continue
        grade = grades.get((s.ref, horizon)) if s.ref else None
        if grade is None:
            counts["ungraded"] += 1
            continue
        counts["graded"] += 1
        counts["beat"] += grade > 0
        excess.append(grade)
    if excess:
        counts["share_pct"] = counts["beat"] / counts["graded"] * 100.0
        counts["median_excess_points"] = statistics.median(excess)
    return counts


def _trigger_label(code: str) -> str:
    if code == "manual":
        return "sold by you"
    if code == "none":
        return "no reason recorded"
    from core.portfolio.advisor import explain_triggers
    return explain_triggers([code]).rstrip(".").lower()


def exit_reasons(all_sales: Iterable[Sale], start: date, end: date) -> dict:
    """Sales in [start, end] and the count per trigger, in plain words. A
    sale with two triggers counts under both."""
    counts: Counter = Counter()
    n = 0
    for s in all_sales:
        if not (start <= s.on <= end):
            continue
        n += 1
        if not s.by_advisor:
            counts["manual"] += 1
        elif not s.triggers:
            counts["none"] += 1
        else:
            counts.update(set(s.triggers))
    return {"from": start.isoformat(), "to": end.isoformat(), "sales": n,
            "reasons": [{"code": c, "label": _trigger_label(c), "count": k}
                        for c, k in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]}


# -- You vs the Nifty (money-weighted) ----------------------------------------------

def _value_points(points: Iterable[dict]) -> list[dict]:
    """Dated value points with an equity figure, ascending; the last wins a date."""
    by_day: dict[date, dict] = {}
    for p in points:
        d = _day(p.get("date"))
        if d is None or not isinstance(p.get("total_equity"), (int, float)):
            continue
        by_day[d] = {**p, "_day": d}
    return [by_day[d] for d in sorted(by_day)]


def deposits_from_values(points: Iterable[dict]) -> list[tuple[date, float]]:
    """Each change in capital_in between value points, dated at the point
    that first shows it. The first point's capital_in is the opening deposit.
    A fall is a withdrawal."""
    out: list[tuple[date, float]] = []
    previous = 0.0
    for p in _value_points(points):
        cap = p.get("capital_in")
        if not isinstance(cap, (int, float)):
            continue
        if abs(float(cap) - previous) > 0.005:
            out.append((p["_day"], float(cap) - previous))
        previous = float(cap)
    return out


def nifty_equivalent(deposits: Iterable[tuple[date, float]],
                     close_on: Callable[[date], float], on: date) -> float:
    """What the same deposits are worth at `on`'s close, had each bought the
    Nifty at its own day's close. Raises if any close is missing."""
    units = 0.0
    for d, amount in deposits:
        if d <= on:
            close = float(close_on(d))
            if close <= 0:
                raise ValueError(f"non-positive Nifty close on {d}")
            units += amount / close
    end_close = float(close_on(on))
    if end_close <= 0:
        raise ValueError(f"non-positive Nifty close on {on}")
    return units * end_close


def vs_nifty(points: Iterable[dict], close_on: Callable[[date], float], *,
             end: date, start: date | None = None) -> dict:
    """The portfolio against the same money in the Nifty, from the last value
    point before `start` (None: from the first deposit) to the last one on or
    before `end`.

    Both returns use the same flows: (end − start − deposits) / (start +
    deposits). The portfolio's figure includes its idle cash; the Nifty's
    holds none."""
    pts = _value_points(points)
    deposits = deposits_from_values(pts)
    end_pt = next((p for p in reversed(pts) if p["_day"] <= end), None)
    if end_pt is None:
        return {"available": False, "reason": "no valuation recorded yet"}
    if start is None:
        start_day, start_equity = None, 0.0
    else:
        if end_pt["_day"] < start:
            # Comparing the last valuation with itself would print a flat 0%
            # against 0%: a week with no valuation is unavailable, not level.
            return {"available": False, "reason": "no valuation recorded in this period",
                    "to": end_pt["_day"].isoformat()}
        start_pt = next((p for p in reversed(pts) if p["_day"] < start), None)
        if start_pt is None:
            return {"available": False, "reason": "younger",
                    "to": end_pt["_day"].isoformat()}
        start_day, start_equity = start_pt["_day"], float(start_pt["total_equity"])
    end_day, end_equity = end_pt["_day"], float(end_pt["total_equity"])
    flows = sum(a for d, a in deposits
                if (start_day is None or d > start_day) and d <= end_day)
    try:
        nifty_start = nifty_equivalent(deposits, close_on, start_day) if start_day else 0.0
        nifty_end = nifty_equivalent(deposits, close_on, end_day)
    except Exception as exc:
        logger.info("[results] Nifty comparison unavailable: %s", exc)
        return {"available": False, "reason": "no Nifty close for a needed day",
                "to": end_day.isoformat()}
    if start_equity + flows <= 0 or nifty_start + flows <= 0:
        return {"available": False, "reason": "no money invested yet",
                "to": end_day.isoformat()}
    portfolio_pct = (end_equity - start_equity - flows) / (start_equity + flows) * 100.0
    nifty_pct = (nifty_end - nifty_start - flows) / (nifty_start + flows) * 100.0
    return {"available": True,
            "from": start_day.isoformat() if start_day else None,
            "to": end_day.isoformat(),
            "portfolio_pct": portfolio_pct, "nifty_pct": nifty_pct,
            "gap_points": portfolio_pct - nifty_pct,
            "portfolio_value": end_equity, "nifty_value": nifty_end,
            "deposits": flows}


# -- Breadth and holding period --------------------------------------------------

def breadth(points: Iterable[dict], holdings: int | None, end: date,
            floor: dict | None = None) -> dict:
    """Holdings and the invested share at the last valuation on or before
    `end`. `holdings` is None when it was not recorded for that week."""
    pts = _value_points(points)
    end_pt = next((p for p in reversed(pts) if p["_day"] <= end), None)
    invested = None
    if end_pt is not None and float(end_pt["total_equity"]) > 0 \
            and isinstance(end_pt.get("market_value"), (int, float)):
        invested = float(end_pt["market_value"]) / float(end_pt["total_equity"]) * 100.0
    return {"holdings": holdings, "invested_pct": invested,
            "as_of": end_pt["_day"].isoformat() if end_pt else None,
            "floor": floor or None}


def sessions_held(opened: date, closed: date) -> int:
    """Exchange sessions after the buy, up to and including the sale."""
    return len(trading_dates(opened + timedelta(days=1), closed))


def holding_period(trades: Iterable[Trade], start: date, end: date) -> dict:
    closed = [t for t in trades if start <= t.closed <= end]
    known = [sessions_held(t.opened, t.closed) for t in closed if t.opened]
    return {"closed": len(closed), "known": len(known),
            "unknown": len(closed) - len(known),
            "median_sessions": statistics.median(known) if known else None,
            "sessions": sorted(known)}


# -- Red flags ---------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x:+.1f}%"


def _below(x: float, line: float) -> bool:
    """x < line, ignoring float noise far below a paisa's worth of a percent."""
    return round(x - line, 9) < 0


def _flag(flag_id: str, status: str, sentence: str, **detail) -> dict:
    return {"id": flag_id, "status": status, "sentence": sentence, **detail}


def expectancy_flag(trades: list[Trade], week: Week) -> dict:
    ends = [week.sunday - timedelta(weeks=i) for i in range(EXPECTANCY_WEEKS)]
    values = [trade_stats([t for t in trades if t.closed <= e])["expectancy_pct"]
              for e in ends]
    unknown = trade_stats([t for t in trades if t.closed <= week.sunday])["unknown"]
    note = (f" {unknown} closed trade{'s' if unknown != 1 else ''} with no recorded "
            "cost not counted." if unknown else "")
    if any(v is None for v in values):
        return _flag("expectancy", NOT_ENOUGH,
                     "Money per trade: not enough closed trades yet for "
                     f"{EXPECTANCY_WEEKS} weeks of figures." + note,
                     values=values, unknown=unknown)
    shown = ", ".join(_pct(v) for v in reversed(values))
    if all(_below(v, 0.0) for v in values):
        return _flag("expectancy", FIRED,
                     "Losing money per trade: the average closed trade was negative at "
                     f"the end of each of the last {EXPECTANCY_WEEKS} weeks ({shown}, "
                     "before costs)." + note, values=values, unknown=unknown)
    return _flag("expectancy", CLEAR,
                 f"Money per trade: not negative {EXPECTANCY_WEEKS} weeks running "
                 f"({shown}, before costs)." + note, values=values, unknown=unknown)


def sold_too_early_flag(stats: dict) -> dict:
    n, beat, missing = stats["sales"], stats["beat"], stats["ungraded"]
    horizon = stats["horizon_td"]
    if n < SOLD_EARLY_MIN_SALES:
        return _flag("sold_too_early", NOT_ENOUGH,
                     f"Selling too early: {n} sale{'s' if n != 1 else ''} reached "
                     f"{horizon} sessions in the last {SOLD_EARLY_WINDOW_WEEKS} weeks; "
                     f"the check needs {SOLD_EARLY_MIN_SALES}.", **stats)
    low = beat / n * 100.0                    # every missing grade counted as "did not beat"
    high = (beat + missing) / n * 100.0       # every missing grade counted as "beat"
    # Whole-number comparisons: 6 of 10 is exactly 60%, which is not above it.
    if beat * 100 > SOLD_EARLY_SHARE_PCT * n:
        return _flag("sold_too_early", FIRED,
                     f"Selling too early: after {beat} of {n} sales the stock beat the "
                     f"Nifty over the next {horizon} sessions ({low:.0f}%; red line "
                     f"{SOLD_EARLY_SHARE_PCT:.0f}%)."
                     + (f" {missing} more have no grade yet." if missing else ""), **stats)
    if (beat + missing) * 100 <= SOLD_EARLY_SHARE_PCT * n:
        return _flag("sold_too_early", CLEAR,
                     f"Selling too early: {beat} of {n} sold stocks beat the Nifty over "
                     f"the next {horizon} sessions ({low:.0f}%; red line "
                     f"{SOLD_EARLY_SHARE_PCT:.0f}%)."
                     + (f" Counting the {missing} with no grade as beating it, the share "
                        f"is still {high:.0f}%." if missing else ""), **stats)
    return _flag("sold_too_early", UNKNOWN,
                 f"Selling too early: could not check. {missing} of {n} sales have no "
                 f"{horizon}-session grade; the share is between {low:.0f}% and "
                 f"{high:.0f}% (red line {SOLD_EARLY_SHARE_PCT:.0f}%).", **stats)


def thesis_break_flag(all_sales: list[Sale], start: date, end: date) -> dict:
    window = [s for s in all_sales if s.by_advisor and start <= s.on <= end]
    n = len(window)
    k = sum(1 for s in window if "thesis_break" in s.triggers)
    detail = {"sales": n, "thesis_break": k, "from": start.isoformat()}
    if n == 0:
        return _flag("thesis_break", NOT_ENOUGH,
                     f"Selling on the price path: no sales by the advisor in the last "
                     f"{THESIS_WINDOW_WEEKS} weeks.", **detail)
    share = k / n * 100.0
    detail["share_pct"] = share
    if k * 100 > THESIS_SHARE_PCT * n:
        return _flag("thesis_break", FIRED,
                     f"Selling on the price path: {k} of {n} sales in the last "
                     f"{THESIS_WINDOW_WEEKS} weeks ({share:.0f}%) were because the "
                     f"thesis broke after a price miss (red line {THESIS_SHARE_PCT:.0f}%).",
                     **detail)
    return _flag("thesis_break", CLEAR,
                 f"Selling on the price path: {k} of {n} sales in the last "
                 f"{THESIS_WINDOW_WEEKS} weeks ({share:.0f}%; red line "
                 f"{THESIS_SHARE_PCT:.0f}%).", **detail)


def behind_nifty_flag(window: dict, stale: bool, ever_valued: bool = True) -> dict:
    if not ever_valued:
        # A portfolio without cash accounting never records a valuation: there
        # is nothing to compare, every week, which is not a lapse to chase.
        return _flag("behind_nifty", NOT_ENOUGH,
                     "Behind the Nifty: no valuation has been recorded for this "
                     "portfolio.", **window)
    if stale:
        return _flag("behind_nifty", UNKNOWN,
                     "Behind the Nifty: could not check. No valuation was recorded "
                     "this week.", **window)
    if not window.get("available"):
        if window.get("reason") == "younger":
            return _flag("behind_nifty", NOT_ENOUGH,
                         f"Behind the Nifty: the portfolio is younger than "
                         f"{NIFTY_WINDOW_WEEKS} weeks.", **window)
        return _flag("behind_nifty", UNKNOWN,
                     f"Behind the Nifty: could not check ({window.get('reason')}).",
                     **window)
    gap = window["gap_points"]
    text = (f"over the last {NIFTY_WINDOW_WEEKS} weeks the portfolio made "
            f"{_pct(window['portfolio_pct'])} against {_pct(window['nifty_pct'])} for "
            f"the same money in the Nifty")
    if _below(gap, -NIFTY_GAP_POINTS):
        return _flag("behind_nifty", FIRED,
                     f"Behind the Nifty: {text} ({-gap:.1f} points behind; red line "
                     f"{NIFTY_GAP_POINTS:.0f}).", **window)
    return _flag("behind_nifty", CLEAR,
                 f"Behind the Nifty: {text} (red line {NIFTY_GAP_POINTS:.0f} points "
                 "behind).", **window)


def _median_with(known: list[int], extra: int, value: float) -> float:
    return statistics.median(known + [value] * extra)


def holding_period_flag(stats: dict) -> dict:
    n, unknown, known = stats["closed"], stats["unknown"], stats["sessions"]
    if n == 0:
        return _flag("holding_period", NOT_ENOUGH,
                     "Holding period: no position was closed this week.", **stats)
    low = _median_with(known, unknown, 0.0)               # missing = sold at once
    high = _median_with(known, unknown, float("inf"))     # missing = held for ever
    if high < MIN_HOLD_SESSIONS:
        return _flag("holding_period", FIRED,
                     f"Selling too fast: positions closed this week were held a median "
                     f"of {high:g} sessions (red line: under {MIN_HOLD_SESSIONS}).",
                     **stats)
    if low >= MIN_HOLD_SESSIONS:
        return _flag("holding_period", CLEAR,
                     f"Holding period: positions closed this week were held a median of "
                     f"{low:g} sessions (red line: under {MIN_HOLD_SESSIONS}).", **stats)
    return _flag("holding_period", UNKNOWN,
                 f"Holding period: could not check. {unknown} of {n} positions closed "
                 "this week have no recorded purchase date.", **stats)


# -- The row -------------------------------------------------------------------------

def _rounded(value):
    if isinstance(value, float):
        return round(value, 2) if value == value and abs(value) != float("inf") else None
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(v) for v in value]
    return value


def build_row(*, week: Week, txns: Iterable, points: Iterable[dict],
              audit_rows: Iterable, close_on: Callable[[date], float],
              holdings: int | None, floor: dict | None = None,
              computed_at: str | None = None) -> dict:
    """The scorecard row for `week` from the user's own ledgers. Facts dated
    after the week are ignored, so a late rebuild describes the week as it was."""
    end = week.sunday
    txns = [t for t in txns if (_day(t.date) or date.max) <= end]
    points = [p for p in points if (_day(p.get("date")) or date.max) <= end]
    trades = closed_trades(txns)
    all_sales = sales(txns)
    grades = advice_grades(audit_rows)

    week_trades = [t for t in trades if week.monday <= t.closed <= end]
    sold = {
        "since_start": [sold_too_early(all_sales, grades, h, as_of=end)
                        for h in SOLD_EARLY_SHOWN_TD],
        "last_8_weeks": [sold_too_early(all_sales, grades, h, as_of=end,
                                        matured_from=week.window_start(SOLD_EARLY_WINDOW_WEEKS))
                         for h in SOLD_EARLY_SHOWN_TD],
    }
    flag_window = next(s for s in sold["last_8_weeks"]
                       if s["horizon_td"] == SOLD_EARLY_HORIZON_TD)

    valued = _value_points(points)
    last_valuation = valued[-1]["_day"] if valued else None
    stale = last_valuation is not None and last_valuation < week.monday
    money = {
        "week": vs_nifty(points, close_on, end=end, start=week.monday),
        "last_4_weeks": vs_nifty(points, close_on, end=end,
                                 start=week.window_start(NIFTY_WINDOW_WEEKS)),
        "since_start": vs_nifty(points, close_on, end=end),
        "stale": stale,
    }
    held = holding_period(trades, week.monday, end)
    thesis_start = week.window_start(THESIS_WINDOW_WEEKS)
    flags = [
        expectancy_flag(trades, week),
        sold_too_early_flag(flag_window),
        thesis_break_flag(all_sales, thesis_start, end),
        behind_nifty_flag(money["last_4_weeks"], stale, last_valuation is not None),
        holding_period_flag(held),
    ]
    sessions = trading_dates(week.monday, end)
    row = {
        "week": week.key,
        "week_start": week.monday.isoformat(),
        "week_end": end.isoformat(),
        "sessions": {"count": len(sessions),
                     "first": sessions[0].isoformat() if sessions else None,
                     "last": sessions[-1].isoformat() if sessions else None},
        "computed_at": computed_at or datetime.now(timezone.utc).isoformat(),
        "valuation_date": last_valuation.isoformat() if last_valuation else None,
        "red_flags": flags,
        "closed_trades": {"week": trade_stats(week_trades),
                          "since_start": trade_stats(trades)},
        "sold_too_early": sold,
        "exit_reasons": {"week": exit_reasons(all_sales, week.monday, end),
                         "last_4_weeks": exit_reasons(all_sales, thesis_start, end)},
        "vs_nifty": money,
        "breadth": breadth(points, holdings, end, floor),
        "holding_period": held,
    }
    row = _rounded(row)
    row["lines"] = scorecard_lines(row)
    return row


# -- Plain words ---------------------------------------------------------------------

def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _short_day(iso: str | None) -> str:
    d = _day(iso)
    return f"{d.day} {d.strftime('%b')}" if d else "?"


def _trades_line(label: str, s: dict) -> str:
    if not s["count"]:
        return f"{label}: none."
    if not s["known"]:
        return f"{label}: {s['count']}, none with a recorded cost."
    parts = [f"{label}: {_plural(s['known'], 'trade')}",
             f"{s['wins']} won ({s['win_rate_pct']:.0f}%)"]
    if s["avg_win_pct"] is not None:
        parts.append(f"average win {_pct(s['avg_win_pct'])}")
    if s["avg_loss_pct"] is not None:
        parts.append(f"average loss {_pct(s['avg_loss_pct'])}")
    parts.append(f"expectancy {_pct(s['expectancy_pct'])} per trade, before costs")
    line = " · ".join(parts) + "."
    if s["unknown"]:
        line += (f" {_plural(s['unknown'], 'earlier trade')} with no recorded cost "
                 "not counted.")
    return line


def _sold_line(rows: list[dict]) -> str:
    if not any(r["sales"] for r in rows):
        return "No sales by the advisor yet."
    bits = []
    for r in sorted(rows, key=lambda r: -r["horizon_td"]):
        h = r["horizon_td"]
        if r["graded"]:
            bits.append(f"at {h} sessions {r['beat']} of {r['graded']} "
                        f"({r['share_pct']:.0f}%)")
        else:
            bits.append(f"at {h} sessions none graded yet")
    line = "Stocks that beat the Nifty after we sold them: " + "; ".join(bits) + "."
    extra = []
    for r in sorted(rows, key=lambda r: -r["horizon_td"]):
        if r["pending"]:
            extra.append(f"{r['pending']} still short of {r['horizon_td']} sessions")
        if r["ungraded"]:
            extra.append(f"{r['ungraded']} past {r['horizon_td']} sessions with no "
                         "grade (missing price or benchmark)")
    if extra:
        joined = "; ".join(extra)
        line += " " + joined[0].upper() + joined[1:] + "."
    return line


def _money_part(label: str, m: dict) -> str:
    if not m.get("available"):
        reason = m.get("reason")
        if reason == "younger":
            reason = "the portfolio is newer than that"
        return f"{label} unavailable ({reason})"
    gap = m["gap_points"]
    side = ("level" if abs(gap) < 0.05 else
            f"{abs(gap):.1f} points {'ahead' if gap > 0 else 'behind'}")
    return f"{label} {_pct(m['portfolio_pct'])} against {_pct(m['nifty_pct'])} ({side})"


def scorecard_lines(row: dict) -> list[dict]:
    """The scorecard as labelled sentences, red flags first. The email text
    and the app render these same lines, so they cannot disagree."""
    lines: list[dict] = []
    for f in row["red_flags"]:
        if f["status"] == FIRED:
            lines.append({"kind": "red_flag", "text": f["sentence"]})
    for f in row["red_flags"]:
        if f["status"] == UNKNOWN:
            lines.append({"kind": "unchecked", "text": f["sentence"]})
    ct = row["closed_trades"]
    lines.append({"kind": "line", "label": "Closed trades",
                  "text": _trades_line("This week", ct["week"]) + " "
                  + _trades_line("Since the start", ct["since_start"])})
    lines.append({"kind": "line", "label": "Sold too early",
                  "text": _sold_line(row["sold_too_early"]["since_start"])})
    reasons = row["exit_reasons"]["last_4_weeks"]
    if reasons["sales"]:
        text = (f"{_plural(reasons['sales'], 'sale')} in the last {THESIS_WINDOW_WEEKS} "
                "weeks: " + "; ".join(f"{r['label']} {r['count']}"
                                       for r in reasons["reasons"]) + ".")
    else:
        text = f"No sales in the last {THESIS_WINDOW_WEEKS} weeks."
    lines.append({"kind": "line", "label": "Why we sold", "text": text})
    money = row["vs_nifty"]
    text = ("Same deposits on the same days, cash included: "
            + "; ".join([_money_part("this week", money["week"]),
                         _money_part("since the start", money["since_start"])]) + ".")
    if money.get("stale"):
        text += (" No valuation was recorded this week" +
                 (f"; the last was on {_short_day(row['valuation_date'])}."
                  if row.get("valuation_date") else "."))
    lines.append({"kind": "line", "label": "You vs the Nifty", "text": text})
    b = row["breadth"]
    parts = []
    if b["holdings"] is not None:
        parts.append(_plural(b["holdings"], "holding"))
    if b["invested_pct"] is not None:
        parts.append(f"{b['invested_pct']:.0f}% of the money invested")
    text = (", ".join(parts) + f" ({_short_day(b['as_of'])})." if parts
            else "Not recorded for this week.")
    floor = b.get("floor") or {}
    if floor.get("min_holdings"):
        text += f" Floor: {floor['min_holdings']} holdings."
    lines.append({"kind": "line", "label": "Breadth", "text": text})
    hp = row["holding_period"]
    if hp["closed"] and hp["median_sessions"] is not None:
        text = (f"Positions closed this week were held a median of "
                f"{hp['median_sessions']:g} sessions.")
        if hp["unknown"]:
            text += f" {hp['unknown']} with no recorded purchase date."
    elif hp["closed"]:
        text = "Positions closed this week have no recorded purchase date."
    else:
        text = "No position was closed this week."
    lines.append({"kind": "line", "label": "Holding period", "text": text})
    for f in row["red_flags"]:
        if f["status"] in (CLEAR, NOT_ENOUGH):
            lines.append({"kind": "check", "status": f["status"], "text": f["sentence"]})
    return lines


def render_scorecard_text(row: dict | None) -> list[str]:
    """Text lines for the weekly email, opening with the red flags."""
    if not row:
        return ["Results: could not be computed this week."]
    first, last = row["sessions"]["first"], row["sessions"]["last"]
    span = (f"{_short_day(first)} – {_short_day(last)} {last[:4]}" if first and last
            else f"week {row['week']}")
    out = [f"Results for {span} ({row['week']})"]
    for line in row.get("lines") or []:
        if line["kind"] == "red_flag":
            out.append(f"RED FLAG: {line['text']}")
        elif line["kind"] == "unchecked":
            out.append(f"COULD NOT CHECK: {line['text']}")
        elif line["kind"] == "line":
            out.append(f"{line['label']}: {line['text']}")
        else:
            out.append(f"Checked, {'no flag' if line['status'] == CLEAR else 'too few to judge'}: "
                       f"{line['text']}")
    out.append("A flag reports; it changes no decision. Figures are before costs "
               "and taxes.")
    return out


# -- I/O wrapper ----------------------------------------------------------------------

def _floor() -> dict | None:
    """The breadth floor, once configured (portfolio.min_holdings)."""
    from backend.shared.config.settings.loader import cfg
    value = cfg("portfolio.min_holdings", fallback=None)
    try:
        return {"min_holdings": int(value)} if value else None
    except (TypeError, ValueError):
        logger.warning("[results] portfolio.min_holdings %r is not a whole number; "
                       "no floor shown", value)
        return None


def _today() -> date:
    from core.intelligence.rl.nse_calendar import now_ist
    return now_ist().date()


def weekly_scorecard(user_id: str, on: date, *, store=None, audit_store=None,
                     close_on: Callable[[date], float] | None = None,
                     today: date | None = None) -> dict:
    """The row for the week `on` covers, stored once per week key.

    An existing row for the week is returned untouched: a re-run rewrites
    nothing and appends nothing. A week whose sessions are not over yet (a
    future `on`) is computed but never stored, and says so."""
    from core.audit.store import AuditOutcomeStore
    from core.portfolio.store import PortfolioStore

    store = store or PortfolioStore(user_id=user_id)
    week = covered_week(on)
    existing = store.load_scorecard(week.key)
    if existing is not None:
        return existing
    audit_store = audit_store or AuditOutcomeStore(user_id=store.user_id,
                                                   base_dir=store.base_dir)
    if close_on is None:
        from core.audit.benchmark import BenchmarkSeries
        close_on = BenchmarkSeries().close_on
    today = today or _today()
    latest = covered_week(today).key == week.key
    row = build_row(
        week=week,
        txns=store.load_transactions(limit=1_000_000),
        points=store.load_value_history(limit=1_000_000),
        audit_rows=audit_store.load_all(),
        close_on=close_on,
        holdings=len(store.load().holdings) if latest else None,
        floor=_floor(),
    )
    if today < week.saturday:
        row["provisional"] = True
        return row
    stored, _appended = store.append_scorecard_once(row)
    return stored
