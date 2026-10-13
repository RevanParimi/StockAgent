# FIX-007 — implementation receipt

**Story:** [FIX-007](../stories/FIX-007.md) · **Phase:** implementation, with same-conversation
self-review only · **Date:** 2026-10-12, about 14:06–15:00 IST · **Baseline:** `b9cc851`
(`b9cc851f04f8f7c6e9dde77f513778c5137354e2`) plus SA-011's accepted, uncommitted worktree
(review input `0323f2a8`) · **Status after this phase:** `review_required`

## How this phase came about

A new conversation opened with "continue". SA-011 was accepted at about 08:35 IST, and FIX-007
was STATE's `next_task`: the first planned `todo` story with no dependencies, placed first in the
product block. No production state was read, nothing was committed, pushed or deployed, and no
production variable was changed. All 35 peer sessions were idle at the start.

## What changed

**Before.** `GET /ui/logs` and `GET /ui/logs/stream` (`services/api/routes/ui_data.py`) took no
user, and the router has no dependency of its own. Anyone with the URL could read up to 1,000
recent log lines and follow new ones live. The ring buffer (`services/api/log_buffer.py`) redacts
nothing, and log lines carry user ids, per-user trade activity and error text.

**After.**

- **Server.** Both routes take `_owner: dict = Depends(require_owner)`: the owner's session or the
  exact `SCHEDULER_KEY` header, the same function every other operator route uses. A member gets
  403 and a caller without a session 401. FastAPI resolves the dependency before it calls the
  handler, so a refused request never reads the buffer, and a refused stream never subscribes,
  starts its generator or sends a line. With `AUTH_REQUIRED` off, `require_owner` treats every
  anonymous request as the owner, here as on every owner route; a member's session is still
  refused (403) and an invalid token still 401s.
- **Logs screen** (`src/frontend/prototypes/logs.jsx`). A browser `EventSource` cannot send an
  `Authorization` header, so the owner's screen would have been refused too. The screen now reads
  the stream with `fetch` and a `ReadableStream` reader, the pattern chat already uses
  (`sphere.jsx`). `index.html`'s global wrapper adds the session header. On 401 or 403 the screen
  shows a plain message, sets the status to `refused` and stops; it does not retry every 5 s.
  Any other failure still reconnects after 5 s. Leaving the screen aborts the request.
  - 403: "Server logs are visible to the owner account only."
  - 401: "Sign in with the owner account to see server logs."
- **Key prompt** (`src/frontend/prototypes/index.html`). The wrapper turns every same-origin 403
  into "This action needs the API key" (`window.prompt`). A request can now opt out with
  `{ saNoKeyPrompt: true }`; only the Logs stream does. A member's 403 there means "not the
  owner", and a member has no key to type.
- Hiding the Logs nav chip from members is PR-001's (acceptance 3 says so).

**Example.** A member signed in on the app opens `/ui/logs?limit=1000`.

| | Before | After |
|---|---|---|
| Member, direct URL | 200 with up to 1,000 lines | 403 `{"detail": "Owner only."}` |
| No session, `AUTH_REQUIRED` on | 200 with the lines | 401 `{"detail": "Login required."}` |
| Member on the Logs screen | live lines | "Server logs are visible to the owner account only.", no key prompt |
| Owner on the Logs screen | live lines (no header sent; open route) | live lines (session header sent) |
| Machine key | 200 | 200 |

## Invariant tests

**Server:** `tests/unit/api/test_log_routes_owner_only_fix007.py`, **42 tests**, through the real
application (`services.api.server.app`: every router and the CORS middleware). A line carrying a
marker string is logged through the real root logger into the real ring buffer (asserted present
first), and spies count every `snapshot` and `subscribe` call.

- **Refusals** (32): four URLs (`/ui/logs`, `/ui/logs?level=DEBUG&limit=1000`, `/ui/logs/stream`,
  `/ui/logs/stream?level=DEBUG`). With `AUTH_REQUIRED` on: anonymous, an invalid token and a wrong
  key get 401; a member, and a member with a wrong key, get 403. With it off: a member, a member
  with a wrong key (403) and an invalid token (401). Each refused response is a JSON body with only
  `detail`, is not an event stream, holds no `data:` line and no marker, the buffer was never read
  or subscribed, and no subscriber was left behind.
- **Single-user mode** (1): with `AUTH_REQUIRED` off, anonymous is the owner (200 with the line), as
  `require_owner` defines. This pins the documented posture; production's protection rests on
  `AUTH_REQUIRED` being on.
- **Owner and machine key** (8): `/ui/logs` returns the marker line, with `AUTH_REQUIRED` on and off.
  The stream sends the buffered marker line first and then a line logged after the client received
  it (live), in that order; leaving unsubscribes.
- **Inventory** (1): every API route whose handler reads the buffer (`log_buffer` with `snapshot(` or
  `subscribe(`) depends on `require_owner`, and those routes are exactly the two.

