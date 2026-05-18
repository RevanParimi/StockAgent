"""
eval/schemas.py
===============
Pydantic v2 models for the evaluation report output.

Hierarchy: EvalReport → SectorEvalResult → AgentEvalResult → SubScoreAccuracy
                                          → VerdictAccuracy
                                          → TickerStats
"""
from __future__ import annotations
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Sub-score level
# ─────────────────────────────────────────────────────────────────────────────

class ScoreCalibrationBucket(BaseModel):
    """One 0.2-width score bucket showing how accurate predictions in that range were."""
    bucket: str          # e.g. "0.60–0.80"
    score_min: float
    score_max: float
    sample_count: int
    direction_hit_rate: float   # fraction of samples where direction was correct
    ideal_hit_rate: float       # bucket midpoint — what perfect calibration looks like
    calibration_error: float    # |hit_rate - ideal|; lower = better calibrated


class SubScoreAccuracy(BaseModel):
    """Accuracy profile for one sub-dimension score (e.g. fada_siam_dispatch)."""
    sub_score_name: str
    agent: str
    sector: str
    sample_count: int           # total observations
    avg: float                  # mean value across all samples
    std: float                  # spread; low std = LLM is bunching scores
    min_val: float
    max_val: float
    # Pearson r between sub-score and direction_correct (1/0). None = insufficient data.
    correlation_with_direction: float | None = None
    calibration_buckets: list[ScoreCalibrationBucket] = Field(default_factory=list)
    # A/B/C/D/F; driven by calibration_error and correlation
    grade: str = "N/A"


# ─────────────────────────────────────────────────────────────────────────────
# Verdict level
# ─────────────────────────────────────────────────────────────────────────────

class VerdictAccuracy(BaseModel):
    """Precision breakdown for one verdict tier (e.g. BUY)."""
    verdict: str
    total_calls: int
    correct_calls: int          # direction_correct == True
    precision: float            # correct / total  (0.0 – 1.0)
    actual_distribution: dict[str, int] = Field(default_factory=dict)
    # e.g. {"UP": 7, "DOWN": 2, "FLAT": 1}


# ─────────────────────────────────────────────────────────────────────────────
# Agent level
# ─────────────────────────────────────────────────────────────────────────────

class AgentEvalResult(BaseModel):
    """Full accuracy profile for one agent within a sector."""
    agent: str
    sector: str
    weight_base: float
    weight_current: float
    weight_drift: float         # current - base; large positive = RL trusted it more

    # Direction accuracy
    direction_hits: int
    total_evaluated: int
    direction_hit_rate: float   # 0.0 – 1.0; > 0.50 beats random

    # Score distribution health
    avg_score: float            # mean overall_score across all runs
    score_std: float            # spread; < 0.10 = bunching problem

    # Miss analysis
    primary_miss_count: int     # how often this agent was named primary_miss_agent
    miss_type_breakdown: dict[str, int] = Field(default_factory=dict)
    # e.g. {"model_bias": 3, "direction_flip": 2, "timing": 1}

    # Regime breakdown (requires regime_accuracy data in WeightMemory)
    regime_hit_rates: dict[str, float] = Field(default_factory=dict)
    # e.g. {"NORMAL": 0.71, "MACRO_CRISIS": 0.44}

    # Sub-score breakdown (keyed by sub-dimension name)
    sub_scores: dict[str, SubScoreAccuracy] = Field(default_factory=dict)

    # A/B/C/D/F driven by direction_hit_rate
    grade: str = "N/A"


# ─────────────────────────────────────────────────────────────────────────────
# Ticker level
# ─────────────────────────────────────────────────────────────────────────────

class TickerStats(BaseModel):
    """Per-ticker summary within a sector."""
    ticker: str
    total_days: int
    direction_hits: int
    direction_hit_rate: float
    avg_price_error_pct: float
    miss_type_distribution: dict[str, int] = Field(default_factory=dict)
    most_blamed_agent: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Sector level
# ─────────────────────────────────────────────────────────────────────────────

class SectorEvalResult(BaseModel):
    """Full accuracy profile for one sector."""
    sector: str
    total_predictions: int
    direction_hit_rate: float   # across all tickers + days
    avg_price_error_pct: float  # mean |actual - predicted| / predicted * 100
    conflict_rate: float        # fraction of pipeline runs with conflicts_resolved non-empty

    # Verdict-level accuracy
    verdict_accuracy: dict[str, VerdictAccuracy] = Field(default_factory=dict)

    # Agent-level accuracy (keyed by agent name)
    agents: dict[str, AgentEvalResult] = Field(default_factory=dict)

    # Per-ticker stats
    tickers: dict[str, TickerStats] = Field(default_factory=dict)

    best_agent: str = ""
    worst_agent: str = ""
    grade: str = "N/A"          # A/B/C/D/F for the whole sector

    # Score calibration for the composite final_score
    final_score_calibration: list[ScoreCalibrationBucket] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Top level
# ─────────────────────────────────────────────────────────────────────────────

class OverallSummary(BaseModel):
    """Cross-sector summary statistics."""
    total_predictions: int
    overall_direction_hit_rate: float
    overall_avg_price_error_pct: float
    best_sector: str = ""
    worst_sector: str = ""
    best_agent_global: str = ""        # agent + sector, e.g. "fundamentals (automobile)"
    worst_agent_global: str = ""
    most_reliable_sub_score: str = ""  # sub-score with highest correlation
    least_reliable_sub_score: str = ""


class EvalReport(BaseModel):
    """
    Full hierarchical accuracy report.
    Saved to eval/reports/eval_{date}.json.
    """
    eval_date: str
    data_sources: list[str] = Field(default_factory=list)  # files that were read
    sectors: dict[str, SectorEvalResult] = Field(default_factory=dict)
    overall: OverallSummary | None = None
    warnings: list[str] = Field(default_factory=list)
