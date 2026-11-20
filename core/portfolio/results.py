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
  person who kept it in an index fund. A holding that arrives without cash
  (Add holding, a CSV import) raises capital_in by its cost, so it is valued
  instead at its close on the date of the first valuation that holds it: its
  gain before it arrived is not the portfolio's. The portfolio screen draws
  the same comparison as a line (`portfolio_vs_nifty`).
- **Idea quality** from the auditor's shelf-lane grades: how discovery's
  ideas did against the Nifty 10 and 30 sessions after they were shelved,
  whether or not the portfolio bought them. It measures the idea supply.
- **By exit reason** (PR-013) from the same round trips: each closed trade
  under exactly one reason, the one its closing sale was made for, over the
  last 13 weeks and since the start.
- **Bought back** (PR-013) from the ledger alone: a stock bought again after
  a sale emptied its position, and the charges on that sale and that buy.
- **At prices that could be had** (PR-016) from executable_prices.jsonl: the
  book again with each autopilot trade at the next session's open and at the
  open after the run that booked it (core/portfolio/executable.py).

The red-flag rules below were predeclared on 11-12 Oct 2026, before any
scorecard existed; `paper_prices` (executable.rule_flag) on PR-016's card on
15 Nov 2026, before any executable price was read. Changing one is a reviewed
code change, never a setting tuned after seeing a result. A flag reports; it
changes no decision.

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
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Callable, Iterable, NamedTuple

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

IDEA_QUALITY_TD = (10, 30)      # shelf ideas against the Nifty (a line, not a flag; PR-004)
REASON_WEEKS = 13               # closed trades by exit reason over this many weeks (PR-013)
BUYBACK_WEEKS = 4               # stocks bought back after a sale, over this many weeks (PR-013)
# An EXIT's triggers in the order the advisor checks them (advisor.decide): a
# trade whose closing EXIT carries more than one counts once, under the first.
EXIT_REASONS = (
    ("stop_breach", "stop"),
    ("case_broken", "case broken"),
    ("thesis_break", "price-path exit"),
    ("shock_reforecast", "shock"),
    ("crisis_regime_bearish", "crisis"),
    ("trailing_stop_breach", "trailing stop"),
)
REASON_LABELS = dict(EXIT_REASONS, switch="SWITCH sale", trim="TRIM", manual="sold by you",
                     other="other (no reason recorded)")

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
    verdict: str = ""        # the closing sale's: EXIT / SWITCH / TRIM; "" for your own
    triggers: tuple[str, ...] = ()   # the closing sale's trigger codes, as recorded

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
                             source=t.source, verdict=t.verdict or "",
                             triggers=tuple(t.triggers or ())))
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


def idea_quality(rows: Iterable, horizon: int, *, as_of: date) -> dict:
    """How shelf ideas did against the Nifty `horizon` sessions after they
    were shelved: the auditor's shelf-lane grades that matured by `as_of`.
    `beat` counts excess over the Nifty above zero. A shelf idea is research,
    not a call, so this measures the idea supply, not the portfolio."""
    excess: dict[str, float] = {}
    for r in rows:
        if r.lane != "shelf" or int(r.horizon_td) != horizon:
            continue
        if (_day(r.graded_on) or date.max) > as_of:
            continue
        excess.setdefault(r.ref, float(r.excess_pct))
    values = list(excess.values())
    beat = sum(1 for v in values if v > 0)
    return {"horizon_td": horizon, "graded": len(values), "beat": beat,
            "share_pct": (beat / len(values) * 100.0) if values else None,
            "median_excess_pct": statistics.median(values) if values else None}


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


def trade_reason(trade: Trade) -> str:
    """The one reason a closed trade is counted under (PR-013): the reason its
    closing sale was made for. A SWITCH is "switch" and a TRIM that sold the
    last share "trim", whatever their triggers. An EXIT is its first trigger
    in EXIT_REASONS (the advisor's order of checks); an EXIT with none of them
    is the first of its codes in alphabetical order, so a rule without a name
    here still shows, and one with no code at all is "other". The order the
    codes were recorded in never matters. A sale you made is "manual"; any
    other sale with no advisor verdict is "other". Never two reasons, never
    none."""
    verdict = (trade.verdict or "").strip().upper()
    if verdict == "SWITCH":
        return "switch"
    if verdict == "TRIM":
        return "trim"
    codes = [str(c) for c in trade.triggers if c]
    if verdict == "EXIT":
        return next((code for code, _ in EXIT_REASONS if code in codes),
                    min(codes) if codes else "other")
    return "manual" if trade.source == "manual" else "other"


