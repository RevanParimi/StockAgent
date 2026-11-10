# FIX-013 implementation receipt — move the fast and reasoning LLM tiers to cheaper current models

- **Story:** [FIX-013](../stories/FIX-013.md), user-requested. The owner's words, 22 Oct 2026 (IST):
  - about 22:30: "the LLMs we are using seems very old, can you research … (cost and efficiency
    are priority …)", then "correction, i didnt mean openai, it can be any model";
  - about 23:00: "reasoning - anthropic/claude-haiku-5.5:batch looks good … rest suggested replace
    also looks good to go. Ya go ahead and proceed with these";
  - about 23:25: chose "Split vendors (Recommended)", after Haiku 5.5 and Qwen3.8 Flash failed the
    benches below;
  - about 23:35: "Once you update it, go ahead with commit and push, dont wait for me to say yes
    again".
- **Context, a recorded deviation:** the research, benches, implementation, commit and push all
  ran in **one conversation** (session `stockagent-main-62`), at the owner's word. A same-conversation self-review was done. It
  is not the fresh review, which is still required. STATE: `review_required`, committed and pushed.
- **Concurrency:** this ran beside session `stockagent-main-a6`'s FIX-012 implementation. Edits
  waited for its "clear" (23:40 IST). The commit holds only this story's paths.
- **Baseline:** `0a798e1`.
- **Production:** the push redeploys Railway. No Railway variable was read or changed.
  Production verification is pending (below).

## Rework 1 (23 Oct 2026, about 10:57–11:30 IST)

**Context.** Session `stockagent-main-48`, a new conversation opened with "continue". Peers were
idle at the start; session `stockagent-main-62` last wrote its own ignored `analysis_data/fix013/`
files at 10:27. It answers the fresh review's CHANGES REQUESTED
([review receipt](FIX-013-review.md)). It includes a same-conversation self-review, which is not
the fresh re-review. **Status after:** `review_required`. Nothing was committed, pushed, deployed
or configured. No production state was read, no LLM or outside endpoint was called, and no
message was sent.

**Input.** The reviewed revision `560d18f` (diff `156a0b84…`); `HEAD` `8c5afed` touches none of
its paths. The rework is the working tree on top of it.

### In one example (L2)

A weekday at 08:45 IST. The pre-open check sends one fast-tier request with JSON mode on.
OpenRouter may serve DeepSeek V4.1 Flash 1017 from any of 33 hosts, and one of them (BaseTen) does
not support `response_format`.

- **Reviewed code:** that host could serve the request without JSON mode. If it answered
  `` ```json {"severity": 0.8, "direction": "risk_off", …} ``` ``, the strict parse failed, and the
  morning was recorded as "neutral, no shock" with a successful telemetry row and one warning line.
  No contradicted forecast was re-run.
