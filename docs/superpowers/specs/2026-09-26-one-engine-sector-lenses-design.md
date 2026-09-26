# One engine with sector lenses — analysis and learning design

Status: **adopted as the plan** on 2026-09-26 (the owner: "go ahead"). Nothing here is implemented
yet. Author: Claude + Revan. Date: 2026-09-26.

This design does two things. It collects the learning-containment logic agreed on 2026-09-25/26
(SA-039, SA-043, SA-022) in one place, and it replaces the per-sector "graphs" with one analysis
engine. Current-code claims were checked at `0b3ebb9`, whose code is identical to `4c4728a`.
Production figures are dated observations from read-only logs, cited where used. Where this
document says **planned**, the behaviour does not exist yet.

---

## 0. Summary for the owner

**The graphs go.** Every stock is analysed by one engine. Sector knowledge becomes data (a *lens*),
not code.

| Step | What it does | Who does it |
|---|---|---|
| **Lens** | Says, per industry, who the real peers are, which benchmark to compare with, which KPIs and news matter, and which macro drivers move the stock | Configuration (YAML), no code per sector |
| **Facts** | Scores five universal factors (Value, Quality, Growth, Momentum and Risk) as percentiles against real peers and the stock's own history | Code; same inputs always give the same score |
| **Reader** | Reads news, results commentary, filings and policy through the lens, and returns dated, sourced events | One LLM call, text only |
| **Decide** | Turns the events into a sixth factor (Catalyst), combines the six factors, and maps the result to the existing verdict bands. Missing data lowers confidence and can stop a verdict. | Code |
| **Explain** | Writes the report from the factor table and events; it cannot change the verdict | LLM |

In one line: **code computes the facts, the LLM reads what only language can reveal, code decides,
and the LLM explains.** Learning then tunes six shared weights using every stock's outcomes,
instead of six to nine weights per stock from about 20 outcomes each.

Nothing switches on trust. The new engine runs in **shadow** beside today's analyst, and it replaces
it only after it proves **at least as good** on the same decisions (§6). Learned weights must
prove **better** before they are used (§1.5).

---

## 1. Learning containment and the exit rule (decided 2026-09-25/26)

These points are the reference for every learning story.

### 1.1 `observe` and `adapt`

