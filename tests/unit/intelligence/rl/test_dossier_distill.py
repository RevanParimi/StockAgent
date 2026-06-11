import json

from backend.shared.schemas.dossier import (
    TickerDossier, DossierObservation, ResponseSignature, RecurringCatalyst,
)
from backend.shared.schemas.feedback import FeedbackEntry
from core.intelligence.rl.agents import dossier_curator as dc


def _dossier():
    return TickerDossier(
        ticker="MARUTI", sector="automobile",
        created_at="2026-05-01", last_updated="2026-06-10", version=2,
        observations=[DossierObservation(date=f"2026-06-{i:02d}", observation=f"obs {i}")
                      for i in range(1, 11)],
        response_signatures=[
            ResponseSignature(signature_id="RS001", trigger_tags=["crude_price"],
                              response="drops on crude", occurrences=2, contradictions=3,
                              first_seen="2026-05-01", last_seen="2026-05-20", confidence=0.2),
            ResponseSignature(signature_id="RS002", trigger_tags=["fii_flow"],
                              response="rises on FII buying", occurrences=4,
                              first_seen="2026-05-01", last_seen="2026-06-09", confidence=0.7)],
        recurring_catalysts=[RecurringCatalyst(name="FADA data", typical_timing="~10th",
                                               expected_effect="±1%")])


def test_distill_applies_llm_consolidation(monkeypatch):
    payload = {
        "business_summary": "Largest car maker.",
        "flow_notes": "FII buyers.",
        "observations_to_fold": ["2026-06-01", "2026-06-02"],
        "signature_updates": [],
        "catalyst_hit_rates": [{"name": "FADA data", "hit_rate": "3/4 moved price"}],
        "stale_guidance": [], "resolved_questions": [],
    }
    monkeypatch.setattr(dc.DossierCurator, "_call_llm", lambda *a, **k: json.dumps(payload))
    out = dc.distill_dossier(_dossier())
    assert out.business_summary == "Largest car maker."
    assert out.version == 3
    assert all(o.date not in ("2026-06-01", "2026-06-02") for o in out.observations)
    assert out.recurring_catalysts[0].hit_rate == "3/4 moved price"
    assert all(s.signature_id != "RS001" for s in out.response_signatures)  # dead → dropped


def test_distill_static_fallback_on_llm_failure(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(dc.DossierCurator, "_call_llm", _boom)
    before = _dossier()
    out = dc.distill_dossier(before)
    assert out.version == 2                                  # version unchanged
    assert all(s.signature_id != "RS001" for s in out.response_signatures)  # dead still dropped
    assert len(out.observations) <= 10


def test_distill_drop_and_create_yields_unique_ids_no_collision(monkeypatch):
    # Fix 1 (CRITICAL): RS001 is dead (contradictions >= occurrences) and gets
    # dropped by the static hygiene pass BEFORE the LLM payload is applied. That
    # shrinks response_signatures from 2 to 1, so the old id formula
    # f"RS{len(d.response_signatures) + 1:03d}" would mint "RS002" for the new
    # signature created in this same pass — colliding with the surviving RS002.
    payload = {
        "business_summary": "", "flow_notes": "",
        "observations_to_fold": [],
        "signature_updates": [
            {"action": "drop", "signature_id": "RS001"},
            {"action": "create", "trigger_tags": ["seasonal"],
             "response": "rallies into year-end on tax-loss unwind"},
        ],
        "catalyst_hit_rates": [], "stale_guidance": [], "resolved_questions": [],
    }
    before = _dossier()
    monkeypatch.setattr(dc.DossierCurator, "_call_llm", lambda *a, **k: json.dumps(payload))
    out = dc.distill_dossier(before)

    ids = [s.signature_id for s in out.response_signatures]
    assert len(ids) == len(set(ids))                         # all unique
    assert "RS001" not in ids                                # dead one dropped
    assert "RS002" in ids                                    # surviving signature kept its id
    new_sigs = [s for s in out.response_signatures if s.signature_id != "RS002"]
    assert len(new_sigs) == 1
    new_id = new_sigs[0].signature_id
    assert new_id not in ("RS001", "RS002")                  # no collision with pre-drop ids

    # Follow-up _merge "confirm" by id must route to the correct (surviving) signature.
    confirm_payload = {
        "event_tags_today": [], "new_observations": [],
        "signature_updates": [{"action": "confirm", "signature_id": "RS002",
                               "trigger_tags": [], "response": ""}],
        "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    rs002_before = next(s for s in out.response_signatures if s.signature_id == "RS002")
    occurrences_before = rs002_before.occurrences
    new_sig_before = next(s for s in out.response_signatures if s.signature_id == new_id)
    new_sig_occurrences_before = new_sig_before.occurrences

    curator = dc.DossierCurator()
    monkeypatch.setattr(curator, "_call_llm", lambda *a, **k: json.dumps(confirm_payload))
    entry = FeedbackEntry(day=2, date="2026-06-12", predicted_close=100.0,
                          actual_close=101.0, price_error_pct=1.0,
                          predicted_verdict="BUY", actual_direction="UP",
                          direction_correct=True)
    confirmed = curator.run(out, entry, "ctx", None)

    rs002_after = next(s for s in confirmed.response_signatures if s.signature_id == "RS002")
    new_sig_after = next(s for s in confirmed.response_signatures if s.signature_id == new_id)
    assert rs002_after.occurrences == occurrences_before + 1     # correct signature updated
    assert new_sig_after.occurrences == new_sig_occurrences_before  # new signature untouched
