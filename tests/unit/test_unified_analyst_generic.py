"""Compass Phase B — 'generic' sector on the Unified Analyst one-call path."""
import json

from backend.shared.pipeline.unified_analyst import (
    DIMENSIONS, SECTOR_SPECS, UnifiedAnalyst,
)
from backend.shared.schemas.pipeline import StockQuery


GENERIC_DIMS = ["business", "fundamentals", "valuation", "technical",
                "macro", "risk", "management", "earnings"]


def test_generic_sector_spec_registered():
    assert "generic" in SECTOR_SPECS
    assert DIMENSIONS["generic"] == GENERIC_DIMS
    spec = SECTOR_SPECS["generic"]
    assert spec.prompts_module == "backend.sectors.generic.prompts.unified"
    assert spec.has_valuation_extras is False


def _fake_response() -> str:
    block = {"score": 0.7, "confidence": 0.7, "key_positives": ["strong growth"],
             "key_risks": ["fx risk"], "summary": "Fine.", "ticker_vs_peers": "cheaper",
             "bull_case_if": "order win", "bear_case_if": "margin miss",
             "what_changed": "nothing"}
    return json.dumps({dim: dict(block) for dim in GENERIC_DIMS})


def test_generic_run_parses_all_8_dimensions(monkeypatch):
    ua = UnifiedAnalyst.__new__(UnifiedAnalyst)   # skip __init__ (no LLM client)
    ua._last_prompt_tokens = 0
    ua._last_completion_tokens = 0
    monkeypatch.setattr(UnifiedAnalyst, "_call_llm",
                        lambda self, s, u: _fake_response())

    class _Bundle:
        api_calls_made: dict = {}
        has_real_data = True
        def to_prompt_text(self) -> str: return "BUNDLE"

    query = StockQuery(ticker="SUNPHARMA", company_name="Sun Pharma")
    outputs = ua.run(query, _Bundle(), "generic")
    assert set(outputs) == set(GENERIC_DIMS)
    assert outputs["fundamentals"].overall_score == 0.7
    assert outputs["risk"].agent == "risk"
    assert outputs["technical"].sub_scores is None   # generic dims have no sub-score models


def test_generic_bundle_cfg_registered():
    from services.data.context.bundle_builder import _SECTOR_BUNDLE_CFG
    cfg = _SECTOR_BUNDLE_CFG["generic"]
    assert cfg["has_commodities"] is False
    assert cfg["macro_cache_key"] == "generic"
    assert cfg["peer_tickers_module"] is None
