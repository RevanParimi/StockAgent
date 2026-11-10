"""
Trading costs and the capital-gains tax estimate of the paper portfolio (SA-048).

Every virtual BUY and SELL pays what an NSE equity delivery trade pays at a
zero-brokerage broker: STT on both sides, stamp duty on the buy, the exchange's
transaction charge and SEBI's fee on both sides, GST on the broker's, the
exchange's and SEBI's charges, and the depository's charge per scrip sold. The
rates are in config.yaml (`portfolio.costs`), dated. A trade's charges are
written on its own ledger row and taken from cash with it: one row, one txn_id,
so a crash and a re-run can never charge twice, and a later rate change never
alters a past trade.

A row written before costs were charged has none recorded. It is never read as
free: `costs_of` estimates it from the configured rates and labels it
estimated. Those costs were never taken from cash, so the performance view
lists them apart from the charged ones.

Realized P&L stays the price difference (`realized_pnl`, before costs).
`cost_summary` adds what each sale paid: its own charges and the share of its
position's buy charges that the sold shares carried.

**Example (ACMESOLAR, the owner's screen of 27 Sep):** 509 shares bought at
₹372.88 (₹1,89,795.92) and sold at ₹446.65 (₹2,27,344.85) pay ₹225.57 on the
buy and ₹250.85 on the sale: ₹476.42 in all. The realized +₹37,548.93 is
+₹37,072.51 net of costs, and the short-term tax estimate is ₹7,797.82.

The tax estimate (`tax_estimate`) is shown, never taken from cash. Per
financial year (April to March), each sale's gain is short-term when its shares
were held 12 months or less and long-term otherwise, the sold shares taken
oldest purchase first. Short-term losses offset short-term gains, then
long-term gains; long-term losses offset long-term gains only, as the law has
it. So a year with a short-term gain and a larger long-term loss still owes
tax on the short-term gain; that long-term loss would be carried forward,
which the estimate does not model. The long-term exemption applies once per
year, then the cess on the tax. STT is not deductible from a gain; every other
charge is.

Pure apart from reading the rates from settings: no clock, no network, no files.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from core.config import settings
from backend.shared.schemas.portfolio import TradeCosts
from core.portfolio.results import _FLAT_QTY, _day, _in_order

COST_KEYS = ("as_of", "brokerage_pct", "brokerage_max_inr", "stt_pct",
             "stamp_duty_buy_pct", "exchange_fee_pct", "sebi_fee_pct", "gst_pct",
             "dp_charge_inr")
TAX_KEYS = ("as_of", "short_term_pct", "long_term_pct", "long_term_exemption_inr",
            "long_term_after_months", "cess_pct")

_PAISA = Decimal("0.01")
_RUPEE = Decimal("1")
_ZERO = Decimal("0")


def _d(x) -> Decimal:
    return Decimal(str(x))


def _round(x: Decimal, unit: Decimal = _PAISA) -> Decimal:
    return x.quantize(unit, rounding=ROUND_HALF_UP)


def _money(x: Decimal) -> float:
    return float(_round(x))


def _rates(block, keys: tuple[str, ...], name: str) -> dict:
    block = block if isinstance(block, dict) else {}
    missing = [k for k in keys if block.get(k) in (None, "")]
    if missing:
        raise ValueError(f"config.yaml portfolio.{name} has no {', '.join(missing)}: "
                         "a trade is never charged nothing for want of a rate")
    return block


def cost_rates() -> dict:
    """The configured trading-cost rates (`portfolio.costs`); raises if one is missing."""
    return _rates(settings.PORTFOLIO_COSTS, COST_KEYS, "costs")


def tax_rates() -> dict:
    """The configured tax rates (`portfolio.tax`); raises if one is missing."""
    return _rates(settings.PORTFOLIO_TAX, TAX_KEYS, "tax")


# ---------------------------------------------------------------------------
# One trade's charges
# ---------------------------------------------------------------------------

def trade_costs(side: str, value: float, *, rates: dict | None = None,
                estimated: bool = False) -> TradeCosts:
    """The charges on one BUY or SELL of `value` rupees (quantity × price).

    Each charge is rounded to the paisa, except STT: the STT Rules round both
    the taxable value and the tax to the nearest rupee. GST is charged on the
    rounded brokerage, exchange fee and SEBI fee."""
    if side not in ("BUY", "SELL"):
        raise ValueError(f"no trading costs for a {side} row")
    r = rates or cost_rates()
    v = _d(value)
    if v <= 0:
        return TradeCosts(rates_as_of=str(r["as_of"]), estimated=estimated)

    def pct(key: str) -> Decimal:
        return v * _d(r[key]) / 100

    brokerage = pct("brokerage_pct")
    cap = _d(r["brokerage_max_inr"])
    if cap > 0:
        brokerage = min(brokerage, cap)
    brokerage = _round(brokerage)
    stt = _round(_round(v, _RUPEE) * _d(r["stt_pct"]) / 100, _RUPEE)
    exchange = _round(pct("exchange_fee_pct"))
    sebi = _round(pct("sebi_fee_pct"))
    stamp = _round(pct("stamp_duty_buy_pct")) if side == "BUY" else _ZERO
    gst = _round((brokerage + exchange + sebi) * _d(r["gst_pct"]) / 100)
    dp = _round(_d(r["dp_charge_inr"])) if side == "SELL" else _ZERO
    total = brokerage + stt + exchange + sebi + stamp + gst + dp
    return TradeCosts(brokerage=float(brokerage), stt=float(stt), exchange_fee=float(exchange),
                      sebi_fee=float(sebi), stamp_duty=float(stamp), gst=float(gst),
                      dp_charge=float(dp), total=float(total),
                      rates_as_of=str(r["as_of"]), estimated=estimated)


def buy_charge(value: float) -> float:
    """The total charges on a BUY of `value` rupees (sizing keeps cash above
    its floor after them)."""
    return trade_costs("BUY", value).total


def costs_of(t, rates: dict | None = None) -> TradeCosts | None:
    """A ledger row's charges: as recorded, or, for a BUY or SELL written
    before costs were charged, estimated from the configured rates and
    labelled so. None for a row that is not a trade (a dividend)."""
    if t.side not in ("BUY", "SELL"):
        return None
    if t.costs is not None:
        return t.costs
    return trade_costs(t.side, t.value, rates=rates, estimated=True)


def _deductible(c: TradeCosts) -> Decimal:
    """What a gain may deduct: every charge but STT."""
    return _d(c.total) - _d(c.stt)


# ---------------------------------------------------------------------------
# Realized P&L net of costs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SaleCost:
    """One SELL row's result before and after its costs."""
    txn_id: str
    symbol: str
    on: date | None
    gross: float             # realized_pnl, before costs
    own: float               # the sale's own charges
    carried: float           # the sold shares' share of their position's buy charges
    estimated: float         # the part of own + carried that is estimated

    @property
    def costs(self) -> float:
        return round(self.own + self.carried, 2)

    @property
    def net(self) -> float:
        return round(self.gross - self.own - self.carried, 2)


