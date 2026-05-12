# Macro News Background Feed

## Why it exists

Without this, the chatbot only learns about broad macro/political events when a user
explicitly asks. If the Prime Minister gives a speech discouraging gold investment or
the RBI surprises with an emergency rate decision, every gold or banking answer between
"the event happened" and "someone asks about it" is silently incomplete.

The macro news feed runs in the background every few hours and writes a daily JSON cache.
The chat pipeline reads from this cache automatically — no user prompt needed.

**Example gap this closes:**
- 10:00 IST: Modi addresses nation, discourages gold investment for 1 year
- 10:30 IST: User asks "should I invest in gold?"
- Without feed: answer ignores Modi's statement entirely
- With feed: HIGH-severity item tagged `["gold", "policy"]` is in the cache;
  `_build_chat_context` injects it into the synthesize prompt; reviewer criterion 4
  catches it if the synthesize LLM still ignores it

---

## Architecture

```
APScheduler (inside FastAPI process)
  │
  ├── Job: macro_market_news   [9:00 / 12:00 / 15:00 IST, weekdays]
  │   └── MacroNewsFetcher.fetch_and_review("market_hours")
  │
  └── Job: macro_daily_news    [7:30 IST, weekdays]
      └── MacroNewsFetcher.fetch_and_review("daily")

MacroNewsFetcher (per run)
  ├── FetchAgent
  │   ├── Serper /news  (2 queries, India-focused, no date strings)
  │   └── NewsAPI top-headlines (daily run only, country=in category=business)
  │
  └── ReviewAgent (LLM, sync, max 1 call per iteration)
      ├── Assigns: severity (HIGH/MEDIUM/LOW), impact_tags, summary
      ├── Judges: satisfied=true/false, missing_topics=[...]
      └── If not satisfied AND iteration < 2: refines queries → repeat

MacroNewsCache
  └── data/macro_news/YYYY-MM-DD_macro_feed.json  (one file per day)

Chat pipeline reads from cache:
  ├── _build_chat_context()  →  inject HIGH items (NEWS/SECTOR/GENERAL intents)
  ├── get_macro_news tool    →  user explicitly asks for broad news
  └── _reviewer_node         →  criterion 4: check HIGH items vs answer
```

---

## Two-Agent Design

### FetchAgent

Pure I/O — no LLM. Runs the configured queries against Serper `/news` and optionally
NewsAPI, returns a list of raw article dicts.

**Critical note from live testing:** Do NOT append date strings to Serper queries.
Including `"2026-05-12"` in the query string returns zero results. Serper's recency
is controlled by the `/news` endpoint itself — it naturally returns recent news.

**Queries (no date strings):**

Market-hours run (real-time):
```python
MARKET_QUERIES = [
    "India Nifty Sensex stock market news",
    "Indian economy major development today",
]
```

Daily pre-market run (policy/structural):
```python
DAILY_QUERIES = [
    "India RBI SEBI policy announcement",
    "India government economic policy news",
]
```

**Serper key selection:** Uses `SERPER_API_KEY_2` first (the bfsi/it key), falling back
to `SERPER_API_KEY_1`. The macro feed runs during market hours (9am–3pm) while the RL
sector agents run post-market (4:30pm), so the keys don't compete on the same hours.

**Date normalisation:** Serper returns relative dates (`"5 hours ago"`, `"1 day ago"`).
These are converted to ISO `YYYY-MM-DD` by `_normalize_serper_date()` before storage.

### ReviewAgent

One LLM call per iteration (sync `OpenAI` client — safe for APScheduler thread).
Receives up to 15 article titles + snippets + today's date. Returns:

```json
{
  "satisfied": true,
  "missing_topics": [],
  "tagged_entries": [
    {
      "index": 1,
      "severity": "HIGH",
      "impact_tags": ["gold", "policy", "economy"],
      "summary": "Modi discouraged gold investment for one year."
    }
  ]
}
```

**Severity classification (LLM-assigned, not keywords):**
- `HIGH` — PM/RBI Governor/Finance Minister statement, major market event, systemic policy
- `MEDIUM` — sector or company news, minor policy
- `LOW` — routine/minor

