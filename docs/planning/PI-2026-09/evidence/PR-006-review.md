# PR-006 — review receipt

## Fresh re-review of rework 1 — 22 Oct 2026 (accepted)

**Phase:** a **fresh-session re-review**: a new conversation opened with "continue", 22 Oct
about 13:39–14:40 IST, session stockagent-main-a8. It is not the implementing conversation
(stockagent-main-bb), the rework (stockagent-main-46, idle from 13:10) or the first review
(stockagent-main-2c). Peers -1c, -2c, -3c, -46, -48, -53, -95 and -bb were idle at the start
and at bookkeeping.
**Verdict: ACCEPTED.** R1 is fixed and L1 is done. No new finding needs a change. Nothing was
committed, pushed, deployed or configured. No production state was read, no message was sent,
no outside endpoint was called, and no reviewed file was changed.

**Reviewed revision:** the uncommitted working tree on
`25fae38ecdc1a85b99b4a2c6d759fc2d11dfbdaf`, pinned by
[PR-006-manifest.json](PR-006-manifest.json)
`ec6eaf86fd339bff1112d4bc8c37c76c8f238d16281bee2948cafe82c8695067` (23 files), stacked on
PR-004's accepted input. Rework diff `44ebfddb…`; cumulative diff `bfafe107…`.

### In one example

Thu 22 Oct, the 18:30 run, called exactly as the scheduler job calls it:
`run_event_feed("pm")`, with no `now`, `clock` or `store`; only the `_clock` seam reads the
fake world's clock. The run tracks 50 stocks and MARUTI is last. Every NSE call, the fetcher's
pauses, every search and every model call moves the clock. MARUTI asks NSE at 18:44:37 and
18:44:42. NSE shows its results filing and a board-meeting intimation, both filed at 18:41:20.

- **Reviewed code (review 1):** both were stored with `published_at: null`, and the
  intimation was stored again, dated, the next morning.
- **Now (RR1):** both are stored with `2026-10-22T18:41:20+05:30` and `fetched_at`
  `2026-10-22T18:44:47+05:30`. That is the end of MARUTI's last NSE call plus the pause, read
  from the world's call log, not from the feed. A `since` read for 22 Oct returns both.
  MARUTI's ingestion runs once, under `automobile`. The next morning stores nothing and sends
  nothing to the model.

### Review input and digests

- `kt_manifest.py verify PR-006-manifest.json`: **23 files, 0 mismatches** at the start (13:39
  IST) and again after the full suite (14:34 IST).
- `PR-006-manifest-review1.json` still hashes to `d2e35f72…`, the first review's input.
- **The bases, checked independently** by the reviewer's own
  `analysis_data/pr006_rereview/rr_digest.py` (`git hash-object --path=<real path>` of each
  copy):
  - `analysis_data/pr006/rework1/base/`: 23 of 23 blobs equal the review-1 manifest;
  - `analysis_data/pr006/base/`: 33 of 33 PR-004 blobs equal `PR-004-manifest.json`.
- **Diffs rebuilt** by the same script, at the start and at the end:
  - rework: **`44ebfddb…`, 50,719 bytes, 5 paths**. They are `core/events/feed.py`,
    `core/events/sources.py`, the guide, the KT and the story test file. The PDF is the sixth
    changed blob (`099cb903` → `138f9f36`), and these six are the only paths whose blob
    changed since review 1;
  - cumulative: **`bfafe107…`, 180,813 bytes, 22 paths** (6 against the base, 5 against
    HEAD, 11 new).

  Both equal the rework receipt.
- Outside the input: STATE, HANDOFF and the receipts (bookkeeping), and PR-004's files that
  PR-006 does not change.

### Code read

- The rework diff in full, then `core/events/feed.py` and `core/events/sources.py` in full.
- Also: `fetch_company_filings` (its pauses run between and after the two NSE calls),
  `_normalize_serper_date`, the ingestor's `_is_qualifying` (a substring rule), and the
  scheduler's `_company_events_job`.
- **The only caller** of `run_event_feed` is that job, and it passes the slot only. So in
  production every stock reads the `_clock` seam, the wall clock in IST. No production caller
  passes `now` or `clock`.
