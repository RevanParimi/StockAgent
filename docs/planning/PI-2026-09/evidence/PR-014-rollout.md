# PR-014 — rollout receipt

**Story:** [PR-014](../stories/PR-014.md): switch idle-cash deployment on, then read what it does.
It serves the **invest** step of the profit path.

**Lane: light (rollout).** Reason: no code changes, and the one setting it changes was authorized
by the owner on 14 Nov 2026. The code behind the setting was reviewed with SA-049 and FIX-023 to
FIX-031. When its steps are done it is accepted without a fresh-session review.

The rollout spans several conversations, because its steps wait for the owner's read, an agreed
push time and scheduled runs. Each conversation adds a section here.

## Steps

| # | Step | State |
| --- | --- | --- |
| 1 | `FIX-030-M1`, the Saturday counts | **Passed**: M1 does not occur |
| 2 | Commit FIX-031, then the docs | **Done**, 14 Nov |
| 3 | Full suite on the tree to be pushed | **Done**: passed on `7487104` |
| 4 | Push: deploys FIX-030, FIX-031 and CLEAN-001 | **Pushed** 07:16 IST Sun 15 Nov, with step 6 (`1913017`); the first jobs after it ran |
| 5 | Read the paper lane's record | **Recorded**, 15 Nov |
| 6 | Switch on (`portfolio.overrides.primary.deploy_idle_cash: true`) | **Pushed** with step 4 (`1913017`) |
| 7 | The first run's `deployment` record | Not started |
| 8 | Three dated checks in STATE | **Done**, 15 Nov |
| 9 | Remind the owner of the deferred setup actions | **Done**, 15 Nov |

## Conversation 1: Saturday 14 Nov, from about 23:45 IST

Session `stockagent-main-2a` [8c7645], a new conversation opened with "continue". `origin/main`
was `5ae2749` after a fetch, so nothing had arrived from the other device; `main` was 13 ahead.
Five peer sessions were idle. No production state was read, no LLM was called, no message was sent,
nothing was pushed and no setting changed.

### Step 1: `FIX-030-M1` is the owner's read

The check is the owner's read of Railway's log view and one read-only run inside the production
container, so this conversation did not run it. It does not hold step 2 or step 3: it decides only
whether a one-point card comes before FIX-030 is deployed (step 4).

1. In Railway's log view, filter on `Discovery` and read Saturday 14 Nov's `[Scheduler] Discovery`
   line: `sectors=[named, generic, unnamed, invalid, disputed, no Yahoo, kept]`, and the
   `Discovery sectors` lines under it. Counts and symbols only.
2. From Git Bash in the repository, the counts-only probe:

   ```text
   railway ssh "cd /app && echo $(gzip -9c analysis_data/fix030/prod_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
   ```

