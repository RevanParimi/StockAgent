"""
tests/unit/test_ticker_resolution_shortcircuit.py
==================================================
Exact managed-ticker short-circuit in BaseSectorOrchestrator._resolve_ticker.

Bug: every input (including exact managed tickers like "TATAPOWER") used to
go through the LLM, which could "correct" a valid ticker to a wrong one
(observed: TATAPOWER -> TATAMOTORS). Fix: if the (stripped, uppercased) user
input is an exact member of this sector's managed TICKERS list, short-circuit
and build the StockQuery directly -- no LLM, no Serper.

No network: get_llm_client and yfinance are mocked throughout.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.shared.schemas.pipeline import AgentOutput


class _DummyAgent:
    def run(self, query, run_id):  # pragma: no cover - never invoked
        return AgentOutput(agent="dummy", ticker=query.ticker, overall_score=0.5)


class _RenewableTestOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "renewable_energy"

    def __init__(self) -> None:
        self._sub_agents = {"dummy": _DummyAgent()}
        super().__init__()


@pytest.fixture
def orchestrator() -> _RenewableTestOrchestrator:
    with patch("backend.shared.pipeline.base_orchestrator.get_llm_client", return_value=MagicMock()):
        orch = _RenewableTestOrchestrator()
    return orch


# ---------------------------------------------------------------------------
# 1. Exact managed ticker -> short-circuit, LLM never called
# ---------------------------------------------------------------------------

class TestManagedTickerShortCircuit:
    def test_exact_managed_ticker_skips_llm(self, orchestrator, monkeypatch):
        monkeypatch.setattr(orchestrator, "_managed_tickers", lambda: {"TATAPOWER"})
        monkeypatch.setattr(orchestrator, "_company_name_for", lambda t: "Tata Power Co Ltd")

        query = orchestrator._resolve_ticker("TATAPOWER")

        assert query.ticker == "TATAPOWER"
        assert query.company_name == "Tata Power Co Ltd"
        assert query.exchange == "NSE"
        assert query.analysis_date == date.today()
        orchestrator._llm.chat.completions.create.assert_not_called()

    # -----------------------------------------------------------------
    # 2. Lowercase / whitespace input still short-circuits
    # -----------------------------------------------------------------

    def test_lowercase_and_whitespace_input_short_circuits(self, orchestrator, monkeypatch):
        monkeypatch.setattr(orchestrator, "_managed_tickers", lambda: {"TATAPOWER"})
        monkeypatch.setattr(orchestrator, "_company_name_for", lambda t: "Tata Power Co Ltd")

        query = orchestrator._resolve_ticker(" tatapower ")

        assert query.ticker == "TATAPOWER"
        orchestrator._llm.chat.completions.create.assert_not_called()

    # -----------------------------------------------------------------
    # 3. Non-managed / free-text input still goes through the LLM path
    # -----------------------------------------------------------------

    def test_non_managed_input_uses_llm_path(self, orchestrator, monkeypatch):
        monkeypatch.setattr(orchestrator, "_managed_tickers", lambda: {"TATAPOWER"})

        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"ticker": "ADANIGREEN", "company_name": "Adani Green Energy Ltd", '
            '"exchange": "NSE", "confidence": 0.95}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        orchestrator._llm.chat.completions.create.return_value = mock_response

        # Make _verify_ticker pass so the Serper fallback branch isn't taken.
        monkeypatch.setattr(orchestrator, "_verify_ticker", lambda t: True)

        query = orchestrator._resolve_ticker("adani green energy")

        orchestrator._llm.chat.completions.create.assert_called()
        assert query.ticker == "ADANIGREEN"
        assert query.company_name == "Adani Green Energy Ltd"

    # -----------------------------------------------------------------
    # 4. _managed_tickers import failure -> falls through to LLM, no raise
    # -----------------------------------------------------------------

    def test_managed_tickers_import_failure_falls_through(self, orchestrator, monkeypatch):
        # Bypass caching so the real lookup path runs and explodes inside
        # _managed_tickers itself (simulating an import failure).
        monkeypatch.setattr(orchestrator, "_managed_tickers_cache", None, raising=False)

        with patch("importlib.import_module", side_effect=RuntimeError("boom")):
            tickers = orchestrator._managed_tickers()

        # _managed_tickers swallows the failure and returns an empty set --
        # it never raises.
        assert tickers == set()

        # With an empty managed-ticker set, _resolve_ticker falls through to
        # the LLM path (no exception propagates from ticker resolution).
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"ticker": "TATAPOWER", "company_name": "Tata Power Co Ltd", '
            '"exchange": "NSE", "confidence": 0.9}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        orchestrator._llm.chat.completions.create.return_value = mock_response
        monkeypatch.setattr(orchestrator, "_verify_ticker", lambda t: True)

        with patch("importlib.import_module", side_effect=RuntimeError("boom")):
            query = orchestrator._resolve_ticker("TATAPOWER")

        orchestrator._llm.chat.completions.create.assert_called()
        assert query.ticker == "TATAPOWER"

    # -----------------------------------------------------------------
    # 5. _company_name_for yfinance failure -> company_name == ticker
    # -----------------------------------------------------------------

    def test_company_name_for_failure_falls_back_to_ticker(self, orchestrator, monkeypatch):
        # Use a ticker with NO curated override / learned cache entry so the
        # yfinance failure path is actually exercised (TATAPOWER now resolves
        # from the curated company-name cache before yfinance is consulted).
        monkeypatch.setattr(orchestrator, "_managed_tickers", lambda: {"UNCACHEDCO"})
        monkeypatch.setattr(
            "backend.shared.pipeline.base_orchestrator.resolve_company_name",
            lambda ticker: None,
        )
        monkeypatch.setattr(
            orchestrator, "_yf_info", MagicMock(side_effect=RuntimeError("network down"))
        )

        query = orchestrator._resolve_ticker("UNCACHEDCO")

        assert query.ticker == "UNCACHEDCO"
        assert query.company_name == "UNCACHEDCO"
        orchestrator._llm.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# Real _managed_tickers() for RenewableAgentOrchestrator (no mocks, no network)
# ---------------------------------------------------------------------------

class TestRealManagedTickers:
    def test_renewable_managed_tickers_contains_tatapower(self):
        with patch("backend.shared.pipeline.base_orchestrator.get_llm_client", return_value=MagicMock()):
            orch = _RenewableTestOrchestrator()

        managed = orch._managed_tickers()

        assert "TATAPOWER" in managed
        assert {"ADANIGREEN", "TORNTPOWER", "CESC", "SJVN", "NHPC"}.issubset(managed)
