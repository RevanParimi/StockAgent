---
name: stockagent-design
description: >
  Master reference for StockAgent — a Python FastAPI backend with 9 AI agents for Indian auto
  stock analysis, and a React (Babel standalone, no build step) frontend prototype. Use this skill
  whenever working on frontend features, backend API wiring, or agent pipeline changes. Contains:
  full architecture, every API endpoint and its frontend binding, all window.* globals and their
  sources, real vs mock data map, component tree, mobile responsiveness system, and known gotchas.
  Also covers the "Bloomberg Terminal meets Apple Vision Pro" design system for UI work.
user-invocable: true
---

# StockAgent — Full System Reference

## Deployment
- **Live URL:** `https://stockagent-ai.up.railway.app/app/index.html`
  - `/index.html` → 404. The correct path is `/app/index.html`.
- **API docs:** `https://stockagent-ai.up.railway.app/docs`
- **Platform:** Railway (Docker). FastAPI + Uvicorn on port 8000.
- **Local repo:** `c:\Users\RevanParimi\OneDrive - IBM\Documents\Gen AI Projects\StockAgent-main`

---

## Architecture Overview

```
Browser (React, no build step)
  │
  ├── /app/index.html          ← entry point; loads all .jsx files via Babel standalone
  ├── data.jsx                 ← sets window.* mock globals, then fetches /ui/bootstrap to overwrite with live data
  ├── icons.jsx                ← Icon.* component library
  ├── sphere.jsx               ← 3D sphere + ChatOverlay (POST /ui/chat). Responsive: bottom sheet on mobile.
  ├── auth.jsx                 ← login screen (mock auth, no backend)
  ├── home.jsx                 ← Home, TopNav (hamburger on mobile), TodayPane, WatchlistPane,
  │                               TrendingPane, AnalysisResultDrawer, DriverDetailPanel, CategoryDrawer
  ├── agents-page.jsx          ← AgentsPage, Pipeline (hidden on mobile), AgentCard, AgentDrawer
  ├── portfolio.jsx            ← PortfolioPage (100% mock — no backend wiring yet)
  ├── learn.jsx                ← LearnPage (100% static educational content, no API calls)
  └── tweaks-panel.jsx         ← Dev-only floating panel for theme / density / sphere mode

FastAPI backend (services/)
  ├── api/routes/ui_data.py       ← all /ui/* endpoints
  ├── api/routes/analyse.py       ← POST /analyse
  ├── api/routes/stream.py        ← WS /ws/stream
  ├── api/routes/history.py       ← GET /history/{ticker}[/latest]
  ├── api/routes/scheduler_api.py ← POST /scheduler/forecast|daily-review|backfill, GET /scheduler/status
  ├── api/server.py               ← FastAPI app + lifespan (startup self-heal + BackgroundScheduler start)
  │
  ├── clients/llm_client.py    ← async OpenAI-compatible client (qwen/qwen3-235b-a22b)
  ├── clients/tavily_fetcher.py
  │
  ├── data/stores/score_store.py   ← SQLite: persists FinalReport per ticker per run
  ├── data/stores/run_logger.py
  ├── data/fetchers/             ← fundamentals, macro, news
  │
  └── scheduler/python/scheduler.py  ← BackgroundScheduler with 3 jobs:
                                         1. Daily RL review (4:30 pm IST weekdays)
                                         2. Monthly forecast (1st of month 9 am IST)
                                         3. NSE calendar update (Dec 31 11 pm IST)

Core pipeline (core/)
  ├── schemas/pipeline.py      ← FinalReport, AgentOutput, all sub-score models
  ├── pipeline/orchestrator.py ← AutomobileAgentOrchestrator + _load_learned_weights()
  ├── pipeline/signal_aggregator.py  ← SignalAggregator (LLM fusion → FinalReport)
  ├── graphs/nodes.py          ← LangGraph aggregate node (alternative path)
  ├── graphs/state.py          ← GraphState
  ├── intelligence/rl/nse_calendar.py      ← dynamic holiday loading (file → hardcoded fallback)
  ├── intelligence/rl/calendar_updater.py  ← NSE API + yfinance + fixed-holidays; writes nse_holidays.json
  └── config/prompts/          ← all system + user prompt templates
```

---

## Frontend Data Flow

### 1. Initial Render (mock data as fallback)
`data.jsx` runs synchronously before React renders. It sets every `window.*` global with
hardcoded mock values so the UI is never blank on first paint.

### 2. Bootstrap (live data hydration)
`data.jsx` contains an async IIFE that fires immediately after setting mock globals:
```js
const res = await fetch('/ui/bootstrap');  // GET /ui/bootstrap
```
On success it overwrites `window.*` globals with live data and sets:
- `window.__apiReady = true`
- `window.__apiLive = bool` (true if any analysis has run, i.e. DB is non-empty)
- `window.__apiFetchedAt = ISO timestamp`

Also applies `AGENT_TASK_FLAGS` from bootstrap on top of the default `window.AGENT_TASKS`.

Then fires `window.__onApiReady()` which triggers `forceRender` in `App` (index.html),
causing React to re-render with live data.

**Key rule:** `if (Array.isArray(d.TRENDING)) window.TRENDING = d.TRENDING` — always
overrides TRENDING even if empty (so TrendingPane can show the correct empty state).
Other globals use `if (d.X?.length)` so empty arrays don't erase mock fallbacks.

### 3. Learnings (separate fetch after bootstrap)
After bootstrap completes, a second fetch hits `/ui/learnings` and overwrites
`window.PORTFOLIO_LEARNINGS` if the response contains items.

