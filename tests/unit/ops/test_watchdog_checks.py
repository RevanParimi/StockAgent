"""Watchdog checks — registration, failure containment, Atlas pre-flight."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from core.ops.watchdog import checks as C


def test_run_check_unknown_name_is_unknown_state():
    r = C.run_check("no_such_check")
    assert r.state == "unknown" and "not registered" in r.detail


def test_run_check_swallows_exception_as_unknown():
    @C.check("boom_for_test")
    def _boom():
        raise RuntimeError("kaboom")
    try:
        r = C.run_check("boom_for_test")
        assert r.state == "unknown"
        assert "kaboom" in r.detail
    finally:
        C.CHECKS.pop("boom_for_test", None)


def test_duplicate_check_name_rejected():
    @C.check("dupe_for_test")
    def _a():
        return C.CheckResult("satisfied", "ok")
    try:
        with pytest.raises(ValueError, match="already registered"):
            @C.check("dupe_for_test")
            def _b():
                return C.CheckResult("satisfied", "ok")
    finally:
        C.CHECKS.pop("dupe_for_test", None)


class TestAtlasCutoverPending:
    def test_satisfied_when_flag_set(self, monkeypatch):
        monkeypatch.setenv("ATLAS_ENABLED", "true")
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "satisfied"

    def test_satisfied_when_config_yaml_flipped_and_env_unset(self, monkeypatch, tmp_path):
        """The documented cutover is `atlas.enabled: true` in config.yaml, and
        prod does NOT set ATLAS_ENABLED — the code itself resolves the flag as
        cfg("atlas.enabled", env=...), so yaml is what is actually in force.
        A check that reads only the env var therefore reports a correctly
        completed cutover as still pending, forever."""
        import backend.shared.config.settings.loader as loader_mod
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
        monkeypatch.setitem(loader_mod._YAML["atlas"], "enabled", True)
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "satisfied"
        assert r.evidence["atlas_enabled"] is True

    def test_flipped_yaml_wins_over_a_dirty_preflight(self, monkeypatch, tmp_path):
        """Post-cutover the ETL has necessarily created atlas.db, so the
        resolved flag must be consulted BEFORE the pre-flight — otherwise the
        finished cutover reads as 'pre-flight DIRTY, investigate'."""
        import backend.shared.config.settings.loader as loader_mod
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
        monkeypatch.setitem(loader_mod._YAML["atlas"], "enabled", True)
        (tmp_path / "atlas.db").write_text("x")
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "satisfied"

    def test_pending_when_flag_unset_and_preflight_clean(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
        (tmp_path / "portfolio").mkdir()
        (tmp_path / "portfolio" / "primary").mkdir()
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "pending"
        assert r.evidence["atlas_db_present"] is False

    def test_blocked_when_atlas_db_already_exists(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
        (tmp_path / "portfolio").mkdir()
        (tmp_path / "portfolio" / "primary").mkdir()
        (tmp_path / "atlas.db").write_text("x")
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "blocked"
        assert "atlas.db" in r.detail

    def test_blocked_when_extra_portfolio_dirs(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
        (tmp_path / "portfolio").mkdir()
        (tmp_path / "portfolio" / "primary").mkdir()
        (tmp_path / "portfolio" / "u_other").mkdir()
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "blocked"
        assert "u_other" in r.detail


def _write_ipo_cache(tmp_path, hours_old: float):
    (tmp_path / "market_cache").mkdir(parents=True, exist_ok=True)
    stamp = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()
    (tmp_path / "market_cache" / "ipo.json").write_text(
        json.dumps({"fetched_at": stamp, "degraded": False,
                    "current": [], "upcoming": [], "past": []}),
        encoding="utf-8")


def test_ipo_cache_fresh_satisfied(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    _write_ipo_cache(tmp_path, hours_old=3)
    assert C.run_check("ipo_cache_fresh").state == "satisfied"


def test_ipo_cache_stale_is_pending(tmp_path, monkeypatch):
    """A stale cache means the twice-daily refresh job is dead — exactly the
    class of silent failure the watchdog exists to catch."""
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    _write_ipo_cache(tmp_path, hours_old=72)
    result = C.run_check("ipo_cache_fresh")
    assert result.state == "pending"
    assert "stale" in result.detail.lower()


def test_ipo_cache_absent_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    assert C.run_check("ipo_cache_fresh").state == "pending"
