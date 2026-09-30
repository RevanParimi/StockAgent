# SA-009 implementation receipt — inventory and reconcile prediction-store ownership

- **Story:** [SA-009](../stories/SA-009.md). Audit finding F12 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md).
- **Phase:** implementation, one conversation, 2026-09-30 about 06:46–11:58 IST, with a pause
  in the middle. It includes a
  same-conversation self-review, which is **not** the fresh-session review. STATE:
  `review_required`.
- **Baseline:** `f443cc7576f06a8ef9782d889aa0efe627abe783`, with a clean tree. At the owner's
  choice (about 06:55 IST, asked because SA-009 edits files SA-008 also changed), SA-008 was
  first committed as `02c43f6`, with its KT bump `f443cc7`. Both are local; nothing was pushed.
- **Production checks:** none was due. SA-039 P3 is Thu 1 Oct 09:30, and SA-007's silent-Thursday
  check is Thu 1 Oct 06:30. No production state was read, and nothing was pushed, deployed,
  configured or sent.
- **Review input:** [SA-009-manifest.json](SA-009-manifest.json). Its digest and the diff digest
  are under "Manifest and digests".

## What it does, in one example

SUZLON is managed as `renewable_energy`. The scheduled forecast and review use
`data/predictions/renewable_energy/SUZLON/`. The startup self-heal (`services/api/server.py`)
used a different rule. For every managed ticker it looked in `automobile/<TICKER>` for the
month's envelope, and when none was there it ran `generate_forecast(ticker)`, whose default
sector is `automobile`. So on the first deploy of each month, SUZLON got an automobile-graph
forecast, with the nine automobile dimensions and an automobile weight file, in
`automobile/SUZLON`. Its reviews never read that store, but every evaluator that walks the tree
does: the scorecard, the eval harness, learning evidence and analytics.

Now:
- the self-heal uses each managed entry's sector, so a restart checks and rebuilds
  `renewable_energy/SUZLON`;
- `store_inventory` reports `automobile/SUZLON` as a store whose data the automobile graph did
  produce (`confirmed` for its directory) but whose dimensions are wrong for its owner
  (`wrong_roster`). It reports the two stores' `SUZLON_2026-07` envelopes as conflicting
  duplicates;
- `store_migration plan` proposes to move `automobile/SUZLON` out of the tree, and `apply` moves
  it by one rename into `data/prediction_quarantine/<id>/stores/automobile/SUZLON/`. There it is
  still readable. `rollback` puts it back byte for byte.

## Measured evidence

- **Production, read-only, from the audit's capture** (2026-09-10 06:48 UTC; the raw summary is
  the ignored `analysis_data/audit_20260910/detail.json`). It found 38 stores for 23 tickers:
  - **15 tickers had two stores.** In each pair, `automobile/<TICKER>` held a weight file and 1–2
    envelopes but no feedback log, beside the managed sector's store, which held feedback,
    weights and envelopes;
  - **all 58 feedback logs declare `automobile`:** 22 under `automobile/` and 36 under other
    sectors;
  - **each directory's weight files share one roster:** automobile 9 dimensions, banking 6, IT 8,
    renewable 6, generic and insurance 8.

  The self-heal explains that shape. It writes an envelope and weights, and its backfill finds no
  forecast row for the days before the envelope, so no feedback log appears. That is inference
  from the code and the capture; the new tool has not run on the volume.
- **Local reproduction 1:** a July 30 copy of a predictions tree, `analysis_data/predictions`,
  whose provenance is not recorded; it is used only as realistic input. The inventory found:
  - 35 stores, and 13 tickers with two stores;
  - 12 conflicting duplicate envelopes, no duplicate graded day, and 13 wrong-roster stores;
  - sector status: 33 `confirmed`, 2 `directory_only`.

  The plan moves exactly the 13 `automobile/<TICKER>` copies, and each owner's store is present.
  It has no holds and no flags. The manifest digest is `e7fb4cb7…`, and the plan digest
  `789a2eae…`.
- **Local reproduction 2:** the dev tree `data/predictions`, run read-only. It has 85 stores, and
  82 are empty directories, created by reads through the `PredictionStore` constructor.
  `automobile/TCS` holds an automobile-roster envelope while TCS is managed as `it_sector`, and
  the plan moves that one store. Before and after the run the tree had 27 files with the same
  hash list, so the run changed nothing.

## The contract

