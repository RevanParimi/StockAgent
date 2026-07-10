# tests/unit/test_discovery_cycle_ipo.py
"""Compass Phase C — IPO stage merged into the weekly discovery cycle."""
from datetime import date
from unittest.mock import patch

from backend.shared.schemas.discovery import DiscoveryCandidate, ScreenResult
import core.discovery as disc


def _screen(n=3):
    return ScreenResult(
        screen_date="2026-07-04", universe_size=2000, shortlist_size=80,
        candidates=[DiscoveryCandidate(symbol=f"SCR{i}", close=100.0, composite=0.9 - i * 0.1)
                    for i in range(n)],
    )


def _ipo_cands(n=2):
    return [DiscoveryCandidate(symbol=f"IPO{i}", close=300.0,
                               composite=0.8 - i * 0.1, flags=["ipo"])
            for i in range(n)]


@patch.object(disc, "run_paper_reviews", return_value={"reviewed": [], "failed": [], "skipped": []})
@patch.object(disc, "run_deep_dives", return_value=[])
@patch.object(disc, "run_screen", return_value=_screen())
@patch.object(disc, "build_ipo_candidates", return_value=_ipo_cands())
@patch.object(disc, "refresh_ipo_cache", return_value={"degraded": False})
@patch.object(disc, "refresh_bulk_block", return_value={})
@patch.object(disc, "sync_recent", return_value={})
def test_ipo_candidates_prepended_within_budget(
        m_sync, m_bulk, m_ipo_refresh, m_ipo_build, m_screen, m_dives, m_paper, monkeypatch):
    monkeypatch.setattr(disc.settings, "DISCOVERY_IPO_ENABLED", True)
    monkeypatch.setattr(disc.settings, "DISCOVERY_IPO_MAX_DEEP_DIVES", 2)
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert result["ipo_candidates"] == 2
    passed = m_dives.call_args.args[0]
    assert [c.symbol for c in passed[:2]] == ["IPO0", "IPO1"]    # prepended
    assert [c.symbol for c in passed[2:]] == ["SCR0", "SCR1", "SCR2"]


@patch.object(disc, "run_paper_reviews", return_value={"reviewed": [], "failed": [], "skipped": []})
@patch.object(disc, "run_deep_dives", return_value=[])
@patch.object(disc, "run_screen", return_value=_screen())
@patch.object(disc, "build_ipo_candidates", side_effect=RuntimeError("boom"))
@patch.object(disc, "refresh_ipo_cache", side_effect=RuntimeError("boom"))
@patch.object(disc, "refresh_bulk_block", return_value={})
@patch.object(disc, "sync_recent", return_value={})
def test_ipo_stage_failure_is_non_fatal(
        m_sync, m_bulk, m_ipo_refresh, m_ipo_build, m_screen, m_dives, m_paper, monkeypatch):
    monkeypatch.setattr(disc.settings, "DISCOVERY_IPO_ENABLED", True)
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert result["ipo_candidates"] == 0
    assert any("ipo" in e for e in result["errors"])
    assert m_dives.called                                        # cycle continued


@patch.object(disc, "run_paper_reviews", return_value={"reviewed": [], "failed": [], "skipped": []})
@patch.object(disc, "run_deep_dives", return_value=[])
@patch.object(disc, "run_screen", return_value=_screen())
@patch.object(disc, "build_ipo_candidates", return_value=_ipo_cands())
@patch.object(disc, "refresh_ipo_cache", return_value={})
@patch.object(disc, "refresh_bulk_block", return_value={})
@patch.object(disc, "sync_recent", return_value={})
def test_ipo_stage_gated_off(
        m_sync, m_bulk, m_ipo_refresh, m_ipo_build, m_screen, m_dives, m_paper, monkeypatch):
    monkeypatch.setattr(disc.settings, "DISCOVERY_IPO_ENABLED", False)
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert result["ipo_candidates"] == 0
    assert not m_ipo_build.called
