# System Reality Map — Audit Phase 1

Date: 2026-07-11 · HEAD: ab243ac · Method: entrypoint trace + AST import-reachability
walk from prod roots, with dynamic-import edges resolved by hand. Prod-log verification
(protocol step 2) **done same day via Railway CLI** — see §7; topology claims below are
prod-confirmed.

## 1. Prod topology

One Railway service, one container, one image:

```
Dockerfile CMD → uvicorn services.api.server:app --workers 2
   worker A (singleton, via localhost:59321 bind — server.py:302)
      ├─ APScheduler in-process: Jobs 1–14 (services/scheduler/python/scheduler.py)
      └─ RL self-heal daemon thread (startup)
   worker B: API-only
   BOTH workers: serve all 10 routers, including portfolio-mutating routes
```

- The singleton lock exists because of a real 2026-07-02 double-fire incident (every
  cron ran twice, 2× LLM spend, tmp→rename races) — server.py:289–296.
- **The lock protects background jobs only.** Portfolio mutations via API can execute on
  either worker while Job 1 (autopilot) mutates on worker A → the AUD-001 no-file-locking
  race is real cross-**process**, not just cross-thread.
- Volume mounts at `/app/data` (checked at startup); calendar file ensured at startup.
- Image COPY set: `core/`, `services/`, `src/backend/ → backend/`, `scripts/`, `main.py`,
  `config.yaml`, `src/frontend/prototypes/ → frontend/prototypes/` (served at `/`).

## 2. Entrypoints

**HTTP (services/api/server.py)** — 10 routers, all from `services/api/routes/`:
analyse, history, stream, ui_data, scheduler_api, prompts, analytics, portfolio_api,
discovery_api, delivery_api. Static: prototype PWA at `/`. `src/backend/api` is **not
mounted anywhere** — dead tree.

**Scheduler (embedded, IST crons)** — services/scheduler/python/scheduler.py:

| Job | What | When (IST) |
|-----|------|------------|
| 1 | Daily RL review → advisor → **autopilot** | intended 16:30 Mon–Fri; **actually fires 11:00 IST Tue–Sat** (AUD-038, prod-observed) |
| 2 | Monthly forecast | 1st, 09:00 |
| 3 | Calendar update | Dec 31, 23:00 |
| 4 | Prompt daily deploy | 00:00 |
| 5 | Market-hours pipeline run | 09:00/12:00/15:00 weekdays |
| 6 | Daily policy/RBI run | 07:30 weekdays |
| 7 | Weekly ledger cleanup | Mon 03:30 |
| 8 | Monthly scorecard | 1st, 02:00 |
| 9 / 9b | Event ingestion / research loop | Sat 10:00 / 11:00 |
| 10 | Pre-open shock check | 08:45 weekdays |
| 11 | Bhavcopy sync | 19:00 weekdays |
| 12 | Discovery funnel | Sat 12:30 |
| 13 | Morning brief | 08:50 weekdays |
| 14 | Weekly review + index watch | Sun 18:00 |

**Manual/CLI (DARK — in image, run by hand):** `main.py` (single-ticker CLI);
`scripts/` = clean_ledger_errors, gen_vapid_keys, model_bench, reasoning_bench,
seed_autopilot; `python -m services.scheduler.run_schedule` (624 LOC manual runner,
19 doc references); `python -m core.intelligence.rl.eval.run_eval` (134 LOC).
Note: docs also reference `python -m scripts.daily_review` (7×) and
`scripts.generate_forecast` (3×) — **those files no longer exist** → doc rot (AUD-036).

## 3. Reachability census

AST walk over `import`/`from` (incl. function-local and relative), roots = server.py +
manual dynamic edges; separately main.py + `scripts/*.py`. Two pitfalls found and fixed:
(a) UTF-8 **BOM** breaks `ast.parse` → silently drops a file's edges (many files here
have BOMs); (b) dynamic string imports. Resolved dynamic edge families:

