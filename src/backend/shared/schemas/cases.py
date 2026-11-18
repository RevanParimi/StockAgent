"""
PR-005: the investment case of one holding, written when it is bought.

It says why we own the stock (pillars, each with cited evidence), what we
expect, what would prove us wrong, and what we watch next. Stored per user
and symbol in data/portfolio/<user>/cases/<SYMBOL>.jsonl; a change appends a
new version and never edits an old one (core/portfolio/cases.py).

Every figure the model writes must be a figure of the input it cites; prices
and dates are set by code, never by the model. `written` says when it was
written: `at_purchase` only by a buy path on the buy's own day; any other
case, a backfill above all, is `after_purchase`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WRITTEN = ("at_purchase", "after_purchase")
AUTHORS = ("model", "deterministic")
BUY_PATHS = ("switch", "deploy", "manual", "backfill")
PILLAR_STATUSES = ("intact", "challenged")


class CaseInput(BaseModel):
    """One input the case may cite, as the bundle held it: its id, its kind
    and when it was known (IST). The text itself is not stored here."""
    ref: str                               # "A1", "S1", "D1", "F1", "E1", ...
    kind: str                              # analysis | shelf_idea | dossier | fundamentals | event
    known_at: str                          # ISO date-time, IST: when it could have been known
    label: str = ""                        # what it is, for people ("deep dive of 2026-10-17")


class CaseEvidence(BaseModel):
    fact: str
    ref: str                               # the CaseInput it cites
    source: str                            # that input's kind, set by code
    date: str                              # that input's day (YYYY-MM-DD), set by code


class PillarChallenge(BaseModel):
    """A company event that contradicted the pillar (or a results day's re-check)."""
    event_id: str
    published_at: str
    source: str                            # the event's source: nse_announcement, news, ...
    category: str
    what: str
    on: str                                # the review day it was read
    why: str                               # "negative results: every pillar is re-checked", ...


class Pillar(BaseModel):
    claim: str
    evidence: list[CaseEvidence] = Field(default_factory=list)
    # The event categories (schemas/events.py) whose negative news would
    # contradict this pillar. A results event re-checks every pillar.
    watch_categories: list[str] = Field(default_factory=list)
    status: Literal["intact", "challenged"] = "intact"
    challenges: list[PillarChallenge] = Field(default_factory=list)
    last_checked: str = ""                 # the last results day that re-checked it


class Expectation(BaseModel):
    text: str = ""
    # The analysis's price target, in the buy day's rupees; None when it
    # gave none or its basis could not be established (`gap`).
    target: float | None = None
    horizon_months: int | None = None      # from the analysis's recovery timeline, in quarters x 3
    ref: str = ""                          # the CaseInput it comes from
    gap: str = ""


class Invalidation(BaseModel):
    """What would prove the case wrong. `price` is in the buy day's rupees,
    used by the evidence exit rule only inside the window: above the
    holding's stop price on the purchase day and at least
    `advisor.case_noise_atr_mult` x ATR% below the entry. None, with `gap`,
    otherwise."""
    price: float | None = None
    price_at_dive: float | None = None     # the shelf idea's level, in its deep dive's rupees
    dived: str = ""                        # that deep dive's day
    note: str = ""                         # the conversion and the window, for people
    gap: str = ""                          # why no price: the basis, or which side of the window
    stop_price: float | None = None        # the holding's stop on the purchase day
    noise_line: float | None = None        # entry x (1 - mult x ATR%)
    business: list[str] = Field(default_factory=list)


class WatchItem(BaseModel):
    what: str
    date: str = ""                         # YYYY-MM-DD when known
    ref: str = ""


class InvestmentCase(BaseModel):
    symbol: str
    user_id: str
    opened_on: str                         # the holding's buy date: one holding, one case
    entry_price: float
    pillars: list[Pillar] = Field(default_factory=list)
    expectation: Expectation = Field(default_factory=Expectation)
    invalidation: Invalidation = Field(default_factory=Invalidation)
    watch_next: list[WatchItem] = Field(default_factory=list)
    one_line: str = ""                     # the case in one sentence, for the portfolio screen
    written: Literal["at_purchase", "after_purchase"]
    author: Literal["model", "deterministic"]
    fallback_reason: str = ""              # why the model's case was not stored
    buy_path: Literal["switch", "deploy", "manual", "backfill"]
    created_at: str                        # ISO date-time, IST
    as_of: str                             # ISO date-time, IST: every input was known before it
    inputs: list[CaseInput] = Field(default_factory=list)
    source_run_id: str = ""                # the analysis run it rests on
    version: int = 1
    change: str = "opened"                 # what this version changed
    events_read: list[str] = Field(default_factory=list)   # event ids the pillar review read
