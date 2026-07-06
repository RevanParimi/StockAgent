"""
Compass Phase A — BULK-tier narration of advisor verdicts (spec §5).

The engine decides; the LLM only phrases. Output is labelled research/
analysis, never "advice" (spec §2). Any failure falls back to deterministic
text from the trigger codes — narration must never block the pipeline.
"""
from __future__ import annotations

import json
import logging
import time

from core.config import settings
from backend.shared.schemas.portfolio import AdviceRecord
from core.portfolio.advisor import AdvisorSignals
from services.clients.llm_client import (
    JSON_MODE_EXTRA_BODY,
    get_llm_client,
    record_llm_call,
    salvage_truncated_json,
)

logger = logging.getLogger(__name__)

_TRIGGER_TEXT = {
    "stop_breach": "the position has breached its volatility-scaled stop",
    "thesis_break": "the original thesis is assessed as broken while the forecast points down",
    "shock_reforecast": "a shock re-forecast moved against the position",
    "crisis_regime_bearish": "the regime is MACRO_CRISIS with a bearish envelope",
    "trim_profit_confidence_decline": "profit is extended while envelope confidence is declining",
    "trim_profit_reversion_elevated": "profit is extended while the reversion prior is elevated",
    "add_bullish_healthy": "the envelope is bullish, the regime supportive and recent accuracy healthy",
}

_NOTE_TEXT = {
    "WAIT_FOR_LTCG": "the position crosses the 12-month LTCG boundary soon, so the trim signal is noted rather than acted on",
    "EARNINGS_GAP_PROTECTION": "results are due within days — a profit-protection review is flagged",
    "SECTOR_CONCENTRATION_HIGH": "position weight is above the concentration comfort band",
}

_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-3 sentence research note (NOT financial advice — never use the word
"advice") explaining this deterministic verdict to the portfolio owner.

Verdict: {verdict} on {symbol} at close ₹{close}
Unrealised P&L: {pnl:+.1f}% | Stop level: {stop:.1f}% | Regime: {regime}
Rule triggers: {triggers}
Annotations: {notes}

Respond with JSON: {{"narrative": "<2-3 sentences>"}}"""


def fallback_narrative(rec: AdviceRecord) -> str:
    reasons = [_TRIGGER_TEXT.get(t, t) for t in rec.triggers]
    notes = [_NOTE_TEXT.get(n, n) for n in rec.notes]
    parts = [f"{rec.verdict} — " + ("; ".join(reasons) if reasons else "no rule fired, thesis intact")]
    if notes:
        parts.append("Also: " + "; ".join(notes) + ".")
    return " ".join(parts)


def narrate(rec: AdviceRecord, signals: AdvisorSignals) -> str:
    if not settings.ADVISOR_NARRATE:
        return fallback_narrative(rec)
    started = time.time()
    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL_BULK,
            messages=[{"role": "user", "content": _PROMPT.format(
                verdict=rec.verdict, symbol=rec.symbol, close=rec.close,
                pnl=rec.unrealised_pnl_pct, stop=rec.stop_pct,
                regime=signals.regime_label,
                triggers=", ".join(rec.triggers) or "none",
                notes=", ".join(rec.notes) or "none",
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
        usage = getattr(resp, "usage", None)
        record_llm_call(
            "portfolio_narrator", settings.LLM_MODEL_BULK,
            getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0),
            int((time.time() - started) * 1000), True,
        )
        narrative = str(data.get("narrative", "")).strip()
        return narrative or fallback_narrative(rec)
    except Exception as exc:
        logger.warning("[narrator] narration failed for %s (non-fatal): %s", rec.symbol, exc)
        try:
            record_llm_call(
                "portfolio_narrator", settings.LLM_MODEL_BULK, 0, 0,
                int((time.time() - started) * 1000), False,
            )
        except Exception:
            pass
        return fallback_narrative(rec)
