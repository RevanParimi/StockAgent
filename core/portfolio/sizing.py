"""
One sizing and entry rule for every autopilot buy (SA-050).

Weights are measured against **total equity**: every holding at its mark plus
deployable cash. A holding without a mark is valued at its adjusted cost, as
the value history does. Measuring against the holdings alone made a ₹1.3 L
position in a ₹10 L portfolio that is 81% cash read as 72.9%, so ADD could
never fire and every review noted a concentration that was not there.

A buy paid from cash moves money from cash into a holding, so it leaves total
equity unchanged. The room under a cap after the trade is therefore
`cap × equity − current value`, in rupees.

Every autopilot buy, ADD and SWITCH alike (and SA-049's new positions), goes
through `size_buy`: the position at most `advisor.max_position_pct`, its
sector at most `advisor.max_sector_pct`, and the cash floor kept. A buy that
opens a position must also pass `entry_check` against its shelf idea's band.

Pure: no I/O, no clock, no settings reads beyond the caps.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from core.config import settings


def inr(x: float) -> str:
    """₹ with Indian digit grouping, whole rupees: ₹1,27,140."""
    n = int(round(x))
    sign, s = ("-" if n < 0 else ""), str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{sign}₹{s}"


def _price(x: float) -> str:
    """A share price: ₹1,911 or ₹330.15."""
    return f"₹{x:,.0f}" if round(x, 2) == round(x) else f"₹{x:,.2f}"


def marked_value(holding, marks: dict[str, float]) -> float:
    """Adjusted quantity at the mark, or at adjusted cost when there is none."""
    return holding.adj_qty * marks.get(holding.symbol, holding.adj_avg_price)


def holdings_value(portfolio, marks: dict[str, float]) -> float:
    return sum(marked_value(h, marks) for h in portfolio.holdings)


def total_equity(portfolio, marks: dict[str, float]) -> float:
    """Holdings at their marks plus deployable cash (none when cash is off)."""
    return holdings_value(portfolio, marks) + (portfolio.cash_deployable or 0.0)


@dataclass(frozen=True)
class Weights:
    """Shares of total equity, in percent."""
    equity: float
    position_pct: dict[str, float]
    sector_pct: dict[str, float]
    cash_pct: float | None          # None when cash accounting is off


def weights(portfolio, marks: dict[str, float]) -> Weights:
    equity = total_equity(portfolio, marks)
    position: dict[str, float] = {}
    sector: dict[str, float] = {}
    if equity > 0:
        for h in portfolio.holdings:
            pct = marked_value(h, marks) / equity * 100.0
            position[h.symbol] = position.get(h.symbol, 0.0) + pct
            sector[h.sector] = sector.get(h.sector, 0.0) + pct
    cash = portfolio.cash_deployable
    cash_pct = (cash / equity * 100.0 if equity > 0 else 0.0) if cash is not None else None
    return Weights(equity=equity, position_pct=position, sector_pct=sector, cash_pct=cash_pct)


def position_cap_pct() -> float:
    return float(settings.ADVISOR_MAX_POSITION_PCT)


def sector_cap_pct() -> float:
    return float(settings.ADVISOR_MAX_SECTOR_PCT)


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BuySize:
    qty: float              # whole shares; 0 = no buy
    wanted: float           # rupees asked for (sale proceeds, or the ADD tranche)
    budget: float           # rupees the rule allows (never negative)
    binding: str            # "" when the request itself was the limit; else
                            # "position cap" | "sector cap" | "cash floor"
    limit: str              # that limit in words ("the 10% position cap"); "" for none


def size_buy(portfolio, marks: dict[str, float], *, symbol: str, sector: str,
             price: float, wanted: float, floor_cash: float) -> BuySize:
    """
    How many whole shares of `symbol` (in `sector`) at `price` one autopilot
    buy may take when it asks for `wanted` rupees.

    After the trade the position is at most the position cap and the sector
    at most the sector cap, both of total equity, and cash stays at or above
    `floor_cash`. The tightest limit wins; on a tie the order is the request,
    then position cap, sector cap, cash floor.
    """
    equity = total_equity(portfolio, marks)
    position = sum(marked_value(h, marks) for h in portfolio.holdings if h.symbol == symbol)
    in_sector = sum(marked_value(h, marks) for h in portfolio.holdings if h.sector == sector)
    pos_cap, sec_cap = position_cap_pct(), sector_cap_pct()
    limits = [
        ("", wanted),
        ("position cap", pos_cap / 100.0 * equity - position),
        ("sector cap", sec_cap / 100.0 * equity - in_sector),
        ("cash floor", (portfolio.cash_deployable or 0.0) - floor_cash),
    ]
    binding, room = min(limits, key=lambda kv: kv[1])   # min keeps the first on ties
    budget = max(0.0, room)
    qty = float(math.floor(budget / price)) if price > 0 else 0.0
    if qty > 0 and qty * price > budget:                 # float guard: never over budget
        qty -= 1.0
    limit = {
        "": "",
        "position cap": f"the {pos_cap:g}% position cap",
        "sector cap": f"the {sec_cap:g}% cap on {sector or 'its sector'}",
        "cash floor": f"the {inr(floor_cash)} cash floor",
    }[binding]
    return BuySize(qty=qty, wanted=wanted, budget=budget, binding=binding, limit=limit)


def capped_note(size: BuySize, price: float, what: str) -> str:
    """'capped by the 10% position cap: ₹1,27,360 of the ₹2,27,000 proceeds
    stay in cash' — empty when nothing but the request limited the buy."""
    if not size.binding:
        return ""
    left = max(0.0, size.wanted - size.qty * price)
    return f"capped by {size.limit}: {inr(left)} of the {inr(size.wanted)} {what} stay in cash"


def under_one_share_note(size: BuySize, price: float, what: str) -> str:
    """Why a buy came to less than one share."""
    if size.binding:
        return f"{size.limit} leaves room for less than one share at {_price(price)}"
    return f"{inr(size.wanted)} of {what} is less than one share at {_price(price)}"


# ---------------------------------------------------------------------------
# Entry rule
# ---------------------------------------------------------------------------

def entry_check(price: float, idea) -> tuple[bool, str]:
    """
    May a buy that opens a position take place at `price`, given its shelf
    idea's band? Returns (allowed, note).

    Allowed at or below `entry_high` and above `invalidation_level`. Below
    `entry_low` it is cheaper than planned, and the note says so. No idea, or
    an idea with no band, is refused: the case was never priced.
    """
    if idea is None:
        return False, "not an active shelf idea with an entry band; needs a fresh deep dive"
    lo = float(getattr(idea, "entry_low", 0.0) or 0.0)
    hi = float(getattr(idea, "entry_high", 0.0) or 0.0)
    inval = float(getattr(idea, "invalidation_level", 0.0) or 0.0)
    if hi <= 0:
        return False, "no entry band on record; needs a fresh deep dive"
    band = f"{_price(lo)}–{_price(hi)}" if lo > 0 else f"up to {_price(hi)}"
    if price > hi:
        return False, (f"{(price / hi - 1) * 100:.1f}% above entry band ({band}); "
                       "needs a fresh deep dive")
    if inval > 0 and price <= inval:
        return False, (f"at or below its invalidation level {_price(inval)}; "
                       "the idea's case no longer holds")
    if lo > 0 and price < lo:
        return True, (f"{(1 - price / lo) * 100:.1f}% below entry band ({band}): "
                      "cheaper than planned")
    return True, ""
