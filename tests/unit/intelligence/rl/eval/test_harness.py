"""
Unit tests for core/intelligence/rl/eval/harness.py

EvalHarness.run_eval() is the orchestration layer: load -> replay -> aggregate
-> EvalReport. These tests exercise the synthetic path end-to-end (fast,
deterministic, no filesystem dependency on data/predictions) and the
ablation registry / no-op-on-real-data behaviour.
"""
from __future__ import annotations

import logging

import pytest

from core.intelligence.rl.eval.harness import (
    ABLATION_REGISTRY,
    EvalHarness,
    EvalReport,
)


class TestSyntheticEval:
    def test_run_eval_synthetic_returns_eval_report(self):
        harness = EvalHarness()
        report = harness.run_eval(synthetic=True, n_tickers=2, n_cycles=2, seed=42)

        assert isinstance(report, EvalReport)
        assert report.source == "synthetic"
        assert report.n_entries > 0

    def test_aggregate_metrics_present(self):
        harness = EvalHarness()
        report = harness.run_eval(synthetic=True, n_tickers=2, n_cycles=1, seed=42)

        for key in (
            "direction_accuracy",
            "brier_score",
            "reliability_table",
            "band_coverage",
            "mae_pct",
        ):
            assert key in report.aggregate, f"missing {key} in aggregate"

    def test_per_ticker_and_per_sector_scopes_present(self):
        harness = EvalHarness()
        report = harness.run_eval(synthetic=True, n_tickers=2, n_cycles=1, seed=42)

        assert len(report.per_ticker) == 2
        assert len(report.per_sector) >= 1
        for ticker_metrics in report.per_ticker.values():
            assert "direction_accuracy" in ticker_metrics

    def test_deterministic_for_same_seed(self):
        harness1 = EvalHarness()
        harness2 = EvalHarness()

        report1 = harness1.run_eval(synthetic=True, n_tickers=2, n_cycles=2, seed=42)
        report2 = harness2.run_eval(synthetic=True, n_tickers=2, n_cycles=2, seed=42)

        assert report1.aggregate == report2.aggregate
        assert report1.per_ticker == report2.per_ticker


class TestAblationRegistry:
    def test_registry_has_pre_registered_keys(self):
        assert "calibration_reward" in ABLATION_REGISTRY
        assert "forgetting" in ABLATION_REGISTRY
        assert "executable_claims" in ABLATION_REGISTRY
        assert ABLATION_REGISTRY["calibration_reward"] == "RL_CALIBRATION_REWARD_ENABLED"
        assert ABLATION_REGISTRY["forgetting"] == "RL_FORGETTING_ENABLED"
        assert ABLATION_REGISTRY["executable_claims"] == "RL_CLAIMS_ENABLED"

    def test_synthetic_ablation_reports_delta(self):
        harness = EvalHarness()
        report = harness.run_eval(
            synthetic=True, n_tickers=2, n_cycles=2, seed=42,
            ablate=["calibration_reward"],
        )

        assert "calibration_reward" in report.ablations_run
        assert "calibration_reward" in report.ablation_deltas
        delta = report.ablation_deltas["calibration_reward"]
        assert "direction_accuracy_delta" in delta
        assert "brier_score_delta" in delta

    def test_synthetic_forgetting_ablation_reports_delta(self):
        harness = EvalHarness()
        report = harness.run_eval(
            synthetic=True, n_tickers=2, n_cycles=3, seed=42,
            ablate=["forgetting"],
        )
        assert "forgetting" in report.ablation_deltas

    def test_synthetic_executable_claims_ablation_reports_delta(self):
        harness = EvalHarness()
        report = harness.run_eval(
            synthetic=True, n_tickers=2, n_cycles=2, seed=42,
            ablate=["executable_claims"],
        )

        assert "executable_claims" in report.ablations_run
        assert "executable_claims" in report.ablation_deltas
        delta = report.ablation_deltas["executable_claims"]
        assert "direction_accuracy_delta" in delta
        assert "brier_score_delta" in delta

    def test_unregistered_ablation_key_still_recorded(self):
        """Arbitrary ablation keys should not crash — registry is open-ended."""
        harness = EvalHarness()
        report = harness.run_eval(
            synthetic=True, n_tickers=1, n_cycles=1, seed=42,
            ablate=["some_future_flag"],
        )
        assert "some_future_flag" in report.ablations_run


class TestRealDataAblationNoOp:
    def test_real_data_ablation_logs_warning_and_is_noop(self, caplog):
        harness = EvalHarness()
        with caplog.at_level(logging.WARNING):
            report = harness.run_eval(
                synthetic=False, ablate=["calibration_reward"],
            )

        assert "calibration_reward" in report.ablations_run
        # Real-data ablation cannot re-run history -> no delta computed.
        assert report.ablation_deltas.get("calibration_reward") is None
        assert any(
            "cannot be re-run" in r.message or "no-op" in r.message.lower()
            for r in caplog.records
        )


class TestRealDataDiscovery:
    def test_real_eval_discovers_maruti_data(self):
        """MARUTI automobile data exists in data/predictions and must be found read-only."""
        harness = EvalHarness()
        report = harness.run_eval(synthetic=False)

        assert report.source == "real"
        assert report.n_entries > 0
        assert "MARUTI" in report.per_ticker
        assert "automobile" in report.per_sector

    def test_real_eval_does_not_modify_data_predictions(self, tmp_path):
        """Read-only guarantee: no writes anywhere under data/predictions."""
        import os

        data_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "..", "data", "predictions"
        )
        data_dir = os.path.abspath(data_dir)

        before = {}
        for root, _, files in os.walk(data_dir):
            for f in files:
                p = os.path.join(root, f)
                before[p] = os.path.getmtime(p)

        harness = EvalHarness()
        harness.run_eval(synthetic=False)

        after = {}
        for root, _, files in os.walk(data_dir):
            for f in files:
                p = os.path.join(root, f)
                after[p] = os.path.getmtime(p)

        assert before == after
