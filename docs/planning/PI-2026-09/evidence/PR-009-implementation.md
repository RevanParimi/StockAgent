# PR-009 — implementation receipt

**Story:** [PR-009](../stories/PR-009.md): exit on evidence, not on a price-path miss (shadow,
then switch).
**Phase:** implementation, 23 Oct 2026, about 20:22–21:30 IST. Session stockagent-main-af, a new
conversation opened with "continue"; the 19 peer sessions were idle at the start and at
bookkeeping.
**Baseline:** HEAD `d7c1411` (PR-011's docs commit). The working tree held only the previous
session's uncommitted push note (STATE, HANDOFF) and the owner's `docs/README.md` line; neither is
part of this phase.
**Status after this phase:** `review_required`. Nothing was committed, pushed, deployed or
configured. No production state was read, no model was called, no message was sent and no
network call was made: every test stubs prices, events and the score history.

## Rework 1 (24 Oct 2026, about 06:40–08:00 IST)

**Context.** Session `stockagent-main-c4`, a new conversation opened with "continue". Peers
`stockagent-main-da` and `depth-eval-resume-engine-b9` were idle at the start and before
bookkeeping (ListAgents). It answers the fresh review's CHANGES REQUESTED
([review receipt](PR-009-review.md), session `stockagent-main-da`). It includes a
same-conversation self-review, which is not the fresh re-review. **Status after:**
`review_required`. Nothing was committed, pushed, deployed or configured. No production state was
read, no model was called, no message was sent and no network call was made.

**Input.** The review's input: manifest `5afb4aa1…` (17 files), diff `9ef8fdba…` (116,287 B,
16 paths), on HEAD `d7c1411`. Both were verified unchanged at the start (`kt_manifest.py verify`,
0 mismatches; `analysis_data/pr009/digest.py`, the same digest). The 17 files were copied to the
ignored `analysis_data/pr009_rework1/review_input/` before any edit; the rework is the working
tree on top of them.

### In one example (F1)

EEE is dived on 22 Sep at about ₹500, with its invalidation level at ₹455, and bought on 23 Sep at
₹500. A 1:1 bonus goes ex on 21 Oct, and the sync makes the holding 20 shares at ₹250. On 23 Oct
EEE closes at ₹245: ₹490 in the old shares, down 2%.

- **Reviewed code:** `case_broken` fired on "close 245.00 at or below the invalidation level
  455.00". Under `evidence` the autopilot sold.
- **Now, when NSE's list read that day reaches back to the dive** (here it starts with a dividend
  of 14 Aug): the level is 455 / 2 = ₹227.50, and nothing fires. At ₹225 (₹450 in the old shares,
  down 10%, inside the 12% stop) the level is crossed: "close 225.00 at or below the invalidation
  level 227.50 (shelf idea dived 2026-09-22, promoted; 455.00 at the dive, adjusted for the bonus
  ex 2026-10-21 (÷2))".
- **Now, with the review's exact R1** (NSE's list holds only the bonus row): the list does not
  reach back to 22 Sep, so a bonus or split between the dive and the buy cannot be ruled out. The
  level is not used. Nothing fires at ₹245 or at ₹225, and the row's `gaps` say why.

### In one example (F2)

BBB has a standing actionable SELL, and the price-path rule holds it on 26–30 Oct. The five rows
now name the holding (bought 23 Sep). They are **one decision**, on 26 Oct; the other four are
later days of it. The review's four five-day episodes read, both Sundays: "The price-path rule
and the evidence rule disagreed on 4 decisions in 20 holding-days reviewed (a holding counts once,
on the first day the rules differed; 16 later days of the same disagreements are not counted); at
10 sessions it was right on 2 of 4; at 30 sessions it was right on 2 of 4. Switch gate: not yet
(4 of the 15 decisions it needs have reached 30 sessions)."

### Changes

