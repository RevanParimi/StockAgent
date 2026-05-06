"""Sector-specific settings for Banking BFSI."""
import os

AGENT_WEIGHTS: dict[str, float] = {
    "fundamentals": 0.25,
    "risk": 0.2,
    "macro_policy": 0.2,
    "institutional": 0.15,
    "pattern_analysis": 0.15,
    "universe_setup": 0.05,
}

TICKERS: list[str] = ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANKBARODA"]
