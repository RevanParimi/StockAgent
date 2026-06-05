# Chat Pipeline Redesign — 3-Node Open Dispatch Architecture

**Date:** 2026-05-15
**Status:** Approved
**Replaces:** `docs/CHAT_ARCHITECTURE.md` (5-node LangGraph pipeline)

---

## Problem Statement

The current 5-node pipeline has three structural failures:

1. **Fixed intent types** — 9 hardcoded categories (`STOCK_COMPARE`, `NEWS_QUERY`, etc.) cannot cover cross-market, cross-sector, or temporal queries. "Compare last 3 days Sensex + predict today" was misclassified as `STOCK_COMPARE`, routing to wrong tools.
2. **Gated news** — `search_market_news` only runs when `needs_external=True`, decided by the planner. Trending news that explains cross-sector moves was missed entirely.
3. **Rigid response format** — a 120-word prompt-enforced template produced robotic, one-size-fits-all answers regardless of who was asking or what was found.

Additionally: the classify → planner telephone game compounded errors (classification mistake → wrong plan), the reviewer-synthesize loop added 1–3s without catching stale tool results, and the RL system's rich prediction data was only surfaced on explicit `RL_QUERY` intent.

---

## Design Goals

- Any query type handled without buckets — the LLM reasons about what to fetch
- Trending/relevant news always fetched on non-trivial queries
- User sophistication detected and response depth adapted accordingly (Casual / Active / Expert)
- RL prediction envelopes surfaced naturally whenever a ticker or sector is involved
- Parallel tool execution — price, history, RL, news all fetched concurrently
- Response format emerges from content and user tier — not a rigid template
- Latency target: 5–9s (vs 8–19s current)

---

## Architecture Overview

```
MemorySaver (session carry-over — unchanged)
        │
User message + session_id + user_profile
        │
  ┌─────▼──────────────────────────────────────────┐
  │  DISPATCH  (1 LLM call, ~300 tokens out)        │
  │                                                 │
  │  Reads: last 8 messages + user_profile          │
  │  Outputs:                                       │
  │    • query_decomposition  (free text)           │
  │    • user_tier: casual | active | expert        │
  │    • tasks: [{tool, args, priority}]            │
  │    • browsing_strategy: {topics[], geo, always_news} │
  └─────┬──────────────────────────────────────────┘
        │ fires all tasks simultaneously
  ┌─────▼──────────────────────────────────────────┐
  │  EXECUTOR  (async parallel, 0 LLM tokens)       │
  │                                                 │
  │  get_live_price      ─┐                         │
  │  get_historical_prices─┤                        │
  │  get_rl_prediction   ─┼─ all concurrent        │
  │  get_macro_news      ─┤                         │
  │  search_market_news  ─┘                         │
  │                                                 │
  │  Streams tool_start/tool_result SSE as each     │
  │  completes. Partial results acceptable.         │
  └─────┬──────────────────────────────────────────┘
        │ collected results
  ┌─────▼──────────────────────────────────────────┐
  │  SYNTHESIZE  (~400 tokens out, streamed)        │
  │                                                 │
  │  • Format decided by LLM, not prompt template   │
  │  • Depth/vocabulary from user_tier              │
  │  • RL envelope injected if ticker found         │
  │  • Streams as tokens (same SSE as today)        │
  └─────────────────────────────────────────────────┘
                     END  (no reviewer)
```

---

## What Is Dropped

| Dropped | Reason |
|---|---|
| Fixed 9 intent types | Dispatch uses open reasoning — no buckets |
| `needs_external` gate | News always runs unless purely conversational |
| `planner` node | Merged into dispatch |
| `classify` node | Merged into dispatch |
| Reviewer-synthesize loop | 1–3s cost, doesn't catch stale tool results |
| 120-word rigid format | Format emerges from content + user tier |
| `intent`, `todo_list`, `needs_external`, `review_count`, `reviewer_feedback` state fields | Replaced by simpler state schema |

## What Is Kept

- MemorySaver conversation carry-over (unchanged)
- SSE stream event contract (unchanged — frontend needs no changes)
- Serper/Tavily search strategy — geo detection, dated-first sort (unchanged)
- All 8 existing tools (unchanged)
- RL data files — chat reads only, never writes

---

## Node 1: Dispatch

### Purpose

One LLM call that replaces both `classify` and `planner`. Produces a free-form query decomposition, detects user sophistication, and plans which tools to call — without any hardcoded intent categories.

### Output schema

