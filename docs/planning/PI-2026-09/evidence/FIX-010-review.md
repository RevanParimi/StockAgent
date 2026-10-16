# FIX-010 — review receipt

**The re-review of rework 1 (16 Oct) accepted FIX-010. Its section comes first; the first review's record follows it.**

## Re-review of rework 1 — 16 Oct 2026 (accepted)

**Phase:** fresh-session re-review (a new conversation opened with "continue", 16 Oct about
11:35–12:25 IST, session stockagent-main-88; peers -7f, -e3, -ec, -06, -0d, -d9, -25, -fb, -5f,
-f9 and splitfamilia-a9 idle). It is neither the reviewing nor the implementing conversation.
**Verdict: ACCEPTED.** One low docs item (RR1) is a follow-up for the commit.

**Reviewed revision:** the uncommitted working tree on `c31136b`, pinned by review input
[`FIX-010-manifest.json`](FIX-010-manifest.json),
`89787068969160313e1ad59458bdc3b15aa1929540c2be2b27c2208124aa8e05` (19 files: the first review's
18 plus `scripts/ci/broad_except_baseline.txt`). Together with the committed `ec3f336`, which the
first review read, this is FIX-010's accepted code. Nothing was committed, pushed, deployed or
configured. No production state was read, no notification was sent and no reviewed file was
changed.

### In one example

The test member opens Home on Monday at 09:00 IST.

- **Friday's 16:30 review was the last analysis of a shared stock.** Today and This month read
  "Last analysis 2 days ago", with the stale dot. Before the rework they read "Updated recently",
  with no dot.
- **Saturday's discovery shelved a stock it had just analysed.** Both panes read "Last analysis 1
  day ago", stale. That is the right rule, the age of the newest shared analysis. But the KT and
  guide 11-K promise "2 days ago" for every Monday (RR1).
- **The owner's own stock, the member's own stock or a dropped shelf idea was analysed an hour
  ago.** The panes still read the shared stocks' age: none of those three makes Home look fresh.

### Review input and digest

- `kt_manifest.py verify FIX-010-manifest.json`: **0 mismatches** against the working tree, at
  the start and again after the full suite. Against `HEAD`, the 12 files that differ are exactly
  the 12 the receipt lists as changed by the rework; the other 7 match `HEAD`.
- **Rework diff rebuilt by the re-reviewer:** `git diff c31136b --` over the receipt's 11 payload
  paths, sorted, PDF excluded. Result: 38,024 bytes, SHA-256
  `279ccf94f99fc5cd71f565d39241e5f3ac423bf914618f28c00912400778c85e`. That equals the receipt.
  The diff's base blob for the backfill script, `b9a65d0`, equals `c31136b`'s.
- **Outside the input:** `docs/README.md` holds the owner's probe command line. It is the
  owner's own edit and was left alone. STATE, HANDOFF and the receipts are bookkeeping.

### Contract checked

The first review's findings: M1 (must fix), L1, L2 and L3 (recommended), I5 (optional). Also
the card's intended result: "the screens that read it show real, dated analysis states". The
rework diff touches only:
- `_freshness_label` in `ui_data.py`;
- the backfill's `plan` cut-off;
- the learnings list's lifetime in `data.jsx` and `index.html`;
- tests and docs.

So the first review's checks of the writer, the entry points, the reader classification and the
privacy rule still apply unchanged.

### Independent checks

The re-reviewer's own tests are in the scratch file `test_rr_adversarial.py` (17 cases). They are
built on the first review's real-server fixture: `services.api.server.app` under uvicorn, AUTH
on, Atlas on, real sessions, and rows through `BaseSectorOrchestrator._record_score_history`. A
browser case was added to a scratch copy of `no_invented_figures.test.mjs`. Every expected value
was worked by hand from the card's rule.

