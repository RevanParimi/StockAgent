"""
models/feedback_schemas.py
==========================
Pydantic v2 models for the RL Feedback / Adaptive Prediction Loop.

Four JSON memory structures:
  1. PredictionEnvelope   – 30-day forecast sheet (revised daily)
  2. DailyFeedbackLog     – actual vs predicted log with miss analysis
  3. WeightMemory         – earned agent weights + accuracy track record
  4. LearningLedger       – accumulated stock-specific pattern lessons

Applies to all four sector graphs:
  automobile · banking_bfsi · it_sector · renewable_energy

These models are used by:
  - tools/prediction_store.py  (serialise / deserialise JSON files)
  - agents/feedback_agent.py   (produce FeedbackEntry + lessons)
  - agents/weight_adapter.py   (read/write WeightMemory)
  - scripts/generate_forecast.py
  - scripts/daily_review.py
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. Prediction Envelope
# ---------------------------------------------------------------------------

class ConvictionStreak(BaseModel):
    """
    Tracks consecutive same-direction verdict runs for mean reversion detection (P3).

    The streak counts days where the envelope issues the same directional verdict
    (BULLISH = BUY/STRONG BUY, BEARISH = SELL/STRONG SELL).  NEUTRAL resets it.
    A growing streak increases reversion_prior, which dampens remaining forecast
    confidence to protect against riding a trend into a cliff edge.
    """
    current_verdict:   str   = ""    # last issued verdict ("BUY", "STRONG SELL", …)
    streak_days:       int   = 0     # consecutive days with same verdict direction
    streak_start_date: str   = ""    # ISO date when this streak began
    max_streak_seen:   int   = 0     # historical max for this ticker-cycle
    reversion_prior:   float = 0.0   # 0.0–0.30; updated daily by tracker.py


class DailyForecast(BaseModel):
    """One row in the 30-day prediction sheet."""
    day: int                                     # 1-indexed from cycle start
    date: str                                    # ISO date string "YYYY-MM-DD"
    predicted_close: float
    price_lower: float | None = None             # P10 Monte Carlo band (None when MC unavailable)
    price_upper: float | None = None             # P90 Monte Carlo band (None when MC unavailable)
    # predicted_change_pct removed — derivable as (predicted_close - base_close)/base_close*100.
    # Kept here for backward compat with existing envelope files; computed on write, not stored.
    predicted_change_pct: float = 0.0
    predicted_verdict: str                       # BUY | SELL | NEUTRAL etc.
    predicted_agent_scores: dict[str, float] = Field(default_factory=dict)
    # Per-agent sub-scores frozen at forecast time.
    # Stored so FeedbackAgent can see WHICH sub-dimension drifted, not just the composite.
    # e.g. {"fundamentals": {"revenue_growth": 0.72, "margin_vs_peers": 0.70, ...}}
    # Populated by generate_forecast.py when agent sub-scores are available.
    predicted_agent_subscores: dict[str, dict[str, float]] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    key_assumptions: list[str] = Field(default_factory=list)
    revised: bool = False                        # True after a daily review revises this row
    revision_count: int = 0
    predicted_agent_catalysts: dict[str, dict[str, str | float]] = Field(
        default_factory=dict,
        description="Agent catalyst predictions for this forecast day: {agent: {bull_case_if, bear_case_if, data_confidence}}"
    )


class PredictionEnvelope(BaseModel):
    """
    The living 30-day forecast for a single ticker + monthly cycle.
    Saved as: data/predictions/{sector}/{TICKER}/{TICKER}_{YYYY-MM}_prediction_envelope.json
    """
    ticker: str
    sector: str = "automobile"                   # which sector graph produced this
    cycle_id: str                                # e.g. "MARUTI_2026-04"
    generated_at: str                            # ISO datetime
    base_close: float                            # actual close on day-0
    weight_version_used: int = 0                 # which WeightMemory version was active
    # Forecast profile from PriceInterpolator — stored for hindsight timing evaluation.
    # "front_loaded" means early move was expected; "back_loaded" means catalyst is 2+ weeks out.
    forecast_profile_shape: str = "linear"
    forecast_profile_monthly_pct: float = 0.0
    forecast_profile_source: str = "static"      # "llm" or "static"
    daily_forecasts: list[DailyForecast] = Field(default_factory=list)
    conviction_streak: ConvictionStreak = Field(default_factory=ConvictionStreak)  # P3
    agent_predictions: dict[str, dict[str, str | float]] = Field(
        default_factory=dict,
        description="Per-agent catalyst snapshot at forecast time: {agent: {bull_case_if, bear_case_if, ticker_vs_peers, what_changed, data_confidence}}"
    )
    fno_snapshot: FnOSnapshot | None = None   # F&O chain snapshot at month-start (G7b)

    def get_forecast(self, target_date: str) -> DailyForecast | None:
        for f in self.daily_forecasts:
            if f.date == target_date:
                return f
        return None

    def remaining_forecasts(self, from_date: str) -> list[DailyForecast]:
        return [f for f in self.daily_forecasts if f.date > from_date]


# ---------------------------------------------------------------------------
# 2. Daily Feedback Log
# ---------------------------------------------------------------------------

Direction = Literal["UP", "DOWN", "FLAT"]

LessonCategory = Literal[
    "macro",            # domestic macro: RBI, FII, INR, repo rate
    "global_macro",     # cross-border macro: Fed, China PMI, crude shock, USD strength
    "technical",        # price patterns, RSI, MACD, support/resistance
    "sentiment",        # news tone, social media, management commentary
    "fundamental",      # earnings, margins, order book, promoter holding
    "seasonal",         # recurring calendar patterns (quarter-end, festive)
    "data_availability",# patterns about when data is/isn't published (e.g. FADA on 10th)
]

# ---------------------------------------------------------------------------
# Per-category base decay rates (confidence lost per month of inactivity).
#
# Design: categories with shorter market half-lives decay faster.
# BUT: as occurrences grow, any lesson becomes more "structural" — confirmed
# patterns deserve slower decay regardless of category.  The occurrence
# adjustment applies a sqrt-damping: rate × (1 / sqrt(occurrences)).
#
# Example — macro lesson seen 1×: 0.030/month
#           macro lesson seen 4×: 0.015/month  (confirmed; halved)
#           macro lesson seen 9×: 0.010/month  (well-established; near structural)
#
# Seasonal is always 0.0 (decay-exempt) — calendars don't change.
# ---------------------------------------------------------------------------
import math as _math

LESSON_DECAY_RATES: dict[str, float] = {
    "seasonal":          0.000,  # decay-exempt — repeats annually
    "data_availability": 0.005,  # data calendar rarely changes
    "fundamental":       0.008,  # earnings/business cycle patterns — slow
    "technical":         0.015,  # chart patterns shift with vol regime
    "sentiment":         0.020,  # sentiment half-life ~50 days
    "macro":             0.030,  # domestic macro regimes are transitional
    "global_macro":      0.040,  # global macro moves fastest
}

MissType = Literal[
    "data_gap",         # input data wasn't published/available at forecast time — zero penalty
    "data_stale",       # hardcoded/outdated data used (e.g. RBI rate not updated) — zero penalty
    "external_shock",   # unpredictable black-swan event — zero penalty
    "timing",           # direction correct but stock moved early/late vs predicted — half penalty
    "magnitude",        # direction correct but size of move was wrong — quarter penalty
    "model_bias",       # agent consistently over/under-estimates a specific signal — full penalty
    "direction_flip",   # completely wrong direction, no external excuse — full penalty
]

# Multiplier applied to the weight penalty based on miss type.
# Imported by WeightAdapter so the mapping lives in one place.
MISS_TYPE_PENALTY_MULTIPLIER: dict[str, float] = {
    "data_gap":       0.0,
    "data_stale":     0.0,
    "external_shock": 0.0,
    "timing":         0.5,
    "magnitude":      0.25,
    "model_bias":     1.0,
    "direction_flip": 1.0,
}

# Miss types that should NOT penalise the primary agent in accuracy tracking
NO_PENALTY_MISS_TYPES: frozenset[str] = frozenset({
    "data_gap", "data_stale", "external_shock"
})

# Miss types that represent a genuine model failure (vs. an unforeseeable/
# data-availability excuse). Used by both `LearningLedger.penalizable_miss_count`
# and `LearningLedger.recency_weighted_miss_scores` — single source of truth.
PENALIZABLE_MISS_TYPES: frozenset[str] = frozenset({
    "model_bias", "direction_flip"
})


class MissAnalysis(BaseModel):
    """Root-cause breakdown of a single day's prediction error."""
    primary_miss_agent: str
    miss_type: MissType = "direction_flip"                                # what kind of miss
    missed_factors: list[str] = Field(default_factory=list)               # real-world events not captured
    over_weighted_factors: list[str] = Field(default_factory=list)        # signals trusted too much
    # agent_score_drift: delta only (today_composite - predicted_composite per agent).
    # Positive = agent underestimated (bullish signal missed); Negative = overestimated.
    agent_score_drift: dict[str, float] = Field(default_factory=dict)
    # Sub-scores for the primary miss agent + agents with |drift| > 0.10.
    # "fundamentals drifted -0.07" is ambiguous; "fundamentals.revenue_growth: 0.75 → 0.42" is not.
    # Keys: agent_name → {sub_dim: predicted_value} and {sub_dim: actual_value}.
    # Only populated for significant drifters; empty for routine days.
    predicted_subscores_significant: dict[str, dict[str, float]] = Field(default_factory=dict)
    actual_subscores_significant: dict[str, dict[str, float]] = Field(default_factory=dict)


