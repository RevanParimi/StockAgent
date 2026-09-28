# SA-005 implementation receipt — a clean, isolated test and CI baseline

- **Story:** [SA-005](../stories/SA-005.md). Audit finding F22 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md).
- **Phase:** implementation, one conversation in two sittings: 2026-09-27 about 16:25–17:30 IST
  and 2026-09-28 about 06:45–07:45 IST. It includes a same-conversation self-review, which is
  **not** the fresh-session review. STATE: `review_required`.
- **Baseline:** `7901f352c90f…`, the SA-004 deploy record (committed locally, unpushed). The tree
  was clean. SA-004 is in `241c393`, pushed and deployed (`b3fb00dd`).
- **SA-039 checks:** none was due. P1 is Mon 28 Sep after 17:00 IST.
- **Review input:** [SA-005-manifest.json](SA-005-manifest.json). Its SHA-256 and the diff digest
  are under "Manifest and digests".
- **Nothing was committed, pushed or deployed.** No production variable, job or notification was
  touched. The CI workflow has therefore never run on GitHub (see "Open limitations").

## What it does, in one example

Before SA-005, the owner's full test run with the local `.env` present:

| | Before (baseline A, 27 Sep) | After |
|---|---|---|
| Outbound network | The socket guard of SA-002 blocked 74 attempts (NSE, OpenRouter, Serper). yfinance's `curl_cffi` requests bypass Python sockets, so it could not see them. | The first run under the new boundary found **286 Yahoo requests, 178 OpenRouter attempts and 124 NSE session attempts**. Every one is now refused, and the test that made it fails. |
| The checkout's `data/` | 149 paths written (35 targets once temp files are grouped); 24 untracked runtime files read. Afterwards 15 local files differed, including `managed_tickers.json` (the MARUTI toggle, I3) and `telemetry.db`. | Every test runs in an empty temporary directory. An audit hook refuses the checkout's `data/`, `logs/` and `outputs/`. The final run changed **0** files in `data/`. |
| `.env` | Loaded. `RL_LEARNING_MODE=observe` there failed 7 tests (SA-039 activation record); `DELIVERY_EMAIL_TO` there made 2 outbox tests pass (F5). 5 more passed only where the environment said Atlas was off, or by test order (D9). | Ignored, with every application variable removed from the process. The suite reads `config.yaml` and the code fallbacks only. |
| CI | None. | `.github/workflows/ci.yml`: the whole tree on Linux / Python 3.11, the broad-except and KT guards, and the SA-001 browser suite. |

## The boundary

`tests/hermetic.py`, imported by `tests/conftest.py` before any application code:

1. **Environment.** `PYTHON_DOTENV_DISABLED=1`, and `dotenv.load_dotenv` replaced by a no-op for
   releases that predate that variable. Every variable the application reads is popped from
   `os.environ`: the names `settings/base.py` reads (derived from its source at import, so a new
   setting is covered automatically) plus 32 read elsewhere (`EXTRA_APP_ENV`). A test keeps that
   list complete by scanning the application source.
2. **Network.** `socket.socket.connect`, `connect_ex` and `socket.getaddrinfo` refuse any
   non-loopback target, and `curl_cffi`'s `Session.request` / `AsyncSession.request` refuse any
   non-loopback URL. The refusal raises `OutboundNetworkBlocked` and is recorded with the test and
   the innermost application frame (and the thread, if not the main one).
3. **Working directory.** At session start the process moves into an empty temporary directory,
   so collection-time reads (the NSE holiday calendar) see a clean checkout. Each test then gets
   its own empty directory, seeded with the three tracked files the application opens by relative
   path: `config/milestones.yaml`, `config/sector_toggles.json`, `data/nse/key_registry.json`.
4. **Checkout guard.** `sys.addaudithook` sees every `open`, rename, remove, mkdir, rmdir,
   rmtree, copy, truncate, chmod, utime and `sqlite3.connect`. It refuses any access under the
   checkout's `data/`, `logs/` or `outputs/`, and any write anywhere else in the checkout
   (`__pycache__`, `.pytest_cache` and `.coverage*` excepted), with `CheckoutAccessBlocked`.
