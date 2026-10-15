# FIX-009 review receipt — index-change notices name only the account's own stocks

## Fresh-session review: ACCEPTED (2026-10-13)

**Story:** [FIX-009](../stories/FIX-009.md) · **Context:** fresh-session review, in a new
conversation opened with "continue", 13 Oct about 16:34–16:56 IST. It is not the implementing
conversation. Peers `stockagent-main-e3` (the implementer), `stockagent-main-06` and
`splitfamilia-a9` were idle. `stockagent-main-25` had just started and confirmed it was not
working on the PI.
**Reviewed revision:** the uncommitted working tree on `4c85eec`, pinned by review input
`11c2c62062516c81a8ecbfd3378a7369d452237d80c5268625f013ae9168005a` (11 files) and diff
`57e5467ff6af7a608287ca0722d550481e6b4adff92ba0b30b36fa72b15069ed` (43,083 bytes).
**Verdict:** **accepted**. No critical, high or medium finding; one low test gap routed to SA-031.

This review committed, pushed and deployed nothing. It read no production state, changed no
production variable and sent no notification. Its only repository edits are bookkeeping: this
receipt, STATE, HANDOFF and the SA-031 card. No reviewed file was changed.

**In one example.** The owner watches QOWNWAT. Member A holds QMEMAHLD. Members A and B both hold
QBOTHHLD. QSHELFHD is a shelf idea that the owner and member B hold. Member B has no push
subscription. The Sunday 18:00 index check finds that all of them changed.

- The owner's two phones and mailbox each get two notices: QOWNWAT in one, and the shelf's
  QSHELFHD and QSHELFNO in the other. QSHELFHD comes once.
- Member A gets its own three stocks and the shelf's two.
- Member B gets one email, with QBOTHHLD and QSHELFHD. It does not get the shelf idea it doesn't
  hold, because it is outside the shelf's audience.
- Nobody is told about another account's own stock, or about QNOBODY.
- **Before this change:** both push-subscribed accounts were told about all six watched stocks,
  and member B was told nothing.

### Review input verified

- `kt_manifest.py verify FIX-009-manifest.json`: 11 files, 0 mismatches. The manifest's LF bytes
  hash to `11c2c620…`. The reviewer also recomputed all 11 git blob ids with `git hash-object`;
  each matches.
- The diff was rebuilt with the reviewer's own shell loop, not the implementer's script:
  `git diff --no-color 4c85eec -- PATH` for tracked paths, `git diff --no-index --no-color
  /dev/null PATH` for the new test file, over the 10 sorted non-PDF paths, concatenated. The result
  is 43,083 bytes, `57e5467f…`, identical.
- `HEAD` is `4c85eec`. The only other worktree changes are STATE, HANDOFF, the implementation
  receipt and manifest, and the owner's `docs/README.md` probe line, none of them in the manifest.
- The reviewer's base copy, `git show 4c85eec:core/delivery/index_watch.py`, has blob `655861b8`,
  as the receipt says.

### Contract checked

- **Routing** (`core/delivery/index_watch.py:133-144`).
  - Events about active shelf ideas go to `emit_alerts_broadcast`.
  - For each account, events about its held or watched stocks go to
    `emit_alerts(own, user_id=uid)`, one bundle per account.
  - A shelf idea is left out of an account's own bundle only when the broadcast's result
    (`users`) includes that account.
  - Every event's symbol is in the shelf or in some account's set, since `watched` is their union.
    So every event reaches exactly the accounts it concerns, plus the market audience for shelf
    ideas.
- **Identity.**
  - `PortfolioStore` requires `[A-Za-z0-9_-]{1,64}`, and the folder is the user id itself
    (`core/portfolio/store.py:47-51`). Directory-scan ids, Atlas ids (`atlas_store.user_ids()`),
    push-store ids and sent-log ids are therefore the same strings. `uid not in reached` can't
    misfire on a formatting difference.
  - An email goes only to the account's own address: SA-006's `resolve_recipient` has no fallback
    for a non-default account, so a member's own stocks never reach the owner's mailbox.
- **Missing data.**
  - Each account has its own `try`. A failed account lookup leaves every account out; that is
    the base's behaviour too, since one `try` covered everything there.
  - A shelf read failure leaves shelf ideas to their holders' own bundles: no leak, and
    non-holders miss the idea.
  - A quarantined portfolio reads as empty.
- **Repeats and the deploy day.**
  - The sent-log key `user_id|date|kind|symbol` is unchanged (`alerts.py:201-217`). Events an
    account received under the old broadcast are not sent again; events about another account's
    stock are no longer sent to it at all.
  - The outbox key includes a hash of the body (`outbox.py:123-131`), so an account's two
    same-titled bundles in one run are distinct rows. Both deliver, as the trace shows.
- **Callers.** `run_index_watch` has one caller, the scheduler's `_weekly_review_job` (Sunday
  18:00 IST), which logs the unchanged return dict. `_watched_symbols` has no remaining reader
  outside historical plan documents.
- **The FIX-008 guard.** `run_index_watch` is now classified as both a market site (shelf ideas)
  and an own-account site, and the guard passes.

