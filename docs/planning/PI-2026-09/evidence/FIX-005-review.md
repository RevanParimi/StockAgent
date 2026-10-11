# FIX-005 review receipt — chat's portfolio brief reads only the caller's own portfolio

## Fresh-session review: ACCEPTED (2026-10-11)

- **What was reviewed:** [FIX-005](../stories/FIX-005.md), as described in the
  [implementation receipt](FIX-005-implementation.md), **committed as `954305a`**. It was
  committed and pushed before this review, at the owner's word (a recorded deviation, as for
  FIX-004 change 1).
  - In `services/api/routes/ui_data.py`, both chat routes pass `user["user_id"]` through
    `_execute_chat_tool` and `_dispatch_chat_tool`. The brief tool opens
    `PortfolioStore(user_id)`, refuses a missing or invalid id, and answers "No brief yet"
    without creating a folder for a user who has none.
  - The change adds 51 tests, adjusts one, and edits CHAT_ARCHITECTURE, KT sections 10 and 12
    (PDF rebuilt), PRODUCT_MAP section 16, guide case 11-F and the card.
- **Context:** a fresh-session review in a new conversation opened with "continue", 11 Oct 2026,
  from about 08:23 IST.
  - It is not the conversation that implemented FIX-005, and it did not read that chat.
  - It read the card, the receipt, the commit's diff, both chat routes, the auth dependency,
    the user store and signup, `PortfolioStore`, the delivery and portfolio routes, the chat
    session store and the brief job.
  - All 28 peer sessions were idle at the start.
- **Nothing** was committed, pushed, deployed or configured, and no production state was read.

### Review input verified

- The reviewer's own script, `analysis_data/fix005/review/rv_verify.py`, at `954305a`:
  - the manifest's LF SHA-256 is `82d6c89c…`, as recorded;
  - all 9 paths match by git blob id and by SHA-256: 0 mismatches;
  - the diff `04ee080..954305a`, rebuilt commit to commit over the 8 non-PDF paths, is 27,443
    bytes with SHA-256 `e28f1e61…`, as recorded;
  - the working tree's `ui_data.py` and both test files equal the commit's bytes.
- `kt_manifest.py verify FIX-005-manifest.json --rev 954305a`: 0 mismatches.
- The KT bump that followed, `304dcff`, changes 10 documentation files and no code.

### Contract checked

- **Where the identity comes from.** Both chat routes depend on `get_current_user`
  (`ui_data.py:3000`, `:3334`).
  - A bearer token resolves to its users-table row (`user_store.resolve_session`).
  - With no token, `AUTH_REQUIRED` off gives the owner passthrough
    (`PORTFOLIO_DEFAULT_USER_ID`), and `AUTH_REQUIRED` on gives 401.
  - The routes pass `user["user_id"]` to the executor (`:3064-3065`, `:3466-3467`). The
    dispatcher hands it to the brief tool (`:2772`) and ignores the tool's arguments.
- **The same store as the delivery and portfolio routes.** `GET /delivery/brief/latest` opens
  `PortfolioStore(user_id=user["user_id"])` (`delivery_api.py:36`), and `GET /portfolio` the
  same through `_store`. The tool checks the store's own id pattern, `_USER_ID_RE`, but without
  the store's `.strip()`. So it is stricter: `" primary"` is refused, not read as `primary`.
- **The owner is `primary`.** The first signup is created with
  `user_id = PORTFOLIO_DEFAULT_USER_ID` (`auth_api.py`, `signup`), and members get `u_` plus 8 hex
  digits (`user_store.create_user`). A signed-in owner and the passthrough therefore read the same
  folder. This settles the implementer's I1 for an owner account made by signup.
