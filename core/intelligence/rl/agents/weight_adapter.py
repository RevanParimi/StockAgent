"""
agents/weight_adapter.py
========================
Adjusts sub-agent weights based on daily feedback accuracy.

Works for all sectors: automobile · banking_bfsi · it_sector · renewable_energy
The agent list is derived from WeightMemory.current_weights — no sector hardcoding.

Penalty rules (all thresholds from config/settings.py):
  - Direction hits ≥ WEIGHT_BOOST_HIT_RATE over last N trading days  → +0.02
  - Direction hits ≤ WEIGHT_PENALTY_HIT_RATE over last N trading days → -0.03
  - Weighted rolling miss rate across 5/10/21 trading-day windows ≥ 0.55 → bias penalty
    (replaces brittle consecutive-streak approach — survives 1 good day in a bad run)
  - Any weight drifts > WEIGHT_MAX_DRIFT from base → clamp to base ± drift
  - Weights always re-normalised to sum to 1.0

Miss-type aware:
  data_gap / data_stale / external_shock  → zero penalty (model not at fault)
  timing                                  → lag-tolerance: ≤3 td off = no penalty,
                                            ≤7 td = 0.20×, >7 td = 0.50×
  magnitude                               → 0.25× bias penalty
  model_bias / direction_flip             → 1.0× bias penalty (full)

Seasonal threshold shifts:
  SeasonalPattern.accuracy_threshold_delta shifts boost/penalty thresholds per agent
  per calendar period — preventing undeserved boosts during easy seasons and
  unfair penalties during structurally hard periods (e.g. budget week).

Calendar awareness:
  All rolling windows are computed using actual trading dates (Mon–Fri),
  not array indices. This prevents weekend/holiday gaps from distorting window sizes.
  NSE holidays are not yet modelled — only weekends are excluded. Add an NSE holiday
  set to _TRADING_DAY_SKIP when that data is available.

The adapter is purely deterministic — no LLM call.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from core.config import settings
from core.schemas.feedback import (
    AgentAccuracy,
    DailyFeedbackLog,
    MISS_TYPE_PENALTY_MULTIPLIER,
    NO_PENALTY_MISS_TYPES,
    WeightHistoryEntry,
    WeightMemory,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weight delta constants — now sourced from settings (STATIC_AUDIT #4)
# Override via env vars: RL_BOOST, RL_PENALTY, RL_MISS_STREAK_PENALTY, etc.
# ---------------------------------------------------------------------------
from backend.shared.config import settings as _s

_BOOST               = _s.RL_BOOST
_PENALTY             = _s.RL_PENALTY
_MISS_STREAK_PENALTY = _s.RL_MISS_STREAK_PENALTY  # base bias penalty; scales with bias_score

# Multi-window bias detection (trading-day-aware)
_BIAS_WINDOWS        = [5, 10, 21]           # trading days: ~1 wk, ~2 wk, ~1 month
_BIAS_WINDOW_WEIGHTS = [0.50, 0.30, 0.20]    # recent windows weighted more heavily
_BIAS_TRIGGER        = _s.RL_BIAS_TRIGGER    # weighted miss rate → penalty starts
_BIAS_FULL           = _s.RL_BIAS_FULL       # weighted miss rate → full _MISS_STREAK_PENALTY

# Timing lag tolerance tiers (trading days)
_TIMING_FREE_WINDOW    = _s.RL_TIMING_FREE_WINDOW    # ≤N days off → no penalty
_TIMING_PARTIAL_WINDOW = _s.RL_TIMING_PARTIAL_WINDOW # ≤N days off → 0.20× penalty
                                                      # >N days     → 0.50× penalty


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
        timing_lag_days: int = 0,
        seasonal_threshold_deltas: dict[str, float] | None = None,
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
        timing_lag_days : int
            Signed lag from TimingAccuracy.lag_days (actual − predicted peak day).
            Used to apply tolerance-based timing penalty scaling.
        seasonal_threshold_deltas : dict[str, float] | None
            Per-agent boost/penalty threshold modifiers from SeasonalContext.
            e.g. {"sales_demand": +0.08} during festive season raises the bar
            for that agent to earn a boost (prevents undeserved weight inflation).
        """
        if len(feedback_log.entries) < settings.WEIGHT_MIN_OBSERVATIONS:
            logger.info(
                "[WeightAdapter] Only %d observations — need %d before adapting",
                len(feedback_log.entries),
                settings.WEIGHT_MIN_OBSERVATIONS,
            )
            return weight_memory

        today          = date.today()
        agents         = list(weight_memory.current_weights.keys())
        accuracy       = self._compute_accuracy(feedback_log, agents, reference_date=today)
        deltas         = self._compute_deltas(
            accuracy=accuracy,
            feedback_log=feedback_log,
            todays_primary_miss=todays_primary_miss_agent,
            todays_miss_type=todays_miss_type,
            agents=agents,
            timing_lag_days=timing_lag_days,
            seasonal_threshold_deltas=seasonal_threshold_deltas,
            reference_date=today,
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
                acc  = accuracy.get(agent)
                hits = f"{acc.direction_hits}/{acc.total}" if acc else "?"
                reason_parts.append(f"{agent}: Δ{delta:+.2f} (hits={hits})")
        reason = "; ".join(reason_parts) if reason_parts else "No adjustment needed"

        new_version = weight_memory.weight_version + 1
        weight_memory.current_weights = new_weights
        weight_memory.weight_version  = new_version
        weight_memory.last_updated    = today.isoformat()
        weight_memory.agent_accuracy  = accuracy
        weight_memory.weight_history.append(
            WeightHistoryEntry(
                version=new_version,
                date=today.isoformat(),
                weights=new_weights.copy(),
                reason=reason,
            )
        )

        logger.info("[WeightAdapter] Weights → v%d — %s", new_version, reason)
        return weight_memory

    # ------------------------------------------------------------------
    # Calendar helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _trading_days_ago(reference: date, n: int) -> date:
        """
        Return the calendar date that is exactly N NSE trading days before reference.
        Uses the shared nse_calendar which excludes weekends + NSE public holidays.
        """
        from core.intelligence.rl.nse_calendar import trading_days_ago
        return trading_days_ago(reference, n)

    def _window_entries(
        self,
        feedback_log: DailyFeedbackLog,
        n_trading_days: int,
        reference: date,
    ) -> list:
        """
        Return feedback entries whose date falls within the last N trading days
        from reference. Uses ISO date strings stored in each entry.
        """
        cutoff = self._trading_days_ago(reference, n_trading_days)
        return [
            e for e in feedback_log.entries
            if date.fromisoformat(e.date) >= cutoff
        ]

    # ------------------------------------------------------------------
    # Accuracy computation
    # ------------------------------------------------------------------

    def _compute_accuracy(
        self,
        feedback_log: DailyFeedbackLog,
        agents: list[str],
        reference_date: date | None = None,
    ) -> dict[str, AgentAccuracy]:
        """
        Compute rolling direction accuracy per agent for the last
        WEIGHT_ACCURACY_WINDOW trading days (calendar-aware, not index-based).

        Miss-type awareness:
          Entries with miss_type in NO_PENALTY_MISS_TYPES grant the primary agent
          a hit credit even on wrong days — the model was not at fault.
        """
        ref    = reference_date or date.today()
        recent = self._window_entries(feedback_log, settings.WEIGHT_ACCURACY_WINDOW, ref)

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
                    # Non-primary agents always get credit on a miss day.
                    # Primary agent gets credit too when miss was not their fault.
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
    # Bias score (replaces consecutive streak)
    # ------------------------------------------------------------------

    def _compute_bias_score(
        self,
        feedback_log: DailyFeedbackLog,
        agent: str,
        reference: date,
    ) -> float:
        """
        Weighted rolling miss rate across three trading-day windows.

        Each window only counts penalisable misses (excludes NO_PENALTY_MISS_TYPES)
        where this agent was blamed. The three windows are weighted so that recent
        performance dominates but persistent patterns across 2–4 weeks still register.

        Returns a score in [0.0, 1.0]:
          ≥ _BIAS_TRIGGER (0.55) → bias penalty begins, scales linearly
          ≥ _BIAS_FULL    (0.70) → full _MISS_STREAK_PENALTY applied
          < _BIAS_TRIGGER        → no bias penalty

        Advantage over streak ≥ 2:
          3 bad days → 1 good day → 3 bad days  gives score ≈ 0.60 → penalty ✓
          2 isolated bad days in 10              gives score ≈ 0.20 → no penalty ✓
        """
        weighted_rate  = 0.0
        total_weight   = 0.0

        for window, wt in zip(_BIAS_WINDOWS, _BIAS_WINDOW_WEIGHTS):
            entries      = self._window_entries(feedback_log, window, reference)
            penalisable  = [
                e for e in entries
                if e.miss_analysis
                and e.miss_analysis.miss_type not in NO_PENALTY_MISS_TYPES
            ]
            if not penalisable:
                continue
            agent_misses = sum(
                1 for e in penalisable
                if not e.direction_correct
                and e.miss_analysis.primary_miss_agent == agent
            )
            weighted_rate += wt * (agent_misses / len(penalisable))
            total_weight  += wt

        return round(weighted_rate / total_weight, 4) if total_weight > 0 else 0.0

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
        timing_lag_days: int = 0,
        seasonal_threshold_deltas: dict[str, float] | None = None,
        reference_date: date | None = None,
    ) -> dict[str, float]:
        """
        Compute raw weight delta per agent before bounds are applied.

        Three adjustment mechanisms:
        1. Hit-rate boost/penalty    — rolling accuracy vs seasonal-adjusted thresholds
        2. Bias penalty              — multi-window weighted miss rate (calendar-aware)
        3. Timing tolerance          — lag_days magnitude determines timing penalty scale
        """
        ref             = reference_date or date.today()
        deltas          = {a: 0.0 for a in agents}
        seasonal_deltas = seasonal_threshold_deltas or {}

        # Resolve timing penalty multiplier based on lag magnitude
        if todays_miss_type == "timing":
            abs_lag = abs(timing_lag_days)
            if abs_lag <= _TIMING_FREE_WINDOW:
                penalty_multiplier = 0.0     # within-week noise, no penalty
            elif abs_lag <= _TIMING_PARTIAL_WINDOW:
                penalty_multiplier = 0.20    # 4–7 td off: light signal
            else:
                penalty_multiplier = 0.50    # >7 td off: real timing failure
        else:
            penalty_multiplier = MISS_TYPE_PENALTY_MULTIPLIER.get(todays_miss_type, 1.0)

        for agent in agents:
            acc = accuracy.get(agent)
            if acc is None or acc.total == 0:
                continue

            hit_rate = acc.hit_rate()

            # Seasonal threshold shift — raises bar during easy periods,
            # lowers it during structurally hard ones (budget week, earnings)
            s_adj             = seasonal_deltas.get(agent, 0.0)
            effective_boost   = settings.WEIGHT_BOOST_HIT_RATE   + s_adj
            effective_penalty = settings.WEIGHT_PENALTY_HIT_RATE + s_adj

            if hit_rate >= effective_boost:
                deltas[agent] += _BOOST
            elif hit_rate <= effective_penalty:
                deltas[agent] += _PENALTY

            # Bias penalty — only for the blamed agent on penalisable misses
            if agent == todays_primary_miss and todays_miss_type not in NO_PENALTY_MISS_TYPES:
                bias_score = self._compute_bias_score(feedback_log, agent, ref)
                if bias_score >= _BIAS_TRIGGER:
                    scale         = min(1.0, (bias_score - _BIAS_TRIGGER)
                                            / (_BIAS_FULL - _BIAS_TRIGGER))
                    bias_penalty  = _MISS_STREAK_PENALTY * scale * penalty_multiplier
                    deltas[agent] += bias_penalty
                    if bias_penalty != 0.0:
                        logger.warning(
                            "[WeightAdapter] %s: bias_score=%.2f (type=%s, lag=%+d td) "
                            "→ bias Δ%.3f",
                            agent, bias_score, todays_miss_type,
                            timing_lag_days, bias_penalty,
                        )
                else:
                    logger.debug(
                        "[WeightAdapter] %s: bias_score=%.2f below trigger %.2f — no bias penalty",
                        agent, bias_score, _BIAS_TRIGGER,
                    )

        return deltas

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
        max_step  = bounds.get("max_single_step",           settings.WEIGHT_MAX_STEP)
        max_drift = bounds.get("max_total_drift_from_base", settings.WEIGHT_MAX_DRIFT)

        new_weights: dict[str, float] = {}
        for agent, w in current.items():
            delta    = deltas.get(agent, 0.0)
            delta    = max(-max_step, min(max_step, delta))   # clamp single-step size
            proposed = w + delta

            base_w   = base.get(agent, w)
            lo       = max(0.0, base_w - max_drift)           # floor: never below base − 0.15
            hi       = base_w + max_drift                     # ceiling: never above base + 0.15
            proposed = max(lo, min(hi, proposed))

            new_weights[agent] = round(proposed, 6)

        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}

        return new_weights
