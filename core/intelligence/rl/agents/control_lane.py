"""
Control lane (the "duel") — Step 10 of run_daily_review.

A bare-LLM predictor that gets exactly the information StockAgent has at the
same moment (yesterday's close + the day's already-fetched market_context)
but none of the architecture (no agents, no learned weights, no lessons, no
dossier). Used to measure StockAgent's edge = agent_accuracy - control_accuracy.

Contract (spec section 2.3): NEVER raises.
  1. Score yesterday's call: find the ControlLog entry with date == review_date
     and correct is None; fill actual_direction + correct.
  2. Predict the next session: one LLM call; append a new ControlPrediction to
     the correct cycle's ControlLog (handling month-boundary rollover).
  3. Any failure (LLM, parse, I/O) is logged and swallowed — the daily review
     is never blocked.

See docs/superpowers/specs/2026-06-12-monthly-scorecard-baseline-duel-design.md
section 2.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date as _date

from backend.shared.schemas.scorecard import ControlPrediction
from core.config.prompts.shared.control_lane import (
    CONTROL_SYSTEM_PROMPT, CONTROL_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

_VALID_DIRECTIONS = {"UP", "DOWN", "FLAT"}


def _strip_think(raw: str) -> str:
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """LLM client pattern mirrors DossierCurator._call_llm."""
    from core.config import settings
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client

    client = get_llm_client()
    model = settings.CONTROL_LANE_MODEL or settings.LLM_MODEL_REASONING
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        max_tokens=300,
        response_format={"type": "json_object"},
        extra_body=JSON_MODE_EXTRA_BODY,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_prompt}],
    )
    return resp.choices[0].message.content or "", model


def run_control_lane_step(
    store, ticker: str, sector: str, review_date: _date,
    actual_close: float, actual_direction: str, market_context: str,
) -> None:
    """Score yesterday's control prediction and make tomorrow's. Never raises.

    Structured as two independent try blocks: scoring failure does not block
    prediction, and vice versa.
    """
    date_str = review_date.isoformat()

    # ------------------------------------------------------------------ #
    # 1. Score yesterday's call (this cycle's ControlLog entry for review_date)
    # ------------------------------------------------------------------ #
    try:
        cycle_id = store.current_cycle_id()
        log = store.load_control_log(cycle_id)
        scored = False
        for entry in log.entries:
            if entry.date == date_str and entry.correct is None:
                entry.actual_direction = actual_direction
                entry.correct = (entry.predicted_direction == actual_direction)
                scored = True
        if scored:
            store.save_control_log(log)
            logger.info("[control_lane] Scored prediction for %s on %s", ticker, date_str)
    except Exception as exc:
        logger.warning("[control_lane] %s: scoring failed for %s (non-fatal): %s",
                        ticker, date_str, exc)

    # ------------------------------------------------------------------ #
    # 2. Predict the next session
    # ------------------------------------------------------------------ #
    try:
        next_day = _next_trading_day(review_date)

        system = CONTROL_SYSTEM_PROMPT.format()
        user = CONTROL_USER_TEMPLATE.format(
            ticker=ticker, sector=sector, last_close=actual_close,
            date=date_str, market_context=(market_context or "")[:3000],
        )
        raw, model = _call_llm(system, user)
        data = json.loads(_strip_think(raw))

        direction = str(data.get("direction", "")).strip().upper()
        if direction not in _VALID_DIRECTIONS:
            logger.warning("[control_lane] %s: invalid direction %r — discarding prediction",
                            ticker, data.get("direction"))
            return

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        predicted_close = data.get("predicted_close")
        if predicted_close is not None:
            try:
                predicted_close = float(predicted_close)
            except (TypeError, ValueError):
                predicted_close = None

        rationale = str(data.get("rationale", ""))[:200]

        prediction = ControlPrediction(
            date=next_day.isoformat(),
            made_on=date_str,
            predicted_direction=direction,
            confidence=confidence,
            predicted_close=predicted_close,
            rationale=rationale,
            model=model,
        )

        # 3. Month-boundary: the prediction may belong to NEXT month's cycle.
        target_cycle_id = f"{store.ticker}_{next_day.year}-{next_day.month:02d}"
        target_log = store.load_control_log(target_cycle_id)
        target_log.entries = [e for e in target_log.entries if e.date != prediction.date]
        target_log.entries.append(prediction)
        target_log.entries.sort(key=lambda e: e.date)
        store.save_control_log(target_log)
        logger.info("[control_lane] Predicted %s for %s (made on %s, model=%s)",
                     prediction.date, ticker, date_str, model)
    except Exception as exc:
        logger.warning("[control_lane] %s: prediction failed for %s (non-fatal): %s",
                        ticker, date_str, exc)


def _next_trading_day(d: _date) -> _date:
    from core.intelligence.rl.nse_calendar import next_trading_day
    return next_trading_day(d)
