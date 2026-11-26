# PR-047 — fresh review, step 2 (option A)

**Story:** [PR-047](../stories/PR-047.md): buy what the analysis itself would buy. Implementation
receipt: [PR-047-implementation.md](PR-047-implementation.md). Step 1 (the measure for option B
and the staged entry) is [its own receipt](PR-047-step1.md); its read is `PR-047-S1`.

**Review context: fresh session.** Autopilot `1126-2234-p8` (Opus), on the code-server, 26 Nov
2026 from about 22:35 IST, a new conversation opened with "continue". It did not take part in the
implementation (`1126-1852-p6`, `1126-1901-p7`) and read none of those chats; it read the card,
the receipt, the diff and the code, and wrote its own cases.

**Verdict: ACCEPTED** for revision `8541b37`. Merged into `main` as **`6eca615`**, whose tree
outside `docs/planning/` is byte-identical to `8541b37` (`git diff 8541b37 6eca615 -- .
':!docs/planning'` is empty). Nothing was read in production, pushed, deployed, run or sent.

## Input verified

- Baseline `f06e3dc`; revision `8541b37` on `story/PR-047` (`f69e2a5`, `8541b37`).
- `git diff f06e3dc 8541b37 | sha256sum` =
  `301a7715869216b414b0ed8e0367ecb1b75315d573f0e234807d790e36035fe4`, as the receipt says
  (33 files, 859 insertions, 88 deletions).
- `scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-047-manifest.json
  --rev 8541b37`: 33 files, mismatches [], review-input SHA-256 `cd10c97c…5913`, as recorded.
- `scripts/docs/check_kt_docs.py` on `8541b37`: errors [].

## Contract checked

Option A (the owner, 21 Nov): a buy needs the composite's band **and** the analysis's own model to
say BUY or STRONG BUY, at every door; it may only refuse, never add a buy.

Traced in the code at `8541b37` [code inspection]:

1. **Issue time.** `SignalAggregator.run` sets `report.model_verdict` from the parsed reply
   before the bind, in the same call that writes the shadow row; both orchestrator paths (sync
   and async `analyse`) go through it, so every analysis, dive and score-history row carries it.
   The decision gate changes `verdict` only (to INSUFFICIENT DATA), never `final_score` or
   `model_verdict`; such an idea is refused by the band check first. `report_json` keeps it
   (`ScoreStore.save` stores `model_dump_json()`).
2. **One rule.** `shelf.verdict_wait` reads the band exactly as FIX-029 did (`band_verdict`) and
   then the model's (`plain_verdict`): narrower by construction. Its callers: the shelf's add and
   re-dive, `buy_candidates`, a SWITCH leg (`autopilot._execute_buys`) and deployment
   (`_deploy_check`). The watchlist door (`watchlist_idea`) adds the same test on the stored
   report. Every door reads ideas that passed `buy_candidates`, which reads the shelf through
   `with_model_verdicts`, so the SWITCH and deployment re-checks see the same filled verdict.
3. **Legacy ideas.** `with_model_verdicts` fills only discovery ideas with no model verdict, from
   rows of their symbol, IST dive day or the next, score to 4 decimals and band, all agreeing; an
   unreadable log or no row leaves "" (refused). `verify_model_verdicts` (weekly, after FIX-033's
   check, before `redive_due`) stamps a BUY, drops any other verdict, leaves the rest for a
   re-dive first. Each weekly step loads and saves the shelf itself, so no stale copy undoes a
   drop.
4. **Consequential readers of a drop.** An idea the weekly check drops may be of a held stock
   (TVSMOTOR is held since 16 Nov). `exit_shadow.invalidation_for` reads ideas of any status, so
   the holding keeps its invalidation level (RV6); nothing sells on a dropped idea. `/analyse`
   now returns `model_verdict` in its JSON; it already returned the gate's `withheld_verdict`, so
   nothing new in kind reaches a member.
5. **Rollback.** `ShelfIdea`, `DeepDiveResult` and `FinalReport` use pydantic's default (extra
   fields ignored): an older build reads the new `shelf.json` and report rows.
6. **Clocks.** The weekly run dates dives with `date.today()` (`run_discovery_cycle()`), the
   container's clock. A UTC date is the IST date or the day before, never after, so "the IST day
   or the next" covers both (RV2).

## Independent adversarial examples

Reviewer file `analysis_data/pr047_review/test_review_pr047.py` (ignored), run from a detached
worktree's `tests/unit/`; every figure worked by hand in its docstring.

| Case | What | Result at `8541b37` | At `f06e3dc` |
|---|---|---|---|
| RV1 | NITIN dived 14 Nov, 0.66, band BUY, model NEUTRAL; the same day's paper review at 0.64 says BUY, Monday's at 0.66 says BUY: read NEUTRAL, refused with the card's words | pass | n/a (no legacy read) |
| RV2 | A dive dated 13 Nov by a UTC clock (Sat 05:15 IST) finds its row; a row two IST days on is not its row | pass | n/a |
| RV3 | Two rows of the dive at the same score and band that disagree: refused ("kept no verdict of the model's own"), left unverified by the weekly check, re-dived before a 42-day stale idea | pass | n/a |
| RV4 | The real daily pipeline, ₹10 L cash: TVS (band BUY, model NEUTRAL, 0.80) and GOOD (both BUY, 0.70). 80% × ₹10,00,000 / 12 = ₹66,666.67 at ₹1,000: GOOD 66 shares, TVS nothing | pass | **fails**: TVS 66 and GOOD 66 bought (the original defect) |
| RV5 | "NOT BUY", "BUY?", "BUYBACK", "HOLD", "Accumulate", "BUY / NEUTRAL", "INSUFFICIENT DATA" refused; "Strong_Buy", "  buy ", "STRONG   BUY" taken | pass (10) | the 7 refusals fail |
| RV6 | The weekly check drops a held stock's legacy idea (model NEUTRAL); its invalidation level ₹3,900 is still read, from 14 Nov's dive | pass | n/a |

