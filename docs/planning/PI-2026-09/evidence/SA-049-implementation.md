# SA-049 implementation receipt — put idle cash to work in normal markets

## Rework 1 (2 Nov 2026), after the fresh review's changes_requested

- **Phase:** rework 1, 2 Nov 2026 about 10:13–11:05 IST (session stockagent-main-f6 [f075f4], a
  new conversation opened with "continue"); the review ran in stockagent-main-2c [c85206], the
  implementation in stockagent-main-a1 [c4bf3b]; neither chat was read. All 17 peer sessions were
  idle at the start and before bookkeeping. Status after it: `review_required`.
- **Input kept first.** The review's input was verified unchanged (`kt_manifest.py verify`: 26
  files, 0 mismatches, `55b642be`), copied byte-for-byte to
  [SA-049-manifest-review1.json](SA-049-manifest-review1.json), and its 26 files copied to the
  ignored `analysis_data/sa049_rework1/review_input/` before any edit
  (`analysis_data/sa049_rework1/snapshot.py`).
- **Nothing committed, pushed, deployed or configured. No production state or network read.**
  The switch ships off.

### What changed

| Finding | Change |
|---|---|
| **H1** (high, issue time) | `buy_candidates` (`core/discovery/candidates.py`) offers a shelf idea only when its latest deep dive (`last_dived`) is on or before `on`, the review session whose close the run books at. Otherwise it is excluded with "deep dive of 2026-10-31 is after the review session 2026-10-30; waits for a review of a session on or after it". The bound comes before the freshness rule, so it holds with re-dives off too. The watchlist lane already refused `age < 0`. SWITCH destinations, deployment and the shadow's switch test all read this one list (the pipeline's `shelf_ideas`, `shelf_index`), so they agree. `dive_is_fresh` is unchanged: `shelf.py` uses it to pick re-dives, where `on` is the discovery run's own day. |
| **T1** (routed FIX-011 tests) | Three cases through the real `surveillance_report` → `surveillance_list`, with FIX-011's fake NSE archive (`_FakeNSE`, `_row`, `_report` imported from its test file) and a cache file written by hand. |
| **L1** (docs) | KT section 6 and `deployment.py`'s docstring: "At or above the holdings floor, a buy can pass the target by at most one position; below it, buying continues toward the floor within the caps and the cash floor (from 9 holdings at 86% in ₹12 L, a tenth position takes invested to 93%)." The story file's module docstring now says the same. |
| **L2** (docs) | KT section 7, the `deposit` docstring, AUTOPILOT_GUIDE's route row and guide 07-N: the Nifty units are bought at the close of the session the first valuation holding the deposit reviews. A deposit made before the 16:30 run on day T is bought at the previous session's close; one made after it at T's close. The example is now Friday's 125. The story's D1 Nifty test docstring says its world dates the point on the deposit day. |
| **M1 → FIX-023** | KT section 12 row; KT section 6 sentence "Until FIX-023, a regime label built on a fallback input (Yahoo's India VIX or Nifty not answering) is read like any other; turn deployment on after FIX-023."; KT section 11 and AUTOPILOT_GUIDE section 16 put FIX-023 first in the rollout. |
| **T2** (recommended) | One case each: below the floor with the target met; a second deposit of another amount with the same reference; a sale on the latest dive's own day. |
| Guide status lines | 07-G (with a new P4 case for H1), 07-N and 07-O: "implemented 2026-11-01; review of 2026-11-02 asked for changes; rework 1 done 2026-11-02, re-review pending; not deployed". 07-G adds "turn it on only after FIX-023". |

