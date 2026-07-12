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
