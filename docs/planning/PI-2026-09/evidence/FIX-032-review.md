# FIX-032 — fresh review receipt

**Story:** [FIX-032](../stories/FIX-032.md): a home-page watchlist save keeps what it does not
show, and a removal there leaves the daily review. Implementation receipt:
[FIX-032-implementation.md](FIX-032-implementation.md).

**Review context: fresh session.** Session `stockagent-main-17` [707fb1], a new conversation
opened with "continue", Monday 16 Nov 2026 from about 13:54 IST. The implementer (`-1a`) and
the peers `-6d` and `-31` were idle. `origin/main` was `1913017` after a fetch, so nothing had
arrived from the other device. `main` is `2f0c777`, 1 ahead, not pushed. Production was not
read in this conversation. The owner's `FIX-032-P1` read (about 13:50 IST) was already recorded.
No LLM was called, no message sent, nothing committed, pushed or deployed. PR-014's step 7 waits
for today's 16:30 run, so this review went first, as the handoff says.

**Lane:** decision path, confirmed. The story decides which watchlist buy candidates survive a
save, and who can change which account's managed entries.

**Verdict: ACCEPTED.** One low finding, pre-existing (R1), goes to the backlog.

## Review input, verified

`analysis_data/fix032_review/rv_digest.py` writes nothing tracked. It uses a temporary index, so
the real index is untouched. Run at the start (`digest_start.json`) and the end
(`digest_end.json`):

| Check | Start | End |
| --- | --- | --- |
| Manifest SHA-256 | `7f30781e…` = receipt | `7f30781e…`, unchanged |
| `kt_manifest.py verify` | 13 files, 0 mismatches | 13 files, 0 mismatches |
| Diff against `2f0c777` (PDF excluded) | `bbf40aee…`, 69,338 B = receipt | `bbf40aee…`, 69,338 B, unchanged |
| Changed outside the manifest | bookkeeping (STATE, HANDOFF, the receipt, the manifest), BACKLOG, SA-026, and the peer's PR-033, PR-034, README, SA-041 | the same, plus this review's receipt and its BACKLOG entry B-6 |

The working tree's end tree differs from the receipt's (`532ae48`) only by bookkeeping: the
receipt and STATE gained the `FIX-032-P1` result after the digest was taken.

## Contract checked

The card's intended results, its five acceptance lines and its two hard-review questions. The
receipt's decisions F32-D1 to F32-D7 and its four questions for the reviewer. I traced from the
request to the stored watchlist, then to the managed list, then to the scheduler's list of
enabled tickers (what the 16:30 review reads).

## Independent cases

These are reviewer cases written from the card, not from the code:
[`analysis_data/fix032_review/test_rv_fix032.py`](../../../../analysis_data/fix032_review/test_rv_fix032.py)
(an ignored folder; on another device, write them from this section). Real routes run through
FastAPI's TestClient, with real portfolio files and a real managed file in the test's folder.
Atlas is on and prices are given. The expected values come from each case's own fixture or from
an oracle that states the card's rule.

- **RV1: 60 random sequences of 30 operations by three users, checked against an oracle.**
  - The operations: the home page's add and remove in the new form, in random spellings; an old
    page's whole-list save of a random part of the list, with or without one added stock; the
    API's watch add and delete; the API's holding add and delete; the autopilot's note of an exit.
  - The oracle keeps each user's watchlist (symbol to source) and each managed entry (origin,
    enabled) from the operations alone, applying the card's rule. A removal disables an entry
    only when no portfolio holds the stock and no user's own watchlist lists it; the autopilot's
    note does not count. A held entry that only a watch keeps turns weekly. Original entries
    never change.
  - After every operation, every user's watchlist, every managed entry (origin, cadence,
    enabled), the page's answer and the API's `demoted` equal the oracle's.
  - **60 pass.**
- **RV2: a quarantine the real store makes.** v's `portfolio.json` (holding BACK, watching NEWCO)
  is corrupted, and one `PortfolioStore.load` quarantines it. This checks that the store's file
  name matches what `_quarantined_users` looks for; the story file names the file by hand. Then:
  - u's autopilot exits BACK: the sale stands, BACK's held entry stays enabled, and the log says
    "no managed entry released … quarantined and not restored for v";
  - w's removal of NEWCO on the home page leaves NEWCO enabled, and the log says "NEWCO not
    demoted";
  - v's file is restored by hand, without BACK. The next run releases BACK.
  - **Passes.**