5. **Failing loudly.** Application code often swallows the refusal. A `pytest_runtest_makereport`
   wrapper therefore marks the phase failed whenever the test recorded a refusal, naming each one:

   ```text
   hermetic boundary (call): the test reached outside the sandbox (see tests/hermetic.py)
     outbound network to www.nseindia.com:443, from services/data/fetchers/nse_client.py:36 in _new_nse
   ```

   A refusal outside any test fails the session (exit status 1) and is listed in the summary.

## For the reviewer: decisions to check

1. **D1: one working-directory sandbox instead of ~40 path redirects.** The probe saw 35 written
   targets and 24 read files; the source holds about 40 CWD-relative runtime paths (module
   constants and `settings.*_DIR` values, all `data/...` or `outputs/...`, the Railway `/app`
   layout). Redirecting each would be a long fixture that misses
   the next one. Changing directory isolates all of them, including future ones; the audit hook
   catches anything resolved to an absolute checkout path. Costs: 3.7 ms per test (about 14 s of
   a 6.5-minute run), and three tracked files must be seeded. A test pins the seeded list to every
   tracked `config/` or `data/` file whose relative path appears in application source. The four
   existing redirect fixtures stay, because 25 test lines read their exact `tmp_path` targets.
2. **D2: no separate `RL_LEARNING_MODE` pin.** The card suggested an autouse pin to `adapt`.
   Removing the variable fixes the cause (the environment leaking in), and `config.yaml` ships
   `adapt`. A pin would also hide a real change to the shipped default.
3. **D3: removed one obsolete contract test.** `test_agent_timeout_plus_buffer_within_ts_client_timeout`
   asserted the agent timeout is below a TypeScript client's 180 s. That client is no longer in
   the repository, the PWA sets no analysis timeout, and `config.yaml` has shipped 180, the
   production value, since 2026-07-06. The test passed only where the environment overrode it. A
   comment stays in its place; routed to [SA-031](../stories/SA-031.md). Reject this if you know
   of a live consumer.
4. **D4: a Windows-only retry in three production writers.** `core/utils/atomic_io.py` gains
   `replace_with_retry`: on Windows it retries `os.replace` five times (0.38 s in all) on
   `PermissionError`; elsewhere it is one `os.replace`. `atomic_write_text`, `PushStore._save`
   and `PortfolioStore._write_json` use it. These were the three observed flakes. Production and
   CI run Linux, where the behaviour is unchanged. Other hand-rolled `.tmp` writers are untouched.
5. **D5: `--output-dir` on the eval CLI.** The smoke test ran `python -m ...run_eval` from the
   checkout and read `outputs/eval/` there. The flag is additive (default unchanged) and the test
   now writes to `tmp_path`.
6. **D6: the broad-except guard is a whole-tree ratchet.** "Changed-code guard" is implemented as
   an exact allowlist of today's 154 silent broad handlers, keyed by path, enclosing function and
   ordinal (moving code does not trip it; adding or re-ordering handlers inside a function does).
   A handler counts as handled if it logs (any `logger.x`/`logging.x`/`warnings.warn`/
   `traceback.print_exc` call), re-raises, or uses the bound exception. `suppress(Exception)`
   counts as a swallow. A new deliberate boundary needs `# swallow-ok: <reason>`. Fixing a
   grandfathered one makes its entry stale, and the check fails until the list is regenerated, so
   the list only shrinks through a reviewed diff. **The 154 entries were not reviewed one by one;**
   it is a burn-down list, not a statement that each is intentional.
7. **D7: `requirements.txt` is untouched.** Any edit to it makes the next production build
   re-resolve every unpinned package (SA-033's problem). Test-only tools are pinned in
   `requirements-test.txt` (pytest 9.0.3, pytest-asyncio 1.3.0). CI installs the runtime set as
   production does, after a CPU-only torch wheel, and prints `pip freeze`.
8. **D8: tests that boot the app use an API-only worker.** Two fixtures entered the FastAPI
   lifespan. When the singleton-lock port was free they became the background owner: they started
   the scheduler and the RL self-heal thread, which after 10 s rebuilds every missing month's
   envelope. With the checkout's data it found nothing to do; in an empty sandbox (and on any fresh
   CI checkout) it made LLM and Yahoo calls in the background, failing whichever test ran next.
   The new `api_worker_app` fixture stubs the lock and the calendar fetch.
9. **D9: tests state their Atlas premise.** `config.yaml` ships `atlas.enabled: true`. Five tests
   assumed "off" by clearing the variable (which falls through to the YAML) or by not saying.
   They passed only where the environment said off, or by order. Each now sets
   `ATLAS_ENABLED=false` explicitly.

