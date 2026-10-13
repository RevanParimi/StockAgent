# Agentic Design Reference

**Edition:** 2026-10-10 · **Code inspected:** `e85da94`, the code production runs

**Scope:** every component that calls a language model, what it decides and
what static code decides around it, with the data each one reads.

The [technical design](TECHNICAL_DESIGN.md) (the KT) traces the research path
in [section 4](TECHNICAL_DESIGN.md#4-research-input-to-recommendation); this
document is the per-component reference behind it. The learning agents are
specified in [RL_DESIGN](RL_DESIGN.md) and the chat loop in
[CHAT_ARCHITECTURE](CHAT_ARCHITECTURE.md). Measured production state lives
only in [KT section 1](TECHNICAL_DESIGN.md#production-state-at-this-edition).
Work planned in PI-2026-09 is labelled **Planned** with its story.

---

## 1. Inventory

```text
Research (on demand, monthly forecast, daily-review re-runs, discovery deep dives)
├── Ticker resolution         [STATIC for tracked tickers; LLM bulk for free text]   section 4
├── Sector routing            [STATIC] registry: 4 native graphs + generic             section 5
├── Sector data bundle        [STATIC] 10 typed sections, one fetch pass               section 6
├── Unified analyst           [LLM reasoning] one call scores every dimension         section 7
│   └── legacy per-dimension pool  [LLM bulk] fallback on total failure only         section 11
├── Signal aggregator         [STATIC composite + LLM reasoning narrative]             section 9
└── Decision gate             [STATIC] actionable / degraded / abstain                 section 10

Learning (daily review and monthly forecast)                                           RL_DESIGN
├── FeedbackAgent             [LLM reasoning] miss type, blame, lessons
├── WeightAdapter             [STATIC] weights or observe-mode proposals
├── ThesisReviewer            [LLM reasoning] conditional, after significant misses
├── PriceInterpolator         [LLM bulk] forecast profile; static fallback
├── PromptEnhancer            [STATIC templates; LLM bulk fallback]
├── Control lane              [LLM reasoning or configured model] baseline duel
└── Re-forecast, sticky regime, pre-open check   [STATIC + LLM fast for the pre-open rating]

Company knowledge                                                                      RL_DESIGN §23, §26
├── DossierCurator, distillation   [LLM bulk] daily and weekly
├── EventIngestor                  [LLM bulk] weekly NSE events
└── QuestionResearcher             [LLM bulk] weekly open questions

Narration and feeds
├── Macro news reviewer       [LLM bulk] severity and tags for the macro feed          section 12
├── Portfolio narrator        [LLM bulk] explains a verdict already decided            section 12
├── Brief and weekly headline [LLM bulk] one line each, with a fallback               section 12
└── IPO extract and narrate   [LLM bulk] dark P3 path, never shown to users            section 12

Chat (on demand, /ui/chat/stream)                                                      CHAT_ARCHITECTURE
└── Agentic tool loop         [LLM fast, reasoning on failure] + static pre-router and sanitizer
```

The rule across all of them: **code decides, the model reads and explains.**
Scores bind to verdicts through fixed bands, trades follow fixed rules, and
every model output passes a parser and bounds before anything stores it.

## 2. Model tiers

`llm:` in [config.yaml](../config.yaml); each tier has an environment
override (`LLM_MODEL_FAST`, `LLM_MODEL_REASONING`, `LLM_MODEL_BULK`), so
production can differ. All calls go through OpenRouter.

| Tier | Repository model | Used by |
|---|---|---|
| Fast | `qwen/qwen3.6-flash` | Chat tool loop; pre-open shock rating |
| Reasoning | `z-ai/glm-5.2` | Unified analyst; aggregator narrative; FeedbackAgent; ThesisReviewer; control lane (unless `rl.control_lane_model` is set); chat retry after a rate limit or server error |
| Bulk | `deepseek/deepseek-v4-flash` | Ticker resolution; legacy per-dimension agents; forecast profile; prompt-enhancer fallback; dossier curator and distillation; event ingestion; research loop; macro reviewer; portfolio narrator; brief and weekly headlines; IPO extraction and narration |

Shared defaults: temperature 0.2 (`llm.temperature`), 2,048 output tokens
(`llm.max_tokens`) and a 60-second timeout. Components that set their own
values say so below. Each call is logged with its tokens and an estimated
cost from `llm.cost_rates`.

## 3. The research pipeline

`BaseSectorOrchestrator.analyse` and `analyse_async`
([base_orchestrator.py](../src/backend/shared/pipeline/base_orchestrator.py))
run the same steps for every graph:

1. **Resolve** the input to a ticker, company name and exchange (section 4).
2. **Weights.** Explicitly injected weights win: the forecast and the review
   pass their decision weights. Otherwise the ticker's stored learned weights
   (version 1 or later) are used in `adapt` mode; in `observe` mode, or with
   none stored, the graph's defaults (section 8).
3. **NSE prefetch.** One NSE session fetches the ticker's announcements,
   board meetings and corporate actions into `query.nse_data`, shared
   read-only by everything after it. TATAMOTORS is skipped by a symbol
   override, because the announcements endpoint returns nothing for it.
4. **Score.** The unified analyst scores every dimension from one data bundle
   (sections 6 and 7). On a total failure with
   `unified_analyst.fallback_legacy` on, the legacy pool runs instead and the
   fallback is counted (section 11).
5. **Aggregate** into a composite, a bound verdict and a narrative
   (section 9).
6. **Gate** the report (section 10) before anything logs or returns its
   verdict.
7. **Record** the run summary, token cost, provider calls, the score history
   row and the data-health row.

**Example (call count):** a scheduled analysis of a managed ticker makes two
LLM calls, the analyst and the aggregator, plus at most three news searches
and one Tavily page. A free-text chat request adds one resolution call, or
two when the first answer cannot be verified.

## 4. Ticker resolution

A ticker resolves to itself, with no LLM or web-search call, when it is in
its sector's built-in `TICKERS`, in the managed list (any sector, enabled or
not) or in the instrument registry:

- the managed list and the registry are read on every resolution, so a ticker
  the owner adds is known at once. Nothing writes the list on this path;
- the company name comes from the curated or learned name, else yfinance for
  the registry's symbol, else the ticker; never from the LLM;
- a retired or unresolved ticker such as TATAMOTORS resolves to itself, and
  the identity gate decides whether it may act;
- an unreadable registry quarantines every ticker but names none, so free text
  is not mistaken for a ticker.

Free text ("tata elxsi") goes to one bulk-tier call (temperature 0, JSON).
When that answer is incomplete, or yfinance has no price for it, a news
search for the name is added to the prompt and the call is repeated. A
weekly discovery candidate that no list holds also goes this way.

**Why.** Asking a model which company a tracked ticker is lets it answer
wrongly: the KT's [ticker resolution](TECHNICAL_DESIGN.md#ticker-resolution)
section records a monthly forecast that analysed Tata Motors for TATAELXSI.

## 5. Sector routing

[registry.py](../src/backend/sectors/registry.py) is the single map, used by
the API, the scheduler and the learning loop alike.

- `SectorRegistry.resolve(ticker)` reads a map of 202 tickers, then
  name fragments for free text. An input it cannot place resolves to
  `generic` (`sectors.generic_fallback_enabled`, default on), never to
  automobile.
- Four sectors have native graphs: `automobile`, `banking_bfsi`, `it_sector`
  and `renewable_energy`. Eighteen more sector keys are defined (pharma,
  FMCG, metals, oil and gas, capital goods, power, chemicals, defence,
  infrastructure, insurance, logistics, media, real estate, retail, agrochem,
  hospitality, tech, telecom), all disabled. Each of them, and any other
  well-formed sector key, is analysed by the **generic** graph.
- The prediction store keeps the real sector name
  (`data/predictions/pharma/SUNPHARMA/`); only the analysis graph is generic.

The managed list, not the registry, decides which tickers are scheduled. Each
native sector's built-in `TICKERS` list (29 symbols across the four) serves
ticker resolution, the banking, IT and renewable peer lists, and the pre-open
check (RL_DESIGN §27.3); it does not schedule anything.

## 6. The sector data bundle

[bundle_builder.py](../services/data/context/bundle_builder.py) fetches
everything the analyst reads in one pass. Every section producer returns a
typed result ([fetch_result.py](../services/data/context/fetch_result.py)):
its text, a status, its source, the as-of date of its newest datum and a
reason. A failing producer degrades its own section and never raises.

| Section | Source | Notes |
|---|---|---|
| `company_news` | One news search (Serper) | Query terms per sector: results and guidance; NPA, NIM and deposits for banks; deal wins and attrition for IT; PPAs and commissioning for renewables |
| `sector_policy_news` | One news search | A sector query for demand, policy and competition |
| `macro_context` | yfinance INR/USD and crude, the factor regime, plus one news search | A missing core indicator makes the section unavailable. A hit on the in-process macro cache would skip the search and read `cache_hit`, but nothing writes that cache, so every run searches |
| `policy_deep_dive` | One Tavily page, cached by month | Policy circulars for automobile and renewables; RBI impact for banks; earnings-call commentary for IT |
| `fundamentals` | yfinance quarterly statements, plus NSE dates as context | Bank-format statements (below) |
| `technicals` | yfinance price history and indicators | Correlation and beta against the sector's benchmark (below) |
| `commodities` | yfinance commodity prices | Automobile only; `n/a` elsewhere |
| `flows_sentiment` | NSE bulk deals and FII/DII flows; AMFI sector-ETF momentum | `empty` when none of the three answers |
| `peers_valuation` | yfinance valuation for up to 5 peers | Peers from the sector's `TICKERS`; the automobile and generic graphs use the automobile peer list |
| `dossier` | The ticker's dossier digest (1,500 characters) | `n/a` until a dossier exists (RL_DESIGN §23.4) |

Each section is capped at 2,500 characters and the rendered bundle at
18,000 (`unified_analyst.section_max_chars`, `.bundle_max_chars`). A run
makes at most three news searches and one Tavily page.

### 6.1 Typed section statuses

| Status | Meaning |
|---|---|
| `ok`, `cache_hit` | Verified data, fresh |
| `stale` | Older than the freshness bound: a newest price bar over 7 days old, or a newest reported quarter over 200 days old |
| `fallback` | A core figure was replaced (search snippets, substituted zeros), or the newest listed quarter has no figure |
| `empty` | The source answered with nothing |
| `n/a` | Deliberately not fetched |
| `failed:<Type>` | The producer raised |
| `unverified` | Plain text with no typed result |

The producer decides the status from its structured data, never from its
sentence: "Technical data unavailable for TATAMOTORS" is not evidence of
data. Every unified run writes one data-health row with these statuses; the
KT's [data health](TECHNICAL_DESIGN.md#data-health) section gives the row's
contract and a worked example.

### 6.2 Bank-format statements

A bank's quarterly statement has interest income and net interest income, and
no operating-income, EBIT or gross-profit row. The
[fundamentals fetcher](../services/data/fetchers/fundamentals.py) lets the
statement's shape decide how it is read, never the ticker or its sector:

- both interest rows and no operating row make a **bank-format** statement.
  Net interest income takes the operating line's place in the prompt, the
  prompt says operating margin is not reported (no 0.0 figure), and the
  section's reason names the format;
- revenue is still required, and the 200-day bound still applies;
- a statement with EBIT beside net interest income, such as PAYTM's, stays
  standard. A non-bank statement without an operating row stays `fallback`.

**Why.** Substituting zeros made every bank `fallback`, showed a 0.0% EBITDA
margin and made the gate abstain on every bank analysis. The KT's
[bank income statements](TECHNICAL_DESIGN.md#bank-income-statements)
section has the measured effect and a worked example.

### 6.3 Sector benchmarks

The technicals section measures the stock's correlation and beta against its
sector's index: automobile `^CNXAUTO`, banking/BFSI `^NSEBANK`, IT `^CNXIT`,
renewable energy `^CNXENERGY` (`settings.SECTOR_BENCHMARKS`). Any other
sector, or none, is measured against the Nifty 50 (`^NSEI`), never against
another sector's index. Fewer than 30 paired returns, missing data, a flat
series or a failed download leave both values unmeasured, and the prompt says
"unavailable" and why. The section's status stays the stock's own, and its
provenance names the benchmark. **Example:** a bank reads "Nifty Bank
Correlation: … | Beta: …"; an automobile stock reads "unavailable (benchmark
^CNXAUTO returned no price data)" while Yahoo serves no data for that index
(KT [sector benchmarks](TECHNICAL_DESIGN.md#sector-benchmarks)).

## 7. Unified analyst

[unified_analyst.py](../src/backend/shared/pipeline/unified_analyst.py) makes
**one reasoning-tier call** per analysis (temperature 0.2, JSON output, up to
6,000 tokens, `unified_analyst.max_tokens`) that scores every dimension of the
sector's graph from the rendered bundle. Each graph's prompt module
(`prompts/unified.py`) defines its dimensions, sub-scores and scoring anchors.

- Each dimension comes back as the graph's own `AgentOutput` subclass, the
  same shape the legacy agents produce, so the aggregator, the learning loop,
  the UI and chat read either path alike.
- A truncated response is salvaged: complete dimensions are kept.
- A missing or unparseable dimension gets a neutral 0.5 with an `error`, which
  the aggregator excludes and the data-health row counts as missing.
- Total failure returns nothing and never raises. The health row still
  records the hollow attempt; with the fallback on, the legacy pool then
  scores the run, and that report carries no health row and no bundle
  provenance, so its gate abstains (section 10).

`unified_analyst.sectors` lists the graphs on this path; all five are on it.

## 8. Dimensions and default weights

Default weights come from each graph's weight table through
[sector_router.py](../core/intelligence/rl/workflows/sector_router.py); each
table sums to 1.0. In `observe` mode every decision uses these tables
(RL_DESIGN §7).

| Graph | Dimensions and default weights |
|---|---|
| Automobile (9) | fundamentals 0.18 · sales_demand 0.15 · risk_macro 0.13 · valuation_catalyst 0.12 · pattern_analysis 0.11 · raw_materials 0.09 · policy_regulatory 0.09 · competitive_intel 0.09 · sentiment 0.04 |
| Banking/BFSI (6) | fundamentals 0.25 · risk 0.20 · macro_policy 0.20 · institutional 0.15 · pattern_analysis 0.15 · universe_setup 0.05 |
| IT (8) | fundamentals 0.25 · global_macro 0.20 · risk_macro 0.15 · peer_benchmark 0.15 · pattern_analysis 0.10 · sentiment 0.08 · transcript_nlp 0.04 · insider_smart_money 0.03 |
| Renewable energy (6) | fundamentals 0.25 · business 0.25 · valuation 0.15 · sentiment_policy 0.15 · technical 0.10 · risk 0.10 |
| Generic (8) | fundamentals 0.18 · business 0.14 · valuation 0.14 · technical 0.12 · macro 0.12 · risk 0.12 · management 0.09 · earnings 0.09 |

That is 37 dimension slots under 24 distinct names. Each dimension returns an
overall score in [0, 1], five sub-scores, a summary, bull and bear cases, a
peer comparison, what changed, and a data confidence. The automobile graph's
`valuation_catalyst` also returns a price target, a fair value, the discount
and its reason, recovery catalysts and a timeline, which the aggregator
copies onto the report.

Several dimensions are proxies for data the system does not fetch: dealer
inventory, Vahan registrations, FADA and SIAM figures, social-media
sentiment, RBI and MNRE structured data, DISCOM payments and call
transcripts reach the model only as news snippets, if at all.

## 9. Signal aggregator

[signal_aggregator.py](../src/backend/shared/pipeline/signal_aggregator.py):

1. **Composite (static).** `Σ score × weight / Σ weight` over the dimensions
   without an `error`; errored outputs are excluded and the surviving weights
   renormalised. With nothing left, the composite is a neutral 0.5.
2. **Conflicts (static).** Every pair of scored dimensions 0.30 or more apart
   is flagged.
3. **Narrative (LLM).** One reasoning-tier call receives the scores, weights,
   composite, conflicts and each dimension's bull and bear cases, and returns
   a verdict, a `final_score`, conviction drivers, top risks, an investment
   thesis and how it resolved the conflicts.
4. **Binding (static).** With `rl.hard_bind_verdict_enabled` on (the
   repository value), the verdict is the composite's band, whatever the model
   said. The model's verdict is logged beside the composite in
   `data/rl/verdict_shadow.jsonl`. `final_score` stays the model's own and
   sets the forecast's base confidence.

| Verdict | Composite band (`score_thresholds`) |
|---|---|
| STRONG BUY | 0.75 – 1.00 |
| BUY | 0.55 – 0.75 |
| NEUTRAL | 0.40 – 0.55 |
| SELL | 0.20 – 0.40 |
| STRONG SELL | 0.00 – 0.20 |

Band edges resolve upward: 0.75 is STRONG BUY.

**Example:** scores 0.8 and 0.4 at weights 0.75 and 0.25 give
`0.8 × 0.75 + 0.4 × 0.25 = 0.70`, so the verdict is BUY. If the second
dimension errored, the composite is 0.8 alone, STRONG BUY, which is why the
decision gate counts scored dimensions (section 10).

## 10. Decision gate

Every report carries a typed `decision_gate`
([decision_gate.py](../src/backend/shared/pipeline/decision_gate.py)),
computed from the same section statuses and dimension counts as the health
row:

- **abstain** when an essential section (fundamentals, technicals,
  peers_valuation) is not `ok` or `cache_hit`; when fewer than half the
  graph's dimensions were scored (`decision_gate.min_dimensions_fraction`);
  when the run has no bundle (the legacy pool); or when the ticker's identity
  for today is unresolved, or its price history came from another symbol;
- **degraded** when it may act but an ordinary enrichment is missing;
- **actionable** when nothing is missing.

`decision_gate.mode` governs every consumer. In `record` (the repository
value) everything is computed and logged, and nothing changes. In `enforce`
an abstaining report's verdict reads `INSUFFICIENT DATA`, with the
aggregator's verdict kept as `withheld_verdict`, and the forecast, review and
portfolio consumers refuse what rests on it. An unrecognised value fails
closed to `enforce`. The KT's [decision gate](TECHNICAL_DESIGN.md#decision-gate)
and [instrument identity](TECHNICAL_DESIGN.md#instrument-identity) sections
give the examples; RL_DESIGN §6 and the [autopilot guide](AUTOPILOT_GUIDE.md)
section 4 describe what each consumer refuses.

## 11. Legacy per-dimension fallback

The pre-unified path remains as the fallback for a total analyst failure.

- **Agents.** Automobile, banking, IT and renewables keep one `BaseAgent`
  subclass per dimension, under `src/backend/sectors/<sector>/agents/`; the
  generic graph builds eight `UniversalAgent`s from its dimension prompts.
  Each agent makes its own bulk-tier call (default temperature and tokens,
  three attempts with back-off on rate limits and timeouts) and, on failure,
  returns a neutral 0.5 with an `error`.
- **Context.** Each agent fetches its own context through
  [ContextBuilder](../services/data/context/builder.py): a sector-specific
  builder method when one exists, else a generic one. Its static search
  queries can be extended by the cycle's prompt enhancements (RL_DESIGN §15),
  and the dossier digest is appended to its system prompt.
- **Graph.** A LangGraph fan-out runs the agents in parallel, with three
  non-blocking rails: an input check, a clamp on each output, and a conflict
  flag at aggregation.
- **Retrieval.** A vector-store retrieval path exists behind `RAG_ENABLED`,
  off by default, with no ingested corpus.

A fallback run makes one search per agent query instead of at most three per
run (the code estimates 6 to 8 times the news-search credits), and builds no
bundle, so its report has no section provenance and its gate abstains. Each
fallback is recorded in the fallback-event store, and `/scheduler/status`
reports the day's count. **Planned:**
measure actual provider calls (SA-025) and retire the fallback once the
replacement is measured (SA-027).

## 12. Narration and feed agents

| Component | What the model does | What code does |
|---|---|---|
| Macro news ([macro_news_fetcher.py](../services/background/macro_news_fetcher.py)) | Assigns each article a severity and impact tags, and says which topics are missing | Fetches news searches and NewsAPI headlines (07:30 policy and RBI; 09:00, 12:00 and 15:00 market), at most 2 rounds, and writes `data/macro_news/<date>_macro_feed.json`. On a model failure, articles are kept at low severity |
| Portfolio narrator ([narrator.py](../core/portfolio/narrator.py)) | Explains the advisor's verdict in research tone | Decides the verdict first; a template replaces a failed narration |
| Morning brief and weekly review ([brief.py](../core/delivery/brief.py), [weekly.py](../core/delivery/weekly.py)) | Writes one headline | Assembles every figure and section; a fallback headline on failure |
| IPO extraction and narration ([extract.py](../core/ipo/extract.py), [narrate.py](../core/ipo/narrate.py)) | Pulls Substance facts from browsed pages; writes a sourced research note | Computes the indices and verdict; rejects a note with a number not in the findings or advice vocabulary; never shows either to users (KT section 8) |

The macro feed file is read by the daily review when company news is
missing (RL_DESIGN §5) and by chat's `get_macro_news` tool. The research
bundle does not read it.

## 13. Chat agent

`POST /ui/chat/stream` streams one answer per question
([CHAT_ARCHITECTURE](CHAT_ARCHITECTURE.md)). A static pre-router detects buy,
sell and momentum questions about a screenable sector and runs the screen
and a news search first. The fast-tier model then calls tools for up to four
rounds, with the reasoning tier as the retry after a rate limit or server
error. The answer passes a static label scrubber, and the browser renders it
only through the sanitizing Markdown boundary. Thirteen tools read prices,
stored verdicts, the learning state, the dossier, news and the user's own
portfolio; one of them, `run_agent_analysis`, runs the full research pipeline
above.

## 14. Static versus LLM

| Component | Kind | File | Notes |
|---|---|---|---|
| Ticker resolution for tracked tickers | Static | `base_orchestrator.py` | Sector list, managed list, registry |
| Ticker resolution for free text | LLM bulk, temperature 0 | `base_orchestrator.py` | One retry with search results |
| Sector routing | Static | `sectors/registry.py` | Unknown → generic |
| Bundle sections and statuses | Static | `services/data/context/bundle_builder.py` | Typed results |
| Unified analyst | LLM reasoning, temperature 0.2 | `shared/pipeline/unified_analyst.py` | One call per analysis |
| Legacy dimension agents | LLM bulk | `sectors/*/agents/`, `shared/agents/universal.py` | Fallback only |
| Composite, conflicts, binding | Static | `shared/pipeline/signal_aggregator.py` | Bands from `score_thresholds` |
| Aggregator narrative | LLM reasoning | same | Verdict overridden by binding |
| Decision gate | Static | `shared/pipeline/decision_gate.py` | Section 10 |
| Instrument identity | Static | `shared/data/instruments.py`, `symbol_resolver.py` | Registry |
| Data-health row | Static | `services/data/stores/data_health.py` | One per unified run |
| FeedbackAgent | LLM reasoning, temperature 0.3 | `rl/agents/feedback_agent.py` | RL_DESIGN §5 |
| WeightAdapter, learning mode | Static | `rl/agents/weight_adapter.py`, `rl/learning_mode.py` | RL_DESIGN §7, §9 |
| ThesisReviewer | LLM reasoning, temperature 0.1 | `rl/agents/thesis_reviewer.py` | RL_DESIGN §16 |
| Forecast profile | LLM bulk, static fallback | `rl/algorithms/price_interpolator.py` | RL_DESIGN §4 |
| Monte Carlo paths | Static | same | RL_DESIGN §4 |
| Regime, sticky regime, streak, seasonal | Static | `regime/`, `rl/conviction/`, `seasonal/` | RL_DESIGN §12–14, §27.1 |
| Prompt enhancer | Static, LLM bulk fallback | `prompt_enhancer/enhancer.py` | RL_DESIGN §15 |
| Dossier curator, distillation, event ingestion, research loop | LLM bulk | `rl/agents/` | RL_DESIGN §23, §26 |
| Dossier merge, digest, tags, lesson emphasis | Static | `rl/agents/dossier_curator.py`, `schemas/dossier.py`, `rl/algorithms/lesson_emphasis.py` | RL_DESIGN §23 |
| Control lane | LLM reasoning or configured | `rl/agents/control_lane.py` | RL_DESIGN §25 |
| Pre-open shock rating | LLM fast | `rl/workflows/preopen_check.py` | RL_DESIGN §27.3 |
| Advisor and autopilot | Static | `core/portfolio/` | Autopilot guide |
| Narrator, brief and weekly headlines | LLM bulk, fallback text | `core/portfolio/narrator.py`, `core/delivery/` | Section 12 |
| Macro reviewer | LLM bulk | `services/background/macro_news_fetcher.py` | Section 12 |
| IPO indices and verdict | Static | `core/ipo/hype.py`, `substance.py`, `verdict.py` | Dark |
| IPO extraction and narration | LLM bulk | `core/ipo/extract.py`, `narrate.py` | Dark |
| Chat pre-router, scrubber, tool dispatch | Static | `services/api/routes/ui_data.py` | CHAT_ARCHITECTURE |
| Chat tool loop | LLM fast, reasoning retry | same | CHAT_ARCHITECTURE |

## 15. External data sources

| Source | Read by | Notes |
|---|---|---|
| yfinance (Yahoo) | Fundamentals, technicals, peers, macro and commodity prices, closes, chat prices | Free; the instrument registry names the symbol |
| NSE (NseIndiaApi, nsepython, bhavcopy) | Prefetch of announcements, board meetings and actions; FII/DII and bulk deals; official closes for the cross-check; EOD cache for discovery | Free |
| Serper (news and search) | Bundle news, macro feed, daily-review company news, ticker-resolution fallback, chat news, research loop | Paid credits; one key for all sectors |
| Tavily | Bundle policy page, event ingestion, research-loop fallback, IPO research | Monthly cache by query |
| NewsAPI | Macro feed headlines | Optional key |
| AMFI (via mfapi.in) | Sector-ETF momentum in `flows_sentiment` | Weekly cache |
| IIMA factor data | Factor regime in `macro_context` and the adapter's penalty scale | Ends March 2023: a static prior |
| OpenRouter | Every LLM call | Section 2 |

## 16. Limits and planned work

- **The analyst re-scores numbers the code has computed**, and a missing
  dimension still scores a neutral 0.5 inside its own output. The one-engine
  redesign computes factors in code, lets the model read only dated events,
  and gives no directional verdict with fewer than 4 of 6 factors.
  **Planned:** SA-026, SA-045, SA-046, SA-047; KT
  [section 11](TECHNICAL_DESIGN.md#11-planned-redesign).
- **Peers.** Generic-graph stocks are valued against automobile peers.
  **Planned:** same-industry peers (SA-044).
- **Benchmarks.** Automobile and renewable energy have no index with data.
  **Planned:** each sector lens names its benchmark (SA-026).
- **Cost accounting.** Bundle call counters are estimates, not complete
  provider or fallback accounting. **Planned:** SA-025, then SA-027.
- **Sector lists.** Ticker lists live in several places: each sector's
  `TICKERS`, the registry map, the managed list and the instrument registry.
  **Planned:** one sector definition (SA-026).
