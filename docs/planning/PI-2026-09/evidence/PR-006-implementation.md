# PR-006 — implementation receipt

**Story:** [PR-006](../stories/PR-006.md): a daily company-event feed for held, watched and
shelf stocks.
**Phase:** implementation, 22 Oct 2026, about 08:19–11:25 IST. Session stockagent-main-bb, a new
conversation opened with "continue"; peers stockagent-main-1c, -3c, -48, -53 and -95 were idle
at the start and at bookkeeping. The laptop slept from about 09:11 to 10:55 IST, during a
mutant run (re-run, below).
**Baseline:** the uncommitted working tree on `25fae38`: PR-004's accepted input
(`PR-004-manifest.json`, `aec91b8f…`, 0 mismatches at the start) plus the planning
bookkeeping. `analysis_data/pr006/base_snapshot.py` copied every changed or untracked path
before the first edit (41 paths, index `4c9bea32…`), and each of PR-004's 33 paths reproduced
its manifest blob id. This is the FIX-007-on-SA-011 pattern: PR-006's diff is against that
base, so PR-004 can still be committed on its own.
**Status after this phase:** `review_required`. Nothing was committed, pushed or deployed. No
production state was read and no message was sent. NSE's public announcements and
board-meetings endpoints were read twice from this machine, for MARUTI, to record their shape
(below). No search credit was spent and no model was called.

## Rework 1 (22 Oct 2026, about 12:19–13:10 IST)

**Context.** Session stockagent-main-46, a new conversation opened with "continue"; peers -1c,
-2c (the review), -3c, -48, -53, -95 and -bb were idle at the start and at bookkeeping. It
answers the fresh review's CHANGES REQUESTED ([review receipt](PR-006-review.md)). It includes
a same-conversation self-review, which is not the fresh re-review. **Status after:**
`review_required`. Nothing was committed, pushed or deployed, no production state was read, no
message was sent, and no outside endpoint was called.

**Input.** The reviewed input, kept byte for byte as
[PR-006-manifest-review1.json](PR-006-manifest-review1.json) (`d2e35f72…`), verified with 0
mismatches at the start. Its 23 files were copied to the ignored
`analysis_data/pr006/rework1/base/` and each copy checked by blob id (`base_snapshot.py`).

### In one example (R1)

Tue 27 Oct, the 18:30 run tracks 50 stocks. MARUTI is the 50th, and its fetches return at
18:42:30. NSE shows its results filing and a board-meeting intimation, both filed at 18:41:20.

