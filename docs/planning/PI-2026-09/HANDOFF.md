# Current handoff - 2026-11-18 (PR-035 accepted; PR-015 has your word and switches in the next push window; PR-039 resumes)

**Which file holds what** (AGENTS.md, "Continuing the active PI", step 5):

- **The story's receipt** (`evidence/<ID>.md`) holds the detail of a phase: tests, manifest,
  digests, findings and commands.
- **This section** says what is true now and what comes next, in at most 8 KB: the next step, what
  is uncommitted or held, what is watched and from when, what waits for the owner, and the dated
  entries of stories not yet accepted, as written on their date (where they differ, "Now" holds).
  When a story is accepted, its dated entry moves word for word to the top of
  [HANDOFF-archive.md](HANDOFF-archive.md).
- **[STATE.json](STATE.json)** holds the status fields and one line of history per event.
  `next_phase` is at most 600 characters: the next first step and a pointer here. History older
  than 14 days and passed production checks move word for word to
  [STATE-history-archive.json](STATE-history-archive.json).
- **The archives** are read only when a card points there. The standing rules follow this section.

## Now

- **Next `continue`, in a push window** (00:10–06:20 IST, not on the 1st, not 03:00–04:00 on
  Mondays): **PR-015's switch first.** You gave the word on 18 Nov at about 07:05 IST ("do as
  per recommendation", that is "switch PR-015"). The session merges `story/PR-015` (`12b7901`)
  into `main`, runs the full suite on the exact commit, pushes, checks the deploy and `/health`,
  and adds `PR-015-W1`, as the receipt's "What the owner's word starts" says
  ([evidence/PR-015-rollout.md](evidence/PR-015-rollout.md)).
- **Outside a window: resume PR-039** (`active_task`). It is on the local branch `story/PR-039`
  (`ac86ec3`, code-server only): `scripts/missed_risers.py`, 13 focused tests, PRODUCT_MAP, KT
  section 8, CODEBASE and guide 06-P. Autopilot `1118-0052-p6` stopped at a usage limit before the
  full suite (run it without `-n`), the receipt `evidence/PR-039.md`, STATE and HANDOFF. Then
  merge to `main`. Its production report waits for your word after the deploy.
- **Then PR-036** (₹1 crore, 25 aimed for), the next ready story in STATE's order. **You gave
  the word for its push and the ₹90 L deposit** (18 Nov, about 07:25 IST; STATE `owner_word`), in
  the card's order: settings first, pushed in a window (it may go with PR-015's push); the deposit
  only after that deploy is confirmed, from inside the container through `railway ssh`, the key
  never printed.
- **PR-035 is accepted** (18 Nov, a manual session; [evidence/PR-035.md](evidence/PR-035.md),
  phase 2). The biggest door was "dived after the session's close" (₹7,86,379 over two
  sessions; one run a week, it clears by itself). The door that stays is "no sector key named":
  five ideas, IGIL (0.70) first; FIX-030 re-dives them first on Saturday 21 Nov (BACKLOG B-13).
  The entry band kept ₹1,96,260, so PR-038 stays after PR-037. At today's ₹10 L, buying stops at
  about 11 holdings (the 80% target). PR-036 and PR-037 now carry the measured values.
- **`CLEAN-007-W1` passed** (no mail; the archive of 17 Nov, drill ok, no `emailed` field). It
  moved to the archive.
- **New:** the code-server's Railway SSH key is registered (START HERE, "The code-server").
  BACKLOG B-13 and B-14 come from PR-035's read.
- **FIX-015 is live** since 18 Nov 00:28 IST (`8422a23`).
- **Git:** this session's records are one docs commit on `main` after `6e1962f`, push pending
  until the next window (Thu 19 Nov 00:10 IST). `story/PR-015` and `story/PR-039` are local only;
  `story/FIX-015` is merged.
- **The investment track** in STATE's order: PR-035 (done), PR-036, PR-037, FIX-015 (done),
  PR-015, PR-038, PR-039, PR-005, then PR-033 and PR-034.

## Waits for you

- **PR-039's report, later:** say "run the PR-039 report" once it is deployed (read-only).
- **Optional:** the weekly watchdog line "No off-site copy has ever been confirmed" stays while it
  is true; removing it is a registry edit you approve separately.

## Watched, and from when

Each row, with its command, its pass rule and the conversation that runs it, is in STATE
`pending_production_checks`.

| From | Row | What |
|---|---|---|
| Tue 24 Nov | `FIX-032-W1` | your re-run of FIX-032's probe |
| Tue 1 Dec | `PR-014-D1` | the door read: what the buy list offered and refused (and BACKLOG B-13) |
| Tue 1 Dec | `FIX-015-W1` | every shock sale since the deploy, read with `PR-014-D1` |
| Mon 14 Dec | `PR-014-R1` | results at 4 weeks; which paused cards to promote |
| Mon 11 Jan 2027 | `PR-014-R2` | results at 8 weeks; whether to promote CLEAN-006 |

Deployed stories still `pending_observation` without a dated row get one from PR-033.

## 18 Nov, night (autopilot): PR-015 prepared on `story/PR-015`; the switch waits for your word