| Site | Pattern | Resolution |
|------|---------|-----------|
| sector_router.py:29–46 | orchestrator + weight modules per sector | 4 native sectors + generic fallback; automobile → `core.pipeline.orchestrator` (**live 7-line shim** → `backend.sectors.automobile.pipeline.orchestrator`) |
| unified_analyst.py:232–258 | `SECTOR_SPECS[*].prompts_module` | 5 × `backend.sectors.{s}.prompts.unified` |
| base_orchestrator.py:315 | `backend.sectors.{s}.config.settings` | 5 sector settings modules |
| routes/prompts.py:125,141 | `backend.sectors.{sector}.prompts.{agent}` | hot-deploy route: reaches ANY prompt file under live sectors (see latent set below) |
| core_adapter.py:37,60 | `core.sectors.{s}.registry/.graph` | **never taken**: registry.py:38–41 enables 4 sectors, all `tier=backend`; tier=core is the only caller |

**Result (873 prod .py files, 66.2K LOC):**

| Class | Files | LOC | Definition |
|-------|-------|-----|------------|
| LIVE | 218 | 42,039 | reachable from server.py (incl. scheduler) |
| DARK | 14 | 2,018 | manual CLI/runners + 5 latent prompt files (338 LOC) editable via prompts route but consumed by nothing |
| DEAD | 586 | 22,103 | unreachable from any entrypoint — **33% of shipped LOC** |

**DEAD by tree (deletion targets for Phase 6):**

| Tree | Files | LOC | What it is |
|------|-------|-----|------------|
| `core/sectors/` | 253 | 9,941 | 23 sector skeletons (graph/registry/agents per sector); only consumer is the never-taken tier=core path |
| `core/config/prompts/` (+shims) | 185 | 8,259 | 22 legacy per-dimension prompt dirs, superseded by unified analyst; prompts route cannot reach them (backend.* prefix only) |
| `src/backend/sectors/` dead subset | 53 | ~1,460 | legacy per-sector fetchers (npa_metrics, rbi_data, mnre_data, transcript, deal_wins), `automobile/pipeline/graph.py`, `schemas/sub_scores.py` |
| `scripts/api_exploration/` | 7 | 1,505 | broker/API exploration spikes, shipped in prod image |
| `core/intelligence/rag/ingestion/` | 2 | 304 | ingestion CLI + pipeline (retriever/vector_store ARE live) |
| `services/clients/alerting.py` | 1 | 196 | orphan alerting client |
| `services/api/user_profile.py` | 1 | 58 | zero importers |
| misc `__init__`/stubs | ~84 | ~380 | mostly empty package files under dead trees |

## 4. Census answers (program questions)

- **API surfaces:** 1 live (`services/api`). `src/backend/api` DEAD (no importers, not
  mounted). The old `typescript/` wrapper was deleted in the April restructure.
- **Schedulers:** 1, embedded APScheduler in the API process behind a port-bind singleton.
  C# scheduler no longer exists. `services/scheduler/run_schedule.py` is a manual runner.
- **Frontends:** prototypes tree is the real UI (served at `/`); `src/frontend/web` is a
  dead stub (not in image).
- **Orchestrator paths:** one dispatch chain — sector_router → per-sector orchestrator
  (4 native + generic), all through `base_orchestrator`. `core/pipeline/orchestrator.py`
  is a live migration shim, not dead (AUD-030 resolved KEEP).
  Note: `automobile/pipeline/graph.py` is DEAD — the "native graph" module isn't imported
  by its own orchestrator; automobile likely runs unified-analyst like the rest (verify
  in Phase 4/5).
- **Config surface:** single chain — `config.yaml` (19 sections) → `settings/loader.py` →
  `backend/shared/config/settings/base.py` (854-LOC god-object, 25 residual getenv sites).
  `core.config.settings` is a compat shim re-exporting it. One config source confirmed;
  god-object split is design-debt for Phase 6/9.
- **Prompt trees:** live = `backend.sectors.{5}.prompts.unified` only. 22 legacy dirs
  under `core/config/prompts/` dead; 5 latent per-dimension files under live sectors
  editable-but-unconsumed.

## 5. Corrections to prior beliefs (memory/docs said → reality)

