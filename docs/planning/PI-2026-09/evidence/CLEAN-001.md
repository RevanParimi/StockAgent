# CLEAN-001 receipt — remove provably unused files

Owner scope change, 13 Nov 2026, session `stockagent-main-50` [fcd907]. The fresh review is
waived by the owner (deletions only). The acceptance is the full suite. Local branch
`chore/remove-dead-code` from `e2b6f34`; not pushed, not deployed.

| Item | Commit | Result | Proof of non-use | Tests |
|---|---|---|---|---|
| 1 `new-product.py`, `example-answers.json` | `643d605` | done: 2 files, −561 lines | No import, run, COPY, CI or script reference; one doc row (PRODUCT_MAP §19) updated | none reference them |
| 2 `services/csharp/`, compose `csharp-scheduler` | `8cccc41` | done: 12 files, −589 lines | Never built in the image (`COPY services/` carried it as inert files); only the opt-in compose profile built it; no Python, CI or script reader. Production sets no `CSHARP_*` variable. The KT sentence was dropped and the PDF rebuilt | `test_phase4_csharp.py` + `test_phase2_api.py`: 59 passed; `check_kt_docs` `errors: []` |
| 3 RAG | `25d6b65` | done: 9 files deleted, −799 lines | Production sets no RAG, Chroma, embedding, vector-store or reranker variable (38 names read, values never printed). The only importers of `chromadb`/`sentence_transformers` were the RAG files; nothing imports `tiktoken` or `torch`; `pypdf`'s other user, `check_kt_docs.py`, installs it from `scripts/docs/requirements.txt` | 9 related files: 123 passed; broad-except OK (148) |
| 4 requirements | `7ed7251` | done | No application import of pytest tools. The kept `openai==2.32.0` and `yfinance==1.3.0` admit exactly what the old pairs admitted | `test_ipo_bids.py` (parses the nse pin): 14 passed |
| 5 `main.py` | `7b6a64d` | done: −217 lines | Railway builds `/Dockerfile` with no start-command override, and the CMD runs uvicorn; no code, test, script, CI or compose invocation | the boundary test file and every test file naming the macro cache or ContextBuilder: 399 passed |
| 7 C# score proxy (`b1aa410`) | done: 1 test file deleted, −381 lines | With `services/csharp/` gone, the flag, URL and `ScoreStore.save` proxy branch had no destination. Production sets neither variable, and the flag defaulted to false, so every save took the SQLite path, which is unchanged | `test_scheduler.py` (SQLite saves), score-history, FIX-029, boundary and config tests: 115 passed |
| 8 macro cache (`3558c88`) | done: 4 files deleted, −201 lines | Nothing in `core/`, `services/`, `src/` or `scripts/` calls `set_macro_cache`, so every read missed and the four builders always fetched fresh news. The fresh-fetch paths are unchanged. `macro_cache_key` and `MACRO_CACHE_TTL_HOURS` (and its config key) were read only by the cache. `cache_hit` stays: the Tavily cache produces it | 21 bundle, builder, data-health and config files plus the boundary test: 769 passed |
| 9 enhancement consumer (`e114b99`) | done: −39 lines | `BaseAgent._extra_queries` and `load_prompt_enhancements` fed only `_rag_retrieve`; nothing calls or reads them now. The enhancer and the feedback agent's read are unchanged. Docs (RL_DESIGN §15, AGENTIC_DESIGN, KT §3) corrected; PDF rebuilt | 7 related files: 175 passed, plus 1 pre-existing order-dependent failure (below) |
| 10 allow rules (`8f7c7e5`) | done: 9 rules | They ran `main.py`, `test_rag.py` or `test_phase4_csharp.py`; 95 → 86 allow rules, deny list unchanged | JSON validated |
| 6a shims | — | skipped | Gate failed: `core.schemas` has 132 import sites and `core.pipeline` 9; `tests/contract/test_scheduler.py:149` patches through `core.pipeline.orchestrator` | — |
| 6b docs move | — | skipped | Risk sign: `config/milestones.yaml:52`, which the watchdog reads in production, names `docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`, the paused IPO lane's live plan | — |

Items 1–5: 43 files changed, 29 insertions, 2,183 deletions.

**Full suite** on `7b6a64d`: 6,409 passed / 12 skipped / 1 xfailed / 0 failed, pytest rc 0, 19m34s (17:42-18:02 IST); the 11 fewer than FIX-030's 6,420 are exactly the 8 deleted test_rag.py tests and the 3 TestRAGConfig tests; `check_broad_except` OK (148); `check_kt_docs` `errors: []`.

**Dependency delta** (pip dry-run resolution for Linux x86_64 / CPython 3.11, public PyPI metadata,
`pywebpush` left out of both sides because it has no wheel): 150 → 78 distributions; 72 dropped, none
added, no remaining version changed; dropped wheels total 659 MB compressed (torch 2.15.0 alone 539 MB).
This is a lower bound: a dry run on Windows cannot evaluate torch's Linux-only CUDA (`nvidia-*`)
dependencies, which SA-028 found in the production image on 23 Sep. The image was not built (no
Docker here), and CI time was not measured.

**Rollout notes.** Editing `requirements.txt` makes the next production build re-resolve every unpinned
package (SA-033 is the lock). The branch sits on unpushed FIX-030, so pushing it also deploys FIX-030,
which waits for `FIX-030-M1`.

**Items 7–10** were added at the owner's word in the same conversation ("if its dead code now,
remove them"), covering the first pass's leftover list. Items 1–10 together: 57 files, +44/−2,805
lines, not counting bookkeeping.

**Full suite after items 7–10** on `8f7c7e5`: 6,378 passed / 12 skipped / 1 xfailed / 0 failed, pytest rc 0, 29m47s (19:13-19:43 IST); 31 fewer than 6,409 = the 24 deleted C# contract tests and the 7 macro-cache-hit tests; `check_broad_except` OK (148); `check_kt_docs` `errors: []`.

**Pre-existing, not caused here:** run alone,
`test_phase0_llm_migration.py::TestOrchestratorUsesOpenAI::test_orchestrator_instantiates_openai`
fails ("OpenAI called 10 times") on the untouched base `e2b6f34` too (checked in a detached
worktree). It passes only when an earlier file has already imported the orchestrator's module-level
sub-agents, as in the full suite.

**Still for the owner:** the KT header names `cddc3be`; bump it when the branch merges.

SA-028 overlap: this retires the RAG and C# paths and splits the test tools. The build backend, the
compiled client and the C++ decision remain SA-028's.