- **Autopilot session `1118-0029-p5`**, a `continue` on the code-server from about 00:29 IST.
  `main` = `origin/main` = `8422a23`.
- **Step 1 confirmed from the code:** under `evidence` the pipeline still decides with the
  price-path rule too and records both verdicts in `exit_shadow.jsonl`; the thesis review still
  runs; the scorecard reads every row whatever its mode. PR-009's pipeline test covers all three
  modes.
- **`12b7901` on `story/PR-015`:** the setting and the living documents (KT sections 1, 3, 4, 6,
  11, 12; AUTOPILOT_GUIDE; README; guide case 07-L). Held: the card says "at a time the owner
  agrees". On the word, the merging session follows the receipt's "What the owner's word starts".
- **STATE:** PR-015 `blocked` on that word; `next_task` PR-039.

# START HERE — standing rules

These opened the old "START HERE — resume checklist, in order"; its dated entries are in the archive.

**Working from another device** (the owner, 7 and 17 Nov: a `continue` may start on another laptop or in a cloud
session). Pull `main` first. Git carries the code, the docs, STATE, this file, every card and every receipt, so
`continue` works from a fresh clone. A fresh clone lacks only what follows:

- **Setup is automatic.** AGENTS.md's first step runs `bash scripts/setup_dev.sh --check`, and `bash scripts/setup_dev.sh`
  when something is missing. It creates `.venv` with the oldest Python from 3.11 up (the laptop keeps `.stockai`), installs
  the three requirement files, runs `npm ci` and installs Playwright's Chromium. On a new copy that took 5 min 26 s on
  17 Nov; a second run installs nothing. The suite needs no `.env` and no network (`tests/hermetic.py`, SA-005), and
  `.env` is never committed. Node.js itself and, to read production, `railway link` with a Railway login are not
  installed by the script.
- **`analysis_data/` (ignored), only on the device that wrote it:** raw diagnostics, probes and reviewer cases. Open cards name files in it:
  PR-035's `pr035/invest_probe.py`, PR-033's `pr033/watch_probe.py`, and reviewer cases named by PR-005, PR-007, PR-012,
  FIX-014, FIX-020, FIX-022, SA-031, SA-033, SA-041 and BACKLOG B-6. Where one is missing, write it again from the card's
  description and examples.
- **The assistant's notes on the laptop** (its memory folder, which no clone carries). What they hold that the
  repository's rules do not:
  - **Every push to `main` redeploys, docs-only too.** The deploy of 7 Nov took about 27 minutes. Push only at the owner's
    word, about 2 h clear of the jobs in KT section 9; safest 00:10–06:20 IST. Read the IST clock first. On the 1st, never
    before the 09:00 monthly forecast. Push with `git -c credential.username=RevanParimi push origin main`.
  - **KT, ARCHITECTURE and CODEBASE describe the current design:** no story notes, no commit, review or deploy history.
    Production facts go only in KT section 1.
  - **The owner decides from plain worked examples.** Optional technical calls are delegated: decide, record, tell.
  - **STATE.json is spliced, never re-dumped,** and repository files are written as LF bytes.
  - **Deleting lines from `milestones.yaml`** needs the owner's approval each time.
  - **Owner setup waits for rollout:** Railway alerts, the OpenRouter key limit, Healthchecks.io with Telegram, SA-007's
    backup bucket. Remind the owner then.
  - **Run the full suite before any push** (about 26 minutes on the laptop). On 17 Nov a push of documents and the docs
    check went without it, at the owner's "now", and its record says so.
  - **Other sessions may share a checkout** (eight on the laptop on 17 Nov). Before writing STATE or HANDOFF, list them
    and compare file times; run review tests in a detached `git worktree`. On any device, pull before committing and
    check `origin/main` again just before pushing.
  - **Look before calling something missing.** Search the code, the paused and removed cards and
    `docs/superpowers/specs` before saying a feature does not exist or writing a card for it. On 14 and 15 Nov three
    "missing" items already existed.
  - **Production is read only at the owner's word in the same conversation** (`railway ssh` probes). Otherwise hand
    the owner the command to run.
  - **When the owner asks to be walked through the product:** one point per reply, plain and exact, ending with "Next:"
    and the next topic.
  - **The unattended `continue` loop** (`scripts/devbox/auto_continue.sh`, a briefings file, waits at usage limits) is
    a draft on the branch `claude/serene-pascal-hm7lek`, not merged. It is the owner's tooling awaiting review: do not
    delete it.
- **The code-server** (added 17 Nov): the owner's standing instructions there, kept outside the
  repository, let its sessions commit once a phase's checks pass and push `main` without asking,
  only in the overnight window (00:10–06:20 IST, not on the 1st, not 03:00–04:00 on Mondays). Its
  unattended loop runs one `continue` phase per fresh session. On another device, fetch before
  writing STATE or HANDOFF: `main` may have moved overnight. Its own Railway SSH key,
  `railway-devbox`, is registered (the owner's word, 18 Nov), so `railway ssh` probes run from
  the StockAgent folder there, at the owner's word in the same conversation.
