"""
Compass Autopilot — deterministic execution of advisor verdicts on the
virtual portfolio (spec docs/superpowers/specs/2026-07-10-compass-autopilot-design.md §4).

The LLM never decides; this module is a pure function over AdviceRecords.
Virtual money only — no broker calls, ever. The transactions ledger is the
audit authority; portfolio.json is derived state.

Trade ordering per run (deterministic): sells first (EXIT, SWITCH sell leg,
TRIM — symbol asc), then buys (SWITCH buy legs, then ADDs by confidence
desc, ties symbol asc). Sells free cash before buys consume it.

SA-050: every buy is sized by core/portfolio/sizing.py (position and sector
caps of total equity, after the trade, and the cash floor), and a SWITCH
buy, which opens a position, must also sit inside its shelf idea's entry
band. What a cap leaves unspent stays in cash; the BUY's note says how much
and why. A skipped SWITCH buy leg says why on its SELL's note.

SA-048: every BUY and SELL pays its trading costs (core/portfolio/costs.py),
written on its own ledger row and taken from cash with it, so the txn_id
dedupe that stops a re-run trading twice also stops it charging twice. A
SWITCH buy leg asks for the sale's proceeds net of the sale's costs.
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
    TradeCosts,
    TransactionRecord,
    WatchlistItem,
)
from backend.shared.pipeline import decision_gate as dg
from core.portfolio import costs, sizing
from core.portfolio.store import PortfolioStore
from core.portfolio.identity_reconcile import symbol_identity_issue
from core.portfolio.pricing import session_close
from core.portfolio.promotion import promote_symbol

logger = logging.getLogger(__name__)


def make_txn_id(user_id: str, d: str, symbol: str, side: str, ref: str) -> str:
    return hashlib.sha256(f"{user_id}|{d}|{symbol}|{side}|{ref}".encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_ist() -> date:
    """IST calendar date — the reference clock for all date guards (AUD-044).
    Module-level seam so tests can freeze 'today'."""
    from core.intelligence.rl.nse_calendar import now_ist
    return now_ist().date()


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


def _execute_buys(portfolio: Portfolio, advice: list[AdviceRecord],
                  closes: dict[str, float], existing_ids: set[str],
                  switch_proceeds: list[SwitchLeg],
                  review_date: date, store: PortfolioStore,
                  sector_lookup: dict[str, str] | None,
                  shelf_index: dict | None = None) -> list[TransactionRecord]:
    txns: list[TransactionRecord] = []
    floor_cash = settings.AUTOPILOT_MIN_CASH_FLOOR

    for proceeds, rec, sell in switch_proceeds:
        cand = rec.switch_candidate.strip().upper()
        if not cand:
            continue
        try:
            quote, session = session_close(cand, review_date)
            price = quote.close
        except Exception as exc:
            logger.warning("[autopilot] SWITCH buy %s skipped: unpriceable (%s)",
                           cand, exc)
            _note_skipped_buy(sell, cand, proceeds, "no price for the review session")
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
        closes[cand] = price                   # AUD-003: one price basis per run
        # SA-050: a new position is bought only inside its idea's entry band.
        allowed, band_note = sizing.entry_check(price, (shelf_index or {}).get(cand))
        if not allowed:
            logger.info("[autopilot] SWITCH buy %s skipped: %s", cand, band_note)
            _note_skipped_buy(sell, cand, proceeds, band_note)
            continue
        sector = (sector_lookup or {}).get(cand, "")
        if not sector:
            try:
                from backend.sectors.registry import SectorRegistry
                sector = SectorRegistry.resolve(cand).strip().lower()
            except Exception:
                sector = "generic"
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
        try:
            promote_symbol(cand, sector, origin="held")
        except Exception as exc:
            logger.warning("[autopilot] promotion failed for %s (non-fatal): %s",
                           cand, exc)

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


def execute_advice(store: PortfolioStore, portfolio: Portfolio,
                   advice: list[AdviceRecord], closes: dict[str, float],
                   review_date: date,
                   sector_lookup: dict[str, str] | None = None,
                   shelf_index: dict | None = None,
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
    destination missing from it has no entry band and is not bought."""
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
        existing_ids = {t.txn_id for t in store.load_transactions(limit=2000)}

        sell_txns, switch_proceeds = _execute_sells(portfolio, advice, closes,
                                                    existing_ids)
        existing_ids |= {t.txn_id for t in sell_txns}
        buy_txns = _execute_buys(portfolio, advice, closes, existing_ids,
                                 switch_proceeds, review_date, store, sector_lookup,
                                 shelf_index)
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
    store.append_value_point(point)
    return point
