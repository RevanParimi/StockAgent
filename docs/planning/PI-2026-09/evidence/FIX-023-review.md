# FIX-023 — fresh review receipt

**Story:** [FIX-023](../stories/FIX-023.md): deployment buys only on a regime read from live inputs,
as of the review session (SA-049 review M1 and L3), and never at a close from before the idea's
latest dive (SA-049 re-review RR-L1, RR-T1).

**Context:** fresh-session review, 4 Nov 2026, about 20:05–20:45 IST. Session
`stockagent-main-18` [3b53f6], a new conversation opened with "continue". The implementation
session (`stockagent-main-79`) and its chat were not read. One peer (`stockagent-main-d7`) was
idle at the start; it and `stockagent-main-9b` were idle before the bookkeeping (ListAgents).

**Verdict: ACCEPTED.** Every acceptance criterion is met at the reviewed revision, with the
relevant tests passing. One medium and two low findings are follow-ups, routed to a new card,
[FIX-024](../stories/FIX-024.md) (P1, 2 points, directly after FIX-023). None is a FIX-023
regression that blocks acceptance. M1 is pre-existing and outside the card's acceptance. L1 is a
consequence FIX-023 did not name. L2 fails closed. Nothing was committed, pushed, deployed or
configured. No production state, log or network was read.

## Reviewed input

