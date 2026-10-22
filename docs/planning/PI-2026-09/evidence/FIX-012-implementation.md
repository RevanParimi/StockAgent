# FIX-012 — implementation receipt

**Story:** [FIX-012](../stories/FIX-012.md) · **Phase:** implementation, with same-conversation
self-review only · **Date:** 2026-10-22, about 22:32 to 23:40 IST · **Session:** stockagent-main-a6
· **Status after this phase:** `review_required`

**How this phase came about.** The owner said "continue" in the conversation that had just
verified the production OpenRouter key (read-only, no story phase). FIX-012 was `next_task`,
`todo`, with no dependencies. Peers were idle at the start; a research-only session
(stockagent-main-62) started later and agreed not to run tests or touch the story's files during
the mutant runs.

**Baseline:** `HEAD` `0a798e1`. **HEAD has since moved:** after this phase, another session
committed FIX-013 as `560d18f` (19 paths: model names in `config.yaml`, `base.py` and two
fallback literals in `ui_data.py`, with its docs). The story file's blob is the same at both
(`a78d15d5…`), `git diff HEAD` over it is still `3bc40d5a…`, the manifest verifies with 0
mismatches, and the story file passed again on the new tree, 43 in each of A, C and E (23:55
IST, `out/after_fix013`). The full-suite and mutant runs below were on `0a798e1`. The story file `tests/unit/api/test_log_routes_owner_only_fix007.py`
was unchanged at `HEAD` (blob `a78d15d5…`, SHA-256 `9332c9eb…`). The uncommitted docs in the tree
(the FIX-012 card, KT row, SA-033 note, README, STATE, HANDOFF) are the planning session's and
this conversation's bookkeeping, not this story's payload.

Nothing was committed, pushed, deployed or configured, no production state was read in this
phase, and no notification was sent.

## In one example

A developer adds `GET /ops/recent-logs` to the ops router and has it return
`log_buffer.snapshot(...)` without the owner check.

| FastAPI | Before FIX-012 | Now |
|---|---|---|
| 0.136.1 (local venv) | the guard fails: the route reads logs ungated | the same |
| 0.137.0 and later (CI) | the guard was already failing, on every push, for an unrelated reason (it found no route at all), so the new failure looked like the old one | the guard fails with "/ops/recent-logs reads server logs without require_owner" and passes when the gate is there |

## What changed

Only `tests/unit/api/test_log_routes_owner_only_fix007.py`. No production file and no
`requirements.txt` change (pinning stays in SA-033).

- **The walk** (`_served_routes()`). It reads, through public interfaces only:
  - the app's own endpoint routes in `app.routes` (`APIRoute`, `APIWebSocketRoute`);
  - the `.routes` of every `APIRouter` bound in `services.api.server`, which is how `server.py`
    mounts all 15 routers.

  On FastAPI before 0.137 the app's copies and the routers' originals coincide (deduplicated by
  path, methods and endpoint). From 0.137, `app.routes` holds one opaque entry per
  `include_router` call, and the routes are read from the routers.
