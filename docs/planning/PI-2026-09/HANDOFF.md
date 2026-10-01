# Current handoff - 2026-10-01 (updated about 10:40 IST)

## START HERE — resume checklist, in order

**0. Step 0 is DONE (1 Oct, about 10:20–10:40 IST). SA-039 P3 passed, and the delegated SA-003
enforce decision is NO-GO: the gate stays in `record`.** Nothing in production changed. Check
STATE `pending_production_checks` again only if a new entry appears.

- **P3, in one example.** The 09:00 monthly forecast made 20 October envelopes, one per enabled
  ticker. Every one was made with `learning_mode=observe` (logs, deploy `14d13162`), including
  TMPV's, which the job regenerated at 09:25:53. None was made for the disabled TATAMOTORS.
  18 weight versions still equal the 26 Sep baseline. The stored field is inferred from code,
  not read from the volume. See the [activation record](evidence/SA-039-activation-2026-09-26.md),
  P3. SA-039's observation window is complete (P1 28 Sep and P2 29 Sep passed earlier).
- **The SA-003 decision, in one example.** YES Bank's June-quarter results are on file, but a
  bank's statement has no "operating income" line. The fetcher fills it with zero and marks
  fundamentals `fallback`, so the gate abstains on every bank analysis. Under `enforce`, four
  banks would get no October forecast and no learning, on fine data. The rules' measures:
  - **(a) met:** 25 of 78 analyses (28 Sep–1 Oct) would abstain, 32%. The 4 banks alone are 22%;
  - **(b) met:** 3 of 5 spot-checked abstentions had fine data (the banks);
  - **wait condition (4) not met:** only 3 review days. Because the cause is structural, the
    outcome is NO-GO rather than WAIT;
  - **F1:** 6 of 20 October envelopes abstain. **F2:** 0 `actual_close` rows.

  See the [decision record](evidence/SA-003-enforce-decision-2026-10-01.md). **Re-decide by the
  same rules** after FIX-002 and FIX-003 are deployed and at least 5 review days have rows
  issued after them: the 1 Nov forecast, or an owner-authorised regeneration of the affected
  envelopes.
- **Found at P3: TATAELXSI was analysed as TATAMOTORS.** The IT orchestrator sends managed
  tickers that are missing from its static `TICKERS` list to an LLM. At 09:16 that LLM answered
  TATAMOTORS, and TATAELXSI's October envelope was saved from a Tata Motors analysis.
  SA-008's identity gate recorded it, in record mode. The same path resolved TVSMOTOR to
  TVSMOTORS on 29 Sep, and named HAPPSTMNDS "Happy Smile Digital Ltd" today. SA-039 `observe`
  keeps the stored weights unchanged meanwhile.
- **Two routed fixes were added to the board as `todo`** (STATE, P1, 1 point each). They are
  recommended next after FIX-001's review and before SA-010:
  - [FIX-002](stories/FIX-002.md): a managed ticker resolves to itself, with no LLM call. After
    its deploy, the owner authorises regenerating TATAELXSI's October envelope;
  - [FIX-003](stories/FIX-003.md): a bank-shaped statement reads as complete, with no invented
    zero.
- **Raw diagnostics** are in ignored `analysis_data/sa039/` (`p3_*`, `gate_rows_2026092*`,
  `review_gate_rows.py`). They hold counts, tickers, reasons and run ids only.

**1. SA-007 change 1 is committed as `8663387`** at the owner's word ("ya commit and push",
about 14:37 IST). `verify SA-007-change1-manifest.json --rev 8663387` mismatches only the 3
review-edited docs, so every reviewed code and test byte is committed as reviewed.

- **The KT bump follows it.** It declares `8663387` (`check_kt_docs` errors `[]`, no linked
  source changed since it, PDF 28 pages).
- **The bump also fixes the routed status wording (the earlier review's I2)** in the KT,
  ARCHITECTURE and the guide:
  - SA-004 was deployed as `b3fb00dd` on 27 Sep;
  - SA-005's CI first ran on 28 Sep (`36453992259`, 3 of 3 jobs);
  - SA-006 was deployed as `00b94de9` on 28 Sep.
- **Pushed and deployed.** The push waited out the 14:55–15:05 jobs.
  - **The push:** `cd33fc4..e3bb6a3` at 15:06:23 IST.
  - **The deploy:** Railway `f2e23722` reached SUCCESS by 15:07:26 IST. It was a cached build,
    because `requirements.txt` did not change.
    - Boot log: 124 lines, 0 tracebacks and 0 error or warning lines; the scheduler started
      with 24 jobs.
    - `/health` returns 200 `ok`.
  - **CI:** run `36550251651` on `e3bb6a3` passed 3 of 3 jobs. Python tests on Linux / 3.11
    took 152 s, the guards 15 s and Chromium 60 s.
  - **What production should now show.** Change 1 landed before the first production run of
    `backup_recoverable`, which is Wed 30 Sep 06:30.
    - That morning's "No off-site copy has ever been confirmed" is the first weekly notice.
      **Observed Wed 30 Sep 06:30.** The owner pasted the alert: one warning, reading "…
      repeats weekly until a target is configured". `checks.py` gives that wording only when
      three things hold: the backup ran within 36 h, its restore drill passed with no warnings,
      and no off-site target is set. So the 29 Sep 23:30 backup, the first in production with a
      drill, passed it. That is inferred from the notice; `backup_status.json` was not read.
    - Thu 1 Oct to Tue 6 Oct should be silent for this entry. The Thursday check is read-only.
  - This record (STATE and HANDOFF) is uncommitted. It rides with the next commit.

**2. Next PI phase: FIX-001's fresh-session review**, in a new conversation (step 0 is done).
STATE: `active_task: FIX-001` (`review_required`), `next_task: FIX-001`. After its acceptance, the
recommended order is FIX-002, then FIX-003, then SA-010.
- **How to review it:** follow [REVIEW.md](REVIEW.md), the [FIX-001 card](stories/FIX-001.md) and
  the [receipt](evidence/FIX-001-implementation.md). `kt_manifest.py verify FIX-001-manifest.json`
  must give 0 mismatches, digest `b0d12caf…`. Rebuild the diff `3dc30945…` (16,938 bytes, 7 text
  files) against `290b3f7`.
- **The push is pending.** `290b3f7` (the rollout records) is committed locally and not pushed.
  The owner's word came at 00:38, but a 1 Oct restart before the 09:00 forecast would make the
  self-heal generate October envelopes for all 20 tickers, and the 09:00 job regenerates them
  all. So the push waits for the 1 Oct 12:05–14:55 window. FIX-001 stays uncommitted until its
  review.

**2b. Earlier plan, superseded by step 2: SA-010's implementation**, in a new conversation. Opener: `Continue`. STATE:
`active_task: null`, `next_task: SA-010`, `next_phase: implementation`. **Run step 0 first:** P3 is
due Thu 1 Oct 09:30, then the SA-003 enforce decision.
- **SA-009 change 1 was ACCEPTED** by its fresh review (about 17:50–18:15 IST; the block below).
  At the owner's word ("ya commit and push", about 22:20 IST) it is committed as `9c626a5`, with
  the KT bump after it (header `9c626a5`). **Pushed and deployed:** `e698c68..2c632e2` at
  22:24:37 IST; Railway `14d13162` SUCCESS 22:26:11 (cached build); boot log 125 lines, 0
  tracebacks, 0 error or warning lines, 24 jobs, self-heal complete in 10 s; `/health` 200 at
  22:29. CI on `2c632e2` was not read here: the owner reads the Actions page.
- SA-008 change 1 stays open. It must be accepted before any `successors` record.

**FIX-001 was IMPLEMENTED on 2026-10-01** (about 00:40–01:00 IST, in this conversation at the
owner's word: "The small price-lookup fix - go ahead as well"). It is uncommitted and not reviewed.
A same-conversation self-review was done; it is not the fresh review.
- **In one example.** On a listing day the 7-day download holds one bar. `squeeze()` turned it into
  a number, and `.dropna()` raised, so SWASTIKAIN's and ADROITIND's listing-day closes were
  discarded on 30 Sep. Now the bar is read like any other, dated its session, and cross-checked
  against NSE.
- **The change:** `daily_review._fetch_session_close._extract` and
  `close_verifier._fetch_yfinance_close`. Frames with two or more bars take the same path as
  before. A NaN last row stays a failure.
- **Checks:**
  - 10 new tests, and focused 24 passed;
  - mutations 3 of 4 caught: the original defect fails 6 tests, and M4 is equivalent;
  - full suite **4036 passed, 12 skipped, 0 failed**, `data/` unchanged;
  - `check_kt_docs` errors `[]`.
- **Docs:** KT §4 and §8 (the first production IPO rows; the skipped listing-day rows), guide
  05-G, the PDF, and the [card](stories/FIX-001.md).

**2a. The 30 Sep audit alert ("audit_nightly completed 25/27"), diagnosed from the log.** Only the
IPO lane missed: 2 listing-day rows (SWASTIKAIN, ADROITIND) got no close. The close lookup discards
a one-bar Yahoo table (`squeeze()` turns it into a number, and `.dropna()` fails). The NSE fallback
rescued ELEVATE and ARMEE, but not these two. The bug is pre-existing (1 May; also seen 29 Sep) and
reproduced locally. `close_on` shares it, so a holding on its listing day has the same gap. The
diagnosis and fix are in a note on the [SA-040](stories/SA-040.md) card; the fix waits for the
owner's word. The 23:30 backup that night was clean (drill passed, emailed; off-site unset as
expected).

**3. SA-008 and SA-009 are pushed and deployed** (the owner's word, about 13:00 IST: "ya commit
and push").
- **The commits:** SA-009 is `313e3f6`, with its KT bump `e698c68`. `verify SA-009-manifest.json
  --rev 313e3f6` mismatches exactly the 4 review-edited docs. SA-008 is `02c43f6`, with its bump
  `f443cc7`.
- **The push:** `e3bb6a3..e698c68` at 13:07:23 IST, in the 12:05–14:55 job-free window.
- **The deploy:** Railway `650bb98c` reached SUCCESS at 13:13:09 IST, a cached build, because
  `requirements.txt` did not change.
  - Boot log: 127 lines, 0 tracebacks and 0 error or warning lines. The scheduler started with
    24 jobs.
  - The self-heal skipped all 20 tickers on September's checkpoint, as expected. The new
    per-sector behaviour starts with October's first restart.
  - `/health` returned Railway's edge 404 "Application not found" for about 4½ minutes after
    SUCCESS, then 200 `ok` from 13:17:48.
- **CI:** run `36684772155` on `e698c68` passed 3 of 3 jobs: guards 13 s, Python tests on Linux /
  3.11 154 s, Chromium 112 s.
- **The owner's rollout steps (not done yet; the owner said "go ahead on the rollout recommended"
  at about 22:20 IST).** Claude cannot do them: the dashboard steps need the owner's login, and
  Claude's `railway ssh` was denied by the auto-mode classifier ("Production Reads"). So the
  owner runs each step and pastes the output. Order matters: the dashboard steps first, because
  the plan's digest pins the managed list. At the owner's request Claude wrote a helper the owner
  runs from Git Bash (ignored, local): `bash analysis_data/sa009/rollout/run.sh check` (read-only:
  TATAMOTORS/TMPV entries, learned symbols, inventory summary, plan digest with ITEM/HOLD/FLAG
  lines), then `run.sh apply <digest>` (refuses unless the fresh plan has that digest and the IST
  time is 00:10-06:20 or 12:05-14:55), and `run.sh rollback <migration id>`. It calls only the
  SA-009 modules. Tested locally on the fixture tree with the real wiring: check wrote nothing,
  apply moved the 3 strays, rollback was byte-identical.
  - **First production check (owner, about 23:35 IST, read-only).** The dashboard step was not yet
    done (TATAMOTORS enabled, TMPV absent). SA-008 L2: no managed ticker has a learned symbol, and
    `AUTO_TICKERS` is unset. The plan (`ce3556d0…`) moves 16 stores and holds or flags none:
    every `automobile/<TICKER>` copy of a ticker managed in another sector, each with its owner
    store present. The copies now hold 19–21 files and 150 conflicting graded days, against
    weights and 1–2 envelopes on 10 Sep (the writer is inferred, not verified).
  - **Apply rule given to the owner:** after the dashboard step, re-run `check`. Apply its new
    digest only if it shows `DASHBOARD STEP DONE`, `PLAN items 16 holds 0 flags 0`, and the same
    16 `ITEM` lines with the same file counts. Otherwise paste the output and do not apply.
  - **Second check (owner, about 23:55 IST) was identical:** inventory `974e6043…`, plan
    `ce3556d0…`, the same 16 items and file counts, and the dashboard step still not done. So nothing
    wrote to the 16 copies between the checks, which included the 23:45 audit.
  - **Claude approved plan `ce3556d0…`** (delegated: "go ahead on the rollout recommended"). The
    dashboard step touches none of the 16 stores, so the order can be: apply first, in 00:10–06:20,
    before any dashboard change; then the dashboard step before 09:00; then a final `check`
    (expect `DASHBOARD STEP DONE`, `PLAN items 0`, no `DUP` lines). If the dashboard step comes
    first, the digest changes, apply refuses, and the earlier rule applies to a new check.
  - **APPLIED 1 Oct 00:10:31 IST** (owner, `run.sh apply ce3556d0…`). Migration
    `20260930T184031Z-ce3556d023d3`: 16 of 16 stores `moved`, with unchanged bytes. The inventory after
    (`c1708d20…`) has 168 stores, 0 duplicate tickers, 0 duplicate envelopes or graded days (36
    and 150 conflicting before) and 0 wrong-roster stores. The undo is `run.sh rollback 20260930T184031Z-ce3556d023d3`.
    **The dashboard step as one command** (owner asked, about 00:20 IST): `run.sh dashboard` calls the
    app's own routes on localhost, with the machine key from the container's environment, never
    printed. It toggles TATAMOTORS off only if it is enabled, never calls remove, and adds TMPV
    (automobile) only if absent. It is safe to run twice, and was tested locally against a fake app.
    **Then to do (done, below):** the dashboard step before 09:00, then a final `check` (expect `DASHBOARD STEP
    DONE`, `PLAN items 0`, no `DUP`). Later, a check after October's first restart should show no
    new `automobile/<TICKER>` copy with files.
  - **ROLLOUT COMPLETE (1 Oct 00:30–00:33 IST).**
    - `run.sh dashboard`: TATAMOTORS is disabled (not removed) and TMPV is added (automobile).
      TMPV's October envelope was done at 00:32:06 (weights v0). The log since 00:00 has 0 errors.
    - Final check: `DASHBOARD STEP DONE`; 169 stores; 0 duplicates; 0 wrong-roster stores;
      plan 0 items, 0 holds, 0 flags.
    - **For P3 at 09:30:** no TATAMOTORS October envelope is expected (it is disabled). TMPV's
      envelope came from the add route at 00:32, not the 09:00 job; check that it too says `observe`.
    - **Left to observe:** October's first restart creates no `automobile/<TICKER>` copy with files
      (a later `check`); new feedback logs carry their store's sector; the scorecard lists each
      moved ticker once.
  - **SA-008:**
    - **Disable** TATAMOTORS with the toggle. **Never remove it:** removing deletes its history.
    - Add TMPV: sector `automobile`, name "Tata Motors Passenger Vehicles Ltd". The add starts
      its envelope in the background.
    - Suggested timing: any time now, before Thu 09:00, so the monthly forecast includes TMPV and
      skips TATAMOTORS. The 30 Sep 16:30 review already showed TATAMOTORS' `identity` stage once
      in production.
    - Also a read-only look at the volume's `data/yf_symbol_cache.json` (SA-008 review L2).
  - **SA-009:** run the inventory and the plan read-only on the volume, and paste the summary
    lines, the items and the holds. The commands are in the SA-009 receipt's "Rollout". Before
    approving, check `owner_store_present` on every item (review I4). Apply only by the plan's
    digest, in a job-free window after the 23:30 backup. It is best to wait until change 1 is
    deployed, so the rollback has its fixes. Change 1 is accepted but not yet committed. A plan
    made now keeps its digest after change 1 deploys (review Q6).
- **Production checks after the deploy:**
  - **today's 16:30 review, observed read-only at about 17:33 IST (the `650bb98c` log to 17:01).**
    - It graded 29 Sep for all 20 tickers in `observe`. There were 19 proposals not applied, 0
      `Weights → v` lines and 0 tracebacks.
    - The outcome was 19/20. The missing one is WELCORP with `no_envelope`, which is known and
      pre-existing.
    - SA-008's `identity` lines name only TATAMOTORS, both "would skip (record mode)": once in the
      analysis gate and twice for the review.
    - The yfinance `^CNXAUTO` "possibly delisted" errors are pre-existing: 38 lines in the 29 Sep
      review on `f2e23722`, 40 today. They belong to SA-010's benchmark work.
    - The ERROR and WARNING totals are 67 and 79, against 88 and 87 the day before;
  - still to observe: new October feedback logs carry their store's sector, and October's first
    restart checks each ticker's own store.

**SA-009 change 1 was ACCEPTED on 2026-09-30 by a fresh-session review** (a new conversation,
about 17:50–18:15 IST). Receipt: [SA-009-review.md](evidence/SA-009-review.md), section "Change 1
fresh-session review". No SA-039 check was due. Nothing was committed, pushed, deployed,
configured or sent, and no production state was read.

- **Input verified:** `7f2a4a2a…` (9 files, 0 mismatches, no unlisted change). The diff
  `e3a04386…` was rebuilt with the reviewer's own script.
- **Traced:** `rollback` touches files in only two ways. It removes an empty live directory with
  `rmdir`, and it renames back a store whose bytes equal the record. `PredictionStore` creates
  only the store's own directory on a read.
- **An example the change also fixes (probe Q1).** A rollback crashes after renaming
  `automobile/SUZLON` back, before recording it.
  - Before: every later run said `refused_quarantine_missing` and `partial`.
  - Now: the next run finds the store live with its recorded bytes (`found_live`) and reports
    `rolled_back`.
- **Checks:**
  - reviewer probes 8 of 8;
  - reviewer mutations 4 of 6 caught (RA is L1, RD is telemetry);
  - focused 45 passed;
  - full suite **4026 passed, 12 skipped, 0 failed** (5 min 16 s), `data/` unchanged;
  - broad-except OK, and `check_kt_docs` errors `[]`.
- **C1–C4 upheld.**
- **Findings.** None is critical, high or medium, and there is no code defect.
  - **L1 (low, tests; predates change 1):** no test pins that a store restored with other bytes
    (`rolled_back_changed`) keeps the run `partial`. Routed to [SA-031](stories/SA-031.md): add
    probe Q2 as a test.
  - **I1:** the KT did not state `found_live`. Fixed in KT §3.
  - **I2:** a Windows-only `os.replace` flake in `_write_lineage`. Routed to SA-031.
- **Review edits (docs only):** the status wording in the KT (§1, §3, §11, §12) and guide 04-G;
  the `found_live` sentence in KT §3; the PDF rebuilt; the SA-031 card note. `verify
  SA-009-change1-manifest.json` now mismatches exactly the KT, the PDF and the guide.

**SA-009 change 1 was IMPLEMENTED on 2026-09-30** (this conversation, about 13:15–17:45 IST,
with a pause). It is uncommitted and not reviewed. A same-conversation self-review was done; it is
not the fresh review. The receipt is the "Change 1" section of
[SA-009-implementation.md](evidence/SA-009-implementation.md).

- **What it is, in one example.** A quarantined SUZLON file was changed, and a dashboard read
  recreated an empty `automobile/SUZLON`.
  - **Before:** rollback refused SUZLON. After the file was fixed, a retry skipped SUZLON yet
    reported `rolled_back` (review L1). The empty directory alone would also have blocked it
    (L2).
  - **Now:** every run retries each store not back, after removing an empty live directory with
    `rmdir`. It reports `rolled_back` only when every store is back with its recorded bytes.
  - A store moved back by hand counts only with its recorded bytes (`found_live`).
  - The inventory's summary gains `roster_collisions` (I3).
- **Checks:**
  - 10 new tests pin the review's probes R2, R3, R5 and R8–R10 (L3);
  - focused 45 passed;
  - mutations 11 of 11 caught, including the review's four survivors;
  - full suite **4026 passed, 12 skipped, 0 failed** (4016 + 10), `data/` unchanged;
  - `check_kt_docs` errors `[]`.
- **Also recorded here:** SA-008 and SA-009 now read "deployed 2026-09-30 (`650bb98c`)" in the
  KT, ARCHITECTURE, the guide and CODEBASE.

**SA-009 was ACCEPTED on 2026-09-30 by a fresh-session review** (a new conversation, about
12:25–12:55 IST). Receipt: [SA-009-review.md](evidence/SA-009-review.md). SA-009 is `done`, and
its `production_verification` is `pending_deployment`. No SA-039 check was due. Nothing was
committed, pushed, deployed, configured or sent, and no production state was read.

- **Input verified:** `72923d91…` (14 files, 0 mismatches, no unlisted change). The diff
  `c931b6c7…` was rebuilt with the reviewer's own script.
- **Traced:**
  - the owner rule against every scheduled writer (the scheduler, the self-heal, the pre-open
    check, the event ingest, the RL monitor) and the add route;
  - the readers: the orchestrator's weight read, the fallbacks, the evaluator walks, the backup
    and the universe walk;
  - the fixture's rosters equal the five real graphs'.
- **Checks:**
  - focused 35 passed;
  - full suite **4016 passed, 12 skipped, 0 failed** (12 min 08 s), `data/` unchanged;
  - reviewer probes: 12 passed, with the real wiring. R1 is SUZLON end to end: the plan moves only
    `automobile/SUZLON`, the scorecard and learning-evidence walks list SUZLON once, and a rollback
    is byte-identical;
  - reviewer mutations: 4 of 8 caught, including each of the three pre-SA-009 writers. The 4
    survivors are L3's untested rules, and each is covered by a probe;
  - `check_kt_docs` errors `[]` after the review edits (409 links, PDF 33 pages).
- **D1–D10 upheld.**
- **Findings.** None is critical, high or medium.
  - **L1 (low), in one example.** A quarantined file changes, so `rollback` refuses that store and
    reports `partial`. The operator restores the bytes and retries. The retry skips the store,
    which stays in quarantine, and reports `rolled_back` with exit 0.
  - **L2 (low).** Any read that constructs the quarantined store's `PredictionStore` recreates an
    empty live directory, and `rollback` then refuses. Removing it and retrying works.
  - **L3 (low, tests).** No test pins the holds for a sectorless or conflicting managed entry, the
    declared-sector conflict, or `apply` ignoring the plan file's items. The code is right; the
    reviewer's probes verified it.
  - **All three go to SA-009 change 1**, which is not required before the production apply. Until
    then the rollback caveat is in KT section 3.
  - **I1 → [SA-015](stories/SA-015.md).** The first restart of each month backfills yesterday for
    all 20 tickers, and the 16:30 job grades it again. The adapter runs twice, which is inert in
    `observe`.
  - **I2 → [SA-017](stories/SA-017.md).** The eval harness groups `per_sector` by the log's label.
  - **I3.** The rosters depend on the sector toggles; all four native sectors are enabled.
  - **I4 → rollout step 3.** Check `owner_store_present` on every item before approving.
- **Review edits (docs only):** status wording in the KT (§1, §3, §11, §12), ARCHITECTURE,
  guide 01-G and 04-G; the rollback caveat in KT §3; the PDF rebuilt. Routed notes were added on
  SA-015 and SA-017.

**SA-009 was IMPLEMENTED on 2026-09-30** (this conversation, about 06:46–11:58 IST, with a
pause). It is uncommitted and not reviewed. A same-conversation self-review was done; it is not
the fresh review. No production check was due, and no production state was read.

- **Sequencing.** SA-009 edits files SA-008 also changed, so the owner chose to commit SA-008
  first (step 3). The SA-009 baseline is the clean tree at `f443cc7`.
- **What it is, in one example.** SUZLON is managed as `renewable_energy`. The startup self-heal
  looked for every managed ticker's envelope in `automobile/<TICKER>`. So on each month's first
  deploy it ran the automobile graph into `automobile/SUZLON`: a second store with the automobile
  dimensions, which SUZLON's reviews never read but every evaluator that walks the tree does. The
  audit's 10 Sep capture found 15 such pairs, and all 58 feedback logs said `automobile` (the
  schema default).
