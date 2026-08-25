# Three Loops PI — sector architecture, signal grading, and data health

Status: **proposed** · Author: Claude + Revan · Date: 2026-08-24
Companion doc: `docs/StockAgent-Three-Loops.pdf`.

---

## 1. Problem

A review of the three-loop pipeline (entry → STEP 1-7 → RL) found three
independent faults. All three were verified against **production** on
2026-08-24 via `railway ssh`; the numbers in this spec are prod numbers, not
local ones. Where a local measurement disagreed with prod, prod wins and the
local claim is recorded as withdrawn (§2.4).

**F1 — Two sector routers that disagree.** `SectorRegistry` (API path) and
`sector_router` (RL path) resolve the same ticker to different orchestrators.
The API path degrades every unknown or disabled sector to **automobile**; the
RL path degrades to **generic**. The same stock gets two different analyses
depending on which door the request came through.

**F2 — A dimension the system cannot grade.** `technical` scores a mean
accuracy of **0.459** across 136 prod snapshots — the worst of 21 dimensions,
barely better than a coin flip. The weight learner correctly defunds it to
~0. But the technical *data is healthy* (verified live), and the RL feedback
agent blames `technical`/`pattern_analysis` for **8 of 12** recorded misses.
The system has been blinded to technical breakdowns by its own
correctly-functioning learner, because the grading of that dimension is wrong.

**F3 — Degradation is invisible.** `bundle.has_real_data` is consumed in
exactly one place in the entire repo: a `logger.info` call. No per-section
health is recorded anywhere. A prod run on 2026-08-24 lost **3 of 6
dimensions**, shipped a BUY verdict, and logged `real_data=True` with
`error_count` visible only in a file that is deleted on every redeploy.

### Root cause, stated once

The pipeline has no **health contract**. Every layer degrades silently and
successfully: a missing sector degrades to automobile, a missing section
degrades to the string `"unavailable"`, a missing dimension degrades to a
neutral 0.5 that is then excluded and renormalised away. Each degradation is
individually defensible. Together they mean the system cannot distinguish a
good run from a hollow one — and neither can we.

---

## 2. Evidence base

Every task in this PI cites this section. A task chat should read §2 and its
own task card; it does not need the rest of the document.

### 2.0 Claim provenance — read this before citing anything below

This spec has already produced **nine** claims that did not survive
verification. They came from one mistake repeated: reasoning from something
plausible instead of measuring it. Listed as a standing warning, not history.

**Outright wrong:**

| Claim | Based on | Measurement |
|---|---|---|
| "Dimension scores collapsed to 0.65" | local `run_summaries.jsonl` | dev traffic — 547/548 runs were MARUTI smoke tests. Prod: 0/13 degenerate |
| "The weights are inert" | the collapse claim above | prod corr(accuracy, weight) = **+0.625**, positive 16/16 stores |
| "The legacy pool never fired in prod" | `fallback_events.jsonl` absent | fired 2026-07-11 (276 failures); evidence eaten by `except Exception: pass` |
| "Tracebacks are dropped by the handler" | the `"%(message)s"` formatter | **false** — `Formatter.format()` appends `exc_text`; 18 rows carry them |
| "`quoteType` is unused" | assumed alongside the other yfinance fields | one call site, `ui_data.py:2343` |

**Wrong scope or source:**

| Claim | Corrected to |
|---|---|
| "`has_real_data` consumed once repo-wide" | 7 sites. Only `SectorDataBundle`'s is inert — `base_agent`'s **gates** (skips the LLM). The unified redesign *removed* a gate |
| "41 of 41 generic tickers" | that was the LOCAL dir; prod is **73 of 73** |
| "`DLF` is the duplicate key" | **two** duplicates — `TORNTPOWER` (benign) and `DLF` (real conflict) |

**Unverified, presented as fact:**

| Claim | Status |
|---|---|
| "the fallback costs 6-8x Serper" | a docstring figure, and **unmeasurable** — `api_usage_events.jsonl` starts after the only event. Measured instead: mean **3.19 serper/run** over 382 runs |

**Rules for every task card in this document:**

1. **Label the source of every number** — `PROD`, `LOCAL`, `CODE`, or
   `INFERRED`. An unlabelled number is treated as unverified.
2. **A missing file is not evidence of absence.** Three of the four errors
   above came from concluding something never happened because its log was
   missing. Check a second, independent source before claiming a negative.
3. **Local `logs/` is dev traffic.** It is dominated by MARUTI and TESTSHOCK
   smoke runs. Never generalise from it to prod behaviour.
4. **Code comments are not measurements.** The "6-8x Serper" figure (§2.5)
   is an example: it lives in a docstring and remains unverified.
5. **If a claim cannot be measured, say so in the card** rather than
   softening the wording until it sounds measured.

### 2.1 Sector routing (F1)

Reproducible now, `python` with `src` on the path:

```
ticker        detect_sector     API orchestrator                RL orchestrator
SUNPHARMA     pharma            AutomobileAgentOrchestrator     GenericSectorOrchestrator
RELIANCE      oilgas            AutomobileAgentOrchestrator     GenericSectorOrchestrator
TATASTEEL     metals            AutomobileAgentOrchestrator     GenericSectorOrchestrator
ITC           fmcg              AutomobileAgentOrchestrator     GenericSectorOrchestrator
TITAN         automobile        AutomobileAgentOrchestrator     AutomobileAgentOrchestrator
SOMETHINGNEW  automobile        AutomobileAgentOrchestrator     AutomobileAgentOrchestrator
```

- `TITAN` (jewellery) and any unrecognised string resolve to `automobile`
  via the `resolve()` fallback at `registry.py:249`.
- **73 of 73** tickers the RL loop files under `predictions/generic/` in
  **prod** would run on the automobile graph via the API path. (An earlier
  draft said "41 of 41" — that was the *local* generic directory. Prod is the
  number to cite.)
- `TICKER_SECTOR` has 203 literal entries but 201 distinct keys (AST-verified,
  not regex). Two keys are duplicated: `TORNTPOWER` (both -> `renewable_energy`,
  **benign**) and **`DLF` (-> `infra`, then `realestate`; realestate silently
  wins)** — only `DLF` is a real conflict.

**Prod prediction store, 2026-08-24:**

```
automobile        37 tickers   23 weight_memories
banking_bfsi      15 tickers    4
bfsi               4 tickers    0     <- alias leak
generic           74 tickers    1
insurance          1 ticker     0
it                 4 tickers    0     <- alias leak
it_sector         13 tickers    4
metals             1 ticker     0
re                 4 tickers    0     <- alias leak
renewable_energy  11 tickers    4
```

`bfsi` / `it` / `re` are the `macro_cache_key` aliases from
`bundle_builder._SECTOR_BUNDLE_CFG` leaking into `PredictionStore` paths.

**13 tickers carry duplicate weight stores.** In every case the automobile
copy is a never-learned stub and the real-sector copy holds the learning:

```
ticker         sector             ver  hist  dims
ADANIGREEN     automobile           0     0     9
ADANIGREEN     renewable_energy    34    34     6
KPITTECH       automobile           0     0     9
KPITTECH       it_sector           34    34     8
YESBANK        automobile           0     0     9
YESBANK        banking_bfsi        34    34     6
   ... 13 tickers, identical shape (real side v29-v34)
```

