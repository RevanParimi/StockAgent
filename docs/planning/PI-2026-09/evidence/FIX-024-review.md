# FIX-024 — fresh review receipt

**Story:** [FIX-024](../stories/FIX-024.md): a buy waits for an analysis made before its close; an
unknown regime adds nothing. **Implementation receipt:**
[FIX-024-implementation](FIX-024-implementation.md).

**Context:** fresh-session review, a new conversation opened with "continue" (5 Nov 2026, about
08:14–09:02 IST, session `stockagent-main-31` [fa7ce5]). The implementation session's chat was not
read. Peers (`stockagent-main-cc`, `-64`) idle throughout.

**Verdict: ACCEPTED**, for the reviewed input below. One medium finding, pre-existing and outside
the card's scope, goes to a new card, [FIX-027](../stories/FIX-027.md). Low findings are routed or
are commit-time edits. Nothing was committed, pushed, deployed or configured, and no production
state, log or network was read.

## Reviewed input

Verified at the start and the end (`analysis_data/fix024_review/rv_digest.py`, the implementer's
recipe writing into the review folder; `start.diff` and `end.diff` byte-identical):

- Baseline: HEAD `c5165a1` with FIX-023's accepted, uncommitted tree on it, written as tree
  `194bb6f7`. All 19 of FIX-023's reviewed blobs are in that tree.
- Manifest [FIX-024-manifest.json](FIX-024-manifest.json) `ff32663c`, 28 files, `kt_manifest.py
  verify` 0 mismatches.
- Diff `f5c80f07`, 121,545 B, 27 paths. Every path changed outside the manifest is bookkeeping
  (this story's receipt and manifest, STATE, HANDOFF). End tree `57ff5145` at the start of this
  review; it changes with the bookkeeping files, the diff over the manifest's paths does not.

## Contract checked

- **M1.** A close prices a buy only when it is struck after the idea was decided. A watchlist
  analysis by its time; a deep dive, which keeps only its day, after that day's 15:30 IST close. One
  rule for the list, the SWITCH leg, deployment and the shadow. The band comes from the last close
  the analysis could read.
- **L1.** On a day whose regime was kept, not established, an ADD is held and the record says why.
  Nothing else changes.
- **L2.** A fresh state file is established for its own day.
- **Routes.** A manual run of an unclosed session is refused.

## Independent adversarial examples

Reviewer cases: `analysis_data/fix024_review/test_rv_fix024.py`, **40 passed + 4 strict xfail**
(each xfail run with `--runxfail` and confirmed to fail at its intended assertion). Expected values
come from a definition written in the test (a close of D may price a buy decided at t iff 15:30 IST
on D is strictly after t), never from the code.

- **RV1, at the ledger.** The real pipeline and deployment over 216 runs: analyses every 4 hours for
  a week, plus 15:29:59 and 15:30:00 each day, against four review sessions. A BUY exists exactly
  when the close is struck after the analysis, dated that session, at that session's close. The
  band's close is the newest one struck at or before the analysis. So a session's close is either
  readable by the analysis or can price it, never both, never neither.
- **RV1b.** Dives dated each of 7 days against 5 sessions: list, executor rule and shadow agree.
- **RV2.** Acceptance's SWITCH leg with no hand-made advice: a real stop breach, real `decide`,
  real `evaluate_switch_candidates`, real executor. 20:00: plain EXIT on Monday's review, SWITCH and
  BUY at Tuesday's close. 11:00: SWITCH and BUY at Monday's close.
- **RV3.** Friday 20:00 with Monday's bar missing: the list offers it (Monday's close is after it),
  but the close carried from Friday is not. The leg, deployment and shadow all refuse, in both gate
  modes; an undated bar too. Friday 11:00 with the same carried close is the gate's call: record buys
  and enforce refuses, as KT section 6 says.
- **RV4.** `decide` over 20,736 signal shapes, with and without the reason: it can only turn ADD into
  HOLD. EXIT, TRIM, SWITCH, triggers and destinations are identical, and the note appears only when
  an ADD the label would allow was held.
- **RV5.** Every call sequence up to length 3 over 5 kinds of prior state (155 per prior): once an
  established detection applied for the day, its label is never undone; a dark call first leaves no
  label; `calm_streak` moves at most one a day.
- **RV6.** The real `ScoreStore`'s stamp reads back as the correct IST time; the boundary in UTC
  (09:59:59 offered, 10:00:00 not), with `Z` and offset forms. The stamp is written at save, after
  the analysis has run, so it errs late.
