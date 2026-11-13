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
| 6a shims | — | skipped | Gate failed: `core.schemas` has 132 import sites and `core.pipeline` 9; `tests/contract/test_scheduler.py:149` patches through `core.pipeline.orchestrator` | — |
| 6b docs move | — | skipped | Risk sign: `config/milestones.yaml:52`, which the watchdog reads in production, names `docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`, the paused IPO lane's live plan | — |

Total: 43 files changed, 29 insertions, 2,183 deletions.

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

**Left for the owner** (seen, not changed):
- the `CSHARP_*` flag, URL and `score_store` proxy branch;
- `.claude/settings.local.json` allow rules naming `main.py` and `test_rag.py`;
- the `settings/base.py` comment saying the bundle builder fills the macro cache (it has no writer);
- prompt enhancements loaded into `BaseAgent._extra_queries` had only `_rag_retrieve` (always off) as a
  reader, so AGENTIC_DESIGN's "search queries can be extended by the cycle's prompt enhancements" was
  not true in production (learning loop, out of scope);
- the KT header still names `cddc3be`; bump it when the branch merges.

SA-028 overlap: this retires the RAG and C# paths and splits the test tools. The build backend, the
compiled client and the C++ decision remain SA-028's.