Plus orphans filed under automobile that belong elsewhere: `FEDERALBNK`
(banking), `STARHEALTH` (insurance), `ACMESOLAR` (also in generic).

### 2.2 Weight learning (F2)

**The weight learner works. This corrects an earlier local-data claim.**
Correlation between a dimension's accuracy and its learned weight, computed
per prod store over the final accuracy snapshot:

```
mean r = +0.625    median r = +0.628    positive in 16/16 stores
20 learned stores, versions v29-v66, mean L1 drift from base = 0.465
```

Pooled per-dimension over **all** prod weight-history snapshots:

```
dimension              n    mean acc   % at 1.0   mean weight   zeroed
technical            136      0.459        17%        0.0047      3/4
pattern_analysis     653      0.741        50%        0.0332      3/16
global_macro         126      0.738        39%        0.1594      0/4
sales_demand         396      0.803        56%        0.1143      0/8
fundamentals         789      0.848        58%        0.2146      0/20
raw_materials        396      0.921        79%        0.1372      0/8
universe_setup       131      0.929        77%        0.0832      0/4
```

`technical` is a clear outlier — worst mean accuracy, lowest weight, zeroed
in 3 of 4 stores that carry it. `pattern_analysis` is second.

**But the technical data is healthy.** Fetched live from prod:

```
SUZLON     Current Price INR 46.71   RSI(14) 34.88   MACD -1.4011
ADANIGREEN Current Price INR 1320.0  RSI(14) 38.0    MACD -39.8059
WAAREEENER Current Price INR 2678.2  RSI(14) 42.2    MACD -34.7355
MARUTI     Current Price INR 13565.0 RSI(14) 42.76   MACD +10.1486
```

**And the outcomes say technical matters.** From the prod log window
2026-08-24 16:30-16:50 IST:

```
miss_type=direction_flip primary=pattern_analysis   x3
miss_type=direction_flip primary=technical          x2
miss_type=direction_flip primary=risk_macro         x2
miss_type=model_bias     primary=technical          x1
miss_type=data_stale     primary=technical          x1
miss_type=magnitude      primary=pattern_analysis   x1
```

The feedback agent auto-created lesson **L066**, slug
`stale_accuracy_gate_zero_weight_technical_ninth_bypass`, and daily-review
theses repeatedly cite "zero-weight technical agent" as the reason a forecast
missed. The system has diagnosed this itself and nobody was reading it.

Counter-example worth keeping: **PAYTM `pattern_analysis` has accuracy 0.857
but a weight below 0.01.** An accurate dimension pinned near zero — the
recovery from `17aa7ae` is working but too slow to matter.

Distribution of dead weights across the 20 learned prod stores:

```
A) a dimension at exactly 0.0                   9/20
B) a dimension in the 0 < w < 0.01 zone         4/20   (all pattern_analysis)
C) every dimension sharing ONE accuracy value   4/20   (nothing to learn from)
```

### 2.3 Observability (F3)

