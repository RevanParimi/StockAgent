"""
src/backend/shared/pipeline/core_adapter.py
=============================================
CoreSectorAdapter — wraps a core/{sector}/graph.py compiled LangGraph graph
and exposes the same analyse_async(ticker) interface as backend orchestrators.

Used by SectorRegistry for tier=core sectors that have been toggled on
but don't yet have a full backend orchestrator implementation.

Promotion path:
  disabled (toggle off) → enabled + tier=core (CoreSectorAdapter, 8-pillar)
                        → enabled + tier=backend (custom orchestrator, domain agents)
"""
from __future__ import annotations

import asyncio
import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.shared.schemas.pipeline import FinalReport

logger = logging.getLogger(__name__)


def _score_to_verdict(score: float) -> str:
    if score >= 0.75: return "STRONG BUY"
    if score >= 0.55: return "BUY"
    if score >= 0.40: return "NEUTRAL"
    if score >= 0.20: return "SELL"
    return "STRONG SELL"


def _load_sector_weights(sector: str) -> dict[str, float]:
    try:
        mod = importlib.import_module(f"core.sectors.{sector}.registry")
        return dict(mod.WEIGHTS)
    except Exception:
        return {}


class CoreSectorAdapter:
    """
    Thin adapter: invokes a core sector's compiled LangGraph graph and
    returns a FinalReport compatible with the existing pipeline.

    Subclasses (created by make_core_adapter_class) set _SECTOR at class level.
    """

    _SECTOR: str = ""

    def __init__(self) -> None:
        self._graph = None

    def _load(self) -> None:
        if self._graph is not None:
            return
        try:
            mod = importlib.import_module(f"core.sectors.{self._SECTOR}.graph")
            self._graph = mod.graph
            logger.debug("[CoreSectorAdapter] Loaded graph for sector '%s'", self._SECTOR)
        except ImportError as exc:
            raise ImportError(
                f"[CoreSectorAdapter] core.sectors.{self._SECTOR}.graph not found: {exc}"
            ) from exc

    async def analyse_async(self, ticker: str) -> "FinalReport":
        from backend.shared.schemas.pipeline import FinalReport, WeightedAgentScore

        self._load()
        ticker = ticker.strip().upper()

        logger.info("[CoreSectorAdapter:%s] Running analysis for %s", self._SECTOR, ticker)

        try:
            state: dict = await asyncio.wait_for(
                self._graph.ainvoke({"ticker": ticker}),
                timeout=120.0,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"[CoreSectorAdapter:{self._SECTOR}] timed out (120s) for {ticker}"
            ) from exc

        # Primary path: aggregate node produced a FinalReport
        report = state.get("final_report")
        if isinstance(report, FinalReport):
            return report

        # Fallback: build minimal FinalReport from agent_outputs if aggregate failed
        agent_outputs: dict = state.get("agent_outputs", {})
        if not agent_outputs:
            raise RuntimeError(
                f"[CoreSectorAdapter:{self._SECTOR}] no final_report and no agent_outputs "
                f"for {ticker}. Rail errors: {state.get('rail_errors', [])}"
            )

        weights = _load_sector_weights(self._SECTOR)
        weighted_scores: dict[str, WeightedAgentScore] = {}
        total_w = total_wv = 0.0

        for name, out in agent_outputs.items():
            w = weights.get(name, 1.0 / max(len(agent_outputs), 1))
            raw = float(getattr(out, "overall_score", 0.5))
            weighted_scores[name] = WeightedAgentScore(raw=raw, weight=w, weighted=raw * w)
            total_wv += raw * w
            total_w  += w

        final_score = total_wv / total_w if total_w > 0 else 0.5

        return FinalReport(
            ticker=ticker,
            company_name=state.get("company_name", ticker),
            final_score=round(final_score, 4),
            verdict=_score_to_verdict(final_score),
            weighted_agent_scores=weighted_scores,
            investment_thesis=(
                f"Analysis via {self._SECTOR.replace('_', ' ').title()} "
                f"core pipeline (8-pillar framework: business, fundamentals, "
                f"valuation, technical, macro, risk, management, earnings)."
            ),
        )


def make_core_adapter_class(sector: str) -> type:
    """
    Factory: returns an instantiable class that wraps core/{sector}/graph.py.

    The returned class matches the backend orchestrator call contract:
        cls = make_core_adapter_class("capgoods")
        instance = cls()                           # like AutomobileAgentOrchestrator()
        report = await instance.analyse_async("LT")

    The class is created with type() so each sector gets a distinct class name,
    which makes logging and debugging clear.
    """
    return type(
        f"CoreAdapter_{sector}",
        (CoreSectorAdapter,),
        {"_SECTOR": sector},
    )
