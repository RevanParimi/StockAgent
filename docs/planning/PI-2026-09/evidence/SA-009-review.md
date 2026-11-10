# SA-009 review receipt — inventory and reconcile prediction-store ownership

## Change 1 fresh-session review: ACCEPTED (2026-09-30)

- **What was reviewed:** change 1, which settles the first review's L1, L2 and L3 and adds its
  optional I3 guard. The implementation is in the [receipt](SA-009-implementation.md), section
  "Change 1".
  - `rollback` retries every store that is not back, and removes an empty live directory with
    `rmdir` first. It reports `rolled_back` only when every store is back with its recorded
    bytes.
  - The inventory's summary gains `roster_collisions`.
- **Context:** a fresh-session review in a new conversation, 2026-09-30 about 17:50–18:15 IST.
  - It is not the conversation that implemented change 1, and it did not read that chat.
  - It read the receipt's change-1 section, the diff and all of `store_migration.py`. It also
    read the `PredictionStore` paths that create directories.
- **SA-039:** no check was due. P3 is Thu 1 Oct 09:30.
- **Peers:** 30 other sessions. Every StockAgent session was idle at the start and before the
  bookkeeping. The one busy session belongs to another project.
- **Nothing** was committed, pushed, deployed, configured or sent. No production state was read.
- **Verdict: accepted.** There is no critical, high or medium finding and no code defect.
  - One low test gap (L1) predates change 1. It is routed to SA-031.
  - Two informational notes: I1 was fixed by a review edit to KT §3, and I2 is routed to SA-031.

### Review input verified

- **Manifest:** [SA-009-change1-manifest.json](SA-009-change1-manifest.json).
  - The SHA-256 of its LF bytes is
    `7f2a4a2a776339dc0cbc002858df32c778d799e1699b19d41a5bc9f8b3fc9964`, as the receipt states.
  - `kt_manifest.py verify` gave 9 files and 0 mismatches at the start, and again after the
    mutations. Each mutated source was restored and checked by SHA-256.
- **Diff:** rebuilt with the reviewer's own script (`rebuild_diff.py` in the session scratchpad).
  It gave 8 text files, 63,325 bytes and SHA-256
  `e3a0438699d9f87de5dee6e418eefd96352723c486cea3b0734ab397b8c609c9`, the receipt's digest. The
  PDF's blob is `eff03b88…`, as pinned.
- **Completeness:** `git status --porcelain -uall` lists exactly these:
  - the 9 manifest paths;
  - the 3 excluded bookkeeping files;
  - the manifest itself.

  HEAD is `e698c68`.

### Contract checked

- **What `rollback` can do to files.** It does only two things: `rmdir` an empty live directory,
  and rename a quarantined store back when its bytes equal the record. Every other branch only
  changes an item's status. So a retry can never merge, delete or overwrite data.
- **Which stores are retried.** `_NOT_BACK` holds every state whose store may still be in
  quarantine, or whose rollback was refused. Every state it leaves out is a live store:
  - `not_moved`, `not_attempted`, `refused_changed`, `refused_destination_exists` and `failed`
    never moved. A rename either happens or it does not;
  - `rolled_back`, `rolled_back_changed` and `found_live` are back.

  Every branch sets a new status, so after a full run no item reads `moved` or `pending`.
- **The outcome.** It is `rolled_back` exactly when no item is in `_NOT_BACK` or reads
  `rolled_back_changed`. So it means that every store is at its live path, and every restored
  store has its recorded bytes.
- **The empty directory.** A read leaves exactly one empty directory, which `rmdir` removes:
  - `PredictionStore.__init__` creates only the store's own directory (`prediction_store.py:121`);
  - `archive_envelope` creates `archived_envelopes/` only after it finds an envelope;
  - the ledger's `mkdir` runs on write.

  `rmdir` is not recursive, so it refuses a directory holding only an empty subdirectory (Q4).
- **`found_live`** needs `list_store_files(src)` to equal the recorded bytes (`after_files`, else
  `files`). A `pending` item whose store is live is checked first and stays `not_moved`.
- **`roster_collisions`** is in the manifest's summary. The plan's digest covers only the items,
  holds, flags and managed roster.
  - So a plan made on the deployed `650bb98c` code keeps its digest after change 1 deploys (Q6).
  - The manifest's digest changes, and nothing consumes it yet (C4).
