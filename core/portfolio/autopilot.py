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


def _execute_buys(portfolio: Portfolio, advice: list[AdviceRecord],
                  closes: dict[str, float], existing_ids: set[str],
                  switch_proceeds: list[tuple[float, AdviceRecord]],
                  review_date: date, store: PortfolioStore,
                  sector_lookup: dict[str, str] | None) -> list[TransactionRecord]:
    return []   # Task 5 (ADD) and Task 6 (SWITCH buy leg) fill this in.


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
