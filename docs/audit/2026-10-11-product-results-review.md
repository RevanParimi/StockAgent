# Product results review — 2026-10-11

Requested by the owner on 2026-10-11: a deep review of trading results, explanations, models,
portfolio breadth, the interface, the "central intelligence" and the morning brief, from the view
of a non-technical investor and a market practitioner, ending in tasks that move results. The
code inspected is `b9cc851`. Nothing in production was read, changed or triggered by this review.

## How to read the evidence

| Label | Meaning here |
|---|---|
| **Code** | Traced in the repository at `b9cc851`. |
| **July snapshot** | The owner's paper portfolio as copied locally on 30 Jul 2026 (`analysis_data/portfolio/primary`, ignored). It predates the September fixes, but the exit and narration code it ran is unchanged since (checked with `git log`). |
| **Public prices** | Yahoo closes for the July exits and the Nifty 50, read locally on 11 Oct. |
| **Recorded production** | Dated facts already in the evidence receipts, the KT section 1 table or the owner's screens. |
| **Production probe** | The owner's read-only probe of 11 Oct (section 11): trades since 1 Aug, weekly equity, advice, declined switches, the shelf, the nightly auditor's grades and brief repetition. Section 11 refines sections 1, 4 and 6. |

The July sample is small (9 sales). It shows a mechanism, not a measured rate. Section 11 adds
the production record from August to October, and section 10 sets the measurement from here.

## Summary for the owner

| Your question | Short answer | Tasks |
|---|---|---|
| 1. Sales are mostly at a loss | Two problems (production, section 11). **Winners are cut early and losers run to the stop:** since August the average win was +7.5% and the average loss −11.9%, so each trade loses 2.2% on average. The price-path rule sells recoveries: after 30 sessions, 6 of 7 stocks we sold had beaten the Nifty. **The stocks held lagged the market**, while discovery's ideas beat it 13 times in 21. Weekly tracking should show this every Sunday. | PR-002, PR-009, PR-004 |
| 2. Reasons are code-like, not company-specific | The model writing the reason is given only the rule code (`thesis_break`), the price and the regime label, with no results, news or thesis. It can only rephrase the code. | PR-005, PR-006, PR-007 |
| 3. Are the models good enough? | The decisions do not depend on model strength (code decides). What the user reads is written by the cheapest tier from empty inputs. Feed it facts and move it up one tier; bench newer models on our own data before switching. | PR-007, PR-012 |
| 4. Only 2 stocks; want 10+ and ₹10 L working | The autopilot cannot open a new position except by selling one (a SWITCH). Plain exits leave cash idle forever. Position size is measured against the money **in stocks**, not the whole portfolio, so with 2 holdings ADD can never fire. Owner decision (12 Oct): add ₹2 L paper capital; aim for 12 holdings of about ₹83,000, at least 10 and at most 15. The idea supply must grow first: today about 6 shelf ideas qualify, and 1 under the strict gate. | SA-050, SA-051, PR-004, SA-048, SA-049 (amended) |
| 5. UI has jargon and static values | The first screen greets everyone as "Aditi", shows "Auto sector +1.24%" and "Nifty Auto 22,847" as fixed text. The portfolio page shows "Avoided loss +₹…" that is a score change × 10,000, not money. Every member sees operator tools. Members need 4 screens, not 11. | PR-001, PR-010 |
| 5b. Central intelligence | The planned one-engine design is right for the research verdict. Its gap is that the **trades** don't use it: buys and sells run on price-path misses and stops. No new platform is needed: an investment case per holding, a daily company-event feed, and exits that read both. | PR-005, PR-006, PR-009, PR-011 |
| 6. Morning brief repeats itself | Overnight news comes from 4 generic Google News searches. "Last 24 hours" means fetched, not published, so old stories return daily, and company news is filtered out by design. In late July the same RBI/rupee story led 8 briefs running. | PR-003, PR-008 |
| 7. Kill or rework | Retire: price-miss exits (after proof), fake "lessons" figures, Learn quiz, member-visible operator screens, auto-sector hard-coding. Rework: narration inputs, brief sources, idea supply. | Section 8 |
| 8. Tasks with impact | 12 new stories (PR-001 to PR-012) plus 4 existing ones moved forward. Each names the result it should move and how it is measured. | Section 9 |
| Found on the way | `GET /ui/logs` and `/ui/logs/stream` require no sign-in and redact nothing: anyone with the URL can read live server logs, including user ids (code inspection; not called). | FIX-007, first |
| 9. What an expert says | "Why we own it, what we expect, what would prove us wrong, what we watch next." Templates and examples in section 7. | PR-005, PR-007 |

## 1. Why sales lose money

### The decision chain (code)

