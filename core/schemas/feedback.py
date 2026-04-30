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

class DailyForecast(BaseModel):
    """One row in the 30-day prediction sheet."""
    day: int                                     # 1-indexed from cycle start
    date: str                                    # ISO date string "YYYY-MM-DD"
    predicted_close: float
    predicted_change_pct: float                  # % change from base_close
    predicted_verdict: str                       # BUY | SELL | NEUTRAL etc.
    predicted_agent_scores: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    key_assumptions: list[str] = Field(default_factory=list)
    revised: bool = False                        # True after a daily review revises this row
    revision_count: int = 0


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
    daily_forecasts: list[DailyForecast] = Field(default_factory=list)

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


class MissAnalysis(BaseModel):
    """Root-cause breakdown of a single day's prediction error."""
    primary_miss_agent: str
    miss_type: MissType = "direction_flip"                                # what kind of miss
    missed_factors: list[str] = Field(default_factory=list)               # real-world events not captured
    over_weighted_factors: list[str] = Field(default_factory=list)        # signals trusted too much
    agent_score_drift: dict[str, float] = Field(default_factory=dict)     # today re-run vs predicted


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
    actual_direction: Direction            # UP | DOWN | FLAT (±0.3% threshold)
    direction_correct: bool
    miss_analysis: MissAnalysis | None = None
    timing: TimingAccuracy | None = None                              # pickup/fall timing
    revised_context: RevisedContext | None = None                     # structured forward outlook
    lessons_generated: list[str] = Field(default_factory=list)       # lesson IDs added to ledger
    weight_adjustment_applied: str = ""    # e.g. "v4" — which weight version was written
    remaining_forecasts_revised: bool = False
    feedback_agent_raw: str = Field(default="", exclude=True)        # raw LLM output, not serialised


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

class AgentAccuracy(BaseModel):
    """Rolling accuracy record for one sub-agent."""
    direction_hits: int = 0       # correct direction calls (excluding no-penalty misses)
    total: int = 0                # total evaluated days
    avg_error: float = 0.0        # mean absolute price_error_pct (agent sub-score drift)

    def hit_rate(self) -> float:
        return self.direction_hits / self.total if self.total > 0 else 0.5


class WeightHistoryEntry(BaseModel):
    """One versioned snapshot of weights with the reason for the change."""
    version: int
    date: str                     # ISO date
    weights: dict[str, float]
    reason: str


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
    adjustment_bounds: dict[str, float] = Field(
        default_factory=lambda: {"max_single_step": 0.05, "max_total_drift_from_base": 0.15}
    )
    agent_accuracy: dict[str, AgentAccuracy] = Field(default_factory=dict)
    weight_history: list[WeightHistoryEntry] = Field(default_factory=list)

    def effective_weights(self) -> dict[str, float]:
        """Return current_weights normalised to sum exactly to 1.0."""
        total = sum(self.current_weights.values())
        if total == 0:
            return self.base_weights.copy()
        return {k: round(v / total, 6) for k, v in self.current_weights.items()}


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
    rule: str                              # actionable rule applied during forecasts
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    occurrences: int = 1
    still_valid: bool = True
    scope: LessonScope = "stock_specific"  # how broadly this lesson applies
    last_seen: str = ""                    # ISO date last reinforced (empty = use date_learned)


class LearningLedger(BaseModel):
    """
    All accumulated lessons for a ticker.  Persists across monthly cycles.
    Saved as: data/predictions/{sector}/{TICKER}/{TICKER}_learning_ledger.json
    """
    ticker: str
    sector: str = "automobile"
    last_updated: str
    lessons: list[Lesson] = Field(default_factory=list)
    miss_counter: dict[str, int] = Field(default_factory=dict)    # factor → miss count
    confidence_decay_rate: float = 0.02    # confidence lost per month of inactivity

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

    def next_lesson_id(self) -> str:
        return f"L{len(self.lessons) + 1:03d}"

    def effective_confidence(self, lesson: Lesson) -> float:
        """
        Apply recency decay to confidence.
        A lesson unseen for N months loses confidence_decay_rate * N of its confidence.
        Floor is 0.10 — lessons are never fully discarded automatically.
        """
        ref_date_str = lesson.last_seen or lesson.date_learned
        if not ref_date_str:
            return lesson.confidence
        try:
            months_inactive = (date.today() - date.fromisoformat(ref_date_str)).days / 30.0
        except ValueError:
            return lesson.confidence
        decayed = lesson.confidence * ((1.0 - self.confidence_decay_rate) ** months_inactive)
        return round(max(decayed, 0.10), 4)

    def active_lessons_summary(self) -> str:
        """
        Compact text injected into the FeedbackAgent prompt.
        Uses effective (decay-adjusted) confidence so the LLM naturally
        weights recent patterns higher than stale ones.
        """
        active = [l for l in self.lessons if l.still_valid]
        if not active:
            return "No lessons learned yet."
        lines = [
            f"{l.lesson_id} [{l.category}|{l.scope}] {l.pattern}: {l.rule} "
            f"(eff_confidence={self.effective_confidence(l):.2f}, seen={l.occurrences}x)"
            for l in active
        ]
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