- **Unchanged by the rework,** checked line by line: the order of names given to the company
  check, the order of items, `news_not_searched`, and the ingestion rule (`day <= on`, `on`
  being the run's start day).

### The story's hard-review questions, again

| Question | Answer for rework 1 |
|---|---|
| Can a fetch-time date masquerade as a publish date? | **No.** The per-stock clock sets only three things: `fetched_at`, the 10-minute bound and the base for news ages. `published_at` still comes only from `an_dt`, `sort_date`, `bm_timestamp` or Serper's string. A row timed after the fetch now waits; it is never dated by the fetch and never stored `null`. RR2 and RR3 (65 timetables) find every stored NSE `published_at` equal to the filing's own time, and RR3 finds no undated NSE event. Mutants X3 and X4, which store such a row undated, are caught. |
| Can one symbol's news be filed under another? | **Unchanged.** The code and company checks are untouched. Review 1's RV2 and RV5 pass as they are. |
| Does the job respect the registry's identity (SA-008)? | **Unchanged.** Review 1's RV4 passes as it is. |

### Rulings on the rework's decisions

| Decision | Ruling |
|---|---|
| RW-D1: a `clock` argument; a replay at a fixed `now` keeps a fixed clock | **Accepted.** The scheduler's call reads the seam once per stock: RR1, the story's `test_the_scheduler_call_reads_the_clock_seam_per_stock`, and mutant X11 (the wall clock read once) caught. A caller that fixes `now` gets a replay: every stock is read at `now`, and a row more than 10 minutes after it waits and is never stored undated (RR4). **Consequence:** review 1's RV1a, unmodified, still xfails. It passes `now=START` with a separate NSE clock, which is now a replay by contract. Its scenario passes in RR1 through the production call shape, with no `clock` argument. It also passes in the implementer's unmarked copy (`rv_unmarked.diff` read: marks removed, `clock=` on the four RV1 calls, a path depth). So rework item 1 is met in substance. RV1b passes as it is (it XPASSes). |
| RW-D2: a row timed after the fetch waits; it is never stored `null` | **Accepted.** Acceptance criterion 3 holds even when NSE's clock runs ahead (RR3). An identity no longer depends on the clock: mutant X10 (board meeting keyed by the fetch day) is caught. The cost is documented as a KT limit. For announcements, NSE's own date filter (`to_date` = the run's day) should keep a far-future-dated row out anyway (inference from review 1's `to_date` probe). A board-meeting row with a future `bm_timestamp` would be counted in every run line's `nse_rows_ahead`. |
| RW-D3: the clock is read after both fetches | **Accepted.** Mutant X2 (read before the fetches) is caught. |
| D9 and the KT "Dates" paragraph, rewritten | **Accepted.** They match the code. |

### Independent checks

1. **The re-reviewer's trace**, `analysis_data/pr006_rereview/rr_trace/test_rr_trace.py`.
   - **Setup:** the hermetic boundary is on. The real feed, NSE fetcher (its pauses
     included), sources, classifier and store run. Fakes stand in for the NSE client, search,
     model, user plane and ingestor.
   - **The fake world's clock** advances on every NSE call (0.2–20 s), pause (0.5 s),
     search (0.5–6 s) and model call (2–40 s). NSE's clock is the world's plus a skew.
   - **Expected values** come from the world's own call log and a separate timetable model:
     - a row is visible once NSE's clock reaches its time;
     - it is stored at the first run whose fetch of its stock sees it and is no more than
       10 minutes before its time, with that stock's fetch time;
     - board-meeting ids are hashed in the test.

     None is read from the feed.
   - **RR1:** the example above.
   - **RR2, 40 seeds:** 1 to 30 stocks; NSE's clock from 2 min behind to 9 min ahead; 4 runs
     (Thu 18:30, Fri 08:15, Fri 18:30, Mon 08:15). Filings and articles (announcements, 30% of
     them results, and some `sort_date`-only; board meetings with one or two rows a day;
     articles with ages) fall half within 30 minutes of a run's start and half anywhere.
     - Per stock, the stored ids, `published_at` and `fetched_at` equal the model.
     - `nse_rows_ahead` is 0; ingestion per run equals the model, under each stock's managed
       sector; nothing is sent to the model twice.
     - 43 stores in 16 seeds were R1 cases (filed more than 10 minutes after the run's
       start).
   - **RR3, 25 seeds:** NSE's clock is 10 min 1 s to 25 min ahead.
     - Per run, the waiting counts equal the model.
     - Later runs store each row with its own time, and no NSE event is undated.
     - 22 of the 25 seeds had waiting rows.
   - **RR4:** a replay at a fixed `now` never reads the seam; every `fetched_at` is `now`.
     A fixed `now` before a filing: 2 rows wait and nothing is stored.
   - **RR5:** observation, I3 below.
   - A final test asserts the R1 and waiting counts above, so the families are not vacuous.

   Result: **69 passed**.
2. **Review 1's trace as it is**
   (`pytest -q -p no:cacheprovider analysis_data/pr006_review/rv_trace`): **105 passed, 2
   failed, 1 xfailed**, exactly as the rework predicted.
   - RV1b XPASSes its strict mark.
   - The RV1 observation records the reviewed behaviour, so it fails.
   - RV1a stays xfailed at a fixed `now` (RW-D1).
   - RV2 (40 histories), RV3 (60 cap cases), RV4, RV5 and the RV1 control pass unchanged.
3. **Bite, 11 in-memory mutants aimed at the rework**
   (`analysis_data/pr006_rereview/rr_mutants.py`, run by `run_rr_mutants.py` against the
   trace and against the story file through `-p rr_plugin`; no repository file is written).
   Both are green unmutated. **The story file catches 11 of 11; the trace 10 of 11.**

   | Mutant | Trace failures | Story failures |
   |---|---|---|
   | X1 every stock read at the run's start (the reviewed behaviour) | 68 | 28 |
   | X2 the clock read before the fetches | 67 | 28 |
   | X3 an announcement after the fetch stored undated | 23 | 5 |
   | X4 a board meeting after the fetch stored undated, keyed "" | 22 | 2 |
   | X5 no 10-minute allowance | 47 | 1 |
   | X6 a 30-minute allowance | 24 | 3 |
   | X7 `fetched_at` = the run's start | 67 | 28 |
   | X8 news ages from the run's start | **0** | 1 |
   | X9 waiting rows not counted | 24 | 1 |
   | X10 a board meeting keyed by the fetch day | 67 | 27 |
   | X11 the scheduler's call reads the wall clock once | 68 | 1 |

   **X8 survives the trace, by arithmetic, not by a gap in the work.** "N hours ago" changes
   its IST day between the run's start and the stock's fetch only when the stock is fetched
   more than about 30 minutes into an 18:30 run, or 45 minutes into an 08:15 run. The trace's
   runs last at most about 20 minutes. The story's
   `test_news_ages_count_back_from_the_stocks_own_fetch` (a 35-minute run) catches it.
4. **The story file:** **138 passed.** The new tests' expected values are hand-worked or
   computed from the fake world's timetable. The property test hashes
   `code|meeting|filing day` itself. The implementer's mutant count (56 of 56) was not re-run;
   this review's bite check is independent.
5. **Documentation.**
   - **Text read against the code:** KT section 4 ("Dates", the MARUTI example, three new
     limits), D9, guide 02-I to 02-K, and the `feed.py` and `sources.py` docstrings.
   - **No stale wording:** no other document describes the bound or `fetched_at` (grep of the
     KT, guide, CODEBASE, PRODUCT_MAP, ARCHITECTURE, AUTOPILOT_GUIDE, config, the schema, the
     store, the classifier and the route).
   - **The PDF:** it carries the KT's digest `ac6d6aac…`, the current source (51 pages).
   - **`check_kt_docs`:** exactly the 2 expected errors (`company_events_am/_pm` absent at the
     declared revision `84eefda`, D14). The commit-time header bump clears them.

### Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| R1 (review 1) | Medium | `feed.py`, `sources.py` | — | — | **Resolved** (RR1–RR4; X1–X4, X7, X10, X11 caught) |
| L1 (review 1) | Low | KT section 4 Limits | — | — | **Resolved** (both bullets, then the PDF) |
| I3 | Info | `core/events/sources.py:194-196` (D4, unchanged by rework 1) | A meeting's rows filed the same day merge under one id. A row filed later that day, **after** the stock's fetch, is never typed. RR5: an 18:41:00 "Board Meeting Intimation", then an 18:45:00 "Financial Results" row; MARUTI is fetched at about 18:42. Observed: one event, titled from the first row. The next morning both rows give the same id, already stored. Expected by D4: one event per meeting and filing day. | Small. In the recorded fixture, MARUTI's two rows for the 27 Oct meeting were filed 5 minutes apart (12:44:21, 12:49:46), and each row's text names the purpose. A run must fall between the rows for this to happen. | None. PR-008 can re-read a meeting's rows if its company lane needs every purpose. |

Review 1's I1 and I2 (info) are unchanged. No other finding.

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Fixture announcements and news give events with the expected category, direction and materiality (LLM stubbed); every stored event cites an input item | **Met** (story tests; RV2; RR2) |
| The same announcement fetched on two runs is stored once | **Met**, including a filing NSE shows during a long run, for announcements and board meetings (RR1, RR2, RR3; RV1b) |
| `published_at` equals the source's date; no usable date → `null`, never new | **Met**, including a long run and NSE's clock ahead: a readable time is stored as itself or waits (RR1–RR4) |
| A source, quota or LLM failure logs and skips; the job never raises; the next run retries | **Met** (story tests; unchanged code paths) |
| The symbol cap and query cap hold; the run records how many it used | **Met** (RV3 as it is; story tests) |
| Search-provider usage is logged | **Met** (unchanged) |
| Docs: KT sections 4 and 9 as current design, human test case | **Met** (above) |

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13). The hermetic boundary was on for every pytest
run.

