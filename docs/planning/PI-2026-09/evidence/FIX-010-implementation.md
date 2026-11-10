# FIX-010 — implementation receipt

**Story:** [FIX-010](../stories/FIX-010.md) · **Phase:** implementation, with same-conversation
self-review only · **Date:** 2026-10-15, about 20:30–21:47 IST · **Status after this phase:**
`review_required`

**How this phase came about.** The phase ran in the same conversation as PR-001's re-review and
FIX-010's planning. The owner asked for it: "ya go ahead on you suggestions and commit and push
at the end". That instruction overrides the one-phase-per-conversation rule for this story. The
fresh review still happens in a new conversation, after the commit and push, as for FIX-005 and
FIX-004 change 1. Peers were idle.

**Baseline:** `4c85eec` plus the accepted, uncommitted PR-001 work (manifest `1c7ea945`) and
FIX-009 work (manifest `11c2c620`). FIX-010 layers on five PR-001 files and five docs:
`ui_data.py`, `portfolio.jsx`, PR-001's two test files, and CODEBASE, PRODUCT_MAP, the guide, the
KT and UI_SPEC. Their pre-FIX-010 bytes were snapshotted to the ignored
`analysis_data/fix010/base/` before any edit, each checked against PR-001's manifest or `HEAD`.

**The fresh review requested changes (16 Oct). Rework 1 (16 Oct) is the next section; the first
implementation's record follows it.**

## Rework 1 — 16 Oct 2026 (implementation, after the review's `changes_requested`)

**Phase:** implementation (rework 1), a new conversation opened with "continue" on 16 Oct 2026,
from about 09:20 IST to about 11:00 IST (session stockagent-main-5f). It is not the reviewing
conversation. Same-conversation self-review only. **Status after this phase:** `review_required`;
a fresh re-review happens in another new conversation. The ten listed peer sessions were idle
at the start.

- **Input:** the reviewed code, committed as `ec3f336` and unchanged at `HEAD` (`c31136b`), with
  the review's input preserved as [FIX-010-manifest-review1.json](FIX-010-manifest-review1.json)
  (`900c8f27…`). `kt_manifest.py verify … --rev HEAD`: 15 of 18 files match; the KT, its PDF and
  the guide differ only by the commit-time KT bump and status lines the review accounted for.
  The rework diff is therefore taken against `HEAD`.
- **Findings addressed:** [the review](FIX-010-review.md) M1 is fixed; the recommended L1, L2
  and L3 are taken; the optional I5 is fixed. I1 to I3 need no change here (I3 is for SA-031).
- Nothing was committed, pushed, deployed or configured, no production state was read and no
  notification was sent.
- **Superseded statements in the sections below:** "32 tests" and "11 browser tests": see Tests
  below. Self-review's I5 ("a cut-off at the earliest live row … less a margin would avoid it"):
  done, per stock (I5 below).

### In one example (M1)

The test member opens Home. The newest analysis of a shared stock (managed, shelf or built-in)
is the one in the left column; the member's own stock was analysed half an hour ago.

| Newest shared analysis | Before this rework | Now |
|---|---|---|
| 2.5 hours old | "Updated recently" | "Updated 2h ago" |
| 13.5 hours old (the next morning) | "Updated recently", no dot | "Updated 13h ago", stale dot |
| 64 hours old (Monday 09:00 IST after Friday's 16:30 review) | "Updated recently", no dot | "Last analysis 2 days ago", stale dot |
| an unreadable time | "Updated recently", no dot | "Analysis time unknown", stale dot |

Both "Today" and "This month" panes follow the same rule; the member's own stock never makes
them look fresh.

### Changes, by finding

- **M1 (medium): Home's time labels never stated an age** (`services/api/routes/ui_data.py`,
  `_freshness_label`). A `run_at` without an offset (the writer's and the backfill's naive UTC)
  is read as UTC before the age is taken. The two identical branches (under 6 h, under 24 h) are
  one. The `except Exception` that turned every `TypeError` into "Updated recently", not stale,
  is narrowed to the parse (`ValueError`), whose answer is now "Analysis time unknown", stale; its
  entry leaves `scripts/ci/broad_except_baseline.txt` (the guard requires the baseline exact).
