"""
Compass Autopilot — deterministic execution of advisor verdicts on the
virtual portfolio (spec docs/superpowers/specs/2026-07-10-compass-autopilot-design.md §4).

The LLM never decides; this module is a pure function over AdviceRecords.
Virtual money only — no broker calls, ever. The transactions ledger is the
audit authority; portfolio.json is derived state.

Trade ordering per run (deterministic): sells first (EXIT, SWITCH sell leg,
TRIM — symbol asc), then buys (SWITCH buy legs, then ADDs by confidence
desc, ties symbol asc), then idle-cash deployment (new positions by
conviction desc, ties symbol asc). Sells free cash before buys consume it.

SA-050: every buy is sized by core/portfolio/sizing.py (position and sector
caps of total equity, after the trade, and the cash floor), and a buy that
opens a position (a SWITCH buy leg, a deployment buy) must also sit inside
its shelf idea's entry band. What a cap leaves unspent stays in cash; the
BUY's note says how much and why. A skipped SWITCH buy leg says why on its
SELL's note.

SA-049: a buy that opens a position also needs NSE's daily surveillance
report to list the stock as active and under no ASM or GSM stage
(`sizing.surveillance_issue`; owner, 1 Nov 2026), and so does a top-up (FIX-025;
owner, 4 Nov 2026): the shares are kept, and the digest says why no more were
bought. With idle-cash deployment
on (core/portfolio/deployment.py), the run then opens new positions from the
day's buy candidates up to the market regime's target invested share, at
most `autopilot.deploy_max_new_per_day` a day. Each BUY's note starts
`deploy_idle_cash`; the run's record, with why every other idea and any
idle cash below the target was not used, goes into the day's digest.

SA-048: every BUY and SELL pays its trading costs (core/portfolio/costs.py),
written on its own ledger row and taken from cash with it, so the txn_id
dedupe that stops a re-run trading twice also stops it charging twice. A
SWITCH buy leg asks for the sale's proceeds net of the sale's costs.

FIX-029: a buy that opens a position, a SWITCH leg or a deployment buy,
re-reads the candidate list's rule against this portfolio's ledger and this
run's own exits: never a stock sold since its idea was decided (from the
watchlist, after an autopilot exit, not before the Saturday after it), nor
an idea whose analysis does not rate it a BUY (`shelf.resale_wait`,
`shelf.verdict_wait`). A skipped SWITCH leg says why on its SELL.

FIX-028: once the trades are saved, the managed list follows the holdings
(`_follow_holdings`): a stock no portfolio holds any more leaves the daily
review (unless a user's own watchlist lists it), then each holding without
an entry is promoted, the run's buys included. A holding the list's cap
keeps out is named in the day's digest.
"""
from __future__ import annotations

import hashlib
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Callable

from core.config import settings
from backend.shared.schemas.portfolio import (
    AdviceRecord,
    Holding,
    Portfolio,
    TradeCosts,
    TransactionRecord,
    WatchlistItem,
)
from backend.shared.pipeline import decision_gate as dg
from core.portfolio import costs, deployment, sizing
from core.portfolio.store import PortfolioStore
from core.portfolio.identity_reconcile import symbol_identity_issue
from core.portfolio.pricing import session_close
from core.portfolio.promotion import promote_symbol, release_unheld, without_daily_review

if TYPE_CHECKING:
    from core.discovery.shelf import Sales

logger = logging.getLogger(__name__)

# What promote_symbol answers when the stock gets no enabled entry.
_NOT_PROMOTED = ("cap_full", "invalid_sector")


