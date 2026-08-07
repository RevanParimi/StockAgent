"""
F3 — dossier observations record where they came from.

The research loop wrote "[research] {answer}" and threw away the dated headline
that produced it, so a dossier could not distinguish an observation grounded in
a real article from one the judge model asserted with no signal. Observations
now carry `source`, exactly as sibling GuidanceItem already did, and render with
it in the digest the forecast agents read.

Additive and optional: dossiers written before F3 must load unchanged.
"""
import json

from backend.shared.schemas.dossier import (
    DossierObservation, OpenQuestion, TickerDossier,
)
from core.intelligence.rl.agents.dossier_curator import merge_curator_output
from core.intelligence.rl.agents.question_researcher import QuestionResearcher

_HIT = "• [Date: 2026-06-10] [Mint] Maruti guides capex up 20%: board approved plan."


def _dossier(**kw) -> TickerDossier:
    return TickerDossier(ticker="MARUTI", sector="automobile",
                         created_at="2026-06-01", last_updated="2026-06-10", **kw)


# --------------------------------------------------------------------------
# Schema + merge plumbing
# --------------------------------------------------------------------------

def test_merge_carries_observation_source_through():
    d = _dossier()

    merge_curator_output(
        d, {"new_observations": [{"observation": "Capex guided up", "tags": [],
                                  "materiality": 0.6, "source": "2026-06-10 — headline"}]},
        today="2026-06-10")

    assert d.observations[0].source == "2026-06-10 — headline"


def test_merge_defaults_source_to_empty_when_absent():
    """The daily curator emits no source — its observations must still merge."""
    d = _dossier()

    merge_curator_output(
        d, {"new_observations": [{"observation": "Quiet session", "materiality": 0.5}]},
        today="2026-06-10")

    assert d.observations[0].source == ""


def test_merge_caps_an_overlong_source():
    d = _dossier()

    merge_curator_output(
        d, {"new_observations": [{"observation": "o", "source": "x" * 500}]},
        today="2026-06-10")

    assert len(d.observations[0].source) <= 120


def test_pre_f3_dossier_json_still_loads():
    """Dossiers on the prod volume have no `source` key on observations."""
    legacy = {
        "ticker": "MARUTI", "sector": "automobile", "created_at": "2026-06-01",
        "last_updated": "2026-06-05",
        "observations": [{"date": "2026-06-05", "observation": "o",
                          "tags": [], "materiality": 0.5}],
    }

    d = TickerDossier.model_validate(json.loads(json.dumps(legacy)))

    assert d.observations[0].source == ""


# --------------------------------------------------------------------------
# Digest render — mirrors the guidance line that already shows provenance
# --------------------------------------------------------------------------

def test_digest_shows_provenance_on_an_observation_that_has_it():
    d = _dossier(observations=[DossierObservation(
        date="2026-06-10", observation="Capex guided up",
        source="2026-06-10 — Mint headline")])

    digest = d.to_digest()

    assert "- 2026-06-10 (2026-06-10 — Mint headline): Capex guided up" in digest


def test_digest_line_unchanged_for_observations_without_provenance():
    d = _dossier(observations=[DossierObservation(
        date="2026-06-10", observation="Capex guided up")])

    digest = d.to_digest()

    assert "- 2026-06-10: Capex guided up" in digest


# --------------------------------------------------------------------------
# Writer — the research loop
# --------------------------------------------------------------------------

def _apply_research(status: str, payload: dict, context: str, **kw):
    researcher = QuestionResearcher.__new__(QuestionResearcher)   # no LLM needed
    question = "Will capex rise in FY27?"
    d = _dossier(open_questions=[OpenQuestion(question=question, raised_on="2026-06-01")])
    results = {question: {"status": status, "tags": [], **payload}}

    researcher._apply(d, list(d.open_questions), results, "2026-06-10",
                      contexts={question: context}, **kw)
    return d


def test_answered_research_observation_keeps_the_headline_that_answered_it():
    d = _apply_research("answered", {"answer": "Capex guided up 20%"}, _HIT)

    obs = [o for o in d.observations if o.observation.startswith("[research]")]
    assert len(obs) == 1
    assert obs[0].source.startswith("2026-06-10 — ")
    assert "capex up 20%" in obs[0].source


def test_partial_research_observation_also_keeps_its_source():
    d = _apply_research("partial", {"finding": "Capex plan under review"}, _HIT)

    obs = [o for o in d.observations if o.observation.startswith("[research-partial]")]
    assert obs[0].source.startswith("2026-06-10 — ")


def test_research_observation_has_no_source_when_the_search_found_nothing_dated():
    """No dated hit ⇒ no provenance. Never invent one."""
    d = _apply_research("answered", {"answer": "Capex guided up 20%"},
                        "[No results for: Maruti capex FY27]")

    obs = [o for o in d.observations if o.observation.startswith("[research]")]
    assert obs[0].source == ""


def test_apply_without_contexts_still_works_for_existing_callers():
    researcher = QuestionResearcher.__new__(QuestionResearcher)
    question = "Will capex rise in FY27?"
    d = _dossier(open_questions=[OpenQuestion(question=question, raised_on="2026-06-01")])

    answered, partial = researcher._apply(
        d, list(d.open_questions),
        {question: {"status": "answered", "answer": "yes", "tags": []}}, "2026-06-10")

    assert (answered, partial) == (1, 0)
    assert d.observations[0].source == ""


def test_kill_switch_restores_pre_f3_behaviour(monkeypatch):
    import core.intelligence.rl.agents.question_researcher as qr
    monkeypatch.setattr(qr.settings, "RL_PROVENANCE_ENABLED", False)

    d = _apply_research("answered", {"answer": "Capex guided up 20%"}, _HIT)

    assert d.observations[0].source == ""
