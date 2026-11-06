# FIX-025 — fresh review receipt

**Story:** [FIX-025](../stories/FIX-025.md): deployment follows the money and the ideas; a top-up checks
NSE's report too. **Implementation receipt:** [FIX-025-implementation](FIX-025-implementation.md).

**Context:** fresh-session review (6 Nov 2026, about 20:02–21:12 IST, session `stockagent-main-02`
[191c47]). The conversation opened with a read-only question about the task board, then "continue". The
implementation session's chat was not read. Peers (`-31`, `-64`, `-77`) were idle throughout.

**Verdict: ACCEPTED**, for the reviewed input below. Every acceptance item is met and nothing is critical
or high. Three medium findings and two low ones go to a new card, [FIX-029](../stories/FIX-029.md); none
comes from FIX-025's change. Two other lows go to PR-007, and one docs correction is a commit-time edit.
Nothing was committed, pushed, deployed or configured, and no production state, log or network was read.

## Reviewed input

Verified at the start and the end (`analysis_data/fix025_review/rv_digest.py`, the implementer's recipe
writing into the review folder; start.diff and end.diff byte-identical):

- Baseline: HEAD `0f0d7f6`, nothing staged.
- Manifest [FIX-025-manifest.json](FIX-025-manifest.json) `33b944df`, 33 files, `kt_manifest.py verify` 0
  mismatches.
- Diff `dabc7e34`, 245,518 B, 32 paths. The end tree differs from the receipt's `4ac1d131` only in STATE,
  HANDOFF and the implementation receipt, which were written after it; this review adds its own
  bookkeeping files. The diff over the manifest's paths does not change.

## Contract checked

- **D1, D2.** The target is the regime's share. A position asks for the NORMAL share of equity ÷
  `target_holdings`, in every regime, inside the caps and the cash floor. A buy passes the target by at
  most one position. The soft minimum never buys. Settings and per-portfolio overrides change behaviour
  with no code change.
- **D3.** A top-up into a stock under a measure, not active, unlisted, or with no report from the last 7
  days buys nothing, keeps the shares and says why, with the cooldown untouched.
- **D4.** A stock the autopilot sold since its latest dive goes first on Saturday, inside the budget, and
  can be bought again by the first run that may use the new dive.
- **F25-D14.** A stock sold with no idea left takes its screen rank once no portfolio holds it.
- **Routed.** FIX-024's L2, T1, T2 and T3.

## Independent adversarial examples

Reviewer cases: `analysis_data/fix025_review/test_rv_fix025.py`, **67 passed + 10 strict xfail**. Each xfail was run with
`--runxfail` and fails at its intended assertion. Expected values are worked by hand in each docstring.

- **RV1, the money, an example the story file lacks.** ₹30 L, all cash, RISK_OFF, five pharma ideas at ₹500
  then six others at ₹2,000. Target ₹15 L; a position asks for ₹2 L. Four pharma buys of 400 shares, a fifth
  of 200 because the sector has ₹1 L left of its 30% cap, then three of 100 shares reach exactly ₹15 L and
  stop. Passed to the rupee.
- **RV1b.** A position asking for 20% takes the 10% cap: eight buys of ₹1 L reach the ₹8 L target.
- **RV2, a property run the story's lacks.** 60 random books through the real executor, with top-ups, random
  measures and regimes, replayed from the ledger by the test alone. No stock under a measure gets a BUY of any
  kind; no cap is passed; cash stays at its floor; every deployment buy starts below the target; nothing new
  in a crisis.
- **RV3 (M1).** A holding with no entry today, an older NORMAL, and RISK_OFF or MACRO_CRISIS recorded today:
  the real `build_signals` and `decide` give ADD.
- **RV4 (M4), RV12 and RV12b (M3).** See the findings. I first read RV4 as a plain re-buy and then traced where
  the newest analysis comes from: the review re-runs it at about 16:35 IST unless the forecast was right
  within 0.5%. That made RV4 narrower than I first wrote and exposed M3.
- **RV5, RV5b (M2).** The real `decide` names a stock sold the day before as the SWITCH destination, and the
  real executor buys it.
- **RV6, RV7 (L1).** A shelf idea, and a re-dive, with verdict NEUTRAL or SELL at conviction 0.70.
- **RV8.** The real reader raises inside the lock: the top-up is refused with its reason, and the same run's
  EXIT stands.
