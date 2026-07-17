"""
pipeline/unified_analyst.py
============================
Unified Sector Analyst (2026-06-12 redesign) — sector-generic.

ONE LLM call -> all of a sector's dimension AgentOutput subclasses, replacing
N parallel per-agent LLM calls (each with its own data fetch). The data fetch
is done once by `services.data.context.bundle_builder.build_sector_bundle`;
this module turns that bundle + a sector prompt module into the same
`AgentOutput` subclasses the legacy agents produce, so downstream consumers
(SignalAggregator, FinalReport, RL) are unaffected.

Public API
----------
DIMENSIONS               — dict[sector] -> ordered list of dimension names
UnifiedAnalyst.run(query, bundle, sector) -> dict[str, AgentOutput]
    NEVER raises. Returns {} on total failure (unknown sector, LLM failure
    after retries, non-JSON response, or any other unexpected error).
"""

from __future__ import annotations

import importlib
import json
import logging
import re
import time
import typing
from dataclasses import dataclass
from datetime import date

from openai import APIError, APITimeoutError, RateLimitError
from pydantic import create_model

from backend.shared.config import settings
from backend.shared.schemas.pipeline import (
    AgentOutput,
    StockQuery,
    SalesDemandOutput,
    RawMaterialsOutput,
    FundamentalsOutput,
    PatternAnalysisOutput,
    SentimentOutput,
    PolicyRegulatoryOutput,
    CompetitiveIntelOutput,
    RiskMacroOutput,
    ValuationCatalystOutput,
)
from services.clients.llm_client import (
    JSON_MODE_EXTRA_BODY,
    get_llm_client,
    salvage_truncated_json,
)
from services.data.context.bundle_builder import SectorDataBundle
from services.data.stores.run_logger import log_llm_call

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sector spec registry
# ---------------------------------------------------------------------------
#
# Each sector's `classes` dict maps dimension name -> AgentOutput subclass.
# Dict order defines DIMENSIONS[sector] order (also the order rendered in the
# unified analyst prompt and the order weights are reported in).
#
# automobile: the original hand-written AgentOutput subclasses
# (SalesDemandOutput, ...), each already declaring its own
# `sub_scores: <Sector>SubScores | None` field — unchanged from before this
# refactor.
#
# banking_bfsi / it_sector / renewable_energy: on the LEGACY path these
# dimensions are produced by `UniversalAgent._parse_output` (5-7 of the
# dimensions) or a sector-specific custom agent (BFSIUniverseAgent,
# ITTranscriptNLPAgent, REBusinessAgent) — see
# src/backend/shared/agents/universal/agent.py:70-79 and the three custom
# agent modules. ALL of these return the BASE `AgentOutput` class,
# parameterized with `agent=<dimension name>`; none of them declare a
# `sub_scores` field on the base class (custom agents pass a `sub_scores={...}`
# dict kwarg, but pydantic v2's default `extra="ignore"` silently drops it —
# i.e. legacy sub_scores are effectively absent for these 20 dimensions too).
#
# To keep `_parse_dimension`/`_missing_output`/`_error_output` working
# unchanged (they read `output_cls.model_fields["agent"].default` and resolve
# `sub_scores` via `_resolve_sub_scores_model`), we mint one small AgentOutput
# subclass per dimension with `agent: str = "<dimension>"` (matching the
# legacy `agent=` value exactly) and `sub_scores: <Model> | None = None` using
# the dimension's named sub-score model from that sector's
# `schemas/sub_scores.py` (the model the legacy custom agents intended to
# populate). This is additive — `FinalReport.agent_outputs` is
# `dict[str, Any]` and RL is key-agnostic (per the rollout spec), so richer
# sub_scores here is a pure improvement, not a contract change.
# ---------------------------------------------------------------------------

_AUTOMOBILE_CLASSES: dict[str, type[AgentOutput]] = {
    "sales_demand": SalesDemandOutput,
    "raw_materials": RawMaterialsOutput,
    "fundamentals": FundamentalsOutput,
    "pattern_analysis": PatternAnalysisOutput,
    "sentiment": SentimentOutput,
    "policy_regulatory": PolicyRegulatoryOutput,
    "competitive_intel": CompetitiveIntelOutput,
    "risk_macro": RiskMacroOutput,
    "valuation_catalyst": ValuationCatalystOutput,
}