| Command (repository root) | Result |
|---|---|
| `scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-006-manifest.json` | 23 files, 0 mismatches (start and end) |
| `python analysis_data/pr006_rereview/rr_digest.py` | bases 23/23 and 33/33; rework `44ebfddb…` 50,719 B, 5 paths; cumulative `bfafe107…` 180,813 B, 22 paths (start and end) |
| `pytest -q -p no:cacheprovider tests/unit/test_company_events_pr006.py` | **138 passed** |
| `pytest -q -p no:cacheprovider analysis_data/pr006_review/rv_trace` | 105 passed, 2 failed, 1 xfailed (as predicted, above) |
| `pytest -q -s -p no:cacheprovider analysis_data/pr006_rereview/rr_trace` | **69 passed** (`rr_trace_out.txt`) |
| `python analysis_data/pr006_rereview/run_rr_mutants.py` | story 11 of 11 caught, trace 10 of 11 (`rr_mutants_out.txt`) |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | exactly the 2 expected errors; 51 pages; source `ac6d6aac…` |
| `pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,559 passed, 12 skipped, 1 xfailed, 0 failed** in 17 min 6 s (14:16:49–14:34:02 IST) |
| `find data -newermt "2026-10-22 13:39"` after the suite | no file: the checkout's runtime data is unchanged |

**Not exercised:**
- live NSE, Serper and the model (no outside call in this review);
- production: no state read, and the real run length is still unmeasured;
- the route through the real app and the frontend (unchanged by the rework).

### Production and follow-up state

- **STATE:** PR-006 `done`; production verification `pending_deployment`; `active_task: null`;
  **`next_task: PR-011`** (ready: its only dependency, PR-006, is done). PR-011 is not started.
- **Commit, at the owner's word.** PR-004 first, from its own bytes in
  `analysis_data/pr006/base/`, with its own commit-time edits. Then PR-006, with the
  implementation receipt's commit-time edits:
  - the KT header bump, which clears `check_kt_docs`' 2 errors;
  - section 12 PR-006 `Done`, section 1, then the PDF;
  - the guide's 02-I to 02-K status lines.
- **Once deployed,** pushes also avoid 08:10–08:35 and 18:25–18:50.
- **Production verification after the deploy:**
  - the first 08:15 and 18:30 run lines show `status` `ok` or `partial` with named causes,
    `nse_rows_ahead` 0, and `fetched_at` spread across the run;
  - the owner's five-day sample (02-I);
  - watch the Serper count. Rollback: `EVENTS_ENABLED=false`.

## Fresh review — 22 Oct 2026 (changes requested)

**Phase:** a **fresh-session review**: a new conversation opened with "continue", 22 Oct
about 11:33–12:30 IST, session stockagent-main-2c. It is not the implementing conversation
(stockagent-main-bb, idle from 11:25). Peers -1c, -3c, -48, -53, -95 and -bb were idle at the
start and at bookkeeping.
**Verdict: CHANGES REQUESTED.** One medium finding (R1) fails two acceptance criteria in a
reachable case: a filing NSE shows while a long run is still going loses its date for good,
and a board-meeting filing in that case is stored twice. One low documentation finding (L1)
should go in the same rework. Nothing was committed, pushed, deployed or configured. No
production state was read, no message was sent and no reviewed file was changed. One public NSE
endpoint was read once from this machine (below).

**Reviewed revision:** the uncommitted working tree on
`25fae38ecdc1a85b99b4a2c6d759fc2d11dfbdaf`, pinned by
[PR-006-manifest.json](PR-006-manifest.json)
`d2e35f720e00e3c954c22b39cd0a3cf88866b09e0a257d00d6ef5a2e51fb4c82` (23 files), stacked on
PR-004's accepted input.

### In one example

Tue 27 Oct, results season. The 18:30 run tracks 50 stocks. Each stock needs two NSE calls with
1 s of pauses, a search and a model call, so MARUTI, late in the order, is fetched at 18:42. NSE
now shows MARUTI's "Financial Result Updates" filed at 18:41:20.

- **Expected:** stored with `published_at` `…T18:41:20+05:30`. A `since` read for that day
  returns it, and MARUTI's dossier ingestion runs under `automobile`.
- **Observed** (RV1a, the real feed and fetcher with a fake NSE):
  - `published_at` is `null`, because 18:41:20 is more than 10 minutes after the run's
    **start**;
  - the `since` read returns nothing, and no ingestion runs;
  - the next morning's run sees the same row with a correct clock, but the id (`nse:<seq_id>`)
    is already stored. So the event stays undated for good, and the feed never ingests it
    (Saturday's scan does).
- **A board-meeting intimation** filed at that moment (RV1b) is stored undated that evening,
  then again, dated, the next morning: **two events for one filing**.

### Review input and digests

- `kt_manifest.py verify PR-006-manifest.json`: **23 files, 0 mismatches**, at the start
  (11:36 IST) and again after the full suite (12:12 IST).
- **The base, checked independently.** Every one of PR-004's 33 manifest paths in
  `analysis_data/pr006/base/` hashes (`git hash-object --path=<real path>`) to its blob id in
  `PR-004-manifest.json`: 33 of 33. The other 8 base paths are bookkeeping and the owner's
  `docs/README.md`.
- **Diff rebuilt** by the reviewer's own `analysis_data/pr006_review/rv_digest.py`:
  - **`403fb28b…`, 161,569 bytes, 22 paths**, at the start and at the end;
  - 6 paths against the base, 5 against HEAD, 11 new;
  - the 5 HEAD-diffed files contain only PR-006 changes.

  This equals the receipt.
- Outside the input: STATE, HANDOFF and the receipts (bookkeeping), and PR-004's files that
  PR-006 does not change.

### Contract checked

**The story's hard-review questions:**

| Question | Answer |
|---|---|
| Can a fetch-time date masquerade as a publish date? | **No.** NSE times come from `an_dt`, then `sort_date` read year first, and for board meetings `bm_timestamp`, never `bm_date`. A news date comes from Serper's own string: an unreadable or future one is `""`, so `null` (`macro_news_fetcher.py:96-123`). "today" and "just now" are the source's own words. RV2 checks this over 40 random histories, and the reviewer's mutant M1 (fetch day for an undated article) fails 38 of its cases. **The reverse fails: a real date can be lost (R1).** |
| Can one symbol's news be filed under another? | **Not by the code's own checks.** The model never names the stock, an NSE row must carry the code asked for, and an article must mention the company. In RV2 an article naming only TVS Motor is never stored under MARUTI; mutant M3 (no company check) fails 40 cases. **Remaining risk (L1b):** a short code or a name prefix lets another firm's article reach the model, so the model's "not about this company" answer is the only guard. |
| Does the job respect the registry's identity (SA-008)? | **Yes.** RV4 runs the real seams with the shipped registry: TVSMOTORS is fetched as TVSMOTOR, MARUTI as MARUTI, and TATAMOTORS is unresolved, so it is skipped. Events are stored under the app's symbol (`feed.py:272`, `:320`). |

**Code read in full:** the schema, `core/events/` (sources, classify, store, feed), the prompt,
the route, the fetcher and news diffs, the scheduler jobs, the config, the doc checker. **Also
read:** `_normalize_serper_date`, `cfg`'s environment coercion (`EVENTS_ENABLED=false` gives
`False`: `loader.py` coerces to the YAML value's type), `symbol_identity_issue` and
`nse_symbol`, the ingestor's qualifier and `run`, the weekly ingestion job's sector reader
(`scheduler.py:109-116`; the feed's `feed.py:141-144` matches it), `active_user_ids`, and
`get_current_user`.

### Rulings on the implementer's decisions

| Decision | Ruling |
|---|---|
| D1 `core/events` outside the intelligence plane | **Accepted.** The ingestor trigger is the allowed arrow. |
| D2 a member reads own holdings, watchlist and the shelf | **Accepted.** The premise holds: `/discovery/shelf` is readable by any signed-in user (`discovery_api.py:24-25`). The 404 detail is the same template whether or not events exist, and the 422 for a malformed symbol comes before any lookup. |
| D3 one event per item; only "unrelated" remembered, per stock | **Accepted.** Seen items are keyed by stock (`feed.py:308`), so an "unrelated" answer for one stock never hides the item from another. |
| D4 board meetings dated by filing, merged per meeting and filing day | **Accepted, with R1.** The id includes the filing day only when the time was accepted (`sources.py:180`, `:194`), so a row first read undated gets a second id. |
| D5 an article must mention the company | **Accepted, with L1b.** |
| D6 figures compared as numbers, two or more digits | **Accepted.** One-digit figures are not checked (I1). |
| D7 60 searches a day, half per run, a spent credit stops the run | **Accepted.** RV3: 60 random cases of cap, stocks and runs per day, all hold; mutants M4, M5 and M9 caught. |
| D8 same-day ingestion for a new qualifying announcement of an enabled managed stock | **Accepted.** RV2 checks exactly one ingestion per run with a new dated qualifying MARUTI filing, and none for unmanaged stocks (mutant M7 caught). |
| D9 one `published_at` at source precision; "a time more than 10 minutes after the fetch is `null`" | **Accepted as a rule; the code does not implement it (R1).** The bound is the run's start (`feed.py:181`, passed through `:239` and `:279-280` to `sources.py:108`), not the fetch. |
| D10–D13 | **Accepted.** For D13 the reviewer confirmed one more shape fact: NSE's `to_date` includes that day (below), so the 18:30 run sees the same day's filings. |
| D14 the doc checker's slot loop table | **Accepted.** `check_kt_docs` gives exactly the 2 expected header errors. |

### Independent checks

1. **NSE's date range** (one public, read-only call through the feed's own
   `fetch_company_filings`, `analysis_data/pr006_review/nse_day_probe.py`, 11:42 IST): MARUTI,
   21 Oct to 21 Oct, returned the 21 Oct 15:39:05 filing (`106823400`). So a range ending on
   the run's day includes that day. The story's fake (inclusive `to_date`) matches.
2. **The reviewer's trace**, `analysis_data/pr006_review/rv_trace/test_rv_trace.py`.
   - **Setup:** the hermetic boundary is on, and the real feed, fetcher, sources, classifier and
     store run. Fakes stand in for the NSE client, the search seam, the model, the user plane
     and the ingestor.
   - **Expected values:** hand tables and a clock-driven simulation written in the trace, never
     the feed's output.
   - **RV1a, RV1b** (strict xfail): R1, as in the example. **RV1 observation:** what the reviewed
     code stores. **RV1 control:** the same filing at 18:39:20, fetched at 18:40, is dated and
     ingested. So the threshold is the start plus 10 minutes, whatever the fetch time.
   - **RV2, 40 random histories:** 3 stocks (one an alias, TVSMOTORS→TVSMOTOR), 14 runs over 7
     trading days.
     - Sources: announcements (normal, `sort_date`-only, unreadable), board meetings (one or
       two rows per filing day, some undated), and articles with ages, absolute dates or none,
       some carrying `utm_` parameters. MARUTI's search also returns another stock's article.
     - Each stock's stored set and every `published_at` equal the simulation.
     - No id is stored twice, and no item is sent to the model twice.
     - `since` reads are exact.
     - The ingestor runs once per run with a new dated qualifying MARUTI filing.
   - **RV3, 60 random cases:** caps from 0 to 9, 0 to 8 stocks, 1 to 4 runs a day for 3 days,
     and a spent credit at a random search.
     - Per day, searches never exceed the cap; per run, never more than half of it, rounded
       up.
     - Searching stops at the spent credit, and the next run searches again.
   - **RV4:** the registry identity through the real seams.
   - **RV5** (observation): see L1b.

   Result: **106 passed, 2 xfailed (strict)**.
3. **Bite.** `run_rv_mutants.py` runs RV2 and RV3 once per in-memory mutant (`RV_MUTANT`;
   the conftest compiles the changed source in memory, and no repository file is written).
   **9 of 10 caught:** M1 fetch day for undated news, M3 no company check, M4 a run spends the
   whole day, M5 a spent credit ignored, M6 a board meeting takes its latest row, M7 every
   announcement ingests, M8 known items re-sent, M9 the counter forgets earlier runs, M10
   `sort_date` read day first. **M2** (the store keeps a second copy of a known id) is not
   caught, because the feed already filters stored ids before the store sees them (equivalent
   at feed level). The story's store tests cover it directly.
4. **Run length (inference, not measured).** This checkout's local telemetry (read with
   `immutable=1`): 91 successful `deepseek-v4-flash` calls, Jul–Sep, median 4.3 s for about
   120 output tokens. A 12-item answer is several times longer, so with the NSE pauses and a
   search, 8–20 s per stock with new items is plausible. 40–60 stocks then exceed 10 minutes.
   The implementer's receipt also records "no time bound on a run", unmeasured.

### Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| R1 | **Medium** (confirmed: RV1a, RV1b; trigger timing inferred) | `core/events/feed.py:181` reads `now` once per run, `:228` sets `fetched_at` from it, and `:239` / `:279-280` pass it to `sources.py`; there `nse_time` (`:101-110`) rejects times after `now + 10 min` (`:57`, `:108`). Board-meeting identity: `sources.py:180`, `:194`. | A run lasts more than 10 minutes, and a stock is fetched after NSE has published a filing made after start + 10 min. **Observed:** that announcement is stored with `published_at: null`; it is permanent, since its id is NSE's `seq_id`. A `since` read never returns it, and the qualifying results filing runs no same-day ingestion. A board-meeting row is stored undated under id (code, meeting, "") and again, dated, on the next run: two events. Also, within the 10-minute slack, `published_at` can be after `fetched_at`. **Expected** (card; D9: "after the **fetch**"): the filing time; one event per filing; ingestion that run. | Fails acceptance criteria 2 (stored once, for board meetings) and 3 (`published_at` equals the source's date) in this case. These are the issue-time and idempotency invariants that AGENTS.md singles out. The store is append-only, so wrong rows outlive the run and reach PR-005/007/008/009 when they read it. Evening results filings in results season are the likeliest case. Nothing trades on it yet. | **Must fix (rework 1).** Direction, the implementer's choice: (a) read the clock per stock at the fetch, through a seam, and use it for the future bound and for `fetched_at`; (b) do not let a row's id depend on whether its time was accepted: either leave an NSE row timed after the fetch clock for the next run (the 7-day window brings it back), or key a board meeting by the raw filing day; (c) a feed-level test with a run longer than 10 minutes. RV1a and RV1b are ready to run without their marks. |
| L1 | Low (documentation) | KT section 4 **Limits** (`docs/TECHNICAL_DESIGN.md:701`); `config.yaml:498` | **(a)** `news_recency: "qdr:d"` searches the past 24 hours, so Monday 08:15 misses news published Fri 18:30–Sun 08:15 (about 38 h), and similarly after an NSE holiday. NSE filings are covered by the 7-day window; the config comment says so, the KT does not. **(b)** A short code or a name prefix passes the company check for another firm (RV5): "LT Foods" for L&T (code `LT` in capitals); "Indian Railway Finance Corporation" for IRCTC (prefix "indian railway"); "HDFC Life Insurance" for LIC (prefix "life insurance"). The model's answer is then the only guard. The receipt names only Tata Motors, and the KT's limits name neither. | A reader of the KT would expect weekend news coverage and a code-level guard that is not there. 02-I's sample would notice (b) but not (a). | In rework 1: two KT section 4 limit bullets, then the PDF. Widening the first run after a non-trading day is a product call for PR-008's company lane; no change asked here. |
| I1 | Info | `core/events/classify.py:70-81` | One-digit figures are not checked (D6 by design): "a dividend of Rs 8" passes for an item saying Rs 6. | The card requires a citation only; this check goes beyond it. | None. |
| I2 | Info | `core/events/feed.py:288-294` | With no Serper key, each attempted search still counts against the day's budget, and every run is `partial`. | Production has a key. The run line would overstate searches only in a keyless environment. | None. |

No other finding.

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Fixture announcements and news give events with the expected category, direction and materiality (LLM stubbed); every stored event cites an input item | **Met** (story tests; RV2) |
| The same announcement fetched on two runs is stored once | **Met** for announcements and news (RV2, 40 histories). **Not met** for a board meeting filed during a long run (RV1b, R1) |
| `published_at` equals the source's date; no usable date → `null`, never new | **Not met** for a filing made during a long run (RV1a, R1); met otherwise (RV2) |
| A source, quota or LLM failure logs and skips; the job never raises; the next run retries | **Met** (story tests; code read: `feed.py:187-197`, `:236-248`) |
| The symbol cap and query cap hold; the run records how many it used | **Met** (RV3; story tests) |
| Search-provider usage is logged | **Met** (`feed.py:254-261`) |
| Docs: KT sections 4 and 9 as current design, human test case | **Met, with L1.** 02-I to 02-K describe the reviewed behaviour. PRODUCT_MAP's 15 routers matches `server.py`; the endpoint count went from 89 to 90 (one route). The PDF source is `60368f58…`, equal to the KT. |

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13). The hermetic boundary was on for every pytest
run.

| Command (repository root) | Result |
|---|---|
| `scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-006-manifest.json` | 23 files, 0 mismatches (start and end) |
| `python analysis_data/pr006_review/rv_digest.py` | base 33 of 33 PR-004 blobs; `403fb28b…`, 161,569 B, 22 paths (start and end) |
| `python analysis_data/pr006_review/nse_day_probe.py` | 1 announcement for 21–21 Oct: `to_date` is inclusive |
| `pytest -q -p no:cacheprovider analysis_data/pr006_review/rv_trace` | **106 passed, 2 xfailed** (strict, R1) |
| `python analysis_data/pr006_review/run_rv_mutants.py` | **9 of 10 caught** (M2 equivalent at feed level) |
| `pytest -q -p no:cacheprovider tests/unit/test_company_events_pr006.py` | **105 passed** |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | exactly the 2 expected errors (`company_events_am/_pm` absent at the declared revision `84eefda`); PDF source `60368f58…` |
| `pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,526 passed, 12 skipped, 1 xfailed, 0 failed** in 13 min 32 s (11:58:37–12:12:16 IST) |
| `find data -newermt "2026-10-22 11:30"` after the suite | no file: the checkout's runtime data is unchanged |