```json
{
  "query_decomposition": "User wants a 3-day Sensex trend comparison and directional prediction for today. IT sector mentioned as concern. Market not yet open.",
  "user_tier": "active",
  "tasks": [
    {"tool": "get_historical_prices", "args": {"symbol": "^BSESN", "days": 5},  "priority": 1},
    {"tool": "get_rl_prediction",     "args": {"ticker": "SENSEX"},              "priority": 1},
    {"tool": "get_live_price",        "args": {"symbol": "^BSESN"},              "priority": 1},
    {"tool": "search_market_news",    "args": {"query": "Sensex IT sector outlook India"}, "priority": 2},
    {"tool": "get_macro_news",        "args": {},                                "priority": 2}
  ],
  "browsing_strategy": {
    "topics": ["Sensex trend", "IT sector drag", "pre-market cues"],
    "geo": "in",
    "always_news": true
  }
}
```

### User tier detection

Dispatch infers tier from how the user writes and what they ask — no hardcoded rules. The LLM detects it from vocabulary, specificity, and question structure:

| Tier | Signal examples | Response style |
|---|---|---|
| `casual` | "why is market down", "is Sensex good today" | Plain English, one key takeaway, no jargon |
| `active` | "compare last 3 days Sensex", "IT sector dragging" | Price + direction + 2–3 dated headlines + watch signals |
| `expert` | "VIX elevated, FII outflow 3 days, RSI oversold — contrarian?" | Regime, RL conviction, agent weights, raw signals, tables |

Tier is written to `user_profile` after each turn. After 3+ sessions, dispatch reads the stored tier and stops re-detecting — saves tokens, improves consistency.

### Always-news rule

`browsing_strategy.always_news = true` for all non-trivial queries. Dispatch sets this. Executor does not gate news behind any flag — it fires if the task is in the list. A query is trivial (always_news=false) only when it is purely definitional — e.g. "what is P/E ratio", "explain SIP". Everything involving a market, asset, sector, event, or opinion gets news.

### Fallback on malformed dispatch output

If dispatch returns invalid JSON or 0 tasks: run `get_live_price(nifty)` + `search_market_news(India Nifty Sensex)` + `get_macro_news`. Safe minimum. No crash.

### Prompt

```
Today: {date} ({weekday}) — NSE {open|closed, last trading day if closed}
User profile: tier={tier}, sessions={n}, topics_seen=[...]

Conversation (last 8 messages):
{messages}

---
You are a financial intelligence dispatcher.

Decompose what the user actually needs — in plain English, no categories.
Identify their sophistication tier from how they write and what they ask.
Plan which tools to call. Include news search on anything non-trivial.
If a ticker or sector is mentioned, include get_rl_prediction.
Map common names: Sensex → ^BSESN, Nifty → ^NSEI, stocks → TICKER.NS

Output valid JSON matching the schema. Nothing else.
```

**Model:** `_FAST_MODEL` · **Temperature:** 0.0 · **Max tokens:** 350

---

## Node 2: Executor (Async Parallel)

### Purpose

Fires all tasks from dispatch concurrently using `asyncio.gather`. Streams `tool_start` SSE for all tasks immediately, then `tool_result` SSE as each completes. Partial results are passed to synthesize — one tool failing does not block others.

```python
results = await asyncio.gather(
    *[run_tool(task) for task in tasks],
    return_exceptions=True  # one failure never kills the rest
)
```

### Tool roster — 10 total

| Tool | Source | Change |
|---|---|---|
| `get_live_price` | yfinance | Unchanged |
| `get_sector_snapshot` | yfinance + DB | Unchanged |
| `get_stock_analysis` | SQLite DB | Unchanged |
| `get_analysis_history` | SQLite DB | Unchanged |
| `get_macro_news` | `data/macro_news/` cache | Unchanged |
| `run_agent_analysis` | sector orchestrator | Unchanged — dispatch plans it when query_decomposition indicates deep multi-stock analysis AND user_tier=expert |
| `search_market_news` | Serper /news + Tavily fallback | Unchanged |
| `get_rl_insights` | SQLite DB | Unchanged |
| **`get_historical_prices`** | yfinance | **NEW** |
| **`get_rl_prediction`** | prediction envelope JSON | **NEW** |

### New tool: `get_historical_prices`

Fetches last N trading days of OHLCV for any yfinance symbol.