- **Reviewed code:** every stock was checked against the run's start plus 10 minutes (18:40),
  so both were stored with `published_at: null`. The results filing stayed undated for good
  (its id is NSE's `seq_id`): no `since` read returned it and no ingestion ran. The intimation
  was stored again, dated, the next morning, under a second id.
- **Now:** the clock is read when MARUTI's fetches return. Both are stored with
  `published_at` 18:41:20 and `fetched_at` 18:42:30, a `since` read returns them, and MARUTI's
  dossier ingestion runs in this run. The next morning stores and sends nothing again.

### Changes

| Finding | Change |
|---|---|
| **R1** (medium, must fix) | **(a)** `core/events/feed.py`: a clock seam `_clock()` and `run_event_feed(..., clock=None)`. `_one_symbol` reads the clock once, after the stock's NSE fetch and news search have returned. That moment checks the NSE times, is what news ages count back from, and is the stock's `fetched_at`. `started_at` and `finished_at` come from the same clock. The scheduler's call, `run_event_feed(slot)`, reads the wall clock; a replay at a fixed `now` reads `now` for every stock unless it passes a clock (RW-D1). **(b)** `core/events/sources.py`: `nse_stamp` reads an NSE time without a clock, and `is_ahead` is the 10-minute bound. A row whose readable time is more than 10 minutes after the fetch is not an item: it is counted and left for a later run (RW-D2). `announcement_items` and `board_meeting_items` return `(items, foreign, ahead)`, and the run record gains `nse_rows_ahead`. A board meeting's identity takes the filing day from the row's own timestamp, so the clock never enters an id. **(c)** Feed-level tests of long runs (below). |
| **L1** (low, docs) | KT section 4 Limits: (b) the short-code and name-prefix matches ("LT Foods" for L&T, "Indian Railway Finance Corporation" for IRCTC, "HDFC Life Insurance" for LIC), and (a) the weekend and holiday news gap (`qdr:d`: Monday 08:15 misses Friday 18:30 to Sunday 08:15). Then the PDF. |
| D9 and the KT "Dates" paragraph | Rewritten: the bound is each stock's fetch; what `fetched_at` means; `null` means the source gave no readable date. One more KT limit, from RW-D2: an NSE time that stays in the future is never stored. Guide 02-I gains the `fetched_at` and `nse_rows_ahead` expectations and the Monday news gap, so a tester does not log it as a defect. |

### Decisions (delegated, recorded)

- **RW-D1. A `clock` argument; a replay keeps a fixed clock.** The feed must learn when each
  stock is fetched, and a test cannot let real minutes pass. Options:
  - A (chosen): the module seam `_clock` (the wall clock) serves the scheduler's call, and a
    `clock` argument serves tests. A call with a fixed `now` and no clock reads `now` for
    every stock. A replay at a fixed time stays deterministic, and the existing tests and the
    reviewer's RV2 to RV5 keep their meaning.
  - B: always read `_clock`. A test passing `now` without replacing `_clock` would mix a fixed
    start with today's wall clock, so its fetch times, news ages and bounds would change with
    the day the suite runs.

  Consequence: the reviewer's RV1a calls the feed with `now=START` and sets only the fake
  NSE's clock, so the feed cannot see that MARUTI is fetched at 18:42. Its unmarked copy passes
  `clock=lambda: env.nse.clock` (below).
- **RW-D2. A time after the fetch waits; it is never stored as `null`.** The review offered
  two ways to stop an id depending on whether its time was accepted: leave the row for a later
  run, or key a board meeting by its raw filing day. Both are done: the row waits, and the
  board-meeting key comes from the row's own timestamp.
  - With the per-stock clock a row waits only when NSE's clock runs more than 10 minutes ahead
    of ours. Waiting keeps acceptance criterion 3 even then: the next run (the 7-day window
    brings the row back) stores it with its own time. Storing it undated would keep it `null`
    for good.
  - The cost: a row whose time stays in the future (a wrong timestamp) is never stored, and
    every run counts it in `nse_rows_ahead` (a KT limit).
  - The 10-minute allowance stays, so within it `published_at` can be later than `fetched_at`
    (KT "Dates").
- **RW-D3. The clock is read after the fetches, not before.** A row NSE returned was filed
  before NSE answered, so the moment the stock's fetches return is the tightest correct bound.
  One read per stock, after the news search too, gives one `fetched_at` per stock, and news
  ages count back from when Serper answered (seconds from the NSE fetch).

D9 is rewritten below. D1–D8 and D10–D14 are unchanged.

### Tests

Story file: **138 tests (was 105)**. Expected values are hand-worked, or computed in the
test from the fake world's timetable; none is read from the changed code.

| Case | Tests |
|---|---|
| Sources | `test_a_filing_timed_after_the_fetch_is_left_for_a_later_run` (4 cases: 10 min 1 s, 45 min and a day after the fetch, and a `sort_date`-only row. No item and counted; a day later the same row is an item with its own time and the same id); `test_a_filing_stamped_seconds_after_the_fetch_clock_is_kept` (90 s, and exactly 10 min); `test_an_unreadable_filing_time_is_none_never_the_fetch_time` (3 cases, none counted as later); `test_a_board_meeting_timed_after_the_fetch_is_left_and_keeps_one_identity` (two rows for one meeting: none at 18:31:19; one item dated by the earlier row at 18:42; the same id the next morning, equal to the hash of code, meeting day and filing day written in the test) |
| R1 in a long run | `test_a_filing_made_during_a_long_run_keeps_its_time_and_is_ingested` (the example above: 50 stocks, 7.5 s per NSE call, MARUTI asks at 18:42:15 and 18:42:22.5; both events at 18:41:20 with `fetched_at` 18:42:30; the `since` read; one ingestion; nothing stored or sent the next morning); `test_news_ages_count_back_from_the_stocks_own_fetch` (MARUTI fetched at 19:05:00, so "19 hours ago" is 22 Oct, not 21 Oct); `test_the_scheduler_call_reads_the_clock_seam_per_stock` (`run_event_feed("pm")` with `_clock` replaced: started 18:30:00, `fetched_at` 18:30:10, :20 and :30, finished 18:30:30); `test_a_filing_nse_stamps_ahead_of_our_clock_waits_for_the_next_run` (NSE 11 min 10 s ahead: 2 rows counted, nothing stored or sent; the next morning both stored once at 18:53:20, and the ingestion runs then) |
| Property | `test_any_run_length_stores_each_filing_once_with_its_own_time`, 25 seeds: 1 to 12 stocks, 1 to 90 s per NSE call, 0–4 announcements and 0–3 board meetings per stock (about half with a second row the same day), filed from 2 h before the first run to 30 min after the third one ends; three runs. Expected per stock: each filing stored once, at the first run whose call for its stock comes at or after it, with its own time and that stock's fetch time from the timetable; `nse_rows_ahead` 0; no item sent to the model twice. |

**Existing tests changed** (a contract moved; no assertion relaxed): the direct calls of
`announcement_items` and `board_meeting_items` unpack three values, and the first of them also
asserts nothing waits. The former `test_an_unusable_filing_time_is_none_never_the_fetch_time`
is split: its unreadable cases stay `null` (one case added: neither field in NSE's formats),
and its two later-than-the-fetch cases moved to the new waiting test.

**Mutants** (`analysis_data/pr006/rework1/run_mutants.py`, in memory through
`rw_swap_plugin.py`; no repository file is written): **56 of 56 caught**. They are the
implementation's 45 (S7 and F11 re-anchored to the rework's text) and the rework's 11:

- RW1 every stock read against the run's start (the reviewed behaviour); RW2 the scheduler's
  call reads the wall clock once; RW3 the clock read before the fetches;
- RW4 an announcement after the fetch stored undated (reviewed); RW5 the same for a board
  meeting, then a second id (reviewed); RW6 a board meeting keyed by the fetch day; RW7 no
  10-minute allowance;
- RW8 `finished_at` from the wall clock; RW9 waiting rows not counted; RW10 a passed clock
  ignored; RW11 news ages from the first stock's fetch.

The reviewed behaviour, expressed on the new code, is RW1 (28 tests fail), RW4 (5) and RW5 (2). Output: `rework1/mutants_out.txt`.

**The reviewer's trace** (`analysis_data/pr006_review/`, not changed):

- **As it is:** **105 passed, 2 failed, 1 xfailed** (`rework1/rv_trace_asis.txt`), as
  expected. RV1b now passes, so its strict xfail fails as XPASS. The RV1 observation records the
  reviewed behaviour and fails: with the trace's fixed clock the evening run now stores nothing,
  because the filing waits. RV1a stays xfailed: the trace runs the feed at a fixed `now`
  (RW-D1). RV2 (40 histories), RV3 (60 cap cases), RV4, RV5 and the RV1 control pass unchanged.
- **Unmarked copy** (`rework1/rv_unmarked/`, made by `make_rv_unmarked.py`; its diff is
  `rv_unmarked.diff`): the two marks removed, the four RV1 calls pass
  `clock=lambda: env.nse.clock`, and the conftest's repository path is one level up. **107
  passed, 1 failed**: only the observation test (`rv_trace_unmarked.txt`). RV1a and RV1b pass.
- **The reviewer's 10 mutants** against RV2 and RV3 on the reworked tree
  (`rework1/run_rv_mutants.py`, a copy that writes its output under `rework1/`): **9 of 10 caught, with the same number of failing tests per mutant as in the review (M2 is equivalent at feed level, as the review found); `rework1/rv_mutants_out.txt`**.

### Commands (rework 1)

| Command (repository root) | Result |
|---|---|
| `kt_manifest.py verify` the reviewed input, at the start | 23 files, 0 mismatches |
| `analysis_data/pr006/rework1/base_snapshot.py` | review-1 manifest kept (`d2e35f72`); 23 files copied, 0 blob mismatches |
| `pytest -q -p no:cacheprovider tests/unit/test_company_events_pr006.py` | **138 passed** |
| `analysis_data/pr006/rework1/run_mutants.py` | **56 of 56 caught** |
| `pytest -q -p no:cacheprovider analysis_data/pr006_review/rv_trace` | 105 passed, 2 failed, 1 xfailed (expected, above) |
| `pytest -q -p no:cacheprovider analysis_data/pr006/rework1/rv_unmarked` | 107 passed, 1 failed (the observation, expected) |
| `analysis_data/pr006/rework1/run_rv_mutants.py` | **9 of 10 caught, with the same number of failing tests per mutant as in the review (M2 is equivalent at feed level, as the review found); `rework1/rv_mutants_out.txt`** |
| `scripts/ci/check_broad_except.py`; `scan_source` on the untracked `core/events/*.py` and `events_api.py` | OK (151 grandfathered); no finding |
| `scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 51 pages (was 50), source `ac6d6aac…`; exactly the 2 expected errors (D14) |
| `pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,559 passed, 12 skipped, 1 xfailed, 0 failed in 11 min 18 s (12:54:30–13:05:53 IST; was 5,526: the 33 new story tests). The manifest and both digests were re-checked after it: unchanged** |
| `find data -newermt "2026-10-22 12:15"` after the suite | no file: the checkout's runtime data is unchanged |

### Self-review (same conversation)

- Read the rework diff again. One behaviour detail: when a row's `an_dt` is readable but
  after the fetch, the row waits; it no longer falls back to a `sort_date` that is not after
  the fetch. NSE gives the same time in both fields.
- The scheduler test that replaces `run_event_feed` calls it with the slot only, as the job
  does; the new `clock` argument is optional.
- `_FUTURE_SLACK`'s comment was reworded while the mutant run was going (a comment only, no
  anchor touched); the 13 mutants of `sources.py` were then re-run on the final bytes: 13 of 13 caught.