## Acceptance criteria

| Criterion | Evidence | Verdict |
|---|---|---|
| Full suite runs without `.env`, production volume or untracked market files. | Fresh git checkout outside OneDrive (only tracked files plus this change; no `.env`; `data/` holds only the tracked key registry): 3799 passed, 13 skipped, 0 failed, 6 min 28 s. In the owner's checkout, with `.env` present: 3800 passed, 12 skipped, 0 failed, 7 min 10 s (the browser suite included), and `data/` unchanged. | Met locally (Windows, Python 3.13). Linux / 3.11 awaits the first CI run. |
| The MARUTI discovery test proves discovery using a test-created fixture. | `test_harness.py` builds a `data/predictions`-shaped tree: MARUTI with two cycles, an orphan feedback log, an empty log, a stray file. It asserts the exact entry count, tickers and sectors, and byte-identical files afterwards. Mutation M8 (wrong file-name glob) fails 3 tests. | Met. |
| CI runs appropriate unit/integration checks and a changed-code guard against unlogged broad exception swallowing; existing intentional boundaries are explicitly allowlisted. | `.github/workflows/ci.yml` (3 jobs, `contents: read`, no secrets, actions pinned to commit SHAs, `persist-credentials: false`). `scripts/ci/check_broad_except.py` with `broad_except_baseline.txt` and the inline pragma. 23 guard tests; mutation M11 (a new silent handler) is caught. | Implemented; not yet run on GitHub. The allowlist is grandfathered, not reviewed (D6). |

**Evidence the card asks for.**

- *Fresh checkout and declared dependencies, full suite once:* the fresh-checkout run above. It
  used the project's existing virtual environment (Python 3.13.11), which satisfies the declared
  ranges (`nse` 2.1.3 locally, 3.2.1 in production; both within `>=2.0,<4.0`). A fresh
  environment built from the declared files on Linux / 3.11 is exactly the CI job, which has not
  run yet.
- *Accidental outbound transport is rejected:* `test_hermetic_boundary.py` refuses raw sockets,
  DNS, `requests`, `httpx`, `smtplib` and `curl_cffi`, and runs a child pytest session in which a
  test swallows a refused request and another swallows a refused checkout write: both are
  reported failed, naming the target. Mutations M1, M2 and M7 break this and are caught.
- *parquet / NSE extras and file-replace tests on the supported environments:* on Windows / 3.13
  they pass with `pyarrow` 24.0.0 and `nse` 2.1.3 installed; the Windows rename flakes are fixed
  (D4) and tested (`test_atomic_replace_retry.py`, 8 tests; mutation M9 caught). On Linux / 3.11
  the first CI run will be the evidence. No Docker or WSL exists on this machine.

## The routed notes on this card

| Note | Disposition |
|---|---|
| F5 (DOC-001): two outbox tests need an ambient `DELIVERY_EMAIL_TO`. | Fixed in the tests. A fixture seeds a throwaway `users.db` account `u1`; the email must go to that account's address. A new premise test shows no account and no fallback means no email. `resolve_recipient()` is unchanged. Mutation M10 (no account) fails 2 tests. |
| T1 (SA-039): the review harness constructs a live NSE session. | Fixed. The shared `_patch_common` and six more copies of the seam stack, in five files, stub `OffMarketFetcher.__init__`; the shared harness and the dossier test also stub `ThesisReviewer._call_llm` (it called OpenRouter). Whether this is what dirtied `data/nse/key_registry.json` stays an inference; the registry is now only reachable as the sandbox copy. |
| `RL_LEARNING_MODE=observe` in `.env` fails 7 tests. | Fixed by removing application variables (D2). |
| L1 (SA-001): the browser suite only skips without Node. | CI's `browser` job runs `npm ci`, installs Chromium and runs `npm run test:frontend`, so it cannot skip there. |
| T2 (SA-002): no suite-wide network guard; 194 measured attempts. | Done, and wider: `curl_cffi` too (the invisible 286). |
| Windows rename flakes (`test_delivery_api`, `test_ops_alerts`, `test_portfolio_locking`). | Retried on Windows only (D4). The locking test now also asserts both workers exited 0, so a crashed worker is named instead of showing up as "lost updates". |
| Date-dependent fixtures: a pinned-date run. | **Not done.** Routed to [SA-012](../stories/SA-012.md) (see "Open limitations"). |
| The config loader stays reloaded. | Fixed: an autouse fixture reloads it against the real `config.yaml` after each test, and a new test shows the leak mechanism and the restore, against `config.yaml` parsed directly. |
| Two portfolio-pipeline tests depend on the local `atlas.db`. | Fixed (D9): they state Atlas off, so they pass alone, in either order and without a local `atlas.db`. |
| The locking flake. | See the rename flakes. |
| SA-004: job-outcome isolation; `managed_tickers.json` read; `ops_alerts_state.json` written. | All CWD-relative, so inside the sandbox (D1). The existing redirect is kept (D1). |
| I3 (SA-004 review): a test toggles MARUTI in the real `managed_tickers.json`. | The toggle now changes the sandbox copy. The final run left `data/` unchanged. |