def _exit_codes(trade: Trade) -> int:
    """How many named exit reasons a trade's closing EXIT carries (0 for any
    other sale: a SWITCH or TRIM is counted under its verdict)."""
    if (trade.verdict or "").strip().upper() != "EXIT":
        return 0
    known = dict(EXIT_REASONS)
    return sum(1 for c in set(trade.triggers) if c in known)


def reason_label(code: str) -> str:
    return REASON_LABELS.get(code, str(code).replace("_", " "))


def results_by_reason(trades: Iterable[Trade], start: date | None, end: date) -> dict:
    """Closed trades in [start, end] (from the first when `start` is None),
    in total and per reason (`trade_reason`), each with trade_stats' count,
    wins and average win, losses and average loss, and mean result.
    `several_triggers` counts the trades whose closing EXIT named more than
    one exit reason: each is counted once, under the first."""
    window = [t for t in trades if (start is None or start <= t.closed) and t.closed <= end]
    groups: dict[str, list[Trade]] = defaultdict(list)
    for t in window:
        groups[trade_reason(t)].append(t)
    reasons = [{"code": code, "label": reason_label(code), **trade_stats(ts)}
               for code, ts in groups.items()]
    reasons.sort(key=lambda r: (-r["count"], r["label"].lower()))
    return {"from": start.isoformat() if start else None, "to": end.isoformat(),
            "all": trade_stats(window), "reasons": reasons,
            "several_triggers": sum(1 for t in window if _exit_codes(t) > 1)}


def buy_backs(txns: Iterable) -> list[dict]:
    """Every stock bought again after a sale emptied its position (PR-013),
    from the ledger alone: the BUY that reopened it and the SELL that closed
    it before. A round trip's charges are those two rows' recorded costs;
    None when either row carries none (written before costs were charged).
    A top-up of a position still held is not a buy-back."""
    closing: dict[str, object] = {}
    out: list[dict] = []
    for t in _in_order(txns):
        if t.side == "SELL" and float(t.holding_qty_after) <= _FLAT_QTY:
            closing[t.symbol] = t
        elif t.side == "BUY" and t.symbol in closing:
            sold = closing.pop(t.symbol)
            charges = None
            if sold.costs is not None and t.costs is not None:
                charges = float(sold.costs.total) + float(t.costs.total)
            out.append({"symbol": t.symbol, "sold_on": _day(sold.date).isoformat(),
                        "bought_on": _day(t.date).isoformat(), "charges": charges,
                        "sold_by": "you" if sold.source == "manual" else (sold.verdict or "")})
    return out


def buy_back_summary(backs: Iterable[dict], start: date | None, end: date) -> dict:
    """Buy-backs whose BUY is in [start, end] (from the first when `start` is
    None): how many, how many stocks, and the charges known on them."""
    window = [b for b in backs
              if (start is None or start <= _day(b["bought_on"])) and _day(b["bought_on"]) <= end]
    known = [b["charges"] for b in window if b["charges"] is not None]
    return {"from": start.isoformat() if start else None, "to": end.isoformat(),
            "count": len(window), "stocks": len({b["symbol"] for b in window}),
            "charges": sum(known) if known else None,
            "no_charges": len(window) - len(known),
            "round_trips": window}


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


class Flow(NamedTuple):
    """Money in (or out) at a value point, dated at the first point that
    shows it. `amount` is None when part of it could not be valued; `note`
    then says why, in words for the screen and the scorecard."""
    day: date
    amount: float | None
    note: str = ""


IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class Arrival:
    """A holding that arrived without cash: Add holding or a CSV import on an
    account with cash accounting. Its ledger row is a BUY by "manual" whose
    cash did not move; `cost` (qty × the buy-date close or a typed price) is
    what capital_in rose by."""
    txn_id: str
    at: datetime | None       # when it was recorded (the row's ts), aware
    day: date                 # that moment's IST date
    symbol: str
    qty: float
    cost: float


