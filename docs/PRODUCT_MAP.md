# StockAgent — Product Map

> **The study document.** Every major module and its minor modules, in one
> place, with a suggested reading order. Where [ARCHITECTURE.md](ARCHITECTURE.md)
> explains *how the system fits together* and the deep-dives explain *how one
> subsystem works*, this document answers a different question: **"what are all
> the parts, and in what order should I learn them?"**
>
> Enumerated directly from the source tree — module lists, job counts and
> endpoint counts here are counted, not remembered.
>
> Verified against the code on **2026-08-08** (post verification-layer merge
> `33956ae`, audit read-path `6ef3c42`).

---

## 0. Orientation

**What the product is:** a single Python process — FastAPI plus an in-process
APScheduler thread — that runs an Indian-equity research loop. It forms a
monthly price forecast per stock, checks itself against reality every trading
day, learns from the miss, manages a virtual portfolio off those signals,
discovers new candidates weekly, delivers briefs and alerts to a PWA, and
grades its own advice against NIFTY.

**Scale (source, excluding tests and vendored deps):**

| Area | Lines |
|---|---|
| `core/` | ~21,200 |
| `services/` | ~17,800 |
| `src/` | ~11,700 |
| `scripts/` | ~1,500 |
| `tests/` | ~38,000 |

**Surface:** 88 HTTP endpoints + 1 WebSocket across 13 routers · 20 scheduled
jobs · 4 native sectors + 1 generic · 3 LLM tiers.

### The one structural trap

The April-2026 restructure is **not finished**, and it stalled in *both*
directions. There are **19 shim files in two families that point opposite
ways** — so "follow the shim" is not a single rule (census verified
2026-08-09).

**Family A — `MIGRATION SHIM`, 9 files: `core/*` → `src/backend/*`.**
The real code moved out of `core/`; the old import path is kept alive.

```
core/schemas/feedback.py             40 → src/backend/shared/schemas/feedback.py  (1,079)
core/schemas/pipeline.py             22 → src/backend/shared/schemas/pipeline.py
core/pipeline/orchestrator.py         7 → src/backend/sectors/automobile/pipeline/orchestrator.py
core/pipeline/signal_aggregator.py    4 → src/backend/shared/pipeline/signal_aggregator.py
core/pipeline/base_agent.py           4 → src/backend/shared/pipeline/base_agent.py
core/config/settings/base.py          4 → src/backend/shared/config/settings/base.py
core/config/settings/__init__.py      5 → src/backend/shared/config/settings/base.py
core/config/rag_config.py             3 → src/backend/shared/config/rag_config.py
core/config/prompts/shared/signal_aggregator.py 3 → src/backend/shared/prompts/signal_aggregator.py
```

**Family B — `FORWARD SHIM`, 10 files: `src/backend/shared/*` → `services/*`.**
The real code already lives in `services/`; the `backend.shared.*` path is kept
alive for a "Phase 7" move that has no owner and is documented nowhere.

```
src/backend/shared/clients/llm_client.py        → services/clients/llm_client.py
src/backend/shared/clients/tavily_fetcher.py    → services/clients/tavily_fetcher.py
src/backend/shared/data/cache/macro_cache.py    → services/data/cache/macro_cache.py
src/backend/shared/data/fetchers/{fundamentals,macro,news}.py
                                                → services/data/fetchers/…
src/backend/shared/data/stores/{analysis_logger,api_usage,run_logger,score_store}.py
                                                → services/data/stores/…
```

**Corrected rule while studying: a file under ~10 lines is a shim — read its
first line to learn which way it points.** `MIGRATION SHIM` sends you to
`src/backend/`; `FORWARD SHIM` sends you to `services/`. The header comment
always names the real module.

**Why this matters beyond tidiness.** One module can be reached by two names,
and the same file sometimes uses both. `src/backend/shared/pipeline/base_orchestrator.py`
imports `llm_client` through the Family-B shim on line 47 and imports directly
from `services.clients.llm_client` on line 48 — same underlying module, two
paths, adjacent lines. Expect this when tracing imports.

---

## 1. Platform & Configuration Substrate

*The plane everything else reads from. Study first — nothing else parses
without it.*

| Minor module | Path | Owns |
|---|---|---|
| Settings loader | `src/backend/shared/config/settings/loader.py` | The `cfg()` function and the precedence chain |
| Settings base | `src/backend/shared/config/settings/base.py` | 984 lines of hardcoded fallback defaults |
| Tunable config | `config.yaml` | 22 sections (below) |
| Sector toggles | `config/sector_toggles.json` | Per-sector enable + tier |
| Secrets | `.env` | API keys only |
| Atomic writes | `core/utils/atomic_io.py` | temp+rename JSON writer (AUD-057) |
| Prompt registry | `core/config/prompts/shared/` | 8 prompt modules for non-sector LLM agents |

**Precedence:** environment variable **>** `config.yaml` **>** hardcoded
fallback in `base.py`.

**`config.yaml` sections:** `llm`, `logging`, `agent_execution`,
`agent_weights`, `score_thresholds`, `data_fetch`, `scheduler`, `chat`,
`macro_news`, `regime`, `regime_multipliers`, `sector_agent_regime_role`, `rl`,
`unified_analyst`, `portfolio`, `advisor`, `discovery`, `generic_graph`,
`delivery`, `atlas`, `audit`, `universe`.

