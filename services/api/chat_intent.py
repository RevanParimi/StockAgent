"""
chat_intent.py — deterministic intent classifier for the StockAgent chat system.
No LLM call: fast, predictable, runs before every message.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum


class IntentType(str, Enum):
    SINGLE_STOCK    = "SINGLE_STOCK"
    STOCK_COMPARE   = "STOCK_COMPARE"
    SECTOR_OVERVIEW = "SECTOR_OVERVIEW"
    MULTI_SECTOR    = "MULTI_SECTOR"
    PRICE_QUERY     = "PRICE_QUERY"
    NEWS_QUERY      = "NEWS_QUERY"
    AGENT_QUERY     = "AGENT_QUERY"
    RL_QUERY        = "RL_QUERY"
    GENERAL         = "GENERAL"


# Sector keyword → canonical sector key
_SECTOR_KEYWORDS: dict[str, str] = {
    "auto":        "automobile",
    "automobile":  "automobile",
    "automotive":  "automobile",
    "car":         "automobile",
    "ev":          "automobile",
    "it":          "it_sector",
    "tech":        "it_sector",
    "software":    "it_sector",
    "banking":     "banking_bfsi",
    "bank":        "banking_bfsi",
    "bfsi":        "banking_bfsi",
    "nbfc":        "banking_bfsi",
    "finance":     "banking_bfsi",
    "pharma":      "pharma",
    "energy":      "renewable_energy",
    "renewable":   "renewable_energy",
    "solar":       "renewable_energy",
    "power":       "renewable_energy",
    "fmcg":        "fmcg",
}

# Known NSE tickers the chat recognises
_KNOWN_TICKERS: frozenset[str] = frozenset({
    "MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT",
    "TVSMOTORS", "ASHOKLEY", "TCS", "INFY", "WIPRO", "HCLTECH", "TECHM",
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK",
    "ADANIGREEN", "TATAPOWER", "NTPC", "POWERGRID", "JSWENERGY",
    "APOLLOTYRE", "MRF", "ESCORTS", "BOSCHLTD", "BALKRISIND", "MOTHERSON",
    "LTIM", "INDUSINDBK", "BAJAJFINSV", "BAJFINANCE",
})

_AGENT_NAMES: frozenset[str] = frozenset({
    "sales", "demand", "fundamentals", "pattern", "raw material", "raw materials",
    "sentiment", "policy", "regulatory", "competitive", "intel", "risk", "macro",
    "valuation", "catalyst",
})

_COMPARE_WORDS = re.compile(r"\b(compare|vs|versus|difference|better|worse|relative)\b", re.I)
_PRICE_WORDS   = re.compile(r"\b(price|level|trading at|how much|what is .{0,20} at|current .{0,15} price)\b", re.I)
_NEWS_WORDS    = re.compile(r"\b(why|reason|what happened|news|cause|driving|behind|fall|rise|drop|surge)\b", re.I)
_RL_WORDS      = re.compile(r"\b(trust|accuracy|accurate|learn|weight|which agent|best agent|reliable)\b", re.I)


def _extract_tickers(text: str) -> list[str]:
    words = re.findall(r"[A-Z][A-Z0-9&\-]{1,11}", text.upper())
    return [w for w in words if w in _KNOWN_TICKERS]


def _extract_sectors(text: str) -> list[str]:
    tl = text.lower()
    found: dict[str, str] = {}
    for kw, sector in _SECTOR_KEYWORDS.items():
        if re.search(r"\b" + re.escape(kw) + r"\b", tl):
            found[sector] = sector
    return list(found.keys())


def _has_agent_mention(text: str) -> bool:
    tl = text.lower()
    return any(a in tl for a in _AGENT_NAMES) and "agent" in tl


@dataclass
class IntentResult:
    intent_type: IntentType
    tickers: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    display_label: str = ""

    def as_dict(self) -> dict:
        return {
            "intent_type":   self.intent_type.value,
            "tickers":       self.tickers,
            "sectors":       self.sectors,
            "display_label": self.display_label,
        }


def classify_intent(message: str, history: list[dict]) -> IntentResult:
    """
    Classify user intent from message text + optional conversation history.
    History is scanned for entity carry-over (tickers/sectors from prior turns).
    Returns IntentResult with intent_type, extracted entities, and display_label.
    """
    tickers = _extract_tickers(message)
    sectors = _extract_sectors(message)

    # Entity carry-over from history (last 4 turns)
    if not tickers and not sectors:
        for turn in (history or [])[-4:]:
            content = turn.get("content", "")
            tickers = tickers or _extract_tickers(content)
            sectors = sectors or _extract_sectors(content)

    # RL / trust query — check early (often contains agent words too)
    if _RL_WORDS.search(message):
        return IntentResult(
            IntentType.RL_QUERY, tickers, sectors,
            "[RL_QUERY] Agent accuracy & learning"
        )

    # Agent-specific query
    if _has_agent_mention(message):
        label = f"[AGENT_QUERY] → {tickers[0] if tickers else 'general'}"
        return IntentResult(IntentType.AGENT_QUERY, tickers, sectors, label)

    # Multiple tickers + compare words
    if len(tickers) >= 2 and _COMPARE_WORDS.search(message):
        label = f"[STOCK_COMPARE] → {' · '.join(tickers[:3])}"
        return IntentResult(IntentType.STOCK_COMPARE, tickers, sectors, label)

    # Multiple sectors
    if len(sectors) >= 2:
        label = f"[MULTI_SECTOR] → {' · '.join(sectors)}"
        return IntentResult(IntentType.MULTI_SECTOR, tickers, sectors, label)

    # Single ticker — no compare, no sector query
    if len(tickers) == 1 and not sectors:
        label = f"[SINGLE_STOCK] → {tickers[0]}"
        return IntentResult(IntentType.SINGLE_STOCK, tickers, sectors, label)

    # Single sector overview
    if len(sectors) == 1 and not tickers:
        label = f"[SECTOR_OVERVIEW] → {sectors[0]}"
        return IntentResult(IntentType.SECTOR_OVERVIEW, tickers, sectors, label)

    # Single sector with tickers = stock+sector combo → still single stock
    if tickers and sectors:
        label = f"[SINGLE_STOCK] → {tickers[0]} ({sectors[0]})"
        return IntentResult(IntentType.SINGLE_STOCK, tickers, sectors, label)

    # News / why queries
    if _NEWS_WORDS.search(message):
        label = "[NEWS_QUERY] Market news & drivers"
        return IntentResult(IntentType.NEWS_QUERY, tickers, sectors, label)

    # Price queries
    if _PRICE_WORDS.search(message):
        label = "[PRICE_QUERY] Live price"
        return IntentResult(IntentType.PRICE_QUERY, tickers, sectors, label)

    return IntentResult(IntentType.GENERAL, tickers, sectors, "[GENERAL] General inquiry")
