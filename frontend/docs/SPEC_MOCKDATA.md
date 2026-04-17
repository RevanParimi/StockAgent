# Mock Data Reference

## Location
`src/mocks/sampleReport.ts`

## Exports

### `sampleReport: FinalReport`
Full MARUTI analysis report for offline/demo use.

```typescript
{
  ticker: "MARUTI",
  company_name: "Maruti Suzuki India Ltd",
  final_score: 0.82,
  verdict: "STRONG BUY",
  weighted_agent_scores: {
    sales_demand:      { raw: 0.85, weight: 0.18, weighted: 0.153 },
    fundamentals:      { raw: 0.79, weight: 0.20, weighted: 0.158 },
    pattern_analysis:  { raw: 0.72, weight: 0.13, weighted: 0.094 },
    raw_materials:     { raw: 0.61, weight: 0.10, weighted: 0.061 },
    sentiment:         { raw: 0.55, weight: 0.04, weighted: 0.022 },
    policy_regulatory: { raw: 0.80, weight: 0.10, weighted: 0.080 },
    competitive_intel: { raw: 0.78, weight: 0.10, weighted: 0.078 },
    risk_macro:        { raw: 0.68, weight: 0.15, weighted: 0.102 },
  },
  conviction_drivers: [5 bullet strings],
  top_risks: [4 bullet strings],
  conflicts_resolved: [1 conflict string],
  investment_thesis: "3-paragraph narrative...",
  report_date: "2026-04-17"
}
```

### `sampleHistory: ScoreRecord[]`
30 ScoreRecord entries spanning 90 days (every 3 days).
Scores range 0.70–0.85. Verdicts auto-calculated by score threshold.

### `mockWatchlistReports: Record<string, { score: number; verdict: string }>`
Latest score + verdict for all 10 tickers:
```
MARUTI:     { score: 0.82, verdict: 'STRONG BUY' }
TATAMOTORS: { score: 0.71, verdict: 'BUY' }
M&M:        { score: 0.68, verdict: 'BUY' }
HEROMOTOCO: { score: 0.55, verdict: 'NEUTRAL' }
BAJAJ-AUTO: { score: 0.63, verdict: 'BUY' }
EICHERMOT:  { score: 0.74, verdict: 'BUY' }
TVSMOTORS:  { score: 0.60, verdict: 'BUY' }
ASHOKLEY:   { score: 0.48, verdict: 'NEUTRAL' }
ESCORTS:    { score: 0.42, verdict: 'SELL' }
FORCEMOT:   { score: 0.35, verdict: 'SELL' }
```

## Fallback Strategy
When backend is not available:
1. Show non-intrusive banner: `"Running on demo data — start backend for live analysis"`
2. POST /analyse fails → return `sampleReport` after 2s simulated delay
3. WS connection fails → simulate stream using `sampleReport.weighted_agent_scores`
   with 500ms delay per agent
4. GET /history fails → return `sampleHistory`
5. GET /api/scheduler/status fails → return mock: `{ is_running: true, next_fire_time: "2026-04-18T03:00:00Z", ticker_count: 5 }`

## Ticker Constants (from `src/types/index.ts`)
```typescript
TICKERS = ['MARUTI','TATAMOTORS','M&M','HEROMOTOCO','BAJAJ-AUTO',
           'EICHERMOT','TVSMOTORS','ASHOKLEY','ESCORTS','FORCEMOT']

TICKER_NAMES = {
  MARUTI:       'Maruti Suzuki India Ltd',
  TATAMOTORS:   'Tata Motors Ltd',
  'M&M':        'Mahindra & Mahindra Ltd',
  HEROMOTOCO:   'Hero MotoCorp Ltd',
  'BAJAJ-AUTO': 'Bajaj Auto Ltd',
  EICHERMOT:    'Eicher Motors Ltd',
  TVSMOTORS:    'TVS Motor Company Ltd',
  ASHOKLEY:     'Ashok Leyland Ltd',
  ESCORTS:      'Escorts Kubota Ltd',
  FORCEMOT:     'Force Motors Ltd',
}

AGENT_LABELS = {
  sales_demand:      'Sales & Demand',
  fundamentals:      'Fundamentals',
  pattern_analysis:  'Pattern Analysis',
  raw_materials:     'Raw Materials',
  sentiment:         'Sentiment',
  policy_regulatory: 'Policy & Regulatory',
  competitive_intel: 'Competitive Intel',
  risk_macro:        'Risk & Macro',
}
```
