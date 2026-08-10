# docs/ — Documentation Index

Two kinds of documents live here. Know which kind you're reading.

## Living documents (kept current — update these when the system changes)

| Document | What it covers | Audience |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | **Start here.** Current-state system map: the three loops, runtime topology, the scheduled jobs, data volume layout, LLM tiers, security posture | Everyone |
| [PRODUCT_MAP.md](PRODUCT_MAP.md) | **Start here to *learn* the product.** Every major module and its minor modules, enumerated from the source tree, plus a 4-week study order and the cross-cutting laws | New developers / anyone onboarding |
| [../README.md](../README.md) | Product-level tour: what it does, sectors, verdicts, portfolio features, FAQ | Users / evaluators |
| [../CODEBASE.md](../CODEBASE.md) | Module map, API endpoint census, sector registry, configuration reference | Developers |
| [RL_DESIGN.md](RL_DESIGN.md) | The self-learning loop in full: memory files, daily review steps 0–9, formulas, LLM contracts, Knowledge Layer, Living Envelope | RL developers |
| [AUTOPILOT_GUIDE.md](AUTOPILOT_GUIDE.md) | Compass money path: advisor rule cascade, executor invariants, ledgers | Portfolio developers |
| [CHAT_ARCHITECTURE.md](CHAT_ARCHITECTURE.md) | Agentic streaming tool-loop behind `/ui/chat/stream` | Chat developers |
| [AGENTIC_DESIGN.md](AGENTIC_DESIGN.md) | Agent taxonomy, per-dimension metrics and data sources, static-vs-LLM boundaries | Prompt/agent developers |
| [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md) | Deep implementation reference: fetchers, context builders, settings, sector engines | Developers (encyclopedic) |

Each living deep-dive carries a **Status** banner under its title stating when
it was last verified and which sections have drifted; trust the banner over the
body text where they disagree.

## StockAgent — Complete Module Map (at a glance)

The 19 major modules of the product. **Minor modules, file paths, the 4-week
study order and the cross-cutting laws live in
[PRODUCT_MAP.md](PRODUCT_MAP.md)** — each row below links straight to its
section there. This table is a directory, not a summary; when it and
PRODUCT_MAP.md disagree, PRODUCT_MAP.md is the one that gets updated.

| # | Major module | What it owns |
|---|---|---|
| 1 | [Platform & Configuration Substrate](PRODUCT_MAP.md#1-platform--configuration-substrate) | `cfg()`, `config.yaml` (22 sections), settings precedence, atomic writes |
| 2 | [LLM & External Service Clients](PRODUCT_MAP.md#2-llm--external-service-clients) | 3 model tiers, OpenRouter wrapper, Tavily, API quota counter |
| 3 | [Data Acquisition Layer](PRODUCT_MAP.md#3-data-acquisition-layer) | 15 fetchers (NSE, bhavcopy, news, macro, IPO…) + context builders |
| 4 | [Persistence Layer](PRODUCT_MAP.md#4-persistence-layer) | SQLite / JSON / append-only JSONL / parquet; the RL file tree |
| 5 | [Analysis Engine](PRODUCT_MAP.md#5-analysis-engine--the-verdict-producer) | Sector routing, unified analyst vs legacy pool, aggregator, C++ indicators |
| 6 | [Regime & Market-State Intelligence](PRODUCT_MAP.md#6-regime--market-state-intelligence) | 6 regime labels, hysteresis, seasonal calendar, conviction streaks |
| 7 | [Adaptive Learning Loop (RL)](PRODUCT_MAP.md#7-the-adaptive-learning-loop-rl--the-heart) | **The heart.** Forecast envelope + the 11-step daily review + lesson machinery |
| 8 | [Knowledge Layer (Ticker Dossier)](PRODUCT_MAP.md#8-knowledge-layer-ticker-dossier) | Permanent per-ticker knowledge: curator, event ingestor, research loop |
| 9 | [Portfolio & Advisory](PRODUCT_MAP.md#9-portfolio--advisory-compass) | Virtual book, advisor cascade, autopilot, narrator, corp actions |
| 10 | [Discovery Engine](PRODUCT_MAP.md#10-discovery-engine-compass-phase-b) | Weekly funnel: universe → signals → screen → guards → deep dive → shelf |
| 11 | [Delivery Layer](PRODUCT_MAP.md#11-delivery-layer-compass-phase-c) | Morning brief, weekly review, alerts, web-push/email, durable outbox |
| 12 | [Verification Layer ("the auditor")](PRODUCT_MAP.md#12-verification-layer-the-auditor) | Deterministic grading of issued advice vs `^NSEI`; breach thresholds |
| 13 | [Measurement & Scientific Evidence](PRODUCT_MAP.md#13-measurement--scientific-evidence) | Eval harness, baseline duel, monthly scorecard, self-ablation report |
| 14 | [Service & Interface Layer](PRODUCT_MAP.md#14-service--interface-layer) | 13 routers, 88 endpoints + 1 WebSocket, the chat tool-loop, the PWA |
| 15 | [Time Orchestration](PRODUCT_MAP.md#15-time-orchestration) | APScheduler thread; 20 registered jobs — the product's clock |
| 16 | [Identity, Multi-Tenancy & Data Governance](PRODUCT_MAP.md#16-identity-multi-tenancy--data-governance) | Auth/sessions/invites, Atlas `atlas.db`, the two-plane boundary, DPDP delete |
| 17 | [Ops, Cost & Reliability](PRODUCT_MAP.md#17-ops-cost--reliability) | Cost telemetry, quota, backup, two-tier self-monitoring |
| 18 | [Quality](PRODUCT_MAP.md#18-quality) | ~38k lines of tests across 5 suites; the audit ledger |
| 19 | [Legacy & dead](PRODUCT_MAP.md#19-legacy--dead--know-it-so-you-skip-it) | Migration shims, the dormant C# scheduler, the RAG stub — what to skip |

Also in PRODUCT_MAP.md: [§0 Orientation](PRODUCT_MAP.md#0-orientation) (scale,
and the migration-shim trap), [§20 Suggested study
order](PRODUCT_MAP.md#20-suggested-study-order) (4 weeks), and [§21
Cross-cutting laws](PRODUCT_MAP.md#21-cross-cutting-laws) — the 10 invariants
that repeat in every module.

## Audit program (append-only working artifacts)

| Document | What it is |
|---|---|
| [audit/CHARTER.md](audit/CHARTER.md) | The audit program's scope, protocol, and hotspot ranking |
| [audit/LEDGER.md](audit/LEDGER.md) | Every finding (`AUD-###`) with evidence, severity, and fix status — the "why is the code like this" record |
| [audit/MAP.md](audit/MAP.md) | System reality map: LIVE / DARK / DEAD census of every module at audit time |
| [audit/ADAPTIVE_LEARNING_REVIEW.md](audit/ADAPTIVE_LEARNING_REVIEW.md) | Scientific review of the adaptive layer (gaps G1–G10) + how to read the monthly Learning Evidence Report (AUD-116) |

## Frozen history (do **not** update)

- `superpowers/plans/` — implementation plans as approved, one per feature/wave.
- `superpowers/specs/` — design specs as approved.

These are provenance: they record what was *intended* at the time, and the
audit ledger records what was later found and changed. Editing them
retroactively would destroy that trail. When a plan and reality disagree, the
plan is the historical artifact — [ARCHITECTURE.md](ARCHITECTURE.md) and the
code are the truth.