```
Args:  {"symbol": "^BSESN", "days": 5}

Output:
SENSEX (^BSESN) — Last 5 trading days:
2026-05-09 (Fri)  Close: 80,218  Change: -0.42%
2026-05-12 (Mon)  Close: 80,891  Change: +0.86%
2026-05-13 (Tue)  Close: 80,654  Change: -0.67%
2026-05-14 (Wed)  Close: 79,980  Change: -0.65%
2026-05-15 (Thu)  Market not yet open — last close: 79,980
Trend: 3 consecutive down days. Net 5-day: -0.30%
```

Returns explicit "no data for {symbol}" if yfinance fails — synthesize states it and moves on.

### New tool: `get_rl_prediction`

Reads today's row from the prediction envelope JSON for a ticker. Returns the RL system's verdict, confidence, regime, and conviction streak. Returns empty string if no envelope exists — synthesize ignores empty results silently. Dispatch maps index queries (Sensex, Nifty) to the nearest tracked sector envelope if available (e.g. `banking_bfsi` for Nifty Bank). If no sector envelope exists, tool returns empty string.

```
Args:  {"ticker": "TCS"}

Output:
RL PREDICTION — TCS (2026-05-15):
Verdict: BUY  |  Confidence: 0.64  |  Predicted close: ₹3,847
Regime: RISK_OFF (VIX elevated, FII selling)
Conviction streak: 7 consecutive BUY days — reversion prior: 5%
Key assumptions: ["INR stable ~₹84", "US tech earnings neutral"]
Revised: Yes (revision 2) — thesis partially intact after May 14 miss
```

### SSE stream order

Tools stream `tool_start` immediately (all at once), then `tool_result` in arrival order:

```
tool_start:  get_live_price          ← fires at t=0
tool_start:  get_historical_prices   ← fires at t=0
tool_start:  get_rl_prediction       ← fires at t=0
tool_start:  search_market_news      ← fires at t=0
tool_result: get_live_price          ← arrives ~1s
tool_result: get_rl_prediction       ← arrives ~1s (file read)
tool_result: get_historical_prices   ← arrives ~2s
tool_result: search_market_news      ← arrives ~2s
```

---

## Node 3: Synthesize

### Purpose

Aggregates all tool results and produces a response. Format and depth are not enforced by prompt template — the LLM decides based on content and user tier. Streams as tokens.

### Prompt

```
Today: {date} — NSE {open|closed, last trading day if closed}

User tier: {casual|active|expert}
What the user needs: {query_decomposition}

RESEARCH RESULTS:
{all tool results, labelled by tool name}

---
Respond as a sharp Indian market analyst in a conversation.
Format and depth must match the user tier:

CASUAL   → 3–4 plain sentences. One key insight. No jargon. No tables.
ACTIVE   → Price + direction + 2–3 dated headlines + watch signals.
            Use ▲/▼. Under 150 words.
EXPERT   → Regime, RL signal, conviction, key assumptions, raw metrics.
            Tables if helpful. No word cap.

Rules that always apply:
- If market not yet open, say so and reason from last close + pre-market cues
- Cite exact headlines with source and date — never paraphrase into fiction
- If RL prediction exists, surface it naturally (never say "RL" to casual users — say "our model")
- If historical data shows a trend, state it — do not fabricate a predicted number
- Never say "real-time data required" — state what you have and its date
- Never add disclaimers or "I cannot predict" hedges unless directly asked
```

**Model:** `_FAST_MODEL` · **Temperature:** 0.4 · **Max tokens:** 500

### Tier response examples — same query

Query: *"Comparing last 3 days Sensex — predict today"* (market not yet open, May 15)

**Casual:**
> Sensex has slipped three days in a row, down about 0.3% this week. IT and metals have been the drag. Pre-market signals look cautious — global cues are mixed and FIIs have been selling. Likely another flat-to-slightly-down open unless something changes before 9:15.

**Active:**
> **Sensex ▼ 3-day trend** — 80,891 → 80,654 → 79,980 (-0.65% Wed)
>
> **Why:** "IT stocks drag Sensex for third session as US tech outlook dims" — ET, May 14 · "FII net sell ₹3,200Cr Wednesday" — Mint, May 14
>
> **Today (pre-open):** Our model is cautiously bearish — 64% confidence, BUY streak at 7 days (reversion risk rising). Watch: FII provisional data at 9:30, Nifty IT open.