- **What changed:**
  - **The owner rule.** A ticker's history belongs to `<managed sector>/<TICKER>`. A ticker
    without a managed entry has no owner, and nothing guesses one.
  - **The writers.** The self-heal uses each managed entry's sector. The store stamps its own
    sector on new logs, weights and ledgers, and leaves old files as they are. The daily review
    rebuilds a missing weight file, live or paper, from its sector's graph.
  - **The inventory.** `python -m core.intelligence.rl.stores.store_inventory` is read-only. Per
    store it gives identity, sector evidence and ownership. `confirmed` needs a dimension roster
    that matches the directory's graph; a directory name alone never confirms. It also lists
    duplicate tickers, envelope ids and graded days, identical or conflicting.
  - **The quarantine.** `python -m core.intelligence.rl.stores.store_migration plan|apply|rollback`.
    `plan` is read-only and ends with a digest. `apply` needs that digest, re-hashes each store
    just before moving it, and moves it by one rename into `data/prediction_quarantine/<id>/`.
    `rollback` restores the tree byte for byte and never merges.
- **Checks:**
  - 35 new tests (35 passed);
  - full suite on the final bytes: 4016 passed, 12 skipped, 0 failed (10 min 41 s; 3981 + the 35 new);
  - mutations: 15 of 15 caught (unmutated 35 passed before and after; sources restored byte-identical by blob id);
  - `check_kt_docs` errors `[]` (PDF 32 pages);
  - local runs: on a July snapshot the plan moves exactly the 13 `automobile/<TICKER>` copies; the
    dev tree was unchanged by the run.
- **Decisions D1–D10 for the reviewer** are in the receipt. The biggest:
  - D1: the owner is the managed sector;
  - D2 and D3: the dimension roster is the evidence, judged against the directory and against the
    owner separately;
  - D5: quarantine moves a store by rename, not copy and delete;
  - D8: the writer fixes are part of this story; without the self-heal fix the next month's
    first deploy would recreate the copies.
- **Routed:** the readers keyed by the graph sector, the `automobile` defaults and the directory
  creation on read go to [SA-026](stories/SA-026.md). Row lineage goes to
  [SA-017](stories/SA-017.md). A caveat for P3's F1 is in step 0.
- **Rollout, after review, commit and push:** first deploy, then the owner runs the inventory and
  plan read-only on the volume. The apply needs the owner's authorisation, by the plan's digest,
  in a job-free window after the nightly backup. Receipt: "Rollout".

**SA-008 was ACCEPTED on 2026-09-30 by a fresh-session review** (a new conversation, about
06:16–06:50 IST). Receipt: [SA-008-review.md](evidence/SA-008-review.md). SA-008 is `done`,
and its `production_verification` is `pending_deployment`. No SA-039 check was due. Nothing was
committed, pushed, deployed, configured or sent, and no production state was read.

- **Input verified:** `9a2edfb2…` (37 files, 0 mismatches, no unlisted change). The diff
  `bb7d0576…` was rebuilt with the reviewer's own script, and 37 of 37 blob ids match.
- **Traced:**
  - TATAMOTORS from the shipped registry through the analysis gate, the forecast stamp, the
    review's `identity` stage, the close fallbacks, the advisor and the autopilot;
  - the Dockerfile copies `config/` into `/app`, and no volume masks it, so production reads the
    real registry and not the fail-closed path;
  - the automobile `TICKERS` default only feeds the LLM lookup's short cut and the preopen
    check's list, so deploying schedules no TMPV run. The owner's add does that.
- **Checks:**
  - focused 500 passed;
  - full suite **3981 passed, 12 skipped, 0 failed** (5 min 14 s), `data/` unchanged;
  - reviewer mutations 4 of 4 caught;
  - reviewer probes 9: 7 passed, and 2 found M1 and L1;
  - `check_kt_docs` errors `[]` before and after the review edits.
- **D1–D9 upheld.**
- **Findings.** None is critical or high.
  - **M1 (medium) and L1 (low), in one example.** They are in the reconciliation tool's
    `apply`, and both go to **SA-008 change 1**.
    - **M1:** a user holds 100 PARENT, which demerged 60/40 into PARENTA and PARENTB, and the
      operator approves the plan. If 50 are sold in the moment between `apply`'s last check and
      its lock, the result is still 100 PARENTA + 100 PARENTB: shares and cost that were never
      held.
    - **L1:** if one user has two such holdings, the second backup overwrites the first, so no
      file holds the portfolio from before the apply. The audit log still has each old holding.
    - **Neither can happen today.** The shipped registry records no `successors`, so `apply`
      applies nothing. Until change 1 is accepted, record no `successors` and run no `apply` in
      production. KT §6 says so.
  - **L2 (low):** the review's close now asks the learned symbol cache first. Before SA-008 it
    used only the overrides dict. A ticker with a learned entry, such as SUZLON → SUZLON.BO, is
    now graded against the same symbol its forecast was priced from. That is right, but the
    receipt did not list it. The rollout adds a read-only look at the volume's cache.
  - **L3 (low, pre-existing):** the fundamentals fetcher never used the dict or the registry.
    TVSMOTORS' fundamentals ask `TVSMOTORS.NS`, while its prices come from `TVSMOTOR.NS`.
    Routed to [SA-045](stories/SA-045.md).
  - **I1 (info):** "different price bases are never compared" holds for grading and holdings. It
    does not hold for the technicals after a future demerger in which the parent keeps its code.
    Change 1's docs will state it.
- **Review edits (docs only):** status wording in the KT (§1, §4, §11, §12), ARCHITECTURE,
  TEAM_TESTING_GUIDE and CODEBASE; M1 and L1 in KT §6; the PDF rebuilt (30 pages, source
  `97953dc0…`).
- **SA-008 change 1** (M1, L1 and I1's wording) is in STATE as `change_1: todo`. It gets its own
  implementation conversation and its own fresh review. It is not urgent under the shipped
  registry, but it must come before any `successors` record.

**SA-008 was IMPLEMENTED on 2026-09-29** (this conversation, about 16:38–17:50 IST, after P2), and
was amended on 30 Sep, about 00:05–00:30, for the owner's decision below. It is uncommitted and not
reviewed. A same-conversation self-review was done; it is not the fresh
review.

- **What it is, in one example.** TATAMOTORS (weights v85) was priced from TMPV.NS through an
  undated `YF_SYMBOL_OVERRIDES` entry. TMPV is the passenger-vehicle company after the 2025
  demerger, while "Tata Motors Limited" now names the commercial-vehicle company. With healthy
  data its analysis was `actionable`.
  - Now `config/instruments.yaml` records each non-trivial ticker's provider symbol, price basis
    and identity status, with dates. Evidence resolves an identity; nothing is needed to
    quarantine one.
  - TATAMOTORS ships `unresolved`, still fetched from TMPV.NS. In `record` (the shipped mode)
    nothing changes, and its gate rows start "identity unresolved: retired by the owner's decision".
  - In `enforce` it reads INSUFFICIENT DATA, builds no envelope, stops its review at stage
    `identity`, and a holding of it is held (note `IDENTITY`).
- **Also:**
  - forecast rows, envelopes and advice keep the instrument they priced;
  - a row is graded only on its own price basis;
  - a holding whose basis changed since purchase (a demerger) is held, exits included, until an
    operator runs `python -m core.portfolio.identity_reconcile plan`, reviews it, and applies it
    with the plan's digest;
  - the close fallbacks and the NSE check price the resolved instrument.
- **Checks:**
  - 70 new tests;
  - 22 of 22 runtime mutations caught;
  - full suite **3981 passed, 12 skipped, 0 failed** (3911 + the 70 new, final bytes), `data/`
    unchanged;
  - `check_kt_docs` errors `[]` (PDF 30 pages).
- **Decisions D1–D9 for the reviewer** are in the receipt. The biggest:
  - D1: it uses SA-003's switch, not a new one;
  - D3: the identity hold also holds EXIT and TRIM, a deliberate departure from SA-003's
    "never blocked", because a demerged parent's price reads as a false 40% loss.
- **Owner decision (29 Sep, delegated: "take whichever is recommended"): option (b).** The
  passenger-vehicle company is tracked as its own ticker, TMPV; TATAMOTORS is retired and stays
  quarantined, with its history kept. TMCV is not added.
  - **The amendment it needed:** TMPV joins the automobile exact-match list, because the LLM
    lookup's prompt lists TATAMOTORS and could rename TMPV back to it; TMPV is added to the
    sector map; the registry's TATAMOTORS reason records the decision.
  - **The owner's step at rollout,** after review, commit and deploy: add TMPV (automobile,
    name "Tata Motors Passenger Vehicles Ltd"), then **disable** TATAMOTORS with the toggle.
    **Never remove it:** removing deletes `data/predictions/automobile/TATAMOTORS` (its v85
    weights, envelopes and feedback). Receipt "Rollout", step 4.
- **Routed:** P2's ticker-resolution traceback goes to [SA-026](stories/SA-026.md).

Six Sprint-1 stories (SA-033, SA-035, SA-036, SA-038, SA-040, SA-042) come later in the STATE
file; taking one before SA-009 needs the owner's word.

**SA-007 change 1 was ACCEPTED on 2026-09-29 by a fresh-session review** (a new conversation,
about 12:33–12:55 IST). Receipt: [SA-007-review.md](evidence/SA-007-review.md), section "Change
1 fresh-session review". SA-007 is `done` again. No SA-039 check was due. Nothing was committed,
pushed, deployed, configured or sent.

- **What it is, in one example.** The owner deferred the off-site bucket to the last task of the
  PI and chose option B (about 12:00 IST).
  - The watchdog reminds "No off-site copy has ever been confirmed" once a week, not every
    morning: Wednesday 06:30, then silence until the next Wednesday.
  - A failed drill, a stopped job, a flagged ledger or a half-done setup still warns daily.
- **Input verified:** `4cda0408…` (8 files, 0 mismatches, no unlisted change). The diff
  `18525515…` was rebuilt with the reviewer's own script, and 8 of 8 blob ids match.
- **Traced:**
  - the engine's daily path is exactly the expression it replaced;
  - `repeat_days` reaches the engine through `run_check` and the runner;
  - the real job writes `target: None` only when `BACKUP_OFFSITE_TARGET` is unset.
- **Reviewer probes, 7 of 7**, through the real nightly job and the real runner:
  - weekly notices on 30 Sep, 7 Oct and 14 Oct;
  - the rollout claim (the deployed code warns Wed 30 Sep; change 1 then keeps Thu–Tue silent);
  - a half-done setup, a flagged ledger and a rollback stay daily;
  - a failed delivery is retried the next day.
