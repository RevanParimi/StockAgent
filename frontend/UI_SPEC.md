# StockAgent Frontend — UI Specification

> **Purpose:** Reference for Claude Code sessions making UI changes.
> Read this before touching any frontend file. No need to read component code line-by-line.
>
> **Live URL:** `http://localhost:8001/app`
> **Served by:** FastAPI `StaticFiles` mount at `/app` → `frontend/` directory
> **Stack:** React 18 (UMD) + Babel Standalone (in-browser JSX) — **no build step, no npm**

---

## File Map

```
frontend/
├── index.html          ← Entry point. Loads all scripts, runs bootstrap, mounts React.
├── styles.css          ← All CSS variables (design tokens) + utility classes
├── data.jsx            ← All mock data + live API bootstrap (Layer 1 / Layer 2)
├── icons.jsx           ← Icon library (window.Icon.*) + AgentIcon component
├── sphere.jsx          ← 3D sphere component + chat overlay with real API
├── auth.jsx            ← Login / sign-up screen (AuthScreen)
├── home.jsx            ← Home page + shared components (TopNav, Sparkline, SectionHead, RangeTabs)
├── agents-page.jsx     ← Agents page (AgentsPage, Pipeline, AgentCard, AgentDrawer)
├── portfolio.jsx       ← Portfolio page (PortfolioPage, HoldingsTable, LearningsSection)
├── learn.jsx           ← Learn page (LearnPage, PathCard, GlossaryCard, PathOverlay)
├── tweaks-panel.jsx    ← Dev panel (theme/sphere/density toggles, quick nav)
└── icons/              ← SVG agent icons (falls back to emoji if missing)
    ├── sales_demand.svg, fundamentals.svg, pattern_analysis.svg
    ├── raw_materials.svg, sentiment.svg, policy_regulatory.svg
    ├── competitive_intel.svg, risk_macro.svg, valuation_catalyst.svg
```

---

## How Scripts Load (index.html)

```
data.jsx      → sets window.AGENTS, window.TICKERS, window.PORTFOLIO, etc. (mock)
icons.jsx     → sets window.Icon = { Search, Plus, Briefcase, Book, ... }
sphere.jsx    → sets window.Sphere, window.SphereOrb, window.ChatOverlay
auth.jsx      → sets window.AuthScreen
home.jsx      → sets window.Home, window.TopNav, window.SectionHead, window.Sparkline, window.RangeTabs
agents-page.jsx → sets window.AgentsPage
portfolio.jsx → sets window.PortfolioPage
learn.jsx     → sets window.LearnPage
tweaks-panel.jsx → sets window.TweaksPanel, useTweaks

Then inline script in index.html:
  1. await window.__bootstrap()   → fetch /ui/bootstrap, overlay mocks with live data
  2. ReactDOM.createRoot().render(<App/>)
  3. Fade out loading spinner
```

---

## Pages & Routing

Routing is a single `screen` state string in the inline `App` component in `index.html`.
No React Router. Navigation calls `onNav(screenName)` or `setScreen(screenName)`.

| Screen name | Component | File |
|---|---|---|
| `'auth'` | `<AuthScreen>` | `auth.jsx` |
| `'home'` | `<Home>` | `home.jsx` |
| `'agents'` | `<AgentsPage>` | `agents-page.jsx` |
| `'portfolio'` | `<PortfolioPage>` | `portfolio.jsx` |
| `'learn'` | `<LearnPage>` | `learn.jsx` |

**Adding a new page:** Create `newpage.jsx` → add `<script type="text/babel" src="newpage.jsx">` to `index.html` → add a route in the `App` function → add a `NavChip` in the bottom nav.

---

## Navigation

### Top nav (all pages except auth)
Defined as `TopNav` in `home.jsx`. Props: `active` (string), `onNav` (fn), `search`, `setSearch`.
Highlights the active tab. Links: Home · Agents · Portfolio · Learn.

### Bottom floating nav strip (index.html inline)
Fixed position, bottom-left, pill shape. Always visible on non-auth screens.