**Rule** (FIX-030's review receipt, "M1"): if most of the week's dives are unnamed with "the
analysis gave no sector answer", M1 occurs and its one-point card comes before the deploy.
Otherwise it closes as not occurring. Either way, record the disputed dives filed `automobile`
with non-automotive Yahoo labels.

**What the probe also tells the switch-on.** On 13 Nov, before Saturday's run, 4 of the 19 active
ideas had a decided sector key, 7 carried a key the old Yahoo table set and 8 had none. After
FIX-030 is deployed, only decided ideas are offered. The 7 are re-dived first on the next Saturday,
and until then they are not bought. The probe's `decided_configured_key`, run after Saturday 14
Nov's dives, is the number of ideas deployment can buy from in its first week.

### Before step 6: will the switch reach the portfolio the autopilot trades?

The switch is keyed by user id: `portfolio.overrides.primary.deploy_idle_cash`. Deployment
runs for a portfolio only when four things hold (`deployment.active`): the autopilot is on,
the portfolio opted in (`autopilot: true`), it keeps cash (`cash_deployable` set), and the
switch is on for that portfolio's user id. Atlas is on (`atlas.enabled: true`), so the
scheduler runs the users table's ids, not the folders on disk.

- **By code inspection:** the first signup becomes the owner under the default id `primary`
  (`services/api/routes/auth_api.py` `signup`), so a key of `primary` names the owner's
  portfolio.
- **Not yet measured:** that the owner's portfolio in production is opted in, keeps cash and
  is in the users table. One read-only probe answers all four, with booleans and counts only
  (no user ids, symbols or amounts). It was dry-run here on a stale local copy, and wrote
  nothing. From Git Bash in the repository:

   ```text
   railway ssh "cd /app && echo $(gzip -9c analysis_data/pr014/switch_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
   ```

  **Pass:** `verdict.override_keyed_primary_would_switch_on` is 1. If it is 0, step 6's key
  is wrong, and the probe's rows show which condition fails.

### Step 2: FIX-031 committed

- **`899526a`, the code:** exactly FIX-031's 16 reviewed files. Before the commit,
  `kt_manifest.py verify FIX-031-manifest.json` gave 0 mismatches against the working tree; after
  it, `--rev 899526a` gives 0 mismatches (manifest `d1fbec94`).
- **The docs commit after it** holds:
  - FIX-031's two receipts and its manifest, with the PR-007 and SA-021 routed notes;
  - the review receipt's commit-time edits: KT header (`899526a`, edition 2026-11-14), KT
    section 12 `Done`, KT section 6's "Not covered" sentence for R1, guide 07-Q's status, the PDF;
  - **one edit beyond that list, KT section 1:** once the header names `899526a`, the sentence
    "the inspected code adds FIX-030, committed as `cddc3be`" is incomplete. It now says the
    inspected code is not yet deployed and names what it holds beyond production: FIX-030,
    FIX-031 and CLEAN-001's removals;
  - **the 14 Nov decisions in the living documents** (this card's step 2):
    - KT section 12: the order since 14 Nov, the 14 learning-rebuild stories shown "Off plan",
      the 5 factor-engine stories shown "On hold", and rows for PR-014 and PR-015;
    - KT section 11: the two groups marked paused and off the plan; the switch-on and the
      evidence rule described as planned by PR-014 and PR-015; SA-024 and SA-031's wait; the
      two review lanes;
    - AUTOPILOT_GUIDE section 16: PR-014's and PR-015's steps;
  - the 14 Nov planning files: the profit-path review, `BACKLOG.md`, the PR-014, PR-015 and
    CLEAN-002 cards, AGENTS.md, REVIEW.md, the PI README's note, and the sentences in the
    FIX-015, FIX-017, PR-009 and PR-013 cards;
  - STATE, HANDOFF and this receipt.
- **Checks on the edited documents:** `check_kt_docs` gives `errors: []` (header `899526a`, edition
  2026-11-14, no linked source changed since the revision). The PDF has 72 pages and carries the
  KT's digest `40db4f24`; the build reported no overflowing element. The first build
  broke the status "Paused" across two lines in the table's narrow cell, so those five
  rows read "On hold"; the PDF's text layer was read again after the rebuild.
- **Where the files differ from FIX-031's manifest:** at the docs commit, the manifest's KT,
  guide, AUTOPILOT_GUIDE and PDF differ from it by the edits above only.
- **Not edited:** `ARCHITECTURE.md`, `RL_DESIGN.md`, `PRODUCT_MAP.md` and `AGENTIC_DESIGN.md` still
  point at stories now off the plan or paused as "Planned". Backlog entry B-4.

### Full suite

Run once on the docs commit `7487104`, the tree to be pushed, with a clean working tree:
**6,456 passed / 12 skipped / 1 xfailed / 0 failed**, pytest return code 0, 22m44s (00:01–00:24 IST on 2026-11-15). `git status` was the same before and after
the run. Command: `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests`; the
hermetic boundary blocks the network.

This result was written after the docs commit, so it is not in it: STATE, HANDOFF and this
receipt carry it in the working tree and go with the next commit (step 6's). The pushed tree
is the tested tree.

### Stopped at step 4

The push deploys FIX-030, FIX-031 and CLEAN-001 together and rebuilds every unpinned package. It
waits for step 1 and for a time the owner agrees. The switch is off.

**Timing, Sunday 15 Nov** (job times in KT section 9; a push needs about 2 hours clear):

- **Step 4** fits from about 08:10 to 15:40 IST: the next jobs are the 17:45 IPO refresh and
  the 18:00 weekly review.
- **Step 6** comes after step 4's build, `/health` and the first job after it are read: about
  19:25 to 20:50 IST, or 00:10 to 06:20 IST on Monday. Either way the Monday 16 Nov 16:30
  review is the first run with the switch on.
- **One push for both** is the owner's choice (the card's step 6). It saves a deploy, and a
  failed build would then hold the switch back too.
- **FIX-030's cost of a Sunday deploy:** the 7 ideas whose key the old Yahoo table set are not
  offered Monday to Friday, 16–20 Nov. They are re-dived first on Saturday 21 Nov.

### One push for steps 4 and 6 (owner, Sunday 15 Nov)

At about 06:30 IST the owner asked: "today is sunday, nothing to wait for right, why cant we
commit and push everything?" The card leaves one push for both to the owner, so step 6's
setting goes out with step 4:

- `config.yaml`: `portfolio.overrides: {primary: {deploy_idle_cash: true}}`. Loaded through
  the settings, `deployment.breadth("primary").deploy` is true and any other user id's is
  false; the global `autopilot.deploy_idle_cash` stays false.
- **Why one push is safe enough here:** the switch acts only in the post-review pipeline
  (`core/portfolio/pipeline.py` `run_post_review_pipeline`), which the scheduler runs after
  the Monday to Friday 16:30 review, or the owner triggers by hand. A Sunday push leaves Sunday
  and Monday morning to read the build, `/health` and the Sunday jobs, and to remove the
  setting before Monday's 16:30 run if anything is wrong.
- **What one push gives up:** a build that fails takes the switch with it; the rollback is the
  same one-line edit and push.
- The full suite runs again on this tree (the setting and these records), before the push.
- **The first run on it failed one guard, as it should:** `test_deploy_idle_cash_sa049.py`
  pinned SA-049's shipped config, `portfolio.overrides == {}` (6,455 passed / 1 failed,
  06:35–06:56 IST). The guard now pins the new shipped config,
  `test_the_shipped_config_switches_on_only_the_primary_portfolio`: the global switch off and
  exactly one override, `primary`. A global switch-on, or one for another portfolio, still
  fails it. Not pushed after that run; the suite runs again on the tree with the guard.

### The owner's two reads, the suite, the push

- **`FIX-030-M1`, passed: M1 does not occur.** The owner ran the probe at about 06:40 IST
  (production `f368f20`, after Saturday's run). Of 20 active ideas, 12 now carry a decided
  sector key (4 on 13 Nov); 10 readings come from an analysis. One idea has no key (8 on 13
  Nov), and it has no reading at all, not an analysis that gave no answer. Five ideas still
  carry a key from the old Yahoo table; FIX-030 re-dives them first on Saturday 21 Nov, and until
  then they are not offered. Not read: the Discovery log line's "disputed" count (M2's size on
  the old code), which FIX-030 removes either way.
- **The switch check, passed.** The same read of `analysis_data/pr014/switch_probe.py`: one
  portfolio, the folder `primary`, opted in, keeping cash, 2 holdings, in the scheduler's run
  list; `override_keyed_primary_would_switch_on` is 1.
- **Full suite on the tree to push** (the setting, the guard and these records, snapshotted
  with a temporary index), run 2: 6,456 passed / 12 skipped / 1 xfailed / 0 failed, rc 0, 18m22s (06:58-07:16 IST). `git status` was the same before and after.
- **Committed `1913017`** (`config.yaml`, the guard test and the three records); its tree equals
  the tested tree.
  **Pushed at 07:16 IST** at the owner's word ("Push when suite passes"), `5ae2749..1913017`:
  FIX-030, CLEAN-001, FIX-031, their docs and the switch.
- **After the push:** Railway deploy 080913e7 (commit 1913017) was created at 07:16:59 IST and reached SUCCESS by 07:19:23; the previous deployment 09698fde is REMOVED; the public /health answered 200 at 07:19:24. The build reinstalled every package (requirements.txt changed). Against the last build that installed packages (7a0719d2, 7 Nov): 76 the same, 12 minor or patch bumps (fastapi 0.162.0 to 0.163.0, langgraph 1.2.20 to 1.2.22, langchain-core 1.7.6 to 1.8.0, filelock 4.2.9 to 4.2.10 among them), none added, and 82 removed: CLEAN-001's RAG stack (torch, chromadb, sentence-transformers, transformers, the CUDA wheels) and the test tools. No module under core/, services/ or src/ imports a removed package; passwords use the standard library's hashlib.scrypt.
- **The switch first acts at Monday 16 Nov's 16:30 run.** Rollback: remove the override and push.

Still to do (a new conversation): the first scheduled jobs after the deploy, step 5, step 7
(Monday's `deployment` record), step 8 and step 9, and the docs commit that says the switch is on.

## Conversation 2: Sunday 15 Nov, from about 21:00 IST

Session `stockagent-main-34` [8fe718], a new conversation opened with "continue". `origin/main`
was `1913017` after a fetch, so nothing had arrived from the other device. One peer session
(`stockagent-main-a5`) was idle; its uncommitted planning files were kept as they were.

### Step 4's last check: the first jobs after the deploy ran

One read-only probe, `analysis_data/pr014/step5_probe.py`, was run through `railway ssh` at
21:10 IST, at the owner's word in this conversation (the same gzip and base64 form as the
probes above). It opens files read-only and writes nothing. It printed counts, dates and the
book's own paper figures. The raw output stays under the ignored `analysis_data/pr014/step5/`.
Its list of files written since the deploy printed a second account's folder name. That name is
in no tracked file, and the probe now masks it.

- **17:45 IPO refresh:** wrote the IPO cache at 17:45. The 08:00 refresh wrote the same file, so
  its own run is not visible in the files.
- **18:00 weekly review:** wrote the 15 Nov weekly review for both accounts at 18:00. The index
  watch wrote its constituents cache at the same time.
- **19:00 IPO deep dive:** finished at 19:00: enabled, 0 candidates, 0 errors.
- **Not yet run at the read:** the 23:00 to 23:45 nightly jobs (Atlas, backup, audit). Step 7's
  probe reads the audit's and the backup's last run.
- **Not read:** whether the weekly review's mail was delivered.

### Step 5: the paper lane's record, recorded

The card's "paper lane's record of shelf ideas against the Nifty" is the nightly auditor's shelf
lane (`grade_shelf_lane` in `core/audit/outcomes.py`). It takes each shelf idea's return from the
close of the day it was added and compares it with the NIFTY 50 over the same sessions, at 10, 30
and 60 sessions. The paper lane module itself (`core/discovery/paper_lane.py`) grades each idea's
30-day price forecast, not its return against the Nifty, so it was not read.

33 ideas added from 18 Jul to 24 Oct, 79 graded rows, the last graded on 12 Nov:

| Sessions after the add | Graded | Beat the Nifty | Mean excess (points) | Median excess | Ideas' mean return | Nifty's mean return |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 33 | 12 | −3.2 | −1.9 | −1.4% | +1.8% |
| 30 | 25 | 14 | +3.2 | 0.0 | +0.8% | −2.4% |
| 60 | 21 | 13 | +3.0 | +5.2 | −0.2% | −3.1% |

- **In plain words:** over 30 and 60 sessions, a little over half the ideas beat the Nifty, by
  about 3 points on average. Most of that came from the Nifty falling: the ideas themselves were
  about flat. Over 10 sessions they lagged the Nifty by about 3 points. On 11 Oct the count at 30
  sessions was 13 of 21; it is now 14 of 25.
- **By month added:** at 10 sessions, October's 8 ideas beat the Nifty once, with a mean of −15.5
  points (median −5.3), so at least one fell hard. At 30 sessions: July 6 of 10 (mean +1.5),
  August 7 of 11 (+7.4), September 1 of 4 (−4.2). At 60 sessions: July 7 of 10 (+7.5), August 6
  of 11 (−1.1).
- **Conviction, split at the median (0.62):** at 30 sessions the higher half beat the Nifty 9
  times in 14 (mean +5.2) and the lower half 5 in 11 (+0.7). At 60 sessions the order reverses: 7
  in 12 (+1.1) against 6 in 9 (+5.6). These small numbers show no consistent order. PR-017 and
  PR-018 measure it properly.
- **The shelf now:** 56 ideas, 20 active and 36 dropped.
- It is a record, not a gate (the card): on paper money, buying is the test.

### The book before the switch's first run

- 2 holdings; the autopilot on; cash kept; the last autopilot run reviewed the 12 Nov session.
- 84 value points. The first, 11 Jul: ₹10,00,000, 98.9% invested. The last, 12 Nov: equity
  ₹9,82,408, cash ₹8,28,910, 15.6% invested, capital put in ₹10,00,000 (−1.8% since 11 Jul).
- Since 1 Nov: one buy, one sale and one dividend, the last on 11 Nov.
- The value points carry no Nifty close. `PR-014-R1` reads the NIFTY 50 for the same dates from
  the auditor's benchmark series.
- **This is `PR-014-R1`'s baseline:** the 12 Nov point is the last before the switch acted.

### Step 8: three dated checks, in STATE

| Check | Due | What it reads |
| --- | --- | --- |
| `PR-014-D1`, the door read | From Tue 1 Dec 2026, after Monday 30 Nov's 16:30 review: the 10th distinct session reviewed with the switch on (13, 16–20, 23 and 25–27 Nov; Tue 24 Nov is an NSE holiday) | Per day: ideas offered, bought, and not bought by outcome. If more than a third of the BUY ideas offered were refused "above entry band", a 2-point card for the band; otherwise closed as not occurring. The reason that most often stopped the run. PR-019 starts after it. |
| `PR-014-R1`, results at 4 weeks | From Mon 14 Dec 2026, after its 16:30 review | Share invested, holdings, the book against the NIFTY 50 from the 12 Nov baseline, closed trades by exit reason, refusal counts; which paused cards' start conditions are met. PR-020 starts after it. |
| `PR-014-R2`, results at 8 weeks | From Mon 11 Jan 2027, after its 16:30 review | The same figures. The owner decides on PR-015's exit rule, the factor engine, the learning rebuild, the daily price-path loop, and CLEAN-006 (CLEAN-003's sector-prompt rule). |

