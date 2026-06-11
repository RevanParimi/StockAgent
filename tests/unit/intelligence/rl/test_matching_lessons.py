"""
matching_lessons() extraction (spec 2026-06-12, section 4).

matching_lessons(ledger, today_tags) -> list[Lesson] applies the same
gates apply_lesson_emphasis used inline: still_valid, non-empty trigger_tags,
trigger_tags intersect today_tags, and effective_confidence(lesson) >=
RL_LESSON_MATCH_MIN_CONF. Never raises; [] on None/empty ledger or no tags.

apply_lesson_emphasis is refactored to iterate matching_lessons() internally
— behavior must stay byte-identical (test_lesson_emphasis.py is the
regression net and must pass unchanged).
"""
from datetime import date

from backend.shared.schemas.feedback import LearningLedger, Lesson
from core.intelligence.rl.algorithms.lesson_emphasis import (
    apply_lesson_emphasis, matching_lessons,
)


def _ledger(**lesson_kwargs) -> LearningLedger:
    defaults = dict(lesson_id="L001", date_learned="2026-06-01", category="macro",
                    pattern="rbi_day", observation="o", rule="r", confidence=0.8,
                    occurrences=3, last_seen=date.today().isoformat(),
                    trigger_tags=["central_bank_event"],
                    prioritise_agents=["risk_macro"], discount_agents=["sales_demand"])
    defaults.update(lesson_kwargs)
    return LearningLedger(ticker="T", sector="automobile",
                          last_updated="2026-06-11", lessons=[Lesson(**defaults)])


SCORES = {"risk_macro": 0.50, "sales_demand": 0.50, "fundamentals": 0.50}


# ---------------------------------------------------------------------------
# None / empty inputs -> []
# ---------------------------------------------------------------------------

def test_none_ledger_returns_empty():
    assert matching_lessons(None, ["central_bank_event"]) == []


def test_empty_ledger_returns_empty():
    empty = LearningLedger(ticker="T", sector="automobile", last_updated="2026-06-11", lessons=[])
    assert matching_lessons(empty, ["central_bank_event"]) == []


def test_no_tags_returns_empty():
    assert matching_lessons(_ledger(), []) == []
    assert matching_lessons(_ledger(), None) == []


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def test_matching_tag_returns_lesson():
    led = _ledger()
    out = matching_lessons(led, ["central_bank_event"])
    assert [l.lesson_id for l in out] == ["L001"]


def test_no_tag_intersection_excluded():
    out = matching_lessons(_ledger(), ["crude_price"])
    assert out == []


def test_invalid_lesson_excluded():
    out = matching_lessons(_ledger(still_valid=False), ["central_bank_event"])
    assert out == []


def test_untagged_lesson_excluded():
    out = matching_lessons(_ledger(trigger_tags=[]), ["central_bank_event"])
    assert out == []


def test_low_confidence_lesson_excluded():
    out = matching_lessons(_ledger(confidence=0.20), ["central_bank_event"])
    assert out == []


def test_bad_lesson_skipped_not_raised(monkeypatch):
    """A lesson that raises during gate evaluation is skipped, never propagates."""
    led = _ledger()

    class BoomLedger(LearningLedger):
        def effective_confidence(self, lesson):
            raise RuntimeError("boom")

    boom = BoomLedger(**led.model_dump())
    # Should not raise, and the bad lesson should simply be excluded.
    assert matching_lessons(boom, ["central_bank_event"]) == []


# ---------------------------------------------------------------------------
# Parity with apply_lesson_emphasis
# ---------------------------------------------------------------------------

def test_parity_matching_lessons_equals_lessons_that_change_scores():
    led = _ledger()
    extra = led.lessons[0].model_copy(update={"lesson_id": "L002", "trigger_tags": ["crude_price"]})
    led.lessons.append(extra)

    matches = matching_lessons(led, ["central_bank_event"])
    out = apply_lesson_emphasis(SCORES, led, ["central_bank_event"])

    # Only L001 matches (L002's trigger_tags don't intersect today's tags).
    assert [l.lesson_id for l in matches] == ["L001"]
    # And the score change reflects exactly L001 firing.
    assert out != SCORES
    assert out["risk_macro"] > SCORES["risk_macro"]
    assert out["sales_demand"] < SCORES["sales_demand"]


def test_parity_no_matches_means_no_score_change():
    led = _ledger()
    matches = matching_lessons(led, ["crude_price"])
    out = apply_lesson_emphasis(SCORES, led, ["crude_price"])
    assert matches == []
    assert out == SCORES
