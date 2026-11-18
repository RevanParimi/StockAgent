# PR-005 — implementation receipt

**Story:** [PR-005](../stories/PR-005.md): an investment case for every position. Owner request of
11 Oct 2026 ("what do you say when you buy a stock or sell it"). Profit-path steps: **hold** and
**sell** (the case is the reason the evidence exit rule keeps or sells a holding).

**Lane: decision path.** Reason: the case's invalidation price is what the evidence exit rule
sells on, and RR-L1 changes when the shelf idea's level may be used (the card; AGENTS.md step 4).
**Status after this phase: `review_required`.** The next fresh conversation performs the hard
review from `REVIEW.md`; this phase's self-review does not count as it.

## Phase

- **Implementation** (autopilot `1118-0904-p6`, code-server). Started Wed 18 Nov 2026 about
  09:04 IST outside a push window, interrupted, and finished Thu 19 Nov from about 04:58 IST.
  Baseline `f5eefa3` (`main`, nine commits ahead of `origin/main` `6e1962f`). Committed
  **`4407b13` on `story/PR-005`**, which only a fresh review's acceptance merges into `main`.
  Production was not read; nothing pushed, deployed, run or sent; no model was called.
- The window's own work (PR-015's switch, the push, PR-036's deposit) was left to its own
  phase, as HANDOFF orders it: one phase per conversation.

## What was built (`f5eefa3..4407b13`)

**The case** (`core/portfolio/cases.py`, schema `src/backend/shared/schemas/cases.py`). Pillars
(2 to 4, each citing inputs), the expectation, what would prove it wrong (a price and business
conditions), what to watch, a one-line case, `written` (`at_purchase` / `after_purchase`),
`author` (`model` / `deterministic`) with `fallback_reason`, `buy_path`, `created_at`, `as_of`,
the input manifest (ids, kinds, when known; no text), `source_run_id`, `version`, `change`,
`events_read`.

**Where it is written.** A SWITCH buy leg and an idle-cash deployment buy that open a position:
`execute_advice` → `write_for_trades`, after the trades are saved and the lock released, with
the shelf index's ideas (the pipeline adds every stored idea). A manual add that opens a
position: the route schedules `write_for_buy` after the response. An ADD, a buy merged into an
older holding and a sale write none. A failure never undoes a trade (`write_for_buy` never
raises). `advisor.case_write: false` writes none.

**Inputs and the clock (FIX-004).** `as_of` is the buy session's 15:30 close for a SWITCH or
deployment buy (the clock the buy was decided on, FIX-031), and the writing time for a manual
add or a backfill. Each input was known before it: A1 the newest actionable or degraded analysis
(score history), F1 that analysis's own fundamentals reading (no live fetch, so it is dated by
the run), S1 the shelf idea decided before it, D1.. the dossier's open guidance dated before its
day (undated catalysts only when the whole dossier was last updated before that day), E1.. the
10 newest medium/high events of 60 days.

**The figure check** (`check_model_case`). Every figure of an evidence fact must be a figure of
the input it cites, with the same unit; every other figure one of the bundle's (or the stock and
buy date it was told). Figures are compared as numbers, commas ignored, digits inside words
counted ("FY27" has 27), units normalised (crore = Cr, per cent = %; "x" is no unit). No rounding,
no conversion. A broken rule, malformed JSON or a failed call stores `deterministic_case`: the
shelf idea's thesis (else the analysis's) first sentence, word for word; its deep dive's
conviction and verdict as the evidence; the analysis's drivers as more evidence and its risks as
the business conditions. No thesis: "No thesis was written; bought on its deep dive's conviction
and verdict." Neither an idea nor an analysis: no case.

