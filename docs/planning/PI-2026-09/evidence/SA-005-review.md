# SA-005 review receipt — a clean, isolated test and CI baseline

- **Story:** [SA-005](../stories/SA-005.md). Audit finding F22 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md).
- **Review context:** a **fresh-session** review, in a new conversation on Mon 2026-09-28, about
  07:25–07:55 IST. It is separate from the implementation conversation (27 Sep about
  16:25–17:30 and 28 Sep about 06:45–07:45 IST). No SA-039 check was due; P1 is today after
  17:00 IST.
- **Reviewed input:** the uncommitted worktree on baseline
  `7901f352c90ff265be9fa60166d93692d11b1a21`. See the
  [implementation receipt](SA-005-implementation.md).
- **Verdict: ACCEPTED.** No critical, high or medium finding.
  - Two low findings (L1, L2) are routed to [SA-031](../stories/SA-031.md). L1's documentation
    half was fixed in this review (documentation only; see "Review edits").
  - Two info notes (I1, I2) need no action.
  - **CI has still never run on GitHub.** Its first run needs a push, and every push redeploys, so
    it waits for the owner. That run is SA-005's remaining verification (human case 12-E).

## Input verified first

- `kt_manifest.py verify SA-005-manifest.json` against the working tree gave 51 files,
  0 mismatches, and review input
  **`ef0e3a3114981160d94ac2c7ee637d42292ebf79f8abbde08a864c63dd0d72d5`**.
- **Checked with the reviewer's own script** (scratchpad `verify_input.py`, not the implementer's
  `sa005_diff.py`):
  - SHA-256 of the manifest's LF bytes: `ef0e3a31…`, as recorded;
  - each file's `git hash-object` equals its manifest blob: 51 of 51;
  - **completeness:** every path that differs from `7901f35` (`git diff --name-only` plus
    untracked, non-ignored files) is in the manifest, apart from the four bookkeeping files the
    receipt excludes. No manifest path is unchanged;
  - **the diff digest** rebuilt by the receipt's recipe: sorted manifest paths without the PDF;
    `git diff --no-color --no-ext-diff 7901f35 -- PATH` for tracked paths and `--no-index` against
    `/dev/null` for new ones, concatenated. It gives
    **`7274a199ecbb91e948257530cc6aa700af49f864cf4b25e8f6b2f5560ff22d5f`**: 139,141 bytes over
    50 files, matching the receipt. The PDF blob is `af4fcff5…`, as recorded.
- **No concurrent session was busy** (`ListAgents`: 13 peers, all idle), and nothing changed the
  input during the review.

## Contract checked

SA-005's invariant, in the card's words: the full suite runs without `.env`, the production volume
or untracked market files; accidental outbound transport is rejected; CI runs the suite and a
changed-code guard against unlogged broad exception swallowing, with the existing boundaries
listed explicitly.

In one example: the owner's `.env` holds real Serper, Tavily and OpenRouter keys and
`RL_LEARNING_MODE=observe`. Before SA-005, a test whose mock missed a seam sent real requests
with those keys, and its assertions depended on that file. After SA-005, the same test sees
`config.yaml`'s values and empty keys, and the request is refused and fails the test.

## The hard review

**What was traced, from input to effect:**

- **`.env` and shell.** `settings/base.py:18-20` calls `from dotenv import load_dotenv;
  load_dotenv()` at import. `tests/hermetic.py` sets `PYTHON_DOTENV_DISABLED=1`, which
  python-dotenv 1.2.2 honours, and replaces `dotenv.load_dotenv` before any application import.
  A guard raises if the settings module was imported first. The popped names come from
  `base.py`'s own source, plus a declared list. The only dynamic read, `loader.cfg(env=...)`, is
  always called with literal names (94 call sites), so the source scan sees every one.
  - **P6 (reviewer probe), with the owner's real `.env` beside the code:** Serper, Tavily, SMTP
    password, Resend, VAPID private key and `DELIVERY_EMAIL_TO` are all empty, and OpenRouter
    holds the code's placeholder. No value was printed.
