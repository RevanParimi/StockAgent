# Repository Guide for Automobile Agent Project

## Overview

The **Automobile Agent** is an AI-powered system designed to analyze Indian automobile stocks listed on NSE/BSE. It uses a multi-agent architecture to provide structured investment scores and verdicts by evaluating stocks from multiple specialized perspectives.

This guide is intended for product owners, designers, and IT professionals who need to understand the repository structure and design flow without diving into the code implementation. It focuses on the high-level organization, key components, and how they support the overall design and future modifications.

## Project Purpose

- **Input**: A stock ticker or company name (e.g., "MARUTI" or "Maruti Suzuki")
- **Process**: Parallel analysis by five specialist AI agents
- **Output**: A consolidated investment score (0.0–1.0) with a verdict and supporting thesis

The system emphasizes specialization, parallelism, and conflict-aware fusion to deliver deep, balanced insights.

## High-Level Architecture

The system follows a modular, agent-based design:

```
User Input
    ↓
Orchestrator (Ticker Resolution & Dispatch)
    ↓
Parallel Agent Execution
├── Sales & Demand Agent (20% weight)
├── Fundamentals Agent (25% weight)
├── Pattern Analysis Agent (20% weight)
├── Sentiment Agent (15% weight)
└── Risk & Macro Agent (20% weight)
    ↓
Signal Aggregator (Weighted Fusion & Conflict Resolution)
    ↓
Final Score & Verdict Output
```

### Key Components

- **Orchestrator**: Manages the overall flow, resolves inputs, and coordinates agents.
- **Agents**: Specialized modules each focusing on a specific analysis dimension.
- **Signal Aggregator**: Combines agent outputs, resolves conflicts, and produces the final verdict.
- **Tools**: Supporting utilities for data fetching, RAG (Retrieval-Augmented Generation), scheduling, and storage.
- **Configuration & Prompts**: Centralized settings and AI prompts for easy customization.

## Repository Structure

The repository is organized into logical folders to separate concerns and facilitate maintenance. Below is an overview of the main directories and their purposes:

### Core Directories

- **`agents/`**: Contains the individual agent implementations and the orchestrator.
  - `orchestrator.py`: Main coordinator for the analysis pipeline.
  - `base_agent.py`: Common base class for all agents.
  - Individual agent files (e.g., `fundamentals.py`, `sentiment.py`): Each handles a specific analysis type.

- **`config/`**: Centralized configuration files.
  - `settings.py`: API keys, model parameters, agent weights, and other static settings.
  - `rag_config.py`: Configuration for the RAG system.

- **`prompts/`**: AI prompts used by agents and the orchestrator.
  - Each agent has its own prompt file (e.g., `fundamentals.py` in prompts/) for easy editing and versioning.

- **`tools/`**: Utility modules for data handling and system operations.
  - Data fetchers (e.g., `yfinance_fetcher.py`, `news_fetcher.py`).
  - RAG components (`rag/embedder.py`, `rag/retriever.py`).
  - Supporting tools like `scheduler.py` for automated runs and `alerting.py` for notifications.

- **`scripts/`**: Executable scripts for setup and operations.
  - `ingest_documents.py`: For loading data into the RAG system.
  - `run_schedule.py`: For running scheduled analyses.

- **`tests/`**: Unit and integration tests to validate functionality.
  - Organized by component (e.g., `test_agents_unit.py`, `test_orchestrator.py`).

- **`data/`**: Placeholder for data files (e.g., documents for RAG).

- **`models/`**: Data models and schemas.
  - `schemas.py`: Defines the structure of inputs, outputs, and intermediate data.

### Key Files for Design Understanding

- **`README.md`**: High-level project description, agent overview, and quick start.
- **`FLOW.md`**: Detailed system flow, including phases, data movement, and decision logic.
- **`requirements.txt`**: List of Python dependencies.
- **`main.py`**: Entry point for command-line usage.

## Understanding the Design Flow

### Entry Points
The system can be triggered via:
- Command-line interface (`python main.py <ticker>`)
- Scheduled runs (via `scripts/run_schedule.py`)
- Direct API calls (importing the orchestrator)

All paths lead to the `AutomobileAgentOrchestrator.analyse()` method.

### Core Pipeline Phases
1. **Ticker Resolution**: Normalize user input to a standard NSE ticker.
2. **Context Assembly**: Gather relevant data and context for analysis.
3. **Parallel Agent Execution**: Run all five agents simultaneously for efficiency.
4. **Signal Aggregation**: Combine results with weighted scoring and resolve any conflicts.
5. **Output Generation**: Produce the final score, verdict, and explanatory thesis.

### Supporting Phases
- **Live Data Feeds**: Real-time data fetching from various sources (e.g., financial APIs, news).
- **RAG Pipeline**: Document ingestion and retrieval for enhanced context.
- **Scheduler & Alerting**: Automated runs and notification systems.

## Navigating for Design Changes

To modify or extend the design:

1. **Review FLOW.md**: Understand the complete system flow before making changes.
2. **Check Config Files**: Adjust settings in `config/settings.py` for parameters like agent weights or API keys.
3. **Edit Prompts**: Update AI behavior in the `prompts/` directory without touching core code.
4. **Agent Modifications**: Add new agents or modify existing ones in `agents/`, following the base class structure.
5. **Test Changes**: Run tests in `tests/` to ensure integrity.
6. **Data & Tools**: Extend data sources or tools in `tools/` for new capabilities.

## Configuration Hierarchy

Settings are managed hierarchically:
- Environment variables (highest priority)
- `.env` file
- Defaults in `config/settings.py`

This allows easy customization without code changes.

## Error Handling & Fallbacks

The system includes robust error handling:
- Agent failures are logged and can be retried.
- Fallbacks ensure partial results can still produce a verdict.
- Conflicts between agents are resolved via LLM arbitration.

## Decision Logic

Scores are calculated as weighted averages of agent outputs. Verdicts are categorized as:
- Strong Buy/Sell (based on score thresholds)
- Conflicts are flagged and resolved by the aggregator.

For detailed scoring rules, refer to FLOW.md.

This guide provides a foundation for understanding the repository's design and structure. For deeper technical details, consult the backend team or refer to the code comments and documentation within the files.