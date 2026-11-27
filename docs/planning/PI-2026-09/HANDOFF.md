# Current handoff - 2026-11-27 (NEXT PR-032; PR-041's run waits for you; push pending)

## Now

- **Deployed:** `69e7c28` (MAP-002), pushed 06:05 IST Fri 27 Nov (`8624f234` SUCCESS, `/health`
  200 at 08:52, CI green). `809a5ea` (03:59) brought OPS, PR-047 and MAP-001; B-12's
  wording shows Sun 29 Nov. The evidence exit rule decides since 23 Nov; PR-015, PR-017,
  FIX-033 and PR-046 stay `pending_observation`.
- **Accepted:** [PR-047](evidence/PR-047-review.md) (B-42: a top-up reads neither verdict,
  `PR-014-R1`), [PR-007](evidence/PR-007-implementation.md),
  [PR-018](evidence/PR-018-implementation.md).
- **PR-041** ([receipt](evidence/PR-041.md)): built and checked; **blocked** on its one
  production run.
- **Box:** full suite only via `scripts/ci/guarded_suite.py`; limit 8 GB. After a redeploy
  check `~/devbox/boot.log` (the Chromium reinstall is unproven).
- **Next `continue`:** **PR-032** (decision path: Opus).
- **Production reads, your word:** `FIX-017-W1`, `CLEAN-004-W1`, `FIX-033-W1`, `PR-015-W1`.
- **Git:** `origin/main` = `69e7c28`; unpushed on `main`: its deploy record, MAP-003 to MAP-005,
  PR-007, PR-018 and PR-041. Push from 00:10 IST Sat 28 Nov after the guarded suite (B-53 and
  B-59 are flaky in its browser step); then check the deploy, `/health` and CI's browser job (B-46).

## Waits for you

- **PR-041's run** (read-only, once the push has deployed; not 16:25–17:15 IST on a weekday or
  12:00–15:00 on a Saturday): say "run the PR-041 report". To change its rule, say so first
  (B-58); silence keeps it.
- **PR-018, before its first look** (6 Dec at the earliest): its rule counts dives, not stocks,
  and looks never stop. Keep it, count one dive per stock a look, or also cap the looks
  (B-54, B-55); silence keeps it.
- **[The map](../../architecture-map/index.html)'s walk-through** (guide 11-P), on a laptop and
  a phone.
- **PR-007:** after its first review, read the reasons (guide 11-Q) and keep three examples; for
  earlier trades say "run the PR-007 backfill" (a dry run, then `--apply`).
- **PR-047's read** (read-only; from Tue 1 Dec, best Sat 12 or Sun 13 Dec, before `PR-014-R1`):
  say "run the PR-047 measure"; command in its receipt.
- **PR-037's catch-up run**, a weekday 09:30–14:00 IST: say "run the PR-037 catch-up" in a
  session and allow it, or run from the StockAgent folder:
  `railway ssh 'python -c "import os,urllib.request as u;r=u.Request(\"http://127.0.0.1:\"+os.environ.get(\"PORT\",\"8000\")+\"/discovery/run\",method=\"POST\",headers={\"X-Scheduler-Key\":os.environ.get(\"SCHEDULER_KEY\",\"\")});print(u.urlopen(r,timeout=30).status)"'`
  (prints 202; the key never leaves the container).
- **`PR-042-W0`'s read** (read-only): `railway ssh 'printenv DECISION_GATE_MODE; python -c "import json,os,collections;p=os.path.join(os.environ.get(\"LOGS_DIR\",\"data/logs\"),\"decision_gate.jsonl\");print(dict(collections.Counter((r.get(\"mode\"),r.get(\"enforced\")) for r in map(json.loads,open(p)) if r.get(\"ts\",\"\")>=\"2026-11-19T18:47\")))"'`.
  Pass: `enforce`, and rows since the deploy read `('enforce', True)`.
