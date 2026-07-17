# Wave E — Dead-Code Deletion (Wave-2 docket) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the ~559-file / ~24.7K-LOC dead-code docket (AUD-026/027/029/031/032/033/034/035/037/079/080/095) and merge the 8 duplicate test pairs (AUD-081), with zero behavior change on any live path.

**Architecture:** Re-point the handful of live imports that currently route through migration shims (prompt shims, core.sectors agent shims), surgically remove the two dormant dispatch branches that keep dead trees import-reachable (registry `tier=core` branch; the shell-only LangGraph node factories), then delete whole trees. The live legacy fallback (`_run_via_graph` via `make_dispatch_fn`/`make_run_agent_node`, `UNIFIED_ANALYST_FALLBACK_LEGACY=True`) is **kept intact** — AUD-095's "dead DAG" is only the standalone compiled-graph side (sector `graph.py` shells + `make_resolve_ticker_node`/`make_input_rail_node`/`make_aggregate_node`).

**Tech Stack:** Python 3.12, pytest, git. No new dependencies.

## Global Constraints

- Baseline suite on main at ba5f393: **2234 passed / 12 skipped**, known fails = AUD-022 stale-mock family + `test_find_qualifying_events_unparseable_date_skipped`. Wave E must not add a failure; it MAY remove known fails (duplicate-copy merges).
- Deletions must be `git rm` only (reversible); never touch `data/`, `config/`, `.env`.
- Dockerfile COPY set (core/, services/, src/backend/→backend/, scripts/, main.py, config.yaml, config/, prototypes) must remain valid — every COPY source dir still exists after deletion.
- Every deleted file must have zero importers outside the deletion set at time of deletion (grep-verified in the task).
- Keep LIVE: `core/config/prompts/shared/` (6 RL importers), `src/backend/sectors/{automobile,banking_bfsi,it_sector,renewable_energy,generic}` agents+prompts (legacy fallback pool), `registry.py`, `graphs/{nodes,state,rails}.py` post-surgery, `services/clients/{llm_client,tavily_fetcher}.py`.
- Public-repo rule: commit messages and ledger text carry no prod endpoint/cash specifics.

---

### Task 1: Branch + baseline

**Files:** none (setup)

- [ ] **Step 1:** `git checkout -b audit-wave-e-deletions` (work in-repo, not a worktree — OneDrive file-locks broke worktree cleanup in Waves C/D).
- [ ] **Step 2:** Record baseline: `python -m pytest -q 2>&1 | tail -3` → expect 2234P/12S + known fails. Save the exact fail list to compare in Task 10.

### Task 2: Re-point live imports off the migration shims

**Files:**
- Modify: `services/data/context/builder.py:99,122,155,204,261,284,314` — `from core.config.prompts.automobile.X import …` → `from backend.sectors.automobile.prompts.X import …` (7 sites, names unchanged)
- Modify: `src/backend/shared/pipeline/base_agent.py:421` — `from core.config.prompts.automobile import …` → `from backend.sectors.automobile.prompts import …`
- Modify: `tests/contract/test_phase0_llm_migration.py:101,111,122` and `tests/unit/test_agents_unit.py:20-24` — `from core.sectors.automobile.X import YAgent` → `from backend.sectors.automobile.agents.X import YAgent`
- Modify: `tests/unit/sectors/automobile/test_prompts.py:16-20` — same prompts re-point (shared imports at :21-22 stay)

**Interfaces:** shims are `from backend.… import *` re-exports, so target symbols are identical by construction.

- [ ] **Step 1:** Apply the edits above (mechanical path swap).
- [ ] **Step 2:** `python -m pytest tests/unit/test_agents_unit.py tests/contract/test_phase0_llm_migration.py tests/unit/sectors/automobile/test_prompts.py tests/unit/test_context_builder*.py -q` → same pass/fail as baseline for those files.
- [ ] **Step 3:** Verify no live (non-test, non-dead-tree) importer of `core.config.prompts.automobile` or `core.sectors` remains: `git grep -lE "(from|import)[^#]*(core\.config\.prompts\.automobile|core\.sectors)" -- "*.py" | grep -vE "^(core/sectors|core/config/prompts|generate_sector_skeletons|src/backend/shared/pipeline/core_adapter|tests/unit/test_prompts.py)"` → empty.
- [ ] **Step 4:** Commit: `refactor(wave-e): re-point 8 prompt imports + 3 test files off migration shims (AUD-032 rider)`

### Task 3: Remove the `tier=core` dispatch branch (AUD-026 activation risk)

**Files:**
- Modify: `src/backend/sectors/registry.py:283,303-304` — remove the `tier=core → CoreSectorAdapter` branch; unknown/core tier now logs a warning and returns None (same as disabled). Update the docstring table at :283.
- Delete: `src/backend/shared/pipeline/core_adapter.py`