**Product law.** All business tunables (quotas, tiers, prices, caps,
thresholds, weights) go through `cfg()` / `config.yaml`, never hardcoded.
Non-secret toggles must have **no** `env=` binding — `config.yaml` is the sole
source, and flipping one means editing yaml and redeploying. Secrets, API keys
and flags whose live value lives in Railway keep `env=`.

---

## 2. LLM & External Service Clients

| Minor module | Path | Role |
|---|---|---|
| LLM client | `services/clients/llm_client.py` | OpenRouter wrapper, 3 tiers, sync + async, cost telemetry |
| Tavily fetcher | `services/clients/tavily_fetcher.py` | Deep-page retrieval + disk cache (`data/tavily_cache/YYYY-MM/`) |
| Quota counter | `services/data/stores/api_usage.py` | Persistent monthly counter (Serper 2500/mo), boot self-check |

**Three tiers** (`config.yaml` → `llm`):

| Tier | Model | Used for |
|---|---|---|
| `fast` | `qwen/qwen3.6-flash` | Chat tool-loop (tools + free text, no `json_object`) |
| `reasoning` | `z-ai/glm-5.2` | Judgment: aggregator verdict, RL feedback, thesis review, unified analyst |
| `bulk` | `deepseek/deepseek-v4-flash` | High-volume sector scoring, narration |

**Hard rule.** Every `json_object` call site must pass
`extra_body=JSON_MODE_EXTRA_BODY`. OpenRouter silently rolled several models to
thinking-by-default snapshots that truncate JSON-mode output; this flag
disables reasoning. Violating it is how models get silently retired.

---

## 3. Data Acquisition Layer

*15 fetchers plus context assembly. Every one follows the **non-fatal
contract**: a fetch failure degrades its signal to "dark", never crashes the
pipeline.*

| Minor module | Path | Source |
|---|---|---|
| NSE client factory | `services/data/fetchers/nse_client.py` | Guaranteed temp-dir cleanup (AUD-017) |
| NSE key registry | `services/data/fetchers/nse_key_registry.py` | Learns NSE's field renames across report vintages |
| Bhavcopy | `services/data/fetchers/bhavcopy.py` | EOD backbone incl. delivery % |
| Close verifier | `services/data/fetchers/close_verifier.py` | Cross-checks yfinance close vs official NSE close |
| Announcements | `services/data/fetchers/nse_announcements.py` | Per-ticker filings, one pre-fetch per run |
| Corporate events | `services/data/fetchers/corporate_events.py` | Splits / bonus / dividend + board meetings |
| Market intel | `services/data/fetchers/nse_market.py` | FII/DII flows via nsepython |
| Bulk / block deals | `services/data/fetchers/bulk_block.py` | Institutional accumulation |
| Surveillance | `services/data/fetchers/surveillance.py` | ASM/GSM, suspension, float mcap |
| IPO feed | `services/data/fetchers/ipo.py` | Current / upcoming / past listings |
| Fundamentals | `services/data/fetchers/fundamentals.py` | yfinance financials |
| Macro | `services/data/fetchers/macro.py` | Rates, currency, commodities |
| MF herding | `services/data/fetchers/mf_herding.py` | AMFI sector-ETF NAV momentum (no API key) |
| News | `services/data/fetchers/news.py` | Serper + NewsAPI |
| Symbol resolver | `src/backend/shared/data/fetchers/symbol_resolver.py` | Self-healing NSE→yfinance; zero-network happy path |
| Macro news fetcher | `services/background/macro_news_fetcher.py` | Two-agent background fetcher |
| Macro news cache | `services/background/macro_news_cache.py` | Daily JSON cache |
| Context builder | `services/data/context/builder.py` | 861 lines — per-agent context |
| Bundle builder | `services/data/context/bundle_builder.py` | 498 lines — one shared fetch pass for the unified analyst |

**The instructive failure in this layer.** News fetches lacked a `tbs` recency
bound. Serper was never returning nothing — it returned months-old articles
that the 3-day filter correctly dropped, producing a 75% news-blind rate that
silently contaminated RL learning for weeks. Measured blind 0/12 before the fix
vs 12/12 after. The lesson generalises: *a filter dropping everything looks
identical to a source returning nothing.*

---

## 4. Persistence Layer

*Mixed storage by design: SQLite for queried data, JSON for state, JSONL for
append-only ledgers, parquet for EOD panels.*

| Minor module | Path | Backing |
|---|---|---|
| Score store | `services/data/stores/score_store.py` | SQLite — analysis history |
| Log store | `services/data/stores/log_store.py` | SQLite telemetry archive (Railway logs rotate per deploy) |
| User store | `services/data/stores/user_store.py` | SQLite `users.db` — users, sessions, invites, quota |
| Atlas store | `services/data/stores/atlas_store.py` | SQLite `atlas.db` — user-plane relational core |
| EOD store | `services/data/stores/eod_store.py` | Parquet, one file per trading day |
| Prediction store | `core/intelligence/rl/stores/prediction_store.py` | The RL file tree (below) |
| Portfolio store | `core/portfolio/store.py` | Per-user JSON + append-only JSONL |
| Chat sessions | `services/data/stores/chat_session_store.py` | Volume-backed chat memory |
| Analysis logger | `services/data/stores/analysis_logger.py` | Per-run structured output |
| Run logger | `services/data/stores/run_logger.py` | Every LLM call, JSONL |
| Job outcomes | `services/data/stores/job_outcomes.py` | Last-run result per cron job (AUD-090d) |
| Fallback events | `services/data/stores/fallback_events.py` | Legacy-pool engagement record |
| Verdict store facade | `services/data/verdict_store.py` | **The plane boundary** |
| Backup | `services/data/backup.py` | Nightly zip + off-site email |

