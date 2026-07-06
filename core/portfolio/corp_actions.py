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
            return AppliedCorpAction(
                key=key, ex_date=ex_date, kind="dividend", desc=desc,
                dividend_per_share=float(m.group(1)), applied_on=today_iso,
            )
    return None


def apply_actions_to_holding(
    holding: Holding, actions: list[AppliedCorpAction | None], today: date
) -> int:
    """Apply every unapplied action with buy_date < ex_date <= today.
    Mutates the holding in place. Returns number applied."""
    applied_keys = {a.key for a in holding.applied_actions}
    count = 0
    for action in actions:
        if action is None or action.key in applied_keys:
            continue
        ex = date.fromisoformat(action.ex_date)
        if ex <= date.fromisoformat(holding.buy_date) or ex > today:
            continue
        if action.kind in ("bonus", "split") and action.ratio > 0:
            holding.adj_avg_price = holding.adj_avg_price / action.ratio
            holding.adj_qty = holding.adj_qty * action.ratio
        elif action.kind == "dividend":
            holding.dividends_received += holding.adj_qty * action.dividend_per_share
        holding.applied_actions.append(action)
        applied_keys.add(action.key)
        count += 1
        logger.info(
            "[corp_actions] %s: applied %s (%s) ex=%s ratio=%.3f dps=%.2f",
            holding.symbol, action.kind, action.desc[:60], action.ex_date,
            action.ratio, action.dividend_per_share,
        )
    return count


def sync_corp_actions(store: PortfolioStore, today: date, fetch=fetch_corp_actions) -> dict:
    """Daily sync for every holding of one user. Non-fatal per symbol —
    pipeline errors are telemetry, never training signal."""
    portfolio = store.load()
    total, touched = 0, []
    for holding in portfolio.holdings:
        try:
            rows = fetch(holding.symbol)
            actions = [parse_action(dict(r, symbol=holding.symbol)) for r in rows]
            n = apply_actions_to_holding(holding, actions, today)
            if n:
                total += n
                touched.append(holding.symbol)
        except Exception as exc:
            logger.warning(
                "[corp_actions] sync failed for %s (non-fatal): %s", holding.symbol, exc
            )
    if total:
        try:
            store.save(portfolio)
        except Exception as exc:
            logger.error(
                "[corp_actions] portfolio save failed after %d applied actions (non-fatal): %s",
                total, exc,
            )
            return {"applied": 0, "symbols": [], "save_failed": True}
    return {"applied": total, "symbols": touched}