- **The walk proves it saw the whole app** before returning anything:
  - every entry of a mounted router is a route it can read (a nested router fails loudly);
  - **one for one:** the app entries the walk cannot read into (FastAPI's include wrappers) are
    either none (the old structure) or exactly as many as the routers it read. A router
    included some other way therefore fails it;
  - a `Mount` must be static files;
  - **published = walked:** the (path, method) pairs FastAPI's public OpenAPI generator
    (`get_openapi(routes=app.routes)`, which does not touch `app.openapi_schema`) publishes
    equal the walked routes that are in the schema.
- **The guard** (`test_every_route_reading_the_log_buffer_requires_the_owner`) runs its unchanged
  check over that walk: every endpoint whose source reads `log_buffer` (`snapshot(` or
  `subscribe(`) depends on `require_owner`, and the readers are exactly `/ui/logs` and
  `/ui/logs/stream`. It now also covers the websocket route.
- **A new test,** `test_the_route_walk_sees_every_route_the_app_serves`, names the walk's
  failure on its own: the walk passes its checks and includes an app route (`/health`), router
  routes (`/ui/logs`, `/ui/logs/stream`) and the websocket route (`/ws/stream`).

## Design decisions (delegated, recorded)

- **D1. Routers from `server.py`'s module names, not FastAPI's wrapper.** Reading
  `_IncludedRouter.original_router` would work today but is a private type; the card asks for
  public interfaces. The one-for-one count closes the gap a name-based list leaves (a router
  included without a module name): M6 and M7 below.
- **D2. OpenAPI as the independent list of what the app serves.** It is FastAPI's public view of
  its own routes and is built by FastAPI's code, not the walk. Routes hidden from the schema
  (two today: `/analytics/powerbi-feed/$metadata` and the frontend catch-all) and the websocket
  route are not in it; for those the one-for-one count and the router checks stand in.
- **D3. The checks live in the helper, not only in the new test,** so the guard can never run
  on a partial walk, even when selected alone.

## Tests

### Environments

| | Python | FastAPI | Starlette | Structure |
|---|---|---|---|---|
| A | 3.13.11 (`.stockai`, local) | 0.136.1 | 1.0.0 | old |
| B | 3.11.9 (CI's fresh install of 22 Oct) | 0.136.1 | 1.9.0 | old |
| C | 3.11.9 + overlay | 0.137.0 (first new) | 1.9.0 | new |
| D | 3.11.9 + overlay | 0.159.1 (CI on 22 Oct) | 1.9.0 | new |
| E | 3.11.9 + overlay | 0.160.0 (newest, released since the reproduction) | 1.9.0 | new |

B to E use the earlier reproduction's CPython 3.11.9 venv (`analysis_data/ci_linux_failure/`),
unmodified; C to E put a `--no-deps` FastAPI install first on `PYTHONPATH`. Each run printed its
versions from inside the interpreter. Runner: `analysis_data/fix012/run_envs.py` (needs the two
`subst` drives in its docstring).

### Results

- **The story file before the change** (`out/baseline`): A and B 42 passed; C, D and E 1 failed,
  41 passed, the failure `assert [] == ['/ui/logs', '/ui/logs/stream']`. CI's failure,
  reproduced.
- **The story file now** (`out/final_file`): **43 passed in each of A to E.**
- **What the walk saw** (`diag_route_walk.py`, `out/diag`), the same in all five: 95 routes
  (94 HTTP, 1 websocket), 92 published operations on 85 paths = the 92 walked schema routes;
  15 routers read; app entries the walk cannot read into: 0 on A and B, 15 on C to E.
- **Mutants** (`mutants.py`; each applied to the file bytes, the two guard tests run in all five
  environments, then the file restored and its SHA-256 checked). Run on the final bytes
  (`out/mutants2_summary.txt`, W4 in `out/mutants_w4_summary.txt`). An earlier pass, before a
  line wrap, gave the same results.

  | Mutant | A | B | C | D | E |
  |---|---|---|---|---|---|
  | M1 `GET /ui/logs` without `require_owner` | caught | caught | caught | caught | caught |
  | M2 `GET /ui/logs/stream` without `require_owner` | caught | caught | caught | caught | caught |
  | M3 a new published route reads the buffer ungated (ops router) | caught | caught | caught | caught | caught |
  | M4 the same, hidden from the schema (analytics router) | caught | caught | caught | caught | caught |
  | M5 a new websocket route subscribes ungated (stream router) | caught | caught | caught | caught | caught |
  | M6 a router included inline in `server.py`, no module name, published ungated reader | caught | caught | caught | caught | caught |
  | M7 M6 with the route hidden from the schema | caught | caught | caught (one-for-one only) | caught (one-for-one only) | caught (one-for-one only) |
  | W1 the walk returns no routes | caught | caught | caught | caught | caught |
  | W2 the pre-FIX-012 walk (`app.routes` only) | equivalent | equivalent | caught | caught | caught |
  | W3 the walk skips one mounted router (analytics) | equivalent | equivalent | caught | caught | caught |
  | W3a W3 with the published = walked check deleted | equivalent | equivalent | caught (one-for-one) | caught | caught |
  | W3b W3 with the one-for-one check deleted | equivalent | equivalent | caught (published = walked) | caught | caught |
  | W4 the walk skips the app's own routes (`/health`, `/tickers`) | caught | caught | caught | caught | caught |

  "Equivalent": on FastAPI 0.136.1 `app.routes` holds a copy of every route, so W2 and W3 still
  walk all 95 (`out/diag`); they are not defects there. W3a and W3b show each completeness check
  catches a partial walk on its own; M7 is caught only by the one-for-one check on C to E
  ("16 app entries the walk cannot read into, 15 routers read").
- **Full suite, CI's command** (`python -m pytest -q -rfEs -p no:cacheprovider tests`, the
  hermetic boundary on), 23:09–23:31 IST:
  - **A** (local): **5,560 passed, 12 skipped, 1 xfailed, 0 failed**, 10 min 41 s;
  - **E** (Python 3.11.9, FastAPI 0.160.0, CI's other packages of 22 Oct): **5,560 passed, 12
    skipped, 1 xfailed, 0 failed**, 10 min 45 s. The reproduction's Windows-only `WinError 5`
    flake did not appear.

  5,560 = PR-006's review count 5,559 plus the new test. `git status` was unchanged by the runs,
  apart from this receipt, written meanwhile.
- `scripts/ci/check_broad_except.py`: OK (151 grandfathered).

## Acceptance criteria

- Under 0.136.1 and the newest release, the guard finds exactly `/ui/logs` and
  `/ui/logs/stream`, both depending on `require_owner`: **met** (A to E).
- Mutants caught under both versions (`require_owner` removed from either route, a new ungated
  `log_buffer.snapshot(` route, a walk that returns no routes): **met** (M1, M2, M3, W1 in all
  five).
- CI's "Python tests (Linux, 3.11)" passes on the push that ships it: **pending**, needs the
  owner's commit and push, then a read of the public GitHub API. Predicted by E: the full suite
  passes under CI's Python and newest FastAPI, but on Windows, not Linux.
- No test reaches the network: **met.** Both full runs were under `tests/hermetic.py`, which fails
  the session and prints a "hermetic boundary" section on any outbound connection or checkout
  write; both exited 0 with no such section. The new code only calls FastAPI's schema generator
  in-process.

## Documentation

None needed in this phase. The change is test-only and changes no behaviour, so no living doc
describes it. KT section 12's FIX-012 row stays `Open` until the commit (the commit-time edit
makes it `Done`, then the PDF is rebuilt).

## Manifest and digest

- **Review input:** [FIX-012-manifest.json](FIX-012-manifest.json),
  `db64de1c00cbff2d5b4a714f332dfeef7aadf5dc3710291009b78c96763013dc`, 1 file:
  `tests/unit/api/test_log_routes_owner_only_fix007.py`, blob `902a89b9…`, SHA-256
  `a230b16e…`. `kt_manifest.py verify`: 0 mismatches.
- **Diff:** `3bc40d5ad666f5cb84a2f6a3dd66998df05f445cd3cf84efa317e07dce0824ad` (4,193 bytes, 1
  path), `git diff HEAD` (`0a798e1`) over the payload path
  (`analysis_data/fix012/digest.py`, writes `fix012_code.diff`).
- **Changed by this phase:** the test file. Bookkeeping: STATE, HANDOFF, this receipt and the
  manifest. Tooling and raw outputs stay in the ignored `analysis_data/fix012/`.

## Self-review

No critical, high or medium finding.

- **I1 (info, inherited from FIX-007, unchanged).** A reader is found by the endpoint's own source
  text. An endpoint that reads the buffer through a helper function, or imports `snapshot` under
  another name (`import snapshot as s`), is not seen. FIX-012 is about the walk; this check is as
  FIX-007's review accepted it. A follow-up could check the ring buffer's callers instead.
- **I2 (info).** The `Mount` check is vacuous in this checkout: no `/assets` directory exists
  locally or in CI, so the app has no mount. It fails loudly if a sub-application is ever
  mounted.
- **I3 (info).** The one-for-one count assumes FastAPI adds one opaque entry per
  `include_router`, as 0.137.0 to 0.160.0 do (`out/diag`). Any other future change of shape fails
  the guard loudly, the intended direction.
- **I4 (info).** The guard's routers are the ones `server.py` binds by name. A router bound there
  but not included would also fail the one-for-one count on the new structure, and it fails the
  published = walked check on either structure if any of its routes is in the schema. That
  failure is loud too.
- **I5 (info).** All runs were on Windows. The story's acceptance is CI's Linux job after the
  push. Production's FastAPI version is still unknown (SA-033).

## Next

- A **fresh review in a new conversation** ("continue"), from [REVIEW.md](../REVIEW.md). The card's
  hard-review questions are answered by W1–W4 (partial or empty walks) and M1–M7 (ungated
  readers) above. The runner needs the two `subst` drives; `mutants.py` restores each file and
  checks its SHA-256.
- After acceptance: commit and push at the owner's word. Every push redeploys production (this
  change is test-only), so push in a job-free window. Then read CI's conclusion for that commit
  from the public GitHub API: the "Python tests (Linux, 3.11)" job must pass, and anything else
  that fails is named.
- Then PR-011.
