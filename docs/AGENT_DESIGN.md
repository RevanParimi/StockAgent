# Agent Design Reference

> Updated: 2026-05-12 · 9 automobile agents active · 3 sectors in progress (20 additional agents) · 17 sectors in pipeline

---

## Execution Architecture

```
AutomobileAgentOrchestrator.analyse(ticker)
       │
       ├─ _resolve_ticker()  →  LLM  →  StockQuery
       │
       ├─ LangGraph worker pool  (START → [Send × 9] → run_agent → END)
       │     RetryPolicy(max_attempts=2) per node
       │     Fan-in via _merge_dicts reducer (race-condition-safe)
       │     SalesDemandAgent.run()
       │     RawMaterialsAgent.run()
       │     FundamentalsAgent.run()
       │     PatternAnalysisAgent.run()
       │     SentimentAgent.run()
       │     PolicyRegulatoryAgent.run()
       │     CompetitiveIntelAgent.run()
       │     RiskMacroAgent.run()
       │     ValuationCatalystAgent.run()
       │
       └─ SignalAggregator.run()  →  FinalReport

Async path (FastAPI/WebSocket): analyse_async() uses graph.astream_events() — progress_callback
  fires as each agent completes (real-time), identical behaviour to the previous asyncio.gather path.
  HTTP/WS requests arrive via the TypeScript gateway (:3000) which proxies to Python :8001.
```

---

## BaseAgent (`core/pipeline/base_agent.py`)

All 9 agents inherit from `BaseAgent`. Subclasses implement 3 things:

| Abstract | Signature | Purpose |
|---|---|---|
| `agent_name` | `@property → str` | snake_case id, matches key in `AGENT_WEIGHTS` |
| `_build_prompt` | `(query, context) → (system_prompt, user_prompt)` | Assembles the LLM prompt |
| `_parse_output` | `(data: dict, ticker: str) → AgentOutput` | Parses JSON response into typed output |

**Context priority** in `_gather_context()`:
1. RAG retrieval — if `RAG_ENABLED=true` (disabled by default)
2. `ContextBuilder.build(agent_name, query)` — live data from fetchers
3. Generic stub — ticker + company name only (fallback when fetchers fail)

**Retry logic**: 3 attempts with exponential backoff on `APIError`, `RateLimitError`, `APITimeoutError`.

---

## 9 Automobile Agents

### 1. SalesDemandAgent
**Score dimensions:** FADA/SIAM dispatch · EV Vahan registrations · dealer inventory · export/import · used-car price index  
**Context:** Serper news (CONTEXT_SEARCH_QUERIES from `config/prompts/automobile/sales_demand.py`)  
**Schema:** `SalesDemandOutput` + `SalesDemandSubScores`

### 2. RawMaterialsAgent
**Score dimensions:** steel/aluminium · platinum/palladium · crude/polymer · power tariff · commodities trend  
**Context:** yfinance prices (SLX, AA, PPLT, PALL, CL=F, BZ=F) → `get_raw_materials_context()` + Serper (1 query)  
**Schema:** `RawMaterialsOutput` + `RawMaterialsSubScores`

### 3. FundamentalsAgent
**Score dimensions:** revenue/EBITDA delta · margin vs peers · order book · attrition/headcount · promoter/FII/DII flow  
**Context:** `get_fundamentals_context(ticker)` (yfinance quarterly financials) + Serper news  
**Schema:** `FundamentalsOutput` + `FundamentalsSubScores`  
**Note:** yfinance may 404 for newly-listed stocks (e.g. ATHERENERGY.NS) — falls back to LLM knowledge.

### 4. PatternAnalysisAgent
**Score dimensions:** price cycle position · seasonal pattern · RSI/MACD/BB · breakout/support zones · peer correlation  
**Context:** `get_technical_context(ticker)` → 10yr OHLCV → RSI, MACD, Bollinger, support/resistance, peer beta  
**Schema:** `PatternAnalysisOutput` + `PatternAnalysisSubScores`

### 5. SentimentAgent
**Score dimensions:** news NLP · management tone · Twitter/Reddit · YouTube spikes · dealer/consumer feedback  
**Context:** Serper news  
**Schema:** `SentimentOutput` + `SentimentSubScores`

### 6. PolicyRegulatoryAgent
**Score dimensions:** FAME/EV subsidy · emission norms · union budget duties · PLI scheme · state EV incentives  
**Context:** Tavily full-page (policy PDFs, government circulars) + Serper  
**Schema:** `PolicyRegulatoryOutput` + `PolicyRegulatorySubScores`

### 7. CompetitiveIntelAgent
**Score dimensions:** EV market share · new model pipeline · JV/acquisitions · ADAS/safety ratings · competitive position  
**Context:** Serper news  
**Schema:** `CompetitiveIntelOutput` + `CompetitiveIntelSubScores`

### 8. RiskMacroAgent
**Score dimensions:** INR/USD & crude exposure · commodity prices · RBI repo/EMI impact · emission policy risk · **global geopolitical risk**  
**Global geopolitical risk** covers 4 channels: oil supply shock · FII outflow · INR depreciation · supply chain disruption (China semiconductors/EV components)  
**Context:** `get_macro_context()` (yfinance: INR=X, CL=F, SLX, AA) + macro_cache OR Serper  
**Schema:** `RiskMacroOutput` + `RiskMacroSubScores`  
**Macro cache:** `get_macro_cache("automobile")` — pre-populated by `--micro-loop` flag; saves 3 Serper calls per run.

