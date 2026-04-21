"""
agents/weight_adapter.py
========================
Adjusts sub-agent weights based on daily feedback accuracy.

Works for all sectors: automobile · banking_bfsi · it_sector · renewable_energy
The agent list is derived from WeightMemory.current_weights — no sector hardcoding.

Penalty rules (all thresholds from config/settings.py):
  - Direction hits ≥ WEIGHT_BOOST_HIT_RATE over last N days  → +0.02
  - Direction hits ≤ WEIGHT_PENALTY_HIT_RATE over last N days → -0.03
  - Same agent was primary_miss_agent 2 days running          → -0.05 streak penalty
  - Any weight drifts > WEIGHT_MAX_DRIFT from base            → clamp to base ± drift
  - Weights always re-normalised to sum to 1.0

Miss-type aware (Design 1):
  Misses classified as data_gap, data_stale, or external_shock do NOT penalise
  the primary agent — the model was not at fault. Only model_bias and direction_flip
  carry full penalties; timing and magnitude carry partial penalties.

The adapter is purely deterministic — no LLM call.

Usage (called by scripts/daily_review.py):
    adapter = WeightAdapter()
    updated_wm = adapter.update(
        weight_memory=wm,
        feedback_log=log,
        todays_primary_miss_agent="risk_macro",
        todays_miss_type="data_gap",
    )
"""

from __future__ import annotations

import logging
from datetime import date

from config import settings
from core.schemas.feedback import (
    AgentAccuracy,
    DailyFeedbackLog,
    MISS_TYPE_PENALTY_MULTIPLIER,
    NO_PENALTY_MISS_TYPES,
    WeightHistoryEntry,
    WeightMemory,
)

logger = logging.getLogger(__name__)

# Base weight delta constants (before miss_type multiplier is applied)
_BOOST             = +0.02
_PENALTY           = -0.03
_MISS_STREAK_PENALTY = -0.05   # extra hit for 2-day consecutive primary miss


