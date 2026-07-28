"""
tests/unit/test_company_name_cache.py
======================================
Learned ticker -> company-name cache (mirrors symbol_resolver's
override -> learned-cache -> naive pattern), plus orchestrator wiring
in BaseSectorOrchestrator._company_name_for.

Goal: yfinance `.info` (longName) is hit AT MOST ONCE per ticker ever —
after that, resolve_company_name() serves the learned/curated value.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import backend.shared.data.fetchers.symbol_resolver as sr
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.shared.schemas.pipeline import AgentOutput


@pytest.fixture
def fresh_resolver(tmp_path, monkeypatch):
    """Isolate the company-name cache file + in-process memo for each test."""
    cache_file = tmp_path / "company_names.json"
    monkeypatch.setattr(sr, "_COMPANY_NAME_CACHE_FILE", cache_file)
    monkeypatch.setattr(sr, "_company_name_cache", None)
    return sr


# ---------------------------------------------------------------------------
# resolve_company_name — curated override -> learned cache -> None
# ---------------------------------------------------------------------------

def test_curated_override_hit(fresh_resolver):
    # MARUTI is seeded in COMPANY_NAME_OVERRIDES — no file IO needed.
    assert fresh_resolver.resolve_company_name("MARUTI") == "Maruti Suzuki India Limited"
    assert fresh_resolver.resolve_company_name("maruti") == "Maruti Suzuki India Limited"  # case-insensitive


def test_learned_cache_hit_after_learn(fresh_resolver):
    fresh_resolver.learn_company_name("TATAPOWER", "Tata Power Company Limited")
    assert fresh_resolver.resolve_company_name("TATAPOWER") == "Tata Power Company Limited"

    # Persisted to disk too.
    on_disk = json.loads(fresh_resolver._COMPANY_NAME_CACHE_FILE.read_text(encoding="utf-8"))
    assert on_disk["TATAPOWER"] == "Tata Power Company Limited"


def test_resolve_miss_returns_none(fresh_resolver):
    assert fresh_resolver.resolve_company_name("SOMENEWTICKER") is None


# ---------------------------------------------------------------------------
# learn_company_name — never raises
# ---------------------------------------------------------------------------

def test_learn_never_raises_on_unwritable_path(fresh_resolver, monkeypatch):
    # Make the REAL writer fail — this actually exercises learn_company_name's
    # try/except. Mocking the PATH does not: os.fspath(MagicMock()) is a real
    # relative path ("MagicMock/mock/<id>"), so atomic_write_text's `Path(path)`
    # bypasses the mock, the write escapes to the CWD, and the error branch is
    # never hit (a false-confidence test that also leaks a junk dir).
    monkeypatch.setattr(fresh_resolver, "atomic_write_json", MagicMock(side_effect=OSError("nope")))

    # Should not raise — and must not write anything to disk.
    fresh_resolver.learn_company_name("FOOBAR", "Foo Bar Ltd")
    assert not fresh_resolver._COMPANY_NAME_CACHE_FILE.exists()


# ---------------------------------------------------------------------------
# Orchestrator wiring — _company_name_for
# ---------------------------------------------------------------------------

class _DummyAgent:
    def run(self, query, run_id):  # pragma: no cover - never invoked
        return AgentOutput(agent="dummy", ticker=query.ticker, overall_score=0.5)


class _RenewableTestOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "renewable_energy"

    def __init__(self) -> None:
        self._sub_agents = {"dummy": _DummyAgent()}
        super().__init__()


@pytest.fixture
def orchestrator():
    with patch("backend.shared.pipeline.base_orchestrator.get_llm_client", return_value=MagicMock()):
        orch = _RenewableTestOrchestrator()
    return orch


def test_company_name_for_uses_cache_before_yf_info(orchestrator, fresh_resolver, monkeypatch):
    monkeypatch.setattr(
        "backend.shared.pipeline.base_orchestrator.resolve_company_name",
        lambda ticker: "Tata Power Company Limited",
    )
    mock_yf_info = MagicMock()
    monkeypatch.setattr(orchestrator, "_yf_info", mock_yf_info)

    name = orchestrator._company_name_for("TATAPOWER")

    assert name == "Tata Power Company Limited"
    mock_yf_info.assert_not_called()


def test_company_name_for_learns_after_live_fetch(orchestrator, fresh_resolver, monkeypatch):
    monkeypatch.setattr(
        "backend.shared.pipeline.base_orchestrator.resolve_company_name",
        lambda ticker: None,
    )
    monkeypatch.setattr(orchestrator, "_yf_info", lambda ticker: {"longName": "Some New Company Limited"})

    learn_mock = MagicMock()
    monkeypatch.setattr("backend.shared.pipeline.base_orchestrator.learn_company_name", learn_mock)

    name = orchestrator._company_name_for("SOMENEWCO")

    assert name == "Some New Company Limited"
    learn_mock.assert_called_once_with("SOMENEWCO", "Some New Company Limited")


def test_company_name_for_falls_back_to_ticker_on_failure(orchestrator, fresh_resolver, monkeypatch):
    monkeypatch.setattr(
        "backend.shared.pipeline.base_orchestrator.resolve_company_name",
        lambda ticker: None,
    )

    def _raise(ticker):
        raise RuntimeError("yfinance down")

    monkeypatch.setattr(orchestrator, "_yf_info", _raise)

    learn_mock = MagicMock()
    monkeypatch.setattr("backend.shared.pipeline.base_orchestrator.learn_company_name", learn_mock)

    name = orchestrator._company_name_for("BROKENCO")

    assert name == "BROKENCO"
    learn_mock.assert_not_called()
