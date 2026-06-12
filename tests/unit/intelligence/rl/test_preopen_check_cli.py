"""
tests/unit/intelligence/rl/test_preopen_check_cli.py
=======================================================
Living Envelope (RL Phase 2.5), Component 3 — `preopen-check` CLI subcommand.

Covers:
  - `python -m services.scheduler.run_schedule preopen-check [--ticker X
    --sector Y]` is registered and dispatches to cmd_preopen_check.
  - cmd_preopen_check calls run_preopen_check() and prints
    severity/direction/headline + flagged/reforecast lists.
  - --ticker/--sector narrows the per-ticker contradiction check to a single
    (ticker, sector) pair; omitting them passes tickers=None (all managed).
  - skipped result (flag off) prints a [SKIP] message without raising.

Mirrors tests/unit/intelligence/rl/test_reforecast_cli.py. All
run_preopen_check() calls are mocked — no real Serper/LLM/network traffic
is possible from this test module.
"""

from __future__ import annotations

import argparse

from services.scheduler import run_schedule


def _ns(ticker=None, sector=None) -> argparse.Namespace:
    return argparse.Namespace(ticker=ticker, sector=sector)


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------

def test_preopen_check_subcommand_registered(monkeypatch):
    """main() parses `preopen-check --ticker X --sector Y` and dispatches to
    cmd_preopen_check with the parsed args."""
    import sys

    received = []
    monkeypatch.setattr(run_schedule, "cmd_preopen_check", lambda args: received.append(args))
    monkeypatch.setattr(sys, "argv", [
        "run_schedule.py", "preopen-check", "--ticker", "MARUTI", "--sector", "automobile",
    ])

    run_schedule.main()

    assert len(received) == 1
    args = received[0]
    assert args.ticker == "MARUTI"
    assert args.sector == "automobile"


def test_preopen_check_subcommand_optional_args_default_none(monkeypatch):
    import sys

    received = []
    monkeypatch.setattr(run_schedule, "cmd_preopen_check", lambda args: received.append(args))
    monkeypatch.setattr(sys, "argv", ["run_schedule.py", "preopen-check"])

    run_schedule.main()

    args = received[0]
    assert args.ticker is None
    assert args.sector is None


# ---------------------------------------------------------------------------
# cmd_preopen_check — happy path
# ---------------------------------------------------------------------------

def test_cmd_preopen_check_prints_severity_direction_headline(monkeypatch, capsys):
    calls = []

    def _fake_run_preopen_check(tickers=None):
        calls.append(tickers)
        return {
            "severity": 0.85, "direction": "risk_off",
            "flagged": ["MARUTI"], "reforecasts": ["MARUTI"],
            "headline": "Crude spikes 10% overnight",
        }

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.preopen_check.run_preopen_check",
        _fake_run_preopen_check,
    )

    run_schedule.cmd_preopen_check(_ns())

    assert calls == [None]
    out = capsys.readouterr().out
    assert "0.85" in out
    assert "risk_off" in out
    assert "Crude spikes 10% overnight" in out
    assert "MARUTI" in out


def test_cmd_preopen_check_with_ticker_and_sector_narrows_tickers(monkeypatch, capsys):
    calls = []

    def _fake_run_preopen_check(tickers=None):
        calls.append(tickers)
        return {
            "severity": 0.9, "direction": "risk_off",
            "flagged": [], "reforecasts": [], "headline": "Crisis",
        }

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.preopen_check.run_preopen_check",
        _fake_run_preopen_check,
    )

    run_schedule.cmd_preopen_check(_ns(ticker="maruti", sector="automobile"))

    assert calls == [[("MARUTI", "automobile")]]


def test_cmd_preopen_check_no_flagged_tickers(monkeypatch, capsys):
    def _fake_run_preopen_check(tickers=None):
        return {"severity": 0.2, "direction": "neutral", "flagged": [], "reforecasts": [], "headline": "Quiet night"}

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.preopen_check.run_preopen_check",
        _fake_run_preopen_check,
    )

    run_schedule.cmd_preopen_check(_ns())

    out = capsys.readouterr().out
    assert "No tickers flagged" in out


# ---------------------------------------------------------------------------
# cmd_preopen_check — flag-off / skipped
# ---------------------------------------------------------------------------

def test_cmd_preopen_check_skipped_prints_skip(monkeypatch, capsys):
    def _fake_run_preopen_check(tickers=None):
        return {"severity": 0.0, "direction": "neutral", "flagged": [], "reforecasts": [], "skipped": "disabled"}

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.preopen_check.run_preopen_check",
        _fake_run_preopen_check,
    )

    run_schedule.cmd_preopen_check(_ns())

    out = capsys.readouterr().out
    assert "[SKIP]" in out