- **`SectorDataBundle.has_real_data` (the unified path's flag)** is consumed
  once, at `src/backend/shared/pipeline/base_orchestrator.py:509`, in a log
  line. Nothing branches on it.
  ⚠ **Scope this claim precisely.** `base_agent.py` has a *separate* local
  `has_real_data` from `ContextBuilder().build()`, and it **does** gate — at
  lines 100 and 144 it skips the LLM entirely and returns a neutral 0.5 with a
  WARNING. So the **legacy** path had a data gate and the **unified** path
  (2026-06-12) dropped it. B2/B5 are therefore *restoring a gate that used to
  exist*, not inventing one. Do not claim "consumed once repo-wide" — a grep
  for `has_real_data` returns 7 sites.
- `has_real_data` is `live_count >= 3` of 10 sections — it reports `True`
  when 7 sections are dead.
- `api_calls_made` is hardcoded `{"serper": 3, "tavily": 1}`. All 13 prod
  bundle log lines in the window are byte-identical regardless of cache hits
  or failures.
- Prod Serper usage for 2026-08: **1607 / 2500 calls** with a week left.
  Accurate accounting is not cosmetic.
- A prod run lost 3 of 6 dimensions and reported healthy:

```
SUZLON  verdict=BUY  errors=[sentiment_policy: missing_in_unified_response,
                             technical: missing_in_unified_response,
                             risk: missing_in_unified_response]
[SignalAggregator] SUZLON: 3/6 dimensions excluded from composite
[base_orchestrator] [renewable_energy] unified bundle: ... real_data=True
```

- `LOGS_DIR` has two different defaults for the same env var:
  `run_logger.py:31` -> `"logs"` (ephemeral container FS);
  `api_usage.py:49` -> `"data/logs"` (Railway volume). It is not set in prod.
  Result: prod `run_summaries.jsonl` holds **13 rows, all timestamped
  2026-08-24 (11:01-11:22 UTC)** `[PROD]`, while volume-backed
  `api_usage_events.jsonl` holds 198 KB going back to 2026-07-31. (That the
  13 rows begin at a redeploy boundary is an *inference* from the ephemeral
  path — the directly verified fact is that only one day survives.)
- `log_llm_call` mirrors to `telemetry.db`; **`log_run_summary` does not.**
- Static scan: **209 of 680** exception handlers neither log nor re-raise.
  Worst files: `services/api/routes/ui_data.py` (36),
  `core/delivery/brief.py` (13), `core/ops/watchdog/checks.py` (7).

### 2.4 Withdrawn claims

Recorded so no later session re-derives them:

- **WITHDRAWN — "dimension scores have collapsed to a single value."** Local
  `run_summaries.jsonl` showed 95.7% of clean runs emitting nine identical
  scores of exactly 0.65. That log is dev traffic: 547 of 548 non-test runs
  are MARUTI smoke tests. **Prod shows 0 of 13 runs degenerate**, with
  dimension ranges 0.15-0.60 and varied verdicts including a SELL. Do not
  build prompt-decorrelation work on the withdrawn claim.
- **WITHDRAWN — "the weights are inert."** Prod correlation is +0.625 across
  16/16 stores. The weights are among the healthiest parts of the system.

### 2.5 Ticker resolution and the legacy fallback

- `_verify_ticker` accepts `previousClose` alone. That field survives
  delisting forever, so a suspended stock passes verification. The check
  tests existence, never freshness.
- yfinance 1.3.0 does not raise for an unknown symbol; it returns a
  one-field dict. So a bad ticker, a 429, and a schema change are one bit.
- `regularMarketTime`, `marketState`, `exchange`, `currency`, `quoteType` are
  all present in `.info` `[PROD probe]`. `regularMarketTime` and `marketState`
  are **unused anywhere in the repo** `[CODE]`; `quoteType` has exactly one
  use, at `services/api/routes/ui_data.py:2343` — none of them are used by
  `_verify_ticker`.
- Symbol overrides verified working: `TATAMOTORS -> TMPV.NS`,
  `TVSMOTORS -> TVSMOTOR.NS`, `CANARABANK -> CANBK.NS`, `HEXAWARE -> HEXT.NS`.
- All five sectors are on the unified path
  (`unified_analyst.sectors: "automobile,banking_bfsi,it_sector,renewable_energy,generic"`).
  ⚠ **CORRECTED 2026-08-24 — an earlier draft of this spec claimed the legacy
  worker pool "has never fired in prod". That was WRONG.** It was inferred from
  `data/rl/fallback_events.jsonl` being absent. `telemetry.db.app_logs` proves
  otherwise:

```
graphs.nodes ERROR rows by day:  2026-07-11 -> 276   (and no other day)
  [generic/business]     agent failed: LLM call failed after 3 attempts
  [generic/fundamentals] agent failed: LLM call failed after 3 attempts
  [generic/technical]    agent failed: LLM call failed after 3 attempts
```

  The pool fired on **2026-07-11**, on `generic`, and then failed on every
  agent. The evidence file is missing because `record_fallback` is wrapped in
  a bare `except Exception: pass` at `base_orchestrator.py:556-558` — **the
  observability of the fallback was destroyed by one of the 209 silent
  handlers**, and the event went unnoticed for six weeks. This is the single
  best argument for WS-E.

### 2.6 Error capture — what already exists (WS-E)

**`SQLiteLogHandler(level=WARNING)` is already attached to the root logger**
at `services/api/server.py:75` and mirrors WARNING+ records into the
`app_logs` table of volume-backed `data/telemetry.db`. `[CODE]`
One deliberate exclusion: `SQLiteLogHandler.emit` drops records whose logger
is `log_store` itself (recursion guard), so that module's own warnings are
invisible to this pipeline — E2 must not treat its silence as health.

**PROD, 2026-08-24:**

```
app_logs: 4,254 rows   2026-07-02 -> 2026-08-24   (53 days, survives redeploys)
WARNING 3,006 · ERROR 1,248

top sources:
  core.intelligence.rl.agents.feedback_agent    WARNING  619
  yfinance                                      ERROR    445
  backend.shared.pipeline.base_agent            ERROR    276
  backend.shared.pipeline.graphs.nodes          ERROR    276
  core.intelligence.rl.stores.offmarket_fetcher WARNING  263

daily volume: ERROR 0-18/day, WARNING 6-42/day
```

That daily volume is what makes a digest practical — a normal day collapses to
single-digit distinct fingerprints, and 2026-07-11's 276 would have been
unmissable.

**No Railway auth is needed for the scheduled job.** `[CODE]` A repo-wide grep
for `RAILWAY_TOKEN|RAILWAY_API|railway login|railway logs|railway ssh` across
`services/ core/ src/ scripts/` returns **two hits, both in comments**. No
application code authenticates to Railway. `ops_watchdog` already runs daily
at 06:30 IST reading `Path("data")` and delivering push/email with zero
Railway credentials — WS-E is the same shape as a job already in production.

`railway login` remains required for **human, outside-in** access
(`railway ssh`, `railway logs`) — that is not the automation path, and
scripting it would be a defect: CLI sessions expire, so a laptop cron would
go blind silently.

**Three verified gaps** in the existing capture:

1. **Tracebacks are absent from 99.6% of rows — but not because of the
   handler.** `[PROD+CODE]` Only 18 of 4,254 rows contain a traceback.
   `Formatter.format()` *does* append `exc_text`; the gap is at the call
   sites: **24** uses of `exc_info=` against **194** sites that pass the
   exception as a `%s` string arg (`logger.error("...: %s", exc)`).
   The fix belongs at hot-path call sites, not in the handler.
2. **The handler is attached in exactly one place** — `server.py:75`.
   `[CODE]` Prod impact is limited: the APScheduler jobs run in-process with
   the API server and are covered. Uncovered are manually-invoked scripts
   (`railway ssh python scripts/...`). Real, but low-severity — do not
   overstate it.
3. **No run correlation.** `[CODE]` The schema is
   `app_logs(id, ts, level, logger, message)` — there is no `run_id` or
   `ticker` column, so an error cannot be tied back to the run that caused it.

---

## 3. Vision

> One analysis path, one sector definition, and a run that can say how
> healthy it was.

Three properties the system should have at the end of this PI, none of which
it has today:

1. **One route.** A ticker resolves to exactly one sector and one
   orchestrator, whichever entry point asked. Sector becomes data, not a
   Python package — adding pharma is a config entry.
2. **One health signal.** Every run emits a structured record of what it
   actually got: which sections were live, cached, empty, or failed; how many
   API calls it really made; how many dimensions survived. That record is
   durable, is read by the existing watchdog, and gates what the RL loop is
   allowed to learn from.
3. **Grading that can be trusted.** A dimension's accuracy measures whether
   that dimension was right. Today, for `technical`, it demonstrably does not.

---

## 4. Goals / non-goals

**Goals**
- Eliminate the router divergence and the automobile catch-all.
- Consolidate the 13 duplicate weight stores and the 3 alias directories
  without losing learning history.
- Make sector a profile (data) rather than a class hierarchy.
- Emit and persist a per-run data-health record; surface it in the watchdog.
- Diagnose why `technical` grades at 0.459 on healthy data, then fix it.
- Make run history survive a redeploy.

**Non-goals**
- Prompt decorrelation / forcing dimension independence. The claim that
  motivated it is withdrawn (§2.4).
- Any change to the verdict thresholds or the hard-bind behaviour.
- Adding new sectors. This PI makes adding them cheap; it does not do it.
- Replacing LangGraph with another orchestration framework.
- Re-tuning `AGENT_WEIGHTS` defaults. The learner works; leave it alone.

---

## 5. Decisions taken

| # | Decision | Rationale |
|---|---|---|
| D1 | Routing hotfix in Sprint 1; profile collapse is the PI goal | Stops the duplicate-store bleed immediately without blocking on the larger refactor |
| D2 | Unknown / disabled sector -> `generic`, never `automobile` | `generic` is sector-agnostic by construction; automobile injects wrong dimensions |
| D3 | `technical` grading gets a diagnosis-first workstream | The data is healthy and the learner is correct, so the fix is not yet known. Specifying a fix now would be a guess |
| D4 | Observability lands before behaviour changes | It is the instrument every other workstream is measured with, and it is additive |
| D5 | Every behaviour change ships behind a `cfg()` flag with a named rollback line | Matches the `atlas.enabled` and `rl.hard_bind_verdict_enabled` cutovers |
| D6 | Retire the legacy worker pool rather than redesign it | Never fired in prod; costs 6-8x Serper; all five sectors are unified |
| D7 | Weight-store merges are additive-then-cutover, never destructive | 34 versions of learning per store; a bad merge is unrecoverable |

---

## 6. Architecture

### 6.1 Sector profile (target state)

One orchestrator. Sector becomes a record loaded from
`config/sector_profiles.yaml`:

```yaml
it_sector:
  display: "IT & Technology"
  enabled: true
  dimensions: [fundamentals, global_macro, risk_macro, peer_benchmark,
               pattern_analysis, sentiment, transcript_nlp, insider_smart_money]
  prompts_module: backend.sectors.it_sector.prompts.unified
  peer_universe: backend.sectors.it_sector.config.settings:TICKERS
  bundle:
    company_news_terms: "results deal wins attrition guidance"
    sector_policy_news_query: "US tech spending H1B visa ... {month} {year}"
    policy_deep_dive_query: "{company_name} earnings call transcript ... {year}"
    has_commodities: false
    macro_cache_key: it_sector      # NOTE: no longer an alias — see A2
  aliases: [it]                     # read-only, for migrating old paths
```

`SectorProfile` is the single source consumed by: the router, the
`PredictionStore` path, `bundle_builder._bundle_cfg`, `unified_analyst`'s
class map, and `sector_router.get_sector_weights`. Each of those five call
sites currently keeps its own copy of part of this.

### 6.2 Data health record

New module `services/data/stores/data_health.py`. One row per run, appended
to `data/logs/data_health.jsonl` (volume-backed) and mirrored to
`telemetry.db`:

```jsonc
{
  "ts": "2026-08-24T11:01:01Z", "run_id": "186c7ad4",
  "ticker": "SUZLON", "sector": "renewable_energy",
  "sections": {
    "company_news": "ok", "sector_policy_news": "ok",
    "macro_context": "cache_hit", "policy_deep_dive": "ok",
    "fundamentals": "ok", "technicals": "ok", "commodities": "n/a",
    "flows_sentiment": "empty", "peers_valuation": "ok", "dossier": "ok"
  },
  "live": 7, "degraded": 0, "empty": 1, "not_applicable": 1,
  "dimensions_expected": 6, "dimensions_scored": 3,
  "dimensions_missing": ["sentiment_policy", "technical", "risk"],
  "api_calls": {"serper": 2, "tavily": 1, "nse_india": 1},
  "health": "degraded"
}
```

`empty` is a first-class outcome and is the state nothing catches today —
a fetcher that returns `""` without raising (`_fetch_flows_sentiment` does
this when all three of its inner calls fail, logging only at DEBUG).

`health` is derived: `ok` | `degraded` | `hollow`. **`hollow`** means the run
should not train the RL loop.

### 6.3 Watchdog integration

No new scheduler. `core/ops/watchdog/` already has a `@check(name)` registry
driven by `config/milestones.yaml`, running 06:30 IST with push/email and a
Sunday heartbeat. Two new checks register there:

- `data_health_degraded_rate` — invariant; alerts when the trailing-7-day
  `degraded`+`hollow` rate exceeds a configured threshold.
- `sector_route_integrity` — invariant; alerts when a ticker gains a second
  prediction directory, or when any alias directory reappears.

Per the standing rule, each registry entry lands in the **same commit** as
the check that reads it.

---

## 7. PI structure

Four sprints, four workstreams. Sprint length is nominal — the ordering and
dependencies are what matter.

```
            Sprint 1              Sprint 2              Sprint 3              Sprint 4
            stop the bleed        see it                collapse              cut over
WS-A  ---   A1 single router      A2 store migration    A3 profile schema     A4 profile cutover
WS-B  ---   B1 LOGS_DIR fix       B3 watchdog checks                          B5 hollow-run gate
            B2 data_health emit   B4 real API counts
WS-C  ---   C1 grading diagnostic C2 grading fix spec   C3 grading fix (dark) C4 recovery validation
WS-D  ---                         D1 TickerVerdict      D2 fallback retire    D3 except-handler gate
WS-E  ---   E1 capture gaps       E2 fingerprint+digest E3 watchdog surface   E4 error backlog
```

**Dependency edges that matter:**
`B2 -> B3`, `B2 -> B5`, `B2 -> C2`, `A1 -> A2`, `A2 -> A3`, `A3 -> A4`,
`C1 -> C2 -> C3 -> C4`, `B4 -> D2`, `E1 -> E2 -> E3 -> E4`.

**Sequencing constraints — these are not optional**

The dependency graph is acyclic and no task depends on a later sprint
(audited). But three Sprint-4 tasks each change what the RL loop observes, and
running them concurrently would destroy C4's ability to measure anything:

- **A4** changes the orchestrator and therefore the dimension outputs.
- **B5** changes *which runs* are allowed to train weights.
- **C4** measures whether the new grading metric ranks dimensions differently.

**Rule: C4's measurement window must not overlap with A4's cutover or B5's
enablement.** Land C4's comparison first (it reads the C3 shadow rows already
accumulated in Sprint 3), publish its verdict, and only then flip A4 and B5.
If schedule pressure makes that impossible, B5 goes last — it is the only one
of the three that is purely additive to skip behaviour and can slip a sprint
without blocking anything else.

