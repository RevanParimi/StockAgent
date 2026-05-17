"""
conviction/tracker.py
=====================
P3 — Conviction Duration & Mean Reversion Prior.

A system that has issued the same directional verdict (BUY / SELL) for many
consecutive days faces elevated mean-reversion risk — the move is more likely
to have been priced in, and a reversal becomes increasingly probable.

This module tracks that streak and emits a reversion_prior that dampens the
confidence of remaining forecasts.  It does NOT change verdict direction (that
is the LLM's job) — it only adjusts confidence to reflect accumulated tail risk.

Reversion prior formula (from RL_EVOLUTION_DESIGN.md):
    reversion_prior = min(0.25, max(0, (streak_days - 4) × 0.025))

Applied to forecast confidence:
    adjusted = current_confidence × (1.0 - reversion_prior × 0.5)
    (dampened — prior alone cannot halve confidence; it is a signal, not a verdict)

RSI divergence amplifier:
    When streak_days ≥ 8 AND sector RSI contradicts the verdict direction,
    the reversion_prior is amplified by 1.5 (capped at 0.30 total).
    Uses actual sector_rsi from RegimeDetector with canonical RSI thresholds 70/30.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.schemas.feedback import ConvictionStreak

logger = logging.getLogger(__name__)

# Minimum streak length before the FeedbackAgent receives a streak warning block.
STREAK_WARNING_THRESHOLD: int = 8

# Verdict groups for direction classification
_BULLISH: frozenset[str] = frozenset({"BUY", "STRONG BUY"})
_BEARISH: frozenset[str] = frozenset({"SELL", "STRONG SELL"})

# RSI thresholds: canonical RSI levels for overbought/oversold detection
_RSI_OVERBOUGHT_THRESHOLD: float = 70.0  # sector_rsi > this while BULLISH → divergence
_RSI_OVERSOLD_THRESHOLD:   float = 30.0  # sector_rsi < this while BEARISH → divergence
_RSI_AMPLIFIER:            float = 1.50  # multiplier when divergence detected
_MAX_REVERSION_PRIOR:      float = 0.30  # absolute cap including amplifier


# ---------------------------------------------------------------------------
# Direction helpers
# ---------------------------------------------------------------------------

def verdict_direction(verdict: str) -> str:
    """
    Classify a verdict string into one of three directions.

    Returns
    -------
    "BULLISH"  — BUY or STRONG BUY
    "BEARISH"  — SELL or STRONG SELL
    "NEUTRAL"  — NEUTRAL or any unrecognised string
    """
    v = verdict.upper().strip()
    if v in _BULLISH:
        return "BULLISH"
    if v in _BEARISH:
        return "BEARISH"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Reversion prior formula
# ---------------------------------------------------------------------------

def compute_reversion_prior(streak_days: int) -> float:
    """
    Compute the base reversion prior from the current streak length.

    Formula: min(0.25, max(0, (streak_days - 4) × 0.025))

    streak_days   prior
    ──────────    ──────
    0 – 4         0.000   (normal operation; no modifier)
    5             0.025   (mild caution)
    8             0.100   (moderate risk; dampen confidence)
    12            0.200   (elevated risk)
    14            0.250   (cap reached)
    21+           0.250   (cap; no further increase)
    """
    if streak_days <= 4:
        return 0.0
    return round(min(0.25, (streak_days - 4) * 0.025), 4)


# ---------------------------------------------------------------------------
# RSI divergence amplifier
# ---------------------------------------------------------------------------

def compute_rsi_amplifier(
    verdict: str,
    todays_agent_scores: dict[str, float],
    streak_days: int,
    sector_rsi: float = 50.0,
) -> float:
    """
    Return 1.5 if sector RSI contradicts the streak verdict, otherwise 1.0.
    Only activates when streak_days >= STREAK_WARNING_THRESHOLD.

    Uses sector_rsi from RegimeDetector (computed in daily_review Step 0):
      BULLISH streak + sector_rsi > 70  → overbought → amplify 1.5×
      BEARISH streak + sector_rsi < 30  → oversold   → amplify 1.5×
    """
    if streak_days < STREAK_WARNING_THRESHOLD:
        return 1.0

    direction = verdict_direction(verdict)

    if direction == "BULLISH" and sector_rsi > _RSI_OVERBOUGHT_THRESHOLD:
        logger.debug(
            "[ConvictionTracker] RSI overbought (BULLISH streak, sector_rsi=%.1f > 70) → amplifier 1.5×",
            sector_rsi,
        )
        return _RSI_AMPLIFIER

    if direction == "BEARISH" and sector_rsi < _RSI_OVERSOLD_THRESHOLD:
        logger.debug(
            "[ConvictionTracker] RSI oversold (BEARISH streak, sector_rsi=%.1f < 30) → amplifier 1.5×",
            sector_rsi,
        )
        return _RSI_AMPLIFIER

    return 1.0


def compute_final_reversion_prior(
    streak_days: int,
    verdict: str,
    todays_agent_scores: dict[str, float],
    sector_rsi: float = 50.0,
) -> float:
    """
    Convenience wrapper: compute base prior, apply RSI amplifier, cap at 0.30.
    sector_rsi should come from regime_snapshot.sector_rsi (Step 0 of daily_review).
    Defaults to 50.0 (neutral RSI) when not provided.

    Returns
    -------
    final_prior : float — 0.0 to 0.30
    """
    base = compute_reversion_prior(streak_days)
    if base == 0.0:
        return 0.0
    amplifier = compute_rsi_amplifier(verdict, todays_agent_scores, streak_days, sector_rsi)
    return round(min(_MAX_REVERSION_PRIOR, base * amplifier), 4)


# ---------------------------------------------------------------------------
# Streak update
# ---------------------------------------------------------------------------

def update_conviction_streak(
    current_streak: "ConvictionStreak",
    today_verdict: str,
    today_date: str,
) -> "ConvictionStreak":
    """
    Produce a new ConvictionStreak reflecting today's predicted verdict.

    Rules
    -----
    - Same direction as existing streak  → increment streak_days by 1
    - Different direction (flip)         → reset streak_days to 1, new start_date
    - NEUTRAL verdict                    → reset streak_days to 0, no start_date
    - max_streak_seen tracks the historical high for this cycle (never resets)

    Parameters
    ----------
    current_streak : ConvictionStreak
        The streak as stored in the envelope at the start of today's review.
    today_verdict : str
        The predicted_verdict from today's DailyForecast row.
    today_date : str
        ISO date string for today.

    Returns
    -------
    A new ConvictionStreak object (does NOT mutate the input).
    """
    from core.schemas.feedback import ConvictionStreak  # late import avoids circularity

    today_dir   = verdict_direction(today_verdict)
    current_dir = verdict_direction(current_streak.current_verdict)

    if today_dir == "NEUTRAL":
        new_days = 0
        new_start = ""
    elif today_dir == current_dir:
        new_days  = current_streak.streak_days + 1
        new_start = current_streak.streak_start_date or today_date
    else:
        # Direction flip — start fresh streak
        new_days  = 1
        new_start = today_date

    new_max   = max(current_streak.max_streak_seen, new_days)
    new_prior = compute_reversion_prior(new_days)

    return ConvictionStreak(
        current_verdict   = today_verdict,
        streak_days       = new_days,
        streak_start_date = new_start,
        max_streak_seen   = new_max,
        reversion_prior   = new_prior,
    )


# ---------------------------------------------------------------------------
# FeedbackAgent prompt warning block
# ---------------------------------------------------------------------------

def build_streak_warning_block(streak: "ConvictionStreak") -> str:
    """
    Return a structured warning block for injection into the FeedbackAgent's
    market_context_today when streak.streak_days >= STREAK_WARNING_THRESHOLD.

    This prompts the LLM to actively look for momentum exhaustion evidence
    rather than mechanically extending the existing trend.
    """
    reversion_pct = f"{streak.reversion_prior:.0%}"
    since = f" (since {streak.streak_start_date})" if streak.streak_start_date else ""
    return (
        f"\n\n[CONVICTION STREAK ALERT — reversion risk elevated]\n"
        f"This stock has issued {streak.current_verdict} for {streak.streak_days} "
        f"consecutive days{since}.\n"
        f"Reversion prior is currently {reversion_pct}.\n"
        f"Explicitly assess whether momentum exhaustion signals are present:\n"
        f"  - RSI divergence (price making new high / RSI making lower high)\n"
        f"  - Volume declining on up days (distribution pattern)\n"
        f"  - Delivery percentage drop on price rise (futures-driven move)\n"
        f"  - Relative underperformance vs sector index in the last 3 sessions\n"
        f"If any of these are present in market_context_today, classify accordingly "
        f"and reduce horizon_confidence_adjustment to reflect exhaustion risk."
    )