### Step 9: the deferred setup, reminded

In this conversation's closing message: Railway alerts, the OpenRouter key's monthly limit,
Healthchecks.io with Telegram, and SA-007's off-site backup bucket. The owner chose on 24 and 29
Sep to do them at the end of the PI.

### The documents say the switch is on

- **KT:** header `1913017`, edition 2026-11-15. Section 1's paragraph now says production runs
  the inspected code, and a new "Idle cash" row gives the switch and the book before it. Section
  6: the shipped configuration switches deployment on for `primary`. Section 11: the planned work
  is reading what deployment does, and PR-015 no longer waits on the switch. Section 12's order
  paragraph. `check_kt_docs`: `errors: []`. The PDF has 72 pages, source digest `329e3143`. The
  row's label is "Idle cash" because "deployment" broke across lines in the table's narrow cell;
  the text layer was read back after the rebuild.
- **AUTOPILOT_GUIDE:** section 7 (the shipped configuration), section 13's `portfolio.overrides`
  row, section 16.
- **ARCHITECTURE:** the planned "Portfolio economics" line.
- **TEAM_TESTING_GUIDE:** 06-O and 07-Q deployed 15 Nov; 07-G switched on.
- **Not edited:** PRODUCT_MAP's row, which describes the code ("Off unless switched on").

