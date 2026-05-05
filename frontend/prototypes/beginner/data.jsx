// Mock data for beginner prototype — Indian autos per AGENT_DESIGN.md

window.AGENTS = [
  { key:'sales_demand',      name:'Sales & Demand',     icon:'📊', weight:0.18, desc:'Tracks FADA/SIAM dispatches, EV registrations, dealer inventory.', enabled:true,  beginner:'How many cars are actually selling each month.' },
  { key:'fundamentals',      name:'Fundamentals',       icon:'📈', weight:0.20, desc:'Revenue & EBITDA delta, margin vs peers, FII/DII flows.',          enabled:true,  beginner:'Whether the company makes more money each quarter.' },
  { key:'pattern_analysis',  name:'Pattern Analysis',   icon:'🔍', weight:0.13, desc:'10-yr OHLCV, RSI/MACD/Bollinger, support/resistance.',             enabled:true,  beginner:'Reads the price chart for buying/selling pressure.' },
  { key:'raw_materials',     name:'Raw Materials',      icon:'⚙️', weight:0.10, desc:'Steel, aluminium, palladium, crude — input cost stack.',           enabled:true,  beginner:'How costly the metals & oil they buy are right now.' },
  { key:'sentiment',         name:'Sentiment',          icon:'💬', weight:0.04, desc:'News tone, mgmt commentary, Twitter/Reddit/YouTube spikes.',        enabled:true,  beginner:'What the news, social media & forums are saying.' },
  { key:'policy_regulatory', name:'Policy & Regulatory', icon:'📋', weight:0.10, desc:'FAME/EV subsidies, BS6 emissions, PLI scheme, state incentives.',  enabled:true,  beginner:'Government rules helping or hurting the company.' },
  { key:'competitive_intel', name:'Competitive Intel',  icon:'🎯', weight:0.10, desc:'EV market share, model pipeline, JV/M&A, ADAS ratings.',           enabled:true,  beginner:'How rivals like Tata, Hyundai, Kia are doing.' },
  { key:'risk_macro',        name:'Risk & Macro',       icon:'⚠️', weight:0.15, desc:'INR/USD, crude, RBI repo, geopolitics, China supply chain.',       enabled:false, beginner:'Big-picture risks: currency, oil, interest rates.' },
  { key:'valuation_catalyst', name:'Valuation & Catalyst', icon:'💎', weight:0.00, desc:'P/E vs history & peers, fair value, recovery catalysts.',         enabled:false, beginner:'Whether the stock is cheap or expensive right now.' },
];

window.TICKERS = [
  { sym:'MARUTI',     name:'Maruti Suzuki India',        price:12_487.40, change: 1.42, score:0.82, verdict:'STRONG BUY', trend:'up'   },
  { sym:'TATAMOTORS', name:'Tata Motors',                price:  942.15,  change: 2.18, score:0.74, verdict:'BUY',         trend:'up'   },
  { sym:'M&M',        name:'Mahindra & Mahindra',        price: 2_854.60, change: 0.62, score:0.71, verdict:'BUY',         trend:'up'   },
  { sym:'BAJAJ-AUTO', name:'Bajaj Auto',                 price: 8_945.10, change:-0.34, score:0.58, verdict:'NEUTRAL',     trend:'flat' },
  { sym:'HEROMOTOCO', name:'Hero MotoCorp',              price: 4_512.85, change:-1.18, score:0.48, verdict:'NEUTRAL',     trend:'down' },
  { sym:'EICHERMOT',  name:'Eicher Motors',              price: 4_896.20, change: 0.85, score:0.66, verdict:'BUY',         trend:'up'   },
  { sym:'TVSMOTORS',  name:'TVS Motor Company',          price: 2_385.45, change: 1.92, score:0.69, verdict:'BUY',         trend:'up'   },
  { sym:'ASHOKLEY',   name:'Ashok Leyland',              price:  248.30,  change:-0.41, score:0.52, verdict:'NEUTRAL',     trend:'flat' },
];

window.WATCHLIST = ['MARUTI','TATAMOTORS','M&M','BAJAJ-AUTO','EICHERMOT'];

