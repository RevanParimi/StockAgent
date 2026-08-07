"""Report assembly — metrics into one verdict word and one shared payload.

The verdict vocabulary deliberately mirrors the Learning Evidence report's, so
two auditors never use the same word for different things.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.shared.config.settings.loader import cfg
from core.audit.metrics import (
    Rate, calibration_spread, coin_flip_p, conviction_calibration, hit_rate,
    mean_excess, per_trigger_precision,
)

logger = logging.getLogger(__name__)

VERDICTS = ("INSUFFICIENT_DATA", "BELOW_COIN_FLIP", "UNPROVEN", "BEATS_BENCHMARK")

# Two-sided significance level for the coin-flip call — matches
# learning_evidence.SIGNIFICANCE_LEVEL so the two reports agree.
SIGNIFICANCE_LEVEL = 0.10

_HORIZONS = (10, 30, 60)


def _rate_dict(r: Rate) -> dict:
    return {"n": r.n, "value": r.value, "lo": r.lo, "hi": r.hi}


def classify(
    rate: Rate, p_value: float | None, mean_excess_pct: float | None, min_n: int,
) -> str:
    """The single word. Conservative by construction: anything unclear is
    UNPROVEN, and anything thin is INSUFFICIENT_DATA."""
    if rate.n < min_n or rate.value is None or p_value is None:
        return "INSUFFICIENT_DATA"
    if p_value <= SIGNIFICANCE_LEVEL and rate.value < 0.5:
        return "BELOW_COIN_FLIP"
    if p_value <= SIGNIFICANCE_LEVEL and rate.value > 0.5 \
            and (mean_excess_pct or 0.0) > 0.0:
        return "BEATS_BENCHMARK"
    return "UNPROVEN"


def build_report(user_id: str | None = None, *, store=None, min_n: int | None = None) -> dict:
    """The payload every surface shares: nightly alerts, monthly email, API."""
    from core.audit.store import AuditOutcomeStore

    store = store or AuditOutcomeStore(user_id=user_id)
    rows = store.load_all()
    floor = int(min_n if min_n is not None else cfg("audit.min_n", fallback=30))

    headline_horizon = 60
    headline = hit_rate(rows, horizon=headline_horizon)
    p = coin_flip_p(rows, horizon=headline_horizon)
    excess_60 = mean_excess(rows, horizon=headline_horizon)
    buckets = conviction_calibration(rows, horizon=30)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": store.user_id,
        "total_rows": len(rows),
        "min_n": floor,
        "headline_horizon_td": headline_horizon,
        "verdict": classify(headline, p, excess_60, floor),
        "coin_flip_p": p,
        "hit_rate": {str(h): _rate_dict(hit_rate(rows, horizon=h)) for h in _HORIZONS},
        "mean_excess_pct": {str(h): mean_excess(rows, horizon=h) for h in _HORIZONS},
        "per_trigger": {t: _rate_dict(r)
                        for t, r in per_trigger_precision(rows, horizon=headline_horizon).items()},
        "conviction_calibration": buckets,
        "conviction_spread": calibration_spread(buckets),
    }


def render_section(report: dict) -> str:
    """Plain-text block for the monthly Learning Evidence email."""
    lines = [
        "",
        "=" * 62,
        "Advice outcomes — verification layer",
        "=" * 62,
        f"Verdict: {report['verdict']}   "
        f"(n={report['total_rows']} rows, floor={report['min_n']})",
        "",
        "Hit-rate vs NIFTY 50, by horizon:",
    ]
    for horizon in ("10", "30", "60"):
        r = report["hit_rate"].get(horizon, {})
        if not r.get("n"):
            lines.append(f"  {horizon:>3}td   no matured rows yet")
            continue
        lines.append(
            f"  {horizon:>3}td   {r['value']:.1%}  "
            f"[{r['lo']:.1%}–{r['hi']:.1%}]   n={r['n']}"
        )
    lines.append("")
    if report["per_trigger"]:
        lines.append("Per-trigger precision (60td):")
        for trigger, r in report["per_trigger"].items():
            lines.append(f"  {trigger:<24} {r['value']:.1%}  n={r['n']}")
        lines.append("")
    spread = report.get("conviction_spread")
    if spread is None:
        lines.append("Conviction calibration: not enough populated buckets yet.")
    else:
        lines.append(
            f"Conviction calibration: top-minus-bottom decile spread "
            f"{spread:+.2f}pp (flat ⇒ conviction carries no information)."
        )
    lines.append("")
    return "\n".join(lines)