### 9. ValuationCatalystAgent *(Gap 2, added eaf52ab)*
**Score dimensions:** P/E discount vs 5yr history · P/E discount vs peer median · discount reason clarity · catalyst strength · price target confidence  
**Context:** `_build_generic` (ContextBuilder method not yet implemented — uses LLM knowledge only)  
**Schema:** `ValuationCatalystOutput` + `ValuationCatalystSubScores`  
**Extra output fields:** `fair_value_estimate`, `current_discount_pct`, `discount_reason`, `recovery_catalysts[]`, `price_target`, `recovery_timeline_quarters`  
**These 5 fields bubble up to `FinalReport`** via SignalAggregator (Gap 3 fix).

---

## SignalAggregator (`core/pipeline/signal_aggregator.py`)

1. Applies `AGENT_WEIGHTS` (or `learned_weights` from RL loop) to each agent's `overall_score`
2. Detects conflicts: any pair with score delta ≥ 0.30 → flagged
3. LLM call with all scores + conflicts → JSON: `{verdict, final_score, conviction_drivers, top_risks, investment_thesis, conflicts_resolved}`
4. Extracts valuation fields from `valuation_catalyst` output → populates `FinalReport`
5. Returns `FinalReport`

**Verdict thresholds** (from `settings.SCORE_THRESHOLDS`):

| Verdict | Score range |
|---|---|
| STRONG BUY | 0.75 – 1.00 |
| BUY | 0.55 – 0.75 |
| NEUTRAL | 0.40 – 0.55 |
| SELL | 0.20 – 0.40 |
| STRONG SELL | 0.00 – 0.20 |

---

## Banking / BFSI — 6 Agents *(In Progress)*

**Stocks covered:** HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK, INDUSINDBK, BANDHANBNK, RBLBANK, YESBANK, BAJFINANCE, MUTHOOTFIN and more

Agent files live in `src/backend/sectors/banking_bfsi/agents/`. Prompts are in `src/backend/sectors/banking_bfsi/prompts/`. All 6 agents inherit `BaseAgent` and have full `_parse_output` implementations. Data fetchers are pending wiring.

### 1. BFSIFundamentalsAgent (`fundamentals`)
**What it measures:** Asset quality (GNPA/NPA ratios, PCR), net interest income (NIM, CASA deposit mix), capital adequacy (CRAR/CET1), profitability (RoA, RoE, credit cost), loan book composition (retail/corporate/SME split).

| Sub-score | What it captures |
|---|---|
| `asset_quality` | GNPA %, NPA %, PCR — lower GNPA and higher PCR = better |
| `net_interest` | NIM spread and CASA ratio — higher NIM + CASA = stronger core income |
| `capital_adequacy` | CRAR and CET1 buffers above regulatory minimums |
| `profitability` | RoA, RoE, credit cost trend — directional over last 4 quarters |
| `loan_mix` | Retail vs corporate vs SME — retail mix typically commands valuation premium |

### 2. BFSIInstitutionalAgent (`institutional`)
**What it measures:** FII/DII shareholding changes, AMFI mutual fund category flow, promoter pledge delta, SAST bulk-acquisition filings, BSE block/bulk deal data.

| Sub-score | What it captures |
|---|---|
| `fii_dii_flow` | Net quarterly directional change — FII buying = confidence signal |
| `promoter_holding` | Pledge % change — rising pledge = stress flag |
| `insider_trades` | Director/KMP SEBI disclosures of open-market trades |
| `amfi_mf_flow` | Sector-specific MF category net inflows/outflows |
| `bulk_block_deals` | Institutional buy/sell blocks on BSE — size and direction |

**Note:** PCR/OI derivative data excluded — exchange terms-of-service restriction.

### 3. BFSIMacroPolicyAgent (`macro_policy`)
**What it measures:** RBI MPC rate cycle, system-wide credit and deposit growth, LAF liquidity conditions, SEBI/RBI regulatory circulars, fiscal policy impact (government borrowing programme, PSU recapitalisation, IBC resolution pipeline).

| Sub-score | What it captures |
|---|---|
| `rbi_rate_cycle` | Repo rate trajectory — rate cuts expand NIM room; rate hikes compress it |
| `system_credit` | Industry credit growth YoY — proxy for loan book opportunity |
| `liquidity_conditions` | LAF net borrowing/lending position — surplus = easier lending environment |
| `regulatory_actions` | Recent SEBI/RBI enforcement, PCA framework triggers, license conditions |
| `fiscal_policy` | Government borrowing programme, PSU bank recap, IBC case pipeline |

### 4. BFSIRiskAgent (`risk`)
**What it measures:** NPA slippage rate, ALM (Asset-Liability Management) mismatch, regulatory enforcement orders, cyber/fraud incident disclosures, concentration risk in loan book.

| Sub-score | What it captures |
|---|---|
| `asset_quality_trend` | Fresh NPA slippage this quarter — directional worsening/improvement |
| `concentration_risk` | Top-10 borrower % of loan book; sectoral concentration |
| `deposit_stability` | CASA vs term deposit split; bulk deposit reliance |
| `regulatory_risk` | PCA status, RBI audit observations, SEBI notices |
| `cyber_fraud_risk` | CERT-In / RBI fraud disclosure reports, recovery % |

