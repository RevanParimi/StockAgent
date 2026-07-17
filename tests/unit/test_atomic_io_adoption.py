"""tests/unit/test_atomic_io_adoption.py — the AUD-057 sites write via atomic_io."""
import inspect


def _uses_atomic(func) -> bool:
    src = inspect.getsource(func)
    return "atomic_write_json" in src and ".write_text(" not in src


def test_api_usage_save_is_atomic():
    from services.data.stores import api_usage
    assert _uses_atomic(api_usage._save)


def test_nse_key_registry_save_is_atomic():
    from services.data.fetchers import nse_key_registry
    assert _uses_atomic(nse_key_registry._save_registry)


def test_ops_alerts_state_save_is_atomic():
    from core.delivery import ops_alerts
    assert _uses_atomic(ops_alerts._save_state)


def test_symbol_resolver_writers_are_atomic():
    from backend.shared.data.fetchers import symbol_resolver
    assert _uses_atomic(symbol_resolver._persist)
    assert _uses_atomic(symbol_resolver._remove_from_cache_file)
    assert _uses_atomic(symbol_resolver.learn_company_name)


def test_calendar_updater_write_is_atomic():
    from core.intelligence.rl import calendar_updater
    src = inspect.getsource(calendar_updater)
    assert "_HOLIDAY_FILE.write_text(" not in src
    assert "atomic_write_json" in src


def test_api_usage_roundtrip_still_works(tmp_path, monkeypatch):
    from services.data.stores import api_usage
    monkeypatch.setattr(api_usage, "_USAGE_FILE", tmp_path / "api_usage.json")
    api_usage.record_call("serper")
    usage = api_usage.get_usage()
    assert usage["serper"]["calls"] == 1
