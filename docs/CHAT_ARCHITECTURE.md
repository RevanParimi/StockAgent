# Chat Architecture — Agentic Streaming Tool-Loop

## Overview

The chat assistant is an **agentic streaming tool-loop**: the LLM reasons, calls tools across
several rounds, and streams a grounded answer. It is served at `POST /ui/chat/stream` (SSE),
with a non-streaming twin at `POST /ui/chat` that runs the same loop.

This replaced the earlier **3-node LangGraph pipeline** (`dispatch → executor → synthesize`,
`chat_graph.py` — removed 2026-06-03). That fixed DAG had to plan *all* tools up front, before
it knew (for example) which IT tickers existed, and could not take a follow-up step — so it
fell back to generic answers. The loop reasons in steps instead, and a **deterministic
pre-router** guarantees the right data is fetched for buy/sell/momentum questions regardless of
the model's tool-routing reliability.

The whole implementation lives in `services/api/routes/ui_data.py` — there is no separate graph
module any more.

---

## Model Strategy (hybrid)

| Role | Constant | Setting | Model |
|---|---|---|---|
| Chat loop | `_CHAT_MODEL` | `LLM_MODEL_FAST` | `qwen/qwen3.6-flash` |
| Fallback (rate-limit / 5xx) | `_CHAT_FALLBACK_MODEL` | `LLM_MODEL_REASONING` | `qwen/qwen3.7-max` |

Chosen from the **2026-06-03 model benchmark** (`scripts/model_bench.py`, 8 models × real
queries through this exact pipeline): qwen3.6-flash produced the deepest answers, fastest
(~12s), at low cost. `qwen3-235b` was **retired** (it broke JSON output and was a weak
function-caller); Gemini 3.5 Flash was rejected (truncated output + 64× the cost); Kimi K2.6
rejected (empty output + 68s latency).

`_chat_completion()` wraps every call with retry + exponential backoff on transient
rate-limit/5xx errors, then falls back to the reasoning model before giving up.

---

## Request Flow

```
user message + session_id
        │
        ▼
build prompt  ── _CHAT_SYSTEM_PROMPT  (grounding rules, step-back intent, tool guidance)
              ├─ _nse_market_context()  (IST session: PRE_OPEN / OPEN / CLOSED / HOLIDAY)
              └─ carried session history (_SESSION_HISTORY[session_id])
        │
        ▼
DETERMINISTIC PRE-ROUTER  ── _detect_invest_intent(message)
   buy / sell / momentum + a screenable sector?
   └─ YES → run screen_stocks(sector, mode) + search_market_news() ourselves,
            inject BOTH into context, emit their tool_result events
        │
        ▼
AGENTIC TOOL LOOP  (≤ _CHAT_MAX_TOOL_ROUNDS = 4)
   model picks tools → _execute_chat_tool() in parallel → results fed back → repeat
        │
        ▼
_sanitize_answer()  → stream as word-chunked `token` events → `done`
```

---

## 1. Deterministic Intent Pre-Router (plan-and-execute)

`_detect_invest_intent(message)` classifies a screen-type intent from keywords — **buy / sell /
momentum** — and the target sector. When both are present, the endpoint runs the plan itself
(`screen_stocks` + `search_market_news`) and injects the results into the prompt **before** the
model's loop.

This is a Tier-1 router (cf. the literature on separating routing from execution): it does not
rely on the model reliably choosing the right tool. It is what makes *"which IT stocks should I
buy now"* deterministically return **beaten-down value names** (near 1-month lows) with **real
catalysts** — instead of today's random gainers, or fabricated headlines when the model skips
the news search.

| Intent phrase | Action | screen_stocks mode |
|---|---|---|
| invest / buy / accumulate / undervalued / oversold | buy | `value` (near 1-mo lows — buy-the-dip) |
| book profit / trim / take profit / overbought | sell | `profit` (near 1-mo highs — trim) |
| momentum / leaders / strongest / breakout | momentum | `momentum` (1-week leaders) |

---

## 2. Agentic Tool Loop

Up to 4 rounds. Each round: one `chat.completions.create` (model decides tool calls) →
all tool calls executed concurrently via `asyncio.gather` → results appended → loop. When the
model returns no tool calls, that content is the final answer; if rounds are exhausted with
tools still pending, a final no-tools call composes the answer. The answer is streamed out as
small word-grouped `token` chunks for a streaming feel.

---

## 3. Tool Catalogue (12 tools)