def make_txn_id(user_id: str, d: str, symbol: str, side: str, ref: str) -> str:
    return hashlib.sha256(f"{user_id}|{d}|{symbol}|{side}|{ref}".encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_ist() -> date:
    """IST calendar date — the reference clock for all date guards (AUD-044).
    Module-level seam so tests can freeze 'today'."""
    from core.intelligence.rl.nse_calendar import now_ist
    return now_ist().date()


Report = tuple[dict | None, str | None]     # (securities, as_of) from NSE's report


def surveillance_report(session: date) -> Report:
    """NSE's Surveillance Indicator report a buy on `session` is checked
    against: the newest dated on or before it, at most 7 days old, cached
    (services/data/fetchers/surveillance.py); (None, None) when there is none,
    or when reading it fails, so the run goes on and no new position opens.
    A seam: the tests answer it."""
    try:
        from services.data.fetchers.surveillance import surveillance_list
        return surveillance_list(session)
    except Exception as exc:
        logger.warning("[autopilot] surveillance report unreadable for %s, so no new "
                       "position opens: %s", session, exc)
        return None, None


def _once(read: Callable[[], Report]) -> Callable[[], Report]:
    """`read`, called at most once."""
    held: list[Report] = []

    def get() -> Report:
        if not held:
            held.append(read())
        return held[0]
    return get


def _txn(portfolio: Portfolio, rec: AdviceRecord, *, side: str, qty: float,
         price: float, cash_before: float, holding_qty_after: float,
         realized: float, note: str, charges: TradeCosts,
         symbol: str | None = None,
         cost_basis: float | None = None) -> TransactionRecord:
    sym = symbol or rec.symbol
    ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
    pnl_pct = None
    if side == "SELL" and cost_basis and cost_basis > 0 and qty > 0:
        pnl_pct = round(realized / (cost_basis * qty) * 100, 2)
    return TransactionRecord(
        txn_id=make_txn_id(portfolio.user_id, rec.date, sym, side, ref),
        date=rec.date, ts=_now_iso(), user_id=portfolio.user_id, symbol=sym,
        side=side, qty=qty, price=price, value=round(qty * price, 2),
        cash_before=round(cash_before, 2),
        cash_after=round(portfolio.cash_deployable, 2),
        holding_qty_after=holding_qty_after, realized_pnl=realized,
        source="autopilot", verdict=rec.verdict, advice_ref=ref,
        triggers=list(rec.triggers), note=note,
        cost_basis=cost_basis, pnl_pct=pnl_pct, reason=rec.narrative,
        costs=charges,
    )


def _find(portfolio: Portfolio, symbol: str) -> Holding | None:
    return next((h for h in portfolio.holdings if h.symbol == symbol), None)


SwitchLeg = tuple[float, AdviceRecord, TransactionRecord]   # proceeds, advice, its SELL

_SKIP_MARK = "; buy leg skipped: "


def _note_skipped_buy(sell: TransactionRecord, candidate: str, proceeds: float,
                      reason: str) -> None:
    """SA-050: a SWITCH whose buy leg did not land says why on its SELL, the
    transaction the user sees; the pipeline's alert repeats it."""
    sell.note = (f"{sell.note}{_SKIP_MARK}{candidate}: {reason}; "
                 f"{sizing.inr(proceeds)} stays in cash")


def switch_skip_reason(sell_note: str) -> str:
    """The skipped-buy reason written by `_note_skipped_buy`, or ""."""
    return sell_note.split(_SKIP_MARK, 1)[1] if _SKIP_MARK in sell_note else ""


def _execute_sells(portfolio: Portfolio, advice: list[AdviceRecord],
                   closes: dict[str, float], existing_ids: set[str],
                   ) -> tuple[list[TransactionRecord], list[SwitchLeg]]:
    txns: list[TransactionRecord] = []
    switch_proceeds: list[SwitchLeg] = []
    sells = sorted((a for a in advice if a.verdict in ("EXIT", "SWITCH", "TRIM")),
                   key=lambda a: a.symbol)
    for rec in sells:
        h = _find(portfolio, rec.symbol)
        if h is None or h.adj_qty <= 0:
            continue
        price = closes.get(rec.symbol) or rec.close
        if price is None or price <= 0:
            # AUD-004: never wipe a position for ₹0 on a bad/missing price.
            logger.warning("[autopilot] SELL %s skipped: non-positive price %r",
                           rec.symbol, price)
            continue
        closes.setdefault(rec.symbol, price)   # AUD-003: one price basis per run
        note = ""
        if rec.verdict in ("EXIT", "SWITCH"):
            qty = h.adj_qty
            note = "exit_full"
        else:  # TRIM
            qty = float(max(1, math.floor(h.adj_qty * settings.AUTOPILOT_TRIM_PCT / 100.0)))
            if h.adj_qty - qty < 1.0:
                qty, note = h.adj_qty, "trim_to_zero"
        ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
        if make_txn_id(portfolio.user_id, rec.date, rec.symbol, "SELL", ref) in existing_ids:
            logger.warning(
                "[autopilot] SELL %s (%s) already in ledger but run marker predates "
                "this run — possible ledger/portfolio divergence from a mid-run "
                "crash; manual reconciliation may be needed", rec.symbol, rec.verdict)
            continue
        cost_basis = round(h.adj_avg_price, 4)
        charges = costs.trade_costs("SELL", round(qty * price, 2))
        cash_before = portfolio.cash_deployable
        realized = h.sell(qty, price)
        # SA-048: the sale's charges leave cash with it, on its own ledger row.
        portfolio.cash_deployable = round(
            portfolio.cash_deployable + qty * price - charges.total, 2)
        if h.adj_qty <= 1e-9:
            portfolio.holdings = [x for x in portfolio.holdings if x.symbol != h.symbol]
            if rec.verdict in ("EXIT", "SWITCH") and not any(
                    w.symbol == h.symbol for w in portfolio.watchlist):
                portfolio.watchlist.append(WatchlistItem(
                    symbol=h.symbol, sector=h.sector, added=rec.date,
                    reason="autopilot_exit", source="autopilot"))
        sell = _txn(portfolio, rec, side="SELL", qty=qty, price=price,
                    cash_before=cash_before,
                    holding_qty_after=(h.adj_qty if h.adj_qty > 1e-9 else 0.0),
                    realized=realized, note=note, charges=charges, cost_basis=cost_basis)
        txns.append(sell)
        if rec.verdict == "SWITCH" and rec.switch_candidate:
            switch_proceeds.append((qty * price - charges.total, rec, sell))
    return txns, switch_proceeds


def _trading_days_between(start: date, end: date) -> int:
    from core.intelligence.rl.nse_calendar import is_trading_day
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if is_trading_day(d):
            n += 1
    return n


def _last_add_date(store: PortfolioStore, symbol: str) -> date | None:
    for t in reversed(store.load_transactions(limit=2000)):
        if t.symbol == symbol and t.side == "BUY" and t.source == "autopilot":
            return date.fromisoformat(t.date)
    return None


def _buy_into_holding(portfolio: Portfolio, symbol: str, sector: str,
                      qty: float, price: float, buy_date: str) -> float:
    """Merge a buy into an existing holding (weighted adj averages) or create
    a new one. Returns the holding's post-trade adj_qty."""
    h = _find(portfolio, symbol)
    if h is None:
        portfolio.holdings.append(Holding(
            symbol=symbol, sector=sector, qty=qty, avg_buy_price=price,
            adj_avg_price=price, adj_qty=qty, buy_date=buy_date))
        return qty
    total = h.adj_qty + qty
    h.adj_avg_price = (h.adj_avg_price * h.adj_qty + price * qty) / total
    h.adj_qty = total
    # raw fields track money actually put in (entry history)
    raw_total = h.qty + qty
    h.avg_buy_price = (h.avg_buy_price * h.qty + price * qty) / raw_total
    h.qty = raw_total
    return h.adj_qty


def _sector_of(symbol: str, sector_lookup: dict[str, str] | None) -> str:
    """The sector a new position is held under: its candidate's, else the
    registry's, else "generic"."""
    sector = (sector_lookup or {}).get(symbol, "")
    if not sector:
        try:
            from backend.sectors.registry import SectorRegistry
            sector = SectorRegistry.resolve(symbol).strip().lower()
        except Exception as exc:
            logger.debug("[autopilot] no registry sector for %s, held as generic: %s",
                         symbol, exc)
            sector = "generic"
    return sector


def _execute_buys(portfolio: Portfolio, advice: list[AdviceRecord],
                  closes: dict[str, float], existing_ids: set[str],
                  switch_proceeds: list[SwitchLeg],
                  review_date: date, store: PortfolioStore,
                  sector_lookup: dict[str, str] | None,
                  shelf_index: dict | None = None,
                  surveillance: Callable[[], Report] | None = None,
                  top_ups_skipped: list[dict] | None = None,
                  sales: Sales | None = None,
                  ) -> list[TransactionRecord]:
    from core.discovery.shelf import Sales, close_before_dive, verdict_wait
    txns: list[TransactionRecord] = []
    floor_cash = settings.AUTOPILOT_MIN_CASH_FLOOR
    surveillance = surveillance or _once(lambda: surveillance_report(review_date))
    sales = sales or Sales()

    for proceeds, rec, sell in switch_proceeds:
        cand = rec.switch_candidate.strip().upper()
        if not cand:
            continue
        # FIX-029: the list's rule again, against the ledger: not a stock
        # sold since its idea was decided, nor an idea not rated a BUY.
        idea = (shelf_index or {}).get(cand)
        wait = (sales.wait(idea) or verdict_wait(idea)) if idea is not None else ""
        if wait:
            logger.info("[autopilot] SWITCH buy %s skipped: %s", cand, wait)
            _note_skipped_buy(sell, cand, proceeds, wait)
            continue
        try:
            quote, session = session_close(cand, review_date)
            price = quote.close
        except Exception as exc:
            logger.warning("[autopilot] SWITCH buy %s skipped: unpriceable (%s)",
                           cand, exc)
            _note_skipped_buy(sell, cand, proceeds, "no price for the review session")
            continue
        # FIX-023, FIX-024: only at a close struck after the idea was decided
        # (its deep dive or analysis), whatever the data gate's mode.
        early = close_before_dive(quote.bar_date, (shelf_index or {}).get(cand))
        if early:
            logger.warning("[autopilot] SWITCH buy %s skipped: %s", cand, early)
            _note_skipped_buy(sell, cand, proceeds, early)
            continue
        if not quote.fresh_for(session):
            # SA-003: a buy needs the session's own close. The pipeline's
            # switch_buy_skipped alert tells the user the proceeds stayed in cash.
            bar = quote.bar_date.isoformat() if quote.bar_date else "undated"
            if dg.enforcing():
                logger.warning("[autopilot] SWITCH buy %s skipped (data gate): close "
                               "%.2f is from bar %s, not session %s",
                               cand, price, bar, session)
                _note_skipped_buy(sell, cand, proceeds,
                                  f"its close is from bar {bar}, not the review session")
                continue
            logger.warning("[autopilot] SWITCH buy %s at a close from bar %s, not "
                           "session %s — the data gate would skip it (record mode)",
                           cand, bar, session)
        # SA-008: never buy into an instrument whose identity is unresolved.
        identity_issue = symbol_identity_issue(cand, session)
        if identity_issue:
            if dg.enforcing():
                logger.warning("[autopilot] SWITCH buy %s skipped (data gate): %s",
                               cand, identity_issue)
                _note_skipped_buy(sell, cand, proceeds, f"identity: {identity_issue}")
                continue
            logger.warning("[autopilot] SWITCH buy %s: %s — the data gate would skip it "
                           "(record mode)", cand, identity_issue)
        # SA-049: never into a stock under ASM/GSM or suspended (owner, 1 Nov).
        watched = sizing.surveillance_issue(cand, surveillance())
        if watched:
            logger.info("[autopilot] SWITCH buy %s skipped: %s", cand, watched)
            _note_skipped_buy(sell, cand, proceeds, watched)
            continue
        closes[cand] = price                   # AUD-003: one price basis per run
        # SA-050: a new position is bought only inside its idea's entry band.
        allowed, band_note = sizing.entry_check(price, (shelf_index or {}).get(cand))
        if not allowed:
            logger.info("[autopilot] SWITCH buy %s skipped: %s", cand, band_note)
            _note_skipped_buy(sell, cand, proceeds, band_note)
            continue
        sector = _sector_of(cand, sector_lookup)
        size = sizing.size_buy(portfolio, closes, symbol=cand, sector=sector,
                               price=price, wanted=proceeds, floor_cash=floor_cash,
                               charge=costs.buy_charge)
        if size.qty < 1:
            why = sizing.under_one_share_note(size, price, "proceeds")
            logger.info("[autopilot] SWITCH buy %s skipped: %s", cand, why)
            _note_skipped_buy(sell, cand, proceeds, why)
            continue
        qty = size.qty
        ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
        if make_txn_id(portfolio.user_id, rec.date, cand, "BUY", ref) in existing_ids:
            logger.warning(
                "[autopilot] SWITCH BUY %s (from %s) already in ledger but run "
                "marker predates this run — possible ledger/portfolio divergence "
                "from a mid-run crash; manual reconciliation may be needed",
                cand, rec.symbol)
            _note_skipped_buy(sell, cand, proceeds,
                              "already in the ledger; needs manual reconciliation")
            continue
        note = "; ".join(n for n in (f"switch from {rec.symbol}", band_note,
                                     sizing.capped_note(size, price, "proceeds")) if n)
        charges = costs.trade_costs("BUY", round(qty * price, 2))
        cash_before = portfolio.cash_deployable
        portfolio.cash_deployable = round(
            portfolio.cash_deployable - qty * price - charges.total, 2)
        qty_after = _buy_into_holding(portfolio, cand, sector, qty, price,
                                      review_date.isoformat())
        txns.append(_txn(portfolio, rec, side="BUY", qty=qty, price=price,
                         cash_before=cash_before, holding_qty_after=qty_after,
                         realized=0.0, note=note, charges=charges, symbol=cand))

    adds = sorted((a for a in advice if a.verdict == "ADD"),
                  key=lambda a: (-a.confidence, a.symbol))
    for rec in adds:
        h = _find(portfolio, rec.symbol)
        if h is None:
            continue
        price = closes.get(rec.symbol) or rec.close
        if price <= 0:
            continue
        closes.setdefault(rec.symbol, price)   # AUD-003: one price basis per run
        last_add = _last_add_date(store, rec.symbol)
        if last_add is not None and _trading_days_between(
                last_add, review_date) < settings.AUTOPILOT_ADD_COOLDOWN_TD:
            logger.info("[autopilot] ADD %s skipped: cooldown", rec.symbol)
            continue
        # FIX-025: more money into a stock passes the check a new position
        # does. Nothing is sold, and no BUY means the cooldown does not move.
        watched = sizing.surveillance_issue(rec.symbol, surveillance())
        if watched:
            logger.info("[autopilot] ADD %s skipped: %s", rec.symbol, watched)
            if top_ups_skipped is not None:
                top_ups_skipped.append({"symbol": rec.symbol,
                                        "why": f"top-up skipped: {watched}"})
            continue
        tranche = h.adj_qty * price * settings.AUTOPILOT_ADD_TRANCHE_PCT / 100.0
        size = sizing.size_buy(portfolio, closes, symbol=rec.symbol, sector=h.sector,
                               price=price, wanted=tranche, floor_cash=floor_cash,
                               charge=costs.buy_charge)
        if size.qty < 1:
            logger.info("[autopilot] ADD %s skipped: %s", rec.symbol,
                        sizing.under_one_share_note(size, price, "tranche"))
            continue
        qty = size.qty
        ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
        if make_txn_id(portfolio.user_id, rec.date, rec.symbol, "BUY", ref) in existing_ids:
            logger.warning(
                "[autopilot] ADD BUY %s already in ledger but run marker predates "
                "this run — possible ledger/portfolio divergence from a mid-run "
                "crash; manual reconciliation may be needed", rec.symbol)
            continue
        charges = costs.trade_costs("BUY", round(qty * price, 2))
        cash_before = portfolio.cash_deployable
        portfolio.cash_deployable = round(
            portfolio.cash_deployable - qty * price - charges.total, 2)
        qty_after = _buy_into_holding(portfolio, rec.symbol, h.sector, qty, price,
                                      review_date.isoformat())
        note = "; ".join(n for n in ("add_tranche",
                                     sizing.capped_note(size, price, "tranche")) if n)
        txns.append(_txn(portfolio, rec, side="BUY", qty=qty, price=price,
                         cash_before=cash_before, holding_qty_after=qty_after,
                         realized=0.0, note=note, charges=charges))
    return txns


def _deploy_check(idea, symbol: str, portfolio: Portfolio, sales: Sales,
                  quotes: dict, review_date: date,
                  surveillance: Callable[[], Report]) -> tuple[str, str, dict]:
    """(outcome, why, the buy's inputs) for one candidate before sizing; the
    outcome is "" when it may be bought. Mirrors a SWITCH buy leg's checks,
    plus the deep dive's own data gate. FIX-029: the re-buy rule and the
    verdict are the candidate list's (`shelf.resale_wait`,
    `shelf.verdict_wait`), read again here with this run's own exits."""
    from core.discovery.shelf import close_before_dive, verdict_wait
    if _find(portfolio, symbol) is not None:
        return "held", "already held", {}
    wait = sales.wait(idea)
    if wait:
        return "sold", wait, {}
    not_a_buy = verdict_wait(idea)
    if not_a_buy:
        return "verdict", not_a_buy, {}
    withheld = []
    status = getattr(idea, "data_gate", dg.UNKNOWN)
    if not dg.is_actionable(status):
        withheld.append(f"its deep dive's data gate is {status or 'unknown'} "
                        "(not verified as actionable)")
    try:
        quote, session = quotes[symbol] if symbol in quotes else session_close(
            symbol, review_date)
    except Exception as exc:
        logger.info("[autopilot] deploy %s: unpriceable (%s)", symbol, exc)
        return "price", "no close for the review session", {}
    price = quote.close
    if price is None or price <= 0:
        return "price", "no close for the review session", {}
    early = close_before_dive(quote.bar_date, idea)       # FIX-023: either gate mode
    if early:
        return "before_dive", early, {}
    if not quote.fresh_for(session):
        bar = quote.bar_date.isoformat() if quote.bar_date else "undated"
        withheld.append(f"its close is from bar {bar}, not the review session")
    identity_issue = symbol_identity_issue(symbol, session)
    if identity_issue:
        withheld.append(f"identity: {identity_issue}")
    if withheld and dg.enforcing():
        return "gate", "withheld by the data gate: " + "; ".join(withheld), {}
    watched = sizing.surveillance_issue(symbol, surveillance())
    if watched:
        return "surveillance", watched, {}
    allowed, band_note = sizing.entry_check(price, idea)
    if not allowed:
        return ("invalidated" if "invalidation" in band_note else "band"), band_note, {}
    return "", "", {"price": float(price), "band_note": band_note, "withheld": withheld}


def _deploy_idle_cash(portfolio: Portfolio, closes: dict[str, float],
                      existing_ids: set[str], review_date: date, store: PortfolioStore,
                      ideas: list, quotes: dict, surveillance: Callable[[], Report],
                      sales: Sales) -> tuple[list[TransactionRecord], dict]:
    """SA-049: open new positions with idle cash, best conviction first, up
    to the regime's target (core/portfolio/deployment.py). Returns the BUYs
    and the run's record."""
    b = deployment.breadth(portfolio.user_id)
    floor_cash = settings.AUTOPILOT_MIN_CASH_FLOOR
    max_new = max(0, int(settings.AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY))
    day = review_date.isoformat()
    equity = sizing.total_equity(portfolio, closes)
    position_inr = b.position_inr(equity)
    invested_before = invested = sizing.holdings_value(portfolio, closes)
    holdings_before = len(portfolio.holdings)
    regime = deployment.recorded_regime(review_date)
    t = deployment.target(regime, equity, b, floor_cash,
                          gap="" if regime else deployment.regime_gap(review_date))
    txns: list[TransactionRecord] = []
    outcomes: list[dict] = []

    def stop() -> str:
        return deployment.stop_reason(
            t, b, equity=sizing.total_equity(portfolio, closes), invested=invested,
            holdings=len(portfolio.holdings), opened=len(txns), max_new=max_new)

    # Nothing to evaluate when nothing may open: a crisis, no regime, the
    # target already met or the maximum held.
    ranked = [] if stop() else sorted(
        ideas, key=lambda i: (-float(getattr(i, "conviction", 0.0) or 0.0), i.symbol))
    seen: set[str] = set()
    for idea in ranked:
        symbol = idea.symbol.strip().upper()
        if symbol in seen:
            continue
        seen.add(symbol)
        row = {"symbol": symbol, "conviction": round(float(idea.conviction or 0.0), 2),
               "source": getattr(idea, "source", "discovery")}
        outcome, why, ctx = _deploy_check(idea, symbol, portfolio, sales, quotes,
                                          review_date, surveillance)
        if not outcome:
            price = ctx["price"]
            sector = idea.sector or _sector_of(symbol, None)
            size = sizing.size_buy(portfolio, closes, symbol=symbol, sector=sector,
                                   price=price, wanted=position_inr, floor_cash=floor_cash,
                                   charge=costs.buy_charge)
            if size.qty < 1:
                outcome = "size"
                why = sizing.under_one_share_note(size, price, "a new position's budget")
        if not outcome:
            halt = stop()
            ref = f"{day}|{symbol}|deploy_idle_cash"
            txn_id = make_txn_id(portfolio.user_id, day, symbol, "BUY", ref)
            if halt:
                outcome, why = "waiting", f"qualifies; not bought: {halt}"
            elif txn_id in existing_ids:
                logger.warning("[autopilot] deploy BUY %s already in ledger but run marker "
                               "predates this run — manual reconciliation may be needed",
                               symbol)
                outcome, why = "ledger", "already in the ledger; needs manual reconciliation"
        if outcome:
            outcomes.append({**row, "outcome": outcome, "why": why})
            continue
        qty = size.qty
        closes[symbol] = price                 # AUD-003: one price basis per run
        before_pct = invested / equity * 100.0 if equity > 0 else 0.0
        charges = costs.trade_costs("BUY", round(qty * price, 2))
        cash_before = portfolio.cash_deployable
        portfolio.cash_deployable = round(
            portfolio.cash_deployable - qty * price - charges.total, 2)
        qty_after = _buy_into_holding(portfolio, symbol, sector, qty, price, day)
        invested = sizing.holdings_value(portfolio, closes)
        now_equity = sizing.total_equity(portfolio, closes)
        after_pct = invested / now_equity * 100.0 if now_equity > 0 else 0.0
        withheld = ctx["withheld"]
        note = "; ".join(n for n in (
            (f"deploy_idle_cash: {row['source']} idea, conviction {row['conviction']:.2f}; "
             f"regime {t.regime}, target {t.invested_inr / equity * 100:.1f}% invested "
             f"({sizing.inr(t.invested_inr)}); invested {before_pct:.1f}% before, "
             f"{after_pct:.1f}% after"),
            ctx["band_note"],
            (f"capped by {size.limit} at {sizing.inr(qty * price)} of the "
             f"{sizing.inr(size.wanted)} a new position asks for") if size.binding else "",
            ("record mode: the data gate would withhold it: " + "; ".join(withheld))
            if withheld else "",
        ) if n)
        txns.append(TransactionRecord(
            txn_id=txn_id, date=day, ts=_now_iso(), user_id=portfolio.user_id, symbol=symbol,
            side="BUY", qty=qty, price=price, value=round(qty * price, 2),
            cash_before=round(cash_before, 2), cash_after=round(portfolio.cash_deployable, 2),
            holding_qty_after=qty_after, realized_pnl=0.0, source="autopilot",
            verdict="DEPLOY", advice_ref=ref, triggers=["deploy_idle_cash"], note=note,
            reason=str(getattr(idea, "thesis", "") or ""), costs=charges))
        existing_ids.add(txn_id)
        outcomes.append({**row, "outcome": "bought", "why": note})
    record = deployment.run_record(
        on=review_date, t=t, b=b, equity=equity, invested_before=invested_before,
        invested_after=invested, holdings_before=holdings_before,
        holdings_after=len(portfolio.holdings), cash_after=portfolio.cash_deployable,
        outcomes=outcomes, stop=stop())
    logger.info("[autopilot] %s deploy for %s: bought %s; %s", day, portfolio.user_id,
                record["bought"] or "nothing", "; ".join(record["reasons"]))
    return txns, record


def _follow_holdings(portfolio: Portfolio, txns: list[TransactionRecord]) -> dict:
    """FIX-028: once a run's trades are saved, the managed list follows the
    holdings. First every `held` entry no portfolio holds is released
    (`promotion.release_unheld`), so a sale's room is free before a buy asks
    for it; then the positions the run opened are promoted, as before, and so
    is each holding the list is waiting for (`without_daily_review`): one the
    cap kept out or a promotion that failed on an earlier run, a disabled
    held entry, a watchlist entry. An original entry the owner disabled stays
    disabled unless this run opened the position.

    Returns {"released": ..., "to_watchlist": ..., "not_reviewed": [{"symbol",
    "why"}]} (and "error" when the release did not run); a holding named in
    "not_reviewed" has no daily review or monthly forecast. Never raises: the
    trades stand either way."""
    try:
        out = release_unheld(portfolio)
    except Exception as exc:
        logger.warning("[autopilot] managed release failed (non-fatal): %s", exc)
        out = {"released": [], "to_watchlist": [], "error": f"release failed: {exc}"}
    holdings = {h.symbol: h for h in portfolio.holdings}
    # The positions this run opened are promoted as before, a disabled
    # original entry included; the rest only when the list waits for them.
    wanted = {t.symbol for t in txns if t.side == "BUY" and t.verdict != "ADD"} & set(holdings)
    try:
        wanted |= without_daily_review(holdings) or set()
    except Exception as exc:
        logger.warning("[autopilot] managed list unread (non-fatal): %s", exc)
    not_reviewed: list[dict] = []
    for symbol in sorted(wanted):
        try:
            result = promote_symbol(symbol, holdings[symbol].sector, origin="held")
        except Exception as exc:
            logger.warning("[autopilot] promotion failed for %s (non-fatal): %s", symbol, exc)
            result = {"status": "error", "detail": f"promotion failed: {exc}"}
        status = (result or {}).get("status")
        if status in _NOT_PROMOTED or status == "error":
            why = f"no daily review or forecast: {result.get('detail') or status}"
            logger.warning("[autopilot] %s holds %s with %s", portfolio.user_id, symbol, why)
            not_reviewed.append({"symbol": symbol, "why": why})
    out["not_reviewed"] = not_reviewed
    return out


def execute_advice(store: PortfolioStore, portfolio: Portfolio,
                   advice: list[AdviceRecord], closes: dict[str, float],
                   review_date: date,
                   sector_lookup: dict[str, str] | None = None,
                   shelf_index: dict | None = None,
                   candidate_quotes: dict | None = None,
                   surveillance: Callable[[], Report] | None = None,
                   report: dict | None = None,
                   ) -> list[TransactionRecord]:
    """Execute one review-day's verdicts. Appends transactions FIRST, then
    saves the portfolio — a crash between the two cannot double-execute
    (txn_id dedupe), but it CAN leave the ledger ahead of portfolio.json
    (a txn recorded, cash/holdings never updated). The dedupe-skip warning
    logged below flags that state for manual reconciliation.

    AUD-001: the `portfolio` argument is a pre-advisor snapshot that may be
    minutes stale (network + LLM per holding). It is used for gating hints
    only — the actual mutation reloads FRESH state under the store lock so a
    concurrent API mutation is never silently reverted.
    AUD-044: a future review_date is refused outright (no trades, no marker
    stamp) — stamping a future marker would brick the monotonic guard.
    SA-050: `shelf_index` maps a symbol to its active shelf idea; a SWITCH
    destination missing from it has no entry band and is not bought.
    SA-049: `shelf_index` holds the day's buy candidates, which idle-cash
    deployment buys from when it is on for the portfolio;
    `candidate_quotes` maps a candidate to its (SessionClose, session),
    fetched before the lock (one missing is fetched here); `surveillance`
    returns NSE's surveillance report, read once (default: read here when a
    buy first needs it); `report`, when given, receives the deployment
    record under "deployment", the top-ups NSE's report refused under
    "top_ups_skipped", and the holdings left with no daily review under
    "not_reviewed" (FIX-028, `_follow_holdings`).
    FIX-028: after the save, the managed list follows the holdings: a stock
    no portfolio holds any more leaves the daily review, and a stock bought
    joins it."""
    if not settings.AUTOPILOT_ENABLED:
        return []
    day = review_date.isoformat()
    today = _today_ist().isoformat()
    if day > today:
        logger.warning("[autopilot] refusing future review_date %s (today %s)",
                       day, today)
        return []
    with store.locked():
        portfolio = store.load()               # fresh state — AUD-001
        if not portfolio.autopilot or portfolio.cash_deployable is None:
            return []
        # Monotonic guard: only run for a day strictly after the last completed
        # run. Equality-only checks let a re-run for a PAST review_date (e.g. a
        # manually retried POST /portfolio/run-advisor?review_date=<past>)
        # execute stale-priced trades against the CURRENT portfolio and regress
        # the marker. ISO date strings compare correctly lexicographically, and
        # a forward recovery run for a missed day still proceeds normally.
        if portfolio.last_autopilot_run and day <= portfolio.last_autopilot_run:
            return []
        ledger = store.load_transactions(limit=2000)
        existing_ids = {t.txn_id for t in ledger}
        surveillance = surveillance or _once(lambda: surveillance_report(review_date))

        sell_txns, switch_proceeds = _execute_sells(portfolio, advice, closes,
                                                    existing_ids)
        existing_ids |= {t.txn_id for t in sell_txns}
        # FIX-029: each exit on the day it was decided, this run's own included.
        from core.discovery.shelf import ledger_sales
        sales = ledger_sales([*ledger, *sell_txns])
        top_ups_skipped: list[dict] = []
        buy_txns = _execute_buys(portfolio, advice, closes, existing_ids,
                                 switch_proceeds, review_date, store, sector_lookup,
                                 shelf_index, surveillance, top_ups_skipped, sales)
        if report is not None and top_ups_skipped:
            report["top_ups_skipped"] = top_ups_skipped
        txns = sell_txns + buy_txns
        if deployment.active(portfolio):
            existing_ids |= {t.txn_id for t in buy_txns}
            # On a copy, kept only when it completes: a failure here never
            # costs the day's sells and switches.
            trial, trial_closes = portfolio.model_copy(deep=True), dict(closes)
            try:
                deploy_txns, record = _deploy_idle_cash(
                    trial, trial_closes, set(existing_ids), review_date, store,
                    list((shelf_index or {}).values()), candidate_quotes or {}, surveillance,
                    sales)
            except Exception as exc:
                logger.error("[autopilot] idle-cash deployment failed for %s, nothing "
                             "bought: %s", portfolio.user_id, exc)
                deploy_txns, record = [], {"date": day, "bought": [],
                                           "error": f"deployment failed: {exc}",
                                           "reasons": [f"deployment failed: {exc}"]}
            else:
                portfolio = trial
                closes.update(trial_closes)
            txns += deploy_txns
            if report is not None:
                report["deployment"] = record
        if not txns:
            # Still stamp the run marker so re-triggered pipelines skip cheaply,
            # but avoid rewriting portfolio.json when nothing happened at all.
            portfolio.last_autopilot_run = day
            store.save(portfolio)
        else:
            for t in txns:
                store.append_transaction(t)
            portfolio.last_autopilot_run = day
            store.save(portfolio)
        # FIX-028: under this portfolio's lock, so what it holds cannot move
        # while the managed list is set to follow it.
        managed = _follow_holdings(portfolio, txns)
    if report is not None and managed["not_reviewed"]:
        report["not_reviewed"] = managed["not_reviewed"]
    if not txns:
        return []
    logger.info("[autopilot] %s executed %d trade(s) for %s",
                day, len(txns), portfolio.user_id)
    return txns


def record_value_point(store: PortfolioStore, portfolio: Portfolio,
                       closes: dict[str, float], review_date: date) -> dict | None:
    """Append today's equity snapshot (spec §3.3). Skips when cash accounting
    is off or the point already exists (idempotent re-runs)."""
    if portfolio.cash_deployable is None:
        return None
    if review_date > _today_ist():
        logger.warning("[autopilot] refusing future value point %s", review_date)
        return None
    day = review_date.isoformat()
    hist = store.load_value_history(limit=1)
    # Skip both the exact-duplicate (idempotent re-run) and out-of-order
    # (stale review_date replayed after a newer point already recorded)
    # cases — either would append a point older than or equal to the tail.
    if hist and hist[-1].get("date", "") >= day:
        if hist[-1].get("date") != day:
            logger.info("[autopilot] skipping out-of-order value point %s "
                        "(history tail is %s)", day, hist[-1].get("date"))
        return None
    mv = round(sizing.holdings_value(portfolio, closes), 2)
    total = round(mv + portfolio.cash_deployable, 2)
    day_change_pct = None
    change_span_days = None   # AUD-089: gap behind day_change_pct, calendar days
    if hist and hist[-1].get("total_equity"):
        prev = hist[-1]["total_equity"]
        if prev > 0:
            day_change_pct = round((total / prev - 1) * 100, 4)
        prev_date = hist[-1].get("date")
        if prev_date:
            try:
                change_span_days = (review_date - date.fromisoformat(prev_date)).days
            except ValueError:
                pass
    # recorded_at: when the point was taken, so the Nifty comparison can tell
    # whether a holding added that day is in it (results.capital_flows).
    point = {"date": day, "market_value": mv,
             "cash": round(portfolio.cash_deployable, 2), "total_equity": total,
             "capital_in": portfolio.capital_in, "day_change_pct": day_change_pct,
             "change_span_days": change_span_days, "recorded_at": _now_iso()}
    # The holdings this point valued at their cost, having no close: the
    # comparison cannot value an arrival among them (results.capital_flows).
    at_cost = sorted(h.symbol for h in portfolio.holdings if h.symbol not in closes)
    if at_cost:
        point["at_cost"] = at_cost
    store.append_value_point(point)
    return point