**Impact tag vocabulary** (constrained to match `classify` node's canonical sector keys):
```
automobile, banking_bfsi, it_sector, renewable_energy, pharma, fmcg,
metals, oilgas, capgoods, chemicals, defence, insurance, realestate,
gold, crude, fuel, currency, inr, rbi, sebi, policy, budget,
economy, markets, inflation, interest_rate, fii, global
```

Using this exact vocabulary ensures the reviewer criterion 4 intersection works:
`set(article.impact_tags) ∩ set(user_question_entities)` — both sides use the same strings.

### Iteration loop (max 2)

```
Iteration 1:
  FetchAgent → raw results
  ReviewAgent → tagged + satisfied?
  If satisfied → write to cache, done
  If not satisfied → note missing_topics

Iteration 2 (if needed):
  FetchAgent → run "India {missing_topic}" queries
  ReviewAgent → tagged + satisfied?
  After iteration 2: always write, even if still not satisfied
  Log WARNING if still not satisfied (visible in /ui/logs ring buffer)
```

The loop always writes partial results. `satisfied=False` at the end of iteration 2 is
a logged warning, not an error — the data that was found is still valuable.

---

## Cache Schema

**File:** `data/macro_news/YYYY-MM-DD_macro_feed.json`

```json
{
  "date": "2026-05-12",
  "last_refresh": "2026-05-12T09:00:00Z",
  "refresh_count": 3,
  "entries": [
    {
      "id": "e0001",
      "fetched_at": "2026-05-12T09:00:00Z",
      "source": "serper_news",
      "title": "PM Modi urges citizens to avoid gold investment for a year",
      "snippet": "Addressing the nation, PM Modi encouraged use of public transport...",
      "url": "https://economictimes.indiatimes.com/...",
      "published_date": "2026-05-12",
      "severity": "HIGH",
      "impact_tags": ["gold", "fuel", "economy", "policy"],
      "summary": "Modi discouraged gold investment and encouraged public transport.",
      "query_used": "India Nifty Sensex stock market news"
    }
  ]
}
```

**Atomic writes:** Written to `.tmp` then `os.replace()` — safe against concurrent reads
from request handlers during the write.

**URL deduplication:** Same URL within the same day is silently skipped. A story fetched
at 9am and again at 12pm only appears once.

**Retention:** Files older than `MACRO_NEWS_RETAIN_DAYS` (default 90) are deleted
automatically during each `add_entries()` call. After 90 days ≈ ~90 files, each <50KB.

---

## Chat Pipeline Integration

### 1. `_build_chat_context()` — passive, always-on

HIGH-severity items from the last 24h are injected into the synthesize system prompt
automatically — no user query needed. Limited to `MACRO_NEWS_CONTEXT_MAX_ITEMS` (default 3).

**Only injected for broad intents:** `NEWS_QUERY`, `SECTOR_OVERVIEW`, `MULTI_SECTOR`, `GENERAL`.
Not injected for `SINGLE_STOCK`, `PRICE_QUERY`, `STOCK_COMPARE` — macro news is noise there.

Example injection:
```
TRENDING MACRO TODAY (HIGH severity — background feed):
• [2026-05-12] PM Modi urges citizens to avoid gold investment for a year [tags: gold, fuel, policy]
• [2026-05-12] RBI holds repo rate at 6.25% — third consecutive pause [tags: banking_bfsi, rbi]
```

### 2. `get_macro_news` tool — on-demand

The planner routes to this tool when the user asks broad questions:
- "Any big news today?"
- "What's happening in India markets?"
- "Give me a market sentiment update"

Returns the full day's feed sorted HIGH → MEDIUM → LOW with title, summary, tags, source.

**Cold cache behaviour:** If the cache is empty (server just started, first scheduled run
hasn't fired), the tool returns an explicit message: _"Macro news cache is empty for today —
background feed has not run yet. Try search_market_news for live results."_ The planner
also queues `search_market_news` as a fallback task, so the user always gets an answer.

### 3. Reviewer criterion 4 — reactive check

The reviewer node loads HIGH items from `MacroNewsCache.get_for_reviewer()` and includes
them in its user message alongside the question entities. It checks:

- Does any HIGH item's `impact_tags` overlap with the user's `entities` (sectors/assets/tickers)?
- If yes AND the answer completely ignores it AND it would materially change the answer → FLAG

The reviewer then triggers a re-synthesis with targeted feedback.

**Tag-to-entity mapping the LLM handles:**
- User entities `{sectors: ["banking_bfsi"]}` + item tag `"banking_bfsi"` → direct match
- User entities `{assets: ["gold"]}` + item tag `"gold"` → direct match
- User entities `{tickers: ["MARUTI"]}` → LLM infers `automobile` → matches item tag `automobile`
- Broad `NEWS_QUERY` with no entities → LLM checks `markets` or `economy` tags

---

## Scheduler Integration

Two APScheduler `CronTrigger` jobs registered inside `AutomobileScheduler._build_scheduler()`:

| Job ID | Schedule | IST | What it runs |
|---|---|---|---|
| `macro_market_news` | `hour="9,12,15" day_of_week="mon-fri"` | 9am / 12pm / 3pm | `fetch_and_review("market_hours")` |
| `macro_daily_news` | `hour=7 minute=30 day_of_week="mon-fri"` | 7:30am | `fetch_and_review("daily")` |

Both jobs use:
- `coalesce=True` — if a run was missed (server restart), only fire once, not catch-up
- `misfire_grace_time=1800` (market) / `3600` (daily) — acceptable delay window
- `replace_existing=True` — safe to restart without duplicate job registration

**Weekends:** `day_of_week="mon-fri"` means neither job runs on Saturday/Sunday.
Friday's HIGH-severity items remain in the cache across the weekend. Since markets are
closed, Friday data IS the latest available — the `_nse_market_context()` helper in
the chat context tells the LLM "NSE CLOSED (weekend) — Last trading day: Friday 2026-05-09"
so it presents the data correctly.

**Disable flag:** Set `MACRO_NEWS_ENABLED=false` in `.env` to skip both jobs entirely
without removing them from the scheduler code.

---

## Configuration

All settings in `src/backend/shared/config/settings/base.py`, all env-overridable:

| Setting | Default | Purpose |
|---|---|---|
| `MACRO_NEWS_ENABLED` | `true` | Set to `false` to disable both scheduler jobs |
| `MACRO_NEWS_RETAIN_DAYS` | `90` | Days before daily JSON files are deleted |
| `MACRO_NEWS_CONTEXT_MAX_ITEMS` | `3` | Max HIGH items injected into synthesize context |
| `MACRO_NEWS_REVIEWER_MAX_ITEMS` | `5` | Max HIGH items passed to reviewer criterion 4 |

---

## API Budget

| Source | Free tier | Usage per day (default) | Monthly |
|---|---|---|---|
| Serper `/news` | 2,500/month (key 2) | 2 queries × 4 runs = 8 | ~240 |
| NewsAPI top-headlines | 100/day | 1 call (daily run only) | ~22 |
| ReviewAgent LLM | — | 4 runs × max 2 iterations = ~8 calls | ~176 calls |

LLM cost estimate: 176 calls × ~800 tokens ≈ 140K tokens ≈ **< $0.05/month** at OpenRouter
pricing for Qwen3.

Serper usage for the macro feed (~240/month) fits within the existing key-2 budget alongside
its primary use by the bfsi/it sector agents (~1,490/month total allowed).

---

## File Locations

```
services/background/
├── __init__.py
├── macro_news_fetcher.py     ← FetchAgent + ReviewAgent orchestrator
└── macro_news_cache.py       ← daily JSON read/write, retention cleanup

data/macro_news/
├── .gitkeep
├── 2026-05-12_macro_feed.json   ← auto-generated, one per trading day
└── ...

src/backend/shared/config/settings/base.py   ← MACRO_NEWS_* settings
services/scheduler/python/scheduler.py       ← jobs 5 + 6 registered here
services/api/routes/ui_data.py               ← _chat_tool_get_macro_news, _get_macro_context_for_intent
services/api/chat_graph.py                   ← reviewer criterion 4, planner tool list
```

---

## Future: Scale and Data Strategy

Current approach (flat daily JSON files) is sufficient for years of operation — 730 files
over 2 years, each < 50KB, total < 35MB. Directory listing is sub-millisecond at this scale.

**When to migrate to SQLite:** When the codebase needs cross-day queries (e.g. "show HIGH
items across the last 7 days by tag") or trend analysis. A single table with an index on
`(published_date, severity, impact_tags)` handles these in one query.

**Trigger for migration:** Adding any feature that reads multiple daily files in a loop.
Until then, flat JSON + daily retention cleanup is simpler and has no write-lock concerns.
