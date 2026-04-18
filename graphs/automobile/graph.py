"""
graphs/automobile/graph.py
==========================
LangGraph StateGraph for the Automobile sector.

Topology
--------
START → resolve_ticker → input_rail
      → [Send fan-out × 8] → run_agent (parallel)
      → aggregate → END

The compiled `graph` object is the entry-point referenced in langgraph.json.

Retry policy (OpenAI Agents SDK pattern)
-----------------------------------------
run_agent nodes get RetryPolicy(max_attempts=2) so a transient API blip
retries once before the Swarm-style fallback score kicks in inside the node.
"""

from langgraph.graph import END, START, StateGraph

# RetryPolicy moved to langgraph.types in 0.3+; pregel in 0.2.x
try:
    from langgraph.types import RetryPolicy
except ImportError:
    from langgraph.pregel import RetryPolicy  # type: ignore[no-redef]

from graphs._shared.nodes import (
    make_aggregate_node,
    make_dispatch_fn,
    make_input_rail_node,
    make_resolve_ticker_node,
    make_run_agent_node,
)
from graphs._shared.state import GraphState
from graphs.automobile.agents import AGENTS, WEIGHTS

SECTOR = "automobile"

# ── Build nodes ────────────────────────────────────────────────────────────
_resolve_ticker = make_resolve_ticker_node(SECTOR)
_input_rail     = make_input_rail_node(SECTOR)
_run_agent      = make_run_agent_node(AGENTS, SECTOR)
_aggregate      = make_aggregate_node(WEIGHTS, SECTOR)
_dispatch       = make_dispatch_fn(list(AGENTS.keys()))

# ── Assemble graph ─────────────────────────────────────────────────────────
_workflow = StateGraph(GraphState)

_workflow.add_node("resolve_ticker", _resolve_ticker)
_workflow.add_node("input_rail",     _input_rail)
_workflow.add_node(
    "run_agent",
    _run_agent,
    retry=RetryPolicy(max_attempts=2),   # Swarm-style resilience
)
_workflow.add_node("aggregate", _aggregate)

# ── Edges ──────────────────────────────────────────────────────────────────
_workflow.add_edge(START,            "resolve_ticker")
_workflow.add_edge("resolve_ticker", "input_rail")
_workflow.add_conditional_edges(     # fan-out via Send — no path_map needed
    "input_rail",                    # LangGraph infers targets from Send objects
    _dispatch,
)
_workflow.add_edge("run_agent",  "aggregate")   # fan-in is automatic
_workflow.add_edge("aggregate",  END)

# ── Compile — exported as `graph` for langgraph.json ──────────────────────
graph = _workflow.compile()
graph.name = "automobile"