**Docs for H1:** KT section 6 "Which ideas" (the run's timing and Saturday → Tuesday) and
section 8's "Buy candidates" bullet (with the excluded reason); AUTOPILOT_GUIDE section 3's first
bullet and section 7 step 3; CODEBASE's `candidates.py` row; PRODUCT_MAP's "Buy candidates" row;
`candidates.py`'s module and function docstrings (the Saturday 31 Oct → Tuesday example). PDF
regenerated.

**Behaviour change with the switch off.** H1 also changes SWITCH destinations: on Monday's run,
an idea dived on Saturday (or an IPO idea dived on Sunday) is not a destination until Tuesday's
run. The rollout's step-1 list of changes that ship with the switch off now names it.

### Tests

All runs: `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider …` (Windows 11, Python
3.13), under the suite's hermetic boundary.

- **Story file** `tests/unit/test_deploy_idle_cash_sa049.py`: **50 passed** (41 + 9 new). No
  existing assertion was changed; one docstring was extended (the D1 Nifty test, L2). New cases,
  each with its numbers worked by hand in the docstring:
  - `test_an_idea_dived_after_the_review_session_is_not_offered`: the real NSE calendar
    (`trading_days_ago(2 Nov, 1)` = 30 Oct); NEWX (first dived Sat 31 Oct) and OLDX (shelved 3
    Oct, re-dived 31 Oct) are excluded for 30 Oct with the exact reason, FRIX (dived 30 Oct) is
    offered; with re-dives off too; all three offered for 2 Nov.
  - `test_mondays_run_waits_for_a_saturday_dive_and_tuesdays_buys_it_at_mondays_close`: the
    real pipeline (RV1's shape). Monday's run (review 30 Oct) buys nothing and logs the reason;
    Tuesday's run (review 2 Nov) buys 83 × ₹1,000 dated 2026-11-02, verdict `DEPLOY`.
  - `test_a_saturday_dive_is_no_switch_destination_on_mondays_run`: the real pipeline with AAA
    held and deployment off; the advisor's `gated_decide` is given only FRIX on Monday's run and
    NEWX and FRIX on Tuesday's.
  - T1: `test_any_status_but_active_in_the_report_refuses` (status "I" and "S" refused, P3
    bought); `test_the_cached_report_serves_only_its_own_day` (a cached 10 Jul report does not
    answer for 13 Jul; NSE is asked for `REG1_IND130726.csv`, whose ST-ASM refuses P1);
    `test_a_report_older_than_seven_days_opens_no_position` (a 6 Jul cache serves 13 Jul, 7 days,
    and not 14 Jul, 8 days, with NSE unreachable).
  - T2: `test_below_the_holdings_floor_a_position_opens_past_the_target` (9 × ₹1,15,000 in
    ₹12 L: one buy to 93.2%, the second idea waits, cash ₹82,000);
    `test_a_second_deposit_of_another_amount_with_the_same_reference_is_written` (cash
    ₹10,60,000, capital in ₹12,50,000); `test_a_sale_on_the_day_of_the_latest_dive_waits_for_a_newer_dive`.
- **Reviewer cases** (`analysis_data/sa049_review/test_rv_sa049.py`), with the PR-004 and FIX-011
  story files: **1 failed, 151 passed**. The one failure is RV1 at its observed-defect line 119
  (`assert buys == [("2026-10-30", "NEWX", 83.0, 1000.0, "DEPLOY")]`; now `[]`), as the review
  asked. The pipeline's log names the new reason.
- **Mutants, in memory** (`analysis_data/sa049_rework1/rw_mutplug.py`, `run_mutants.sh`; results
  in `mutants_rw.txt`): **11 of 11 caught by the story file**, each a test failure:

  | Mutant | Story file |
  |---|---|
  | `floor_clause_dropped` (review T2a) | caught (was: survived) |
  | `deposit_key_without_amount` (review T2b) | caught (was: survived) |
  | `sold_strictly_after_dive` (review T2c) | caught (was: survived) |
  | `at_cost_never_written` | caught |
  | `rebuy_misses_todays_sells` | caught |
  | `buy_status_only_s` (FIX-011 routed) | caught (was: survived) |
  | `buy_older_cache_serves_first` (FIX-011 routed) | caught (was: survived) |
  | `buy_age_eight_days` (FIX-011 routed) | caught (was: survived) |
  | `dive_after_session_offered` (H1: the bound dropped) | caught, 3 tests |
  | `dive_on_session_refused` (H1: `>=` for `>`) | caught, 2 tests |
  | `bound_only_with_redives` (H1: the bound only with re-dives on) | caught |

- **Mutants, in place** (the implementer's `analysis_data/sa049/mutants.py`, each file restored
  and the code files' SHA-256 checked after; results in
  `analysis_data/sa049_rework1/mutants_inplace.txt`): **23 of 23 caught on the final bytes**
  (10:24–10:43 IST); all 10 files (the 9 code files and the story file) hash back to their
  pre-run bytes. "Empty portfolio skipped" is now first caught by the new Monday/Tuesday pipeline
  case (the harness stops at the first failure).
- **Full suite:** **6,023 passed / 12 skipped / 1 xfailed / 0 failed** (18m51s, 10:43–11:02
  IST), on the final code, test and doc bytes, after both mutant runs: the review's 6,014 plus
  the 9 new cases. `git status` was identical before and after (no tracked runtime file
  changed). Output: `analysis_data/sa049_rework1/full_suite.txt`.
- **Checks:** `check_broad_except` OK (149); `check_kt_docs` exactly one error, "KT links
  core/portfolio/deployment.py, which is absent at its declared revision 866eae5107b3", as before,
  cleared by the commit-time header bump; 694 local links; PDF 65 pages, source
  `ff6a386dad3e…`.

### Self-review (same conversation; not the fresh re-review)

- **Where the bound lives.** The review offered `buy_candidates` or the deploy check. One place
  that feeds every new-position buy is the smaller change, and it keeps SWITCH, deployment and
  the shadow consistent. `_deploy_check` gets its ideas only from that list (`shelf_index`), so
  no second check is needed.
- **Re-dives off.** A bound inside `dive_is_fresh` would vanish when re-dives are off
  (`redive_after_days: 0` returns True early). The bound is separate, and a case and a mutant
  (`bound_only_with_redives`) pin it.
- **The boundary.** A dive dated the review session itself is offered (FRIX), as a watchlist
  analysis of that day is. Mutant `dive_on_session_refused` pins it.
- **A same-day dive after the close** (for example a manual dive on Monday at 18:00) counts as
  Monday's and can be bought at Monday's close on Tuesday's run. The day is the unit of issue
  time here, as in the watchlist lane. This is a limit; Saturday's and Sunday's scheduled dives
  are the common case, and they are handled.
- **A re-dived idea loses its older dive.** The shelf keeps only the latest dive's levels, so an
  idea re-dived on Saturday is not offered on Monday even though its previous dive was older than
  Friday. Correct: the stored band and conviction are Saturday's.
- **A shelf idea excluded by the bound still blocks its watchlist twin** ("the shelf idea, fresh
  or not, is the record of it"), unchanged.

### Review input (rework 1)

- **Manifest:** [SA-049-manifest.json](SA-049-manifest.json)
  `64b81d4fa6db341350287a513f13c643cee5390c30960d14e867a046da7f1fa0` (26 files, the same paths
  as the review's input; `kt_manifest.py verify` 0 mismatches). The review's input is kept as
  [SA-049-manifest-review1.json](SA-049-manifest-review1.json) `55b642be…`.
- **Rework diff:** `1acfdc8857e1525886acdfee6741bf23b2b0f8da70c4e3fffab70e0b44508854` (54,656 B,
  25 paths compared, 9 changed: CODEBASE.md, candidates.py, deployment.py, AUTOPILOT_GUIDE.md,
  PRODUCT_MAP.md, TEAM_TESTING_GUIDE.md, TECHNICAL_DESIGN.md, portfolio_api.py and the story
  file; the PDF also changed and is excluded as before). Each path against the kept copy in
  `analysis_data/sa049_rework1/review_input/`, which the script first checks against
  `55b642be`.
- **Cumulative diff:** `0270757038675a854265d253230a266c9fee043e1e1b724ba487761f4adce09b`
  (237,273 B, 25 paths), the implementer's recipe against the index (= HEAD `f47d246`, nothing
  staged), new files against `/dev/null`.
- Both from `analysis_data/sa049_rework1/rw_digest.py`.
- **Not in the manifest:** this receipt, the review receipt, the kept manifest, STATE.json and
  HANDOFF.md (bookkeeping; STATE and HANDOFF also hold session -e7's uncommitted FIX-011 deploy
  record).

### Commit (after an accepted re-review, only at the owner's word)

As in the implementation's "Commit" section below, with this input's 26 files. The docs commit
also brings KT section 1's production paragraph up to date: FIX-011 (`f47d246`) was deployed at
00:14 IST on 2 Nov (session -e7's record). That paragraph is outside this rework, so it was not
edited here.

### For the fresh re-review

- Run RV1: it should fail only on its defect line. Check H1's rule against each new-position
  lane: shelf ideas (discovery and IPO), the watchlist, SWITCH legs, deployment, the shadow.
- The routed tests use FIX-011's fake archive and the real reader; check they would catch the
  three FIX-011 mutants.
- FIX-023 stays a precondition for switching deployment on, not for this story's acceptance.

## Implementation (1–2 Nov 2026)

- **Phase:** implementation, 1 Nov 2026 about 22:40 IST to 2 Nov (session stockagent-main-a1
  [c4bf3b], a new conversation opened with "continue"). Status after it: `review_required`.
- **Base:** HEAD `f47d246` (FIX-011's docs commit on `866eae5`). Session -e7 pushed it during
  this phase (00:12:42 IST 2 Nov, Railway `298fb42d`), pushing only those commits and splicing
  its deploy record into STATE and HANDOFF; the working tree was not touched.
- **Nothing committed, pushed, deployed or configured. No production state read.** The switch
  ships off.

## Owner decisions taken at the start (1 Nov, all as recommended)

Asked with plain examples before any code:

1. **Regime targets and the daily limit:** 80% invested in NORMAL, RISK_ON, MOMENTUM_EXTENDED
   and OVERSOLD; 50% in RISK_OFF; no new positions in MACRO_CRISIS; at most 2 new positions a
   day.
2. **Surveillance at buy time:** every autopilot buy that opens a position (idle-cash buys and
   SWITCH buy legs) reads NSE's daily Surveillance Indicator report and skips a stock under any
   ASM/GSM stage or not active; IPO ideas included; no report within 7 days means no new
   position, reason recorded.
3. **The DEPOSIT:** an owner-only API action run at rollout from one command; no screen button.

The 12 Oct decisions stand: D1 (₹2 L of paper capital through a dated DEPOSIT) and D2
(`target_holdings` 12, between 10 and 15).

## What changed

- **`core/portfolio/deployment.py` (new).** `breadth()` (config, then
  `portfolio.overrides.<user>`), `active()`, `recorded_regime()` (a seam over the regime
  state), `target()` (the regime's share; in a calm regime at least `min_invested_inr`; never
  above equity less the cash floor, with "invested floor unreachable" recorded), `stop_reason()`
  (never at `max_holdings` or past the daily limit; otherwise open while below the holdings
  floor in force, or while invested is below the target unless `target_holdings` are held and
  the regime's own share is met), `counted()` and `run_record()` (the digest's record).
- **`core/portfolio/autopilot.py`.** `_deploy_idle_cash` runs after sells, SWITCH legs and ADDs
  when `deployment.active(portfolio)`: candidates by conviction; `_deploy_check` (held; sold on
  or after the latest deep dive; SA-003's gate: the dive's `data_gate`, a session-dated close and
  a resolved identity, withheld in `enforce` and noted in `record`; NSE's report; the entry
  band); `size_buy` asking for `min_invested_inr / target_holdings`; a `BUY` with verdict
  `DEPLOY`, `advice_ref` `<date>|<symbol>|deploy_idle_cash`, the thesis as `reason` and a
  `deploy_idle_cash` note; promotion as held. `execute_advice` gains `candidate_quotes`,
  `surveillance` and `report`. `surveillance_report()` is the seam over `surveillance_list`; a
  SWITCH buy leg is now refused by it too. `record_value_point` lists holdings valued at cost in
  `at_cost`.
- **`core/portfolio/sizing.py`.** `whole_shares()` counts shares in paisa (SA-050 review R1);
  `surveillance_issue()` (the owner's rule above).
- **`core/portfolio/pipeline.py`.** A deploying portfolio with no holdings is reviewed; the
  candidates' closes are fetched before the lock when deploying; NSE's report is read once a run
  before any lock; FIX-016's `deploys_cash` and `switch_lands` get deployment and the
  surveillance check; the switch alert matches a buy leg to its own SELL by `advice_ref`
  (SA-050 review R2); before the value point a close is fetched, outside the lock, for any
  holding still without one (SA-051 review R1); the digest gets the deployment record.
- **`core/portfolio/results.py`.** `capital_flows`: an arrival its first point valued at cost
  (`at_cost`) is unknown there and at the first later point that values it at a close.
- **`core/portfolio/exit_shadow.py`.** `switch_buy_lands(..., surveillance_issue=)`; docstrings.
- **`core/discovery/candidates.py`.** `shelf_sector()`: an unmanaged shelf idea stored as
  `generic` is offered under the key its stored classification maps to.
- **`core/intelligence/regime/state.py`.** `label_recorded_for(day)`: the sticky label only
  when the state was updated for that day.
- **`core/portfolio/digest.py`, `digest_text.py`.** The `deployment` record and an "Idle cash:"
  line.
- **`services/api/routes/portfolio_api.py`.** `POST /portfolio/deposit` (owner or machine key;
  `amount` > 0, `reference`; one `DEPOSIT` row dated the IST day; cash and `capital_in` up by the
  amount; idempotent on (date, amount, reference); 409 without cash accounting).
- **`src/backend/shared/schemas/portfolio.py`.** `side` gains `DEPOSIT`.
- **`src/frontend/prototypes/portfolio.jsx`.** A deposit row reads "Paper capital added".
- **Settings and config.** `AUTOPILOT_DEPLOY_IDLE_CASH` (false), `…_MAX_NEW_PER_DAY` (2),
  `…_TARGET_PCT`, `PORTFOLIO_MIN_HOLDINGS` (10), `…_TARGET_HOLDINGS` (12), `…_MAX_HOLDINGS`
  (15), `…_MIN_INVESTED_INR` (10,00,000), `PORTFOLIO_OVERRIDES` ({}). config.yaml gains the
  four `portfolio` keys, `overrides: {}` and an `autopilot:` section holding today's defaults
  (`enabled`, `add_tranche_pct`, `trim_pct`, `min_cash_floor`, `add_cooldown_td`, same values)
  plus the three deploy keys.
- **`tests/conftest.py`.** `_surveillance_all_clear`: the suite's buys see a report that clears
  every symbol unless a test answers `autopilot.surveillance_report` itself.

## Technical decisions (delegated; for the fresh review to rule on)

- **T1. The executor's record goes into the digest, not a new file.** Digests are dated files
  kept per review day, so each day's "why the cash stayed" survives. Revisit if the weekly
  scorecard needs it (PR-002).
- **T2. Position size is `min_invested_inr / target_holdings`, as the card says**, also when
  equity grows: at ₹30 L the 80% target is not met inside 15 holdings and the run says "15
  holdings, the maximum of 15". Revisit when equity passes about ₹12.5 L (80% then exceeds the
  ₹10 L floor): raise `min_invested_inr`.
- **T3. A deploy buy that passes the target.** The rule allows at most one position past it
  (the card's invariant); below the holdings floor in a calm regime, buying continues past the
  target, bounded by the caps and the cash floor (the card's "buys until holdings ≥
  min_holdings and invested ≥ min_invested_inr").
- **T4. Re-buy rule:** a stock sold on or after its idea's latest deep dive is not re-bought
  until a new dive (the card's churn question; the same rule `buy_candidates` applies to the
  autopilot's own watchlist exits).
- **T5. The daily limit counts idle-cash buys only;** a SWITCH replaces a sold position and
  moves no idle cash.
- **T6. No regime recorded for the review day opens nothing** (missing, stale or written for a
  later day). Buying is the risky direction, and cash can wait a day.
- **T7. The sector key.** The sizing cap keeps counting `sector` (FIX-011's key). An unmanaged
  shelf idea stored as `generic` before FIX-011 takes the key its stored classification maps to
  (`shelf_sector`), so twelve screen-sourced positions are not one "sector". Holdings already
  held as `generic` stay so. This also applies to SWITCH destinations, a deliberate change with
  the switch off.
- **T8. SA-051 R1:** both of the card's options, combined: the pipeline fetches a close before
  the point (the common case reads true), and the point names what it valued at cost so the
  comparison reads that arrival "could not check" at that point and the next one that values it
  at a close, never the jump as a gain.
- **T9. The DEPOSIT is dated the IST day it is made;** no backdating (the comparison dates money
  by the valuation that first holds it). Symbol `CASH`, quantity 0, source `manual`.
- **T10. ADD is not checked against the surveillance report** (it opens no position; the owner's
  decision named new positions). Route if wanted.
- **T11. A failure of the deployment step never loses the day's sells.** It runs on a deep copy
  of the portfolio and the closes, kept only when it completes; on an exception nothing is
  bought, the record is `{"error": "deployment failed: …"}` and the digest's text says so. The
  real `surveillance_report` returns (None, None) on any exception: no new position, the run
  goes on.

## Tests

All runs: `.stockai/Scripts/python.exe -m pytest -p no:cacheprovider …` under the repository's
hermetic boundary (Windows 11, Python 3.13).

- **Story file** `tests/unit/test_deploy_idle_cash_sa049.py`: **41 passed** (56 s). Hand-derived
  fixtures (each docstring works its numbers):
  - the 27 Sep shape: P1 166 × ₹500, P2 333 × ₹250 on day 1 (target 99.0%, the daily limit, the
    two floors unreachable, P3 waiting), P3 83 × ₹1,000 on day 2; cash ₹6,43,750 then ₹5,60,750;
  - a crisis (only the EXIT sells; NSE not read), no regime, RISK_OFF target reached (55.0% of
    50.0%), every non-buy reason with its exact words (held, above band 14.3%, invalidated,
    abstain and stale close withheld in enforce, LT-ASM, no close, under one share, the sector
    cap, sold after its dive), SA-003 in both modes, the same day twice, the switch off (the
    deployment step and the regime reader would raise; trades equal a run with no candidates),
    the shipped config;
  - D1: the real deposit route then six days: 4, 6, 8, 10, 12, 12 holdings, ₹10,20,000 (85.0%)
    invested, cash ₹1,80,000; D2: 14 ideas stop at 12 (83.0%), 16 never pass 15; 6 ideas and
    "holdings floor unreachable: 6 qualifying ideas"; RISK_OFF from cash stops at 8 (55.3%);
    config and per-portfolio overrides change it with no code change;
  - churn (sold today, or sold before a newer dive), surveillance (no report, unlisted,
    suspended, a SWITCH into ST-ASM: SELL only, note and one report read), the shadow row's
    switch test agreeing, the generic key;
  - a 400-seed property test at the configured costs (nothing in a crisis or without a regime;
    at most N; never above the maximum; caps after the trade; band; cash floor; at most one
    position past the target from at or above the floor; every non-buy explained), with
    counters;
  - R1 (the 36-share budget; 5,000 random exact multiples; never overspends), R2 (two switches
    into one stock), the regime reader, the DEPOSIT (once, retry, reconcile clean, member 403,
    machine key, 422s, 409, the Nifty buys ₹2 L at 125: ₹14,50,000 and the day reads 0.0%),
    SA-051 R1 through the real pipeline and add route (0.0% against +2.56% and +1.90%; with no
    close, those two weeks unavailable and the next one flat against +2.80%), FIX-016 (before:
    `cash`, graded −3.0; after: `nifty`, +2.0), and the pipeline end to end (the 27 Sep shape,
    the digest and its text, the value point, the alerts; an empty portfolio deploying; with the
    switch off it is skipped); a deployment step that fails after buying on its copy (the EXIT
    is saved, nothing bought); an unreadable report counted as none.
- **Mutants** (`analysis_data/sa049/mutants.py`, each in place, original bytes restored and the
  8 code files' SHA-256 checked after; results in `analysis_data/sa049/mutants.txt`): **23 of 23
  caught on the final bytes**: no maximum holdings; the daily limit off by one; no calm floor;
  crisis buys; no "share met" clause; no surveillance check on deploy or on a SWITCH leg; no
  re-buy rule; enforce never withholds; no entry band; a double-sized position; the switch
  ignored; R1's old float floor; R2's any-buy match; no close fetch for a late arrival;
  `at_cost` unknown at the first point only; `deploys_cash` always off; a deposit twice; a
  `generic` key kept; an empty portfolio skipped; the regime of any day; deployment on the live
  portfolio; the report read unguarded.
- **Neighbouring suites** (sizing, the executor's sells/ADDs/switches, pipeline, API, schemas,
  store, settings, isolation, wave 1, FIX-016, PR-004, SA-051, SA-003, SA-008, SA-048, PR-009,
  FIX-011): **770 passed** (4m22s) after the first code pass, before the story file existed;
  the full suite below runs them again on the final bytes.
- **Full suite:** **6,014 passed / 12 skipped / 1 xfailed / 0 failed** (25m50s, 00:00–00:26
  IST 2 Nov; FIX-011's 5,973 plus this story's 41), on the final code and test bytes, after the
  mutant rerun. No tracked runtime file changed (`git status`). Output:
  `analysis_data/sa049/full_suite.txt`.
- **Checks:** `check_broad_except` OK (149 grandfathered, one fewer: the registry fallback
  moved into `_sector_of` now logs); `check_kt_docs`: exactly one error, "KT links
  core/portfolio/deployment.py, which is absent at its declared revision 866eae5107b3", expected
  until the commit-time header bump (as SA-048's `costs.py`); 688 local links, PDF 65 pages
  (was 64), source `42058dc6`.

## Self-review (same conversation; not the fresh review)

Found and fixed before the final runs:

- **A failing deployment step would have lost the day's sells.** `execute_advice` saves the
  portfolio once at the end, so an exception in the new step would have dropped that day's EXITs
  too. It now runs on a copy (T11). Pinned by a test that makes it raise after buying on its
  copy, and the mutant "deploy on the live portfolio".
- **The real report reader could raise into the executor.** `surveillance_list` promises never
  to raise, but the seam now guards it anyway (mutant "report read unguarded").
- **The all-clear test report is an empty `dict` subclass**, which `if not securities` read as
  "no report"; the rule now tests `is None` (the real reader returns None or a non-empty map).
- **`whole_shares` at large budgets.** A fixed `+1e-6` paisa could lose a paisa near ₹10⁸
  (float spacing there is about 4e-6 paisa); it now rounds the paisa to 4 places before
  flooring, and still re-checks the cost in rupees. The 5,000-case exact-multiple test runs to
  ₹2.7 crore.
- **The R1 example's mechanism.** My first test asserted that 228916.8 / 6358.8 falls below
  36; it does not. The old code lost the share because 36 × 6358.8 = 228916.80000000002 exceeded
  the budget. The test and the docstrings now say so.
- **The moved registry fallback** (`_sector_of`) was a silent broad `except`; it logs now, and the
  grandfathered entry it replaced is gone from the baseline (150 → 149).
- **The R2 test** first answered `gated_decide` from a two-item list, which shadow mode (two calls
  per holding) exhausts; it answers per holding now.

## Documentation

- **KT** (`docs/TECHNICAL_DESIGN.md`): section 6 "Cash deployment" rewritten as current design
  (the regime's target, the breadth floor, which ideas, every buy and idle rupee explained, what
  it does not change); the executor's SWITCH re-check names the surveillance report and the R2
  matching, with a new "Surveillance at buy time" paragraph; "Sizing every buy" adds the
  deployment budget and whole shares in paisa; the FIX-016 benchmark sentence is current;
  section 7 gets "Adding paper capital", the Nifty line names the deposit, and the SA-051 limit
  becomes "An add during the 16:30 run"; section 8 names the buy-time check in its limits and
  the generic-key rule; section 11's portfolio-economics bullet keeps only the rollout. Section
  12's SA-049 row stays `Open` until acceptance. PDF regenerated.
- **AUTOPILOT_GUIDE.md:** the pipeline sketch, file map, execution rules, section 7 rewritten
  with an "Idle-cash deployment" walk-through, ledger formats (`DEPOSIT`, `at_cost`), the
  deposit route, configuration (the keys are now in config.yaml), tests and planned work.
- **TEAM_TESTING_GUIDE.md:** 07-G rewritten with hand-derived expectations; new 07-N (the
  deposit) and 07-O (surveillance at buy time).
- **CODEBASE.md, docs/PRODUCT_MAP.md, docs/ARCHITECTURE.md, src/frontend/prototypes/UI_SPEC.md:**
  the new module, the deposit route and row, the candidates' sector rule.

## Review input

- **Manifest:** [SA-049-manifest.json](SA-049-manifest.json)
  `55b642bec33d4c39eafd9940f2e899b2fc86f5e8d9c9e7315a5e58f92ad38b57` (26 files),
  `kt_manifest.py verify` 0 mismatches.
- **Diff:** `45a56c30bd9557e4a82e5eeb976bbf97eb972a1ba2b4611a44d08d0364114704` (214,039 B, 25
  paths), from `analysis_data/sa049/digest.py`: every manifest path except the PDF, sorted,
  against the index (= HEAD `f47d246`, nothing staged); the two new files against `/dev/null`.
- **Not in the manifest:** this receipt, STATE.json and HANDOFF.md (bookkeeping; HANDOFF and
  STATE also hold session -e7's uncommitted FIX-011 deploy record).

## Commit (after the fresh review accepts it, only at the owner's word)

The manifest's files exactly as reviewed, then a docs commit: the KT header (the new code
commit, which clears `check_kt_docs`'s one expected error), section 12 SA-049 `Done`, guides
07-G/N/O's status lines, the PDF, with this receipt, the review receipt, STATE and HANDOFF. A
push deploys it, in a job-free window; the switch stays off.

## For the fresh review (the card's hard-review questions)

- **Can it buy in a crisis?** No: MACRO_CRISIS's target is 0, `target()` closes, and the step
  evaluates nothing (pinned by the crisis test, the property test and the mutant "crisis
  buys"). With no regime recorded for the day it buys nothing either.
- **Can it churn?** It never re-buys a stock sold on or after its latest deep dive (the re-buy
  rule), and an ADD after a deploy buy waits the 5-session cooldown (the deploy BUY is an
  autopilot BUY). It can still buy an idea that the price-path rule or a stop sells within days;
  the stop is intended, and the price-path rule needs the new holding's own forecasts first. The
  weekly scorecard's holding period and the exit test measure it (limit below).
- **Can the target be met by breaching a cap?** No: every buy goes through `size_buy` (caps after
  the trade and its costs, the cash floor); an unreachable floor is recorded. Property test.
- **Is every idle rupee below target explained?** The record lists why buying stopped, each
  unreachable floor, and each idea's outcome; a day that stops below the target always has a
  first reason (property test).
- **Is the switch really off by default?** config.yaml `deploy_idle_cash: false` and
  `overrides: {}` (test); with it off the step never runs and the regime is never read (test and
  mutant "switch ignored").

## Limits

- **Churn by the price-path rule.** A deploy buy can be sold soon by `thesis_break` once the new
  holding has forecasts; PR-009's evidence rule waits `min_hold_sessions`, the legacy rule does
  not. Measured by the scorecard, not prevented here.
- **Holdings already `generic`** stay so for the sector cap (T7).
- **The report's lag.** The file dated D is published that evening and lists measures from the
  next session (FIX-011's review), so the 16:30 run reads D-1's file, which is the list in force
  on D.

## Rollout (production verification, separate)

1. Deploy with the switch off (no behaviour change but the surveillance check on SWITCH legs, R1,
   R2, SA-051 R1, the generic key, the deposit route and, from rework 1, the dive-date bound on
   SWITCH destinations).
   **Rework 1:** FIX-023 must be accepted before step 4.
2. The owner deposits ₹2 L:
   `curl -X POST https://<host>/portfolio/deposit -H "X-Scheduler-Key: <key>" -H
   "Content-Type: application/json" -d '{"amount": 200000, "reference": "SA-049 rollout"}'`
   (or signed in as the owner). Guide 07-N.
3. Read the paper lane's record of shelf ideas against the Nifty.
4. The owner switches it on for the portfolio: `portfolio.overrides: {primary:
   {deploy_idle_cash: true}}` (a config change and a deploy). Guide 07-G on the first trading day.
5. After a month, read the Nifty comparison. Rollback: the switch off; bought positions stay.
