# StockAgent

> AI-powered Indian stock analyser with a self-learning feedback loop.
> Analyses NSE/BSE stocks across 4 sectors using up to 9 specialist AI agents in parallel —
> then reviews its own predictions every trading day to get smarter over time.
> Now with **Compass**: a virtual portfolio it watches for you daily, telling you
> when to HOLD / ADD / TRIM / EXIT each position — with the receipts in a permanent advice ledger.

**Live app:** [stockagent-ai.up.railway.app/app/index.html](https://stockagent-ai.up.railway.app/app/index.html)

---

## What Is StockAgent?

Most stock research tools give you a one-shot answer and forget it the moment you close the tab. StockAgent works differently.

Every time you run an analysis, the stock is scored across specialist dimensions tailored to its sector — automobile spans nine (fundamentals, macro risk, technical patterns, sentiment, raw material costs, policy risk, competitive position, valuation, and sales data); Banking/BFSI, IT, and Renewable Energy span six, eight, and six of their own. For every sector, a single reasoning-model call scores all dimensions in one pass from one shared data bundle. A Signal Aggregator then weighs the scores, detects where dimensions disagree, and asks a final AI model to resolve the conflicts and issue a verdict.

That is the analysis part. The learning part is what makes it unusual.

After every trading day, the system automatically fetches the actual closing price and compares it against what was predicted. It asks: *was the prediction right? If wrong, which agent was responsible? Was it a data gap, a model blind spot, or an external shock no one could have predicted?* The answers get written into a permanent per-stock memory file. The agent that keeps getting it wrong sees its influence quietly reduced. The one that keeps getting it right earns more weight in future predictions. After several months of trading days, the system has accumulated a proprietary rulebook for how a specific stock responds to specific events — something no static research tool can replicate.

---

## Supported Sectors and Stocks

| Sector | Status | Stocks covered |
|---|---|---|
| **Automobile** | ✅ Full — unified single-call analyst + RL loop live | MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO, HEROMOTOCO, EICHERMOT, TVSMOTORS, ASHOKLEY, ESCORTS, FORCEMOT + 6 extended (APOLLOTYRE, MRF, CEATLTD, MOTHERSON, BOSCHLTD, BALKRISIND) |
| **Banking / BFSI** | ✅ Unified single-call analyst live (6 dimensions) | HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK, INDUSINDBK, BANDHANBNK, RBLBANK, YESBANK, BAJFINANCE, MUTHOOTFIN and more |
| **IT Sector** | ✅ Unified single-call analyst live (8 dimensions) | TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM, COFORGE, MPHASIS, PERSISTENT and more |
| **Renewable Energy** | ✅ Unified single-call analyst live (6 dimensions) | ADANIGREEN, TATAPOWER, NTPC, POWERGRID, SJVN, JSWENERGY and more |
| **17 more sectors** | 🔲 Pipeline — prompt templates ready | Pharma, FMCG, Metals, Oil & Gas, Capital Goods, Insurance, Telecom, Defence, Chemicals, Infra, Logistics, Real Estate, Retail, Power, Media, Hospitality, Agro-Chemicals |

You can type either the NSE ticker (`MARUTI`) or the company name (`Maruti Suzuki`) — the system resolves it automatically.

---

## The 9 Analysis Dimensions (Automobile Sector)

Every analysis is scored across its sector's dimensions (9 automobile / 6 BFSI / 8 IT / 6 renewable). A single **Unified Sector Analyst** call assesses all of them from one shared data bundle (one set of fetches, one reasoning-model pass) — but each dimension still gets its own focused scoring lens, so a dimension that only cares about raw material prices cannot take shortcuts on the technical picture. The legacy per-dimension agent pool remains in the codebase purely as an automatic fallback.

### 1. Fundamentals (18% weight)
Examines the last 4 quarters of P&L data: revenue growth, EBITDA margin vs sector peers, order book pipeline, FII/DII shareholding changes. A company that is growing revenue and expanding margins will score well here even if the stock price has not reacted yet.

### 2. Sales & Demand (16% weight)
Digs into India-specific demand signals: FADA retail dispatch figures, SIAM wholesale data, Vahan EV registration trends, dealer inventory health, DGFT export volumes. This is the "on-the-ground" signal — wholesale numbers can look good while retail demand is actually weakening, and this agent is designed to catch that gap.

### 3. Risk & Macro (13% weight)
Assesses macro headwinds and tailwinds: INR/USD exposure, crude oil trajectory, steel and aluminium input cost direction, RBI repo rate outlook, and four global geopolitical risk channels (oil supply shock, FII outflow, INR depreciation pressure, supply chain disruption from China). High risk = low score.

### 4. Pattern Analysis (12% weight)
Technical analyst. Uses 10 years of price history to identify where the stock sits in its historical cycle, current RSI/MACD/Bollinger Band posture, breakout and support zones, and correlation with the Nifty Auto index. This agent does not use any news data — it talks only to price history.

### 5. Valuation & Catalyst (10% weight)
Derives a fair value estimate using P/E vs 5-year history and peer median — without using any analyst reports. Estimates the stock's current discount or premium, lists the specific catalysts that could close that gap, and generates a price target with a recovery timeline.

### 6. Policy & Regulatory (9% weight)
Covers the government policy environment: FAME EV subsidy eligibility, BS-7/CAFE emission norm compliance readiness, Union Budget duties, PLI scheme capture, and state-level EV incentives. For auto stocks, a surprise duty change or subsidy cut can matter more than a quarterly earnings miss.

### 7. Raw Materials (9% weight)
Steel, aluminium, platinum, palladium, crude oil, and polymer price direction. Every auto OEM has a different input cost mix — this agent scores the commodity environment for the company's specific exposure.

### 8. Competitive Intel (9% weight)
EV market share trajectory, upcoming model launch pipeline, joint ventures, and ADAS/safety ratings. Is this company gaining share or losing it? Is its product pipeline rich or thin?

### 9. Sentiment (4% weight)
News NLP across financial media, management tone from earnings calls, social media signals, and dealer feedback. Given the smallest weight — markets can be irrational in the short term, but persistently negative sentiment often precedes a structural problem.

---

## How the Verdict Is Produced

For the **automobile** sector:

```
One shared data bundle is fetched (news, policy, macro, fundamentals,
technicals, commodities, flows, peers, dossier — all in one pass)
      ↓
One reasoning-model call scores all 9 dimensions from that bundle
      ↓
Each dimension returns a score 0.0–1.0 with sub-scores and reasoning
      ↓
Signal Aggregator applies weighted average
      ↓
Detects conflicts: any two dimensions with score delta ≥ 0.30 flagged
      ↓
LLM resolves conflicts: "fundamentals bullish, macro bearish — which matters more right now?"
      ↓
Final score + Verdict + Investment thesis + Conviction drivers + Top risks
```

This unified flow is the default for **all four sectors** (Banking/BFSI scores 6
dimensions, IT 8, Renewable Energy 6 — same mechanics, sector-specific prompts and
data bundle). If the unified analyst call ever fails outright, the sector
automatically falls back to the legacy multi-agent path (parallel per-dimension
agents, each with its own data fetch and LLM call) so a report is always produced.

**Verdict scale:**

| Verdict | Score range | Meaning |
|---|---|---|
| STRONG BUY | 0.75 – 1.00 | Strong signals across most dimensions |
| BUY | 0.55 – 0.75 | Majority positive signals |
| NEUTRAL | 0.40 – 0.55 | Mixed or uncertain signals |
| SELL | 0.20 – 0.40 | Majority negative signals |
| STRONG SELL | 0.00 – 0.20 | Weakness across most dimensions |

The verdict is not a simple average of agent scores. After the weighted composite is computed, an LLM reviews the conflicts and may adjust the final score if it judges that one agent's signal is especially reliable or unreliable in the current context.

---

## Reading an Analysis Result

When an analysis completes, the drawer shows:

**Executive Summary** — 2 sentences for a quick read.

**Score Gauge** — 0–100 visual representation of the final score. 50 is neutral.

**Investment Thesis** — the 2–3 sentence analytical case, combining all agents' views.

**Conviction Drivers** — the top 3–5 specific factors pushing the score positive. These are the things the system is most confident about.

**Top Risks** — the top 3–5 specific factors that could invalidate the bullish case.

**Agent Breakdown** — per-agent scores displayed as a bar chart. This is where you see disagreements. If fundamentals scores 0.72 but risk_macro scores 0.38, the stock might be fundamentally strong but exposed to near-term macro headwinds.

**Conflicts Resolved** — if any two agents disagreed significantly, this shows the conflict and how it was resolved.

**Price Target** — derived by the Valuation agent from P/E normalisation and technical channel analysis. Not from broker reports. May be blank if data is insufficient.

**Recovery Timeline** — estimated quarters to reach fair value. Only shown for SELL/STRONG SELL verdicts where recovery is anticipated.

---

## The Learning System (Why It Gets Smarter Over Time)

Every analysis generates a 30-day forward forecast. Each evening at 4:30 PM IST, after NSE market close, the system automatically:

1. Fetches the actual closing price for every tracked stock
2. Compares it to what was predicted
3. Identifies the primary miss — which agent led the call astray
4. Classifies the type of miss (was it a data gap? model bias? external shock?)
5. Adjusts that agent's influence weight for future predictions — each agent is scored on
   whether *its own signal* called the move (calibration), not just whether the ensemble won
6. Writes lessons into a permanent learning ledger for that stock — each lesson carries
   **trigger tags** (e.g. `central_bank_event`, `crude_price`) so it fires automatically
   on matching days instead of sitting as advice text
7. Revises the remaining days in the current 30-day forecast
8. Updates the stock's **dossier** — a living knowledge file maintained by a daily curator
   that runs on *every* day, including days the call was right ("what worked"), recording
   observations, institutional flow trends, management guidance, recurring catalysts, and
   quantified response signatures ("drops ~2% within 2 sessions of crude > $90")

The dossier is consolidated weekly (episodic observations distilled into durable
knowledge), injected into every agent's prompt on the next analysis, and exposed to the
chat assistant — so what the system learns by watching a stock daily is what it uses to
reason about that stock everywhere. Stale lessons decay, repeatedly-contradicted patterns
are archived (and resurrected if they start recurring), and a read-only evaluation harness
(`python -m core.intelligence.rl.eval.run_eval`) measures direction accuracy, Brier score,
and confidence calibration so improvement is a number, not a feeling.

**The system also keeps score against controls.** Every day a *control lane* — the same
LLM given the same information but none of the agents, learned weights, or dossier — makes
its own prediction, and naive baselines (persistence, always-up) are computed alongside.
A monthly scorecard (`python -m services.scheduler.run_schedule scorecard`, auto-generated
on the 1st) persists the time series: StockAgent vs control vs baselines, month-over-month
deltas, accuracy on days learned claims fired vs other days, and dossier health. The edge
over the bare model is a measured number, not a claim.

**And it reads the filings, not just the tape.** A weekly event scan watches NSE corporate
announcements (results, concalls, investor presentations, guidance) and digests qualifying
events into the dossier — so management guidance like "expects ~1% growth in FY27" enters
the stock's knowledge file straight from the source, the quarter it's said, and is tracked
to met/missed.

**The monthly forecast isn't set in stone.** If a real shock invalidates the thesis mid-cycle
— a surprise external shock, a thesis-breaking miss, or the market tipping into a sustained
crisis regime — the system re-underwrites the remaining days of its 30-day forecast from
the current price, archiving the old path for the record; and every weekday morning before
the market opens it runs a quick overnight-news check so a global shock doesn't go unnoticed
until the evening review.

**The miss classification matters.** If the stock moved because of a surprise RBI rate decision that nobody predicted, that is classified as an `external_shock` — zero penalty to any agent, because the system could not have known. But if the fundamentals agent consistently overestimates a specific signal month after month, that is classified as `model_bias` — full penalty, weight reduction.

**What the learning ledger looks like after 3 months:**

```
MARUTI learning ledger — 4 active lessons:

[L001] RBI_policy_day (confidence=0.80, seen=4×, scope=sector_wide)
       Rule: On RBI announcement days, risk_macro signal dominates — trust it more.

[L002] month_end_inventory_flush (confidence=0.65, seen=2×, scope=stock_specific)
       Rule: Discount sales_demand score in last 3 trading days of each month.

[L003] crude_oil_spike (confidence=0.72, seen=3×, scope=market_wide)
       Rule: Crude spike >5% in 5 days → raise risk_macro weight, lower sales_demand.

[L004] shravan_demand_dip (confidence=0.68, seen=1×, scope=sector_wide)
       Rule: Jul–Aug Shravan period → discount sales_demand for North India-heavy OEMs.
```

These lessons are applied automatically to every subsequent analysis and forecast. Lessons tagged `sector_wide` (like L001 and L003) propagate to other stocks in the same sector — so a lesson learned from MARUTI's misses automatically helps TATAMOTORS forecasts.

**Agent weight example after 60 days:**

```
Current weights vs base (MARUTI, weight version v7):
  risk_macro      0.16 → 0.19  (+0.03)  ← consistently called direction correctly
  fundamentals    0.18 → 0.20  (+0.02)  ← strong track record on quarterly data
  sales_demand    0.16 → 0.14  (−0.02)  ← over-optimistic on wholesale dispatch 4× 
  sentiment       0.04 → 0.03  (−0.01)  ← noise signal; rarely predictive
```

---

## Market Regime Awareness

The system detects the broad market regime each day from three signals:

| Signal | What it measures |
|---|---|
| India VIX | Market fear level |
| Nifty 50 momentum (5-day) | Whether foreign institutional money is flowing in or out |
| Sector RSI | Whether the sector is technically overbought or oversold |

The regime label — `MACRO_CRISIS`, `RISK_OFF`, `NORMAL`, `RISK_ON`, `MOMENTUM_EXTENDED`, or `OVERSOLD` — temporarily adjusts which agents carry more weight in that day's forecast revision. In a `MACRO_CRISIS` day (VIX > 22, Nifty falling), the risk_macro agent's weight is boosted by 40%. In a `RISK_ON` day, sentiment and fundamentals are elevated and macro risk is discounted.

These regime adjustments are **ephemeral** — they affect today's forecast but do not permanently change the learned weight memory. The system does not let one bad week of macro volatility permanently silence the fundamentals agent.

---

## Conviction Streak Protection

If the system has issued the same verdict (e.g. `STRONG BUY`) for 10 or more consecutive trading days, it automatically applies a **mean-reversion prior** — a growing uncertainty discount — to future forecast confidence. A streak of 15+ days is flagged as elevated risk.

When the pattern_analysis agent's RSI indicator contradicts the sustained verdict (e.g. RSI showing overbought conditions while the system keeps calling BUY), the reversion warning is amplified further.

This is not a prediction — it is a calibration. The system is telling you: *"We have been bullish for a long time. Markets tend to correct sustained directional trends. Be proportionally cautious."*

---

## Compass — Your Portfolio, Watched Daily

Everything above analyses stocks *in general*. Compass points all of that machinery at **your stocks specifically**. You tell it what you hold; from that moment every holding gets the full treatment — monthly forecast envelope, daily RL review, living dossier — and every evening a deterministic advisor tells you, per position: **HOLD, ADD, TRIM, or EXIT**, with the reason.

It launches **virtual-first**: you enter mock buys with real money mechanics. Entry price is the *actual NSE close* on your buy date, P&L is marked against real closes on trading days only, and every piece of advice is logged to a permanent ledger — so the system's advice quality is proven on paper before a single real rupee moves.

> Everything Compass outputs is research/analysis for the portfolio owner — never investment advice, and there is no auto-trading anywhere in the system.

### How an evening works

```
  YOU (once)                                THE SYSTEM (every trading day)
┌─────────────────────────┐
│ "Add 10 MARUTI,          │      4:30pm IST daily RL review finishes for
│  bought 2026-07-03"      │      ALL managed tickers (yours included)
│                          │                      │
│ entry priced at the      │                      │  event-trigger — the advisor runs
│ REAL NSE close that day  │                      │  when the review completes,
└───────────┬─────────────┘                      │  never on a wall clock
            │ auto-promotion                      ▼
            ▼                        ┌────────────────────────────────┐
┌─────────────────────────┐         │ 1  CORP-ACTION SYNC            │
│ MANAGED UNIVERSE         │         │    splits · bonuses · dividends │
│ your holding now gets:   │         │    adjust cost basis FIRST      │
│  · 30-day envelope       │         ├────────────────────────────────┤
│  · daily RL review       │         │ 2  EVENTS CALENDAR REFRESH     │
│  · living dossier        │         │    forward earnings dates       │
│  — identical treatment   │         ├────────────────────────────────┤
│  to the original tickers │         │ 3  PER HOLDING                 │
└─────────────────────────┘         │    envelope + regime + thesis   │
                                     │    + P&L + earnings distance    │
                                     │    → HOLD / ADD / TRIM / EXIT   │
                                     │    → LLM writes the one-liner   │
                                     ├────────────────────────────────┤
                                     │ 4  ADVICE LEDGER (append-only) │
                                     ├────────────────────────────────┤
                                     │ 5  EOD DIGEST saved per user   │
                                     └────────────────────────────────┘
```

Step 1 is deliberately first and non-negotiable: without it, a 1:1 bonus issue would look like a −50% overnight crash and fire a false EXIT. All P&L and stop math runs on the **corp-action-adjusted** cost basis (`adj_avg_price` / `adj_qty`), never the raw entry numbers — and dividends you've received count toward P&L, so dividend payers aren't unfairly trimmed.

### The verdicts

The decision engine is **pure Python — deterministic, testable, cheap**. The LLM only phrases the explanation afterwards; it never makes the call.

**Precedence is absolute: `EXIT > TRIM > ADD > HOLD`.**

| Verdict | Fires when | Rule codes in the ledger |
|---|---|---|
| 🟥 **EXIT** | Loss breaches the volatility-scaled stop, **or** thesis assessed broken with a bearish envelope, **or** a shock re-forecast moved against you, **or** `MACRO_CRISIS` regime + bearish envelope | `stop_breach`, `thesis_break`, `shock_reforecast`, `crisis_regime_bearish` |
| 🟧 **TRIM** | Profit ≥ 25% **and** envelope confidence is fading or the mean-reversion prior is elevated | `trim_profit_confidence_decline`, `trim_profit_reversion_elevated` |
| 🟩 **ADD** | Envelope bullish + supportive regime + position under its 10% weight cap + recent direction accuracy ≥ 60% | `add_bullish_healthy` |
| ⬜ **HOLD** | Default — thesis intact, nothing above fired | `default_hold` |

Two tax/event refinements ride on top:

| Annotation | Meaning |
|---|---|
| `WAIT_FOR_LTCG` | A TRIM on a position aged 10–12 months with an intact thesis is softened to HOLD — selling a few weeks early would pay 20% STCG instead of 12.5% LTCG. **This never softens an EXIT** — capital protection outranks tax optimisation, always. |
| `EARNINGS_GAP_PROTECTION` | Profitable position with results due within 3 trading days — flags the profit-protection question before the gap risk, fed by a live NSE corporate-events calendar. |
| `SECTOR_CONCENTRATION_HIGH` | Position weight has crossed the 30% concentration comfort band. |

### Stops that respect volatility

A flat stop-loss % is wrong twice: it's one bad week of noise on a small-cap and far too loose on a large-cap bank. Compass scales the stop to the stock:

```
stop % = clamp( 3 × ATR(20d)% ,  bucket floor ,  bucket cap )
```

| Market-cap bucket | Stop floor | Stop cap | Example |
|---|---|---|---|
| Large (≥ ₹65,000 cr) | 8% | 12% | HDFCBANK (ATR ~0.8%) → stop ≈ 8% (floored) |
| Mid (≥ ₹20,000 cr) | 12% | 18% | typical mid-cap ATR ~1.5% → stop ≈ 12–15% |
| Small | 15% | 22% | volatile small-cap ATR ~3.5% → stop ≈ 22% (capped) |

A `conservative` risk profile tightens the bucket one notch (small→mid, mid→large). Every threshold above — trim %, weight cap, ATR multiple, bucket bands, LTCG window — lives in `config.yaml` under `advisor.*` / `portfolio.*`.

### Auto-promotion — the key mechanic

Any symbol you hold or watchlist is **automatically promoted into the managed universe** and starts receiving forecasts, daily reviews, and a dossier — no separate setup.

| Rule | Behaviour |
|---|---|
| Sector gate | Phase A supports the 4 live sectors (automobile, banking/BFSI, IT, renewable energy). Anything else is rejected with a clear *"sector not yet supported"* — the generic sector graph that lifts this arrives in Phase B. |
| Review cadence | **Held names review daily; watchlist names weekly** (Fridays) — this is what keeps LLM spend governed. |
| Cap | 40 managed tickers max (`portfolio.max_managed_tickers`). At the cap, the **oldest watchlist-origin** name rotates out. |
| Protection | Held positions and the original manually-managed tickers are **never** rotated out. |

### What lands on disk

```
data/portfolio/
└── <user_id>/                        ← per-user from day one (default: "primary")
    ├── portfolio.json                ← holdings + watchlist + risk profile
    │     symbol, sector, qty, buy_date,
    │     avg_buy_price     (raw — never touched)
    │     adj_avg_price     (corp-action-adjusted — ALL math uses this)
    │     dividends_received, applied_actions[], virtual: true
    ├── advice_ledger.jsonl           ← append-only: every verdict ever issued
    │     date, symbol, verdict, close, pnl%, stop%,
    │     trigger codes, confidence, narrative, outcome slots (+10/30/60td)
    └── digests/
        └── 2026-07-03.json           ← one EOD digest per trading day

data/market_cache/
└── corporate_events.json             ← forward earnings calendar (degraded-mode safe)
```

The advice ledger is the seed of the next learning loop: outcome slots get filled at +10/+30/+60 trading days, and in Phase D the same weight-adaptation machinery that tunes the analysis agents starts tuning the advisor's own thresholds — *"were my TRIM calls actually right?"* becomes a measured number.

### A digest, rendered

```
EOD DIGEST — 2026-07-03 · user: primary
──────────────────────────────────────────────────────────
Portfolio value  ₹1,43,660        Cost basis  ₹1,20,000
Total P&L        +19.7%           Escalations: none
──────────────────────────────────────────────────────────
 MARUTI    ⬜ HOLD   ₹14,366   +19.7%
           "Thesis intact; envelope tracking within band and
            no rule fired. Results due Jul 29 — no gap risk yet."
──────────────────────────────────────────────────────────
```

### Driving it — the `/portfolio` API

| Method | Endpoint | What it does |
|---|---|---|
| GET | `/portfolio` | Holdings + watchlist, marked to market at the latest close |
| POST | `/portfolio/holdings` | Add a virtual buy — omit `price` and it's priced at the real NSE close on your buy date |
| DELETE | `/portfolio/holdings/{symbol}` | Remove a position (auto-demotes from the managed universe if not watchlisted) |
| POST | `/portfolio/watchlist` · DELETE `/portfolio/watchlist/{symbol}` | Watch a symbol (weekly review cadence) |
| POST | `/portfolio/import-csv` | Bulk import — `symbol,sector,qty,avg_buy_price,buy_date` (price blank → real close) |
| GET | `/portfolio/advice?limit=50` | The advice-ledger tail |
| GET | `/portfolio/digest/latest` | Latest EOD digest |
| POST | `/portfolio/run-advisor` | Manual pipeline trigger (202, runs in background) |

### What Compass is not (yet)

| Not in Phase A | Arrives |
|---|---|
| Discovery engine (weekly quant funnel over ~2000 NSE stocks) + paper-trading lane | Phase B |
| Sectors beyond the live 4 (generic sector graph) | Phase B |
| IPO tracker, morning brief, push/email delivery, SWITCH verdicts | Phase C |
| Advice-outcome RL (thresholds that tune themselves) | Phase D — data-gated on ~6 weeks of ledger |
| Broker sync (Zerodha Kite Personal — flips `virtual: false`) | Optional, any time after A |

---

## The Chat Assistant

The floating orb (bottom-right corner) opens a chat assistant — an **agentic tool-loop** that reasons,
calls tools across several rounds, and answers from live data:

- **"Which IT stocks should I buy now?"** → `screen_stocks` (value mode) — surfaces the **beaten-down names near 1-month lows** (buy-the-dip), then confirms catalysts with live news. It understands that "good to invest" means *buy low*, not echo today's gainers or famous blue-chips.
- **"Which auto stocks should I book profit on?"** → `screen_stocks` (profit mode) — the **extended names near 1-month highs**.
- **"What is the current price of Reliance?"** → `get_live_price` — NSE-first symbol resolution (no more wrong US tickers), labelled `live` or `last close <date>` by the IST market session.
- **"Why did Tata Motors fall today?"** → `search_market_news` — live news via Serper, fused across multiple query variants (RRF) with a Tavily fallback.
- **"What is StockAgent's rating on HDFCBANK?"** → `get_stock_analysis` · **"How is the Banking sector today?"** → `get_sector_snapshot` (index + per-stock movers) · **"Which agent should I trust?"** → `get_rl_insights` · **"Run a fresh analysis on BAJAJ-AUTO"** → `run_agent_analysis`.
- **"What do we know about MARUTI?"** → `get_ticker_dossier` — the stock's accumulated knowledge file: current thesis, learned price-response signatures, open management guidance, recurring catalysts, and institutional flow trend from daily tracking.

For buy/sell/momentum questions a **deterministic pre-router** fetches the screen and news *before* the
model answers — so the right candidates and real, dated sources always reach it. It is grounded to the
IST market session (it knows whether the market is pre-open, open, or closed), never quotes a price it
didn't fetch, and never invents a source. Conversation history is kept within the session for natural
follow-ups. Full design: [`docs/CHAT_ARCHITECTURE.md`](docs/CHAT_ARCHITECTURE.md).

---

## Watchlist

Add up to any supported NSE stock to your watchlist. The app fetches live prices for all watchlist stocks on page load and shows them in a compact table with current score and verdict (if an analysis has been run).

Click **Analyze** on any watchlist row to run a fresh full analysis across all 9 dimensions immediately.

The watchlist persists between sessions. Changes are saved to the server.

---

## Trending

The Trending tab shows stocks sorted by **score delta** — not price change. A stock that moved +3% in price but whose AI analysis score dropped from 0.72 to 0.58 appears as a negative mover here.

This is intentional. Price momentum is a lagging signal. Score changes reflect what the agents are finding in fundamentals, macro, and sentiment — often before the price reacts.

---

## Categories

The Browse by Category section organises stocks into:

| Category | What it covers |
|---|---|
| EV | OEMs with significant EV exposure (Tata, M&M, TVS, Bajaj, Hero) |
| Mass Market | Volume-driven passenger vehicles |
| Premium | Royal Enfield, Bajaj, Maruti premium segment |
| Commercial Vehicles | Ashok Leyland, Tata Motors CV |
| Two-Wheelers | Hero, TVS, Bajaj, Eicher |
| Auto Parts | Bosch, Motherson, Apollo Tyres, CEAT, MRF, Balkrishna |

Click any category to see all stocks within it and their latest verdicts side by side.

---

## Agent Weight Customisation

On the Agents page, each agent card has a weight slider. You can reduce or increase an agent's influence on the final score — for example, if you believe raw material costs are currently irrelevant for a particular stock, you can lower that agent's weight.

Changes are saved and applied to all future analyses in the current session. Weights must sum to approximately 1.0; the system validates this and will show an error if the total drifts too far.

You can also disable individual agents entirely (weight = 0) if you want to run a leaner analysis.

**Note:** The system also maintains its own *learned* weights per ticker from RL feedback. User-applied slider weights override the learned weights for that session.

---

## Analytics Page

The Analytics page and `/analytics` API expose the RL system's performance over time:

- **Direction accuracy** (`/analytics/agent-accuracy`) — per-agent hit rates and average price prediction error
- **Weight drift** (`/analytics/weight-drift`) — how far each agent's learned weight has moved from its default, shown as a time-series
- **Miss breakdown** (`/analytics/miss-breakdown`) — miss type counts by ticker (`direction_flip`, `model_bias`, `timing`, `magnitude`, `data_gap`, `external_shock`)
- **Conviction outcomes** (`/analytics/conviction-outcomes`) — streak length bucketed against accuracy (are long streaks more or less reliable?)
- **Sector comparison** (`/analytics/sector-comparison`) — cross-sector average scores and verdict distribution
- **Full RL export** (`/analytics/rl-export?format=csv|json`) — raw performance rows for external analysis
- **Power BI feed** (`/analytics/powerbi-feed`) — OData v4 JSON feed with EDMX metadata for direct Power BI Web connector ingestion

This page is honest about the system's blind spots. If crude oil spikes keep catching it off guard, that shows up in miss-breakdown — and the PromptEnhancer will start injecting crude oil queries into relevant agents automatically to reduce that gap over time.

---

## Logs Page

Live server log stream. Useful for monitoring when a daily review job runs, when a monthly forecast is being generated, or when an analysis is queued.

---

## Understanding the Limitations

**1. This is not financial advice.**
StockAgent is a research and pattern-recognition tool. Verdicts are AI-generated signals, not professional investment recommendations. Do not make investment decisions solely based on these outputs.

**2. Data gaps exist for some inputs.**
Some data sources do not have free, structured APIs. FADA/SIAM dispatch numbers, Vahan registrations, and RBI repo rate changes are fetched via web search proxies, not official structured data pipelines. The system is explicit about this in each agent's reasoning.

**3. Newly listed stocks may have limited data.**
Stocks that listed recently (e.g. ATHERENERGY) may not have enough yfinance history for technical analysis. The system falls back to LLM training knowledge in these cases, which is less reliable.

**4. The RL loop needs time to calibrate.**
In the first month of tracking a stock, agent weights are the system defaults — no learning has happened yet. The system becomes meaningfully more accurate after 2–3 months of daily feedback, and genuinely useful as a learning tool after 6 months.

**5. Sector coverage is uneven.**
All four active sectors (Automobile, Banking/BFSI, IT, Renewable Energy) run a single Unified Sector Analyst call over a one-pass, sector-aware data bundle — 9/6/8/6 dimensions respectively. Automobile additionally has the deepest live data fetchers and the full RL loop; the other sectors' fetchers continue to deepen over time.

**6. Black-swan events are unforeseeable.**
A surprise government order, a sudden exchange circuit breaker, or a geopolitical shock that was not in any news feed cannot be predicted. The system classifies these correctly as `external_shock` misses and does not penalise itself for them, but it also cannot warn you in advance.

---

## Technical Stack (for the curious)

| Layer | Technology |
|---|---|
| AI models (hybrid, via OpenRouter) | `qwen3.6-flash` for the chat assistant · `qwen3.7-max` for the verdict synthesis, RL reasoning, and the Unified Sector Analyst (all four sectors) · `qwen-2.5-72b` for the legacy per-dimension fallback agents (tier chosen by a benchmark; Qwen3-235B retired) |
| Analysis framework | Single unified-analyst call per run (all sectors); LangGraph parallel agent dispatch retained as the automatic fallback |
| Backend | Python FastAPI |
| Data — prices & OHLCV | yfinance (NSE/BSE prices, 10-year OHLCV, sector indices, commodities) |
| Data — news & search | Serper News API (primary), Tavily (fallback + policy docs) |
| Data — NSE exchange | nsepython — live FII/DII flows, bulk deals, upcoming earnings events |
| Data — MF flows | mfapi.in (AMFI) — sector ETF 30-day NAV momentum (herding signal) |
| Data — factor regime | IIMA Indian Fama-French 4-Factor dataset — long-run momentum/style regime prior |
| Frontend | React (Babel standalone, no build step) |
| Database | SQLite (analysis history) + JSON files (RL memory) |
| Deployment | Railway (Docker) |

All AI reasoning happens server-side. The browser receives structured JSON results.

---

## Frequently Asked Questions

**How long does an analysis take?**
Typically 15–25 seconds for any sector: one shared data fetch feeds a single reasoning-model call that scores all dimensions at once. Only if that call fails outright does the system fall back to the slower parallel multi-agent run (~60–120s). The exact time depends on how quickly the LLM API responds.

**How often should I re-run analysis on a stock?**
For active monitoring, once a week is usually sufficient unless a significant event (earnings, policy announcement, sharp price move) has occurred. The daily RL review updates forward forecasts automatically — you don't need to re-run analysis to get an updated prediction.

**Why does the score sometimes disagree with what I see in the news?**
The score reflects a weighted view across nine dimensions, including macro risks and technical patterns, not just recent news. A stock with positive news but rising input costs, deteriorating technicals, and policy headwinds will score below what the headlines suggest.

**What does it mean when two agents conflict?**
A conflict is flagged when two agents' scores differ by 0.30 or more (e.g. fundamentals = 0.70, macro = 0.38). The Signal Aggregator LLM explicitly addresses this conflict and explains which signal it weighted more heavily and why.

**Can I use this for short-term trading?**
The system is calibrated for 30-day horizon analysis, not intraday or weekly trading. The technical Pattern Analysis agent provides the most short-term-relevant signals, but the overall verdict is a medium-term view.

**Why are some verdicts different from what analysts say?**
By design. The system explicitly excludes analyst ratings, broker price targets, and consensus EPS estimates from its reasoning. It derives all scores from raw data: price history, financial statements, macro indicators, and news. Analyst consensus is a lagging signal that the system intentionally ignores.

**Is my watchlist saved?**
Yes. Your watchlist and agent weight preferences are saved on the server. They persist across browser sessions and devices.

---

## Key Terms Reference

A quick guide to every abbreviation, metric, and concept you will encounter in StockAgent's analysis output. Grouped by topic.

---

### How the System Works

| Term | What it means | In plain English |
|---|---|---|
| **Agent weight** | A number (0.0–1.0) representing how much influence one agent has on the final score | If `risk_macro` has weight 0.19 and scores 0.30, it pulls the final score down more than `sentiment` at weight 0.03 |
| **Signal Aggregator** | The component that combines all agent scores and resolves disagreements | "9 experts voted; 6 said BUY, 2 said SELL, 1 was neutral — here's why the BUY camp is right today" |
| **Conflict** | When two agents' scores differ by 0.30 or more | Fundamentals scores 0.72 (strong BUY) but macro scores 0.38 (near SELL) — flagged and resolved by LLM |
| **Learning ledger** | Permanent memory of patterns the system has noticed for a specific stock | After 3 months MARUTI has 4 lessons: "On RBI days trust risk_macro more", "Shravan months discount demand", etc. Each lesson carries trigger tags so it fires automatically on matching days |
| **Ticker dossier** | Living knowledge file per stock, updated by a daily curator on every day — hits included | MARUTI's dossier holds the current thesis, response signatures ("drops ~2% within 2 sessions of crude > $90"), open management guidance, recurring catalysts, FII/DII flow trend, and open questions |
| **RL feedback loop** | The daily process of comparing prediction to reality and updating agent weights | Every evening: system asks "was I right? who was wrong? by how much?" — and quietly adjusts. Agents are scored on their own calibration, not just the ensemble's result |
| **Conviction streak** | Consecutive days of the same verdict | 15 straight BUY days triggers caution — markets tend to correct sustained trends |
| **Market regime** | The system's classification of current broad market conditions | `MACRO_CRISIS` (VIX high, Nifty falling) → risk_macro agent gets 40% extra influence; `RISK_ON` (bull run) → fundamentals and sentiment elevated |
| **Prediction envelope** | The 30-day forward forecast generated at month start | Contains a predicted price for each of the next 30 trading days, updated daily by the RL loop |

---

### Compass Portfolio Advisor

| Term | What it means | In plain English |
|---|---|---|
| **Virtual holding** | A mock-money position entered at the real NSE close on the buy date, marked to market daily | Real prices, fake money — the advisor's track record is provable before any real capital moves |
| **`adj_avg_price`** | Corp-action-adjusted cost basis (splits, bonuses, dividends applied in ex-date order) | After a 1:1 bonus your ₹1,000 entry becomes ₹500 × double the shares — P&L stays truthful instead of showing a fake −50% crash |
| **Verdict precedence** | `EXIT > TRIM > ADD > HOLD` — a stronger signal always wins | An 11-month-old profitable position breaching its stop gets EXIT, never "wait for LTCG" |
| **ATR-scaled stop** | Stop-loss % = 3 × the stock's 20-day ATR, clamped to a market-cap band | HDFCBANK gets a tight ~8% stop; a volatile small-cap gets room up to 22% — one bad week of normal noise doesn't eject you |
| **WAIT_FOR_LTCG** | TRIM softened to HOLD when the position is 10–12 months old with an intact thesis | Selling at month 11 pays 20% STCG; waiting past month 12 pays 12.5% LTCG. Never applied to an EXIT |
| **Advice ledger** | Append-only JSONL of every verdict ever issued, with outcome slots at +10/30/60 trading days | The product grades its own advice — the Phase D learning loop tunes thresholds from this file |
| **Auto-promotion** | Held/watchlisted symbols automatically join the managed universe (cap 40) | Add a holding once; envelopes, daily reviews, and a dossier start without any other setup |
| **EOD digest** | Per-user end-of-day summary, event-triggered when the daily review finishes | Per-holding verdict + one-line reason + P&L, saved as one file per trading day |

---

### Indian Market Structure

| Term | Full Form | What it means in context |
|---|---|---|
| **NSE** | National Stock Exchange | Primary Indian exchange; tickers like `MARUTI`, `HDFCBANK` |
| **BSE** | Bombay Stock Exchange (BSE Ltd.) | Secondary exchange; block/bulk deals disclosed here |
| **SEBI** | Securities and Exchange Board of India | Stock market regulator — sets rules on insider trades, takeovers, fund reporting |
| **RBI** | Reserve Bank of India | Central bank — sets interest rates, regulates banks, manages currency |
| **MPC** | Monetary Policy Committee | RBI's 6-member panel that votes on repo rate every 2 months |
| **Repo rate** | Repurchase rate | Rate at which RBI lends overnight to banks. A cut typically boosts markets; a hike tightens credit |
| **FII** | Foreign Institutional Investor | Foreign fund houses (BlackRock, Nomura etc.). Heavy FII selling = market breadth signal |
| **DII** | Domestic Institutional Investor | Indian mutual funds, LIC, pension funds. Often cushion FII selling |
| **AMFI** | Association of Mutual Funds in India | Publishes monthly MF inflow/outflow data by sector category |
| **VIX** | India Volatility Index | Measures expected market fear. Above 22 = volatile; below 14 = calm. Used to detect market regime |
| **Nifty 50** | NSE's 50-stock benchmark | Proxy for FII flow direction in the system's regime detection |
| **SAST** | Substantial Acquisition of Shares and Takeovers | SEBI rule requiring disclosure when anyone buys >2% of a company — tracked as smart money signal |

---

### Fundamental & Valuation Metrics

| Term | What it measures | Quick example |
|---|---|---|
| **EBITDA** | Operating profit before interest, tax, depreciation | Maruti EBITDA margin 11.2% = ₹11.20 earned per ₹100 revenue from operations |
| **EBITDA margin** | EBITDA as % of revenue | Higher margin = more efficient operations vs peers |
| **P/E ratio** | Price relative to earnings per share | HDFC Bank P/E 22× vs 5-year median 24× = slight discount to history |
| **EV/EBITDA** | Enterprise value to operating profit | Standard cross-sector comparison: lower = cheaper relative to earnings power |
| **IRR** | Internal Rate of Return | Solar project IRR 14% vs cost of debt 8% → 6% spread = good project economics |
| **DSCR** | Debt Service Coverage Ratio | Project cash flow ÷ annual debt payments. DSCR 1.35× = comfortable; below 1.0× = distress |
| **RoA** | Return on Assets | Profit per ₹100 of total assets. HDFC Bank RoA 2.2% vs industry 1.4% = superior |
| **RoE** | Return on Equity | Profit per ₹100 of shareholder equity. TCS RoE 52% = very capital-efficient |

---

### Automobile Sector

| Term | Full Form | What it means |
|---|---|---|
| **FADA** | Federation of Automobile Dealers Associations | Monthly retail dispatch data (how many cars actually sold to end customers). The "real demand" number |
| **SIAM** | Society of Indian Automobile Manufacturers | Monthly wholesale data (factory to dealer). SIAM > FADA = dealers building inventory. SIAM < FADA = destocking |
| **Vahan** | MoRTH national vehicle registration database | Every vehicle registered in India. Key source for EV registration trends |
| **FADA vs SIAM gap** | Retail − wholesale delta | Large positive gap means dealers are sitting on unsold stock — bearish for near-term wholesale |
| **DGFT** | Directorate General of Foreign Trade | Export licensing data. Strong export growth can compensate for weak domestic demand |
| **OEM** | Original Equipment Manufacturer | The vehicle maker itself (Maruti, Tata Motors) — distinct from component makers |
| **FAME** | Faster Adoption and Manufacturing of Electric Vehicles | Government EV subsidy scheme. Changes to FAME directly affect EV OEM unit economics |
| **BS norms / CAFE** | Bharat Stage / Corporate Average Fuel Economy | Emission standards. Non-compliance with future norms = penalty risk |
| **PLI** | Production Linked Incentive | Manufacturing subsidy tied to incremental production. Automobile PLI: ₹26,000 Cr for advanced auto technology |
| **ADAS** | Advanced Driver Assistance Systems | Safety tech features rated by NCAP. Higher ADAS rating = competitive advantage in premium segment |

---

### Banking & BFSI

| Term | Full Form | What it means |
|---|---|---|
| **GNPA** | Gross Non-Performing Assets | Total bad loans ÷ total loan book. HDFC Bank 1.2% vs SBI 2.2% — lower is better |
| **NPA** | Non-Performing Asset | Any loan overdue more than 90 days |
| **Slippage** | Fresh NPA formation this quarter | Slippage 2% means 2% of previously "good" loans turned bad this quarter |
| **PCR** | Provision Coverage Ratio | % of NPAs already set aside as provisions. PCR 80% = ₹80 already written off per ₹100 of bad loans |
| **NIM** | Net Interest Margin | Lending rate minus deposit rate. 4% NIM = bank earns ₹4 per ₹100 deployed |
| **CASA** | Current Account Savings Account ratio | % of deposits in low-cost CA/SA accounts. Higher CASA = lower funding cost = better NIM protection |
| **CRAR** | Capital to Risk-Weighted Assets Ratio | Bank's capital buffer. RBI requires 11.5%; well-run banks maintain 14–16% |
| **CET1** | Common Equity Tier 1 | Highest-quality capital (retained earnings). Must be ≥ 8% under Basel III rules |
| **LAF** | Liquidity Adjustment Facility | RBI's daily lending/borrowing window for banks. Banks borrowing heavily via LAF = system liquidity deficit |
| **IBC** | Insolvency and Bankruptcy Code | Debt resolution law. Successful IBC resolution returns money to bank lenders |
| **Credit cost** | Provisioning / total advances | Bank's expense to set aside for future bad loans. Rising credit cost = deteriorating book |
| **ALM mismatch** | Asset-Liability Management mismatch | Bank funds long-term loans with short-term deposits — risk if rates change rapidly |

---

### IT Sector

| Term | Full Form | What it means |
|---|---|---|
| **CC growth** | Constant Currency revenue growth | Revenue growth after stripping out currency movements. "TCS grew 4.5% CC" = real business volume grew 4.5% |
| **TCV** | Total Contract Value | Full value of a new deal including all years. TCS $2.4B TCV in Q2 = $2.4B of future revenue booked |
| **EBIT margin** | Earnings Before Interest and Tax margin | Operating profitability. IT margins compressed when attrition is high and wages rise |
| **Attrition** | Annual employee turnover rate | Infosys attrition 12% (down from 28% peak) — stabilising delivery quality and costs |
| **Vertical mix** | Revenue by industry served | 35% BFSI means 35% of revenue is from banks/financial firms — US banking slowdown hits harder |
| **Guidance delta** | Reported guidance vs analyst expectations | Company guided 5–6% CC growth; street expected 6.5% → negative delta → stock fell |
| **H1B visa risk** | US specialty worker visa policy | H1B denial rates affect onsite delivery model economics for Indian IT companies |
| **AI disruption** | AI automation impact on current service lines | Application maintenance and testing (both large IT revenue segments) are most exposed to AI agent automation |

---

### Renewable Energy

| Term | Full Form | What it means |
|---|---|---|
| **PPA** | Power Purchase Agreement | Long-term contract to sell electricity at a fixed tariff. 25-year PPA = revenue certainty for the plant's lifetime |
| **DISCOM** | Distribution Company | State-owned electricity distributor and buyer. If a DISCOM delays payment, RE company's receivables pile up |
| **MNRE** | Ministry of New and Renewable Energy | Issues RE tenders, sets RPO targets, runs PLI for solar manufacturing |
| **RPO** | Renewable Purchase Obligation | Law requiring DISCOMs to buy a % of power from renewables. Creates captive demand for RE projects |
| **CUF / PLF** | Capacity Utilisation Factor / Plant Load Factor | % of theoretical maximum generation actually achieved. Solar CUF 22% is typical for Rajasthan |
| **Curtailment risk** | Grid operator backing down generator output | Tamil Nadu curtailed solar 40% in peak summer — contracted MWh not generated, revenue lost |
| **EV/MW** | Enterprise Value per Megawatt | Standard RE valuation benchmark. ₹8 Cr/MW vs peer ₹12 Cr/MW = discount |
| **Implied IRR** | Project return implied by current stock price | ADANIGREEN at current price implies 11% IRR — if below WACC, stock may be expensive |
| **Module price** | Cost per watt of solar panels | Chinese module price collapse in 2024 improved economics for new projects; doesn't help existing ones |
| **ISTS waiver** | Inter-State Transmission System charge waiver | Centre removed cross-state transmission charges for RE — lowers effective delivered cost |
| **Green hydrogen** | Hydrogen produced from renewable electricity | Emerging sector; NTPC and Adani building capacity — National Green Hydrogen Mission target 5 MMT by 2030 |

---

### Technical Indicators

| Term | What it measures | How it is used |
|---|---|---|
| **OHLCV** | Open, High, Low, Close, Volume — the 5 core data points for any trading period | Foundation of all technical analysis. Open = first trade price, Close = last trade price, High/Low = session extremes, Volume = shares traded. StockAgent fetches 10 years of daily OHLCV from yfinance for every tracked stock |
| **ATR** (Average True Range) | A stock's typical daily price swing over the last 14 trading days | ATR% = ATR ÷ price. HDFCBANK ATR ~0.8% (stable), ADANIGREEN ATR ~3.5% (volatile). Used to calibrate how large a prediction miss needs to be before triggering a thesis review — a 2% miss on a 0.8% ATR stock is serious; the same miss on a 3.5% ATR stock is normal noise |
| **RSI** (Relative Strength Index, 0–100) | Momentum — is the stock overbought or oversold? | RSI > 70 = overbought, potential reversal. RSI < 30 = oversold, potential bounce. Used in all sector pattern agents and to amplify mean-reversion caution when conviction streak is high |
| **MACD** (Moving Average Convergence Divergence) | Trend momentum — signal line and histogram | MACD crossing above its signal line = bullish momentum building. Renewable energy uses weekly MACD to filter out short-term sector noise |
| **Bollinger Bands** (20-day MA ± 2σ) | Volatility envelope around the moving average | Stock near upper band with declining volume = exhaustion signal. Stock touching lower band on high volume = capitulation. Used in automobile pattern agent |
| **SMA / EMA** | Simple / Exponential Moving Average | SMA gives equal weight to all days in the window. EMA gives more weight to recent days. 50-day and 200-day SMAs are used for trend direction; short-term EMAs for momentum |
| **Golden / Death Cross** | 50-day SMA crossing the 200-day SMA | Golden cross (50 rises above 200) = long-term bullish shift. Death cross (50 falls below 200) = long-term bearish shift. Used in RE technical agent as a filter for sector-level trend |
| **Support / Resistance** | Historical price levels where buying or selling has repeatedly stalled | Support = floor where buyers historically stepped in. Resistance = ceiling where sellers historically emerged. Used in pattern analysis to define price targets and stop zones |
| **Fibonacci retracement** | Key pullback levels derived from the Fibonacci sequence (23.6%, 38.2%, 50%, 61.8%) | After a strong move, stocks often retrace to these levels before resuming. Used in automobile pattern agent to identify entry zones after a rally |
| **Delivery %** | Proportion of traded volume resulting in actual delivery (not squared off intraday) | High delivery % on a rising stock = genuine accumulation. Low delivery % on a rally = speculative froth. Used as a conviction signal in the conviction streak warning |
| **Open Interest (OI)** | Total outstanding F&O contracts at any point in time | Rising OI with rising price = new longs being added (bullish). Rising OI with falling price = new shorts (bearish). Used as a supplementary signal in technical pattern analysis |

---

## Reference Documents

| Document | Purpose |
|---|---|
| [CODEBASE.md](CODEBASE.md) | Full module map, all API endpoints, configuration reference |
| [docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md](docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md) | Compass design spec: portfolio core, position advisor, discovery engine, proactive delivery — full 4-phase roadmap |
| [docs/RL_DESIGN.md](docs/RL_DESIGN.md) | RL feedback loop: formulas, daily flow, schemas, static vs LLM, knowledge layer (ticker dossier + executable claims, §23) and measurement phase (eval harness, §24) |
| [docs/AGENT_DESIGN.md — not yet created] | All sector agents, sub-scores, implementation status, full terminology reference |
| [docs/AGENTIC_DESIGN.md](docs/AGENTIC_DESIGN.md) | All agents, tasks, data sources, static vs LLM boundary |
