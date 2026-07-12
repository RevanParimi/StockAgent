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