| Tool | Source | Notes |
|---|---|---|
| `screen_stocks(sector, mode)` | yfinance 1-mo windows | **The insight engine.** `value` = beaten-down near lows; `momentum` = leaders; `profit` = extended near highs. Surfaces non-obvious picks, not blue-chips |
| `get_sector_snapshot(sector)` | yfinance + DB | Sector index **plus per-stock movers** (top gainers/losers, live %) + verdicts |
| `get_live_price(symbol)` | yfinance | NSE-first resolution; freshness-labelled (`live` vs `last close <date>`) |
| `get_historical_prices(symbol, days)` | yfinance | Last N days OHLCV + trend |
| `get_stock_analysis(ticker)` | SQLite | Latest verdict + score |
| `get_analysis_history(days)` | SQLite | Historical verdict trend |
| `get_rl_prediction(ticker)` | prediction JSON | RL verdict + confidence + conviction |
| `get_rl_insights()` | RL weight memory | Agent accuracy + learned weights + lessons |
| `get_macro_news()` | daily macro cache → **live Serper fallback** | Self-heals when the cache is empty |
| `get_ticker_dossier(ticker)` | `{TICKER}_dossier.json` digest | Accumulated thesis, response signatures, guidance, flow notes |
| `search_market_news(query)` | Serper /news + RRF, Tavily fallback | Multi-query fusion (see §4) |
| `run_agent_analysis(ticker)` | sector orchestrator | Deep 9-agent run (~45s) |

> Every dispatched tool — including `get_rl_prediction`, `get_macro_news`, and
> `get_historical_prices` — now has a matching `_CHAT_TOOLS` schema, enforced by a
> drift-guard test (previously these three were documented but uncallable).

---

## 4. Grounding Subsystems

**IST market session** — `_nse_market_context()` → `nse_calendar.market_session()` resolves the
*current* session in IST (not just whether today is a trading day): `PRE_MARKET`, `PRE_OPEN`,
`OPEN`, `CLOSED`, `HOLIDAY`. Prices fetched outside the OPEN session are explicitly labelled
**last close** so a settled price is never passed off as live. This killed the old
"market is OPEN at 9:16am" contradiction.

**NSE-first symbol resolution** — `_resolve_yf_symbol()` resolves a bare name India-first:
common-name aliases → registry tickers → India-preferred `yfinance.Search` (prefers `.NS`/`.BO`).
Fixes "reliance" resolving to the US ticker "RS".

**Multi-query + Reciprocal Rank Fusion** — `_chat_tool_search_news()` fires 2–3 deterministic
query variants and fuses the results with RRF (`_rrf_fuse`), surfacing relevant dated sources a
single phrasing would miss. A noise filter drops horoscope/astrology results.

**Deterministic answer sanitizer** — `_sanitize_answer()` strips banned data-limitation
disclaimer labels ("Critical Note", etc.) the model occasionally appends. (An LLM Reflexion
self-critique gate was trialled and rejected — on qwen it hallucinated or misjudged; the
grounded pre-router prevents fabrication at the source, which is more reliable.)

**Anti-fabrication contract** — the prompt requires every cited source to come from a fetched
tool result; with the pre-router injecting real screen + news, the model has no reason to invent.

---

## 5. Session Memory

In-process `_SESSION_HISTORY: dict[session_id → list[turn]]`, capped at the last 12 messages.
This replaced the LangGraph `MemorySaver` checkpointer — same semantics (in-RAM, cleared on
restart), no graph dependency. The client sends only `session_id`; no client-side history.

---

## SSE Event Stream (`POST /ui/chat/stream`)

```
Request:  {"message": "Which IT stocks should I buy now?", "session_id": null}
Response: text/event-stream

data: {"event":"intent",      "session_id":"<uuid>", "tier":"active", "query":"Which IT stocks..."}
data: {"event":"tool_result", "tool":"screen_stocks",      "summary":"It Sector screen — VALUE / OVERSOLD..."}
data: {"event":"tool_result", "tool":"search_market_news", "summary":"=== NEWS RESULTS (Serper + RRF) ..."}
data: {"event":"token",       "text":"**TCS ₹2,242 ▼8.4% (at 1-month low)** — deep discount on quality..."}
data: {"event":"done"}
```

Events: `intent` (sets/persists session_id + tier badge) · `tool_result` · `token` · `done`.
The frontend (`sphere.jsx`) reads `/ui/chat/stream` as a streaming `fetch`, falling back to the
blocking `/ui/chat` only if the stream fails.