**Note:** Real-time interbank rates, SWIFT flows, and FX swap desk data are excluded (require paid/restricted data access).

### 5. BFSIPatternAgent (`pattern_analysis`)
**What it measures:** 10-year price cycle positioning, rate-cut seasonality patterns, RSI/MACD/Bollinger Band momentum, breakout and support zones, relative strength vs Nifty Bank index.

| Sub-score | What it captures |
|---|---|
| `price_cycle` | Where stock sits in its historical bull/bear cycle |
| `momentum` | RSI, MACD crossover state |
| `breakout_zones` | Distance from key resistance/support levels |
| `relative_strength` | Return vs Nifty Bank over 30/90 days |
| `volume_pattern` | Volume confirmation on up/down moves |

### 6. BFSIUniverseSetupAgent (`universe_setup`)
Infrastructure agent. Resolves bank/NBFC/insurance tickers, normalises NSE/BSE codes, validates sector routing, and ensures the correct agent pipeline is loaded for each BFSI sub-type. Does not produce an analysis score.

---

## IT Sector — 8 Agents *(In Progress)*

**Stocks covered:** TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM, COFORGE, MPHASIS, PERSISTENT and more

Agent files live in `src/backend/sectors/it_sector/agents/`. All 8 agents have full `_parse_output` implementations.

### 1. ITFundamentalsAgent (`fundamentals`)
**What it measures:** Revenue growth in constant currency (removes FX noise), EBIT operating margins, TCV of new deal wins, employee attrition rate, valuation vs peer group.

| Sub-score | What it captures |
|---|---|
| `revenue_growth` | CC revenue growth YoY and QoQ — currency-neutral organic growth |
| `ebit_margins` | Operating margin trend — attrition and wage cycles compress margins |
| `deal_wins` | TCV of new bookings this quarter — leading indicator for future revenue |
| `attrition` | Trailing 12-month annualised attrition — high attrition = cost and delivery risk |
| `valuation` | P/E and EV/EBITDA vs 5-year history and peer median |

### 2. ITGlobalMacroAgent (`global_macro`)
**What it measures:** US enterprise IT spending environment, Federal Reserve rate impact on client capex decisions, USD/INR rate (directly affects rupee earnings), geopolitical risk, M&A activity as consolidation signal.

| Sub-score | What it captures |
|---|---|
| `us_tech_spend` | Gartner/IDC forecasts, US CIO survey signals, client budget commentary |
| `fed_rate_impact` | Higher rates → clients defer discretionary IT spend |
| `usd_inr` | Weaker INR = higher rupee revenue per USD earned |
| `geopolitical` | India-US trade relations, tariff risk, offshoring regulatory pressure |
| `ma_activity` | Consolidation among clients or sector peers — can signal demand shift |

### 3. ITInsiderAgent (`insider_smart_money`)
**What it measures:** Promoter SAST (>2% threshold) filings, director open-market trades, AMFI MF sectoral flows, FII futures positioning in IT index, block deal activity.

| Sub-score | What it captures |
|---|---|
| `promoter_activity` | SAST disclosures — directional signal from informed insiders |
| `director_trades` | SEBI-disclosed KMP buy/sell in open market |
| `amfi_mf_flow` | Sector-level MF inflow/outflow from AMFI monthly data |
| `fii_futures` | FII net long/short in Nifty IT futures — positioning proxy |
| `block_deals` | Large institutional transactions on BSE — size, direction, counterparty type |

### 4. ITPeerBenchmarkAgent (`peer_benchmark`)
**What it measures:** Ranks the stock against its IT sector peers on five performance dimensions to identify relative outperformance or underperformance.

| Sub-score | What it captures |
|---|---|
| `revenue_growth_rank` | Percentile position among peers on CC revenue growth |
| `margin_rank` | Percentile on EBIT margins — controls for scale differences |
| `deal_momentum_rank` | Percentile on TCV growth trajectory |
| `attrition_rank` | Inverse rank on attrition — lower attrition = better score |
| `valuation_gap` | P/E z-score vs peer median — identifies discount/premium vs warranted |

### 5. ITRiskMacroAgent (`risk_macro`)
**What it measures:** H1B/L1 visa policy risk (affects US delivery model), AI disruption risk to service revenue lines, client concentration, FX hedge effectiveness, talent supply risk in key skills.

| Sub-score | What it captures |
|---|---|
| `visa_risk` | H1B/L1 policy changes, denial rates — affects US onsite staffing economics |
| `ai_disruption` | AI automation risk to application maintenance, testing, BPO revenue lines |
| `client_concentration` | Top-5 client % of revenue — single-client event risk |
| `fx_hedge` | Hedge ratio and coverage period for USD/EUR/GBP receivables |
| `talent_risk` | Niche skill availability (cloud, AI, ERP) — talent scarcity = cost pressure |

### 6. ITSentimentAgent (`sentiment`)
**What it measures:** Earnings call management tone via NLP, analyst note sentiment index, LinkedIn hiring activity as forward demand signal, technology community signals.

| Sub-score | (sector-equivalent of automobile SentimentAgent — 5 NLP dimensions) |
|---|---|
| Tone indicators | Earnings call positivity/negativity delta vs prior quarter |

### 7. ITTranscriptNLPAgent (`transcript_nlp`)
**What it measures:** Deep NLP analysis of management earnings call transcripts — the most unique IT-sector agent. Extracts signals that raw financials miss.