- **Now:** the request carries `provider.require_parameters`, so OpenRouter serves it only from
  the 32 hosts that support every parameter sent (DeepSeek's own among them). The 0.8 risk-off
  rating is read. If no such host is available, OpenRouter refuses the request: the telemetry row
  is a failure and the "LLM shock rating failed" line appears, instead of a quiet neutral.

### Changes

| Finding | Change |
|---|---|
| **R-AC6** (required) | `CODEBASE.md`: the `/ui/chat/stream` row describes the current design (the fast tier with reasoning off; after two tries that hit a rate limit or 5xx, the reasoning tier, a different vendor). The section intro is rewritten without bench dates: the three tiers, the reasoning-off requirement, the two harnesses, and that `config.yaml` lists rejected and retired models. The stray `LLM_MODEL` history line, which sat inside the table and split it in two, became one sentence of that intro. |
| **M1** | Guide 11-L: engineering also shows the 16:30 run's log lines, and the expected result requires no `unified analyst failed -> legacy fallback`, `[UnifiedAnalyst] run() failed` or `response truncated` line, with the reason (the analyst's row is written before its reply is read). This receipt's production step 2 gains the same check. STATE's steps already had it (the review's edit). |
| **L1** | `config.yaml`'s `cost_rates` comment, D2 below and the PR-012 card: `z-ai/glm-5.2` keeps its last measured rate (17 Jul), not a 22 Oct price; its hosts' prices vary widely, so a rollback's run costs are approximate. The rate itself is unchanged (RW-D2). PR-012 also records that the analyst's own prompt was not benched on the new reasoning model. |
| **I1** | `config.yaml` and the caveat below: DeepSeek's own host doubles on weekdays 06:30–09:30 and 11:30–15:30 IST, Alibaba's every day 05:30–19:30 IST (both read from the saved endpoint data). The Gate 2 table's restraint column is 3/3, the FeedbackAgent task only (recounted from the raw files). `scripts/reasoning_bench.py` now prices DeepSeek V4.1 at the base rate, as `config.yaml` and `model_bench.py` do, and the table shows $0.00067 with a note on the recorded $0.00135. |
| **L2** (recommended) | `core/intelligence/rl/workflows/preopen_check.py`: the call's `extra_body` is `JSON_MODE_EXTRA_BODY` plus `"provider": {"require_parameters": True}`; docstring and comment say why. `docs/RL_DESIGN.md` section 27.3, `CODEBASE.md`'s FAST row and `config.yaml`'s fast-tier comment describe it. Two tests (below). |

### Decisions (delegated, recorded)

- **RW-D1. L2 is taken, with `require_parameters` rather than a fence strip.** A fence strip
  would still lose a prose-first reply, and it would hide the cause. The pin removes the host that
  ignores JSON mode. Its cost: when none of the 32 eligible hosts is up, the morning's rating
  fails visibly instead of being served without JSON mode. The pin is scoped to the pre-open call,
  the only fast-tier JSON call. The reasoning and bulk tiers' hosts all support
  `response_format`, so `JSON_MODE_EXTRA_BODY` itself is unchanged.
- **RW-D2. glm-5.2's rate keeps its 17 Jul value; only the wording changes.** Its 35 hosts range
  from $0.03 to $2.31 per M in, so no single price is right. A rollback is unlikely, and changing
  the rate would also change a tracked test's hand-worked value for no production benefit.

### Tests

- **New** (`tests/unit/intelligence/rl/test_preopen_check.py`): the real OpenAI SDK over an
  in-memory `httpx.MockTransport`, answered by a fake OpenRouter that follows its documented rule.
  Without `require_parameters` it serves the first host listed, which does not support
  `response_format` and fences its JSON. With it, only hosts that support every parameter in the
  request body are eligible, and with none it answers OpenRouter's 404.
  - `test_shock_is_rated_from_a_host_that_honours_json_mode`: a 0.8 risk-off night is rated 0.8
    risk-off; one request, carrying the fast-tier id, `json_object`, reasoning off and the pin;
    one successful telemetry row.
  - `test_no_eligible_host_is_a_recorded_failure_not_a_quiet_neutral`: with only the host that
    lacks `response_format`, the result is neutral, the telemetry row is a failure, and the
    warning line is logged.
- **Bite** (`analysis_data/fix013/rework1/rw_swap_plugin.py`, `RW_SWAP`, in memory only): HEAD's
  file fails both new tests. Mutants M1 (the pin set false), M3 (`allow_fallbacks` instead) and M4
  (`response_format` dropped) fail both; M2 (reasoning-off dropped, pin kept) fails the first. The
  other 15 tests pass in every variant.
- **Targeted run** (the original receipt's six files): **77 passed, 1 failed**, the known
  `test_orchestrator_instantiates_openai` (review I5: fails alone, identically on `0a798e1`).
- **The reviewer's cases** (`analysis_data/fix013_review/test_rv_fix013.py`, hermetic) on the
  rework: 17 passed, 1 failed. The failure is R5, at its assertion that the pre-open request's
  `extra_body` is exactly reasoning-off with no `provider` key (its lines 237–238, written to show
  L2 in the reviewed code). That is the L2 change. R5's parse cases (plain, `<think>`, fenced,
  prose-first) are unchanged: the parser is unchanged.
- `scripts/ci/check_broad_except.py`: OK (151 grandfathered). `scripts/docs/check_kt_docs.py`:
  errors `[]`.
- **Full suite:** `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider`, 11:07–11:18 IST: **5,564 passed, 12 skipped, 1 xfailed, 0 failed** (613 s). That is FIX-012's 5,562 plus the 2 new tests; the SA-009 store-migration flake did not recur. The suite left no `data/` change.

**Not exercised:** no live call with the pin. The first 08:45 run after this rework is deployed
shows it: telemetry `success` 1 and no "LLM shock rating failed" line.

### Review input for the fresh re-review

- **Manifest:** [FIX-013-manifest.json](FIX-013-manifest.json), 18 files (FIX-013's 16 plus
  `preopen_check.py` and its test file), review-input sha256
  `d16cfe2ca3fcfb094cb04be88283b76a8ef63aa71c2bb0d7dcc1340b627a410b`, 0 mismatches. Against
  `560d18f`, exactly the 8 rework paths differ.
- **Rework diff:** `git diff 560d18f` over the 8 paths, 25,079 bytes, sha256
  `3d6d3a005e7377584e462023113fc5d622705f4b67fa81c4300cd6892a45293f`.
- **Cumulative diff:** the original recipe (baseline `0a798e1`) over the 18 paths, 47,653 bytes,
  sha256 `4645aa6e3fe17d3c8239ff2e00fdbf0fa74fd02c668b010ab850d8e15078f5cd`. Both are written by
  `analysis_data/fix013/rework1/rw_digest.py`.
- **Excluded bookkeeping:** this receipt, STATE, HANDOFF, the review receipt, and the owner's
  `docs/README.md` line.
- **Not changed:** `src/backend/shared/config/settings/base.py`, `tests/unit/test_llm_cost.py`
  and the other FIX-013 paths. The KT names no model, so the PDF is unchanged.

### Production, measured so far (read-only, not by this conversation)

Session `stockagent-main-62` ran a read-only probe at the owner's "also check prod", 23 Oct
10:26 IST (counts only; summary in the ignored `analysis_data/fix013/prod_probe_2026-10-23_1026IST.txt`):

- the owner listed Railway's variables: no `LLM_MODEL_*` (production step 1 done);
- since the 00:10 deploy: 41 LLM calls, 41 successful, including the 08:45 pre-open check on
  `deepseek/deepseek-v4.1-flash-1017` (1 of 1); in the 24 h before, 148 calls and 0 successful
  (the dead key, fixed on 22 Oct);
- no `LLM shock rating failed`, `legacy fallback`, `run() failed`, `response truncated`, JSON
  parse, 429, 401 or degraded-FeedbackAgent line;
- not yet seen: any `xiaomi/mimo-v2.6-pro` call (no analysis run since the deploy) and any chat
  turn. The 16:30 run and 11-L's chat questions remain.

## What it does, in one example

A unified-analyst call reads about 7,440 tokens and writes 2,957.

- **Before:** `z-ai/glm-5.2` at $1.218/$3.828 per M cost about **$0.0204**.
- **After:** `xiaomi/mimo-v2.6-pro` at $0.435/$0.87 costs about **$0.0058** (−72%).

The four-question chat battery cost $0.0118 and took 20.6 s a turn on `qwen/qwen3.6-flash`. On
`deepseek/deepseek-v4.1-flash-1017` it cost **$0.0059** and took **14.0 s**, with no fabricated
source, skipped tool or broken answer.

## The change

- **`config.yaml`:**
  - `model_fast` is `deepseek/deepseek-v4.1-flash-1017`, `model_reasoning` is
    `xiaomi/mimo-v2.6-pro`, and bulk is unchanged.
  - The tier rationale is rewritten as current design, with the rejected candidates listed.
  - `cost_rates` uses the 22 Oct list prices for the current tiers, and the previous tiers keep
    their rates for rollback pricing (D2).
- **`src/backend/shared/config/settings/base.py`:** the same fallbacks and `_DEFAULT_COST_RATES`.
  The reasoning fallback had still named `qwen/qwen3.7-max`.
- **`services/api/routes/ui_data.py`:** the two chat fallback literals used when settings fail to
  import. Nothing else.
- **`tests/unit/test_llm_cost.py`:**
  - The old test asserted that the reasoning call costs more than 5 × the bulk flat rate. MiMo
    is 4.83 ×, so that bound no longer measured AUD-105's invariant.
  - It now asserts that the reasoning call is priced at its own table rate and is not the bulk
    flat cost.
  - A new parametrised test checks both new models against hand-worked values: 0.00580899 and
    0.0028902 for 7,440 in and 2,957 out.
- **`scripts/reasoning_bench.py`, `scripts/model_bench.py`:**
  - Their `PRICES` hold the 22 Oct ids and prices, so tonight's runs can be repeated.
  - `model_bench.py` takes model ids as arguments, as `reasoning_bench.py` already did.
- **Living docs:** the tier tables and passages in CODEBASE, README, AGENTIC_DESIGN,
  ARCHITECTURE, CHAT_ARCHITECTURE, PRODUCT_MAP and RL_DESIGN describe the current models.
  - README's row had called DeepSeek "the chat default"; it now matches the code.
  - TECHNICAL_DESIGN (the KT) names no model, so the PDF is unchanged.
- **TEAM_TESTING_GUIDE:** new case **11-L**, the first trading morning after a tier change: chat
  answers, telemetry model ids and the pre-open parse.
- **PR-012 card:** its "Today" table shows the new tiers. It says what FIX-013 did **not** do:
  the role bench on stored bundles, grounding counts, blind scoring and the bulk tier. PR-012
  stays `todo`.

## Evidence: how the models were chosen

Sources: OpenRouter's public catalogue (`/api/v1/models`, read 22 Oct, 22:37 IST, 468 models) and
Artificial Analysis Intelligence Index v4.3.2. AA scores are measured with reasoning on. Every
call site here runs with reasoning off, so AA was used only to shortlist. The benches decided.

**Gate 1 — reasoning must be optional on OpenRouter** (`reasoning.mandatory`). This ruled out
`z-ai/glm-5.3`, `z-ai/glm-5.3-flash`, `minimax/minimax-m3.1-flash`, `google/gemini-3.8-flash` and
`reflection/beam-1.0-501b-a23b`.

**Gate 2 — `scripts/reasoning_bench.py`.** This is the production JSON shape with reasoning off,
temperature 0.1, 1,200 tokens and `json_object`. It runs 2 tasks × 3 trials: the FeedbackAgent
post-mortem and the aggregator verdict, with schema, slug, verdict, top-driver, range and restraint
checks.

| Model | JSON parsed | Verdict / drivers | Restraint (FeedbackAgent task) | Avg latency | Cost (6 calls) |
|---|---|---|---|---|---|
| z-ai/glm-5.2 (old reasoning) | 6/6 | 3/3, 2/3 | 3/3 | 2.3 s | $0.00512 |
| **xiaomi/mimo-v2.6-pro** | **6/6** | **3/3, 3/3** | **3/3** | 3.2 s | $0.00162 |
| deepseek/deepseek-v4.1-flash-1017 | 6/6 | 3/3, 2/3 | 3/3 | 1.1 s | $0.00067* |
| inclusionai/ling-3.1-flash | 6/6 | 3/3, 3/3 | 3/3 | 15.4 s | $0.00035 |
| anthropic/claude-haiku-5.5 | **1/6** | — | 1/1 | 2.4 s | $0.00164 |
| qwen/qwen3.6-flash (old fast) | 6/6 | 3/3, 1/3 | 3/3 | 2.1 s | $0.00116 |
| qwen/qwen3.8-flash | 6/6 | 3/3, 0/3 | 3/3 | 3.1 s | $0.00070 |

\* At the base list price, $0.15/$0.60. The raw file records $0.00135: at the time,
`reasoning_bench.py` priced this model at its host's weekday peak rate, $0.30/$1.20, though the run
was off-peak. Restraint is checked only on the FeedbackAgent task (3 runs per model); Haiku's 1/1 is
its one parseable FeedbackAgent reply. (Both corrected in rework 1.)

- **Haiku:** in 4 of 6 runs it wrote its working before the JSON, and in 1 it fenced the JSON.
  The aggregator, thesis reviewer and control lane parse after only a fence strip, so those
  replies would fail there.
- **`math_ok` is 0 for every model,** the old tiers included. With reasoning off, each one does
  the nine-term weighted mean in its head and lands within 0.002–0.028 of 0.5412. Production
  computes the composite itself (`signal_aggregator.py:144`). Most "drivers" misses swap
  sales_demand and fundamentals (0.1116 against 0.1136). qwen3.6-flash twice put
  valuation_catalyst second.

**Gate 3 — `scripts/model_bench.py`:** the real chat pipeline (pre-router, tools, grounding,
sanitiser), 4 questions per model, run 23:16–23:22 IST.

| Model | Fabricated / skipped / broken | Avg turn | Cost (4 turns) |
|---|---|---|---|
| qwen/qwen3.6-flash (old fast) | 0 / 0 / 0 | 20.6 s | $0.01179 |
| **deepseek/deepseek-v4.1-flash-1017** | **0 / 0 / 0** | **14.0 s** | **$0.00586** |
| xiaomi/mimo-v2.6-pro (the fallback) | 0 / 0 / 0 | 14.7 s | $0.01569 |
| anthropic/claude-haiku-5.5 | 1 / 0 / 0 | 13.2 s | $0.00745 |
| qwen/qwen3.8-flash | 0 / 0 / 0 | 33.8 s (one turn 47.2 s) | $0.01101 |

- The transcripts were read by hand. DeepSeek's answers cite dated headlines from the fetched
  news.
- **Qwen3.8 Flash** is OpenRouter's `Qwen3.8-Flash-Next`, a preview. One turn exceeded the 45 s
  chat budget.
- **The owner's choice:** split vendors. The fast tier is DeepSeek and the reasoning tier, which
  is also the chat fallback, is Xiaomi. The alternative put all three tiers on DeepSeek.

**Caveats:**
- The samples are small: 6 JSON calls and 4 chat turns per model. They catch gross failures, not
  fine quality differences.
- The chat runs saw live news minutes apart.
- Nothing here measures forecast accuracy. Successful calls are not evidence of better verdicts.
- List prices are not billed prices, because OpenRouter routes across hosts that charge
  differently. For V4.1 Flash 1017, DeepSeek's own endpoint doubles its price on weekdays
  06:30–09:30 and 11:30–15:30 IST, and Alibaba's every day 05:30–19:30 IST (corrected in
  rework 1).
