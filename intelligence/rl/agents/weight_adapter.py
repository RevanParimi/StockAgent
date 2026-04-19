"""
agents/weight_adapter.py
========================
Adjusts the 5 sub-agent weights based on daily feedback accuracy.

Rules (all from config/settings.py):
  - Agent direction_hits ≥ WEIGHT_BOOST_HIT_RATE over last N days  → +0.02
  - Agent direction_hits ≤ WEIGHT_PENALTY_HIT_RATE over last N days → -0.03
  - Agent was primary_miss_agent 2 days in a row                    → -0.05 (immediate)
  - Any weight drifts > WEIGHT_MAX_DRIFT from its base value        → clamp to base ± drift
  - Weights re-normalised to sum to 1.0 after every step

The adapter is purely deterministic — no LLM call.

Usage (called by scripts/daily_review.py):
    adapter = WeightAdapter()
    updated_wm = adapter.update(
        weight_memory=wm,
        feedback_log=log,
        todays_primary_miss_agent="risk_macro",
    )
"""

from __future__ import annotations

import logging
from datetime import date

from config import settings
from core.schemas.feedback import (
    AgentAccuracy,
    DailyFeedbackLog,
    WeightHistoryEntry,
    WeightMemory,
)

logger = logging.getLogger(__name__)

# Weight delta constants
_BOOST   = +0.02
_PENALTY = -0.03
_MISS_STREAK_PENALTY = -0.05    # applied when same agent misses 2 days running


class WeightAdapter:
    """
    Deterministic weight adaptation engine.

    Reads the DailyFeedbackLog to score each agent, then applies bounded
    adjustments to the WeightMemory and returns an updated copy.
    """

    def update(
        self,
        weight_memory: WeightMemory,
        feedback_log: DailyFeedbackLog,
        todays_primary_miss_agent: str,
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

        Returns
        -------
        WeightMemory
            Updated memory with new version, weights, and history entry.
        """
        if len(feedback_log.entries) < settings.WEIGHT_MIN_OBSERVATIONS:
            logger.info(
                "[WeightAdapter] Only %d observations — need %d before adapting weights",
                len(feedback_log.entries),
                settings.WEIGHT_MIN_OBSERVATIONS,
            )
            return weight_memory

        agents = list(weight_memory.current_weights.keys())
        accuracy = self._compute_accuracy(feedback_log, agents)
        deltas = self._compute_deltas(
            accuracy,
            feedback_log,
            todays_primary_miss_agent,
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
                reason_parts.append(
                    f"{agent}: Δ{delta:+.2f} (hits={hits})"
                )
        reason = "; ".join(reason_parts) if reason_parts else "No adjustment needed"

        new_version = weight_memory.weight_version + 1
        history_entry = WeightHistoryEntry(
            version=new_version,
            date=date.today().isoformat(),
            weights=new_weights.copy(),
            reason=reason,
        )

        weight_memory.current_weights = new_weights
        weight_memory.weight_version = new_version
        weight_memory.last_updated = date.today().isoformat()
        weight_memory.agent_accuracy = accuracy
        weight_memory.weight_history.append(history_entry)

        logger.info(
            "[WeightAdapter] Weights updated to v%d — %s",
            new_version, reason,
        )
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

        For direction_hits we use the overall log direction_correct flag
        (the system-level direction), split by which agent was the
        primary_miss_agent on wrong days.

        For avg_error we use agent_score_drift values from miss_analysis.
        """
        window = settings.WEIGHT_ACCURACY_WINDOW
        recent = feedback_log.entries[-window:]

        # Initialise
        hits:  dict[str, int]   = {a: 0 for a in agents}
        total: dict[str, int]   = {a: 0 for a in agents}
        drift_sum: dict[str, float] = {a: 0.0 for a in agents}
        drift_cnt: dict[str, int]   = {a: 0 for a in agents}

        for entry in recent:
            for agent in agents:
                total[agent] += 1
                if entry.direction_correct:
                    hits[agent] += 1
                elif (
                    entry.miss_analysis
                    and entry.miss_analysis.primary_miss_agent == agent
                ):
                    # Primary miss agent does NOT get the hit
                    pass
                else:
                    # Non-primary agents on a miss day still get credit
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
        agents: list[str],
    ) -> dict[str, float]:
        """
        Compute the raw weight delta for each agent before bounds are applied.
        """
        deltas: dict[str, float] = {a: 0.0 for a in agents}
        miss_streak = self._consecutive_miss_streak(feedback_log, todays_primary_miss)

        for agent in agents:
            acc = accuracy.get(agent)
            if acc is None or acc.total == 0:
                continue

            hit_rate = acc.hit_rate()

            if hit_rate >= settings.WEIGHT_BOOST_HIT_RATE:
                deltas[agent] += _BOOST
            elif hit_rate <= settings.WEIGHT_PENALTY_HIT_RATE:
                deltas[agent] += _PENALTY

            # Extra penalty for 2-day consecutive primary miss
            if agent == todays_primary_miss and miss_streak >= 2:
                deltas[agent] += _MISS_STREAK_PENALTY
                logger.warning(
                    "[WeightAdapter] %s caused %d-day miss streak — applying streak penalty",
                    agent, miss_streak,
                )

        return deltas

    def _consecutive_miss_streak(
        self, feedback_log: DailyFeedbackLog, agent: str
    ) -> int:
        """
        Count how many consecutive recent days this agent was primary_miss_agent.
        """
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
        """
        Apply deltas, clamp to bounds, then re-normalise to sum to 1.0.
        """
        max_step  = bounds.get("max_single_step", settings.WEIGHT_MAX_STEP)
        max_drift = bounds.get("max_total_drift_from_base", settings.WEIGHT_MAX_DRIFT)

        new_weights: dict[str, float] = {}
        for agent, w in current.items():
            delta = deltas.get(agent, 0.0)
            # Clamp single step
            delta = max(-max_step, min(max_step, delta))
            proposed = w + delta

            # Clamp total drift from base
            base_w = base.get(agent, w)
            lo = max(0.0, base_w - max_drift)
            hi = base_w + max_drift
            proposed = max(lo, min(hi, proposed))

            new_weights[agent] = round(proposed, 6)

        # Re-normalise
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}

        return new_weights