| Finding | Change |
|---|---|
| **F1** (required) | `core/portfolio/corp_actions.py`: `ActionRecord` (a symbol's parsed bonus and split rows; `covers_from`, the earliest ex-date of any row NSE returned; `unparsed`, the ex-dates of split or bonus rows that did not parse, a bonus read as a dividend included) and `action_record()`. `sync_corp_actions()` returns `records` for every symbol whose fetch did not raise; what it applies is unchanged (`parse_action`'s field reading moved into `_row_desc`/`_row_ex_date`, same behaviour). `core/portfolio/exit_shadow.py`: `invalidation_for()` also returns the dive day; **`level_in_basis()`** (D12); `exit_evidence(actions=)`; `EvidenceReader(corp_actions=)`; the row's evidence keeps `invalidation_level_at_dive`. `advisor.py`: the field `ExitEvidence.invalidation_level_at_dive`. `pipeline.py`: keeps the sync's records and passes them to the reader. |
| **F2** (required) | `schemas/portfolio.py`: `ExitShadowRow.buy_date` (required: the holding's identity) and `price_bar_date`. `exit_shadow.py`: **`first_disagreements()`** (D13); `grade_disagreements()` grades decisions only; `scorecard_block()` reports `decisions` and `repeat_days` (in place of `disagreements`); the line and the gate's reason say "decisions". `pipeline.py` writes the buy date. |
| **L1** (optional, done) | The row records `price_bar_date`; grading reads the Nifty from that session (`priced` in each grade), the horizons still counted from the review day (D14). |
| **L2** (optional, routed) | [PR-007](../stories/PR-007.md) gains "Routed input — 2026-10-23 PR-009 review (L2)": the sale names the reason that fired, with a fixture for each, before any switch to `evidence`. KT section 6 lists it as a limit. |
| Docs | KT section 6: evidence-rule item 3; "The invalidation level's price basis" with the bonus example; the row's holding and session; "Decisions"; grading from the close's session; the gate's population and table in decisions; "When it can first pass" (D4′); three limits (NSE's reach, L2, the re-fetch in decisions). Section 7's scorecard row. PDF rebuilt. CODEBASE: the `exit_shadow.py` row; a new `corp_actions.py` row. Guide 07-K (a fifth holding with a bonus, and its list holding only the bonus), 07-L (buy dates, both levels, the gap count reported to the owner), 09-H (counted in decisions, 3 later days that change nothing, the four five-day stocks). Status lines: "rework 1 2026-10-24; fresh re-review pending". |

### Decisions (delegated, recorded)

