# StockAgent architecture, as trees

The walkthrough of 22 Nov 2026 (checked against the code at `62580ab`), the architecture map's
phases, and where the work stands on 26 Nov 2026.

How to read: `├──` is a step or a branch, `─►` means "leads to", `(M5)` means "see module 5".
Production values are as of 22 Nov 2026 (source: KT section 1 of docs/TECHNICAL_DESIGN.md).
Since then, on 23 Nov, **PR-015 switched the exit rule to `evidence`**: from that day's 16:30
review, `case_broken` decides sales instead of `thesis_break` (M5.2, M5.5).

Contents: Part 0 (the product, the flow, the code, the clock) · M1 to M12 · Finale (one stock's
life) · Notes from our discussion · The architecture map's phases · Where we are.

---

# Part 0: Start here

## 0.1 The product in one tree

```
StockAgent: an autonomous research-and-trading agent for NSE stocks, on paper money
│
├── M1  Platform ......... boots the app, owns the clock (25 jobs), config, storage
├── M2  Data ............. prices, filings, news ─► one checked bundle per stock
├── M3  Research ......... one stock ─► a verdict, STRONG BUY ... STRONG SELL
├── M4  Learning ......... 30-day forecast each month, daily grading, lessons, regime
├── M5  Portfolio ........ advisor rules ─► virtual trades ─► profit and loss
├── M6  Discovery ........ weekly hunt for new ideas ─► "the shelf"
├── M7  Company events ... filings and news per stock, typed and dated
├── M8  IPO .............. IPO calendar, order book, research, verdict (mostly dark)
├── M9  Delivery ......... morning brief, weekly review, alerts ─► push and email
├── M10 Interface ........ API routes, login, PWA screens, chat assistant
├── M11 Measurement ...... grades every call against the Nifty
└── M12 Operations ....... watchdog, error backlog, ops alerts, backups
```

## 0.2 How the modules feed each other

```
   M2 Data ──────────► M3 Research ◄────────── M6 Discovery (deep dives call M3)
                          │                          │
                          ▼                          ▼
                   M4 Learning                  the shelf (ideas)
             (envelope, daily grade)                 │
                          │                          │
                          └────────► M5 Portfolio ◄──┘
                                    advisor + autopilot
                    M7 Events ────►     │   (evidence for exits, case pillars)
                                        ▼
                                   M9 Delivery ──► the user (push, email, inbox)

   M10 reads every store, and the chat can call M3 on demand
   M11 grades the outputs of M3, M5 and M6;  M12 watches every job
```

## 0.3 Where the code lives

```
StockAgent/
├── services/                 the runtime shell
│   ├── api/                  FastAPI app (server.py), auth.py, routes/ (14 routers)
│   ├── scheduler/python/     scheduler.py: every timed job
│   ├── data/                 fetchers/ (yfinance, NSE, news...), stores/ (SQLite, parquet),
│   │                         context/bundle_builder.py, verdict_store.py, backup
│   ├── clients/              llm_client.py (OpenRouter), tavily_fetcher.py
│   └── background/           macro news cache
├── src/backend/              the research engine
│   ├── shared/pipeline/      orchestrator, unified analyst, aggregator, decision gate
│   ├── shared/config/        settings (the real one; core/config is a shim to it)
│   └── sectors/              registry + 5 paths: automobile, banking_bfsi, it_sector,
│                             renewable_energy, generic
├── src/frontend/prototypes/  the PWA (JSX turned into JS in the browser, no build step)
├── core/                     the product logic
│   ├── intelligence/         learning loop (rl/), regime, seasonal, indicators, F&O
│   ├── portfolio/            advisor, autopilot, sizing, costs, cases, results
│   ├── discovery/            screen, deep dive, shelf, candidates, paper lane
│   ├── events/  ipo/         company events; IPO research and verdict
│   ├── delivery/             brief, weekly review, alerts, channels, outbox
│   ├── audit/                nightly grader
│   └── ops/                  watchdog, error backlog
├── config.yaml               every tunable value and switch
├── config/                   instruments.yaml, sector_toggles.json, milestones.yaml
└── data/                     (Railway volume) all state: JSON, JSONL, parquet, SQLite
```

## 0.4 One day on the clock (IST)

```
Daily (weekdays unless marked)
06:30  ops_watchdog (every day) ...... M12  milestones + invariants ─► owner
07:30  macro_daily_news .............. M2   policy and RBI headlines cached
08:00  ipo_refresh_am (every day) .... M8
08:15  company_events_am ............. M7
08:45  preopen_shock_check ........... M4   1 search + 1 LLM call: overnight shock?
08:50  morning_brief ................. M9
09:00 / 12:00 / 15:00  macro_market_news  M2
15:30  ── NSE closes ──
16:30  rl_daily_review ............... M4   grades the PREVIOUS session (T-1)
         └─► post-review pipeline .... M5   advice ─► trades at T-1's close ─► alerts
17:45  ipo_refresh_pm (every day) .... M8
18:30  company_events_pm ............. M7
19:00  bhavcopy_daily_sync ........... M2   NSE end-of-day file for all stocks
19:00  ipo_deep_dive (every day) ..... M8
23:00 / 23:15 / 23:20  atlas jobs .... M1   universe, cost per user, retention
23:30  data_backup_nightly ........... M12
23:45  audit_nightly ................. M11

Weekly
Mon 03:30  ledger_cleanup_weekly ..... M4   old lessons cleaned
Sat 10:00  event_ingest_weekly ....... M4   results and concalls into the dossier
Sat 11:00  research_loop_weekly ...... M4   answer the dossier's open questions
Sat 12:30  discovery_weekly .......... M6
Sun 18:00  weekly_review + index watch M9

Monthly and yearly
1st 02:00  scorecard_monthly ......... M11
1st 09:00  rl_monthly_forecast ....... M4   a new 30-day envelope per stock
Dec 31 23:00  rl_calendar_update ..... M1   next year's NSE holidays
```

The most useful timing fact: the 16:30 job on day T reviews session T-1 and books every trade at
T-1's 15:30 close. Nothing the system decides reads anything published after that close.

---

# M1: Platform and runtime

```
M1 Platform
├── 1.1 Boot ............ services/api/server.py
├── 1.2 Scheduler ....... services/scheduler/python/scheduler.py
├── 1.3 Config .......... config.yaml + src/backend/shared/config/settings/
├── 1.4 Storage ......... data/ on the Railway volume
└── 1.5 LLM access ...... services/clients/llm_client.py
```

### 1.1 Boot

```
Docker starts uvicorn with 2 workers ── each worker runs lifespan()
│
├── every worker
│   ├── logging: console, plus WARNING+ kept forever in data/telemetry.db
│   ├── self-checks in the log: volume mounted? managed_tickers.json? API counter?
│   └── NSE holiday file has this year? ── no ─► fetch it (hardcoded list as fallback)
│
└── try to bind 127.0.0.1:59321 (the singleton lock)
    ├── got it = PRIMARY worker
    │   ├── thread "RL self-heal" (starts after 10 s)
    │   │   └── for each managed stock, in its own sector
    │   │       ├── already done this month (checkpoint file)? ─► skip
    │   │       ├── no envelope this month? ─► generate_forecast (M4.1)
    │   │       │     └── fails ─► skip this stock; the next deploy retries it
    │   │       └── trading days without a review? ─► run_daily_review for each
    │   ├── start the scheduler (1.2)
    │   ├── sweep expired chat sessions and login sessions
    │   └── start the outbox drainer (M9.5)
    └── lost it = API-only worker: serves requests, runs no jobs
    Why: before this lock every job ran twice (2x LLM cost, racing file writes).
```

