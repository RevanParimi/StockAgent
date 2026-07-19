"""
Monthly Scorecard + Baseline Duel — RL Phase 1 schemas.

Two families of models, persisted separately:

1. Control lane (the duel) — `ControlPrediction` / `ControlLog`.
   A bare-LLM predictor gets the same close + market_context StockAgent has
   (no agents, no learned weights, no lessons, no dossier) and predicts the
   next session's direction. Persisted per ticker per monthly cycle as
   `data/predictions/{sector}/{TICKER}/{cycle_id}_control_log.json`
   (see `PredictionStore._control_log_path`).

2. Monthly scorecard — `LaneScore` / `TickerScorecard` / `MonthlyScorecard`.
   A permanent, append-only time series of per-month accuracy across lanes
   (StockAgent, control LLM, naive baselines), persisted to
   `{SCORECARD_DIR}/{YYYY-MM}_scorecard.json`.

See docs/superpowers/specs/2026-06-12-monthly-scorecard-baseline-duel-design.md
sections 2.2 and 5.1.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Component 1 — Control lane (the duel)
# ---------------------------------------------------------------------------

class ControlPrediction(BaseModel):
    """
    One day's bare-LLM prediction, made the previous session with the same
    close + market_context StockAgent had at that moment.

    `actual_direction` and `correct` are filled on the NEXT review (Step 10
    of `run_daily_review`), once the predicted day's outcome is known.
    """
    date: str                       # trading day being predicted
    made_on: str                    # review date when prediction was made (prev session)
    predicted_direction: str        # "UP" | "DOWN" | "FLAT"
    confidence: float = 0.5         # 0..1
    predicted_close: float | None = None
    rationale: str = ""             # capped 200 chars
    model: str = ""
    # Filled when scored (next review):
    actual_direction: str = ""
    correct: bool | None = None


class ControlLog(BaseModel):
    """
    All control-lane predictions for a single ticker + monthly cycle.
    Saved as: data/predictions/{sector}/{TICKER}/{cycle_id}_control_log.json
    (mirrors DailyFeedbackLog's monthly-cycle file pattern).
    """
    ticker: str
    sector: str
    cycle_id: str                   # e.g. "MARUTI_2026-06" — monthly, like feedback log
    entries: list[ControlPrediction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Component 4 — Monthly scorecard
# ---------------------------------------------------------------------------

class LaneScore(BaseModel):
    """Accuracy summary for one prediction lane (agent / control / baseline)."""
    n: int = 0
    direction_accuracy: float | None = None
    brier_score: float | None = None          # only lanes with confidence (agent, control)


class TickerScorecard(BaseModel):
    """
    One ticker's monthly scorecard — StockAgent vs the control LLM vs naive
    baselines, plus claim-audit and dossier-health snapshots.
    """
    ticker: str
    sector: str
    agent: LaneScore                          # StockAgent (from feedback log, existing metrics)
    control: LaneScore                        # control lane (scored entries only)
    persistence: LaneScore                    # naive baselines (direction accuracy only)
    always_up: LaneScore
    band_coverage: float | None = None
    mae_pct: float | None = None
    edge_vs_control: float | None = None      # agent − control direction accuracy
    edge_vs_persistence: float | None = None
    claim_days: int = 0                       # days with claims_fired non-empty
    accuracy_on_claim_days: float | None = None
    accuracy_on_other_days: float | None = None
    dossier_version: int | None = None        # health snapshot
    dossier_observations: int | None = None
    live_signatures: int | None = None


class MonthlyScorecard(BaseModel):
    """
    Permanent, append-only monthly scorecard — the improvement time series.
    Saved as: {SCORECARD_DIR}/{YYYY-MM}_scorecard.json
    """
    month: str                                # "2026-06"
    generated_at: str
    tickers: dict[str, TickerScorecard] = Field(default_factory=dict)
    aggregate: TickerScorecard | None = None  # ticker-weighted aggregate (ticker="ALL")
    deltas_vs_previous: dict[str, float] = Field(default_factory=dict)  # aggregate metric deltas; {} when no prior
    # Wave I: per-regime accuracy breakdown, pooled across tickers —
    # {regime_label: {"n": days, "direction_accuracy": float|None,
    #                 "agents": {agent: {"hits": int, "total": int, "hit_rate": float}}}}
    # Report-only evidence for retuning the hand-authored REGIME_MULTIPLIERS
    # table (hit-credit rule shared with WeightAdapter Stage 1).
    regime_agent_hit_rates: dict[str, dict] = Field(default_factory=dict)
