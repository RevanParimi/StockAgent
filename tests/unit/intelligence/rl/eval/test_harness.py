"""
Unit tests for core/intelligence/rl/eval/harness.py

EvalHarness.run_eval() is the orchestration layer: load -> replay -> aggregate
-> EvalReport. These tests exercise the synthetic path end-to-end (fast,
deterministic, no filesystem dependency on data/predictions), the ablation
registry / no-op-on-real-data behaviour, and discovery of a predictions tree
the tests build themselves.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from core.intelligence.rl.eval.harness import (
    ABLATION_REGISTRY,
    EvalHarness,
    EvalReport,
)
from core.intelligence.rl.eval.synthetic import SyntheticLogGenerator
from core.intelligence.rl.stores.prediction_store import PredictionStore


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

    def test_synthetic_ablation_delta_carries_caveat(self):
        """AUD-072: synthetic deltas are generator artifacts and must say so."""
        harness = EvalHarness()
        report = harness.run_eval(
            synthetic=True, ablate=["calibration_reward"],
            n_tickers=1, n_cycles=1, seed=7,
        )
        delta = report.ablation_deltas["calibration_reward"]
        assert "caveat" in delta
        assert "synthetic" in delta["caveat"].lower()

    def test_unregistered_ablation_key_still_recorded(self):
        """Arbitrary ablation keys should not crash — registry is open-ended."""
        harness = EvalHarness()
        report = harness.run_eval(
            synthetic=True, n_tickers=1, n_cycles=1, seed=42,
            ablate=["some_future_flag"],
        )
        assert "some_future_flag" in report.ablations_run


def _history_tree(base: Path) -> dict:
    """A predictions tree laid out like data/predictions, built by the test
    (SA-005: the suite never reads the checkout's runtime data).

    automobile/MARUTI  two cycles, each with an envelope and feedback log
    automobile/TATAMOTORS  a feedback log whose envelope is missing
    banking_bfsi/HDFCBANK  one cycle
    banking_bfsi/SBIN  an empty feedback log (skipped by design)
    plus a control log and a stray note that do not match the feedback name.

    Returns the expected discovery, counted from what was written.
    """
    pairs = SyntheticLogGenerator(seed=11).generate(n_tickers=6, n_cycles=3)
    # One pair per cycle id: the generator gives cycles 0 and 1 the same month.
    by_ticker, seen = {}, set()
    for envelope, log in pairs:
        if envelope.cycle_id not in seen:
            seen.add(envelope.cycle_id)
            by_ticker.setdefault(envelope.ticker, []).append((envelope, log))
    expected = {"entries": 0, "tickers": set(), "sectors": set()}
    for ticker, keep_envelope, cycles in (("MARUTI", True, 2), ("TATAMOTORS", False, 1),
                                          ("HDFCBANK", True, 1)):
        for envelope, log in by_ticker[ticker][:cycles]:
            store = PredictionStore(ticker, sector=envelope.sector, base_dir=str(base))
            if keep_envelope:
                store.save_envelope(envelope)
            store.save_feedback_log(log)
            expected["entries"] += len(log.entries)
            expected["tickers"].add(ticker)
            expected["sectors"].add(envelope.sector)
    empty_envelope, empty_log = by_ticker["HDFCBANK"][0]
    sbin = PredictionStore("SBIN", sector="banking_bfsi", base_dir=str(base))
    sbin.save_feedback_log(empty_log.model_copy(update={"ticker": "SBIN", "entries": [],
                                                        "cycle_id": "SBIN_2026-01"}))
    maruti_dir = base / "automobile" / "MARUTI"
    (maruti_dir / "MARUTI_2026-01_control_log.json").write_text("{}", encoding="utf-8")
    (maruti_dir / "notes.txt").write_text("not a feedback log", encoding="utf-8")
    return expected


def _digest_tree(base: Path) -> dict[str, str]:
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob("*")) if p.is_file()}


class TestRealDataAblationNoOp:
    def test_real_data_ablation_logs_warning_and_is_noop(self, caplog, tmp_path):
        _history_tree(tmp_path)
        harness = EvalHarness(base_dir=str(tmp_path))
        with caplog.at_level(logging.WARNING):
            report = harness.run_eval(
                synthetic=False, ablate=["calibration_reward"],
            )

        assert report.n_entries > 0
        assert "calibration_reward" in report.ablations_run
        # Real-data ablation cannot re-run history -> no delta computed.
        assert report.ablation_deltas.get("calibration_reward") is None
        assert any(
            "cannot be re-run" in r.message or "no-op" in r.message.lower()
            for r in caplog.records
        )


class TestRealDataDiscovery:
    def test_real_eval_discovers_maruti_data(self, tmp_path):
        """MARUTI automobile history in a data/predictions-shaped tree is found."""
        expected = _history_tree(tmp_path)
        report = EvalHarness(base_dir=str(tmp_path)).run_eval(synthetic=False)

        assert report.source == "real"
        assert "MARUTI" in report.per_ticker
        assert "automobile" in report.per_sector
        assert report.n_entries == expected["entries"]
        # The orphan log counts, the empty one does not.
        assert set(report.per_ticker) == expected["tickers"] == {"MARUTI", "TATAMOTORS", "HDFCBANK"}
        assert set(report.per_sector) == expected["sectors"] == {"automobile", "banking_bfsi"}

    def test_real_eval_default_root_is_the_prediction_data_dir(self, tmp_path, monkeypatch):
        from core.intelligence.rl.eval import harness as harness_mod

        expected = _history_tree(tmp_path)
        monkeypatch.setattr(harness_mod.settings, "PREDICTION_DATA_DIR", str(tmp_path))
        report = EvalHarness().run_eval(synthetic=False)
        assert report.n_entries == expected["entries"]

    def test_missing_root_yields_an_empty_report(self, tmp_path):
        report = EvalHarness(base_dir=str(tmp_path / "absent")).run_eval(synthetic=False)
        assert report.source == "real"
        assert report.n_entries == 0 and report.per_ticker == {}

    def test_real_eval_does_not_modify_the_tree(self, tmp_path):
        """Read-only guarantee: every byte and file under the root is unchanged."""
        _history_tree(tmp_path)
        before = _digest_tree(tmp_path)

        EvalHarness(base_dir=str(tmp_path)).run_eval(synthetic=False)

        assert _digest_tree(tmp_path) == before