**The owner rule** (`store_inventory.owner_of`). A ticker's history belongs to
`<managed sector>/<TICKER>`: the managed entry's sector, whether or not the ticker is enabled.
That is the store the scheduled monthly forecast and daily review write. These tickers have no
owner:
- one without a managed entry;
- one whose entry has no sector (the scheduler would default it to automobile; SA-009 does not act
  on a default);
- one with two entries that disagree.

The ticker map (`TICKER_SECTOR`) is evidence, never the owner.

**The inventory** (`core/intelligence/rl/stores/store_inventory.py`, new; read-only CLI). It
walks the tree itself. A top-level directory holding files named `<DIR>_*` is a legacy flat store;
any other top-level directory is a sector, whose subdirectories are stores. Per store it records:
- **identity:** path, ticker, file count, bytes, and a digest over every file's path, SHA-256 and
  size;
- **file kinds and cycles**, and any unreadable file;
- **sector evidence.** Each file's dimension roster is matched exactly against each graph's current
  `AGENT_WEIGHTS` keys. It becomes `files_by_roster`, per file, with `mixed` and `unrecognized`
  kept apart. The declared `sector` field of every JSON kind is recorded. The status is
  `confirmed`, `conflicting`, `directory_only`, `roster_only`, `missing` or `empty`; KT section 3
  gives the table;
- **ownership:** the owner's sector and graph, the store's role (`canonical`, `non_canonical`,
  `unowned`), `roster_vs_owner`, and whether the owner agrees with the ticker map;
- **schema markers:** SA-039 `learning_mode`, SA-003 `decision_gate` and row `data_gate`,
  SA-008 `instrument` and row `instrument`, row subscores, reforecast history, and the feedback
  entries' `graded_verdict`, agent scores and fired claims;