- **Network.** `socket.socket.connect`, `connect_ex` and `socket.getaddrinfo` are patched at class
  or module level, so `create_connection`, `http.client`, `urllib3`, `httpx` and `smtplib` all
  pass through them. `curl_cffi`'s `Session.request` / `AsyncSession.request` are patched too.
  - **P1 (reviewer probe): yfinance's real call path.** `yf.Ticker("MARUTI.NS").history()` with the
    error swallowed was reported FAILED, naming `query1.finance.yahoo.com (curl_cffi GET)`. A
    backstop below the boundary, on libcurl's `perform`, was never reached.
- **Working directory.** `pytest_runtest_setup` moves each test into a fresh, seeded, empty
  directory. The application's runtime paths are relative (`settings.*_DIR`, module constants),
  so they land there.
  - `grep` finds exactly one application path anchored at the checkout,
    `server.py:298` (N2, routed to SA-029). `api_worker_app` stubs it.
  - The parquet store uses the relative `DISCOVERY_BHAVCOPY_DIR`. No SQLite `file:` URI exists in
    the application.
- **Swallowed refusals.** `pytest_runtest_makereport` turns any recorded refusal into a failure of
  that phase. The implementer's child-session test shows it end to end, and so do P1 and P3.
- **Background threads (P3).** A daemon thread that makes its attempt after its test ended is
  refused. The attempt is charged to the test running at that moment, labelled
  `(thread late-probe)`. It is loud but misattributed; the receipt describes this (I1).
- **D1–D9.** Each was checked, and the review agrees with each:
  - **D3:** no TypeScript client is tracked; `config.yaml` has shipped `180` since `1b5fe27`
    (2026-07-06); the frontend sets no analysis timeout. No live consumer was found.
  - **D4:** on Linux `_REPLACE_RETRY_DELAYS == ()`, so `replace_with_retry` is exactly one
    `os.replace`. Production behaviour is unchanged. The three call sites keep their own error
    handling.
  - **D8:** every test that enters the lifespan (3) uses `api_worker_app`, and the two stubs match
    the lifespan's two side effects (`server.py:360-362`).
- **Stubs added to tests.** Each returns the application's own failure answer:
  - `ThesisReviewer` returns an intact thesis with multiplier 1.0 on an LLM failure
    (`thesis_reviewer.py:208`, `:272`);
  - `RegimeDetector._get_5d_pct` / `_get_last_session_pct` return `None`;
  - `ui_data._fetch_yf_price` returns `(0.0, 0.0)`;
  - `analysis_logger._fetch_price` returns `{}`;
  - `symbol_resolver._india_candidates` returns `[]`.

  None is a success fixture that the application could not produce.
- **Assertions.** Three were removed:
  - the D3 contract test (justified above);
  - `n_entries > 0` and the mtime comparison in `test_harness.py`. Both are replaced by stronger
    ones: an exact count derived from what the test wrote, the exact ticker and sector sets, and a
    byte digest.

  One assertion got stronger: the outbox test now pins the recipient. No test was newly skipped
  or marked xfail. The 12 skips predate the change.
- **CI.** Checked the workflow's own properties:
  - `permissions: contents: read`, no secrets, no `pull_request_target`,
    `persist-credentials: false`;
  - **the action pins are the upstream tags' commits.** `git ls-remote` on 2026-09-28 gave the
    pinned SHAs for `actions/checkout` v7.0.1, `actions/setup-python` v7.0.0 and
    `actions/setup-node` v7.0.0. They are not commits reachable only through a fork;
  - `requirements.txt`'s `pytest>=8.0.0` and `pytest-asyncio>=0.23.0` admit the pinned 9.0.3 and
    1.3.0.
