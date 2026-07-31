"""
F2 — the FeedbackAgent's attribution-honesty rule.

The prompt already forbids citing factors absent from market_context_today and
caps external_shock at 20% of days. Combined with a blind news day that left
exactly one escape route for a large unexplained move: model_bias /
direction_flip, both full 1.0x weight penalties. Absence of evidence was being
scored as evidence of a biased agent, and lessons were written off it.

The rule added here does NOT hand the agent a new excuse — the external_shock
cap is untouched. It tells it to say "unexplained" rather than to guess.

⚠ Shipping this deliberately breaks the miss_type distribution (as Wave G did).
Ship date is recorded in the intelligence-loop audit memory.
"""
import pytest

from core.config.prompts.shared.feedback_agent import build_system_prompt

AGENTS = ["risk_macro", "sales_demand"]


@pytest.fixture
def prompt() -> str:
    return build_system_prompt("automobile", AGENTS)


def test_prompt_states_absent_news_is_not_evidence_of_model_bias(prompt):
    """The core rule: blindness must not be scored as agent bias."""
    lowered = prompt.lower()
    assert "absence of news is not evidence" in lowered
    assert "model_bias" in prompt


def test_prompt_names_the_large_move_threshold(prompt):
    """The rule has to be actionable — it fires on large unexplained moves."""
    assert "3%" in prompt


def test_prompt_still_caps_external_shock_at_20_percent(prompt):
    """The new rule must not become a back door around the cap."""
    assert "20%" in prompt
    assert "external_shock must not exceed" in prompt


def test_prompt_explains_the_market_wide_context_block(prompt):
    """
    The agent now sometimes receives macro items instead of company news; it
    must know they are market-wide, not stock-specific evidence.
    """
    assert "[MARKET-WIDE CONTEXT" in prompt


def test_prompt_still_forbids_inventing_factors(prompt):
    """The pre-existing grounding rule is not relaxed by the new one."""
    assert "Do NOT invent factors" in prompt