### 1.2 Scheduler

```
Registration (APScheduler, timezone Asia/Kolkata)
├── always: daily review, monthly forecast, calendar, ledger cleanup, pre-open check,
│           backup, 3 atlas jobs
├── only when the flag is on
│   ├── macro_news.enabled ─► 2 macro news jobs
│   ├── scorecard / event ingest / research loop flags ─► those jobs
│   ├── events.enabled ─► company_events_am, company_events_pm
│   ├── discovery.enabled ─► bhavcopy sync, discovery_weekly
│   ├── delivery.enabled ─► morning_brief, weekly_review
│   ├── audit.enabled ─► audit_nightly
│   ├── ipo.enabled ─► 2 IPO refreshes, IPO deep dive
│   └── watchdog.enabled ─► ops_watchdog
├── every job: coalesce (missed runs fold into one), misfire grace 15 min to 6 h
└── a job crashes ─► error listener ─► one critical alert to the owner

The 16:30 daily-review job (the heart of the day)
├── review_date = the previous trading session (skips holidays)
├── cohort = enabled managed stocks, each once (duplicates logged)
├── thread pool ─► run_daily_review(stock, review_date, sector) (M4.2)
│   └── total budget 300 s × number of stocks
│       └── budget runs out ─► keep the finished reviews, mark the rest timed out,
│                              carry on (a slow day must not kill the trading day)
├── each stock gets ONE outcome: completed | degraded | data_gated | skipped | failed
├── produced = completed + degraded
│   ├── produced = 0 ─► zero-output alert (owner)
│   └── produced < required ─► partial-output alert naming each stock and reason
├── run_post_review_pipeline(review_date) (M5.1); its failure never fails the reviews
└── record the outcome ─► GET /scheduler/status "last_runs"
```

### 1.3 Config and switches

```
settings.X = cfg("section.key", env="VAR", fallback=...)
├── 1 environment variable (Railway) ... wins
├── 2 config.yaml ...................... otherwise
└── 3 the code's fallback .............. otherwise
    config.yaml malformed ─► the app refuses to start (fails loudly)

Switches that change behaviour         repository default ─► production (22 Nov 2026)
├── rl.learning_mode ................. adapt  ─► observe   (RL_LEARNING_MODE, since 26 Sep)
├── decision_gate.mode ............... record ─► enforce   (DECISION_GATE_MODE, since 19 Nov)
├── advisor.exit_rule ................ shadow: the legacy rule decides, evidence rule recorded
├── autopilot.deploy_idle_cash ....... false, but overrides.primary = true
│                                      (only the owner's paper book deploys idle cash)
├── atlas.enabled .................... true: outbox drainer and 23:xx atlas jobs are live
├── config/sector_toggles.json ....... 4 native sectors on; 18 others use the generic path
└── AUTH_REQUIRED .................... false = an anonymous request acts as the owner
```

### 1.4 Storage

```
data/   one Railway volume at /app/data; the ONLY home of state
├── predictions/<sector>/<TICKER>/    envelopes, feedback logs, weights, lessons, dossier
│   ├── <sector>/_shared_ledger.json       sector-wide lessons
│   └── _market_ledger.json, _regime_state.json
├── portfolio/<user>/                  portfolio.json, transactions.jsonl, advice_ledger.jsonl,
│                                      value history, digests/, cases/, exit_shadow.jsonl
├── discovery/                         screens/, shelf, dives.json, shelf_events.jsonl
├── events/<SYMBOL>.jsonl              company events
├── ipo/, market_cache/                IPO facts; EOD parquet, index constituents
├── logs/                              data_health.jsonl, decision_gate.jsonl
├── backups/                           last 7 archives + manifests
├── managed_tickers.json               which stocks the 16:30 review covers
└── SQLite: users.db, chat_sessions.db, atlas.db, telemetry.db, scores.db

Rules
├── writes are atomic (temp file + rename)
├── ledgers are append-only
└── transactions.jsonl is the authority; portfolio.json is derived from it
```

### 1.5 LLM access

```
OpenRouter through one client factory; every call logged (tokens, cost) to telemetry.db
├── fast ....... deepseek-v4.1-flash-1017 ─► chat tool loop, pre-open shock rating
├── reasoning .. xiaomi mimo-v2.6-pro ...... ─► unified analyst, aggregator, feedback agent,
│                                            thesis review, investment case, chat fallback
└── bulk ....... deepseek-v4-flash ......... ─► ticker resolution, advice narration,
                                              brief and weekly headlines, event typing
Failure watch: 10 failed calls in a row ─► one critical owner alert (at most every 6 h)
```

---

# M2: Data layer

```
M2 Data
├── 2.1 Prices and closes .... close_verifier, pricing, indicators/fetcher, bhavcopy, eod_store
├── 2.2 Sector data bundle ... services/data/context/bundle_builder.py
├── 2.3 Identity ............. config/instruments.yaml, symbol_resolver.py
└── 2.4 Other feeds .......... Serper news, Tavily pages, macro cache, NSE disclosures,
                               surveillance, bulk/block deals, fundamentals, peers, F&O
```

### 2.1 Prices and closes

```
"What did stock X close at on session D?"      get_verified_close / session_close
├── which symbol? ─► instrument registry (TATAMOTORS is priced from TMPV.NS)
├── yfinance close + NSE official close
│   ├── both present, within tolerance ─► yfinance value ("agree")
│   ├── both present, too far apart ─► NSE value + warning
│   │     (yfinance once returned another company's price for MARUTI: ~131 vs ~13,000)
│   ├── only one present ─► that one
│   └── none ─► None
├── no bar dated D ─► walk back to the last trading day (one retry)
│   └── bar older than D ─► fresh_for(D) = False ─► the gates call it stale
└── still nothing ─► PriceUnavailableError (the portfolio skips that holding today)

Prices for every NSE stock at once
└── 19:00 bhavcopy sync (last 7 days, so it heals after an outage)
    ─► one parquet per day (EodStore)
    ─► read by the discovery screen, the weekly review, the executable-price check
```

### 2.2 Sector data bundle

```
build_sector_bundle(stock, sector)      one fetch pass per analysis; never raises
├── 10 sections, fixed order
│   ├── company_news ........ Serper search (other engines run beside it, record only)
│   ├── sector_policy_news
│   ├── macro_context ....... from the macro news cache
│   ├── policy_deep_dive
│   ├── fundamentals ........ ESSENTIAL
│   ├── technicals .......... ESSENTIAL (price history, indicators)
│   ├── commodities
│   ├── flows_sentiment ..... uses the NSE data prefetched once per run
│   ├── peers_valuation ..... ESSENTIAL
│   └── dossier ............. what the learning loop knows about the company (M4.4)
├── each section returns text + a STATUS set by its producer from the data, not the text
│   ├── ok / cache_hit ................. usable
│   ├── stale / fallback / empty ....... weak
│   ├── not_applicable
│   ├── failed:<ErrorType> ............. the fetcher raised; text = "unavailable"
│   └── unverified ..................... plain text came back with no proof
└── capped per section and in total ─► to_prompt_text() for the analyst
```

### 2.3 Identity

