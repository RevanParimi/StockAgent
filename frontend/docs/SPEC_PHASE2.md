# Phase 2 — Dashboard + Watchlist
**Status: 🔲 TODO**

## Build Order
1. Build `Sidebar` + `MarketBar` layout components
2. Build `PageTransition` wrapper (already done in Phase 1)
3. Build `Dashboard` page (3-column, all 4 cards)
4. Build `VerdictDonut` chart
5. Build `StockCard` + 3D tilt effect
6. Build `QuickDrawer` (slide-out panel)
7. Build `WatchlistManager` + `AddTickerModal`
8. Build `MiniSparkline` (fetch from /history/:ticker or mock)
9. Build `Watchlist` page (full grid + drawer)
10. Wire `useWatchlist` hook to Zustand (localStorage persistence)

## New Files to Create
```
src/
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx              ← Left nav, collapsible icon→label
│   │   └── MarketBar.tsx            ← Top strip: SENSEX, NIFTY, NIFTY AUTO, INR/USD
│   ├── charts/
│   │   ├── VerdictDonut.tsx         ← Recharts PieChart: BUY/SELL/NEUTRAL distribution
│   │   └── MiniSparkline.tsx        ← Tiny 30-day area sparkline (Recharts)
│   └── watchlist/
│       ├── StockCard.tsx            ← Glassmorphism card with 3D tilt on hover
│       ├── QuickDrawer.tsx          ← Slide-out panel (380px from right)
│       ├── WatchlistManager.tsx     ← Create/rename/delete watchlists
│       └── AddTickerModal.tsx       ← Modal to add tickers
├── hooks/
│   └── useWatchlist.ts              ← CRUD for watchlists (delegates to Zustand)
└── pages/
    ├── Dashboard.tsx                ← REPLACE stub
    └── Watchlist.tsx                ← REPLACE stub
```

## Sidebar Component
```
Props: none (reads from router location for active state)

Layout:
  - Width: 72px collapsed, 220px expanded (hover to expand)
  - Slide animation: CSS transition width 300ms
  - Logo at top (icon always visible, text slides in)
  
Navigation items:
  ⊞ Dashboard   → /dashboard
  ◎ Analyze     → /analyze
  ☆ Watchlist   → /watchlist
  📈 History    → /history
  ⚙ Settings   → /settings (static page)

  Each item:
  - Lucide icon (always visible)
  - Label (visible only when expanded)
  - Active state: cyan accent + glow
  - Hover: bg-elevated

  Bottom:
  - User avatar (initials circle) + name (visible when expanded)
  - Logout button
```

## MarketBar Component
```
Layout: 48px tall strip, full width, above main content
Background: rgba(5,8,16,0.9) backdrop-blur

Items (poll every 60s or use static mock):
  SENSEX  82,450  ▲ 1.2%
  NIFTY   24,980  ▲ 0.9%
  NIFTY AUTO  24,120  ▲ 2.1%
  INR/USD 83.42  ▼ 0.1%

Each item: label + value (JetBrains Mono) + change (green if ▲, red if ▼)
Left side: pulsing green dot + "Live" text
Right side: last updated time
```

## Dashboard Page — 3-Column Layout
```
Grid: grid-cols-3 on desktop, grid-cols-2 tablet, grid-cols-1 mobile

COLUMN 1 (30%) — "Your Watchlist"
  GlassCard with list of watchlisted tickers
  Each row: ticker (mono) + VerdictBadge + score bar + score number
  Hover: highlight row + show "→ Quick View"
  Click: opens QuickDrawer
  "+" button → AddTickerModal

COLUMN 2 (40%) — Market Mood + Recent Analyses
  Card 1: VerdictDonut
    - Donut chart: BUY/NEUTRAL/SELL/STRONG BUY/STRONG SELL split across watchlist
    - Center: "Portfolio Bias" + dominant verdict
  Card 2: "Recent Analyses" (last 5 from Zustand analyses map)
    - Each row: ticker + VerdictBadge + score + "X mins ago"
    - Click: route to /analyze?ticker=MARUTI

COLUMN 3 (30%) — Scheduler + Score Leaders
  Card 1: "Scheduler Status"
    - "Next Run" time (from C# /api/scheduler/status or mock)
    - "Tomorrow · 8:30am IST"
    - Pill: "5 tickers queued"
    - "Run Now" button → triggers POST /analyse for all watchlisted tickers
    - List of scheduled tickers
  Card 2: "Score Leaders"
    - Top 3 tickers by score
    - Mini score bars + VerdictBadge
```

