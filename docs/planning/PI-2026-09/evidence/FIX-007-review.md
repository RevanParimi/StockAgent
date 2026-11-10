# FIX-007 review receipt — server logs are readable only by the owner

## Fresh-session review: ACCEPTED (2026-10-13)

**Context:** a fresh-session review in a new conversation opened with "continue" (12 Oct about
23:17 IST to 13 Oct about 00:20 IST). It is not the implementing conversation. All 36 peer
sessions were idle at the start. Nothing was committed, pushed, deployed or configured, and no
production state was read.

**Story:** [FIX-007](../stories/FIX-007.md). **Reviewed input:**
[FIX-007-manifest.json](FIX-007-manifest.json) `ff6001e76333439d271d843d76e764aed173eae46dc1056de04c2bd4c0aa8411`
(13 files) and diff `910503e2b17cf51fb7f502b59cfe77c2107561540fbee891a86de020ab9b2113` (42,278
bytes, 12 paths). The baseline is `b9cc851` plus SA-011's accepted, uncommitted worktree (input
`0323f2a8`). The review made two documentation edits, listed under "Review edits".

**In one example.** A member is signed in on the app.

- **On the Logs screen**, the screen's own request carries the member's session and gets 403.
  - The screen says "Server logs are visible to the owner account only." It opens no API-key
    prompt and makes one request in 6.5 seconds.
  - The server never read the log buffer or subscribed to it.
- **From the address bar**, `/ui/logs?limit=1000` gets 401. A typed URL sends no session, even
  from a signed-in browser. The testing guide expected 403 here; this review corrected it (L1).
- **The owner** sees the buffered lines, then live ones. On leaving the screen, the server
  releases the stream within 2 seconds, while the page is still open.

### Review input verified

- **At the start:** the manifest's LF bytes hash to `ff6001e7…`, and `kt_manifest.py verify`
  gives 0 mismatches over 13 files.
- **Own verifier** (`analysis_data/fix007/review/rv_verify.py`):
  - The implementer's base snapshot is proved by blob ids computed in Python, not by their
    script:
    - the four docs equal SA-011's accepted blobs: CODEBASE `f9bf175c`, PRODUCT_MAP
      `5e0e6161`, KT `88238a78`, guide `58fd754e`;
    - the six code and test files equal `b9cc851`'s blobs;
    - the two new test files did not exist before.
  - SA-011's eight other accepted files are unchanged in the worktree.
  - Only one worktree change falls outside both manifests and the planning/audit docs:
    `docs/README.md`. It holds 3 added lines, the owner's own probe command from 12 Oct, and is
    not part of this story.
  - The diff, rebuilt from that base, is `910503e2…`, 42,278 bytes, and matches the receipt.
- **At the end:** `verify` mismatches exactly `CODEBASE.md` and `docs/TEAM_TESTING_GUIDE.md`,
  this review's two edits. Every code and test file still has its reviewed bytes.

### Contract checked

The card's five acceptance criteria and its three hard-review items:

- **Every reader of the buffer or the log files.**
  - Only `get_logs` and `stream_logs` read the ring buffer (`services/api/routes/ui_data.py:3783-3831`).
    The other `log_buffer` imports use its managed-ticker helpers.
  - The durable `app_logs` table is read only by SA-011's `/ops/*` routes, each with
    `require_owner` (`ops_api.py:44`, `:54`, `:77`), and by scripts.
  - Only two logging handlers exist, `RingBufferHandler` and `SQLiteLogHandler`. No other route
    or WebSocket relays log records.
  - The UI router is included once (`server.py:476`). No page or script calls `/ui/logs` except
    `logs.jsx`.
- **The stream cannot send before the check.** FastAPI resolves `Depends(require_owner)` before
  it calls the endpoint, and `generate()` is created inside the endpoint. Over real HTTP, every
  refused request left the buffer unread and unsubscribed (spies), and the subscriber count
  unchanged.
- **The machine-key path** is `require_owner` itself (`services/api/auth.py:164-180`), the
  function every operator route uses.
- **The service worker** does not intercept `/ui` (`sw.js:30`, `:77`), so the `fetch` stream is
  neither cached nor buffered.