### The RL file tree — memorise this

`data/predictions/<sector>/<TICKER>/`:

```
{TICKER}_YYYY-MM_prediction_envelope.json    30-day forecast path
{TICKER}_YYYY-MM_daily_feedback_log.json     daily hit/miss records
{TICKER}_YYYY-MM_control_log.json            bare-LLM duel opponent
{TICKER}_YYYY-MM_prompt_enhancements.json    self-improving prompt deltas
{TICKER}_agent_weight_memory.json            learned per-agent weights
{TICKER}_learning_ledger.json                stock-specific lessons
{TICKER}_dossier.json                        PERMANENT knowledge document
{TICKER}_thesis_calls.jsonl                  thesis-review history
{TICKER}_YYYY-MM-DD_offmarket.json           block/bulk/pre-open signals
```

Shared, one level up:

```
data/predictions/<sector>/_shared_ledger.json    sector-wide lessons
data/predictions/_market_ledger.json             market-wide lessons
data/predictions/_regime_state.json              sticky regime
```

Per-user portfolio plane:

```
data/portfolio/<user_id>/portfolio.json
data/portfolio/<user_id>/advice_ledger.jsonl      APPEND-ONLY (test-enforced)
data/portfolio/<user_id>/advice_outcomes.jsonl    graded rows (auditor)
data/portfolio/<user_id>/digests/
```

---

## 5. Analysis Engine — the verdict producer

*Given a ticker, produce a `FinalReport` with score, verdict and thesis.*

### 5.1 Routing

- `src/backend/sectors/registry.py` — `TICKER_SECTOR` map, `detect_sector()`,
  `get_orchestrator()`
- Sectors: `automobile`, `banking_bfsi`, `it_sector`, `renewable_energy`, plus
  `generic` for unmapped tickers

### 5.2 The two execution paths — the critical distinction

| Path | Entry | Cost |
|---|---|---|
| **Unified analyst** (live) | `src/backend/shared/pipeline/unified_analyst.py` | **ONE** reasoning call → all dimension outputs |
| **Legacy worker pool** (fallback) | `src/backend/shared/pipeline/graphs/` | LangGraph fan-out, ~9 parallel bulk calls |

Supporting:

- `src/backend/shared/pipeline/base_orchestrator.py` — abstract base; chooses the path
- `src/backend/shared/pipeline/base_agent.py` — per-agent contract
- `src/backend/shared/agents/universal/agent.py` — one class replaces every
  sector-specific agent class; behaviour comes entirely from the injected
  prompts module
- `graphs/nodes.py` (node factories), `graphs/rails.py` (guardrail validator),
  `graphs/state.py` (merge-reducer state for parallel fan-out)

Fallback engagements are recorded in `services/data/stores/fallback_events.py`
— the analyst failing over used to be invisible.

### 5.3 Per-sector dimensions

Study one sector fully; the rest rhyme.

| Sector | Dimensions |
|---|---|
| `automobile` | fundamentals, sales_demand, raw_materials, competitive_intel, policy_regulatory, pattern_analysis, sentiment, risk_macro, valuation_catalyst |
| `banking_bfsi` | fundamentals, macro_policy, risk, universe_setup |
| `it_sector` | fundamentals, global_macro, peer_benchmark, transcript_nlp, sentiment, risk_macro |
| `renewable_energy` | business, fundamentals, valuation, risk, sentiment_policy |
| `generic` | `src/backend/sectors/generic/prompts/dimensions.py` |

Cross-sector prompts (deduplicated): `src/backend/shared/agents/prompts/technical.py`,
`.../institutional_flow.py`.

### 5.4 Fusion & scoring

- `src/backend/shared/pipeline/signal_aggregator.py` — weighted fusion +
  conflict resolution → final verdict
- `src/backend/shared/pipeline/verdict_shadow.py` — **AUD-077 shadow lane**.
  The RL loop learns per-agent weights, but the final verdict was emitted by
  the LLM; this observed the divergence until hard-bind was enabled
  (2026-08-03). Both tests pass in either flag state so rollback stays green.

### 5.5 Numeric sub-engines

| Minor module | Path | Note |
|---|---|---|
| C++ indicators | `core/intelligence/algorithms/cpp/src/indicators.cpp` | RSI, MACD, Bollinger, adjusted/unadjusted EWM via pybind11 |
| Indicator fetcher | `core/intelligence/algorithms/indicators/fetcher.py` | Python side |
| FnO analyzer | `core/intelligence/fno/analyzer.py` | PCR, max-pain, OI shifts |
| FnO fetcher | `core/intelligence/fno/fetcher.py` | NSE options chain |
| Prompt enhancer | `core/intelligence/prompt_enhancer/enhancer.py` | Prompts that improve from feedback |
| RAG | `core/intelligence/rag/` | **Stub, inactive** — forward-declared only |

---

## 6. Regime & Market-State Intelligence

| Minor module | Path | What |
|---|---|---|
| Regime detector | `core/intelligence/regime/detector.py` | 3 cheap yfinance signals → 6 labels. **No LLM.** |
| Sticky regime | `core/intelligence/regime/state.py` | Hysteresis so the label does not flap daily |
| Regime multipliers | `config.yaml` → `regime_multipliers`, `sector_agent_regime_role` | Which agent's weight is boosted in which regime |
| Factor regime | `core/intelligence/rl/algorithms/factor_regime.py` | IIMA India Fama-French 4-factor signal |
| Seasonal calendar | `core/intelligence/seasonal/calendar.py` | Pre-seeded YAML patterns ⊕ RL-discovered seasonal lessons |
| Seasonal validator | `core/intelligence/seasonal/validator.py` | Tracks confirmation/contradiction of seeded patterns |
| Conviction tracker | `core/intelligence/rl/conviction/tracker.py` | **P3** — long BUY/SELL streaks raise mean-reversion risk |
| NSE calendar | `core/intelligence/rl/nse_calendar.py` | Trading-day math |
| Calendar updater | `core/intelligence/rl/calendar_updater.py` | Dec 31 auto-refresh, three-layer fallback |

