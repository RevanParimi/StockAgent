# FIX-024 — implementation receipt

**Story:** [FIX-024](../stories/FIX-024.md): a buy waits for an analysis made before its close; an
unknown regime adds nothing (FIX-023 review M1, L1 and L2).

**Phase:** implementation, 4 Nov 2026, about 21:40–23:25 IST. Session `stockagent-main-35`
[c2a52d], a new conversation opened with "continue". Peer `stockagent-main-9b` was writing board
cards (FIX-025, FIX-026) at the start; it messaged when done (21:45), and this phase's first
bookkeeping write came after that. This phase includes a same-conversation self-review, which is
not the fresh review.

**Baseline:** HEAD `c5165a1`, with FIX-023's accepted but uncommitted working tree on it
(`kt_manifest.py verify` of FIX-023-manifest.json: 0 mismatches at 21:44). FIX-024 stacks on that
tree. At the start it was written as a git tree object, `194bb6f7cf000f4dbbcf27827e9b479d2ec02768`,
with a temporary index (`analysis_data/fix024/base_tree.txt`; the real index untouched). It
includes -9b's FIX-025/FIX-026 cards and this phase's `in_progress` splice.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or
configured. No production state was read, no network was used, and no message was sent. No test
reaches the network (`tests/hermetic.py`).

## In one example

- **Before (RV5):** a user's watchlist BUY of W is analysed on Mon 2 Nov at 20:00 IST, after
  results filed that evening. Tuesday's 16:30 run reviews Monday, offers W, sets its band from
  Monday's ₹505 close, and a SWITCH leg (or deployment, once on) buys W at ₹505 dated Monday: a
  price from before the news the analysis read.
- **Now:** Tuesday's run does not offer W ("analysis of 2026-11-02 20:00 IST is after the close of
  2026-11-02; waits for a review of a later session"). Wednesday's run, reviewing Tuesday, buys it
  at Tuesday's close. An analysis at 11:00 IST is bought at Monday's close, its band from Friday's
  ₹500, the last close it could have read.
- **L1 (RV6):** sticky NORMAL from Thursday; Friday India VIX is dark and the Nifty fell 3%. The
  kept NORMAL used to let an UP holding ADD. Now the review's feedback entry says why its label was
  kept, and the advisor holds the ADD in either gate mode: "an add was withheld: market regime
  unavailable for 2026-10-30: India VIX did not answer".
- **L2 (RV3):** with no state file, Friday's first review writes a fresh NORMAL; a later review
  that day finding India VIX empty used to mark Friday unavailable. Friday now stays NORMAL.

## What changed

- **`core/intelligence/rl/nse_calendar.py`:** `session_close_at(day)`, 15:30 IST of a session,
  from the module's own `_MARKET_CLOSE`.
