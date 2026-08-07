"""Breach rules — the Gap F fix.

ops_alerts catches jobs that produce nothing or crash. It cannot see a job that
produces FULL output that is silently wrong, which is exactly what the
2026-07-30 news-blind incident was. These rules watch for that class: the
system still running, still confident, and no longer right.

Read-only and advisory. A breach notifies a human; nothing here halts autopilot
or overrides advice.
"""
from __future__ import annotations

import logging
from datetime import date

from backend.shared.config.settings.loader import cfg
from core.delivery.alerts import AlertEvent, emit_alerts_broadcast

logger = logging.getLogger(__name__)


def _cfg(key: str, default):
    """Indirection so tests can patch one function instead of the loader."""
    return cfg(key, fallback=default)


def evaluate_breaches(
    report: dict, *, news_blind_rate: float | None = None,
) -> list[dict]:
    """Rules over a built report. Pure apart from cfg reads; never raises."""
    breaches: list[dict] = []

    min_n = int(report.get("min_n") or 30)
    hit60 = (report.get("hit_rate") or {}).get("60") or {}
    floor = float(_cfg("audit.min_hit_rate_60d", 0.45))
    if hit60.get("n", 0) >= min_n and hit60.get("value") is not None \
            and hit60["value"] < floor:
        breaches.append({
            "rule": "min_hit_rate_60d",
            "severity": "warning",
            "message": (
                f"60-trading-day hit-rate vs NIFTY is {hit60['value']:.1%} "
                f"(floor {floor:.0%}) over n={hit60['n']} graded calls."
            ),
        })

    lag_cap = float(_cfg("audit.max_bench_lag_pct", 10.0))
    lag = report.get("portfolio_excess_pct")
    if lag is not None and lag < -abs(lag_cap):
        breaches.append({
            "rule": "max_bench_lag_pct",
            "severity": "warning",
            "message": (
                f"Portfolio trails NIFTY by {abs(lag):.1f}pp over the tracked "
                f"window (cap {lag_cap:.0f}pp)."
            ),
        })

    blind_cap = float(_cfg("audit.max_news_blind_rate", 0.20))
    if news_blind_rate is not None and news_blind_rate > blind_cap:
        breaches.append({
            "rule": "max_news_blind_rate",
            "severity": "warning",
            "message": (
                f"News-blind rate is {news_blind_rate:.0%} (ceiling "
                f"{blind_cap:.0%}) — reviews are running without company news, "
                "which contaminates miss attribution."
            ),
        })

    spread_floor = float(_cfg("audit.conviction_flat_spread", 1.0))
    spread = report.get("conviction_spread")
    if spread is not None and spread < spread_floor:
        breaches.append({
            "rule": "conviction_flat_spread",
            "severity": "info",
            "message": (
                f"Conviction decile spread is {spread:+.2f}pp (floor "
                f"{spread_floor:.2f}pp) — high-conviction shelf ideas are not "
                "outperforming low-conviction ones."
            ),
        })

    return breaches


def emit_breaches(breaches: list[dict]) -> dict:
    """One bundled alert batch. Never raises."""
    if not breaches:
        return {"emitted": 0}
    if not bool(_cfg("audit.alerts_enabled", True)):
        logger.info("[audit] %d breach(es) suppressed — audit.alerts_enabled=false",
                    len(breaches))
        return {"emitted": 0, "suppressed": len(breaches)}
    try:
        today = date.today().isoformat()
        events = [
            AlertEvent(date=today, kind=f"audit_{b['rule']}", symbol="",
                       message=b["message"], severity=b["severity"])
            for b in breaches
        ]
        return emit_alerts_broadcast(events, title="StockAgent verification")
    except Exception as exc:
        logger.warning("[audit] breach emit failed (non-fatal): %s", exc)
        return {"emitted": 0, "error": str(exc)}