class TimingAccuracy(BaseModel):
    """Tracks whether a predicted move arrived on time, early, or late."""
    predicted_peak_day: int | None = None       # day in 30-day envelope where peak/trough was predicted
    actual_move_start_day: int | None = None    # day the actual move materialised
    lag_days: int | None = None                 # actual_start - predicted_peak (negative = early)
    assessment: Literal["early", "on_time", "late", "no_move"] = "on_time"


class RevisedContext(BaseModel):
    """Structured forward outlook replacing the previous single-sentence string."""
    headline: str = ""                                      # one-sentence summary of revision
    risks_next_7_days: list[str] = Field(default_factory=list)      # max 3 specific risks
    catalysts_next_7_days: list[str] = Field(default_factory=list)  # max 3 positive triggers
    watch_signals: list[str] = Field(default_factory=list)          # what to monitor
    horizon_confidence_adjustment: float = 0.0              # applied to remaining forecast confidence


class ThesisReview(BaseModel):
    """
    Output of ThesisReviewer — produced only on significant prediction misses.

    Triggered when |price_error_pct| > THESIS_REVIEW_THRESHOLD (2.0%) OR
    (direction_correct=False AND miss_type in {direction_flip, model_bias}).

    Tells the forecast revision step whether to treat the remaining 30-day
    thesis as intact (minor re-weighting only) or invalidated (confidence
    multiplier applied to ALL remaining forecasts, not just adjustment).
    """
    assumptions_invalidated: list[str] = Field(default_factory=list)
    assumptions_still_valid: list[str] = Field(default_factory=list)
    thesis_intact: bool = True
    revised_narrative: str = ""
    # Multiplied into every remaining forecast's confidence.
    # 1.0 = thesis intact, no extra discount.
    # 0.75 = one major assumption broken, 25% confidence haircut across the board.
    # 0.50 = core thesis invalidated, deep uncertainty ahead.
    horizon_confidence_multiplier: float = Field(ge=0.3, le=1.0, default=1.0)