---

## window.* Globals Map

| Global | Mock source (data.jsx) | Live source | Overwritten? |
|---|---|---|---|
| `window.AGENTS` | hardcoded 9 agent objects | `/ui/bootstrap → AGENTS` | yes |
| `window.TICKERS` | 8 tickers with fake price/score | `/ui/bootstrap → TICKERS` | yes |
| `window.WATCHLIST` | `["MARUTI","TATAMOTORS","M&M","BAJAJ-AUTO","EICHERMOT"]` | `/ui/bootstrap → WATCHLIST` | yes |
| `window.AGENT_TASKS` | hardcoded task lists per agent | bootstrap applies `AGENT_TASK_FLAGS` on top | partial |
| `window.MARKET_TODAY` | fake pulse + drivers | `/ui/bootstrap → MARKET_TODAY` | yes |
| `window.MARKET_MONTH` | fake pulse + agent votes | `/ui/bootstrap → MARKET_MONTH` | yes |
| `window.NIFTY_AUTO_HISTORY` | 30-pt procedural series | `/ui/bootstrap → NIFTY_AUTO_HISTORY` | yes (if non-empty) |
| `window.NIFTY_AUTO_RANGES` | procedural 1W/1M/3M/6M/1Y | `/ui/nifty-ranges?range=X` on tab click | per-tab fetch |
| `window.TRENDING` | 4 hardcoded tickers | `/ui/bootstrap → TRENDING` | **always** (even empty) |
| `window.SUGGESTIONS` | 3 hardcoded suggestion cards | `/ui/bootstrap → SUGGESTIONS` | yes (if non-empty) |
| `window.CATEGORIES` | 6 categories | `/ui/bootstrap → CATEGORIES` (includes `tickers[]`) | yes |
| `window.CHAT_SEEDS` | 4 seed questions | `/ui/bootstrap → CHAT_SEEDS` | yes |
| `window.PORTFOLIO` | fully hardcoded holdings/P&L | **never overwritten** | ❌ no endpoint |
| `window.PORTFOLIO_RANGES` | procedural sparklines | **never overwritten** | ❌ no endpoint |
| `window.PORTFOLIO_LEARNINGS` | detailed lesson cards | `/ui/learnings` (if items > 0) | yes |
| `window.LEARN_PATHS` | 6 learning paths with progress | **never overwritten** | ❌ no endpoint |
| `window.GLOSSARY` | 6 terms | **never overwritten** | ❌ no endpoint |
| `window.LEARN_TIPS` | 3 tips | **never overwritten** | ❌ no endpoint |
| `window.__apiReady` | false | true after bootstrap success | — |
| `window.__apiLive` | false | `bool(db_latest)` — true if any analysis run | — |
| `window.__learningsLive` | false | true if `/ui/learnings` returned real items | — |

---

## API Endpoints — Complete Map

### Analysis
| Method | Path | Frontend caller | Notes |
|---|---|---|---|
| `POST` | `/analyse` | `home.jsx` — fallback when WebSocket fails | Full 9-agent pipeline. Body: `{ticker}`. Returns `FinalReport`. |
| `WS` | `/ws/stream?ticker=X` | `home.jsx` — primary analysis path | Streams `agent_progress` events then `complete` with FinalReport. |

### History
| Method | Path | Frontend caller | Notes |
|---|---|---|---|
| `GET` | `/history/{ticker}` | `agents-page.jsx` — Recent Runs in AgentDrawer | SQLite reads. Shows "No analysis runs found yet" if empty. |
| `GET` | `/history/{ticker}/latest` | not called from UI | Available via API. |

### UI Data (`/ui/*`)
| Method | Path | Frontend caller | Returns | Notes |
|---|---|---|---|---|
| `GET` | `/ui/bootstrap` | `data.jsx` — on page load | All window.* data in one payload | Core 8 tickers fetched from yfinance. ~2-3s cold. |
| `GET` | `/ui/agents` | not called | Agent defs + weights | Redundant — data comes via bootstrap. |
| `PUT` | `/ui/agents/weights` | `agents-page.jsx` — on slider release or toggle | Updated agents | Persists to `data/agent_weights.json`. Validates 0–0.30 per agent, sum 0.95–1.05. |
| `GET` | `/ui/agents/tasks` | not called | Task flags | Redundant — flags applied by bootstrap. |
| `PUT` | `/ui/agents/tasks` | `agents-page.jsx` — fire-and-forget on task toggle | `{status, flags}` | Persists to `data/agent_tasks.json`. |
| `GET` | `/ui/watchlist` | `home.jsx WatchlistPane` — on mount + after add/remove | `{watchlist, tickers}` | Returns live yfinance prices for watchlist tickers. |
| `PUT` | `/ui/watchlist` | `home.jsx` — on add or remove | `{watchlist:[str]}` | Persists to `data/watchlist.json`. Validates against `_ALL_TICKERS`. |
| `GET` | `/ui/nifty-ranges?range=` | `home.jsx` — on range tab click (1W/3M/6M/1Y) | `{range, points, label, change}` | 1M tab uses bootstrap data. Other tabs fetch live. |
| `GET` | `/ui/trending` | not called from UI | `{trending, all}` | Computes score deltas from DB. Redundant — trending in bootstrap. |
| `GET` | `/ui/tickers` | not called | All tickers + prices | Redundant — data comes via bootstrap. |
| `GET` | `/ui/market/summary` | not called | Market pulse + drivers | Redundant — data comes via bootstrap. |
| `GET` | `/ui/search?q=` | `home.jsx` — 350ms debounce on TopNav | `{results:[{sym,name,type,snippet?}]}` | Searches 16 tickers + DB theses + yfinance fallback for unknown NSE symbols. |
| `GET` | `/ui/learnings` | `data.jsx` — after bootstrap | `{summary, items, patterns}` | RL feedback + score history → lesson cards. |
| `POST` | `/ui/chat` | `sphere.jsx` — on message send | `{reply}` | Body: `{message, history:[{role,content}]}`. History capped at last 6 turns. LLM: qwen/qwen3-235b-a22b. Falls back to `_mock_reply()`. |