| Sub-score | What it captures |
|---|---|
| `guidance_delta` | Beat/miss vs consensus guidance, tone of forward commentary |
| `vertical_mix` | Revenue split shift across BFSI/retail/hi-tech/healthcare — BFSI heavy = US banking risk |
| `geography_colour` | Management language about US, Europe, APAC pipeline — demand directional signals |
| `ai_deal_count` | Number of named AI/GenAI deal wins mentioned — AI monetisation progress |
| `analyst_pushback` | Volume and intensity of adversarial analyst questions — proxy for credibility gaps |

### 8. ITPatternAnalysisAgent (`pattern_analysis`)
Technical analysis agent. Identical logic to automobile's `PatternAnalysisAgent` but uses Nifty IT index (`^CNXIT`) for sector-relative positioning instead of Nifty Auto.

---

## Renewable Energy — 6 Agents *(In Progress)*

**Stocks covered:** ADANIGREEN, TATAPOWER, NTPC, POWERGRID, SJVN, JSWENERGY and more

Agent files live in `src/backend/sectors/renewable_energy/agents/`. All 6 agents have full `_parse_output` implementations.

### 1. REBusinessAgent (`business`)
**What it measures:** Quality and diversity of the revenue-generating asset base — what kind of capacity, under what contracts, for which customers, in which states.

| Sub-score | What it captures |
|---|---|
| `subsector_mix` | Solar/wind/hydro/storage ratio — storage commands valuation premium |
| `ppa_quality` | Contracted tariff level, counterparty (central/state/C&I), remaining PPA term |
| `pipeline_cred` | Under-construction capacity vs announced targets — land acquired, FC achieved, equipment ordered |
| `customer_divers` | Revenue concentration by offtake counterparty — single-DISCOM risk |
| `geography_spread` | State exposure diversification — reduces DISCOM payment risk |

### 2. REFundamentalsAgent (`fundamentals`)
**What it measures:** Asset utilisation, cash quality, debt capacity, and receivables health — the financial health layer unique to capital-heavy RE infrastructure.

| Sub-score | What it captures |
|---|---|
| `capacity_utilisation` | Actual MWh generated vs installed capacity — PLF/CUF ratio |
| `ebitda_quality` | % of EBITDA from contracted vs merchant (spot) revenue |
| `debt_serviceability` | DSCR (Debt Service Coverage Ratio) — can cash flows service project debt |
| `receivables` | DISCOM payment delay in days — high receivables = cash flow risk |
| `leverage` | Net debt / EBITDA — RE companies are inherently levered; trajectory matters |

### 3. RERiskAgent (`risk`)
**What it measures:** Risks specific to operating renewable energy infrastructure in India — payment, curtailment, contractual, execution, and promoter risk.

| Sub-score | What it captures |
|---|---|
| `discom_credit` | State DISCOM financial health ratings, payment delays, restructuring history |
| `curtailment_risk` | % of contracted generation rejected by grid operator — revenue loss |
| `ppa_protection` | Force majeure clause strength, change-in-law protection, dispute resolution |
| `execution_risk` | Under-construction-to-commissioned ratio — commissioning delays = cost overruns |
| `promoter_pledge` | Promoter shares pledged — RE groups often pledge to raise project finance |

### 4. RESentimentPolicyAgent (`sentiment_policy`)
**What it measures:** Government policy environment and global sentiment for renewable energy — the primary driver of valuation re-rating in this sector.

| Sub-score | What it captures |
|---|---|
| `mnre_auction_health` | MNRE tender pipeline, bid/offer ratio, clearing tariffs — supply-demand for RE capacity |
| `budget_allocation` | Union Budget RE allocation, green hydrogen outlay, PLI for modules |
| `policy_tailwinds` | RPO compliance pressure on states, ISTS waiver status, KUSUM scheme |
| `rbi_rate_impact` | Project finance rate direction — 1% rate cut can add 50–80bps to project IRR |
| `module_price` | Chinese solar module spot price — drives new project LCOE and margins |

### 5. RETechnicalAgent (`technical`)
**What it measures:** Technical price action for RE stocks, which are often driven by policy announcement-driven sentiment cycles.

| Sub-score | What it captures |
|---|---|
| `moving_averages` | 50-day/200-day MA relationship — golden/death cross signals |
| `rsi_signal` | 14-day RSI momentum state |
| `macd_weekly` | MACD on weekly chart — longer-cycle trends for infrastructure stocks |
| `volume_catalyst` | Unusual volume accumulation patterns |
| `accumulation_zone` | Institutional buying zone identification |

### 6. REValuationAgent (`valuation`)
**What it measures:** RE-specific valuation metrics — P/E is not used because RE companies reinvest and carry depreciation, making earnings-based multiples misleading.

| Sub-score | What it captures |
|---|---|
| `ev_per_mw` | Enterprise Value per MW of operational capacity — standard RE transaction benchmark |
| `ev_ebitda` | EV/EBITDA vs historical range and comparable listings |
| `tariff_vs_auction` | Current locked-in tariff vs latest MNRE auction clearing price — competitive position |
| `pipeline_dcf` | DCF on under-construction pipeline at reasonable commissioning assumptions |
| `implied_irr` | Back-calculated project IRR from current stock price — fair if IRR > cost of capital |

---

## Implementation Pipeline — 17 Sectors