def _instant(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def in_kind_arrivals(txns: Iterable) -> list[Arrival]:
    """Every holding that arrived without cash, once per ledger row."""
    out: list[Arrival] = []
    seen: set[str] = set()
    for t in txns:
        if t.side != "BUY" or t.source != "manual" or t.txn_id in seen:
            continue
        if abs(float(t.cash_after) - float(t.cash_before)) > 0.005 or t.qty <= 0:
            continue
        seen.add(t.txn_id)
        at = _instant(t.ts)
        day = at.astimezone(IST).date() if at else _day(t.date)
        if day is None:
            continue
        out.append(Arrival(t.txn_id, at, day, t.symbol, float(t.qty), float(t.value)))
    return sorted(out, key=lambda a: (a.day, a.at or datetime.min.replace(tzinfo=timezone.utc)))


def _arrival_point(a: Arrival, pts: list[dict]) -> tuple[int | None, bool]:
    """(index of the first value point that holds the arrival, ambiguous).
    The index is None when no point holds it yet. Ambiguous: a point written
    before value points recorded their time is dated the arrival's own day,
    so it may have been taken before the holding arrived, or after."""
    for i, p in enumerate(pts):
        taken = _instant(p.get("recorded_at")) if p.get("recorded_at") else None
        if taken is not None and a.at is not None:
            if taken > a.at:
                return i, False
            continue
        if p["_day"] > a.day:
            return i, False
        if p["_day"] == a.day:
            return i, True
    return None, False


def capital_flows(points: Iterable[dict], txns: Iterable = (),
                  stock_close_on: Callable[[str, date], float] | None = None) -> list[Flow]:
    """Each change in capital_in between value points, dated at the point
    that first shows it (the first point's capital_in is the opening
    deposit), with every holding that arrived in it valued at the stock's
    close on that point's date instead of its cost: a backdated add of shares
    bought at ₹50 and worth ₹150 brings ₹150 of money in, not ₹50.

    A flow is unknown (amount None) when an arrival in it has no close that
    day, or when it cannot be told which point first held the arrival.

    A point lists in `at_cost` the holdings it valued at their cost for want
    of a close. An arrival its first point valued so cannot be valued as
    money in: that flow is unknown, and so is the one at the first later
    point that values it at a close (its jump from cost to that close is not
    a gain). The pipeline fetches a close for every holding before the point,
    so this happens only when the stock's close cannot be found."""
    pts = _value_points(points)
    adjust: dict[int, float] = defaultdict(float)
    unknown: dict[int, str] = {}
    for a in in_kind_arrivals(txns):
        i, ambiguous = _arrival_point(a, pts)
        if i is None:
            continue
        if ambiguous:
            # Its cost is in this point's rise in capital_in or the next
            # one's. Any period that holds the next rise also holds this
            # unknown flow or follows it with money moving, so vs_nifty
            # reads it unavailable as well.
            unknown.setdefault(i, f"could not tell whether {a.symbol}, added on "
                                  f"{_short_day(a.day.isoformat())}, was in that day's valuation")
            continue
        if a.symbol in (pts[i].get("at_cost") or ()):
            why = (f"no close for {a.symbol} on {_short_day(pts[i]['_day'].isoformat())}, "
                   "the day it was added: valued at its cost")
            unknown.setdefault(i, why)
            j = next((k for k in range(i + 1, len(pts))
                      if a.symbol not in (pts[k].get("at_cost") or ())), None)
            if j is not None:
                unknown.setdefault(j, why)
            continue
        on = pts[i]["_day"]
        try:
            close = float(stock_close_on(a.symbol, on)) if stock_close_on else 0.0
        except Exception as exc:
            logger.info("[results] no close for %s on %s: %s", a.symbol, on, exc)
            close = 0.0
        if close <= 0:
            unknown.setdefault(i, f"no close for {a.symbol} on "
                                  f"{_short_day(on.isoformat())}, the day it was added")
            continue
        adjust[i] += a.qty * close - a.cost
    out: list[Flow] = []
    previous = 0.0
    for i, p in enumerate(pts):
        cap = p.get("capital_in")
        if not isinstance(cap, (int, float)):
            continue
        delta = float(cap) - previous
        previous = float(cap)
        if i in unknown:
            out.append(Flow(p["_day"], None, unknown[i]))
            continue
        amount = delta + adjust.get(i, 0.0)
        if abs(amount) > 0.005:
            out.append(Flow(p["_day"], amount))
    return out


def nifty_equivalent(deposits: Iterable[tuple],
                     close_on: Callable[[date], float], on: date) -> float:
    """What the same deposits are worth at `on`'s close, had each bought the
    Nifty at its own day's close. Raises if any close is missing, or a
    deposit up to `on` could not be valued."""
    units = 0.0
    for d, amount, *_ in deposits:
        if d <= on:
            if amount is None:
                raise ValueError(f"a deposit on {d} could not be valued")
            close = float(close_on(d))
            if close <= 0:
                raise ValueError(f"non-positive Nifty close on {d}")
            units += amount / close
    end_close = float(close_on(on))
    if end_close <= 0:
        raise ValueError(f"non-positive Nifty close on {on}")
    return units * end_close


def vs_nifty(points: Iterable[dict], close_on: Callable[[date], float], *,
             end: date, start: date | None = None,
             flows: Iterable[Flow] | None = None) -> dict:
    """The portfolio against the same money in the Nifty, from the last value
    point before `start` (None: from the first deposit) to the last one on or
    before `end`. `flows` defaults to the changes in capital_in at cost; the
    callers pass `capital_flows`, which values arrivals on their day.

    Both returns use the same flows: (end − start − deposits) / (start +
    deposits). The portfolio's figure includes its idle cash; the Nifty's
    holds none.

    A flow that could not be valued makes the comparison unavailable when it
    falls in the period, or when it falls before it and money moved in the
    period (the Nifty side's weights then depend on it). Before a period with
    no flow at all, the Nifty side's units are constant, so its return is
    the index's own move and is still known."""
    pts = _value_points(points)
    deposits = (list(flows) if flows is not None
                else [Flow(d, a) for d, a in deposits_from_values(pts)])
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
    inside = [f for f in deposits
              if (start_day is None or f.day > start_day) and f.day <= end_day]
    unvalued = [f for f in deposits if f.amount is None and f.day <= end_day]
    if unvalued and (start_day is None or inside):
        return {"available": False, "reason": unvalued[0].note or "a deposit could not be valued",
                "to": end_day.isoformat()}
    flows_in = sum(f.amount for f in inside)
    try:
        if unvalued:
            # Units unknown but constant over the period: the index's move.
            nifty_start = nifty_end = None
            nifty_pct = (float(close_on(end_day)) / float(close_on(start_day)) - 1.0) * 100.0
        else:
            nifty_start = nifty_equivalent(deposits, close_on, start_day) if start_day else 0.0
            nifty_end = nifty_equivalent(deposits, close_on, end_day)
    except Exception as exc:
        logger.info("[results] Nifty comparison unavailable: %s", exc)
        return {"available": False, "reason": "no Nifty close for a needed day",
                "to": end_day.isoformat()}
    if start_equity + flows_in <= 0 or (nifty_start is not None
                                        and nifty_start + flows_in <= 0):
        return {"available": False, "reason": "no money invested yet",
                "to": end_day.isoformat()}
    portfolio_pct = (end_equity - start_equity - flows_in) / (start_equity + flows_in) * 100.0
    if nifty_start is not None:
        nifty_pct = (nifty_end - nifty_start - flows_in) / (nifty_start + flows_in) * 100.0
    return {"available": True,
            "from": start_day.isoformat() if start_day else None,
            "to": end_day.isoformat(),
            "portfolio_pct": portfolio_pct, "nifty_pct": nifty_pct,
            "gap_points": portfolio_pct - nifty_pct,
            "portfolio_value": end_equity, "nifty_value": nifty_end,
            "deposits": flows_in}


def nifty_line(points: Iterable[dict], flows: Iterable[Flow],
               close_on: Callable[[date], float]) -> list[float | None]:
    """For each value point (ascending, one per date), what the deposits made
    up to it would be worth in the Nifty at its close. None where that is not
    known: before any deposit, with no close that day, or from the first flow
    that could not be valued on. Never a carried-forward or flat value."""
    pts = _value_points(points)
    flows = sorted(flows, key=lambda f: f.day)
    out: list[float | None] = []
    units, k, broken = 0.0, 0, False
    for p in pts:
        while k < len(flows) and flows[k].day <= p["_day"]:
            f = flows[k]
            k += 1
            if broken:
                continue
            try:
                close = float(close_on(f.day)) if f.amount is not None else 0.0
            except Exception as exc:
                logger.debug("[results] no Nifty close for the deposit on %s: %s", f.day, exc)
                close = 0.0
            if close <= 0:
                broken = True      # units unknown from here on
                continue
            units += f.amount / close
        if broken or units <= 0:
            out.append(None)
            continue
        try:
            close = float(close_on(p["_day"]))
        except Exception as exc:
            logger.debug("[results] no Nifty close on %s: %s", p["_day"], exc)
            close = 0.0
        out.append(units * close if close > 0 else None)
    return out


def portfolio_vs_nifty(points: Iterable[dict], txns: Iterable, *,
                       close_on: Callable[[date], float],
                       stock_close_on: Callable[[str, date], float] | None,
                       ranges: dict[str, int]) -> dict:
    """The portfolio screen's comparison: the Nifty line under each value
    point, the gap at the last one (since the first deposit, in rupees and in
    points of return), and each range's money-weighted return beside the
    Nifty's. A range of n points runs from the n-th last point to the last,
    as the chart shows it. The same functions as the weekly scorecard."""
    pts = _value_points(points)
    flows = capital_flows(pts, txns, stock_close_on)
    line = nifty_line(pts, flows, close_on)
    first = next((f.day for f in flows if f.amount is None or f.amount > 0), None)
    if not pts:
        since = {"available": False, "reason": "no valuation recorded yet"}
    else:
        since = vs_nifty(pts, close_on, end=pts[-1]["_day"], flows=flows)
    since["first_deposit"] = first.isoformat() if first else None
    if since.get("available") and since.get("nifty_value") is not None:
        since["gap_inr"] = since["portfolio_value"] - since["nifty_value"]
    windows: dict[str, dict] = {}
    for key, n in ranges.items():
        if len(pts) < 2:
            windows[key] = {"available": False, "reason": "not enough valuations yet"}
            continue
        i = max(0, len(pts) - int(n))
        windows[key] = vs_nifty(pts, close_on, end=pts[-1]["_day"],
                                start=pts[i + 1]["_day"], flows=flows)
    return _rounded({
        "line": [{"date": p["_day"].isoformat(), "nifty_value": v} for p, v in zip(pts, line)],
        "since_start": since,
        "ranges": windows,
        "flows": [{"date": f.day.isoformat(), "amount": f.amount, "note": f.note or None}
                  for f in flows],
    })


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
              computed_at: str | None = None,
              stock_close_on: Callable[[str, date], float] | None = None,
              exit_shadow_rows: Iterable[dict] | None = None,
              previous_exit_look: dict | None = None,
              stock_quote_on: Callable[[str, date], object] | None = None,
              corp_actions: Callable[[str], object] | None = None,
              stock_series_on: Callable[[str, date], object] | None = None,
              executable_rows: Iterable[dict] | None = None) -> dict:
    """The scorecard row for `week` from the user's own ledgers. Facts dated
    after the week are ignored, so a late rebuild describes the week as it was.
    `stock_close_on(symbol, day)` values the holdings that arrived without
    cash (capital_flows).

    PR-009: with `exit_shadow_rows`, the row gains `exit_rule`, the two exit
    rules' tally and this week's look at the switch gate
    (core/portfolio/exit_shadow.py); `previous_exit_look` is the look stored
    with the week before. The disagreements are graded at
    `stock_quote_on(symbol, day)` (the close with its bar and source) in the
    price basis `corp_actions(symbol)` establishes (FIX-016).

    PR-013: the row also gains the closed trades by exit reason and the
    stocks bought back after a sale, from the ledger; and, with
    `exit_shadow_rows`, `waiting_cost` (the fall each stock the evidence rule
    kept went through, from `stock_series_on(symbol, since)`'s daily closes)
    and `gate_pace`. Reports: they change no decision.

    PR-016: with `executable_rows` (the side file's rows,
    core/portfolio/executable.py), the row gains `executable`, the book at
    prices that could be had, and the red flag `paper_prices`, its
    predeclared rule. A report: it changes no trade or price."""
    end = week.sunday
    txns = [t for t in txns if (_day(t.date) or date.max) <= end]
    points = [p for p in points if (_day(p.get("date")) or date.max) <= end]
    audit_rows = list(audit_rows)
    flows = capital_flows(points, txns, stock_close_on)
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
        "week": vs_nifty(points, close_on, end=end, start=week.monday, flows=flows),
        "last_4_weeks": vs_nifty(points, close_on, end=end,
                                 start=week.window_start(NIFTY_WINDOW_WEEKS), flows=flows),
        "since_start": vs_nifty(points, close_on, end=end, flows=flows),
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
    executable = None
    if executable_rows is not None:
        from core.portfolio.executable import rule_flag, scorecard_block
        executable = scorecard_block(txns, executable_rows, end=end,
                                     since_start=money["since_start"])
        flags.append(rule_flag(executable))
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
        "idea_quality": [idea_quality(audit_rows, h, as_of=end) for h in IDEA_QUALITY_TD],
        "by_reason": {"last_13_weeks": results_by_reason(
                          trades, week.window_start(REASON_WEEKS), end),
                      "since_start": results_by_reason(trades, None, end)},
    }
    if executable is not None:
        row["executable"] = executable
    backs = buy_backs(txns)
    row["bought_back"] = {"last_4_weeks": buy_back_summary(
                              backs, week.window_start(BUYBACK_WEEKS), end),
                          "since_start": buy_back_summary(backs, None, end)}
    if exit_shadow_rows is not None:
        from core.portfolio.exit_shadow import gate_pace, scorecard_block, waiting_cost
        exit_shadow_rows = list(exit_shadow_rows)
        row["exit_rule"] = scorecard_block(
            exit_shadow_rows, as_of=end, stock_quote_on=stock_quote_on,
            bench_close_on=close_on, corp_actions=corp_actions,
            previous_look=previous_exit_look)
        row["waiting_cost"] = waiting_cost(
            exit_shadow_rows, as_of=end, stock_series=stock_series_on,
            corp_actions=corp_actions)
        row["gate_pace"] = gate_pace(exit_shadow_rows, week_monday=week.monday, as_of=end)
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


