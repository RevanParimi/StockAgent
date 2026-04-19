"""
graphs/renewable_energy/graph.py
==================================
LangGraph StateGraph for the Renewable Energy sector.
Six agents: fundamentals, business, valuation, sentiment_policy,
            technical, risk (monitoring-only, weight=0)
"""

from langgraph.graph import END, START, StateGraph

try:
    from langgraph.types import RetryPolicy
except ImportError:
    from langgraph.pregel import RetryPolicy  # type: ignore[no-redef]

from core.graphs.nodes import (
    make_aggregate_node,
    make_dispatch_fn,
    make_input_rail_node,
    make_resolve_ticker_node,
    make_run_agent_node,
)
from core.graphs.state import GraphState
from core.sectors.renewable.agents import AGENTS, WEIGHTS

SECTOR = "renewable_energy"

_resolve_ticker = make_resolve_ticker_node(SECTOR)
_input_rail     = make_input_rail_node(SECTOR)
_run_agent      = make_run_agent_node(AGENTS, SECTOR)
_aggregate      = make_aggregate_node(WEIGHTS, SECTOR)
_dispatch       = make_dispatch_fn(list(AGENTS.keys()))

_workflow = StateGraph(GraphState)

_workflow.add_node("resolve_ticker", _resolve_ticker)
_workflow.add_node("input_rail",     _input_rail)
_workflow.add_node("run_agent",      _run_agent, retry=RetryPolicy(max_attempts=2))
_workflow.add_node("aggregate",      _aggregate)

_workflow.add_edge(START,            "resolve_ticker")
_workflow.add_edge("resolve_ticker", "input_rail")
_workflow.add_conditional_edges("input_rail", _dispatch)
_workflow.add_edge("run_agent",  "aggregate")
_workflow.add_edge("aggregate",  END)

graph = _workflow.compile()
graph.name = "renewable_energy"