- **Rendering.** A log line is a React text node (`logs.jsx:234`), so markup in a line stays text.
  This matters more now that the screen's only reader is the owner, whose token is in that page.

### Independent adversarial examples

The reviewer's own trace is in the ignored folder `analysis_data/fix007/review/`:

- `test_rv_trace.py` (89 tests), `test_rv_navigate.py` (3) and `test_rv_leave.py` (1);
- `rv_browser.mjs` and `rv_navigate.mjs`.

The setup:

- The real `services.api.server.app` runs on uvicorn 0.46 in a thread, with lifespan off and
  under the suite's hermetic guard. Production also runs uvicorn (`Dockerfile:48`).
- Requests travel over real sockets, with sessions from the real `user_store` in a temporary
  `users.db`.
- Marker lines go through the real root logger into the real ring buffer.
- Expected results come from the card and from `require_owner`'s documented contract.

1. **Refusals over HTTP**, for the 4 URLs. Each refused body is JSON holding only `detail`, is not
   an event stream, and carries no `data:` line and no marker. The buffer was not read or
   subscribed, and the subscriber count did not change.

   | Setting | Caller | Result |
   |---|---|---|
   | `AUTH_REQUIRED` on | anonymous, an invalid token, Basic credentials, a wrong key, an empty key | 401 |
   | `AUTH_REQUIRED` on | a member (also with lower-case `bearer`, also with a wrong key) | 403 |
   | `AUTH_REQUIRED` off | a member, a member with a wrong key | 403 |
   | `AUTH_REQUIRED` off | an invalid token | 401 |
   | `SCHEDULER_KEY` unset | anonymous, a wrong key, an empty key | 401: no key spelling becomes the machine |
   | `SCHEDULER_KEY` unset | a member | 403 |

2. **Readers.** These callers read the marker from `/ui/logs`:
   - the owner, also with lower-case `bearer` and with a stale wrong key;
   - the machine key;
   - a member who also sends the right key. The key is owner-equivalent by design.
3. **The stream**, for the owner and the machine key: the buffered marker arrives first, then a
   line logged after the client received it. When the client leaves, the subscriber is released.
4. **`AUTH_REQUIRED` off, anonymous:** 200. This is `require_owner`'s documented single-user mode
   (card criterion 1).
5. **Other spellings, as anonymous with `AUTH_REQUIRED` on.** 13 spellings and methods: a trailing
   slash, upper-case `UI`, `//`, `/./`, `x/../`, `%2F`, `%6c`, `HEAD` on both routes, `POST`,
   `//ui/logs` and an absolute-form URI. Also a CORS preflight from another origin. None returned
   a line or read the buffer. `%2F` and `%6c` decode to the real routes, and the check refuses
   them there.
6. **The real screen in Chromium.** The page is the real `index.html` head and `logs.jsx`, served
   by that server. `/ui/logs/stream` is not intercepted.
   - **The owner:** buffered and live lines, status `live`, the session header sent, no dialog and
     no `EventSource`. After leaving, there is no new request in 6.5 seconds. Every sample from
     2 seconds after leaving until the page closed shows the subscription released
     (`test_rv_leave.py`).
   - **A member,** with and without a stale wrong `sa_key`: the owner-only message, `refused`, no
     dialog and one request (403). Nothing was read, and the member stays signed in.
   - **No session, or an expired token:** the sign-in message, 401, no dialog. The wrapper drops
     the dead token.
   - **The owner with a stale wrong key:** `live`.
   - **Markup in a line.** A planted line carries `<img src=x onerror=…>` and `<script>…</script>`.
     The owner's screen shows it as literal text: no `<img>` element, and no script ran.
   - **The implementer's I2, confirmed.** The cached pre-fix screen (`EventSource`, proved as
     `b9cc851`'s blob) against the gated server sends no session header and gets 401. It shows
     `error` and retries every 5 seconds, and nothing is read.
   - **The address bar:** a signed-in member's direct visit to either URL gets 401 (L1).

**A correction to the reviewer's own harness, made during the review.** The browser's first
"live line" check could be met by the history flush: the ring buffer still held other tests' live
lines. Its release check also ran after the browser had closed, and closing drops the connection
anyway. It passed alone and failed once when all three files ran together, because the stream
lasted too short a time to be sampled. The final harness (`LivePlanter` in `test_rv_trace.py`)
works differently:

- it waits until the screen's stream is open, and then 0.5 seconds more, so the history snapshot
  is already taken;
- only then does it log a token unique to that run, so the screen must receive that token live;
- it samples the subscriber count every 50 ms and checks the release between leaving and closing
  the page.

The table's "Reviewed", base and F4 results come from this final harness. The M1–M6 runs used only
the HTTP tests, which did not change.

### Tests

| Code | The implementer's 42 server tests | The implementer's 3 browser tests | The reviewer's trace |
|---|---|---|---|
| Reviewed | 42 passed | 3 passed (17 with chat) | 93 passed (three files, one run) |
| Base: both routes as at `b9cc851`, no gate | **caught:** 33 failed (re-run here) | n/a | **caught:** 70 failed, 23 passed |
| Base frontend: `logs.jsx` and `index.html` as at `b9cc851` (proved by blob) | n/a | **caught:** 3 failed (re-run here) | **caught:** I2 scenario (no line shown) |
| M1: `/ui/logs` gated, stream open | caught: 17 failed (their receipt) | n/a | **caught:** 31 failed |
| M2: any signed-in member | caught: 19 failed | n/a | **caught:** 26 failed |
| M3: any session or the key | caught: 17 failed | n/a | **caught:** 24 failed |
| M4: owner checked inside the stream, after the history | caught: 21 failed | n/a | **caught:** 33 failed |
| M5: stream gated only with `AUTH_REQUIRED` on | caught: 7 failed | n/a | **caught:** 6 failed |
| M6: the machine key alone | caught: 22 failed | n/a | **caught:** 41 failed |
| F4 (reviewer's): leaving the screen does not abort the stream | **survives:** 42 passed (server unchanged) | **survives:** 3 passed | **caught:** `test_rv_leave.py` 1 failed |

How the table was produced:

- The reviewer's base and M1–M6 runs used the implementer's in-memory swap
  (`FIX007_SWAP`, `-p swap_plugin`).
- M1–M6 ran over HTTP only (`-k "not browser"`, 82 tests). Base ran all three files.
- F4 is `analysis_data/fix007/review/fe/F4/logs.jsx`: the cleanup's `ctrl.abort();` removed.
- The 23 trace tests that pass on base are expected to pass there. They are the owner and
  machine-key reads (over HTTP and in the browser, including the leave and markup checks), plus
  the bypass probes whose spellings never reach the routes.

**Mocked boundaries.** Neither side calls a real model, SMTP or push transport.

- The implementer's server tests use the real app and the real ring buffer. Their browser test
  replaces only `/ui/logs/stream`, underneath the real wrapper.
- The reviewer's trace replaces nothing on the request path.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (docs; behaviour correct) | `docs/TEAM_TESTING_GUIDE.md:282` (11-G); the implementation receipt's "Production check", step 3 | Both expect 403 when a member opens a log URL directly. A typed URL carries no `Authorization` header: the session lives in `localStorage`, and only `index.html`'s fetch wrapper attaches it. So the member gets 401, the same as anyone without a session. Fixture: `test_rv_navigate.py::test_member_direct_visit_is_401_not_403` (real Chromium, member token stored on the origin, 401 on both URLs; the same member's session on a scripted request gets 403). Impact: a tester, or the owner at rollout, may record a correct 401 as a failure, or think the member check was not done. | **Fixed** in guide 11-G by this review. The rollout check is restated below and in HANDOFF. The implementation receipt is left as the record of what was claimed. |
| L2 | Low (tests; code correct) | `tests/frontend/logs_screen.test.mjs`; `src/frontend/prototypes/logs.jsx:83-88` | No test leaves the screen, but the receipt claims that leaving aborts the stream. Mutant F4 (no `ctrl.abort()`) passes all 3 browser tests and the 42 server tests. With F4, each owner visit keeps one server subscription open until the tab closes: a 500-line queue and a reader thread. No member ever gets a stream, so this is not a privacy defect. The reviewer's `test_rv_leave.py` catches F4. | **Routed** to [SA-031](../stories/SA-031.md), with the fixture. |
| I1 | Info (docs style) | `CODEBASE.md:357` | The route row ended in "(FIX-007)", the only story tag in CODEBASE. The owner's documentation rule keeps story IDs in design docs to **Planned** pointers or evidence links. | **Removed** by this review. |
| I2 | Info (inference from code; not exercised) | `services/api/routes/ui_data.py:3792` | Authorization is checked once per connection. A stream the owner opened keeps flowing after that session is signed out elsewhere, until the connection drops; the reconnect is then refused. Only the owner can open one. | No action. |
| I3 | Info (dated evidence) | production configuration | The 10 Sep audit recorded production `AUTH_REQUIRED=true` and the machine key configured ([audit](../../../audit/2026-09-10-repository-production-review.md), "Identity and tenancy"). This supports the implementer's I1. The rollout check re-confirms it. | Run the rollout check. |
| I4 | Info | `README.md:494-496` | The "Logs Page" paragraph does not say the page is owner-only. It is not wrong. | No card change; SA-031's documentation pass may add it. |