- **consumers:** which lookup rules reach the store (KT section 3's table).

The duplicates list covers tickers with more than one non-empty store, and envelope cycle ids and
graded days (ticker and date) seen more than once, each identical or conflicting. Content
equality is canonical-JSON equality of the parsed object. The manifest's digest excludes
`generated_at`.

**The quarantine** (`core/intelligence/rl/stores/store_migration.py`, new; operator CLI). It
has three commands:
- **`plan`** is read-only and described in KT section 3 and D6. Each item pins every file (path,
  SHA-256, size), the owner's store and whether it exists, and the evidence. The digest covers the
  items, the holds, the flags and the managed roster's SHA-256.
- **`apply`** refuses a quarantine root inside the predictions root, and the reverse. It refuses an
  approved digest other than the plan's, and a fresh plan that differs. Then it creates
  `<quarantine root>/<UTC time>-<digest12>/` exclusively and writes `lineage.json`, with every
  item pending. For each item it:
  1. re-hashes the store, and stops if anything differs;
  2. refuses an existing destination;
  3. renames the store into `stores/<store_id>` and re-hashes it there, recording `moved`, or
     `moved_changed` with the difference;
  4. rewrites the lineage.

  The remaining items become `not_attempted` if it stopped. The last step appends one line to
  `migrations.jsonl`.
- **`rollback`** returns, in reverse order, each moved store, and any pending one found in
  quarantine after a crash. It checks the quarantined bytes against the record first. It refuses a
  live path that exists again, and a quarantine whose bytes changed. Otherwise it renames the store
  back and re-hashes it. Refused items can be retried after the operator resolves them.

**The writers** (the same root cause):
- **`services/api/server.py` `_self_heal_rl`:** reads `get_active_tickers_with_sector()`, the
  scheduler's own list, and passes each entry's sector to the store, `generate_forecast` and
  `run_daily_review`;
- **`PredictionStore._own_sector`:** a feedback log, weight memory or ledger the store creates
  carries the store's sector. A file already on disk is read and rewritten with the sector it
  records. A flat store (no sector) keeps the schema default;
- **`daily_review`:** a missing or unreadable weight file is rebuilt from
  `get_sector_weights(sector)`, both on the live first init and in a paper review's memory, as
  `generate_forecast` already did.

## Acceptance criteria

- **No silent merge, deletion or guessed sector assignment.** Nothing is ever merged: rollback
  refuses a reappeared live store (tested). No code path deletes a store file; a store is renamed,
  never copied then removed. Ownership comes only from an explicit managed entry. Unmanaged
  duplicates, owner-versus-map conflicts, sectorless or conflicting entries, and several owner
  stores are held, never moved (tested). The writers now stamp the store's real sector instead of
  the `automobile` default, and they do not relabel old files (tested).
- **The manifest distinguishes missing metadata from a confirmed sector, and identifies
  conflicting duplicate forecast ids.** The status table, with `confirmed` requiring a matching
  roster, is tested on each case in the fixture. The default-prone `sector` fields are reported
  and never used (tested). Duplicate envelopes and graded days are marked identical or
  conflicting, across stores and within one store (tested).
- **Dry run and rerun produce deterministic plans; old data stays readable.** Two plans are equal,
  and a copy of the tree built elsewhere gives the same digest. The tree's bytes and directories
  are unchanged by inventory or plan. After apply, `PredictionStore(..., base_dir=<migration>/stores)`
  reads the same objects. After rollback the tree is byte-identical and reads the same objects
  (all tested).

**The card's evidence list.** The fixtures include:
- missing sector: `generic/NEWCO`, flat `LEGACYCO`, and the default-labelled logs;
- duplicate identical rows: `RBLBANK_2026-07` and `RBLBANK:2026-07-03`;
- conflicting duplicates: `SUZLON_2026-07`, `SUZLON:2026-07-01`, `ACME_2026-07`, and
  `TCS:2026-07-31` within one store;
- a wrong dimension roster: `automobile/SUZLON`, `it_sector/TCS` and
  `renewable_energy/INOXWIND`.

The dry run leaves source hashes unchanged, and rollback restores the same readable state.

**Independence of expectations.** The fixture (`tests/unit/intelligence/rl/store_tree_sa009.py`)
copies each graph's roster as literals. Every expected status, role, duplicate and plan item is
written from the fixture's design, not produced by the code. The real-wiring test takes its
expected roster from the banking settings module itself. The writer tests take theirs from
`banking_bfsi.config.settings.AGENT_WEIGHTS` and `settings.GENERIC_AGENT_WEIGHTS`.

## Decisions for the reviewer

- **D1. The owner is the managed entry's sector.** The live writers use it. The ticker map, the
  directory or a declared field would each guess. Consequence: a managed entry that names the
  wrong sector makes its own store the owner, so owner-versus-map disagreements are held for a
  person to decide.
- **D2. Evidence is the dimension roster, matched exactly** against today's `AGENT_WEIGHTS` of the
  five graphs, and compared with today's `get_graph_sector` of the directory. The local snapshot
  showed rows carry either the full roster or none, so exact matching loses nothing there. A
  roster from an older configuration reads `unrecognized` and is listed, never guessed. The
  `sector` fields of feedback logs, weight memory and ledgers are never evidence.
- **D3. Two separate questions.** `sector_status` asks whether the data agrees with its directory,
  and `roster_vs_owner` asks whether it agrees with the ticker's owner. `automobile/SUZLON` is
  `confirmed` and `wrong_roster`. That is honest provenance: the automobile graph produced it, and
  it belongs to the wrong owner.
- **D4. Forecast identities here are derived keys:** the cycle id for an envelope, ticker and date
  for a graded day. They are not issuance identities (SA-013). Archived envelopes are versions,
  not duplicates. Equality is field-sensitive, so a row written before a later field existed reads
  `conflicting`: conservative, and it asks for a look.
- **D5. "Copy/quarantine" is implemented as a move by one directory rename,** hashed before and
  after and reversible. A copy-then-delete would add a window with two live copies and a deletion
  path. The rename is atomic on one filesystem; the default root is a sibling under `data/`, and a
  cross-device root fails that item cleanly (`failed`, and the apply stops). The quarantine root
  sits beside the predictions root: inside `data/`, so the nightly backup keeps it, and outside
  every tree walk.
- **D6. The plan's scope.** It moves only non-empty stores of managed tickers that are not the
  owner's, including legacy flat ones. Two owner directories differing only in case (possible
  only on a case-sensitive volume) are held. Empty stores are ignored: reads create them, and they carry
  nothing. Owner stores that carry another graph's roster are flagged, because excluding those
  rows is SA-017's work.
- **D7. Apply's safeguards were designed against the SA-008 review's M1 and L1.** The digest pins
  every byte it moves. Each store is re-checked immediately before its rename, and the first
  difference stops the run. Each migration gets a new directory and one lineage file, so nothing
  is overwritten. A racing writer is detected (`refused_changed` or `moved_changed`), not
  prevented, so the rollout says to run in a job-free window.
