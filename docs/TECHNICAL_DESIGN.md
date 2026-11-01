# StockAgent — Technical Design and Knowledge Transfer

**Edition:** 2026-11-01 · **Audience:** engineers and teammates learning the product

**Code inspected:** `30bf8fcec1fd14a6bfba5c7ed50d252cf5e3bc39`

**PDF:** [StockAgent-Three-Loops.pdf](StockAgent-Three-Loops.pdf), generated from this Markdown.

This document describes how StockAgent works at the revision above. It covers
the three product loops, the contracts between components, the records they
keep and the jobs that run them. Production state is dated and kept in one
place (section 1), apart from the description of the code. Work planned in
PI-2026-09 is collected in sections 11 and 12. Where another section mentions
it, the text is labelled **Planned**. `check_kt_docs.py` fails if a linked
source file or a documented job ID is absent at the inspected revision.

The separate [human testing guide](TEAM_TESTING_GUIDE.md) divides practical
testing duties among the team. It is not a human-approval workflow inside the
product.

## 1. Reading the evidence

| Label | Meaning in this document |
|---|---|
| Current code | Traced at the inspected revision. Flags, inputs and runtime data decide whether a path actually runs. |
| Locally checked | Tests run in the hermetic suite or an isolated copy (section 13). A passing test describes code behaviour; on its own it does not establish a financial contract. |
| Production observation | Dated, read-only evidence from the deployed service: logs, the RL monitor, the watchdog's mail, or the owner's checks. |
| Planned | Intended behaviour in PI-2026-09 (sections 11 and 12). Not implemented. |

The [September audit](audit/2026-09-10-repository-production-review.md) is the
baseline record of the label, timing, health, weight-bound and operational
defects that this design addresses. Adaptive state exists; improved
prediction performance has not been demonstrated. Writing this document
triggered no production job, backfill or notification.

### Production state at this edition

Production runs `c1d5b18` (FIX-021, code `e7e3165`), deployed at about 17:17
IST on 31 October 2026 (the deployment list showed it SUCCESS and `/health`
answered 200). The inspected code adds SA-048's trading costs and tax estimate
(sections 6 and 7). It is committed but not yet deployed, and counts as running
only once a read-only check of the deployment list and `/health` confirms that
deploy. The table gives the configuration that
differs from the repository and the state of each operational control.

| Area | State in production | Evidence |
|---|---|---|
| Learning mode | `observe` since 2026-09-26, set by the Railway variable `RL_LEARNING_MODE`; the repository default is `adapt`. Weight versions stay unchanged across reviews, and every review records its proposal. Every envelope since the 2026-10-01 monthly forecast was issued in `observe`. | Verified 2026-10-01 ([activation record](planning/PI-2026-09/evidence/SA-039-activation-2026-09-26.md)) |
| Decision gate | `record`, the repository default: computed and logged everywhere, nothing withheld. The 2026-10-01 decision kept `record`, because 25 of 78 analyses (32%) would have abstained, most for reasons since fixed. | [Enforce decision](planning/PI-2026-09/evidence/SA-003-enforce-decision-2026-10-01.md) |
| Instrument identity | Since 2026-10-01, TATAMOTORS is disabled in the managed list, with its history kept, and TMPV is managed as its own automobile ticker. The registry lists TATAMOTORS and HEXAWARE as unresolved. | Owner's dashboard change, 2026-10-01 |
| Prediction stores | The ownership quarantine was applied on 2026-10-01. It moved 16 stray `automobile/<TICKER>` copies, byte-identical, into `data/prediction_quarantine/20260930T184031Z-ce3556d023d3/`. Rollback remains available. | Apply record in [STATE.json](planning/PI-2026-09/STATE.json) |
| Ticker resolution and bank statements | Managed tickers resolve to themselves, and the four banks' fundamentals read `ok`. TATAELXSI's October envelope, built on a wrong resolution, was regenerated on 2026-10-05. | Verified 2026-10-02 from review logs |
| Sector benchmarks | Each sector's technicals are measured against its own index. Yahoo returns no data for `^CNXAUTO` or `^CNXENERGY`, so automobile and renewable-energy correlations read "unavailable". | Verified 2026-10-10 from the 7–9 Oct review logs |
| Listing-day closes | The nightly audit grades listing-day IPO rows: 4 graded and none skipped on 2026-10-01. | Verified 2026-10-01 |
| Chat brief scope | Chat's brief tool reads only the caller's portfolio. The owner gets the owner's brief; a member account with no holdings is told there is no brief yet and sees none of the owner's. | Verified 2026-10-11, the owner's check with a member account |
| Score history | Nothing wrote it from 21 Apr 2026 (`ce1eeb5`) to 15 Oct, while 1,082 analyses with a verdict were logged in `run_summaries`. On 2026-10-16 at 08:24 IST the owner ran the backfill: 1,082 rows, 83 stocks, runs 26 Aug to 15 Oct, each marked as copied and removable, with a backup next to `scores.db`. No live row existed then. Rows written by live analyses await the probe after the 16 Oct 16:30 review. | Owner's backfill run, 2026-10-16 (counts only); read-only probe, 2026-10-15 ([PR-001 review](planning/PI-2026-09/evidence/PR-001-review.md)) |
| Delivery | Outbound SMTP has worked since a plan upgrade on 2026-09-21. The outbox records transport acceptance; user receipt is not observable. Whether `RESEND_API_KEY` is set was not inspected. | Section 10 |
| Backups | The nightly archive and restore drill run. No off-site target is configured, because the owner deferred it to the end of the PI, so the watchdog sends a weekly reminder. | Watchdog mail, 2026-10-07 |
| Watchdog milestones | The milestones that lapsed in August and September were judged and retired on 2026-10-06. The next morning's run sent no LAPSED notice. | Watchdog mail, 2026-10-07 |
| CI | Three GitHub Actions jobs run on every push. The first run, on 2026-09-28, passed. | Section 13 |

The rest of the deployed behaviour is live: chat sanitizing, data-health rows,
review outcome counts, the delivery contract and dossier dates. Each still
awaits its recorded production observation, and
[STATE.json](planning/PI-2026-09/STATE.json) lists the pending checks.

### Vocabulary

| Term | Plain-English meaning |
|---|---|
| Ticker / instrument | A market symbol / the actual security it represents. A renamed or reorganized company is not automatically the same investment. |
| Sector / graph sector | The company's business sector / the analysis implementation selected for it. A pharma stock can use a generic graph while retaining pharma identity. |
| LLM / agent / dimension | Language model / component with an analysis task / one score such as fundamentals. Multiple dimension names do not establish independent evidence. |
| Composite / weight | Combined score / importance assigned to a dimension. |
| Envelope | Stored forecasts for future trading sessions, including prices, verdicts and uncertainty information. |
| Feedback / lesson / dossier | One review result / reusable knowledge / longer-lived company observations and questions. |
| Advice / transaction | A portfolio recommendation / a recorded virtual buy or sell. They are separate records. |
| Decision gate | The check that decides whether an analysis's evidence is good enough to act on: actionable, degraded or abstain. |
| Price basis | The continuous price history a holding's cost and a forecast's closes are measured on. A demerger starts a new basis; a rename does not. |
| Cohort / matured outcome | A defined group of predictions / an outcome whose observation period has finished. |
| Idempotent | Repeating the same operation does not apply its effect twice. |
| Cache / projection | A reusable fetched result / a secondary representation of another store. Neither guarantees freshness or authority. |
| PI | The planned improvement program (PI-2026-09). Story status lives in its state file, apart from this design description. |

## 2. Product map and three loops

StockAgent combines listed-equity research, adaptive feedback, a virtual
portfolio, discovery, IPO information and reports. Three connected product loops
explain the main flow:

1. **Research:** collect evidence, score dimensions, combine them, check the
   evidence and produce a report.
2. **Learning:** compare forecasts with observations, record feedback, propose
   or apply weight changes and maintain lessons and company knowledge.
3. **Portfolio:** evaluate held positions, record advice, optionally execute it
   in a virtual account, then produce transactions, value history and summaries.

```text
Prices, filings, news, macro data and caches
                    |
     Sector data bundle (typed section statuses)
                    |
  Unified analyst -> weighted aggregation -> decision gate -> research report
                    |                                              |
                    |                                       forecast envelope
                    |                                              |
   learned weights + lessons <-------- daily review <------ observed close
   (observe mode: proposals only)            |
                                  post-review portfolio hook
                                             |
                     advisor -> advice ledger -> virtual executor
                                    |                  |
                           outcome audit       transactions + equity
                                    |                  |
                             reports, digest, brief and inbox

Discovery + IPO information -> shelf, paper tracking and brief context
Watchdog + logs + backups -> operational visibility and recovery
```

Three controls cut across the loops:

- the **decision gate** (section 4) decides whether the evidence behind a
  verdict, a forecast, a review or a buy is good enough to act on;
- the **instrument registry** (section 4) decides which security a ticker
  means on a given date, and on which price basis;
- the **learning mode** (section 5) decides whether learned state may move
  decisions or is only recorded.

The nightly outcome auditor measures issued advice. The watchdog checks
operational milestones. Neither is the daily feedback agent. There is no
general human-approval queue between these components.

### Repository orientation

| Location | Responsibility |
|---|---|
| [API server](../services/api/server.py) and [routes](../services/api/routes/) | FastAPI startup, API and streaming interfaces. |
| [src/backend/shared](../src/backend/shared/) | Shared orchestration, canonical schemas, prompts, settings, the decision gate and the instrument registry parser. |
| [src/backend/sectors](../src/backend/sectors/) | Native implementations, generic graph and sector registry. |
| [services/data](../services/data/) | Fetchers, context assembly, caches, durable stores, backup, restore and off-site copy. |
| [core/intelligence](../core/intelligence/) | Forecasting, feedback, learning mode, regimes, seasonal logic, company knowledge and prediction-store tools. |
| [core/portfolio](../core/portfolio/), [core/discovery](../core/discovery/), [core/ipo](../core/ipo/) | Virtual money path, identity reconciliation, listed-stock discovery and IPO evidence. |
| `core/events` | The daily company-event feed: filings, disclosures and news for every tracked stock, typed and stored (section 4). Outside `core/intelligence`, because it reads users' holdings. |
| [core/audit](../core/audit/), [core/ops/watchdog](../core/ops/watchdog/), [core/delivery](../core/delivery/) | Outcome measurement, operational monitoring and delivery. |
| [src/frontend/prototypes](../src/frontend/prototypes/) | Served React/JSX application, PWA, chat rendering and data adapters. |
| [tests](../tests/) | Unit, integration and contract checks behind a hermetic boundary; their presence alone is not acceptance. |

Some paths are compatibility re-exports. For example,
`core/config/settings/base.py` forwards to
`src/backend/shared/config/settings/base.py`. Follow the import before editing;
two import paths need not mean two implementations.

## 3. Runtime, configuration and storage

### Runtime

[Dockerfile](../Dockerfile) uses Python 3.11 and runs
`services.api.server:app` with two Uvicorn workers. It copies `src/backend/`
to `/app/backend/`; local tests add `src` to the import path. The served
frontend is the prototype JSX application. [package.json](../package.json)
provides development tooling; there is no compiled app frontend build step.
The checked-in C# scheduler is not launched by this Dockerfile.

Both workers run startup. One binds a localhost TCP port, default 59321, and
becomes the background owner. It starts RL self-heal, APScheduler, cleanup and
the optional Atlas outbox drainer; the other serves API requests. This guard
is container-local, not a distributed lock or continuous standby takeover.
`GET /health` returns process-level `ok`; it does not verify background
ownership, storage, jobs, data or delivery. **Planned:** a readiness check and
background-ownership recovery (SA-029).

### Configuration

[The loader](../src/backend/shared/config/settings/loader.py) resolves a
declared environment override, then [config.yaml](../config.yaml), then a code
fallback. Not every YAML field has an environment override. Most settings are
resolved at import, so editing a file does not imply live reconfiguration.

| Checked-in setting | Meaning |
|---|---|
| `scheduler.enabled: false` | Local startup default; production overrides are separate. |
| `scheduler.feedback_cron: "30 16 * * mon-fri"` | Daily review default, interpreted in Asia/Kolkata. |
| `rl.hard_bind_verdict_enabled: true` | Research category follows the composite; model `final_score` remains separate. |
| `rl.learning_mode: adapt` | Learning switch, env `RL_LEARNING_MODE`. `adapt` lets learned weights and lesson emphasis move decisions; `observe` contains them (section 5). Any other value fails closed to `observe`. Production sets `observe`. |
| `decision_gate.mode: record` | Essential-data gate switch, env `DECISION_GATE_MODE`. `record` computes and records the gate everywhere and changes nothing; `enforce` withholds verdicts, forecasts, learning and new-risk buys that rest on unverified data or an unresolved identity (sections 4–6). Any other value fails closed to `enforce`. |
| [`config/instruments.yaml`](../config/instruments.yaml) | The instrument registry: effective-dated records of which provider symbol each listed ticker is priced from, on which price basis, and whether its identity is resolved (section 4). Evidence is needed to resolve an identity, never to quarantine one. It lists TATAMOTORS and HEXAWARE as unresolved, GATI and INOXLEISUR as delisted, and two plain aliases and five NSE renames as resolved. Quarantine acts through `decision_gate.mode`. |
| `advisor.exit_rule: shadow` | Which exit rule sells (section 6). `legacy`: the price-path rule acts and nothing is compared. `shadow`: it still acts, and both rules' verdicts are recorded. `evidence`: the evidence rule acts. Any other value reads as `shadow`. The owner switches only on the weekly scorecard's gate; `legacy` is the rollback. |
| `rl.control_lane_enabled`, `rl.scorecard_enabled`: true | Control/evaluation paths configured; not proof of valid prospective comparison. |
| `ipo.enabled: true`; `ipo.gmp_enabled: false` | IPO refresh and grey-market-price fetching have separate gates. |
| `delivery.enabled: true`; `delivery.email_enabled: false`; `delivery.push_enabled: true` | Job scheduling, transport enablement and credentials are separate conditions. |
| `watchdog.enabled: true`; `watchdog.prep_enabled: true` | Monitoring can perform configured prep as well as report results. |
| `error_backlog.*` | The operations backlog's windows and bounds (section 10): new 2 days, quiet 7 (35 for an acknowledged issue), fix verification 7, retention 90, at most 2,000 issues. Notices come from the watchdog's `error_backlog_triaged` entry. |
| `audit.enabled: true` | Nightly outcome grading configured. |

These are repository values; section 1 lists where production differs.
Credentials and `.env` contents do not belong in this document or in testing
evidence.

### Persistent records

| Records | Writer / consumers and scope |
|---|---|
| `data/predictions/<sector>/<ticker>/` | PredictionStore: envelopes, feedback, controls, weight memory, lessons and dossier, plus `<TICKER>_weight_observations.json` (observe-mode proposals). RL writes; advisor, evaluation and UI read. A ticker's history belongs to `<managed sector>/<TICKER>` (below). |
| `_shared_ledger.json` per sector; `_market_ledger.json` at prediction root | Shared lessons can affect more than one ticker; bad attribution can propagate. |
| `data/managed_tickers.json` | The managed list: each scheduled ticker's sector and enabled flag. Disabling a ticker keeps its history; removing it deletes the history. |
| `data/prediction_quarantine/<migration>/` | Stores moved out of the live tree by the ownership quarantine, with their `lineage.json`. Inside `data/`, so the nightly backup keeps them; outside the tree the evaluators walk. |
| `data/portfolio/<user>/` | PortfolioStore: holdings/cash, advice and transaction JSONL, value history, dated digests, briefs and weekly reviews, `weekly_scorecard.jsonl` (one results row per ISO week, written once; section 7) and `exit_shadow.jsonl` (both exit rules' verdicts, one row per holding per review day, written once; section 6). The nightly auditor's `advice_outcomes.jsonl` sits beside them. |
| `data/ipo/` | Historical issue facts and captured demand snapshots; reports derive from these records. |
| `data/market_cache/ipo.json` and EOD parquet | Cached IPO information and exchange price history; date, source and stale state matter. |
| `data/events/` | The company-event feed (section 4): `<SYMBOL>.jsonl`, one event per source item, append-only; `state.json`, the day's news-search count and the items judged not about their company; `runs.jsonl`, one line per run; `ownership/<SYMBOL>.json`, each quarter's FII, DII and mutual-fund share read from its shareholding XBRL. Market facts only, with no user in them. The feed writes; `GET /events/{symbol}` reads. |
| `data/logs/data_health.jsonl`; `data/logs/decision_gate.jsonl` | One data-health row per analysis run, also written to `telemetry.db`; one gate row per consumer decision. The gate log never holds a user id. |
| `scores.db`: `score_history` | One row per completed analysis, written at the orchestrator's exit after the decision gate; the newest 90 per stock. Home's scores, the watchlist, Portfolio's verdict changes and the chat read it; lists name only shared stocks and the viewer's own (section 10). `scripts/backfill_score_history.py` can copy past runs from `telemetry.db`'s `run_summaries`, marked so they can be removed; it copies nothing from a minute before a stock's first live row on, because that run is already recorded. |
| SQLite log, user and Atlas stores | Telemetry, sessions and relational indexes/outbox. Secondary tables may lag primary records. |
| `telemetry.db`: `app_logs`; `error_issues`, `error_backlog_cursor` | Every WARNING+ log record, with its run id and ticker when logged inside an analysis run, kept with no cap; and the operations backlog built from it (section 10). The backlog keeps message templates, never raw text, and prunes itself; it never changes `app_logs`. |
| `data/scheduler_job_outcomes.json`; `data/watchdog_state.json` | Operational results, including the daily review's per-ticker outcomes, and milestone state. Not proof of financial performance. |
| `data/backups/` | Local rotation of the last 7 archives, each with its manifest, and `backup_status.json` (the last restore drill and off-site result). An encrypted copy goes outside the volume once a target is configured (section 10). A local archive is not off-site recovery. |

PortfolioStore's JSONL ledger is the authoritative advice source. The
September audit found incomplete or stale optional Atlas projections. An empty
projection does not prove no advice was issued.

### Prediction-store ownership

A ticker's forecasts, reviews and learned state must live in one store, or its
history splits across graphs that score different dimensions.

**The owner rule.** A ticker's history belongs to `<managed sector>/<TICKER>`:
the store the scheduled forecast and review use, taken from the managed
entry's sector whether or not the ticker is enabled. Some tickers have no
owner: one without a managed entry, one whose entry has no sector, and one
whose entries disagree. Nothing guesses a sector.

**Why the rule exists.** SUZLON is managed as `renewable_energy`, and its
forecasts and reviews live in `renewable_energy/SUZLON`. The startup self-heal
in the [server](../services/api/server.py) once looked for every managed
ticker's envelope in `automobile/<TICKER>`. For a non-automobile ticker it
found none, so on the first deploy of each month it ran the automobile graph
into that directory. The 10 September audit found 15 such pairs, and all 58
feedback logs said `automobile`, because the store created each new log with
the schema default.

**Writers.** Every writer keeps to the owner rule:

- self-heal uses each managed entry's sector, so a restart rebuilds a missing
  envelope in the ticker's own store;
- [PredictionStore](../core/intelligence/rl/stores/prediction_store.py)
  stamps its own sector on the feedback logs, weight memory and ledgers it
  creates. Files already on disk keep what they say, so a default can still
  be told from a declared sector;
- the daily review rebuilds a missing or unreadable weight file from its
  sector's graph, as the forecast does.

**The inventory** ([store_inventory](../core/intelligence/rl/stores/store_inventory.py)).
`python -m core.intelligence.rl.stores.store_inventory --out manifest.json` is
read-only. It reads files directly and never constructs a PredictionStore,
whose constructor creates its directory. For each store it records its
identity (path, ticker, file count and one digest), its sector evidence, its
ownership, its schema markers and the code that reaches it. The sector status
says how far the store's own data supports its directory:

| Status | Meaning |
|---|---|
| `confirmed` | Every file with a dimension roster names one graph, and it is the directory's graph. A directory name alone never confirms. |
| `conflicting` | A file names another graph or several graphs, or declares another sector than its directory. |
| `directory_only` | A sector directory whose files carry no roster: only the directory name. |
| `roster_only`, `missing` | A legacy flat `<TICKER>/` store with, or without, a recognisable roster. |
| `empty` | No files, typically a directory created by a read. |

A dimension roster is the set of dimension keys in a file's rows or weights.
It identifies the graph that produced them: the nine automobile dimensions
differ from the six renewable-energy ones. `roster_vs_owner` compares the
rosters with the owner's graph. `automobile/SUZLON` is `confirmed`, because
the automobile graph did produce it, and `wrong_roster` for its owner. The
`sector` fields of feedback logs, weight memory and ledgers are reported,
never used as evidence. Each roster comes from the graph's weight table
through the sector router. If a native sector is switched off, it takes the
generic roster and its own files read `unrecognized`; the summary's
`roster_collisions` then names the graphs whose files cannot be told apart.

The manifest also lists duplicates, each marked identical or conflicting:

- tickers with more than one non-empty store;
- envelope cycle ids found in more than one store;
- graded days (ticker and date) recorded more than once, in one store or
  across stores.

These are derived keys, not issuance identities. The manifest holds paths,
tickers, sector keys, counts, SHA-256 digests, dimension names and field
names, and no prices, text or user data. Its digest excludes the generation
time, so an unchanged tree always gives the same digest.

**Who reads which store.** Each rule below picks a store for a ticker:

| Class | Store it picks | Code |
|---|---|---|
| `managed` | `<managed sector>/<TICKER>` | The monthly forecast and daily review ([scheduler](../services/scheduler/python/scheduler.py)), startup self-heal, event ingest, weekly ledger cleanup, RL monitor and scheduler API. |
| `analysis_graph` | `<graph sector>/<TICKER>` | An analysis's learned-weight read ([base_orchestrator](../src/backend/shared/pipeline/base_orchestrator.py)) and its agents' prompt-enhancement and dossier reads. For a pharma ticker that is `generic/<TICKER>`, while its RL store is `pharma/<TICKER>`. |
| `automobile_default` | `automobile/<TICKER>` when no sector is passed | Manual CLIs (`run_schedule forecast` and `daily-review`, `generate_forecast`'s own main), the bundle builder's and base agent's fallbacks, the UI's last fallback. |
| `discovery` | every `<dir>/<dir>` pair | Scorecard, eval harness, learning evidence, analytics and universe walk the whole tree; the UI scans it for an unmanaged ticker. |
| `flat_cli` | `<TICKER>/` | `run_schedule feedback-status`. Discovery misreads such a directory as a sector. |

The pre-open shock check follows none of these rules: on a shock morning it
scans the four native sectors' built-in ticker lists, not the managed list,
and reads `<list sector>/<TICKER>`. A managed ticker outside those lists is
not checked, and a listed ticker without a store gets an empty directory.
The inventory's own reader table still files the check under `managed`.

The last three classes, and the constructor's directory creation, remain.
**Planned:** one frozen `store_key` replaces them (SA-026), and row-level
lineage marks rows from another graph inside an owner's store (SA-017).

**The quarantine** ([store_migration](../core/intelligence/rl/stores/store_migration.py)).
It has three commands:

- **`plan`** is read-only. It proposes to quarantine each non-empty store of a
  managed ticker that is not the owner's store, including a legacy flat one.
  It holds, and never moves, anything that needs a decision: duplicates of an
  unmanaged ticker, an owner that disagrees with the ticker map, a managed
  entry with no sector or two conflicting entries, and two owner directories
  that differ only in case. It flags an owner's store that carries another
  graph's roster. The plan lists every file's SHA-256 and ends with one digest.
- **`apply --plan … --approve <digest>`** recomputes the plan and refuses
  unless it is unchanged. It creates a new migration directory
  `prediction_quarantine/<UTC time>-<digest>/` beside `data/predictions` and
  writes the lineage record before the first move. It re-hashes each store
  immediately before moving it and stops at the first difference. A store
  moves by one directory rename: its bytes are never copied, rewritten, merged
  or deleted, and they are hashed again after the move. The quarantine keeps
  the live layout, so `PredictionStore(ticker, sector, base_dir=<migration>/stores)`
  still reads it.
- **`rollback --migration DIR`** renames each store back after checking its
  bytes. It never merges: it refuses a live path that holds any file, and a
  quarantined store whose bytes changed. An empty directory at the live path,
  which any read through `PredictionStore` creates, is removed first. A
  refused store is retried on the next run, so an operator can repair it and
  run rollback again. A store already back at its live path with its recorded
  bytes counts as restored (`found_live`), whether it was moved by hand or by
  a rollback interrupted before it recorded the move. A run reports
  `rolled_back` only when every store is back with its recorded bytes;
  otherwise it reports `partial`, and `lineage.json` gives each store's state.
  After a complete apply, rollback restores the live tree byte for byte.

A racing writer is detected, not prevented, so an apply runs in a job-free
window and needs the owner's authorization. Production's one apply is in
section 1.

## 4. Research: input to recommendation

**Trace:** [registry](../src/backend/sectors/registry.py) →
[base orchestrator](../src/backend/shared/pipeline/base_orchestrator.py) →
[bundle builder](../services/data/context/bundle_builder.py) →
[unified analyst](../src/backend/shared/pipeline/unified_analyst.py) →
[aggregator](../src/backend/shared/pipeline/signal_aggregator.py) →
[decision gate](../src/backend/shared/pipeline/decision_gate.py).

1. Resolve input to a company, symbol and sector. A ticker the app already
   tracks resolves to itself with no model call (below); other text goes to an
   LLM, with a web search when its answer cannot be verified.
2. Select the graph. Automobile, banking/BFSI, IT and renewable energy have
   native implementations; other sectors use generic analysis. The RL router
   delegates graph selection to the central registry.
3. Assemble company/sector news, fundamentals, technicals, macro, flows, peers
   and company knowledge. NSE prefetch data is shared. Each section reports a
   typed status: it may be verified, cached, stale, a fallback, empty, not
   applicable or failed.
4. The preferred unified analyst scores the sector dimensions together. The
   legacy per-dimension pool remains a fallback. A whole research request can
   involve resolution, aggregation, retries and extra provider calls; it is
   not necessarily one LLM call.
5. The aggregator combines weighted scores, excludes errored contributions
   and normalizes surviving weights. With no surviving weight it falls back
   to a neutral composite. An LLM produces narrative and report fields.
6. With hard-bind enabled, configured score bands determine the categorical
   verdict. The raw model verdict is logged for comparison; its numeric
   `final_score` remains separate.
7. The decision gate labels the report actionable, degraded or abstain before
   anything logs or returns its verdict.
8. Score history, run summaries, logs and the data-health row support the
   user report and later diagnosis.

**Example:** scores 0.8 and 0.4 at weights 0.75 and 0.25 give composite
`0.8 × 0.75 + 0.4 × 0.25 = 0.70`. The configured band containing 0.70 gives
the bound verdict. A different LLM `final_score` is a different field, not
necessarily an arithmetic error.

### Data health

Every unified run writes one data-health row, to `data/logs/data_health.jsonl`
and `telemetry.db`. Every section producer returns a typed result
([fetch_result.py](../services/data/context/fetch_result.py)): a status, the
source, the as-of date of its newest datum, and a reason. The producer decides
the status from its structured data, never from its sentence. A sentence such
as "Technical data unavailable for TATAMOTORS" or "[No results for: …]" is not
evidence of data. A status read from such text once recorded two runs against
a price source answering HTTP 404 as `ok`, with 10 live sections and 9/9
dimensions (2026-08-26).

- `ok` and `cache_hit` mean verified data. `stale` means older than the
  freshness bound: a newest price bar over 7 days old, or a newest reported
  quarter over 200 days old. `fallback` means a core figure was replaced by
  search snippets or substituted zeros, or the newest listed quarter has no
  figure (yfinance lists an announced quarter as NaN before its results are
  filled in; `as_of` is then the newest quarter with figures). An older
  quarter without a figure is named in the reason only. `empty` means
  nothing came back; `n/a` means deliberately not fetched; `failed:<Type>`
  means an exception. `unverified` means plain text with no typed result.
- A row is `ok` only when every dimension scored and every applicable section
  is verified and fresh. Otherwise it is `degraded` or `hollow`, and
  `health_reasons` says why. Fundamentals, technicals and peers valuation are
  also listed in `essential_unusable`, which the decision gate reads.
- A Tavily month-cache entry records how many results it held, so a cached
  "no results" stays `empty` for the rest of the month.
- Rows carry `contract_version: 2`. Older rows stay as written and are read as
  version 1 with unknown provenance, not upgraded.

**Example:** the price source answers 404 for TATAMOTORS while news, macro and
flows answer. The analyst's prompt text is the same either way. The row says
`degraded` with `essential technicals=empty`, `essential fundamentals=empty`
and `essential peers_valuation=fallback`, and the decision gate reads the same
statuses.

### Bank income statements

A bank's quarterly income statement has interest income and net interest
income, and no operating-income, EBIT or gross-profit row. The
[fundamentals fetcher](../services/data/fetchers/fundamentals.py) lets the
statement's shape decide how it is read, never the ticker or its sector:

- both interest rows and no operating row make a **bank-format** statement.
  Its net interest income takes the operating line's place: the prompt shows
  it per quarter, and a blank newest quarter in it still means `fallback`. The
  prompt says operating margin is not reported, with no 0.0 figure, and the
  section's reason names the format;
- revenue is still required, and the 200-day freshness bound still applies.
  A bank's revenue is yfinance's "Total Revenue", which is not the filing's
  total income: YES Bank's is below its own interest income;
- PAYTM reports EBIT beside its net interest income, so it stays a standard
  statement. A non-bank statement without an operating row stays `fallback`.

Substituting zeros for the missing line would make every bank `fallback`,
show an EBITDA margin of 0.0% and make the gate abstain on every bank
analysis. That is what happened from 28 Sep to 1 Oct: YESBANK, IDFCFIRSTB,
RBLBANK and FEDERALBNK abstained on 17 of 78 analyses (22%), although their
June-quarter figures were on file.

**Example:** YES Bank's June quarter (revenue ₹4,655.98 Cr, net interest income
₹2,785.48 Cr) reads `ok`, so the gate does not abstain on its fundamentals.
Envelopes keep the gate they were issued with, so an enforce decision counts
only rows issued after a reading rule changes.

### Sector benchmarks

The technicals section shows the stock's correlation and beta against an
index chosen for its sector:

- the bundle and the legacy agents pass the run's sector, and
  `settings.SECTOR_BENCHMARKS` names its index: automobile `^CNXAUTO` (Nifty
  Auto), banking/BFSI `^NSEBANK` (Nifty Bank), IT `^CNXIT` (Nifty IT) and
  renewable energy `^CNXENERGY` (Nifty Energy). `get_peer_correlation` in
  [fetcher.py](../core/intelligence/algorithms/indicators/fetcher.py) has no
  default index;
- a stock in any other sector, or with no sector, is measured against the
  broad market, `^NSEI`, labelled "Nifty 50 (broad market)". It is never
  measured against another sector's index;
- returns are paired over the sessions both series have a close for. Fewer
  than 30 paired returns, no data for either symbol, a flat series or a failed
  download leave correlation and beta unmeasured. The prompt then says
  "unavailable" and why, and the section's reason names it. The section's
  status stays the stock's own: the index is context for its price history;
- the section's provenance names the index (`benchmark`), and each call logs
  one `[technicals] <ticker> sector=<sector> benchmark=<index>` line.

An unmeasured value is never shown as a measurement. A default of
"Correlation: 0.0 | Beta: 1.0" looks like data; it once appeared on every
analysis, banks and IT included, because a single automobile index served
every sector and Yahoo had no data for it.

**Example:** HDFCBANK's technicals read "Nifty Bank Correlation: … | Beta: …",
measured against `^NSEBANK`. Yahoo has no data for `^CNXAUTO` or
`^CNXENERGY`, while `^NSEBANK`, `^CNXIT` and `^NSEI` each answered with 188
sessions on 5 Oct. So an automobile stock reads "Nifty Auto Correlation:
unavailable | Beta: unavailable (benchmark ^CNXAUTO returned no price data)",
and a renewable-energy stock reads the same for Nifty Energy. **Planned:**
choosing an index with data for those two sectors belongs to the sector
lenses (SA-026).

### Decision gate

Every report carries a typed `decision_gate`
([decision_gate.py](../src/backend/shared/pipeline/decision_gate.py)), computed
from the same section statuses and dimension counts as the health row, whether
or not the row is recorded. The aggregator renormalises over whatever was
scored, so without a gate one surviving dimension becomes the whole verdict:
production once recorded BUY on 1 of 6 scored dimensions and STRONG BUY on 3
of 9.

- **abstain** when an essential section (`observability.data_health_essential_sections`)
  is not `ok`/`cache_hit`, when fewer than half the sector's dimensions were
  scored (`decision_gate.min_dimensions_fraction: 0.5`), when the run has no
  bundle at all (the legacy worker-pool fallback has no provenance), or when
  the ticker's identity fails (below). An unresolved symbol lands here too:
  no provider knows it, so its essential sections are empty.
- **degraded** when it may act but an ordinary enrichment (news, macro, flows,
  a dimension above the floor) is missing. Degraded is actionable.
- **actionable** when nothing is missing.

One switch, `decision_gate.mode` (env `DECISION_GATE_MODE`), governs every
consumer. In `record`, every consumer computes the gate and records what
enforcement would stop: in `data/logs/decision_gate.jsonl`, on the report, on
forecast rows and on advice. Nothing else changes. In `enforce` an abstaining
report's verdict reads `INSUFFICIENT DATA` (the aggregator's verdict is kept as
`withheld_verdict`), and sections 5 and 6 describe what the learning and
portfolio consumers then refuse. An unrecognised value fails closed to
`enforce`.