def _ideas_line(rows: list[dict]) -> str:
    if not any(r["graded"] for r in rows):
        return "No shelf idea has been graded against the Nifty yet."
    bits = []
    for r in sorted(rows, key=lambda r: -r["horizon_td"]):
        if r["graded"]:
            bits.append(f"at {r['horizon_td']} sessions {r['beat']} of {r['graded']} beat it "
                        f"({r['share_pct']:.0f}%, median {r['median_excess_pct']:+.1f} points)")
        else:
            bits.append(f"at {r['horizon_td']} sessions none graded yet")
    return "Shelf ideas against the Nifty after they were shelved: " + "; ".join(bits) + "."


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


def _reason_part(r: dict) -> str:
    """One reason (or the total) as "-2.2% a trade (4 won, average +7.5%; 4
    lost, average -11.9%)"."""
    if not r["known"]:
        return "no recorded cost"
    bits = [f"{r['wins']} won" + (f", average {_pct(r['avg_win_pct'])}"
                                  if r["avg_win_pct"] is not None else "")]
    bits.append(f"{r['losses']} lost" + (f", average {_pct(r['avg_loss_pct'])}"
                                        if r["avg_loss_pct"] is not None else ""))
    text = f"{_pct(r['expectancy_pct'])} a trade ({'; '.join(bits)})"
    if r["unknown"]:
        text += f", {r['unknown']} with no recorded cost"
    return text


