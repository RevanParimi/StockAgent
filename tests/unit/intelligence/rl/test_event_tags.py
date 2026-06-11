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


def test_tag_events_short_keyword_word_boundary_no_false_positive():
    ctx = "Arbiter rules in company's favor; carbide maker posts strong Q4"
    tags = tag_events(ctx)
    assert "central_bank_event" not in tags


def test_tag_events_short_keyword_word_boundary_still_fires():
    ctx = "RBI holds repo rate steady"
    tags = tag_events(ctx)
    assert "central_bank_event" in tags


def test_tag_events_fed_keyword_word_boundary():
    assert "global_macro" in tag_events("Fed signals pause")
    assert "global_macro" not in tag_events("federal court order")


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


def test_feedback_entry_claims_fired_default_empty():
    e = FeedbackEntry(day=1, date="2026-06-11", predicted_close=100.0,
                      actual_close=101.0, price_error_pct=1.0,
                      predicted_verdict="BUY", actual_direction="UP",
                      direction_correct=True)
    assert e.claims_fired == []


def test_feedback_entry_claims_fired_round_trip():
    e = FeedbackEntry(day=1, date="2026-06-11", predicted_close=100.0,
                      actual_close=101.0, price_error_pct=1.0,
                      predicted_verdict="BUY", actual_direction="UP",
                      direction_correct=True, claims_fired=["L001", "L002"])
    restored = FeedbackEntry(**e.model_dump())
    assert restored.claims_fired == ["L001", "L002"]


def test_feedback_entry_claims_fired_independent_lists():
    """Mutable default must not be shared between instances."""
    e1 = FeedbackEntry(day=1, date="2026-06-11", predicted_close=100.0,
                       actual_close=101.0, price_error_pct=1.0,
                       predicted_verdict="BUY", actual_direction="UP",
                       direction_correct=True)
    e2 = FeedbackEntry(day=2, date="2026-06-12", predicted_close=100.0,
                       actual_close=101.0, price_error_pct=1.0,
                       predicted_verdict="BUY", actual_direction="UP",
                       direction_correct=True)
    e1.claims_fired.append("L001")
    assert e2.claims_fired == []
