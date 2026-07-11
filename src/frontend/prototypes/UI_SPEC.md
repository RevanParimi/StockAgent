# StockAgent Beginner Prototype — UI Specification

> Optimized for fast lookup by future Claude sessions. Prefer tables over prose.

---

## 1. Architecture Overview

### Script load order (index.html lines 19–27)
```
styles.css          ← CSS variables, utility classes (.card, .mono, .eyebrow)
data.jsx            ← Populates window.* globals (no React)
icons.jsx           ← window.Icon object
sphere.jsx          ← window.Sphere, window.SphereOrb, window.ChatOverlay
auth.jsx            ← window.AuthScreen
home.jsx            ← window.Home, window.TopNav, window.RangeTabs, window.Sparkline
agents-page.jsx     ← window.AgentsPage, window.AGENT_SOURCES
portfolio.jsx       ← window.PortfolioPage
learn.jsx           ← window.LearnPage
tweaks-panel.jsx    ← window.useTweaks, window.TweaksPanel, and all TweakXxx controls
inline <script>     ← App(), NavChip(), ReactDOM.createRoot().render()
```

**Why Babel standalone:** No build step. All JSX files are tagged `type="text/babel"` — Babel parses and transpiles in-browser at page load. Suitable for prototype iteration only.

### Global state sharing
No React context. All shared data is attached to `window.*` by data.jsx and read directly inside components. Agent/task mutable state is lifted into `AgentsPage` local state and initialized from `window.AGENTS` / `window.AGENT_TASKS`.

### Live data bootstrap
`data.jsx` defines mock data first (instant first render), then fires an async IIFE that calls `GET /ui/bootstrap`. On success, it overwrites the relevant `window.*` keys and calls `window.__onApiReady()`. `App` (index.html) sets that callback in a `useEffect` and calls `forceRender(n+1)` to trigger a re-render with live data.

```
page load
  → data.jsx: mock data set synchronously
  → React renders with mock data (no flicker)
  → data.jsx: fetch('/ui/bootstrap') fires in background
  → on resolve: window.AGENTS/TICKERS/etc overwritten
  → window.__onApiReady() → App forceRender() → React re-renders with live data
```

Status flags: `window.__apiReady` (bool), `window.__apiLive` (bool — false if DB empty), `window.__apiFetchedAt` (ISO string).

### Routing model
Single `screen` string in `App` state (index.html line 40):
```
'auth' | 'home' | 'agents' | 'portfolio' | 'learn'
```
`setScreen(name)` is passed as `onNav` prop to every screen. No React Router, no URL changes.

### Theme system
- `App` calls `document.documentElement.setAttribute('data-theme', tweaks.theme)` on mount and on change (index.html lines 43–45).
- CSS variables are defined in `:root` (light) and overridden in `[data-theme="dark"]` in styles.css.
- Two theme values: `"light"` | `"dark"`.

### TweaksPanel
Fixed floating panel (bottom-right, draggable, z-index 2147483646) defined in tweaks-panel.jsx.
- Opened by host iframe via `window.postMessage({ type: '__activate_edit_mode' })`.
- Closed via `__deactivate_edit_mode` or user clicking ✕ (posts `__edit_mode_dismissed` back).
- **What it controls (index.html lines 79–105):**

| Section | Key | Values |
|---|---|---|
| Theme | `theme` | `light` / `dark` |
| Sphere style | `sphereMode` | `wireframe` / `liquid` |
| Density | `density` | `comfy` / `cozy` / `dense` |
| Quick jump | — | Buttons: setScreen to each screen |

---

## 2. Data Layer (data.jsx)

All variables are on `window`. No module exports.

**Live status:** Variables marked ✅ are overwritten by `GET /ui/bootstrap` with real backend data. Variables marked ❌ remain mock-only (no backend source exists yet). Variables marked 〰️ are static content (no API needed).