- **FIX-023's own reproductions** (`analysis_data/fix023_review/test_rv_fix023.py`) now fail at
  their defect lines: RV3 (`'NORMAL' is None`) and RV5 (W excluded), and RV3's strict xfail passes.
  Its RV6 still passes, because it calls `decide` directly without the new signal; the story's
  L1 cases and my RV4 cover that path.
- **A dive's date:** `dive_date` is the cycle's `on or date.today()`, the UTC date on a UTC server. A
  UTC date is never later than the IST one, and the next session's 15:30 is after any run on it, so
  the day rule holds unless one cycle runs for more than about 10 hours.
- **Consumers traced:** `shelf_index` comes from `buy_candidates`, so watchlist ideas carry
  `analysed_at` into the leg; the provisional `FeedbackEntry` (`daily_review.py:1291`) is in memory
  only; the brief lists `notes` only for non-HOLD verdicts, so the raw code does not reach it; old
  records parse, and never hold an ADD (RV11). Of the five places that write a `BUY`, the SWITCH leg
  and deployment go through the rule; `store.py:582` (CSV import) and `portfolio_api.py:181` record
  the user's own holdings; the ADD (`autopilot.py:406`) tops up a holding and does not, which is M1.

## Reviewer mutants

- `test_rv_mutants.py`: **23 of 23 caught** by the reviewer's cases, in memory (source replaced,
  compiled in the function's globals, `__code__` swapped for one test). No file edited.
- Against the tracked tests, in memory (`test_rv_story_gaps.py`, control `add_not_held` caught): two
  survive; see T1 and T2. I did not re-run the implementer's 23 in-place mutants.

## Findings