A related, milder note: **A2 (Sprint 2) relocates prediction stores**, so any
baseline C1 captured in Sprint 1 is measured against pre-migration paths. A2
preserves every `weight_version > 0` store byte-identical, so the *values* are
unchanged — but C4 must confirm it is comparing the same stores, not assume it.

**Sprint goals**
- **S1 — Stop the bleed and switch the lights on.** No more duplicate stores
  created; every run emits health; run history survives a redeploy.
- **S2 — See it.** Health is alertable, API counts are real, the historical
  mess is migrated, and the grading diagnosis has an answer.
- **S3 — Collapse.** Sector becomes data; the grading fix ships dark.
- **S4 — Cut over.** Profile routing goes live, the legacy pool is deleted,
  and the grading fix is validated against recovered weights.

---

## 8. Task cards

Each card is self-contained. **To work a task in a fresh chat, paste the
"Chat opener" line.** The chat should read §2 (evidence) and its own card;
nothing else in this document is required.

Every card obeys: additive first, behaviour behind a `cfg()` flag, tests
before implementation (TDD), full suite green before commit, and
`config/milestones.yaml` updated in the same commit when the task creates a
date-bound obligation.

---

### A1 — Single router, `generic` fallback

- **Sprint** 1 · **Workstream** A · **Depends on** nothing
- **Chat opener:** `Work task A1 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.1. Two routers disagree on every disabled sector; unknown
  tickers land on automobile. This is what mints the duplicate stores.
- **Files:** `src/backend/sectors/registry.py`,
  `src/backend/sectors/__init__.py`,
  `core/intelligence/rl/workflows/sector_router.py`,
  `core/portfolio/promotion.py` (mirrors `NATIVE_SECTORS`),
  `core/discovery/deep_dive.py`
- **Approach:** Make `sector_router` delegate to `SectorRegistry` so there is
  one resolution function. Change both fallbacks (unknown ticker, disabled
  sector) to `generic`. Fix the `DLF` duplicate key. Add a unit test that
  asserts the two entry points return the same class for a table of tickers
  spanning enabled, disabled, unknown, and alias cases.
- **Flag:** `sectors.generic_fallback_enabled` (default `true` on merge;
  `false` restores automobile degradation).
- **Acceptance:**
  - For all of `SUNPHARMA RELIANCE TATASTEEL ITC LT BHARTIARTL DLF TITAN
    ZOMATO SOMETHINGNEW`, API and RL paths return the identical class.
  - No path returns `AutomobileAgentOrchestrator` for a ticker whose
    resolved sector is not `automobile`.
  - `TICKER_SECTOR` literal count == distinct key count (a test asserts it,
    so a future duplicate fails CI).
- **Verify:** the routing table script in §2.1 prints zero `DIVERGE` rows.
- **Rollback:** flip `sectors.generic_fallback_enabled` to `false`.
- **Memory on completion:** update `project_architecture.md` — sector routing
  is now single-source.

---

### B1 — `LOGS_DIR` unification and durable run history

- **Sprint** 1 · **Workstream** B · **Depends on** nothing
- **Chat opener:** `Work task B1 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.3. Prod `run_summaries.jsonl` holds 13 rows because
  `run_logger` defaults to ephemeral `logs/` while `api_usage` defaults to
  volume-backed `data/logs/`. `log_run_summary` has no SQLite mirror.