def _by_reason_text(label: str, block: dict) -> str:
    total = block["all"]
    if not total["count"]:
        return f"{label}: no closed trades."
    text = (f"{label}: {_plural(total['count'], 'closed trade')}, "
            f"{_reason_part(total)}. By reason: "
            + "; ".join(f"{r['label']} {r['count']}, {_reason_part(r)}"
                        for r in block["reasons"]) + ".")
    if block.get("several_triggers"):
        n = block["several_triggers"]
        text += (f" {n} {'was' if n == 1 else 'were'} sold on more than one reason, "
                 "counted once, under the first the advisor checks.")
    return text


def _by_reason_line(block: dict) -> str:
    recent, start = block["last_13_weeks"], block["since_start"]
    if not start["all"]["count"]:
        return "No closed trades yet."
    text = _by_reason_text(f"Last {REASON_WEEKS} weeks", recent)
    if start["all"]["count"] == recent["all"]["count"]:
        text += " Since the start: the same trades."
    else:
        text += " " + _by_reason_text("Since the start", start)
    return text + " Before costs."


def _bought_back_line(block: dict) -> str:
    recent, start = block["last_4_weeks"], block["since_start"]
    if not start["count"]:
        return "No stock has been bought again after a sale emptied its position."
    from core.portfolio.sizing import inr

    def part(b: dict) -> str:
        if not b["count"]:
            return "none"
        text = str(b["count"])
        if b["stocks"] != b["count"]:
            text += f" ({_plural(b['stocks'], 'stock')})"
        if b["charges"] is not None:
            text += f", {inr(b['charges'])} of charges on those sales and buys back"
        if b["no_charges"]:
            text += f", {b['no_charges']} with none recorded"
        return text
    return (f"Last {BUYBACK_WEEKS} weeks: {part(recent)}. Since the start: {part(start)}. "
            "Each is a stock bought again after a sale emptied its position.")