- **Decisions C1–C4 upheld.** C4's cost: after any daily notice, a return to the deferred state
  is silent for up to six days. The Sunday heartbeat still lists the state weekly.
- **Findings, both fixed by docs-only review edits:**
  - **L1 (low):** guide 12-G said a drill failed by hand on a test copy would reach the watchdog.
    `restore drill` never writes `backup_status.json`.
  - **I1 (info):** SA-007's "not yet deployed" wording was stale since `26b442f4`.
- **Checks:** focused 202 passed; reviewer mutations 5 of 5 caught; full suite **3911 passed, 12 skipped, 0 failed** (6 min 06 s), `data/` unchanged;
  broad-except OK; `check_kt_docs` errors `[]` (PDF 28 pages, source `70a321ef…`).
- **Review edits (docs only):** KT §1, §10, §11 and §12; the PDF; guide 12-B, 12-G and 12-H;
  ARCHITECTURE; LEGAL. `verify SA-007-change1-manifest.json` now mismatches exactly the KT, the
  PDF and the guide.
- **Production verification** stays `pending_observation`: tonight's 23:30 backup, then the
  Wed 06:30 watchdog. After change 1 deploys, its own check is a silent watchdog on the morning
  after the first weekly notice.

**SA-007 was ACCEPTED on 2026-09-29 by a fresh-session review** (a new conversation, about
07:05–07:35 IST). Receipt: [SA-007-review.md](evidence/SA-007-review.md). SA-007 is `done`. No
SA-039 check was due. Nothing was committed, pushed, deployed, configured or sent.

- **Input verified:** `7c1d43d9…` (18 files, 0 mismatches, no unlisted change). The diff
  `2e0a5656…` was rebuilt with the reviewer's own script.
- **The original defect, reproduced against the baseline module.** A WAL `chat_sessions.db` with
  5 committed rows still in its `-wal`: the old zip restores to "no such table", and the new one
  holds 5 rows. A writer committing during the build still gives a clean drill.
- **Two low findings, both reproduced and routed. Neither blocks acceptance.**
  - **F1 → [SA-034](stories/SA-034.md), in one example.** Sunday's backup is confirmed. On Monday
    the container restarts at 23:30, so the job never runs and no error fires. At 06:30 on
    Tuesday the status is 31 h old, under the check's 36 h limit, so the watchdog says
    `satisfied`. If Tuesday's run works, the missed night is never reported. Fix: SA-034's
    job-ran invariant, or a limit of about 30 h.
  - **F2 → [SA-036](stories/SA-036.md), in one example.** `atlas.db` is malformed and
    `transactions.jsonl` is healthy. Before SA-007 the zip held both. Now the job raises
    `DatabaseError`, and no archive, off-site copy or status is written until the database is
    repaired. The job-error alert fires each night, and earlier copies are kept. Fix: archive the
    rest and record a `partial` outcome.
  - **I1 (info) → the SA-036 card:** the local rotation ignores the drill. **I2 (info, predates
    SA-007):** SA-004 and SA-006 still read "not yet deployed" in the KT, ARCHITECTURE and the
    guide. For the next KT bump or SA-031.
- **Decisions:** D1–D10 upheld, except D6 in part (F1). D4's cost is now in the KT: a ledger
  rewrite is reported on one morning, then the history survives only in the older off-site
  copies, for 30 nights by default.
- **Checks:**
  - focused 136 passed;
  - reviewer probes: 7 passed, and 2 failed as the findings;
  - reviewer mutations 9 of 9 caught;
  - full suite alone **3902 passed, 12 skipped, 0 failed** (5 min 03 s), `data/` unchanged. An
    earlier run beside the mutations hit a Windows rename flake in `core/ipo/history.py`, which
    passes 5 of 5 alone; it is routed to SA-031 with the `signals.py` one;
  - broad-except OK; `check_kt_docs` errors `[]`.
  - The probes and the mutation plugin are in `analysis_data/sa007/review/` (ignored).
- **Review edits (docs only):** SA-007 status wording in the KT (§1, §10, §11, §12),
  ARCHITECTURE, guide 12-B/G/H and LEGAL. KT §10 now states F1 and F2. The PDF is rebuilt (28
  pages, source `9efaf9da…`). Routed notes are on the SA-034 and SA-036 cards. `verify
  SA-007-manifest.json` now mismatches exactly the KT, the PDF, ARCHITECTURE, the guide and LEGAL.
- **Production verification: `pending_deployment`.** It needs:
  - the owner's commit, push and deploy. A deploy alone makes the watchdog warn every morning
    until a bucket exists;
  - the bucket, key and `BACKUP_*` variables (deferred owner setup);
  - a recorded `restore fetch` from outside Railway.
  The plaintext backup email (D7) is still the owner's decision.
- **Committed at the owner's word** ("ya go ahead commit and push", about 07:37 IST Tue 29 Sep).
  - **`165d152`:** SA-007 and its review bookkeeping. `verify SA-007-manifest.json --rev 165d152`
    mismatches only the 5 review-edited docs, so every reviewed code and test byte is committed as
    reviewed.
  - **The next commit is the KT bump.** It declares `165d152` and links `offsite.py` and
    `restore.py`. The SA-007 status lines now say "committed as `165d152`". It also records
    `implementation_commit` and rebuilds the PDF (28 pages, `check_kt_docs` errors `[]`).
- **Pushed and deployed.** The 07:37 word waited out the morning-job window.
  - **The push:** `acf72d2..cd33fc4` at 12:12:57 IST, carrying `cdec78f`, `165d152` and
    `cd33fc4`.
  - **The deploy:** Railway `26b442f4` reached SUCCESS by 12:19:54 IST.
    - Boot log: 124 lines, 0 tracebacks and 0 error or warning lines; the scheduler started
      with 24 jobs.
    - `/health` returns 200 `ok`.
  - **Packages:** the pip layer reinstalled. Against the 27 Sep full build `0106fc89`, 6
    transitive packages changed:
    - `oauthlib` 3.3.1 → 4.0.0, a major version. It comes through chromadb → kubernetes →
      requests-oauthlib, and no app code imports it. For SA-033's pinning;
    - `coverage`, `filelock`, `peewee`, `platformdirs` and `regex`, minor or patch versions.
    - `cryptography` 50.0.1 and every core package are unchanged.
    - The raw build logs are in the ignored `analysis_data/sa007/deploy/`.
  - **CI:** run `36532524605` passed 3 of 3 jobs. Python tests on Linux / 3.11 took 2 min 50 s,
    so SA-007's tests pass there.
  - **SA-007 `production_verification`: `pending_observation`.**
    - Tonight's 23:30 backup is the first with a manifest and a drill. Its continuity will read
      "not checked" against the old-format archive, and `backup_status.json` will say "not
      configured".
    - At 06:30 on Wed 30 Sep the watchdog should say "No off-site copy has ever been confirmed".
      That is expected. It repeats daily until change 1 lands, then weekly.
    - Off-site recovery stays unverified until the bucket. The owner deferred it to the last task
      of the PI.
  - STATE and HANDOFF record this uncommitted. It rides with change 1's commit.

**SA-007 was implemented on 2026-09-29** (about 03:20–04:10 IST). Receipt:
[SA-007-implementation.md](evidence/SA-007-implementation.md). Review input
**`7c1d43d9…`** (18 files); full diff `2e0a5656…` against `cdec78f`. Nothing was committed,
pushed, deployed, configured or sent. No bucket exists.

- **In one example.** Tonight's archive gets a `MANIFEST.json`, for example `users.db`:
  integrity ok, `users: 2`, `transactions.jsonl`: 1,200 bytes and 3 rows. The job restores it into
  a temporary directory and checks all of it. It also checks that the ledger still begins with
  last night's 1,100 bytes. Only then does it encrypt the archive (AES-256-GCM) and send it
  off-site, ciphertext first and manifest last, each read back at its size. With no bucket
  configured, the watchdog says every morning: "No off-site copy has ever been confirmed".
- **A real defect was fixed.** `users.db`, `atlas.db` and `chat_sessions.db` run in WAL mode and
  were zipped as raw files with their `-wal`/`-shm` files. Rows still in the WAL were lost:
  restored alone, a raw copy of a fresh WAL database has no tables at all. Now every SQLite file
  goes through the backup API.
- **For the reviewer:**
  - D1–D10 are in the receipt. The contested ones are D3 (only a drill-passing archive leaves),
    D4 (continuity breaks are warnings, not errors), D5 (what "confirmed" means) and D7 (the
    email copy is unchanged).
  - The S3 signer is from the standard library, checked against AWS's three published examples.
  - A deploy alone makes the watchdog warn daily until the owner configures a bucket.
- **Checks:**
  - 65 new tests (27 recovery, 28 off-site, 10 watchdog);
  - full suite **3902 passed, 12 skipped, 0 failed** (9 min 32 s), `data/` unchanged;
  - 15 of 15 mutations caught;
  - the broad-except guard OK, and `check_kt_docs` errors `[]` (PDF 28 pages);
  - a local rehearsal on a copy of the dev data: 63 files, 5 databases and 77,540 rows drilled
    clean, then recovered from the off-site copy alone.
- **Docs:** KT §3, §9, §10 ("Backups and recovery": steps, runbook, owner configuration, limits)
  and §11; guide 12-B, new 12-G and 12-H; ARCHITECTURE, PRODUCT_MAP, CODEBASE and LEGAL. New files
  are not linked from the KT until the KT bump after a commit.
- **Production verification: `pending_deployment`.** It needs:
  - acceptance, then the owner's commit, push and deploy;
  - the owner's bucket, key and `BACKUP_*` variables, set in a job-free window (each set
    redeploys). This joins the deferred owner setup list;
  - a recorded `python -m services.data.restore fetch --dest <empty dir>` from outside Railway.

  Also for the owner to decide: retire or encrypt the plaintext backup email.
- **After acceptance:** select the next ready story, but do not start it in the review chat. By
  STATE file order that is **SA-008**. Six Sprint-1 stories (SA-033, SA-035, SA-036, SA-038,
  SA-040, SA-042) come later in the file.

**SA-006 was ACCEPTED by its fresh re-review on 2026-09-28** (this conversation, about
19:40–20:45 IST, after P1). Receipt: [SA-006-review.md](evidence/SA-006-review.md), section
"Re-review". Nothing was committed, pushed, deployed or sent.

- **F1 is fixed, in one example.** A phone's push service stores the morning brief's push, then
  drops the connection. The brief now shows once; the row dead-letters with the reason. A
  refused connection is still retried and shows once.
  - The rule matches urllib3's own "safe to retry" test (`Retry._is_connection_error`).
  - Real-stack tests prove both cases.
- **F2 is fixed:** the owner report carries no user id.
- **D10, D11 and D12 are upheld:**
  - D10: a TLS error is an unknown outcome;
  - D11: one phone's unknown outcome stops the row;
  - D12: no `sw.js` tag for now. It is revisited if guide case 10-C shows a double.
- **Checks:**
  - the input `b8273b2c…` verified, and the diffs `e01c4913…` and `713e1675…` rebuilt;
  - focused tests 124 passed;
  - full suite **3837 passed, 12 skipped, 0 failed** (7 min 12 s), `data/` unchanged;
  - the reviewer's 8 of 8 mutations caught, and 7 of 7 probes as the contract requires;
  - `check_kt_docs` errors `[]`.
  - No findings.
- **Review edits (docs only):** the SA-006 status wording in the KT (§1, §10, §11, §12), ARCHITECTURE
  and guide 10-B/C/E/F; the PDF is rebuilt (26 pages, source `38ddf518…`). So `verify
  SA-006-manifest.json` now mismatches exactly those 4 files.
- **Production verification: `pending_deployment`.**
  - It needs the owner's commit and push.
  - After the deploy, read `GET /delivery/outbox` (machine key) or run the owner probe
    `analysis_data/sa006/prod_probe_outbox.py`.
  - Then human cases 10-B, 10-C, 10-E and 10-F.
  - A real test email or push needs explicit messaging authorization.
- **Committed as `15dcda1`** at the owner's word ("commit and push with revan.datta132@gmail.com",
  about 22:18 IST Mon 28 Sep). The author is `Revan <revan.datta132@gmail.com>`, the same as
  earlier commits.
  - `verify SA-006-manifest.json --rev 15dcda1` mismatches only the 4 review-edited docs, so every
    reviewed code and test byte is committed as reviewed.
  - A follow-up commit bumps the KT to `15dcda1` (§1, §10, §11 and §12 now say "committed"; PDF
    26 pages, `check_kt_docs` errors `[]`) and records the commit in STATE.

**The push hold is lifted** (owner, about 22:18 IST Mon 28 Sep: "commit and push"). The push
carries 5 commits: `7901f35`, `48143ed` (SA-005), `9e65c7a`, `15dcda1` (SA-006) and the KT bump.
It is timed so the deploy lands before the 22:55–00:05 blocked window (23:00 atlas jobs, 23:30
backup). **After the push:**

- check the deploy with `railway deployment list`;
- read the Actions page and record CI's three jobs against SA-005 (human case 12-E);
- do SA-006's first read-only production read (`GET /delivery/outbox` or the owner probe).

**Pushed and deployed.**

- **The push:** `90353f3..acf72d2` at 22:20:54 IST.
- **The deploy:** Railway `00b94de9`, created 22:21:00, SUCCESS by 22:27:46 IST, before the
  22:55 window. The 23:00–23:45 nightly jobs run on the new code; `atlas_retention` at 23:20 is
  the first to keep dead letters for 180 days.
- **After the deploy (read-only):**
  - startup completed, with 0 tracebacks in its first 126 log lines;
  - `/health` returns ok;
  - the RL monitor is still `learning_mode=observe`;
  - `GET /delivery/outbox` without credentials returns 401 (owner-only, as designed).
- **CI's first run passed** (run `36453992259` on `acf72d2`, read via the public GitHub API):
  - Python tests (Linux, 3.11): success, 2 min 30 s;
  - the broad-except and KT guards: success;
  - the Chromium browser suite: success.
  - That is SA-005's human case 12-E, measured. What remains for SA-005 is the witnessed drill
    12-F.
- **SA-005 and SA-006 `production_verification`:** now `pending_observation`.
- **Still to do for SA-006:**
  - the first authenticated outbox read: the owner runs `analysis_data/sa006/prod_probe_outbox.py`
    in the container, or uses a machine-key GET;
  - then one observed retry or dead letter (case 10-C), and cases 10-B, 10-E and 10-F.
- **Local `main` is 1 ahead** after the next commit (this record). It is not pushed, because every
  push redeploys; it goes out with the next push.

**SA-006 rework 1 was done on 2026-09-28** (a new conversation, about 15:38–16:25 IST, baseline
`9e65c7a`). Receipt: [SA-006-implementation.md](evidence/SA-006-implementation.md), section
"Rework 1". No SA-039 check was due. Nothing was committed, pushed, deployed or sent.

- **F1 fixed, in one example.** A push service stores a brief's push, then the connection
  drops before its 201.
  - Before: the drainer retried it, so the phone showed it twice.
  - Now: it is an unknown outcome and dead-letters after one attempt, so the phone shows it once
    and the owner report says why.
  - A push is retried only when its connection was never made: refused, a DNS failure or a
    connect timeout. The check uses exception types, found along `args`, `reason` and
    `__cause__`, never message text.
- **F2 fixed.** The dead letter for an account with no address now reads "permanent: no email on
  file for this account", with no user id.
- **Two new decisions for the re-reviewer:**
  - **D10:** TLS errors count as unknown outcomes, because their type cannot prove that nothing
    was sent.
  - **D11:** one phone's unknown outcome stops the row for all of that account's phones. A phone
    whose service answered 5xx then loses that notification, visibly, as a dead letter.
- **D12, decided by Claude on the owner's delegation:** no notification `tag` in the service
  worker for now.
  - Our own retries can no longer duplicate a push.
  - A tag only merges a copy that is still on screen, so it makes no retry safe.
  - It would change code on every phone, and no automated test covers that code.
  - Revisit if a phone ever shows one notification twice (guide case 10-C).
- **Tests:**
  - 12 new tests. One is the review's R1, kept as a permanent test: the real pywebpush →
    requests → urllib3 stack against a loopback push service. The service stores 1 copy and the
    row dead-letters after 1 attempt; the reviewed code fails this test. Another uses a real
    refused connection, which is retried and ends with 1 copy stored.
  - A 9-case table of exception types, and I5 extended with an account that has no address.
  - Focused: 124 passed. Full suite: **3837 passed, 12 skipped, 0 failed** (11 min 02 s).
    `data/`, `logs/` and `outputs/` were unchanged.
  - 5 of 5 rework mutations were caught, the broad-except guard is OK, and `check_kt_docs`
    errors are `[]` (PDF 26 pages).
- **Docs:** KT §10 (the transient, at-most-once and visibility bullets); the status lines in the
  KT, ARCHITECTURE and the guide, which now say "re-review pending"; and guide case 10-C.

**SA-006's fresh review requested changes on 2026-09-28** (a new conversation, about
15:08–15:35 IST). Receipt: [SA-006-review.md](evidence/SA-006-review.md). The review input
`516d2aec…` was verified (18 files, 0 mismatches) and the diff `79ec6b54…` rebuilt
independently. No SA-039 check was due. The review edited no code or docs, and nothing was
committed, pushed, deployed or sent.