```
Is TICKER on date D the company we think, priced on the right basis?
resolve_identity(ticker, D) ─ reads dated segments in config/instruments.yaml
├── no entry ─► its own NSE listing, resolved
├── active segment ─► that period's provider symbol + price basis
├── unresolved / retired / demerged ─► UNRESOLVED, and then
│   ├── research ─► the decision gate abstains
│   ├── daily review ─► the day is not graded
│   └── portfolio ─► the holding is HELD (even exits) until an operator runs
│        identity_reconcile plan (read-only) ─► apply --approve <digest>
└── prices came from a different symbol ─► the gate abstains

The user typed a name, not a ticker         _resolve_ticker
├── a managed or tracked ticker ─► itself, no LLM
└── otherwise ─► bulk LLM guess ─► does yfinance have a price for it?
    ├── yes ─► use the guess
    └── no ─► Serper search ─► LLM again with the snippets ("do not guess")
```

---

# M3: Research engine (one stock ─► one verdict)

```
M3 Research  src/backend/shared/pipeline/ + src/backend/sectors/
├── 3.1 Orchestrator ...... base_orchestrator.py: the one analyse() path
├── 3.2 Unified analyst ... unified_analyst.py: ONE reasoning call scores every dimension
├── 3.3 Aggregator ........ signal_aggregator.py: weights ─► composite ─► verdict
├── 3.4 Decision gate ..... decision_gate.py: actionable / degraded / abstain
└── 3.5 Sector routing .... registry.py

Who asks for an analysis
├── 16:30 daily review (re-run on a miss day) ................ M4.2
├── monthly forecast, startup self-heal, shock re-forecasts ... M4
├── Saturday deep dives, paper lane ........................... M6
├── POST /analyse, /ws/stream, chat tool run_agent_analysis ... M10
└── "generate envelope" on a managed ticker ................... M10
```

### 3.1 Orchestrator

```
analyse("MARUTI")      one run id; every warning in the run carries it
├── 1 resolve the ticker (2.3)
├── 2 choose weights
│   ├── learning_mode observe (production) ─► the sector's default weights
│   └── adapt ─► this stock's learned weights (defaults if none)
├── 3 prefetch NSE data once
├── 4 bundle (2.2) + unified analyst (3.2)
│   ├── write one data-health row: what arrived, what was missing
│   └── queue the search shadow on a daemon thread (changes nothing)
├── 5 no dimension scored?
│   └── yes ─► record the failure, raise AnalysisUnavailable
│              no verdict, no score row; the caller skips this stock today
├── 6 aggregator (3.3) ─► FinalReport
├── 7 decision gate (3.4) ─► may turn the verdict into INSUFFICIENT DATA
└── 8 record: run summary, score history (scores.db), analysis log, API usage
       score history feeds Home, the watchlist, chat and the buy candidates (M6.4)
```

### 3.2 Unified analyst

```
UnifiedAnalyst.run(stock, bundle, sector)     never raises
├── the sector's spec ─► its prompt module + its dimensions
│   ├── automobile (9) ....... sales_demand, raw_materials, fundamentals, pattern_analysis,
│   │                          sentiment, policy_regulatory, competitive_intel, risk_macro,
│   │                          valuation_catalyst (+ price target, fair value)
│   ├── banking_bfsi (6) ..... fundamentals, risk, macro_policy, institutional,
│   │                          pattern_analysis, universe_setup
│   ├── it_sector (8) ........ fundamentals, global_macro, risk_macro, peer_benchmark,
│   │                          pattern_analysis, sentiment, transcript_nlp, insider_smart_money
│   ├── renewable_energy (6) . fundamentals, business, valuation, sentiment_policy,
│   │                          technical, risk
│   └── generic (8) .......... business, fundamentals, valuation, technical, macro, risk,
│                              management, earnings
├── one reasoning-tier call (with retries), JSON out
│   ├── valid JSON ─► one AgentOutput per dimension (score 0..1, texts capped)
│   ├── cut-off JSON ─► salvage the dimensions present; the rest are marked errored
│   └── garbage or call failed ─► {} + reason (the orchestrator raises AnalysisUnavailable)
└── optional "sector question" from discovery, answered in the same call
```

### 3.3 Aggregator

```
SignalAggregator.run(outputs, weights)
├── composite = Σ(score × weight) ÷ Σ(weight), over SCORED dimensions only
│   └── errored dimension ─► excluded and the weights renormalised (never counted as 0.5)
├── conflicts: two dimensions more than 0.30 apart ─► flagged to the LLM
├── one reasoning-tier call ─► thesis, drivers, risks, final_score, verdict
├── verdict shadow: log the LLM's verdict beside the composite's verdict
└── hard-bind on (config: true) ─► verdict = the composite's band
    ├── ≥ 0.75 ......... STRONG BUY
    ├── 0.55 – 0.75 .... BUY
    ├── 0.40 – 0.55 .... NEUTRAL
    ├── 0.20 – 0.40 .... SELL
    └── < 0.20 ......... STRONG SELL
    (final_score stays the LLM's; it sets how wide the forecast's confidence is)
```

### 3.4 Decision gate

```
assess_analysis(section statuses, dimensions scored)
├── ABSTAIN if any of
│   ├── an essential section (fundamentals, technicals, peers_valuation) not ok/cache_hit
│   ├── fewer than 50% of the sector's dimensions scored
│   ├── no structured provenance (the bundle was not described)
│   ├── identity unresolved, or prices fetched for another symbol
│   └── the gate itself crashed (fails closed)
├── DEGRADED: essentials present, some enrichment (news, macro, flows) missing; still usable
└── ACTIONABLE: everything present

Then, by mode
├── record ─► compute it, log to decision_gate.jsonl, change nothing
└── enforce (production since 19 Nov) ─► an abstained analysis means
    ├── verdict = INSUFFICIENT DATA
    ├── no forecast envelope, no re-forecast, no shelf idea
    ├── no weight update and no lesson from it
    ├── no ADD, no SWITCH buy, no idle-cash buy on it
    └── EXIT and TRIM are never blocked (missing data must not trap a position)
    An unknown mode value ─► fails closed to enforce
```

### 3.5 Sector routing

```
Which path runs for sector key S?      registry.get_graph_sector(S)
├── S native and enabled (automobile, banking_bfsi, it_sector, renewable_energy) ─► itself
├── S known but has no native path (pharma, fmcg, metals ... 18 in all) ─► generic
└── S unknown ─► generic (automobile only if the fallback flag is turned off)
One map for every entry point. Two maps once disagreed and created duplicate stores.
```

---

# M4: Learning loop

```
M4 Learning  core/intelligence/
├── 4.1 Monthly forecast ........ rl/workflows/generate_forecast.py
├── 4.2 Daily review ............ rl/workflows/daily_review.py (largest file, 1,878 lines)
├── 4.3 Weights + learning mode . rl/agents/weight_adapter.py, rl/learning_mode.py
├── 4.4 Lessons + knowledge ..... ledgers, dossier curator, event ingestor, question researcher
└── 4.5 Regime + living envelope  regime/, rl/workflows/preopen_check.py
Store: PredictionStore = data/predictions/<sector>/<TICKER>/ (exactly one store per stock)
```

### 4.1 Monthly forecast (the "envelope")

