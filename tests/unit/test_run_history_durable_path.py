"""
tests/unit/test_run_history_durable_path.py
============================================
Three Loops PI — task B1: run history must survive a redeploy.

Prod evidence (2026-08-24, spec §2.3): `run_summaries.jsonl` held **13 rows**
after 53 days of live traffic. `run_logger` and `analysis_logger` default
`LOGS_DIR` to the ephemeral `logs/`, while `api_usage` (fixed by F4) defaults
to the volume-backed `data/logs/`. Same env var, two different defaults — so
every redeploy silently wiped the run history while the API counter survived.

These tests pin the *default*, not the override: `LOGS_DIR` set explicitly
must keep winning for local dev and tests.
"""
from __future__ import annotations

import importlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import services.data.stores.analysis_logger as al
import services.data.stores.run_logger as rl

REPO_ROOT = Path(__file__).resolve().parents[2]


def _reload_with_env(module, env: dict[str, str]):
    """Re-execute a module body under an exact LOGS_DIR environment."""
    clean = {k: v for k, v in os.environ.items() if k != "LOGS_DIR"}
    clean.update(env)
    with mock.patch.dict(os.environ, clean, clear=True):
        return importlib.reload(module)


def _run_summary(mod) -> None:
    mod.log_run_summary(
        run_id="r1",
        ticker="MARUTI",
        company_name="Maruti Suzuki",
        started_at=datetime.now(timezone.utc),
        duration_seconds=12.5,
        final_score=0.61,
        verdict="BUY",
        total_prompt_tokens=100,
        total_completion_tokens=20,
        total_cost_usd=0.001,
        agent_scores={"technical": 0.5},
        errors=[],
    )


# ── run_logger ────────────────────────────────────────────────────────────

def test_run_summaries_log_defaults_under_data_volume(tmp_path, monkeypatch):
    """The file whose prod copy held 13 rows must land on the Railway volume."""
    monkeypatch.chdir(tmp_path)
    try:
        mod = _reload_with_env(rl, {})
        _run_summary(mod)

        assert (tmp_path / "data" / "logs" / "run_summaries.jsonl").exists()
        assert not (tmp_path / "logs").exists()
    finally:
        importlib.reload(rl)


def test_agent_calls_log_defaults_under_data_volume(tmp_path, monkeypatch):
    """The per-LLM-call log follows the run summaries onto the volume."""
    monkeypatch.chdir(tmp_path)
    try:
        mod = _reload_with_env(rl, {})
        mod.log_llm_call(
            run_id="r1", ticker="MARUTI", phase="agent", agent_name="technical",
            model="qwen/qwen3.6-flash", prompt_tokens=10, completion_tokens=2,
            duration_ms=100.0, cost_usd=0.0001,
        )

        assert (tmp_path / "data" / "logs" / "agent_calls.jsonl").exists()
        assert not (tmp_path / "logs").exists()
    finally:
        importlib.reload(rl)


def test_run_logger_env_override_still_wins(tmp_path):
    """Explicit LOGS_DIR keeps overriding the default (local dev / tests)."""
    try:
        mod = _reload_with_env(rl, {"LOGS_DIR": str(tmp_path / "custom")})

        assert mod.RUN_SUMMARIES_LOG == tmp_path / "custom" / "run_summaries.jsonl"
        assert mod.AGENT_CALLS_LOG == tmp_path / "custom" / "agent_calls.jsonl"
    finally:
        importlib.reload(rl)


def test_run_logger_default_stays_relative_so_prod_resolves_to_app_data():
    """Guards the prod mapping: cwd on Railway is /app, so the default must
    stay relative — an absolute default would miss the volume mount."""
    try:
        mod = _reload_with_env(rl, {})
        assert not mod.RUN_SUMMARIES_LOG.is_absolute()
        assert mod.RUN_SUMMARIES_LOG.parts[:2] == ("data", "logs")
    finally:
        importlib.reload(rl)


# ── analysis_logger ───────────────────────────────────────────────────────

def test_analysis_logs_default_under_data_volume(tmp_path):
    """`analysis_rich.jsonl` is the UI's history — same ephemeral default,
    same fix. It also read LOGS_DIR off `settings.__dict__`, where the key
    never existed, so the env var could not override it at all."""
    try:
        mod = _reload_with_env(al, {})

        assert mod.RICH_LOG == Path("data") / "logs" / "analysis_rich.jsonl"
        assert mod.READABLE_LOG == Path("data") / "logs" / "analysis_readable.log"
    finally:
        importlib.reload(al)


def test_analysis_logger_env_override_still_wins(tmp_path):
    try:
        mod = _reload_with_env(al, {"LOGS_DIR": str(tmp_path / "custom")})

        assert mod.RICH_LOG == tmp_path / "custom" / "analysis_rich.jsonl"
    finally:
        importlib.reload(al)


# ── the rule itself ───────────────────────────────────────────────────────

_LOGS_DIR_DEFAULT = re.compile(r"""LOGS_DIR["']\s*,\s*["']([^"']+)["']""")
_SOURCE_ROOTS = ("core", "services", "src", "scripts")


def test_every_logs_dir_default_in_the_repo_is_the_volume():
    """Acceptance: one default for one env var. A future consumer that
    re-introduces `logs/` fails here instead of losing history for 53 days."""
    offenders: list[str] = []
    found = 0
    for root in _SOURCE_ROOTS:
        for path in (REPO_ROOT / root).rglob("*.py"):
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                for default in _LOGS_DIR_DEFAULT.findall(line):
                    found += 1
                    if default != "data/logs":
                        rel = path.relative_to(REPO_ROOT).as_posix()
                        offenders.append(f"{rel}:{lineno} -> {default!r}")

    assert not offenders, "LOGS_DIR defaults off the volume: " + ", ".join(offenders)
    assert found >= 3, f"expected the known LOGS_DIR consumers, found {found}"
