"""
core/portfolio/universe.py
==========================
Atlas C4 — nightly Universe recompute (design spec §4).

USER/DATA-plane job: reads atlas.db `user_instruments` (which carries user_id)
and writes only AGGREGATE counts + cadence + status back to `instruments`. The
scheduler/intelligence plane then reads `instruments WHERE enabled=1` exactly as
it reads the JSON file today and never sees a user_id (Learning Constitution R1;
the counts are a *universe-ranking feature*, explicitly permitted by R2 —
SCALING_BLUEPRINTS.md:232 — not a reward signal).

Demand → cadence tiers (BP1): every held ticker is daily; the top-N by demand
fill the rest of the daily budget; watch-only long tail is weekly; refcount-0 is
demoted to on_demand + disabled (history preserved, never hard-deleted). Archive
only a refcount-0 instrument with NO intelligence history, an archivable origin,
and a fully-elapsed grace window.

Dormant behind ATLAS_ENABLED — a no-op until the C11 cutover. Hot-path safe.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings
from backend.shared.config.settings.loader import cfg
from services.data.stores import atlas_store

logger = logging.getLogger(__name__)

_DEFAULT_DEMAND_WEIGHTS = {"holders": 3.0, "watchers": 1.0, "chat_hits_7d": 0.5}
_ARCHIVABLE_ORIGINS = ("watched", "on_demand", "discovery")


def _no_intelligence_history(sym: str) -> bool:
    """True when no `data/predictions/**/<SYM>/` directory exists — nothing has
    ever been learned for this ticker. Conservative on error: assume history
    exists (so a filesystem glitch never archives a learned instrument)."""
    try:
        root = Path(settings.PREDICTION_DATA_DIR)
        if not root.exists():
            return True
        target = sym.upper()
        return not any(d.is_dir() and d.name.upper() == target for d in root.rglob(target))
    except Exception:
        return False


def _days_since(iso: str, now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(iso)).total_seconds() / 86400.0
    except Exception:
        return 0.0


def _emit_ops_alert(message: str) -> None:
    """Budget-governor ops alert (broadcast, non-fatal)."""
    try:
        from core.delivery.alerts import AlertEvent, emit_alerts_broadcast
        emit_alerts_broadcast([AlertEvent(
            date=datetime.now(timezone.utc).date().isoformat(),
            kind="universe_budget", symbol="", message=message, severity="warning",
        )], title="Universe budget governor")
    except Exception as exc:
        logger.warning("[universe] ops alert failed (non-fatal): %s", exc)


def recompute_universe() -> dict:
    """Recompute instruments aggregates + cadence tiers from user_instruments.
    No-op unless ATLAS_ENABLED. Never raises (nightly-lane safe)."""
    if not atlas_store.enabled():
        return {"status": "disabled"}

    weights = cfg("universe.demand_weights", fallback=_DEFAULT_DEMAND_WEIGHTS) \
        or _DEFAULT_DEMAND_WEIGHTS
    w_h = float(weights.get("holders", 3.0))
    w_w = float(weights.get("watchers", 1.0))
    w_c = float(weights.get("chat_hits_7d", 0.5))
    max_daily = int(cfg("universe.max_daily_analyses",
                        env="UNIVERSE_MAX_DAILY_ANALYSES", fallback=25))
    budget_pct = float(cfg("universe.budget_alert_pct", fallback=0.8))
    grace_days = float(cfg("universe.archive_grace_days", fallback=30))
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")

    try:
        conn = atlas_store._get_conn()
        with atlas_store._lock:
            held: dict[str, set] = defaultdict(set)
            watch: dict[str, set] = defaultdict(set)
            for r in conn.execute(
                    "SELECT symbol, relationship, user_id FROM user_instruments").fetchall():
                (held if r["relationship"] == "held" else watch)[r["symbol"]].add(r["user_id"])

            rows = conn.execute(
                "SELECT sym, origin, cadence, enabled, status, holders, watchers,"
                " chat_hits_7d, demand_score, updated_at FROM instruments").fetchall()
            computed = []
            for inst in rows:
                sym = inst["sym"]
                h = len(held.get(sym, ()))
                w = len(watch.get(sym, ()))
                # chat_hits_7d = 0 at M1 (reviewer R4 — no per-symbol chat tap yet)
                demand = round(w_h * h + w_w * w + w_c * 0, 4)
                computed.append({"sym": sym, "h": h, "w": w, "demand": demand, "inst": inst})

            # Daily tier: all held (must-analyze, can exceed the budget → governor),
            # then the highest-demand WATCH-ONLY tickers fill the remaining daily
            # slots — but only once a watch-only ticker is as in-demand as a single
            # holder (demand >= holders weight), so a lone watcher stays weekly
            # rather than consuming a daily slot. The rest of the watched set is the
            # weekly long tail (spec §4 / BP1 cost control).
            daily = {c["sym"] for c in computed if c["h"] > 0}
            remaining = max(0, max_daily - len(daily))
            promote_floor = w_h
            promotable = sorted(
                [c for c in computed
                 if c["h"] == 0 and c["w"] > 0 and c["demand"] >= promote_floor],
                key=lambda c: c["demand"], reverse=True)
            for c in promotable[:remaining]:
                daily.add(c["sym"])

            changed = 0
            for c in computed:
                sym, h, w, inst = c["sym"], c["h"], c["w"], c["inst"]
                refcount = h + w
                if refcount == 0:
                    cadence, enabled = "on_demand", 0            # demote (history preserved)
                elif sym in daily:
                    cadence, enabled = "daily", 1
                elif w > 0:
                    cadence, enabled = "weekly", 1
                else:
                    cadence, enabled = "on_demand", 1

                status = inst["status"]
                if (refcount == 0 and status == "active"
                        and inst["origin"] in _ARCHIVABLE_ORIGINS
                        and _no_intelligence_history(sym)
                        and _days_since(inst["updated_at"], now) >= grace_days):
                    status = "archived"

                new = (h, w, 0, c["demand"], cadence, enabled, status)
                cur = (inst["holders"], inst["watchers"], inst["chat_hits_7d"],
                       round(inst["demand_score"], 4), inst["cadence"],
                       inst["enabled"], inst["status"])
                if new != cur:                                   # keep updated_at = last real change
                    conn.execute(
                        "UPDATE instruments SET holders=?, watchers=?, chat_hits_7d=?,"
                        " demand_score=?, cadence=?, enabled=?, status=?, updated_at=?"
                        " WHERE sym=?",
                        (h, w, 0, c["demand"], cadence, enabled, status, now_iso, sym))
                    changed += 1
            conn.commit()

        daily_count = len(daily)
        if max_daily > 0 and daily_count >= budget_pct * max_daily:
            _emit_ops_alert(
                f"Daily-analysis universe at {daily_count}/{max_daily} "
                f"(>={int(budget_pct * 100)}% of budget). Held-ticker growth is "
                "outpacing the analysis budget — review universe.max_daily_analyses.")
        return {"status": "ok", "instruments": len(computed),
                "daily": daily_count, "changed": changed}
    except Exception as exc:
        logger.warning("[universe] recompute failed (non-fatal): %s", exc)
        return {"status": "error", "error": str(exc)}
