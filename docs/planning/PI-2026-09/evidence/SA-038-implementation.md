# SA-038 implementation receipt — judging the lapsed production-verification milestones

- **Story:** [SA-038](../stories/SA-038.md); evidence §1.1 of the
  [2026-09-23 production assurance review](../../../audit/2026-09-23-production-assurance-review.md).
- **Context:** implemented 5–6 Oct 2026 in **one new conversation** opened with "continue" (about
  23:44 IST on 5 Oct). STATE: `review_required`. A same-conversation self-review was done; it is
  not the fresh review.
  - The auto-mode classifier blocked the registry edit as "audit tampering" (about 00:00 IST). It
    was not worked around.
  - The owner added four narrow allow rules to their own `.claude/settings.local.json`: the edit
    script, `Edit(config/milestones.yaml)` and two `git diff` reads. The phase resumed at 07:54 IST
    with "continue SA-038". That settings file is the owner's change, and it is **excluded** from
    this story's manifest.
  - The owner ran the read-only probe at 10:41 IST and pasted its output. Judging from it finished
    the phase.
- **Baseline:** `a502cf7` (SA-010's KT bump, pushed by the timed job at 00:10:07 IST and deployed
  as Railway `8b97dab8`). Another session recorded that push in STATE and HANDOFF at 00:17; this
  phase keeps those lines.
- **Nothing** was committed, pushed, deployed or configured. Claude read no production state. Its
  only Railway call was the read-only `railway deployment list`.

## What it does, in one example

On Fri 2 Oct at 06:30 the ops mail carried "F3 provenance checkpoint … LAPSED — deadline 2026-09-04
passed and it is still not done", a `critical`. Nothing was broken. `f3_checkpoint` is a
`manual_confirmation` entry, which has no signal of its own. It stays pending until someone deletes
it, and after its deadline the engine re-sends a critical every 7 days (`engine.py`,
`_LAPSED_REPEAT_DAYS`). By 23 Sep, 8 of the 9 milestones were in that state, so "critical" had come
to mean "nobody wrote the judgement down".

F3 itself works. The probe found that 1,021 of 1,041 lessons written since F3 carry their dated
headlines. So the entry is deleted, with that count recorded here.

After this change, take the state production holds now: every milestone was last notified
`critical` 7 days earlier. Force every check to `pending` and run the real watchdog on Wed 7 Oct at
06:30. It sends **no critical**, no notice for a deleted entry, and it drops their state. On the
baseline registry the same test fails.

## The judgements

> **Corrected by the fresh review (2026-10-06, M1).** The `a1_routing_prod_verify` row below
> says "Verified". By SA-009's recorded 30 Sep inventory, A1 did not stop the bleed: copies
> of other sectors' tickers kept receiving writes until SA-009's fix and its 1 Oct quarantine.
> The entry is deleted as **superseded by SA-009**, not as verified for A1. See the
> [review](SA-038-review.md).

Evidence labels as in the audit:
- **Measured:** observed in production. Either earlier, and recorded in the entry or a receipt, or
  by this phase's owner-run probe.
- **Code:** read in source.
- **Decision:** a recorded choice, not a measurement.

