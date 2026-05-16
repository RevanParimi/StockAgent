# Chat Pipeline Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 5-node classify→plan→execute→synthesize→review pipeline with a 3-node open dispatch → async parallel executor → tier-aware synthesize pipeline.

**Architecture:** A single `dispatch` LLM call replaces both `classify` and `planner`, using free-form query decomposition and user sophistication detection instead of fixed intent categories. The executor fires all tool tasks concurrently via `asyncio.gather`. Synthesize adapts format and depth to the detected user tier (casual/active/expert) without a rigid template.

**Tech Stack:** Python 3.11+, LangGraph, LangChain OpenAI-compat client, FastAPI SSE, yfinance, asyncio, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `services/api/user_profile.py` | **Create** | Load/save per-session user tier profile to `data/user_profiles/` |
| `services/api/chat_graph.py` | **Rewrite** | 3-node graph, new state schema, dispatch + executor + synthesize nodes |
| `services/api/routes/ui_data.py` | **Modify** | Add `get_historical_prices`, `get_rl_prediction`; remove reviewer SSE event |
| `tests/unit/intelligence/chat/test_user_profile.py` | **Create** | Unit tests for profile load/save/default |
| `tests/unit/intelligence/chat/test_new_tools.py` | **Create** | Unit tests for two new tools |
| `tests/unit/intelligence/chat/test_dispatch_node.py` | **Create** | Unit tests for dispatch JSON parsing + fallback |
| `tests/unit/intelligence/chat/test_executor_node.py` | **Create** | Unit tests for async parallel executor |

Old files that become dead code once Task 9 removes them: the inline `CLASSIFY_SYSTEM_PROMPT`, `PLANNER_SYSTEM_PROMPT`, `REVIEWER_SYSTEM_PROMPT`, and the `_node_classify`, `_node_planner`, `_node_reviewer` functions inside `chat_graph.py`.

---

## Task 1: User Profile Module

**Files:**
- Create: `services/api/user_profile.py`
- Create: `tests/unit/intelligence/chat/test_user_profile.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/intelligence/chat/test_user_profile.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_load_profile_missing_returns_defaults(tmp_path):
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import load_profile
        profile = load_profile("nonexistent-session")
    assert profile["detected_tier"] == "active"
    assert profile["sessions_seen"] == 0
    assert profile["topics_seen"] == []


def test_save_and_reload_profile(tmp_path):
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import save_profile, load_profile
        save_profile("sess-1", tier="expert", tier_confidence=0.9, topics=["Nifty", "VIX"])
        profile = load_profile("sess-1")
    assert profile["detected_tier"] == "expert"
    assert profile["tier_confidence"] == 0.9
    assert "Nifty" in profile["topics_seen"]
    assert profile["sessions_seen"] == 1


def test_save_increments_sessions(tmp_path):
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import save_profile, load_profile
        save_profile("sess-2", tier="casual", tier_confidence=0.7, topics=[])
        save_profile("sess-2", tier="active", tier_confidence=0.8, topics=["Sensex"])
        profile = load_profile("sess-2")
    assert profile["sessions_seen"] == 2


def test_save_merges_topics(tmp_path):
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import save_profile, load_profile
        save_profile("sess-3", tier="active", tier_confidence=0.7, topics=["Nifty"])
        save_profile("sess-3", tier="active", tier_confidence=0.7, topics=["Sensex"])
        profile = load_profile("sess-3")
    assert "Nifty" in profile["topics_seen"]
    assert "Sensex" in profile["topics_seen"]


def test_corrupt_profile_returns_defaults(tmp_path):
    prof_path = tmp_path / "bad-session.json"
    prof_path.write_text("not valid json")
    with patch("services.api.user_profile.PROFILES_DIR", tmp_path):
        from services.api.user_profile import load_profile
        profile = load_profile("bad-session")
    assert profile["detected_tier"] == "active"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/unit/intelligence/chat/test_user_profile.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.api.user_profile'`

- [ ] **Step 3: Create the user profile module**

```python
# services/api/user_profile.py
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

PROFILES_DIR = Path("data/user_profiles")
_DEFAULT_TIER = "active"


def load_profile(session_id: str) -> dict:
    """Load user profile from disk. Returns safe defaults if missing or corrupt."""
    path = PROFILES_DIR / f"{session_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_profile(session_id)


def save_profile(
    session_id: str,
    tier: str,
    tier_confidence: float,
    topics: list[str],
) -> None:
    """Persist updated profile. Increments sessions_seen, merges topics."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_profile(session_id)
    merged_topics = list(set(existing.get("topics_seen", []) + topics))[:20]
    existing.update(
        {
            "session_id": session_id,
            "detected_tier": tier,
            "tier_confidence": tier_confidence,
            "sessions_seen": existing.get("sessions_seen", 0) + 1,
            "topics_seen": merged_topics,
            "last_seen": str(date.today()),
        }
    )
    path = PROFILES_DIR / f"{session_id}.json"
    try:
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save user profile %s: %s", session_id, exc)


def _default_profile(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "detected_tier": _DEFAULT_TIER,
        "tier_confidence": 0.5,
        "sessions_seen": 0,
        "topics_seen": [],
        "last_seen": str(date.today()),
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/unit/intelligence/chat/test_user_profile.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add services/api/user_profile.py tests/unit/intelligence/chat/test_user_profile.py
git commit -m "feat(chat): add user profile module with tier persistence"
```