```
generate_forecast(stock, sector)     1st of month 09:00 · startup self-heal · manual
├── weights: observe ─► sector defaults | adapt ─► stored weights
├── run the analysis (M3)
│   └── not actionable + enforce ─► InsufficientDataError, NO envelope
├── base close (verified; one retry after 15 s) ── none ─► fail; the next run retries
├── context
│   ├── learning ledger (past lessons)
│   ├── seasonal calendar (sector events seeded per day)
│   ├── forecast profile: LLM-calibrated monthly return % + path shape
│   │   (front-loaded, back-loaded or linear; static values if the call fails)
│   ├── regime label, F&O snapshot, per-dimension catalyst predictions
│   └── "blindspot" hints from past misses (saved for the month; the review reads them)
├── 30 trading-day rows: predicted close, verdict, confidence, key assumptions,
│   gate status + source run id
└── save <TICKER>_<YYYY-MM>_prediction_envelope.json
    (stamped with weight version, learning mode, gate and instrument)
```

### 4.2 Daily review (grade one stock on one session)

```
run_daily_review(stock, session D)
│
├── Step 0   regime: VIX, FII proxy, sector RSI ─► raw label ─► sticky label (4.5)
├── Step 1   find D's forecast row (this month's envelope, else last month's)
│   ├── no envelope ─► skipped (no_envelope)
│   ├── no row for D ─► skipped (no_forecast_row)
│   ├── row issued on non-actionable data ─► gate (enforce: stop = data_gated)
│   └── identity or price basis changed ─► gate
├── Step 2   actual close for D (2.1)
│   ├── none ─► skipped (no_actual_data)
│   └── close not dated D ─► gate (stale price would fake a flat day)
├── Step 3   error % = (actual − predicted) ÷ predicted; direction right?; timing
├── Step 4   why did we miss?
│   ├── direction right and |error| < 0.5% ─► reuse the forecast's scores (no re-run)
│   ├── otherwise ─► re-run today's analysis (M3)
│   │   ├── nothing scored ─► skipped (no_analysis)
│   │   └── re-run not actionable ─► gate
│   └── FeedbackAgent (LLM) ─► miss_type + analysis + new lessons
│       miss types include data_gap, data_stale, external_shock, timing,
│       direction_flip, model_bias
├── Step 5   WeightAdapter (4.3); + regime multipliers for today only, never saved
├── Step 6   lessons ─► the stock's ledger ─► sector/market ledgers by scope (4.4)
├── Step 6.5 conviction streak ─► "reversion prior" (the advisor's TRIM reads it)
├── Step 7a  big miss? ─► ThesisReviewer: which assumptions broke? confidence multiplier
├── Re-forecast (live month only; the first match wins)
│   ├── external_shock + direction wrong
│   ├── thesis multiplier at or below the threshold (thesis_break)
│   └── sticky regime has just turned MACRO_CRISIS (regime_flip)
│   └── new envelope made ─► skip 7b
├── Step 7b  revise the remaining rows' confidence
├── Step 8   append a FeedbackEntry to the month's feedback log  ◄── this is "output"
├── Step 8.5 DossierCurator updates the company dossier (every day; never blocks)
├── off-market signals; was news available? (recorded per stock per day)
└── Step 9   last trading day of the month ─► seasonal validation

Outcome: completed | degraded (written, on data the gate flagged) | data_gated
         | skipped | failed
paper=True (discovery's paper lane) ─► the same steps with every learning write disabled
```

### 4.3 Weights and learning mode

```
WeightAdapter (one weight per dimension)
├── the model was not at fault (data_gap, data_stale, external_shock) ─► no penalty
├── a timing miss of 3 sessions or less ─► no penalty
├── hit rate per dimension over the last N sessions
│   ├── ≥ 70% ─► +0.02
│   └── ≤ 40% ─► −0.03
├── weighted rolling miss rate (5/10/21 sessions) ≥ 0.55 ─► bias penalty
├── factor regime (IIMA momentum) scales the penalties
├── clamp: largest step per day, largest drift from the base
└── renormalise so the weights sum to 1.0

learning_mode decides what happens to that result
├── adapt ─► save a new weight version; lessons nudge dimension scores
└── observe (PRODUCTION) ─► the adapter runs on a copy; its proposal goes to
                           <TICKER>_weight_observations.json; decisions use the
                           sector defaults; lessons are recorded but move nothing
    An unknown value ─► fails closed to observe
```

### 4.4 Lessons and company knowledge

```
Lessons (written by the FeedbackAgent)
├── scope stock_specific ─► the stock's learning ledger only
├── scope sector_wide ─► + <sector>/_shared_ledger.json
└── scope market_wide ─► + _market_ledger.json
    Read back as tiers: the stock's top lessons, sector top 3, market top 2.
    Monday 03:30 cleans old lessons.

Dossier (what we know about the company); every write goes through ONE bounded merge
├── daily ......... DossierCurator (Step 8.5): the day's observations
├── Sat 10:00 ..... EventIngestor: results, concalls, guidance from NSE filings
│                   + one Tavily page each
└── Sat 11:00 ..... QuestionResearcher: picks open questions, runs targeted searches,
                    one LLM judges; questions that stay unanswered expire
Read by: the bundle's "dossier" section (M3), chat's get_ticker_dossier
```

### 4.5 Regime and the "living envelope"

```
RegimeDetector (no LLM: VIX, 5-day FII proxy, sector RSI)
├── MACRO_CRISIS ....... VIX > 22 and FII proxy < −1%
├── RISK_OFF ........... VIX > 22, or VIX 14–22 with FII proxy < −1%
├── MOMENTUM_EXTENDED .. VIX < 14, FII > +1%, RSI > 70
├── RISK_ON ............ VIX < 22, FII > +1%, RSI < 70
├── OVERSOLD ........... RSI < 30
└── NORMAL ............. anything else

Sticky label (market-wide, _regime_state.json)
├── severe label (RISK_OFF, MACRO_CRISIS) ─► entered at once
├── a milder reading while severe ─► calm_streak + 1; leave after N calm days
└── inputs unavailable ─► keep the last label, mark the day ─► no ADD, no new deployment

Who reads the sticky label
├── today's weight multipliers (M4.2 Step 5)
├── advisor: crisis + falling path ─► EXIT; crisis or risk-off ─► no ADD
├── deployment target: calm 80%, RISK_OFF 50%, MACRO_CRISIS 0% invested
└── the brief's wording ("Steady", "Cautious", "Crisis")

Pre-open check 08:45 (1 Serper search + 1 fast LLM call in total)
├── overnight shock severity below the threshold ─► nothing
└── at or above ─► for each stock: does today's forecast contradict the shock?
    └── yes ─► regenerate_envelope(trigger="preopen_shock")
```

---

# M5: Portfolio (paper money, real prices, no broker anywhere)

```
M5 Portfolio  core/portfolio/
├── 5.1 Post-review pipeline .. pipeline.py (after the 16:30 review, for each user)
├── 5.2 Advisor ............... advisor.py (rules decide; the LLM only narrates)
├── 5.3 Autopilot ............. autopilot.py (carries out the verdicts on the paper book)
├── 5.4 Money rules ........... sizing.py, deployment.py, costs.py
├── 5.5 Cases + exit rules .... cases.py, exit_shadow.py
├── 5.6 Integrity ............. corp_actions, reconcile, identity_reconcile, promotion
└── 5.7 Results ............... results.py, executable.py, digest.py
```

### 5.1 Post-review pipeline

