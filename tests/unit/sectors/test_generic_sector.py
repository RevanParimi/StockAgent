"""Compass Phase B — generic sector graph package (spec §4.3 reality check)."""
from core.config import settings


def test_generic_dimensions_order():
    from backend.sectors.generic.prompts.dimensions import DIMENSIONS, PROMPTS
    assert DIMENSIONS == ["business", "fundamentals", "valuation", "technical",
                          "macro", "risk", "management", "earnings"]
    for dim in DIMENSIONS:
        p = PROMPTS[dim]
        assert isinstance(p.SYSTEM_PROMPT, str) and len(p.SYSTEM_PROMPT) > 50
        rendered = p.ANALYSIS_PROMPT.format(ticker="SUNPHARMA",
                                            company_name="Sun Pharma", context="ctx")
        assert "SUNPHARMA" in rendered
        assert isinstance(p.CONTEXT_SEARCH_QUERIES, list)


def test_generic_config_settings_module():
    from backend.sectors.generic.config.settings import AGENT_WEIGHTS, TICKERS
    assert AGENT_WEIGHTS == settings.GENERIC_AGENT_WEIGHTS
    assert TICKERS == []


def test_generic_orchestrator_constructs_with_8_agents():
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    orch = GenericSectorOrchestrator()
    assert orch.SECTOR_NAME == "generic"
    assert set(orch._sub_agents) == {"business", "fundamentals", "valuation",
                                     "technical", "macro", "risk",
                                     "management", "earnings"}
    assert abs(sum(orch._get_default_weights().values()) - 1.0) < 1e-9


def test_generic_unified_prompt_module_contract():
    import backend.sectors.generic.prompts.unified as U
    assert "JSON" in U.SYSTEM_PROMPT
    rendered = U.ANALYSIS_PROMPT.format(ticker="SUNPHARMA", company_name="Sun Pharma",
                                        report_date="2026-07-07", bundle="BUNDLE")
    assert "SUNPHARMA" in rendered and "BUNDLE" in rendered
    for dim in ["business", "fundamentals", "valuation", "technical",
                "macro", "risk", "management", "earnings"]:
        assert dim in rendered
