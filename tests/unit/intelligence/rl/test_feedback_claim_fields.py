"""Tests for FeedbackAgent emitting validated executable-claim fields on lessons.

Covers Task 9 of docs/superpowers/plans/2026-06-11-ticker-dossier.md:
- RawLesson.trigger_tags / prioritise_agents / discount_agents are parsed from the
  LLM response, validated against EVENT_TAGS / known agent names, and passed
  through to Lesson when merged into the LearningLedger.
"""
import json

from backend.shared.schemas.feedback import EVENT_TAGS, FeedbackAgentInput
from core.intelligence.rl.agents.feedback_agent import FeedbackAgent


def _fb_input() -> FeedbackAgentInput:
    return FeedbackAgentInput(
        ticker="MARUTI",
        sector="automobile",
        date="2026-06-11",
        predicted_close=100.0,
        actual_close=98.0,
        price_error_pct=-2.0,
        direction_correct=False,
        predicted_agent_scores={"risk_macro": 0.5, "sales_demand": 0.7},
        todays_agent_scores={"risk_macro": 0.4, "sales_demand": 0.6},
        market_context_today="RBI surprise hold",
        key_assumptions_made=[],
        active_lessons_summary="No active lessons.",
    )


def test_parse_extracts_and_validates_claim_fields():
    agent = FeedbackAgent.__new__(FeedbackAgent)        # no LLM client needed for _parse
    raw = json.dumps({
        "primary_miss_agent": "risk_macro", "miss_type": "model_bias",
        "missed_factors": ["RBI surprise"], "over_weighted_factors": [],
        "agent_score_drift": {},
        "new_lessons": [{
            "category": "macro", "pattern": "rbi_day", "observation": "o", "rule": "r",
            "confidence": 0.7, "scope": "stock_specific",
            "trigger_tags": ["central_bank_event", "not_a_real_tag"],
            "prioritise_agents": ["risk_macro", "ghost_agent"],
            "discount_agents": ["sales_demand"],
        }],
        "revised_context": {"headline": "h"},
    })
    out = agent._parse(raw, _fb_input())
    lesson = out.new_lessons[0]
    assert lesson.trigger_tags == ["central_bank_event"]          # invalid tag dropped
    assert lesson.prioritise_agents == ["risk_macro"]              # unknown agent dropped
    assert lesson.discount_agents == ["sales_demand"]
    assert set(lesson.trigger_tags) <= EVENT_TAGS


def test_parse_defaults_when_fields_absent():
    agent = FeedbackAgent.__new__(FeedbackAgent)
    raw = json.dumps({
        "primary_miss_agent": "", "miss_type": "magnitude",
        "missed_factors": [], "over_weighted_factors": [], "agent_score_drift": {},
        "new_lessons": [{"category": "macro", "pattern": "p", "observation": "o",
                         "rule": "r", "confidence": 0.6}],
        "revised_context": {"headline": "h"},
    })
    lesson = agent._parse(raw, _fb_input()).new_lessons[0]
    assert lesson.trigger_tags == []
    assert lesson.prioritise_agents == []


def test_merge_passes_through_claim_fields_on_new_lesson():
    """A brand-new Lesson created from a RawLesson keeps its claim fields."""
    from backend.shared.schemas.feedback import (
        FeedbackAgentOutput, LearningLedger, RawLesson, RevisedContext,
    )

    agent = FeedbackAgent.__new__(FeedbackAgent)
    ledger = LearningLedger(ticker="MARUTI", sector="automobile", last_updated="2026-06-11")
    output = FeedbackAgentOutput(
        primary_miss_agent="risk_macro",
        miss_type="model_bias",
        missed_factors=[],
        over_weighted_factors=[],
        agent_score_drift={},
        new_lessons=[RawLesson(
            category="macro", pattern="rbi_day", observation="o", rule="r",
            confidence=0.7, scope="stock_specific",
            trigger_tags=["central_bank_event"],
            prioritise_agents=["risk_macro"],
            discount_agents=["sales_demand"],
        )],
        revised_context=RevisedContext(headline="h"),
    )
    updated_ledger, lesson_ids = agent.merge_lessons_into_ledger(output, ledger)
    new_lesson = updated_ledger.find_by_pattern("rbi_day")
    assert new_lesson is not None
    assert new_lesson.trigger_tags == ["central_bank_event"]
    assert new_lesson.prioritise_agents == ["risk_macro"]
    assert new_lesson.discount_agents == ["sales_demand"]