| Variable | Shape | Live? | Consumed by | Notes |
|---|---|---|---|---|
| `AGENTS` | `Array<{key, name, icon, weight, desc, enabled, beginner}>` | ✅ bootstrap | AgentsPage (initial state), MonthPane | 9 items; `weight` custom-overridden via `PUT /ui/agents/weights` |
| `TICKERS` | `Array<{sym, name, price, change, score, verdict, trend, hasData}>` | ✅ bootstrap | WatchlistPane, TrendingPane, SuggestCard | 8 NSE auto stocks; `hasData` false if no analysis run yet |
| `WATCHLIST` | `string[]` | ✅ bootstrap | WatchlistPane | Default: `['MARUTI','TATAMOTORS','M&M','BAJAJ-AUTO','EICHERMOT']` |
| `AGENT_TASKS` | `Record<agentKey, Array<{key,label,source,enabled,beginner}>>` | ❌ mock | AgentsPage (initial state), AgentDrawer | Toggle state is local React state only; not persisted |
| `MARKET_TODAY` | `{pulse, oneLiner, autoChange, drivers[], sectorChange[]}` | ✅ bootstrap | TodayPane | `drivers[i]: {kind,label,impact,tickers[]}` |
| `MARKET_MONTH` | `{pulse, oneLiner, drivers[], agentVotes[]}` | ✅ bootstrap | MonthPane | `agentVotes[i]: {n,v,k}` |
| `TRENDING` | `Array<{sym,delta,volume,why}>` | ✅ bootstrap | TrendingPane | Ranked by `abs(price change)` in bootstrap; use `GET /ui/trending` for score-delta ranking |
| `SUGGESTIONS` | `Array<{sym,reason,score,why}>` | ✅ bootstrap | SuggestCard | Tickers not in watchlist with DB scores |
| `CATEGORIES` | `Array<{key,icon,label,count,color}>` | 〰️ static | CategoryCard | 6 items; color is hex — no API needed |
| `NIFTY_AUTO_HISTORY` | `number[]` (30 items) | ✅ bootstrap | (unused directly — feeds NIFTY_AUTO_RANGES) | Real yfinance `^CNXAUTO` 30-day closes |
| `NIFTY_AUTO_RANGES` | `Record<'1W'|'1M'|'3M'|'6M'|'1Y', {points:number[], label, change}>` | ❌ mock | TodayPane → Sparkline via RangeTabs | Multi-range series not in bootstrap; only 1M via NIFTY_AUTO_HISTORY |
| `PORTFOLIO_RANGES` | Same shape as NIFTY_AUTO_RANGES | ❌ mock | PortfolioPage → Sparkline | Demo mode only — live hero chart instead reads `GET /portfolio/performance` history (`liveHist`/`liveSlice`), hidden until ≥2 equity points exist |
| `CHAT_SEEDS` | `string[]` (4 items) | ✅ bootstrap | ChatOverlay seed buttons when `msgs.length === 1` | Static strings from backend |
| `PORTFOLIO` | `{totalValue, totalCost, dayChange, dayChangePct, cash, holdings[], recentActivity[], perfHistory[], alerts[]}` | ❌ mock | PortfolioPage and all sub-cards | Demo fallback only — live page fetches `GET /portfolio` + `GET /portfolio/performance` (cash/day-change/equity curve) + `GET /portfolio/transactions` (activity) (`?demo=1` forces demo; see §4 Portfolio) |
| `PORTFOLIO.holdings` | `Array<{sym,qty,avgPrice,currentPrice,agentScore,verdict}>` | ❌ mock | HoldingsTable, AllocationCard | 5 items; demo only |
| `PORTFOLIO.recentActivity` | `Array<{kind,sym,qty?,price?,text?,t}>` | ❌ mock | ActivityCard | `kind`: `'buy'|'sell'|'agent'`; demo only |
| `PORTFOLIO.alerts` | `Array<{sym,kind,text}>` | ❌ mock | AlertsCard | `kind`: `'good'|'warn'`; demo only — live alerts come from the digest via `digestAlerts()` |
| `PORTFOLIO_LEARNINGS` | `{summary, items[], patterns[]}` | ❌ mock | LearningsSection | No feedback/RL engine connected to UI yet |
| `PORTFOLIO_LEARNINGS.items` | `Array<{id,kind,severity,sym,title,when,what,cost,costValue,lesson,agentSnapshot[],action}>` | ❌ mock | LessonCard | `kind`: `'missed-buy'|'missed-sell'|'sold-too-early'|'sizing'|'good-call'|'avoided-loss'` |
| `PORTFOLIO_LEARNINGS.patterns` | `Array<{id,label,rate,kind,detail}>` | ❌ mock | PatternChip | `kind`: `'good'|'bad'`; `rate` 0–1 |
| `LEARN_PATHS` | `Array<{key,title,sub,minutes,steps,progress,color,icon}>` | 〰️ static | PathCard, PathOverlay, LearnPage hero | 6 paths; content is curated — no DB needed |
| `GLOSSARY` | `Array<{term,short,defn}>` | 〰️ static | GlossaryCard | 6 terms |
| `LEARN_TIPS` | `Array<{title,body}>` | 〰️ static | TipsCard | 3 tips |
| `AGENT_SOURCES` | `Record<agentKey, string[]>` | ✅ via bootstrap `AGENT_SOURCES` key | AgentDrawer "Data sources" | Defined in agents-page.jsx, also returned by bootstrap |
| `Icon` | `Record<string, (props)=>JSX>` | 〰️ static | All screens | Defined in icons.jsx |

---

## 3. Icon System (icons.jsx)

All icons are inline SVG, Lucide-style, exposed on `window.Icon`.

**Base component:** `I({ children, size=18, sw=1.75, c='currentColor', ...rest })` — renders `<svg>` with stroke only, no fill.

**Usage pattern:**
```jsx
<Icon.Name size={N} c="var(--css-var)"/>
// size defaults to 18; c is stroke color, defaults to currentColor
```

**Available icons:**

| Name | Use in app |
|---|---|
| `Search` | TopNav search box, Pipeline input node |
| `Plus` | Watchlist "Add ticker", HoldingsTable "Add holding", ActivityCard buy icon |
| `Star` | Home tab bar "Watchlist", Hero "Run on MARUTI" button |
| `Trend` | Home tab "Today", DriverRow good kind, PatternChip good kind |
| `TrendDown` | DriverRow bad kind, ActivityCard sell icon, PatternChip bad kind |
| `Sparkles` | Logo, Hero CTA, SuggestCard, ChatOverlay header, AskAssistantCard |
| `Compass` | Home tab "This month", DriverRow mid kind, LessonCard action |
| `Layers` | PathCard step counter |
| `Bot` | (available, unused in current screens) |
| `Cpu` | TopNav "Agents" link, bottom NavChip "Agents" |
| `Settings` | (available, unused) |
| `Home` | TopNav "Home" link, bottom NavChip "Home" |
| `Bell` | TopNav notification button |
| `Send` | ChatOverlay submit button |
| `X` | ChatOverlay close, AgentDrawer close, PathOverlay close |
| `Check` | AgentCard task count, PathCard done badge, PathOverlay done steps |
| `Eye` | Auth password show toggle |
| `EyeOff` | Auth password hide toggle |
| `ChevronR` | DriverRow, GlossaryCard ask link, RecCard CTA, PathOverlay CTA |
| `ChevronL` | AgentsPage back button |
| `ChevronD` | (available, unused) |
| `Mic` | (available, unused) |
| `Plug` | AgentDrawer plug-in toggle section |
| `Drag` | (available, unused) |
| `Mail` | Auth email field |
| `Lock` | Auth password field |
| `User` | Auth name field (signup), bottom NavChip "Sign out" |
| `Google` | Auth Google social button (colored SVG, not stroked) |
| `Apple` | Auth Apple social button |
| `Briefcase` | TopNav "Portfolio" link, bottom NavChip "Portfolio" |
| `Book` | TopNav "Learn" link, bottom NavChip "Learn" |

---

## 4. Screen Inventory

### Auth (auth.jsx)

**Entry component:** `AuthScreen({ onAuthed })`

**Layout:**
```
<div> grid 2-col (1.05fr 1fr)
├── LEFT: brand panel (dark gradient, animated bg)
│   ├── Logo (Icon.Sparkles + "StockAgent" text)
│   ├── <Sphere size={360} mode="wireframe"/>
│   └── headline copy + 3 stat numbers
└── RIGHT: auth card (centered grid)
    ├── tab switcher (login | signup) — sliding pill animation
    ├── <form> with Field inputs
    ├── OR divider
    └── social buttons (Google, Apple)
```

