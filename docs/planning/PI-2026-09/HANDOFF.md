# Current handoff - 2026-11-19 (PR-005 implemented on `story/PR-005`, its fresh review next outside a window; in a push window PR-015 switches, PR-036 ships, then the ₹90 L deposit)

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
  [STATE-history-archive.json](STATE-history-archive.json). A `done` story keeps its card in
  STATE; the rest of its entry moves word for word to
  [STATE-tasks-archive.json](STATE-tasks-archive.json) with `scripts/docs/archive_done_tasks.py`.
- **The archives** are read only when a card points there. The standing rules follow this section.

## Now

- **Next `continue`, in a push window** (00:10–06:20 IST, not on the 1st, not 03:00–04:00 on
  Mondays; the next opens Fri 20 Nov 00:10): **PR-015's switch** (your word, 18 Nov about 07:05
  IST): merge `story/PR-015` (`12b7901`) into `main` (one conflict: KT section 11's table, "Idle
  cash" rewritten on `main`, "Exit rule" added by PR-015; keep both), the full suite on the
  exact commit, push, check the deploy and `/health`, add `PR-015-W1`
  ([evidence/PR-015-rollout.md](evidence/PR-015-rollout.md)).
- **PR-036 is live and the ₹90 L is in** (19 Nov): the runner pushed `2e995fe` at 05:25 IST
  (deploy SUCCESS, `/health` 200), without PR-015's switch, since no session ran in the window
  after the night's last phase. The deposit was made at 06:34 IST at your confirmation: ₹1 crore
  put in, cash ₹95,04,483, 7 holdings ([evidence/PR-036.md](evidence/PR-036.md), "Rollout").
  Next, read-only: today's 16:30 run's `deployment` record (position about ₹3,20,000, at most 5
  bought; the receipt's step 4); `PR-036-W5` and `-W10` keep their dates.
- **Outside a window: PR-005's fresh review** ([REVIEW.md](REVIEW.md)) of `4407b13` on
  `story/PR-005` ([evidence/PR-005-implementation.md](evidence/PR-005-implementation.md)). It
  merges into `main` only on acceptance; its backfill runs only at your word.
- **PR-038 is blocked on your word for its read** ([evidence/PR-038.md](evidence/PR-038.md));
  its rule is fixed there. If the limit ships, it is built on `story/PR-038` after PR-015.
- **PR-037 is accepted** (18 Nov, fresh review): `d6e5777` on `story/PR-037`, not merged; it
  merges at your word (below), cleanly with or without PR-015.
- **PR-039 is accepted and deployed** (19 Nov); its report runs at your word.
- **PR-035's read:** the door that stays is "no sector key named" (five ideas re-dived Sat
  21 Nov; B-13). **FIX-015 is live** since 18 Nov 00:28 IST.
- **Git:** `main` = `origin/main` = `2e995fe` before this session's records (one docs commit,
  push pending to Fri 20 Nov 00:10). `story/PR-015`, `story/PR-037` and `story/PR-005` are
  local only.
- **The investment track** in STATE's order: PR-035, PR-036, PR-037 (held), FIX-015, PR-015,
  PR-038 (blocked: the read), PR-039, PR-005 (review), then PR-033 and PR-034.

## Waits for you

- **PR-038's read:** say "run the PR-038 read" in a session on the code-server (read-only; the
  commands and the hours to avoid are in its receipt, with the rule that decides).
- **PR-037's rollout** (the card: "at the owner's word"; its review accepted it on 18 Nov): may
  it ship with a push in a job-free window, and may a session then make the one catch-up
  discovery run (`POST /discovery/run`, a weekday 09:30-14:00 IST, so the shelf fills that week
  instead of over three Saturdays)? It is a 45-idea shelf, 6 a sector, 45 deep dives a week (15
  kept for new companies); the 0.55 bar does not move; about $2.6 a month more model cost. A
  catch-up run on Monday to Wednesday is first bought a session sooner than one on Thursday.
