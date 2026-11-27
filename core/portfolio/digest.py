"""
Compass Phase A — EOD digest (spec §7): per-holding verdicts with one-line
reasons, P&L move, escalations. Event-triggered on review+advisor completion,
never clock-scheduled (at 40 tickers the review runs ~80 min).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from backend.shared.schemas.portfolio import AdviceRecord, Portfolio
from core.portfolio.advisor import explain_triggers


def keep_day_record(digest: dict, previous: dict | None) -> None:
    """FIX-025 L2, FIX-028: a same-day re-run stops at the autopilot's run
    marker, so it has no trades and no record of its own. Keep what the day's
    first run recorded: its idle-cash record, its trades, and each row's
    reason for no top-up or no daily review. Call only when this run's
    execution did not run (no trades and an empty run report)."""
    if not previous or previous.get("date") != digest.get("date"):
        return
    if "deployment" in previous and "deployment" not in digest:
        digest["deployment"] = previous["deployment"]
    if previous.get("trades") and not digest.get("trades"):
        digest["trades"] = previous["trades"]
    earlier = {r.get("symbol"): r for r in previous.get("holdings", [])}
    for row in digest.get("holdings", []):
        for key in ("top_up_skipped", "not_reviewed"):
            kept = earlier.get(row.get("symbol"), {}).get(key)
            # A refused top-up belongs to an ADD; a row that now says
            # otherwise never carries it.
            if kept and key not in row and (key != "top_up_skipped"
                                            or row.get("verdict") == "ADD"):
                row[key] = kept


def build_digest(
    user_id: str,
    review_date: date,
    advice: list[AdviceRecord],
    portfolio: Portfolio,
    closes: dict[str, float],
    transactions: list | None = None,
    deployment: dict | None = None,
    top_ups_skipped: list[dict] | None = None,
    not_reviewed: list[dict] | None = None,
) -> dict:
    """`deployment` is the autopilot's idle-cash record for the day
    (core/portfolio/deployment.py `run_record`), present only when deployment
    is on for the portfolio: what it bought and why any idle cash stayed.
    `top_ups_skipped` names each ADD NSE's surveillance report refused
    ({"symbol", "why"}); its row keeps the ADD verdict and says why no shares
    were bought. `not_reviewed` names each holding the managed list could not
    take ({"symbol", "why"}, FIX-028: the list's cap): its row says it has no
    daily review or monthly forecast."""
    value = 0.0
    cost = 0.0
    rows = []
    by_symbol = {a.symbol: a for a in advice}
    skipped = {s["symbol"]: s["why"] for s in (top_ups_skipped or [])}
    unreviewed = {s["symbol"]: s["why"] for s in (not_reviewed or [])}
    for h in portfolio.holdings:
        close = closes.get(h.symbol)
        if close is not None:
            value += h.adj_qty * close
            cost += h.adj_qty * h.adj_avg_price
        rec = by_symbol.get(h.symbol)
        rows.append({
            "symbol": h.symbol,
            "verdict": rec.verdict if rec else "NO_DATA",
            "close": close,
            "pnl_pct": round(h.unrealised_pnl_pct(close), 2) if close is not None else None,
            # `narrative` is the LLM's line and empties out whenever narration
            # fails; the deterministic triggers are always present, so a failed
            # narration costs prose, never the reason itself.
            "reason": (rec.narrative.strip() or explain_triggers(rec.triggers)) if rec
                      else "no advisor run for this holding today",
            "notes": rec.notes if rec else [],
            # Carried so the brief can name the destination. Without it a
            # SWITCH reached "Needs attention" as a verdict with no object.
            "switch_candidate": rec.switch_candidate if rec else "",
            **({"top_up_skipped": skipped[h.symbol]} if h.symbol in skipped else {}),
            **({"not_reviewed": unreviewed[h.symbol]} if h.symbol in unreviewed else {}),
        })
    escalations = sorted(a.symbol for a in advice if a.verdict in ("TRIM", "EXIT", "SWITCH"))
    digest = {
        "date": review_date.isoformat(),
        "user_id": user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_value": round(value, 2),
        "cost_basis": round(cost, 2),
        "total_pnl_pct": value / cost * 100 - 100 if cost > 0 else 0.0,
        "holdings": rows,
        "escalations": escalations,
        "trades": [t.model_dump() for t in (transactions or [])],
    }
    if deployment is not None:
        digest["deployment"] = deployment
    return digest