- **A race (inference, not reproduced).** Suppose a writer recreates the live directory between
  the `rmdir` and the rename.
  - On Linux, the rename replaces an empty directory.
  - If the directory holds a file, the rename raises. The item keeps its recorded status, and
    the next run retries it.
  - This is the racing-writer case that D7 accepts. Run rollback in a job-free window.

### Independent adversarial examples

The probes are `probes/test_c1_review_probes.py` in the session scratchpad; they are not
tracked. They use the real `PredictionStore` and the SA-009 fixture tree.
- The expected results come from the contract.
- Each is measured against the tree before the apply (`fx.tree_state`), never against the
  changed code's own output.

**8 of 8 passed**, on 5 of 5 repeated runs.

| Probe | Example | Expected and observed |
|---|---|---|
| Q1 | A rollback crashes after renaming `automobile/SUZLON` back, before recording it. Rollback runs again | Change 1: `found_live`, run `rolled_back`, tree byte-identical. The same probe on `e698c68`: `refused_quarantine_missing` and `partial` on every retry |
| Q2 | A job writes a file into SUZLON right after it is renamed back | `rolled_back_changed` and run `partial`. A retry leaves it alone and stays `partial`, and the CLI exits 1. The job's file is kept |
| Q3 | A writer's file blocks the rollback. The operator moves the file away and leaves the empty directory | The first run is `refused_live_path_exists`. The retry removes the empty directory and restores the store; tree byte-identical |
| Q4 | The live path holds only an empty `archived_envelopes/` | Refused. Nothing under it is removed, and the store stays in quarantine |
| Q5 | The receipt's example: a quarantined file changed, and a dashboard read recreated the empty directory | `partial`, and the empty directory is left alone while the store is refused. After the file is put back: `rolled_back`, CLI exit 0, tree byte-identical |
| Q6 | The same fixture tree through the inventory at `e698c68` and now | The manifest digests differ (the new field). The store records and the plan digest are equal |
| Q7 | The real `default_rosters()` with `renewable_energy` routed to the generic graph, as with its toggle off | `roster_collisions` names `["generic", "renewable_energy"]` |

### Decisions

- **C1 upheld** (Q3, Q4, mutation RB).
- **C2 upheld** (Q2).
  - The consequence: after one `rolled_back_changed` store, that migration never reports
    `rolled_back`, and its CLI exits 1 for good. The store is live, and `lineage.json` names it.
  - That is honest, because the tree is not the recorded one.