- **No other route to personal data in chat.**
  - Of the 13 tools, only `get_portfolio_brief` reads per-user data.
  - `_build_chat_context` reads no portfolio, watchlist or user data.
  - The pre-router seeds the per-turn cache only with `screen_stocks` and `search_news`.
  - Session history is keyed by `(user_id, session_id)` (`chat_session_store`).
  - The only other caller of `_execute_chat_tool` is `scripts/model_bench.py`. It passes no
    user, so the brief tool refuses there (the implementer's I2).
- **The memo cache** is created inside one turn of the stream (`:3382`); `/ui/chat` uses none. It
  is never shared between requests, so not between users.
- **Storage.** Briefs and digests are files under `PORTFOLIO_DATA_DIR/<user>/`. The brief job
  (`run_morning_brief`) writes each user's brief into that user's store. The tool's folder check
  uses the same root as the store.
- **Not applicable:** horizon, issue-time availability, idempotency and bounded math. The change
  selects which stored file is read and changes no writer.

### Independent adversarial examples

The reviewer's own trace, `analysis_data/fix005/review/test_rv_trace.py` (3 tests), was written
from the card and the code, not from the implementer's tests.

- **The setup.**
  - The real HTTP stack (FastAPI `TestClient`), with real signup, invites and bearer sessions
    in a temporary `users.db` and `atlas.db`.
  - Atlas is **on**. `config.yaml` has `atlas.enabled: true`, and its comment says production
    follows the yaml.
  - `AUTH_REQUIRED` is on, except in test 2.
  - Briefs are written by the real `run_morning_brief`. Only its builder (a marker brief per
    user and date) and its transports are stubbed.
  - The model is stubbed: it asks for `get_portfolio_brief`, then echoes every tool result.
- **Test 1, in production time order:**
  1. **Thu 8 Oct.** The owner signs up (id `primary`) and holds FEDERALBNK. The job writes
     the owner's brief and delivers it to the owner only.
  2. **A member joins by invite** (id `u_` plus 8 hex digits), with no portfolio. On the stream,
     "show my brief" gives "No brief yet". No marker appears anywhere in the event stream, and
     no folder is created.
  3. **Adversarial identity.** The model sends `{"user_id": "primary"}` as the tool's
     arguments, and the request body carries `"user_id": "primary"` on both routes. The member
     still gets none of the owner's data.
  4. `GET /delivery/brief/latest` gives the member 404. As before FIX-005, that route creates the
     member's folder. Chat then still says no brief: the branch with a folder and no brief.
  5. **The owner's reply** on `/ui/chat` is exactly "Your brief:" plus the delivery route's
     text for the same token (first 1,800 characters). The stream carries the same text.
  6. **Fri 9 Oct.** The member now holds TMPV, and the job writes both briefs. Each delivery
     carries its own account's marker. For each account, on both routes, chat equals that
     account's delivery text, also with the other account's id in the body or the tool's
     arguments.
  7. **A second member** with only an EOD digest sees only that digest.
  8. **No token, or a forged one:** 401 on both routes.
- **Test 2.** With `AUTH_REQUIRED` off, anonymous chat gets the owner's brief: the passthrough,
  as for `GET /portfolio`. A member's token still gets only the member's brief.
- **Test 3.** Eight streaming turns of two accounts run interleaved on one event loop (the stub
  yields between rounds). Each stream carries only its caller's marker.

### Tests

- **The implementer's tests are invariant tests.** Each account carries a planted marker
  string, and the assertions check that no other account's marker appears. So the expected
  results do not depend on the changed code.
- **Mocked boundaries.** The model call (`_chat_completion`), the LLM client and the context
  builder are stubbed. The session store is in a temporary directory. SA-005's hermetic guard
  blocks the network. No real transport is reachable.
- **Reviewer mutations.** `rv_swap_plugin.py` loads the baseline source or a mutant into
  `sys.modules` after the hermetic sandbox is set up. Repo files are never written.

| Code | The implementer's 54 tests | The reviewer's trace (3) |
|---|---|---|
| Reviewed (`954305a`) | 54 passed | 3 passed |
| Baseline `04ee080` (the original defect) | **caught:** 51 failed, 3 passed | **caught:** 3 failed (a member receives `primary`'s brief) |
| R1: the tool takes `user_id` from the model's arguments | **survives:** 54 passed | **caught:** 1 failed |
| R2: the memo cache is process-wide | **caught:** 3 failed | **caught:** 3 failed |
| R3: a caller with no folder falls back to the default user | **caught:** 5 failed | **caught:** 1 failed |
| R5a: `/ui/chat` takes `user_id` from the body | **survives:** 54 passed | **caught:** 1 failed |
| R5b: `/ui/chat/stream` takes `user_id` from the body | **survives:** 54 passed | **caught:** 1 failed |

Every failure in the reviewer's trace is the owner's marker reaching another account.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (tests; code correct) | `tests/unit/api/test_chat_brief_user_scope_fix005.py` | No test pins that the identity comes only from the signed-in session. Mutants R1, R5a and R5b pass all 54 tests, because the tests never send a `user_id` in the body or the tool's arguments. A prompt-injected model, or a later change that adds a parameter to the tool, would be the regression. | Routed to the [SA-031 card](../stories/SA-031.md), with the fixture (the trace's step 3). Not blocking: acceptance 5 is met as written. |
| L2 | Low (related; carried from the implementer's L1; owner decision) | `services/api/routes/ui_data.py:1043` | Confirmed by code. With Atlas on and `AUTH_REQUIRED` on, an anonymous `GET /ui/watchlist` reads the default user's watchlist. Atlas is on in `config.yaml`, so this is production's branch. The exposure depends on production's `AUTH_REQUIRED`, which this review did not read. It exposes a symbol list, not values or verdicts. PRODUCT_MAP section 16 records it. | Owner to route, for example as a FIX card. |
| I1 | Info (production data) | `services/data/stores/chat_session_store.py`; `services/api/server.py:382-388` | Session turns, the assistant's replies included, are kept in the volume-backed `chat_sessions.db`. A brief that a member received before the deploy stays in that member's own history and is replayed into later turns of that session. It is never served to another account. The sweep runs only at startup and deletes turns older than 7 days (`SESSION_TTL_DAYS`). | Added to the production check. If a member asked for a brief before 08:16 IST on 11 Oct, the owner may let those turns age out or authorize a purge, which is a production data change. |
| I2 | Info | implementation receipt, I1 | The owner made by signup is `primary` (above), so the owner's chat and portfolio screen read the owner's own brief. | No action. |

No critical, high or medium finding.

### Decisions

The receipt records no open decision. The design choices are upheld: the default argument is
`None`, so a caller that forgets the user is refused; the refusal is a reply, not an error; and the
folder check comes before the store is built, so a read creates nothing.

### Commands and results

Environment: Windows 11, the project's `.stockai` virtual environment (Python 3.13), with
SA-005's hermetic guard.

| Check | Command | Result |
|---|---|---|
| Input | `python analysis_data/fix005/review/rv_verify.py 954305a`; `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-005-manifest.json --rev 954305a` | 0 mismatches; `82d6c89c…`; diff `e28f1e61…`, 27,443 bytes |
| The reviewer's trace | `python -m pytest analysis_data/fix005/review/test_rv_trace.py -q -p no:cacheprovider` | 3 passed |
| Baseline and mutations | `python analysis_data/fix005/review/run_rv_mutants.py` (`RV_MODE=<mode>`, `-p rv_swap_plugin`) | The table above |
| Full suite | `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count` | **4318 passed, 12 skipped, 0 failed** (9 min 45 s, about 08:40–08:50 IST), on the first run |
| Runtime data | `python analysis_data/fix005/review/rv_tree.py`, before and after the full suite | 800 files, `88a644fc…` before and after (path, size, modification time and bytes) |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT and PDF | `rc_pdf_pair.py` on the committed pairs; `check_kt_docs.py` (with `PYTHONPATH=analysis_data/kt_docs_deps`) | `954305a`: PDF `f140b2b7` prints source `55d6c82f`, 37 pages; `304dcff`: `4dd74511` prints `971daaec`, 37 pages; no chapter missing. Working tree: errors `[]` |

**Not exercised:**

- a real model: a prompt-injected model is simulated by the stub's tool arguments;
- the frontend's rendering of the tool trace, and a browser;
- the Atlas-off watchlist branch (the legacy global list);
- production, which was not read.

### Review edits (documentation only)

- **Guide 11-F:** the status line.
- **The SA-031 card:** L1, with its fixture.
- This receipt, STATE and HANDOFF.
- **Not edited:** the KT, its PDF, CHAT_ARCHITECTURE and PRODUCT_MAP. They describe the reviewed
  behaviour, and the KT body carries no review status.
- `verify FIX-005-manifest.json` on the working tree mismatches exactly the five manifest paths
  the KT bump `304dcff` changed: the KT, its PDF, CHAT_ARCHITECTURE, PRODUCT_MAP and the guide,
  which this review edits again. `--rev 954305a` is unaffected.

### Acceptance and what remains

| Criterion | Result |
|---|---|
| 1. Both routes pass the caller; the tool opens only that store, the same as `GET /portfolio` and `GET /delivery/brief/latest` | Met (contract; trace steps 5 and 6: chat equals the delivery text for the same token) |
| 2. Fail closed: no fallback to the default user | Met (the implementer's 28 invalid-id cases and the default argument; trace step 8; R3 caught) |
| 3. No portfolio: "no brief yet", and no folder | Met (the implementer's tests; trace step 2) |
| 4. The digest fallback is scoped the same way | Met (the implementer's `member_b`; trace step 7) |
| 5. Invariant tests, both real routes with a stubbed model | Met; L1 extends them |
| 6. Documentation | Met: CHAT_ARCHITECTURE sections 2, 4 and 9; KT sections 10 and 12, with the PDF matching its source; PRODUCT_MAP section 16; guide 11-F |

- **Production verification:** `pending_deployment`. The push was at 08:16:32 IST, 11 Oct, and
  the owner confirms `railway deployment list` and `/health`. Then the card's read-only check:
  as a member account, or with `AUTH_REQUIRED` on, "show my brief" shows none of the owner's
  holdings. If no member account exists, record the cross-account case `not_applicable` and
  confirm the owner still gets the owner's own brief. Also I1, if a member exists.

## Verdict

**ACCEPTED.**

- The reviewed revision is the committed `954305a`: review input `82d6c89c…` and diff
  `e28f1e61…`.
- FIX-005 is `done`, and its `production_verification` is `pending_deployment`.
- **Next:**
  1. Commit this review's documentation at the owner's word. It is docs only, and every push
     redeploys.
  2. The owner confirms the 11 Oct deploy, then runs the production check.
  3. The owner routes L2 (the anonymous watchlist read).
  4. Then SA-011's implementation, in a new conversation.
