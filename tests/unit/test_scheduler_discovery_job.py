"""Compass Phase B — run_discovery_cycle orchestration + scheduler job gating."""
from datetime import date

import pytest

import core.discovery as disc


def test_run_discovery_cycle_happy_path(monkeypatch):
    calls = []
    monkeypatch.setattr(disc, "sync_recent",
                        lambda days_back=7: calls.append("sync") or
                        {"synced": 1, "skipped": 4, "failed": [], "pruned": 0})
    monkeypatch.setattr(disc, "refresh_bulk_block",
                        lambda weeks=4: calls.append("bulk") or {"degraded": False, "deals": []})

    class _Screen:
        candidates = ["c1", "c2"]
        dark_signals = ["mf_holding"]
        universe_size = 1500
        def model_dump(self):
            return {}
    monkeypatch.setattr(disc, "run_screen", lambda on=None: calls.append("screen") or _Screen())
    monkeypatch.setattr(disc, "run_deep_dives",
                        lambda cands, on, max_n=None: calls.append("dives") or ["d1"])

    class _FakeShelf:
        def apply_deep_dives(self, dives, on):
            calls.append("shelf")
            return {"added": ["AAA"], "displaced": [], "skipped": []}
        def rotate_stale(self, on):
            return []
    monkeypatch.setattr(disc, "ShelfStore", _FakeShelf)
    monkeypatch.setattr(disc, "run_paper_reviews",
                        lambda on: calls.append("paper") or
                        {"reviewed": ["AAA"], "failed": [], "skipped": []})

    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert calls == ["sync", "bulk", "screen", "dives", "shelf", "paper"]
    assert result["shelf"]["added"] == ["AAA"]
    assert result["paper"]["reviewed"] == ["AAA"]
    assert result["dark_signals"] == ["mf_holding"]


def test_run_discovery_cycle_stage_failure_is_contained(monkeypatch):
    monkeypatch.setattr(disc, "sync_recent",
                        lambda days_back=7: (_ for _ in ()).throw(RuntimeError("NSE down")))
    monkeypatch.setattr(disc, "refresh_bulk_block", lambda weeks=4: {"degraded": True, "deals": []})

    class _Empty:
        candidates = []
        dark_signals = []
        universe_size = 0
        def model_dump(self):
            return {}
    monkeypatch.setattr(disc, "run_screen", lambda on=None: _Empty())
    monkeypatch.setattr(disc, "run_deep_dives", lambda cands, on, max_n=None: [])

    class _FakeShelf:
        def apply_deep_dives(self, dives, on):
            return {"added": [], "displaced": [], "skipped": []}
        def rotate_stale(self, on):
            return []
    monkeypatch.setattr(disc, "ShelfStore", _FakeShelf)
    monkeypatch.setattr(disc, "run_paper_reviews",
                        lambda on: {"reviewed": [], "failed": [], "skipped": []})

    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert "sync failed" in result["errors"][0]        # contained, cycle continued
    assert result["shelf"]["added"] == []
