# docs/ — Documentation Index

**Current KT (2026-09-15):** [Technical Design](TECHNICAL_DESIGN.md) and its [PDF](StockAgent-Three-Loops.pdf) explain inspected code and every planned PI change. **Separate deliverable:** [Team Human Testing Guide](TEAM_TESTING_GUIDE.md), with 12 assignable functional duties; all cases start NOT RUN.

**Detailed production evidence (2026-09-10):** [repository and production audit](audit/2026-09-10-repository-production-review.md). For implementation work, use the [current PI and sprint stories](planning/PI-2026-09/README.md) and [next-task handoff](planning/PI-2026-09/HANDOFF.md). The audit distinguishes deployed behavior from older design claims; the PI state records what remains unimplemented. September 15 checked deployment revision/status only.

Two kinds of documents live here. Know which kind you're reading.

## Living documents (kept current — update these when the system changes)

| Document | What it covers | Audience |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | **Start here.** Current-state system map: the three loops, runtime topology, the scheduled jobs, data volume layout, LLM tiers, security posture | Everyone |
| [PRODUCT_MAP.md](PRODUCT_MAP.md) | Detailed August module inventory; consult its status banner and current KT for subsequent changes | Developers needing the older detailed map |
| [../README.md](../README.md) | Product-level tour: what it does, sectors, verdicts, portfolio features, FAQ | Users / evaluators |
| [../CODEBASE.md](../CODEBASE.md) | Module map, API endpoint census, sector registry, configuration reference | Developers |
| [RL_DESIGN.md](RL_DESIGN.md) | The self-learning loop in full: memory files, daily review steps 0–9, formulas, LLM contracts, Knowledge Layer, Living Envelope | RL developers |
| [AUTOPILOT_GUIDE.md](AUTOPILOT_GUIDE.md) | Compass money path: advisor rule cascade, executor invariants, ledgers | Portfolio developers |
| [CHAT_ARCHITECTURE.md](CHAT_ARCHITECTURE.md) | Agentic streaming tool-loop behind `/ui/chat/stream` | Chat developers |
| [AGENTIC_DESIGN.md](AGENTIC_DESIGN.md) | Agent taxonomy, per-dimension metrics and data sources, static-vs-LLM boundaries | Prompt/agent developers |
| [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md) | **Start here for KT.** Current workflows, examples, storage, jobs, IPO, P/L, report contracts and all PI targets | Everyone learning the system |
| [StockAgent-Three-Loops.pdf](StockAgent-Three-Loops.pdf) | Generated PDF edition of the technical KT; [original PDF archive](archive/README.md) retained | KT sessions and sharing |
| [TEAM_TESTING_GUIDE.md](TEAM_TESTING_GUIDE.md) | Separate non-code-intensive duties, scenarios, expected results and evidence template | Human functional testers |

Update affected living documentation with every implementation story and regenerate the PDF when its Markdown source changes. SA-031 is a final consistency check, not deferred documentation work. Each living deep-dive carries a **Status** banner under its title stating when
it was last verified and which sections have drifted; trust the banner over the
body text where they disagree.

## StockAgent — Complete Module Map (at a glance)

The 19 major modules of the product. **Minor modules, file paths, the 4-week
study order and the cross-cutting laws live in
[PRODUCT_MAP.md](PRODUCT_MAP.md)** — each row below links straight to its
section there. This is the August inventory, not a current source census;
the September KT supersedes stale counts, runtime statements and learning claims.

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
| 15 | [Time Orchestration](PRODUCT_MAP.md#15-time-orchestration) | APScheduler; current builder has 23 possible IDs, with registration controlled by gates (KT section 9) |
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