### Scheduler (`/scheduler/*`)
All POST endpoints return 202 immediately and run work as background tasks.
Auth: `X-Scheduler-Key` header must match `SCHEDULER_KEY` env var (open if not set).

| Method | Path | Notes |
|---|---|---|
| `POST` | `/scheduler/forecast` | Generate monthly prediction envelopes. Optional `?ticker=` param. Takes ~2 min/ticker. Requires full 9-agent pipeline per ticker. |
| `POST` | `/scheduler/daily-review` | Run daily RL feedback loop for one date. Optional `?ticker=&date=YYYY-MM-DD`. Requires envelope to exist. |
| `POST` | `/scheduler/backfill` | Run daily reviews for all past trading days this month. One-time catch-up on fresh deployment (normally done automatically by server lifespan). |
| `GET` | `/scheduler/status` | Full per-ticker RL state: envelope exists?, feedback entries count, weight version, direction accuracy, weight drifts vs base. |

### Health / Meta
| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Railway health check. |
| `GET` | `/tickers` | Lists configured scheduler tickers. |

---

## Server Startup Sequence (lifespan)

`services/api/server.py` uses a FastAPI `lifespan` context manager that runs on every deployment:

```
1. Calendar first-run
   → If data/nse_holidays.json doesn't exist: call calendar_updater.update_calendar()
   → Ensures accurate NSE holiday data from day one

2. RL self-heal (background daemon thread — non-blocking)
   → For each SCHEDULER_TICKERS:
       a. Load PredictionStore for current cycle
       b. If no envelope exists → run generate_forecast() (~2 min/ticker)
       c. Find missing trading-day reviews → run run_daily_review() for each
   → Server accepts requests immediately; self-heal runs in background

3. BackgroundScheduler start
   → 3 jobs registered and running as daemon thread
```

This makes every fresh deployment fully self-bootstrapping. No manual curl commands needed.

---

## Ticker Universe

### Core 8 (fetched in every bootstrap, fully analysable)
```
MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO, HEROMOTOCO, EICHERMOT, TVSMOTORS, ASHOKLEY
```
**yfinance symbols:** `MARUTI.NS`, `TATAMOTORS.NS`, `M&M.NS`, `BAJAJ-AUTO.NS`,
`HEROMOTOCO.NS`, `EICHERMOT.NS`, `TVSMOTOR.NS` (**no trailing S** — fixed), `ASHOKLEY.NS`

### Extended 8 (searchable + analysable, NOT fetched in bootstrap)
```
APOLLOTYRE, MRF, CEATLTD, MOTHERSON, ESCORTS, BOSCHLTD, BALKRISIND, TIINDIA
```
These appear in search results and Category drawers. Watchlist add validates against all 16.

---

## FinalReport Schema (core/schemas/pipeline.py)
```python
class FinalReport(BaseModel):
    ticker: str
    company_name: str
    final_score: float          # 0.0–1.0
    verdict: str                # STRONG BUY | BUY | NEUTRAL | SELL | STRONG SELL
    weighted_agent_scores: dict[str, WeightedAgentScore]   # {agent_key: {raw, weight, weighted}}
    conflicts_resolved: list[str]
    conviction_drivers: list[str]
    top_risks: list[str]
    executive_summary: str      # 1-2 plain-English sentences for beginner UI (shown at top of drawer)
    investment_thesis: str      # 2-3 sentence detailed thesis
    report_date: str
    price_target: float | None
    recovery_timeline_quarters: int | None
    undervalued_by_pct: float | None
    discount_reason: str | None
    recovery_catalysts: list[str]
    agent_outputs: dict[str, Any]
```

---

## Component Tree & Responsibilities

### `index.html` (App root)
- Manages `screen` state: `auth | home | agents | portfolio | learn`
- Mounts `ChatOverlay` and `SphereOrb` globally (not per-screen)
- Hooks `window.__onApiReady` → `forceRender` so live data triggers a re-render

### `home.jsx`
**Key state in `Home`:**
- `analyzeState` — `{ticker, loading, report, error, agentProgress}` — drives `AnalysisResultDrawer`
- `selectedDriver` — a driver object from `MARKET_TODAY.drivers` — drives `DriverDetailPanel`
- `selectedCategory` — a category object from `window.CATEGORIES` — drives `CategoryDrawer`
- `tab` — `today | month | watch | trend`

**Key callbacks:**
- `onAnalyze(sym)` — sets `localStorage.sa_last_ticker`, opens WebSocket stream, falls back to POST
- `closeAnalysis()` — resets analyzeState

