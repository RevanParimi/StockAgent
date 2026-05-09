// RL Monitor data layer — mock data + /ui/rl/* API fetch
// All data exposed on window.RL_* globals, same pattern as data.jsx

window.RL_TICKERS = [
  { sym:'MARUTI',     name:'Maruti Suzuki',     color:'#0891b2', enabled:true,  has_envelope:true,  has_weights:true  },
  { sym:'TATAMOTORS', name:'Tata Motors',        color:'#7c3aed', enabled:true,  has_envelope:true,  has_weights:true  },
  { sym:'M&M',        name:'Mahindra & Mahindra',color:'#16a34a', enabled:true,  has_envelope:true,  has_weights:false },
  { sym:'HEROMOTOCO', name:'Hero MotoCorp',      color:'#d97706', enabled:true,  has_envelope:false, has_weights:false },
  { sym:'BAJAJ-AUTO', name:'Bajaj Auto',         color:'#dc2626', enabled:true,  has_envelope:true,  has_weights:true  },
];

// Mock summary per ticker
window.RL_SUMMARIES = {
  MARUTI: {
    available: true,
    ticker: 'MARUTI',
    cycle_id: 'cycle-2025-04',
    direction_accuracy_pct: 85.7,
    total_entries: 21,
    weight_version: 8,
    lesson_count: 14,
    top_miss_factor: 'macro_surprise',
    current_verdict: 'STRONG BUY',
    streak_days: 4,
    reversion_prior: 0.62,
    avg_price_error_pct: 0.22,
    direction_hits: 18,
    total_days: 21,
  },
  TATAMOTORS: {
    available: true,
    ticker: 'TATAMOTORS',
    cycle_id: 'cycle-2025-04',
    direction_accuracy_pct: 78.6,
    total_entries: 14,
    weight_version: 6,
    lesson_count: 9,
    top_miss_factor: 'sentiment_flip',
    current_verdict: 'BUY',
    streak_days: 2,
    reversion_prior: 0.55,
    avg_price_error_pct: 0.38,
    direction_hits: 11,
    total_days: 14,
  },
  'M&M': {
    available: true,
    ticker: 'M&M',
    cycle_id: 'cycle-2025-04',
    direction_accuracy_pct: 72.2,
    total_entries: 18,
    weight_version: 4,
    lesson_count: 7,
    top_miss_factor: 'timing',
    current_verdict: 'BUY',
    streak_days: 1,
    reversion_prior: 0.50,
    avg_price_error_pct: 0.45,
    direction_hits: 13,
    total_days: 18,
  },
  'BAJAJ-AUTO': {
    available: true,
    ticker: 'BAJAJ-AUTO',
    cycle_id: 'cycle-2025-04',
    direction_accuracy_pct: 66.7,
    total_entries: 12,
    weight_version: 3,
    lesson_count: 5,
    top_miss_factor: 'magnitude',
    current_verdict: 'NEUTRAL',
    streak_days: 0,
    reversion_prior: 0.48,
    avg_price_error_pct: 0.61,
    direction_hits: 8,
    total_days: 12,
  },
};

// Generate mock prediction history for a ticker
function genPredictions(basePrice, n) {
  const days = [];
  let price = basePrice;
  const now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    const actual = price * (1 + (Math.random() - 0.49) * 0.02);
    const predicted = actual * (1 + (Math.random() - 0.5) * 0.008);
    const hit = Math.random() > 0.14;
    days.push({
      date: dateStr,
      predicted: Math.round(predicted * 100) / 100,
      actual: i === 0 ? null : Math.round(actual * 100) / 100,
      error_pct: i === 0 ? null : Math.abs((predicted - actual) / actual * 100).toFixed(2),
      direction_hit: i === 0 ? null : hit,
      confidence: 0.6 + Math.random() * 0.35,
      miss_type: (!hit && i > 0) ? ['direction_flip','macro_surprise','timing','magnitude'][Math.floor(Math.random()*4)] : null,
    });
    price = actual;
  }
  return days;
}

window.RL_PREDICTIONS = {
  MARUTI:     genPredictions(12487, 21),
  TATAMOTORS: genPredictions(942, 14),
  'M&M':      genPredictions(2854, 18),
  'BAJAJ-AUTO': genPredictions(8945, 12),
};

