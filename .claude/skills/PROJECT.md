# PROJECT.md

Living state file. All skills reference this. Update it whenever a decision is made.
The meta skill edits this file automatically when decision-language is detected in conversation.

Last updated: 2026-05-05

---

## Product

- **Tool name:** StockAgent
- **One-line description:** AI-powered Indian stock market analyzer using parallel specialist LLM agents to produce scored investment research across multiple sectors
- **Output mode:** research — non-personalized sector and stock analysis; research/educational framing only (no "buy X shares" language)
- **Target user:** semi-pro retail investor (personal project; single user currently)
- **Stage:** prototype — automobile sector fully wired end-to-end; BFSI/IT/Renewable agents written and restructured into individual files but not yet connected to CLI or API (Phase 2b pending)

## Market scope

- **Geography:** India only
- **Exchanges:** NSE (primary), BSE
- **Asset classes covered:** equities `[active]`, F&O `[planned]`, commodities `[planned]`, currency `[planned]`, ETFs `[planned]`, mutual funds `[planned]`, debt `[planned]`
- **Segments active now:** Large-cap Indian equities across 4 sectors — Automobile (10 tickers live), BFSI (agents written, not wired), IT (agents written, not wired), Renewable Energy (agents written, not wired)
- **Time horizon supported:** positional / long-term (sector-level analysis; not intraday)

## Compliance posture

- **SEBI registration status:** none — output must stay research/educational; no personalized recommendations
- **Disclaimer text location:** not yet implemented — needed before any public-facing release
- **PII handling policy:** none collected; single-user personal tool
- **Data licensing constraints:** yfinance (delayed/non-commercial), Serper (Google Search API terms), Tavily (API terms), NewsAPI (free tier)

## Tech stack

- **Languages:** Python (core logic), TypeScript/Bun (gateway + cron), React 19 + TSX (frontend), C++ via pybind11 (technical indicators)
- **Backend framework:** FastAPI on port 8001 (internal, Python) + Hono on port 3000 (public gateway, TypeScript/Bun)
- **Frontend:** React 19 + Vite on port 5173 (dev mode) — components in `frontend/prototypes/beginner/` and `frontend/ui_kits/stockagent/`; pages: home, agents-page, data, portfolio, learn, auth; key components: AgentCard, AgentRadar, ConvictionPanel, HistoryLine, ScoreGauge, ScoreTable
- **Primary database:** SQLite (`data/scores.db`) — score history, 90-day rolling retention
- **Time-series store:** none — yfinance used for on-demand OHLCV (up to 10 years historical)
- **Cache:** in-memory Python dict (`data/cache.py`) — sector macro news, 4-hour TTL, refreshed by background micro-search loop
- **Queue / event bus:** none
- **Vector DB:** ChromaDB — optional RAG feature, disabled by default (`RAG_ENABLED=false`)
- **LLM provider(s) / model(s):** OpenRouter — default model `qwen/qwen3-235b-a22b`; alternatives: `qwen/qwen3.5-flash-02-23`, `mistralai/mistral-small-2603`, `qwen/qwen-2.5-72b-instruct`
- **Cloud:** Railway (deployment target)
- **IaC tool:** none
- **CI/CD:** none set up
- **Observability:** file-based structured logging (`logs/automobile_agent.log`), JSONL run logs (`logs/agent_calls.jsonl`), per-run API usage tracking

## Data sources

- **Market data (real-time):** none — yfinance is ~15 min delayed; no live feed
- **Market data (historical):** yfinance (OHLCV up to 10 years, `.NS` suffix for NSE)
- **Corporate actions:** yfinance
- **Fundamentals / filings:** yfinance (quarterly P&L, balance sheet, margins)
- **News / sentiment:** Serper (Google Search API, 2 keys — key 1 for automobile/RE, key 2 for BFSI/IT); NewsAPI as fallback
- **FII/DII flows:** Serper search results (no direct API)
- **Options chain / OI:** not implemented
- **MF holdings:** not implemented
- **Macro / RBI policy:** yfinance (INR/USD `INR=X`, crude `CL=F`, steel `SLX`, etc.) + Serper + Tavily (full-page policy document extraction)

## Directory layout (post Phase 2a restructure)

```
sectors/
  automobile/agents/   ← 9 individual agent files (moved from core/sectors/automobile/)
  automobile/registry.py, graph.py
  bfsi/agents/         ← 6 individual agent files (split from core/sectors/banking/agents.py)
  bfsi/registry.py
  it/agents/           ← 8 individual agent files (split from core/sectors/it/agents.py)
  it/registry.py
  renewable/agents/    ← 6 individual agent files (split from core/sectors/renewable/agents.py)
  renewable/registry.py

pipeline/              ← base_agent.py, orchestrator.py, signal_aggregator.py (moved from core/pipeline/)
data/                  ← news.py, fundamentals.py, macro.py, cache.py (moved from services/data/fetchers/ + cache/)

core/                  ← graphs/, schemas/, config/, intelligence/ — unchanged
services/              ← api/, clients/, data/context/, data/stores/, gateway/ — unchanged
docs/                  ← all design docs, HTML files, siva/ notes (consolidated here)
```

