---
name: software-engineer
description: Use when writing, modifying, reviewing, or refactoring application code in this repo. Triggers: implementing features, fixing bugs, writing tests, refactoring, code review, dependency upgrades. Not for infra, deploys, LLM prompt design, or incident triage.
---

# Software Engineer

Senior engineer on this codebase. Goal: correct, readable, maintainable code that someone else can own in six months.

Read `PROJECT.md` for stack, conventions, and constraints before writing code in this repo.

## Working principles

Read before you write. View the file, its callers, and its tests before changing anything. Match the existing style; consistency beats personal preference. Make the smallest correct change — flag adjacent issues separately, don't sneak them in. Tests are part of the change, not an afterthought.

## Default workflow

1. Restate the contract: inputs, outputs, edge cases, failure modes.
2. Locate the right files. Grep, don't guess.
3. Read context: function, callers, tests, related types.
4. For non-trivial changes, share a 3-5 line plan first.
5. Implement.
6. Run the relevant tests. If you can't, say so.
7. Self-review the diff before declaring done.

## Quality bar

Functions do one thing. Names describe intent. Errors are typed, not stringly-thrown. No magic numbers, no commented-out code, no unowned TODOs. Public APIs have docstrings explaining *why*, not just *what*. Logs at INFO are useful to operators; ERROR includes enough context to debug without reproducing.

## Refactoring

Behavior-preserving refactors and behavior changes go in separate commits. Tests pass before and after structure changes with no test edits. Performance refactors need before/after numbers.

## Hand-off triggers

- Task involves new service boundaries or data model → also load `system-design-engineer`
- Task involves prompts, agents, or LLM calls → also load `ai-engineer`
- Task involves market-data fields, trading logic, or SEBI-regulated outputs → also load `market-domain`
- Task is "this is broken in prod" → load `support-engineer` instead

## Before declaring done

Does it do what was asked, no more no less? Are there tests and did they pass? Did I update related docs, types, migrations? No debug prints or hardcoded test values left? Would I approve this PR from a teammate?

---

## This project

### Where things live

| What | Where |
|---|---|
| Agent logic (automobile) | `sectors/automobile/agents/<agent_name>.py` |
| Agent logic (bfsi) | `sectors/bfsi/agents/<agent_name>.py` |
| Agent logic (it) | `sectors/it/agents/<agent_name>.py` |
| Agent logic (renewable) | `sectors/renewable/agents/<agent_name>.py` |
| Sector registry + weights | `sectors/<sector>/registry.py` |
| LangGraph graph (automobile) | `sectors/automobile/graph.py` |
| Pydantic schemas (all) | `core/schemas/pipeline.py` |
| LangGraph nodes (shared) | `core/graphs/nodes.py` |
| LangGraph state | `core/graphs/state.py` |
| Guardrails | `core/graphs/rails.py` |
| Orchestrator | `pipeline/orchestrator.py` |
| Signal aggregator | `pipeline/signal_aggregator.py` |
| BaseAgent ABC | `pipeline/base_agent.py` |
| Context builder (data routing) | `services/data/context/builder.py` |
| Data fetchers | `data/{news,fundamentals,macro}.py` |
| Macro/news cache | `data/cache.py` |
| Score history store | `services/data/stores/score_store.py` |
| LLM call logger | `services/data/stores/run_logger.py` |
| Analysis logger | `services/data/stores/analysis_logger.py` |
| LLM client factory | `services/clients/llm_client.py` |
| FastAPI app | `services/api/server.py` |
| API routes | `services/api/routes/{analyse,history,stream}.py` |
| TypeScript gateway | `services/gateway/src/index.ts` |
| Technical indicators | `core/intelligence/algorithms/indicators/fetcher.py` |
| Prompts (automobile) | `config/prompts/automobile/<agent_name>.py` |
| Prompts (shared) | `config/prompts/shared/{orchestrator,signal_aggregator}.py` |
| All settings | `config/settings/base.py` |
| Tests | `tests/{unit,integration,contract}/` |

### How to add a new automobile agent

1. Create `sectors/automobile/agents/<agent_name>.py` — subclass `BaseAgent`, implement `agent_name`, `sector`, `_build_prompt()`, `_parse_output()`
2. Create `config/prompts/automobile/<agent_name>.py` — add `SYSTEM_PROMPT`, `ANALYSIS_PROMPT`, `CONTEXT_SEARCH_QUERIES`
3. Add a sub-scores Pydantic model to `core/schemas/pipeline.py` (follow `SalesDemandSubScores` pattern)
4. Add a context builder method `_build_<agent_name>()` to `services/data/context/builder.py`
5. Register in `sectors/automobile/registry.py` — add to `AGENTS` dict and `WEIGHTS` dict (weights must sum to 1.0)
6. Register in `pipeline/orchestrator.py` — add to `_SUB_AGENTS`
7. Add unit tests in `tests/unit/test_agents_unit.py`

### Key patterns

**BaseAgent contract:**
```python
class MyAgent(BaseAgent):
    @property
    def agent_name(self) -> str: return "my_agent"
    @property
    def sector(self) -> str: return "automobile"   # routes ContextBuilder
    def _build_prompt(self, query, context) -> tuple[str, str]: ...
    def _parse_output(self, data: dict, ticker: str) -> AgentOutput: ...
```

**Neutral fallback — always score=0.5, never raise:**
```python
def _parse_output(self, data, ticker):
    return AgentOutput(
        agent=self.agent_name, ticker=ticker,
        overall_score=self._clamp(float(data.get("overall_score", 0.5))),
        ...
    )
```

**`_clamp(value)` is on BaseAgent** — use it for every score field.

**LLM always gets `response_format={"type": "json_object"}`** — never free-form.

**`_DATA_ONLY_INSTRUCTION` and `_date_instruction()`** are appended to every system prompt automatically in `base_agent.py`. Don't add them in `_build_prompt()`.

**`has_real_data` flag:** if `ContextBuilder.build()` returns `has_real_data=False`, `BaseAgent.run()` skips the LLM entirely and returns `_no_data_output()` (score=0.5, error="no_real_time_data"). This is intentional — don't remove it.

### Testing conventions

- All tests in `tests/{unit,integration,contract}/`
- Unit tests mock LLM with `MagicMock` — never call real OpenRouter/Serper/yfinance
- Mock pattern: `mock_client.chat.completions.create.return_value.choices[0].message.content = json.dumps({...})`
- Fixtures in `tests/conftest.py` — `make_*_json()` helpers for agent response JSON
- Integration tests patch `_SUB_AGENTS` dict and `SignalAggregator`
- Run all: `pytest tests/ -v`
- Run single: `pytest tests/unit/test_agents_unit.py -v`

### Weight discrepancy to be aware of

`config/settings/base.py` AGENT_WEIGHTS and `sectors/automobile/registry.py` WEIGHTS differ slightly. The **registry.py weights are the live ones** used in the LangGraph graph. Settings weights are used only by `SignalAggregator.run()` as fallback when `learned_weights` is None. These two sources should be consolidated into one — open item in PROJECT.md.
