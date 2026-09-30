# SA-009 review receipt — inventory and reconcile prediction-store ownership

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
