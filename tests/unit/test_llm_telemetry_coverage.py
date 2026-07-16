"""AUD-093/097: RL + background LLM call sites record telemetry via the factory client."""
from types import SimpleNamespace

import pytest

import services.clients.llm_client as llm_mod


class _Completions:
    def __init__(self, content='{"ok": true}'):
        self.kwargs = None
        self._content = content

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(prompt_tokens=9, completion_tokens=4),
        )


@pytest.fixture
def fake_client(monkeypatch):
    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    monkeypatch.setattr(llm_mod, "get_llm_client", lambda: client)
    return client


@pytest.fixture
def recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_mod, "record_llm_call", lambda *a: calls.append(a))
    return calls


def _assert_recorded(recorded, caller):
    assert recorded, f"{caller}: record_llm_call never invoked"
    assert recorded[0][0] == caller
    assert recorded[0][2] == 9 and recorded[0][3] == 4 and recorded[0][5] is True


def test_preopen_check(fake_client, recorded):
    from core.intelligence.rl.workflows import preopen_check
    preopen_check._call_llm("sys", "user")
    _assert_recorded(recorded, "preopen_check")


def test_control_lane(fake_client, recorded):
    from core.intelligence.rl.agents import control_lane
    control_lane._call_llm("sys", "user")
    _assert_recorded(recorded, "control_lane")


def test_thesis_reviewer(fake_client, recorded):
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    ThesisReviewer._call_llm(SimpleNamespace(_client=fake_client), "user")
    _assert_recorded(recorded, "thesis_reviewer")


def test_question_researcher(fake_client, recorded):
    from core.intelligence.rl.agents.question_researcher import QuestionResearcher
    QuestionResearcher._call_llm(SimpleNamespace(), "sys", "user")
    _assert_recorded(recorded, "question_researcher")


def test_event_ingestor(fake_client, recorded):
    from core.intelligence.rl.agents.event_ingestor import EventIngestor
    EventIngestor._call_llm(SimpleNamespace(), "sys", "user")
    _assert_recorded(recorded, "event_ingestor")


def test_dossier_curator(fake_client, recorded):
    from core.intelligence.rl.agents.dossier_curator import DossierCurator
    DossierCurator._call_llm(SimpleNamespace(), "sys", "user")
    _assert_recorded(recorded, "dossier_curator")


def test_price_interpolator(fake_client, recorded):
    from core.intelligence.rl.algorithms.price_interpolator import PriceInterpolator
    PriceInterpolator._call_llm(SimpleNamespace(), "user")
    _assert_recorded(recorded, "price_interpolator")


def test_failure_is_recorded(fake_client, recorded, monkeypatch):
    def boom(**kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(fake_client.chat.completions, "create", boom)
    from core.intelligence.rl.agents import control_lane
    with pytest.raises(ValueError):
        control_lane._call_llm("sys", "user")
    assert recorded and recorded[0][5] is False
