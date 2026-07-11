# Deep Audit — Findings Ledger

Append-only. One row per finding. Format:
`ID | tag | severity | where | one-line defect | evidence | proposed action | status`

Severity: P0 money/data corruption · P1 wrong decisions/reliability · P2 design debt · P3 polish.
Status: `OPEN (PhN)` = to be verified/deepened in phase N · `ON-HOLD` · `USER-DECISION` ·
later: `WAVE-n` (assigned to remediation wave) · `FIXED` · `WONTFIX`.

Seeded rows (AUD-001…030, Phase 0) cite their source backlog; file:line gets pinned when the
owning phase examines them. `apl` = `.superpowers/sdd/compass-autopilot-progress.md`,
`phc` = `.superpowers/sdd/compass-phase-c-progress.md`, `mem` = audit program memory
known-issues, `ph0` = verified directly during Phase 0 at HEAD 69e317d.

## Money path (Phase 2 owners)

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-001 | BUG | P1 | `core/portfolio/store.py` + API mutation routes | No file locking on portfolio.json; API routes and pipeline both load→mutate→save; T9 doubled round-trips widen the race window. P0-class if concurrent writes collide | mem (known gap); apl:16 | FIX | OPEN (Ph2) |
| AUD-002 | BUG | P2 | `core/portfolio/store.py` sell() | Theoretical ZeroDivisionError when 0<qty≤1e-9 and adj_qty=0 | apl:8 (T1) | FIX | OPEN (Ph2) |
| AUD-003 | BUG | P2 | `core/portfolio/autopilot.py` | ADD executes at rec.close but valuation falls back to adj_avg_price when closes lacks the symbol — inconsistent equity around a trade | apl:12 (T5) | FIX | OPEN (Ph2) |
| AUD-004 | GAP | P2 | `core/portfolio/autopilot.py` | Sell path lacks price>0 guard | apl:21 (M1) | FIX | OPEN (Ph2) |
| AUD-005 | GAP | P2 | `core/portfolio/autopilot.py` | existing_ids not refreshed within a run — duplicate-id class inside one run | apl:21 (M2) | FIX | OPEN (Ph2) |
| AUD-006 | GAP | P2 | `core/portfolio/` | No ledger-replay reconciler: transactions.jsonl ⇄ portfolio.json drift is warned (I1 divergence warnings) but never reconciled | apl:20-21 | FIX | OPEN (Ph2) |
| AUD-007 | BUG | P2 | `services/api` portfolio delete/manual-txn routes | Non-idempotent datetime-ref manual txn ids; redundant store.load()s; dead 404 guard | apl:16 (T9, I3) | FIX (consolidate delete flow) | OPEN (Ph2) |
| AUD-023 | BUG | P2 | IST trading calendar | Guru Nanak Jayanti false-positive (trading day treated as holiday or vice versa) | mem (Ph2 known) | FIX | OPEN (Ph2) |

## Data layer (Phase 3 owners)

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-017 | BUG | P2 | NSE client | mkdtemp leak per client instantiation — temp dirs accumulate on the Railway volume | phc:21; mem | FIX | OPEN (Ph3) |
| AUD-024 | BUG | P2 | PredictionStore | mkdir-on-read side effect | mem (Ph3 known) | FIX | OPEN (Ph3) |
| AUD-025 | BUG | P2 | `services/api/server.py` | Hardcoded sector="automobile" in PredictionStore self-heal | mem (Ph3 known) | FIX | OPEN (Ph3) |

## Delivery / ops (Phase 7 owners)

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-012 | SEC | P1 | `services/api` push-subscribe route | Auth bypass: subscribe route skips SCHEDULER_KEY auth when the key is set | phc:21 | FIX (auth-lockdown ticket) | ON-HOLD (user 2026-07-10) |
| AUD-013 | GAP | P2 | `core/delivery` alerts_sent.jsonl | No rotation/truncation — unbounded growth on volume | phc:21 | FIX | OPEN (Ph7) |
| AUD-015 | GAP | P2 | `core/delivery` index/discovery/preopen alerts | Audience hardcoded to default user only | phc:21 | FIX | OPEN (Ph7) |
| AUD-019 | GAP | P2 | `core/delivery` alerts_sent.jsonl writer | Plain append vs global atomic temp+rename convention; readers tolerate torn lines | phc:12,21 (T7) | USER-DECISION | OPEN (user) |
| AUD-022 | GAP | P2 | tests/contract + tests/integration | 19 failures/errors, all tracing to 2 stale-mock roots: AutomobileAgentOrchestrator + SignalAggregator mock targets | apl:18 (T11 gate); phc:19 | FIX (one cleanup ticket) | OPEN (Ph7) |

