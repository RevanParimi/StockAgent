# StockAgent Beginner Prototype — UI Specification

> Optimized for fast lookup by future Claude sessions. Prefer tables over prose.

---

## 1. Architecture Overview

### Script load order (index.html)
```
styles.css          ← CSS variables, utility classes (.card, .mono, .eyebrow)
marked + DOMPurify  ← CDN, exact versions with SRI (SA-001)
chat-markdown.js    ← window.saRenderChatMarkdown: chat reply → sanitized HTML (plain script, not Babel)
inline <script>     ← window.saUser / saSetUser / useSaUser / saIsOwner (the signed-in account)
                      and SA_OPERATOR_FILES / saLoadOperator / saOperatorState (operator code, owner only)
inline <script>     ← window.saDemoMode = (?demo=1); only then appends a <script> for demo-fixtures.js
demo-fixtures.js    ← window.saDemoFixtures: sample data (plain script; requested only with ?demo=1;
                      data.jsx applies it at once, or on 'sa-demo-fixtures' if it is still loading)
data.jsx            ← Empty market globals; bootstrap fetch (no React)
hooks.jsx           ← useIsMobile, useViewportWidth
icons.jsx           ← window.Icon object
sphere.jsx          ← window.Sphere, window.SphereOrb, window.ChatOverlay (Ask)
auth.jsx            ← window.AuthScreen
home.jsx            ← window.Home (Today), window.TopNav, window.RangeTabs, window.Sparkline; saTodayHoldsInbox
portfolio.jsx       ← window.PortfolioPage
brief-view.jsx, digest-view.jsx, weekly-view.jsx ← the brief panel's views
inbox.jsx           ← window.InboxPanel (the brief panel on Today)
settings.jsx        ← window.SettingsPage
inline <script>     ← App(), saShownScreen(), OperatorScreen(), ReactDOM.createRoot().render()

owner only, after /auth/me says role 'owner' (saLoadOperator → Babel.transformScriptTags):
agents-page.jsx     ← window.AgentsPage, window.AGENT_SOURCES, the AGENT_TASKS catalogue
analytics.jsx       ← window.AnalyticsPage
logs.jsx            ← window.LogsPage
rl-data.jsx         ← RL_* globals, window.rlFetch
rl-monitor.jsx      ← window.RLMonitorPage
```
`sw.js` precaches the member files only; the operator files are not in its list.

**Why Babel standalone:** No build step. All JSX files are tagged `type="text/babel"` — Babel parses and transpiles in-browser at page load. Suitable for prototype iteration only.

### Global state sharing
No React context. All shared data is attached to `window.*` by data.jsx and read directly inside components. Agent/task mutable state is lifted into `AgentsPage` local state and initialized from `window.AGENTS` / `window.AGENT_TASKS`.

The signed-in account is `window.saUser` (from `/auth/me`, published by `App` with `saSetUser` at boot, sign-in and sign-out); components read it with `useSaUser()`. The helpers sit in an inline script in index.html, not a .jsx file: navigations are network-first but the service worker serves scripts from its cache first, so the first open after a deploy runs the new index.html with the previous .jsx files, which must still render. Operator tools render only when `saIsOwner(user)` (role `owner`): the Operator menu (Agents, Analytics, Logs, RL Monitor) and the agent tuning controls. Their code is requested only then (`saLoadOperator`); until it has run, an operator screen shows "Loading the operator tools…". A member sent to an operator screen gets Today. The server routes keep their own guards. There is no Tweaks panel.

### Live data bootstrap (PR-001: real or unavailable, never a sample)
`data.jsx` sets every market global empty (`[]` / `null`), then fires an async IIFE that calls `GET /ui/bootstrap`. On success it fills the `window.*` keys; on failure it leaves them empty. Either way it sets `window.__apiState` and calls `window.__onApiReady()`, and `App` re-renders. Screens show "Loading…" while `__apiState` is `'loading'` and "… is unavailable right now" after `'failed'`; no screen falls back to sample values.

```
page load
  → data.jsx: market globals empty, __apiState = 'loading'
  → React renders loading states
  → data.jsx: fetch('/ui/bootstrap')
  → ok:   window.AGENTS/TICKERS/NIFTY50/… filled, __apiState = 'ready'
  → fail: globals stay empty,                __apiState = 'failed'
  → window.__onApiReady() → App forceRender()
```

