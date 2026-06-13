"""
QuestionResearcher (RL Phase 4) — active open-question resolution.

Spec: docs/superpowers/specs/2026-06-13-research-loop-design.md. Covers the
pure selection/expiry helpers, the never-raises run() contract with its cost
caps (<=2 Serper, <=1 Tavily, exactly 1 batched LLM call), and the
OpenQuestion backward-compat schema change. All LLM/search/store calls are
mocked — no network traffic is possible from this test module.
"""
import json
from datetime import date

import pytest

from backend.shared.schemas.dossier import OpenQuestion, TickerDossier

TODAY = "2026-06-13"
_RUN_TODAY = date.today().isoformat()


def _q(text, raised_on="2026-06-01", **kw):
    return OpenQuestion(question=text, raised_on=raised_on, **kw)


def _dossier(questions, ticker="TESTX", sector="automobile"):
    return TickerDossier(ticker=ticker, sector=sector, created_at="2026-01-01",
                         last_updated="2026-06-01", open_questions=questions)


# ---------------------------------------------------------------------------
# OpenQuestion schema — backward compat
# ---------------------------------------------------------------------------

def test_open_question_without_new_fields_parses_with_defaults():
    q = OpenQuestion(**{"question": "do dispatch numbers confirm guidance?",
                        "raised_on": "2026-05-20"})
    assert q.attempts == 0
    assert q.last_attempt == ""


def test_dossier_with_legacy_open_question_dicts_parses():
    data = {
        "ticker": "MARUTI", "sector": "automobile",
        "created_at": "2026-01-01", "last_updated": "2026-06-01",
        "open_questions": [
            {"question": "management guided ~1% growth FY27 — do monthly "
                          "dispatch numbers confirm?",
             "raised_on": "2026-05-20", "resolved_on": "", "answer": ""},
        ],
    }
    d = TickerDossier(**data)
    assert d.open_questions[0].attempts == 0
    assert d.open_questions[0].last_attempt == ""


# ---------------------------------------------------------------------------
# select_questions — ordering, cap, exclusions
# ---------------------------------------------------------------------------

def test_select_orders_by_attempts_then_newest_raised_on():
    from core.intelligence.rl.agents.question_researcher import select_questions

    d = _dossier([
        _q("old once-attempted", raised_on="2026-05-01", attempts=1),
        _q("old fresh", raised_on="2026-05-02"),
        _q("new fresh", raised_on="2026-06-10"),
        _q("new once-attempted", raised_on="2026-06-09", attempts=1),
    ])
    selected = select_questions(d, TODAY, cap=4)
    assert [q.question for q in selected] == [
        "new fresh", "old fresh", "new once-attempted", "old once-attempted",
    ]


def test_select_respects_cap():
    from core.intelligence.rl.agents.question_researcher import select_questions

    d = _dossier([_q(f"q{i}", raised_on=f"2026-06-{i:02d}") for i in range(1, 6)])
    selected = select_questions(d, TODAY, cap=2)
    assert len(selected) == 2
    assert [q.question for q in selected] == ["q5", "q4"]


def test_select_excludes_resolved_maxed_and_attempted_today(monkeypatch):
    from core.intelligence.rl.agents import question_researcher as qr

    monkeypatch.setattr(qr.settings, "RL_RESEARCH_MAX_ATTEMPTS", 3)
    d = _dossier([
        _q("resolved", resolved_on="2026-06-01", answer="done"),
        _q("maxed out", attempts=3),
        _q("tried today", last_attempt=TODAY),
        _q("eligible", attempts=2, last_attempt="2026-06-06"),
    ])
    selected = qr.select_questions(d, TODAY, cap=4)
    assert [q.question for q in selected] == ["eligible"]


def test_select_empty_dossier_returns_empty():
    from core.intelligence.rl.agents.question_researcher import select_questions

    assert select_questions(_dossier([]), TODAY, cap=2) == []


# ---------------------------------------------------------------------------
# expire_stale_questions — at-cap resolution
# ---------------------------------------------------------------------------

def test_expire_resolves_at_cap_questions_with_exact_answer(monkeypatch):
    from core.intelligence.rl.agents import question_researcher as qr

    monkeypatch.setattr(qr.settings, "RL_RESEARCH_MAX_ATTEMPTS", 3)
    d = _dossier([
        _q("stale one", attempts=3),
        _q("stale two", attempts=4),
        _q("still going", attempts=2),
    ])
    count = qr.expire_stale_questions(d, TODAY)

    assert count == 2
    stale = [q for q in d.open_questions if q.question.startswith("stale")]
    for q in stale:
        assert q.resolved_on == TODAY
        assert q.answer == "expired: no public signal after 3 research attempts"
    alive = next(q for q in d.open_questions if q.question == "still going")
    assert alive.resolved_on == ""
    assert alive.answer == ""