class FeedbackEntry(BaseModel):
    """
    One day's entry in the feedback log.
    Appended daily by scripts/daily_review.py.
    """
    day: int
    date: str                              # ISO date string
    predicted_close: float
    actual_close: float
    price_error_pct: float                 # (actual - predicted) / predicted * 100
    predicted_verdict: str
    actual_direction: Direction            # UP | DOWN | FLAT (±ATR-relative threshold)
    direction_correct: bool
    # Per-agent composite scores frozen at forecast time (copied from the day's
    # DailyForecast.predicted_agent_scores). Enables per-agent calibration scoring
    # in WeightAdapter._compute_accuracy — was an agent's own lean (>=0.5 = bullish)
    # consistent with the realized direction, independent of the ensemble verdict?
    # Empty dict for entries written before this field existed (backward-compatible).
    predicted_agent_scores: dict[str, float] = Field(default_factory=dict)
    # Market regime active at time of review — critical for regime-stratified accuracy analysis.
    # Enables: "risk_macro is 71% accurate in NORMAL but only 44% in MACRO_CRISIS"
    regime_label: str = "NORMAL"
    # Today's volume relative to 20-day average.  >2.0 = institutional activity; <0.5 = noise.
    # Derived from yfinance volume data already fetched in Step 2; None if unavailable.
    volume_vs_20d_avg: float | None = None
    miss_analysis: MissAnalysis | None = None
    timing: TimingAccuracy | None = None                              # pickup/fall timing
    revised_context: RevisedContext | None = None                     # structured forward outlook
    thesis_review: ThesisReview | None = None                        # set only on significant misses
    lessons_generated: list[str] = Field(default_factory=list)       # lesson IDs added to ledger
    weight_adjustment_applied: str = ""    # e.g. "v4" — human audit reference
    # remaining_forecasts_revised removed — always True when entry is finalized.
    # The revision timestamp can be inferred from revised=True on DailyForecast rows.
    # feedback_agent_raw: stored to debug/ directory separately, not in main log.
    feedback_agent_raw: str = Field(default="", exclude=True)
    predicted_catalysts_snapshot: dict[str, dict[str, str | float]] = Field(
        default_factory=dict,
        description="Catalyst predictions from the forecast cycle, stored for audit trail alongside miss_analysis"
    )
    offmarket_context: str = ""   # previous day's off-market signals injected as LLM context


class DailyFeedbackLog(BaseModel):
    """
    All daily feedback entries for a single ticker + monthly cycle.
    Saved as: data/predictions/{sector}/{TICKER}/{TICKER}_{YYYY-MM}_daily_feedback_log.json
    """
    ticker: str
    sector: str = "automobile"
    cycle_id: str
    entries: list[FeedbackEntry] = Field(default_factory=list)

    def get_entry(self, target_date: str) -> FeedbackEntry | None:
        for e in self.entries:
            if e.date == target_date:
                return e
        return None

    def direction_hit_rate(self, last_n: int = 7) -> float:
        """Fraction of recent entries where direction_correct is True."""
        recent = self.entries[-last_n:]
        if not recent:
            return 0.5
        return sum(1 for e in recent if e.direction_correct) / len(recent)


# ---------------------------------------------------------------------------
# 3. Weight Memory
# ---------------------------------------------------------------------------

class MonthlyAccuracySnapshot(BaseModel):
    """
    One month's accuracy summary for a single agent.
    Stored in a rolling 12-entry deque in AgentAccuracy.monthly_snapshot_history.
    Enables the base-weight recalibration LLM to see a trend, not just today's number.
    """
    month: str                   # "YYYY-MM"
    hit_rate: float              # direction hits / total for that month
    total: int                   # total evaluated days in that month
    dominant_regime: str = "NORMAL"   # most frequent regime label in that month