- OpenRouter `:batch` slugs are the 24-hour asynchronous Batch API, so none of these tiers can
  use them.

**Spend:** about **$0.064** on OpenRouter, from the bench cost columns. Telemetry and the
LLM-failure owner alert were patched off for the chat bench.

**Raw outputs:** in `analysis_data/fix013/`, which is ignored and exists in this checkout only.

| File | SHA-256 |
|---|---|
| `reasoning_bench_tiers_2026-10-22.json` | `094ff96c…` |
| `reasoning_bench_fastjson_2026-10-22.json` | `214d8558…` |
| `model_bench_2026-10-22.json` | `50e72143…` |
| `openrouter_models_2026-10-22.json` | `5eb4a7f7…` |

## Tests

- **Targeted run:** `.stockai/Scripts/python.exe -m pytest -q tests/unit/test_llm_cost.py
  tests/unit/shared/test_config.py tests/unit/shared/test_config_loader.py
  tests/contract/test_phase0_llm_migration.py tests/unit/test_chat_llm_hardening.py
  tests/unit/intelligence/rl/test_preopen_check.py`. Result: **75 passed, 1 failed.**
  - The failure is `test_phase0_llm_migration.py::TestOrchestratorUsesOpenAI::test_orchestrator_instantiates_openai`
    ("OpenAI called 10 times").
  - It was already failing: it fails the same way on untouched `0a798e1` in an isolated worktree
    (1 failed, 19 passed). It is order-dependent, and it passes inside the full suite.
