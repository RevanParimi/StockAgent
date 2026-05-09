import pytest
from services.api.chat_intent import classify_intent, IntentType


def test_single_stock():
    r = classify_intent("What's the outlook for MARUTI?", [])
    assert r.intent_type == IntentType.SINGLE_STOCK
    assert "MARUTI" in r.tickers


def test_stock_compare():
    r = classify_intent("Compare MARUTI vs TATAMOTORS", [])
    assert r.intent_type == IntentType.STOCK_COMPARE
    assert "MARUTI" in r.tickers
    assert "TATAMOTORS" in r.tickers


def test_sector_overview():
    r = classify_intent("How is the auto sector doing today?", [])
    assert r.intent_type == IntentType.SECTOR_OVERVIEW
    assert "automobile" in r.sectors


def test_multi_sector():
    r = classify_intent("Compare auto vs IT and banking sectors", [])
    assert r.intent_type == IntentType.MULTI_SECTOR
    assert len(r.sectors) >= 2


def test_price_query():
    r = classify_intent("What is the price of silver today?", [])
    assert r.intent_type == IntentType.PRICE_QUERY


def test_news_query():
    r = classify_intent("Why is MARUTI falling today?", [])
    # MARUTI present → single stock takes precedence over news
    assert r.intent_type in (IntentType.NEWS_QUERY, IntentType.SINGLE_STOCK)


def test_agent_query():
    r = classify_intent("What does the Sales & Demand agent say about MARUTI?", [])
    assert r.intent_type == IntentType.AGENT_QUERY


def test_rl_query():
    r = classify_intent("Which agent should I trust most for short-term trades?", [])
    assert r.intent_type == IntentType.RL_QUERY


def test_general():
    r = classify_intent("Hello, what can you do?", [])
    assert r.intent_type == IntentType.GENERAL


def test_entity_carryover():
    history = [{"role": "user", "content": "Tell me about MARUTI"}]
    r = classify_intent("What about the risks?", history)
    assert "MARUTI" in r.tickers


def test_display_label_nonempty():
    r = classify_intent("How is banking sector?", [])
    assert r.display_label
    assert "banking_bfsi" in r.display_label


def test_as_dict_keys():
    r = classify_intent("MARUTI price?", [])
    d = r.as_dict()
    assert set(d.keys()) == {"intent_type", "tickers", "sectors", "display_label"}
