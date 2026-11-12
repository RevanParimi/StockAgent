# FIX-029 — fresh review receipt

**Story:** [FIX-029](../stories/FIX-029.md): every door to a buy reads the same facts: the day's
regime, the sale and the verdict.

**Context:** fresh-session review, 12 Nov 2026, from about 08:10 IST. Session `stockagent-main-77`
[0cd619], a new conversation opened with "continue". It is not the implementing session
(`stockagent-main-3b`). After a fetch, `origin/main` was `581eb90`, the same as HEAD: nothing had
arrived from the other device. Peers -17, -22, -63, -77 [fd76db], -09, -38 and -3b were idle.

**Verdict: ACCEPTED** for the working tree of manifest `55c54758` (uncommitted). No finding is above
low. One low finding is about evidence: the local measurement behind the hard-review answer on the
verdict rule says less than it appears to (R1); it changes a sentence in KT section 6 at commit
time and makes the card's probe the thing to read before the deploy. Nothing was committed, pushed,
deployed or configured. During the review no production state, log or environment was read, no LLM
or network call was made from a test, and no message was sent. Afterwards, at the owner's word, one
read-only counts-only probe ran in production ([Pre-deploy probe](#pre-deploy-probe-12-nov-1055-ist-at-the-owners-word));
it closes R1.

## Reviewed input

- **Manifest** [FIX-029-manifest.json](FIX-029-manifest.json), SHA-256 `55c547584e492137254ea031ef0e545e23f06232bea0e89fc28e3fbfe628d539`, 31 files:
  `scripts/docs/kt_manifest.py verify` against the working tree: 0 mismatches, at the start and at
  the end (`analysis_data/fix029_review/rv_digest.py`, which writes nothing tracked).
- **Diff** against HEAD `581eb90` over the manifest's paths but the PDF, taken from the working tree
  written as a tree with a temporary index: 154,159 B, SHA-256
  `3bc38e520461ceb443c1d0b9cde123c5386efc4e959fb061f6e9154eb0bbe5aa`, 30 paths. Equal to the
  receipt's. Outside the manifest only the bookkeeping changed (STATE, HANDOFF, the implementation
  receipt, the manifest itself).
- **The bytes tested:** the working tree as git tree `eb00809022015ced0be6fe8ff4cc1105483e1463`
  (the receipt's end tree `acbbd174` plus its own last bookkeeping), held by a commit object
  `6b07e81` that is on no branch; two detached worktrees in the scratchpad ran from it (removed at
  the end). The shared checkout was not used for any run.

## The contract, and how it was checked

**1. Option A end to end, over a fortnight (RV1).** Through the real executor (the sale), the real
ledger, the real score store, the real candidate list and the real post-review pipeline with
deployment on; only prices, the listing, the EOD window and NSE's report are stubbed. W is on the
user's own watchlist, held 100 at ₹1,000, cash ₹9,00,000; Tuesday 3 Nov's job sells it at Monday's
close; the daily review writes a BUY at 0.70 at 16:35 IST every weekday. Worked by hand: the job on
day J reviews the weekday before and reads the analysis of the weekday before that, and only an
analysis from Saturday 7 Nov counts. The runs for Tue 3, Wed 4, Thu 5, Fri 6 and Mon 9 offer
nothing, each with "sold by the autopilot on 2026-11-03; from the watchlist only an analysis made on
or after Saturday 2026-11-07 counts (this one is of <the day read>)"; the run for Tue 10 reads Monday
9 Nov's analysis and deployment buys 80% × ₹10,00,000 / 12 = ₹66,666.67, so 66 shares at Tuesday 10
Nov's close. **Pass.** Against `581eb90` it fails on its first run (the old reader read the job's
own analysis, after the close).

**2. The rollout's last bullet, concretely (RV2).** Wednesday 4 Nov's job reviews Tuesday. Y
(it_sector, 1,000 at ₹100, now ₹70) breaches its stop; the shelf is empty; W (the user's own
watchlist, in the daily review) has BUYs at 0.80 from the 16:35 re-runs of Mon 2, Tue 3 and Wed 4.
The list offers W with Monday's analysis (analysed `2026-11-02T16:35+05:30`, Monday's thesis), the
advisor SWITCHes Y into W, and the leg buys floor(70,000 / 1,000) = 70 shares at Tuesday's close.
**Pass.** With the old reader (the control) the same day is a plain EXIT and the ₹70,000 stays in
cash; against `581eb90` the main case fails on exactly that. So, with the switch off, deploying
FIX-029 makes a SWITCH buy the user's own watchlist BUYs, as the implementation receipt says.