// Sub-tasks per agent (5 score dimensions per AGENT_DESIGN.md). Each is independently toggleable.
window.AGENT_TASKS = {
  sales_demand: [
    { key:'fada',     label:'FADA monthly retail dispatch',  source:'Serper · fada.in',          enabled:true,  beginner:'Tracks how many vehicles dealers actually sold last month.' },
    { key:'siam',     label:'SIAM dispatch data',            source:'Serper · siam.in',           enabled:true,  beginner:'Manufacturer-level wholesale dispatch numbers.' },
    { key:'vahan',    label:'EV Vahan registrations',        source:'Serper · vahan.parivahan',   enabled:true,  beginner:'Government registration data for electric vehicles.' },
    { key:'dealer',   label:'Dealer inventory channel check',source:'Serper · analyst notes',     enabled:true,  beginner:'Are dealerships overstocked or running thin?' },
    { key:'export',   label:'Export / Import (DGFT)',        source:'Serper · dgft.gov.in',       enabled:false, beginner:'Foreign demand for India-made vehicles.' },
    { key:'used',     label:'Used-car price index',          source:'Cars24 · CarDekho',          enabled:false, beginner:'Resale prices — early demand signal.' },
  ],
  fundamentals: [
    { key:'revenue',  label:'Revenue & EBITDA delta',        source:'yfinance quarterly',         enabled:true,  beginner:'Is the company earning more each quarter?' },
    { key:'margins',  label:'Margin vs sector peers',        source:'Serper · peer basket',       enabled:true,  beginner:'Does it keep more profit per rupee than rivals?' },
    { key:'orders',   label:'Order book pipeline',           source:'Serper · press releases',    enabled:true,  beginner:'How many cars are pre-booked but not yet delivered.' },
    { key:'attrition',label:'Attrition & headcount',         source:'Serper · annual reports',    enabled:false, beginner:'Are skilled people staying or leaving?' },
    { key:'flows',    label:'Promoter / FII / DII flow',     source:'yfinance institutional',     enabled:true,  beginner:'Are big investors buying or selling?' },
  ],
  pattern_analysis: [
    { key:'cycle',    label:'10-yr price cycle position',    source:'yfinance OHLCV',             enabled:true,  beginner:'Where are we in the long-term price cycle?' },
    { key:'rsi',      label:'RSI (14)',                       source:'C++ indicators',             enabled:true,  beginner:'Overbought / oversold momentum gauge.' },
    { key:'macd',     label:'MACD (12,26,9)',                 source:'C++ indicators',             enabled:true,  beginner:'Trend strength and direction shifts.' },
    { key:'bb',       label:'Bollinger Bands (20, 2σ)',       source:'C++ indicators',             enabled:true,  beginner:'Price stretched outside its normal range?' },
    { key:'support',  label:'Support / resistance zones',     source:'Derived from 52w',           enabled:true,  beginner:'Levels where buyers/sellers usually step in.' },
    { key:'corr',     label:'Peer correlation (Nifty Auto)',  source:'yfinance multi-ticker',      enabled:false, beginner:'How tightly it follows the auto index.' },
  ],
  raw_materials: [
    { key:'steel',    label:'Steel (SLX)',                    source:'yfinance',                   enabled:true,  beginner:'Steel cost — the biggest input for car bodies.' },
    { key:'alu',      label:'Aluminium (AA proxy)',           source:'yfinance',                   enabled:true,  beginner:'Aluminium cost — used in EV battery housings.' },
    { key:'pgm',      label:'Platinum / Palladium',           source:'yfinance PPLT, PALL',        enabled:true,  beginner:'Catalytic converter metals.' },
    { key:'crude',    label:'Crude / Polymer (CL=F, BZ=F)',  source:'yfinance',                   enabled:true,  beginner:'Oil price — drives plastics, paint, freight.' },
    { key:'power',    label:'Power tariff trend',             source:'Serper · state regulators',  enabled:false, beginner:'Cost of running factories.' },
  ],
  sentiment: [
    { key:'news',     label:'News NLP (Reuters/ET/BBG)',      source:'Serper news',                enabled:true,  beginner:'Tone of major news coverage.' },
    { key:'earnings', label:'Management tone (earnings)',     source:'Serper · transcripts',       enabled:true,  beginner:'How confident management sounds on calls.' },
    { key:'social',   label:'Twitter / Reddit',               source:'Serper · social',            enabled:false, beginner:'What retail investors are saying.' },
    { key:'youtube',  label:'YouTube review spikes',          source:'Serper · YT search',         enabled:false, beginner:'Sudden interest in a model launch.' },
    { key:'feedback', label:'Dealer / consumer feedback',     source:'Serper · complaints',        enabled:false, beginner:'On-the-ground customer satisfaction.' },
  ],
  policy_regulatory: [
    { key:'fame',     label:'FAME / EV subsidy',              source:'Tavily · gov circulars',     enabled:true,  beginner:'Government cash incentives for EVs.' },
    { key:'emissions',label:'BS6 / CAFE emission norms',      source:'Tavily',                     enabled:true,  beginner:'Pollution rules — affects engine R&D cost.' },
    { key:'budget',   label:'Union Budget duties',            source:'Serper · budget docs',       enabled:true,  beginner:'Import / GST changes from the budget.' },
    { key:'pli',      label:'PLI scheme disbursements',       source:'Serper · DPIIT',             enabled:true,  beginner:'Production-linked subsidies for local mfg.' },
    { key:'state',    label:'State EV incentives',            source:'Tavily · state portals',     enabled:false, beginner:'State-by-state EV registration discounts.' },
  ],
  competitive_intel: [
    { key:'evshare',  label:'EV market share',                source:'Serper · Vahan',             enabled:true,  beginner:'Slice of EV sales going to this company.' },
    { key:'pipeline', label:'New model pipeline',             source:'Serper · auto press',        enabled:true,  beginner:'What launches are coming next.' },
    { key:'jvs',      label:'JV / acquisitions',              source:'Serper · M&A news',          enabled:true,  beginner:'Strategic partnerships and buyouts.' },
    { key:'adas',     label:'ADAS / safety ratings',          source:'Serper · NCAP',              enabled:false, beginner:'Self-driving features and crash ratings.' },
    { key:'position', label:'Competitive positioning',        source:'Serper · analyst',           enabled:true,  beginner:'Where it ranks vs Tata, Hyundai, Kia.' },
  ],
  risk_macro: [
    { key:'inrcrude', label:'INR/USD & crude exposure',       source:'yfinance INR=X, CL=F',       enabled:true,  beginner:'How currency & oil moves hit the company.' },
    { key:'commod',   label:'Commodity prices',               source:'yfinance SLX, AA',           enabled:true,  beginner:'Steel and aluminium swings.' },
    { key:'rbi',      label:'RBI repo / EMI impact',          source:'Static · RBI',               enabled:true,  beginner:'Loan EMIs — drives car affordability.' },
    { key:'policy',   label:'Emission policy risk',           source:'Cached macro',               enabled:false, beginner:'Surprise pollution-rule tightening.' },
    { key:'geopol',   label:'Global geopolitical risk',       source:'Cached macro',               enabled:true,  beginner:'Wars, China supply chain, FII outflows.' },
  ],
  valuation_catalyst: [
    { key:'pe5y',     label:'P/E vs 5yr history',             source:'LLM knowledge',              enabled:true,  beginner:'Is the stock cheap vs its own past?' },
    { key:'peer',     label:'P/E vs peer median',             source:'LLM knowledge',              enabled:true,  beginner:'Is it cheap vs Tata, M&M, Bajaj?' },
    { key:'reason',   label:'Discount reason clarity',        source:'LLM knowledge',              enabled:false, beginner:'Why is it cheap — fixable or structural?' },
    { key:'catalyst', label:'Catalyst strength',              source:'LLM knowledge',              enabled:true,  beginner:'What event could re-rate the stock.' },
    { key:'target',   label:'Price target confidence',        source:'LLM knowledge',              enabled:false, beginner:'How confident the model is in the upside.' },
  ],
};

