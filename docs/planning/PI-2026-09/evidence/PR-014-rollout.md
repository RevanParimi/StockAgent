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
| 3 | Full suite on the tree to be pushed | Recorded under "Full suite" |
| 4 | Push: deploys FIX-030, FIX-031 and CLEAN-001 | Not started: waits for step 1 and a time the owner agrees |
| 5 | Read the paper lane's record | Not started |
| 6 | Switch on (`portfolio.overrides.primary.deploy_idle_cash: true`) | Not started |
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

It runs on the docs commit, the tree to be pushed. The result is written here after the run.

### Stopped at step 4

The push deploys FIX-030, FIX-031 and CLEAN-001 together and rebuilds every unpinned package. It
waits for step 1 and for a time the owner agrees. The switch is off.