**Not exercised:**
- live Serper and a live model call (no credit spent);
- production: no state read, and the real run length is not measured (R1's trigger timing is
  inference);
- the route through the real app (the story's tests do this with real sessions; the reviewer
  read the code);
- the implementer's 45 mutants (this review's bite check is independent);
- the frontend (no screen changed).

### What rework 1 must deliver

1. **R1 fixed**, with RV1a and RV1b passing without their marks. The story file gains a
   feed-level test of a run longer than 10 minutes, for an announcement and for a board
   meeting.
2. **L1:** two bullets in KT section 4's limits, then the PDF and `check_kt_docs`.
3. Rewrite the receipt's D9 and the KT "Dates" paragraph so the bound is the fetch, and say
   what `fetched_at` now means if (a) is taken.
4. A new manifest and diff: rework diff against this input, and cumulative against the base.
   This receipt's input stays `d2e35f72…`; keep it as `PR-006-manifest-review1.json` before
   rewriting the manifest.
5. A fresh re-review in a new conversation. The reviewer's trace and mutant runner are in
   `analysis_data/pr006_review/`.

The implementation receipt's commit-time edits still apply after acceptance:
- the KT header bump, which clears `check_kt_docs`' 2 errors;
- section 12 `Done`, section 1, then the PDF;
- the guide's 02-I to 02-K status lines.

PR-004 is committed first, from its own bytes in `analysis_data/pr006/base/`.

### Production and follow-up state

STATE: PR-006 `changes_requested`, `active_task: null`, **`next_task: PR-006`** (rework 1 in a
new conversation, then a fresh re-review, then PR-011). Production verification
`not_started`. PR-004 stays `done`, `pending_deployment`, uncommitted underneath.
