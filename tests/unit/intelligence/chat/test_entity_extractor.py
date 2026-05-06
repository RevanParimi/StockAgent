"""
Unit tests for chat/algorithms/entity_extractor.py.
These tests define expected behaviour — the implementation lives in Phase 6.
"""
import pytest


@pytest.mark.parametrize("message,expected_tickers,expected_agents", [
    ("compare MARUTI vs TATAMOTORS",        ["MARUTI", "TATAMOTORS"],    []),
    ("what does the sales demand agent do?", [],                         ["sales_demand"]),
    ("analyze TCS and INFY",                ["TCS", "INFY"],             []),
    ("HDFCBANK fundamentals look strong",   ["HDFCBANK"],                ["fundamentals"]),
    ("hello there",                          [],                         []),
    ("BAJAJ-AUTO risk macro score?",        ["BAJAJ-AUTO"],              ["risk_macro"]),
])
def test_entity_extraction_placeholder(message, expected_tickers, expected_agents):
    """
    Documents expected entity extraction.
    Will become a real test once EntityExtractor is implemented in Phase 6.
    """
    pytest.skip(
        f"Phase 6 pending — expected: extract({message!r}) == "
        f"Entities(tickers={expected_tickers}, agents={expected_agents})"
    )


def test_extractor_normalises_ticker_case():
    pytest.skip("Phase 6: 'maruti' should be extracted as 'MARUTI'")


def test_extractor_detects_sector_context():
    pytest.skip("Phase 6: 'banking stocks' should set sector='banking_bfsi'")
