"""
tests/unit/intelligence/rl/test_preopen_check.py
===================================================
Living Envelope (RL Phase 2.5), Component 3 — run_preopen_check().

Covers:
  - RL_PREOPEN_CHECK_ENABLED == False -> zero side effects.
  - severity below RL_PREOPEN_SHOCK_SEVERITY -> no per-ticker work, exactly
    1 Serper call + 1 LLM call.
  - severity >= threshold + contradiction (predicted UP, direction=risk_off)
    -> flagged + regenerate_envelope called with trigger="preopen_shock".
  - no contradiction (predicted DOWN in risk_off) -> not flagged.
  - regenerate_envelope returns None (cap/failure) -> flagged but
    reforecasts empty.
  - LLM garbage JSON -> severity 0.0 path, never raises.
  - per-ticker exception isolated -> loop continues.
  - cost contract: exactly 1 Serper call + 1 LLM call even with many tickers.

All Serper/LLM/PredictionStore/regenerate_envelope calls are mocked — no
real network or LLM traffic is possible from this test module.
"""

from __future__ import annotations

import json

import pytest

from core.intelligence.rl.workflows import preopen_check as pc
from backend.shared.schemas.feedback import DailyForecast, PredictionEnvelope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _envelope_with_today(date_str: str, verdict: str) -> PredictionEnvelope:
    return PredictionEnvelope(
        ticker="MARUTI", sector="automobile", cycle_id="MARUTI_2026-06",
        generated_at="2026-06-01T09:00:00", base_close=1000.0,
        daily_forecasts=[
            DailyForecast(
                day=1, date=date_str, predicted_close=1010.0,
                predicted_verdict=verdict, confidence=0.6,
            ),
        ],
    )


def _patch_serper(monkeypatch, calls: list, context: str = "headline text"):
    def _fake_fetch_news_context(queries, max_queries=1, **kwargs):
        calls.append((list(queries), max_queries))
        return context
    monkeypatch.setattr(
        "services.data.fetchers.news.fetch_news_context",
        _fake_fetch_news_context,
    )


def _patch_llm(monkeypatch, calls: list, response: dict | str):
    """response: dict -> serialized to JSON; str -> raw passthrough (e.g. garbage)."""
    def _fake_call_llm(system_prompt, user_prompt):
        calls.append((system_prompt, user_prompt))
        if isinstance(response, dict):
            return json.dumps(response), "qwen/qwen3.6-flash"
        return response, "qwen/qwen3.6-flash"

    monkeypatch.setattr(pc, "_call_llm", _fake_call_llm)


def _patch_predicted_direction(monkeypatch, mapping: dict[str, str | None]):
    """mapping: ticker -> "UP"|"DOWN"|"FLAT"|None"""
    def _fake(ticker, sector, date_str):
        return mapping.get(ticker)
    monkeypatch.setattr(pc, "_predicted_direction", _fake)


def _patch_regenerate(monkeypatch, calls: list, result=None):
    def _fake_regenerate(ticker, sector, reason, trigger):
        calls.append({"ticker": ticker, "sector": sector, "reason": reason, "trigger": trigger})
        return result
    monkeypatch.setattr(
        "core.intelligence.rl.workflows.generate_forecast.regenerate_envelope",
        _fake_regenerate,
    )


# ---------------------------------------------------------------------------
# Flag off
# ---------------------------------------------------------------------------

def test_flag_off_zero_side_effects(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", False)

    serper_calls = []
    llm_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.9, "direction": "risk_off", "headline": "x"})

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile")])

    assert result == {
        "severity": 0.0, "direction": "neutral",
        "flagged": [], "reforecasts": [], "skipped": "disabled",
    }
    assert serper_calls == []
    assert llm_calls == []


# ---------------------------------------------------------------------------
# Severity below threshold
# ---------------------------------------------------------------------------

def test_severity_below_threshold_no_per_ticker_work(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.3, "direction": "risk_off", "headline": "minor news"})
    _patch_regenerate(monkeypatch, regen_calls)

    # _predicted_direction should never even be consulted below threshold.
    def _boom(*a, **k):
        raise AssertionError("should not check per-ticker direction below threshold")
    monkeypatch.setattr(pc, "_predicted_direction", _boom)

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile"), ("TATAMOTORS", "automobile")])

    assert result["severity"] == 0.3
    assert result["direction"] == "risk_off"
    assert result["flagged"] == []
    assert result["reforecasts"] == []
    assert len(serper_calls) == 1
    assert len(llm_calls) == 1
    assert regen_calls == []


