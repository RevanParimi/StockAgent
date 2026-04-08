"""
agents/feedback_agent.py
========================
The 6th agent in the Automobile Agent system.

Unlike the 5 sub-agents, FeedbackAgent does NOT subclass BaseAgent because its
inputs are structured feedback data rather than a StockQuery.

Responsibilities each trading day:
  1. Receive predicted vs actual values + market context
  2. Call LLM to produce a structured miss analysis
  3. Extract new lessons for the LearningLedger
  4. Return a FeedbackAgentOutput ready for WeightAdapter consumption

Usage (called by scripts/daily_review.py):
    agent = FeedbackAgent()
    output = agent.run(fb_input, ledger)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

from groq import Groq, APIError, APITimeoutError, RateLimitError

from config import settings
from models.feedback_schemas import (
    FeedbackAgentInput,
    FeedbackAgentOutput,
    LearningLedger,
    Lesson,
    MissAnalysis,
    RawLesson,
)
from prompts.feedback_agent import SYSTEM_PROMPT, format_feedback_prompt

logger = logging.getLogger(__name__)

# Price change threshold to classify direction as FLAT (±0.3%)
FLAT_THRESHOLD_PCT = 0.3


def classify_direction(actual: float, predicted: float) -> str:
    """Return 'UP', 'DOWN', or 'FLAT' based on actual vs predicted close."""
    if predicted == 0:
        return "FLAT"
    change_pct = (actual - predicted) / predicted * 100
    if change_pct > FLAT_THRESHOLD_PCT:
        return "UP"
    if change_pct < -FLAT_THRESHOLD_PCT:
        return "DOWN"
    return "FLAT"


def is_direction_correct(predicted_verdict: str, actual_direction: str) -> bool:
    """
    True if the verdict's implied direction aligns with the actual price move.
    BUY / STRONG BUY → expects UP
    SELL / STRONG SELL → expects DOWN
    NEUTRAL → any direction is treated as 'not wrong'
    """
    bullish = {"BUY", "STRONG BUY"}
    bearish = {"SELL", "STRONG SELL"}
    verdict_upper = predicted_verdict.upper()
    if verdict_upper in bullish:
        return actual_direction == "UP"
    if verdict_upper in bearish:
        return actual_direction == "DOWN"
    return True  # NEUTRAL — no directional claim


class FeedbackAgent:
    """
    Analyses daily prediction misses and generates stock-specific lessons.

    Not a subclass of BaseAgent — has a different run() signature.
    """

    def __init__(self) -> None:
        self._client = Groq(
            api_key=settings.GROQ_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(
        self,
        fb_input: FeedbackAgentInput,
        ledger: LearningLedger,
    ) -> FeedbackAgentOutput:
        """
        Run one daily feedback analysis cycle.

        Parameters
        ----------
        fb_input : FeedbackAgentInput
            All numeric and contextual inputs for this day's review.
        ledger : LearningLedger
            Current ledger so the LLM knows what patterns are already known.

        Returns
        -------
        FeedbackAgentOutput
            Structured miss analysis + new raw lessons.
        """
        logger.info(
            "[FeedbackAgent] Analysing %s on %s | error=%.2f%% | direction_correct=%s",
            fb_input.ticker,
            fb_input.date,
            fb_input.price_error_pct,
            fb_input.direction_correct,
        )

        user_prompt = format_feedback_prompt(
            ticker=fb_input.ticker,
            date=fb_input.date,
            predicted_close=fb_input.predicted_close,
            actual_close=fb_input.actual_close,
            price_error_pct=fb_input.price_error_pct,
            direction_correct=fb_input.direction_correct,
            predicted_agent_scores=fb_input.predicted_agent_scores,
            todays_agent_scores=fb_input.todays_agent_scores,
            market_context_today=fb_input.market_context_today,
            key_assumptions_made=fb_input.key_assumptions_made,
            active_lessons_summary=ledger.active_lessons_summary(),
        )

        raw = self._call_llm(SYSTEM_PROMPT, user_prompt)
        output = self._parse(raw, fb_input)

        logger.info(
            "[FeedbackAgent] Done – primary_miss=%s, new_lessons=%d",
            output.primary_miss_agent,
            len(output.new_lessons),
        )
        return output

    # ------------------------------------------------------------------
    # LLM call with retry
    # ------------------------------------------------------------------

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        delay = settings.RETRY_DELAY_SECONDS
        last_error: Exception | None = None

        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    temperature=0.1,   # low temperature for analytical consistency
                    max_tokens=1024,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content or "{}"

            except RateLimitError as e:
                logger.warning("[FeedbackAgent] Rate limit (attempt %d/%d)", attempt, settings.MAX_RETRIES)
                last_error = e
                time.sleep(delay)
                delay *= 2

            except APITimeoutError as e:
                logger.warning("[FeedbackAgent] Timeout (attempt %d/%d)", attempt, settings.MAX_RETRIES)
                last_error = e
                time.sleep(delay)

            except APIError as e:
                logger.error("[FeedbackAgent] API error: %s", e)
                last_error = e
                break

        raise RuntimeError(f"[FeedbackAgent] LLM call failed: {last_error}")

    # ------------------------------------------------------------------
    # Parse LLM JSON → FeedbackAgentOutput
    # ------------------------------------------------------------------

    def _parse(self, raw: str, fb_input: FeedbackAgentInput) -> FeedbackAgentOutput:
        try:
            data = json.loads(raw)
            raw_lessons = [
                RawLesson(
                    category=item.get("category", "macro"),
                    pattern=item.get("pattern", "unknown"),
                    observation=item.get("observation", ""),
                    rule=item.get("rule", ""),
                    confidence=float(item.get("confidence", 0.5)),
                )
                for item in data.get("new_lessons", [])
            ]
            return FeedbackAgentOutput(
                primary_miss_agent=data.get("primary_miss_agent", "unknown"),
                missed_factors=data.get("missed_factors", []),
                over_weighted_factors=data.get("over_weighted_factors", []),
                agent_score_drift=data.get("agent_score_drift", {}),
                new_lessons=raw_lessons,
                revised_context_for_remaining_days=data.get(
                    "revised_context_for_remaining_days", ""
                ),
            )
        except Exception as exc:
            logger.error("[FeedbackAgent] Parse error: %s | Raw: %s", exc, raw[:400])
            # Return a minimal safe output so the pipeline doesn't crash
            return FeedbackAgentOutput(
                primary_miss_agent="unknown",
                missed_factors=[f"Parse error: {exc}"],
            )

    # ------------------------------------------------------------------
    # Ledger integration: merge raw lessons into LearningLedger
    # ------------------------------------------------------------------

    def merge_lessons_into_ledger(
        self,
        output: FeedbackAgentOutput,
        ledger: LearningLedger,
    ) -> tuple[LearningLedger, list[str]]:
        """
        Merge new lessons from a FeedbackAgentOutput into the LearningLedger.

        - If a lesson with the same pattern already exists → increment occurrences
          and update confidence (weighted average).
        - Otherwise → add as a new lesson.

        Returns
        -------
        (updated_ledger, list_of_lesson_ids_touched)
        """
        lesson_ids: list[str] = []

        for raw in output.new_lessons:
            existing = ledger.find_by_pattern(raw.pattern)
            if existing is not None:
                # Update existing: bump occurrences, blend confidence
                existing.occurrences += 1
                existing.confidence = round(
                    (existing.confidence * (existing.occurrences - 1) + raw.confidence)
                    / existing.occurrences,
                    4,
                )
                lesson_ids.append(existing.lesson_id)
                logger.info(
                    "[FeedbackAgent] Updated lesson %s (pattern=%s, occurrences=%d)",
                    existing.lesson_id, existing.pattern, existing.occurrences,
                )
            else:
                new_id = ledger.next_lesson_id()
                lesson = Lesson(
                    lesson_id=new_id,
                    date_learned=date.today().isoformat(),
                    category=raw.category,
                    pattern=raw.pattern,
                    observation=raw.observation,
                    rule=raw.rule,
                    confidence=raw.confidence,
                    occurrences=1,
                    still_valid=True,
                )
                ledger.lessons.append(lesson)
                lesson_ids.append(new_id)
                logger.info(
                    "[FeedbackAgent] Added new lesson %s (pattern=%s)",
                    new_id, raw.pattern,
                )

        # Update miss counters from missed_factors
        for factor in output.missed_factors:
            # Normalise to snake_case key
            key = factor.strip().replace(" ", "_").replace("-", "_").lower()[:40]
            ledger.increment_miss(key)

        ledger.last_updated = date.today().isoformat()
        return ledger, lesson_ids