- **F1 (medium; an acceptance criterion is not met), in one example.** A push service receives
  a brief's push, then the connection drops before it answers. The drainer calls that
  transient and sends it again a minute later, so the phone shows the brief twice. This was
  reproduced with the real pywebpush and requests stack against a loopback push service, which
  stored 2 copies. Today only a `ReadTimeout` counts as an unknown outcome.
  - **The fix:** retry a push only when the exception shows the connection was never made
    (`ConnectTimeout`, `NewConnectionError`, `NameResolutionError`). Treat anything else as an
    unknown outcome, which dead-letters.
- **F2 (low).** The dead letter for an account with no address reads "no email on file for
  user 'u_…'". So the owner report shows a user id, although its contract says it shows none.
  The fix is to drop the id.
- **Everything else holds.**
  - 112 focused tests passed.
  - Full suite: 3825 passed, 12 skipped, 0 failed (11 min 26 s), data/logs/outputs unchanged.
  - 10 of 10 reviewer mutations were caught, including the `590bc9f` owner fallback.
  - The broad-except guard is OK, and `check_kt_docs` errors are `[]`.

**SA-006 was implemented on 2026-09-28** (one conversation, about 13:15–15:05 IST, baseline
`9e65c7a`). Receipt: [SA-006-implementation.md](evidence/SA-006-implementation.md). No SA-039
check was due. Nothing was committed, pushed, deployed or sent.

- **What it does, in one example.** A beta account's brief meets a locked `users.db`: before, it
  went to the owner's `DELIVERY_EMAIL_TO`; now it waits a minute and goes to the account's own
  address, once. The owner's brief meets a rejected Gmail password: before, 3 tries and a raw
  error; now one try and a dead letter saying "check SMTP_USER and SMTP_PASSWORD".
- **The contract:** every transport returns a `SendResult`, meaning acceptance, never receipt.
  Transient failures retry on the backoff or the provider's `Retry-After` (capped at 6 h).
  Permanent ones dead-letter at once with a hint. Unknown outcomes (a drop inside the SMTP send,
  a push read timeout, a process killed mid-send) dead-letter and are never re-sent. Resend gets
  a per-row `Idempotency-Key`. Reasons and logs are redacted. `GET /delivery/outbox` (owner)
  shows counts, dead letters and retrying rows, with `delivered` shown as `accepted`. Dead
  letters are kept 180 days (payload cleared at 30). Pushes carry a 12 h TTL (pywebpush's default
  0 lets a push service drop them).
- **Production, read-only:** the live deploy `b3fb00dd` logged 3 outbox enqueues, 0 dead letters
  and 0 send failures from 27 Sep 16:05 to 28 Sep 12:01. The 23 Sep probe had 8 email rows
  accepted and 0 dead since the Pro redeploy. SMTP works; SA-006 does not change transport
  selection. A read-only outbox probe for the owner is `analysis_data/sa006/prod_probe_outbox.py`
  (not yet run in production).
- **Tests:** full suite 3825 passed, 12 skipped, 0 failed (SA-005's 3800 plus 25 new), with
  `data/`, `logs/` and `outputs/` unchanged; 22 new invariant tests at the network boundary
  (fake relay, Resend and push service count what they accepted); 16 of 16 mutations caught,
  including the `590bc9f` owner fallback; broad-except guard OK; `check_kt_docs` errors `[]`;
  PDF rebuilt (26 pages).
- **Found and routed to SA-031:** `scripts/docs/run_kt_checks.py` has not run since SA-005 (it
  does not copy the tracked seed `data/nse/key_registry.json`, exits 4 and then prints a stale
  24 Sep XML); a Windows rename flake in `core/ipo/signals.py`.
- **Nine decisions for the reviewer,** in the receipt (D1 at most once; D3 stored status stays
  `delivered`, reported as `accepted`; D5 dead-letter retention; D6 push TTL; D8 direct senders
  stay direct).
- **Open:** receipt is not observed (no webhooks); direct senders (monthly report, heartbeat,
  backup) have no retry; no dead-letter alert (SA-011); CI never ran.

- **Earlier plan note:** SA-006 was the first planned `todo` story in STATE's order whose
  dependencies are done. SA-005's acceptance also unblocked [SA-012](stories/SA-012.md).

**SA-005 was ACCEPTED on 2026-09-28 by a fresh-session review** (a new conversation, about
07:25–07:55 IST). Receipt: [SA-005-review.md](evidence/SA-005-review.md). SA-005 is `done`. Its
`production_verification` stays `pending_deployment`: CI has never run on GitHub. No SA-039 check
was due. The review committed, pushed and deployed nothing.

- **Input verified:** `ef0e3a31…` (51 files, 0 mismatches). The completeness check found no
  unlisted change, and the diff `7274a199…` was rebuilt with the reviewer's own script. The three
  action pins are the upstream tags' commits (`git ls-remote`).
- **Tests:**
  - owner's checkout (`.env` present): 3800 passed, 12 skipped, 0 failed. `data/`, `logs/` and
    `outputs/` were unchanged (800 files);
  - reviewer's fresh copy (`git archive 7901f35` plus the manifest, run from the long temp path):
    3799 passed, 13 skipped, 0 failed. `git status` was empty afterwards, and `logs/` and
    `outputs/` were never created;
  - reviewer's 6 mutations: all caught. They include the original F22 defect (the old MARUTI
    test fails without local data) and the F5 defect (the old outbox tests fail without
    `DELIVERY_EMAIL_TO`);
  - probes: yfinance's real call path is refused and fails the test (P1); the owner's real `.env`
    does not reach settings (P6);
  - no Python 3.12-only syntax in 730 files (a tokenizer scan, since `ast` feature_version misses
    PEP 701).
- **Findings.** None critical, high or medium.
  - **L1 (low), in one example.** A test that read
    `C:\Users\REVANP~1\…\data\nse\key_registry.json` (the 8.3 spelling of the checkout) got the
    file instead of a refusal. The same holds for `listdir`/`exists`, pyarrow reads, SQLite
    `file:` URIs and a numeric-IP connection on Windows' asyncio loop. The application reaches
    none of these today. The KT and `tests/TEST_DOCUMENTATION.md` now say so; the docstring and
    optional hardening go to [SA-031](stories/SA-031.md).
  - **L2 (low):** fixing one grandfathered broad `except` and adding a new silent one in the same
    function passes the guard. Routed to SA-031, and the KT states it.
  - I1 and I2 are info only.
- **Review edits (documentation only):** KT §13 (two passages) and the SA-005 status wording
  (§1, §10, §12, the §13 heading), the PDF rebuilt (source `f407a930…`), `tests/TEST_DOCUMENTATION.md` rule 4, and the SA-031 card. `verify
  SA-005-manifest.json` now mismatches exactly these four files. The code, test, CI and tooling
  bytes are as reviewed.
- **Committed at the owner's word** ("commit and push now", about 07:58 IST Mon 28 Sep).
  - **`48143ed`:** SA-005 and its review bookkeeping. `verify SA-005-manifest.json --rev 48143ed`
    mismatches only the four review-edited docs, so every reviewed code, test and CI byte is
    committed as reviewed.
  - **The next commit is the KT bump:** it declares `48143ed`, links the five new or changed
    files, changes the status lines to "committed as `48143ed`", records `implementation_commit`
    and rebuilds the PDF (source `abec1a58…`; `check_kt_docs` errors `[]`).
  - **The push was held for the window.** The word came at 07:58, inside the 07:25–09:05
    morning-job window (`ipo_refresh_am` 08:00, `preopen_shock_check` 08:45, `morning_brief`
    08:50, `macro_market_news` 09:00). A push then would have restarted the container about
    08:06, during the IPO refresh. (Superseded: the owner put the push on hold at 08:46 IST; see step 1.) It
    carries `7901f35`, `48143ed` and the KT bump, and it is CI's first run: afterwards, read
    the Actions page and record the three jobs against SA-005 (human case 12-E).

**Earlier: the SA-005 implementation (27–28 Sep).**

- **SA-005 was implemented** in one conversation (27 Sep about 16:25–17:30 IST and 28 Sep about
  06:45–07:45 IST, baseline `7901f35`). Receipt:
  [SA-005-implementation.md](evidence/SA-005-implementation.md). No SA-039 check was due. Nothing
  was committed, pushed or deployed.
  - **What it does, in one example.** Before, the owner's test run loaded `.env`, and yfinance's
    requests went out unseen by the old socket guard. The first run under the new boundary refused
    286 Yahoo requests, 178 OpenRouter attempts and 124 NSE session attempts. The old suite also
    changed 15 files in the local `data/`, including the MARUTI toggle (I3). Now every test runs in
    an empty working directory, with no `.env` and no network, and the final run left `data/`
    byte-identical.
  - **The boundary:** `tests/hermetic.py`, imported first by `tests/conftest.py`. A test that
    reaches the network or the checkout's `data/`, `logs/` or `outputs/` fails, naming the target
    and the application line, even when the application swallowed the error.
  - **CI:** `.github/workflows/ci.yml` (the whole tree on Linux / Python 3.11, the broad-except
    ratchet and `check_kt_docs`, the browser suite; `contents: read`, no secrets),
    `requirements-test.txt`, `scripts/ci/check_broad_except.py` (154 handlers grandfathered, not
    reviewed one by one).
  - **Nine decisions for the reviewer,** in the receipt. For example: D1 one working-directory
    sandbox instead of ~40 path redirects; D3 an obsolete TypeScript-client contract test removed;
    D4 a Windows-only rename retry in three production writers; D6 the guard is a whole-tree
    ratchet.
  - **Tests:** owner's checkout 3800 passed, 12 skipped, 0 failed; a fresh git checkout outside
    OneDrive 3799 passed, 13 skipped, 0 failed; the reverse-order run found one leak, now fixed;
    12 of 12 mutations caught; `check_kt_docs` 0 errors; PDF rebuilt.
  - **Open:** CI has never run (it needs a push, and every push redeploys); no pinned-date run
    (routed to SA-012); child processes are outside the boundary; cached store connections are
    shared between tests.
  - **Routed:** [SA-012](stories/SA-012.md), [SA-018](stories/SA-018.md),
    [SA-029](stories/SA-029.md), [SA-031](stories/SA-031.md).
  - **Local data restored.** The old suite's measurement run changed 15 files in `data/`; they
    were restored from the ignored `analysis_data/sa005/data_before` copy and are identical to it.
  - **Running tests here:** plain `python -m pytest tests`. `-p nonet` and
    `RL_LEARNING_MODE=adapt` are no longer needed in this checkout; a checkout without SA-005
    still needs them.

**Earlier: SA-004 accepted, committed and deployed (27 Sep).**

- **SA-004 was ACCEPTED on 2026-09-27 by a fresh-session review** (a new conversation, about
  15:23–15:50 IST). Receipt: [SA-004-review.md](evidence/SA-004-review.md). SA-004 is `done`. Its
  `production_verification` is `pending_observation`: it was deployed at 16:06 (see below). No SA-039 check was due. The review itself
  committed, pushed and deployed nothing; the commit and push followed at the owner's word (below).
  - **Input verified:** `a5e77a74…` (13 files, 0 mismatches), and the diff `648b7b68…`, rebuilt
    with the reviewer's own script.
    - Payload update 1 (`5d9030e0…`, diff `e16a8e3f…`) arrived during the review, from the
      concurrent planning session (the backlog bullet below).
    - The reviewer rebuilt it too. The code, tests and `CODEBASE.md` are byte-identical, and the
      four doc changes are planning content only. The acceptance covers both inputs.
  - **Traced:**
    - `completed` implies a stored feedback entry, because a failed write raises;
    - the ticker and date pass through unchanged, so `classify` cannot misread a real review;
    - `/scheduler/status` is the only reader of the record;
    - the HTTP task and the paper lane already counted only `completed`;
    - no watchdog check reads review outcomes.
  - **Hard review.** The five counts always add up to `required`. Within the counting, the zero-
    and partial-output alerts fire for every `produced < required`.
  - **F1 (low, reproduced), in one example.** Suppose Friday's record for 1 Oct had a wrong type
    in it, for example `"attempts": [1]`. On Mon 5 Oct, `summarize` raises before the portfolio
    pipeline:
    - the crash pages;
    - that day's advisor → autopilot → digest does not run.

    The only writer writes integers, so this needs a hand edit. Routed to
    [SA-036](stories/SA-036.md): wrap the block and fall back to no merge. I1 and I2 (info) are
    routed there too.
  - **I3 (info, predates SA-004).** `test_api_auth_lockdown.py:82` flips MARUTI's `enabled` flag
    in the checkout's real `data/managed_tickers.json` on every full run. It now holds MARUTI
    enabled, TCS and HDFCBANK disabled. This is local only. Routed to [SA-005](stories/SA-005.md).
  - **The implementer's five decisions:** the review agreed with each.
  - **Tests** (network guard on, `RL_LEARNING_MODE=adapt`):
    - focused: 376 passed;
    - the reviewer's 5 runtime mutations: all caught. The baseline scheduler, which is F09
      itself, fails 30 of 61;
    - pinned Mon 28 Sep and Fri 2 Oct: 71 passed each;
    - the reviewer's probes: 8 passed;
    - full `tests/unit`: 3502 passed, 5 skipped, 1 failed, the known `test_delivery_api` rename
      flake (5 of 5 alone); the guard blocked the pre-existing 194;
    - `check_kt_docs`: 0 errors.
  - **Review edits (documentation only):**
    - status wording in the KT (§1, §5, §9, §11, §12), ARCHITECTURE, 01-A and 01-F, `CODEBASE.md`
      and the SA-034 note;
    - the PDF rebuilt (source `bf3d73d3…`).

    `verify SA-004-manifest.json` now mismatches exactly the KT, the PDF, ARCHITECTURE,
    TEAM_TESTING_GUIDE and `CODEBASE.md`.
  - **Committed at the owner's word** ("commit and push", about 15:55 IST on Sun 27 Sep).
    - **`241c393`:** SA-004 and this review's bookkeeping. It also carries the planning session's
      SA-048…SA-051 cards and PI README, because the docs interleave the two.
    - `verify SA-004-manifest.json --rev 241c393` mismatches only the five status-edited docs, so
      every reviewed code, test and config byte is committed as reviewed.
    - **The next commit is the KT bump.** It declares `241c393`, links `review_outcomes.py`,
      changes the status lines to "committed as `241c393`", records `implementation_commit` in
      STATE and rebuilds the PDF.
  - **Pushed and deployed.** `a61fafe..90353f3` was pushed at 16:00:04 IST, and it also carried
    `0a5bf9e`. On a Sunday nothing runs between 09:05 and the daily `ipo_refresh_pm` at 17:45.
    - Deploy `b3fb00dd` reached SUCCESS at about 16:06 IST. The build was cached, about 6 minutes
      from the push.
    - The boot log (read-only, filtered) shows the scheduler started with 24 jobs registered and
      startup complete at 16:05:52, with 0 error or warning lines. No job fell in the switch.
    - SA-004's `production_verification` is now `pending_observation`.
    - This record is committed locally and rides the next push.
  - **Verify read-only across one scheduled session,** as the receipt's "Rollout" says. The first
    is Mon 28 Sep 16:30, alongside SA-039-P1 and the SA-003 cohort check. In
    `/scheduler/status` → `last_runs.daily_review`:
    - `by_ticker` holds every enabled ticker once;
    - the five counts add up to `required`;
    - `produced` equals the tickers whose `feedback_log.last_date` is 2026-09-25.

    Expect most outcomes to read `degraded` until the 1 Oct envelopes, because the rows were issued
    before the data gate. A skip (for example `no_envelope`) now sends a partial-output alert,
    which is intended. SA-004 is live before Fri 2 Oct, so Mon 5 Oct's record should read
    `runs: 2` for 1 Oct.