- **Files:** `services/data/stores/run_logger.py`,
  `services/data/stores/analysis_logger.py`,
  `services/data/stores/log_store.py`, `Dockerfile`
- **Approach:** One default, `data/logs`, for every `LOGS_DIR` consumer. Add a
  `run_summaries` table to `telemetry.db` and mirror `log_run_summary` into
  it the way `log_llm_call` already mirrors. Add a boot-time log line
  reporting row count, mirroring `api_usage.log_boot_state`.
- **Acceptance:**
  - Every `LOGS_DIR` default in the repo is `data/logs` (grep asserts it).
  - A run written, then `telemetry.db` queried, returns that run.
  - Boot log reports the surviving row count.
- **Verify:** `railway ssh` — confirm `/app/data/logs/run_summaries.jsonl`
  exists and grows; confirm the row count survives the next deploy.
- **Rollback:** revert; no data migration is performed by this task.
- **Note:** do **not** migrate the 13 existing ephemeral rows. They are
  today's only, and they will be gone before this ships.

---

### B2 — Emit the data-health record

- **Sprint** 1 · **Workstream** B · **Depends on** B1 (for the durable path)
- **Chat opener:** `Work task B2 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.3, §6.2. A run that lost 3 of 6 dimensions logged
  `real_data=True`. There is no record of what a run actually received.
- **Files:** new `services/data/stores/data_health.py`;
  `services/data/context/bundle_builder.py`;
  `src/backend/shared/pipeline/base_orchestrator.py`;
  `src/backend/shared/schemas/pipeline.py` (`FinalReport.data_health`)
- **Approach:** Have each `_fetch_*` wrapper in `build_sector_bundle` record
  an outcome — `ok` | `cache_hit` | `empty` | `n/a` | `failed:<Type>` —
  rather than only a string. Widen `SectorDataBundle` with
  `section_status: dict[str, str]`. `_run_unified` combines that with the
  dimension outcome from `UnifiedAnalyst` and writes one row. Purely
  additive: no existing behaviour changes, nothing branches on `health` yet.
- **Flag:** `observability.data_health_enabled` (default `true`; the record is
  write-only until B5, so enabling it changes no behaviour).
- **Acceptance:**
  - A row is written for every run, including failed runs.
  - `empty` is distinguished from `failed` and from `n/a`
    (`_fetch_flows_sentiment` returning `""` records `empty`, not `ok`).
  - The SUZLON case reproduces as `dimensions_scored: 3` of 6 with the three
    missing dimensions named.
  - `data_health` never raises — a unit test forces each writer to throw and
    asserts the run still completes.
- **Verify:** one prod run after deploy produces a row whose
  `dimensions_scored` matches the `SignalAggregator` exclusion warning.
- **Rollback:** `observability.data_health_enabled: false`.

---

### C1 — Technical grading diagnostic (read-only)

- **Sprint** 1 · **Workstream** C · **Depends on** nothing
- **Chat opener:** `Work task C1 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.2. `technical` grades 0.459 on healthy data and is zeroed in
  3 of 4 stores, while the feedback agent blames it for most misses and
  auto-wrote lesson L066 naming the accuracy gate itself.
- **Files:** read-only across `core/intelligence/rl/agents/weight_adapter.py`,
  `core/intelligence/rl/agents/feedback_agent.py`, whatever computes
  `hit_rate()` / `accuracy_snapshot`, and the prod weight histories.
  **Writes nothing but a report.**
- **Approach — answer these, with numbers:**
  1. What exactly does `accuracy_snapshot[dim]` measure, and over what
     horizon? Is it the same horizon `technical` predicts on?
  2. Why does the same update log `technical: hits=1/7` alongside
     `fundamentals: hits=7/7` — are both counting the same event class?
  3. Is `technical` graded on direction over a window where a technical
     signal has no directional claim (i.e. a horizon mismatch)?
  4. Reconcile the memory note that `hit_rate()` blends sparse calibration
     with these numbers — is `technical` sparse, mis-horizoned, or genuinely
     wrong?
  5. Quantify the cost: over the prod histories, how many misses were
     attributed to a dimension whose weight was already below 0.01?
- **Acceptance:** a written findings section appended to this spec as §12,
  naming the mechanism and proposing (not implementing) the fix. If the
  finding is "technical is genuinely uninformative", say so — that is a
  valid outcome and it retires C2-C4.
- **Verify:** N/A — read-only.
- **Rollback:** N/A.

---

### A2 — Prediction-store migration

- **Sprint** 2 · **Workstream** A · **Depends on** A1
- **Chat opener:** `Work task A2 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.1. 13 tickers with duplicate stores, 3 alias directories,
  74 generic tickers with 1 weight memory between them.
- **Files:** `core/intelligence/rl/stores/prediction_store.py`; new
  `scripts/migrate_prediction_stores.py`
- **Approach:** Dry-run-first migration script. For each duplicate pair,
  keep the store with `weight_version > 0` and archive the v0 stub under
  `_archived/`. Fold `bfsi`/`it`/`re` into their canonical sectors. **Never
  merge two stores that both have `weight_version > 0`** — none exist today
  (verified), so that case aborts loudly rather than guessing.
- **Flag:** none — this is a one-shot script, gated by `--apply`.
- **Acceptance:**
  - Dry run prints every planned move and is reviewed before `--apply`.
  - After apply: zero tickers with two weight memories; zero alias dirs;
    every `weight_version > 0` store preserved byte-identical.
  - `PredictionStore` gains a guard that refuses to write to an alias key.
- **Verify:** re-run the §2.1 prod inventory — 10 sector dirs become 5, the
  13 duplicates become 13 singles at their original versions.
- **Rollback:** archived stubs are restorable from `_archived/`; **take a
  volume backup before `--apply`** (`data_backup_nightly` covers this, but
  confirm the latest one succeeded first).
- **Gate:** this is the one task in the PI that touches irreversible data.
  Confirm the dry-run output with Revan before `--apply`.

---

### B3 — Watchdog checks for health and route integrity

- **Sprint** 2 · **Workstream** B · **Depends on** B2, A2
- **Chat opener:** `Work task B3 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §6.3. The health record is only useful if something reads it.
- **Files:** `core/ops/watchdog/checks.py`, `config/milestones.yaml`,
  `tests/unit/ops/`
- **Approach:** Two `@check` functions per §6.3. Thresholds via `cfg()`.
  Registry entries land in the same commit.
- **Acceptance:**
  - `data_health_degraded_rate` returns `satisfied` on clean data,
    `at_risk` above threshold, `unknown` when the file is absent.
  - `sector_route_integrity` fails if a second prediction dir appears for a
    ticker, or an alias dir reappears.
  - Both checks follow the existing `conftest.py` pattern so they do not
    assert the repo deploy state (see the 2026-08-22 watchdog regression).
- **Verify:** `run_check("data_health_degraded_rate")` on prod data.
- **Rollback:** remove the two registry entries; the checks become inert.

---

### B4 — Real API-call accounting

