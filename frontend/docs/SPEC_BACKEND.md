# Backend Context & API Specification

## What the App Does

StockAgent analyzes 10 Indian automobile OEM stocks using 8 specialized LLM agents that run
in parallel. Each agent scores the stock 0.0–1.0 across a domain. A Signal Aggregator fuses
the scores (weighted), detects conflicts, and produces a final verdict.

## Supported Tickers
```
MARUTI, TATAMOTORS, M&M, HEROMOTOCO, BAJAJ-AUTO,
EICHERMOT, TVSMOTORS, ASHOKLEY, ESCORTS, FORCEMOT
```

## The 8 Agents + Weights
| # | Agent | Weight | Domain |
|---|-------|--------|--------|
| 1 | sales_demand | 18% | FADA dispatches, EV Vahan data, dealer inventory |
| 2 | fundamentals | 20% | Revenue/EBITDA, margins vs peers, FII/DII flow |
| 3 | pattern_analysis | 13% | RSI/MACD/Bollinger, support/resistance, 10yr cycles |
| 4 | raw_materials | 10% | Steel/aluminium, crude, polymers, commodities |
| 5 | sentiment | 4% | News NLP, earnings call tone, social media |
| 6 | policy_regulatory | 10% | FAME EV subsidy, emission norms, PLI scheme |
| 7 | competitive_intel | 10% | EV market share, new model pipeline, ADAS ratings |
| 8 | risk_macro | 15% | INR/USD exposure, RBI rate, China supply risk |

## Verdict Thresholds
| Score | Verdict | Color |
|-------|---------|-------|
| 0.75–1.00 | STRONG BUY | Glowing green (#22c55e) |
| 0.60–0.74 | BUY | Green (#4ade80) |
| 0.45–0.59 | NEUTRAL | Amber (#f59e0b) |
| 0.30–0.44 | SELL | Orange-red (#f97316) |
| 0.00–0.29 | STRONG SELL | Red (#ef4444) |

## API Endpoints

### Python FastAPI — http://localhost:8000

```
POST /analyse
  Body:    { "ticker": "MARUTI" }
  Returns: FinalReport JSON

GET /history/{ticker}
  Returns: Array<ScoreRecord> (up to 30, newest first)

GET /history/{ticker}/latest
  Returns: Single most-recent ScoreRecord

WS ws://localhost:8000/ws/stream?ticker=MARUTI
  Emits stream of JSON events:
    { "event": "agent_progress", "agent": "fundamentals", "score": 0.68 }
    { "event": "complete", "report": <FinalReport> }
    { "event": "error", "detail": "..." }
  One event fires as each agent completes (~8–10 events total)

GET /health
  Returns: { "status": "ok" }
```

### TypeScript Express — http://localhost:3000
```
POST /api/analyse        → proxies to :8000/analyse
GET  /api/history/:ticker → proxies to :8000/history/:ticker
```

### C# Scheduler — http://localhost:5000
```
GET /api/scheduler/status
  Returns: { "is_running": bool, "next_fire_time": "ISO datetime", "ticker_count": int }

GET /api/scores/latest
  Returns: Array<ScoreRecord> (latest per configured ticker)
```

## TypeScript Interfaces

```typescript
interface AgentScoreDetail {
  raw: number        // 0.0–1.0 agent score before weighting
  weight: number     // e.g. 0.18 for sales_demand
  weighted: number   // raw × weight
}

interface FinalReport {
  ticker: string
  company_name: string
  final_score: number
  verdict: "STRONG BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG SELL"
  weighted_agent_scores: { [agent: string]: AgentScoreDetail }
  conviction_drivers: string[]        // 3–6 bullets
  top_risks: string[]                 // 3–6 bullets
  conflicts_resolved?: string[]
  investment_thesis: string           // 2–3 paragraph narrative
  report_date: string                 // ISO date string
}

interface ScoreRecord {
  id: number
  ticker: string
  company_name: string
  final_score: number
  verdict: string
  report_date: string
}

interface StreamEvent {
  event: "agent_progress" | "complete" | "error"
  agent?: string
  score?: number
  report?: FinalReport
  detail?: string
}

interface SchedulerStatus {
  is_running: boolean
  next_fire_time: string
  ticker_count: number
}
```