class AgentAccuracy(BaseModel):
    """Rolling accuracy record for one sub-agent."""
    direction_hits: int = 0       # correct direction calls in the current rolling window
    total: int = 0                # total days evaluated in the current rolling window
    avg_error: float = 0.0        # mean absolute price_error_pct (agent sub-score drift)
    # Per-agent calibration record (RL Intelligence Phase, Component 2).
    # calibration_hits: days where this agent's own predicted_agent_scores[agent] lean
    #   (>=AGENT_BULLISH_THRESHOLD = bullish) matched the realized direction.
    # calibration_total: denominator for calibration_hits — excludes NEUTRAL-verdict
    #   days (no directional claim was made) and days with no recorded agent score.
    # Both default to 0 so existing WeightMemory JSON files load unchanged.
    calibration_hits: int = 0
    calibration_total: int = 0
    # Rolling 12-month snapshot history (evict oldest at month-13).
    # Gives the recalibration LLM a trend series: was this agent improving or degrading?
    monthly_snapshot_history: list[MonthlyAccuracySnapshot] = Field(default_factory=list)

    def direction_hit_rate(self) -> float:
        return self.direction_hits / self.total if self.total > 0 else 0.5

    def calibration_hit_rate(self) -> float:
        return self.calibration_hits / self.calibration_total if self.calibration_total > 0 else 0.5

    def hit_rate(self) -> float:
        """
        Hit rate that drives WeightAdapter boost/penalty decisions.

        When RL_CALIBRATION_REWARD_ENABLED is True and this agent has at least one
        non-NEUTRAL calibration observation, blends ensemble-direction accuracy with
        the agent's own calibration accuracy:

            hit_rate = (1 - w) * direction_hit_rate + w * calibration_hit_rate
            w = RL_CALIBRATION_WEIGHT

        When the flag is False (or there is no calibration data), returns the
        pre-existing direction_hit_rate unchanged — byte-identical to prior behavior.
        """
        direction_rate = self.direction_hit_rate()

        # Late import: lets tests monkeypatch settings per-call and avoids any
        # import-order coupling between the schema module and config.
        from core.config import settings

        calibration_enabled = getattr(settings, "RL_CALIBRATION_REWARD_ENABLED", True)
        if not calibration_enabled or self.calibration_total == 0:
            return direction_rate

        weight = getattr(settings, "RL_CALIBRATION_WEIGHT", 0.5)
        return (1 - weight) * direction_rate + weight * self.calibration_hit_rate()

    def lifetime_hit_rate(self) -> float:
        """Compute cumulative hit rate across all stored monthly snapshots."""
        if not self.monthly_snapshot_history:
            # Monthly snapshots (MonthlyAccuracySnapshot.hit_rate) are direction-only
            # by definition, so the empty-history fallback must use the direction-only
            # rate too — not the calibration-blended hit_rate() — to keep both
            # branches of this method in the same units.
            return self.direction_hit_rate()
        total_hits = sum(s.hit_rate * s.total for s in self.monthly_snapshot_history)
        total_days = sum(s.total for s in self.monthly_snapshot_history)
        return round(total_hits / total_days, 4) if total_days > 0 else 0.5


class WeightHistoryEntry(BaseModel):
    """One versioned snapshot of weights with the reason for the change."""
    version: int
    date: str                     # ISO date
    weights: dict[str, float]
    reason: str                   # human-readable text explanation
    # Structured delta applied at this version — parseable without string splitting.
    # e.g. {"risk_macro": +0.02, "sales_demand": -0.03}
    deltas: dict[str, float] = Field(default_factory=dict)
    # Hit rates that triggered this weight update, per agent.
    # e.g. {"risk_macro": 0.857, "sales_demand": 0.429}
    accuracy_snapshot: dict[str, float] = Field(default_factory=dict)
    # Market regime active at time of weight update.
    regime_at_update: str = "NORMAL"


class WeightMemory(BaseModel):
    """
    Per-ticker adaptive weight state.  Persists across monthly cycles.
    Saved as: data/predictions/{sector}/{TICKER}/{TICKER}_agent_weight_memory.json
    """
    ticker: str
    sector: str = "automobile"
    last_updated: str             # ISO date
    weight_version: int = 0
    current_weights: dict[str, float]
    base_weights: dict[str, float]    # original config defaults — never mutated
    # adjustment_bounds removed from JSON — these are settings constants, not per-ticker data.
    # Read from settings.WEIGHT_MAX_STEP and settings.WEIGHT_MAX_DRIFT at runtime.
    # Kept here as a deprecated field for backward compatibility with existing JSON files.
    adjustment_bounds: dict[str, float] = Field(
        default_factory=lambda: {"max_single_step": 0.05, "max_total_drift_from_base": 0.15}
    )
    agent_accuracy: dict[str, AgentAccuracy] = Field(default_factory=dict)
    weight_history: list[WeightHistoryEntry] = Field(default_factory=list)
    # Per-regime accuracy breakdown — updated at month rollover by scanning FeedbackLog.
    # Enables: "risk_macro hits 71% in NORMAL but 44% in MACRO_CRISIS → multiplier needs adjustment"
    # Schema: {regime_label: {agent_name: AgentAccuracy}}
    regime_accuracy: dict[str, dict[str, AgentAccuracy]] = Field(default_factory=dict)

    def effective_weights(self) -> dict[str, float]:
        """Return current_weights normalised to sum exactly to 1.0."""
        total = sum(self.current_weights.values())
        if total == 0:
            return self.base_weights.copy()
        return {k: round(v / total, 6) for k, v in self.current_weights.items()}

    def weight_drift_summary(self) -> str:
        """
        One-line summary of how far each agent has drifted from base.
        Injected into FeedbackAgentInput.weight_drift_summary.
        Example: "risk_macro +0.06 (base 0.13→current 0.19); sales_demand -0.04"
        """
        drifts = []
        for agent, current in self.current_weights.items():
            base = self.base_weights.get(agent, current)
            delta = current - base
            if abs(delta) >= 0.01:
                drifts.append(f"{agent} {delta:+.2f} (base {base:.2f} -> {current:.2f})")
        return "; ".join(drifts) if drifts else "No significant weight drift from base."


# ---------------------------------------------------------------------------
# 4. Learning Ledger
# ---------------------------------------------------------------------------