- **M1, the time labels, through the real server.**
  - Monday, for member A, the owner and an anonymous caller:
    - the managed stock analysed 64 h ago and a Saturday shelf dive 44 h ago give "Last analysis
      1 day ago", stale, `runAt` = the shelf row;
    - without the shelf dive, "Last analysis 2 days ago", `runAt` = the managed row.
    - Rows for the dropped idea (2 h), the owner's own stock (1 h) and A's own stock (30 min)
      never count.
  - Boundaries:

    | Age of the newest shared analysis | Label | Stale |
    |---|---|---|
    | 30 min, 59 min | "Live" | no |
    | 61 min | "Updated 1h ago" | no |
    | 11 h 59 min | "Updated 11h ago" | no |
    | 12 h 01 min | "Updated 12h ago" | yes |
    | 23 h 59 min | "Updated 23h ago" | yes |
    | 24 h 01 min | "Last analysis 1 day ago" (Today falls back to the latest rows) | yes |
    | 49 h | "Last analysis 2 days ago" | yes |

    Both panes give the same answer.
  - Only the viewer's own rows, and no shared row: "No data yet", stale.
  - **Bite:** on `HEAD`'s `_freshness_label` (`rw_swap_plugin`, `RW_SWAP=base`), all 14 label
    cases fail. The no-data case passes; that path did not change.
- **I5, the backfill, in production order with live rows.**
  - The cycle:
    1. three pre-deploy runs are logged through the real `log_store.log_run_summary`;
    2. `apply` copies them (3);
    3. three post-deploy analyses each log their run and then write the live row, 4 ms later
       (one 1.5 s later);
    4. `remove` deletes the 3 copies;
    5. `apply` runs again, then a third time.
  - Result: 3 inserted and 3 cut, so **6 rows for 6 analyses**. The third `apply` adds 0, and
    `/ui/learnings` lists the dated changes.
  - **Bite:** `HEAD`'s script on the same cycle gives **8 rows**: each stock's first live
    analysis is copied once more.
  - The margin holds. `run_summaries.ts` is taken inside the insert (`log_store._now()`). The
    live row follows in the same synchronous sequence (`base_orchestrator.py` lines 195–204 and
    274–283, no `await` in between), so the gap is milliseconds. SQLite's lock wait is well
    under 60 s.
- **L1:** with the reviewer's mutant X1 (`RV_SWAP=X1`, the async exit writes before the gate),
  the story file's `async-exit` case fails and `sync-exit` passes.
- **L2, in Chromium.** The implementer's two cases drive the Sign out button. The re-reviewer's
  case takes the other way out, an expired session:
  - any request answered 401 drops the list (`PORTFOLIO_LEARNINGS` null and `__learningsLive`
    false at the login screen);
  - the next account's `/ui/learnings` answers 503, and its Portfolio shows no list and no
    `QMYOWN`.
  - It passes on the rework. On `HEAD`'s frontend (`analysis_data/fix010/rework1/fe/base`,
    whose blob ids equal `c31136b`'s) it fails at "dropped on expiry".
  - Account deletion calls the same `saClearToken` (`settings.jsx:267`).
  - The service worker fetches navigations network-first and serves `.jsx` stale-while-
    revalidate. So the first open after a deploy runs the new `index.html` with the old
    `data.jsx`, as the receipt's I6 says; "close and reopen the app once" covers it.
- **L3, guide 11-K.** It matches the code: deep dives skip managed and shelved stocks
  (`core/discovery/deep_dive.py:117`), the 16:30 review analyses managed stocks, and the owner
  analyses the held stock on request first.
- **No other reader repeats M1.** The other uses of `run_at` in `ui_data.py` and `analytics.py`
  slice the date or compare dates. None subtracts a naive time from an aware one.
- **Test independence.** The new story tests write rows through the real `ScoreStore.save` (only
  the clock is faked), read `runAt` back with plain SQL and state hand-worked labels. The
  hermetic boundary covers every pytest run. Unplanned browser requests get a 503, and outside
  requests are aborted.

### Findings

