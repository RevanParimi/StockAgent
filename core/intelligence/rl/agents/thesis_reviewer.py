"""
core/intelligence/rl/agents/thesis_reviewer.py
===============================================
Conditional thesis review after a significant prediction miss.

WHEN IT FIRES (checked in daily_review.py):
  |price_error_pct| > ATR-relative threshold (max(1.5%, 1.5 * atr_pct))
  OR (direction_correct=False AND miss_type in {direction_flip, model_bias})

WHY IT EXISTS:
  After a large miss the system mechanically re-weights and re-forecasts the
  remaining 30 days.  But if the underlying thesis was wrong (e.g. the stock
  was assumed to benefit from stable crude, and crude just spiked 8%), then
  every remaining forecast carries forward a broken assumption.  Re-weighting
  produces a BUY with lower confidence — still BUY, still wrong direction.

  ThesisReviewer asks: which of the original key_assumptions are now
  invalidated?  Is the 30-day thesis still intact, or does the remaining
  forecast need a confidence haircut across the board?

ATR-RELATIVE THRESHOLD:
  A flat 2% threshold was too blunt.  For HDFCBANK (ATR ~0.8%), 2% is a
  2.5-sigma event.  For ADANIGREEN (ATR ~3.5%), 2% is sub-1-sigma noise.
  Threshold = max(settings.RL_ATR_THRESHOLD_FLOOR, settings.RL_ATR_THRESHOLD_MULTIPLIER * atr_pct)
  This ensures volatile stocks need proportionally larger misses to trigger.

WHAT IT DOES NOT DO:
  - It does NOT change the verdict direction (that is the FeedbackAgent's job
    via the regular daily review cycle).
  - It does NOT re-run agents or fetch new data.
  - It only examines the original assumptions against what actually happened.

LLM COST:
  ~250 input tokens, ~80 output tokens.  Fires at most once per ticker per
  significant-miss day — typically 1-3 times per month across all tickers.

CALIBRATION TELEMETRY:
  Each review appends a jsonl record to data/predictions/<sector>/<ticker>/
  thesis_calls.jsonl capturing the multiplier, thesis_intact flag, and the
  price error that triggered the review.  Used for future accuracy analysis.
"""

from __future__ import annotations

import json
import logging
import re
import time

from openai import APIError, APITimeoutError, RateLimitError

from core.config import settings
from services.clients.llm_client import JSON_MODE_EXTRA_BODY
from core.schemas.feedback import FeedbackAgentOutput, ThesisReview

logger = logging.getLogger(__name__)

# Backward-compat alias — external code that imports THESIS_REVIEW_THRESHOLD still works.
# Effective threshold is ATR-relative: max(RL_ATR_THRESHOLD_FLOOR, RL_ATR_THRESHOLD_MULTIPLIER * atr_pct)
THESIS_REVIEW_THRESHOLD: float = settings.RL_ATR_THRESHOLD_FLOOR

# Miss types that warrant thesis review even below the price error threshold.
THESIS_REVIEW_MISS_TYPES: frozenset[str] = frozenset({"direction_flip", "model_bias"})

_SYSTEM_PROMPT = """\
You are a quantitative analyst reviewing whether a stock prediction thesis is still valid \
after a significant miss.

You will receive:
- The original key assumptions made when the 30-day forecast was generated
- What actually happened today (the miss analysis)
- Current market context

Your job is to identify which assumptions are NOW invalidated by today's outcome, \
and whether the 30-day forward thesis is still broadly intact.

Return ONLY valid JSON matching this schema:
{
  "assumptions_invalidated": ["<assumption text>", ...],
  "assumptions_still_valid": ["<assumption text>", ...],
  "thesis_intact": true | false,
  "revised_narrative": "<1-2 sentence forward outlook given what just happened>",
  "horizon_confidence_multiplier": <float 0.3 to 1.0>
}

horizon_confidence_multiplier guidance:
  1.00 — thesis intact; minor revision only
  0.85 — one assumption broken but recovery still plausible
  0.70 — core assumption invalidated; high uncertainty for 30-day horizon
  0.50 — thesis is fundamentally wrong; deep uncertainty

Do NOT speculate about future price direction. Only assess assumption validity.
Do NOT output analyst ratings, broker targets, or EPS estimates.
"""


def _format_prompt(
    ticker: str,
    sector: str,
    key_assumptions: list[str],
    fb_output: FeedbackAgentOutput,
    market_context: str,
) -> str:
    assumptions_str = "\n".join(f"  - {a}" for a in key_assumptions) or "  (none recorded)"
    missed_str = "\n".join(f"  - {f}" for f in fb_output.missed_factors) or "  (none)"
    over_str = "\n".join(f"  - {f}" for f in fb_output.over_weighted_factors) or "  (none)"
    return (
        f"TICKER: {ticker} | SECTOR: {sector}\n\n"
        f"ORIGINAL KEY ASSUMPTIONS (when 30-day forecast was generated):\n{assumptions_str}\n\n"
        f"TODAY'S MISS ANALYSIS:\n"
        f"  miss_type: {fb_output.miss_type}\n"
        f"  primary_miss_agent: {fb_output.primary_miss_agent}\n"
        f"  missed_factors (not captured):\n{missed_str}\n"
        f"  over_weighted_factors:\n{over_str}\n\n"
        f"MARKET CONTEXT TODAY (first 400 chars):\n{market_context[:400]}\n\n"
        f"Assess: which original assumptions are invalidated? Is the 30-day thesis intact?"
    )


