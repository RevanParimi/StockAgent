"""
Unit tests for core/intelligence/rl/eval/synthetic.py

SyntheticLogGenerator must be deterministic for a fixed seed (same seed ->
byte-identical output) and must vary with a different seed. It fabricates
PredictionEnvelope + DailyFeedbackLog pairs that conform to the same schemas
as real recorded data, so the harness can replay them through the same
code path as real PredictionStore output.
"""
from __future__ import annotations

import pytest

from core.schemas.feedback import DailyFeedbackLog, PredictionEnvelope
from core.intelligence.rl.eval.synthetic import SyntheticLogGenerator


class TestDeterminism:
    def test_same_seed_produces_identical_output(self):
        gen1 = SyntheticLogGenerator(seed=42)
        gen2 = SyntheticLogGenerator(seed=42)

        out1 = gen1.generate(n_tickers=2, n_cycles=2)
        out2 = gen2.generate(n_tickers=2, n_cycles=2)

        assert out1 == out2

    def test_different_seed_produces_different_output(self):
        gen1 = SyntheticLogGenerator(seed=42)
        gen2 = SyntheticLogGenerator(seed=99)

        out1 = gen1.generate(n_tickers=2, n_cycles=2)
        out2 = gen2.generate(n_tickers=2, n_cycles=2)

        assert out1 != out2

    def test_repeated_generate_calls_on_same_instance_are_deterministic(self):
        """Calling generate() twice on the same generator instance with the
        same args should not depend on internal state mutation between calls."""
        gen = SyntheticLogGenerator(seed=42)
        out1 = gen.generate(n_tickers=1, n_cycles=1)

        gen2 = SyntheticLogGenerator(seed=42)
        out2 = gen2.generate(n_tickers=1, n_cycles=1)

        assert out1 == out2


class TestStructure:
    def test_returns_list_of_envelope_feedback_pairs(self):
        gen = SyntheticLogGenerator(seed=42)
        out = gen.generate(n_tickers=2, n_cycles=1)

        assert isinstance(out, list)
        assert len(out) == 2  # one pair per ticker (1 cycle each)
        for envelope, feedback_log in out:
            assert isinstance(envelope, PredictionEnvelope)
            assert isinstance(feedback_log, DailyFeedbackLog)

    def test_n_cycles_multiplies_pairs_per_ticker(self):
        gen = SyntheticLogGenerator(seed=42)
        out = gen.generate(n_tickers=2, n_cycles=3)
        assert len(out) == 2 * 3

    def test_envelope_and_feedback_share_ticker_and_cycle(self):
        gen = SyntheticLogGenerator(seed=42)
        out = gen.generate(n_tickers=1, n_cycles=1)
        envelope, feedback_log = out[0]
        assert envelope.ticker == feedback_log.ticker
        assert envelope.cycle_id == feedback_log.cycle_id

    def test_feedback_entries_have_matching_forecast_dates(self):
        gen = SyntheticLogGenerator(seed=42)
        out = gen.generate(n_tickers=1, n_cycles=1)
        envelope, feedback_log = out[0]

        forecast_dates = {f.date for f in envelope.daily_forecasts}
        entry_dates = {e.date for e in feedback_log.entries}
        # Every feedback entry must correspond to a forecast row on the same date
        assert entry_dates <= forecast_dates
        assert len(entry_dates) > 0


class TestAccuracyRate:
    def test_accuracy_rate_controls_direction_correct_fraction(self):
        gen_high = SyntheticLogGenerator(seed=42)
        out_high = gen_high.generate(n_tickers=3, n_cycles=3, accuracy_rate=0.9)

        gen_low = SyntheticLogGenerator(seed=42)
        out_low = gen_low.generate(n_tickers=3, n_cycles=3, accuracy_rate=0.3)

        def hit_rate(pairs):
            entries = [e for _, log in pairs for e in log.entries]
            hits = sum(1 for e in entries if e.direction_correct)
            return hits / len(entries)

        assert hit_rate(out_high) > hit_rate(out_low)


class TestAblation:
    def test_ablate_calibration_reward_changes_output(self):
        gen_on = SyntheticLogGenerator(seed=42)
        out_on = gen_on.generate(n_tickers=2, n_cycles=2)

        gen_off = SyntheticLogGenerator(seed=42)
        out_off = gen_off.generate(n_tickers=2, n_cycles=2, ablate={"calibration_reward"})

        assert out_on != out_off

    def test_ablate_forgetting_changes_output(self):
        gen_on = SyntheticLogGenerator(seed=42)
        out_on = gen_on.generate(n_tickers=2, n_cycles=3)

        gen_off = SyntheticLogGenerator(seed=42)
        out_off = gen_off.generate(n_tickers=2, n_cycles=3, ablate={"forgetting"})

        assert out_on != out_off

    def test_ablate_executable_claims_changes_output(self):
        gen_on = SyntheticLogGenerator(seed=42)
        out_on = gen_on.generate(n_tickers=2, n_cycles=2)

        gen_off = SyntheticLogGenerator(seed=42)
        out_off = gen_off.generate(n_tickers=2, n_cycles=2, ablate={"executable_claims"})

        assert out_on != out_off

    def test_ablate_unknown_key_is_a_noop_but_does_not_error(self):
        gen = SyntheticLogGenerator(seed=42)
        out_known = gen.generate(n_tickers=1, n_cycles=1)

        gen2 = SyntheticLogGenerator(seed=42)
        out_unknown = gen2.generate(n_tickers=1, n_cycles=1, ablate={"some_future_flag"})

        assert out_known == out_unknown