- **Backlog added at the owner's request (2026-09-27, after SA-004).** The owner reviewed the live
  portfolio screen: ₹9,99,611 equity, 81% cash, 2 holdings, a flat total return with nothing to
  compare it with. Four stories were added; the task order is unchanged, and they follow SA-047:
  - [SA-048](stories/SA-048.md) (S3, 3 points): costs and tax in paper P&L. ACMESOLAR's
    +₹37,551 would be about ₹29,660 in hand.
  - [SA-049](stories/SA-049.md) (S3, 5 points): put idle cash to work in normal markets. **Owner
    decision:** deploy idle cash in a normal market, and hold it only in a crisis ("if it's some
    war"). The regime targets and the per-day limit are proposals the owner confirms; the switch
    ships off. It depends on SA-050 and SA-051.
  - [SA-050](stories/SA-050.md) (S2, 2 points): one sizing rule for every autopilot buy. Today a
    SWITCH buy spends all its proceeds, with no 10% cap.
  - [SA-051](stories/SA-051.md) (S2, 3 points): the portfolio against the Nifty, with honest
    labels ("Invested" is really capital added) and a closed-trade record.

  Totals: 48 planned stories, 171 points (Sprints 1–6: 41 / 35 / 31 / 29 / 24 / 11). If the owner
  wants these sooner, SA-050 and SA-051 have no dependencies and could come next instead of
  SA-005; that resequencing needs the owner's word.
- **SA-004 was implemented on 2026-09-27** (a conversation, about 11:45–12:35 IST, on baseline
  `0a5bf9e`). Receipt: [SA-004-implementation.md](evidence/SA-004-implementation.md). No SA-039
  check was due. Nothing was committed, pushed or deployed.
  - **What it does, in one example.** The 8 Sep production record said `produced=20`,
    `expected=20`, `pipeline_ok=true`, while WELCORP had no envelope and 19 feedback rows existed.
    The same day now reads 19 of 20, `status: partial` and
    `missing: {WELCORP: "skipped: no_envelope"}`. The partial-output alert says
    "completed 19/20 — missing: skipped no_envelope: WELCORP".
  - **Outcomes.** The new `core/intelligence/rl/workflows/review_outcomes.py` gives each enabled
    ticker exactly one outcome:
    - `completed`;
    - `degraded`: completed on an input SA-003's record mode flags;
    - `data_gated`;
    - `skipped`: no envelope, no forecast row, or no close;
    - `failed`: an exception, a malformed result, or a timeout.

    Only completed and degraded (feedback written) are output.
  - **Also:**
    - required and attempted are counted separately;
    - disabled tickers are `excluded`, and a duplicate entry is reviewed once;
    - a second scheduled run of the same session merges: attempts add up, completion does not;
    - job `status` is `ok`, `partial`, `failed` or `empty`;
    - `pipeline_ok` is false for a malformed or raising pipeline, and when a review failed.
  - **Decisions flagged for the reviewer:** 5, in the receipt. For example, `degraded` counts as
    output, and the alerts use the merged cohort, not only this run.
  - **Tests** (network guard on, `RL_LEARNING_MODE=adapt`):
    - new files: 61 passed, including an integration test through the real `run_daily_review`
      that checks the persisted record against the stored feedback rows;
    - focused (36 existing files plus the 2 new): 376 passed;
    - 13 runtime mutations, 13 caught;
    - 7-day sweep: 91 passed each day, after one known `test_ops_alerts` flake on the Tuesday pin;
    - full `tests/unit`: 3503 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
    - `check_kt_docs`: 0 errors, and the PDF is rebuilt.
  - **Docs:** KT §1, §5, §9 (a new "Daily-review outcomes" paragraph), §11 and §12; the PDF;
    ARCHITECTURE; human cases 01-A and 01-B, plus a new 01-F (a rerun of the same session);
    `CODEBASE.md`.
  - **Routed:**
    - [SA-005](stories/SA-005.md): the new job-outcome test isolation, and leaks still open;
    - [SA-015](stories/SA-015.md): see the heads-up below;
    - [SA-034](stories/SA-034.md): no watchdog check reads this record yet;
    - [SA-036](stories/SA-036.md): one outcome contract; the pipeline's own `completed` hides
      per-holding advisor failures.
  - **Heads-up, pre-existing (F10, routed to SA-015).** The Mon–Fri 16:30 cron does not skip a
    weekday holiday, so each weekday holiday reviews a session twice.
    - Fri 2 Oct (NSE holiday) reviews Thu 1 Oct, and Mon 5 Oct reviews Thu 1 Oct again.
    - Each ticker runs a full `run_daily_review` for 1 Oct twice.
    - SA-004 would count that once; it does not stop the second run's learning writes.
  - **At commit:** the KT names `review_outcomes.py` in code formatting. The commit that lands
    SA-004 should link it and bump the KT header past `167f08b`.
- Before SA-005: run every test with the network guard `-p nonet` and `RL_LEARNING_MODE=adapt`
  (see step 4). With SA-005 in the checkout, plain `python -m pytest tests` is enough.
- **SA-003 is committed, pushed and deployed** at the owner's word ("commit and push", about
  09:00 IST on Sun 27 Sep).
  - **Commits.** SA-003 is `167f08b`; the KT bump is `a61fafe`, which declares `167f08b`, links
    `decision_gate.py` and rebuilds the PDF. `check_kt_docs` reports no errors.
    `verify SA-003-manifest.json --rev 167f08b` mismatches only the five status-edited docs. So
    every reviewed code, test and config byte is committed as reviewed.
  - **Push.** `f1c7eba..a61fafe` was pushed at 09:05:01 IST; it also carried `da90ee5`. On a
    Sunday, the time after 09:05 IST is job-free until `weekly_review` at 18:00.
  - **Deploy.** `0106fc89` reached SUCCESS at 09:27:57 IST. The boot log (read-only) shows startup
    complete, the scheduler started with 24 jobs registered, and 0 error or warning lines. No job
    fell in the switch.
  - **The build was a full rebuild, about 22 minutes.**
    - Docker Hub had moved the floating `python:3.11-slim` tag (base digest `da047cb8…` became
      `e41613d4…`). That invalidated every cached layer, so pip re-resolved the unpinned
      requirements.
    - Against the 23 Sep install, 15 packages changed (all minor or patch, for example uvicorn
      0.53→0.54 and opentelemetry 1.44→1.45), and 1 transitive package was added.
    - pandas, yfinance, nse (3.2.1), APScheduler (3.11.3), openai and torch are unchanged.
    - Routed to [SA-033](stories/SA-033.md): pin the base-image digest as well as the packages.
  - It ships `record` (`DECISION_GATE_MODE` is not set), so the deploy changes no outcome and is
    not a policy-flag change. It is live before the 1 Oct 09:00 forecast, so the October envelopes
    will carry `data_gate`.
  - **This record is committed locally** and rides the next push.
  - **Verify read-only across one scheduled cohort,** as the receipt's "Rollout" says. The first
    cohort is Mon 28 Sep, at the 16:30 review; check it alongside SA-039-P1.
    - `data/logs/decision_gate.jsonl` gains rows. Until 1 Oct, every review names
      `stage: forecast_row`, "issued before the data gate existed".
    - Reports carry `decision_gate`.
    - The weight and feedback behaviour is unchanged; SA-039-P1 checks this anyway.

**2. SA-003 was ACCEPTED on 2026-09-27 by a fresh-session review** (a new conversation, about
08:30–09:15 IST). Receipt: [SA-003-review.md](evidence/SA-003-review.md). SA-003 is `done`, and its
`production_verification` is now `pending_observation`, after the deploy in step 1. No SA-039
check was due. The review itself committed, pushed and deployed nothing; the commit and push
followed at the owner's word (step 1).

- **Input verified:**
  - the review input `dbe16714…`: 38 files, 0 mismatches;
  - the diff `a46a6846…`, rebuilt with the reviewer's own script;
  - the PDF blob.
- **Traced:**
  - all 8 non-test `analyse` callers;
  - the one `decide` caller;
  - both autopilot buy paths;
  - every weight and lesson writer;
  - the re-forecast paths.

  Each acts only through the gate, or is display-only and routed.
- **F1 (medium), in one example.** With `enforce` on, TATAMOTORS' 09:00 analysis on 1 Nov
  abstains.
  - No November envelope is built.
  - Nothing scheduled retries it before 1 Dec; only a restart's self-heal does.
  - Until then its reviews return `no_envelope`, and its ADDs stay blocked.

  The KT said "the next scheduled run retries", and the review corrected it. The retry and the log
  text are routed to [SA-036](stories/SA-036.md).
- **F2 (medium, predates SA-003), in one example.** Friday's review: yfinance has Friday's close,
  110. NSE has not listed Friday yet, and its newest row is Thursday's, 100.
  - The verifier returns 100, from Thursday.
  - Before SA-003, Friday was graded against Thursday's close.
  - SA-003 dates it Thursday, so it is not fresh: `record` logs it, and `enforce` skips the day.

  Routed to [SA-012](stories/SA-012.md).
- **The implementer's seven decisions:** the review agreed with each. EXIT and TRIM are never
  blocked (verified).
- **Tests** (network guard on):
  - full `tests/unit`: 3442 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
  - the 4 new files: 119 passed;
  - the reviewer's 5 runtime mutations: all caught (34, 5, 11, 13 and 32 failing);
  - the 7-day sweep: 119 passed each day;
  - the NSE-lag probe: 3 passed;
  - `check_kt_docs`: 0 errors.
- **Review edits (documentation only):**
  - status wording in the KT, ARCHITECTURE, 02-C, 03-C and `CODEBASE.md`;
  - the KT's F1 sentence corrected, and the F2 case named;
  - the PDF rebuilt (source `3735be42…`).

  `verify SA-003-manifest.json` now mismatches exactly those five files. No code, test or config
  changed.

**3. SA-003 was implemented on 2026-09-27** (a new conversation, about 03:40–05:15 IST, on baseline
`da90ee5`). Receipt: [SA-003-implementation.md](evidence/SA-003-implementation.md). No SA-039 check
was due. Nothing was committed, pushed or deployed.

- **What it does, in one example.** TATAMOTORS' price source answers 404, and the aggregator still
  says STRONG BUY on 9 of 9 dimensions.
  - The report now carries a typed `decision_gate`, `abstain`, naming the three unusable essential
    sections and the run id.
  - In `record` (the checked-in mode) nothing else changes, and a row in
    `data/logs/decision_gate.jsonl` says what enforcement would have withheld.
  - In `enforce` the report reads INSUFFICIENT DATA. No envelope is built on it, and the small
    holding's ADD becomes HOLD with no buy.
  - With a live price source, the same chain still buys.
- **Where it acts** (in `enforce`):
  - public analysis;
  - the month-start forecast and re-forecast;
  - the daily review: the graded row, a close from the session's own bar, and the re-run;
  - discovery's shelf;
  - the advisor's ADD and SWITCH destinations;
  - the autopilot's SWITCH buy leg.

  EXIT and TRIM are never blocked.
- **Tests** (network guard on, `RL_LEARNING_MODE=adapt`):
  - new files: 119 passed;
  - focused (32 affected existing files plus the new 4): 570 passed, 2 pre-existing failures that
    need the local Atlas DB (identical on baseline);
  - full `tests/unit`: 3442 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
  - 12 runtime mutations, 12 caught;
  - 7-day sweep (27 Sep – 3 Oct, across the month rollover and the 2 Oct holiday): 119 passed
    each day;
  - `check_kt_docs`: 0 errors.
- **Docs:** KT §1, §3, §4, §5, §6, §11 and §12; the PDF is rebuilt; ARCHITECTURE; human cases
  02-C, 02-F and 03-C; `CODEBASE.md`.
- **Routed:** [SA-004](stories/SA-004.md) (count `data_gated` separately),
  [SA-005](stories/SA-005.md) (the loader reload, the Atlas-dependent pipeline tests, the locking
  flake), [SA-008](stories/SA-008.md) (what the gate gives; TATAMOTORS maps to TMPV, and the gate
  cannot see that), and [SA-024](stories/SA-024.md) (the screens show a score next to INSUFFICIENT
  DATA).
- **At commit:** the KT names `src/backend/shared/pipeline/decision_gate.py` in code formatting.
  The commit that lands SA-003 should link it and bump the KT header past `8413b59`;
  `check_kt_docs.py` fails on a link to a file absent at the header's revision.

**4. SA-001 and SA-002 were committed, pushed and deployed on 2026-09-27.** They are committed as
`8413b59` (about 03:40 IST, at the owner's "commit and push", inside the 00:10–06:20 safe window).

- **Network guard.** Use `-p nonet` for every test run. Without it, a missed patch reaches real
  providers (see the incident in step 8). Check any date-relative fixture on 7 consecutive days;
  see the SA-005 note.
- **Commit and deploy:**
  - Commit checks passed. `verify SA-001-manifest.json --rev 8413b59` (17 files) and
    `verify SA-002-manifest.json --rev 8413b59` (19 files) each mismatch only in the five
    status-edited docs: the KT, the PDF, ARCHITECTURE, TEAM_TESTING_GUIDE and `CODEBASE.md`.
  - `npm run test:frontend`: 14 of 14 passed before the push.
  - The next commit bumps the KT header to `8413b59` (edition 2026-09-27), links
    `chat-markdown.js` and `fetch_result.py`, and changes the status lines to "committed".
  - **Pushed and deployed.** `16e7ea7..f1c7eba` was pushed at 03:41:25 IST; it also carried
    `994a7b6` and `103f2b8`. Deploy `0509de45` reached SUCCESS at about 03:42:48 IST.
    - The boot log (read-only) shows startup complete at 03:42:34 and the scheduler started with
      24 jobs registered. It has no error or warning lines.
    - No job fell in the switch; the next is the 06:30 watchdog.
    - Both stories' `production_verification` is now `pending_observation`.
    - This record is committed locally and rides the next push.
  - **Owner's post-deploy checks:**
    - SA-001: open the app twice, so that sw v8 takes over. Run human case 11-C in an isolated
      test account. Confirm that `marked@12.0.2` and `dompurify@3.4.16` load with status 200 and no
      SRI error.
    - SA-002: read-only, across one scheduled cohort, as in the Rollout section of its receipt.

**5. SA-002 was ACCEPTED on 2026-09-26 by a fresh-session re-review** (a new conversation, about
21:57–22:25 IST). Receipt: [SA-002-review.md](evidence/SA-002-review.md), under "Re-review". SA-002
is `done`, and `production_verification` is `pending_deployment`. No SA-039 check was due.

- **Input verified:**
  - the review input `c88edda5…`: 19 files, 0 mismatches;
  - the full diff `dc7e850b…` and the rework diff `56544c46…` both reproduced;
  - the first review's blobs exist in the object database.
- **M1 resolved, in one example.** Run as if on Monday 28 Sep, the whole contract file now passes.
  The reviewer reran the 7-day sweep: 7 of 7 days pass 155 of 155. With the old fixture put back,
  it fails on every day, through the guard.
- **M2 resolved, in one example.** The reviewer's own fixture uses yfinance's real shape: every row
  is NaN in the newest quarter (30 Jun), and the oldest column is sparse. The first review's code
  says `ok`, as of 30 Jun. The reworked code says `fallback`, as of 31 Mar, and names 30 Jun.
  - The same holds for three more shapes: the EBIT fallback row, a `pd.NA` nullable frame, and no
    quarter reported.
  - The prompt text is byte-identical to HEAD in 8 of 8 cases.
- **Decided:** an older blank quarter keeps `ok`, as the first review specified. The growth figure
  then shows `nan`, and SA-045's note covers it.
- **New findings (both low, both predate SA-002):**
  - **N1 → [SA-045](stories/SA-045.md).** The prompt's "Revenue YoY" compares the newest quarter
    with the one three quarters back. Revenue growing 10% a quarter shows +33.1%, where the true
    year-over-year change is +46.4%.
  - **T3 → [SA-005](stories/SA-005.md).** The full run failed 2 tests on Windows rename flakes.
    `test_delivery_api` fails 2 of 5 runs even alone, and `test_ops_alerts` loses its streak when a
    save fails.
- **Tests:**
  - focused: 289 passed, with 0 connections blocked;
  - full: 3321 passed, 2 failed (the flakes above), 5 skipped; the guard blocked the pre-existing
    194;
  - `check_kt_docs`: 0 errors.
- **Docs:** status wording in the KT (§1, §4, §11, §12), ARCHITECTURE, 02-F and `CODEBASE.md`. The
  PDF is rebuilt (source `333895c4…`). `verify SA-002-manifest.json` now mismatches exactly those
  five files.
- **Rollout (owner, after commit and push):** follow the "Rollout" section of the
  [implementation receipt](evidence/SA-002-implementation.md). It is additive: 7 nullable columns,
  and expect more `degraded` rows. Verify read-only across one scheduled cohort. Rollback is
  `observability.data_health_enabled: false`.
- Nothing was committed, pushed or deployed.

**6. The SA-002 rework was done on 2026-09-26** (a new conversation, about 20:50–21:30 IST).
The rework section is in the [implementation receipt](evidence/SA-002-implementation.md). No
SA-039 check was due.

- **M1, in one example.** Before, running on Monday 28 Sep made the fake "fresh" series end on
  Sunday. pandas 3 then built 299 dates for 300 values, so technicals read `empty` and 5 tests
  failed.
  - Now `_bars` rolls weekend dates back to the last session.
  - 14 guard tests pin a fixed Mon–Sun week and do not depend on the run day.
  - The whole contract file passes as if run on each of 7 days (Sun 27 Sep – Sat 3 Oct).
  - With the old fixture body put back, the original tests fail only on Sun, Mon and Tue, but the
    guard fails on every day.
- **M2, in one example.** Before, yfinance listing the quarter ended 27 Aug with NaN figures made
  fundamentals read `ok`, as of 27 Aug.
  - Now they read `fallback`, as of 28 May (the newest fully reported quarter), and the reason
    names the blank quarter. The row is `degraded`.
  - NaN, `None` and infinity all count as missing. The new key is `get_financials`
    `missing_values`.
  - The prompt text is byte-identical to HEAD in 13 of 13 cases.
  - Three runtime mutations are each caught: 9, 9 and 2 failing tests.
- **I1** had already been corrected in the receipt and in step 8 below before the rework began.
  The rework checked that no doc repeats the claim.
- **Tests:**
  - contract file: 155 passed (132 before + 23 new);
  - focused: 289 passed, with 0 connections blocked;
  - full: 3323 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
  - `check_kt_docs`: 0 errors; the PDF was rebuilt (source `0979ad97…`).
- **Docs:** status wording in the KT (§1, §4, §11, §12), ARCHITECTURE, TEAM_TESTING_GUIDE 02-F and
  `CODEBASE.md`. The KT §4 `fallback` meaning now includes a blank newest quarter, and 02-F gains
  that expectation. Routed: a note on [SA-045](stories/SA-045.md) (the Growth factor must read
  `missing_values`).
- Nothing was committed, pushed or deployed.

**7. The SA-002 fresh review requested changes on 2026-09-26** (a new conversation, about
13:20–14:00 IST). Receipt: [SA-002-review.md](evidence/SA-002-review.md).

- **Input verified:** `4d8968fd…`, 19 files, 0 mismatches; the diff digest `f605966c…` reproduced.
- **The production code has no critical or high defect:**
  - every essential producer decides its status from structured data;
  - the analyst's only input is the bundle, and nothing branches on the row;
  - the migration is additive, and there is no new secret sink.
- **The reviewer's own fixtures:**
  - A frozen symbol reads `stale` on all three essential sections (`degraded`). Correct.
  - Serper over quota reads `degraded`, with no essential section flagged. Correct.
  - With B2's rule put back at runtime, 100 of 104 health tests fail. Correct.
- **Why changes were requested, in one example.** Run the suite on Monday 28 Sep. The fake
  "healthy" price series then ends on Sunday 27 Sep. The test helper cannot build a price frame
  ending on a weekend, so the healthy technicals read `empty`, and 5 tests fail. They passed on
  2026-09-26 only because that was a Saturday.
  - **Second finding:** yfinance lists a quarter ended 30 days ago with no figures in it. The row
    says fundamentals `ok`, as of that quarter, while the prompt shows `₹nanCr`.
- **Tests:**
  - focused: 266 passed, with 0 connections blocked;
  - full: 3299 passed, 1 failed, 5 skipped. The failure is a Windows rename flake in
    `test_delivery_api`, which passes 16 of 16 alone; routed to SA-005. The guard blocked 194
    connections, the pre-existing set;
  - `check_kt_docs`: 0 errors.
- **Routed:** L1 (the Gross Profit EBITDA proxy) to SA-045; the flake and date-dependent fixtures
  to SA-005.
- **Doc edits:** status wording in the KT, ARCHITECTURE, TEAM_TESTING_GUIDE 02-F and CODEBASE.md,
  and the PDF is rebuilt. Nothing was committed, pushed or deployed.

**8. SA-002 was implemented on 2026-09-26** (a conversation from about 10:24 to 11:20 IST). Its
fresh review requested changes (step 7); the rework is step 6, and the re-review accepted it (step 5).

- **What it does, in one example:** TATAMOTORS' price source answers 404, while news, macro and
  flows answer, and the analyst scores 9/9.
  - Before, the data-health row said `ok`, with 10 live sections: every "Technical data
    unavailable for …" sentence counted as data.
  - Now each section producer returns a typed `FetchResult` (status, source, as-of, reason), so
    technicals and fundamentals read `empty`, peers valuation `fallback`, and the row `degraded`,
    with `essential_unusable` naming all three.
  - The analyst's prompt text is byte-identical: 24 producer cases and 5 whole-bundle scenarios
    were compared against the HEAD code.
  - Nothing branches on the row yet; SA-003 gates.
- **Evidence:**
  - 132 new tests;
  - the full unit suite: 3300 passed, 5 skipped, under a network guard;
  - 12 of 12 reintroduced defects caught;
  - `check_kt_docs`: 0 errors; the PDF was rebuilt.
- **Incident (recorded in the receipt).** One intermediate run of the existing sector tests, before
  their patches were retargeted, reached real providers with the local `.env` keys. It made +2
  Serper and +10 Tavily successful calls, plus public yfinance calls. The 8 Tavily cache pairs it
  wrote were deleted. Nothing in production was touched.
- **Found, pre-existing (routed to SA-005 as T2).** With the guard on, the *existing* suite tried
  194 outbound connections: `openrouter.ai` 120 (four RL review test files), NSE 68 and Serper 6.
  The pre-SA-002 code shows the same pattern. **In a normal unguarded run with `.env` keys, these
  are real calls, and the OpenRouter ones likely spend LLM credit on every suite run.** Consider
  running the suite with the guard until SA-005 lands.
- **Other routed notes:** SA-003 (gate on the record, not `has_real_data`), SA-044 (F1: the
  automobile peer P/E fallback query), SA-045 (F3: substitute zeros and defaults as factor inputs).
- **Rollout (owner, after acceptance).** Deploy is additive: 7 nullable DB columns are added on
  boot, and old rows are untouched. Expect more `degraded` rows, which is the point. Tavily cache
  entries from September read `unverified` until 1 Oct.
- **Serper credit, answered (owner, 2026-09-26):** the serper.dev dashboard shows **37,747 credits
  left**. The app's "2,590 of 2,500" was never a limit: `SERPER_MONTHLY_LIMIT` only feeds the usage
  log, and no code enforces it. Recorded on [SA-035](stories/SA-035.md). This closes the open
  "check serper.dev for real remaining credits" item from 23 Sep. IPO-0c's decision (GMP stays
  dark) stands on its own reasons.

  Rollback: `observability.data_health_enabled: false`. Production verification is read-only,
  across one scheduled cohort; see the receipt.