## API / UI / chat (Phase 8 owners)

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-008 | PERF | P3 | `services/api` /performance | Legacy live-mark cost (M4); stale-history quirk right after delete (T10) | apl:17,21 | FIX | OPEN (Ph8) |
| AUD-014 | SEC | P2 | chat portfolio-brief fallback | "Brief unavailable: {exc}" surfaces raw exception internals in chat UI | phc:17,21 (T12) | FIX (sanitize) | OPEN (Ph8) |
| AUD-018 | GAP | P2 | chat system prompt | get_portfolio_brief tool absent from system prompt — chat can't discover the portfolio tool | phc:21 | FIX | OPEN (Ph8) |

## Decision quality (Phase 4 owners)

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-016 | PATTERN | P2 | advisor vs discovery | Two different "underweight" definitions in play | phc:21 | FIX (unify) | OPEN (Ph4) |

## Over-engineering / dead code (Phase 1 census → Phase 6 sweep)

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-026 | OVERENG | P2 | `core/sectors/` | 23 sector skeleton dirs vs 5 live sector impls (`src/backend/sectors/`); memory: toggled off, 8 LLM calls each if enabled | ph0 (ls verified); mem | DELETE (proposal Ph6) | OPEN (Ph1 wiring check) |
| AUD-027 | DEAD | P3 | `src/frontend/web/` | Stub React app; not in Dockerfile COPY set; prototypes are the real UI | ph0; Dockerfile | DELETE | OPEN (Ph6) |
| AUD-028 | OVERENG | P2 | `services/api` vs `src/backend/api` | Dual API route surfaces, both shipped in the image (`services/`, `src/backend/ → backend/`) | ph0; Dockerfile | census Ph1, then DELETE/merge | OPEN (Ph1) |
| AUD-029 | DEAD | P3 | `generate_sector_skeletons.py` (repo root) | One-shot codegen script (1,013-line single commit) living at root | ph0; churn scan | DELETE or move to tools/ | OPEN (Ph6) |
| AUD-030 | DEAD | P3 | `core/pipeline/orchestrator.py` | 853 lines churned across 7 commits, now a 7-line remnant — importers unknown | ph0 (wc) | verify importers, likely DELETE | OPEN (Ph1) |

## Polish batch (any wave)

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-009 | LOWIMPACT | P3 | `core/portfolio/digest.py` | SWITCH-day digest omits candidate value | apl:21 (M3) | FIX | OPEN |
| AUD-010 | LOWIMPACT | P3 | seed script | --force flag deviates from spec (M5b); no-tickers SystemExit precedes idempotency check (T8) | apl:15,21 | FIX | OPEN |
| AUD-011 | LOWIMPACT | P3 | multiple | Lint/docs batch: unused imports (T4/T11), stale docstrings/Layout docs (T1/T2), "Advisor escalations" title on trade-only batches (T7), M6 cosmetics | apl:8-18,21 | FIX (one commit) | OPEN |
| AUD-020 | LOWIMPACT | P3 | lockin watch | watched-or-None lockin widening | phc:21 | FIX | OPEN |
| AUD-021 | LOWIMPACT | P3 | preopen alerts | Alert scope broader than holdings | phc:21 | FIX or KEEP | OPEN |

## Phase 1 additions (2026-07-11, HEAD ab243ac — evidence in MAP.md)

`ph1` = import-reachability walk + entrypoint trace, docs/audit/MAP.md.

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-031 | DEAD | P3 | `services/api/user_profile.py` | 58 LOC, zero importers | ph1 | DELETE | OPEN (Ph6) |
| AUD-032 | DEAD | P2 | `core/config/prompts/` | 22 legacy per-dimension prompt dirs, 185 files / 8,259 LOC, unreachable (prompts route only imports `backend.*`); superseded by unified analyst | ph1 | DELETE | OPEN (Ph6) |
| AUD-033 | DEAD | P2 | `src/backend/sectors/` dead subset | 53 files / ~1,460 LOC: legacy fetchers (npa_metrics, rbi_data, mnre_data, transcript, deal_wins), `automobile/pipeline/graph.py`, `schemas/sub_scores.py`; +5 latent prompt files (338 LOC) editable via prompts route but consumed by nothing | ph1 | DELETE (latent prompts: decide in Ph5) | OPEN (Ph6) |
| AUD-034 | DEAD | P3 | `services/clients/alerting.py` | 196 LOC orphan alerting client | ph1 | DELETE | OPEN (Ph6) |
| AUD-035 | DEAD | P3 | `core/intelligence/rag/ingestion/` | ingestion.py + ingest_cli.py (304 LOC) unreachable; retriever/vector_store ARE live | ph1 | DELETE or move to tools | OPEN (Ph6) |
| AUD-036 | GAP | P3 | docs (run instructions) | 7× `python -m scripts.daily_review` + 3× `scripts.generate_forecast` reference files that no longer exist; 19× refs to manual run_schedule runner need a currency check | ph1 (grep) | FIX docs | OPEN (Ph7) |
| AUD-037 | OVERENG | P3 | `scripts/api_exploration/` | 7 exploration spikes (1,505 LOC) shipped inside the prod image (`COPY scripts/`) | ph1; Dockerfile | DELETE or move out of image | OPEN (Ph6) |