def _sold_fraction(t) -> Decimal:
    """The share of the position this SELL sold (1 when it sold the last share)."""
    after = _d(t.holding_qty_after)
    qty = _d(t.qty)
    if float(after) <= _FLAT_QTY or qty + after <= 0:
        return Decimal(1)
    return qty / (qty + after)


def sale_costs(txns: Iterable, rates: dict | None = None) -> tuple[list[SaleCost], dict]:
    """Every SELL with its costs, in ledger order, and the buy charges still
    carried by open positions ({symbol: (total, estimated part)}).

    A position's buy charges are pooled; a sale takes the share of the pool
    that its shares are of the position (quantity sold over quantity held
    before the sale, so a split in between changes nothing)."""
    pool: dict[str, list[Decimal]] = defaultdict(lambda: [_ZERO, _ZERO])
    out: list[SaleCost] = []
    for t in _in_order(txns):
        c = costs_of(t, rates)
        if c is None:
            continue
        total = _d(c.total)
        est = total if c.estimated else _ZERO
        if t.side == "BUY":
            pool[t.symbol][0] += total
            pool[t.symbol][1] += est
            continue
        frac = _sold_fraction(t)
        held = pool[t.symbol]
        carried, carried_est = held[0] * frac, held[1] * frac
        if frac == 1:
            pool.pop(t.symbol, None)
        else:
            held[0] -= carried
            held[1] -= carried_est
        out.append(SaleCost(txn_id=t.txn_id, symbol=t.symbol, on=_day(t.date),
                            gross=float(t.realized_pnl or 0.0), own=_money(total),
                            carried=_money(carried), estimated=_money(est + carried_est)))
    still_open = {s: (_money(v[0]), _money(v[1])) for s, v in pool.items() if v[0] > 0}
    return out, still_open