LessonScope = Literal[
    "stock_specific",   # only applies to this one ticker
    "sector_wide",      # applies to all stocks in the same sector
    "market_wide",      # applies regardless of sector (global macro, broad market events)
]


class Lesson(BaseModel):
    """One accumulated pattern lesson for a specific stock."""
    lesson_id: str                         # e.g. "L001"
    date_learned: str                      # ISO date first observed
    category: LessonCategory
    pattern: str                           # short machine-readable key e.g. "RBI_policy_day"
    observation: str                       # human-readable: what was observed
    # rule should express INTENT, not a numeric delta.
    # Good: "Prioritise risk_macro over fundamentals on RBI event days — macro dominates."
    # Bad:  "Boost risk_macro by +0.05 when RBI event detected."  ← delta goes stale as weights evolve
    rule: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    occurrences: int = 1
    still_valid: bool = True
    scope: LessonScope = "stock_specific"  # how broadly this lesson applies
    last_seen: str = ""                    # ISO date last reinforced (empty = use date_learned)
    contributing_tickers: list[str] = Field(default_factory=list)
    # Semantic tags for deduplication beyond exact pattern-string matching.
    # Two lessons "RBI_policy_day" and "RBI_surprise_hold" share tag "central_bank_event"
    # and will be merged by the monthly ledger consolidator.
    # Controlled vocabulary: central_bank_event, fii_flow, crude_price, currency,
    # earnings_miss, sector_policy, technical_pattern, seasonal, credit_event,
    # supply_chain, regulatory + sector=<name> qualifier
    semantic_tags: list[str] = Field(default_factory=list)
    # How many consecutive cycles contradicted this lesson before invalidation.
    # invalidation_streak >= 3 → still_valid = False. Allows "degrading" state:
    # streak=0: healthy, streak=1: warn, streak=2: critical, streak=3: invalidated.
    invalidation_streak: int = 0
    # Populated when still_valid is set to False — preserves the reason for audit.
    invalidation_reason: str = ""
    invalidation_date: str = ""


class MissEvent(BaseModel):
    """
    One recorded instance of a missed factor.
    Replaces the raw miss_counter dict with structured, queryable events.

    Why structured: PromptEnhancer should only generate search queries for
    penalizable misses (model_bias, direction_flip).  External_shock misses
    don't need better data — they're unforeseeable.  The old dict[str, int]
    couldn't distinguish between 5× model_bias and 5× external_shock.
    """
    date: str            # ISO date of the miss
    miss_type: str       # "model_bias", "direction_flip", "external_shock", etc.
    cycle_id: str        # which monthly cycle this occurred in