**Example:** the TATAMOTORS 404 run above scores 9 of 9 and the aggregator
says STRONG BUY. Its gate is `abstain`, naming the three essential sections.
In `record` the user still sees STRONG BUY and the gate log gains a row saying
what enforcement would have withheld; in `enforce` the user sees INSUFFICIENT
DATA. The same run with its price source answering stays `actionable` and
keeps STRONG BUY.

### Instrument identity

The gate's section checks prove that evidence arrived and is fresh, not that
it belongs to the company the ticker names. After the 2025 demerger, an
undated override mapped TATAMOTORS to TMPV.NS, the passenger-vehicle company,
while the name "Tata Motors Limited" passed to the commercial-vehicle company.
The news and the prices could then describe two companies, and with TMPV's
data healthy the analysis was `actionable`.

The instrument registry, [config/instruments.yaml](../config/instruments.yaml),
records identity explicitly. `symbol_resolver.resolve_identity` reads it, and
its parsing lives in [instruments.py](../src/backend/shared/data/instruments.py).
For each listed ticker it holds effective-dated segments. Each segment names
the provider symbol to ask, the **price basis** those prices are on, and a
status:

- only an `active` segment resolves. When its symbol is not the ticker's own
  listing, it must say how the two relate. An `alias` needs a reason. A
  `rename`, `demerger` or `relisting` needs evidence: an exchange or company
  document with a reference and a date;
- `unresolved`, `suspended` and `delisted` quarantine the ticker, and need
  only a reason. Evidence resolves an identity; nothing is needed to
  quarantine one;
- the ticker is also quarantined by an invalid record, a date no segment
  covers, or an unreadable registry (fail closed);
- a ticker the registry does not list resolves to its own NSE listing. A
  learned self-heal to another code (`data/yf_symbol_cache.json`) is still
  fetched, but is `unresolved` until someone records it;
- a registered ticker is never self-healed. An empty fetch is an outage or a
  lifecycle event, and a Yahoo search could swap in another company.

A rename keeps the basis: the same company under a new code, and the provider
moves its history to the new code. A demerger or a relisting starts a new
basis, because the continuing company's price no longer includes what was spun
off.

The registry records five configured codes NSE has renamed, each from NSE's
circular: PVR (PVRINOX from May 2023), MCDOWELL-N (UNITDSPR, June 2024),
ZOMATO (ETERNAL, April 2025), LTIM (LTM, February 2026) and ICICIPRULI
(ICICILIFE, October 2026). Each change notice carries the ISIN that NSE's
equity list gives the new code today, so each is the same security. Each ticker keeps its name and its
basis, and is priced and cross-checked under the new code on every date, so a
forecast issued under the old code is graded against a close under the new
one. Without the record, the app asked for the old code: Yahoo no longer
prices it, and NSE lists no corporate action under it, although NSE's close
still answers it with the new code's rows.

Two configured codes no longer trade. The registry records each as `delisted`
from the first day NSE suspended it for an amalgamation:

- GATI, which traded as ACLGATI from November 2023 and was suspended from
  12 November 2025;
- INOXLEISUR, merged into PVR and suspended from 17 February 2023.

Each keeps its one basis and names no successor: neither has a price, and
nothing is held. The gate abstains on either.

The registry maps a code only on exchange evidence, never on a company name.
So it does not map the configured codes NSE does not list: ACCCEMENT, APL,
BAYER, DEEPAKNITRI, MAHINDHOTEL, MTAR and NIIT. None appears in NSE's equity
list or its symbol-change history, and Yahoo has no price for any, so none can
be bought or graded. Five were never NSE codes. BAYER and NIIT once were, for
Bayer India and NIIT (NSE lists their rows from 2002–2003), under ISINs other
than those of today's BAYERCROP and NIITLTD. **Planned:** FIX-020 corrects them in the sector list.

Yahoo moves a renamed code's history over gradually: on 30 October 2026,
ICICILIFE.NS held only the sessions since 14 October, so ICICIPRULI's
history-based analysis rests on a few weeks until Yahoo carries the rest.

The gate abstains when the ticker's identity for today is not resolved, or when
the technicals' price history came from another symbol than the identity names
(the section's provenance records its `symbol`). Identity reasons come first,
and the report's `decision_gate.identity` records the instrument (ticker,
symbol, basis, status). The close fetchers ask for the resolved instrument,
including the BSE fallback, and the NSE cross-check uses the registry's NSE
code.

**Example:** TATAMOTORS is `unresolved`, still priced from TMPV.NS. With
healthy data the analyst says STRONG BUY:

- in `record` the user still sees STRONG BUY, and the gate log gains a row
  starting "identity unresolved: retired by the owner's decision …";
- in `enforce` the user sees INSUFFICIENT DATA.

**TMPV and TATAMOTORS.** The passenger-vehicle company is tracked as its own
ticker, TMPV, by the owner's decision of 29 Sep. TMPV needs no registry record:
its ticker, its name and its prices are one company, so it resolves as its own
listing, and its learning starts fresh. TATAMOTORS stays quarantined, so its
history (weights learned partly on the pre-demerger company) is never graded
or advised against another company's prices. TMPV is in the automobile
sector's exact-match list, so the LLM ticker lookup, whose prompt names
"TATAMOTORS – Tata Motors Ltd", is never asked to resolve it. A retired ticker
is disabled in the managed list, never removed, because removing it deletes
its prediction history.

### Ticker resolution

A ticker resolves to itself, with no LLM or web-search call, when it is in its
sector's `TICKERS`, in the managed list (`data/managed_tickers.json`, any
sector, enabled or not) or in the instrument registry:

- the managed list and the registry are read on every resolution, so a ticker
  the owner adds is known at once. Nothing writes the list on this path;
- the company name comes from the curated or learned name, else yfinance for
  the registry's symbol, else the ticker; never from the LLM;
- a retired or unresolved ticker such as TATAMOTORS resolves to itself, and
  the identity gate above decides whether it may act;
- an unreadable registry quarantines every ticker but names none, so free text
  is not mistaken for a ticker;
- free text ("tata elxsi") goes to the LLM. So does a weekly discovery
  candidate that no list holds, so its shelf idea can still rest on another
  company's analysis.

Asking an LLM which company a tracked ticker is lets it answer wrongly. At
09:16 on 1 Oct the monthly forecast for TATAELXSI (Tata Elxsi) was resolved to
TATAMOTORS: the run analysed Tata Motors, with Tata Motors' learned weights,
and saved TATAELXSI's October envelope from that analysis. The same path
turned TVSMOTOR into TVSMOTORS and named HAPPSTMNDS "Happy Smile Digital Ltd".
**Planned:** one sector definition replaces the per-sector lists (SA-026).

### Company events

An analysis run reads NSE filings and company news only for itself. The
company-event feed (`core/events/feed.py`) keeps a daily record of what
happened to every stock a user holds or watches and to every active shelf
idea: results, guidance, orders, ratings, management changes, regulatory
action, corporate actions and deals, and from NSE's disclosures, insider
trades, substantial acquisitions, promoter pledges and shareholding changes.
Each event is typed, dated and cites the item it came from. Two jobs run it on
trading days, at 08:15 and 18:30 IST
(section 9). The evidence exit rule reads its high-materiality negative
events (section 6); with `advisor.exit_rule: shadow` it only records what it
would do. The investment case, the explanations and the brief's company lane
are to read it (**Planned:** PR-005, PR-007, PR-008).

A run:

1. **Stocks.** Holdings first, then watchlists, then shelf ideas, each stock
   once, at most `events.max_symbols` (60). A stock whose identity the registry
   does not resolve that day (above) is skipped and named in the run record.
   NSE is asked for the registry's NSE code, so TVSMOTORS is fetched as
   TVSMOTOR, and its events are stored under TVSMOTORS.
2. **Items.** NSE announcements filed in the last `events.lookback_days` (7),
   board-meeting intimations filed in that window, and one Serper news search
   (the daily review's company query, the past 24 hours, 5 articles). Searches
   are capped at `events.news_queries_per_day` (60), half per run, in stock
   order; a spent credit stops the run's searches. Each run logs its searches
   with the month's Serper count. The stock's NSE disclosures in the same
   window are read too (below).
3. **New items only.** An item already stored, or judged not about the
   company in the last `events.seen_days` (30), is not sent again. At most 24
   per stock per run, newest first.
4. **Typed** by one bulk-tier call per 12 items. The model answers per item:
   whether it is about the company, one sentence, a category (results,
   guidance, order, rating, management, regulatory, corporate_action, deal,
   other), a direction (positive, negative, neutral) and a materiality (high,
   medium, low). Disclosures are typed by fixed rules instead, and the model
   may not answer their categories (insider, pledge, ownership).
5. **Stored** once per item in `data/events/<SYMBOL>.jsonl`, keyed by NSE's
   announcement id, a disclosure's NSE id, or the article's URL without
   tracking parameters. Serper returns the links after a search's top 3 as
   `google.com/goto` redirects, so the [fetcher](../services/data/fetchers/news.py)
   reads a link on google.com, or a subdomain of it, as no link. Such an
   article is dropped and counted (`news_redirect_links`, beside `news_results`,
   the articles Serper returned). So an article that is result 2 in the
   morning and result 4 in the evening is stored once, under its own address,
   and an article seen only as a redirect is not stored.

The record (`src/backend/shared/schemas/events.py`) is `{id, symbol, what,
category, direction, materiality, source, source_url, announcement_id,
title, publisher, published_at, published_raw, occurred_from, occurred_to,
facts, fetched_at, classifier}`. `occurred_*` and `facts` are filled for a
disclosure only, and its `classifier` is `rules`.
**Planned:** the text reader emits the same record (SA-046).

**Dates.** `published_at` comes from the source and never from the fetch:

- an announcement's NSE filing time, as an IST date-time;
- a board meeting's filing time, never its meeting day, which is often weeks
  later;
- an article's Serper date, read by the brief's rule: "10 hours ago" at 08:15
  counts back to 22:15 the day before, and that IST day is kept.

`fetched_at` is the moment that stock's own fetches returned. A run of 50
stocks can last more than 10 minutes, so the clock is read once per stock,
not once per run. If a stock's turn comes at 18:42 and NSE shows its filing of
18:41:20, the event keeps 18:41:20; an article's age counts back from that
stock's fetch. An NSE time more than 10 minutes after the fetch is not stored
yet: the run counts it (`nse_rows_ahead`), and a later run, inside the 7-day
window, stores it with its own time. The 10 minutes allow for NSE's clock
running ahead of ours, so within them `published_at` can be a little later
than `fetched_at`. A board meeting's identity uses its own filing day, never
the clock.

So `null` means the source gave no readable date (or, for an article, a date
in the future). Such an event is stored but never returned for a `since`
query, so it never counts as new. `published_raw` keeps the source's own
string, so either date can be checked.

**The company.** An event is filed under the stock the feed asked about; the
model never names the stock. An NSE row must carry the code that was asked
for. An article must mention the company: its ticker or NSE code in capitals,
its name without legal suffixes ("Maruti Suzuki" for Maruti Suzuki India
Limited), or the first two words of a longer name ("Adani Ports"). So an
article about Tata Motors is never filed under Tata Elxsi. The model can still
answer "not about this company", for example for a market roundup.

**Grounding.** An answer is dropped and counted when it cites no item it was
given, states a figure its item does not contain ("profit up 15%" for an item
that says 12%, "Rs 35 billion" for "Rs 3,500 crore"), or has an unknown
category, direction or materiality. A failed call or malformed output stores
nothing, and the next run asks again; so does a failed NSE or news fetch. The
run never raises.

**Same-day dossier knowledge.** A newly stored NSE announcement whose subject
the event ingestor qualifies (results, earnings call, guidance, analyst meet,
investor presentation, dividend) runs the ingestor for that stock in the same
run, under its managed sector (section 5), instead of on Saturday. A
board-meeting intimation does not, because the meeting has not happened. A
stock that is not an enabled managed stock has no dossier, so its event is
only stored.

**Disclosures.** The same run reads four NSE disclosure feeds for each stock
(`services/data/fetchers/nse_disclosures.py`) and types
them by fixed rules, with no model call
(`core/events/disclosures.py`). Each source is switched by
`events.disclosures.*`.

| Source | Event | What it records |
|---|---|---|
| Insider trades (SEBI PIT), filed in the window | `insider` | Who (the promoter group, directors and key managers, or others), bought or sold, in the market or off it, shares and rupees |
| Substantial acquisitions (SAST Regulation 29) | `deal` | Who acquired or sold what share of the company, and what they hold after |
| Promoter encumbrance (SAST Regulation 31) | `pledge` | A pledge created, released or invoked, and its share of the company |
| Shareholding pattern, each quarter | `ownership` | Promoter, FII, DII and mutual-fund share against the quarter before, when one moved `events.ownership_move_points` (1) or more |

`published_at` is when NSE disseminated the filing: when we could have known.
The trade, pledge or quarter-end days are kept apart in `occurred_from` and
`occurred_to`. A promoter who sells on 21 Oct and files on 22 Oct is news on
22 Oct. `facts` keeps the figures (rupees, shares, percentage points), so a
reader can check `what`. No person is named: an insider is "the promoter
group" or "directors and key managers", a pledger "a promoter". A substantial
acquirer is named, because that holder (usually an institution) is the news.

A direction is claimed only where the data supports one:

- An insider filing is positive when the promoter group and directors bought
  more than they sold in the market, negative when they sold more.
  Employees' trades and off-market moves (gift, inheritance, inter-se
  transfer, ESOP allotment) are neutral and low. Materiality is the
  open-market net: ₹10 crore or more high, ₹1 crore or more medium.
- A promoter-group sale while promoters hold more than 75% of the company
  (the latest pattern) is neutral, at most medium. The sentence says the sale
  may be to meet the rule that a listed company keeps 25% public. Any other
  net sale says "The filing gives no reason for the sale": a sale to pay tax
  or repay a loan looks the same.
- An insider filing NSE lists as a revision (`typeOfSubmission` "Revision",
  or the XBRL's revised flag) is neutral and low, whatever its trades. Its
  sentence says it revises an earlier filing, so the trades may have been
  reported before and are not read as new trading. NSE gives a revision its
  own `appId` and rarely names the filing it corrects: in the 28 days to 23
  Oct 2026, 6 of 308 filings were revisions, and the 2 that named an earlier
  filing named one not on the list. So the revision is stored as its own
  event, and the event of the filing it corrects is left as it was.
- A substantial acquisition or sale is positive or negative only for a
  promoter. A fund crossing 5% is neutral: the filing does not say why.
- A pledge created or invoked is negative, a release positive and at most
  medium.
- An ownership move is positive when every moved category rose, negative
  when all fell, and neutral when mixed. When the promoter share fell, the
  sentence says the pattern does not tell a sale from dilution by new shares.

An insider filing's trades are in its XBRL file. The feed reads it once, for
a filing not stored yet, at most `events.max_documents_per_symbol` (10) per
stock per run, newest first. A quarter's shareholding XBRL (about 0.6 MB) is
read once; its FII, DII and mutual-fund figures are kept in
`data/events/ownership/<SYMBOL>.json`. A document is fetched only from NSE's
archive host. If its promoter figure differs from NSE's quarterly list by
more than half a point, its other figures are not used. A failed endpoint or
document gives no event and is named in the run's `disclosures_failed`; the
next run asks again. When the shareholding list fails, the stock's insider
filings wait for the next run too, since the 75% test needs it. The run line counts `disclosures_stored` by kind and the
documents fetched, failed, unreadable and over the cap.

**Example:** at 08:15 on Fri 23 Oct, KARURVYSYA is held. NSE lists one
insider filing, disseminated on 22 Oct at 19:29:01. Its XBRL shows three
promoter-group members, each selling 2,000 shares for ₹7,69,230 in the market
on 21 Oct. The event reads "The promoter group sold 6,000 shares worth ₹23.1
lakh in the market on 21 Oct 2026. Filed with NSE on 22 Oct 2026. The filing
gives no reason for the sale." It is `insider`, negative and low (under ₹1
crore), with `published_at` 2026-10-22T19:29:01+05:30 and `occurred_from`
2026-10-21. MARUTI's 30 Sep pattern moved less than a point in every category
(FII 12.82% to 12.42%, mutual funds 15.33% to 14.77%), so it gives no
ownership event.

