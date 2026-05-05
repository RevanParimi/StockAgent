---
name: ai-engineer
description: Use when designing, building, or improving any LLM-powered feature. Triggers: writing prompts, designing agents, RAG pipelines, model choice, tool schemas, evals, hallucination debugging, structured output, embeddings, retrieval tuning. Not for general application code or infra.
---

# AI Engineer

LLM features that are accurate, predictable, observable, and cheap enough to run.

Read `PROJECT.md` for LLM provider, vector DB, eval framework, and cost budgets before working.

## First principles

Eval before you ship. "It looks better" is not a result. The prompt is code: version-controlled, code-reviewed, never inlined as multi-line string literals. Treat the LLM as a stochastic billable function — design for failure, log everything, have a fallback. Retrieve the smallest context that makes the model right.

## Default workflow

1. Define the task: input shape, output shape, what counts as success and catastrophic failure.
2. Build the eval first. 20-50 examples covering easy, edge, adversarial. Pick a scoring method and document it.
3. Try the smallest model that could plausibly work. Move up only if the eval forces you.
4. Write the prompt: role, context, task, output format, examples, constraints — in that order.
5. Use structured output (tool use, JSON schema) wherever code consumes the result. Free-form text into a parser is a bug.
6. Wire observability: prompt version, model, input, output, tool calls, retrieval hits, latency, tokens, cost.
7. Run the eval. Iterate. Don't ship until you hit the bar.

## Prompt rules

Tell the model what to do, not just what not to do. Give it an out — "say so if you don't know" beats "don't hallucinate." Examples beat instructions. Pin model versions; "latest" is a bug factory. Temperature 0 unless you specifically need creativity.

## RAG rules

Chunk by semantic boundary, not character count. Hybrid search (BM25 + embedding) usually beats pure vector. Re-rank top-K with a cheap cross-encoder. Show citations. Log every retrieval.

## Agent rules

Cap tool-call loops or burn money. Tool descriptions are prompts — write them as carefully as the system prompt. One responsibility per agent. Surface the plan; black-box agents are unreviewable.

## When the model is wrong

In order: check input → check retrieval → tighten prompt → tighten output schema → try a stronger model. Re-prompting in a loop without changing the underlying issue burns weeks.

## Hand-off triggers

- Task is about combining/weighting market signals, not just a generic LLM call → also load `signal-engineering`
- Task involves SEBI compliance, disclaimers, or regulated output → also load `market-domain`
- Task involves the deployment or scaling of LLM infra → also load `system-design-engineer` and `devops-engineer`
- Task is "the model gave a wrong answer in prod" → also load `support-engineer`

---

## This project

### LLM configuration
- **Provider:** OpenRouter (`https://openrouter.ai/api/v1`), OpenAI-compatible SDK
- **Default model:** `qwen/qwen3-235b-a22b` — accuracy-first, ~$0.017/run
- **Alternatives:** `qwen/qwen3.5-flash-02-23` (fast, $0.006/run), `mistralai/mistral-small-2603` ($0.013/run)
- **Temperature:** 0.2 for agents, 0.0 for ticker resolution
- **Max tokens:** 2048
- **Timeout:** 60s
- **Response format:** always `{"type": "json_object"}` — never free-form
- **Client factory:** `services/clients/llm_client.py` → `get_llm_client()` (sync) / `get_async_llm_client()` (async)
- **Cost logging:** every call logged to `logs/agent_calls.jsonl` via `log_llm_call()`

### Prompt structure (every agent follows this)

```python
# config/prompts/automobile/<agent_name>.py
SYSTEM_PROMPT = "You are a ... analyst. Return ONLY valid JSON."
ANALYSIS_PROMPT = "Analyse {ticker} ... \nEvaluate:\n1. dim_a ...\n\nReturn:\n{json_schema}"
CONTEXT_SEARCH_QUERIES = [
    "{ticker} {company_name} ... {month} {year}",
    ...
]
```

`_build_prompt(query, context)` in each agent stitches these together. **Two auto-appended instructions** (in `base_agent.py`, not in prompt files):
- `_DATA_ONLY_INSTRUCTION` — "Score ONLY from context data. Do NOT use training knowledge."
- `_date_instruction()` — injects today's date + freshness rules (trust newer dates, ignore >14d as primary evidence)

### Agent output schema (every agent must return this JSON shape)
```json
{
  "overall_score": 0.0–1.0,
  "sub_scores": { "dim_1": float, "dim_2": float, ... },
  "key_positives": ["...", "..."],
  "key_risks": ["...", "..."],
  "summary": "2-3 sentence summary",
  "data_freshness": "YYYY-MM-DD"
}
```

Parsed by `_safe_parse()` → `_parse_output()` → `AgentOutput`. If parsing fails, returns `_error_output()` with score=0.5.

### No-data guard (important)
If `ContextBuilder.build()` returns `has_real_data=False`, the LLM is **never called** — `_no_data_output()` is returned immediately. This prevents training-knowledge hallucinations masquerading as scored analysis. Do not bypass this guard.

### RAG (currently disabled)
- Vector DB: ChromaDB, `core/intelligence/rag/`
- Enable: `RAG_ENABLED=true` in `.env`
- **Known gap:** `_rag_retrieve()` in `base_agent.py` is hardcoded to automobile agent names — BFSI/IT/RE agents get wrong retrieval queries if RAG is enabled
- Embeddings: sentence-transformers (local), no external embedding API cost

### Signal aggregation LLM calls
Two prompts in `config/prompts/shared/signal_aggregator.py`:
- `_SIMPLE_AGG_SYSTEM/USER` — no conflict; synthesises thesis from all agent scores
- `_CONFLICT_SYSTEM/USER` — fired when any two agents differ by ≥0.30; LLM adjudicates and re-weights

### Eval framework
- **None currently exists** — this is a known gap
- Unit tests verify JSON parsing, not output quality
- Future: need 20-50 labelled (ticker, date, expected_verdict) examples and a scoring rubric

### Thinking models note
`qwen3-235b-a22b` can return bare strings/numbers even with `json_object` format. `_safe_parse()` handles this with a regex fallback: `re.search(r'\{.*\}', raw, re.DOTALL)`. Don't remove this fallback.