A granted stream never ends, and the TestClient waits for a response to end, so every request is
driven as raw ASGI by a client that disconnects once it has what it came for, or after 2 s. A
stream that should have been refused therefore fails the test instead of hanging the suite (the
first version used the TestClient for refusals and hung on the ungated baseline; rewritten).

**Browser:** `tests/frontend/logs_screen.test.mjs`, **3 tests**, in Chromium with no network,
mounting the real `LogsPage` under `index.html`'s own head, so the real fetch wrapper runs. Only
`/ui/logs/stream` is replaced, underneath the wrapper, and records what the wrapper sent.

- A member (403): the owner-only message, the status `refused`, the member's session header was
  sent, no dialog of any kind, and one request in 6 s (no reconnect).
- No session (401): the sign-in message, no header, no dialog.
- The owner (200, stream left open): the line is shown, the status is `live`, the owner's session
  header was sent, no refusal, no dialog and no `EventSource` request.

`npm run test:frontend` now runs both browser files. The harness constants it shares with
`chat_harness.mjs` are exported from there (four `export` keywords, no behaviour change).

**Mutations** (in memory; repo files never written):

| Variant (server: `analysis_data/fix007/swap_plugin.py`, `FIX007_SWAP`) | 42 server tests |
|---|---|
| None (the change as written) | 42 passed |
| `base`: both routes as at `b9cc851`, no gate | **caught:** 33 failed |
| M1: `/ui/logs` gated, stream open | **caught:** 17 failed |
| M2: gated with `get_current_user` (any signed-in member) | **caught:** 19 failed |
| M3: gated with `get_current_user_or_machine` | **caught:** 17 failed |
| M4: stream checks the owner inside the generator, after the history flush | **caught:** 21 failed |
| M5: stream gated only when `AUTH_REQUIRED` is on | **caught:** 7 failed |
| M6: gated by the machine key alone (owner session refused) | **caught:** 22 failed |

| Variant (browser: `analysis_data/fix007/fe_variants.sh`, `SA_FRONTEND_ROOT`) | 3 browser tests |
|---|---|
| None | 3 passed |
| `base`: `logs.jsx` and `index.html` as at `b9cc851` (`EventSource`) | **caught:** 3 failed |
| F1: new screen, wrapper without the opt-out | **caught:** 1 failed (the key prompt opens) |
| F2: a refusal is treated as any error (retry, no message) | **caught:** 2 failed |
| F3: the refusal message is never rendered | **caught:** 2 failed |

## Commands and environment

Windows 11, Python 3.13.11, pytest 9.0.3, the project's `.stockai` virtual environment; every
Python run passes through `tests/hermetic.py`. Node with Playwright's Chromium for the browser
tests.

- `python -m pytest tests/unit/api/test_log_routes_owner_only_fix007.py -q -p no:cacheprovider`
  → 42 passed (about 11 s).
- Server mutants: `FIX007_SWAP=<variant> PYTHONPATH=analysis_data/fix007 python -m pytest
  tests/unit/api/test_log_routes_owner_only_fix007.py -q -p no:cacheprovider -p swap_plugin`.
- `npm run test:frontend` → **17 passed** (14 chat, 3 logs).
- Browser variants: `bash analysis_data/fix007/fe_variants.sh`, then
  `SA_FRONTEND_ROOT=<abs path>/analysis_data/fix007/fe/<variant> node --test
  tests/frontend/logs_screen.test.mjs`.
- Neighbours: `tests/unit/api`, `test_api_auth_lockdown.py`, `test_chat_markdown_boundary.py`,
  `test_spa_catchall.py` → **122 passed**.
- Full suite: `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count`, run
  twice:
  - first run: 4470 passed, 12 skipped, **1 failed** (9 min 34 s). The failure was
    `tests/unit/ipo/test_ipo_verdicts_store.py::test_prune_keeps_a_row_whose_timestamp_cannot_be_parsed`:
    `PermissionError: [WinError 5] Access is denied` when `IpoVerdictStore` replaced its `.tmp`
    file with the `.jsonl` (`core/ipo/verdicts.py`, `tmp.replace`). Its file passed 23 of 23 alone,
    and it imports nothing FIX-007 changed: the Windows rename flake class already routed to SA-031;
  - second run: **4471 passed, 12 skipped, 0 failed** (12 min 43 s).
- Runtime data: SHA-256 over `sha256sum` of every file under `data/`, `logs/` and `outputs/`
  (sorted paths): `798 files 6856c417…` before the first run, after it, and after the second.
- Docs: KT PDF rebuilt (source `ce490484a1d154efc7495035af8a4cd8bee77524a2d9256305c9c567cf0541bc`,
  389,430 bytes); `check_kt_docs` errors `[]`.

## Documentation

