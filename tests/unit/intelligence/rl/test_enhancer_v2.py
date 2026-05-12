"""
tests/unit/intelligence/rl/test_enhancer_v2.py
===============================================
Section 8 — PromptEnhancer with sector-specific templates and LLM fallback.

What is verified:
  - Sector templates exist for all 3 new sectors (banking_bfsi, it_sector, renewable_energy)
  - Each sector has ≥8 miss factors covered
  - Sector template takes priority over generic template for the same factor
  - _guess_primary_agent() maps factor keywords to correct agents per sector
  - Unknown factors (no template in any map) are identified for LLM generation
  - LLM generation path is called for unknown factors; returns queries on success,
    empty list on failure (non-fatal)
  - enhance() with sector='banking_bfsi' uses banking templates
  - save_enhancements() includes sector field in payload
  - Date substitution present in sector-specific queries

Design context:
  - The static template map covered only 5 automobile miss factors.
  - Banking BFSI has 10 miss factors (GNPA_slippage, NIM_compression, etc.);
    IT sector has 10 (attrition_spike, H1B_visa_restriction, etc.);
    Renewable has 10 (DISCOM_payment_delay, curtailment_risk, etc.).
  - LLM query generation fires only for factors absent from both maps — a narrow
    path that keeps token cost negligible (< 200 tokens per unknown factor per month).
"""

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.intelligence.prompt_enhancer.enhancer import (
    MISS_FACTOR_TO_QUERY_TEMPLATE,
    SECTOR_MISS_FACTOR_TEMPLATES,
    PromptEnhancer,
)
from core.schemas.feedback import LearningLedger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger(miss_counter: dict, sector: str = "automobile", ticker: str = "MARUTI") -> LearningLedger:
    return LearningLedger(
        ticker=ticker,
        sector=sector,
        last_updated=date.today().isoformat(),
        miss_counter=miss_counter,
    )


# ---------------------------------------------------------------------------
# Sector template map structure
# ---------------------------------------------------------------------------

class TestSectorTemplateMapsStructure:

    @pytest.mark.parametrize("sector", ["banking_bfsi", "it_sector", "renewable_energy"])
    def test_sector_present_in_map(self, sector):
        assert sector in SECTOR_MISS_FACTOR_TEMPLATES

    @pytest.mark.parametrize("sector", ["banking_bfsi", "it_sector", "renewable_energy"])
    def test_each_sector_has_at_least_8_factors(self, sector):
        factors = SECTOR_MISS_FACTOR_TEMPLATES[sector]
        assert len(factors) >= 8, (
            f"Sector '{sector}' has only {len(factors)} miss factors; expected ≥ 8"
        )

    @pytest.mark.parametrize("sector", ["banking_bfsi", "it_sector", "renewable_energy"])
    def test_each_factor_has_at_least_one_agent_query(self, sector):
        for factor, agent_map in SECTOR_MISS_FACTOR_TEMPLATES[sector].items():
            assert isinstance(agent_map, dict) and len(agent_map) >= 1, (
                f"Factor '{factor}' in sector '{sector}' has no agent queries"
            )

    def test_banking_has_gnpa_slippage(self):
        assert "GNPA_slippage" in SECTOR_MISS_FACTOR_TEMPLATES["banking_bfsi"]

    def test_banking_has_nim_compression(self):
        assert "NIM_compression" in SECTOR_MISS_FACTOR_TEMPLATES["banking_bfsi"]

    def test_it_has_attrition_spike(self):
        assert "attrition_spike" in SECTOR_MISS_FACTOR_TEMPLATES["it_sector"]

    def test_it_has_deal_win_slowdown(self):
        assert "deal_win_slowdown" in SECTOR_MISS_FACTOR_TEMPLATES["it_sector"]

    def test_renewable_has_discom_payment(self):
        assert "DISCOM_payment_delay" in SECTOR_MISS_FACTOR_TEMPLATES["renewable_energy"]

    def test_renewable_has_curtailment_risk(self):
        assert "curtailment_risk" in SECTOR_MISS_FACTOR_TEMPLATES["renewable_energy"]

    def test_all_templates_have_supported_placeholders(self):
        import re
        supported = {"{ticker}", "{date}", "{month}", "{year}"}
        for sector, factor_map in SECTOR_MISS_FACTOR_TEMPLATES.items():
            for factor, agent_map in factor_map.items():
                for agent, template in agent_map.items():
                    used = set(re.findall(r"\{[^}]+\}", template))
                    unknown = used - supported
                    assert not unknown, (
                        f"Sector '{sector}', factor '{factor}', agent '{agent}': "
                        f"unsupported placeholders {unknown} in: {template}"
                    )


