"""
Compass Phase C — Weekly Review (spec §7): Sun 18:00 IST. Allocation vs risk
profile, laggard analysis, switch candidates from the shelf, advice-ledger
scoreboard ("last month: 7/9 calls right"). Deterministic assembly; ONE
BULK-tier headline call (fallback text on failure).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone

from core.config import settings
from core.delivery.channels import deliver
from core.portfolio.store import PortfolioStore, active_user_ids

logger = logging.getLogger(__name__)

_SCOREBOARD_WINDOW_DAYS = 28
_SCOREBOARD_MIN_AGE_DAYS = 5           # advice younger than this (calendar days) isn't judged
_LAGGARD_COUNT = 3
_SWITCH_CANDIDATE_COUNT = 3

_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-4 sentence weekly portfolio review headline (research tone; NEVER
the word "advice").

Allocation: {allocation}
Concentration flags: {concentration}
Laggards: {laggards}
Advice scoreboard (last 4 weeks): {scoreboard}

Respond with JSON: {{"headline": "<2-4 sentences>"}}"""


def _latest_closes(symbols: list[str], on: date) -> dict[str, float]:
    """Last close per symbol from the EOD parquet cache. {} on failure."""
    try:
        from services.data.stores.eod_store import EodStore
        window = EodStore().load_window(end=on, sessions=10)
        out: dict[str, float] = {}
        for sym in symbols:
            sw = window[window["symbol"] == sym].sort_values("date")
            if len(sw):
                out[sym] = float(sw["close"].iloc[-1])
        return out
    except Exception as exc:
        logger.warning("[weekly] closes read failed (non-fatal): %s", exc)
        return {}


def _active_shelf_ideas() -> list:
    try:
        from core.discovery.shelf import ShelfStore
        return [i for i in ShelfStore().load().ideas if i.status == "active"]
    except Exception as exc:
        logger.warning("[weekly] shelf read failed (non-fatal): %s", exc)
        return []


def _narrate_weekly(review: dict) -> str:
    fallback = _fallback_headline(review)
    started = time.time()
    try:
        from services.clients.llm_client import (
            JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call,
            salvage_truncated_json,
        )
        sb = review["scoreboard"]
        resp = get_llm_client().chat.completions.create(
            model=settings.LLM_MODEL_BULK,
            messages=[{"role": "user", "content": _PROMPT.format(
                allocation="; ".join(f"{a['sector']} {a['weight_pct']:.0f}%"
                                     for a in review["allocation"]) or "empty",
                concentration=", ".join(review["concentration_flags"]) or "none",
                laggards="; ".join(f"{l['symbol']} {l['pnl_pct']:+.1f}%"
                                   for l in review["laggards"]) or "none",
                scoreboard=f"{sb['correct']}/{sb['checked']} judged calls right; "
                           f"counts {sb['counts']}",
            )}],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=300,
            response_format={"type": "json_object"},
            extra_body=JSON_MODE_EXTRA_BODY,
        )
        raw = resp.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            data = salvage_truncated_json(raw)
        if not isinstance(data, dict):
            data = {}
        usage = getattr(resp, "usage", None)
        record_llm_call("weekly_review", settings.LLM_MODEL_BULK,
                        getattr(usage, "prompt_tokens", 0),
                        getattr(usage, "completion_tokens", 0),
                        int((time.time() - started) * 1000), True)
        return str(data.get("headline", "")).strip() or fallback
    except Exception as exc:
        logger.warning("[weekly] narration failed (non-fatal): %s", exc)
        try:
            from services.clients.llm_client import record_llm_call
            record_llm_call(
                "weekly_review", settings.LLM_MODEL_BULK, 0, 0,
                int((time.time() - started) * 1000), False,
            )
        except Exception:
            pass
        return fallback


def _fallback_headline(review: dict) -> str:
    sb = review["scoreboard"]
    parts = []
    if sb["checked"]:
        parts.append(f"Last 4 weeks: {sb['correct']}/{sb['checked']} judged calls right.")
    if review["concentration_flags"]:
        parts.append("Concentration above the comfort band in: "
                     + ", ".join(review["concentration_flags"]) + ".")
    return " ".join(parts) or "Weekly review generated."