window.MARKET_TODAY = {
  pulse: 'Mostly green',
  oneLiner: 'Auto sector up 1.2% on dispatch beat. RBI on hold, crude cooling.',
  drivers: [
    { tag:'Today', kind:'good', label:'FADA April retail dispatch +14% YoY',         impact:'Sales & Demand',     tickers:['MARUTI','M&M','TATAMOTORS'] },
    { tag:'Today', kind:'good', label:'Crude (Brent) -1.4% to $86 — input cost relief', impact:'Raw Materials',    tickers:['MARUTI','TATAMOTORS','BAJAJ-AUTO'] },
    { tag:'Today', kind:'mid',  label:'INR weakens 0.18% vs USD — mild import drag',  impact:'Risk & Macro',      tickers:['MARUTI','HEROMOTOCO'] },
    { tag:'Today', kind:'bad',  label:'Hero MotoCorp Q4 dispatch miss — guidance cut', impact:'Sentiment',         tickers:['HEROMOTOCO'] },
  ],
  sectorChange: [
    { name:'Auto',     pct: 1.24 },
    { name:'IT',       pct:-0.67 },
    { name:'Banking',  pct:-0.12 },
    { name:'Pharma',   pct: 0.41 },
    { name:'Energy',   pct: 0.88 },
    { name:'FMCG',     pct: 0.22 },
  ],
};

