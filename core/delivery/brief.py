"""
Compass Phase C — Morning Brief (spec §7): 08:50 IST, right after the 08:45
pre-open shock check. Deterministic assembly from existing artifacts; ONE
BULK-tier narration call for the headline (fallback text on any failure).
Research tone, never "advice" (spec §2).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

from core.config import settings
from core.delivery.alerts import AlertEvent, emit_alerts
from core.delivery.channels import deliver
from core.discovery.ipo_tracker import upcoming_lockin_alerts
from core.intelligence.rl.nse_calendar import is_trading_day
from core.portfolio.store import PortfolioStore, active_user_ids
from services.data.fetchers.corporate_events import (
    load_events_calendar,
    next_results_event,
)
from services.data.fetchers.ipo import load_ipo_cache

logger = logging.getLogger(__name__)

_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-4 sentence morning headline (research tone; NEVER the word "advice")
summarising the portfolio state and what matters today.

Portfolio: {portfolio}
Escalations flagged yesterday: {escalations}
Market regime: {regime}
Overnight HIGH-severity items: {overnight}
Earnings within 3 sessions: {earnings}
New discovery-shelf ideas: {adds}

Respond with JSON: {{"headline": "<2-4 sentences>"}}"""


# -- section collectors (each non-fatal, monkeypatchable) -------------------

def _read_regime() -> dict | None:
    try:
        path = Path(settings.PREDICTION_DATA_DIR) / "_regime_state.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return {"label": raw.get("label", "NORMAL"),
                    "calm_streak": raw.get("calm_streak", 0)}
    except Exception as exc:
        logger.warning("[brief] regime read failed (non-fatal): %s", exc)
    return None


def _overnight_items(max_items: int = 3) -> list[dict]:
    try:
        from services.background.macro_news_cache import MacroNewsCache
        # Cache entries carry "title" (macro_news_cache schema), not "headline".
        items = [i for i in MacroNewsCache().get_high_severity(hours_back=24)
                 if i.get("title")][:max_items]
        return [{"headline": i["title"], "severity": i.get("severity", "HIGH")}
                for i in items]
    except Exception as exc:
        logger.warning("[brief] macro feed read failed (non-fatal): %s", exc)
        return []


def _shelf_events_since(since_iso: str) -> list[dict]:
    try:
        path = Path(settings.DISCOVERY_DATA_DIR) / "shelf_events.jsonl"
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines()[-200:]:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("ts", "") >= since_iso and rec.get("event") in ("added", "promoted"):
                out.append({"event": rec["event"], "symbol": rec.get("symbol", ""),
                            "detail": rec.get("detail", "")})
        return out[-5:]
    except Exception as exc:
        logger.warning("[brief] shelf events read failed (non-fatal): %s", exc)
        return []


def _earnings_soon(symbols: list[str], on: date) -> list[dict]:
    try:
        calendar = load_events_calendar()
        out = []
        for sym in symbols:
            ev = next_results_event(sym, on, calendar)
            if ev is not None and (date.fromisoformat(ev.date) - on).days <= 3:
                out.append({"symbol": sym, "date": ev.date})
        return out
    except Exception as exc:
        logger.warning("[brief] earnings scan failed (non-fatal): %s", exc)
        return []


def _ipo_watch(max_items: int = 3) -> list[dict]:
    try:
        cache = load_ipo_cache()
        rows = cache.get("current", []) + cache.get("upcoming", [])
        return [{"symbol": r.get("symbol", ""), "company": r.get("company", ""),
                 "status": r.get("status", "")} for r in rows[:max_items]]
    except Exception as exc:
        logger.warning("[brief] ipo watch failed (non-fatal): %s", exc)
        return []


