"""SA-005: the suite's hermetic boundary (tests/hermetic.py).

Invariants, each checked against something the boundary did not compute:
- outbound transports are refused: raw sockets, DNS, requests, httpx, SMTP
  and curl_cffi (yfinance's transport, which does its own DNS in C);
- a refusal the application swallows still fails the test that caused it;
- the checkout's data/, logs/ and outputs/ are unreachable, and nothing else
  in the checkout is writable;
- each test runs in an empty working directory holding only the tracked
  files the application reads by relative path;
- settings see config.yaml and the checked-in fallbacks, whatever a .env or
  the shell holds.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests import hermetic

REPO = hermetic.REPO
HOSTILE_ENV = {
    "OPENROUTER_API_KEY": "sk-hostile-shell",
    "RL_LEARNING_MODE": "observe",
    "DELIVERY_EMAIL_TO": "someone@example.invalid",
    "AUTH_REQUIRED": "true",
}
HOSTILE_DOTENV = "RL_LEARNING_MODE=observe\nDECISION_GATE_MODE=enforce\nSERPER_API_KEY=sk-hostile-dotenv\n"


def _child_env() -> dict:
    keep = {k: v for k, v in os.environ.items()
            if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC",
                             "PATHEXT", "LOCALAPPDATA", "APPDATA", "HOME", "USERPROFILE"}}
    return {**keep, **HOSTILE_ENV, "PYTHONPATH": os.pathsep.join([str(REPO), str(REPO / "src")]),
            "PYTHONUTF8": "1"}


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("attempt, target", [
    (lambda: socket.create_connection(("api.example.com", 443), timeout=1), "api.example.com:443"),
    (lambda: socket.socket().connect(("203.0.113.10", 443)), "203.0.113.10:443"),
    (lambda: socket.getaddrinfo("openrouter.ai", 443), "openrouter.ai:443"),
])
def test_raw_sockets_and_dns_are_refused(attempt, target):
    with hermetic.expect_blocked() as caught:
        with pytest.raises(hermetic.OutboundNetworkBlocked):
            attempt()
    assert [a[1] for a in caught.attempts] == [target]


def test_http_clients_and_smtp_are_refused():
    import httpx
    import requests
    import smtplib

    with hermetic.expect_blocked() as caught:
        with pytest.raises(requests.ConnectionError):
            requests.get("https://google.serper.dev/search", timeout=1)
        with pytest.raises(httpx.ConnectError):
            httpx.get("https://openrouter.ai/api/v1/models", timeout=1)
        with pytest.raises(hermetic.OutboundNetworkBlocked):
            smtplib.SMTP("smtp.example.com", 587, timeout=1)
    hosts = {a[1].split(":")[0] for a in caught.attempts}
    assert {"google.serper.dev", "openrouter.ai", "smtp.example.com"} <= hosts


def test_curl_cffi_which_bypasses_python_sockets_is_refused():
    curl_requests = pytest.importorskip("curl_cffi.requests")
    with hermetic.expect_blocked() as caught:
        with pytest.raises(hermetic.OutboundNetworkBlocked):
            curl_requests.Session().get("https://query1.finance.yahoo.com/v8/finance/chart/MARUTI.NS")
    assert caught.attempts and "query1.finance.yahoo.com" in caught.attempts[0][1]


def test_loopback_stays_open():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        client = socket.create_connection(listener.getsockname(), timeout=2)
        server, _ = listener.accept()
        client.sendall(b"ok")
        assert server.recv(2) == b"ok"
        client.close()
        server.close()
    finally:
        listener.close()
    assert asyncio.run(asyncio.sleep(0, result="loop")) == "loop"


# ---------------------------------------------------------------------------
# Checkout guard and working directory
# ---------------------------------------------------------------------------

def test_checkout_runtime_dirs_are_unreachable_even_for_tracked_files():
    with hermetic.expect_blocked() as caught:
        with pytest.raises(hermetic.CheckoutAccessBlocked):
            (REPO / "data" / "nse" / "key_registry.json").read_bytes()      # tracked, still refused
        with pytest.raises(hermetic.CheckoutAccessBlocked):
            (REPO / "outputs" / "sa005-probe.json").write_text("{}")
        with pytest.raises(hermetic.CheckoutAccessBlocked):
            sqlite3.connect(str(REPO / "data" / "sa005-probe.db"))
        with pytest.raises(hermetic.CheckoutAccessBlocked):
            os.mkdir(REPO / "logs" / "sa005-probe")
    assert [v[1:3] for v in caught.violations] == [
        ("read", "data/nse/key_registry.json"),
        ("write", "outputs/sa005-probe.json"),
        ("sqlite3.connect", "data/sa005-probe.db"),
        ("os.mkdir", "logs/sa005-probe"),
    ]
    assert not (REPO / "data" / "sa005-probe.db").exists()


def test_the_rest_of_the_checkout_is_readable_but_not_writable(tmp_path):
    assert "StockAgent" in (REPO / "README.md").read_text(encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1", encoding="utf-8")
    with hermetic.expect_blocked() as caught:
        with pytest.raises(hermetic.CheckoutAccessBlocked):
            (REPO / "README.md").open("a")
        with pytest.raises(hermetic.CheckoutAccessBlocked):
            os.replace(outside, REPO / "src" / "sa005_moved.py")
    assert [v[1:3] for v in caught.violations] == [
        ("write", "README.md"), ("os.rename", "src/sa005_moved.py")]
    assert outside.exists() and not (REPO / "src" / "sa005_moved.py").exists()


def test_each_test_runs_in_an_empty_seeded_sandbox():
    cwd = Path.cwd()
    assert not str(cwd.resolve()).lower().startswith(str(REPO).lower())
    found = sorted(p.relative_to(cwd).as_posix() for p in cwd.rglob("*") if p.is_file())
    assert found == sorted(hermetic.SEEDED)
    for rel in hermetic.SEEDED:
        assert (cwd / rel).read_bytes() == hermetic._SEED_BYTES[rel]
    Path("data/logs").mkdir(parents=True)
    Path("data/logs/api_usage.json").write_text("{}", encoding="utf-8")   # relative: sandbox


def test_a_previous_tests_relative_writes_are_gone():
    """Runs after the test above (file order): its data/logs file is not here."""
    assert not Path("data/logs/api_usage.json").exists()


def test_seeded_files_are_every_tracked_file_the_app_reads_by_relative_path():
    tracked = set(subprocess.run(["git", "ls-files", "config", "data"], cwd=REPO, check=True,
                                 capture_output=True, text=True).stdout.split())
    assert set(hermetic.SEEDED) <= tracked
    source = "\n".join(p.read_text(encoding="utf-8-sig", errors="replace")
                       for d in ("core", "services", "src") for p in (REPO / d).rglob("*.py"))
    read_by_relative_path = {f for f in tracked if f'"{f}"' in source or f"'{f}'" in source}
    assert read_by_relative_path <= set(hermetic.SEEDED)
    assert {f for f in tracked if f.startswith("data/")} <= set(hermetic.SEEDED)


def test_api_worker_app_starts_no_background_work(api_worker_app, monkeypatch):
    """Booted as the singleton owner, the app starts the scheduler and an RL
    self-heal thread that, after a 10-second sleep, rebuilds every missing
    envelope: LLM and market calls that land in whichever test runs next."""
    import threading
    from fastapi.testclient import TestClient
    from services.api import server

    monkeypatch.setattr(server, "_scheduler_instance", None)
    monkeypatch.setattr(server, "_singleton_lock_socket", None)
    before = {t.ident for t in threading.enumerate()}
    with TestClient(api_worker_app):
        started = [t.name for t in threading.enumerate() if t.ident not in before]
    assert "rl-self-heal" not in started
    assert server._scheduler_instance is None and server._singleton_lock_socket is None


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def test_every_environment_variable_the_app_reads_is_removed():
    read = set()
    for d in ("core", "services", "src"):
        for p in (REPO / d).rglob("*.py"):
            read |= set(hermetic.ENV_READ.findall(p.read_text(encoding="utf-8-sig", errors="replace")))
    read |= set(hermetic.ENV_READ.findall((REPO / "main.py").read_text(encoding="utf-8-sig")))
    missing = read - hermetic.app_env_names()
    assert not missing, f"add to tests/hermetic.py EXTRA_APP_ENV: {sorted(missing)}"
    assert not (hermetic.app_env_names() & set(os.environ))
    assert os.environ.get("PYTHON_DOTENV_DISABLED") == "1"


def test_settings_ignore_a_hostile_dotenv_and_shell(tmp_path):
    """A child process sees a hostile .env (cwd) and shell. Without the boundary
    they reach settings (control); with it, settings match config.yaml."""
    import yaml
    shipped = yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
    (tmp_path / ".env").write_text(HOSTILE_DOTENV, encoding="utf-8")
    probe = ("import json; from core.config import settings as s; print(json.dumps("
             "{k: getattr(s, k) for k in ('RL_LEARNING_MODE', 'DECISION_GATE_MODE', "
             "'SERPER_API_KEY', 'OPENROUTER_API_KEY', 'AUTH_REQUIRED')}))")

    control = subprocess.run([sys.executable, "-c", probe], cwd=tmp_path, env=_child_env(),
                             capture_output=True, text=True, timeout=120)
    assert control.returncode == 0, control.stderr[-2000:]
    leaked = json.loads(control.stdout.strip().splitlines()[-1])
    assert leaked["DECISION_GATE_MODE"] == "enforce"          # from the .env
    assert leaked["SERPER_API_KEY"] == "sk-hostile-dotenv"     # from the .env
    assert leaked["OPENROUTER_API_KEY"] == "sk-hostile-shell"  # from the shell

    guarded = subprocess.run([sys.executable, "-c", "import tests.hermetic; " + probe],
                             cwd=tmp_path, env=_child_env(), capture_output=True, text=True,
                             timeout=120)
    assert guarded.returncode == 0, guarded.stderr[-2000:]
    seen = json.loads(guarded.stdout.strip().splitlines()[-1])
    assert seen["RL_LEARNING_MODE"] == shipped["rl"]["learning_mode"]
    assert seen["DECISION_GATE_MODE"] == shipped["decision_gate"]["mode"]
    assert seen["SERPER_API_KEY"] == ""
    assert seen["OPENROUTER_API_KEY"] not in ("sk-hostile-shell", "")
    assert seen["AUTH_REQUIRED"] is False


# ---------------------------------------------------------------------------
# End to end: a swallowed refusal still fails the test
# ---------------------------------------------------------------------------

_INNER_TESTS = '''
import requests
from pathlib import Path
from tests.hermetic import REPO

def test_swallowed_network_call():
    try:
        requests.get("https://google.serper.dev/search", timeout=1)
    except Exception:
        pass                      # application code often does exactly this

def test_swallowed_checkout_write():
    try:
        (REPO / "data" / "sa005-inner-probe.json").write_text("{}")
    except Exception:
        pass

def test_sandbox_write_is_fine():
    Path("data/logs").mkdir()
    Path("data/logs/ok.json").write_text("{}")
'''


def test_a_swallowed_refusal_fails_the_test_that_caused_it(tmp_path):
    (tmp_path / ".env").write_text(HOSTILE_DOTENV, encoding="utf-8")
    (tmp_path / "test_inner.py").write_text(textwrap.dedent(_INNER_TESTS), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider", "-p", "tests.hermetic",
         "test_inner.py"],
        cwd=tmp_path, env=_child_env(), capture_output=True, text=True, timeout=300)
    out = run.stdout
    assert run.returncode == 1, out[-3000:]
    assert re.search(r"\b2 failed, 1 passed\b", out), out[-3000:]
    assert "FAILED test_inner.py::test_swallowed_network_call" in out
    assert "outbound network to google.serper.dev:443" in out
    assert "FAILED test_inner.py::test_swallowed_checkout_write" in out
    assert "write on the checkout's data/sa005-inner-probe.json" in out
    assert not (REPO / "data" / "sa005-inner-probe.json").exists()