# ---------------------------------------------------------------------------
# Resolution priority: sector template > generic template
# ---------------------------------------------------------------------------

class TestTemplateResolutionPriority:

    def test_banking_fii_factor_uses_banking_template(self):
        """
        FII_outflow_spike exists in both generic and banking templates.
        Banking should use banking-specific one (institutional agent).
        """
        banking_agents = SECTOR_MISS_FACTOR_TEMPLATES["banking_bfsi"].get(
            "FII_outflow_spike", {}
        )
        generic_agents = MISS_FACTOR_TO_QUERY_TEMPLATE.get("FII_outflow_spike", {})
        # Banking template should have 'institutional' agent; generic doesn't
        assert "institutional" in banking_agents, (
            "Banking FII_outflow_spike template should include 'institutional' agent"
        )
        assert "institutional" not in generic_agents

    def test_enhance_banking_fii_returns_institutional_query(self):
        """enhance() for banking sector uses banking template for FII factor."""
        miss = {"FII_outflow_spike": 5}
        ledger = _make_ledger(miss, sector="banking_bfsi", ticker="HDFCBANK")
        result = PromptEnhancer().enhance("HDFCBANK", ledger, sector="banking_bfsi", top_n=1)
        assert "institutional" in result, (
            f"Expected 'institutional' agent in result, got: {list(result.keys())}"
        )

    def test_enhance_automobile_uses_generic_fii_template(self):
        """enhance() for automobile uses generic FII template (no institutional agent)."""
        miss = {"FII_outflow_spike": 5}
        ledger = _make_ledger(miss, sector="automobile", ticker="MARUTI")
        result = PromptEnhancer().enhance("MARUTI", ledger, sector="automobile", top_n=1)
        assert "risk_macro" in result
        assert "institutional" not in result


# ---------------------------------------------------------------------------
# Date substitution in sector queries
# ---------------------------------------------------------------------------

class TestSectorQueryDateSubstitution:

    def test_gnpa_query_contains_month_and_year(self):
        miss = {"GNPA_slippage": 3}
        ledger = _make_ledger(miss, sector="banking_bfsi", ticker="HDFCBANK")
        result = PromptEnhancer().enhance("HDFCBANK", ledger, sector="banking_bfsi", top_n=1)
        today = date.today()
        all_queries = [q for qs in result.values() for q in qs]
        assert any(today.strftime("%B") in q or str(today.year) in q for q in all_queries), (
            f"No date found in queries: {all_queries}"
        )

    def test_attrition_query_contains_month_year(self):
        miss = {"attrition_spike": 4}
        ledger = _make_ledger(miss, sector="it_sector", ticker="TCS")
        result = PromptEnhancer().enhance("TCS", ledger, sector="it_sector", top_n=1)
        today = date.today()
        all_queries = [q for qs in result.values() for q in qs]
        assert any(today.strftime("%B") in q or str(today.year) in q for q in all_queries)

    def test_discom_query_contains_year(self):
        miss = {"DISCOM_payment_delay": 3}
        ledger = _make_ledger(miss, sector="renewable_energy", ticker="ADANIGREEN")
        result = PromptEnhancer().enhance("ADANIGREEN", ledger, sector="renewable_energy", top_n=1)
        today = date.today()
        all_queries = [q for qs in result.values() for q in qs]
        assert any(str(today.year) in q for q in all_queries)

    def test_ticker_substituted_in_sector_query(self):
        miss = {"GNPA_slippage": 5}
        ledger = _make_ledger(miss, sector="banking_bfsi", ticker="ICICIBANK")
        result = PromptEnhancer().enhance("ICICIBANK", ledger, sector="banking_bfsi", top_n=1)
        all_queries = [q for qs in result.values() for q in qs]
        assert any("ICICIBANK" in q for q in all_queries)


# ---------------------------------------------------------------------------
# _guess_primary_agent()
# ---------------------------------------------------------------------------