Regime labels: `MACRO_CRISIS`, `RISK_OFF`, `MOMENTUM_EXTENDED`, and three more
— see the detector docstring.

---

## 7. The Adaptive Learning Loop (RL) — the heart

*~6,000 lines. Budget the most study time here.* Full narrative:
[RL_DESIGN.md](RL_DESIGN.md).

### 7.1 Forecast generation (monthly)

`core/intelligence/rl/workflows/generate_forecast.py` (760) — runs the analysis
engine, then builds a **PredictionEnvelope**: a 30-day price path with per-day
forecast and confidence.

- `core/intelligence/rl/algorithms/price_interpolator.py` (623) — LLM-calibrated
  path shape, replacing an old static dict
- `core/intelligence/rl/workflows/sector_router.py` — shared routing so forecast
  and review can never disagree about which orchestrator or weights apply

### 7.2 Daily review — the 11-step spine

`core/intelligence/rl/workflows/daily_review.py` (1,572). **Read this file top
to bottom; it is the product.**

| Step | What happens |
|---|---|
| 0 | Detect market regime (non-fatal → NORMAL) |
| 1 | Load envelope, find today's forecast row |
| 2 | Fetch actual close + volume context (NSE cross-checked) |
| 3 | Compute error metrics + timing accuracy |
| 4 | **FeedbackAgent** → miss_type, miss analysis, raw lessons |
| 5 | **WeightAdapter** → adjust per-agent weights, miss_type-aware |
| 5.5 | Apply regime multipliers to effective weights |
| 6 | **LearningLedger** merge + propagate to sector/market ledgers |
| 6.5 | Update conviction streak + compute reversion prior |
| 7a | *Conditional:* **ThesisReviewer** on a significant miss |
| 7b | Revise remaining forecast days with regime-adjusted weights |
| 8 | Append the complete `FeedbackEntry` |
| 8.5 | **DossierCurator** — runs every day, hit or miss |
| 9 | Seasonal validation — month-end only |
| 10 | **Control lane** — the bare-LLM duel |

### 7.3 The learning agents

| Agent | Path | Role |
|---|---|---|
| FeedbackAgent | `core/intelligence/rl/agents/feedback_agent.py` (600) | Classifies the miss, writes lessons. Carries the **evidence rule**: *absence of news is not evidence of model_bias*; 20% external_shock cap |
| WeightAdapter | `core/intelligence/rl/agents/weight_adapter.py` (549) | Moves per-agent weights; derives the agent list from `WeightMemory`, so zero sector hardcoding |
| ThesisReviewer | `core/intelligence/rl/agents/thesis_reviewer.py` | Fires when \|price_error_pct\| > max(1.5%, 1.5 × atr_pct) |
| ControlLane | `core/intelligence/rl/agents/control_lane.py` | Bare LLM: same close + market context, **no** tools, memory, weights, lessons or dossier — the honest opponent |

### 7.4 Lesson machinery

| Minor module | Path | Role |
|---|---|---|
| Ledger propagator | `core/intelligence/rl/stores/ledger_propagator.py` (545) | **P2** — routes lessons to stock / sector / market ledger by scope |
| Lesson emphasis | `core/intelligence/rl/algorithms/lesson_emphasis.py` | The **only** place tagged lessons act numerically on scores; deltas read from settings at call time so they never go stale |
| Provenance | `core/intelligence/rl/provenance.py` | **F3** — every lesson and dossier observation keeps the date + headline that produced it |
| Month-end validation | `core/intelligence/rl/workflows/month_end_validation.py` | Extracted from Step 9 |

### 7.5 Living Envelope (Phase 2.5)

- `core/intelligence/rl/workflows/preopen_check.py` — 08:45 IST market-level
  overnight shock rating; can trigger an envelope re-forecast. Never fatal.
- `core/intelligence/rl/stores/offmarket_fetcher.py` — block/bulk/pre-open
  auction as a **next-day leading** signal, fetched at the end of the review

### 7.6 Schemas

`src/backend/shared/schemas/feedback.py` — 1,079 lines, 30+ Pydantic v2 models.
The four JSON memory structures: `PredictionEnvelope`, `DailyFeedbackLog`,
`WeightMemory`, `LearningLedger`.

---

## 8. Knowledge Layer (Ticker Dossier)

*Permanent per-ticker knowledge that survives forecast cycles.*

| Minor module | Path | Cadence |
|---|---|---|
| Dossier schema | `src/backend/shared/schemas/dossier.py` | — |
| DossierCurator | `core/intelligence/rl/agents/dossier_curator.py` | Daily (Step 8.5) + weekly distillation |
| EventIngestor | `core/intelligence/rl/agents/event_ingestor.py` | Sat 10:00 — results, concalls, guidance, investor presentations, digested into the **same** JSON contract the curator emits |
| QuestionResearcher | `core/intelligence/rl/agents/question_researcher.py` | Sat 11:00 — targeted search to resolve dossier `open_questions`, one batched judgment call per ticker |