### Manifest and digests (rework 1)

- **Review input:** [PR-006-manifest.json](PR-006-manifest.json), the same 23 paths, **`ec6eaf86fd339bff1112d4bc8c37c76c8f238d16281bee2948cafe82c8695067`**,
  0 mismatches (`analysis_data/pr006/rework1/write_manifest.py`).
- **Rework diff:** **`44ebfddbaccf6dd28cc4d0bad6eeee2cc08ce0508730011ad6a301a8ce2356e4`**, 50,719 bytes over 5 paths
  (`rework1/rw_digest.py`: `git diff --no-index rework1/base/PATH PATH` for each manifest path
  except the PDF, headers relabelled `a/PATH`; unchanged paths give no output): `core/events/feed.py`, `core/events/sources.py`, `docs/TEAM_TESTING_GUIDE.md`, `docs/TECHNICAL_DESIGN.md` and the story test file. The PDF is the sixth changed file; `kt_manifest.py verify` of the review-1 manifest gives exactly these 6 mismatches.
- **Cumulative diff:** **`bfafe107cf3fa1f395e5dd3cb5a388961e3b3fd892a76d8124adfc49cdd447a0`**, 180,813 bytes over 22 paths: the
  implementation's recipe (`analysis_data/pr006/digest.py`) on today's bytes, written to
  `rework1/cumulative.diff`.

