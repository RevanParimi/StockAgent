# Chat Architecture — LangGraph Planner Pipeline

## Overview

The chat system uses a **5-node LangGraph pipeline** backed by `MemorySaver` for cross-request
conversation carry-over. Every HTTP request adds one user message to the graph state; the
`MemorySaver` automatically restores the full prior conversation for that `session_id`, so
no client-side history is ever needed.

The fifth node — `reviewer` — is a cheap factual accuracy pass that runs after every synthesis.
It checks date integrity, price grounding, question relevance, and macro news coverage before
accepting the answer or sending it back for one more synthesis with targeted feedback.

---

## Graph

```
User message + session_id
        │
        ▼
  ┌─────────────┐
  │  classify   │  LLM call (120 tok) → intent_type, entities, focus
  └──────┬──────┘   (today's date prepended to system prompt)
         │
  ┌──────▼──────┐
  │   planner   │  LLM call (250 tok) → depth, needs_external, ordered task list
  └──────┬──────┘   (today's date prepended; 8 tools available)
         │
  ┌──────▼──────┐
  │  executor   │◄──────────────────────┐  one task per traversal
  └──────┬──────┘                       │
         │ pending tasks?               │
     yes │ ──────────────────────────── ┘  loop
      no │
  ┌──────▼──────┐
  │ synthesize  │  LLM call (600 tok) → final answer (streamed as tokens)
  └──────┬──────┘   (reviewer_feedback injected on re-synthesis passes)
         │
  ┌──────▼──────┐
  │  reviewer   │  LLM call (200 tok) → pass / fail with specific issues
  └──────┬──────┘   (max CHAT_MAX_REVIEW_CYCLES=3 before accepting answer)
         │
    pass │ count≥N
        END
         │ fail + count<N
        synthesize  (loop with feedback)
```

---

## State

```python
class ChatState(TypedDict):
    messages:          Annotated[list, operator.add]  # plain OpenAI-format dicts
    intent:            dict | None                    # from classify
    todo_list:         list[dict] | None              # from planner, mutated by executor
    needs_external:    bool | None                    # from planner, gates Tavily
    review_count:      int | None                     # reviewer loop iterations so far
    reviewer_feedback: str | None                     # critique from last reviewer; None = passed
```

`messages` uses `operator.add` as the reducer — each new request appends its messages
to the existing list stored by `MemorySaver`. This is the entire carry-over mechanism.

`reviewer_feedback` is reset to `None` by `synthesize` at the start of each pass, then
set by `reviewer` if issues are found. A `None` value in `reviewer` → routes to END.

---

## Nodes

### 1. classify

**Cost:** ~120 tokens · **Temperature:** 0.0

Reads the last 6 messages (including the new user message just added by the reducer)
and outputs structured intent. Uses `<json>` delimiter + `_extract_json()` to handle
Qwen3 thinking tokens.

**Today's date is prepended** to the system prompt at call time:
```
Today's date: 2026-05-12 (Tuesday)

[CLASSIFY_SYSTEM_PROMPT follows...]
```
This anchors the LLM's temporal context so it classifies "why did markets fall today"
correctly rather than reasoning from its training cutoff.

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
Today's date is prepended to the system prompt (same pattern as classify) so the planner
builds date-accurate search queries.

**Two decisions:**
- `depth` (`"shallow"` / `"deep"`) — LLM decides based on conversation complexity
- `needs_external` (`true` / `false`) — only `true` when live web news is genuinely needed

**Task priority order (always):**
```
1. get_live_price / get_sector_snapshot / get_macro_news  — free, instant
2. get_stock_analysis / get_analysis_history / get_rl_insights  — internal DB
3. run_agent_analysis   — heavy 9-agent pipeline, deep only
4. search_market_news   — Tavily, external=true only
```

**Enforced rules in planner prompt:**
- `NEWS_QUERY` with specific entity: always plan `get_live_price` as task 1 — prevents
  synthesize from fabricating prices from training memory.
- `NEWS_QUERY` with no entity ("any big news today"): plan `get_macro_news` first,
  then `search_market_news` as fallback.
- `get_macro_news` is the right tool for broad "what's happening in India markets today" queries.

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

| intent_type | fallback tasks |
|---|---|
| PRICE_QUERY + tickers | `get_live_price` per ticker |
| SECTOR_OVERVIEW + sectors | `get_sector_snapshot` per sector |
| SINGLE_STOCK / STOCK_COMPARE + tickers | `get_stock_analysis` per ticker |
| NEWS_QUERY + entities | `get_live_price(entity)` + `search_market_news` |
| NEWS_QUERY (no entity) | `get_macro_news` + `search_market_news` |
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
prompt as `RESEARCH RESULTS`. Calls the LLM once for the final answer, streams it as
`token` SSE events.

**Context block** (`_build_chat_context`) includes:
1. Today's date + NSE market status (open / closed, last trading day) — always present
2. Trending macro HIGH-severity news from background feed — only for `NEWS_QUERY`,
   `SECTOR_OVERVIEW`, `MULTI_SECTOR`, `GENERAL` intents (not SINGLE_STOCK/PRICE_QUERY)
