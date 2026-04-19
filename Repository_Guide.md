# Repository Guide

Quick index to the live documentation. Start here.

## docs/

| File | When to read it |
|---|---|
| [docs/CODEBASE.md](docs/CODEBASE.md) | **Start here.** Module map, shim→real path table, schemas, settings, data flow, known issues |
| [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md) | Each of the 9 agents: what it scores, what data it uses, its schema |
| [docs/API_SOURCES.md](docs/API_SOURCES.md) | yfinance tickers, Serper/Tavily quotas, per-agent call budget |
| [docs/RL_FEEDBACK_DESIGN.md](docs/RL_FEEDBACK_DESIGN.md) | Adaptive weight learning loop design (`intelligence/rl/`) |
| [docs/SOLUTION_DESIGN.md](docs/SOLUTION_DESIGN.md) | Gap analysis per agent — what's a real source vs Serper proxy |

## Key facts

- **Real code lives in:** `core/`, `services/`, `config/`, `intelligence/`
- **`agents/`, `models/`, `prompts/`, `tools/`** are compatibility shims — never edit them directly
- **9 agents** active for automobile; banking/IT/renewable are stubs
- **Settings:** `config/settings/base.py` — all weights, API limits, yfinance tickers, LLM config
- **Schemas:** `core/schemas/pipeline.py` — all Pydantic models
- **Run:** `python main.py <ticker>` · add `--micro-loop` to pre-cache macro news (saves ~3 Serper/run)
- **Logs:** `logs/agent_calls.jsonl` · `logs/run_summaries.jsonl` · `logs/api_usage.json`

## .env variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | LLM inference |
| `SERPER_API_KEY` | Yes | Google search (2,500/month free) |
| `TAVILY_API_KEY` | Yes | Full-page extraction — policy agent (1,000/month free) |
| `NEWSAPI_KEY` | No | Fallback when Serper fails (100/day free) |
| `LLM_MODEL` | No | Override default `qwen/qwen3-235b-a22b` |
| `AGENT_TIMEOUT_SECONDS` | No | Default 120s |
| `SERPER_MONTHLY_LIMIT` | No | Default 2500 |
| `TAVILY_MONTHLY_LIMIT` | No | Default 1000 |