def _waiting_line(block: dict) -> str:
    if not block["kept"]:
        return ("No decision yet in which the evidence rule kept a stock the price-path "
                "rule sold.")
    bits, extra = [], []
    for h in block["horizons"]:
        if h["graded"]:
            bits.append(f"within {h['horizon_td']} sessions, median {_pct(h['median_fall_pct'])}"
                        f" and worst {_pct(h['worst_fall_pct'])} ({h['worst_symbol']}), "
                        f"over {h['graded']}")
        else:
            bits.append(f"within {h['horizon_td']} sessions none graded yet")
        if h["pending"]:
            extra.append(f"{h['pending']} short of {h['horizon_td']} sessions")
        if h["no_result"]:
            extra.append(f"{h['no_result']} with no result at {h['horizon_td']} sessions "
                         f"(a close missing or a corporate action: "
                         f"{', '.join(h['no_result_symbols'])})")
    text = (f"The evidence rule kept {_plural(block['kept'], 'holding')} the price-path rule "
            "sold. Their lowest close after the decision, against its close: "
            + "; ".join(bits) + ".")
    if extra:
        joined = "; ".join(extra)
        text += " " + joined[0].upper() + joined[1:] + "."
    return text


def _pace_line(p: dict) -> str:
    text = (f"{p['per_week']:g} decision{'' if p['per_week'] == 1 else 's'} a week over the "
            f"last {p['weeks']} weeks ({p['recent']}); {p['decisions']} in all")
    text += f" since {_short_day(p['first'])}." if p.get("first") else "."
    if p.get("already"):
        return text + " The gate already has the decisions it needs to judge."
    if not p.get("first_pass_week"):
        return text + " No decision in the last 4 weeks, so no date can be given."
    first, rec = _day(p["first_pass_week"]), _day(p["recommend_week"])
    return (text + f" At this pace the gate can first pass in the week of "
            f"{first.day} {first.strftime('%b %Y')}, and two weeks running in the week of "
            f"{rec.day} {rec.strftime('%b %Y')} (arithmetic, not a forecast).")


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
    if row.get("by_reason"):
        lines.append({"kind": "line", "label": "By exit reason",
                      "text": _by_reason_line(row["by_reason"])})
    lines.append({"kind": "line", "label": "Sold too early",
                  "text": _sold_line(row["sold_too_early"]["since_start"])})
    if row.get("idea_quality"):
        lines.append({"kind": "line", "label": "Idea quality",
                      "text": _ideas_line(row["idea_quality"])})
    reasons = row["exit_reasons"]["last_4_weeks"]
    if reasons["sales"]:
        text = (f"{_plural(reasons['sales'], 'sale')} in the last {THESIS_WINDOW_WEEKS} "
                "weeks: " + "; ".join(f"{r['label']} {r['count']}"
                                       for r in reasons["reasons"]) + ".")
    else:
        text = f"No sales in the last {THESIS_WINDOW_WEEKS} weeks."
    lines.append({"kind": "line", "label": "Why we sold", "text": text})
    if row.get("bought_back"):
        lines.append({"kind": "line", "label": "Bought back",
                      "text": _bought_back_line(row["bought_back"])})
    exit_rule = row.get("exit_rule")
    if isinstance(exit_rule, dict) and exit_rule.get("rows"):
        from core.portfolio.exit_shadow import scorecard_text
        lines.append({"kind": "line", "label": "Exit rule test",
                      "text": scorecard_text(exit_rule)})
        if row.get("waiting_cost"):
            lines.append({"kind": "line", "label": "What waiting cost",
                          "text": _waiting_line(row["waiting_cost"])})
        if row.get("gate_pace"):
            lines.append({"kind": "line", "label": "Decision pace",
                          "text": _pace_line(row["gate_pace"])})
    money = row["vs_nifty"]
    text = ("Same deposits on the same days, cash included: "
            + "; ".join([_money_part("this week", money["week"]),
                         _money_part("since the start", money["since_start"])]) + ".")
    if money.get("stale"):
        text += (" No valuation was recorded this week" +
                 (f"; the last was on {_short_day(row['valuation_date'])}."
                  if row.get("valuation_date") else "."))
    lines.append({"kind": "line", "label": "You vs the Nifty", "text": text})
    if row.get("executable"):
        from core.portfolio.executable import line_text
        lines.append({"kind": "line", "label": "At prices that could be had",
                      "text": line_text(row["executable"])})
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
        text += f" Aimed for: at least {floor['min_holdings']} holdings."
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
    """The holdings aimed for, once configured (portfolio.min_holdings: a soft
    minimum, FIX-025)."""
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