**Reviewer mutants** (chosen here, not the implementer's 17), each run against both files:
M-a the legacy read takes the first matching row instead of requiring agreement (caught by RV3
and the story's A4); M-b no next-day window (caught by RV2 and A4); M-c an unknown model verdict
passes (caught by RV3, A1, A3, A4 and the card's words: 10 failed). 3 of 3.

**The story's tests** derive their expectations by hand (the `TAKEN` table of 8 pairs, 66 shares
from 80% of ₹10 L / 12, the TVSMOTOR words), drive the real aggregator, deep dive, dive record,
score store, weekly cycle and daily pipeline, and mock only the model reply, prices and stores
under `tmp_path`; no real transport. The older fixtures' change (`model_verdict="BUY"` beside each
literal `verdict="BUY"`) changes no expected figure.

## Findings

| # | Severity | Where | Finding | Disposition |
|---|---|---|---|---|
| L1 | low (pre-existing, scope) | `core/portfolio/advisor.py:823-838` | A top-up (ADD) of a holding reads neither verdict, the band (FIX-029) nor the model's: it follows the forecast path (envelope UP, regime, weight under the cap, 7-day direction accuracy). So TVSMOTOR, held since 16 Nov with its dive's model at NEUTRAL, can still be added to. Not introduced here: the card's options, examples and owner decision are about new positions, and the receipt and KT section 6 say so | BACKLOG **B-42**, with its trigger; for `PR-014-R1` |
| L2 | low (inference) | `core/discovery/shelf.py` `model_verdict_from_shadow` | "Cannot be told" is likelier than the receipt's limitation 1 suggests: Saturday's paper reviews (and a new month's envelope) analyse a newly shelved idea again the same day, so many legacy ideas have two or three rows on their dive day. A second row at the same score and band with another model verdict refuses the idea until its re-dive. It fails closed (a buy delayed to the first Saturday after the deploy, re-dived first), never a buy against the rule | `PR-047-W1` counts `unverified` and the re-dive slots they take |
| N1 | nit | `core/portfolio/pipeline.py:218-233` | Were `with_model_verdicts` itself to raise, the shelf block's handler logs at DEBUG and no shelf idea is offered that day. Reader faults are already caught per day inside it, so only an import fault reaches the handler, which predates PR-047 | none |

No critical, high or medium finding. No acceptance criterion unmet.

## Acceptance checklist

- [x] Every buy door needs both verdicts: the shelf's add, a re-dive, the list, a SWITCH leg,
  deployment, the watchlist (story A1; RV4 through the real pipeline).
- [x] It can only refuse (A2 over 2,000 random ideas; `band_verdict` unchanged from FIX-029).
- [x] Issue time: the same report's model verdict, through the real aggregator to the shelf file,
  the dive record and the score history (A3).
- [x] Ideas shelved before PR-047 are read from their own dive's row and fail closed (A4, RV1 to
  RV3, RV6).
- [x] Tests fail for the original defect (RV4 and RV5 on `f06e3dc`).
- [x] Documentation: KT sections 3, 4 (step 6), 6 and 8; `docs/AUTOPILOT_GUIDE.md`;
  `CODEBASE.md`; human case 07-W; KT section 12 marked Done by this review. PDF not rebuilt
  (AGENTS.md).

## Commands and results (code-server, `.stockai`, Python 3.13.5)

- Detached worktree at `8541b37`: `pytest -q tests/unit/test_model_verdict_pr047.py`: 168 passed
  (4.1 s). Reviewer file: 15 passed (4.6 s). With each reviewer mutant: 1-2 failed.
- Detached worktree at `f06e3dc`: reviewer RV4 and RV5: RV4 and the 7 refusals of RV5 failed.
- Full suite through `scripts/ci/guarded_suite.py` on **`6eca615`** (`main`, the merge), 26 Nov,
  22:43–22:52 IST: main step 7,163 passed / 5 skipped / 1 xfailed (5 min 26 s), browser step 58
  passed (3 min 13 s), 0 failed, verdict PASS; anon 1,354 MB at the start, peak 2,108 MB (the
  browser step; the guard stops at 2,400), 1,339 MB after; nothing left running.
- Not exercised: production (read only at the owner's word); the real model's wording on new
  analyses (the prompt asks for the five words; B-32's 60 days showed only those); how many legacy
  ideas the log can tell (`PR-047-W1`).

## Production

`production_verification`: `pending_deployment` (merged, not pushed; the next push window is
00:10–06:20 IST). After the deploy, **`PR-047-W1`** (STATE `pending_production_checks`): the first
16:30 review buys no idea whose model verdict, on the idea or in `verdict_shadow.jsonl` for its
dive, is not a BUY, and names any refused; the first Saturday run reports
`hygiene.model_verdicts` (TVSMOTOR's idea, if still active, dropped), the shelf's
`not_buy_model`, and the re-dive slots unverified ideas took (L2). `PR-047-S1` (step 1's read)
is unchanged: at the owner's word from 1 Dec.

## Decision

**ACCEPTED**: PR-047 is `done` (code); production verification separate. Follow-ups: BACKLOG
B-42 (L1); L2 in `PR-047-W1`; N1 none. Next ready story: **OPS-005** (light).
