"""
Compass Autopilot — deterministic execution of advisor verdicts on the
virtual portfolio (spec docs/superpowers/specs/2026-07-10-compass-autopilot-design.md §4).

The LLM never decides; this module is a pure function over AdviceRecords.
Virtual money only — no broker calls, ever. The transactions ledger is the
audit authority; portfolio.json is derived state.

Trade ordering per run (deterministic): sells first (EXIT, SWITCH sell leg,
TRIM — symbol asc), then buys (SWITCH buy legs, then ADDs by confidence
desc, ties symbol asc). Sells free cash before buys consume it.
"""
from __future__ import annotations

import hashlib
import logging
import math
from datetime import date, datetime, timedelta, timezone

from core.config import settings
from backend.shared.schemas.portfolio import (
    AdviceRecord,
    Holding,
    Portfolio,
    TransactionRecord,
    WatchlistItem,
)
from core.portfolio.store import PortfolioStore
from core.portfolio.pricing import close_on
from core.portfolio.promotion import promote_symbol

logger = logging.getLogger(__name__)


def make_txn_id(user_id: str, d: str, symbol: str, side: str, ref: str) -> str:
    return hashlib.sha256(f"{user_id}|{d}|{symbol}|{side}|{ref}".encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _txn(portfolio: Portfolio, rec: AdviceRecord, *, side: str, qty: float,
         price: float, cash_before: float, holding_qty_after: float,
         realized: float, note: str, symbol: str | None = None) -> TransactionRecord:
    sym = symbol or rec.symbol
    ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
    return TransactionRecord(
        txn_id=make_txn_id(portfolio.user_id, rec.date, sym, side, ref),
        date=rec.date, ts=_now_iso(), user_id=portfolio.user_id, symbol=sym,
        side=side, qty=qty, price=price, value=round(qty * price, 2),
        cash_before=round(cash_before, 2),
        cash_after=round(portfolio.cash_deployable, 2),
        holding_qty_after=holding_qty_after, realized_pnl=realized,
        source="autopilot", verdict=rec.verdict, advice_ref=ref,
        triggers=list(rec.triggers), note=note,
    )


def _find(portfolio: Portfolio, symbol: str) -> Holding | None:
    return next((h for h in portfolio.holdings if h.symbol == symbol), None)


def _execute_sells(portfolio: Portfolio, advice: list[AdviceRecord],
                   closes: dict[str, float], existing_ids: set[str],
                   ) -> tuple[list[TransactionRecord], list[tuple[float, AdviceRecord]]]:
    txns: list[TransactionRecord] = []
    switch_proceeds: list[tuple[float, AdviceRecord]] = []
    sells = sorted((a for a in advice if a.verdict in ("EXIT", "SWITCH", "TRIM")),
                   key=lambda a: a.symbol)
    for rec in sells:
        h = _find(portfolio, rec.symbol)
        if h is None or h.adj_qty <= 0:
            continue
        price = closes.get(rec.symbol) or rec.close
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
            continue
        cash_before = portfolio.cash_deployable
        realized = h.sell(qty, price)
        portfolio.cash_deployable = round(portfolio.cash_deployable + qty * price, 2)
        if h.adj_qty <= 1e-9:
            portfolio.holdings = [x for x in portfolio.holdings if x.symbol != h.symbol]
            if rec.verdict in ("EXIT", "SWITCH") and not any(
                    w.symbol == h.symbol for w in portfolio.watchlist):
                portfolio.watchlist.append(WatchlistItem(
                    symbol=h.symbol, sector=h.sector, added=rec.date,
                    reason="autopilot_exit", source="autopilot"))
        txns.append(_txn(portfolio, rec, side="SELL", qty=qty, price=price,
                         cash_before=cash_before,
                         holding_qty_after=(h.adj_qty if h.adj_qty > 1e-9 else 0.0),
                         realized=realized, note=note))
        if rec.verdict == "SWITCH" and rec.switch_candidate:
            switch_proceeds.append((qty * price, rec))
    return txns, switch_proceeds


def _trading_days_between(start: date, end: date) -> int:
    from core.intelligence.rl.nse_calendar import is_trading_day
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if is_trading_day(d):
            n += 1
    return n


def _portfolio_market_value(portfolio: Portfolio, closes: dict[str, float]) -> float:
    return sum(h.adj_qty * closes.get(h.symbol, h.adj_avg_price)
               for h in portfolio.holdings)


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


def _execute_buys(portfolio: Portfolio, advice: list[AdviceRecord],
                  closes: dict[str, float], existing_ids: set[str],
                  switch_proceeds: list[tuple[float, AdviceRecord]],
                  review_date: date, store: PortfolioStore,
                  sector_lookup: dict[str, str] | None) -> list[TransactionRecord]:
    txns: list[TransactionRecord] = []
    floor_cash = settings.AUTOPILOT_MIN_CASH_FLOOR

    for proceeds, rec in switch_proceeds:
        cand = rec.switch_candidate.strip().upper()
        if not cand:
            continue
        try:
            price = close_on(cand, review_date)
        except Exception as exc:
            logger.warning("[autopilot] SWITCH buy %s skipped: unpriceable (%s)",
                           cand, exc)
            continue
        budget = min(proceeds, portfolio.cash_deployable - floor_cash)
        qty = float(math.floor(budget / price)) if price > 0 else 0.0
        if qty < 1:
            logger.info("[autopilot] SWITCH buy %s skipped: budget %.2f < 1 share",
                        cand, budget)
            continue
        ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
        if make_txn_id(portfolio.user_id, rec.date, cand, "BUY", ref) in existing_ids:
            continue
        sector = (sector_lookup or {}).get(cand, "")
        if not sector:
            try:
                from backend.sectors.registry import SectorRegistry
                sector = SectorRegistry.resolve(cand).strip().lower()
            except Exception:
                sector = "generic"
        cash_before = portfolio.cash_deployable
        portfolio.cash_deployable = round(portfolio.cash_deployable - qty * price, 2)
        qty_after = _buy_into_holding(portfolio, cand, sector, qty, price,
                                      review_date.isoformat())
        txns.append(_txn(portfolio, rec, side="BUY", qty=qty, price=price,
                         cash_before=cash_before, holding_qty_after=qty_after,
                         realized=0.0, note=f"switch from {rec.symbol}",
                         symbol=cand))
        try:
            promote_symbol(cand, sector, origin="held")
        except Exception as exc:
            logger.warning("[autopilot] promotion failed for %s (non-fatal): %s",
                           cand, exc)

    adds = sorted((a for a in advice if a.verdict == "ADD"),
                  key=lambda a: (-a.confidence, a.symbol))
    cap = settings.ADVISOR_MAX_POSITION_PCT / 100.0
    for rec in adds:
        h = _find(portfolio, rec.symbol)
        if h is None:
            continue
        price = closes.get(rec.symbol) or rec.close
        if price <= 0:
            continue
        last_add = _last_add_date(store, rec.symbol)
        if last_add is not None and _trading_days_between(
                last_add, review_date) < settings.AUTOPILOT_ADD_COOLDOWN_TD:
            logger.info("[autopilot] ADD %s skipped: cooldown", rec.symbol)
            continue
        position_value = h.adj_qty * price
        tranche = position_value * settings.AUTOPILOT_ADD_TRANCHE_PCT / 100.0
        total_mv = _portfolio_market_value(portfolio, closes)
        # post-trade weight cap: (pos + X)/(total + X) <= cap
        weight_headroom = (cap * total_mv - position_value) / (1 - cap) \
            if cap < 1 else float("inf")
        budget = min(tranche, max(0.0, weight_headroom),
                     portfolio.cash_deployable - floor_cash)
        qty = float(math.floor(budget / price))
        if qty < 1:
            logger.info("[autopilot] ADD %s skipped: budget %.2f < 1 share @ %.2f",
                        rec.symbol, budget, price)
            continue
        ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
        if make_txn_id(portfolio.user_id, rec.date, rec.symbol, "BUY", ref) in existing_ids:
            continue
        cash_before = portfolio.cash_deployable
        portfolio.cash_deployable = round(portfolio.cash_deployable - qty * price, 2)
        qty_after = _buy_into_holding(portfolio, rec.symbol, h.sector, qty, price,
                                      review_date.isoformat())
        txns.append(_txn(portfolio, rec, side="BUY", qty=qty, price=price,
                         cash_before=cash_before, holding_qty_after=qty_after,
                         realized=0.0, note="add_tranche"))
    return txns


def execute_advice(store: PortfolioStore, portfolio: Portfolio,
                   advice: list[AdviceRecord], closes: dict[str, float],
                   review_date: date,
                   sector_lookup: dict[str, str] | None = None,
                   ) -> list[TransactionRecord]:
    """Execute one review-day's verdicts. Appends transactions FIRST, then
    saves the portfolio (txn_id dedupe makes a crash between the two safe)."""
    if not settings.AUTOPILOT_ENABLED or not portfolio.autopilot \
            or portfolio.cash_deployable is None:
        return []
    day = review_date.isoformat()
    if portfolio.last_autopilot_run == day:
        return []
    existing_ids = {t.txn_id for t in store.load_transactions(limit=2000)}

    sell_txns, switch_proceeds = _execute_sells(portfolio, advice, closes, existing_ids)
    existing_ids |= {t.txn_id for t in sell_txns}
    buy_txns = _execute_buys(portfolio, advice, closes, existing_ids,
                             switch_proceeds, review_date, store, sector_lookup)
    txns = sell_txns + buy_txns
    if not txns:
        # Still stamp the run marker so re-triggered pipelines skip cheaply,
        # but avoid rewriting portfolio.json when nothing happened at all.
        portfolio.last_autopilot_run = day
        store.save(portfolio)
        return []
    for t in txns:
        store.append_transaction(t)
    portfolio.last_autopilot_run = day
    store.save(portfolio)
    logger.info("[autopilot] %s executed %d trade(s) for %s",
                day, len(txns), portfolio.user_id)
    return txns


def record_value_point(store: PortfolioStore, portfolio: Portfolio,
                       closes: dict[str, float], review_date: date) -> dict | None:
    """Append today's equity snapshot (spec §3.3). Skips when cash accounting
    is off or the point already exists (idempotent re-runs)."""
    if portfolio.cash_deployable is None:
        return None
    day = review_date.isoformat()
    hist = store.load_value_history(limit=1)
    if hist and hist[-1].get("date") == day:
        return None
    mv = round(_portfolio_market_value(portfolio, closes), 2)
    total = round(mv + portfolio.cash_deployable, 2)
    day_change_pct = None
    if hist and hist[-1].get("total_equity"):
        prev = hist[-1]["total_equity"]
        if prev > 0:
            day_change_pct = round((total / prev - 1) * 100, 4)
    point = {"date": day, "market_value": mv,
             "cash": round(portfolio.cash_deployable, 2), "total_equity": total,
             "capital_in": portfolio.capital_in, "day_change_pct": day_change_pct}
    store.append_value_point(point)
    return point
