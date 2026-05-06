"""Sector-specific settings for IT Sector."""
import os

AGENT_WEIGHTS: dict[str, float] = {
    "fundamentals": 0.25,
    "global_macro": 0.2,
    "risk_macro": 0.15,
    "peer_benchmark": 0.15,
    "pattern_analysis": 0.1,
    "sentiment": 0.08,
    "transcript_nlp": 0.04,
    "insider_smart_money": 0.03,
}

TICKERS: list[str] = ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "COFORGE"]
