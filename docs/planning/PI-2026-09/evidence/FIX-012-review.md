# FIX-012 review receipt — FIX-007's log-route guard on any FastAPI

## Fresh-session review: ACCEPTED (2026-10-23)

**Context:** a fresh-session review in a new conversation (stockagent-main-a4) opened with
"continue", 23 Oct about 00:04 to 00:50 IST. It is not the implementing conversation
(stockagent-main-a6). At the start, 10 peers were idle and stockagent-main-62 was busy; per the
implementation receipt that is a research-only session. Nothing was committed, pushed, deployed
or configured. No production state was read and no notification was sent.

**Story:** [FIX-012](../stories/FIX-012.md). **Reviewed input:**
[FIX-012-manifest.json](FIX-012-manifest.json) `db64de1c…` (1 file) and diff `3bc40d5a…`
(4,193 bytes, 1 path), on `HEAD` `560d18f`. The review made no edit to the reviewed file.

**In one example.** A developer adds a route to the app that returns `log_buffer.snapshot(...)`
and forgets the owner check.

| How the route is added | FastAPI 0.136.1 (local) | FastAPI 0.137.0 to 0.160.0 (CI) |
|---|---|---|
| A new router, included with a prefix (`app.include_router(r, prefix="/x")`) | fails: "/x/logs-copy reads server logs without require_owner" | fails: "16 app entries the walk cannot read into, 15 routers read" |
| `@app.get(..., include_in_schema=False)` on the app | fails, by name | fails, by name |
| A sub-router included into the ops router | fails: walked, not published | fails: "a mounted router holds routes the walk cannot read" |
| `app.add_route(...)`, a plain Starlette route | **passes** (L1) | **passes** (L1) |

Before FIX-012, CI's guard failed on every push because it found no route at all, so none of
these could be told from the standing failure. The last row is a gap FIX-007's guard already
had. It is routed to SA-031 (L1).

### Review input verified

- **Blob:** `git hash-object` of the story file gives `902a89b9…`, the manifest's. Its blob at
  `HEAD` `560d18f` and at the implementer's baseline `0a798e1` is the same, `a78d15d5…`.
- **Diff:** `git -c core.autocrlf=false diff --no-color HEAD --` over the one path, piped to
  `sha256sum` by the reviewer (not the implementer's script): `3bc40d5a…`, 4,193 bytes. It
  matches the receipt.
- **HEAD drift:** `0a798e1..560d18f` is FIX-013's one commit, 19 paths. None is the story file,
  `services/api/server.py` or a router's route table (`ui_data.py` changed two model-name
  literals only).
- **At the end:** the same blob and diff digest; `git status --porcelain` unchanged apart from
  this receipt and the bookkeeping (STATE, HANDOFF, SA-031 card).

### Contract checked

- **The card's invariant:** on both FastAPI structures, every route the app serves that reads the
  ring buffer depends on `require_owner`, and the readers are exactly `/ui/logs` and
  `/ui/logs/stream`. The guard must fail, not pass, when it walks no route or only some.
- **How FastAPI 0.137+ serves an included route** (code inspection of 0.160.0's
  `fastapi/routing.py`):
  - `_IncludedRouter.effective_candidates()` reads `original_router.routes` on each version
    change. So the router's own `routes` list is what is served, and a route added after the
    include is served too.
  - An included `APIRoute` is served with `dependencies=[*include_context.dependencies,
    *route.dependencies]`; an `APIWebSocketRoute` is rebuilt the same way. So a served route has
    at least the original's dependencies. A `require_owner` the guard reads on the original
    route cannot be missing at serve time. That is the direction that matters: no false pass.
  - From 0.159, an `APIRouter` also keeps `_low_priority_routes`, which the walk does not read.
    Only `router.frontend(...)` fills it, with static-file groups, not endpoints, so no route
    there can read the buffer. The app does not call `frontend(` (I3).
- **Public interfaces only:** the walk reads `app.routes`, `APIRouter.routes`, route attributes
  and `fastapi.openapi.utils.get_openapi`. It never imports `_IncludedRouter` and never touches
  `app.openapi_schema`. Its only private-looking read is `vars(server)`, which is the test's own
  module lookup, not FastAPI's.
- **Nothing else walks routes:** a search for `.routes` across `services`, `src`, `core`,
  `tests` and `scripts` finds only this file (other hits are module paths).

### Independent adversarial examples

The reviewer's own cases, not the implementer's mutants. They are applied by a pytest plugin
(`analysis_data/fix012_review/rv_plugin.py`) to the live app after collection, as a developer's
edit would be, so no tracked file was touched. Runner: `rv_run.py`. Each case ran the two guard
tests in the same five environments as the implementation receipt (A: Python 3.13.11 with
FastAPI 0.136.1; B to E: Python 3.11.9 with CI's packages of 22 Oct, FastAPI 0.136.1, 0.137.0,
0.159.1 and 0.160.0). The version was printed from inside each interpreter.

