"""PR-046: the chat's stock tool returns the theses behind a verdict change.

"Ask why" on a verdict card sends "Why did the analysis change X's verdict from
NEUTRAL to SELL …". The model answers from `get_stock_analysis`, which returned
only verdicts and scores; it now also returns the newest run's thesis and the
thesis of the last run with another verdict, each cut at a word.
"""
from __future__ import annotations

from services.api.routes import ui_data


class _Store:
    def __init__(self, rows):
        self.rows = rows

    def get_history(self, ticker, limit=30):
        return self.rows[:limit]

    def get_score_delta(self, ticker):
        return -0.01


def _row(day, verdict, score, thesis):
    return {"run_at": f"{day}T11:05:00", "verdict": verdict, "final_score": score,
            "investment_thesis": thesis}


def _detail(monkeypatch, rows):
    monkeypatch.setattr(ui_data, "_score_store", lambda: _Store(rows))
    return ui_data._ctx_ticker_detail("olaelec")


def test_the_newest_thesis_and_the_one_before_the_change(monkeypatch):
    rows = [_row("2026-11-20", "SELL", 0.41, "Demand is falling: registrations down 30%."),
            _row("2026-11-19", "NEUTRAL", 0.42, "Cheaper cells may offset a weak quarter."),
            _row("2026-11-18", "NEUTRAL", 0.44, "Older view.")]
    out = _detail(monkeypatch, rows)
    lines = out.splitlines()
    assert lines[0] == "OLAELEC HISTORY | Δscore=-0.010 vs prior:"
    assert "  2026-11-20: SELL score=0.41" in lines
    assert "LATEST THESIS (2026-11-20, SELL): Demand is falling: registrations down 30%." in lines
    # the last run with another verdict, not simply the oldest
    assert ("BEFORE THE VERDICT CHANGE THESIS (2026-11-19, NEUTRAL): "
            "Cheaper cells may offset a weak quarter.") in lines
    assert "Older view." not in out


def test_no_change_in_the_kept_runs_gives_the_latest_thesis_only(monkeypatch):
    rows = [_row("2026-11-20", "BUY", 0.61, "Order book covers two years."),
            _row("2026-11-19", "BUY", 0.60, "Same view.")]
    out = _detail(monkeypatch, rows)
    assert "LATEST THESIS (2026-11-20, BUY): Order book covers two years." in out
    assert "BEFORE THE VERDICT CHANGE" not in out and "Same view." not in out


def test_a_long_thesis_is_cut_at_a_word_and_marked(monkeypatch):
    long = "word " * 400                      # 2,000 characters
    out = _detail(monkeypatch, [_row("2026-11-20", "BUY", 0.6, long)])
    thesis = next(line for line in out.splitlines() if line.startswith("LATEST THESIS"))
    text = thesis.split("): ", 1)[1]
    assert text.endswith("word…")
    assert len(text) <= ui_data._TICKER_THESIS_CHARS + 1


def test_no_thesis_stored_adds_no_line_and_no_history_returns_nothing(monkeypatch):
    out = _detail(monkeypatch, [_row("2026-11-20", "BUY", 0.6, None)])
    assert "THESIS" not in out and out.startswith("OLAELEC HISTORY")
    assert _detail(monkeypatch, []) == ""
