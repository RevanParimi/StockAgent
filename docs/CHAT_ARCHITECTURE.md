# Chat Architecture — 3-Node Open Dispatch Pipeline

## Overview

The chat system uses a **3-node LangGraph pipeline** backed by `MemorySaver` for cross-request
conversation carry-over. Every HTTP request adds one user message to the graph state; the
`MemorySaver` automatically restores the full prior conversation for that `session_id`, so
no client-side history is ever needed.

The pipeline replaced the old 5-node classify→plan→execute→synthesize→review design.
Key differences: open query decomposition (no fixed intent categories), parallel async tool
execution, user-tier-aware response format, and no reviewer loop.

---

## Model Strategy

One model is used for all LLM nodes:

| Constant | Model | Used for | Latency |
|---|---|---|---|
| `_FAST_MODEL` | `settings.LLM_MODEL` (default: `qwen/qwen-2.5-72b-instruct`) | dispatch, synthesize | ~1–3s per call |

All nodes use `_FAST_MODEL`. Switch `LLM_MODEL` in `.env` to upgrade quality at cost of latency.

---

## Graph

```
User message + session_id + user_profile
        │
        ▼
  ┌─────────────────────────────────────┐
  │  dispatch                           │  _FAST_MODEL (400 tok)
  │  • Free-form query decomposition    │  → query_decomposition, user_tier
  │  • User sophistication detection    │  → tasks[], browsing_strategy
  │  • Parallel task plan               │  (no fixed intent categories)
  └──────┬──────────────────────────────┘
         │ fires all tasks simultaneously
  ┌──────▼──────────────────────────────┐
  │  executor  (async parallel, 0 LLM)  │  asyncio.gather over all tasks
  │  get_live_price      ─┐             │  → SSE tool_start for all
  │  get_historical_prices─┤            │  → SSE tool_result as each arrives
  │  get_rl_prediction   ─┼─ parallel  │
  │  get_macro_news      ─┤            │
  │  search_market_news  ─┘            │
  └──────┬──────────────────────────────┘
         │ collected results
  ┌──────▼──────────────────────────────┐
  │  synthesize                         │  _FAST_MODEL (500 tok, streamed)
  │  • Format decided by LLM            │  → tier-adaptive response
  │  • Depth from user_tier             │  → streams as tokens
  │  • RL signal injected if available  │  → saves user_profile after
  └─────────────────────────────────────┘
                    END
```

---

## State

```python
class ChatState(TypedDict):
    messages:            Annotated[list, operator.add]  # MemorySaver key — unchanged
    session_id:          str | None                     # session identifier
    query_decomposition: str | None                     # from dispatch: what user needs
    user_tier:           str | None                     # casual | active | expert
    browsing_strategy:   dict | None                    # from dispatch: topics, geo, always_news
    tasks:               list[dict] | None              # from dispatch: [{tool, args, priority}]
    tool_results:        list[dict] | None              # from executor: [{tool, result, error}]
```

`messages` uses `operator.add` reducer — each request appends to the existing list in MemorySaver.

---

## Nodes

### 1. dispatch

**Model:** `_FAST_MODEL` · **Tokens out:** ~400 · **Temperature:** 0.0

Reads the last 8 messages and the user's profile. Outputs structured task plan via a single
LLM call — replaces both `classify` and `planner` from the old pipeline.

**Key behaviours:**
- No fixed intent categories — free-form `query_decomposition` in plain English
- Detects user tier from vocabulary and specificity: `casual` / `active` / `expert`
- `always_news=true` for any non-definitional query — news is never gated
- Includes `get_rl_prediction` whenever a ticker or sector is mentioned
- Includes `get_historical_prices` for any trend/comparison/prediction query
- Falls back to `[get_live_price(nifty), get_macro_news, search_market_news]` if LLM returns 0 tasks

**Dispatch output:**
```json
{
  "query_decomposition": "User wants 3-day Sensex trend and direction for today (pre-open)",
  "user_tier": "active",
  "tasks": [
    {"tool": "get_historical_prices", "args": {"symbol": "^BSESN", "days": 5}, "priority": 1},
    {"tool": "get_live_price",        "args": {"symbol": "^BSESN"},            "priority": 1},
    {"tool": "search_market_news",    "args": {"query": "Sensex India outlook"},"priority": 2}
  ],
  "browsing_strategy": {"topics": ["Sensex trend"], "geo": "in", "always_news": true}
}
```

