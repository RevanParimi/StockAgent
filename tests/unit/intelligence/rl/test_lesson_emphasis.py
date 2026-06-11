from datetime import date

from backend.shared.schemas.feedback import LearningLedger, Lesson
from core.intelligence.rl.algorithms.lesson_emphasis import (
    apply_lesson_emphasis, calendar_day_tags,
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


def test_matching_tag_applies_emphasis():
    out = apply_lesson_emphasis(SCORES, _ledger(), ["central_bank_event"])
    assert out["risk_macro"] == 0.53
    assert out["sales_demand"] == 0.47
    assert out["fundamentals"] == 0.50


def test_no_tag_intersection_no_change():
    out = apply_lesson_emphasis(SCORES, _ledger(), ["crude_price"])
    assert out == SCORES


def test_low_confidence_lesson_does_not_fire():
    out = apply_lesson_emphasis(SCORES, _ledger(confidence=0.20), ["central_bank_event"])
    assert out == SCORES


def test_invalid_or_untagged_lesson_skipped():
    assert apply_lesson_emphasis(SCORES, _ledger(still_valid=False), ["central_bank_event"]) == SCORES
    assert apply_lesson_emphasis(SCORES, _ledger(trigger_tags=[]), ["central_bank_event"]) == SCORES


def test_cap_limits_stacked_lessons():
    led = _ledger()
    extra = led.lessons[0].model_copy(update={"lesson_id": "L002"})
    extra2 = led.lessons[0].model_copy(update={"lesson_id": "L003"})
    led.lessons.extend([extra, extra2])         # 3 × 0.03 = 0.09 → capped at 0.06
    out = apply_lesson_emphasis(SCORES, led, ["central_bank_event"])
    assert out["risk_macro"] == 0.56
    assert out["sales_demand"] == 0.44


def test_flag_off_is_identity(monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "RL_CLAIMS_ENABLED", False, raising=False)
    out = apply_lesson_emphasis(SCORES, _ledger(), ["central_bank_event"])
    assert out == SCORES


def test_calendar_day_tags_monsoon_and_budget():
    assert "monsoon" in calendar_day_tags(date(2026, 7, 15))
    assert "budget_event" in calendar_day_tags(date(2026, 2, 1))
    assert "monsoon" not in calendar_day_tags(date(2026, 12, 15))
