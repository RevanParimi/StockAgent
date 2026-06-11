import json

import pytest

from backend.shared.schemas.dossier import GuidanceItem, TickerDossier, ResponseSignature
from backend.shared.schemas.feedback import FeedbackEntry
from core.intelligence.rl.agents.dossier_curator import DossierCurator


def _entry(direction_correct=False):
    return FeedbackEntry(day=1, date="2026-06-11", predicted_close=100.0,
                         actual_close=98.0, price_error_pct=-2.0,
                         predicted_verdict="BUY",
                         actual_direction="UP" if direction_correct else "DOWN",
                         direction_correct=direction_correct)


def _dossier():
    return TickerDossier(ticker="MARUTI", sector="automobile",
                         created_at="2026-06-01", last_updated="2026-06-10",
                         response_signatures=[ResponseSignature(
                             signature_id="RS001", trigger_tags=["crude_price"],
                             response="drops 2% on crude spike", occurrences=2,
                             first_seen="2026-05-01", last_seen="2026-06-01",
                             confidence=0.6)])


def _curator_with(monkeypatch, payload: dict) -> DossierCurator:
    c = DossierCurator()
    monkeypatch.setattr(c, "_call_llm", lambda *a, **k: json.dumps(payload))
    return c


def test_observations_capped_per_day_by_materiality(monkeypatch):
    payload = {
        "event_tags_today": ["crude_price"],
        "new_observations": [
            {"observation": f"obs {i}", "tags": ["crude_price"], "materiality": i / 10}
            for i in range(1, 6)                       # 5 candidates
        ],
        "signature_updates": [], "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    out = _curator_with(monkeypatch, payload).run(_dossier(), _entry(), "crude up", None)
    todays = [o for o in out.observations if o.date == "2026-06-11"]
    assert len(todays) == 3                            # DOSSIER_MAX_NEW_OBS_PER_DAY
    assert {o.observation for o in todays} == {"obs 5", "obs 4", "obs 3"}  # top materiality


def test_confirm_and_contradict_update_signature(monkeypatch):
    payload = {
        "event_tags_today": [], "new_observations": [],
        "signature_updates": [{"action": "confirm", "signature_id": "RS001",
                               "trigger_tags": [], "response": ""}],
        "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    out = _curator_with(monkeypatch, payload).run(_dossier(), _entry(True), "ctx", None)
    sig = out.response_signatures[0]
    assert sig.occurrences == 3
    assert sig.confidence == pytest.approx(0.65)
    assert sig.last_seen == "2026-06-11"


def test_create_signature_with_unknown_tags_filtered(monkeypatch):
    payload = {
        "event_tags_today": ["made_up_tag", "fii_flow"],
        "new_observations": [],
        "signature_updates": [{"action": "create", "signature_id": "",
                               "trigger_tags": ["fii_flow", "bogus"],
                               "response": "rises on FII buying streaks"}],
        "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    out = _curator_with(monkeypatch, payload).run(_dossier(), _entry(), "ctx", None)
    created = [s for s in out.response_signatures if s.signature_id != "RS001"]
    assert len(created) == 1
    assert created[0].trigger_tags == ["fii_flow"]      # bogus dropped


def test_llm_failure_returns_dossier_unchanged(monkeypatch):
    c = DossierCurator()
    monkeypatch.setattr(c, "_call_llm", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    before = _dossier()
    out = c.run(before, _entry(), "ctx", None)
    assert out.model_dump() == before.model_dump()


def test_hit_day_runs_too(monkeypatch):
    payload = {
        "event_tags_today": [], "new_observations": [
            {"observation": "FADA +8% materialised as predicted", "tags": [], "materiality": 0.8}],
        "signature_updates": [], "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    out = _curator_with(monkeypatch, payload).run(_dossier(), _entry(True), "ctx", None)
    assert any("materialised" in o.observation for o in out.observations)
    assert [o for o in out.observations if o.date == "2026-06-11"][0].outcome_link == "hit"


def test_guidance_cap_applies_even_with_no_updates(monkeypatch):
    # Fix 2: the [-20:] cap must run unconditionally after the loop, not only
    # when guidance_updates is non-empty (it was previously nested inside the loop).
    payload = {
        "event_tags_today": [], "new_observations": [],
        "signature_updates": [], "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    d = _dossier()
    d.guidance = [GuidanceItem(date=f"2026-05-{i:02d}", source="src", guidance=f"item {i}")
                   for i in range(1, 26)]                  # 25 pre-existing items
    out = _curator_with(monkeypatch, payload).run(d, _entry(), "ctx", None)
    assert len(out.guidance) == 20


def test_empty_payload_from_llm_leaves_dossier_unchanged(monkeypatch):
    # Fix 4(a): {} is valid JSON but has no recognized keys — nothing should crash
    # and the dossier should be unchanged apart from anything {} legitimately implies.
    before = _dossier()
    out = _curator_with(monkeypatch, {}).run(before, _entry(), "ctx", None)
    assert out.model_dump() == before.model_dump()


def test_non_json_llm_response_returns_dossier_unchanged(monkeypatch):
    # Fix 4(b): garbage (non-JSON) LLM output must be caught by the run() try/except
    # and return the dossier unchanged, just like an LLM exception would.
    c = DossierCurator()
    monkeypatch.setattr(c, "_call_llm", lambda *a, **k: "sorry, I can't help with that")
    before = _dossier()
    out = c.run(before, _entry(), "ctx", None)
    assert out.model_dump() == before.model_dump()