@lru_cache(maxsize=1024)
def _cached_stock_close(symbol: str, on: date) -> float:
    from core.portfolio.pricing import close_on
    return close_on(symbol, on)


def stock_close_fn() -> Callable[[str, date], float]:
    """The NSE close an arrival is valued at: the same fetch and walkback as
    the portfolio's marks. A past day's close does not change, so a found one
    is kept for the life of the process; today's (which may not be final)
    and a miss are not kept."""
    def lookup(symbol: str, on: date) -> float:
        if on < _today():
            return _cached_stock_close(symbol, on)
        from core.portfolio.pricing import close_on
        return close_on(symbol, on)
    return lookup


_SETTLED_QUOTES: dict[tuple[str, date], object] = {}
_SETTLED_QUOTES_MAX = 4096


def stock_quote_fn() -> Callable[[str, date], object]:
    """The close an exit-rule decision's horizon is graded at, with its bar
    and source (pricing.session_close, the same fetch as stock_close_fn). A
    past day's quote is kept for the life of the process only when it is
    that day's own bar in NSE's raw basis (NSE's close, or Yahoo's agreeing
    with it): a Yahoo-only close may be adjusted for a later bonus or split,
    and the next read may get NSE's."""
    def lookup(symbol: str, on: date):
        from core.portfolio.exit_shadow import RAW_CLOSE_SOURCES
        from core.portfolio.pricing import session_close
        key = (symbol, on)
        if key in _SETTLED_QUOTES:
            return _SETTLED_QUOTES[key]
        quote, _session = session_close(symbol, on)
        if on < _today() and quote.bar_date == on and quote.source in RAW_CLOSE_SOURCES:
            if len(_SETTLED_QUOTES) >= _SETTLED_QUOTES_MAX:
                _SETTLED_QUOTES.clear()
            _SETTLED_QUOTES[key] = quote
        return quote
    return lookup


