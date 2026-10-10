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