| | `adapt` (production today) | `observe` (SA-039, accepted; activation is the owner's call) |
|---|---|---|
| Weights used for decisions | Each stock's learned weights | The configured default table |
| Nightly review | Saves new weights (v41 → v42 → v43 …) | Never writes the weight file; records what the adapter would have done |
| Lessons | Nudge agent scores | Recorded, but move no score |
| Switching back | — | Exact: the stored weights were never touched |

### 1.2 The defaults are not zero; the learned zeros are untrusted

| Graph | Chart agent | Default |
|---|---|---:|
| Generic (pharma, metals, fmcg, …) | `technical` | 0.12 |
| Renewable | `technical` | 0.10 |
| Automobile | `pattern_analysis` | 0.11 |
| Banking | `pattern_analysis` | 0.15 |
| IT | `pattern_analysis` | 0.10 |

On 2026-09-24 the chart weight was 0.0 for 9 of 18 logged tickers
([baseline](../../planning/PI-2026-09/evidence/SA-039-baseline-2026-09-24.md)). The adapter
produced those zeros while grading against the target the audit found wrong (F02). The baseline
shows what the adapter did, not that zero is wrong. It cannot be trusted either way, which is why
decisions go back to the defaults.

### 1.3 Activation timing

Forecast rows already issued keep their verdicts and closes; the review re-weights only their
confidence. The first fully contained cycle therefore starts at a monthly forecast
(`rl_monthly_forecast`, the 1st at 09:00 IST). Activating before 2026-10-01 09:00 IST makes October
the first clean cohort.

### 1.4 Why `observe` alone cannot answer "is learning ready?"

In today's code, `observe` re-proposes **one step from the frozen stored file** every night: v41 → v42,
and the next night v41 → v42 again. Nothing accumulates, so there is no learner to evaluate.
**SA-043 adds a shadow learner** that learns every night beside the live decisions but never
decides anything. Under this design it learns the **six pooled factor weights** of §4.5, starting
from the defaults, not the stored pre-fix weights.

### 1.5 Scoring only disagreements, and the four gates (SA-022)

The default policy and the learned policy score the **same agent or factor scores**, so they differ
only in weighting. When their verdicts agree, neither can be right where the other is wrong. Only
**disagreements** carry information.

> Example (six factors, BUY at composite ≥ 0.55). Every factor scores 0.5 except Momentum at 0.78,
> so the composite is 0.5 + 0.28 × w_momentum. With the default weight 1/6 the composite is 0.547,
> which is NEUTRAL. With a learned weight of 0.25 it is 0.570, a BUY. If the price then beats
> SA-012's target threshold, the learner wins that disagreement.

Learning may return only when **all four** predeclared gates pass:

| Gate | Rule |
|---|---|
| Enough evidence | At least 100 **effective** disagreements (SA-020 collapses overlapping horizons on one ticker), over at least 3 months and at least 3 lenses |
| Better | The learner is right on at least 60% of them (about two standard errors above a coin flip at n = 100) |
| Consistent | It wins in at least 2 of the last 3 months, and dropping its best lens does not flip the result |
| Sane weights | No factor stays at its bound, or below half its default, for 4 weeks; weights stay inside SA-015's bounds |

The rules around the gates:

- **Peeking guard:** look once a month on a fixed date; a pass must hold at **two consecutive**
  monthly looks.
- **Rarely different:** if the policies seldom disagree, learning barely matters, so stay in `observe`.
- **Promotion:** only by owner decision, at a month start. `adapt` resumes from the **learner's**
  weights, never the stored pre-fix weights, which are archived.
- **Reverse tally:** in the first full month after promotion, fewer than 45% right on at least 30
  effective disagreements returns learning to `observe`.

Learning is held to **superiority** (it must beat the defaults), because it adds risk and brings no
other benefit. The engine switch in §6 needs only **non-inferiority**, because it brings other
benefits.

---

## 2. What exists today (verified at `0b3ebb9`)

| Fact | Evidence |
|---|---|
| All five graphs already run one pipeline: a shared data bundle, then **one** reasoning-model call that scores every dimension | `unified_analyst.sectors: "automobile,banking_bfsi,it_sector,renewable_energy,generic"` in `config.yaml`; `base_orchestrator._run_agents` |
| The per-sector agent graphs (LangGraph worker pool) run only if that call fails | `_run_agents` → `_run_via_graph` on empty output with `fallback_legacy: true`. LangGraph is imported only by `base_orchestrator.py` and `pipeline/graphs/nodes.py`. |
| About **3,800 lines** exist only for that fallback | Sector `agents/` 1,307, `shared/agents` 430, `pipeline/graphs` 228, non-unified sector prompts 1,813. How often production falls back is recorded in `fallback_events` but was **not measured** here. |
| Five scoring schemes: **37 dimension slots under 24 names** for about six real questions | `DIMENSIONS`: automobile 9, banking 6, IT 8, renewable 6, generic 8. The chart signal alone is `pattern_analysis` or `technical`. Five default weight tables, five unified prompts (888 lines). |
| The LLM re-scores numbers the code already computed | `_fetch_technicals` renders locally computed RSI, MACD, Bollinger bands, 52-week position and support/resistance as text; `_fetch_peers_valuation` computes peer P/E. The prompt then asks for a 0–1 score from that text. Score reproducibility was **not measured**. |
| **Generic-graph stocks are valued against car makers** | `_sector_peer_tickers("generic", "SUNPHARMA")` → MARUTI, TATAMOTORS, M&M, HEROMOTOCO, BAJAJ-AUTO (the same for TATASTEEL). Elsewhere, peers are the first 5 names of a hand-typed list. |
| Every stock's technicals quote the automobile index | "Nifty Auto Correlation … Beta" in `get_technical_context`; `^CNXAUTO` failed 18× on 2026-09-23 (SA-010) |
| Missing data looks neutral | The prompts say: "no supporting data → score it 0.5 (neutral)" |
| Sector membership is typed by hand | `TICKER_SECTOR` in `registry.py`. NSE's own `industry` field is already read by `core/discovery/deep_dive.py` and `surveillance.py`. |
| Learning is per ticker, per scheme | One `WeightMemory` file per ticker with 6–9 weights, from about 20 graded rows a month |
| The verdict is already decided by code | `rl.hard_bind_verdict_enabled: true`: the category comes from the composite's score band; the aggregator's LLM writes the narrative |

Inputs the factors can use **today**: yfinance P/E, P/B, market cap and dividend yield; quarterly
revenue, EBITDA and margin, and revenue QoQ/YoY; institutional and promoter holding; 10 years of
daily prices; peer P/E; NSE bulk deals, FII/DII and MF herding; surveillance flags. **Not fetched
today:** RoE/RoCE, debt, cash flow and pledge data. Quality starts thin (§4.2).

---

## 3. Principles

1. **Reproducible:** the same inputs as of the same time give the same factor scores.
2. **Comparable:** every stock gets the same six factors on the same 0–1 scale, so any two stocks
   can be ranked.
3. **Learnable:** few parameters, pooled across stocks.
4. **Honest:** missing data is missing, lowers confidence, and can stop a verdict. It is never 0.5.
5. **Issue-time safe:** every input carries its as-of date, feeding SA-013/SA-014.
6. **Cheap to extend:** a new industry is a lens file, not a package.
7. **LLM where language matters:** reading and explaining. Not arithmetic, and not the decision.

---

## 4. Design

### 4.1 Lenses: sector knowledge as data

One small YAML file per industry group. The shape below is illustrative; SA-026 fixes exact values.

```yaml
id: banking_bfsi
display: Banking & financial services
store_key: banking_bfsi            # frozen for existing stores (SA-009): no directory moves
nse_industries: [...]              # NSE industry labels this lens covers
benchmark: ^NSEBANK                # SA-010: momentum and beta use this, never the auto index
peers: {rule: same_industry_nearest_market_cap, count: 5, minimum: 3}
kpis: [NIM, GNPA, NNPA, credit growth, CASA, provisions]   # what the reader looks for
news_terms: "quarterly results NPA NIM deposits"
policy_query: "India banking RBI policy credit growth {month} {year}"
macro_drivers: [repo_rate, 10y_gsec]
```

- **Resolution:** a symbol's lens comes from NSE's `industry` field. Existing tickers keep their
  current `store_key`, so stores never move silently. An unmatched industry uses a **default lens**
  with the market benchmark, industry peers when they exist, and generic KPIs.
- **Initial lenses:** the four current native sectors, lenses for industries that managed tickers
  actually hold (for example metals and pharma), and the default. Others are added when a managed
  ticker needs them.
- **What moves into lenses:** the per-sector bundle settings (`_SECTOR_BUNDLE_CFG`), peer lists,
  benchmarks and default weight tables. The weight tables become one universal table (§4.4).

### 4.2 Facts: five computed factors

Each factor is a 0–1 score where higher is more bullish (for Risk, higher is safer). Each is a
percentile against the lens peers and, where the table says so, against the stock's own history.

| Factor | The question | Inputs available today | Method (SA-045 sets the details) | Known gap |
|---|---|---|---|---|
| **Value** | Cheap against peers and its own past? | P/E, P/B, peer P/E | 50% peer percentile, 50% own 5-year percentile, both inverted | EV/EBITDA and historical multiples need an earnings history |
| **Quality** | Is the business sound? | EBITDA margin level and stability | Peer percentile | RoE/RoCE, leverage and cash conversion are not fetched. The factor is **partial** and carries low confidence until added. |
| **Growth** | Is it growing? | Revenue YoY/QoQ, EBITDA trend | Peer percentile | Profit growth |
| **Momentum** | Is the market confirming? | 10-year prices, 52-week position, RSI/MACD, bulk deals, FII/DII | 6- and 12-month return **relative to the lens benchmark** (peer percentile), plus trend against the 200-day average | Needs SA-010's benchmark |
| **Risk** | What could hurt? | Price volatility and drawdown, surveillance flags, promoter holding | Inverse percentile of volatility and drawdown. A surveillance flag caps the score. | Pledge data |

- **Minimum peers:** fewer than 3 usable peers means the own-history percentile only. With neither,
  the factor is **missing**.
- **As-of:** each factor records the oldest input date it used. Inputs older than the lens's
  staleness limit make the factor missing.

### 4.3 Reader: text into dated events

One LLM call reads the text sections (company news, sector and policy news, macro context, policy
deep dive and dossier) with the lens's KPIs and macro drivers as its brief. It returns events:

```json
{"what": "Commissioned 500 MW solar capacity", "kpi": "capacity",
 "direction": "positive", "materiality": "high", "horizon": "months",
 "source": "company_news", "source_date": "2026-09-20"}
```

- **Grounding:** an event without a `source` section and a `source_date` present in the bundle is
  dropped. This keeps the existing rule against using training knowledge.
- **Catalyst** (the sixth factor) is **computed by code** from the events. For example: a recency
  weighted sum (half-life 14 days, matching the prompts' freshness rule) of direction × materiality,
  squashed to 0–1. No events means Catalyst 0.5 with **zero coverage**, which lowers confidence
  rather than posing as an opinion.
- The reader runs on the bulk-tier model. During the shadow period it is an extra call, which
  SA-025 measures (§8).

### 4.4 Decide and explain

- **Composite:** Σ wᶠ·sᶠ over the factors present, divided by Σ wᶠ over the same factors.
- **Default weights:** **equal, 1/6 each**. No evidence favours any factor yet; favouring one is
  exactly what the learner has to earn.
- **Coverage:** the share of weight with real, fresh data. **Below 4 of 6 factors, no directional
  verdict**; the report says "insufficient data" (SA-003's gate). Confidence is coverage × freshness.
- **Verdict:** the existing score bands (`score_thresholds`: BUY from 0.55, and so on). They are
  unchanged.
- **Explanation:** the LLM receives the factor table, events and verdict. It writes the report
  and **cannot change the verdict**. Numbers it quotes must match the table, and a check rejects
  output that invents one.

### 4.5 Learning on the engine: six pooled weights

- **One weight table for all stocks** (six numbers), learned by SA-043's shadow learner with
  SA-015's bounded, idempotent update, and judged by SA-022's gates (§1.5).
- **Why pooled:** about 20 tickers × about 21 sessions gives roughly 420 graded rows a month for 6
  parameters, about 70 per weight. Per-ticker learning has about 20 rows for 6–9 weights, about
  2–3 per weight. That imbalance is how weights collapsed to 0. The rows are correlated, so SA-020's
  effective counts apply, but the ratio stands.
- **Per-lens tables** only after pooled learning has been promoted, and only if a per-lens
  comparison passes the same gates.
- **Timing:** the learner works on the engine's factor scores, which exist in shadow from SA-045.
  So it does not wait for the engine switch. Its `evidence_start` is the later of SA-015 and
  SA-045 going live.

### 4.6 What happens to existing structures

| Structure | After the switch |
|---|---|
| `rl.learning_mode` | Unchanged meaning: `observe` uses the equal default factor table; `adapt` uses the promoted pooled table |
| Per-ticker `WeightMemory` files | History only, kept for forensics |
| Envelope `predicted_agent_scores`, review re-scoring, Step 7b | Keyed by the six factor names. RL code is key-agnostic; SA-047 verifies that. |
| Lessons with `prioritise_agents` naming old dimensions | Inert (no factor matches). Lesson emphasis is off in `observe` anyway. SA-023 decides how lessons attach to factors. |
| Data fetchers, bundle, data-health records, dossier, daily review loop, verdict bands, portfolio advisor | Kept. The advisor still receives a verdict and confidence. |
| `TICKER_SECTOR`, sector packages, LangGraph pool, five unified prompts | Retired by SA-027 after the switch |

---

## 5. Worked example (illustrative numbers)

**SUNPHARMA today:** the generic graph with 8 dimensions. Its valuation compares P/E with MARUTI,
TATAMOTORS, M&M, HEROMOTOCO and BAJAJ-AUTO, and its technicals quote the Nifty Auto correlation.
The LLM turns the RSI text into a technical score, and missing sections become 0.5.

**SUNPHARMA under this design:**

| Factor | Score | Why |
|---|---:|---|
| Value | 0.30 | P/E at the 70th percentile of pharma peers (CIPLA, DRREDDY, LUPIN, …) and the 65th of its own 5 years |
| Quality | 0.62 (partial) | EBITDA margin above the peer median and stable; RoE not yet fetched |
| Growth | 0.58 | Revenue YoY at the 60th peer percentile |
| Momentum | 0.72 | 6-month return beats the pharma index; above the 200-day average |
| Risk | 0.66 | Volatility below the peer median; no surveillance flag |
| Catalyst | 0.68 | "USFDA clearance for the Halol plant" (positive, high, 9 days old) |

The composite is (0.30 + 0.62 + 0.58 + 0.72 + 0.66 + 0.68) / 6 = **0.593, a BUY**. Coverage is 6
of 6, with Quality marked partial. The report quotes these rows, and the same inputs tomorrow give
the same numbers.

---

## 6. Migration: shadow first, switch on proof, delete last

| Phase | Stories | What happens | Decision changes? |
|---|---|---|---|
| 0 | **SA-044** | Stop valuing stocks against another sector's peers (the car-maker bug) | Yes, a bug fix |
| 1 | **SA-026**, then **SA-045** and **SA-046** | Lenses, factors and the reader are computed and recorded **beside** every decision | No |
| 2 | **SA-043** | The shadow learner learns the six pooled weights on the shadow factors | No |
| 3 | **SA-047** | Paired comparison against today's analyst; the owner switches at a month start | Only on a pass |
| 4 | **SA-027** | Delete the sector packages, LangGraph pool and five prompts, after one clean month post-switch | No |
| Later | **SA-022** | Learned factor weights promoted if §1.5's gates pass | Only on a pass |

**The switch gate (SA-047, non-inferiority)** uses the same scoring method as §1.5: paired
issue-time decisions, disagreements only, effective counts and SA-012's target.

- At least 100 effective disagreements over at least 2 months and at least 3 lenses.
- The engine is right on **at least 50%** of them.
- No lens with at least 20 disagreements falls below **40%**, which guards against one lens getting
  much worse.
- Two consecutive monthly looks.

Parity is enough here, because the engine also fixes peers, is reproducible, costs less to run and
extend, and removes about 3,800 lines of fallback plus four packages. **Rollback** is a flag back
to today's analyst, kept until SA-027.

---

## 7. Non-goals

- No LangGraph or multi-agent framework. The pipeline is linear, and parallel fetches are plain
  concurrency.
- No per-sector code packages.
- No machine-learning model training now: about 20 stocks and an unfixed target cannot support it.
- No new structure driven by the UI. The UI shows lens display names.
- No price targets from the LLM.
- No change to the portfolio advisor's contract.

## 8. Risks and how the design contains them

| Risk | Containment |
|---|---|
| Thin inputs (Quality) | The factor is marked partial with lower confidence. SA-045 adds RoE/leverage from yfinance statements or records the gap. |
| yfinance gaps and stale data | As-of dates and staleness limits make a factor missing; coverage below 4/6 stops a verdict |
| Too few peers in a lens | Own-history percentile only, otherwise missing; never another sector's peers |
| Extra LLM cost during shadow | The reader runs on the bulk tier over text only; SA-025 measures actual calls; the shadow period is bounded by SA-047 |
| Engine worse in one lens | The per-lens 40% guard, a month-start switch and a rollback flag |
| Sector nuance lost | Lens KPIs and macro drivers brief the reader, which still reads sector-specific evidence |
| A learner overfitting | Six pooled parameters, SA-015 bounds, the §1.5 gates and the reverse tally |

## 9. Mapping to the board

| Story | Change |
|---|---|
| **SA-044** (new, Sprint 2, 2 points) | Compare valuations only with same-industry peers |
| **SA-026** (amended: P1, Sprint 6 → 3) | Consolidate sector definitions into sector lenses (§4.1) |
| **SA-045** (new, Sprint 4, 5 points) | Compute the five universal factors deterministically (§4.2) |
| **SA-046** (new, Sprint 4, 3 points) | Read text into dated events and a Catalyst factor (§4.3) |
| **SA-047** (new, Sprint 5, 5 points) | Decide and explain with the factor engine; shadow it against today's analyst and switch when not worse (§4.4, §6) |
| **SA-043** (amended, Sprint 3 → 4) | The shadow learner learns six pooled factor weights; it now also depends on SA-045 |
| **SA-022** (amended) | Gates on factors and lenses; now also depends on SA-047 |
| **SA-027** (amended) | Retires the sector packages, LangGraph pool and five prompts after SA-047's switch |
| **SA-010**, **SA-009**, **SA-003** (unchanged) | They supply the lens benchmark, the frozen store keys and the coverage gate |

## 10. Decisions and open questions

**Adopted 2026-09-26:**

- **D1:** one engine with sector lenses; no graphs.
- **D2:** six universal factors.
- **D3:** code computes and decides; the LLM reads and explains.
- **D4:** equal default weights.
- **D5:** pooled learning.
- **D6:** the engine switch needs non-inferiority; learning needs superiority.
- **D7:** fix the peer bug first.

**Open, owned by the story named:**

- **O1:** the exact NSE-industry → lens mapping, and whether BFSI splits into banks and NBFCs (SA-026).
- **O2:** the Catalyst formula and half-life (SA-046).
- **O3:** how the forecast envelope's price path uses the composite after the switch (SA-047).
- **O4:** how lessons attach to factors (SA-023).
