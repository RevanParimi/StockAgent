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


def _cfg_int(key: str, default: int) -> int:
    """Indirection so tests patch one function, not the loader."""
    try:
        return int(cfg(key, fallback=default))
    except Exception:
        return default


def _switch_block(rows: list, horizon: int, min_n: int,
                  decision: str | None = None) -> dict:
    """One switch block. `decision` filters to taken-only when given.

    Every claim here rests on the STRIDED subsample: daily capture of one pair
    yields many rows and almost no extra information, so raw `n` is reported
    for transparency and never used as the basis of a verdict.
    """
    from core.audit.metrics import mean_edge, stride_subsample

    lane = [r for r in rows if r.lane == "switch"
            and (decision is None
                 or (r.triggers and r.triggers[0] == decision))]
    strided = stride_subsample(lane, horizon)
    rate = hit_rate(strided, horizon=horizon)
    p = coin_flip_p(strided, horizon=horizon)
    edge = mean_edge(strided, horizon=horizon)
    return {
        "n": len([r for r in lane if r.horizon_td == horizon]),
        "n_effective": rate.n,
        "horizon_td": horizon,
        "hit_rate": _rate_dict(rate),
        "mean_edge_pct": edge,
        "coin_flip_p": p,
        # Switch-lane rows ONLY: per_trigger_precision filters on
        # `correct is not None` and nothing else, so passing the whole store
        # would blend advisor trigger codes with switch reason codes.
        "per_reason": {t: _rate_dict(r) for t, r
                       in per_trigger_precision(strided, horizon=horizon).items()},
        "verdict": classify(rate, p, edge, min_n),
        # The rule, not the advice delivered — see the design's section 7.
        "measures": ("the decision rule over every pair it evaluated, "
                     "not the advice the user was shown"),
    }


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

    from core.audit.attribution import attribution_distribution
    from core.audit.evidence import news_availability_index

    switch_horizon = _cfg_int("audit.switch_horizon_td", 10)
    switch_min_n = _cfg_int("audit.switch_min_n", 30)
    headline_horizon = 60
    headline = hit_rate(rows, horizon=headline_horizon)
    p = coin_flip_p(rows, horizon=headline_horizon)
    excess_60 = mean_excess(rows, horizon=headline_horizon)
    buckets = conviction_calibration(
        rows, horizon=_cfg_int("audit.conviction_horizon_td", 10))

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
        # Was hardcoded to 60td while conviction_calibration used 30td, so on
        # real data both blocks rendered empty. Configurable, defaulting to the
        # shortest horizon (first to accumulate rows); a FIXED default is
        # chosen over auto-detecting "the horizon with rows" so the metric
        # stays comparable with itself over time.
        "per_trigger": {t: _rate_dict(r) for t, r in per_trigger_precision(
            rows, horizon=_cfg_int("audit.per_trigger_horizon_td", 10)).items()},
        "conviction_calibration": buckets,
        "conviction_spread": calibration_spread(buckets),
        # Switch validation (design 2026-08-20). Two blocks on purpose:
        # switch_rule covers every pair the advisor EVALUATED, most of which
        # were never shown to the user; switch_taken is the much smaller set
        # that actually became advice. Conflating them would let a future
        # reader take a rule-level hit-rate as "the switches I was given".
        "switch_rule": _switch_block(rows, switch_horizon, switch_min_n),
        "switch_taken": _switch_block(rows, switch_horizon, switch_min_n,
                                      decision="taken"),
        "attribution": attribution_distribution(
            [r for r in rows if r.lane == "switch"],
            news_index=news_availability_index()),
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
    sw = report.get("switch_rule") or {}
    if sw:
        lines.append(
            f"Switch RULE ({sw.get('horizon_td')}td): {sw.get('verdict')} — "
            f"{sw.get('n_effective')} independent pair(s) "
            f"from {sw.get('n')} raw rows.")
        # Said here, every time, because it is the one thing about this block
        # a later reader will otherwise get wrong.
        lines.append("  Measures the decision rule over every pair it evaluated,")
        lines.append("  NOT the advice you were shown — see switch_taken for that.")
        lines.append("")
    return "\n".join(lines)
