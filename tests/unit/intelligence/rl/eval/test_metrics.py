"""
Unit tests for core/intelligence/rl/eval/metrics.py

All metrics.py functions are PURE: list[FeedbackEntry] / list[MatchedRecord] in,
float/dict out. No I/O, no PredictionStore, no settings mutation.
"""
from __future__ import annotations

import pytest

from core.schemas.feedback import FeedbackEntry
from core.intelligence.rl.eval.metrics import (
    MatchedRecord,
    direction_accuracy,
    brier_score,
    reliability_table,
    band_coverage,
    mae_pct,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(
    date: str,
    predicted_close: float,
    actual_close: float,
    direction_correct: bool,
    actual_direction: str = "UP",
    predicted_verdict: str = "BUY",
) -> FeedbackEntry:
    price_error_pct = (actual_close - predicted_close) / predicted_close * 100
    return FeedbackEntry(
        day=1,
        date=date,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        predicted_verdict=predicted_verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
    )


def _record(
    date: str,
    confidence: float,
    direction_correct: bool,
    actual_close: float = 100.0,
    price_lower: float | None = 95.0,
    price_upper: float | None = 105.0,
) -> MatchedRecord:
    return MatchedRecord(
        date=date,
        confidence=confidence,
        direction_correct=direction_correct,
        actual_close=actual_close,
        price_lower=price_lower,
        price_upper=price_upper,
    )


# ---------------------------------------------------------------------------
# direction_accuracy
# ---------------------------------------------------------------------------

class TestDirectionAccuracy:
    def test_empty_returns_zero(self):
        assert direction_accuracy([]) == 0.0

    def test_all_hits(self):
        entries = [_entry(f"2026-06-{d:02d}", 100, 101, True) for d in range(1, 4)]
        assert direction_accuracy(entries) == 1.0

    def test_all_misses(self):
        entries = [_entry(f"2026-06-{d:02d}", 100, 99, False) for d in range(1, 4)]
        assert direction_accuracy(entries) == 0.0

    def test_mixed(self):
        entries = [
            _entry("2026-06-01", 100, 101, True),
            _entry("2026-06-02", 100, 99, False),
            _entry("2026-06-03", 100, 101, True),
            _entry("2026-06-04", 100, 99, False),
        ]
        assert direction_accuracy(entries) == 0.5


# ---------------------------------------------------------------------------
# brier_score
# ---------------------------------------------------------------------------

class TestBrierScore:
    def test_empty_returns_zero(self):
        assert brier_score([]) == 0.0

    def test_perfect_confidence_correct_predictions(self):
        # confidence=1.0, outcome=1 (hit) -> (1-1)^2 = 0
        records = [_record("2026-06-01", 1.0, True), _record("2026-06-02", 1.0, True)]
        assert brier_score(records) == pytest.approx(0.0)

    def test_perfect_confidence_wrong_predictions(self):
        # confidence=1.0, outcome=0 (miss) -> (1-0)^2 = 1
        records = [_record("2026-06-01", 1.0, False), _record("2026-06-02", 1.0, False)]
        assert brier_score(records) == pytest.approx(1.0)

    def test_mixed_confidence_and_outcomes(self):
        # confidence=0.5 hit -> (0.5-1)^2 = 0.25
        # confidence=0.5 miss -> (0.5-0)^2 = 0.25
        records = [_record("2026-06-01", 0.5, True), _record("2026-06-02", 0.5, False)]
        assert brier_score(records) == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# reliability_table
# ---------------------------------------------------------------------------

class TestReliabilityTable:
    def test_empty_returns_empty_dict(self):
        assert reliability_table([]) == {}

    def test_buckets_by_confidence_decile(self):
        records = [
            _record("2026-06-01", 0.55, True),   # decile [0.5, 0.6)
            _record("2026-06-02", 0.58, False),  # decile [0.5, 0.6)
            _record("2026-06-03", 0.95, True),   # decile [0.9, 1.0]
        ]
        table = reliability_table(records)
        # Two buckets present
        assert set(table.keys()) <= {"0.5-0.6", "0.9-1.0"}
        bucket_low = table["0.5-0.6"]
        assert bucket_low["n"] == 2
        assert bucket_low["hit_rate"] == pytest.approx(0.5)
        bucket_high = table["0.9-1.0"]
        assert bucket_high["n"] == 1
        assert bucket_high["hit_rate"] == pytest.approx(1.0)

    def test_confidence_one_falls_in_top_bucket(self):
        records = [_record("2026-06-01", 1.0, True)]
        table = reliability_table(records)
        assert "0.9-1.0" in table
        assert table["0.9-1.0"]["n"] == 1


# ---------------------------------------------------------------------------
# band_coverage
# ---------------------------------------------------------------------------

class TestBandCoverage:
    def test_empty_returns_zero(self):
        assert band_coverage([]) == 0.0

    def test_all_within_band(self):
        records = [
            _record("2026-06-01", 0.5, True, actual_close=100.0, price_lower=95.0, price_upper=105.0),
            _record("2026-06-02", 0.5, True, actual_close=95.0, price_lower=95.0, price_upper=105.0),
            _record("2026-06-03", 0.5, True, actual_close=105.0, price_lower=95.0, price_upper=105.0),
        ]
        assert band_coverage(records) == pytest.approx(1.0)

    def test_some_outside_band(self):
        records = [
            _record("2026-06-01", 0.5, True, actual_close=100.0, price_lower=95.0, price_upper=105.0),
            _record("2026-06-02", 0.5, True, actual_close=110.0, price_lower=95.0, price_upper=105.0),
        ]
        assert band_coverage(records) == pytest.approx(0.5)

    def test_skips_records_with_missing_band(self):
        records = [
            _record("2026-06-01", 0.5, True, actual_close=100.0, price_lower=None, price_upper=None),
            _record("2026-06-02", 0.5, True, actual_close=100.0, price_lower=95.0, price_upper=105.0),
        ]
        # Only the second record has a usable band -> coverage 1.0
        assert band_coverage(records) == pytest.approx(1.0)

    def test_all_missing_band_returns_zero(self):
        records = [
            _record("2026-06-01", 0.5, True, actual_close=100.0, price_lower=None, price_upper=None),
        ]
        assert band_coverage(records) == 0.0


# ---------------------------------------------------------------------------
# mae_pct
# ---------------------------------------------------------------------------

class TestMaePct:
    def test_empty_returns_zero(self):
        assert mae_pct([]) == 0.0

    def test_mean_absolute_error(self):
        entries = [
            _entry("2026-06-01", 100, 102, True),   # +2%
            _entry("2026-06-02", 100, 98, False),   # -2%
        ]
        assert mae_pct(entries) == pytest.approx(2.0)

    def test_mixed_errors(self):
        entries = [
            _entry("2026-06-01", 100, 101, True),   # +1%
            _entry("2026-06-02", 100, 95, False),   # -5%
        ]
        assert mae_pct(entries) == pytest.approx(3.0)