---

## Task 2: get_historical_prices Tool

**Files:**
- Modify: `services/api/routes/ui_data.py` (add one async function)
- Create: `tests/unit/intelligence/chat/test_new_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/intelligence/chat/test_new_tools.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import pandas as pd
from datetime import datetime


@pytest.mark.asyncio
async def test_historical_prices_returns_formatted_output():
    mock_hist = pd.DataFrame(
        {
            "Open":  [80000.0, 80500.0, 81000.0],
            "Close": [80200.0, 80100.0, 79980.0],
        },
        index=pd.to_datetime(["2026-05-13", "2026-05-14", "2026-05-15"]),
    )
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist

    with patch("yfinance.Ticker", return_value=mock_ticker):
        from services.api.routes.ui_data import _chat_tool_historical_prices
        result = await _chat_tool_historical_prices("^BSESN", days=3)

    assert "^BSESN" in result
    assert "79,980" in result or "79980" in result
    assert "▼" in result  # last close was down


@pytest.mark.asyncio
async def test_historical_prices_empty_returns_no_data():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch("yfinance.Ticker", return_value=mock_ticker):
        from services.api.routes.ui_data import _chat_tool_historical_prices
        result = await _chat_tool_historical_prices("INVALID", days=3)

    assert "No historical data" in result


@pytest.mark.asyncio
async def test_historical_prices_exception_returns_no_data():
    with patch("yfinance.Ticker", side_effect=Exception("network error")):
        from services.api.routes.ui_data import _chat_tool_historical_prices
        result = await _chat_tool_historical_prices("^BSESN", days=3)

    assert "No historical data" in result
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/chat/test_new_tools.py::test_historical_prices_returns_formatted_output -v
```

Expected: `ImportError` — function does not exist yet

- [ ] **Step 3: Add `_chat_tool_historical_prices` to ui_data.py**

Find the section in `services/api/routes/ui_data.py` where other `_chat_tool_*` functions are defined and add after the last one:

```python
async def _chat_tool_historical_prices(symbol: str, days: int = 5) -> str:
    """Fetch last N trading days OHLCV for a yfinance symbol."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{days + 7}d")  # buffer for weekends/holidays
        if hist.empty:
            return f"No historical data for {symbol}"

        hist = hist.tail(days)
        lines = [f"{symbol} — Last {len(hist)} trading days:"]
        closes: list[float] = []
        for dt, row in hist.iterrows():
            date_str = dt.strftime("%Y-%m-%d (%a)")
            change_pct = ((row["Close"] - row["Open"]) / row["Open"]) * 100
            arrow = "▲" if change_pct >= 0 else "▼"
            lines.append(
                f"{date_str}  Close: {row['Close']:,.2f}  Change: {arrow}{abs(change_pct):.2f}%"
            )
            closes.append(float(row["Close"]))

        if len(closes) >= 2:
            net = ((closes[-1] - closes[0]) / closes[0]) * 100
            arrow = "▲" if net >= 0 else "▼"
            lines.append(f"Net {len(closes)}-day: {arrow}{abs(net):.2f}%")
            down_streak = 0
            for i in range(len(closes) - 1, 0, -1):
                if closes[i] < closes[i - 1]:
                    down_streak += 1
                else:
                    break
            if down_streak >= 2:
                lines.append(f"Trend: {down_streak} consecutive down days")

        return "\n".join(lines)
    except Exception:
        return f"No historical data for {symbol}"
```

- [ ] **Step 4: Register the tool in `_execute_chat_tool`**

In `services/api/routes/ui_data.py`, add to the `_execute_chat_tool` function before the final `return f"Unknown tool: {name}"` line:

```python
    if name == "get_historical_prices":
        return await _chat_tool_historical_prices(
            args.get("symbol", "^NSEI"), int(args.get("days", 5))
        )
```

- [ ] **Step 5: Run tests**

```
pytest tests/unit/intelligence/chat/test_new_tools.py -k "historical" -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add services/api/routes/ui_data.py tests/unit/intelligence/chat/test_new_tools.py
git commit -m "feat(chat): add get_historical_prices tool"
```

---

## Task 3: get_rl_prediction Tool

**Files:**
- Modify: `services/api/routes/ui_data.py`
- Modify: `tests/unit/intelligence/chat/test_new_tools.py`

- [ ] **Step 1: Write the failing tests** (append to existing test file)

