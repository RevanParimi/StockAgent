// data.jsx — StockAgent prototype data layer
//
// TWO-LAYER STRATEGY:
//   Layer 1 (this file): mock data set synchronously on window.*
//                        — the app renders immediately with these values
//   Layer 2 (bootstrap): fetch /ui/bootstrap from the FastAPI server
//                        — if successful, live data overlays the mocks
//                        — if API is down, mocks remain as-is (offline-safe)
//
// The index.html inline script calls window.__bootstrap() after all scripts
// load and waits for it to resolve before mounting React.

// ─── MOCK DATA (always available, used as fallback) ──────────────────────

window.AGENTS = [
  { key:'sales_demand',       name:'Sales & Demand',       icon:'📊', weight:0.16, desc:'Tracks FADA/SIAM dispatches, EV registrations, dealer inventory.', enabled:true,  beginner:'How many cars are actually selling each month.' },
  { key:'fundamentals',       name:'Fundamentals',         icon:'📈', weight:0.18, desc:'Revenue & EBITDA delta, margin vs peers, FII/DII flows.',          enabled:true,  beginner:'Whether the company makes more money each quarter.' },
  { key:'pattern_analysis',   name:'Pattern Analysis',     icon:'🔍', weight:0.12, desc:'10-yr OHLCV, RSI/MACD/Bollinger, support/resistance.',             enabled:true,  beginner:'Reads the price chart for buying/selling pressure.' },
  { key:'raw_materials',      name:'Raw Materials',        icon:'⚙️', weight:0.09, desc:'Steel, aluminium, palladium, crude — input cost stack.',           enabled:true,  beginner:'How costly the metals & oil they buy are right now.' },
  { key:'sentiment',          name:'Sentiment',            icon:'💬', weight:0.04, desc:'News tone, mgmt commentary, Twitter/Reddit/YouTube spikes.',        enabled:true,  beginner:'What the news, social media & forums are saying.' },
  { key:'policy_regulatory',  name:'Policy & Regulatory',  icon:'📋', weight:0.09, desc:'FAME/EV subsidies, BS6 emissions, PLI scheme, state incentives.',  enabled:true,  beginner:'Government rules helping or hurting the company.' },
  { key:'competitive_intel',  name:'Competitive Intel',    icon:'🎯', weight:0.09, desc:'EV market share, model pipeline, JV/M&A, ADAS ratings.',           enabled:true,  beginner:'How rivals like Tata, Hyundai, Kia are doing.' },
  { key:'risk_macro',         name:'Risk & Macro',         icon:'⚠️', weight:0.13, desc:'INR/USD, crude, RBI repo, geopolitics, China supply chain.',       enabled:true,  beginner:'Big-picture risks: currency, oil, interest rates.' },
  { key:'valuation_catalyst', name:'Valuation & Catalyst', icon:'💎', weight:0.10, desc:'P/E vs history & peers, fair value, recovery catalysts.',          enabled:true,  beginner:'Whether the stock is cheap or expensive right now.' },
];

window.TICKERS = [
  { sym:'MARUTI',     name:'Maruti Suzuki India',   price:12_487.40, change: 1.42, score:0.82, verdict:'STRONG BUY', trend:'up'   },
  { sym:'TATAMOTORS', name:'Tata Motors',            price:  942.15,  change: 2.18, score:0.74, verdict:'BUY',        trend:'up'   },
  { sym:'M&M',        name:'Mahindra & Mahindra',   price: 2_854.60, change: 0.62, score:0.71, verdict:'BUY',        trend:'up'   },
  { sym:'BAJAJ-AUTO', name:'Bajaj Auto',             price: 8_945.10, change:-0.34, score:0.58, verdict:'NEUTRAL',   trend:'flat' },
  { sym:'HEROMOTOCO', name:'Hero MotoCorp',          price: 4_512.85, change:-1.18, score:0.48, verdict:'NEUTRAL',   trend:'down' },
  { sym:'EICHERMOT',  name:'Eicher Motors',          price: 4_896.20, change: 0.85, score:0.66, verdict:'BUY',       trend:'up'   },
  { sym:'TVSMOTORS',  name:'TVS Motor Company',      price: 2_385.45, change: 1.92, score:0.69, verdict:'BUY',       trend:'up'   },
  { sym:'ASHOKLEY',   name:'Ashok Leyland',          price:  248.30,  change:-0.41, score:0.52, verdict:'NEUTRAL',   trend:'flat' },
];

