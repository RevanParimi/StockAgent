# Current handoff - 2026-11-18 (PR-015 prepared and held for your word; PR-039 next; PR-035 waits for your word)

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

- **Next `continue`: PR-039** (where the funnel lost the stocks that rose; light, a report; profit
  step: measure). It is the first ready story in STATE's order: PR-035 and PR-015 wait for your
  word, and PR-036, PR-037 and PR-038 wait for PR-035. Then PR-005.
- **PR-015 is prepared and held** on the branch `story/PR-015` (`12b7901`, local to the
  code-server): `advisor.exit_rule: evidence` and its living documents; the full suite passed on
  it. It is not on `main`, because pushing `main` switches which rule sells. Say "switch PR-015"
  and the next session in a push window merges it, runs the suite, pushes and checks the deploy.
  Example: bought at ₹500, a market fall takes it to ₹480 and the thesis review says "not
  intact"; today it is sold at ₹480, after the switch it is kept unless a filing, a SELL verdict
  or its invalidation price (₹455) says the case broke. Receipt:
  [evidence/PR-015-rollout.md](evidence/PR-015-rollout.md).
- **FIX-015 is live:** `8422a23` deployed on 18 Nov at 00:28 IST (`/health` 200, again at 00:32).
  KT section 1 says so (`4fd57ab`), and AUTOPILOT_GUIDE 3.2 no longer lists `thesis_break` among
  the shock exit's triggers.
- **New backlog entry B-12:** after the switch, the scorecard's gate sentence still says the
  evidence rule "may replace" the price-path rule; it waits for PR-013.
- **Git:** `main` carries `4fd57ab` and this phase's records, pushed in this window if the full
  suite passes on the exact commit (the result is in SESSION_LOG.md and goes into STATE with the
  next phase). `story/PR-015` is not pushed.
- **Nothing is uncommitted.** Nothing in production was read or changed but `/health` and
  `railway status`.
- **The investment track** you set on 17 Nov, in STATE's order: PR-035, PR-036, PR-037, FIX-015
  (done), PR-015, PR-038, PR-039, PR-005, then PR-033 and PR-034. The reasons and the provisional
  numbers are in the archive's entry "17 Nov: ₹1 crore in 20 to 30 holdings becomes the plan".

## Waits for you

- **PR-015's switch:** say "switch PR-015". Recommended soon: until then the price-path rule keeps
  deciding sales, and the 8-week judgment (`PR-014-R2`, from 11 Jan) has fewer weeks of the
  evidence rule to read. Rollback is one setting (`shadow`) and a push.
- **PR-035's production read:** how and when are in its entry below.
- **`CLEAN-007-W1`:** did a "StockAgent nightly backup" mail arrive for the night of 17 Nov? None
  should. Asked on 18 Nov at about 00:30 IST; no answer yet.
- **Optional:** the weekly watchdog line "No off-site copy has ever been confirmed" stays while it
  is true; removing it is a registry edit you approve separately.

## Watched, and from when

Each row, with its command, its pass rule and the conversation that runs it, is in STATE
`pending_production_checks`.

| From | Row | What |
|---|---|---|
| Wed 18 Nov | `CLEAN-007-W1` | no backup mail for the night of 17 Nov |
| Tue 24 Nov | `FIX-032-W1` | your re-run of FIX-032's probe |
| Tue 1 Dec | `PR-014-D1` | the door read: what the buy list offered and refused |
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

## 17 Nov, night (autopilot): PR-035's probe written and dry-run; the read waits for your word

- **Autopilot session `1117-2304-p1`**, a `continue` on the code-server from about 23:04 IST.
  `main` = `origin/main` = `d2f45cd`. This machine has no `analysis_data/` from the laptop, so the
  probe was written again from the card.
- **The probe** (`analysis_data/pr035/invest_probe.py`, on the code-server): the door per review
  session since 13 Nov, using the buy list's own code on the shelf as it stood at each run; the
  entry band (B-3); the last 8 Saturdays' yield; the load and the unit costs. Read-only, counts
  and symbols only. Receipt: [evidence/PR-035.md](evidence/PR-035.md).
- **Dry run:** on a made-up fixture with one idea per door, through the exact production command
  form, every row printed as expected and nothing in the fixture changed.
- **Needs you:** say "run the PR-035 probe" in a session on the code-server, or run the command in
  the receipt and paste the output. Best before Saturday 21 Nov 12:00 IST; not 16:30-17:10.
- **STATE:** PR-035 `blocked` on that word; `active_task` null; `next_task` CLEAN-002 (the next
  ready story). `next_phase` is now short; its old text repeated this file.
- **Nothing in production was read or changed.** Docs only; the full suite was not run.
- **Next `continue`:** CLEAN-002, unless you have given the word, then PR-035 first.

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
  writing STATE or HANDOFF: `main` may have moved overnight.
