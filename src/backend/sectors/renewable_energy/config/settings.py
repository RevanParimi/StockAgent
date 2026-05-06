"""Sector-specific settings for Renewable Energy."""
import os

AGENT_WEIGHTS: dict[str, float] = {
    "fundamentals": 0.3,
    "business": 0.25,
    "valuation": 0.2,
    "sentiment_policy": 0.15,
    "technical": 0.1,
    "risk": 0.0,
}

TICKERS: list[str] = ["ADANIGREEN", "TATAPOWER", "TORNTPOWER", "CESC", "SJVN", "NHPC"]