def _make_output_cls(sector_prefix: str, dimension: str, sub_scores_model: type | None) -> type[AgentOutput]:
    """
    Mint an `AgentOutput` subclass for `dimension` with
    `agent: str = dimension` (matches the legacy `agent=` value) and, if
    `sub_scores_model` is given, `sub_scores: sub_scores_model | None = None`.
    For sectors with no sub-score models (sub_scores_model=None), add
    `sub_scores: None = None`.
    """
    fields: dict[str, tuple] = {"agent": (str, dimension)}
    if sub_scores_model is not None:
        fields["sub_scores"] = (sub_scores_model | None, None)
    else:
        # For sectors with no sub-score models (like generic), add a field with type None
        fields["sub_scores"] = (type(None), None)
    return create_model(
        f"{sector_prefix}_{dimension}_Output",
        __base__=AgentOutput,
        **fields,
    )


def _build_sector_classes(
    sector_prefix: str, sub_scores_models: dict[str, type | None]
) -> dict[str, type[AgentOutput]]:
    """Build the dimension -> AgentOutput-subclass map for one new sector."""
    return {
        dim: _make_output_cls(sector_prefix, dim, model)
        for dim, model in sub_scores_models.items()
    }


# --- banking_bfsi -----------------------------------------------------------
from backend.sectors.banking_bfsi.schemas.sub_scores import (
    BFSIFundamentalsAgentSubScores,
    BFSIRiskAgentSubScores,
    BFSIMacroPolicyAgentSubScores,
    BFSIInstitutionalAgentSubScores,
    BFSIPatternAgentSubScores,
    BFSIUniverseAgentSubScores,
)

_BANKING_BFSI_CLASSES: dict[str, type[AgentOutput]] = _build_sector_classes(
    "BankingBFSI",
    {
        "fundamentals": BFSIFundamentalsAgentSubScores,
        "risk": BFSIRiskAgentSubScores,
        "macro_policy": BFSIMacroPolicyAgentSubScores,
        "institutional": BFSIInstitutionalAgentSubScores,
        "pattern_analysis": BFSIPatternAgentSubScores,
        "universe_setup": BFSIUniverseAgentSubScores,
    },
)

# --- it_sector ----------------------------------------------------------------
from backend.sectors.it_sector.schemas.sub_scores import (
    ITFundamentalsAgentSubScores,
    ITGlobalMacroAgentSubScores,
    ITRiskMacroAgentSubScores,
    ITPeerBenchmarkAgentSubScores,
    ITPatternAgentSubScores,
    ITSentimentAgentSubScores,
    ITTranscriptNLPAgentSubScores,
    ITInsiderAgentSubScores,
)

_IT_SECTOR_CLASSES: dict[str, type[AgentOutput]] = _build_sector_classes(
    "ITSector",
    {
        "fundamentals": ITFundamentalsAgentSubScores,
        "global_macro": ITGlobalMacroAgentSubScores,
        "risk_macro": ITRiskMacroAgentSubScores,
        "peer_benchmark": ITPeerBenchmarkAgentSubScores,
        "pattern_analysis": ITPatternAgentSubScores,
        "sentiment": ITSentimentAgentSubScores,
        "transcript_nlp": ITTranscriptNLPAgentSubScores,
        "insider_smart_money": ITInsiderAgentSubScores,
    },
)

# --- renewable_energy -----------------------------------------------------------
from backend.sectors.renewable_energy.schemas.sub_scores import (
    REFundamentalsAgentSubScores,
    REBusinessAgentSubScores,
    REValuationAgentSubScores,
    RESentimentPolicyAgentSubScores,
    RETechnicalAgentSubScores,
    RERiskAgentSubScores,
)

_RENEWABLE_ENERGY_CLASSES: dict[str, type[AgentOutput]] = _build_sector_classes(
    "RenewableEnergy",
    {
        "fundamentals": REFundamentalsAgentSubScores,
        "business": REBusinessAgentSubScores,
        "valuation": REValuationAgentSubScores,
        "sentiment_policy": RESentimentPolicyAgentSubScores,
        "technical": RETechnicalAgentSubScores,
        "risk": RERiskAgentSubScores,
    },
)

