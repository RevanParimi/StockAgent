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
| AUD-012 | SEC | P1 | `services/api` push-subscribe route | Auth bypass: subscribe route skips SCHEDULER_KEY auth when the key is set | phc:21 | FIX (auth-lockdown ticket) | FIXED (2026-07-16 Wave B — POST/DELETE keyless BY DESIGN for the pre-login 🔔 flow; hardened instead: https-only endpoint + per-user 50-sub cap) |
| AUD-013 | GAP | P2 | `core/delivery` alerts_sent.jsonl | No rotation/truncation — unbounded growth on volume | phc:21 | FIX | OPEN (Ph7) |
| AUD-015 | GAP | P2 | `core/delivery` index/discovery/preopen alerts | Audience hardcoded to default user only | phc:21 | FIX | OPEN (Ph7) |
| AUD-019 | GAP | P2 | `core/delivery` alerts_sent.jsonl writer | Plain append vs global atomic temp+rename convention; readers tolerate torn lines | phc:12,21 (T7) | USER-DECISION | OPEN (user) |
| AUD-022 | GAP | P2 | tests/contract + tests/integration | 19 failures/errors, all tracing to 2 stale-mock roots: AutomobileAgentOrchestrator + SignalAggregator mock targets | apl:18 (T11 gate); phc:19 | FIX (one cleanup ticket) | OPEN (Ph7) |

## API / UI / chat (Phase 8 owners)

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-008 | PERF | P3 | `services/api` /performance | Legacy live-mark cost (M4); stale-history quirk right after delete (T10) | apl:17,21 | FIX | OPEN (Ph8) |
| AUD-014 | SEC | P2 | chat portfolio-brief fallback | "Brief unavailable: {exc}" surfaces raw exception internals in chat UI | phc:17,21 (T12) | FIX (sanitize) | FIXED (2026-07-16 Wave B — absorbed by AUD-103) |
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
| AUD-042a | COST | P1 | (root cause update, 2026-07-11 evening) | Confirmed via OpenRouter dashboard: key "BlueStock" status **Expired** (created with an expiry date); live chat probe still returns LLM-failure fallback → prod degraded NOW, redeploys did not fix. Secondary trap: key usage $25.42 vs **$15/month key limit** — a replacement key with the same cap will 402/429 mid-month at the ~$19–25/mo real burn. Replacement key should have limit ≥$30 or none, and no expiry (or calendar reminder) | dashboard screenshot + chat-stream probe (canned fallback, ui_data.py:3313 path) | USER (new key, update Railway var) | OPEN (URGENT) |

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

## Phase 2 — Money path (2026-07-12, HEAD 98449af)