**Design principle.** The LLM *proposes* dossier updates; the merge code
enforces every bound deterministically and **never raises** — any failure
returns the dossier unchanged so the daily review is never blocked.

Note for spec-readers: dossier observations are the `DossierObservation` model
(`dossier.py`), not plain dicts.

---

## 9. Portfolio & Advisory ("Compass")

*Virtual money, real NSE prices.* Full narrative:
[AUTOPILOT_GUIDE.md](AUTOPILOT_GUIDE.md).

| Minor module | Path | Role |
|---|---|---|
| Schemas | `src/backend/shared/schemas/portfolio.py` | `adj_avg_price` / `adj_qty` are corp-action-adjusted — **all** P&L and stop math uses these |
| Store | `core/portfolio/store.py` | `data/portfolio/<user_id>/` — JSON + append-only JSONL |
| Advisor | `core/portfolio/advisor.py` | Pure-Python decision engine. Precedence **EXIT > TRIM > ADD > HOLD**, non-negotiable |
| Autopilot | `core/portfolio/autopilot.py` | Deterministic execution of verdicts. Virtual money only — no broker calls, ever |
| Narrator | `core/portfolio/narrator.py` | BULK-tier phrasing. **The engine decides; the LLM only phrases.** Falls back to deterministic text from trigger codes |
| Narrative cache | `core/portfolio/narrative_cache.py` | Day-scoped, keyed by verdict context — one LLM call per (symbol, verdict, …) across all users |
| Pricing | `core/portfolio/pricing.py` | Reuses daily_review's NSE-verified close fetcher |
| Corp actions | `core/portfolio/corp_actions.py` | Splits / bonus adjustment |
| Promotion | `core/portfolio/promotion.py` | Held or watchlisted symbols auto-promoted into `managed_tickers.json` |
| Pipeline | `core/portfolio/pipeline.py` | Post-review orchestration. **Order is load-bearing:** corp-action sync runs FIRST |
| Digest | `core/portfolio/digest.py`, `digest_text.py` | EOD per-holding verdicts. **Event-triggered, never clock-scheduled** — at 40 tickers the review takes ~80 min |
| Reconcile | `core/portfolio/reconcile.py` | Drift detection |
| Retention | `core/portfolio/retention.py` | Nightly prune; every cap a `cfg()` tunable, `None` = keep-all |
| Universe | `core/portfolio/universe.py` | Atlas C4 nightly demand-tier recompute |

---

## 10. Discovery Engine (Compass Phase B)

*Weekly funnel: full universe → shortlist → deep dives → shelf → promotion.*

| Stage | Path | What |
|---|---|---|
| Universe | `core/discovery/universe.py` | Mainboard EQ series only, price floor |
| Signals | `core/discovery/signals.py` | 7 pure-pandas signals, zero LLM. Returns `None` when **DARK** |
| Screen | `core/discovery/screen.py` | Weighted percentile-rank composite, **renormalized over live signals only** |
| Guards | `core/discovery/guards.py` | Free bhavcopy gates (liquidity, series, price, circuit streaks) then per-symbol gates (surveillance, float mcap) on the shortlist only |
| Deep dive | `core/discovery/deep_dive.py` | ONE reasoning call per name + deterministic entry zone and ATR-scaled invalidation level |
| Shelf | `core/discovery/shelf.py` | Capped; a stronger idea displaces the weakest; stale ideas rotate out |
| Paper lane | `core/discovery/paper_lane.py` | Virtual position, real forecasts, **isolated store root, zero learning writes** |
| IPO tracker | `core/discovery/ipo_tracker.py` | Research-calibrated: post-listing evidence outweighs subscription froth |
| Schemas | `src/backend/shared/schemas/discovery.py` | `ScreenResult`, `DeepDiveResult`, shelf |

**Pattern worth extracting: dark-signal renormalization.** Sub-scores normalise
over whatever is actually available, so a missing feed degrades precision
instead of poisoning the score with an implicit zero. The same pattern recurs
in the screen, the IPO tracker and the advisor.

---

## 11. Delivery Layer (Compass Phase C)

| Minor module | Path | Trigger |
|---|---|---|
| Morning brief | `core/delivery/brief.py` (978) | Mon–Fri 08:50 IST. Deterministic assembly + **one** bulk narration call, fallback text on any failure. Styled HTML multipart/alternative |
| Weekly review | `core/delivery/weekly.py` | Sun 18:00 — allocation vs risk profile, laggards, switch candidates from the shelf, advice-ledger scoreboard |
| Alerts | `core/delivery/alerts.py` | Event-driven. Dedupe key `{user_id}\|{date}\|{kind}\|{symbol}` |
| Channels | `core/delivery/channels.py` | web-push (pywebpush + VAPID) + email; prunes dead subscriptions on 400/403/404/410 |
| Outbox | `core/delivery/outbox.py` | Atlas C7 durable queue when `ATLAS_ENABLED`; inline send otherwise |
| Index watch | `core/delivery/index_watch.py` | Weekly constituent diff → inclusion/exclusion alerts for held + watchlist + shelf only. First snapshot never alerts |
| Ops alerts | `core/delivery/ops_alerts.py` | **Self-monitoring.** Born from 2026-07-11: a dead OpenRouter key produced 887 silent 401s over 3 hours while every job logged "complete" |

**Compliance constraint threaded through all of it:** output is framed as
research/analysis, never "advice" — see
[LEGAL_AND_COMPLIANCE.md](LEGAL_AND_COMPLIANCE.md).