# --- generic (Compass Phase B — sector-agnostic graph) -----------------------
GENERIC_DIMENSIONS: list[str] = [
    "business", "fundamentals", "valuation", "technical",
    "macro", "risk", "management", "earnings",
]

# No sub-score models by design: the generic graph is sector-agnostic, and
# _make_output_cls / _parse_dimension already handle sub_scores_model=None.
_GENERIC_CLASSES: dict[str, type[AgentOutput]] = _build_sector_classes(
    "Generic", {dim: None for dim in GENERIC_DIMENSIONS},
)


@dataclass(frozen=True)
class SectorSpec:
    """Per-sector configuration for the Unified Analyst."""

    classes: dict[str, type[AgentOutput]]  # dimension -> output class (defines order)
    prompts_module: str                    # importable module with SYSTEM_PROMPT/ANALYSIS_PROMPT
    has_valuation_extras: bool = False


SECTOR_SPECS: dict[str, SectorSpec] = {
    "automobile": SectorSpec(
        classes=_AUTOMOBILE_CLASSES,
        prompts_module="backend.sectors.automobile.prompts.unified",
        has_valuation_extras=True,
    ),
    "banking_bfsi": SectorSpec(
        classes=_BANKING_BFSI_CLASSES,
        prompts_module="backend.sectors.banking_bfsi.prompts.unified",
        has_valuation_extras=False,
    ),
    "it_sector": SectorSpec(
        classes=_IT_SECTOR_CLASSES,
        prompts_module="backend.sectors.it_sector.prompts.unified",
        has_valuation_extras=False,
    ),
    "renewable_energy": SectorSpec(
        classes=_RENEWABLE_ENERGY_CLASSES,
        prompts_module="backend.sectors.renewable_energy.prompts.unified",
        has_valuation_extras=False,
    ),
    "generic": SectorSpec(
        classes=_GENERIC_CLASSES,
        prompts_module="backend.sectors.generic.prompts.unified",
        has_valuation_extras=False,
    ),
}

DIMENSIONS: dict[str, list[str]] = {s: list(spec.classes) for s, spec in SECTOR_SPECS.items()}

# Dimension that valuation extras (price_target etc.) attach to, per sector
# with has_valuation_extras=True. Automobile-only today.
_VALUATION_EXTRA_DIMENSION = "valuation_catalyst"

# Fields copied onto ValuationCatalystOutput when present and not None.
_VALUATION_EXTRA_FIELDS = [
    "price_target",
    "recovery_timeline_quarters",
    "discount_reason",
    "recovery_catalysts",
    "fair_value_estimate",
    "current_discount_pct",
]

_TEXT_FIELD_CAP = 400
_SUMMARY_CAP = 1200
_MAX_LIST_ITEMS = 5


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# _salvage_truncated_json moved to services/clients/llm_client.py (shared with
# FeedbackAgent). Alias kept so existing imports/tests keep working.
_salvage_truncated_json = salvage_truncated_json


def _resolve_sub_scores_model(output_cls: type[AgentOutput]) -> type | None:
    """
    Resolve the concrete pydantic SubScores model from `output_cls`'s
    `sub_scores` field annotation (e.g. `SalesDemandSubScores | None`).
    """
    field = output_cls.model_fields.get("sub_scores")
    if field is None:
        return None
    annotation = field.annotation
    for arg in typing.get_args(annotation):
        if arg is type(None):
            continue
        return arg
    # Annotation may not be a Union (e.g. directly the model class).
    if annotation is not None and annotation is not type(None):
        return annotation
    return None