### Independent adversarial examples

The reviewer's own trace is `analysis_data/fix009/review/test_rv_trace.py`, with 4 tests. It is
built to differ from the implementer's tests:

- **Production shape.** AUTH is on and Atlas is on: accounts come from a real `atlas.db` in
  signup order, through the real outbox and `drain_once`.
- **Entry point.** The run starts from the scheduler's own `_weekly_review_job`, with
  `run_weekly_review` stubbed and the snapshot redirected to the test's folder.
- **Data and reads.** Portfolio and shelf files are written through the real stores, and each
  account's Inbox is read over HTTP with its own session.
- **Accounts.** There are three: the owner, member A, and member B with no push subscription.
- **Edge cases the implementer's tests lack:** a stock held by two members, a dropped shelf idea
  that a member holds, and the unreadable account in the middle of the order.

1. **The Sunday job.** Every recipient gets exactly the set in the example above, the right
   number of times. Each outbox row holds only its account's allowed symbols. Each Inbox lists
   exactly its own and the shelf's records. QNOBODY appears nowhere.
2. **A same-day re-run after a failed snapshot write.** The same seven changes are found again.
   No new push, email or outbox row is created.
3. **An unreadable member A, read second of three.**
   - A's stocks reach nobody, and nothing is broadcast in their place.
   - Member B, read after A, still gets its own two stocks.
   - A still gets the shelf's two.
   - The warning names A.
4. **A failed index fetch.** Nothing is sent, and the stale snapshot is kept.

FIX-008's characterization of this leak
(`analysis_data/fix008/review/test_rv_trace.py::test_rv_characterize_…`) now fails at its
"member received BBB" assertion, as it should.

### Tests