- **RV9 (L2).** The real pipeline twice for one day.
- **RV10, RV10b.** A sale stamped 00:30 IST belongs to the next IST day; a hand sale keeps its own date; a TRIM
  is no exit; the later sale wins across portfolios.
- **RV11.** A dive of a stock managed under "pharma" whose dive key is "generic": the idea is offered, held
  and promoted under "pharma".

**Consumers traced.** `Target.notes`, `min_invested_inr` and the `position_inr` property have no other reader
(grep over `core`, `src`, `services`, `scripts`). The real screen has no managed filter, so D14's flag does
reach it. A sale's date is compared with a dive in `_last_sales` and `autopilot_sales` only. `report` is per
user, so one portfolio's skips do not reach another's digest. An analysis of a managed stock writes to the score
history and the run logs, and opens a prediction store only outside observe mode (I1).

## Reviewer mutants

`analysis_data/fix025_review/rv_mutants.py`: **40 of 40 caught by the tracked tests**, none of them the
implementer's: 36 on the story's code and 4 on the routed T1, T2 and T3 (`mutants.txt`, `mutants2.txt`). They
ran in memory, so no file was edited, and each counts only on a reported test failure. I did not re-run the
implementer's in-place mutants.

## Findings

| ID | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| M1 | **Medium, pre-existing**, confirmed locally | `advisor.py:258-261`, read at 574 and 601 | Own review wrote nothing; older entry NORMAL; another review recorded MACRO_CRISIS today. **Observed (RV3):** ADD; the crisis exit reads NORMAL too. **Expected:** no ADD. FIX-025's L2 asks for the label and acts only on None. | A top-up of 25% on a crisis day. Live with the switch off. Frequency not measured. | [FIX-029](../stories/FIX-029.md) |
| M2 | **Medium, pre-existing**, confirmed locally | `autopilot.py:277` (leg), `advisor.py:382`; the rule is only at `autopilot.py:447` | X sold Tuesday, no new dive; Y exits Wednesday. **Observed (RV5, RV5b):** the real advisor names X and the executor buys it. **Expected by the rule:** X is no destination. | A round trip in a day, paying costs twice, on the analysis the sale overruled. Live with the switch off. Frequency not measured. | FIX-029 |
| M3 | **Medium, pre-existing since FIX-024**, confirmed locally; fails safe | `candidates.py:159`, `daily_review.py:773` | W, on the user's watchlist and in the daily review, a BUY every day. **Observed (RV12):** the list for T-1 reads the analysis of T, 16:35, always after T-1's close, so W is not offered. It is offered only after two reviews in a row skip their analysis (RV12b). **Expected:** the owner's watchlist route works. | Nothing wrong is bought, but the route is mostly shut for such stocks. Not measured; the local logs hold only 10 reviews. | FIX-029 |
| M4 | Low today, owner decides; confirmed locally | `autopilot.py:196`, `shelf.sold_since_dive` | Own-watchlist W sold at Monday's close; Wednesday's review analysis a BUY; Thursday's and Friday's reviews skip theirs. **Observed (RV4):** with deployment on, bought back at Thursday's close. **Claimed:** at most one round trip a week. | Rare today because M3 mostly hides it. Normal once M3 is fixed. | FIX-029, with options |
| L1 | Low; confirmed locally; measured as not yet occurring | `shelf.py:367`, `candidates.py:244` | Verdict NEUTRAL or SELL at conviction 0.70. **Observed (RV6, RV7):** kept and bought. D1 says "rates BUY", D4 "still a BUY". | In `data/rl/verdict_shadow.jsonl` (1,541 analyses, 17 Jul to 27 Sep, before FIX-013's model change), all 1,364 at or above 0.55 had a BUY bound verdict. | FIX-029 |
| L2 | Low; confirmed locally | `pipeline.py:463-465` | The pipeline re-run for the same day. **Observed (RV9):** the run marker stops execution, `run_report` stays empty and the digest is rewritten with no `top_up_skipped`. SA-049's `deployment` record goes the same way (code inspection). | "ADD" with no reason after a manual re-run. | PR-007 |
| L3 | Low; code inspection, no browser run | `src/frontend/prototypes/portfolio.jsx:668-670` | The holdings table shows the digest's verdict and `reason`, not `top_up_skipped`. | The page says ADD for a top-up that did not happen. The ledger shows no buy. The card asked for the log and the digest; the brief is right. | PR-007 |
| L4 | Low, docs; confirmed by M2 and M4 | KT section 6; `PR-013.md` | "a round trip happens at most once a week" holds for a shelf idea only. | The answer to the card's own question is overstated. | Commit-time edits 3 to 5, 8 |
| I1 | Info; inference, not exercised | `base_orchestrator.py:333`, `prediction_store.py:121` | Under `adapt`, the repository's default, the analysis opens `PredictionStore` under the dive's key, whose constructor makes the folder. Production runs `observe` (KT section 1), which returns first. | An empty folder for a managed stock whose dive key differs. No data is written there. | Noted; no action |
| I2 | Info, test environment; confirmed | `store_migration.py:163`, `test_store_migration_sa009.py` | `os.replace` of `lineage.json.tmp` in pytest's temp folder raised `WinError 5` during the full suite, in `test_rollback_never_merges_into_a_live_store_that_reappeared`. The file then passed 5 of 5 runs alone. FIX-025 changes no store code. | The third test in this file to fail this way, after `test_a_refused_store_is_retried...` (22 Oct, in HANDOFF, unrouted) and `test_cli_round_trip` (this story's first run). Windows only; production is Linux. It can make a clean tree look red. | Noted, still unrouted; the suite's result is recorded as it was |