- **Python 3.11.** None is installed here. `ast.parse(feature_version=(3, 11))`, the receipt's
  check, does not reject PEP 701 f-strings. So the reviewer tokenized all 730 tracked and new
  `.py` files, looking for:
  - quotes reused inside an f-string's expression;
  - backslashes, comments or newlines there;
  - a list of 3.12-only standard-library calls.

  It found none; the only hits were `email.message.walk()`, which is fine on 3.11. Behaviour on
  Linux / 3.11 still awaits CI.

## Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (reproduced) | `tests/hermetic.py:1-30` (docstring), `:117-156`, `:227-283`; KT §13; `tests/TEST_DOCUMENTATION.md` rule 4 | Probes P2, P4, P5, P7 below | Documentation corrected in this review; the docstring and optional hardening are routed to [SA-031](../stories/SA-031.md) |
| L2 | Low (reproduced) | `scripts/ci/check_broad_except.py:94-100` (`_record` keys) | Probe below | Documented in the KT in this review; routed to [SA-031](../stories/SA-031.md) |
| I1 | Info | `tests/hermetic.py:93`, `:99-106` | P3 | None. A late thread's attempt is refused and fails a test, labelled with the thread's name, but it is charged to whichever test is running. |
| I2 | Info | implementation receipt, "Final, fresh git checkout" | `tempfile.gettempdir()` here is `C:\Users\REVANP~1\…` | None. The implementer's fresh copy ran under the 8.3 temp spelling, where L1's short-name gap applies to paths built from `__file__`. The reviewer's fresh copy ran from the long path (below), with the same result. |

**L1: the boundary's reach is Python-level; the docs said "any access".** The reviewer's probes
ran in a child pytest session with `-p tests.hermetic`. Backstops sat below the boundary, so a
gap was caught before any real I/O:

- **P2:** `asyncio.open_connection("203.0.113.10", 443)` on Windows' default proactor loop. The
  backstop on `IocpProactor.connect` was hit, and the boundary recorded 0 attempts. `ConnectEx`
  is C-level, and a numeric IP skips `getaddrinfo`. A hostname still goes through the guarded
  `getaddrinfo`, and Linux (CI, production) uses the selector loop, which calls the patched
  `connect`.
- **P4:** reading the checkout's `data/nse/key_registry.json` through the 8.3 short spelling, and
  through the `\\?\` spelling, both succeeded (13,159 bytes) and were not refused. The docstring
  says "whatever path spelling reached it".
- **P5:** `os.listdir` of the checkout's `data/` (34 entries) and `.exists()` are not refused: they
  raise no audit event. `pyarrow.parquet.read_table` read a checkout bhavcopy file (2,698 rows),
  because native file I/O raises no audit event.
- **P7:** `sqlite3.connect("file:<checkout>/data/…?mode=ro", uri=True)` was allowed:
  `_checkout_path` skips `file:` strings.

**Impact today: none found.** The application builds one absolute checkout path (N2), which the
fixture stubs. It has no SQLite URI and no numeric-IP async connection, and its parquet paths are
relative. The risk is a future test or module that builds a checkout path and gets a silent read
instead of a loud failure. **Fix in this review:** one sentence each in KT §13 and
`TEST_DOCUMENTATION.md` states the reach. **Routed:**

- correct the docstring phrase;
- optionally, have `_checkout_path` expand `\\?\` and short names (`GetLongPathNameW`) and parse
  `file:` URIs;
- optionally, guard `BaseProactorEventLoop.sock_connect`.

**L2: a fix and a new swallow in the same function cancel out.** Keys are
`path | function | #ordinal` over silent handlers only. Take a `sync()` with one grandfathered
silent handler (`#0`). Add logging to it and a new silent `except Exception: pass` in the same
function: the key set is unchanged, `{core/x.py | sync | #0}`, so the check passes. The script's
docstring says a new swallow trips it. The diff still shows the change to a human reviewer, and
the acceptance criterion's "changed-code guard" holds for every other shape. The unit tests cover
additions, re-ordering, moves and fixes. The reviewer's mutation X4 (any call counts as handling)
is caught only indirectly, through the real tree's baseline. **Routed:** add a fingerprint of the handler (for example, its
normalized body or `except` line) to the key, or record per-function counts together with
fingerprints. Also add a direct case that a non-logging call, such as `cleanup()`, is still a
swallow.

