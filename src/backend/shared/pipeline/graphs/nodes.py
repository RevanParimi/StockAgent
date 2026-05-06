"""
graphs/_shared/nodes.py
=======================
Factory functions that produce LangGraph node callables shared across
all four sector graphs.

Each factory is parameterised at graph-build time (sector name, agent
registry, weights dict) so the same logic runs for every sector with
zero code duplication.

Node pipeline per sector graph:
  resolve_ticker → input_rail → [Send fan-out] → run_agent
      → aggregate → final_report

The conflict_rail is called inside aggregate — not a separate node —
because it needs all agent outputs before it can detect divergence.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

from langgraph.types import Send

from backend.shared.config import settings
from backend.shared.schemas.pipeline import AgentOutput, FinalReport, StockQuery, WeightedAgentScore
from services.clients.llm_client import get_llm_client
from services.data.stores.run_logger import log_llm_call

from backend.shared.pipeline.graphs.rails import conflict_rail, input_rail, output_rail
from backend.shared.pipeline.graphs.state import GraphState

logger = logging.getLogger(__name__)

VALID_VERDICTS = {"STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"}


# ──────────────────────────────────────────────────────────────────────────
# Node 1: resolve_ticker
# ──────────────────────────────────────────────────────────────────────────

_RESOLVE_SYSTEM = (
    "You are a financial data assistant specialising in Indian stock markets. "
    "Return ONLY valid JSON."
)
_RESOLVE_USER = (
    'Given the user input "{user_input}", identify the NSE/BSE ticker symbol '
    "and full company name. Return: "
    '{"ticker": "SYMBOL", "company_name": "Full Name", "exchange": "NSE"}'
)


def make_resolve_ticker_node(sector: str) -> Callable[[GraphState], dict]:
    """Return a node function that resolves a raw ticker string."""
    llm = get_llm_client()

    def resolve_ticker(state: GraphState) -> dict:
        run_id = state.get("run_id") or str(uuid.uuid4())[:8]
        user_input = state["ticker"]
        t0 = time.time()

        try:
            resp = llm.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=0.0,
                max_tokens=128,
                messages=[
                    {"role": "system", "content": _RESOLVE_SYSTEM},
                    {"role": "user",   "content": _RESOLVE_USER.format(user_input=user_input)},
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            if resp.usage:
                pt, ct = resp.usage.prompt_tokens, resp.usage.completion_tokens
                cost = (pt * settings.LLM_INPUT_COST_PER_M + ct * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
                log_llm_call(
                    run_id=run_id, ticker=user_input.upper(),
                    phase="ticker_resolution", agent_name=None,
                    model=settings.LLM_MODEL, prompt_tokens=pt,
                    completion_tokens=ct, duration_ms=(time.time() - t0) * 1000,
                    cost_usd=cost,
                )
            query = StockQuery(
                ticker=data.get("ticker", user_input.upper()),
                company_name=data.get("company_name", user_input),
                exchange=data.get("exchange", settings.DEFAULT_EXCHANGE),
                analysis_date=date.today(),
            )
        except Exception as exc:
            logger.warning("[%s] resolve_ticker failed: %s", sector, exc)
            query = StockQuery(
                ticker=user_input.upper(),
                company_name=user_input,
                exchange=settings.DEFAULT_EXCHANGE,
            )

        logger.info("[%s] Resolved '%s' → %s", sector, user_input, query.ticker)
        return {
            "query": query,
            "company_name": query.company_name,
            "run_id": run_id,
            "agent_outputs": {},
            "rail_errors": [],
            "final_report": None,
            "current_agent": "",
        }

    return resolve_ticker


# ──────────────────────────────────────────────────────────────────────────
# Node 2: input_rail
# ──────────────────────────────────────────────────────────────────────────

def make_input_rail_node(sector: str) -> Callable[[GraphState], dict]:
    """Return a node that runs the NeMo-style input validation rail."""

    def input_rail_node(state: GraphState) -> dict:
        query = state["query"]
        if query is None:
            return {"rail_errors": ["INPUT_RAIL: query not resolved"]}

        _, errors = input_rail(query.ticker, query.exchange)
        if errors:
            logger.warning("[%s] InputRail: %s", sector, errors)
        return {"rail_errors": errors}

    return input_rail_node


# ──────────────────────────────────────────────────────────────────────────
# Node 3: dispatch (conditional edge — returns list[Send])
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
# Node 4: run_agent  (called N times in parallel via Send)
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


# ──────────────────────────────────────────────────────────────────────────
# Node 5: aggregate
# ──────────────────────────────────────────────────────────────────────────

_CONFLICT_SYSTEM = (
    "You are a senior equity analyst. You will be given conflicting signal "
    "scores from multiple specialist sub-agents for the same stock. Your task "
    "is to produce a fair, evidence-weighted resolution.\n"
    "Return ONLY valid JSON."
)

_SIMPLE_AGG_SYSTEM = (
    "You are a senior equity analyst synthesising specialist sub-agent signals "
    "into a final investment verdict for an Indian listed stock.\n"
    "Return ONLY valid JSON."
)
_CONFLICT_USER = """
Stock: {ticker} ({company_name})
Sector: {sector}

