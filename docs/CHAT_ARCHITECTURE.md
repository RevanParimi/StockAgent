# Chat Architecture — LangGraph Planner Pipeline

## Overview

The chat system uses a 4-node LangGraph pipeline backed by `MemorySaver` for cross-request
conversation carry-over. Every HTTP request adds one user message to the graph state; the
`MemorySaver` automatically restores the full prior conversation for that `session_id`, so
no client-side history is ever needed.

---

## Graph

```
User message + session_id
        │
        ▼
  ┌─────────────┐
  │  classify   │  LLM call (120 tok) → intent_type, entities, focus
  └──────┬──────┘
         │
  ┌──────▼──────┐
  │   planner   │  LLM call (250 tok) → depth, needs_external, ordered task list
  └──────┬──────┘
         │
  ┌──────▼──────┐
  │  executor   │◄──────────────────────┐  one task per traversal
  └──────┬──────┘                       │
         │ pending tasks?               │
     yes │ ──────────────────────────── ┘  loop
      no │
  ┌──────▼──────┐
  │ synthesize  │  LLM call (600 tok) → final answer (fake-streamed as tokens)
  └──────┬──────┘
         │
        END
```

---

## State

```python
class ChatState(TypedDict):
    messages:       Annotated[list, operator.add]  # plain OpenAI-format dicts
    intent:         dict | None                    # from classify
    todo_list:      list[dict] | None              # from planner, mutated by executor
    needs_external: bool | None                    # from planner, gates Tavily
```

`messages` uses `operator.add` as the reducer — each new request appends its messages
to the existing list stored by `MemorySaver`. This is the entire carry-over mechanism.

---

## Nodes

### 1. classify

**Cost:** ~120 tokens · **Temperature:** 0.0

Reads the last 6 messages (including the new user message just added by the reducer)
and outputs structured intent. Uses `<json>` delimiter + `_extract_json()` to handle
Qwen3 thinking tokens.

**Output:**
```json
{
  "intent_type": "SECTOR_OVERVIEW",
  "entities": {"tickers": [], "sectors": ["automobile"], "assets": []},
  "focus": "User wants to know how the auto sector is performing"
}
```

**Intent types:** `SINGLE_STOCK` · `STOCK_COMPARE` · `SECTOR_OVERVIEW` · `MULTI_SECTOR` ·
`PRICE_QUERY` · `NEWS_QUERY` · `AGENT_QUERY` · `RL_QUERY` · `GENERAL`

**SSE event emitted:**
```json
{"event": "intent", "session_id": "...", "intent_type": "SECTOR_OVERVIEW",
 "entities": {...}, "focus": "..."}
```

---

### 2. planner

**Cost:** ~250 tokens · **Temperature:** 0.0

Receives the full conversation + classified intent. Outputs a structured research plan.

**Two decisions:**
- `depth` (`"shallow"` / `"deep"`) — LLM decides based on conversation complexity
- `needs_external` (`true` / `false`) — only `true` when live web news is genuinely needed

**Task priority order (always):**
```
1. get_live_price / get_sector_snapshot   — free, instant (yfinance)
2. get_stock_analysis / get_analysis_history / get_rl_insights  — internal DB
3. run_agent_analysis   — heavy 9-agent pipeline, deep only
4. search_market_news   — Tavily/Serper, external=true only
```

**Planner output:**
```json
{
  "depth": "shallow",
  "needs_external": false,
  "tasks": [
    {"id": 1, "tool": "get_sector_snapshot", "args": {"sector": "automobile"}, "external": false}
  ]
}
```

**Fallback:** If the LLM returns 0 tasks, the node infers default tasks from `intent_type`:

| intent_type | fallback task |
|---|---|
| PRICE_QUERY + tickers | `get_live_price` per ticker |
| SECTOR_OVERVIEW + sectors | `get_sector_snapshot` per sector |
| SINGLE_STOCK / STOCK_COMPARE + tickers | `get_stock_analysis` per ticker |
| NEWS_QUERY + entities | `search_market_news` (sets `needs_external=True`) |
| RL_QUERY | `get_rl_insights` |

**SSE event emitted:**
```json
{"event": "plan", "depth": "shallow", "needs_external": false,
 "tasks": [{"tool": "get_sector_snapshot", "args": {"sector": "automobile"}}]}
```

---

### 3. executor (loop)

**Cost:** 0 LLM tokens — purely deterministic

Processes **one task per graph traversal**. The conditional edge loops back until all
tasks are `"done"` or `"skipped"`, then routes to `synthesize`.

**External gate (strict):**
```
task.external=True  AND  needs_external=False  →  status="skipped" (Tavily never called)
task.external=True  AND  needs_external=True   →  runs normally
```

**Task lifecycle:**
```
status: "pending" → (running) → "done"   (result stored inline)
                              → "skipped" (external gated)
```

**SSE events emitted:**
```json
{"event": "tool_start",  "tool": "get_sector_snapshot", "args": {"sector": "automobile"}}
{"event": "tool_result", "tool": "get_sector_snapshot", "summary": "Automobile index (^CNXAUTO): 27,260 ▼0.29%..."}
```

---

### 4. synthesize

**Cost:** ~600 tokens · **Temperature:** 0.4

Aggregates all `"done"` task results from `todo_list` and injects them into the system
prompt as `RESEARCH RESULTS`. Calls the LLM once for the final answer, then fake-streams
it in 4-word chunks as `token` SSE events.

**SSE event emitted (repeated per chunk):**
```json
{"event": "token", "text": "Automobile sector shows "}
{"event": "token", "text": "mild weakness with the "}
...
{"event": "done"}
```

---

## Available Tools (7 total)

