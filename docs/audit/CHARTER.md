# Deep Audit — Charter (Phase 0)

Production-grade design/logic/ML audit of StockAgent. Approved 2026-07-11. Program memory:
`project_tech_audit_program.md` (Claude auto-memory). This doc + `LEDGER.md` are the in-repo
source of truth; `MAP.md` (Phase 1 output) will hold the system reality map.

**Goal (user's words):** track every logic, design, gap, better suggestion, improvisation;
find over-engineered stuff, low-impact design, better patterns/ML algorithms to replace.
Not a one-shot review — an end-to-end program.

## Rules

- **Report-first.** No fixes during audit phases. Fixes come as remediation waves (Phase 9
  output), each a separate planned session using the 3-agent loop.
- **No finding without evidence.** Every ledger row cites file:line, a source ledger, or a
  reproduced observation. Seeded rows carry their backlog source until re-verified in the
  owning phase.
- **Verdict per component:** FIX / DELETE / REPLACE / KEEP, with impact×effort (H/M/L) added
  when the owning phase examines it.
- **Prod constraint:** autopilot observation window is live — first auto-trades expected
  after the Mon 2026-07-13 daily review. Audit is read-only against prod; nothing that
  disturbs the pipeline, ledgers, or seeded portfolio.
- **Prod-run tracing prereq:** Railway MCP token expired → protocol step "trace one real
  prod run" is blocked until `railway login`. Static tracing proceeds; prod-log verification
  backfills later.

## Taxonomy

Tags: `BUG` · `GAP` · `OVERENG` · `LOWIMPACT` · `PATTERN` (better pattern exists) ·
`ML-UP` (better algorithm) · `PERF` · `SEC` · `COST` · `DEAD`.

Severity: **P0** money/data corruption · **P1** wrong decisions/reliability ·
**P2** design debt · **P3** polish.

## Phases

| # | Phase | Budget | Status |
|---|-------|--------|--------|
| 0 | Charter: artifacts, hotspot ranking, ledger seeding | ½ session | **DONE 2026-07-11** |
| 1 | System reality map: every entrypoint traced, every module LIVE/DARK/DEAD → `MAP.md` | 1–2 | IN PROGRESS |
| 2 | Money path: autopilot, ledgers, portfolio math, idempotency, concurrency, calendar | 2–3 | not started |
| 3 | Data layer: fetchers, EodStore, PredictionStore, symbol resolution, staleness | 1–2 | not started |
| 4 | Decision/ML quality: each algorithm vs statistical validity + naive baseline + better candidate | 2–3 | not started |
| 5 | LLM usage & cost: call-site × tier map, JSON hardening, cost per run vs cap | 1 | not started |
| 6 | Over-engineering sweep: deletion proposals with LOC counts | 1–2 | not started |
| 7 | Reliability/ops/security: retries, backups, observability, secrets, test health | 1–2 | not started |
| 8 | API/UI contract: route census, validation, error surfaces, chat cost/latency | 1 | not started |
| 9 | Synthesis → remediation waves ranked impact×effort | 1 | not started |

## Hotspot ranking — git churn × risk (2026-01-01 → 2026-07-11, prod files only)

Churn = added+deleted lines across commits touching the path. Risk weight: money path >
live decision path > live serving path > config > UI. Historical-only churn (paths deleted
by the April restructure) excluded — see notes below.

| # | File | Churn | Commits | LOC now | Risk driver | Owning phase |
|---|------|-------|---------|---------|-------------|--------------|
| 1 | `services/api/routes/ui_data.py` | 5,265 | 46 | 3,639 | Largest live surface; serves UI **and mutates portfolio**; god-file | 2, 8 |
| 2 | `core/intelligence/rl/workflows/daily_review.py` | 1,499 | 32 | 1,492 | Daily advisor → autopilot money path | 2, 4 |
| 3 | `src/backend/shared/config/settings/base.py` | 1,348 | 37 | 854 | Config god-object; every feature flag flows through it | 1 |
| 4 | `services/scheduler/python/scheduler.py` | 1,325 | 24 | 927 | Prod scheduler (Jobs 1–14); single point of cadence | 1, 7 |
| 5 | `core/intelligence/rl/workflows/generate_forecast.py` | 884 | 18 | — | Envelope forecasts feeding advice | 4 |
| 6 | `main.py` | 865 | 12 | 210 | Pipeline entrypoint | 1 |
| 7 | `core/pipeline/orchestrator.py` | 853 | 7 | **7** | Churned heavily, now a 7-line remnant — verify importers | 1, 6 |
| 8 | `src/backend/shared/pipeline/unified_analyst.py` | 761 | 5 | — | One-call analyst for all live sectors | 4, 5 |
| 9 | `core/portfolio/*` (store/autopilot/advisor/pipeline) | (new, Jul '26) | — | — | Money path; newest code so churn window understates risk | 2 |
| 10 | `src/frontend/prototypes/rl-monitor.jsx` + prototypes | 1,790 | 11 | — | Prototypes ARE the prod UI (Dockerfile serves them at `/`) | 8 |

**Historical churn artifacts (not findings):** `services/api/chat_graph.py` (2,388/15) —
deleted, DAG chat retired for agentic loop; top-level `frontend/`, `typescript/`,
`services/typescript/` (incl. committed node_modules) — all removed by the April 2026
restructure; `git ls-files` confirms 0 node_modules files tracked at HEAD (69e317d).

## Census corrections found during Phase 0

The program memory's Phase-1 suspect list was partly stale. Verified at HEAD 69e317d:

- **Gone already:** top-level `typescript/` wrapper, C# scheduler, committed node_modules,
  duplicate `scripts/make_ppt.py` / `sanity_rl.py` copies. Two API surfaces remain, not 3;
  one scheduler (python), not 2.
- **Still present (Phase 1/6 targets):** `core/sectors/` = 23 sector skeleton dirs vs 5
  live sector impls under `src/backend/sectors/`; `src/frontend/web` stub (has node_modules
  on disk, untracked, not in Dockerfile); dual API surface `services/api` vs
  `src/backend/api` — Dockerfile ships **both** (`services/` and `src/backend/ → backend/`);
  7 orchestrator-named modules across `core/` and `src/backend/`;
  `generate_sector_skeletons.py` (one-shot codegen) at repo root.
- **Deploy anchor:** single Dockerfile → Railway. Ships `core/`, `services/`, `src/backend/
  → backend/`, `scripts/`, `main.py`, `config.yaml`, `src/frontend/prototypes/ →
  frontend/prototypes/`. Anything outside that COPY set is DEAD in prod by construction.

## Session protocol

Per module: read code → trace data flow end-to-end → (when unblocked) trace one real prod
run via Railway logs → check test coverage vs failure modes → ledger rows with evidence →
verdict. Every session ends with a ledger commit and a program-memory status update.
