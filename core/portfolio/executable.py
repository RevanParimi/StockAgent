"""What the paper book earns at prices that could really be had (PR-016).

The 16:30 run on day T reviews session T-1 and books every trade at T-1's
15:30 close (AUTOPILOT_GUIDE section 9). The decision reads nothing from after
that close (FIX-027, FIX-031), so the first price a person could act on it at
is T's open; as the job runs, after T's close, it is the open of the session
after T. This module measures that gap. It changes no trade, no price the
book is kept at and no decision.

Two real prices for every autopilot BUY and SELL in transactions.jsonl, from
NSE's daily bhavcopy (the EOD panel discovery keeps,
services/data/stores/eod_store.py; raw prices as NSE struck them):

- `open_next`: the open of the first session after the booked close's
  session (the row's `date`);
- `open_as_run`: the open of the first session the run that booked it could
  still act at: the run's own day when it ran before the 09:00 pre-open
  auction, else the session after it, and never before `open_next`'s.

So a real price never comes from a bar dated on or before the booked close.

**Price basis.** Each open is put into the booked close's price basis across
every bonus or split that went ex between the two sessions, with the exit
grading's fail-closed rules (exit_shadow.horizon_in_basis over NSE's list,
read when the price is taken; registry_break for a demerger or relisting the
instrument registry records). The booked close is first checked against the
panel's close of its own session: within BOOKED_CLOSE_TOLERANCE_PCT it is
that session's raw NSE close, so a split that goes ex the next morning is
converted (₹100 booked, a 1:2 split, an open of ₹51 is ₹102). Otherwise it
may have been fetched at the run already adjusted, so a bonus or split
between its session and the run leaves the price unknown. A dividend ex
between the two is not added back (the open is lower by about it).

**No price, never a guess.** A price is `no_price` for good when the panel
has no bar for the stock that session, the day's file has not arrived
PANEL_RETRY_DAYS after the session (the daily sync re-reads only that far
back), or the basis cannot be established and no later read can change that.
It is `pending` while it may still come: the session is not over, the file
may still be synced, NSE's list could not be read.

**The side file.** data/portfolio/<user>/executable_prices.jsonl holds one
row per transaction id, written once both prices are settled (priced or no
price); a stored row is never rewritten and the ledger is never touched.

**The book at each price**: the same trades and quantities, the same cost
rates (costs.trade_costs), each BUY paying and each SELL receiving the real
price. A trade with no price, or still pending, keeps its booked close and is
counted on the line. The comparison is the scorecard's own since-start "You
vs the Nifty": the trades' cash difference moves the last valuation, the
Nifty side is unchanged.

**The rule** (card PR-016 step 5, written 15 Nov 2026, before any figure): if
the average round trip loses more than ROUND_TRIP_MAX_LOSS_POINTS points of
return at `open_next`, or the book's lead over the Nifty since the start
changes sign at either price, open a card to book trades at the next
session's open; otherwise paper prices are close enough. Under MIN_CASES
cases it is too few to judge (EDGE-ROADMAP rule 4). It is a red flag on the
scorecard: it reports and changes no decision.

Pure apart from the seams at the bottom (`panel_fn`, `refresh`).
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, time
from typing import Callable, Iterable, NamedTuple

from core.intelligence.rl.nse_calendar import IST, is_trading_day, next_trading_day
from core.portfolio.exit_shadow import LASTING, _actions, horizon_in_basis, registry_break
from core.portfolio.results import (CLEAR, FIRED, NOT_ENOUGH, UNKNOWN, _FLAT_QTY, _day,
                                    _flag, _in_order, _pct, _plural)

logger = logging.getLogger(__name__)

# -- The rule, predeclared on the card (15 Nov 2026); the owner may change 0.5 before
#    the first look ---------------------------------------------------------------------
ROUND_TRIP_MAX_LOSS_POINTS = 0.5    # average round trip at open_next, points of return
MIN_CASES = 30                      # round trips, and trades priced, before it is judged

BOOKED_CLOSE_TOLERANCE_PCT = 1.0    # the booked price is its session's NSE close within this
PANEL_RETRY_DAYS = 7                # the daily bhavcopy sync re-reads this many days back
PRE_OPEN = time(9, 0)               # orders for the open are entered from the pre-open auction
KINDS = ("open_next", "open_as_run")
SIDES = ("BUY", "SELL")
SERIES_PREFERENCE = ("EQ", "BE", "BZ", "SM", "ST")   # as bhavcopy.fetch_listing
PRICED, NO_PRICE, PENDING = "priced", "no_price", "pending"


class PanelBar(NamedTuple):
    """One stock's bar in one day's panel file."""
    open: float | None       # None: no bar for the stock that day, or no positive open
    close: float | None
    filed: bool              # the day's file is on disk


class _Open(NamedTuple):
    """An open in the shape horizon_in_basis reads (a pricing.SessionClose)."""
    close: float
    bar_date: date
    source: str


def is_autopilot_trade(t) -> bool:
    return (t.source == "autopilot" and t.side in SIDES
            and float(t.qty or 0) > 0 and float(t.price or 0) > 0)


def run_instant(ts) -> datetime | None:
    """The run's time in IST, from the row's UTC timestamp; None when unreadable."""
    try:
        at = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return at.astimezone(IST) if at.tzinfo is not None else None


def first_session_after_run(run: datetime) -> date:
    """The first session whose open a run at `run` (IST) could still act at."""
    day = run.date()
    if is_trading_day(day) and run.time() < PRE_OPEN:
        return day
    return next_trading_day(day)


def _price(session: date, status: str, **kw) -> dict:
    out = {"session": session.isoformat() if session else None, "status": status,
           "open": None, "raw_open": None, "gap_pct": None, "basis": "", "no_price": ""}
    out.update(kw)
    return out


def price_at(t, session: date, *, booked: date, decided: date,
             panel: Callable[[str, date], PanelBar], record: Callable[[], object],
             today: date) -> dict:
    """The open of `session` for trade `t`, in the booked close's price basis.
    `decided` is the last day the booked close's basis may have been set on;
    `record()` is NSE's ActionRecord for the stock (None when unread)."""
    if session <= booked:
        return _price(session, NO_PRICE,
                      no_price="the session is not after the booked close's")
    if session > today:
        return _price(session, PENDING, no_price="the session's bar is not in yet")
    bar = panel(t.symbol, session)
    if not bar.filed:
        if (today - session).days <= PANEL_RETRY_DAYS:
            return _price(session, PENDING,
                          no_price=f"the EOD panel has no file for {session} yet")
        return _price(session, NO_PRICE, no_price=f"the EOD panel has no file for {session}")
    if bar.open is None:
        return _price(session, NO_PRICE, no_price=f"no bar for {t.symbol} on {session}")
    real, note, gap, kind = horizon_in_basis(_Open(float(bar.open), session, "nse"),
                                             record(), booked, decided)
    if real is None:
        return _price(session, NO_PRICE if kind == LASTING else PENDING,
                      raw_open=float(bar.open), no_price=gap)
    broken = registry_break(t.symbol, booked, session)
    if broken:
        return _price(session, NO_PRICE, raw_open=float(bar.open), no_price=broken)
    return _price(session, PRICED, open=real, raw_open=float(bar.open), basis=note,
                  gap_pct=(real / float(t.price) - 1.0) * 100.0)


