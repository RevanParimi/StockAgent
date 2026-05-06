# ── MIGRATION SHIM ────────────────────────────────────────────────────────────
# Real module: src/backend/shared/schemas/feedback.py
# This shim keeps all existing `from core.schemas.feedback import ...` working
# unchanged during the migration.  Remove once every import is updated.
from backend.shared.schemas.feedback import *  # noqa: F401, F403
from backend.shared.schemas.feedback import (  # explicit re-exports for IDEs
    Direction,
    LessonCategory,
    LessonScope,
    MissType,
    MISS_TYPE_PENALTY_MULTIPLIER,
    NO_PENALTY_MISS_TYPES,
    MissAnalysis,
    TimingAccuracy,
    RevisedContext,
    FeedbackEntry,
    DailyFeedbackLog,
    AgentAccuracy,
    WeightHistoryEntry,
    WeightMemory,
    Lesson,
    LearningLedger,
    ConvictionStreak,
    DailyForecast,
    PredictionEnvelope,
    SeasonalPattern,
    SeasonalContext,
    FeedbackAgentInput,
    RawLesson,
    FeedbackAgentOutput,
    RegimeSnapshot,
)
