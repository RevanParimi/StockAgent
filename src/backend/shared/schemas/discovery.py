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


class SectorReading(BaseModel):
    """How a deep dive named its stock's sector key (FIX-026). The dive's own
    analysis call answers a key from the configured list; the key stored as
    `sector` is that answer unless the stock already had one (`source`).
    Example: {"answer": "Pharmaceuticals", "problem": "not_a_key"} is an
    idea filed under the "generic" graph whose key nobody has named yet."""
    answer: str = ""                       # the key the analysis answered, as written; "" = none
    reason: str = ""                       # its one-line reason
    yahoo_fits: bool | None = None         # the analysis's view of Yahoo's labels; None = no view
    # Why the answer named no key: "" (it did), "no_answer", "malformed",
    # "not_a_key", "generic_without_reason".
    problem: str = ""
    yahoo_gap: bool = False                # Yahoo gave neither a sector nor an industry
    # Where `sector` came from: "analysis" (this answer), "managed" (the
    # managed record), "ticker_map" (the registry's map), "earlier" (the
    # idea's key, named before), "unnamed" (nothing named one).
    source: str = "analysis"


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
    data_gate: str = ""                    # SA-003 gate status of the dive's run
    # The company's market sector and industry (Yahoo Finance's classification):
    # evidence for the analysis's sector answer, shown beside it. "" = unknown.
    market_sector: str = ""
    industry: str = ""
    # FIX-026: how `sector` was named. `graph` is the graph that ran.
    sector_reading: SectorReading | None = None


class ShelfIdea(BaseModel):
    symbol: str
    # The sector key: SA-050's sector cap, the shelf's per-sector cap and the
    # paper lane's store all read it. "generic" with a reading whose `problem`
    # is set means no key is named yet (core/discovery/sector_naming.py).
    sector: str
    graph: Literal["native", "generic"] = "generic"
    market_sector: str = ""                # Yahoo's sector, evidence only; "" = unknown
    industry: str = ""
    # FIX-026: how `sector` was named; None = shelved before FIX-026.
    sector_reading: SectorReading | None = None
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
    # SA-003: gate status of the latest deep dive of this idea; "" = shelved
    # before the gate existed (unverified: not a SWITCH destination in enforce).
    data_gate: str = ""
    # ISO date of the latest deep dive; "" = the one that shelved it
    # (source_screen_date). A re-dive refreshes the conviction, band and gate
    # in place and restarts the rotation clock (stale_days counts from here).
    # `added` stays, so the auditor's shelf grades count from the day the idea
    # was shelved.
    dived: str = ""
    # "watchlist": a user's own watchlist BUY offered as a buy candidate for
    # that user's portfolio. Built per review, never stored on the shelf.
    source: Literal["discovery", "watchlist"] = "discovery"
    # FIX-024: a watchlist idea's analysis time (ISO, IST offset), so a buy
    # at a session's close counts it only when it was made before that close.
    # "" for a deep dive, which keeps only its day (shelf.decision_time).
    analysed_at: str = ""


class Shelf(BaseModel):
    ideas: list[ShelfIdea] = Field(default_factory=list)
    updated_at: str = ""


class LockinEvent(BaseModel):
    """One IPO lock-in expiry cliff (spec §6.2: supply risk — flag, don't buy into)."""
    symbol: str
    expiry: str                            # ISO date
    kind: Literal["anchor_50pct", "anchor_remaining", "pre_ipo_6mo"]