def cost_summary(txns: Iterable, rates: dict | None = None) -> dict:
    """Realized P&L before and after costs, and the account's costs.

    realized.gross is the ledger's realized P&L (the price difference),
    realized.costs what the sales and the shares they sold paid, and
    realized.net_of_costs the difference. costs.charged were taken from cash;
    costs.estimated belong to trades made before costs were charged and were
    not; costs.on_open_positions are buy charges of shares still held."""
    txns = list(txns)
    r = rates or cost_rates()
    sales, still_open = sale_costs(txns, r)
    charged = estimated = _ZERO
    for t in txns:
        c = costs_of(t, r)
        if c is None:
            continue
        if c.estimated:
            estimated += _d(c.total)
        else:
            charged += _d(c.total)
    gross = sum((_d(s.gross) for s in sales), _ZERO)
    paid = sum((_d(s.own) + _d(s.carried) for s in sales), _ZERO)
    return {
        "realized": {"gross": _money(gross), "costs": _money(paid),
                     "net_of_costs": _money(gross - paid),
                     "estimated_costs": _money(sum((_d(s.estimated) for s in sales), _ZERO))},
        "costs": {"charged": _money(charged), "estimated": _money(estimated),
                  "on_open_positions": _money(sum((_d(v[0]) for v in still_open.values()), _ZERO)),
                  "rates_as_of": str(r["as_of"])},
    }


# ---------------------------------------------------------------------------
# The capital-gains tax estimate
# ---------------------------------------------------------------------------

def financial_year(d: date) -> str:
    """'2026-27' for any day from 1 Apr 2026 to 31 Mar 2027."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _long_term_qty(lots: list[list], qty: Decimal, held_before: Decimal, sold_on: date,
                   months: int) -> Decimal | None:
    """Take `qty` shares from `lots` ([bought_on, shares], oldest first) and
    return how many were held more than `months` months. Lots are first
    scaled to the shares held before the sale, which carries a split or bonus
    since they were bought. None when no purchase is on record."""
    on_record = sum((q for _, q in lots), _ZERO)
    if on_record <= 0:
        return None
    if held_before > 0 and held_before != on_record:
        scale = held_before / on_record
        for lot in lots:
            lot[1] *= scale
    left, long_qty = qty, _ZERO
    while left > 0 and lots:
        bought_on, shares = lots[0]
        take = min(shares, left)
        if sold_on > _add_months(bought_on, months):
            long_qty += take
        left -= take
        lots[0][1] = shares - take
        if lots[0][1] <= 0:
            lots.pop(0)
    return long_qty


def _year_tax(b: dict, r: dict) -> dict:
    """One financial year's estimate from its gains and losses."""
    st_net = b["st_gains"] - b["st_losses"]
    lt_net = b["lt_gains"] - b["lt_losses"]
    lt_net = max(lt_net, _ZERO)                 # a long-term loss offsets long-term gains only
    if st_net < 0:                              # a short-term loss offsets long-term gains too
        lt_net = max(lt_net + st_net, _ZERO)
        st_net = _ZERO
    exemption = min(lt_net, _d(r["long_term_exemption_inr"]))
    lt_taxable = lt_net - exemption
    tax = _round(st_net * _d(r["short_term_pct"]) / 100
                 + lt_taxable * _d(r["long_term_pct"]) / 100)
    cess = _round(tax * _d(r["cess_pct"]) / 100)
    return {
        "short_term": {"gains": _money(b["st_gains"]), "losses": _money(b["st_losses"])},
        "long_term": {"gains": _money(b["lt_gains"]), "losses": _money(b["lt_losses"])},
        "short_term_taxable": _money(st_net), "long_term_taxable": _money(lt_taxable),
        "long_term_exemption_used": _money(exemption),
        "tax": float(tax), "cess": float(cess), "total": float(tax + cess),
        "sales": b["sales"], "sales_without_cost_basis": b["no_basis"],
        "sales_without_purchase_date": b["no_date"],
    }