- **`core/discovery/shelf.py`:**
  - `decision_time(idea)`: (when the idea was decided, whether to the minute). A watchlist idea's
    `analysed_at`; otherwise the latest dive's day at its 15:30 close; None when undatable. An
    unparseable or naive `analysed_at` falls back to the day.
  - `close_before_decision(bar, at, timed, what)`: "" only when `session_close_at(bar) > at`.
    Reasons: "close of <bar> is before the <what> of <when>" (an earlier day), "<what> of <when> is
    after the close of <bar>" (a timed decision that day), "<what> of <when> has no time, so it
    counts as made after that day's close" (a dive dated the bar's day), and the undated bar's
    "cannot be placed after".
  - `close_before_dive(bar, idea)`: now `close_before_decision` at `decision_time` (same callers:
    deployment, the SWITCH leg, the shadow's switch test).
- **`src/backend/shared/schemas/discovery.py`:** `ShelfIdea.analysed_at` ("" for a deep dive).
- **`core/discovery/candidates.py`:**
  - `buy_candidates`: a shelf idea is excluded by `close_before_dive(on, idea)` (replaces
    `dived > on`), with "; waits for a review of a later session".
  - `watchlist_idea`: the analysis's IST time (`_ist_time`; `_ist_day` now wraps it). The age
    limit stays by day; `age < 0` is replaced by `close_before_decision(on, analysed_at, True,
    "analysis")`. The band's close is the last bar the analysis could have read: its own day's
    when the analysis ran at or after that day's 15:30, else the day before's ("no close before
    the analysis of <when>" when there is none). The idea carries `analysed_at`.
- **`src/backend/shared/schemas/feedback.py`:** `FeedbackEntry.regime_unavailable` ("" by
  default and for old entries).
- **`core/intelligence/rl/workflows/daily_review.py`:** after the sticky block, `regime_kept_why` =
  the snapshot's `unavailable` when it is set and the day has no established label
  (`label_recorded_for(review_date) is None`, or the paper lane); written on the feedback entry.
- **`core/portfolio/advisor.py`:** `AdvisorSignals.regime_unavailable`, built from the last
  feedback entry ("market regime unavailable for <its date>: <why>"). In `decide`'s ADD block an
  ADD the label would allow is held with the note `REGIME_UNAVAILABLE` (either gate mode; DATA_GATE
  still noted when the gate's blocks apply too). The record carries `regime_unavailable`.
- **`src/backend/shared/schemas/portfolio.py`:** `AdviceRecord.regime_unavailable` ("").
- **`core/portfolio/narrator.py`:** the note's plain text; the fallback narrative names the day and
  why ("an add was withheld: <the record's sentence>").
- **`core/intelligence/regime/state.py`:** `_established_for(path, state, today)`: `(_last_update
  or since) == today` and not marked. Used by `update_sticky_regime` (same-day idempotence),
  `record_unavailable_day` (the no-op) and `label_recorded_for` (its old inline test).
- **`services/api/routes/portfolio_api.py`, `scheduler_api.py`:** `POST /portfolio/run-advisor`
  and `POST /scheduler/daily-review` refuse a `review_date` whose 15:30 IST close is after now:
  "review_date <D> has not closed yet (15:30 IST); review the previous session, or run after the
  close — refusing." Their default dates are unchanged (run-advisor's the server's today; the
  scheduler's the last trading day before today, always closed).
- **`core/portfolio/deployment.py`:** the `before_dive` outcome reads "priced at a close from
  before its latest deep dive or analysis". `autopilot.py` and `exit_shadow.py`: comments only.

## Decisions (implementer's, recorded for the review)

- **F24-D1, one rule for every lane.** The candidate list (bar = the review session) and each
  executor check (bar = the close's own bar) call the same `close_before_decision`, so they cannot
  disagree; the story file's sweep checks them against the definition over 240 half-hours.
- **F24-D2, a dive keeps only its day.** The card's rule: a dive dated a trading day counts as made
  after that day's close, so its first buyable close is the next session's. A Saturday dive is
  unchanged. A dive dated a weekday holiday follows the same rule (no close that day). FIX-023's
  "a bar on the dive's day passes" is withdrawn: its test now uses a Thursday dive (below).
- **F24-D3, the watchlist band (not in the card).** The band came from the analysis day's close
  even for an analysis made before that close, so a buy at that close always sat inside its own
  band and the entry rule could not refuse it. It now comes from the last close the analysis could
  have read, as a deep dive's comes from the close it read. Shape: W analysed Mon 11:00 IST, Friday
  ₹500, Monday ₹505: band ₹485–510 (was ₹489.85–515.10).
- **F24-D4, L1 reads the holding's own entry, not the market-wide state.** The advisor already
  reads the regime label from the holding's last feedback entry; that entry now says whether the
  label was kept. So a ticker reviewed while India VIX was dark, before a later ticker established
  the day, is held; one reviewed after is not. Deployment keeps FIX-023's market-wide
  `label_recorded_for`. On a wholly dark day the two agree.
- **F24-D5, either gate mode.** A kept label is not a data-gate input SA-003's record mode is
  measuring: like FIX-023's deployment refusal, the hold applies in both modes. DATA_GATE is still
  noted when the gate's own blocks apply too, so the gate's shadow record keeps counting what it
  would block.
- **F24-D6, the crisis exit keeps reading the kept label** (the card's recommendation): a sale is
  never blocked by a missing input, and a crisis entered before dark days stays armed (F23-D3).
  The record still carries `regime_unavailable` on such a day.
- **F24-D7, L2's one test also fixes a same-day double count.** `update_sticky_regime` used the same
  marker-only test: on a fresh state's day, a second, milder detection counted a calm day. With
  `_established_for` it changes nothing, as on every later day. Only the first run, or the day
  after a corrupt file, could show it.
- **F24-D8, a manual review of an unclosed session is refused** (the card's hard-review question).
  Before 15:30 IST a run of today books every trade at a close carried from the previous session,
  under decisions made today: FIX-024's rule already refuses any buy decided after that close, but
  ADD, EXIT and TRIM of holdings would still be priced there. `POST /scheduler/daily-review` with
  an explicit `review_date` of today is the same shape (its reviews would also grade an unfinished
  session), so both owner-only routes refuse it.
- **F24-D9, the 15:30 lives in `nse_calendar`,** which already owns the session's times, rather
  than a second constant in `shelf.py`.
- **F24-D10, `before_dive` keeps its name:** guide 07-G's production check counts it.

## Found, not changed (for the review to route or reject)

- **`exit_shadow.invalidation_for`** (PR-009's evidence exit) takes a shelf idea dived on or before
  the review day by date, so a dive dated the review session (a manual weekday-evening run) sets the
  invalidation level that session's sale decision reads. A sell lane, not a buy; frequency
  unmeasured.

## Tests

- **Story file** [`tests/unit/test_analysis_time_fix024.py`](../../../../tests/unit/test_analysis_time_fix024.py),
  16 cases (each figure worked by hand in its docstring):
  - RV5 through `buy_candidates`: 20:00 not offered for Monday (both times named), offered for
    Tuesday with its band from Monday's ₹505 (489.85–515.1); 11:00 offered for Monday with its band
    from Friday's ₹500 (485–510); Friday's close refused for it; no close before the analysis.
  - The SWITCH leg: AAA sold, W not bought at Monday's close (the SELL's note names both times,
    ₹1,00,000 stays in cash); bought at Tuesday's close, floor(₹1,00,000 / ₹505) = 198 shares; the
    shadow's switch test agrees.
  - Deployment through the real pipeline (readers faked): 20:00 buys nothing on Tuesday's run, 165
    shares (floor(₹83,333.33 / ₹505)) dated Tuesday on Wednesday's; 11:00 buys 165 dated Monday;
    handed the 20:00 idea for Monday directly, the executor refuses it (`before_dive`).
  - A dive dated Monday (a manual run): not offered for Monday, offered for Tuesday, refused at a
    close carried from Monday.
  - **Invariant sweep:** analyses every 30 minutes over 5 days (240) against bars Fri, Mon, Tue, Wed:
    the candidate list, `close_before_dive` and the shadow's switch test each admit a close exactly
    when 15:30 IST of its day is strictly after the analysis (the definition written in the test);
    dives dated Fri/Sat/Mon/Tue admit exactly the later bars.
  - L1 through the real daily review (shock-path seams, real detector over a fake Yahoo, real state
    file), the real feedback log, `build_signals` and `gated_decide`: the dark day holds ADD in
    record and enforce, note `REGIME_UNAVAILABLE`, the record and fallback narrative name the day and
    "India VIX did not answer", `data_gate` None; established VIX 15 ADDs; a dark review after the
    day was established carries no reason and ADDs; the crisis exit still fires on the kept
    MACRO_CRISIS.
  - L2: RV3 through the real detector and review step 0 (fresh state, then VIX empty): Friday stays
    NORMAL, unmarked, and deployment buys 2; a fresh RISK_OFF's second same-day NORMAL is not a calm
    day.
- **Moved tests** (the rule FIX-024 changes; each change says so in place):
  - `test_regime_inputs_fix023.py`: the outcome words "or analysis"; the "bar on the dive's day keeps
    record mode" case becomes a Thursday dive with a Friday bar (renamed `…bar_after_the_dive…`);
    `close_before_dive(SAT, dive of SAT)` is now refused; the undated bar reads "after"; RR-T1's
    reason names both times.
  - `test_deploy_idle_cash_sa049.py`: FRIX (dived Friday) is no longer offered for Friday's review;
    the switch-destination case uses THUX dived Thursday; the "not offered" log text.
  - `test_portfolio_api.py`: the 202 case pins the route's clock after 15:30 (it ran at the
    wall-clock time before); a new case refuses 11:00 and 15:29, accepts 15:30.
    `test_autopilot_api.py`: the same three times on the scheduler's route (its reviews stubbed).
  - `test_trading_costs_sa048.py`: the cost-of-a-SWITCH case shelved its idea on the review
    day itself (a fixture convenience, no dive date); it is now shelved the day before, since a
    dive dated the review session counts as made after its close. Found by the first full run.
- **Mutants** (`analysis_data/fix024/mutants.py`, in place, restored by sha256; the story file, the
  FIX-023 story file and both API test files): **23/23 caught** (analysis_data/fix024/mutants.txt,
  mutants_sched.txt): the rule at and before 15:30, the day-granular bound, the analysis time
  ignored, an undated bar allowed (caught by FIX-023's file), the watchlist time check and band,
  the shelf check, the three executor checks, both routes' guard (removed, and `>=`), the entry's
  reason (never set; set on an established day), the advisor ignoring it, ADD not held, the crisis
  exit blocked, the narrative's text, and the three L2 shapes.
- **Neighbours:** before the moved tests were updated, 14 neighbouring files (the FIX-023, SA-049
  and PR-004 story files, regime, advisor, narrator, pipeline, autopilot, shelf): 306 passed, 8
  failed, exactly the 8 moved cases above. After the last code change: both API test files 31
  passed, SA-048's file 22 passed; the rest through the full suite.
- **Full suite** (`tests`, hermetic): first run 6,065 passed / 12 skipped / 1 xfailed / **1
  failed** (26m08s): SA-048's switch-cost fixture above. Second run, on the final bytes: **6,066
  passed / 12 skipped / 1 xfailed / 0 failed** (29m13s). `git status` identical before and after
  each run (`analysis_data/fix024/full_suite*.txt`, `status_*`).
- `check_broad_except`: OK (148, unchanged). `check_kt_docs`: errors `[]`. PDF rebuilt: 67 pages,
  source `5ffe709c…`.

## Self-review (same conversation; not the fresh review)

- Issue time: the only clocks read are `run_at` (stored UTC, converted to IST) and the 15:30
  constant; no wall clock enters a decision except the manual route's guard (`now_ist`).
- Every lane that opens a position at a close goes through `close_before_dive` or the candidate
  list's `close_before_decision`: SWITCH destination choice (candidates), SWITCH leg, deployment,
  shadow switch test. ADD adds to a holding and is not a new idea's decision.
- `ShelfIdea.analysed_at` is set only on watchlist ideas, built per review and never stored on the
  shelf; old shelf files parse with the default.
- `FeedbackEntry.regime_unavailable` and `AdviceRecord.regime_unavailable` default to "", so old
  logs and ledger lines parse, and an entry written before this change never holds an ADD.
- `rationale_hash` changes only on held days (a new note); the advice ledger is append-only.

## Documentation

- KT ([TECHNICAL_DESIGN.md](../../../TECHNICAL_DESIGN.md)) section 6: Advisor precedence (ADD needs
  the day's regime established; the crisis exit reads the kept label); Cash deployment's regime
  paragraph (a dark detection never undoes an established day; a held ADD's money stays in cash and
  the Nifty comparison counts it like idle cash) and "Which ideas" (decided before the close, the
  20:00 / 11:00 examples, the manual-run refusal); section 8's buy candidates. PDF rebuilt.
- [RL_DESIGN.md](../../../RL_DESIGN.md) step 0 and section 27.1; [AUTOPILOT_GUIDE.md](../../../AUTOPILOT_GUIDE.md)
  (triggers, the ADD row, buy candidates, deployment step 3); [PRODUCT_MAP.md](../../../PRODUCT_MAP.md);
  [CODEBASE.md](../../../../CODEBASE.md); guide case 07-G (the 20:00 / 11:00 watchlist cases, the
  held ADD on the dark Friday, the manual run before and after 15:30, P4's new text).
- Not edited now, because FIX-023's commit-time edits own them: the KT header, section 1, section
  11 and section 12, and guide 07-G/N/O's status lines (FIX-024's own status sentence is appended
  after FIX-023's in 07-G).

## Review input

- **Manifest** [FIX-024-manifest.json](FIX-024-manifest.json): `review_input_sha256`
  `ff32663c22356d4d59b85219373a6f7d44d53070764bbec016c63659aa58feac`, 28 files (`kt_manifest.py
  verify`: 0 mismatches).
- **Diff:** `f5c80f07b4037c8ee6176e8c354b56ba6a7b66933a82c94e87495d263b33b33e`, 121,545 B, 27
  paths (the manifest's without the PDF), between the base tree `194bb6f7` and the working tree
  written the same way (`analysis_data/fix024/digest.py`; the end tree's id changes with the
  bookkeeping files, the diff over the manifest's paths does not). Every changed path outside the
  manifest is bookkeeping (this receipt, the manifest, STATE, HANDOFF).
- **FIX-023's reviewed bytes:** its 19 blobs are all in tree `194bb6f7` (checked by
  `git rev-parse 194bb6f7:<path>` against FIX-023-manifest.json). FIX-024 changes 15 of those
  files, all in its own manifest. Text copies of every base file FIX-024 changed are in
  `analysis_data/fix024/base_files/` (hash-checked against their blobs), in case `git gc` prunes
  the unreferenced tree; the PDF rebuilds from FIX-023's KT.

## Commit (after both fresh reviews accept, only at the owner's word)

FIX-023 commits first, exactly as its review receipt says, from its reviewed bytes (the base tree
`194bb6f7` holds them; `git ls-tree 194bb6f7 -- <path>` gives each blob, and FIX-023's manifest
verifies them). FIX-024 then commits its manifest's files. Its KT differs from FIX-023's commit at
section 6, which FIX-024's reviewed copy gives whole:

1. **KT section 6** ("Advisor precedence", "Cash deployment"): take FIX-024's reviewed text. That
   drops FIX-023's commit-time limit sentences (its edit 3: the M1 day-bound sentence and the L1
   ADD bullet), which FIX-024 fixes. Section 8's buy-candidates bullets likewise.
2. **KT header and section 1:** the FIX-024 code commit and the production state at that time.
3. **KT section 12:** the FIX-024 row FIX-023's commit adds becomes `Done`.
4. **Guide 07-G:** FIX-024's status sentence becomes "accepted <date>, committed as `<commit>`; not
   deployed".
5. Rebuild the PDF and run `check_kt_docs` (errors `[]`).

## For the fresh review (the card's hard-review questions)

- **Does any other lane price a buy at a close from before its decision?** The manual
  `run-advisor` of an unclosed session did, and so did the scheduler's manual review route with
  today's date (F24-D8, both now refused); with FIX-024's rule their buys of ideas decided that
  morning were already refused at the leg (their close is the session before's). The 16:30 job
  reviews a closed session. ADD tops up a holding at the review close; it
  is not a new idea's decision, and SA-003's gate covers its close's date.
- **Does holding ADD on an unavailable day change the paper record's comparison with the Nifty?**
  The comparison's rule does not change: every deposit buys Nifty units at its day's close, and
  cash counts against the portfolio. A held ADD leaves its 25% tranche in cash, which that rule
  counts like any idle cash; the ADD can fire on the next established day (no cooldown starts,
  since nothing was bought). Stated in KT section 6 (Cash deployment). Frequency: as often as a
  dark India VIX day with an ADD due; not measured.

## Production verification (separate, after the deploy)

Guide 07-G's production line, read-only, counts and fields only: count advice records carrying
`REGIME_UNAVAILABLE` per dark day, the run logs' "is after the close of" exclusions, and the
digests' `before_dive` outcomes.
