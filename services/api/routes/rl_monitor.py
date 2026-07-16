"""
services/api/routes/rl_monitor.py
=================================
Real backing for the RL Monitor page (AUD-100). Five read-only adapters over
PredictionStore matching the shapes rl-data.jsx already consumes. No auth:
read-only GETs, same posture as the other /ui reads (Wave B gates writes only).

Tickers are validated against the managed list BEFORE any PredictionStore is
constructed — the store mkdirs on init (AUD-024 class), so unknown symbols 404
without touching the filesystem.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ui/rl", tags=["RL Monitor"])

# Test seam: overrides PredictionStore base_dir when set (None in prod).
_BASE_DIR_OVERRIDE: str | None = None

_CHIP_COLORS = ["#0891b2", "#7c3aed", "#16a34a", "#d97706", "#dc2626",
                "#0ea5e9", "#db2777", "#65a30d", "#9333ea", "#ea580c",
                "#0d9488", "#4f46e5", "#ca8a04", "#e11d48", "#059669", "#6d28d9"]


def _managed() -> list[dict]:
    """[{'sym','sector'}] for all managed tickers (scheduler source of truth)."""
    from services.api.routes.scheduler_api import _resolve_tickers
    return _resolve_tickers(None)


def _entry_for(ticker: str) -> dict:
    sym = ticker.strip().upper()
    for e in _managed():
        if e["sym"] == sym:
            return e
    raise HTTPException(status_code=404, detail="unknown ticker")


def _store(entry: dict):
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    return PredictionStore(entry["sym"], sector=entry.get("sector", "automobile"),
                           base_dir=_BASE_DIR_OVERRIDE)


def _all_entries(store) -> list:
    entries = []
    for cycle_id in store.list_cycles():
        fb = store.load_feedback_log(cycle_id)
        if fb and fb.entries:
            entries.extend(fb.entries)
    entries.sort(key=lambda e: e.date)
    return entries


@router.get("/tickers", summary="Managed tickers with RL data flags")
async def rl_tickers() -> dict:
    out = []
    for i, e in enumerate(_managed()):
        row = {"sym": e["sym"], "name": e.get("name", e["sym"]),
               "color": _CHIP_COLORS[i % len(_CHIP_COLORS)],
               "enabled": bool(e.get("enabled", True)),
               "has_envelope": False, "has_weights": False}
        try:
            store = _store(e)
            row["has_envelope"] = store.load_envelope(store.current_cycle_id()) is not None
            wm = store.load_weight_memory()
            row["has_weights"] = bool(wm and wm.weight_version > 0)
        except Exception as exc:
            logger.debug("[rl_monitor] tickers flags failed for %s: %s", e["sym"], exc)
        out.append(row)
    return {"tickers": out}


@router.get("/summary/{ticker}", summary="RL summary card data for a ticker")
async def rl_summary(ticker: str) -> dict:
    e = _entry_for(ticker)
    store = _store(e)
    env = store.load_envelope(store.current_cycle_id())
    entries = _all_entries(store)
    if not entries and env is None:
        return {"available": False, "ticker": e["sym"]}
    wm = store.load_weight_memory()
    ledger = store.load_learning_ledger()
    hits = sum(1 for x in entries if x.direction_correct)
    total = len(entries)
    miss_counter = (ledger.miss_counter or {}) if ledger else {}
    streak = env.conviction_streak if env else None
    return {
        "available": True,
        "ticker": e["sym"],
        "cycle_id": store.current_cycle_id(),
        "direction_accuracy_pct": round(hits / total * 100, 1) if total else 0.0,
        "total_entries": total,
        "total_days": total,
        "direction_hits": hits,
        "avg_price_error_pct": round(
            sum(abs(x.price_error_pct) for x in entries) / total, 2) if total else 0.0,
        "weight_version": wm.weight_version if wm else 0,
        "lesson_count": len(ledger.lessons) if ledger else 0,
        "top_miss_factor": max(miss_counter, key=miss_counter.get) if miss_counter else "",
        "current_verdict": streak.current_verdict if streak else "",
        "streak_days": streak.streak_days if streak else 0,
        "reversion_prior": streak.reversion_prior if streak else 0.0,
    }


@router.get("/predictions/{ticker}", summary="Per-day predicted vs actual rows")
async def rl_predictions(ticker: str, limit: int = 30) -> dict:
    e = _entry_for(ticker)
    store = _store(e)
    entries = _all_entries(store)
    if not entries:
        return {"available": False, "ticker": e["sym"], "days": []}
    env = store.load_envelope(store.current_cycle_id())

    def _confidence(d: str) -> float:
        f = env.get_forecast(d) if env else None
        return f.confidence if f else 0.5

    days = [{
        "date": x.date,
        "predicted": round(x.predicted_close, 2),
        "actual": round(x.actual_close, 2),
        "error_pct": round(abs(x.price_error_pct), 2),
        "direction_hit": x.direction_correct,
        "confidence": _confidence(x.date),
        "miss_type": (str(x.miss_analysis.miss_type)
                      if x.miss_analysis and x.miss_analysis.miss_type else None),
    } for x in entries[-limit:]]
    return {"available": True, "ticker": e["sym"], "days": days}


@router.get("/weights/{ticker}", summary="Agent weight state + history")
async def rl_weights(ticker: str) -> dict:
    e = _entry_for(ticker)
    wm = _store(e).load_weight_memory()
    if not wm:
        return {"available": False, "ticker": e["sym"]}
    return {
        "available": True,
        "ticker": e["sym"],
        "base_weights": dict(wm.base_weights or {}),
        "current_weights": dict(wm.current_weights or {}),
        "weight_history": [
            {"version": h.version, "date": h.date, "reason": h.reason,
             "weights": dict(h.weights)}
            for h in sorted(wm.weight_history or [], key=lambda h: h.date)
        ],
    }


@router.get("/misses/{ticker}", summary="Miss attribution counts")
async def rl_misses(ticker: str) -> dict:
    e = _entry_for(ticker)
    store = _store(e)
    entries = _all_entries(store)
    ledger = store.load_learning_ledger()
    if not entries and not (ledger and ledger.lessons):
        return {"available": False, "ticker": e["sym"]}
    miss_type_counts: dict[str, int] = {}
    for x in entries:
        if x.miss_analysis and x.miss_analysis.miss_type:
            mt = str(x.miss_analysis.miss_type)
            miss_type_counts[mt] = miss_type_counts.get(mt, 0) + 1
    miss_counter = (ledger.miss_counter or {}) if ledger else {}
    top = dict(sorted(miss_counter.items(), key=lambda kv: -kv[1])[:5])
    return {
        "available": True,
        "ticker": e["sym"],
        "miss_type_counts": miss_type_counts,
        "top_missed_factors": top,
        "lesson_count": len(ledger.lessons) if ledger else 0,
    }