Prompt templates and agent prompt files exist in `core/config/prompts/` for all sectors below. Data fetchers and pipeline wiring are not yet built.

| Sector key | Name | Indicative stocks |
|---|---|---|
| `agrochem` | Agro-Chemicals | PI Industries, Rallis India, Bayer CropScience, UPL |
| `capgoods` | Capital Goods | L&T, Siemens, ABB, Thermax, Bharat Forge, CG Power |
| `chemicals` | Speciality Chemicals | SRF, Aarti Industries, Deepak Nitrite, Navin Fluorine |
| `defence` | Defence & Aerospace | HAL, BEL, Data Patterns, Bharat Dynamics, Paras Defence |
| `fmcg` | FMCG | HUL, ITC, Nestlé India, Dabur, Marico, Godrej Consumer |
| `hospitality` | Hospitality & Travel | Indian Hotels (Taj), EIH (Oberoi), Lemon Tree, IRCTC |
| `infra` | Infrastructure & Construction | L&T, IRB Infra, KNR Constructions, NCC, PNC Infratech |
| `insurance` | Insurance | HDFC Life, SBI Life, ICICI Prudential, Star Health |
| `logistics` | Logistics & Supply Chain | Blue Dart, Container Corp, TCI Express, Delhivery, VRL |
| `media` | Media & Entertainment | Zee Entertainment, Sun TV, PVR-INOX, Dish TV |
| `metals` | Metals & Mining | Tata Steel, JSW Steel, Hindalco, NMDC, Vedanta |
| `oilgas` | Oil & Gas | Reliance, ONGC, BPCL, IOC, GAIL, Oil India |
| `pharma` | Pharmaceuticals | Sun Pharma, Dr Reddy's, Cipla, Aurobindo, Divis Labs |
| `power` | Power & Utilities | NTPC, Power Grid, CESC, Torrent Power, Tata Power |
| `realestate` | Real Estate | DLF, Godrej Properties, Prestige Estates, Sobha, Brigade |
| `retail` | Retail & Consumer | DMart, Trent, V-Mart, Zomato, Swiggy, Nykaa |
| `telecom` | Telecom | Bharti Airtel, Reliance Jio (unlisted), Indus Towers |

---

## RL Feedback Loop (`intelligence/rl/`)

| Module | Role |
|---|---|
| `stores/prediction_store.py` | Saves `{ticker, run_id, verdict, final_score, date}` |
| `agents/feedback_agent.py` | After N days: compares prediction vs actual price move, generates accuracy signal |
| `agents/weight_adapter.py` | Updates `AGENT_WEIGHTS` based on which agents were most predictive |
| `workflows/generate_forecast.py` | Pre-injects learned weights into orchestrator before a run |
| `workflows/daily_review.py` | Scheduled daily (4:30pm IST via Python APScheduler): process predictions older than review_window, update weights |

> **Scheduler note:** The RL daily review runs in `services/scheduler/python/scheduler.py` (APScheduler, Python).
> The analysis cron job has been moved to the TypeScript gateway (`services/gateway/src/jobs/analysis-cron.ts`).
> The Python scheduler now runs the RL review job only — it must stay Python because it imports `intelligence.rl` directly.
> `AutomobileScheduler` exposes `run_now(tickers)` for immediate manual analysis and `status()` for health monitoring.

Activate by setting `learned_weights` on the orchestrator:
```python
orchestrator._aggregator_weights = weight_adapter.get_weights(ticker)
```

---

## Terminology Reference

Definitions for every domain term, acronym, and architectural keyword used in this codebase. Practical examples are drawn from Indian market context.

---

### Architecture & Framework

| Term | Full Form / Meaning | Practical Example |
|---|---|---|
| **LangGraph** | Graph-based LLM orchestration framework | 9 agent nodes run in parallel via `Send × 9`; results fan-in via `_merge_dicts` reducer |
| **BaseAgent** | Abstract base class all sector agents inherit | Subclasses implement `agent_name`, `_build_prompt`, `_parse_output` — nothing else |
| **SignalAggregator** | Weighted score combiner + LLM conflict resolver | Takes 9 agent scores, flags any pair with delta ≥ 0.30, asks LLM to resolve which signal dominates |
| **Fan-in** | Merge pattern: multiple parallel outputs → single dict | `_merge_dicts` reducer collects all agent `AgentOutput` objects into one dict after parallel execution |
| **RetryPolicy** | Per-node retry with exponential backoff | `max_attempts=2` on each agent node; catches `APIError`, `RateLimitError`, `APITimeoutError` |
| **RAG** | Retrieval-Augmented Generation | LLM response enhanced with retrieved documents from a vector store; disabled by default (`RAG_ENABLED=false`) |
| **ContextBuilder** | Per-agent data fetcher orchestrator | Calls yfinance, Serper, Tavily, and sector-specific fetchers to assemble context before LLM call |
| **RL** | Reinforcement Learning | Agent learns by comparing its predictions against actual outcomes and updating weights |
| **Prediction Envelope** | 30-day forward forecast container | JSON file: `MARUTI_2026-04_prediction_envelope.json` — holds 30 daily forecast rows, conviction streak, base close |
| **Learning Ledger** | Per-stock permanent pattern knowledge base | `MARUTI_learning_ledger.json` — stores lessons like "On RBI days trust risk_macro more" with confidence and occurrence count |
| **Weight Adapter** | Algorithm that adjusts agent influence from accuracy history | After risk_macro hits direction correctly 6/7 days, its weight increments by `+0.02` |
| **Feedback Loop** | Daily actual vs predicted comparison cycle | Every weekday 4:30pm IST: fetch actual close, compare to predicted, root-cause the miss, update weights |
| **Regime Multiplier** | Ephemeral weight overlay based on market regime | MACRO_CRISIS day: risk_macro multiplied by 1.40 — applied only for that day's forecast revision, never written to weight memory |
| **Conviction Streak** | Count of consecutive days with same verdict direction | 15 consecutive BUY days → `reversion_prior = 0.20` → confidence discount applied |
| **Reversion Prior** | Uncertainty penalty on sustained directional conviction | Formula: `min(0.25, (streak_days − 4) × 0.025)` — starts at day 5, caps at 25% |
| **Prompt Enhancer** | Dynamic query injector from miss history | If `crude_oil_spot_price` appears in top-3 missed factors, injects crude-specific search query into `raw_materials` and `risk_macro` agents |
| **Tiered Lessons** | T1/T2/T3 lesson context injected into FeedbackAgent | T1 = stock-specific (top 6 lessons), T2 = sector-wide (top 3), T3 = market-wide (top 2) |
| **Seasonal Calendar** | Pre-seeded + RL-discovered calendar pattern system | `SEA_AUTO_002`: Navratri-Diwali (Oct–Nov) → `sales_demand +0.10` — seeded at start, validated by RL over cycles |