| Case | What it does | A | B | C | D | E |
|---|---|---|---|---|---|---|
| control | nothing | pass | pass | pass | pass | pass |
| R0 | the guard's walk as FIX-007 shipped it (`APIRoute`s in `app.routes`) | guard passes; walk test fails | the same | **both fail** (CI's defect) | both fail | both fail |
| X1 | a new router with an ungated published reader, `include_router(r, prefix="/x")` | caught, by name | caught | caught, one for one | caught | caught |
| X2 | X1, with the router also bound in `server.py` | caught: walked, not published | caught | caught: `/x/logs-copy` published, not walked | caught | caught |
| X3 | an ungated websocket reader on the app (`add_api_websocket_route`) | caught, by name | caught | caught | caught | caught |
| X4 | an ungated plain Starlette route on the app (`app.add_route`) | **missed** | missed | missed | missed | missed |
| X5 | an ungated reader added to the ops router after it was included | caught: walked, not published (not served on 0.136.1) | caught | caught, by name (served) | caught | caught |
| X6 | a sub-router with an ungated reader included into the ops router | caught: walked, not published | caught | caught: unreadable router entry | caught | caught |
| X7 | an ungated reader on the app, hidden from the schema | caught, by name | caught | caught | caught | caught |
| X8 | a bound router never included, plus an unbound included router; both hidden from the schema | caught, by name | caught | **missed** | missed | missed |

"Caught" means one or both guard tests failed with the message shown. "By name" is "`<path>`
reads server logs without require_owner".