window.MARKET_MONTH = {
  pulse: 'Building strength',
  oneLiner: 'EV momentum + PLI benefits flowing through margins. Watch crude & INR.',
  drivers: [
    { tag:'This month', kind:'good', label:'PLI auto disbursements at 18-mo high',          impact:'Fundamentals',  tickers:['MARUTI','M&M','TATAMOTORS'] },
    { tag:'This month', kind:'good', label:'EV registrations +38% MoM (Vahan)',             impact:'Sales & Demand', tickers:['TATAMOTORS','M&M'] },
    { tag:'This month', kind:'good', label:'Steel prices -6% — margin tailwind',            impact:'Raw Materials',  tickers:['MARUTI','TATAMOTORS','ASHOKLEY'] },
    { tag:'This month', kind:'mid',  label:'FII flows into autos +₹2,400 Cr',               impact:'Fundamentals',   tickers:['MARUTI','TATAMOTORS'] },
    { tag:'This month', kind:'bad',  label:'Semiconductor tightness for ADAS variants',     impact:'Competitive Intel', tickers:['MARUTI','M&M'] },
  ],
};

window.TRENDING = [
  { sym:'TATAMOTORS', why:'EV order book + Tiago.ev launch buzz', delta:'+2.18%', volume:'2.4× avg' },
  { sym:'MARUTI',     why:'Brezza & Grand Vitara dispatch beat',  delta:'+1.42%', volume:'1.8× avg' },
  { sym:'TVSMOTORS',  why:'Premium 2W mix improving',             delta:'+1.92%', volume:'1.6× avg' },
  { sym:'M&M',        name:'Mahindra & Mahindra', why:'Thar.e teaser + tractor margins',     delta:'+0.62%', volume:'1.3× avg' },
];

window.SUGGESTIONS = [
  { sym:'EICHERMOT',  reason:'Premium 2W tailwinds + RE 650 launch',           score:0.66, why:'Matches your "growth + brand moat" picks' },
  { sym:'ASHOKLEY',   reason:'Infra spend cycle, M&HCV demand recovery',       score:0.52, why:'Cyclical play on capex you usually like' },
  { sym:'TVSMOTORS',  reason:'EV scooter share gain (iQube)',                  score:0.69, why:'EV exposure outside your existing list' },
];

window.CATEGORIES = [
  { key:'ev',     icon:'⚡', label:'EV-first',     count:5, color:'#7c3aed' },
  { key:'mass',   icon:'🚗', label:'Mass-market',  count:8, color:'#0891b2' },
  { key:'premium',icon:'💎', label:'Premium',      count:4, color:'#d97706' },
  { key:'cv',     icon:'🚛', label:'Commercial',   count:3, color:'#16a34a' },
  { key:'2w',     icon:'🏍️', label:'Two-wheelers', count:4, color:'#dc2626' },
  { key:'parts',  icon:'⚙️', label:'Auto-parts',   count:6, color:'#475569' },
];

window.NIFTY_AUTO_HISTORY = (() => {
  // 30-day mock series for spark area
  const out = [];
  let v = 22650;
  for (let i = 0; i < 30; i++) {
    v += (Math.sin(i / 3) * 60) + ((Math.random() - 0.45) * 90);
    out.push(Math.round(v));
  }
  return out;
})();

