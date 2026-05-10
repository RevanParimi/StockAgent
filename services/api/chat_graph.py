"""
LangGraph chat pipeline for StockAgent.

Graph: classify → planner → executor (loop) → synthesize → END

State:
  messages:       Annotated[list, operator.add]  — plain OpenAI-format dicts
  intent:         dict | None   — from classify, consumed by planner + synthesize
  todo_list:      list[dict] | None — research plan from planner; executor marks tasks done
  needs_external: bool | None  — from planner; gates Tavily/Serper in executor

Carry-over: MemorySaver keyed by thread_id (= session_id).
  state.messages accumulates across HTTP requests — no client-side history.

SSE events dispatched via adispatch_custom_event:
  "intent"      — classify done
  "plan"        — planner done (task list, depth, needs_external)
  "tool_start"  — executor about to run a task
  "tool_result" — executor finished a task
  "token"       — synthesize streaming chunks
"""
from __future__ import annotations

import json
import logging
import re
from operator import add
from typing import Annotated

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)

_MODEL = "qwen/qwen3-235b-a22b"

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
# Prompts
# ---------------------------------------------------------------------------

CLASSIFY_SYSTEM_PROMPT = """\
You are an intent classifier for a stock market assistant.
Respond with ONLY a JSON object inside <json> tags, no other text:

<json>
{"intent_type": "<type>", "entities": {"tickers": [], "sectors": [], "assets": []}, "focus": "<one sentence>"}
</json>

Intent types (pick exactly one):
- SINGLE_STOCK: asking about one specific NSE stock
- STOCK_COMPARE: comparing multiple stocks
- SECTOR_OVERVIEW: one sector (auto/IT/banking/energy/pharma/FMCG)
- MULTI_SECTOR: multiple sectors or cross-sector comparison
- PRICE_QUERY: current price of any asset (stock, commodity, crypto, index)
- NEWS_QUERY: why something moved, recent events, news, reasons
- AGENT_QUERY: about a specific analysis agent (Sales & Demand, Fundamentals, etc.)
- RL_QUERY: agent accuracy, which agent to trust, prediction quality
- GENERAL: anything else

Extract entities from the FULL conversation — if user says "what about risks?"
but prior messages mentioned MARUTI, include MARUTI in tickers.
Known sectors (use canonical key): automobile, banking_bfsi, it_sector, renewable_energy,
pharma, fmcg, metals, oilgas, capgoods, infra, chemicals, defence, insurance,
logistics, realestate, retail, agrochem, hospitality, tech, telecom"""


PLANNER_SYSTEM_PROMPT = """\
You are a research planner for a stock market AI assistant.
Respond with ONLY a JSON object inside <json> tags, no other text:

<json>
{"depth": "shallow", "needs_external": false, "tasks": [{"id": 1, "tool": "<tool_name>", "args": {}, "external": false}]}
</json>

depth — exactly one word:
  "shallow" → user wants a quick answer (price, single fact, brief overview). 1-3 tasks max.
  "deep"    → user wants thorough research, full analysis, or the conversation has drilled
              down across multiple turns. Use all relevant internal tools.

needs_external — true ONLY when live web news is genuinely required and cannot be answered
  by internal data: "why did it fall today", "latest news", "what happened this week".
  Default false.

Available tools (use ONLY these, in this priority order):
  INTERNAL — always prefer:
    get_live_price        {"symbol": "MARUTI or silver or crude etc"}
    get_sector_snapshot   {"sector": "<sector_key>"}
                          Valid keys: automobile, banking_bfsi, it_sector, renewable_energy,
                          pharma, fmcg, metals, oilgas, capgoods, infra, chemicals,
                          defence, insurance, realestate, retail, logistics, telecom,
                          agrochem, hospitality, tech
    get_stock_analysis    {"ticker": "MARUTI"}
    get_analysis_history  {"days": 14}
    get_rl_insights       {}
    run_agent_analysis    {"ticker": "MARUTI"}   ← DEEP ONLY; works for ALL sectors
                          Disabled sectors degrade safely to automobile analysis.

  EXTERNAL — include ONLY if needs_external=true:
    search_market_news    {"query": "specific query with year e.g. MARUTI Q4 results 2026"}

Rules:
  - Mark external tasks with "external": true
  - run_agent_analysis only for depth=deep and when a specific ticker is in scope
  - PRICE_QUERY: just get_live_price (1 task)
  - GENERAL with no entities: empty tasks list (answer from memory)
  - Order: free/fast internal first → DB reads → heavy (run_agent_analysis) → external last
  - Avoid redundant tasks: don't call get_stock_analysis AND run_agent_analysis for shallow"""


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ChatState(TypedDict):
    messages:       Annotated[list, add]   # plain OpenAI-format dicts
    intent:         dict | None
    todo_list:      list[dict] | None      # [{id, tool, args, external, status, result}]
    needs_external: bool | None


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
# Nodes
# ---------------------------------------------------------------------------