- **The card's hard-review questions.**
  - *Can the guard pass while it walks no route or only some?* No route: no. The readers must be
    exactly the two log routes, the published set must equal the walked set, and the walk test
    needs `/health`, both log routes and `/ws/stream` (implementer's W1). Only some: on 0.137+
    the one-for-one count or published = walked fails it (W3, W3a, W3b, X1, X2, X6). The one
    exception needs two unusual edits at once (X8, I2). On 0.136.1 every partial walk still sees
    every route, because `app.routes` holds a copy of each (W2, W3 "equivalent").
  - *Does it still fail when a route reads the buffer without the owner check, on both
    structures?* Yes, for every FastAPI route however it is registered (X1 to X3, X5 to X7; the
    implementer's M1 to M7). Not for a plain Starlette route on the app (X4, L1), on either
    structure, as before FIX-012.
- **The original defect.** R0 reproduces CI's failure on C to E and passes the guard on A and B,
  as the implementation receipt's `out/baseline` showed for the unmodified file.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (test gap, inherited from FIX-007; code correct) | `tests/unit/api/test_log_routes_owner_only_fix007.py:270` (`if not isinstance(route, _ENDPOINT_ROUTES): continue`) | A plain Starlette `Route` or `WebSocketRoute` in `app.routes` is skipped. X4 (`app.add_route("/rv-raw-logs", …)`, returning `log_buffer.snapshot(…)` with no check) passes both guard tests in all five environments. FastAPI's own docs routes are such entries (`/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`), so they cannot simply be refused. Such a route cannot carry `require_owner` as a dependency, so any reader there is ungated. A plain route inside a mounted router is already refused loudly (the "cannot read" check). No route of this kind reads the buffer today: the guard finds exactly the two log routes. Impact: a future `app.add_route` reader would reach CI unflagged. | **Routed** to [SA-031](../stories/SA-031.md), with the fixture: X4 in `analysis_data/fix012_review/rv_plugin.py`. Fix: also read the endpoints of plain `Route` and `WebSocketRoute` entries of `app.routes`, and assert that none reads the buffer. |
| I1 | Info (inherited) | the same file, `:296-297` | The implementer's I1: a reader is found by the endpoint's own source text. A helper function or an aliased import is not seen. | Agreed. Noted with L1 at SA-031 as an optional stronger check (the buffer's callers). |
| I2 | Info | `:255`, `:262` | X8 is missed on 0.137+: a router bound in `server.py` but never included (all its routes hidden from the schema), plus a router included without a module name whose ungated reader is also hidden. The one-for-one count then matches (16 = 16), and published = walked holds. It needs both edits at once, and the local 0.136.1 run still catches it by name. The private `original_router` would close it; the card asks for public interfaces. | No action. |
| I3 | Info | FastAPI ≥0.159 `APIRouter._low_priority_routes` | Not walked. It holds only `frontend()` static-file groups, so no endpoint there can read the buffer. Unused here. | No action. |
| I4 | Info | the card's third acceptance criterion | CI's "Python tests (Linux, 3.11)" can only be read after the push. Predicted by environment E, but that ran on Windows, not Linux (the implementer's I5). | The check after the push (below). |

**The implementer's own items:** I1 agreed (above). I2: confirmed, the app has no mount in this
checkout. I3: agreed; any other shape of include fails loudly (X6 on 0.137+). I4: confirmed by
X2 and by the published = walked check. I5: agreed (I4 above).

No critical, high or medium finding.

### Commands and results

All under `tests/hermetic.py` (loaded by `tests/conftest.py`).

- **Story file, five environments**
  (`.stockai/Scripts/python.exe analysis_data/fix012/run_envs.py review_story tests/unit/api/test_log_routes_owner_only_fix007.py`):
  **43 passed** in each of A to E.
- **Reviewer cases:** `.stockai/Scripts/python.exe analysis_data/fix012_review/rv_run.py`, 10
  cases × 5 environments. The table above; raw output in `analysis_data/fix012_review/out/`
  and `out_matrix.txt`. Every run printed "applied <case>", so no case ran unapplied.
- **Full suite, CI's command, in environment E** (Python 3.11.9, FastAPI 0.160.0, starlette
  1.9.0, CI's other packages of 22 Oct), on the reviewed tree (`560d18f` plus the diff):
  `python -m pytest -q -rfEs -p no:cacheprovider tests`: **5,562 passed, 12 skipped, 1 xfailed,
  0 failed** in 13 min 32 s (00:22–00:36 IST). No "hermetic boundary" section. 5,562 is the
  implementer's 5,560 plus FIX-013's two new tests. This is the first full run on the tree after
  FIX-013; the implementer's runs were on `0a798e1`. The known intermittent SA-009 test (below)
  passed.
- `scripts/docs/check_kt_docs.py`: `errors: []` (the uncommitted KT row and rebuilt PDF of
  22 Oct).
- `scripts/ci/check_broad_except.py`: OK (151 grandfathered).

**Not exercised:** Linux, and the real CI runner (after the push). Starlette was 1.9.0 in B to E
and 1.0.0 in A; no other Starlette version was tried.

### Documentation

None needed, as the implementation receipt says. No living document describes the guard's
mechanism: KT section 10 describes the owner-only log routes, which are unchanged. The
uncommitted KT section 12 row (FIX-012, `Open`) and its rebuilt PDF pass `check_kt_docs`. At the
commit, the row becomes `Done` and the PDF is rebuilt.

### Acceptance

| Criterion | Result |
|---|---|
| Under 0.136.1 and the newest release, the guard finds exactly `/ui/logs` and `/ui/logs/stream`, both depending on `require_owner` | **Met.** 43 passed in A to E, including 0.160.0, the newest. |
| Mutants caught under both versions: `require_owner` removed from either route; a new route calling `log_buffer.snapshot(` without it; a walk returning no routes | **Met** for FastAPI routes (implementer's M1, M2, M3, W1; reviewer's X1 to X3, X5 to X7). A plain Starlette route is not caught (L1, inherited, routed). |
| CI's Linux job passes on the push that ships it, checked through the public GitHub API | **Pending:** after the owner's commit and push. Predicted by E. |
| No test reaches the network | **Met.** All runs were under the hermetic boundary, and none printed a "hermetic boundary" section. |

## Verdict

**ACCEPTED.**

- **Reviewed revision:** the uncommitted story file on `HEAD` `560d18f`, at review input
  `db64de1c…` (blob `902a89b9…`) and diff `3bc40d5a…`. No review edit to it.
- **Status:** FIX-012 is `done`. Production is unaffected (test-only).
  `production_verification` is `pending_deployment`: what remains is CI's Linux job on the push
  commit.
- **Next:**
  1. **FIX-013's fresh review**, in a new conversation ("continue"). FIX-013 is
     `review_required` (committed and pushed as `560d18f` by the owner's word; a recorded
     deviation). Then **PR-011** (its dependency PR-006 is done).
  2. **Commit and push FIX-012** at the owner's word, in a job-free window (safest 00:10–06:20
     IST; every push redeploys). With the commit: the KT section 12 FIX-012 row `Open` → `Done`,
     the KT header revision bumped, the PDF rebuilt, `check_kt_docs` run.
  3. **After the push:** read the commit's check runs from the public GitHub API. "Python tests
     (Linux, 3.11)" must pass. Name anything else that fails; do not hide it. One test is known
     to fail intermittently, unrelated to FIX-012:
     `test_store_migration_sa009.py::test_a_refused_store_is_retried_and_the_status_never_overstates`
     (found during FIX-013: 1 run in 6 on `0a798e1`; not routed yet).
