"""The suite's hermetic boundary (SA-005): no .env, no production volume, no
untracked market files and no outbound network.

tests/conftest.py imports this module before any application module, because
the settings module reads the environment once, at import.

1. Environment. python-dotenv is switched off (PYTHON_DOTENV_DISABLED, and
   dotenv.load_dotenv replaced by a no-op for releases that predate that
   variable), and every variable the application reads is removed from
   os.environ. Settings therefore resolve to config.yaml plus the checked-in
   fallbacks, whatever the developer's .env or shell holds. A test that needs
   a value sets it itself.
2. Network. A non-loopback socket connect or DNS lookup, and any curl_cffi
   request (yfinance's transport, which resolves names in C), raises
   OutboundNetworkBlocked. Application code often swallows transport errors,
   so the attempt is also recorded and fails the test, naming the target and
   the application frame that made it. Loopback stays open: asyncio on
   Windows builds its self-pipe from a 127.0.0.1 socket pair.
3. Working directory. The application keeps runtime state relative to the
   working directory: data/... and outputs/..., the Railway volume layout
   under /app. The session runs in an empty temporary directory and each
   test in its own, seeded only with the tracked files the application reads
   by relative path (SEEDED). Every relative data/ read or write therefore
   lands in a sandbox that starts as empty as a fresh checkout.
4. Checkout guard. An audit hook refuses any access to the checkout's own
   data/, logs/ and outputs/, and any write elsewhere in the checkout
   (bytecode and pytest caches excepted), whatever path spelling reached it.
   The refusal fails the test that made it; outside a test it fails the
   session.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import traceback
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

REPO = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# 1. Environment
# ---------------------------------------------------------------------------

_SETTINGS_BASE = REPO / "src" / "backend" / "shared" / "config" / "settings" / "base.py"
ENV_READ = re.compile(r"""(?:getenv\(|environ\.get\(|environ\[|\benv=)\s*["']([A-Z][A-Z0-9_]*)["']""")

# Read outside settings/base.py. tests/unit/test_hermetic_boundary.py scans the
# application source and fails when a new name is missing here.
EXTRA_APP_ENV = frozenset({
    "ATLAS_DB_PATH", "ATLAS_ENABLED", "AUTO_TICKERS", "CHROMA_COLLECTION_NAME",
    "CHROMA_PERSIST_DIR", "CONFIG_FILE", "EMBEDDING_DIMENSION", "EMBEDDING_MODEL",
    "EMBEDDING_PROVIDER", "GITHUB_BRANCH", "GITHUB_REPO", "GITHUB_TOKEN", "LOGS_DIR",
    "PINECONE_API_KEY", "PINECONE_ENVIRONMENT", "PINECONE_INDEX_NAME", "QDRANT_COLLECTION",
    "QDRANT_URL", "RAG_CHUNK_OVERLAP", "RAG_CHUNK_SIZE", "RAG_ENABLED",
    "RAG_SIMILARITY_THRESHOLD", "RAG_TOP_K", "RERANKER_ENABLED", "RERANKER_MODEL",
    "SCHEDULER_KEY", "SECTOR_TOGGLES_PATH", "SERPER_MONTHLY_LIMIT", "SINGLETON_LOCK_PORT",
    "TAVILY_MONTHLY_LIMIT", "UNIVERSE_MAX_DAILY_ANALYSES", "VECTOR_STORE_PROVIDER",
})


def app_env_names() -> frozenset[str]:
    """Every environment variable the application reads, as far as the
    settings module and EXTRA_APP_ENV declare them."""
    base = _SETTINGS_BASE.read_text(encoding="utf-8-sig")
    return frozenset(ENV_READ.findall(base)) | EXTRA_APP_ENV


if "backend.shared.config.settings.base" in sys.modules:
    raise RuntimeError(
        "tests/hermetic.py must run before the settings module is imported; a plugin "
        "loaded ahead of tests/conftest.py imported application code")

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *args, **kwargs: False
REMOVED_ENV = tuple(sorted(n for n in app_env_names() if os.environ.pop(n, None) is not None))

# ---------------------------------------------------------------------------
# Attribution: which test (and phase) is running
# ---------------------------------------------------------------------------

_CURRENT = ["<startup>"]
_ATTEMPTS: list[tuple[str, str, str]] = []       # (test, target, application frame)
_VIOLATIONS: list[tuple[str, str, str, str]] = []  # (test, operation, path, application frame)
_APP_DIRS = tuple(os.path.normcase(str(REPO / d)) + os.sep for d in ("core", "services", "src"))


def _app_frame() -> str:
    thread = threading.current_thread()
    where = "" if thread is threading.main_thread() else f" (thread {thread.name})"
    for frame in reversed(traceback.extract_stack()[:-3]):
        if os.path.normcase(frame.filename).startswith(_APP_DIRS):
            rel = os.path.relpath(frame.filename, REPO).replace(os.sep, "/")
            return f"{rel}:{frame.lineno} in {frame.name}{where}"
    return f"no application frame{where or ' (the test itself)'}"


# ---------------------------------------------------------------------------
# 2. Network
# ---------------------------------------------------------------------------

class OutboundNetworkBlocked(ConnectionRefusedError):
    """An outbound connection was attempted under pytest. Mock the transport."""


def _is_loopback(host) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").lower()
    return host in ("", "localhost", "::1", "0.0.0.0") or host.startswith("127.")


def _refuse(target: str):
    _ATTEMPTS.append((_CURRENT[0], target, _app_frame()))
    raise OutboundNetworkBlocked(f"tests/hermetic.py blocked an outbound connection to {target}")


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo


def _guarded_connect(self, address):
    if isinstance(address, tuple) and not _is_loopback(address[0]):
        _refuse(f"{address[0]}:{address[1]}")
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if isinstance(address, tuple) and not _is_loopback(address[0]):
        _refuse(f"{address[0]}:{address[1]}")
    return _real_connect_ex(self, address)


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    if not _is_loopback(host):
        _refuse(f"{host}:{port}")
    return _real_getaddrinfo(host, port, *args, **kwargs)


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
socket.getaddrinfo = _guarded_getaddrinfo


def _guard_curl_cffi() -> None:
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        return

    def _host(url) -> str:
        return urlsplit(str(url)).hostname or str(url)

    real_sync = curl_requests.Session.request
    real_async = curl_requests.AsyncSession.request

    def request(self, method, url, *args, **kwargs):
        if not _is_loopback(_host(url)):
            _refuse(f"{_host(url)} (curl_cffi {method})")
        return real_sync(self, method, url, *args, **kwargs)

    async def arequest(self, method, url, *args, **kwargs):
        if not _is_loopback(_host(url)):
            _refuse(f"{_host(url)} (curl_cffi {method})")
        return await real_async(self, method, url, *args, **kwargs)

    curl_requests.Session.request = request
    curl_requests.AsyncSession.request = arequest


_guard_curl_cffi()

# ---------------------------------------------------------------------------
# 3. Working directory
# ---------------------------------------------------------------------------

# Tracked files the application opens relative to the working directory. They
# are read into memory now, before the checkout guard is armed.
SEEDED = ("config/milestones.yaml", "config/sector_toggles.json", "data/nse/key_registry.json")
_SEED_BYTES = {rel: (REPO / rel).read_bytes() for rel in SEEDED}
_SESSION_DIR: list[Path] = []
_INVOCATION_DIR = os.getcwd()


def make_sandbox(parent: Path | None = None) -> Path:
    """An empty working directory holding only the SEEDED tracked files."""
    root = Path(tempfile.mkdtemp(prefix="cwd-", dir=parent))
    for rel, data in _SEED_BYTES.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


# ---------------------------------------------------------------------------
# 4. Checkout guard
# ---------------------------------------------------------------------------

class CheckoutAccessBlocked(PermissionError):
    """A test touched the checkout's runtime files. Use tmp_path or a relative path."""


_REPO_PREFIX = os.path.normcase(str(REPO)) + os.sep
_PROTECTED = tuple(os.path.normcase(str(REPO / d)) for d in ("data", "logs", "outputs"))
_WRITE_EVENTS = {"os.remove", "os.mkdir", "os.rmdir", "shutil.rmtree", "os.truncate",
                 "os.chmod", "os.utime", "sqlite3.connect"}
_TWO_PATH_EVENTS = {"os.rename", "shutil.copyfile", "shutil.move", "os.link", "os.symlink"}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_ARMED = [True]
_inside = threading.local()


def _checkout_path(path) -> tuple[str, str] | None:
    """(normalized absolute path, path relative to the checkout as spelled)
    if `path` lies inside the checkout."""
    if path is None or isinstance(path, int):
        return None
    try:
        text = os.fsdecode(path)
    except TypeError:
        return None
    if not text or text == ":memory:" or text.startswith("file:"):
        return None
    absolute = os.path.abspath(text)
    full = os.path.normcase(absolute)
    if not full.startswith(_REPO_PREFIX):
        return None
    return full, absolute[len(_REPO_PREFIX):].replace(os.sep, "/")


def _cache_path(full: str) -> bool:
    parts = full[len(_REPO_PREFIX):].split(os.sep)
    return "__pycache__" in parts or ".pytest_cache" in parts or parts[-1].startswith(".coverage")


def _protected(full: str) -> bool:
    return any(full == p or full.startswith(p + os.sep) for p in _PROTECTED)


def _check(operation: str, path, writing: bool) -> None:
    found = _checkout_path(path)
    if found is None:
        return
    full, rel = found
    if not (_protected(full) or (writing and not _cache_path(full))):
        return
    _VIOLATIONS.append((_CURRENT[0], operation, rel, _app_frame()))
    raise CheckoutAccessBlocked(f"tests/hermetic.py blocked {operation} on the checkout's {rel}")


def _audit(event: str, args) -> None:
    if not _ARMED[0] or getattr(_inside, "busy", False):
        return
    if event != "open" and event not in _WRITE_EVENTS and event not in _TWO_PATH_EVENTS:
        return
    _inside.busy = True
    try:
        if event == "open":
            path, mode, flags = args
            writing = (any(c in mode for c in "wax+") if isinstance(mode, str)
                       else bool(flags & _WRITE_FLAGS))
            _check("write" if writing else "read", path, writing)
        elif event in _TWO_PATH_EVENTS:
            _check(event, args[0], event in ("os.rename", "shutil.move"))
            _check(event, args[1], True)
        else:
            _check(event, args[0], True)
    finally:
        _inside.busy = False


sys.addaudithook(_audit)

@contextmanager
def expect_blocked():
    """For the boundary's own tests: collect what is refused inside the block
    instead of failing the test. A refusal outside the block still fails it."""
    start_attempts, start_violations = len(_ATTEMPTS), len(_VIOLATIONS)
    caught = SimpleNamespace(attempts=[], violations=[])
    try:
        yield caught
    finally:
        caught.attempts = _ATTEMPTS[start_attempts:]
        caught.violations = _VIOLATIONS[start_violations:]
        del _ATTEMPTS[start_attempts:]
        del _VIOLATIONS[start_violations:]


# ---------------------------------------------------------------------------
# pytest hooks, re-exported by tests/conftest.py
# ---------------------------------------------------------------------------


def pytest_report_header(config):
    return (f"hermetic: .env disabled; {len(REMOVED_ENV)} application env var(s) removed; "
            "outbound network blocked; each test runs in an empty working directory")


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    session_dir = Path(tempfile.mkdtemp(prefix="stockagent-tests-"))
    _SESSION_DIR.append(session_dir)
    os.chdir(make_sandbox(session_dir))
    _CURRENT[0] = "<collection>"


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    _CURRENT[0] = item.nodeid
    os.chdir(make_sandbox(_SESSION_DIR[0] if _SESSION_DIR else None))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    lines = [f"outbound network to {target}, from {frame}"
             for test, target, frame in _ATTEMPTS if test == item.nodeid]
    lines += [f"{operation} on the checkout's {path}, from {frame}"
              for test, operation, path, frame in _VIOLATIONS if test == item.nodeid]
    _ATTEMPTS[:] = [a for a in _ATTEMPTS if a[0] != item.nodeid]
    _VIOLATIONS[:] = [v for v in _VIOLATIONS if v[0] != item.nodeid]
    if lines:
        report.outcome = "failed"
        report.longrepr = (f"hermetic boundary ({call.when}): the test reached outside the sandbox"
                           " (see tests/hermetic.py)\n  " + "\n  ".join(lines))
    return report


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    _CURRENT[0] = "<between tests>"
    if _SESSION_DIR:
        os.chdir(_SESSION_DIR[0])


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    _ARMED[0] = False
    os.chdir(_INVOCATION_DIR)
    if _ATTEMPTS or _VIOLATIONS:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    for session_dir in _SESSION_DIR:
        shutil.rmtree(session_dir, ignore_errors=True)


def pytest_terminal_summary(terminalreporter):
    if not (_ATTEMPTS or _VIOLATIONS):
        return
    terminalreporter.section("hermetic boundary: outside any test", sep="-", red=True)
    for test, target, frame in _ATTEMPTS:
        terminalreporter.line(f"{test}: outbound network to {target}, from {frame}")
    for test, operation, path, frame in _VIOLATIONS:
        terminalreporter.line(f"{test}: {operation} on the checkout's {path}, from {frame}")