async def _classify_node(state: ChatState) -> dict:
    from services.clients.llm_client import get_async_llm_client

    client = get_async_llm_client()
    classify_msgs = [{"role": "system", "content": CLASSIFY_SYSTEM_PROMPT}]
    classify_msgs.extend(_to_openai_msgs(state["messages"][-6:]))

    try:
        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=classify_msgs,
            max_tokens=120,
            temperature=0.0,
        )
        intent_data = _extract_json(resp.choices[0].message.content or "")
        if not intent_data:
            raise ValueError("classify returned no JSON object")
    except Exception as exc:
        logger.warning("[classify] %s", exc)
        intent_data = {
            "intent_type": "GENERAL",
            "entities": {"tickers": [], "sectors": [], "assets": []},
            "focus": "General inquiry",
        }

    await adispatch_custom_event("intent", intent_data)
    return {"intent": intent_data}


async def _planner_node(state: ChatState) -> dict:
    from services.clients.llm_client import get_async_llm_client

    client = get_async_llm_client()
    intent = state.get("intent") or {}

    planner_msgs = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}]
    planner_msgs.extend(_to_openai_msgs(state["messages"][-8:]))
    planner_msgs.append({
        "role": "system",
        "content": f"Current classified intent: {json.dumps(intent)}",
    })

    try:
        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=planner_msgs,
            max_tokens=250,
            temperature=0.0,
        )
        plan = _extract_json(resp.choices[0].message.content or "")
        if not plan:
            raise ValueError("planner returned no JSON object")
    except Exception as exc:
        logger.warning("[planner] %s", exc)
        plan = {"depth": "shallow", "needs_external": False, "tasks": []}

    todo_list = [
        {
            "id":       t.get("id", i + 1),
            "tool":     t.get("tool", ""),
            "args":     t.get("args", {}),
            "external": bool(t.get("external", False)),
            "status":   "pending",
            "result":   None,
        }
        for i, t in enumerate(plan.get("tasks", []))
        if isinstance(t, dict) and t.get("tool")
    ]
    needs_external = bool(plan.get("needs_external", False))

    # Safety fallback: if planner returned 0 tasks, derive minimal tasks from intent
    if not todo_list:
        intent_type = intent.get("intent_type", "GENERAL")
        entities   = intent.get("entities", {})
        tickers    = entities.get("tickers", [])
        sectors    = entities.get("sectors", [])

        def _task(tool, args):
            return {"id": len(todo_list) + 1, "tool": tool, "args": args,
                    "external": False, "status": "pending", "result": None}

        if intent_type == "PRICE_QUERY" and tickers:
            todo_list += [_task("get_live_price", {"symbol": t}) for t in tickers[:2]]
        elif intent_type == "SECTOR_OVERVIEW" and sectors:
            todo_list += [_task("get_sector_snapshot", {"sector": s}) for s in sectors[:2]]
        elif intent_type in ("SINGLE_STOCK", "STOCK_COMPARE") and tickers:
            todo_list += [_task("get_stock_analysis", {"ticker": t}) for t in tickers[:2]]
        elif intent_type == "NEWS_QUERY" and (tickers or sectors):
            entity = tickers[0] if tickers else sectors[0]
            needs_external = True
            todo_list.append(_task("search_market_news", {"query": f"{entity} latest news 2026"}))
        elif intent_type == "RL_QUERY":
            todo_list.append(_task("get_rl_insights", {}))

    await adispatch_custom_event("plan", {
        "depth": plan.get("depth", "shallow"),
        "needs_external": needs_external,
        "tasks": [{"tool": t["tool"], "args": t["args"]} for t in todo_list],
    })

    return {"todo_list": todo_list, "needs_external": needs_external}