- **D12 (F1). The invalidation level is compared in the review day's price basis, or not at all.**
  The level, set from the dive's close, is divided by the ratio of every bonus or split that went
  ex after the dive and on or before the review day. Each record covers its own days:
  - after the buy, the holding's applied actions: the record its cost basis and the stops already
    trust, so the level stays in the holding's basis;
  - from the dive day to the buy day, the symbol's `ActionRecord` from that day's sync. It counts
    only if NSE's list reaches back to the dive day: its earliest row of any kind is on or before
    it. The list for those days is the only use of NSE's rows, so a row NSE rewords later (another
    key) cannot be counted twice.

  Unknown, and then the level is unused with a gap: a list that does not reach the dive (an empty
  list, NSE's answer or a failed fetch, looks the same), a bonus or split ex on the dive day
  itself, or an unparseable split or bonus row from the dive day on. A dive on the buy day still
  needs the list, because the holding's record starts the day after.

  *Rejected:*
  - skipping whenever the dive precedes the buy: that is almost every autopilot buy (dives are
    weekly; a buy may use a dive up to 30 days old, `discovery.redive_after_days`);
  - trusting the entry rule for those days: an assumption, not a basis; a 1:10 bonus can leave the
    price inside the band;
  - the dive day's adjusted close from yfinance: the money-path close is cross-checked against
    NSE's raw close, which may replace it;
  - inferring actions from the EOD store's `prev_close`: an unverified data convention.

  *Revisit* when guide 07-L counts the gaps. If most rows say the list does not reach the dive,
  the sync should ask NSE for an explicit date range; that changes the money path, so it is its
  own story.
- **D13 (F2). A decision is a holding's first disagreeing row**, the holding being its symbol and
  buy date.
  - The later rows of the same holding stay in the file and are not graded or counted (the total,
    the tally, the 30% share, the span), whichever rule they favour. Under the rule that sold it,
    the holding no longer exists.
  - A stock bought again is a new holding.
  - A row without a buy date can only come from the reviewed code, which never reached production;
    it would group by symbol alone (at most one decision).
  - The stored block renames `disagreements` to `decisions` and adds `repeat_days`. No scorecard
    with an exit-rule block exists in production.
- **D14 (L1). A carried-forward close is graded from its own bar's session**: the stock's start is
  the row's close and the Nifty's start is that session. The horizons are counted from the review
  day, the day the decision was made. A bar date after the review day is ignored.
- **D4′ (D4 restated).** The span rule is unchanged. The estimate is now in decisions: at two new
  decisions a week the first possible pass is about 15 weeks after the shadow starts (the 8-week
  span, 6 weeks for the last decision to mature, one more look); at one a week, about 21 weeks.
  That is arithmetic, not a measurement. The price-path rule sold 8 times between 1 Aug and
  11 Oct, on about 2 holdings (product review section 11): about one candidate decision a week.
  So for the owner: "not yet" for about four to five months, sooner with more holdings (SA-049).

### Invariant tests (expected values worked by hand)

Story file `tests/unit/test_exit_evidence_pr009.py`: 26 → 39 tests.

| Contract | Test |
|---|---|
| Split before the buy, bonus after it: 900 / 5 / 2 = **₹90.00**; the bonus once although NSE rewords it (45 if twice), the split from NSE's list only (180 if missed) | `test_a_split_before_the_buy_and_a_bonus_after_it_both_divide_the_level` |
| Dive after the buy: only the bonus after the dive divides, 300 / 2 = **₹150.00**; one after the review day does not; a dividend changes nothing | `test_a_dive_after_the_buy_needs_only_the_holdings_own_record` |
| Never used on an unestablished basis, each with a neighbour one day or one row away: the list reaching the dive day (yes) or starting the day after (no); empty; not read; a bonus on the dive day (no) or the day before (yes); an unreadable bonus after the dive or on the dive day (no) or before it (yes); dived on the buy day without a list (no) and with one (yes). An unused level fires nothing at ₹100 | `test_a_level_whose_basis_cannot_be_established_is_never_used` |
| The record from NSE's rows (an AGM sets the reach; a bonus read as a dividend is unparsed); the sync still applies only the bonus after the buy (₹500 → ₹250, 10 → 20 shares); a raising fetch gives no record | `test_nse_rows_become_a_record_and_the_sync_applies_exactly_as_before` |
| **R1 as an invariant**, real sync, pipeline and autopilot, both modes: level 227.50, at the dive 455.00; ₹245 fires nothing; ₹225 fires, and is sold only under `evidence` | `test_r1_a_bonus_after_the_buy_halves_the_level_and_a_2pct_fall_fires_nothing[shadow/evidence]` |
| R1 exactly as reviewed (list = the bonus row): level unused, the gap's text, nothing fires or is sold at ₹245 or ₹225 | `test_r1_as_reviewed_nse_listing_only_the_bonus_leaves_the_level_unused` |
| **R2**, real pipeline: 5 rows with the same buy date and bar date, 1 decision (26 Oct), 4 later | `test_r2_a_standing_sell_over_five_days_is_one_decision` |
| **R2's gate**, real weekly scorecard: 4 decisions, 2 right at both, span 63 days, "not yet (4 of the 15 …)" both Sundays, the exact line | `test_r2_four_five_day_episodes_are_four_decisions_and_the_gate_says_not_yet` |
| A stock bought again is a second decision; both are graded | `test_a_stock_bought_again_later_is_a_second_decision` |
| A price-path EXIT nobody executes (no autopilot), through the real pipeline on 3 days: 12 rows, 6 disagreeing, 2 decisions | `test_a_price_path_sale_that_repeats_is_one_decision` |
| Later days never reach the count (14 + 10 later: not enough; a 15th holding passes), the span (50 days, later days to 70) or the share (S0 4 of 15, not 10 of 21) | `test_later_days_never_reach_the_gate_count_span_or_share` |
| L1: a close carried from 1 Sep, reviewed 2 Sep: excess **−4.0** points (−3.02 from 2 Sep); the Nifty read on 1 Sep, never 2 Sep | `test_a_carried_forward_close_is_graded_from_its_own_session` |

**Existing tests changed** (a contract moved; no assertion was relaxed):
- the ₹500 example passes NSE's list, because its dive (1 Oct) precedes its buy (16 Oct), and now
  also asserts no gap and the row's buy date;
- two `shadow_row` calls pass the buy date;
- `invalidation_for` also returns the dive day;
- the gate's reason says "decisions";
- the `_row` fixture names a holding (one per symbol unless a test re-buys), and `_matured_rows`
  makes each of its 16 rows its own holding (8 stocks held twice), so the scorecard test still
  has 16 decisions;
- the scorecard test reads `decisions` and `repeat_days` and the new line.

**Mutants.** `analysis_data/pr009_rework1/mutants.py` (the implementation's harness: one change,
the story file with `-x`, each file restored and SHA-checked): **31 of 31 caught**
(`mutants_run1.txt`, and S10 run on its own):
- 18 on the basis rule: no division, multiplication, the dive-to-buy window not required, the
  dive-day reach refused, the holding's record unused, its actions before the dive used, NSE's
  list used after the buy, the dive-day ambiguity, unparsed rows, unparsed on the dive day, a dive
  on the buy day, a gap keeping the level, actions after the review day, the pipeline, the sync's
  return, the reach from parsed rows only, a bonus read as a dividend, the reader;
- 10 on the first-day rule: every row a decision, the holding by symbol only, by buy date only,
  the last day kept, grading around it, the block's count, the pipeline's buy date, `repeat_days`,
  the line, and the implementation's M27 on its new line;
- 3 on L1.

The implementation's 36 re-run on the reworked code (`mutants_impl_rerun.txt`): 35 caught; M27's
pattern no longer exists (its check moved into `first_disagreements`) and is S10 above.

**The reviewer's repro** (`analysis_data/pr009_review/test_review_repro.py`, which asserts the
defects): R1 and R2-gate now fail on their defect lines (`evidence_triggers == []`; the gate
`not_enough`, 4 matured). R2-pipeline still passes: its five rows are kept, as the contract says.
R3, the positive control, passes.

### Self-review (same conversation; not the fresh re-review)

- **Found and fixed:** the reader looked records up by the normalized symbol, while the sync keys
  them by the holding's own spelling. It now normalizes the keys, so a difference in case cannot
  silently drop a record.
- **Found and fixed in the tests:** `_row`'s first default (a new buy date per row) made every row
  its own holding, and it hid R2-gate from the reviewer's repro. It is now one holding per symbol,
  as the pipeline writes. A rewording by NSE was untested: same keys masked a double count (now
  R07). An unparseable row on the dive day itself was untested (now R10).