Not a finding: my RV11 first failed on a price outside the dive's own band, then on an assertion about learning
mode that does not belong in it. Both were my fixture; I corrected them.

## The implementation receipt's questions

1. **D12, D13:** right. Nothing else compares a sale's date with a dive. D13 is needed: the mutant that drops
   the flag fails the end-to-end test.
2. **D14:** nothing is keyed by the wrong sector (RV11), and the flag cannot let in a held stock (the mutant
   `cycle_flags_every_sold_candidate_held_or_not` is caught). The re-dive's flag can pass a stock another
   portfolio still holds. That is right: it costs one analyst call, and the portfolio that sold needs that dive.
3. **`below_aim`:** matches the card's examples; pinned by `test_the_soft_minimums_sentence`.
4. **D13's sector:** see RV11 and I1.
5. **T3 and row 2:** real. T3 has a real stop breach, `decide`, `evaluate_switch_candidates` and executor. Row 2
   has the real pipeline, list, executor, digest and value point, with prices, the shelf's load, narration and
   delivery stubbed.

## The card's hard-review questions

- **Can the soft minimum still force a buy anywhere?** No. `Target.min_holdings` is read only by `below_aim`;
  the record, the target and `stop_reason` have no branch on it.
- **With a large deposit, can a position pass the 10% cap or its sector's cap?** No (RV1, RV1b, RV2).
- **Can D4 churn?** Through a shelf idea, at most one round trip a week, as the receipt says. **Not through a
  SWITCH (M2), and rarely through the user's own watchlist (M4).** Each round trip's cost is on its ledger row and
  the portfolio page's cost summary, not on the scorecard: routed to PR-013, whose line needs edit 8.
- **Is a refused ADD ever retried past the check?** No. `_execute_buys` is the only top-up path, deployment
  answers "held", and a SWITCH excludes a held stock at advice time and has its own check at execution.

## Upheld

F25-D1 to D14 hold as reasoned. Living documentation matches the behaviour except L4 and M3's example. The PDF has
68 pages and carries the KT's digest `c3fc57173004`, with new text present and removed text absent
(`rv_docs.py`).

**Still the owner's:** `portfolio.max_holdings` (15), "asked, not assumed". It binds when money arrives on a full
book: ₹40 L arriving on 12 holdings stops at 15 holdings and 37.0% invested, ₹31,51,000 idle (pinned by
`test_max_holdings_still_binds_when_money_arrives_on_a_full_book`).

## Commands and environment

`.stockai` venv, Python 3.13, Windows, `tests/hermetic.py` in force (no network).

- `pytest tests -q -p no:cacheprovider --tb=short --show-capture=no`: **6,160 passed / 12 skipped / 1 xfailed / 1 failed (25m43s, 20:41-21:07, pytest rc 1; the failure is WinError 5 on a temp-folder rename in test_store_migration_sa009, code FIX-025 does not touch, and that file then passed 5 of 5 runs alone)**; `git status` identical before and after.
- `pytest analysis_data/fix025_review/test_rv_fix025.py`: 67 passed + 10 strict xfail.
- `python analysis_data/fix025_review/rv_mutants.py`: 40 of 40 caught.
- `check_kt_docs`: errors `[]`. `check_broad_except`: OK (148). Fresh-interpreter imports of the changed modules
  and `services.api.server`: OK.

