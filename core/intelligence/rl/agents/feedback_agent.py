"""
agents/feedback_agent.py
========================
The daily learning agent for the RL Feedback Loop.

Unlike the sector sub-agents it does NOT subclass BaseAgent because its
inputs are structured feedback data rather than a StockQuery.

Works for all sectors: automobile · banking_bfsi · it_sector · renewable_energy
The system prompt is built dynamically from fb_input.sector + agent names.

Responsibilities each trading day:
  1. Receive predicted vs actual values + market context
  2. Call LLM to produce structured miss analysis with miss_type classification
  3. Extract new scoped lessons for the LearningLedger
  4. Return FeedbackAgentOutput ready for WeightAdapter consumption

Usage (called by scripts/daily_review.py):
    agent = FeedbackAgent()
    output = agent.run(fb_input, ledger)
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date
from pathlib import Path

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

from core.config import settings
from services.clients.llm_client import record_llm_call
from core.intelligence.rl.stores.ledger_propagator import resurrect_lesson
from core.schemas.feedback import (
    FeedbackAgentInput,
    FeedbackAgentOutput,
    LearningLedger,
    Lesson,
    MissType,
    RawLesson,
    RevisedContext,
)
from core.config.prompts.shared.feedback_agent import build_system_prompt, format_feedback_prompt

logger = logging.getLogger(__name__)

# ±N% threshold to classify a price move as directional vs FLAT.
# Override via settings.RL_FLAT_THRESHOLD_PCT for more volatile tickers.
try:
    FLAT_THRESHOLD_PCT: float = settings.RL_FLAT_THRESHOLD_PCT
except AttributeError:
    FLAT_THRESHOLD_PCT: float = 0.3  # type: ignore[no-redef]

# Temperature for the FeedbackAgent LLM call.
# 0.3 (vs the previous 0.1) gives enough creativity to surface non-obvious
# cross-signal patterns while still producing deterministic structured JSON.
_FEEDBACK_TEMPERATURE = 0.3


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
    BUY / STRONG BUY  → expects UP
    SELL / STRONG SELL → expects DOWN
    NEUTRAL            → no directional claim, always treated as not-wrong
    """
    bullish = {"BUY", "STRONG BUY"}
    bearish = {"SELL", "STRONG SELL"}
    verdict_upper = predicted_verdict.upper()
    if verdict_upper in bullish:
        return actual_direction == "UP"
    if verdict_upper in bearish:
        return actual_direction == "DOWN"
    return True