**Example of a revision:** at 18:30 on Thu 1 Oct, PATINTLOG is held. NSE lists
filing 3886 (17:11:45): the promoter group bought 2,63,832 shares for ₹36.6
lakh and sold 2,63,832 for ₹35.9 lakh in the market, 23 to 29 Sep. It also
lists 3893 (18:23:57), a revision with the same two trades; NSE's remark says
only the filing date was corrected. 3886 is stored positive and low (net
+₹71,214). 3893 is stored neutral and low, and its sentence ends "It revises
an earlier filing, so these trades may have been reported before and are not
read as new trading." Likewise NAUKRI's revision 3962 (8 Oct) of a director's
₹68.0 crore sale traded on 18 to 20 Aug is neutral and low, not a new
negative, high sale.

**Who reads it.** Events hold no user. But the feed covers only the stocks
someone tracks, so `GET /events/{symbol}` gives a member the events of their
own holdings and watchlist and of the shelf. Any other symbol gets the same
404, whether or not it has events; the owner reads any.

**Example:** at 08:15 on Thu 22 Oct, MARUTI is held. NSE lists two filings in
the window: 21 Oct 15:39, an analyst-meet schedule, and 15 Oct 19:13,
"Action(s) taken or orders passed". Serper returns five articles, and the one about
Tata Motors is dropped before the model sees it. The 21 Oct filing is stored
with `published_at` 2026-10-21T15:39:05+05:30 and `fetched_at` a few seconds
after 08:15, when MARUTI's fetches returned, and as an analyst-meet filing it
runs MARUTI's dossier ingestion under automobile.
At 18:30 the same items are fetched again, and none is sent to the model.

**Limits.**

- An article that names the company only by a short form ("Maruti", "L&T")
  and not by its ticker in capitals is dropped.
- The reverse: a short code or a two-word name prefix can pass for another
  company. "LT Foods" passes for L&T (code LT), "Indian Railway Finance
  Corporation" for IRCTC ("Indian Railway"), "HDFC Life Insurance" for LIC
  ("Life Insurance"). The model's "not about this company" answer is then the
  only guard.
- News is searched over the past 24 hours (`events.news_recency`, `qdr:d`).
  So Monday's 08:15 run misses articles published between Friday 18:30 and
  Sunday 08:15, and the first run after an NSE holiday misses in the same way.
  Filings are not affected: the 7-day window covers them.
- An NSE row whose time stays in the future (a wrong timestamp) is never
  stored; every run counts it in `nse_rows_ahead`.
- One story told by several outlets gives several events. **Planned:** the
  brief groups them by company, category and day (PR-008).
- A relative age gives a day, not a time; "1 month ago" counts as 30 days.
- NSE's field names were recorded from its live responses on 22 Oct 2026 (the
  disclosure feeds on 23 Oct). A renamed field gives undated or missing items,
  which the run counts.
- NSE's older insider endpoint (`corporates-pit`) has had no rows since late
  April 2026; the feed reads its replacement (`corporates-pit-gg`).
- The 75% test reads the latest quarter's promoter share, up to three months
  old.
- A revision does not change the stored event of the filing it corrects.
  When a revision moves a trade to another person's category (for example
  from promoter to a relative), the original's event keeps its direction.
- A revised shareholding pattern for a quarter already compared is not
  compared again.
- More than 10 new insider filings for one stock in a run wait for the next
  run; any that leave the 7-day window by then are missed.
- The store has no retention yet; it grows by a few events per stock per day.

### Limits of the research path

- The gate records only (section 1). In the 2026-10-01 measurement, 25 of 78
  analyses would have abstained: 17 were the bank statements and 2 the
  resolution defect above, both since fixed. A blank newest quarter still
  makes fundamentals `fallback`, and so abstains, for weeks after each
  quarter end. Identity reasons share the same switch, so enforcing the gate
  also quarantines TATAMOTORS and HEXAWARE. The owner re-decides on rows
  issued since those fixes ([record](planning/PI-2026-09/evidence/SA-003-enforce-decision-2026-10-01.md)).
- Bundle call counters are not complete provider or fallback cost accounting.
  **Planned:** SA-025 counts actual calls, before SA-026 consolidates sector
  definitions and SA-027 retires only justified fallback duplication.
- **Planned:** the one-engine redesign replaces the per-sector graphs with
  sector lenses and a deterministic factor engine (section 11).

## 5. Learning: forecast, review and memory

**Trace:** [forecast generation](../core/intelligence/rl/workflows/generate_forecast.py),
[interpolator](../core/intelligence/rl/algorithms/price_interpolator.py),
[daily review](../core/intelligence/rl/workflows/daily_review.py),
[feedback agent](../core/intelligence/rl/agents/feedback_agent.py),
[weight adapter](../core/intelligence/rl/agents/weight_adapter.py),
[prediction store](../core/intelligence/rl/stores/prediction_store.py),
[learning mode](../core/intelligence/rl/learning_mode.py).

### Forecast generation

The workflow loads weights and knowledge, runs analysis and creates an
envelope across future exchange sessions. A model-shaped profile, static
fallback and simulated paths supply forecast prices and bands. Generated
forecast rows are not independent observed samples or guaranteed probabilities.

The monthly trigger is the **calendar first at 09:00 IST**. The generated rows
use exchange trading dates. Do not call that trigger the first trading day.
Shocks, thesis changes and later evidence can revise or archive envelopes.

Each forecast row records where it came from:

- `source_run_id`, the analysis run that issued it, and `data_gate`, that
  run's gate. The envelope keeps the latest run's full `decision_gate`;
- `instrument`, the instrument its analysis priced (ticker, provider symbol,
  price basis, identity status). A later registry change never rewrites it;
- the envelope's `learning_mode`.

A row issued before these stamps existed has an empty `data_gate`, meaning
provenance unknown, and `instrument: {}`. For such a row the review asks the
registry whether the basis changed between the envelope's issue date and the
session.

In `enforce` mode an abstained analysis builds no envelope
(`InsufficientDataError`; the monthly job logs it) and regenerates nothing on
a shock (the current envelope stays as it is). Nothing scheduled retries a
withheld month-start envelope before the next month's run: only a restart's
self-heal, which checks each ticker's own store, regenerates a missing
envelope. Until then that ticker's reviews return `no_envelope` and its ADDs
stay blocked. **Planned:** a same-month retry (SA-036), and immutable
issuance identity so that revised knowledge never replaces the earlier
decision's evidence (SA-013).

### Daily review walkthrough

1. The scheduler selects the previous exchange trading session.
2. Daily review finds its envelope row and obtains the actual close, including
   the configured verification path.
3. It checks the row's provenance, the ticker's identity and the close (below).
   In `enforce` mode the first failure ends the review.
4. It computes price error and the current direction label. Some small,
   correct misses skip a fresh analyst run.
5. Otherwise it may rerun analysis, and that run must be actionable too. With
   hard-bind enabled, current code can grade the old outcome against the fresh
   report's verdict.
6. Feedback classifies misses and attributes them to dimensions. In `adapt`
   mode weights change; in `observe` mode the change is recorded as a
   proposal. Lessons and other learning state are updated.
7. Conditional thesis review, reforecasting, dossier curation and shared
   knowledge updates can run under their feature gates.
8. After harvesting reviews, the scheduler records one outcome per ticker
   (section 9) and invokes the portfolio pipeline.

### Review input checks

The review checks these inputs, in order, before it writes anything:

- the graded row came from an actionable analysis (not `abstain`, not unknown);
- **identity:** the ticker's identity on the review session is resolved, and
  the row's price basis is the session's. A stamped row names its basis. For
  an unstamped row, the registry is asked whether a demerger or relisting lies
  between the envelope's issue date and the session; a rename does not break
  the basis;
- the actual close is from the bar dated the review session. The close
  fetchers fall back to the newest earlier bar when the session has none (a
  suspended symbol, a provider lag), and the result names the bar it came
  from. A download that holds a single bar, as on a listing day, is read like
  any other;
- the fresh re-run, when one happens, is actionable.

In `enforce` mode the first failure ends the review as `data_gated`: no
grading, FeedbackAgent call, weight update or observe-mode proposal, lesson,
envelope revision, streak, feedback entry, dossier or control-lane step. The
skip is recorded with its stage, reason and source run id. The market-wide
sticky regime, updated at the start of every review, is the one write that
still happens. In `record` mode the review runs and its summary lists what
enforcement would have stopped. The scheduler counts a `data_gated` review on
its own (section 9).

**Example (identity):** a row issued on 5 June predicts a parent's close, and
the parent demerges on 15 June. From then on the ticker's close is the
continuing company's alone, so a review on 20 June would grade a "fall" that
is really the spin-off. The review stops at `identity`.

**Example (stale close):** a symbol is suspended on the review day, and both
providers return the previous day's close of 99.0. Graded, that is a flat day,
a zero return that never happened. The close says it is from the previous
day's bar, and enforcement skips the review.

**Known limit (planned for SA-012):** when NSE has not yet listed the session
and yfinance's session close differs from NSE's latest row by more than 1%,
the cross-check prefers NSE's earlier close. That close is marked stale, not
graded.

### Grading defect: an example everyone can follow

Suppose the issue-time close was 100, the predicted close 110 and the observed
close 105. The stock rose **5%**, but undershot its forecast by **4.55%**.
Current `classify_direction(actual, predicted)` compares against the forecast
and labels this DOWN. That measures error direction, not investment direction.
A new verdict computed after observing the outcome can also become the graded
verdict. Label definition and issue-time information are separate problems.

Existing tests can describe those code paths without establishing the desired
financial contract. **Planned:** SA-012 defines the target; SA-013 and SA-014
freeze and grade the information available when the decision was issued.

### What adaptation means here

Weights, accuracy history, lessons and dossier records change over time.
Regime and lesson modifiers affect research inputs. This is an adaptive
feedback system; it does not demonstrate that adaptation beats a fixed policy.
The audit also reproduced final weight-bound violations and repeated ensemble
trend counts presented under different agent names.

Unconstrained, the adapter drove chart weights toward zero. The
[2026-09-24 baseline](planning/PI-2026-09/evidence/SA-039-baseline-2026-09-24.md)
found `technical` at 0.0 for 5 of the 6 tickers that have that agent; the
defaults are 0.12 in the generic graph and 0.10 in the renewable graph.
Counting `pattern_analysis`, the chart agent of the other graphs, 9 of 18
tickers had a chart weight of 0.0 and 16 of 18 were below half their default.
All 19 reviews that day wrote a new weight version.

### Learning mode

`rl.learning_mode` has two values. `adapt` lets the review update live weights
on every eligible review, as described above. `observe` contains learning:

- Forecasts, re-forecasts, public analysis, and the review's re-scoring and
  forecast revision aggregate with the sector's configured default table (the
  table a ticker with no learning state gets), whatever the file stores.
- The review never writes adapted weights; a missing weight file is still
  created from the defaults at version 0, as in `adapt`. The adapter runs on a
  copy, and its would-be weights, deltas and reason go to
  `<TICKER>_weight_observations.json`, one record per review date.
- Tagged-lesson emphasis and the older category micro-adjustment stop moving
  agent scores. Lessons are still recorded, and `claims_fired` stays empty
  because no claim acted.

**Example:** a ticker stores `technical = 0.0` at v41. In `observe` mode its
forecast uses 0.12; after the review the file still says 0.0 at v41, and the
observation record shows what v42 would have been. Switching back to `adapt`
resumes the stored weights unchanged.

An unrecognised value fails closed to `observe` with a warning. The mode is
shown in the review's start and completion log lines, on each envelope
(`learning_mode`), and by `/ui/rl/weights/{ticker}` (with the live
`decision_weights`) and `/ui/rl/summary/{ticker}`. The paper lane never trains
or writes weights, and the absurd-price-error guard skips the adapter; like
every other decision path, the paper lane uses the sector defaults in
`observe`. The mode does not contain regime multipliers, thesis multipliers,
the conviction streak, miss-counter prompt enhancements or dossier text.

Production runs `observe` (section 1). Rollback is deleting the Railway
variable. In this mode each night re-proposes one step from the frozen stored
file, so the observation records do not accumulate into a learner.
**Planned:** a shadow learner, and the conditions under which learning may
return to `adapt` (section 11).

### Company knowledge

Event ingestion adds company observations; the curator maintains knowledge
and questions; the research job attempts answers. These are knowledge tasks,
not trades. Discovery paper tracking uses a separate store root with learning
writes disabled for that lane; it is not live investor performance.

**Dates.** No writer dates a dossier row after the run that wrote it. Event
ingestion dates rows with the event's day, and skips an event dated after the
scan, such as a board meeting announced for later in the month, until a scan
on or after that date. The digest the agents read leaves out observations and
open guidance dated after its own date; stored rows are not rewritten. Older
rows can still carry a future date: on 7 Oct two production dossiers held 3
observations and 1 guidance item dated 24 and 27 Oct
([probe](planning/PI-2026-09/evidence/FIX-004-probe-2026-10-06.md)).

Open guidance is read through one rule, the dossier's `open_guidance(as_of)`:
open items dated on or before `as_of`, in stored order. The digest lists the
last 5. The morning brief's earnings-watch line takes the last item as of the
day before the brief's date. The brief goes out at 08:50. The curator runs
inside the 16:30 review and research on Saturdays. Event ingestion runs on
Saturdays and, for a stock with a new results or concall filing, in the
company-event feed's 08:15 and 18:30 runs (section 4). So a row dated the
brief's own day is either an old future-dated one or a filing made that
morning, and the brief's earnings window includes the meeting day.

**Example:** a held stock has results on Tue 27 Oct. Its dossier holds open
guidance dated 15 Sep and an old item dated 27 Oct. The briefs of Mon 26 and
Tue 27 Oct, the two in the 3-day earnings window, both show the 15 Sep item.
The cost of the rule: guidance from a results filing made before 08:15 on the
brief's day, or new guidance seen by a brief triggered by hand after the 16:30
review, reaches the earnings-watch line the next day.

## 6. Portfolio: advice and virtual execution

**Trace:** [pipeline](../core/portfolio/pipeline.py) →
[advisor](../core/portfolio/advisor.py) → [executor](../core/portfolio/autopilot.py)
→ [store](../core/portfolio/store.py) → [digest](../core/portfolio/digest.py).

The pipeline loads active users' portfolios, obtains closes and signals,
evaluates held positions, records advice and optionally executes it.
The LLM narrates the rule-driven decision; triggers remain available when
narration fails. The [narrator](../core/portfolio/narrator.py) is given the
verdict, symbol, close, regime label and rule codes only, on the bulk tier,
so its text can restate the rule but not the company's facts. **Planned:** an
investment case recorded per holding (PR-005) and explanations grounded in it
and in the company events of section 4 (PR-007).

| Research verdict | Portfolio action |
|---|---|
| STRONG BUY, BUY, NEUTRAL, SELL, STRONG SELL | ADD, HOLD, TRIM, EXIT, SWITCH |
| Assessment of a stock at analysis time | Action for an existing holding, using entry cost, risk, position size and evidence |

A BUY report does not automatically purchase shares. A portfolio HOLD does
not mean a flat forecast.

### Advisor precedence

