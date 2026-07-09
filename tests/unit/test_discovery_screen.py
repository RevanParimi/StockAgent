"""Compass Phase B — composite screen orchestration + persistence."""
from datetime import date

import pandas as pd
import pytest

import core.discovery.screen as scr
from backend.shared.schemas.discovery import ScreenResult


@pytest.fixture
def patched(tmp_path, monkeypatch):
    """Screen with every collaborator faked: 3-symbol universe, 2 live signals,
    one guard rejection."""
    monkeypatch.setattr(scr.settings, "DISCOVERY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(scr.settings, "DISCOVERY_SHORTLIST_SIZE", 3)
    monkeypatch.setattr(scr.settings, "DISCOVERY_MAX_CANDIDATES", 2)

    win = pd.DataFrame([{"symbol": s, "series": "EQ", "date": "2026-07-03",
                         "prev_close": 99.0, "open": 99.0, "high": 101.0, "low": 98.0,
                         "close": 100.0, "volume": 1.0, "traded_value_cr": 6.0,
                         "delivery_qty": 1.0, "delivery_pct": 40.0}
                        for s in ("AAA", "BBB", "CCC")])

    class _FakeStore:
        def load_window(self, end, sessions):
            return win
        def latest_day(self):
            return date(2026, 7, 3)
    monkeypatch.setattr(scr, "EodStore", lambda: _FakeStore())
    monkeypatch.setattr(scr, "build_universe", lambda w: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(
        scr, "compute_signals",
        lambda w, u, c: {
            "momentum": pd.Series({"AAA": 3.0, "BBB": 2.0, "CCC": 1.0}),
            "delivery_surge": pd.Series({"AAA": 1.0, "BBB": 3.0, "CCC": 2.0}),
            "volume_breakout": None, "bulk_block": None,
            "high_52wk_rs": None, "insider_buying": None, "mf_holding": None,
        })
    monkeypatch.setattr(
        scr, "apply_guards",
        lambda shortlist, w: (
            [s for s in shortlist if s != "CCC"],
            {"CCC": ["low_liquidity"]},
            ["promoter_pledge"],
        ))
    monkeypatch.setattr(scr, "load_bulk_block", lambda: {"degraded": True, "deals": []})
    return tmp_path


def test_run_screen_ranks_guards_and_persists(patched):
    result = scr.run_screen(on=date(2026, 7, 4))
    assert isinstance(result, ScreenResult)
    assert result.universe_size == 3
    assert len(result.candidates) == 2
    # momentum weight 0.30 dominates delivery 0.15 -> AAA first
    assert result.candidates[0].symbol == "AAA"
    assert result.rejected == {"CCC": ["low_liquidity"]}
    assert set(result.dark_signals) == {"volume_breakout", "bulk_block",
                                        "high_52wk_rs", "insider_buying", "mf_holding"}
    assert "promoter_pledge" in result.degraded_checks
    assert (patched / "screens" / "2026-07-03_screen.json").exists()

    latest = scr.load_latest_screen()
    assert latest is not None and latest.screen_date == "2026-07-03"


def test_run_screen_empty_store(patched, monkeypatch):
    class _Empty:
        def load_window(self, end, sessions):
            return pd.DataFrame()
        def latest_day(self):
            return None
    monkeypatch.setattr(scr, "EodStore", lambda: _Empty())
    result = scr.run_screen(on=date(2026, 7, 4))
    assert result.universe_size == 0 and result.candidates == []
