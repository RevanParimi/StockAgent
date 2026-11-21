# Current handoff - 2026-11-21 (NEXT FIX-033, P0: DEEPA was bought on Deepak Nitrite's analysis; then PR-017's review; PR-046 waits for the push)

## Now

- **Deployed:** `19611f1` at about 06:05 IST Sat 21 Nov (`0f16bb7f` SUCCESS, `/health` 200):
  PR-045 on `b0d6bca` (00:19, the runner: CLEAN-005, PR-013, PR-016). Cards `pending_observation`.
- **Your requests of 21 Nov:** PR-045 live (guide 11-N); PR-046 done, push pending (11-O);
  PR-007 reshaped and moved up. **The B-32 read** ([evidence](evidence/B-32-read-2026-11-21.md)):
  5 of 10 new buys went against their own analysis; DEEPA's was Deepak Nitrite's (sold). New
  FIX-033 (P0, with an automatic exit) and PR-047 (option A). You are not a user: no hand trades.
- **Next `continue`, any time:** **FIX-033** on `story/FIX-033`, its fresh review, and a push
  before Tue 24 Nov 16:30 (Saturday's dives are first bought by Tuesday's run).
- **Awaiting its fresh review:** PR-017 on `story/PR-017` (`1b01f80`,
  [receipt](evidence/PR-017-implementation.md), B-30); not on `main`.
