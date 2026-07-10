"""
Compass Phase B — Discovery Engine schemas (spec §6).

Everything the funnel persists: weekly ScreenResult (quant stage), DeepDiveResult
(LLM stage) and the Discovery Shelf. All output copy is research/analysis,
never "advice"; every idea carries an invalidation_level (spec §9.4).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DiscoveryCandidate(BaseModel):
    """One guard-passed symbol from the weekly quant screen."""
    symbol: str
    close: float
    composite: float                       # weighted percentile-rank blend, 0-1
    signal_ranks: dict[str, float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)


class ScreenResult(BaseModel):
    """Stage-1 output: ~2000 universe -> ranked, guarded candidates."""
    screen_date: str                       # ISO
    universe_size: int
    shortlist_size: int
    candidates: list[DiscoveryCandidate] = Field(default_factory=list)
    rejected: dict[str, list[str]] = Field(default_factory=dict)   # symbol -> gates
    dark_signals: list[str] = Field(default_factory=list)
    degraded_checks: list[str] = Field(default_factory=list)


class DeepDiveResult(BaseModel):
    """Stage-3 output: unified-analyst one-call conviction on a candidate."""
    symbol: str
    sector: str
    graph: Literal["native", "generic"]
    conviction: float                      # FinalReport.final_score, 0-1
    verdict: str
    thesis: str
    entry_low: float
    entry_high: float
    invalidation_level: float              # "thesis dead below X" (spec §9.4)
    close: float
    composite: float
    dive_date: str                         # ISO


class ShelfIdea(BaseModel):
    symbol: str
    sector: str
    graph: Literal["native", "generic"] = "generic"
    added: str                             # ISO date
    conviction: float
    verdict: str = ""
    thesis: str = ""
    entry_low: float = 0.0
    entry_high: float = 0.0
    invalidation_level: float = 0.0
    close_at_add: float = 0.0
    status: Literal["active", "promoted", "dropped"] = "active"
    paper_cycle_id: str = ""
    last_paper_review: str = ""            # ISO date of last paper review
    source_screen_date: str = ""


class Shelf(BaseModel):
    ideas: list[ShelfIdea] = Field(default_factory=list)
    updated_at: str = ""


class LockinEvent(BaseModel):
    """One IPO lock-in expiry cliff (spec §6.2: supply risk — flag, don't buy into)."""
    symbol: str
    expiry: str                            # ISO date
    kind: Literal["anchor_50pct", "anchor_remaining", "pre_ipo_6mo"]