- [ ] **Step 1:** Edit registry.py; `git rm src/backend/shared/pipeline/core_adapter.py`.
- [ ] **Step 2:** `git grep -n "core_adapter\|CoreSectorAdapter" -- "*.py"` → hits only inside `core/sectors/` (deleted next task) and `generate_sector_skeletons.py`.
- [ ] **Step 3:** `python -m pytest tests -q -k "registry or sector"` → no new fails.
- [ ] **Step 4:** Commit: `refactor(wave-e): remove tier=core dispatch + CoreSectorAdapter (AUD-026) — a config flip can no longer activate 2024 skeletons`

### Task 4: Delete core/sectors, skeleton codegen, core/graphs, langgraph.json

**Files:**
- Delete: `core/sectors/` (253 files), `generate_sector_skeletons.py`, `core/graphs/` (4 shims), `langgraph.json`

- [ ] **Step 1:** `git rm -r core/sectors core/graphs && git rm generate_sector_skeletons.py langgraph.json`
- [ ] **Step 2:** Dangling check: `git grep -lE "core\.sectors|core\.graphs|generate_sector_skeletons|langgraph\.json" -- "*.py" "*.json" "*.toml" "*.cfg"` → empty (docs/ may still mention them).
- [ ] **Step 3:** Import smoke: `python -c "import main; import services.api.server; import services.scheduler.python.scheduler"` (run with repo sys.path as tests do; acceptable substitute: `python -m pytest tests/unit/test_agents_unit.py tests/contract -q`).
- [ ] **Step 4:** Commit: `chore(wave-e): delete core/sectors skeleton tree + codegen + core/graphs shims (AUD-026/029/079, AUD-095 shells)`

### Task 5: Delete dead prompt dirs (keep shared/)

**Files:**
- Delete: every `core/config/prompts/<dir>` except `shared/` (≈190 files incl. `automobile/` shims — Task 2 unhooked them)

- [ ] **Step 1:** `cd core/config/prompts && git rm -r $(ls -d */ | grep -v shared)` plus any loose non-shared files except `__init__.py`.
- [ ] **Step 2:** `git grep -lE "core\.config\.prompts" -- "*.py" | grep -v "core/config/prompts/shared"` → only files importing `…prompts.shared`.
- [ ] **Step 3:** `python -m pytest tests/unit -q -k "prompt or control_lane or dossier or event_ingestor or question or preopen or feedback_agent"` → no new fails.
- [ ] **Step 4:** Commit: `chore(wave-e): delete 20 dead legacy prompt dirs, keep prompts/shared (AUD-032)`

### Task 6: AUD-095 graph surgery — delete the standalone DAG, keep the fallback pool

**Files:**
- Delete: `src/backend/sectors/{automobile,banking_bfsi,it_sector,renewable_energy}/pipeline/graph.py`
- Modify: `src/backend/shared/pipeline/graphs/nodes.py` — remove `make_resolve_ticker_node`, `make_input_rail_node`, `make_aggregate_node`, `_score_to_verdict` (shell-only); trim now-unused imports (`input_rail`, `conflict_rail`, any resolver/LLM imports used only by removed nodes); update module docstring.
- Modify: `src/backend/shared/pipeline/graphs/rails.py` — remove `input_rail` and `conflict_rail` if nothing else imports them (`output_rail` stays — used by `make_run_agent_node:203`).
- Modify: `src/backend/shared/pipeline/graphs/__init__.py` — drop removed exports if listed.

**Interfaces:** `make_dispatch_fn(agent_names) -> Callable`, `make_run_agent_node(…)`, `GraphState` keep exact signatures — `base_orchestrator.py:53-54` depends on them.