## Other tests changed

Each change states a premise or stubs a seam the test does not exercise; no assertion was
weakened, and no test was skipped or marked xfail.

- **Relative fixture paths** (they broke in the sandbox): `test_ipo_research.py`,
  `test_ipo_extract.py`, `test_ipo_deep_dive.py`, `test_ipo_narrate.py`, `test_ipo_offer.py` and
  `test_requirements_deps.py` now anchor on `Path(__file__)`.
- **Live Yahoo calls, now stubbed with the application's own failure answer:** the regime
  detector's Brent / USD-INR / S&P fetches (`test_regime.py`; their labels depended on that day's
  markets), the run log's price lookup (`test_unified_e2e_parity*.py`), the symbol self-heal
  search (`tests/integration/test_data_fetchers.py`) and the watchlist quotes
  (`test_atlas_singletons.py`).
- **Premises:** `test_atlas_signup_user_mirror.py` (2 tests), `test_portfolio_pipeline.py` (2),
  `test_delivery_channels.py` (1): Atlas off (D9). `test_delivery_channels.py` and
  `test_delivery_channels_attachments.py`: a test assigned `settings.APP_PUBLIC_URL` without
  restoring it, and the attachment tests passed only after it (found by the reverse-order run).
- **App startup:** `test_phase2_api.py`, `test_analyse_auth_quota_dedup.py` (D8).
- **Eval CLI:** `test_run_eval_cli.py` (D5).

## Tests: commands, environment, results

Windows 11, Python 3.13.11 (`.stockai`), pytest 9.0.3. Every command from the repository root
unless stated; no `-p nonet` or `RL_LEARNING_MODE` any more. Raw logs are in ignored
`analysis_data/sa005/`.

| Run | Command | Result |
|---|---|---|
| Baseline A (old suite, measured) | `PYTHONPATH=analysis_data/sa005 RL_LEARNING_MODE=adapt python -m pytest -q -p no:cacheprovider -p probe -rfE tests` | 3751 passed, 12 skipped, 0 failed, 7 min 25 s. Probe: 74 blocked socket attempts, 149 checkout paths written, 24 `data/` files read. |
| First run under the boundary | `python -m pytest -q -p no:cacheprovider -rfE tests` | 3630 passed, 73 failed, 73 errors: the list this phase fixed. |
| Final, owner's checkout (`.env` present) | `python -m pytest -q -p no:cacheprovider -rfEs tests` | 3800 passed, 12 skipped, 0 failed, 7 min 10 s (the browser suite included). `data/` afterwards: 0 files changed, added or removed against the pre-session backup. |
| Final, fresh git checkout | same, run in `%TEMP%\sa005-clean-…` (`analysis_data/sa005/clean_copy.py`, then `git init`, `git add -A`, `git add -f data/nse/key_registry.json`, commit) | 3799 passed, 13 skipped, 0 failed, 6 min 28 s. Afterwards `git status` was empty, `data/` held only the tracked key registry, and `logs/` and `outputs/` did not exist. The 13th skip is the browser suite (no `node_modules`). |
| Reverse order | `PYTHONPATH=analysis_data/sa005 python -m pytest -q -p no:cacheprovider -p reverse -rfE tests` | 3798 passed, 1 failed (the `APP_PUBLIC_URL` leak, then fixed; the fixed files pass in both orders, 40 tests). |
| New tests | `python -m pytest -q tests/unit/test_hermetic_boundary.py tests/unit/test_broad_except_guard.py tests/unit/test_atomic_replace_retry.py` | 15 + 23 + 8 passed. |
| Mutations | `python analysis_data/sa005/mutate5.py` | 12 of 12 caught (table below) |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK, 154 grandfathered. |
| Python 3.11 syntax | `ast.parse(..., feature_version=(3, 11))` over all 730 tracked and new `.py` files | 0 failures. |
| KT | `python scripts/docs/build_kt_pdf.py`; `python scripts/docs/check_kt_docs.py` | PDF rebuilt, 25 pages, source `ae7e3940…`; `check_kt_docs`: 0 errors |

