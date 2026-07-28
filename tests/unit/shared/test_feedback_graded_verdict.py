"""AUD-117 — FeedbackEntry records the verdict direction_correct was graded against."""
from backend.shared.schemas.feedback import FeedbackEntry


def _entry(**over):
    base = dict(day=1, date="2026-07-28", predicted_close=100.0, actual_close=99.0,
                price_error_pct=-1.0, predicted_verdict="BUY",
                actual_direction="DOWN", direction_correct=False)
    base.update(over)
    return FeedbackEntry(**base)


def test_graded_verdict_defaults_empty():
    # Backward-compatible: entries written before the field carry "".
    assert _entry().graded_verdict == ""


def test_graded_verdict_set_and_roundtrips():
    e = _entry(graded_verdict="STRONG SELL")
    assert e.graded_verdict == "STRONG SELL"
    assert FeedbackEntry(**e.model_dump()).graded_verdict == "STRONG SELL"