# ---------------------------------------------------------------------------
# Severity >= threshold + contradiction
# ---------------------------------------------------------------------------

def test_severity_above_threshold_contradiction_flags_and_reforecasts(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.85, "direction": "risk_off", "headline": "Crude spikes 10% overnight"})
    # MARUTI predicted UP, overnight direction risk_off -> contradiction
    _patch_predicted_direction(monkeypatch, {"MARUTI": "UP"})
    _patch_regenerate(monkeypatch, regen_calls, result=_envelope_with_today("2026-06-12", "BUY"))

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile")])

    assert result["severity"] == 0.85
    assert result["direction"] == "risk_off"
    assert result["flagged"] == ["MARUTI"]
    assert result["reforecasts"] == ["MARUTI"]
    assert len(serper_calls) == 1
    assert len(llm_calls) == 1
    assert len(regen_calls) == 1
    assert regen_calls[0]["ticker"] == "MARUTI"
    assert regen_calls[0]["sector"] == "automobile"
    assert regen_calls[0]["trigger"] == "preopen_shock"
    assert "Crude spikes 10% overnight" in regen_calls[0]["reason"]


# ---------------------------------------------------------------------------
# No contradiction
# ---------------------------------------------------------------------------

def test_no_contradiction_predicted_down_in_risk_off_not_flagged(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.9, "direction": "risk_off", "headline": "Global selloff"})
    # MARUTI predicted DOWN, overnight risk_off -> NOT a contradiction (agrees)
    _patch_predicted_direction(monkeypatch, {"MARUTI": "DOWN"})
    _patch_regenerate(monkeypatch, regen_calls)

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile")])

    assert result["flagged"] == []
    assert result["reforecasts"] == []
    assert regen_calls == []


def test_no_contradiction_predicted_up_in_risk_on_not_flagged(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.9, "direction": "risk_on", "headline": "Major rally"})
    _patch_predicted_direction(monkeypatch, {"MARUTI": "UP"})
    _patch_regenerate(monkeypatch, regen_calls)

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile")])

    assert result["flagged"] == []
    assert result["reforecasts"] == []
    assert regen_calls == []


# ---------------------------------------------------------------------------
# No envelope / no forecast for today -> skip silently
# ---------------------------------------------------------------------------

def test_missing_envelope_skips_ticker_silently(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.9, "direction": "risk_off", "headline": "Crisis"})
    _patch_predicted_direction(monkeypatch, {"MARUTI": None})
    _patch_regenerate(monkeypatch, regen_calls)

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile")])

    assert result["flagged"] == []
    assert result["reforecasts"] == []
    assert regen_calls == []


# ---------------------------------------------------------------------------
# regenerate_envelope returns None (cap / failure)
# ---------------------------------------------------------------------------

def test_regenerate_returns_none_flagged_but_not_reforecast(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.9, "direction": "risk_off", "headline": "Crisis"})
    _patch_predicted_direction(monkeypatch, {"MARUTI": "UP"})
    _patch_regenerate(monkeypatch, regen_calls, result=None)

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile")])

    assert result["flagged"] == ["MARUTI"]
    assert result["reforecasts"] == []
    assert len(regen_calls) == 1


# ---------------------------------------------------------------------------
# LLM garbage JSON -> severity 0.0 path, never raises
# ---------------------------------------------------------------------------

def test_llm_garbage_json_never_raises_severity_zero(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, "not valid json {{{")
    _patch_regenerate(monkeypatch, regen_calls)

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile")])

    assert result["severity"] == 0.0
    assert result["direction"] == "neutral"
    assert result["flagged"] == []
    assert result["reforecasts"] == []
    assert regen_calls == []


def test_llm_raises_exception_never_propagates(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    _patch_serper(monkeypatch, serper_calls)

    def _boom(system_prompt, user_prompt):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(pc, "_call_llm", _boom)

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile")])

    assert result["severity"] == 0.0
    assert result["direction"] == "neutral"


# ---------------------------------------------------------------------------
# Severity clamping / unknown direction
# ---------------------------------------------------------------------------

def test_severity_clamped_and_unknown_direction_falls_to_neutral(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 5.0, "direction": "bullish???", "headline": "weird"})

    result = pc.run_preopen_check(tickers=[("MARUTI", "automobile")])

    assert result["severity"] == 1.0  # clamped
    assert result["direction"] == "neutral"  # unknown -> neutral
    # neutral direction can never contradict -> no per-ticker work even
    # though severity is at max.
    assert result["flagged"] == []
    assert result["reforecasts"] == []


