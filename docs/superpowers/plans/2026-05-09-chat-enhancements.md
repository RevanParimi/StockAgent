# Chat Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add intent classification, `get_sector_snapshot` / `run_agent_analysis` tools, SSE streaming, and frontend intent-badge + tool-trace UI to the StockAgent chat system.

**Architecture:** New `services/api/chat_intent.py` for the deterministic classifier; new tools added into the existing `_CHAT_TOOLS` list and `_execute_chat_tool` dispatch in `services/api/routes/ui_data.py`; a new `POST /ui/chat/stream` endpoint returns `text/event-stream`; `ChatOverlay` in `src/frontend/prototypes/sphere.jsx` switches from blocking `fetch` to a streaming reader and renders intent badge + collapsible tool trace.

**Tech Stack:** FastAPI `StreamingResponse`, asyncio, OpenAI streaming API (`stream=True`), Fetch ReadableStream in the browser, React hooks (useState/useRef/useEffect).

---

## Existing code map (read before touching)

| Path | Role |
|---|---|
| `services/api/routes/ui_data.py:1329-1431` | `_CHAT_TOOLS` list + `_execute_chat_tool` dispatch |
| `services/api/routes/ui_data.py:1531-1672` | `/ui/chat` POST endpoint + system prompt |
| `src/frontend/prototypes/sphere.jsx:149-241` | `ChatOverlay` component |
| `src/backend/sectors/__init__.py` | `detect_sector`, `get_orchestrator` |
| `services/data/stores/score_store.py` | `ScoreStore` — DB reads |

---

## Task 1: Intent Classifier

**Files:**
- Create: `services/api/chat_intent.py`
- Create: `tests/api/test_chat_intent.py`

### Context
The classifier is deterministic (no LLM). It pattern-matches on the user message to emit one of 9 intent types and extracts entity lists (tickers, sectors). It also returns the tool plan the LLM should run. This is fast — runs before the LLM call.

Nine intent types:
- `SINGLE_STOCK` — one ticker mentioned
- `STOCK_COMPARE` — multiple tickers + compare/vs/difference
- `SECTOR_OVERVIEW` — one sector keyword, no ticker
- `MULTI_SECTOR` — multiple sector keywords or "all sectors"
- `PRICE_QUERY` — price/how much/level asked
- `NEWS_QUERY` — why/what happened/news/reason
- `AGENT_QUERY` — agent name mentioned
- `RL_QUERY` — accuracy/trust/learn/weight mentioned
- `GENERAL` — everything else

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_chat_intent.py
import pytest
from services.api.chat_intent import classify_intent, IntentType

def test_single_stock():
    r = classify_intent("What's the outlook for MARUTI?", [])
    assert r.intent_type == IntentType.SINGLE_STOCK
    assert "MARUTI" in r.tickers

def test_stock_compare():
    r = classify_intent("Compare MARUTI vs TATAMOTORS", [])
    assert r.intent_type == IntentType.STOCK_COMPARE
    assert "MARUTI" in r.tickers
    assert "TATAMOTORS" in r.tickers

def test_sector_overview():
    r = classify_intent("How is the auto sector doing today?", [])
    assert r.intent_type == IntentType.SECTOR_OVERVIEW
    assert "automobile" in r.sectors

def test_multi_sector():
    r = classify_intent("Compare auto vs IT and banking sectors", [])
    assert r.intent_type == IntentType.MULTI_SECTOR
    assert len(r.sectors) >= 2

def test_price_query():
    r = classify_intent("What is the price of silver today?", [])
    assert r.intent_type == IntentType.PRICE_QUERY

def test_news_query():
    r = classify_intent("Why is MARUTI falling today?", [])
    assert r.intent_type == IntentType.NEWS_QUERY

def test_agent_query():
    r = classify_intent("What does the Sales & Demand agent say about MARUTI?", [])
    assert r.intent_type == IntentType.AGENT_QUERY

def test_rl_query():
    r = classify_intent("Which agent should I trust most for short-term trades?", [])
    assert r.intent_type == IntentType.RL_QUERY

def test_general():
    r = classify_intent("Hello, what can you do?", [])
    assert r.intent_type == IntentType.GENERAL