**Fixed vs scrollable:** Full viewport height, no scroll needed. Left panel is fixed-height brand art.

**Sub-components:**

| Component | Props | Notes |
|---|---|---|
| `Field` | `icon, label, children` | Wraps input with left icon, label above |
| `SocialBtn` | `icon, label, onClick` | Grid-2col social buttons row |

**window.* reads:** None — auth is self-contained mock.

**Internal state:**

| State | Controls |
|---|---|
| `tab` ('login'|'signup') | Which form fields show; submit button label |
| `showPw` (bool) | Password input type text/password |
| `email`, `name`, `pw` | Controlled inputs (values unused by mock) |

---

### Home (home.jsx)

**Entry component:** `Home({ onNav, openChat })`

**Layout:**
```
<div> min-height:100vh
├── <TopNav active="home" onNav search setSearch/>  ← sticky top
└── <main> maxWidth:1280, padding:24px 32px 96px
    ├── <Hero openChat/>                             ← dark gradient hero, Sphere inside
    ├── tab bar (Today / This month / Watchlist / Trending)
    ├── active tab pane (conditionally rendered)
    ├── "Browse by category" → 6-col CategoryCard grid
    └── "Suggested for you" → 3-col SuggestCard grid
```

**Sub-components and data:**

| Component | Props | window.* reads |
|---|---|---|
| `TopNav` | `active, onNav, search, setSearch` | None (layout only) |
| `Hero` | `openChat` | `MARKET_TODAY.oneLiner` |
| `TodayPane` | `data` (MARKET_TODAY) | `NIFTY_AUTO_RANGES` |
| `MonthPane` | `data` (MARKET_MONTH) | Hardcoded agent vote list |
| `WatchlistPane` | — | `WATCHLIST`, `TICKERS` |
| `TrendingPane` | — | `TRENDING`, `TICKERS` |
| `CategoryCard` | `c` (one CATEGORIES item) | — |
| `SuggestCard` | `s` (one SUGGESTIONS item) | `TICKERS` (by sym) |

**Internal state:**

| State | Controls |
|---|---|
| `tab` ('today'|'month'|'watch'|'trend') | Which pane renders |
| `search` (string) | TopNav search input (display only, no filter logic) |
| `range` ('1W'…'1Y') inside TodayPane | Nifty Auto sparkline range |

---

### Agents (agents-page.jsx)

**Entry component:** `AgentsPage({ onNav, openChat })`

**Layout:**
```
<div> min-height:100vh
├── <TopNav active="agents" .../>
└── <main> maxWidth:1280
    ├── header bar (title + 3 Stat badges: plugged-in count, active tasks, avg latency)
    ├── <Pipeline agents={enabled}/>        ← ticker→agents fan-out→verdict visual
    ├── 3-col agent card grid (<AgentCard> × 9)
    └── [conditional] <AgentDrawer/>        ← right-side drawer, fixed, z-55
```

**Sub-components:**

| Component | Props | Notes |
|---|---|---|
| `Stat` | `label, value, max?, hint?` | Small stat badge in header |
| `Pipeline` | `agents` (enabled agents array) | Fan-out diagram; animates with `float-soft` |
| `PipelineNode` | `icon, title, sub, color, highlight?` | Input/output end of pipeline |
| `AgentCard` | `a, tasks[], onToggle, onOpen` | Clickable card → opens drawer; toggle switch |
| `AgentDrawer` | `a, tasks[], onClose, onToggle, onWeight, onToggleTask` | 520px right panel |
| `TaskRow` | `t, disabled, onToggle` | One task with toggle switch inside drawer |
| `Section` | `title, children` | Eyebrow label + children grouping inside drawer |

**window.* reads:** `AGENTS` (initial state only), `AGENT_TASKS` (initial state only), `AGENT_SOURCES` (in AgentDrawer data sources section).

**Internal state:**

| State | Controls |
|---|---|
| `agents` (copy of AGENTS) | Enable/disable, weight changes reflected live |
| `tasks` (copy of AGENT_TASKS) | Task enable/disable |
| `drawerKey` (string|null) | Which agent's drawer is open (null = closed) |
| `search` (string) | TopNav input (not used for filtering in current code) |

---

### Portfolio (portfolio.jsx)

**Entry component:** `PortfolioPage({ onNav, openChat })`

**Live-wired (as of portfolio-live-wiring + autopilot):** `usePortfolioLive()` (portfolio.jsx:34) fetches `GET /portfolio` (holdings, mark-to-market), then in parallel `GET /portfolio/digest/latest` (advisor verdicts — optional, 404 until first advisor run), `GET /portfolio/performance` (cash/day-change/equity curve — optional, absent until cash accounting is on), and `GET /portfolio/transactions?limit=500` (Autopilot audit trail — optional). Status is `'loading' | 'live' | 'demo'`. Falls back to mock `window.PORTFOLIO` on any fetch failure, or unconditionally when `?demo=1` is in the URL (skips the live fetch entirely). A later reload failure never downgrades an already-live page back to demo (`wasLiveRef`) — it just keeps the last good data.

Cash/day-change/range-chart/activity are now live-wired via `/portfolio/performance` + `/portfolio/transactions` (no longer demo-only): the hero shows a real day-change badge, Cash + Realized P&L stats, and the range chart plots `perf.history` (`total_equity` per day, sliced to the selected range) once ≥2 equity points exist. An `AUTOPILOT` pill renders in the hero eyebrow when `perf.autopilot` is true. Demo mode is unchanged (still reads `window.PORTFOLIO`/`PORTFOLIO_RANGES`/`window.PORTFOLIO.recentActivity` unconditionally).

**Layout (live):**
```
<div> min-height:100vh
├── <TopNav active="portfolio" .../>
└── <main> maxWidth:1280
    ├── hero strip (dark gradient; DEMO DATA / AUTOPILOT pill in the eyebrow;
    │   day-change badge + Cash + Realized P&L stats once /portfolio/performance
    │   has cash accounting on; Sparkline/DarkRangeTabs render once ≥2 equity points exist)
    └── grid 2fr / 1fr
        ├── LEFT column (flex column, gap:20)
        │   ├── <HoldingsTable/> (or <EmptyPortfolio/> when live with 0 holdings)
        │   ├── <LearningsSection/>  — demo only, or window.__learningsLive
        │   ├── <ActivityCard/>      — demo only (window.PORTFOLIO.recentActivity)
        │   └── <LiveActivityCard/>  — live only, when live.txns.length > 0 (/portfolio/transactions)
        └── RIGHT column (flex column, gap:20)
            ├── <AlertsCard/>        — rendered only if alerts.length > 0
            ├── <AllocationCard/>    — rendered only if holdings.length > 0
            └── <AskAssistantCard/>
{addOpen && <AddHoldingModal/>}      — overlay outside the grid
```