| ID | Severity | Where | Finding | Disposition |
|---|---|---|---|---|
| RR1 | Low (docs; code inspection, configuration and local reproduction) | `docs/TECHNICAL_DESIGN.md` section 10, lines 1504–1506; `docs/TEAM_TESTING_GUIDE.md` 11-K, expected result | Both promise "Last analysis 2 days ago" on a Monday morning. Saturday's `discovery_weekly` (12:30 IST; `config.yaml` `discovery.enabled: true`, 10 deep dives) analyses stocks through the orchestrator (`deep_dive.py:126`). A stock it shelves is a shared stock (`_shared_symbols`, active shelf ideas). Then Monday 09:00 reads "Last analysis 1 day ago" (about 44 h), stale. Reproduced: `test_monday_after_a_saturday_shelf_dive_reads_one_day`. The code is right. A tester following 11-K on such a Monday would record a false FAIL. | **Follow-up with FIX-010's commit** (the session that commits at the owner's word), wording below. Prose only, so no test is needed. |
| I9 | Info | `ui_data.py:634` | The newest `run_at` is a string `max`, so an unreadable `run_at` sorts above every ISO time: one such row reads "Analysis time unknown", stale, even next to readable rows. Both writers (`ScoreStore.save`, the backfill) write ISO times, so no such row exists. It fails safe. | None. |
| I10 | Info | `data.jsx` `saLoadLearnings` | The anonymous fetch at load and the sign-in fetch share one viewer count. If the anonymous answer arrived after the signed-in one, it would replace the member's list with the shared stocks' list. That shows less, and never another viewer's stocks. It needs the anonymous answer to take longer than typing the credentials. | None. |
| I1 (extended) | Info, pre-existing | `src/frontend/prototypes/home.jsx:961` | Trending's "· 16 Oct" reads the naive UTC `run_at` as local time. An analysis between 00:00 and 05:30 IST shows the day before, the same class as I1. | For SA-031's sweep, with I1 and I3. |

**RR1 wording for the commit:**
- **KT section 10.** Replace "So on a Monday at 09:00 IST, after Friday's 16:30 review, Today
  reads "Last analysis 2 days ago", marked stale." with: "So on a Monday at 09:00 IST, when
  Friday's 16:30 review made the newest analysis of a shared stock, Today reads "Last analysis 2
  days ago", marked stale; after a Saturday on which discovery shelved a stock it had just
  analysed, it reads "Last analysis 1 day ago"." Rebuild the PDF.
- **Guide 11-K, expected result.** Replace ""Last analysis 2 days ago" with the dot on a Monday
  morning" with: ""Last analysis 2 days ago" with the dot on a Monday morning, or "1 day ago" if
  Saturday's discovery added a stock to the shelf".

### Commands and results

- `kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-010-manifest.json`: 19 files, 0
  mismatches, at the start and after the suite. `--rev HEAD`: 12 changed, the rework's files.
- Rework diff (above): `279ccf94…`, 38,024 bytes.
- The review's story set: `pytest tests/unit/test_score_history_fix010.py
  tests/unit/test_ui_no_invented_figures_pr001.py tests/unit/api/test_chat_brief_user_scope_fix005.py
  tests/unit/test_chat_session_memory.py tests/unit/test_broad_except_guard.py -q -p
  no:cacheprovider`: **170 passed** (4 min 51 s). The broad-except guard requires the baseline
  exact, so M1's removed entry is checked.
- The first review's tooling, `test_rv_trace.py` and `test_rv_async_gate.py`: **13 passed**.
- The re-reviewer's scratch `test_rr_adversarial.py`: **17 passed**. Under `RW_SWAP=base`: 14 of
  the 15 label and no-data cases fail (all 14 labels). The `HEAD` backfill bite case passes,
  which means it shows 8 rows.
- `RV_SWAP=X1` on the story file's gate test: `async-exit` failed, `sync-exit` passed.
- Browser: `npm run test:frontend`: **30 of 30**. The re-reviewer's expired-session case passes
  on the rework and fails on `fe/base`.
- `check_kt_docs.py`: errors `[]`; the PDF's source SHA-256 `b67626c1…` equals the KT's (43
  pages).
- The implementer's freshness tests under `RW_SWAP=base` (`-k "age_of_the_newest or
  with_or_without_an_offset"`): **11 of 11 fail**.
- Full suite (`pytest -q -p no:cacheprovider -o console_output_style=count`): **4597 passed, 12
  skipped, 0 failed**, 12 min 1 s (12:01–12:13 IST).
  The working tree was unchanged after it.
- Environment: Windows 11, the project venv `.stockai` (Python 3.13), the hermetic boundary,
  Node 24 with the vendored Playwright Chromium.

**Not exercised:**
- production: the owner's probe after today's 16:30 review is FIX-010's production check;
- the layout audit (no layout change);
- the implementer's fe variants `noclear` and `nogen`, which were not re-run (the re-reviewer's
  own case covers the drop on another path);
