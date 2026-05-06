"""
Unit tests for chat/algorithms/intent_detector.py.
These tests define expected behaviour — the implementation lives in Phase 6.

Import path (after Phase 6): from backend.intelligence.chat.algorithms.intent_detector import IntentDetector
"""
import pytest


# ── Pure intent classification rules (tested against expected values) ──────

@pytest.mark.parametrize("message,expected_intent", [
    # compare_tickers
    ("compare MARUTI vs TATAMOTORS",                    "compare_tickers"),
    ("MARUTI or M&M — which is better?",                "compare_tickers"),
    ("what's the difference between TCS and INFY",      "compare_tickers"),
    # explain_agent
    ("what does the Sales & Demand agent do?",          "explain_agent"),
    ("explain pattern analysis",                        "explain_agent"),
    ("how does the fundamentals agent work?",           "explain_agent"),
    # score_query
    ("what is MARUTI's score?",                         "score_query"),
    ("what is the verdict for HDFCBANK?",               "score_query"),
    ("give me TATAMOTORS rating",                       "score_query"),
    # analyze
    ("analyze BAJAJ-AUTO",                              "analyze"),
    ("should I buy ICICIBANK?",                         "analyze"),
    ("run analysis on ADANIGREEN",                      "analyze"),
    # generic
    ("hello",                                           "generic"),
    ("how are you?",                                    "generic"),
])
def test_intent_classification_placeholder(message, expected_intent):
    """
    Documents expected intent mapping.
    Will become a real test once IntentDetector is implemented in Phase 6.
    """
    pytest.skip(f"Phase 6 pending — expected: classify({message!r}) == {expected_intent!r}")


def test_intent_detector_is_pure():
    """IntentDetector.classify() must have no external dependencies — pure string matching."""
    pytest.skip("Verify in Phase 6: IntentDetector imports only stdlib (re, string)")


def test_intent_detector_case_insensitive():
    """Classification must work regardless of message case."""
    pytest.skip("Phase 6: classify('COMPARE maruti VS tatamotors') == 'compare_tickers'")