**The implementer's own items:**

- **I1:** see I3.
- **I2:** confirmed in a browser (example 6).
- **I3, redaction:** agreed; it is out of the card's scope.
- **I4, members still see the Logs chip:** agreed. The chip is item 3 of PR-001's card.
- **I5, a reconnect replays the history:** agreed.
- **I6, unsubscribing at once:** confirmed under the real uvicorn. It reports ASGI spec 2.3, so
  Starlette 1.0 cancels the stream on disconnect. The parked reader thread was not measured.

No critical, high or medium finding.

### Decisions

The receipt records no open decision. These choices are upheld:

- With `AUTH_REQUIRED` off, anonymous requests act as the owner (card criterion 1).
- A refusal is final for that visit; reopening the screen tries again.
- The service worker's version is not bumped (I2): one reload replaces the cached screen.

### Commands and results

Environment: Windows 11, the project's `.stockai` virtual environment (Python 3.13.11, uvicorn
0.46.0, Starlette 1.0.0, FastAPI 0.136.1, httpx 0.28.1), SA-005's hermetic guard, and Node with
Playwright's Chromium.

| Check | Command | Result |
|---|---|---|
| Input | `python analysis_data/fix007/review/rv_verify.py`; `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-007-manifest.json` | 0 mismatches at the start; `ff6001e7…`; diff `910503e2…`, 42,278 bytes; base proved by blob ids |
| Story tests | `python -m pytest tests/unit/api/test_log_routes_owner_only_fix007.py -q -p no:cacheprovider` | 42 passed |
| Browser tests | `npm run test:frontend` | 17 passed (14 chat, 3 logs) |
| The implementer's tests on base | `FIX007_SWAP=base PYTHONPATH=analysis_data/fix007 python -m pytest tests/unit/api/test_log_routes_owner_only_fix007.py -p swap_plugin …`; `SA_FRONTEND_ROOT=<abs>/analysis_data/fix007/fe/base node --test tests/frontend/logs_screen.test.mjs` | 33 failed, 9 passed; 3 failed |
| The reviewer's trace | `python -m pytest analysis_data/fix007/review/test_rv_trace.py analysis_data/fix007/review/test_rv_navigate.py analysis_data/fix007/review/test_rv_leave.py --rootdir=analysis_data/fix007/review -q -p no:cacheprovider` | 93 passed (4 min 20 s), all three files in one run |
| Base and mutants on the trace | `FIX007_SWAP=<mode> PYTHONPATH=analysis_data/fix007 python -m pytest analysis_data/fix007/review/test_rv_trace.py --rootdir=analysis_data/fix007/review -p swap_plugin [-k "not browser"]` | The table above: M1–M6 in `review/mutant_runs.txt`, base with the final harness in `review/base_final.txt` |
| F4 | `RV_LOGS_JSX=<abs>/analysis_data/fix007/review/fe/F4/logs.jsx python -m pytest analysis_data/fix007/review/test_rv_leave.py …`; `SA_FRONTEND_ROOT=<abs>/analysis_data/fix007/review/fe/F4 node --test tests/frontend/logs_screen.test.mjs` | 1 failed; 3 passed (survives) |
| Full suite | `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count` | **4471 passed, 12 skipped, 0 failed** (8 min 39 s, about 23:43–23:52 IST), on the first run; the same 4,483 tests as the implementer's runs |
| Runtime data | SHA-256 over `sha256sum` of every file under `data/`, `logs/` and `outputs/`, sorted, before and after the full suite | 798 files, `6856c417…` before and after, equal to the implementer's value |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT and PDF | `check_kt_docs.py` (with `PYTHONPATH=analysis_data/kt_docs_deps`); PDF text search | errors `[]`; the PDF prints source `ce490484a1d1`, 41 pages; it holds the new section 10 text and "Six fixes outside", and no longer holds "Planned: owner-only logs" |