| ID | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| M1 | **Medium, pre-existing**, issue time; confirmed, local reproduction | `generate_forecast.py:90` and `regenerate_envelope`; `daily_review.py:1532`; `preopen_check.py:279`; `advisor.py:220` | Monday ₹1,000, Tuesday ₹1,100. Tuesday's run reviews Monday; its re-forecast runs a live analysis with no as-of and anchors on "the most recent close". **Observed (RV13):** direction UP, ADD at ₹1,000, dated Monday; with Tuesday ₹900 and thesis not intact, EXIT at ₹1,000. **Expected:** the decision reads nothing from after its close. | The record gains or avoids up to one session's move on the shares traded. ADD and the `thesis_break` sale are live. Inference: tilts the exit-rule gate toward the legacy rule. At most 2 re-forecasts per ticker per month; frequency **not measured**. | New [FIX-027](../stories/FIX-027.md), P1, 3 points. Not in FIX-024's acceptance, so it does not block it. KT limit at commit (edit 2). |
| L1 | Low; confirmed | `narrator.py:97-100`, `_PROMPT` | Dark Friday, ADD held, `advisor.narrate: true` (production). **Observed (RV7):** the prompt holds `Annotations: REGIME_UNAVAILABLE` and `Regime: NORMAL`; no day, no reason. | The record (`regime_unavailable`) and the fallback narrative name both; the line the owner reads does not, and KT, AUTOPILOT_GUIDE and guide 07-G imply it does. Explanation only: the ADD is held. | Routed to [PR-007](../stories/PR-007.md). Docs corrected at commit (edits 1, 5, 6). |
| L2 | Low; confirmed; needs two faults | `advisor.py:243-246` | The holding's own review wrote no entry on a dark day (failed, skipped, gated). **Observed (RV8):** the older established entry is read, ADD. **Expected:** HOLD. | One 25% tranche on a day the market-wide state marks unavailable. Follows F24-D4's choice to read the entry; the label read is pre-existing. | Routed to [FIX-025](../stories/FIX-025.md), which edits the top-up's checks. |
| L3 | Low, docs; confirmed | `docs/AUTOPILOT_GUIDE.md`, section 3 example | "analysed on 17 Oct … a ₹500 close that day … a candidate from the review of 20 Oct". 17 Oct 2026 is a Saturday, 20 Oct an NSE holiday; RV9: first offered by the review of Mon 19 Oct, at Friday's close. | A reader's example, wrong twice. | Commit-time edit 4. |
| T1 | Low, test gap | `tests/unit/test_portfolio_api.py` | `run-advisor` with **no date** before the close is unpinned; only an explicit date is. Mutant `guard_only_for_an_explicit_date` survives (69 tests). The route is right today (RV10). | | Routed to FIX-025. |
| T2 | Low, test gap | `test_an_established_day_adds_as_before` | Mutant `note_when_nothing_held` (the note on an ADD that fired) survives 118 tracked tests. The code is right today (RV4). | | Routed to FIX-025. |
| T3 | Low, test gap | `test_analysis_time_fix024.py` | Acceptance asks for 11:00 through a SWITCH leg; tracked tests pin 20:00 through the leg and 11:00 through deployment and the shadow's rule. The leg calls the same `close_before_dive` the sweep pins, so it is materially covered; RV2 passes. | | Routed to FIX-025. |
| I1 | Info; rejected | `exit_shadow.invalidation_for` (implementer's "found, not changed") | `run_deep_dives` skips enabled managed symbols, and a held stock is promoted to managed, so a dive dated the review day on a held stock needs a disabled entry or a failed promotion. `advisor.exit_rule` is `shadow`. | | No action. |
| I2 | Info | `candidates.watchlist_idea` | W: BUY Mon 11:00, HOLD Tue 11:00. Tuesday's run reviews Monday and reads only the latest: not offered (RV12). A later analysis can veto an earlier close. Same bias as M1, smaller, and it buys nothing. | | KT sentence at commit (edit 3); hard-review question on FIX-027. |
| I3 | Info, receipt | F24-D5 | "DATA_GATE is still noted … so the gate's shadow record keeps counting" holds in enforce only. In record mode (production) the kept record is the ungated one, with no note and no `data_gate` (RV4b). No ADD would have fired, so nothing is lost. | | Recorded here. |

Not a finding: my first RV5 failed at random positions, each matching a logged `Failed to persist
state`, Windows refusing a rename under my test's rapid file churn. The state rules were not
involved, production is Linux, and RV5 now retries the rename.

## The card's hard-review questions

- **Does any other lane price a buy at a close from before its decision?** **Yes: M1.** The
  implementation receipt's answer, "ADD … is not a new idea's decision", does not settle it, because
  ADD's direction can come from a re-forecast made after the close. The manual routes are correctly
  closed, and every lane that opens a position goes through the rule.
- **Does holding ADD on an unavailable day change the paper record's comparison with the Nifty, and
  is that stated?** The comparison's rule does not change. A held ADD leaves its tranche in cash,
  which counts against the portfolio like any idle cash, and no cooldown starts
  (`_last_add_date` reads only BUY transactions). Stated in KT section 6. Frequency not measured.

## Upheld

F24-D1 to D4 and D6 to D10 hold as reasoned. F24-D3 (the band) is confirmed by RV1's partition.
Living documentation matches the behaviour except L1 and L3, and carries no story notes. Scripted and
documented callers of the two refused routes: none in `scripts/`; the guide says when to run them.

## Commands and environment

`.stockai` venv, Python 3.13, Windows, `tests/hermetic.py` in force (no network).

- `pytest tests -q -p no:cacheprovider --show-capture=no --tb=short --maxfail=30`: **6,066 passed,
  12 skipped, 1 xfailed, 0 failed** (13m05s, 08:41:47–08:54:57); `git status` identical before and
  after.
- `pytest analysis_data/fix024_review/test_rv_fix024.py`: 40 passed, 4 xfailed.
- `pytest analysis_data/fix024_review/test_rv_mutants.py`: 23 passed (each asserts its mutant fails).
- `python analysis_data/fix024_review/test_rv_story_gaps.py`: T1, T2 survive; the control is caught.
- `pytest analysis_data/fix023_review/test_rv_fix023.py`: 4 failed (the defects gone), 4 passed.
- `check_kt_docs`: errors `[]`. `check_broad_except`: OK (148). Fresh-interpreter imports of the
  changed modules and `services.api.server`: OK.
- PDF (`rv_docs.py`): 67 pages; the KT's digest `5ffe709caecc` is in its footer; new text present,
  removed text absent.

**Not exercised:** production state, logs or live data (M1's and every other shape's frequency); the
real LLM (narration and the analysis inside `regenerate_envelope` are faked); a real browser (no UI
change); real Yahoo or NSE reads; the implementer's in-place mutants.

## Acceptance checklist

- [x] RV5's shape: 20:00 not offered for Monday, offered for Tuesday; 11:00 offered for Monday.
  Through deployment and the leg (tracked), and a real SWITCH (RV2). See T3.
- [x] RV6's shape: no ADD; the record and the fallback narrative name Friday and "India VIX did not
  answer". The record is the level SA-003's `DATA_GATE` names its reasons at. **The LLM's line does
  not: L1.**
- [x] RV3's shape: Friday stays NORMAL.
- [x] KT section 6 states the rules; guide 07-G has the cases. Section 12's row and the removal of
  FIX-023's limit sentences happen at commit (below).

## Commit-time edits

The KT, the guides and the PDF are in the reviewed manifest, so these wait for the docs commit.

**Order:** FIX-023's code commit (its 19 blobs from tree `194bb6f7`), its docs commit (its receipt's
edits 1-8), FIX-024's code commit, FIX-024's docs commit. **FIX-024's code commit is all 28 reviewed
files, byte-exact** (`kt_manifest.py verify --rev HEAD` 0 mismatches). That briefly takes FIX-023's
docs edits out of the KT and guide, so FIX-024's docs commit **re-applies FIX-023's edits 1, 2, 4, 5,
6, 7 and not 3** (FIX-024 fixes what edit 3 lists), then:

1. **KT section 6, Advisor precedence (L1).** Replace "in either gate mode with the note
   `REGIME_UNAVAILABLE`: "an add was withheld: market regime unavailable for 2026-10-30: India VIX
   did not answer". The crisis" with "in either gate mode with the note `REGIME_UNAVAILABLE`. The
   record's `regime_unavailable` says "market regime unavailable for 2026-10-30: India VIX did not
   answer", and so does the fallback narrative; the LLM's line gets only the code (**Planned:**
   PR-007). The crisis".
2. **KT section 6, after that paragraph (M1).** Add: "**Limit.** The advisor reads the envelope as it
   stands when the run starts, and a re-forecast made after the review session's close is in it: the
   review's own (a thesis break, a shock, a flip into crisis) or that morning's pre-open check. Its
   analysis reads news up to that moment, and the review's re-forecast anchors its path on the most
   recent close. So an ADD or a sale booked at the review session's close can rest on what happened
   after that close: with Monday's close at ₹1,000 and Tuesday's at ₹1,100, Tuesday's run can ADD at
   ₹1,000. A stock has at most 2 re-forecasts a month; how often this has happened is not measured.
   **Planned:** FIX-027."
3. **KT section 6, Cash deployment, "Which ideas" (I2).** Before " Each must:", insert " The list
   reads only the latest analysis, so one made after the close that is no longer a BUY takes the
   stock off that close's offer."
4. **AUTOPILOT_GUIDE section 3 (L3).** Replace "analysed on 17 Oct at 18:00 IST" with "analysed on
   Thu 15 Oct at 18:00 IST", and "from the review of 20 Oct" with "from the review of Fri 16 Oct".
5. **AUTOPILOT_GUIDE, the ADD row (L1).** Replace "with the note `REGIME_UNAVAILABLE`, "an add was
   withheld: market regime unavailable for 2026-10-30: India VIX did not answer"." with "with the
   note `REGIME_UNAVAILABLE`; the record's `regime_unavailable` says "market regime unavailable for
   2026-10-30: India VIX did not answer"."
6. **Guide 07-G (L1).** Replace "and "an add was withheld: market regime unavailable for <Friday>:
   India VIX did not answer";" with "and the record's `regime_unavailable` "market regime unavailable
   for <Friday>: India VIX did not answer" (the narrative says so only when the LLM's line is off or
   failed);".
7. **Guide 07-G status.** "**FIX-024: implemented 2026-11-04, review pending; not deployed.**" becomes
   "**FIX-024: accepted 2026-11-05, committed as `<code commit>`; not deployed.**" In FIX-023's edit
   6, "turn it on only after FIX-023 and FIX-024" becomes "turn it on only after FIX-023, FIX-024 and
   FIX-025".
8. **KT header and section 1:** the FIX-024 code commit, and the production state at that time.
9. **KT section 12:** the FIX-024 row FIX-023's edit 4 adds becomes `Done`; after it add `|
   [FIX-027](planning/PI-2026-09/stories/FIX-027.md) | A decision booked at a session's close reads
   nothing from after that close | Open | 6 Portfolio | FIX-024 |`.
10. **Rebuild the PDF** (`scripts/docs/build_kt_pdf.py`), then `check_kt_docs` (errors `[]`).

Checked now (`rv_docs.py`): the anchors of FIX-023's edits 2, 5, 6 and 7 are all present in FIX-024's
copies, and edit 3's first anchor is gone, as expected.

## Follow-up state

- **STATE:** FIX-024 `done` with a `review` entry, production `pending_deployment`; new FIX-027
  `todo`; `active_task` null; `next_task` FIX-025 (implementation, new conversation).
- **Routed:** FIX-027 (M1; card, README row, STATE). PR-007 (L1). FIX-025 (L2, T1, T2, T3).
- **Commit:** FIX-023 and FIX-024, only at the owner's word, in the order above. A push deploys: in a
  job-free window. Deployment's switch stays off (after FIX-023, FIX-024 and FIX-025).
- **Production verification (after the deploy):** guide 07-G's production line, read-only, counts and
  fields only: advice records carrying `REGIME_UNAVAILABLE` per dark day, the run logs' "is after the
  close of" exclusions, the digests' `before_dive` outcomes.

This review is a separate-context agent review; it is not independent human or professional financial
certification.