- **Next `continue`, in a push window** (00:10–06:20 IST, not on the 1st, not 03:00–04:00 on
  Mondays; next Sun 22 Nov 00:10): **PR-015's switch** (your word, 18
  Nov): merge `story/PR-015` (`12b7901`; four KT conflict hunks, sections 1, 3, 4 and 11: keep
  both as in [PR-005's review](evidence/PR-005-review.md), "Decision"), the full suite on the
  exact commit, push, deploy and `/health`, `PR-015-W1`
  ([rollout](evidence/PR-015-rollout.md)); then BACKLOG B-12.
- **Then, outside a window:** PR-017's fresh hard review (`REVIEW.md`), then PR-007.
  `FIX-017-W1` and `CLEAN-004-W1` are production reads: your word or your command.
- **Git:** `origin/main` = `19611f1`; `main` 2 ahead, push pending to Sun 22 Nov 00:10.
  `story/PR-015` and `story/PR-017` are local.

## Waits for you

- Nothing new. (DEEPA sold 21 Nov 07:48 at your word, ₹191.72, −9.5%; PR-047: A decided.)
- **PR-037's catch-up run**, a weekday 09:30–14:00 IST (the next is Mon 23 Nov if not today):
  say "run the PR-037 catch-up" in a session and allow it, or run from the StockAgent folder:
  `railway ssh 'python -c "import os,urllib.request as u;r=u.Request(\"http://127.0.0.1:\"+os.environ.get(\"PORT\",\"8000\")+\"/discovery/run\",method=\"POST\",headers={\"X-Scheduler-Key\":os.environ.get(\"SCHEDULER_KEY\",\"\")});print(u.urlopen(r,timeout=30).status)"'`
  (prints 202; the key never leaves the container).
- **`PR-042-W0`'s read** (read-only): `railway ssh 'printenv DECISION_GATE_MODE; python -c "import json,os,collections;p=os.path.join(os.environ.get(\"LOGS_DIR\",\"data/logs\"),\"decision_gate.jsonl\");print(dict(collections.Counter((r.get(\"mode\"),r.get(\"enforced\")) for r in map(json.loads,open(p)) if r.get(\"ts\",\"\")>=\"2026-11-19T18:47\")))"'`.
  Pass: `enforce`, and rows since the deploy read `('enforce', True)`.
- **PR-033's probe run:** say "run the PR-033 probe" (read-only; the command is in its receipt),
  and confirm the closure list: SA-001 alone.
- **PR-005's backfill:** say "run the PR-005 backfill" (a dry run, then `--apply`).
- **PR-038's re-read** (Sat 21 Nov, `PR-038-R1`) and **PR-040's walk-through** (`PR-040-W1`,
  guide 11-M).
- **Optional:** the weekly watchdog line "No off-site copy has ever been confirmed"; removing it
  is a registry edit you approve separately.

## Watched, and from when

Each row, with its command, its pass rule and the conversation that runs it, is in STATE
`pending_production_checks`.

| From | Row | What |
|---|---|---|
| Fri 20 Nov | `PR-042-W0` | the gate reads enforce: deploy and `/health` pass; the read waits for you |
| Fri 20 Nov | `PR-040-W1` | your walk-through (11-M) |
| Fri 20 Nov | `FIX-017-W1` | after the 16:30 review: the sync's data-health lines and applied ratios |
| Fri 20 Nov | `CLEAN-004-W1` | after the 16:30 review: no prompt job, no control call or log |
| Sat 21 Nov | `CLEAN-005-W1` | after the 00:10 push: the build without `langgraph`, `analyses_failed_today`; Mon 23 Nov: the 16:30 review's log |
| Sat 21 Nov | `PR-038-R1` | the PR-038 re-read |
| Sun 22 Nov | `PR-013-W1` | after the weekly review: the scorecard's four new lines |
| Sun 22 Nov | `PR-016-W1` | after the weekly review: `executable_prices.jsonl`, the line and `paper_prices` |
| Sat 21 Nov | `PR-043-W1` | the first Saturday's shadow rows |
| Tue 24 Nov | `FIX-032-W1` | your re-run of FIX-032's probe |
| Wed 25 Nov‡ | `PR-005-W1` | the first cases written at purchase, and any price retried |
| Thu 26 Nov | `PR-036-W5` | share invested and holdings, 5 sessions after the deposit |
| Fri 27 Nov | `PR-042-W1` | a week of enforce: what it stopped; no exit or trim stopped |
| Tue 1 Dec | `PR-014-D1` | the door read: what the buy list offered and refused (and BACKLOG B-13) |
| Tue 1 Dec | `FIX-015-W1` | every shock sale since the deploy, read with `PR-014-D1` |
| Tue 1 Dec | `PR-037-W2` | the shelf, ideas offered a day and holdings after two Saturdays; BACKLOG B-14 |
| Thu 3 Dec | `PR-036-W10` | share invested and holdings, 10 sessions after the deposit |
| Fri 4 Dec | `PR-043-W2` | two engines beside Serper: which one PR-044 reads |
| by Thu 10 Dec | `PR-001-E1` | needs your eyes: member screens (guide 11-H, 11-I, 11-J) |
| Mon 14 Dec | `PR-014-R1` | results at 4 weeks; which paused cards to promote |
| Mon 11 Jan 2027 | `PR-014-R2` | results at 8 weeks; whether to promote CLEAN-006 |

‡ If that day's review opens a position; a later first buy moves it. `PR-014-D1`, `R1` and
`R2` keep their dates; their baseline note says capital changes on the deposit day.

## 20 Nov, afternoon (autopilot): PR-017 implemented; its fresh review is next

- **Autopilot `1120-1454-p6`**, from about 14:54 IST, on `7293fb4`. **`1b01f80`:** every dive
  kept as issued (`dives.jsonl`, seeded once on the first Saturday after the deploy); the bare
  judge (20 a week); lanes `dive`, `screen`, `bare` from the next open, 10 to 180 sessions; an
  "ideas" report block and a scorecard line. To weigh: the automatic seed, and the Nifty leg
  from the close before the entry open.

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

## 19 Nov, morning (autopilot): the PR-038 read, not yet decidable

- **Autopilot `1119-0745-p2`**, from about 07:45 IST, read-only, at your word. Against the NIFTY
  50 at 10 sessions: inside the band −7.9% (n 19), above it to 10% −12.1% (n 14 of 15); likely an
  early fail. A 10% limit adds 5 of 43 BUY dives (about ₹16 L).
- **For `PR-014-R1`:** these Sep-Nov ideas trailed the Nifty wherever the price stood
  (inside the band, 30 sessions: −13.0%) while it rose 12.7% from 9 Oct.

## 19 Nov, afternoon (autopilot): PR-033 phase 1, the September-October half

- **Autopilot `1119-1608-p2`**, no production read. 31 stories shaped; six stale labels corrected;
  SA-003 and SA-005 verified; `PR-001-E1` needs your eyes; SA-001's closure proposed. After
  phase 2, your word runs the one read-only probe (dry run passed).

## 19 Nov, evening (autopilot): PR-033 phase 2, the November half

- **Autopilot `1119-1629-p1`**, no production read. 15 November deploys shaped and in the same
  probe (dry run: 2 passed); CLEAN-007 verified from `CLEAN-007-W1`; no November closure.

# START HERE — standing rules

These opened the old "START HERE — resume checklist, in order"; its dated entries are in the archive.

**Which file holds what** (AGENTS.md, "Continuing the active PI", step 5):

- **The story's receipt** (`evidence/<ID>.md`) holds the detail of a phase: tests, manifest,
  digests, findings and commands.
- **The current section** (the first `#` section, above these rules) says what is true now and
  what comes next, in at most 8 KB: the next step, what
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
- **The archives** are read only when a card points there.

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
