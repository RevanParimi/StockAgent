"""
QuestionResearcher (RL Phase 4) — active open-question resolution.

Spec: docs/superpowers/specs/2026-06-13-research-loop-design.md. Covers the
pure selection/expiry helpers, the never-raises run() contract with its cost
caps (<=2 Serper, <=1 Tavily, exactly 1 batched LLM call), and the
OpenQuestion backward-compat schema change. All LLM/search/store calls are
mocked — no network traffic is possible from this test module.
"""
import pytest

from backend.shared.schemas.dossier import OpenQuestion, TickerDossier

TODAY = "2026-06-13"


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
