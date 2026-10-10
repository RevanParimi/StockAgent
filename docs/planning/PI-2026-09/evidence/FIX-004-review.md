# FIX-004 review receipt — never date dossier knowledge after the day it was learned

## Fresh-session review: ACCEPTED (2026-10-10)

- **What was reviewed:** [FIX-004](../stories/FIX-004.md), as described in the
  [implementation receipt](FIX-004-implementation.md).
  - Event ingestion skips an event dated after the run (`event_ingestor.py:93`, `:121`), and
    `run()` passes its own run date (`:224`, `:234-235`).
  - `TickerDossier.to_digest(as_of=None)` picks "Recent observations" and "Open guidance" from
    rows dated on or before `as_of`, which defaults to today (`dossier.py:102-105`, `:119`,
    `:134-135`).
  - 53 new tests, two fakes widened in `test_event_ingestor.py`, KT §5 and the PDF, RL_DESIGN
    §23.1 and §26, guide case 04-H, and the FIX-004, SA-013 and SA-046 cards.
- **Context:** a fresh-session review in a new conversation, 10 Oct 2026, about 14:36–15:05 IST.
  - It is not the conversation that implemented FIX-004 (8 Oct), and it did not read that chat.
  - It read the card, the receipt, REVIEW.md, the whole code and test diff, and the documentation
    diff. It traced event ingestion, the shared merge, the daily curator, the research loop,
    `distill_dossier`, the store's save stamp, the NSE prefetch and its key registry, every caller
    of `to_digest`, and every other reader of dossier observations and guidance.
  - The StockAgent peer sessions were idle throughout (ListAgents at the start and before the
    bookkeeping).
- **Nothing** was committed, pushed, deployed or configured. No production state was read, and no
  test or probe made a network call (SA-005's hermetic boundary was active in every run).

### Review input verified

- The reviewer's own script (`analysis_data/fix004/review/rv_verify.py`, ignored; it also saves
  the rebuilt diff as `rv_diff.patch`), not the implementer's `diff_digest.py` or
  `kt_manifest.py`, checked the input:
  - the manifest's LF SHA-256 is **`2f4cf482…`**, as recorded;
  - all 11 paths match both their git blob id and their SHA-256: **0 mismatches**;
  - the diff rebuilt by the receipt's recipe is **`5550aab9…`**, 36,266 bytes over 10 files, as
    recorded.
- Files changed outside the manifest are the ones the manifest excludes by design: STATE, HANDOFF,
  the implementation receipt, and the 7 Oct probe phase's receipt and SA-038 L2 note. The
  re-check before the review edits gave the same result (0 mismatches, same digests), and
  STATE and HANDOFF had not been touched by another session.

### Contract checked