- [KT](../../../TECHNICAL_DESIGN.md) section 10, "Interface and chat rendering": the log routes
  as current design (gate, refusal before any read, `AUTH_REQUIRED` off, the screen's `fetch`
  reader and message); "owner-only logs (FIX-007)" removed from its Planned list. Section 12: the
  fixes outside the SA numbering now include FIX-007. Its roadmap row stays `Open` until the
  commit, as SA-011's did. PDF rebuilt.
- [PRODUCT_MAP](../../../PRODUCT_MAP.md): section 14.1's log-buffer row; section 16 gains
  "Server logs".
- [CODEBASE](../../../../CODEBASE.md): the route table's auth column (was "None") and the module
  table.
- [Testing guide](../../../TEAM_TESTING_GUIDE.md) case **11-G**; HT-11's related PI list.

## Manifest and digest

- **Review input:** [FIX-007-manifest.json](FIX-007-manifest.json), 13 files. The SHA-256 of its
  LF bytes is **`ff6001e76333439d271d843d76e764aed173eae46dc1056de04c2bd4c0aa8411`**, and
  `kt_manifest.py verify` gives 0 mismatches.
  - Files: `ui_data.py`, `log_buffer.py`, `logs.jsx`, `index.html`, the two new test files,
    `chat_harness.mjs`, `package.json`, the KT and its PDF, PRODUCT_MAP, CODEBASE and the guide.
  - Excluded: STATE, HANDOFF and this receipt (bookkeeping).
  - CODEBASE, PRODUCT_MAP, the KT, the guide and the PDF also carry SA-011's accepted,
    uncommitted changes (and the peer's product-results edits that SA-011's input already held).
- **Diff digest:** **`910503e2b17cf51fb7f502b59cfe77c2107561540fbee891a86de020ab9b2113`**, 42,278
  bytes over 12 paths (every manifest path except the PDF).
  - **The base** is the worktree just before FIX-007. `analysis_data/fix007/base_snapshot.py`
    rebuilds it under `analysis_data/fix007/base/`: the four docs SA-011 touched by undoing
    FIX-007's exact edits, each proved to reproduce SA-011's accepted blob id (CODEBASE `f9bf175c`,
    PRODUCT_MAP `5e0e6161`, KT `88238a78`, guide `58fd754e`); the six other changed files from
    `b9cc851`, which SA-011 never touched. So these diffs hold FIX-007's changes and nothing else.
  - **To rebuild:** `analysis_data/fix007/diff_digest.py` runs `git diff --no-index --no-color`
    from `analysis_data/fix007/base/PATH` (or `/dev/null` for the two new test files) to `PATH`
    over the sorted paths and concatenates the outputs. A reviewer without that ignored folder
    can rebuild the base the same way from the SA-011 manifest's blob ids and `b9cc851`.

## Self-review

No critical, high or medium finding. Most severe first:

- **I1 (info, owner check at rollout). `AUTH_REQUIRED` decides anonymous access.** With it off,
  every anonymous request acts as the owner on every owner route, logs included; that is
  `require_owner`'s defined single-user mode, and the card keeps it. Production's value was not
  read. The rollout check (an anonymous `GET /ui/logs` returns 401) settles it: a 200 there means
  `AUTH_REQUIRED` is off, which exposes far more than logs.
- **I2 (info). The first load after the deploy.** The service worker serves static files
  stale-while-revalidate, so the first visit after the deploy may still run the cached
  `EventSource` screen: with `AUTH_REQUIRED` on, the owner sees `error` and retries until a
  reload. One reload fixes it. The worker's version was not bumped: a bump takes effect on the
  same next load, so it would not help.
- **I3 (info). Log redaction** is not done; the card puts it out of scope once the routes are
  owner-only.
- **I4 (info). Members still see the Logs chip** until PR-001 hides it; they now get the message.
- **I5 (info). A reconnect replays the history** (up to 500 lines), so a dropped stream shows some
  lines twice, as `EventSource` did before.
- **I6 (info). A stream's reader thread** parks on its queue for up to 30 s after the client
  leaves (unchanged): `asyncio.to_thread(q.get, True, 30.0)` cannot be cancelled. Unsubscribe
  happens at once.

## Production check (after an owner-authorized deploy, read-only)

1. Without a session: `GET <app URL>/ui/logs?limit=1` returns 401 with only `detail`. A 200 with
   entries means `AUTH_REQUIRED` is off (I1): report it to the owner.
2. The owner opens the Logs screen (after one reload, I2) and sees lines arriving, status `live`.
3. If the test member account is available: the screen shows the owner-only message and no key
   prompt; the direct URL returns 403.

Rollback is a revert. This receipt does not authorize deploying, pushing or changing production
variables.

## Next

A fresh-session review in a new conversation ("continue"), by [REVIEW.md](../REVIEW.md). Then
PR-001.