**SSE event emitted:**
```json
{"event": "dispatch", "session_id": "...", "tier": "active", "query": "3-day Sensex trend..."}
```

---

### 2. executor (parallel)

**Cost:** 0 LLM tokens — purely async I/O via `asyncio.gather`

Fires all tasks from dispatch concurrently. Emits `tool_start` for all tasks immediately,
then `tool_result` as each completes (in arrival order — fastest tool appears first).

One failure never blocks the rest — `asyncio.gather(return_exceptions=True)` ensures
a Serper timeout doesn't stop the RL prediction from appearing.

**Tool roster (10 total):**

| Tool | Source | Notes |
|---|---|---|
| `get_live_price` | yfinance | Current price + % change |
| `get_historical_prices` | yfinance | Last N days OHLCV + trend summary |
| `get_sector_snapshot` | yfinance + DB | All stocks in a sector |
| `get_stock_analysis` | SQLite DB | Verdict lookup |
| `get_analysis_history` | SQLite DB | Historical verdicts |
| `get_rl_prediction` | prediction envelope JSON | RL verdict + confidence + conviction |
| `get_rl_insights` | SQLite DB | Agent-level RL breakdown |
| `get_macro_news` | `data/macro_news/` cache | Today's HIGH/MEDIUM/LOW macro news |
| `search_market_news` | Serper /news + Tavily fallback | Live news with geo detection |
| `run_agent_analysis` | sector orchestrator | Deep mode, expert tier only (~45s) |

**SSE events emitted:**
```json
{"event": "tool_start",  "tool": "get_historical_prices", "args": {"symbol": "^BSESN", "days": 5}}
{"event": "tool_result", "tool": "get_historical_prices", "summary": "^BSESN — Last 5 trading days:\n..."}
```

---

### 3. synthesize

**Model:** `_FAST_MODEL` · **Tokens out:** ~500 · **Temperature:** 0.4 · **Streaming**

Aggregates all tool results and produces a response. Format and depth are decided by the
LLM based on content and user tier — no rigid 120-word template.

**Tier-adaptive format:**

| Tier | Format |
|---|---|
| `casual` | 3–4 plain sentences, one key insight, no jargon, no tables |
| `active` | Price + direction + 2–3 dated headlines + watch signals. Under 150 words. Uses ▲/▼ |
| `expert` | Regime, RL signal, conviction streak, key assumptions, raw metrics. Tables if helpful. No word cap |

**Hard rules in prompt:**
- If market not yet open, say so and reason from last close + pre-market cues
- Cite exact headlines with source and date — never paraphrase into fabricated summaries
- RL prediction: `casual` → "our model says"; `active` → verdict + confidence; `expert` → full metrics
- Historical trend: state what the data shows — never fabricate a predicted price number
- Never say "real-time data required" — state what you have and its date
- Empty tool results are silently ignored

**After synthesis:** saves updated `user_profile` (tier, topics, sessions_seen) to
`data/user_profiles/{session_id}.json` for tier carry-over across sessions.

**SSE events emitted:**
```json
{"event": "thinking"}                 (if model enters think phase)
{"event": "token", "text": "**Sensex ▼ 3-day trend**..."}
{"event": "done"}
```

---

## User Profile

Stored at `data/user_profiles/{session_id}.json`. Written after every synthesis turn.

```json
{
  "session_id": "abc-123",
  "detected_tier": "active",
  "tier_confidence": 0.82,
  "sessions_seen": 4,
  "topics_seen": ["Sensex", "IT sector", "FII flows"],
  "last_seen": "2026-05-17"
}
```

After 3+ sessions the tier stabilises — dispatch reads the stored value instead of re-detecting.

---

## Available Tools — search_market_news in detail

Primary: Serper `/news` · Fallback: Tavily (only when Serper returns 0)

**Geo detection from query content:**

| Query | India terms? | geo used |
|---|---|---|
| "why did Nifty fall" | yes (Nifty) | `"in"` |
| "OpenAI IT stocks" | no | `None` (global) |
| "why is market down" | no | `"in"` (default) |

**Retry strategy:**
1. Serper /news with detected geo, 5 results
2. Auto-retry if 0 results and no India terms (strip + prefix "India Nifty")
3. Conditional second query if <3 results and global entity detected
4. Fallback to Tavily only when all Serper passes return 0