3. Current ticker verdicts from DB

**On re-synthesis passes** (when `reviewer_feedback` is set), the system prompt includes:
```
REVIEWER FEEDBACK (revision N of 3):
Your previous answer had specific factual issues. Fix ONLY these — do not change anything else:
- [specific issue from reviewer]
How to fix: [reviewer hint]
```

The synthesize node resets `reviewer_feedback` to `None` at the start of each pass.

**SSE event emitted (repeated per chunk):**
```json
{"event": "token", "text": "Automobile sector shows "}
{"event": "token", "text": "mild weakness with the "}
...
{"event": "done"}
```

---

### 5. reviewer

**Cost:** ~200-300 tokens · **Temperature:** 0.0

Cheap factual accuracy pass on the latest synthesized answer. Runs after every synthesis.
Uses structured JSON output — either `{"pass": true}` or `{"pass": false, "issues": [...], "hint": "..."}`.

**Skips entirely when:**
- No tools ran (conversational GENERAL reply — nothing to ground-check)
- `CHAT_MAX_REVIEW_CYCLES = 0` (disabled via `.env` for dev/low-latency mode)
- `review_count >= CHAT_MAX_REVIEW_CYCLES` (limit reached, accept answer as-is)

**Four criteria (all must pass):**

**1. Date integrity** — Does the answer present data as current when tool results say otherwise?
- Flags: specific year in answer (e.g. "2023") contradicting TODAY's date
- Flags: "today" claims when tool results are from a prior day
- Does NOT flag: historical facts stated with their own date ("In 2023, X happened")

**2. Price grounding** — Does the answer cite a price not present in tool results?
- Flags: specific price for an asset where `get_live_price` ran and returned a different value
- Does NOT flag: analyst targets from news articles (those are opinions, not live prices)

**3. Question relevance** — Does the answer address what was asked?
- Flags only if answer is completely off-topic
- Does NOT flag partial but on-topic answers

**4. Macro news coverage** — Was a HIGH-severity trending macro item missed?
- Checks `impact_tags` of HIGH items against the question's entities (sectors, assets, tickers)
- Flags only if: tag overlap exists AND item would materially change the answer AND answer ignores it
- Does NOT flag: MEDIUM/LOW items, items with no overlap, items the answer already mentions

**Example: criterion 4 in action:**
```
User asked: "Should I invest in gold?"
TRENDING MACRO HIGH item: "Modi discouraged gold investment for 1 year" [tags: gold, policy]
User entities: {assets: ["gold"]}
→ intersection: {"gold"} — FLAG if answer doesn't mention this
```

**SSE event emitted:**
```json
{"event": "review", "cycle": 1, "pass": false, "issues": ["answer says Nifty at 17,850 but get_live_price returned 24,420"]}
{"event": "review", "cycle": 2, "pass": true}
```

---

## Available Tools (8 total)

| Tool | Source | Cost | When used |
|---|---|---|---|
| `get_live_price` | yfinance | free | any price query; mandatory for NEWS_QUERY |
| `get_sector_snapshot` | yfinance + DB | free | sector queries — all 27 sectors |
| `get_stock_analysis` | SQLite DB | free | stock verdict lookup |
| `get_analysis_history` | SQLite DB | free | trend / history |
| `get_rl_insights` | SQLite DB | free | agent trust queries |
| `get_macro_news` | `data/macro_news/` cache | free | broad "what's happening today" queries |
| `run_agent_analysis` | SectorRegistry → orchestrator | heavy (45s) | deep mode only |
| `search_market_news` | Tavily API | API cost | `needs_external=True`; fallback when macro cache empty |

### search_market_news — date-anchored queries

The tool implementation in `ui_data.py` automatically enriches every query:
1. **Pass 1** — adds `after:TODAY` to the query for same-day results
2. **Pass 2** — falls back to unanchored query if pass 1 returns nothing (weekends, niche topics)
3. Uses `search_depth="advanced"` — full article text, not 2-line snippets
4. Each result returned with structured age label: `[published: 2026-05-12 (today)]` /
   `[published: 2026-05-09 (3 days ago)]` / `[published: 2026-04-10 (32 days ago)]`
5. Results block has a market-context header: today's date + NSE open/closed + last trading day

### get_macro_news — background feed tool

Returns today's feed from the `MacroNewsCache`. Sorted HIGH → MEDIUM → LOW.
If the cache is empty (cold start or no HIGH items found today), returns an explicit
message and the planner's `search_market_news` fallback task picks up instead.
See [MACRO_NEWS.md](MACRO_NEWS.md) for the full background feed architecture.

### get_sector_snapshot — extended sector index

Sector key → NSE index: automobile `^CNXAUTO` · banking_bfsi `^NSEBANK` · it_sector `^CNXIT` ·
renewable_energy `^CNXENERGY` · pharma `^CNXPHARMA` · fmcg `^CNXFMCG` · metals `^CNXMETAL` ·
capgoods/infra `^CNXINFRA` · realestate `^CNXREALTY` · media `^CNXMEDIA` · retail `^CNXCONSUMP`

---

## Temporal Grounding