- **Checked:** what the sync applies is byte for byte the same code path (the field readers are
  the same loops); the corp-action file's 17 tests and the fetcher's tests pass. A failed NSE fetch
  still returns `[]` (unchanged), and for the level it reads as "not reached". The stops and the
  other rules are untouched: the property test and the shadow/legacy byte identity pass.

### Limits after the rework

- **NSE's reach is unmeasured** (KT section 6 limit). The sync asks for the symbol's actions
  without dates. If NSE returns only recent and forthcoming actions, the invalidation test cannot
  run for a holding dived before its buy, which is most of them, and each row's `gaps` says so.
  The other two reasons still run. Guide 07-L counts it on the first review days.
- **L2** waits for PR-007, before any switch to `evidence`.
- Everything in "Limits and follow-ups" below stands; the re-fetch now grows with decisions.

### Commands and environment (rework 1)

Windows 11, the `.stockai` venv (Python 3.13), with the hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `kt_manifest.py verify` on manifest 5afb4aa1; `analysis_data/pr009/digest.py` (start) | 0 mismatches; `9ef8fdba…` 116,287 B, 16 paths |
| `pytest tests/unit/test_exit_evidence_pr009.py` | **39 passed** |
| `pytest` on the story file, the corp-action and fetcher files, and the review's 11 related files | **918 passed** (80 s), on the final bytes |
| `analysis_data/pr009_rework1/mutants.py` | 31 of 31 caught |
| `analysis_data/pr009/mutants.py` (re-run) | 35 of 36 caught; M27 not applicable, re-expressed as S10 (caught) |
| `pytest analysis_data/pr009_review/test_review_repro.py` | 2 failed (R1, R2-gate: on their defect lines), 2 passed |
| `pytest tests` (full suite) | **5,711 passed, 12 skipped, 1 xfailed, 0 failed** in 14 min 13 s (5,698 before, plus the 13 new); `find data -newer suite_start.marker`: no file |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `build_kt_pdf.py`, then `check_kt_docs.py` | 56 pages, no overflow; exactly the one expected error (`exit_shadow.py` absent at the header's `ffa012b`) |

### Manifest and digests (the re-review's input)

- **Manifest:** [PR-009-manifest.json](PR-009-manifest.json), rewritten for rework 1: **19 files**,
  SHA-256 of its LF bytes **`0c6057e9d3964a5265f7829b77f8d913873534d55d2013a36526808a62ef2256`**;
  `kt_manifest.py verify` gives 0 mismatches. It is review 1's 17 files plus
  `core/portfolio/corp_actions.py` and `docs/planning/PI-2026-09/stories/PR-007.md`. Review 1's
  manifest `5afb4aa1…` is kept as `analysis_data/pr009_rework1/review_input_manifest.json`.
  Excluded, as before: STATE, HANDOFF, this receipt, the review receipt and the owner's line in
  `docs/README.md`.
- **Rework diff** (what changed since review 1's input):
  **`4afc909a086e2ae33486fa9a3b48694055ae494b4cad429d242d4761fd383342`**, 91,569 bytes over the
  manifest's 18 text paths, of which 10 changed (and the PDF). Made by
  `analysis_data/pr009_rework1/rw_digest.py`. It checks HEAD `d7c1411` and that every copied
  review-input file's blob id equals manifest `5afb4aa1`'s. A reviewed path gives
  `git diff --no-index review_input/PATH PATH` (labels rewritten to `a/PATH b/PATH`); the two
  paths outside it give `git diff HEAD -- PATH`. Output: `rework.diff`.
- **Cumulative diff** (PR-009 as a whole against `d7c1411`, the implementation's recipe over the
  18 paths): **`86aac81bbb5c6163718bd770dcf2567501c57e196c2e204839169d4076e16495`**, 163,305
  bytes. Output: `cumulative.diff`. Both digests were computed twice after the full suite, with the
  same result.

**Commit-time edits** (unchanged from the implementation): the KT header "Code inspected" bump
and section 12's PR-009 row Done; the PDF; the guide's 07-K, 07-L and 09-H status lines.

## In one example

A stock is bought at ₹500 for its order book. Four sessions later the market falls 2% and the
stock 4%, to ₹480. The price path expected about ₹505, so the daily review asks the thesis
reviewer, which says "not intact", and the re-forecast path ends at ₹470.

- **The price-path rule** (`thesis_break`, unchanged) sells at ₹480, a 4% loss.
- **The evidence rule** (`case_broken`) asks three questions and the holding period. Is there a
  high-materiality negative company event in the last 5 sessions? No. Is the latest actionable
  analysis a SELL? No, it is a BUY. Is ₹480 at or below the invalidation level (₹455)? No. Has
  it been held 10 sessions? No, 4. So it **holds**.
- **What happens:** with `advisor.exit_rule: shadow`, the shipped setting, the price-path rule
  still sells. `data/portfolio/<user>/exit_shadow.jsonl` gains one row for the stock and day:
  legacy EXIT `thesis_break`, evidence HOLD, a disagreement, with the inputs read (no event ids,
  the BUY and its run time, the ₹455 level and the shelf idea it came from).
- **Later:** the Sunday scorecard grades the row 10 and 30 sessions on. If the stock then beat
  the Nifty, keeping it was right and the evidence rule scores a point. When at least 15 such
  disagreements have passed 30 sessions over at least 8 weeks, and the evidence rule was right on
  at least half at both horizons, two Sundays running, the scorecard says so. The owner decides
  whether to switch.

The card's own figure, a path ending at ₹478, would not fire the price-path rule: ₹478 is within
1% of ₹480, the band in which the path counts as flat. The test uses ₹470, and the KT says so.

## What changed

- **The rule** ([advisor.py](../../../../core/portfolio/advisor.py)): `ExitEvidence` (the inputs),
  `case_broken_reasons` (pure, plain-word reasons), `case_broken_fires` (a reason and at least
  `advisor.min_hold_sessions` sessions held) and `decide(exit_rule="legacy"|"evidence",
  evidence=…)`. Under `evidence`, `case_broken` takes `thesis_break`'s place in the EXIT block;
  every other line of `decide` is shared. An unknown `exit_rule` raises.
- **Its inputs, the shadow row, grading and the gate**
  ([exit_shadow.py](../../../../core/portfolio/exit_shadow.py), new):
  - `exit_rule_mode()` reads `advisor.exit_rule` per run (`legacy`, `shadow`, `evidence`; any
    other value reads as `shadow`); `acting_rule()` maps a mode to the rule that acts.
  - `recent_negative_events`, `latest_actionable_verdict` and `invalidation_for` select the
    evidence as of the review day; `exit_evidence` assembles it, pure. `EvidenceReader` reads the
    event store and the score history per holding and the shelf once, naming any source it
    could not read in `gaps`.
  - `shadow_row` builds the comparison row; `grade_disagreements`, `tally`, `gate_look`,
    `recommends`, `scorecard_block`, `scorecard_text` and `previous_week_look` are the grading and
    the gate, pure.
- **The pipeline** ([pipeline.py](../../../../core/portfolio/pipeline.py)): reads the mode once
  per run; outside `legacy` it reads each holding's evidence, decides with the acting rule, then
  decides again with the other rule for the record only, and appends the rows once per user.
  `gated_decide` passes `exit_rule` and `evidence` to every `decide` call. The shelf is loaded
  with every status, for the invalidation level; the buy candidates still come from the active
  ideas only.
- **The store** ([store.py](../../../../core/portfolio/store.py)): `append_exit_shadow_once`
  (keyed by date and symbol under its own lock; a stored row wins) and `load_exit_shadow`.
- **The scorecard** ([results.py](../../../../core/portfolio/results.py)): `build_row` takes the
  shadow rows and last week's look and stores an `exit_rule` block; `scorecard_lines` adds an
  "Exit rule test" line once a row exists; `weekly_scorecard` passes both.
- **Smaller:** `ExitShadowRow` in the portfolio schemas; `ScoreStore.get_records` (full rows,
  so the gate status can be read); `ADVISOR_MIN_HOLD_SESSIONS`; `advisor.exit_rule: shadow` and
  `advisor.min_hold_sessions: 10` in `config.yaml`; plain words for `case_broken` in the
  advisor's and the narrator's trigger maps.

## Design decisions (delegated, recorded)

The owner delegated technical calls (2026-09-28, 2026-10-13). Each has a revisit trigger.

- **D1. Information is the review day's.** An event counts when its IST publication day is after
  the session 5 sessions before the review day and on or before it: for Friday 23 Oct, with the
  20 Oct holiday, 16 Oct to 23 Oct, so the sessions 16, 19, 21, 22 and 23 Oct and the days
  between them. A research run counts when its IST day is on or before the review day. Nothing
  later is read, so a re-run or a backfill cannot use the future. Within the day, the evidence
  rule sees what the 16:30 review and the morning feed wrote, as the price-path rule sees that
  day's thesis review: the two rules get the same day's information. An event published at
  18:30, after the pipeline ran, is in the store only for a later re-run, and by then the first
  row is fixed. *Revisit* if 07-L finds a `case_broken` reason that the first run could not have
  seen.
- **D2. The invalidation test is "at or below".** The card says "below". The entry rule
  (`sizing.entry_check`) refuses a buy "at or below its invalidation level", so the level means
  the same thing to both rules: at ₹455.00 the case is broken; at ₹455.01 it is not. *Revisit*
  if the reviewer prefers the card's wording; it is one character.
- **D3. The invalidation level comes from the stock's shelf idea**: of every idea for the
  symbol, active, promoted (bought) or dropped, the one whose latest deep dive is the newest on
  or before the review day; none when it set no level. PR-005's case will supply its own price.
  A holding bought from a watchlist BUY has no stored idea, so this test cannot fire for it (a
  KT limit).
- **D4. "Over at least 8 weeks" is the span of the counted disagreements' review days** (first to
  last, at least 56 days), not the shadow's age. A single sell-off week could otherwise supply
  all 15. So the first possible pass is about 14–15 weeks after the shadow starts (8 weeks of
  span, 6 for the last to mature, one more weekly look), not the card's 10–12. *Revisit* if the
  owner prefers the shadow's age. (**Restated in rework 1 as D4′**, counted in decisions.)
- **D5. A missing grade counts against the evidence rule**, at that horizon, and stays in the
  count, as PR-002's flags treat missing data. The gate can pass only on graded evidence.
- **D6. A disagreement is "exactly one rule sells the whole position"** (EXIT or SWITCH), and the
  evidence rule is right by the auditor's `is_correct`: its EXIT is right when the excess is
  below 0, its HOLD when it is 0 or more. TRIM and ADD count as keeping. Under the property test
  the two records are identical whenever neither `thesis_break` nor `case_broken` fires, so a
  difference without one selling cannot arise.
- **D7. An unknown `advisor.exit_rule` reads as `shadow`**: the same decisions as `legacy`, and the
  record keeps growing. `decide` itself refuses an unknown rule.
- **D8. Grading runs in the weekly scorecard, not in the auditor's store.** A new lane in
  `advice_outcomes.jsonl` would enter the auditor's headline hit rate (`report.py` reads every
  lane but `ipo`). The scorecard already holds the Nifty series and a cached stock close; the
  row stores the tally and the look, once per week. The cost is a re-fetch of each graded
  disagreement's closes every Sunday (a KT limit). *Revisit* if the weekly job slows.