---

## Temporal Grounding

Every node that calls an LLM receives today's date + NSE market status.

| Layer | How |
|---|---|
| `dispatch` system prompt | `f"{market_ctx}\nUser profile: ..."` — market context first line |
| `synthesize` system prompt | `_nse_market_context()` first in prompt |
| `search_market_news` result | `=== NEWS RESULTS ===\nTODAY: ...` header |

**NSE market status** (`_nse_market_context()`):
```
TODAY: 2026-05-17 (Sunday) — NSE market CLOSED (weekend / holiday)
Last NSE trading day: 2026-05-16 (Friday)
```

---

## Carry-Over Mechanism

```python
# MemorySaver stores state.messages per thread_id
# operator.add reducer appends new messages on every request

# Session 1, Request 1:  state.messages = [user_msg_1, assistant_msg_1]
# Session 1, Request 2:  state.messages = [user_msg_1, assistant_msg_1, user_msg_2, ...]
# Session 2, Request 1:  state.messages = [user_msg_A]   ← completely isolated
```

When the user says "what about IT?" after discussing Sensex, dispatch sees the full prior
conversation and understands the context. No client-side history needed.

---

## SSE Event Stream (endpoint: POST /ui/chat/stream)

```
Request:  {"message": "Compare last 3 days Sensex, predict today", "session_id": null}
Response: text/event-stream

data: {"event":"dispatch",    "session_id":"<uuid>", "tier":"active", "query":"3-day Sensex trend..."}
data: {"event":"tool_start",  "tool":"get_historical_prices", "args":{"symbol":"^BSESN","days":5}}
data: {"event":"tool_start",  "tool":"get_live_price",        "args":{"symbol":"^BSESN"}}
data: {"event":"tool_start",  "tool":"search_market_news",    "args":{"query":"Sensex India outlook"}}
data: {"event":"tool_result", "tool":"get_live_price",        "summary":"Sensex (^BSESN): 79,980 ▼0.65%"}
data: {"event":"tool_result", "tool":"get_historical_prices", "summary":"^BSESN — Last 5 trading days:..."}
data: {"event":"tool_result", "tool":"search_market_news",    "summary":"=== NEWS RESULTS (Serper)..."}
data: {"event":"token",       "text":"**Sensex ▼ 3-day trend**\n\n80,891 → 80,654 → 79,980..."}
data: {"event":"done"}
```

**Events removed vs old pipeline:** `intent`, `plan`, `review` — these were emitted by the
old classify/planner/reviewer nodes, which no longer exist.

---

## Token Budget per Request

| Node | Model | Tokens in | Tokens out | Notes |
|---|---|---|---|---|
| dispatch | `_FAST_MODEL` | ~450 | ~400 | last 8 msgs + profile + system |
| executor | — | 0 | 0 | async I/O only |
| synthesize | `_FAST_MODEL` | ~900 | ~500 | history + tool results; streamed |
| **Total** | | **~1,350** | **~900** | vs ~1,790/~820 in old pipeline |

**Latency breakdown:**

| Step | Time |
|---|---|
| dispatch | ~1–2s (1 API call vs 2 in old pipeline) |
| executor tools | ~2–3s (parallel vs ~3–5s sequential) |
| synthesize | ~2–4s |
| reviewer | **0s** (removed) |
| **Target** | **~5–9s** (vs 8–19s old pipeline) |

---

## Files

| File | Role |
|---|---|
| `services/api/chat_graph.py` | Graph definition: 3 nodes, `_node_dispatch`, `_node_executor`, `_new_synthesize_node`, `_build_synthesize_prompt` |
| `services/api/routes/ui_data.py` | `/ui/chat/stream` SSE endpoint, all 10 tool implementations, `_nse_market_context`, `_execute_chat_tool` |
| `services/api/user_profile.py` | Per-session user tier profile: `load_profile`, `save_profile` |
| `services/data/fetchers/news.py` | `search_serper_news(query, n, geo)` — Serper `/news` endpoint |
| `src/frontend/prototypes/sphere.jsx` | `ChatOverlay` — session_id state, SSE reader, tier badge from `dispatch` event |

See [MACRO_NEWS.md](MACRO_NEWS.md) for the background macro news feed architecture.
