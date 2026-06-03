"""
LangGraph chat pipeline for StockAgent.

Graph: dispatch → executor → synthesize → END

State:
  messages:            Annotated[list, operator.add]  — plain OpenAI-format dicts
  query_decomposition: str | None   — from dispatch: plain-English summary of user need
  user_tier:           str | None   — casual | active | expert
  browsing_strategy:   dict | None  — from dispatch: topics, geo, always_news
  tasks:               list[dict] | None — from dispatch: [{tool, args, priority}]
  tool_results:        list[dict] | None — from executor: [{tool, result, error}]
  session_id:          str | None   — session/thread ID for user profile and memory

Carry-over: MemorySaver keyed by thread_id (= session_id).
  state.messages accumulates across HTTP requests — no client-side history.

SSE events dispatched via adispatch_custom_event:
  "dispatch"    — dispatch done (tier, query decomposition)
  "tool_start"  — executor about to run a task
  "tool_result" — executor finished a task
  "token"       — synthesize streaming chunks
  "thinking"    — model entered a think block (Qwen3)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from operator import add
from typing import Annotated

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from services.clients.llm_client import get_async_llm_client

logger = logging.getLogger(__name__)

# Fast model — used for dispatch and synthesize.
# qwen-2.5-72b has no think-block overhead: ~0.5-1s per call vs 5-30s for Qwen3-235B.
# Reads from settings so the user can override via LLM_MODEL in .env.
try:
    from backend.shared.config import settings as _chat_cfg
    _FAST_MODEL: str = _chat_cfg.LLM_MODEL
except Exception:
    _FAST_MODEL = "qwen/qwen-2.5-72b-instruct"

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
  active  — uses market terms, comparisons ("compare 3 days", "FII data", "sector rotation")
  expert  — technical signals ("VIX elevated", "RSI oversold", "regime", "conviction")

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
    {"tool": "get_live_price",     "args": {"symbol": "^NSEI"},                         "priority": 1},
    {"tool": "get_macro_news",     "args": {},                                            "priority": 2},
    {"tool": "search_market_news", "args": {"query": "India Nifty Sensex market news"},  "priority": 2},
]


# ---------------------------------------------------------------------------
# Helpers — JSON extraction (Qwen3 emits <think>…</think> before JSON)
# ---------------------------------------------------------------------------

def _extract_json(content: str) -> dict | None:
    """Extract JSON object from LLM output.
    Handles: Qwen3 <think> blocks, <json> delimiters, ```json fences, raw objects.
    """
    # Strip thinking blocks
    text = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    # Try <json>…</json> tags first (our explicit delimiter)
    m = re.search(r"<json>(.*?)</json>", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    else:
        # Try ```json…``` fence
        m2 = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
        if m2:
            text = m2.group(1).strip()
    # Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    # Last resort: find first {...} block
    m3 = re.search(r"\{.*\}", text, re.DOTALL)
    if m3:
        try:
            result = json.loads(m3.group())
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ChatState(TypedDict):
    messages:            Annotated[list, add]   # MemorySaver key — unchanged
    query_decomposition: str | None             # from dispatch: what user needs
    user_tier:           str | None             # casual | active | expert
    browsing_strategy:   dict | None            # from dispatch: topics, geo, always_news
    tasks:               list[dict] | None      # from dispatch: [{tool, args, priority}]
    tool_results:        list[dict] | None      # from executor: [{tool, result, error}]
    session_id:          str | None             # session/thread ID for user profile and memory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_role(msg: dict | object) -> str:
    if isinstance(msg, dict):
        return msg.get("role", "")
    return getattr(msg, "type", "") or getattr(msg, "role", "")


def _to_openai_msgs(messages: list) -> list:
    """Convert state messages (plain dicts or LangChain objects) to OpenAI format."""
    result = []
    for m in messages:
        if isinstance(m, dict):
            result.append(m)
        else:
            msg_type = getattr(m, "type", "unknown")
            content = getattr(m, "content", "")
            if msg_type == "human":
                result.append({"role": "user", "content": content})
            elif msg_type == "ai":
                entry: dict = {"role": "assistant", "content": content or ""}
                tcs = getattr(m, "tool_calls", None)
                if tcs:
                    entry["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc.get("args", {})),
                            },
                        }
                        for tc in tcs
                    ]
                result.append(entry)
            elif msg_type == "tool":
                result.append({
                    "role": "tool",
                    "tool_call_id": getattr(m, "tool_call_id", ""),
                    "content": content,
                })
    return result


def _last_user_text(state: ChatState) -> str:
    m = next((m for m in reversed(state["messages"]) if _get_role(m) == "user"), None)
    if not m:
        return ""
    return m["content"] if isinstance(m, dict) else getattr(m, "content", "")


# ---------------------------------------------------------------------------
# Dispatch node
# ---------------------------------------------------------------------------

async def _node_dispatch(state: ChatState) -> dict:
    """Single LLM call: decompose query + detect user tier + plan tasks."""
    from services.api.user_profile import load_profile

    messages = state.get("messages", [])
    session_id = state.get("session_id", "")

    profile = load_profile(session_id) if session_id else {}
    tier_hint = profile.get("detected_tier", "active")
    sessions = profile.get("sessions_seen", 0)
    topics = profile.get("topics_seen", [])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")
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

    dispatch_msgs = [{"role": "system", "content": system}]
    dispatch_msgs.extend(_to_openai_msgs(messages[-8:]))

    parsed = None
    try:
        client = get_async_llm_client()
        resp = await client.chat.completions.create(
            model=_FAST_MODEL,
            messages=dispatch_msgs,
            max_tokens=400,
            temperature=0.0,
        )
        parsed = _extract_json(resp.choices[0].message.content or "")
    except Exception as exc:
        logger.warning("[dispatch] LLM call failed: %s", exc)

    if not parsed or not parsed.get("tasks"):
        logger.warning("[dispatch] no tasks returned — using fallback")
        return {
            "query_decomposition": "general market query",
            "user_tier": tier_hint,
            "browsing_strategy": {"topics": [], "geo": "in", "always_news": True},
            "tasks": _DISPATCH_FALLBACK_TASKS,
            "tool_results": [],
        }

    try:
        await adispatch_custom_event(
            "dispatch",
            {
                "tier": parsed.get("user_tier", tier_hint),
                "query": parsed.get("query_decomposition", ""),
            },
        )
    except RuntimeError:
        pass  # Not inside a LangGraph run (e.g. unit tests) — safe to skip

    return {
        "query_decomposition": parsed.get("query_decomposition", ""),
        "user_tier": parsed.get("user_tier", tier_hint),
        "browsing_strategy": parsed.get("browsing_strategy", {}),
        "tasks": parsed.get("tasks", []),
        "tool_results": [],
    }


# ---------------------------------------------------------------------------
# Task 5: Async Parallel Executor Node
# ---------------------------------------------------------------------------

async def _run_one_task(task: dict) -> dict:
    """Run a single tool via _execute_chat_tool. Never raises."""
    from services.api.routes.ui_data import _execute_chat_tool

    tool_name = task.get("tool", "")
    args = task.get("args", {})
    try:
        result = await _execute_chat_tool(tool_name, args)
        return {"tool": tool_name, "args": args, "result": result or ""}
    except Exception as exc:
        logger.warning("[executor] tool %s failed: %s", tool_name, exc)
        return {"tool": tool_name, "args": args, "result": "", "error": str(exc)}


async def _run_tasks_parallel(tasks: list[dict]) -> list[dict]:
    """Fire all tasks concurrently. Returns results list (same length as tasks)."""
    return list(await asyncio.gather(*[_run_one_task(t) for t in tasks]))


async def _node_executor(state: ChatState) -> dict:
    """Parallel async tool executor. Emits tool_start/tool_result SSE per task."""
    tasks = state.get("tasks") or []

    for task in tasks:
        try:
            await adispatch_custom_event("tool_start", {"tool": task["tool"], "args": task.get("args", {})})
        except RuntimeError:
            pass

    results = await _run_tasks_parallel(tasks)

    for r in results:
        summary = str(r["result"])[:600] if r["result"] else "(no result)"
        try:
            await adispatch_custom_event("tool_result", {"tool": r["tool"], "summary": summary})
        except RuntimeError:
            pass

    return {"tool_results": results}


# ---------------------------------------------------------------------------
# Task 6: Synthesize Node (Tier-Aware)
# ---------------------------------------------------------------------------

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

GROUNDING RULES (never break these):
- MARKET STATUS: Obey the session line above literally. If it says NSE has NOT opened
  (PRE-OPEN / not yet open), do NOT say "the market is trading/rising/falling today" —
  reason from the stated LAST CLOSE. If it says CLOSED/holiday, say "as of [last trading
  day], ..." never "today the market...".
- PRICES: Quote price numbers ONLY from get_live_price results, and repeat its freshness
  label — "live" vs "last close [date]". NEVER quote a price from a news article (article
  prices are stale on publish); an article's "₹210 target" is an analyst opinion, not a price.
- SOURCES: NEVER invent a source name, headline, or date. Every cited headline must appear
  verbatim in the RESEARCH RESULTS above. If it is not there, you have no source — do not cite one.
- SPECIFICITY: Use the exact numbers and events from the results — "Sensex −1,450 pts; FII
  sold ₹2,800 cr; IT −2.3%" is good. Generic lines like "markets fell on global risk aversion
  and macro concerns" are BANNED — they describe any day and signal you have no real data.
- DON'T CONNECT UNRELATED DOTS: Do not claim a headline drives a sector unless the result
  explicitly says so (e.g. a fragrance-hub launch is NOT evidence pharma will rise).
- EMPTY SEARCH: If the news results are empty or fewer than 2 useful items, say plainly:
  "I don't have grounded live results for this specific query" — do NOT backfill from training
  memory (it is stale and will fabricate sources/dates).
- RL prediction: casual → "our model says"; active → verdict + confidence; expert → full metrics.
- Historical trend: state what the data shows — never fabricate a predicted price number.
- Never say "real-time data required" or add unsolicited "I cannot predict" disclaimers —
  state what you have and its date.
- If a single tool result is empty or says "no data", ignore that one silently.
"""


async def _new_synthesize_node(state: ChatState) -> dict:
    """Tier-aware synthesize node. Streams tokens as SSE. Saves user profile."""
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
        market_context = f"Today: {datetime.now(timezone.utc).strftime('%Y-%m-%d (%A)')}"

    system_prompt = _build_synthesize_prompt(
        user_tier, query_decomposition, tool_results, market_context
    )

    lc_messages = [{"role": "system", "content": system_prompt}]
    lc_messages.extend(_to_openai_msgs(messages[-8:] if len(messages) > 8 else messages))

    final_text = ""
    buf = ""
    in_think = False
    thinking_fired = False
    _T_OPEN = "<think>"
    _T_CLOSE = "</think>"

    try:
        client = get_async_llm_client()
        stream = await client.chat.completions.create(
            model=_FAST_MODEL,
            messages=lc_messages,
            temperature=0.4,
            max_tokens=500,
            stream=True,
        )

        async for chunk in stream:
            raw = ""
            if chunk.choices and chunk.choices[0].delta:
                raw = chunk.choices[0].delta.content or ""
            if not raw:
                continue

            buf += raw
            visible = ""

            while buf:
                if in_think:
                    idx = buf.find(_T_CLOSE)
                    if idx < 0:
                        buf = ""
                        break
                    buf = buf[idx + len(_T_CLOSE):]
                    in_think = False
                else:
                    idx = buf.find(_T_OPEN)
                    if idx < 0:
                        visible += buf
                        buf = ""
                        break
                    visible += buf[:idx]
                    buf = buf[idx + len(_T_OPEN):]
                    in_think = True
                    if not thinking_fired:
                        thinking_fired = True
                        try:
                            await adispatch_custom_event("thinking", {})
                        except RuntimeError:
                            pass

            if visible:
                final_text += visible
                try:
                    await adispatch_custom_event("token", {"text": visible})
                except RuntimeError:
                    pass

    except Exception as exc:
        logger.warning("[new_synthesize] %s", exc)
        final_text = "I encountered an error composing the answer. Please try again."
        try:
            await adispatch_custom_event("token", {"text": final_text})
        except RuntimeError:
            pass

    # Save updated user profile
    if session_id:
        browsing = state.get("browsing_strategy") or {}
        topics = browsing.get("topics", [])
        try:
            save_profile(session_id, tier=user_tier, tier_confidence=0.75, topics=topics)
        except Exception as exc:
            logger.warning("[new_synthesize] failed to update profile: %s", exc)

    return {"messages": [{"role": "assistant", "content": final_text.strip()}]}


# ---------------------------------------------------------------------------
# Graph — 3-node pipeline: dispatch → executor → synthesize
# ---------------------------------------------------------------------------

_builder = StateGraph(ChatState)
_builder.add_node("dispatch",   _node_dispatch)
_builder.add_node("executor",   _node_executor)
_builder.add_node("synthesize", _new_synthesize_node)

_builder.set_entry_point("dispatch")
_builder.add_edge("dispatch",   "executor")
_builder.add_edge("executor",   "synthesize")
_builder.add_edge("synthesize", END)

_checkpointer = MemorySaver()
chat_graph = _builder.compile(checkpointer=_checkpointer)