Every month the forecast job turns the research verdict into a **30-day daily price path**. A
bulk-tier LLM call (`core/intelligence/rl/algorithms/price_interpolator.py`) picks the month's
expected return and a path shape. Each evening the daily review compares the close with that
day's point on the path. A miss larger than `max(1.5%, 1.5 × ATR%)` triggers the **thesis
reviewer** (`core/intelligence/rl/agents/thesis_reviewer.py`). It is one short LLM call of about
250 tokens. By its own docstring it "does NOT re-run agents or fetch new data". It answers
whether the 30-day thesis is still intact.

The advisor (`core/portfolio/advisor.py`, `decide`) then fires EXIT when:

| EXIT trigger | What it really means |
|---|---|
| `stop_breach` | Loss beyond a volatility-scaled stop (8–12% large cap, 12–18% mid, 15–22% small). A sound risk rule. |
| `trailing_stop_breach` | Gave back a volatility budget after a gain of 10%+. A sound profit-protection rule. |
| `thesis_break` | The latest thesis review said "not intact" **and** the remaining path now ends more than 1% below today's close. |
| `shock_reforecast`, `crisis_regime_bearish` | Market-level events with a falling path. |

`thesis_break` is the problem. A stock that drops sharply for a day misses its path. The reviewer
then judges the thesis from that miss alone. The advisor reads the latest review in the month's
cycle, so a "not intact" answer stands until another miss triggers a new review. Whenever the
remaining path then ends more than 1% below the close, EXIT fires. A single bad day can
therefore sell the position: selling on weakness. Nothing in the rule asks whether the
company's results, guidance, orders or valuation changed. The rule has not changed since
July (`git log` over the advisor, thesis reviewer and daily review shows only data-gate,
identity and trailing-stop additions).

**Example.** We buy a stock at ₹500 for its order book. On day 4 the whole market falls 2% and
the stock falls 4%. The path expected ₹505, so the close missed by more than 1.5 × ATR. The
reviewer, seeing only the miss, says "thesis not intact". The re-forecast path ends at ₹478.
EXIT at ₹480, a 4% loss. Nothing about the order book changed. A practitioner would have held.

### What July shows (July snapshot + public prices)

- The portfolio was seeded with **16 stocks × ₹62,500 = ₹10 L**, chosen as the managed sector
  universe rather than by conviction.
- **9 sales between 10 and 28 July, every one triggered by `thesis_break`** (two as SWITCH). The
  positions with a recorded cost were held **4 to 17 days**. 2 sales made money; realized total
  **+₹524** on ₹10 L. Four early rows predate cost stamping and carry no P&L.
- **After we sold** (8 measurable; TATAMOTORS is no longer quoted after its demerger):

  | Horizon after the sale | Stocks that beat the Nifty afterwards | Mean excess | Median excess |
  |---|---:|---:|---:|
  | 20 sessions | 6 of 8 | +4.9 points | +3.0 points |
  | 40 sessions | 6 of 8 | +5.0 points | — |

  TVSMOTOR was sold at a ₹1,193 loss on 16 Jul; over the next 20 sessions it rose 21.9% while
  the Nifty rose 1.3%. PERSISTENT and KPITTECH beat the Nifty by 6.7 and 10.6 points.
- **Plain reading:** the exits were mostly early. A sale is a bet that the stock will do worse
  than the alternative. In this sample the alternative did worse. Eight sales in one month is
  far too few to call it a rate. It is enough to make "what happened after we sold" the first
  number the weekly report shows.

### What production shows so far (recorded)

On 27 Sep the owner's screen showed ₹8,09,297 of ₹9,99,611 in cash (81%) and 2 holdings.
ACMESOLAR's full exit alone moved about ₹2.27 L to cash. The trades between August and October
are **pending** the probe.

### Measuring it weekly

The nightly auditor already grades every EXIT, TRIM and SWITCH against the benchmark at 10, 30
and 60 sessions (`core/audit/outcomes.py`, `excess_pct`). Its results are not in any report a
person reads. PR-002 puts them, with the closed-trade record, into the Sunday weekly review and a
stored weekly row:

| Weekly number | Why it matters | Red flag (predeclared) |
|---|---|---|
| Closed trades: count, win rate, average win, average loss, **expectancy** per trade | A majority of winners can still lose money | Expectancy below 0 for 3 weeks running |
| **Sold too early**: share of exits whose stock beat the Nifty 10 and 30 sessions later | Directly tests the exit rule | Above 60% at 30 sessions, over exits matured in the trailing 8 weeks, with at least 8 of them (production 11 Oct: 6 of 7) |
| Exit reasons mix | Shows which rule is doing the selling | `thesis_break` above 50% of exits |
| Portfolio vs Nifty (money-weighted, from SA-051) | "Is this good?" | Behind the Nifty by more than 3 points over 4 weeks |
| Invested share and holdings count vs the floor | Breadth | Below the configured floor in a normal regime |
| Average holding period | Churn | Under 10 sessions |