def price_trade(t, *, panel: Callable[[str, date], PanelBar],
                corp_actions: Callable[[str], object] | None, today: date) -> dict | None:
    """The side-file row of one autopilot BUY or SELL (None for any other row)."""
    booked = _day(t.date)
    if not is_autopilot_trade(t) or booked is None:
        return None
    run = run_instant(t.ts)
    own = panel(t.symbol, booked)
    is_close = (own.close is not None and own.close > 0
                and abs(float(t.price) / own.close - 1.0) * 100.0 <= BOOKED_CLOSE_TOLERANCE_PCT)
    if is_close:
        decided = booked                      # its session's own raw close
    elif run is not None:
        decided = max(run.date(), booked)     # fetched at the run, maybe adjusted
    else:
        decided = date.max                    # fetched when, unknown
    held: list = []

    def record():
        if not held:
            held.append(_actions(corp_actions, t.symbol))
        return held[0]

    common = dict(booked=booked, decided=decided, panel=panel, record=record, today=today)
    following = next_trading_day(booked)
    row = {"txn_id": t.txn_id, "symbol": t.symbol, "side": t.side, "qty": float(t.qty),
           "price": float(t.price), "date": booked.isoformat(),
           "run_at": run.isoformat() if run else "",
           "booked_session_close": own.close, "booked_is_session_close": is_close,
           "open_next": price_at(t, following, **common)}
    if run is None:
        row["open_as_run"] = _price(None, NO_PRICE, no_price="the run's time is not recorded")
    else:
        row["open_as_run"] = price_at(t, max(first_session_after_run(run), following),
                                      **common)
    return row