```python
# Append to tests/unit/intelligence/chat/test_new_tools.py

@pytest.mark.asyncio
async def test_rl_prediction_returns_formatted_output(tmp_path):
    from datetime import date
    today = str(date.today())
    cycle_id = f"TCS_{today[:7]}"
    ticker_dir = tmp_path / "it_sector" / "TCS"
    ticker_dir.mkdir(parents=True)
    envelope = {
        "ticker": "TCS",
        "sector": "it_sector",
        "conviction_streak": {"current_verdict": "BUY", "streak_days": 7},
        "daily_forecasts": [{
            "date": today,
            "predicted_verdict": "BUY",
            "confidence": 0.64,
            "predicted_close": 3847.0,
            "key_assumptions": ["INR stable ~₹84"],
            "revised": True,
            "revision_count": 2,
        }],
    }
    (ticker_dir / f"{cycle_id}_prediction_envelope.json").write_text(
        __import__("json").dumps(envelope)
    )

    with patch("services.api.routes.ui_data._PREDICTIONS_DIR", tmp_path):
        from services.api.routes.ui_data import _chat_tool_rl_prediction
        result = await _chat_tool_rl_prediction("TCS")

    assert "BUY" in result
    assert "0.64" in result
    assert "3,847" in result or "3847" in result


@pytest.mark.asyncio
async def test_rl_prediction_missing_envelope_returns_empty(tmp_path):
    with patch("services.api.routes.ui_data._PREDICTIONS_DIR", tmp_path):
        from services.api.routes.ui_data import _chat_tool_rl_prediction
        result = await _chat_tool_rl_prediction("UNKNOWN")

    assert result == ""


@pytest.mark.asyncio
async def test_rl_prediction_index_returns_empty():
    from services.api.routes.ui_data import _chat_tool_rl_prediction
    result = await _chat_tool_rl_prediction("SENSEX")
    assert result == ""

    result2 = await _chat_tool_rl_prediction("NIFTY")
    assert result2 == ""
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/chat/test_new_tools.py -k "rl_prediction" -v
```

Expected: `ImportError` — function does not exist yet

- [ ] **Step 3: Add `_PREDICTIONS_DIR` constant and `_chat_tool_rl_prediction` to ui_data.py**

Near the top of `services/api/routes/ui_data.py`, with other `Path` constants:

```python
_PREDICTIONS_DIR = Path("data/predictions")
_RL_INDEX_NAMES = frozenset({"SENSEX", "NIFTY", "NIFTY50", "NSEI", "BSESN"})
```

Then add the tool function alongside the other `_chat_tool_*` functions:

```python
async def _chat_tool_rl_prediction(ticker: str) -> str:
    """Read today's RL prediction envelope for a ticker. Returns '' if not found."""
    if ticker.upper() in _RL_INDEX_NAMES:
        return ""

    ticker_upper = ticker.upper()
    today = str(date.today())
    cycle_id = f"{ticker_upper}_{today[:7]}"  # e.g. TCS_2026-05

    try:
        for sector_dir in _PREDICTIONS_DIR.iterdir():
            if not sector_dir.is_dir():
                continue
            candidate = sector_dir / ticker_upper / f"{cycle_id}_prediction_envelope.json"
            if not candidate.exists():
                continue

            envelope = json.loads(candidate.read_text(encoding="utf-8"))
            forecasts = envelope.get("daily_forecasts", [])
            today_row = next((d for d in forecasts if d.get("date") == today), None)
            if not today_row:
                return ""

            streak = envelope.get("conviction_streak", {})
            streak_days = streak.get("streak_days", 0)
            reversion = envelope.get("reversion_prior", 0.0)
            lines = [
                f"RL PREDICTION — {ticker_upper} ({today}):",
                (
                    f"Verdict: {today_row['predicted_verdict']}"
                    f"  |  Confidence: {today_row['confidence']:.2f}"
                    f"  |  Predicted close: ₹{today_row['predicted_close']:,.0f}"
                ),
                (
                    f"Conviction streak: {streak_days} consecutive"
                    f" {streak.get('current_verdict', '')} days"
                    f" — reversion prior: {reversion * 100:.0f}%"
                ),
            ]
            assumptions = today_row.get("key_assumptions", [])
            if assumptions:
                lines.append(f"Key assumptions: {assumptions}")
            if today_row.get("revised"):
                lines.append(
                    f"Revised: Yes (revision {today_row.get('revision_count', 1)})"
                )
            return "\n".join(lines)
    except Exception:
        return ""

    return ""
```

- [ ] **Step 4: Register the tool in `_execute_chat_tool`**

In `services/api/routes/ui_data.py`, add to `_execute_chat_tool` before the final `return f"Unknown tool: {name}"`:

```python
    if name == "get_rl_prediction":
        return await _chat_tool_rl_prediction(args.get("ticker", ""))
```

- [ ] **Step 5: Run tests**

```
pytest tests/unit/intelligence/chat/test_new_tools.py -v
```

Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add services/api/routes/ui_data.py tests/unit/intelligence/chat/test_new_tools.py
git commit -m "feat(chat): add get_rl_prediction tool"
```

---

## Task 4: Dispatch Node

**Files:**
- Modify: `services/api/chat_graph.py` (add dispatch node + new state schema)
- Create: `tests/unit/intelligence/chat/test_dispatch_node.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/intelligence/chat/test_dispatch_node.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


VALID_DISPATCH = {
    "query_decomposition": "User wants 3-day Sensex trend and prediction",
    "user_tier": "active",
    "tasks": [
        {"tool": "get_historical_prices", "args": {"symbol": "^BSESN", "days": 5}, "priority": 1},
        {"tool": "get_live_price", "args": {"symbol": "^BSESN"}, "priority": 1},
        {"tool": "search_market_news", "args": {"query": "Sensex India outlook"}, "priority": 2},
    ],
    "browsing_strategy": {"topics": ["Sensex"], "geo": "in", "always_news": True},
}