class LearningLedger(BaseModel):
    """
    All accumulated lessons for a ticker.  Persists across monthly cycles.
    Saved as: data/predictions/{sector}/{TICKER}/{TICKER}_learning_ledger.json
    """
    ticker: str
    sector: str = "automobile"
    last_updated: str
    lessons: list[Lesson] = Field(default_factory=list)
    # miss_counter: legacy raw dict preserved for backward compatibility.
    # New code should use miss_events for structured access.
    miss_counter: dict[str, int] = Field(default_factory=dict)
    # Structured miss history — replaces the raw count dict.
    # {factor_name: [MissEvent, ...]} — last 12 events per factor (evict oldest).
    # PromptEnhancer reads this to skip external_shock misses when generating queries.
    miss_events: dict[str, list[MissEvent]] = Field(default_factory=dict)
    # How many times an active lesson matched today's market context AND direction was correct.
    # Approximate "lesson effectiveness" = correction_counter[factor] / (correction_counter + miss_count)
    # Updated by daily_review when direction_correct=True AND lesson pattern in market_context.
    correction_counter: dict[str, int] = Field(default_factory=dict)
    # Deprecated — per-category decay rates from LESSON_DECAY_RATES are used instead.
    # Kept for backward compatibility with existing ledger files.
    confidence_decay_rate: float = 0.02

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        for lesson in self.lessons:
            if lesson.lesson_id == lesson_id:
                return lesson
        return None

    def find_by_pattern(self, pattern: str) -> Lesson | None:
        for lesson in self.lessons:
            if lesson.pattern == pattern and lesson.still_valid:
                return lesson
        return None

    def find_by_semantic_overlap(self, tags: list[str], min_overlap: int = 2) -> "Lesson | None":
        """
        Find an existing lesson that shares at least min_overlap semantic tags.
        Used by ledger_propagator for semantic deduplication beyond exact pattern matching.
        """
        if not tags:
            return None
        tag_set = set(tags)
        best: "Lesson | None" = None
        best_overlap = 0
        for lesson in self.lessons:
            if not lesson.still_valid or not lesson.semantic_tags:
                continue
            overlap = len(tag_set & set(lesson.semantic_tags))
            if overlap >= min_overlap and overlap > best_overlap:
                best_overlap = overlap
                best = lesson
        return best

    def next_lesson_id(self) -> str:
        return f"L{len(self.lessons) + 1:03d}"

    def penalizable_miss_count(self, factor: str) -> int:
        """Count of misses for this factor with penalizable miss types (model_bias, direction_flip)."""
        events = self.miss_events.get(factor, [])
        return sum(1 for e in events if e.miss_type in PENALIZABLE_MISS_TYPES)

    def add_miss_event(self, factor: str, miss_type: str, date: str, cycle_id: str) -> None:
        """Record a miss event and keep the raw miss_counter in sync."""
        event = MissEvent(date=date, miss_type=miss_type, cycle_id=cycle_id)
        events = self.miss_events.setdefault(factor, [])
        events.append(event)
        if len(events) > 12:
            self.miss_events[factor] = events[-12:]  # keep last 12
        self.miss_counter[factor] = self.miss_counter.get(factor, 0) + 1

    def increment_miss(self, factor: str) -> None:
        """Legacy method — use add_miss_event for new code."""
        self.miss_counter[factor] = self.miss_counter.get(factor, 0) + 1

    def recency_weighted_miss_scores(self) -> dict[str, float]:
        """
        Recency-weighted miss scores per factor (RL Intelligence Phase, Component 3).

        score(factor) = sum over events in miss_events[factor] of:
            exp(-age_days / MISS_RECENCY_HALFLIFE_DAYS)
            x (1.0 if event.miss_type in PENALIZABLE_MISS_TYPES else MISS_PENALIZABLE_DISCOUNT)

        where age_days = (today - event.date).days, floored at 0.

        Recent misses dominate; non-penalizable miss types (e.g. external_shock,
        data_gap) are discounted since they don't reflect a model failure that
        better search data could fix.

        Falls back to {factor: float(miss_counter[factor])} for any factor with
        no entries in miss_events (legacy ledgers / factors only ever recorded
        via the deprecated increment_miss path).

        Behind settings.RL_FORGETTING_ENABLED — when the flag is False, callers
        should use raw miss_counter ranking instead (this method is still safe
        to call but callers gate on the flag, not this method).
        """
        from core.config import settings

        halflife = getattr(settings, "MISS_RECENCY_HALFLIFE_DAYS", 21)
        discount = getattr(settings, "MISS_PENALIZABLE_DISCOUNT", 0.3)
        today = date.today()

        scores: dict[str, float] = {}

        for factor, count in self.miss_counter.items():
            events = self.miss_events.get(factor)
            if not events:
                # Legacy fallback: no structured history for this factor.
                scores[factor] = float(count)
                continue

            total = 0.0
            for event in events:
                try:
                    event_date = date.fromisoformat(event.date)
                    age_days = max((today - event_date).days, 0)
                except ValueError:
                    age_days = 0
                recency_weight = _math.exp(-age_days / halflife) if halflife > 0 else 1.0
                type_weight = 1.0 if event.miss_type in PENALIZABLE_MISS_TYPES else discount
                total += recency_weight * type_weight
            scores[factor] = total

        # Factors that only ever appear in miss_events (shouldn't normally
        # happen since add_miss_event keeps miss_counter in sync, but guard
        # for safety/consistency).
        for factor, events in self.miss_events.items():
            if factor in scores or not events:
                continue
            total = 0.0
            for event in events:
                try:
                    event_date = date.fromisoformat(event.date)
                    age_days = max((today - event_date).days, 0)
                except ValueError:
                    age_days = 0
                recency_weight = _math.exp(-age_days / halflife) if halflife > 0 else 1.0
                type_weight = 1.0 if event.miss_type in PENALIZABLE_MISS_TYPES else discount
                total += recency_weight * type_weight
            scores[factor] = total

        return scores

    def effective_confidence(self, lesson: Lesson) -> float:
        """
        Apply recency decay to confidence.

        Decay rate is determined in priority order:
          1. Seasonal category → always 0.0 (decay-exempt).
          2. Per-category base rate from LESSON_DECAY_RATES.
          3. Occurrence damping: rate × (1 / sqrt(occurrences)).
             A macro lesson confirmed 9 times decays at 0.010/month, not 0.030.
             This reflects that repeated confirmation makes a pattern structural.
          4. Fallback: self.confidence_decay_rate (legacy 0.02 default).

        Floor = 0.10 — lessons are never fully discarded automatically.
        """
        # 1. Seasonal — exempt
        if lesson.category == "seasonal":
            return lesson.confidence

        # 2. Category base rate
        base_rate = LESSON_DECAY_RATES.get(lesson.category, self.confidence_decay_rate)

        # 3. Occurrence damping: the more times a pattern is confirmed, the more
        #    structural it becomes.  sqrt(n) gives diminishing returns so a single
        #    extra confirmation doesn't collapse the rate.
        occ = max(1, lesson.occurrences)
        effective_rate = base_rate / _math.sqrt(occ)
        effective_rate = max(0.002, effective_rate)   # floor: never fully static for non-seasonal

        ref_date_str = lesson.last_seen or lesson.date_learned
        if not ref_date_str:
            return lesson.confidence
        try:
            ref   = date.fromisoformat(ref_date_str)
            today = date.today()
            months_inactive = (today.year - ref.year) * 12 + (today.month - ref.month)
            months_inactive += (today.day - ref.day) / 30.0
            months_inactive  = max(months_inactive, 0.0)
        except ValueError:
            return lesson.confidence

        decayed = lesson.confidence * ((1.0 - effective_rate) ** months_inactive)
        return round(max(decayed, 0.10), 4)

    def active_lessons_summary(self) -> str:
        """
        Compact text injected into the FeedbackAgent prompt.
        Filters out nearly-stale lessons (eff_confidence < 0.20) and sorts
        by effective confidence descending so the LLM sees the most reliable,
        recent patterns first.
        """
        _min_eff = 0.20
        active = [
            l for l in self.lessons
            if l.still_valid and self.effective_confidence(l) >= _min_eff
        ]
        if not active:
            return "No lessons learned yet."
        active.sort(key=lambda l: self.effective_confidence(l), reverse=True)
        today = date.today()
        lines = []
        for l in active:
            ref_str = l.last_seen or l.date_learned or ""
            try:
                days_ago = (today - date.fromisoformat(ref_str)).days
            except Exception:
                days_ago = -1
            age = f"{days_ago}d ago" if days_ago >= 0 else "?"
            lines.append(
                f"{l.lesson_id} [{l.category}|{l.scope}] {l.pattern}: {l.rule} "
                f"(eff_confidence={self.effective_confidence(l):.2f}, seen={l.occurrences}x, last={age})"
            )
        return "\n".join(lines)

    def increment_miss(self, factor: str) -> None:
        self.miss_counter[factor] = self.miss_counter.get(factor, 0) + 1