async def _executor_node(state: ChatState) -> dict:
    from services.api.routes.ui_data import _execute_chat_tool

    todo_list = [dict(t) for t in (state.get("todo_list") or [])]
    needs_external = bool(state.get("needs_external"))

    # Find first pending task
    next_idx = next(
        (i for i, t in enumerate(todo_list) if t.get("status") == "pending"), None
    )
    if next_idx is None:
        return {}

    task = todo_list[next_idx]

    # Gate external tools strictly
    if task["external"] and not needs_external:
        task["status"] = "skipped"
        todo_list[next_idx] = task
        return {"todo_list": todo_list}

    tool_name = task["tool"]
    args = task["args"]

    await adispatch_custom_event("tool_start", {"tool": tool_name, "args": args})

    try:
        result = await _execute_chat_tool(tool_name, args)
    except Exception as exc:
        result = f"{tool_name} failed: {exc}"

    summary = result[:120].replace("\n", " ")
    await adispatch_custom_event("tool_result", {"tool": tool_name, "summary": summary})

    task["status"] = "done"
    task["result"] = result
    todo_list[next_idx] = task

    return {"todo_list": todo_list}


async def _synthesize_node(state: ChatState) -> dict:
    from services.api.routes.ui_data import _CHAT_SYSTEM_PROMPT, _build_chat_context
    from services.clients.llm_client import get_async_llm_client

    client = get_async_llm_client()
    intent = state.get("intent") or {}

    # Aggregate research results from completed tasks
    results_parts = [
        f"[{t['tool']}]:\n{t['result']}"
        for t in (state.get("todo_list") or [])
        if t.get("status") == "done" and t.get("result")
    ]
    results_context = "\n\n".join(results_parts)

    # Build system prompt
    user_text = _last_user_text(state)
    context = _build_chat_context(user_text)
    system = _CHAT_SYSTEM_PROMPT.format(context=context)

    if intent:
        system += (
            f"\n\nCLASSIFIED INTENT: {intent.get('intent_type', 'GENERAL')}"
            f"\nFOCUS: {intent.get('focus', '')}"
            f"\nKEY ENTITIES: {intent.get('entities', {})}"
        )
    if results_context:
        system += f"\n\nRESEARCH RESULTS (use these as your primary data source):\n{results_context}"

    messages = [{"role": "system", "content": system}] + _to_openai_msgs(state["messages"])

    try:
        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=600,
        )
        final_text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("[synthesize] %s", exc)
        final_text = "I encountered an error composing the answer. Please try again."

    # Fake-stream: emit in 4-word chunks
    words = final_text.split()
    for i in range(0, len(words), 4):
        chunk = " ".join(words[i : i + 4])
        if i + 4 < len(words):
            chunk += " "
        await adispatch_custom_event("token", {"text": chunk})

    return {"messages": [{"role": "assistant", "content": final_text}]}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_after_executor(state: ChatState) -> str:
    """Loop back to executor while any task is still pending, then synthesize."""
    for t in (state.get("todo_list") or []):
        if t.get("status") == "pending":
            return "executor"
    return "synthesize"


# ---------------------------------------------------------------------------
# Graph — module-level singleton (one MemorySaver per server process)
# ---------------------------------------------------------------------------

_builder = StateGraph(ChatState)
_builder.add_node("classify",   _classify_node)
_builder.add_node("planner",    _planner_node)
_builder.add_node("executor",   _executor_node)
_builder.add_node("synthesize", _synthesize_node)

_builder.set_entry_point("classify")
_builder.add_edge("classify",  "planner")
_builder.add_edge("planner",   "executor")
_builder.add_conditional_edges(
    "executor",
    _route_after_executor,
    {"executor": "executor", "synthesize": "synthesize"},
)
_builder.add_edge("synthesize", END)

_checkpointer = MemorySaver()
chat_graph = _builder.compile(checkpointer=_checkpointer)
