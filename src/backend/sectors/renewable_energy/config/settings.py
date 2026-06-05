"""Sector-specific settings for Renewable Energy."""
import os

AGENT_WEIGHTS: dict[str, float] = {
    "fundamentals":    0.25,   # -0.05: redistributed to risk agent
    "business":        0.25,
    "valuation":       0.15,   # -0.05: redistributed to risk agent
    "sentiment_policy": 0.15,
    "technical":       0.10,
    "risk":            0.10,   # was 0.0 — DISCOM defaults, grid curtailment, PPA counterparty risk
}

TICKERS: list[str] = ["ADANIGREEN", "TATAPOWER", "TORNTPOWER", "CESC", "SJVN", "NHPC"]