| Code | The implementer's 40 tests (new file, `test_index_watch.py`, FIX-008 guard file) | The reviewer's trace (4) |
|---|---|---|
| Reviewed | 40 passed (66 with `test_alerts_wave_f.py` and `test_delivery_alerts.py`) | 4 passed |
| Base `4c85eec`, by the reviewer's own plugin (`RV_SWAP=base`, blob-checked) | **caught:** 17 failed, 23 passed. 11 of the new file's 15 fail on behaviour: the member received the owner's stocks, the orphan subscription received the default user's, the Atlas rows held every stock. The rest patch seams the base lacks. | **caught:** 3 failed (1–3); test 4 passes on both, as it should |
| The implementer's mutants M1–M11 (their `swap_plugin.py`) | caught, all 11 (their receipt) | caught 9 of 11; M4 (a failed lookup falls back to the default user) and M11 (who the broadcast reached is ignored, which only matters when delivery fails) survive, as expected: the trace has neither case, and the implementer's tests catch both |
| **X1** (reviewer's): `continue` becomes `break` after an unreadable account | **survives:** 40 passed | **caught:** test 3 |
| X2: an own bundle carries every watched event | caught: 8 failed | caught: 3 failed |
| X3: the card read literally (every account assumed to be in the market audience) | caught: 1 failed | caught: 3 failed |
| X4: a dropped shelf idea treated as an active one | caught: 11 failed | caught: 2 failed |
| X5: an unreadable account's events fall back to the broadcast | caught: 1 failed | caught: 1 failed |

Results are in `analysis_data/fix009/review/trace_vs_swaps.txt`, `trace_vs_impl_swaps.txt` and
`impl_tests_on_base.txt`.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (tests; code correct) | `core/delivery/index_watch.py:65-72`; `tests/unit/test_index_watch_own_accounts_fix009.py:302-316` | No test pins that accounts read after an unreadable one still get their own events (acceptance 1, "the other accounts still get theirs"). Mutation X1 (`continue` → `break`) passes all 40 tests. The read-error test makes the member unreadable, and in the directory scan `primary` comes before `u_…` on Windows (names listed sorted, checked), so no account follows it; on Linux the order depends on the file system. The reviewer's trace test 3 catches X1. | **Routed** to [SA-031](../stories/SA-031.md), with the fixture. |
| I1 | Info (pre-existing; behaviour change already noted as the implementer's I1) | `core/delivery/channels.py:630-636`; `core/delivery/outbox.py` | With Atlas on, an account with no push subscription now gets its own index changes. Its bundle queues a push row as well as an email row, and the push row is dead-lettered with a WARNING ("no push subscriptions registered"); the trace's log shows it. A morning brief to such an account does the same today, so this is not new behaviour of the outbox. With SA-011 the warning can surface in the owner's backlog. Today both production accounts have push on. | No action. |
| I2 | Info (docs) | `docs/TEAM_TESTING_GUIDE.md` 10-H | 10-H has no status line yet. 10-G's (FIX-008) was added with its commit. | Add "FIX-009: accepted 2026-10-13, committed as `…`; production verification pending" with the commit. |

The implementer's infos I1–I4 were checked and stand: an account with no push hears about its
own stocks; the warning names the account id in owner-only logs; a failed shelf delivery retries
only on a later emit; symbol case is unchanged.

### Commands and results

Windows 11, Python 3.13, the project's `.stockai` environment; every pytest run goes through
`tests/hermetic.py` (the repository's and the review folder's `conftest.py`).

| Check | Command | Result |
|---|---|---|
| Input | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-009-manifest.json`; `git hash-object` per path; the reviewer's diff loop (above) | 0 mismatches; `11c2c620…`; diff `57e5467f…`, 43,083 bytes |
| Focused | `python -m pytest tests/unit/test_index_watch_own_accounts_fix009.py tests/unit/test_index_watch.py tests/unit/test_operator_notices_owner_only_fix008.py tests/unit/test_alerts_wave_f.py tests/unit/test_delivery_alerts.py -q -p no:cacheprovider` | 66 passed |
| The reviewer's trace | `PYTHONPATH=analysis_data/fix009/review python -m pytest analysis_data/fix009/review/test_rv_trace.py -q -p no:cacheprovider -p rv_swap_plugin` | 4 passed |
| Base and the reviewer's mutants | the same with `RV_SWAP=base\|X1..X5`, over the trace and the implementer's 40 tests | table above |
| The implementer's mutants vs the trace | `FIX009_SWAP=<mode> PYTHONPATH=analysis_data/fix009 python -m pytest -p swap_plugin analysis_data/fix009/review/test_rv_trace.py` | table above |
| Guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| Docs | `PYTHONPATH=analysis_data/kt_docs_deps python scripts/docs/check_kt_docs.py` | errors `[]`; the PDF's source digest `91c7e427…` equals the current KT; 41 pages |
| Full suite | `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count tests` | **4508 passed, 12 skipped, 0 failed** (6 min 56 s, about 16:40–16:47 IST), the same count as the implementer's run |
| Runtime data | `python analysis_data/fix009/data_fingerprint.py` before and after the suite (path, size, mtime; no contents read) | 801 files, `e715a34c…`, unchanged |

**Documentation checked against the code:** KT section 10 (Delivery: market notices, an account's
own alerts, the once-only rule, the skipped unreadable account and the owner-watches example) and
section 12 (the fixes paragraph and the FIX-009 row `Open` until the commit); ARCHITECTURE
Operations; PRODUCT_MAP's Index watch row; CODEBASE's tree note and module row; guide case 10-H
and HT-10's related PI list. Each describes the reviewed behaviour.

**Not exercised:** production (not read); a real NSE response; the Linux directory order (the
finding's fixture removes the dependence); a real push service or SMTP server (recorded at
pywebpush and `smtplib`; Resend off).

### Acceptance checklist

| Card criterion | Verdict |
|---|---|
| 1. Each event goes to the accounts it concerns: own events by `emit_alerts(..., user_id=)` in one bundle; shelf ideas by `emit_alerts_broadcast`; a symbol that is both once per account; accounts from `active_user_ids()` or the default user; an unreadable account skipped with a warning, never broadcast, the others still served | **Met.** Trace 1 and 3 and the implementer's tests. The "both" rule follows the recorded delegated design call: an account outside the market audience gets the held idea in its own bundle. That keeps "once" and is the card's intent; the reviewer agrees with it. The "others still served" part is correct in the code; its test gap is L1. |
| 2. Tests with a fake NSE, real stores and shelf, recording transports; the four-symbol example, Inbox, no accounts, unreadable portfolio, first snapshot and failed fetch, the guard updated | **Met.** No test reaches NSE, SMTP, Resend or a push service. |
| 3. Documentation as current design: KT 10 and 12 with the PDF, PRODUCT_MAP, CODEBASE, a human test case | **Met.** The PDF matches its source. |
| Hard review: readers of `_watched_symbols` and callers of `run_index_watch`; the deploy-day dedupe; a held shelf idea not sent twice; no real NSE or transport | **Checked**, as above. |

### Production verification

`pending_deployment`. FIX-008 is already pushed (15:29 IST), so FIX-009 ships in a later commit
and deploy, at the owner's word and in a job-free window, not on a Sunday between 17:50 and 18:30
IST. With the commit: KT section 12's FIX-009 row goes from `Open` to `Done`, the KT header
revision is bumped, the PDF is rebuilt, and guide 10-H gets its status line (I2).

Read-only check after that deploy: at the next Sunday 18:00 index check that reports a change to
a held or watched stock, only the accounts that hold or watch it get the notice, unless it is a
shelf idea (guide 10-H). Many weeks have no change, and then there is nothing to check.

Rollback is a revert. This receipt does not authorize deploying, pushing, changing production
variables or sending notifications.

### Decision

**Accepted** for the reviewed revision above. FIX-009 is `done`, with production verification
`pending_deployment`. Follow-ups: L1 goes to SA-031; I1 needs no action; I2 is done with the
commit. The next ready story is **PR-001**, in a new conversation; it has not been started.

Reviewer tooling, in the ignored `analysis_data/fix009/review/`: `rv_swap_plugin.py` (`RV_SWAP`),
`test_rv_trace.py` with its `conftest.py`, `base/index_watch_4c85eec.py`, `rv.diff`,
`full_suite.txt`, `data_before.txt` and `data_after.txt`, and the result files named above.