Every node that calls an LLM receives today's date. This prevents the classic failure mode
where the LLM reasons from its training cutoff instead of the actual current date.

**Where date is injected:**

| Layer | How | Effect |
|---|---|---|
| `classify` system prompt | `f"Today's date: {today}\n\n{CLASSIFY_SYSTEM_PROMPT}"` | Correct temporal scope extraction |
| `planner` system prompt | Same pattern | Date-accurate search query construction |
| `_build_chat_context()` | `_nse_market_context()` first line | Synthesize LLM knows today + NSE status |
| `search_market_news` result block | `=== NEWS RESULTS ===\nTODAY: ...` header | LLM sees market context with each result |
| reviewer user message | `TODAY: {today}` first line | Reviewer catches stale date claims |

**NSE market status** (`_nse_market_context()`):
```
TODAY: 2026-05-11 (Sunday) — NSE market CLOSED (weekend / holiday)
Last NSE trading day: 2026-05-09 (Friday)
```
This prevents the LLM from saying "today the market fell" when NSE was closed and the
most recent data is from the previous Friday.

**Result age labels** (in `search_market_news` output):
```
[Result 1 — published: 2026-05-12 (today)]
[Result 2 — published: 2026-05-09 (3 days ago)]
[Result 3 — published: 2026-04-10 (32 days ago)]
```
Relevance is left to the LLM — a 4-day-old RBI rate decision is still fully relevant,
a 4-day-old "why did Nifty fall on Tuesday" is not. No static threshold is applied.
The one special case: `date unknown — treat with caution` when Tavily returns no `published_date`.

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
Request:  {"message": "Why did Nifty fall today?", "session_id": null}
Response: text/event-stream

data: {"event":"intent",  "session_id":"<uuid>", "intent_type":"NEWS_QUERY", ...}
data: {"event":"plan",    "depth":"shallow", "needs_external":true, "tasks":[...]}
data: {"event":"tool_start",  "tool":"get_live_price", "args":{"symbol":"nifty"}}
data: {"event":"tool_result", "tool":"get_live_price", "summary":"Nifty 50 (^NSEI): 24,420 ▼1.2%..."}
data: {"event":"tool_start",  "tool":"search_market_news", "args":{"query":"India Nifty fall today"}}
data: {"event":"tool_result", "tool":"search_market_news", "summary":"=== NEWS RESULTS ===\nTODAY: 2026-05-12..."}
data: {"event":"token",   "text":"Nifty fell 1.2% today driven by..."}
data: {"event":"review",  "cycle": 1, "pass": true}
data: {"event":"done"}
```

If reviewer fails and triggers a re-synthesis:
```
data: {"event":"review",  "cycle": 1, "pass": false, "issues": ["answer cites Nifty 17,850 from training memory"]}
data: {"event":"token",   "text":"[revised answer begins]..."}
data: {"event":"review",  "cycle": 2, "pass": true}
data: {"event":"done"}
```

---

## Depth × External Matrix

| depth | needs_external | What happens |
|---|---|---|
| shallow | false | 1–3 internal tools, DB + yfinance + macro cache only |
| shallow | true | 1–3 tools + Tavily for live news |
| deep | false | all enabled internal tools including `run_agent_analysis` |
| deep | true | all internal tools + Tavily |

`needs_external` is decided solely by the planner LLM — no regex, no keyword matching.

---

## Token Budget per Request

| Node | Tokens in | Tokens out | Notes |
|---|---|---|---|
| classify | ~320 | 120 | last 6 msgs + date + system prompt |
| planner | ~420 | 250 | last 8 msgs + date + intent + system |
| executor | 0 | 0 | no LLM, pure tool dispatch |
| synthesize | ~900 | 600 | full history + context (with macro) + results |
| reviewer | ~300 | 100 | answer + tool results + today + macro items |
| re-synthesis (if needed) | ~950 | 600 | same as synthesize + reviewer feedback |
| **Total (pass)** | **~1940** | **~1070** | normal path with reviewer passing |
| **Total (1 retry)** | **~3190** | **~1770** | reviewer catches one issue, one re-synthesis |

Reviewer adds ~300 input tokens per request on every path. Re-synthesis is rare in practice —
most answers pass on the first reviewer cycle. Set `CHAT_MAX_REVIEW_CYCLES=0` in `.env`
to disable the reviewer entirely (e.g., latency-sensitive deployments).

---

## Files

| File | Role |
|---|---|
| `services/api/chat_graph.py` | Graph definition, all 5 nodes, MemorySaver singleton, REVIEWER_SYSTEM_PROMPT |
| `services/api/routes/ui_data.py` | `/ui/chat/stream` SSE endpoint, all 8 tool implementations, `_nse_market_context`, `_result_age_label`, `_build_chat_context` |
| `services/background/macro_news_fetcher.py` | FetchAgent + ReviewAgent LLM loop for background India macro news |
| `services/background/macro_news_cache.py` | Daily JSON cache read/write, retention cleanup |
| `src/frontend/prototypes/sphere.jsx` | `ChatOverlay` — session_id state, SSE reader |

See [MACRO_NEWS.md](MACRO_NEWS.md) for the full background feed system documentation.