window.WATCHLIST = ['MARUTI','TATAMOTORS','M&M','BAJAJ-AUTO','EICHERMOT'];

window.MARKET_TODAY = {
  pulse: 'Mostly green',
  oneLiner: 'Auto sector broadly positive. Run an analysis to see live intelligence here.',
  autoChange: 1.24,
  drivers: [
    { kind:'good', label:'FADA April retail dispatch +14% YoY',            impact:'Sales & Demand',  tickers:['MARUTI','M&M','TATAMOTORS'] },
    { kind:'good', label:'Crude (Brent) -1.4% to $86 — input cost relief', impact:'Raw Materials',   tickers:['MARUTI','TATAMOTORS','BAJAJ-AUTO'] },
    { kind:'mid',  label:'INR weakens 0.18% vs USD — mild import drag',    impact:'Risk & Macro',    tickers:['MARUTI','HEROMOTOCO'] },
    { kind:'bad',  label:'Hero MotoCorp Q4 dispatch miss — guidance cut',  impact:'Sentiment',       tickers:['HEROMOTOCO'] },
  ],
  sectorChange: [
    { name:'Auto',    pct: 1.24 },
    { name:'IT',      pct:-0.67 },
    { name:'Banking', pct:-0.12 },
    { name:'Pharma',  pct: 0.41 },
    { name:'Energy',  pct: 0.88 },
    { name:'FMCG',    pct: 0.22 },
  ],
};

window.MARKET_MONTH = {
  pulse: 'Building strength',
  oneLiner: 'EV momentum + PLI benefits flowing through margins. Watch crude & INR.',
  drivers: [
    { kind:'good', label:'PLI auto disbursements at 18-mo high',       impact:'Fundamentals',    tickers:['MARUTI','M&M','TATAMOTORS'] },
    { kind:'good', label:'EV registrations +38% MoM (Vahan)',          impact:'Sales & Demand',  tickers:['TATAMOTORS','M&M'] },
    { kind:'good', label:'Steel prices -6% — margin tailwind',         impact:'Raw Materials',   tickers:['MARUTI','TATAMOTORS','ASHOKLEY'] },
    { kind:'mid',  label:'FII flows into autos +₹2,400 Cr',            impact:'Fundamentals',    tickers:['MARUTI','TATAMOTORS'] },
    { kind:'bad',  label:'Semiconductor tightness for ADAS variants',  impact:'Competitive Intel', tickers:['MARUTI','M&M'] },
  ],
  agentVotes: window.AGENTS.map(a => ({
    n: a.name, v: 0.60, k: 'mid'
  })),
};

window.TRENDING = [
  { sym:'TATAMOTORS', why:'EV order book + Tiago.ev launch buzz', delta:'+2.18%', volume:'2.4× avg' },
  { sym:'MARUTI',     why:'Brezza & Grand Vitara dispatch beat',  delta:'+1.42%', volume:'1.8× avg' },
  { sym:'TVSMOTORS',  why:'Premium 2W mix improving',             delta:'+1.92%', volume:'1.6× avg' },
  { sym:'M&M',        why:'Thar.e teaser + tractor margins',      delta:'+0.62%', volume:'1.3× avg' },
];

window.SUGGESTIONS = [
  { sym:'EICHERMOT', reason:'Premium 2W tailwinds + RE 650 launch',     score:0.66, why:'Matches your "growth + brand moat" picks' },
  { sym:'ASHOKLEY',  reason:'Infra spend cycle, M&HCV demand recovery',  score:0.52, why:'Cyclical play on capex you usually like' },
  { sym:'TVSMOTORS', reason:'EV scooter share gain (iQube)',             score:0.69, why:'EV exposure outside your existing list' },
];