- **Revision:** the working tree on HEAD `c5165a1` (SA-049's docs commit on `f064010`), nothing
  staged.
- **Manifest:** [FIX-023-manifest.json](FIX-023-manifest.json) `211735f4…` (19 files),
  `kt_manifest.py verify` 0 mismatches.
- **Diff:** `672f6c606645c6284a9a5828bed8478a5f9877c1981ab0a08031d297824b0867` (115,078 B, 18
  paths), the implementer's recipe re-run into the review folder
  (`analysis_data/fix023_review/rv_digest.py start|end`).
- **Checked twice:** at the start (20:08 IST) and at the end (20:39 IST), with equal results.
- **Outside the manifest:** the working tree also holds STATE.json and HANDOFF.md, which carry
  the implementation's bookkeeping and SA-049's uncommitted deploy record.

## Contract checked

- **The label's session (L3).** The 16:30 job passes the same `trading_days_ago(today, 1)` to
  each `run_daily_review` and to `run_post_review_pipeline` (`scheduler.py:771, 807, 962`).
  - The detector cuts each input by its bar's own exchange date (`_closes`): Indian inputs on
    or before the session, Brent, USD/INR and the S&P 500 before it.
  - So the label for session D uses only bars closed before D's buys are booked at D's close.
- **"Established".** The deployment targets depend only on severity: the four calm labels share
  80%, and the breadth floor applies to all four (`deployment.CALM`, `config.yaml:494-500`).
  So a label fixed in severity is the right unit.
  - `_label_bounds` relies on the classifier being monotone in VIX and in the Nifty's fall, and
    on escalation being monotone in the count of firing signals.
  - I checked this against an independent brute force (RV1).
- **Every route to the recorded label:**
  - the detector's exception path (recorded unavailable);
  - the sticky layer off (nothing written, so `label_recorded_for` is None);
  - a missing or corrupt state file (a dark day writes nothing; a live day writes a fresh
    state, see L2);
  - `update_sticky_regime`'s own exception (nothing written);
  - a later dark call on an established day (no-op, except L2's fresh state);
  - the paper lane (writes nothing).
- **Consumers of the kept label on a dark day:**
  - deployment opens nothing;
  - the multipliers and the feedback log use the kept label (RL_DESIGN 27.1 says so);
  - the advisor's ADD gate and crisis exit read that feedback log (L1);
  - the brief shows the state file's label;
  - `regime_flip` cannot fire on a dark day, because the floor is never MACRO_CRISIS while the
    severity is open.
- **RR-L1.** `close_before_dive` runs before SA-003's freshness check, in both modes, in all
  three places:
  - `_deploy_check`;
  - `_execute_buys`'s SWITCH leg (via `shelf_index`, which the pipeline always passes);
  - `switch_buy_lands`.
  An undated bar is refused. ADD is unchanged, as stated.
- **Docs:**
  - KT section 5 (regime modifier) and section 6 (the regime paragraph and its two limits; the
    close-and-dive rule);
  - RL_DESIGN 13 and 27.1, AUTOPILOT_GUIDE, CODEBASE and guide 07-G describe the reviewed
    behaviour;
  - the old "Until FIX-023" limits are gone;
  - the PDF has 66 pages, and its footer carries the KT's digest `4d65a516f357`;
  - `check_kt_docs` errors `[]` (703 local links).

## Independent adversarial examples

Reviewer cases: `analysis_data/fix023_review/test_rv_fix023.py` (not tracked; 7 passed, 1 strict
xfail). Expected values come from the thresholds as the detector's docstring states them,
re-coded in the file (`truth_severity`), not from the code under test.

- **RV1, brute force (1,728 detections through the real `detect`, Yahoo faked by dated bars).**
  - The inputs: VIX at 7 values around 14 and 22; the Nifty's 5-session move at 7 values around
    ±1%; each global input not firing or firing; and each of the five inputs present or missing.
  - For every combination, the day is established exactly when every value the missing inputs
    could take gives one severity. Then the label has that severity; otherwise `floor_label`
    has the mildest one.
- **RV2, issue-time invariant over 60 random sessions.** Each session runs the real detector,
  the real daily review step 0 and the real state file.
  - There are 1–3 reviews a day, each with its own random dark inputs; the state file is
    sometimes corrupted or deleted.
  - The label recorded for a day is never milder than that day's live truth.
  - The sticky severity drops only on a day with an established review.
  - 37 of the 60 days recorded a label.
- **Reviewer mutants** (`test_rv_mutants.py`, in memory, no file edited): **6 of 6 caught.**
  RV1 catches:
  - dark global inputs ignored in the bounds;
  - a VIX midpoint in the bounds;
  - the floor set to the severest label;
  - a dark Nifty read only as rising.
  RV2 catches:
  - a dark day counted with its floor label;
  - the pre-FIX-023 flow (a dark day recorded as NORMAL).
- **RV4, L3 with Yahoo's real index shape** (tz-aware: Asia/Kolkata, America/New_York,
  Europe/London). Yahoo holds Monday's VIX 30 and Nifty 23,000, and the S&P fell 3% in its
  Friday session.
  - Friday's label is NORMAL (VIX 15, Nifty 0%, S&P 0%).
  - Monday's is MACRO_CRISIS, with (23,000 − 24,000) / 24,000 = −4.1667% and S&P −3.0%.
- **Earlier reviewers' defect cases** now fail at their defect lines, as the receipt says:
  - SA-049's RV2 and RV2b (`analysis_data/sa049_review/test_rv_sa049.py:192, 206, 226`);
  - the re-review's RR3 in both modes (`analysis_data/sa049_rereview1/test_rr_sa049.py:233,
    240`).

## Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| M1 | Medium, pre-existing (issue time; PR-004's watchlist lane, SA-049's day bound) | `core/discovery/candidates.py:154-159, 222`; `core/discovery/shelf.py` `close_before_dive` | RV5 (below) | Routed to FIX-024; KT limit sentence as a commit-time edit |
| L1 | Low (a consequence not recorded) | `core/intelligence/rl/workflows/daily_review.py:613, 1611`; `core/portfolio/advisor.py:239, 581` | RV6 (below) | Routed to FIX-024; KT limit bullet as a commit-time edit |
| L2 | Low (fails closed) | `core/intelligence/regime/state.py:164, 228` | RV3 (below) | Routed to FIX-024 |
| I1 | Info | `detector.py` `_closes` | RV4; the implementer's live probe, 2 Nov | No change |
| I2 | Info (production check) | `state.py` `record_unavailable_day` | Inspection | Guide 07-G's production count covers it |

**M1, medium, pre-existing: an analysis made after the review session's close is booked at that
close (RV5).**

- **The bound compares days.** `buy_candidates` offers an idea whose dive or analysis is dated on
  or before the review session. FIX-023's rule passes a bar on the dive's day, by the card's
  design.
- **Shape.** A user's watchlist BUY of W is analysed on Mon 2 Nov at 20:00 IST (`run_at`
  14:30 UTC), after NSE's 15:30 close.
  - Tuesday's 16:30 run reviews Monday, and W is offered (`excluded == {}`, `dived` 2 Nov).
  - `close_before_dive(Mon, W)` is "", so a SWITCH leg, or deployment once on, books W at
    Monday's close.
  - Its band also comes from that close, so the buy lands inside the band.
  - The analysis read news from after that price. In results season companies file after
    hours.
- **Reach.** SWITCH destinations are live, deployment ships off, and the shadow's switch test
  reads the same list. The Saturday discovery funnel never meets this; the owner's manual
  `POST /discovery/run` on a weekday evening would.
- **Frequency: unmeasured.** No production analysis log was read.
- **Expected:** a buy at D's close counts only an analysis made before D's close; one made after
  waits for D+1.
- **Why medium:** it decides what is bought, at a price before the decision. The record is
  flattered by hours, not SA-049 H1's days.

**L1, low: on an unavailable day, ADD reads the last established label (RV6).**

- **Shape.** Sticky NORMAL from Thursday. Friday's India VIX is dark and the Nifty fell 3.0%.
  - FIX-023 records Friday unavailable and keeps NORMAL.
  - The daily review writes NORMAL into the feedback log the advisor reads.
  - `decide` with an UP envelope and 7-day accuracy 0.70 gives ADD.
  - With RISK_OFF, the label the old fallback recorded in this shape (SA-049's RV2), it does
    not.
- **Elsewhere the change is protective.** A crisis is no longer exited by dark days, so ADD
  stays closed in more cases than before. Nothing is worse in kind: before FIX-023, ADD read a
  guess.
- **What is missing.** The receipt's hard-review answer names the multipliers and the
  hysteresis, but not this money path.
- **Bounded:** 25% of the holding, the 10% position cap, a 5-session cooldown, an UP envelope,
  accuracy ≥ 0.60.
- **The crisis exit** (`crisis_regime_bearish`) likewise stays armed through dark days, as
  F23-D3 intends.
- **Expected (FIX-024):** ADD held on an unavailable day, with a note.

**L2, low, fails closed: a fresh state file loses its own established day (RV3).**

- **Shape.** With no state file, or a corrupt one:
  - Friday's first review answers NORMAL and writes a fresh state with no `_last_update`
    (`state.py:164`); `label_recorded_for(Fri)` is NORMAL (by `since`).
  - The second review finds `^INDIAVIX` empty (the Nifty flat, so VIX > 22 alone could make it
    RISK_OFF), and `record_unavailable_day` marks the day (`state.py:228` compares only the
    marker).
  - Friday then has no label, and deployment opens nothing.
- **The claim it contradicts.** The implementation receipt's "a later dark call cannot override
  an established day" does not hold for a fresh state. The function's docstring rule ("the day
  is already established (updated for `today`, not marked): no-op") and `label_recorded_for`
  disagree on what "updated for today" means.
- **Frequency:** only the first run, or the day after a corrupt state file.
- **Pinned:** an observed-value case and a strict xfail for the expected behaviour.

**I1, info: L3 relies on Yahoo indexing each ticker in its exchange's time zone.**

- The live probe of 2 Nov and RV4 show the current shape.
- If an index came back in UTC, an Indian bar (midnight IST = 18:30 UTC the day before) would
  date a day early. The cut at D would then admit D+1's bar.
- No change asked for. The production line for guide 07-G could note the index time zones once.

**I2, info: a persistent India VIX outage makes every day unavailable.**

- VIX above 22 alone is RISK_OFF, so a missing VIX always leaves the severity open.
- So deployment opens nothing, and a crisis entered before the outage cannot exit during it.
  ADD stays closed, and the crisis exit stays armed.
- This is F23-D3 as designed. Guide 07-G's production count of "did not answer" days is the
  check; count consecutive days too.

**Upheld:**

- F23-D1..D7, in particular:
  - D2: the RSI never closes the day; the targets prove it;
  - D3: the hysteresis on dark days;
  - D5: the overseas cut;
  - D6: the 7-day bound;
  - D7: either mode, undated refused.
- The 22 story cases' hand-worked figures. I re-derived the RISK_OFF buy: 50% of ₹12 L = ₹6 L
  against ₹3.6 L invested; two buys (the daily limit) of floor(83,333.33 / 1,000) = 83 shares
  at ₹1,000; ₹3.6 L + ₹1.66 L = ₹5.26 L = 43.8%.
- The broad-except ratchet change (one fewer, `swallow-ok` with its reason).
- The docs, and the PDF.

**Test fakes.**

- The story's fake Yahoo returns naive midnight indexes; RV4 covers the tz-aware shape.
- No test reaches the network (`tests/hermetic.py`; the reviewer conftest imports the suite's
  autouse isolation).
- The executor, state file and detector are real in the acceptance cases.

## Commands and results

From the repository root, Windows, `.stockai` venv (Python 3.13), `-p no:cacheprovider`:

- `python analysis_data/fix023_review/rv_digest.py start` / `end`: manifest `211735f4`, diff
  `672f6c60`, 115,078 B, 18 paths, verify 0 mismatches (both).
- `pytest tests/unit/test_regime_inputs_fix023.py tests/unit/test_deploy_idle_cash_sa049.py
  tests/unit/intelligence/regime tests/unit/intelligence/rl/test_regime.py`: **146 passed**.
- `pytest analysis_data/fix023_review/test_rv_fix023.py`: **7 passed, 1 xfailed** (strict, L2).
- `pytest analysis_data/fix023_review/test_rv_mutants.py`: **6 passed** (each mutant caught).
- `pytest analysis_data/sa049_review/test_rv_sa049.py -k rv2`: 3 failed at their defect lines, 2
  passed; `pytest analysis_data/sa049_rereview1/test_rr_sa049.py -k rr3`: 2 failed at their
  defect lines.
- **Full suite** `pytest tests`: **6,045 passed / 12 skipped / 1 xfailed / 0 failed** (18m18s, 20:20–20:39 IST). Output:
  `analysis_data/fix023_review/full_suite.txt`; `git status` equal before and after.
- `python scripts/docs/check_kt_docs.py`: errors `[]`; `python
  analysis_data/fix023_review/rv_pdf.py`: 66 pages, KT digest in the footer, the new sentences
  present (one probe split by a page break), the removed limits absent.

**Not exercised:**

- a real Yahoo outage;
- the 16:30 job end to end with an envelope (the review stops after step 0 without one);
- the advisor's full `build_signals` path for L1 (`decide` called with the feedback log's label);
- production logs, state or analyses (frequency of every shape unmeasured).

## Acceptance checklist

- [x] RV2's shapes: India VIX empty → no position, the reason names the input; live MACRO_CRISIS
  control unchanged (story file, RV1, RV2).
- [x] A crisis already entered stays (story file; RV2's severity-drop check).
- [x] A detector exception opens no position (story file).
- [x] L3 decided (Indian on or before, overseas before) and pinned (story file; RV4 tz-aware).
- [x] KT section 6 regime paragraph and the guide 07-G dark-input case. Section 12's row turns
  `Done` at commit (commit-time edit 4).
- [x] RR-L1: RR3's shape buys nothing in record mode, and the reason names both dates. A bar on
  the dive's day is unchanged. The KT sentence moved from a limit to the rule.
- [x] RR-T1: a tracked case; the mutant `watchlist_no_lower_bound` is caught (implementer's
  23/23).

## Commit-time edits

The KT, the guide and the PDF are in the reviewed manifest, so these are applied with the docs
commit after the code commit, not now. Exact text:

1. **KT header:** `**Edition:** <commit day>` and `**Code inspected:** <the FIX-023 code
   commit>`.
2. **KT section 1, "Production state at this edition", first paragraph**, replaced by:
   "Production runs `c5165a1` (SA-049, code `f064010`), deployed at about 20:12 IST on 2
   November 2026 (the deployment list showed it SUCCESS and `/health` answered 200), with
   idle-cash deployment off. The inspected code adds FIX-023: a regime label counts only when
   live inputs establish it, read as of the review session, and no buy that opens a position
   takes a close from before its idea's latest dive (section 6). It is committed but not yet
   deployed, and counts as running only once a read-only check of the deployment list and
   `/health` confirms that deploy. The table gives the configuration that differs from the
   repository and the state of each operational control." (Use the production state as it
   stands at commit time.)
3. **KT section 6, Cash deployment:**
   - In "Which ideas", after "Monday's run reviews Friday." insert: "The bound compares days: a
     watchlist analysis made on the review session's day after its 15:30 close, or the owner's
     manual deep dive that evening, is offered for that session and bought at that close, so it
     can act on news from after its price (FIX-024)."
   - In the regime paragraph's limits, add a third bullet: "- The advisor's ADD gate reads the
     kept label on such a day, so an ADD can go ahead in a market the live inputs that answered
     may call a crisis (FIX-024)."
4. **KT section 12:**
   - The FIX-023 row's `Open` becomes `Done`.
   - After it, add the row: `| [FIX-024](planning/PI-2026-09/stories/FIX-024.md) | A buy waits
     for an analysis made before its close; an unknown regime adds nothing | Open | 6
     Portfolio; 8 Discovery | FIX-023 |`.
5. **KT section 11, Portfolio economics:** "after FIX-023 (a regime label built on a fallback
   input opens no position)" becomes "after FIX-023 (a regime label built on a fallback input
   opens no position) and FIX-024 (an idea analysed after a session's close is not bought at
   that close)".
6. **Guide 07-G status:** "**SA-049: accepted 2026-11-02, committed as `f064010`; not deployed,
   and the switch ships off (turn it on only after FIX-023).** **FIX-023: implemented
   2026-11-02, review pending; not deployed.**" becomes "**SA-049: accepted 2026-11-02,
   committed as `f064010`; deployed 2 Nov 2026 (the switch is off; turn it on only after
   FIX-023 and FIX-024).** **FIX-023: accepted 2026-11-04, committed as `<code commit>`; not
   deployed.**"
7. **Guide 07-N and 07-O status:** "**SA-049: accepted 2026-11-02, committed as `f064010`; not
   deployed.**" becomes "**SA-049: accepted 2026-11-02, committed as `f064010`; deployed 2 Nov
   2026 (the switch is off).**" (SA-049's deploy record).
8. **Rebuild the PDF** (`scripts/docs/build_kt_pdf.py`), then run `check_kt_docs` (errors `[]`).

## Follow-up state

- **STATE:**
  - FIX-023 `done`, with a `review` entry; production `pending_deployment`.
  - New FIX-024: `todo`, P1, 2 points, depends on FIX-023, directly after it.
  - `active_task` null; `next_task` FIX-024 (implementation, in a new conversation).
  - The card, the PI README row and STATE carry the routing.
- **Commit:** only at the owner's word.
  - The code commit is the manifest's files exactly as reviewed (`kt_manifest.py verify --rev
    HEAD` 0 mismatches).
  - The docs commit carries the edits above, this receipt, the implementation receipt and
    manifest, the FIX-024 card, the README, STATE and HANDOFF (with SA-049's uncommitted
    deploy record).
  - A push deploys it: in a job-free window.
- **Production verification (after the deploy):** guide 07-G's production line.
  - Count the review days whose log says "did not answer", and the longest run of them.
  - Count the digests' `before_dive` outcomes.
  - Confirm the state file carries `_unavailable` only on such days.
  - Read-only, counts and fields only.
- **Switch-on (SA-049 rollout step 4):** recommended after FIX-024 too, because of M1.
