"""Tests for EVENT_TAGS vocabulary, tag_events(), and claim fields on Lesson/FeedbackEntry."""
from backend.shared.schemas.feedback import (
    EVENT_TAGS, tag_events, Lesson, FeedbackEntry,
)


def test_vocabulary_is_frozen_and_complete():
    assert isinstance(EVENT_TAGS, frozenset)
    for tag in ("central_bank_event", "fii_flow", "crude_price", "expiry_week",
                "block_deal", "budget_event", "monsoon", "guidance_change"):
        assert tag in EVENT_TAGS


def test_tag_events_matches_keywords_case_insensitive():
    ctx = "RBI held rates today; FII sold 2200Cr; Brent crude spiked past $90."
    tags = tag_events(ctx)
    assert "central_bank_event" in tags
    assert "fii_flow" in tags
    assert "crude_price" in tags
    assert tags == sorted(set(tags))           # sorted, unique


def test_tag_events_empty_and_no_match():
    assert tag_events("") == []
    assert tag_events("calm uneventful session") == []


def test_lesson_claim_fields_default_empty():
    l = Lesson(lesson_id="L001", date_learned="2026-06-11", category="macro",
               pattern="rbi_day", observation="x", rule="y")
    assert l.trigger_tags == []
    assert l.prioritise_agents == []
    assert l.discount_agents == []


def test_feedback_entry_event_tags_default_empty():
    e = FeedbackEntry(day=1, date="2026-06-11", predicted_close=100.0,
                      actual_close=101.0, price_error_pct=1.0,
                      predicted_verdict="BUY", actual_direction="UP",
                      direction_correct=True)
    assert e.event_tags == []
