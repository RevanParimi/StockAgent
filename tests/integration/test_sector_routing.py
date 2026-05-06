"""
Sector routing integration tests.

Verifies that detect_sector() maps tickers to the correct sector,
and that get_orchestrator() returns the right class for each sector.
No LLM calls, no network — purely import + class identity checks.
"""
import pytest
from backend.sectors import detect_sector, get_orchestrator


# ── detect_sector() ────────────────────────────────────────────────────────

class TestDetectSector:

    @pytest.mark.parametrize("ticker,expected", [
        # Automobile (default)
        ("MARUTI",      "automobile"),
        ("TATAMOTORS",  "automobile"),
        ("BAJAJ-AUTO",  "automobile"),
        ("EICHERMOT",   "automobile"),
        ("ASHOKLEY",    "automobile"),
        # Banking BFSI
        ("HDFCBANK",    "banking_bfsi"),
        ("ICICIBANK",   "banking_bfsi"),
        ("SBIN",        "banking_bfsi"),
        ("KOTAKBANK",   "banking_bfsi"),
        ("AXISBANK",    "banking_bfsi"),
        ("BAJFINANCE",  "banking_bfsi"),
        # IT Sector
        ("TCS",         "it_sector"),
        ("INFY",        "it_sector"),
        ("WIPRO",       "it_sector"),
        ("HCLTECH",     "it_sector"),
        ("TECHM",       "it_sector"),
        ("LTIM",        "it_sector"),
        # Renewable Energy
        ("ADANIGREEN",  "renewable_energy"),
        ("TATAPOWER",   "renewable_energy"),
        ("SJVN",        "renewable_energy"),
        ("NHPC",        "renewable_energy"),
        # Unknown → automobile fallback
        ("UNKNOWN",     "automobile"),
        ("RELIANCEXYZ", "automobile"),
    ])
    def test_ticker_routes_to_correct_sector(self, ticker, expected):
        assert detect_sector(ticker) == expected

    def test_case_insensitive(self):
        assert detect_sector("hdfcbank") == "banking_bfsi"
        assert detect_sector("TCS") == "it_sector"
        assert detect_sector("maruti") == "automobile"

    def test_with_whitespace(self):
        assert detect_sector("  MARUTI  ") == "automobile"


# ── get_orchestrator() ─────────────────────────────────────────────────────

class TestGetOrchestrator:

    def test_automobile_orchestrator(self):
        from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator
        cls = get_orchestrator("automobile")
        assert cls is AutomobileAgentOrchestrator

    def test_banking_orchestrator(self):
        from backend.sectors.banking_bfsi.pipeline.orchestrator import BankingAgentOrchestrator
        cls = get_orchestrator("banking_bfsi")
        assert cls is BankingAgentOrchestrator

    def test_it_orchestrator(self):
        from backend.sectors.it_sector.pipeline.orchestrator import ITAgentOrchestrator
        cls = get_orchestrator("it_sector")
        assert cls is ITAgentOrchestrator

    def test_renewable_orchestrator(self):
        from backend.sectors.renewable_energy.pipeline.orchestrator import RenewableAgentOrchestrator
        cls = get_orchestrator("renewable_energy")
        assert cls is RenewableAgentOrchestrator

    def test_unknown_sector_falls_back_to_automobile(self):
        from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator
        cls = get_orchestrator("unknown_sector_xyz")
        assert cls is AutomobileAgentOrchestrator

    def test_all_orchestrators_extend_base(self):
        from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
        for sector in ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]:
            cls = get_orchestrator(sector)
            assert issubclass(cls, BaseSectorOrchestrator), \
                f"{cls.__name__} must extend BaseSectorOrchestrator"

    def test_sector_name_attribute(self):
        expected = {
            "automobile":      "automobile",
            "banking_bfsi":    "banking_bfsi",
            "it_sector":       "it_sector",
            "renewable_energy":"renewable_energy",
        }
        for sector, name in expected.items():
            cls = get_orchestrator(sector)
            assert cls.SECTOR_NAME == name, \
                f"{cls.__name__}.SECTOR_NAME should be {name!r}, got {cls.SECTOR_NAME!r}"
