# Current handoff - 2026-11-18 (FIX-015 implemented on its branch, awaiting its fresh review; PR-035 waits for your word)

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

- **Next `continue`: FIX-015's fresh review** (REVIEW.md), on the branch `story/FIX-015`
  (commit `b159073`, local to the code-server, not pushed), in a detached worktree. On acceptance,
  merge it into `main`; `main` holds only accepted work. Then the next ready story in STATE's
  order: PR-015 (after FIX-015), PR-039, PR-005. PR-036, PR-037 and PR-038 wait for PR-035.
- **Git:** `main` carries `8f47a0d` (PR-035's probe), `64b3cbb` (CLEAN-002) and this phase's
  records (FIX-015's receipt and manifest, STATE, HANDOFF, CLEAN-002's measure), all docs; push
  pending until the full suite passes on them in the 00:10-06:20 IST window (the autopilot does
  it between phases). If `origin/main` is still `d2f45cd`, they are not pushed.
- **Nothing is uncommitted or held.** Nothing in production was read or changed since the push of
  17 Nov 17:50 IST.
- **The investment track** you set on 17 Nov, in STATE's order: PR-035, PR-036, PR-037, FIX-015,
  PR-015, PR-038, PR-039, PR-005, then PR-033 and PR-034. The reasons and the provisional numbers
  are in the archive's entry "17 Nov: ₹1 crore in 20 to 30 holdings becomes the plan".

## Waits for you

- **PR-035's production read:** how and when are in its entry below.
- **`CLEAN-007-W1`, from Wed 18 Nov:** did a "StockAgent nightly backup" mail arrive for the night
  of 17 Nov? None should. The first `continue` on or after that day asks you (STATE's row).
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
| Mon 14 Dec | `PR-014-R1` | results at 4 weeks; which paused cards to promote |
| Mon 11 Jan 2027 | `PR-014-R2` | results at 8 weeks; whether to promote CLEAN-006 |

Deployed stories still `pending_observation` without a dated row get one from PR-033.

## 17-18 Nov, night (autopilot): FIX-015 implemented on `story/FIX-015`; awaiting its fresh review

- **Autopilot session `1117-2344-p3`**, a `continue` on the code-server from about 23:44 IST.
  Decision path (when a holding is sold), so the code is on `story/FIX-015` (`b159073`), not on
  `main`. Receipt: [evidence/FIX-015-implementation.md](evidence/FIX-015-implementation.md).
- **The change:** the advisor reads the re-forecast's `trigger` key, not its sentence.
  `shock_reforecast` counts `external_shock` and `preopen_shock` only, never `thesis_break`, at the
  first two closes after the re-forecast was made. Example: the review of Monday re-forecasts on a
  shock at Tuesday 16:45 to a path ending 10% below the close: Wednesday's and Thursday's decisions
  sell; Friday's does not.
- **One departure from the card (F15-D1):** the window counts from when the re-forecast was made,
  not from its date. The daily review dates its re-forecast the session it reviewed (the day
  before it runs), so the card's "dated the review day or the session before" would never let a
  daily-review shock fire. The fresh review should press on it.
- **Tests:** 42 story tests; 4 mutants caught; PR-009's file unchanged; full suite passed on the
  branch. Nothing in production was read or changed.

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
