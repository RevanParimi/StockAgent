"""PI Prospect P0 — issue-window state machine."""
from datetime import date

import pytest

from core.ipo.calendar import STATES, issue_state

_OPEN = {"issue_start": "2026-08-11", "issue_end": "2026-08-13", "listing_date": ""}


@pytest.mark.parametrize("on,expected", [
    (date(2026, 8, 10), "upcoming"),   # day before it opens
    (date(2026, 8, 11), "open"),       # first day, inclusive
    (date(2026, 8, 12), "open"),
    (date(2026, 8, 13), "open"),       # last day, inclusive
    (date(2026, 8, 14), "closed"),     # bidding done, not yet listed
])
def test_window_boundaries_are_inclusive(on, expected):
    assert issue_state(_OPEN, on) == expected


def test_listed_wins_over_a_closed_window():
    rec = {**_OPEN, "listing_date": "2026-08-18"}
    assert issue_state(rec, date(2026, 8, 17)) == "closed"
    assert issue_state(rec, date(2026, 8, 18)) == "listed"   # listing day itself
    assert issue_state(rec, date(2026, 9, 1)) == "listed"


def test_missing_or_unparseable_dates_are_unknown():
    assert issue_state({}, date(2026, 8, 12)) == "unknown"
    assert issue_state({"issue_start": "2026-08-11"}, date(2026, 8, 12)) == "unknown"
    assert issue_state({"issue_start": "garbage", "issue_end": "2026-08-13"},
                       date(2026, 8, 12)) == "unknown"


def test_every_returned_state_is_declared():
    assert issue_state(_OPEN, date(2026, 8, 12)) in STATES