## In one example

At 08:15 on Thu 22 Oct MARUTI is held.

- **Before:** nothing looks at MARUTI's filings or news until someone runs an analysis, and
  the dossier learns of a results filing on Saturday.
- **After:**
  1. NSE lists two filings in the 7-day window: 21 Oct 15:39:05, "Analysts/Institutional
     Investor Meet/Con. Call Updates" (seq_id 106823400), and 15 Oct 19:13:00, "Action(s)
     taken or orders passed". The board-meeting rows (27 Oct results meeting, filed 8 Oct) are
     outside the window.
  2. One Serper search returns five articles. "Tata Motors shares slip after JLR wholesales
     update" does not mention Maruti Suzuki or MARUTI, so the model never sees it.
  3. One bulk-tier call types the rest. Each event is filed under MARUTI, with the cited
     item's own date: the 21 Oct filing as `2026-10-21T15:39:05+05:30`, an article dated "10
     hours ago" as `2026-10-21`, an article with no date as `null`. `fetched_at` is
     `2026-10-22T08:15:00+05:30` on all of them.
  4. The 21 Oct filing is an analyst-meet filing, which the event ingestor qualifies, so
     MARUTI's dossier ingestion runs now, under its managed sector, `automobile`.
  5. At 18:30 the same items come back and none is sent to the model.

This is the story's main end-to-end test
(`test_two_runs_store_each_item_once_and_classify_it_once` and its neighbours) on the
recorded NSE payload.

## What changed