Demo mode: `?demo=1` sets `window.saDemoMode`; demo-fixtures.js then defines `window.saDemoFixtures`, data.jsx copies it onto `window`, sets `__apiState = 'demo'` and makes no market call. `App` shows a "Sample data — the market figures and portfolio here are not live" banner. `scripts/ui_responsive_audit.mjs` runs in this mode (`--live` to skip it).

Status flags: `window.__apiState` (`'loading'|'ready'|'failed'|'demo'`), `window.__apiReady` (bool), `window.__apiLive` (bool — false if DB empty), `window.__apiFetchedAt` (ISO string; the hero shows it in IST).

### Routing model
Single `screen` string in `App` state:
```
'auth' | 'home' (Today) | 'portfolio' | 'settings' | 'inbox' (Today, on a brief-panel tab)
owner: 'agents' | 'analytics' | 'logs' | 'rl-monitor'
```
`nav(name)` is passed as `onNav` to every screen; `nav('ask')` opens the chat instead of changing screen, `nav('auth')` signs out. `saShownScreen(screen, isOwner)` decides what is drawn: any other name (Learn, or one an older cached script still offers) is Today, an operator screen is Today for a member, and `'inbox'` is Today unless the cached `home.jsx` predates the brief panel (`window.saTodayHoldsInbox` unset) and the old `InboxPage` exists. No React Router, no URL changes; notification links `#/inbox/<tab>` are read once at boot.

### Theme system
- `App` keeps `theme` in state and writes it through `saSetTheme` (the one writer of `data-theme`), which persists it in localStorage.
- CSS variables are defined in `:root` (light) and overridden in `[data-theme="dark"]` in styles.css.
- Two theme values: `"light"` | `"dark"`.

---

## 2. Data Layer (data.jsx)

All variables are on `window`. No module exports.

**Live status:** Variables marked ✅ come from an API answer and are empty until it arrives (and stay empty if it fails). Variables marked 🧪 exist only in demo mode (`?demo=1`, demo-fixtures.js). Variables marked 〰️ are static content (no API needed).

