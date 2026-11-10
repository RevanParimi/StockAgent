# SA-049 review receipt — put idle cash to work in normal markets

## Re-review of rework 1 (2 Nov 2026): accepted

- **Context:** a **fresh-session re-review**, in a new conversation opened with "continue" (2 Nov
  2026, about 13:40–14:25 IST, session stockagent-main-15 [59b0c2]). The implementation ran in
  stockagent-main-a1 [c4bf3b], the review in -2c [c85206] and rework 1 in -f6 [f075f4]; none of
  their chats was read. All 18 peer sessions were idle at the start and before bookkeeping.
- **Verdict: `accepted`** for the input below. H1 is fixed, and every lane that opens a position
  reads the bound. T1, L1, L2, T2, the FIX-023 docs and the guide's status lines are done as the
  review asked. One new low item (RR-L1) and one low test gap (RR-T1) go to FIX-023, which is
  already a precondition for switching deployment on.
- **Nothing was committed, pushed, deployed or configured. No production state or network was
  read.**

### Reviewed input

- **Base:** HEAD `f47d246`, with nothing staged.
- **Manifest:** [SA-049-manifest.json](SA-049-manifest.json) `64b81d4f…e7f1fa0`, 26 files.
  `kt_manifest.py verify` gives 0 mismatches.
- **Rework diff:** `1acfdc88…44508854`, 54,656 B, 25 paths, 9 changed. It is taken against the
  kept review input (`analysis_data/sa049_rework1/review_input/`), and each copy is first checked
  against [SA-049-manifest-review1.json](SA-049-manifest-review1.json) `55b642be`.
- **Cumulative diff:** `02707570…4adce09b`, 237,273 B, 25 paths, against the index.
- **Verified at the start (13:42 IST) and the end (14:11 IST):**
  `analysis_data/sa049_rereview1/rr_digest.py` runs the rework's recipe and writes into the
  re-review folder.

### What was checked

- **Where the bound lives.** `buy_candidates(portfolio, on, …)` refuses a shelf idea whose
  `last_dived` is after `on`. The pipeline's only call passes `review_date`
  (`pipeline.py:228`), and the 16:30 job passes `trading_days_ago(today, 1)`. So `on` is the
  session whose close the run books at.
