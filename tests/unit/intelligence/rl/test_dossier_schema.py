from backend.shared.schemas.dossier import (
    TickerDossier, DossierObservation, ResponseSignature, GuidanceItem,
    RecurringCatalyst, OpenQuestion,
)


def _dossier() -> TickerDossier:
    return TickerDossier(
        ticker="MARUTI", sector="automobile",
        created_at="2026-06-01", last_updated="2026-06-11",
        business_summary="India's largest passenger-car maker.",
        current_thesis="BUY — rural recovery + stable crude.", thesis_since="2026-06-01",
        response_signatures=[ResponseSignature(
            signature_id="RS001", trigger_tags=["crude_price"],
            response="closes -1.5% to -2.5% within 2 sessions of crude > $90",
            occurrences=4, first_seen="2026-05-02", last_seen="2026-06-09",
            confidence=0.7, evidence_dates=["2026-05-02", "2026-06-09"])],
        guidance=[GuidanceItem(date="2026-05-21", source="Q4 earnings call",
                               guidance="FY27 dispatch growth 8-10%")],
        recurring_catalysts=[RecurringCatalyst(
            name="FADA dispatch data", typical_timing="~10th monthly",
            expected_effect="±1% same-day move")],
        flow_notes="FII net buyers 3 weeks running.",
        open_questions=[OpenQuestion(question="Will EV capex dent margins?",
                                     raised_on="2026-06-02")],
        observations=[DossierObservation(date="2026-06-10",
                                         observation="Dealer inventory down 3 days MoM.",
                                         tags=["seasonal"], materiality=0.6)],
    )


def test_digest_contains_priority_sections_and_header():
    d = _dossier().to_digest(2500)
    assert d.startswith("# MARUTI dossier")
    for needle in ("Thesis", "Response signatures", "crude", "FADA", "Dealer inventory"):
        assert needle in d


def test_digest_respects_budget_and_drops_whole_sections():
    full = _dossier().to_digest(5000)
    small = _dossier().to_digest(220)
    assert len(small) <= 220
    assert small.startswith("# MARUTI dossier")
    assert len(small) < len(full)
    assert not small.rstrip().endswith(("-", ","))   # no mid-section truncation


def test_dead_signature_excluded_from_digest():
    doss = _dossier()
    doss.response_signatures[0].contradictions = 5   # >= occurrences → dead
    assert "crude > $90" not in doss.to_digest(2500)


def test_resolved_question_excluded():
    doss = _dossier()
    doss.open_questions[0].resolved_on = "2026-06-10"
    assert "EV capex" not in doss.to_digest(2500)


def test_empty_dossier_digest_is_just_header():
    d = TickerDossier(ticker="TCS", sector="it_sector",
                      created_at="2026-06-11", last_updated="2026-06-11")
    out = d.to_digest(2500)
    assert out.startswith("# TCS dossier")
    assert "##" not in out
