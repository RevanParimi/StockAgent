"""
graphs/_shared/nodes.py
=======================
Factory functions that produce LangGraph node callables for the legacy
worker pool (`BaseOrchestrator._run_via_graph`) — the fallback path used
when the unified analyst is disabled for a sector or fails outright
(UNIFIED_ANALYST_FALLBACK_LEGACY).

Wave E (AUD-095): the standalone compiled sector graphs and their
resolver/input-rail/aggregate nodes were deleted; ticker resolution and
verdict aggregation live in BaseOrchestrator/SignalAggregator on the
live path. Only the fan-out dispatch and per-agent execution nodes
remain here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langgraph.types import Send

from backend.shared.schemas.pipeline import AgentOutput
from backend.shared.pipeline.graphs.rails import output_rail
from backend.shared.pipeline.graphs.state import GraphState

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# dispatch (conditional edge — returns list[Send])
# ──────────────────────────────────────────────────────────────────────────

def make_dispatch_fn(agent_names: list[str]) -> Callable[[GraphState], list[Send]]:
    """
    Return a conditional-edge function that fans out to run_agent for each
    agent in the registry.  Uses LangGraph's Send API for true parallelism.
    """

    def dispatch(state: GraphState) -> list[Send]:
        return [
            Send("run_agent", {**state, "current_agent": name})
            for name in agent_names
        ]

    return dispatch


# ──────────────────────────────────────────────────────────────────────────
# run_agent  (called N times in parallel via Send)
# ──────────────────────────────────────────────────────────────────────────

def make_run_agent_node(
    agents: dict[str, Any],
    sector: str,
) -> Callable[[GraphState], dict]:
    """
    Return a node that runs one agent (identified by state["current_agent"]).

    Swarm-style fallback: if the full agent raises, inject a neutral
    AgentOutput with error=True rather than crashing the graph.

    Output rail (NeMo pattern) sanitizes the result before it's stored.
    """

    def run_agent(state: GraphState) -> dict:
        name = state["current_agent"]
        query = state["query"]
        run_id = state.get("run_id", "")
        agent = agents.get(name)

        output: AgentOutput
        if agent is None:
            output = AgentOutput(
                agent=name, ticker=query.ticker,
                overall_score=0.5,
                summary=f"{name} agent not registered for {sector}.",
                error=f"agent '{name}' missing from registry",
            )
        else:
            try:
                output = agent.run(query, run_id)
            except Exception as exc:
                logger.error("[%s/%s] agent failed: %s", sector, name, exc)
                # Swarm handoff: neutral score, full error context preserved
                output = AgentOutput(
                    agent=name, ticker=query.ticker,
                    overall_score=0.5,
                    summary=f"{name} encountered an error; neutral score applied.",
                    error=str(exc),
                )

        # NeMo output rail — clamp & validate
        output, rail_errs = output_rail(output)
        return {
            "agent_outputs": {name: output},
            "rail_errors": rail_errs,
        }

    return run_agent
