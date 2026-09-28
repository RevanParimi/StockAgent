# Test documentation

For engineers running or adding tests. Updated 2026-09-27 for SA-005; the
April 2026 version of this page described a layout that no longer exists.

## Layout

| Path | What it holds |
|---|---|
| `tests/unit/` | Most of the suite, mirroring `core/`, `services/` and `src/backend/`. |
| `tests/integration/` | Several modules together: API routes, fetchers with mocked transports, stores. |
| `tests/contract/` | JSON shapes and settings other components rely on. |
| `tests/test_*.py` | Older top-level tests, collected with the rest. |
| `tests/frontend/` | The SA-001 browser suite (Node and Chromium), run by `npm run test:frontend`. |
| `tests/fixtures/` | Captured payloads. Read them through `Path(__file__)`, never a relative path. |
| `tests/hermetic.py` | The suite's hermetic boundary, described below. |

## Running

```text
pip install -r requirements.txt -r requirements-test.txt
python -m pytest tests                       # the whole tree, as CI runs it
python -m pytest tests/unit/test_atomic_io.py -q
npm ci && npx playwright install chromium && npm run test:frontend
python scripts/ci/check_broad_except.py      # the broad-exception guard
```

On this Windows checkout, use the project virtual environment
(`.stockai/Scripts/python.exe`). The whole tree takes about 7 minutes there.

No `.env`, network flag or `RL_LEARNING_MODE` setting is needed. The suite
ignores all three (next section).

## The hermetic boundary

`tests/conftest.py` imports `tests/hermetic.py` before any application code.
Four rules then hold for every test, on a laptop and in CI alike:

1. **No `.env`, no shell settings.** dotenv is off, and every environment
   variable the application reads is removed. Settings come from
   `config.yaml` and the code fallbacks. A test that needs a value sets it:
   `monkeypatch.setenv("ATLAS_ENABLED", "false")` or
   `monkeypatch.setattr(settings, ...)`. Do not rely on an unset variable
   meaning "off": `config.yaml` may say otherwise (it ships
   `atlas.enabled: true`).
2. **No outbound network.** Non-loopback sockets and DNS lookups, and every
   `curl_cffi` request (yfinance's transport), raise `OutboundNetworkBlocked`.
   Application code often swallows that error, so the boundary also fails the
   test itself and names the target and the application line that made the
   call. Loopback stays open.
3. **An empty working directory.** The application keeps runtime state under
   `data/` and `outputs/`, relative to the working directory (`/app` on
   Railway). Each test runs in its own empty temporary directory, seeded only
   with `config/milestones.yaml`, `config/sector_toggles.json` and
   `data/nse/key_registry.json`, the tracked files the application reads by
   relative path.
4. **The checkout is off limits.** Any access to the checkout's `data/`,
   `logs/` or `outputs/`, and any write anywhere else in it, raises
   `CheckoutAccessBlocked` and fails the test. The hook sees Python's file
   calls only: a directory listing, an existence check, a native library's
   own file access (pyarrow, SQLite given a `file:` URI) and a Windows
   short-name spelling of the checkout are not refused. Build paths from the
   working directory or `tmp_path`, never from the checkout.

### When a test fails at the boundary

The failure reads like this:

```text
hermetic boundary (call): the test reached outside the sandbox (see tests/hermetic.py)
  outbound network to openrouter.ai:443, from core/intelligence/rl/agents/thesis_reviewer.py:223 in _call_llm
```

Stub the seam the message names, at the lowest level the test does not
exercise, and give it the answer the application gives when that call fails.
For example, `ThesisReviewer._call_llm` returns an intact thesis, and
`OffMarketFetcher.__init__` opens no NSE session. If the call came from a
background thread (the message says so), look for a thread the test started:
`with TestClient(app)` runs the app's startup, so use the `api_worker_app`
fixture, which boots it as an API-only worker.

The boundary does not reach child processes. A test that runs a subprocess
must point its outputs at `tmp_path`, as `test_run_eval_cli.py` does with
`--output-dir`.

## CI

`.github/workflows/ci.yml` runs on every push to `main`, on pull requests and
on demand. It uses Linux, Python 3.11 (the production image's interpreter),
read-only repository access and no secrets. It has three jobs:

- the whole `tests/` tree;
- `scripts/ci/check_broad_except.py` and `scripts/docs/check_kt_docs.py`;
- the SA-001 browser suite in Chromium.

The broad-exception guard fails when new code catches every exception
(`except:`, `Exception`, `BaseException`, `contextlib.suppress(Exception)`)
and neither logs, re-raises nor uses the exception. The handlers that did so
before SA-005 are listed in `scripts/ci/broad_except_baseline.txt`, a
burn-down list that was not reviewed entry by entry. A deliberate new boundary
carries its reason on the `except` line:

```python
except Exception:  # swallow-ok: best-effort cache warm-up; a miss is harmless
```

Test-only tools are pinned in `requirements-test.txt`. The runtime packages
come from `requirements.txt`, which is still mostly unpinned until SA-033
adds a lock.

## Windows

Local runs use Python 3.13 on Windows; CI and production use 3.11 on Linux.

- On Windows, `os.replace` can fail for a moment with `PermissionError` while
  another handle (a reader, an antivirus scan) holds the target. The shared
  writer in `core/utils/atomic_io.py` retries it briefly, on Windows only,
  and the push-subscription and portfolio stores use the same step. This used
  to fail `test_delivery_api`, `test_ops_alerts` and `test_portfolio_locking`
  intermittently.
- The browser suite skips inside pytest when Node or Chromium is missing. CI
  runs it as a separate job, so there it cannot be skipped.

## Adding a test

1. Put it under `tests/unit/`, next to the module it covers.
2. Derive the expected result independently: by hand, from the input, or from
   a second source. Do not read it back from the code under test.
3. Build the files it needs in `tmp_path`. For store paths, use the same
   recipe as the existing tests: repoint the module's path constant and give
   it a fresh connection holder.
4. Mock transports at the seam the test does not exercise. If you miss one,
   the boundary fails the test and names it.