- **Sprint** 2 · **Workstream** B · **Depends on** B2
- **Chat opener:** `Work task B4 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.3. `api_calls_made` is hardcoded `{"serper": 3, "tavily": 1}`.
  Prod Serper is at 1607/2500 for August. Also `record_call("nse_india")` is
  skipped on partial success, so NSE is undercounted.
- **Files:** `services/data/context/bundle_builder.py`,
  `src/backend/shared/pipeline/base_orchestrator.py:322`,
  `services/data/stores/api_usage.py`
- **Approach:** Count actual calls per section; fix the NSE partial-success
  undercount. Feed the real numbers into the B2 record.
- **Acceptance:** a run with a macro cache hit reports `serper: 2`, not 3;
  a partial NSE prefetch records 1 nse_india call, not 0.
- **Verify:** compare a day of `data_health.jsonl` `api_calls` sums against
  the `api_usage.json` monthly delta — they should agree within the
  non-bundle call sites.
- **Rollback:** revert; accounting only.

---

### C2 — Grading fix specification

- **Sprint** 2 · **Workstream** C · **Depends on** C1, B2
- **Chat opener:** `Work task C2 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** C1 names the mechanism; this turns it into a reviewable design
  before any code touches the learner.
- **Approach:** Append §13 to this spec: the proposed change, its blast
  radius across the 20 learned stores, the expected recovery trajectory for
  `technical` and `pattern_analysis`, and the flag name. Must state what
  would falsify it.
- **Acceptance:** design reviewed and approved by Revan before C3 opens.
- **Verify:** N/A — this task writes a design section, it changes no code.
- **Rollback:** N/A — nothing ships.
- **Note:** if C1 concluded `technical` is genuinely uninformative, this task
  closes as `not needed` and C3/C4 are cancelled.

---

### D1 — `TickerVerdict` replaces the boolean

- **Sprint** 2 · **Workstream** D · **Depends on** B2
- **Chat opener:** `Work task D1 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.5. `_verify_ticker` returns one bit for four distinct
  conditions, and accepts `previousClose` alone so a delisted stock passes.
  A false negative silently costs a Serper call plus a second LLM call.
  **Measured cost (382 prod runs):** 41 runs (**10.7%**) exceed the 3-call
  baseline, totalling **75 excess Serper calls** — extrapolating, ~90/month,
  about **5.6%** of August's 1607 spend. **Measured cause** (`app_logs`,
  logger `yfinance`, n=445): 206x "Quote not found", **123x "Unauthorized /
  Invalid Crumb"**, 94x "possibly delisted", 8x "unable to access this
  feature". The 123 crumb failures are transient upstream errors that today
  are indistinguishable from a bad ticker.
- **Files:** `src/backend/shared/pipeline/base_orchestrator.py:353-473`
- **Approach:** Return an enum — `ok` | `stale` | `wrong_market` | `no_data`
  | `upstream`. Use `regularMarketTime` for staleness (N trading days, via
  `cfg()`), and `exchange`/`currency`/`quoteType` for market sanity. Only
  `no_data` triggers the Serper fallback; `upstream` retries then degrades.
  Every non-`ok` verdict writes to the B2 record. Cache `_yf_info` per run so
  `_company_name_for` and `_verify_ticker` share one round trip.
- **Flag:** `data_fetch.ticker_verdict_enabled` (dark first).
- **Acceptance:**
  - All of `MARUTI TATAMOTORS TVSMOTORS CANARABANK HEXAWARE KPITTECH SUZLON`
    return `ok` (they do today — this must not regress).
  - `NOTAREAL123` returns `no_data`.
  - A stubbed 429 returns `upstream` and does **not** trigger Serper.
  - A stubbed price older than the threshold returns `stale`.
- **Verify:** the §2.5 probe table, plus a day of health records showing
  zero unexplained `upstream` verdicts.
- **Rollback:** flip the flag; the boolean path is retained until S4.

---

### A3 — Sector profile schema

- **Sprint** 3 · **Workstream** A · **Depends on** A2
- **Chat opener:** `Work task A3 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §6.1. Five call sites each keep a partial copy of what a sector is.
- **Files:** new `config/sector_profiles.yaml`, new
  `src/backend/sectors/profile.py`; readers in `registry.py`,
  `bundle_builder.py`, `unified_analyst.py`, `sector_router.py`
- **Approach:** Define `SectorProfile`, load and validate at import the way
  `watchdog/registry.py` validates milestones — a malformed profile is a loud
  failure, never a silent default. Ship the five existing sectors as
  profiles. **Readers are switched one at a time**, each behind
  `sectors.profile_source_enabled`, each with a test asserting the profile
  and the legacy constant agree.
- **Flag:** `sectors.profile_source_enabled` (dark; each reader switches
  independently behind it).
- **Acceptance:** for all five sectors, profile-derived dimensions, prompts
  module, peer universe, bundle config and macro cache key are identical to
  today's hardcoded values. A test asserts equality so drift fails CI.
- **Verify:** full suite green; a dark prod run produces byte-identical
  bundles under both sources.
- **Rollback:** `sectors.profile_source_enabled: false`.

---

### C3 — Grading fix, dark

- **Sprint** 3 · **Workstream** C · **Depends on** C2 approved
- **Chat opener:** `Work task C3 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** implements the §13 design.
- **Approach:** Ship behind a flag, writing a **shadow** accuracy alongside
  the live one — the way `verdict_shadow` shadows the composite. No weight is
  updated from the new metric until C4 validates it.
- **Flag:** `rl.grading_shadow_enabled` (dark; shadow-write only).
- **Acceptance:** shadow accuracy recorded for every dimension for at least
  10 trading days without touching live weights.
- **Verify:** `[PROD]` after 10 trading days, assert every learned store's
  `weight_version` advanced **only** by the live metric — diff the version
  history against a pre-C3 snapshot and confirm zero shadow-driven writes.
- **Rollback:** flip `rl.grading_shadow_enabled` off; shadow rows are inert
  and are never read by the live path.

---

### D2 — Retire the legacy worker pool

- **Sprint** 3 · **Workstream** D · **Depends on** B4
- **Chat opener:** `Work task D2 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.5. Fired once (2026-07-11) and failed completely; all five
  sectors are unified.
  ⚠ **The "6-8x Serper" figure is UNVERIFIED** — it comes from a code comment
  in `fallback_events.py`, not a measurement, and it cannot be checked from
  prod: `api_usage_events.jsonl` starts **2026-07-31**, after the only
  fallback event. Do not cite it as fact. What *is* measured (382 runs,
  2026-07-31..2026-08-24): the unified path costs **mean 3.19 Serper/run,
  median 3, max 8**.
- **Files:** `src/backend/shared/pipeline/base_orchestrator.py:552-607`,
  `src/backend/shared/pipeline/graphs/`, the per-sector agent classes
- **Approach — in order, not all at once:**
  1. Add **one retry** of the unified call before any fallback. Most `{}`
     returns are transient; a retry is ~1/8 the cost.
  2. Budget-gate the fallback: read the live Serper counter (real after B4)
     and refuse to engage when the month is tight, degrading to a
     low-confidence verdict instead.
  3. Watch `fallback_events.jsonl` for one full sprint. **Only if it stays
     empty**, delete the pool, the graph modules, and the agent classes.
- **Acceptance:** step 3 is a separate commit, gated on the observed rate.
  If the file is non-empty, stop and file the failures as unified-path bugs.
