"""Compass Phase B — unknown sectors route to the generic graph, not automobile."""
from core.config import settings
from core.intelligence.rl.workflows import sector_router as sr


def test_native_sectors_unchanged():
    assert sr.NATIVE_SECTORS == frozenset(
        {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
    )
    assert sr._ORCHESTRATORS["automobile"].endswith("AutomobileAgentOrchestrator")


def test_unknown_sector_gets_generic_orchestrator():
    orch = sr.get_orchestrator("pharma")
    assert type(orch).__name__ == "GenericSectorOrchestrator"
    assert orch.SECTOR_NAME == "generic"


def test_unknown_sector_gets_generic_weights():
    w = sr.get_sector_weights("pharma")
    assert w == settings.GENERIC_AGENT_WEIGHTS


def test_native_sector_still_gets_native_weights():
    w = sr.get_sector_weights("automobile")
    assert "sales_demand" in w        # automobile agent name — not a generic dim


def test_scheduler_sector_lookup_uses_managed_tickers(monkeypatch):
    import services.scheduler.python.scheduler as sched
    monkeypatch.setattr(
        sched, "get_active_tickers_with_sector",
        lambda: [{"sym": "SUNPHARMA", "sector": "pharma"},
                 {"sym": "MARUTI", "sector": "automobile"}],
        raising=False,
    )
    lookup = sched._sector_lookup()
    assert lookup["SUNPHARMA"] == "pharma"
    assert lookup["MARUTI"] == "automobile"