- **D9. The latest actionable analysis is used whatever its age**, as the card says. A held
  managed stock is analysed at every 16:30 review; a discovery buy only at its re-dives. The row
  records the run time, so 07-L can see an old verdict. *Revisit* if one fires `case_broken`
  long after it was issued.
- **D10. No investment case exists yet**, so any high-materiality negative event about the stock
  counts. PR-005 narrows it to an event that contradicts a pillar.
- **D11. `shock_reforecast` is unchanged, and routed.** It never fires (found on the way, below);
  fixing it changes production exits, which is outside this card. **FIX-015** (P2, 1 point,
  after FIX-014; it moves ahead before any switch): read the `trigger` key, never count a
  `thesis_break` re-forecast, and only a recent one.

## Found on the way (code inspection)

**`shock_reforecast` has never fired.** `build_signals` sets `reforecast_reason` from the cycle's
latest `ReforecastEvent.reason`, and `decide` compares it with `external_shock`, `thesis_break`
and `preopen_shock`. Every writer stores a sentence in `reason` and the key in `trigger`: the daily
review ("External shock on …", "Thesis break on …", "Regime flip on …"), the pre-open check
("pre-open shock: <headline>") and the manual command. A naive fix that matched the key would
also fire on a `thesis_break` re-forecast, which follows the same price-path miss, and would bring
the thesis-review exit back inside the evidence rule. Card: [FIX-015](../stories/FIX-015.md).