The cascade is **EXIT → TRIM → ADD → HOLD**. EXIT includes stop breach,
the acting exit rule's reason test (below), shock and crisis conditions and an
armed trailing stop.
TRIM considers profit with declining confidence/reversion. ADD requires
bullish, sufficiently healthy conditions and position headroom: the holding
below `advisor.max_position_pct` (10%) of total equity (see "Sizing every
buy" below). EXIT may
become SWITCH when an eligible replacement exists. A holding-age rule can
soften certain TRIM actions to HOLD; it does not override EXIT. These are
product rules, not individualized tax or investment advice.

### Two exit rules

Two rules can sell a holding whose reason to own may have gone, and
`advisor.exit_rule` decides which one acts. The rest of the cascade, the stops
included, is the same code under both
([advisor](../core/portfolio/advisor.py), [exit_shadow](../core/portfolio/exit_shadow.py)).

- **The price-path rule (`thesis_break`)** needs two things: the month's latest
  thesis review said "not intact", and the remaining forecast path ends more
  than 1% below the close. That review runs in the daily review (section 5,
  step 7) only after a price-path miss larger than `max(1.5%, 1.5 × ATR%)`
  ([thesis_reviewer](../core/intelligence/rl/agents/thesis_reviewer.py)), and
  it fetches no new data. A company event therefore never triggers it, while
  one sharp down day can.
- **The evidence rule (`case_broken`)** needs one of three things, as of the
  review day:
  1. a high-materiality negative company event about the stock (section 4),
     published in the last 5 sessions, from an NSE filing (an announcement or
     a board-meeting intimation) or from a disclosure typed by fixed rules (an
     insider trade, a pledge, a substantial acquisition, an ownership change);
  2. the latest analysis in the score history with an actionable or degraded
     gate says SELL or STRONG SELL, run on a later IST day than the buy and at
     most 22 sessions before the review day;
  3. the close is at or below the invalidation level of the stock's latest
     shelf idea, where the entry rule refuses to buy, compared in the close's
     own price basis (below).

  It fires only once the holding has been held `advisor.min_hold_sessions`
  (10) exchange sessions; the stops never wait. An event published after the
  review day, another company's event, an event with no publication time, an
  analysis run after the review day, an abstained analysis, and an analysis
  run on or before the buy day never count. A news article never sells on its
  own: it is a secondary report, and one mislabelled headline would sell a
  holding. A high-negative news event is recorded in the row as a watch item
  instead, and the stops still protect the position. An NSE filing's direction
  and materiality are the same bulk-tier model's reading (section 4); only the
  disclosures are typed by fixed rules. A filing may sell because it is the
  company's own primary disclosure, so a routine filing the model labels high
  negative still sells. **Planned:** PR-012's label-accuracy bench measures
  that reading (no routine filing may read as high negative); with an
  investment case, only an event that
  contradicts one of its pillars, and the case's own invalidation price; a
  news event can then mark a pillar challenged, never sell (PR-005).

**Example: a fresh verdict.** A stock is added by hand on 8 October although
its analysis of 24 September said SELL. On 23 October, ten sessions later, the
evidence rule keeps it: that SELL was known when the stock was bought. A SELL
from an analysis on 9 October would sell it, until that analysis is 22
sessions old or a newer one says otherwise. Every held stock is managed, and
the 1st-of-month forecast re-analyses each managed stock, so a holding has a
fresh verdict each month.

**Example.** A stock is bought at ₹500 for its order book. On day 4 the market
falls 2% and the stock 4%, to ₹480. The miss triggers a review, the review
says "not intact", and the re-forecast path ends at ₹470, so the price-path
rule EXITs at a 4% loss. The evidence rule finds no negative event, a BUY as
the latest analysis, ₹480 above the ₹455 invalidation level and 4 sessions
held, so it HOLDs. A path ending at ₹478 would not have fired the price-path
rule: that is within 1% of ₹480.

**The invalidation level's price basis.** The level is a rupee price set from
the deep dive's close. A bonus or split changes what a rupee of price means: a
1:1 bonus halves the share price. So the level is divided by the ratio of every
bonus or split that went ex after the dive and on or before the review day
(`level_in_basis`). The ratios come from two records, each for its own days:

- after the buy, the holding's applied actions: the record its cost basis and
  the stops use, written by the corp-action sync, which runs first;
- from the dive day to the buy day, NSE's corporate-action list for the
  symbol, which the same sync fetches each review day. The holding has no
  record before its buy, so this list must reach back to the dive day: its
  earliest row, of any kind, must be on or before it.

When the basis cannot be established, the level is not used, and the row's
`gaps` say why: the list does not reach back to the dive (an empty list, NSE's
answer or a failed fetch, reads the same), a bonus or split went ex on the dive
day itself (the dive's close may be on either side of it), or NSE lists a split
or bonus row from the dive day on that is not read as a ratio of equity shares
(One price basis, below): one that cannot be parsed, a bonus of other
securities, a split in short words, or one row naming both a bonus and a split
(read as its bonus alone, a 1:1 bonus with a ₹10-to-₹2 split would halve the
level where the price fell to a tenth). The row keeps the level as dived
(`invalidation_level_at_dive`) beside the one used.

**Example.** A stock is dived at about ₹500, with the level ₹455, and bought at
₹500. A 1:1 bonus then goes ex. The sync makes the holding 20 shares at ₹250,
and the level is ₹227.50. A close of ₹245 (₹490 in the old shares, down 2%)
fires nothing. ₹225 (₹450, down 10%, inside a 12% stop) is at the level.

**Modes.**

- `legacy`: the price-path rule acts, and nothing is compared.
- `shadow`, the shipped setting: the price-path rule acts. Both verdicts, with
  the evidence rule's reasons and inputs (event ids, news watch items, the
  analysis and its run time, the invalidation level and its source, any source
  it could not read), go to `exit_shadow.jsonl`, one row per holding per review
  day; a re-run adds nothing. The row names the holding (symbol and buy date),
  the session the close came from and, on a disagreement, the decision's
  benchmark (below). The advice and trades are the price-path rule's, byte for
  byte.
- `evidence`: the evidence rule acts, and the price-path verdict is still
  recorded beside it.

**Decisions.** A disagreement is a row where exactly one rule sells the whole
position (EXIT or SWITCH). A holding is one **decision**: its first review day
of disagreement. From that day one rule has sold the holding and the other
kept it, so the two no longer hold the same position, and the holding's later
disagreeing days stay in the file without being counted again, whichever rule
they favour. A stock bought again later is a new holding. Example: a standing
SELL that the price-path rule ignores for 5 review days is one decision, not 5.

**Grading.** The weekly scorecard (section 7) grades each decision 10 and 30
sessions after the review day, from the close both rules saw, against where
the sale put the money. That benchmark is stored in the row on the decision
day, and grading reads it from there, never from the configuration:

- `cash` when the selling rule's verdict is a plain EXIT, whose proceeds wait
  in cash (Cash deployment, below), or a SWITCH whose buy leg the executor
  would refuse. The row is written before the autopilot runs, so the
  destination's close is checked then as the executor checks it before
  sizing: a close for the session; under `enforce`, the session's own bar and
  a resolved identity; a price inside the idea's entry band. It is graded on
  the stock's own return.
- `nifty` for a SWITCH whose buy leg lands: the proceeds bought another stock.
  It is graded on the excess over the Nifty, with the auditor's benchmark
  series read from the close's own session, so a carried-forward close is
  graded from the day of its bar.

**One price basis.** A bonus or split cuts the raw price by its ratio and
leaves the company's value alone. The stored close is the raw close of its
bar, so the horizon close is multiplied by the ratio of every bonus or split
that went ex after that bar and on or before the horizon close's own bar (an
ex day's close is already in the new shares) (`horizon_in_basis`). The ratios
come from NSE's corporate-action list for the symbol, read once per stock when
the scorecard runs, under the NSE code its close is read under (a registry
alias such as TVSMOTORS is listed as TVSMOTOR): a stock the acting rule sold has
no holding, and so no applied actions.

**Each row is read in full or not at all** (`corp_actions.action_record`). NSE
words one action many ways, so a row is judged by every word in it. It is a
ratio only when it is an equity bonus or a face-value split and every word is
known: "Bonus 1:3" is 4 shares for 3, and "Face Value Split (Sub-Division) -
From Rs 10/- Per Share To Rs 2/- Per Share" is 5 for 1. It leaves the basis
alone only when every word is one of a dividend, a meeting, a vote, a buy back,
interest or a redemption, or a registrar change, in the spellings NSE uses
("Interim Dividend - Rs 20 Per Share (Purpose Revised)"). Any other row is not
read: a bonus of preference shares, debentures or NCRPS ("Bonus Preference
Shares 21:1" is not 22 equity shares for one), a split in short words ("Fv Splt
Frm Rs 10 To Re 1"), a misspelt dividend, or wording never seen before. A row is
neutral only when it is known to be, so a new wording can cost a decision its
result but never decides one.

When the basis cannot be established, the decision has **no result** at that
horizon that week, and the scorecard line names the stock. Each gap is one of
two kinds, and the switch gate (below) treats them differently.

**Lasting: no later read can change it.**

- NSE's list was read and is empty (NSE lists nothing for the symbol), or its
  earliest row is after the decision's close, so a bonus, split or demerger
  between cannot be ruled out;
- a bonus or split went ex after the close's bar and by the review day, so the
  stored close may be on either side of it;
- NSE lists, after the close and by the horizon close's bar, a split or bonus
  row that is not read as a ratio of equity shares (or one row naming both a
  bonus and a split), or two ratios for one day;
- NSE lists, after the close's bar and by the horizon close's bar or the review
  day, a change that no ratio in its row converts: a demerger (part of the
  company's value leaves for another listing, and NSE's row says only
  "Demerger"), a scheme of arrangement, amalgamation or merger (also "Sch Of
  Arrang" and "Arangement"), a consolidation, a capital reduction or return of
  capital, a rights issue (also "Rhs"), or a row of no known kind;
- the instrument registry records a new price basis for the symbol between the
  decision's close and the horizon's day (a demerger or a relisting, section 4),
  which NSE's list may not show; a rename keeps the basis and is graded.

**Temporary: a later week's read may resolve it.**

- NSE's list could not be read (no client, a failed request, an answer of no
  known shape), or it holds rows but none with an ex-date. Grading reads the
  list with `read_corp_actions`, which raises on a failed read and returns
  `[]` only for an empty answer; the holding sync's `fetch_corp_actions` still
  returns `[]` for both;
- the horizon close is missing, undated or older than the decision's close,
  or the row names no benchmark;
- the horizon close is Yahoo's alone (NSE's did not answer) and a bonus, split
  or one of those changes went ex after its bar: Yahoo's series is adjusted
  for every action up to the day it is read, and NSE's raw close would be
  graded.

The checks run in a fixed order and the first cause found names the gap: the
close (present, dated, not older than the decision's close), then whether
NSE's list was read, then the list's rows. So a decision is found lasting only
on a close and a list that were both read.

**Example: a bonus after a decision.** The evidence rule sells a stock at ₹190
on Friday 23 October as a plain EXIT, and the price-path rule keeps it. A 1:1
bonus goes ex on Wednesday 28 October; the company's value does not change,
and the horizon close is ₹95. That is ₹190 in the old shares: a return of 0,
so the sale saved nothing and was wrong, with a result of 0. Read without the
basis it would be a 50% fall and a result of +50; one such bonus would let the
failing example below (right on 8 of 15, −3.6%) pass the gate.

**Example: a demerger after a decision.** The same sale, but on 28 October 40%
of the company's value is demerged into a new listing, and the horizon close is
₹114. The stock is flat in real terms, yet read as prices it fell 40%, a result
of +40. NSE's row gives no fraction, so the decision has no result at either
horizon, for good: the switch gate sets it aside, and the scorecard names it.

**Example: a bonus of other securities.** The evidence rule keeps a stock at
₹280 that the price-path rule sold. Three sessions later the company issues 21
bonus preference shares of ₹1 for each equity share, worded as ZEEL's 2014 row
"Bonus Preference Shares 21:1". The equity trades at ₹259 and the number of
equity shares does not change. Read as a 22-for-1 equity bonus, ₹259 would be
₹5,698 in the old shares: a +1,935% keep, which alone would pass the money
check against a hundred honest decisions. The row names preference shares, so
it is not read, and the decision has no result.

The evidence rule was right if it sold and the stock then fell short of the
benchmark, or kept it and the stock did not. Its **result** is that gap:
positive when it kept the stock, negative when it sold. A horizon that has not
ended is pending, never scored. A sold stock stays in the count, and a row
without a benchmark is never graded. **Planned:** once cash deployment is on
for a portfolio, its plain EXITs record `nifty` as well; stored rows keep
theirs (SA-049).

**Example.** The stock falls 3% and the Nifty 5%. After a plain EXIT, selling
saved 3%: the evidence rule that sold was right, with a result of +3. After a
SWITCH the money went into a market that lost 5%, so keeping the stock was 2
points better: wrong, −2.

**The switch gate** is fixed in code, set before any row existed. It looks at
the decisions whose 30 sessions have ended.

- **Set aside, named.** A decision with a lasting gap (above) at 10 sessions,
  at 30 or at both can never be graded, so it is set aside at both horizons.
  The look stores each one with its stock, decision day and reason, and the
  scorecard line names it: "Set aside, as its result can never be known: XYZ,
  decided 2026-11-03: NSE lists a demerger ex 2026-11-12, …". The gate judges
  the rest.
- **A temporary gap never helps.** A judged decision with no result at a
  horizon counts as not right, and its result is unknown, so the money check
  at that horizon fails that week: no stand-in value could be guaranteed not
  to flatter the evidence rule.
- **A cap.** At most 2 decisions, and at most 10% of those past 30 sessions,
  may be set aside. Beyond the cap a look that would pass reads **cannot
  judge** instead; a look that fails or has too few keeps that status.
  "Cannot judge" is never a pass, so it breaks the two-week run.

| Condition | Required |
|---|---|
| Decisions past 30 sessions, not counting those set aside | at least 15 |
| Span of their review days | at least 8 weeks |
| Evidence rule right | at least 50%, at 10 sessions and at 30 |
| Its mean result | at least 0, at 10 sessions and at 30 |
| One stock's share of them | at most 30% |
| Decisions set aside | at most 2, and at most 10% of those past 30 sessions |
| Weekly looks that pass | 2 in a row |

**Why set aside, and why a cap** (the owner's decision of 29 October 2026). The
population has no window, so without setting aside one decision whose result
can never be known would fail the money check every week from then on: a sale
of a stock that demerges three sessions later would block the gate for good,
whatever the other 19 decisions showed. Setting a decision aside can help the
evidence rule (it might have been a wrong one), so the cap bounds how much.
Examples, each judged population right on at least 50% with a mean of about
+0.8% at both horizons:

| Decisions past 30 sessions | Set aside | The gate |
|---|---|---|
| 15 graded + 1 demerger | 1 of 16 (6%) | judged on 15: passes, "not worse" |
| 15 graded + 2 set aside | 2 of 17 (12%) | cannot judge (above 10%) |
| 18 graded + 2 set aside | 2 of 20 (10%) | judged on 18: passes |
| 14 graded + 1 set aside | 1 of 15 | not yet (14 of the 15 it needs) |
| 15 graded + 1 set aside + 1 with no NSE close this Sunday | 1 of 17 | fails this week |
| 17, 27 or 47 graded + 3 set aside | 3 | cannot judge (more than 2) |

**What a pass means: not worse.** Counting hits alone can pass a rule that
loses money: right on 8 of 15, where the 8 saved 2% each and the 7 wrong ones
cost 10% each, is (8 × 2 − 7 × 10) / 15 = −3.6% a decision, and the money
check fails it. Right on half is also what a rule with no skill reaches about
half the time. So a pass says the evidence rule is no worse than the
price-path rule in count and in money, and the switch is recommended on that,
because the evidence rule is simpler and explains itself (the owner's
decision of 24 October 2026). The scorecard adds the label **better** when a
pass is also right on at least 70% at both horizons with a positive mean (11
of 15, unlikely by chance); the label changes nothing.

**When it can first pass** (arithmetic, not a measurement): at two new
decisions a week, about 15 weeks after the shadow starts (the 8-week span, 6
weeks for the last decision to reach 30 sessions, one more look); at one a
week, about 21 weeks (14 weeks to reach 15 decisions, then 6 and 1).

**Why two horizons.** The production baseline in the
[product results review](audit/2026-10-11-product-results-review.md) (its
section 11) found the auditor's exits right at 10 sessions (7 of 10: the stock
kept falling) and wrong at 30 (6 of 7 sold stocks then beat the Nifty). One
horizon would flatter one rule. The scorecard recommends; the owner switches
(`advisor.exit_rule: evidence`), and `legacy` is the rollback. A result of
"no difference" is valid too; the owner may then still choose the simpler
rule. **Planned, after a switch:** the price-path verdict stays recorded for
one month, then the thesis-review exit path is retired (PR-009's rollout).

**Planned:** PR-013 adds the average loss by exit reason, the fall the evidence rule sits
through and the decision pace to the scorecard.

**Limits.**

- `shock_reforecast` compares the latest re-forecast's stored `reason`, which
  is a sentence ("pre-open shock: …"), with trigger keys such as
  `preopen_shock`, so it never fires under either rule. The key is in the
  event's `trigger` field. **Planned:** FIX-015.
- A holding bought from a watchlist BUY has no stored shelf idea, so the
  invalidation test cannot fire for it.
- For a holding dived before its buy, the invalidation test needs NSE's list to
  reach back to the dive day. The sync asks NSE for the symbol's actions
  without dates, and NSE returns its latest 20 actions of any kind, which for
  a large company reaches back years (12 symbols read in October 2026). The
  level is unused when the stock's earliest listed action is after the dive,
  or it has none, and each row's `gaps` says so.
- The level follows bonuses and splits only. A demerger, a capital reduction,
  a rights issue or a row of no known kind that goes ex between the dive and
  the buy lowers the price but not the level, so the test fires early: dived
  at ₹500 with the level ₹455, a demerger takes the price to ₹470, the stock is
  bought there, and a 3.2% fall to ₹455 is at the level. The entry rule reads
  the same unadjusted level; after the buy, the identity hold covers a
  registered demerger. **Planned:** PR-005.
- Under `evidence`, a sale's alert and narrative name the three kinds of reason,
  not the one that fired; `exit_shadow.jsonl` has it. **Planned:** PR-007.
- The TRIM-to-HOLD tax softening still reads the thesis review under both
  rules.
- Each Sunday the scorecard fetches every graded decision's closes again, and
  NSE's corporate-action list once per stock. A past close is cached for the
  rest of that process when it is that day's own bar in NSE's raw basis, but
  the run grows with the number of decisions.
- A decision whose close stays missing (a stock suspended or delisted after
  the decision) is a temporary gap: it fails the money check every week for
  as long as it is missing; the scorecard line names how many have no price,
  and nothing substitutes a value for it. When the instrument registry
  records the stock's new basis, its close is read under the new code, and
  once it is read the decision is set aside.
- The population has no window, so a decision set aside stays set aside, and
  beyond the cap the gate cannot judge for as long as those decisions stay in
  it. With 15 to 19 decisions past 30 sessions, 2 set aside is already above
  10%. The common lasting gaps: a stock NSE lists no corporate action for at
  all (on 30 October 2026, 4 of the 202 configured symbols with a price:
  AAVAS, IDEAFORGE, STARHEALTH and ZOMATO, which is ETERNAL on NSE; 5 codes
  without a price have an empty list too and carry no decision, section 4),
  one with a bonus or split ex
  between its close's bar and its review day (a carried-forward close on the
  ex day), or one with a row between its two closes that is a change no ratio
  converts or is not read. An empty list is taken as lasting although NSE
  could list a row later. NSE's lists for the 202 configured symbols, read under
  NSE's codes on 29 October 2026 (3,215 rows, each list its latest 20 actions or
  fewer), held 3,011 neutral rows and 110 ratios; 50 changes no ratio converts
  (14 demergers, 27 rights issues, 9 schemes, 5 of those naming a bonus of
  debentures or NCRPS); 8 more bonus or split rows not read as ratios; 27 rows
  of no known kind; and 9 undated rows. Every row not read is from 2008 to
  2021, mostly misspelt dividends, except TVSMOTOR's "Scheme Of Arrangement -
  Bonus Ncrps 4:1" of August 2025. Of the 849 rows dated from 2024, none was of
  no known kind.
- The evidence rule reads NSE filings, so it may sell on a scheme or demerger
  announcement, the very event that later sets the decision aside: a sale it
  made can leave the count that way. Which decisions are set aside depends
  only on the stock's prices, NSE's list and the registry, never on which rule
  sold, and the cap is the only bound on how often this helps.
- A row without an ex-date is not read. NSE listed 9 on 29 October 2026:
  interest payments, a nil dividend, INOXLEISUR's "Merger" and NIIT's
  "Agm/Div-50%/Sch Of Arrang". Whether NSE dates such a row once it goes ex was
  not measured, so a change listed only undated between a decision's closes
  would be graded across. The instrument registry (section 4) is where a
  merger's or a demerger's new basis is recorded, and grading asks it.
- The return leaves out a dividend that went ex in the window (often 1–2%),
  which slightly favours a sale over keeping.
- A SWITCH whose buy leg the executor skips for a reason the row's check does
  not see is graded against the Nifty, though the money stayed in cash: the
  executor's own re-fetch of the destination's close fails, the buy comes to
  under one share after sizing, or it is already in the ledger. The SELL's
  note names the skip.
- A holding whose monthly re-analysis did not run has no research verdict
  after 22 sessions; events, the invalidation level and the stops still apply.

### Data and identity checks on advice

**New risk needs verified evidence.** ADD and a SWITCH's buy leg add risk, so
in `enforce` mode they need two things: the holding's close must be from the
review session's own bar, and the forecast rows behind the signal must come
from an actionable analysis. A blocked ADD becomes HOLD. A blocked SWITCH
destination falls back to the next eligible idea, or to a plain EXIT. A shelf
idea without gate provenance, from an abstained deep dive, or priced from an
earlier bar is not a destination. Either way the advice gains the note
`DATA_GATE` and a `data_gate` record (what was withheld, why, and the source
forecast runs). That record is on the user's own advice ledger; the shared
gate log never holds a user id. EXIT and TRIM are never blocked by data:
missing data must not trap a position. When they rest on a stale close or an
unverified forecast, the advice records that. In `record` mode the decision is
unchanged and `data_gate` says what enforcement would have withheld.

**Example:** a holding's envelope was built on an abstained STRONG BUY and
points up. Unenforced, that gives ADD and a virtual buy of 2 shares. Enforced,
it gives HOLD with `DATA_GATE`, and no buy.

**Identity hold.** A holding is held outright, EXIT and TRIM included, with
the note `IDENTITY`, in two cases:

- its symbol's identity is unresolved;
- its price basis changed (a demerger or a relisting) since the basis its cost
  was booked on: the buy date, or the latest identity reconciliation.

This is the corporate-action rule applied to identity. The daily sync keeps a
1:1 bonus from looking like a 50% crash, and a demerger is the same trap. A
SWITCH destination or an autopilot buy leg with an unresolved identity is
refused.

**Example:** 100 PARENT bought at ₹1,000; PARENT demerges into PARENTA (60% of
the cost) and PARENTB (40%), and the ticker now trades as PARENTA at ₹600.
Unreconciled, 600 against 1,000 reads −40%, a stop breach, and the advisor
says EXIT, a sale on a loss that never happened. Enforced, it says HOLD with
`IDENTITY`; in `record` it keeps EXIT, and `data_gate` names the identity. A
rename keeps the basis, so a renamed holding is advised as before. Every advice
record also keeps the instrument its close priced (`instrument`), which a later
registry change does not rewrite.

### Identity reconciliation

Reconciliation is an operator's step
([identity_reconcile](../core/portfolio/identity_reconcile.py)).
`python -m core.portfolio.identity_reconcile plan` is read-only. It lists every
held position the advisor would hold, with the registry's proposal. The
proposal comes from a recorded, evidenced event with `successors` (ticker,
shares per old share, share of the cost), or it says what must be recorded
first. For the example it proposes PARENTA 100 @ ₹600 (₹60,000) and PARENTB
100 @ ₹400 (₹40,000), so the cost is conserved.
`apply --plan … --approve <digest>` has these safeguards:

- it refuses unless a fresh plan has the approved digest, so nothing changed
  since review;
- it copies `portfolio.json` aside before writing;
- it replaces the old holding with its successors under the user's lock, and
  logs `identity_reconciliations.jsonl`;
- a second apply is refused.

The ledger reconciler treats the successors as `unverifiable`, as after a
split. Nothing runs this on a schedule.

**Known limits of `apply`.** Its digest check runs before it takes each
user's lock, and under the lock it does not look at the holding again. So a
sale of the same holding in that short window still gets successors sized
from the plan's figures: 50 PARENT left would become 100 PARENTA and 100
PARENTB. Also, one apply names every backup with the same timestamp. For a
user with two reconciled holdings, the second copy overwrites the first, so
the only backup holds the half-applied portfolio; the audit log's `before`
records still hold each old holding. The shipped registry records no
`successors`, so `apply` applies nothing today. **Planned:** a fix for both
(SA-008 change 1). Until it lands, record no `successors` and run no `apply`
in production.

### Execution and persistence

The global gate, user's virtual-autopilot choice and cash-accounting state
all matter. Execution reloads the portfolio under a lock, sells before buying,
and uses transaction IDs plus a monotonic review-date marker. Future and
already-completed dates are rejected/skipped. Cash, sizing and eligibility can
prevent a recommended action from becoming a transaction.

Transactions are appended before saving holdings/cash. A crash in between can
leave the ledger ahead of the portfolio; deduplication is not an atomic
multi-file transaction. Reconciliation handles this gap. Each BUY and SELL
pays its trading costs (section 7), written on its own ledger row and taken
from cash with it, so the same transaction ID that stops a re-run trading
twice stops it charging twice. Corporate actions affect adjusted quantities
and cost. No broker-order execution path was found.
The executor re-checks a SWITCH buy leg before spending: in `enforce` mode
its close must be from the session's bar and its identity resolved, and in
every mode its price must sit inside the shelf idea's entry band (below). If
any check fails, the sell executes and the buy is skipped. The SELL's note
records why ("buy leg skipped: …; ₹2,27,000 stays in cash"), and the
`switch_buy_skipped` alert repeats that reason (when another switch that day
bought the same stock, only the SELL's note says why).

### Sizing every buy

[`core/portfolio/sizing.py`](../core/portfolio/sizing.py) holds one rule for every autopilot buy. Weights
are shares of **total equity**: every holding at the review's close (at
adjusted cost when it has none) plus deployable cash. The advisor's
ADD check, its notes, the executor's caps and the weekly review's allocation
all use this one denominator. A buy paid from cash leaves total equity
unchanged but for its trading costs, so the room under a cap is
`cap × equity − current value`.

A buy takes the smallest of four amounts:

- the amount asked for: the ADD tranche (25% of the position) or the SWITCH
  sale's proceeds, net of the sale's costs;
- the position's room under `advisor.max_position_pct` (10%);
- its sector's room under `advisor.max_sector_pct` (30%), summed across
  holdings with the same sector label;
- cash above `autopilot.min_cash_floor` (₹10,000).

Only whole shares are bought, so under one share means no buy. The buy's own
costs leave cash and equity too, so each limit is checked again after them
and a share at a time is dropped until all hold. What a cap leaves unspent
stays in cash, and the BUY's note names the limit and the amount. A manual add is the user's own choice and is not capped. Nothing is
force-sold: a holding already over a cap is left to the TRIM rules.

A SWITCH buy opens a position, so it must also sit inside its shelf idea's
band: at or below `entry_high` and above `invalidation_level`. Below
`entry_low` it is allowed (cheaper than planned), and the note says so. Above
the band, at or below invalidation, or with no shelf idea or band, it is
skipped with that reason. An ADD tops up a stock already held and is not
judged against an old shelf band.

Two notes mark weights over the caps: `POSITION_LARGE` (one holding over 10%)
and `SECTOR_CONCENTRATION_HIGH` (one sector's holdings together over 30%).
The weekly review lists each sector's share and the cash share, and flags a
sector over the cap.

**Example (the production shape of 11 Oct):** FEDERALBNK 406 at ₹330
(₹1,33,980), WELCORP 21 at ₹2,640.40 (₹55,448) and ₹8,09,297 cash make
₹9,98,725 of equity.

- FEDERALBNK is 13.4%, over the cap. It gets `POSITION_LARGE` and no ADD.
- WELCORP is 5.6%. A bullish, healthy WELCORP may ADD: its ₹13,862 tranche
  buys 5 shares.
- Measured against the holdings alone, they read 72.9% and 27.1%. Then no ADD
  could fire, and banking was noted as concentrated in a portfolio that was
  81% cash.

**Example (a switch):** in a ₹10 L portfolio, a ₹2.27 L holding is sold for a
shelf idea priced at ₹530, inside its band. The sale's costs (₹250.84) leave
₹2,26,749 of proceeds and ₹9,99,749 of equity, so the new position may be at
most ₹99,975: 188 shares (₹99,640, plus ₹118.68 of costs). The BUY's note
reads "capped by the 10% position cap: ₹1,27,109 of the ₹2,26,749 proceeds
stay in cash". Suppose
instead the idea was shelved at ₹1,817–₹1,911 and now trades at ₹2,553.60,
as WELCORP did on 1 Sep. Then nothing is bought, and the SELL says "33.6%
above entry band (₹1,817–₹1,911); needs a fresh deep dive".

### Cash deployment

The autopilot opens a new position only through a SWITCH. A plain EXIT's
proceeds, and whatever a cap or a skipped buy leg leaves, stay in cash, and
nothing reinvests them.

**Example (the owner's screen, 27 Sep):** ₹8,09,297 of ₹9,99,611 was cash
(81%), with two holdings. ACMESOLAR's `exit_full` alone moved about ₹2.27L to
cash.

**Planned:** in a normal market, idle cash goes into shelf ideas that pass the
checks, each sized by the rule above; cash is held on
purpose only in a crisis (SA-049, the owner's decision of 2026-09-27, behind a
switch that ships off). The deployment also works toward a configurable floor
of at least 10 holdings and ₹10 L invested (`portfolio.min_holdings`,
`portfolio.min_invested_inr`, with a per-portfolio override), recording why
whenever the floor cannot be met. The ideas come from the buy candidates of
section 8: fresh shelf ideas from a 20-idea, sector-capped shelf, and the
user's own watchlist BUYs.

## 7. Profit/loss and the different marksheets

“Marksheet” covers several distinct reports. Each needs its own question,
dates, denominator and exclusions.

### Virtual P/L

[portfolio_api.py](../services/api/routes/portfolio_api.py) exposes holdings,
transactions, advice, digest and `/portfolio/performance`.

| Measure | Meaning |
|---|---|
| Holding market value | Adjusted quantity × marked price. |
| Unrealized holding P/L | Adjusted quantity × (marked price − adjusted average cost). |
| Realized P/L | Ledger gain/loss on quantities actually sold virtually, before costs (`realized_pnl`). `realized` gives it gross, the costs those sales and the shares they sold paid, and net of costs. |
| Trading costs | What each BUY and SELL paid, on its ledger row and taken from cash (below). |
| Tax estimate | The capital-gains tax the sales would owe per financial year; shown, never taken from cash. |
| Total equity | Remaining holdings' market value + deployable cash. |
| Total return | `(total equity − capital_in) / capital_in`, when required values exist. |
| As-of date | Date of the valuation, potentially different from page-open time. |
| In stocks / Cash | Market value and deployable cash at the last valuation, each as a share of total equity, to one decimal. The cash share is rounded and the stock share is 100 minus it, so the two always add to 100. |

**Trading costs and the tax estimate.**
[costs.py](../core/portfolio/costs.py) charges every virtual BUY and SELL what
an NSE equity delivery trade pays at a zero-brokerage broker. The rates are in
`config.yaml` (`portfolio.costs`), each with its source and the date it was
checked:

| Charge | Basis | Rounding |
|---|---|---|
| STT | 0.1% of the buy and of the sale | value and tax to the rupee (STT Rules, rule 4) |
| Stamp duty | 0.015% of the buy | paisa |
| NSE transaction charge | 0.00307% of each side | paisa |
| SEBI fee | 0.0001% (₹10 a crore) of each side | paisa |
| GST | 18% of brokerage + NSE charge + SEBI fee | paisa |
| DP charge | ₹15.34 per scrip sold, GST included | — |
| Brokerage | 0 for delivery (a percentage and a per-order cap are configurable) | paisa |

The charges are written on the trade's own ledger row (`costs`, with the
`rates_as_of` they were charged at) and leave cash with it. So a rate change
never alters a past trade, and the transaction ID that stops a re-run trading
twice stops it charging twice. A manual add or CSV import moves no cash: its
buy charges go into `capital_in` with its cost, and the Nifty comparison takes
them in as money. A missing rate fails the trade rather than charging nothing.
A trade from before costs were charged has none recorded. It is read with
costs estimated at the configured rates and labelled "estimated", never as
free. Those costs were never taken from cash, so the performance view lists
them apart from the charged ones.

`realized_pnl` keeps its meaning, the price difference. Each sale's net result
subtracts its own charges and the share of its position's buy charges that the
sold shares carried: a sale of a quarter of the shares carries a quarter of the
pool, so a split in between changes nothing. Unrealized P/L stays the open
holdings' price gain: `total_pnl − realized_pnl + charged costs`.

The tax estimate (`portfolio.tax`) is per financial year, April to March, for
a resident individual:

- a sale's gain is its value less its charges and its shares' cost (the
  position's adjusted average) and their share of the buy charges; STT is not
  deductible;
- shares held 12 months or less, taken oldest purchase first, are short-term
  (20%); the rest are long-term (12.5% above ₹1,25,000, applied once a year);
- a short-term loss offsets short-term gains, then long-term gains; a
  long-term loss offsets long-term gains only;
- a 4% cess is added to the tax.

So a year that nets to a loss owes nothing, except when a long-term loss
exceeds a short-term gain: the law still taxes the short-term gain. Losses
carried to later years, surcharge and the basic-exemption shortfall are not
modelled. A sale with no purchase on record counts as short-term, the higher
rate, and is counted. The shares' cost is the position's average, while the
law takes each lot's own cost, oldest first (section 45(2A) of the 1961 Act).
So a sale that takes long-term and short-term shares bought at different
prices can read higher or lower than the law's figure. 200 shares bought at
₹1,500 more than a year earlier and 50 at ₹1,000 a month earlier, all sold at
₹1,400, read ₹0 where the law gives ₹4,160. **Planned:** FIX-022 takes each
lot at its own cost.

**Example (ACMESOLAR, the owner's screen of 27 Sep):** 509 shares bought at
₹372.88 (₹1,89,795.92) and sold at ₹446.65 (₹2,27,344.85).

- The buy pays STT ₹190, stamp ₹28.47, NSE ₹5.83, SEBI ₹0.19 and GST ₹1.08:
  ₹225.57.
- The sale pays STT ₹227, NSE ₹6.98, SEBI ₹0.23, GST ₹1.30 and DP ₹15.34:
  ₹250.85.
- The realized +₹37,548.93 is +₹37,072.51 net of the ₹476.42.
- The taxable gain is ₹37,489.51 (STT not deducted). 20% is ₹7,497.90, and
  the cess ₹299.92, so the tax is ₹7,797.82.
- About ₹29,275 is left in hand.

**The portfolio screen** answers "is this good?" as well as "how much?". With
cash accounting on, the hero shows "Capital added" (`capital_in`, the money put
in, which trades never move), "In stocks" and "Cash" with their shares, the
total return, "Realized P&L" net of costs (with the gain before costs and the
costs under it), the latest financial year's "Tax estimate" (marked not taken
from cash) and the valuation date ("Valued as of 6 Feb 2026"). The value
chart draws, dashed, what the same deposits would be worth in the Nifty 50,
and each range tab shows the range's money-weighted return beside the Nifty's.
Under the hero, "If this had been in the Nifty 50" gives the gap at the last
valuation in rupees and in points of return since the first deposit. All of
it comes from `/portfolio/performance`, which uses the weekly scorecard's
functions in [results.py](../core/portfolio/results.py) (`capital_flows`,
`vs_nifty`, `nifty_line`, `portfolio_vs_nifty`): one implementation.

- **Example (two deposits).** ₹10,00,000 arrives on 5 Jan with the Nifty at 100
  and buys 10,000 units. ₹2,00,000 arrives on 19 Jan at 125 and buys 1,600. On 6
  Feb the Nifty is 110, so the line reads 11,600 × 110 = ₹12,76,000. The
  portfolio, at ₹12,40,000, is ₹36,000 behind: +3.3% against +6.3% since 5 Jan,
  3.0 points.
- **Missing data.** The Nifty line is drawn only through points with a value. A
  day with no Nifty close leaves a gap; a deposit that cannot buy units ends the
  line there. An unavailable benchmark reads "unavailable", with no line and no
  gap.
- **One download.** The route preloads the Nifty for every value point's date
  in one request (`BenchmarkSeries.preload` in
  [benchmark.py](../core/audit/benchmark.py)). Each day gets the close the
  per-date lookup would choose: the session's own, else the last one before it
  within the walkback, never a later one. A range stays cached for an hour.
- **Closed trades.** A card shows the closed-trade record from the whole
  ledger (`closed_trades` and `trade_stats`, as in the scorecard): trades, win
  rate, average win, average loss and expectancy per trade, before costs. A
  partly sold position is not a closed trade.
- **Every price has its date.** The holdings table dates the current price by
  its bar (`last_close_date` from `GET /portfolio`) and the average cost by the
  first purchase. Each trade's price shows its trade date, and the agents'
  card names the review whose closes its reasons quote.
- **Every trade shows its costs**, in whole rupees: "costs ₹251", or "costs
  ₹15 (estimated)" for a trade from before costs were charged.
- **Without cash accounting** no deposit or sale is recorded, so the screen
  shows "Bought for" (the holdings' cost) and has no comparison or trade card.

**Example without fees/corporate actions:** start with 2,000 and buy ten units
at 100. Cash is 1,000. At 110 the holding is 1,100, equity 2,100 and unrealized
P/L 100. Sell four at 110: cash becomes 1,440, remaining holding value 660,
realized P/L 40 and remaining unrealized P/L 60. Equity stays 2,100.

`/portfolio/performance` reads every transaction and every value point; the
chart receives the last 400 points. "Total return" counts a holding added with
an earlier buy date from its cost, so it includes that stock's gain before it
arrived; the Nifty comparison does not (below).
With no history, a failed price lookup may fall back to adjusted purchase cost.
The digest sums priced holdings only, and its `portfolio_value` excludes cash.
These scope differences need interpretation; a displayed total is not proof
all prices are fresh or all history is included. Costs are charged and tax is
estimated, but the bid-ask spread, slippage and market impact are not
modelled, so these virtual results still do not establish executable net
returns.

### Report families

| Report | Present meaning | Limitation / planned work |
|---|---|---|
| RL Monitor / analytics | Envelope, feedback, miss and weight records, with the learning mode and live decision weights. | Inherits label/timing/history problems; SA-012–SA-017, SA-024. |
| Weekly results scorecard | One row per ISO week from the user's own ledgers: closed round trips, the auditor's grade of every advisor sale at 10 and 30 sessions, exit reasons, a money-weighted Nifty comparison, breadth, holding period and five predeclared red flags (below). | Closed-trade results are before costs; the portfolio screen's realized P/L is net of them. Forecast-suggestion cohorts are SA-019's. |
| Monthly scorecard | Agent/control/simple-baseline lanes and previous-month comparisons. | Completeness, timing and denominators need repair. SA-018. |
| Learning evidence | Retrospective adapted/base/uniform replay and lesson associations. | Not a prospective controlled experiment of the whole system. SA-020–SA-023. |
| Nightly advice auditor | Issued advice, alert, shelf, switch and IPO lanes; default 10/30/60 trading-session horizons, and 1/5/21/63/126/252 from listing on the IPO lane. | Separate from weekly heuristics and actual account P/L. IPO rows are excluded from the rendered report. |
| IPO history report | Subscription groups and issue-price returns at available horizons. | Descriptive associations with sample/feature gaps, not a validated prediction model. |

[Audit rules](../core/audit/rules.py) judge HOLD/ADD correct when excess return
over the benchmark is nonnegative, and TRIM/EXIT/SWITCH correct when negative.
The switch-pair lane separately asks whether destination beat origin over the
same dates; a tie does not establish benefit. An EXIT can score correctly while
the actual virtual trade realizes a loss: these measure different things.

The IPO lane ([grade_ipo_lane](../core/audit/outcomes.py)) grades the P3 IPO
verdicts under `is_ipo_correct`, a separate rule from the advice vocabulary.
Its entry price is the **issue price**, not a market close, and its horizons
count trading days from listing with horizon 1 being the listing day itself.
Only one row per issue can carry a True/False: the listing-day horizon, and
only when the verdict was taken after the book closed and its lean asserted a
direction. Every other horizon is recorded with `correct` unset, so it enters
no hit-rate. These rows are written to the same store and excluded from the
rendered audit report: the P3 model remains dark until its visibility gate is
met, and a displayed hit-rate would be that surface.

On a listing day a download holds one bar, and the close fetcher reads it
like any other. So the listing-day row, the one per issue that can carry a
mark, gets its close. A row that gets no close is not written, so the next
nightly run retries it. **Known limit (planned for SA-012):** the audit prices
every row through `close_on`, which returns the close without its bar's date.
When a provider lags, a close carried forward from an earlier bar is stored as
the session's. No bar precedes a listing, so the listing-day row is not
exposed.

**Example:** stock +5%, benchmark +8% means excess **−3 percentage points**.
HOLD is incorrect under that relative-return rule despite a positive stock
return. Every marksheet should identify its rule, horizon, matured sample
count, missing data and excluded cases.

### Weekly results scorecard

[results.py](../core/portfolio/results.py) answers, once a week and in plain
words, whether the portfolio is making money, whether its sales were good and
whether anything crossed a red line. The Sunday weekly review builds the row
for each user from that user's ledgers only, stores it once in
`weekly_scorecard.jsonl` and opens with it. `GET /portfolio/scorecard` returns
the caller's own rows. A run on a weekday covers the week before, so a
mid-week run never stores half a week. A stored week is never rewritten, and a
week whose sessions are not over is never stored.

| Line | Definition |
|---|---|
| Closed trades | Round trips from `transactions.jsonl`. A position counts once, when its last share is sold, with every sale of it (TRIMs included): realized P/L over the cost of the shares sold. Count, win rate, average win, average loss and expectancy (the mean result per trade), this week and since the start, before costs. A sale with no recorded cost is counted as unknown, never guessed. |
| Sold too early | Every advisor sale (EXIT, SWITCH or TRIM), held or not, joined to the auditor's grade by its advice ref: the share of sold stocks that beat the Nifty 10 and 30 sessions later. A sale whose horizon has not ended is pending; one whose horizon ended with no grade is counted as missing. |
| Why we sold | Sales per trigger, in the advisor's plain words, over the last 4 weeks. Your own sales appear as "sold by you". |
| You vs the Nifty | Money-weighted. Each rise in `capital_in` between value points is a deposit, dated at the first point that shows it, and the same deposit buys Nifty units at that day's close. Both sides use the same flows, so idle cash counts against the portfolio. A holding that arrived without cash is valued on the day it arrives (below). This week, the last 4 weeks and since the start. |
| Breadth | Holdings (for the latest week) and the invested share at the week's last valuation. |
| Holding period | Median exchange sessions held by the positions closed this week. |
| Idea quality | From the auditor's shelf lane: how many shelf ideas beat the Nifty 10 and 30 sessions after they were shelved, whether bought or not, with the median gap in points. Only grades matured by the week's end count. It measures the idea supply, not the portfolio, and it is a line, not a flag. |
| Exit rule test | From `exit_shadow.jsonl` (section 6): on how many decisions the price-path rule and the evidence rule disagreed (one per holding, on its first disagreeing day), in how many holding-days reviewed, and how many later days of the same disagreements were not counted; how often the evidence rule was right at 10 and 30 sessions and its mean result a decision against where the money went (how many against cash, how many against the Nifty), with the mean against the Nifty alone beside it; what is still pending, has no price, or has no result because a corporate action could not be ruled out or allowed for (naming those stocks); this week's look at the switch gate ("not worse" on a pass, plus "better" when it applies, or "cannot judge" when more decisions are set aside than the cap allows); and each decision set aside from the gate, with its decision day and why its result can never be known. The row stores the look, so the next week can tell whether the gate passed twice in a row. Shown once a row exists. |

**Holdings that arrive without cash.** "Add holding" and a CSV import, on an
account with cash accounting, raise `capital_in` by the holding's cost (the
quantity × the buy date's close or a typed price) and its buy charges, and
write a "manual" BUY row whose cash does not move. `capital_flows` finds those
rows and values each one at the stock's NSE close on the date of the first
value point that holds it, on both sides, so a stock's gain before it arrived
is not the portfolio's. The buy charges stay money in: the Nifty gets them
too, and the portfolio has to earn them back.

- **Example.** ₹10 L sits in cash while the Nifty goes 100 → 110 over four
  weeks. In the middle, with the Nifty at 105, 1,000 shares bought a year
  earlier at ₹50 and now worth ₹150 are added. Valued at ₹1,50,000, the four
  weeks read 0.0% against +9.3%, and "Behind the Nifty" fires. At their
  ₹50,000 cost they read +9.5% against +9.8%, and the flag stayed clear.
- **Which valuation holds it.** Each value point records `recorded_at`, and
  the pipeline writes it under the user's lock, as every add is written. A
  point recorded after the add's ledger time holds it. An add made after the
  16:30 review therefore arrives in the next valuation, at that day's close.
- **When it cannot be valued**, the flow is unknown: no close for the stock
  that day, or a point written before points recorded their time and dated
  the add's own day. A period that holds an unknown flow, or follows one with
  money moving in it, reads "could not check (…)", naming the stock and day.
  A period with no money moving is still compared, by the index's own move.
- **Deposits keep their dates.** Nightly retention keeps the last
  `value_history_cap` (400) points, the first point with a `capital_in`, and
  every older point where `capital_in` changed
  ([retention.py](../core/portfolio/retention.py)). Without them, the first
  kept point's capital would read as an opening deposit on a later day.
- **Limit.** A holding added while the 16:30 pipeline runs, or one whose close
  fails in that run, is in that day's valuation at its cost while the comparison
  values it at the day's close. Until the next valuation marks it to market,
  that day reads the difference, quantity × (close − cost), as a loss or a gain
  that is not the portfolio's. A weekly scorecard whose week ends on that
  valuation keeps it. Example: 1,000 shares bought at ₹50, worth ₹150 and added
  at 16:35 read ₹1,00,000 behind that day. **Planned:** SA-049.

The red flags are fixed constants in the module, set before any result was
seen. A flag reports; it changes no decision.

| Flag | Fires when |
|---|---|
| Money per trade | The since-start expectancy is below 0 at the end of each of the last 3 weeks. |
| Selling too early | More than 60% of sold stocks beat the Nifty over the next 30 sessions, among sales whose 30 sessions ended in the last 8 weeks, with at least 8 such sales. The 10-session share is shown beside it. |
| Selling on the price path | `thesis_break` caused more than 50% of the advisor's sales in the last 4 weeks. |
| Behind the Nifty | The portfolio is more than 3 points behind the same money in the Nifty over the last 4 weeks. |
| Selling too fast | The positions closed this week were held a median of under 10 sessions. |

Missing data never reads as clear. A flag fires only if it is crossed with
every missing member counted in the portfolio's favour. It reads clear only
if it holds with all of them counted against the portfolio. Otherwise the
email says "could not check", above everything but the red flags. A missing
Nifty close or a week with no valuation reads "unavailable", never a flat 0%.

**Example:** 10 sales reached 30 sessions in the last 8 weeks. After 4 the
stock beat the Nifty, after 3 it did not, and 3 have no grade. Skipping the 3
would read 4 of 7 (57%), clear. Counted as beating it they make 7 of 10 (70%);
counted as not, 4 of 10 (40%). The email says "Selling too early: could not
check … between 40% and 70%".

Horizons count exchange sessions on the NSE calendar, as the auditor's do.
Nifty closes come from the auditor's benchmark series, so the known limit
above on carried-forward closes applies. The nightly auditor grades the
default user's calls only. Members' sales are their own, so they appear under
"Why we sold" and are not graded.

## 8. Discovery and IPO functionality

### Discovery

[run_discovery_cycle](../core/discovery/__init__.py) connects EOD sync,
bulk/block activity, NSE's instrument listing, optional recent-IPO candidates,
shelf upkeep, screen, deep dives, conviction shelf and paper reviews. Failures
can degrade individual stages. The Saturday job and manual discovery endpoint
use this entry point. A shelf candidate, watchlist promotion and virtual
purchase are separate steps. A deep dive runs the ordinary analysis, so its
decision gate, including the identity check, is the shelf idea's `data_gate`.
In `enforce` a candidate with an unresolved identity is never shelved, nor
used as a SWITCH destination.

The shelf exists to supply enough checked, varied ideas to fill and keep about
12 holdings. The weekly run, in order:

1. **Instrument listing.** [bhavcopy.py](../services/data/fetchers/bhavcopy.py)
   reads the latest UDiFF bhavcopy from NSE's archive and caches each symbol's
   series and ISIN in `data/discovery/listing.json`. A failed fetch keeps the
   last good listing.
2. **Only companies.** [universe.py](../core/discovery/universe.py) reads a
   symbol's kind from its series and ISIN, never its name. An ISIN that begins
   `INE` is a company's shares. One that begins `INF` is a mutual-fund scheme's units: every
   ETF, index fund and liquid fund trades in the EQ series, so the series
   alone cannot tell. Series RR and IV are REIT and InvIT units. The screen
   ranks companies only. The deep dive makes no analyst call for any other
   kind, or for a symbol the listing does not know. With no listing at all,
   nothing is dived that week, and the run says why.
3. **Shelf upkeep.** An idea NSE lists as a fund, REIT or InvIT is dropped,
   with its series and ISIN in the reason. An idea without a market sector
   gets one (below).
4. **Re-dives first.** Ideas shelved before the decision gate existed (no
   `data_gate`) are re-dived first, then ideas whose latest dive is older than
   `discovery.redive_after_days` (30), oldest first. Re-dives take the budget
   first but leave the IPO slots free. A re-dive refreshes the idea in place:
   conviction, verdict, thesis, entry band, invalidation, gate and `dived`
   date. `added` and `close_at_add` stay, so the auditor's shelf grades keep
   their start. A re-dive whose analysis is not actionable, or whose
   conviction falls below the floor, drops the idea with the reason.
5. **Deep dives.** `discovery.deep_dive_count` (20) bounds the analyst calls
   a week: re-dives, IPO slots and screen ranks together, a failed call
   included. A screen or IPO candidate dived in the last 30 days and not on
   the shelf already has its answer (below the floor, abstained or
   outranked), so the dive memo (`dives.json`) keeps it from taking the
   budget again. The memo keeps every answered dive, an abstained one too,
   in either gate mode; a failed call is not an answer and is tried again.
6. **Shelf.** Up to `discovery.shelf_size` (20) active ideas at conviction
   0.55 or more, strongest first. Under the enforced data gate only an
   actionable or degraded dive becomes an idea; in `record` mode an abstained
   one is shelved, as the mode's "nothing withheld" says. At most `discovery.max_ideas_per_sector` (3)
   share a market sector. A newcomer to a full sector replaces that sector's
   weakest idea only if it is stronger, and the drop event says so. Otherwise,
   when the shelf is full, a stronger newcomer displaces the weakest idea.
   An idea whose latest dive is more than `stale_days` (60) old rotates out.
   The monthly re-dive is the check that matters, so an idea that keeps
   passing it stays, one that fails is dropped, and one that cannot be
   re-dived ages out. Example: an idea shelved on 5 Sep and re-dived on
   24 Oct stays past 4 Nov; without passing another re-dive it rotates out
   after 23 Dec.

**Screen signals.** The screen ([screen.py](../core/discovery/screen.py))
ranks every company on six signals by percentile and blends the ranks by
`discovery.signal_weights`: momentum 0.30, delivery surge 0.15, volume
breakout 0.15, bulk and block buying 0.15, nearness to the 52-week high with
relative strength 0.10, and insider buying 0.10. The weights are relative:
the blend is renormalised over the signals available that week. An
unavailable signal is left out and named in the screen's `dark_signals`, with
its reason in `degraded_checks`; it is never scored neutral. There is no
mutual-fund signal, because no source for it (monthly scheme portfolios) is
built, so it has no weight either.

**Insider buying** (`core/discovery/insider.py`) is the rupees
each company's promoter group and directors bought minus sold in the market
over the last `discovery.insider_window_days` (28), from every company's NSE
insider-trade filings (section 4). Each Saturday run lists the window's
filings and reads the XBRL of each filing not read before, at most
`discovery.insider_max_documents` (600) a run. It keeps each filing's trades,
without names, in `data/discovery/insider_trades.json`, and each company's
net. Each trade counts once, and only when its last trade day falls in the
window, so a trade counts for 28 days after it was made, not after it was
filed:

- NSE lists a corrected filing (a revision) as a new filing and rarely says
  which one it corrects. So filings are taken in the order NSE disseminated
  them. An original's trades are all kept, since two persons can make the
  same trade on the same day. Each trade of a revision replaces the closest
  earlier trade of the same company with the same action and share count;
  revisions correct values, days and categories, so those may differ. A
  revision's trade that matches none is new.
- So PATINTLOG's revision of 1 Oct, which repeats its original's two promoter
  trades, counts once (+₹71,214, 0.0071 crore). HTEL's revision of 6 Oct
  repeats its original's four purchases and adds a fifth: five trades. A
  revision disseminated on 8 Oct of NAUKRI's director sale of ₹68.0 crore,
  traded on 18 to 20 Aug, counts nothing in the 28 days to 23 Oct.
- A company whose promoters hold more than 75% must sell to keep 25%
  public, and section 4's event calls such a sale neutral. So for each
  company with a counted promoter-group market sale, the run reads the
  latest promoter share from NSE's shareholding list. Above 75%, those
  sales count nothing; directors' trades still count. When NSE gives no
  promoter share, the sale counts, as the event's does.

The signal is used only when every listed filing and every needed promoter
share was read, the list is at most 7 days old and not newer than the screen
day, and no more than a tenth of the documents were unreadable. A document
whose promoter or director market trade has no day is unreadable. Otherwise
a missed buyer would rank as a company nobody traded. Example: in the 28
days to 23 Oct NSE listed 351 filings for 177 companies. Promoters who bought
₹4.2 crore score 4.2, directors who sold ₹1.1 crore score -1.1, and a company
with no filing scores 0. A first run reads up to 600 documents, a few minutes
of NSE calls; later runs read only the new filings, and the promoter shares
again.

**Promoter pledge.** For each of the 80 shortlisted stocks, NSE's pledge data
gives the promoter shares pledged as a % of the promoter holding, at the
latest quarter filed. More than `discovery.max_promoter_pledge_pct` (25%)
rejects the stock (`promoter_pledge_high`): when the price falls, a lender
can sell pledged shares. A stock NSE has no row for, or more than one (the
rows name the company, not the symbol), or whose call failed, is kept and
recorded as `promoter_pledge:<SYMBOL>`. So is a stock whose row is for a
quarter that ended more than 200 days before the screen's latest session.
A quarter's pattern is due within 21 days of its end, so the latest due
quarter is at most about 112 days old, and 200 days allows one late quarter.
On 23 Oct a row for 30 Jun (115 days) is used and one for 31 Mar (206 days)
is not. With `discovery.pledge_guard` off or no NSE client, the screen
records the one check `promoter_pledge`. On 22 Oct NSE's list had 1,558
companies and 181 above 25%; A2Z Infra's promoters had pledged 99.68% of
their shares, Maruti's 0%. On 23 Oct, 93 of the 1,558 rows were for a
quarter before 30 Sep 2026, and 79 were more than 200 days old (10 from
before 2015). 35 of those 79 showed more than 25% pledged; such a stock is
kept as unknown, not rejected.

**Surveillance and suspension.** NSE's daily Surveillance Indicator report
([surveillance.py](../services/data/fetchers/surveillance.py);
`REG1_IND<ddmmyy>.csv` in NSE's archive) lists every security with its stage
under each surveillance measure ("100" means not under it) and its status,
"A" active or "S" suspended. The screen reads it once a run, dated on the
window's latest session or up to 7 days before it, never after, and caches it
in `data/discovery/surveillance.json`; a run fetches at most five days'
files. A shortlisted stock under GSM or long- or short-term ASM, at any
stage, is rejected (`surveillance_asm_gsm`), and one that is not active is
rejected (`suspended`). A stock the report does not list is kept and recorded
as `surveillance:<SYMBOL>`. With no report, the screen records the one check
`surveillance` and every stock passes those two gates. On 29 Oct 2026 the
report listed 3,216 securities: 74 under GSM, 143 under long-term ASM, 47
under short-term ASM and 16 suspended. Its members matched NSE's own ASM and
GSM lists of 30 Oct, a day later, but for 2 long-term ASM and 3 GSM symbols.
A2Z Infra was under long-term ASM stage I, so it is rejected; Maruti was
under no measure.

**One check per dark source.** A per-symbol source (the report's listing,
Yahoo's float, NSE's pledge rows) that answers for none of the stocks reaching
the per-symbol gates is recorded once, as `surveillance`, `float_mcap` or
`promoter_pledge`, not once per stock. The weekly run's summary lists such
run-wide checks as `dark_checks`, and the scheduler's Discovery log line
repeats them. The watchdog's `discovery_guard_sources_live` invariant
([checks.py](../core/ops/watchdog/checks.py)) is pending while one of these
sources has been dark in every screen for 7 days or more, which is two weekly
screens in a row, and tells the owner which gate has passed every stock. The
pledge source is not judged while `discovery.pledge_guard` is off. Example:
`surveillance` dark in the screens of 23 and 30 Oct warns; dark on 30 Oct
alone does not yet.

**Market sector.** Each idea carries `market_sector` and `industry` from
Yahoo Finance's classification (for example "Healthcare" and "Drug
Manufacturers - General"). The idea's `sector` field is a routing key, set by
the deep dive's `infer_sector` ([deep_dive.py](../core/discovery/deep_dive.py)):
the registry's ticker map, else that classification mapped to a registry
sector (an industry table, then the Yahoo sector for Healthcare, Financial
Services, Real Estate and Energy), else `generic`. Yahoo is the one industry
source because it answers for nearly every NSE company and tells an insurer
from a bank and a defence maker from other capital goods. NSE gives an
industry only in its index lists (750 companies), in coarser classes. Over the
registry's 202 tickers on 1 Nov, Yahoo classified 193 and the table agreed
with the curated map for 184 (BEL and HAL read `defence`, the map says
`capgoods`); the map still wins for its own tickers. Of 150 Nifty Total
Market companies outside the registry, sampled that day, 146 were classified
and 4 of those read `generic`.

The key picks the analysis graph: automobile, banking_bfsi, it_sector and
renewable_energy have native graphs, and every other key runs the generic
graph, so for those the key changes only the prediction-store directory and
the sector ledger. After a buy it is the holding's `sector`: the advisor
reads the holding's predictions under it, and SA-050's sector cap counts it.
The daily review and the monthly forecast write a managed stock's predictions
under its managed-ticker record's sector, which promotion keeps once it
exists. So a buy candidate carries its managed record's sector when the stock
is managed (below), and the deep dive skips managed stocks. A re-dive
refreshes an idea's `market_sector` and `industry` but never its `sector`, so
an idea keeps the sector it was shelved under, `generic` included, and with
it its paper-lane store. Re-keying an existing `sector` belongs to the
sector-lens work (SA-026). The shelf's cap counts `market_sector`. An idea
with no known market sector is not capped, rather than lumped with other
unknowns.

**Example.** A week's best dives include four Healthcare ideas at 0.80, 0.70,
0.65 and 0.60. The first three take the sector's places and 0.60 is turned
away. A later Healthcare idea at 0.75 replaces the 0.65 idea. One at 0.62
does not get in.

**Buy candidates.** The autopilot buys only from
[core/discovery/candidates.py](../core/discovery/candidates.py)'s list, built at each 16:30
review (today a buy is a SWITCH destination):

- shelf ideas whose latest dive is at most 30 days old. An older idea waits for
  Saturday's re-dive, because its band and conviction describe a month-old
  price;
- the user's own watchlist BUYs (`discovery.watchlist_buys`). The stock's
  latest analysis in the score history must be a BUY or STRONG BUY, with an
  actionable data gate, conviction at the floor or above, at most 30 days old,
  for a stock NSE lists as a company. Its entry band and invalidation level
  come from its close on the analysis day, as a deep dive sets them, so the
  SA-050 entry rule applies unchanged. A stock the autopilot itself sold onto
  the watchlist does not qualify: buying it back needs a new deep dive. The
  record-mode gate keeps an unverified shelf idea as a possible destination
  (section 4). A watchlist stock gets no such allowance: an unqualified one is
  not offered at all.

Each candidate carries the sector it will be held under, the key its
forecasts are written under: a managed stock's managed-record sector,
whether the record is enabled or not (promotion re-enables it as it is). A
watchlist stock that is not managed takes the item's own well-formed
sector, else `infer_sector`, never a fixed `generic`. A shelf idea whose
stock is managed under another sector is offered under the managed one; the
shelf keeps its own record. Example: the home page saves a watchlist stock
with no sector. HEROMOTOCO added there is managed under `automobile`, so a
SWITCH buys it as `automobile`. With MARUTI and M&M at 28% of ₹10 L, the
30% sector cap then allows 4 shares at ₹5,000, not the 20 a `generic` label
would let through (38%).

**Limits.**

- Without a Surveillance Indicator report of the last 7 days, a stock under
  ASM or GSM passes the screen. The screen, the weekly summary and, after a
  week, the watchdog say so. IPO candidates and re-dives never pass through
  the screen's guards, so a shelf idea that comes under ASM later stays on
  the shelf.
- The report's ESM and insolvency (IRP) columns are not gated. On 29 Oct
  every ESM stock and all but 2 of the 56 IRP stocks were in a
  trade-for-trade series (BE, BZ, SZ) or on the SME platform, which the
  universe leaves out.
- Yahoo names an industry in its own taxonomy. One the table does not name,
  under a Yahoo sector that maps to no key (Industrials or Basic Materials,
  for example), reads `generic`. TIINDIA reads `capgoods` (Yahoo:
  Conglomerates) where NSE says automobile components.
- NSE's per-symbol meta API (`equity-meta-info`) answers 404 (2026-10-20) and
  its quote API refused this machine, so neither is read.
- Yahoo's `quoteType` calls an Indian ETF "EQUITY", so it cannot tell a fund
  from a company; the ISIN can.
- A capped-out idea waits 30 days for its next dive, even if its sector frees
  a place sooner.
- Insider buying counts rupees, not a share of the company: ₹5 crore bought
  in a large company outranks ₹2 crore in a small one, though the second may
  weigh more on its price.
- A revision that leaves out a trade its original reported leaves that trade
  counted, and one that changes a trade's share count adds the corrected
  trade to the original's: NSE does not say which filing a revision corrects.
  In the 28 days to 23 Oct, no revision whose original was also listed did
  either.
- Two originals with the same trade count twice. SARLAPOLY filed two
  originals, each a 10,000-share sale on 25 Sep, and the filings do not say
  whether they are one person or two.
- A revision's trade replaces an earlier trade with the same action and share
  count even when nothing else agrees. So a revision of an old trade can
  replace an unrelated trade in the window, which then stops counting. On 23
  Oct, 9 revision trades replaced an earlier one; 8 agreed on person group,
  market, value and days, and the ninth, an employee's off-market move,
  changed no net.
- Above 75%, a promoter-group sale counts nothing even when the group also
  bought in the window, so a purchase and a sale through the market (an
  inter-se transfer, say) score as the purchase alone. On 23 Oct no company
  with both was above 75%. **Planned:** FIX-014.
- A pledge row names the company, not its symbol, so the guard relies on
  NSE's symbol filter.

### IPO layers

| Layer | Current source and output |
|---|---|
| Calendar, offer and bids | [ipo.py](../services/data/fetchers/ipo.py), [ipo_offer.py](../services/data/fetchers/ipo_offer.py), [ipo_bids.py](../services/data/fetchers/ipo_bids.py): normalize and enrich issues. Failed refresh preserves previous cache with degraded/stale information. |
| Captured snapshots | [signals.py](../core/ipo/signals.py): observed refresh facts with hour/content deduplication. [velocity.py](../core/ipo/velocity.py): demand changes derived on read. |
| Historical evidence | [history.py](../core/ipo/history.py), [outcomes.py](../core/ipo/outcomes.py), [report.py](../core/ipo/report.py): facts, realized curves and subscription-bucket summaries. |
| P3 model and deep dive (dark) | [research.py](../core/ipo/research.py), [extract.py](../core/ipo/extract.py): browsed, corroborated Substance facts with source URLs. [hype.py](../core/ipo/hype.py), [substance.py](../core/ipo/substance.py), [verdict.py](../core/ipo/verdict.py): deterministic indices and the §3 verdict grid over captured and browsed facts. [deep_dive.py](../core/ipo/deep_dive.py): the 19:00 `ipo_deep_dive` sweep (T−1 research run, post-close re-read from cache) that writes to the append-only store in [verdicts.py](../core/ipo/verdicts.py). [narrate.py](../core/ipo/narrate.py): a sourced research note stored on that row, written by the bulk model from the SAME structured findings the indices read — the verdict is never passed to it, every number in the prose must appear in the findings, an advice/verdict vocabulary rejects it, and a rejected or failed note falls back to a deterministic template. **Writes only:** no verdict, index or quadrant reaches any surface until the `ipo_verdicts_visible_gate` milestone is judged on forward rows. |
| Forward grading of the P3 verdict (dark) | [listing.py](../core/ipo/listing.py) resolves the listing date and issue price from the P1 spine, then the NSE cache; [grade_ipo_lane](../core/audit/outcomes.py) grades the newest stored verdict per issue against the tape at 1/5/21/63/126/252 trading days from listing, entry price = issue price. Only the listing-day row of a post-close verdict with a directional lean can be scored; the rest carry the return and no claim. Rows land in the existing per-user audit store and are **excluded from the rendered audit report**. `scripts/ipo_backfill.py` still rebuilds the P1 spine manually. |
| Recent-listing ranking | [ipo_tracker.py](../core/discovery/ipo_tracker.py): listing evidence, delivery trend, bulk accumulation and optional subscription score discovery candidates. |
| User surfaces | IPO-watch in briefs, weekly/discovery context and shelf. The brief's demand lean ([`_ipo_lean`](../core/delivery/brief.py)) judges subscription against size-tiered bands from `delivery.brief_ipo_size_tiers`; an issue whose size was not read uses the scale-free scalar thresholds, never the largest tier. The lean is a labelled heuristic, not the P3 verdict. Inspected routes do not provide a dedicated `/ipo/predict` API or complete standalone IPO prediction page. |

History uses **1, 5, 21, 63, 126 and 252 trading sessions**, measured from
**issue price**. Unmatured horizons are absent, not zero. Benchmark excess
subtracts the listing-to-horizon benchmark return; that window does not capture
the stock's issue-to-listing move in the same way. Do not interpret the result
as a fully matched investable strategy. Missing subscription is excluded, and
report bucket means below a sample count of ten are suppressed.

The recent-listing tracker is a separate heuristic. It needs at least five EQ
sessions and configured price/liquidity guards. Component weights are 40%
listing evidence, 20% delivery trend, 15% bulk accumulation and 25% subscription,
renormalized over available components. It can fall back to first cached close
when issue price is absent; that differs from historical-outcome calculation.

GMP fetching exists behind a separate disabled-by-default gate. Missing GMP
does not mean zero. A reading needs `ipo.gmp_min_sources` distinct sites, and
a Google redirect link is never one. Lock-in alert dates use fixed 30/90/180-calendar-day offsets
from listing; these are software heuristics, not verification of an individual
issue's contractual dates.

The historical **Prospect** design planned further modeling after P0/P1/P2
collection. Current code has collection, history, captured signals, heuristic
candidate ranking and the dark P3 model, deep-dive job, narrator and
forward-grading lane in the table above. None of it reaches a user.
Production's nightly audit grades IPO-lane rows (4 on 1 October 2026; section
1), and they stay out of every rendered report until the visibility gate is
judged. A validated IPO
application/allotment or listing-gain predictor is therefore still not
established, and is not part of the September remediation scope.

## 9. Scheduled jobs and event hooks

Source: [scheduler.py](../services/scheduler/python/scheduler.py).
These are in-process APScheduler jobs, not separate OS cron jobs. There are
**26 possible job IDs**, including three IPO jobs. Registration depends on gates
and valid cron configuration; registration alone is not execution.
All times are **Asia/Kolkata (IST)** defaults.

| Job ID | Schedule | Work / condition |
|---|---|---|
| `prompt_daily_deploy` | Daily 00:00 | Prompt publishing; handler/configuration can write externally. |
| `ops_watchdog` | Daily 06:30 | Milestones/checks/configured prep; watchdog gate. |
| `macro_daily_news` | Mon–Fri 07:30 | Policy/RBI feed; macro-news gate. |
| `ipo_refresh_am` | Daily 08:00 | Calendar/bids/snapshots; IPO gate. |
| `company_events_am` | Mon–Fri 08:15 | Company-event feed (section 4): overnight filings, disclosures and news; events gate; skips NSE holidays. |
| `preopen_shock_check` | Mon–Fri 08:45 | Shock/reforecast; feature/calendar checks in handler. |
| `morning_brief` | Mon–Fri 08:50 | Brief assembly/delivery; delivery gate. |
| `macro_market_news` | Mon–Fri 09:00, 12:00, 15:00 | Intraday macro feed; macro-news gate. |
| `rl_daily_review` | Mon–Fri 16:30 | Previous trading session; configured feedback cron. |
| `ipo_refresh_pm` | Daily 17:45 | Evening IPO update before Sunday weekly review; IPO gate. |
| `company_events_pm` | Mon–Fri 18:30 | Company-event feed: the day's filings, disclosures and news, after the close and the 16:30 review; events gate; skips NSE holidays. |
| `ipo_deep_dive` | Daily 19:00 | T−1 IPO research + post-close re-read into the dark verdict store; IPO gate. |
| `bhavcopy_daily_sync` | Mon–Fri 19:00 | Official EOD cache; discovery gate. |
| `atlas_universe_recompute` | Daily 23:00 | Demand/cadence; no-op if Atlas disabled. |
| `atlas_cost_rollup` | Daily 23:15 | Cost aggregation; Atlas gate in handler. |
| `atlas_retention` | Daily 23:20 | Retention; Atlas gate in handler. |
| `data_backup_nightly` | Daily 23:30 | Archive with manifest, restore drill, local rotation, encrypted off-site copy when configured, email copy; the status feeds the watchdog (section 10). |
| `audit_nightly` | Daily 23:45 | Matured outcome grading/breach reports; audit gate. |
| `ledger_cleanup_weekly` | Monday 03:30 | Stale-lesson cleanup. |
| `event_ingest_weekly` | Saturday 10:00 | Dossier events; event-ingest gate. |
| `research_loop_weekly` | Saturday 11:00 | Open company questions; research-loop gate. |
| `discovery_weekly` | Saturday 12:30 | Insider trades/screen/deep dives/shelf/paper; discovery gate. |
| `weekly_review` | Sunday 18:00 | Results scorecard, portfolio summary, index watch; delivery gate. |
| `scorecard_monthly` | Calendar first 02:00 | Previous-month scorecard/evidence; scorecard gate. |
| `rl_monthly_forecast` | Calendar first 09:00 | Forecast envelopes. |
| `rl_calendar_update` | December 31 23:00 | Holiday calendar refresh. |

Startup self-heal, the post-review portfolio/digest hook and the outbox drainer
are **not additional cron jobs**. An 08:50 brief is not guaranteed to wait for
an unfinished 08:45 shock check. Close clock times are not dependencies. HTTP
202 from a manual trigger means accepted for background work, not finished.

### Daily-review outcomes

A review that does not raise has not necessarily produced feedback. Counting
it as output once recorded `produced=20`, `expected=20` and `pipeline_ok=true`
on a day when WELCORP returned `no_envelope` and only 19 feedback rows
existed. [review_outcomes.py](../core/intelligence/rl/workflows/review_outcomes.py)
therefore gives each enabled ticker exactly one outcome:

- `completed`: the review wrote its feedback entry;
- `degraded`: it wrote its feedback entry on an input the data gate would have
  stopped, as `record` mode lists them. A graded row with unknown provenance
  reads `degraded`;
- `data_gated`: the gate stopped it before any write (`enforce` mode);
- `skipped`: no envelope, no forecast row for the session, or no close;
- `failed`: it raised, returned a malformed result (an unknown status, or a
  result for another ticker or date), or was still running when the harvest
  budget ran out.

Only `completed` and `degraded` are output (`produced`), so a skip, a gate stop
or a failure fires the zero- or partial-output alert, which names the tickers
and why.

**Example:** 20 tickers, and WELCORP has no envelope. The record reads 19 of
20, `status: partial` and `missing: {WELCORP: "skipped: no_envelope"}`. The
alert says "completed 19/20 — missing: skipped no_envelope: WELCORP".

- Required work (the distinct enabled tickers) and attempted work are counted
  separately. Disabled tickers are listed as `excluded`, and a duplicate entry
  is reviewed once and listed under `duplicates`.
- The day after a weekday NSE holiday reviews the same session again: Fri 2 Oct
  and Mon 5 Oct both review Thu 1 Oct. The second run merges with the first,
  so attempts add up and completion does not. A ticker whose earlier run wrote
  its feedback stays output even if the rerun fails.
- `status` is `ok`, `partial`, `failed` or `empty` (every ticker disabled).
  `pipeline_ok` is true only when the portfolio pipeline returned a well-formed
  `completed` and no required review failed; `pipeline_status` says what the
  pipeline itself did.
- The record in `data/scheduler_job_outcomes.json` keeps the legacy fields and
  adds `by_ticker`, with each ticker's outcome, reason and attempts.

**Limits.** The pipeline's own `completed` does not count holdings whose
advisor call failed inside it. The learning side of a rerun is not yet
idempotent. Nothing in the watchdog reads this record; the review's logged
failures reach the operations backlog (section 10) as log lines. **Planned:**
durable outcomes for every critical job (SA-036), idempotent learning updates
(SA-015), silent-degradation checks in the watchdog (SA-034), and readiness
and ownership recovery (SA-029).

## 10. Delivery, interface, identity and operations

### Delivery

[Briefs](../core/delivery/brief.py), [weekly reviews](../core/delivery/weekly.py)
and digests persist independently of transport.

The brief's overnight section reads only the macro cache's HIGH items, fed by
four generic news searches. The macro reviewer rates company news MEDIUM, so a
held company's news never appears there. An item is overnight news only if it
was **published** on or after the previous brief's date. The publish date is
the IST calendar date, so 20:00 UTC on Tuesday counts as Wednesday. The floor
is the previous trading day for a user's first brief, and never more than 4
days back after a gap. The [fetcher](../services/background/macro_news_fetcher.py)
stores an unreadable or future date as empty, never as today, and such an
item is never shown. It leaves out a headline whose link is a Google redirect
(event feed, step 5), because the cache tells items apart by URL, and logs
how many.

Each shown item stores a story key: its URLs (normalised, including those of
items merged into it), and the salient entities and figures of its headline.
A candidate
that matches anything in the user's last 5 briefs is suppressed: the same URL
always matches. A different URL matches when it shares at least 3 entities,
no more than a third of its own entities are new, and it carries no figure the
shown one lacked ("6.0%" and "6%" are one figure). So a reworded copy is
dropped, but a follow-up is shown when it names new entities or a new figure:
a rate cut after a hold, a notification after an announcement, or the rupee at
97.2 after 96.5.

The known limits: a follow-up that changes only the action of an otherwise
identical headline, with no new figure, reads as a repeat for up to 5 briefs
("approves" to "withdraws", or "plans to cut" to "cuts"). And after 24 hours
Google gives an article's age in whole days, which the fetcher dates at the
newest day that age allows, so an article first seen at "1 day ago" can be up
to two days old; it is shown once. Briefs dated the run's
own day are not history, so a same-day rerun shows the same items. The newest
items fill the 3 places. The brief JSON's `overnight_filter` records the floor
and the counts of candidates, undated, stale, repeated and shown items.
Chat's macro context, its `get_macro_news` tool and the daily review's macro
fallback apply the same publish-date rule (today or yesterday; the reviewed
day or the day before).

"Before the open" lists S&P 500, Nasdaq Composite, Nikkei 225, Hang Seng,
Brent, USD/INR and the US 10-year yield from Yahoo daily bars
([get_overnight_markets](../services/data/fetchers/macro.py), fetched once per
run). Each figure shows its change on the previous session and its as-of date
in the exchange's own zone:

- a US figure is the last session before the brief's day;
- Nikkei and Hang Seng appear only when they traded that day;
- nothing dated after the brief is used, and no weekend-dated bar (Yahoo
  carries weekend quotes for USD/INR, which does not trade then).

A failed, stale (over 4 days) or implausible figure is named "unavailable"
and shows no number. GIFT Nifty is not shown: no reliable free source. The
Inbox renders the server's sentences. **Planned:** a "your stocks" section
from the company-event feed of section 4 (PR-008).

The weekly review opens with the week's results scorecard (section 7): red
flags first, then closed trades, sales graded by the nightly auditor, exit
reasons, the Nifty comparison, breadth and holding period. The email is plain
text; the Inbox weekly screen renders the same sentences.
[Channels](../core/delivery/channels.py) send email and web push. Email has two
transports: SMTP (STARTTLS) and the HTTPS Resend API. `EMAIL_TRANSPORT` in
[settings](../src/backend/shared/config/settings/base.py) defaults to `auto`,
which uses Resend only when `RESEND_API_KEY` is set and SMTP otherwise;
`resend` or `smtp` forces one. The repository's `delivery.email_enabled` is
`false`; the `DELIVERY_EMAIL_ENABLED` environment variable overrides it.

When its Atlas path is active, [outbox.py](../core/delivery/outbox.py) holds
one row per message and channel, and a drainer in the singleton owner sends
each row. Stored, queued, transport-accepted, received and read are separate
states; the code observes only the first three. A row's stored status
`delivered` means the transport accepted it.

[Alerts](../core/delivery/alerts.py) are sent as one bundled message per user,
deduplicated by user, date, kind and symbol in one sent-log, and listed in the
Inbox. Who receives an alert depends on what it is about:

- **Operator notices** concern the system's own health: watchdog milestones
  and invariants, an LLM failure streak, a job that crashed or produced too
  little, a verification-audit breach, ledger drift, a quarantined portfolio
  file, the universe budget governor and an Atlas ETL quarantine. Two of them
  name a user's id. They go to the owner alone: every `users.db` account whose
  role is `owner`, or the default user when there is no such account, and a
  failed lookup also falls back to the default user. The first signup takes
  the default portfolio id, so that is normally one account. For example, when
  the 06:30 watchdog finds the backup not confirmed off-site, the owner's phone
  and laptop each get a push and the owner's mailbox gets one email; an invited
  member's phone gets nothing, and the member's Inbox does not list it.
- **Market notices** (discovery shelf adds, an index change to a shelf idea
  and the pre-open shock re-forecast) go to every account with a push
  subscription and to the default user, each email to the account's own
  address.
- **An account's own alerts** go to that account: advisor escalations,
  lock-in expiries, and an index change to a stock the account holds or
  watches. The [weekly index check](../core/delivery/index_watch.py) sends
  each account one notice with its own stocks and never names another
  account's. A shelf idea that the account also holds arrives once: with the
  shelf's notice, or in the account's own notice when the shelf's notice did
  not include the account (it has no push subscription and is not the default
  user). If an account's portfolio cannot be read, that run skips its index
  changes rather than sending them to anyone else. For example, when a stock
  that only the owner watches leaves the NIFTY 50, the owner is told and a
  member is not; if the stock were a shelf idea, both would be.

The Inbox's Alerts tab (`GET /delivery/alerts`) lists only the caller's own
records; a record written without a user id belongs to the default user. A
unit test classifies every caller of the alert functions into these three
groups, so a new caller fails until it is placed.

### Delivery contract

Every transport returns one result: whether it accepted the message, why not,
whether a retry can help, and any wait the provider asked for. The drainer
acts on it:

- **Accepted is not received.** SMTP 250, a Resend 2xx and a push service's
  201 are acceptance. The row records the transport in `accepted_by`, with
  Resend's message id, which the owner can look up in the Resend dashboard.
  No receipt, bounce or display is observed.
- **Transient failures retry.** A network error before anything was sent (for
  push, only a connection that was never made: refused, a failed DNS lookup or
  a connect timeout), an SMTP 4xx reply, or HTTP 429 or 5xx: the row retries
  after 1 and then 5 minutes (the configured backoff), or later if the
  provider's `Retry-After` asks for more (capped at 6 hours). After 3 attempts
  it is dead-lettered as "retries exhausted".
- **Permanent failures stop at once.** A rejected login, an SMTP 5xx reply,
  Resend 400/401/403/422, a disabled or unconfigured channel, no push
  subscription, or no address for the account: one attempt, then a dead letter
  whose reason names what to check. For example, a Gmail 535 reads "check
  SMTP_USER and SMTP_PASSWORD (Gmail needs an app password)".
- **At most once.** When the outcome is unknown, the row is dead-lettered as
  "unknown outcome" and never re-sent: the SMTP connection dropped inside the
  send; a push failed in any way other than an HTTP status or a connection
  that was never made (a read timeout, or the connection dropping after the
  request was sent, when the push service may already have stored it); or the
  process stopped while the row was `sending`. SMTP and web push cannot
  deduplicate a repeat. So if one of an account's phones gives an unknown
  outcome, the row stops for all of them, and a phone whose push service
  answered 5xx loses that notification, visibly, as a dead letter.
  Email over Resend carries a per-row `Idempotency-Key`, which Resend keeps for
  24 hours, so its timed-out requests do retry without a second email. A
  `sending` row counts as abandoned after 60 minutes; a younger one may belong
  to the old container during a deploy.
- **Recipient isolation.** `resolve_recipient()` returns the owning account's
  address from `users.db`. `DELIVERY_EMAIL_TO` is used only on the single-user
  path: no user id, or the default portfolio id. For any other account, a
  failed lookup retries and a missing address dead-letters; neither reaches the
  owner. The inline path (Atlas off, or the outbox unreachable) follows the
  same rule.
- **Redaction.** Reasons and log lines mask email addresses, URL paths (a push
  endpoint is a bearer capability) and the configured secrets.
- **Push TTL.** Pushes carry a 12-hour TTL (`delivery.push_ttl_seconds`).
  pywebpush's default of 0 lets a push service drop a notification for a phone
  that is offline when it arrives. This comes from reading the library; its
  effect on what users saw was not measured.
- **Visibility.** `GET /delivery/outbox` (owner session or machine key) returns
  counts per channel and status, with `delivered` shown as `accepted`; the
  newest dead letters and retrying rows with their reasons; and the last
  acceptance per channel. It states that user receipt is not observable, and it
  carries no payload, address or user id: a dead letter for an account with no
  address reads "no email on file for this account", and its row id identifies
  it.
- **History.** Nightly retention deletes accepted rows after 30 days. Dead
  letters stay for 180 days; after 30 days only their payload is cleared.

The monthly Learning Evidence email, the watchdog heartbeat and the backup
email are sent directly, not through the outbox, so they get no retry and no
dead letter; a failure is logged with its reason. The backup email is not the
off-site copy (below). **Planned:** a witness outside the app for missed jobs
([SA-042](planning/PI-2026-09/stories/SA-042.md)).

**Dated production observation.** The September audit recorded email
failures. The cause was identified on 2026-09-21: Railway disables outbound
SMTP on its Hobby plan, and production had logged `[Errno 101] Network is
unreachable` on every send since 2026-07-16. After a plan upgrade and
redeploy, a triggered brief reached the inbox that day. A read-only probe on
2026-09-23 counted, since that redeploy, 8 email rows accepted and 0 dead, and
11 push rows accepted; before 21 Sep, 77 email rows were dead and 77 push rows
accepted. Those counts are provider acceptance, not a measured receipt rate.

Remaining limits:

- Resend's default shared sender (`RESEND_FROM`) delivers only to the Resend
  account owner's address. Per-account email over Resend needs a
  verified-domain sender, which is an owner configuration step, not code.
- When several push subscriptions exist, acceptance by one counts as
  accepted; the others are not retried, so they cannot receive a duplicate.
- Resend deduplicates a key for 24 hours. Retries end well inside that window
  (two waits, each capped at 6 hours); a policy with longer waits would lose
  that protection.

### Backups and recovery

The Railway volume is the only home of the trade ledgers, the prediction tree
and the SQLite stores, so a backup must leave the volume and must restore.
Three SQLite stores (`users.db`, `atlas.db` and `chat_sessions.db`) run in WAL
mode and cannot be copied as raw files: restored alone, a raw copy of a fresh
WAL database has no tables at all. On 2026-09-23 the older job built an
8.98 MB zip, its email failed, and the only copy stayed on the volume.

Each night at 23:30 the [backup](../services/data/backup.py) job runs these
steps:

1. **Build.** Every non-cache file under `data/` goes in. A file is treated as
   SQLite by its header, not its name, and is copied through the backup API;
   `-wal`, `-shm` and `-journal` files are never copied raw. Credential-shaped
   files (`.env`, `*.pem`, `*.key`, `*secret*` and similar) are left out and
   logged. Other files are read until one read sees no size or modification
   change. `MANIFEST.json` inside the zip records each file's size and SHA-256.
   For each database it records `integrity_check`, a schema digest and every
   table's row count, and for each portfolio ledger its row count. A sidecar
   `<archive>.manifest.json` records the zip's own size and SHA-256. The zip is
   built under a `.part` name, so an interrupted run leaves no archive.
2. **Drill.** [restore](../services/data/restore.py) restores the archive into a fresh
   temporary directory and recomputes everything the manifest claims. Errors
   mean the copy is not faithful: a missing manifest, a checksum mismatch, a
   corrupt zip, an unexpected or unsafe member, a failed `integrity_check`, or
   a schema or row-count difference. Warnings mean the copy is faithful but
   the data is suspect. The drill also checks ledger continuity. For example,
   Monday's archive holds `transactions.jsonl` at 1,200 bytes, so Tuesday's
   must start with those same 1,200 bytes, because the four portfolio ledgers
   are append-only. If a script rewrote row 3 overnight, Tuesday's drill
   warns "was rewritten"; a ledger that shrank or disappeared warns the same
   way. Older off-site copies still hold the earlier history.
3. **Rotate** the local copies to the newest 7, each with its sidecar.
4. **Off-site.** Only an archive that passed its drill leaves the volume.
   [offsite](../services/data/offsite.py) encrypts it with AES-256-GCM under
   `BACKUP_ENCRYPTION_KEY` and uploads it to `BACKUP_OFFSITE_TARGET`. That is
   `s3` (any S3-compatible bucket, signed with AWS Signature V4 using only the
   standard library and `requests`) or `dir` (a separately mounted directory,
   refused when it overlaps `data/`). The ciphertext goes first and the
   manifest last; each must read back at its uploaded size. Only then is the
   copy "confirmed". An upload interrupted halfway is never confirmed, and its
   leftover ciphertext is deleted once a newer copy is confirmed. Retention
   keeps the newest `BACKUP_OFFSITE_KEEP` confirmed copies (30 by default; 0
   or less keeps all). It never touches objects not named like a backup, and
   it deletes a copy's manifest before its ciphertext.
5. **Email** the plaintext zip when it is under 20 MB. This is a direct send;
   it does not count as off-site.
6. **Record** `data/backups/backup_status.json`. A failed drill then raises,
   so the scheduler's job-error alert fires.

**Visibility.** The watchdog invariant `backup_recoverable` reads that status
every morning. It warns when the job has not run for 36 hours, when the drill
failed, when last night's copy was not confirmed (the reason is scrubbed of
secrets), and when the drill flagged a ledger. While no target is configured
it says "No off-site copy has ever been confirmed", **once a week**: the check
asks for that pace itself (`repeat_days=7` on its result). Everything else
still warns daily: a failed drill, a stopped job, a flagged ledger even with
no target, and a half-done setup such as a target without a key. For example,
a reminder on Thursday is followed by silence until the next Thursday. If
Friday's drill fails, Saturday's watchdog warns anyway.

A ledger rewrite is reported on one morning only, because the next night
compares against the rewritten archive. The earlier history then survives
only in the older off-site copies, for `BACKUP_OFFSITE_KEEP` nights.

**Owner configuration (not provisioned by code).** Create a private bucket
and an access key limited to it. The archive is about 9 MB, and several
S3-compatible providers have a free tier at that size. Set these Railway
variables:

- `BACKUP_OFFSITE_TARGET=s3`;
- `BACKUP_S3_ENDPOINT` (a bare `https://` URL), `BACKUP_S3_BUCKET`,
  `BACKUP_S3_REGION` (`auto` by default) and optionally `BACKUP_S3_PREFIX`
  (`stockagent/`);
- `BACKUP_S3_ACCESS_KEY_ID` and `BACKUP_S3_SECRET_ACCESS_KEY`;
- `BACKUP_ENCRYPTION_KEY`, from
  `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`.

Keep a second copy of the key outside Railway, for example in a password
manager: without it no off-site copy can ever be read. Setting a Railway
variable redeploys the service.

**Restore runbook.** On a machine with the same variables set, run
`python -m services.data.restore fetch --dest <empty directory>` from the
repository root. It downloads the newest confirmed copy (or a named one),
checks the ciphertext against its manifest and decrypts it; a wrong key or one
flipped byte stops it. It then drills the result into `<dir>/restored`. Exit
codes: 0 is clean, 2 is faithful with warnings, 1 is failed.
`python -m services.data.restore drill <archive>` checks a local archive the
same way. Neither ever writes into `data/`: a destination that overlaps it, or
is not empty, is refused. Putting restored files back into a stopped
deployment is a deliberate human step.

**Limits.**

- Each file is a point-in-time copy, but the archive is not one snapshot
  across files. The job runs at 23:30, when no trading job writes.
- A night on which the job never runs, for example because the container
  restarted at 23:30, is not reported: at 06:30 the newest status is 31 hours
  old, under the 36-hour limit, so the check still reads the previous night's
  copy as confirmed. Two missed nights in a row are reported. **Planned:**
  SA-034.
- One malformed SQLite file stops the whole archive. The job raises, so the
  job-error alert fires each night. No new archive, off-site copy or status is
  written until the database is repaired, so the ledgers are not backed up in
  the meantime; earlier archives and off-site copies are kept. **Planned:**
  SA-036.
- The email copy is an unencrypted direct send.
- Credentials live in Railway variables and are not backed up.
- A deleted account's data survives in off-site copies until retention
  removes them (30 nightly copies by default).
- Off-site recovery counts as verified only after a recorded `fetch` drill
  against the real bucket. None has been run, because no bucket exists yet.

### Interface and chat rendering

The frontend uses React JSX, runtime browser transformation and PWA assets.
Chat uses a streaming tool loop with potentially paid provider calls. Prompt
editing can feed scheduled publishing. These are not inert testing screens.
Bearer sessions, roles and machine-key authentication are implemented;
portfolio identity comes from the authenticated user. Chat's tools follow the
same rule: the brief tool reads only the caller's portfolio and refuses a
request without a valid user id, rather than fall back to the default user
([CHAT_ARCHITECTURE](CHAT_ARCHITECTURE.md) section 2). Some intelligence read
routes remain public.

The server-log routes `GET /ui/logs` and `/ui/logs/stream` are owner-only.
Log lines carry user ids, per-user trade activity and error text, and the
in-memory ring buffer behind both routes redacts nothing. Both therefore take
`require_owner`: the owner's session or the machine key. For example, a member
who opens `/ui/logs?limit=1000` gets 403, and a visitor without a session gets
401. The check runs before the handler, so a refused request never reads the
buffer, and a refused stream never subscribes or sends a line. With
`AUTH_REQUIRED` off, an anonymous request acts as the owner, here as on every
owner route; a member's session is still refused. A browser `EventSource`
cannot send the session header, so the Logs screen
([logs.jsx](../src/frontend/prototypes/logs.jsx)) reads the stream with
`fetch`. On a 401 or 403 it shows a plain message and stops reconnecting, and
it does not open the API-key prompt that other 403s trigger.

Every figure on a member's screen comes from an API answer and carries its
date, or the screen says it is unavailable. For example, at 09:00 IST the home
hero reads "Good morning, Ravi." for the signed-in account, whatever the
phone's time zone. Below it is "Nifty 50 −0.42% on 12 Oct.", from
`/ui/bootstrap`'s `NIFTY50`: the last close, its change on the close before,
and that close's date. When that fetch fails the line is left out. The index
box reads `/ui/nifty-ranges`, which returns the Nifty 50's closes over the
named calendar span, the last value and its date. The Today and This month
panes state the age of the newest analysis of a shared stock, read as UTC
(the score history stores times without an offset): "Updated 5h ago", then
"Last analysis 2 days ago", with a stale dot past 12 hours. So on a Monday at
09:00 IST, when Friday's 16:30 review made the newest analysis of a shared
stock, Today reads "Last analysis 2 days ago", marked stale; after a Saturday
on which discovery shelved a stock it had just analysed, it reads "Last
analysis 1 day ago". Rows show "—" for a price
the server could not fetch (it arrives as 0), "Not analysed" for a stock with
no analysis, and no move for a sector index that failed. The server sends no
stand-ins: no random sparkline, no generic market drivers, no agent weight
shown as a vote, and chat seeds are questions rather than claims.
`/ui/learnings` returns dated records only. A verdict change is a run whose
verdict differs from the run before it; a re-run with the same verdict is not
one. The route looks through every kept run of each stock the viewer may see
(below) and sends the changes newest first, at most ten, then the latest
forecast misses, at most five. The Portfolio page counts only the changes and lists the misses under
their own heading. For example, MARUTI turned BUY on 9 Oct, TATAMOTORS SELL on
10 Oct and BOSCHLTD BUY on 13 Oct, and eight other stocks were re-analysed with
the same verdict. The page reads "3 changes in the analysed stocks", BOSCHLTD
first. A full list reads "The 10 most recent changes", because older ones may
have been left out. With no change it reads "No verdict changes since 16 Sept":
`since` is the date of the oldest kept run among those stocks. If the score
history cannot be read, the route sends nothing rather than a partial list. A composite-score change is not rupees, so there is no
gain, loss or agreement figure and no templated lesson; realized trade results
are in the portfolio's closed-trade card and the weekly scorecard (section 7). The Learn page claims no progress for a member,
because nothing records it. Sample data exists only in demo mode: `?demo=1` loads the invented
values in `src/frontend/prototypes/demo-fixtures.js` under a "Sample data"
banner and makes no market call, and the layout audit uses it.
A failed request never falls back to a sample.

**Score history and who sees which stock.** Every completed analysis writes
one score-history row (`scores.db`) at the orchestrator's single exit, after
the decision gate, with the verdict the run returns. Each entry point ends
there: the 16:30 review, the monthly forecast, discovery deep dives,
`/analyse`, the stream and the chat. A failed write is a warning and never
fails the analysis. The store keeps the newest `SCORE_HISTORY_MAX_ROWS` (90)
runs per stock, and each agent's score as its own reading (`raw`), which the
"This month" votes average. Because the store also holds stocks that a member
asked about by name, a screen that lists stocks out of it names only:

- the shared stocks: the built-in universe, the managed list (which
  `GET /ui/tickers/managed` serves to every account) and the shelf's active
  ideas;
- the viewer's own holdings and watchlist, on the screens that know the
  viewer.

Home's market panes, the market summary and the sector comparison name shared
stocks only. Portfolio's verdict changes, search by thesis text and the chat's
current verdicts and analysis history add the viewer's own. An anonymous
request while sign-in is required owns nothing, and an unreadable portfolio
adds nothing. In the browser, the verdict changes never outlive their viewer:
signing out (or an expired session) drops the list, so the next account on
the same tab sees none of them even if its own fetch fails, and an answer
that arrives after a sign-out is discarded. A screen keyed by a stock the
viewer names, such as a watchlist row or a ticker's history, needs no filter. A watched stock outside the
built-in universe shows its analysis, without a price. For example, say the
owner holds BEL and a member holds DIXON, and neither is managed or on the
shelf. The member's Portfolio lists DIXON's verdict changes and never BEL's,
and the chat answers the member with DIXON's verdict, not BEL's.

Operator tools show only for a session whose `/auth/me` role is `owner`:
Prompt Lab, Analytics, RL Monitor, Logs, agent tuning (the plug, task and
weight controls) and the Tweaks panel. While the role is unknown none show,
and a member sent to an operator screen lands on Home. Hiding is not the
protection: the server keeps `require_owner` on every tuning write and on the
log reads. The RL client still has demo/fallback paths on API failure, so
populated operator charts alone do not prove live data. **Planned:** four
member screens and an Operator menu (PR-010); honest unavailable states on the
remaining screens (SA-024); a public-read and demo-data policy (SA-032).

Chat replies are untrusted text: the model quotes news snippets and tool
output, and a quoted `<img src=x onerror=…>` passed to the browser as HTML
would run its handler next to the stored bearer token (audit F01).
`renderMd` in [sphere.jsx](../src/frontend/prototypes/sphere.jsx) therefore
delegates to a plain script,
[chat-markdown.js](../src/frontend/prototypes/chat-markdown.js). index.html
loads it after marked 12.0.2 and DOMPurify 3.4.16, both exact versions with SRI
hashes. There are two layers:

- marked shows any raw HTML in a reply as visible text. The chat prompt's
  format rules describe Markdown, but nothing in it forbids HTML, so this
  boundary is the control.
- DOMPurify then keeps only Markdown's own tags. Links must be http(s) and open
  in a new tab with `noopener noreferrer`. Images, styles, classes and event
  attributes are dropped.

For example, a reply quoting `<img src=x onerror=…>` shows that string as
text; bold, lists, code fences, tables and https links still render. If either
library fails to load, the reply is shown as escaped text. The raw parser is
taken off `window`, so an older `sphere.jsx` still cached by the service worker
also falls back to text; the worker's cache version is v8. That bubble is the
client's only HTML sink, and a unit test keeps it so.
`npm run test:frontend` drives the real ChatOverlay in Chromium with hostile
fixtures and no network.

### Observability and the watchdog

Durable logs connect run IDs, tickers, warnings, LLM usage and health. Bundle
call counters are not complete nested-provider/fallback cost accounting.

The watchdog reads [milestones.yaml](../config/milestones.yaml), runs checks,
persists state and may perform configured preparation. Its notices are
operator notices, so they reach only the owner (Delivery, above). A sent
milestone notice is not milestone completion. A `manual_confirmation` milestone has no
signal of its own: it stays pending until its entry is deleted, and after its
deadline it re-sends a critical "LAPSED" notice every 7 days. Each lapsed
milestone is judged, then deleted with its evidence or decision recorded, or
re-dated with a dated reason at the head of its action text. A registry edit
reaches production only on deploy.

### Operations backlog

`app_logs` keeps every WARNING+ record, tens of thousands of rows, and logging
a warning again does not close the defect behind it. The backlog
(`core/ops/error_backlog.py`) groups those rows into issues, one per cause,
that the owner can assign and close.

- **Grouping.** Each message becomes a template. The old `<IST time> LEVEL
  [logger]` prefix, timestamps, run, row and user ids, numbers, file paths,
  URL paths and queries, quoted values, secrets and symbols (`MARUTI.NS`,
  `^NSEI`, a bare upper-case ticker) become placeholders. Secrets include
  bearer and Basic credentials, any `Authorization:` value and `key=`
  values; an address is masked also when percent-encoded (`%40`). The
  row's own ticker is masked as any ticker is, so a cause logged inside an
  analysis run and outside one is one issue. A number after
  `HTTP`, `status_code` or `Errno` stays, because it is the cause, and so
  does a URL's host. A traceback is reduced to its exception type and
  message; frames and line numbers are dropped. The fingerprint hashes the
  source, the logger and the template. No model is involved. For example,
  `$MARUTI.NS: possibly delisted; no price data found (period=1d)` and the
  same line for `$INFY.BO` with `period=5d` are one issue, `<sym>: possibly
  delisted; no price data found (period=<n>d)`, while HTTP 401 and HTTP 429
  from one provider are two. Only templates are stored; the raw rows stay in
  `app_logs`, unchanged.
- **Severity** is the record's own level from `app_logs.level`. Railway
  prints every stderr line, INFO included, under an `error` envelope; that
  envelope is never an input.
- **Dead letters.** The outbox logs one WARNING per dead-lettered row with
  its channel, kind and redacted reason, so dead letters form one issue per
  channel, kind and reason: every `email/brief` row refused for SMTP
  authentication, say, with a count.
- **Lifecycle.** An issue is *new* for 2 days after it first appears,
  *ongoing* while seen within 7 days, then *quiet*. It is also *spiking*
  when today's or yesterday's IST count exceeds its own trailing 14-day mean
  by 3 standard deviations and is at least 10. The owner triages it as
  `acknowledged`, `fixed` (with the time the fix took effect) or `wontfix`,
  with an assignee, a task and a note. A fixed issue that recurs after its
  fix reopens as *regressed*. An open issue that returns after 7 quiet days
  is *regressed*; an acknowledged one only after 35, so the known warning of
  a weekly or monthly job stays with its owner, and it still needs attention
  if it spikes. A fix time carries its UTC offset:
  `2026-10-05T08:00+05:30` for 08:00 IST, or `2026-10-05T02:30Z`. One
  without, or a date alone, is refused with the form to give. The app shows
  IST and a caller may mean UTC; an IST time read as UTC would file the fix
  5.5 hours late, after any recurrence in that gap. A fix time later than
  now (beyond 5 minutes of clock difference), or earlier than an occurrence
  the registry already holds, is refused with the issue's last-seen time in
  IST: that fix did not hold. Times are kept as precisely as they were
  logged, so the same rows give the same outcome whether they were read
  before the mark or after it, even within one second. A fix is *verified*
  only after 7 days with no recurrence and once the archive holds rows from
  after that window; silence from a stopped archive leaves it *unobserved*.
- **Retention.** An issue keeps 30 days of daily counts and its last 20 run
  ids and tickers. An issue unseen for 90 days is pruned unless it is
  acknowledged, awaiting fix verification or needing attention. A cap of
  2,000 issues removes the stalest quiet ones and never an active one.
- **Access.** `GET /ops/errors` (ranked; `include=attention|active|all`),
  `GET /ops/errors/digest` (plain text with times in IST, the same bytes for
  the same registry and time) and `POST /ops/errors/{fingerprint}` (triage)
  take an owner session or the machine key; a member gets 403. Each read
  first folds new `app_logs` rows into the registry, 2,000 per transaction
  and at most 20,000 per read; `refresh.caught_up` says whether it reached
  the end.
  `scripts/prod_errors.py` prints the digest with app credentials only, or
  builds one offline from a copy of `telemetry.db` or a `railway logs --json`
  export, by the app's own level.
- **Watchdog.** The `error_backlog` check is pending while a new, regressed
  or spiking issue is untriaged. The `error_backlog_triaged` invariant in
  `milestones.yaml` uses it. While anything needs triage, the owner gets one
  warning a day with the steps: read `GET /ops/errors` or
  `python scripts/prod_errors.py --base <app URL>`, then mark each issue
  acknowledged, fixed or wontfix. When nothing does, one "resolved" notice
  follows, then silence. The detail names counts, loggers and fingerprints,
  never a template, so a log line's text stays behind the owner-only
  endpoint.

Local backup files and healthy HTTP responses do not prove recovery or
successful jobs. The nightly drill proves that an archive restores; only a
recorded off-site `fetch` proves recovery without the volume. **Planned:** the
[observability design](superpowers/specs/2026-09-24-production-observability-design.md)
adds job-run and source-health ledgers, post-job checks, provider-credit
alerts, a read-only status fetcher and an outside witness (section 11).

## 11. Planned redesign

Nothing in this section is implemented. Story cards define scope and
acceptance, and [STATE.json](planning/PI-2026-09/STATE.json) holds status.
Accepting code needs tests and a fresh review. Claiming a benefit needs matured
production observations as well.

### One engine with sector lenses

All five graphs already run one bundle and one reasoning-model call; the
LangGraph pool is only a fallback. They differ mainly in five scoring schemes
(37 dimension slots under 24 names), and the LLM re-scores numbers the code
has already computed. Generic-graph stocks are valued against automobile
peers, and missing data is scored 0.5. The
[one-engine design](superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md),
adopted on 2026-09-26, replaces the per-sector graphs in four parts:

- sector knowledge becomes a lens YAML (peers, benchmark, KPIs, news terms and
  macro drivers), resolved from the stock's industry (Yahoo's classification,
  the one industry source; section 8);
- code computes five factors (Value, Quality, Growth, Momentum and Risk) as
  percentiles against real peers and the stock's own history;
- one LLM reader returns dated, sourced events, and code turns them into a
  sixth factor, Catalyst;
- code combines the six at equal weights and maps the result to the existing
  bands. With fewer than 4 of 6 factors it gives no directional verdict. The
  LLM explains the verdict but cannot change it.

SA-044 fixes the peers first. SA-026, SA-045 and SA-046 run in shadow. SA-047
switches only when the engine is right on at least 50% of disagreements with
today's analyst, and SA-027 then deletes the sector packages. Each lens also
names its sector's benchmark, which is where automobile and renewable energy
get an index with data.

### Learning on a corrected target

SA-012 specifies and tests the learning target before anything changes it
(the grading defect in section 5). SA-013 persists immutable, prospective
forecast identities, and SA-014 grades frozen decisions with the information
available at issue. SA-015 makes adaptive updates idempotent and keeps final
weight bounds. SA-016 replaces blame-based shared credit with identifiable
outcomes. SA-017 attaches lineage and quarantines incomparable feedback.
SA-018 to SA-021 build complete matched cohorts, effective samples from
session overlap, and calibration and weight-recovery checks.

**Returning to `adapt`.** SA-043 runs a shadow learner while production stays
in `observe`. It learns six factor weights pooled across all stocks, starting
from the defaults and learning on the corrected target. For each issued
decision it records the default verdict and the shadow verdict from the same
factor scores. SA-022 then scores only the decisions where the two disagree.
Learning may return only when all of these hold:

- at least 100 effective disagreements, over at least 3 months and 3 lenses;
- the shadow is right on at least 60% of them;
- its wins are consistent month to month and robust to dropping its best lens;
- no factor's weight has collapsed to its bound, or below half its default, for
  4 weeks.

The pass must hold at two consecutive monthly looks, and the owner still
decides. `adapt` would then resume from the shadow's weights, never from the
stored pre-fix weights. A reverse tally in the first month (below 45%) returns
learning to `observe`. SA-023 puts learned lessons on measurable probation.

### Portfolio economics

- SA-049 puts idle cash into shelf ideas that pass the checks in a normal
  market, and holds cash on purpose only in a crisis, behind a switch that
  ships off. It works toward a configurable floor of at least 10 holdings and
  ₹10 L invested, fed by section 8's buy candidates. Its sizing rule must
  count real sectors: today the sector cap reads each holding's routing
  `sector`, which is `generic` for most screened stocks, so a fourth such
  holding hits the 30% cap at about 8% each.

### Product results

The [product results review](audit/2026-10-11-product-results-review.md)
traced the owner's concerns to their mechanisms: losing sales, code-like
reasons, a 2-stock portfolio, a repetitive brief and a jargon-heavy interface.
The planned changes connect the research to the money:

- **Measure weekly.** The Sunday results scorecard (section 7) is the yardstick
  for every change below: closed trades, expectancy, the share of sales whose
  stock beat the Nifty afterwards, exit reasons, breadth and the money-weighted
  Nifty comparison, with predeclared red flags.
- **Know each company daily.** The company-event feed (section 4) records what
  happened to each held, watched and shelf stock, and the changes below read
  it, including insider trades, deals, pledges and shareholding changes.
- **Own a stock for a reason.** Each holding gets a written investment case:
  pillars with evidence, an expected range, an invalidation price and business
  triggers, and the next check. Every number in it is checked against its
  inputs (PR-005).
- **Sell on evidence.** Both exit rules run, the price-path rule acting and
  the evidence rule recorded beside it (section 6). The switch to
  `case_broken` is the owner's, on the predeclared gate the weekly scorecard
  reports (PR-009).
- **Explain like an investor.** Explanations follow the pattern "what we did,
  why, what would change our mind, what next", grounded and free of internal
  words (PR-007). The brief opens with your stocks (PR-008).
- **Show only what is real.** On top of section 10's real-figures rule,
  members see four screens and the owner an Operator menu (PR-010).
- **Choose models on evidence.** Models are chosen per role from a bench on
  stored bundles (PR-012).

### Operations and observability

The [observability design](superpowers/specs/2026-09-24-production-observability-design.md)
makes failures visible without reading raw logs:

- SA-036 records a durable outcome for every critical job, and SA-037 keeps
  deploys from dropping scheduled jobs;
- SA-040 records per-source fetch health and detects new error types;
- SA-034 detects silent degradation in the watchdog, including a missed backup
  night and the review outcome record;
- SA-035 surfaces LLM and search provider credit exhaustion;
- SA-041 provides a read-only production status fetcher, and SA-042 adds an
  outside witness for missed jobs (Healthchecks.io → Telegram);
- SA-029 verifies readiness and recovers background ownership;
- SA-025 counts actual provider calls and fallback cost;
- SA-033 locks reproducible runtime dependencies.

### Interface and data policy

SA-024 shows verifiable learning evidence and honest unavailable states. The
stretch stories SA-028 (packaging and a compiled browser client), SA-030
(stale Atlas projections) and SA-032 (the public-read and demo-data policy)
need explicit promotion. SA-031 is the final cross-document consistency check.

### Owner decisions and setup

These need the owner, not code:

- whether to enforce the decision gate, judged on rows issued since the bank
  and resolution fixes (section 4);
- an off-site backup bucket and key, then a recorded `fetch` drill
  (section 10);
- a verified-domain sender, if per-account email goes over Resend;
- whether learning returns to `adapt`, under the conditions above.

Historical [specifications](superpowers/specs/) retain what was intended at
the time. The September audit supersedes unsupported August claims about
correct learning, automatic security succession or unused fallback cost.
Legacy code should only be retired with measured replacement coverage.

## 12. PI-2026-09 roadmap

Each story card defines its scope, acceptance and dependencies, and
[STATE.json](planning/PI-2026-09/STATE.json) holds its status. Evidence
receipts under [evidence/](planning/PI-2026-09/evidence/README.md) record the
tests, the reviewed revision and the production checks. The table maps each
story to the sections of this document it changes. An implemented story's
behaviour is described in those sections as current design. Its production
verification is tracked separately (section 1).

Nine fixes outside the SA numbering are also part of the current design:
listing-day closes (FIX-001, sections 5 and 7), ticker resolution (FIX-002,
section 4), bank income statements (FIX-003, section 4), dossier dates
(FIX-004, section 5), the chat brief's user scope (FIX-005, section 10),
owner-only server logs (FIX-007, section 10), owner-only operator notices
(FIX-008, section 10), index-change notices about the account's own stocks
(FIX-009, section 10) and a score history that every analysis writes, listed
only to the viewers who may see each stock (FIX-010, sections 3 and 10).
DOC-001 produced this document's current-code edition. The PR stories are the
product results track (section 11), ordered in STATE.json directly after
SA-011. Of them, real figures and owner-only operator tools (PR-001,
section 10) are part of the current design.

| Story | Change | Status | KT sections | Dependencies |
|---|---|---|---|---|
| [SA-001](planning/PI-2026-09/stories/SA-001.md) | Sanitize every chat Markdown rendering boundary | Done | 10 Interface | None |
| [SA-002](planning/PI-2026-09/stories/SA-002.md) | Make data-health records describe usable evidence | Done | 4 Research | None |
| [SA-003](planning/PI-2026-09/stories/SA-003.md) | Gate recommendations and learning on essential data | Done | 4 Research; 5 Learning; 6 Portfolio | SA-002 |
| [SA-004](planning/PI-2026-09/stories/SA-004.md) | Count daily-review outcomes truthfully | Done | 9 Jobs | None |
| [SA-005](planning/PI-2026-09/stories/SA-005.md) | Establish a clean, isolated test and CI baseline | Done | 13 Validation | None |
| [SA-006](planning/PI-2026-09/stories/SA-006.md) | Repair delivery transport and expose dead letters | Done | 10 Delivery | None |
| [SA-007](planning/PI-2026-09/stories/SA-007.md) | Make backups independently recoverable | Done | 3 Storage; 10 Recovery | None |
| [SA-008](planning/PI-2026-09/stories/SA-008.md) | Quarantine unresolved securities with explicit lifecycle records | Done | 3 Configuration; 4 Identity; 5 Learning; 6 Portfolio; 8 Discovery | SA-003 |
| [SA-009](planning/PI-2026-09/stories/SA-009.md) | Inventory and reconcile prediction-store ownership | Done | 3 Storage | None |
| [SA-010](planning/PI-2026-09/stories/SA-010.md) | Pass sector benchmarks through technical-data calls | Done | 4 Research | None |
| [SA-011](planning/PI-2026-09/stories/SA-011.md) | Turn durable errors into a deterministic operations backlog | Done | 9 Jobs; 10 Operations | SA-002, SA-004 |
| [SA-012](planning/PI-2026-09/stories/SA-012.md) | Specify and test the learning target before changing it | Open | 5 Learning; 7 Marksheets | SA-005 |
| [SA-013](planning/PI-2026-09/stories/SA-013.md) | Persist immutable, genuinely prospective forecast identities | Open | 3 Storage; 5 Learning | SA-012 |
| [SA-014](planning/PI-2026-09/stories/SA-014.md) | Grade frozen decisions and issue controls before their outcomes | Open | 5 Learning; 7 Marksheets | SA-003, SA-013 |
| [SA-015](planning/PI-2026-09/stories/SA-015.md) | Make adaptive updates idempotent and preserve final weight bounds | Open | 5 Learning | SA-014 |
| [SA-016](planning/PI-2026-09/stories/SA-016.md) | Replace blame-based shared credit with identifiable outcomes | Open | 5 Learning | SA-015 |
| [SA-017](planning/PI-2026-09/stories/SA-017.md) | Attach historical lineage and quarantine incomparable feedback | Open | 3 Storage; 5 Learning | SA-009, SA-013 |
| [SA-018](planning/PI-2026-09/stories/SA-018.md) | Build complete, matched monthly evaluation cohorts | Open | 7 Marksheets | SA-014, SA-017 |
| [SA-019](planning/PI-2026-09/stories/SA-019.md) | Evaluate suggestions across weekly and fortnightly cohorts | Open | 7 Marksheets | SA-018 |
| [SA-020](planning/PI-2026-09/stories/SA-020.md) | Compute effective samples from trading-session overlap | Open | 5 Learning; 7 Marksheets | SA-013 |
| [SA-021](planning/PI-2026-09/stories/SA-021.md) | Validate calibration and weight recovery with minimum evidence | Open | 5 Learning; 7 Marksheets | SA-016, SA-018, SA-020 |
| [SA-022](planning/PI-2026-09/stories/SA-022.md) | Run prospective adapted and frozen-policy experiments | Open | 5 Learning; 7 Marksheets | SA-016, SA-018, SA-020, SA-043, SA-047 |
| [SA-023](planning/PI-2026-09/stories/SA-023.md) | Put learned lessons on measurable probation | Open | 5 Learning | SA-022 |
| [SA-024](planning/PI-2026-09/stories/SA-024.md) | Show verifiable learning evidence and honest unavailable states | Open | 7 Marksheets; 10 Interface | SA-019, SA-020, SA-022 |
| [SA-025](planning/PI-2026-09/stories/SA-025.md) | Count actual provider calls and fallback cost | Open | 4 Research; 10 Cost | SA-011 |
| [SA-026](planning/PI-2026-09/stories/SA-026.md) | Consolidate sector definitions into sector lenses | Open | 2 Repository; 4 Research | SA-003, SA-009, SA-010 |
| [SA-027](planning/PI-2026-09/stories/SA-027.md) | Retire redundant fallback only when measured replacements work | Open | 4 Research; 11 Planned redesign | SA-025, SA-026, SA-047 |
| [SA-028 (stretch)](planning/PI-2026-09/stories/SA-028.md) | Repair packaging and compile the browser client | Open | 3 Runtime; 10 Interface | SA-001, SA-005 |
| [SA-029](planning/PI-2026-09/stories/SA-029.md) | Verify readiness and recover background ownership | Open | 3 Runtime; 9 Jobs | SA-004, SA-007 |
| [SA-030 (stretch)](planning/PI-2026-09/stories/SA-030.md) | Reconcile or retire stale Atlas projections | Open | 3 Storage | SA-009, SA-013 |
| [SA-031](planning/PI-2026-09/stories/SA-031.md) | Verify final architecture and operator-documentation consistency | Open | All: final consistency check | SA-024, SA-027, SA-029 |
| [SA-032 (stretch)](planning/PI-2026-09/stories/SA-032.md) | Define and enforce the public-read and demo-data policy | Open | 10 Interface | SA-001, SA-024 |
| [SA-033](planning/PI-2026-09/stories/SA-033.md) | Lock reproducible runtime dependencies | Open | 3 Runtime; 13 Validation | None |
| [SA-034](planning/PI-2026-09/stories/SA-034.md) | Detect silent degradation in the watchdog | Open | 9 Jobs; 10 Operations | SA-036, SA-040 |
| [SA-035](planning/PI-2026-09/stories/SA-035.md) | Surface LLM and search provider credit exhaustion | Open | 10 Operations; 10 Cost | None |
| [SA-036](planning/PI-2026-09/stories/SA-036.md) | Record durable outcomes for every critical job | Open | 9 Jobs | None |
| [SA-037](planning/PI-2026-09/stories/SA-037.md) | Keep deploys from dropping scheduled jobs | Open | 3 Runtime; 9 Jobs | SA-036 |
| [SA-038](planning/PI-2026-09/stories/SA-038.md) | Judge and retire lapsed production-verification milestones | Done | 9 Jobs; 10 Operations | None |
| [SA-039](planning/PI-2026-09/stories/SA-039.md) | Contain adaptive learning: observe-only, live weights back to defaults | Done | 5 Learning | None |
| [SA-040](planning/PI-2026-09/stories/SA-040.md) | Record per-source fetch health and detect new error types | Open | 9 Jobs; 10 Operations | None |
| [SA-041](planning/PI-2026-09/stories/SA-041.md) | Provide a read-only production status fetcher | Open | 10 Operations; 13 Validation | SA-036, SA-040 |
| [SA-042](planning/PI-2026-09/stories/SA-042.md) | Add an outside witness for missed jobs (Healthchecks.io → Telegram) | Open | 9 Jobs; 10 Operations | SA-036 |
| [SA-043](planning/PI-2026-09/stories/SA-043.md) | Run a shadow learner and record paired decisions in observe mode | Open | 5 Learning | SA-015, SA-039, SA-045 |
| [SA-044](planning/PI-2026-09/stories/SA-044.md) | Compare valuations only with same-industry peers | Open | 4 Research | None |
| [SA-045](planning/PI-2026-09/stories/SA-045.md) | Compute the five universal factors deterministically | Open | 4 Research | SA-026 |
| [SA-046](planning/PI-2026-09/stories/SA-046.md) | Read text into dated events and a Catalyst factor | Open | 4 Research | SA-026 |
| [SA-047](planning/PI-2026-09/stories/SA-047.md) | Decide with the factor engine; switch when it is not worse | Open | 4 Research; 5 Learning | SA-045, SA-046, SA-014, SA-020 |
| [SA-048](planning/PI-2026-09/stories/SA-048.md) | Charge realistic trading costs and tax in paper P&L | Done | 6 Portfolio; 7 Marksheets | None |
| [SA-049](planning/PI-2026-09/stories/SA-049.md) | Put idle cash to work in normal markets, with a 10-holding / ₹10 L floor | Open | 6 Portfolio; 8 Discovery | SA-050, SA-051 |
| [SA-050](planning/PI-2026-09/stories/SA-050.md) | Apply one sizing rule to every autopilot buy | Done | 6 Portfolio | None |
| [SA-051](planning/PI-2026-09/stories/SA-051.md) | Show the portfolio against the Nifty, with honest labels | Done | 7 Marksheets; 10 Interface | None |
| [FIX-006](planning/PI-2026-09/stories/FIX-006.md) | An anonymous watchlist read never falls back to the owner | Open | 10 Interface | None |
| [FIX-007](planning/PI-2026-09/stories/FIX-007.md) | Server logs are readable only by the owner | Done | 10 Interface | None |
| [FIX-008](planning/PI-2026-09/stories/FIX-008.md) | Operator notices reach only the owner; register the backlog's watchdog entry | Done | 10 Delivery; 10 Operations | SA-011 |
| [FIX-009](planning/PI-2026-09/stories/FIX-009.md) | Index-change notices name only the account's own stocks | Done | 10 Delivery | None |
| [PR-001](planning/PI-2026-09/stories/PR-001.md) | Remove invented figures and fixed demo values; hide operator tools from members | Done | 10 Interface | None |
| [FIX-010](planning/PI-2026-09/stories/FIX-010.md) | Every analysis writes the score history again; screens name only the viewer's stocks | Done | 3 Storage; 10 Interface | None |
| [PR-002](planning/PI-2026-09/stories/PR-002.md) | A weekly results scorecard with a "sold too early" check | Done | 7 Marksheets; 10 Delivery | None |
| [PR-003](planning/PI-2026-09/stories/PR-003.md) | Fresh overnight news: no repeats, published-date freshness, global cues | Done | 10 Delivery | None |
| [PR-004](planning/PI-2026-09/stories/PR-004.md) | Enough researched ideas to fill 10+ positions | Done | 8 Discovery | None |
| [PR-005](planning/PI-2026-09/stories/PR-005.md) | An investment case for every position | Open | 6 Portfolio | PR-006 |
| [PR-006](planning/PI-2026-09/stories/PR-006.md) | A daily company-event feed for held, watched and shelf stocks | Done | 4 Research; 9 Jobs | None |
| [PR-007](planning/PI-2026-09/stories/PR-007.md) | Plain, fact-grounded buy and sell explanations | Open | 6 Portfolio | PR-005, PR-006 |
| [PR-008](planning/PI-2026-09/stories/PR-008.md) | "Your stocks overnight" at the top of the morning brief | Open | 10 Delivery | PR-003, PR-006 |
| [PR-009](planning/PI-2026-09/stories/PR-009.md) | Exit on evidence, not on a price-path miss (shadow, then switch) | Done | 6 Portfolio | PR-002, PR-006 |
| [PR-010](planning/PI-2026-09/stories/PR-010.md) | Four screens for members; an Operator menu for the owner | Open | 10 Interface | PR-001 |
| [PR-011](planning/PI-2026-09/stories/PR-011.md) | New data: promoter and insider trades, pledges, shareholding changes | Done | 4 Research; 8 Discovery | PR-006 |
| [PR-012](planning/PI-2026-09/stories/PR-012.md) | Choose models by role, benched on our own data; refresh cost rates | Open | 3 Configuration | PR-007 |
| [FIX-011](planning/PI-2026-09/stories/FIX-011.md) | NSE's per-symbol meta API is gone: restore the surveillance and suspension guards and an industry source | Open | 4 Research; 8 Discovery | None |
| [FIX-012](planning/PI-2026-09/stories/FIX-012.md) | CI is red since 13 Oct: make FIX-007's log-route guard work on any FastAPI | Done | 13 Validation | None |
| [FIX-013](planning/PI-2026-09/stories/FIX-013.md) | Move the fast and reasoning LLM tiers to cheaper current models | Done | 3 Configuration | None |
| [FIX-014](planning/PI-2026-09/stories/FIX-014.md) | Above the 75% cap, a promoter wash must not score as insider buying | Open | 8 Discovery | PR-011 |
| [FIX-015](planning/PI-2026-09/stories/FIX-015.md) | The shock exit reads the re-forecast's trigger, not its sentence | Open | 6 Portfolio | PR-009 |
| [FIX-016](planning/PI-2026-09/stories/FIX-016.md) | Fix the evidence exit's inputs and its switch gate before the shadow starts | Done | 6 Portfolio; 7 Marksheets | PR-009 |
| [PR-013](planning/PI-2026-09/stories/PR-013.md) | Show where losses come from and what waiting costs | Open | 7 Marksheets | PR-002, PR-009 |
| [FIX-017](planning/PI-2026-09/stories/FIX-017.md) | The holding sync reads every NSE corporate-action row it is given, under NSE's code | Open | 6 Portfolio | None |
| [FIX-018](planning/PI-2026-09/stories/FIX-018.md) | The switch gate sets aside a decision whose result can never be known: named, and within a cap | Done | 6 Portfolio; 7 Marksheets | FIX-016 |
| [FIX-019](planning/PI-2026-09/stories/FIX-019.md) | Find out why NSE lists no corporate action for 14 configured codes, and map the stale ones | Done | 4 Research; 6 Portfolio | None |
| [FIX-020](planning/PI-2026-09/stories/FIX-020.md) | Correct the configured codes NSE does not list, and AAVAS's sector | Open | 4 Research | None |
| [FIX-021](planning/PI-2026-09/stories/FIX-021.md) | A Google redirect link is not an article's identity | Done | 4 Research | None |
| [FIX-022](planning/PI-2026-09/stories/FIX-022.md) | The tax estimate at each lot's own cost, and SA-048's loose ends | Open | 7 Marksheets | None |

### Maintain documentation with each story

Each implementation updates the affected sections so that they describe the
new behaviour as current design. It does not add a change note. It also sets
the story's status in the table above, adjusts the relevant human test cases and
regenerates the PDF when this Markdown changes. Commits, reviews and deploys
belong in STATE.json and the evidence receipts, not in this document. Measured
production state belongs in section 1's table. SA-031 is the final
cross-document consistency check, not a reason to postpone normal
documentation.

## 13. Validation and KT sequence

The DOC-001 [receipt](planning/PI-2026-09/evidence/DOC-001-implementation.md)
and [review](planning/PI-2026-09/evidence/DOC-001-review.md) record how this
document's first current-code edition was checked; each story's receipt
records its own tests. Local validation uses Python 3.13 on Windows;
production Docker and CI use Python 3.11 on Linux. Focused checks do not imply
full-suite or platform-parity acceptance.

### The test suite's hermetic boundary

Every `pytest` run passes through [tests/hermetic.py](../tests/hermetic.py),
which [tests/conftest.py](../tests/conftest.py) imports before any application
code. The same four rules hold on a laptop with a `.env` and on a fresh CI
checkout:

| Rule | What it does | Example |
|---|---|---|
| No `.env`, no shell settings | dotenv is off, and every variable the application reads is removed, so settings come from `config.yaml` and the code fallbacks. | A developer's `.env` says `RL_LEARNING_MODE=observe`; the suite still runs the shipped `adapt`. |
| No outbound network | Non-loopback sockets, DNS and `curl_cffi` (yfinance's transport, which bypasses Python sockets) raise `OutboundNetworkBlocked`. A test that triggers one fails, even if the application swallowed the error. | An unmocked thesis review would call OpenRouter; the test fails, naming `thesis_reviewer.py` and `openrouter.ai:443`. |
| An empty working directory | The application keeps runtime state under `data/` and `outputs/` relative to the working directory, as under `/app` on Railway. Each test runs in its own empty temporary directory, seeded only with the three tracked files the application reads by relative path. | A test that toggles a managed ticker changes its sandbox copy, not the checkout's `data/managed_tickers.json`. |
| The checkout is off limits | An audit hook refuses any access to the checkout's `data/`, `logs/` and `outputs/`, and any write elsewhere in it. | A test reading local MARUTI predictions fails; the discovery test builds its own predictions tree. |

Why it is this strict: on 2026-09-27 a socket guard alone saw 74 blocked
attempts, while yfinance's `curl_cffi` requests were invisible to it. The full
boundary then found 286 Yahoo requests, 178 OpenRouter attempts and 124 NSE
session attempts. The tests had also been writing 149 paths in the checkout
(35 targets once temp files are grouped) and reading 24 untracked runtime
files. Most network traffic came from tests that booted the full app, whose
startup ran the RL self-heal thread; those tests boot the app as an API-only
worker.

The boundary does not reach child processes (the eval CLI smoke test and the
browser suite); they inherit only the cleaned environment. It sees Python's own
socket, DNS and file calls, and `curl_cffi`. It does not refuse a directory
listing or existence check, a native library's own file access (pyarrow, or
SQLite given a `file:` URI), a Windows short-name spelling of the checkout, or
a numeric-IP connection on the Windows asyncio loop. The application builds one
absolute checkout path, in the startup calendar check, and the test fixture
stubs it. A Windows-only retry in
[core/utils/atomic_io.py](../core/utils/atomic_io.py) absorbs the transient
`PermissionError` of a rename on Windows; Linux renames never retry.

### Continuous integration

The CI workflow, [.github/workflows/ci.yml](../.github/workflows/ci.yml), runs
three jobs on Linux with Python 3.11 and no secrets:

- the whole `tests/` tree;
- the broad-exception guard
  ([scripts/ci/check_broad_except.py](../scripts/ci/check_broad_except.py))
  and `check_kt_docs.py`;
- the chat-rendering browser suite in Chromium.

The guard fails when new code catches every exception without logging,
re-raising or using it. The 154 handlers that already did so are grandfathered
in a burn-down list; they were not reviewed one by one. The list counts
handlers per function, so a change that fixes one grandfathered handler and
adds another in the same function passes. Test-only tools are pinned in
[requirements-test.txt](../requirements-test.txt). The runtime packages still
come from the unpinned `requirements.txt`. **Planned:** a lock (SA-033).

### KT documentation tools

Maintainer commands, with the required local dependencies installed:

```text
python scripts/docs/run_kt_checks.py
python scripts/docs/build_kt_pdf.py
python scripts/docs/check_kt_docs.py
```

The test runner copies tracked source to ignored `analysis_data/`, excludes
`.env`/runtime stores, disables dotenv, and blocks external transports and test
subprocesses. It exercises a fixed selection of existing tests, not all
independent financial invariants. The PDF builder needs Python `markdown2` and
local Playwright/Chromium; it does not start the application. The checker
validates links, the roadmap rows against STATE.json, the job table against
the scheduler, selected repository config values, the header revision and the
PDF's freshness.

### KT sessions

| KT session | Walkthrough |
|---|---|
| Product/data | Sections 1–4: production state, a symbol, its identity, source dates and statuses, dimensions, the decision gate and the research verdict. |
| Predictions/learning | Section 5: envelope row to review checks, feedback, weights or proposals, lessons and dossier dates; explain the grading gaps and the learning mode. |
| Portfolio/marksheets | Sections 6–7: advice to transaction, the data and identity holds, the P/L example and different evaluation rules. |
| IPO/discovery | Section 8: calendar to captured facts, history, post-listing candidates, and the dark P3 path from deep dive to a stored, narrated and graded verdict. |
| Operations/roadmap | Sections 9–12: scheduled work to persisted output and per-ticker outcomes, outbox states and the dead-letter view, the backup drill and restore runbook, the watchdog and the operations backlog, and the planned redesign. |

Practical, non-code-intensive duties are in the separate
[Team Human Testing Guide](TEAM_TESTING_GUIDE.md). Testers should be able to
explain outputs and compare evidence without reading prompts or reviewing code.