- **Every lane that opens a position:**
  - **Shelf ideas, discovery and IPO.** Both write paths stamp `dived` with the run's day, in the
    same step as the band and the conviction: the add at `shelf.py:191-199`, the re-dive at
    `262-267`. IPO shelf ideas come from Saturday's discovery cycle (`build_ipo_candidates`).
    The Sunday 19:00 IPO deep dive writes only its own verdict store (dark), not the shelf. The
    discovery job runs Saturday 12:30 IST, so `date.today()` is Saturday in either timezone.
  - **Watchlist.** `watchlist_idea` keeps its `age < 0` rule, unchanged; RR2 drives it end to
    end.
  - **SWITCH.** `gated_decide` (both exit rules), `capture_switch_evaluations` and the
    executor's buy leg (`shelf_index`) all read the filtered list; RR2 drives it end to end
    through the real advisor.
  - **Deployment.** `_deploy_check` gets its ideas only from `shelf_index`; RR1 covers it.
  - **The shadow's switch test.** `switch_lands` reads `shelf_index` (`pipeline.py:302-305`).
  - **Not buy paths.** `all_ideas` feeds `EvidenceReader` (a holding's invalidation level), and
    `weekly.py` builds messages.
- **The boundary.** A dive dated the review session is offered (FRIX), as a watchlist analysis
  of that day is. The day is the unit of issue time, so a dive run after D's close but dated D
  can be bought at D's close. The scheduled dives fall on Saturday, when there is no session,
  so the common case is handled. Upheld as the receipt states it.
- **Docs.** KT sections 6, 7, 8, 11 and 12; AUTOPILOT_GUIDE sections 3, 7 and 16 and the route
  row; guide 07-G (the P4 case), 07-N and 07-O; CODEBASE and PRODUCT_MAP; the docstrings. No
  stale "at most one position" or deposit wording is left (grep). `results.py`'s "that day's
  close" is SA-051's sentence about the point's date. ARCHITECTURE and UI_SPEC do not describe
  candidates.
- **PDF:** 65 pages. The footer carries the KT's LF SHA-256 `ff6a386dad3e`, and all six of the
  rework's new sentences are in its text (`rr_pdf.py`).
- **Checks:** `check_broad_except` OK (149). `check_kt_docs` gives exactly one error, the
  expected header error: "KT links core/portfolio/deployment.py, which is absent at its declared
  revision 866eae5107b3". It counts 697 local links; the receipt's 694 is from before
  bookkeeping, and the implementer's own end check (`check_kt_docs_end.txt`) also has 697.

### Reviewer cases

`analysis_data/sa049_rereview1/test_rr_sa049.py`, **4 passed**. They drive the real pipeline,
`buy_candidates`, advisor, executor and regime state file. Every value is hand-derived in the
case. Fixture builders are borrowed from the story file and PR-004's file; none of their
assertions are.

| Case | What it shows |
|---|---|
| RR1 | **Deployment over two runs.** ₹12 L in cash, four ideas. Monday's run (review Fri 30 Oct) buys FRIX (dived Fri, 333 × ₹250) and OLDY (dived 3 Oct, 41 × ₹2,000), both dated 30 Oct. NEWX (first dived Sat) and OLDX (shelved 3 Oct, re-dived Sat) are left out, with the reason logged. Tuesday's run (review Mon 2 Nov) buys NEWX (83 × ₹1,000) and OLDX (166 × ₹500), dated 2 Nov. **Invariant**, from the case's own dive table: every BUY's date is on or after its idea's dive. |
| RR2 | **SWITCH end to end, deployment off.** ACMESOLAR breaks its stop. On Monday's run its only candidates are CAND (shelf, dived Sat) and W (a watchlist BUY analysed Sat 12:30 IST), so the advice is EXIT and nothing is bought. Adding FRIC (dived Fri) makes it a SWITCH into FRIC, bought dated 30 Oct. On Tuesday's run, the SWITCH goes into CAND, dated 2 Nov. |
| RR3 (record, enforce) | **The residual (RR-L1).** Tuesday's run reviews Monday, but NEWX has no Monday bar, so the close is Friday's. Record mode buys 83 × ₹1,000 dated 2 Nov at a close from before Saturday's dive; the note says "its close is from bar 2026-10-30, not the review session". Enforce withholds it. The case asserts the observed behaviour. |

**The previous review's cases.** With the story, PR-004 and FIX-011 files: **1 failed, 201
passed**. The one failure is RV1 at its observed-defect line: the buy list is now `[]`. This is
what the review asked for. RV2–RV8 and the RV1 control pass.

### Mutants

In memory (`rr_mutplug.py` with `run_mutants.sh`; results in `rr_mutants.txt`). Each is run
against the story file and the reviewer cases, and the failing tests are listed.

| Mutant | Story file | Reviewer cases |
|---|---|---|
| `bound_removed` (rework 1 undone) | caught: the three issue-time cases | caught: RR1, RR2 |
| `bound_reads_added` (the bound reads `added`, not the latest dive) | caught: `test_an_idea_dived_after_the_review_session_is_not_offered` (OLDX) | caught: RR1 (OLDX) |
| `bound_one_day_slack` (`dived > on + 1 day`) | caught: the three issue-time cases | caught: RR1, RR2 |
| `pipeline_passes_run_day` (the pipeline passes `date.today()`, the run's day) | caught: 4 tests, the two issue-time pipeline cases among them | caught: RR1, RR2 |
| `watchlist_no_lower_bound` (`age < 0` dropped; PR-004's rule) | **survives** (and PR-004's file with the SA-003 portfolio and pipeline files: 126 passed) | caught: RR2 → **RR-T1** |
| `buy_status_only_s` (FIX-011, T1) | caught: `test_any_status_but_active_in_the_report_refuses` | not exercised |
| `buy_older_cache_serves_first` (FIX-011, T1) | caught: `test_the_cached_report_serves_only_its_own_day` | not exercised |
| `buy_age_eight_days` (FIX-011, T1) | caught: `test_a_report_older_than_seven_days_opens_no_position` | not exercised |

`pipeline_passes_run_day` uses the real clock (2 Nov 2026), so its result holds for runs on or
after 31 Oct 2026.

The rework's own runs (11/11 in memory, 23/23 in place) were not repeated.

### Full suite

**6,023 passed / 12 skipped / 1 xfailed / 0 failed (16m56s, 13:54–14:11 IST)** with `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests` on
Windows 11 and Python 3.13 (output `analysis_data/sa049_rereview1/full_suite.txt`). It equals rework 1's count. `git status` was identical before and after (no tracked runtime file changed).

### Findings

| ID | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| RR-L1 | Low (confirmed: RR3; frequency unmeasured) | `core/portfolio/autopilot.py:441-452` (`_deploy_check`: a stale bar is withheld only when `dg.enforcing()`); `core/portfolio/pricing.py:51-70` with `daily_review._fetch_session_close` (the latest bar on or before the session); the SWITCH leg's SA-003 check (pre-existing) | **Trigger:** the review session's bar is missing at the 16:30 run, or the owner runs `POST /portfolio/run-advisor` with no date before the day's close. **Observed:** the close is carried forward from an earlier bar. In `record` mode (the checked-in mode) the buy goes ahead with a note, so an idea dived after that bar is bought at a price from before its dive. **Expected:** a buy that opens a position uses a close from a bar on or after the idea's latest dive, in either gate mode. | The bound on the dive holds. This is the price's date, which SA-003's record mode lets through by the owner's decision, and the buy's note names the bar. It needs a missing bar or a manual run before the close; the scheduled run reviews a session that has closed a day earlier. Deployment ships off; SWITCH legs share the path, and that part is pre-existing. | **Routed to [FIX-023](../stories/FIX-023.md)** (now 3 points), a precondition for the switch-on. Its section "Routed input — 2026-11-02 SA-049 re-review" holds the rule and the acceptance. Commit-time KT edit 1 below names the limit until then. |
| RR-T1 | Low (test gap; pre-existing PR-004) | `core/discovery/candidates.py:157-159` (`watchlist_idea`: `age < 0`) | Mutant `watchlist_no_lower_bound` survives the story file, PR-004's file and the SA-003 portfolio and pipeline files (`rr_mutant_watchlist_pr004.txt`: 126 passed). Only the ignored reviewer files (RV1's control, RR2) catch it. | A regression in the watchlist's issue-time bound would pass the tracked suite. | **Routed to FIX-023's routed section:** one case, a watchlist BUY analysed after the review session is not offered. |
| RR-I1 | Info | This receipt's input record | The implementation receipt names "an IPO idea dived on Sunday". No job writes a shelf idea on a Sunday: IPO ideas are dived in Saturday's discovery cycle. | None: the bound compares dates, whatever the day. | None. |

**Upheld:** H1's fix and its place (one list feeds every lane), the boundary (a dive on the
review session is offered), the re-dive-off case, T1's three routed tests (each catches its
FIX-011 mutant through the real reader), L1, L2, T2's three cases, the KT section 12 FIX-023 row
and section 6 sentence, the rollout's step-1 list, and the guide's status lines.