- the M1 label in a browser (the server's JSON was checked; `home.jsx:645-648` prints
  `freshness.label` and the dot as sent).

### Acceptance checklist

1. The write: **met** (first review; the rework adds the async-exit test with enforce).
2. Who sees which stocks: **met** (first review). In the browser, the list now ends with its
   viewer (L2).
3. Watchlist rows outside the universe: **met**.
4. The empty case: **met**.
5. The backfill: **met**, now also for a mid-day apply and an apply after remove (I5).
6. Tests: **met**; the L1 gap is closed.
7. Documentation: **met**, with L3 done and RR1 as a wording follow-up.
- The intended result, "real, dated analysis states": **met**. Home's two panes state the age of
  the newest shared analysis and mark it stale past 12 hours.

### Decision

**ACCEPTED** for the uncommitted working tree on `c31136b`, review input `89787068…`, with the
committed `ec3f336`. STATE: FIX-010 `done`, `next_task: PR-002` (no dependencies; not started in
this conversation).

**Production verification stays `pending_observation`.**
- `ec3f336` is live, and the owner's probe after today's 16:30 review still checks the writer.
- The rework needs a commit and a deploy at the owner's word, in a job-free window, never
  16:25–17:15 IST.
- The commit carries:
  - RR1's wording, with a PDF rebuild;
  - KT section 12's FIX-010 row, `Open` → `Done`;
  - the KT header bump;
  - guide 11-K's status line.
- After the deploy: close and reopen the app once (I6). Then run guide 11-K, and check that
  Home's labels state an age after the next 16:30 review.

## First review — 16 Oct 2026 (changes requested)

**Story:** [FIX-010](../stories/FIX-010.md) · **Phase:** fresh-session review (a new conversation
opened with "continue", 16 Oct about 08:30–09:05 IST, session stockagent-main-0d; peers -7f, -e3,
-ec, -06, -d9, -25, -fb, -f9 and splitfamilia-a9 idle) · **Verdict: CHANGES REQUESTED** (one
medium finding must be fixed; three lows are recommended in the same rework)

