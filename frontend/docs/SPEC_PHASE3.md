# Phase 3 — Analyze (Flagship Page)
**Status: 🔲 TODO**

## Build Order
1. Build `TickerSearch` (autocomplete + free text)
2. Build `useWebSocket` hook (native WebSocket, handles reconnect)
3. Build `useAnalysis` hook (state machine: idle→streaming→complete→error)
4. Build `StreamProgress` with 8 `AgentCard` components (pending/analyzing/complete states)
5. Build `ScoreGauge` (SVG speedometer with animated needle)
6. Build `VerdictReveal` (card flip animation)
7. Build `AgentRadar` (Recharts RadarChart, animated draw)
8. Build `AgentScoreTable` (sortable)
9. Build `ConvictionPanel` (drivers + risks)
10. Build `ThesisCard` + `ConflictsPanel`
11. Build `HistoryLine` (full-width score trend chart)
12. Build export functionality (JSON copy, CSV download, print PDF)
13. Wire full Analyze page end-to-end with real backend

## New Files to Create
```
src/
├── components/
│   ├── charts/
│   │   ├── ScoreGauge.tsx          ← SVG speedometer, animated needle 0→score
│   │   ├── AgentRadar.tsx          ← Recharts RadarChart, 8 axes, animated
│   │   ├── HistoryLine.tsx         ← Score trend LineChart with verdict zones
│   │   └── MiniSparkline.tsx       ← (also needed by Phase 2 watchlist)
│   └── analysis/
│       ├── TickerSearch.tsx        ← Autocomplete search (10 tickers + free text)
│       ├── StreamProgress.tsx      ← Live WebSocket agent progress tracker
│       ├── AgentCard.tsx           ← Individual agent card: pending/analyzing/complete
│       ├── VerdictReveal.tsx       ← Animated card flip + score counter
│       ├── ConvictionPanel.tsx     ← Drivers vs Risks two-column
│       ├── ThesisCard.tsx          ← Investment thesis + copy button
│       ├── ConflictsPanel.tsx      ← Collapsible conflicts section
│       └── AgentScoreTable.tsx     ← Sortable table: agent, raw, weight, weighted
├── hooks/
│   ├── useWebSocket.ts             ← Native WebSocket manager
│   └── useAnalysis.ts              ← State machine orchestrator
└── pages/
    └── Analyze.tsx                 ← REPLACE stub — full 3-step page
```

## Analyze Page — 3 Steps

### Step 1: Search (idle state)
```
TickerSearch:
  - Large search input (placeholder: "Enter ticker or company name...")
  - Autocomplete dropdown: 10 tickers with company names + current score if known
  - Free-text input: resolve via POST /analyse (LLM ticker resolution)
  - URL param: if ?ticker=MARUTI → auto-populate + trigger analysis
  - "Analyze →" GlowButton (cyan glow)
  - On submit → transition to Step 2 (streaming)
```

### Step 2: Streaming Progress (streaming state, 30–90 seconds)
```
StreamProgress (WebSocket: ws://localhost:8000/ws/stream?ticker=X):

  Top bar:
  - "Analyzing MARUTI · Maruti Suzuki India Ltd"
  - Overall progress bar (completedCount / 8)
  - Elapsed time counter (counting up in seconds, useInterval)

  8 AgentCard in 2×4 grid:

  PENDING state (dim):
    - Icon (gray) + name (muted text) + "Waiting..."
    - Card border: border-[var(--border-color)]

  ANALYZING state (pulsing, shown for in-flight agent):
    - Icon (cyan, animate-pulse) + name (bright) + spinner
    - Card border: cyan glow pulsing animation

  COMPLETE state (lit up):
    - Icon (colored by score) + name + score number (large mono font)
    - Horizontal fill bar: Framer Motion width 0% → score×100%
    - Card border: glows in verdict color
    - Framer Motion spring pop: scale 1.0 → 1.05 → 1.0

  WebSocket event: { "event": "agent_progress", "agent": "fundamentals", "score": 0.68 }
  → update agentStates[agent] = { state: 'complete', score: 0.68 }

  When all 8 complete:
  - "Generating verdict..." spinner
  - Wait for { "event": "complete", "report": <FinalReport> }
  - Scroll-reveal transition to Step 3

  On { "event": "error" }:
  - Show error card: "Analysis failed: <detail>"
  - "Try Again" button
```

### Step 3: Results (complete state)

#### Verdict Block (centered, above fold)
```
VerdictReveal:
  Animated card flip:
    Front: "Analyzing..." → spinning animation
    Back (on complete):
      - Company name + ticker + date
      - ScoreGauge: SVG speedometer, needle 0→final_score over 1.5s
      - AnimatedCounter: 0.00 → 0.82
      - VerdictBadge: slide in from below + glow pulse

  Below card:
    "Report generated in 47s · 8 agents · 0 conflicts"
    (or "2 conflicts resolved by LLM" if conflicts_resolved present)
```