class WeightAdapter:
    """
    Deterministic weight adaptation engine.

    Reads the DailyFeedbackLog to score each agent, then applies bounded,
    miss-type-aware adjustments to WeightMemory and returns an updated copy.
    """

    def update(
        self,
        weight_memory: WeightMemory,
        feedback_log: DailyFeedbackLog,
        todays_primary_miss_agent: str,
        todays_miss_type: str = "direction_flip",
    ) -> WeightMemory:
        """
        Compute and apply weight adjustments based on today's feedback.

        Parameters
        ----------
        weight_memory : WeightMemory
            Current state loaded from JSON.
        feedback_log : DailyFeedbackLog
            Full log for the current cycle (used for rolling accuracy).
        todays_primary_miss_agent : str
            The agent blamed for today's miss by FeedbackAgent.
        todays_miss_type : str
            Miss classification from FeedbackAgentOutput.miss_type.
            Determines the penalty multiplier applied to streak penalty.
        """
        if len(feedback_log.entries) < settings.WEIGHT_MIN_OBSERVATIONS:
            logger.info(
                "[WeightAdapter] Only %d observations — need %d before adapting",
                len(feedback_log.entries),
                settings.WEIGHT_MIN_OBSERVATIONS,
            )
            return weight_memory

        agents   = list(weight_memory.current_weights.keys())
        accuracy = self._compute_accuracy(feedback_log, agents)
        deltas   = self._compute_deltas(
            accuracy,
            feedback_log,
            todays_primary_miss_agent,
            todays_miss_type,
            agents,
        )

        new_weights = self._apply_deltas(
            current=weight_memory.current_weights,
            base=weight_memory.base_weights,
            deltas=deltas,
            bounds=weight_memory.adjustment_bounds,
        )

        reason_parts = []
        for agent, delta in deltas.items():
            if delta != 0.0:
                acc = accuracy.get(agent)
                hits = f"{acc.direction_hits}/{acc.total}" if acc else "?"
                reason_parts.append(f"{agent}: Δ{delta:+.2f} (hits={hits})")
        reason = "; ".join(reason_parts) if reason_parts else "No adjustment needed"

        new_version = weight_memory.weight_version + 1
        weight_memory.current_weights = new_weights
        weight_memory.weight_version  = new_version
        weight_memory.last_updated    = date.today().isoformat()
        weight_memory.agent_accuracy  = accuracy
        weight_memory.weight_history.append(
            WeightHistoryEntry(
                version=new_version,
                date=date.today().isoformat(),
                weights=new_weights.copy(),
                reason=reason,
            )
        )

        logger.info("[WeightAdapter] Weights → v%d — %s", new_version, reason)
        return weight_memory

    # ------------------------------------------------------------------
    # Accuracy computation
    # ------------------------------------------------------------------

    def _compute_accuracy(
        self,
        feedback_log: DailyFeedbackLog,
        agents: list[str],
    ) -> dict[str, AgentAccuracy]:
        """
        Compute rolling direction accuracy per agent from the feedback log.

        Miss-type awareness:
          - Entries whose miss_type is in NO_PENALTY_MISS_TYPES (data_gap, data_stale,
            external_shock) grant the primary agent a hit credit even on wrong days —
            the model was not at fault, so it should not lose accuracy score.
        """
        window    = settings.WEIGHT_ACCURACY_WINDOW
        recent    = feedback_log.entries[-window:]

        hits:      dict[str, int]   = {a: 0 for a in agents}
        total:     dict[str, int]   = {a: 0 for a in agents}
        drift_sum: dict[str, float] = {a: 0.0 for a in agents}
        drift_cnt: dict[str, int]   = {a: 0 for a in agents}

        for entry in recent:
            miss_type = (
                entry.miss_analysis.miss_type
                if entry.miss_analysis and entry.miss_analysis.miss_type
                else "direction_flip"
            )
            is_no_penalty = miss_type in NO_PENALTY_MISS_TYPES

            for agent in agents:
                total[agent] += 1

                if entry.direction_correct:
                    hits[agent] += 1
                elif (
                    entry.miss_analysis
                    and entry.miss_analysis.primary_miss_agent == agent
                    and not is_no_penalty
                ):
                    # Primary miss agent on a penalisable miss — no hit credit
                    pass
                else:
                    # Non-primary agents on a miss day get credit.
                    # Primary agent also gets credit if miss was not their fault.
                    hits[agent] += 1

                if entry.miss_analysis and agent in entry.miss_analysis.agent_score_drift:
                    drift_sum[agent] += abs(entry.miss_analysis.agent_score_drift[agent])
                    drift_cnt[agent] += 1

        accuracy: dict[str, AgentAccuracy] = {}
        for agent in agents:
            avg_err = (drift_sum[agent] / drift_cnt[agent]) if drift_cnt[agent] > 0 else 0.0
            accuracy[agent] = AgentAccuracy(
                direction_hits=hits[agent],
                total=total[agent],
                avg_error=round(avg_err, 4),
            )
        return accuracy

    # ------------------------------------------------------------------
    # Delta computation
    # ------------------------------------------------------------------

    def _compute_deltas(
        self,
        accuracy: dict[str, AgentAccuracy],
        feedback_log: DailyFeedbackLog,
        todays_primary_miss: str,
        todays_miss_type: str,
        agents: list[str],
    ) -> dict[str, float]:
        """
        Compute raw weight delta per agent before bounds are applied.

        The miss_type multiplier scales the streak penalty:
          data_gap / data_stale / external_shock → 0.0 (no streak penalty)
          timing                                  → 0.5× streak penalty
          magnitude                               → 0.25× streak penalty
          model_bias / direction_flip             → 1.0× streak penalty (full)
        """
        deltas: dict[str, float] = {a: 0.0 for a in agents}
        miss_streak = self._consecutive_miss_streak(feedback_log, todays_primary_miss)
        penalty_multiplier = MISS_TYPE_PENALTY_MULTIPLIER.get(todays_miss_type, 1.0)

        for agent in agents:
            acc = accuracy.get(agent)
            if acc is None or acc.total == 0:
                continue

            hit_rate = acc.hit_rate()

            if hit_rate >= settings.WEIGHT_BOOST_HIT_RATE:
                deltas[agent] += _BOOST
            elif hit_rate <= settings.WEIGHT_PENALTY_HIT_RATE:
                deltas[agent] += _PENALTY

            if agent == todays_primary_miss and miss_streak >= 2:
                streak_penalty = _MISS_STREAK_PENALTY * penalty_multiplier
                deltas[agent] += streak_penalty
                if streak_penalty != 0.0:
                    logger.warning(
                        "[WeightAdapter] %s: %d-day miss streak (type=%s) → streak Δ%.3f",
                        agent, miss_streak, todays_miss_type, streak_penalty,
                    )
                else:
                    logger.info(
                        "[WeightAdapter] %s: %d-day streak but miss_type=%s — streak penalty waived",
                        agent, miss_streak, todays_miss_type,
                    )

        return deltas

    def _consecutive_miss_streak(
        self, feedback_log: DailyFeedbackLog, agent: str
    ) -> int:
        """Count how many consecutive recent days this agent was primary_miss_agent."""
        streak = 0
        for entry in reversed(feedback_log.entries):
            if (
                not entry.direction_correct
                and entry.miss_analysis
                and entry.miss_analysis.primary_miss_agent == agent
            ):
                streak += 1
            else:
                break
        return streak

    # ------------------------------------------------------------------
    # Delta application with bounds + normalisation
    # ------------------------------------------------------------------

    def _apply_deltas(
        self,
        current: dict[str, float],
        base: dict[str, float],
        deltas: dict[str, float],
        bounds: dict[str, float],
    ) -> dict[str, float]:
        """Apply deltas, clamp to bounds, then re-normalise to sum to 1.0."""
        max_step  = bounds.get("max_single_step",         settings.WEIGHT_MAX_STEP)
        max_drift = bounds.get("max_total_drift_from_base", settings.WEIGHT_MAX_DRIFT)

        new_weights: dict[str, float] = {}
        for agent, w in current.items():
            delta    = deltas.get(agent, 0.0)
            delta    = max(-max_step, min(max_step, delta))   # clamp single step
            proposed = w + delta

            base_w   = base.get(agent, w)
            lo       = max(0.0, base_w - max_drift)
            hi       = base_w + max_drift
            proposed = max(lo, min(hi, proposed))              # clamp total drift

            new_weights[agent] = round(proposed, 6)

        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}

        return new_weights
