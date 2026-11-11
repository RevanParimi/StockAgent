# FIX-027 — fresh review receipt

**Story:** [FIX-027](../stories/FIX-027.md): a decision booked at a session's close reads nothing from
after that close.

**Context.** This is a **fresh-session review** on 10 Nov 2026, about 21:15 to 22:00 IST. Session
`stockagent-main-77` [fd76db] was a new conversation, opened with "continue" on the laptop.

- `origin/main` was `02f3ad7`, the same as local `main`, so nothing had arrived from the other
  device.
- Peers `-17`, `-22` and `-09` were idle.
- Nothing was committed, pushed, deployed or configured. No production state or log was read, and
  no LLM or network was called.

**Verdict: ACCEPTED** for the reviewed revision. Two pre-existing medium findings, the answers to
the card's hard-review questions, are routed to the new [FIX-031](../stories/FIX-031.md).

## Input verified

- **Reviewed revision:** code `794968e`. This is `c94dc17`, FIX-026 with FIX-027, plus the
  review-fixes commit. HEAD `02f3ad7` holds byte-identical blobs for all 9 FIX-027 files, and so
  does the working tree. Production runs `794968e` (KT section 1), so the reviewed code is the
  deployed code.
- **Diff:** `git diff 412645f..794968e` over the 9 files is 38,229 B, sha256 `2c7c32e639408255…`.
  The `git ls-tree 794968e` listing of the 9 files hashes to sha256 `65a6f8c860fc3562…`.
  - Files: advisor.py, narrator.py, generate_forecast.py, prediction_store.py, verdict_store.py,
    schemas/feedback.py, schemas/portfolio.py, test_envelope_after_close_fix027.py and
    test_reforecast.py.
  - None of the 9 is in FIX-026-manifest.json, so the diff is FIX-027's alone.
- **Recipe:** `git diff 412645f..794968e -- <9 files> > review_input.diff`, then `sha256sum`. The
  output is in `analysis_data/fix027_review/` (ignored); recompute it on another device.
- **Docs:** the FIX-027 parts of `4d98c76` (KT section 6, RL_DESIGN 27.2, CODEBASE, AUTOPILOT_GUIDE,
  guide 06-N, PDF).
- **No drift:** `git diff 794968e HEAD -- core services src tests config` is empty.

## Contract checked

The one rule is that a re-forecast whose `at` is at or after session D's 15:30 IST close does not
set what a decision at D reads. The clock is the same as `close_before_decision`.

- **Direction:** the decision reads the envelope archived before the first such re-forecast. If
  that archive cannot be read, it reads no path at all (FLAT).
- **Old events** (no `at`) count as made before.
- **Anchor:** the review's re-forecast anchors on D's own close, and is skipped when D's bar is not
  fresh.
- **ADD:** an ADD only the later path allows is held, with the note `ENVELOPE_AFTER_CLOSE`.
- **Sales wait.** This was the owner's choice.

**Traced from input to the persisted result and its consumers**, by reading the code:

1. `regenerate_envelope` archives, analyses, anchors through `_review_session_close`, appends the
   event with `at=now_ist()`, and saves.
2. The daily review saves the streak onto the new envelope and skips Step 7b.
3. `pipeline.py` calls `build_signals(…, review_date=D, close=D's close)`.
4. `envelope_at_close` runs, then `decide`.
5. The `AdviceRecord` gets `envelope_after_close`; the narrator has its fixed text.
6. The shadow row and the autopilot read the record. Both exit rules read the same
   `envelope_direction`.

- **Retries:** a retried 16:30 pipeline for D now reads the same archive, so the decision no
  longer changes when a re-forecast lands between attempts.
- **The price history behind the stops and the trailing peak is not a leak:**
  `get_price_history` passes `end=date.today()` to `yf.download`, whose end date is exclusive. In
  the 16:30 run on T, the frame therefore ends at D.

**Independent adversarial example (RV1, through the real `regenerate_envelope` twice).**

- Monday closes at ₹1,000.
- At 08:45 on Tuesday the pre-open check re-forecasts: review date Tuesday, a +20% profile, path UP.
- At 16:45 on Tuesday the review of Monday re-forecasts: review date Monday, a −20% profile, path
  DOWN.