window.CATEGORIES = [
  { key:'ev',      icon:'⚡', label:'EV-first',     count:5, color:'#7c3aed' },
  { key:'mass',    icon:'🚗', label:'Mass-market',  count:8, color:'#0891b2' },
  { key:'premium', icon:'💎', label:'Premium',      count:4, color:'#d97706' },
  { key:'cv',      icon:'🚛', label:'Commercial',   count:3, color:'#16a34a' },
  { key:'2w',      icon:'🏍️', label:'Two-wheelers', count:4, color:'#dc2626' },
  { key:'parts',   icon:'⚙️', label:'Auto-parts',   count:6, color:'#475569' },
];

window.NIFTY_AUTO_HISTORY = (() => {
  const out = [];
  let v = 22_650;
  for (let i = 0; i < 30; i++) {
    v += (Math.sin(i / 3) * 60) + ((Math.random() - 0.45) * 90);
    out.push(Math.round(v));
  }
  return out;
})();

window.CHAT_SEEDS = [
  'Why is MARUTI rated STRONG BUY today?',
  'What does the Sales & Demand agent see this week?',
  'Compare Tata Motors vs M&M for EV exposure',
  'Which agent should I trust most for short-term moves?',
];

window.AGENT_SOURCES = {
  sales_demand:       ['Serper news','FADA','SIAM','Vahan'],
  fundamentals:       ['yfinance','Serper news','NSE filings'],
  pattern_analysis:   ['yfinance OHLCV','RSI/MACD/BB (C++)'],
  raw_materials:      ['yfinance commodities','Serper news'],
  sentiment:          ['Serper news','Twitter/Reddit','YouTube'],
  policy_regulatory:  ['Tavily','Serper','gov circulars'],
  competitive_intel:  ['Serper news','peer baskets'],
  risk_macro:         ['yfinance INR/crude','macro cache'],
  valuation_catalyst: ['LLM knowledge','peer P/E','price targets'],
};

// ─── LIVE BOOTSTRAP (overlays mocks with real API data) ──────────────────

window.__LIVE_DATA = false;   // flipped to true when bootstrap succeeds

window.__bootstrap = async function () {
  try {
    const res = await fetch('/ui/bootstrap', { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error(`/ui/bootstrap → ${res.status}`);
    const data = await res.json();

    // Overlay each window.* key from the API response
    const keys = [
      'AGENTS','TICKERS','WATCHLIST',
      'MARKET_TODAY','MARKET_MONTH',
      'NIFTY_AUTO_HISTORY',
      'TRENDING','SUGGESTIONS',
      'CATEGORIES','CHAT_SEEDS','AGENT_SOURCES',
    ];
    keys.forEach(k => { if (data[k] !== undefined) window[k] = data[k]; });

    window.__LIVE_DATA = true;
    console.info('[StockAgent] Live data loaded from API ✓');
  } catch (err) {
    console.warn('[StockAgent] API unavailable — using mock data.', err.message);
  }
};

// ─── LIVE CHAT (replaces the mock reply function) ─────────────────────────

window.__sendChat = async function (message) {
  try {
    const res = await fetch('/ui/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) throw new Error(`/ui/chat → ${res.status}`);
    const { reply } = await res.json();
    return reply || 'No reply from assistant.';
  } catch (err) {
    // Fall back to the mock reply if the server is unavailable
    return window.__mockReply(message);
  }
};

window.__mockReply = function (q) {
  const ql = q.toLowerCase();
  if (ql.includes('maruti'))  return "MARUTI's latest score reflects strong sales dispatch data and easing raw material costs. Check Sales & Demand and Raw Materials agents.";
  if (ql.includes('tata') || ql.includes('tatamotors')) return "TATAMOTORS is driven by EV order book strength and JLR margin recovery. Watch the China supply chain risk in Risk & Macro.";
  if (ql.includes('agent') && ql.includes('trust')) return "For short-term moves, Pattern Analysis and Sentiment lead. For 3–6 month horizons, Fundamentals and Sales & Demand carry more weight.";
  if (ql.includes('compare')) return "TATAMOTORS leads on EV pure-play exposure. M&M has the diversified moat (SUVs + tractors + Thar.e). Both rated BUY; M&M has lower beta.";
  return "Ask me about a specific ticker like MARUTI or BAJAJ-AUTO, or about an agent like Sales & Demand.";
};