---

## 12. Verification Layer ("the auditor")

*Deterministic, no LLM. Grades what the system actually told users, against
`^NSEI`. Design:
[superpowers/specs/2026-08-07-verification-layer-design.md](superpowers/specs/2026-08-07-verification-layer-design.md).*

| Minor module | Path | Role |
|---|---|---|
| Rules | `core/audit/rules.py` | **What "correct" means.** Pure functions, no I/O — the one file that cannot be quietly changed without invalidating accumulated history |
| Outcomes | `core/audit/outcomes.py` | The recorder. Idempotent by `(ref, horizon_td)`; never raises — a bad row is counted and skipped |
| Benchmark | `core/audit/benchmark.py` | NIFTY 50 close lookup — the only benchmark fetch in the codebase |
| Metrics | `core/audit/metrics.py` | Pure. Every function reports its own `n` and returns `None`, never `0`, when there is nothing to compute |
| Thresholds | `core/audit/thresholds.py` | Breach rules — catches jobs producing **full but silently wrong** output, which `ops_alerts` structurally cannot see |
| Report | `core/audit/report.py` | One verdict word; vocabulary deliberately shared with the Learning Evidence report |
| Store | `core/audit/store.py` | Separate append-only JSONL — never annotates the advice ledger |
| CLI | `core/audit/cli.py` | `python -m core.audit.cli --report \| --backfill` |
| Schema | `src/backend/shared/schemas/audit.py` | The graded-outcome row |

**Study the failure, not just the code.** The layer graded 0/119 on its first
production run: `_fetch_index_close` used a 1-day yfinance window, which
returns empty for `^NSEI`. The function had been "isolated so tests can patch
it" — so the one function that touched the network was the one function never
tested against it. 84 green tests hid a bug that broke 100% of the feature.

---

## 13. Measurement & Scientific Evidence

*Distinct from the auditor: this measures whether **learning** works, not
whether **advice** works.*

| Minor module | Path | Question |
|---|---|---|
| Eval harness | `core/intelligence/rl/eval/harness.py` | load → replay → aggregate, **read-only** |
| Metrics | `core/intelligence/rl/eval/metrics.py` | Pure functions over `FeedbackEntry` lists |
| Baselines | `core/intelligence/rl/eval/baselines.py` | Naive predictors the system must beat |
| Scorecard | `core/intelligence/rl/eval/scorecard.py` | Monthly baseline duel — StockAgent vs the control lane |
| Learning evidence | `core/intelligence/rl/eval/learning_evidence.py` (727) | **Self-ablation:** does the learning machinery actually help? |
| Synthetic | `core/intelligence/rl/eval/synthetic.py` | Deterministic fabricated logs so metrics run without real history |
| Runner | `core/intelligence/rl/eval/run_eval.py` | CLI |
| Schemas | `src/backend/shared/schemas/scorecard.py` | `ControlPrediction` / `ControlLog` |

Read alongside [audit/ADAPTIVE_LEARNING_REVIEW.md](audit/ADAPTIVE_LEARNING_REVIEW.md)
(gaps G1–G10).

---

## 14. Service & Interface Layer

### 14.1 API — `services/api/server.py`

13 routers, **85 router endpoints + 1 WebSocket + 3 app-level** (`/health`,
`/tickers`, SPA catch-all).

| Router | Path | Surface |
|---|---|---|
| ui_data | `services/api/routes/ui_data.py` **(3,801 lines)** | 30 endpoints: bootstrap, market summary, trending, watchlist, categories, search, learnings, managed tickers, agent weights/tasks, logs — **plus the entire chat engine** |
| portfolio | `services/api/routes/portfolio_api.py` | holdings, watchlist, CSV import, advice, digest, transactions, performance, run-advisor |
| analytics | `services/api/routes/analytics.py` | rl-export, agent-accuracy, weight-drift, miss-breakdown, conviction-outcomes, sector-comparison, **Power BI OData feed** |
| prompts | `services/api/routes/prompts.py` | Live prompt read/edit + GitHub deploy |
| scheduler | `services/api/routes/scheduler_api.py` | status + HTTP job triggers |
| rl_monitor | `services/api/routes/rl_monitor.py` | 5 read-only adapters over PredictionStore (AUD-100) |
| delivery | `services/api/routes/delivery_api.py` | brief/weekly latest, manual runs, alert tail, push subscribe |
| discovery | `services/api/routes/discovery_api.py` | shelf, screen, run, promote, drop |
| auth | `services/api/routes/auth_api.py` | signup, login, logout, me, invites, **DPDP account delete** |
| audit | `services/api/routes/audit_api.py` | summary, backfill |
| analyse | `services/api/routes/analyse.py` | On-demand full pipeline run |
| history | `services/api/routes/history.py` | SQLite score history |
| stream | `services/api/routes/stream.py` | WebSocket `/ws/stream?ticker=` agent progress |
| Auth gate | `services/api/auth.py` | session / owner / machine-key tiers |
| Log buffer | `services/api/log_buffer.py` | In-memory ring buffer for live log streaming |

### 14.2 Chat sub-system

Lives inside `ui_data.py` but is a module in its own right. Agentic streaming
tool-loop; the old DAG is retired. Design:
[CHAT_ARCHITECTURE.md](CHAT_ARCHITECTURE.md).

- **5 tools:** `get_live_price`, `get_historical_prices`, `get_macro_news`,
  `search_market_news`, `screen_stocks`
