"""Compass Phase A — narration is presentation-only, never blocks advice."""
import json

from backend.shared.schemas.portfolio import AdviceRecord
from core.portfolio.advisor import AdvisorSignals
import core.portfolio.narrator as narrator


def _rec(verdict="TRIM", triggers=None) -> AdviceRecord:
    return AdviceRecord(
        date="2026-07-06", user_id="primary", symbol="MARUTI", verdict=verdict,
        close=13000.0, unrealised_pnl_pct=28.0, stop_pct=10.0,
        triggers=triggers or ["trim_profit_confidence_decline"],
    )


def _signals() -> AdvisorSignals:
    return AdvisorSignals(
        symbol="MARUTI", sector="automobile", close=13000.0,
        atr_stop_pct=10.0, unrealised_pnl_pct=28.0, holding_age_days=180,
    )


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeClient:
    def __init__(self, content):
        usage = type("U", (), {"prompt_tokens": 100, "completion_tokens": 50})()
        resp = type("R", (), {"choices": [_FakeChoice(content)], "usage": usage})()
        create = lambda self_, **kw: resp
        completions = type("C", (), {"create": create})()
        self.chat = type("Ch", (), {"completions": completions})()


def test_narrate_happy_path(monkeypatch):
    payload = json.dumps({"narrative": "Profit is extended while envelope confidence is fading; consider booking part of the gain."})
    monkeypatch.setattr(narrator, "get_llm_client", lambda: _FakeClient(payload))
    text = narrator.narrate(_rec(), _signals())
    assert "confidence" in text


def test_narrate_falls_back_on_llm_error(monkeypatch):
    def boom():
        raise RuntimeError("openrouter down")
    monkeypatch.setattr(narrator, "get_llm_client", boom)
    text = narrator.narrate(_rec(), _signals())
    assert text == narrator.fallback_narrative(_rec())
    assert "TRIM" in text


def test_narrate_disabled_uses_fallback(monkeypatch):
    monkeypatch.setattr(narrator.settings, "ADVISOR_NARRATE", False)
    text = narrator.narrate(_rec(), _signals())
    assert text == narrator.fallback_narrative(_rec())


def test_fallback_never_says_advice():
    for verdict in ("HOLD", "ADD", "TRIM", "EXIT"):
        text = narrator.fallback_narrative(_rec(verdict=verdict))
        assert "advice" not in text.lower()   # research/analysis posture (spec §2)


def test_narrate_passes_json_mode_extra_body(monkeypatch):
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY
    captured = {}

    payload = json.dumps({"narrative": "ok"})

    class _CapturingClient(_FakeClient):
        def __init__(self):
            super().__init__(payload)
            orig = self.chat.completions.create
            def create(**kw):
                captured.update(kw)
                return orig(**kw)
            self.chat.completions.create = create

    monkeypatch.setattr(narrator, "get_llm_client", lambda: _CapturingClient())
    narrator.narrate(_rec(), _signals())
    assert captured["extra_body"] == JSON_MODE_EXTRA_BODY
    assert captured["response_format"] == {"type": "json_object"}


def test_narrate_non_dict_json_falls_back_single_telemetry(monkeypatch):
    calls = []
    monkeypatch.setattr(narrator, "record_llm_call",
                        lambda *a, **k: calls.append(a[-1] if a else k.get("success")))
    monkeypatch.setattr(narrator, "get_llm_client", lambda: _FakeClient('["not", "a", "dict"]'))
    text = narrator.narrate(_rec(), _signals())
    assert text == narrator.fallback_narrative(_rec())
    assert calls == [True]   # exactly one telemetry record, success=True (call succeeded, content unusable)
