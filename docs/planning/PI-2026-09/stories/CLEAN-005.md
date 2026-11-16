# CLEAN-005 — Remove the backup analysis and the old per-analyst layer it runs on

Priority: **P2** · Scope: **owner decision** of 2026-11-15 ("if the AI call fails ... we can track
LLM failure with exceptions, so we don't need backup analysis") · Estimate: **5 points** · Lane:
**decision path** (it changes what an analysis returns when the main call fails, and advice reads
analyses; fresh-session review)

Status lives in [STATE.json](../STATE.json), not this card. Depends on [CLEAN-004](CLEAN-004.md)
(the Prompt Lab reads the prompt files this card deletes). **Order:** after CLEAN-004.

**New conversation? Read first:** the evidence note
[CLEAN-003-production-counts-2026-11-15.md](../evidence/CLEAN-003-production-counts-2026-11-15.md)
(sections 1, 2 and 8), then [CLEAN-003](CLEAN-003.md)'s decision table.

## What exists

The product was first built as a team of analysts per sector: nine for automobiles (fundamentals,
sales and demand, raw materials, sentiment, policy, competition, risk, valuation, chart patterns),
four to six for banking, IT and renewables. Each analyst had its own prompt, its own data fetch and
its own model call.

In June 2026 that was replaced by **one analysis call per stock** on one shared data bundle
(`src/backend/shared/pipeline/unified_analyst.py`, `services/data/context/bundle_builder.py`). All
five paths (four sectors and the general one) run on it.

The old team was kept as a **backup**: when the one call returns nothing, the analysts run instead
(`base_orchestrator.py` `_run_agents`, setting `unified_analyst.fallback_legacy`, on).

## Why it goes

- **It almost never runs.** 21 times in about 1,360 analyses over 60 days (1.5%), all in October,
  none in November.
- **Its answer cannot become a buy, yet it still reaches a held stock.** It builds no data bundle,
  so its report carries an abstaining data gate ("no structured provenance"). The deep dive mints
  no idea from it. But the gate is in `record` mode, and a held stock's daily review stops only
  when the gate is enforcing (`daily_review.py` `_review_gate`), so there the old analysts' verdict
  is used like a real one (code inspection; how often this happened is the 21 runs above).
- **It is a different, older method.** The code's own comment puts it at six to eight times the
  search cost (`services/data/stores/fallback_events.py`); that figure was never measured, so do
  not quote it as a saving.
- **A failed model call is already visible**: `core/delivery/ops_alerts.py` `record_llm_result`
  alerts at 10 consecutive failures.
- It is about 5,000 lines to keep correct: 30 analyst classes (1,307 lines), 25 per-analyst prompt
  files (1,813), their own data builder (852), the base class (447) and the shared analyst and
  worker-pool code (656). The `langgraph` package is installed only for it.

## Step 1 — "no analysis" instead of a backup analysis (commit 1)

Set `unified_analyst.fallback_legacy: false`. **Before that, trace every caller** and write down
what each does when the analysis comes back with no scored dimension:

| Caller | Where |
|---|---|
| Weekly deep dive | `core/discovery/deep_dive.py` line 161 |
| Daily review's re-analysis | `core/intelligence/rl/workflows/daily_review.py` line 350 |
| Monthly forecast | `core/intelligence/rl/workflows/generate_forecast.py` line 334 |
| A scheduled analysis | `services/scheduler/python/scheduler.py` line 1577 |
| On-demand analysis (three routes) | `services/api/routes/analyse.py` line 62, `stream.py` line 134, `ui_data.py` line 2082 |

Required, each with an invariant test:

1. No caller books a buy, a sell, a size change, a forecast or a grade from an analysis that
   scored nothing.
2. A scheduled caller skips the stock for that run, logs it once and carries on with the others.
3. The user-facing routes say plainly that today's analysis could not be produced. They show no
   verdict and no score.
4. The day's count of failed analyses is where the owner looks: reuse the slot the fallback count
   has today in `GET /scheduler/status`.

**Example.** The model provider is down at 16:30. Today a held stock gets a verdict from the old
analysts and the advisor reads it. After this step the stock is skipped for that review, the
advisor acts on nothing new for it, and the status page shows "1 analysis failed today".

## Step 2 — delete the layer (commit 2, after step 1's suite passes)

Prove each unused first (every import, string reference, route, job, test, document link):

| What | Where |
|---|---|
| The worker pool | `src/backend/shared/pipeline/base_orchestrator.py`: `_build_worker_pool_graph`, `_run_via_graph`, its async twin, `_sub_agents`, the import of `SalesDemandAgent` at line 20; `src/backend/shared/pipeline/graphs/` |
| The `langgraph` requirement | `requirements.txt` line 2. On 15 Nov only `base_orchestrator.py` and `pipeline/graphs/nodes.py` import it. Removing a package changes the production build: say so in the receipt |
| The analysts | `src/backend/sectors/*/agents/`, each sector's `config/registry.py`, `_sub_agents` in each `pipeline/orchestrator.py` |
| The per-analyst prompts | `src/backend/sectors/*/prompts/*.py` **except** `unified.py`; `generic/prompts/dimensions.py` if only the generic orchestrator's `_sub_agents` reads it |
| The shared pieces | `src/backend/shared/pipeline/base_agent.py`, the shim `core/pipeline/base_agent.py`, `src/backend/shared/agents/universal/`, `services/data/context/builder.py` (read only by `base_agent.py`) |
| The fallback record | `services/data/stores/fallback_events.py`, its field in `services/api/routes/scheduler_api.py`, `tests/unit/test_fallback_events.py` |
| The settings | `UNIFIED_ANALYST_FALLBACK_LEGACY` and its `config.yaml` key |

**One trap.** `unified_analyst.sectors` lists the paths on the one-call method. A path missing from
it runs the old analysts as its main route, and an empty value sends every path there. After this
card that setting must not be able to route anywhere: remove it, or fail closed with an error.
`TestAnalyseAsyncDispatch` in `tests/unit/test_orchestrator_unified_branch.py` covers the old
route and is rewritten.

## Lose nothing good

Before deleting the per-analyst prompts, put in the receipt, per sector, what those prompts ask for
that the sector's `unified.py` does not (for example monthly vehicle registrations, deal wins,
credit costs). **Do not edit any `unified.py` in this card.** The list feeds the owner's decision
on the four sector prompts ([CLEAN-003](CLEAN-003.md), candidate 8).

## Acceptance criteria

This card takes over the legacy-pool part of the paused [SA-027](SA-027.md) and inherits its
criteria: no caller can silently bring a fallback back, and a failed analysis gives the documented
safe result with a visible reason.

- The four requirements of step 1, each with its test.
- Failure tests through the scheduled and the on-demand entry points: a timeout, an unparseable
  answer, a missing section, an exhausted retry.
- No import of a deleted module anywhere; the full suite, `scripts/ci/check_broad_except.py` and
  `scripts/docs/check_kt_docs.py` pass after each commit.
- A run with a failing model call produces no decision record for that stock.
- Living documents: KT (the analysis section), `docs/TECHNICAL_DESIGN.md` and its PDF,
  `docs/PRODUCT_MAP.md`, `CODEBASE.md`, the testing guide.
- Nothing pushed or deployed. The setting reaches production with the owner's next push.

## Not in this card

The four sector prompts of the main analysis and the general one (they stay; CLEAN-003 candidate
8). The factor table's other reader, the frozen learner (CLEAN-003 candidate 2).

## Handoff

Receipt `evidence/CLEAN-005-implementation.md`; status `review_required`; STATE and HANDOFF
together.