- **Commit interaction.** SA-001 and SA-002 are both uncommitted in one worktree and share six
  files. If they are committed together, SA-001's commit check will also show `CODEBASE.md`, which
  is SA-002's hunk. The receipt explains. Commit and push only at the owner's word, in a safe
  window.

**9. SA-001 was ACCEPTED on 2026-09-26 by a fresh-session review** (a new conversation, about
07:35–07:55 IST). Receipt: [SA-001-review.md](evidence/SA-001-review.md). SA-001 is `done`;
`production_verification` is `pending_deployment`. No SA-039 check was due during the review.

- **What the review checked:**
  - The input was verified first: `2ded4b43…`, 17 files, 0 mismatches, on baseline `103f2b8`.
  - The reviewer re-traced model and tool text to every client sink. There is one HTML sink, the
    bubble; the only URL sink, `sw.js` `openWindow`, takes server constants.
  - The previously executable fixture was re-run on the pre-fix files: 0 of 14 pass, and
    `img-onerror`/`img-split` execute. The reviewed files pass 14 of 14.
  - 20 of the reviewer's own payloads went through at every prefix: 0 executions, and the output is
    stable on re-parse.
  - The live CDN bytes equal all five SRI hashes.
  - Focused pytest: 12 passed. `check_kt_docs`: 0 errors, after the review's status-wording edits
    and the PDF rebuild.
- **Findings:** none critical, high or medium.
  - **L1 (low):** the browser suite skips on machines without Node, and the repo has no CI. Routed
    to [SA-005](stories/SA-005.md). Until then, run `npm run test:frontend` before any push that
    touches `src/frontend/prototypes/`.
  - **I1 (info):** the harness flags an inert partial `href="https://"`. Noted on
    [SA-028](stories/SA-028.md).
- **Uncommitted in the worktree:**
  - the SA-001 implementation (the 17 manifest files, plus its receipt and manifest);
  - the review bookkeeping: the review receipt, STATE, this file, and the notes on SA-005, SA-028
    and SA-002;
  - status wording in the KT, the PDF, ARCHITECTURE and TEAM_TESTING_GUIDE.

  Commit at the owner's word. Before committing, run
  `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-001-manifest.json --rev <commit>`.
  Expect mismatches only in `TECHNICAL_DESIGN.md`, the PDF, `ARCHITECTURE.md` and
  `TEAM_TESTING_GUIDE.md`. Bump the KT header revision to the commit, and link `chat-markdown.js`
  there. `994a7b6` and `103f2b8` are also still unpushed.
- **What it does, in one example:** the model quotes `Tata Motors <img src=x onerror="…">`. Before,
  the chat bubble created the image and the handler ran, next to the stored login token. Now the
  bubble shows that text literally, and nothing runs. Bold, lists, code, tables and https links
  still render. Links open in a new tab that cannot reach the app.
- **How:** the new `src/frontend/prototypes/chat-markdown.js` has two layers:
  - marked shows raw HTML as text;
  - DOMPurify 3.4.16 keeps Markdown tags and http(s) links only, with no images, styles or events.

  It fails closed to escaped text. index.html pins marked 12.0.2 (the same bytes as before) and
  DOMPurify with SRI, and takes marked off `window` immediately. That covers a pre-fix `sphere.jsx`
  still cached by the service worker, which goes to v8.
- **Evidence:**
  - 14 real-browser tests through the actual `ChatOverlay`, with no network, stable over 3 runs;
  - 9 static pytest guards (the sink inventory, including URL sinks, and the exact pins);
  - full unit suite: 3166 passed, 5 skipped (with `RL_LEARNING_MODE=adapt`);
  - on the pre-fix files the suite records the fixture executing, and five weakened fixes are each
    caught;
  - `check_kt_docs`: 0 errors, and the PDF is rebuilt.
- **Routed:** CSP and bearer-token storage go to [SA-028](stories/SA-028.md) (a routed note). CSP
  needs the compiled client first.
- **Rollout (owner):** commit at the owner's word, and bump the KT header to that commit, linking
  `chat-markdown.js`. Every push redeploys, so push only in a safe window (step 0 rules; read IST
  with plain `date`). This change affects the served client. After the deploy, open the app twice so
  sw v8 takes over, then run human case 11-C in an isolated test account. The fixture only changes
  the tab title if it ever runs. Also confirm that `marked@12.0.2` and `dompurify@3.4.16` load with
  status 200 and no SRI error. `production_verification` stays `pending_deployment` until then.

**2026-09-26, owner-adopted design (no story started): [one engine with sector lenses](../../superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md).**
This is the single reference for both the learning-exit logic (§1) and the analysis redesign.

- **The per-sector graphs go.**
  - Sector knowledge becomes lens YAML (real peers, benchmark, KPIs), resolved from NSE's
    industry field.
  - Code computes five factors: Value, Quality, Growth, Momentum and Risk.
  - One LLM reader returns dated events, and code turns them into Catalyst.
  - Code decides at equal weights; below 4 of 6 factors it gives no verdict. The LLM explains.
  - Learning uses six pooled factor weights.
- **Board:**
  - New stories: SA-044 (peer fix, Sprint 2), SA-045 (factors, Sprint 4), SA-046 (reader,
    Sprint 4) and SA-047 (decide, shadow and switch on non-inferiority, Sprint 5).
  - SA-026 is now the lens story (Sprint 3). SA-043 learns pooled factor weights (Sprint 4).
  - SA-022 and SA-027 now also depend on SA-047.
  - Totals: 44 planned stories, 158 points (Sprints 1–6: 41 / 30 / 23 / 29 / 24 / 11).
- **Found while inspecting (a live defect, fixed by SA-044):** generic-graph stocks are valued
  against car makers (SUNPHARMA → MARUTI, TATAMOTORS, M&M, HEROMOTOCO, BAJAJ-AUTO).
- KT sections 1, 4, 5, 11 and 12, ARCHITECTURE and the PI README are updated; the PDF is rebuilt
  (`check_kt_docs`: 0 errors, 47 stories).