class FeedbackAgent:
    """
    Analyses daily prediction misses and generates stock-specific lessons.
    Sector-agnostic — behaviour is driven by fb_input.sector.
    """

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
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
            fb_input.sector drives the system prompt and agent list.
        ledger : LearningLedger
            Current ledger so the LLM knows what patterns are already known.
        """
        logger.info(
            "[FeedbackAgent] Analysing %s (%s) on %s | error=%.2f%% | correct=%s",
            fb_input.ticker,
            fb_input.sector,
            fb_input.date,
            fb_input.price_error_pct,
            fb_input.direction_correct,
        )

        # Build sector-aware system prompt from live agent list
        agent_names = list(fb_input.predicted_agent_scores.keys()) or list(
            fb_input.todays_agent_scores.keys()
        )
        system_prompt = build_system_prompt(fb_input.sector, agent_names)

        # P2: use the pre-built 3-tier summary from fb_input when available;
        # fall back to the single-ledger summary for backward compatibility.
        active_lessons = (
            fb_input.active_lessons_summary
            if fb_input.active_lessons_summary
            else ledger.active_lessons_summary()
        )

        user_prompt = format_feedback_prompt(
            ticker=fb_input.ticker,
            sector=fb_input.sector,
            date=fb_input.date,
            predicted_close=fb_input.predicted_close,
            actual_close=fb_input.actual_close,
            price_error_pct=fb_input.price_error_pct,
            direction_correct=fb_input.direction_correct,
            predicted_agent_scores=fb_input.predicted_agent_scores,
            todays_agent_scores=fb_input.todays_agent_scores,
            market_context_today=fb_input.market_context_today,
            key_assumptions_made=fb_input.key_assumptions_made,
            active_lessons_summary=active_lessons,
            # New context fields — all have safe defaults so backward compat is preserved
            significant_subscore_drift=fb_input.significant_subscore_drift or {},
            weight_drift_summary=fb_input.weight_drift_summary or "",
            recent_accuracy_trend=fb_input.recent_accuracy_trend or "",
            previous_watch_signals=fb_input.previous_watch_signals or [],
            volume_context=fb_input.volume_context or "",
            forecast_profile_context=fb_input.forecast_profile_context or "",
            predicted_catalysts_by_agent=fb_input.predicted_catalysts_by_agent or {},
        )

        try:
            raw = self._call_llm(system_prompt, user_prompt)
        except Exception as exc:
            logger.error(
                "[FeedbackAgent] LLM call failed for %s on %s: %s — "
                "returning degraded output; weights and lessons NOT updated",
                fb_input.ticker, fb_input.date, exc,
            )
            return FeedbackAgentOutput(
                miss_type="data_gap",
                primary_miss_agent="",
                missed_factors=[f"LLM unavailable: {exc}"],
                over_weighted_factors=[],
                agent_score_drift={},
                new_lessons=[],
                revised_context=RevisedContext(
                    headline=f"LLM unavailable on {fb_input.date} — no analysis performed",
                    watch_signals=[],
                    horizon_confidence_adjustment=0.0,
                ),
            )

        output = self._parse(raw, fb_input)

        logger.info(
            "[FeedbackAgent] Done — miss_type=%s primary=%s new_lessons=%d",
            output.miss_type,
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
            _t0 = time.monotonic()
            try:
                response = self._client.chat.completions.create(
                    model=settings.LLM_MODEL_REASONING,
                    temperature=_FEEDBACK_TEMPERATURE,
                    max_tokens=1500,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                _latency = int((time.monotonic() - _t0) * 1000)
                record_llm_call(
                    caller="FeedbackAgent",
                    model=response.model or "unknown",
                    input_tokens=response.usage.prompt_tokens if response.usage else 0,
                    output_tokens=response.usage.completion_tokens if response.usage else 0,
                    latency_ms=_latency,
                    success=True,
                )
                return response.choices[0].message.content or "{}"

            except RateLimitError as e:
                _latency = int((time.monotonic() - _t0) * 1000)
                record_llm_call(
                    caller="FeedbackAgent",
                    model="unknown",
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=_latency,
                    success=False,
                )
                logger.warning(
                    "[FeedbackAgent] Rate limit (attempt %d/%d)", attempt, settings.MAX_RETRIES
                )
                last_error = e
                time.sleep(delay)
                delay *= 2

            except APITimeoutError as e:
                _latency = int((time.monotonic() - _t0) * 1000)
                record_llm_call(
                    caller="FeedbackAgent",
                    model="unknown",
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=_latency,
                    success=False,
                )
                logger.warning(
                    "[FeedbackAgent] Timeout (attempt %d/%d)", attempt, settings.MAX_RETRIES
                )
                last_error = e
                time.sleep(delay)

            except APIError as e:
                _latency = int((time.monotonic() - _t0) * 1000)
                record_llm_call(
                    caller="FeedbackAgent",
                    model="unknown",
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=_latency,
                    success=False,
                )
                logger.error("[FeedbackAgent] API error: %s", e)
                last_error = e
                break

        raise RuntimeError(f"[FeedbackAgent] LLM call failed after retries: {last_error}")

    # ------------------------------------------------------------------
    # Parse LLM JSON → FeedbackAgentOutput
    # ------------------------------------------------------------------

    _VALID_MISS_TYPES = {
        "data_gap", "data_stale", "external_shock",
        "timing", "magnitude", "model_bias", "direction_flip",
    }
    _VALID_SCOPES = {"stock_specific", "sector_wide", "market_wide"}

    def _parse(self, raw: str, fb_input: FeedbackAgentInput) -> FeedbackAgentOutput:
        try:
            stripped = (raw or "").strip()
            if stripped.startswith("```"):
                stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
                stripped = re.sub(r"\s*```\s*$", "", stripped).strip()
            data = json.loads(stripped)

            # Parse raw lessons with scope
            raw_lessons = [
                RawLesson(
                    category=item.get("category", "macro"),
                    pattern=item.get("pattern", "unknown").lower().replace(" ", "_"),
                    observation=item.get("observation", ""),
                    rule=item.get("rule", ""),
                    confidence=float(item.get("confidence", 0.5)),
                    scope=item.get("scope", "stock_specific")
                    if item.get("scope") in self._VALID_SCOPES
                    else "stock_specific",
                )
                for item in data.get("new_lessons", [])
            ]

            # Parse revised_context as structured object
            rc_raw = data.get("revised_context", {})
            if isinstance(rc_raw, str):
                # Backward compat: LLM returned a string instead of an object
                revised_context = RevisedContext(headline=rc_raw)
            else:
                raw_conf_adj = float(rc_raw.get("horizon_confidence_adjustment", 0.0))
                # Clamp to [-0.15, +0.05]: thesis_reviewer handles deeper cuts via multiplier
                clamped_conf_adj = max(-0.15, min(0.05, raw_conf_adj))
                if clamped_conf_adj != raw_conf_adj:
                    logger.warning(
                        "[FeedbackAgent] horizon_confidence_adjustment %.3f out of range "
                        "[-0.15, +0.05] — clamped to %.3f",
                        raw_conf_adj, clamped_conf_adj,
                    )
                revised_context = RevisedContext(
                    headline=rc_raw.get("headline", ""),
                    risks_next_7_days=rc_raw.get("risks_next_7_days", []),
                    catalysts_next_7_days=rc_raw.get("catalysts_next_7_days", []),
                    watch_signals=rc_raw.get("watch_signals", []),
                    horizon_confidence_adjustment=clamped_conf_adj,
                )

            # Validate miss_type
            miss_type_raw = data.get("miss_type", "direction_flip")
            miss_type: MissType = (
                miss_type_raw if miss_type_raw in self._VALID_MISS_TYPES else "direction_flip"
            )

            known_agents = set(fb_input.predicted_agent_scores.keys())
            raw_miss_agent = data.get("primary_miss_agent", "unknown")
            validated_miss_agent = (
                raw_miss_agent if raw_miss_agent in known_agents else "unknown"
            )
            if raw_miss_agent not in known_agents and raw_miss_agent != "unknown":
                logger.warning(
                    "[FeedbackAgent] primary_miss_agent '%s' not in known agents %s — reset to 'unknown'",
                    raw_miss_agent, sorted(known_agents),
                )

            return FeedbackAgentOutput(
                primary_miss_agent=validated_miss_agent,
                miss_type=miss_type,
                missed_factors=data.get("missed_factors", []),
                over_weighted_factors=data.get("over_weighted_factors", []),
                agent_score_drift=data.get("agent_score_drift", {}),
                new_lessons=raw_lessons,
                revised_context=revised_context,
            )

        except Exception as exc:
            logger.error("[FeedbackAgent] Parse error: %s | Raw: %s", exc, raw[:400])
            return FeedbackAgentOutput(
                primary_miss_agent="unknown",
                miss_type="direction_flip",
                missed_factors=[f"Parse error: {exc}"],
            )

    # ------------------------------------------------------------------
    # Ledger integration: merge raw lessons into LearningLedger
    # ------------------------------------------------------------------

    def merge_lessons_into_ledger(
        self,
        output: FeedbackAgentOutput,
        ledger: LearningLedger,
        cold_store_path: "Path | str | None" = None,
    ) -> tuple[LearningLedger, list[str]]:
        """
        Merge new lessons from FeedbackAgentOutput into the LearningLedger.

        - Existing pattern → increment occurrences, blend confidence (weighted avg),
          update last_seen to today, update scope if broader.
        - New pattern → check the cold store (RL Intelligence Phase, Component 3)
          for a previously-archived lesson with the same pattern; if found,
          resurrect it (occurrences/history intact) instead of creating a
          duplicate. Otherwise create a fresh Lesson with scope and last_seen set.

        `cold_store_path` is optional — when None (default), resurrection is
        skipped entirely and behavior is unchanged from before Component 3.

        Returns (updated_ledger, list_of_lesson_ids_touched).
        """
        lesson_ids: list[str] = []
        today_str = date.today().isoformat()

        for raw in output.new_lessons:
            existing = ledger.find_by_pattern(raw.pattern)
            if existing is not None:
                existing.occurrences += 1
                existing.confidence = round(
                    (existing.confidence * (existing.occurrences - 1) + raw.confidence)
                    / existing.occurrences,
                    4,
                )
                existing.last_seen = today_str
                # Widen scope if the new observation implies broader applicability
                _scope_rank = {"stock_specific": 0, "sector_wide": 1, "market_wide": 2}
                if _scope_rank.get(raw.scope, 0) > _scope_rank.get(existing.scope, 0):
                    existing.scope = raw.scope
                lesson_ids.append(existing.lesson_id)
                logger.info(
                    "[FeedbackAgent] Updated %s (pattern=%s occurrences=%d scope=%s)",
                    existing.lesson_id, existing.pattern, existing.occurrences, existing.scope,
                )
                continue

            # No live lesson with this pattern — check the cold store before
            # creating a new one (resurrection, Component 3).
            resurrected = None
            if cold_store_path is not None:
                try:
                    resurrected = resurrect_lesson(
                        ledger,
                        cold_store_path,
                        pattern=raw.pattern,
                        new_confidence=raw.confidence,
                    )
                except Exception as exc:
                    logger.warning(
                        "[FeedbackAgent] Lesson resurrection check failed for "
                        "pattern '%s' (non-fatal): %s", raw.pattern, exc,
                    )

            if resurrected is not None:
                lesson_ids.append(resurrected.lesson_id)
                logger.info(
                    "[FeedbackAgent] Resurrected %s (pattern=%s occurrences=%d) "
                    "from cold store instead of creating a duplicate",
                    resurrected.lesson_id, resurrected.pattern, resurrected.occurrences,
                )
                continue

            new_id = ledger.next_lesson_id()
            lesson = Lesson(
                lesson_id=new_id,
                date_learned=today_str,
                category=raw.category,
                pattern=raw.pattern,
                observation=raw.observation,
                rule=raw.rule,
                confidence=raw.confidence,
                occurrences=1,
                still_valid=True,
                scope=raw.scope,
                last_seen=today_str,
            )
            ledger.lessons.append(lesson)
            lesson_ids.append(new_id)
            logger.info(
                "[FeedbackAgent] Added %s (pattern=%s scope=%s)",
                new_id, raw.pattern, raw.scope,
            )

        for factor in output.missed_factors:
            key = factor.strip().replace(" ", "_").replace("-", "_").lower()[:40]
            ledger.increment_miss(key)

        ledger.last_updated = today_str
        return ledger, lesson_ids
