"""Run the KT document's existing test selection in an isolated source copy.

No .env, production data, application startup, real transports or subprocesses
are permitted in the test child. Requires the project's test dependencies.
Optional --dependency-path adds an existing isolated dependency directory.
Raw output remains under ignored analysis_data/kt_20260915/.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
TESTS = [
    "tests/unit/sectors/test_router_equivalence.py",
    "tests/unit/shared/test_data_health_record.py",
    "tests/unit/shared/test_hard_bind_flag.py",
    "tests/unit/test_scheduler_ipo_refresh.py",
    "tests/unit/test_scheduler_delivery_jobs.py",
    "tests/unit/test_scheduler_portfolio_hook.py",
    "tests/unit/intelligence/rl/test_daily_review_early_exit.py",
    "tests/unit/intelligence/rl/test_hard_bind_daily_review.py",
    "tests/unit/test_ipo_calendar.py",
    "tests/unit/test_ipo_history.py",
    "tests/unit/test_ipo_report.py",
    "tests/unit/test_ipo_signals.py",
    "tests/unit/test_ipo_velocity.py",
    "tests/unit/test_ipo_tracker.py",
    "tests/unit/test_portfolio_api.py",
    "tests/unit/test_txn_transparency.py",
    "tests/unit/test_trailing_stop.py",
    "tests/unit/test_portfolio_digest_text.py",
    "tests/unit/test_portfolio_reconcile.py",
    "tests/unit/test_discovery_cycle_ipo.py",
    "tests/unit/audit/test_audit_rules.py",
    "tests/unit/audit/test_audit_outcomes.py",
    "tests/unit/intelligence/rl/eval/test_scorecard.py",
    "tests/unit/intelligence/rl/eval/test_learning_evidence.py",
    "tests/unit/test_autopilot_executor_sells.py",
    "tests/unit/test_autopilot_executor_adds.py",
    "tests/unit/test_autopilot_executor_switch.py",
    "tests/unit/test_atlas_outbox.py",
    "tests/unit/ops/test_watchdog_engine.py",
    "tests/unit/ops/test_watchdog_runner.py",
]

GUARD = r'''
import os, socket, subprocess, sys
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
def blocked(*args, **kwargs):
    raise RuntimeError("KT validation blocked an external transport or subprocess")
async def blocked_async(*args, **kwargs):
    return blocked()
original_connect = socket.socket.connect
def local_socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
    # Windows asyncio needs a self-pipe. Permit only this connection to a
    # newly-created loopback listener; ordinary socket.connect remains blocked.
    if family not in (socket.AF_INET, socket.AF_INET6):
        raise ValueError("Only loopback socket pairs are supported in KT checks")
    listener = socket.socket(family, type, proto)
    client = socket.socket(family, type, proto)
    try:
        listener.bind(("::1" if family == socket.AF_INET6 else "127.0.0.1", 0))
        listener.listen(1)
        original_connect(client, listener.getsockname())
        server, _ = listener.accept()
        return server, client
    except Exception:
        client.close()
        raise
    finally:
        listener.close()
if os.name == "nt":
    socket.socketpair = local_socketpair
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.socket.sendto = blocked
socket.create_connection = blocked
class BlockedPopen(subprocess.Popen):
    def __init__(self, *args, **kwargs):
        blocked()
subprocess.Popen = BlockedPopen
os.system = blocked
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
import requests, httpx, urllib.request, smtplib
requests.sessions.Session.request = blocked
httpx.HTTPTransport.handle_request = blocked
httpx.AsyncHTTPTransport.handle_async_request = blocked_async
urllib.request.urlopen = blocked
smtplib.SMTP.connect = blocked
try:
    import curl_cffi.requests
    curl_cffi.requests.Session.request = blocked
    curl_cffi.requests.AsyncSession.request = blocked_async
except ImportError:
    pass
try:
    import pywebpush
    pywebpush.webpush = blocked
except ImportError:
    pass
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-path", type=Path)
    args = parser.parse_args()
    work = ROOT / "analysis_data/kt_20260915"
    work.mkdir(parents=True, exist_ok=True)
    checkout = Path(tempfile.mkdtemp(prefix="test_checkout_", dir=work))
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in names:
        if not name or name.startswith((".env", "data/", "outputs/", "logs/", "docs/")):
            continue
        source = ROOT / name
        if source.is_file():
            target = checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    guard = work / "guarded_pytest.py"
    guard.write_text(GUARD, encoding="utf-8")
    keep = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT",
            "LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update(PYTHON_DOTENV_DISABLED="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               OPENROUTER_API_KEY="kt-dummy-key", GROQ_API_KEY="kt-dummy-key",
               DELIVERY_EMAIL_ENABLED="false", DELIVERY_PUSH_ENABLED="false",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    if args.dependency_path:
        env["PYTHONPATH"] = str(args.dependency_path.resolve())
    xml = work / "pytest.xml"
    command = [sys.executable, str(guard), "-q", "--tb=short", "--disable-warnings",
               "-p", "pytest_asyncio.plugin", "--junitxml=" + str(xml), *TESTS]
    with (work / "pytest.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=checkout, env=env, stdout=log, stderr=subprocess.STDOUT)
    summary = {"exit_code": result.returncode, "python": sys.version.split()[0],
               "platform": sys.platform, "test_files": TESTS}
    if xml.exists():
        suites = ET.parse(xml).getroot().findall("testsuite")
        for key in ("tests", "failures", "errors", "skipped"):
            summary[key] = sum(int(s.get(key, "0")) for s in suites)
        summary["seconds"] = round(sum(float(s.get("time", "0")) for s in suites), 2)
    (work / "test_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