- [ ] **Step 1:** Before editing, confirm shell-only status again: `git grep -l "make_aggregate_node\|make_resolve_ticker_node\|make_input_rail_node\|_score_to_verdict" -- "*.py"` → only graphs/nodes.py itself (shells + codegen already deleted in Task 4… the 4 src/backend shells die in this task's Step 2, so run this check after Step 2).
- [ ] **Step 2:** `git rm src/backend/sectors/*/pipeline/graph.py`; apply the nodes.py/rails.py/__init__.py edits.
- [ ] **Step 3:** Fallback-path regression: `python -m pytest tests/unit/test_orchestrator_unified_branch.py tests/unit/test_unified_e2e_parity.py tests/unit/test_unified_e2e_parity_sectors.py tests/unit/sectors -q` → all pass as baseline.
- [ ] **Step 4:** Commit: `refactor(wave-e): delete standalone LangGraph DAG (AUD-095) — legacy fallback pool retained; BULK-tier aggregate drift gone by deletion`

### Task 7: src/backend/sectors dead subset (AUD-033)

**Files:**
- Delete (verify each with zero-importer grep first): legacy fetchers `npa_metrics`, `rbi_data`, `mnre_data`, `transcript`, `deal_wins` (wherever they live under the 4 sector dirs), `schemas/sub_scores.py`, and the 5 latent prompt files (prompt modules under `src/backend/sectors/*/prompts/` with zero importers).

- [ ] **Step 1:** Enumerate: for every candidate `f`, `git grep -l "<module_name>" -- "*.py"` excluding the file itself and already-deleted trees → must be empty; build the final delete list. (The latent-prompt check: every `src/backend/sectors/*/prompts/*.py` module not imported by any agents/, builder, base_agent, or dimensions file.)
- [ ] **Step 2:** `git rm` the verified list.
- [ ] **Step 3:** `python -m pytest tests/unit/sectors tests/unit/pipeline -q` → baseline parity; import smoke as Task 4 Step 3.
- [ ] **Step 4:** Commit: `chore(wave-e): delete src/backend/sectors dead subset — legacy fetchers, sub_scores, latent prompts (AUD-033)`

### Task 8: Small orphans (AUD-027/031/034/035/037/080)

**Files:**
- Delete: `scripts/api_exploration/` (9 files); `src/frontend/web/` (27 tracked; also remove untracked node_modules from disk); `core/intelligence/rag/ingestion/` (3 files); `services/clients/alerting.py` + `src/backend/shared/clients/alerting.py`; `services/api/user_profile.py`; empty-namespace residue `src/backend/{api,intelligence,scheduler}/` (28 empty `__init__.py`, keep `src/backend/__init__.py`)
- Modify: `tests/integration/test_rag.py` — remove ingestion-only tests (classes/methods importing `rag.ingestion`); `tests/contract/test_scheduler.py` — remove alerting tests (`AlertManager`/`Alert` block around :150-232); delete `tests/unit/intelligence/chat/test_user_profile.py`

- [ ] **Step 1:** Zero-importer re-check per target (same grep pattern as recon; expect: empty outside the delete set + the test blocks being pruned).
- [ ] **Step 2:** `git rm -r` the dirs, `git rm` the files; prune the test blocks; delete `data/` artifacts? — NO, never touch data/.
- [ ] **Step 3:** `python -m pytest tests/integration/test_rag.py tests/contract/test_scheduler.py tests/unit -q` → baseline parity minus the pruned tests.
- [ ] **Step 4:** Commit: `chore(wave-e): delete orphans — api_exploration, frontend/web stub, rag ingestion, alerting client, user_profile, namespace residue (AUD-027/031/034/035/037/080)`

### Task 9: Merge duplicate test pairs (AUD-081)

**Files:** 8 pairs — canonical copy KEPT is the subdir one, root copy deleted after merge:
`tests/unit/{shared/test_config.py, intelligence/rl/test_enhancer.py, sectors/automobile/test_prompts.py, intelligence/rl/test_regime.py, contract/test_scheduler.py(vs tests/test_scheduler.py), unit/shared/test_schemas.py, intelligence/rl/test_seasonal.py, shared/test_signal_aggregator.py}`

- [ ] **Step 1:** For each pair: `git diff --no-index <root> <subdir>` — if identical, `git rm <root>`; if diverged, port unique/newer tests into the subdir copy, then `git rm <root>`. (Known diverged: test_enhancer. tests/test_scheduler.py vs tests/contract/test_scheduler.py may be different suites — merge only true duplicates, keep both if genuinely distinct.)
- [ ] **Step 2:** `python -m pytest tests -q 2>&1 | tail -3` — compare against Task 1 baseline: pass count may drop by exactly the number of de-duplicated collections; no NEW failure names. AUD-022 stale-mock fails that lived in deleted root copies disappear — record which.
- [ ] **Step 3:** Commit: `test(wave-e): merge 8 duplicate test pairs, single collection each (AUD-081)`

### Task 10: Final verification + ledger + ship

**Files:**
- Modify: `docs/audit/LEDGER.md` — Wave E section + flip AUD-026/027/029/031/032/033/034/035/037/079/080/081/095 rows to FIXED/DELETED with commit range; net file/LOC tally.

- [ ] **Step 1:** Full suite: `python -m pytest -q` → no new fails vs Task 1 list.
- [ ] **Step 2:** Entry-point smoke: `python -c "import compileall"`-style import of main/server/scheduler (as Task 4 Step 3); `python -m compileall core services src -q` → 0 errors.
- [ ] **Step 3:** Dockerfile validity: every COPY source still exists (`core/ services/ src/backend/ scripts/ main.py config.yaml config/ src/frontend/prototypes/`).
- [ ] **Step 4:** Tally: `git diff --stat main...HEAD | tail -1` — expect ≈550+ files deleted, ~25K LOC removed.
- [ ] **Step 5:** Update LEDGER.md, commit `docs(audit): Wave E shipped — dead-code docket deleted`, `git checkout main && git merge --ff-only audit-wave-e-deletions && git push`, verify Railway deploy goes green, update memory.