```

Run: `python -m pytest tests/api/test_chat_intent.py -v`
Expected: FAIL (module not found)

- [ ] **Step 2: Implement the classifier**

Create `services/api/chat_intent.py`:

```python
"""
chat_intent.py — deterministic intent classifier for the StockAgent chat system.
No LLM call: fast, predictable, runs before every message.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum

class IntentType(str, Enum):
    SINGLE_STOCK   = "SINGLE_STOCK"
    STOCK_COMPARE  = "STOCK_COMPARE"
    SECTOR_OVERVIEW = "SECTOR_OVERVIEW"
    MULTI_SECTOR   = "MULTI_SECTOR"
    PRICE_QUERY    = "PRICE_QUERY"
    NEWS_QUERY     = "NEWS_QUERY"
    AGENT_QUERY    = "AGENT_QUERY"
    RL_QUERY       = "RL_QUERY"
    GENERAL        = "GENERAL"

# Sector keyword → canonical sector key
_SECTOR_KEYWORDS: dict[str, str] = {
    "auto":        "automobile",
    "automobile":  "automobile",
    "automotive":  "automobile",
    "car":         "automobile",
    "ev":          "automobile",
    "it":          "it_sector",
    "tech":        "it_sector",
    "software":    "it_sector",
    "infosys":     "it_sector",
    "banking":     "banking_bfsi",
    "bank":        "banking_bfsi",
    "bfsi":        "banking_bfsi",
    "nbfc":        "banking_bfsi",
    "finance":     "banking_bfsi",
    "pharma":      "pharma",
    "energy":      "renewable_energy",
    "renewable":   "renewable_energy",
    "solar":       "renewable_energy",
    "power":       "renewable_energy",
    "fmcg":        "fmcg",
}

# Known NSE tickers the chat recognises
_KNOWN_TICKERS: frozenset[str] = frozenset({
    "MARUTI","TATAMOTORS","M&M","BAJAJ-AUTO","HEROMOTOCO","EICHERMOT",
    "TVSMOTORS","ASHOKLEY","TCS","INFY","WIPRO","HCLTECH","TECHM",
    "HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK",
    "ADANIGREEN","TATAPOWER","NTPC","POWERGRID","JSWENERGY",
    "APOLLOTYRE","MRF","ESCORTS","BOSCHLTD","BALKRISIND","MOTHERSON",
})

_AGENT_NAMES: frozenset[str] = frozenset({
    "sales", "demand", "fundamentals", "pattern", "raw material", "raw materials",
    "sentiment", "policy", "regulatory", "competitive", "intel", "risk", "macro",
    "valuation", "catalyst",
})

_COMPARE_WORDS = re.compile(r"\b(compare|vs|versus|difference|better|worse|relative)\b", re.I)
_PRICE_WORDS   = re.compile(r"\b(price|level|trading at|how much|what is .{0,20} at|current .{0,15} price)\b", re.I)
_NEWS_WORDS    = re.compile(r"\b(why|reason|what happened|news|cause|driving|behind|fall|rise|drop|surge)\b", re.I)
_RL_WORDS      = re.compile(r"\b(trust|accuracy|accurate|learn|weight|which agent|best agent|reliable)\b", re.I)


def _extract_tickers(text: str) -> list[str]:
    words = re.findall(r"[A-Z][A-Z0-9&\-]{1,11}", text.upper())
    return [w for w in words if w in _KNOWN_TICKERS]


def _extract_sectors(text: str) -> list[str]:
    tl = text.lower()
    found: dict[str, str] = {}
    for kw, sector in _SECTOR_KEYWORDS.items():
        if re.search(r"\b" + re.escape(kw) + r"\b", tl):
            found[sector] = sector
    return list(found.keys())


def _has_agent_mention(text: str) -> bool:
    tl = text.lower()
    return any(a in tl for a in _AGENT_NAMES) and "agent" in tl


@dataclass
class IntentResult:
    intent_type: IntentType
    tickers: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    display_label: str = ""

    def as_dict(self) -> dict:
        return {
            "intent_type":   self.intent_type.value,
            "tickers":       self.tickers,
            "sectors":       self.sectors,
            "display_label": self.display_label,
        }


def classify_intent(message: str, history: list[dict]) -> IntentResult:
    """
    Classify user intent from message text + optional conversation history.
    History is scanned for entity carry-over (tickers/sectors from prior turns).
    Returns IntentResult with intent_type, extracted entities, and display_label.
    """
    tickers = _extract_tickers(message)
    sectors = _extract_sectors(message)

    # Entity carry-over from history (last 4 turns)
    if not tickers and not sectors:
        for turn in (history or [])[-4:]:
            content = turn.get("content", "")
            tickers = tickers or _extract_tickers(content)
            sectors = sectors or _extract_sectors(content)

    ml = message.lower()

    # RL / trust query — check early (often contains agent words too)
    if _RL_WORDS.search(message):
        return IntentResult(
            IntentType.RL_QUERY, tickers, sectors,
            "[RL_QUERY] Agent accuracy & learning"
        )

    # Agent-specific query
    if _has_agent_mention(message):
        label = f"[AGENT_QUERY] → {tickers[0] if tickers else 'general'}"
        return IntentResult(IntentType.AGENT_QUERY, tickers, sectors, label)

    # Multiple tickers + compare words
    if len(tickers) >= 2 and _COMPARE_WORDS.search(message):
        label = f"[STOCK_COMPARE] → {' · '.join(tickers[:3])}"
        return IntentResult(IntentType.STOCK_COMPARE, tickers, sectors, label)

    # Multiple sectors
    if len(sectors) >= 2:
        label = f"[MULTI_SECTOR] → {' · '.join(sectors)}"
        return IntentResult(IntentType.MULTI_SECTOR, tickers, sectors, label)

    # Single ticker — no compare, no sector query
    if len(tickers) == 1 and not sectors:
        label = f"[SINGLE_STOCK] → {tickers[0]}"
        return IntentResult(IntentType.SINGLE_STOCK, tickers, sectors, label)

    # Single sector overview
    if len(sectors) == 1 and not tickers:
        label = f"[SECTOR_OVERVIEW] → {sectors[0]}"
        return IntentResult(IntentType.SECTOR_OVERVIEW, tickers, sectors, label)

    # Single sector with tickers = sector+stock combo → treat as single stock with sector context
    if tickers and sectors:
        label = f"[SINGLE_STOCK] → {tickers[0]} ({sectors[0]})"
        return IntentResult(IntentType.SINGLE_STOCK, tickers, sectors, label)

    # News / why queries
    if _NEWS_WORDS.search(message):
        label = "[NEWS_QUERY] Market news & drivers"
        return IntentResult(IntentType.NEWS_QUERY, tickers, sectors, label)

    # Price queries
    if _PRICE_WORDS.search(message):
        label = "[PRICE_QUERY] Live price"
        return IntentResult(IntentType.PRICE_QUERY, tickers, sectors, label)

    return IntentResult(IntentType.GENERAL, tickers, sectors, "[GENERAL] General inquiry")
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_chat_intent.py -v`
Expected: All 9 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add services/api/chat_intent.py tests/api/test_chat_intent.py
git commit -m "feat: add deterministic intent classifier (9 types)"
```

---

## Task 2: Add `get_sector_snapshot` and `run_agent_analysis` tools

**Files:**
- Modify: `services/api/routes/ui_data.py`

### Context
These two tools fill the data gaps described in the spec.
- `get_sector_snapshot(sector)` reads the NSE sector index price + all recent verdicts for tickers in that sector from the DB.
- `run_agent_analysis(ticker)` returns the latest cached analysis from DB; if no cached data, triggers the orchestrator with a 45-second timeout.

Both tools are added to `_CHAT_TOOLS` (the list used by the LLM) and to `_execute_chat_tool` (the dispatch function). The ticker→sector mapping already exists in `src/backend/sectors/__init__.py`.

- [ ] **Step 1: Verify existing tool list length**

Run: `python -c "from services.api.routes.ui_data import _CHAT_TOOLS; print(len(_CHAT_TOOLS), 'tools')"` from project root.
Expected: `5 tools`

- [ ] **Step 2: Add sector→ticker mapping and snapshot implementation**

In `services/api/routes/ui_data.py`, add after the `_COMMODITY_YF` dict (around line 1327):

```python
# Sector name → yfinance NSE sector index
_SECTOR_INDEX_YF: dict[str, str] = {
    "automobile":      "^CNXAUTO",
    "banking_bfsi":    "^NSEBANK",
    "it_sector":       "^CNXIT",
    "renewable_energy":"^CNXENERGY",
    "pharma":          "^CNXPHARMA",
    "fmcg":            "^CNXFMCG",
}

# Sector → tickers list (for verdict counts)
_SECTOR_TICKERS: dict[str, list[str]] = {
    "automobile":       ["MARUTI","TATAMOTORS","M&M","BAJAJ-AUTO","HEROMOTOCO","EICHERMOT","TVSMOTORS","ASHOKLEY"],
    "banking_bfsi":     ["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK","INDUSINDBK"],
    "it_sector":        ["TCS","INFY","WIPRO","HCLTECH","TECHM","LTIM"],
    "renewable_energy": ["ADANIGREEN","TATAPOWER","NTPC","POWERGRID","JSWENERGY"],
    "pharma":           [],
    "fmcg":             [],
}


async def _chat_tool_get_sector_snapshot(sector: str) -> str:
    """Fetch NSE sector index price + verdict counts from DB."""
    sector = sector.strip().lower().replace(" ", "_")
    # Normalize common aliases
    alias = {"auto": "automobile", "banking": "banking_bfsi", "it": "it_sector",
             "energy": "renewable_energy", "renewable": "renewable_energy"}
    sector = alias.get(sector, sector)

    yf_sym = _SECTOR_INDEX_YF.get(sector)
    if not yf_sym:
        return f"Unknown sector '{sector}'. Known: {', '.join(_SECTOR_INDEX_YF)}."

    price, change = await asyncio.to_thread(_fetch_yf_price, yf_sym)
    arrow = "▲" if change >= 0 else "▼"

    # Verdict counts from DB
    store = _score_store()
    tickers_in_sector = _SECTOR_TICKERS.get(sector, [])
    verdicts: list[str] = []
    for sym in tickers_in_sector:
        row = await asyncio.to_thread(store.get_latest, sym)
        if row:
            verdicts.append(row["verdict"])

    verdict_summary = ""
    if verdicts:
        counts: dict[str, int] = {}
        for v in verdicts:
            counts[v] = counts.get(v, 0) + 1
        verdict_summary = " · ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        verdict_summary = f" [{len(verdicts)} verdicts: {verdict_summary}]"

    label = sector.replace("_", " ").title()
    if price:
        return f"{label} index ({yf_sym}): {price:,.0f}  {arrow}{abs(change):.2f}%{verdict_summary}"
    return f"{label} index: price unavailable{verdict_summary}"


async def _chat_tool_run_agent_analysis(ticker: str) -> str:
    """Return cached analysis from DB; trigger orchestrator if no data (45s timeout)."""
    ticker = ticker.strip().upper()
    store = _score_store()
    row = await asyncio.to_thread(store.get_latest, ticker)
    if row:
        score = float(row["final_score"])
        verdict = row["verdict"]
        run_at = (row.get("run_at") or "")[:10]
        thesis = (row.get("investment_thesis") or "")[:200]
        return (
            f"{ticker}: {verdict} (score={score:.2f}, run {run_at})\n"
            f"Thesis: {thesis}"
        )
    # No cached data — trigger a fresh analysis
    try:
        from backend.sectors import detect_sector, get_orchestrator
        sector = detect_sector(ticker)
        OrchestratorClass = get_orchestrator(sector)
        orchestrator = OrchestratorClass()
        report = await asyncio.wait_for(
            orchestrator.analyse_async(ticker),
            timeout=45.0,
        )
        return (
            f"{ticker}: {report.verdict} (score={report.final_score:.2f}, fresh)\n"
            f"Thesis: {(report.investment_thesis or '')[:200]}"
        )
    except asyncio.TimeoutError:
        return f"Analysis for {ticker} timed out after 45s. Click 'Analyze' on the Home screen to run a full analysis."
    except Exception as exc:
        return f"Could not run analysis for {ticker}: {exc}"
```

- [ ] **Step 3: Add the two tool definitions to `_CHAT_TOOLS`**

In `services/api/routes/ui_data.py`, append to the `_CHAT_TOOLS` list (after the `get_rl_insights` entry, before the closing `]`):

```python
    {
        "type": "function",
        "function": {
            "name": "get_sector_snapshot",
            "description": (
                "Fetch the live NSE sector index price and recent agent verdicts for a sector. "
                "Use when the user asks about a sector (auto, banking, IT, energy, pharma, FMCG). "
                "Pass the sector name as a plain string."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Sector name: automobile, banking_bfsi, it_sector, renewable_energy, pharma, fmcg"
                    }
                },
                "required": ["sector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_agent_analysis",
            "description": (
                "Get the latest StockAgent deep analysis for an NSE ticker: verdict, score, thesis, "
                "agent breakdown. Returns cached result if available, otherwise triggers a fresh analysis. "
                "Use when the user wants a detailed deep-dive on a specific stock."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "NSE ticker symbol e.g. MARUTI, TATAMOTORS."
                    }
                },
                "required": ["ticker"],
            },
        },
    },
```

- [ ] **Step 4: Add the two tools to `_execute_chat_tool` dispatch**

In `_execute_chat_tool` in `ui_data.py`, add before the final `return f"Unknown tool: {name}"` line:

```python
    if name == "get_sector_snapshot":
        return await _chat_tool_get_sector_snapshot(args.get("sector", ""))
    if name == "run_agent_analysis":
        return await _chat_tool_run_agent_analysis(args.get("ticker", ""))
```

- [ ] **Step 5: Smoke-test the new tools with curl**

Start server first: `uvicorn services.api.server:app --port 8001 --reload` (keep running in another terminal).

```bash
curl -s -X POST http://localhost:8001/ui/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How is the auto sector doing?","history":[]}' | python -m json.tool
```
Expected: JSON with `reply` field containing sector index data and verdicts.

```bash
curl -s -X POST http://localhost:8001/ui/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Give me a deep analysis of MARUTI","history":[]}' | python -m json.tool
```
Expected: JSON with `reply` containing verdict, score, thesis (from DB or fresh analysis).

- [ ] **Step 6: Commit**

```bash
git add services/api/routes/ui_data.py
git commit -m "feat: add get_sector_snapshot and run_agent_analysis chat tools"
```

---

## Task 3: SSE Streaming Endpoint

**Files:**
- Modify: `services/api/routes/ui_data.py`

### Context
Add `POST /ui/chat/stream` that emits Server-Sent Events over a `StreamingResponse`. The endpoint uses the OpenAI streaming API (`stream=True`) to forward tokens as they arrive.

Events emitted in order:
1. `{"event":"intent", "intent_type":"SINGLE_STOCK", "display_label":"[SINGLE_STOCK] → MARUTI", "tickers":["MARUTI"], "sectors":[]}`
2. `{"event":"tool_start", "tool":"get_stock_analysis", "args":{"ticker":"MARUTI"}}`
3. `{"event":"tool_result", "tool":"get_stock_analysis", "summary":"MARUTI: STRONG BUY (score=0.82...)"}`
4. `{"event":"token", "text":"MARUTI is currently..."}`  (many of these)
5. `{"event":"done"}`

The frontend uses `fetch()` with a `ReadableStream` reader (not EventSource) because POST with body is required.

- [ ] **Step 1: Add the SSE endpoint to `ui_data.py`**

Add this after the existing `/chat` POST handler (around line 1672):

```python
@router.post("/chat/stream", summary="AI assistant chat — SSE streaming response")
async def chat_stream(body: dict):
    """
    Streaming version of /ui/chat.
    Returns text/event-stream; each line is a JSON event.
    Events: intent | tool_start | tool_result | token | done
    """
    from fastapi.responses import StreamingResponse
    from services.api.chat_intent import classify_intent

    message: str = (body.get("message") or "").strip()
    history: list = body.get("history") or []
    if not message:
        async def _empty():
            yield 'data: {"event":"done"}\n\n'
        return StreamingResponse(_empty(), media_type="text/event-stream")

    async def generate():
        import json as _json

        # 1. Intent classification (instant, no LLM)
        intent = classify_intent(message, history)
        yield f"data: {_json.dumps({'event': 'intent', **intent.as_dict()})}\n\n"

        # 2. Build messages list (same as /chat)
        context = _build_chat_context(message)
        system_prompt = _CHAT_SYSTEM_PROMPT.format(context=context)
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for h in history[-8:]:
            role = h.get("role", "")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        try:
            from services.clients.llm_client import get_async_llm_client
            client = get_async_llm_client()

            # 3. Tool loop (max 4 rounds, non-streaming for tool calls)
            tool_trace: list[dict] = []
            for _ in range(4):
                resp = await client.chat.completions.create(
                    model="qwen/qwen3-235b-a22b",
                    messages=messages,
                    temperature=0.4,
                    max_tokens=600,
                    tools=_CHAT_TOOLS,
                    tool_choice="auto",
                )
                msg = resp.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None) or []

                if not tool_calls:
                    # No more tool calls — break and stream final answer
                    break

                # Emit tool_start for each call
                for tc in tool_calls:
                    args_str = tc.function.arguments or "{}"
                    try:
                        args_dict = _json.loads(args_str)
                    except Exception:
                        args_dict = {}
                    yield f"data: {_json.dumps({'event': 'tool_start', 'tool': tc.function.name, 'args': args_dict})}\n\n"

                # Execute tools
                assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
                assistant_entry["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ]
                messages.append(assistant_entry)

                tool_results = await asyncio.gather(*[
                    _execute_chat_tool(tc.function.name, _json.loads(tc.function.arguments or "{}"))
                    for tc in tool_calls
                ])
                for tc, result in zip(tool_calls, tool_results):
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    # Emit tool_result with a short summary (first 120 chars)
                    summary = result[:120].replace("\n", " ")
                    yield f"data: {_json.dumps({'event': 'tool_result', 'tool': tc.function.name, 'summary': summary})}\n\n"
                    tool_trace.append({"tool": tc.function.name, "summary": summary})

            # 4. Stream the final answer token by token
            stream = await client.chat.completions.create(
                model="qwen/qwen3-235b-a22b",
                messages=messages,
                temperature=0.4,
                max_tokens=600,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                text = (delta.content or "") if delta else ""
                if text:
                    yield f"data: {_json.dumps({'event': 'token', 'text': text})}\n\n"

        except Exception as exc:
            logger.warning("[ui/chat/stream] Error: %s", exc)
            fallback = _mock_reply(message)
            yield f"data: {_json.dumps({'event': 'token', 'text': fallback})}\n\n"

        yield 'data: {"event":"done"}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )
```

- [ ] **Step 2: Test the SSE endpoint with curl**

```bash
curl -N -X POST http://localhost:8001/ui/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"How is the auto sector doing?","history":[]}' 
```
Expected output (one line per event, streaming):
```
data: {"event": "intent", "intent_type": "SECTOR_OVERVIEW", ...}
data: {"event": "tool_start", "tool": "get_sector_snapshot", ...}
data: {"event": "tool_result", "tool": "get_sector_snapshot", "summary": "Automobile index..."}
data: {"event": "token", "text": "The auto sector..."}
data: {"event": "token", "text": " is currently..."}
...
data: {"event": "done"}
```

- [ ] **Step 3: Test with a SINGLE_STOCK query**

```bash
curl -N -X POST http://localhost:8001/ui/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"What should I do with MARUTI?","history":[]}'
```
Expected: `intent_type: SINGLE_STOCK` event, then tool calls for `get_live_price` and `get_stock_analysis`, then tokens.

- [ ] **Step 4: Test with follow-up entity carry-over**

```bash
curl -N -X POST http://localhost:8001/ui/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"What about the risks?","history":[{"role":"user","content":"Tell me about MARUTI"},{"role":"assistant","content":"MARUTI is strong..."}]}'
```
Expected: Intent should still resolve MARUTI from history context (SINGLE_STOCK).

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/ui_data.py
git commit -m "feat: add SSE streaming /ui/chat/stream with intent + tool-trace events"
```

---

## Task 4: Frontend — Intent Badge, Tool Trace, Streaming

**Files:**
- Modify: `src/frontend/prototypes/sphere.jsx` (the `ChatOverlay` function, lines 149–241)

### Context
Replace the existing blocking `fetch('/ui/chat', {method:'POST'})` with a streaming `fetch('/ui/chat/stream')` that reads the response body as a `ReadableStream`.

The message object in `msgs` state grows:
```js
// Before: {from, text, loading}
// After:  {from, text, loading, intent, toolTrace}
```

New sub-components added:
- `IntentBadge({intent})` — renders `[SECTOR_OVERVIEW] → automobile` inline above the bot bubble
- `ToolTracePanel({trace})` — collapsible `<details>` panel showing each tool run

**Important**: `ChatOverlay` is defined inside `sphere.jsx` and exported as `window.ChatOverlay`. Do NOT move it to another file or change its props (`open`, `onClose`, `mode`).

- [ ] **Step 1: Replace the `send` function in `ChatOverlay` with a streaming version**

In `src/frontend/prototypes/sphere.jsx`, replace the `ChatOverlay` function (the entire block from `function ChatOverlay` to `window.ChatOverlay = ChatOverlay;`) with:

```jsx
// Intent badge — small chip above the bot bubble
function IntentBadge({ intent }) {
  if (!intent) return null;
  const typeColors = {
    SINGLE_STOCK: '#0891b2', STOCK_COMPARE: '#7c3aed', SECTOR_OVERVIEW: '#059669',
    MULTI_SECTOR: '#d97706', PRICE_QUERY: '#dc2626', NEWS_QUERY: '#2563eb',
    AGENT_QUERY: '#9333ea', RL_QUERY: '#c026d3', GENERAL: '#64748b',
  };
  const color = typeColors[intent.intent_type] || '#64748b';
  return (
    <div style={{ fontSize:10, fontWeight:700, letterSpacing:'.06em', color, marginBottom:4,
      display:'flex', alignItems:'center', gap:6, flexWrap:'wrap' }}>
      <span style={{ padding:'2px 6px', borderRadius:4, background:`${color}22`, border:`1px solid ${color}44` }}>
        {intent.intent_type}
      </span>
      {intent.display_label && intent.display_label !== `[${intent.intent_type}]` && (
        <span style={{ color:'var(--ink-3)', fontWeight:500 }}>{intent.display_label.replace(/^\[[A-Z_]+\]\s*/,'')}</span>
      )}
    </div>
  );
}

// Tool trace panel — collapsible
function ToolTracePanel({ trace }) {
  if (!trace || trace.length === 0) return null;
  return (
    <details style={{ marginTop:6, fontSize:11 }}>
      <summary style={{ cursor:'pointer', color:'var(--ink-3)', userSelect:'none', marginBottom:4 }}>
        {trace.length} tool{trace.length > 1 ? 's' : ''} used
      </summary>
      <div style={{ display:'flex', flexDirection:'column', gap:3, paddingTop:4 }}>
        {trace.map((t, i) => (
          <div key={i} style={{ display:'flex', gap:8, alignItems:'flex-start',
            padding:'4px 8px', background:'var(--bg-tinted)', borderRadius:6, fontFamily:'var(--font-mono,monospace)' }}>
            <span style={{ color:'var(--buy)', flexShrink:0 }}>✓</span>
            <span style={{ color:'var(--cyan)', flexShrink:0 }}>{t.tool}()</span>
            <span style={{ color:'var(--ink-3)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              {t.summary}
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}

function ChatOverlay({ open, onClose, mode='wireframe' }) {
  const [msgs, setMsgs] = useState([
    { from:'bot', text:"Hi I'm your StockAgent assistant. Ask me anything about Indian markets." }
  ]);
  const [input, setInput] = useState('');
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollTo?.(0, 99999); }, [msgs, open]);

  const send = async (text) => {
    if (!text.trim()) return;
    setInput('');
    const history = msgs
      .filter(m => !m.loading)
      .slice(-8)
      .map(m => ({ role: m.from === 'user' ? 'user' : 'assistant', content: m.text }));

    setMsgs(m => [...m,
      { from:'user', text },
      { from:'bot', text:'', loading:true, intent:null, toolTrace:[] }
    ]);

    try {
      const resp = await fetch('/ui/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history }),
      });

      if (!resp.ok || !resp.body) throw new Error('Stream unavailable');

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();  // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.event === 'intent') {
              setMsgs(m => {
                const next = [...m];
                next[next.length - 1] = { ...next[next.length - 1], intent: evt };
                return next;
              });
            } else if (evt.event === 'tool_result') {
              setMsgs(m => {
                const next = [...m];
                const last = next[next.length - 1];
                next[next.length - 1] = {
                  ...last,
                  toolTrace: [...(last.toolTrace || []), { tool: evt.tool, summary: evt.summary }]
                };
                return next;
              });
            } else if (evt.event === 'token') {
              setMsgs(m => {
                const next = [...m];
                next[next.length - 1] = {
                  ...next[next.length - 1],
                  text: (next[next.length - 1].text || '') + evt.text,
                  loading: false,
                };
                return next;
              });
            } else if (evt.event === 'done') {
              setMsgs(m => {
                const next = [...m];
                next[next.length - 1] = { ...next[next.length - 1], loading: false };
                return next;
              });
            }
          } catch {}
        }
      }
    } catch {
      // Fallback to blocking POST if streaming fails
      try {
        const res = await fetch('/ui/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, history }),
        });
        const data = res.ok ? await res.json() : {};
        setMsgs(m => [...m.slice(0, -1), { from:'bot', text: data.reply || 'Error', loading:false }]);
      } catch {
        setMsgs(m => [...m.slice(0, -1), { from:'bot', text:'Network error — try again.', loading:false }]);
      }
    }
  };

  if (!open) return null;
  return (
    <div className="chat-overlay" style={{
      background:'var(--bg-surface)', border:'1px solid var(--border)',
      display:'flex', flexDirection:'column'
    }}>
      <div className="drawer-handle"/>
      <style>{`@keyframes chat-in { from { opacity:0; transform: translateY(12px) scale(.98); } to { opacity:1; transform:none; } }`}</style>
      <div style={{ padding:'14px 16px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:12 }}>
        <Sphere size={36} mode={mode}/>
        <div style={{ flex:1 }}>
          <div style={{ fontWeight:700, fontSize:14, color:'var(--ink-1)' }}>StockAgent AI</div>
          <div style={{ fontSize:11, color:'var(--ink-3)', display:'flex', alignItems:'center', gap:6 }}>
            <span style={{ width:6, height:6, borderRadius:'50%', background:'var(--buy)', display:'inline-block' }}/>
            9 agents online · live
          </div>
        </div>
        <button onClick={onClose} style={{ background:'transparent', border:'none', color:'var(--ink-3)', padding:4 }}><Icon.X size={18}/></button>
      </div>
      <div ref={endRef} style={{ flex:1, padding:16, overflowY:'auto', display:'flex', flexDirection:'column', gap:10 }}>
        {msgs.map((m, i) => {
          const bubbleStyle = {
            alignSelf: m.from==='user' ? 'flex-end' : 'flex-start',
            maxWidth:'82%', padding:'10px 14px',
            background: m.from==='user' ? 'var(--cyan)' : 'var(--bg-tinted)',
            color: m.from==='user' ? '#fff' : 'var(--ink-1)',
            borderRadius: m.from==='user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
            fontSize:13, lineHeight:1.6,
            animation: m.loading && !m.text ? 'pulse-soft 1.2s ease-in-out infinite' : 'none',
            opacity: m.loading && !m.text ? 0.7 : 1,
          };
          if (m.from === 'bot') {
            return (
              <div key={i} style={{ alignSelf:'flex-start', maxWidth:'82%' }}>
                <IntentBadge intent={m.intent}/>
                <div className="chat-md" style={bubbleStyle}
                  dangerouslySetInnerHTML={{ __html: m.loading && !m.text ? '…' : renderMd(m.text) }}/>
                <ToolTracePanel trace={m.toolTrace}/>
              </div>
            );
          }
          return <div key={i} style={bubbleStyle}>{m.text}</div>;
        })}
        {msgs.length===1 && <div style={{ display:'flex', flexDirection:'column', gap:6, marginTop:8 }}>
          {(window.CHAT_SEEDS || []).map(s => (
            <button key={s} onClick={()=>send(s)} style={{
              textAlign:'left', padding:'8px 12px', borderRadius:10, border:'1px solid var(--border)',
              background:'transparent', color:'var(--ink-2)', fontSize:12
            }}>{s}</button>
          ))}
        </div>}
      </div>
      <form onSubmit={e=>{e.preventDefault(); send(input);}} style={{
        padding:12, borderTop:'1px solid var(--border)', display:'flex', gap:8, alignItems:'center'
      }}>
        <input value={input} onChange={e=>setInput(e.target.value)} placeholder="Ask about a stock or sector…"
          style={{ flex:1, border:'1px solid var(--border)', borderRadius:999, padding:'10px 14px',
                   background:'var(--bg-base)', color:'var(--ink-1)', fontSize:13, outline:'none' }}/>
        <button type="submit" style={{
          width:36, height:36, borderRadius:'50%', border:'none', background:'var(--cyan)', color:'#fff',
          display:'grid', placeItems:'center'
        }}><Icon.Send size={16}/></button>
      </form>
    </div>
  );
}
window.ChatOverlay = ChatOverlay;
```

- [ ] **Step 2: Remove the old `mockReply` function**

The old `mockReply` function (lines ~243–250) is no longer needed in sphere.jsx since fallback now calls `/ui/chat`. Delete it.

- [ ] **Step 3: Open the app in the browser and test manually**

Open `src/frontend/prototypes/index.html` directly in Chrome (or navigate to `http://localhost:8001/app/`).

Test sequence:
1. Click "Ask the assistant" button
2. Type: "How is the auto sector doing today?" → verify intent badge shows `SECTOR_OVERVIEW`, tool trace shows `get_sector_snapshot`, response is grounded
3. Type: "Compare MARUTI vs TATAMOTORS" → verify `STOCK_COMPARE` badge, tokens stream in
4. Type: "What should I trust most?" → verify `RL_QUERY` badge
5. Type: "What about risks?" (after a stock question) → verify entity carry-over shows the prior ticker

- [ ] **Step 4: Commit**

```bash
git add src/frontend/prototypes/sphere.jsx
git commit -m "feat: ChatOverlay — SSE streaming, intent badge, tool trace panel"
```

---

## Task 5: End-to-End Verification and Push

**Files:** None changed — verification only.

- [ ] **Step 1: Run the full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: Same pass count as before (≥275), no new failures.

- [ ] **Step 2: Verify intent classifier is importable from the project root**

```bash
python -c "from services.api.chat_intent import classify_intent, IntentType; r = classify_intent('How is banking sector?', []); print(r.intent_type, r.sectors)"
```
Expected: `IntentType.SECTOR_OVERVIEW ['banking_bfsi']`

- [ ] **Step 3: Verify both chat endpoints**

```bash
# Blocking endpoint still works
curl -s -X POST http://localhost:8001/ui/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is silver price?","history":[]}' | python -m json.tool

# Streaming endpoint returns SSE
curl -N -X POST http://localhost:8001/ui/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"What is silver price?","history":[]}'
```
Expected (blocking): `{"reply": "Silver (SI=F): ..."}`
Expected (streaming): Multiple `data:` lines ending with `data: {"event":"done"}`

- [ ] **Step 4: Verify debug logs show intent + tools in server output**

In the server terminal, after each chat request, verify you see lines like:
```
INFO     services.api.routes.ui_data — [ui/chat/stream] ...
```
(No crashes, no unhandled exceptions.)

- [ ] **Step 5: Push to remote**

```bash
git log --oneline -5   # review the 4 commits
git push
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Intent badge — IntentBadge component + intent SSE event
- [x] Tool trace — ToolTracePanel + tool_result SSE events
- [x] Streaming tokens — token SSE events + ReadableStream reader
- [x] `get_sector_snapshot` — reads NSE index + DB verdicts
- [x] `run_agent_analysis` — DB cache + orchestrator fallback
- [x] Intent classifier — 9 types, deterministic
- [x] Follow-up entity continuity — history scan in `classify_intent`
- [x] Old `/ui/chat` unbroken — streaming endpoint is additive

**No placeholders:** All code blocks contain real, complete implementations.

**Type consistency:**
- `IntentResult.as_dict()` returns `{intent_type, tickers, sectors, display_label}` — matches frontend `evt` destructuring
- `toolTrace` array shape `{tool: str, summary: str}` — matches `ToolTracePanel` props
- Tool names in `_CHAT_TOOLS` match names in `_execute_chat_tool` and SSE tool_start events
