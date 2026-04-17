# Phase 4 — History + Polish
**Status: 🔲 TODO**

## Build Order
1. Build `History` page (single + compare mode)
2. Add date range filtering to `useHistory` hook
3. Responsive: implement mobile/tablet breakpoints for all pages
4. Performance: lazy-load Three.js scenes (already done in Phase 1 via lazy())
5. Accessibility: keyboard nav, ARIA labels, focus rings
6. Loading states: Skeleton loaders (LoadingPulse) everywhere
7. Error states: graceful UI for API failures
8. ⚠️ Remind user about image assets

## New Files to Create
```
src/
├── hooks/
│   ├── useHistory.ts           ← Fetches /history/:ticker with date range
│   └── useMarketData.ts        ← Polls market indices (mock or /api/market)
└── pages/
    └── History.tsx             ← REPLACE stub — full history page
```

## History Page

### Top Bar
```
- Ticker selector: multi-select dropdown (compare up to 3 tickers)
  Options: all 10 tickers with their latest score/verdict
- Date range buttons: "30d" | "90d" | "1yr" | "All"
  → filters displayed data
- "Compare Mode" toggle (boolean)
```

### Single Ticker Mode
```
Large HistoryLine chart:
  - Full width, 400px tall
  - Same chart as in Analyze page (verdict zone bands + tooltip)
  - Animated on mount

Data table below chart:
  Columns: Date | Verdict | Score | Change (±) | Actions
  - Color-coded Verdict column (VerdictBadge)
  - Change: +0.03 (green) / -0.05 (red)
  - Actions: "View Full Report" button → /analyze?ticker=X&date=Y (loads historical report)
  - Sortable by Date (default: newest first)
  - Pagination or virtual scroll for large datasets
```

### Compare Mode
```
- Overlay multiple HistoryLine charts on same axes
- One line per selected ticker, different colors
- Legend: ticker + current score + current verdict (top right)
- Hovering: vertical crosshair + tooltip per ticker
  Format: "MARUTI: 0.82 | TATAMOTORS: 0.71"
- Color palette: cyan, violet, amber for up to 3 tickers
```

## useHistory Hook
```typescript
// src/hooks/useHistory.ts
interface UseHistoryOptions {
  ticker: string
  days?: 30 | 90 | 365 | 9999   // 9999 = all
  enabled?: boolean
}

interface UseHistoryReturn {
  records: ScoreRecord[]
  loading: boolean
  error: string | null
  refetch: () => void
}

// GET /history/:ticker → filter client-side by date range
// Falls back to sampleHistory from mocks if backend down
```

## useMarketData Hook
```typescript
// src/hooks/useMarketData.ts
interface MarketIndex {
  label: string
  value: number
  change: number       // percentage
  changeDirection: 'up' | 'down'
}

// Poll every 60 seconds
// Endpoint: GET /api/market (TypeScript proxy) or yfinance directly
// Mock data if endpoint unavailable:
const MOCK_MARKET = [
  { label: 'SENSEX',    value: 82450, change: 1.2,  changeDirection: 'up' },
  { label: 'NIFTY',     value: 24980, change: 0.9,  changeDirection: 'up' },
  { label: 'NIFTY AUTO',value: 24120, change: 2.1,  changeDirection: 'up' },
  { label: 'INR/USD',   value: 83.42, change: -0.1, changeDirection: 'down' },
]
```

## Responsive Design — All Pages

### Mobile (< 768px)
```
Sidebar:         → Bottom tab bar (5 items: Dashboard, Analyze, Watchlist, History, Settings)
Dashboard:       → Single column stack
Analysis Step 2: → 4×2 AgentCards → 2×4 (2 columns)
Analysis Step 3: → Verdict full-width, radar below, table below radar, thesis below
Watchlist:       → 1-column grid
QuickDrawer:     → Full-screen bottom sheet (slides up from bottom, 90vh)
3D effects:      → Reduce particle count 50%, disable cursor trail
Custom cursor:   → Hidden on touch devices
```

### Tablet (768px–1024px)
```
Sidebar:         → Icon-only 72px (no labels), no hover expand
Dashboard:       → 2-column grid
Analysis:        → Radar + table side-by-side, thesis below
Watchlist:       → 2-column grid
QuickDrawer:     → 280px panel (smaller than desktop 380px)
```

### Desktop (> 1024px)
```
Full layout as specified in Phase 2 + Phase 3 specs
```

## Accessibility Checklist
- [ ] All interactive elements keyboard-navigable (Tab + Enter/Space)
- [ ] Focus rings visible (outline-2 outline-offset-2 outline-accent-cyan)
- [ ] ARIA labels on icon-only buttons
- [ ] `role="progressbar"` on score bars with `aria-valuenow`
- [ ] `role="status"` on streaming progress updates
- [ ] Color not sole indicator of verdict (also text + shape)
- [ ] Screen reader text on VerdictBadge: `aria-label="Verdict: STRONG BUY"`
- [ ] Reduced motion: `prefers-reduced-motion` → disable animations
- [ ] Alt text or aria-hidden on decorative Three.js canvases

## Performance Checklist
- [ ] Three.js scenes lazy-loaded (already done: `lazy(() => import(...))`)
- [ ] Dispose Three.js geometries/materials on unmount (already in Globe3D/ParticleField)
- [ ] Recharts responsive containers (already wrapped in ResponsiveContainer)
- [ ] Zustand store: avoid re-renders by using selectors not full store
- [ ] React.memo on AgentCard, StockCard (re-render only when score changes)
- [ ] useCallback on WebSocket message handler
- [ ] Vite code splitting: each page is already lazy-loaded in App.tsx

## Error States — All Components
Every data-fetching component must show:
```
Loading: <LoadingPulse /> or <CardSkeleton />
Error:   GlassCard with ⚠ icon + error message + "Retry" button
Empty:   GlassCard with icon + helpful empty state message
```

## Final Image Assets Reminder
At end of Phase 4, remind user:

> ⚠️ Image assets needed for full visual impact:
> 1. App logo SVG → replace `<TrendingUp>` icon in nav/sidebar/auth
> 2. Company logos for 10 OEMs (PNG, 64×64px) — optional, initials avatar is fallback
>    MARUTI, TATAMOTORS, M&M, HEROMOTOCO, BAJAJ-AUTO,
>    EICHERMOT, TVSMOTORS, ASHOKLEY, ESCORTS, FORCEMOT
> 3. Mumbai skyline (optional hero background) → 1920×1080px
> The app works without all of these — initials avatars and icon logos are already in place.