def _narrate_brief(brief: dict) -> str:
    """ONE BULK call; deterministic fallback (mirror narrator.py)."""
    fallback = _fallback_headline(brief)
    started = time.time()
    try:
        from services.clients.llm_client import (
            JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call,
            salvage_truncated_json,
        )
        p = brief.get("portfolio") or {}
        resp = get_llm_client().chat.completions.create(
            model=settings.LLM_MODEL_BULK,
            messages=[{"role": "user", "content": _PROMPT.format(
                portfolio=(f"value ₹{p.get('portfolio_value', 0):,.0f} "
                           f"({p.get('total_pnl_pct', 0.0):+.1f}%)") if p else "empty",
                escalations=", ".join(f["symbol"] for f in brief["advisor_flags"]) or "none",
                regime=(brief.get("regime") or {}).get("label", "unknown"),
                overnight="; ".join(i["headline"] for i in brief["overnight"]) or "none",
                earnings=", ".join(f"{e['symbol']} {e['date']}"
                                   for e in brief["earnings_soon"]) or "none",
                adds=", ".join(a["symbol"] for a in brief["discovery_adds"]) or "none",
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
        record_llm_call("morning_brief", settings.LLM_MODEL_BULK,
                        getattr(usage, "prompt_tokens", 0),
                        getattr(usage, "completion_tokens", 0),
                        int((time.time() - started) * 1000), True)
        return str(data.get("headline", "")).strip() or fallback
    except Exception as exc:
        logger.warning("[brief] narration failed (non-fatal): %s", exc)
        try:
            from services.clients.llm_client import record_llm_call
            record_llm_call(
                "morning_brief", settings.LLM_MODEL_BULK, 0, 0,
                int((time.time() - started) * 1000), False,
            )
        except Exception:
            pass
        return fallback


def _fallback_headline(brief: dict) -> str:
    p = brief.get("portfolio") or {}
    parts = []
    if p:
        parts.append(f"Portfolio ₹{p.get('portfolio_value', 0):,.0f} "
                     f"({p.get('total_pnl_pct', 0.0):+.1f}% overall).")
    esc = [f["symbol"] for f in brief.get("advisor_flags", [])]
    if esc:
        parts.append(f"Flags to review: {', '.join(esc)}.")
    regime = (brief.get("regime") or {}).get("label")
    if regime and regime != "NORMAL":
        parts.append(f"Regime: {regime}.")
    return " ".join(parts) or "No portfolio activity to report."


# -- builder + renderer + runner --------------------------------------------

def build_morning_brief(
    user_id: str, on: date, store: PortfolioStore | None = None
) -> dict:
    store = store or PortfolioStore(user_id=user_id)
    digest = store.load_latest_digest()
    portfolio = None
    advisor_flags: list[dict] = []
    held: list[str] = []
    if digest:
        portfolio = {k: digest.get(k) for k in
                     ("date", "portfolio_value", "total_pnl_pct", "escalations")}
        portfolio["portfolio_value"] = digest.get("portfolio_value", 0.0)
        held = [r["symbol"] for r in digest.get("holdings", [])]
        advisor_flags = [
            {"symbol": r["symbol"], "verdict": r["verdict"],
             "reason": r.get("reason", ""), "notes": r.get("notes", [])}
            for r in digest.get("holdings", [])
            if r.get("verdict") not in ("HOLD", "NO_DATA")
        ]

    prev = store.load_latest_brief()
    since = prev.get("generated_at", "") if prev else ""

    # Lock-in flags cover held + watchlist + active shelf names (spec §7:
    # "lock-in expiry on shelf name").
    watched: set[str] = set(held)
    try:
        watched |= {w.symbol for w in store.load().watchlist}
    except Exception:
        pass
    try:
        from core.discovery.shelf import ShelfStore
        watched |= {i.symbol for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception as exc:
        logger.debug("[brief] shelf read for lock-in scan failed (non-fatal): %s", exc)

    brief = {
        "date": on.isoformat(),
        "user_id": user_id,
        "kind": "morning_brief",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": portfolio,
        "advisor_flags": advisor_flags,
        "regime": _read_regime(),
        "overnight": _overnight_items(),
        "earnings_soon": _earnings_soon(held, on),
        "discovery_adds": _shelf_events_since(since),
        "ipo_watch": _ipo_watch(),
        "lockin_flags": [
            e.model_dump() for e in upcoming_lockin_alerts(on, symbols=watched or None)
        ],
    }
    brief["headline"] = _narrate_brief(brief)
    return brief


def render_brief_text(brief: dict) -> str:
    lines = [f"Morning brief — {brief['date']}", brief.get("headline", ""), ""]
    p = brief.get("portfolio")
    if p:
        lines.append(f"Portfolio ₹{p.get('portfolio_value', 0):,.0f} "
                     f"({p.get('total_pnl_pct', 0.0):+.1f}%)")
    for f in brief.get("advisor_flags", []):
        lines.append(f"{f['symbol']}: {f['verdict']} — {f['reason']}")
    regime = (brief.get("regime") or {}).get("label")
    if regime:
        lines.append(f"Regime: {regime}")
    for i in brief.get("overnight", []):
        lines.append(f"Overnight: {i['headline']}")
    for e in brief.get("earnings_soon", []):
        lines.append(f"Earnings soon: {e['symbol']} on {e['date']}")
    for a in brief.get("discovery_adds", []):
        lines.append(f"Shelf {a['event']}: {a['symbol']} {a.get('detail', '')}")
    for w in brief.get("ipo_watch", []):
        lines.append(f"IPO {w['status']}: {w['symbol']} {w['company']}")
    for lf in brief.get("lockin_flags", []):
        lines.append(f"Lock-in expiry: {lf['symbol']} {lf['kind']} on {lf['expiry']}")
    return "\n".join(x for x in lines if x != "").strip()


def run_morning_brief(on: date | None = None) -> dict:
    """Scheduler Job 13 / POST /delivery/run-brief entry point. Never raises."""
    on = on or date.today()
    if not is_trading_day(on):
        return {"status": "not_trading_day"}
    users = active_user_ids() or [settings.PORTFOLIO_DEFAULT_USER_ID]
    built = 0
    for user_id in users:
        try:
            store = PortfolioStore(user_id=user_id)
            brief = build_morning_brief(user_id, on, store=store)
            store.save_brief(brief)
            deliver(f"Morning brief — {on}", render_brief_text(brief),
                    url="/#/inbox/brief", user_id=user_id)
            if brief["lockin_flags"]:
                emit_alerts(
                    [AlertEvent(date=on.isoformat(), kind="lockin_expiry",
                                symbol=lf["symbol"],
                                message=f"{lf['kind']} lock-in expires {lf['expiry']} "
                                        "— supply risk, not a signal",
                                severity="warning")
                     for lf in brief["lockin_flags"]],
                    user_id=user_id, title=f"Lock-in expiries — {on}",
                )
            built += 1
        except Exception as exc:
            logger.warning("[brief] build failed for %s (non-fatal): %s", user_id, exc)
    return {"status": "completed", "users": built, "date": on.isoformat()}