**3. A run's own exit at the deployment door (RV3).** X is held and still an active shelf idea
(dived Sat 31 Oct, 0.90); the run EXITs it; deployment, after the sale, refuses X ("sold on
2026-11-04, after its deep dive of 2026-10-31; waits for a new deep dive": the run's own decision
day) and buys Z, 66 shares. **Pass**, and it passes on `581eb90` too: this protection existed in
deployment before; FIX-029 keeps it while moving the rule into `resale_wait`.

**4. The card's acceptance.** The FIX-025 reviewer's RV3 to RV7 and RV12 with their strict xfail
marks removed (the implementer's copy `analysis_data/fix029/rv025/`), run here from the pinned
bytes: **76 passed, 1 xfailed** (RV9, routed to PR-007). The adaptations A1–A3 were read and are
faithful: A1 is the reader's rename; A2 makes RV12's fake answer what the bounded reader returns
(the story file checks the same against the real score store); A3 gives `decide` the list built
with the ledger, which is where the card puts the rule, while the executor still gets the
unfiltered idea, so the leg's own check is exercised too. Those cases were strict xfails written
before the fix, each confirmed failing at its assertion by FIX-025's review.

**5. The story's tests.** Expected results are worked by hand in each docstring. The sale rule's
oracle finds the Saturday by counting days, not with `saturday_after`; M1's 104 shapes state the
card's invariants (an older label never allows what today's recorded label refuses; today's calm
label frees an older crisis label; an own entry of the day is never overruled; the crisis exit reads
the same label); M3 runs the real score store. The implementer's 30 mutants cover every rule this
review would have targeted (the bound at the close, the newest of all, the Saturday's edges, a trim,
a hand sale as the autopilot's, the list, both doors, this run's exits, each verdict rule), all
caught; they were not re-run.

**6. Every buy door reads the list** (code inspection). `buy_candidates` has one caller, the
pipeline, which passes the ledger's `Sales` and gives the same filtered list to the live decision,
the exit shadow's `switch_lands` and the executor's `shelf_index`. A destination the advisor picks
is never held at list time, so this run's exits cannot refuse it at the leg, and the shadow's
`switch_lands` stays true to the executor. Hand-made advice, or a list built without the ledger, is
caught at the SWITCH leg and in `_deploy_check`. A top-up is of a held stock; `POST
/portfolio/holdings` is the user's own trade; IPO ideas reach the shelf through the same dive.

**7. Data shapes** (code inspection). Ledger reads take the newest 2,000 rows. A hand sale is
written with `source="manual"` by every route that writes one, so it is never read as the
autopilot's. `holding_qty_after` is a required field. `run_at` is written as naive UTC by `save` and
by the backfill script, so the text comparison in `get_latest_before` orders correctly (D10); a
differently written stamp could only hide an earlier analysis, never admit a later one, since the
list still refuses a record after the close. The report's verdict is hard-bound to the composite's
canonical labels (`hard_bind_verdict_enabled: true`), so `verdict_wait`'s BUY/STRONG BUY test meets
the strings it reads. The old reader name and `_last_sales` have no remaining caller.

**8. The card's hard-review questions.**

