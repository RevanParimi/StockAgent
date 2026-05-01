// Data module — mocks mirrored from frontend/src/mocks/sampleReport.ts

const AGENT_KEYS = [
  'sales_demand', 'fundamentals', 'pattern_analysis', 'raw_materials',
  'sentiment', 'policy_regulatory', 'competitive_intel', 'risk_macro',
];

const AGENT_LABELS = {
  sales_demand:      'Sales & Demand',
  fundamentals:      'Fundamentals',
  pattern_analysis:  'Pattern Analysis',
  raw_materials:     'Raw Materials',
  sentiment:         'Sentiment',
  policy_regulatory: 'Policy & Regulatory',
  competitive_intel: 'Competitive Intel',
  risk_macro:        'Risk & Macro',
};

const AGENT_ICONS = {
  sales_demand:      '📊',
  fundamentals:      '📈',
  pattern_analysis:  '🔍',
  raw_materials:     '⚙️',
  sentiment:         '💬',
  policy_regulatory: '📋',
  competitive_intel: '🎯',
  risk_macro:        '⚠️',
};

const TICKER_NAMES = {
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
};

const sampleReport = {
  ticker: 'MARUTI',
  company_name: 'Maruti Suzuki India Ltd',
  final_score: 0.82,
  verdict: 'STRONG BUY',
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
  conviction_drivers: [
    'Strong Q4 FY26 dispatch growth driven by SUV segment leadership',
    'PLI scheme benefits starting to reflect in margin expansion',
    'EV transition well-managed with Arena EV lineup pipeline',
    'FII/DII inflows into auto sector at 18-month high',
    'Healthy dealer inventory levels at 28 days (below 35-day caution threshold)',
  ],
  top_risks: [
    'INR weakness vs USD increases import component costs by ~3%',
    'Crude oil above $90/bbl compresses consumer purchasing power',
    'Competition from Hyundai/Kia in premium SUV segment intensifying',
    'Semiconductor supply tightness for ADAS-equipped variants',
  ],
  conflicts_resolved: [
    'Pattern Analysis (bearish RSI divergence, 0.72) vs Fundamentals (strong Q4, 0.79): LLM resolved in favor of Fundamentals given upcoming earnings catalyst',
  ],
  investment_thesis:
    "Maruti Suzuki remains the structural beneficiary of India's four-wheeler penetration story, commanding 42% market share in a market growing at 8% CAGR. The company's CNG leadership, combined with an imminent transition to BEVs via the eVITARA platform, positions it uniquely for the next decade of Indian auto growth.\n\nNear-term, Q4 FY26 dispatches exceeded consensus by 6%, driven by the Brezza and Grand Vitara. Management has guided for 12% revenue growth in FY27, with EBITDA margins expanding 50–80bps through localization and PLI benefits. The balance sheet remains fortress-like with ₹38,000 Cr net cash.\n\nThe primary risk is the pace of EV adoption cannibalizing CNG volumes faster than management anticipates, and sustained crude above $90 suppressing rural demand. However, at 26× FY27 P/E vs. 5-year average of 29×, current valuation offers a reasonable entry for a 12–18 month horizon.",
  report_date: '2026-04-17',
  elapsed_seconds: 47,
};

// 30 history records (3-day spaced, most recent first)
const sampleHistory = (() => {
  const records = [];
  const base = new Date('2026-04-17');
  const scores = [
    0.82,0.81,0.80,0.83,0.79,0.78,0.80,0.77,0.76,0.78,
    0.75,0.74,0.76,0.73,0.75,0.77,0.74,0.72,0.73,0.75,
    0.76,0.78,0.77,0.79,0.80,0.78,0.79,0.81,0.80,0.82,
  ];
  scores.forEach((score, i) => {
    const d = new Date(base);
    d.setDate(d.getDate() - i * 3);
    const v = score >= 0.75 ? 'STRONG BUY' : score >= 0.60 ? 'BUY' : 'NEUTRAL';
    records.push({
      date: d.toISOString().split('T')[0],
      score,
      verdict: v,
    });
  });
  return records.reverse(); // chronological
})();

const marketIndices = [
  { name: 'NIFTY 50',    value: 22438.15, change:  0.42 },
  { name: 'SENSEX',      value: 74205.82, change:  0.38 },
  { name: 'BANK NIFTY',  value: 48192.60, change: -0.12 },
  { name: 'NIFTY AUTO',  value: 23117.44, change:  1.24 },
  { name: 'NIFTY IT',    value: 34928.05, change: -0.67 },
  { name: 'USD/INR',     value:    83.42, change:  0.08 },
  { name: 'CRUDE (BR)',  value:    87.12, change: -0.92 },
];

window.StockData = {
  AGENT_KEYS, AGENT_LABELS, AGENT_ICONS, TICKER_NAMES,
  sampleReport, sampleHistory, marketIndices,
};
