"""Audit Wave 1 (AUD-040) — sector-toggles path resolution."""
import importlib
import json


def test_toggles_load_from_env_path(tmp_path, monkeypatch):
    toggles = tmp_path / "sector_toggles.json"
    toggles.write_text(json.dumps({
        "automobile":   {"enabled": True,  "tier": "backend"},
        "banking_bfsi": {"enabled": False, "tier": "backend"},
        "_comment":     "underscore keys are metadata",
    }), encoding="utf-8")
    monkeypatch.setenv("SECTOR_TOGGLES_PATH", str(toggles))

    import backend.sectors.registry as registry
    importlib.reload(registry)
    try:
        assert registry.SectorRegistry.is_enabled("automobile") is True
        assert registry.SectorRegistry.is_enabled("banking_bfsi") is False
        assert "_comment" not in registry._TOGGLES
    finally:
        monkeypatch.delenv("SECTOR_TOGGLES_PATH")
        importlib.reload(registry)      # restore real toggle state for other tests


def test_toggles_default_path_is_cwd_relative():
    """AUD-040: the default must not depend on __file__ depth (repo vs image
    layouts differ) — CWD-relative works in both."""
    import backend.sectors.registry as registry
    assert not str(registry._TOGGLES_PATH).startswith("/config"), \
        "absolute /config path = the AUD-040 prod bug"
    assert registry._TOGGLES_PATH.as_posix().endswith("config/sector_toggles.json")