---

### Indian Market Structure & Regulators

| Term | Full Form / Meaning | Practical Example |
|---|---|---|
| **NSE** | National Stock Exchange | Primary exchange; tickers are suffixed `.NS` in yfinance (e.g. `MARUTI.NS`) |
| **BSE** | Bombay Stock Exchange (now BSE Ltd.) | Parallel exchange; block/bulk deal disclosures are filed here |
| **SEBI** | Securities and Exchange Board of India | Regulates listed companies, mandates insider trade disclosures, enforces SAST threshold rules |
| **RBI** | Reserve Bank of India | Sets repo rate via MPC; issues LAF, CRR, SLR policy; regulates banks |
| **MPC** | Monetary Policy Committee | 6-member RBI committee that votes on repo rate every 2 months |
| **Repo rate** | Repurchase rate — RBI's overnight lending rate to banks | Cut from 6.5% to 6.25% in Feb 2025 → banks can borrow cheaper → NIM pressure, but credit growth stimulus |
| **FII** | Foreign Institutional Investor | Foreign funds like BlackRock, Nomura. FII selling ₹15,000 Cr in March → bearish breadth signal |
| **DII** | Domestic Institutional Investor | Indian MFs, LIC, pension funds. DII absorbed FII selling in 2022 — provided market floor |
| **AMFI** | Association of Mutual Funds in India | Publishes monthly MF category inflow/outflow data |
| **VIX** | Volatility Index | India VIX = expected 30-day market volatility. VIX 28 → high fear; VIX 12 → calm |
| **SAST** | Substantial Acquisition of Shares and Takeovers | SEBI regulation requiring disclosure when any party crosses 2% ownership — signals institutional activity |
| **Nifty 50** | NSE's 50-stock benchmark index | 5-day Nifty momentum is used as the FII proxy signal in regime detection |
| **NSE Holidays** | BSE/NSE market closure calendar | System fetches this via `calendar_updater.py` annually; hardcoded 2025–2026 fallback exists |
| **Circuit Breaker** | Exchange-imposed trading halt on extreme moves | A stock hitting +20% upper circuit = no more sellers at that price — agent cannot model this |

---

### Financial Metrics (Cross-Sector)

| Term | Full Form / Meaning | Practical Example |
|---|---|---|
| **EBITDA** | Earnings Before Interest, Tax, Depreciation and Amortisation | Maruti Q3 EBITDA margin 11.2% → operating profit per ₹100 revenue = ₹11.20 |
| **P/E ratio** | Price-to-Earnings ratio | HDFC Bank P/E 22× vs 5-year median 24× → stock trading at a modest discount |
| **EV** | Enterprise Value = Market Cap + Net Debt | ADANIGREEN EV = market cap + project debt − cash — used in EV/MW and EV/EBITDA multiples |
| **EV/EBITDA** | Enterprise Value to EBITDA multiple | JSW Steel at 7× EV/EBITDA vs historical 8× → slight discount |
| **DCF** | Discounted Cash Flow | Intrinsic value model: sum of future cash flows discounted at cost of capital |
| **IRR** | Internal Rate of Return | Solar project IRR 14% at ₹2.60/kWh tariff with 8% cost of debt → 6% spread, acceptable |
| **RoA** | Return on Assets | HDFC Bank RoA 2.2% vs industry average 1.4% → superior asset deployment efficiency |
| **RoE** | Return on Equity | TCS RoE 52% → business generates ₹52 of profit per ₹100 of shareholder equity |
| **DSCR** | Debt Service Coverage Ratio | Project DSCR 1.3× → operational cash flows cover annual debt repayment 1.3 times — minimum comfort level for lenders |
| **FX hedge** | Foreign Exchange hedging | TCS hedges 50% of USD receivables for 12 months forward — limits INR appreciation impact |

---

### Technical Analysis

