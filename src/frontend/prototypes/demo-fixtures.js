/* demo-fixtures.js — sample screen data for demo mode ONLY.
 *
 * Demo mode is explicit: the page is opened with ?demo=1 (index.html sets
 * window.saDemoMode before this file runs). It exists for the layout audit
 * (scripts/ui_responsive_audit.mjs) and for showing the screens without a
 * database. Every value below is invented. The app shows a "Sample data"
 * banner in this mode and data.jsx then makes no market API call.
 *
 * Outside demo mode this file defines nothing: no screen may fall back to
 * these values when a request fails (PR-001). A failed request shows
 * "unavailable". This is the only prototype file allowed to hold sample
 * tickers, prices, index levels or percentage moves; the guard test
 * tests/unit/test_ui_no_invented_figures_pr001.py enforces that.
 */
(function () {
  if (!window.saDemoMode) return;

  // Deterministic sample series ending at `end` (no Math.random, so the
  // audit's screenshots are stable run to run).
  function series(points, start, end, wobble) {
    const out = [];
    for (let i = 0; i < points; i++) {
      const t = points === 1 ? 1 : i / (points - 1);
      out.push(Math.round(start + (end - start) * t + Math.sin(i / 2.3) * wobble));
    }
    out[out.length - 1] = end;
    return out;
  }

  const NIFTY_NOW = 24850;
  const PORTFOLIO_NOW = 4_82_350;

  window.saDemoFixtures = {
    AGENTS: [
      { key:'sales_demand',      name:'Sales & Demand',     icon:'📊', weight:0.18, desc:'Tracks FADA/SIAM dispatches, EV registrations, dealer inventory.', enabled:true,  beginner:'How many cars are actually selling each month.' },
      { key:'fundamentals',      name:'Fundamentals',       icon:'📈', weight:0.20, desc:'Revenue & EBITDA delta, margin vs peers, FII/DII flows.',          enabled:true,  beginner:'Whether the company makes more money each quarter.' },
      { key:'pattern_analysis',  name:'Pattern Analysis',   icon:'🔍', weight:0.13, desc:'10-yr OHLCV, RSI/MACD/Bollinger, support/resistance.',             enabled:true,  beginner:'Reads the price chart for buying/selling pressure.' },
      { key:'raw_materials',     name:'Raw Materials',      icon:'⚙️', weight:0.10, desc:'Steel, aluminium, palladium, crude — input cost stack.',           enabled:true,  beginner:'How costly the metals & oil they buy are right now.' },
      { key:'sentiment',         name:'Sentiment',          icon:'💬', weight:0.04, desc:'News tone, mgmt commentary, Twitter/Reddit/YouTube spikes.',        enabled:true,  beginner:'What the news, social media & forums are saying.' },
      { key:'policy_regulatory', name:'Policy & Regulatory', icon:'📋', weight:0.10, desc:'FAME/EV subsidies, BS6 emissions, PLI scheme, state incentives.',  enabled:true,  beginner:'Government rules helping or hurting the company.' },
      { key:'competitive_intel', name:'Competitive Intel',  icon:'🎯', weight:0.10, desc:'EV market share, model pipeline, JV/M&A, ADAS ratings.',           enabled:true,  beginner:'How rivals like Tata, Hyundai, Kia are doing.' },
      { key:'risk_macro',        name:'Risk & Macro',       icon:'⚠️', weight:0.15, desc:'INR/USD, crude, RBI repo, geopolitics, China supply chain.',       enabled:false, beginner:'Big-picture risks: currency, oil, interest rates.' },
      { key:'valuation_catalyst', name:'Valuation & Catalyst', icon:'💎', weight:0.00, desc:'P/E vs history & peers, fair value, recovery catalysts.',         enabled:false, beginner:'Whether the stock is cheap or expensive right now.' },
    ],

    TICKERS: [
      { sym:'MARUTI',     name:'Maruti Suzuki India', price:12_487.40, change: 1.42, score:0.82, verdict:'STRONG BUY', trend:'up',   hasData:true },
      { sym:'TATAMOTORS', name:'Tata Motors',         price:   942.15, change: 2.18, score:0.74, verdict:'BUY',        trend:'up',   hasData:true },
      { sym:'M&M',        name:'Mahindra & Mahindra', price: 2_854.60, change: 0.62, score:0.71, verdict:'BUY',        trend:'up',   hasData:true },
      { sym:'BAJAJ-AUTO', name:'Bajaj Auto',          price: 8_945.10, change:-0.34, score:0.58, verdict:'NEUTRAL',    trend:'flat', hasData:true },
      { sym:'HEROMOTOCO', name:'Hero MotoCorp',       price: 4_512.85, change:-1.18, score:0.48, verdict:'NEUTRAL',    trend:'down', hasData:true },
      { sym:'EICHERMOT',  name:'Eicher Motors',       price: 4_896.20, change: 0.85, score:0.66, verdict:'BUY',        trend:'up',   hasData:true },
      { sym:'TVSMOTORS',  name:'TVS Motor Company',   price: 2_385.45, change: 1.92, score:0.69, verdict:'BUY',        trend:'up',   hasData:true },
      { sym:'ASHOKLEY',   name:'Ashok Leyland',       price:   248.30, change:-0.41, score:0.52, verdict:'NEUTRAL',    trend:'flat', hasData:true },
    ],

    WATCHLIST: ['MARUTI', 'TATAMOTORS', 'M&M', 'BAJAJ-AUTO', 'EICHERMOT'],

    MARKET_TODAY: {
      pulse: 'Mostly green',
      oneLiner: 'Auto sector up 1.2% on dispatch beat. RBI on hold, crude cooling.',
      freshness: { label: 'Sample data', runAt: null, isStale: false },
      drivers: [
        { kind:'good', label:'FADA April retail dispatch +14% YoY',            impact:'Sales & Demand', tickers:['MARUTI','M&M','TATAMOTORS'] },
        { kind:'good', label:'Crude (Brent) -1.4% to $86 — input cost relief', impact:'Raw Materials',  tickers:['MARUTI','TATAMOTORS','BAJAJ-AUTO'] },
        { kind:'mid',  label:'INR weakens 0.18% vs USD — mild import drag',    impact:'Risk & Macro',   tickers:['MARUTI','HEROMOTOCO'] },
        { kind:'bad',  label:'Hero MotoCorp Q4 dispatch miss — guidance cut', impact:'Sentiment',      tickers:['HEROMOTOCO'] },
      ],
      sectorChange: [
        { name:'Auto',    pct: 1.24 },
        { name:'IT',      pct:-0.67 },
        { name:'Banking', pct:-0.12 },
        { name:'Pharma',  pct: 0.41 },
        { name:'Energy',  pct: 0.88 },
        { name:'FMCG',    pct: 0.22 },
      ],
    },

    MARKET_MONTH: {
      pulse: 'Building strength',
      oneLiner: 'EV momentum + PLI benefits flowing through margins. Watch crude & INR.',
      freshness: { label: 'Sample data', runAt: null, isStale: false },
      drivers: [
        { kind:'good', label:'PLI auto disbursements at 18-mo high',      impact:'Fundamentals',      tickers:['MARUTI','M&M','TATAMOTORS'] },
        { kind:'good', label:'EV registrations +38% MoM (Vahan)',         impact:'Sales & Demand',    tickers:['TATAMOTORS','M&M'] },
        { kind:'good', label:'Steel prices -6% — margin tailwind',        impact:'Raw Materials',     tickers:['MARUTI','TATAMOTORS','ASHOKLEY'] },
        { kind:'mid',  label:'FII flows into autos +₹2,400 Cr',           impact:'Fundamentals',      tickers:['MARUTI','TATAMOTORS'] },
        { kind:'bad',  label:'Semiconductor tightness for ADAS variants', impact:'Competitive Intel', tickers:['MARUTI','M&M'] },
      ],
      agentVotes: [
        { n:'Sales & Demand',      v:0.78, k:'good' },
        { n:'Fundamentals',        v:0.72, k:'good' },
        { n:'Pattern Analysis',    v:0.65, k:'good' },
        { n:'Sentiment',           v:0.61, k:'good' },
        { n:'Policy & Regulatory', v:0.58, k:'mid' },
        { n:'Raw Materials',       v:0.55, k:'mid' },
        { n:'Competitive Intel',   v:0.52, k:'mid' },
        { n:'Risk & Macro',        v:0.42, k:'bad' },
      ],
    },

    // The hero's market line and the home index box (same shapes as
    // /ui/bootstrap's NIFTY50 and /ui/nifty-ranges).
    NIFTY50: { name:'Nifty 50', value: NIFTY_NOW, changePct: 0.48, asOf: '2026-07-30' },
    NIFTY50_RANGES: {
      '1W': { index:'Nifty 50', range:'1W', label:'1 week',   points: series(6,   24690, NIFTY_NOW, 40),  change: 0.65, value: NIFTY_NOW, asOf:'2026-07-30', from:'2026-07-23' },
      '1M': { index:'Nifty 50', range:'1M', label:'1 month',  points: series(22,  24380, NIFTY_NOW, 70),  change: 1.93, value: NIFTY_NOW, asOf:'2026-07-30', from:'2026-06-30' },
      '3M': { index:'Nifty 50', range:'3M', label:'3 months', points: series(63,  23700, NIFTY_NOW, 120), change: 4.85, value: NIFTY_NOW, asOf:'2026-07-30', from:'2026-04-30' },
      '6M': { index:'Nifty 50', range:'6M', label:'6 months', points: series(124, 22800, NIFTY_NOW, 160), change: 8.99, value: NIFTY_NOW, asOf:'2026-07-30', from:'2026-01-29' },
      '1Y': { index:'Nifty 50', range:'1Y', label:'1 year',   points: series(248, 20300, NIFTY_NOW, 220), change:22.41, value: NIFTY_NOW, asOf:'2026-07-30', from:'2025-07-30' },
    },

    TRENDING: [
      { sym:'TATAMOTORS', name:'Tata Motors',         score:0.74, delta: 0.06, direction:'up',   verdict:'BUY',        why:'EV order book + Tiago.ev launch buzz' },
      { sym:'MARUTI',     name:'Maruti Suzuki India', score:0.82, delta: 0.04, direction:'up',   verdict:'STRONG BUY', why:'Brezza & Grand Vitara dispatch beat' },
      { sym:'TVSMOTORS',  name:'TVS Motor Company',   score:0.69, delta: 0.03, direction:'up',   verdict:'BUY',        why:'Premium 2W mix improving' },
      { sym:'M&M',        name:'Mahindra & Mahindra', score:0.71, delta:-0.02, direction:'down', verdict:'BUY',        why:'Thar.e teaser + tractor margins' },
    ],

    SUGGESTIONS: [
      { sym:'EICHERMOT', reason:'Premium 2W tailwinds + RE 650 launch',     score:0.66, why:'Matches your "growth + brand moat" picks' },
      { sym:'ASHOKLEY',  reason:'Infra spend cycle, M&HCV demand recovery', score:0.52, why:'Cyclical play on capex you usually like' },
      { sym:'TVSMOTORS', reason:'EV scooter share gain (iQube)',            score:0.69, why:'EV exposure outside your existing list' },
    ],

    CATEGORIES: [
      { key:'ev',      icon:'⚡',  label:'EV-first',     count:5, color:'#7c3aed', tickers:['TATAMOTORS','M&M','TVSMOTORS','BAJAJ-AUTO','HEROMOTOCO'] },
      { key:'mass',    icon:'🚗', label:'Mass-market',  count:8, color:'#0891b2', tickers:['MARUTI','TATAMOTORS','M&M','BAJAJ-AUTO','HEROMOTOCO','TVSMOTORS','EICHERMOT','ASHOKLEY'] },
      { key:'premium', icon:'💎', label:'Premium',      count:4, color:'#d97706', tickers:['MARUTI','EICHERMOT','BAJAJ-AUTO','M&M'] },
      { key:'cv',      icon:'🚛', label:'Commercial',   count:3, color:'#16a34a', tickers:['ASHOKLEY','TATAMOTORS','EICHERMOT'] },
      { key:'2w',      icon:'🏍️', label:'Two-wheelers', count:4, color:'#dc2626', tickers:['HEROMOTOCO','TVSMOTORS','BAJAJ-AUTO','EICHERMOT'] },
      { key:'parts',   icon:'⚙️', label:'Auto-parts',   count:6, color:'#475569', tickers:['BOSCHLTD','MOTHERSON','APOLLOTYRE','CEATLTD','MRF','BALKRISIND'] },
    ],

    CHAT_SEEDS: [
      'Why is MARUTI rated STRONG BUY today?',
      'What does the Sales & Demand agent see this week?',
      'Compare Tata Motors vs M&M for EV exposure',
      'Which agent should I trust most for short-term moves?',
    ],

    // ---------- PORTFOLIO (the portfolio page in demo mode) ----------
    PORTFOLIO: {
      totalValue: PORTFOLIO_NOW,
      totalCost:  4_24_800,
      dayChange:  +5_240,
      dayChangePct: +1.10,
      cash:        38_400,
      holdings: [
        { sym:'MARUTI',     qty: 8,  avgPrice:11_240.00, currentPrice:12_487.40, agentScore:0.82, verdict:'STRONG BUY' },
        { sym:'TATAMOTORS', qty: 45, avgPrice:  812.50,  currentPrice:  942.15,  agentScore:0.74, verdict:'BUY' },
        { sym:'M&M',        qty: 12, avgPrice: 2_780.00, currentPrice: 2_854.60, agentScore:0.71, verdict:'BUY' },
        { sym:'BAJAJ-AUTO', qty:  6, avgPrice: 9_120.00, currentPrice: 8_945.10, agentScore:0.58, verdict:'NEUTRAL' },
        { sym:'EICHERMOT',  qty:  4, avgPrice: 4_350.00, currentPrice: 4_896.20, agentScore:0.66, verdict:'BUY' },
      ],
      recentActivity: [
        { kind:'buy',   sym:'EICHERMOT',  qty: 2, price:4_882.40, t:'Today, 10:42 AM' },
        { kind:'agent', sym:'BAJAJ-AUTO', text:'Verdict downgraded BUY → NEUTRAL', t:'Yesterday' },
        { kind:'sell',  sym:'TVSMOTORS',  qty:10, price:2_410.20, t:'2 days ago' },
        { kind:'agent', sym:'MARUTI',     text:'Pattern Analysis flagged breakout above ₹12,400', t:'3 days ago' },
        { kind:'buy',   sym:'TATAMOTORS', qty:15, price:  890.00, t:'4 days ago' },
      ],
      alerts: [
        { sym:'BAJAJ-AUTO', kind:'warn', text:'Position now -1.9%. Risk & Macro flagged INR pressure.' },
        { sym:'MARUTI',     kind:'good', text:'Strongest pick — Sales & Demand at 0.84 (top 5%).' },
        { sym:'TATAMOTORS', kind:'good', text:'EV order book +22% MoM, agent target ₹1,020.' },
      ],
    },

    PORTFOLIO_RANGES: {
      '1W': { points: series(7,   4_75_200, PORTFOLIO_NOW, 1500), label:'1 week',   change:+1.50 },
      '1M': { points: series(30,  4_24_800, PORTFOLIO_NOW, 2200), label:'1 month',  change:+13.55 },
      '3M': { points: series(60,  3_98_400, PORTFOLIO_NOW, 2800), label:'3 months', change:+21.07 },
      '6M': { points: series(120, 3_72_500, PORTFOLIO_NOW, 3400), label:'6 months', change:+29.49 },
      '1Y': { points: series(180, 3_18_200, PORTFOLIO_NOW, 4200), label:'1 year',   change:+51.59 },
    },

    // Same shape as GET /ui/learnings: dated verdict changes newest first, then
    // forecast misses; no money figure.
    PORTFOLIO_LEARNINGS: {
      items: [
        { id:'turned-bullish-tatamotors', kind:'turned-bullish', severity:'low', sym:'TATAMOTORS',
          title:'TATAMOTORS: SELL → BUY', when:'2026-07-29',
          what:'EV order book is ahead of plan and the Tiago.ev launch is pulling dealer demand forward.',
          detail:'Score moved +0.21 → now BUY',
          agentSnapshot:[{ n:'Sales & Demand', v:0.82 }, { n:'Fundamentals', v:0.79 }, { n:'Sentiment', v:0.74 }] },
        { id:'turned-bearish-bajaj-auto', kind:'turned-bearish', severity:'med', sym:'BAJAJ-AUTO',
          title:'BAJAJ-AUTO: BUY → SELL', when:'2026-07-27',
          what:'Export volumes fell for a second month and the rupee move adds margin pressure.',
          detail:'Score moved -0.18 → now SELL',
          agentSnapshot:[{ n:'Risk & Macro', v:0.41 }, { n:'Fundamentals', v:0.45 }, { n:'Pattern Analysis', v:0.38 }] },
        { id:'bullish-maruti', kind:'bullish', severity:'low', sym:'MARUTI',
          title:'MARUTI: BUY → STRONG BUY', when:'2026-07-25',
          what:'Dispatch beat across utility vehicles; margins held despite the commodity cycle.',
          detail:'Score moved +0.06 → now STRONG BUY',
          agentSnapshot:[{ n:'Sales & Demand', v:0.84 }, { n:'Fundamentals', v:0.81 }, { n:'Competitive Intel', v:0.70 }] },
        { id:'rl-eichermot-2026-07-24', kind:'forecast-miss', severity:'high', sym:'EICHERMOT',
          title:'RL flag: model bias on EICHERMOT', when:'2026-07-24',
          what:'Agent fundamentals flagged as primary miss. Direction correct: False',
          detail:'Miss type: model_bias', agentSnapshot:[] },
      ],
    },
  };
})();
