"""
tests/unit/test_unified_e2e_parity_sectors.py
==============================================
End-to-end FinalReport contract parity for the Unified Sector Analyst
(sector rollout, 2026-06-13) — banking_bfsi, it_sector, renewable_energy.

Mirrors tests/unit/test_unified_e2e_parity.py (automobile) but covers the
three newly-enabled sectors. Runs the REAL <sector>AgentOrchestrator + REAL
SignalAggregator code with UNIFIED_ANALYST_SECTORS set to the sector under
test. Only LLM calls and fetchers are mocked (no network):
  - _resolve_ticker            -> StockQuery(ticker=<sector ticker>, ...)
  - _prefetch_nse_data          -> no-op
  - build_sector_bundle          -> a tiny SectorDataBundle (patched at the
                                     source module so the call-time
                                     `from services.data.context.bundle_builder
                                     import build_sector_bundle` inside
                                     _run_unified resolves to the mock)
  - UnifiedAnalyst._call_llm     -> JSON for all of that sector's
                                     dimensions, every score 0.65
  - SignalAggregator._call_llm   -> verdict JSON (BUY)

Asserts FinalReport keeps the same shape as the legacy multi-agent path:
  - weighted_agent_scores / agent_outputs keys == DIMENSIONS[sector]
  - verdict in the 5-value enum

Sync path is sufficient here; async is covered for automobile in
test_unified_e2e_parity.py.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.shared.pipeline import base_orchestrator as bo_mod
from backend.shared.pipeline.unified_analyst import DIMENSIONS, UnifiedAnalyst
from backend.shared.pipeline.signal_aggregator import SignalAggregator
from core.schemas.pipeline import StockQuery
from services.data.context.bundle_builder import SectorDataBundle

VALID_VERDICTS = {"STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"}


SECTOR_CASES = [
    pytest.param(
        "banking_bfsi",
        "backend.sectors.banking_bfsi.pipeline.orchestrator",
        "BankingAgentOrchestrator",
        "HDFCBANK",
        "HDFC Bank",
        "HDFC Bank reported strong Q4 NIM expansion.",
        id="banking_bfsi",
    ),
    pytest.param(
        "it_sector",
        "backend.sectors.it_sector.pipeline.orchestrator",
        "ITAgentOrchestrator",
        "INFY",
        "Infosys",
        "Infosys reported strong Q4 deal wins.",
        id="it_sector",
    ),
    pytest.param(
        "renewable_energy",
        "backend.sectors.renewable_energy.pipeline.orchestrator",
        "RenewableAgentOrchestrator",
        "TATAPOWER",
        "Tata Power",
        "Tata Power commissioned new solar capacity.",
        id="renewable_energy",
    ),
]


def _unified_analyst_payload(sector: str, score: float = 0.65) -> dict:
    payload: dict = {}
    for dim in DIMENSIONS[sector]:
        payload[dim] = {
            "score": score,
            "confidence": 0.8,
            "summary": f"{dim} summary.",
            "key_positives": ["positive driver"],
            "key_risks": ["some risk"],
            "sub_scores": {},
            "ticker_vs_peers": "vs peers",
            "bull_case_if": "bull case",
            "bear_case_if": "bear case",
            "what_changed": "no major change",
        }
    return payload


def _aggregator_verdict_payload() -> dict:
    return {
        "final_score": 0.65,
        "verdict": "BUY",
        "conflicts_resolved": [],
        "conviction_drivers": ["Strong fundamentals", "Improving outlook"],
        "top_risks": ["Sector risk"],
        "executive_summary": "Looks healthy near-term.",
        "investment_thesis": "Solid pick on current trends.",
        "report_date": "2026-06-13",
    }


def _make_llm_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=200)
    return response


@pytest.mark.parametrize(
    "sector, orchestrator_module, orchestrator_cls, ticker, company_name, news",
    SECTOR_CASES,
)
def test_unified_e2e_final_report_contract_parity(
    monkeypatch, sector, orchestrator_module, orchestrator_cls, ticker, company_name, news,
):
    monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", sector)
    monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_FALLBACK_LEGACY", True)

    import importlib
    mod = importlib.import_module(orchestrator_module)
    OrchestratorCls = getattr(mod, orchestrator_cls)

    orchestrator = OrchestratorCls()

    query = StockQuery(ticker=ticker, company_name=company_name)
    bundle = SectorDataBundle(
        sections={"company_news": news},
        has_real_data=True,
        api_calls_made={"serper": 3, "tavily": 1},
    )

    unified_response = _make_llm_response(json.dumps(_unified_analyst_payload(sector)))
    aggregator_response = _make_llm_response(json.dumps(_aggregator_verdict_payload()))

    with patch.object(orchestrator, "_resolve_ticker", return_value=query), \
         patch.object(orchestrator, "_prefetch_nse_data"), \
         patch("services.data.context.bundle_builder.build_sector_bundle", return_value=bundle), \
         patch.object(UnifiedAnalyst, "_call_llm", return_value=unified_response.choices[0].message.content) as mock_unified_llm, \
         patch.object(SignalAggregator, "_call_llm", return_value=aggregator_response.choices[0].message.content) as mock_agg_llm:

        report = orchestrator.analyse(ticker.lower())

    mock_unified_llm.assert_called_once()
    mock_agg_llm.assert_called_once()

    expected_dims = set(DIMENSIONS[sector])
    assert set(report.weighted_agent_scores) == expected_dims
    assert set(report.agent_outputs) == expected_dims

    assert report.verdict in VALID_VERDICTS
    assert report.verdict == "BUY"
