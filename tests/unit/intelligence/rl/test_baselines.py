"""
Naive baseline accuracy functions (spec 2026-06-12, section 3).

Pure functions over a month's ordered FeedbackEntry list — no I/O, no LLM.
Directions are compared against entry.actual_direction (3-way classifier:
UP | DOWN | FLAT).
"""
from backend.shared.schemas.feedback import FeedbackEntry
from core.intelligence.rl.eval.baselines import (
    always_down_accuracy,
    always_up_accuracy,
    persistence_accuracy,
)


def _entry(day: int, actual_direction: str) -> FeedbackEntry:
    return FeedbackEntry(
        day=day,
        date=f"2026-06-{day:02d}",
        predicted_close=100.0,
        actual_close=101.0,
        price_error_pct=1.0,
        predicted_verdict="BUY",
        actual_direction=actual_direction,
        direction_correct=True,
    )


# ---------------------------------------------------------------------------
# persistence_accuracy
# ---------------------------------------------------------------------------

def test_persistence_accuracy_known_sequence():
    # Directions: UP, UP, DOWN, UP (days 1-4).
    # Persistence predicts day D's direction = day D-1's actual direction;
    # day 1 has no prior day so it is skipped.
    #   day 2: predict UP (day1=UP),   actual=UP   -> correct
    #   day 3: predict UP (day2=UP),   actual=DOWN -> wrong
    #   day 4: predict DOWN (day3=DOWN), actual=UP -> wrong
    # accuracy = 1/3
    entries = [_entry(1, "UP"), _entry(2, "UP"), _entry(3, "DOWN"), _entry(4, "UP")]
    assert persistence_accuracy(entries) == 1 / 3


def test_persistence_accuracy_all_correct():
    # UP, UP, UP -> day2 predict UP (correct), day3 predict UP (correct) = 2/2 = 1.0
    entries = [_entry(1, "UP"), _entry(2, "UP"), _entry(3, "UP")]
    assert persistence_accuracy(entries) == 1.0


def test_persistence_accuracy_all_wrong():
    # UP, DOWN, UP, DOWN
    #   day2: predict UP (day1=UP), actual=DOWN -> wrong
    #   day3: predict DOWN (day2=DOWN), actual=UP -> wrong
    #   day4: predict UP (day3=UP), actual=DOWN -> wrong
    # accuracy = 0/3 = 0.0
    entries = [_entry(1, "UP"), _entry(2, "DOWN"), _entry(3, "UP"), _entry(4, "DOWN")]
    assert persistence_accuracy(entries) == 0.0


def test_persistence_accuracy_empty_list_none():
    assert persistence_accuracy([]) is None


def test_persistence_accuracy_single_entry_none():
    assert persistence_accuracy([_entry(1, "UP")]) is None


# ---------------------------------------------------------------------------
# always_up_accuracy
# ---------------------------------------------------------------------------

def test_always_up_accuracy_mixed():
    # UP, UP, DOWN, FLAT -> 2/4 = 0.5
    entries = [_entry(1, "UP"), _entry(2, "UP"), _entry(3, "DOWN"), _entry(4, "FLAT")]
    assert always_up_accuracy(entries) == 0.5


def test_always_up_accuracy_all_up():
    entries = [_entry(1, "UP"), _entry(2, "UP")]
    assert always_up_accuracy(entries) == 1.0


def test_always_up_accuracy_all_down():
    entries = [_entry(1, "DOWN"), _entry(2, "DOWN")]
    assert always_up_accuracy(entries) == 0.0


def test_always_up_accuracy_empty_list_none():
    assert always_up_accuracy([]) is None


def test_always_up_accuracy_single_entry_valid():
    # Unlike persistence, always_up needs no prior day -> single entry is valid.
    assert always_up_accuracy([_entry(1, "UP")]) == 1.0
    assert always_up_accuracy([_entry(1, "DOWN")]) == 0.0


# ---------------------------------------------------------------------------
# always_down_accuracy
# ---------------------------------------------------------------------------

def test_always_down_accuracy_mixed():
    # UP, DOWN, DOWN, FLAT -> 2/4 = 0.5
    entries = [_entry(1, "UP"), _entry(2, "DOWN"), _entry(3, "DOWN"), _entry(4, "FLAT")]
    assert always_down_accuracy(entries) == 0.5


def test_always_down_accuracy_all_down():
    entries = [_entry(1, "DOWN"), _entry(2, "DOWN")]
    assert always_down_accuracy(entries) == 1.0


def test_always_down_accuracy_all_up():
    entries = [_entry(1, "UP"), _entry(2, "UP")]
    assert always_down_accuracy(entries) == 0.0


def test_always_down_accuracy_empty_list_none():
    assert always_down_accuracy([]) is None


def test_always_down_accuracy_single_entry_valid():
    assert always_down_accuracy([_entry(1, "DOWN")]) == 1.0
    assert always_down_accuracy([_entry(1, "UP")]) == 0.0