| Term | Full Form / Meaning | Practical Example |
|---|---|---|
| **RSI** | Relative Strength Index (0–100) | MARUTI RSI = 74 → overbought; system flags conviction streak risk if sustained BUY |
| **MACD** | Moving Average Convergence Divergence | MACD crossing above signal line on Nifty IT weekly chart → positive momentum trigger |
| **Bollinger Bands** | ±2σ bands around 20-day moving average | Stock touching upper Bollinger Band with declining volume → potential reversal signal |
| **Support zone** | Price level where buyers historically emerge | TATAMOTORS ₹780 acted as support 3 times in 2024 → high-confidence floor for pattern agent |
| **Resistance zone** | Price level where sellers historically appear | HDFCBANK ₹1,900 — stock has reversed 4 times near this level |
| **Golden cross** | 50-day MA crosses above 200-day MA | Bullish signal; pattern agent scores this in the `moving_averages` sub-dimension |
| **Death cross** | 50-day MA crosses below 200-day MA | Bearish signal; opposite of golden cross |
| **PLF / CUF** | Plant Load Factor / Capacity Utilisation Factor | RE sector: CUF 22% for a solar plant in Rajasthan → 22% of theoretical max MWh actually generated |
| **ATR** | Average True Range | 14-day ATR measures daily price range. Used to derive whether 0.3% flat threshold is appropriate |
| **OHLCV** | Open, High, Low, Close, Volume | Raw price data fetched via yfinance for 10 years in PatternAnalysisAgent |

---

### Automobile Sector

| Term | Full Form / Meaning | Practical Example |
|---|---|---|
| **FADA** | Federation of Automobile Dealers Associations | Publishes monthly retail dispatch by vehicle category. FADA Oct 2024: PV sales 3.98L units, +14% YoY → feeds sales_demand agent |
| **SIAM** | Society of Indian Automobile Manufacturers | Publishes wholesale (factory → dealer) data. SIAM > FADA = dealer inventory building; SIAM < FADA = destocking |
| **Vahan** | MoRTH vehicle registration database | Registers every vehicle sold in India. Vahan March 2025: 95K EV registrations → key input for EV sub-score |
| **FADA vs SIAM gap** | Retail − wholesale delta | SIAM wholesale 410K, FADA retail 340K → 70K excess inventory at dealers → bearish for near-term demand |
| **DGFT** | Directorate General of Foreign Trade | Publishes export licensing data. DGFT: Maruti exports +23% in Q3 → offsets domestic volume weakness |
| **OEM** | Original Equipment Manufacturer | Maruti, Tata Motors, M&M — the vehicle makers (distinct from auto component makers) |
| **FAME** | Faster Adoption and Manufacturing of Electric Vehicles | Government EV subsidy scheme. FAME-II ended March 2024; FAME-III design = policy risk for EV-heavy OEMs |
| **BS norms** | Bharat Stage emission standards | BS-6 Phase 2 effective Apr 2023. Future BS-7 / CAFE-2 compliance readiness scored by policy_regulatory agent |
| **CAFE** | Corporate Average Fuel Economy | Fleet-level fuel efficiency regulation. Non-compliance = penalty per vehicle sold |
| **PLI for Auto** | Production Linked Incentive (automotive) | ₹26,000 Cr scheme for advanced automotive technology; eligibility scored in policy_regulatory agent |
| **ADAS** | Advanced Driver Assistance Systems | Safety tech: AEB, lane-keep, adaptive cruise. NCAP/GNCAP ratings feed competitive_intel agent |
| **Dealer inventory days** | Months of stock at dealers | >60 days → wholesale slowdown expected; <30 days → factory can push volume |

---

### Banking & BFSI

| Term | Full Form / Meaning | Practical Example |
|---|---|---|
| **GNPA** | Gross Non-Performing Assets (ratio) | HDFC Bank GNPA 1.2% vs SBI 2.2% → HDFC's loan book is cleaner |
| **NPA** | Non-Performing Asset | Any loan overdue >90 days. ₹500 Cr NPA on ₹50,000 Cr book = 1% GNPA |
| **PCR** | Provision Coverage Ratio | PCR 80% = bank has set aside ₹80 per ₹100 of NPAs as provision — higher PCR = more conservative |
| **Slippage** | Fresh loans turning into NPA in the quarter | Slippage ratio 2% this quarter → ₹2 of every ₹100 good loan became bad |
| **NIM** | Net Interest Margin | Bank earns 8% on loans, pays 4% on deposits → NIM = 4%. Higher NIM = better spread |
| **CASA** | Current Account Savings Account ratio | HDFC Bank CASA 46% → 46% of deposits are low-cost (0–3.5% interest), supporting NIM |
| **CRAR** | Capital to Risk-Weighted Assets Ratio | RBI minimum = 11.5%; SBI at 14% = well-capitalized, can grow loan book |
| **CET1** | Common Equity Tier 1 capital | Highest-quality capital (retained earnings + share capital). CET1 must be ≥ 8% under Basel III |
| **RoA** | Return on Assets | HDFC Bank RoA 2.2% → generates ₹2.20 profit per ₹100 of total assets |
| **Credit cost** | Provisioning expense / total advances | Credit cost 0.6% → bank sets aside ₹60 per ₹10,000 of loans as bad loan provision |
| **LAF** | Liquidity Adjustment Facility | RBI's daily window where banks borrow (repo) or park excess funds (reverse repo). Banks borrowing ₹2L Cr overnight = system liquidity deficit |
| **ALM mismatch** | Asset-Liability Management mismatch | Bank funds 5-year loans with 1-year deposits → rate risk if short-term rates rise |
| **IBC** | Insolvency and Bankruptcy Code (2016) | Debt resolution law. IBC resolution of large stressed accounts (Essar Steel, Bhushan Power) returned value to bank lenders |
| **PCA framework** | Prompt Corrective Action | RBI restricts a bank's lending/expansion when capital/NPA thresholds breach — material regulatory risk |
| **Concentration risk** | Loan book dominated by single sector/borrower | BFSI bank with 25% exposure to RE sector has high concentration risk if RE faces payment delays |