window.RL_WEIGHTS = {
  MARUTI: {
    available: true,
    ticker: 'MARUTI',
    base_weights:    { sales_demand:0.18, fundamentals:0.20, pattern_analysis:0.13, raw_materials:0.10, sentiment:0.04, policy_regulatory:0.10, competitive_intel:0.10, risk_macro:0.15 },
    current_weights: { sales_demand:0.20, fundamentals:0.22, pattern_analysis:0.12, raw_materials:0.09, sentiment:0.04, policy_regulatory:0.10, competitive_intel:0.09, risk_macro:0.14 },
    weight_history: [
      { version:8, date:'2025-04-28', reason:'Upweighted fundamentals after strong Q4 earnings beat.', weights: { sales_demand:0.20, fundamentals:0.22, pattern_analysis:0.12, raw_materials:0.09, sentiment:0.04, policy_regulatory:0.10, competitive_intel:0.09, risk_macro:0.14 } },
      { version:7, date:'2025-04-14', reason:'Downweighted raw_materials after crude normalised.', weights: { sales_demand:0.19, fundamentals:0.20, pattern_analysis:0.13, raw_materials:0.09, sentiment:0.05, policy_regulatory:0.10, competitive_intel:0.10, risk_macro:0.14 } },
      { version:6, date:'2025-03-31', reason:'Boosted sales_demand after FADA dispatch beat.', weights: { sales_demand:0.21, fundamentals:0.19, pattern_analysis:0.12, raw_materials:0.10, sentiment:0.05, policy_regulatory:0.10, competitive_intel:0.09, risk_macro:0.14 } },
    ],
  },
  TATAMOTORS: {
    available: true,
    ticker: 'TATAMOTORS',
    base_weights:    { sales_demand:0.18, fundamentals:0.20, pattern_analysis:0.13, raw_materials:0.10, sentiment:0.04, policy_regulatory:0.10, competitive_intel:0.10, risk_macro:0.15 },
    current_weights: { sales_demand:0.17, fundamentals:0.19, pattern_analysis:0.14, raw_materials:0.10, sentiment:0.06, policy_regulatory:0.10, competitive_intel:0.11, risk_macro:0.13 },
    weight_history: [
      { version:6, date:'2025-04-21', reason:'Boosted competitive_intel on JLR/EV market share data.', weights: { sales_demand:0.17, fundamentals:0.19, pattern_analysis:0.14, raw_materials:0.10, sentiment:0.06, policy_regulatory:0.10, competitive_intel:0.11, risk_macro:0.13 } },
    ],
  },
};

window.RL_MISSES = {
  MARUTI: {
    available: true,
    ticker: 'MARUTI',
    miss_type_counts: { direction_flip:1, macro_surprise:1, timing:1, magnitude:0, data_gap:0, data_stale:0, external_shock:0 },
    top_missed_factors: { macro_surprise:2, sentiment_reversal:1, crude_spike:1 },
    lesson_count: 14,
  },
  TATAMOTORS: {
    available: true,
    ticker: 'TATAMOTORS',
    miss_type_counts: { direction_flip:1, macro_surprise:0, timing:1, magnitude:1, data_gap:0, data_stale:0, external_shock:0 },
    top_missed_factors: { sentiment_flip:2, jlr_fx:1 },
    lesson_count: 9,
  },
};

// ── Live API fetch ────────────────────────────────────────────────────────────
window.__rlApiReady = false;

(async function loadRLData() {
  try {
    const res = await fetch('/ui/rl/tickers');
    if (!res.ok) return;
    const d = await res.json();
    if (d.tickers?.length) {
      window.RL_TICKERS = d.tickers;
      window.__rlApiReady = true;
    }
  } catch {
    // keep mock RL_TICKERS
  }
})();

// Per-ticker async loaders used by rl-monitor.jsx
window.rlFetch = async function(ticker) {
  const result = { summary: null, predictions: [], weights: null, misses: null };
  try {
    const [sumRes, predRes, wtRes, missRes] = await Promise.all([
      fetch(`/ui/rl/summary/${ticker}`),
      fetch(`/ui/rl/predictions/${ticker}`),
      fetch(`/ui/rl/weights/${ticker}`),
      fetch(`/ui/rl/misses/${ticker}`),
    ]);
    if (sumRes.ok)  { const d = await sumRes.json();  if (d.available) result.summary     = d; }
    if (predRes.ok) { const d = await predRes.json(); if (d.available) result.predictions = d.days ?? []; }
    if (wtRes.ok)   { const d = await wtRes.json();   if (d.available) result.weights     = d; }
    if (missRes.ok) { const d = await missRes.json(); if (d.available) result.misses      = d; }
  } catch {
    // keep mock data
  }
  return result;
};
