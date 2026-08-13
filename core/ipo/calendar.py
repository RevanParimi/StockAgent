"""Issue-window state machine (spec section 5, P0).

Pure functions over a record normalised by services/data/fetchers/ipo.py. The
brief renders IPOs under headings that assert a state ("IPOs OPEN NOW"), so
that state has to be derived rather than assumed — before this existed, a
closed issue kept rendering as open because nothing parsed the window at all.
"""
from __future__ import annotations

from datetime import date

STATES: tuple[str, ...] = ("upcoming", "open", "closed", "listed", "unknown")


def _iso(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def issue_state(rec: dict, on: date) -> str:
    """Where `rec` sits in its lifecycle on `on`.

    Window bounds are INCLUSIVE: bidding is open on both the start and the end
    date. `listed` outranks everything — once the tape exists the window is
    history, and a record can legitimately carry both.
    """
    listed_on = _iso(rec.get("listing_date"))
    if listed_on is not None and listed_on <= on:
        return "listed"

    start, end = _iso(rec.get("issue_start")), _iso(rec.get("issue_end"))
    if start is None or end is None:
        return "unknown"
    if on < start:
        return "upcoming"
    if on > end:
        return "closed"
    return "open"