# ---------------------------------------------------------------------------
# Feedback Agent I/O contracts
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Seasonal Calendar models
# ---------------------------------------------------------------------------

class SeasonalPattern(BaseModel):
    """
    One pre-seeded seasonal pattern loaded from a YAML seed file.

    agent_adjustments contains signed deltas applied on top of live agent scores.
    Positive = boost the agent's influence; Negative = discount it.
    Deltas are intentionally small (±0.04 to ±0.10) — they shift emphasis,
    not override the agent's actual analysis.
    """
    id: str
    name: str
    evidence: str                               # source data backing this pattern
    months: list[int]                           # 1=Jan … 12=Dec
    day_range: list[int] | None = None          # [start_day, end_day] inclusive; None = whole month
    direction_bias: str                         # documentation only — not used computationally
    confidence: float = Field(ge=0.0, le=1.0)
    agents_affected: dict[str, float]           # agent_name → delta (−0.20 … +0.20)
    narrative: str                              # one-sentence context injected into FeedbackAgent
    scope: LessonScope = "sector_wide"
    validated_by_rl: bool = False               # True once RL confirms ≥2 cycles
    decay_exempt: bool = True                   # seasonal patterns don't decay (Decembers always happen)
    lunar_dependency: bool = False              # if True, apply 0.5× delta (Gregorian date uncertainty)
    # Per-agent boost/penalty threshold shifts for WeightAdapter during this period.
    # Positive = raise the bar (agent expected to perform well → harder to earn boost).
    # Negative = lower the bar (structurally hard period → more forgiving on penalty).
    # e.g. festive season: {"sales_demand": +0.08}  budget week: {"fundamentals": -0.05}
    accuracy_threshold_delta: dict[str, float] = Field(default_factory=dict)
    # F&O expiry week patterns cannot use month/day_range (expiry date is dynamic).
    # When True, _is_active() skips this pattern; _get_fno_expiry_context() handles it instead.
    fno_week_only: bool = False


class SeasonalContext(BaseModel):
    """
    Output of SeasonalCalendar.get_context() for a specific date.
    Consumed by generate_forecast.py (per-day adjustment) and
    daily_review.py (narrative injection into FeedbackAgent prompt).
    """
    target_date: date
    active_pattern_ids: list[str] = Field(default_factory=list)
    active_rl_lesson_ids: list[str] = Field(default_factory=list)
    # Merged signed deltas to apply to predicted_agent_scores.
    # Multiple patterns are summed; capped at ±0.20 per agent.
    agent_adjustments: dict[str, float] = Field(default_factory=dict)
    narrative: str = ""                         # injected into FeedbackAgent market_context_today
    confidence_modifier: float = 0.0           # added to base forecast confidence; capped ±0.10
    is_seasonal_period: bool = False
    # Aggregated threshold deltas from all active SeasonalPatterns for this date.
    # Passed to WeightAdapter.update() as seasonal_threshold_deltas.
    accuracy_threshold_delta: dict[str, float] = Field(default_factory=dict)


class FeedbackAgentInput(BaseModel):
    """Structured payload passed to the FeedbackAgent LLM."""
    ticker: str
    sector: str = "automobile"              # drives sector-aware system prompt
    date: str
    predicted_close: float
    actual_close: float
    price_error_pct: float
    direction_correct: bool
    predicted_agent_scores: dict[str, float]
    todays_agent_scores: dict[str, float]
    market_context_today: str
    key_assumptions_made: list[str]
    active_lessons_summary: str
    # --- New context fields that close the gap between stored data and LLM analysis ---
    # Sub-scores for agents with |drift| > 0.10, injected when available.
    # Format: {agent: {sub_dim: {"predicted": float, "actual": float}}}
    # Gives LLM specific sub-dimension signal instead of just composite drift.
    # Example: {"fundamentals": {"revenue_growth": {"predicted": 0.72, "actual": 0.42}}}
    significant_subscore_drift: dict[str, dict[str, dict[str, float]]] = Field(
        default_factory=dict
    )
    # Summary of weight drift from base — tells LLM which agents have earned trust over time.
    # Example: "risk_macro +0.06 (base 0.13→current 0.19); sales_demand -0.04"
    weight_drift_summary: str = ""
    # Recent accuracy trend for the primary candidate agents (computed in daily_review).
    # Example: "risk_macro: 5/7 this week, 4/7 last week, 6/7 two weeks ago"
    recent_accuracy_trend: str = ""
    # Watch signals from yesterday's revised_context — closes the monitoring loop.
    # LLM is told: "You flagged these for monitoring yesterday. Did any of them materialise?"
    previous_watch_signals: list[str] = Field(default_factory=list)
    # Volume context — injected only when volume_vs_20d_avg is available.
    # "Today's volume was 2.8× the 20-day average — institutional-scale activity."
    volume_context: str = ""
    # Forecast profile shape from PriceInterpolator — needed for timing accuracy assessment.
    # "The forecast was front_loaded (60% of expected move in first 10 days)."
    forecast_profile_context: str = ""
    predicted_catalysts_by_agent: dict[str, dict[str, str | float]] = Field(
        default_factory=dict,
        description="Predicted bull/bear catalysts per agent from the envelope, for FeedbackAgent to compare against actual outcome"
    )