- **Verify:** per stage — (1) `[PROD]` a forced unified failure retries once
  before falling back; (2) a simulated tight budget refuses the fallback and
  emits a low-confidence verdict; (3) `app_logs` shows **zero**
  `graphs.nodes` rows for a full sprint. ⚠ Use `app_logs`, **not**
  `fallback_events.jsonl` — that file's writer is behind a bare
  `except: pass` and is exactly what made this claim wrong the first time.
- **Rollback:** `unified_analyst.fallback_legacy` already exists; deletion is
  the only irreversible step and it is gated on evidence.

---

### A4 — Profile-driven routing cutover

- **Sprint** 4 · **Workstream** A · **Depends on** A3
- **Chat opener:** `Work task A4 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** completes the collapse — one orchestrator, sector as data.
- **Approach:** Generalise `GenericSectorOrchestrator` into
  `SectorOrchestrator(profile)`. The four native subclasses become thin
  profile lookups, then are deleted. Cutover is a single config flip, exactly
  like the `atlas.enabled` cutover.
- **Flag:** `sectors.profile_source_enabled` -> `true` (the same flag A3
  introduced; A4 is the flip, not a new switch).
- **Acceptance:**
  - One orchestrator class remains.
  - Adding a sector requires no Python change — a test adds a synthetic
    sector by profile alone and analyses a ticker through it.
  - No change in dimension names, prediction paths, or weights for the five
    existing sectors.
- **Verify:** dark run over one ticker per sector, diffing the full
  `FinalReport` against the pre-cutover run.
- **Rollback:** flip `sectors.profile_source_enabled` back to `false`.

---

### B5 — Hollow-run gate on the RL loop

- **Sprint** 4 · **Workstream** B · **Depends on** B2, B3
- **Chat opener:** `Work task B5 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §1 root cause. A run built on 3 live sections should not train
  weights as if it were built on 10.
- **Files:** the RL daily-review / weight-adapter entry points
- **Approach:** Skip weight updates for runs whose health record says
  `hollow`. Record the skip; do **not** silently drop it.
- **Flag:** `rl.hollow_run_gate_enabled`, dark first.
- **Acceptance:** a synthetic hollow run does not move any weight; the skip
  is visible in the health record and countable by the watchdog.
- **Verify:** `[PROD]` run one sprint with the flag OFF, recording what
  *would* have been skipped; only then enable. Confirm the observed skip rate
  matches the dry-run prediction.
- **Risk to state plainly:** this reduces training volume. If the skip rate is
  high, the fix is the data pipeline, not the gate.
- **Rollback:** flip `rl.hollow_run_gate_enabled` off.

---

### C4 — Weight recovery validation

- **Sprint** 4 · **Workstream** C · **Depends on** C3
- **Chat opener:** `Work task C4 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** closes the loop opened by C1.
- **Approach:** Compare shadow accuracy against live over the C3 window. If
  the shadow metric ranks dimensions differently for `technical` and
  `pattern_analysis`, cut over; otherwise the C1 hypothesis is falsified —
  say so and stop.
- **Acceptance:** a written verdict with numbers, and either a cutover or a
  documented refutation. **A refutation is a successful outcome.**
- **Verify:** recheck the §2.2 table post-cutover — does `technical` climb
  off 0.0047, and does the miss-attribution rate for `technical` fall?
- **Rollback:** the cutover is a flag flip (`rl.grading_shadow_enabled` ->
  live). Reverting restores the previous metric, but **weights updated under
  the new metric are not automatically undone** — snapshot every
  `*_agent_weight_memory.json` before the cutover so versions can be restored.

---

### D3 — Exception-handler CI gate

- **Sprint** 4 · **Workstream** D · **Depends on** nothing
- **Chat opener:** `Work task D3 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.3. 209 of 680 handlers neither log nor re-raise.
- **Approach:** Promote the AST scan to `scripts/` with an allowlist seeded
  at today's count, wired into `repo_sanity`. The gate is **ratchet-only**:
  it fails when the count rises. Then burn down the analysis hot path first —
  `base_orchestrator.py` (5), `bundle_builder.py`, `prediction_store.py`.
- **Acceptance:** the count cannot rise; hot-path handlers either log or
  record to the B2 health record.
- **Verify:** injecting a new bare `except: pass` fails `repo_sanity`;
  removing one lowers the ceiling.
- **Rollback:** remove the check from `repo_sanity`; the script stays as a
  manual tool.
- ⚠ **Ratchet friction:** A1-A4 and E1-E2 all add code. A ratchet that only
  ever falls will block a legitimate new handler. The allowlist therefore
  needs an explicit *add-with-justification* entry (handler + one-line reason),
  or this gate becomes something people disable.
- **Note:** do not mass-edit all 209. Many are legitimate (wrapping a
  `progress_callback`). The allowlist is the deliverable, not a purge.
- **First target, by evidence:** the `record_fallback` handler at
  `base_orchestrator.py:556-558` — it is the one silent except already proven
  to have destroyed real evidence (§2.5).

---

### E1 — Close the error-capture gaps

- **Sprint** 1 · **Workstream** E · **Depends on** nothing
- **Chat opener:** `Work task E1 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.6. Capture already works (4,254 prod rows over 53 days). Three
  verified gaps stop it being usable as a diagnosis surface.
- **Files:** `services/data/stores/log_store.py`, `services/api/server.py`,
  plus hot-path call sites in `base_orchestrator.py`, `bundle_builder.py`,
  `unified_analyst.py`, `prediction_store.py`
- **Approach:**
  1. Add `run_id` and `ticker` columns to `app_logs` (nullable; existing rows
     keep NULL — no migration of history). Populate from a `contextvars`
     run context set in `analyse()`/`analyse_async()`.
  2. Add `exc_info=True` at **hot-path** error sites only. **Do not touch all
     194** — pick the analysis path first and measure the traceback rate
     before and after.
  3. Extract handler attachment into one `configure_logging()` used by
     `server.py` and by standalone script entry points.
- **Flag:** none — additive schema + logging changes.
- **Acceptance:**
  - New rows carry `run_id`/`ticker` when logged inside a run; NULL otherwise.
  - Traceback-bearing rows rise measurably from the 18/4254 baseline for the
    hot-path loggers specifically (state the before/after number).
  - A script run via `railway ssh` produces `app_logs` rows.
  - **Existing 4,254 rows remain readable** — a test asserts the old schema
    still queries.
- **Verify:** `[PROD]` after deploy, query `app_logs` for a run_id from a
  known run and confirm its errors are linked.
- **Rollback:** revert; the added columns are nullable and harmless if unused.
- ⚠ **Do not claim tracebacks were "lost" or that the handler drops them.**
  §2.0 records that as a wrong claim. The handler is fine; the call sites are
  the gap.

---

### E2 — Fingerprint and digest

- **Sprint** 2 · **Workstream** E · **Depends on** E1
- **Chat opener:** `Work task E2 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §2.6. 4,254 raw rows are unreadable; ~10 errors/day collapse to a
  handful of distinct causes.
- **Files:** new `core/ops/error_digest.py`; new scheduler job in
  `services/scheduler/python/scheduler.py` (alongside the existing 21)