| Entry (old deadline) | Judgement | Evidence |
|---|---|---|
| `atlas_c11_cutover` (08-23) | **Deleted.** Done. | **Code:** `config.yaml` sets `atlas.enabled: true`, and `atlas_cutover_pending` returns `satisfied` once the flag resolves true. By code, the entry was already silent. |
| `f3_checkpoint` (09-04) | **Deleted.** Verified. | **Measured (probe):** see "Production result", F3. |
| `hard_bind_observation` (08-31) | **Deleted without a verdict;** folded into SA-012 and SA-014. | **Decision.** The review would grade `direction_accuracy_7d`, a target the September audit found defective (F02, F04). Any verdict would certify a known-bad number. Notes on both cards name the two cuts no single series may span: AUD-060 (2026-07-17) and hard-bind (2026-08-03). |
| `a1_routing_prod_verify` (09-08) | **Deleted.** Verified. | Part (a) was **measured** on 2026-08-25. Part (b): **measured (probe)**, see A1(b). |
| `b1_run_history_prod_verify` (09-15) | **Deleted.** Verified. | (a) and (c) were **measured** on 2026-08-26. (b): **measured (probe)**, see B1. |
| `b2_data_health_prod_verify` (09-15) | **Deleted;** its open half carried to SA-002. | **Measured 2026-08-26** (recorded in the entry): all four acceptances met; 13 rows, `ok` 12 / `degraded` 1; the mirror matched; (c) matched exactly. The entry's own "DO NOT CLOSE AS HEALTHY" is card B6, which SA-002 implemented (accepted; deployed 27 Sep). It is now tracked only by SA-002's `production_verification` (`pending_observation`). A note is on the SA-002 card and in STATE. |
| `e1_error_capture_prod_verify` (09-15) | **Deleted;** (c) judged **not applicable**. | **Measured 2026-08-26:** (a), (b) and (d) met. (b), the one that mattered: 44 `app_logs` rows carry a real run id and ticker. **Decision on (c):** the loudest production errors come from yfinance's own logger, which E1's `exc_info` change cannot reach by construction. It was the wrong acceptance, not a failed one. |
| `ipo_p0_live_window_check` (09-15) | **Kept open; re-dated to 2026-10-31**, with the measured ledger evidence in its reason. | The card keeps it open until capture is verified. **Measured:** the brief half (22 Sep 08:50 brief), and now the ledger half (probe, IPO section). Closing it means closing **IPO-0a** in the paused IPO plan. The receipt committed in advance that SA-038 would not do that, so it is the owner's call. |
| `ipo_verdicts_visible_gate` (12-31) | Unchanged. | In date. |

The one entry left open opens `RE-DATED 2026-10-06 by SA-038 (was 2026-09-15, lapsed): …` and
gives the reason. The registry header now says how an entry is retired. **After this phase no
milestone is past its deadline, and the open one says why.**

### The SA-039 backstop

The card says SA-038 cannot be accepted while SA-039's `production_verification` is
`pending_observation` with no dated reason. It still read `pending_observation`, with "Pending: …
P3". In fact P3 had **passed** on 2026-10-01 at 10:25 IST (`pending_production_checks`,
SA-039-P3), and the activation record had closed the window that day.

All three card conditions were measured:
- `observe` logged (P1, P2);
- `weight_version` unchanged across two reviews (P2, all 20 at the baseline);
- observation records landing (19 each).

So this was a bookkeeping lapse. STATE now says `verified` (`verified_ist` 2026-10-01 10:25, with a
note naming SA-038 as the recorder). The activation record's header says the same.

## The probe (owner-run, read-only)

`analysis_data/sa038/sa038_probe.py` (ignored). It prints counts, dates, tickers and sector names
only: no headlines, lesson text, logs, env values or user data. It opens SQLite with `mode=ro`, and
A1b goes through `store_inventory.build_inventory`, the read-only module SA-009's own `check` used
in production. Run from Git Bash at the repo root:

