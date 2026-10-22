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
  - `cost_rates` uses the 22 Oct list prices, and the previous tiers are kept for rollback
    pricing.
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

| Model | JSON parsed | Verdict / drivers | Restraint | Avg latency | Cost (6 calls) |
|---|---|---|---|---|---|
| z-ai/glm-5.2 (old reasoning) | 6/6 | 3/3, 2/3 | 6/6 | 2.3 s | $0.00512 |
| **xiaomi/mimo-v2.6-pro** | **6/6** | **3/3, 3/3** | **6/6** | 3.2 s | $0.00162 |
| deepseek/deepseek-v4.1-flash-1017 | 6/6 | 3/3, 2/3 | 6/6 | 1.1 s | $0.00135 |
| inclusionai/ling-3.1-flash | 6/6 | 3/3, 3/3 | 6/6 | 15.4 s | $0.00035 |
| anthropic/claude-haiku-5.5 | **1/6** | — | 1/1 | 2.4 s | $0.00164 |
| qwen/qwen3.6-flash (old fast) | 6/6 | 3/3, 1/3 | 6/6 | 2.1 s | $0.00116 |
| qwen/qwen3.8-flash | 6/6 | 3/3, 0/3 | 6/6 | 3.1 s | $0.00070 |

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
  differently. DeepSeek's and Alibaba's endpoints for V4.1 Flash 1017 double their price on
  weekdays 06:30–09:30 and 11:30–15:30 IST.
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
  priced correctly.
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
   - the pre-open log has no "LLM shock rating failed" line.
3. **Rollback:** revert the `config.yaml` tier lines, or set `LLM_MODEL_FAST` /
   `LLM_MODEL_REASONING` on Railway to `qwen/qwen3.6-flash` / `z-ai/glm-5.2`. Either one
   redeploys.