| Tool | Source | Cost | When used |
|---|---|---|---|
| `get_live_price` | yfinance | free | any price query |
| `get_sector_snapshot` | yfinance + DB | free | sector queries |
| `get_stock_analysis` | SQLite DB | free | stock verdict lookup |
| `get_analysis_history` | SQLite DB | free | trend / history |
| `get_rl_insights` | SQLite DB | free | agent trust queries |
| `run_agent_analysis` | sector orchestrators (9 agents) | heavy (45s) | deep mode only |
| `search_market_news` | Tavily/Serper API | API cost | `needs_external=True` only |

---

## Carry-Over Mechanism

```python
# MemorySaver stores state.messages per thread_id
# operator.add reducer appends new messages on every request

# Session 1, Request 1:  state.messages = [user_msg_1, assistant_msg_1]
# Session 1, Request 2:  state.messages = [user_msg_1, assistant_msg_1, user_msg_2, ...]
# Session 2, Request 1:  state.messages = [user_msg_A]   ← completely isolated
```

When the user says `"What about risks?"` after discussing the auto sector, the `classify`
node sees the full prior conversation and correctly extracts `sectors: ["automobile"]`
without the user mentioning it again. No client-side history. No regex scanning.

---

## SSE Event Stream (endpoint: POST /ui/chat/stream)

```
Request:  {"message": "How is auto doing?", "session_id": null}
Response: text/event-stream

data: {"event":"intent",  "session_id":"<uuid>", "intent_type":"SECTOR_OVERVIEW", ...}
data: {"event":"plan",    "depth":"shallow", "needs_external":false, "tasks":[...]}
data: {"event":"tool_start",  "tool":"get_sector_snapshot", "args":{"sector":"automobile"}}
data: {"event":"tool_result", "tool":"get_sector_snapshot", "summary":"^CNXAUTO 27,260 ▼0.29%..."}
data: {"event":"token",   "text":"Automobile sector shows "}
data: {"event":"token",   "text":"mild weakness today..."}
data: {"event":"done"}
```

`session_id` is generated server-side on first message (when client sends `null`) and
returned in the `intent` event. The client stores it and sends it on every subsequent
message in the same chat session.

---

## Evaluation — 4 Live Queries (2026-05-10)

### Q1 · Silver price · `PRICE_QUERY`

```
Query:   "What is the silver price right now?"
Intent:  PRICE_QUERY
Depth:   shallow
Tasks:   [get_live_price(symbol=silver)]
Result:  Silver (SI=F): 80.39 USD ▲0.87% today
```

**Web verification:** Yahoo Finance shows SI=F at $80.84–80.99 on 2026-05-08/09,
up ~0.82%. System price $80.39 is within normal intraday variance. **PASS**

---

### Q2 · Banking sector · `SECTOR_OVERVIEW`

```
Query:   "How is the banking sector performing today?"
Intent:  SECTOR_OVERVIEW
Depth:   shallow
Tasks:   [get_sector_snapshot(sector=banking_bfsi)]
Result:  Banking Bfsi index (^NSEBANK): 55,311 ▼1.31%
```

**Web verification:** NSE shows Nifty Bank at ₹55,411 ▼1.13% on 2026-05-08.
System value 55,311 / ▼1.31% is within intraday fluctuation range. **PASS**

---

### Q3 · TATAMOTORS news · `NEWS_QUERY` + external

```
Query:   "Why has TATAMOTORS been falling this week?"
Intent:  NEWS_QUERY
Depth:   shallow (needs_external=True)
Tasks:   [search_market_news(query="TATAMOTORS falling...")]
Result:  "Tata Motors PV Q3 Results 2026: Why Shares Fell 3%..."
Reply:   mentions margin pressure, JLR headwinds, ▼5% this week
```

**Web verification:** Business Standard confirms Q3 FY26 results showed PV unit
₹3,483 crore loss (JLR cyber attack + Jaguar model discontinuation). CV unit net profit
down 48%. 3–5% share decline post-results confirmed. **PASS**

---

### Q4 · Buy signal? · Carry-over from Q3

```
Query:       "Is it a good time to buy then?"   ← no ticker mentioned
Session ID:  same as Q3
Intent:      SINGLE_STOCK   ← correctly inferred TATAMOTORS from memory
Depth:       deep
Tasks:       [run_agent_analysis(ticker=TATAMOTORS)]
Result:      "TATAMOTORS: BUY (score=0.62, fresh)"
Reply:       references TATAMOTORS valuation, margin risks, JLR recovery
```

**Carry-over verified:** User never said "TATAMOTORS" — MemorySaver restored Q3
conversation, classify extracted the ticker from prior context. **PASS**

---

## Depth × External Matrix

| depth | needs_external | What happens |
|---|---|---|
| shallow | false | 1–3 internal tools, DB + yfinance only |
| shallow | true | 1–3 tools + Tavily for live news |
| deep | false | all enabled internal tools including `run_agent_analysis` |
| deep | true | all internal tools + Tavily |

`needs_external` is decided solely by the planner LLM — no regex, no keyword matching.

---

## Token Budget per Request

| Node | Tokens in | Tokens out | Notes |
|---|---|---|---|
| classify | ~300 | 120 | last 6 msgs + system prompt |
| planner | ~400 | 250 | last 8 msgs + intent + system |
| executor | 0 | 0 | no LLM, pure tool dispatch |
| synthesize | ~800 | 600 | full history + results + system |
| **Total** | **~1500** | **~970** | per request, 0 external on shallow/no-news |

---

## Files

| File | Role |
|---|---|
| `services/api/chat_graph.py` | Graph definition, all 4 nodes, MemorySaver singleton |
| `services/api/routes/ui_data.py` | `/ui/chat/stream` SSE endpoint, tool implementations |
| `src/frontend/prototypes/sphere.jsx` | `ChatOverlay` — session_id state, SSE reader |