**Reviewed revision:** the committed code `ec3f336` (parent `9db8ba7`, PR-001's accepted bytes)
and its docs in `445d7fa`, pinned by review input [`FIX-010-manifest.json`](FIX-010-manifest.json),
preserved as [`FIX-010-manifest-review1.json`](FIX-010-manifest-review1.json):
`900c8f27ff08f4ead35c73227f3038fef4860082449119c61c016701467b8027`, 18 files.

The code was committed, pushed and deployed (`c31136b`) before this review, at the owner's word,
and the owner applied the backfill in production at 08:23:59 IST today. This review read no
production state, changed no production variable, sent no notification and changed no reviewed
file.

## In one example (M1, the finding that must be fixed)

The test member opens Home on Monday at 09:00 IST. The last 16:30 review ran on Friday, so the
newest analyses are about 64 hours old.

- **What Home says:** "Market pulse · today ... Updated recently", with no stale dot. "This
  month" says the same.
- **What is true:** "Last analysis 2 days ago", marked stale (the code's own rule: older than
  12 hours is stale).

The label never states an age. With rows 5.5 hours old it should read "Updated 5h ago"; it reads
"Updated recently". If a 16:30 review fails, Home keeps saying "Updated recently".

Reproduced through the real server with rows from the orchestrator's own write method
(`test_today_s_freshness_label_is_the_age_of_the_newest_shared_run` and
`test_a_three_day_old_analysis_is_not_called_recent` in
`analysis_data/fix010/review/test_rv_trace.py`).

## Review input and digest

- `kt_manifest.py verify FIX-010-manifest.json --rev 445d7fa`: one mismatch, the testing guide.
  The reviewer's own check (`analysis_data/fix010/review/rv_verify.py`) shows why: at `445d7fa`
  all 18 files match the manifest's SHA-256 and git blob id once the guide's five commit-time
  status lines are removed (10-H, 11-H, 11-I, 11-J and 11-K, " **FIX-009|PR-001|FIX-010: …** |").
  The manifest's guide blob was never staged, so this content check stands in for a blob lookup.
- At `HEAD` (`c31136b`) only the KT, its PDF (the commit bump) and the guide differ; the twelve
  code and test files are byte-identical between `ec3f336` and `HEAD`.
- **Code diff rebuilt from git**, `git diff 9db8ba7 ec3f336` (FIX-010's commit alone): 72,554
  bytes, 12 paths, SHA-256 `77cac0bddb0e20460180ecf28b7a3f755485fdb30b89321c1f886bb01ef278da`.
  The implementer's `150bb8b6…` (105,005 bytes, 17 paths) also covers five docs from a snapshot
  base; the docs were read in `445d7fa` instead.

## Contract checked

From the card: one row per completed analysis at the single exit, after the decision gate, with
the returned verdict; a failed write is a warning; lists name only shared stocks and the viewer's
own; watched stocks outside the universe read the store; a dated empty case; an owner-run
backfill (dry run, marker, idempotence, live-row cut-off, cap, backup); tests independent of the
changed code; KT 10/12, CODEBASE, guide 11-J and a human case. Also the card's intended result:
"the screens that read it show real, dated analysis states".

## Independent checks

**Every entry point reaches the writer.** Grep of `.analyse(` and `.analyse_async(` outside
tests: `main.py`, discovery deep dives, the monthly forecast, the 16:30 review, `/analyse`, the
stream, the chat tool and `run_now`. Each calls an orchestrator from `backend.sectors` or
`sector_router`. Both resolve through `registry._BACKEND_LOADERS`. The reviewer's
`test_every_registry_class_ends_at_the_one_writer` loads every class from both and checks it
subclasses `BaseSectorOrchestrator` without overriding `analyse`, `analyse_async` or
`_record_score_history`. The implementer's guard covered `backend.sectors` only. (`core/ipo`'s
`analyse` is an unrelated IPO function.)

**Every reader of the store, classified.** `get_all_latest`, `get_by_date_range`, `get_history`,
`get_latest`, `get_previous`, counts:
- filtered list reads: `/ui/learnings`, `/ui/search`'s thesis match, the chat's current verdicts
  and history, bootstrap's panes, `/ui/market/summary`, `/analytics/sector-comparison` and the
  score index behind `/analytics/rl-export` and `/analytics/powerbi-feed`;
- keyed or universe-bound: `_gather_ticker_data` (8 built-in tickers), `/ui/watchlist` (the
  viewer's symbols), `/ui/trending` (the 16 built-in), bootstrap's suggestion "why" line, the
  sector snapshot (counts only), `_ctx_ticker_detail`, the chat's cached analysis,
  `/history/{ticker}`, the CLI `run_schedule.py` and the scheduler status counts.

**The reviewer's trace through the real server** (`test_rv_trace.py`, 7 tests, 12 cases).
- **Setup.** `services.api.server.app` under uvicorn in a thread, `AUTH_REQUIRED` on, Atlas on (as
  in production), real sessions for the owner and members A and B, the test's empty working
  directory. Rows come from `BaseSectorOrchestrator._record_score_history` with real
  `FinalReport` objects; only the store's clock is faked. `yfinance` raises.
- **Fixture table.** The owner holds ZOWNR; A holds ZAHLD and watches ZAWCH (outside the
  universe, one run); B holds ZBHLD; ZCHAT was only analysed; ZMNGD is managed; ZSHLF an active
  shelf idea, ZDROP a dropped one; plus TATAMOTORS. Every stock with two runs went BUY → SELL.
- **Results (pass):** for the owner, A, B and an anonymous caller, `/ui/learnings` lists exactly
  the table's visible changes and `since` is the oldest run's date; search by thesis text names
  exactly the visible stocks; `/ui/bootstrap`, `/ui/market/summary`, `/ui/trending`,
  `/ui/tickers` and the sector comparison name shared stocks only. The RL export and the Power
  BI feed answered 200 with no stock at all (they walk prediction stores, empty here), so the
  trace did not exercise their score index; its filter rests on code inspection and the
  implementer's guard. The chat's context and history tool name exactly the caller's visible set, and the
  cached-analysis tool still answers for ZCHAT by name. A's watchlist shows ZAWCH 0.71 BUY.
- **Freshness (fail, M1):** see the example above.
- **Backfill on a mid-day fixture (production order).** Runs logged through the real
  `log_store.log_run_summary`. TATAMOTORS logged 40, 20 and 10 days ago; ZMNGD logged 9 days ago,
  then a post-deploy analysis 2 days ago that logs its run and writes its live row 4 ms later.
  Dry run 5, apply 5, a second apply 0 (5 already present). On these backfilled rows (what
  production holds until today's 16:30 review) `/ui/bootstrap` answers 200, its "This month"
  vote is the raw scores' mean, and `/ui/learnings` lists ZMNGD then TATAMOTORS, dated, `since`
  the 40-day-old run. ZMNGD ends with three rows for two analyses: I5, below.

**Mutants and variants** (`rv_swap_plugin.py`, in memory; no repo file written):
- X1, the async exit writes before the decision gate: all 32 story tests still pass; the
  reviewer's `test_rv_async_gate.py` (async, enforce, missing price) fails. L1.
- X2, the M1 fix (a naive `run_at` read as UTC): the reviewer's trace then passes 11 of 12 (the
  remaining failure is I5).

**Test independence.** Expected values in `test_score_history_fix010.py` come from the fixture
tables (the hand-worked vote means, the dates), rows come from the real writer, and the hermetic
boundary fails any test that tries the network even if the error is caught. The base-code run (28
of 32 fail) and M1–M11 in the receipt were not repeated.

## Findings

| ID | Severity | Where | Finding | Disposition |
|---|---|---|---|---|
| M1 | Medium (confirmed, local reproduction) | `services/api/routes/ui_data.py:633-647`, `_freshness_label` | The writer and the backfill store `run_at` as naive UTC. `datetime.fromisoformat` gives a naive time, and `now - run_dt` with an aware `now` raises `TypeError`. The `except` returns the fixed `{"label": "Updated recently", "isStale": False}`. So Home's "today" and "This month" labels never state an age and never show stale: 5.5 h → "Updated recently" (expected "Updated 5h ago"); 3 days → "Updated recently", not stale (expected "Last analysis 3 days ago", stale). The code dates from 5 May (`e3d9e19`), after the last writer was removed, so it never met a real row; FIX-010 makes it reachable, as with the agent-score crash it fixed (D4). Production, by inference only: since the 08:24 backfill, Home reads "Updated recently" for the 15 Oct runs. | **Must fix (rework 1):** read a naive `run_at` as UTC; tests through the writer's rows for under 6 h, 6–24 h and over 24 h, and `isStale` over 12 h. |
| L1 | Low (test gap) | `tests/unit/test_score_history_fix010.py` | The async exit (`/analyse`, the stream, the chat) is never tested with enforce: mutant X1 survives the story file. The code is right. | Recommended: adopt `analysis_data/fix010/review/test_rv_async_gate.py`'s case. |
| L2 | Low (code inspection, not reproduced) | `src/frontend/prototypes/index.html` `saClearToken`; `data.jsx` `saLoadLearnings` | Sign-out keeps `window.PORTFOLIO_LEARNINGS`. When another account then signs in on the same tab, the list is replaced only by a 2xx answer; a failed fetch leaves the previous viewer's list, which names that viewer's own holdings. | Recommended: clear the list (and `__learningsLive`) on sign-out or before the re-fetch; a browser case. |
| L3 | Low (docs) | `docs/TEAM_TESTING_GUIDE.md` 11-K | The 16:30 review analyses only managed tickers. The owner's held stock, by the case's own terms not managed, gets no row, so the member-side check passes without anything to hide. "A third stock that is analysed every day" must be a managed stock, and for the watchlist rule one outside the 16 automobile stocks. | Recommended: the owner first analyses the held stock (Home's Analyze, or the chat); add the owner's own check (it appears there); say the watched stock is a managed one outside the 16. |
| I5 | Low (implementer's, reproduced) | `scripts/backfill_score_history.py` `plan` | A stock's first live analysis logs its run a few ms before its live row, so the per-stock cut-off copies that analysis once more (fixture: 3 rows for 2 analyses, 4 ms apart). Production's apply found no live row, so it is unaffected. | Optional: refuse `apply` when a live row exists, or cut at the earliest live row less a margin; otherwise state in the docstring that it is for a store with no live row. |
| I1 | Info | `ui_data.py` `_verdict_change_record`, `get_learnings` | A card's date and `since` are UTC dates (`run_at[:10]`); a chat analysis between 00:00 and 05:30 IST carries the day before. The 16:30 review (11:00 UTC) is unaffected. Unchanged from PR-001. | None. |
| I2 | Info | receipt and handoff example | "The 16:30 analysis turns DIXON from BUY to SELL" with DIXON not managed: the review analyses managed tickers only, so such a stock changes only through analyses on request. The KT's example makes no such claim. | Dated records; no change. |
| I3 | Info (pre-existing) | `src/frontend/prototypes/agents-page.jsx:443-470` | The agent drawer's recent runs read `agent_scores` from `/history/{sym}`, which does not return it, so the list is always empty. Not a FIX-010 reader. | For SA-031's sweep. |

## Commands and results

- `.stockai/Scripts/python.exe analysis_data/fix010/review/rv_verify.py`: 18 files, no
  mismatch at `445d7fa` after removing 5 status lines; code unchanged to `HEAD`; diff
  `77cac0bd…`.
- `pytest tests/unit/test_score_history_fix010.py tests/unit/test_ui_no_invented_figures_pr001.py
  tests/unit/api/test_chat_brief_user_scope_fix005.py tests/unit/test_chat_session_memory.py`:
  134 passed.
- `PYTHONPATH=. pytest analysis_data/fix010/review/test_rv_trace.py -p no:cacheprovider --rootdir
  analysis_data/fix010/review`: 9 passed, 3 failed (M1 twice, I5); with `RV_SWAP=X2` and `-p
  rv_swap_plugin`: 11 passed, 1 failed (I5).
- `test_rv_async_gate.py`: base 1 passed; X1 1 failed. Story file under X1: 32 passed.
- `npm run test:frontend`: 28 of 28.
- `check_kt_docs.py`: errors `[]`.
- Full suite (`pytest -q -p no:cacheprovider -o console_output_style=count`): 4584 passed, 12 skipped, 0 failed, 10 min 53 s (08:48–08:59 IST). The working tree was unchanged after it.
- Environment: Windows 11, the project venv `.stockai` (Python 3.13), the hermetic boundary.

**Not exercised:** production (the owner's probe after today's 16:30 review is the production
check); the browser on L2; the layout audit (no layout change); the M1 label in a browser.

## Acceptance checklist

1. The write: **met** (both exits after the gate; failure is a warning; every entry point).
2. Who sees which stocks: **met** (reviewer's trace, four viewers, Atlas on).
3. Watchlist rows outside the universe: **met**.
4. The empty case: **met**.
5. Backfill: **met** for the production run (no live row); I5 for a mid-day run.
6. Tests: **met**, with the L1 gap.
7. Documentation: **met**, with L3.
- Intended result, "real, dated analysis states": **not met** on Home's two analysis panes (M1).

## Decision

**CHANGES REQUESTED.** FIX-010 returns to implementation (rework 1) in a new conversation, then a
fresh re-review in another. Rework 1 fixes M1, takes L1, L2 and L3 unless it records why not, and
decides I5. STATE: `status: changes_requested`, `next_task: FIX-010`. Production verification
stays `pending_observation`: the code is live and the after-16:30 probe still checks the writer;
the M1 fix needs its own deploy at the owner's word.
