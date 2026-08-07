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

Verdict = Literal["HOLD", "ADD", "TRIM", "EXIT", "SWITCH"]


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

    def sell(self, sell_qty: float, price: float) -> float:
        """Reduce the live (adj_*) position by sell_qty shares at price.
        Returns realized P&L incl. pro-rata dividends; moves that dividend
        slice out of dividends_received so remaining unrealised P&L doesn't
        double-count it. Raw qty/avg_buy_price stay as entered (entry
        history); adj_* is the live position (Autopilot spec §3/§4)."""
        if sell_qty <= 0 or self.adj_qty <= 0 or sell_qty > self.adj_qty + 1e-9:
            raise ValueError(
                f"invalid sell qty {sell_qty} for {self.symbol} (adj_qty={self.adj_qty})"
            )
        fraction = min(1.0, sell_qty / self.adj_qty)
        realized = (price - self.adj_avg_price) * sell_qty \
            + self.dividends_received * fraction
        self.dividends_received = round(self.dividends_received * (1 - fraction), 2)
        self.adj_qty = round(self.adj_qty - sell_qty, 6)
        return round(realized, 2)


class WatchlistItem(BaseModel):
    symbol: str
    sector: str = ""
    added: str                     # ISO date
    reason: str = ""
    source: Literal["user", "discovery", "autopilot"] = "user"


class Portfolio(BaseModel):
    user_id: str
    holdings: list[Holding] = Field(default_factory=list)
    watchlist: list[WatchlistItem] = Field(default_factory=list)
    cash_deployable: float | None = None      # optional — enables ADD sizing later
    capital_in: float = 0.0                   # total mock money ever put in
    autopilot: bool = False                   # advisor-executed trading opt-in
    last_autopilot_run: str = ""              # ISO date of last executed run
    risk_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"
    updated_at: str = ""


class AdviceRecord(BaseModel):
    """One advice-ledger line (append-only JSONL).

    DEPRECATED FIELDS: outcome_10td / outcome_30td / outcome_60td were added
    for a "Phase D review machinery" that was never built — nothing has ever
    written them, so every row in every ledger carries NULL. They are kept for
    ledger-parsing compatibility and MUST NOT be used as a data source.

    Graded outcomes live in data/portfolio/<user>/advice_outcomes.jsonl, keyed
    by "<date>|<symbol>|<rationale_hash>" — see core/audit/ and
    docs/superpowers/specs/2026-08-07-verification-layer-design.md. The ledger
    is deliberately never rewritten: grading is derived data and derived data
    must not be able to corrupt the record of what the user was told.
    """
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
    switch_candidate: str = ""     # SWITCH only: the stronger shelf idea's symbol
    rationale_hash: str = ""
    # DEPRECATED — never written by anything. See the class docstring.
    outcome_10td: float | None = None
    outcome_30td: float | None = None
    outcome_60td: float | None = None


class TransactionRecord(BaseModel):
    """One executed virtual trade (append-only transactions.jsonl —
    Autopilot spec §3.2). The ledger is the audit authority; portfolio.json
    is derived state."""
    txn_id: str                    # sha256(user|date|symbol|side|ref)[:16]
    date: str                      # trade/review date (ISO)
    ts: str                        # UTC timestamp (ISO)
    user_id: str
    symbol: str
    side: Literal["BUY", "SELL", "DIV"]   # DIV = dividend cash credit (qty 0)
    qty: float                     # whole shares (0 for DIV)
    price: float
    value: float                   # qty × price
    cash_before: float
    cash_after: float
    holding_qty_after: float
    realized_pnl: float = 0.0      # SELL only
    source: Literal["autopilot", "seed", "manual"] = "autopilot"
    verdict: str = ""              # originating advisor verdict, "" for seed/manual
    advice_ref: str = ""           # "<date>|<symbol>|<rationale_hash>"
    triggers: list[str] = Field(default_factory=list)
    note: str = ""
    # Piece A transparency (spec 2026-07-27) — all optional so historical
    # ledger rows keep parsing; the ledger itself is never rewritten.
    cost_basis: float | None = None   # SELL: holding adj_avg_price at sale
    pnl_pct: float | None = None      # SELL: realized P&L % vs cost_basis
    reason: str = ""                  # advice narrative at execution time


class CorporateEvent(BaseModel):
    """Forward-looking calendar entry (board meetings / results dates).
    Feeds the advisor's earnings-gap rule (spec §5.2)."""
    symbol: str
    date: str                      # ISO date of the event
    kind: Literal["results", "meeting", "action", "other"] = "other"
    desc: str = ""