- **PR-033's probe run:** say "run the PR-033 probe" (read-only; the command is in its receipt),
  and confirm the closure list: SA-001 alone.
- **PR-005's backfill:** say "run the PR-005 backfill" (a dry run, then `--apply`).
- **PR-038's re-read** (Sat 21 Nov, `PR-038-R1`) and **PR-040's walk-through** (`PR-040-W1`,
  guide 11-M).
- **Optional:** remove the weekly off-site-copy watchdog line.

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
| Sat 28 Nov | `PR-017-W1` | the first Saturday run and that night's audit: `dives.jsonl` seeded, the idea lanes graded; B-33's two lines |
| Mon 23 Nov | `FIX-033-W1` | after the 16:30 review: no buy on another company's analysis; Sat 28 Nov: `hygiene.analyses`, `other_company` |
| Mon 23 Nov | `PR-015-W1` | after the 16:30 review: every shadow row `evidence`, one per holding; no SELL on `thesis_break` |
| Tue 24 Nov | `FIX-032-W1` | your re-run of FIX-032's probe |
| Wed 25 Nov‡ | `PR-005-W1` | the first cases written at purchase, and any price retried |
| Thu 26 Nov | `PR-036-W5` | share invested and holdings, 5 sessions after the deposit |
| Fri 27 Nov | `PR-042-W1` | a week of enforce: what it stopped; no exit or trim stopped |
| Fri 27 Nov | `PR-047-W1` | after the 16:30 review: no buy whose own model did not say BUY; Sat 28 Nov: `hygiene.model_verdicts`, `not_buy_model` |
| first review after deploy | `PR-007-W1` | the stored words, the model's share and tokens (your word) |
| after deploy | `PR-041-W1` | the screen-cut report's one run (your word); B-57's count |
| Tue 1 Dec | `PR-047-S1` | PR-047's measure, at your word; best 12-13 Dec |
| Tue 1 Dec | `PR-014-D1` | the door read: what the buy list offered and refused (and BACKLOG B-13) |
| Tue 1 Dec | `FIX-015-W1` | every shock sale since the deploy, read with `PR-014-D1` |
| Tue 1 Dec | `PR-037-W2` | the shelf, ideas offered a day and holdings after two Saturdays; BACKLOG B-14 |
| Thu 3 Dec | `PR-036-W10` | share invested and holdings, 10 sessions after the deposit |
| Fri 4 Dec | `PR-043-W2` | two engines beside Serper: which one PR-044 reads |
| Sun 6 Dec† | `PR-018-W1` | the conviction check line, then each month's first Sunday |
| by Thu 10 Dec | `PR-001-E1` | needs your eyes: member screens (guide 11-H, 11-I, 11-J) |
| Mon 14 Dec | `PR-014-R1` | results at 4 weeks; which paused cards to promote |
| Mon 11 Jan 2027 | `PR-014-R2` | results at 8 weeks; whether to promote CLEAN-006 |

† If deployed by then; else 3 Jan. ‡ If that day's review opens a position; a later first buy moves it. `PR-014-D1`, `R1` and
`R2` keep their dates; their baseline note says capital changes on the deposit day.

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

- **Regenerate the architecture map with any code change** (a `.py` under `core/`, `services/`,
  `src/backend/` or `scripts/`, `config.yaml`, or the map's curated files): run
  `python tools/architecture_map/model/generate.py` and commit what it writes, or CI's guard and
  the suite fail with the reason and the fix. A conflict on `model.json` is resolved the same way
  (MAP-001; MAP-005 adds the AGENTS.md rule). **And rebuild its page** after a change to the
  curated model, a setting's default or a scheduled job: `cd tools/architecture_map/viewer &&
  npm ci && npm run build`; a test fails otherwise (MAP-002).
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
  - **Run the full suite before any push** (about 26 minutes on the laptop; on the code-server
    only through `scripts/ci/guarded_suite.py`, its memory guard). On 17 Nov a push of documents and the docs
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