1. *The exit shadow and the switch rows:* a sold idea has no row, and the next-best idea may be
   taken (RV2's shape, the story's `rv5b`); `switch_lands` reads the same filtered list (item 6).
   Agreed.
2. *Can L1's rule empty the list on its first day?* Yes, in principle, and the evidence that it
   will not is weaker than the receipt says (finding R1). Every shelved idea stores a verdict (the
   shelf's first commit `fa2e77c`, 9 Jul, already wrote `verdict=dive.verdict`), so "no verdict
   stored" is not the risk; disagreement is. The local verdict log's 1,364 of 1,364 agreement holds
   because the composite sat at 0.649–0.65 on 1,537 of its 1,541 analyses; after FIX-013's model
   change (22 Oct) nothing is measured. It fails safe: a SWITCH becomes a plain EXIT, and fewer dives
   are shelved (D7).
3. *Can M1's recorded label reach a reader that assumed the holding's own entry?* Only `decide` (ADD
   and the crisis exit) and the narrator read `AdvisorSignals.regime_label`; `regime_unavailable`
   reaches the advice record and the narrator's note only with `REGIME_UNAVAILABLE`. Agreed. For a
   holding with no entries at all (D1), the crisis exit now reads the day's recorded label instead
   of a default NORMAL: intended.
4. *A band or thesis older than the page's analysis; an older BUY against a newer SELL:* yes, for
   the close before the newer analysis (D3; RV2 shows Monday's thesis carried at Tuesday's close
   while Wednesday's analysis exists). This is issue-time correct and follows the decision recorded
   with FIX-027's review (FIX-031 I-1).

**9. The implementer's decisions.** D1–D6 and D8–D10 agree with the card and the code. **D7**
(a new dive not rated BUY is not shelved) goes beyond the card's list but follows the owner's D1
("the ideas the analysis rates BUY"): such an idea would hold a shelf slot and a sector place that
no door may buy from, and its re-dive would drop it. Accepted; its size is R1's measurement too.
The recorded limit (on a dark day, a holding with no entry of its own keeps its older label for the
crisis exit) stands as written.

## Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| R1 | Low, evidence and rollout | The implementation receipt's hard-review answer 2 and F29-D8; KT section 6 ("In the local verdict log … all 1,364 at or above 0.55 had a BUY verdict"; `docs/TECHNICAL_DESIGN.md` 1914–1916) | The local `data/rl/verdict_shadow.jsonl` (17 Jul–27 Sep): the composite is 0.649, 0.6499 or 0.65 on 1,537 of 1,541 rows, and its minimum among the 1,364 with a score of 0.55 or more is 0.649 (`analysis_data/fix029_review/local_verdict_margin.py`). **Observed:** the agreement reflects a near-constant composite. **Expected:** the docs and the answer should not read it as evidence about today's models. | How many active shelf ideas, and Saturday's dives, are not rated BUY since FIX-013 is unknown, so the first days may offer far fewer SWITCH destinations and shelve fewer ideas. Fails safe (cash, not a wrong buy). | **Closed 12 Nov 10:55 IST** by the production probe (next section): all 19 active ideas are BUYs, and 216 of the 218 analyses since 23 Oct with a score of 0.55 or more are BUYs. Commit-time edit 3 stands: the local sentence still reads a stale file's artefact as evidence |

No other finding. The implementer's "Found on the way" items are confirmed by reading.

## Pre-deploy probe (12 Nov, 10:55 IST, at the owner's word)

The owner said "go ahead on the recommendation" in this conversation. Before it, a fetch showed
`origin/main` = HEAD = `581eb90`. One `railway ssh` call (rc 0) ran two read-only, counts-only
probes in `/app`:
- the card's `analysis_data/fix029/doors_probe.py`;
- the reviewer's `analysis_data/fix029_review/r1_probe.py`, which reads the verdict shadow log, the
  score database (`immutable=1`) and the shelf. Run locally first, it reproduced R1's local figures
  and left nothing behind.

Neither probe prints symbols, user ids or values. The output is in
`analysis_data/fix029_review/prod_probe_out.txt` (ignored).

| Question | Production |
|---|---|
| L1: active shelf ideas by verdict | 19, all BUY (17 dived since 23 Oct, 2 before), so L1 keeps all 19 |
| Analyses since FIX-013 (23 Oct to 11 Nov; the shadow log and the score store agree on 441) with a score of 0.55 or more | 218: 216 BUY and 2 NEUTRAL. The NEUTRALs sit at the floor's edge: one composite was 0.5439, the other was logged as 0.55, presumably just under it before rounding (inference) |
| The composite behind those verdicts | 0.544 to 0.727, median 0.61, 108 distinct values. Before 23 Oct (18 Jul to 21 Oct): 0.55 to 0.807 over 590 such analyses, 589 of them BUY or STRONG BUY |
| Active ideas sold since their dive (cut by the resale rule today) | 0 |
| M2: a SWITCH into a stock the autopilot sold, with no newer dive | 0 (21 autopilot exits, 11 SWITCH buys) |
| M3: watchlist stocks the user or the shelf added that are in the daily review | 0, so neither rule offers any |
| M4: holdings with such a watchlist row | 0 |
| Portfolios | 1 |

**What this shows:**
- R1's worry does not hold in production. The near-constant composite was a property of the stale
  local file, not of the models: in production the composite varies (108 distinct values since 23
  Oct) and it agrees with the floor on 216 of 218.
- Deploying FIX-029 today removes nothing from the list: all 19 ideas stay, and no sale cuts an
  idea.
- No watchlist stock is in the daily review, so the RV2 case has no stock to apply to until one is
  added.
- FIX-029's effects come on later days: a sale, a re-dive no longer rated BUY, or a watchlist stock
  added to the daily review.
- **No benefit is shown:** these are counts.

## Commands and results

Environment: `.stockai/Scripts/python.exe` (Python 3.13), Windows, hermetic (`tests/hermetic.py`).
Runs in detached worktrees of `6b07e81` in the scratchpad (removed at the end). Reviewer files in
`analysis_data/fix029_review/` (ignored).

| Command | Result |
|---|---|
| `analysis_data/fix029_review/rv_digest.py` (start and end) | manifest `55c54758`, verify 0 mismatches; diff `3bc38e52`, 154,159 B, 30 paths |
| `pytest -q -p no:cacheprovider analysis_data/fix029_review/test_rv_fix029.py analysis_data/fix029/rv025/test_rv_fix025_unxfailed.py` | **80 passed, 1 xfailed** (RV1, RV2, its control and RV3; the 76 acceptance cases; RV9 strict xfail) |
| The same reviewer file against `581eb90` (a worktree) | RV1 and RV2 fail on their assertions (the old reader's "close of … is before the analysis of …"); RV3 passes (pre-existing protection); the control cannot patch a reader that did not exist |
| `scripts/ci/check_broad_except.py` | OK (148 grandfathered) |
| `scripts/docs/check_kt_docs.py` | `errors: []`; PDF 69 pages, source `21f4fa4a…` = the KT's SHA-256; the header still names `245e29e` (the commit-time bump) |
| `local_shelf_verdicts.py`, `local_verdict_margin.py` (read-only, local data) | the local shelf is empty (a July file); the verdict log as in R1 |
| Full suite `pytest tests -q -p no:cacheprovider` (worktree of `6b07e81`) | **6,304 passed, 14 skipped, 1 xfailed, 1 failed**, pytest rc 1, 26m03s (08:18–08:44 IST; the worktree's git status empty before and after; `analysis_data/fix029_review/full_suite.txt`). The failure is the story's `test_m1_every_label_with_or_without_an_entry_of_its_own`, on its dark-day reason: the captured log shows `[RegimeState] Failed to persist state … [WinError 5] Access is denied` in the test's own tmp folder, so the swallowed write left the day unmarked. Environmental (a Windows file lock on the atomic `replace`, the class FIX-025's review met in `test_store_migration_sa009`); the test then passed 5 of 5 runs alone and its file 27 of 27. Production runs on Linux. The 2 skips beyond the implementer's 12 are the browser tests, which need `node_modules` (absent in a worktree): run in the main checkout, `test_chat_markdown_boundary.py` and `test_ui_no_invented_figures_pr001.py` give **53 passed** (3m59s; status unchanged). The test counts sum to the implementer's 6,320 |

**Not exercised:** production during the review (the probe ran afterwards, at the owner's word, as
described in Pre-deploy probe); a re-run of the
implementer's mutants (item 5); a browser (no interface changed).

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| RV3 to RV7 and RV12 pass with their strict xfails removed, through the real advisor, list and executor | Met (76 passed, 1 xfailed: RV9 belongs to PR-007) |
| `decide` over the labels and an own or older entry: an older label never allows what today's recorded label refuses, and today's calm label frees an older crisis label | Met (the story's 104 shapes; read) |
| A sold stock is offered again by the first run that may use a new dive; a hand sale still blocks as deployment did | Met (the story's tests; RV1 for the watchlist through the pipeline) |
| Docs: KT sections 6 and 8, AUTOPILOT_GUIDE, guide 07-G and 07-O, PR-013's routed line | Met, with commit-time edit 3 |
| Card's measure first | Met 12 Nov 10:55 IST, after the review, at the owner's word (Pre-deploy probe); it closes R1 |

## Production verification (pending)

Status `pending_deployment`: nothing is committed. Deploying changes production with the switch off
(the implementation receipt's Rollout): a SWITCH skips a stock sold since its idea was decided and an
idea not rated BUY; an ADD for a holding with no entry of its own reads the day's recorded label;
Saturday's discovery shelves only BUY dives and drops a re-dive that is no longer one; **a SWITCH may
buy the user's own watchlist BUYs (RV2).** The read-only probe has run (12 Nov 10:55 IST, Pre-deploy
probe): today's list loses nothing, and no watchlist stock is in the daily review. After the deploy,
read the run log's "not offered" reasons and the digests' deployment outcomes. No benefit is shown by
this review.

## Commit-time edits

The KT, the guides and the PDF are in FIX-029's reviewed manifest, so they were not edited during
this review. At the commit, with the owner's word:

1. **KT header:** Code inspected = the FIX-029 code commit; edition = the commit's date.
2. **KT section 1** (production paragraph): the inspected code adds FIX-029, not yet deployed.
3. **KT section 6** ("Which ideas", the verdict bullet): delete "In the local verdict log (1,541
   analyses, 17 Jul to 27 Sep, before the October model change), all 1,364 at or above 0.55 had a
   BUY verdict;" and end the previous sentence "(section 8);". The measurement and its limit stay in
   this receipt (R1).
4. **KT section 12:** FIX-029 `Done`.
5. **TEAM_TESTING_GUIDE 07-G and 07-O:** "**FIX-029: implemented 2026-11-11; fresh review pending;
   not committed.**" → "**FIX-029: accepted 2026-11-12 (fresh review), committed as `<sha>`; not yet
   deployed.**"
6. **PDF:** regenerate from the KT; `check_kt_docs` `errors: []`.

## Follow-up state

- FIX-029 `done`; production `pending_deployment` (above).
- `active_task` null; `next_task` SA-044 (implementation, a new conversation; its sequencing note
  puts it right before FIX-030), then FIX-030, FIX-031, FIX-032. The switch stays off. The Saturday
  14 Nov watch for SA-044 and FIX-030 still applies.
- Uncommitted, waiting for the owner's word: FIX-029's work, this receipt, STATE, HANDOFF, and the
  11 Nov push record.