`ph2` = full read of core/portfolio/* + schemas + portfolio_api/scheduler_api +
scheduler.py + nse_calendar/calendar_updater, cross-checked against prod via Railway
logs and read-only API probes. 129 money-path unit tests pass at HEAD — every defect
below lives in untested territory.

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-043 | BUG | P1 | `services/scheduler/python/scheduler.py:464-522` | **Autopilot/advisor pipeline unreachable from the production schedule.** `run_post_review_pipeline` (advisor → autopilot → value point → digest → alerts) is called ONLY from HTTP `_review_task` (scheduler_api.py:244) and manual POST /portfolio/run-advisor (portfolio_api.py:384). The APScheduler `rl_daily_review` job runs reviews and returns — no pipeline call. CODEBASE.md:273 documents the intended hook as if live; test_scheduler_portfolio_hook.py patches only the API module (false confidence). Prod signature: zero `[portfolio_pipeline]` lines in any deployment; value_history frozen at the seed point (GET /performance 2026-07-12: 1 point, 2026-07-11); autopilot=true but nothing will ever trade. **No auto-trades Tue 2026-07-14 without a fix or a manual daily POST /scheduler/daily-review** | ph2; plog; /performance probe | FIX (wire `_daily_review_job` → pipeline; impact H, effort L) — USER-DECISION: hotfix before Tue 2026-07-14? | OPEN (URGENT) |
| AUD-044 | BUG | P1 | `services/api/routes/portfolio_api.py:365-388` + `core/portfolio/autopilot.py:270,280-284` | Future-dated POST /portfolio/run-advisor bricks autopilot: any future weekday passes `is_trading_day`, all `close_on` calls fail → advice empty → `execute_advice` still stamps `last_autopilot_run=<future>` and the monotonic guard then rejects every real run until that date. Also saves a future-dated digest that pins /digest/latest. One typo'd year = autopilot silently dead for months, zero alerts | ph2 (code path) | FIX (reject review_date > today-IST at the route; never stamp marker beyond today; impact H, effort L) | OPEN (Ph2) |
| AUD-045 | GAP | P2 | `core/portfolio/corp_actions.py:112-113` + `core/portfolio/autopilot.py:307-316` | Dividends are booked to `holding.dividends_received` (inflates pnl% and realized_pnl on sell) but **never credited to cash_deployable** — total_equity = MV + cash excludes them, so the equity curve understates true return while pnl% overstates vs equity; on SELL, ledger `realized_pnl` includes the dividend slice but `cash_after` moves only by qty×price — ledger cash and P&L are mutually inconsistent by construction | ph2 | FIX (credit cash at ex-date, or exclude dividends from realized_pnl — pick one accounting identity) | OPEN (Ph2→wave) |
| AUD-046 | GAP | P2 | `core/portfolio/corp_actions.py:25,81-87` | Dividend regex assumes ₹-per-share; an NSE row quoting percent-of-face-value ("Dividend 150%") books ₹150/share into dividends_received → pnl% inflated → can suppress a legitimate EXIT (stop math is dividend-inclusive). Tests cover only "Rs 8 Per Share" format | ph2; tests/unit/test_portfolio_corp_actions.py:41-66 | VERIFY real NSE actions() formats in Ph3, then FIX parser (% × face value or reject) | OPEN (Ph3) |
| AUD-047 | PATTERN | P2 | `core/portfolio/advisor.py:127-131` + `core/portfolio/pipeline.py:63-68` vs `core/portfolio/autopilot.py:220-227` | Two weight definitions in one decision chain: advisor position_weight_pct and pipeline sector_weights use **cost basis** (adj_avg_price), autopilot ADD headroom uses **market value** — the ADD gate and the ADD sizing can disagree on the same holding; SWITCH underweight test also runs on cost. Third instance of the AUD-016 class | ph2 | FIX (one MV-based weight helper shared by advisor/pipeline/autopilot) | OPEN (Ph4 w/ AUD-016) |
| AUD-048 | LOWIMPACT | P3 | `core/portfolio/advisor.py:73-82,100-124` | Cap-bucket stop machinery is constant in practice: pipeline never passes market_cap_inr, so resolve_cap_bucket always returns "mid" — stops are always clamp(3×ATR, 12, 18) (large-bucket if conservative). large/small buckets + both floor_cr settings are unreachable code | ph2; pipeline.py:93-96 | FIX (wire real mcap) or DELETE the parameter | OPEN (Ph4) |
| AUD-049 | GAP | P3 | `scripts/seed_autopilot.py:47,75-87` | Seed appends transactions before the single portfolio save; a crash mid-loop leaves txns with no holdings, and the idempotency check then refuses re-seed — recovery requires manual volume surgery. One-time script, low likelihood | ph2 | KEEP (document) or FIX (write txns after save) | OPEN (polish) |
| AUD-050 | GAP | P2 | `core/portfolio/store.py:83-99` | Corrupt portfolio.json is quarantined and **silently replaced by an empty portfolio** — API keeps serving/saving empty state, autopilot disengages (cash None), no alert fires. Correct crash-safety instinct, wrong failure mode for the money store | ph2; ties to AUD-039 | FIX (alert + refuse mutations while quarantined file exists) | OPEN (Ph7) |
| AUD-051 | GAP | P3 | `services/scheduler/python/scheduler.py:473-475` + `services/api/routes/scheduler_api.py:65-70` | Both review-date derivations skip weekends but not holidays ("not NSE-holiday-aware for simplicity") — the day after any weekday holiday reviews the holiday and no-ops the whole ticker loop; compounds with AUD-023's missing holidays | ph2 | FIX alongside AUD-038 (use nse_calendar last-trading-day) | OPEN (Ph2 wave) |

**Updates to seeded rows (Phase 2 verification):**

- AUD-001 — **reclassified P0** (was P1). The race window is not milliseconds, it is
  the WHOLE pipeline run: pipeline.py:50 loads the portfolio, then per-holding network
  fetches (close_on, 1y OHLCV) + LLM narration run for minutes, then execute_advice
  saves the stale object (autopilot.py:283,288). Any API mutation in between is
  silently reverted while its transaction stays in the ledger → ledger/portfolio
  divergence. Mutation routes run on both uvicorn workers; store.py has zero locking;
  corp_actions.sync adds a second load-mutate-save. Today the pipeline only runs via
  manual HTTP (AUD-043) so collisions need a manual trigger; the moment AUD-043 is
  fixed this is live daily at review time. **Wave-1 rule: file locking must land in
  the same change that wires the scheduler hook.**
- AUD-002 — verified; downgrade P3. `Holding.sell` (schemas/portfolio.py:64-72) raises
  on overdraw; ZeroDivision needs adj_qty exactly 0 with 0<qty≤1e-9, and zero-qty
  holdings are removed at creation of that state. Theoretical only.
- AUD-003 — confirmed, pinned: ADD/sell execute at `closes.get(sym) or rec.close`
  (autopilot.py:75,212) while valuation falls back to adj_avg_price
  (autopilot.py:120-122). Same-run equity mixes two price bases when closes lacks a
  symbol. Also: SWITCH buy price from close_on never enters `closes` → digest values
  the new position at cost and shows NO_DATA (= AUD-009's mechanism, pipeline.py:122).
- AUD-004 — confirmed for sells only: buys guard `price <= 0` (autopilot.py:213),
  sells don't (autopilot.py:75) — a 0-price sell would wipe the position for ₹0 cash.
  Unreachable from today's pipeline (close_on raises instead of returning 0) — P3 in
  practice, guard still worth adding.
- AUD-005 — **resolved at HEAD**: existing_ids is refreshed between the sell and buy
  legs (autopilot.py:275), and within-leg collisions are impossible (txn_id embeds the
  advice ref incl. rationale_hash, unique per record). No duplicate-id class remains.
- AUD-006 — confirmed open, sharpened: the dedupe key itself is fragile across a
  crash-retry because rationale_hash is recomputed from live signals (advisor.py:294);
  if triggers shift between crash and retry, the retry gets a NEW txn_id and re-sells —
  portfolio stays consistent (it was never saved) but the ledger records two SELLs for
  one economic sale and /performance double-counts realized_pnl. Reconciler (replay
  transactions.jsonl → derived portfolio, diff against portfolio.json) remains the fix.
- AUD-007 — confirmed + worse: delete flow is THREE sequential writes
  (reduce_holding save → cash-credit save → txn append, portfolio_api.py:177-204); a
  crash after the first write destroys the cash credit AND the audit record — the
  holding is gone, cash never credited, ledger silent. Manual txn ids are
  datetime-based (portfolio_api.py:156,198) → client retries double-record. Also
  noted: sell-price fallback to adj_avg_price on fetch failure (line 189) silently
  sells at cost on data-outage days. CSV import path credits neither capital_in nor
  cash (store.py:301-330) while POST /holdings does — two manual-entry accountings.
- AUD-023 — **expanded to P1, root cause found.** Hardcoded 2026 fallback
  (nse_calendar.py:64-73) is wrong: Mar 4 + Mar 20 were real trading days marked as
  holidays (labels are shifted guesses: actual Holi was Mar 3, actual Eid Mar 21 —
  both dates false), and FOUR future weekday holidays are missing — **Sep 14 (Ganesh
  Chaturthi), Oct 20 (Dussehra), Nov 10 (Diwali Balipratipada), Nov 24 (Guru Nanak)**
  [NSE 2026 official list]. Root cause: the correcting job `rl_calendar_update` only
  fires Dec 31 (scheduler.py:171-176) and the service first deployed 2026-05-04
  (git log) — it has NEVER run, so data/nse_holidays.json cannot exist on the volume
  (no "[nse_calendar] Loaded" at startup; direct volume check pending — needs
  `railway ssh -- ls data/`). On each missing-holiday date: close_on treats it as a
  trading day, gets no data and RAISES instead of walking back (pricing.py:30-35) →
  every holding skipped, no advice, autopilot stamps the marker for a dead day.
  FIX: run calendar_updater at startup when file missing/stale + correct the
  hardcoded list (impact H, effort L).
- AUD-038 — unchanged (cron still wrong at HEAD); note the interplay: fixing the cron
  alone doesn't start autopilot (AUD-043), and fixing both still leaves review_date
  derivation holiday-blind (AUD-051).
- AUD-042/042a — **key verified WORKING 2026-07-12**: fresh deploy 8d2c6c31 (06:25
  IST, same commit — env-var change), zero 401s since, and a live /ui/chat/stream
  probe streamed a real LLM token (not the canned fallback). Residual: confirm the
  replacement key's monthly limit ≥ $30 (042a trap) — dashboard-only check.

**Component verdicts (Phase 2 protocol step 5):**
`autopilot.py` KEEP (clean deterministic core; add AUD-004/044 guards) ·
`store.py` KEEP+FIX (locking AUD-001, corrupt-load AUD-050) ·
`advisor.py` KEEP+FIX (AUD-047/048) · `pipeline.py` KEEP+FIX (AUD-043 wiring, AUD-001) ·
`corp_actions.py` KEEP+FIX (AUD-045/046) · `pricing.py` KEEP (correct given a correct
calendar) · `nse_calendar.py`+`calendar_updater.py` FIX (AUD-023) ·
`portfolio_api.py` FIX (AUD-007 consolidation, AUD-044 guard) · `digest.py`,
`narrator.py`, `promotion.py`, seed script KEEP (polish rows only).

## Wave 1 — correctness remediation SHIPPED (2026-07-12, merge 6884dd8)

Spec: docs/superpowers/specs/2026-07-12-audit-wave1-correctness-design.md ·
Plan: docs/superpowers/plans/2026-07-12-audit-wave1-correctness.md ·
14 commits 96b1dd8..6884dd8, reviewer-runs-code verdict APPROVED (9/9 executed
criteria), unit suite 1913 passed / 5 skipped (2 pre-existing failures
unchanged: event_ingestor date-parse [fails on main], eval harness real-data
[environment]). Prod deploy + post-deploy verification logged below the table.

| ID | Resolution |
|----|------------|
| AUD-001 | **FIXED** 96b1dd8+539b6da — filelock per user (`portfolio.lock`, re-entrant, 30 s timeout) on every RMW; executor reloads FRESH state under the lock (stale pre-advisor snapshot is signals-only). Cross-process atomicity + fresh-reload proven by executed tests |
| AUD-002 | **FIXED** 0303347 — `Holding.sell` guards `adj_qty <= 0` |
| AUD-003 | **FIXED** 539b6da — every executed price feeds back into `closes` (one price basis per run; also removes AUD-009's mechanism) |
| AUD-004 | **FIXED** 539b6da — sell path skips non-positive prices |
| AUD-006 | **FIXED (detect+alert per user decision)** 557d6e8 — `core/portfolio/reconcile.py`: cash-chain continuity (lost-update signature), final-cash replay, per-symbol net qty (corp-action-adjusted symbols reported unverifiable); daily pipeline step; drift → critical push alert; never repairs |
| AUD-007 | **FIXED** 15bab5f — delete = one locked critical section (price fetched pre-lock); manual txn ids state-derived (`manual-add\|date\|qty\|price`), identical same-day resubmits skipped whole; CSV import credits capital_in |
| AUD-023 | **FIXED** ec354d4 — official 2026 NSE list hardcoded (adds Sep 14/Oct 20/Nov 10/Nov 24 etc., drops false Mar 4/Mar 20); holiday set = hardcoded ∪ file (partial yfinance file years can no longer drop future holidays); startup refresh when file missing OR lacks current year |
| AUD-038 | **FIXED** 51e9000+2dc8c53 — `feedback_cron: "30 16 * * mon-fri"` in config.yaml (the live source) + settings fallback + comments; named days end the numeric-day trap |
| AUD-039 | **FIXED** 4fc1a31 — `core/delivery/ops_alerts.py`: LLM consecutive-failure streak alert (≥10, throttled 6 h, wired into `record_llm_call`) + zero-output alerts on daily review / event ingestion / discovery deep-dives |
| AUD-040 | **FIXED** 9f89f6e — toggles path CWD-relative (+ env override) AND `COPY config/` added to Dockerfile (file never shipped in the image at all) |
| AUD-043 | **FIXED** 51e9000 — `_daily_review_job` now event-triggers `run_post_review_pipeline(review_date)` (non-fatal); review_date holiday-aware; REAL hook test executes the scheduled job itself |
| AUD-044 | **FIXED** 539b6da+1a0bdf5 — routes 422 future review_date (IST); executor refuses future dates outright (no marker stamp); value points skip future dates |
| AUD-045 | **FIXED (credit-cash per user decision)** 51c96d0 — dividends credit cash_deployable at ex-date application + append `DIV` ledger rows (side literal widened); no prod migration needed (pipeline never ran → dividends_received all 0) |
| AUD-046 | **PARTIAL (guard)** 51c96d0 — percent-of-face-value dividend rows skipped with warning; full parse fix stays gated on Ph3 format verification |
| AUD-049 | **FIXED** 9f89f6e — seed saves portfolio before appending txns |
| AUD-050 | **FIXED** 1792588 — `QuarantinedPortfolioError` blocks saves while an unrecovered corrupt archive exists (reads stay up); 409 handler; critical alert on quarantine |
| AUD-051 | **FIXED** 51e9000 — both review-date derivations use `trading_days_ago(now_ist().date(), 1)` |

Also shipped: `_today_ist()` seam + frozen-today fixtures make all executor tests
calendar-independent; sync_corp_actions split into fetch-outside-lock /
apply-under-lock phases.

Still OPEN from Phases 0–2 (deferred by scope decision, unchanged): AUD-005
(resolved earlier), 008, 009 (mechanism fixed via 003; digest cosmetics remain),
010, 011, 012 (ON HOLD), 013–022, 024–037, 041, 042a residual (key limit/balance
check), 047, 048.

## Phase 3 — Data layer (2026-07-12, HEAD f2177e8)

`ph3` = full read of services/data/* (fetchers, stores, cache, context wiring),
prediction_store, symbol_resolver, indicators/fetcher, daily_review fetch path,
server.py self-heal. `probe` = live read-only NSE probe run locally 2026-07-12
(fetch_equity_historical_data + actions() across MARUTI/TCS/HDFCBANK/SUNPHARMA/
ITC/VEDL, 60 action rows). `plog` = prod deploy logs via Railway MCP 2026-07-12.

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-052 | BUG | P2 | `core/portfolio/corp_actions.py:25,81-97` | `_DIV_RE.search` captures the FIRST amount only — NSE combines interim+special dividends in one row ("Interim Dividend Rs 11 Per Share/ Special Dividend Rs 46 Per Share", TCS pattern EVERY January; "Dividend - Rs 6.75 /Special Dividend - Rs 2.75", ITC 2023): the special slice is silently dropped from cash credit + P&L. Risk universe-dependent (TCS/ITC not in current 16) but the class is live for any promoted holding | probe (real rows) | FIX (parse every `dividend…amount` segment, sum; effort L) | OPEN (wave) |
| AUD-053 | GAP | P2 | `core/portfolio/corp_actions.py:parse_action` | Demerger rows return None with **no warning** — a demerger on a held stock leaves adj basis unadjusted → phantom −X% "crash" on ex-date → false EXIT/stop fire (exactly the class this module exists to prevent; the split/bonus branch does warn). Real rows: ITC 06-Jan-2025, VEDL 30-Apr-2026 | probe; corp_actions.py:98-101 warns only for split/bonus | FIX (WARN + mark holding corp-action-unverifiable + suppress auto-EXIT on demerger ex-date) | OPEN (wave) |
| AUD-054 | BUG | P2 | `services/data/fetchers/fundamentals.py:27-33` | Private `_nse_ticker` bypasses symbol_resolver AND `YF_SYMBOL_OVERRIDES` — TATAMOTORS (managed, automobile) hits `TATAMOTORS.NS`, stale/dead since the 2025 demerger (override says TMPV.NS) → analyst fundamentals context empty or wrong-entity daily. Same naive-suffix class: analysis_logger.py:76 (log-only, P3), ui_data.py:1129/2284/3474 (chat, mixed) | ph3; settings/base.py:158-163 | FIX (route through resolve_yf_symbol; effort L) | OPEN (wave) |
| AUD-055 | GAP | P2 | `src/backend/shared/data/fetchers/symbol_resolver.py:107-136` | Wrong-company cache-poisoning guard only protects tickers present in static `TICKER_SECTOR` — unknown symbols (discovery shelf, user adds, future promotions) may still learn a wrong-company mapping from a single "valid" fuzzy Yahoo match and keep it forever. Companion of the portfolio-page "validate before promotion" follow-up | ph3 | FIX (unknowns: require name-similarity or exact-root; or resolve+validate at promotion time) | OPEN (Ph6/wave) |
| AUD-056 | PATTERN | P2 | `core/intelligence/algorithms/indicators/fetcher.py:258-294,548-581` | `get_technical_context` hardcodes correlation/beta vs `NIFTY_AUTO_TICKER` and automobile-peer Serper fallback queries — and it feeds the unified analyst for ALL sectors (bundle_builder.py:283-285, builder.py:144-146,825-827): banking/IT/renewable prompts carry "Nifty Auto Correlation/Beta" as decision input | ph3 | FIX (sector→index map in SECTOR_SPECS; feeds Ph4/5 decision-quality review) | OPEN (Ph4) |
| AUD-057 | LOWIMPACT | P3 | `services/data/stores/api_usage.py`, `nse_key_registry.py:117-122`, symbol/company caches | Non-atomic `write_text` + in-process-only threading locks across 2 uvicorn workers + scheduler → lost updates / torn JSON (Serper monthly counter undercounts → false quota headroom; registry/caches degrade gracefully) | ph3 | FIX (shared temp+rename util, one polish commit) | OPEN (polish) |
| AUD-058 | LOWIMPACT | P3 | `prediction_store.py:127`, `news.py:37`, `close_verifier.py:47`, `bhavcopy.py:97`, `api_usage.py:55` | `date.today()`/`utcnow()` = server TZ (UTC): cycle ids, day-cache keys and month counters shift between 00:00–05:30 IST and at month boundaries. Latent — all scheduled jobs run 08:50–18:00 IST | ph3 | KEEP (document) or fold into an ist_today() helper during a wave | OPEN (polish) |
| AUD-059 | OVERENG | P3 | `services/data/fetchers/nse_market.py` | Second NSE client library (`nsepython`) shipped alongside the `nse` package for FII/DII + a second bulk-deals path — two scraper deps to break independently | ph3 | Ph6 consolidation candidate | OPEN (Ph6) |

**Updates to seeded rows (Phase 3 verification):**

- AUD-017 — confirmed + widened: `mkdtemp` per call across **9 prod files** (bhavcopy
  ×2 per fetch_day — client + folder arg, bhavcopy.py:52,65; corporate_events per
  symbol; close_verifier per ticker/day; nse_announcements, bulk_block, surveillance,
  ipo, index_watch, nse_key_registry.seed). Target is container /tmp (resets on
  redeploy), NOT the volume — the 800-day backfill left ~1,600 dirs+CSVs in the
  then-running container. Fix: one shared download dir with cleanup. Severity stays P2.
- AUD-024 — confirmed, pinned prediction_store.py:119 (`mkdir` in `__init__`).
  Read-heavy constructors are everywhere (analytics routes build stores per request
  per ticker: analytics.py:168,304,377,438,503,584) → empty dirs accumulate on the
  volume. FIX: mkdir lazily on write paths only.
- AUD-025 — **escalated P2→P1, prod-confirmed.** The startup self-heal iterates ALL
  managed tickers (`get_active_tickers()`, 16 across 4 sectors) but constructs
  `PredictionStore(ticker, sector="automobile")` (server.py:164) and calls
  `generate_forecast(ticker)` / `run_daily_review(ticker, date)` WITHOUT sector —
  both default to "automobile" (generate_forecast.py:406, daily_review.py:391). For
  12 non-auto tickers: envelope lookup misses (wrong root) → regenerates through the
  AUTOMOBILE analyst → writes a shadow envelope under data/predictions/automobile/
  <TICKER>/ → backfills a month of daily reviews against it. Monthly checkpoint
  (data/self_heal_checkpoint_YYYY-MM.json) makes the burn recur on the first deploy
  of every month: ~12 forecasts + ~12×20 reviews of wrong-sector LLM spend, plus a
  growing shadow tree the real scheduler jobs (which pass correct sectors) never
  read. Prod: 2026-07-12 08:29 IST startup logs show all 16 tickers checkpoint-
  skipped for cycle 2026-07 → the July burn already happened. Secondary hardcodes:
  prediction_store.py:345 (`sector or "automobile"` in load_control_log),
  scheduler_api.py:163 (default param). FIX: use get_active_tickers_with_sector()
  and pass sector through (effort L, impact H — cost + data hygiene). **Volume
  CONFIRMED (user ran `railway ssh "ls data/predictions/automobile/"` 2026-07-12):
  33 ticker dirs under automobile/ — all 12 non-auto managed tickers present
  (SUZLON, INOXWIND, WAAREEENER, ADANIGREEN, YESBANK, IDFCFIRSTB, RBLBANK, PAYTM,
  OLAELEC, KPITTECH, PERSISTENT, TATAELXSI, HAPPSTMNDS, OLECTRA) plus legacy auto
  names (APOLLOTYRE, BALKRISIND, BOSCHLTD, CEATLTD, ESCORTS, MOTHERSON, MRF,
  TIINDIA…). BONUS defect evidence for AUD-024: malformed sibling dirs
  `'TATA MOTORS'` (space) next to TATAMOTORS and `TVSMOTORS` next to TVSMOTOR —
  some call path constructs PredictionStore with raw un-normalized display names
  and mkdir-on-init mints a junk dir each time (PredictionStore strips/uppercases
  but never validates against the registry). Cleanup of the shadow+junk dirs
  belongs in the AUD-025 fix wave.**
- AUD-041 — root cause pinned: `get_news_context` (news.py:274-317) applies **no
  date filter at all** — no Serper time-range param, no post-filter on the dates it
  already parses via `_normalize_date` — yet stamps output "last 48h context"
  (news.py:305). FeedbackAgent correlates months-old articles with today's move
  (prod: 2026-05-13 article in TATAMOTORS "48h" context on 2026-07-11). Also
  `_normalize_date` returns the RAW STRING on parse failure (news.py:60) → junk in
  prompt date tags. FIX: post-filter to review_date−2d + honest header + drop
  unparseable dates (effort L). Upgrade P2→P1 candidate: this is a direct RL
  training-signal contaminant.
- AUD-046 — **RESOLVED (verified low-risk).** Live probe of real `actions()` rows
  (60 rows, 6 symbols, 2015–2026): 100% ₹-per-share formats ("Rs 140 Per Share",
  "Rs 80/-", "Rs 15 Per Sh" — all parse), ZERO percent-of-face-value rows in the
  NSE feed. Wave-1 percent guard is sufficient; full %-parser unnecessary.
  Superseded by AUD-052 (combined rows) as the real dividend-parse risk.

**Prod observations (context):** current deploy 50a66b18 startup clean; zero
[close_verifier] lines since deploy — expected, no review job has run post-deploy
(Wave-1 cron = Mon–Fri 16:30 IST; next fire Mon 2026-07-13). Historical-data API
keys verified against live NSE: `mtimestamp`/`chClosingPrice` exactly as
close_verifier expects, rows oldest→newest (package docstring claiming mTIMESTAMp
is wrong, code is right).

**Test coverage vs failure modes:** close_verifier 12 unit tests (all NSE-mocked;
the live-API key-shape assumption was untested until this probe) · news staleness
UNTESTED (get_news_context appears only as a mock in RL tests) · fundamentals
symbol resolution UNTESTED (an "honors YF_SYMBOL_OVERRIDES" test would have caught
AUD-054) · corp_actions combined-dividend + demerger rows UNTESTED · self-heal
sector wiring UNTESTED (same false-confidence class as AUD-043's hook test).
Pattern from Phase 2 holds: every defect sits in untested territory.

**Component verdicts (Phase 3 protocol step 5):**
`eod_store.py` KEEP (atomic per-day parquet, regex-filtered, corrupt-skip) ·
`bhavcopy.py` KEEP+FIX (AUD-017 ×2/call) · `corporate_events.py` KEEP+FIX (mkdtemp;
parser fixes live in corp_actions AUD-052/053) · `news.py` FIX (AUD-041) ·
`close_verifier.py` KEEP (live-verified, well-tested — the strongest file in the
layer) · `symbol_resolver.py` KEEP+FIX (AUD-055 unknown-ticker guard) ·
`fundamentals.py` FIX (AUD-054) · `prediction_store.py` KEEP+FIX (AUD-024, :345
hardcode) · `server.py` self-heal FIX (AUD-025 P1) · `nse_key_registry.py` KEEP
(+AUD-057 polish) · `daily_review._fetch_actual_close` KEEP (overrides + BSE + C++
fallbacks + NSE cross-check — the reference implementation) · macro_cache /
nse_market / mf_herding / bulk_block / surveillance / ipo KEEP (house pattern
conformant) · `api_usage.py` KEEP+polish (AUD-057).

## Phase 4 — Decision/ML quality (2026-07-12, HEAD ae4fe7b)

`ph4` = full read of core/intelligence/rl/{eval,agents,algorithms,conviction,workflows},
core/intelligence/regime, core/discovery/{signals,screen,deep_dive}, core/portfolio/advisor,
autopilot sizing path, src/backend/shared/pipeline/signal_aggregator + settings constants.
`sc` = data/eval/scorecards (May n=6, June n=1 — real artifacts). `dev` = local
data/predictions feedback logs (3 files: BUY n=7 hit 0%, NEUTRAL n=2 hit 100%).
Rubric per algorithm: statistical validity · vs-naive-baseline · better-algorithm candidate.

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-060 | BUG | P1 | `feedback_agent.py:87-101` + `daily_review.py:547` | **NEUTRAL verdict = automatic direction hit** ("always treated as not-wrong") → inflates direction_accuracy, Brier (outcome forced 1.0), scorecard agent lane (baselines get NO free pass; control lane FLAT must exact-match — asymmetric duel), WeightAdapter hit credit for all agents, and **the advisor ADD money gate** (`direction_accuracy_7d` ≥ 0.60, advisor.py:160-164): a NEUTRAL month scores 100% and passes the quality gate with zero demonstrated skill. Synthetic generator uses the OTHER rule (hit iff FLAT, synthetic.py:266-269) — synthetic/live semantics diverge | ph4; dev (NEUTRAL 100% vs BUY 0%) | FIX (score NEUTRAL correct iff actual FLAT everywhere, or exclude NEUTRAL days from accuracy denominators; align synthetic+live+control on ONE rule; effort L-M, impact H) | OPEN (wave) |
| AUD-061 | BUG | P2 | `eval/scorecard.py:49-58,201-205` + `eval/harness.py:193-215` | Ticker discovery = directory scan of data/predictions → AUD-025's shadow `automobile/<non-auto>` trees (33 dirs on volume) pool into the aggregate (`all_entries.extend`) double-counting 12 tickers, and `sc.tickers[ticker]` is silently overwritten by the last sector dir. Scorecard job IS live (scheduler Job 8, 1st 02:00 IST) → the Aug-1 run builds a contaminated July scorecard | ph4; AUD-025 volume evidence | FIX (registry-driven discovery via get_active_tickers_with_sector; joins AUD-025 wave incl. tree cleanup) | OPEN (wave w/ 025) |
| AUD-062 | GAP | P2 | scorecard/duel edges | No statistical significance anywhere: edges + month-over-month deltas are raw point differences on n=1–20 correlated days (sc: June n=1 renders "edge"); "did RL help" is unanswerable from output | sc; ph4 | FIX (Wilson CI / binomial test + min-n gate before rendering edges; pool ≥3 months; effort L) | OPEN (Ph9) |
| AUD-063 | PATTERN | P2 | `control_lane.py:95-101` vs envelope verdicts | Duel horizon mismatch: control predicts NEXT-DAY with same-day fresh market_context; the agent's verdict for that day was fixed at month-start (verdict never revised — only confidence). Scoring rules also differ (control: exact 3-way match; agent: is_direction_correct w/ NEUTRAL free pass). Negative edge is uninterpretable; docstring parity claim ("exactly the information StockAgent has") is false | ph4 | FIX (score both lanes with one rule on the same day set; add cycle-return sign scoring; document asymmetry) | OPEN (Ph9) |
| AUD-064 | BUG | P2 | `weight_adapter.py:338-380` | Bias score = blame-share among MISSES, not miss rate over days (denominator = penalisable misses only): a window's single miss blamed on agent X → bias_score 1.0 → full penalty at 95% ensemble accuracy; docstring example computes over days | ph4 | FIX (denominate by window days or require min misses; effort L) | OPEN (wave) |
| AUD-065 | BUG | P3 | `weight_adapter.py:509-518` + `daily_review.py:791-808` | Per-agent labels on ensemble numbers: escape-hatch "agent streak" loops agents but computes the identical ensemble direction_correct streak for each; `_accuracy_trend` prints "agent: W/7" lines that are all the ensemble rate — misinformation into the FeedbackAgent prompt | ph4 | FIX (use per-agent calibration records or drop the per-agent framing) | OPEN (polish) |
| AUD-066 | ML-UP | P2 | `weight_adapter.py:295-310` credit assignment | Learning signal is 1 bit/day: LLM picks ONE scapegoat; every other agent gets hit credit → direction component of per-agent hit_rate near-identical across agents; uniform boosts cancel exactly under renormalization (delta ∝ weight). The real per-agent signal exists (Component-2 calibration_hits vs own lean, blended 50%) | ph4 | REPLACE candidate (Wave 4): drive weights from per-agent calibration accuracy via multiplicative-weights/Hedge or Thompson; drop blame plumbing | OPEN (Ph9/W4) |
| AUD-067 | BUG | P2 | `regime/detector.py:116-174` | All three signal fetchers ignore `as_of_date` (`period="1mo"/"3mo"` + `iloc[-1]`) → backfilled reviews stamp TODAY's regime on historical entries (regime_label on FeedbackEntry, regime-segmented historical returns, sticky transitions). AUD-025's July backfill labeled a month of entries with one day's regime | ph4 | FIX (slice frame at as_of_date; effort L) | OPEN (wave) |
| AUD-068 | BUG | P2 | `price_interpolator.py:517-612,355-359` | `compute_historical_avg_return` = median DAILY price_error_pct, but the profile-LLM prompt presents it as "Historical average return … over 30 days" → monthly_return_pct calibrated against a wrong-scale number | ph4 | FIX (compute realized cycle return per verdict: last actual vs base_close; effort L-M) | OPEN (wave) |
| AUD-069 | GAP | P2 | envelope confidence semantics | `confidence` is not a probability: base = LLM composite `final_score` (bullishness), then horizon decay + band penalty + blends/multipliers (generate_forecast.py:166, interpolator:289-299, daily_review revise) — yet Brier/reliability_table treat it as P(hit) and the advisor consumes it; reliability_table exists but NOTHING recalibrates from it | ph4; sc (May: Brier .164 on 0% accuracy) | FIX (rolling isotonic/Platt map before writing DailyForecast.confidence, or split display-score from probability field) | OPEN (Ph9/W4) |
| AUD-070 | GAP | P2 | MC band calibration | σ = LLM band (anchor ATR×0.5) × regime scale — no feedback from realized coverage; P10–P90 at that σ is ≈half of realized daily moves → systematic under-coverage (sc May: band_coverage 0.0, n=6); `band_coverage` also returns 0.0 when NO band exists (metrics.py:147-151) masking absent bands as zero coverage. No envelope-level naive baseline exists (duel covers direction only) | ph4; sc | FIX (σ from realized returns EWMA/GARCH-lite, LLM adjusts ±; trailing-coverage width correction; add "zero-drift GBM w/ historical σ" envelope control lane; distinguish no-band from zero-coverage) | OPEN (Ph9/W4) |
| AUD-071 | PATTERN | P3 | verdict/scoring granularity | One month-scoped verdict copied onto ~30 daily rows, scored daily against ±0.3% FLAT threshold — daily noise dominates the metric the whole loop learns from | ph4 | Design note for Ph9: score cycle-return sign at horizon alongside daily | OPEN (Ph9) |
| AUD-072 | OVERENG | P3 | `eval/synthetic.py:70-73` + harness ablation | Ablation deltas measure the generator's own hard-coded constants (0.05/0.03/0.02 injected, then "detected"); real-data ablation is a documented no-op — circular instrumentation | ph4 | KEEP generator (schema parity), drop/flag ablation delta reporting | OPEN (Ph6) |
| AUD-073 | LOWIMPACT | P3 | `algorithms/factor_regime.py` | IIMA factor data frozen at 2023-03 → MOMENTUM/REVERSAL label + agent leniency (0.80/0.85) are constants from 2022-23 presented as live regime awareness; also `requests.get(verify=False)` in prod code (:71-75) | ph4 | FIX (compute WML live from EOD store or DELETE; at minimum verify=True) | OPEN (Ph6) |
| AUD-074 | LOWIMPACT | P3 | `daily_review.py:233-282` | Timing "lag" = review-day index minus envelope argmax day — measures nothing about when the actual move occurred; feeds WeightAdapter timing-penalty tiers | ph4 | Document or replace with actual move-day detection | OPEN (polish) |
| AUD-075 | PATTERN | P2 | `advisor.py:194-210` + `deep_dive.py:134` | SWITCH gap compares raw deep-dive LLM final_score against the holding's horizon-decayed mean envelope confidence — different quantities, different scales; decay alone biases toward SWITCH; the 0.15 gap has no calibration basis. Third member of the AUD-016/047 "one semantics" family | ph4 | FIX with 016/047 (single confidence/weight semantics helper) | OPEN (wave w/ 016/047) |
| AUD-076 | ML-UP | P3 | `autopilot.py:235-243` sizing | Fixed-fraction sizing (ADD = 25% of position value; TRIM 25%; equal-weight seed) with vol-scaled STOPS but not vol-scaled SIZES → per-name risk heterogeneous by construction | ph4 | Wave-4 candidate: ATR/vol-targeted sizing reusing the advisor's ATR | OPEN (Ph9/W4) |
| AUD-077 | PATTERN | P1 | `signal_aggregator.py:129-172,264-265` | **Learned weights do not bind the decision.** Verdict + final_score come free-form from the aggregation LLM; the weighted composite appears only as one prompt line. The entire learning loop (WeightAdapter, regime multipliers, lesson emphasis, seasonal deltas) modulates prompt context, not a decision function — its causal effect on trades is unenforced and unmeasured (no ablation lane, no composite-vs-final_score drift logging). SCORE_THRESHOLDS verdict bands already exist in settings but are unused here | ph4 | FIX (Ph9 decision: (a) verdict = threshold(composite), LLM narrates — matches advisor's "LLM never decides" philosophy; or (b) at minimum log/monitor LLM-vs-composite drift + add a thresholded shadow lane to the scorecard) | OPEN (Ph9 — USER DECISION) |

**Updates to seeded rows (Phase 4 verification):**

- AUD-016/047 — confirmed + widened: advisor position_weight_pct is cost-basis
  (advisor.py:127-131) while autopilot gates/sizes on market value; AUD-075 adds the
  conviction-vs-confidence instance. One wave item: single weight+confidence semantics.
- AUD-048 — confirmed unchanged at HEAD: `build_signals(market_cap_inr=None)` default and
  no caller passes mcap → `resolve_cap_bucket` always "mid"; stops always clamp(3×ATR,12,18).
- AUD-056 — unchanged; its decision-quality impact lands via analyst prompts (Ph5 scope).
- Advisor threshold provenance (rubric): every ADVISOR_* constant is a config fallback with
  no evidence trail (trim 25%, ADD gate 0.60 — measured on the AUD-060-inflated metric,
  max position 10%, SWITCH gap 0.15). Not separately actionable beyond 048/060/075.

**Test coverage vs failure modes:** direction-semantics (NEUTRAL) asymmetry untested
(synthetic and live rules diverge silently) · scorecard discovery never tested against a
polluted tree · WeightAdapter bias-score denominator untested at low miss counts ·
regime as_of_date behavior untested for backfill dates · no test asserts envelope
band coverage ≈ nominal 80%. Phase 2/3 pattern holds: defects live where tests aren't.

**Component verdicts (Phase 4 protocol step 5):**
`eval/metrics.py`+`baselines.py` KEEP+FIX (060 semantics, 070 no-band conflation) ·
`eval/scorecard.py` KEEP+FIX (061/062) · `eval/harness.py` KEEP (drop ablation output, 072) ·
`eval/synthetic.py` KEEP (schema-parity value) · `weight_adapter.py` REPLACE-candidate
(Wave 4 via 066; interim FIX 064/065) · `feedback_agent.py` KEEP (parse hardening + rate
cap are good) · `lesson_emphasis.py` KEEP (bounded, clean) · `conviction/tracker.py` KEEP ·
`regime/detector.py` KEEP+FIX (067; rule-based+hysteresis is right-sized — HMM/BOCPD NOT
warranted at this scale) · `regime/state.py` KEEP (well-built, idempotent) ·
`factor_regime.py` FIX-or-DELETE (073) · `price_interpolator.py` KEEP+FIX (068/070) ·
`generate_forecast.py` KEEP+FIX (069) · `daily_review.py` KEEP+FIX (060/065/074 wiring) ·
`control_lane.py` KEEP+FIX (063) · discovery `signals.py`+`screen.py` KEEP (strongest
decision-quality files this phase; honest dark-signal renormalization) · `deep_dive.py`
KEEP+FIX (075) · `advisor.py` KEEP+FIX (047/048/060/075) · autopilot sizing KEEP (076
later) · `signal_aggregator.py` FIX (077 — the phase headline).

## Phase 6 — Over-engineering / dead-code sweep (2026-07-12, HEAD 13ca54a; Phase 5 deferred by user)

`ph6` = full census re-run at HEAD (AST import-reachability walk, BOM-aware, all four
dynamic-edge families re-verified by hand at HEAD: sector_router `_ORCHESTRATORS`/`_WEIGHT_MODULES`,
unified_analyst `SECTOR_SPECS`, base_orchestrator settings import, core_adapter tier=core) +
targeted importer greps + git history + Railway deploy-log search. Census at HEAD:
**LIVE 281 files / 42.6K LOC · DARK 15 / 3.2K (manual CLIs + api_exploration) ·
DEAD 524 / 20.9K.** Both big dead trees are byte-stable since Phase 1 (253/9,941 and
183/8,259) — Wave 1 resurrected nothing.

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-078 | GAP | P1 | `requirements.txt` + `services/data/fetchers/nse_market.py:72-75` | **`nsepython` is imported by two LIVE fetchers but has NEVER been in requirements.txt** (git log -S: no hit; `pyproject.toml` declares NO `[project.dependencies]`; Dockerfile installs requirements.txt only) → in prod, every context build takes the ImportError branch: FII/DII flows, bulk deals, upcoming earnings (nse_events) and MF-herding context are **structurally empty in every analyst prompt and daily review since first deploy** (8 live call sites: builder.py ×5, bundle_builder.py ×2, daily_review.py:725). Silent divergence never caught because the gitignored local `.stockai` venv HAS nsepython 2.97 installed — it "works" in dev, empty in prod ("[nse_market] nsepython not installed" warning, empty string into prompts). The design treats institutional flow as a decision signal; prod has never seen it | ph6; requirements.txt; pyproject.toml; Dockerfile:15-16; nse_market.py:72-75; mf_herding guard :210; `.stockai/…/nsepython-2.97.dist-info` | FIX (decide with AUD-059: EITHER add `nsepython` to requirements — one line, activates dormant features — OR delete the nsepython paths and port FII/DII to the `nse` package; adding the dep is effort-trivial) — optional pre-Monday hotfix, USER call | FIXED (Wave C 2026-07-17: `nsepython>=2.90` declared + regression test; watch next trading day's prompts/brief for populated FII/DII + Overnight lines) |
| AUD-079 | DEAD | P3 | `core/graphs/` | 4 files / 12 LOC of migration shims re-exporting `backend.shared.pipeline.graphs` (which is LIVE); zero importers of the shim side | ph6 census | DELETE | OPEN (Wave 2) |
| AUD-080 | DEAD | P3 | namespace/shim residue across `src/backend/` | `src/backend/api/` is now just 2 empty `__init__`s (AUD-028's tree already shrunk — resolves that row); `src/backend/scheduler/` 2 empty; `src/backend/intelligence/` 23 empty `__init__`s (restructure skeleton, zero code); `src/backend/shared/` dead subset 10 files/309 LOC: 2-LOC re-export shims with no importers (clients/alerting, clients/tavily_fetcher, data/cache/macro_cache, data/fetchers/{fundamentals,macro,news}, data/stores/score_store) + `config/rag_config.py` (67) + `prompts/feedback_agent.py` (227, superseded by core/config/prompts/shared/feedback_agent.py) + `core/config/rag_config.py` 3-LOC shim | ph6 census | DELETE (~37 files / ~312 LOC, mostly zero-LOC) | OPEN (Wave 2) |
| AUD-081 | OVERENG | P2 | `tests/unit/` root vs subdirs | **7 test files exist in TWO collected copies** (pre-restructure root + post-restructure subdir): test_config, test_enhancer, test_prompts, test_regime, test_schemas, test_seasonal, test_signal_aggregator (~1,666 duplicated test lines). Actively double-maintained: both test_config copies edited 2026-07-02; test_enhancer copies have DIVERGED (root 2026-05-31/321L vs subdir 2026-05-12/329L — a fix landed in one copy only). Doubles suite time for these modules and guarantees rot | ph6 (md5 + git dates) | FIX (diff each pair, merge newest into the subdir copy, delete root copy) | OPEN (Wave 2) |
| AUD-082 | LOWIMPACT | P3 | `requirements.txt` | Comment/constraint rot: duplicate constraint pairs (`openai>=1.30.0` AND `openai==2.32.0`; `yfinance>=0.2.40` AND `yfinance==1.3.0`), comments referencing deleted layers ("consumed by TypeScript + C#", "C# Quartz.NET is primary" — python scheduler is the ONLY scheduler), langgraph comment pointing at the dead shim dir | ph6 | FIX (one cleanup commit; joins AUD-011 polish batch) | OPEN (polish) |
| AUD-083 | OVERENG | P2 | `src/backend/shared/config/settings/base.py` | Config god-object: 857 LOC, 25 residual `getenv` sites despite "config.yaml sole source" doctrine; every module imports the whole surface | ph6; MAP §4 | Split proposal in Ph9 (by domain: llm/, data/, portfolio/, delivery/) — design debt, not a wave-2 deletion | OPEN (Ph9) |

**Updates to seeded/earlier rows (Phase 6 verification at HEAD 13ca54a):**

- AUD-026 — confirmed + fully quantified: `core/sectors/` = 253 files / 9,941 LOC, all DEAD.
  Composition: 19 codegen skeletons (~501 LOC each) + banking 413 + renewable 463 +
  automobile 44 (12 shim files re-exporting backend agents) + it 3 (2 shims). Only
  consumer remains `core_adapter` (142 LOC) whose tier=core branch requires a sector
  with `enabled:true, tier:core` — config/sector_toggles.json ships all 19 as
  `enabled:false`. **New risk note: Wave 1's AUD-040 fix ships the toggles file into the
  image, so a config-only flip can now actually activate a CoreSectorAdapter in prod
  (8 LLM calls/analysis through 2024-era skeleton prompts) — before Wave 1 the file never
  loaded and the branch was doubly dead.** The promotion path is superseded by the
  generic sector graph (Compass Phase B): sector_router routes non-native sectors to
  GenericSectorOrchestrator; SectorRegistry's core tier is a second, INCONSISTENT
  promotion path (registry degrades disabled→automobile; router uses generic).
  DELETE proposal: core/sectors tree + core_adapter.py + registry tier=core branch +
  generate_sector_skeletons.py (AUD-029, 1,013 LOC) = **255 files / ~11.1K LOC**;
  re-point 2 test files (tests/unit/test_agents_unit.py, tests/contract/
  test_phase0_llm_migration.py import automobile agents via the dead shims —
  redirect to backend.sectors.automobile). USER-DECISION: forfeits the core-tier
  promotion path (generic graph covers the need).
- AUD-027 — quantified: `src/frontend/web/` = 27 files / 1,180 LOC (excl. package-lock).
  Not in the image; prototypes are the real UI. DELETE.
- AUD-028 — **RESOLVED (already gone at HEAD)**: `src/backend/api/` now contains only
  2 empty `__init__.py` files; the route files were deleted in an earlier restructure.
  Residue folded into AUD-080.
- AUD-029 — confirmed 1,013 LOC; rides the AUD-026 deletion (it is the skeleton generator).
- AUD-031 — confirmed zero importers (`user_profile` grep: none outside the file).
  The chat-side tests/unit/intelligence/chat/test_user_profile.py tests a DIFFERENT
  module — unaffected. DELETE (58 LOC).
- AUD-032 — confirmed + made precise: DEAD subset = **183 files / 8,259 LOC** = 20 fully-dead
  sector prompt dirs (~9 files/~400 LOC each; renewable 703, banking 396) + shared/
  orchestrator.py (57) + shared/signal_aggregator.py (3) + automobile/valuation_catalyst.py
  (3). **NOT deletable wholesale: `core/config/prompts/shared/` has 7 LIVE files (627 LOC)
  imported by six RL agents (control_lane:28, preopen_check:40, feedback_agent:51,
  event_ingestor:22, dossier_curator:20, question_researcher:25), and
  `core/config/prompts/automobile/` has 9 LIVE 3-LOC shims imported from base_agent.py:415
  + services/data/context/builder.py ×7.** Cleanest cut: re-point those 8 automobile import
  sites to backend.sectors.automobile.prompts (the shim targets), keep shared/, delete the
  rest (then 192 files / ~8.3K LOC).
- AUD-033 — re-censused at HEAD: dead subset = 40 files / 1,800 LOC (Phase 1's 53/1,460
  counted empty `__init__`s now rolled into AUD-080; LOC method = raw lines). The 5 latent
  prompt files (banking institutional 76 + pattern_analysis 71, it_sector
  insider_smart_money 77 + pattern_analysis 71, renewable technical 43 = 338 LOC) —
  **decision brought forward from skipped Ph5: DELETE all 5**; they are editable via the
  prompts hot-deploy route but consumed by nothing (per-dimension agents dead) — a
  phantom edit surface that silently discards edits.
- AUD-034 — confirmed: only importer of services/clients/alerting.py is the DEAD 2-line
  shim src/backend/shared/clients/alerting.py. DELETE both (198 LOC); prune the alerting
  tests inside tests/contract/test_scheduler.py (:150,204-222 — tests of an orphan).
- AUD-035 — DELETE hardened: `ingest_cli.py:114` contains a **syntax error**
  (`from core.intelligence.rag import config as rag_config as rc`) — the file has never
  been importable since that line was written; py_compile fails at HEAD. ingestion.py
  is valid but unreachable. tests/integration/test_rag.py imports ingestion helpers
  (_chunk_text/_doc_id ×5 sites) — those tests go with it. retriever/vector_store stay
  (LIVE).
- AUD-037 — confirmed unchanged: 7 spikes / 1,505 LOC shipped in the image via
  `COPY scripts/`. DELETE (or move out of image); nse_insider_scraper.py also imports
  nsepython (consistent with AUD-078 — it was a local-only experiment).
- AUD-040 — (FIXED in Wave 1) follow-on risk recorded under AUD-026: shipping the
  toggles file makes accidental core-tier activation a live config surface.
- AUD-055 — not an over-engineering item; re-parked to remediation wave assignment in
  Ph9 (unknown-symbol resolver guard).
- AUD-059 — REFRAMED by AUD-078: there is no "second NSE client" in prod — nsepython
  was never installed. The consolidation decision collapses into AUD-078's either/or.
- AUD-072 — confirmed; harness.py:18-30 itself documents the real-data ablation no-op.
  Action refined: KEEP harness + synthetic generator; stop emitting `ablation_deltas`
  for real-data runs (or annotate "synthetic-only") so the scorecard can't render
  circular numbers.
- AUD-073 — quantified: factor_regime.py = 263 LOC, 3 LIVE importers (weight_adapter,
  daily_review, context builder). FIX-or-DELETE unchanged — lands in Wave 4 next to
  AUD-066 (it feeds agent-leniency into the same weight loop); `verify=False` fix is
  immediate-wave material.

**Program-question verdicts (named suspects closed out):**
typescript/ wrapper + C# scheduler — already deleted (April), nothing at HEAD ·
dual sync/async dispatch — **KEEP, not dual**: one chain; `analyse()` is a sync wrapper
over `analyse_async` and is the entry used by ALL callers (daily_review:224,
generate_forecast:276, deep_dive:125, scheduler:942, main:189) ·
duplicate API layers — resolved (AUD-028: already reduced to empty residue) ·
`core/graphs` — DELETE (AUD-079) · fno / seasonal / prompt_enhancer — **KEEP, all LIVE**
(generate_forecast:32-33,363-364; daily_review:61; month_end_validation:50; note test
duplication in AUD-081) · config surface — one source confirmed; god-object split =
AUD-083 (Ph9).

**Wave 2 deletion docket (proposal — nothing deleted this session):**

| Target | Files | LOC | Rider actions |
|--------|------:|----:|---------------|
| core/sectors + core_adapter + tier=core branch + skeleton codegen (026/029) | 255 | 11,096 | re-point 2 test files; USER sign-off on promotion path |
| core/config/prompts dead subset (032) | 183 | 8,259 | re-point 8 automobile-shim imports → +9 shim files/25 LOC deletable |
| src/backend/sectors dead subset incl. 5 latent prompts (033) | 40 | 1,800 | AUD-022 stale-mock cleanup rides along |
| scripts/api_exploration in-image spikes (037) | 7 | 1,505 | or relocate out of COPY set |
| src/frontend/web stub (027) | 27 | 1,180 | non-Python |
| rag/ingestion incl. syntax-broken CLI (035) | 3 | 304 | prune test_rag ingestion tests |
| services/clients/alerting + shim (034) | 2 | 198 | prune test_scheduler alerting tests |
| services/api/user_profile.py (031) | 1 | 58 | — |
| core/graphs shims (079) | 4 | 12 | — |
| namespace/shim residue (080, incl. old 028) | 37 | 312 | — |
| **Total prod code** | **559** | **~24,724** | **≈37% of shipped LOC** |
| duplicate test copies (081) | 7 | ~1,666 | merge-then-delete, not blind delete |

Prod-trace note (protocol step 2): Railway deploy-log search for "nsepython" in the
current deployment (0a2b1057, live since 06:10 UTC today) — no hits, as expected: no
context-building job has run on it yet; older deployments are REMOVED (logs gone). The
structural chain (requirements.txt → Dockerfile → ImportError guard) is conclusive
without the log line; if AUD-078 stays unfixed, expect the warning in Monday's
16:30 IST review logs.

**Component verdicts (Phase 6 protocol step 5):**
`core/sectors/*` DELETE (026) · `core_adapter.py` DELETE with it ·
`generate_sector_skeletons.py` DELETE (029) · `core/config/prompts/{20 dirs}` DELETE,
`shared/` KEEP-LIVE, `automobile/` re-point-then-DELETE (032) · `src/backend/api|scheduler|
intelligence` residue DELETE (080) · `src/frontend/web` DELETE (027) ·
`scripts/api_exploration` DELETE-from-image (037) · `rag/ingestion` DELETE (035) ·
`services/clients/alerting.py` DELETE (034) · `user_profile.py` DELETE (031) ·
`core/graphs` DELETE (079) · `nse_market.py`/`mf_herding.py` KEEP+FIX-dep (078) ·
`base_orchestrator` sync/async KEEP · `fno`/`seasonal`/`prompt_enhancer` KEEP (live) ·
`settings/base.py` KEEP now, split in Ph9 (083) · `eval/harness.py` KEEP+flag (072) ·
`factor_regime.py` FIX-or-DELETE in W4 (073) · duplicate test copies MERGE+DELETE (081).

## Phase 7 — Reliability / ops / security (2026-07-16, HEAD 4eda774)

`ph7` = full read of scheduler.py, core/delivery/* (alerts, ops_alerts, channels),
llm_client, pipeline.py step wiring, server.py lifespan/lock; retry-pattern grep across
services/data (zero hits); contract+integration suite re-run at HEAD. `plog7` = prod
deploy logs for deployment faccdf0b (live 2026-07-12 17:12 UTC → today, spans the first
three scheduled autopilot days Mon 7/13–Wed 7/15) + read-only API probes 2026-07-16.

**Prod trace headline — Wave 1 WORKS, but day 2 of 3 was lost silently.**
(All figures = the VIRTUAL paper portfolio.) Mon 7/13: review 16:30 IST → pipeline
17:07 → **first-ever auto-trades: 7 (3 EXITs RBLBANK/OLAELEC/KPITTECH + 4 ADD
tranches), ledger cash-chain continuous, realized_pnl 0.0 is CORRECT** (seeded 7/11 at
7/10 closes; EXITs executed at the same 7/10 closes — zero P&L by construction).
Wed 7/15: 1 ADD (TVSMOTOR), cooldown correctly blocked a second INOXWIND ADD.
Tue 7/14: **NO pipeline, no trades, no digest, no value point, no alert** — see
AUD-084. Paper equity −0.68% on 2 value points.

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-084 | BUG | P1 | `services/scheduler/python/scheduler.py:509-534` | **One slow review day silently kills the whole trading day.** Docstring promises a 3-min per-ticker timeout, but `future.result(timeout=180)` never blocks (as_completed yields finished futures) — the only real cap is the AGGREGATE `as_completed(timeout=180×N)`; with RL_SCHEDULER_MAX_WORKERS=1 the loop is serial, so mean review >180s guarantees a tail TimeoutError; that TimeoutError is UNCAUGHT (inner except guards result(), not the generator) → skips the zero-output alert AND the run_post_review_pipeline hook. Same loss-class: a Railway deploy landing 16:30–17:10 IST kills the job with no resumption. Prod: Tue 2026-07-14 "TimeoutError: 3 (of 16) futures unfinished" at 17:21 IST — 13 reviews saved, 0 trades, value_history gap, zero alerts (partial ≠ produced==0) | plog7 traceback; scheduler.py | FIX (catch TimeoutError around harvest; run pipeline regardless of stragglers — reviews are per-ticker persisted; budget 300s/ticker or workers>1; optional APScheduler error-listener → ops alert) — **hotfix candidate, USER call** | FIXED (Wave A 2026-07-16: harvest TimeoutError contained — stragglers logged, zero/partial alerts + pipeline always run; budget 300s/ticker; shutdown(wait=False, cancel_futures=True); EVENT_JOB_ERROR listener → job_crashed ops alert) |
| AUD-085 | GAP | P1 | delivery transport (channels.py + prod state) | **Every prod delivery lands nowhere: `push=0 email=0` on ALL sends all 4 days** (morning briefs, Monday's 7-trade digest + escalations, lock-in expiries). VAPID keys ARE configured (live /delivery/push/public-key returns a key) → cause = ZERO push subscriptions ever registered (🔔 Enable-alerts never tapped on the deployed PWA); email fallback default-disabled. The whole Wave-1 AUD-039 alert stack (LLM-streak, zero-output, quarantine, reconcile-drift) has no working transport. Design flaw compounding it: emit_alerts appends the sent-log BEFORE delivery outcome (alerts.py:107-119) → date\|kind dedupe suppresses a same-day resend even after the user subscribes; send_push returns 0 with no log when unconfigured/no-subs | plog7 (8× push=0 email=0); live probe | **USER ACTION: tap 🔔 on the PWA (and/or set SMTP_* + delivery.email_enabled)**; FIX (WARNING log on 0-subscription send; only sent-log after ≥1 channel delivers, or record delivered=false) | FIXED (transport: email live+verified 2026-07-16; Wave A code riders: sent-log written AFTER outcome w/ delivered flag — delivered=false records don't dedupe so same-day retry works, zero-subscription WARNING, deliver landed-nowhere WARNING, dead subs pruned on 400/403 too) |
| AUD-086 | BUG | P2 | `core/intelligence/rl/stores/offmarket_fetcher.py` | Off-market context structurally empty every ticker/day: "nse package unavailable: NSE.__init__() missing 1 required positional argument: 'download_folder'" — the nse package IS installed; the CONSTRUCTOR CALL is wrong (other callers pass a download folder, AUD-017 family). Mislabeled as missing-dep so it reads like AUD-078; fires ~16×/day in prod | plog7 (every review) | FIX (pass download_folder=mkdtemp-shared dir; effort trivial) — joins AUD-078's "context silently empty" wave | FIXED (Wave C 2026-07-17: download_folder passed in offmarket_fetcher AND core/intelligence/fno/fetcher.py — FnOFetcher had the identical defect, found during the wave) |
| AUD-087 | GAP | P2 | `src/backend/shared/pipeline/base_orchestrator.py:154,214` | Run-level cost telemetry is fiction: both dispatch paths hardcode `total_prompt_tokens=0, total_completion_tokens=0, total_cost_usd=0.0` into every run summary (prod: "Run … tokens=0 cost=$0.0000") while real usage lands only in per-call telemetry.db rows — the $19–25/mo burn vs the key monthly limit (AUD-042a residual trap) is unmonitorable from run logs | plog7; code | FIX (sum agent-call usage into the summary; feeds deferred Ph5 cost audit) | FIXED (2026-07-16 wave: AgentOutput usage fields + `sum_run_usage()`; run_id now passed to UnifiedAnalyst.run too) |
| AUD-088 | GAP | P2 | volume backup story | **No backup/export mechanism exists anywhere** for data/ — portfolio.json, transactions.jsonl (now holding real trade history), value_history, predictions tree, telemetry.db live solely on the single Railway volume; repo grep: zero backup scripts; no scheduled export job | ph7 grep; MAP | FIX (nightly ledger export job → private repo/object storage; at minimum enable+document Railway volume backups) | FIXED (2026-07-17 Wave D — scheduler Job 15 daily 23:30 IST: `services/data/backup.py` zips all non-rebuildable data/ state (caches excluded), SQLite via the backup API, 7-copy local rotation under data/backups/, archive emailed off-site through the live SMTP transport when ≤20MB; no off-site copy → WARNING) |
| AUD-089 | LOWIMPACT | P3 | `core/portfolio/autopilot.record_value_point` + /performance | Equity curve boundary quirks: Monday's value point (review_date 7/10) predates the 7/11 seed point and was silently skipped → the first real trading day is absent from the curve; `day_change_pct` is labeled per-day but computed across multi-day gaps (−0.685% spans 7/11→7/14) | probe (/portfolio/performance: 2 points) | FIX (record at execution-date or allow ordered backdate-insert; label change as period_change) | OPEN (polish) |
| AUD-090 | GAP | P3 | observability polish batch | (a) reconcile logs nothing on a clean pass — "ran clean" indistinguishable from "didn't run"; (b) alert_job_zero_output only fires at produced==0 — 13/16 partial is invisible; (c) send_push silent at 0 recipients; (d) run_now/scheduler status has no last-run-outcome surface | ph7 | FIX (one INFO/WARNING line each; fold into AUD-084/085 wave commit) | PARTIAL (Wave A 2026-07-16: (a) reconcile clean INFO, (b) job_partial_output alert, (c) zero-recipient WARNING done; (d) last-run-outcome surface on scheduler status → Wave F) |
| AUD-091 | PATTERN | P3 | fetcher layer (services/data/*) | Zero retry/backoff anywhere in the data layer (grep: no hits) — every NSE/yfinance/Serper fetch is single-attempt try/except-degrade; one transient blip at 16:30 = context holes or skipped holdings (close_on raise → holding unadvised that day). House degrade-gracefully style is otherwise right for daily cadence | ph7 grep; 2026-07-11 yfinance "Invalid Crumb" day | KEEP overall; targeted FIX: one 2-attempt retry on the money-path close_on + get_price_history only | OPEN (polish) |

**Updates to earlier rows (Phase 7 verification):**

- AUD-012 — evidence re-presented per hold: posture unchanged at HEAD, re-verified
  by read-only probe 2026-07-16 (specifics withheld from this public doc — recorded
  in the private session notes). The endpoints now guard live trade history, not
  just seed state. Status ON-HOLD (user 2026-07-10) unchanged — re-decide in Ph9.
- AUD-013 — pinned alerts.py:107 (plain append, no rotation) + `_seen_keys` re-reads
  the WHOLE file per emit. Actual growth ~10 lines/day → **downgrade P2→P3**, fold
  into delivery wave.
- AUD-015 — pinned: ops_alerts._emit and pipeline emits pass no/default user_id;
  single-real-user today → P3 in practice, unchanged action.
- AUD-019 — unchanged (USER-DECISION); reader torn-line tolerance verified
  (alerts.py:56-60 json-per-line try/except).
- AUD-022 — re-measured at HEAD: **9 failed + 10 errors = 19**, identical two stale-mock
  roots (AutomobileAgentOrchestrator patch targets in test_phase0_llm_migration/
  test_orchestrator; SignalAggregator/WS mocks in test_phase2_api); 221 pass alongside.
  One cleanup ticket, count stable since seed.
- AUD-036 — unchanged: RL_DESIGN.md still carries 4 stale `scripts.daily_review` /
  `scripts.generate_forecast` run instructions.
- AUD-039 — Wave-1 hooks verified wired (llm-streak + zero-output) BUT effectiveness = 0
  until AUD-085 lands a transport; coverage hole = AUD-084's crash class skips the hook.
- AUD-041 — prod-reconfirmed at HEAD: TATAELXSI "last 48h context" carried a 2026-04-22
  article on 7/14 (P1-candidate upgrade evidence unchanged).
- AUD-050 — FIXED verified in prod code path (409 quarantine handler at server.py:405);
  no quarantine event has occurred in prod.
- AUD-057 — scope widened: data/ops_alerts_state.json joins the non-atomic
  write_text set (streak counter RMW from every LLM call site across 2 workers +
  scheduler thread).
- AUD-060/066 — live evidence: WeightAdapter logs "hits=7/7" for ALL 8 agents with
  uniformly positive Δ on both observed days (NEUTRAL free-pass inflation visible in
  prod exactly as predicted).
- AUD-078 — prod-confirmed live: "[nse_market] nsepython not installed — context will
  be empty" at 16:30:1x IST on 7/13, 7/14, 7/15. Still a one-line fix, still unshipped.
- Error-handling taxonomy verdict: house pattern (per-step try/except-log-continue,
  "non-fatal by construction") is RIGHT for this system and consistently applied; its
  two systemic holes are exactly AUD-084 (exceptions that escape the pattern kill whole
  chains) and AUD-085 (the only human-facing failure channel has no recipients).

**Component verdicts (Phase 7 protocol step 5):**
`scheduler.py` jobs KEEP+FIX (084 harvest/timeout; else clean taxonomy) ·
`ops_alerts.py` KEEP+FIX (085 rider, 057 atomicity) · `alerts.py` KEEP+FIX (sent-log
ordering, 013 P3) · `channels.py` KEEP+FIX (silent-zero logging) · `llm_client.py` KEEP
(SDK default 2-retry is adequate; salvage util solid) · `pipeline.py` step wiring KEEP
(clean-pass logging only) · server.py lifespan/singleton lock KEEP (port-bind lock
verified working in prod all week) · fetcher resilience KEEP+targeted-retry (091).

## Phase 5 — LLM usage / cost, slice 1: call-site inventory (2026-07-16, HEAD 0da0dca)

Method: enumerated EVERY production `chat.completions.create` — 23 call sites across
17 files (tests and `scripts/reasoning_bench.py` excluded). Tier resolution per
`src/backend/shared/config/settings/base.py:31-37` + `config.yaml`: FAST =
qwen/qwen3.6-flash, REASONING = z-ai/glm-5.2, BULK = deepseek/deepseek-v4-flash;
back-compat alias `LLM_MODEL` → BULK (base.py:35). `LLM_TEMPERATURE`=0.2,
`LLM_MAX_TOKENS`=2048, `UNIFIED_ANALYST_MAX_TOKENS`=6000.

| # | Call site | Model (tier) | max_tok | temp | json_object | reasoning-off | telemetry |
|---|-----------|--------------|---------|------|-------------|---------------|-----------|
| 1 | `core/delivery/weekly.py:71` (weekly narrate) | BULK | 300 | 0.2 | ✓ | ✓ | ✓ |
| 2 | `core/delivery/brief.py:123` (brief narrate) | BULK | 300 | 0.2 | ✓ | ✓ | ✓ |
| 3 | `core/portfolio/narrator.py:70` (advice narrate) | BULK | 300 | 0.2 | ✓ | ✓ | ✓ |
| 4 | `services/background/macro_news_fetcher.py:337` (review agent) | LLM_MODEL→BULK | 1500 | 0.0 | ✓ | ✓ | ✗ |
| 5 | `services/api/routes/ui_data.py:2915` (chat tool loop, non-stream) | FAST | 600 | 0.4 | n/a (tools) | ✗ | ✗ |
| 6 | `ui_data.py:2948` (chat synthesis, non-stream) | FAST | 600 | 0.4 | n/a | ✗ | ✗ |
| 7 | `ui_data.py:3258` (stream tool loop, via `_chat_completion:3006`) | FAST, fb→REASONING | 700 | 0.4 | n/a (tools) | ✗ | ✗ |
| 8 | `ui_data.py:3299` (stream synthesis) | FAST, fb→REASONING | 700 | 0.4 | n/a | ✗ | ✗ |
| 9 | `core/intelligence/rl/workflows/preopen_check.py:66` | FAST | 300 | 0.2 | ✓ | ✓ | ✗ |
| 10 | `src/backend/shared/pipeline/unified_analyst.py:441` (LIVE analyst) | REASONING | 6000 | 0.2 | ✓ | ✓ | ✓ |
| 11 | `signal_aggregator.py:224` (legacy-fallback verdict) | REASONING | 2048 | 0.2 | ✓ | ✓ | usage→instance var only |
| 12–13 | `base_agent.py:213,271` (legacy-fallback agents, sync+async) | LLM_MODEL→BULK | 2048 | 0.2 | ✓ | ✓ | usage→instance var only |
| 14 | `base_orchestrator.py:372` (ticker resolve) | LLM_MODEL→BULK | 256 | 0.0 | ✓ | ✓ | ✓ |
| 15 | `graphs/nodes.py:69` (resolve — legacy DAG) | LLM_MODEL→BULK | 128 | 0.0 | ✓ | ✓ | ✓ |
| 16–17 | `graphs/nodes.py:340,376` (aggregation — legacy DAG) | LLM_MODEL→BULK | 512 | 0.1 | ✓ | ✓ | ✓ |
| 18 | `rl/agents/control_lane.py:48` | CONTROL_LANE_MODEL(∅)→REASONING | 300 | 0.2 | ✓ | ✓ | ✗ |
| 19 | `rl/agents/thesis_reviewer.py:223` | REASONING | 300 | 0.1 | ✓ | ✓ | ✗ |
| 20 | `rl/agents/feedback_agent.py:229` | REASONING | 4000 | 0.3 | ✓ | ✓ | ✓ |
| 21 | `rl/agents/question_researcher.py:136` | LLM_MODEL→BULK | 900 | 0.2 | ✓ | ✓ | ✗ |
| 22 | `rl/agents/event_ingestor.py:176` | LLM_MODEL→BULK | 900 | 0.2 | ✓ | ✓ | ✗ |
| 23 | `rl/agents/dossier_curator.py:152` | LLM_MODEL→BULK | 900 | 0.2 | ✓ | ✓ | ✗ |
| 24 | `rl/algorithms/price_interpolator.py:383` | LLM_MODEL→BULK | 180 | 0.2 | ✓ | ✓ | ✗ |
| 25 | `core/intelligence/prompt_enhancer/enhancer.py:426` | LLM_MODEL→BULK | 120 | 0.1 | ✓ | ✓ | ✗ |

(#12–13 and #16–17 share one parameter block each; 23 distinct `create()` calls.)

**What's healthy:** the JSON_MODE_EXTRA_BODY hardening rule holds at 100% — all 19
`response_format=json_object` sites pass reasoning-off. Tier placement is broadly
right: the two verdict paths (unified analyst, aggregator) on REASONING, narration
and the RL knowledge layer on BULK, chat on FAST. Temperatures are all in the sane
0.0–0.4 band, lowest where determinism matters (resolve 0.0, thesis 0.1). The
feedback 4000-token headroom is deliberate and documented (truncation-poisoning
guard). Note on caps: with reasoning disabled, max_tokens is a safety bound, not a
spend driver — you only pay for emitted tokens — so the cost levers below are tier
and reasoning-off, not cap-lowering.

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-092 | COST | P2 | `services/api/routes/ui_data.py:2915,2948,3258,3299` | Chat is the ONLY surface that never disables reasoning: all 4 free-text chat calls omit the reasoning-off extra_body while the code itself strips `<think>` blocks from the output (`_strip_think` at :3302) — on thinking-by-default snapshots (exactly the 2026-07 incident class; FAST=qwen3.6-flash was one of the rolled models) the 600/700-token completion cap is burned on reasoning that is then discarded, and a long think can eat the whole cap leaving an empty visible answer | code read (no extra_body on any chat call; `_strip_think` present) | FIX (pass `extra_body={"reasoning": {"enabled": False}}` on all 4 chat calls — orthogonal to tools/response_format; keep `_strip_think` as belt-and-braces) | FIXED (2026-07-16 wave) |
| AUD-093 | GAP | P2 | 13 of 23 call sites | Cost telemetry coverage is partial — extends AUD-087: chat (4 sites), preopen_check, control_lane, thesis_reviewer, question_researcher, event_ingestor, dossier_curator, price_interpolator, enhancer, macro reviewer never call `record_llm_call`/`log_llm_call`, so the RL knowledge layer (runs per-ticker daily) and the whole chat surface are invisible in telemetry.db; signal_aggregator/base_agent capture usage only into instance vars that AUD-087's hardcoded-zero summary then drops | grep record_llm_call/log_llm_call across call-site files | FIX (add `record_llm_call` at the 13 sites — it already never-raises by design; unlocks the deferred spend-vs-key-limit check) | FIXED (2026-07-16 wave) |
| AUD-094 | COST | P3 | `ui_data.py:2979-2982,2995-3013` | Chat fallback chain escalates to the DEAREST tier: docstring says "fall back to a lighter model" but the chain is FAST→REASONING (glm-5.2), and the config-import except-branch hardcodes retired `qwen/qwen3.7-max` (:2982) — under a sustained 429/5xx storm every chat message pays 3 backoff retries then lands on the priciest model; separately the non-stream endpoint (:2915) bypasses `_chat_completion` entirely (no retry, no fallback) — two chat paths, two resilience behaviours | code read | FIX (fall back to BULK deepseek or fix the docstring to say "escalate"; update stale :2982 literal; route :2915/:2948 through `_chat_completion`) | FIXED (2026-07-16 wave; escalation kept by design, docstring corrected) |
| AUD-095 | DEAD | P3 | `graphs/nodes.py:69,340,376` + 16 `core/sectors/*/graph.py` | Legacy LangGraph DAG duplicates resolver+aggregation with a tier twin-drift: its final verdict aggregation runs on LLM_MODEL→BULK while both live verdict paths (unified_analyst, signal_aggregator fallback) use REASONING; scheduler/services never import the graph path (only the 16 sector `graph.py` shells do — Wave-2 shadow-tree candidates) | grep imports; scheduler grep = 0 hits | CONFIRM dead → fold into Wave-2 deletion docket (AUD-025 family); if any sector graph IS reachable its verdict silently runs on deepseek | OPEN (Wave-2) |
| AUD-096 | PATTERN | P3 | `base.py:35` + 12 call sites | Back-compat catch-all `LLM_MODEL` still read by 12 production call sites (nodes ×3, base_agent ×2, base_orchestrator, macro, question_researcher, event_ingestor, dossier_curator, price_interpolator, enhancer) — tier choice at those sites is an implicit default, not a decision; worse, the alias is `os.getenv`-only (no `cfg()`), so it bypasses the config.yaml precedence that is supposed to be the single source of truth | base.py:35; grep LLM_MODEL | FIX (mechanical: s/settings.LLM_MODEL/settings.LLM_MODEL_BULK/ at all 12 sites, delete the alias) | FIXED (2026-07-16 wave) |
| AUD-097 | PATTERN | P3 | `price_interpolator.py:373-377`, `enhancer.py:421-425` | Two sites construct inline `OpenAI(...)` clients instead of `get_llm_client()` — the factory docstring's "single place to swap provider/model" is false; any future base-url/timeout/provider change silently misses these two (both also in the AUD-093 unlogged set) | code read | FIX (use the factory; 2-line change each) | FIXED (2026-07-16 wave; widened — third bypass found+fixed in `thesis_reviewer.__init__`) |
| AUD-098 | COST | P3 | `thesis_reviewer.py:224`, `control_lane.py:47-48` | Down-tier candidates: two tiny bounded-JSON judgments (300-token cap, temp 0.1/0.2, output = bool+multiplier / direction+confidence) run per-ticker daily on REASONING (glm-5.2 $0.686/$2.156) where BULK (deepseek $0.09/$0.18) benches 100% JSON-reliable — ~90% unit-cost cut on the two highest-frequency REASONING jobs; `CONTROL_LANE_MODEL` yaml knob already exists for a zero-code A/B | tier table above; llm-tiers memory bench data | EVALUATE (bench rule applies: live json_object smoke via reasoning_bench.py before any swap; control-lane decision AFTER AUD-060/077 RL-semantics verdict — don't retune a metric under audit) | OPEN (Ph5, USER-DECISION) |

**Not flagged (checked and fine):** macro reviewer 1500 cap (~200-400-token payload,
headroom documented) · unified analyst 6000 cap on REASONING — it is the dominant
spend by construction (16 tickers/day × biggest prompt) but that's the product's
core call; right tier, right cap · resolve calls at 0.0 temp with 128/256 caps ·
narration trio on BULK at 300 · preopen on FAST. Quantifying actual $/day per
caller stays blocked on AUD-087/093 telemetry — that's the remaining Phase 5 slice
(pull telemetry.db once coverage lands).

**Wave — LLM cost/telemetry SHIPPED (2026-07-16, branch audit-llm-cost-wave):**
plan `docs/superpowers/plans/2026-07-16-audit-llm-cost-wave.md`; TDD, 4 commits.
FIXED: AUD-087 (AgentOutput usage fields excluded from reports + module-level
`sum_run_usage()` in base_orchestrator; resolve usage captured per-run; unified
path stamps its single call's totals once; bonus — run_id was silently dropped
on the UnifiedAnalyst.run call, now passed), AUD-092 (`_chat_completion` defaults
`extra_body` to reasoning-off), AUD-093 (telemetry coverage now 23/23 — chat
records per attempt inside `_chat_completion`; 9 RL/background sites use a
uniform nested-try record pattern; callers: ui_chat, preopen_check, control_lane,
thesis_reviewer, question_researcher, event_ingestor, dossier_curator,
price_interpolator, prompt_enhancer, macro_reviewer), AUD-094 (non-stream chat
routed through `_chat_completion`; stale `qwen/qwen3.7-max` fallback literal →
`z-ai/glm-5.2`; docstring now says ESCALATE — escalation kept by design),
AUD-096 (alias deleted from base.py; all call sites explicit `LLM_MODEL_BULK`;
3 test files updated incl. both AUD-081 duplicate `test_config.py` copies),
AUD-097 (3 factory bypasses fixed — price_interpolator, enhancer, plus
thesis_reviewer.__init__ found during implementation). New tests:
`test_chat_llm_hardening.py` (5), `test_run_usage_totals.py` (3),
`test_llm_telemetry_coverage.py` (8). NOT touched: AUD-095 (Wave-2 deletion
docket), AUD-098 (bench-gated user decision). Suite: no new failures vs
baseline 10F/10E/2150P/12S (pre-existing = AUD-022 stale-mock family + 1
event_ingestor date test). Phase 5 slice 2 ($/caller from telemetry.db) is now
UNBLOCKED once this deploy accumulates a few days of prod rows.

## Phase 8 — API / UI / chat surface (2026-07-16, HEAD 524af78)

`ph8` = full read of services/api/server.py + all 10 routers (analyse, history,
stream, ui_data, scheduler_api, prompts, analytics, portfolio_api, discovery_api,
delivery_api); route-decorator census (75 paths incl. SPA catch-all); frontend
fetch/EventSource/WebSocket inventory across src/frontend/prototypes/*.jsx matched
against the route contracts; error-path grep (`detail=str(exc)` / `f"…{exc}"` sites);
chat call-count from static read of `chat()` + `chat_stream()` + `_chat_completion()`
retry chain; latency from telemetry.db instrumented rows (chat's own `ui_chat` rows
are still 0 — that surface only runs in prod and AUD-093 telemetry just shipped, so
latency is proxied from the models chat calls).

**Census headline — the surface is broad (75 routes) and the request/response
contracts are consistent and largely well-validated (portfolio + agents/weights are
exemplary: sector/qty/date/weight-sum all checked, domain errors → 422 with actionable
messages). Two structural gaps dominate: the `/ui/prompts/*` and `/ui/*` mutation
families carry NO auth at all (not even the optional `X-Scheduler-Key` gate the
portfolio/discovery/delivery/scheduler routers use), and the RL Monitor page calls
five routes that don't exist — silently masked by the SPA catch-all. Error handling is
correct at the front door (`/analyse` logs the traceback and returns a generic 503) but
leaks `str(exc)` on the sibling paths (`/ws/stream`, the chat brief tool, prompts 500s).**

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-099 | SEC | P1 | `services/api/routes/prompts.py` (all 6 routes) | **Unauthenticated prompt read/write/deploy that writes attacker-controlled text into an imported `.py` module.** No `_check_auth` on any `/ui/prompts/*` route (the only router with zero auth gate); PUT `/ui/prompts/{sector}/{agent}` writes `body.system_prompt`/`analysis_prompt` into the agent prompt file via `_safe_triple_quote` — which escapes only `"""` and NOT a trailing backslash, so a payload ending in `\` escapes the closing delimiter and breaks out of the string literal in a file that is then `importlib.import_module`-ed and hot-patched into live modules; POST `/ui/prompts/deploy` then git-pushes with the repo's `GITHUB_TOKEN`. Internet-reachable on the public Railway host | ph8 (prompts.py:490-535 no auth; `_safe_triple_quote`:169-172 backslash gap; `_write_prompt_file`→import at 541-547) | FIX (add `_check_auth` to all prompt routes — same gate as scheduler_api; replace `_safe_triple_quote` with `repr()`-style literal encoding or write prompts as data not code; gate `/deploy` behind the key). Joins the AUD-012 auth-lockdown decision | FIXED (2026-07-16 Wave B — all 6 routes gated + `_py_string_literal` unbreakable encoder; enforcement live once SCHEDULER_KEY is set in Railway) |
| AUD-100 | CONTRACT | P2 | `src/frontend/prototypes/rl-data.jsx:182,199-202` vs router | **Five phantom routes: the RL Monitor page shows fabricated data as real, permanently.** `rl-data.jsx`/`rl-monitor.jsx` fetch `/ui/rl/tickers`, `/ui/rl/summary/{t}`, `/ui/rl/predictions/{t}`, `/ui/rl/weights/{t}`, `/ui/rl/misses/{t}` — none are defined server-side (grep = 0). The SPA catch-all (`server.py:467`) returns `index.html` with HTTP 200 for the unmatched paths, so `res.ok` is TRUE, `res.json()` throws on the HTML, the `catch{}` swallows it, and the page silently keeps its mock `RL_TICKERS`. The real RL state IS exposed — under `/scheduler/status` and `/analytics/*` — just never wired to this page | ph8 (5 fetches, 0 matching routes; catch-all fallthrough) | FIX (either implement the 5 `/ui/rl/*` routes as thin adapters over PredictionStore/`/scheduler/status`, or repoint the page at the existing `/scheduler/status` + `/analytics/weight-drift`/`miss-breakdown`; at minimum make the catch-all 404 unknown `/ui/*` + `/api/*` paths instead of serving index.html so contract drift fails loudly) | FIXED (Wave C 2026-07-17: BOTH halves — 5 real `/ui/rl/*` adapter routes over PredictionStore (`rl_monitor.py`, managed-list-gated so unknown symbols 404 without the AUD-024 mkdir side effect), page treats mocks as demo-only once the API answers, AND the catch-all now 404s unknown API-namespace paths) |
| AUD-101 | PERF | P2 | `ui_data.py` `chat()`:2915-2955, `chat_stream()`:3276-3321, `_chat_completion()`:3011-3032 | **Chat fan-out: 1–5 sequential LLM calls per turn, each expandable to 6 upstream attempts.** A turn runs up to `_CHAT_MAX_TOOL_ROUNDS`=4 tool rounds + 1 forced synthesis = up to 5 logical LLM calls, ALL sequential (tools within a round run concurrently, rounds do not). Each logical call goes through `_chat_completion`, which on transient 429/5xx retries 3× with 0.8/1.6/3.2s backoff across 2 models (FAST→REASONING escalation) = up to 6 upstream completions per logical call. Worst case per single user message ≈ 30 upstream completions + ~56s of pure backoff sleep, and every retry escalates onto the DEAREST tier (glm-5.2 — compounds AUD-094). Measured proxy latency (telemetry, instrumented rows): median LLM call ~1–3s, p90 up to ~17s → a 1-round answer ~2–4s; a 4-round loop 10–20s nominal, 60s+ under upstream stress | ph8 static trace; telemetry.db latency by model (glm-5.2 median 960ms/p90 17.2s, deepseek-flash median 3.2s) | FIX (cap the retry×model product for the interactive path — chat is latency-bound, prefer fail-fast + honest "retry" over 56s of silent backoff; consider a per-turn wall-clock budget; the escalation-on-stress is AUD-094's cost lever). Re-measure with real `ui_chat` rows once prod accumulates them | FIXED (2026-07-17 Wave D — retries 3→2 per model (≤4 upstream/logical call, was 6); 45s wall-clock budget per turn on BOTH chat routes: backoff sleeps never run past the deadline (fail fast → honest "retry shortly" text), tool rounds stop when the budget is spent, and ONE final no-tools synthesis is always allowed so a long turn still ends grounded, not mocked) |
| AUD-102 | GAP | P2 | `ui_data.py` all `/ui/*` write routes | **Unauthenticated mutation of the RL-scheduling surface, with a whole-list clobber path.** PUT `/ui/tickers/managed` (replace entire list), POST/DELETE/PATCH `/ui/tickers/managed/{sym}`, PUT `/ui/agents/weights`, PUT `/ui/agents/tasks`, PUT `/ui/watchlist`, PUT `/ui/categories/{key}/tickers` all lack any auth gate. PUT `/ui/tickers/managed` accepts `list[_ManagedTickerBody]` where `sym` defaults to `""` and is never validated non-empty — a garbage or empty-sym list silently replaces the managed-ticker list that drives RL scheduling AND (via `_generate_envelope_for_new_ticker`) triggers the ~2-min 9-agent LLM pipeline per added symbol. Unauth spend + scheduling-state amplification vector | ph8 (replace_managed_tickers:3395 no `sym` guard, no `_check_auth`; envelope side effect 3407-3428) | FIX (add the shared auth gate to `/ui/*` writes; reject empty/whitespace `sym`; rate-limit or gate the envelope-generation side effect). Folds into the AUD-012/099 auth-lockdown decision | FIXED (2026-07-16 Wave B — 9 mutation routes gated + empty/whitespace `sym` rejected; enforcement live once SCHEDULER_KEY is set) |
| AUD-103 | SEC | P3 | `stream.py:68`, `ui_data.py:2668`, `prompts.py:500,502,522,535` | **Raw `str(exc)` leaks on the paths that mirror `/analyse`'s hardened one.** `/analyse` is the correct template — logs the traceback server-side, returns a generic 503. But the WebSocket `/ws/stream` sends `{"event":"error","detail":str(exc)}` for the SAME pipeline; `_chat_tool_portfolio_brief` returns `f"Brief unavailable: {exc}"` into the model's tool context (this is seeded AUD-014, still live); and prompts 500s return `str(exc)`/`f"…{exc}"` (import errors, filesystem paths). Low attacker value but an inconsistent, information-disclosing contract | ph8 grep + read | FIX (mirror the `/analyse` pattern: log server-side, return generic client text; sanitize the brief tool). Supersedes+absorbs AUD-014 | FIXED (2026-07-16 Wave B — /ws/stream + chat brief + prompts 500s now log server-side, return generic text; prompt PUT no longer returns the server fs path) |
| AUD-104 | PATTERN | P3 | `ui_data.py` `chat()`:2896 vs `chat_stream()`:3222 | **Two chat endpoints, two conversation-memory models.** POST `/ui/chat` trusts a CLIENT-supplied `history` array (`body["history"]`, last 8, role-filtered to user/assistant) — the client controls the model's memory and can inject arbitrary prior turns. POST `/ui/chat/stream` uses server-side in-process `_SESSION_HISTORY` (last 12, keyed by `session_id`). Divergent truncation windows (8 vs 12) and trust boundaries for the same product feature; the non-stream path is a minor prompt-injection surface (bounded by the role filter) | ph8 read | FIX (converge on the server-side session store for both; if client history is kept, treat it as untrusted context not conversation state) | OPEN (Ph9) |

**Updates to seeded Phase 8 rows (verified at HEAD 524af78):**

- AUD-008 — CONFIRMED live: `/portfolio/performance` still does the legacy per-holding
  live-mark (`close_on` in a loop) only on the empty-history branch (portfolio_api.py:358-367);
  normal path reads `value_history`. Cost is now bounded (fires only right after opt-in or a
  history gap). Unchanged action, still P3.
- AUD-014 — CONFIRMED live at ui_data.py:2668 (`return f"Brief unavailable: {exc}"`).
  **Absorbed into AUD-103** (same leak taxonomy); track/fix there.
- AUD-018 — **RESOLVED at HEAD.** `get_portfolio_brief` IS now a registered chat tool
  (`_CHAT_TOOLS` at ui_data.py:2165, dispatched at :2701) — the model can discover and call
  it. The seeded "tool absent" defect no longer holds. Mark FIXED (verify: chat can answer
  portfolio questions via the tool loop).

**Not flagged (checked and fine):** request/response shapes are consistent JSON dicts;
FastAPI+Pydantic validation is correct and often exemplary (`update_agent_weights`
range+sum checks, `add_holding` sector/date/price validation, `Query(ge=…, le=…)` bounds
on every `limit`/pagination param, `rl-export?format=` regex-pinned); the QuarantinedPortfolio
409 handler (server.py:405) is the right shape; `/analyse` error handling is the model to
copy; the `/ws/stream` 150s aggregate timeout + task-cancel-on-disconnect is sound. **CORS
note (not a separate row):** `allow_origins=["*"]` + `allow_credentials=True` (server.py:394)
is a contradictory combo browsers reject and a smell to fix when auth lands — harmless today
only because no route reads cookies. Fold into the auth-lockdown wave.

**Component verdicts (Phase 8 protocol step 5):**
`analyse.py` KEEP (reference error-handling) · `history.py` KEEP · `stream.py` KEEP+FIX
(103 leak) · `portfolio_api.py` KEEP (exemplary validation+locking; auth deferred per user) ·
`delivery_api.py` KEEP · `discovery_api.py` KEEP · `scheduler_api.py` KEEP · `analytics.py`
KEEP (read-only, well-bounded) · `prompts.py` FIX (099 auth+code-write — highest-severity
row this phase) · `ui_data.py` KEEP+FIX (100 phantom routes, 101 chat fan-out, 102 unauth
writes, 103/104 chat debt) · `server.py` KEEP+FIX (catch-all should 404 unknown API paths;
CORS combo).

## Phase 9 — Improvement backlog prioritization (2026-07-16)

Consolidated ranking of every OPEN finding across all phases into execution waves.
Ordering key: prod-impact-now > correctness/security > cost > polish; within a wave,
cheapest-first. `USER-DECISION` items are called out — they gate on a policy choice
(auth lockdown, tier retune), not on engineering.

**Wave A — URGENT prod (ship next; live paper-portfolio is affected today):**
1. AUD-084 (P1) — uncaught scheduler TimeoutError silently kills a trading day (lost Tue 7/14).
   Catch around the harvest; run the pipeline regardless of stragglers. HOTFIX.
2. AUD-085 (P1) — all prod alerts land nowhere (0 push subs + email off). Needs the user
   action (tap 🔔 / set SMTP) PLUS the code rider (WARNING on 0-recipient send; sent-log
   only after ≥1 channel delivers). HOTFIX + USER ACTION.
   → these two are the reliability/observability blind spot; everything else can wait behind them.

**Wave B — Security / auth lockdown (one coherent decision, USER-DECISION):**
3. AUD-099 (P1) — unauth prompt write→imported `.py` + token-backed git push. Highest new severity.
4. AUD-102 (P2) — unauth `/ui/*` mutations + empty-`sym` whole-list clobber of the scheduling surface.
5. AUD-012 (P1, ON-HOLD) — push-subscribe auth-bypass; re-decide now.
6. CORS `*`+credentials cleanup (rides along).
   → all four resolve together the moment the user lifts the 2026-07-06 "virtual money, lockdown
   deferred" hold. Recommend lifting it: real trade history now lives behind these endpoints.

**Wave C — Correctness / context (cheap, high-signal):**
7. AUD-086 (P2) — off-market NSE() ctor bug, fires ~16×/day; trivial fix, joins AUD-078.
8. AUD-078 (P1) — nsepython missing, context silently empty; one-line, prod-confirmed daily.
9. AUD-100 (P2) — phantom `/ui/rl/*`; wire the page to existing data + make catch-all 404 unknown APIs.
10. AUD-103 (P3, absorbs AUD-014) — sanitize the three `str(exc)` leak sites to the `/analyse` pattern.

**Wave D — Cost / LLM (Phase 5 slice 2 gated on prod telemetry):**
11. AUD-101 (P2) — chat retry×model fan-out; cap the interactive path, add a per-turn budget.
12. AUD-098 (P3, USER-DECISION) — down-tier thesis_reviewer/control_lane to BULK; bench-gated.
13. AUD-088 (P2) — no volume backup for data/; nightly ledger export. (Ops, not LLM, but Ph9 wave.)
14. Phase 5 slice 2 — pull $/caller from telemetry.db once a few prod days accumulate (now unblocked).

**Wave E — Dead code / structure (Wave-2 deletion docket):**
15. AUD-095 / AUD-025 family (P3) — legacy LangGraph DAG + shadow tree, 559 files/~24.7K LOC.
    Confirm-dead then delete in one sweep.

**Wave F — Polish (fold into whichever wave touches the file):**
16. AUD-104 (P3) chat memory convergence · AUD-089/090 (P3) equity-curve + observability lines ·
    AUD-091 (P3) targeted close_on retry · AUD-013/015/057 (P3) alert-log rotation/atomicity/user_id ·
    AUD-036 (P3) stale RL_DESIGN run docs · AUD-008 (P3) /performance live-mark.

**RL-semantics gate (blocks parts of D):** AUD-060/066/077 (NEUTRAL free-pass weight
inflation, RL reward semantics) are under audit — do NOT retune any tier/metric that
depends on them (esp. AUD-098's control-lane A/B) until that verdict lands.

**Suite baseline unchanged this phase** (read-only audit, no code touched): 10F/10E/2150P/12S,
same AUD-022 stale-mock family + 1 event_ingestor date test as prior phases.

## Phase 5 — LLM usage / cost, slice 2: spend quantification (2026-07-16, HEAD 524af78)

`ph5b` = read of the cost-computation path (all 8 `LLM_INPUT/OUTPUT_COST_PER_M` sites),
config.yaml tier+rate block, `record_llm_call`/`log_llm_call`, base_orchestrator unified
dispatch, daily_review LLM caller set; measured per-call token magnitudes pulled from
`data/telemetry.db` (`llm_calls`, 394 instrumented rows, span 2026-07-02…07-16). Prod
telemetry for the NEW callers (AUD-093 coverage shipped today) has not accumulated yet —
Railway MCP token unauthorized, CLI Bash-gated — so magnitudes come from the real rows
that exist and cadence from config + the code path. The empirical prod pull stays a
follow-up (query below), but the cost MODEL and the systemic finding are complete now.

**Headline — the cost telemetry AUD-087 just made non-zero is still systematically wrong
(low) for the calls that dominate spend, because the rate is tier-blind. Every cost site
uses the single flat `input=0.09 / output=0.18` (deepseek BULK) rate regardless of the
model actually called, so every REASONING-tier call — unified_analyst (the dominant
call), FeedbackAgent, aggregation, thesis_reviewer, macro_reviewer, control_lane — is
undercosted ~7.6× on input and ~12× on output. Measured: a real unified_analyst call is
7,440 in / 2,957 out → $0.0115 tier-correct (glm-5.2 $0.686/$2.156) but is LOGGED at
$0.0012 (9.6× undercount). Separately, the actual spend is small: recurring scheduled LLM
cost is ≈ $2/mo tier-correct, comfortably under the $19–25/mo cap (AUD-042a residual). The
cap exposure is entirely on-demand chat + UI `/analyse`, amplified by AUD-101's retry
fan-out — that is the only path that can approach the cap, and it is exactly the path the
broken telemetry cannot see accurately.**

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-105 | COST | P2 | `unified_analyst.py:357`, `signal_aggregator.py:162`, `base_orchestrator.py:84,412,516`, `base_agent.py:119,163`, `graphs/nodes.py:83,401` — all via `settings.LLM_INPUT/OUTPUT_COST_PER_M` | **Tier-blind flat cost rate — the cost telemetry undercounts REASONING calls ~8–12×.** All 9 cost-computation sites multiply tokens by the SAME flat `input_cost_per_m=0.09 / output_cost_per_m=0.18` (config.yaml:37 — "default to the BULK tier") regardless of the model each call actually uses. deepseek BULK sites are correct; glm-5.2 REASONING sites (unified_analyst, aggregation, FeedbackAgent, thesis_reviewer, macro_reviewer, control_lane) are costed at 7.6× too low on input ($0.686 vs 0.09) and 12.0× too low on output ($2.156 vs 0.18). This is exactly the AUD-042a "spend vs key monthly limit" figure everyone will read off the run summaries — now non-zero (AUD-087) but ~10× understated for the dominant caller. Measured unified_analyst call: $0.0115 real vs $0.0012 logged. Units are consistent (all sites `/1_000_000`; no 1e6 bug) — the defect is purely the rate | ph5b (grep of the 9 sites all on one flat rate; config.yaml:36-38; measured tokens from telemetry.db) | FIX (per-model rate table keyed on the `model` string already passed to `log_llm_call` — e.g. `{glm-5.2:(0.686,2.156), deepseek-v4-flash:(0.09,0.18), qwen3.6-flash:(…)}`; the tier is known at every call site. Cheap, unblocks a trustworthy $/mo vs cap number) | FIXED (2026-07-17 Wave D — `llm.cost_rates` per-model table in config.yaml + `settings.llm_cost_usd()`; all 9 sites swapped; `sum_run_usage` costs resolve@BULK + aggregator@REASONING separately. NB live OpenRouter prices 2026-07-17: glm-5.2 REPRICED upstream to 1.218/3.828 per M (was 0.686/2.156 at the 2026-07-03 bench, ~1.8×) — scheduled recurring spend estimate rises to ≈$3.3–3.6/mo, still far under the cap) |

**Spend model (tier-correct, per-call cost from measured token medians):**

| Caller | Tier / model | in→out tok (measured) | $/call (tier-correct) | $/call (as-logged, flat) |
|--------|--------------|-----------------------|-----------------------|--------------------------|
| unified_analyst | REASONING glm-5.2 | 7,440 → 2,957 | **$0.01148** | $0.00120 (9.6× low) |
| aggregation (legacy path) | REASONING glm-5.2 | 2,566 → 1,276 | $0.00451 | $0.00046 |
| FeedbackAgent | REASONING glm-5.2 | 1,420 → 380 | $0.00179 | $0.00020 |
| thesis_reviewer | REASONING glm-5.2 | 474 → 96 | $0.00053 | $0.00006 |
| portfolio_narrator | BULK deepseek | 100 → 50 | $0.00002 | $0.00002 (correct) |

**Monthly spend estimate (16 managed tickers, ~22 trading days), tier-correct:**
- Monthly forecast (1st): 16 × unified_analyst ≈ **$0.18/mo** (once).
- Daily review (weekdays): per ticker ≈ FeedbackAgent $0.0018 + thesis_reviewer $0.0005 +
  control_lane ~$0.0004 + RL knowledge layer (question_researcher/event_ingestor/dossier_curator,
  BULK 900-cap, ~$0.0006 total) + price_interpolator re-forecast (BULK, ~$0.0002) ≈ $0.0031;
  × 16 × 22 ≈ **$1.09/mo**; + macro_reviewer (REASONING, once/day) ~$0.05/mo. Daily review does
  NOT re-run the analyst — the Living-Envelope re-forecast is price_interpolator (BULK), verified.
- Weekly discovery deep-dive: `deep_dive_count=10` unified calls/wk × $0.0115 × 4.3 ≈ **$0.49/mo**.
- Narration + preopen: negligible (< $0.02/mo).
- **Scheduled recurring total ≈ $1.8–2.0/mo tier-correct** (≈ $0.20/mo as the flat-rate
  telemetry would report). Far under the $19–25/mo cap.
- **On-demand (uncapped, the real variable):** UI `/analyse` = $0.0115/call; chat = 1–5
  REASONING/FAST calls/turn (AUD-101), a heavy tool-loop turn up to ~$0.05. Reaching the cap
  needs roughly ~1,700 `/analyse` calls or ~400 heavy chat turns per month. The historical
  $19–25/mo figure predates the glm-5.2 + unified-analyst consolidation (8 calls → 1) and is
  almost certainly stale on the high side.

**Two remaining Phase 5 questions — both CLOSED here (no new rows needed):**
- **8-agent ensemble value ("do all 8 agents earn their calls?") — RESOLVED by architecture,
  not cost.** The live path is a SINGLE `UnifiedAnalyst` call (`base_orchestrator._run_unified`,
  all 4 live sectors), not 8 per-agent calls. The completed unified migration already collapsed
  the ensemble 8→1; the 8 separate `base_agent` calls survive only in the dead/fallback legacy
  worker pool (AUD-095 family). Nothing to prune — the expensive version is already off the live path.
- **LLM-where-code-suffices sweep — clean.** `ticker_resolution` (the one that looked suspect) is
  gated behind an exact-match managed-ticker lookup and only calls the LLM for unknown free-text
  symbols (genuinely fuzzy NSE-name resolution) — right call. The chat pre-router
  (`_detect_invest_intent`), table flattener, and answer sanitizer are already deterministic code
  (a prior good decision). No LLM-for-deterministic-work found worth a row.

**Empirical follow-up (unblocked, needs a few prod days of rows).** Do NOT trust any stored
`cost_usd` until AUD-105 lands — recompute from tokens × the correct per-model rate:
```sql
-- against the prod data/telemetry.db once ui_chat + RL-layer rows accumulate
SELECT substr(caller,1,20) AS caller, COUNT(*) n,
       SUM(input_tokens)  in_tok, SUM(output_tokens) out_tok,
       SUM( CASE WHEN model='z-ai/glm-5.2'
                 THEN input_tokens*0.686/1e6 + output_tokens*2.156/1e6
                 WHEN model='deepseek/deepseek-v4-flash'
                 THEN input_tokens*0.09/1e6  + output_tokens*0.18/1e6
                 ELSE input_tokens*0.30/1e6  + output_tokens*0.50/1e6  -- FAST/other, adjust
            END ) AS usd_tier_correct
FROM llm_calls WHERE success=1 AND input_tokens>0
GROUP BY 1 ORDER BY usd_tier_correct DESC;
```

**Component verdict (Phase 5 slice 2):** cost-computation path KEEP+FIX (AUD-105 rate table) ·
tier placement + reasoning-off + telemetry coverage all verified sound (slice 1 + the shipped
wave) · ensemble economics already optimal on the live path · no code-suffices offenders.
**Phase 5 COMPLETE** (slice 1 inventory + shipped cost/telemetry wave + slice 2 quantification);
the only residual is the empirical prod pull above, which is data-time-gated, not analysis-gated.

## Wave B — API security lockdown SHIPPED (2026-07-16, branch audit-wave-b-security)

Plan `docs/superpowers/plans/2026-07-16-audit-wave-b-security.md`; TDD, 8 code commits.
FIXED: **AUD-099** (shared `check_scheduler_key` gate — new `services/api/auth.py` — on all
6 `/ui/prompts/*` routes; `_safe_triple_quote` → `_py_string_literal` that escapes backslash
THEN quote, closing the trailing-`\`/trailing-`"` breakout — verified by an ast-parse +
exec round-trip test over 5 injection payloads), **AUD-102** (same gate on all 9 `/ui/*`
mutation routes — agents/weights, agents/tasks, watchlist, categories, the 5 managed-ticker
verbs; `replace_managed_tickers` now rejects empty/whitespace `sym` before it can clobber the
scheduling list), **AUD-012** (push subscribe hardened: https-only endpoint + per-user 50-sub
cap; POST/DELETE stay keyless BY DESIGN — the pre-login 🔔 flow and AUD-085 recovery depend on
it, rationale in the plan), **AUD-103** (+**AUD-014**: `/ws/stream`, chat portfolio-brief tool,
and prompts 500s now log server-side with `exc_info` and return generic client text — the
`/analyse` pattern; prompt PUT response no longer leaks the server filesystem path), plus the
CORS `*`+`allow_credentials=True` contradiction dropped to `False`. The 4 pre-existing
`_check_auth` copies (portfolio/delivery/discovery/scheduler) now delegate to the shared helper
— behaviour identical. **Enforcement is DORMANT until the user sets `SCHEDULER_KEY` in Railway**
(same optional-gate semantics as before — zero prod behaviour change on deploy); the prototype
PWA got a global fetch wrapper that attaches `X-Scheduler-Key` from `localStorage` and prompts
once on a 403, so flipping the key won't brick the UI. New tests: `test_api_auth_lockdown.py`
(7), `test_prompt_file_encoding.py` (5 params), `test_delivery_api.py` push-hardening (2),
`test_api_routes.py` ws-leak (1). NOT touched: AUD-100/101/104 (correctness/perf — different
waves). **USER ACTION to activate: add `SCHEDULER_KEY=<strong random>` to Railway Variables;
after redeploy the PWA prompts for it once on the first gated action.**

## Incident — test suite sent real alert emails (2026-07-16 23:14 IST; fixed 2026-07-17, 9f13a5f)

Operator received two `[ALERT] portfolio.json for user 'u9'/'u1' was corrupt and
quarantined` emails. **Prod was untouched** — the Railway volume holds only the
primary user, no quarantine files, portfolio intact (verified read-only over ssh).
Root cause: the AUD-050 quarantine unit tests use fixture users u1/u9 and drive
`PortfolioStore.load()` → `_alert_quarantine` → `emit_alerts` with REAL transports;
once live SMTP creds landed in the developer `.env` (AUD-085 transport work, same
day), every local pytest run could email real alerts and append fixture records
(u1/u9/t1) to the repo's real `data/delivery/alerts_sent.jsonl`. The 5s gap between
the two emails = sequential SMTP sends between tests; the 23:14 IST timestamp = the
Wave A post-merge verification run.

| ID | Tag | Sev | Where | Defect | Evidence | Action | Status |
|----|-----|-----|-------|--------|----------|--------|--------|
| AUD-106 | BUG | P2 | `tests/conftest.py` (was: nothing isolating delivery) | Unit tests exercised live delivery transports + the repo's real sent-log; any machine with delivery configured emails real alerts on every pytest run and pollutes dedupe state | operator emails 2026-07-16; `data/delivery/alerts_sent.jsonl` fixture records; prod volume clean | FIX (autouse `_no_real_deliveries` fixture: forces `DELIVERY_EMAIL_ENABLED`/`DELIVERY_PUSH_ENABLED` off + redirects default sent-log to tmp_path per test; explicit `sent_log=` honored; regression tests `test_delivery_test_isolation.py`; `DELIVERY_PUSH_ENABLED` config assert → type assert, same class as 6620cdb) | FIXED (9f13a5f) |

Suite after fix: 1962 passed / 5 skipped / 1 failed = the known pre-existing
`test_find_qualifying_events_unparseable_date_skipped` (fails at clean HEAD).
Residual: `data/delivery/alerts_sent.jsonl` still carries the 4 junk fixture lines
(local-only dedupe records for nonexistent users — safe to delete by hand).

## Wave C — context & contract correctness SHIPPED (2026-07-17, branch audit-wave-c)

Plan `docs/superpowers/plans/2026-07-17-audit-wave-c-context-contract.md`; TDD in worktree,
6 code commits. FIXED: **AUD-078** (`nsepython>=2.90` declared — FII/DII flows, bulk deals,
earnings calendar and MF-herding context stop being structurally empty in prod; pulls scipy,
accepted), **AUD-086** (`NSE(download_folder=…)` in offmarket_fetcher AND FnOFetcher — the
F&O copy of the same bare-`NSE()` defect was found during the wave; "nse package unavailable"
mislabel gone), **AUD-100** (both halves: five real `/ui/rl/*` GET adapters over
PredictionStore in `services/api/routes/rl_monitor.py`, shapes matching the page's existing
contract, ticker param validated against the managed list BEFORE store construction so
unknown symbols 404 with zero mkdir side effect (AUD-024 class); `rl-data.jsx`/`rl-monitor.jsx`
now treat mocks as demo-only once the API answers — live-empty tickers show the real empty
state; SPA catch-all 404s unknown paths under ui/ api/ scheduler/ analytics/ portfolio/
discovery/ delivery/ history/ ws/ analyse so the phantom-route class fails loudly forever;
sw.js cache v3→v4). New tests: `test_requirements_deps.py` (2), `test_nse_ctor_fetchers.py`
(2), `test_rl_monitor_api.py` (7), `test_spa_catchall.py` (3 — RL adapter stubbed to avoid
real-data-dir mkdir). Suite in worktree: 2 known failures only (worktree-absent data/ harness
test + pre-existing event_ingestor date test); one transient `test_manual_add_records_txn_and_capital`
failure did not reproduce on two follow-up full runs and passes in isolation — watch, not chased.
Local smoke: tickers/summary 200 JSON, unknown API paths 404, root + static 200.
POST-DEPLOY: verify `/ui/rl/tickers` JSON + a 404 probe in prod; next trading-day review
(~16:35 IST) should log no "nsepython not installed" / "nse package unavailable" lines; next
morning brief should render populated Overnight lines.

## Wave D — cost / resilience SHIPPED (2026-07-17, branch audit-wave-d)

Plan `docs/superpowers/plans/2026-07-17-audit-wave-d-cost-resilience.md`; TDD in worktree.
FIXED: **AUD-105** (per-model `llm.cost_rates` table + `settings.llm_cost_usd()`, all 9 cost
sites tier-correct; `sum_run_usage` splits resolve@BULK vs aggregator@REASONING; discovery
during the wave: OpenRouter REPRICED glm-5.2 to 1.218/3.828 per M — ~1.8× the 2026-07-03
bench rates — so the slice-2 spend model's scheduled total rises to ≈$3.3–3.6/mo, still far
under the cap; deepseek 0.098/0.196, qwen3.6-flash 0.1875/1.125 recorded from the live
models endpoint), **AUD-101** (`_chat_completion` retries 3→2 per model ⇒ ≤4 upstream
attempts per logical call; new `deadline=` honored before every backoff sleep; both chat
routes set a 45s per-turn wall-clock budget, stop tool rounds once it is spent, and always
allow one final deadline-free no-tools synthesis — worst case drops from ~30 completions +
~56s pure sleep to ≤~9 completions bounded by the budget), **AUD-088** (new
`services/data/backup.py` + scheduler Job 15 daily 23:30 IST: zips every non-rebuildable
data/ file — portfolio, predictions, delivery, user_profiles, discovery, top-level json,
telemetry.db/scores.db via the SQLite backup API (explicit close: the ctx-manager-only
version held the file lock on Windows) — excludes market_cache/tavily_cache/nse/macro_news/
eval/backups; 7-copy local rotation guards corruption, the emailed archive (≤20MB cap,
multipart attachment support added to `send_email`) is the off-site copy guarding volume
loss; archive-creation failures raise into the EVENT_JOB_ERROR alert listener, missing
off-site copy only WARNs). New tests: test_llm_cost.py (6), test_chat_turn_budget.py (6),
test_delivery_channels_attachments.py (3), test_backup.py (5), scheduler job tests (2).
NOT in this wave: AUD-098 tier retune stays bench-gated on the RL-semantics verdict
(060/066/077); the empirical telemetry $ pull stays data-gated — run the slice-2 SQL against
prod telemetry.db from ~2026-07-21 (a few trading days of the new caller rows), recomputing
from tokens × `llm.cost_rates`; cost_usd stored AFTER this deploy is trustworthy as-is.
POST-DEPLOY: startup log shows "[Scheduler] Backup job: daily at 11:30 pm IST"; first
backup email lands ~23:30 IST tonight; data/backups/ starts rotating on the volume.
