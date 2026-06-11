import json

from backend.shared.schemas.dossier import (
    TickerDossier, DossierObservation, ResponseSignature, RecurringCatalyst,
)
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