```jsx
<NavChip active={screen==='home'}      onClick={goHome}                     icon={<Icon.Home size={14}/>}      label="Home"/>
<NavChip active={screen==='agents'}    onClick={goAgents}                   icon={<Icon.Cpu size={14}/>}       label="Agents"/>
<NavChip active={screen==='portfolio'} onClick={()=>setScreen('portfolio')} icon={<Icon.Briefcase size={14}/>} label="Portfolio"/>
<NavChip active={screen==='learn'}     onClick={()=>setScreen('learn')}     icon={<Icon.Book size={14}/>}      label="Learn"/>
<NavChip                               onClick={()=>setScreen('auth')}      icon={<Icon.User size={14}/>}      label="Sign out"/>
```

---

## Design Tokens (styles.css CSS variables)

```css
/* Backgrounds */
--bg-base:       #f6f7fb    /* page background */
--bg-surface:    #ffffff    /* cards */
--bg-tinted:     #f0f4ff    /* subtle accent bg */

/* Text */
--ink-1:  #111827   /* primary */
--ink-2:  #4b5563   /* secondary */
--ink-3:  #9ca3af   /* muted/labels */

/* Accent */
--cyan:         #0891b2
--cyan-soft:    rgba(8,145,178,.10)
--violet:       #7c3aed
--violet-soft:  rgba(124,58,237,.10)

/* Verdict colours */
--buy-strong:  #16a34a    --buy-soft:   rgba(22,163,74,.10)
--buy:         #22c55e
--neutral:     #d97706    --neutral-soft: rgba(217,119,6,.10)
--sell:        #ea580c    --sell-soft:   rgba(234,88,12,.10)
--sell-strong: #dc2626

/* Shadows */
--shadow-sm: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04)
--shadow-md: 0 4px 16px rgba(0,0,0,.08), 0 2px 4px rgba(0,0,0,.04)

/* Borders */
--border:        #e5e7eb
--border-strong: #d1d5db

/* Dark mode — applied when data-theme="dark" on <html> */
/* All vars above are overridden for dark in :root[data-theme="dark"] */
```

**Utility classes:** `.card` (white surface + shadow + border-radius), `.eyebrow` (11px uppercase label), `.mono` (JetBrains Mono font).

**Theme toggle:** `tweaks.theme` → sets `document.documentElement.setAttribute('data-theme', value)`. Options: `'light'` | `'dark'`.

---

## Data Layer (data.jsx)

### Layer 1 — Mock data (always set synchronously)

| Global | Type | Used by |
|---|---|---|
| `window.AGENTS` | `array[9]` | AgentsPage, Home |
| `window.AGENT_TASKS` | `object` | AgentsPage drawer |
| `window.AGENT_SOURCES` | `object` | AgentsPage drawer |
| `window.TICKERS` | `array[8]` | Home watchlist |
| `window.WATCHLIST` | `string[]` | Home |
| `window.MARKET_TODAY` | `object` | Home today pane |
| `window.MARKET_MONTH` | `object` | Home month pane |
| `window.TRENDING` | `array` | Home trending |
| `window.SUGGESTIONS` | `array` | Home suggestions |
| `window.CATEGORIES` | `array` | Home categories |
| `window.NIFTY_AUTO_HISTORY` | `number[]` | Home sparkline |
| `window.NIFTY_AUTO_RANGES` | `object` | Home range chart |
| `window.CHAT_SEEDS` | `string[]` | Chat overlay |
| `window.PORTFOLIO` | `object` | PortfolioPage |
| `window.PORTFOLIO_RANGES` | `object` | PortfolioPage chart |
| `window.PORTFOLIO_LEARNINGS` | `object` | PortfolioPage |
| `window.LEARN_PATHS` | `array[6]` | LearnPage |
| `window.GLOSSARY` | `array[6]` | LearnPage |
| `window.LEARN_TIPS` | `array[3]` | LearnPage |