## Phase 1 backfill — real prod-run trace (2026-07-11 evening, Railway CLI)

Deployments traced: b6818b60 (08:23–14:54 IST, ran all three Saturday jobs) and
fec3e7a3 (live since 15:19 IST). `plog` = prod deploy logs, 2026-07-11.

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-038 | BUG | P1 | `services/scheduler/python/scheduler.py:133-141` | Daily review actually fires **Tue–Sat 11:00 IST**, not the intended Mon–Fri 16:30 IST: FEEDBACK_CRON `'0 11 * * 1-5'` was written as UTC (comment: "4:30 pm IST = 11:00 UTC") but raw fields go into `CronTrigger(timezone="Asia/Kolkata")`, and numeric `1-5` in APScheduler = Tue–Sat (0=Mon). Consequences: NO Monday review (first weekly auto-trade chance slips to Tuesday), Tue–Fri reviews run mid-session at 11:00 IST, digest lands at 11am. Only Job 1 affected — all other jobs use named days | plog: trigger `day_of_week='1-5'` fired Sat 2026-07-11 11:00:00 IST; no 08:45/08:50 jobs fired Sat | FIX (named days + intended hour, e.g. `hour=16, minute=30, day_of_week="mon-fri"`) | OPEN (Ph2) |
| AUD-039 | GAP | P1 | pipeline alerting (delivery layer exists but unused for self-monitoring) | A 100%-LLM-failure day produced **zero alerts**: 887× OpenRouter 401 (10:00–12:43 IST) and all 3 Saturday jobs logged "complete" — ingestion "total ingested=0", research "answered=0", discovery `errors=[]` with deep_dives=0/40 candidates; FeedbackAgent silently "weights and lessons NOT updated" | plog | FIX (LLM-failure circuit breaker + job-level failure-rate alert through existing push channel) | OPEN (Ph7) |
| AUD-040 | BUG | P2 | SectorRegistry toggles loader | Reads `/config/sector_toggles.json` (filesystem root — bad path resolution); never loads on Railway, silently uses defaults; any attempt to toggle sectors via file is a no-op | plog: both workers log Errno 2 at startup | FIX path + log level | OPEN (Ph6/wave) |
| AUD-041 | GAP | P2 | news context fetcher (daily review) | "Last 48h context" for TATAMOTORS contained an article dated 2026-05-13 (2 months old) — staleness filter ineffective or label wrong | plog 11:03:11 | VERIFY then FIX | OPEN (Ph3) |
| AUD-042 | COST | P1 | OpenRouter API key (Railway var) | Key invalid since ≥10:00 IST 2026-07-11 ("User not found" = key revoked/deleted at provider). Unknown whether the 14:54/15:19 redeploys fixed it — no LLM call has run since. **USER ACTION: verify/rotate OPENROUTER_API_KEY before Sun 18:00 IST weekly review** (next LLM-dependent job) | plog: 887×401 | USER (verify key) | OPEN (URGENT) |

**Prod observations (context, not defects):** singleton lock verified working (one worker
scheduler+self-heal, one API-only); volume mounted, 16 managed tickers present; 15 jobs
registered; autopilot did not engage on the Saturday run (0 log mentions — no portfolio
impact from the degraded day); SCHEDULER_KEY **not set** in prod → portfolio/scheduler
endpoints log "endpoint is open" warnings (per-user accepted for virtual-money phase —
evidence for the on-hold AUD-012 lockdown ticket); yfinance also threw 401 "Invalid Crumb"
during the window (fetcher resilience → Ph3).

**Updates to seeded rows:**

- AUD-001 — evidence hardened: prod runs `--workers 2`; singleton lock (server.py:302)
  covers scheduler/self-heal only, portfolio-mutating routes execute on both workers →
  race is cross-process. Severity P1 confirmed; candidate P0 reclassification in Phase 2.
- AUD-026 — confirmed + quantified: 253 files / 9,941 LOC; only consumer is
  `core_adapter` tier=core path, which registry (all 4 sectors tier=backend) never takes.
- AUD-028 — resolved: `src/backend/api` is DEAD (not mounted, zero importers). Merge
  action now = plain DELETE in Phase 6; `services/api` is the single live surface.
- AUD-030 — **resolved KEEP**: `core/pipeline/orchestrator.py` is a live migration shim
  (sector_router resolves automobile's orchestrator through it). Do not delete without
  updating sector_router._ORCHESTRATORS.
