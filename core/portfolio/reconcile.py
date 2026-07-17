"""
Audit Wave 1 (AUD-006) — transactions.jsonl ⇄ portfolio.json reconciler.

DETECT + ALERT ONLY, never repairs: the ledger is the audit authority, but a
mid-run crash can leave double entries (the retry class AUD-006 documents), so
auto-repair could cement a bad state. A human decides.

Three checks, run daily as a non-fatal pipeline step:
  1. Chain continuity — txn[i].cash_before ≈ txn[i-1].cash_after. A gap is the
     AUD-001 lost-update signature (a write landed that the ledger never saw,
     or vice versa).
  2. Final cash — txn[0].cash_before + Σ(cash_after − cash_before) vs
     portfolio.cash_deployable (covers BUY/SELL/DIV and capital injections,
     since each row records its own delta).
  3. Per-symbol net quantity — Σ(BUY qty) − Σ(SELL qty) vs held adj_qty, for
     holdings with NO ratio-changing corp actions (split/bonus change adj_qty
     without a ledger row; those symbols are reported "unverifiable").
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from core.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)

_CHAIN_TOL = 0.05     # ₹ — rounding slack between consecutive rows
_CASH_TOL = 1.00      # ₹ — final cash tolerance
_QTY_TOL = 1e-6


def _alert(user_id: str, issues: list[str]) -> None:
    """One critical push alert per drift detection. Never raises."""
    try:
        # AUD-015: ops-severity event — broadcast to the whole alert audience
        # (the affected user is named in the message).
        from core.delivery.alerts import AlertEvent, emit_alerts_broadcast
        emit_alerts_broadcast([AlertEvent(
            date=date.today().isoformat(), kind="ledger_drift", symbol="",
            message="Ledger/portfolio reconciliation drift for user "
                    f"'{user_id}': " + " | ".join(issues[:5]),
            severity="critical",
        )], title="Portfolio reconciliation drift")
    except Exception as exc:
        logger.warning("[reconcile] alert failed (non-fatal): %s", exc)


def reconcile(store: PortfolioStore) -> dict:
    """Replay the full ledger against portfolio.json. Returns
    {"status": "clean"|"drift"|"skipped", "issues": [...], "unverifiable": [...]}.
    Never raises, never mutates."""
    try:
        txns = store.load_transactions(limit=100000)
        portfolio = store.load()
        if portfolio.cash_deployable is None or not txns:
            return {"status": "skipped", "issues": [], "unverifiable": []}

        issues: list[str] = []

        # 1. Chain continuity (AUD-001 lost-update signature).
        for prev, cur in zip(txns, txns[1:]):
            if abs(cur.cash_before - prev.cash_after) > _CHAIN_TOL:
                issues.append(
                    f"cash chain gap at {cur.txn_id} ({cur.symbol} {cur.side}): "
                    f"cash_before {cur.cash_before:.2f} != prior cash_after "
                    f"{prev.cash_after:.2f}")

        # 2. Final cash from per-row deltas.
        expected_cash = txns[0].cash_before + sum(
            t.cash_after - t.cash_before for t in txns)
        if abs(expected_cash - portfolio.cash_deployable) > _CASH_TOL:
            issues.append(
                f"cash mismatch: ledger replay expects {expected_cash:.2f}, "
                f"portfolio holds {portfolio.cash_deployable:.2f}")

        # 3. Per-symbol net qty (skip corp-action-adjusted holdings).
        net_qty: dict[str, float] = defaultdict(float)
        for t in txns:
            if t.side == "BUY":
                net_qty[t.symbol] += t.qty
            elif t.side == "SELL":
                net_qty[t.symbol] -= t.qty
        unverifiable: list[str] = []
        for h in portfolio.holdings:
            if any(a.ratio != 1.0 for a in h.applied_actions):
                unverifiable.append(h.symbol)
                continue
            if abs(net_qty.get(h.symbol, 0.0) - h.adj_qty) > _QTY_TOL:
                issues.append(
                    f"qty mismatch {h.symbol}: ledger nets "
                    f"{net_qty.get(h.symbol, 0.0):g}, portfolio holds {h.adj_qty:g}")

        if issues:
            logger.error("[reconcile] DRIFT for %s: %s", store.user_id, issues)
            _alert(store.user_id, issues)
            return {"status": "drift", "issues": issues, "unverifiable": unverifiable}
        logger.info("[reconcile] clean for %s — %d txns replayed, %d holdings "
                    "verified (%d unverifiable)", store.user_id, len(txns),
                    len(portfolio.holdings) - len(unverifiable), len(unverifiable))
        return {"status": "clean", "issues": [], "unverifiable": unverifiable}
    except Exception as exc:
        logger.warning("[reconcile] failed (non-fatal): %s", exc)
        return {"status": "skipped", "issues": [], "unverifiable": []}
