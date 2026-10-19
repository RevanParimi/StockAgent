# StockAgent — Product Map

**Edition:** 2026-10-13 · **Code inspected:** `e85da94`, the code production runs

**Scope:** every major module and its parts, counted from the tracked tree,
with a suggested order for learning them.

[ARCHITECTURE.md](ARCHITECTURE.md) explains how the system fits together,
the [technical design](TECHNICAL_DESIGN.md) (the KT) traces its contracts,
and the deep-dives explain one subsystem each. This map answers a different
question: **what are all the parts, and in what order should I learn them?**
Counts here were taken from `git ls-files` at the revision above. Measured
production state lives only in
[KT section 1](TECHNICAL_DESIGN.md#production-state-at-this-edition); the
[team testing guide](TEAM_TESTING_GUIDE.md) holds the human testing duties.

---

## 0. Orientation

**What the product is:** one Python service, FastAPI with an in-process
APScheduler, run by Docker as two Uvicorn workers of which one owns the
background jobs. It researches Indian listed equities: it issues a monthly
forecast per managed stock, grades it against the actual close every trading
day, records what it learns, manages a virtual portfolio from those signals,
discovers new candidates weekly, tracks IPOs, delivers briefs and alerts to a
PWA, and grades its own advice against the Nifty 50.

**Size** (lines of Python, JavaScript and C++ in tracked files):

| Area | Lines |
|---|---|
| `core/` | ~30,700 |
| `services/` | ~22,600 |
| `src/` (backend and the PWA) | ~22,500 |
| `scripts/` | ~3,000 |
| `tests/` | ~60,700 in 333 test files |

**Surface:** 86 HTTP endpoints and 1 WebSocket across 13 routers, plus 3
app-level routes · 24 possible scheduled job IDs · 4 native sector graphs and
1 generic graph · 3 LLM tiers · 28 `config.yaml` sections.

**Three switches change what the system may do** (KT section 2): the
decision gate (`decision_gate.mode`), the instrument registry
(`config/instruments.yaml`) and the learning mode (`rl.learning_mode`).
Section 1 of the KT records how production sets them.

### The one structural trap

The April 2026 restructure stalled in two directions, so one module can be
reached by two import paths. There are **19 shim files in two families that
point opposite ways**:

- **`MIGRATION SHIM`, 9 files: `core/*` → `src/backend/*`.** The real code
  moved out of `core/`; the old import path stays alive. Examples:
  `core/schemas/feedback.py` → `src/backend/shared/schemas/feedback.py`,
  `core/config/settings/base.py` → `src/backend/shared/config/settings/base.py`,
  `core/pipeline/orchestrator.py` → the automobile orchestrator.
- **`FORWARD SHIM`, 10 files: `src/backend/shared/*` → `services/*`.** The
  real code lives in `services/`, and the `backend.shared.*` path stays alive.
  Examples: `src/backend/shared/clients/llm_client.py` →
  `services/clients/llm_client.py`, and the shared fetchers and stores.

**Rule while studying:** a file of a few lines is a shim. Its header names the
real module: `MIGRATION SHIM` sends you to `src/backend/`, `FORWARD SHIM` to
`services/`. Several shims have no importer left; grep before deleting one.

---

## 1. Platform & Configuration Substrate

*The layer everything reads. Study it first.*

| Part | Path | Owns |
|---|---|---|
| Settings loader | `src/backend/shared/config/settings/loader.py` | `cfg()` and the precedence chain |
| Settings | `src/backend/shared/config/settings/base.py` | 1,136 lines of resolved settings and code fallbacks |
| Tunable config | `config.yaml` | 28 sections (below) |
| Instrument registry | `config/instruments.yaml` | Which security each ticker means on a date, and on which price basis |
| Milestones | `config/milestones.yaml` | The watchdog's checks and deadlines |
| Sector toggles | `config/sector_toggles.json` | Per-sector enable flag and tier |
| Secrets | `.env` locally, Railway variables in production | Keys only; never in documents or evidence |
| Atomic writes | `core/utils/atomic_io.py` | Temp-file-and-rename JSON writes, with a Windows retry |
| Shared prompts | `core/config/prompts/shared/` | 10 prompt modules for the non-sector LLM components |

**Precedence:** a declared environment override, then `config.yaml`, then
the code fallback. Not every key has an environment override, and most
settings are read at import, so a change needs a restart (and in production a
Railway variable change redeploys).

**`config.yaml` sections:** `llm`, `logging`, `agent_execution`,
`agent_weights`, `score_thresholds`, `data_fetch`, `scheduler`, `chat`,
`analyse`, `watchdog`, `error_backlog`, `macro_news`, `regime`, `regime_multipliers`,
`sector_agent_regime_role`, `rl`, `unified_analyst`, `portfolio`, `advisor`,
`discovery`, `ipo`, `observability`, `decision_gate`, `sectors`,
`generic_graph`, `delivery`, `atlas`, `audit`, `universe`.

---

## 2. LLM & External Service Clients

| Part | Path | Role |
|---|---|---|
| LLM client | `services/clients/llm_client.py` | OpenRouter wrapper, sync and async, call logging and cost |
| Tavily fetcher | `services/clients/tavily_fetcher.py` | Page retrieval with a monthly disk cache |
| API usage counter | `services/data/stores/api_usage.py` | Monthly call counts per provider (Serper budget 2,500 a month by default), checked at boot |

**Three tiers** (`llm:` in config.yaml, each overridable by environment):

| Tier | Repository model | Used for |
|---|---|---|
| Fast | `qwen/qwen3.6-flash` | Chat tool loop, pre-open shock rating |
| Reasoning | `z-ai/glm-5.2` | Unified analyst, aggregator narrative, FeedbackAgent, ThesisReviewer, control lane, chat retries |
| Bulk | `deepseek/deepseek-v4-flash` | Ticker resolution, legacy agents, forecast profile, dossier and event agents, narration, macro reviewer, IPO extraction |

[AGENTIC_DESIGN](AGENTIC_DESIGN.md) section 2 lists every caller. **Hard
rule:** every JSON-mode call passes `extra_body=JSON_MODE_EXTRA_BODY`, which
switches provider-side reasoning off; thinking-by-default model snapshots
otherwise truncate JSON output.

---

## 3. Data Acquisition Layer

*17 fetchers plus context assembly. Each one is non-fatal: a failure degrades
its own data, and the typed result says how (KT section 4).*

| Part | Path | Source |
|---|---|---|
| NSE client, key registry | `services/data/fetchers/nse_client.py`, `nse_key_registry.py` | NSE sessions; field renames across report vintages |
| Bhavcopy | `services/data/fetchers/bhavcopy.py` | Official EOD, delivery % |
| Close verifier | `services/data/fetchers/close_verifier.py` | yfinance close cross-checked with NSE's |
| Announcements | `services/data/fetchers/nse_announcements.py` | Filings, board meetings, corporate actions; one prefetch per analysis |
| Corporate events | `services/data/fetchers/corporate_events.py` | Results dates and actions for holdings |
| Market intelligence | `services/data/fetchers/nse_market.py` | FII/DII flows, bulk deals |
| Bulk and block deals | `services/data/fetchers/bulk_block.py` | Institutional accumulation for discovery |
| Surveillance | `services/data/fetchers/surveillance.py` | ASM/GSM, suspension, free-float market cap |
| IPO feeds | `services/data/fetchers/ipo.py`, `ipo_offer.py`, `ipo_bids.py`, `ipo_gmp.py` | Calendar, offer documents, bids; grey-market price behind its own switch |
| Fundamentals | `services/data/fetchers/fundamentals.py` | yfinance statements, bank-format aware |
| Macro | `services/data/fetchers/macro.py` | Currency, crude, commodities; the brief's "Before the open" figures |
| MF herding | `services/data/fetchers/mf_herding.py` | AMFI sector-ETF momentum |
| News | `services/data/fetchers/news.py` | Serper news with recency bounds; NewsAPI |
| Symbol resolver | `src/backend/shared/data/fetchers/symbol_resolver.py` | `resolve_identity`: the registry's symbol, else the NSE listing; a registered ticker is never self-healed |
| Instrument registry parser | `src/backend/shared/data/instruments.py` | Effective-dated identity records |
| Macro news feed | `services/background/macro_news_fetcher.py`, `macro_news_cache.py` | Market and policy headlines reviewed by the bulk model, one file a day |
| Fetch result | `services/data/context/fetch_result.py` | The typed status every section producer returns |
| Bundle builder | `services/data/context/bundle_builder.py` | One fetch pass for the unified analyst (595 lines) |
| Context builder | `services/data/context/builder.py` | Per-agent context for the legacy fallback (868 lines) |
| Technical indicators | `core/intelligence/algorithms/indicators/fetcher.py` | Price history, indicators, sector benchmarks |

**The instructive failure in this layer.** News searches once had no recency
bound: the provider returned months-old articles, the 3-day filter correctly
dropped them all, and most daily reviews ran news-blind for weeks. *A filter
that drops everything looks identical to a source that returns nothing*,
which is why every producer now reports a typed status and a reason.

---

## 4. Persistence Layer

*SQLite for queried data, JSON for state, JSONL for append-only ledgers,
parquet for EOD panels. KT section 3 lists every record and its writer.*

| Part | Path | Backing |
|---|---|---|
| Prediction store | `core/intelligence/rl/stores/prediction_store.py` | The learning file tree (below) |
| Store inventory and quarantine | `core/intelligence/rl/stores/store_inventory.py`, `store_migration.py` | Read-only ownership census; reversible quarantine of stray stores |
| Portfolio store | `core/portfolio/store.py` | Per-user JSON and append-only JSONL, with a file lock |
| Score store | `services/data/stores/score_store.py` | SQLite analysis history |
| Log store | `services/data/stores/log_store.py` | SQLite telemetry archive |
| Data health | `services/data/stores/data_health.py` | One row per analysis run (JSONL and `telemetry.db`) |
| User store | `services/data/stores/user_store.py` | `users.db`: users, sessions, invites, quotas |
| Atlas store | `services/data/stores/atlas_store.py` | `atlas.db`: the user-plane relational core and outbox |
| EOD store | `services/data/stores/eod_store.py` | Parquet, one file per trading day |
| Chat sessions | `services/data/stores/chat_session_store.py` | `chat_sessions.db` |
| Analysis and run loggers | `services/data/stores/analysis_logger.py`, `run_logger.py` | Per-run output; every LLM call |
| Job outcomes, fallback events | `services/data/stores/job_outcomes.py`, `fallback_events.py` | Last result per job, with per-ticker review outcomes; legacy-pool engagements |
| Verdict store | `services/data/verdict_store.py` | **The plane boundary**: the user plane's only read path into prediction stores |
| Backup, restore, off-site | `services/data/backup.py`, `restore.py`, `offsite.py` | Nightly archive, restore drill, encrypted off-site copy |

### The RL file tree — memorise this

`data/predictions/<sector>/<TICKER>/` holds the monthly envelope, feedback
log, control log and prompt enhancements; the permanent weight memory,
observe-mode weight observations, learning ledger, archived lessons and
dossier; dated off-market files; `archived_envelopes/`; and
`thesis_calls.jsonl`. One level up are each sector's shared ledger and seed
validation state; at the root, the market ledger and the sticky regime.
[RL_DESIGN](RL_DESIGN.md) section 3 gives every file and its schema.

The owner rule: a ticker's history belongs to `<managed sector>/<TICKER>`.
Constructing a store creates its directory, so a read can leave an empty one
behind (KT [prediction-store ownership](TECHNICAL_DESIGN.md#prediction-store-ownership)).

Per-user portfolio plane, `data/portfolio/<user>/`: `portfolio.json`,
`transactions.jsonl`, `advice_ledger.jsonl`, `value_history.jsonl`,
`switch_evaluations.jsonl`, `identity_reconciliations.jsonl`,
`weekly_scorecard.jsonl`, digests, briefs and weekly reviews
([AUTOPILOT_GUIDE](AUTOPILOT_GUIDE.md) section 2). The nightly auditor writes
its graded rows to its own append-only store, `advice_outcomes.jsonl`.

---

## 5. Analysis Engine — the verdict producer

*Given a ticker, produce a `FinalReport` with a score, a verdict, a thesis
and a decision gate.* Design: [AGENTIC_DESIGN](AGENTIC_DESIGN.md).

### 5.1 Routing and resolution

- `src/backend/sectors/registry.py`: a map of 202 tickers, name fragments for
  free text, sector toggles. Four native graphs; every other sector, and any
  input it cannot place, runs the **generic** graph. The store keeps the real
  sector name.
- `base_orchestrator._resolve_ticker`: a tracked ticker (sector list, managed
  list or instrument registry) resolves to itself with no model call; free
  text goes to the bulk model.

### 5.2 The two execution paths — the critical distinction

| Path | Entry | Cost |
|---|---|---|
| **Unified analyst** (live, all five graphs) | `src/backend/shared/pipeline/unified_analyst.py` | One data bundle, **one** reasoning call for every dimension |
| **Legacy worker pool** (fallback) | `src/backend/shared/pipeline/graphs/`, `base_agent.py`, `shared/agents/universal.py` | LangGraph fan-out, one bulk call per dimension |

`base_orchestrator.py` chooses the path, records the data-health row and
applies the decision gate. Fallback engagements are counted in
`fallback_events.py`.

### 5.3 Per-sector dimensions

| Graph | Dimensions |
|---|---|
| `automobile` (9) | fundamentals, sales_demand, risk_macro, valuation_catalyst, pattern_analysis, raw_materials, policy_regulatory, competitive_intel, sentiment |
| `banking_bfsi` (6) | fundamentals, risk, macro_policy, institutional, pattern_analysis, universe_setup |
| `it_sector` (8) | fundamentals, global_macro, risk_macro, peer_benchmark, pattern_analysis, sentiment, transcript_nlp, insider_smart_money |
| `renewable_energy` (6) | fundamentals, business, valuation, sentiment_policy, technical, risk |
| `generic` (8) | fundamentals, business, valuation, technical, macro, risk, management, earnings |

37 slots under 24 names; AGENTIC_DESIGN section 8 gives the default weights.

### 5.4 Fusion, gate and evidence checks

| Part | Path | Role |
|---|---|---|
| Signal aggregator | `src/backend/shared/pipeline/signal_aggregator.py` | Composite over scored dimensions, conflicts, narrative; the verdict is bound to the composite's band |
| Verdict shadow | `src/backend/shared/pipeline/verdict_shadow.py` | Logs the model's own verdict beside the bound one |
| Decision gate | `src/backend/shared/pipeline/decision_gate.py` | Actionable, degraded or abstain; `record` or `enforce`; the gate log |
| Instrument identity | `src/backend/shared/data/instruments.py`, `symbol_resolver.py` | Resolved, unresolved or quarantined; price basis |

### 5.5 Numeric sub-engines

| Part | Path | Note |
|---|---|---|
| C++ indicators | `core/intelligence/algorithms/cpp/src/indicators.cpp` | RSI, MACD, Bollinger via pybind11, with a Python fallback |
| F&O analyzer and fetcher | `core/intelligence/fno/` | Put-call ratio, max pain, open-interest build-up |
| Prompt enhancer | `core/intelligence/prompt_enhancer/enhancer.py` | Extra search queries from the miss counter |
| Retrieval (RAG) | `core/intelligence/rag/` | Behind `RAG_ENABLED`, off, with no corpus |

---

## 6. Regime & Market-State Intelligence

| Part | Path | What |
|---|---|---|
| Regime detector | `core/intelligence/regime/detector.py` | VIX, Nifty 5-session move and sector RSI → six labels, with global-stress escalation. No LLM |
| Sticky regime | `core/intelligence/regime/state.py` | Hysteresis so the label does not flap |
| Regime multipliers | `config.yaml` → `regime_multipliers`, `sector_agent_regime_role` | Per-dimension weight overlays, never stored |
| Factor regime | `core/intelligence/rl/algorithms/factor_regime.py` | IIMA four-factor data, a static prior ending March 2023 |
| Seasonal calendar and validator | `core/intelligence/seasonal/` | Seeded patterns per native sector, and their month-end validation |
| Conviction tracker | `core/intelligence/rl/conviction/tracker.py` | Long same-direction streaks raise a reversion prior |
| NSE calendar and updater | `core/intelligence/rl/nse_calendar.py`, `calendar_updater.py` | Trading days, sessions, F&O expiry; the 31 December refresh |

Labels: `MACRO_CRISIS`, `RISK_OFF`, `MOMENTUM_EXTENDED`, `RISK_ON`,
`OVERSOLD`, `NORMAL` ([RL_DESIGN](RL_DESIGN.md) section 13).

---

## 7. The Adaptive Learning Loop (RL) — the heart

*About 12,500 lines under `core/intelligence/rl/`. Budget the most study
time here.* Full design:
[RL_DESIGN.md](RL_DESIGN.md). Adaptive state exists; improved prediction
has not been demonstrated, and production runs the `observe` learning mode
(KT section 1).

### 7.1 Forecast generation (monthly)

`core/intelligence/rl/workflows/generate_forecast.py` (834 lines) runs the
analysis, then builds the **envelope**: forecast rows for the next 30 trading
days, each stamped with its issuing run, gate and instrument. An abstained
analysis builds no envelope in `enforce` mode.

- `core/intelligence/rl/algorithms/price_interpolator.py`: the forecast
  profile (bulk model, static fallback) and the Monte Carlo paths;
- `core/intelligence/rl/workflows/sector_router.py`: the weight tables, with
  routing delegated to the registry.

### 7.2 Daily review — the spine

`core/intelligence/rl/workflows/daily_review.py` (1,833 lines). **Read it top
to bottom; it is the product.**

| Step | What happens |
|---|---|
| 0 | Regime detection and the sticky label |
| 1 | The envelope row for the session |
| — | Input checks: row provenance, identity (`data_gated` in `enforce` mode) |
| 2 | The session's close, cross-checked with NSE, and the stale-close check |
| 3 | Error and direction (measured against the predicted close) |
| 4 | Optional re-run (gated), context assembly, **FeedbackAgent** |
| 5 | **WeightAdapter**: a new version in `adapt`, a recorded proposal in `observe` |
| 5.5 | Regime multipliers on the decision weights |
| 6 | Lessons merge and shared-ledger propagation |
| 6.5 | Conviction streak and reversion prior |
| 7a | **ThesisReviewer** on a significant miss |
| — | Re-forecast trigger (Living Envelope) |
| 7b | Confidence-only revision of the remaining rows |
| 8 | The feedback entry |
| 8.5 | **DossierCurator**, every day |
| 9 | Seasonal validation, month end only |
| 10 | **Control lane** |

`review_outcomes.py` then gives each enabled ticker one outcome:
completed, degraded, data_gated, skipped or failed.

### 7.3 The learning agents and controls

| Part | Path | Role |
|---|---|---|
| FeedbackAgent | `core/intelligence/rl/agents/feedback_agent.py` | Classifies the miss and writes lessons |
| WeightAdapter | `core/intelligence/rl/agents/weight_adapter.py` | Deterministic weight update; bounds applied before renormalising |
| Learning mode | `core/intelligence/rl/learning_mode.py` | `adapt` or `observe`; decision weights; observation records |
| ThesisReviewer | `core/intelligence/rl/agents/thesis_reviewer.py` | Fires when the error exceeds `max(1.5%, 1.5 × ATR%)` or on a structural miss |
| Control lane | `core/intelligence/rl/agents/control_lane.py` | A bare model with the same close and context, the baseline opponent |
| Review outcomes | `core/intelligence/rl/workflows/review_outcomes.py` | One outcome per ticker per run |

### 7.4 Lesson machinery

| Part | Path | Role |
|---|---|---|
| Ledger propagator | `core/intelligence/rl/stores/ledger_propagator.py` | Routes lessons by scope; weekly downgrade and archiving |
| Lesson emphasis | `core/intelligence/rl/algorithms/lesson_emphasis.py` | The only place tagged lessons move scores; a no-op in `observe` |
| Provenance | `core/intelligence/rl/provenance.py` | Keeps the dated headlines behind a lesson or observation |
| Month-end validation | `core/intelligence/rl/workflows/month_end_validation.py` | Step 9 |

### 7.5 Living Envelope

- `preopen_check.py`: the 08:45 overnight shock rating; on a shock it
  re-forecasts contradicted envelopes among the native sectors' built-in
  ticker lists.
- `regenerate_envelope` in `generate_forecast.py`: archives the current
  envelope and replaces only the rows after the trigger date.
- `stores/offmarket_fetcher.py`: block and bulk deals and the pre-open
  price, saved after each review as the next day's context.

### 7.6 Schemas

`src/backend/shared/schemas/feedback.py` (1,099 lines): the envelope, the
feedback log, weight memory and the learning ledger, among some thirty
Pydantic models.

---

## 8. Knowledge Layer (Ticker Dossier)

*Permanent per-ticker knowledge that outlives forecast cycles.*

| Part | Path | Cadence |
|---|---|---|
| Dossier schema | `src/backend/shared/schemas/dossier.py` | `open_guidance(as_of)` and the dated digest |
| DossierCurator | `core/intelligence/rl/agents/dossier_curator.py` | Daily (step 8.5), plus weekly distillation on Mondays at 03:30 |
| EventIngestor | `core/intelligence/rl/agents/event_ingestor.py` | Saturday 10:00: NSE results, con-calls, guidance and presentations dated on or before the scan |
| QuestionResearcher | `core/intelligence/rl/agents/question_researcher.py` | Saturday 11:00: searches for open questions, one batched call per ticker |

**Design principle.** The model *proposes* dossier updates; the merge code
enforces every bound and never raises, so a failure leaves the dossier
unchanged. No writer dates a row after the run that wrote it, and every
reader filters by date ([RL_DESIGN](RL_DESIGN.md) section 23.1).

---

## 9. Portfolio & Advisory ("Compass")

*Virtual money, real NSE closes.* Full design:
[AUTOPILOT_GUIDE.md](AUTOPILOT_GUIDE.md).

| Part | Path | Role |
|---|---|---|
| Schemas | `src/backend/shared/schemas/portfolio.py` | `adj_avg_price` and `adj_qty` are adjusted; all P&L and stop math uses them |
| Store | `core/portfolio/store.py` | Per-user files, lock, corrupt-file quarantine |
| Advisor | `core/portfolio/advisor.py` | Precedence **EXIT > TRIM > ADD > HOLD**, SWITCH, the data and identity checks |
| Autopilot | `core/portfolio/autopilot.py` | Deterministic execution; no broker call anywhere |
| Sizing | `core/portfolio/sizing.py` | One rule for every autopilot buy: position and sector caps of total equity after the trade, the cash floor, and a new position only inside its shelf idea's entry band |
| Results scorecard | `core/portfolio/results.py` | One row per ISO week from the user's own ledgers: closed round trips, sales graded by the auditor, exit reasons, the money-weighted Nifty comparison, five predeclared red flags. Stored once per week; `GET /portfolio/scorecard` |
| Identity reconcile | `core/portfolio/identity_reconcile.py` | Operator plan/apply for demergers and renames |
| Narrator, narrative cache | `core/portfolio/narrator.py`, `narrative_cache.py` | Bulk-tier phrasing of a decided verdict, cached per day |
| Pricing | `core/portfolio/pricing.py` | The daily review's verified close, with the bar's date |
| Corporate actions | `core/portfolio/corp_actions.py` | Splits, bonuses, dividends (with `DIV` ledger rows) before any rule |
| Promotion | `core/portfolio/promotion.py` | Held and watchlisted symbols join the managed list (cap 40) |
| Pipeline | `core/portfolio/pipeline.py` | Post-review orchestration; corporate actions first |
| Digest | `core/portfolio/digest.py`, `digest_text.py` | The EOD digest, event-triggered after the reviews |
| Reconcile | `core/portfolio/reconcile.py` | Ledger versus portfolio, detect and alert |
| Retention, universe | `core/portfolio/retention.py`, `universe.py` | Atlas pruning and nightly demand recompute |

---

## 10. Discovery Engine (Compass Phase B)

*Weekly funnel: universe → signals → screen → guards → deep dives → shelf →
promotion.* KT section 8.

| Stage | Path | What |
|---|---|---|
| Universe | `core/discovery/universe.py` | Mainboard EQ series, price floor |
| Signals | `core/discovery/signals.py` | Seven pandas signals, no LLM; `None` when dark |
| Screen | `core/discovery/screen.py` | Percentile-rank composite over live signals only |
| Guards | `core/discovery/guards.py` | Liquidity, series, price and circuit gates, then surveillance and float on the shortlist |
| Deep dive | `core/discovery/deep_dive.py` | The ordinary analysis per name, so its decision gate is the idea's `data_gate`; entry zone and invalidation level |
| Shelf | `core/discovery/shelf.py` | Capped; stronger ideas displace weaker ones; promotion to the watchlist |
| Paper lane | `core/discovery/paper_lane.py` | Real forecasts under an isolated store root, with no learning writes |
| IPO tracker | `core/discovery/ipo_tracker.py` | Recent listings ranked on listing evidence, delivery, accumulation and subscription |
| Schemas | `src/backend/shared/schemas/discovery.py` | Screen, deep dive, shelf |

**Pattern worth extracting: dark-signal renormalization.** A score is
normalised over the signals actually available, so a missing feed costs
precision instead of adding an implicit zero. The screen, the IPO tracker and
the aggregator all do this.

### IPO intelligence

`core/ipo/` (16 modules) collects issue facts and demand snapshots
(`calendar.py`, `signals.py`, `velocity.py`; `ledger.py` refuses any rewrite
of its JSONL stores that would drop a line it cannot parse), builds the history
and its report (`history.py`, `outcomes.py`, `report.py`), and runs the dark
P3 model: browsed research (`research.py`, `extract.py`), deterministic
indices and the verdict grid (`hype.py`, `substance.py`, `verdict.py`), the
19:00 deep-dive sweep into the append-only verdict store (`deep_dive.py`,
`verdicts.py`), a sourced narration (`narrate.py`) and forward grading from
the listing day (`listing.py`). None of the P3 output reaches a user until
its visibility milestone is judged.

---

## 11. Delivery Layer (Compass Phase C)

| Part | Path | Trigger |
|---|---|---|
| Morning brief | `core/delivery/brief.py` (1,395 lines) | Mon–Fri 08:50. Deterministic assembly, the overnight market figures from Yahoo and one bulk headline call; overnight news is what was published since the previous brief and not shown in the last 5; HTML and text |
| Weekly review | `core/delivery/weekly.py` | Sunday 18:00: the results scorecard first (red flags at the top), then allocation, laggards, switch calls and shelf candidates. Text email; the Inbox screen renders the same sentences |
| Alerts | `core/delivery/alerts.py` | Event-driven, deduplicated per user, date, kind and symbol. Operator notices reach only the owner, market notices every account; the Inbox lists the caller's own |
| Channels | `core/delivery/channels.py` | Web push and email (SMTP or Resend), one result contract |
| Outbox | `core/delivery/outbox.py` | One durable row per message and channel when Atlas is on; retries, dead letters, at-most-once |
| Index watch | `core/delivery/index_watch.py` | Weekly constituent changes. Each account hears only about stocks it holds or watches; a change to a shelf idea reaches every account |
| Ops alerts | `core/delivery/ops_alerts.py` | Job errors and zero-output alerts |

KT section 10 gives the delivery contract. **Compliance runs through all of
it:** output is framed as research, never advice
([LEGAL_AND_COMPLIANCE.md](LEGAL_AND_COMPLIANCE.md)).

---

## 12. Verification Layer ("the auditor")

*Deterministic, no LLM. Grades what the system told users, against `^NSEI`.*
Design: [verification layer](superpowers/specs/2026-08-07-verification-layer-design.md).

| Part | Path | Role |
|---|---|---|
| Rules | `core/audit/rules.py` | What "correct" means for each advice verb; pure functions |
| Outcomes | `core/audit/outcomes.py` | The recorder, idempotent per reference and horizon; also the IPO lane |
| Benchmark | `core/audit/benchmark.py` | Nifty 50 closes |
| Metrics | `core/audit/metrics.py` | Each function reports its own `n` and returns `None`, never 0, with no data |
| Thresholds | `core/audit/thresholds.py` | Breach rules for output that is complete but wrong |
| Attribution, evidence | `core/audit/attribution.py`, `evidence.py` | Why switch decisions went wrong, as a distribution; which inputs a call had (for example, whether news was available) |
| Report, store, CLI | `core/audit/report.py`, `store.py`, `cli.py` | One verdict word; its own append-only store; `python -m core.audit.cli` |

**Study the failure, not just the code.** On its first production run the
layer graded nothing: the benchmark lookup used a one-day yfinance window,
which returns empty for `^NSEI`. The one function that touched the network had
been isolated so tests could patch it, so it was the one function no test
exercised.

---

## 13. Measurement & Scientific Evidence

*Distinct from the auditor: this asks whether **learning** works, not whether
**advice** works.* [RL_DESIGN](RL_DESIGN.md) sections 24 and 25.

| Part | Path | Question |
|---|---|---|
| Eval harness, metrics, runner | `core/intelligence/rl/eval/harness.py`, `metrics.py`, `run_eval.py` | Read-only replay of recorded history |
| Synthetic | `core/intelligence/rl/eval/synthetic.py` | Fabricated logs so metrics run without history |
| Baselines | `core/intelligence/rl/eval/baselines.py` | Persistence and always-up |
| Scorecard | `core/intelligence/rl/eval/scorecard.py` | Monthly lanes: agent, control, baselines |
| Learning evidence | `core/intelligence/rl/eval/learning_evidence.py` | Self-ablation: adapted versus base versus uniform weights |
| Schemas | `src/backend/shared/schemas/scorecard.py` | Control-lane records |

All of it grades the same label the daily review records, which measures
error direction (KT [section 5](TECHNICAL_DESIGN.md#grading-defect-an-example-everyone-can-follow)).
**Planned:** a corrected target and matched cohorts (SA-012 to SA-022).

---

## 14. Service & Interface Layer

### 14.1 API — `services/api/server.py`

14 routers: **89 router endpoints and 1 WebSocket**, plus 3 app-level routes
(`/health`, `/tickers` and the single-page fallback).

| Router | Path | Endpoints and surface |
|---|---|---|
| ui_data | `services/api/routes/ui_data.py` (3,975 lines) | 26: bootstrap, market summary, trending, watchlist, search, learnings, managed tickers, agent weights, logs, feedback, **and the chat engine** |
| portfolio | `services/api/routes/portfolio_api.py` | 11: holdings, watchlist, CSV import, advice, digest, transactions, performance, run-advisor |
| delivery | `services/api/routes/delivery_api.py` | 9: brief and weekly, manual runs, alerts, push subscriptions, the outbox view |
| analytics | `services/api/routes/analytics.py` | 8: RL exports, accuracy, drift, misses, conviction, sector comparison, an OData feed |
| auth | `services/api/routes/auth_api.py` | 7: signup, login, logout, me, invites, account deletion |
| prompts | `services/api/routes/prompts.py` | 6: live prompt read and edit, publishing |
| discovery | `services/api/routes/discovery_api.py` | 5: shelf, screen, run, promote, drop |
| rl_monitor | `services/api/routes/rl_monitor.py` | 5: read-only learning views, with the learning mode |
| scheduler | `services/api/routes/scheduler_api.py` | 4: status and job triggers (owner or machine key) |
| ops | `services/api/routes/ops_api.py` | 3: the operations backlog, its digest and triage (owner or machine key) |
| audit, history | `services/api/routes/audit_api.py`, `history.py` | 2 each |
| analyse | `services/api/routes/analyse.py` | 1: an on-demand analysis (member quota) |
| stream | `services/api/routes/stream.py` | The WebSocket `/ws/stream` with agent progress |
| Auth gate | `services/api/auth.py` | Session, owner and machine-key checks |
| Log buffer | `services/api/log_buffer.py` | The managed list's readers and a live log ring buffer, read only by the owner or the machine key (`/ui/logs`) |

### 14.2 Chat sub-system

Inside `ui_data.py`, but a module in its own right:
[CHAT_ARCHITECTURE.md](CHAT_ARCHITECTURE.md). A static pre-router for buy,
sell and momentum questions, a fast-tier tool loop with 13 tools, per-user
session memory, a daily member quota, and a sanitizing Markdown boundary in
the browser.

### 14.3 Frontend — `src/frontend/prototypes/`

A single-page PWA of 23 modules, transformed in the browser with no build
step: `home`, `portfolio`, `brief-view`, `digest-view`, `weekly-view`,
`inbox`, `analytics`, `agents-page`, `rl-monitor`, `rl-data`, `prompt-lab`,
`settings`, `auth`, `learn`, `logs`, `data`, `sphere` (the chat overlay),
`chat-markdown.js` (the sanitizing boundary), `demo-fixtures.js` (sample data
for `?demo=1` only), `tweaks-panel`, `hooks`, `icons` and the versioned
service worker `sw.js`.

Every figure a member sees comes from an API answer, with its date, or the
screen says it is unavailable; a failed request never shows sample data. The
operator screens (Prompt Lab, Analytics, RL Monitor, Logs), agent tuning and
the Tweaks panel show only for the owner's session (`/auth/me` role), and the
server keeps its own guards ([KT section 10](TECHNICAL_DESIGN.md#10-delivery-interface-identity-and-operations)).

Responsive check: `node scripts/ui_responsive_audit.mjs` (runs on the
`?demo=1` samples; `--live` for the server's answers). Browser tests
(`npm run test:frontend`) cover the chat boundary, the Logs screen and the
real-figures and owner-only rules. **Planned:** packaging and a compiled
client (SA-028, stretch).

---

## 15. Time Orchestration

`services/scheduler/python/scheduler.py` (1,531 lines): an APScheduler
background thread in the process that owns the background work. **24 possible
job IDs**; registration depends on feature gates and valid cron settings, and
registration is not execution. The KT's
[job table](TECHNICAL_DESIGN.md#9-scheduled-jobs-and-event-hooks) is the
reference.

| IST | Job ID | Days |
|---|---|---|
| 00:00 | `prompt_daily_deploy` | Daily |
| 02:00 | `scorecard_monthly` | 1st |
| 03:30 | `ledger_cleanup_weekly` | Monday |
| 06:30 | `ops_watchdog` | Daily |
| 07:30 | `macro_daily_news` | Mon–Fri |
| 08:00 | `ipo_refresh_am` | Daily |
| 08:45 | `preopen_shock_check` | Mon–Fri |
| 08:50 | `morning_brief` | Mon–Fri |
| 09:00 | `rl_monthly_forecast` | 1st |
| 09:00, 12:00, 15:00 | `macro_market_news` | Mon–Fri |
| 10:00 | `event_ingest_weekly` | Saturday |
| 11:00 | `research_loop_weekly` | Saturday |
| 12:30 | `discovery_weekly` | Saturday |
| 16:30 | `rl_daily_review` | Mon–Fri (`scheduler.feedback_cron`) |
| 17:45 | `ipo_refresh_pm` | Daily |
| 18:00 | `weekly_review` | Sunday |
| 19:00 | `ipo_deep_dive` | Daily |
| 19:00 | `bhavcopy_daily_sync` | Mon–Fri |
| 23:00 | `atlas_universe_recompute` | Daily |
| 23:15 | `atlas_cost_rollup` | Daily |
| 23:20 | `atlas_retention` | Daily |
| 23:30 | `data_backup_nightly` | Daily |
| 23:45 | `audit_nightly` | Daily |
| 31 Dec 23:00 | `rl_calendar_update` | Yearly |

Not on this list because they are not cron jobs: the startup self-heal, the
post-review portfolio pipeline and digest, and the outbox drainer.

CLI, `python -m services.scheduler.run_schedule`: `start`, `run-now`,
`status`, `history`, `latest`, `forecast`, `daily-review`, `feedback-status`,
`reforecast`, `preopen-check`, `dossier-status`, `ingest-events`, `research`
and `scorecard`.

---

## 16. Identity, Multi-Tenancy & Data Governance

*"M0" (authentication) and "Atlas" (data architecture).* Design:
[SCALING_VISION.md](SCALING_VISION.md) and the
[data architecture spec](superpowers/specs/2026-07-26-m1-data-architecture-design.md).

| Part | Path | Role |
|---|---|---|
| Identity store | `services/data/stores/user_store.py` | scrypt hashing, sessions, invite-gated signup, quota counters |
| Auth middleware | `services/api/auth.py` | `get_current_user`, `require_owner`, machine key |
| Atlas core | `services/data/stores/atlas_store.py` | `data/atlas.db`, foreign-key linked |
| Plane boundary | `services/data/verdict_store.py` | The user plane's read seam over ticker-keyed output |
| Universe recompute | `core/portfolio/universe.py` | Writes aggregate counts only; no user identity crosses into the intelligence plane |
| Retention | `core/portfolio/retention.py` | Bounds the user-plane stores |
| ETL | `scripts/atlas_etl.py` | Freeze-cutover migration |
| Account deletion | `DELETE /auth/account` | One cascade |

**Two planes.** The intelligence plane is ticker-keyed and shared; the user
plane is user-keyed and private; they join only through `verdict_store`.
User-plane reads take the caller's own user id, chat's tools included: the
brief tool reads only the caller's portfolio, and refuses a request that
carries no valid user id (CHAT_ARCHITECTURE section 2). One exception
remains: with Atlas on and `AUTH_REQUIRED` on, an anonymous
`GET /ui/watchlist` reads the default user's watchlist.

**Server logs.** Log lines name users and their trade activity, and the ring
buffer redacts nothing, so `GET /ui/logs` and `/ui/logs/stream` take the
owner session or the machine key. A member gets 403 and a caller without a
session 401, before the buffer is read (KT section 10).

**Switches.** With `AUTH_REQUIRED` off (the code default), anonymous requests
act as the owner. With `ATLAS_ENABLED` off, the Atlas layer is a dormant
no-op and delivery sends inline.

---

## 17. Ops, Cost & Reliability

- **Watchdog** — `core/ops/watchdog/` (engine, registry, checks, prep,
  runner) reads `config/milestones.yaml` at 06:30, runs its invariants
  (`backup_recoverable` among them) and mails or pushes the result to the
  owner alone. A sent notice is not completion (KT section 10).
- **Operations backlog** — `core/ops/error_backlog.py` groups the durable
  WARNING+ log rows into issues, one per cause, that the owner reads and
  triages at `/ops/errors` (or `scripts/prod_errors.py`). The watchdog's
  `error_backlog_triaged` invariant warns the owner daily while one needs
  triage. A fix is verified
  by measured archive coverage, a recurrence reopens it, and a fix time the
  recorded occurrences already contradict is refused (KT section 10).
- **Backups** — `services/data/backup.py`: the Railway volume is the only
  home of the ledgers, the prediction tree and the SQLite stores. Each nightly
  archive is restore-drilled (`restore.py`) and, once the owner configures a
  bucket, copied off-site encrypted (`offsite.py`).
- **Self-monitoring in two tiers** — `ops_alerts.py` catches a job that
  crashed or produced nothing (with per-ticker review outcomes), and
  `core/audit/thresholds.py` catches output that is complete but wrong.
- **Cost telemetry** — per-model rates in `llm.cost_rates`, rolled up nightly
  by `atlas_cost_rollup`; provider counts in `api_usage.py`. Bundle counters
  are estimates. **Planned:** actual call counts (SA-025).
- **Benches** — `scripts/model_bench.py`, `reasoning_bench.py`,
  `aud098_thesis_tier_bench.py`.
- **Deploy** — `Dockerfile`, `docker-compose.yml`, Railway. Every push
  redeploys.

**Planned:** durable outcomes for every job, deploy-safe scheduling,
source-health records, silent-degradation checks, credit alerts, a status
fetcher and an outside witness (KT section 11).

---

## 18. Quality

`tests/` holds 333 test files and about 3,500 test functions in `unit/`,
`integration/`, `api/`, `contract/` and `frontend/`, with `fixtures/`. Every
run passes through `tests/hermetic.py`: no `.env`, no outbound network, an
empty working directory per test, and the checkout's `data/`, `logs/` and
`outputs/` off limits (KT section 13). CI runs three jobs on every push: the
test tree, the broad-exception guard with `check_kt_docs.py`, and the
browser suite.

Documentation tools: `scripts/docs/` builds the KT's PDF, checks the KT
against the code and STATE.json, and records review manifests. Audit
history: the [September audit](audit/2026-09-10-repository-production-review.md)
is the current baseline; [audit/LEDGER.md](audit/LEDGER.md) records every
`AUD-###` finding from the earlier programme.

---

## 19. Legacy & dead — know it so you skip it

| Item | Status |
|---|---|
| `services/csharp/StockAgent.Scheduler/` | Dormant: 9 `.cs` files, superseded by the Python scheduler. `CSHARP_SCHEDULER_ENABLED` defaults to false, a contract test still covers the settings, and `docker-compose.yml` keeps the service behind an opt-in `csharp` profile. The production image never references it |
| `main.py`, `new-product.py` | Old standalone entry points |
| `core/intelligence/rag/` | Retrieval stub, off, no corpus |
| 19 shim files | The half-finished restructure ([§0](#0-orientation)) |
| `src/backend/shared/prompts/feedback_agent.py` | An old copy; the live prompt is `core/config/prompts/shared/feedback_agent.py` |
| Legacy LangGraph worker pool | Fallback only; engagements counted |
| `services/data/cache/macro_cache.py` | Read by the bundle and legacy builders, but nothing writes it, so it never hits |

---

## 20. Suggested study order

**Week 1 — the spine**

1. [ARCHITECTURE.md](ARCHITECTURE.md) → [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md) sections 1–4 → [../CODEBASE.md](../CODEBASE.md)
2. Module 1 (configuration) → module 2 (LLM tiers)
3. Module 5 (analysis engine): trace `POST /analyse` for one ticker, from
   resolution through the bundle to the decision gate
4. `src/backend/shared/schemas/pipeline.py`, the contract everything speaks

**Week 2 — the loop**

5. [RL_DESIGN.md](RL_DESIGN.md), then module 7 in this order: schemas →
   `generate_forecast` → **`daily_review`, steps 0–10** → `feedback_agent` →
   `weight_adapter` → `learning_mode` → `ledger_propagator`
6. Module 6 (regime) and module 8 (dossier), both hung off the daily review

**Week 3 — the product surface**

7. Module 9 (portfolio) → module 10 (discovery and IPO) → module 11 (delivery)
8. Module 15 (scheduler): by now the 24 jobs read as a story, not a list

**Week 4 — the meta layers**

9. Module 12 (auditor) and module 13 (evidence): the two things measuring
   whether the rest works
10. Module 14 (API and frontend), module 16 (identity and Atlas), module 17
    (operations), module 18 (tests)

---

## 21. Cross-cutting laws

*These repeat in every module. Learn them once and the code stops surprising
you.*

1. **Code decides; the model reads and explains.** Advisor, autopilot,
   discovery guards, auditor, regime detector, decision gate and verdict
   binding are deterministic. The model scores dimensions, narrates and
   proposes.
2. **Non-fatal by contract.** Every enrichment step is wrapped; a failure
   degrades its signal and never blocks the pipeline. The typed status says
   which signal degraded and why.
3. **Evidence before action.** An analysis whose essential data is missing,
   or whose identity is unresolved, is recorded as such; in `enforce` mode
   nothing builds on it.
4. **Append-only ledgers are the audit authority.** Transactions, advice,
   value history and switch evaluations are append-only, and the nightly
   backup drill flags a rewritten one.
5. **Dark-signal renormalization.** A missing feed means drop the signal and
   renormalise over what remains; never impute zero.
6. **`n` travels with every number.** Metrics return `None`, not 0, when
   there is no data; a fresh install reads `INSUFFICIENT_DATA`.
7. **Configuration over hardcoding, mostly.** Business tunables go through
   `cfg()`. Some algorithm constants live in code: the aggregator's 0.30
   conflict gap, the 20% external-shock cap, the Monte Carlo regime scales.
8. **Two planes.** Intelligence (ticker-keyed, shared) and user (user-keyed,
   private), joined only through `verdict_store`.
9. **A switch per feature.** `rl.learning_mode`, `decision_gate.mode`,
   `AUTH_REQUIRED`, `ATLAS_ENABLED`, `DISCOVERY_ENABLED`, `DELIVERY_ENABLED`,
   `delivery.brief_html_enabled`, `audit.enabled`, `ipo.enabled`,
   `rl.hard_bind_verdict_enabled`, `rl.macro_fallback_context_enabled`.
10. **Idempotency where a job repeats.** Grading, alerts, transactions, value
    points and observation records are keyed so a re-run adds nothing. The
    learning update itself is not yet (**Planned:** SA-015).
11. **Isolation for anything that must not teach the system.** The paper lane
    runs real forecasts under its own store root with every learning write
    removed.