- **Full suite:** `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider`, run 23:40–23:50
  IST. Result: **5,561 passed, 1 failed, 12 skipped, 1 xfailed** (585 s).
  - The orchestrator test above passes inside the full suite.
  - The one failure is
    `tests/unit/intelligence/rl/test_store_migration_sa009.py::test_a_refused_store_is_retried_and_the_status_never_overstates`:
    a `FileNotFoundError` on a file under its pytest temp quarantine folder
    (`…/stores/automobile/SUZLON/SUZLON_agent_weight_memory.json`).
  - **It was already failing intermittently, and it is unrelated to the LLM code.** It failed
    1 run in 3 of that file in this tree, and 1 run in 6 on untouched `0a798e1` in an isolated
    worktree. FIX-012's full-suite runs earlier that evening passed it. This is found on the way,
    not fixed here.
- **Settings as loaded:** FAST `deepseek/deepseek-v4.1-flash-1017`, REASONING
  `xiaomi/mimo-v2.6-pro`, BULK `deepseek/deepseek-v4-flash`. The analyst-call cost is 0.005809
  (glm-5.2: 0.020381).

## Review input

- **Paths:** 16, of which 15 are tracked and 1 is new (`stories/FIX-013.md`).
- **Diff:** 34,810 bytes, sha256
  `156a0b84107bd7a55cc13cc3c1b15c12fb6a9632f3e58943a70c8240abc6b78e`. The recipe and per-file
  hashes come from `python analysis_data/fix013/digest.py`. Paths are sorted, tracked paths are
  diffed against `0a798e1`, and the new file against `/dev/null`.
