# PR-015 — rollout receipt

**Story:** [PR-015](../stories/PR-015.md): the evidence exit rule acts. It serves the **sell** step
of the profit path.

**Lane: light (rollout).** Reason: no code changes; the one setting it changes,
`advisor.exit_rule: evidence`, was decided by the owner on 14 Nov 2026 ("yes" to R3 of the
profit-path review). The code behind it was reviewed with PR-009, FIX-016, FIX-018, FIX-031 and
FIX-015. When its steps are done it is accepted without a fresh-session review.

The card says the setting is pushed "at a time the owner agrees", and the owner's standing
instructions keep production flags theirs. So the change is prepared on the branch
`story/PR-015` and merges into `main` only at the owner's word: every push of `main` redeploys,
and this one switches which rule sells.

## Steps

| # | Step | State |
| --- | --- | --- |
| 1 | Confirm from the code: `evidence` mode still records the old verdict, and the scorecard reads both | **Done**, 18 Nov (below) |
| 2 | `advisor.exit_rule: evidence` in `config.yaml`, pushed at a time the owner agrees | **Prepared** on `story/PR-015` (`12b7901`); **waits for the owner's word** |
| 3 | Living documents in the same commit | **Done** in `12b7901` |
| 4 | After the first review day under `evidence`, the read-only read | Not started: after the deploy, at the owner's word (`PR-015-W1`, below) |
| 5 | `thesis_break` stays computed and recorded | **Confirmed** from the code (below); nothing to change |

## Conversation 1: Wednesday 18 Nov, from about 00:29 IST

Autopilot session `1118-0029-p5` on the code-server, a `continue`. `main` = `origin/main` =
`8422a23` after a fetch. No production state was read beyond `/health` (200 at 00:32 IST) and
`railway status` (project carefree-renewal, environment production). No setting changed, no job
ran, no message was sent.

### Step 1: what the code does in `evidence` mode (code inspection, `8422a23`)

- **The mode is read per run.** `exit_shadow.exit_rule_mode()` reads `advisor.exit_rule`; an
  unknown value reads as `shadow`. `acting_rule("evidence")` is `evidence`
  (`core/portfolio/exit_shadow.py:131-145`).
- **Both verdicts are still recorded.** The pipeline builds the evidence reader in every mode but
  `legacy` (`core/portfolio/pipeline.py:285-286`). It decides with the acting rule, then calls
  `decide` again with the other rule and writes one `exit_shadow.jsonl` row per holding per review
  day, the price-path verdict in `legacy_verdict` and `legacy_triggers` whichever rule acts
  (`pipeline.py:345-363`). The row's `mode` names the setting.
- **The thesis review still runs.** It is a step of the daily review, not of the pipeline, so
  `thesis_intact` and the price-path verdict are computed in every mode (card step 5).
- **The scorecard reads both.** `results.py:1239` passes every row of `exit_shadow.jsonl` to
  `scorecard_block`, which neither filters nor weighs by `mode`; the grading is written from the
  evidence rule's side ("right when it sold and the stock then fell short"), so it reads the same
  with the roles swapped.
- **A test holds it.** `tests/unit/test_exit_evidence_pr009.py:428`
  (`test_shadow_decisions_and_transactions_are_byte_identical_to_legacy`) runs the pipeline in all
  three modes: under `evidence` the sales are the evidence rule's (BBB on a SELL verdict, not AAA on
  `thesis_break`), and every row still carries both verdicts.

**One finding, low (BACKLOG B-12).** The scorecard's gate sentence is worded for a switch not yet
made: after two passing weeks it says "so the evidence rule may replace the price-path rule. The
owner decides." (`exit_shadow.py:963`), and the line never says which rule acts. No buy, sell, size
or grade reads it. KT section 6 (on the branch) says how to read it after the switch; the
rewording waits in the backlog until PR-013 next edits the scorecard.

### Steps 2 and 3: the change, held on `story/PR-015`

`12b7901` (parent `4fd57ab` on `main`): `advisor.exit_rule: shadow` becomes `evidence`, with the
living documents the card names and two the search found:

| File | Change |
| --- | --- |
| `config.yaml` | `exit_rule: evidence`; the comment says why the gate was not waited for, and that `shadow` is the rollback |
| `docs/TECHNICAL_DESIGN.md` | Section 1: an "Exit rule" row. Section 3: the setting's row. Section 4: the events paragraph. Section 6: the modes (with a worked example) and "The switch was made without the gate", which replaces the old "the owner switches on the gate". Section 11: "Sell on evidence" is current, not planned. Section 12: the order paragraph |
| `docs/AUTOPILOT_GUIDE.md` | 3.2: EXIT names "the acting exit rule's reason test", explained under the table with an example; 16: the PR-015 bullet says how the rule is judged |
| `README.md` | The verdict table's EXIT row names `case_broken` and says when `thesis_break` acts instead |
| `docs/TEAM_TESTING_GUIDE.md` | 07-L: repeated after PR-015's deploy; under `evidence` every SELL carries the evidence rule's triggers, never `thesis_break` |
| `tests/unit/test_exit_evidence_pr009.py` | The test of the shipped setting expects `evidence` (renamed `test_evidence_is_shipped_and_an_unknown_value_reads_as_shadow`); a missing or unknown value still reads as `shadow` |

Diff `4fd57ab..12b7901`: 6 files, 62 insertions, 31 deletions, sha256
`9501379b57b2581c34db904c18e82cf477c25e44ccd3585e7e65736ab3e0627e` (of `git diff 4fd57ab 12b7901`).
A first commit, `e5478e1`, lacked the test change. Its full-suite run showed a failure at about
61%: PR-009's test of the shipped setting asserts `shadow`. The run was stopped, the test updated,
and the local, unpushed commit amended into `12b7901`, whose full run is below.

`4fd57ab`, on `main` before the branch, holds two corrections that are true today: KT section 1
records FIX-015's deploy (`8422a23`, 18 Nov 00:27 IST), and AUTOPILOT_GUIDE 3.2 no longer lists
`thesis_break` among the shock exit's triggers (FIX-015 left that row stale).

### Tests

- **Full suite on `12b7901`** (detached worktree on the code-server, the repository's `.stockai`
  Python): 6,791 passed, 12 skipped, 1 xfailed, 0 failed, return code 0, 6 min 8 s (about 00:38 to
  00:45 IST).
- **Focused:** `test_exit_evidence_pr009.py`, `test_exit_fix016.py`, `test_shock_reforecast_fix015.py`,
  `test_issue_time_fix031.py` and `test_portfolio_pipeline.py` on the branch: 298 passed.
- **`scripts/docs/check_kt_docs.py`:** no errors, on the branch and on `main`.
- Under `evidence` the existing pipeline test checks that the sales are the evidence rule's and
  that both verdicts are still recorded; no new test was needed for a setting.

### What the owner's word starts (the merging session)

1. `git fetch`; on `main`, `git merge --no-ff story/PR-015`. If `main` has moved and the merge
   conflicts, abort and record it.
2. In the same session, a records commit: KT section 1's production paragraph and its "Exit rule"
   row get the commit and the push time; this receipt gets a "Conversation 2" section; STATE adds
   `PR-015-W1` (below) with its date.
3. The full suite on the exact commit, then the push in a job-free window (00:10-06:20 IST, not on
   the 1st, not 03:00-04:00 on a Monday). Then the deploy and `/health`, recorded.
4. The first review under `evidence` is that day's 16:30 run, which reviews the previous session.

**`PR-015-W1`** (card step 4), from the morning after the first 16:30 review under `evidence`,
read-only, counts and trigger names only: for that review day, the number of `exit_shadow.jsonl`
rows against the holdings advised; every row's `mode` is `evidence`; each holding has one row;
every SELL in `transactions.jsonl` that day carries the evidence rule's triggers (`case_broken`, a
stop, `shock_reforecast`, `crisis_regime_bearish`), never `thesis_break`; and the disagreements,
with both rules' trigger names. Production is read only at the owner's word in the same
conversation, so the session hands the owner the command or runs it when they say so.

**Rollback:** `advisor.exit_rule: shadow` on `main`, pushed in a window. The price-path rule
decides again from the next review, and both verdicts stay recorded.

### Example for the owner

Bought at ₹500. The close falls to ₹480 on a broad market fall; the thesis review says "not intact"
and the path ends at ₹478. No filing, no SELL verdict, the invalidation price ₹455. Today
(`shadow`) the stock is sold at ₹480. After the switch it is kept: if it recovers to ₹560 the
evidence rule earned ₹80 a share more; if it falls to its stop at ₹440, it lost ₹40 a share more.
Either way the row records both verdicts, and the tally at 10 and 30 sessions shows which was
right, for the owner's decision at `PR-014-R2` (from 11 Jan 2027).
