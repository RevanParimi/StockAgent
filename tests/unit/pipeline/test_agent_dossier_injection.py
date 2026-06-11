"""
tests/unit/pipeline/test_agent_dossier_injection.py
=====================================================
RL knowledge layer: ticker dossier digest injection into agent prompts.

Covers `_get_dossier_digest` / `_fetch_dossier_digest` (lazy, cached, flag-gated,
never raises) on BaseAgent. Prompt-injection no-op behavior (byte-identical
prompts when flag off / no dossier) is covered by `_build_prompt`-level tests
in the agent test suites; this file focuses on the digest helper contract.
"""

from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput


class _Probe(BaseAgent):
    """Minimal concrete agent capturing the final system prompt."""

    sector = ""  # plain class attribute — shadows BaseAgent.sector property so
                  # tests can freely assign agent.sector on instances.

    @property
    def agent_name(self) -> str:
        return "probe"

    def _build_prompt(self, query, context):
        return ("sys", "usr")

    def _parse_output(self, data, ticker):
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=0.5,
            key_positives=[],
            key_risks=[],
            summary="",
        )


def _make_probe() -> _Probe:
    # Bypass __init__ to avoid LLM client construction.
    return _Probe.__new__(_Probe)


def test_digest_appended_when_dossier_exists(monkeypatch):
    agent = _make_probe()
    agent.sector = "automobile"
    agent._dossier_digest_cache = {}
    monkeypatch.setattr(agent, "_fetch_dossier_digest",
                         lambda ticker: "# MARUTI dossier\n## Thesis\nBUY")
    out = agent._get_dossier_digest("MARUTI")
    assert "ACCUMULATED TICKER KNOWLEDGE" not in out      # raw digest, no wrapper here
    assert out.startswith("# MARUTI dossier")
    # cached on second call
    monkeypatch.setattr(agent, "_fetch_dossier_digest",
                         lambda ticker: (_ for _ in ()).throw(AssertionError("not cached")))
    assert agent._get_dossier_digest("MARUTI").startswith("# MARUTI dossier")


def test_empty_when_flag_off(monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "RL_DOSSIER_ENABLED", False, raising=False)
    agent = _make_probe()
    agent.sector = "automobile"
    agent._dossier_digest_cache = {}
    assert agent._get_dossier_digest("MARUTI") == ""


def test_empty_when_no_dossier(monkeypatch):
    agent = _make_probe()
    agent.sector = "automobile"
    agent._dossier_digest_cache = {}
    monkeypatch.setattr(agent, "_fetch_dossier_digest", lambda ticker: "")
    assert agent._get_dossier_digest("NEWTICKER") == ""


def test_fetch_dossier_digest_never_raises_on_store_error(monkeypatch):
    """_fetch_dossier_digest must swallow any PredictionStore/load_dossier error."""
    agent = _make_probe()
    agent.sector = "automobile"

    import core.intelligence.rl.stores.prediction_store as ps_mod

    class _BoomStore:
        def __init__(self, *a, **k):
            raise RuntimeError("boom")

    monkeypatch.setattr(ps_mod, "PredictionStore", _BoomStore)
    assert agent._fetch_dossier_digest("MARUTI") == ""
