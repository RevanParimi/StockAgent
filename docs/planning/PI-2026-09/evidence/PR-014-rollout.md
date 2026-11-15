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
| 1 | `FIX-030-M1`, the Saturday counts | **Waits for the owner's read** (below) |
| 2 | Commit FIX-031, then the docs | **Done**, 14 Nov |
| 3 | Full suite on the tree to be pushed | **Done**: passed on `7487104` |
| 4 | Push: deploys FIX-030, FIX-031 and CLEAN-001 | Not started: waits for step 1 and a time the owner agrees |
| 5 | Read the paper lane's record | Not started |
| 6 | Switch on (`portfolio.overrides.primary.deploy_idle_cash: true`) | Setting made; goes out with step 4 in one push |
| 7 | The first run's `deployment` record | Not started |
| 8 | Three dated checks in STATE | Not started |
| 9 | Remind the owner of the deferred setup actions | Not started |

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