class UnifiedAnalyst:
    """
    Sector-generic Unified Analyst: ONE LLM call -> all of that sector's
    dimension AgentOutput subclasses.
    """

    def __init__(self) -> None:
        self._client = get_llm_client()
        self._last_prompt_tokens: int = 0
        self._last_completion_tokens: int = 0

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    def run(
        self,
        query: StockQuery,
        bundle: SectorDataBundle,
        sector: str,
        run_id: str = "",
    ) -> dict[str, AgentOutput]:
        """
        One LLM call -> all dimension outputs for `sector`.

        NEVER raises. Returns {} on:
          - unknown sector (no prompt module / class map)
          - LLM call failure after retries
          - non-JSON / non-dict response
          - any other unexpected error
        """
        try:
            spec = SECTOR_SPECS.get(sector)
            if spec is None:
                logger.error("[UnifiedAnalyst] Unknown sector '%s' — no sector spec", sector)
                return {}
            class_map = spec.classes

            system_prompt, user_prompt = self._build_prompt(query, bundle, sector, spec)
            if system_prompt is None:
                # _build_prompt already logged the error.
                return {}

            t0 = time.time()
            raw = self._call_llm(system_prompt, user_prompt)
            duration_ms = (time.time() - t0) * 1000

            cost = settings.llm_cost_usd(
                settings.LLM_MODEL_REASONING,
                self._last_prompt_tokens, self._last_completion_tokens,
            )
            log_llm_call(
                run_id=run_id, ticker=query.ticker, phase="unified_analyst",
                agent_name=None, model=settings.LLM_MODEL_REASONING,
                prompt_tokens=self._last_prompt_tokens,
                completion_tokens=self._last_completion_tokens,
                duration_ms=duration_ms, cost_usd=cost,
            )

            stripped = (raw or "").strip()
            if stripped.startswith("```"):
                stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
                stripped = re.sub(r"\s*```\s*$", "", stripped).strip()

            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                salvaged = _salvage_truncated_json(stripped)
                if not salvaged:
                    raise
                n_total = len(class_map)
                n_present = sum(1 for dim in class_map if isinstance(salvaged.get(dim), dict))
                logger.warning(
                    "[UnifiedAnalyst] %s/%s: response truncated (%s) — salvaged %d/%d "
                    "dimensions from partial JSON; remaining will degrade to neutral",
                    sector, query.ticker, exc, n_present, n_total,
                )
                data = salvaged

            if not isinstance(data, dict):
                raise ValueError(f"LLM returned {type(data).__name__}, expected dict")

            return self._parse_all(data, query.ticker, class_map, spec)

        except Exception as exc:
            logger.error("[UnifiedAnalyst] run() failed for %s/%s: %s", sector, query.ticker, exc)
            return {}

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self, query: StockQuery, bundle: SectorDataBundle, sector: str, spec: SectorSpec
    ) -> tuple[str | None, str | None]:
        try:
            P = importlib.import_module(spec.prompts_module)
        except ImportError as exc:
            logger.error(
                "[UnifiedAnalyst] No prompt module for sector '%s' (%s): %s",
                sector, spec.prompts_module, exc,
            )
            return None, None

        try:
            system_prompt = P.SYSTEM_PROMPT
            user_prompt = P.ANALYSIS_PROMPT.format(
                ticker=query.ticker,
                company_name=query.company_name,
                report_date=str(date.today()),
                bundle=bundle.to_prompt_text(),
            )
        except AttributeError as exc:
            logger.error(
                "[UnifiedAnalyst] Prompt module '%s' for sector '%s' missing SYSTEM_PROMPT/ANALYSIS_PROMPT: %s",
                spec.prompts_module, sector, exc,
            )
            return None, None

        return system_prompt, user_prompt

    # ------------------------------------------------------------------
    # LLM call (retry x2, mirrors SignalAggregator)
    # ------------------------------------------------------------------

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        retries = 3  # initial attempt + 2 retries
        delay = 1.0
        last_error: Exception | None = None

        for attempt in range(1, retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=settings.LLM_MODEL_REASONING,
                    temperature=0.2,
                    max_tokens=settings.UNIFIED_ANALYST_MAX_TOKENS,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    extra_body=JSON_MODE_EXTRA_BODY,
                )
                content = response.choices[0].message.content or "{}"
                if response.usage:
                    self._last_prompt_tokens = response.usage.prompt_tokens
                    self._last_completion_tokens = response.usage.completion_tokens
                return content

            except RateLimitError as e:
                logger.warning(
                    "[UnifiedAnalyst] Rate limit hit (attempt %d/%d), sleeping %.1fs",
                    attempt, retries, delay,
                )
                last_error = e
                if attempt < retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 2.0)

            except APITimeoutError as e:
                logger.warning("[UnifiedAnalyst] Timeout (attempt %d/%d)", attempt, retries)
                last_error = e
                if attempt < retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 2.0)

            except APIError as e:
                logger.error("[UnifiedAnalyst] API error: %s", e)
                last_error = e
                break

            except Exception as e:
                logger.error("[UnifiedAnalyst] Unexpected error calling LLM: %s", e)
                last_error = e
                if attempt < retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 2.0)

        raise RuntimeError(f"[UnifiedAnalyst] LLM call failed after {retries} attempts: {last_error}")

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_all(
        self, data: dict, ticker: str, class_map: dict[str, type[AgentOutput]], spec: SectorSpec
    ) -> dict[str, AgentOutput]:
        outputs: dict[str, AgentOutput] = {}
        for dim, output_cls in class_map.items():
            block = data.get(dim)
            if not isinstance(block, dict):
                outputs[dim] = self._missing_output(output_cls, ticker)
                continue
            try:
                outputs[dim] = self._parse_dimension(dim, block, output_cls, ticker, spec)
            except Exception as exc:
                logger.error("[UnifiedAnalyst] Parse error for dimension '%s' (%s): %s", dim, ticker, exc)
                outputs[dim] = self._error_output(output_cls, ticker, f"parse_error: {exc}")
        return outputs

    def _missing_output(self, output_cls: type[AgentOutput], ticker: str) -> AgentOutput:
        return output_cls(
            agent=output_cls.model_fields["agent"].default,
            ticker=ticker,
            overall_score=0.5,
            error="missing_in_unified_response",
            data_freshness="unified_analyst",
            summary="Dimension missing from unified analyst response — neutral fallback.",
            key_risks=["no real-time data for this dimension"],
        )

    def _error_output(self, output_cls: type[AgentOutput], ticker: str, error_msg: str) -> AgentOutput:
        return output_cls(
            agent=output_cls.model_fields["agent"].default,
            ticker=ticker,
            overall_score=0.5,
            error=error_msg,
            data_freshness="unified_analyst",
            summary="Dimension failed to parse from unified analyst response — neutral fallback.",
        )

    def _parse_dimension(
        self, dim: str, block: dict, output_cls: type[AgentOutput], ticker: str, spec: SectorSpec
    ) -> AgentOutput:
        score = _clamp(float(block.get("score", 0.5)))

        sub_scores_obj = None
        sub_scores_model = _resolve_sub_scores_model(output_cls)
        if sub_scores_model is not None:
            raw_sub_scores = block.get("sub_scores") or {}
            resolved: dict[str, float] = {}
            for field_name in sub_scores_model.model_fields:
                raw_val = raw_sub_scores.get(field_name)
                if raw_val is None:
                    resolved[field_name] = score
                else:
                    resolved[field_name] = _clamp(float(raw_val))
            sub_scores_obj = sub_scores_model(**resolved)

        key_positives = list(block.get("key_positives") or [])[:_MAX_LIST_ITEMS]
        key_risks = list(block.get("key_risks") or [])[:_MAX_LIST_ITEMS]

        summary = str(block.get("summary", ""))[:_SUMMARY_CAP]
        confidence = block.get("confidence", 0.5)
        try:
            confidence = _clamp(float(confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        kwargs = dict(
            agent=output_cls.model_fields["agent"].default,
            ticker=ticker,
            overall_score=score,
            key_positives=key_positives,
            key_risks=key_risks,
            summary=summary,
            data_freshness="unified_analyst",
            sub_scores=sub_scores_obj,
            ticker_vs_peers=str(block.get("ticker_vs_peers", ""))[:_TEXT_FIELD_CAP],
            bull_case_if=str(block.get("bull_case_if", ""))[:_TEXT_FIELD_CAP],
            bear_case_if=str(block.get("bear_case_if", ""))[:_TEXT_FIELD_CAP],
            what_changed=str(block.get("what_changed", ""))[:_TEXT_FIELD_CAP],
            data_confidence=confidence,
        )

        if spec.has_valuation_extras and dim == _VALUATION_EXTRA_DIMENSION:
            for field_name in _VALUATION_EXTRA_FIELDS:
                if field_name in block and block[field_name] is not None:
                    kwargs[field_name] = block[field_name]

        return output_cls(**kwargs)
