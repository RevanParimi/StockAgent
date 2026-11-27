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
| `tests/frontend/` | The browser suites (Node and Chromium), run by `npm run test:frontend`: the chat Markdown boundary, the Logs screen, real figures with owner-only operator tools (`no_invented_figures.test.mjs`), the member screens (`member_screens.test.mjs`) and the architecture map (`architecture_map.test.mjs` opens the committed page from disk with the network off; `architecture_map_logic.test.mjs` checks its layout, flowcharts, colours and rebuild without a browser). The app suites serve the real prototype files and answer the API from the test's own plan; nothing reaches the network. |
| `tests/fixtures/` | Captured payloads. Read them through `Path(__file__)`, never a relative path. |
| `tests/hermetic.py` | The suite's hermetic boundary, described below. |
| `tests/guard_plugin.py`, `tests/proc_tree.py` | The memory guard's pytest plugin and its process-tree helpers, described below. |

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
ignores all three (see "The hermetic boundary").

## The two screen suites

`no_invented_figures.test.mjs` and `member_screens.test.mjs` open the real app
afresh for most cases. Both stop CSS animations and transitions in every page
(`stopAnimations` in `chat_harness.mjs`): the app's rotating sphere and pulsing
dots repaint on every frame, headless Chromium draws them in software, and one
open page held about one of the build box's two CPUs while its test only
waited. The suites read text, the DOM and clicks, which animations do not
change. The chat Markdown suite does not use it: a security suite should not
switch off anything a hostile fixture could run on.

`no_invented_figures.test.mjs` also runs its cases two at a time. Add a case
above the suite at the end of that file; one added after it, or one without a
body, fails the file instead of silently not running. A case that needs an
answer to arrive late holds it with `gate()` and opens it itself, not with a
timed delay. `member_screens.test.mjs`'s "unavailable" checks wait for the text
(`shown`); a new check of text a screen may still be drawing should do the same.
Older checks still follow fixed pauses.

## The memory guard (the build box, Linux)

On the code-server, run the full suite through the guard, not bare pytest:

```text
.stockai/bin/python scripts/ci/guarded_suite.py                   # the full suite
.stockai/bin/python scripts/ci/guarded_suite.py --only browser    # the browser files alone
.stockai/bin/python scripts/ci/guarded_suite.py -- tests/unit/test_atomic_io.py -q
```

The test run before a push (`autopilot/prepush-suite.sh`, outside git) calls
the same script. The full suite is two steps, and both must pass: `main`
(everything but the four browser files) and then `browser`
(`test_chat_markdown_boundary.py`, `test_member_screens_pr040.py`,
`test_ui_no_invented_figures_pr001.py` and
`architecture_map/test_viewer_browser_map002.py`). A new test file that starts a browser
belongs in `BROWSER_FILES` in the script; a test fails if it is missing.

| Rule | Limit | What happens |
|---|---|---|
| Memory: the container's `anon` (cgroup v2 `memory.stat`; page cache is not counted) | over 2,400 MB | the run stops, exit 3 |
| One test | 300 s; 960 s in the browser step | the run stops, exit 4 |
| No test running (start-up, collection, session end) | 600 s | the run stops, exit 4 |
| The whole run | 5,400 s | the run stops, exit 4 |
| SIGTERM, SIGINT or SIGHUP to the guard | | the run stops, exit 5 |

A stopped run ends every process it started and runs no further step. A process
a test leaves behind, such as a browser whose test timed out, is ended after
that test in the browser step, and at session end in both. Processes are found
by lineage, never by name, so the editor's and other sessions' `node` processes
are never touched. The pytest process is also the kernel's first choice if
memory runs out, and it dies if the guard does. Other exit codes: 0 passed,
1 a test or step failed (so does a pytest that ends without finishing its
session, or a process that cannot be ended), 2 the guard could not run (it needs
Linux and a readable `anon`; elsewhere run pytest itself) or failed itself. The
log warns when the container's cap leaves under 300 MB above the limit. A run
given after `--` ends leftovers at session end, or after each test when it names
a browser file.

Each stop and each process ended is logged in
`analysis_data/test-guard/guard.log` (ignored by git; the last 400 lines), with
the test that was running. To see the guard act on a real machine, run
`.stockai/bin/python scripts/ci/guarded_suite.py -- scripts/ci/guard_forced_memory.py -s`:
it grows towards 3.5 GB, must be stopped on the way (exit 3), gives up on its
own above 2,700 MB of `anon`, and skips without the guard.

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
- the browser suites in Chromium (`npm run test:frontend`).

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
- The browser suites run inside pytest too (`test_chat_markdown_boundary.py`,
  `test_member_screens_pr040.py`, `test_ui_no_invented_figures_pr001.py`,
  `architecture_map/test_viewer_browser_map002.py`) and
  skip there when Node or Chromium is missing. CI runs them as a separate job,
  so there they cannot be skipped.

## Adding a test

1. Put it under `tests/unit/`, next to the module it covers.
2. Derive the expected result independently: by hand, from the input, or from
   a second source. Do not read it back from the code under test.
3. Build the files it needs in `tmp_path`. For store paths, use the same
   recipe as the existing tests: repoint the module's path constant and give
   it a fresh connection holder.
4. Mock transports at the seam the test does not exercise. If you miss one,
   the boundary fails the test and names it.