#### Two-Column Layout
```
LEFT (55%):
  AgentRadar (Recharts RadarChart):
    - 8 axes: sales_demand, fundamentals, pattern_analysis, raw_materials,
              sentiment, policy_regulatory, competitive_intel, risk_macro
    - Axis labels use AGENT_LABELS from types/index.ts
    - Filled polygon = weighted scores (not raw)
    - Tooltip: raw + weight + weighted for hovered axis
    - Animation: strokes draw from center outward on mount
    - Colors: fill rgba(6,182,212,0.15), stroke #06b6d4

  AgentScoreTable (below radar):
    Columns: Agent | Raw Score | Weight | Weighted Score
    - Sortable by any column (click header)
    - Color-coded rows:
        raw >= 0.70 → green text
        raw 0.45–0.69 → amber text
        raw < 0.45 → red text
    - "Total / Composite" row at bottom showing final_score
    - Styled as dark table, alternating row backgrounds

RIGHT (45%):
  ConvictionPanel:
    "Conviction Drivers" section:
      - Green checkmark icon header
      - Bullet list with ✓ prefix in green
    "Top Risks" section (below drivers):
      - Red × icon header
      - Bullet list with ✗ prefix in red
    Each item animates in on mount (staggered)

  ConflictsPanel (show only if conflicts_resolved?.length > 0):
    - Collapsible: "⚡ N Conflicts Resolved" header (orange)
    - Click to expand → list of conflict descriptions
    - Chevron icon rotates on expand/collapse
```

#### Below Two-Column
```
ThesisCard (full-width):
  "Investment Thesis" heading
  investment_thesis text (readable, line-height 1.8, 16px, preserving \n as paragraphs)
  "Copy" button (top-right) → copies to clipboard

HistoryLine (full-width):
  "Score History — MARUTI · Last 90 Days" heading
  Recharts LineChart:
    - x-axis: date (format "MMM dd")
    - y-axis: score 0–1
    - Reference bands (verdict zones):
        0.75–1.00 → green band (opacity 0.05)
        0.60–0.74 → teal band
        0.45–0.59 → amber band
        0.30–0.44 → orange band
        0.00–0.29 → red band
    - Reference lines at 0.75, 0.60, 0.45, 0.30 (faint dashed)
    - Dots at each data point
    - Tooltip: "Apr 14 · 0.79 · BUY"
    - Gradient stroke color (changes with score zone)
  Uses /history/:ticker endpoint or falls back to sampleHistory

Export Bar (sticky bottom or top-right floating):
  📋 "Copy JSON"  → JSON.stringify(report, null, 2) → clipboard
  ⬇ "Download CSV" → generate CSV file of AgentScoreTable
  📄 "Print PDF"  → window.print() with clean print stylesheet
```

## useWebSocket Hook
```typescript
// src/hooks/useWebSocket.ts
interface UseWebSocketOptions {
  url: string
  onMessage: (event: StreamEvent) => void
  onError?: (error: Event) => void
  enabled?: boolean   // connect only when true
}

// Returns: { connected, disconnect }
// Auto-reconnect: up to 3 times, 2s backoff
// Cleanup on unmount
```

## useAnalysis Hook (State Machine)
```typescript
// src/hooks/useAnalysis.ts
type AnalysisStatus = 'idle' | 'streaming' | 'complete' | 'error'

interface UseAnalysisReturn {
  status: AnalysisStatus
  ticker: string
  agentStates: Record<string, AgentStreamState>
  completedCount: number
  elapsedSeconds: number
  report: FinalReport | null
  error: string | null
  startAnalysis: (ticker: string) => void
  reset: () => void
}

// startAnalysis:
//   1. Open WebSocket: ws://localhost:8000/ws/stream?ticker=X
//   2. On agent_progress → update agentStates
//   3. On complete → save report, update Zustand analyses store
//   4. On error → set error state
//   5. Fallback: if backend down → use sampleReport after 3s mock delay
```

## ScoreGauge Component
```
SVG speedometer gauge (no external library):
  - Semicircle arc (180°) from left to right
  - Background track: dark gray arc
  - Colored fill arc: animates from 0 to final_score * 180°
  - Color: interpolated by score (red → amber → green)
  - Needle: thin line from center rotating 0° (left) to 180° (right)
  - Needle animates via requestAnimationFrame over 1.5s
  - Score labels at bottom: 0, 0.25, 0.5, 0.75, 1.0
  - Zone tick marks at 0.30, 0.45, 0.60, 0.75

Props: { score: number, size?: number, animate?: boolean }
```

## Demo/Offline Fallback
```
If WebSocket connection fails or backend is not running:
  - Show banner: "Running on demo data — start backend for live analysis"
  - Use sampleReport from mocks/sampleReport.ts
  - Simulate streaming: reveal agents one-by-one with 500ms delay each
```