- **L1 (test gap): the async exit with enforce.**
  `test_the_row_holds_the_verdict_after_the_decision_gate` runs both exits (`sync-exit`,
  `async-exit`), with a missing price and the gate on `enforce`.
- **L2 (sign-out kept the previous viewer's list)** (`src/frontend/prototypes/data.jsx`,
  `index.html`). `saForgetLearnings` drops `PORTFOLIO_LEARNINGS` and `__learningsLive`, re-renders,
  and moves a viewer counter on. `saClearToken` calls it, and every change of account passes
  through `saClearToken`: the Sign out button, an expired session (the fetch wrapper's 401) and a
  deleted account. `saLoadLearnings` notes the counter when it asks and discards an answer that
  arrives after a sign-out. Demo mode keeps its samples. The call in `index.html` is guarded, so
  an old cached `data.jsx` still renders (I6 below).
- **L3 (guide 11-K).** The third stock is a managed one outside the 16 automobile stocks (the
  16:30 review analyses only managed stocks). The owner analyses the held stock once on request,
  so it has a row to hide; the owner's own check is added (search and current verdicts show it,
  not the member's). The case also checks the panes' time labels (evening, next morning, Monday)
  and an account switch on one tab.
- **I5 (backfill cut-off)** (`scripts/backfill_score_history.py`). Nothing is copied from
  `SAME_RUN_SECONDS` (60) before a stock's first live row onward. An analysis logs its run a few
  milliseconds before it writes its live row, so the log's copy of that analysis sat just before
  the old cut-off and was copied once more. This matters once live rows exist, for example an
  `apply` after a `remove` (the documented undo). Production's 16 Oct apply found no live row, so
  it is unaffected. The count keeps its key, `skipped_at_or_after_live_rows`.

### Design decisions (delegated, recorded)

- **An unreadable time is "Analysis time unknown", stale,** not the old "Updated recently", not
  stale: the label never claims recency it cannot date (PR-001's rule).
- **One drop point for the list (sign-out), plus the late-answer check,** rather than also
  clearing before every fetch: every account change already passes through `saClearToken`, and
  clearing on each fetch would blank the list on any future same-account re-fetch. The browser
  tests show each half is needed (variants `noclear`, `nogen` below).
- **I5 by a one-minute margin, not by refusing `apply` when a live row exists:** refusing would
  block re-applying after a `remove`, the one time live rows exist. The cost: another analysis of
  the same stock logged in the minute before its first live row is not copied, one past row
  fewer and never a false change.
- **"Live" for an analysis under an hour old is unchanged** (I7 below).

### Tests

- **Story file** `tests/unit/test_score_history_fix010.py`: 32 → 45 tests.
  - the gate test on both exits (+1, L1);
  - `test_home_states_the_age_of_the_newest_shared_analysis`: rows written by the real
    `ScoreStore.save` (clock faked) for the managed stock at 2.5, 8.5, 13.5, 30 and 64 hours, the
    shelf stock 30 hours earlier and the member's own stock half an hour ago; through
    `/ui/bootstrap` as the member, with Atlas off and on (+10). Expected values worked by hand from
    the rule: label, `runAt` = the managed row's stored `run_at` (read with plain SQL), `isStale`;
  - `test_the_label_reads_a_time_with_or_without_an_offset_and_never_invents_an_age`: naive,
    `+00:00` and `Z` forms 3.5 hours old all read "Updated 3h ago"; an unreadable time; no rows
    (+1);
  - `test_a_mid_day_backfill_records_each_analysis_once`: runs logged two days and 90 seconds
    before, and the live analysis's own log 4 ms before its live row (written by the real
    writer); dry run 2 to insert and 1 cut; after apply, three rows for three analyses (+1).
- **Browser** `tests/frontend/no_invented_figures.test.mjs`: 11 → 13 tests.
  - "signing out drops the verdict changes; a failed fetch for the next account shows none": the
    member's own change is on Portfolio; Sign out (the real button); the list is `null` at the
    login screen; a second member signs in and that account's `/ui/learnings` answers 503; no
    QMYOWN anywhere and no section;
  - "an answer for the previous viewer that arrives after the next sign-in is discarded": the
    first viewer's answer is held 4 seconds, over a sign-out and a second sign-in.
- **The new tests fail on the reviewed code** (in-memory or copied variants, no repo file
  written; `analysis_data/fix010/rework1/`):
  - `RW_SWAP=base` (`rw_swap_plugin.py`, `HEAD`'s `_freshness_label`): 11 of 11 freshness tests
    fail;
  - `RW_SWAP=base-backfill` (`HEAD`'s script): the mid-day test fails, `(3, 0) != (2, 1)`; the
    original backfill test passes on both;
  - the reviewer's `RV_SWAP=X1` (async exit writes before the gate): the `async-exit` case fails,
    `sync-exit` passes;
  - browser variants (`fe_variants.py`, `fe_variants.txt`): `base` fails both new tests;
    `noclear` (no drop at sign-out) fails both; `nogen` (no late-answer check) fails the
    late-answer test only; `stalejsx` (this `index.html`, the reviewed `data.jsx`) renders with
    no page error and passes the three existing learnings tests, and fails the sign-out test, as
    expected until the new `data.jsx` loads (I6).
- **The reviewer's tooling on the rework:** `test_rv_trace.py` and `test_rv_async_gate.py`, 13
  passed (the review had 9 of 12 and 1; M1 twice and I5 now pass).
- The review's story set (`test_score_history_fix010.py`, `test_ui_no_invented_figures_pr001.py`,
  `api/test_chat_brief_user_scope_fix005.py`, `test_chat_session_memory.py`) plus
  `test_broad_except_guard.py`: 170 passed (the review's 134, 13 new, the guard's 23); the story
  file alone 45 passed.
- `npm run test:frontend`: 30 of 30 (was 28).
- `check_kt_docs.py`: errors `[]`; PDF 43 pages, source `b67626c1…` = the KT's SHA-256.
- Full suite (`pytest -q -p no:cacheprovider -o console_output_style=count`): **4597 passed, 12
  skipped, 0 failed**, 19 min 47 s (10:28–10:48 IST, alongside browser runs). The working tree
  was unchanged after it.
- Environment: Windows 11, the project venv `.stockai` (Python 3.13), the hermetic boundary.

### Documentation

- KT section 10 (and the PDF): Home's panes state the age of the newest shared analysis, read as
  UTC, stale past 12 hours, with the Monday example; the verdict changes never outlive their
  viewer in the browser. Section 3's `score_history` row: the backfill's one-minute cut-off. The
  KT header and section 12's FIX-010 row are unchanged until the commit.
- UI_SPEC: `MARKET_TODAY`/`MARKET_MONTH` `freshness`; `PORTFOLIO_LEARNINGS` dropped at sign-out.
- Guide 11-K (L3, M1 and L2 checks; status line).
- PRODUCT_MAP: `ui_data.py` 3,975 lines.

### Manifest and digest

- **Review input:** [FIX-010-manifest.json](FIX-010-manifest.json),
  `89787068969160313e1ad59458bdc3b15aa1929540c2be2b27c2208124aa8e05`, 19 files: the first review's
  18 plus `scripts/ci/broad_except_baseline.txt`. `kt_manifest.py verify`: 0 mismatches. The
  first input stays preserved as [FIX-010-manifest-review1.json](FIX-010-manifest-review1.json).
- **Rework diff:** `279ccf94f99fc5cd71f565d39241e5f3ac423bf914618f28c00912400778c85e` (38,024
  bytes, 11 paths), `git diff HEAD` (`c31136b`) over the rework's payload paths, sorted, PDF
  excluded (`analysis_data/fix010/rework1/rw_digest.py`, writes `rw_code.diff`). The reviewed
  code diff stays `77cac0bd…` (`9db8ba7..ec3f336`).
- **Changed by the rework (12):** `services/api/routes/ui_data.py`,
  `scripts/backfill_score_history.py`, `scripts/ci/broad_except_baseline.txt`,
  `src/frontend/prototypes/data.jsx`, `index.html`, `UI_SPEC.md`,
  `tests/unit/test_score_history_fix010.py`, `tests/frontend/no_invented_figures.test.mjs`,
  `docs/TECHNICAL_DESIGN.md`, `docs/StockAgent-Three-Loops.pdf`, `docs/TEAM_TESTING_GUIDE.md`,
  `docs/PRODUCT_MAP.md`. Bookkeeping: STATE, HANDOFF, this receipt.

### Self-review

No critical, high or medium finding.

- **I6 (info, rollout).** The service worker serves cached `.jsx` first, so the first open after
  the deploy runs this `index.html` with the old `data.jsx`: the page works, and the sign-out
  drop starts from the second open (variant `stalejsx`). The rollout note stays "close and reopen
  the app once".
- **I7 (info, pre-existing).** An analysis under an hour old reads "Live". It is dated by
  `runAt` but not by the label; left as it is (SA-024 owns honest states on the remaining
  screens).
- **I8 (info, pre-existing).** `_rows_since` compares an offset-carrying `since` string with the
  naive `run_at` strings. Both share the format up to the microseconds, so the window is right
  except at the exact same microsecond. Not changed.

### Next

A fresh re-review in a new conversation ("continue"). Then PR-002. Production: the code is live
without this rework; the M1 fix needs its own deploy at the owner's word, after acceptance. The
after-16:30 probe of FIX-010's writer is unchanged.

## First implementation (15 Oct)

## In one example

The member holds DIXON, the owner holds BEL, and neither is managed or on the shelf.

**Before.** The 16:30 analysis turns DIXON from BUY to SELL. Nothing records it in the score
history. Home calls DIXON "Not analysed", Portfolio shows no change, and the chat finds no saved
analysis.

**Now.** The analysis writes DIXON's row.
- Home shows DIXON's score and verdict, and Portfolio lists "DIXON: BUY → SELL".
- The chat's current verdicts include DIXON.
- None of these screens names BEL to the member. If restoring the write had been the only change:
  - the chat's context, search, Home's market panes, the market summary and the sector comparison
    would have named BEL;
  - so would a stock someone else had only asked the chat about.

## What changed

- **The write** (`src/backend/shared/pipeline/base_orchestrator.py`).
  - `_record_score_history(report)` runs at both exits, `analyse` and `analyse_async`, right after
    `log_run_summary`. That is after the decision gate, so the row holds the verdict the run
    returns (`INSUFFICIENT DATA` when enforce withholds one).
  - A failed write (`sqlite3.Error`, `OSError`, or a report that will not serialize, `ValueError`
    or `TypeError`) is a warning. It never fails the analysis.
- **Who sees which stock** (`services/api/routes/ui_data.py`).
  - Shared stocks, from `_shared_symbols()`:
    - the built-in universe;
    - the managed list, which `GET /ui/tickers/managed` already serves to everyone;
    - the shelf's active ideas.
  - The viewer's own stocks, from `_own_symbols(user_id)`: holdings and watchlist, plus the global
    watchlist when Atlas is off. It reads only an existing portfolio, like the chat's brief
    (FIX-005), so the read never creates an account's folder. No user id means an anonymous
    request while sign-in is required: it owns nothing and never stands in for the default user.
  - Both reads fail closed: an unreadable list adds nothing.
  - `_only_visible(rows, symbols)` filters store rows. It is applied to:
    - `/ui/learnings`, now with the session (`get_current_user_optional`), which walks the visible
      stocks instead of the 16 built-in ones and returns `{items, since}`;
    - `/ui/search`'s thesis-text match, with the session;
    - the chat's `_ctx_current_verdicts` and `_ctx_recent_history`, with the caller's
      `user_id`, through `_build_chat_context` and the history tool;
    - `/ui/bootstrap`'s market panes (pulse, one-liners, drivers, "This month" votes) and
      `/ui/market/summary`, shared stocks only;
    - `services/api/routes/analytics.py`: `/analytics/sector-comparison` and the score index
      behind the RL export and Power BI feed, shared stocks only.
- **Agent scores.** The writer stores `{raw, weight, weighted}` per agent. Home's "This month"
  votes did `float(value)` on each value, so the writer's rows made `/ui/bootstrap` raise
  `TypeError` (reproduced on the base code). `_agent_score()` now reads `raw`, and takes a plain
  number as it is. The suggestions' "why" line uses it too.
- **The watchlist.** A watched stock outside the built-in universe shows its score history row,
  with no price fetched ("—"). A stock with no row is still "Not analysed".
- **The empty case.** `since` is the date of the oldest kept run among the listed stocks.
  Portfolio reads "No verdict changes since 16 Sept", or "No verdict changes recorded yet" with
  no date (`portfolio.jsx`, `fmtLearningsSince`).
- **The backfill** (`scripts/backfill_score_history.py`, new). It copies `run_summaries` runs into
  `score_history`:
  - **Rows:** naive-UTC `run_at`, as the writer writes; agent scores as `{raw}`; thesis empty; a
    `{"backfill": "run_summaries", "run_id": …}` marker.
  - **Skips:** runs with no verdict or score, and anything at or after a stock's first live row.
    A second apply adds nothing, and each stock keeps at most 90 rows.
  - **Modes:** dry run by default; `apply` and `remove` take an SQLite backup first. The mode comes
    from `SCORE_BACKFILL`, because the production pipe passes no arguments.
  - **Output:** counts only.

## Design decisions (delegated, recorded)

- **D1.** One writer, at the orchestrator's exit. Every entry point ends there: the 16:30 review,
  the monthly forecast, discovery deep dives, `/analyse`, the stream and the chat. Each caller
  could save its own row instead, but a new entry point would then forget.
- **D2.** Restore the documented store; don't point readers at `run_summaries`. That log has no
  thesis, and about a dozen readers expect the score store (AGENTIC_DESIGN step 7 already says
  each analysis records the row). Merging the two stores is out of scope (card).
- **D3. The managed list counts as shared.** Members can already read it.
- **D4. Beyond the card's named readers.** The card listed `/ui/learnings` and two chat readers.
  Restoring the write also activates these list-shaped reads of the store, so each is filtered:
  - Home's market panes;
  - the market summary;
  - search by thesis text;
  - the analytics sector comparison and score index.

  A guard test now fails on any unfiltered list-shaped read, apart from three keyed ones.
- **D5. Anonymous means shared only.** With sign-in required, an anonymous request never stands
  in for the default user, because that would show the owner's holdings (the same class as
  FIX-006).
- **D6.** Forecast misses still come from the built-in universe's feedback logs, which are public,
  as before.
- **D7.** Dating the watchlist score stays with SA-024 (the first PR-001 review's I2). The card's
  example said "dated" and was corrected.
- **D8. The backfill's backup** is a sibling copy made with SQLite's backup API, not the nightly
  archive tooling (SA-007), which has no off-site target yet.

## Tests

- **`tests/unit/test_score_history_fix010.py`, 32 tests (new).** Expected values come from each
  fixture's own table, not from the code.
  - **The write**, through the real orchestrator and aggregator (the SA-003 harness). One analysis
    writes one row with the returned verdict, and each agent's raw score is checked. A second
    analysis adds a second row.
  - The async exit writes its row too. With enforce, the row holds `INSUFFICIENT DATA`, never the
    withheld verdict.
  - A locked database leaves the report and its `run_summaries` call intact, and logs the
    warning.
  - **Guards:**
    - every sector orchestrator inherits both exits, and the registry gives out only those
      classes;
    - the base orchestrator is the only writer;
    - an AST scan finds every `get_all_latest`/`get_by_date_range` call filtered by
      `_only_visible`, apart from three keyed reads.
  - **Who sees which stock**, with Atlas on and off. The rows are written by the real writer: the
    owner holds QOWNHOLD, the member QMEMHOLD; QASKED is only analysed; QMANAGED is managed; QSHELF
    is an active idea and QDROPPED a dropped one. Every one changed verdict. The owner, the member
    and an anonymous caller each see exactly their set on `/ui/learnings`, `/ui/search` and the
    chat's context and history tool. Bootstrap, the market summary and the sector comparison name
    shared stocks only.
  - **"This month" votes** equal the mean raw score of the shared stocks' runs, worked out by hand.
  - A watched stock outside the universe shows its score; one with no analysis is "Not analysed".
  - **The empty case:** `since` is the older of two single runs. With nothing visible it is
    `null`.
  - An unreadable portfolio names only shared stocks.
  - **The backfill:**
    - the dry run's exact counts, and it writes nothing;
    - apply: naive UTC, the agent shape, the marker, the live-row cut-off, the newest 90;
    - a second apply adds nothing, and `remove` restores the table exactly.
- **PR-001's story tests, adjusted to the new contract.** `since` is now in the shape and in
  three empty bodies, and `_rows_since` takes `visible`. 44 pass (43 plus the browser wrapper).
- **The browser suite**, `tests/frontend/no_invented_figures.test.mjs`, has 11 tests (was 10):
  - the misses-only heading reads "No verdict changes since 16 Sept", or "recorded yet" with no
    date;
  - a new test starts signed out: the page loads the shared stocks' changes, and a sign-in
    through the form fetches them again as the member, whose own holding then shows ("2
    changes").
- **Two chat test stubs** (`test_chat_brief_user_scope_fix005.py`, `test_chat_session_memory.py`)
  replace `_build_chat_context` with a one-argument lambda. They now accept the `user_id`
  keyword; nothing else changed.
- **On the base code** (`analysis_data/fix010/swap_plugin.py`, `FIX010_SWAP=base`, SHA-256
  checked): 28 of the 32 new tests fail.
  - The four that pass on the base are the backfill test (a new script, not swapped) and the
    three source-scanning guards. They read the files on disk, which an in-memory swap cannot
    change.
  - That those guards bite is shown separately, with planted violations in a temp tree
    (`analysis_data/fix010/test_guard_probe.py`, 3 passed): an unfiltered
    `get_all_latest()` fails the list guard with its file, line and function; a filtered one
    passes; a second `ScoreStore().save` site fails the writer guard.
  - The market-wide test fails there with `TypeError: float() argument must be a string or a real
    number, not 'dict'`: the crash.
- **Mutants M1–M11**, each caught (`swap_results.txt`, `swap_results_final.txt`):
  - M1/M2: no write from the sync/async exit;
  - M3: a failed write propagates;
  - M4: an anonymous viewer stands in for the default user;
  - M5: dropped shelf ideas count as shared. It survived at first; the fixture now gives QDROPPED
    a change (20 fail);
  - M6: per-agent objects read as numbers;
  - M7: the outside-universe watchlist row is "Not analysed" again;
  - M8: `since` is the newest run. It survived at first; the empty-case fixture now has two runs
    (2 fail);
  - M9: the chat context forgets its caller;
  - M10: search unfiltered;
  - M11: the sector comparison unfiltered.
- **Elsewhere:**
  - `npm run test:frontend`: 28 of 28;
  - `check_kt_docs`: errors `[]`;
  - the broad-except guard: OK (153);
  - the failing files after the first full run, re-run: 91 passed.
- **Full suite:** 4584 passed, 12 skipped, 0 failed (run 2, 21 min 1 s, 21:25–21:46 IST).
  - The first run (20:59–21:23) failed 10: the two stubs (9 tests) and the hot-path guard, which
    requires `exc_info` on the new warning. Both were fixed.
- **Not run:**
  - the layout audit (FIX-010 changes a heading string and a fetch function, not the layout);
  - the backfill against real data;
  - production.

## Documentation

- **KT:**
  - section 1: a dated "Score history" row with the probe's figures;
  - section 3: `scores.db` gets its own persistent-records row;
  - section 10: the learnings paragraph covers the stocks the viewer may see, the `since` empty
    case, and "may have been left out", the SA-031 RR-I1 wording, now fixed;
  - section 10: a new "Score history and who sees which stock" paragraph, with an example;
  - section 12: the intro and a FIX-010 row (`Open`).
- The PDF was rebuilt: 43 pages, source digest `0ced16a2…` = the KT's SHA-256, `check_kt_docs`
  errors `[]`.
- **CODEBASE:** the `/ui/learnings` and `/ui/search` rows ("session optional"), market summary,
  sector comparison, `score_store.py`, `base_orchestrator.py`, `data/scores.db`.
- **Guide:** 11-J (the dated empty case) and a new case, 11-K (the privacy rule and a watched
  stock's analysis).
- **UI_SPEC:** `PORTFOLIO_LEARNINGS` gets `{items[], since}`, the visible-stocks note and the
  heading wording. **PRODUCT_MAP:** `ui_data.py`'s line count.
- `docs/AGENTIC_DESIGN.md` step 7 is unchanged: it already said each analysis records the score
  history row, and now that is true.

## Manifest and digest

- **Review input:** [FIX-010-manifest.json](FIX-010-manifest.json),
  `900c8f27ff08f4ead35c73227f3038fef4860082449119c61c016701467b8027`, 18 files.
- **Diff:** `150bb8b6164d30e608825992d2df3e1df4b9cbcb6ee414cb2466854fc2b95df3` (105,005 bytes, 17 paths, PDF excluded), from
  `analysis_data/fix010/manifest_and_digest.py`.
  - Bases: `analysis_data/fix010/base/` (SHA-256 checked) and `git show HEAD` for `analytics.py`.
  - New files are diffed against `/dev/null`.
- PR-001's manifest (`1c7ea945`) now mismatches on the ten files FIX-010 layered. FIX-009's still
  mismatches on its five layered docs, as before.

## Self-review

No critical, high or medium finding.

- **I1 (info, rollout).** Until the backfill runs (it is optional), production's history starts
  empty. Home fills after the first analyses: Friday's 16:30 review and any chat or `/analyse`
  request. A verdict change shows only once a stock has two runs.
- **I2 (info).** `/ui/learnings` now looks through about 100 stocks: the 16 built-in, the managed
  list, shelf ideas and the viewer's own. That is one indexed query each, on a page opened by
  hand.
- **I3 (info).** Forecast misses still come only from the built-in universe's feedback logs (D6).
  A managed stock's misses outside the universe are not listed, as before.
- **I4 (info).** An analysis that the chat runs for a stock nobody holds is stored, and named only
  when a viewer asks for it by name. The store does not record who asked, so not even the asker's
  own lists show it (the card's privacy case).

- **I5 (low, found after the commit).** The backfill's cut-off is per stock, at the first live row. An analysis logs `run_summaries` a few milliseconds before `ScoreStore.save`. So a run made between the deploy and the backfill is copied too, a second row for one analysis with the same verdict: no false change, but slightly double-weighted votes. A cut-off at the earliest live row across all stocks, less a margin, would avoid it. The production dry run of 16 Oct found no live row, so applying before the first post-deploy analysis is unaffected. For the fresh review.

## Production check (after an owner-authorized deploy, read-only)

1. After the first 16:30 review following the deploy, re-run
   `analysis_data/pr001/rereview1/score_history_probe.py`. `score_history` rows are above 0, and
   `last_run_at` is that day.
2. **Home:** as the test member, a watched stock that is analysed daily shows a score and
   verdict.
3. Guide 11-K.
4. **Backfill, only at the owner's word.** First the dry run:
   `railway ssh "cd /app && echo $(gzip -9c scripts/backfill_score_history.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"`.
   Then the same command with `SCORE_BACKFILL=apply` placed before `python`.