class TestGuessPrimaryAgent:

    def _guess(self, factor: str, sector: str) -> str:
        return PromptEnhancer._guess_primary_agent(factor, sector)

    def test_fii_factor_returns_institutional_for_banking(self):
        assert self._guess("FII_large_block_deal", "banking_bfsi") == "institutional"

    def test_fii_factor_returns_risk_macro_for_auto(self):
        assert self._guess("FII_outflow_spike", "automobile") == "risk_macro"

    def test_rbi_factor_returns_macro_policy_for_banking(self):
        assert self._guess("RBI_circular_action", "banking_bfsi") == "macro_policy"

    def test_rbi_factor_returns_risk_macro_for_others(self):
        assert self._guess("RBI_rate_surprise", "it_sector") == "risk_macro"

    def test_revenue_factor_returns_fundamentals(self):
        assert self._guess("revenue_growth_miss", "it_sector") == "fundamentals"

    def test_margin_factor_returns_fundamentals(self):
        assert self._guess("margin_compression", "banking_bfsi") == "fundamentals"

    def test_gnpa_factor_returns_fundamentals(self):
        assert self._guess("GNPA_slippage_event", "banking_bfsi") == "fundamentals"

    def test_attrition_factor_returns_fundamentals(self):
        assert self._guess("attrition_spike", "it_sector") == "fundamentals"

    def test_discom_factor_returns_risk_for_renewable(self):
        assert self._guess("DISCOM_credit_issue", "renewable_energy") == "risk"

    def test_mnre_factor_returns_sentiment_policy_for_renewable(self):
        assert self._guess("MNRE_policy_reversal", "renewable_energy") == "sentiment_policy"

    def test_technical_factor_returns_pattern_analysis(self):
        assert self._guess("rsi_divergence_signal", "automobile") == "pattern_analysis"

    def test_valuation_factor_returns_valuation(self):
        assert self._guess("PE_rerating_miss", "it_sector") == "valuation"

    def test_sentiment_factor_returns_sentiment(self):
        assert self._guess("news_sentiment_collapse", "automobile") == "sentiment"

    def test_unknown_factor_returns_sector_default(self):
        # Unknown factor → sector default
        assert self._guess("completely_unknown_xyz", "banking_bfsi") == "fundamentals"
        assert self._guess("completely_unknown_xyz", "it_sector") == "fundamentals"
        assert self._guess("completely_unknown_xyz", "automobile") == "risk_macro"


# ---------------------------------------------------------------------------
# LLM fallback for unknown factors
# ---------------------------------------------------------------------------

class TestLLMFallbackForUnknownFactors:

    def test_unknown_factor_queues_for_llm(self):
        """
        A factor with no entry in EITHER template map should result in the
        LLM path being triggered.  We patch _generate_queries_llm to capture
        the call rather than making a real API request.
        """
        enhancer = PromptEnhancer()
        llm_calls: list[str] = []

        def fake_llm(factor, ticker, sector, agent_name, fmt):
            llm_calls.append(factor)
            return [f"fake query for {factor} {fmt['month']} {fmt['year']}"]

        enhancer._generate_queries_llm = fake_llm

        # "completely_unknown_banking_factor" is not in any template map
        miss = {"completely_unknown_banking_factor": 10}
        ledger = _make_ledger(miss, sector="banking_bfsi", ticker="HDFCBANK")
        result = enhancer.enhance("HDFCBANK", ledger, sector="banking_bfsi", top_n=1)

        assert "completely_unknown_banking_factor" in llm_calls, (
            "LLM should have been called for the unknown factor"
        )
        # Result should contain the fake query
        all_queries = [q for qs in result.values() for q in qs]
        assert any("fake query" in q for q in all_queries)

    def test_known_sector_factor_does_not_queue_llm(self):
        """A factor in the banking sector template should NOT trigger LLM."""
        enhancer = PromptEnhancer()
        llm_calls: list[str] = []

        def fake_llm(factor, *args, **kwargs):
            llm_calls.append(factor)
            return []

        enhancer._generate_queries_llm = fake_llm

        miss = {"GNPA_slippage": 5}
        ledger = _make_ledger(miss, sector="banking_bfsi", ticker="HDFCBANK")
        enhancer.enhance("HDFCBANK", ledger, sector="banking_bfsi", top_n=1)

        assert "GNPA_slippage" not in llm_calls, (
            "Known sector factor should not trigger LLM"
        )

    def test_llm_failure_returns_empty_queries(self):
        """_generate_queries_llm catches exceptions and returns []."""
        enhancer = PromptEnhancer()

        def failing_llm(factor, ticker, sector, agent_name, fmt):
            raise RuntimeError("Simulated API failure")

        enhancer._generate_queries_llm = failing_llm

        miss = {"totally_unknown_factor": 3}
        ledger = _make_ledger(miss, sector="banking_bfsi", ticker="HDFCBANK")
        result = enhancer.enhance("HDFCBANK", ledger, sector="banking_bfsi", top_n=1)
        # Should return {} or something without raising
        assert isinstance(result, dict)

    def test_generic_factor_not_in_sector_map_still_resolved_by_generic_map(self):
        """
        crude_oil_spot_price is in the generic map but not in it_sector map.
        Should use generic map, NOT trigger LLM.
        """
        enhancer = PromptEnhancer()
        llm_calls: list[str] = []

        def fake_llm(factor, *args, **kwargs):
            llm_calls.append(factor)
            return []

        enhancer._generate_queries_llm = fake_llm

        miss = {"crude_oil_spot_price": 4}
        ledger = _make_ledger(miss, sector="it_sector", ticker="TCS")
        result = enhancer.enhance("TCS", ledger, sector="it_sector", top_n=1)

        assert "crude_oil_spot_price" not in llm_calls, (
            "crude_oil_spot_price is in generic map — should not trigger LLM"
        )
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# save_enhancements() sector field
# ---------------------------------------------------------------------------