**Components (home.jsx exports to window):**
| Component | What it does |
|---|---|
| `TopNav` | Sticky header. Desktop: nav links + search. Mobile: hamburger (☰) → full-screen overlay with all nav links. Search: `GET /ui/search` with 350ms debounce. |
| `TodayPane` | Nifty Auto sparkline + range tabs + sector heatmap + driver cards. Props: `data, onDriverClick`. |
| `MonthPane` | Monthly pulse + agent vote bars. Props: `data, onDriverClick`. |
| `WatchlistPane` | Add/remove tickers. Fetches `GET /ui/watchlist` on mount for live prices. Desktop: table. Mobile: card list (CSS `.ticker-cards-wrap`). Falls back to `window.TICKERS` on error. |
| `TrendingPane` | Shows top movers by score delta. Shows empty-state CTA if `window.__apiLive && TRENDING.length === 0`. |
| `AnalysisResultDrawer` | Desktop: right-side panel (600px). Mobile: bottom sheet (full width, 92vh max). Loading: liquid sphere + per-agent progress bars (WebSocket). Success: executive_summary → score gauge → investment_thesis → conviction_drivers / top_risks → agent breakdown → conflicts. |
| `DriverDetailPanel` | Desktop: right-side panel (420px). Mobile: bottom sheet. Triggered by clicking a driver row. Shows affected tickers with score/verdict + Analyze buttons. No new API call. |
| `CategoryDrawer` | Desktop: right-side drawer (460px). Mobile: bottom sheet. Triggered by clicking a category card. Reads `category.tickers[]` from `window.CATEGORIES`. |
| `DriverRow` | Clickable driver card. `onClick` prop — calls parent's `onDriverClick`. |
| `CategoryCard` | `onClick` prop — calls parent `setSelectedCategory`. |
| `SuggestCard` | Analyze button calls `onAnalyze(s.sym)`. |
| `TickerRow` | In WatchlistPane table (desktop only). Analyze + Remove (×) buttons. |

### `agents-page.jsx`
**Key state in `AgentsPage`:**
- `agents` — from `window.AGENTS`, mutated locally on toggle/slider
- `tasks` — from `window.AGENT_TASKS`, mutated on task toggle
- `drawerKey` — which agent card is open
- `saveStatus` — `null | 'saving' | 'saved' | {error}`

**Pipeline component:**
- Hidden on mobile via `.pipeline-section` CSS class.
- Shows `localStorage.getItem('sa_last_ticker') || 'MARUTI'` as the ticker node.
- Agent boxes are dynamic: only `enabled` agents (weight > 0) appear.
- Agent card grid: 3 columns desktop → 2 tablet → 1 mobile (via `var(--grid-agents)`).

**Toggle flow:**
1. `toggle(key)` → sets `enabled=false, weight=0` (or restores prev weight) → calls `persistWeights()`
2. `persistWeights()` → `PUT /ui/agents/weights {weights: {key: float, ...}}`
3. Backend validates: each 0.00–0.30, sum 0.95–1.05. 422 if invalid.

**Task toggle flow:**
1. `toggleTask(agentKey, taskKey)` → local state update → fire-and-forget `PUT /ui/agents/tasks`

**AgentDrawer:** Desktop 520px right panel, mobile full-width bottom sheet via `.drawer-panel` CSS class.

### `sphere.jsx`
- `SphereOrb` — floating bottom-right button (`.sphere-orb` class, shrinks to 52px on mobile).
- `ChatOverlay` — uses `.chat-overlay` CSS class. Desktop: 400×560px fixed bottom-right. Mobile: full-width 72vh bottom sheet.
- Chat history: `msgs` state, filtered for non-loading entries, last 8 sent with each request.
- Seeds shown only when `msgs.length === 1`.
- Falls back to `mockReply()` if fetch fails.

### `portfolio.jsx`
- **Fully mock.** Uses `window.PORTFOLIO`, `window.PORTFOLIO_RANGES`, `window.PORTFOLIO_LEARNINGS`.
- Responsive: hero uses `var(--hero-cols)`, content grid uses `var(--grid-portfolio)`.
- Future: needs Groww / Zerodha API integration. **Do not add real data here yet.**

### `learn.jsx`
- **Fully static.** Uses `window.LEARN_PATHS`, `window.GLOSSARY`, `window.LEARN_TIPS`.
- Responsive: path grid uses `var(--grid-paths)` (3→2→1 col), glossary/tips use `var(--grid-2col)`.
- No API calls. Progress percentages are hardcoded.

---

## Mobile Responsiveness System

All layouts are responsive via CSS variables + media query overrides in `styles.css`.
No JavaScript resize hooks needed — pure CSS approach.

### Breakpoints
| Breakpoint | Range | Variables override |
|---|---|---|
| Desktop | ≥ 1024px | Defaults (3-col grids, 32px padding, right-side drawers) |
| Tablet | 768–1023px | 2-col agent grid, 4-col categories, reduced padding |
| Mobile | < 768px | 1-col grids, 16px padding, bottom-sheet drawers |

### CSS Variables (`:root` → overridden in media queries)
```css
--main-px           /* horizontal page padding: 32px → 16px */
--main-py           /* vertical page padding: 24px → 16px */
--hero-cols         /* hero section: 1.4fr 1fr → 1fr */
--grid-2col         /* 2-col panes (Today/Month): 1.5fr 1fr → 1fr */
--grid-agents       /* agent card grid: repeat(3,1fr) → 1fr */
--grid-categories   /* category grid: repeat(6,1fr) → repeat(3,1fr) */
--grid-suggestions  /* suggestions: repeat(3,1fr) → 1fr */
--grid-trending     /* trending: repeat(2,1fr) → 1fr */
--grid-paths        /* learn paths: repeat(3,1fr) → repeat(2,1fr) */
--grid-portfolio    /* portfolio content: 2fr 1fr → 1fr */
```