- **Approach:** Daily in-container job. Normalise each message into a
  **fingerprint** by stripping tickers, numbers, paths, and UUIDs — the same
  normalisation used to produce the yfinance shapes in §2.5. Classify each
  fingerprint against a registry on the volume:

```
NEW        never seen                    -> alert
REGRESSED  seen, quiet >= 7d, returned   -> alert
SPIKE      count > baseline + 3 sigma    -> alert
ONGOING    known, steady                 -> count only
RESOLVED   absent >= 7d                  -> close
```

- **Flag:** `observability.error_digest_enabled` (dark first).
- **Acceptance:**
  - Replaying the 53 days of existing `app_logs` produces a stable fingerprint
    set — **the yfinance 445 must collapse to the 4 shapes in §2.5**, and
    2026-07-11 must surface as a SPIKE. This is the regression test: it runs
    against real historical data, not fixtures.
  - The digest never raises and never blocks the scheduler.
  - Normalisation is deterministic — same input, same fingerprint.
- **Verify:** `[PROD]` run the digest over history; confirm the 2026-07-11
  legacy-pool event is flagged and that a normal day yields < 10 fingerprints.
- **Rollback:** flag off; the job becomes a no-op.

---

### E3 — Surface the digest through the watchdog

- **Sprint** 3 · **Workstream** E · **Depends on** E2
- **Chat opener:** `Work task E3 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** §6.3, §2.6. The alerting path already exists and is trusted; no new
  scheduler, no new delivery channel.
- **Files:** `core/ops/watchdog/checks.py`, `config/milestones.yaml`,
  `tests/unit/ops/`
- **Approach:** One `prod_error_digest` check that fires **only** on NEW,
  REGRESSED or SPIKE. Thresholds via `cfg()`. Registry entry in the same
  commit.
- **DECIDED (Revan, 2026-08-24): WARNING+ with per-logger thresholds.**
  ERROR-only (~10/day) would be tighter but would miss the entire F3 failure
  class — `bundle_builder` section degradations are logged at WARNING, which
  is precisely how they stayed invisible. The tuning cost is real and is
  absorbed here: seed each logger's threshold from its own trailing-30-day
  baseline in `app_logs` (53 days are available), not from a global constant.
  Loggers with a high steady WARNING rate — `feedback_agent` (619),
  `offmarket_fetcher` (263) — must not drown the digest: they alert on
  *deviation from their own baseline*, never on absolute count.
- **Acceptance:**
  - A quiet day produces no alert.
  - An injected NEW fingerprint produces exactly one alert.
  - Follows the `tests/unit/ops/conftest.py` pattern — must not assert the
    repo deploy state.
- **Verify:** `run_check("prod_error_digest")` against prod data.
- **Rollback:** remove the registry entry; the check goes inert.

---

### E4 — The error registry as a work backlog

- **Sprint** 4 · **Workstream** E · **Depends on** E3
- **Chat opener:** `Work task E4 from docs/superpowers/specs/2026-08-24-three-loops-pi-design.md`
- **Why:** this is the task that makes the system "grow with log data" rather
  than merely alert. Alerting answers *did something break*; the registry
  answers *what should we fix next*.
- **Files:** the E2 registry, plus `GET /ops/errors` in `services/api/routes/`
  and `scripts/prod_errors.py`
- **Approach:** Each fingerprint carries `first_seen`, `last_seen`, `count`,
  `trend`, `status` (`new` | `triaged` | `wontfix` | `fixed`), and an optional
  linked task id. Expose it via an endpoint authenticated with **the app's own
  auth** (the M0 layer, `AUTH_REQUIRED`) — **not** Railway credentials. A
  small local script fetches and renders it.
- **Acceptance:**
  - The endpoint requires auth and returns the ranked registry.
  - `scripts/prod_errors.py` prints a ranked digest with no Railway CLI
    involvement.
  - Marking a fingerprint `fixed` suppresses it until it REGRESSES.
- **Verify:** fetch from a local machine with only app credentials; confirm no
  `railway` binary is invoked.
- **Rollback:** the endpoint is read-only and additive; remove the route.
- **Security:** this repo is public and the endpoint exposes prod error text —
  it must be auth-gated, and the digest must not be committed to the repo.

---

## 9. Testing

- Every task is TDD: test first, watch it fail, then implement.
- The full suite must be green before each commit. Baseline is
  **2985P/12S/0F** as of 2026-08-25 (local `main`, post-A1); any delta must
  be explained in the commit message. ⚠ The figure here read **2945P** for
  the first day of this PI — that was measured 2026-08-22, before `7c410aa`
  and `17aa7ae` added two test files, so HEAD was already 2953P when A1
  started. **Re-measure HEAD before attributing a delta to your own change.**
- **Run the suite yourself.** Subagents background the 5-minute run, lose the
  child, and report success without committing.
- New tests must not assert the repo deploy state. Use the
  `tests/unit/ops/conftest.py` pattern established after the 2026-08-22
  watchdog regression.
- A1, A3 and A4 each need an equivalence test (old path == new path) before
  the flag flips, not after.

## 10. Operational rules

- **Never push to main 16:25-17:15 IST on trading days.**
- A2 is the only task touching irreversible data — volume backup confirmed
  and dry-run reviewed before `--apply`.
- Keep prod endpoint and cash specifics out of committed docs; this repo is
  public.
- Every flag introduced here gets a `config.yaml` entry with a comment naming
  its rollback line.
- **Never enable two RL-affecting flags in the same window.**
  `rl.hollow_run_gate_enabled`, `rl.grading_shadow_enabled` and
  `sectors.profile_source_enabled` each change what the learner sees; flipping
  two at once makes any regression unattributable. One flip, one observation
  window, one verdict.

## 11. Memory changes (part of the work, not a follow-up)

On completion of each workstream, update:

- `project_architecture.md` — sector routing is single-source; sector is data.
- **New** `project_three_loops_pi.md` — indexed in `MEMORY.md`, carrying the
  §2.4 withdrawn claims so no future session re-derives the collapse story.
- `project_weight_absorbing_state.md` — add the C1 finding; the 0.0 weights
  are the learner working correctly on a bad grade, not a learner bug.
- `project_operational_watchdog.md` — the two new checks.
- `project_test_strategy.md` — new baseline after each suite delta.

## 12. C1 findings

*(populated by task C1)*

## 13. C2 grading design

*(populated by task C2)*

## 14. Known limitations

- The prod log buffer holds ~960 lines, so §2.2's miss-attribution counts
  come from a ~20-minute window (n=12 misses). The weight-history numbers
  (n=126-789 per dimension) are the durable evidence; the log window is
  corroboration, not the basis.
- Prod `run_summaries.jsonl` had 13 rows at the time of writing, so no
  historical run-quality baseline exists. B1 creates one; until it has run
  for a sprint, degraded-rate thresholds in B3 are estimates.
- `technical` appears in only 4 prod stores (the renewable sector). The
  0.459 figure is well-sampled per store (136 snapshots) but narrow in
  ticker coverage. C1 must check whether the automobile/IT analogue
  (`pattern_analysis`, n=653, 16 stores) shows the same mechanism before
  generalising.
- This PI does not address the `generic` sector's learning gap (74 tickers,
  1 weight memory). That is a consequence of routing, and should be
  re-measured after A2 rather than fixed blind.