### Full suite

Run once on the working tree with this conversation's edits:
**6,456 passed / 12 skipped / 1 xfailed / 0 failed, return code 0, 17m33s (21:16-21:34 IST)**. Command: `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests`; the
hermetic boundary blocks the network. `git status` was the same before and after the run. The
bookkeeping files changed after the run started; no test reads them.

### Committed, not pushed

At the owner's word ("ya go ahead and commit", Mon 16 Nov about 08:30 IST), one docs commit holds this
section, the morning's records and the two planning sessions' files. It is not pushed: a
docs-only push redeploys the container, so it goes after Monday's 16:30 run, at the owner's word.

### Next: step 7

From about 17:10 IST on Monday 16 Nov, after the first run with the switch on. From Git Bash in
the repository:

```text
railway ssh "cd /app && echo $(gzip -9c analysis_data/pr014/step7_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

It prints every run's `deployment` record since the switch-on (what was bought, why the run
stopped, each offered idea's outcome by symbol), that day's transactions, the book after the
run, and the nightly jobs of 15 Nov. It was dry-run on a made-up fixture and writes nothing.
After step 7 is recorded, PR-014 is accepted in the light lane and becomes `done`; its three
checks stay pending.

## Conversation 3: Tuesday 17 Nov, from about 06:24 IST

Session `stockagent-main-35` [341d05], a new conversation opened with "continue". `origin/main`
was `1913017` after a fetch; `main` was `2f0c777`, 1 ahead. Peers `-1a`, `-6d`, `-31` and `-17`
were idle. Lane: light (rollout). The owner chose to run step 7's probe and paste the output,
and asked in the same conversation for FIX-032 to be committed and pushed ("commit and
push now"); that push is recorded in STATE and HANDOFF, not here.

### Step 7: the first run with deployment on

The owner ran `analysis_data/pr014/step7_probe.py` through `railway ssh` at 06:38 IST (the form in
"Next: step 7" above) and pasted its output. It opens files read-only and writes nothing; it
printed counts, symbols and the book's own paper figures. The output is kept under the ignored
`analysis_data/pr014/step7/`.

Monday 16 Nov's 16:30 job reviewed the session of Friday 13 Nov and finished at 17:01 IST:
18 stocks required, 18 completed, none degraded, gated, skipped or failed; news for all 18; the
pipeline completed. Its digest (`2026-11-13.json`) carries the first `deployment` record:

| | Before | After |
| --- | --- | --- |
| Holdings | 2 | 3 |
| Invested | 15.7% | 22.3% |
| Cash | | ₹7,63,937 |

- **Regime RISK_ON, so the target was 80% of equity** (₹7,86,379 of ₹9,82,974). One position asks
  for the NORMAL share over the 12 holdings aimed for: ₹65,532.
- **Bought one stock: COFORGE, ₹64,896**, booked at Friday 13 Nov's close as the design books every
  run's trades (the reviewed session's close). The ledger has this one `BUY` (`DEPLOY`) since the
  switch, and no sale.
- **Why it stopped:** "no further qualifying idea"; "3 holdings, below the 10 aimed for: only 1
  qualifying idea"; "1 idea already held". Two ideas were offered: COFORGE (bought) and UNIONBANK
  (already held).
- **The book after the run:** equity ₹9,82,897 at the 13 Nov point, against ₹10,00,000 put in
  (−1.7%); 3 holdings; 22.3% invested.

**In plain words:** the switch works. It bought the one idea that qualified, at the size the rule
asks for, and said why it stopped. What held it back is the supply of ideas: of the 20 active
shelf ideas counted on 15 Nov, only 2 reached the buy step, so ₹7.64 L stays in cash while the
target asks for about ₹7.86 L invested.

**The door upstream of the record.** The `deployment` record lists only the ideas the day's buy
list offered (`core/discovery/candidates.py`). An idea the list leaves out (a deep dive older
than the re-dive age, a dive after the session's close, a verdict that is not a BUY, no sector
key named, a stock sold since) is in no count. `PR-014-D1` as written counts only offered ideas,
so it could not see this door. Delegated call, recorded: D1 also counts the shelf's active ideas
that were not offered, by the reason the list left them out, and names the door that kept the most
money in cash. `step7_probe.py` does not read this; the D1 conversation extends it (the shelf
file and the list's own rules, read-only).

### The nightly jobs of 16 Nov

- **Audit (23:45):** 37 rows graded, 2,415 already present, none unpriceable, 2,394 pending.
- **Backup (23:30):** 3,619 files, 19,549,981 bytes, `emailed: false`. The code tries the email
  copy for an archive up to 20 MiB (`services/data/backup.py`, `EMAIL_MAX_BYTES`), but base64 makes
  a 19.5 MB attachment about 26 MB, over Gmail's 25 MB limit, so the send most likely failed
  (inference from the code; the send's error was not read). The archive grows each night; above
  20 MiB the email is not tried. With SA-007's off-site bucket deferred, that mail was the only
  copy off the Railway volume. Recorded as [BACKLOG](../BACKLOG.md) B-7.
- **Not read:** Atlas's 23:00 to 23:20 jobs, and whether the weekly review's mail was delivered.

### Accepted

PR-014 is accepted in the light lane, **without a fresh-session review** (AGENTS.md step 4: a
rollout story that changes one setting the owner authorized). Its steps:

| Step | Done |
| --- | --- |
| 1. FIX-030-M1 | Passed, the owner's read, 15 Nov |
| 2. Commit FIX-031 | `899526a` and `7487104`, 15 Nov |
| 3. Full suite | 6,456 passed / 0 failed, 15 Nov |
| 4. Push | `1913017`, 15 Nov 07:16 IST; the first jobs ran on it |
| 5. The paper lane's record | Conversation 2 |
| 6. The switch | `portfolio.overrides.primary.deploy_idle_cash: true`, in step 4's push |
| 7. The first run's record | This section |
| 8. Dated checks | `PR-014-D1` (amended above), `R1`, `R2` in STATE |
| 9. Deferred setup reminded | Conversation 2 |

The full suite in this conversation ran once, on the committed tree `62d36ce` before the FIX-032
push, which holds the switch's configuration unchanged: **6,748 passed / 12 skipped / 1 xfailed /
1 failed, return code 1, 25m10s (06:32-06:57 IST)**. The one failure is the Windows file-lock flake
(`PermissionError: [WinError 5]` on `os.replace` in the test's own temp folder) in
`tests/unit/intelligence/rl/test_store_migration_sa009.py::test_a_refused_store_is_retried_and_the_status_never_overstates`.
Its file passed 5 of 5 alone (22 tests each), and nothing under `core/intelligence/rl/stores/` or
its tests changed since `2f0c777`. `git status` was the same before and after. The project guards
ran in it, and `check_kt_docs` gives `errors: []` after this record's KT edit. STATE: PR-014 `done`;
production `pending_observation` until `PR-014-D1`, `R1` and `R2` are read. Next: PR-033.