// Multi-range Nifty Auto series — keys map to selector buttons on Home hero.
// Each ends at the same "now" value (~22847) so the headline stays consistent.
window.NIFTY_AUTO_RANGES = (() => {
  const NOW = 22847;
  function gen(points, startVal, vol) {
    const arr = [];
    let v = startVal;
    const drift = (NOW - startVal) / points;
    for (let i = 0; i < points; i++) {
      v += drift + Math.sin(i / (points / 6)) * vol * 0.6 + (Math.random() - 0.5) * vol;
      arr.push(Math.round(v));
    }
    arr[arr.length - 1] = NOW;
    return arr;
  }
  return {
    '1W': { points: gen(7,    22680, 60),  label:'1 week',   change:+0.73 },
    '1M': { points: gen(30,   22410, 90),  label:'1 month',  change:+1.95 },
    '3M': { points: gen(60,   21780, 140), label:'3 months', change:+4.90 },
    '6M': { points: gen(120,  20920, 180), label:'6 months', change:+9.21 },
    '1Y': { points: gen(180,  18650, 220), label:'1 year',   change:+22.51 },
  };
})();

// Same approach for portfolio total value
window.PORTFOLIO_RANGES = (() => {
  const NOW = 4_82_350;
  function gen(points, startVal, vol) {
    const arr = [];
    let v = startVal;
    const drift = (NOW - startVal) / points;
    for (let i = 0; i < points; i++) {
      v += drift + Math.sin(i / (points / 5)) * vol * 0.7 + (Math.random() - 0.5) * vol;
      arr.push(Math.round(v));
    }
    arr[arr.length - 1] = NOW;
    return arr;
  }
  return {
    '1W': { points: gen(7,   4_75_200, 1500), label:'1 week',   change:+1.50 },
    '1M': { points: gen(30,  4_24_800, 2200), label:'1 month',  change:+13.55 },
    '3M': { points: gen(60,  3_98_400, 2800), label:'3 months', change:+21.07 },
    '6M': { points: gen(120, 3_72_500, 3400), label:'6 months', change:+29.49 },
    '1Y': { points: gen(180, 3_18_200, 4200), label:'1 year',   change:+51.59 },
  };
})();

window.CHAT_SEEDS = [
  'Why is MARUTI rated STRONG BUY today?',
  'What does the Sales & Demand agent see this week?',
  'Compare Tata Motors vs M&M for EV exposure',
  'Which agent should I trust most for short-term moves?',
];

// ---------- PORTFOLIO ----------
window.PORTFOLIO = {
  totalValue: 4_82_350,   // ₹
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
    { kind:'buy',    sym:'EICHERMOT',  qty: 2, price:4_882.40, t:'Today, 10:42 AM' },
    { kind:'agent',  sym:'BAJAJ-AUTO', text:'Verdict downgraded BUY → NEUTRAL', t:'Yesterday' },
    { kind:'sell',   sym:'TVSMOTORS',  qty:10, price:2_410.20, t:'2 days ago' },
    { kind:'agent',  sym:'MARUTI',     text:'Pattern Analysis flagged breakout above ₹12,400', t:'3 days ago' },
    { kind:'buy',    sym:'TATAMOTORS', qty:15, price:  890.00, t:'4 days ago' },
  ],
  perfHistory: (() => {
    // 30-day cumulative-value series ending at totalValue
    const target = 4_82_350;
    let v = 4_24_800;
    const out = [];
    for (let i = 0; i < 30; i++) {
      const drift = (target - v) / Math.max(30 - i, 1);
      v += drift + (Math.random() - 0.4) * 2000;
      out.push(Math.round(v));
    }
    out[out.length - 1] = target;
    return out;
  })(),
  alerts: [
    { sym:'BAJAJ-AUTO', kind:'warn', text:'Position now -1.9%. Risk & Macro flagged INR pressure.' },
    { sym:'MARUTI',     kind:'good', text:'Strongest pick — Sales & Demand at 0.84 (top 5%).' },
    { sym:'TATAMOTORS', kind:'good', text:'EV order book +22% MoM, agent target ₹1,020.' },
  ],
};

