"""
agents/signal_aggregator.py
============================
Signal Aggregator — the final stage of the Automobile Agent pipeline.

Responsibilities:
  1. Apply configured weights to each sub-agent's score
  2. Detect conflicts between agent scores (score delta > 0.3)
  3. Call LLM to resolve conflicts and produce an investment thesis
  4. Return a FinalReport with verdict, conviction drivers, and risks
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

from core.config import settings
from core.schemas.pipeline import (
    AgentOutput,
    FinalReport,
    WeightedAgentScore,
)
from core.config.prompts.shared import signal_aggregator as P
from services.clients.llm_client import get_llm_client
from services.data.stores.run_logger import log_llm_call

logger = logging.getLogger(__name__)

# Minimum score difference between two agents to flag a conflict
CONFLICT_THRESHOLD = 0.30


class SignalAggregator:
    """
    Combines outputs from the five sub-agents into a single stock verdict.
    Not a subclass of BaseAgent because it has a different input signature.
    """

    def __init__(self) -> None:
        self._client = get_llm_client()
        self._last_prompt_tokens: int = 0
        self._last_completion_tokens: int = 0

    def run(
        self,
        ticker: str,
        company_name: str,
        agent_outputs: dict[str, AgentOutput],
        learned_weights: dict[str, float] | None = None,
        run_id: str = "",
    ) -> FinalReport:
        """
        Parameters
        ----------
        learned_weights : dict | None
            If provided (from WeightMemory), overrides settings.AGENT_WEIGHTS for
            this run only.  Used by generate_forecast.py and daily_review.py to
            inject ticker-specific earned weights without mutating global config.
        """
        logger.info("[SignalAggregator] Aggregating %d agent signals for %s", len(agent_outputs), ticker)

        if learned_weights:
            weights = learned_weights
            logger.info(
                "[SignalAggregator] Using learned weights for %s: %s",
                ticker,
                {k: round(v, 4) for k, v in learned_weights.items()},
            )
        else:
            weights = settings.AGENT_WEIGHTS
        weighted_scores: dict[str, WeightedAgentScore] = {}
        weighted_sum = 0.0
        weight_total = 0.0

        for agent_name, output in agent_outputs.items():
            w = weights.get(agent_name, 0.0)
            ws = WeightedAgentScore(
                raw=output.overall_score,
                weight=w,
                weighted=round(output.overall_score * w, 4),
            )
            weighted_scores[agent_name] = ws
            weighted_sum += ws.weighted
            weight_total += w

        # Normalise in case weights don't sum to exactly 1.0
        composite = weighted_sum / weight_total if weight_total else 0.5
        composite = max(0.0, min(1.0, composite))

        conflicts = self._detect_conflicts(agent_outputs)

        # Build the block of scores for the prompt
        score_lines = []
        for name, ws in weighted_scores.items():
            score_lines.append(
                f"  {name}: raw={ws.raw:.3f}, weight={ws.weight:.2f}, "
                f"weighted={ws.weighted:.4f}"
            )
        agent_scores_block = "\n".join(score_lines)

        system_prompt = P.SYSTEM_PROMPT
        user_prompt = P.AGGREGATION_PROMPT.format(
            ticker=ticker,
            company_name=company_name,
            agent_scores_block=agent_scores_block,
            weighted_score=composite,
            conflict_flags=conflicts if conflicts else "None",
            report_date=str(date.today()),
        )

        t0 = time.time()
        raw = self._call_llm(system_prompt, user_prompt)
        duration_ms = (time.time() - t0) * 1000

        cost = (
            self._last_prompt_tokens * settings.LLM_INPUT_COST_PER_M
            + self._last_completion_tokens * settings.LLM_OUTPUT_COST_PER_M
        ) / 1_000_000
        log_llm_call(
            run_id=run_id, ticker=ticker, phase="aggregation",
            agent_name=None, model=settings.LLM_MODEL,
            prompt_tokens=self._last_prompt_tokens,
            completion_tokens=self._last_completion_tokens,
            duration_ms=duration_ms, cost_usd=cost,
        )
        return self._parse(raw, ticker, company_name, weighted_scores, agent_outputs)

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def _detect_conflicts(self, agent_outputs: dict[str, AgentOutput]) -> list[str]:
        scores = {k: v.overall_score for k, v in agent_outputs.items()}
        names = list(scores.keys())
        conflicts: list[str] = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                diff = abs(scores[a] - scores[b])
                if diff >= CONFLICT_THRESHOLD:
                    conflicts.append(
                        f"{a}({scores[a]:.2f}) vs {b}({scores[b]:.2f}): delta={diff:.2f}"
                    )
        return conflicts

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        if response.usage:
            self._last_prompt_tokens = response.usage.prompt_tokens
            self._last_completion_tokens = response.usage.completion_tokens
        return response.choices[0].message.content or "{}"

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def _parse(
        self,
        raw: str,
        ticker: str,
        company_name: str,
        weighted_scores: dict[str, WeightedAgentScore],
        agent_outputs: dict[str, AgentOutput],
    ) -> FinalReport:
        try:
            data = json.loads(raw)

            price_target = None
            recovery_quarters = None
            undervalued_pct = None
            discount_reason = None
            recovery_catalysts: list[str] = []

            vc_output = agent_outputs.get("valuation_catalyst")
            if vc_output is not None:
                vc = vc_output if isinstance(vc_output, dict) else vc_output.model_dump()
                price_target = vc.get("price_target")
                recovery_quarters = vc.get("recovery_timeline_quarters")
                raw_disc = vc.get("current_discount_pct")
                if raw_disc is not None:
                    undervalued_pct = -float(raw_disc)
                discount_reason = vc.get("discount_reason")
                recovery_catalysts = vc.get("recovery_catalysts", [])

            return FinalReport(
                ticker=ticker,
                company_name=company_name,
                final_score=max(0.0, min(1.0, float(data.get("final_score", 0.5)))),
                verdict=data.get("verdict", "NEUTRAL"),
                weighted_agent_scores=weighted_scores,
                conflicts_resolved=data.get("conflicts_resolved", []),
                conviction_drivers=data.get("conviction_drivers", []),
                top_risks=data.get("top_risks", []),
                executive_summary=data.get("executive_summary", ""),
                investment_thesis=data.get("investment_thesis", ""),
                report_date=data.get("report_date", str(date.today())),
                price_target=float(price_target) if price_target is not None else None,
                recovery_timeline_quarters=int(recovery_quarters) if recovery_quarters is not None else None,
                undervalued_by_pct=float(undervalued_pct) if undervalued_pct is not None else None,
                discount_reason=str(discount_reason) if discount_reason else None,
                recovery_catalysts=recovery_catalysts,
                agent_outputs={k: v.model_dump() for k, v in agent_outputs.items()},
            )
        except Exception as exc:
            logger.error("[SignalAggregator] Parse error: %s\nRaw: %s", exc, raw[:500])
            return FinalReport(
                ticker=ticker,
                company_name=company_name,
                final_score=0.5,
                verdict="NEUTRAL",
                weighted_agent_scores=weighted_scores,
                investment_thesis=f"Aggregation failed: {exc}",
                report_date=str(date.today()),
                agent_outputs={k: v.model_dump() for k, v in agent_outputs.items()},
            )