- The test snapshots the envelope file before each run. My expected reads, by the rule:
  - Monday's decision reads snapshot 0 (FLAT): both events are after Monday's close.
  - Tuesday's reads snapshot 1 (UP): 08:45 is before Tuesday's close, 16:45 is not.
  - Wednesday's reads the current file (DOWN).
- **Result:** the advisor's rows and directions equal the snapshots and my own drift rule in all
  three cases.
- **RV1b:** an `at` that cannot be read counts as after the close.

## Tests check what they claim

- **The original defect fails the tests.** The implementer's always-read-current mutant fails 29
  tests. Reviewer mutants m06 (build_signals reads the current envelope) and m09 (anchor on the
  latest close) are both caught.
- **The expected results are independent.** The invariant's `_oracle_end` walks the events by hand;
  the hand-worked examples (1,000, 1,100, 900) derive from the fixture.
- **Mocked boundaries:** the price fetch, the orchestrator, `now_ist` and the session close are
  stubbed. No real HTTP, LLM or SMTP is reachable (SA-005 hermetic).
- **Unrealistic fixtures (L2 below):**
  - The end-to-end test's +40% profile is refused by `ForecastProfile`, whose limit is ±20%. The
    log shows "PriceInterpolator failed … using static", so the path comes from the static
    fallback. The read rule it tests still holds.
  - The example tests use `reason="external_shock"`. The real writers store a sentence there (L1).

## Findings