### CSS Classes
| Class | Purpose |
|---|---|
| `.hide-mobile` | Hidden at < 768px |
| `.show-mobile` | Hidden at ≥ 768px |
| `.nav-desktop` | Shown on desktop, hidden on mobile |
| `.nav-hamburger` | Hidden on desktop, shown on mobile |
| `.mobile-menu` | Full-screen nav overlay (mobile only) |
| `.drawer-panel` | Right-side drawer on desktop → bottom sheet on mobile (uses `!important` overrides) |
| `.drawer-handle` | Drag pill — hidden on desktop, visible on mobile bottom sheets |
| `.pipeline-section` | Hidden on mobile (`display:none !important`) |
| `.ticker-table-wrap` | Shown on desktop, hidden on mobile |
| `.ticker-cards-wrap` | Hidden on desktop, shown on mobile (card list for watchlist) |
| `.chat-overlay` | 400×560px bottom-right on desktop → full-width 72vh bottom sheet on mobile |
| `.sphere-orb` | 64px orb, shrinks to 52px on mobile, repositions to 80px from bottom |

### Drawer pattern
All drawers use `className="drawer-panel"` with only `width` and `zIndex` as inline overrides.
The CSS class controls all positioning. On mobile, `!important` rules override the inline `width`.
Drawers also get a `<div className="drawer-handle"/>` for the visible drag pill on mobile.

---

## Real vs Mock — Master Table

| Feature | Status | Notes |
|---|---|---|
| Market Pulse (Today/Month) | ✅ Real | From `window.MARKET_TODAY/MONTH` → bootstrap → DB + yfinance |
| Driver cards (click → panel) | ✅ Real | Panel uses `window.TICKERS` (live from bootstrap) |
| Nifty Auto sparkline (1M) | ✅ Real | yfinance `^CNXAUTO` |
| Nifty Auto range tabs (3M/6M/1Y) | ✅ Real | `GET /ui/nifty-ranges` on click |
| Sector heatmap | ✅ Real | yfinance NSE sector indices |
| Watchlist add/remove | ✅ Real | Persisted to `data/watchlist.json` |
| Watchlist prices | ✅ Real | `GET /ui/watchlist` on mount fetches live yfinance prices |
| Trending tab | ✅ Real (if analyses run) | Score deltas from DB. Shows empty-state CTA if no analyses yet. |
| Search dropdown | ✅ Real | 16 tickers + DB theses + yfinance fallback |
| Category drawer | ✅ Real | Category tickers from `_CATEGORIES.tickers[]`, prices from `window.TICKERS` |
| Full analysis (WebSocket) | ✅ Real | 9 agents, LLM, yfinance. ~1-2 min per ticker. |
| Analysis drawer | ✅ Real | executive_summary → score → thesis → drivers/risks → agent breakdown |
| Agent weight sliders | ✅ Real | Persisted to `data/agent_weights.json` |
| Agent task toggles | ✅ Real | Persisted to `data/agent_tasks.json` |
| Recent Runs (AgentDrawer) | ✅ Real | `GET /history/{ticker}` — shows "No runs" if DB empty |
| Chat (sphere) | ✅ Real | LLM with conversation history. Falls back to `mockReply()`. |
| Live Pipeline ticker | ✅ Real | Reads `localStorage.sa_last_ticker` — set on every `onAnalyze()` |
| RL learned weights in analysis | ✅ Real | Auto-loaded via `_load_learned_weights()` if WeightMemory exists |
| RL daily review automation | ✅ Real | BackgroundScheduler runs daily_review at 4:30pm IST weekdays |
| RL monthly forecast automation | ✅ Real | BackgroundScheduler runs generate_forecast on 1st of month |
| NSE calendar auto-update | ✅ Real | Runs Dec 31, writes `data/nse_holidays.json`, hot-reloads |
| Mobile responsive layout | ✅ Real | CSS variables + media queries across all screens and drawers |
| Greeting name ("Good afternoon, Aditi.") | ❌ Hardcoded | No auth/user profile endpoint. |
| Nifty Auto live index value ("22,847") | ❌ Hardcoded | Should read from bootstrap `NIFTY_AUTO_HISTORY` last value. |
| Portfolio holdings / P&L | ❌ Mock | `window.PORTFOLIO` never overwritten. Needs broker API. |
| Portfolio sparklines | ❌ Mock | `window.PORTFOLIO_RANGES` — procedural. |
| Learn page progress | ❌ Mock | All percentages hardcoded. No user progress tracking. |
| Suggestions (Suggested for you) | ⚠️ Semi-real | Real if analyses run. Mock otherwise. |

---

## Backend Static Data & Persistence Files

| Path | Purpose |
|---|---|
| `data/agent_weights.json` | User-overridden agent weights. Merged on top of `settings.AGENT_WEIGHTS`. |
| `data/agent_tasks.json` | User-toggled task enabled flags `{agent_key: {task_key: bool}}`. |
| `data/watchlist.json` | User-saved watchlist `["MARUTI", ...]`. |
| `data/nse_holidays.json` | NSE trading holidays by year `{"2025": ["2025-01-26",...], "2026":[...]}`. Written by `calendar_updater.py` every Dec 31. Loaded by `nse_calendar.py` on import. |
| SQLite (ScoreStore) | All FinalReport results. Powers history, trending, learnings, market pulse. |
| `data/predictions/automobile/{TICKER}/` | RL data: envelopes, feedback logs, WeightMemory, LearningLedger. |

---

## Categories — Ticker Mapping