**Mutations** put one defect back at a time and restore the file afterwards; each must fail the
named tests.

| ID | Defect put back | Tests run | Result |
|---|---|---|---|
| M1 | `tests/hermetic.py`: a refusal raises but is not recorded | `test_hermetic_boundary.py` | 6 failed, 9 passed |
| M2 | a recorded refusal does not fail the test | same | 1 failed (the child session's swallowed refusals pass) |
| M3 | `data/`, `logs/`, `outputs/` not protected | same | 1 failed |
| M4 | dotenv left on (both layers removed); the outer run sets `PYTHON_DOTENV_DISABLED=1` so no real `.env` is read | the hostile-`.env` test | 1 failed (the child reads the hostile `.env`) |
| M5 | application variables not removed | `test_hermetic_boundary.py` | 1 failed |
| M6 | no per-test working directory | same | 2 failed |
| M7 | DNS lookups not guarded (a real lookup; the connect guard still refuses) | the socket tests | 2 failed |
| M8 | `harness.py` discovery globs the wrong file name | `test_harness.py` | 3 failed |
| M9 | `atomic_io`: the rename is never retried | `test_atomic_replace_retry.py` | 4 failed |
| M10 | the outbox tests without the seeded account (the F5 defect) | `test_atlas_outbox.py` | 2 failed |
| M11 | a new silent `except Exception` in `core/delivery/outbox.py` | the real-tree guard test | 1 failed |
| M12 | `api_worker_app` without the lock stub | the fixture test, then `test_phase2_api.py` | 1 failed |

After restoring, all 86 target tests pass. M12 is caught only when the fixture test runs before
anything else has taken the lock in that process (the lock is process-wide); in the first
attempt, with `test_phase2_api.py` first, it passed, and the self-heal thread's 10-second sleep
outlasted the file. In a full run the same defect fails unrelated later tests, as the first run
under the boundary showed. The `curl_cffi` guard was not mutated: that would send a real request.

## Documentation

- **KT** ([TECHNICAL_DESIGN.md](../../../TECHNICAL_DESIGN.md)): §1 status row; §10, the outbox
  gap now fixed; §12 status; §13 a new "The suite's hermetic boundary" subsection with the four
  rules, examples, the measurement and CI. New files are named in code formatting until the
  commit that lands them. PDF rebuilt (source ``ae7e39408e3a…``).
- **Human testing guide** ([TEAM_TESTING_GUIDE.md](../../../TEAM_TESTING_GUIDE.md)): HT-12 gains
  12-E (a green CI run, read as a tester) and 12-F (a witnessed drill: a throwaway pull request
  whose test calls a real website must fail, naming it). Both NOT RUN, PI target SA-005.
- **[CODEBASE.md](../../../../CODEBASE.md):** module map entries for `tests/hermetic.py`,
  `tests/conftest.py`, `scripts/ci/`, `.github/workflows/ci.yml`, `requirements-test.txt` and the
  `atomic_io` retry.
- **`tests/TEST_DOCUMENTATION.md`:** rewritten. The April version described files and a Groq
  client that no longer exist, and claimed no test used the network.
- **ARCHITECTURE:** unchanged; it has no testing or CI content and links the testing guide.
- **Story cards:** routed notes on [SA-012](../stories/SA-012.md), [SA-018](../stories/SA-018.md),
  [SA-029](../stories/SA-029.md) and [SA-031](../stories/SA-031.md).

## New findings, routed

| ID | Finding | Route |
|---|---|---|
| N1 | yfinance's `curl_cffi` transport bypasses Python sockets, so every earlier guard missed it. The old suite made about 286 real Yahoo requests per full run. | Fixed here (guard and test stubs). |
| N2 | `_ensure_calendar_file` checks `_ROOT/data/nse_holidays.json` while the calendar reads and writes `data/nse_holidays.json` relative to the working directory. Same file on Railway; different anywhere else. | [SA-029](../stories/SA-029.md) |
| N3 | Whether the app boots as the background owner depends on a local port being free, so tests entering the lifespan took different paths on different machines. | Fixed for tests (D8); the owner path is untested → [SA-029](../stories/SA-029.md). |
| N4 | The synthetic generator gives cycles 0 and 1 the same month, so they share a cycle id. | [SA-018](../stories/SA-018.md) |
| N5 | A contract test guarded a retired TypeScript client (D3). | [SA-031](../stories/SA-031.md) |

## Open limitations

- **CI has not run.** The workflow runs on the first push to `main`, and a push redeploys
  production, so it waits for the owner. YAML was parsed locally; the action SHAs were read from
  the upstream tags on 2026-09-27 (`checkout` v7.0.1, `setup-python` v7.0.0, `setup-node` v7.0.0).
  Risks for that first run: Linux-only failures, and the runtime packages resolving to newer
  versions than production (they are unpinned until SA-033).
- **No pinned-date run** (routed to SA-012).
- **Child processes are outside the boundary.** They inherit the cleaned environment only. Today
  that is the eval CLI smoke test (synthetic, no network) and the Node browser suite.
- **Cached store connections are shared between tests.** A store that keeps a module-level SQLite
  connection (`log_store`, `user_store`, `chat_session_store`, `atlas_store`) opens it in the first
  test's sandbox and keeps it. Tests that care already repoint the path and the holder. Nothing
  reaches the checkout, but test isolation is per path, not per connection.
- **`outputs/` was not backed up** before baseline A. Its two dated files for 2026-09-27
  (`llm_log`, `eval`) were also written by earlier runs that day, so they were left as they are.
  `data/` was restored from the backup and is identical to it.
- **The allowlist is not a review** (D6).

## Rollout

No production rollout. The CI workflow starts running when this is pushed; that push also
redeploys production, although no runtime behaviour changes on Linux (D4 retries only on
Windows; D5 adds an optional flag). After the first push, read the Actions page (human case
12-E) and record the three jobs' results against this story.

## At commit

The KT names `tests/hermetic.py`, `scripts/ci/check_broad_except.py`,
`.github/workflows/ci.yml`, `requirements-test.txt` and `core/utils/atomic_io.py` in code
formatting. The commit after the one that lands SA-005 should link the new files and bump the KT
header past `241c393`.

## Manifest and digests

- **Review input:** [SA-005-manifest.json](SA-005-manifest.json), SHA-256 of its LF bytes
  **`ef0e3a3114981160d94ac2c7ee637d42292ebf79f8abbde08a864c63dd0d72d5`**. 51 paths:
  - 4 code files: `core/utils/atomic_io.py`, `core/delivery/channels.py`,
    `core/portfolio/store.py`, `core/intelligence/rl/eval/run_eval.py`;
  - 4 CI and tooling files, all new: `.github/workflows/ci.yml`, `requirements-test.txt`,
    `scripts/ci/check_broad_except.py`, `scripts/ci/broad_except_baseline.txt`;
  - 2 test-support files: `tests/hermetic.py` (new) and `tests/conftest.py`;
  - 32 test files: 3 new, 29 changed;
  - 9 documentation files: the KT, the PDF, TEAM_TESTING_GUIDE, `CODEBASE.md`,
    `tests/TEST_DOCUMENTATION.md` and the SA-012, SA-018, SA-029 and SA-031 cards.

  `kt_manifest.py verify` gives 0 mismatches.
- **Excluded,** because they are written after the manifest: STATE.json, HANDOFF.md and this
  receipt.
- **Full diff** against `7901f35`:
  **`7274a199ecbb91e948257530cc6aa700af49f864cf4b25e8f6b2f5560ff22d5f`**, 139,141 bytes over 50
  text files. The PDF is pinned by its blob, `af4fcff5…` (source `ae7e3940…`).
- **To rebuild the diff:** take every manifest path except the PDF, sorted.
  - For a path tracked at the baseline, run `git diff --no-color --no-ext-diff 7901f35 -- PATH`.
  - For a new file, run `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`.
  - Concatenate the bytes. The ignored `analysis_data/sa005/sa005_diff.py` does exactly this.
- **After the commit:** `verify --rev <commit>` compares against the commit instead.