| # | Severity | Where | Trigger → observed / expected | Disposition |
|---|---|---|---|---|
| F1 | Medium, pre-existing, confirmed (code + local) | `services/data/fetchers/news.py` `_recent_article_lines` (lower bound only); `daily_review.py` Step 7a; `advisor.py` `build_signals` thesis read; `decide` `thesis_break` | Path at Monday's close ends 970 (DOWN); Tuesday's 16:30 review of Monday reads a Tuesday article and says "not intact" (multiplier 0.75, no re-forecast) → **EXIT at Monday's ₹1,000** / expected: no sale at Monday's close on a Tuesday judgement. Same context drives Step 7b's confidence (TRIM inputs; trend moves little, not shown to change a TRIM). Reviewer cases `test_f1_*` (strict xfail). | [FIX-031](../stories/FIX-031.md) item 2 |
| F2 | Medium, pre-existing, confirmed (code + local) | `core/portfolio/exit_shadow.py` `recent_negative_events`, `latest_actionable_verdict` | NSE loss filed 18:10 IST Monday → **counts** for the shadow sale at Monday's close; an analysis at 20:00 IST Monday counts as Monday's verdict / expected: from Tuesday's close. Biases the exit-rule switch gate toward the evidence rule (F1 biases it the other way). `test_f2_*` (strict xfail; a 14:10 control passes). | FIX-031 item 3 |
| I-1 | Info | `core/discovery/candidates.py` `watchlist_idea` | The card's second hard-review question (FIX-024 I2): a later analysis vetoes an earlier close's offer. **Decided** (delegated): read the latest analysis made before the close. | FIX-031 item 4 |
| I-2 | Info, pre-existing | `generate_forecast.regenerate_envelope` | The review's re-forecast on T rewrites T's row (T already closed); the review of T grades it (direction accuracy gates ADD). Disclosed by the implementer; confirmed. | FIX-031 item 5 |
| L1 | Low | `advisor.envelope_at_close` (`why` uses `first.reason`) | The record reads "the External shock on 2026-…: actual direction … re-forecast of …" (the writers' sentence); the narrator shows fixed text, so it is not user-facing. | [FIX-015](../stories/FIX-015.md) (note added) |
| L2 | Low | tests/unit/test_envelope_after_close_fix027.py `_real_round_trip` | +40% profile refused; static path; docstring figure "about 1,040" not what runs. | FIX-031 item 6 |
| L3 | Low | `advisor.reforecasts_after_close` | No tracked test for an unreadable `at` (m02 survives) or a naive one (m08 survives); the writer never produces either. RV1b shows the code is right. | FIX-031 item 6 |

No finding in FIX-027's own change rises above low.

**The card's hard-review questions, answered:**

- `thesis_intact`: moves after the close (F1).
- The review's re-scoring: Step 7b confidence moves after the close (F1, TRIM; small).
- `next_results_event`: feeds only the note `EARNINGS_GAP_PROTECTION`, which nothing acts on.
- The case events PR-009's exit reads: by calendar day (F2).
- The latest-analysis list: I-1, decided.

**Transition (by the card's rule, not a finding).** Events stored before the 13:20 deploy on 10 Nov
have no `at` and count as before. Only the 16:30 run of 10 Nov, deciding at 9 Nov's close, could
read an event made after that close: the review re-forecasts of 9 Nov 16:30 and the pre-open
re-forecast at 08:45 on 10 Nov. Not measured.

## Commands and results (laptop, `.stockai` venv, Python 3.13.11, Windows)

| Command | Result |
|---|---|
| `pytest -q -p no:cacheprovider` FIX-027 file, test_reforecast, test_reforecast_cli, test_preopen_check, test_portfolio_advisor, test_portfolio_advisor_switch, test_portfolio_narrator, test_broad_except_guard, shared/test_error_capture_context | **181 passed** (46 s) |
| `scripts/ci/check_broad_except.py` | OK (148 grandfathered) |
| `scripts/docs/check_kt_docs.py` | `errors: []`; PDF 68 pages, `source_sha256` `5f699918…` equals the KT's sha256 |
| `analysis_data/fix027_review/mutants.py` (detached worktree at `794968e`, tracked FIX-027 tests + test_reforecast) | **11 of 13 caught**; m02 and m08 survive (L3) |
| `pytest analysis_data/fix027_review/test_rv_fix027.py` | 4 passed, 4 strict xfail (F1 ×2, F2 ×2) |
| Full suite `pytest tests -q -p no:cacheprovider` (hermetic) | **6,257 passed, 12 skipped, 1 xfailed, 0 failed** (rc 0, 23m04s, 21:28-21:51 IST; git status unchanged; `analysis_data/fix027_review/full_suite.txt`) |

**Not exercised:**

- Production. The counts probe (story step 1) is still not run, at the owner's word. Guide 06-N's
  production line waits for the first run after a re-forecast.
- Real Serper news. F1's news half rests on reading the filter and on the offline reviewer case.
- A pipeline-to-ledger run of the autopilot.

## Acceptance checklist

- **RV13's shapes:** met. There are tracked hand-worked tests for ₹1,100 (no ADD), ₹900 (no EXIT,
  under Wait), the Friday re-forecast that still ADDs, and the 15:29/15:30 boundary.
- **Independent invariant, pre-open included:** met. The 40-seed oracle includes flipped
  post-close paths, and there is a pre-open case. RV1 adds a multi-session check with two real
  events.
- **Old envelopes parse:** met.
- **Docs:** met. The KT section 6 limit was replaced, the section 12 row and guide case 06-N exist,
  RL_DESIGN 27.2 was updated, and the PDF matches its source.
- **Step 1, measure first:** not run. The owner chose "proceed, run later", and the receipt and
  STATE record it.

## Commit-time edits (docs only, for the next docs commit at the owner's word)

1. **KT section 6**, at the end of "The envelope at the session's close", replace "Not covered:
   `thesis_intact`, the review's re-scoring and the case events the evidence rule reads may also
   reflect news after the reviewed close; this has not been checked." with:

   > Not covered: the thesis review the legacy rule sells on reads company news up to the run, so
   > it can rest on news after the reviewed close; the evidence rule counts filings and analyses by
   > the calendar day, so one published that evening counts for that close. **Planned:** FIX-031.

   Then regenerate the PDF.
2. **KT section 12:** add a FIX-031 row.
3. **Guide 06-N status line:** replace "review pending" with "accepted on 2026-11-10 (fresh
   review)".

## Decision

**ACCEPTED** for revision `794968e`.

- **STATE:** FIX-027 `done`. Production `pending_observation`: deployed on 10 Nov, first check
  guide 06-N's production line.
- **New:** FIX-031 `todo`, P1, 5 points, after FIX-030.
- **FIX-015's card** gains L1.
- `active_task` null; `next_task` FIX-028.