```python
"ev"      → [TATAMOTORS, M&M, TVSMOTORS, BAJAJ-AUTO, HEROMOTOCO]
"mass"    → [MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO, HEROMOTOCO, TVSMOTORS, EICHERMOT, ASHOKLEY]
"premium" → [MARUTI, EICHERMOT, BAJAJ-AUTO, M&M]
"cv"      → [ASHOKLEY, TATAMOTORS, EICHERMOT]
"2w"      → [HEROMOTOCO, TVSMOTORS, BAJAJ-AUTO, EICHERMOT]
"parts"   → [BOSCHLTD, MOTHERSON, APOLLOTYRE, CEATLTD, MRF, BALKRISIND]  ← extended tickers
```

---

## Agent Pipeline

9 agents run in parallel, then the Signal Aggregator fuses them:

| Key | Name | What it scores |
|---|---|---|
| `sales_demand` | Sales & Demand | FADA/SIAM dispatches, EV Vahan, dealer inventory, exports |
| `fundamentals` | Fundamentals | Revenue/EBITDA delta, margin vs peers, FII/DII flow |
| `pattern_analysis` | Pattern Analysis | RSI/MACD/Bollinger, support/resistance, 10yr OHLCV |
| `raw_materials` | Raw Materials | Steel, aluminium, palladium, crude input cost stack |
| `sentiment` | Sentiment | News NLP, mgmt tone, Twitter/Reddit/YouTube |
| `policy_regulatory` | Policy & Regulatory | FAME/EV subsidies, BS6, PLI, state incentives |
| `competitive_intel` | Competitive Intel | EV market share, model pipeline, JV/M&A |
| `risk_macro` | Risk & Macro | INR/USD, crude, RBI repo, geopolitics, China supply chain |
| `valuation_catalyst` | Valuation & Catalyst | P/E vs history, fair value, price target |

**Weight priority chain (highest → lowest):**
1. Explicitly injected by `generate_forecast.py` / `daily_review.py`
2. RL `WeightMemory.effective_weights()` — auto-loaded by `_load_learned_weights(ticker)` in orchestrator
3. `settings.AGENT_WEIGHTS` config defaults

---

## Known Gotchas

1. **TVSMOTORS yfinance symbol** — The correct symbol is `TVSMOTOR.NS` (no trailing S).
   `TVSMOTORS.NS` returns 404 from Yahoo Finance. Fixed in `ui_data.py _ALL_TICKERS`.

2. **Bootstrap timing** — `window.*` globals are set synchronously (mock), then async bootstrap
   overwrites them. React doesn't re-render on `window.*` changes. The fix: `window.__onApiReady`
   callback triggers `forceRender` in `App`. If you add new globals hydrated from bootstrap,
   also call `forceRender` in `App`'s `useEffect`.

3. **Trending empty state** — When DB is empty, bootstrap returns `TRENDING: []`. `data.jsx`
   uses `if (Array.isArray(d.TRENDING))` so it always overwrites (even with empty). `TrendingPane`
   checks `window.__apiLive && window.TRENDING.length === 0` to show the "Run first analysis" CTA.

4. **WatchlistPane live prices** — `GET /ui/watchlist` returns `{watchlist, tickers}` with
   live yfinance prices. `WatchlistPane` fetches on mount and stores in `liveTickers` state.
   Falls back to `window.TICKERS` if fetch fails.

5. **Chat history** — Frontend sends `history: [{role, content}]` (last 8 turns filtered for
   non-loading messages). Backend caps at 6 turns to limit token usage. History lives in React
   state only — not persisted across page reloads.

6. **Search fallback** — If query matches no known ticker, `/ui/search` tries
   `yf.Ticker(query.upper()+'.NS').info`. This adds latency (~1-2s). Only triggered when
   `results.length === 0 && len(query) >= 3`.

7. **Bootstrap fetches core 8 only** — `_BOOTSTRAP_TICKERS = _ALL_TICKERS[:8]` to keep
   bootstrap fast. Extended tickers (APOLLOTYRE, MRF, etc.) are searchable and analysable
   but NOT batch-fetched on load.

8. **Portfolio is fully mock** — `window.PORTFOLIO` is never overwritten. Don't wire it until
   Groww/Zerodha broker API integration is decided.

9. **Agent weight validation** — Backend enforces: each weight 0.00–0.30, all 9 sum to 0.95–1.05.
   Toggling an agent off sets its weight to 0. Re-enabling restores `_prevWeight || 0.10`.
   If weights don't sum correctly, the PUT returns 422 and the frontend shows an error badge.

10. **No auth backend** — `auth.jsx` is a mock login screen. The "AS" avatar and "Aditi" greeting
    are hardcoded. There is no user session, JWT, or backend auth endpoint.

11. **Drawer CSS pattern** — All drawers use `className="drawer-panel"` with only `width` and
    `zIndex` as inline styles. The CSS class controls all positioning, animation, and mobile
    bottom-sheet behaviour. Never add `position`, `top`, `right`, `bottom` as inline styles to
    a drawer — they will conflict with the mobile CSS overrides.

12. **Inline styles vs CSS variables** — All layout grids and paddings use CSS variables
    (`var(--grid-agents)`, `var(--main-px)`, etc.) so they respond to media query breakpoints.
    Never hard-code pixel grid widths like `gridTemplateColumns:'repeat(3,1fr)'` in JSX —
    use the appropriate CSS variable instead.

13. **NSE calendar hot-reload** — After `calendar_updater.py` writes `data/nse_holidays.json`,
    it calls `nse_calendar.reload_holidays()` to update the module-level `_NSE_HOLIDAYS` set
    in the live process. No restart needed. The module-level set is rebuilt from file + hardcoded.