## Invariant tests

`tests/unit/test_exit_evidence_pr009.py`, each from the card:

| Card criterion | Test |
|---|---|
| The ₹500 example, both recorded with reasons | `test_the_500_rupee_example_legacy_exits_evidence_holds_both_recorded` |
| Each `case_broken` path on its own fixture and not one unit short | `…a_high_negative_event_in_the_window_fires_and_its_neighbours_do_not` (15 Oct out, 16 Oct in; medium, neutral, positive), `…an_actionable_sell_verdict_fires` (SELL, STRONG SELL), `…the_invalidation_level_fires_at_the_level_and_not_a_paisa_above` |
| A stale or misattributed event (hard review) | `…a_stale_future_misattributed_or_undated_event_never_fires`; for analyses, `…a_verdict_that_is_not_an_actionable_sell_on_the_day_does_not_fire` (NEUTRAL, abstained, INSUFFICIENT DATA, 24 Oct 00:01 IST, superseded by a BUY, another company's; 23 Oct 23:59 IST still counts) |
| Within the minimum holding period only stops fire | `…within_the_minimum_holding_period_only_stops_fire` (9 sessions hold, 10 fire; a stop fires at 1) |
| Property: stops fire exactly when the legacy rule fires them | `test_property_stops_fire_exactly_when_the_legacy_rule_fires_them`: 4,000 seeded random cases; stop, trailing stop, shock and crisis triggers equal; a stop sells under both; with neither reason trigger the records are identical; every branch exercised more than 50 times |
| In `shadow`, decisions and transactions byte-identical to `legacy` | `test_shadow_decisions_and_transactions_are_byte_identical_to_legacy`: the real pipeline, decide and autopilot on a temporary store, run in each mode. `advice_ledger.jsonl` and `transactions.jsonl` are equal byte for byte, and the holdings too. Under `evidence` the sales differ (BBB and CCC instead of AAA and CCC), so the comparison can see a difference |
| Grading uses only prices after the decision date; unmatured is pending | `test_grading_by_hand_and_only_from_prices_up_to_the_horizon` (hand-computed: −4 and +10 points; the stock read only on the 10- and 30-session days; a day early, the 30-session grade is pending and nothing on or after its day is read), `test_a_missing_price_is_ungraded_never_a_result` |
| One shadow row per holding per review date | `test_one_shadow_row_per_holding_per_review_day_however_often_it_runs` (three runs; a repeat with different content is refused) |
| The gate fixture: 30 passes and 10 fails, or the reverse, recommends nothing | `test_a_pass_at_30_with_a_fail_at_10_does_not_recommend_nor_the_reverse` |
| The gate's other conditions (hard review: matured rows only, exited stocks kept) | `…passes_at_exactly_half_at_both_horizons`, `…a_missing_grade_counts_against_the_evidence_rule`, `…too_few_too_close_together_or_one_stock_too_many_never_passes` (14 vs 15; 55 vs 56 days; 5 of 16 vs 5 of 17; 6 of 20 vs 7 of 20), `…only_disagreements_past_30_sessions_count`; the scorecard test grades stocks no longer held |
| The switch is really off by default (hard review) | `test_shadow_is_the_default_and_an_unknown_value_reads_as_shadow` (config as shipped) |
| The scorecard reports the tally; two weeks running | `test_the_scorecard_shows_the_tally_and_recommends_only_on_two_passing_weeks` (the exact line; a skipped week breaks the run), `test_a_scorecard_without_shadow_rows_has_no_exit_line` |
| A failing source never changes the acting decision | `test_a_failing_evidence_read_never_changes_the_acting_decision`, `test_an_unreadable_source_is_named_not_silent` |

**Mutants:** `analysis_data/pr009/mutants.py` applies each of 36 one-rule mutants to the real file,
runs the story file with `-x`, and restores the file, checking its SHA-256 afterwards. **36 of 36
caught** (`mutants_run1.txt`, ignored). They cover the minimum hold (off by one, removed), the
invalidation comparison, `thesis_break` leaking into the evidence rule, STRONG SELL, a stop that
differs by rule, the event window (one session long, calendar days, future, any symbol,
medium), the research run (future, abstained), a later dive's level, the grade's direction, the
entry price and the pending boundary, every gate condition and its boundary (half, 30%, 15, 8
weeks, two weeks, the previous week's key, a missing grade counted as right, pending rows
counted), non-disagreements graded, rows after the look, the mode mapping both ways, the
store's dedupe, the shadow decision without evidence, the session count, the disagreement test,
and the scorecard dropping last week's look.

**Existing tests:** none changed. The 840 tests of the advisor, pipeline, autopilot, data-gate,
scorecard, idea-supply, sizing, Nifty, import-boundary and scheduler-hook files pass with the
change; the pipeline tests that patch `gated_decide` now also exercise the shadow path, since
`shadow` is the default.

## Commands and environment

`.stockai` venv (Python 3.13) on Windows; the suite's hermetic boundary (`tests/hermetic.py`)
refuses network, the checkout's `data/` and app environment variables.

| Command | Result |
|---|---|
| `pytest tests/unit/test_exit_evidence_pr009.py` | 26 passed (13 s) |
| `pytest` on the 10 related files (advisor, portfolio pipeline, autopilot pipeline, SA-003 portfolio gate, PR-002 scorecard, PR-004 idea supply, SA-050 sizing, SA-051 Nifty, Atlas import boundary, scheduler portfolio hook) | 840 passed, before the story file existed; 866 passed (97 s) with it |
| `python analysis_data/pr009/mutants.py` | 36 of 36 caught |
| `pytest tests` (full suite) | **5,698 passed, 12 skipped, 1 xfailed, 0 failed** in 23 min 20 s (5,672 before, plus the 26 new) |
| `python scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 56 pages (was 54), no overflow; **exactly 1 error**: "KT links core/portfolio/exit_shadow.py, which is absent at its declared revision ffa012b40468". It is expected: the header names a commit without the file, and the commit-time header bump clears it, as with PR-006's jobs. |
| `find data -newer analysis_data/pr009/suite_start.marker` after the suite | no file: the checkout's runtime data is unchanged |

## Documentation

- **KT** ([TECHNICAL_DESIGN.md](../../../TECHNICAL_DESIGN.md)), as current design:
  - section 3: the `advisor.exit_rule` row in the configuration table; `exit_shadow.jsonl` in the
    portfolio records row;
  - section 4: the evidence exit rule reads the feed's high negative events, in shadow;
  - section 6: "Two exit rules" replaces the `thesis_break` paragraph and its **Planned** line:
    both rules, the ₹500 example (with the 1% band), the modes, grading, the gate table, why two
    horizons (cited from the product results review), the post-switch retirement as
    **Planned**, and four limits (`shock_reforecast` → FIX-015; watchlist buys without a level;
    the tax softening still reads the thesis review; the weekly re-fetch);
  - section 7: the "Exit rule test" line in the scorecard table;
  - section 11: the "Sell on evidence" bullet now says what runs and what is the owner's;
  - section 12: a FIX-015 row (Open). PR-009's row stays Open until the commit.
- **PDF** rebuilt, 56 pages.
- **CODEBASE.md:** the advisor row gains `decide(exit_rule=, evidence=)`; a new row for
  `exit_shadow.py`; `exit_shadow.jsonl` in the per-user folder row.
- **Guide:** 07-K (the four prepared holdings in shadow, a re-run, evidence mode and 9 sessions),
  07-L (the first five production review days) and 09-H (the gate counted by hand, both
  one-horizon failures, two weeks running, the 31% stock). Each says "PR-009: implemented
  2026-10-23; fresh review pending"; HT-07 and HT-09 list PR-009.
- **PI README:** FIX-015's row (order 24) and paragraph. **Card:** [FIX-015](../stories/FIX-015.md).

## Manifest and digest

- **Review input:** [PR-009-manifest.json](PR-009-manifest.json), 17 files. The SHA-256 of its
  LF bytes is **`5afb4aa1028bccc2b6d8fb9744879c0e4e2b7423eec10bf2def89b1c79df370c`**;
  `kt_manifest.py verify` gives 0 mismatches.
  - Code (10): `config.yaml`, `core/portfolio/advisor.py`, `core/portfolio/exit_shadow.py` (new),
    `core/portfolio/narrator.py`, `core/portfolio/pipeline.py`, `core/portfolio/results.py`,
    `core/portfolio/store.py`, `services/data/stores/score_store.py`,
    `src/backend/shared/config/settings/base.py`, `src/backend/shared/schemas/portfolio.py`.
  - Tests (1, new): `tests/unit/test_exit_evidence_pr009.py`.
  - Docs (6): the KT and its PDF, CODEBASE, the testing guide, the PI README and the FIX-015 card
    (new).
  - Excluded: STATE, HANDOFF and this receipt (bookkeeping); the owner's line in
    `docs/README.md`.
- **Diff digest:** **`9ef8fdbae5415cfbf9e7be7b68b2a98d17a61ba3c9f65fe7c96fa9e6aa5c4e5d`**,
  116,287 bytes over 16 paths (every manifest path except the PDF), by
  `analysis_data/pr009/digest.py`. It checks that HEAD is `d7c1411`, then for each path, sorted:
  `git diff HEAD -- PATH` for the 13 tracked text paths, `git diff --no-index /dev/null PATH` for the
  3 new files (`exit_shadow.py`, the test file, the FIX-015 card). Run twice after
  the full suite: the same digest. The diff itself is `analysis_data/pr009/pr009.diff` (ignored).

## Self-review

Same-conversation self-review; it does not replace the fresh review.

- Found by the story's own tests and fixed: the byte-identity test first compared the whole
  portfolio file, whose `updated_at` is the save's wall-clock time; it now compares the advice
  and transaction ledgers byte for byte and the portfolio without that stamp.
- Found while writing the gate tests: a 30% boundary and a row dated after the look were not
  pinned; both are now (mutants M20, M28).
- Read again: the evidence is read before the acting decision, and every read is inside its own
  handler. If evidence cannot be read under `evidence`, `case_broken` cannot fire, so the
  failure never sells by mistake; only the stops then protect the holding, and the row names
  the gap. The second `gated_decide` uses the same inputs and is never executed or narrated.
  No user id or price is written anywhere but the user's own folder.
- Checked: in the older pipeline tests (`gated_decide` and the store mocked), the shadow rows go
  to the mocked store. `EvidenceReader` constructs `ScoreStore()` as `buy_candidates` does, which
  creates its table if missing: under the hermetic boundary that is `data/scores.db` inside the
  test's own sandbox directory, never the checkout. In production the database exists, and the
  statement is a no-op.

## Limits and follow-ups

- **`shock_reforecast` never fires** under either rule → FIX-015 (above).
- **A watchlist buy has no invalidation level** (D3); PR-005's case supplies one.
- **Any high negative event counts** until PR-005's pillars exist (D10). The classifier's
  materiality decides; 07-L samples it.
- **The tax softening** (TRIM to HOLD before 12 months) still reads the thesis review under both
  rules; it is not an exit.
- **The weekly re-fetch** of graded closes (D8).
- **After a switch:** the price-path verdict keeps being recorded under `evidence`; the
  retirement of the thesis-review exit one month later is a later change (the card's rollout).

## For the owner

- **Nothing changes in what the portfolio does.** The shipped setting is `shadow`: the same
  sales as today, and a record of what the evidence rule would have done.
- **The Sunday email gains one line**, "Exit rule test", once the first row exists: how often the
  two rules disagreed, how often the evidence rule was right at 10 and 30 sessions, and the gate.
  Expect "not yet" for about three to four months (D4; rework 1's D4′ says four to five).
- **When it says "passed two weeks running"**, the decision is yours: set `advisor.exit_rule:
  evidence` in `config.yaml` (a reviewed change and a deploy). `legacy` stops the comparison;
  it is the rollback.
- **Before any switch, FIX-015** should be done, so the shock exit works and cannot reopen the
  price-path exit.
