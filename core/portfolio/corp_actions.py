"""
Compass Phase A — daily corp-action sync (spec §4.1 corp-action invariant).

Adjusts adj_avg_price / adj_qty / dividends_received BEFORE any advisor rule
runs. Without this, a 1:1 bonus looks like a −50% crash and fires a false
EXIT. Raw qty/avg_buy_price are NEVER mutated. Idempotent via applied-action
keys stored on the holding.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from backend.shared.schemas.portfolio import AppliedCorpAction, Holding
from core.portfolio.store import PortfolioStore
from services.data.fetchers.corporate_events import fetch_corp_actions

logger = logging.getLogger(__name__)

_BONUS_RE = re.compile(r"bonus[^0-9]*?(\d+)\s*:\s*(\d+)", re.I)
_SPLIT_RE = re.compile(
    r"from\s+r[se]\.?\s*(\d+(?:\.\d+)?).{0,40}?to\s+r[se]\.?\s*(\d+(?:\.\d+)?)", re.I
)
_DIV_RE = re.compile(r"dividend[^0-9]*(\d+(?:\.\d+)?)", re.I)

_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")


def _parse_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    for fmt in _NSE_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_action(row: dict) -> AppliedCorpAction | None:
    """Parse one raw NSE actions() row into an AppliedCorpAction.
    Returns None for unrecognised or non-financial rows (AGM/EGM/rights…)."""
    desc = ""
    for key in ("subject", "desc", "purpose"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            desc = v.strip()
            break
    ex_raw = ""
    for key in ("exDate", "ex_date", "date", "exdate"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            ex_raw = v.strip()
            break
    ex_date = _parse_date(ex_raw)
    if not desc or not ex_date:
        return None

    low = desc.lower()
    symbol = str(row.get("symbol", "")).upper()
    key = f"{symbol}|{ex_date}|{desc[:40]}"
    today_iso = date.today().isoformat()

    m = _BONUS_RE.search(low)
    if m:
        new, base = float(m.group(1)), float(m.group(2))
        if base > 0:
            return AppliedCorpAction(
                key=key, ex_date=ex_date, kind="bonus", desc=desc,
                ratio=(new + base) / base, applied_on=today_iso,
            )
    if "split" in low or "sub-division" in low:
        m = _SPLIT_RE.search(low)
        if m:
            old_fv, new_fv = float(m.group(1)), float(m.group(2))
            if new_fv > 0:
                return AppliedCorpAction(
                    key=key, ex_date=ex_date, kind="split", desc=desc,
                    ratio=old_fv / new_fv, applied_on=today_iso,
                )
    if "dividend" in low:
        m = _DIV_RE.search(low)
        if m:
            after = low[m.end(1):].lstrip()
            if after.startswith("%"):
                # AUD-046: percent-of-face-value quote ("Dividend 150%") —
                # booking it as ₹/share would inflate P&L and could suppress a
                # legitimate EXIT. Needs the face value to convert; skip.
                logger.warning(
                    "[corp_actions] percent-of-face-value dividend skipped "
                    "(needs face value, AUD-046): %s", desc[:80],
                )
                return None
            return AppliedCorpAction(
                key=key, ex_date=ex_date, kind="dividend", desc=desc,
                dividend_per_share=float(m.group(1)), applied_on=today_iso,
            )
    if "split" in low or "bonus" in low or "sub-division" in low:
        logger.warning(
            "[corp_actions] unparseable split/bonus row (manual review needed): %s", desc[:80]
        )
    return None


def apply_actions_to_holding(
    holding: Holding, actions: list[AppliedCorpAction | None], today: date
) -> tuple[int, list[tuple[AppliedCorpAction, float]]]:
    """Apply every unapplied action with buy_date < ex_date <= today.
    Mutates the holding in place. Returns (number applied, dividend events)
    where each dividend event is (action, cash credit) — the caller books the
    credit to cash and the transactions ledger (AUD-045)."""
    applied_keys = {a.key for a in holding.applied_actions}
    valid = sorted((a for a in actions if a is not None), key=lambda a: a.ex_date)
    count = 0
    div_events: list[tuple[AppliedCorpAction, float]] = []
    for action in valid:
        if action.key in applied_keys:
            continue
        ex = date.fromisoformat(action.ex_date)
        if ex <= date.fromisoformat(holding.buy_date) or ex > today:
            continue
        if action.kind in ("bonus", "split") and action.ratio > 0:
            holding.adj_avg_price = holding.adj_avg_price / action.ratio
            holding.adj_qty = holding.adj_qty * action.ratio
        elif action.kind == "dividend":
            credit = holding.adj_qty * action.dividend_per_share
            holding.dividends_received += credit
            div_events.append((action, round(credit, 2)))
        holding.applied_actions.append(action)
        applied_keys.add(action.key)
        count += 1
        logger.info(
            "[corp_actions] %s: applied %s (%s) ex=%s ratio=%.3f dps=%.2f",
            holding.symbol, action.kind, action.desc[:60], action.ex_date,
            action.ratio, action.dividend_per_share,
        )
    return count, div_events


def sync_corp_actions(store: PortfolioStore, today: date, fetch=fetch_corp_actions) -> dict:
    """Daily sync for every holding of one user. Non-fatal per symbol —
    pipeline errors are telemetry, never training signal.

    Two phases (AUD-001): network fetches run OUTSIDE the store lock (seconds
    per symbol), then apply + dividend cash credit + save run in one short
    critical section against a FRESH load. Dividends credit cash_deployable
    and append a DIV ledger row when cash accounting is on (AUD-045)."""
    from datetime import datetime, timezone

    # Phase 1 — network, lock-free, keyed by symbol from a snapshot.
    snapshot = store.load()
    actions_by_symbol: dict[str, list] = {}
    for holding in snapshot.holdings:
        try:
            rows = fetch(holding.symbol)
            actions_by_symbol[holding.symbol] = [
                parse_action(dict(r, symbol=holding.symbol)) for r in rows
            ]
        except Exception as exc:
            logger.warning(
                "[corp_actions] sync failed for %s (non-fatal): %s", holding.symbol, exc
            )
    if not any(actions_by_symbol.values()):
        return {"applied": 0, "symbols": []}

    # Phase 2 — locked apply + credit + save on fresh state.
    from core.portfolio.autopilot import make_txn_id   # lazy: avoids import cycle
    from backend.shared.schemas.portfolio import TransactionRecord

    with store.locked():
        portfolio = store.load()
        total, touched, div_txns = 0, [], []
        for holding in portfolio.holdings:
            actions = actions_by_symbol.get(holding.symbol)
            if not actions:
                continue
            n, div_events = apply_actions_to_holding(holding, actions, today)
            if n:
                total += n
                touched.append(holding.symbol)
            for action, credit in div_events:
                if portfolio.cash_deployable is None or credit <= 0:
                    continue
                cash_before = portfolio.cash_deployable
                portfolio.cash_deployable = round(cash_before + credit, 2)
                div_txns.append(TransactionRecord(
                    txn_id=make_txn_id(portfolio.user_id, action.ex_date,
                                       holding.symbol, "DIV", action.key),
                    date=action.ex_date,
                    ts=datetime.now(timezone.utc).isoformat(),
                    user_id=portfolio.user_id, symbol=holding.symbol,
                    side="DIV", qty=0.0, price=action.dividend_per_share,
                    value=round(credit, 2), cash_before=round(cash_before, 2),
                    cash_after=portfolio.cash_deployable,
                    holding_qty_after=holding.adj_qty, realized_pnl=0.0,
                    source="autopilot", note=f"dividend: {action.desc[:40]}"))
        if total:
            existing = {t.txn_id for t in store.load_transactions(limit=2000)}
            for t in div_txns:
                if t.txn_id not in existing:
                    store.append_transaction(t)
            try:
                store.save(portfolio)
            except Exception as exc:
                logger.error(
                    "[corp_actions] portfolio save failed after %d applied actions (non-fatal): %s",
                    total, exc,
                )
                return {"applied": 0, "symbols": [], "save_failed": True}
        return {"applied": total, "symbols": touched}