14. **RL self-heal blocks first analysis** — The startup self-heal runs `generate_forecast()`
    in a background daemon thread (10s delay). If a user clicks Analyze within those 10 seconds,
    the orchestrator will use `settings.AGENT_WEIGHTS` (no RL weights yet). After self-heal
    completes, subsequent analyses use RL weights. This is by design — server stays responsive.

---

## Design System (for UI work)

**Aesthetic:** Bloomberg Terminal meets Apple Vision Pro. Light mode default with dark mode toggle.

### Colors (CSS variables in `styles.css`)
```css
--cyan:          #0891b2   /* primary accent, CTAs, scores */
--violet:        #7c3aed   /* secondary accent, gradients */
--buy-strong:    #16a34a
--buy:           #22c55e
--buy-soft:      #dcfce7
--neutral:       #d97706
--neutral-soft:  #fef3c7
--sell:          #ea580c
--sell-strong:   #dc2626
--sell-soft:     #fee2e2
--bg-base:       #f6f7fb   /* page background */
--bg-surface:    #ffffff   /* card background */
--bg-tinted:     #eef2fb   /* subtle inset */
--border:        #e2e8f0
--border-strong: #cbd5e1
--ink-1:         #0f172a   /* primary text */
--ink-2:         #475569   /* secondary text */
--ink-3:         #94a3b8   /* tertiary / labels */
--shadow-sm / --shadow-md / --shadow-lg
```

### Typography
- **Body / UI:** Inter (400, 500, 600, 700, 800)
- **Mono / numbers:** JetBrains Mono (400, 500, 700) — class `mono`
- **Labels:** class `eyebrow` → uppercase, tracked, 10-11px

### Card anatomy
```css
.card { background: var(--bg-surface); border-radius: 16px; box-shadow: var(--shadow-sm); border: 1px solid var(--border); }
/* On mobile: border-radius reduces to 12px */
```

### Verdict color system
| Verdict | Color |
|---|---|
| STRONG BUY | `var(--buy-strong)` |
| BUY | `var(--buy)` |
| NEUTRAL | `var(--neutral)` |
| SELL | `var(--sell)` |
| STRONG SELL | `var(--sell-strong)` |

Background tint: `color-mix(in oklab, {verdictColor} 14%, transparent)`

### Key UI patterns
- **Drawers (desktop):** `className="drawer-panel"` + `style={{width:N, zIndex:N}}` + `slide-in` animation
- **Drawers (mobile):** Same class, CSS overrides to `top:auto; left:0; right:0; max-height:92vh; border-radius:20px 20px 0 0` + `slide-up` animation
- **Drag handle:** `<div className="drawer-handle"/>` — pill visible on mobile, hidden on desktop
- **Overlays:** `position:fixed; inset:0; background:rgba(15,23,42,.45); backdropFilter:blur(4-6px)` + `fade-in` animation
- **Score gauge:** conic-gradient circle with inner white disk showing score as integer (0-100)
- **Sparklines:** SVG polyline + polygon fill with gradient
- **Progress bars:** height 6-7px, border-radius 999, color based on score threshold (≥0.70 buy, ≥0.50 neutral, else sell)

---

## What's Left / Known Future Work

| Feature | Gap |
|---|---|
| Nifty Auto live price in hero | Shows hardcoded "22,847". Should read from bootstrap `NIFTY_AUTO_HISTORY` last value. |
| Greeting personalisation | "Aditi" hardcoded. Needs auth/user profile endpoint. |
| Search result → navigate | Clicking a search result closes dropdown but doesn't trigger analysis or navigate to ticker. |
| Portfolio real data | Needs Groww/Zerodha API. Entire `window.PORTFOLIO` is mock. |
| Learn progress tracking | All progress % hardcoded. Needs user activity endpoint. |
| RL seasonal threshold deltas | In WeightMemory weight_history reason string but not as structured field. |
| RL lesson scope narrowing | Design question — lessons only accumulate credibility, can't narrow scope. |

---

## Reinforcement Learning System (`core/intelligence/rl`)

### What It Does
A closed feedback loop that learns which of the 9 agents makes the most accurate predictions
and adapts their weights automatically over time. Runs monthly (forecast) and daily (feedback)
per ticker. Fully automated — no manual intervention needed after deployment.

### Directory Structure
```
core/intelligence/rl/
├── nse_calendar.py              ← Dynamic holiday loading: reads data/nse_holidays.json,
│                                   falls back to hardcoded 2025-2026 dates. reload_holidays()
│                                   hot-reloads after calendar_updater writes new data.
├── calendar_updater.py          ← Fetches NSE holidays (3-layer fallback: NSE API →
│                                   yfinance reverse-lookup → fixed Indian holidays).
│                                   run_dec31_update() is the Dec 31 scheduler entry point.
├── agents/
│   ├── feedback_agent.py        ← LLM: classifies miss type, extracts lessons
│   └── weight_adapter.py        ← Deterministic: adjusts agent weights based on hit rates
├── conviction/
│   └── tracker.py               ← Mean-reversion prior from consecutive verdict streaks
├── stores/
│   ├── prediction_store.py      ← JSON persistence for all 4 RL data files per ticker
│   └── ledger_propagator.py     ← Routes lessons across 3 tiers (stock/sector/market)
└── workflows/
    ├── daily_review.py          ← 8-step daily feedback loop
    └── generate_forecast.py     ← Month-start 30-day envelope generation
```

