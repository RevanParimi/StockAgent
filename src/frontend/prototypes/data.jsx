// Static catalogues the screens read: agent task definitions per sector and
// the Learn page's course. None of it is market data. Market data comes only
// from the API (see "Market data" at the bottom); sample values for demo
// mode live in demo-fixtures.js.

// Sub-tasks per agent (5 score dimensions per AGENT_DESIGN.md). Each is independently toggleable.
// All sector task definitions — switch via window.AGENT_TASKS = window.AGENT_TASKS_BY_SECTOR[sector]
window.AGENT_TASKS_BY_SECTOR = {

  banking_bfsi: {
    fundamentals: [
      { key:'earn_qual',  label:'Earnings quality (NII vs one-time)',   source:'yfinance · RBI filings',   enabled:true,  beginner:'Is income from loans/fees — not lucky treasury bets?' },
      { key:'nim',        label:'NIM & CASA ratio trend',               source:'yfinance quarterly',        enabled:true,  beginner:'Borrowing cheap and lending at good spreads?' },
      { key:'crar',       label:'Capital adequacy (CRAR / CET1)',       source:'RBI filings · yfinance',    enabled:true,  beginner:'Buffer to absorb bad loans without failing.' },
      { key:'roa_roe',    label:'RoA & RoE profitability',              source:'yfinance quarterly',        enabled:true,  beginner:'Returns the bank earns on assets and equity.' },
      { key:'loan_mix',   label:'Loan book: retail vs corporate',       source:'Serper · analyst notes',    enabled:true,  beginner:'Diversified retail book = safer than lumpy corporate.' },
    ],
    risk: [
      { key:'npa',        label:'GNPA% & slippage ratio',               source:'yfinance · RBI',            enabled:true,  beginner:'Bad loan percentage and how fast new ones are forming.' },
      { key:'conc',       label:'Concentration risk (sector/borrower)', source:'RBI · annual report',       enabled:true,  beginner:'Too much exposure to one sector or big borrower?' },
      { key:'deposits',   label:'Deposit stability & ALM',              source:'yfinance · Serper',         enabled:true,  beginner:'Can the bank keep funding itself cheaply?' },
      { key:'regrisk',    label:'RBI enforcement & penalties',          source:'RBI circulars · Serper',    enabled:true,  beginner:'Any regulatory actions that signal deeper issues?' },
      { key:'cyber',      label:'Cyber & fraud incidents',              source:'CERT-In · Serper',          enabled:false, beginner:'Digital fraud events that erode customer trust.' },
    ],
    macro_policy: [
      { key:'rbi_rate',   label:'RBI repo rate cycle',                  source:'RBI MPC · Serper',          enabled:true,  beginner:'Rate cuts boost NIMs; hikes compress them.' },
      { key:'credit',     label:'System credit growth',                 source:'RBI weekly data',           enabled:true,  beginner:'Growing economy = more loans = more fee income.' },
      { key:'liquidity',  label:'LAF / system liquidity',               source:'RBI LAF data',              enabled:true,  beginner:'Tight liquidity = banks borrow at higher cost.' },
      { key:'regs',       label:'Regulatory circulars (IRAC/LCR)',      source:'RBI · SEBI · Tavily',       enabled:true,  beginner:'New provisioning or capital rules change earnings.' },
      { key:'fiscal',     label:'PSU recapitalisation / fiscal policy', source:'Budget · Serper',           enabled:false, beginner:'Govt support for public sector banks.' },
    ],
    institutional: [
      { key:'fii_flow',   label:'FII / DII shareholding change',        source:'BSE/NSE quarterly',         enabled:true,  beginner:'Foreign & domestic institutions buying or selling?' },
      { key:'promoter',   label:'Promoter stake & pledge change',       source:'SAST filings · BSE',        enabled:true,  beginner:'Management adding shares = confidence signal.' },
      { key:'mf',         label:'AMFI mutual fund holding delta',       source:'AMFI monthly',              enabled:true,  beginner:'Indian MFs adding = smart domestic money following.' },
      { key:'block',      label:'Bulk / block deals',                   source:'BSE/NSE exchange',          enabled:true,  beginner:'Big institutional trades visible on the exchange.' },
      { key:'insider',    label:'Director / KMP insider trades',        source:'SEBI disclosures',          enabled:false, beginner:'Board members buying = high-conviction signal.' },
    ],
    pattern_analysis: [
      { key:'cycle',      label:'Price cycle vs RBI rate regime',       source:'yfinance OHLCV',            enabled:true,  beginner:'Rate-cut cycles = bank stock rallies historically.' },
      { key:'momentum',   label:'RSI / MACD momentum',                  source:'Derived indicators',        enabled:true,  beginner:'Price gathering or losing steam right now.' },
      { key:'zones',      label:'Support / resistance zones',           source:'52w high/low · yfinance',   enabled:true,  beginner:'Levels where buyers historically step in.' },
      { key:'rel',        label:'Nifty Bank relative strength',         source:'yfinance ^NSEBANK',         enabled:true,  beginner:'Beating or lagging the Nifty Bank index?' },
      { key:'vol',        label:'Volume confirmation',                  source:'yfinance volume',           enabled:false, beginner:'Is the price move backed by strong volumes?' },
    ],
    universe_setup: [
      { key:'idx_wt',     label:'Nifty Bank index weight',              source:'NSE constituent data',      enabled:true,  beginner:'Larger weight = more passive fund buying on inflows.' },
      { key:'peer_rank',  label:'Peer market-cap rank (PSU vs pvt)',    source:'NSE · yfinance',            enabled:true,  beginner:'Tier-1 private vs PSU vs NBFC peer comparison.' },
      { key:'corp_act',   label:'Corporate actions',                    source:'BSE corporate actions',     enabled:true,  beginner:'Upcoming dividends, rights issues, or mergers.' },
      { key:'rebal',      label:'Index rebalancing risk',               source:'NSE semi-annual review',    enabled:false, beginner:'Risk of being dropped from or added to an index.' },
      { key:'mf_hold',    label:'MF portfolio weight',                  source:'AMFI monthly',              enabled:true,  beginner:'How heavily mutual funds are already positioned.' },
    ],
  },

  it_sector: {
    fundamentals: [
      { key:'cc_rev',     label:'Constant-currency revenue growth',     source:'yfinance quarterly · NSE',  enabled:true,  beginner:'Revenue growth stripping out currency effects.' },
      { key:'margins',    label:'EBIT margin (8-quarter trend)',         source:'yfinance quarterly',        enabled:true,  beginner:'Improving margins = operational leverage at work.' },
      { key:'deals',      label:'TCV deal wins (large deals $50M+)',    source:'Serper press releases',     enabled:true,  beginner:'Pipeline of future revenue locked in by contracts.' },
      { key:'attrition',  label:'LTM attrition & headcount',            source:'Serper · annual reports',   enabled:true,  beginner:'High attrition = rising wage costs + delivery risk.' },
      { key:'valuation',  label:'P/E & EV/Revenue vs peers',            source:'yfinance · Serper',         enabled:true,  beginner:'Cheap or expensive vs TCS, Infosys, HCL, Wipro?' },
    ],
    global_macro: [
      { key:'us_spend',   label:'US enterprise IT spend cycle',         source:'Serper · Gartner/IDC',      enabled:true,  beginner:'US clients cutting or expanding tech budgets?' },
      { key:'fed_rate',   label:'Fed rate impact on tech capex',        source:'Serper · Fed releases',     enabled:true,  beginner:'Higher rates → US clients defer big IT projects.' },
      { key:'usd_inr',    label:'USD/INR forex impact',                 source:'yfinance USDINR=X',         enabled:true,  beginner:'Stronger USD = more INR revenue for IT exporters.' },
      { key:'geopol',     label:'CHIPS Act / US-China tech policy',     source:'Serper',                    enabled:true,  beginner:'Offshoring trends and tech-sector geopolitics.' },
      { key:'ma',         label:'Global IT M&A activity',               source:'Serper · deal news',        enabled:false, beginner:'M&A wave signals sector consolidation or growth.' },
    ],
    risk_macro: [
      { key:'visa',       label:'H1B / L1 visa approval rate',          source:'USCIS data · Serper',       enabled:true,  beginner:'Tighter visas = costlier onsite delivery model.' },
      { key:'ai_disr',    label:'AI / GenAI disruption risk',           source:'Serper',                    enabled:true,  beginner:'Will AI reduce IT services headcount demand?' },
      { key:'client_conc',label:'Client concentration risk',            source:'Serper · company filings',  enabled:true,  beginner:'Too dependent on one big client = vulnerable.' },
      { key:'fx_hedge',   label:'FX hedging position',                  source:'Serper · company filings',  enabled:false, beginner:'How much currency risk is hedged away.' },
      { key:'talent',     label:'STEM talent supply & wage inflation',  source:'Serper',                    enabled:true,  beginner:'India talent supply vs wage pressure on margins.' },
    ],
    peer_benchmark: [
      { key:'rev_rank',   label:'Revenue growth rank vs peers',         source:'Serper quarterly comps',    enabled:true,  beginner:'Faster or slower growth than TCS/Infosys/HCL?' },
      { key:'margin_rank',label:'EBIT margin rank vs peers',            source:'Serper quarterly comps',    enabled:true,  beginner:'Higher or lower margins than the big four?' },
      { key:'deal_rank',  label:'TCV deal momentum rank',               source:'Serper deal announcements', enabled:true,  beginner:'Winning more or fewer big contracts than peers?' },
      { key:'attr_rank',  label:'Attrition rank vs peers',              source:'Serper · HR reports',       enabled:true,  beginner:'Retaining staff better or worse than rivals?' },
      { key:'val_gap',    label:'P/E valuation gap vs peer median',     source:'yfinance',                  enabled:true,  beginner:'Premium or discount to the sector peer group?' },
    ],
    pattern_analysis: [
      { key:'cycle',      label:'Price cycle (rate-sensitive growth)',  source:'yfinance OHLCV',            enabled:true,  beginner:'IT stocks fall when rates rise, rally when they cut.' },
      { key:'momentum',   label:'RSI / MACD momentum',                  source:'Derived indicators',        enabled:true,  beginner:'Short-term price momentum signal.' },
      { key:'zones',      label:'Support / resistance zones',           source:'52w high/low',              enabled:true,  beginner:'Key price levels where buyers step in.' },
      { key:'rel',        label:'Nifty IT relative strength (beta)',    source:'yfinance ^CNXIT',           enabled:true,  beginner:'Beating or lagging the Nifty IT index?' },
      { key:'vol',        label:'Volume confirmation',                  source:'yfinance volume',           enabled:false, beginner:'Conviction behind recent price moves.' },
    ],
    sentiment: [
      { key:'ai_narr',    label:'AI / GenAI narrative strength',        source:'Serper news',               enabled:true,  beginner:'Strong AI deal story = higher P/E multiple.' },
      { key:'layoffs',    label:'Layoff / bench utilisation signals',   source:'Serper · LinkedIn',         enabled:true,  beginner:'Layoffs = cost cutting; bench filling = demand ahead.' },
      { key:'mgmt_tone',  label:'Management tone (earnings calls)',     source:'Serper transcripts',        enabled:true,  beginner:'Confident or cautious forward commentary.' },
      { key:'sector_narr',label:'Sector narrative (Nifty IT outlook)',  source:'Serper · analyst notes',    enabled:true,  beginner:'Broad market view on Indian IT sector.' },
      { key:'news_vol',   label:'News volume & sentiment',              source:'Serper news',               enabled:false, beginner:'Spike in coverage = event risk or catalyst.' },
    ],
    transcript_nlp: [
      { key:'guidance',   label:'Guidance: raised / maintained / cut',  source:'Earnings transcripts',      enabled:true,  beginner:'Did management raise or lower revenue guidance?' },
      { key:'verticals',  label:'Vertical mix (BFSI/retail/mfg)',       source:'Earnings transcripts',      enabled:true,  beginner:'Which client industries are growing vs slowing?' },
      { key:'geo',        label:'Geography (Americas / Europe)',         source:'Earnings transcripts',      enabled:true,  beginner:'Where revenue is growing fastest.' },
      { key:'ai_deals',   label:'AI deal count mentioned',              source:'Earnings transcripts',      enabled:true,  beginner:'How many AI-specific contracts won this quarter.' },
      { key:'pushback',   label:'Analyst pushback on call',             source:'Earnings transcripts',      enabled:true,  beginner:'Tough analyst questions = market wants more proof.' },
    ],
    insider_smart_money: [
      { key:'fii_fo',     label:'FII F&O net futures position',         source:'NSE F&O data',              enabled:true,  beginner:'FII long futures buildup = forward accumulation.' },
      { key:'promoter',   label:'Promoter SAST / pledge activity',      source:'SEBI SAST filings',         enabled:true,  beginner:'Promoter buying = high conviction from insiders.' },
      { key:'mf',         label:'AMFI MF holding change',               source:'AMFI monthly',              enabled:true,  beginner:'Indian MFs adding = domestic smart money signal.' },
      { key:'block',      label:'Bulk / block deals',                   source:'BSE/NSE exchange',          enabled:true,  beginner:'Large institutional trades direction.' },
      { key:'insider',    label:'Director / KMP trades',                source:'SEBI disclosures',          enabled:false, beginner:'Board members trading with their own money.' },
    ],
  },

  renewable_energy: {
    fundamentals: [
      { key:'cuf',        label:'CUF vs technology benchmark',          source:'company reports · Serper',  enabled:true,  beginner:'Are solar/wind plants producing at rated capacity?' },
      { key:'ebitda_mw',  label:'EBITDA per MW (8-quarter trend)',      source:'yfinance quarterly',        enabled:true,  beginner:'Profitability per unit of power-generation capacity.' },
      { key:'dscr',       label:'DSCR — debt service coverage',         source:'yfinance · company filings',enabled:true,  beginner:'Can the company pay its loan EMIs from plant cash flow?' },
      { key:'receivables',label:'DISCOM receivables (payment days)',    source:'PFC reports · Serper',      enabled:true,  beginner:'How long state power utilities take to pay bills.' },
      { key:'leverage',   label:'Project D/E & holdco leverage',        source:'yfinance · annual report',  enabled:true,  beginner:'Debt load relative to assets — higher = riskier.' },
    ],
    business: [
      { key:'mix',        label:'Solar / wind / hybrid capacity mix',   source:'company filings · Serper',  enabled:true,  beginner:'Diversified generation mix reduces output risk.' },
      { key:'ppa',        label:'PPA quality (tenor, counterparty)',    source:'Serper · company PPAs',     enabled:true,  beginner:'Long-term power purchase agreements = locked revenue.' },
      { key:'pipeline',   label:'Pipeline credibility (GW under const)',source:'Serper · MNRE',             enabled:true,  beginner:'How credible is the project construction pipeline?' },
      { key:'customers',  label:'Customer diversification',             source:'Serper · company filings',  enabled:true,  beginner:'C&I + multiple DISCOMs = safer than single buyer.' },
      { key:'geography',  label:'State-wise MW spread',                 source:'company filings',           enabled:false, beginner:'Spread across states reduces single-state policy risk.' },
    ],
    valuation: [
      { key:'ev_mw',      label:'EV / MW vs benchmark (₹4-6Cr/MW)',    source:'Serper · peer comps',       enabled:true,  beginner:'Standard infra metric — cheap if below ₹4Cr/MW.' },
      { key:'ev_ebitda',  label:'EV / EBITDA (15-25x healthy)',         source:'yfinance · Serper',         enabled:true,  beginner:'Earnings multiple — similar to global clean energy.' },
      { key:'tariff',     label:'Tariff vs current MNRE auction price', source:'Serper · MNRE data',        enabled:true,  beginner:'Projects signed at better-than-market rates = value.' },
      { key:'irr',        label:'Implied project IRR vs WACC',          source:'Serper · analyst models',   enabled:true,  beginner:'Is the project return above the cost of capital?' },
      { key:'dcf',        label:'Pipeline DCF value',                   source:'Serper · analyst notes',    enabled:false, beginner:'Discounted value of projects under development.' },
    ],
    sentiment_policy: [
      { key:'mnre',       label:'MNRE auction health (GW awarded)',     source:'MNRE portal · Serper',      enabled:true,  beginner:'Government awarding more auctions = sector growth.' },
      { key:'budget',     label:'Union Budget capex / PLI allocation',  source:'Budget · Serper',           enabled:true,  beginner:'More budget spend = more renewable projects funded.' },
      { key:'policy',     label:'RPO / must-run / ISTS waiver',         source:'CERC · Tavily',             enabled:true,  beginner:'Grid access and purchase obligation policies.' },
      { key:'rbi_rate',   label:'RBI rate → WACC impact',               source:'RBI MPC · yfinance',        enabled:true,  beginner:'25bp rate cut = ~15bp WACC improvement for RE.' },
      { key:'modules',    label:'Solar module price (BloombergNEF)',    source:'BloombergNEF · Serper',     enabled:true,  beginner:'Cheaper modules = better project economics ahead.' },
    ],
    technical: [
      { key:'cycle',      label:'Price cycle (policy-sensitive)',        source:'yfinance OHLCV',            enabled:true,  beginner:'RE stocks rally on budget/MNRE news cycles.' },
      { key:'momentum',   label:'RSI / MACD momentum',                  source:'Derived indicators',        enabled:true,  beginner:'Short-term price momentum signal.' },
      { key:'zones',      label:'Support / resistance zones',           source:'52w high/low',              enabled:true,  beginner:'Key levels where buyers have stepped in historically.' },
      { key:'rel',        label:'Nifty Energy relative strength',       source:'yfinance ^CNXENERGY',       enabled:true,  beginner:'Beating or lagging the Nifty Energy index?' },
      { key:'vol',        label:'Volume confirmation',                  source:'yfinance volume',           enabled:false, beginner:'Is price action backed by conviction volumes?' },
    ],
    risk: [
      { key:'discom',     label:'DISCOM credit health (PFC rating)',    source:'PFC reports · Serper',      enabled:true,  beginner:'Weak DISCOM = delayed payments or defaults.' },
      { key:'curtail',    label:'Curtailment risk (CERC data)',         source:'CERC · MNRE · Serper',      enabled:true,  beginner:'State grids sometimes refuse to buy power generated.' },
      { key:'ppa_prot',   label:'PPA tariff protection / force majeure',source:'company PPAs · Serper',     enabled:true,  beginner:'Are PPA terms protected from policy changes?' },
      { key:'exec',       label:'Execution delay risk',                 source:'company filings · Serper',  enabled:true,  beginner:'Construction delays hurt revenue commissioning timelines.' },
      { key:'pledge',     label:'Promoter pledge %',                   source:'BSE/NSE disclosures',       enabled:true,  beginner:'High pledge = margin call risk on stock correction.' },
    ],
  },

};