- **PR-039's report, now deployed:** say "run the PR-039 report" (read-only; the
  command is in its receipt). If place 1 or 2 loses more than a quarter of the risers, that
  session writes the card, with a money example.
- **PR-005's backfill**, after its acceptance and deploy: say "run the PR-005 backfill" (a dry
  run, then `--apply`: one model call per holding; the command is in its receipt).
- **Optional:** the weekly watchdog line "No off-site copy has ever been confirmed" stays while it
  is true; removing it is a registry edit you approve separately.

## Watched, and from when

Each row, with its command, its pass rule and the conversation that runs it, is in STATE
`pending_production_checks`.

| From | Row | What |
|---|---|---|
| Tue 24 Nov | `FIX-032-W1` | your re-run of FIX-032's probe |
| Thu 26 Nov* | `PR-036-W5` | share invested and holdings, 5 sessions after the deposit |
| Tue 1 Dec | `PR-014-D1` | the door read: what the buy list offered and refused (and BACKLOG B-13) |
| Tue 1 Dec | `FIX-015-W1` | every shock sale since the deploy, read with `PR-014-D1` |
| Thu 3 Dec* | `PR-036-W10` | share invested and holdings, 10 sessions after the deposit |
| Tue 1 Dec† | `PR-037-W2` | the shelf, ideas offered a day and holdings after two Saturdays; BACKLOG B-14 |
| Mon 14 Dec | `PR-014-R1` | results at 4 weeks; which paused cards to promote |
| Mon 11 Jan 2027 | `PR-014-R2` | results at 8 weeks; whether to promote CLEAN-006 |

\* If the deposit is recorded on Thu 19 Nov; a later deposit moves both. † If PR-037 is deployed
and its catch-up run made by Fri 20 Nov; a later deploy moves it by as many weeks. `PR-014-D1`, `R1` and
`R2` keep their dates; their baseline note says capital changes on the deposit day.

Deployed stories still `pending_observation` without a dated row get one from PR-033.

## 18 Nov, night (autopilot): PR-015 prepared on `story/PR-015`; the switch waits for your word

- **Autopilot `1118-0029-p5`**, code-server, from about 00:29 IST; `main` = `8422a23`.
- **Step 1 confirmed from the code:** under `evidence` both verdicts are still recorded in
  `exit_shadow.jsonl`; the thesis review still runs; the scorecard reads every row.
- **`12b7901` on `story/PR-015`:** the setting and the living documents (KT sections 1, 3, 4, 6,
  11, 12; AUTOPILOT_GUIDE; README; guide case 07-L). On the word, the merging session follows
  the receipt's "What the owner's word starts".

## 18 Nov, morning (autopilot): PR-038's rule predeclared; its read waits for your word

- **Autopilot `1118-0848-p5`**, code-server, from about 08:48 IST; no code changed.
- **The receipt** fixes the rule before any data (above the band to 10% against inside it, mean
  30-session return against the Nifty, 15 a side) and holds the read, dry-run on a fixture.

## 19 Nov, early morning (autopilot): PR-005 implemented on `story/PR-005`; its fresh review next

- **Autopilot `1118-0904-p6`**, code-server: started 18 Nov 09:04 IST, finished 19 Nov from
  about 04:58 IST (in a window, but its planned work is a phase of its own). Decision path.
- **`4407b13` on `story/PR-005`:** each opening buy (SWITCH, deployment, manual add) writes an
  append-only case; code checks every figure; the case's invalidation price is in the buy day's
  rupees and used only between the stop and 1.5 ATR below the entry; RR-L1 and T1; pillars
  challenged by events, never a sale; `GET /portfolio/cases`; a backfill script.
- **Decisions to check in review:** the filing leg of `case_broken` is not narrowed to pillars
  (waits for PR-013); a case with no price is not replaced by the shelf's level.

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
