# FIX-004 implementation receipt — never date dossier knowledge after the day it was learned

- **Story:** [FIX-004](../stories/FIX-004.md), routed from finding F1 of the
  [SA-038 implementation](SA-038-implementation.md). The count probe ran on 7 Oct
  ([probe receipt](FIX-004-probe-2026-10-06.md)).
- **Context:** implemented on 8 Oct 2026 in **one new conversation** opened with "continue" (from
  about 15:33 IST). STATE: `review_required`. A same-conversation self-review was done; it is not
  the fresh review.
- **Baseline:** `5ea49fe` (SA-038's KT bump; deployed as Railway `406ad444`). The probe phase's
  bookkeeping from 7 Oct was still uncommitted: STATE, HANDOFF, the probe receipt, the SA-038
  review's L2 note and the FIX-004 card. This phase keeps those edits.
- **Nothing** was committed, pushed, deployed or configured. Claude read no production state.

## What it does, in one example

On 7 Oct the IDFCFIRSTB dossier held three observations dated **24 Oct**. Event ingestion had read
a board meeting announced for 24 Oct, and stamped everything it wrote with the meeting's date.
`to_digest` sorts by date and lists the newest five, so 3 of the 5 "Recent observations" every
agent read for that stock were about a meeting that had not happened.

After FIX-004:
- **A new meeting.** Say the Sat 10 Oct scan sees a meeting dated 24 Oct that was not ingested
  before. It skips it: nothing is written and no watermark key is added. The 17 Oct scan does the
  same. The 24 Oct scan runs on the meeting day, so it digests the meeting, dated 24 Oct. A
  meeting on Tue 27 Oct is digested by the 31 Oct scan, dated 27 Oct (4 days back, inside the
  8-day lookback). IDFCFIRSTB's and STARHEALTH's own meetings are already in their watermarks, so
  they are not digested again (L1).
- **The digest on 8 Oct** lists IDFCFIRSTB's five newest observations dated 8 Oct or earlier. The
  three 24 Oct rows stay on disk, but no digest shows them before 24 Oct.

## The rule chosen, and why

The card asks the implementation to choose between "stamp the day it was learned, keep the
scheduled date in the text" and "skip the event until it happens", and to record why.

**Write time: skip an event dated after the run date until it has happened.**
`find_qualifying_events` drops any item dated after `today` (`event_ingestor.py:121`), and
`EventIngestor.run` passes its own run date as `today` (`:224`, `:235`). Reasons:
1. **The prompt says the event happened.** `EVENT_SYSTEM_PROMPT` opens "A corporate event just
   happened (results, concall, …)". Digesting a meeting that has not been held asks the model for
   its outcome. Stamping the scan date would fix the date but not the text, and a prompt change
   cannot be tested deterministically.
2. **Nothing is lost.** The fundamentals and earnings agents already receive upcoming board
   meetings from the live NSE feed (`format_nse_context`, `[NSE BOARD MEETINGS — official dates]`).
3. **The scan cap.** Candidates are sorted newest first and capped at 3
   (`EVENT_INGEST_MAX_EVENTS_PER_SCAN`). Before, future meetings sorted first and could take every
   slot from the week's real announcements. Filtering before the cap gives the slots back.
4. **Signatures and guidance.** A digested event can confirm a response signature (occurrences +1,
   confidence +0.05) and change guidance status. An event that has not happened cannot confirm a
   price response.
5. **It is picked up later.** A skipped event gets no watermark key. The lookback is 8 days and the
   scan weekly, so the first scan on or after the meeting date sees it, and it is then dated as any
   past event: its own date.

Past and same-day events are unchanged. They keep their own date, and the watermark key stays
`date|subject[:60]`.

**Read time: leave the row out.** `to_digest` takes `as_of` (ISO date; default `date.today()`) and
chooses "Recent observations" (newest 5) and "Open guidance" (last 5 open) only from rows dated on
or before it (`dossier.py:89`, `:102`, `:119`, `:134`). Re-labelling would need a new section for
text written under the "just happened" prompt. Clamping would show a date that is wrong. Stored rows
are not rewritten. No caller changed, since all five call `to_digest` without a date.

## Every writer of a dossier date (the card's hard-review list)

| Writer | Date it stamps | After FIX-004 |
| --- | --- | --- |
| `DossierCurator._merge` (daily review) | `entry.date`, the graded trading day | unchanged; never after the review run |
| `QuestionResearcher` `_apply` / `expire_stale_questions` | `date.today()` | unchanged |
| `distill_dossier` (weekly) | `date.today()` for new signatures and resolved questions; folds by date | unchanged |
| `EventIngestor.run` → `merge_curator_output(today=event["date"])` | the event's date | only events dated on or before the run date reach it |
| `PredictionStore.save_dossier` | `last_updated = date.today()` | unchanged |

`merge_curator_output` stamps its `today` on observations, guidance, signature `first_seen`,
`last_seen` and `evidence_dates`, `thesis_since`, and open questions' `raised_on` and
`resolved_on`. The new invariant test exercises every one of these through event ingestion. This
list comes from a search of `core/`, `services/`, `src/` and `scripts/` for every constructor and
assignment of these fields.

## Tests

All commands were run from the repository root with the project venv
(`.stockai/Scripts/python.exe`, Windows). SA-005's hermetic boundary was active: no `.env`, no
network and no access to the checkout's `data/`. NSE, Tavily and the LLM are fakes.

**New file `tests/unit/intelligence/rl/test_dossier_dates_fix004.py`, 53 tests:**
- **The date table.** Eight events (announcements and board meetings) against a pinned run date,
  Sat 10 Oct: 9 days back, the lookback edge, 2 days back, yesterday, the same day, tomorrow, and
  the two measured cases (24 and 27 Oct). The expected column is written by hand from the card's
  rule, and `test_table_matches_the_rule` checks it against a short statement of that rule, not
  against the implementation. The run must write each digested event's rows under the event's own
  date. The fake LLM must never see a skipped event, and only digested events may be watermarked.
- **The invariant.** Every date in the saved dossier is on or before the run date. That covers all
  the fields above, plus `created_at` and `last_updated`.
- **The cap.** With 3 future meetings and 3 past announcements, the 3 slots go to the past
  announcements.
- **One board meeting, from scan to digest.** STARHEALTH's shape: weekly scans on 10, 17 and 24 Oct
  write nothing and call no LLM. The 31 Oct scan writes it dated 27 Oct. A digest dated 26 Oct lists
  neither its observation nor its guidance, and one dated 27 Oct lists both. A 3 Nov scan does not
  ingest it again.
- **The digest with the clock pinned to 7 Oct** (the probe's date), on IDFCFIRSTB's measured shape:
  7 past observations, 3 dated 24 Oct, and an open guidance item dated 27 Oct. "Recent
  observations" lists the 5 newest past rows. No 24 or 27 Oct date appears.
- **45 digest dates**, 7 Oct −20 to +24 days. No listed observation or guidance date is after the
  digest's date, and the observations listed are the 5 newest of those on or before it (same-day
  included). When there are none, there is no empty section header.
- Explicit `as_of` overrides the clock, and a digest leaves the stored rows unchanged.

**Changed:** `test_event_ingestor.py`. Its two fakes of `find_qualifying_events` accept the new
`today` keyword. No assertion changed.

**Focused run:**
`python -m pytest -q -p no:cacheprovider tests/unit/intelligence/rl/test_dossier_dates_fix004.py tests/unit/intelligence/rl/test_event_ingestor.py tests/unit/intelligence/rl/test_dossier_schema.py`
→ **80 passed** in 2.9 s.

**Baseline and mutants** (`analysis_data/fix004/impl/mutants.py`, ignored; it swaps source bytes,
runs the 3 files above, and restores the bytes, which it checks are byte-identical afterwards):

| Case | Result |
| --- | --- |
| Both files at `5ea49fe` | caught: 52 failed |
| Event ingestion at `5ea49fe` only | caught: 4 failed (the table, the default clock, the cap, scan to digest) |
| Digest at `5ea49fe` only | caught: 51 failed |
| M1: no upper bound on the event date | caught: 4 failed |
| M2: also drops same-day events (`>=`) | caught: 2 failed |
| M3: stamps the run date instead of the event's date | caught: 2 failed |
| M4: observations unfiltered in the digest | caught: 39 failed |
| M5: open guidance unfiltered | caught: 42 failed |
| M6: the digest drops same-day rows (`<`) | caught: 12 failed |
| M7: the digest ignores the clock | caught: 1 failed |

**Full suite:**
`python -u -m pytest -q -p no:cacheprovider -o console_output_style=count tests` → **4214 passed,
12 skipped, 0 failed** in 13 min 58 s. That is SA-038's 4161 plus the 53 new tests. A digest of
`data/`, `logs/` and `outputs/` (paths and bytes, 800 files) is the same before and after:
`0542ad05…`. The first attempt, without `-u`, wrote nothing to its buffered log file. Another
project's tests were running on the same machine, and it was stopped at the 30-minute background
limit. Its result is unknown, and it is not counted.

**Documentation checks:** `scripts/docs/build_kt_pdf.py` regenerated the PDF (source
`ae47071f…`, 35 pages). `check_kt_docs.py` reports errors `[]`, 448 local links (re-run after the HANDOFF edits).

## Documentation

- **KT** ([TECHNICAL_DESIGN.md](../../../TECHNICAL_DESIGN.md) §5, the knowledge-tasks paragraph):
  the rule, labelled "implemented 2026-10-08, awaiting its fresh review", with the 7 Oct measured
  count. The PDF is regenerated. The header still declares `70fce66`; the usual KT bump follows the
  commit.
- **[RL_DESIGN.md](../../../RL_DESIGN.md)** §23.1 (the digest) and §26 (the scan).
- **[TEAM_TESTING_GUIDE.md](../../../TEAM_TESTING_GUIDE.md)**: new case 04-H, and FIX-004 added
  to HT-04's related-PI line.
- **Cards:**
  - [FIX-004](../stories/FIX-004.md): "Implementation choice", with the reasons above.
  - [SA-046](../stories/SA-046.md): a note that the raw dossier still holds the old future rows.
  - [SA-013](../stories/SA-013.md): the routed limit (L3 below).

## Manifest and digest

- **Review input:** [FIX-004-manifest.json](FIX-004-manifest.json), 11 files. The SHA-256 of its
  LF bytes is **`2f4cf4827c03e1d3ba4d1e4bc9949ca7c82ad96237f601d007d9b9f1f208b90b`**, and
  `kt_manifest.py verify` gives 0 mismatches.
  - Files: the 2 code files, the 2 test files, the KT and its PDF, RL_DESIGN, the testing guide,
    and the FIX-004, SA-013 and SA-046 cards.
  - Excluded: STATE, HANDOFF and this receipt (bookkeeping), and the 7 Oct probe phase's own
    files, unchanged since then: the probe receipt and the SA-038 review's L2 note.
  - The FIX-004 card also carries the uncommitted 7 Oct probe-phase edits, so its diff against the
    baseline shows both phases.
- **Diff digest:** **`5550aab9eda371dd79cc8acfb23159193b1dc3d6e44037efa96a1ede99d745ba`**, 36,266
  bytes over 10 files.
  - **To rebuild it:** take every manifest path except the PDF, sorted. For a path tracked at
    `5ea49fe`, run `git diff --no-color --no-ext-diff 5ea49fe -- PATH`. For the new test, run
    `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`. Concatenate the outputs.
  - `analysis_data/fix004/impl/diff_digest.py` does exactly this.

## Self-review

No critical or high finding. Findings, most severe first:

- **L1 (low). The old rows come back on their date.** IDFCFIRSTB's three rows were written before
  7 Oct, under the "just happened" prompt, about a meeting on 24 Oct. From 24 Oct the digest lists
  them as observations of that day, and STARHEALTH's guidance from 27 Oct. Nothing stored says when
  a row was learned, so the read rule cannot tell them apart. No migration is authorised. Their
  watermark keys stay, so the meeting itself is not digested again. They leave the digest as newer
  rows arrive, and the 30-row buffer drops them in time. If the owner wants them gone sooner, that
  is an authorised production data edit of 4 rows. It is not proposed here.
- **L2 (low). A skipped meeting depends on later scans.** A meeting skipped as future is digested
  only if a weekly scan runs within 8 days after it, and NSE's board-meetings list still has it
  among the first 5 items (`prefetch_nse_data` keeps `items[:5]`). That second condition was not
  measured. The results themselves arrive as a separate announcement (for example "Outcome of
  board meeting"), which qualifies and is dated when published.
- **L3 (low, routed to SA-013). Dates are event dates, not learned dates.** A past event is still
  dated with its own day, while its Tavily page is fetched on the scan day, up to 8 days later.
  `as_of` is a "now" filter, not a point-in-time view: in a digest dated before a later write, the
  thesis and signatures from that write still render. This matters only to a retrospective replay.
  The card keeps past events unchanged.
- **I1 (info). Same-day events.** A meeting dated the scan day (a Saturday) is digested at
  10:00 IST, possibly before it ends. The card keeps same-day events unchanged.
- **I2 (info). Other dated digest lines.** "Thesis (since …)" and "Open questions (since …)" are not
  filtered. On 7 Oct none of them was future-dated (`thesis` 0, `oq_raised` 0), and no writer can
  now stamp a future one.
- **I3 (info). One clock.** Event ingestion, the store's `last_updated`, the research loop and the
  digest all use the container's `date.today()`. The daily curator uses the graded trading day.
  Whether Railway runs in UTC or IST was not read. The scan runs at 10:00 IST and the forecast at
  09:00 IST, when both clocks show the same date.

## Production verification (after a deploy; not authorised here)

Read-only, by the owner, after a deploy:
1. Rerun the count probe after the first weekly scan that runs on the new code. Any row dated after
   the day its scan ran is a failure. Baseline (7 Oct): 3 observations, 1 guidance item and 4 keys
   dated after the probe date. The Sat 10 Oct scan runs before any deploy and may add more.
2. Sample IDFCFIRSTB's digest before 24 Oct. Its "Recent observations" shows no 24 Oct row.

## Rollout and rollback

The change reaches production only on deploy. This phase authorises no deploy, production variable
or data migration. Rollback: revert the commit. Rows written after the fix carry past dates, so a
revert leaves them valid. The old future rows stay as they are either way.

## Change 1 (2026-10-10): the morning brief's earnings watch

Implemented 2026-10-10, about 15:28–16:05 IST, in a new conversation opened with "continue".
Source: the fresh review's L1 and I1 ([review](FIX-004-review.md)). Baseline `0ebd29b` (FIX-004
committed as `ff95a51`, then the KT bump). Same-conversation self-review only; the fresh review
is a new conversation. Nothing committed, pushed, deployed or configured; no production state read.

### What it does, in one example

A held stock has results on Tue 27 Oct. Its dossier holds an open guidance item dated 15 Sep and
a pre-FIX-004 item dated 27 Oct (STARHEALTH's measured shape: one stored guidance item dated
27 Oct, 7 Oct probe).
- **Before:** the briefs of Mon 26 and Tue 27 Oct, the two inside the brief's 3-day earnings
  window, show "watch: <the 27 Oct item>". That text was written before the meeting under the
  "just happened" prompt.
- **After:** both briefs show "watch: <the 15 Sep item>". With only the 27 Oct item, the line is
  the generic "results & guidance are the next catalyst.". From 28 Oct the 27 Oct item counts;
  by then the stock is no longer in the window.

### The rule, and why it differs from the scope's wording

The scope said "dated on or before the brief's date (the digest's rule)". The brief counts guidance
dated **before** its date, which is the same rule applied as of the day before the brief.
- **Why (code):** the brief runs Mon–Fri at 08:50 IST
  (`services/scheduler/python/scheduler.py:385-392`; misfire grace 30 minutes). Guidance has
  exactly three writers, all through `merge_curator_output`. They are the curator at the daily
  review (`FEEDBACK_CRON`, default `30 16 * * mon-fri`), and event ingestion and the research
  loop on Saturdays at 10:00 and 11:00 (`scheduler.py:299-330`). `distill_dossier` only changes
  a status. So at 08:50 on a weekday no row dated that day can come from today's code.
- **Measured:** the production review runs at 16:30 (SA-039 P1/P2 logs, 28–29 Sep).
- **Why it matters:** the earnings window includes the meeting day (`next_results_event`:
  `ev_date >= on`). With "on or before", the 27 Oct row would still be the watch line on the
  27 Oct morning, before the meeting. Of the two briefs in its window (26 and 27 Oct), that rule
  would fix one.
- **Cost:** a brief triggered by hand after the 16:30 review leaves out that day's new guidance
  until the next day (self-review L1).

### Design

- `TickerDossier.open_guidance(as_of=None)` (`src/backend/shared/schemas/dossier.py:89`): open
  items dated on or before `as_of` (default: today), in stored order. The digest's "Open guidance"
  is now `open_guidance(as_of)[-5:]`, the same rule as before, moved. One place for both readers.
- `_earnings_watch(symbol, on)` (`core/delivery/brief.py:346`): the last item of
  `open_guidance(on - 1 day)`, else `""`. `on` is now required; `build_morning_brief` passes the
  brief's date. "Latest" stays the latest stored, as before: guidance is append-only, so this is
  the latest learned. A Saturday scan appends a 6 Oct announcement after the curator's 8 Oct row;
  the 6 Oct item is the later one learned.
- Every consumer (text, HTML, the chat brief tool) reads the built brief, so all are covered.

### Tests

- **New file** `tests/unit/test_brief_earnings_watch_fix004.py`, 51 tests. The clocks of the brief
  and the dossier are pinned to 1 Dec, after every fixture date, so code that reads the clock
  instead of the brief's date shows the future row.
  - A hand-written table of 8 brief dates against stored guidance (one met item, one future
    item). `test_table_matches_the_rule` checks the table against the rule, written separately.
  - The review's L1 reproduction (23 Oct, guidance dated 24 Oct), and the 24 Oct morning.
  - A sweep of 36 brief dates across the meeting. The watch line is always an item dated before
    the brief, never the future row up to the meeting day, and always the last "Open guidance"
    line of the digest as of the day before.
  - The latest stored wins over the latest dated. No dossier, or a store that raises, gives `""`.
  - End to end, through a real `PredictionStore` under `tmp_path` and a stubbed events calendar:
    `build_morning_brief` on 26 and 27 Oct, `render_brief_text` and `render_brief_html` never show
    the future row and show the earlier item. With only the future row, the generic line.
- **The review's I1**, in `test_dossier_dates_fix004.py` (+2): a dossier with 7 known open items
  among 10 lists the newest 5 (written by hand), and `open_guidance` keeps stored order, drops
  later and closed rows, keeps a same-day row and defaults to today.
- **Changed:** `test_delivery_brief.py`'s two `_earnings_watch` tests pass the brief's date, and
  the first uses a real `TickerDossier` with dated items instead of a duck-typed fake. The fake had
  no `open_guidance`. Same assertion.
- **Focused:** 172 passed (the three files). With the event-ingestor and curator tests, 201.
- **Baseline and mutants** (`analysis_data/fix004/change1/c1_swap_plugin.py`, in memory; repo files
  never written): all 12 caught. The HEAD baseline fails 53, mostly on the new signature. Among the
  mutants, **W0** (the baseline's behaviour: no date check) fails 38, and **W1** (the scope's
  literal "on or before") fails 7, on the table's same-day rows, the meeting morning and both end
  to end tests. W2 (last item, then the date check) fails 35, W3 (latest dated) 1, W4 (clock) 38,
  W5 (dossier default) 38, and W6 (the caller passes the clock) 3. **G1** (the review's surviving
  variant) now fails 1. OG1 (status ignored) fails 4, OG2 (strictly before in `open_guidance`) 8,
  and OG3 (`as_of` ignored) 49.
- **Full suite:** **4267 passed, 12 skipped, 0 failed** (361 s; 4214 + 53). `data/`, `logs/`
  and `outputs/` unchanged (800 files, `0542ad05…` before and after).
- `check_kt_docs`: errors `[]` (449 links, PDF 35 pages, source `6b1e4b5e…`).

### Documentation

- **KT** (`docs/TECHNICAL_DESIGN.md` §5): the L1 sentence now states the brief's rule and why. The
  PDF was rebuilt.
- **RL_DESIGN** §23.1: `open_guidance` and the brief's use of it.
- **Testing guide 04-H:** the brief on the day before the results and on the results morning.
- **Cards:** FIX-004 "Change 1", with the decision. SA-046: the brief now has the rule; raw
  readers should use `open_guidance`.

### Manifest and digest

- **Review input:** [FIX-004-change1-manifest.json](FIX-004-change1-manifest.json), 11 files. The
  SHA-256 of its LF bytes is
  **`146c7507f191e975d4242f8700cd838bff93793aab2322ef86882918875d5d6a`**; `kt_manifest.py verify`
  gives 0 mismatches.
  - Files: the 2 code files, the 3 test files, the KT and its PDF (blob `1d43620c`), RL_DESIGN,
    the testing guide, and the FIX-004 and SA-046 cards.
  - Excluded: STATE, HANDOFF and this receipt. STATE and HANDOFF also carry the previous
    session's uncommitted push and deploy note.
- **Diff digest:** **`2ebe6299449677c79d173e6d3200034d7bfcc7a14ac04170946f6fd3604eb375`**,
  28,835 bytes over 10 files. Same recipe as above with baseline `0ebd29b`
  (`analysis_data/fix004/change1/diff_digest.py`).

### Self-review (not the fresh review)

No critical, high or medium finding.
- **L1 (low): a brief triggered by hand after the 16:30 review** (the delivery API's
  `run-brief` route)
  leaves out the guidance the curator wrote that day. Its watch line is the previous open item or
  the generic line, never a wrong one, and the next morning's brief counts it. Accepted for the
  rule above.
- **L2 (low): the rule rests on the schedule.** If the review were moved before 08:50, or a
  dossier writer were run by hand before a brief, a row dated that day would wait one day. The
  schedule is code, and the 16:30 review time is measured (SA-039 P1/P2).
- **I1 (info): the digest still counts same-day rows**, as reviewed. Its scheduled readers run at
  16:30, after a meeting has usually ended. A morning reader of the digest, such as the chat tool,
  shows an old future row on its own day: IDFCFIRSTB's 24 Oct observations on Sat 24 Oct, and
  STARHEALTH's 27 Oct guidance on 27 Oct. Unchanged and out of scope; the reviewer may route it.
- **I2 (info): other raw readers stay as they are** (review I4): the operator CLI
  (`run_schedule.py` `ingest-events` prints the stored open guidance after a run, and
  `dossier-status` counts it) and the weekly `distill_dossier` prompt.

### Not exercised

Production. A real brief delivery. The 08:50 run in production (code only). The container time
zone: `run_morning_brief` takes `date.today()`, and 08:50 IST is the same calendar date in UTC.

### Production verification (after a deploy; not authorised here)

Read-only, by the owner, only if STARHEALTH is held on 26 or 27 Oct: that morning's brief shows
no watch line from the 27 Oct row. Otherwise this change is a guard, with nothing to observe.