class ThesisReviewer:
    """
    Single-call LLM reviewer for post-miss thesis validity.
    Stateless — one instance is fine to reuse across tickers.
    """

    def __init__(self) -> None:
        from openai import OpenAI
        self._client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def should_review(
        self,
        price_error_pct: float,
        direction_correct: bool,
        miss_type: str,
        ticker: str = "",
    ) -> bool:
        """True when a thesis review is warranted for this day's outcome."""
        # Structural miss always triggers regardless of size
        if not direction_correct and miss_type in THESIS_REVIEW_MISS_TYPES:
            return True
        # ATR-relative size trigger: volatile stocks need larger misses to trigger
        try:
            atr_pct = self._compute_atr_pct(ticker) if ticker else 0.0
        except Exception:
            atr_pct = 0.0
        threshold = max(settings.RL_ATR_THRESHOLD_FLOOR, settings.RL_ATR_THRESHOLD_MULTIPLIER * atr_pct)
        return abs(price_error_pct) > threshold

    def _compute_atr_pct(self, ticker: str = "") -> float:
        """14-day ATR as % of price. Returns 0.0 on failure (caller uses floor)."""
        try:
            from core.intelligence.rl.algorithms.price_interpolator import compute_atr_pct
            from core.data.fetchers.price import get_price_history
            ohlcv = get_price_history(ticker, years=1)
            return compute_atr_pct(ohlcv)
        except Exception:
            return 0.0

    def review(
        self,
        ticker: str,
        sector: str,
        key_assumptions: list[str],
        fb_output: FeedbackAgentOutput,
        market_context: str,
        price_error_pct: float = 0.0,
    ) -> ThesisReview:
        """
        Run the thesis review LLM call.

        Returns a ThesisReview on success.
        On any LLM/parse failure, returns a safe default (thesis_intact=True,
        multiplier=1.0) so the daily review is never blocked.
        """
        try:
            user_prompt = _format_prompt(ticker, sector, key_assumptions, fb_output, market_context)
            raw = self._call_llm(user_prompt)
            result = self._parse(raw, key_assumptions)
            # --- calibration telemetry ---
            try:
                import json as _json
                from datetime import date as _date
                from pathlib import Path as _Path
                _cal_dir = _Path("data/predictions") / sector / ticker
                _cal_dir.mkdir(parents=True, exist_ok=True)
                _entry = _json.dumps({
                    "date": str(_date.today()),
                    "ticker": ticker,
                    "multiplier": result.horizon_confidence_multiplier,
                    "thesis_intact": result.thesis_intact,
                    "price_error_at_trigger": round(abs(price_error_pct), 2),
                })
                with open(_cal_dir / "thesis_calls.jsonl", "a", encoding="utf-8") as _fh:
                    _fh.write(_entry + "\n")
            except Exception:
                pass
            return result
        except Exception as exc:
            logger.warning(
                "[ThesisReviewer] Failed for %s (%s) — returning safe default: %s",
                ticker, sector, exc,
            )
            return ThesisReview(thesis_intact=True, horizon_confidence_multiplier=1.0)

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_llm(self, user_prompt: str) -> str:
        delay = settings.RETRY_DELAY_SECONDS
        last_err: Exception | None = None

        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=settings.LLM_MODEL_REASONING,
                    temperature=0.1,        # low temp — we want deterministic validity assessment
                    max_tokens=300,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    extra_body=JSON_MODE_EXTRA_BODY,
                )
                return resp.choices[0].message.content or "{}"
            except RateLimitError as e:
                logger.warning("[ThesisReviewer] Rate limit (attempt %d)", attempt)
                last_err = e
                time.sleep(delay); delay *= 2
            except APITimeoutError as e:
                logger.warning("[ThesisReviewer] Timeout (attempt %d)", attempt)
                last_err = e
                time.sleep(delay)
            except APIError as e:
                logger.error("[ThesisReviewer] API error: %s", e)
                last_err = e; break

        raise RuntimeError(f"[ThesisReviewer] LLM failed after retries: {last_err}")

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def _parse(self, raw: str, original_assumptions: list[str]) -> ThesisReview:
        # Strip markdown code fences that some models add despite json_object format
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```\s*$", "", stripped).strip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            logger.warning("[ThesisReviewer] JSON parse error: %s — raw: %.200s", exc, raw)
            return ThesisReview(thesis_intact=True, horizon_confidence_multiplier=1.0)

        multiplier = float(data.get("horizon_confidence_multiplier", 1.0))
        multiplier = max(0.3, min(1.0, multiplier))

        return ThesisReview(
            assumptions_invalidated=data.get("assumptions_invalidated", [])[:5],
            assumptions_still_valid=data.get("assumptions_still_valid", [])[:5],
            thesis_intact=bool(data.get("thesis_intact", True)),
            revised_narrative=str(data.get("revised_narrative", ""))[:300],
            horizon_confidence_multiplier=round(multiplier, 3),
        )
