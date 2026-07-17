"""
backend/shared/pipeline/verdict_shadow.py
==========================================
AUD-077 shadow lane (observe-only, decision 2026-07-17).

The RL loop learns per-agent weights, but the final verdict is emitted
free-form by the aggregation LLM — the learned composite reaches it only as
one prompt line, so the weight loop's causal effect on verdicts is unmeasured
(live evidence: SUZLON 0/10 direction accuracy on an 11-day BUY streak).

This module logs what the verdict WOULD be if bound to the learned composite
via settings.SCORE_THRESHOLDS, next to what the LLM actually said. It never
changes behavior. After ~2 weeks of rows, join data/rl/verdict_shadow.jsonl
against the feedback logs to compare the two lanes' direction accuracy —
that comparison decides hard-bind vs keep (and unblocks AUD-098).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.shared.config import settings

logger = logging.getLogger(__name__)

_SHADOW_LOG = Path("data") / "rl" / "verdict_shadow.jsonl"


def verdict_from_composite(composite: float) -> str:
    """Map a [0,1] composite onto settings.SCORE_THRESHOLDS bands.

    Bands are lo-inclusive, checked from the highest lo downward, so band
    edges resolve upward (0.75 -> STRONG BUY). Labels match the LLM's verdict
    vocabulary ("strong_buy" -> "STRONG BUY").
    """
    composite = max(0.0, min(1.0, float(composite)))
    for name, (lo, _hi) in sorted(
        settings.SCORE_THRESHOLDS.items(), key=lambda kv: kv[1][0], reverse=True
    ):
        if composite >= lo:
            return name.replace("_", " ").upper()
    return "STRONG SELL"


def log_verdict_shadow(
    ticker: str,
    composite: float,
    llm_verdict: str,
    llm_final_score: float,
    learned_weights_used: bool,
    shadow_log: str | None = None,
) -> dict | None:
    """Append one shadow record. Observe-only, never raises."""
    try:
        threshold_verdict = verdict_from_composite(composite)
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "composite": round(float(composite), 4),
            "threshold_verdict": threshold_verdict,
            "llm_verdict": llm_verdict,
            "llm_final_score": round(float(llm_final_score), 4),
            "diverged": threshold_verdict != (llm_verdict or "").strip().upper(),
            "learned_weights_used": learned_weights_used,
        }
        path = Path(shadow_log) if shadow_log else _SHADOW_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        logger.info(
            "[verdict_shadow] %s composite=%.3f -> %s | llm=%s (%.3f) | diverged=%s",
            ticker, rec["composite"], threshold_verdict,
            llm_verdict, rec["llm_final_score"], rec["diverged"],
        )
        return rec
    except Exception as exc:
        logger.warning("[verdict_shadow] log failed (non-fatal): %s", exc)
        return None