### Layer 2 — Live API bootstrap
```javascript
window.__bootstrap()  // called in index.html before React mounts
// → POST /ui/bootstrap → Python FastAPI
// → overlays AGENTS, TICKERS, MARKET_TODAY, NIFTY_AUTO_HISTORY, TRENDING, etc.
// → sets window.__LIVE_DATA = true on success
// → falls back silently to mock on error
```

**Live data badge:** `window.__LIVE_DATA === true` → green "● LIVE" pill appears in bottom nav.

---

## Key Components

### `window.Icon` (icons.jsx)
All icons are Lucide-style SVG. Usage: `<Icon.Search size={18}/>` or `<Icon.Home size={14} c="var(--cyan)"/>`.

Available: `Search, Plus, Star, Trend, TrendDown, Sparkles, Compass, Layers, Bot, Cpu, Settings, Home, Bell, Send, X, Check, Eye, EyeOff, ChevronR, ChevronL, ChevronD, Mic, Plug, Drag, Mail, Lock, User, Google, Apple, Briefcase, Book`

**Adding a new icon:** Add to the `Icon` object in `icons.jsx` following the same `(p)=> <I {...p}>...</I>` pattern.

### `AgentIcon` (icons.jsx)
```jsx
<AgentIcon agentKey="sales_demand" emoji="📊" size={48}/>
// Tries to load /app/icons/{agentKey}.svg
// Falls back to emoji if SVG missing or fails to load
```

### `TopNav` (home.jsx)
```jsx
<TopNav active="agents" onNav={setScreen} search={search} setSearch={setSearch}/>
// active: 'home' | 'agents' | 'portfolio' | 'learn'
```

### `SphereOrb` / `ChatOverlay` (sphere.jsx)
```jsx
<SphereOrb onOpen={openChat} mode={tweaks.sphereMode}/>   // floating orb
<ChatOverlay open={chat} onClose={closeChat} mode={tweaks.sphereMode}/>  // full overlay
// mode: 'wireframe' | 'liquid'
// Chat calls window.__sendChat(text) → POST /ui/chat → Python LLM
// Falls back to window mockReply() on error
```

### `Sparkline` (home.jsx)
```jsx
<Sparkline values={[22650, 22700, ...]} height={60} color="var(--cyan)"/>
// Renders an SVG area chart from a number array
```

### `SectionHead` (home.jsx)
```jsx
<SectionHead title="All agents" subtitle="Click any card to tune"/>
```

---

## Agents Page (agents-page.jsx)

### Data dependencies
- `window.AGENTS` — array of 9 agent objects `{ key, name, icon, weight, enabled, desc, beginner }`
- `window.AGENT_TASKS` — per-agent task arrays `{ key, label, source, enabled, beginner }`
- `window.AGENT_SOURCES` — per-agent source label arrays

### Components
```
AgentsPage
  ├── TopNav
  ├── Stat (×3)          — PLUGGED IN / ACTIVE TASKS / AVG LATENCY
  ├── Pipeline           — Live pipeline visual (Ticker → agents fan → Verdict)
  │   └── PipelineNode
  ├── AgentCard (×9)     — PLUGGED IN toggle, task chip preview, weight bar
  └── AgentDrawer        — Slide-in right panel on card click
      ├── plug toggle
      ├── TaskRow (×5-6) — per-task toggle with beginner desc + source
      ├── weight slider
      ├── recent runs (mock)
      └── data sources
```

---

## Portfolio Page (portfolio.jsx)

### Data dependencies
- `window.PORTFOLIO` — `{ totalValue, totalCost, dayChange, cash, holdings[], recentActivity[], alerts[] }`
- `window.PORTFOLIO_RANGES` — `{ '1W'|'1M'|'3M'|'6M'|'1Y': { points[], label, change } }`
- `window.PORTFOLIO_LEARNINGS` — `{ summary, items[], patterns[] }`