class RawLesson(BaseModel):
    """Lesson as returned raw by the FeedbackAgent LLM (before deduplication)."""
    category: LessonCategory
    pattern: str
    observation: str
    rule: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    scope: LessonScope = "stock_specific"   # LLM declares the scope


class FeedbackAgentOutput(BaseModel):
    """Structured output the FeedbackAgent LLM must return."""
    primary_miss_agent: str
    miss_type: MissType = "direction_flip"
    missed_factors: list[str] = Field(default_factory=list)
    over_weighted_factors: list[str] = Field(default_factory=list)
    agent_score_drift: dict[str, float] = Field(default_factory=dict)
    new_lessons: list[RawLesson] = Field(default_factory=list)
    revised_context: RevisedContext = Field(default_factory=RevisedContext)


# ---------------------------------------------------------------------------
# P5 — Regime Snapshot
# ---------------------------------------------------------------------------

class RegimeSnapshot(BaseModel):
    """
    Output of RegimeDetector.detect() for a specific date.
    Ephemeral — used only for the daily weight modifier computation.
    Not written to weight_memory.json.
    """
    regime_label: str = "NORMAL"           # one of 6 labels: MACRO_CRISIS, RISK_OFF, NORMAL, RISK_ON, MOMENTUM_EXTENDED, OVERSOLD
    vix_value: float = 17.0
    fii_proxy_5d_pct: float = 0.0          # Nifty 50 5-day return % (proxy for FII direction)
    sector_rsi: float = 50.0
    multipliers: dict[str, float] = Field(default_factory=dict)   # per-agent regime multipliers
    narrative: str = ""                    # one-sentence context for LLM injection
    as_of_date: str = ""                   # ISO date


# ---------------------------------------------------------------------------
# G4 — Off-Market Signals (block deals, bulk deals, pre-open auction)
# ---------------------------------------------------------------------------

class BlockDeal(BaseModel):
    """SEBI block deal: ≥500,000 shares OR ≥₹10Cr, executed in the 9:15-9:50am window."""
    symbol: str
    client_name: str
    trade_type: Literal["BUY", "SELL"]
    quantity: int
    price: float
    trade_value_cr: float   # quantity × price / 1e7


class BulkDeal(BaseModel):
    """SEBI bulk deal: single-day quantity > 0.5% of company's equity. Reported by day-end."""
    symbol: str
    client_name: str
    trade_type: Literal["BUY", "SELL"]
    quantity: int
    price: float
    trade_value_cr: float


class OffMarketSignals(BaseModel):
    """
    Off-market institutional signals for a ticker on a given date.
    Fetched at end of daily_review day T; injected at start of day T+1.
    """
    date: str          # ISO date this data was fetched for
    ticker: str
    block_deals: list[BlockDeal] = Field(default_factory=list)
    bulk_deals: list[BulkDeal] = Field(default_factory=list)
    pre_open_price: float | None = None
    pre_open_vs_prev_close_pct: float | None = None   # gap % (pre_open - prev_close)/prev_close*100
    pre_open_volume: int | None = None
    net_institutional_direction: Literal["BUY", "SELL", "MIXED", "NONE"] = "NONE"
    total_trade_value_cr: float = 0.0
    summary: str = ""


# ---------------------------------------------------------------------------
# G7b — F&O Chain Snapshot
# ---------------------------------------------------------------------------

class FnOSnapshot(BaseModel):
    """
    NSE options chain snapshot for a ticker at month-start.
    Stored in PredictionEnvelope; injected as context during F&O expiry week.
    """
    date: str
    ticker: str
    pcr: float | None = None                     # Put-Call Ratio (OI-based)
    max_pain_price: float | None = None           # strike minimising option buyer payoff
    oi_buildup_direction: Literal["LONG", "SHORT", "NEUTRAL"] | None = None
    atm_strike: float | None = None               # nearest strike to current price
    near_month_expiry: str | None = None          # "YYYY-MM-DD"
    total_call_oi: int | None = None
    total_put_oi: int | None = None
    current_price: float | None = None
    max_pain_deviation_pct: float | None = None   # (current_price - max_pain) / current_price * 100
    source: str = "nse_api"

    def to_context_string(self) -> str:
        if self.pcr is None:
            return ""
        lines = [f"[F&O SNAPSHOT — {self.date}]"]
        pcr_signal = (
            "bearish (heavy put writing)" if (self.pcr or 0) > 1.5
            else ("bullish (heavy call writing)" if (self.pcr or 0) < 0.7 else "neutral")
        )
        lines.append(f"  PCR: {self.pcr:.2f} → {pcr_signal}")
        if self.max_pain_price and self.current_price:
            lines.append(
                f"  Max Pain: ₹{self.max_pain_price:.0f} "
                f"(current: ₹{self.current_price:.0f}, "
                f"deviation: {self.max_pain_deviation_pct or 0:+.1f}%)"
            )
        lines.append(f"  OI Buildup: {self.oi_buildup_direction}")
        return "\n".join(lines)