```
run_post_review_pipeline(session D)
├── advisor off, or D not a trading day ─► stop
├── NSE surveillance report: read at most once per run
└── for each active user
    ├── 1  corp-action sync FIRST (bonus, split, dividend adjust cost and quantity)
    ├── no holdings and no idle-cash deployment ─► next user
    ├── 2  buy candidates = fresh shelf ideas + own watchlist BUYs − resale wait (M6.4)
    ├── 3  closes for D (holdings and candidates); sector weights on total equity
    ├── 4  refresh the results calendar for held stocks
    ├── 5  for each holding
    │   ├── build signals (envelope path, regime, confidence, ATR stop, P/L, age, weights)
    │   ├── decide with the acting exit rule + the data gate (5.2)
    │   ├── decide again with the other exit rule ─► exit_shadow row (never acted on)
    │   ├── narrate (bulk LLM; template text on failure)
    │   ├── append the AdviceRecord to advice_ledger.jsonl
    │   └── compare with the top 5 shelf ideas ─► switch evaluations (for grading)
    ├── 6  autopilot executes (5.3)
    ├── 7  case upkeep: retry a missing invalidation price; events challenge pillars
    ├── 8  value point: equity at D's marks ─► value history
    ├── 9  reconcile the ledger with portfolio.json (detects and alerts, never repairs)
    ├── 10 digest for D
    └── 11 alerts: TRIM/EXIT/SWITCH, each trade, a skipped switch buy; EOD digest push
Every step is non-fatal: one holding or one user failing never stops the rest.
```

### 5.2 Advisor: the decision for one holding

```
decide(signals, holding)      a pure function, no LLM
│
├── identity changed or unresolved ─► HOLD (note IDENTITY); even exits wait
│
├── EXIT if any trigger fires
│   ├── stop_breach ............. unrealised P/L ≤ −stop%
│   │                             stop = 3 × ATR(20), clamped: large cap 8–12%,
│   │                             mid 12–18%, small 15–22%
│   ├── thesis_break (legacy, acting today) ... the thesis reviewer says "not intact"
│   │                                           and the forecast path is falling
│   │   or case_broken (evidence rule, after 10 sessions) ... a material negative filing,
│   │       a fresh actionable SELL analysis, or the close at the invalidation price
│   ├── shock_reforecast ........ a recent shock re-forecast + falling path
│   ├── crisis_regime_bearish ... MACRO_CRISIS + falling path
│   └── trailing_stop_breach .... was up ≥ 10%, then fell ≥ stop% from its peak
│
├── else TRIM if P/L ≥ +25% and
│   ├── confidence has fallen by ≥ 0.05, or
│   └── reversion prior ≥ 0.20
│
├── else ADD if all of
│   ├── the remaining forecast path is UP
│   ├── regime is not MACRO_CRISIS or RISK_OFF
│   ├── the position is < 10% of equity
│   ├── direction accuracy over the last 7 reviews ≥ 60%
│   ├── the day's regime is known ........ (else note REGIME_UNAVAILABLE, no ADD)
│   └── data gate: fresh close, actionable forecast .. (else note DATA_GATE, no ADD)
│
├── else HOLD
│
├── EXIT + a stronger shelf idea in an underweight sector (conviction gap ≥ 0.15,
│   gate passes) ─► SWITCH (sell this one, buy that one)
├── TRIM in months 10–12 with the thesis intact ─► HOLD (WAIT_FOR_LTCG)
│   This tax softening never applies to an EXIT.
└── notes: EARNINGS_GAP_PROTECTION, POSITION_LARGE (>10%), SECTOR_CONCENTRATION_HIGH (>30%)

Precedence: EXIT > TRIM > ADD > HOLD
```

### 5.3 Autopilot: carrying out the verdicts

```
execute_advice(advice, closes, session D)      every trade is booked at D's close
├── fixed order
│   ├── 1 SELLS: EXIT (all), SWITCH sell leg (all), TRIM (25%) ─ in symbol order
│   ├── 2 BUYS: SWITCH buy legs, then ADDs (25% of the holding's value) by confidence
│   │      ADD cooldown: 5 sessions between two buys of one stock
│   └── 3 idle-cash deployment, if it is on for this portfolio (5.4)
├── every buy must pass
│   ├── size: position ≤ 10% and sector ≤ 30% of equity AFTER the trade; ₹10,000 cash floor
│   ├── a new position: price inside its idea's entry band
│   ├── NSE surveillance: listed active, no ASM or GSM stage
│   ├── identity resolved; close dated D (enforce)
│   ├── resale wait: not sold by this book since its idea was decided
│   └── the analysis rates it BUY
│   └── any check fails ─► skipped; the money stays in cash; the reason goes on the note
├── every trade pays its costs (STT, stamp, exchange, SEBI, GST, DP) from cash
├── txn_id = hash(user, date, symbol, side, ref) ─► a re-run never trades twice
├── a new position ─► an investment case is written (5.5)
└── the managed list follows the holdings
    ├── a sold stock leaves the 16:30 review (unless someone watches it)
    └── a new holding joins it
```

### 5.4 Money rules: sizing, deployment, costs

```
Deployment (idle cash ─► new positions)
├── target invested share from the sticky regime: calm 80% | RISK_OFF 50% | MACRO_CRISIS 0%
├── position size = target ÷ target_holdings (80% ÷ 25 = 3.2% of equity)
├── at most 5 new positions a day; at most 30 holdings; a minimum of 20 is reported,
│   never forced
├── candidates by conviction, best first ─► each through the buy checks (5.3)
└── stops when: target met, 30 holdings, 5 opened today, crisis, or regime unknown
    The digest says why each idea, and each idle rupee, was not used.

Sizing: every weight is a share of TOTAL equity (holdings at market + cash)
Costs: dated rates in config.yaml; older rows without costs are estimated and labelled so
```

### 5.5 Investment cases and the two exit rules

```
Investment case (written when a position opens: SWITCH buy, deployment buy, manual add)
├── inputs: the newest actionable analysis, the shelf idea, prices
├── one reasoning call writes: pillars with evidence, expectations,
│   what would prove us wrong, what to watch
├── every figure is checked against the inputs ─► an invented figure ─► a plain
│   deterministic case is stored instead
├── invalidation price: used only if it is above the purchase-day stop and at least
│   1.5 ATR below the entry
└── each day, new company events challenge the pillars (a record, never a sale by itself)

Exit rule mode (advisor.exit_rule)
├── legacy ─► thesis_break decides; nothing recorded
├── shadow (CURRENT) ─► legacy decides; both verdicts saved for each holding, each day,
│                       in exit_shadow.jsonl
└── evidence ─► case_broken decides; switched only by the owner, using the weekly
                scorecard's gate that was declared in advance
```

### 5.6 Integrity guards

```
├── corp actions (daily, before any advice)
│   ├── bonus/split/dividend ─► adj_avg_price, adj_qty; raw quantity and price never change
│   └── why: without it, a 1:1 bonus reads as a −50% crash and fires a false EXIT
├── reconcile (daily): cash chain continuity, final cash, per-stock quantity vs ledger
│   └── drift ─► error log + alert; never auto-repaired (a human decides)
├── identity reconcile (operator CLI): plan (read-only) ─► apply --approve <digest>
├── corrupt portfolio.json ─► quarantined; changes return HTTP 409
└── promotion: a held or watched stock ─► managed_tickers.json (cap 60;
    only watchlist entries are ever evicted)
```

### 5.7 Results: is it making money?

```
├── value history: equity at each review's marks; deposits tracked as capital_in
├── weekly results scorecard (Sunday)
│   ├── closed round trips; exit reasons
│   ├── sold too early (from the auditor's grades)
│   ├── you vs the Nifty (each deposit buys Nifty units on its day, so idle cash counts
│   │   against the book)
│   └── breadth, holding period, red flags
├── executable prices: the booked close vs the next real open ─► the gap a person would pay
└── GET /portfolio/performance, /scorecard, /transactions, /advice ─► Portfolio screen
```