- **Context builders:** `_build_chat_context`, `_nse_market_context`,
  `_ctx_rl_learning`, `_ctx_current_verdicts`, `_ctx_recent_history`,
  `_ctx_ticker_detail`
- IST session awareness, NSE-first symbol resolution, sector movers,
  result-age labelling

### 14.3 Frontend — `src/frontend/prototypes/`

Single-page PWA, 21 JSX modules + a versioned service worker:

`home` · `portfolio` · `brief-view` · `digest-view` · `weekly-view` · `inbox` ·
`analytics` · `agents-page` · `rl-monitor` · `rl-data` · `prompt-lab` ·
`settings` · `auth` · `learn` · `logs` · `data` · `sphere` · `tweaks-panel` ·
`hooks` · `icons` · `sw.js`

Responsive gate: `node scripts/ui_responsive_audit.mjs`. Android ships as a
PWABuilder TWA wrapping this prototype (the React app under `src/prototypes/`
is a stub).

---

## 15. Time Orchestration

`services/scheduler/python/scheduler.py` (1,254) — an APScheduler
`BackgroundScheduler` thread inside the FastAPI process. **20 registered jobs.**
This is the product's clock; study it as a module in its own right.

| IST | Job id | Days |
|---|---|---|
| 00:00 | `prompt_daily_deploy` | daily |
| 02:00 | `scorecard_monthly` | 1st |
| 03:30 | `ledger_cleanup_weekly` | Mon |
| 07:30 | `macro_daily_news` | Mon–Fri |
| 08:45 | `preopen_shock_check` | Mon–Fri |
| 08:50 | `morning_brief` | Mon–Fri |
| 09:00 | `rl_monthly_forecast` | 1st |
| 09/12/15 | `macro_market_news` | Mon–Fri |
| 10:00 | `event_ingest_weekly` | Sat |
| 11:00 | `research_loop_weekly` | Sat |
| 12:30 | `discovery_weekly` | Sat |
| `FEEDBACK_CRON` (16:30) | `rl_daily_review` | trading days |
| 18:00 | `weekly_review` | Sun |
| 19:00 | `bhavcopy_daily_sync` | Mon–Fri |
| 23:00 | `atlas_universe_recompute` | daily |
| 23:15 | `atlas_cost_rollup` | daily |
| 23:20 | `atlas_retention` | daily |
| 23:30 | `data_backup_nightly` | daily |
| 23:45 | `audit_nightly` | daily |
| Dec 31 23:00 | `rl_calendar_update` | yearly |

Not on this list because it is **event-triggered**: the EOD portfolio digest,
fired by `scheduler_api._review_task` after the reviews finish.

CLI surface — `services/scheduler/run_schedule.py`: `start`, `run-now`,
`status`, `history`, `latest`, `forecast`, `daily-review`, `feedback-status`,
`reforecast`, `preopen-check`, `scorecard`, `ingest-events`, `research`.

---

## 16. Identity, Multi-Tenancy & Data Governance

*"M0" (auth) and "Atlas" (data architecture). Design:
[SCALING_VISION.md](SCALING_VISION.md),
[superpowers/specs/2026-07-26-m1-data-architecture-design.md](superpowers/specs/2026-07-26-m1-data-architecture-design.md).*

| Minor module | Path | Role |
|---|---|---|
| Identity store | `services/data/stores/user_store.py` | scrypt hashing, sessions, invite-gated signup, chat quota counters |
| Auth middleware | `services/api/auth.py` | `get_current_user`, `require_owner`, `get_current_user_or_machine` |
| Atlas relational core | `services/data/stores/atlas_store.py` | FK-linked `data/atlas.db` |
| Plane boundary | `services/data/verdict_store.py` | The user-plane read seam over ticker-keyed intelligence output |
| Universe recompute | `core/portfolio/universe.py` | Writes **aggregate counts only** back to `instruments` — user identity never crosses into the intelligence plane |
| Retention | `core/portfolio/retention.py` | Keeps user-plane stores bounded |
| ETL | `scripts/atlas_etl.py` | Freeze-cutover migration |
| DPDP delete | `DELETE /auth/account` | Single-cascade deletion |

**Two planes.** Intelligence plane = ticker-keyed and shared across users. User
plane = user-keyed and private. They join **only** through `verdict_store`.

**Escape hatches.** `AUTH_REQUIRED=false` reverts to anonymous-as-owner
instantly. `ATLAS_ENABLED` unset makes the whole Atlas layer a dormant no-op.

---

## 17. Ops, Cost & Reliability

- **Cost telemetry** — per-model rates in `config.yaml` → `llm.cost_rates`
  (AUD-105); unknown models fall back to the flat bulk rate. Rolled up nightly
  by `atlas_cost_rollup`.
- **Quota** — `services/data/stores/api_usage.py`; Serper capped at 2500/month,
  counter verified at every boot (`[api_usage] counter intact at boot …`).
- **Backup** — `services/data/backup.py`. The Railway volume is the **only**
  home of the trade ledgers, the RL prediction tree and `telemetry.db`.
- **Two-tier self-monitoring** — `ops_alerts.py` catches "job produced nothing
  or crashed"; `core/audit/thresholds.py` catches "job produced full output
  that is silently wrong". The second tier exists because the first structurally
  cannot see the news-blind class of failure.
- **Benches** — `scripts/model_bench.py`, `scripts/reasoning_bench.py`,
  `scripts/aud098_thesis_tier_bench.py`.
- **Deploy** — `Dockerfile`, `docker-compose.yml`, Railway.

---

## 18. Quality

