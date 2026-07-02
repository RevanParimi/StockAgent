"""Tests for the 2026-07 garbage-learning fix.

Root cause: OpenRouter silently rolled qwen3.7-max to a thinking-by-default
snapshot; reasoning burned the max_tokens=1500 budget, JSON truncated
mid-string, and FeedbackAgent's fallback stuffed the parse-error text into
missed_factors — which merge_lessons_into_ledger slugged into the
LearningLedger miss counter ("parse_error:_expecting_value:_line_1_col").

Fix contract, verified here:
  1. Unsalvageable responses → degraded=True, empty missed_factors.
  2. Truncated-but-salvageable responses → partial real analysis, not degraded.
  3. degraded=True → merge_lessons_into_ledger leaves the ledger untouched.
  4. Error-shaped factor strings never reach increment_miss (slug validation).
"""
import json

from backend.shared.schemas.feedback import (
    FeedbackAgentInput,
    FeedbackAgentOutput,
    LearningLedger,
)
from core.intelligence.rl.agents.feedback_agent import (
    VALID_MISS_FACTOR_RE,
    FeedbackAgent,
)


def _fb_input() -> FeedbackAgentInput:
    return FeedbackAgentInput(
        ticker="MARUTI",
        sector="automobile",
        date="2026-07-02",
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


def _agent() -> FeedbackAgent:
    return FeedbackAgent.__new__(FeedbackAgent)  # no LLM client needed for _parse


# ---------------------------------------------------------------------------
# 1. Unsalvageable garbage → degraded, factors empty
# ---------------------------------------------------------------------------

def test_unparseable_response_returns_degraded_with_no_factors():
    out = _agent()._parse("Sorry, I cannot answer that.", _fb_input())
    assert out.degraded is True
    assert out.missed_factors == []
    assert out.new_lessons == []
    assert out.miss_type == "data_gap"


def test_empty_response_returns_degraded():
    out = _agent()._parse("", _fb_input())
    # "" parses to nothing salvageable → degraded, never an error-string factor
    assert out.degraded is True
    assert out.missed_factors == []


# ---------------------------------------------------------------------------
# 2. Truncated JSON → salvage keeps the complete top-level keys
# ---------------------------------------------------------------------------

def test_truncated_json_is_salvaged_not_degraded():
    full = {
        "primary_miss_agent": "risk_macro",
        "miss_type": "external_shock",
        "missed_factors": ["FII outflow", "RBI surprise"],
        "over_weighted_factors": [],
        "agent_score_drift": {"risk_macro": -0.1},
        "revised_context": {"headline": "h"},
    }
    raw = json.dumps(full)
    truncated = raw + ', "new_lessons": [{"category": "macro", "pattern": "unfinished'
    # sanity: truncation actually breaks plain json.loads
    try:
        json.loads(truncated)
        assert False, "expected truncated JSON to be unparseable"
    except json.JSONDecodeError:
        pass

    out = _agent()._parse(truncated, _fb_input())
    assert out.degraded is False
    assert out.primary_miss_agent == "risk_macro"
    assert out.miss_type == "external_shock"
    assert "FII outflow" in out.missed_factors


# ---------------------------------------------------------------------------
# 3. Degraded output must leave the ledger byte-identical
# ---------------------------------------------------------------------------

def test_degraded_output_never_touches_ledger():
    ledger = LearningLedger(ticker="MARUTI", last_updated="2026-07-02")
    before_counter = dict(ledger.miss_counter)
    before_lessons = len(ledger.lessons)

    out = FeedbackAgentOutput(
        primary_miss_agent="unknown",
        miss_type="data_gap",
        missed_factors=["Parse error: Expecting value: line 1 column 823"],
        degraded=True,  # even WITH junk factors present, degraded gates all writes
    )
    updated, lesson_ids = _agent().merge_lessons_into_ledger(out, ledger)

    assert lesson_ids == []
    assert updated.miss_counter == before_counter
    assert len(updated.lessons) == before_lessons


# ---------------------------------------------------------------------------
# 4. Slug validation: error-shaped factors dropped, real factors kept
# ---------------------------------------------------------------------------

def test_error_shaped_factors_are_dropped_real_ones_kept():
    ledger = LearningLedger(ticker="MARUTI", last_updated="2026-07-02")
    out = FeedbackAgentOutput(
        primary_miss_agent="risk_macro",
        miss_type="model_bias",
        missed_factors=[
            "RSI divergence",                                        # legit
            "Parse error: Expecting value: line 1 column 823",        # poison
            "LLM unavailable: Connection timed out",                  # poison
        ],
    )
    _agent().merge_lessons_into_ledger(out, ledger)

    assert ledger.miss_counter.get("rsi_divergence") == 1
    poison = [k for k in ledger.miss_counter if "error" in k or ":" in k]
    assert poison == []
    assert len(ledger.miss_counter) == 1


def test_valid_factor_regex_matches_known_prod_slugs():
    good = [
        "rsi_divergence", "momentum_exhaustion_signals",
        "risk_on_fii_inflow_amplifier", "strong_fundamentals",
        "positive_sentiment_overweight_risk_off", "m&m_supply_chain",
    ]
    bad = [
        "parse_error:_expecting_value:_line_1_col",
        "llm_unavailable:_connection_timed_out",
        "parse_error:_unterminated_string_startin",
        "", "ab",
    ]
    for slug in good:
        assert VALID_MISS_FACTOR_RE.fullmatch(slug), f"should accept {slug!r}"
    for slug in bad:
        assert not VALID_MISS_FACTOR_RE.fullmatch(slug), f"should reject {slug!r}"