- "regime detector, WeightAdapter, price_interpolator, context builder possibly dead" →
  all **LIVE** (first classifier pass mislabeled them due to the BOM parse bug — worth
  remembering as a tooling gotcha).
- "~20 core/sectors skeletons + 23 prompt dirs" → quantified: 9.9K + 8.3K LOC, both dead.
- "3 API surfaces, 2 schedulers" → 1 + 1 at HEAD; the others were already deleted.
- `services/api/chat_graph.py` (old DAG chat) already deleted; agentic loop is the only
  chat path.

## 6. Ledger deltas from Phase 1

New: AUD-031…037. Updated: AUD-001 (evidence hardened: 2 workers × mutation routes),
AUD-026 (confirmed + quantified), AUD-028 (src/backend/api confirmed dead),
AUD-030 (resolved KEEP — live shim). See LEDGER.md.

## 7. Prod-run trace (backfill, 2026-07-11 evening — Railway CLI)

Deployments: b6818b60 (08:23–14:54 IST — ran Saturday's jobs) → cecd42a7 (14:54) →
fec3e7a3 (15:19, live). Verified against real logs:

- **Topology confirmed:** two uvicorn workers; singleton lock works (one worker logs
  "held by another worker … API requests only", the other starts self-heal + scheduler);
  volume mounted True; 16 managed tickers on volume; "BackgroundScheduler started — 15
  jobs registered"; RL self-heal completed via checkpoint skips.
- **Job-1 schedule reality (AUD-038):** "RL daily feedback review" trigger
  `day_of_week='1-5', hour='11'`, tz Asia/Kolkata — fired **Saturday** 2026-07-11
  11:00:00 IST, reviewing 2026-07-10. Numeric days + IST timezone ≠ the "11:00 UTC
  weekdays" comment. No Monday run exists on current prod.
- **Incident (AUD-042/039):** OpenRouter key invalid — 887× HTTP 401 "User not found"
  from 10:00:19 to 12:43:11 IST; every LLM call of event-ingestion, daily review,
  research loop, and discovery deep-dives failed; all jobs still reported "complete"
  (ingested=0, answered=0, deep_dives=0, discovery errors=[]); zero alerts emitted.
  Autopilot did not engage (no log mentions; portfolio untouched).
- **Misc:** SectorRegistry tries `/config/sector_toggles.json` at fs root (AUD-040);
  SCHEDULER_KEY unset → open endpoints warned at startup; yfinance 401 "Invalid Crumb"
  during the window; a "last 48h" news context contained a 2026-05-13 article (AUD-041).

## 8. Phase 2 census correction — money path (2026-07-12)

Phase 1 marked `core/portfolio/*` LIVE. Phase 2 shows the execution half is
**DARK, not LIVE**: `run_post_review_pipeline` (advisor → autopilot → value point →
digest) has no caller on the production schedule — the APScheduler `rl_daily_review`
job never invokes it; only HTTP `POST /scheduler/daily-review|backfill` and
`POST /portfolio/run-advisor` reach it (AUD-043). Prod confirms: zero
`[portfolio_pipeline]` log lines across deployments; value_history has exactly the
seed point (2026-07-11); autopilot=true with no trades and no digests.

Corollary: the advice ledger, transactions ledger (beyond seed), digests, briefs'
digest fallback, and the equity curve are all dormant until AUD-043 is fixed or a
human POSTs daily. The compass expectation "first auto-trades Tue 2026-07-14" does
not hold on current prod.

Calendar reality (AUD-023 expanded): prod runs on the hardcoded 2026 fallback —
`rl_calendar_update` fires only Dec 31 and the service first deployed 2026-05-04,
so `data/nse_holidays.json` has never been written. The fallback list has 2 past
false holidays (Mar 4, Mar 20) and misses 4 future weekday holidays (Sep 14, Oct 20,
Nov 10, Nov 24).

OpenRouter key (AUD-042): verified working 2026-07-12 after env-var redeploy
8d2c6c31 — live chat probe streamed a real LLM token. Monthly-limit check on the
new key still outstanding.