@pytest.mark.asyncio
async def test_dispatch_node_parses_valid_llm_output():
    from services.api.chat_graph import _node_dispatch

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(content=f"<json>{json.dumps(VALID_DISPATCH)}</json>")
    )

    state = {
        "messages": [{"role": "user", "content": "compare last 3 days sensex"}],
        "query_decomposition": None,
        "user_tier": None,
        "browsing_strategy": None,
        "tasks": None,
        "tool_results": None,
    }

    with patch("services.api.chat_graph._dispatch_llm", mock_llm):
        result = await _node_dispatch(state)

    assert result["user_tier"] == "active"
    assert len(result["tasks"]) == 3
    assert result["query_decomposition"] == VALID_DISPATCH["query_decomposition"]


@pytest.mark.asyncio
async def test_dispatch_node_fallback_on_bad_json():
    from services.api.chat_graph import _node_dispatch

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(content="this is not json at all")
    )

    state = {
        "messages": [{"role": "user", "content": "what is happening in the market"}],
        "query_decomposition": None,
        "user_tier": None,
        "browsing_strategy": None,
        "tasks": None,
        "tool_results": None,
    }

    with patch("services.api.chat_graph._dispatch_llm", mock_llm):
        result = await _node_dispatch(state)

    # Fallback tasks must always include these three
    tools = {t["tool"] for t in result["tasks"]}
    assert "get_live_price" in tools
    assert "get_macro_news" in tools
    assert "search_market_news" in tools
    assert result["user_tier"] == "active"  # safe default


@pytest.mark.asyncio
async def test_dispatch_node_falls_back_on_zero_tasks():
    from services.api.chat_graph import _node_dispatch

    bad_dispatch = {**VALID_DISPATCH, "tasks": []}
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(content=json.dumps(bad_dispatch))
    )

    state = {
        "messages": [{"role": "user", "content": "market news"}],
        "query_decomposition": None,
        "user_tier": None,
        "browsing_strategy": None,
        "tasks": None,
        "tool_results": None,
    }

    with patch("services.api.chat_graph._dispatch_llm", mock_llm):
        result = await _node_dispatch(state)

    assert len(result["tasks"]) >= 3
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/chat/test_dispatch_node.py -v
```

Expected: `ImportError` — `_node_dispatch` does not exist yet

- [ ] **Step 3: Add new state schema and dispatch node to chat_graph.py**

Replace the `ChatState` TypedDict at the top of `services/api/chat_graph.py`:

```python
# New state — replaces old ChatState
class ChatState(TypedDict):
    messages:            Annotated[list, add]   # MemorySaver key — operator.add unchanged
    query_decomposition: str | None             # from dispatch: what user needs (free text)
    user_tier:           str | None             # casual | active | expert
    browsing_strategy:   dict | None            # from dispatch: topics, geo, always_news
    tasks:               list[dict] | None      # from dispatch: [{tool, args, priority}]
    tool_results:        list[dict] | None      # from executor: [{tool, result, error}]
```

Add the dispatch prompt constant and LLM client after the `_FAST_MODEL` line:

```python
DISPATCH_SYSTEM_PROMPT = """\
You are a financial intelligence dispatcher for an Indian stock market assistant.

Decompose what the user actually needs, identify their sophistication tier,
and plan which tools to call to answer the query.

TOOL CATALOGUE:
  get_live_price(symbol)               — current price + % change
  get_historical_prices(symbol, days)  — last N trading days OHLCV + trend
  get_sector_snapshot(sector)          — all stocks in a sector
  get_stock_analysis(ticker)           — DB verdict (BUY/SELL/NEUTRAL)
  get_analysis_history(ticker)         — historical verdicts trend
  get_rl_prediction(ticker)            — RL verdict + confidence + regime
  get_rl_insights(ticker)              — agent-level RL breakdown
  get_macro_news()                     — today's macro news cache
  search_market_news(query)            — live Serper news search
  run_agent_analysis(ticker)           — deep 9-agent pipeline (EXPERT ONLY, ~45s)

SYMBOL MAPPING:
  Sensex → ^BSESN | Nifty 50 → ^NSEI | Nifty Bank → ^NSEBANK
  Nifty IT → ^CNXIT | Indian stocks → TICKER.NS

TIER DETECTION:
  casual  — plain language, no jargon ("is market good today", "should I buy X")
  active  — uses market terms, asks comparisons ("compare 3 days", "FII data", "sector rotation")
  expert  — technical signals and metrics ("VIX elevated", "RSI oversold", "regime", "conviction")

PLANNING RULES:
  1. Include get_rl_prediction when a specific stock ticker is mentioned
  2. Include get_historical_prices when a trend, comparison, or prediction is asked
  3. Include search_market_news on everything where always_news=true
  4. Include get_macro_news on broad market/index queries
  5. run_agent_analysis ONLY when user_tier=expert AND deep multi-signal analysis needed
  6. Priority 1 = fast/critical, Priority 2 = supporting context

ALWAYS-NEWS RULE:
  always_news=true  — anything involving a market, stock, sector, event, index, or opinion
  always_news=false — ONLY pure definitional questions ("what is P/E", "explain SIP")

OUTPUT: Valid JSON only. No text outside the JSON.

{
  "query_decomposition": "<plain English: what does the user actually need>",
  "user_tier": "casual|active|expert",
  "tasks": [
    {"tool": "<tool_name>", "args": {}, "priority": 1}
  ],
  "browsing_strategy": {
    "topics": ["<topic>"],
    "geo": "in|global",
    "always_news": true
  }
}
"""