### 4 Persistent Files Per Ticker
| File | What it stores |
|---|---|
| `MARUTI_2026-05_prediction_envelope.json` | 30-day forecast: predicted close, verdict, agent scores, confidence per day |
| `MARUTI_2026-05_daily_feedback_log.json` | Each day's actual vs predicted, miss type, lessons generated, weight version applied |
| `MARUTI_agent_weight_memory.json` | Learned agent weights + full audit trail across all months |
| `MARUTI_learning_ledger.json` | Pattern lessons ("RBI policy day suppresses sentiment") — persists forever |

All stored under `data/predictions/automobile/{TICKER}/`.

### Automation (BackgroundScheduler — runs inside FastAPI process)

```
Job 1: rl_daily_review       — every weekday 4:30 pm IST (11:00 UTC)
  → run_daily_review(ticker, yesterday) for each SCHEDULER_TICKERS

Job 2: rl_monthly_forecast   — 1st of each month 9:00 am IST (03:30 UTC)
  → generate_forecast(ticker) for each SCHEDULER_TICKERS
  → Creates new envelope, resets daily review cycle

Job 3: rl_calendar_update    — Dec 31 11:00 pm IST (17:30 UTC)
  → calendar_updater.run_dec31_update()
  → Fetches next year's NSE holidays, writes data/nse_holidays.json
  → Calls nse_calendar.reload_holidays() — hot reload, no restart
```

### Startup Self-Heal (runs once on every server boot)
```
For each ticker in SCHEDULER_TICKERS:
  1. Check if current-month envelope exists
     → No: run generate_forecast() in background thread (~2 min/ticker)
  2. Check for missing daily-review entries this month
     → Missing: run_daily_review() for each missing trading day (backfill)
```
This ensures a fresh deployment is fully bootstrapped automatically.

### Data Flow (Closed Loop)
```
Month Start → generate_forecast.py
  Load WeightMemory → inject into orchestrator → run 9 agents
  → Save 30-day PredictionEnvelope

Daily 4:30pm IST → BackgroundScheduler → daily_review.py (8 steps):
  1. Load today's forecast row from envelope
  2. Fetch actual close via yfinance
  3. Compute: price_error_pct, direction_correct, timing_lag
  4. FeedbackAgent (LLM):
       → primary_miss_agent, miss_type, new_lessons, revised_context
  5. WeightAdapter (deterministic, no LLM):
       → Boost/penalize agents, save WeightMemory v(N+1)
  5.5 Apply regime multipliers (ephemeral — NOT persisted)
  6. Merge lessons into LearningLedger + propagate to sector/market ledgers
  6.5 Update ConvictionStreak → compute mean-reversion prior (caps at 0.30)
  7. Revise remaining forecasts with new weights + confidence_adj
  8. Append FeedbackEntry to daily_feedback_log
  9. Validate seasonal patterns → update LearningLedger confidence/validity
```

### RL Gap Status (as of 2026-05)
| Gap | Status | Fix location |
|---|---|---|
| Orchestrator ignores RL weights on UI calls | ✅ **FIXED** | `orchestrator.py:_load_learned_weights` |
| NSE calendar missing from rolling windows | ✅ **FIXED** | `nse_calendar.py` dynamic loading |
| NSE calendar requires manual yearly update | ✅ **FIXED** | `calendar_updater.py` Dec 31 job |
| RL never starts without manual bootstrap | ✅ **FIXED** | `server.py` lifespan self-heal |
| RL stops between deployments | ✅ **FIXED** | `BackgroundScheduler` embedded in FastAPI |
| P4 PromptEnhancer generated but never loaded | ✅ **FIXED** | `daily_review.py` Step 4 |
| Seasonal validation disconnected from LearningLedger | ✅ **FIXED** | `daily_review.py` Step 9 |
| Agent re-run failure → FeedbackAgent gets empty drift | ✅ **FIXED** | Falls back to envelope predicted scores |
| Regime multiplier persistence strategy undocumented | ✅ **DOCUMENTED** | `daily_review.py` Step 5.5 comment |
| FLAT_THRESHOLD_PCT hardcoded (not per-ticker) | ✅ **FIXED** | Reads `settings.RL_FLAT_THRESHOLD_PCT` |
| Month decay uses naive /30 instead of calendar months | ✅ **FIXED** | `feedback.py LearningLedger.effective_confidence` |
| Lesson scope narrowing (market→sector→stock) not possible | ⚠️ **OPEN** | Design question — lessons only accumulate credibility |
| Seasonal threshold deltas not persisted in WeightMemory | ⚠️ **OPEN** | In weight_history reason string but not structured |
| Price split detection in error calculation | ⚠️ **OPEN** | Low priority — yfinance returns split-adjusted prices |

### RL Schemas Quick Reference (`core/schemas/feedback.py`)
- `PredictionEnvelope` — 30-day forecast sheet per cycle
- `DailyForecast` — one row: predicted_close, predicted_agent_scores, confidence, revised
- `ConvictionStreak` — current_verdict, streak_days, reversion_prior (0–0.30)
- `FeedbackEntry` — one day's actual result + MissAnalysis + lessons_generated
- `WeightMemory` — current_weights, base_weights, agent_accuracy, weight_history
- `LearningLedger` — lessons[], miss_counter, confidence_decay_rate (0.02/month)
- `Lesson` — pattern, rule, confidence, occurrences, scope, still_valid
- `MissType` — `data_gap|data_stale|external_shock` (no penalty) · `timing|magnitude|model_bias|direction_flip` (penalized)
- `RegimeSnapshot` — regime_label, multipliers (ephemeral, not persisted)