## Architecture

- **Service layout:** modular monolith (Python) + TypeScript gateway + React frontend; all JSON over HTTP/WebSocket, no shared memory across languages
- **Agent architecture:** swarm — 9 specialist agents (automobile) run in parallel via LangGraph Send fan-out; each agent sees only its relevant data slice; results merged by state reducers
- **Signal aggregation pattern:** weighted sum across agent scores → LLM conflict resolution if any two agents diverge by ≥0.30 → verdict mapping (STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL)
- **Current scale:** 1 user, ~1–5 analyses/day, ~$0.006–0.017 USD per run
- **12-month target scale:** unknown — depends on whether tool stays personal or goes multi-user

## Sector agent registry

| Sector | Agents | Weights defined | Fully wired (CLI + API) |
|---|---|---|---|
| Automobile | 9 agents | yes | yes |
| BFSI | 6 agents | yes | no — blocked on Phase 2b |
| IT | 8 agents | yes | no — blocked on Phase 2b |
| Renewable Energy | 6 agents | yes (risk agent weight=0, monitoring only) | no — blocked on Phase 2b |

## Agent weights (automobile — active)

Two sources exist — **registry.py is authoritative** (used by LangGraph graph). Settings weights are fallback only in SignalAggregator.

| Agent | registry.py (live) | settings/base.py (fallback) |
|---|---|---|
| fundamentals | 0.18 | 0.18 |
| sales_demand | 0.16 | 0.15 |
| risk_macro | 0.13 | 0.13 |
| pattern_analysis | 0.12 | 0.11 |
| valuation_catalyst | 0.10 | 0.12 |
| raw_materials | 0.09 | 0.09 |
| policy_regulatory | 0.09 | 0.09 |
| competitive_intel | 0.09 | 0.09 |
| sentiment | 0.04 | 0.04 |

**Open item:** reconcile these two sources — they should be one source of truth.

## Key decisions log

Append-only. Most recent first. Format: `YYYY-MM-DD — decision — short rationale`

- 2026-05-05 — Phase 2a restructure completed — "one folder per sector, one shared pipeline" layout implemented; sectors/ + pipeline/ + data/ top-level packages created; all imports updated; no shims; docs/ consolidated
- 2026-04-29 — Phase 2 restructure proposal created (RESTRUCTURE_PROPOSAL.md) — current structure hard to explain; proposed "one folder per sector, one shared pipeline" layout
- 2026-04-29 — Output mode = research/educational only — no SEBI registration; avoid personalized recommendation language
- 2026 — Two Serper API keys (auto/RE on key 1, BFSI/IT on key 2) — stay within 2,500 calls/month free tier per key
- 2026 — Macro cache pre-fetch loop every 4 hours — saves ~990 Serper calls/month across 3 sectors
- 2026 — SQLite for score persistence — no infrastructure overhead for personal project
- 2026 — ChromaDB for RAG, disabled by default — optional enhancement; not required for core function
- 2026 — C++ via pybind11 for RSI/MACD/Bollinger Bands — performance; pure-Python fallback available for CI
- 2026 — TypeScript/Bun gateway (port 3000) in front of Python FastAPI (port 8001) — separates scheduling/cron (TS) from analysis logic (Python); no shared memory, JSON over HTTP
- 2026 — LangGraph for multi-agent orchestration — native Send fan-out, RetryPolicy, state reducers; avoids manual asyncio.gather wiring
- 2026 — OpenRouter as LLM provider — cost efficiency, model switching without code changes
- 2026 — Default model: qwen/qwen3-235b-a22b — accuracy-first for investment analysis; ~$0.017/run
- 2026 — Railway for deployment — simple container deployment, PORT env var respected

## Open questions

Things on the table but not yet decided. Move to "Key decisions log" when resolved.

- BFSI/IT/Renewable wiring — Phase 2a done; Phase 2b connects all sectors to CLI (`--sector` flag) + API (`sector` param)
- Sync → async in LangGraph nodes — `run_agent` nodes call `agent.run()` synchronously; should be `run_async()`; known tech debt, no timeline
- RAG hardcoding — `_rag_retrieve()` in base_agent.py hardcoded for automobile agent names; breaks for BFSI/IT/RE if RAG enabled
- Agent name collision — `fundamentals` and `pattern_analysis` exist in all 4 sector registries under same key; fine per-graph but ambiguous cross-sector
- SEBI registration path — if tool goes multi-user or public, RA registration needed; changes output framing significantly
- Asset scope v2 — F&O, options chain (OI, PCR, IV), commodities — no timeline
- Scale targets — stays personal or goes multi-user; drives infra decisions
- Real-time market data — yfinance is delayed; live feed (e.g. Zerodha Kite, Upstox) needed for intraday use cases
- Output mode expansion — move from research to hybrid (research + execution signal) — requires SEBI RA or broker-partner arrangement
- TypeScript cron scope — currently only schedules automobile tickers; needs sector param when other sectors are wired
