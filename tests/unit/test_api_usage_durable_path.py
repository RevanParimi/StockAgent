"""
tests/unit/test_api_usage_durable_path.py
==========================================
F4 — the monthly Serper/Tavily counter must live on the persistent volume.

Prod evidence (2026-07-31, railway ssh): /app/logs/api_usage.json read
`{"month": "2026-07", "serper": {"calls": 1}}` after a month of hundreds of
real calls — logs/ is ephemeral container storage, so every redeploy (near
daily) wiped the counter and the monthly quota reading was fiction. Only
/app/data is volume-backed, so the default location moves under data/.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from unittest import mock

import services.data.stores.api_usage as au


def _reload_with_env(env: dict[str, str]):
    """Re-execute api_usage's module body under an exact LOGS_DIR environment."""
    clean = {k: v for k, v in os.environ.items() if k != "LOGS_DIR"}
    clean.update(env)
    with mock.patch.dict(os.environ, clean, clear=True):
        return importlib.reload(au)


def test_usage_counter_defaults_under_data_volume(tmp_path, monkeypatch):
    """With LOGS_DIR unset, record_call() must write under data/logs — the
    Railway volume mount — not the ephemeral logs/ directory."""
    monkeypatch.chdir(tmp_path)
    try:
        mod = _reload_with_env({})
        mod.record_call("serper")

        assert (tmp_path / "data" / "logs" / "api_usage.json").exists()
        assert not (tmp_path / "logs").exists()
    finally:
        importlib.reload(au)


def test_run_events_log_defaults_under_data_volume(tmp_path, monkeypatch):
    """The per-run JSONL event log follows the counter onto the volume."""
    monkeypatch.chdir(tmp_path)
    try:
        mod = _reload_with_env({})
        mod.log_run_api_usage(run_id="r1", ticker="MARUTI", before={})

        assert (tmp_path / "data" / "logs" / "api_usage_events.jsonl").exists()
        assert not (tmp_path / "logs").exists()
    finally:
        importlib.reload(au)


def test_logs_dir_env_override_still_wins(tmp_path):
    """Explicit LOGS_DIR keeps overriding the default (local dev / tests)."""
    try:
        mod = _reload_with_env({"LOGS_DIR": str(tmp_path / "custom")})

        assert mod._USAGE_FILE == tmp_path / "custom" / "api_usage.json"
        assert mod._EVENTS_FILE == tmp_path / "custom" / "api_usage_events.jsonl"
    finally:
        importlib.reload(au)


def test_existing_counter_on_volume_is_read_not_reset(tmp_path, monkeypatch):
    """A counter already on the volume survives — record_call increments it
    instead of starting a fresh month (the redeploy-reset symptom)."""
    monkeypatch.chdir(tmp_path)
    try:
        mod = _reload_with_env({})
        month = mod._current_month()
        usage_file = tmp_path / "data" / "logs" / "api_usage.json"
        usage_file.parent.mkdir(parents=True, exist_ok=True)
        usage_file.write_text(
            '{"month": "%s", "serper": {"calls": 640}}' % month, encoding="utf-8"
        )

        mod.record_call("serper")

        assert mod.get_usage()["serper"]["calls"] == 641
    finally:
        importlib.reload(au)


def test_usage_file_path_is_relative_so_prod_resolves_to_app_data(tmp_path):
    """Guards the prod mapping: cwd on Railway is /app, so the default path
    must stay relative — an absolute default would miss the volume."""
    try:
        mod = _reload_with_env({})
        assert not Path(mod._USAGE_FILE).is_absolute()
        assert Path(mod._USAGE_FILE).parts[:2] == ("data", "logs")
    finally:
        importlib.reload(au)
