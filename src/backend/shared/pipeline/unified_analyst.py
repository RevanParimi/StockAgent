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

import json
import logging
import re
import time
import typing
from datetime import date

from openai import APIError, APITimeoutError, RateLimitError

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
from services.clients.llm_client import get_llm_client
from services.data.context.bundle_builder import SectorDataBundle
from services.data.stores.run_logger import log_llm_call

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dimension -> AgentOutput class maps (per sector)
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

DIMENSIONS: dict[str, list[str]] = {
    "automobile": list(_AUTOMOBILE_CLASSES),
}

_SECTOR_CLASS_MAPS: dict[str, dict[str, type[AgentOutput]]] = {
    "automobile": _AUTOMOBILE_CLASSES,
}

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


def _salvage_truncated_json(raw: str) -> dict:
    """
    Best-effort recovery of a partial top-level JSON object from `raw` when
    `json.loads(raw)` fails (e.g. the response was cut off mid-stream by a
    max_tokens cap).

    Strategy: walk the string tracking string/escape state and brace depth.
    Each time depth returns to 1 immediately after a `}` (i.e. a top-level
    key's object value has just fully closed), record that index as a
    candidate salvage point. Take the LAST such point, truncate the string
    there, strip a trailing comma, and append `}` to close the top-level
    object. Returns {} if nothing salvageable (including on any error, or if
    `raw` doesn't even open a top-level `{`).

    Safe to call on valid, complete JSON too — it will simply return the
    parsed dict if the whole string parses after the salvage transform falls
    back to the full string, or {} if nothing better is found. (In practice
    `run()` only calls this after `json.loads(raw)` has already failed.)
    """
    if not raw:
        return {}

    depth = 0
    in_string = False
    escape = False
    last_complete_idx: int | None = None
    started = False

    for i, ch in enumerate(raw):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 1:
                # A top-level value's object just closed cleanly.
                last_complete_idx = i

    if last_complete_idx is None:
        return {}

    candidate = raw[: last_complete_idx + 1].rstrip()
    candidate = candidate.rstrip(",")
    candidate += "}"

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return {}

    return parsed if isinstance(parsed, dict) else {}


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
            class_map = _SECTOR_CLASS_MAPS.get(sector)
            if class_map is None:
                logger.error("[UnifiedAnalyst] Unknown sector '%s' — no prompt module/class map", sector)
                return {}

            system_prompt, user_prompt = self._build_prompt(query, bundle, sector)
            if system_prompt is None:
                # _build_prompt already logged the error.
                return {}

            t0 = time.time()
            raw = self._call_llm(system_prompt, user_prompt)
            duration_ms = (time.time() - t0) * 1000

            cost = (
                self._last_prompt_tokens * settings.LLM_INPUT_COST_PER_M
                + self._last_completion_tokens * settings.LLM_OUTPUT_COST_PER_M
            ) / 1_000_000
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

            return self._parse_all(data, query.ticker, class_map)

        except Exception as exc:
            logger.error("[UnifiedAnalyst] run() failed for %s/%s: %s", sector, query.ticker, exc)
            return {}

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self, query: StockQuery, bundle: SectorDataBundle, sector: str
    ) -> tuple[str | None, str | None]:
        if sector == "automobile":
            from backend.sectors.automobile.prompts import unified as P
        else:
            logger.error("[UnifiedAnalyst] No prompt module for sector '%s'", sector)
            return None, None

        system_prompt = P.SYSTEM_PROMPT
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name,
            report_date=str(date.today()),
            bundle=bundle.to_prompt_text(),
        )
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
        self, data: dict, ticker: str, class_map: dict[str, type[AgentOutput]]
    ) -> dict[str, AgentOutput]:
        outputs: dict[str, AgentOutput] = {}
        for dim, output_cls in class_map.items():
            block = data.get(dim)
            if not isinstance(block, dict):
                outputs[dim] = self._missing_output(output_cls, ticker)
                continue
            try:
                outputs[dim] = self._parse_dimension(dim, block, output_cls, ticker)
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
        self, dim: str, block: dict, output_cls: type[AgentOutput], ticker: str
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

        if output_cls is ValuationCatalystOutput:
            for field_name in _VALUATION_EXTRA_FIELDS:
                if field_name in block and block[field_name] is not None:
                    kwargs[field_name] = block[field_name]

        return output_cls(**kwargs)
