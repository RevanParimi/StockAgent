# FIX-005 — implementation receipt

**Story:** [FIX-005](../stories/FIX-005.md) · **Phase:** implementation, with same-conversation
self-review only · **Date:** 2026-10-11, about 07:47–08:10 IST · **Baseline:** `04ee080`
(`04ee080323cd9418e66fc7796cb423c01618d4ec`; its code is identical to `61c85d6`, the code
production runs) · **Status after this phase:** `review_required`

## How this phase came about

The deep-dive rewrite (same conversation, 10–11 Oct) traced chat's `get_portfolio_brief` and found
it reads the default user's portfolio for every caller. The owner, about 07:50 IST 11 Oct: "on
privacy - good finding, lets do as per recommendation and later commit and push them". Two
recorded deviations, both at the owner's word:

- this implementation runs in the conversation that found the defect, not a new one;
- it is committed and pushed before its fresh-session review, as FIX-004 change 1 was. The fresh
  review then reviews the committed bytes (`kt_manifest.py verify FIX-005-manifest.json --rev
  <commit>`), and any requested change lands as a follow-up commit.

No production state was read.

## What changed

**Before.** `_chat_tool_portfolio_brief()` built `PortfolioStore()` with no user id, which opens
the default `primary` store. Neither `_execute_chat_tool` nor `_dispatch_chat_tool` received the
caller, although both chat routes know it (`user["user_id"]`).

**After** (`services/api/routes/ui_data.py`):

- `_execute_chat_tool(name, args, cache=None, user_id=None)` and
  `_dispatch_chat_tool(name, args, user_id=None)` carry the caller; both chat routes pass
  `user_id=user["user_id"]`.
- `_chat_tool_portfolio_brief(user_id)` opens `PortfolioStore(user_id=user_id)`: the same store
  `GET /portfolio` and `GET /delivery/brief/latest` open.
- **Fail closed.** No user id, or one that fails the store's own id pattern
  (`^[A-Za-z0-9_-]{1,64}$`), returns "Your brief is unavailable — this request is not tied to a
  signed-in account." The default argument is `None`, so a caller that forgets the user is
  refused, never served the default user.