---

### IT Sector

| Term | Full Form / Meaning | Practical Example |
|---|---|---|
| **CC growth** | Constant Currency revenue growth | TCS reported 4.5% CC growth — removes USD/GBP/EUR FX movements; pure organic volume signal |
| **EBIT margin** | Earnings Before Interest and Tax margin | Infosys EBIT 21% → operating efficiency after paying employees but before financial charges |
| **TCV** | Total Contract Value | New deal TCV $2.4B in Q2 → $2.4B of revenue contracted (spread over multi-year term) |
| **Deal wins** | New client engagement or contract renewal | Wipro won a $500M 5-year BFSI deal → adds to TCV backlog, converts to revenue over deal term |
| **Attrition** | Employee annual turnover rate | Infosys attrition 12% in Q3 2025 vs 28% peak in 2022 — stabilising costs and delivery quality |
| **Vertical mix** | Revenue split by industry served | TCS: BFSI 32%, retail 10%, hi-tech 8% → BFSI-heavy means US banking client budget freeze hurts more |
| **Geography colour** | Management commentary on demand by region | "North America recovery is gradual; Europe remains soft" → Wipro Q2 call → European exposure bearish |
| **Guidance delta** | Reported guidance vs street consensus expectation | HCL Tech guided 5–6% CC growth vs street's 6.5% → negative guidance delta → stock fell 4% |
| **H1B visa** | US specialty worker visa (IT services companies use heavily) | H1B denial rate rise → Indian IT firms must localise US hiring → cost/margin pressure |
| **AI disruption score** | Model assessment of AI threat to current revenue lines | Application maintenance and testing (30% of IT revenue) most at risk from AI agents |
| **SAST disclosure** | Substantial Acquisition of Shares filing | TCS director buys ₹10Cr of stock in open market → SEBI-mandated disclosure → positive insider signal |

---

### Renewable Energy

| Term | Full Form / Meaning | Practical Example |
|---|---|---|
| **PPA** | Power Purchase Agreement | ADANIGREEN has PPAs for 80% of its 10 GW portfolio at ₹2.44/kWh average tariff locked for 25 years → revenue certainty |
| **DISCOM** | Distribution Company | State-owned electricity retailer that buys power from generators and sells to end users. Rajasthan DISCOM payment delay 90+ days → ADANIGREEN receivables risk |
| **MNRE** | Ministry of New and Renewable Energy | Issues tenders for RE capacity; sets RPO targets; administers PLI for solar modules |
| **RPO** | Renewable Purchase Obligation | State DISCOMs must source 43.33% of power from renewables by 2030 — creates captive demand for RE capacity |
| **ISTS waiver** | Inter-State Transmission System charge waiver | Centre waived ISTS charges for RE projects → lowers effective cost for long-distance RE transmission |
| **Curtailment risk** | Grid operator instructing generator to back down output | Tamil Nadu grid curtailed solar plants at 40% in peak summer → 40% of contracted MWh not billed |
| **CUF** | Capacity Utilisation Factor | 10 GW plant producing 22% of theoretical max → CUF 22% for Rajasthan solar |
| **DSCR** | Debt Service Coverage Ratio | Project DSCR 1.35× → operational cash flows cover debt payments 1.35× — banks require minimum 1.1× |
| **EV/MW** | Enterprise Value per Megawatt | NTPC RE division valued at ₹8 Cr/MW vs private peers at ₹12 Cr/MW → discount; or ₹8 Cr/MW in a transaction = comparable |
| **Implied IRR** | Internal Rate of Return implied by current stock price | ADANIGREEN at current price implies 11% IRR on operational portfolio — below WACC of 13% = overvalued |
| **Module price** | Cost per watt of solar panels | Chinese module prices fell from $0.28/W to $0.15/W in 2024 → new project LCOE improved; incumbents with older PPAs unaffected |
| **LCOE** | Levelised Cost of Energy | All-in cost per kWh over project life. Solar LCOE ₹1.90/kWh vs coal ₹4.50/kWh → economic case for RE |
| **Force majeure** | Contract clause for unforeseeable events | PPA with force majeure protection → DISCOM cannot terminate contract if grid infrastructure fails |
| **PLF** | Plant Load Factor | Thermal plant equivalent of CUF. Coal plant PLF 65% → running at 65% of installed capacity |
| **Green hydrogen** | H₂ produced via electrolysis using RE power | NTPC and Adani both building green hydrogen capacity — MNRE's National Green Hydrogen Mission target 5 MMT by 2030 |
| **KUSUM** | PM KUSUM scheme (solar for farmers) | Rooftop and feeder-level solar for agricultural use — creates distributed RE demand, less DISCOM-dependent revenue |