| Variable | Shape | Live? | Consumed by | Notes |
|---|---|---|---|---|
| `AGENTS` | `Array<{key, name, icon, weight, desc, enabled, beginner}>` | ✅ bootstrap | AgentsPage (initial state), the analysis drawer's progress rows | 9 items; `weight` custom-overridden via `PUT /ui/agents/weights` |
| `TICKERS` | `Array<{sym, name, price, change, score, verdict, trend, hasData}>` | ✅ bootstrap | WatchlistPane, TrendingPane, DriverDetailPanel | 8 NSE auto stocks; `hasData` false if no analysis run yet |
| `WATCHLIST` | `string[]` | ✅ bootstrap | WatchlistPane | The pane re-reads the account's own list from `GET /ui/watchlist` |
| `AGENT_TASKS` | `Record<agentKey, Array<{key,label,source,enabled,beginner}>>` | 〰️ static catalogue, in agents-page.jsx (owner only) | AgentsPage (initial state), AgentDrawer | `enabled` overlaid from `AGENT_TASK_FLAGS` by `saApplyTaskFlags`; the owner's toggles persist via `PUT /ui/agents/tasks` |
| `AGENT_TASK_FLAGS` | `Record<agentKey, Record<taskKey, bool>>` | ✅ bootstrap | AgentsPage | `{}` until bootstrap answers |
| `MARKET_TODAY` | `{pulse, oneLiner, autoChange, drivers[], sectorChange[], freshness}` | ✅ bootstrap | TodayPane, Hero | `null` until bootstrap; `drivers` only from analyses (may be empty); `sectorChange[i].pct` is `null` when that index failed. `freshness` (here and in `MARKET_MONTH`) is `{label, runAt, isStale}` for the newest shared analysis: "Updated 5h ago", then "Last analysis 2 days ago"; `isStale` past 12 h; "No data yet" with none |
| `MARKET_MONTH` | `{pulse, oneLiner, drivers[], agentVotes[], freshness}` | ✅ bootstrap | MonthPane | `agentVotes` is sent and not drawn (the vote bars were removed) |
| `NIFTY50` | `{name, value, changePct, asOf}` \| `null` | ✅ bootstrap | Hero market line | Last close, its change on the close before, that close's date |
| `TRENDING` | `Array<{sym,delta,volume,why}>` | ✅ bootstrap | TrendingPane | Ranked by `abs(price change)` in bootstrap; use `GET /ui/trending` for score-delta ranking |
| `SUGGESTIONS` | `Array<{sym,reason,score,why}>` | ✅ bootstrap | — | Sent and not drawn ("Suggested for you" was removed; BACKLOG B-25) |
| `CATEGORIES` | `Array<{key,icon,label,count,color}>` | ✅ bootstrap | — | Sent and not drawn ("Browse by category" was removed; BACKLOG B-25) |
| `NIFTY_AUTO_HISTORY` | `number[]` | ✅ bootstrap | (unused by the screens) | `^CNXAUTO` closes; `[]` when the fetch failed |
| `NIFTY50_RANGES` | `Record<'1W'…'1Y', /ui/nifty-ranges answer>` | 🧪 demo | NiftyBox (demo mode) | Live mode fetches `GET /ui/nifty-ranges?range=` per tab |
| `PORTFOLIO_RANGES` | `Record<'1W'…'1Y', {points, label, change}>` | 🧪 demo | PortfolioPage → Sparkline | Live hero chart reads `GET /portfolio/performance` history (`liveHist`/`liveSlice`), hidden until ≥2 equity points exist |
| `CHAT_SEEDS` | `string[]` (4 items) | ✅ bootstrap | ChatOverlay seed buttons when `msgs.length === 1` | Questions only, never a verdict or figure; data.jsx starts with the same list |
| `PORTFOLIO` | `{totalValue, totalCost, dayChange, dayChangePct, cash, holdings[], recentActivity[], alerts[]}` | 🧪 demo | PortfolioPage and all sub-cards | Live page fetches `GET /portfolio` + `/portfolio/performance` + `/portfolio/transactions`; when `/portfolio` fails the page says the portfolio is unavailable |
| `PORTFOLIO_LEARNINGS` | `{items[], since}` | ✅ `GET /ui/learnings` | LearningsSection ("Recent verdict changes") | Shown only when the API sent items (`__learningsLive`) or in demo mode. Fetched at load and again when `saSetToken` stores a sign-in (`saLoadLearnings` in data.jsx): the list depends on the viewer. `saClearToken` (sign-out, an expired session, a deleted account) drops it (`saForgetLearnings`), and an answer that arrives after a sign-out is discarded |
| `PORTFOLIO_LEARNINGS.items` | `Array<{id,kind,severity,sym,title,when,what,detail,agentSnapshot[]}>` | ✅ | LessonCard | Only stocks the viewer may see (shared ones plus their own; `/ui/learnings` with the session). Verdict changes first (a verdict that differs from the run before it), newest first, at most 10 (`LEARNINGS_MAX_CHANGES` mirrors the server's cap); then forecast misses, newest first, at most 5. `kind`: `'turned-bullish'|'turned-bearish'|'bullish'|'bearish'|'neutral'` for a change, `'forecast-miss'` for a miss; no money figure, rate or advice text |
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
| `Star` | Home tab bar "Watchlist" |
| `Trend` | Home tab "Today", DriverRow good kind, PatternChip good kind |
| `TrendDown` | DriverRow bad kind, ActivityCard sell icon, PatternChip bad kind |
| `Sparkles` | Logo, Hero CTA, the Ask nav entry, ChatOverlay header, AskAssistantCard |
| `Compass` | Home tab "This month", DriverRow mid kind, LessonCard action |
| `Layers` | PathCard step counter |
| `Bot` | (available, unused in current screens) |
| `Cpu` | Operator menu "Agents" |
| `Settings` | (available, unused) |
| `Home` | TopNav "Today" link |
| `Bell` | TopNav notification button |
| `Send` | ChatOverlay submit button |
| `X` | ChatOverlay close, AgentDrawer close, PathOverlay close |
| `Check` | AgentCard task count, PathCard done badge, PathOverlay done steps |
| `Eye` | Auth password show toggle |
| `EyeOff` | Auth password hide toggle |
| `ChevronR` | DriverRow, GlossaryCard ask link, PathOverlay CTA |
| `ChevronL` | AgentsPage back button |
| `ChevronD` | (available, unused) |
| `Mic` | (available, unused) |
| `Plug` | AgentDrawer plug-in toggle section |
| `Drag` | (available, unused) |
| `Mail` | Auth email field |
| `Lock` | Auth password field |
| `User` | Auth name field (signup), "Sign out" in the account and phone menus |
| `Google` | Auth Google social button (colored SVG, not stroked) |
| `Apple` | Auth Apple social button |
| `Briefcase` | TopNav "Portfolio" link |

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

### Today (home.jsx, `Home`)

**Entry component:** `Home({ onNav, openChat, inboxTab, setInboxTab })`

**Layout:**
```
<div> min-height:100vh
├── <TopNav active="home" onNav search setSearch/>  ← sticky top
└── <main> maxWidth:1280, padding:24px 32px 96px
    ├── <Hero openChat/>                             ← dark gradient hero, Sphere inside
    ├── "Your brief" → <InboxPanel tab setTab/>       ← Brief / Digest / Weekly / Alerts (maxWidth 760)
    ├── "Markets and your watchlist"
    ├── tab bar (Today's market / This month / Watchlist / Trending)
    └── active tab pane (conditionally rendered)
```
`InboxPanel` (inbox.jsx) fetches the active tab's `/delivery/brief/latest`, `/portfolio/digest/latest`, `/delivery/weekly/latest` or `/delivery/alerts?limit=20`: 404 → the empty sentence, another failure → "Couldn't load this — HTTP …" with Retry. Home draws it only when `window.InboxPanel` exists (an older cached inbox.jsx has `InboxPage` instead).

**Sub-components and data:**

| Component | Props | window.* reads |
|---|---|---|
| `TopNav` | `active, onNav, search, setSearch` | `saUser` via `useSaUser`: Today / Portfolio / Ask; the Operator menu (Agents, Analytics, Logs, RL Monitor) for the owner only; the avatar's account menu (Settings, Sign out). Phone: bottom bar Today / Portfolio / Ask; the hamburger menu adds Settings, the owner's Operator entries and Sign out |
| `Hero` | `openChat` | `saUser` (first name), `NIFTY50` ("Nifty 50 ±x.xx% on <date>", omitted when null), `MARKET_TODAY.oneLiner`, `__apiState` / `__apiFetchedAt` (badge). Greeting by the IST hour |
| `TodayPane` | `data` (MARKET_TODAY) | `MarketUnavailable` when `data` is null; `NiftyBox` fetches `GET /ui/nifty-ranges?range=` (value, change, "as of <date>", or "Unavailable right now") |
| `MonthPane` | `data` (MARKET_MONTH) | Pulse and themes only |
| `WatchlistPane` | — | `WATCHLIST`, `TICKERS`, then `GET /ui/watchlist` (the account's list + prices). Price 0 → "—"; `hasData` false → "Not analysed". Add and remove send `PUT /ui/watchlist` with `{add: [sym]}` or `{remove: [sym]}` only, then show the list the answer carries |
| `TrendingPane` | — | `GET /ui/trending`, `TRENDING` on a network error; unavailable when both are empty |
| `AnalysisResultDrawer` | `state` | The case for everyone (summary, verdict, thesis, drivers, risks); "Agent breakdown" and "Conflicts resolved" for the owner only |

**Internal state:**

| State | Controls |
|---|---|
| `tab` ('today'|'month'|'watch'|'trend') | Which pane renders |
| `search` (string) | TopNav search input (display only, no filter logic) |
| `range` ('1W'…'1Y') inside NiftyBox | Nifty 50 range (`GET /ui/nifty-ranges`) |

---

### Agents (agents-page.jsx) — Operator, owner only

**Entry component:** `AgentsPage({ onNav, openChat })`. Loaded only in the owner's browser. `LearningModeNote` under the title reads the learning mode from `GET /ui/rl/tickers` → `GET /ui/rl/weights/<first ticker>` and says the page's saved weights reach no analysis (BACKLOG B-25).

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

**window.* reads:** `AGENTS` (initial state only; when empty the page fetches `GET /ui/agents` itself), `AGENT_TASKS` + `AGENT_TASK_FLAGS` (initial state only), `AGENT_SOURCES` (in AgentDrawer data sources section), `saUser` (`canTune` = owner). Only the owner opens the page; `canTune` still guards the controls.

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

**Live-wired (as of portfolio-live-wiring + autopilot):** `usePortfolioLive()` (portfolio.jsx:34) fetches `GET /portfolio` (holdings, mark-to-market), then in parallel `GET /portfolio/digest/latest` (advisor verdicts — optional, 404 until first advisor run), `GET /portfolio/performance` (cash, capital added, the equity shares, day change, the equity curve with the Nifty line, the range figures and the closed-trade record — optional, absent until cash accounting is on), and `GET /portfolio/transactions?limit=500` (Autopilot audit trail — optional). Status is `'loading' | 'live' | 'unavailable' | 'demo'`. When `GET /portfolio` fails the page shows "Your portfolio is unavailable right now" with a Try again button, never sample data (PR-001). Only demo mode (`?demo=1`) reads `window.PORTFOLIO` (skips the live fetch entirely). A later reload failure never downgrades an already-live page back to demo (`wasLiveRef`) — it just keeps the last good data.

Cash/day-change/range-chart/activity are now live-wired via `/portfolio/performance` + `/portfolio/transactions` (no longer demo-only): the hero shows a real day-change badge, "Valued as of" (`perf.as_of`), the stats Capital added, In stocks and Cash with their shares of total equity (`in_stocks_pct`, `cash_pct`, adding to 100), Total return, Realized P&L (net of costs from `perf.realized.net_of_costs`, with "+₹X before ₹Y of costs" under it and ", partly estimated" when `estimated_costs` > 0; a performance answer without `realized` shows `realized_pnl` alone) and Tax estimate (the latest year in `perf.tax_estimate.years`: its `total`, "FY 2026-27, not taken from cash"), and "If this had been in the Nifty 50" (`VsNiftyLine` from `perf.vs_nifty`: the gap since the first deposit in rupees and points, or "unavailable"). `ValueChart` plots `perf.history` (`total_equity` per day, sliced to `perf.range_points[range]`) with the same money in the Nifty dashed (`nifty_value`, drawn only through known values; a gap is never bridged) once ≥2 equity points exist, and `RangeFigure` shows the range's money-weighted return beside the Nifty's (`perf.ranges[range]`). Without cash accounting the hero shows "Bought for" and no comparison. An `AUTOPILOT` pill renders in the hero eyebrow when `perf.autopilot` is true. Demo mode is unchanged (still reads `window.PORTFOLIO`/`PORTFOLIO_RANGES`/`window.PORTFOLIO.recentActivity` unconditionally).

**Layout (live):**
```
<div> min-height:100vh
├── <TopNav active="portfolio" .../>
└── <main> maxWidth:1280
    ├── hero strip (dark gradient; SAMPLE DATA (demo mode) / AUTOPILOT pill in the eyebrow;
    │   day-change badge, Valued as of, Capital added / In stocks / Cash (shares) /
    │   Total return / Realized P&L and <VsNiftyLine/> once /portfolio/performance has
    │   cash accounting on; <ValueChart/> (Sparkline in demo) + <RangeFigure/> +
    │   DarkRangeTabs render once ≥2 equity points exist)
    └── grid 2fr / 1fr
        ├── LEFT column (flex column, gap:20)
        │   ├── <HoldingsTable/> (or <EmptyPortfolio/> when live with 0 holdings)
        │   ├── <TradeRecordCard/>   — live with cash accounting (perf.closed_trades)
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
| `LiveActivityCard` | `txns` | — wraps `ActivityCard`; maps `/portfolio/transactions` rows to activity items (BUY→buy, SELL→sell, DEPOSIT→"Paper capital added" with the amount and its note, text = verdict/source + realized P&L + the trade's costs in whole rupees, "(estimated)" for a trade from before costs were charged + note), "View all N" toggle past the first 10 |
| `AlertsCard` | `alerts, reviewDate?` | — (live: "From the review of …" dates the prices its reasons quote) |
| `AllocationCard` | `holdings` | — (each holding's share of the holdings, not of equity) |
| `TradeRecordCard` | `stats` | — (`perf.closed_trades`: trades, win rate, average win and loss, expectancy, "before costs") |
| `ValueChart` | `values, nifty, benchmark, height?` | — (equity line, and the Nifty dashed through known values only) |
| `RangeFigure` | `fig, benchmark` | — (one range's return beside the Nifty's, or "unavailable (reason)") |
| `VsNiftyLine` | `v, benchmark` | — ("If this had been in the Nifty 50", the gap, or "unavailable") |
| `AskAssistantCard` | `openChat` | — (renders Sphere inline) |
| `LessonCard` | `it, openChat` | — |
| `PatternChip` | `p` | — |
| `FilterTabs` | `value, onChange` | — |
| `SummaryStat` | `label, value, sub, tone` | — |
| `DarkRangeTabs` | `value, onChange, options?` | — |
| `Stat2` | `label, value, pct?, share?` | — (`pct` a coloured gain or loss; `share` a plain part of total equity) |

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
| `live.status` ('loading'\|'live'\|'unavailable'\|'demo') | Which layout renders (skeleton / live / unavailable card / demo) |
| `live.perf` / `live.txns` | `/portfolio/performance` response / `/portfolio/transactions` rows (live mode only) |
| `range` ('1W'…'1Y') | Range chart selector — demo mode slices `PORTFOLIO_RANGES`, live mode slices `perf.history` to a trading-day window (5/22/66/132/252) |
| `search` (string) | TopNav search input (display only) |
| `addOpen` (bool) | AddHoldingModal visibility |

**Add holding:** `AddHoldingModal` debounce-searches `GET /ui/search?q=` for ticker autocomplete, then `POST /portfolio/holdings` with `{symbol, qty, buy_date, price?}` — no `sector` sent; the backend resolves it via `SectorRegistry`. `price` omitted → backend prices at the real NSE close for `buy_date`. Success calls `onAdded()` → `live.reload()`.

**Row delete:** the remove button in each `HoldingsTable` row calls `DELETE /portfolio/holdings/{symbol}` then `onRemoved()` → `live.reload()`.

---

## 5. Component Reference

### Shared / cross-screen

| Name | File | Props | Visual | window.* |
|---|---|---|---|---|
| `TopNav` | home.jsx | `active, onNav, search, setSearch` | Sticky frosted-glass header: logo, Today / Portfolio / Ask (+ the owner's Operator ▾), theme toggle, search input, avatar (account menu) | `saUser` |
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
| `MonthPane` | home.jsx | `data` | One card: pulse and the month's themes | None |
| `WatchlistPane` | home.jsx:293 | — | Full-width card with table (6 cols) | `WATCHLIST`, `TICKERS` |
| `TrendingPane` | home.jsx:320 | — | 2×2 card grid | `TRENDING`, `TICKERS` |
| `DriverRow` | home.jsx:412 | `d` | 3-col row: colored icon, label+meta, chevron | None |
| `SectorRow` | home.jsx:445 | `s` | 3-col: name, centered bar with midpoint, % value | None |
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
| `HoldingsTable` | portfolio.jsx:126 | `holdings` | Card with 7-col table: Ticker, Qty, Avg buy, Current, Value, P/L, Agent take; live, the average cost is dated "first bought …" and the current price "on …" (its bar's date) |
| `TradeRecordCard` | portfolio.jsx | `stats` | Card "Closed trades · before costs": trades, win rate (won/lost), average win, average loss, expectancy per trade |
| `LearningsSection` | portfolio.jsx | `learnings, openChat` | Card: "Recent verdict changes" header with the number of change cards ("3 changes in the analysed stocks"; "The 10 most recent changes …" at the server's cap; "No verdict changes since 16 Sept" from `PORTFOLIO_LEARNINGS.since` when only misses came, "No verdict changes recorded yet" without a date), one LessonCard per dated change, then "Latest forecast misses" with one LessonCard per miss (no summary figures, filters or pattern strip) |
| `LessonCard` | portfolio.jsx:458 | `it, openChat` | 2-col card: ticker avatar left, title+what+impact+agent snapshot+lesson+CTA buttons right |
| `PatternChip` | portfolio.jsx:429 | `p` | Compact card: icon, label, rate bar |
| `ActivityCard` | portfolio.jsx:199 | `items` | Card with icon-labeled activity rows (buy/sell/agent events) |
| `AlertsCard` | portfolio.jsx:234 | `alerts` | Card with left-bordered alert rows |
| `AllocationCard` | portfolio.jsx:257 | `holdings` | Card: horizontal bar chart + legend list |
| `AskAssistantCard` | portfolio.jsx:286 | `openChat` | Dark mini-card with Sphere(36), prompt text, open button |

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
| `fade-in` | agents-page.jsx: opacity | Drawer backdrop |
| `slide-in` | agents-page.jsx: translateX(100%)→0 | AgentDrawer |

---

## 7. Navigation & Wiring

### onNav flow
```
index.html: App()
  screen state + nav(name)
  │
  ├── passes nav as onNav to: Home, PortfolioPage, SettingsPage, and (owner) the operator pages
  │
  └── each screen passes onNav to <TopNav onNav={onNav}/>
      TopNav calls onNav('home'|'portfolio'|'ask') from its links, onNav('settings'|'auth')
      from the account menu, and (owner) onNav('agents'|'analytics'|'logs'|'rl-monitor')
```
`AuthScreen` receives `onAuthed` (not `onNav`) — calling it sets `screen='home'` (or the pending notification tab).

There is no floating chip strip: Sign out is in the account menu (desktop) and the hamburger menu (phone).

### ChatOverlay
- **Opens:** `App.openChat` → `setChat(true)` — called from: the Ask nav entry (`nav('ask')`), Hero "Ask the assistant" button, Hero Sphere click, `SphereOrb.onOpen`, `AskAssistantCard` button (portfolio.jsx).
- **Closes:** `App.closeChat` → `setChat(false)` — called from `ChatOverlay.onClose` (Icon.X button, sphere.jsx:170).
- **Renders:** Fixed bottom-right (right:24, bottom:104), 400×560, z-65. Slides up on mount.
- **Seeds:** Shows `window.CHAT_SEEDS` buttons when `msgs.length === 1` (initial bot message only).

### SphereOrb
- Renders when: `screen !== 'auth' && !chat` (index.html line 60).
- Position: `fixed, right:24, bottom:24, z-60`.
- Hidden when ChatOverlay is open (both would occupy bottom-right).
- `mode` is `SPHERE_MODE` ('wireframe') in index.html.

---

## 8. Quick-Change Guide

| Task | File | Location | What to change |
|---|---|---|---|
| **Add a new screen** | index.html | `App` render + `saShownScreen` | Add `{shown==='myscreen' && <MyScreen onNav={nav} openChat={openChat}/>}` and let `saShownScreen` return it |
| | home.jsx | `TopNav` `navLinks` (members) or `operatorLinks` (owner) | Add `{ screen:'myscreen', label:'My', icon:<Icon.X size={17}/> }`; an operator screen also goes in `OPERATOR_SCREENS` and its file in `SA_OPERATOR_FILES` (and never in `sw.js`) |
| **Add a new window.* variable** | data.jsx | End of file | `window.MY_DATA = {...};` — must come before any component that reads it |
| **Change a color token** | styles.css | Lines 3–34 (light) or 36–50 (dark) | Update `--token-name` value; dark overrides only need to list changed tokens |
| **Add a new icon** | icons.jsx | Lines 6–38 (Icon object) | Add `MyIcon: (p) => <I {...p}><path d="..."/></I>,` then access as `<Icon.MyIcon size={N}/>` |
| **Add a tab to Home** | home.jsx | Lines 21–26 (tab array) | Add `{k:'mytab', label:'My Tab', icon:<Icon.X size={15}/>}` |
| | home.jsx | Lines 38–41 (pane rendering) | Add `{tab==='mytab' && <MyPane/>}` |
| **Add an agent card** | data.jsx | Lines 3–13 (AGENTS array) | Add entry `{key, name, icon, weight, desc, enabled, beginner}` |
| | agents-page.jsx | AGENT_TASKS catalogue (top of file) | Add `myagentkey: [{key,label,source,enabled,beginner}, ...]` |
| | agents-page.jsx | Lines 429–439 (AGENT_SOURCES) | Add `myagentkey: ['source1','source2']` |
| **Add a portfolio holding** | data.jsx | Lines 222–228 (PORTFOLIO.holdings) | Add `{sym, qty, avgPrice, currentPrice, agentScore, verdict}` — sym must exist in TICKERS |
| **Change TopNav links** | home.jsx | `TopNav` `navLinks` / `operatorLinks` | Edit the arrays; `active` is compared against the `active` prop passed by each screen |

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
| `GET` | `/portfolio` | portfolio_api.py | `{user_id, risk_profile, holdings[], watchlist[]}` — holdings marked to market (`last_close`, `last_close_date` = the date of the bar the price came from, `pnl_pct`) | `window.PORTFOLIO.holdings` (PortfolioPage live mode) |
| `GET` | `/portfolio/digest/latest` | portfolio_api.py | Latest EOD digest `{holdings[{symbol,verdict,reason,...}], escalations[]}`; 404 until first advisor run | `window.PORTFOLIO.alerts` (AlertsCard) + Agent-take column |
| `POST` | `/portfolio/holdings` | portfolio_api.py | `{holding, promotion}` — body `{symbol, qty, buy_date, price?}`; sector resolved server-side | AddHoldingModal submit |
| `DELETE` | `/portfolio/holdings/{symbol}` | portfolio_api.py | `{removed, demoted}` | HoldingsTable row delete |
| `GET` | `/portfolio/performance` | portfolio_api.py | `{cash, market_value, total_equity, capital_in, in_stocks_pct, cash_pct, realized_pnl, realized{gross, costs, net_of_costs, estimated_costs}, costs{charged, estimated, on_open_positions, rates_as_of}, tax_estimate{years[{year, short_term, long_term, short_term_taxable, long_term_taxable, long_term_exemption_used, tax, cess, total, sales, ...}], total, rates_as_of, basis}, unrealized_pnl, day_change_pct, total_return_pct, as_of, autopilot, history[{date, market_value, cash, total_equity, capital_in, day_change_pct, recorded_at, nifty_value}], benchmark, vs_nifty, ranges, range_points, closed_trades}` — reads every value point and transaction; `history` is the last 400 points; sourced from `value_history.jsonl`, falls back to a live mark when history is empty; `vs_nifty`, `ranges` and `closed_trades` need cash accounting (core/portfolio/results.py) | Hero stats, the Nifty comparison, the range chart and figure, the closed-trade card (`live.perf`) |
| `GET` | `/portfolio/transactions?limit=` | portfolio_api.py | `{transactions: [{txn_id, date, symbol, side, qty, price, realized_pnl, costs{..., total, rates_as_of, estimated}, source, verdict, note, ...}]}` — newest first; a trade from before costs were charged has its costs estimated (`estimated: true`), a DIV has `costs: null` | `LiveActivityCard` (`live.txns`) |
| `GET` | `/ui/search?q=` | ui_data.py | `{results: [{sym, name, type, snippet?}], query}` — ticker + thesis text search, max 8 | AddHoldingModal autocomplete |

### New endpoints (added in this session)

| Method | Path | File | Body / Params | Returns | Notes |
|---|---|---|---|---|---|
| `PUT` | `/ui/agents/weights` | ui_data.py | `{weights: {agent_key: float}}` | Updated `{agents: [...]}` | Persists overrides to `data/agent_weights.json`; validates 0.00–0.30 per key, sum 0.95–1.05 |
| `GET` | `/ui/trending` | ui_data.py | — | `{trending: [...top4], all: [...all]}` | Ranks by `abs(score_delta)` between last two runs; each item: `{sym, name, score, prevScore, delta, verdict, direction, why, runAt}` |

### Weight persistence notes
- `PUT /ui/agents/weights` saves only the changed keys to `data/agent_weights.json`.
- `GET /ui/agents` and `GET /ui/bootstrap` both merge `data/agent_weights.json` on top of `settings.AGENT_WEIGHTS` (base config).
- No analysis reads `data/agent_weights.json`: the analyses use the learned weights (`adapt`) or the sector's configured table (`observe`). The Agents page says so beside the controls (BACKLOG B-25).

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
