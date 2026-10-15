# FIX-009 — implementation receipt

**Story:** [FIX-009](../stories/FIX-009.md) · **Phase:** implementation, with same-conversation
self-review only · **Date:** 2026-10-13, about 15:32–16:30 IST · **Baseline:** `4c85eec`
(FIX-008 committed, and pushed at 15:29:02 IST at the owner's word; deploy confirmation pending)
plus the uncommitted push note in STATE and HANDOFF and the owner's `docs/README.md` probe line,
neither of them FIX-009's · **Status after this phase:** `review_required`

## How this phase came about

A new conversation opened with "continue". FIX-009 was STATE's `next_task` and the first planned
`todo` story whose dependencies are `done` (it has none). No production state was read, nothing
was committed, pushed or deployed, no production variable was changed and no notification was
sent. The two peer sessions (`stockagent-main-06`, `splitfamilia-a9`) were idle.

## What changed

**Before (code inspection; the FIX-008 review's trace test 5 reproduced it).**
`_watched_symbols()` in `core/delivery/index_watch.py` joined every active account's holdings and
watchlist with the shelf's active ideas, and `run_index_watch()` sent every resulting event through
`emit_alerts_broadcast()` to every account with a push subscription and the default user. One
`try` covered all accounts, so a read error on one account stopped the loop and left the later
accounts' stocks out of the check.

**After.**

- `_shelf_symbols()`: the shelf's active ideas.
- `_account_symbols()`: held and watched symbols for each account, by user id. Accounts are
  `active_user_ids()`, or the default user when there are none, as before. Each account has its
  own `try`: a read error leaves that account out, with a warning that names it. A failed account
  lookup leaves every account out, with a warning; the shelf's events still go.
- `run_index_watch()` picks events from the shelf's and every account's symbols, as before; the
  snapshot, the diff and the degraded mode are unchanged. Then:
  - events about shelf ideas go to the market audience through `emit_alerts_broadcast()`;
  - each account gets one `emit_alerts(own, user_id=uid)` bundle with the events about stocks it
    holds or watches, leaving out a shelf idea only when the broadcast's result (`users`)
    included that account.
- `core/delivery/alerts.py`: `emit_alerts_broadcast`'s docstring lists an index change to a shelf
  idea, not every index change, among market notices.

**Example.**

| Index change | Before | After |
|---|---|---|
| BBB, which only the owner watches, leaves the NIFTY 50 | the owner and the member (push, email, Inbox) | the owner only |
| DDD, which only the member holds | both | the member only |
| EEE, an active shelf idea | both | both, once each |
| EEE, also held by the member | both, once | both, once (with the shelf's notice) |
| EEE, held by an account with no push subscription | nothing: the account is outside the market audience | that account, once, in its own notice (email and Inbox) |
| The member's `portfolio.json` is corrupt | the member's stocks read as empty (quarantine); nothing about them | the same, and the owner gets FIX-008's quarantine notice |
| Reading the member's portfolio raises | the loop stopped: the member's stocks and those of every account after it went unwatched | only the member's own changes are skipped, with a warning |

**Design decision (delegated, recorded).** The card says a symbol that is both a shelf idea and
an account's stock "is sent once per account: as a shelf event". That assumes every account is in
the market audience. An account with no push subscription that is not the default user is not, so
the shelf's notice never reaches it; sent only as a shelf event, it would never hear about a stock
it holds. The implementation sends such an idea in that account's own bundle when, and only when,
the broadcast's result does not include the account. `index_watch` reads the result of
`emit_alerts_broadcast` and does not choose an audience itself, which is the FIX-008 guard's rule.

An earlier version of this phase left shelf ideas in every own bundle and relied on the sent-log's
per-account key to drop the repeat. Mutation testing showed no visible difference while delivery
worked, but a failed delivery is recorded `delivered: false`, which does not deduplicate
(AUD-085), so the held idea would have been recorded, and listed in that account's Inbox, twice in
one run. The explicit check replaced it; test
`test_a_held_shelf_idea_is_recorded_once_when_delivery_fails` and mutant M11 pin it.

## Invariant tests

`tests/unit/test_index_watch_own_accounts_fix009.py`, **15 tests**. The NSE client is a fake;
transports are recorded at pywebpush's `webpush` and `smtplib.SMTP` by FIX-008's `wire` fixture
(imported, as other test modules import fixtures). Everything else is real: a temporary
`users.db` with the owner (the default portfolio id, two devices) and a member (one device), real
`PortfolioStore` files, a real `shelf.json` with one active and one dropped idea, the real
sent-log, `deliver`, `resolve_recipient` and the application for the Inbox. The five symbols:
the owner watches one and holds another, the member holds a third, the shelf lists a fourth, and
the fifth is a dropped shelf idea that nobody holds.

- **Each account's own and the shelf's** (1): one run moves all five. Each owner device gets two
  pushes, its own two stocks in one and the shelf idea in the other; the owner's mailbox two
  emails. The member's device and mailbox get the member's stock and the shelf idea. Nobody hears
  about the fifth; the member never receives the owner's stocks, and the owner never the member's.
  The sent-log holds exactly those records per account.
- **Inbox** (1): each account's `GET /delivery/alerts` lists exactly its own index events.
- **A held shelf idea, once** (3): when both accounts hold or watch it, every device and mailbox
  gets it once and each account has one record; an account with no push subscription gets it once,
  by email and in its Inbox; with delivery off, each account records it once.
- **No accounts** (2, AUTH off): by the directory scan and by the empty-list fallback, the default
  user gets its own stock and the shelf idea (push and `DELIVERY_EMAIL_TO`); an orphan push
  subscription gets the shelf idea alone.
- **An unreadable account** (3): a corrupt member file (real quarantine; the owner-only notice
  goes out), a read that raises (the warning names the account; 3 events instead of 4), and a
  failed account lookup (the shelf idea alone, to both). The member's stock reaches nobody; the
  owner's still reach the owner.
- **Snapshots and repeats** (4): the first snapshot sends nothing and stores the list; a failed
  index keeps its stale snapshot while another index's change still reaches only its account; a
  re-run of the same diff on the same day sends nothing; after the old broadcast has delivered all
  four events to both accounts (the pre-FIX-009 writer, `emit_alerts_broadcast`), a run on the same
  day sends nothing to anyone, because the sent-log key (account, date, kind, symbol) is unchanged.
- **Atlas on** (1): the accounts come from a real `atlas.db` (`mirror_user`), and the real outbox
  queues four rows per account (two bundles, push and email), each holding only that account's own
  stocks and the shelf idea; nothing is sent inline.

**Existing tests changed:**

- `tests/unit/test_index_watch.py`: the three tests patch `_shelf_symbols` and `_account_symbols`
  instead of `_watched_symbols`; the diff test asserts the split (the shelf's event broadcast, the
  account's own to `user_id="u1"`), and every test asserts that neither path is called when it
  should not be. The third test no longer reads the checkout's `data/portfolios`.
- `tests/unit/test_operator_notices_owner_only_fix008.py`: the index-reconstitution market caller
  makes both symbols shelf ideas; the guard's classification adds `run_index_watch` to
  `OWN_ACCOUNT_SITES` and keeps it in `MARKET_SITES` (shelf ideas only).

**Mutations** (in memory; repo files never written; `analysis_data/fix009/swap_plugin.py`,
`FIX009_SWAP`), over the new file, `test_index_watch.py` and the FIX-008 guard file (40 tests):

| Variant | Result |
|---|---|
| None (the change as written) | 40 passed |
| `base`: `index_watch.py` as at `4c85eec`, proved by blob id `655861b8` | **caught:** 17 failed. 11 of the new file's 15 fail on assertions. 9 fail on routing: the member received the owner's stocks and the owner the member's; the orphan subscription received the default user's stock; the no-push account got nothing; with Atlas on, both accounts' rows held every stock. The read-error and failed-lookup tests fail first on the warning, which on the base neither names the account nor says the lookup failed; on a failed lookup the base also sent the shelf idea alone. The 4 that pass pin preserved behaviour (first snapshot, re-run, deploy-day dedupe, failed delivery). The other 6 failures patch seams the base lacks. |
| M1: every watched event broadcast (the old routing) | **caught:** 11 failed |
| M2: shelf ideas never in an own bundle | **caught:** 1 failed (the no-push account) |
| M3: one unreadable portfolio drops every account | **caught:** 1 failed |
| M4: a failed account lookup falls back to the default user | **caught:** 1 failed |
| M5: no broadcast of shelf ideas | **caught:** 13 failed |
| M6: own bundles sent without the account id (to the default user) | **caught:** 7 failed |
| M7: one message per event instead of one bundle per account | **caught:** 2 failed |
| M8: dropped shelf ideas count as shelf ideas | **caught:** 11 failed |
| M9: shelf ideas not watched | **caught:** 13 failed |
| M10: the watchlist ignored | **caught:** 9 failed |
| M11: who the broadcast reached ignored (relies on the sent-log dedupe) | **caught:** 1 failed (delivery off: recorded twice) |

## Commands and environment

Windows 11, Python 3.13, the project's `.stockai` virtual environment; every Python run passes
through `tests/hermetic.py`.

- `python -m pytest tests/unit/test_index_watch_own_accounts_fix009.py -q -p no:cacheprovider`
  → 15 passed.
- Related: the new file, `test_index_watch.py`, `test_operator_notices_owner_only_fix008.py`,
  `test_alerts_wave_f.py`, `test_delivery_alerts.py` → **66 passed**.
- `python scripts/ci/check_broad_except.py` → OK (154 grandfathered). The new handlers log.
- Mutants: `bash analysis_data/fix009/run_swaps.sh` (results in `swap_results.txt`); base:
  `analysis_data/fix009/base_snapshot.py`, mutants: `analysis_data/fix009/mutants.py`.
- Full suite: `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count tests`
  → **4508 passed, 12 skipped, 0 failed (14 min 12 s)**, on the manifest's code and test
  bytes. The KT's and ARCHITECTURE's line wrapping and the PDF were redone two minutes into the
  run; no test reads them, and `check_kt_docs` ran after.
- Runtime data: `analysis_data/fix009/data_fingerprint.py` (path, size and mtime of every file
  under `data/`, `logs/`, `outputs/` and `config/`; no contents read): 801 files, `e715a34c…`
  before and after the full suite (unchanged).
- Docs: KT PDF rebuilt (source
  `91c7e427ec024d18a2d4c73185a81612a6d55aae9e84bf314e27dd8ef9ef260c`, 394,881 bytes);
  `check_kt_docs` errors `[]`.

## Documentation

- [KT](../../../TECHNICAL_DESIGN.md) section 10, Delivery: market notices list an index change to
  a shelf idea; an account's own alerts include an index change to a stock it holds or watches,
  with the once-only rule, the skipped unreadable account and the owner-watches example. Section
  12: the fixes outside the SA numbering include FIX-009, and its roadmap row is added as `Open`
  until the commit, as FIX-008's was. PDF rebuilt. The KT header revision is bumped with the
  commit.
- [ARCHITECTURE](../../../ARCHITECTURE.md) Operations, Delivery: an index change reaches only the
  accounts that hold or watch the stock, unless it is a shelf idea.
- [PRODUCT_MAP](../../../PRODUCT_MAP.md): the Index watch row.
- [CODEBASE](../../../../CODEBASE.md): the `index_watch.py` tree note and module row.
- [Testing guide](../../../TEAM_TESTING_GUIDE.md): case **10-H** (a stock only the owner holds
  or watches changes index; the member's phone, mailbox and Alerts tab show nothing; a shelf idea
  reaches both once), and HT-10's related PI list.

## Manifest and digest

- **Review input:** [FIX-009-manifest.json](FIX-009-manifest.json), 11 files. The SHA-256
  of its LF bytes is **`11c2c62062516c81a8ecbfd3378a7369d452237d80c5268625f013ae9168005a`**, and `kt_manifest.py verify` gives 0 mismatches.
  - Code (2): `core/delivery/index_watch.py`, `core/delivery/alerts.py`.
  - Tests (3): the new file, `test_index_watch.py`, `test_operator_notices_owner_only_fix008.py`.
  - Docs (6): CODEBASE, ARCHITECTURE, PRODUCT_MAP, the guide, the KT and its PDF.
  - Excluded: STATE, HANDOFF and this receipt (bookkeeping), and the owner's `docs/README.md`.
- **Diff digest:** **`57e5467ff6af7a608287ca0722d550481e6b4adff92ba0b30b36fa72b15069ed`**, 43,083 bytes over 10 paths (every manifest path except
  the PDF).
  - **The base** is `4c85eec`, which holds FIX-008 as accepted and committed; no uncommitted
    change sits under FIX-009's paths.
  - **To rebuild:** `analysis_data/fix009/diff_digest.py`: `git diff --no-color 4c85eec -- PATH`
    for tracked paths and `git diff --no-index --no-color /dev/null PATH` for the new test file,
    over the sorted paths, concatenated.

## Self-review

No critical, high or medium finding. The card's hard-review items:

- Readers of `_watched_symbols`: none remain outside historical plan documents. `run_index_watch`
  has one caller, the scheduler's `_weekly_review_job`, which logs the returned counts.
- Dedupe across the deploy: the sent-log key is unchanged, and the deploy-day test passes on the
  base and the change.
- A held shelf idea is sent once per account (three tests, mutants M2 and M11).
- No test reaches NSE or a transport: the NSE client is a fake, pushes and SMTP are recorded at
  their lowest seams, Resend is off, and with Atlas on rows are only queued.

Infos, most relevant first:

- **I1 (info, behaviour change). An account with no push subscription now hears about its own
  stocks.** Before, the broadcast reached only the market audience, so such an account was never
  told of an index change. Now its own changes reach it by email (when email is on) and its Inbox.
  This is the card's intent ("goes to that account"). Today both production accounts have push
  on, so nothing changes for them.
- **I2 (info). The skipped-account warning names the account's id** in the server log, as the
  brief's and the weekly review's per-account failures already do. Logs are owner-only (FIX-007),
  and the backlog surfaces repeats to the owner only (FIX-008).
- **I3 (info). A failed shelf delivery to an account in the market audience** is retried on that
  account's next emit (AUD-085), not in its own notice in the same run.
- **I4 (info). Symbol case.** Constituents are upper-cased; holdings and watchlist entries are
  upper-cased when added (`add_holding`, `add_watchlist`). Unchanged by FIX-009.

## Production check (after an owner-authorized deploy, read-only)

At the next weekly index check that reports a change to a held or watched stock, only the
accounts that hold or watch it get the notice, unless it is a shelf idea (guide case 10-H). Many
weeks have no change; then there is nothing to check until one occurs. FIX-008 is already pushed
(15:29 IST), so FIX-009 ships in a later commit and deploy, after its review is accepted and at
the owner's word.

Rollback is a revert. This receipt does not authorize deploying, pushing, changing production
variables or sending notifications.

## Next

A fresh-session review in a new conversation ("continue"), by [REVIEW.md](../REVIEW.md). Then
PR-001.