# ---------------------------------------------------------------------------
# Per-ticker exception isolation
# ---------------------------------------------------------------------------

def test_per_ticker_exception_isolated(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.9, "direction": "risk_off", "headline": "Crisis"})
    _patch_regenerate(monkeypatch, regen_calls, result=_envelope_with_today("2026-06-12", "BUY"))

    def _fake_predicted_direction(ticker, sector, date_str):
        if ticker == "BOOM":
            raise RuntimeError("boom")
        return {"MARUTI": "UP"}.get(ticker)

    monkeypatch.setattr(pc, "_predicted_direction", _fake_predicted_direction)

    result = pc.run_preopen_check(tickers=[("BOOM", "automobile"), ("MARUTI", "automobile")])

    # BOOM's exception is swallowed; MARUTI is still processed.
    assert result["flagged"] == ["MARUTI"]
    assert result["reforecasts"] == ["MARUTI"]


# ---------------------------------------------------------------------------
# Cost contract: exactly 1 Serper + 1 LLM call even with many tickers
# ---------------------------------------------------------------------------

def test_cost_contract_one_serper_one_llm_with_ten_tickers(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.9, "direction": "risk_off", "headline": "Crisis"})
    _patch_regenerate(monkeypatch, regen_calls, result=_envelope_with_today("2026-06-12", "BUY"))

    tickers = [(f"TICK{i}", "automobile") for i in range(10)]
    # All predicted UP -> all contradict risk_off.
    _patch_predicted_direction(monkeypatch, {f"TICK{i}": "UP" for i in range(10)})

    result = pc.run_preopen_check(tickers=tickers)

    assert len(serper_calls) == 1
    assert len(llm_calls) == 1
    assert len(result["flagged"]) == 10
    assert len(result["reforecasts"]) == 10


def test_cost_contract_below_threshold_with_ten_tickers(monkeypatch):
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.1, "direction": "neutral", "headline": "Quiet night"})

    def _boom(*a, **k):
        raise AssertionError("should not check per-ticker direction below threshold")
    monkeypatch.setattr(pc, "_predicted_direction", _boom)

    tickers = [(f"TICK{i}", "automobile") for i in range(10)]
    result = pc.run_preopen_check(tickers=tickers)

    assert len(serper_calls) == 1
    assert len(llm_calls) == 1
    assert result["flagged"] == []
    assert result["reforecasts"] == []


# ---------------------------------------------------------------------------
# Default tickers (tickers=None) — sanity that the loader doesn't blow up
# ---------------------------------------------------------------------------

def test_default_tickers_loaded_when_none_passed(monkeypatch):
    """When tickers=None and severity is below threshold, _default_tickers()
    is never even called (no per-ticker work needed) — but make sure passing
    None doesn't raise before we get there."""
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.1, "direction": "neutral", "headline": "Quiet night"})

    result = pc.run_preopen_check(tickers=None)

    assert result["severity"] == 0.1
    assert result["flagged"] == []
    assert result["reforecasts"] == []


def test_default_tickers_above_threshold_uses_real_sector_configs(monkeypatch):
    """With tickers=None and severity above threshold, _default_tickers()
    reads the real sector TICKERS lists. Verify it returns a non-empty list
    of (ticker, sector) tuples without raising, and that the per-ticker loop
    (with mocked PredictionStore/regenerate_envelope) completes."""
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_CHECK_ENABLED", True)
    monkeypatch.setattr(pc.settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    serper_calls = []
    llm_calls = []
    regen_calls = []
    _patch_serper(monkeypatch, serper_calls)
    _patch_llm(monkeypatch, llm_calls, {"severity": 0.9, "direction": "risk_off", "headline": "Crisis"})
    # No envelopes anywhere -> _predicted_direction returns None for everyone.
    _patch_predicted_direction(monkeypatch, {})
    _patch_regenerate(monkeypatch, regen_calls)

    result = pc.run_preopen_check(tickers=None)

    assert result["severity"] == 0.9
    assert result["flagged"] == []
    assert result["reforecasts"] == []
    assert len(serper_calls) == 1
    assert len(llm_calls) == 1