---

# M6: Discovery (finding new ideas)

```
M6 Discovery  core/discovery/   Saturday 12:30, or POST /discovery/run
├── 6.1 Weekly funnel ....... __init__.py run_discovery_cycle
├── 6.2 Screen + guards ..... screen.py, signals.py, guards.py, universe.py, insider.py
├── 6.3 Deep dive + shelf ... deep_dive.py, shelf.py, sector_naming.py
├── 6.4 Buy candidates ...... candidates.py (M5 reads it every day)
└── 6.5 Paper lane .......... paper_lane.py
```

### 6.1 Weekly funnel

```
run_discovery_cycle()     each stage non-fatal; failures are listed in the result
├── 1 data: EOD sync (7 days), bulk/block deals (4 weeks), insider trades, NSE listing
│   └── no listing ─► no stock can be confirmed as a company ─► no deep dives this week
├── 2 IPO candidates (up to 2 slots)
├── 3 shelf hygiene: drop non-companies, classify, pick re-dives
│   └── re-dive order: sold by the autopilot since its dive ─► unverified or unnamed
│       ─► dive older than 30 days
├── 4 screen (6.2) ─► ranked candidates, minus those dived in the last month
├── 5 deep dives, budget 45 analyst calls a week
│   ├── IPO slots first
│   ├── re-dives up to 45 − IPO slots − 15 (15 calls kept for new companies)
│   ├── new companies in rank order
│   └── leftover re-dives take what remains; the rest wait a week
├── 6 shelf update: refresh or drop re-dived ideas; add new ones; rotate stale (> 60 days)
├── 7 alert to all: "added to the research shelf, tracking only, not a buy"
└── 8 weekly paper reviews (6.5)
```

### 6.2 Screen and guards

```
run_screen()      pure pandas, no LLM
├── universe: EQ series, above the price floor, companies only (NSE listing)
├── 6 signals (raw values, then percentile ranks)
│   ├── momentum ........... 6- and 12-month return ÷ volatility
│   ├── delivery_surge
│   ├── volume_breakout
│   ├── bulk_block ......... bulk and block deal activity
│   ├── high_52wk_rs ....... near the 52-week high, relative strength
│   └── insider_buying ..... promoter and director open-market net buying
│   └── a signal without data ─► "dark": left out, weights renormalised, named in the result
├── composite rank ─► shortlist
├── guards on the shortlist
│   ├── liquidity, series, price, circuit streaks (from EOD data)
│   ├── surveillance: any ASM or GSM stage ─► reject; suspended ─► reject
│   ├── free-float market cap floor
│   └── promoter pledge > 25% ─► reject
│   └── a guard's source is down ─► stock kept, check marked degraded
│                                    (the watchdog warns when it lasts a week)
└── top N candidates ─► screens/<date>_screen.json
```

### 6.3 Deep dive and the shelf

```
Deep dive (one candidate)
├── skipped before any LLM call: not a company; already managed (unless sold);
│   already on the shelf (unless due a re-dive)
├── M3 analysis (native or generic path), with the sector question in the same call
├── code, not the LLM, sets the entry band and an ATR-scaled invalidation level
│   ("the thesis is dead below X")
└── result: verdict, conviction, gate status, sector key

Shelf (at most 45 active ideas)
├── shelved only if: gate actionable, verdict BUY or STRONG BUY, conviction ≥ 0.55
├── at most 6 ideas per sector (an unnamed or "generic" key is not capped)
│   └── sector full ─► replaces its weakest idea only if conviction is higher
├── shelf full ─► a stronger idea displaces the weakest
├── re-dive ─► refreshed in place, or dropped (not actionable, below floor, no longer BUY)
├── latest dive older than 60 days ─► rotated out
└── every change ─► shelf_events.jsonl (feeds the alerts)
```

### 6.4 Buy candidates: what the autopilot may buy on session D

```
buy_candidates(portfolio, D)
├── source A: shelf ideas
│   ├── dive fresh (≤ 30 days) AND made before D's close
│   └── the dive's verdict is BUY or STRONG BUY
├── source B: this user's watchlist BUYs
│   ├── newest analysis before D's close: BUY or STRONG BUY, actionable,
│   │   conviction ≥ floor, fresh, an NSE company
│   ├── gets an entry band + invalidation level from the close that analysis read
│   └── a stock the autopilot sold onto the watchlist does not qualify
└── resale wait: sold since its idea was decided ─► not offered;
    buying back needs an analysis from the Saturday after the exit or later
```

### 6.5 Paper lane

```
Every active shelf idea
├── a PAPER envelope (generate_forecast paper=True) in a separate store root
├── a weekly paper review (run_daily_review paper=True): graded, no learning writes
└── a new month ─► the envelope is remade if missing
Purpose: see how an idea's forecast performs before any money goes into it.
```

---

# M7: Company events

```
Company-event feed  core/events/    08:15 and 18:30 on trading days
├── which stocks: holdings ─► watchlists ─► shelf ideas (each once, up to a cap)
│   └── identity unresolved ─► skipped and named
├── which items
│   ├── NSE announcements + board meetings (last N days)
│   ├── NSE disclosures: insider trades, SAST deals, pledges, shareholding
│   └── company news searches (daily budget, half per run)
├── new items only (by item identity; "not about this company" answers remembered)
├── typing
│   ├── disclosures ─► fixed rules, no LLM (insider, deal, pledge, ownership)
│   └── announcements + news ─► one bulk LLM call per batch of a stock's items
│       ├── must cite an item it was given ─► else dropped (ungrounded)
│       ├── every figure must appear in the item ─► else dropped
│       └── unknown category, direction or materiality ─► dropped (invalid)
├── the date is when NSE published it, never the trade day (when we could have known)
└── stored in data/events/<SYMBOL>.jsonl (no user data in it)

Read by: the evidence exit rule (case_broken), case pillar review, brief, GET /events/{symbol}
```

---

# M8: IPO

```
IPO  core/ipo/ + services/data/fetchers/ipo*.py
├── 08:00 + 17:45 refresh: NSE calendar + bid ladder (QIB, retail, total ×) ─► cache
├── 19:00 deep dive sweep (reads the cache; no NSE calls)
│   ├── issues closing tomorrow (T-1): full research
│   │   ├── research: Tavily pages (prospectus financials, peers, promoter, anchors,
│   │   │   use of proceeds, risks)
│   │   ├── extract: one LLM call per page; code stamps the page URL on every claim
│   │   └── corroborate: every number needs ≥ 2 domains that agree, else it is None
│   └── closed but not listed: re-read from the cache (the post-close row)
├── hype
│   ├── demand: fitted on 188 past listings (QIB ≥ total > retail)
│   └── froth: unfitted (retail ×, skew, cut-off share, GMP) ─► only widens the band
├── substance: profit, revenue, P/E vs peers (all unfitted except QIB ×)
├── verdict
│   ├── SHORT (listing day) lean ─► from demand alone
│   └── LONG ─► dark: no direction; the reasoning is kept for later
├── narrate: facts only; a number not in the facts ─► rejected; advice words ─► rejected
└── after listing: the auditor's IPO lane grades it
Nothing appears on a screen until its visibility milestone passes (the watchdog tracks it).
```

---

# M9: Delivery