// ---------- LEARN ----------
// ---------- PORTFOLIO LEARNINGS ----------
// Grounded lessons from THIS user's holdings + activity, not theory.
// Each item points at a real action (or non-action) the user took.
window.PORTFOLIO_LEARNINGS = {
  // Headline stats summarizing the lessons below
  summary: {
    missedGain:    +18_420,   // ₹ — opportunities user didn't take that would have made money
    avoidedLoss:   +6_180,    // ₹ — situations user got out (or didn't enter) and avoided pain
    realizedLoss:  -3_240,    // ₹ — actual losses booked
    accuracyVsAgent: 0.62,    // 0–1 — how often user agreed with agent's verdict on actions taken
    actionsReviewed: 12,
  },

  // Each lesson references a real ticker the user holds or watches.
  items: [
    {
      id:'miss-buy-tata',
      kind:'missed-buy',
      severity:'high',         // high / med / low
      sym:'TATAMOTORS',
      title:'Missed a STRONG BUY entry on TATAMOTORS',
      when:'14 days ago',
      what:'Agent issued STRONG BUY at ₹812. You added a calendar reminder but did not buy.',
      cost:'+₹11,250 missed gain · stock now ₹942 (+16.0%)',
      costValue: +11_250,
      lesson:'When 6+ agents agree (composite ≥ 0.75), your average follow-through is best within 48h. Set price-trigger alerts instead of calendar reminders.',
      agentSnapshot:[
        {n:'Sales & Demand', v:0.82},
        {n:'Fundamentals',   v:0.79},
        {n:'Sentiment',      v:0.74},
      ],
      action:'Set price-trigger alert',
    },
    {
      id:'miss-sell-bajaj',
      kind:'missed-sell',
      severity:'high',
      sym:'BAJAJ-AUTO',
      title:'Held BAJAJ-AUTO past the downgrade',
      when:'9 days ago',
      what:'Verdict moved BUY → NEUTRAL at ₹9,120. You held. Stock is now ₹8,945.',
      cost:'-₹1,050 unrealized · -1.92% drawdown on this position',
      costValue: -1_050,
      lesson:'You\u2019ve held through 3 of 4 downgrades this year — average extra drawdown after a downgrade is -2.4%. Consider trimming 25% on the first downgrade, not waiting for the second.',
      agentSnapshot:[
        {n:'Risk & Macro',     v:0.41},
        {n:'Fundamentals',     v:0.55},
        {n:'Pattern Analysis', v:0.48},
      ],
      action:'Review trim rule',
    },
    {
      id:'sell-too-early-tvs',
      kind:'sold-too-early',
      severity:'med',
      sym:'TVSMOTORS',
      title:'Sold TVSMOTORS before the run-up',
      when:'2 days ago',
      what:'Sold 10 @ ₹2,410 with verdict still at BUY (score 0.69). Stock is now ₹2,385 but agent target is ₹2,560.',
      cost:'+₹1,500 left on the table at agent target',
      costValue: +1_500,
      lesson:'You\u2019ve booked early on 4 of 7 BUY-rated names this quarter. Average post-sale return: +6.2% within 30 days. Try trailing stops instead of fixed exits.',
      agentSnapshot:[
        {n:'Pattern Analysis', v:0.71},
        {n:'Sentiment',        v:0.68},
        {n:'Sales & Demand',   v:0.66},
      ],
      action:'Try trailing stop',
    },
    {
      id:'good-call-eicher',
      kind:'good-call',
      severity:'low',
      sym:'EICHERMOT',
      title:'Nice — bought EICHERMOT close to the agent signal',
      when:'Today, 10:42 AM',
      what:'Bought 2 @ ₹4,882 within an hour of the BUY upgrade (score 0.66). Already +0.29%.',
      cost:'+₹28 unrealized · on track with agent target ₹5,200',
      costValue: +28,
      lesson:'This is the pattern that works for you — quick action on multi-agent BUYs. Repeat with similar setups in your watchlist (TVSMOTORS, M&M).',
      agentSnapshot:[
        {n:'Fundamentals',     v:0.72},
        {n:'Competitive Intel',v:0.68},
        {n:'Sentiment',        v:0.61},
      ],
      action:'Find similar setups',
    },
    {
      id:'concentration-maruti',
      kind:'sizing',
      severity:'med',
      sym:'MARUTI',
      title:'MARUTI is 21% of your portfolio',
      when:'Now',
      what:'Single-name concentration above 20% on a single stock. Strong agent score (0.82), but a Sales & Demand miss could swing your whole book.',
      cost:'Risk metric — no realized cost yet',
      costValue: 0,
      lesson:'Your sweet spot historically: 12–18% per name. Trimming 3 shares (~₹37k) brings you back into your own range without giving up the upside thesis.',
      agentSnapshot:[
        {n:'Sales & Demand',   v:0.84},
        {n:'Fundamentals',     v:0.81},
        {n:'Risk & Macro',     v:0.42},
      ],
      action:'Rebalance suggestion',
    },
    {
      id:'avoided-hero',
      kind:'avoided-loss',
      severity:'low',
      sym:'HEROMOTOCO',
      title:'You skipped HEROMOTOCO at the right time',
      when:'6 days ago',
      what:'You watched HEROMOTOCO when verdict moved to NEUTRAL. Stock has since fallen -3.1%.',
      cost:'+₹6,180 saved on a hypothetical 50-share entry',
      costValue: +6_180,
      lesson:'Watching, not buying, on NEUTRAL verdicts has worked 4 of 5 times for you this quarter. Keep this rule.',
      agentSnapshot:[
        {n:'Sales & Demand',   v:0.38},
        {n:'Sentiment',        v:0.41},
        {n:'Pattern Analysis', v:0.45},
      ],
      action:'Keep on watchlist',
    },
  ],

  // Personal pattern highlights — short rules derived from the user's full history
  patterns: [
    { id:'p1', label:'Acts within 48h of STRONG BUY signals',           rate:0.71, kind:'good',
      detail:'5 of 7 STRONG BUY signals acted on within 2 days. Above-average follow-through.' },
    { id:'p2', label:'Holds through first downgrade',                    rate:0.75, kind:'bad',
      detail:'3 of 4 downgrades this year held past the first warning, costing -2.4% average extra drawdown.' },
    { id:'p3', label:'Books gains too early on BUY-rated holds',         rate:0.57, kind:'bad',
      detail:'4 of 7 BUY-rated sales locked in less than 60% of agent target.' },
    { id:'p4', label:'Avoids entries on NEUTRAL-rated names',            rate:0.80, kind:'good',
      detail:'4 of 5 NEUTRAL watchlist names skipped — average drawdown avoided -2.6%.' },
  ],
};

