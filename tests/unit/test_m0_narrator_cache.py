"""M0 — narrator cache tests (spec §4.4, decision D7/D8)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _rec(pnl=12.3):
    return SimpleNamespace(symbol="TCS", verdict="TRIM", close=4100.0,
                           unrealised_pnl_pct=pnl, stop_pct=-8.0,
                           triggers=["trim_profit_confidence_decline"],
                           notes=[])


def _signals():
    return SimpleNamespace(regime_label="RANGE_NEUTRAL")


@pytest.fixture(autouse=True)
def fresh_cache(tmp_path, monkeypatch):
    from core.portfolio import narrative_cache
    monkeypatch.setattr(narrative_cache, "_CACHE_PATH",
                        tmp_path / "narrative_cache.json")
    narrative_cache._mem.clear()
    yield


def test_context_key_ignores_user_numbers():
    from core.portfolio.narrative_cache import context_key
    k1 = context_key("TCS", "TRIM", ["a"], [], "RANGE_NEUTRAL", "2026-07-26")
    k2 = context_key("TCS", "TRIM", ["a"], [], "RANGE_NEUTRAL", "2026-07-26")
    k3 = context_key("TCS", "HOLD", ["a"], [], "RANGE_NEUTRAL", "2026-07-26")
    assert k1 == k2 and k1 != k3


def test_second_call_same_context_hits_cache():
    from core.portfolio import narrator
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"narrative": "Ticker-level why."}'))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))
    with patch.object(narrator, "get_llm_client", return_value=fake), \
         patch.object(narrator.settings, "ADVISOR_NARRATE", True):
        out1 = narrator.narrate(_rec(pnl=12.3), _signals())
        out2 = narrator.narrate(_rec(pnl=-4.0), _signals())   # different user P&L!
    assert fake.chat.completions.create.call_count == 1        # ONE call
    assert "Ticker-level why." in out1 and "Ticker-level why." in out2
    assert "+12.3%" in out1 and "-4.0%" in out2                # per-user suffixes


def test_cache_failure_degrades_to_llm(monkeypatch):
    from core.portfolio import narrator, narrative_cache
    monkeypatch.setattr(narrative_cache, "get",
                        lambda k: (_ for _ in ()).throw(RuntimeError("boom")))
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"narrative": "Fresh."}'))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
    with patch.object(narrator, "get_llm_client", return_value=fake), \
         patch.object(narrator.settings, "ADVISOR_NARRATE", True):
        assert "Fresh." in narrator.narrate(_rec(), _signals())
