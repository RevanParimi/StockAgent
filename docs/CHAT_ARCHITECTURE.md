# Chat Architecture — Agentic Streaming Tool Loop

**Edition:** 2026-10-11 · **Code inspected:** `dd7a158`, the code production runs

**Scope:** the assistant behind `POST /ui/chat/stream`: its runtime contract,
tools, grounding, session memory and the sanitizing boundary that renders
its replies.

The assistant is a tool loop: the model calls tools across several rounds and
then answers from what they returned. A deterministic pre-router fetches the
right data for buy, sell and momentum questions before the model starts, so
those answers do not depend on the model choosing tools well. The whole
server side lives in [ui_data.py](../services/api/routes/ui_data.py). The
[technical design](TECHNICAL_DESIGN.md) summarises the rendering boundary in
[section 10](TECHNICAL_DESIGN.md#interface-and-chat-rendering), and
[AGENTIC_DESIGN](AGENTIC_DESIGN.md) places chat among the other LLM
components. Work planned in PI-2026-09 is labelled **Planned** with its
story.

---

## 1. Request flow

```text
POST /ui/chat/stream  {"message": "...", "session_id": "<uuid> or null"}
  signed-in user required (or the owner passthrough when AUTH_REQUIRED is off)
        |
  daily quota check (members only)
        |
  emit `intent` (carries the session id, so the client keeps it)
        |
  prompt = system prompt
         + IST market session and today's macro context
         + this user's stored history for the session (last 12 messages)
         + the message
        |
  PRE-ROUTER (static)  buy / sell / momentum + a screenable sector?
     yes -> run screen_stocks + search_market_news now, inject both, emit `tool_result` x2
        |
  TOOL LOOP (fast tier, up to 4 rounds, 45-second budget)
     model asks for tools -> run them concurrently -> emit `tool_result` each -> repeat
     no tool calls -> that text is the answer
        |
  rounds or budget spent -> one final call without tools, no deadline
        |
  strip <think> blocks, scrub disclaimer labels, flatten tables
        |
  emit the answer as `token` chunks of 3 words -> store the turn -> emit `done`
```

## 2. Runtime contract

| Concern | Behaviour |
|---|---|
| Who may chat | Any signed-in user (`get_current_user`). With `AUTH_REQUIRED` off, an anonymous request acts as the owner. |
| User scope | Both routes pass the caller's user id to the tools. Session history and the one tool that reads personal data, `get_portfolio_brief`, see only the caller's records; a tool given no valid user id refuses rather than fall back to the default user. |
| Quota | Members get `CHAT_DAILY_QUOTA` questions per IST day (30 by default; the `chat:` section of config.yaml does not set it). One message is one turn, whatever the tool fan-out. The owner is exempt. When the quota store fails, the turn is allowed and logged. An exhausted quota returns the reason as an ordinary assistant bubble on the stream, and HTTP 429 on `/ui/chat`. |
| Models | The fast tier (`llm.model_fast`, `qwen/qwen3.6-flash` in the repository), then the reasoning tier (`z-ai/glm-5.2`) as the fallback. Provider-side reasoning is switched off: the reply is user-visible text, and `<think>` blocks are stripped anyway. |
| Generation | Temperature 0.4; at most 700 output tokens per call on the stream, 600 on `/ui/chat`. |
| Retries | Two attempts per model on a rate limit or 5xx (waits of 0.8 s and 1.6 s), then the fallback model: at most four upstream attempts per call. Any other error is not retried. |
| Turn budget | 45 seconds of wall clock for the tool rounds. A wait that would cross it gives up at once. The final no-tools answer always runs, so a long turn still ends grounded. |
| Tool calls | Concurrent within a round. On the stream a per-turn memo stops the same tool being run twice with the same arguments. |
| Failure replies | A rate limit that survives the retries gets "The market model is briefly rate-limited upstream. Please retry in a few seconds." Any other failure gets the canned demo reply (section 9). |
| Telemetry | Every attempt is recorded with its model, tokens, latency and success. |

## 3. Deterministic pre-router

`_detect_invest_intent` needs both an action and a sector:

| Words in the message | Action | `screen_stocks` mode |
|---|---|---|
| book profit, trim, take profit, overbought, sell, exit | sell | `profit`: names near their 1-month highs |
| momentum, leaders, strongest, breakout, outperform | momentum | `momentum`: 1-week leaders |
| invest, buy, accumulate, undervalued, oversold, cheap | buy | `value`: names near their 1-month lows |

Sell words are checked first, then momentum, then buy. The sector comes from
plain words (auto, bank, IT, solar, …) and must be one of the four native
sectors. The pre-router runs the screen and a dated news search for that
sector concurrently, and injects both as system messages: base picks only on
the screen, and cite only headlines that appear in the news, otherwise say
"no specific catalyst in today's news".

**Why.** Left to choose, the model answered "which IT stocks should I buy"
with today's gainers, and sometimes cited headlines it had not fetched. The
pre-router makes the candidate set and the evidence deterministic; the model
only explains them.

## 4. Tools

Thirteen tools, each with a schema in `_CHAT_TOOLS` and a branch in
`_dispatch_chat_tool`; a unit test fails when the two lists drift apart.

| Tool | Reads | Notes |
|---|---|---|
| `get_live_price(symbol)` | yfinance | Names resolve India-first; a price outside the open session is labelled as the last close |
| `get_historical_prices(symbol, days)` | yfinance | Recent OHLCV and trend |
| `screen_stocks(sector, mode)` | yfinance, 1-month windows | `value`, `momentum` or `profit` over the sector's tickers |
| `get_sector_snapshot(sector)` | yfinance and the score store | The sector index, live movers and stored verdicts |
| `get_stock_analysis(ticker)` | Score store | The latest stored verdict and score |
| `get_analysis_history(days)` | Score store | Verdicts over up to 30 days |
| `run_agent_analysis(ticker)` | Score store, else the research pipeline | Returns the latest stored analysis whatever its age; only with none stored does it run the pipeline, with a 45-second timeout |
| `get_rl_prediction(ticker)` | The current month's envelope | Taken from the first sector directory that has one |
| `get_rl_insights()` | Weight memory and lessons | Agent accuracy, learned weights, lessons |
| `get_ticker_dossier(ticker)` | The ticker's dossier | A 2,000-character digest (RL_DESIGN §23) |
| `get_macro_news()` | Today's macro feed file | The feed the 07:30 and market-hours jobs write (AGENTIC_DESIGN §12) |
| `search_market_news(query)` | News search, Tavily as fallback | 2–3 query variants, fused (section 5) |
| `get_portfolio_brief()` | The caller's latest morning brief, else their latest EOD digest | Opens the same store as `GET /portfolio`. A caller without a portfolio gets "no brief yet", and the read creates no folder; a request without a valid user id is refused |

`run_agent_analysis` resolves the sector through the sector registry, so an
unknown ticker runs the generic graph, and its result carries the decision
gate like any other analysis. It counts as one chat turn; it is not charged
against the separate analysis quota (`analyse.daily_quota`).

## 5. Grounding

- **Market session.** The context names the current IST session
  (`PRE_MARKET`, `PRE_OPEN`, `OPEN`, `CLOSED` or `HOLIDAY`) and the last
  trading day, so a settled price is never presented as live.
- **India-first symbols.** A bare name resolves through common aliases, then
  the sector registry, then a yfinance search that prefers `.NS` and `.BO`, so
  "reliance" is not the US ticker RS.
- **News fusion.** `search_market_news` fires 2–3 fixed variants of the query
  concurrently and merges them by reciprocal rank fusion, with a filter for
  horoscope results.
- **Prompt rules.** Prices only from `get_live_price` results; sources only
  from fetched tool results, with their dates; no invented headline, source or
  date; analyst opinion as one data point, never the conclusion; and a layout
  for a phone-width bubble: short stacked lines, no tables.
- **Scrubber.** `_sanitize_answer` removes blocks headed "Critical note",
  "Important note", "Final note", "Revision note" or "Disclaimer", and turns
  any Markdown table into one bullet per row. It formats text; it is not a
  security control (section 7).

## 6. Session memory

[chat_session_store.py](../services/data/stores/chat_session_store.py) keeps
history in `data/chat_sessions.db` (SQLite in WAL mode), shared by both API
workers and kept across deploys. Rows are keyed by session id **and** user
id, so one user cannot read another's history by reusing a session id. Each
turn reads the last 12 messages. Turns older than 7 days are swept at
startup. The client sends only `session_id`; history it sends is ignored. On
a storage failure the turn runs without history.

## 7. Streaming events and the sanitizing boundary

```text
data: {"event":"intent", "session_id":"<uuid>", "tier":"active", "query":"Which IT stocks..."}
data: {"event":"tool_result", "tool":"screen_stocks", "summary":"It Sector screen — VALUE ..."}
data: {"event":"tool_result", "tool":"search_market_news", "summary":"=== NEWS RESULTS ..."}
data: {"event":"token", "text":"**TCS** ₹2,242 ▼8.4% "}
data: {"event":"done"}
```

`tool_result` summaries are the first 600 characters of each result. The
frontend (`ChatOverlay` in [sphere.jsx](../src/frontend/prototypes/sphere.jsx))
reads the stream with `fetch` and falls back to `/ui/chat` if the stream
fails.

**Every reply is untrusted text.** The model quotes news snippets and tool
output, and a quoted `<img src=x onerror=…>` passed to the browser as HTML
would run its handler next to the stored bearer token. So `renderMd` hands
each reply to [chat-markdown.js](../src/frontend/prototypes/chat-markdown.js),
which index.html loads after marked 12.0.2 and DOMPurify 3.4.16, both pinned
with SRI hashes:

- marked shows any raw HTML in the reply as visible text;
- DOMPurify then keeps only Markdown's own tags. Links must be http(s) and
  open in a new tab with `noopener noreferrer`; images, styles, classes and
  event attributes are dropped.

**Example:** a reply quoting `<img src=x onerror=…>` shows that string as
text, while bold, lists, code fences and https links still render. If either
library fails to load, the reply is shown as escaped text. The raw parser is
taken off `window`, so an older `sphere.jsx` still cached by the service
worker (cache version v8) also falls back to text. The chat bubble is the
client's only HTML sink, and a unit test keeps it so.
`npm run test:frontend` drives the real `ChatOverlay` in Chromium with hostile
fixtures and no network.

The prompt's format rules describe Markdown output and never ask for HTML,
but they do not forbid it either: the boundary above, not the prompt, is the
control.

## 8. The non-streaming route

`POST /ui/chat` returns `{"reply", "session_id"}` and shares the tools, the
models, the retries, the budget, the quota and the session store. It differs
in four ways: it runs no pre-router, it does not strip `<think>` blocks or
scrub the answer, it allows 600 output tokens, and every failure, a rate
limit included, gets the canned demo reply.

## 9. Limits and planned work

- **The canned demo reply.** `_mock_reply` answers a failed turn with fixed
  text that can name a stock and a reason ("TATAMOTORS is being driven by EV
  order book strength…"), shown as an ordinary reply. Nothing marks it as a
  fallback.
- **Stale analyses.** `run_agent_analysis` returns the latest stored
  analysis of any age before it would run a new one.
- **Public reads and demo data.** Some intelligence read routes remain
  public, and the frontend has demo fallbacks on API failure. **Planned:**
  the public-read and demo-data policy (SA-032) and honest unavailable states
  (SA-024).

## 10. Files

| File | Role |
|---|---|
| `services/api/routes/ui_data.py` | Both chat routes, the quota, the pre-router, `_CHAT_TOOLS` and every tool, `_chat_completion`, market session, symbol resolution, news fusion, the scrubber |
| `services/data/stores/chat_session_store.py` | Session history |
| `services/data/fetchers/news.py` | News search |
| `services/background/macro_news_cache.py` | The macro feed file read by `get_macro_news` |
| `core/intelligence/rl/nse_calendar.py` | `market_session()` |
| `src/frontend/prototypes/sphere.jsx` | `ChatOverlay`: stream reader, session id, tool trace |
| `src/frontend/prototypes/chat-markdown.js` | The Markdown-to-sanitized-HTML boundary |
| `tests/frontend/chat_markdown.test.mjs` | The browser test of that boundary |
| `tests/unit/api/test_chat_dossier_tool.py` | The schema/dispatch drift guard |
| `scripts/model_bench.py` | The model-comparison harness |