- **D8. The writer fixes are included** because without the self-heal fix the next month's first
  deploy would recreate the copies the quarantine removes.
  - **Deploy effect:** a restart now checks non-automobile tickers' own stores, and backfills
    their missing review days. That is the self-heal's intended behaviour, already in place for
    automobile tickers, and it runs under the current `observe` and `record` modes. It no longer
    spends one automobile-graph analysis per non-automobile ticker per month on the wrong store.
  - **The paper-review weight fix settles the SA-039 reviewer's reproduction,** routed to SA-026.
    SA-026 keeps the single initialiser and the key check.
- **D9. Routed, not fixed.** These go to SA-026's `store_key`: the readers keyed by the graph
  sector (the orchestrator's learned-weight read, the agents' enhancement and dossier reads), the
  `automobile` defaults in manual CLIs and fallbacks, the flat `feedback-status` CLI, and the
  constructor's directory creation. Row-level lineage and cohort exclusion go to SA-017. Card
  notes were added to both.
- **D10. The manifest and plan carry no absolute path and no content.** `lineage.json` records the
  absolute predictions root, because rollback needs it. It lives on the volume and is never
  committed.

**An input for the SA-003 enforce decision (P3, Thu 1 Oct).** The review's F1 says "only a
restart's self-heal retries" a withheld month-start envelope. Until SA-009 is deployed, that is
true only for automobile tickers. For the others a restart writes an automobile-graph envelope
into `automobile/<TICKER>`, which their reviews never read. Recorded in HANDOFF step 0.

## Tests: commands, environment, results

Environment: Windows 11, the repository's `.stockai` venv (Python 3.13), pytest with the SA-005
hermetic boundary: no network, and no access to the checkout's `data/`.

- **New tests:** 35 in 3 files, plus the fixture module:
  - `test_store_inventory_sa009.py`: 14;
  - `test_store_migration_sa009.py`: 14;
  - `test_store_writers_sa009.py`: 7, including an end-to-end live review and a paper review
    through `run_daily_review`, and two self-heal runs through `_self_heal_rl`.
- **Focused:** `.stockai/Scripts/python.exe -m pytest tests/unit/intelligence/rl/test_store_inventory_sa009.py
  tests/unit/intelligence/rl/test_store_migration_sa009.py tests/unit/intelligence/rl/test_store_writers_sa009.py
  -q -p no:cacheprovider` → 35 passed (25 s).
- **Existing tests:** none was changed. The neighbouring files (`tests/integration/test_prediction_store.py`,
  the RL eval, shock-path, paper-lane, learning-mode, SA-003 and SA-008 review tests) run in the
  full suite. An earlier full run, before the last two self-review fixes, gave 4014 passed,
  12 skipped, 0 failed.
- **Full suite:** `.stockai/Scripts/python.exe -m pytest tests -q -p no:cacheprovider` on the final
  bytes → 4016 passed, 12 skipped, 0 failed (10 min 41 s; 3981 + the 35 new). `data/` is unchanged.
- **Mutations.** `analysis_data/sa009/mutate9.py` (ignored) applies 15 mutations, each
  re-introducing one defect, runs the three files, and restores the exact bytes (verified by blob
  id). Result: 15 of 15 caught (unmutated 35 passed before and after; sources restored byte-identical by blob id). The mutations:
  - M1: the old self-heal;
  - M2: the schema-default stamp;
  - M3: the automobile bootstrap;
  - M4: a directory name confirms;
  - M5: duplicates are never conflicting;
  - M6: the roster is judged against the directory, not the owner;
  - M7: flat stores are read as sectors;
  - M8: no per-store re-check;
  - M9: no fresh-plan check;
  - M10: a migration directory is reused;
  - M11: an owner-versus-map conflict is ignored;
  - M12: unmanaged stores are moved;
  - M13: rollback merges;
  - M14: rollback trusts a changed quarantine;
  - M15: malformed rows crash the inventory.
- **Self-review fixes:**
  - found by a test: file lists were sorted by `Path`, which ignores case on Windows, so the
    digests would have differed between a Windows checkout and the Linux volume. They now sort
    by the POSIX path string;
  - a file that parses but has the wrong inner types (rows that are not objects) crashed the
    whole inventory. It is now counted and carries no evidence (tested; M15);
  - two owner directories that differ only in case are held (tested on an edited manifest,
    because Windows cannot hold both).
- **Not exercised:** Linux and Python 3.11 (CI runs after a push); a cross-device quarantine root;
  any production data; the CLIs on the volume.