_DISPATCH_FALLBACK_TASKS = [
    {"tool": "get_live_price",       "args": {"symbol": "^NSEI"},                           "priority": 1},
    {"tool": "get_macro_news",       "args": {},                                              "priority": 2},
    {"tool": "search_market_news",   "args": {"query": "India Nifty Sensex market news"},    "priority": 2},
]

# LLM client — module-level so tests can patch it
from langchain_openai import ChatOpenAI as _ChatOpenAI
_dispatch_llm = _ChatOpenAI(
    model=_FAST_MODEL,
    temperature=0.0,
    max_tokens=400,
    base_url="https://openrouter.ai/api/v1",
    api_key=__import__("os").environ.get("OPENROUTER_API_KEY", ""),
)
```

Add the `_node_dispatch` async function:

```python
async def _node_dispatch(state: ChatState) -> dict:
    """Single LLM call: decompose query + detect user tier + plan tasks."""
    from services.api.user_profile import load_profile

    messages = state.get("messages", [])
    last_8 = messages[-8:] if len(messages) > 8 else messages

    # Load user profile for tier hint
    session_id = state.get("session_id", "")
    profile = load_profile(session_id) if session_id else {}
    tier_hint = profile.get("detected_tier", "active")
    sessions = profile.get("sessions_seen", 0)
    topics = profile.get("topics_seen", [])

    from datetime import date
    today = date.today()
    try:
        from services.api.routes.ui_data import _nse_market_context
        market_ctx = _nse_market_context()
    except Exception:
        market_ctx = f"Today: {today}"

    system = (
        f"{market_ctx}\n"
        f"User profile: tier={tier_hint}, sessions={sessions}, topics_seen={topics[:10]}\n\n"
        + DISPATCH_SYSTEM_PROMPT
    )

    lc_messages = [{"role": "system", "content": system}]
    for m in last_8:
        role = m.get("role", "user")
        if role in ("user", "assistant"):
            lc_messages.append({"role": role, "content": m.get("content", "")})

    try:
        response = await _dispatch_llm.ainvoke(lc_messages)
        parsed = _extract_json(response.content)
    except Exception as exc:
        logger.warning("Dispatch LLM call failed: %s", exc)
        parsed = None

    if not parsed or not parsed.get("tasks"):
        logger.warning("Dispatch returned no tasks — using fallback")
        return {
            "query_decomposition": "general market query",
            "user_tier": tier_hint,
            "browsing_strategy": {"topics": [], "geo": "in", "always_news": True},
            "tasks": _DISPATCH_FALLBACK_TASKS,
            "tool_results": [],
        }

    return {
        "query_decomposition": parsed.get("query_decomposition", ""),
        "user_tier": parsed.get("user_tier", tier_hint),
        "browsing_strategy": parsed.get("browsing_strategy", {}),
        "tasks": parsed.get("tasks", []),
        "tool_results": [],
    }
```

- [ ] **Step 4: Run tests**

```
pytest tests/unit/intelligence/chat/test_dispatch_node.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/api/chat_graph.py tests/unit/intelligence/chat/test_dispatch_node.py
git commit -m "feat(chat): add dispatch node — replaces classify+planner"
```

---

## Task 5: Async Parallel Executor Node

**Files:**
- Modify: `services/api/chat_graph.py`
- Create: `tests/unit/intelligence/chat/test_executor_node.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/intelligence/chat/test_executor_node.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_executor_runs_all_tasks_concurrently():
    """All tasks fire; results collected for both."""
    call_log = []

    async def mock_execute(name: str, args: dict) -> str:
        call_log.append(name)
        return f"result_{name}"

    tasks = [
        {"tool": "get_live_price", "args": {"symbol": "^NSEI"}, "priority": 1},
        {"tool": "get_macro_news", "args": {}, "priority": 2},
    ]

    with patch("services.api.routes.ui_data._execute_chat_tool", side_effect=mock_execute):
        from services.api.chat_graph import _run_tasks_parallel
        results = await _run_tasks_parallel(tasks)

    assert len(results) == 2
    assert "get_live_price" in call_log
    assert "get_macro_news" in call_log


@pytest.mark.asyncio
async def test_executor_one_failure_does_not_block_others():
    async def mock_execute(name: str, args: dict) -> str:
        if name == "bad_tool":
            raise ValueError("simulated failure")
        return "ok result"

    tasks = [
        {"tool": "bad_tool",  "args": {}, "priority": 1},
        {"tool": "good_tool", "args": {}, "priority": 1},
    ]

    with patch("services.api.routes.ui_data._execute_chat_tool", side_effect=mock_execute):
        from services.api.chat_graph import _run_tasks_parallel
        results = await _run_tasks_parallel(tasks)

    assert len(results) == 2
    ok = next(r for r in results if r["tool"] == "good_tool")
    assert ok["result"] == "ok result"
    bad = next(r for r in results if r["tool"] == "bad_tool")
    assert bad["result"] == ""
    assert "error" in bad