def settled(row: dict) -> bool:
    return all(row[k]["status"] != PENDING for k in KINDS)


# -- The book at each price ----------------------------------------------------------------

def _status(row: dict | None, kind: str, end: date) -> tuple[str, dict | None]:
    """A row's price of `kind` as known at the week's end: a price from a
    later session is still pending then."""
    p = (row or {}).get(kind)
    if not isinstance(p, dict):
        return PENDING, None
    session = _day(p.get("session"))
    if p.get("status") == PRICED and session is not None and session <= end:
        return PRICED, p
    if p.get("status") == NO_PRICE and (session is None or session <= end):
        return NO_PRICE, p
    return PENDING, p


def cash_effect(t, real: float, rates: dict | None = None) -> float:
    """What trading `t` at `real` instead of its booked price does to cash:
    a BUY pays the difference, a SELL receives it, and a trade whose charges
    were taken from cash pays them on the real value (same rates both ways)."""
    from core.portfolio.costs import trade_costs
    qty, booked = float(t.qty), float(t.price)
    moved = qty * (real - booked)
    charged = t.costs is not None and not t.costs.estimated
    extra = (trade_costs(t.side, qty * real, rates=rates).total
             - trade_costs(t.side, qty * booked, rates=rates).total) if charged else 0.0
    return -moved - extra if t.side == "BUY" else moved - extra


def round_trips(txns: Iterable) -> list[list]:
    """Each position fully sold, as its BUY and SELL rows (the grouping of
    results.closed_trades)."""
    legs: dict[str, list] = {}
    out: list[list] = []
    for t in _in_order(txns):
        if t.side not in SIDES:
            continue
        legs.setdefault(t.symbol, []).append(t)
        if t.side == "SELL" and float(t.holding_qty_after) <= _FLAT_QTY:
            out.append(legs.pop(t.symbol))
    return out


def round_trip_loss(legs: list, prices: dict[str, float]) -> float | None:
    """Points of return a round trip loses when every leg trades at its real
    price (`prices` by txn_id): its return on the booked prices minus its
    return on the real ones. None unless it has a BUY and every leg a price."""
    if not any(t.side == "BUY" for t in legs) or any(t.txn_id not in prices for t in legs):
        return None
    paid = sum(float(t.qty) * float(t.price) for t in legs if t.side == "BUY")
    got = sum(float(t.qty) * float(t.price) for t in legs if t.side == "SELL")
    paid_real = sum(float(t.qty) * prices[t.txn_id] for t in legs if t.side == "BUY")
    got_real = sum(float(t.qty) * prices[t.txn_id] for t in legs if t.side == "SELL")
    if paid <= 0 or paid_real <= 0:
        return None
    return (got / paid - got_real / paid_real) * 100.0


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def scorecard_block(txns: Iterable, rows: Iterable[dict], *, end: date,
                    since_start: dict, rates: dict | None = None) -> dict:
    """The scorecard row's `executable` block for the week ending `end`, from
    the ledger up to it (`txns`), the side-file rows and the row's own
    since-start comparison with the Nifty (results.vs_nifty)."""
    txns = [t for t in txns if (_day(t.date) or date.max) <= end]
    by_id = {r.get("txn_id"): r for r in rows if isinstance(r, dict)}
    trades = [t for t in _in_order(txns) if is_autopilot_trade(t)]
    valued = since_start.get("available") and since_start.get("deposits")
    valued_to = _day(since_start.get("to")) if valued else None
    block: dict = {"trades": len(trades),
                   "paper": {"book_pct": since_start.get("portfolio_pct") if valued else None,
                             "lead_points": since_start.get("gap_points") if valued else None,
                             "valued_to": since_start.get("to") if valued else None,
                             "reason": None if valued else since_start.get("reason")}}
    next_prices: dict[str, float] = {}
    for kind in KINDS:
        buys, sells, effect = [], [], 0.0
        counts = {PRICED: 0, NO_PRICE: 0, PENDING: 0}
        for t in trades:
            status, p = _status(by_id.get(t.txn_id), kind, end)
            counts[status] += 1
            if status != PRICED:
                continue
            real = float(p["open"])
            if kind == "open_next":
                next_prices[t.txn_id] = real
            gap = (real / float(t.price) - 1.0) * 100.0
            (buys if t.side == "BUY" else sells).append(gap)
            if valued_to is not None and _day(t.date) <= valued_to:
                effect += cash_effect(t, real, rates)
        k = {"priced": counts[PRICED], "no_price": counts[NO_PRICE], "pending": counts[PENDING],
             "buys": len(buys), "buy_gap_pct": _mean(buys),
             "sells": len(sells), "sell_shortfall_pct": _mean([-g for g in sells]),
             "cash_effect_inr": effect, "book_pct": None, "lead_points": None}
        if valued:
            deposits = float(since_start["deposits"])
            k["book_pct"] = ((float(since_start["portfolio_value"]) + effect - deposits)
                             / deposits * 100.0)
            k["lead_points"] = k["book_pct"] - float(since_start["nifty_pct"])
        block[kind] = k
    trips = round_trips(txns)
    losses = [x for x in (round_trip_loss(legs, next_prices) for legs in trips) if x is not None]
    block["round_trips"] = {"closed": len(trips), "priced": len(losses),
                            "mean_loss_points": _mean(losses)}
    return block