## Documentation

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - section 3: the storage row, and a new "Prediction-store ownership" part with the owner rule,
    the writers, the inventory with its status table, who reads which store, the quarantine and
    its limits;
  - section 5: the self-heal retry now covers each ticker's own store;
  - sections 1, 11 and 12: status lines;
  - the two new modules are code spans until the landing commit's KT bump, because
    `check_kt_docs` requires linked sources at the declared revision.
- **PDF** rebuilt from the KT.
- **ARCHITECTURE:** the learning paragraph and the current-versus-planned row.
- **TEAM_TESTING_GUIDE:**
  - 01-G (new): a restart rebuilds a missing envelope in the ticker's own sector;
  - 04-G (new): inventory, plan, apply and rollback on a test copy;
  - SA-009 added to both related-PI lines.
- **CODEBASE:** the stores tree line, the `prediction_store` row, two new module rows, and a
  paragraph.
- **Routed notes** on [SA-026](../stories/SA-026.md) and [SA-017](../stories/SA-017.md).
- `check_kt_docs` → errors `[]` (407 local links; PDF 32 pages, source `46afd5db…`).

## Rollout (owner, after the fresh review, commit and push)

1. **Push and deploy** in a job-free window. This carries the writer fixes, so no new copies are
   made. Check that the boot log is clean and `/health` is ok.
2. **Read-only on the volume:** `python -m core.intelligence.rl.stores.store_inventory --out
   /tmp/sa009_manifest.json` and `python -m core.intelligence.rl.stores.store_migration plan --out
   /tmp/sa009_plan.json`. The owner runs them (`railway ssh`), with `/tmp` outside the volume,
   and pastes the summary lines and the plan's items and holds. Expect the `automobile/<TICKER>`
   copies as items (there were 15 on 10 Sep), and possibly some holds.
3. **Decide:** the owner reviews the plan (items, holds, flags) and authorises the apply by the
   plan's digest. Nothing is applied without that authorisation.
4. **Apply** in a job-free window (00:10–06:20 IST), after the nightly 23:30 backup: `apply --plan
   /tmp/sa009_plan.json --approve <digest>`. Rerun the inventory: no `automobile/<TICKER>` copy,
   and the duplicate tickers are only the held ones.
5. **Verify:** the next scorecard lists each moved ticker once. Rollback is `rollback --migration
   data/prediction_quarantine/<id>` at any time.
6. **Later:** P3/F1 as above; SA-017 reads the manifest.

## Open limitations

- **The production tree has not been inventoried with this tool.** The measured production
  picture is the audit's 10 September capture.
- **A writer racing `apply` is detected, not prevented.** Run it in a job-free window.
- **Rosters are matched against today's configuration.** A graph whose dimensions changed
  historically reads `unrecognized` for its older files.
- **The routed readers** (D9) still read other stores, and the constructor still creates empty
  ones.
- **Old files keep their `automobile` labels.** SA-017 treats them as unknown lineage.

## Manifest and digests

- **Review input:** [SA-009-manifest.json](SA-009-manifest.json), 14 paths:
  - 5 code files (2 new: `core/intelligence/rl/stores/store_inventory.py` and
    `store_migration.py`);
  - 4 test files, all new: the three test files and the fixture module `store_tree_sa009.py`;
  - 5 documentation files, including the PDF.

  The SHA-256 of its LF bytes is
  **`72923d9179fce3b5ee4ac06d6413ddf06df6c8cfc69692b3283510aa05d05464`**, and
  `kt_manifest.py verify` gives 0 mismatches. The manifest lists exactly the files `git status`
  shows changed outside `docs/planning/`.
- **Excluded,** because they are written after the manifest or belong to another record:
  STATE.json, HANDOFF.md, this receipt, and the SA-017 and SA-026 cards (routed notes).
- **Full diff** against `f443cc7`:
  **`c931b6c79c83ecc5061a7433e40f6bb08af55d5c822cf91b70c723f11e1755db`**, 138,453 bytes over 13
  text files. The PDF is pinned by its blob, `453856ed…`.
- **To rebuild the diff:** take every manifest path except the PDF, sorted. For a path tracked at
  the baseline, run `git diff --no-color --no-ext-diff f443cc7 -- PATH`. For a new file, run
  `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`. Concatenate the bytes. The
  ignored `analysis_data/sa009/sa009_diff.py` does exactly this.
- **The landing commit's KT bump** must link the two new modules (they are code spans now) and
  re-read the sections that link `services/api/server.py` and `prediction_store.py`, which this
  story changes.
- **After the commit:** `verify --rev <commit>` compares against the commit instead.