window.LEARN_PATHS = [
  {
    key:'agents',
    title:'Meet your 9 agents',
    sub:'How specialist agents fuse into one verdict',
    minutes: 6,
    steps: 5,
    progress: 0.6,
    color:'#0891b2',
    icon:'🧠',
  },
  {
    key:'verdict',
    title:'Reading a verdict',
    sub:'STRONG BUY, BUY, NEUTRAL — what they really mean',
    minutes: 4,
    steps: 4,
    progress: 1.0,
    color:'#16a34a',
    icon:'🎯',
  },
  {
    key:'metrics',
    title:'P/E, EBITDA & friends',
    sub:'Decode the numbers without the jargon',
    minutes: 8,
    steps: 6,
    progress: 0.33,
    color:'#7c3aed',
    icon:'📐',
  },
  {
    key:'macro',
    title:'INR, crude & RBI for autos',
    sub:'Why these three move auto stocks the most',
    minutes: 5,
    steps: 4,
    progress: 0,
    color:'#d97706',
    icon:'🌐',
  },
  {
    key:'ev',
    title:'The Indian EV opportunity',
    sub:'FAME, PLI, Vahan — and who wins',
    minutes: 7,
    steps: 5,
    progress: 0,
    color:'#dc2626',
    icon:'⚡',
  },
  {
    key:'risk',
    title:'Position sizing & stop-losses',
    sub:'Don\u2019t blow up your account',
    minutes: 6,
    steps: 4,
    progress: 0,
    color:'#475569',
    icon:'🛡️',
  },
];