Conflicting agents and their scores:
{conflict_lines}

All agent summaries:
{summaries}

Resolve the conflict and return:
{{
  "resolution_notes": ["<reason 1>", ...],
  "adjusted_scores": {{"<agent_name>": <0.0-1.0>, ...}},
  "final_score": <0.0-1.0>,
  "verdict": "<STRONG BUY|BUY|NEUTRAL|SELL|STRONG SELL>",
  "executive_summary": "<1-2 plain-English sentences a beginner investor can act on>",
  "investment_thesis": "<2-3 sentence thesis>",
  "conviction_drivers": ["<driver 1>", ...],
  "top_risks": ["<risk 1>", ...]
}}
"""

_SIMPLE_AGG_USER = """
Stock: {ticker} ({company_name})
Sector: {sector}

Weighted agent scores:
{score_lines}

Agent summaries:
{summaries}

Synthesise a final verdict. Return:
{{
  "final_score": <0.0-1.0>,
  "verdict": "<STRONG BUY|BUY|NEUTRAL|SELL|STRONG SELL>",
  "executive_summary": "<1-2 plain-English sentences a beginner investor can act on>",
  "investment_thesis": "<2-3 sentence thesis>",
  "conviction_drivers": ["<driver 1>", ...],
  "top_risks": ["<risk 1>", ...]
}}
"""


def make_aggregate_node(
    weights: dict[str, float],
    sector: str,
) -> Callable[[GraphState], dict]:
    """
    Return a node that:
      1. Applies configured weights to agent scores
      2. Runs conflict_rail — if conflicts exist, calls LLM for resolution
      3. Otherwise calls LLM for simple synthesis
      4. Produces a FinalReport
    """
    llm = get_llm_client()

    def aggregate(state: GraphState) -> dict:
        outputs = state["agent_outputs"]
        query = state["query"]
        run_id = state.get("run_id", "")

        # ── 1. Weighted score computation ──────────────────────────────
        total_weight = 0.0
        weighted_sum = 0.0
        weighted_agent_scores: dict[str, WeightedAgentScore] = {}

        for name, out in outputs.items():
            w = weights.get(name, 1.0 / len(outputs))
            ws = WeightedAgentScore(
                raw=out.overall_score,
                weight=w,
                weighted=round(out.overall_score * w, 4),
            )
            weighted_agent_scores[name] = ws
            weighted_sum += ws.weighted
            total_weight += w

        raw_final = weighted_sum / total_weight if total_weight > 0 else 0.5

        # ── 2. Conflict rail ────────────────────────────────────────────
        has_conflict, conflict_pairs = conflict_rail(outputs)

        summaries = "\n".join(
            f"  {n}: score={o.overall_score:.3f} — {o.summary[:120]}"
            for n, o in outputs.items()
        )

        conflicts_resolved: list[str] = []
        conviction_drivers: list[str] = []
        top_risks: list[str] = []
        investment_thesis = ""
        executive_summary = ""
        final_score = round(raw_final, 4)
        verdict = _score_to_verdict(final_score)

        t0 = time.time()
        try:
            if has_conflict:
                conflict_lines = "\n".join(
                    f"  {a} ({outputs[a].overall_score:.3f}) vs "
                    f"{b} ({outputs[b].overall_score:.3f}) — delta={d}"
                    for a, b, d in conflict_pairs
                )
                prompt = _CONFLICT_USER.format(
                    ticker=query.ticker,
                    company_name=query.company_name,
                    sector=sector,
                    conflict_lines=conflict_lines,
                    summaries=summaries,
                )
                resp = llm.chat.completions.create(
                    model=settings.LLM_MODEL,
                    temperature=0.1,
                    max_tokens=512,
                    messages=[
                        {"role": "system", "content": _CONFLICT_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                data = json.loads(resp.choices[0].message.content or "{}")
                final_score = float(data.get("final_score", final_score))
                final_score = max(0.0, min(1.0, final_score))
                verdict = data.get("verdict", verdict)
                if verdict not in VALID_VERDICTS:
                    verdict = _score_to_verdict(final_score)
                executive_summary = data.get("executive_summary", "")
                investment_thesis = data.get("investment_thesis", "")
                conviction_drivers = data.get("conviction_drivers", [])
                top_risks = data.get("top_risks", [])
                conflicts_resolved = data.get("resolution_notes", [
                    f"{a} vs {b} (Δ={d})" for a, b, d in conflict_pairs
                ])
            else:
                score_lines = "\n".join(
                    f"  {n}: raw={ws.raw:.3f} weight={ws.weight:.2f} → {ws.weighted:.4f}"
                    for n, ws in weighted_agent_scores.items()
                )
                prompt = _SIMPLE_AGG_USER.format(
                    ticker=query.ticker,
                    company_name=query.company_name,
                    sector=sector,
                    score_lines=score_lines,
                    summaries=summaries,
                )
                resp = llm.chat.completions.create(
                    model=settings.LLM_MODEL,
                    temperature=0.1,
                    max_tokens=512,
                    messages=[
                        {"role": "system", "content": _SIMPLE_AGG_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                data = json.loads(resp.choices[0].message.content or "{}")
                final_score = float(data.get("final_score", final_score))
                final_score = max(0.0, min(1.0, final_score))
                verdict = data.get("verdict", verdict)
                if verdict not in VALID_VERDICTS:
                    verdict = _score_to_verdict(final_score)
                executive_summary = data.get("executive_summary", "")
                investment_thesis = data.get("investment_thesis", "")
                conviction_drivers = data.get("conviction_drivers", [])
                top_risks = data.get("top_risks", [])

            # Log usage after both branches — resp is guaranteed defined here
            if resp.usage:
                pt, ct = resp.usage.prompt_tokens, resp.usage.completion_tokens
                cost = (pt * settings.LLM_INPUT_COST_PER_M + ct * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
                log_llm_call(
                    run_id=run_id, ticker=query.ticker,
                    phase="aggregation", agent_name="signal_aggregator",
                    model=settings.LLM_MODEL, prompt_tokens=pt,
                    completion_tokens=ct, duration_ms=(time.time() - t0) * 1000,
                    cost_usd=cost,
                )

        except Exception as exc:
            logger.error("[%s] aggregate LLM call failed: %s", sector, exc)
            # Fall back to pure weighted average — no LLM thesis
            investment_thesis = "LLM synthesis unavailable; score is pure weighted average."

        report = FinalReport(
            ticker=query.ticker,
            company_name=query.company_name,
            final_score=final_score,
            verdict=verdict,
            weighted_agent_scores=weighted_agent_scores,
            conflicts_resolved=conflicts_resolved,
            conviction_drivers=conviction_drivers,
            top_risks=top_risks,
            investment_thesis=investment_thesis,
            executive_summary=executive_summary,
            report_date=date.today().isoformat(),
            agent_outputs={n: o.model_dump() for n, o in outputs.items()},
        )
        logger.info(
            "[%s] Aggregation done — verdict=%s score=%.4f conflicts=%d",
            sector, verdict, final_score, len(conflicts_resolved),
        )
        return {"final_report": report}

    return aggregate


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _score_to_verdict(score: float) -> str:
    if score >= 0.75:
        return "STRONG BUY"
    if score >= 0.55:
        return "BUY"
    if score >= 0.40:
        return "NEUTRAL"
    if score >= 0.20:
        return "SELL"
    return "STRONG SELL"
