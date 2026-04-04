# Test Documentation — Automobile Agent

## Overview

This folder contains the full test suite for the Automobile Agent system.
Tests are written with **pytest** and use mocking extensively so that
**no real LLM API calls or network access** are needed to run them.

---

## Test Files

| File | Phase | What it tests |
|---|---|---|
| `conftest.py` | 1 | Shared fixtures and mock JSON factories used by all tests |
| `test_config.py` | 1 | Config validation — weights, thresholds, LLM settings, RAG defaults |
| `test_schemas.py` | 1 | Pydantic model validation — field bounds, defaults, auto-normalisation |
| `test_agents_unit.py` | 1 | Per-agent JSON parsing — mocked LLM, no API calls |
| `test_signal_aggregator.py` | 1 | Weighted fusion, conflict detection, fallback on bad JSON |
| `test_orchestrator.py` | 1 | End-to-end pipeline with fully mocked agents and LLM |
| `test_prompts.py` | 1 | Prompt template formatting — all placeholders resolve correctly |
| `test_data_fetchers.py` | 2 | yfinance RSI/MACD/BB math, Serper/NewsAPI parsing, ContextBuilder routing |
| `test_rag.py` | 3 | Embedder, VectorStore, chunking, DocumentIngester, RAGRetriever |
| `test_scheduler.py` | 4 | ScoreStore CRUD/delta/prune, AlertManager channels, Scheduler dispatch |

---

## Running the Tests

### Prerequisites

```bash
cd automobile_agent
pip install -r requirements.txt
```

### Run all tests

```bash
pytest tests/ -v
```

### Run with coverage

```bash
pytest tests/ --cov=. --cov-report=term-missing -v
```

### Run a specific file

```bash
pytest tests/test_config.py -v
pytest tests/test_agents_unit.py -v
```

### Run a specific test

```bash
pytest tests/test_signal_aggregator.py::TestConflictDetection::test_conflict_detected_when_delta_exceeds_threshold -v
```

---

## Test Strategy

### Unit tests (no I/O)
- `test_config.py` — Pure Python assertions on constant values
- `test_schemas.py` — Pydantic model instantiation; validates constraints
- `test_prompts.py` — String `.format()` calls; no external deps
- `test_agents_unit.py` — Agent `_parse_output()` called directly with pre-built dicts; `Groq` is mocked when `run()` is tested

### Integration tests (mocked LLM)
- `test_signal_aggregator.py` — Full `SignalAggregator.run()` with `Groq` patched
- `test_orchestrator.py` — Full `AutomobileAgentOrchestrator.analyse()` with all sub-agents and `Groq` patched

---

## Mock Strategy

All `Groq` client calls are patched via `unittest.mock.patch`.

```python
@patch("agents.base_agent.Groq")
def test_run_calls_llm(self, mock_groq_cls, maruti_query):
    mock_instance = MagicMock()
    mock_groq_cls.return_value = mock_instance
    mock_instance.chat.completions.create.return_value = _mock_groq_response(
        make_sales_demand_json()
    )
    ...
```

Mock JSON factories (in `conftest.py`):
- `make_sales_demand_json(score)` → valid Sales & Demand LLM response
- `make_fundamentals_json(score)` → valid Fundamentals LLM response
- `make_pattern_json(score)` → valid Pattern Analysis LLM response
- `make_sentiment_json(score)` → valid Sentiment LLM response
- `make_risk_macro_json(score)` → valid Risk & Macro LLM response
- `make_aggregator_json(score)` → valid Signal Aggregator LLM response

---

## Test Results Log

| Date | Run | Pass | Fail | Notes |
|---|---|---|---|---|
| 2026-04-03 | Initial implementation | TBD | TBD | First run after setup |

> Update this table after each significant test run.

---

## Adding New Tests

1. Create a new file `tests/test_<feature>.py`
2. Import fixtures from `conftest.py` where possible
3. Use `@patch("agents.base_agent.Groq")` to prevent real API calls
4. Add a row to the table above
5. Update this document with what the new file covers

---

## Known Gaps / Future Tests

- [ ] Live integration test against real Groq API (requires `GROQ_API_KEY`; mark `@pytest.mark.integration`)
- [ ] Real yfinance integration test (requires network; mark `@pytest.mark.integration`)
- [ ] Rate limit retry logic (requires injecting `RateLimitError` from groq SDK)
- [ ] Output file generation tests for `--save` flag in `main.py`
- [ ] `--list-tickers` CLI flag test
- [ ] `scripts/ingest_documents.py` CLI argument parsing tests
- [ ] End-to-end RAG round-trip: ingest a real PDF → retrieve relevant chunks