### Components
```
PortfolioPage
  ├── TopNav
  ├── Hero strip (dark gradient, total value, sparkline, range selector)
  ├── HoldingsTable      — qty, avg buy, current, value, P/L, agent take (verdict badge)
  ├── LearningsSection   — missed gains, avoided losses, pattern chips, lesson cards
  ├── ActivityCard       — buy/sell/agent event feed
  ├── AlertsCard         — agent flags per holding
  ├── AllocationCard     — coloured bar + legend
  └── AskAssistantCard   — opens sphere chat
```

---

## Learn Page (learn.jsx)

### Data dependencies
- `window.LEARN_PATHS` — 6 learning paths `{ key, title, sub, minutes, steps, progress, color, icon }`
- `window.GLOSSARY` — 6 terms `{ term, short, defn }`
- `window.LEARN_TIPS` — 3 tips `{ title, body }`

### Components
```
LearnPage
  ├── TopNav
  ├── Hero (gradient, progress bar, sphere button)
  ├── PathCard (×6)      — progress bar header, icon, title, steps/min, done badge
  ├── GlossaryCard       — 6 terms in 2-col grid
  ├── TipsCard           — numbered list
  ├── RecCard (×2)       — "Watch a demo" + "Quiz"
  └── PathOverlay        — slide-in drawer with step list on PathCard click
```

---

## API Endpoints Used

| Endpoint | Method | Used by | What it returns |
|---|---|---|---|
| `/ui/bootstrap` | GET | data.jsx `__bootstrap()` | All UI data merged (agents, tickers, market, history) |
| `/ui/market/summary` | GET | data.jsx (UI kit, not main app) | Live market indices |
| `/ui/chat` | POST `{message}` | sphere.jsx `__sendChat()` | `{reply: string}` |
| `/analyse` | POST `{ticker}` | (UI kit Analyze page — not `/app`) | Full FinalReport JSON |

---

## Tweaks Panel (dev only)

Accessible via gear icon, bottom-right corner.

| Tweak | Values | Effect |
|---|---|---|
| Theme | light / dark | Sets `data-theme` on `<html>` |
| Sphere style | wireframe / liquid | Changes sphere visual mode |
| Density | comfy / cozy / dense | Future: tighten card spacing |
| Quick jump | buttons | Jump to any screen directly |
| Data | status text | Shows "✓ Live data" or "⚠ Mock data" |

---

## How to Make Changes

### Change text / copy in a page
Find the JSX string in the relevant `*.jsx` file. No rebuild needed — just save and refresh.

### Add a new agent card field
1. Add the field to each agent object in `window.AGENTS` in `data.jsx`
2. Read it in `AgentCard` or `AgentDrawer` in `agents-page.jsx`

### Add a new icon
In `icons.jsx`, add to the `Icon` object:
```javascript
MyIcon: (p)=> <I {...p}><path d="...SVG path..."/></I>,
```

### Add a new page
1. Create `newpage.jsx` with `function NewPage({ onNav, openChat }) {...}` and `window.NewPage = NewPage;`
2. Add `<script type="text/babel" src="newpage.jsx"></script>` in `index.html` (before the inline script)
3. Add route in `index.html` App function: `{screen === 'newpage' && <NewPage onNav={setScreen} openChat={openChat}/>}`
4. Add `NavChip` in the bottom nav strip

### Add new mock data
Add `window.MY_DATA = {...}` in `data.jsx` before the bootstrap section.
For it to be overridden by live API: add it to the `/ui/bootstrap` response in `services/api/routes/ui_data.py`.

### Wire a new API endpoint
In `data.jsx` inside `window.__bootstrap()`:
```javascript
const res = await fetch('/ui/my-endpoint');
const data = await res.json();
window.MY_DATA = data.something;
```

---

## Server Setup

```bash
# Start Python backend (serves /app at port 8001)
uvicorn services.api.server:app --host 0.0.0.0 --port 8001 --reload

# Optional: Start TypeScript gateway (port 3000)
cd services/gateway && bun dev
```

Only one URL needed to use the UI: `http://localhost:8001/app`