| Area | Change |
|---|---|
| Event schema (`src/backend/shared/schemas/events.py`, new) | `CompanyEvent`: `id, symbol, what, category, direction, materiality, source, source_url, announcement_id, title, publisher, published_at, published_raw, fetched_at, classifier`; the category, direction and materiality vocabularies. The one schema SA-046 is to adopt. |
| Sources (`core/events/sources.py`, new) | NSE announcement and board-meeting rows and Serper results → `SourceItem` with an identity, a text and the source's own time; the code check for NSE rows; the company-mention check for articles (`name_phrases`, `mentions_company`). |
| Classifier (`core/events/classify.py`, new; prompt `core/config/prompts/shared/company_events.py`, new) | One bulk-tier JSON call per batch, recorded with `record_llm_call("company_events", …)`; grounding: a cited item, figures that the item contains (compared as numbers), the vocabularies; "not about this company" answers. |
| Store (`core/events/store.py`, new) | `EventStore`: `data/events/<SYMBOL>.jsonl` (append-only, one id once, a file lock), `state.json` (the day's search count, unrelated items for 30 days), `runs.jsonl`; `read(since=)` never returns an undated event; only an NSE symbol names a file. |
| Feed (`core/events/feed.py`, new; `core/events/__init__.py`) | `run_event_feed(slot)`: tracked stocks (holdings, watchlists, shelf), identity skips, the NSE code, both caps, new items only, batches, storage, same-day ingestion, the run record and the search-usage log line. Never raises. |
| NSE fetcher (`services/data/fetchers/nse_announcements.py`) | `fetch_company_filings(nse, symbol, since, until)`: announcements in a date window and every board-meeting row, raw, no key-registry writes; one failing endpoint keeps the other. `prefetch_nse_data` unchanged. |
| News fetcher (`services/data/fetchers/news.py`) | `search_serper_news_status` returns `(results, status)` with `ok, empty, no_key, exhausted, http_<code>, error`; `search_serper_news` returns its results, unchanged. `company_news_query(ticker)` is the daily review's query, now shared; `get_news_context` uses it. |
| Scheduler (`services/scheduler/python/scheduler.py`) | Jobs `company_events_am` (Mon–Fri 08:15) and `company_events_pm` (18:30) when `EVENTS_ENABLED`; a malformed time skips that job with a warning. `_company_events_job` skips NSE holidays and records `record_job_outcome("company_events_<slot>", …)`. |
| Route (`services/api/routes/events_api.py`, new; `services/api/server.py`) | `GET /events/{symbol}?since=&limit=`; mounted; `events/` added to the API namespaces so an unknown `/events/...` path is a 404, not the app page. |
| Config (`config.yaml`, `src/backend/shared/config/settings/base.py`) | `events.*` (13 keys); `enabled: true` in config, fallback `false`. |
| Doc checker (`scripts/docs/check_kt_docs.py`) | The reviewed dynamic job IDs are a table: `ipo_refresh_{slot}` and now `company_events_{slot}`. |

## Data sources: what was measured

Public endpoints, read from this machine on 22 Oct about 08:50 IST through the `nse` package
(2.1.3 locally; production pins `<4.0`). Raw output in `analysis_data/pr006/` (ignored);
the fixture below is its unmodified first rows.

- `NSE.announcements(symbol="MARUTI")` with no date range returned **2,017 rows**, MARUTI's
  whole history; with 15–22 Oct it returned 2. So the feed always sends a range.
  (`prefetch_nse_data`, which every analysis runs, downloads the whole history and keeps 10;
  not changed here.)
- Announcement fields: `symbol, desc, an_dt ("21-Oct-2026 15:39:05"), sort_date
  ("2026-10-21 15:39:05"), seq_id, attchmntFile, attchmntText, sm_name, sm_isin,
  exchdisstime, …`.
- Board-meeting fields: `bm_symbol, bm_date ("27-Oct-2026", the meeting), bm_timestamp
  ("08-Oct-2026 12:44:21", the filing), bm_purpose, bm_desc, attachment, sm_isin, …`. NSE
  returned 20 rows with no range; with 1–31 Oct it returned the two rows whose **meeting** is
  in October. So the date filter is on the meeting day, and the feed filters filings itself.
- Board-meeting intimations are not in the announcements feed: 7–9 Oct had no announcement,
  while two board-meeting rows were filed on 8 Oct. The two sources complement each other.

Recorded fixture: `tests/fixtures/company_events/nse_maruti_20261022.json` (3 announcements,
3 board-meeting rows, unmodified; public filings, no personal data). The news fixture
`serper_news_maruti.json` is **constructed**, not recorded, in Serper's `/news` shape: a live
query spends search credit (D13).

## Design decisions (delegated, recorded)

Optional technical calls, made under the owner's standing delegation ("i trust your technical
expertise").

- **D1. Outside the intelligence plane.** The feed reads users' portfolios, and
  `core/intelligence` must never import the user plane (R1, `test_atlas_import_boundary.py`).
  So it lives in `core/events/`, and the store holds no user. The ingestor trigger is the
  allowed arrow, user plane → intelligence.
- **D2. The route shows a member their own stocks.** An event is a market fact, as the card
  says, but the feed covers only stocks someone tracks. If any member could read any symbol, a
  member could learn the owner's holdings: `GET /events/INFY` with events means someone holds
  or watches INFY. So a member reads their holdings, watchlist and the shelf (which every
  member sees), and gets the same 404 for anything else; the owner reads any.
- **D3. One event per source item.** Every item about the company becomes one event; routine
  filings are `other`, `low`. Identity is NSE's `seq_id` or the URL without `utm_*`, so the
  store de-duplicates by id. Only "not about this company" answers are remembered separately
  (`state.json`, 30 days), so they are not asked again. A failed or invalid answer is not
  remembered and is asked again next run, while the item is in the window.
- **D4. Board meetings.** The publication time is `bm_timestamp`, the filing; never
  `bm_date`. Rows filed on the same day for the same meeting (NSE files an intimation and a
  "Financial Results" row) become one item. A row with no filing time is kept, undated, only
  when its meeting is on or after the window start. An intimation never triggers ingestion:
  the meeting has not happened, and the ingestor skips it until then (FIX-004).
- **D5. Articles must mention the company** before the model sees them: the ticker or NSE
  code in capitals, the name without legal suffixes, or the first two words of a name with
  three or more. Then the model may still answer "not about this company". Names come from the
  curated or learned name, the managed list, then NSE's `sm_name`.
- **D6. Figures are grounded.** A sentence stating a figure of two or more digits that the
  cited item does not contain is dropped, compared as numbers ("3,500" = "3500", "35" ≠
  "3500"). The story's own test found the first version, a substring check, let "Rs 35
  billion" through for "Rs 3,500 crore".
- **D7. Search budget.** `news_queries_per_day: 60`, each run at most half (30), in stock
  order (held first); a spent credit (`exhausted`, HTTP 400) stops that run's searches.
  Worst case about 60 a trading day, about 1,300 a month. The counter is written once per
  run, so a process killed mid-run can over-spend by at most that run's half.
- **D8. Same-day ingestion** runs in either daily run, for a newly stored NSE
  **announcement** whose subject the ingestor's own keyword rule qualifies, and only for an
  enabled managed stock, under its managed sector (`get_active_tickers_with_sector`, the
  weekly job's reader). The ingestor's watermark keeps Saturday from repeating it. KT section 5
  now says a row dated the brief's own day can be a filing made that morning.
- **D9. One `published_at` field at the source's precision** (rewritten in rework 1): a
  date-time with `+05:30` from NSE, a date from news; its first ten characters are always the
  IST day. `published_raw` keeps the source's string. The clock is read once per stock, when
  its fetches return; that moment is the stock's `fetched_at`. An NSE time more than 10
  minutes after it is not stored yet: the row is counted (`nse_rows_ahead`) and a later run
  stores it with its own time. `null` means the source gave no readable date (or, for news, a
  date in the future). The reviewed version checked every stock against the run's start and
  stored such a time as `null` (review R1).
- **D10. On at deploy, store only.** `events.enabled: true` in config (fallback `false`), as
  the card's rollout says ("runs dark (store only)"). Rollback: `EVENTS_ENABLED=false`.
- **D11. Corporate actions** (`NSE.actions()`) are not read: their rows have an ex-date and
  no filing time, so every one would be undated. Dividends, splits and record dates arrive as
  announcements.
- **D12. Runs skip NSE holidays** (the card says trading days); the 7-day window covers long
  weekends.
- **D13. Fixtures.** NSE's payload was recorded once, from public endpoints, for the field
  names. The news fixture is constructed in the shape the code already reads, because
  recording one spends a paid Serper credit.
- **D14. The doc checker.** The scheduler registers the two jobs in one loop, like the IPO
  refresh; `check_kt_docs.py` lists that f-string as reviewed. Its header check reports the two
  new job IDs as absent at the KT's declared revision `84eefda` until the commit-time header
  bump (below).

## Invariant tests

`tests/unit/test_company_events_pr006.py`, 105 tests. Expected values are written by hand from
the card and the recorded payload, not read back from the code.

- **Source dates:** the recorded announcements give `nse:<seq_id>` and the filing time as
  IST; `sort_date` is read year first (FIX-004's "2026-10-08 17:10:00" trap); an empty,
  unreadable, 45-minutes-later or next-day time is `null`, never the fetch time; a filing
  stamped 90 seconds after the fetch clock is kept. The two 8 Oct board-meeting rows become one
  item dated 8 Oct 12:44:21, never 27 Oct, with the same id in either row order. Article ages
  against an independent clock: 200 random ages and fetch times, the day computed in the test.
- **The company:** a row for another NSE code is dropped and counted (announcements and board
  meetings); 11 hand-written mention cases (Tata Motors vs Tata Elxsi, `M&M`, `TCS`, "a bright
  idea" vs IDEA, State Bank, Bank of Baroda vs "Bank stocks", Adani Ports, an unknown name).
  NSE is asked for the registry code (TVSMOTOR) and the event is stored under TVSMOTORS, both
  with a fake and with the shipped `config/instruments.yaml` (TATAMOTORS skipped as
  unresolved). The model's own `symbol`, `published_at` and `source` keys are ignored.
- **Stored once:** two runs store 6 events and make one model call; an id is stored once
  across calls and within a batch; an event cannot be written into another stock's file.
- **Grounded:** an index out of range, 0, `true` or missing; a figure the item lacks; a
  converted unit; an unknown category or direction; an empty sentence; a non-object: each
  dropped and counted. Five malformed outputs and a raising call store nothing.
- **Caps:** 5 tracked stocks with a cap of 3 keep the two holdings and the watchlist stock;
  four runs in a day with a daily cap of 5 use 3, 2, 0, 0, and the next day starts again;
  24 items per stock and 12 per call are honoured (5 and 2 in the test: calls of 2, 2, 1,
  the undated item left for later).
- **Failures:** NSE failing, a news HTTP 503, a spent credit, a model failure, one stock's
  crash and a crash in reading the users: each logs, the run never raises, its record says
  `partial` or `failed`, and the next run stores what was missed.
- **Ingestion:** a qualifying announcement runs the ingestor once, under the managed sector,
  and not again on the next run; none for an unmanaged stock, a board-meeting intimation, or
  with the switch off.
- **Run record and privacy:** the record counts stocks, searches and calls, names skipped
  stocks, matches the returned record, and no file in `data/events/` holds a user id; the
  search-usage line is logged.
- **Route,** through the real app with real sessions: a member reads their holding, watchlist
  stock and the shelf idea (any case); the owner's stock and an untracked stock give the same
  404; the owner reads any; `since` excludes earlier and undated events; 422 for `BAD$`,
  `MARUTI.NS`, `limit=0` and a non-date; 401 without a session when sign-in is required.
- **Fetchers and jobs:** `fetch_company_filings` sends the window and keeps a working
  endpoint; `search_serper_news_status` for each status, through a fake `requests.post`; the
  real search seam and query through the feed (the exact Serper request body is checked); both
  jobs registered at 08:15 and 18:30 Mon–Fri, absent when disabled, the evening one absent
  with a malformed time; the job runs on Thu 22 Oct and records its outcome, and not on Sat
  24 Oct.

**Mutants:** `analysis_data/pr006/run_mutants.py` compiles each of 45 mutants of the
working tree in memory (`swap_plugin.py`; no repository file is written) and runs the story
file. **45 of 45 caught**: 9 on source dates and the company check, 8 on grounding, 6 on the
store, 15 on the feed, 3 on the route, 1 on the news status, 1 on the NSE window, 2 on the
jobs. The first run caught 27 and then timed out while the laptop slept; the remaining 18
were run again and all caught (`mutants_out.txt`, `mutants_out2.txt`).

## Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), the vendored Playwright Chromium for the PDF.
Hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_company_events_pr006.py` | **105 passed** |
| `.stockai/Scripts/python.exe analysis_data/pr006/run_mutants.py` (then the last 18 by name) | **45 of 45 caught** |
| the 57 test files that import a changed module, plus the story file (`analysis_data/pr006/affected2.txt`) | **1,081 passed** in 2 min 37 s |
| `.stockai/Scripts/python.exe -m pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,526 passed, 12 skipped, 1 xfailed, 0 failed** in 13 min 26 s (PR-004's 5,421 plus these 105) |
| `.stockai/Scripts/python.exe scripts/ci/check_broad_except.py` | **OK (151 grandfathered)** |
| `python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 50 pages (was 49), source `60368f58…`; **exactly 2 errors**: "KT documents job company_events_am / company_events_pm, which is absent at its declared revision 84eefda04682". They are expected: the header names a commit without the jobs, and the commit-time header bump clears them (D14). No other error. |
| `kt_manifest.py verify` both manifests, after the suite | PR-006: 23 files, 0 mismatches. PR-004: 7 mismatches, exactly the 7 shared files PR-006 changed; PR-004's own bytes are in `analysis_data/pr006/base/` |
| `find data -newermt "2026-10-22 08:00"` after the suite | no file: the checkout's runtime data is unchanged |

Raw outputs (ignored, `analysis_data/pr006/`): `nse_probe.py` and `nse_probe_out.json`,
`make_fixture.py`, `base_snapshot.py` and `base/`, `swap_plugin.py`, `run_mutants.py`,
`mutants_out.txt` and `mutants_out2.txt`, `digest.py` and `pr006.diff`, the suite outputs.

## Documentation

Each change is written as current design.

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - section 4, new "Company events": the run in five steps, the record, dates, the company,
    grounding, same-day ingestion, who reads it, the MARUTI example and the limits; the
    readers are **Planned:** PR-005, PR-007, PR-008, PR-009, and SA-046's reader;
  - section 2, a `core/events` row; section 3, a `data/events/` row;
  - section 5 "Company knowledge": event ingestion also runs in the feed's runs, so a row of
    the brief's own day can be that morning's filing;
  - section 9: 26 job IDs, rows `company_events_am` and `company_events_pm`;
  - sections 6, 10 and 11: the planned readers point to section 4 instead of "PR-006".
  - New files are named in code text, not linked: `check_kt_docs` requires a linked file to
    exist at the declared revision. Section 12's PR-006 row stays `Open`.
- **PDF** rebuilt: 50 pages (was 49), source SHA-256 `60368f58…`.
- **CODEBASE:** the `core/events/` module map, a `/events` API section, the `events.*`
  configuration table, a note under the dossier-ingestion table, key-file rows (feed, schema,
  route, the NSE fetcher) and a `data/events/` row.
- **PRODUCT_MAP:** the fetcher table, the EventIngestor cadence, the event store, 15 routers
  and 90 endpoints with an `events` row, and the two jobs in the schedule.
- **Human testing guide** (HT-02): 02-I (five trading days of events against their sources,
  the owner's first-week sample from the card's rollout), 02-J (member access and identity
  skips), 02-K (failures and caps in a test environment). Status: "PR-006: implemented
  2026-10-22; fresh review pending."
- No change: ARCHITECTURE (no job or data-source list at this level), AUTOPILOT_GUIDE
  (nothing trades on events), `docs/README.md`, the story cards (SA-046 already says it adopts
  this schema).

## Manifest and digest

- **Review input:** [PR-006-manifest.json](PR-006-manifest.json), 23 files. The SHA-256 of its
  LF bytes is **`d2e35f720e00e3c954c22b39cd0a3cf88866b09e0a257d00d6ef5a2e51fb4c82`**;
  `kt_manifest.py verify` gives 0 mismatches (written by `analysis_data/pr006/write_manifest.py`).
  - Code (15): `config.yaml`, `core/config/prompts/shared/company_events.py` (new),
    `core/events/__init__.py`, `classify.py`, `feed.py`, `sources.py`, `store.py` (new),
    `scripts/docs/check_kt_docs.py`, `services/api/routes/events_api.py` (new),
    `services/api/server.py`, `services/data/fetchers/news.py`,
    `services/data/fetchers/nse_announcements.py`, `services/scheduler/python/scheduler.py`,
    `src/backend/shared/config/settings/base.py`, `src/backend/shared/schemas/events.py` (new).
  - Tests (3, new): `tests/unit/test_company_events_pr006.py` and the two fixtures in
    `tests/fixtures/company_events/`.
  - Docs (5): the KT and its PDF, CODEBASE, PRODUCT_MAP, the testing guide.
  - Excluded: STATE, HANDOFF and this receipt (bookkeeping); every PR-004 path PR-006 does not
    change; the owner's line in `docs/README.md`.
- **Diff digest:** **`403fb28b45a7e0a6a59c4737434e29b18d35c20d74fd556ef42dc3263230340a`**,
  161,569 bytes over 22 paths (every manifest path except the PDF), by
  `analysis_data/pr006/digest.py`. It checks that HEAD is `25fae38`, then for each path,
  sorted: `git diff --no-index analysis_data/pr006/base/PATH PATH` (headers relabelled
  `a/PATH`) for the 6 text paths PR-004 also changed (the PDF is the seventh);
  `git diff HEAD -- PATH` for the 5 paths only PR-006 changes; `git diff --no-index /dev/null
  PATH` for the 11 new files. Run twice, before
  and after the full suite: the same digest.
- **Base:** `analysis_data/pr006/base_snapshot.py` (run once, before the first edit) and its
  `base_index.json` (`4c9bea32…`): 41 paths with git blob and SHA-256. A reviewer can check
  that each of the 33 PR-004 paths in it carries the blob id in `PR-004-manifest.json`.

## Self-review

Same-conversation self-review; it does not replace the fresh review.

- Found by the story's own tests and fixed: the figure check was a substring test ("35" in
  "3500"), D6.
- Read again after the tests: the per-stock and per-run exception handlers log and name the
  stock; `save_state` runs in a `finally`; the route validates the symbol before it names a
  file; nothing writes a user id. No change.
- Checked: `data/` in the checkout is untouched (no file newer than this session); the
  managed list, the key registry and `telemetry.db` keep their old times.

## Limits and follow-ups

- **An article that names the company only by a short form** ("Maruti", "L&T") without its
  ticker in capitals is dropped. The first-week sample (02-I) shows how often.
- **Duplicates across outlets:** one story in three articles is three events. PR-008 groups by
  company, category and day (its card already says so).
- **Ambiguous names:** "Tata Motors" news matches both TMPV and TMCV by the two-word prefix;
  the model's "not about this company" is the only guard there.
- **No retention** on `data/events/` yet: a few events per stock per day.
- **No time bound** on a run. Unmeasured: per stock two NSE calls with 0.5 s pauses, one search
  and at most one model call; the 08:15 run should end well before 08:45, but nothing stops it.
- **An announcement without `an_dt` or `sort_date`** is undated; NSE's `exchdisstime`
  is not used as a fallback.
- **Search credit:** up to about 1,300 more Serper queries a month at the default cap (D7).
  SA-035 measures the real plan; lower `events.news_queries_per_day` if needed.

## For the owner

- Runs dark: the feed stores events and runs the dossier ingestion earlier; nothing trades,
  advises or sends a message on them.
- **At rollout:** the deploy adds two jobs, at 08:15 and 18:30 IST on trading days, so pushes
  should also avoid 08:10–08:35 and 18:25–18:50. For the first week, read five held stocks'
  events each day (guide 02-I) and record whether they are right. Watch the Serper count in
  the run log line. Rollback: set `EVENTS_ENABLED=false`.