- **Excluded bookkeeping:** this receipt, `STATE.json` and `HANDOFF.md`.
- **The commit:** it holds exactly these paths plus that bookkeeping. `STATE.json` and
  `HANDOFF.md` are staged as `0a798e1` plus this story's splice, so FIX-012's uncommitted edits
  stay out.

## Decisions for review

- **D1:** split vendors, the owner's choice, rather than all-DeepSeek. All-DeepSeek costs less
  for reasoning, but it removes the chat fallback's vendor independence.
- **D2:** retired tiers keep their `cost_rates` entries, so an `LLM_MODEL_*` rollback is still
  priced: `qwen/qwen3.6-flash` at its 22 Oct list price, `z-ai/glm-5.2` at its last measured rate
  (17 Jul, $1.218/$3.828). glm-5.2's 22 Oct hosts vary widely (first party $1.40/$4.40), so run
  costs after a rollback are approximate. (Wording corrected in rework 1; the rate is unchanged.)
- **D3:** the fast tier's rate is recorded at the base list price ($0.15/$0.60), not the
  peak-hour price ($0.30/$1.20).
- **D4:** the AUD-105 test asserts the invariant (the call is priced at its own rate, not the bulk
  flat rate), with hand-worked values. It no longer uses a price-ratio bound.
- **D5:** FIX-013 does not satisfy PR-012, which stays `todo`.

