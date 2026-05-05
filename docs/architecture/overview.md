# Architecture Overview

> System as it exists on 2026-05-05.
> Update this diagram whenever a component graduates from planned → in-progress → built,
> or whenever a new component is added.

---

## Component status legend

| Color | Meaning |
|-------|---------|
| Green | Built and wired end-to-end |
| Gold | Written but not yet wired (in-progress / blocked) |
| Grey | Planned — not started |

---

## System diagram

```mermaid
flowchart TD
    %% ── Entry points ──────────────────────────────────────────────────────────
    CLI["CLI\npython main.py TICKER"]:::built
    FE["React Frontend\nport 5173"]:::built
    CRON["TypeScript Cron\n(automobile only today)"]:::built
    CS["C# Quartz.NET Scheduler\nport 5000 · 8:30am IST weekdays"]:::built

    %% ── Gateway ───────────────────────────────────────────────────────────────
    GW["TypeScript/Bun Gateway\nport 3000 · Hono"]:::built

    %% ── Python FastAPI ────────────────────────────────────────────────────────
    API["Python FastAPI\nport 8001\nPOST /analyse  GET /history  WS /ws/stream"]:::built

    %% ── LangGraph sector graphs ───────────────────────────────────────────────
    AUTO["LangGraph: Automobile\n9 agents · fully wired"]:::built
    BFSI["LangGraph: Banking/BFSI\n6 agents · written, not wired"]:::inProgress
    IT["LangGraph: IT Sector\n8 agents · written, not wired"]:::inProgress
    RE["LangGraph: Renewable Energy\n6 agents · written, not wired"]:::inProgress

    %% ── Core agent pipeline ───────────────────────────────────────────────────
    RESOLVE["Ticker Resolver\nLLM call · temp=0"]:::built
    RAIL_IN["Input Rail\nNeMo guard · yfinance existence check"]:::built
    AGENTS["8 Specialist Agents\nfan-out via LangGraph Send"]:::built
    AGG["Signal Aggregator\nweighted sum → conflict detect → LLM resolve"]:::built
    REPORT["FinalReport\nverdict + score + thesis"]:::built

    %% ── Intelligence layer ────────────────────────────────────────────────────
    RL["RL Weight Adapter\nfeedback-driven agent weight updates"]:::built
    REGIME["Regime Detector\nmarket regime classification"]:::built
    SEASONAL["Seasonal Calendar\naccuracy threshold shifts per agent"]:::built
    RAG["RAG Pipeline\nChromaDB · disabled by default"]:::inProgress
    ENHANCER["Prompt Enhancer\nlearned weight injection"]:::built

    %% ── Data layer ────────────────────────────────────────────────────────────
    CB["ContextBuilder\nper-agent data routing"]:::built
    YF["yfinance\nOHLCV · fundamentals · macro"]:::built
    CPP["C++ Indicators\nRSI · MACD · Bollinger Bands\nvia pybind11"]:::built
    SERPER["Serper / NewsAPI\nnews · sentiment · FII flows"]:::built
    TAVILY["Tavily\nfull-page policy articles"]:::built
    MACRO["Macro Cache\n4-hr TTL · in-memory"]:::built

    %% ── Persistence ───────────────────────────────────────────────────────────
    SQLITE["SQLite\ndata/scores.db · 90-day retention"]:::built
    PRED["Prediction Store\nRL ledger · JSONL"]:::built
    ALERTS["AlertManager\nscore delta / verdict change\nconsole · file · webhook"]:::built

    %% ── Planned ───────────────────────────────────────────────────────────────
    CICD["CI/CD + Railway Deploy"]:::planned
    RT["Real-time Market Feed\nZerodha / Upstox"]:::planned
    FO["F&O / Options Chain"]:::planned

    %% ── Edges: entry → gateway ────────────────────────────────────────────────
    CLI --> API
    FE --> GW
    CRON --> GW
    CS --> API
    GW --> API

    %% ── Edges: API → LangGraph ────────────────────────────────────────────────
    API --> AUTO
    API -.->|blocked| BFSI
    API -.->|blocked| IT
    API -.->|blocked| RE

    %% ── Edges: automobile graph internal ──────────────────────────────────────
    AUTO --> RESOLVE
    RESOLVE --> RAIL_IN
    RAIL_IN --> AGENTS
    AGENTS --> AGG
    AGG --> REPORT

    %% ── Edges: intelligence ───────────────────────────────────────────────────
    RL --> ENHANCER
    REGIME --> AGENTS
    SEASONAL --> RL
    ENHANCER --> AGENTS
    RAG -.->|disabled| AGENTS

    %% ── Edges: data ───────────────────────────────────────────────────────────
    CB --> AGENTS
    YF --> CB
    CPP --> YF
    SERPER --> CB
    TAVILY --> CB
    MACRO --> CB

    %% ── Edges: persistence ────────────────────────────────────────────────────
    REPORT --> SQLITE
    REPORT --> PRED
    REPORT --> ALERTS
    PRED --> RL

    %% ── Class definitions ─────────────────────────────────────────────────────
    classDef built fill:#90EE90,stroke:#333,color:#000
    classDef inProgress fill:#FFD700,stroke:#333,color:#000
    classDef planned fill:#D3D3D3,stroke:#333,color:#000
```

---

## Port map

| Service | Port | Status |
|---------|------|--------|
| Python FastAPI | 8001 | Built |
| TypeScript/Bun Gateway | 3000 | Built |
| React Frontend (dev) | 5173 | Built |
| C# Quartz.NET Scheduler | 5000 | Built |
| LangGraph Studio (dev) | varies | Built |

---

## Cross-language contract

All language boundaries use **JSON over HTTP**. No shared memory across process boundaries.
C++ is the sole exception: it runs in-process via pybind11 and is loaded by the Python process directly.

```
React (5173) → Bun Gateway (3000) → FastAPI (8001) → LangGraph/Python agents
                                  ↗
C# Scheduler (5000) ────────────
```
