"""
models/feedback_schemas.py
==========================
Pydantic v2 models for the RL Feedback / Adaptive Prediction Loop.

Four JSON memory structures:
  1. PredictionEnvelope   – 30-day forecast sheet (revised daily)
  2. DailyFeedbackLog     – actual vs predicted log with miss analysis
  3. WeightMemory         – earned agent weights + accuracy track record
  4. LearningLedger       – accumulated stock-specific pattern lessons

These models are used by:
  - tools/prediction_store.py  (serialise / deserialise JSON files)
  - agents/feedback_agent.py   (produce FeedbackEntry + lessons)
  - agents/weight_adapter.py   (read/write WeightMemory)
  - scripts/generate_forecast.py
  - scripts/daily_review.py
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. Prediction Envelope
# ---------------------------------------------------------------------------

class DailyForecast(BaseModel):
    """One row in the 30-day prediction sheet."""
    day: int                                    # 1-indexed from cycle start
    date: str                                   # ISO date string "YYYY-MM-DD"
    predicted_close: float
    predicted_change_pct: float                 # % change from base_close
    predicted_verdict: str                      # BUY | SELL | NEUTRAL etc.
    predicted_agent_scores: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    key_assumptions: list[str] = Field(default_factory=list)
    revised: bool = False                       # True after a daily review revises this row
    revision_count: int = 0


class PredictionEnvelope(BaseModel):
    """
    The living 30-day forecast for a single ticker + monthly cycle.
    Saved as: data/predictions/{TICKER}/{TICKER}_{YYYY-MM}_prediction_envelope.json
    """
    ticker: str
    cycle_id: str                               # e.g. "MARUTI_2026-04"
    generated_at: str                           # ISO datetime
    base_close: float                           # actual close on day-0
    weight_version_used: int = 0                # which WeightMemory version was active
    daily_forecasts: list[DailyForecast] = Field(default_factory=list)

    def get_forecast(self, target_date: str) -> DailyForecast | None:
        """Return the forecast row for a given ISO date string."""
        for f in self.daily_forecasts:
            if f.date == target_date:
                return f
        return None

    def remaining_forecasts(self, from_date: str) -> list[DailyForecast]:
        """Return all forecast rows strictly after from_date (for revision)."""
        return [f for f in self.daily_forecasts if f.date > from_date]


# ---------------------------------------------------------------------------
# 2. Daily Feedback Log
# ---------------------------------------------------------------------------

LessonCategory = Literal["macro", "technical", "sentiment", "fundamental", "seasonal"]
Direction = Literal["UP", "DOWN", "FLAT"]


class MissAnalysis(BaseModel):
    """Root-cause breakdown of a single day's prediction error."""
    primary_miss_agent: str                          # which agent led the miss
    missed_factors: list[str] = Field(default_factory=list)      # real-world events not captured
    over_weighted_factors: list[str] = Field(default_factory=list)  # signals trusted too much
    agent_score_drift: dict[str, float] = Field(default_factory=dict)  # today re-run vs predicted


class FeedbackEntry(BaseModel):
    """
    One day's entry in the feedback log.
    Appended daily by scripts/daily_review.py.
    """
    day: int
    date: str                            # ISO date string
    predicted_close: float
    actual_close: float
    price_error_pct: float               # (actual - predicted) / predicted * 100
    predicted_verdict: str
    actual_direction: Direction          # UP | DOWN | FLAT (±0.3% threshold)
    direction_correct: bool
    miss_analysis: MissAnalysis | None = None
    lessons_generated: list[str] = Field(default_factory=list)   # lesson IDs added to ledger
    weight_adjustment_applied: str = ""  # e.g. "v4" — which weight version was written
    remaining_forecasts_revised: bool = False
    feedback_agent_raw: str = Field(default="", exclude=True)    # raw LLM output, not serialised


class DailyFeedbackLog(BaseModel):
    """
    All daily feedback entries for a single ticker + monthly cycle.
    Saved as: data/predictions/{TICKER}/{TICKER}_{YYYY-MM}_daily_feedback_log.json
    """
    ticker: str
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
    direction_hits: int = 0      # correct direction calls in current cycle
    total: int = 0               # total evaluated days
    avg_error: float = 0.0       # mean absolute price_error_pct (agent sub-score drift)

    def hit_rate(self) -> float:
        return self.direction_hits / self.total if self.total > 0 else 0.5


class WeightHistoryEntry(BaseModel):
    """One versioned snapshot of weights with the reason for the change."""
    version: int
    date: str                    # ISO date
    weights: dict[str, float]
    reason: str


class WeightMemory(BaseModel):
    """
    Per-ticker adaptive weight state.  Persists across monthly cycles.
    Saved as: data/predictions/{TICKER}/{TICKER}_agent_weight_memory.json
    """
    ticker: str
    last_updated: str            # ISO date
    weight_version: int = 0
    current_weights: dict[str, float]
    base_weights: dict[str, float]   # original config defaults — never mutated
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

class Lesson(BaseModel):
    """One accumulated pattern lesson for a specific stock."""
    lesson_id: str                       # e.g. "L001"
    date_learned: str                    # ISO date first observed
    category: LessonCategory
    pattern: str                         # short machine-readable key e.g. "RBI_policy_day"
    observation: str                     # human-readable what was observed
    rule: str                            # actionable rule applied during forecasts
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    occurrences: int = 1
    still_valid: bool = True


class LearningLedger(BaseModel):
    """
    All accumulated lessons for a ticker.  Persists across monthly cycles.
    Saved as: data/predictions/{TICKER}/{TICKER}_learning_ledger.json
    """
    ticker: str
    last_updated: str
    lessons: list[Lesson] = Field(default_factory=list)
    miss_counter: dict[str, int] = Field(default_factory=dict)   # factor → miss count

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
        """Generate the next sequential lesson ID."""
        return f"L{len(self.lessons) + 1:03d}"

    def active_lessons_summary(self) -> str:
        """Short text summary injected into FeedbackAgent prompt."""
        active = [l for l in self.lessons if l.still_valid]
        if not active:
            return "No lessons learned yet."
        lines = [
            f"{l.lesson_id} [{l.category}] {l.pattern}: {l.rule} (confidence={l.confidence:.2f}, seen={l.occurrences}x)"
            for l in active
        ]
        return "\n".join(lines)

    def increment_miss(self, factor: str) -> None:
        self.miss_counter[factor] = self.miss_counter.get(factor, 0) + 1


# ---------------------------------------------------------------------------
# Feedback Agent I/O contracts
# ---------------------------------------------------------------------------

class FeedbackAgentInput(BaseModel):
    """Structured payload passed to the FeedbackAgent LLM."""
    ticker: str
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


class FeedbackAgentOutput(BaseModel):
    """Structured output the FeedbackAgent LLM must return."""
    primary_miss_agent: str
    missed_factors: list[str] = Field(default_factory=list)
    over_weighted_factors: list[str] = Field(default_factory=list)
    agent_score_drift: dict[str, float] = Field(default_factory=dict)
    new_lessons: list[RawLesson] = Field(default_factory=list)
    revised_context_for_remaining_days: str = ""