| Card criterion | Verdict | Evidence |
|---|---|---|
| No stored date after the run date, for any event date; the rule chosen and recorded | **Met** | `find_qualifying_events` drops `item_date > today` before the cap (`event_ingestor.py:121`, cap at `:141-143`); `run()` passes `run_date` (`:234-235`); `merge_curator_output` stamps only `event["date"]` (`:253`). The receipt and card record "skip until it happens" with five reasons. The reviewer upholds the choice (see Decisions). |
| Past and same-day events unchanged; watermark key unchanged | **Met** | The lower bound and the key `f"{date_iso}\|{desc[:60]}"` (`:130`) are untouched; the table test pins 2, 1 and 0 days back and the lookback edge. |
| Existing future rows handled at read time, no migration; covers Recent observations and Open guidance | **Met for the digest** | `dossier.py:119`, `:134-135`; stored rows unchanged (test, and the reviewer's trace). One reader outside the digest does not apply the rule: **L1** below. The card scopes this criterion to the digest. |
| Daily curator and research loop unchanged | **Met** | Neither file is in the diff. The curator stamps `entry.date`, the graded trading day (`dossier_curator.py:219-221`); the research loop stamps `date.today()` (`question_researcher.py:182`, `:319`). |
| Deterministic tests, blocked transports, an independent date table, a pinned-clock digest test | **Met** | `_rule` is a separate statement of the card's rule, and the hand-written table is checked against it. The digest sweep derives its expected rows from the fixture, not from `to_digest`. NSE, Tavily and the LLM are fakes; the boundary refuses any real call. |

**Every writer of a dossier date** (the card's hard-review list), checked by code:

| Writer | Stamps | Can it date a row after its run? |
|---|---|---|
| Event ingestion → `merge_curator_output(today=event["date"])` | the event's date: observations, guidance, signature `first_seen`/`last_seen`/`evidence_dates`, `thesis_since`, `raised_on`, `resolved_on` | No: only events dated on or before `run_date` get there |
| `DossierCurator._merge` (daily review) | `entry.date`, the graded day | No |
| `QuestionResearcher` (`_apply`, `expire_stale_questions`) | `date.today()`, plus `last_attempt` | No |
| `distill_dossier` (weekly) | `date.today()` for new signatures and resolved questions | No |
| `PredictionStore.save_dossier` | `last_updated = date.today()` | No |

**Every caller of `to_digest`** passes no date, so each reads "as of today":
`dossier_curator.py:199` (the daily curator's prompt), `bundle_builder.py:532` (the context
bundle), `base_agent.py:501` (the agents), `ui_data.py:2659` (the chat tool `get_ticker_dossier`)
and `run_schedule.py:524` (a CLI length count).

### Independent adversarial examples

The reviewer's own trace (`analysis_data/fix004/review/test_rv_trace.py`, ignored; run under the
suite's hermetic hooks). The NSE items are shaped like production's: `bm_date`, `bm_desc`,
`bm_purpose` and `bm_timestamp` for meetings, `an_dt` for announcements, and empty key mappings,
so the registry's own candidate chain resolves them. The local registry maps every ticker's
board-meeting date to `bm_date` (47 of 47), the meeting day, so the trace models the measured
case. The event prompt template, the store and the merge are all real.

1. **One board meeting, from scan to every consumer.** A meeting on Sat 24 Oct, intimated 6 Oct,
   and an investor presentation dated 8 Oct:
   - Scan of 10 Oct: one LLM call, for the 8 Oct announcement. Its rows are dated 8 Oct, and only
     its key is watermarked.
   - Scan of 17 Oct: no LLM call, nothing saved.
   - Scan of 24 Oct: the meeting is digested. The prompt says `EVENT DATE: 2026-10-24`, and its
     rows are dated 24 Oct.
   - Scan of 31 Oct: the meeting is still in the 8-day window but watermarked, so it is not
     digested again.
   - After every scan, no stored date is after the scan date.
   - **Readers on 23 Oct,** shown a dossier that holds a 24 Oct row, as a pre-fix dossier does:
     the agents' digest, the context bundle, the chat tool and the daily curator's prompt all list
     the 8 Oct rows and no 24 Oct row. On 24 Oct they list it.
   - **The morning brief on 23 Oct** gives the earnings-watch line `"guide from 2026-10-24"`.
     That is **L1**.
2. **Old rows on their own day (the receipt's L1).** A pre-fix dossier holds three observations
   dated 24 Oct and the meeting's key. The 24 Oct scan makes no LLM call, so the old meeting is not
   digested again.
3. **A sweep.** Scans from 3 Oct to 30 Nov, daily or weekly, over 10 meetings and 12
   announcements. The feed always lists the whole schedule, future and past. Every event in reach
   was digested exactly once, under its own date, and never before that date. No stored date was
   ever after the scan date. Both cadences passed.

### Tests

- **Focused** (the receipt's command): 80 passed.
- **Do the tests fail on the original defect?** Yes. The reviewer's plugin
  (`analysis_data/fix004/review/rv_swap_plugin.py`) loads the code under test into memory, so no
  reviewed file is touched. It runs the same 3 files:

| Code under test | Result |
|---|---|
| Control (the reviewed code) | 80 passed |
| Both files at `5ea49fe` | 52 failed (the receipt says 52) |
| Event ingestion at `5ea49fe` | 4 failed (receipt: 4) |
| Digest at `5ea49fe` | 51 failed (receipt: 51) |
| O1: the newest 5 observations taken before the date filter | 30 failed |
| E1: the event date filter applied after the 3-event cap | 1 failed (the cap test) |
| G1: the last 5 open guidance taken before the date filter | **passes**: I1 |
| E2: `run()` drops `today=` (the scan reads its own clock) | passes; the same in production (one clock) |
| D1: the date compared as a whole string, not `[:10]` | passes; the same in production (no writer stores a time) |
| D2: undated rows also hidden | passes; the same in production (both fields are required, and every writer sets them) |

- **Mocked boundaries:** `prefetch_nse_data`, `_build_bundle` (Tavily) and `_call_llm` are
  replaced in every ingestion test. The hermetic boundary would fail any test that reached a real
  transport.
- **Full suite:** see "Commands and results".

### Findings

| ID | Severity | Location | Finding | Disposition |
|---|---|---|---|---|
| L1 | Low (confirmed by the reviewer's trace) | `core/delivery/brief.py:346-362` (`_earnings_watch`, `open_g[-1]`) | The morning brief's "Earnings within 3 sessions" section adds a dossier watch line: the newest open guidance item, with **no date check**. **Trigger:** a held stock with results within 3 sessions whose newest open guidance is dated after the brief's date. **Observed:** on 23 Oct a dossier holding open guidance dated 24 Oct gives `watch: "guide from 2026-10-24"`. **Expected,** by the card's intent: no row dated after the reading day is shown as known. **Impact:** after FIX-004 no writer can create such a row, so only stored rows qualify. By the 7 Oct probe that is one row: STARHEALTH's guidance item dated 27 Oct. It reaches a brief only if STARHEALTH is held (not read: private data) and only in the briefs where its 27 Oct meeting is within 3 sessions, about 22–26 Oct. The line is LLM text written under the "just happened" prompt, shown without its date. The criterion's own scope is the digest, so it is met. The receipt's list of writers and digest callers did not include this raw reader. | **Follow-up: FIX-004 change 1** (STATE, card). Apply the digest's rule in `_earnings_watch`, with its own test, in its own implementation and fresh-review phases. Worth doing before about 22 Oct; after 27 Oct it is only a guard. The reviewer's choice is to take it next; the owner can drop it. |
| I1 | Info (test gap) | `tests/unit/intelligence/rl/test_dossier_dates_fix004.py` (`_idfc_like` has 2 guidance items) | Variant G1 survives: no test has more than 5 open guidance items, so "filter, then take the last 5" is not pinned. The code does it in the right order (`dossier.py:119`). | Add a case with 6 or more open items to change 1's tests. |
| I2 | Info (equivalent variants) | — | E2, D1 and D2 survive, but in production they behave the same as the reviewed code. | No action. |
| I3 | Info (older, not FIX-004's) | `event_ingestor.py:66` (`_dp.parse(..., dayfirst=True)`) | `dayfirst=True` swaps the month and day of ISO dates: `"2026-10-08 17:10:00"` parses as 10 Aug, and `"2026-09-11"` as 9 Nov. Production is not affected: its mappings resolve `an_dt` and `bm_date` (the local registry: 47 of 47 each), which use the `08-Oct-2026` format. If a mapping ever fell back to `sort_date`, dates would be wrong. With FIX-004, a swap that lands in the future is now skipped instead of stored. | No action; recorded. |
| I4 | Info (other raw readers) | `dossier_curator.py:242-243`; `run_schedule.py:383-387` | Weekly `distill_dossier` sends the whole stored dossier, old future rows included, to its LLM. The operator CLI `dossier` prints open guidance without the rule. Both affect only rows stored before the fix, which already lose their future status on 24 and 27 Oct. The SA-046 card already says raw readers need the rule. | No action. |

The receipt's own self-review findings (L1–L3, I1–I3) are upheld as written.

### Decisions

- **"Skip until it happens" is upheld** over "date it the day it was learned".
  - The prompt says the event "just happened", so digesting a meeting not yet held asks the model
    for its outcome.
  - The agents that need upcoming meetings get them, with their official dates, from the live NSE
    feed. `format_nse_context` gives them to the fundamentals, valuation/catalyst and BFSI
    fundamentals agents (`nse_announcements.py:366`; `bundle_builder.py:383`, `:508`;
    `builder.py:137`, `:348`, `:375`).
  - The sweep shows every meeting in reach is digested once, on or after its date. The cost is the
    receipt's L2: one missed weekly scan can lose a meeting dated early in the week, because the
    lookback is 8 days. Before the fix, it would have been digested ahead of time, under a false
    date.
- **"Leave the row out" is upheld** for the digest. Stored rows are untouched, as the card requires.
- **L1 is a follow-up, not a reason to send the story back.** It is outside the card's criterion,
  bounded to one stored row and a few days, and conditional on a holding. Holding the fix back
  would let more weekly scans on the old code write new future rows.

### Commands and results

- Environment: Windows 11, `.stockai` venv (Python 3.13), with SA-005's hermetic boundary active.
- `python analysis_data/fix004/review/rv_verify.py`: 0 mismatches, `2f4cf482…`, `5550aab9…`
  (36,266 bytes), at the start and again before the review edits.
- `python -m pytest -q -p no:cacheprovider tests/unit/intelligence/rl/test_dossier_dates_fix004.py
  tests/unit/intelligence/rl/test_event_ingestor.py tests/unit/intelligence/rl/test_dossier_schema.py`:
  80 passed.
- The same, with `-p rv_swap_plugin` and `RV_MODE` set to each row: the table above.
- `PYTHONPATH="<repo>;<repo>/src" python -m pytest -q -s --rootdir analysis_data/fix004/review
  analysis_data/fix004/review/test_rv_trace.py`: 4 passed.
- `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count tests`: **4214 passed,
  12 skipped, 0 failed** in 6 min 10 s (the receipt's count). A fingerprint of `data/`, `logs/`
  and `outputs/` (the reviewer's own `rv_tree.py`: 798 files, `dec323a4…`) is the same before
  and after.
- `PYTHONPATH=analysis_data/kt_docs_deps python scripts/docs/check_kt_docs.py`: errors `[]` on the
  reviewed KT (source `ae47071f…`, which the PDF matches, 448 local links). After the review edits:
  errors `[]` (PDF rebuilt, source `2dcad25f…`, 448 local links, 35 pages).
- **Not exercised:**
  - production: no deploy is authorised; the after-deploy count probe and digest sample are the
    owner's;
  - a real NSE board-meetings response: the `items[:5]` question of the receipt's L2 stays
    unmeasured;
  - the container's time zone (the receipt's I3);
  - the morning brief end to end: only `_earnings_watch` was called.

### Review edits (documentation only)

- KT §5: FIX-004's status (accepted, not yet deployed) and one sentence on L1. The PDF is
  rebuilt (source `2dcad25f…`).
- Guide case 04-H: the status line.
- Cards: [FIX-004](../stories/FIX-004.md) gains "Fresh review (2026-10-10)", which defines
  change 1. [SA-046](../stories/SA-046.md): the status, and the brief named as a raw reader.
- STATE, HANDOFF and this receipt.
- No code or test byte changed. `kt_manifest.py verify FIX-004-manifest.json` now mismatches
  exactly the KT, the PDF, the guide, the FIX-004 card and the SA-046 card (checked; the other 6 paths, all code and tests among them, still match; PDF blob `994af607`).

### Acceptance and what remains

- **Verdict: ACCEPTED** for review input `2f4cf482…` (diff `5550aab9…`), worktree on `5ea49fe`
  (uncommitted), plus the documentation-only review edits above.
- **Production verification: `pending_deployment`.** After an authorised deploy (read-only, by the
  owner):
  1. Rerun the count probe after the first weekly scan on the new code. No row may be dated after
     its scan date. The 7 Oct baseline is 3 observations, 1 guidance item and 4 keys. The 10 Oct
     10:00 IST scan ran on the old code and may have added more.
  2. Sample IDFCFIRSTB's digest before 24 Oct: no 24 Oct row under "Recent observations".
- **Next, at the owner's word:** commit FIX-004 together with the 7 Oct probe-phase bookkeeping,
  bump the KT, and push in a job-free window. Then **FIX-004 change 1** (L1), in its own
  conversation, then its own fresh review.

## Change 1 fresh-session review: ACCEPTED (2026-10-10)

- **What was reviewed:** FIX-004 change 1, the morning brief's earnings watch, as committed in
  **`61c85d6`** ([implementation receipt](FIX-004-implementation.md), section "Change 1"):
  - `TickerDossier.open_guidance(as_of)` (`dossier.py:89-96`); the digest lists
    `open_guidance(as_of)[-5:]` (`:128`);
  - `_earnings_watch(symbol, on)` takes the last item of `open_guidance(on - 1 day)`
    (`brief.py:346-367`), and `build_morning_brief` passes the brief's date (`:771`);
  - the new `test_brief_earnings_watch_fix004.py` (51), 2 tests added to
    `test_dossier_dates_fix004.py`, 2 adapted in `test_delivery_brief.py`; KT §5 and the PDF,
    RL_DESIGN §23.1, guide case 04-H, and the FIX-004 and SA-046 cards.
- **Context:** a fresh-session review in a new conversation opened with "continue", 10 Oct 2026,
  from about 20:14 IST. It is not the conversation that implemented change 1, and it did not
  read that chat.
  - It reviews committed bytes. At the owner's word, change 1 was committed and pushed before
    this review (a recorded deviation from REVIEW.md's order). The owner reported the deploy
    and `/health` good at about 20:10 IST.
  - One StockAgent peer session (`stockagent-main-e5`) was busy throughout. It was rewriting the
    living docs in the worktree (the KT, ARCHITECTURE, the PDF, RL_DESIGN and others;
    uncommitted, owner-requested). The review input is the commit, so the rewrite does not
    touch it. This review edited none of the peer's files (see "Review edits").
- **Nothing** was committed, pushed, deployed or configured. No production state was read.
  SA-005's hermetic boundary was active in every test run.

### Review input verified

- The reviewer's own script (`analysis_data/fix004/review_change1/rc_verify.py`, ignored), not
  the implementer's `diff_digest.py`, checked the input:
  - the manifest as committed at `61c85d6` has the LF SHA-256 **`146c7507…`**, as recorded;
  - all 11 paths match their git blob id at `61c85d6`, and the 10 text files also match their
    SHA-256 (the PDF by blob id; its body was read separately, below): **0 mismatches**;
  - the diff `0ebd29b..61c85d6` over the 10 text paths, sorted, is 28,835 bytes, **`2ebe6299…`**,
    as recorded. The commit-to-commit form gives the same bytes as the receipt's worktree
    recipe.
  - `kt_manifest.py verify … --rev 61c85d6` agrees: 0 mismatches.
- **Drift.** At the start, the worktree differed from `61c85d6` on the manifest's paths in exactly
  the KT, the PDF and the guide: the KT bump `47d49c9`, as recorded. Code and test bytes in the
  worktree equal the commit. The peer's later rewrite of the KT and PDF adds to that drift only.
  The re-check at the end gave the same code and test result.

### Contract checked

| Change 1 scope | Verdict | Evidence |
|---|---|---|
| `_earnings_watch` applies the digest's date rule | **Met**, with a stricter cutoff (C1, upheld) | `brief.py:360`, through `dossier.py:96` |
| A future-dated item is never the watch line | **Met** | The 8-date table, the L1 reproduction, the 36-date sweep, end to end on 26 and 27 Oct (text and HTML), and the reviewer's trace (below) |
| A digest with 6 or more open items filters, then takes the last 5 (review I1) | **Met** | `test_digest_takes_the_newest_five_known_guidance_items`. The digest's expression is the old one, moved. The reviewer's D1 (the oldest five) is caught. |
| Docs: KT §5, and a guide case for the brief | **Met** | KT §5 at `61c85d6` and at the bump `47d49c9`, guide 04-H, RL_DESIGN §23.1, the cards |

**Every writer of a guidance date**, checked by code at `61c85d6`:

| Writer | When | Date it stamps | Can a row dated the brief's day exist at 08:50? |
|---|---|---|---|
| `DossierCurator._merge` → `merge_curator_output` | daily review, `FEEDBACK_CRON` 16:30 Mon–Fri | `entry.date` = the review date (`daily_review.py:119`, `:1582`; `dossier_curator.py:219`) | No: it is written at 16:30 that day |
| `EventIngestor.run` → `merge_curator_output` | Sat 10:00 (`scheduler.py:297-310`) | the event's date, never after the run (`event_ingestor.py:121`, `:235`, `:253`) | No on a weekday. Monday's brief (as of Sunday) counts rows dated Saturday. |
| `QuestionResearcher` | Sat 11:00 | none: it passes no `guidance_updates` (`question_researcher.py:315-319`) | n/a |
| `distill_dossier` | weekly | none: only sets `withdrawn` (`dossier_curator.py:271-274`) | n/a |

**Consumers.** `brief["earnings_soon"][i]["watch"]` goes to `save_brief`, which
`/delivery/brief/latest` and the chat tool read back (`ui_data.py:2695`), and to
`render_brief_text` and `render_brief_html`, which go to `deliver`. `_earnings_watch` has no
other caller. `open_guidance` has two: the brief and `to_digest`.

### Decisions

- **C1 (before the brief's date, not on or before): upheld.**
  - The window includes the meeting day: `next_results_event` keeps `ev_date >= on`
    (`corporate_events.py:153`), and the brief keeps events at most 3 calendar days away
    (`brief.py:512`). So the scope's literal rule would still show the pre-FIX-004 row on the
    meeting's morning. The reviewer's R7 mutant (on or before) fails 7 of the implementer's
    tests and 3 of the 4 trace tests.
  - No weekday writer runs before 08:50, so "before" loses nothing at the scheduled time.
  - Cost (self-review L1, confirmed by code): a brief triggered by hand after the 16:30 review
    leaves out that day's new guidance until the next brief. It never shows a wrong line.
  - A benefit the receipt does not claim: a replay (`run-brief?on=<past date>`,
    `delivery_api.py:60-73`) no longer shows guidance dated after its brief (trace 3).
- **C2 (one rule, in one place): upheld.** The digest's behaviour is unchanged. The old
  expression was `[g … if open and _known(g.date)][-5:]`, where `_known` is `d[:10] <= as_of`,
  which is exactly `open_guidance(as_of)[-5:]`.
- **C3 (the latest stored, not the latest dated): upheld.** Guidance is append-only:
  `merge_curator_output` appends and trims to the last 20, and status edits are in place. So
  the latest stored is the latest learned. The reviewer's R5 (latest by date) is caught by
  `test_latest_stored_wins_over_latest_dated`.

### Independent adversarial examples

The reviewer's own trace (`analysis_data/fix004/review_change1/test_rc_trace.py`, ignored; run
under the suite's hermetic hooks). It runs in production order through:
- the real `run_morning_brief`: the trading-day check, the saved brief, text and HTML, with the
  delivery call captured;
- a real `PredictionStore` under `tmp_path`;
- the real writer, `merge_curator_output`.

Results are on Tue 27 Oct. Tue 20 Oct is an NSE holiday. The expected lines were written by
hand from "what had the system learned by 08:50 that morning".

1. **Writers between briefs.** The store holds a 15 Sep item and a pre-FIX-004 row dated 27 Oct.
   - 19, 21 and 23 Oct: no earnings line. 23 Oct is 4 days out.
   - The Sat 24 Oct scan writes a row dated 24 Oct. The Mon 26 brief shows it.
   - The Mon 16:30 curator writes a row dated 26 Oct. The Tue 27 brief shows it.
   - 28 Oct: no window.
   - The 27 Oct row is in no delivered text, HTML or saved brief.
2. **Two pre-FIX-004 rows inside the window** (dated 26 and 27 Oct), no writers.
   - Mon 26: the 15 Sep item. The 26 Oct row is dated the brief's own day.
   - Tue 27: the 26 Oct row, dated the day before, and never the 27 Oct row.
   - A row written before its date shows once that date has passed. That is FIX-004's accepted
     behaviour: no migration is authorised.
3. **Replay.** A `run-brief` for 26 Oct, after rows dated 26 and 27 Oct exist, shows the 15 Sep item.

All 4 tests pass on `61c85d6`. The baseline `0ebd29b` fails 3 of the 4.

### Reviewer mutations (in memory; repo files never written)

`rc_swap_plugin.py` loads the baseline source, or a mutant of the reviewed source, into
`sys.modules` before collection. Columns: the implementer's 3 files (172 tests), and the
reviewer's trace (4).

| Mode | What it does | Implementer tests | Trace |
|---|---|---|---|
| reviewed `61c85d6` | — | 172 passed | 4 passed |
| base `0ebd29b` | the old brief and dossier | 53 failed | 3 failed |
| R0 | no date check, new signature (the original defect) | 38 failed | 3 failed |
| R1 | cutoff two days back | 5 failed | 2 failed |
| R2 | cutoff anchored to the results date, not the brief's | **0 failed** | 2 failed |
| R3 | cutoff = the previous trading session | 1 failed | 1 failed |
| R4 | the oldest known item | 43 failed | 2 failed |
| R5 | the latest dated item (a sort) | 1 failed | 0 failed |
| R6 | status ignored in the brief | 2 failed | 0 failed |
| R7 | the scope's literal "on or before" | 7 failed | 3 failed |
| D1 | digest: the oldest five known items | 1 failed | 0 failed |
| D2 | `open_guidance` compares the whole string (no `[:10]`) | 0 failed | 0 failed |
| D3 | `open_guidance()` with no date: no filter | 1 failed | 0 failed |

Every mutant that changes production behaviour is caught by one of the two sets. D2 is
equivalent today: every writer stamps a plain `isoformat()` date.

### Findings

None is critical, high or medium.

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | low, product decision | `brief.py:360` | Self-review L1, confirmed by code. A brief triggered by hand after the 16:30 review omits that day's new guidance until the next brief. It shows the previous item or the generic line, never a wrong one. | Accepted with C1. No follow-up. |
| I1 | info, tests | `tests/unit/test_brief_earnings_watch_fix004.py:153-196` | R2 passes all 172 implementer tests. The end-to-end fixture has no row dated the brief's own day inside the window, so a caller passing the results date instead of the brief's date goes unseen. The code is correct, and trace 2 catches R2. | Routed to the [SA-031](../stories/SA-031.md) card: add trace 2's 26 Oct row to the end-to-end fixture. |
| I2 | info, receipt | implementation receipt, "Change 1", "Why (code)" | It names three guidance writers, the research loop among them. The research loop writes no guidance. The conclusion holds: it lists more writers than exist. | Recorded here. No action. |
| I3 | info, scope | replay of a past brief | The rule uses the stored date. For an event row that is the event's date, not the day it was learned (FIX-004 L3, routed to SA-013). Status changes are not versioned. So a replay can count a row ingested after its brief but dated before it. The scheduled brief is unaffected. | Already routed (SA-013). No new action. |

### Commands and results

- Environment: Windows 11, `.stockai` venv (Python 3.13), with SA-005's hermetic boundary active.
- `python analysis_data/fix004/review_change1/rc_verify.py 61c85d6`: 0 mismatches, `146c7507…`,
  `2ebe6299…` (28,835 bytes); the same at the end.
- `python -m pytest -q -p no:cacheprovider` on the 3 change-1 test files plus
  `test_dossier_curator.py`, `test_event_ingestor.py` and `test_event_ingest_job.py`: **204 passed**.
- `python analysis_data/fix004/review_change1/run_rc_mutants.py`: the mutation table above.
- `PYTHONPATH="<repo>;<repo>/src;<review dir>" python -m pytest --rootdir <review dir> -p rc_swap_plugin
  <review dir>/test_rc_trace.py`: 4 passed.
- `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count tests`: **4267 passed, 12 skipped, 0 failed** in 9 min 03 s (the receipt's count), on a worktree whose code and test bytes equal `61c85d6`. A fingerprint of `data/`, `logs/` and `outputs/` (the reviewer's own `rc_tree.py`: 798 files, `dec323a4…`) is the same before and after.
- **The PDF against its source, at each commit.** The worktree's KT and PDF hold the peer's
  rewrite, so `check_kt_docs` on the worktree would check that rewrite instead. The reviewer's
  `rc_pdf_pair.py` reads each committed pair (`git show REV:…`) and runs `check_kt_docs`'s PDF
  test on it:
  - `61c85d6`: PDF blob `1d43620c`, KT source `6b1e4b5e…` printed in the PDF, 35 pages, no
    chapter missing;
  - `47d49c9`: PDF blob `f9e34256`, source `1fde0ed9…`, 35 pages, no chapter missing.
- `PYTHONPATH=analysis_data/kt_docs_deps python scripts/docs/check_kt_docs.py`, after the review
  edits, on the worktree: errors `[]`. That run checks the peer's KT, source `96fcf08a…`, and
  this review's guide and card links.
- **Not exercised:**
  - production. Whether STARHEALTH is held on 26–27 Oct is the owner's read-only check;
  - a real delivery (the delivery call was captured);
  - the 08:50 job itself (code only);
  - the container time zone (code: 08:50 IST is the same calendar date in UTC).

### Review edits (documentation only)

- Guide case 04-H: the status line ("accepted 2026-10-10, committed as `61c85d6`").
- Cards: [FIX-004](../stories/FIX-004.md) "Change 1" (accepted). [SA-046](../stories/SA-046.md):
  the status. [SA-031](../stories/SA-031.md): I1, routed.
- STATE, HANDOFF and this receipt.
- **Not edited: the KT, the PDF and RL_DESIGN.** The peer session told this review, by message,
  what it changed: an owner-requested restructure of the living docs, uncommitted and docs only.
  - It rewrote the KT as a design document, with the header still at `61c85d6`. The body no
    longer carries commit, review or deploy status. Change 1's rule is in §5 with no status
    wording, so the KT needs no edit for this verdict.
  - It removed only the FIX-004 story tags from RL_DESIGN §23.1, leaving the rule's text
    unchanged.
  - It did not touch STATE, HANDOFF, the guide, or any evidence or story file.

  So `verify FIX-004-change1-manifest.json` on the worktree now also mismatches RL_DESIGN, and
  the guide after this edit. `--rev 61c85d6` is unaffected.
- No code or test byte changed.

### Acceptance and what remains

- **Verdict: ACCEPTED** for `61c85d6` (review input `146c7507…`, diff `2ebe6299…`), plus the
  documentation-only review edits above.
- **Production verification: `pending_observation`.** It is deployed (the owner's report, about
  20:10 IST 10 Oct; deployment id not recorded). Read-only, by the owner, and only if
  STARHEALTH is held on Mon 26 or Tue 27 Oct: that morning's brief has no watch line from the
  27 Oct row. If it is not held, the change is a guard with nothing to observe.
- **Next:** FIX-004's own production check: the count probe after the 17 Oct 10:00 IST scan, and
  IDFCFIRSTB's digest before 24 Oct. Also SA-038's Sunday 11 Oct heartbeat. Then the normal
  queue resumes in STATE order, which is not started in this conversation.