### Acceptance checklist (the review's open items)

| Item | Verdict |
|---|---|
| H1: one rule for every new-position buy; RV1's shape buys nothing on Monday and at Monday's close on Tuesday; a SWITCH destination of that kind is not offered; a mutant dropping the bound is caught | Met (story file, RR1, RR2, mutants) |
| T1: FIX-011's routed tests through the real reader | Met (each of the three mutants is caught by its own new case) |
| L1, L2: the review's sentences | Met (KT, docstrings, AUTOPILOT_GUIDE, guide 07-N) |
| KT section 12 FIX-023 row and section 6 sentence; rollout order | Met |
| T2 (recommended): three cases | Met (each mutant is caught) |
| Issue time (REVIEW.md: an independent invariant test) | Met for the dive (RR1's invariant). The price's bar is RR-L1, which FIX-023 resolves before the switch-on. |
| Everything else in the card's acceptance | Met at the review of 2 Nov; unchanged by the rework |

### Commit (only at the owner's word)

The code commit holds the 26 files of `64b81d4f`, exactly as reviewed. Then a docs commit with
the implementation's commit-time edits and these:

1. **KT section 6, "Which ideas"**: after "…Monday's run reviews Friday.", add: "Until FIX-023,
   record mode can still buy an idea at a close carried forward from before its dive, when the
   review session's bar is missing or a manual run comes before the close; the buy's note names
   the bar."
2. **KT section 12**: SA-049 `Done`. **KT header**: the new code commit (this clears
   `check_kt_docs`'s one expected error). **KT section 1**: the production paragraph, with FIX-011
   (`f47d246`) deployed at 00:14 IST on 2 Nov (session -e7's record).
3. **Guide status lines.** 07-G: "SA-049: accepted 2026-11-02; not deployed, and the switch ships
   off (turn it on only after FIX-023)." 07-N and 07-O: "SA-049: accepted 2026-11-02; not
   deployed."
4. **Rebuild the PDF**, then run `check_kt_docs`.

The docs commit also carries the receipts, both manifests, the FIX-023 card, the PI README, and
STATE and HANDOFF (with session -e7's uncommitted FIX-011 deploy record). A push deploys it;
do it in a job-free window, with the switch still off.

### Not exercised

- A real Saturday discovery run followed by Monday's and Tuesday's 16:30 runs.
- How often a review session's bar is missing at the 16:30 run (RR-L1's frequency). The
  `decision_gate.jsonl` records could answer it; they were not read.
- Production logs, shelf and regime state.

### Production verification

`not_started`; nothing is deployed. The rollout follows the implementation receipt's steps.
Before the switch-on: FIX-023 accepted (with RR-L1 and RR-T1), then the owner's deposit (guide
07-N). After the switch-on: guide 07-G, including the P4 case on the first Monday.

## Review (2 Nov 2026): changes requested

- **Context:** a **fresh-session review**, in a new conversation opened with "continue" (2 Nov
  2026, about 09:08–09:55 IST, session stockagent-main-2c [c85206]). The implementation ran in
  stockagent-main-a1 [c4bf3b]; its chat was not read. All 16 peer sessions were idle at the
  start and again before bookkeeping.
- **Verdict: `changes_requested`.** One high finding (H1, issue time) is unresolved. Everything
  else in the card's acceptance holds; see the checklist.
- **Nothing was committed, pushed, deployed or configured. No production state was read.**
  The only network reads were public: Yahoo's three regime tickers.

## Reviewed input

- **Base:** HEAD `f47d246` (FIX-011's docs commit on `866eae5`), with nothing staged.
- **Manifest:** [SA-049-manifest.json](SA-049-manifest.json) `55b642be…2ad38b57`, 26 files.
  `kt_manifest.py verify` gives 0 mismatches.
- **Diff:** `45a56c30…64114704`, 214,039 B over 25 paths.
- **Verified at the start (09:10 IST) and the end:**
  `analysis_data/sa049_review/rv_digest.py` runs the implementer's recipe (every manifest path
  except the PDF, against the index, new files against `/dev/null`) and writes into the review
  folder.

## Contract checked

- **Target** (`deployment.target`):
  - The day's sticky label maps to a share (80 / 50 / 0).
  - In a calm regime the target is at least `min_invested_inr`, and the holdings floor is
    `min_holdings`.
  - The target is capped at equity less the cash floor, with "invested floor unreachable"
    recorded.
  - No label recorded for the day, or no share set for the label, opens nothing.
- **When another position opens** (`stop_reason`):
  - Never at `max_holdings`, and never past the daily limit.
  - Otherwise, always below the holdings floor in force.
  - Above the floor, while invested is below the target, unless `target_holdings` are held and
    the regime's share is met.
- **Each candidate** (`_deploy_check`), from the day's `buy_candidates` by conviction:
  - Not held.
  - Not sold on or after its latest dive.
  - SA-003's gate: the dive's gate, a session-dated close and a resolved identity; withheld in
    `enforce`, noted in `record`.
  - NSE's report (`surveillance_issue`).
  - The entry band.
  - `size_buy` asking for `min_invested_inr / target_holdings`.
- **The step's safety:**
  - It runs on a deep copy of the portfolio and is kept only when it completes.
  - Each buy's ledger row and note are written; the run's record goes to the digest.
- **Routed fixes:**
  - SA-050 R1: whole shares in paisa.
  - SA-050 R2: the switch alert matched by `advice_ref`.
  - SA-051 R1: a late close fetch plus `at_cost`.
  - FIX-016: `deploys_cash`.
  - PR-004/FIX-011: the generic key read from the stored classification.
  - FIX-011: the buy-time surveillance check, on SWITCH legs too.
- **The deposit route:** owner or machine key; one dated `DEPOSIT` row; idempotent on
  (date, amount, reference); 409 without cash accounting.
- **Ledger readers of the new side:**
  - `costs_of` skips non-trades.
  - `reconcile` nets quantities only for BUY and SELL, and the cash chain covers the deposit.
  - `results` filters on BUY and SELL.
  - The UI renders the deposit's note as escaped JSX text.
- **How the run is timed (it decides two findings):**
  - The 16:30 job on day T reviews the previous session: `review_date =
    trading_days_ago(today, 1)` (`scheduler.py:771`).
  - It passes that date to the daily review and to the pipeline, so the regime's
    `_last_update` and the deployment's date agree.
  - Trades are booked at that session's close (`session_close(sym, review_date)`).

## Independent adversarial examples (reviewer cases)

`analysis_data/sa049_review/test_rv_sa049.py`, **15 passed**. The cases drive the real
executor, and where named the real pipeline, `buy_candidates`, regime state, regime detector,
deposit route and comparison. Every value is hand-derived in the case. Fixture builders are
borrowed from the story file; none of its assertions are.

| Case | What it shows |
|---|---|
| RV1 | **H1.** Monday 2 Nov's run reviews Fri 30 Oct (real NSE calendar). An idea first dived on Sat 31 Oct is still "fresh" for 30 Oct (age −1 ≤ 30). The real pipeline buys 83 at ₹1,000, dated 2026-10-30, verdict DEPLOY. Asserts the observed defect, so it should fail after rework 1. |
| RV1 control | The watchlist lane refuses the same timing: "latest analysis of 2026-10-31 is -1 days old (limit 30)". |
| RV2 | **M1.** The real detector with Yahoo answering VIX 30 and Nifty −3.0% gives MACRO_CRISIS, and nothing is bought. With `^INDIAVIX` empty, VIX 17.0 gives RISK_OFF: the real state file records it and the executor buys 2 × 83 to 43.8%. With both dark, NORMAL. Bound: a crisis already entered survives one dark day. |
| RV2b | **L3.** With Yahoo holding Monday's bar, `detect(as_of_date=30 Oct)` returns Monday's VIX 30 and MACRO_CRISIS. |
| RV3 | **L1.** NORMAL, ₹12 L, 9 holdings at 86.25%: below the floor, one more opens. Invested becomes ₹11,18,000 (93.2%), past the ₹10 L target by ₹1,18,000, more than one ₹83,333 position. This is decision T3 by design; the docs claim "at most one position". |
| RV4 | **L2.** A Monday-morning deposit is first held by the point dated Fri 30 Oct, which Monday's run writes. The Nifty units are bought at Friday's close (2,00,000 / 120), not Monday's. |
| RV5 | The real state file: a crisis recorded for the day buys nothing, and the EXIT still sells. A state written for the day before buys nothing. The sticky layer off writes no state, so nothing opens (fail closed). |
| RV6 | Two SWITCHes and deployment on one run. X and Y are bought by the legs and are "held" for deployment. Z1 and Z2 are deployed and Z3 waits: the limit counts deployment buys only (T5). Cash ₹12 L − ₹2 L − ₹1.66 L. |
| RV7 | A deposit, then a deploy run: the first BUY's `cash_before` is the deposit's `cash_after`, and `reconcile` is clean. |
| RV8 | Churn: deployed, EXITed the next session, then "sold" that day and on later sessions. It is bought back only after a newer dive (T4). |

## Other checks

- **Public reads**, about 09:10 IST.
  - **Yahoo:** `analysis_data/sa049_review/vix_probe.py` read `^INDIAVIX` (15.3), `^NSEI` and
    the 3-month `^NSEI`. Today the real detector gives RISK_ON with no fallback. So M1's path
    is not live today.
- **Aliases** (`alias_probe.py`, local files only):
  - Against NSE's real 30 Oct report (FIX-011's saved copy), 9 registry aliases are "not
    listed" under the app code and clear under the NSE code. Examples: TATAMOTORS → TMPV,
    ZOMATO → ETERNAL, TVSMOTORS → TVSMOTOR. GATI is delisted.
  - **Not a finding.** A candidate reaches the check only under NSE's code. Shelf ideas come
    from NSE's screen. A watchlist BUY must be in NSE's listing (`instrument_kind`) and in the
    bhavcopy window under that code, and the autopilot's own exits never qualify.
  - A future lane that offers app codes must resolve `nse_symbol` first.
- **PDF:** 65 pages. The footer carries the KT's LF SHA-256 `42058dc649fb`, and the new
  sections are in its text (`rv_pdf.py`).
- **`check_broad_except`:** OK (149).
- **`check_kt_docs`:** exactly one error, "KT links core/portfolio/deployment.py, which is
  absent at its declared revision 866eae5107b3". It is expected until the commit-time header
  bump.
- **Reviewer mutants** (in memory, `rv_mutplug.py` with `run_mutants.sh` and
  `run_mutants_routed.sh`; results in `rv_mutants.txt` and `rv_mutants_routed.txt`). Each
  targets a rule outside the implementer's 23:

  | Mutant | Story file | Reviewer cases |
  |---|---|---|
  | `floor_clause_dropped` (below the holdings floor with the target met, open nothing) | survives | caught (RV3) |
  | `deposit_key_without_amount` | survives | survives |
  | `sold_strictly_after_dive` (a sale on the dive's own day) | survives | survives |
  | `at_cost_never_written` | caught | survives |
  | `rebuy_misses_todays_sells` | caught | caught (RV8) |
  | `buy_status_only_s` (a status other than A or S passes) | survives | not run |
  | `buy_older_cache_serves_first` | survives | not run |
  | `buy_age_eight_days` | survives | not run |
- **Full suite:** **6,014 passed / 12 skipped / 1 xfailed / 0 failed** (21m55s, 09:29–09:51
  IST), with `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests` on Windows 11
  and Python 3.13. It equals the implementation's count. `git status` before and after differs
  only by this receipt and the FIX-023 card, written meanwhile. Output:
  `analysis_data/sa049_review/full_suite.txt`.
- **Reviewer cases:** `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider
  analysis_data/sa049_review/test_rv_sa049.py` (this folder's `conftest.py` imports the suite's
  hermetic hooks).

## Findings

| ID | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| H1 | **High** (confirmed: RV1) | `core/discovery/shelf.py:83-91` (`dive_is_fresh`: no lower bound), used by `core/discovery/candidates.py:210`; `core/portfolio/autopilot.py:417-455` (`_deploy_check` reads no dive date against the session). The watchlist lane has the bound (`candidates.py:152`). | **Trigger:** the Saturday discovery run (`on = date.today()`, `__init__.py:50`) stamps `dived` (and `added` for a new idea) with Saturday (`deep_dive.py:260`). Monday's 16:30 run reviews Friday. **Observed:** the idea is offered and bought at Friday's close, for an idea that did not exist then. A re-dived idea is the same. **Expected:** a buy booked at session D's close uses only an idea whose latest deep dive is on or before D. Monday's run leaves it out; Tuesday's run (reviewing Monday) buys it at Monday's close. | **Issue-time information** in the paper record, which SA-051's comparison and the weekly scorecard use to judge deployment (rollout steps 3 and 5). The date order is confirmed. What the dive knows is inference: it reads news up to Saturday, and results announced on Friday evening or Saturday are common in results season, so a buy at Friday's close then carries the Monday gap. It happens every week: Monday's run is the first after the dives, and new and re-dived ideas lead it by conviction. SWITCH legs share the path (PR-004's `buy_candidates`, pre-existing). SA-049 makes it the main way cash is invested, and the story file never draws a dive after the session. | **Rework 1, required.** Use one rule for every buy that opens a position: the dive must be on or before the review session (the watchlist's `age < 0` rule, applied to shelf ideas in `buy_candidates`). Then SWITCH legs, deployment and the shadow's switch test agree. Excluded reason, for example "deep dive of 2026-10-31 is after the review session 2026-10-30; offered from the next run". Tests: RV1's shape through the real pipeline buys nothing on Monday's run and 83 at Monday's close on Tuesday's run; a SWITCH destination of that kind is not offered; a mutant that drops the bound is caught. Docs: KT section 6 "Which ideas" and section 8's candidates paragraph, AUTOPILOT_GUIDE step 3, guide 07-G. |
| M1 | Medium (confirmed: RV2; frequency unmeasured) | `core/intelligence/regime/detector.py:147-174` (VIX 17.0 / FII 0.0 fallbacks), `core/intelligence/rl/workflows/daily_review.py:555,592` (the NORMAL default; the first review of the day sets the sticky label); `core/portfolio/deployment.py:128-132` reads it | **Trigger:** Yahoo's `^INDIAVIX` answers nothing during a crisis. **Observed:** RISK_OFF is recorded and deployment buys toward 50%; with `^NSEI` dark too, NORMAL toward 80% and the floor. **Expected:** a label built on fallbacks opens nothing, as T6 already does for a missing label. | This is the card's first hard-review question ("Can it buy in a crisis?"). The label can be wrong when an input fails. The bound: a crisis already entered survives 2 dark days (calm streak 3), and at most 2 positions open a day. Paper money; the switch ships off. Pre-existing in the regime layer; SA-049 is its first consumer that spends cash. | **Routed to new card [FIX-023](../stories/FIX-023.md)** (P1, 2 points, directly after SA-049): a **precondition for switching deployment on**, not for this story's acceptance. Rework 1 adds the KT section 12 row and one KT section 6 sentence naming the gap until FIX-023. |
| L1 | Low (docs; confirmed: RV3) | `docs/TECHNICAL_DESIGN.md:1721-1725`; `core/portfolio/deployment.py:38-42` (module docstring) | The docs say "so a buy can pass the target by at most one position". Below the holdings floor in a calm regime, buying continues past the target, bounded only by the caps and the cash floor (T3, upheld). AUTOPILOT_GUIDE step 2 already states the rule correctly. | A reader expects at most one position past the target, and RV3 shows ₹1,18,000 over. | **Rework 1.** Replace with: "At or above the holdings floor, a buy can pass the target by at most one position; below it, buying continues toward the floor within the caps and the cash floor (from 9 holdings at 86% in ₹12 L, a tenth position takes invested to 93%)." Use the same sense in the docstring. |
| L2 | Low (docs; confirmed: RV4) | `docs/TECHNICAL_DESIGN.md:1801-1807`; `services/api/routes/portfolio_api.py:536-541` (the `deposit` docstring); `docs/TEAM_TESTING_GUIDE.md:220` (07-N's expected result) | They say the Nifty buys "that day's [close] when made before the 16:30 review, else the next session's", with the example "at Monday's 125". The 16:30 run on day T writes the point for the session it reviews (T−1). So a deposit before the run is bought at the previous session's close, and one after it at the deposit day's own close. | Comparison figures are right: both sides use the point's date. A tester running 07-N would look for the wrong close. | **Rework 1.** Say: "at the close of the session the first valuation holding it reviews: a deposit made before the 16:30 run on day T is bought at the previous session's close (the run reviews it), one made after it at T's close." Fix the example (Friday's close). Update 07-N's expected result. In the story file's D1 Nifty test docstring, note that the unit world dates the point on the deposit day. |
| T1 | Low (test gap; the card's routed input) | `tests/unit/test_deploy_idle_cash_sa049.py`; the card's "Routed input — 2026-11-01 FIX-011" asks for these tests with any buy-time check | The story file stubs `surveillance_report` and draws status "S" only. It does not pin a status other than A or S (`sizing.surveillance_issue`), nor through the buy path the report cache serving only its own day and the 7-day bound. Their three mutants (`buy_status_only_s`, `buy_older_cache_serves_first`, `buy_age_eight_days`) all survive the story file. | A regression in those rules would pass the story file. | **Rework 1, required by the card.** Add the three cases through the real `surveillance_report` with a fake archive, as `test_surveillance_sector_fix011.py` builds it. |
| T2 | Low (test gaps) | `tests/unit/test_deploy_idle_cash_sa049.py` | Three rules survive their mutants in the story file. (a) Below the holdings floor with the target already met, another position opens (`floor_clause_dropped`; the 27 Sep and D1 worlds are always below the target; RV3 catches it). (b) The deposit is idempotent on the amount too (`deposit_key_without_amount`: under the mutant, a second deposit of another amount with the same reference that day is dropped). (c) A sale on the latest dive's own day waits for a newer dive (`sold_strictly_after_dive`). | A regression would pass. | **Rework 1, recommended:** one case each (RV3's shape for (a)). |
| L3 | Low (issue time; confirmed: RV2b; pre-existing) | `core/intelligence/regime/detector.py:152,170` (`iloc[-1]` whatever `as_of_date`) | The label written for session D comes from the run day's (D+1's) bar. A D+1 crash that turns the label severe withholds a buy booked at D's close. | Flatters the paper record around a crisis's onset. The advisor's ADD gate and crisis exit read the same label already. | **Routed to FIX-023** (decide the label's session and pin it). |
| I1 | Info (owner) | `deployment.target` with the card's floor | In a calm regime, the ₹10 L floor governs whenever 80% of equity is below ₹10 L. After the ₹2 L deposit that holds up to ₹12.5 L equity. After a fall it pushes the target up: 91% at ₹11 L, 98% at ₹10.2 L. Without the deposit it reaches 99% ("works toward ₹9.9 L", in the KT example). The rule is the card's, so this is not a defect. If the switch were turned on globally, every member's portfolio would get the ₹10 L floor. | Little rotation cash after a fall. | No change. The rollout already switches on one portfolio (`portfolio.overrides.primary`); keep it so. Tell the owner. |
| I2 | Info | T4 (re-buy rule) | A stock sold after a stop can be re-bought once a newer dive exists. With 30-day re-dives that is 1 to 30 days later (RV8). Within days, the legacy `thesis_break` can also sell a new holding; the receipt lists this as a limit. | Churn, measured by the weekly scorecard. | Upheld, as disclosed. |

## Rulings on the implementer's decisions T1–T11

All are upheld. T3 holds the card's later breadth floor over its earlier property; the docs
fix is L1. T9 is right; its docs fix is L2. The card's "switch off: byte-identical"
criterion is read as "the deployment step adds nothing". With the switch off, the routed
fixes and the owner's buy-time surveillance rule still change behaviour by design: SWITCH
legs, R1, R2, SA-051 R1, the generic key and the route. The receipt's rollout step 1 lists
them, and the story's switch-off test shows that the step and the regime read never run.

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| The 27 Sep shape (2 today, the third tomorrow; hand-derived quantities) | Met (story file; the pipeline end to end; RV6's limit) |
| MACRO_CRISIS: no new position, reason recorded; EXIT and TRIM unaffected | Met for the label (RV5). A label built on fallbacks is M1 (FIX-023, before the switch is turned on). |
| Target reached; no qualifying idea with each reason | Met |
| SA-003 enforce and record | Met |
| The same review date twice | Met |
| Switch off | Met in substance (see the rulings) |
| Breadth floor: D1 six days, 6 ideas, config and override, D2 14/16 | Met |
| D1 deposit: exactly once, owner or machine key, Nifty bought at that valuation's close | Met. The docs name the wrong session (L2). |
| Property: no crisis buy, no cap breach, cash floor kept, the target passed by at most one position | Met as T3 reads it, at or above the floor (L1). |
| Routed: SA-050 R1/R2, SA-051 R1, FIX-016, PR-004 sector key | Met |
| Routed: FIX-011's tests with the buy-time check | **Not met** (T1) |
| Issue time (REVIEW.md: financial targets and issue-time information need invariant tests) | **Not met** (H1) |

## For rework 1 (a new conversation)

1. **Before the first edit,** copy the review input to `SA-049-manifest-review1.json` and keep
   a copy of the reviewed bytes. The rework's diff is taken against it, as FIX-016's reworks
   did.
2. **Required:**
   - H1: the bound, its tests and its docs.
   - T1: the three routed tests.
   - L1 and L2: the exact sentences above.
   - The KT section 12 FIX-023 row and the section 6 sentence: "Until FIX-023, a regime label
     built on a fallback input (Yahoo's India VIX or Nifty not answering) is read like any
     other; turn deployment on after FIX-023."
   - The guide's status lines.
3. **Recommended:** T2's three cases.
4. **Then re-run:** the story file, RV1 (it should now fail on its defect lines), the full suite
   and the checks, and re-record the input.

## Not exercised

- A real Saturday discovery run followed by Monday's 16:30 run.
- Production regime logs and the production shelf's dive dates. The H1 frequency argument is
  inference from the schedules and the code.
- Whether Saturday dives rank first on a real Monday.
- The real NSE archive through the buy path. FIX-011's review covered the fetcher.
- The browser rendering of the deposit row. It is pure display through escaped JSX text, not a
  security sink.
- `AUTH_REQUIRED=false` anonymous calls. They behave as for run-advisor (`require_owner`).

## Production verification

`not_started`; nothing is deployed. After an accepted rework:

- Deploy with the switch off (the receipt's rollout steps).
- Before the switch-on: FIX-023 accepted, then the owner's deposit (guide 07-N).
- Read the paper lane's record against the Nifty.
- Switch on per portfolio (guide 07-G).