**Not exercised:**

- production, which was not read;
- the real app's navigation to the Logs screen (the harness mounts `LogsPage` directly) and an
  installed service worker (blocked; its `/ui` exclusion was checked by reading the code);
- two uvicorn workers, each with its own ring buffer (the check is the same in each);
- a session revoked while a stream is open (I2).

### Review edits (documentation only)

- **Guide 11-G:** the direct-URL expectation (L1); blob `b3f671bd`.
- **`CODEBASE.md:357`:** the "(FIX-007)" tag removed (I1); blob `13feb38a`.
- **The SA-031 card:** L2, with its fixture.
- This receipt, STATE and HANDOFF.
- **Not edited:** the KT, its PDF, PRODUCT_MAP and the implementation receipt. The KT and
  PRODUCT_MAP describe the reviewed behaviour, and the KT's section 12 row stays `Open` until the
  commit, as SA-011's did.

### Acceptance and what remains

| Criterion | Result |
|---|---|
| 1. Both routes depend on `require_owner`; anonymous and member requests are refused, with `AUTH_REQUIRED` on and off as `require_owner` defines | Met: code, examples 1, 2 and 4, M2, M3, M5 and M6 caught |
| 2. The stream refuses before sending any buffered line | Met: examples 1 and 5 (no read, no subscribe), M4 caught |
| 3. The Logs screen handles a refusal with a plain message; PR-001 hides the chip | Met: example 6; the chip is item 3 of PR-001's card |
| 4. Invariant tests through the real HTTP stack, for 4 callers and both routes; no entry and no planted marker in a refused body | Met: the implementer's 42 tests through `server.app`, and this trace over real sockets; L2 adds the leave case |
| 5. Documentation: KT section 10 and PRODUCT_MAP as current design; a human test case | Met: KT sections 10 and 12, with the PDF matching its source; PRODUCT_MAP sections 14.1 and 16; CODEBASE; guide 11-G, corrected here (L1) |

**Production check, after an owner-authorized deploy (read-only, corrected):**

1. **Anonymous request.** Without a session, `GET <app URL>/ui/logs?limit=1` returns 401 with
   only `detail`. A 200 with entries means `AUTH_REQUIRED` is off: report it.
2. **The owner.** Open the Logs screen, reloading once if it shows `error` (I2). Lines arrive and
   the status is `live`.
3. **The test member account.**
   - The Logs screen shows "Server logs are visible to the owner account only." and no key
     prompt. Its request shows 403 in the browser's network panel.
   - A URL typed into the address bar gets 401, as anyone's would.

Rollback is a revert.

## Verdict

**ACCEPTED.**

- **Reviewed revision:** the uncommitted worktree, at review input `ff6001e7…` and diff
  `910503e2…`, with this review's two documentation edits (CODEBASE `13feb38a`, guide
  `b3f671bd`).
- **Status:** FIX-007 is `done`, and its `production_verification` is `pending_deployment`.
- **Next:**
  1. **FIX-008**, implemented in a new conversation ("continue"). It depends on SA-011 (done)
     and is first in STATE order. Then PR-001.
  2. **Commit and push** at the owner's word, in a job-free window (safest 00:10–06:20 IST).
     FIX-007's and SA-011's files are all uncommitted. With the commit:
     - set the KT section 12 rows for SA-011 and FIX-007 from `Open` to `Done`;
     - bump the KT header's revision and rebuild the PDF.
  3. **After the deploy,** run the production check above and SA-011's rollout check.