window.GLOSSARY = [
  { term:'P/E ratio',     short:'Price-to-Earnings',  defn:'How many years of profit you\u2019re paying for one share. Lower can mean cheaper, but context matters.' },
  { term:'EBITDA',        short:'Operating earnings', defn:'Earnings before Interest, Taxes, Depreciation, Amortization \u2014 a clean view of core profitability.' },
  { term:'FII / DII',     short:'Big investors',      defn:'Foreign and Domestic Institutional Investors. Their flows often move stocks more than retail.' },
  { term:'Composite score',short:'0.00 to 1.00',      defn:'The fused score across all 9 agents, weighted. 0.75+ is STRONG BUY territory.' },
  { term:'RSI',           short:'Momentum gauge',     defn:'Relative Strength Index. >70 may be overbought, <30 may be oversold.' },
  { term:'PLI scheme',    short:'Gov subsidy',        defn:'Production-Linked Incentive \u2014 cash for hitting local manufacturing targets.' },
];

window.LEARN_TIPS = [
  { title:'Start with the verdict, not the price',  body:'Verdict + score tells you the strength of the signal. Price is just the cost of acting on it.' },
  { title:'One conflicting agent is normal',         body:'When 1\u20132 agents disagree it usually means the move is contested \u2014 size smaller, not zero.' },
  { title:'Crude up = autos down (usually)',         body:'Higher oil hits both input costs and consumer wallet. Watch Brent + INR together.' },
];

// ─── Live bootstrap ────────────────────────────────────────────────────────
// Fetches /ui/bootstrap once on page load and overwrites window.* globals
// with real prices, scores and market data.  Mock data above stays as the
// instant first-render fallback so the UI is never blank.
window.__apiReady = false;

(async function loadFromAPI() {
  try {
    const res = await fetch('/ui/bootstrap');
    if (!res.ok) return;
    const d = await res.json();

    if (d.AGENTS?.length)             window.AGENTS             = d.AGENTS;
    if (d.TICKERS?.length)            window.TICKERS            = d.TICKERS;
    if (d.WATCHLIST?.length)          window.WATCHLIST          = d.WATCHLIST;
    if (d.MARKET_TODAY)               window.MARKET_TODAY       = d.MARKET_TODAY;
    if (d.MARKET_MONTH)               window.MARKET_MONTH       = d.MARKET_MONTH;
    if (d.NIFTY_AUTO_HISTORY?.length) window.NIFTY_AUTO_HISTORY = d.NIFTY_AUTO_HISTORY;
    if (d.TRENDING?.length)           window.TRENDING           = d.TRENDING;
    if (d.SUGGESTIONS?.length)        window.SUGGESTIONS        = d.SUGGESTIONS;
    if (d.CATEGORIES?.length)         window.CATEGORIES         = d.CATEGORIES;
    if (d.CHAT_SEEDS?.length)         window.CHAT_SEEDS         = d.CHAT_SEEDS;

    // T2.2 — Apply persisted agent task flags on top of the default AGENT_TASKS
    if (d.AGENT_TASK_FLAGS && Object.keys(d.AGENT_TASK_FLAGS).length > 0) {
      Object.entries(d.AGENT_TASK_FLAGS).forEach(([agentKey, taskFlags]) => {
        if (window.AGENT_TASKS[agentKey]) {
          window.AGENT_TASKS[agentKey] = window.AGENT_TASKS[agentKey].map(t => ({
            ...t,
            enabled: taskFlags[t.key] !== undefined ? taskFlags[t.key] : t.enabled,
          }));
        }
      });
    }

    window.__apiReady     = true;
    window.__apiLive      = d._liveData ?? false;
    window.__apiFetchedAt = d._fetchedAt;

    if (typeof window.__onApiReady === 'function') window.__onApiReady();
  } catch (e) {
    console.warn('[StockAgent] Bootstrap API unavailable — using mock data.', e);
  }

  // T2.5 — Fetch RL-derived learnings separately (not in bootstrap to keep it fast)
  try {
    const lr = await fetch('/ui/learnings');
    if (lr.ok) {
      const learnings = await lr.json();
      if (learnings.items?.length > 0) {
        window.PORTFOLIO_LEARNINGS = learnings;
        window.__learningsLive = true;
      }
    }
  } catch {
    // keep mock PORTFOLIO_LEARNINGS
  }
})();
