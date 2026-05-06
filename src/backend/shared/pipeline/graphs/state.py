"""
graphs/_shared/state.py
=======================
Shared LangGraph state schema used by all 4 sector graphs.

- agent_outputs uses a merge reducer so parallel fan-out nodes can each
  write their single agent result and LangGraph accumulates them safely.
- rail_errors uses list-append so both input and output rails can add
  errors without overwriting each other.
"""

from __future__ import annotations

import operator
from typing import Annotated
from typing_extensions import TypedDict

from backend.shared.schemas.pipeline import AgentOutput, FinalReport, StockQuery


def _merge_dicts(existing: dict, update: dict) -> dict:
    """Reducer: merge two dicts, update wins on key collision."""
    return {**existing, **update}


# total=False: all fields are Optional from LangGraph's perspective.
# Only `ticker` is required at invoke() time; every other field is
# populated by nodes as the graph executes.  Without total=False,
# LangGraph may error on partial initial states.
class GraphState(TypedDict, total=False):
    # ── Input ──────────────────────────────────────────────────────────────
    ticker: str                    # raw user input, e.g. "MARUTI"

    # ── Resolved by resolve_ticker node ───────────────────────────────────
    company_name: str
    query: StockQuery | None

    # ── Fan-out accumulator (merge reducer) ───────────────────────────────
    # Each run_agent node writes {"agent_name": AgentOutput}; LangGraph
    # merges all partial dicts before aggregate node runs.
    agent_outputs: Annotated[dict[str, AgentOutput], _merge_dicts]

    # ── Rail error log (append reducer) ───────────────────────────────────
    rail_errors: Annotated[list[str], operator.add]

    # ── Final output ───────────────────────────────────────────────────────
    final_report: FinalReport | None

    # ── Run metadata ───────────────────────────────────────────────────────
    run_id: str

    # ── Fan-out routing — set by Send, empty string at all other times ─────
    current_agent: str
