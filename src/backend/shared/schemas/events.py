"""
Company events: what happened to one listed company, typed, dated and sourced.

One record per source item: an NSE announcement, an NSE board-meeting
intimation, a news article, or an NSE disclosure (an insider-trade filing, a
substantial-acquisition filing, a promoter pledge event or a quarter's
shareholding pattern). The feed (core/events/feed.py) writes them; the
investment case, the explanations, the brief and the exit rule read them.
This is the one event schema: the text reader (SA-046) emits the same record.

Dates, never confused:

- `published_at` is when the source published the item, in IST: when we
  could have known it. A date-time when the source gives one (NSE's filing or
  dissemination time), a date when it gives only a day or an age ("5 hours
  ago" counts back from the fetch and is kept as the IST day). None when the
  source gives no usable date; such an event is stored but never counts as new.
- `occurred_from` / `occurred_to` are the days the disclosed thing happened
  (a trade, a pledge, a quarter end), as YYYY-MM-DD, for a disclosure only. An
  insider may trade on 21 Oct and the filing reach NSE on 22 Oct: the event is
  new on 22 Oct.
- `fetched_at` is when the feed fetched it. It never stands in for
  `published_at`.

`published_raw` keeps the source's own date string, so either can be checked.
A disclosure's `facts` keep its figures (values in rupees, shares, percentage
points), so a reader can recompute what `what` says.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# The categories the classifier may answer (core/events/classify.py).
CLASSIFIER_CATEGORIES = ("results", "guidance", "order", "rating", "management", "regulatory",
                         "corporate_action", "deal", "other")
# The categories only a disclosure parser writes (core/events/disclosures.py).
DISCLOSURE_CATEGORIES = ("insider", "pledge", "ownership")
CATEGORIES = CLASSIFIER_CATEGORIES + DISCLOSURE_CATEGORIES
DIRECTIONS = ("positive", "negative", "neutral")
MATERIALITIES = ("high", "medium", "low")
SOURCES = ("nse_announcement", "nse_board_meeting", "news",
           "nse_insider", "nse_sast", "nse_pledge", "nse_shareholding")

Category = Literal["results", "guidance", "order", "rating", "management", "regulatory",
                   "corporate_action", "deal", "other", "insider", "pledge", "ownership"]
Direction = Literal["positive", "negative", "neutral"]
Materiality = Literal["high", "medium", "low"]
Source = Literal["nse_announcement", "nse_board_meeting", "news",
                 "nse_insider", "nse_sast", "nse_pledge", "nse_shareholding"]


class CompanyEvent(BaseModel):
    """One thing that happened to `symbol`, citing the item it came from."""
    id: str                             # the source item's identity; one event per item
    symbol: str                         # the app's symbol (as held), never the model's
    what: str                           # one plain sentence, from the item's own words
    category: Category
    direction: Direction
    materiality: Materiality
    source: Source
    source_url: str | None = None
    announcement_id: str | None = None  # NSE's seq_id for an announcement
    title: str = ""                     # the item's title or NSE subject
    publisher: str = ""                 # the news outlet; "" for NSE
    published_at: str | None = None     # ISO 8601, IST; see the module docstring
    published_raw: str = ""
    occurred_from: str | None = None    # YYYY-MM-DD; a disclosure only
    occurred_to: str | None = None      # YYYY-MM-DD; a disclosure only
    facts: dict = {}                    # a disclosure's figures; see core/events/disclosures.py
    fetched_at: str                     # ISO 8601 date-time, IST
    classifier: str = ""                # the model that typed it, or "rules" for a disclosure

    def published_day(self) -> str | None:
        """The IST calendar day it was published (YYYY-MM-DD), or None."""
        return self.published_at[:10] if self.published_at else None