## Production verification (pending)

1. **The owner checks** that no Railway variable from A to O is named `LLM_MODEL_FAST`,
   `LLM_MODEL_REASONING` or `LLM_MODEL_BULK`. The list the owner pasted at 23:35 started at
   `PREDICTION_DATA_DIR`. If one exists, it overrides `config.yaml`.
2. **On the first trading morning,** run guide case 11-L:
   - telemetry rows carry the new ids, with successful calls for the 08:45 pre-open check, chat
     and the analyst;
   - the pre-open log has no "LLM shock rating failed" line;
   - after the first 16:30 run, the log has no `unified analyst failed -> legacy fallback`,
     `[UnifiedAnalyst] run() failed` or `response truncated` line. The analyst's telemetry row is
     written before its reply is parsed, so a successful row alone does not show that the reply
     was usable; an unparseable one sends the stock back to the bulk-tier legacy agents (added in
     rework 1, review M1). Every `data_health` row from that run also shows `dimensions_scored`
     equal to `dimensions_expected`. A JSON reply without the dimensions logs none of those lines
     (re-review RR-L2).
3. **Rollback:** revert the `config.yaml` tier lines, or set `LLM_MODEL_FAST` /
   `LLM_MODEL_REASONING` on Railway to `qwen/qwen3.6-flash` / `z-ai/glm-5.2`. Either one
   redeploys.