def test_expire_skips_already_resolved_and_returns_zero_when_none():
    from core.intelligence.rl.agents.question_researcher import expire_stale_questions

    d = _dossier([
        _q("answered already", attempts=5, resolved_on="2026-06-01", answer="42"),
        _q("under cap", attempts=1),
    ])
    assert expire_stale_questions(d, TODAY) == 0
    assert d.open_questions[0].answer == "42"
    assert d.open_questions[0].resolved_on == "2026-06-01"


# ---------------------------------------------------------------------------
# run() — full pipeline, fully mocked (no network, no real store)
# ---------------------------------------------------------------------------

def _install_store(monkeypatch, dossier):
    """Patch PredictionStore (imported inside run()) to serve `dossier` and
    record save_dossier calls. Returns the list of saved dossiers."""
    saves = []

    class _Store:
        def __init__(self, ticker, sector=None, base_dir=None):
            self.ticker, self.sector = ticker, sector

        def load_dossier(self):
            return dossier

        def save_dossier(self, d):
            saves.append(d)

    monkeypatch.setattr(
        "core.intelligence.rl.stores.prediction_store.PredictionStore", _Store)
    return saves


def _researcher(monkeypatch, llm_payload, news_return="", tavily_return="",
                company="Maruti Suzuki India"):
    """Build a QuestionResearcher with all I/O mocked. Returns (instance, calls)
    where calls records every external touch for cost-cap assertions."""
    from core.intelligence.rl.agents import question_researcher as qr

    calls = {"news": [], "tavily": [], "llm": []}

    def _news(queries, max_queries=1, **kw):
        calls["news"].append(queries)
        return news_return

    def _tavily(queries, max_queries=1, max_results_per_query=1, **kw):
        calls["tavily"].append(queries)
        return tavily_return

    monkeypatch.setattr(qr, "fetch_news_context", _news)
    monkeypatch.setattr(qr, "fetch_tavily_context", _tavily)
    monkeypatch.setattr(qr, "resolve_company_name", lambda t: company)

    r = qr.QuestionResearcher()

    def _llm(system, user):
        calls["llm"].append((system, user))
        if isinstance(llm_payload, str):
            return llm_payload
        return json.dumps(llm_payload)

    r._call_llm = _llm
    return r, calls


def test_run_flag_off_returns_zeros_and_does_no_io(monkeypatch):
    from core.intelligence.rl.agents import question_researcher as qr

    monkeypatch.setattr(qr.settings, "RL_RESEARCH_LOOP_ENABLED", False)

    def _boom_store(*a, **k):
        raise AssertionError("PredictionStore must not be constructed when flag off")

    monkeypatch.setattr(
        "core.intelligence.rl.stores.prediction_store.PredictionStore", _boom_store)
    r, calls = _researcher(monkeypatch, {"results": []})

    out = r.run("TESTX", "automobile")

    assert out == {"selected": 0, "answered": 0, "partial": 0, "expired": 0}
    assert calls == {"news": [], "tavily": [], "llm": []}


def test_run_no_dossier_returns_zeros(monkeypatch):
    _install_store(monkeypatch, None)
    r, calls = _researcher(monkeypatch, {"results": []})

    out = r.run("TESTX", "automobile")

    assert out == {"selected": 0, "answered": 0, "partial": 0, "expired": 0}
    assert calls["llm"] == []
    assert calls["news"] == []


def test_run_expiry_only_saves_without_llm(monkeypatch):
    from core.intelligence.rl.agents import question_researcher as qr

    monkeypatch.setattr(qr.settings, "RL_RESEARCH_MAX_ATTEMPTS", 3)
    d = _dossier([_q("stale and done", attempts=3)])
    saves = _install_store(monkeypatch, d)
    r, calls = _researcher(monkeypatch, {"results": []})

    out = r.run("TESTX", "automobile")

    assert out["expired"] == 1
    assert out["selected"] == 0
    assert calls["llm"] == []
    assert calls["news"] == []
    assert len(saves) == 1
    assert d.open_questions[0].resolved_on == _RUN_TODAY


def test_run_answered_resolves_question_and_adds_observation(monkeypatch):
    from core.intelligence.rl.agents import question_researcher as qr

    monkeypatch.setattr(qr.settings, "RL_RESEARCH_MAX_QUESTIONS_PER_RUN", 2)
    d = _dossier([_q("do monthly dispatch numbers confirm FY27 guidance?",
                     raised_on="2026-06-10")])
    saves = _install_store(monkeypatch, d)
    payload = {"results": [{
        "question": "do monthly dispatch numbers confirm FY27 guidance?",
        "status": "answered",
        "answer": "May dispatches +12% YoY, consistent with ~1% FY27 growth guide",
        "finding": "",
        "tags": ["earnings_event"]}]}
    r, calls = _researcher(
        monkeypatch, payload,
        news_return="Maruti May dispatches rose 12% confirming guidance.")

    out = r.run("MARUTI", "automobile")

    assert out == {"selected": 1, "answered": 1, "partial": 0, "expired": 0}
    assert len(calls["llm"]) == 1
    assert len(calls["news"]) == 1
    assert calls["tavily"] == []                      # news had content; no fallback
    q = d.open_questions[0]
    assert q.resolved_on == _RUN_TODAY
    assert q.answer.startswith("May dispatches")
    assert q.last_attempt == _RUN_TODAY
    assert any(o.observation.startswith("[research]") for o in d.observations)
    assert len(saves) == 1