@pytest.mark.asyncio
async def test_executor_unknown_tool_returns_empty():
    async def mock_execute(name: str, args: dict) -> str:
        return f"Unknown tool: {name}"

    tasks = [{"tool": "nonexistent_tool", "args": {}, "priority": 1}]

    with patch("services.api.routes.ui_data._execute_chat_tool", side_effect=mock_execute):
        from services.api.chat_graph import _run_tasks_parallel
        results = await _run_tasks_parallel(tasks)

    assert "nonexistent_tool" in results[0]["result"] or results[0]["result"] == ""
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/chat/test_executor_node.py -v
```

Expected: `ImportError` — `_run_tasks_parallel` does not exist

- [ ] **Step 3: Add `_run_tasks_parallel` and `_node_executor` to chat_graph.py**

The existing `_execute_chat_tool(name, args)` in `ui_data.py` is already the single dispatch point for all tools. The executor wraps it — no new import map needed. The two new tools (Tasks 2 & 3) will be added to `_execute_chat_tool` directly in `ui_data.py`.

```python
async def _run_one_task(task: dict) -> dict:
    """Run a single tool task via _execute_chat_tool. Never raises."""
    from services.api.routes.ui_data import _execute_chat_tool

    tool_name = task.get("tool", "")
    args = task.get("args", {})

    try:
        result = await _execute_chat_tool(tool_name, args)
        return {"tool": tool_name, "args": args, "result": result or ""}
    except Exception as exc:
        logger.warning("Tool %s failed: %s", tool_name, exc)
        return {"tool": tool_name, "args": args, "result": "", "error": str(exc)}


async def _run_tasks_parallel(tasks: list[dict]) -> list[dict]:
    """Fire all tasks concurrently. Returns results list (same length as tasks)."""
    return list(await asyncio.gather(*[_run_one_task(t) for t in tasks]))


async def _node_executor(state: ChatState) -> dict:
    """Parallel async tool executor. Emits tool_start/tool_result SSE per task."""
    tasks = state.get("tasks") or []

    # Emit tool_start for all tasks immediately
    for task in tasks:
        await adispatch_custom_event(
            "tool_start",
            {"tool": task["tool"], "args": task.get("args", {})},
        )

    results = await _run_tasks_parallel(tasks)

    # Emit tool_result as each completes (in arrival order — already collected)
    for r in results:
        summary = str(r["result"])[:600] if r["result"] else "(no result)"
        await adispatch_custom_event(
            "tool_result",
            {"tool": r["tool"], "summary": summary},
        )

    return {"tool_results": results}
```

- [ ] **Step 4: Run tests**

```
pytest tests/unit/intelligence/chat/test_executor_node.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/api/chat_graph.py tests/unit/intelligence/chat/test_executor_node.py
git commit -m "feat(chat): add async parallel executor node"
```

---

## Task 6: Synthesize Node (Tier-Aware)

**Files:**
- Modify: `services/api/chat_graph.py`

- [ ] **Step 1: Add synthesize prompt builder and `_node_synthesize`**

Add after the executor code in `services/api/chat_graph.py`:

```python
def _build_synthesize_prompt(
    user_tier: str,
    query_decomposition: str,
    tool_results: list[dict],
    market_context: str,
) -> str:
    results_block = "\n\n".join(
        f"[{r['tool']}]\n{r['result']}"
        for r in tool_results
        if r.get("result")
    ) or "(no tool results — answer from general knowledge)"

    return f"""{market_context}

User tier: {user_tier}
What the user needs: {query_decomposition}

RESEARCH RESULTS:
{results_block}

---
Respond as a sharp Indian market analyst in a direct conversation.
Format and depth must match the user tier:

CASUAL   → 3-4 plain sentences. One key insight. No jargon. No tables. Friendly tone.
ACTIVE   → Price + direction + 2-3 dated headlines + what to watch. Use ▲/▼. Under 150 words.
EXPERT   → Regime, RL signal, conviction streak, key assumptions, raw metrics. Tables if helpful. No word cap.

Rules (always):
- If market not yet open, say so and reason from last close + pre-market cues
- Cite exact headlines with source and date — never paraphrase into fabricated summaries
- RL prediction: casual → "our model says"; active → verdict + confidence; expert → full metrics
- Historical trend: state what the data shows — never fabricate a predicted price number
- Never say "real-time data required" — state what you have and its date
- Never add unsolicited disclaimers or "I cannot predict" hedges
- If a tool result is empty or says "no data", ignore it silently
"""


# Module-level synthesize LLM client (patchable in tests)
_synthesize_llm = _ChatOpenAI(
    model=_FAST_MODEL,
    temperature=0.4,
    max_tokens=500,
    base_url="https://openrouter.ai/api/v1",
    api_key=__import__("os").environ.get("OPENROUTER_API_KEY", ""),
    streaming=True,
)