- **C3 upheld** (Q1, and the implementer's hand-moved test).
- **C4 upheld** (Q6).

### Tests

- **The 10 new tests** turn the first review's probes R2, R3, R5, R8, R9 and R10 into repository
  tests, as the change's scope asked.
  - Their expected results come from the tree before the apply and the fixture's design, not
    from the changed code.
  - They use temporary directories only: no network, SMTP or push.
- **The reviewer's mutations** (`mutate_review.py` in the scratchpad) were **4 of 6 caught**:
  - RB, `rmtree` in place of `rmdir`: caught by the never-merges test (1 failing);
  - RC, `refused_quarantine_missing` never retried: 1 failing;
  - RE, every roster reported as a collision: 1 failing;
  - RF, the CLI exits 0 on `partial`: 1 failing;
  - **RA survived:** `rolled_back_changed` no longer keeps the run `partial`. Probe Q2 fails on
    it. This is L1;
  - **RD survived:** the `restored` count in `migrations.jsonl` ignores `found_live`. It is
    telemetry only, and `lineage.json` is the record. It goes with L1.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (tests; predates change 1) | `store_migration.py:347-348` | No repository test produces `rolled_back_changed`, so the rule that it keeps the run `partial` (C2) is not pinned. Mutation RA passes all 45 SA-009 tests, and probe Q2 fails on it. At `e698c68` the in-run rule (`if restored != expected: outcome = "partial"`) was untested too. Q2 shows the behaviour is right | Routed to [SA-031](../stories/SA-031.md) as a card note: add Q2 as a repository test. Pinning the `restored` count (RD) is optional |
| I1 | Info (docs) | KT §3, the rollback bullets | The KT did not say that a store already back with its recorded bytes counts as restored (`found_live`). Nor did it say that this recovers a rollback interrupted before its record (Q1). Before change 1, that store read `refused_quarantine_missing` on every retry | **Fixed in review:** one sentence in KT §3 |
| I2 | Info (Windows only) | `store_migration.py:163`, `_write_lineage` | One `PermissionError: [WinError 5]` from `os.replace`, in probe Q2, while the full suite ran alongside. It was clean on 5 of 5 runs alone. This is the known Windows rename flake; production runs on Linux. Q1 shows the next run recovers | Routed to SA-031's `replace_with_retry` check (card note) |

No code defect was found.

### Commands and results

Environment: Windows 11, `.stockai` venv (Python 3.13), repository root.

| Check | Command | Result |
|---|---|---|
| Manifest | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-009-change1-manifest.json` | 9 files, 0 mismatches, `7f2a4a2a…`, at the start and after the mutations |
| Diff | the reviewer's `rebuild_diff.py` | `e3a04386…`, 63,325 bytes, 8 text files; PDF blob `eff03b88…`; no unlisted change |
| Focused | `python -m pytest -q -p no:cacheprovider` on the 3 SA-009 test files | 45 passed (17 s) |
| Full suite | `python -m pytest tests -q -p no:cacheprovider` | **4026 passed, 12 skipped, 0 failed** (5 min 16 s, about 17:54–17:59 IST), the implementer's count. `data/`, `logs/` and `outputs/` are unchanged: 800 files, the same digest before and after |
| Probes | `python -m pytest <scratchpad>/probes/test_c1_review_probes.py --rootdir <scratchpad>/probes` (its conftest adds the repository paths and `tests.hermetic`) | 8 passed, on 5 of 5 repeated runs. One earlier run beside the full suite hit I2 |
| Mutations | `mutate_review.py` | 4 of 6 caught (RA and RD survived) |
| RA against Q2 | `mutate_probe_ra.py` | Q2 fails on RA (`'rolled_back' == 'partial'`); the source was restored (`fb0d625a…`) |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT check | `python scripts/docs/check_kt_docs.py` | Before the edits: errors `[]`, 415 links, 33 pages, source `11199632…`, the manifest's KT. After the edits and `build_kt_pdf.py`: errors `[]`, 415 links, 33 pages, source `e90092fb…`, PDF blob `e7af1487…` |

**Not exercised:**
- Linux and Python 3.11 (CI runs after a push);
- a real second process racing `rollback`;
- a quarantine root on another device;
- any production data. The CLIs have not run on the volume.

### Review edits (documentation only)

- **The KT:**
  - the status wording in §1, §3, §11 and §12 now reads "accepted …, not yet committed";
  - §3 gains the `found_live` sentence (I1).
  - The PDF was rebuilt.
- **Guide 04-G:** the status wording.
- **The [SA-031](../stories/SA-031.md) card:** a routed note for L1 and I2.
- **Manifest check:** `verify SA-009-change1-manifest.json` now mismatches exactly the KT, the
  PDF and the guide. No code or test file was changed.

### Acceptance and what remains

- **Change 1's scope: met.**
  - Rollback re-attempts refused stores (the R3 test, Q5).
  - The run's status is derived from every item (R3, Q2).
  - An empty live directory is treated as absent (the R2 test, Q3, Q5).
  - Tests from R2, R3, R5, R8, R9 and R10 are in the repository.
  - The I3 guard works through the real wiring (Q7).
  - KT §3's rollback caveat is replaced by the behaviour.
- **Reviewed revision:** the uncommitted working tree on `e698c68`, pinned by input `7f2a4a2a…`
  and diff `e3a04386…`, plus the documentation-only review edits.
- **Next:**
  - **Commit and push** need the owner's word, in a job-free window. The landing commit's KT
    bump declares the change-1 commit, because `store_migration.py` and `store_inventory.py`
    changed after `313e3f6`.
  - **Production:** change 1 has no effect until a rollback runs. SA-009's
    `production_verification` stays `pending_observation`.
  - **The owner's rollout is unchanged:** inventory and plan read-only, then apply by digest. A
    plan made before change 1 deploys keeps its digest (Q6). Once change 1 is deployed, the
    "until change 1" steps (remove an empty live directory by hand, and don't trust a later
    `rolled_back`) are no longer needed. After any `partial`, `lineage.json` still gives each
    store's state.
- **Next story:** SA-010, in a new conversation, after P3 (Thu 1 Oct 09:30) and the SA-003
  enforce decision. SA-008 change 1 stays open. It must come before any `successors` record.

## Fresh-session review: ACCEPTED (2026-09-30), with change 1 to follow

- **What was reviewed:** SA-009 as the [implementation receipt](SA-009-implementation.md)
  describes it. That covers:
  - the owner rule;
  - the three writer fixes: the startup self-heal, the store's own-sector stamp, and the daily
    review's weight bootstrap;
  - the read-only store inventory;
  - the quarantine's `plan`, `apply` and `rollback`.
- **Context:** a fresh-session review in a new conversation, 2026-09-30 about 12:25–12:55 IST.
  It is not the conversation that implemented SA-009. It read the story card, the receipt, the
  full diff, and the readers and writers the owner rule depends on. It did not read the
  implementing chat.
- **SA-039:** no check was due. P3 is Thu 1 Oct 09:30.
- **Peers:** 28 other sessions. All were idle at the start and before the bookkeeping.
- **Nothing** was committed, pushed, deployed, configured or sent. No production state was read.
- **Verdict: accepted.** The owner rule matches every live writer, and the inventory never
  confirms a sector from a directory name. The quarantine moves only strays of managed tickers
  and holds everything that needs a decision. A rollback after a complete apply restores the
  tree byte for byte. There is no critical, high or medium finding.
  - **Three low findings** (L1–L3) concern `rollback`'s retry path and missing tests. They go to
    **SA-009 change 1**. It is recommended before a production rollback is ever needed. It does
    not block the production apply.
  - **Four informational notes** (I1–I4) are routed or become rollout steps.

### Review input verified

- **Manifest:** [SA-009-manifest.json](SA-009-manifest.json). The SHA-256 of its LF bytes is
  `72923d9179fce3b5ee4ac06d6413ddf06df6c8cfc69692b3283510aa05d05464`, as the receipt states.
  `kt_manifest.py verify` gave 14 files and 0 mismatches at the start. At the end it mismatches
  exactly the 4 documents this review edited. Every code and test byte is as reviewed, and the
  mutations restored each source by blob id.
- **Diff:** rebuilt with the reviewer's own script (`rev_diff.py` in the session scratchpad, not
  `analysis_data/sa009/sa009_diff.py`). It gave 13 text files, 138,453 bytes and SHA-256
  `c931b6c79c83ecc5061a7433e40f6bb08af55d5c822cf91b70c723f11e1755db`, the receipt's digest. The
  PDF's blob is `453856ed…`, as pinned.
- **Completeness:** `git status` outside `docs/planning/` lists exactly the 14 manifest paths.
  The baseline `f443cc7` is HEAD.

## Contract checked

**The owner rule against the real writers.** `owner_of` takes the managed entry's sector. Every
scheduled writer uses that same value:
- the monthly forecast and the daily review, through `get_active_tickers_with_sector()` in
  `scheduler.py`;
- the self-heal, now also through `get_active_tickers_with_sector()`;
- the pre-open check, the event ingest and the RL monitor.

`load_managed` reads `data/managed_tickers.json` as `log_buffer.load_managed_tickers()` does. The
only differences are these:
- `load_managed` does not bootstrap a missing file. The consequence is that every ticker is
  unowned and nothing moves;
- `owner_of` strips whitespace from the sector, and the writers do not. The add route
  (`ui_data.py`) only writes sectors from its fixed list, so no stored sector has whitespace.

A sectorless entry makes the writers default to `automobile`. `owner_of` gives it no owner and
the plan holds it (R8).

**Readers.** The following were checked against KT section 3's table:
- the orchestrator's learned-weight read (`base_orchestrator.py:313`) only loads. The
  constructor's `mkdir` leaves an empty directory, which the plan ignores;
- the bundle builder's and the base agent's `automobile` fallbacks apply only when no sector is
  passed;
- the manual `generate-envelope` endpoint defaults to `automobile`, but the UI never calls it;
- the evaluators' walks (`scorecard`, `learning_evidence`, `harness`) list only
  `<dir>/<dir>` pairs under `data/predictions`, so the sibling quarantine is outside them;
- the backup's `rglob` over `data/` includes the quarantine (D5);
- `universe.py` walks only the predictions root.

**Other assumptions checked.**
- **Rosters.** The fixture's literal rosters equal `default_rosters()` for all five graphs. They
  are five distinct sets while the four native sectors are enabled, which is the committed
  `config/sector_toggles.json` that the Dockerfile copies (I3).
- **Resolution is pure.** `SectorRegistry.resolve` and `get_graph_sector` only look things up.
  The default wiring makes no call and writes nothing.
- **Sector labels.** Every `sector` field is a plain `str` with the default `automobile`, so the
  stamp cannot fail validation.
- **One reader uses the stamped label** (`harness.py:260`; I2).

## Independent adversarial examples

Reviewer probes, written by hand outside the repository (`probes/test_sa009_review_probes.py` in
the session scratchpad). They ran under the repository's hermetic conftest, with the **real
default wiring**: rosters from each sector's settings, the real ticker map and the real graph
router, and no injected keyword arguments. Expected values come from the story's contract, not
from the code's outputs.

| # | Example | Expected | Observed |
|---|---|---|---|
| R1 | The audit's shape. `renewable_energy/SUZLON` holds a renewable envelope, a log labelled `automobile` and renewable weights. `automobile/SUZLON` holds what the old self-heal made: an automobile envelope and weights from `settings.AGENT_WEIGHTS`. MARUTI is canonical. Run the inventory, the plan, `apply` to the default root, the evaluator walks, then `rollback` | The copy is `confirmed` and `wrong_roster`, and it is `non_canonical`. The owner is `confirmed`, `match` and `canonical`, and its default label is reported. `SUZLON_2026-07` conflicts. The plan moves only the copy, with no holds or flags. Inventory and plan write nothing. After `apply`, the scorecard and learning-evidence walks list SUZLON once, under `renewable_energy`. The quarantine opens with `PredictionStore`. `rollback` gives a byte-identical tree | Passed |
| R2 | After `apply`, one read constructs `PredictionStore("SUZLON", "automobile")`, which creates an empty live directory. Then `rollback` | A restore, or a refusal that a retry resolves | `partial`, with `refused_live_path_exists`. After `rmdir` of the empty directory, a retry gives `rolled_back` and a byte-identical tree. **L2** |
| R3 | A quarantined file changes, and `rollback` is refused. The operator restores the exact bytes and retries | The retry restores the store, or it reports that it did not | The retry skips the item, and the store stays in quarantine. Yet it reports **`status: rolled_back`**, and the CLI exits 0. **L1** |
| R4 | Between `plan` and `apply`, the 16:30 review appends a graded day to the owner's store and a new month's envelope lands there | The plan pins only what it moves, so `apply` proceeds | Passed (`applied`) |
| R5 | A tampered plan file: an extra item for the owner's store, with the digest field left as it was | Only the fresh plan's items move | Passed. The owner's store is untouched |
| R6 | HDFCBANK is unmanaged but in the ticker map, with `banking_bfsi/` and `automobile/` stores | Held, and no owner guessed from the map | Passed (`unmanaged_duplicate`) |
| R7 | The owner's store is absent, and only `automobile/SUZLON` exists | Proposed for quarantine, with the absence shown | Passed. The item has `owner_store_present: false` (I4) |
| R8 | The managed entry has no sector: missing, `""` or `"   "` (3 cases). Once with two stores, once with one | Held, never given the scheduler's `automobile` default | Passed |
| R9 | Two managed entries for SUZLON disagree (`renewable_energy`, and `"suzlon "` with `automobile`) | Held | Passed (`managed_conflict_duplicate`) |
| R10 | An automobile-roster envelope in `automobile/FOO` whose `sector` field says `banking_bfsi` | Not `confirmed` | Passed (`conflicting`) |

**Would the tests fail for the original defect?** The review ran its own mutations, separate from
the implementer's 15 (`mutate_review.py` in the session scratchpad). Each one rewrites one
source file and runs the three SA-009 test files. It then restores the file's exact bytes and
checks the blob id against the manifest:

| Mutation | Result |
|---|---|
| RM1: `services/api/server.py` as at the baseline. This is the original defect: the self-heal uses `automobile/<TICKER>` | **Caught** (the self-heal test) |
| RM2: `prediction_store.py` as at the baseline (the schema-default stamp) | **Caught** |
| RM3: `daily_review.py` as at the baseline (the automobile bootstrap) | **Caught** |
| RM6: `rollback` no longer treats `pending` items (crash recovery) | **Caught** |
| RM4: `apply` moves the plan file's items, not the fresh plan's | Survived. R5 covers it (L3) |
| RM5: `_sector_status` ignores a declared sector that differs from the directory | Survived. R10 covers it (L3) |
| RM7: conflicting managed entries: the first sector wins (a guess) | Survived. R9 covers it (L3) |
| RM8: a sectorless managed entry gets `automobile` (the scheduler's default) | Survived. R8 covers it (L3) |

Unmutated, the 35 tests pass, and every source was restored byte-identical (blob ids checked).
The three pre-SA-009 writers (RM1–RM3) each fail a test. The four survivors are rules the code
gets right but no repository test pins.

**Mocked boundaries.** The writer tests patch `generate_forecast` and `run_daily_review` at the
module attributes the self-heal imports inside the function, so the patches take effect. The
review tests reuse the shock-path and paper-lane fixtures, which stub prices, LLMs and the
feedback agent. Every test ran under the SA-005 hermetic boundary: no network, and no access to
the checkout's `data/`.

## Findings

| ID | Severity | Location | Finding | Disposition |
|---|---|---|---|---|
| L1 | Low (confirmed, R3) | `core/intelligence/rl/stores/store_migration.py:288-290, 322` | `rollback` retries only items in `moved`, `moved_changed`, `pending` or `refused_live_path_exists`. An item refused as `refused_quarantine_changed` or `refused_quarantine_missing` is skipped on every later run. The lineage `status` starts as `rolled_back` and only a failure seen in this run lowers it. So after the operator repairs the quarantine and retries, the store stays quarantined while the run reports `rolled_back` and the CLI exits 0. The first run did report `partial`, and the item's own status in `lineage.json` stays accurate. No data is lost. The receipt's "Refused items can be retried after the operator resolves them" holds only for `refused_live_path_exists`. | **SA-009 change 1:** re-attempt `refused_quarantine_*` items, and derive the run's status from the items: `rolled_back` only when no item is left in quarantine. Add R3 as a test. Until then, after any `partial` rollback, read each item's status in `lineage.json` rather than the summary. |
| L2 | Low (confirmed, R2) | `store_migration.py:311` | A live path that exists again is refused even when it is an empty directory. Any `PredictionStore` construction for that store creates one: the `automobile_default` callers in KT section 3, or `run_schedule feedback-status` for a flat store. Rollback then needs a manual `rmdir` and a retry. The receipt's rollout says "rollback … at any time". | **SA-009 change 1:** treat an empty live directory as absent. Remove it, then rename. That is neither a merge nor a deletion of data. Add R2 as a test. Until then the rollout's rollback step says: remove an empty live directory, then run rollback again. |
| L3 | Low (test gap; the behaviour was verified by R8–R10) | `tests/unit/intelligence/rl/test_store_*_sa009.py` | No repository test pins three rules: the hold for a managed entry with no sector (`managed_without_sector`), the hold for conflicting entries (`managed_conflict`), and the declared-sector conflict rule in `_sector_status`. The receipt marks the first two "(tested)". The reviewer mutations RM5, RM7 and RM8 show what the suite misses (table above). The code is correct. | **SA-009 change 1:** add R8, R9 and R10 as tests, and a test that `apply` moves the fresh plan's items, not the file's (R5; RM4). |
| I1 | Info (pre-existing, widened by D8) | `services/api/server.py:183-197`; `core/intelligence/rl/agents/weight_adapter.py:211` | The self-heal backfills every trading day of the month not yet in the log, yesterday included. A restart before 16:30 grades yesterday, and the 16:30 job grades it again. The feedback entry is replaced, but the weight adapter runs again: there is no per-date guard. The checkpoint limits this to one restart per ticker per month. It applied to about 5 automobile tickers before SA-009 and applies to all 20 after. In `observe` (production today) it only logs a second proposal and spends one extra review's LLM calls. In `adapt` it would apply two updates for one graded day. | **Routed to [SA-015](../stories/SA-015.md)** (idempotent adaptive updates; card note added). It matters before learning leaves `observe`. |
| I2 | Info | `core/intelligence/rl/eval/harness.py:260` | The eval harness groups `per_sector` by the log's declared `sector`, the label D2 calls "never evidence". Before SA-009 every log said `automobile`, so the whole breakdown fell into one bucket. New logs now carry the real sector and old ones keep `automobile`, so a report spanning the change mixes both. It is an improvement, but the receipt does not list this consumer. | **Routed to [SA-017](../stories/SA-017.md)** (row lineage; card note added): key `per_sector` by the store's owner sector, or exclude default-labelled logs. |
| I3 | Info | `store_inventory.py:170-174` | `default_rosters()` goes through `get_sector_weights`, which routes by the runtime toggle. If a native sector were switched off, its roster would become the generic one, and its real files would read `unrecognized`. Today all four native sectors are enabled in the shipped config. Only evidence and flags would change, never which stores move. | No action now. Change 1 may add an optional guard: the manifest warns when two graphs share a roster. |
| I4 | Info (R7) | `store_migration.py:121-122` | An item whose owner store is absent is still proposed for quarantine. After the apply, the ticker has no live history until its next forecast. The plan item shows `owner_store_present: false`, but the CLI's summary line counts only items, holds and flags. | **Rollout step 3:** before approving the digest, check `owner_store_present` on every item. Any `false` item is a decision for the owner. |

## Decisions D1–D10

- **D1** upheld. It matches every scheduled writer (above). Held disagreements were verified by R6
  and R9.
- **D2** upheld, with I3 noted.
- **D3** upheld. `automobile/SUZLON` is `confirmed` and `wrong_roster` under the real wiring (R1).
- **D4** upheld.
- **D5** upheld. The default quarantine root is `data/prediction_quarantine`, on the same volume
  as `data/predictions`, so the rename is atomic in production.
- **D6** upheld, with I4 added to the rollout.
- **D7** upheld. The re-check before each rename and the digest are verified by the implementer's
  tests. R4 shows that a normal write to the owner's store between plan and apply does not
  invalidate the plan. R5 shows that the file's items are never trusted.
- **D8** upheld, with I1 routed.
- **D9** upheld.
- **D10** upheld. The manifest and plan carry no absolute path, as tested.

## Commands, environment and results

Windows 11, Python 3.13 (`.stockai` venv), hermetic suite (`tests/hermetic.py`).

```text
kt_manifest.py verify SA-009-manifest.json     -> 14 files, 0 mismatches, 72923d91… (start; and after
                                                  the tests and mutations, before the review
                                                  edits); at the end exactly the 4 review-edited
                                                  docs
reviewer's rev_diff.py (own script)            -> 13 files, 138,453 B, c931b6c7…; PDF blob 453856ed
pytest -q -p no:cacheprovider <3 SA-009 files> -> 35 passed (34 s)
pytest -q -p no:cacheprovider tests            -> 4016 passed, 12 skipped, 0 failed (12 min 08 s);
                                                  data/ unchanged (814 entries, same digest
                                                  before and after)
reviewer probes (probes/, real wiring)         -> 12 passed (R1–R10; R8 has 3 cases); R2 and R3
                                                  show L2 and L1
reviewer mutations (8, mutate_review.py)       -> 4 caught (RM1-RM3 = the three pre-SA-009
                                                  writers, RM6); 4 survived (RM4, RM5, RM7, RM8 =
                                                  L3); sources restored by blob id
check_kt_docs.py (after the review edits)      -> errors [] (409 links; PDF 33 pages, source
                                                  69f30076…)
```

**Not exercised:** Linux and Python 3.11 (CI runs after a push); a cross-device quarantine root;
a real second process racing `apply`; any production data. The CLIs have not run on the volume.

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| No silent merge, deletion or guessed sector assignment | **Met.** Nothing merges: `rollback` refuses a reappeared live path, which R2 showed even for an empty one. Nothing deletes: a store moves by one rename. Nothing is guessed: R6, R8 and R9 hold, and the writers stamp only the store's own sector (the implementer's tests). |
| The manifest distinguishes missing metadata from a confirmed sector, and identifies conflicting duplicate forecast ids | **Met.** `directory_only`, `missing` and `empty` are kept apart from `confirmed`, which needs a matching roster. Duplicate envelopes and graded days are marked identical or conflicting. R1 checked this with the real rosters. |
| Dry run and rerun give deterministic plans, and old data stays readable | **Met.** Two plans are equal, the tree is unchanged by them, and the quarantine is readable with `PredictionStore`. A rollback after a complete apply is byte-identical (R1; the implementer's tests). |
| Fixtures: missing sector, duplicate identical rows, conflicting duplicates, a wrong dimension roster | **Met** (the implementer's fixture; R8 adds the managed-entry cases, L3). |
| The dry run leaves source hashes unchanged, and rollback restores the same readable state | **Met** for a complete apply. Retry after a refusal: L1 and L2. |
| Hard review: every authority assumption checked against actual readers and writers; a directory name alone never certifies provenance | **Met** (Contract checked; R1, R10). |
| Documentation | **Met.** KT sections 1, 3, 5, 11 and 12, ARCHITECTURE, guide 01-G and 04-G, and CODEBASE describe the reviewed behaviour. The PDF matched its source before the review edits and was rebuilt after them. |

## Review edits (documentation only)

- **Status wording** now reads "accepted 2026-09-30, not yet committed" in:
  - the KT: section 1's PI-target row, the section 3 heading, section 11's sector-routing row and
    section 12;
  - ARCHITECTURE: the learning paragraph and the current-versus-planned row;
  - TEAM_TESTING_GUIDE: 01-G and 04-G.
- **KT section 3's `rollback` bullet** now states L1 and L2 until change 1.
- **The PDF** was rebuilt (33 pages, source `69f30076…`).
- **Before the edits:** the pre-edit KT bytes are the manifest's (`46afd5db…`). That is the source
  digest the implementer's `check_kt_docs` recorded for the PDF, and the PDF blob matched the
  manifest. The reviewer did not run `check_kt_docs` before editing, because the command
  classifier was failing at the time.
- **Manifest check:** `kt_manifest.py verify SA-009-manifest.json` now mismatches exactly those 4
  files: the KT, the PDF, ARCHITECTURE and TEAM_TESTING_GUIDE. No code or test file was changed.
- **Routed card notes** were added on [SA-015](../stories/SA-015.md) (I1) and
  [SA-017](../stories/SA-017.md) (I2).

## Production verification and follow-up state

- **`production_verification`: `pending_deployment`.** SA-009 is not committed. Commit and push
  need the owner's word, in a job-free window (00:10–06:20 IST is safest). The landing commit's KT
  bump links `store_inventory.py` and `store_migration.py`, which are code spans until then.
- **Rollout** stays as in the receipt's "Rollout" section, with these additions:
  - **step 3 (I4):** before approving the digest, check that every item has
    `owner_store_present: true`, or decide each `false` item;
  - **step 5 (L1, L2), until change 1:** a rollback that reports `partial` needs a look at each
    item in `lineage.json`. Remove an empty live directory, then run rollback again. A store
    refused as `refused_quarantine_changed` is not re-attempted, even when a later run reports
    `rolled_back`.
- **After deploy:** the first restart of each month backfills yesterday for all 20 tickers, and
  the 16:30 job grades it again (I1). This is inert in `observe`. SA-015 owns the fix before
  learning leaves `observe`.
- **SA-009 change 1** (L1, L2, L3, and the optional I3 guard) is recorded in STATE. It is
  implemented in its own conversation and needs its own fresh review. It is not required before
  the production apply.
- **Routed:** I1 to SA-015 and I2 to SA-017, as card notes.
- **The SA-003 enforce decision at P3 (Thu 1 Oct):** SA-009 is accepted but not deployed. The F1
  caveat in HANDOFF step 0 stands until it deploys: a restart retries only automobile tickers.
- **Next ready story** by STATE order: **SA-010**. Start it in a new conversation, after any due
  production check. P3 is Thu 1 Oct 09:30.