# -- The rule and the line --------------------------------------------------------------------

def _sign(x: float) -> int:
    x = round(x, 9)
    return (x > 0) - (x < 0)


def _points(x: float) -> str:
    return f"{x:+.1f}"


def rule_flag(block: dict) -> dict:
    """The predeclared rule as a red flag (`paper_prices`)."""
    trips = block["round_trips"]
    paper = block["paper"]["lead_points"]
    tests: dict[str, str] = {}
    if trips["priced"] < MIN_CASES:
        tests["round_trips"] = NOT_ENOUGH
    elif round(trips["mean_loss_points"] - ROUND_TRIP_MAX_LOSS_POINTS, 9) > 0:
        tests["round_trips"] = FIRED
    else:
        tests["round_trips"] = CLEAR
    for kind in KINDS:
        k = block[kind]
        if paper is None or k["lead_points"] is None:
            tests[kind] = UNKNOWN
        elif k["priced"] < MIN_CASES:
            tests[kind] = NOT_ENOUGH
        else:
            tests[kind] = FIRED if _sign(k["lead_points"]) != _sign(paper) else CLEAR
    detail = {"tests": tests, "max_loss_points": ROUND_TRIP_MAX_LOSS_POINTS,
              "min_cases": MIN_CASES}
    rule = (f"(rule of 15 Nov 2026: a round trip losing more than "
            f"{ROUND_TRIP_MAX_LOSS_POINTS:g} points on average at the next session's open, or "
            "the lead over the Nifty changing sign at either price)")
    nxt, run = block["open_next"], block["open_as_run"]
    if FIRED in tests.values():
        why = []
        if tests["round_trips"] == FIRED:
            why.append(f"round trips lose {trips['mean_loss_points']:.2f} points on average "
                       f"at the next session's open, over {trips['priced']}")
        for kind, words in (("open_next", "the next session's open"),
                            ("open_as_run", "the open after the run")):
            if tests[kind] == FIRED:
                why.append(f"the lead over the Nifty is {_points(paper)} points at the booked "
                           f"closes and {_points(block[kind]['lead_points'])} at {words}")
        return _flag("paper_prices", FIRED,
                     "Paper prices flatter the book: " + "; ".join(why) + ". Open a card to "
                     "book trades at the next session's open " + rule + ".", **detail)
    if all(v == CLEAR for v in tests.values()):
        return _flag("paper_prices", CLEAR,
                     f"Paper prices are close enough: round trips lose "
                     f"{trips['mean_loss_points']:.2f} points on average at the next "
                     f"session's open (over {trips['priced']}), and the lead over the Nifty "
                     f"keeps its sign ({_points(paper)} points at the booked closes, "
                     f"{_points(nxt['lead_points'])} at the next open, "
                     f"{_points(run['lead_points'])} after the run) " + rule + ".", **detail)
    if NOT_ENOUGH in tests.values():
        return _flag("paper_prices", NOT_ENOUGH,
                     f"Paper prices: too few to judge ({_plural(trips['priced'], 'round trip')}"
                     f" and {_plural(nxt['priced'], 'trade')} priced at the next session's "
                     f"open; the rule needs {MIN_CASES} of each).", **detail)
    reason = block["paper"]["reason"] or "the comparison with the Nifty is unavailable"
    return _flag("paper_prices", UNKNOWN,
                 f"Paper prices: could not check ({reason}).", **detail)


