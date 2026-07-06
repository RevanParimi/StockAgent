"""
Compass Phase A — Portfolio Core schemas (spec §4.1).

Virtual-first: holdings are mock-money positions at real NSE prices.
adj_avg_price / adj_qty are corp-action-adjusted — ALL P&L and stop math
uses them, never the raw avg_buy_price (a 1:1 bonus would otherwise look
like a −50% crash and fire a false EXIT).
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["HOLD", "ADD", "TRIM", "EXIT"]


class AppliedCorpAction(BaseModel):
    """One corporate action already applied to a holding (idempotency record)."""
    key: str                       # dedupe key: "{symbol}|{ex_date}|{desc[:40]}"
    ex_date: str                   # ISO date
    kind: Literal["split", "bonus", "dividend"]
    desc: str
    ratio: float = 1.0             # qty multiplier (2.0 for 1:1 bonus, 5.0 for 10→2 split)
    dividend_per_share: float = 0.0
    applied_on: str                # ISO date the sync applied it


class Holding(BaseModel):
    symbol: str
    sector: str
    qty: float                     # as entered by the user — never mutated
    avg_buy_price: float           # as entered — never mutated
    adj_avg_price: float           # corp-action-adjusted; ALL P&L/stop math uses this
    adj_qty: float                 # corp-action-adjusted quantity
    buy_date: str                  # ISO date
    virtual: bool = True           # mock-money position (launch default)
    broker: str = ""
    notes: str = ""
    target_pct: float | None = None
    max_loss_pct: float | None = None
    dividends_received: float = 0.0     # total ₹ credited (adj_qty × dps at each ex-date)
    applied_actions: list[AppliedCorpAction] = Field(default_factory=list)

    def unrealised_pnl_pct(self, close: float) -> float:
        """P&L % vs adjusted cost, dividend-inclusive so HOLD/TRIM scoring
        isn't biased against payers (spec §4.1)."""
        cost = self.adj_avg_price * self.adj_qty
        if cost <= 0:
            return 0.0
        gain = (close - self.adj_avg_price) * self.adj_qty + self.dividends_received
        return gain / cost * 100.0

    def age_days(self, on: date) -> int:
        return (on - date.fromisoformat(self.buy_date)).days


class WatchlistItem(BaseModel):
    symbol: str
    sector: str = ""
    added: str                     # ISO date
    reason: str = ""
    source: Literal["user", "discovery"] = "user"


class Portfolio(BaseModel):
    user_id: str
    holdings: list[Holding] = Field(default_factory=list)
    watchlist: list[WatchlistItem] = Field(default_factory=list)
    cash_deployable: float | None = None      # optional — enables ADD sizing later
    risk_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"
    updated_at: str = ""


class AdviceRecord(BaseModel):
    """One advice-ledger line (append-only JSONL). Outcome fields are filled
    later by the review machinery (Phase D); ledger exists from day one so
    data accumulates immediately (spec §5.3)."""
    date: str
    user_id: str
    symbol: str
    verdict: Verdict
    close: float
    unrealised_pnl_pct: float
    stop_pct: float
    triggers: list[str] = Field(default_factory=list)   # machine-readable rule codes
    notes: list[str] = Field(default_factory=list)      # WAIT_FOR_LTCG, EARNINGS_GAP_PROTECTION, ...
    confidence: float = 0.5
    narrative: str = ""            # LLM narration (research tone, never "advice")
    rationale_hash: str = ""
    outcome_10td: float | None = None
    outcome_30td: float | None = None
    outcome_60td: float | None = None


class CorporateEvent(BaseModel):
    """Forward-looking calendar entry (board meetings / results dates).
    Feeds the advisor's earnings-gap rule (spec §5.2)."""
    symbol: str
    date: str                      # ISO date of the event
    kind: Literal["results", "meeting", "action", "other"] = "other"
    desc: str = ""
