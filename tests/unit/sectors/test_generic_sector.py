"""Compass Phase B — generic sector graph package (spec §4.3 reality check)."""
from core.config import settings


def test_generic_config_settings_module():
    from backend.sectors.generic.config.settings import AGENT_WEIGHTS, TICKERS
    assert AGENT_WEIGHTS == settings.GENERIC_AGENT_WEIGHTS
    assert TICKERS == []


def test_generic_orchestrator_scores_8_dimensions_in_one_call():
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    from backend.shared.pipeline.unified_analyst import DIMENSIONS
    orch = GenericSectorOrchestrator()
    assert orch.SECTOR_NAME == "generic"
    assert set(DIMENSIONS["generic"]) == {"business", "fundamentals", "valuation",
                                          "technical", "macro", "risk",
                                          "management", "earnings"}
    assert set(orch._get_default_weights()) == set(DIMENSIONS["generic"])
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