**Prices are code's.** `purchase_invalidation`: the idea's level through `level_in_basis`'s
dive-to-buy part (NSE's list read for the buy, `_corp_record`), then the window: above the stop
price on the purchase day and at or below `entry × (1 − 1.5 × ATR%)`; ATR and stop as the advisor
computes them (`purchase_stop`: `atr_pct` over the history up to the buy day, `compute_stop_pct`
with the pipeline's mid bucket). Outside it, no price and a gap naming the side; an unknown ATR,
no price. The analysis's price target through the same conversion from its run day; horizon =
quarters × 3. On review days `level_after_buy` divides only by the holding's applied bonuses and
splits after the buy; NSE rows after the buy no ratio converts (or unread), an applied demerger or
relisting, and a registry break leave it unused.

**The evidence rule** (`exit_shadow.exit_evidence(case=)`, `EvidenceReader(cases=)`). With a case
(the newest version written before the review session's close), its price; without one, the
shelf's level as before. A case with no price is not replaced by the shelf's level. The evidence
records `case_version` and `challenged_pillars`.

**RR-L1** (`level_in_basis`): from the dive day to the review day, a row in
`ActionRecord.basis_changes`, an applied `demerger`/`relisting` after the buy, or `registry_break`
leaves the level unused with a gap. **T1** pinned in `test_exit_evidence_pr009.py`.

**Pillars** (`review_pillars`, a pipeline step after the trades, per holding). Events published
in `[as_of, review close)`, each read once (`events_read`): a medium/high negative event in a
watched category challenges that pillar, citing it; a results event re-checks every pillar
(negative: all challenged; otherwise `last_checked`). Each change is a new version; nothing is
edited.

**API and backfill.** `GET /portfolio/cases` (newest version of each), `?symbol=` (every
version); the caller's own store only; a symbol outside `[A-Z0-9&_.-]{1,20}` is a 422.
`scripts/backfill_cases.py`: dry run by default; `--apply` writes `after_purchase` cases.

## Decisions I took (delegated calls)

1. **The filing leg of `case_broken` is not narrowed to pillar-contradicting filings.** The
   advisor's comment anticipated it; the card's criteria do not ask for it, and the roadmap's
   rule 2 says a report before a rule. A qualifying NSE filing still sells; narrowing waits for
   PR-013's losses by exit reason. Challenged pillars are recorded beside the evidence.
2. **A case decides the price, the shelf only without one**, so a level the window refused is
   never used through the back door.
3. **`at_purchase` only when a buy path writes on the buy's own IST day**; a catch-up run, a
   past-dated manual add and every backfill are `after_purchase`.
4. **Fundamentals come from the analysis's own reading**, not a live fetch after the close.
5. **No calendar watch item**: the pipeline's events calendar is fetched after the 15:30 clock
   and holds only already-held stocks, so it could never be an input of an at-purchase case.
6. **The stop uses the pipeline's mid bucket** (it reads no market cap), so the window matches
   the stop the advisor will apply.
7. **Case writing is off in tests by default** (`tests/conftest.py` `_no_case_writes`), as the
   other side-effecting writers are; PR-005's tests switch it on with stubs.
8. **The KT names `core/portfolio/cases.py` as code, not a link**: the docs check requires a
   linked file to exist at the header's revision, which is bumped after the merge.

## Tests

- **New `tests/unit/test_investment_case_pr005.py`, 42 tests**, expected values worked by hand
  in each docstring: figures and units; the fixture case holds only bundle figures (a property
  over every text field, and each fact against its cited input); ten rule-breaking stubs
  (invented 21%, rounded 18%, ₹1,200 for Rs 1,200 Cr, another input's figure, unknown ref, no
  evidence, unknown category, five pillars, not JSON, not an object) and one that keeps the
  rules with "18.0%" and "18.40%"; a failed call and the model off; no thesis; nothing to build
  from; issue time (the 16:30 analysis, the 16:10 filing, the 24 Oct guidance and re-dive are not
  inputs) and a 203-point property over publication times including exactly 15:30; the window
  (₹470 and ₹485 used; ₹455, ₹460, ₹490 and ₹485.01 not; unknown ATR); RR-L1 for a demerger, a
  capital reduction and a rights issue with a neighbour one day before the dive; the shelf rule
  refusing the same rows and a registry break; a split before or on the buy day applied once and
  never again; a bonus after the buy dividing once; the evidence rule reading the case, and a
  case with no price not falling back; pillar challenge by a news rating cut (never sells), read
  once; results re-checks; the purchase stop ignoring later rows; a SWITCH buy through
  `execute_advice` (one v1 case, a re-run writes none, the writer called again writes none); a
  deployment buy through `execute_advice`; ADD, a buy into an older holding and a sale write
  none; the manual add route (one case, a retry and a second add write none; another member
  reads none; a path-like symbol is a 422); no analysis or idea writes none; backfill (dry run,
  `after_purchase`, second run); a late buy-path case; case writing off; the store taking each
  version once and only growing.
- **`test_exit_evidence_pr009.py`**: T1 (a split ex on the buy day divides ₹900 to ₹180).
- **Mutants: 13 of 13 caught** (buy-day split; RR-L1 basis change; RR-L1 registry; both window
  edges; units ignored; an analysis after `as_of`; an event at exactly `as_of`; read once; the
  backfill label; the shelf fallback; the store's version check; a fact checked against the
  whole bundle). Script kept in the session's scratchpad, not tracked.
- **Related suites:** 883 passed (PR-005, PR-009, FIX-016, SA-049, the SWITCH executor, the
  pipeline, SA-051, FIX-032, FIX-029).
- **Full suite on `4407b13`** (detached worktree, without `-n`): 6,852 passed / 12 skipped / 1 xfailed / 0 failed (6m28s).
- **Guards:** `check_broad_except` OK (148 grandfathered); `check_kt_docs` errors `[]`.

## Manifest

Diff `f5eefa3..4407b13`: `git diff f5eefa3 4407b13 | sha256sum` = `ef61b3609e06b9cb…`, 18 files,
+2206/−45. File digests at `4407b13` (`git show 4407b13:<path> | sha256sum`, first 12):
`core/portfolio/cases.py` `deff06f32e1c`; `src/backend/shared/schemas/cases.py` `b5ef80d504eb`;
`core/config/prompts/shared/investment_case.py` `d5ae3c15a995`; `core/portfolio/exit_shadow.py`
`3b1905e844b8`; `core/portfolio/advisor.py` `c8f9bf4f6d16`; `core/portfolio/autopilot.py`
`c93632008909`; `core/portfolio/pipeline.py` `03207be6e168`;
`services/api/routes/portfolio_api.py` `d172ce2fbaf9`; `base.py` `b8520719382e`; `config.yaml`
`0475fa46d1a6`; `scripts/backfill_cases.py` `55d33b21f0d2`; `tests/conftest.py` `faae6f5f6af2`;
`test_investment_case_pr005.py` `3937682101fc`; `test_exit_evidence_pr009.py` `3f61292bed89`;
`TECHNICAL_DESIGN.md` `acd13273f293`; `CODEBASE.md` `7df718e47962`; `AUTOPILOT_GUIDE.md`
`5255d3b7f679`; `TEAM_TESTING_GUIDE.md` `91520893e378`.

Living documents: KT sections 3 (persistent records), 4 (company events), 6 (intro, the third
reason, the filing paragraph, the price basis, two limits, new "The investment case") and 11;
CODEBASE (module row, API row); AUTOPILOT_GUIDE (API row); testing case 07-U.

## For the fresh review (the card's hard review, and what the self-review saw)

- **Written after the fact, looking original?** `created_at`, `as_of` and `written` are code's;
  inputs are filtered by `as_of`; the manifest records when each was known. A reviewer may ask
  whether a manual add's `as_of` (writing time) should be the buy session's close instead.
- **Laundering through rounding or units?** Exact numeric match with the unit after the figure.
  Known limits [code]: a unit written before the figure ("Rs", "₹") is not read, so "₹1,200"
  and "1,200 shares" are the same figure; signs and words ("rose" / "fell") are not checked.
- **An honest fallback without a thesis?** Yes, pinned.
- **Cost** [inference]: one reasoning-tier call per opening buy, at most 5 a day (PR-036);
  the model's price is not measured here.
- **Self-review findings fixed before the commit:** the case store first followed the global
  data folder, not the portfolio's (tests would have written to the real folder); the manual
  add read the shelf eagerly; a dead calendar watch item; an unreadable run time in the target
  conversion.

## Rollout and rollback

Cases are written from the next buy after the merge and deploy. The backfill runs once, at the
owner's word: `railway ssh "cd /app && python -B scripts/backfill_cases.py"` (dry run), then
`--apply` (one model call per holding). Rollback: `advisor.case_write: false` (stored cases
stay as history; the evidence rule then reads the shelf's level for holdings without a case and
the stored case for the rest).