`tests/` — ~38,000 lines across `unit/` (136 files), `integration/`, `api/`,
`contract/`, `fixtures/`. Baseline is fully green, so **any failure is a new
failure**, not known rot.

Audit program artifacts: [audit/CHARTER.md](audit/CHARTER.md),
[audit/LEDGER.md](audit/LEDGER.md) (every `AUD-###` finding — the "why is the
code like this" record), [audit/MAP.md](audit/MAP.md) (LIVE / DARK / DEAD
census).

---

## 19. Legacy & dead — know it so you skip it

| Item | Status |
|---|---|
| `services/csharp/StockAgent.Scheduler/` | **DORMANT, not deleted** — see note below |
| `new-product.py` | Old standalone script |
| `core/intelligence/rag/` | Stub, never activated |
| 19 shim files — 9 `MIGRATION SHIM` in `core/*`, 10 `FORWARD SHIM` in `src/backend/shared/*` | Half-finished restructure; see [§0](#0-orientation). **8 of the 19 have zero importers** and are deletable; the rest are load-bearing |
| `src/backend/shared/prompts/feedback_agent.py` (227) | **Old copy.** Live one is `core/config/prompts/shared/feedback_agent.py` (347) |
| Legacy LangGraph worker pool | Fallback only; engagements logged to `fallback_events.py` |
| `src/prototypes/` React app | Stub — the live UI is `src/frontend/prototypes/` |

### Note on the C# scheduler

Superseded by `services/scheduler/python/scheduler.py`, but *not* fully
unreferenced — do not assume it is safe to delete without checking these four
facts (verified 2026-08-08):

- 9 `.cs` files still present under `services/csharp/StockAgent.Scheduler/`
  (`Program.cs`, 3 controllers, `AnalyseJob.cs`, `SchedulerDbContext.cs`, 3 DTOs)
- `CSHARP_SCHEDULER_ENABLED` and `CSHARP_API_URL` still exist in
  `src/backend/shared/config/settings/base.py` (lines ~302 / ~305). The flag is
  env-gated and **defaults to `false`**
- A live contract test still covers those settings:
  `tests/contract/test_phase4_csharp.py`
- **`docker-compose.yml` has a `csharp-scheduler` service that sets
  `CSHARP_SCHEDULER_ENABLED: "true"` — with build context `csharp/StockAgent.Scheduler`,
  a pre-restructure path that no longer exists.** That compose service would
  fail to build today. It is a latent stale reference, not a working opt-in.

Production is unaffected either way: the Railway image is built from
`Dockerfile`, which never references the C# service, and no production Python
imports it.

---

## 20. Suggested study order

**Week 1 — the spine**

1. [ARCHITECTURE.md](ARCHITECTURE.md) → [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md) → [../CODEBASE.md](../CODEBASE.md)
2. Module 1 (config substrate) → Module 2 (LLM tiers)
3. Module 5 (analysis engine) — trace `POST /analyse` for a single ticker, end to end
4. `src/backend/shared/schemas/pipeline.py` — the data contract everything speaks

**Week 2 — the loop**

5. [RL_DESIGN.md](RL_DESIGN.md), then Module 7 in this order: schemas →
   `generate_forecast` → **`daily_review` steps 0–10** → `feedback_agent` →
   `weight_adapter` → `ledger_propagator`
6. Module 6 (regime) and Module 8 (dossier) — both hang off `daily_review`

**Week 3 — the product surface**

7. Module 9 (portfolio) → Module 10 (discovery) → Module 11 (delivery)
8. Module 15 (scheduler) — by now the 20 jobs read as a story, not a list

**Week 4 — the meta layers**

9. Module 12 (auditor) + Module 13 (evidence) — the two things measuring
   whether any of the rest works
10. Module 14 (API + frontend), Module 16 (identity/Atlas), Module 17 (ops)

---

## 21. Cross-cutting laws

*These repeat in every module. Learn them once and the code stops surprising
you.*

1. **The LLM never decides.** Advisor, autopilot, discovery guards, auditor and
   regime detector are all deterministic. The LLM scores dimensions, narrates,
   and proposes — code decides.
2. **Non-fatal by contract.** Every enrichment step is wrapped; a failure
   degrades the signal and never blocks the pipeline. Curator, dossier, control
   lane, offmarket, seasonal and alerts all state this explicitly.
3. **Append-only ledgers are the audit authority.** `advice_ledger.jsonl`
   append-only is *test-enforced* — which is why the auditor had to write to a
   separate file rather than annotate rows in place.
4. **Dark-signal renormalization.** A missing feed means drop the signal and
   renormalize over what remains — never impute zero.
5. **`n` travels with every number.** Metrics return `None`, not `0`, when
   there is no data. A fresh install must read `INSUFFICIENT_DATA`, never
   "0% hit rate".
6. **Config over hardcode.** Every threshold is a `cfg()` lookup.
7. **Two planes.** Intelligence (ticker-keyed, shared) vs user (user-keyed,
   private), joined only through `verdict_store`.
8. **A kill-switch per feature.** `ATLAS_ENABLED`, `AUTH_REQUIRED`,
   `DISCOVERY_ENABLED`, `DELIVERY_ENABLED`, `brief_html_enabled`,
   `audit.enabled`, `rl.hard_bind_verdict_enabled`,
   `rl.macro_fallback_context_enabled`.
9. **Idempotency where a job repeats.** Nightly grading, alert dedupe and
   backfill are all keyed so a re-run is a no-op.
10. **Isolation for anything that must not teach the system.** The paper lane
    runs real forecasts under an isolated store root with every learning write
    removed.