## Tests would fail for the original defect

Run in the reviewer's fresh copy (below). Each mutation restores the file afterwards; the copy's
`git status` was clean at the end.

| ID | Defect put back | Tests run | Result |
|---|---|---|---|
| X1 | the checkout guard ignores `sqlite3.connect` | `test_hermetic_boundary.py` | 1 failed (the runtime-dirs test) |
| X3 | `CONFIG_FILE` dropped from `EXTRA_APP_ENV` | the env-completeness test | 1 failed: the source scan finds it |
| X4 | the guard counts any call in a handler as handling | `test_broad_except_guard.py` | 1 failed: only `test_real_tree_matches_its_baseline`. No snippet case has a non-logging call such as `cleanup()` in a handler, so this weakening is caught indirectly, by the real tree's baseline going stale. It is worth one direct case when L2 is fixed. |
| X5 | **the original F22 defect:** `test_harness.py` at `7901f35`, in the fresh copy without MARUTI data | `test_harness.py` | 1 failed: `test_real_eval_discovers_maruti_data` |
| X6 | **the original F5 defect:** `test_atlas_outbox.py` at `7901f35` (ambient `DELIVERY_EMAIL_TO`) | `test_atlas_outbox.py` | 2 failed: the two outbox tests the card names |
| X9 | `api_worker_app` without the calendar stub | `test_phase2_api.py`, `test_analyse_auth_quota_dedup.py` | 42 errors, 9 passed. The message names `calendar_updater.py:67 in _fetch_from_nse_api` → `www.nseindia.com:443`, and a yfinance fallback, on the lifespan's thread. |

The implementer's 12 mutations (M1–M12) were not re-run; the reviewer's X-series is independent of
them. The `curl_cffi` guard was exercised safely by P1 instead, with the libcurl backstop.

## Commands, environment and results

Windows 11, Python 3.13.11 (`.stockai`), pytest 9.0.3, python-dotenv 1.2.2, curl_cffi 0.15.0.
Reviewer scripts are in the session scratchpad (not tracked).

| Run | Command | Result |
|---|---|---|
| Input | `verify_input.py`; `kt_manifest.py verify SA-005-manifest.json` | 51 files, 0 mismatches; digests as above |
| Action pins | `git ls-remote https://github.com/actions/<name> refs/tags/<tag>` | all three match |
| 3.11 syntax/API scan | `py311_scan.py` (tokenizer) over 730 files | 0 PEP 701 constructs; 3 false positives (`email` `walk()`) |
| Probes | `pytest -q -s -p no:cacheprovider -p tests.hermetic test_review_probes.py` (scratchpad, `PYTHONPATH=<repo>;<repo>/src`) | P1 and P3b FAILED as designed; P2, P4, P5, P7 show L1; P6 passed |
| Full suite, owner's checkout (`.env` present) | `python -m pytest -q -p no:cacheprovider -rfEs tests` | **3800 passed, 12 skipped, 0 failed** in 5 min 14 s. `data/`, `logs/`, `outputs/`: 800 files before and after, **0 changed, added or removed** (size and mtime of every file) |
| Full suite, reviewer's fresh copy | `git archive 7901f35` + the 51 manifest files, `git init` + commit (tracked key registry forced), run from `C:\Users\RevanParimi\AppData\Local\Temp\sa005-review-fresh` (long path); `python -m pytest -p no:cacheprovider -rfEs tests` | **3799 passed, 13 skipped, 0 failed** in 4 min 13 s (the 13th skip: the browser suite, no `node_modules`). Header: `hermetic: .env disabled; 0 application env var(s) removed; …`. Afterwards `git status` was empty, `data/` held only the tracked key registry, and `logs/` and `outputs/` did not exist |
| Mutations | `mutate_review.py` in the fresh copy (X1, X3, X4, X5, X6, X9) | 6 of 6 caught; the copy was clean afterwards |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK, 154 grandfathered |
| L2 probe | `swap_probe.py` (`scan_source` on two snippets) | the key sets are identical, so the check passes |
| KT | `python scripts/docs/build_kt_pdf.py`; `python scripts/docs/check_kt_docs.py` | before the review edit: 0 errors. After the review edits: PDF rebuilt, 25 pages, source `f407a930…`; 0 errors |