**Expert:**
> Regime: RISK_OFF — VIX 21.4, Nifty 5d momentum -1.1%, IT RSI 38
> RL: BUY | Confidence 0.64 | Streak 7d | Reversion prior 5% | Multiplier 0.85 (one assumption broken: US tech neutral ✗)
> 5-day OHLCV: [table]
> Watch: FII provisional, CNXIT vs ^NSEI spread at open, VIX direction 9:15.

---

## State Schema

```python
class ChatState(TypedDict):
    messages:            Annotated[list, operator.add]  # unchanged — MemorySaver key
    query_decomposition: str | None                     # from dispatch
    user_tier:           str | None                     # casual | active | expert
    browsing_strategy:   dict | None                    # from dispatch
    tasks:               list[dict] | None              # from dispatch
    tool_results:        list[dict] | None              # from executor
```

Removed: `intent`, `todo_list`, `needs_external`, `review_count`, `reviewer_feedback`

---

## User Profile

Stored at `data/user_profiles/{session_id}.json`. Written after each synthesis turn.

```json
{
  "session_id": "abc-123",
  "detected_tier": "active",
  "tier_confidence": 0.82,
  "sessions_seen": 4,
  "topics_seen": ["Sensex", "IT sector", "FII flows"],
  "last_seen": "2026-05-15"
}
```

- Missing or corrupt file → defaults to `active` tier, writes fresh file after turn
- After 3+ sessions → dispatch reads stored tier, skips re-detection

---

## Error Handling

| Failure | Behavior |
|---|---|
| Serper times out | Tavily fallback (same as today) |
| Both Serper + Tavily fail | Synthesize works with remaining results |
| yfinance returns no data | Tool returns "no data for {symbol}" — synthesize states it |
| RL envelope missing | `get_rl_prediction` returns empty string — synthesize ignores |
| `asyncio.gather` task throws | Caught via `return_exceptions=True` — logged, treated as empty |
| Dispatch returns malformed JSON | Fallback: `get_live_price(nifty)` + `search_market_news` + `get_macro_news` |
| User profile missing/corrupt | Default to `active` tier, write fresh profile after turn |

---

## SSE Event Contract

New `dispatch` event added. All other events unchanged — no frontend breaking changes.

```
data: {"event":"dispatch",    "tier":"active", "query":"3-day Sensex trend + prediction"}
data: {"event":"tool_start",  "tool":"get_historical_prices", "args":{"symbol":"^BSESN","days":5}}
data: {"event":"tool_start",  "tool":"get_rl_prediction",     "args":{"ticker":"SENSEX"}}
data: {"event":"tool_start",  "tool":"search_market_news",    "args":{"query":"..."}}
data: {"event":"tool_result", "tool":"get_live_price",        "summary":"Sensex 79,980 ▼0.65%"}
data: {"event":"tool_result", "tool":"get_rl_prediction",     "summary":"BUY 0.64 conf, streak 7d"}
data: {"event":"token",       "text":"**Sensex ▼ 3-day trend**..."}
data: {"event":"done"}
```

---

## Latency Profile

| Step | Current | New |
|---|---|---|
| classify + planner | ~2–6s (2 serial calls) | ~1–2s (1 call) |
| executor tools | ~3–5s (sequential) | ~2–3s (parallel) |
| synthesize | ~2–5s | ~2–4s |
| reviewer | ~1–3s | **0s (dropped)** |
| **Total** | **~8–19s** | **~5–9s** |

---

## Files Changed

| File | Change |
|---|---|
| `services/api/chat_graph.py` | Full rewrite — 3 nodes, async executor, new state schema |
| `services/api/routes/ui_data.py` | Add `get_historical_prices`, `get_rl_prediction`. Remove reviewer SSE. |
| `services/api/prompts/dispatch.py` | New — dispatch system prompt |
| `services/api/prompts/synthesize.py` | New — tier-aware synthesize prompt (replaces old) |
| `services/api/prompts/classify.py` | Deleted |
| `services/api/prompts/planner.py` | Deleted |
| `services/api/prompts/reviewer.py` | Deleted |
| `data/user_profiles/` | New directory — one JSON per session_id |
| `src/frontend/prototypes/sphere.jsx` | Optional: display tier badge from `dispatch` event |
| All other files | Unchanged |

---

## Token Budget per Request

| Node | Tokens in | Tokens out |
|---|---|---|
| dispatch | ~450 | ~300 |
| executor | 0 | 0 |
| synthesize | ~900 | ~400 |
| **Total** | **~1350** | **~700** |

Current total (reviewer pass): ~1790 in / ~820 out. New design is cheaper and faster.