**Not exercised:** production state, logs or live data (the frequency of every finding); the real LLM and a real
orchestrator (analyses are faked); a browser (L3 is by inspection); real Yahoo or NSE reads; the implementer's
in-place mutants.

## Acceptance checklist

- [x] Each row of the card's table by hand-derived quantities through the real executor, and row 2 through the
  pipeline.
- [x] The property test with no below-floor exception, and RV2.
- [x] `min_holdings`, `target_holdings`, `max_holdings` and the regime shares, in config or per portfolio, change
  behaviour with no code change.
- [x] D3: every refusal in either switch position, a cleared stock unchanged, the cooldown untouched.
- [x] D4: a sold idea first, inside the budget.
- [x] 6 Nov: the real buy, rotation, sale, dive and second buy, end to end.
- [x] Docs: KT sections 6, 8 and 12, AUTOPILOT_GUIDE, guide 06-K, 06-L, 07-G and 07-O, config comments, the
  docstring. Corrections below.
- [x] Routed L2, T1, T2 and T3. L2's neighbour is M1.

## Commit-time edits

The KT, the guide, the README and PR-013 are in the reviewed manifest, so these wait for the docs commit.

**Order:** the code commit is all 33 reviewed files, byte-exact (`kt_manifest.py verify --rev HEAD` 0 mismatches).
The docs commit then carries the implementer's edits, these, this receipt, the FIX-029 card, PR-007's routed section
and STATE and HANDOFF.

1. **KT header and section 1:** the code commit, the edition, and "the inspected code adds FIX-025, committed but
   not yet deployed".
2. **KT section 12:** FIX-025 `Done`; after FIX-028's row add `| [FIX-029](planning/PI-2026-09/stories/FIX-029.md) |
   Every door to a buy reads the same facts: the day's regime, the sale and the verdict | Open | 6 Portfolio; 8
   Discovery | FIX-025 |`.
3. **KT section 6, Advisor precedence (M1).** After "label recorded for that day holds the ADD the same way." add "A
   label recorded for that day does not yet replace the older one, so such a holding can still add on a recorded
   RISK_OFF or MACRO_CRISIS day (**Planned:** FIX-029)."
4. **KT section 6, "Which ideas" (M3).** After "one analysed at 11:00 IST is offered by Tuesday's run, at Monday's
   close." add "A stock in the daily review usually has a newer analysis by then, made after the session the run
   reviews, so it is usually not offered (**Planned:** FIX-029)."
5. **KT section 6, the re-buy bullet (L4).** Replace "so a round trip happens at most once a week, each side paying
   its costs;" with "so through a shelf idea a round trip happens at most once a week, each side paying its costs. A
   SWITCH leg does not read this rule, and for a stock on the user's own watchlist a newer analysis counts as a new
   dive (**Planned:** FIX-029);".
6. **Guide 06-K, 06-L, 07-G and 07-O:** status lines, "accepted 2026-11-06, committed as `<code commit>`; not
   deployed".
7. **The plan's README:** after FIX-028's paragraph add "FIX-029, added on 2026-11-06 from FIX-025's fresh review
   (routing delegated), comes after FIX-028: a holding with no review entry can top up on a recorded bad day, a SWITCH
   can buy a stock sold the day before, the daily review mostly shuts the watchlist route, and a shelf idea's verdict
   is not read. Recommended before switch-on, not a precondition; the owner decides how a stock on their own watchlist
   comes back (3 points)." After FIX-028's row add `| 26b | [FIX-029](stories/FIX-029.md) | P1 | 3 | Every door to a
   buy reads the same facts: the day's regime, the sale and the verdict | FIX-025 |`.
8. **PR-013's routed line.** Replace "so a stock can be sold and bought back at most\nonce a week." with "so through a
   shelf idea a stock can be sold and bought back at most once a week (FIX-029 covers the other doors)."
9. **The PDF** regenerated, then `check_kt_docs`.

## Follow-up state

STATE: FIX-025 `done` with a `review` entry; production `pending_deployment`, its first look guide 06-K, 06-L and
07-O's production lines. New FIX-029 `todo`, P1, 3 points, after FIX-028. `active_task` null; `next_task` FIX-026,
implementation, in a new conversation. Commit and push only at the owner's word, in a job-free window. **Deploying
changes production with the switch off** (the implementation receipt's Rollout section). The switch stays off;
FIX-023, FIX-024 and FIX-025 are its preconditions, and FIX-028's measurement comes before it.