```
M9 Delivery  core/delivery/
├── 9.1 Morning brief .... brief.py (08:50 weekdays)
├── 9.2 Weekly review .... weekly.py + index_watch.py (Sunday 18:00)
├── 9.3 Alerts ........... alerts.py, ops_alerts.py
├── 9.4 Channels ......... channels.py (web push, email)
└── 9.5 Outbox ........... outbox.py (durable queue)
```

### 9.1 and 9.2: Brief and weekly review

```
Morning brief (not a trading day ─► skipped)
├── assembled by code: regime in plain words, overnight market (Yahoo), holdings needing
│   attention, results due, events, shelf, IPOs
├── one bulk LLM call for the headline (fallback text on failure)
└── research tone; never the word "advice"

Weekly review
├── index watch first: constituent changes ─► alerts
│   (a shelf stock ─► everyone; any other stock ─► only accounts holding or watching it)
└── results scorecard ─► allocation vs risk profile ─► laggards ─► switch calls
    (last 4 weeks) ─► shelf candidates; one bulk headline call
```

### 9.3 Alerts: who gets what

```
├── operator notices (system health, job crash, LLM down) ─► the owner only
├── market notices (shelf adds, IPOs, index changes for shelf stocks) ─► everyone
└── account notices (your advice, your trades, your stocks) ─► that account only
Dedupe key user|date|kind|symbol in alerts_sent.jsonl
├── already delivered today ─► not sent again
└── no channel accepted it ─► marked undelivered ─► retried at the next emit
```

### 9.4 Channels

```
deliver(title, body, user, kind)
├── Atlas on (production) ─► put it on the outbox (9.5)
└── otherwise send now
    ├── web push (VAPID) ─► a dead subscription (400/403/404/410) is pruned
    └── email ─► SMTP or Resend ("auto" uses Resend when a key is set)
    Each send returns SendResult: accepted? permanent? reason (addresses masked)
    "accepted" means the transport took it; nothing confirms a person read it.
```

### 9.5 Outbox

```
Drainer (runs only in the primary worker)
├── claim a row: UPDATE ... SET status='sending' WHERE status='queued' ─► one sender only
├── send it
│   ├── accepted ─► delivered (+ which transport)
│   ├── permanent failure ─► dead letter at once
│   └── transient failure ─► retry after backoff (≥ the provider's Retry-After)
│                            ─► too many attempts ─► dead letter
└── a row left in 'sending' by a restart ─► dead letter (outcome unknown; never resent)
GET /delivery/outbox (owner): counts and dead letters, no message contents
```

---

# M10: Interface (API, login, screens, chat)

```
M10 Interface
├── 10.1 API routes ...... services/api/routes/
├── 10.2 Identity ........ auth.py, auth_api.py, user_store (users.db)
├── 10.3 Screens ......... src/frontend/prototypes/
└── 10.4 Chat ............ routes/ui_data.py (/ui/chat/stream)
```

### 10.1 API routes

```
FastAPI app
├── /auth/*         signup (by invite), login, logout, me, invites, delete account
├── /ui/*           bootstrap, tickers, market summary, watchlist, search, learnings,
│                   managed tickers, agents + weights, chat, logs (SSE)
├── /portfolio/*    portfolio, holdings, watchlist, CSV import, advice, digest,
│                   transactions, performance, scorecard, cases, deposit, run-advisor
├── /discovery/*    shelf, latest screen, run, promote, drop
├── /events/{sym}   company events
├── /delivery/*     brief, weekly, alerts, outbox, push keys/subscribe, run-brief/weekly
├── /scheduler/*    status (last runs), manual triggers (X-Scheduler-Key)
├── /analytics/*    accuracy, weight drift, misses, conviction, sector comparison, exports
├── /ui/rl/*        RL monitor: predicted vs actual, weights, misses
├── /audit/*        graded-outcome summary, backfill (owner)
├── /ops/errors     error backlog (owner)
├── /analyse, /ws/stream, /history/{ticker}
├── /health         is the process alive? (not jobs, not data)
└── /{anything}     a PWA file, else index.html; an unknown API path ─► 404
```

### 10.2 Identity

```
get_current_user(request)
├── AUTH_REQUIRED off ─► an anonymous request acts as the owner ("primary")
├── valid bearer token ─► that user (owner or member)
└── otherwise ─► 401
Owner-only routes: deposit, outbox, ops errors, audit backfill ...
Machine routes: X-Scheduler-Key (open, with a warning, while SCHEDULER_KEY is unset)
Quotas: chat 30 questions a day per member; /analyse metered; the owner is exempt from chat's
```

### 10.3 Screens (PWA)

```
index.html loads the JSX files; they become JS in the browser (no build step)
├── home.jsx ............ market pulse, scores, trending, watchlist
├── portfolio.jsx ....... holdings, P/L vs Nifty, trades, why a BUY was not bought, cases
├── inbox.jsx + brief / digest / weekly views
├── analytics.jsx, rl-monitor.jsx, agents-page.jsx (weights), logs.jsx
├── settings.jsx, auth.jsx
├── chat replies rendered via chat-markdown.js (marked + DOMPurify, pinned with SRI hashes)
└── sw.js + manifest.json ─► installable app, web push
```

### 10.4 Chat assistant

```
POST /ui/chat/stream {message, session_id}
├── signed in? quota left? (members: 30 a day)
├── prompt = system + IST market session + macro context + last 12 messages + message
├── pre-router (no LLM): a buy / sell / momentum question with a sector?
│   └── yes ─► run screen_stocks + search_market_news first and inject the results
├── tool loop: fast model, at most 4 rounds, 45-second budget
│   ├── the model asks for tools ─► they run in parallel ─► results go back ─► repeat
│   └── no tool call ─► that text is the answer
│   13 tools: live price, historical prices, macro news, market news search, screen stocks,
│   stock analysis, analysis history, RL insights, sector snapshot, run analysis (M3),
│   RL prediction, dossier, portfolio brief (the caller's own data only)
├── rounds or budget spent ─► one last call without tools
├── errors: 2 retries per model, then the reasoning model as fallback
└── strip <think>, clean up, stream in 3-word chunks, save the turn
```

---

# M11: Measurement (reads decisions, changes none)

```
M11 Measurement
├── 11.1 Nightly auditor .... core/audit/ (23:45)
├── 11.2 Monthly scorecard .. core/intelligence/rl/eval/scorecard.py (1st, 02:00)
├── 11.3 Weekly results ..... core/portfolio/results.py (see 5.7)
└── 11.4 Shadows ............ side-by-side records, never acted on
```

### 11.1 Nightly auditor

```
grade_due(today)      safe to re-run: one grade per (call, horizon)
├── lanes
│   ├── advice .... every advisor verdict
│   ├── alert ..... every escalation alert
│   ├── shelf ..... every shelf idea
│   ├── switch .... every switch evaluated (did the candidate beat the holding?)
│   └── ipo ....... IPO verdicts after listing
├── "correct" = EXCESS return vs NIFTY 50 over the horizon, never raw return
│   (in a rising market raw return makes every HOLD look right)
├── not matured yet ─► waits; no price ─► counted as unpriceable
├── report ─► one verdict word (INSUFFICIENT_DATA while the sample is small), Wilson intervals
└── breach rules ─► owner alerts
```

### 11.2 and 11.4: Scorecards and shadows