- **Committed as `5a27683` and pushed on 2026-09-26 at 06:22:29 IST** (the reflog says "update
  by push" from this checkout). The owner asked to commit and push. The push was not run by
  Claude's commands, most likely through VS Code. It carried `0b3ebb9` too.
  - Deploy `82c945da` reached SUCCESS, and the new container registered its jobs at 06:31:09.
  - The old container ran the 06:30 watchdog first (`evaluated=17 notified=0 levels=[]`), so
    nothing was missed.
  - Documentation only; production still runs `adapt`.
- **`observe` is ACTIVE in production since 2026-09-26, about 06:40 IST.** The owner set the
  Railway variable `RL_LEARNING_MODE=observe`. Deploys `786faf7f` and `da9df6cf` (`16e7ea7`)
  reached SUCCESS. A read-only RL-monitor check shows all 20 tickers in `observe`, using the default
  weights. Record: [SA-039-activation-2026-09-26.md](evidence/SA-039-activation-2026-09-26.md).
  STATE: `production_verification: pending_observation`. Rollback is deleting the variable.
  **Checks still due (read-only):**
  - **Mon 28 Sep after 16:30:** the logs show `learning_mode=observe` and `Proposal (not
    applied)`; `/ui/rl/summary` versions match the baseline in ignored
    `analysis_data/sa039_activation_versions_20260926.json`; `/ui/rl/weights` has a
    `latest_observation` dated 2026-09-28.
  - **Tue 29 Sep:** the versions are still unchanged.
  - **Thu 1 Oct after 09:00:** the new envelopes carry `learning_mode: observe`.
- **Local side effect:** the owner's local environment (probably `.env`) now also resolves
  `observe`, so **7 lesson-emphasis unit tests fail locally**. They assume `adapt`, and SA-001 did
  not cause this. Until SA-005 pins the mode in `tests/conftest.py` (routed note added), run tests
  with `RL_LEARNING_MODE=adapt`, or remove that line from the local `.env`.
- The docs for this (the activation record, STATE, this file, KT sections 1/5/12, ARCHITECTURE,
  04-F, the SA-005 note and the PDF) are committed locally and ride the next push.

**2026-09-26, owner-requested planning (no story started): how learning leaves `observe`.**

- **New [SA-043](stories/SA-043.md)** (Sprint 3, 3 points, after SA-015): a shadow learner.
  - A separate weight file starts from the defaults and learns every night on the corrected
    target. Decisions stay on the defaults.
  - For each issued decision it records the default verdict and the shadow verdict, computed from
    the same agent scores.
- **[SA-022](stories/SA-022.md) is amended** with predeclared gates. They are scored only on
  disagreements between the two verdicts:
  - at least 100 effective disagreements, over at least 3 months and 3 sectors;
  - the shadow right on at least 60% of them;
  - wins consistent month to month and robust to dropping the best sector;
  - sane weights, with no agent collapsing to 0.

  A pass must hold at two consecutive monthly looks, and the owner decides. Promotion resumes from
  the shadow's weights, never the stored pre-fix ones. A reverse tally below 45% returns learning
  to `observe`.
- Totals are now 40 planned stories and 143 points (Sprint 3: 21). KT sections 1, 5 and 12 and the
  PI README are updated; the PDF is rebuilt (`check_kt_docs`: 0 errors). This is uncommitted,
  alongside the SA-039 review bookkeeping below.
- Owner-decided backlog changes are recorded in STATE; nothing changed in the task order, and the
  next story is still SA-001.

**SA-039 was ACCEPTED on 2026-09-25** by a fresh-session review at `4c4728a`, with review input
`1efe361f…` (0 mismatches). Receipt: [SA-039-review.md](evidence/SA-039-review.md). SA-039 is `done`.
STATE has `active_task: null`, `next_task: SA-001` and `next_phase: implementation`.
`production_verification` stays `not_started`, because production still runs `adapt`.

- **Next PI phase: implement [SA-001](stories/SA-001.md)** in a new conversation. It has no
  dependencies. Opener: `Continue — implement SA-001`.
- **Review bookkeeping is uncommitted** in the worktree:
  - the review receipt, STATE, this file and the implementation-receipt banner;
  - routed notes on SA-022 (I2) and SA-026 (L2);
  - post-acceptance docs maintenance: KT §1, §5 and §12 status lines, the L1 paper-lane wording
    and the I1 timing sentence in §5, ARCHITECTURE, TEAM_TESTING_GUIDE 04-F, and the rebuilt PDF
    (`check_kt_docs`: 0 errors).

  Commit at the owner's word. `0b3ebb9` is also still unpushed. Every push redeploys, so push only
  in a safe window (Step 0 rules; read IST with plain `date`).
- **Owner decision: activate `observe`.** Either a one-line `rl.learning_mode: observe` commit or
  the Railway variable `RL_LEARNING_MODE=observe` (checked: the env value overrides the yaml).
  **Timing (review I1):** rows already issued keep their verdicts; the review re-weights only their
  confidence. If activation lands before the **1 Oct 09:00 IST** monthly forecast, October is the
  first clean `observe` cohort. The activation commit should also update the "Production is still
  `adapt`" and status lines in the KT, ARCHITECTURE and 04-F, then rebuild the PDF. Afterwards,
  verify read-only against the [baseline](evidence/SA-039-baseline-2026-09-24.md).
- Findings: L1 is fixed (wording). L2, which predates SA-039, is routed to SA-026: the review
  initialises missing weight memory from the automobile table. I2 is routed to SA-022: observe
  freezes the numeric channels only. Earlier routes stand: T1 → SA-005, F1 → SA-024, F2 → SA-016.

### Previous state (SA-039 implemented and pushed, 2026-09-24/25)

**SA-039 implementation is done and awaits a fresh-session review** (2026-09-24, one conversation).
STATE: `active_task: SA-039`, status `review_required`, `next_phase: review`. Receipt:
[SA-039-implementation.md](evidence/SA-039-implementation.md). Review input: `1efe361f…` from
[SA-039-manifest.json](evidence/SA-039-manifest.json) (18 files) on top of HEAD `3742fff`.

- **Next PI phase: the fresh review of SA-039** in a new conversation. Opener:
  `Continue — fresh review of SA-039`. First step:
  `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-039-manifest.json --rev 4c4728a`
  (expect 0 mismatches), then follow [REVIEW.md](REVIEW.md). Without `--rev`, the KT and PDF
  mismatch by design, because the next commit bumped the KT header. The receipt lists every decision
  consumer and the test that covers it. It also flags one scope interpretation for the reviewer:
  the untagged lesson micro-adjustment is contained too.
- **Committed and pushed on 2026-09-25 at the owner's word.** **Correction:** the owner asked at
  16:18 IST, not 10:48. `TZ=Asia/Kolkata date` returns UTC in Git Bash, so the push went out at
  about 16:22 IST, inside the blocked review window. Deploy `7ebd06c5` (`309d801`) reached SUCCESS.
  The new container was up at 16:28:56, so the 16:30 review still ran, on the new code in `adapt`
  mode: 19 completions and 19 weight writes, done at 16:54. The 20th ticker (metals) returned
  `no_envelope`; it has no forecast envelope, an existing gap. The job and its portfolio pipeline
  finished at 16:55. Nothing was missed.
  This correction is committed locally and **not pushed**; it rides the next push. Read IST with
  plain `date` from now on.
  `4c4728a` is the SA-039 change exactly as the review input describes it. The next commit bumps
  the KT header's `Code inspected` revision to `4c4728a` (edition 2026-09-25), links
  `learning_mode.py` and rebuilds the PDF. The deploy outcome is recorded in the commit after that.
  The code ships as `adapt`, so the deploy changes no decision.
- **What it does, in one example:** a ticker stores `technical = 0.0` at v41. With
  `rl.learning_mode: observe`, its forecast and analysis use the 0.12 default. After the review the
  file still says 0.0 at v41, and `<TICKER>_weight_observations.json` shows what v42 would have
  been. The code ships as `adapt`, so nothing changes until activation.
- **Activation is a separate owner decision after acceptance:** a one-line config commit, or the
  Railway variable `RL_LEARNING_MODE=observe`. Push only in a safe window (Step 0 rules). Afterwards,
  verify production read-only against the
  [baseline](evidence/SA-039-baseline-2026-09-24.md).
- **R2 done:** the baseline comes from today's 16:30 review logs (deploy `d9c459ae`). Chart weight
  was 0.0 for 9 of 18 logged tickers; 5 of the 6 `technical` tickers were at 0.0, which reproduces
  the 23 Sep figure; all 19 reviews wrote a new version. KT §1 and §5 now cite it. §5 also corrects
  the default: 0.12 generic, 0.10 renewable.
- **Routed self-review follow-ups:**
  - T1: the shared review test harness still constructs a live NSE session. Routed to SA-005, and
    it may explain the `key_registry.json` leak.
  - F1: chat context, `/scheduler/status` and the CLI show stored weights as if live. Routed to
    SA-024.
  - F2: the FeedbackAgent drift summary. Routed to SA-016.
- The Step 1 production checks below are otherwise unchanged. **OpenRouter was recharged**
  (owner, 2026-09-25). IPO-0a is still open.

### Previous state (DOC-001 accepted, earlier on 2026-09-24)

**DOC-001 was ACCEPTED on 2026-09-24** by a second fresh-session review, at `c832145` with review
input `63ff474c…`. The receipt is [DOC-001-review-2026-09-24.md](evidence/DOC-001-review-2026-09-24.md).
DOC-001 is `done`. STATE now has `active_task: null`, `next_task: SA-039` and `next_phase: implementation`.

- **Next PI phase: implement [SA-039](stories/SA-039.md)** in a new conversation. Opener:
  `Continue — implement SA-039`. Read the card's new "Routed input (R2)" section: the
  implementation must also record a sanitized pre-activation weight baseline. That record becomes
  the evidence for KT §5's "5 of 6 tickers" sentence, and §1's production row should name the
  2026-09-23 inspection when §5 is rewritten.
- The low follow-ups are routed, not waived. R3 (the KT harness imports nse 4.0.1, outside the
  `<4.0` pin) is on SA-033, and F5 stays on SA-005/SA-006.
- **Committed locally, not pushed** (at the owner's "commit", 2026-09-24): this conversation's work
  in one commit on top of `c832145`:
  - the review bookkeeping: the review receipt, STATE, this file, the implementation-receipt banner,
    and routed notes on SA-033 and SA-039;
  - the observability backlog (below).

  `origin/main` is still `e8df088`, so both local commits ride the next push. Push only on the
  owner's explicit word, in a safe window (Step 0 rules). The commits are docs-only, but every push
  still redeploys. **Manifest note:** the backlog changes
  three DOC-001 payload files (the KT, the PDF and the PI README) as normal post-acceptance
  maintenance. Verify the accepted input with `kt_manifest.py verify <manifest> --rev c832145`
  (0 mismatches). Against a later HEAD those three files will differ, and that is expected.
- **Step 1 production checks, 24 Sep**, from read-only `railway logs` (no ssh):
  - The build installed **nse 3.2.1**, so the pin works, and the fix has been live since
    23 Sep 22:44 IST (deploy `dfd7a15d`).
  - The **08:00 `ipo_refresh_am` logged no bid-ladder fetch failure**: current=7, 50 s, where the
    23 Sep 17:45 run had 10 `_req` failures. Rows on the volume are not visible from logs, so
    **IPO-0a stays open**; the 06:30 watchdog on 25 Sep or an owner probe confirms them.
  - The 06:30 watchdog raised 1 `warning`. The log doesn't name the check; it is inferred to be
    `ipo_signals_accruing`.
  - **0 OpenRouter 402s** since 23 Sep 13:30. The 23 Sep 16:30 review logged 18 runs costing
    **$0.40**, so a $0.97 balance leaves about 2 days. **Top up before 25 Sep 16:30.**
  - Still due: VARMORA rows after 17:45, and whether the 19:00 `ipo_deep_dive` stores its first
    verdict.

### Production observability — adopted 2026-09-24 (owner decisions D1–D5)

The owner asked for a proper production "fetcher" and a careful tool evaluation. The design is
[2026-09-24-production-observability-design.md](../../superpowers/specs/2026-09-24-production-observability-design.md).

- **Verdict:** no Prometheus, no OpenTelemetry SDK (field names only), no Arize or Langfuse for
  now, and Sentry deferred. Instead:
  - an in-app ops ledger in `telemetry.db`: `job_runs`, `source_health_day`, `error_signatures`
    and `budget_readings`;
  - the watchdog as evaluator, now also run right after each critical job;
  - a read-only `GET /ops/status` with `OPS_READ_TOKEN`, plus a fetcher CLI;
  - Healthchecks.io as the outside witness, alerting by Telegram.
- **Board:** SA-040 (S1, 3 points), SA-041 (S2, 3 points) and SA-042 (S1, 2 points) are added.
  SA-034 goes 5 → 6 points, SA-036 goes 3 → 4, and SA-035 is amended. That makes 39 planned
  stories and 140 points; Sprint 1 is 41 and Sprint 2 is 28. SA-039 is still first. The KT §12
  rows are added and the PDF is rebuilt (`check_kt_docs.py`: 0 errors).
- **Owner actions (settings only, no code). The owner will do these at the end**, so don't press
  for them earlier. Remind when a rollout needs one: the OpenRouter key limit for SA-035, and
  Healthchecks.io for SA-042.
  - Railway: turn on alerts for deploy failed/crashed and volume usage.
  - OpenRouter: set a monthly credit limit on the production key.
  - Healthchecks.io: create the account and connect Telegram, ready for SA-042.
- **Suggested ops order after SA-039:** SA-036 → SA-035 → SA-040 → SA-042 → SA-034 → SA-041.
  STATE's task order is unchanged, so "continue" still follows the existing sequence.

**Pushed 2026-09-24 06:56 IST at the owner's explicit "push it".** `a2c19c9..e8df088` was pushed, and
deploy `d9c459ae` reached SUCCESS at 07:03 IST. The boot log shows 24 jobs registered, no errors,
and the serper counter at 2,590/2,500. The 06:30 watchdog had already finished, and no job was due
before 07:30. Production now runs `e8df088`, which adds no application code over `a2c19c9`. The rest
of Step 0 below is the record of how the push was arranged.

### Step 0 — push the two local commits (done; see above)

Done at the owner's go-ahead, 23:30 IST:

- **`650c01c`** holds the earlier 22-path batch: the production assurance review, SA-033…SA-038,
  routed notes, and the DOC-001 payload `d5516ae0…`. `verify --rev HEAD` reported 0 mismatches.
- **The commit after it** holds the owner's three decisions (Step 2, now resolved). That is the
  SA-039 card, the SA-003 split, the SA-024 routed note, STATE, the PI README, KT §1/§5/§12, the
  rebuilt PDF, the IPO-0c record, this HANDOFF, the DOC-001 receipt ("Payload update 2") and the
  regenerated manifest (**review input `63ff474c…`**). After it, `verify --rev HEAD` must again
  report 0 mismatches.

**The push is still pending.** The owner chose "commit now, push later". At 23:28 IST a push would
have redeployed over `data_backup_nightly` (23:30), and probably over `audit_nightly` (23:45) and
`prompt_daily_deploy` (00:00).

**Every push redeploys production** (no watch-path rule until SA-037), and the in-memory scheduler
loses any job whose time falls inside the roughly 8-minute deploy.

- **Safest window: 00:10–06:20 IST.**
- Otherwise avoid 07:25–09:05, 11:55–12:05, 14:55–15:05, 16:25–17:05, 17:40–17:55, 18:55–19:20
  and 22:55–00:05.
- Push only when the owner says "push". Afterwards, confirm with `railway deployment list --json` that
  the new deploy reached SUCCESS. The two commits change documentation only, with no application code
  or requirements. The deploy still rebuilds and restarts the scheduler.

### Step 1 — time-sensitive production checks (read-only; the owner runs the probe)

| When (IST) | Check | Why |
|---|---|---|
| 24 Sep after 08:00 and 17:45 | VARMORA rows appear in `data/ipo/ipo_signals.jsonl` | First proof that `a2c19c9` fixed capture. VARMORA closes on the 24th. |
| 24 Sep after 19:00 | `ipo_deep_dive` post-close for VARMORA stored a row: `ipo_verdicts.jsonl` exists; note whether `substance` is still null | First stored P3 verdict. The 23 Sep T−1 run stored nothing (`demand=None substance=None`). |
| Until 25 Sep | `railway logs \| grep -i "error code: 402"` | The owner reported an OpenRouter balance of **$0.97**, with a top-up on 25 Sep. The existing streak alert can miss a low-balance pattern (SA-035). |
| After capture is proven | Close `IPO-0a`: delete `ipo_p0_live_window_check` from `config/milestones.yaml`, evidence in the commit message | Not before. |

The probe is `analysis_data/prod_probe_20260923.py`. It is ignored, so it may be missing in another
checkout; it prints counts and IPO fields only. Run it from Git Bash at the repo root:

```bash
railway ssh "cd /app && echo $(gzip -9c analysis_data/prod_probe_20260923.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

Claude can run `railway status`, `railway deployment list --json` and `railway logs <id> -n 2000`
(plus `--build`), after prepending `/c/Program Files/nodejs:$HOME/AppData/Roaming/npm` to PATH.
**Claude's `railway ssh` is blocked by the auto-mode classifier.** Volume reads go through the
owner.

### Step 2 — owner decisions: all three resolved 2026-09-23, about 23:30 IST

1. **Learning containment: yes, reset to defaults.** The containment is split out of SA-003 as
   **[SA-039](stories/SA-039.md)** (P0, Sprint 1, 3 points, no dependencies). It is placed first in
   STATE's task order, and SA-003 went from 5 to 4 points. SA-039 resets on the **read side**:
   - Decision consumers (forecast, public analysis, and the review's re-scoring and re-forecast) use
     the sector's configured default table.
   - Lesson emphasis stops.
   - The adapter keeps computing into a diagnostic record, and stored `WeightMemory` is never
     mutated.

   So there is no production data migration, and rollback is exact. Example: stored
   `technical = 0.0` stays 0.0 on disk, while the forecast uses 0.12. The code ships with `adapt` as
   the default. Activation is a separate one-line config commit, pushed only with the owner's
   go-ahead.

   Also found while writing the card, by code inspection: the verdict-shadow field
   `learned_weights_used` is true whenever any weights are passed, defaults included, so it
   overstates learned-weight use. That is routed to SA-024, and SA-039 must not use it as evidence.
2. **IPO-0c: GMP stays dark.** It is closed in the IPO plan with no code change, because `gmp_pct` is
   already a dark froth input. The serper.dev dashboard was **not** read, so the question of real
   account credit stays with SA-035.
3. **Push timing:** commit now, and push only when the owner says so, after 00:10 IST (Step 0).

### Step 3 — then the normal PI sequence

- ✅ **DOC-001 accepted 2026-09-24** (see START HERE). The bullets below are the pre-review record.
- **DOC-001** was `review_required`, with review input
  **`63ff474cec51a5810af84dca279a8fcdaa93239cd65230e6f5cd738b01128dd0`**.
  - Its fresh-session review runs in a **new conversation**. It can run against the local commits
    before the push. Opener: `Continue — fresh-session review of DOC-001`.
  - Receipt: [the 2026-09-23 section](evidence/DOC-001-implementation.md#remediation-phase--2026-09-23).
    F1–F4 are fixed, F5 is routed to SA-005/SA-006, F6 is done, and F2 was fixed by the PDF rebuild.
  - The payload changed twice more. The first change added the SA-033–SA-038 KT rows ("Payload
    update"). The second added SA-039's row and a labelled PI-target paragraph in KT §5 ("Payload
    update 2"). Check that §5 paragraph against `daily_review.py` Step 5.
- **After DOC-001 is accepted:** select the next ready story, but do not start it in the review
  chat. By STATE's order that is **SA-039**, then SA-001.
- **Ready now** (all dependencies done): SA-039 (S1, P0), SA-001 (S1, P0), SA-002 (S1), SA-004 (S1),
  SA-005 (S1), SA-007 (S1), SA-033 (S1), SA-035 (S1), SA-036 (S1), SA-038 (S1), SA-006 (S2), SA-009
  (S2) and SA-010 (S2, P2). There are 39 SA stories in total: 36 planned (130 points) and 3 stretch.
  Sprint 1 is 35 points, and Sprint 2 is 24.
- **IPO (PI Prospect)** stays paused apart from the Step 1 checks. Open items: IPO-0a (Step 1),
  IPO-0d (brief freshness), IPO-0e (P1 spine in production), and IPO-5a/5b (gated). IPO-0c is
  closed as "no". See `docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`.

### How the owner likes to work (observed this session)

- Explain each decision with a small concrete example (e.g. ₹100 → predicted ₹110 → closed ₹105).
- Welcomes deep research and wants every recommendation turned into board tasks.
- Commits and pushes happen only when the owner says so; each push is asked separately.

### Backlog additions and owner decisions — 2026-09-23 (late)

At the user's request, every recommendation in the
[production assurance review](../../audit/2026-09-23-production-assurance-review.md) is now on a
board. **New stories:** SA-033 (dependency lock), SA-034 (silent-degradation watchdog), SA-035
(LLM/Serper credit exhaustion; OpenRouter was at $0.97, top-up 25 Sep), SA-036 (job outcomes),
SA-037 (deploy/missed-job hygiene), SA-038 (lapsed milestones). **SA-007 moved to Sprint 1** (no
off-site backup). Notes were routed to SA-003, SA-008, SA-010, SA-011, SA-023 and SA-028. The IPO
plan gains `IPO-0d` (brief freshness) and `IPO-0e` (P1 spine in production).

**Decisions that were waiting on the owner** have all been resolved; see Step 2 above. Containment
became SA-039, GMP stays dark, and the push waits for the owner's word after 00:10 IST.

### Production read — 2026-09-23 (read-only; supersedes "no railway access" notes below)

The Railway CLI now works here (Node installed, folder linked to project `carefree-renewal` /
`production` / `StockAgent`). The user ran one read-only probe through `railway ssh`; Claude's own
`railway ssh` is blocked by the auto-mode classifier. The probe is
`analysis_data/prod_probe_20260923.py` (ignored). Run it from Git Bash:
`railway ssh "cd /app && echo $(gzip -9c <probe> | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"`.

- **Deploy:** `b68bc02` is SUCCESS (2026-09-23 07:59 UTC).
- **D6 — closeable.** In the outbox, before 21 Sep there were 77 email rows dead and 77 push
  delivered. Since 21 Sep: 3 email dead, all before the redeploy (last at 07:52 UTC on the 21st);
  **8 email delivered, 0 dead since**, and 11 push delivered (email/push parity). "Delivered" means
  provider-accepted. This is production evidence toward SA-006, **not** its acceptance.
- **IPO live capture is broken in production since ~18–19 Sep.** Cause confirmed from the logs:
  `'NSE' object has no attribute '_req'`. `nse` 4.0 (31 Aug) removed `NSE._req`, and the 21 Sep
  rebuild installed 4.0.1 under the open-ended pin `nse>=2.0.0`. The fix is the pin
  `nse>=2.0.0,<4.0` plus tests of the real dependency. The 19–21 Sep window, on the old 3.2.1
  image, is still unexplained. The 22 Sep brief's category figures were 2–3 days stale (NSE QIB 1.53× shown,
  final 12.68×). VARMORA has no ledger rows, and `ipo_signals_accruing` is warning. **Do not close
  IPO-0a.** Full evidence is under IPO-0a in the plan.
- **P1 spine absent in production** (`data/ipo/ipo_history.jsonl` missing).
- **IPO-0c:** serper counter 2,590 in September (default budget 2,500). Recommend GMP stays dark;
  check serper.dev for real remaining credits.
- **P3:** no `ipo_verdicts.jsonl` yet. That is expected for NSE/SONA, because their T−1 run predates
  the deploy. VARMORA's T−1 run is 23 Sep 19:00 IST, but its demand inputs are dark (no ledger rows).
- **P3 run observed:** `ipo_deep_dive` fired at 19:01 IST for VARMORA (`t_minus_1`, 16 docs, 9
  extracted), with demand and substance both dark, so `written=False` ("every index dark, not
  stored").
- **After the fix deploys:** confirm VARMORA ledger rows land at the 08:00 / 17:45 IST refreshes on
  24 Sep, the day it closes (re-run the probe). Only then revisit IPO-0a.

### IPO stays paused

`ed1b900` (IPO-4c) is pushed and `origin/main` is current, which closes **Sprint 4** of PI "Prospect".
The user chose to **pause IPO work and wait for live production evidence** rather than start `IPO-5a`.
Do not start an `IPO-` task unless the user brings evidence or says so. One encouraging note from the
review: the incremental-documentation discipline DOC-001 introduced **is** being followed — the 23→24
job-count change propagated correctly to four documents, and cases 05-F/05-G were added with their
stories.

After DOC-001 is accepted, `SA-039` is the first remediation story. It was promoted ahead of `SA-001`
by the owner on 2026-09-23 (Step 2). Select it, but do not start it in the acceptance conversation.

### Why IPO is waiting, and what arrives on its own

Everything through Sprint 4 is built and now deployed-on-push; **none of it has been measured in
production.** The first real evidence appears without anyone doing anything:

- **Tonight and each evening after**, the `ipo_deep_dive` job (19:00 IST) should hit its `post_close`
  slot for **NSE** and **SONA**, both `bidding closed — awaiting listing`.
- **2026-09-23** is the first genuine **T−1** candidate: **VARMORA** closes 24 Sep (the 22 Sep brief
  said "closes in 2 days"), so the expensive research slot should fire that evening.

Check `GET /scheduler/status` for the `ipo_deep_dive` last-run outcome, or whether
`data/ipo/ipo_verdicts.jsonl` now exists on the volume. Until a row exists, `IPO-5a` would be surfacing
code written against an imagined row.

### IPO-0a — criterion 1 is MET; one piece of evidence remains

The user supplied the **22 Sep 08:50 IST production brief**. It satisfies the live-observation half in
full — this is the subject the milestone had never had:

| Issue | Heading rendered | Subscription rendered |
|---|---|---|
| NSE | `bidding closed — awaiting listing` | 3.78261× overall (QIB 1.52996×, retail 0.722428×, 39% at cut-off) |
| SONA | `bidding closed — awaiting listing` | 1.45233× overall (QIB 0.459178×, retail 1.28955×, 58% at cut-off) |
| VARMORA | `closes in 2 days` (open) | `data pending` — correct; it opened that morning |

Real × values, not `data pending`, under correct state headings. **Still needed:** the ledger half —
either no `ipo_signals_accruing` `pending` alert since NSE/SONA opened on the 17th (Inbox or
`GET /delivery/alerts`), or a volume read. ⚠ `railway ssh` is NOT available: this machine has no Node,
so the CLI's npm install route is closed too (a standalone binary from Railway's releases would work).
Do not delete the milestone entry on the brief alone.

### ⚠ Open question raised by that brief — worth one look before IPO-5b

Both closed issues rendered **"(NSE only)"**. Per `services/data/fetchers/ipo.py`, `total_x_nse_only`
clears only when the all-exchange **combined** ladder is fetched, and `_enrich_open_issues` fetches a
live ladder only while `issue_state == "open"` — a closed issue inherits via `_carry_forward`. So the
final book recorded in production for NSE and SONA looks like the **NSE-only under-report**.

Against the 21 Sep 14:15 IST scratch fetch in the plan's IPO-0a note (total 3.817×, **QIB 7.81×, retail
1.10×, 14% at cut-off**) the totals are close and the categories are not. Combined-vs-NSE-only would
explain it; so would something wrong. **This is unresolved and was not investigated** — it needs
production data this machine cannot reach.

**Why it matters:** P3's `demand` is computed from exactly those category figures (`qib_x`, `retail_x`,
`cutoff_share`), and `IPO-1` fitted its thresholds on the spine's combined subscription. If production's
final book is habitually NSE-only, `demand` is being computed on a different quantity than it was fitted
on — which would undercut the forward hit-rate `IPO-5b`'s gate depends on. Resolve before `IPO-5b`.

### Also outstanding, user-side

- `IPO-0c` still waits on the production Serper counter (`cat data/logs/api_usage.json`, or the boot log
  `[api_usage] counter intact at boot ... serper=N/2500`). `fetch_gmp()` also has no production caller.
- `docs/StockAgent-Three-Loops.pdf` is stale and cannot be rebuilt here — no Node, no Chromium cache,
  although `node_modules/playwright` is vendored. Install Node LTS, then
  `npx playwright install chromium` and `python scripts/docs/build_kt_pdf.py`. It is the only
  `check_kt_docs.py` error; 24 job IDs, 221 local links and 13 configuration claims are green.

**IPO-4c is done** (2026-09-22): the audit lane. `Lane` gains `"ipo"`; `core/ipo/listing.py` resolves the
listing date and issue price (P1 spine first, NSE cache second); `grade_ipo_lane` in
`core/audit/outcomes.py` grades the newest stored verdict per issue at 1/5/21/63/126/252 trading days
from listing, with `entry_close` = the **issue price**, documented at the schema field rather than left
to be inferred. Three design points the plan's outline did not reach, all now in its step detail:
`is_correct` was **not** taught an IPO word — `core/audit/rules.py` gains `is_ipo_correct` beside
`is_switch_correct`, on the precedent that a different question gets its own answer; **only one row per
issue can carry True/False** (the listing-day horizon, of a post-close verdict, whose lean asserts a
direction), every other horizon carrying the return and no claim; and an issue with no tape yet counts as
`awaiting_listing`, deliberately **not** `skipped_unpriceable`, because the nightly job feeds that
counter to `alert_job_partial_output`. IPO rows are excluded from the rendered audit report and reach no
surface. 37 offline tests; full suite **3126 passed, 5 skipped**. `TEAM_TESTING_GUIDE.md` gained case
**05-G** (12 duties, **59** cases, all still NOT RUN).

⚠ **`IPO-4c` has had implementation and same-conversation self-review only — no fresh-session review.**
That matches how `IPO-3*`/`IPO-4a`/`IPO-4b` were closed under this plan's own "commit per task"
discipline, and it is not the `REVIEW.md` gate. If a fresh review is wanted, the three highest-value
targets are: the horizon off-by-one (horizon 1 must be the listing day, not the day after); the
scoreability rule (nothing outside an evidenced, directional, listing-day row may carry True/False); and
containment (no IPO row may move a number in `build_report`). All three have tests; the question a
reviewer should ask is whether the tests can pass while the property is false.

⚠ **No production IPO row has been graded and none can be yet**, for three reasons that are not code:
the `ipo_deep_dive` job reaches production only on deploy; `data/ipo/ipo_verdicts.jsonl` does not exist
there until it does; and grading additionally needs the issue in the P1 spine, which
`scripts/ipo_backfill.py` rebuilds **manually** from the bhavcopy volume. Until an issue reaches the
spine the NSE cache is the only resolver, and NSE drops issues from `past` after a few months — so a
252-td horizon on an issue that never reached the spine sits in `awaiting_listing` for good. That is a
visible counter in the lane summary, not a silent loss. Wiring the spine to a job is unclaimed work; it
is not in this plan.

**IPO-4b is done** (2026-09-22): `core/ipo/narrate.py` + `core/config/prompts/shared/ipo_narrate.py`.
The note is the `IPO-5a` explainer content, stored on the verdict row and reaching **no surface**.
What the plan put in the prompt, the build put in the code path: the verdict is never passed to the
narrator at all; every number in the prose must appear in the structured findings (rounding yes,
arithmetic no); an advice/verdict vocabulary rejects the note; and a rejected or failed note falls back
to a deterministic template from the same facts. The model is handed source COUNTS, never URLs — the
"Sources:" line and the "research view — not advice" framing are appended in code on both routes.
Cost shape: a note is bought only for a row that will actually be stored, and reused while the facts
digest holds, so an issue costs at most two model calls — T−1 and the close (the note states which).
⚠ This nuances `IPO-4a`'s "post-close costs nothing": that remains true for network and extraction; the
narration adds exactly one call at the close. 45 offline tests.

**IPO-4a is done** (2026-09-22): `core/ipo/deep_dive.py` + the `ipo_deep_dive` job at 19:00 IST.
The design point that was not in the plan's table: the visibility gate counts only `short.evidenced`
rows, which exist only after the book closes, so the sweep has **two slots** — the T−1 research run and
a post-close re-read off the cached dossier + cached extraction (zero network). A verdict with every index
dark is not stored (the capture ledger's "a row asserts a reading was taken"). 32 offline tests. ⚠ The
job reaches prod only on deploy; until then `data/ipo/ipo_verdicts.jsonl` does not exist in production.
The first real T−1 candidate after deploy is whichever mainboard issue closes the day after.
⚠ `docs/StockAgent-Three-Loops.pdf` is stale (was already stale at `5f7238c`; §8/§9 of the KT changed at
`IPO-4a`, §8 again at `IPO-4b`, and §7 + §8 again at `IPO-4c`). No Node/Chromium on this machine —
rebuild with `python scripts/docs/build_kt_pdf.py` where there is. It is the only `check_kt_docs.py`
error; 24 job IDs, 221 local links and 13 configuration claims are green.

**IPO-0a status (2026-09-21 afternoon):** worked, not closeable that day — nothing was in the
`closed — awaiting listing` state until NSE and SONA closed that night. Read the "Progress 2026-09-21"
note under IPO-0a in the plan; it names the two pieces of production evidence the 22 Sep 08:50 brief
provides. Do not delete the milestone entry without both.

**IPO-0b is done** (size-tiered demand lean; see the plan's "Done 2026-09-21" note).

**IPO-1 is done** (2026-09-21 evening): the per-horizon read is in the plan under IPO-1 with the decision — fit the SHORT (post-close listing-day) horizon to QIB/total demand, LONG stays dark, OFS never scored. `ipo_p1_backtest_review` removed from the registry. Sprints 3–5 may now get step detail.

**IPO-0c is blocked on you:** it needs the production Serper counter (`railway ssh` → `cat data/logs/api_usage.json`, or the boot log line `[api_usage] counter intact at boot ... serper=N/2500`). Also found: `fetch_gmp()` has no production caller, so provisioning the key would need a wiring change too — see the plan's IPO-0c progress note.

**Sprint 2 is done** (2026-09-21 evening, `e8abda3` + `c8e54c2`): `core/ipo/research.py` (Tavily dossier, cached per issue) and `core/ipo/extract.py` (per-document extraction, corroboration gate). 60 offline tests over three real captures. Not yet wired to any job — that is `IPO-4a`.

**Sprint 3 is DONE** (`4c26072`, `c60f602`, and `IPO-3c`/`3d`/`3e` on 2026-09-22): `hype.py` (fitted `demand` + unfitted `froth`), `substance.py` (S, never fitted), `verdict.py` (the §3 grid, SHORT from `demand`, LONG hard-wired dark) and `verdicts.py` (the append-only store). The model runs end to end on the recorded dossiers and reaches no job and no surface.

**`ipo_verdicts_visible_gate` is now in `config/milestones.yaml`**, deadline 2026-12-31 or 60 days of forward P2 rows, whichever comes first. It is the gate P3 has to pass before any verdict is shown. ⚠ A milestone reaches prod only on deploy — the `registry_is_current` invariant watches for that.

**Sprint 4 is complete.** `IPO-4a` (the `ipo_deep_dive` job at 19:00 IST) wired Sprints 2–3 to the clock,
`IPO-4b` (the narrator) gave the row its prose, and `IPO-4c` (the audit lane) gave it forward grading.
The model now runs, writes, narrates and will be measured — and still reaches no user.

Still open from Sprint 0: `IPO-0a` closes on the 22 Sep brief; `IPO-0c` still waits on the production Serper counter (see below).

Read that plan's "State of play as of 2026-09-21" section first. Sprints 0–4 are
executable and built; Sprint 5 carries acceptance criteria and a gate column but
no step detail yet.

The Three Loops PI below is **paused, not abandoned** — DOC-001 still awaits its
fresh-session review and all 32 `SA-` stories remain `todo`. `STATE.json` was
deliberately not touched by any IPO task: it describes PI-2026-09, which has zero
IPO scope, and writing an IPO `active_task` into it would misrepresent that PI.

## Resolved since September 19 — the email outage

The September 19 investigation below is superseded on its central question.

- **Cause:** Railway disables outbound SMTP on Free/Trial/Hobby. Production
  logged `[Errno 101] Network is unreachable` on every send since 2026-07-16
  (n=103 over 21 days — card **D6**, spec `2026-08-24-three-loops-pi-design.md` §15.4).
- **Fix:** upgraded to Pro **and redeployed**. The upgrade alone changes nothing
  for an already-running container; the 25-day-old deployment was still under the
  Hobby network policy. Verified 2026-09-21 — a triggered brief reached the inbox.
- **D6 is closeable** after a day of clean logs.
- ⚠ The [September 19 audit](../../audit/2026-09-19-delivery-deployment-review.md)
  advances a Gmail-credential hypothesis that production evidence **disproved**.
  Its §1 and §3 are wrong on cause. Treat it as a record of what was believed on
  the 19th, not as current diagnosis.

### Shipped in `590bc9f` (on `origin/main`, deployed)

- `outbox.last_error`, written on retry and dead-letter, cleared on recovery —
  a failed send now explains itself without container logs. Partially satisfies **SA-006**.
- An HTTPS Resend transport beside SMTP; `EMAIL_TRANSPORT=auto` picks it only
  when `RESEND_API_KEY` is set, so current behaviour is unchanged on Pro+SMTP.
- Per-account recipients via `resolve_recipient()`. ⚠ **Known gap:** a transient
  `users.db` lookup failure falls back to `DELIVERY_EMAIL_TO`, which in multi-user
  beta could route a tester's brief to the owner's inbox. Tighten before beta.
- Tests: 2832 passed, 5 skipped (full `tests/unit`).

## Operational investigation requested September 19

The user temporarily resequenced a read-only review of missing scheduled emails
and Railway deployment state. See the [dated findings](../../audit/2026-09-19-delivery-deployment-review.md).
Public HTTP and remote Git checks are current; private production logs/configuration
could not be refreshed because this machine has no Railway CLI/login/token.
September 10 delivery counts remain historical. Current service inventory, source
branch, scheduler activity and SMTP connectivity still need authenticated inspection.
No application, deployment, variable, job or notification was changed. This is
an operational investigation, not DOC-001 acceptance or SA-006 implementation.
The PI state and unresolved dependencies below are preserved.

## PI handoff retained from September 15

**DOC-001 implementation is complete; fresh-session review is required.**
No remediation code was changed or accepted. All 29 planned SA stories and
three stretch stories remain `todo`.

Next task: [DOC-001](stories/DOC-001.md). Next phase: **fresh-session review**
under [REVIEW.md](REVIEW.md). Read the [implementation receipt](evidence/DOC-001-implementation.md),
verify the [manifest](evidence/DOC-001-manifest.json) and inspect the worktree.
Review-input SHA-256: `90c005c46417db97d6e3f6feba2431aae66a8ad93037e852e9823ad7936125c0`.
Do not sign off this phase using its same-conversation self-review.

## Scope and deliverables

The user explicitly resequenced two tasks ahead of SA-001:

1. Current-code KT Markdown/PDF including all PI targets, clearly separate
   from implemented and production-verified behavior.
2. A separate human testing guide: assignable duties, practical cases,
   expected results and evidence; no code-intensive review or named assignment.

The updated entry points are [Technical KT](../../TECHNICAL_DESIGN.md),
[generated PDF](../../StockAgent-Three-Loops.pdf),
[architecture](../../ARCHITECTURE.md) and
[team testing guide](../../TEAM_TESTING_GUIDE.md).
The guide has 12 duties and 60 cases (05-F added at `IPO-4b`, 05-G at `IPO-4c`, 10-E at the 2026-09-23 DOC-001 remediation), all NOT RUN.

Every future implementation updates its affected living docs/test cases and
regenerates the PDF when its source changes. SA-031 now means the final
consistency check; SA-024/SA-027/SA-029 remain unresolved dependencies. After
DOC-001 acceptance, select SA-001 as the first remediation story, but do not
start it in that review conversation. *(Superseded 2026-09-23: SA-039 now comes first.)*

## Verification and limitations

- HEAD and September 15 Railway deployment metadata match
  `9a805878ed19c0cda7833d5b897ac05ee407436d`; deployment status SUCCESS.
  Only deployment context was refreshed. The [September 10 audit](../../audit/2026-09-10-repository-production-review.md)
  remains the detailed dated production evidence.
- 323 existing tests passed across 30 files, Python 3.13.11 on Windows,
  in an isolated source copy with dotenv disabled and external transports
  blocked. TestClient and a Windows asyncio local socket pair are allowed.
  No full-suite or Linux/Python-3.11 parity claim.
- 16-page PDF: searchable, source-hash matched, rendered and visually checked.
  All 32 SA targets/dependencies/titles, 23 possible scheduler IDs (24 since `IPO-4a`), 13 config
  assertions and local documentation links checked. Receipt has exact results.
- Known grading, timing, health, weight-bound, delivery and recovery gaps
  remain. Neither tests describing existing behavior nor this KT establishes
  learning benefit. Human acceptance and future market evidence remain pending.

## Preserve and continue safely

- Pre-existing user audit banners/provenance were retained. The original PDF
  is preserved byte-for-byte in [the archive](../../archive/README.md); the user
  explicitly requested updating its primary path.
- No application source/configuration change, deployment, production job,
  backfill, notification, commit or push was performed.
- Do not read/expose `.env` or private raw logs. Raw local diagnostics are
  ignored under `analysis_data/kt_20260915/`; audit history under
  `analysis_data/audit_20260910/` may be absent elsewhere.
- Preserve other unrelated worktree changes. Manifest covers the intended
  payload; inspect STATE, HANDOFF and receipt bookkeeping separately.