def test_run_partial_bumps_attempts_keeps_open_adds_observation(monkeypatch):
    d = _dossier([_q("will the new plant ramp on schedule?", raised_on="2026-06-10")])
    saves = _install_store(monkeypatch, d)
    payload = {"results": [{
        "question": "will the new plant ramp on schedule?",
        "status": "partial",
        "answer": "",
        "finding": "Plant commissioning reported but no dated ramp schedule",
        "tags": ["capex"]}]}
    r, calls = _researcher(monkeypatch, payload,
                           news_return="Some commissioning news without a date.")

    out = r.run("TESTX", "automobile")

    assert out == {"selected": 1, "answered": 0, "partial": 1, "expired": 0}
    q = d.open_questions[0]
    assert q.resolved_on == ""                          # still open
    assert q.attempts == 1
    assert q.last_attempt == _RUN_TODAY
    assert any(o.observation.startswith("[research-partial]") for o in d.observations)
    assert len(saves) == 1


def test_run_no_signal_bumps_attempts_only(monkeypatch):
    d = _dossier([_q("any update on the FII stake change?", raised_on="2026-06-10")])
    saves = _install_store(monkeypatch, d)
    payload = {"results": [{
        "question": "any update on the FII stake change?",
        "status": "no_signal", "answer": "", "finding": "", "tags": []}]}
    r, calls = _researcher(monkeypatch, payload, news_return="Unrelated market wrap.")

    out = r.run("TESTX", "automobile")

    assert out == {"selected": 1, "answered": 0, "partial": 0, "expired": 0}
    q = d.open_questions[0]
    assert q.resolved_on == ""
    assert q.attempts == 1
    assert q.last_attempt == _RUN_TODAY
    assert d.observations == []
    assert len(saves) == 1


def test_run_llm_garbage_degrades_to_no_signal_never_raises(monkeypatch):
    d = _dossier([_q("does the order book support guidance?", raised_on="2026-06-10")])
    saves = _install_store(monkeypatch, d)
    r, calls = _researcher(monkeypatch, "this is not json {{{",
                           news_return="Some context.")

    out = r.run("TESTX", "automobile")

    assert out == {"selected": 1, "answered": 0, "partial": 0, "expired": 0}
    q = d.open_questions[0]
    assert q.attempts == 1
    assert q.last_attempt == _RUN_TODAY
    assert q.resolved_on == ""
    assert len(saves) == 1


def test_run_cost_caps_two_news_one_tavily_one_llm(monkeypatch):
    from core.intelligence.rl.agents import question_researcher as qr

    monkeypatch.setattr(qr.settings, "RL_RESEARCH_MAX_QUESTIONS_PER_RUN", 2)
    d = _dossier([
        _q("question one about margins?", raised_on="2026-06-10"),
        _q("question two about volumes?", raised_on="2026-06-09"),
    ])
    _install_store(monkeypatch, d)
    payload = {"results": [
        {"question": "question one about margins?", "status": "no_signal",
         "answer": "", "finding": "", "tags": []},
        {"question": "question two about volumes?", "status": "no_signal",
         "answer": "", "finding": "", "tags": []},
    ]}
    # News returns the placeholder for both -> Tavily fallback eligible, but the
    # per-run Tavily budget is 1, so only the first question may use it.
    r, calls = _researcher(monkeypatch, payload,
                           news_return="[No results for: q]",
                           tavily_return="Some Tavily text.")

    out = r.run("TESTX", "automobile")

    assert out["selected"] == 2
    assert len(calls["news"]) == 2          # one Serper per question
    assert len(calls["tavily"]) == 1        # budget capped at one per run
    assert len(calls["llm"]) == 1           # exactly one batched judgment


def test_run_unmatched_llm_question_is_dropped(monkeypatch):
    d = _dossier([_q("alpha question about exports?", raised_on="2026-06-10")])
    saves = _install_store(monkeypatch, d)
    payload = {"results": [{
        "question": "a completely different question the LLM hallucinated",
        "status": "answered", "answer": "bogus", "finding": "", "tags": []}]}
    r, calls = _researcher(monkeypatch, payload, news_return="context")

    out = r.run("TESTX", "automobile")

    # Unmatched result dropped -> the selected question degrades to no_signal.
    assert out == {"selected": 1, "answered": 0, "partial": 0, "expired": 0}
    q = d.open_questions[0]
    assert q.resolved_on == ""
    assert q.attempts == 1
    assert q.answer == ""