async def _node_synthesize(state: ChatState) -> dict:
    """Tier-aware synthesize node. Streams tokens as SSE events."""
    from services.api.user_profile import save_profile

    user_tier = state.get("user_tier") or "active"
    query_decomposition = state.get("query_decomposition") or ""
    tool_results = state.get("tool_results") or []
    messages = state.get("messages", [])
    session_id = state.get("session_id", "")

    try:
        from services.api.routes.ui_data import _nse_market_context
        market_context = _nse_market_context()
    except Exception:
        from datetime import date
        market_context = f"Today: {date.today()}"

    system_prompt = _build_synthesize_prompt(
        user_tier, query_decomposition, tool_results, market_context
    )

    lc_messages = [{"role": "system", "content": system_prompt}]
    for m in (messages[-8:] if len(messages) > 8 else messages):
        role = m.get("role", "user")
        if role in ("user", "assistant"):
            lc_messages.append({"role": role, "content": m.get("content", "")})

    full_answer = ""
    async for chunk in _synthesize_llm.astream(lc_messages):
        token = chunk.content if hasattr(chunk, "content") else str(chunk)
        if token:
            full_answer += token
            await adispatch_custom_event("token", {"text": token})

    # Persist user profile update after successful synthesis
    if session_id:
        browsing = state.get("browsing_strategy") or {}
        topics = browsing.get("topics", [])
        try:
            save_profile(
                session_id,
                tier=user_tier,
                tier_confidence=0.75,
                topics=topics,
            )
        except Exception as exc:
            logger.warning("Failed to update user profile: %s", exc)

    assistant_msg = {"role": "assistant", "content": full_answer}
    return {"messages": [assistant_msg]}
```

- [ ] **Step 2: Run existing tests to confirm no regressions**

```
pytest tests/unit/intelligence/chat/ -v
```

Expected: all previously passing tests still pass

- [ ] **Step 3: Commit**

```bash
git add services/api/chat_graph.py
git commit -m "feat(chat): add tier-aware synthesize node"
```

---

## Task 7: Wire the 3-Node Graph

**Files:**
- Modify: `services/api/chat_graph.py` — replace old graph definition with new one

- [ ] **Step 1: Replace the graph builder function in chat_graph.py**

Find the section that builds the LangGraph (typically `build_graph()` or similar) and replace it entirely:

```python
def build_chat_graph():
    """Build and compile the 3-node chat graph with MemorySaver."""
    graph = StateGraph(ChatState)

    graph.add_node("dispatch",    _node_dispatch)
    graph.add_node("executor",    _node_executor)
    graph.add_node("synthesize",  _node_synthesize)

    graph.set_entry_point("dispatch")
    graph.add_edge("dispatch",   "executor")
    graph.add_edge("executor",   "synthesize")
    graph.add_edge("synthesize", END)

    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


chat_graph = build_chat_graph()
```

- [ ] **Step 2: Verify the graph compiles without error**

```
python -c "from services.api.chat_graph import chat_graph; print('Graph OK:', chat_graph)"
```

Expected: `Graph OK: <CompiledStateGraph ...>` with no errors

- [ ] **Step 3: Commit**

```bash
git add services/api/chat_graph.py
git commit -m "feat(chat): wire 3-node graph — dispatch→executor→synthesize"
```

---

## Task 8: SSE Endpoint — Add Dispatch Event, Remove Reviewer

**Files:**
- Modify: `services/api/routes/ui_data.py` — update the `/ui/chat/stream` SSE handler

- [ ] **Step 1: Find the SSE stream handler in ui_data.py**

Search for the `/ui/chat/stream` endpoint:

```
grep -n "chat/stream\|astream_events\|adispatch_custom_event\|reviewer" services/api/routes/ui_data.py
```

- [ ] **Step 2: Update the event handler to emit `dispatch` event and remove `review` event**

In the SSE handler's event loop (the part that processes `astream_events` from LangGraph), add handling for the new `dispatch` event and remove the `review` event block:

```python
# Inside the async generator that processes astream_events:

elif kind == "on_custom_event":
    event_name = event["name"]
    data = event.get("data", {})

    if event_name == "tool_start":
        yield f"data: {json.dumps({'event': 'tool_start', 'tool': data.get('tool'), 'args': data.get('args', {})})}\n\n"

    elif event_name == "tool_result":
        yield f"data: {json.dumps({'event': 'tool_result', 'tool': data.get('tool'), 'summary': data.get('summary', '')})}\n\n"

    elif event_name == "token":
        yield f"data: {json.dumps({'event': 'token', 'text': data.get('text', '')})}\n\n"

    elif event_name == "dispatch":
        yield f"data: {json.dumps({'event': 'dispatch', 'tier': data.get('tier'), 'query': data.get('query', '')})}\n\n"

    # NOTE: "review" event removed — reviewer node no longer exists
```

Also update the dispatch node to emit its event (add this at the end of `_node_dispatch` in `chat_graph.py`, before the return):

```python
    await adispatch_custom_event(
        "dispatch",
        {
            "tier": parsed.get("user_tier", tier_hint),
            "query": parsed.get("query_decomposition", ""),
        },
    )
