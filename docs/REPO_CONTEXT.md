# Repo Context — What Is Built vs What We Need

> Quick reference for team onboarding. Read this alongside TRAINING_PLAN.md.

---

## What The Repo Is

**StockAgent** is a multi-sector, multi-agent AI stock analysis system for Indian markets (NSE/BSE).

It is a **multi-language system**:
- Python — agents, orchestrator, RAG, RL, FastAPI
- TypeScript (Bun + Hono) — API gateway, frontend, cron scheduler
- C# (Quartz.NET + EF Core) — backup scheduler + SQL Server persistence
- C++ (pybind11) — RSI, MACD, Bollinger Bands indicators

---

## What Is Fully Built (Automobile Sector)

The Automobile sector is the reference implementation. Study this before building anything.

### Entry points
- CLI: `python main.py MARUTI`
- API: `POST http://localhost:8001/analyse` via FastAPI
- Scheduled: TypeScript gateway cron at 8:30am IST daily

### 9 agents (all in `core/sectors/automobile/`)
| Agent | Weight | What it analyses |
|---|---|---|
| Sales & Demand | 18% | FADA/SIAM dispatch, EV data, dealer inventory, exports |
| Raw Materials | 10% | Steel, aluminium, crude, polymers, power tariff |
| Fundamentals | 20% | Revenue/EBITDA, margins vs peers, FII/DII flow |
| Pattern Analysis | 13% | Price cycle, RSI/MACD/BB, support/resistance |
| Sentiment | 4% | News NLP, earnings call tone, social media |
| Policy & Regulatory | 10% | FAME EV subsidy, emission norms, PLI scheme |
| Competitive Intel | 10% | EV market share, new model pipeline, JVs |
| Risk & Macro | 15% | INR/USD/crude exposure, RBI rate, emission risk |
| Valuation & Catalyst | — | P/E, EV/EBITDA, upcoming catalysts |

### Infrastructure that is fully reusable
| Module | Location | Purpose |
|---|---|---|
| BaseAgent | `core/pipeline/base_agent.py` | Template for all agents — retry, RAG, LLM calls |
| Orchestrator | `core/pipeline/orchestrator.py` | Parallel dispatch + progress callbacks |
| SignalAggregator | `core/pipeline/signal_aggregator.py` | Weighted fusion + LLM conflict resolution |
| RAG pipeline | `intelligence/rag/` | ChromaDB + sentence-transformers + retriever |
| RL workflows | `intelligence/rl/` | Daily review, forecast generation, outcome tracking |
| Data fetchers | `services/data/fetchers/` | fundamentals, macro, news |
| Context builder | `services/data/context/builder.py` | Routes each agent to correct fetchers |
| Score store | `services/data/stores/score_store.py` | SQLite persistence (or C# via feature flag) |
| LLM client | `services/clients/llm_client.py` | OpenRouter wrapper (sync + async) |
| FastAPI server | `services/api/server.py` | /analyse, /history, /ws/stream |
| TypeScript gateway | `services/gateway/src/index.ts` | REST proxy + WebSocket + cron |
| Frontend | `frontend/src/` | React + Vite dashboard |
| Pydantic schemas | `core/schemas/pipeline.py` | StockQuery, AgentOutput, FinalReport |

---

## What Has Stubs (Not Yet Built)

### Banking / BFSI
| File | Status |
|---|---|
| `core/sectors/banking/agents.py` | Imports from banking agents that don't exist yet |
| `core/sectors/banking/graph.py` | Stub |
| `graphs/banking_bfsi/agents.py` | Imports core.sectors.banking.agents |

### IT Sector
| File | Status |
|---|---|
| `core/sectors/it/agents.py` | Stub |
| `core/sectors/it/graph.py` | Stub |
| `graphs/it_sector/agents.py` | Stub |

### Renewable Energy
| File | Status |
|---|---|
| `core/sectors/renewable/agents.py` | Stub |
| `core/sectors/renewable/graph.py` | Stub |
| `graphs/renewable_energy/agents.py` | Stub |

---

## Port Map

| Service | Port | Protocol | File |
|---|---|---|---|
| Python FastAPI (internal) | 8001 | HTTP + WebSocket | `services/api/server.py` |
| TypeScript gateway (public) | 3000 | HTTP + WebSocket | `services/gateway/src/index.ts` |
| C# scheduler | 5000 | HTTP | `services/csharp/StockAgent.Scheduler/Program.cs` |
| React frontend | 5173 | HTTP | `frontend/` |

---

## Config / Feature Flags

All in `config/settings/base.py`:

| Flag | Default | Purpose |
|---|---|---|
| `LLM_MODEL` | `qwen/qwen3-235b-a22b` | Swap to `claude-sonnet-4-6` for production |
| `RAG_ENABLED` | `false` | Set to `true` to use ChromaDB context |
| `CSHARP_SCHEDULER_ENABLED` | `false` | Routes persistence to C# when true |
| `SCHEDULER_ENABLED` | `false` | Python APScheduler (RL reviews only) |

---

## Key Files to Read First (Team Onboarding Order)

1. `README.md` — full project overview, quick start, port map
2. `docs/CODEBASE.md` — authoritative module map
3. `core/schemas/pipeline.py` — all data shapes (StockQuery, AgentOutput, FinalReport)
4. `core/pipeline/base_agent.py` — the template every agent extends
5. `core/sectors/automobile/sales_demand.py` — a complete agent example
6. `core/pipeline/signal_aggregator.py` — how signals are fused
7. `intelligence/rag/` — RAG pipeline (embedder, vector store, retriever)
8. `intelligence/rl/` — RL feedback loop

---

## How to Add a New Sector (e.g. Banking)

1. Create agents in `core/sectors/banking/<agent_name>.py` — extend `BaseAgent`
2. Register all agents + weights in `core/sectors/banking/agents.py`
3. Wire LangGraph in `core/sectors/banking/graph.py` (copy from automobile/graph.py)
4. Create a `BFSIAgentOrchestrator` in `core/pipeline/bfsi_orchestrator.py` (copy automobile orchestrator, swap agents)
5. Add prompts in `prompts/banking/<agent_name>.py` (include `CONTEXT_SEARCH_QUERIES` for RAG)
6. Add a new FastAPI route in `services/api/routes/` for the BFSI endpoint
7. Add BFSI tickers to the TypeScript gateway cron