def corp_actions_fn() -> Callable[[str], object]:
    """What NSE lists of a symbol's bonuses and splits, and of the changes no
    ratio converts (corp_actions.action_record over read_corp_actions), read once per
    symbol for one scorecard: the exit-rule grading puts each horizon close
    into its decision's price basis with it. NSE is asked for the code its
    close is read under (symbol_resolver.nse_symbol: a registry alias such as
    TVSMOTORS is listed as TVSMOTOR). A list that could not be read is None,
    a gap a later week's read may close; an empty answer is a record of no
    rows (FIX-018)."""
    records: dict[str, object] = {}

    def lookup(symbol: str):
        if symbol not in records:
            from backend.shared.data.fetchers.symbol_resolver import nse_symbol
            from core.portfolio import corp_actions
            from services.data.fetchers import corporate_events
            try:
                records[symbol] = corp_actions.action_record(
                    corporate_events.read_corp_actions(nse_symbol(symbol)), symbol)
            except Exception as exc:
                logger.warning("[results] corporate actions unread for %s: %s", symbol, exc)
                records[symbol] = None
        return records[symbol]
    return lookup


def stock_series_fn() -> Callable[[str, date], list[tuple[date, float]]]:
    """A stock's daily closes from `since`, for the "what waiting cost" line
    (PR-013): one Yahoo download per symbol for one scorecard
    (indicators.fetcher.get_price_history), adjusted for bonuses, splits and
    dividends, so every close in it is in one price basis. A failed or empty
    download is an empty series: the line then says it has no result."""
    held: dict[str, list[tuple[date, float]]] = {}

    def lookup(symbol: str, since: date) -> list[tuple[date, float]]:
        if symbol not in held:
            from core.intelligence.algorithms.indicators.fetcher import get_price_history
            years = max(1, (_today() - since).days // 365 + 1)
            out: list[tuple[date, float]] = []
            try:
                df = get_price_history(symbol, years=years)
                close = df["Close"] if len(df) else None
                if close is not None and hasattr(close, "columns"):
                    close = close.iloc[:, 0]
                if close is not None:
                    out = [(d.date(), float(c)) for d, c in close.dropna().items()]
            except Exception as exc:
                logger.warning("[results] price series unread for %s: %s", symbol, exc)
            held[symbol] = out
        return [(d, c) for d, c in held[symbol] if d >= since]
    return lookup


def weekly_scorecard(user_id: str, on: date, *, store=None, audit_store=None,
                     close_on: Callable[[date], float] | None = None,
                     today: date | None = None,
                     stock_close_on: Callable[[str, date], float] | None = None,
                     stock_quote_on: Callable[[str, date], object] | None = None,
                     corp_actions: Callable[[str], object] | None = None,
                     stock_series_on: Callable[[str, date], object] | None = None,
                     panel_on: Callable[[str, date], object] | None = None) -> dict:
    """The row for the week `on` covers, stored once per week key.

    An existing row for the week is returned untouched: a re-run rewrites
    nothing and appends nothing. A week whose sessions are not over yet (a
    future `on`) is computed but never stored, and says so.

    PR-016: before the row is built, every autopilot trade without a row in
    executable_prices.jsonl is priced at the real opens (`panel_on(symbol,
    day)`, the EOD panel; executable.refresh), and the settled ones are
    written once. A failure there leaves the stored rows to the line."""
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
    from core.portfolio import executable
    from core.portfolio.exit_shadow import previous_week_look
    corp_actions = corp_actions or corp_actions_fn()
    txns = store.load_transactions(limit=1_000_000)
    try:
        executable_rows = executable.refresh(
            store, txns, panel=panel_on or executable.panel_fn(),
            corp_actions=corp_actions, today=today)
    except Exception as exc:
        logger.warning("[results] executable prices not refreshed for %s: %s",
                       store.user_id, exc)
        executable_rows = store.load_executable_prices()
    row = build_row(
        week=week,
        txns=txns,
        points=store.load_value_history(limit=1_000_000),
        audit_rows=audit_store.load_all(),
        close_on=close_on,
        holdings=len(store.load().holdings) if latest else None,
        floor=_floor(),
        stock_close_on=stock_close_on or stock_close_fn(),
        exit_shadow_rows=store.load_exit_shadow(),
        previous_exit_look=previous_week_look(store.load_scorecards(), week.monday),
        stock_quote_on=stock_quote_on or stock_quote_fn(),
        corp_actions=corp_actions,
        stock_series_on=stock_series_on or stock_series_fn(),
        executable_rows=executable_rows,
    )
    if today < week.saturday:
        row["provisional"] = True
        return row
    stored, _appended = store.append_scorecard_once(row)
    return stored