```bash
railway ssh "cd /app && echo $(gzip -9c analysis_data/sa038/sa038_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

**Pre-registered criteria** (written into this receipt before any production output was seen):

- **B1 closes** if `run_summaries` in `telemetry.db` is non-zero, its oldest row predates at least
  one redeploy since 26 Aug, and `data/logs/run_summaries.jsonl` is present.
- **A1(b) closes** if no `automobile/<TICKER>` store with files belongs to a ticker owned by another
  sector (`bleed_stores 0`, `wrong_roster 0`).
- **F3 closes** if post-F3 lessons carry `evidence` and post-F3 dossier observations carry `source`,
  in the documented `YYYY-MM-DD — headline` form, and the share is not zero in any month with rows.
  An empty value on a newsless day is honest by design, so below 100% is not a failure.
- **IPO:** the section only informs the IPO-0a note. SA-038 does not close that entry.

**Local dry run** (5 Oct 23:57 IST, through the same transport, against the stale local `data/`):
every section ran, ending in `READ-ONLY`. Local data proves only that the script runs. SQLite's
shared-memory index `data/telemetry.db-shm` was touched, as it is for any reader.

### Production result — 6 Oct 2026, 10:41 IST (05:11Z), deploy `8b97dab8`

The owner pasted the output. A copy is in ignored `analysis_data/sa038/probe_20261006.txt`, without
12 `[SectorRegistry] … 'bfsi'/'it'/'re'` log lines from the known unmanaged single stores.

- **B1: met.**
  - `run_summaries` holds **888 rows**: first `2026-08-26T11:03`, last `2026-10-05T18:05`, over 35
    distinct days (Aug 72, Sep 714, Oct 102).
  - `data/logs/run_summaries.jsonl` has **888 lines** with the same first and last day, so the
    mirror is in step.
  - The first row is the 26 Aug 16:30 IST review, B1's first writer. `railway deployment list`
    (read by Claude, read-only) shows the last 20 deploys, all after 23 Sep 13:17 UTC. All of them
    came after that first row, and the count never reset.
- **A1(b): met.**
  - Inventory `8fb9419e`: 176 stores, `wrong_roster` 0, duplicate tickers 0, roles canonical 21 /
    unowned 18.
  - Automobile stores with files: 9, of which 5 are canonical. The 4 unowned are BAJAJ-AUTO,
    HEROMOTOCO, M&M and MARUTI: automobile companies with no managed entry, newest files 2 and
    22 Jul, before A1. `bleed_stores 0`.
  - That is 5 days after SA-009's quarantine (1 Oct 00:10). Since then there were 5 restarts (deploys
    `ccd6ca78`, `e7a994a5`, `8983ab80`, `f4be41ef`, `8b97dab8`) and the 1, 2 and 5 Oct 16:30
    reviews.
  - This also meets the first half of **SA-009's** "still to observe", recorded in STATE. The
    scorecard half remains.
  - Not explained: unowned stores rose from 17 (1 Oct) to 18. The extra store is not under
    `automobile/`, so it is not a bleed.
- **F3: met for lessons. The dossier half is met by the pre-registered rule, with a limit stated
  below.**
  - **Lessons:** ticker ledgers have 1,041 lessons touched since 2026-08-07, and **1,021 (98%)**
    carry `evidence`. By month: Aug 325/345, Sep 610/610, Oct 86/86. All 2,005 items are well formed,
    84 of them `market-wide`.
  - Sector ledgers: 108 of 109. The market ledger: 9 of 9.
  - **Dossier observations:** 13 of 391 post-F3 rows carry `source` (Sep 11 of 312, Oct 2 of 79),
    all 13 in the documented form. No August rows remain, inferred from the capped buffer
    (`DOSSIER_MAX_OBSERVATIONS`).
- **IPO ledger:**
  - `data/ipo/ipo_signals.jsonl` has 198 rows. **54 are since 24 Sep**, over 15 issues (VARMORA 2),
    all `open`; the last is 2026-10-05. Capture resumed after `a2c19c9`.
  - `data/ipo/ipo_history.jsonl` is **missing** (the P1 spine, N9).

### Findings from the probe

- **The F3 dossier denominator (limit, stated, not routed).** The share is low by design, and this
  was found in code only *after* seeing the data.
  - Only the research loop gives an observation a `source`: `question_researcher._provenance`.
  - The daily curator's observations carry none on purpose. The comment at `dossier_curator.py:76`
    says: "absent from daily curator output (its evidence is the whole day, not one article)". Event
    ingestion carries none either.
  - So 13 is the count of sourced research observations, and the probe did not split research rows
    (`[research] …`) from the others.
  - The milestone asked whether `source` is populated on real rows. It is, on 13 rows, in the
    documented form. The share among research rows alone is **unmeasured**, and this receipt does not
    claim it.
- **F1 (medium, routed to SA-046): a dossier observation is dated in the future (2026-10-24).**
  - **Cause (code):** `EventIngestor` scans board meetings, and `find_qualifying_events` has no
    upper date bound (`event_ingestor.py:111`). It stamps the observation with the event's date
    (`event_ingestor.py:239`), so a meeting announced for 24 Oct becomes an observation dated
    24 Oct.
  - **Effect:** the forecast agents and chat read the dossier digest, and SA-046's Catalyst weights
    events by recency. A date 18 days ahead is wrong evidence for both.
  - It is an issue-time defect outside SA-038's scope. The cause, an illustrative example, a fix
    direction and an invariant test are on the [SA-046](../stories/SA-046.md) card. Which ticker,
    and how often, were not measured. The owner may promote it to a FIX story.

## Tests

New: `tests/unit/ops/test_milestones_judged_sa038.py`, 5 tests over the **real**
`config/milestones.yaml`. No check implementation is exercised: every check is forced to
`pending`, the worst case for the ladder.

1. No milestone is past its deadline at the first run (Wed 7 Oct 06:30 IST).
2. The real runner starts from production's state: every milestone, including the 7 deleted ones,
   last `critical` on 30 Sep. It sends no critical, and no notice names a deleted id. The saved
   state holds exactly the current ids.
3. The 7 judged ids are gone, and `ipo_p0_live_window_check` stays. Whoever closes IPO-0a deletes
   the entry and that line together.
4. Every `manual_confirmation` milestone has a deadline. Without one, it would warn every day for
   ever and could never lapse into a judgement.
5. Every re-dated entry opens `RE-DATED <date> by <story> (was <date>`, with was < re-dated <
   deadline and a stated reason.

**Do the tests detect a wrong registry?** A pytest plugin served each variant in place of the file
(`analysis_data/sa038/rv_registry_plugin.py`; mutants from `make_mutants.py`; output in
`mutants_final.txt`). The tracked file was not touched.

| Variant (from the final registry) | Result |
|---|---|
| Baseline registry (`a502cf7`) | 4 of 5 fail. Test 4 passes, because every old milestone had a deadline |
| Atlas entry re-added | 3 fail (1, 2, 3) |
| IPO deadline back to 2026-09-15 | 3 fail (1, 2, 5) |
| IPO re-date line removed | 1 fails (5) |
| IPO entry deleted | 2 fail (3, 5) |
| `ipo_verdicts_visible_gate` deadline removed | 1 fails (4) |
| IPO reason emptied | 1 fails (5) |
| Control: final registry through the plugin | 5 pass |

All 7 variants are caught.

- **Every test that reads the real registry:** `python -m pytest tests/unit/ops
  tests/unit/test_delivery_alerts.py tests/unit/shared/test_instrument_identity_sa008.py -q -p
  no:cacheprovider` gives **207 passed**.
- **Full suite, run 1** (07:59–08:09 IST, on the registry before the probe judgement):
  `python -m pytest tests -q -p no:cacheprovider` gave **4160 passed, 12 skipped, 1 failed**.
  `data/`, `logs/` and `outputs/` were unchanged (800 files, `bbf9c186…`).
  - The failure is the known Windows rename flake, not SA-038:
    `test_store_migration_sa009.py::test_rollback_never_merges_into_a_live_store_that_reappeared`,
    WinError 5 renaming `lineage.json.tmp` at `store_migration.py:163`.
  - SA-038 changes no code. Alone, the test passed 3 of 3. Its file passed 22/22 in 2 of 3 runs.
    SA-009 change_1's review recorded this line and routed it to the SA-031 card. Production runs
    on Linux.
- **Full suite, run 2** (on the final registry and the final test file, 10:46–10:53 IST, 6 min
  45 s): the same command gave **4161 passed, 12 skipped, 0 failed**. `data/`, `logs/` and
  `outputs/` were unchanged (800 files, `bbf9c186…` before and after). Output in ignored
  `analysis_data/sa038/full_suite2.out`.

## Documentation

- `config/milestones.yaml`: the registry change, plus a header note on how an entry is retired.
- KT §10 ([TECHNICAL_DESIGN.md](../../../TECHNICAL_DESIGN.md)): what a `manual_confirmation`
  milestone is, why it becomes a weekly critical, and how it is retired. PDF rebuilt (source
  `8f89c401…`); `check_kt_docs` errors `[]`.
- [TEAM_TESTING_GUIDE.md](../../../TEAM_TESTING_GUIDE.md):
  - new case **12-I** (the first morning after the deploy, and the Sunday heartbeat);
  - a stray blank line that split the section 12 table, so that 12-G and 12-H rendered as plain
    text, is removed;
  - SA-038 is added to the section's related-PI line.
- Cards:
  - [SA-012](../stories/SA-012.md) and [SA-014](../stories/SA-014.md): the hard-bind fold;
  - [SA-002](../stories/SA-002.md): the B2 milestone retired there;
  - [SA-046](../stories/SA-046.md): finding F1.
- The [SA-039 activation record](SA-039-activation-2026-09-26.md): its header now says `verified`.
- STATE (excluded from the manifest):
  - SA-038 `review_required`;
  - SA-039 `production_verification` `verified`;
  - a note on SA-002's pending check;
  - SA-009's restart check recorded as met.

## Manifest and digest

- **Review input:** [SA-038-manifest.json](SA-038-manifest.json), 10 files. The SHA-256 of its LF
  bytes is **`e3a251d5b63a7dfd18f99b2963efb3a0a1983ddae2a382114427548f3ad1a7c9`**, and
  `kt_manifest.py verify` gives 0 mismatches.
  - Excluded: STATE, HANDOFF, this receipt and `.claude/settings.local.json`, which is the owner's.
- **Diff digest:** **`22196d37a9cc077a015608fa1e4210ba9d964742f1861b3b4bed3a61ebfb1e25`**, 34,650
  bytes over 9 files.
  - **To rebuild it:** take every manifest path except the PDF, sorted. For a path tracked at
    `a502cf7`, run `git diff --no-color --no-ext-diff a502cf7 -- PATH`. For the new test, run
    `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`. Concatenate the outputs.
  - `analysis_data/sa038/diff_digest.py` does exactly this.

## Self-review

- **I1 (info).** A deleted entry gets no "resolved" notice; its alerts simply stop, because the
  engine only walks registry entries. Test case 12-I tells the tester to look for that absence.
- **I2 (info).** The re-date format is enforced by a test over the real file, not by the loader. A
  loader rule would turn a wording slip into a "registry broken" critical at 06:30, which is worse
  than a red test.
- **I3 (info).** `atlas_cutover_pending` and `atlas_cutover_prep` are now registered but unused by
  any entry. Deleting them would widen this story into code. Noted for SA-011 (E4 registry).
- **I4 (info).** Test 2 pins Wed 7 Oct. That is the first run after the judgement, not the deploy
  date. The only open milestone stays silent until 28 Oct.
- **I5 (process).** The F3 dossier criterion was written before the design fact behind it was known.
  It is met as written; the limit above says what it does not show.

## Rollout

A registry edit reaches production only on deploy (`registry_is_current` watches the file). This
card authorizes no deploy.

**Production verification, after an authorized deploy:** the next 06:30 `ops_watchdog` run sends no
`critical` for any of the 7 deleted ids, and the Sunday heartbeat lists only the two IPO milestones
and the invariants.

**Rollback:** revert the commit, which restores the entries and their weekly criticals.