---

## Files

| File | Role |
|---|---|
| `services/api/routes/ui_data.py` | The whole chat loop: `chat_stream`/`chat` endpoints, pre-router, `_CHAT_TOOLS` + all tool implementations, `_chat_completion`, `_nse_market_context`, `_resolve_yf_symbol`, `_rrf_fuse`, `_sanitize_answer`, session memory |
| `services/data/fetchers/news.py` | `search_serper_news(query, n, geo)` — Serper `/news` |
| `core/intelligence/rl/nse_calendar.py` | `market_session()` — IST session resolver |
| `scripts/model_bench.py` | Model-comparison harness (re-runnable; auto-scores fabrication / broken-output / latency / cost) |
| `src/frontend/prototypes/sphere.jsx` | `ChatOverlay` — SSE reader, session_id state, tool-trace |

> `services/api/user_profile.py` (per-session tier detection) is currently **dormant** — it was
> only used by the removed DAG. Retained for a future tier-adaptive verbosity feature.

---

## Analysis Pipeline — API Calls Per Ticker

(The full 9-agent **analysis** pipeline below is separate from chat. It still uses LangGraph for
parallel agent dispatch; only the chat layer changed.)

For a single ticker analysis run (9 automobile agents, macro cache warm):

| Source | Calls | Cost | When |
|---|---|---|---|
| yfinance OHLCV (pattern_analysis) | 1 | Free | Pre-graph |
| yfinance macro tickers (CL=F, INR=X, SLX…) | 3–4 | Free | risk_macro / raw_materials |
| NseIndiaApi `announcements()` | 1 | Free | Pre-fetch (once, before fan-out) |
| NseIndiaApi `boardMeetings()` | 1 | Free | Pre-fetch (once, before fan-out) |
| NseIndiaApi `actions()` | 1 | Free | Pre-fetch (once, before fan-out) |
| Serper (all agents combined, cache warm) | ~16 | Credits | During fan-out |
| Tavily (policy_regulatory only, 96% cache hit) | ~0.08 | Credits | policy_regulatory |
| LLM — 9 agents (BULK: qwen-2.5-72b) | 9 | Paid | During fan-out |
| LLM — SignalAggregator (REASONING: qwen3.7-max) | 1 | Paid | Aggregate node |
| **Total Serper (cold)** | **~19** | — | Risk_macro cache miss |
| **Total Serper (warm)** | **~16** | — | Risk_macro cache hit |

**Net reduction from NseIndiaApi pre-fetch:** 4–5 fewer Serper calls (~15%) because NseIndiaApi covers board meeting dates, dividend queries, and results filing queries that Serper previously handled.

**RL daily review (per ticker, per day):**

| Source | Calls | Purpose |
|---|---|---|
| Serper `get_news_context(ticker, days=2)` | 1 credit | Editorial market context for FeedbackAgent |
| NseIndiaApi `announcements(ticker, days=2)` | Free | Official regulatory events for FeedbackAgent |
| yfinance OHLCV (close + volume) | 1 | Actual close price + volume vs 20d avg |
| LLM — FeedbackAgent (REASONING: qwen3.7-max) | 1 | Miss classification + lesson generation |
| LLM — ThesisReviewer (REASONING, conditional) | 0–1 | Only on significant misses (~1–3×/month) |
| LLM — DossierCurator (Step 8.5, qwen temp=0.2) | 1 | Updates ticker dossier — runs every day, hit or miss |

**Weekly (per ticker):** `distill_dossier()` adds +1 LLM call/ticker/week, hooked into the
`ledger_cleanup_weekly` scheduler job. See `RL_DESIGN.md` §23.5.

**Monthly budget (5 tickers, 21 trading days, automobile sector):**

| Usage type | Formula | Calls/month |
|---|---|---|
| Pre-market analysis (warm) | 16 × 5 × 21 | 1,680 Serper |
| RL daily review (30% full rerun) | 0.3 × 16 × 5 × 21 | 504 Serper |
| Macro micro-loop (weekdays only) | 3 sectors × 2 × 6 × 22 | 792 Serper |
| **Total Serper** | | **~2,976** ⚠️ exceeds free 2,500 |
| Tavily (96% disk cache) | 2 × 0.04 × 5 × 21 | ~8 |
| NseIndiaApi | Free | No limit (NSE website) |
| RSS feeds | Free | No limit |

> Start with 3 tickers/day to stay within the 2,500 Serper free quota (~1,848/month).