- **RV3: the consumer.** `log_buffer.get_active_tickers_with_sector()`, the scheduler's list of
  enabled tickers. v and w watch BACK through the API, so BACK is weekly. v removes BACK on the
  home page: BACK stays (w watches it). v removes MARUTI, which is not on v's list: nothing
  changes. w removes BACK: BACK leaves the list. **Passes.**
- **RV4: a page loaded before two server-side writes.** The page saw MARUTI only. Then a real
  autopilot exit writes OLD's note, and a shelf idea NEWCO arrives. The old page saves
  `[MARUTI, HEROMOTOCO]`: the answer is MARUTI, OLD, NEWCO, HEROMOTOCO. The new page then removes
  MARUTI: OLD and NEWCO stay byte for byte. **Passes.**
- **RV5: finding R1** (below), as a strict xfail. **xfailed, as expected.**

**On the code before the story** (a detached worktree at `2f0c777` in the scratchpad, removed
afterwards):

- **With the new request shape:** every case fails. The old route refuses `add` and `remove`
  (422). RV3 and RV4 fail on the rule too.
- **With exactly the old page's request** (`RV_OLD_PAGE=1`: the whole list the page read, with
  the one change): **all 63 fail, each on the defect itself.**
  - RV1 and RV4 fail on dropped items (RV5 of FIX-028's review). Example: `[] == ['ZEDCO']`, and
    `['MARUTI', 'HEROMOTOCO']` where `MARUTI, OLD, NEWCO, HEROMOTOCO` was expected.
  - RV3 fails because BACK stays enabled after the last watch ends on the home page (RV4b).
  - RV2 fails because BACK is released while v's account is quarantined (RV6).

  So the oracle catches the original defects, not only the change of request shape.

FIX-028's reviewer cases (`analysis_data/fix032/rv/`, compared line by line with
`analysis_data/fix028_review/test_rv_fix028.py`: they differ only in the three removed xfail
marks, plus RV4b's one changed request line in the second copy):

- with RV4b's page request: **455 passed**;
- as written: RV5 and RV6 pass, and RV4b fails with `assert ['BACK'] == []`, exactly as the
  receipt says (F32-D2, below).

## The implementer's decisions

- **F32-D1, the save names the change: agreed.** Read literally, the card's "items it does not
  offer stay as they are" would make the remove button useless for those items. The card's own
  second example removes BACK on the home page. A change-only body serves both, and it cannot
  drop what the page never saw.
- **F32-D2, the whole-list form only adds: agreed.** A list that omits a stock cannot be told
  from a stale page. RV4 shows the example: a stale page's `[MARUTI, HEROMOTOCO]` would drop OLD
  and NEWCO under any reading that removes.
  - **The card's acceptance line on RV4b is met in substance.** RV4b tests the home page's
    removal. The page now sends `{"remove": ["BACK"]}`; RV4b passes with it, and so do RV3 and
    the browser test.
  - **What the old form still costs:** a tab opened before the deploy hides a removed row
    without asking the server, and the stock comes back on reload. The files are served by
    `FileResponse` with no Cache-Control header, so a reload revalidates (inference, not
    measured). In production one account's watchlist is in use (`FIX-032-P1`). The deploy note
    below says to reload the open home page.
- **F32-D3, the question lives in `demote_symbol`: agreed.** The API's two deletes and the home
  page now ask one function. The holding delete used to count the autopilot's note as a watch.
  RV1 checks all three against the oracle.
- **F32-D4, a held entry that only a watch keeps turns weekly: agreed.** It is FIX-028's rule.
- **F32-D5, an unrestored quarantine stops every release: agreed.** It is the card's "like an
  unreadable file". A quarantined account's holdings are unknown, so no finer rule is safe.
  - Cost: until the file is restored, sold stocks keep their daily review. That shows only in the
    log. The quarantine itself sends the owner a critical alert, and restoring the file ends it.
  - `FIX-032-P1` read 0 unrestored quarantines in production.
- **F32-D6 and F32-D7: agreed.** `demoted` now means "this call disabled it". No client reads it:
  a search of `src/`, `services/`, `core/`, `scripts/` and `tests/` finds only this story's
  tests. The UI_SPEC row lists the field, but no page reads it.

## The receipt's questions and the card's

1. **The change-only body and RV4b:** above (F32-D1, F32-D2).
2. **Every release or only that account's:** above (F32-D5).
3. **Readers of `demote_symbol`'s old answer:** none (F32-D6).
4. **Lock order: no inversion.**
   - The autopilot takes the account's lock, then the list's (`_follow_holdings` under
     `store.locked()`).
   - The route takes the account's lock for the add and remove, lets it go, then calls
     `demote_symbol` (`ui_data.py:1235`, `:1247`).
   - `demote_symbol` takes the list's lock and reads portfolio files directly, with no account
     lock.
   - The API's holding add promotes after its lock. The API's watch add and the shelf's promote
     take the two locks one after the other, never nested.
5. **Card: does any other path save a watchlist from a partial view?** No. My own search of
   `src/`, `services/`, `core/` and `scripts/` finds the writers the receipt names, plus
   `scripts/atlas_etl.py`, which only adds. Only the home page's PUT saved a whole list.
6. **Card: must the home page show the autopilot's notes?** Not decided here, as the card says.
   The page shows every watchlist symbol with a remove button. Removing a note leaves the daily
   review only when nobody holds or watches the stock.

## Findings

| # | Severity | Where | Trigger, observed against expected | Impact | Disposition |
| --- | --- | --- | --- | --- | --- |
| R1 | Low, pre-existing order, latent | `services/api/routes/portfolio_api.py:272` (`promote_symbol`) before `:277` (`add_watchlist`) | w adds BACK through `POST /portfolio/watchlist` while v removes BACK (the API's delete or, since FIX-032, the home page). When v's demotion lands between w's promote and w's save, it sees nobody watching and disables BACK. w then watches BACK with its entry disabled. Expected: enabled. Fixture: RV5 (strict xfail) | BACK, a stock w watches, leaves the daily review until someone promotes it again. It needs two users acting on one stock within milliseconds. The shelf's promote already saves first. No buy, sell, size or grade reads the entry directly | [BACKLOG](../BACKLOG.md) B-6, with the fix (save the watch first) and its trigger |

**Not findings, recorded:**

- The quarantine shows only in the log after its alert (F32-D5, above).
- An old tab's removal does nothing (F32-D2, above).
- With Atlas off (not production), removing the last item of the global list brings the default
  list back, because `_load_watchlist` treats `[]` as missing. This is pre-existing and the
  same before FIX-032.
- BACKLOG's table had a blank line between B-4 and B-5, which split the table. Fixed with B-6.

## Documentation

Each of these matches the reviewed behaviour:

- KT section 6: the release paragraph, its example, and "the home page's watchlist save names
  only the change";
- AUTOPILOT_GUIDE section 12 and its route table;
- CODEBASE's three route rows;
- UI_SPEC's `WatchlistPane`;
- guide case 07-R (each expected result traced against the rule) and 07-P's note.

The limits FIX-028's review added are gone. `check_kt_docs` gives `errors: []`, and the PDF
(72 pages) matches its source `96a086c8`. KT section 12 still lists FIX-032 as Open, and 07-R
says "fresh review pending": commit-time edits below.

## Commands and results

All run from the repository root with `.stockai/Scripts/python.exe`, on Windows, under the
suite's hermetic guard (no network).

- `analysis_data/fix032_review/rv_digest.py start` / `end`: as in the table above.
- Focused, once: `pytest -q tests/unit/test_watchlist_save_fix032.py
  tests/unit/test_ui_no_invented_figures_pr001.py tests/unit/test_atlas_singletons.py
  tests/unit/test_api_auth_lockdown.py tests/unit/test_autopilot_api.py
  tests/unit/test_sold_stock_leaves_review_fix028.py`. Result: **383 passed**, 0 skipped. The
  browser suite ran, including the story's browser test.
- `pytest -q analysis_data/fix032/rv/test_rv_fix028_fix032.py`: 455 passed.
  `… test_rv_fix028_unxfailed.py -k "rv4b or rv5 or rv6"`: 2 passed, RV4b failed (expected).
- `pytest -q analysis_data/fix032_review/test_rv_fix032.py`, the final file: **63 passed, 1
  xfailed** (RV5, strict).
- On `2f0c777` (worktree): 63 failed with the new shape, and 63 failed with `RV_OLD_PAGE=1`
  (`rv_base_oldpage.txt`).
- `scripts/docs/check_kt_docs.py`: `errors: []`. `scripts/ci/check_broad_except.py`: OK (148
  grandfathered).
- **Full suite**, once, on the reviewed tree (`analysis_data/fix032_review/run_suite.sh`,
  14:14–14:36 IST): **6,748 passed / 12 skipped / 1 xfailed / 1 failed**, return code 1, 22m17s.
  - **The one failure is environmental.** `tests/unit/ops/test_watchdog_backup.py::
    test_nightly_job_to_watchdog_end_to_end` hit `PermissionError: [WinError 5]` on `os.replace`
    of `backup_status.json.part` in its own temp folder. That is the Windows file-lock flake
    already seen in FIX-029's and FIX-031's runs.
  - Run alone it passed 5 of 5 (`flake_rerun.txt`). Neither `services/data/backup.py` nor its test
    differs from `2f0c777`, and no FIX-032 file touches backups.
  - The implementer's full suite on the same code bytes had 0 failures (6,749 passed).
  - `git status` changed during the run only by this receipt, written meanwhile; the suite wrote
    nothing.

**Not exercised:**

- The implementer's mutants (20 of 20) were not re-run. The baseline runs above stand in for
  them.
- The page against a running server: the browser test answers the API from the test.
- Atlas's `user_instruments` mirror is stubbed in every case, as in the story file.
- Production was not read by this review.

## Acceptance checklist

- [x] The card's example through the real route with Atlas on: the four items stay, then the
  other four stay (story file, RV1, RV4).
- [x] v's removal of BACK on the home page disables it. With another user watching or a
  portfolio holding it, it stays enabled (story file, RV1, RV3).
- [x] A quarantined, unrestored account holding BACK: another portfolio's exit releases
  nothing, and the log says why (story file, RV2 with the store's own quarantine).
- [x] FIX-028's RV5 and RV6 pass as written. RV4b passes with the page's request, and fails as
  written by F32-D2, which this review accepts.
- [x] Docs: KT section 6 and AUTOPILOT_GUIDE section 12 drop the limits; guide case 07-R.
- [x] Housekeeping: `deep_dive.py`'s comment at the `sold` flag.

## Verdict and what follows

**ACCEPTED** for the reviewed input: the uncommitted tree over `2f0c777`, manifest `7f30781e`,
diff `bbf40aee`. STATE: FIX-032 `done`, production `pending_deployment`.

**Commit-time edits** (at the owner's word, with the commit):

1. KT header: "Code inspected" becomes the FIX-032 code commit; edition 2026-11-16.
2. KT section 1, first paragraph: the inspected code holds FIX-032 beyond production's
   `1913017` (committed, not deployed).
3. KT section 12: FIX-032's row, "Open" becomes "Done".
4. Guide 07-R status: "accepted on 2026-11-16 (fresh review); not deployed".
5. Regenerate the PDF. `check_kt_docs` must then give `errors: []`.

**Deploy** (the owner's word and a job-free window, as always):

- `FIX-032-P1` has passed, so nothing blocks it. A docs-only push of `2f0c777` is already
  waiting for after today's 16:30 run; FIX-032 can go in the same push.
- After the deploy, reload any open home page (F32-D2).
- The deploying conversation adds a dated watch row to `pending_production_checks`
  (`FIX-032-W1`) for one week after the deploy. It re-runs `analysis_data/fix032/prod_probe.py`.
  Pass: `quarantined_not_restored` 0; P3 (enabled watchlist entries nobody holds or watches) 0;
  no user-added or shelf-promoted watchlist item lost without a removal.

**Next `continue`:** PR-014 step 7 from about 17:10 IST today (its own conversation), then
PR-033.