```

- [ ] **Step 3: Run the full unit test suite**

```
pytest tests/unit/ -v --tb=short
```

Expected: all tests pass (same count as before this task)

- [ ] **Step 4: Commit**

```bash
git add services/api/routes/ui_data.py services/api/chat_graph.py
git commit -m "feat(chat): add dispatch SSE event, remove reviewer event"
```

---

## Task 9: Remove Old Nodes + Dead Code

**Files:**
- Modify: `services/api/chat_graph.py` — delete `_node_classify`, `_node_planner`, `_node_reviewer`, old prompts, old state fields

- [ ] **Step 1: Delete dead code from chat_graph.py**

Remove the following from `services/api/chat_graph.py`:
- `CLASSIFY_SYSTEM_PROMPT` constant
- `PLANNER_SYSTEM_PROMPT` constant
- `REVIEWER_SYSTEM_PROMPT` constant
- `_REVIEWER_CRITERION_4` constant (if present)
- `_node_classify` function
- `_node_planner` function
- `_node_reviewer` function
- Any `_should_continue_executor` or similar conditional edge functions from the old loop
- Old `ChatState` fields: `intent`, `todo_list`, `needs_external`, `review_count`, `reviewer_feedback`

- [ ] **Step 2: Run full test suite**

```
pytest tests/ -v --tb=short -q
```

Expected: same pass count as before — no regressions from dead code removal

- [ ] **Step 3: Delete the old chat intent/entity test files that tested the removed nodes**

The following test files test nodes that no longer exist. Check each and delete if they only test removed code:

```
tests/unit/intelligence/chat/test_entity_extractor.py   ← tests classify entity extraction
tests/unit/intelligence/chat/test_intent_detector.py    ← tests classify intent detection
```

Run the deleted tests first to confirm they test only removed code:

```
pytest tests/unit/intelligence/chat/test_entity_extractor.py tests/unit/intelligence/chat/test_intent_detector.py -v
```

If they fail with `ImportError` on the removed functions, delete them:

```bash
git rm tests/unit/intelligence/chat/test_entity_extractor.py
git rm tests/unit/intelligence/chat/test_intent_detector.py
```

- [ ] **Step 4: Final test run**

```
pytest tests/ -v --tb=short -q
```

Expected: all remaining tests pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(chat): remove old classify/planner/reviewer nodes and dead prompts"
```

---

## Task 10: Smoke Test (End-to-End)

**Files:**
- No new files — manual verification

- [ ] **Step 1: Start the server**

```bash
cd "c:/Users/RevanParimi/OneDrive - IBM/Documents/Gen AI Projects/StockAgent-main"
python -m uvicorn services.api.server:app --port 8001 --reload
```

- [ ] **Step 2: Send the query that originally failed**

```bash
curl -N -X POST http://localhost:8001/ui/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Comparing the last 3 days Sensex, predict today as market has not opened yet", "session_id": null}'
```

Expected SSE stream:
```
data: {"event":"dispatch", "tier":"active", "query":"3-day Sensex comparison + prediction for today pre-open"}
data: {"event":"tool_start", "tool":"get_historical_prices", ...}
data: {"event":"tool_start", "tool":"get_live_price", ...}
data: {"event":"tool_start", "tool":"search_market_news", ...}
data: {"event":"tool_result", "tool":"get_live_price", "summary":"Sensex ..."}
data: {"event":"tool_result", "tool":"get_historical_prices", "summary":"^BSESN — Last 5 trading days:..."}
data: {"event":"token", "text":"**Sensex ▼ 3-day trend**..."}
...
data: {"event":"done"}
```

Verify:
- `get_historical_prices` fired (not just `get_live_price`)
- `search_market_news` fired without `needs_external` gate
- Response discusses actual 3-day trend from data, not fabricated
- No `review` event in the stream

- [ ] **Step 3: Send the IT sector query that was wrong**

```bash
curl -N -X POST http://localhost:8001/ui/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "IT was down on May 14, what is happening today May 15", "session_id": null}'
```

Verify:
- `search_market_news` fires with an IT-sector specific query
- Response cites actual dated headlines, not fabricated summaries

- [ ] **Step 4: Send a casual query to verify tier adaptation**

```bash
curl -N -X POST http://localhost:8001/ui/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "is the stock market good today", "session_id": null}'
```

Verify: `dispatch` event shows `"tier":"casual"` — response is plain English with no jargon

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "test: verify 3-node chat pipeline end-to-end smoke test passing"
```

---

## Summary

| Task | Adds / Changes | Tests |
|---|---|---|
| 1 — User Profile | `services/api/user_profile.py` | 5 unit tests |
| 2 — get_historical_prices | Tool in `ui_data.py` | 3 unit tests |
| 3 — get_rl_prediction | Tool in `ui_data.py` | 3 unit tests |
| 4 — Dispatch Node | Node + prompt + state schema in `chat_graph.py` | 3 unit tests |
| 5 — Async Executor | `_run_tasks_parallel` + `_node_executor` in `chat_graph.py` | 3 unit tests |
| 6 — Synthesize Node | Tier-aware node in `chat_graph.py` | Regression check |
| 7 — Wire Graph | `build_chat_graph()` in `chat_graph.py` | Compile check |
| 8 — SSE Events | `dispatch` event added, `review` removed | Full suite check |
| 9 — Remove Dead Code | Old nodes/prompts deleted | Full suite check |
| 10 — Smoke Test | Manual curl verification | 3 query scenarios |