def _waiting(k: dict) -> str:
    parts = []
    if k["no_price"]:
        parts.append(f"{k['no_price']} with no price")
    if k["pending"]:
        parts.append(f"{k['pending']} waiting")
    return " and ".join(parts)


def line_text(block: dict) -> str:
    """The scorecard line: "At prices that could be had: …"."""
    n, nxt, run, paper = block["trades"], block["open_next"], block["open_as_run"], block["paper"]
    if not n:
        return "No trade by the autopilot yet."
    if paper["book_pct"] is not None:
        text = (f"the paper book is {_pct(nxt['book_pct'])} since the start at the next "
                f"session's open and {_pct(run['book_pct'])} at the open after the run "
                f"({_pct(paper['book_pct'])} at the booked closes).")
    else:
        text = (f"the paper book's result since the start is not available "
                f"({paper['reason'] or 'no comparison'}).")
    gaps = []
    if nxt["buys"]:
        g = nxt["buy_gap_pct"]
        gaps.append(f"buys cost {abs(g):.1f}% {'more' if g >= 0 else 'less'} on average "
                    f"({nxt['buys']})")
    if nxt["sells"]:
        s = nxt["sell_shortfall_pct"]
        gaps.append(f"sells brought {abs(s):.1f}% {'less' if s >= 0 else 'more'} "
                    f"({nxt['sells']})")
    if gaps:
        text += " At the next open " + " and ".join(gaps) + "."
    text += f" {n} trade{'s' if n != 1 else ''}"
    held = [(words, _waiting(block[kind])) for kind, words in
            (("open_next", "at the next open"), ("open_as_run", "at the open after the run"))]
    held = [f"{w} {words}" for words, w in held if w]
    if held:
        text += "; " + ", ".join(held) + ", each kept at its booked close"
    return text + "."


# -- Seams: the panel and the side file -----------------------------------------------------

def _positive(value) -> float | None:
    """A price from the panel, or None when it is missing, not a number or not above 0."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x == x and x > 0 else None


def panel_fn(store=None) -> Callable[[str, date], PanelBar]:
    """A stock's bar in the EOD panel on one day, read under the NSE code its
    close is read under (symbol_resolver.nse_symbol on that day), its equity
    series first. Each day's file is read once per call of this function."""
    from backend.shared.data.fetchers.symbol_resolver import nse_symbol
    from services.data.stores.eod_store import EodStore
    eod = store or EodStore()
    days: dict[date, dict | None] = {}

    def lookup(symbol: str, day: date) -> PanelBar:
        if day not in days:
            frame = eod.load_day(day)
            bars: dict | None = None
            if frame is not None:
                rank = {s: i for i, s in enumerate(SERIES_PREFERENCE)}
                bars = {}
                for sym, series, opened, closed in zip(frame["symbol"], frame["series"],
                                                       frame["open"], frame["close"]):
                    key, r = str(sym).strip().upper(), rank.get(str(series).strip().upper(), 99)
                    if key not in bars or r < bars[key][0]:
                        bars[key] = (r, opened, closed)
            days[day] = bars
        bars = days[day]
        if bars is None:
            return PanelBar(None, None, False)
        hit = bars.get(nse_symbol(symbol, day).upper())
        if hit is None:
            return PanelBar(None, None, True)
        _r, opened, closed = hit
        return PanelBar(_positive(opened), _positive(closed), True)
    return lookup


def refresh(store, txns: Iterable, *, panel: Callable[[str, date], PanelBar],
            corp_actions: Callable[[str], object] | None, today: date) -> list[dict]:
    """Every autopilot trade's row: a stored one as written, the others priced
    now. The new rows whose two prices are settled are appended once
    (store.append_executable_prices_once); the rest are priced again next
    time."""
    stored = {r.get("txn_id"): r for r in store.load_executable_prices()}
    rows, new = [], []
    for t in txns:
        if not is_autopilot_trade(t):
            continue
        if t.txn_id in stored:
            rows.append(stored[t.txn_id])
            continue
        try:
            row = price_trade(t, panel=panel, corp_actions=corp_actions, today=today)
        except Exception as exc:
            logger.warning("[executable] %s %s %s not priced this time: %s",
                           t.date, t.symbol, t.side, exc)
            continue
        if row is None:
            continue
        rows.append(row)
        if settled(row):
            new.append(row)
    if new:
        written = store.append_executable_prices_once(new)
        logger.info("[executable] %s: %d new rows written", store.user_id, written)
    return rows