**Not exercised:**

- the GitHub workflow itself (no push; no local runner, since there is no Docker);
- Linux and Python 3.11 at runtime;
- the browser job's `npx playwright install --with-deps` on Ubuntu;
- a pinned-date run (routed to SA-012 by the implementation).

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| Full suite runs without `.env`, production volume or untracked market files | **Met locally.** Two full runs, above: the owner's checkout (`.env` present but ignored, runtime directories untouched) and a fresh copy (no `.env`, no untracked files). Linux / 3.11 awaits CI. |
| The MARUTI discovery test proves discovery using a test-created fixture | **Met.** The expected values are counted from what the test writes, not from the harness. The test covers an orphan log, an empty log and stray files. X5: the baseline version fails in a fresh copy. |
| CI runs unit/integration checks and a changed-code guard against unlogged broad swallowing; existing boundaries explicitly allowlisted | **Met in code, not yet run.** The workflow runs the whole tree, the guard and the browser suite with least privilege. The allowlist is explicit and labelled a burn-down, not a review. L2 is a narrow blind spot. The first GitHub run is pending. |
| Card evidence: outbound transport rejected | **Met.** The implementer's tests, and P1 through yfinance's real path. |
| Card evidence: parquet/NSE extras and file-replace on supported environments | **Met on Windows / 3.13** (pyarrow 24.0.0, nse 2.1.3; the three rename flakes absent in both full runs). Linux awaits CI. |
| Hard review: no skip/xfail conversion hides a defect; fixture realism; CI secret permissions | **Met.** No new skip or xfail; the stubs return the application's own failure answers; no secrets in CI. |

## Review edits (documentation only)

- `docs/TECHNICAL_DESIGN.md` §13, two additions:
  - a short passage on the boundary's reach (L1);
  - one sentence on the broad-except key's blind spot (L2).
- The KT's SA-005 status wording (§1, §10, §12 and the §13 heading): "accepted, not yet
  committed", with the review linked in §1.
- `docs/StockAgent-Three-Loops.pdf` rebuilt (source `f407a930…`).
- `tests/TEST_DOCUMENTATION.md`, rule 4: the hook's reach, and "build paths from the working
  directory or `tmp_path`" (L1).
- [SA-031](../stories/SA-031.md): a routed-input section for L1 and L2.
- Nothing else changed: the code, tests, CI and tooling bytes are as reviewed. So
  `kt_manifest.py verify SA-005-manifest.json` now mismatches exactly these four files.

## Decision and follow-up state

- **Accepted** for review input `ef0e3a31…` (diff `7274a199…`), plus the three documentation edits
  above. SA-005 is `done`.
- `production_verification`: `pending_deployment`. There is no runtime change on Linux. What
  remains is the workflow's first GitHub run after the owner's push: read the Actions page and
  record the three jobs (human case 12-E). The witnessed drill 12-F follows once CI is green.
- **Follow-ups:**
  - L1 and L2 → [SA-031](../stories/SA-031.md);
  - I1 and I2: none.
- **Not committed, pushed or deployed** by this review. The commit and the push wait for the owner.
  Any push redeploys production, so use a safe window.