**Sub-components:**

| Component | Props | window.* reads |
|---|---|---|
| `AddHoldingModal` | `onClose, onAdded` | — (`GET /ui/search` autocomplete → `POST /portfolio/holdings`) |
| `EmptyPortfolio` | `onAdd` | — |
| `HoldingsTable` | `holdings, digest, isLive, onAdd, onRemoved` | — verdict/reason come from `digest`, not window.* |
| `LearningsSection` | `learnings, openChat` | `PORTFOLIO_LEARNINGS` |
| `ActivityCard` | `items` | — (demo activity, or fed by `LiveActivityCard`'s mapped `items`) |
| `LiveActivityCard` | `txns` | — wraps `ActivityCard`; maps `/portfolio/transactions` rows to activity items (BUY→buy, SELL→sell, text = verdict/source + realized P&L + note), "View all N" toggle past the first 10 |
| `AlertsCard` | `alerts` | — |
| `AllocationCard` | `holdings` | — |
| `AskAssistantCard` | `openChat` | — (renders Sphere inline) |
| `LessonCard` | `it, openChat` | — |
| `PatternChip` | `p` | — |
| `FilterTabs` | `value, onChange` | — |
| `SummaryStat` | `label, value, sub, tone` | — |
| `DarkRangeTabs` | `value, onChange, options?` | — |
| `Stat2` | `label, value, pct?` | — |

**Live data helpers (module-level functions, not window.*):**

| Function | Purpose |
|---|---|
| `digestAlerts(digest)` | Digest holdings with a `verdict`+`reason` → up to 4 rows for `AlertsCard`; symbols in `digest.escalations` sorted first with `kind:'warn'`, rest `kind:'good'` |
| `agentTake(h, digest)` | Per-row "Agent take": digest advisor verdict/reason first, else demo `h.verdict`, else `window.TICKERS` composite verdict/score fallback, else `null` (renders `—`) |
| `adaptHolding(h)` | Maps a raw `/portfolio` holding to UI shape; uses `adj_qty`/`adj_avg_price` (corp-action-adjusted) |

**window.* reads (PortfolioPage):** `PORTFOLIO`, `PORTFOLIO_RANGES`, `PORTFOLIO_LEARNINGS` — demo mode only. In live mode holdings/verdicts/cash/chart/activity come from `GET /portfolio` + `GET /portfolio/digest/latest` + `GET /portfolio/performance` + `GET /portfolio/transactions`; `window.TICKERS` is read only as the `agentTake` fallback when no digest row matches.

**Internal state:**

| State | Controls |
|---|---|
| `live.status` ('loading'\|'live'\|'demo') | Which layout renders (skeleton / live / demo) |
| `live.perf` / `live.txns` | `/portfolio/performance` response / `/portfolio/transactions` rows (live mode only) |
| `range` ('1W'…'1Y') | Range chart selector — demo mode slices `PORTFOLIO_RANGES`, live mode slices `perf.history` to a trading-day window (5/22/66/132/252) |
| `search` (string) | TopNav search input (display only) |
| `addOpen` (bool) | AddHoldingModal visibility |
| `filter` ('all'|'mistakes'|'wins') inside LearningsSection | LessonCard filter |

**Add holding:** `AddHoldingModal` debounce-searches `GET /ui/search?q=` for ticker autocomplete, then `POST /portfolio/holdings` with `{symbol, qty, buy_date, price?}` — no `sector` sent; the backend resolves it via `SectorRegistry`. `price` omitted → backend prices at the real NSE close for `buy_date`. Success calls `onAdded()` → `live.reload()`.

**Row delete:** the remove button in each `HoldingsTable` row calls `DELETE /portfolio/holdings/{symbol}` then `onRemoved()` → `live.reload()`.

---

### Learn (learn.jsx)

**Entry component:** `LearnPage({ onNav, openChat })`

**Layout:**
```
<div> min-height:100vh
├── <TopNav active="learn" .../>
└── <main> maxWidth:1280
    ├── hero (dark gradient, progress bar, Sphere)
    ├── "Continue where you left off" → 3-col PathCard grid
    ├── grid 1.3fr/1fr
    │   ├── <GlossaryCard/>
    │   └── <TipsCard/>
    ├── "Recommended next" → 2-col RecCard grid
    └── [conditional] <PathOverlay/>    ← right drawer, fixed z-55
```

**Sub-components:**

| Component | Props | window.* reads |
|---|---|---|
| `PathCard` | `p, onClick` | — |
| `GlossaryCard` | `openChat` | `GLOSSARY` |
| `TipsCard` | `tips` | — (passed `LEARN_TIPS` directly) |
| `RecCard` | `title, body, cta, kind` | — |
| `PathOverlay` | `p, onClose` | — (uses `getStepTitle` helper) |

**window.* reads (LearnPage):** `LEARN_PATHS`, `LEARN_TIPS`.

**Internal state:**

| State | Controls |
|---|---|
| `search` (string) | TopNav input (display only) |
| `activePath` (string|null) | Which PathOverlay is open |

---

## 5. Component Reference

### Shared / cross-screen

| Name | File | Props | Visual | window.* |
|---|---|---|---|---|
| `TopNav` | home.jsx:63 | `active, onNav, search, setSearch` | Sticky frosted-glass header: logo, 4 nav links, search input, bell icon, avatar initials | None |
| `NavLink` | home.jsx:108 | `children, icon, active, onClick` | Pill button with icon + label; active = `--bg-tinted` bg | None |
| `Sparkline` | home.jsx:518 | `values, height=60, color` | SVG polyline with gradient area fill | None |
| `RangeTabs` | home.jsx:536 | `value, onChange, options?` | Small segmented button group (1W/1M/3M/6M/1Y) on light bg | `NIFTY_AUTO_RANGES` keys |
| `SectionHead` | home.jsx:170 | `title, subtitle?, action?` | H2 + gray subtitle + optional right-side action | None |
| `Sphere` | sphere.jsx:70 | `size=320, mode='wireframe', paused=false` | 3D CSS sphere: wireframe (lat/lng rings + 60 dots) or liquid (glassy gradient orb) | None |
| `SphereOrb` | sphere.jsx:125 | `onOpen, mode='wireframe'` | 64×64 fixed bottom-right button wrapping small Sphere | None |
| `ChatOverlay` | sphere.jsx:137 | `open, onClose, mode='wireframe'` | 400×560 fixed bottom-right chat panel; seeds from CHAT_SEEDS on first open | `CHAT_SEEDS` |

### Auth screen

| Name | File | Props | Visual |
|---|---|---|---|
| `AuthScreen` | auth.jsx:4 | `onAuthed` | Full-screen 2-col split: dark brand left, white card right |
| `Field` | auth.jsx:170 | `icon, label, children` | Label + relative div with left-pinned icon, input as child |
| `SocialBtn` | auth.jsx:182 | `icon, label, onClick` | Outlined button with icon + label |

### Home screen

| Name | File | Props | Visual | window.* |
|---|---|---|---|---|
| `Hero` | home.jsx:119 | `openChat` | Dark gradient card (2-col): copy left, Sphere right; two CTA buttons | `MARKET_TODAY.oneLiner` |
| `TodayPane` | home.jsx:183 | `data` | 2-col: market pulse card left; Nifty sparkline + sector heatmap right | `NIFTY_AUTO_RANGES` |
| `MonthPane` | home.jsx:243 | `data` | 2-col: pulse card left; agent vote bars right | None |
| `WatchlistPane` | home.jsx:293 | — | Full-width card with table (6 cols) | `WATCHLIST`, `TICKERS` |
| `TrendingPane` | home.jsx:320 | — | 2×2 card grid | `TRENDING`, `TICKERS` |
| `DriverRow` | home.jsx:412 | `d` | 3-col row: colored icon, label+meta, chevron | None |
| `SectorRow` | home.jsx:445 | `s` | 3-col: name, centered bar with midpoint, % value | None |
| `CategoryCard` | home.jsx:466 | `c` | Card with emoji icon, label, stock count | `CATEGORIES` |
| `SuggestCard` | home.jsx:485 | `s` | Card: ticker avatar + name, reason text, AI explanation chip | `TICKERS` |
| `TickerRow` | home.jsx:355 | `t` | Table row: avatar+sym, price, change%, score+dot, verdict pill, Analyze button | None |
| `ScoreDot` | home.jsx:397 | `v` | 8px colored circle: green ≥0.75, lighter green ≥0.55, amber ≥0.40, orange ≥0.20, red else | None |
| `PulseDot` | home.jsx:402 | `kind='good'` | 10px pulsing dot with outer ring animation | None |
| `Pill` | home.jsx:510 | `children, kind='neutral'` | Small rounded chip: neutral=tinted, good=green | None |
| `DarkRangeTabs` | portfolio.jsx:91 | `value, onChange, options?` | Same as RangeTabs but inverted colors for dark hero | None |

### Agents screen

| Name | File | Props | Visual |
|---|---|---|---|
| `AgentCard` | agents-page.jsx:158 | `a, tasks[], onToggle, onOpen` | Card: status bar top (plug toggle), icon+name, beginner desc, task chip preview, weight bar |
| `AgentDrawer` | agents-page.jsx:252 | `a, tasks[], onClose, onToggle, onWeight, onToggleTask` | 520px right slide-in panel with backdrop blur overlay |
| `TaskRow` | agents-page.jsx:390 | `t, disabled, onToggle` | Toggle row: label, beginner hint, mono source, toggle switch |
| `Pipeline` | agents-page.jsx:96 | `agents` | Horizontal: Ticker node → fan-out of agent mini-cards → Verdict node |
| `Stat` | agents-page.jsx:82 | `label, value, max?, hint?` | Small labeled card with mono value |
| `Section` | agents-page.jsx:420 | `title, children` | Eyebrow + children; used inside AgentDrawer |

### Portfolio screen

| Name | File | Props | Visual |
|---|---|---|---|
| `HoldingsTable` | portfolio.jsx:126 | `holdings` | Card with 7-col table: Ticker, Qty, Avg buy, Current, Value, P/L, Agent take |
| `LearningsSection` | portfolio.jsx:317 | `learnings, openChat` | Card: header (summary stats + filter tabs), pattern strip, lesson card list |
| `LessonCard` | portfolio.jsx:458 | `it, openChat` | 2-col card: ticker avatar left, title+what+impact+agent snapshot+lesson+CTA buttons right |
| `PatternChip` | portfolio.jsx:429 | `p` | Compact card: icon, label, rate bar |
| `ActivityCard` | portfolio.jsx:199 | `items` | Card with icon-labeled activity rows (buy/sell/agent events) |
| `AlertsCard` | portfolio.jsx:234 | `alerts` | Card with left-bordered alert rows |
| `AllocationCard` | portfolio.jsx:257 | `holdings` | Card: horizontal bar chart + legend list |
| `AskAssistantCard` | portfolio.jsx:286 | `openChat` | Dark mini-card with Sphere(36), prompt text, open button |

### Learn screen

| Name | File | Props | Visual |
|---|---|---|---|
| `PathCard` | learn.jsx:97 | `p, onClick` | Card: 6px progress bar top, emoji icon, title, sub, steps/min footer |
| `GlossaryCard` | learn.jsx:139 | `openChat` | Card: 2-col grid of term+defn mini-cards |
| `TipsCard` | learn.jsx:166 | `tips` | Card: numbered tip list with gradient number badges |
| `RecCard` | learn.jsx:191 | `title, body, cta, kind` | 2-col card: copy left, large emoji icon right |
| `PathOverlay` | learn.jsx:219 | `p, onClose` | 560px right slide-in: colored header, step list, Continue button footer |

### TweaksPanel controls (tweaks-panel.jsx)

| Name | Props | Visual |
|---|---|---|
| `TweaksPanel` | `title?, children` | Floating draggable panel; hidden until `__activate_edit_mode` |
| `TweakSection` | `label, children` | Uppercase eyebrow label separator |
| `TweakRow` | `label, value?, children, inline?` | Label+value row wrapper |
| `TweakSlider` | `label, value, min, max, step, unit, onChange` | Range input with label+value |
| `TweakToggle` | `label, value, onChange` | Inline toggle switch |
| `TweakRadio` | `label?, value, options, onChange` | Segmented draggable radio (supports `{value,label}` or plain string options) |
| `TweakSelect` | `label, value, options, onChange` | Native `<select>` styled |
| `TweakText` | `label, value, placeholder, onChange` | Text input |
| `TweakNumber` | `label, value, min, max, step, unit, onChange` | Scrub-to-change number input |
| `TweakColor` | `label, value, onChange` | Color swatch `<input type="color">` |
| `TweakButton` | `label?, onClick, secondary?` | Dark (primary) or light (secondary) action button |

---

## 6. CSS / Design Tokens (styles.css)

### CSS Variables — Light theme (`:root`)

| Variable | Value | Role |
|---|---|---|
| `--bg-base` | `#f6f7fb` | Page background |
| `--bg-surface` | `#ffffff` | Card background |
| `--bg-elevated` | `#ffffff` | Elevated surface (unused, reserved) |
| `--bg-tinted` | `#eef2fb` | Subtle tint for tab bars, hover states |
| `--border` | `#e2e8f0` | Default border |
| `--border-strong` | `#cbd5e1` | Stronger border, dividers |
| `--ink-1` | `#0f172a` | Primary text |
| `--ink-2` | `#475569` | Secondary text |
| `--ink-3` | `#94a3b8` | Muted/placeholder text, labels |
| `--cyan` | `#0891b2` | Brand accent, active states, CTAs |
| `--cyan-soft` | `#e0f7fa` | Cyan tint backgrounds |
| `--blue` | `#2563eb` | (Available, minimal use) |
| `--violet` | `#7c3aed` | Secondary accent, AI-associated elements |
| `--violet-soft` | `#f3e8ff` | Violet tint backgrounds |
| `--buy-strong` | `#16a34a` | Strong positive / STRONG BUY |
| `--buy` | `#22c55e` | Positive / BUY |
| `--buy-soft` | `#dcfce7` | Green tint background |
| `--neutral` | `#d97706` | Neutral / NEUTRAL verdict |
| `--neutral-soft` | `#fef3c7` | Amber tint background |
| `--sell` | `#ea580c` | Negative / SELL |
| `--sell-strong` | `#dc2626` | Strong negative / STRONG SELL |
| `--sell-soft` | `#fee2e2` | Red tint background |
| `--shadow-sm` | see CSS | Card default shadow |
| `--shadow-md` | see CSS | Hover elevated shadow |
| `--shadow-lg` | see CSS | Overlay/modal shadow |
| `--shadow-glow` | see CSS | Cyan glow ring (unused in most components) |

### Dark theme overrides (`[data-theme="dark"]`)

| Variable | Dark value |
|---|---|
| `--bg-base` | `#0a0e1a` |
| `--bg-surface` | `#111827` |
| `--bg-elevated` | `#1a2235` |
| `--bg-tinted` | `#1a2235` |
| `--border` | `#1e293b` |
| `--border-strong` | `#334155` |
| `--ink-1` | `#f1f5f9` |
| `--ink-2` | `#cbd5e1` |
| `--ink-3` | `#64748b` |
| `--cyan-soft` | `rgba(6,182,212,.12)` |
| `--buy-soft` | `rgba(34,197,94,.12)` |
| `--neutral-soft` | `rgba(245,158,11,.12)` |
| `--sell-soft` | `rgba(239,68,68,.12)` |
| `--violet-soft` | `rgba(139,92,246,.12)` |
| (buy/sell/neutral/cyan/violet values) | **Unchanged** between themes |

### Utility classes (styles.css)

| Class | Definition |
|---|---|
| `.card` | `bg-surface`, 1px border, 16px radius, shadow-sm |
| `.mono` | JetBrains Mono, tabular-nums |
| `.eyebrow` | 700 10px JetBrains Mono, 0.18em letter-spacing, uppercase, ink-3 |

### Animations (styles.css)

| Name | Effect | Used by |
|---|---|---|
| `spin-slow` | 360° rotation | (available) |
| `float-soft` | Y ±6px ease-in-out | Pipeline agent cards |
| `pulse-soft` | opacity 0.6→1 | PulseDot outer ring, Hero LIVE dot |
| `shimmer` | bg-position sweep | (available) |
| `sa-rotate` | sphere.jsx: rotateY 360° in 24s | Sphere wireframe/liquid |
| `sa-pulse` | sphere.jsx: scale 1→1.18 | Sphere core dot |
| `auth-grad` | auth.jsx: bg-position 0→100% | Auth left panel gradient |
| `chat-in` | sphere.jsx: opacity+translateY slide up | ChatOverlay mount |
| `fade-in` | agents-page.jsx / learn.jsx: opacity | Drawer backdrop |
| `slide-in` | agents-page.jsx / learn.jsx: translateX(100%)→0 | AgentDrawer / PathOverlay |

---

## 7. Navigation & Wiring

### onNav flow
```
index.html: App()
  screen state + setScreen
  │
  ├── passes setScreen as onNav to: Home, AgentsPage, PortfolioPage, LearnPage
  │
  └── each screen passes onNav to <TopNav onNav={onNav}/>
      TopNav calls onNav('home'|'agents'|'portfolio'|'learn') on NavLink clicks
```
`AuthScreen` receives `onAuthed` (not `onNav`) — calling it sets `screen='home'`.

### Bottom nav strip (index.html lines 64–76)
Fixed bottom-left, z-index 55, visible on all non-auth screens.

| Chip | Icon | onClick |
|---|---|---|
| Home | `Icon.Home` | `goHome` → `setScreen('home')` |
| Agents | `Icon.Cpu` | `goAgents` → `setScreen('agents')` |
| Portfolio | `Icon.Briefcase` | `setScreen('portfolio')` |
| Learn | `Icon.Book` | `setScreen('learn')` |
| Sign out | `Icon.User` | `setScreen('auth')` |

Active chip: `background: var(--bg-tinted)`, color `var(--ink-1)`.

### ChatOverlay
- **Opens:** `App.openChat` → `setChat(true)` — called from: Hero "Ask the assistant" button (home.jsx:148), Hero Sphere click (home.jsx:162), `SphereOrb.onOpen` (sphere.jsx:130), `AskAssistantCard` button (portfolio.jsx:302), Learn Sphere click (learn.jsx:52), GlossaryCard "Ask anything" (learn.jsx:144).
- **Closes:** `App.closeChat` → `setChat(false)` — called from `ChatOverlay.onClose` (Icon.X button, sphere.jsx:170).
- **Renders:** Fixed bottom-right (right:24, bottom:104), 400×560, z-65. Slides up on mount.
- **Seeds:** Shows `window.CHAT_SEEDS` buttons when `msgs.length === 1` (initial bot message only).

### SphereOrb
- Renders when: `screen !== 'auth' && !chat` (index.html line 60).
- Position: `fixed, right:24, bottom:24, z-60`.
- Hidden when ChatOverlay is open (both would occupy bottom-right).
- `mode` prop comes from `tweaks.sphereMode`.

---

## 8. Quick-Change Guide

| Task | File | Location | What to change |
|---|---|---|---|
| **Add a new screen** | index.html | Lines 52–57 | Add `{screen==='myscreen' && <MyScreen onNav={setScreen} openChat={openChat}/>}` |
| | index.html | Lines 70–74 | Add `<NavChip active={screen==='myscreen'} onClick={()=>setScreen('myscreen')} icon={<Icon.X size={14}/>} label="My"/>` |
| | tweaks-panel.jsx section in index.html | Lines 99–104 | Add `<TweakButton onClick={()=>setScreen('myscreen')}>Open myscreen</TweakButton>` |
| | home.jsx | Line 81 (TopNav nav) | Add `<NavLink onClick={()=>onNav?.('myscreen')} active={active==='myscreen'} icon={<Icon.X size={15}/>}>MyScreen</NavLink>` |
| **Add a nav chip** | index.html | Lines 70–74 | Add `<NavChip>` with desired `icon`, `label`, `onClick` |
| **Add a new window.* variable** | data.jsx | End of file | `window.MY_DATA = {...};` — must come before any component that reads it |
| **Change a color token** | styles.css | Lines 3–34 (light) or 36–50 (dark) | Update `--token-name` value; dark overrides only need to list changed tokens |
| **Add a new icon** | icons.jsx | Lines 6–38 (Icon object) | Add `MyIcon: (p) => <I {...p}><path d="..."/></I>,` then access as `<Icon.MyIcon size={N}/>` |
| **Add a tab to Home** | home.jsx | Lines 21–26 (tab array) | Add `{k:'mytab', label:'My Tab', icon:<Icon.X size={15}/>}` |
| | home.jsx | Lines 38–41 (pane rendering) | Add `{tab==='mytab' && <MyPane/>}` |
| **Add an agent card** | data.jsx | Lines 3–13 (AGENTS array) | Add entry `{key, name, icon, weight, desc, enabled, beginner}` |
| | data.jsx | Lines 29–95 (AGENT_TASKS) | Add `myagentkey: [{key,label,source,enabled,beginner}, ...]` |
| | agents-page.jsx | Lines 429–439 (AGENT_SOURCES) | Add `myagentkey: ['source1','source2']` |
| **Change sphere mode default** | index.html | Line 33 (TWEAK_DEFAULTS) | Change `"sphereMode": "wireframe"` to `"liquid"` |
| **Add a portfolio holding** | data.jsx | Lines 222–228 (PORTFOLIO.holdings) | Add `{sym, qty, avgPrice, currentPrice, agentScore, verdict}` — sym must exist in TICKERS |
| **Add a learn path** | data.jsx | Lines 395–456 (LEARN_PATHS) | Add `{key, title, sub, minutes, steps, progress, color, icon}` |
| | learn.jsx | Lines 316–323 (getStepTitle) | Add `mykey: ['Step 1 title', ...]` entry |
| **Add a TweaksPanel control** | index.html | Lines 79–105 (TweaksPanel JSX) | Add `<TweakXxx ... onChange={v=>setTweak('myKey', v)}/>` inside a `<TweakSection>` |
| | index.html | Lines 32–36 (TWEAK_DEFAULTS) | Add `"myKey": defaultValue` |
| **Change TopNav links** | home.jsx | Lines 80–85 (TopNav nav) | Edit the four `<NavLink>` calls; `active` is compared against the `active` prop passed by each screen |

---

## 9. Backend API Endpoints

FastAPI server at `http://localhost:8001`. Frontend served at `/app` via `StaticFiles` (same origin — no CORS). All routes in `services/api/routes/`.

### Existing endpoints (wired to frontend)

| Method | Path | File | Returns | Replaces window.* |
|---|---|---|---|---|
| `GET` | `/ui/bootstrap` | ui_data.py | `{AGENTS, TICKERS, WATCHLIST, MARKET_TODAY, MARKET_MONTH, NIFTY_AUTO_HISTORY, TRENDING, SUGGESTIONS, CATEGORIES, CHAT_SEEDS, AGENT_SOURCES, _fetchedAt, _liveData}` | All ✅ vars above |
| `GET` | `/ui/agents` | ui_data.py | `{agents: [...]}` — 9 agent defs + merged weights | `window.AGENTS` |
| `GET` | `/ui/tickers` | ui_data.py | `{tickers, watchlist, trending, suggestions}` — live yfinance prices + DB scores | `window.TICKERS`, `window.TRENDING`, `window.SUGGESTIONS` |
| `GET` | `/ui/market/summary` | ui_data.py | `{today, month, niftyAutoHistory}` | `window.MARKET_TODAY`, `window.MARKET_MONTH`, `window.NIFTY_AUTO_HISTORY` |
| `POST` | `/ui/chat` | ui_data.py | `{reply: string}` — LLM answer with live ticker context | `ChatOverlay.send()` in sphere.jsx |
| `POST` | `/analyse` | analyse.py | Full `FinalReport` JSON (all agent scores, verdict, thesis) | Trigger on demand |
| `WS` | `/ws/stream?ticker=X` | stream.py | Events: `{type:'agent_progress', agent, score}`, `{type:'complete'}`, `{type:'error'}` | Real-time analysis UI (not yet wired) |
| `GET` | `/history/{ticker}` | history.py | `list[{id, ticker, run_at, final_score, verdict, investment_thesis}]` — newest first | Score history chart (not yet wired) |
| `GET` | `/history/{ticker}/latest` | history.py | Single most-recent record or 404 | — |
| `GET` | `/health` | server.py | `{status:'ok', timestamp}` | — |
| `GET` | `/tickers` | server.py | `{tickers: [...]}` — scheduler tickers list | — |
| `GET` | `/portfolio` | portfolio_api.py | `{user_id, risk_profile, holdings[], watchlist[]}` — holdings marked to market (`last_close`, `pnl_pct`) | `window.PORTFOLIO.holdings` (PortfolioPage live mode) |
| `GET` | `/portfolio/digest/latest` | portfolio_api.py | Latest EOD digest `{holdings[{symbol,verdict,reason,...}], escalations[]}`; 404 until first advisor run | `window.PORTFOLIO.alerts` (AlertsCard) + Agent-take column |
| `POST` | `/portfolio/holdings` | portfolio_api.py | `{holding, promotion}` — body `{symbol, qty, buy_date, price?}`; sector resolved server-side | AddHoldingModal submit |
| `DELETE` | `/portfolio/holdings/{symbol}` | portfolio_api.py | `{removed, demoted}` | HoldingsTable row delete |
| `GET` | `/portfolio/performance` | portfolio_api.py | `{cash, market_value, total_equity, capital_in, realized_pnl, unrealized_pnl, day_change_pct, total_return_pct, autopilot, history[{date, market_value, cash, total_equity, day_change_pct}]}` — sourced from `value_history.jsonl`, falls back to a live mark when history is empty | Hero cash/day-change/AUTOPILOT-pill stats + range chart (`live.perf`) |
| `GET` | `/portfolio/transactions?limit=` | portfolio_api.py | `{transactions: [{txn_id, date, symbol, side, qty, price, realized_pnl, source, verdict, note, ...}]}` — newest first | `LiveActivityCard` (`live.txns`) |
| `GET` | `/ui/search?q=` | ui_data.py | `{results: [{sym, name, type, snippet?}], query}` — ticker + thesis text search, max 8 | AddHoldingModal autocomplete |

### New endpoints (added in this session)

| Method | Path | File | Body / Params | Returns | Notes |
|---|---|---|---|---|---|
| `PUT` | `/ui/agents/weights` | ui_data.py | `{weights: {agent_key: float}}` | Updated `{agents: [...]}` | Persists overrides to `data/agent_weights.json`; validates 0.00–0.30 per key, sum 0.95–1.05 |
| `GET` | `/ui/trending` | ui_data.py | — | `{trending: [...top4], all: [...all]}` | Ranks by `abs(score_delta)` between last two runs; each item: `{sym, name, score, prevScore, delta, verdict, direction, why, runAt}` |

### Weight persistence notes
- `PUT /ui/agents/weights` saves only the changed keys to `data/agent_weights.json`.
- `GET /ui/agents` and `GET /ui/bootstrap` both merge `data/agent_weights.json` on top of `settings.AGENT_WEIGHTS` (base config).
- The frontend AgentDrawer weight slider must call `PUT /ui/agents/weights` to persist — currently it only updates local React state.

### DB schema (SQLite at `data/scores.db`)
Table `score_history`: `id, ticker, company_name, run_at, final_score, verdict, agent_scores (JSON), investment_thesis, conviction_drivers (JSON), top_risks (JSON), report_json`.

---

## 10. Future Roadmap

### Deferred — no real data source yet

| Feature | What's missing | Path to unblock |
|---|---|---|
| **Learnings / patterns** | No feedback/RL engine connected to frontend | Wire `core/intelligence/rl/` prediction store to a `GET /ui/learnings` endpoint |
| **NIFTY_AUTO_RANGES multi-timeframe** | Bootstrap only returns 30-day; `1W/3M/6M/1Y` series not exposed | Add range param to `GET /ui/market/summary?range=3M` calling yfinance with longer periods |
| **AGENT_TASKS persistence** | Toggle state is local React only | New `PUT /ui/agents/tasks` endpoint; store per-agent task flags in a JSON sidecar like weights |
| **Watchlist persistence** | Hardcoded default; no user concept | Session token + `GET/PUT /ui/watchlist` once auth is real |
| **Search backend** | `GET /ui/search` exists (used by AddHoldingModal) but TopNav search is still display-only | Wire TopNav input to `GET /ui/search?q=` results |

### Innovative ideas — backend ready, just needs UI

These features require **zero new backend endpoints** — the data already exists. Only frontend work needed.

| Idea | What to build in UI | Backend it uses | Effort |
|---|---|---|---|
| **Score History Drawer** | Tap any ticker card → right drawer with a 30-point score sparkline and verdict timeline (BUY→NEUTRAL→BUY) | `GET /history/{ticker}` — returns 30 records with `run_at + final_score + verdict` | Low — add drawer + Sparkline component |
| **"Analyze Now" + live progress** | Button on each AgentCard / TickerRow → triggers analysis, shows real-time per-agent progress bars via WebSocket | `POST /analyse` + `WS /ws/stream?ticker=X` — both fully implemented | Medium — add progress modal + WS hook |
| **API Budget badge** | Small chip in TweaksPanel or TopNav showing `Serper: 1,240 / 2,500 calls this month` | New `GET /ui/api-usage` (1 line wrapping `api_usage.get_usage()`) | Very low — 1 endpoint + 1 UI chip |

### Suggested next build order
1. **Score History Drawer** — highest signal/effort ratio; uses existing endpoint; dramatically improves ticker insight
2. **API Budget badge** — 30 min; prevents surprise quota exhaustion
3. **"Analyze Now" + streaming** — most impressive feature; needs WS handling in React (~2h)
4. ~~**Portfolio live data**~~ — shipped (portfolio-live-wiring, 2026-07-10): holdings/digest/add/delete wired to `/portfolio/*`
5. ~~**Autopilot cash/chart/activity**~~ — shipped (compass-autopilot, 2026-07-11): hero cash/day-change/AUTOPILOT pill + range chart wired to `GET /portfolio/performance`, activity feed wired to `GET /portfolio/transactions` (`LiveActivityCard`); demo mode unchanged
