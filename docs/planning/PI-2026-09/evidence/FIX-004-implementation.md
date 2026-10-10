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