## StockCard Component
```
Size: ~280px wide, glassmorphism
Content:
  - Company initials avatar (colored circle, first 2 letters)
  - Company name + NSE ticker (mono font)
  - VerdictBadge (with glow)
  - Score number (large, JetBrains Mono)
  - MiniSparkline (30-day score, Recharts AreaChart 120×40px)
  - "Analyze Now" button → navigate to /analyze?ticker=X
  - 3-dot menu: "Add note" | "Remove from list"

3D Tilt Effect (onMouseMove):
  const rect = card.getBoundingClientRect()
  const x = (e.clientY - rect.top  - rect.height/2) / rect.height * 8   // rotateX
  const y = (e.clientX - rect.left - rect.width/2)  / rect.width  * -8  // rotateY
  style: `perspective(1000px) rotateX(${x}deg) rotateY(${y}deg)`
  transition: 0.1s ease on move, 0.3s ease on leave → reset to 0,0

Card click (anywhere except button/menu): opens QuickDrawer
```

## QuickDrawer Component
```
Layout: 380px wide, slides in from right, overlays content
Background: bg-surface + glassmorphism
Backdrop: semi-transparent overlay on main content

Header:
  - Company name + ticker
  - Close button (×)

Sections:
  1. "Last analyzed" — time ago
     - ScoreGauge mini (200px) [import from Phase 3 or use simple progress arc]
     - VerdictBadge

  2. "Agent Breakdown" — 8 horizontal score bars
     Sales & Demand    ████████░░  0.85
     Fundamentals      ███████░░░  0.79
     ... (all 8 agents) ...
     Color: green/amber/red by score

  3. "Top Insight" — first conviction driver
     Blockquote style with left border

  4. "Top Risk" — first risk
     Warning style with warning icon

  5. CTAs:
     "Full Analysis →" → /analyze?ticker=X
     "View History →"  → /history?ticker=X

Animation: Framer Motion x: 400→0 slide
Mobile: full-screen bottom sheet instead
```

## VerdictDonut Chart
```tsx
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

// Group watchlist tickers by verdict category
// Colors match verdict color tokens
// Center label: count + dominant verdict
// Animated: isAnimationActive={true}
```

## MiniSparkline Chart
```tsx
import { AreaChart, Area, ResponsiveContainer } from 'recharts'

// 30 data points from /history/:ticker or mock
// No axes, no labels — just the shape
// Color: gradient from verdict color (top) to transparent (bottom)
// Height: 40px
// Stroke: 1.5px verdict color
```

## WatchlistManager + AddTickerModal
```
WatchlistManager:
  - Dropdown selector: "My Stocks ▼"
  - Buttons: "+ Create List" | "✏ Rename" | "🗑 Delete"
  - Uses Zustand: addWatchlist, renameWatchlist, removeWatchlist

AddTickerModal:
  - Modal (centered, glassmorphism)
  - Search input + grid of 10 ticker chips
  - Select ticker(s) → addTicker(activeWatchlist, ticker)
  - "Add" button
```

## useWatchlist Hook
```typescript
// src/hooks/useWatchlist.ts
// Thin wrapper over Zustand store selectors
// Returns: { list, add, remove, rename, create, activeList, setActive }
```

## Shared Layout Wrapper
```tsx
// AppLayout wraps Dashboard + Watchlist + Analyze + History
// Children: MarketBar (top) + Sidebar (left) + main content area
// Page content gets: ml-[72px] mt-[48px] padding (desktop)
```

## Mock Data Available
- `src/mocks/sampleReport.ts` → `mockWatchlistReports` for all 10 tickers
- `sampleHistory` for MARUTI sparkline
- C# scheduler mock: `{ is_running: true, next_fire_time: "2026-04-18T03:00:00Z", ticker_count: 5 }`