```
Monthly scorecard ─► forecast accuracy, Brier score, coverage vs simple baselines
                     ("baseline duel"), read from the feedback logs

Shadows
├── verdict shadow ........ the LLM's verdict vs the composite band (every analysis)
├── exit shadow ........... legacy vs evidence exit rule (every holding, every day)
├── switch evaluations .... every holding vs the top 5 shelf ideas, taken or not
├── search shadow ......... other search engines beside Serper for company news
├── weight observations ... what adapt mode WOULD have done (while in observe)
└── decision_gate.jsonl ... what enforce stops (or, in record mode, would stop)
```

---

# M12: Operations

```
M12 Operations
├── Watchdog 06:30 (config/milestones.yaml + named checks; the ladder is a pure function)
│   ├── satisfied after not being satisfied ─► "resolved" once, then silent
│   ├── unknown (the check crashed) ─► warning every day (a silent watchdog is worse than none)
│   ├── past its deadline ─► critical every 7 days, indefinitely
│   ├── window open ─► warning every day
│   ├── window near ─► info once
│   └── otherwise silent
│   examples: backup restorable, audit ran, IPO cache fresh, screen guard sources alive,
│             error backlog needs triage, scorecard written
├── Error backlog: every WARNING+ in telemetry.db ─► normalised text ─► fingerprint
│   ─► one issue per cause: new | regressed | spiking | quiet; ack | fixed | wontfix
│   "fixed" is proven by later data; a recurrence reopens the issue
├── Ops alerts: 10 LLM failures in a row; a job with 0 or partial output; a crashed job
├── Backup 23:30: zip of everything that cannot be rebuilt; SQLite through its backup API;
│   manifest (SHA-256, integrity, row counts); restore drill; keep 7;
│   off-site copy (AES-256-GCM) once a target is set — the watchdog says none is confirmed yet
└── Logs: telemetry.db (LLM calls, run summaries, app logs, data health),
          an in-memory buffer for /ui/logs, a run id on every warning
```

---

# Finale: one stock's life, end to end

```
Saturday     discovery: XYZ ranks high ─► deep dive (M3): BUY, conviction 0.68, actionable
             ─► shelf (entry band, invalidation level) ─► "tracking only" alert to all
             ─► paper envelope + weekly paper review start (M6.5)
Mon 16:30    reviews Friday ─► XYZ not offered (its dive came after Friday's close)
Tue 16:30    reviews Monday ─► XYZ is a buy candidate (M6.4)
             ─► idle-cash deployment: regime NORMAL, book below 80% ─► size 3.2% of equity
             ─► band, surveillance, identity, caps, cash floor all pass
             ─► BUY at Monday's close; costs charged; case written; XYZ joins managed list
Envelope     made by the next deploy's self-heal, the 1st-of-month job or a manual trigger.
             Until then XYZ's review is "skipped: no_envelope", and its advice reads a FLAT
             path: no ADD, but the price stops still protect it.
Every day    16:30 grades its forecast row ─► advisor: HOLD / ADD / TRIM / EXIT / SWITCH
             08:15 + 18:30 events feed watches its filings and news
             23:45 the auditor grades matured advice against the Nifty
Exit day     e.g. stop breach ─► EXIT ─► SELL at that session's close ─► realised P/L
             ─► alert + digest ─► resale wait before it can be bought back
Sunday       weekly results: the closed trade, its exit reason, the book vs the Nifty
```

---

# Notes from our discussion (22–23 Nov)

```
Why trades use only what was known at the close
├── the 16:30 run on day T books at T-1's 15:30 close
├── news published at time X may only affect a trade booked at a close after X
│   └── e.g. bad news Mon 17:00 ─► ignored for Monday's close ─► SELL at Tuesday's close
└── without it the paper P/L would be hindsight ("look-ahead"), and worthless to show anyone

Proposed upgrade (not yet a story): decide the same evening, trade at the next open
├── evening decision (about 19:30): reads everything known until then
├── morning check (about 08:50): new filings or news on holdings and planned buys since 19:30
│   ├── bad news on a holding ─► add a SELL at the open
│   ├── bad news on a planned buy ─► cancel the buy
│   └── nothing new ─► trades go ahead
├── trades booked at the 09:15 open, a price a person could really get
├── news during market hours waits for the next evening (the product never trades intraday)
└── trigger: PR-016's rule (round trip loses > 0.5 points at the next open, or the lead over
    the Nifty flips) ─► read with PR-016-W1, then a decision-path story (about 3 phases)

IPOs
├── a good IPO that keeps rising (Ather-like) ─► discovery's IPO lane: listed < 90 days,
│   at least 5 sessions traded, scored on post-listing evidence, 2 deep dives a week
├── listing-day pop and day-2 fade ─► avoided by design: no IPO applications, no day-1 buys
├── lock-in expiries (30 / 90 / 180 days) ─► alerts only, never signals
└── the IPO listing verdict runs dark and is graded nightly; revisit when it has evidence
```

---

# The architecture map's phases (MAP-001 to MAP-005)

Design: docs/superpowers/specs/2026-11-23-architecture-map-design.md. A 3D world for the flow
(three planes: what people see, the product flow, storage; camera presets for each direction)
and a flat detail panel for the logic, all drawn from one model generated from the code plus
curated meaning, kept true by a CI guard, built into one self-contained HTML file
(docs/architecture-map/index.html).

| Story | Phases | What it delivers | Needs | Status |
|---|---|---|---|---|
| MAP-001 | 1 | The model: jobs, routes, imports and switches generated from the code; modules, flows, stores and logic trees curated from this walkthrough; `model.json`, `TREES.md`; the guard in CI | — | todo |
| MAP-002 | 1–2 | `DESIGN.md` and `UI-CHECKLIST.md` first; the 3D world, camera presets (front, top, side, below), click-to-focus, the detail panel with ELK flowcharts (money path checked in depth: M3, M4.2, M5.2, M5.3, M6), manager/developer toggle, keyboard use | MAP-001 | todo |
| MAP-003 | 1 | The clock (day player), "trace a stock", the guided tour | MAP-002 | todo |
| MAP-004 | 1 | The code galaxy: every Python file and its imports, coloured by module, linked to the world | MAP-001, MAP-002 | todo |
| MAP-005 | 1 | Every module's logic checked, the 2D fallback, polish (reduced motion, phone), the full UI checklist, the living-map rule | MAP-002 to 004 | todo |

Each is a light story: built, tested and accepted in its own phase on the full suite, the
browser suite and the guards, with screenshots for the owner.

---

# Where we are (26 Nov 2026)

```
Done on 23 Nov (autopilot phases 1–4)
├── FIX-033   a deep dive's idea is the company it was asked about ─► live 01:49
├── PR-017    every deep dive graded at the conviction it was issued with ─► live 02:40
├── PR-046    "ask why" asks the card's own question ─► live 00:29
└── PR-015    the evidence exit rule acts ─► live 04:07

Autopilot: stopped after phase 4 (the weekly limit). main: f893dc4 (the MAP design/checklist
edit) waits for a push window.

Next, in order (about 11 phases)
├── 1     B-12      light            the scorecard's exit-rule line after the switch
├── 2–4   PR-047    measure + build + fresh review   a buy needs the analysis's own BUY
├── 5     MAP-001   the model and its guard
├── 6–7   MAP-002   the 3D world and the detail panel
├── 8     MAP-003   the clock, trace and tour
├── 9     MAP-004   the code galaxy
├── 10    MAP-005   every module, 2D fallback, polish, living map
└── 11    PR-007    plain, fact-grounded buy and sell explanations
Then the rest of the PI queue: about 33 phases.
```
