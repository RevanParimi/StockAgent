// Agents page — card grid with toggle on/off + drawer with sliders. An
// operator screen: index.html loads this file for the owner only (PR-040).

// Sub-task catalogue: defined here unless an older cached data.jsx (which
// carried it, flags applied) already did. Then the persisted flags from
// /ui/bootstrap (data.jsx's AGENT_TASK_FLAGS) are applied by saApplyTaskFlags.
if (!window.AGENT_TASKS) {
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
}

// The persisted task flags over the catalogue's defaults.
function saApplyTaskFlags(tasks, flags) {
  const out = { ...(tasks || {}) };
  Object.entries(flags || {}).forEach(([agentKey, taskFlags]) => {
    if (out[agentKey] && taskFlags && typeof taskFlags === 'object') {
      out[agentKey] = out[agentKey].map(t => ({
        ...t,
        enabled: taskFlags[t.key] !== undefined ? taskFlags[t.key] : t.enabled,
      }));
    }
  });
  return out;
}
const { useState: useStateAg, useEffect: useEffectAg } = React;

const _SECTOR_LABELS = {
  automobile:       'Automobile',
  banking_bfsi:     'Banking',
  it_sector:        'IT',
  renewable_energy: 'Renewable',
};

function AgentsPage({ onNav, openChat }) {
  // Tuning (plug toggles, task toggles, weight slider) is the owner's: a member
  // sees the agents read-only (PR-001). The server's require_owner on the weight
  // and task routes stays the real guard.
  const canTune = saIsOwner(useSaUser());
  const [activeSector, setActiveSectorState] = useStateAg('automobile');
  const [agents, setAgents] = useStateAg(window.AGENTS);
  const [agentsFailed, setAgentsFailed] = useStateAg(false);
  const [tasks, setTasks] = useStateAg(() => saApplyTaskFlags(window.AGENT_TASKS, window.AGENT_TASK_FLAGS));
  const [drawerKey, setDrawerKey] = useStateAg(null);
  const [search, setSearch] = useStateAg('');
  const [saveStatus, setSaveStatus] = useStateAg(null); // null | 'saving' | 'saved' | {error}
  const [sectorLoading, setSectorLoading] = useStateAg(false);

  // Bootstrap failed or has not answered: read the agents from their own route.
  useEffectAg(() => {
    if (agents.length || window.saDemoMode) return;
    let alive = true;
    fetch('/ui/agents?sector=automobile')
      .then(r => r.ok ? r.json() : Promise.reject(new Error('agents HTTP ' + r.status)))
      .then(d => { if (alive) setAgents(d.agents || []); })
      .catch(() => { if (alive) setAgentsFailed(true); });
    return () => { alive = false; };
  }, []);

  const switchSector = async (sector) => {
    if (sector === activeSector) return;
    setSectorLoading(true);
    setDrawerKey(null);
    try {
      const res = await fetch(`/ui/agents?sector=${sector}`);
      if (res.ok) {
        const data = await res.json();
        setAgents(data.agents);
        setTasks(window.AGENT_TASKS_BY_SECTOR?.[sector] || {});
        setActiveSectorState(sector);
      }
    } catch { /* keep existing */ }
    finally { setSectorLoading(false); }
  };

  const enabled = agents.filter(a => a.enabled);
  const totalWeight = enabled.reduce((s,a)=>s+a.weight, 0);
  const allTasks = Object.values(tasks).flat();
  const enabledTasks = allTasks.filter(t => t.enabled).length;

  // Persist all current weights to the backend (scoped to activeSector)
  const persistWeights = async (updatedAgents) => {
    setSaveStatus('saving');
    const weights = {};
    updatedAgents.forEach(a => { weights[a.key] = parseFloat(a.weight) || 0; });
    try {
      const res = await fetch(`/ui/agents/weights?sector=${activeSector}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ weights }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setSaveStatus({ error: err.detail || 'Save failed' });
        setTimeout(() => setSaveStatus(null), 4000);
      } else {
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus(null), 2000);
      }
    } catch {
      setSaveStatus({ error: 'Network error — weights saved locally only' });
      setTimeout(() => setSaveStatus(null), 4000);
    }
  };

  // Toggle: zero the weight when disabling, restore previous weight when enabling
  const toggle = (key) => {
    const updated = agents.map(a => {
      if (a.key !== key) return a;
      const nowEnabled = !a.enabled;
      return {
        ...a,
        enabled: nowEnabled,
        _prevWeight: a.enabled ? a.weight : a._prevWeight,
        weight: nowEnabled ? (a._prevWeight || 0.10) : 0,
      };
    });
    setAgents(updated);
    persistWeights(updated);
  };

  // Visual-only update during slider drag
  const setWeight = (key, w) =>
    setAgents(prev => prev.map(a => a.key===key ? { ...a, weight: w } : a));

  // Persist on slider release (mouseUp / touchEnd)
  const saveWeight = (key, w) => {
    const updated = agents.map(a => a.key===key ? { ...a, weight: parseFloat(w) } : a);
    setAgents(updated);
    persistWeights(updated);
  };

  const toggleTask = async (agentKey, taskKey) => {
    const updatedTasks = {
      ...tasks,
      [agentKey]: (tasks[agentKey] || []).map(t => t.key===taskKey ? { ...t, enabled: !t.enabled } : t),
    };
    setTasks(updatedTasks);
    // Persist flags to backend
    const flags = {};
    Object.entries(updatedTasks).forEach(([aKey, list]) => {
      flags[aKey] = {};
      list.forEach(t => { flags[aKey][t.key] = t.enabled; });
    });
    fetch('/ui/agents/tasks', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ flags }),
    }).catch(() => {}); // fire-and-forget; local state already updated
  };

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-base)' }}>
      <TopNav active="agents" onNav={onNav} search={search} setSearch={setSearch}/>

      <main style={{ maxWidth:1280, margin:'0 auto', padding:'var(--main-py) var(--main-px) 96px' }}>
        {/* Header bar */}
        <div className="agents-header" style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:24, marginBottom:24 }}>
          <div>
            <button onClick={()=>onNav?.('home')} style={{
              display:'inline-flex', alignItems:'center', gap:6, padding:'4px 10px 4px 6px',
              border:'1px solid var(--border)', borderRadius:8, background:'var(--bg-surface)',
              fontSize:11, fontWeight:600, color:'var(--ink-2)', marginBottom:12
            }}><Icon.ChevronL size={13}/> Back to Today</button>
            <h1 style={{ fontSize:30, fontWeight:800, letterSpacing:'-0.02em', margin:'0 0 6px' }}>
              Your AI agents
            </h1>
            <p style={{ color:'var(--ink-2)', fontSize:14, margin:0, maxWidth:600 }}>
              {canTune
                ? 'Each agent is a specialist. Plug them in to add a viewpoint, unplug to silence one. Tap a card to tune its weight.'
                : 'Each agent is a specialist that looks at one side of a stock. Tap a card to see what it watches.'}
            </p>
            {canTune && <LearningModeNote/>}
          </div>

          <div className="agents-stats" style={{ display:'flex', gap:12, alignItems:'flex-start' }}>
            {/* Save status badge */}
            {canTune && saveStatus && (
              <div style={{
                padding:'8px 14px', borderRadius:8, fontSize:12, fontWeight:600,
                background: saveStatus==='saving' ? 'var(--bg-tinted)' :
                            saveStatus==='saved'  ? 'var(--buy-soft)' : 'var(--sell-soft)',
                color: saveStatus==='saving' ? 'var(--ink-3)' :
                       saveStatus==='saved'  ? 'var(--buy-strong)' : 'var(--sell-strong)',
                border: '1px solid',
                borderColor: saveStatus==='saving' ? 'var(--border)' :
                             saveStatus==='saved'  ? 'var(--buy)' : 'var(--sell)',
              }}>
                {saveStatus==='saving' ? '⟳ Saving…' :
                 saveStatus==='saved'  ? '✓ Weights saved' :
                 '⚠ ' + (saveStatus.error || 'Error')}
              </div>
            )}
            {/* Counts only once the agents are known: 0 of 0 would be a figure about nothing. */}
            {agents.length > 0 && <>
              <Stat label="Plugged in"   value={enabled.length}    max={agents.length}/>
              <Stat label="Active tasks" value={enabledTasks}      max={allTasks.length} hint="Across all agents"/>
              <Stat label="Total weight" value={(totalWeight*100).toFixed(0)+'%'} hint={canTune ? 'Should be ~100%' : undefined}/>
            </>}
          </div>
        </div>

        {/* Sector switcher */}
        <div style={{ display:'flex', gap:6, marginBottom:24, flexWrap:'wrap' }}>
          {Object.entries(_SECTOR_LABELS).map(([key, label]) => {
            const active = key === activeSector;
            return (
              <button key={key} onClick={() => switchSector(key)} disabled={sectorLoading} style={{
                padding:'7px 16px', borderRadius:20, border:'1.5px solid',
                borderColor: active ? 'var(--cyan)' : 'var(--border)',
                background: active ? 'var(--cyan-soft)' : 'var(--bg-surface)',
                color: active ? 'var(--cyan)' : 'var(--ink-2)',
                fontSize:12, fontWeight:700, cursor:'pointer',
                opacity: sectorLoading ? 0.6 : 1, transition:'all .15s',
              }}>
                {label}
                {active && <span style={{ marginLeft:6, fontSize:10 }}>●</span>}
              </button>
            );
          })}
          {/* Like the counts above: no "0 agents" while the agents are not known. */}
          {agents.length > 0 && (
            <span style={{ fontSize:11, color:'var(--ink-3)', alignSelf:'center', marginLeft:4 }}>
              {agents.length} agents · {activeSector.replace('_',' ')}
            </span>
          )}
        </div>

        {agents.length === 0 && (
          <div className="card sa-unavailable" style={{ padding:24, color:'var(--ink-3)', fontSize:13, marginBottom:24 }}>
            {agentsFailed || window.__apiState === 'failed'
              ? 'The agents are unavailable right now. Try again in a few minutes.'
              : 'Loading the agents…'}
          </div>
        )}

        {/* Pipeline visual — hidden on mobile via CSS */}
        {agents.length > 0 && (
          <div className="pipeline-section">
            <Pipeline agents={enabled} onOpenAgent={setDrawerKey} canTune={canTune}/>
          </div>
        )}

        {/* Agent grid */}
        <div style={{ marginTop:32 }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14 }}>
            <h2 style={{ fontSize:18, fontWeight:700, margin:0 }}>All agents</h2>
            <div style={{ fontSize:12, color:'var(--ink-3)' }}>{canTune ? 'Click any card to tune' : 'Click any card for details'}</div>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'var(--grid-agents)', gap:16 }}>
            {agents.map(a => (
              <AgentCard key={a.key} a={a} tasks={tasks[a.key]||[]} canTune={canTune}
                onToggle={()=>toggle(a.key)} onOpen={()=>setDrawerKey(a.key)}/>
            ))}
          </div>
        </div>
      </main>

      {drawerKey && (
        <AgentDrawer
          a={agents.find(x => x.key === drawerKey)}
          tasks={tasks[drawerKey] || []}
          canTune={canTune}
          onClose={()=>setDrawerKey(null)}
          onToggle={()=>toggle(drawerKey)}
          onWeight={(w)=>setWeight(drawerKey, w)}
          onWeightSave={(w)=>saveWeight(drawerKey, w)}
          onToggleTask={(taskKey)=>toggleTask(drawerKey, taskKey)}
          saveStatus={saveStatus}
        />
      )}
    </div>
  );
}

// PR-040: the learning mode, beside the manual weight controls. The mode is
// global (SA-039); /ui/rl/weights/<ticker> reports it, so the first managed
// ticker is asked. What the note says about saved weights is from the code:
// PUT /ui/agents/weights writes data/agent_weights.json, which only this
// page's GET /ui/agents reads, and PUT /ui/agents/tasks writes
// data/agent_tasks.json, which only /ui/bootstrap and GET /ui/agents/tasks
// read (BACKLOG B-25).
function LearningModeNote() {
  const [mode, setMode] = useStateAg({ state: 'loading' });
  useEffectAg(() => {
    let alive = true;
    fetch('/ui/rl/tickers', { saNoKeyPrompt: true })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(d => {
        const sym = ((d && d.tickers) || [])[0]?.sym;
        if (!sym) throw new Error('no managed ticker');
        return fetch(`/ui/rl/weights/${encodeURIComponent(sym)}`, { saNoKeyPrompt: true });
      })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(d => { if (alive) setMode({ state: 'ok', mode: d.learning_mode, reason: d.learning_mode_reason }); })
      .catch(() => { if (alive) setMode({ state: 'failed' }); });
    return () => { alive = false; };
  }, []);
  const said = mode.state === 'loading' ? 'Learning mode: checking…'
    : mode.state === 'failed' ? 'Learning mode: unavailable right now.'
    : mode.mode === 'observe'
      ? 'Learning mode: observe. Decisions use each sector\'s configured weights; the learned weights are recorded, not used.'
    : mode.mode === 'adapt'
      ? 'Learning mode: adapt. Decisions use each stock\'s learned weights.'
    : `Learning mode: ${mode.mode}.`;
  return (
    <div className="sa-learning-mode" style={{ marginTop:12, padding:'10px 14px', maxWidth:600,
      borderRadius:10, border:'1px solid var(--border)', background:'var(--bg-tinted)',
      fontSize:12.5, lineHeight:1.55, color:'var(--ink-2)' }}>
      <div style={{ fontWeight:700, color:'var(--ink-1)' }}>{said}</div>
      <div>The weights and task switches saved on this page are kept for this page only: no analysis reads them yet.</div>
    </div>
  );
}

function Stat({ label, value, max, hint }) {
  return (
    <div className="agents-stat-card" style={{ padding:'10px 16px', background:'var(--bg-surface)', border:'1px solid var(--border)',
      borderRadius:12, minWidth:120 }}>
      <div className="eyebrow" style={{ fontSize:9, marginBottom:4 }}>{label}</div>
      <div style={{ display:'flex', alignItems:'baseline', gap:4 }}>
        <span className="mono" style={{ fontSize:20, fontWeight:700, color:'var(--ink-1)' }}>{value}</span>
        {max && <span className="mono" style={{ fontSize:13, color:'var(--ink-3)' }}>/ {max}</span>}
      </div>
      {hint && <div style={{ fontSize:10, color:'var(--ink-3)', marginTop:2 }}>{hint}</div>}
    </div>
  );
}

function Pipeline({ agents, onOpenAgent, canTune }) {
  return (
    <div className="card" style={{ padding:24, position:'relative', overflow:'hidden' }}>
      <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:18 }}>
        <div className="eyebrow">Live pipeline</div>
        <span style={{ fontSize:11, color:'var(--ink-3)' }}>How a ticker flows through your agents{canTune && <> · <strong style={{color:'var(--cyan)'}}>Click any agent to tune</strong></>}</span>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'auto 1fr auto', alignItems:'center', gap:24 }}>
        <PipelineNode icon={<Icon.Search size={18}/>} title="Ticker" sub={localStorage.getItem('sa_last_ticker') || 'Any stock'} color="var(--ink-2)"/>
        <div style={{ position:'relative', minHeight:120 }}>
          <div style={{ display:'grid', gridTemplateColumns:`repeat(${Math.max(agents.length,1)}, 1fr)`, gap:8 }}>
            {agents.map((a,i) => (
              <div key={a.key} onClick={()=>onOpenAgent?.(a.key)} style={{
                padding:'10px 8px', borderRadius:10,
                background:'linear-gradient(180deg, var(--bg-surface), var(--bg-tinted))',
                border:'1px solid var(--border)', textAlign:'center',
                animation: `float-soft 3s ease-in-out infinite ${i*.15}s`,
                cursor:'pointer', transition:'transform .15s, box-shadow .15s'
              }}
                onMouseEnter={e=>{e.currentTarget.style.transform='translateY(-3px)'; e.currentTarget.style.boxShadow='var(--shadow-md)'; e.currentTarget.style.borderColor='var(--cyan)';}}
                onMouseLeave={e=>{e.currentTarget.style.transform=''; e.currentTarget.style.boxShadow=''; e.currentTarget.style.borderColor='var(--border)';}}>
                <div style={{ fontSize:18 }}>{a.icon}</div>
                <div style={{ fontSize:10, color:'var(--ink-2)', fontWeight:600, marginTop:4, lineHeight:1.2 }}>
                  {a.name.split(' ')[0]}
                </div>
              </div>
            ))}
          </div>
          <div style={{ position:'absolute', left:-24, top:'50%', transform:'translateY(-50%)', color:'var(--border-strong)' }}>
            <Icon.ChevronR size={14}/>
          </div>
          <div style={{ position:'absolute', right:-24, top:'50%', transform:'translateY(-50%)', color:'var(--border-strong)' }}>
            <Icon.ChevronR size={14}/>
          </div>
        </div>
        <PipelineNode icon={<Icon.Sparkles size={18}/>} title="Verdict" sub="Aggregator" color="var(--cyan)" highlight/>
      </div>
    </div>
  );
}

function PipelineNode({ icon, title, sub, color, highlight }) {
  return (
    <div style={{
      padding:'14px 18px', borderRadius:12,
      background: highlight ? 'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))' : 'var(--bg-tinted)',
      border:'1px solid var(--border)', minWidth:140, textAlign:'center'
    }}>
      <div style={{
        width:36, height:36, borderRadius:9,
        background: highlight ? 'linear-gradient(135deg,#22d3ee,#a78bfa)' : 'var(--bg-surface)',
        color: highlight ? '#fff' : color,
        display:'grid', placeItems:'center', margin:'0 auto 8px',
        boxShadow: highlight ? '0 4px 14px rgba(8,145,178,.3)' : 'none'
      }}>{icon}</div>
      <div style={{ fontSize:12, fontWeight:700 }}>{title}</div>
      <div style={{ fontSize:10, color:'var(--ink-3)', marginTop:2 }}>{sub}</div>
    </div>
  );
}

function AgentCard({ a, tasks=[], canTune, onToggle, onOpen }) {
  const activeTasks = tasks.filter(t => t.enabled).length;
  return (
    <div className="card" style={{
      padding:0, overflow:'hidden', cursor:'pointer',
      opacity: a.enabled ? 1 : 0.6,
      transition:'transform .15s, box-shadow .15s'
    }}
      onClick={onOpen}
      onMouseEnter={e=>{e.currentTarget.style.transform='translateY(-2px)'; e.currentTarget.style.boxShadow='var(--shadow-md)'}}
      onMouseLeave={e=>{e.currentTarget.style.transform=''; e.currentTarget.style.boxShadow='var(--shadow-sm)'}}>
      <div style={{
        padding:'12px 18px', display:'flex', alignItems:'center', gap:10,
        borderBottom:'1px solid var(--border)',
        background: a.enabled ? 'linear-gradient(90deg, var(--cyan-soft), transparent)' : 'transparent'
      }}>
        <span style={{
          width:8, height:8, borderRadius:'50%',
          background: a.enabled ? 'var(--buy)' : 'var(--ink-3)'
        }}/>
        <span style={{ fontSize:11, fontWeight:700, letterSpacing:'.08em', textTransform:'uppercase',
          color: a.enabled ? 'var(--buy-strong)' : 'var(--ink-3)' }}>
          {a.enabled ? 'Plugged in' : 'Unplugged'}
        </span>
        {canTune && (
          <button className="sa-tune-control" aria-label={`Plug ${a.name} in or out`}
            onClick={(e)=>{e.stopPropagation(); onToggle();}} style={{
            marginLeft:'auto', width:36, height:20, borderRadius:999, border:'none', padding:0,
            background: a.enabled ? 'var(--cyan)' : 'var(--border-strong)',
            position:'relative', cursor:'pointer', transition:'background .2s'
          }}>
            <span style={{
              position:'absolute', top:2, left: a.enabled ? 18 : 2, width:16, height:16,
              background:'#fff', borderRadius:'50%', boxShadow:'0 1px 3px rgba(0,0,0,.2)',
              transition:'left .2s'
            }}/>
          </button>
        )}
      </div>

      <div style={{ padding:18 }}>
        <div style={{ display:'flex', alignItems:'flex-start', gap:14, marginBottom:14 }}>
          <div style={{
            width:48, height:48, borderRadius:12,
            background: 'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
            display:'grid', placeItems:'center', fontSize:24, flexShrink:0
          }}>{a.icon}</div>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:14, fontWeight:700, marginBottom:2 }}>{a.name}</div>
            <div style={{ fontSize:11, color:'var(--ink-3)' }} className="mono">{a.key}</div>
          </div>
        </div>

        <div style={{ fontSize:13, color:'var(--ink-2)', lineHeight:1.5, marginBottom:12, minHeight:38 }}>
          {a.beginner}
        </div>

        {tasks.length > 0 && (
          <div style={{ display:'flex', flexWrap:'wrap', gap:4, marginBottom:12, minHeight:24 }}>
            {tasks.slice(0,3).map(t => (
              <span key={t.key} style={{
                padding:'3px 8px', borderRadius:6, fontSize:10, fontWeight:600,
                background: t.enabled ? 'var(--cyan-soft)' : 'var(--bg-tinted)',
                color: t.enabled ? 'var(--cyan)' : 'var(--ink-3)'
              }}>
                {t.enabled ? '●' : '○'} {t.label.length > 18 ? t.label.slice(0,16)+'…' : t.label}
              </span>
            ))}
            {tasks.length > 3 && (
              <span style={{ padding:'3px 8px', fontSize:10, color:'var(--ink-3)', fontWeight:600 }}>+{tasks.length - 3}</span>
            )}
          </div>
        )}

        <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:10, fontSize:11, color:'var(--ink-3)' }}>
          <Icon.Check size={12} c="var(--buy)"/>
          <span><strong style={{ color:'var(--ink-2)' }}>{activeTasks}/{tasks.length}</strong> tasks active</span>
        </div>

        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:6 }}>
          <span style={{ fontSize:11, color:'var(--ink-3)', fontWeight:600 }}>Weight</span>
          <div style={{ flex:1, height:5, background:'var(--bg-tinted)', borderRadius:999, overflow:'hidden' }}>
            <div style={{ width: (a.weight*100/0.25)+'%', height:'100%',
              background:'linear-gradient(90deg, var(--cyan), var(--violet))',
              borderRadius:999 }}/>
          </div>
          <span className="mono" style={{ fontSize:12, fontWeight:700, color:'var(--ink-1)' }}>{(a.weight*100).toFixed(0)}%</span>
        </div>

        <div style={{ marginTop:10, paddingTop:10, borderTop:'1px solid var(--border)',
          display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <span style={{ fontSize:11, color:'var(--cyan)', fontWeight:600 }}>{canTune ? 'Tap to tune weight & tasks' : 'Tap for details'}</span>
          <Icon.ChevronR size={13} c="var(--cyan)"/>
        </div>
      </div>
    </div>
  );
}

function _timeAgo(isoStr) {
  if (!isoStr) return '—';
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs > 1 ? 's' : ''} ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days > 1 ? 's' : ''} ago`;
}

function AgentDrawer({ a, tasks=[], canTune, onClose, onToggle, onWeight, onWeightSave, onToggleTask, saveStatus }) {
  const activeCount = tasks.filter(t => t.enabled).length;
  const [recentRuns, setRecentRuns] = useStateAg([]);
  const [runsLoading, setRunsLoading] = useStateAg(true);

  // Fetch history for all watchlist tickers on mount / agent change
  useEffectAg(() => {
    setRunsLoading(true);
    const tickers = window.WATCHLIST || [];
    Promise.all(
      tickers.map(sym =>
        fetch(`/history/${sym}?limit=5`)
          .then(r => r.ok ? r.json() : [])
          .catch(() => [])
      )
    ).then(results => {
      const runs = results
        .flat()
        .map(row => {
          let agentScore = null;
          try {
            const scores = typeof row.agent_scores === 'string'
              ? JSON.parse(row.agent_scores)
              : (row.agent_scores || {});
            agentScore = scores[a.key];
          } catch {}
          return { ticker: row.ticker, score: agentScore, runAt: row.run_at };
        })
        .filter(r => r.score != null)
        .sort((x, y) => new Date(y.runAt) - new Date(x.runAt))
        .slice(0, 5);
      setRecentRuns(runs);
      setRunsLoading(false);
    });
  }, [a.key]);

  return (
    <>
      <div onClick={onClose} style={{
        position:'fixed', inset:0, background:'rgba(15,23,42,.4)', backdropFilter:'blur(4px)', zIndex:50,
        animation:'fade-in .2s'
      }}/>
      <style>{`
        @keyframes fade-in { from { opacity:0; } to { opacity:1; } }
        @keyframes slide-in { from { transform: translateX(100%); } to { transform: translateX(0); } }
      `}</style>
      <aside className="drawer-panel" style={{ width:520, zIndex:55 }}>
        <div className="drawer-handle"/>
        {/* header */}
        <div style={{ padding:'20px 24px', borderBottom:'1px solid var(--border)',
          display:'flex', alignItems:'flex-start', gap:14 }}>
          <div style={{ width:52, height:52, borderRadius:13,
            background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
            display:'grid', placeItems:'center', fontSize:26 }}>{a.icon}</div>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:18, fontWeight:700 }}>{a.name}</div>
            <div className="mono" style={{ fontSize:11, color:'var(--ink-3)' }}>{a.key}</div>
          </div>
          <button onClick={onClose} style={{
            width:32, height:32, borderRadius:8, border:'1px solid var(--border)',
            background:'transparent', display:'grid', placeItems:'center', color:'var(--ink-2)' }}>
            <Icon.X size={16}/>
          </button>
        </div>

        <div style={{ padding:24, overflowY:'auto', flex:1, display:'flex', flexDirection:'column', gap:24 }}>
          {/* Plug toggle */}
          <div style={{
            padding:'14px 16px', border:'1px solid var(--border)', borderRadius:12,
            display:'flex', alignItems:'center', gap:14,
            background: a.enabled ? 'var(--cyan-soft)' : 'var(--bg-base)'
          }}>
            <Icon.Plug size={20} c={a.enabled ? 'var(--cyan)' : 'var(--ink-3)'}/>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:13, fontWeight:700 }}>{a.enabled ? 'This agent is plugged in' : 'This agent is unplugged'}</div>
              <div style={{ fontSize:12, color:'var(--ink-3)', marginTop:2 }}>
                {a.enabled ? 'It contributes to every verdict.' : 'Verdicts ignore this agent until plugged in.'}
              </div>
            </div>
            {canTune && (
              <button className="sa-tune-control" onClick={onToggle} style={{
                padding:'8px 14px', borderRadius:8, border:'1px solid var(--border-strong)',
                background:'var(--bg-surface)', fontSize:12, fontWeight:600, color:'var(--ink-1)'
              }}>{a.enabled ? 'Unplug' : 'Plug in'}</button>
            )}
          </div>

          {/* Tasks */}
          <Section title={`Tasks · ${activeCount} of ${tasks.length} active`}>
            <p style={{ fontSize:12, color:'var(--ink-3)', lineHeight:1.5, margin:'0 0 14px' }}>
              {canTune
                ? "Each task is one specific signal this agent watches. Toggle off any you don't care about — the agent skips them on its next run."
                : 'Each task is one specific signal this agent watches.'}
            </p>
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {tasks.map(t => (
                <TaskRow key={t.key} t={t} disabled={!a.enabled} canTune={canTune} onToggle={()=>onToggleTask(t.key)}/>
              ))}
            </div>
          </Section>

          {/* What it watches */}
          <Section title="What it watches">
            <p style={{ fontSize:13, color:'var(--ink-2)', lineHeight:1.6, margin:'0 0 10px' }}>
              {a.beginner}
            </p>
            <p style={{ fontSize:12, color:'var(--ink-3)', lineHeight:1.6, margin:0, fontStyle:'italic' }}>
              Technical: {a.desc}
            </p>
          </Section>

          {/* Weight: a slider for the owner, the value for everyone else */}
          {!canTune && (
            <Section title="Weight in the verdict">
              <p style={{ fontSize:12, color:'var(--ink-3)', lineHeight:1.5, margin:'0 0 10px' }}>
                How much this agent's view counts in the final score.
              </p>
              <span className="mono" style={{ fontWeight:700, fontSize:14 }}>{(a.weight*100).toFixed(0)}%</span>
            </Section>
          )}
          {canTune && (
          <Section title="Weight in the verdict">
            <p style={{ fontSize:12, color:'var(--ink-3)', lineHeight:1.5, margin:'0 0 16px' }}>
              How much this agent's view counts in the final score. Drag and release to save — all weights must sum to ~100%.
            </p>
            <div style={{ display:'flex', alignItems:'center', gap:14 }}>
              <input className="sa-tune-control" type="range" min="0" max="0.30" step="0.01" value={a.weight}
                onChange={e => onWeight(parseFloat(e.target.value))}
                onMouseUp={e => onWeightSave(parseFloat(e.target.value))}
                onTouchEnd={e => onWeightSave(parseFloat(e.target.value))}
                disabled={!a.enabled}
                style={{ flex:1, accentColor:'var(--cyan)' }}/>
              <div style={{
                minWidth:64, padding:'6px 10px', borderRadius:8, background:'var(--bg-tinted)',
                textAlign:'center'
              }}>
                <span className="mono" style={{ fontWeight:700, fontSize:14 }}>{(a.weight*100).toFixed(0)}%</span>
              </div>
            </div>
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:10, color:'var(--ink-3)', marginTop:6 }}>
              <span>Off</span><span>Default</span><span>Heavy</span>
            </div>
            {/* Save status inline */}
            {saveStatus && (
              <div style={{
                marginTop:10, padding:'6px 10px', borderRadius:8, fontSize:11, fontWeight:600,
                background: saveStatus==='saving' ? 'var(--bg-tinted)' :
                            saveStatus==='saved'  ? 'var(--buy-soft)'  : 'var(--sell-soft)',
                color: saveStatus==='saving' ? 'var(--ink-3)' :
                       saveStatus==='saved'  ? 'var(--buy-strong)' : 'var(--sell-strong)',
              }}>
                {saveStatus==='saving' ? '⟳ Saving weights…' :
                 saveStatus==='saved'  ? '✓ Weights saved to server' :
                 '⚠ ' + (saveStatus.error || 'Error saving')}
              </div>
            )}
          </Section>
          )}

          {/* Recent runs — live from /history/{ticker} */}
          <Section title="Recent runs">
            {runsLoading ? (
              <div style={{ color:'var(--ink-3)', fontSize:12, padding:'10px 0' }}>Loading history…</div>
            ) : recentRuns.length === 0 ? (
              <div style={{ color:'var(--ink-3)', fontSize:12, padding:'10px 0' }}>
                No analysis runs found yet. Run an analysis from the Home page.
              </div>
            ) : (
              <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                {recentRuns.map((r, i) => (
                  <div key={i} style={{
                    display:'grid', gridTemplateColumns:'1fr auto auto', gap:12, alignItems:'center',
                    padding:'10px 12px', background:'var(--bg-base)', borderRadius:8
                  }}>
                    <span className="mono" style={{ fontSize:12, fontWeight:700 }}>{r.ticker}</span>
                    <span className="mono" style={{
                      fontSize:12, fontWeight:700,
                      color: r.score >= 0.7 ? 'var(--buy-strong)' : r.score >= 0.5 ? 'var(--neutral)' : 'var(--sell-strong)'
                    }}>{r.score.toFixed(2)}</span>
                    <span style={{ fontSize:11, color:'var(--ink-3)' }}>{_timeAgo(r.runAt)}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Data sources */}
          <Section title="Data sources">
            <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
              {(window.AGENT_SOURCES?.[a.key] || ['LLM knowledge','Serper news','yfinance']).map(s => (
                <span key={s} style={{
                  padding:'4px 10px', borderRadius:999, background:'var(--bg-tinted)',
                  fontSize:11, color:'var(--ink-2)', fontWeight:600
                }}>{s}</span>
              ))}
            </div>
          </Section>
        </div>
      </aside>
    </>
  );
}

function TaskRow({ t, disabled, canTune, onToggle }) {
  return (
    <div style={{
      display:'grid', gridTemplateColumns:'1fr auto', gap:12, alignItems:'center',
      padding:'12px 14px', borderRadius:10,
      background: t.enabled ? 'var(--bg-base)' : 'transparent',
      border:'1px solid var(--border)',
      opacity: disabled ? 0.5 : 1,
      transition:'background .15s'
    }}>
      <div style={{ minWidth:0 }}>
        <div style={{ fontSize:13, fontWeight:600, color: t.enabled ? 'var(--ink-1)' : 'var(--ink-3)' }}>{t.label}</div>
        <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:2, lineHeight:1.4 }}>{t.beginner}</div>
        <div className="mono" style={{ fontSize:10, color:'var(--ink-3)', marginTop:6 }}>{t.source}</div>
      </div>
      {canTune ? (
        <button className="sa-tune-control" onClick={onToggle} disabled={disabled} style={{
          width:34, height:20, borderRadius:999, border:'none', padding:0,
          background: t.enabled ? 'var(--cyan)' : 'var(--border-strong)',
          position:'relative', cursor: disabled ? 'not-allowed' : 'pointer', transition:'background .2s'
        }}>
          <span style={{
            position:'absolute', top:2, left: t.enabled ? 16 : 2, width:16, height:16,
            background:'#fff', borderRadius:'50%', boxShadow:'0 1px 3px rgba(0,0,0,.2)',
            transition:'left .2s'
          }}/>
        </button>
      ) : (
        <span style={{ fontSize:11, fontWeight:600, color: t.enabled ? 'var(--cyan)' : 'var(--ink-3)' }}>
          {t.enabled ? 'On' : 'Off'}
        </span>
      )}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom:10 }}>{title}</div>
      {children}
    </div>
  );
}

window.AGENT_SOURCES = {
  sales_demand:      ['Serper news','FADA','SIAM','Vahan'],
  fundamentals:      ['yfinance','Serper news','NSE filings'],
  pattern_analysis:  ['yfinance OHLCV','RSI/MACD/BB (C++)'],
  raw_materials:     ['yfinance commodities','Serper news'],
  sentiment:         ['Serper news','Twitter/Reddit','YouTube'],
  policy_regulatory: ['Tavily','Serper','gov circulars'],
  competitive_intel: ['Serper news','peer baskets'],
  risk_macro:        ['yfinance INR/crude','macro cache'],
  valuation_catalyst:['LLM knowledge','peer P/E','price targets'],
};

window.AgentsPage = AgentsPage;