- A valid id with no portfolio folder returns "No brief yet …" before the store is constructed, so
  the read creates no folder (the store's constructor would).

**Example.** The owner's `primary` portfolio has a brief listing FEDERALBNK; a member account
`u_3f9a1c2b` has none. Before: the member asking chat "show my brief" got the owner's brief.
After: the member gets "No brief yet"; the owner still gets the owner's own brief. Member ids are
generated as `u_` plus 8 hex digits (`user_store.create_user`), so a member cannot be `primary`.

## Invariant tests

New: `tests/unit/api/test_chat_brief_user_scope_fix005.py`, **51 tests**. Fixture: the owner with
a brief and a digest, `member_a` with a brief, `member_b` with a digest only, `member_c` with no
portfolio; each carries a unique marker string.

- **Every layer, every caller** (12 tests = 4 layers × 3 accounts): the tool, the dispatcher, the
  executor and the executor with a memo cache. Each caller's output holds its own marker and
  **none** of the other accounts' markers.
- **No portfolio** (4): "no brief yet", and the portfolio tree is byte-for-byte the same listing.
- **No or invalid user** (28 = 7 values × 4 layers: `None`, `""`, `" primary"`, `"../primary"`,
  `"a/b"`, 65 characters, `"primary/../member_a"`): the refusal text, no marker of any account,
  no folder created.
- **Default argument** (1): calling the dispatcher or executor without a user is refused.
- **Both real routes, model stubbed** (6): the stub asks for `get_portfolio_brief`, then echoes
  the tool's output. On `/ui/chat/stream` (owner, `member_a`, `member_b`) the `tool_result` event
  and the streamed answer hold the caller's marker and no other account's anywhere in the event
  stream; the stub is called twice (tool round, then answer). On `/ui/chat` (owner, `member_a`)
  the reply holds only the caller's marker. A `member_c` stream shows "No brief yet", no marker
  and no new folder.

Updated: `tests/unit/test_chat_brief_tool.py` now names the default user explicitly when it
dispatches (its cases are the owner's).

**Mutations** (in memory, `analysis_data/fix005/fix005_mutants.py`, loaded with `-p`; repo files
never written), over the new file and the updated one (54 tests):

| Variant | Result |
|---|---|
| None (the change as written) | 54 passed |
| Baseline behaviour: the caller ignored, the default user read | **caught:** 45 failed |
| Uses the caller but falls back to the default user when none is given | **caught:** 9 failed |
| Dispatcher drops the user | **caught:** 20 failed |
| Cached executor path drops the user | **caught:** 8 failed |
| A route passes the default user instead of the caller | **caught:** 25 failed |
| No folder check: the read constructs the store (creates the folder) | **caught:** 9 failed |

## Commands and environment

Windows 11, Python 3.13.11, pytest 9.0.3, the project's `.stockai` virtual environment; every run
passes through `tests/hermetic.py` (no `.env`, no network, empty working directory per test).

- New file: `python -m pytest tests/unit/api/test_chat_brief_user_scope_fix005.py -q
  -p no:cacheprovider` → 51 passed.
- Focused chat set (brief, dossier tool and drift guard, session memory, turn budget, chat user
  binding, `tests/unit/intelligence/chat`, the new file) → **106 passed**.
- Mutations: `FIX005_MUTANT=<variant> PYTHONPATH=analysis_data/fix005 python -m pytest -p
  fix005_mutants <the two files> -q -p no:cacheprovider`.
- Full suite: `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count`, run
  twice:
  - first run: 4317 passed, 12 skipped, **1 failed** (8 min 36 s). The failure was
    `test_store_migration_sa009.py::test_a_refused_store_is_retried_and_the_status_never_overstates`:
    the store that `apply` should have moved was not found in the quarantine. It passed 3 of 3
    alone and its file 22 of 22. It imports none of the changed files; this is the known Windows
    rename flake in the store migration (HANDOFF; routed to SA-031);
  - second run: **4318 passed, 12 skipped, 0 failed** (4 min 57 s).
- Runtime data: `analysis_data/fix005/runtime_digest.py` over `data/`, `logs/` and `outputs/`
  (paths, sizes, modification times and bytes): `800 files 0f244752a10d7597` before the first
  run, after it, and after the second.
- Docs: KT PDF rebuilt (source `55d6c82f…`, 37 pages); `check_kt_docs` errors `[]`; relative
  links, anchors and list spacing checked on the edited documents.

## Documentation

- [CHAT_ARCHITECTURE](../../../CHAT_ARCHITECTURE.md): section 2 gains a "User scope" row; the
  tools table describes the brief as the caller's; the limit is removed from section 9.
- [KT](../../../TECHNICAL_DESIGN.md) section 10 (portfolio identity, chat included) and section
  12 (five fixes outside the SA numbering); PDF rebuilt.
- [PRODUCT_MAP](../../../PRODUCT_MAP.md) section 16: the user-plane rule, and the one remaining
  exception (below, L1).
- [Testing guide](../../../TEAM_TESTING_GUIDE.md) case **11-F**.
- The [FIX-005 card](../stories/FIX-005.md).

## Manifest and digest

- **Review input:** [FIX-005-manifest.json](FIX-005-manifest.json), 9 files. The SHA-256 of its
  LF bytes is **`82d6c89c20d215b30b0b60826a679a6f992a01fd7991dd39c0532ed50bc04c9d`**, and
  `kt_manifest.py verify` gives 0 mismatches.
  - Files: `ui_data.py`, the new and the updated test file, the KT and its PDF,
    CHAT_ARCHITECTURE, PRODUCT_MAP, the testing guide and the FIX-005 card.
  - Excluded: STATE, HANDOFF and this receipt (bookkeeping). STATE and HANDOFF also carry the
    deep-dive rewrite's notes.
- **Diff digest:** **`e28f1e61ce93e906b2c71a9b902e9eacfffa3712e14b8c9293c10ac307a1ccdc`**, 27,443
  bytes over 8 files.
  - **To rebuild it:** take every manifest path except the PDF, sorted. For a path tracked at
    `04ee080`, run `git diff --no-color --no-ext-diff 04ee080 -- PATH`. For the new test and the
    new card, run `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`. Concatenate
    the outputs. `analysis_data/fix005/diff_digest.py` does exactly this.
  - After the commit, a reviewer runs `kt_manifest.py verify FIX-005-manifest.json --rev
    <commit>`. The KT bump commit that follows changes the KT, its PDF, the deep-dive headers and
    guide 11-F, so verify against the implementation commit, not the bump.

## Self-review

No critical or high finding in the change. Findings, most severe first:

- **L1 (low, related, not fixed). The watchlist route's fallback.** `GET /ui/watchlist` uses
  `get_current_user_optional`. With Atlas on and `AUTH_REQUIRED` on, an anonymous request gets no
  user, and the route reads the default user's watchlist (`ui_data.py`, `get_watchlist`). With
  `AUTH_REQUIRED` off, the passthrough is the owner anyway. The exposure is a symbol list, not
  values or verdicts. Out of FIX-005's scope (the card names the brief tool); recorded in
  PRODUCT_MAP section 16 for the owner to route.
- **I1 (info). The owner's own account.** A real owner session uses its users-table id, so chat
  now opens that id's portfolio, exactly as `GET /portfolio` does. If the owner's holdings live
  under `primary` while the owner signs in under another id, chat and the portfolio screen agree
  with each other and both show that id's portfolio.
- **I2 (info). The model bench.** `scripts/model_bench.py` calls tools without a user, so the
  brief tool refuses there; the bench does not exercise the brief.
- **I3 (info). The memo cache key** does not include the user. The cache is created inside one
  turn of one request, so it never holds another caller's result; the pre-router's cache keys
  stay compatible.

## Production check (after deploy, read-only)

As a member account (or with `AUTH_REQUIRED` on), ask chat "show my brief" and confirm the reply
and its tool trace carry none of the owner's holdings. If no member account exists, record the
cross-account case as `not_applicable` and confirm the owner still gets the owner's own brief.

## Next

A fresh-session review in a new conversation ("continue"), by REVIEW.md, of the committed bytes.
