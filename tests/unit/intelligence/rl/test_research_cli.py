"""
`research` CLI subcommand (RL Phase 4, spec section 5).

`python -m services.scheduler.run_schedule research [--ticker T ...]` mirrors
`ingest-events`: all managed tickers with dossiers, or a narrowed set. Each is
researched via QuestionResearcher().run(ticker, sector); an ASCII-only summary
line is printed per ticker (Windows cp1252 console — no rupee/arrow glyphs).

All QuestionResearcher.run calls are mocked — no Serper/Tavily/LLM/network
traffic is possible from this test module.
"""
from __future__ import annotations

import argparse

from services.scheduler import run_schedule


def _ns(ticker=None) -> argparse.Namespace:
    return argparse.Namespace(ticker=ticker)


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------

def test_research_subcommand_registered(monkeypatch):
    import sys

    received = []
    monkeypatch.setattr(run_schedule, "cmd_research", lambda args: received.append(args))
    monkeypatch.setattr(sys, "argv", ["run_schedule.py", "research", "--ticker", "MARUTI"])

    run_schedule.main()

    assert len(received) == 1
    assert received[0].ticker == ["MARUTI"]


def test_research_subcommand_optional_ticker_default_none(monkeypatch):
    import sys

    received = []
    monkeypatch.setattr(run_schedule, "cmd_research", lambda args: received.append(args))
    monkeypatch.setattr(sys, "argv", ["run_schedule.py", "research"])

    run_schedule.main()

    assert received[0].ticker is None


# ---------------------------------------------------------------------------
# cmd_research
# ---------------------------------------------------------------------------

def _patch_tickers(monkeypatch, rows):
    monkeypatch.setattr(
        "services.api.log_buffer.get_active_tickers_with_sector", lambda: rows)


def test_cmd_research_runs_each_ticker_and_prints_ascii_summary(monkeypatch, capsys):
    _patch_tickers(monkeypatch, [
        {"sym": "MARUTI", "sector": "automobile"},
        {"sym": "TVSMOTOR", "sector": "automobile"},
    ])

    calls = []

    def fake_run(self, ticker, sector):
        calls.append((ticker, sector))
        return {"selected": 2, "answered": 1, "partial": 1, "expired": 0}

    monkeypatch.setattr(
        "core.intelligence.rl.agents.question_researcher.QuestionResearcher.run",
        fake_run)

    run_schedule.cmd_research(_ns())

    assert calls == [("MARUTI", "automobile"), ("TVSMOTOR", "automobile")]
    out = capsys.readouterr().out
    assert "MARUTI" in out
    assert out.isascii()                     # cp1252 console safety


def test_cmd_research_narrows_to_requested_ticker(monkeypatch, capsys):
    _patch_tickers(monkeypatch, [
        {"sym": "MARUTI", "sector": "automobile"},
        {"sym": "TVSMOTOR", "sector": "automobile"},
    ])

    calls = []

    def fake_run(self, ticker, sector):
        calls.append(ticker)
        return {"selected": 0, "answered": 0, "partial": 0, "expired": 0}

    monkeypatch.setattr(
        "core.intelligence.rl.agents.question_researcher.QuestionResearcher.run",
        fake_run)

    run_schedule.cmd_research(_ns(ticker=["maruti"]))   # case-insensitive

    assert calls == ["MARUTI"]


def test_cmd_research_non_fatal_when_one_ticker_raises(monkeypatch, capsys):
    _patch_tickers(monkeypatch, [
        {"sym": "MARUTI", "sector": "automobile"},
        {"sym": "TVSMOTOR", "sector": "automobile"},
    ])

    calls = []

    def fake_run(self, ticker, sector):
        calls.append(ticker)
        if ticker == "MARUTI":
            raise RuntimeError("boom")
        return {"selected": 1, "answered": 0, "partial": 0, "expired": 1}

    monkeypatch.setattr(
        "core.intelligence.rl.agents.question_researcher.QuestionResearcher.run",
        fake_run)

    run_schedule.cmd_research(_ns())          # must not raise

    assert calls == ["MARUTI", "TVSMOTOR"]
    out = capsys.readouterr().out
    assert "TVSMOTOR" in out