// Automobile tasks (existing window.AGENT_TASKS is automobile — keep for backward compat)
window.AGENT_TASKS_BY_SECTOR.automobile = null; // filled below after automobile definition

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

// Wire automobile into the by-sector map
window.AGENT_TASKS_BY_SECTOR.automobile = window.AGENT_TASKS;

// ---------- LEARN ----------
// progress is 0 for every path: nothing records a user's progress yet, so a
// non-zero value would be invented.
window.LEARN_PATHS = [
  {
    key:'agents',
    title:'Meet your 9 agents',
    sub:'How specialist agents fuse into one verdict',
    minutes: 6,
    steps: 5,
    progress: 0,
    color:'#0891b2',
    icon:'🧠',
  },
  {
    key:'verdict',
    title:'Reading a verdict',
    sub:'STRONG BUY, BUY, NEUTRAL — what they really mean',
    minutes: 4,
    steps: 4,
    progress: 0,
    color:'#16a34a',
    icon:'🎯',
  },
  {
    key:'metrics',
    title:'P/E, EBITDA & friends',
    sub:'Decode the numbers without the jargon',
    minutes: 8,
    steps: 6,
    progress: 0,
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

// ─── Market data ───────────────────────────────────────────────────────────
// Every market global starts empty. /ui/bootstrap fills them; until it
// answers a screen shows "Loading…", and if it fails the screen says the data
// is unavailable. Nothing falls back to sample values (PR-001). Demo mode
// (?demo=1, index.html) is the one exception: it installs demo-fixtures.js's
// sample values instead and makes no market API call.
//
// window.__apiState: 'loading' | 'ready' | 'failed' | 'demo'. App() re-renders
// through window.__onApiReady when it settles either way.
Object.assign(window, {
  AGENTS: [], TICKERS: [], WATCHLIST: [], TRENDING: [], SUGGESTIONS: [], CATEGORIES: [],
  MARKET_TODAY: null, MARKET_MONTH: null, NIFTY50: null, NIFTY_AUTO_HISTORY: [],
  PORTFOLIO_LEARNINGS: null,
  // Questions only, never a claim about a stock (same list as the server's).
  CHAT_SEEDS: [
    'How is my portfolio doing?',
    'What moved the market today?',
    'What should I watch in my holdings this week?',
    'Explain the latest verdict on one of my stocks',
  ],
});
window.__apiReady = false;
window.__apiState = 'loading';

function saApiSettled(state) {
  window.__apiState = state;
  window.__apiReady = state === 'ready' || state === 'demo';
  if (typeof window.__onApiReady === 'function') window.__onApiReady();
}

if (window.saDemoMode && window.saDemoFixtures) {
  Object.assign(window, window.saDemoFixtures);
  window.__learningsLive = false;
  saApiSettled('demo');
} else {
  (async function loadFromAPI() {
    try {
      const res = await fetch('/ui/bootstrap');
      if (!res.ok) throw new Error('bootstrap HTTP ' + res.status);
      const d = await res.json();

      if (Array.isArray(d.AGENTS))      window.AGENTS      = d.AGENTS;
      if (Array.isArray(d.TICKERS))     window.TICKERS     = d.TICKERS;
      if (Array.isArray(d.WATCHLIST))   window.WATCHLIST   = d.WATCHLIST;
      if (Array.isArray(d.TRENDING))    window.TRENDING    = d.TRENDING;
      if (Array.isArray(d.SUGGESTIONS)) window.SUGGESTIONS = d.SUGGESTIONS;
      if (Array.isArray(d.CATEGORIES))  window.CATEGORIES  = d.CATEGORIES;
      if (d.MARKET_TODAY)               window.MARKET_TODAY = d.MARKET_TODAY;
      if (d.MARKET_MONTH)               window.MARKET_MONTH = d.MARKET_MONTH;
      window.NIFTY50 = d.NIFTY50 || null;
      if (Array.isArray(d.NIFTY_AUTO_HISTORY)) window.NIFTY_AUTO_HISTORY = d.NIFTY_AUTO_HISTORY;
      if (d.CHAT_SEEDS?.length)         window.CHAT_SEEDS  = d.CHAT_SEEDS;

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

      window.__apiLive      = d._liveData ?? false;
      window.__apiFetchedAt = d._fetchedAt;
      saApiSettled('ready');
    } catch (e) {
      console.warn('[StockAgent] Bootstrap API unavailable — market data shown as unavailable.', e);
      saApiSettled('failed');
    }

    // T2.5 — recent verdict changes, fetched separately (not in bootstrap to keep it fast)
    try {
      const lr = await fetch('/ui/learnings');
      if (lr.ok) {
        const learnings = await lr.json();
        if (learnings.items?.length > 0) {
          window.PORTFOLIO_LEARNINGS = learnings;
          window.__learningsLive = true;
          if (typeof window.__onApiReady === 'function') window.__onApiReady();
        }
      }
    } catch {
      // no section: there is nothing real to show
    }
  })();
}