def build_weekly_review(
    user_id: str, on: date, store: PortfolioStore | None = None
) -> dict:
    store = store or PortfolioStore(user_id=user_id)
    portfolio = store.load()
    symbols = [h.symbol for h in portfolio.holdings]
    closes = _latest_closes(symbols, on)

    # allocation by sector (market value; cost fallback when no close)
    values: dict[str, float] = {}
    total = 0.0
    for h in portfolio.holdings:
        v = h.adj_qty * closes.get(h.symbol, h.adj_avg_price)
        values[h.sector] = values.get(h.sector, 0.0) + v
        total += v
    allocation = sorted(
        ({"sector": s, "weight_pct": round(v / total * 100.0, 2)}
         for s, v in values.items()),
        key=lambda a: -a["weight_pct"],
    ) if total > 0 else []
    warn = settings.ADVISOR_SECTOR_CONCENTRATION_WARN_PCT
    concentration_flags = [a["sector"] for a in allocation if a["weight_pct"] > warn]

    # laggards: bottom holdings by unrealised P&L (needs a close)
    perf = [
        {"symbol": h.symbol, "sector": h.sector,
         "pnl_pct": round(h.unrealised_pnl_pct(closes[h.symbol]), 2)}
        for h in portfolio.holdings if h.symbol in closes
    ]
    laggards = sorted(perf, key=lambda r: r["pnl_pct"])[:_LAGGARD_COUNT]

    # switch candidates: active shelf ideas in UNDERWEIGHT sectors
    sector_weights = {a["sector"]: a["weight_pct"] for a in allocation}
    max_weight = max(sector_weights.values(), default=0.0)
    switch_candidates = sorted(
        ({"symbol": i.symbol, "sector": i.sector, "conviction": i.conviction}
         for i in _active_shelf_ideas()
         if i.conviction >= settings.DISCOVERY_MIN_CONVICTION
         and sector_weights.get(i.sector, 0.0) < max_weight),
        key=lambda c: -c["conviction"],
    )[:_SWITCH_CANDIDATE_COUNT]

    # advice-ledger scoreboard (deterministic; Phase D owns real outcome RL)
    counts: dict[str, int] = {}
    switch_suggestions: list[dict] = []
    checked = correct = 0
    window_start = (on - timedelta(days=_SCOREBOARD_WINDOW_DAYS)).isoformat()
    for rec in store.load_advice(limit=500):
        if rec.date < window_start or rec.date > on.isoformat():
            continue
        counts[rec.verdict] = counts.get(rec.verdict, 0) + 1
        # SWITCH is an EXIT with a replacement suggestion — surface the
        # advisor's actual pick, not just an anonymous tally (spec §5.2).
        if rec.verdict == "SWITCH" and rec.switch_candidate:
            switch_suggestions.append({
                "symbol": rec.symbol,
                "switch_candidate": rec.switch_candidate,
                "date": rec.date,
            })
        if rec.verdict in ("HOLD",):
            continue
        age_days = (on - date.fromisoformat(rec.date)).days
        if age_days < _SCOREBOARD_MIN_AGE_DAYS:
            continue
        now = closes.get(rec.symbol)
        if now is None or rec.close <= 0:
            continue
        move = now / rec.close - 1.0
        checked += 1
        if (rec.verdict in ("EXIT", "TRIM", "SWITCH") and move < 0) or \
           (rec.verdict == "ADD" and move > 0):
            correct += 1

    review = {
        "date": on.isoformat(),
        "user_id": user_id,
        "kind": "weekly_review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "allocation": allocation,
        "concentration_flags": concentration_flags,
        "risk_profile": portfolio.risk_profile,
        "laggards": laggards,
        "switch_candidates": switch_candidates,
        "switch_suggestions": switch_suggestions,
        "scoreboard": {"counts": counts, "checked": checked, "correct": correct},
        "paper_shelf": [
            {"symbol": i.symbol, "conviction": i.conviction,
             "last_paper_review": getattr(i, "last_paper_review", "")}
            for i in _active_shelf_ideas()
        ],
    }
    review["headline"] = _narrate_weekly(review)
    return review


def render_weekly_text(review: dict) -> str:
    lines = [f"Weekly review — {review['date']}", review.get("headline", ""), ""]
    for a in review.get("allocation", []):
        flag = "  ⚠ over-concentrated" if a["sector"] in review["concentration_flags"] else ""
        lines.append(f"{a['sector']}: {a['weight_pct']:.1f}%{flag}")
    for l in review.get("laggards", []):
        lines.append(f"Laggard: {l['symbol']} {l['pnl_pct']:+.1f}%")
    for c in review.get("switch_candidates", []):
        lines.append(f"Shelf candidate ({c['sector']}): {c['symbol']} "
                     f"conviction {c['conviction']:.2f}")
    for s in review.get("switch_suggestions", []):
        lines.append(f"SWITCH: {s['symbol']} → {s['switch_candidate']}")
    sb = review.get("scoreboard", {})
    if sb.get("checked"):
        lines.append(f"Scoreboard: {sb['correct']}/{sb['checked']} judged calls right")
    return "\n".join(x for x in lines if x != "").strip()


def run_weekly_review(on: date | None = None) -> dict:
    """Scheduler Job 14 / POST /delivery/run-weekly entry point. Never raises."""
    on = on or date.today()
    users = active_user_ids() or [settings.PORTFOLIO_DEFAULT_USER_ID]
    built = 0
    for user_id in users:
        try:
            store = PortfolioStore(user_id=user_id)
            review = build_weekly_review(user_id, on, store=store)
            store.save_weekly(review)
            deliver(f"Weekly review — {on}", render_weekly_text(review),
                    url="/#/inbox/weekly", user_id=user_id)
            built += 1
        except Exception as exc:
            logger.warning("[weekly] build failed for %s (non-fatal): %s", user_id, exc)
    return {"status": "completed", "users": built, "date": on.isoformat()}