A red flag says so in plain words at the top of the weekly email. It changes nothing by itself.

## 2. Why the reasons read like code

The narrator (`core/portfolio/narrator.py`) builds its prompt from exactly six things: the
verdict, the symbol, the close, the regime label, the trigger codes and the note codes. It is
told not to mention the position. It runs on the bulk tier (`deepseek-v4-flash`). Then it
appends "Your position: −6.2% vs a 12.0% stop."

The only output it can produce is a paraphrase of the code. The one July sale with a stored
reason reads: *"The thesis for IDFCFIRSTB has broken down under current market conditions,
triggering an exit signal at the close of ₹85.75. This deterministic verdict reflects a regime
shift to normal …"* A reader learns nothing about IDFC First Bank.

The facts that would make it a real reason already exist in the system, but they never reach
the narrator:

| Fact a reader wants | Where it already lives |
|---|---|
| Why we bought it | The deep dive's `investment_thesis`, `conviction_drivers`, risks (score store, shelf idea `thesis`) |
| Latest results, guidance, management commentary | The ticker dossier, fed by the weekly event ingestor (results, concalls, presentations) |
| Today's company announcements | `services/data/fetchers/nse_announcements.py` |
| Price levels: entry band, invalidation | The shelf idea (`entry_low`, `entry_high`, `invalidation_level`) |
| Institutional activity | FII/DII flows, bulk and block deals (`nse_market.py`) |
| Next event | Results calendar (`corporate_events.py`) |

PR-005 records an **investment case** per holding from these. PR-006 adds a daily company-event
feed. PR-007 rewrites the narration to use both, in the investor's words, with a check that every
number it writes appears in its inputs.

## 3. Models

### Where each tier runs (code, `config.yaml` `llm:`; `.env` sets no model)

| Tier | Model | Used for |
|---|---|---|
| Fast | `qwen/qwen3.6-flash` | Chat tool loop; the 08:45 pre-open shock check |
| Reasoning | `z-ai/glm-5.2` | The unified analyst (the research verdict), aggregator, feedback and thesis reviews, chat fallback |
| Bulk | `deepseek/deepseek-v4-flash` | Sector-agent scoring, **trade narration, morning brief, weekly review**, macro-news review, event and dossier digestion, the 30-day price path, IPO narration |

### Assessment

- **Decisions do not need a stronger model.** Code decides the portfolio actions. The research
  verdict already uses the reasoning tier, and the one-engine design moves scoring into code.
  A better model will not fix an exit rule driven by price-path misses.
- **What users read is written by the cheapest tier from almost no facts.** That is an input
  problem first (section 2). Moving narration, the brief and the weekly to the reasoning tier
  costs little: at most one narration per holding per review day (cached), one brief a day and
  one weekly review, per account.
- **Newer options exist.** OpenRouter lists GLM-5.3 (released 18 Aug 2026, $1.40/$4.40 per
  million tokens) and DeepSeek V4 Pro (0813, $0.435/$0.87). GLM-5.2 now lists at $0.49/$1.54.
  The `llm.cost_rates` entry for GLM-5.2 still says $1.218/$3.828 (dated 17 Jul), so cost
  telemetry likely overstates spend. Verify before relying on either figure.
- **Recommendation.** Do not upgrade blindly. PR-012 benches the reasoning tier and one step up
  on our own stored bundles, for the two roles that matter to users: reading events from text
  and explaining a decision. Grade them on grounding (no invented numbers) and specificity, then
  choose per role. Refresh the cost rates.

## 4. Breadth: 10+ stocks and ₹10 L working

### Why the portfolio shrank (code)

`core/portfolio/autopilot.py` opens a new position **only** through a SWITCH, which needs all of:
an EXIT on a holding, an active shelf idea in a strictly **underweight** sector, and a
conviction gap of 0.15 over the holding. ADD only tops up a stock already held. A plain EXIT
parks its proceeds in cash, and nothing reinvests them. From 16 seeded stocks, every exit
without a qualifying switch made the portfolio smaller. That leads to 2 holdings and 81% cash.
This is already recorded as SA-049 (owner decision of 27 Sep) and in KT section 6.

### Why breadth matters for the data, not only the money

With 2 holdings we see perhaps one exit a fortnight, and a month of results says nothing. With
10 or more we see several exits a week, enough to judge the exit rule (PR-009) in 4 to 6 weeks.
Breadth is how the product gets evidence quickly.

### The floor you asked for

Add to SA-049, configurable, with a per-portfolio override for users with other needs:

```yaml
portfolio:
  min_holdings: 10          # at least; not exactly
  target_holdings: 12       # what deployment aims for (owner, 12 Oct: "more stocks")
  max_holdings: 15          # stops over-dilution
  min_invested_inr: 1000000 # ₹10 L working in a normal market
```

**The arithmetic.** Capital today is about ₹10 L, so ₹10 L invested would mean 100% invested,
with no cash for rotation, the cash floor or switches. Two options were offered:

- **(A, recommended)** Add ₹2 L of paper capital (₹12 L total), so about ₹10 L is invested (83%)
  and ₹2 L is left for rotation. SA-051's Nifty comparison counts the deposit on its own date, so
  returns stay honest.
- **(B)** Keep ₹10 L and read the floor as 90%.

**Owner decision (12 Oct): A,** with "more data and more stocks". Deployment therefore aims for
**12 holdings of about ₹83,000** (₹10 L ÷ 12, 6.9% of ₹12 L each): never fewer than 10, never
more than 15. More holdings means more closed trades, so the evidence arrives sooner. There is
no deposit path in the app today: only a manual holding add raises `capital_in`. SA-049 adds a
dated, owner-only "add paper capital" action, and the top-up happens at its rollout.

In RISK_OFF the floor relaxes (SA-049's regime targets); in MACRO_CRISIS no new positions. When
the floor cannot be met, the run records why ("only 6 qualifying ideas", "equity below floor plus
buffer"). It never breaches a cap to meet the floor.

### Idea supply (code, `config.yaml` `discovery:`)

The weekly funnel screens the whole NSE list down to 40 candidates and runs **10 deep dives a
week**, and the shelf holds at most **10** ideas at conviction 0.55 or more. Filling 10 positions
plus replacements needs roughly 15 to 20 qualified ideas across 5 or more sectors. PR-004 raises
the shelf to 20, deep dives to 20 a week, and caps any one sector at 3 ideas. It also lets an
owner-watchlist stock with an actionable BUY qualify. A deep dive is one reasoning call (a
bundle of up to 18,000 characters in, up to 6,000 tokens out), so 10 more a week is small in
cost; PR-004 records the measured figure.

### Order matters

Deploying cash with today's exit rule will churn: buy, then `thesis_break` a week later. So the
sequence is: one sizing rule (SA-050), the Nifty comparison (SA-051), idea supply (PR-004),
costs (SA-048, so churn is not free on paper), then SA-049 with the floor. PR-009's exit shadow
runs alongside from the start, and the weekly scorecard (PR-002) watches churn from day one.

## 5. The interface

### What a new user sees today (code, `src/frontend/prototypes`)

**Fixed values that look live:**

| Where | Shown to everyone |
|---|---|
| Home hero (`home.jsx:445–446`) | "Good afternoon, **Aditi**." and "**Auto sector +1.24%** today." (fixed text, any time of day) |
| Home, Nifty box (`home.jsx:542`) | "Nifty Auto **22,847**" (fixed) |
| Home buttons | "Run on MARUTI"; "Browse by category: Pick a slice of the auto sector" |
| Home, month tab | "How agents are voting" with eight fixed bars when the API sends none |
| Mock fallbacks (`data.jsx`) | Watchlist of five auto stocks, sample suggestions and figures whenever `/ui/bootstrap` fails |

**Money figures that are not money** (`services/api/routes/ui_data.py:1302, 1346–1348`):
"Missed gain +₹X — trades you didn't take" and "Avoided loss +₹X — smart skips & exits" are the
change in a composite score × 10,000, printed as rupees. "Realized loss" is fixed at 0. The
"lessons" under them are templates ("When score crosses 0.70+, X has shown sustained upside.
Watch agent weights."). This is the most urgent UI fix: a user shown false rupee figures
should not trust any other number on the page.

**Operator tools shown to every member:** Prompt Lab, Analytics (agent accuracy, weight drift,
miss types), RL Monitor, Logs, the Agents page ("tap to tune weight"), and a Tweaks panel. The
weight save is owner-only on the server, so a member gets a failed save.

**Internal words on customer screens:** verdict, conviction, agent take, agent breakdown,
conflicts resolved, regime labels, shelf.

### What a member needs

| Screen | Contents |
|---|---|
| **Today** | What changed overnight for **your** stocks first, then the market in three lines; anything you need to know before 09:15 |
| **Portfolio** | You vs the Nifty, in stocks vs cash, each holding with its one-line investment case and "what we're watching", recent trades with plain reasons, the weekly scorecard |
| **Ideas** | What we would buy next and why, with the price we would pay |
| **Ask** | Chat |

Everything else moves behind an owner-only **Operator** menu or is removed: Learn (course and
quiz), categories, "Suggested for you", agent voting bars, agent breakdown, the Tweaks panel.
That removes roughly three quarters of what a member sees today, and nothing in the backend.
PR-001 removes the false and fixed values and hides the operator tools this week. PR-010 is the
four-screen redesign.

## 6. Central intelligence: market reasons, not only data analytics

### What a practitioner checks before buying or selling, and our coverage

| Check | Today | Planned / new |
|---|---|---|
| Earnings trend, surprise, quality | Quarterly P&L from Yahoo; no consensus | Growth and Quality factors (SA-045) |
| Guidance and management commentary | Event ingestor reads results and concalls **weekly** into the dossier; not used in trades or the brief | Daily feed (PR-006); used by case, exits, brief (PR-005, PR-008, PR-009) |
| Company announcements: orders, ratings, management change, regulatory action | Fetched for analysis runs; not watched daily for holdings | PR-006 |
| Valuation vs its own history and true peers | Peer P/E against the wrong peers for generic stocks | SA-044, SA-045 (Value) |
| Promoter and insider buying or selling, pledges | **Dark**: the discovery weight exists, no source | PR-011 |
| Institutional ownership changes per stock | Market-level FII/DII daily; per-stock shareholding not compared quarter to quarter | PR-011 |
| Sector cycle and policy | Macro news with sector tags; sector lenses planned | SA-026, SA-046 |
| Trend and relative strength | Present (technicals, 52-week, momentum screen) | SA-045 (Momentum vs the lens benchmark) |
| Global overnight cues: US close, Asia, crude, dollar, US yields | One generic search at 08:45 | PR-003, PR-011 |
| A written case with a target and an invalidation | Shelf ideas have entry and invalidation prices; **holdings have no case** | PR-005 |

### Verdict on the design

The [one-engine design](../superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md) is
the right direction for the **research verdict**. Code computes the facts, an LLM reads the text
into dated events, code decides and the LLM explains. Its text side (SA-046) is where market
reasons enter.

The gap is downstream. **The portfolio does not trade on that verdict's reasons.** It trades on
price-path misses and stops (section 1), and it explains with rule codes (section 2). No new
framework is needed. Four bounded pieces connect the intelligence to the money:

1. an **investment case** recorded per holding (PR-005);
2. a **daily company-event feed** for held, watched and shelf names (PR-006), later the input
   SA-046 reads;
3. **exits that read the case and the events**, proven in shadow first (PR-009);
4. **narration and the brief built from both** (PR-007, PR-008).

New data (PR-011) widens what the case and the events can see. The data sources are free (NSE
disclosures, Yahoo indices) but must be proven to work from the production container first: the
IPO ladder fetch broke in production in September.

## 7. What an expert says when buying or selling

A reader agrees with a decision when it answers four questions: **why we own it, what we expect,
what would prove us wrong, and what happens next.** Today's text answers none.

**Today**, the rule-text the code writes when narration is off or fails (numbers illustrative):
"EXIT — the original thesis is assessed as broken while the forecast points down. Your
position: −6.2% vs a 12.0% stop." The model-written version is no more specific (section 2).

**Target shape (illustrative company and numbers):**

> **Bought ABC Bank at ₹212 (8% of the portfolio).**
> **Why:** loans grew 18% last quarter with bad loans steady at 1.9%; the stock trades at 1.3×
> book against its 5-year average of 1.5×; foreign funds raised their stake by 1.2 points.
> **What we expect:** ₹245–255 over 6 to 9 months as the valuation gap closes.
> **We are wrong if:** bad loans pass 2.5% at the January results, or it closes below ₹190.
> **Next check:** Q3 results on 18 January.

> **Sold XYZ Tech at ₹5,420 (−6.2%).**
> **Why:** revenue fell 4% on the quarter and management cut its full-year outlook for the
> automotive design business, which was the main reason we owned it. The stop was not hit; we
> sold because the reason broke.
> **The money:** ₹1.1 L moves to DEF Capital Goods, whose order book grew 30%.

> **Holding PQR Power through a 7% fall.**
> **Why:** the fall followed the sector after a policy headline that does not affect its signed
> contracts. Its case is intact; the price is above our ₹410 line.

Every number in such a text must come from the stored case, the event feed or the price record.
PR-007's check rejects an output with a number it cannot trace.

## 8. Retire or rework

| Item | Action | Why |
|---|---|---|
| `thesis_break` from price-path misses as an EXIT trigger | **Retire after PR-009's shadow proves the replacement no worse** | Sells on weakness; July exits outperformed afterwards |
| "Missed gain / Avoided loss / Realized loss" and templated lessons | **Remove now** (PR-001) | Score × 10,000 shown as rupees |
| Fixed hero text, Nifty Auto figure, MARUTI buttons, auto categories, agent-vote fallback, mock fallbacks | **Remove now** (PR-001) | Fixed values presented as live |
| Operator screens for members (Prompt Lab, Analytics, RL Monitor, Logs, Agents tuning, Tweaks) | **Owner-only now** (PR-001), Operator menu later (PR-010) | Confusing and fails for members |
| Learn page (course, quiz) | **Remove** (PR-010) | Static content, not product value |
| Manual agent-weight tuning while learning is contained | **Owner-only, and reconsider** (PR-010 decision) | It moves live weights outside the contained learning policy |
| Macro-only overnight section | **Rework** (PR-003, PR-008) | Stale and blind to holdings |
| Narration from codes on the bulk tier | **Rework** (PR-007) | Cannot say anything specific |
| Discovery's dark insider and MF signals | **Fill or delete** (PR-011) | Weights for signals that never arrive |

Kept as they are: the stops and trailing stop (sound risk rules), the decision gate, the
nightly auditor (it already measures exits; PR-002 surfaces it), the one-engine plan, and the
learning containment.

## 9. Tasks

Twelve new stories, prefixed **PR** (product results), plus four existing stories moved forward.
Each card names the result it should move and how it is measured. Points are provisional.

| Order | Story | Result it moves | Pts | Depends on |
|---:|---|---|---:|---|
| 0 | [FIX-007](../planning/PI-2026-09/stories/FIX-007.md) Server logs readable only by the owner (privacy; ahead of the track by the PI's rule) | No log exposure | 1 | — |
| 1 | [PR-001](../planning/PI-2026-09/stories/PR-001.md) Remove invented figures and fixed demo values; hide operator tools from members | Trust in every number shown | 3 | — |
| 2 | [PR-002](../planning/PI-2026-09/stories/PR-002.md) Weekly results scorecard with a "sold too early" check | Visible weekly profit evidence | 3 | — |
| 3 | [PR-003](../planning/PI-2026-09/stories/PR-003.md) Fresh overnight news: no repeats, published-date freshness, global cues | Brief novelty | 2 | — |
| 4 | [SA-050](../planning/PI-2026-09/stories/SA-050.md) One sizing and entry rule for every autopilot buy, measured against the whole portfolio | No outsized positions; ADD unlocked; no buys far above the entry band | 3 | — |
| 5 | [SA-051](../planning/PI-2026-09/stories/SA-051.md) The portfolio against the Nifty, honest labels | "Is this good?" | 3 | — |
| 6 | [PR-004](../planning/PI-2026-09/stories/PR-004.md) Enough researched ideas for 10+ positions | Idea supply | 3 | — |
| 7 | [PR-006](../planning/PI-2026-09/stories/PR-006.md) Daily company-event feed for held, watched and shelf names | Company-specific facts | 3 | — |
| 8 | [PR-011](../planning/PI-2026-09/stories/PR-011.md) New data: promoter and insider trades, pledges, shareholding changes (P1 since 12 Oct: "I need more data") | Wider view of each stock | 3 | PR-006 |
| 9 | [PR-009](../planning/PI-2026-09/stories/PR-009.md) Exit on evidence, not on a price-path miss (shadow, then switch) | Fewer premature, losing exits | 5 | PR-002, PR-006 |
| 10 | [SA-048](../planning/PI-2026-09/stories/SA-048.md) Costs and tax in paper P&L | Honest net results | 3 | — |
| 11 | [SA-049](../planning/PI-2026-09/stories/SA-049.md) Put idle cash to work, **with the breadth floor and the ₹2 L top-up** | 10–15 holdings, cash working | 7 | SA-050, SA-051 |
| 12 | [PR-005](../planning/PI-2026-09/stories/PR-005.md) An investment case for every position | Reasons users agree with | 5 | PR-006 |
| 13 | [PR-007](../planning/PI-2026-09/stories/PR-007.md) Plain, fact-grounded buy and sell explanations | Reasons users agree with | 3 | PR-005, PR-006 |
| 14 | [PR-008](../planning/PI-2026-09/stories/PR-008.md) "Your stocks overnight" at the top of the brief | Brief relevance | 3 | PR-003, PR-006 |
| 15 | [PR-010](../planning/PI-2026-09/stories/PR-010.md) Four screens for members; Operator menu for the owner | Demo-ready product | 5 | PR-001 |
| 16 | [PR-012](../planning/PI-2026-09/stories/PR-012.md) Choose models by role, benched on our own data; refresh cost rates | Explanation quality per rupee | 2 | PR-007 |

New points: 41 (40 product, 1 privacy). Moved-forward points: 16. SA-049 grows from 5 to 7
(the floor and the paper-capital top-up), and SA-050 from 2 to 3 (the denominator and the entry
band, section 11). The owner confirmed this order on 12 Oct and moved PR-011 up ("I need more
data").

**What these tasks cannot promise.** They make results visible, make the portfolio broad enough
to learn from, stop one identified source of early selling, and make every reason specific. They
cannot guarantee profit. Whether the exit change helps is decided by PR-009's predeclared gate on
matured outcomes, and "no benefit" is a valid answer.

**What they push back.** The reliability and learning stories (SA-012 onward, SA-033 to SA-042)
move after this block. None is a production incident today; security and incident work still
jumps the queue under the PI's rules.

## 10. One-month measurement plan

The latest code changes landed from 20 Sep. Judge on the four weeks to 8 Nov, not on July.

1. **Baseline: done 11 Oct** (section 11). The owner ran the read-only probe
   `analysis_data/review_20261011/portfolio_results_probe.py` (no ids, emails, logs or env
   printed). Re-run it each Sunday until PR-002 ships.
2. **Weekly, 18 Oct to 8 Nov.** Until PR-002 ships, re-run the probe each Sunday evening. After
   it ships, read the Sunday weekly review. Compare against section 1's red flags.
3. **What would change this review's conclusions.** If the auditor's matured exits since
   September beat the Nifty **less** often than they lag it (sold too early under 40%), the
   exit rule is working and PR-009 drops in priority. If shelf ideas lagged the Nifty on paper,
   SA-049 should not be switched on until PR-004 and SA-045 improve the ideas.

## 11. Production baseline (the owner's probe, 11 Oct)

The owner ran the read-only probe on 11 Oct. The figures below are the paper portfolio of the
owner's account and aggregate counts, checked against Yahoo closes. Grades come from the nightly
auditor's stored rows (`advice_outcomes.jsonl`). Samples are small, and daily HOLD rows overlap
heavily (the same few stocks on consecutive days), so read them as indications.

### Where the money stands

| Measure | Value |
|---|---|
| Holdings | 2: FEDERALBNK (406 at ₹355.44, since 7 Aug), WELCORP (21 at ₹2,553.60, since 1 Sep) |
| Cash | ₹8,09,297 of equity ₹9,95,301 (81%) |
| Since the start (10 Jul) | Portfolio **−0.5%**. Nifty 24,206.90 → 22,231.80, **−8.2%**. ₹10 L in the Nifty would be ₹9,18,408, so the portfolio is ₹76,893 ahead |
| Since 7 Aug | Portfolio +1.5%; Nifty −9.5% |
| Invested share | 58.8% (7 Aug) → 40.8% (11 Sep) → 18.7% (8 Oct) |

**Plain reading:** the portfolio beat a falling market mainly by sitting in cash, and that was an
accident of the shrinking rule (section 4), not a decision. The news through September was
risk-off: war costs, tariff threats, $17 billion of foreign outflows, rate-hike talk. A
deliberate rule would have said "risk-off, so we hold 50% cash" and explained why. The same
cash will cost money in a rising market. The breadth floor must therefore stay regime-aware, as
SA-049 specifies: in RISK_OFF the floor relaxes, and in MACRO_CRISIS there are no new positions.

### Sales since 1 August

| Sale | Rule | Result | Held |
|---|---|---:|---:|
| PAYTM, 7 Aug (switch) | thesis_break | +7.6% | 27 days |
| TATAELXSI, 7 Aug (switch) | thesis_break | +2.5% | 27 days |
| INOXWIND, 11 Aug (switch) | thesis_break | −9.9% | 31 days |
| ADANIGREEN, 12 Aug (switch) | stop_breach | −13.3% | 32 days |
| OLECTRA, 1 Sep (switch) | stop_breach | −12.4% | 52 days |
| WAAREEENER, 8 Sep | stop_breach | −12.0% | 59 days |
| STARHEALTH, 10 Sep | thesis_break | +0.1% | 34 days |
| ACMESOLAR, 24 Sep | thesis_break | +19.8% | 69 days |

- **4 wins, 4 losses, realized +₹13,776.** ACMESOLAR alone made +₹37,551; without it the sales
  lost ₹23,775.
- **Average win +7.5%, average loss −11.9%, so expectancy is −2.2% per trade** (before costs).
  Winners are cut early and losers run to the full stop: the reverse of "let winners run, cut
  losers short".
- **The losses are stops on the original sector list** (renewables and EVs): three of the four
  losers, at −12% to −13%. The price-path rule (`thesis_break`) sold the winners.

### What happened after we sold (the auditor, every exit since 10 Jul)

| Horizon | Exits graded | Stock beat the Nifty after we sold | Mean excess | Median excess |
|---|---:|---:|---:|---:|
| 10 sessions | 10 | 3 | +0.5 | −1.7 |
| 30 sessions | 7 | **6** | **+7.3** | **+4.7** |
| 60 sessions | 5 | 2 | +1.6 | −5.1 |

Exits look right after two weeks and wrong after six: the sold stocks kept falling briefly, then
recovered against the market. That is the pattern of selling near a short-term low.

**Example.** PAYTM was sold on 7 Aug at +7.6% by `thesis_break`. Over the next 30 sessions it
rose 25.6% while the Nifty fell 4.7%: 30.3 points left on the table.

Switches did not add value at 30 sessions: in 4 of 4 graded switches, the stock bought did a
little worse than the stock sold (−0.0 to −2.1 points).

### Were the stocks themselves good?

| Group | Horizon | Beat the Nifty | Median excess |
|---|---|---:|---:|
| Held stocks (daily HOLD rows, overlapping) | 30 sessions | 90 of 232 (39%) | −2.1 |
| Held stocks | 60 sessions | 9 of 27 (33%) | −9.5 |
| **Shelf ideas, from the day shelved** | 30 sessions | **13 of 21 (62%)** | **+2.9** (mean +4.6) |

The stocks we held, mostly the seeded sector list, lagged the market. The discovery funnel's
ideas beat it. This is small-sample evidence, but it points the same way as the plan: put money
into researched ideas (SA-049), and supply more of them (PR-004).

The two current holdings are doing better than the market:

- FEDERALBNK is −7.2% since purchase, against −8.3% for the Nifty.
- WELCORP is +3.4%, against −6.4%.

### Three defects the baseline exposed (code, confirmed against the data)

1. **Position size is measured against the money in stocks, not the whole portfolio.**
   - The advisor computes a holding's weight against the holdings' total cost
     (`core/portfolio/advisor.py`, `build_signals`). The autopilot's ADD cap uses the holdings'
     market value (`_portfolio_market_value`). Neither counts cash.
   - FEDERALBNK is about 13.4% of equity, but the advisor sees 72.9%. ADD can never fire while it
     holds two stocks, and `SECTOR_CONCENTRATION_HIGH` was noted 18 times since 20 Sep on a
     portfolio that is 81% cash.
   - It is also a position check under a sector name.
   - Routed to **SA-050** (one sizing rule, now against total equity).
2. **A SWITCH buys at any price.**
   - WELCORP went onto the shelf on 15 Aug at ₹1,873, inside its entry band of
     ₹1,817–₹1,911. The switch bought it on 1 Sep at ₹2,553.60, after a 36% run, 34% above the
     band.
   - It has worked so far, but the rule the idea stated was ignored.
   - Routed to **SA-050**: every autopilot buy checks the band; above it, the buy is skipped
     with the reason until a fresh deep dive resets the band.
3. **The shelf is thin and partly invalid.**
   - Of 9 active ideas, 7 were shelved before the data gate existed, 1 abstained, and only
     AUROPHARMA is verified actionable.
   - LIQUID1 is the Kotak Nifty 1D Rate Liquid ETF, a cash fund, not a company.
   - 5 of the 9 are tagged "generic", so a per-sector cap on that label would mean nothing.
   - On 9 Oct, AUROPHARMA was in its band and REDINGTON 0.3% above it. Five ideas were 6–12%
     below their band but above invalidation.
   - So SA-049 would find about 6 stock candidates in record mode, and 1 under the strict gate:
     far short of 12.
   - Routed to **PR-004**: exclude funds and ETFs, cap by real industry, re-dive the pre-gate
     ideas.

### The brief

- Over 20 briefs from 10 Sep to 9 Oct, 32 of the 57 overnight items after the first day
  repeated the previous day's (56%). Three RBI and NRI-limit stories recur all month.
- The macro feed held 128 HIGH items over 14 days, about 9 a day, so the repetition is a
  selection problem, not a lack of news. That confirms PR-003.
- None of the 20 briefs carried an advisor flag, an earnings line or any news about Federal Bank
  or Welspun Corp. That is PR-008's gap.

### What changes in the plan

- **SA-050** grows to 3 points: weights against total equity, and the entry band on every buy.
- **PR-004** excludes funds and ETFs, caps by real industry, and re-dives the 7 pre-gate ideas.
- **PR-009** grades disagreements at both 10 and 30 sessions, and switches only if the evidence
  rule is not worse at both. One horizon alone would flatter one rule or the other.
- **PR-002's** "sold too early" red flag reads the 30-session grade, with 10 sessions beside it.
- **SA-049** carries the owner's decisions of 12 Oct: add ₹2 L of paper capital through a new
  dated action, and aim for 12 holdings (10 to 15).
- **PR-011** becomes P1 and moves up to follow PR-006 ("I need more data").
