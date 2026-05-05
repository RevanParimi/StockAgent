# StockAgent — Complete Design Discussion
> Last updated: 2026-04-23 | Primary artifact: StockAgent_Vision.html

---

## What we're building

A money-making tool for Indian markets (NSE/BSE) that:
- Watches multiple independent pointers/signals that affect stock prices
- Acts (or alerts) when enough pointers align — the confluence model
- Learns from outcomes to get better over time
- Scales from personal use to a platform for 10+ people investing together

The core bet: **most retail investors lose because they act on 1-2 signals. We act only when 4+ independent signals agree.**

---

## What we decided NOT to build (as important as what we're building)

- Not a screener (reactive — we're proactive)
- Not a prediction model (too fragile — we're a signal-confluence engine)
- Not a black box (every action must have a reason that can be audited)
- Not a single-account tool (the multi-account flywheel is core architecture)
- F&O is Phase 3 — not now

---

## The Three Products

### Product 1: AI Copilot
Prompt-driven research assistant. You ask "what should I buy in pharma right now?" and it:
- Pulls signal state for all pharma stocks
- Checks market phase, sector momentum, FII flow
- Returns a ranked list with reasoning
- Not an executor — a researcher

### Product 2: Signal-Driven Action Engine
The core engine. Runs 24/7, watches all signals. When confluence score crosses threshold:
- Phase 1: Sends alert to user (semi-auto)
- Phase 2: Executes with user approval
- Phase 3: Full auto with position sizing and exit management

### Product 3: Portfolio Platform
10+ accounts, each individual, but with shared intelligence:
- All accounts see the same signals
- Each account has isolated risk
- All account outcomes feed the same RL model (cross-account learning flywheel)
- Shared intelligence = faster learning than any single account could achieve alone

---

## The Complete Investment Logic (11 layers)

### Layer 1: Market Phase First
Before looking at any stock, determine market phase:

| Signal | Bull | Sideways | Bear |
|---|---|---|---|
| % stocks above 200 DMA | >60% | 40-60% | <40% |
| FII flow (3-month rolling) | Net buy | Mixed | Net sell |
| India VIX | <15 | 15-20 | >20 |

**What changes by phase:**
- Bull: full position sizing, all 4 signal types active
- Sideways: reduced size (50%), only Mispricing + Catalyst
- Bear: cash heavy (80%+), only Mean Reversion, no new longs

**Note:** We don't hard-code regime detection. The RL system handles it implicitly — wrong signals in bear markets get penalized, the system naturally becomes conservative. This is better than explicit rules because regimes transition gradually.

### Layer 2: Sector Before Stock
You never buy a stock without first confirming the sector is in favor.

Sector selection uses:
- Institutional money flow (FII/DII sector allocation changes)
- Earnings revision momentum (are analysts upgrading or downgrading sector?)
- Policy tailwind (budget allocations, PLI schemes, RBI policy effects)
- Relative strength vs Nifty 50

**Sector concentration rule:** When a sector theme is confirmed (e.g., PSU banks in a rate-cut cycle), allocate 40-50% of portfolio to that sector. Not diversification — conviction.

**Pair trading:** Within a confirmed sector, long the strongest stock, short the weakest. Reduces market beta exposure, captures sector-relative alpha.

### Layer 3: Four Reasons a Stock Moves
Every trade must map to exactly one of these four signal types:

1. **Mispricing** — stock below fair value, catalyst expected to close the gap
   - Signals: P/E below sector average, P/B below book, DCF undervaluation, promoter buying
   
2. **Catalyst** — known upcoming event that will move the stock
   - Signals: earnings date approaching, policy announcement, product launch, regulatory decision
   
3. **Momentum** — sustained directional move with institutional backing
   - Signals: 52-week high breakout, volume surge + price, FII accumulation, relative strength
   
4. **Mean Reversion** — stock overextended, snap-back expected
   - Signals: RSI >80 or <20, Bollinger Band breach, sector rotation away, institutional selling

**Why this matters:** The reason for entry must match the reason the outcome happened. If you enter on Catalyst and the stock goes up because of Momentum, that doesn't count as a correct prediction for RL credit. This prevents overfitting to luck.

### Layer 4: Confluence Scoring
Every pointer is a vote. More independent pointers aligned = higher conviction = larger position.

**Confluence threshold:** Minimum 3-4 pointers before any action. 6+ pointers = maximum position.

**Independence requirement:** 4 technical indicators don't count as 4 votes — they're correlated. You need pointers from different domains (technical + fundamental + macro + alternative data).

**Example — high conviction trade:**
- Technical: RSI oversold + volume spike (1 vote, technical)
- Fundamental: Q results beat estimate (1 vote, fundamental)
- Macro: FII net buying sector for 3 consecutive weeks (1 vote, macro)
- Alternative: Google Trends for company's product spiking (1 vote, alt data)
- Event: New government contract announced (1 vote, catalyst)
= 5 independent pointers → high conviction → 8-10% position

### Layer 5: Position Sizing — Kelly Criterion
Position size = (win_rate × avg_win - loss_rate × avg_loss) / avg_win × portfolio

Use **half-Kelly** in practice (Kelly tends to be too aggressive):
- Full Kelly = mathematically optimal but psychologically brutal
- Half-Kelly = ~75% of max geometric growth, much lower drawdowns

**Adjustments:**
- Market phase multiplier: 1.0 (bull), 0.5 (sideways), 0.2 (bear)
- Sector conviction multiplier: 1.0-1.4 when sector theme confirmed
- Confluence score multiplier: scales from 0.5 (threshold) to 1.0 (maximum signals)
- Portfolio cap: no single position >10%, no single sector >40%

Kelly fractions updated monthly as RL accumulates more outcome data.

### Layer 6: Position Management
After entry, the position is actively managed:
- T1 exit: at first target (close 50% of position)
- Trail the rest with dynamic stop
- Add to winners only when new signals confirm (not averaging down losers)
- Reduce when confluence score drops (signals fading = exit signal)

### Layer 7: Exit Logic — Three Categories
**Profit exits:**
- T1: Fixed target (e.g., 8% gain for mid cap) — close 50%
- T2: Extended target (e.g., 15% gain) — close another 30%
- Trailing stop: Lock in gains on remaining 20%

**Loss exits:**
- Hard stop: Fixed % (e.g., -5% for large cap, -8% for mid cap, -12% for small cap)
- Thesis-break stop: Original signal invalidated (e.g., earnings miss when you entered on Catalyst)
- Time stop: Position not moving after 20 trading days — opportunity cost exit

**Signal-driven exits:**
- Confluence score drops below threshold → exit regardless of P&L
- This is the most important exit — it means the edge is gone

### Layer 8: Portfolio Logic
- Correlation matrix: don't hold positions that move together (sector concentration is intentional; correlated individual stocks is not)
- Factor exposure balance: don't be inadvertently long quality + momentum + large cap all at once
- Sector caps: 40% max in any single sector (except during confirmed sector rotation)
- Cash is a position: holding cash when no high-conviction trades = correct decision, not failure

### Layer 9: Multi-Account Logic
- Shared signal intelligence: all 10+ accounts see identical signals
- Isolated risk: each account has independent position sizing based on its own Kelly history
- Cross-account RL: all accounts' outcomes (reason + result) feed the shared learning model
- Flywheel: 10 accounts learning simultaneously = 10x faster improvement than 1 account

### Layer 10: Learning Logic
The RL system learns by tracking:
1. **Entry reason** — which signal type triggered the trade
2. **Exit outcome** — did the stock move for the reason predicted?
3. **Credit rule** — RL credit only when reason matches outcome

This prevents a common failure mode: the model learns "pharma stocks go up" when actually it predicted a specific catalyst. Walk-forward validation prevents overfitting.

**Daily cycle:**
- Market close → scrape all outcomes for open positions
- Match outcomes to entry reasons
- Update agent weights
- Generate lesson log ("Catalyst trades in PSU banks underperformed this week — check if policy cycle is turning")

### Layer 11: Patience Filter (When NOT to Trade)
The system must be capable of saying NO. Explicit rules:

- Market phase unclear → no new positions
- Confluence score < 3 aligned pointers → no trade
- Risk/reward ratio < 2:1 → no trade
- VIX > 25 without specific hedge → no trade
- No sector with positive flow → no new sector longs
- Already at sector cap → no new positions in that sector

**The most important metric:** How often does the system correctly decide NOT to trade? Most systems are evaluated on wins/losses. This one is also evaluated on no-trade quality.

---

## Signal Pointers (full list)

### Technical
- RSI (14-day, weekly)
- MACD crossovers
- Volume surge (2x+ 20-day average)
- 52-week high/low proximity
- Bollinger Band position
- Moving average alignment (20/50/200 DMA)
- Support/resistance levels

### Fundamental
- P/E vs sector average
- P/B vs book value
- Revenue growth acceleration/deceleration
- Margin trajectory (expanding/compressing)
- Debt/equity trend
- Promoter holding change
- Earnings revision direction

### Macro
- FII daily flow (sector-wise)
- DII daily flow
- India VIX level
- RBI policy stance
- USD/INR trend (affects IT and import-heavy sectors differently)
- Commodity prices (crude for auto/aviation, metals for infra)

### Alternative Data
- GST e-way bill volumes (demand proxy for FMCG, auto, logistics)
- VAHAN vehicle registration (auto sector demand)
- Job posting trends on Naukri/LinkedIn (sector health indicator)
- App store ratings + downloads (consumer sentiment for tech/consumer companies)
- Google Trends (product/brand searches)
- Freight indices (economic activity proxy)

### Event-Based
- Earnings calendar proximity
- Policy announcements (Budget, RBI meetings)
- Sector-specific regulatory events
- Block deal detection (institutional accumulation/distribution)
- Bulk deal data
- M&A pre-detection (unusual volume/options activity before announcement)
- Credit rating watch list additions/removals

### Options-Derived
- Put-Call Ratio (PCR)
- Max pain level
- OI buildup at strikes
- Implied volatility changes

---

## MiroFish Integration

MiroFish (github.com/666ghj/MiroFish) simulates how market participants behave under different macro scenarios.

**How we use it:**
- Input: current macro state (RBI rate, FII flow trend, global risk-on/off)
- Output: simulated market behavior prediction (which sectors get bought, which get sold)
- Role in confluence: One macro pointer among many — confirms or contradicts other signals

**Tech stack:**
- OASIS/CAMEL-AI: multi-agent simulation (retail investors, FII desks, DII desks all modeled)
- GraphRAG: retrieves relevant historical scenarios
- Zep Cloud: long-term memory for simulation agents

---

## Alpha Enhancement Ideas

These are the things that separate a 15-20% alpha system from a 40-50% alpha system:

| Enhancement | Expected Alpha Add | Complexity |
|---|---|---|
| Sector concentration (40-50% when theme confirmed) | +8-12% | Low |
| Pair trading (long strong / short weak) | +6-10% | Medium |
| Alternative data (GST, VAHAN, job postings) | +5-8% | High |
| Options flow as signal pointer | +4-6% | Medium |
| Event Radar (M&A, earnings pre-detection) | +3-5% | High |
| Tax optimization (LTCG vs STCG timing) | +2-3% | Low |
| Walk-forward RL validation | Prevents -10% from overfitting | Medium |

**Honest ceiling:** Real ceiling is data quality + execution quality, not model sophistication. A perfect model with bad data = bad results.

---

## Return Projections

| Scenario | Annual Alpha Over Nifty |
|---|---|
| Base design (signals + RL) | 15-20% |
| With alternative data + pair trading | 25-30% |
| With options + sector concentration, strong bull year | 40-55% |
| Realistic 3-year average | 20-25% |

**What the RL learns over time:** The system gets better each year as it accumulates outcome data. Year 1 (paper trading + learning) → Year 2 (real money, conservative) → Year 3+ (full conviction).

---

## Sector Coverage

### BFSI (17 agents)
- 726 NSE/BSE financial stocks
- Institution-type routing: bank / NBFC / insurance / AMC / HFC
- Different signals weight differently by institution type
  - Banks: NIM, GNPA, credit growth, RBI policy sensitivity
  - NBFCs: AUM growth, funding cost, ALM
  - Insurance: premium growth, claims ratio, VNB margin
  - AMCs: AUM, SIP flows, equity/debt ratio
  - HFCs: loan book growth, NPA, spreads
- 4 output streams: Intraday, Swing, Positional, MF Rotation

### Automobile (9 agents)
- Key signals: VAHAN registration data, GST e-way bills, crude price, EV transition indicators
- Sub-sectors: 2W, 3W, PV, CV, ancillaries, EV

### IT (planned)
- USD/INR critical input
- Deal win/loss announcements, headcount trends, visa data

### Real Estate (planned)
- Registration data (state-wise), cement/steel prices, interest rate sensitivity

---

## Build Phases

### Phase 1 — Foundation (1-2 months paper trading)
- Data pipeline: NSE/BSE APIs, alternative data sources
- Signal computation engine
- Confluence scoring model
- Paper trading simulation
- Basic alerting
- **Infra cost: ₹8-12K/month**

### Phase 2 — Semi-Auto (with real money, conservative)
- Alert + approval workflow
- Position tracking
- Basic RL feedback loop
- Multi-account dashboard
- **Infra cost: ₹13-18K/month**

### Phase 3 — Full Auto
- Automatic execution (broker API integration)
- Advanced RL with walk-forward validation
- Alternative data integration
- Options signals
- MiroFish macro integration
- **Infra cost: ₹35-45K/month**

---

## Key Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| Signal threshold | 3-4 minimum pointers | Below this, edge is noise |
| Position sizing | Kelly Criterion (half) | Mathematically optimal for compounding |
| Regime detection | Implicit via RL | Explicit rules break at transitions |
| Universe | 3 buckets (Large/Mid/Small) | Different risk/data quality profiles |
| RL credit | Reason must match | Prevents overfitting to lucky outcomes |
| Multi-account | Shared intelligence, isolated risk | Best of both worlds |
| Sector concentration | 40-50% when theme confirmed | High conviction = high allocation |
| Paper trading | 1-2 months before real money | Non-negotiable circuit breaker |
| Exit type 3 | Confluence score drop | Most important exit signal |
| F&O | Phase 3 only | Need track record first |

---

## Files

All files in: `c:\Users\SivaVenkataDattaSank\OneDrive - ShipBob Inc\Documents\Repo\Personal\`

| File | Purpose |
|---|---|
| `StockAgent_Vision.html` | Primary living design document (16 interactive tabs) |
| `StockAgent_Discussion.md` | This file — full design discussion narrative |
| `siva/banking_agent_v5.html` | BFSI architecture diagram |
| `siva/TRAINING_PLAN.md` | BFSI team training plan |
| `siva/REPO_CONTEXT.md` | Existing codebase technical map |

**The HTML is the shareable artifact for team discussions.**
**This MD file is the complete design rationale.**