def tax_estimate(txns: Iterable, *, rates: dict | None = None,
                 charge_rates: dict | None = None) -> dict:
    """The capital-gains tax the paper sales would owe, per financial year.

    A sale's gain is its value less its deductible charges, less its shares'
    cost (the ledger's `cost_basis`, the position's adjusted average) and
    their share of the position's deductible buy charges. A sale with no
    recorded cost basis falls back to its realized P&L, and its shares count
    as short-term when no purchase of them is on record (the higher rate:
    the estimate never reads low for want of a date). Both are counted."""
    r = rates or tax_rates()
    cr = charge_rates or cost_rates()
    months = int(r["long_term_after_months"])
    lots: dict[str, list[list]] = defaultdict(list)
    pool: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    years: dict[str, dict] = {}
    for t in _in_order(txns):
        c = costs_of(t, cr)
        if c is None:
            continue
        day, qty = _day(t.date), _d(t.qty)
        if t.side == "BUY":
            if qty > 0:
                lots[t.symbol].append([day, qty])
            pool[t.symbol] += _deductible(c)
            continue
        frac = _sold_fraction(t)
        carried = pool[t.symbol] * frac
        pool[t.symbol] -= carried
        b = years.setdefault(financial_year(day), {
            "st_gains": _ZERO, "st_losses": _ZERO, "lt_gains": _ZERO, "lt_losses": _ZERO,
            "sales": 0, "no_basis": 0, "no_date": 0})
        b["sales"] += 1
        if t.cost_basis and t.cost_basis > 0:
            gain = _d(t.value) - _deductible(c) - _d(t.cost_basis) * qty - carried
        else:
            b["no_basis"] += 1
            gain = _d(t.realized_pnl or 0.0) - _deductible(c) - carried
        long_qty = _long_term_qty(lots[t.symbol], qty, qty + _d(t.holding_qty_after),
                                  day, months)
        if frac == 1:
            lots.pop(t.symbol, None)
            pool.pop(t.symbol, None)
        if long_qty is None:
            b["no_date"] += 1
            long_qty = _ZERO
        long_gain = gain * long_qty / qty if qty > 0 else _ZERO
        for part, key in ((gain - long_gain, "st"), (long_gain, "lt")):
            if part > 0:
                b[f"{key}_gains"] += part
            elif part < 0:
                b[f"{key}_losses"] -= part
    out = [{"year": fy, **_year_tax(b, r)} for fy, b in sorted(years.items())]
    return {"years": out, "total": _money(sum((_d(y["total"]) for y in out), _ZERO)),
            "rates_as_of": str(r["as_of"]),
            "basis": ("estimate for a resident individual, shown and not taken from cash; "
                      "no surcharge, basic-exemption shortfall or losses carried forward")}
