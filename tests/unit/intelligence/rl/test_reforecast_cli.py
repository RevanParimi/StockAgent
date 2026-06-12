"""
tests/unit/intelligence/rl/test_reforecast_cli.py
====================================================
Living Envelope (RL Phase 2.5), Component 3 — `reforecast` CLI subcommand.

Covers:
  - `python -m services.scheduler.run_schedule reforecast --ticker X
    [--sector Y] [--reason TEXT]` is registered and dispatches to
    cmd_reforecast.
  - cmd_reforecast calls regenerate_envelope(ticker, sector, reason,
    trigger="manual") and prints the archived file path, new
    reforecast_count, and the first 3 remaining-day predicted closes.
  - Sector defaults: explicit --sector wins; otherwise looked up from
    get_active_tickers_with_sector(), falling back to "automobile".
  - regenerate_envelope() returning None (flag off / cap / no remaining
    days / pipeline failure) prints a [SKIP] message without raising.
"""

from __future__ import annotations

import argparse
from datetime import date

import pytest

from core.schemas.feedback import DailyForecast, PredictionEnvelope, ReforecastEvent
from services.scheduler import run_schedule


def _ns(ticker="MARUTI", sector=None, reason=None) -> argparse.Namespace:
    return argparse.Namespace(ticker=ticker, sector=sector, reason=reason)


def _regenerated_envelope() -> PredictionEnvelope:
    today_str = date.today().isoformat()
    return PredictionEnvelope(
        ticker="MARUTI", sector="automobile", cycle_id="MARUTI_2026-06",
        generated_at="2026-06-01T00:00:00", base_close=1000.0,
        reforecast_count=1,
        reforecast_history=[
            ReforecastEvent(
                date=today_str, reason="Manual re-forecast requested for MARUTI via CLI.",
                trigger="manual",
                archived_file="data/predictions/automobile/MARUTI/archived_envelopes/2026-06_v1.json",
            ),
        ],
        daily_forecasts=[
            DailyForecast(day=1, date="2099-01-01", predicted_close=1010.0,
                          predicted_verdict="BUY", confidence=0.6),
            DailyForecast(day=2, date="2099-01-02", predicted_close=1015.0,
                          predicted_verdict="BUY", confidence=0.6),
            DailyForecast(day=3, date="2099-01-03", predicted_close=1020.0,
                          predicted_verdict="BUY", confidence=0.6),
            DailyForecast(day=4, date="2099-01-04", predicted_close=1025.0,
                          predicted_verdict="BUY", confidence=0.6),
        ],
    )


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------

def test_reforecast_subcommand_registered(monkeypatch):
    """main() parses `reforecast --ticker X --sector Y --reason Z` and
    dispatches to cmd_reforecast with the parsed args."""
    import sys

    received = []
    monkeypatch.setattr(run_schedule, "cmd_reforecast", lambda args: received.append(args))
    monkeypatch.setattr(sys, "argv", [
        "run_schedule.py", "reforecast", "--ticker", "MARUTI",
        "--sector", "automobile", "--reason", "test reason",
    ])

    run_schedule.main()

    assert len(received) == 1
    args = received[0]
    assert args.ticker == "MARUTI"
    assert args.sector == "automobile"
    assert args.reason == "test reason"


def test_reforecast_subcommand_optional_args_default_none(monkeypatch):
    import sys

    received = []
    monkeypatch.setattr(run_schedule, "cmd_reforecast", lambda args: received.append(args))
    monkeypatch.setattr(sys, "argv", ["run_schedule.py", "reforecast", "--ticker", "MARUTI"])

    run_schedule.main()

    args = received[0]
    assert args.ticker == "MARUTI"
    assert args.sector is None
    assert args.reason is None


# ---------------------------------------------------------------------------
# cmd_reforecast — happy path
# ---------------------------------------------------------------------------

def test_cmd_reforecast_calls_regenerate_with_manual_trigger(monkeypatch, capsys):
    calls = []

    def _fake_regenerate(**kwargs):
        calls.append(kwargs)
        return _regenerated_envelope()

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.generate_forecast.regenerate_envelope",
        _fake_regenerate,
    )
    monkeypatch.setattr(
        "services.api.log_buffer.get_active_tickers_with_sector",
        lambda: [{"sym": "MARUTI", "sector": "automobile"}],
    )

    run_schedule.cmd_reforecast(_ns(ticker="maruti"))

    assert len(calls) == 1
    assert calls[0]["ticker"] == "MARUTI"
    assert calls[0]["sector"] == "automobile"
    assert calls[0]["trigger"] == "manual"
    assert "Manual re-forecast" in calls[0]["reason"]

    out = capsys.readouterr().out
    assert "MARUTI" in out
    assert "archived_envelopes" in out
    assert "reforecast_count: 1" in out
    # First 3 remaining-day predicted closes printed.
    assert "2099-01-01" in out
    assert "2099-01-02" in out
    assert "2099-01-03" in out
    assert "2099-01-04" not in out


def test_cmd_reforecast_explicit_sector_overrides_lookup(monkeypatch, capsys):
    calls = []

    def _fake_regenerate(**kwargs):
        calls.append(kwargs)
        return _regenerated_envelope()

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.generate_forecast.regenerate_envelope",
        _fake_regenerate,
    )
    # Lookup would return a different sector — explicit --sector must win.
    monkeypatch.setattr(
        "services.api.log_buffer.get_active_tickers_with_sector",
        lambda: [{"sym": "MARUTI", "sector": "it_sector"}],
    )

    run_schedule.cmd_reforecast(_ns(ticker="MARUTI", sector="automobile", reason="custom reason"))

    assert calls[0]["sector"] == "automobile"
    assert calls[0]["reason"] == "custom reason"


def test_cmd_reforecast_unknown_ticker_falls_back_to_automobile(monkeypatch, capsys):
    calls = []

    def _fake_regenerate(**kwargs):
        calls.append(kwargs)
        return _regenerated_envelope()

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.generate_forecast.regenerate_envelope",
        _fake_regenerate,
    )
    monkeypatch.setattr(
        "services.api.log_buffer.get_active_tickers_with_sector",
        lambda: [],
    )

    run_schedule.cmd_reforecast(_ns(ticker="UNKNOWNTICK"))

    assert calls[0]["sector"] == "automobile"


# ---------------------------------------------------------------------------
# cmd_reforecast — regenerate_envelope() returns None
# ---------------------------------------------------------------------------

def test_cmd_reforecast_none_result_prints_skip(monkeypatch, capsys):
    monkeypatch.setattr(
        "core.intelligence.rl.workflows.generate_forecast.regenerate_envelope",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "services.api.log_buffer.get_active_tickers_with_sector",
        lambda: [{"sym": "MARUTI", "sector": "automobile"}],
    )

    run_schedule.cmd_reforecast(_ns(ticker="MARUTI"))

    out = capsys.readouterr().out
    assert "[SKIP]" in out