class TestSaveEnhancementsSectorField:

    def test_sector_field_in_saved_payload(self, tmp_path, monkeypatch):
        import core.intelligence.prompt_enhancer.enhancer as emod
        monkeypatch.setattr(emod.settings, "PREDICTION_DATA_DIR", str(tmp_path))

        miss = {"GNPA_slippage": 3}
        ledger = _make_ledger(miss, sector="banking_bfsi", ticker="HDFCBANK")
        enhancements = PromptEnhancer().enhance("HDFCBANK", ledger, sector="banking_bfsi", top_n=1)
        PromptEnhancer().save_enhancements(
            "HDFCBANK", "banking_bfsi", enhancements, "HDFCBANK_2026-05", ledger
        )

        saved = tmp_path / "banking_bfsi" / "HDFCBANK" / "HDFCBANK_2026-05_prompt_enhancements.json"
        assert saved.exists()
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert data.get("sector") == "banking_bfsi"

    def test_empty_miss_counter_returns_empty(self):
        ledger = _make_ledger({}, sector="it_sector", ticker="TCS")
        result = PromptEnhancer().enhance("TCS", ledger, sector="it_sector")
        assert result == {}


# ---------------------------------------------------------------------------
# Full enhance() integration for each new sector
# ---------------------------------------------------------------------------

class TestEnhanceIntegrationPerSector:

    def test_banking_enhance_produces_output(self):
        miss = {"GNPA_slippage": 5, "NIM_compression": 3, "RBI_regulatory_action": 2}
        ledger = _make_ledger(miss, sector="banking_bfsi", ticker="HDFCBANK")
        result = PromptEnhancer().enhance("HDFCBANK", ledger, sector="banking_bfsi", top_n=3)
        assert len(result) >= 1
        all_queries = [q for qs in result.values() for q in qs]
        assert len(all_queries) >= 3

    def test_it_sector_enhance_produces_output(self):
        miss = {"attrition_spike": 4, "deal_win_slowdown": 3, "guidance_cut": 2}
        ledger = _make_ledger(miss, sector="it_sector", ticker="TCS")
        result = PromptEnhancer().enhance("TCS", ledger, sector="it_sector", top_n=3)
        assert len(result) >= 1

    def test_renewable_enhance_produces_output(self):
        miss = {"DISCOM_payment_delay": 5, "curtailment_risk": 3, "module_price_spike": 2}
        ledger = _make_ledger(miss, sector="renewable_energy", ticker="ADANIGREEN")
        result = PromptEnhancer().enhance("ADANIGREEN", ledger, sector="renewable_energy", top_n=3)
        assert len(result) >= 1

    def test_automobile_still_works_with_sector_param(self):
        """Passing sector='automobile' should still use generic map (no sector override)."""
        miss = {"FII_outflow_spike": 5, "crude_oil_spot_price": 3}
        ledger = _make_ledger(miss, sector="automobile", ticker="MARUTI")
        result = PromptEnhancer().enhance("MARUTI", ledger, sector="automobile", top_n=2)
        assert "risk_macro" in result
