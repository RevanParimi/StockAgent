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
from datetime import datetime, timezone
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
  - NEWS_QUERY: ALWAYS include get_live_price(entity) as task 1 before search_market_news —
    this prevents the answer from using training-memory prices instead of live data.
  - NEWS_QUERY with no specific entity ("any big news", "what happened today", "why is market down"):
    ALWAYS plan: get_live_price(nifty) first, then get_macro_news, then search_market_news.
    get_live_price is mandatory even when no ticker is mentioned — it anchors the answer to
    real current price data and prevents the LLM from fabricating prices.
  - GENERAL with no entities: empty tasks list (answer from memory)
  - Order: free/fast internal first → DB reads → heavy (run_agent_analysis) → external last
  - Avoid redundant tasks: don't call get_stock_analysis AND run_agent_analysis for shallow
  - get_macro_news  {}  ← use for broad "what's happening", "any big news", "market sentiment today"
  - CRITICAL: Do NOT include date strings (like "2026-05-12") inside search_market_news query
    arguments — the tool handles date anchoring automatically. Write natural language queries:
    "India Nifty market decline reasons" NOT "India Nifty market decline reasons 2026-05-12"
  - CRITICAL: For questions about the Indian stock market (Nifty, Sensex, NSE stocks), the
    search_market_news query MUST include "India" and at least one of: Nifty, Sensex, NSE.
    "India Nifty fall reasons" is correct. "stock market decline reasons" will return generic
    Wikipedia content, not India-specific news. """


REVIEWER_SYSTEM_PROMPT = """\
You are a factual accuracy reviewer for a stock market assistant response.
Your job is narrow: check for specific, verifiable errors only.
Do NOT critique writing style, opinion quality, or depth of analysis.

Check ONLY these three criteria:

1. DATE INTEGRITY
   Does the answer present information as current/today when the dates say otherwise?
   Flag: a specific year in the answer (e.g. "2023", "2024") that conflicts with TODAY.
   Flag: "today" or "right now" claims about market moves when tool results are from a prior day.
   Do NOT flag: historical background facts stated with their own date ("In 2023, X happened...").

2. PRICE GROUNDING
   Does the answer cite a specific numeric price for an asset that is NOT present in the tool results?
   Flag only when get_live_price was called and the answer uses a different price for the same asset.
   Do NOT flag analyst price targets from news — those are opinions, not live prices.

3. QUESTION RELEVANCE
   Does the answer address what the user actually asked?
   Flag only if the answer is completely off-topic or refuses to engage with the question.
   Do NOT flag if the answer is partial but on-topic.

If ALL three pass, respond with:
<json>{"pass": true}</json>

If any fail, respond with:
<json>{"pass": false, "issues": ["specific issue 1", "specific issue 2"], "hint": "one sentence on what to fix"}</json>

Respond ONLY with the JSON inside <json> tags. No other text."""

# Criterion 4 — appended to the reviewer user message ONLY when macro feed has data.
# Keeping it out of the static prompt avoids wasting ~100 tokens every request
# when the background cache is cold (most of the time in current deployment).
_REVIEWER_CRITERION_4 = """
ADDITIONAL CHECK — Criterion 4: Macro News Coverage
The TRENDING MACRO ITEMS block above is non-empty. Check:
- Does any HIGH-severity item's impact_tags overlap with what the user asked?
- If yes AND the answer ignores it AND it would materially change the answer → flag it.
- Do NOT flag: MEDIUM/LOW items, no-overlap items, items the answer already mentions."""


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ChatState(TypedDict):
    messages:          Annotated[list, add]   # plain OpenAI-format dicts
    intent:            dict | None
    todo_list:         list[dict] | None      # [{id, tool, args, external, status, result}]
    needs_external:    bool | None
    review_count:      int | None             # how many reviewer cycles have run (None = 0)
    reviewer_feedback: str | None             # critique from last reviewer pass; None = passed / not yet run


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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")
    classify_msgs = [{"role": "system", "content": f"Today's date: {today}\n\n{CLASSIFY_SYSTEM_PROMPT}"}]
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

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")
    planner_msgs = [{"role": "system", "content": f"Today's date: {today}\n\n{PLANNER_SYSTEM_PROMPT}"}]
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
            # Always fetch live price first — prevents synthesize from fabricating it
            price_sym = tickers[0] if tickers else "nifty"
            todo_list.append(_task("get_live_price", {"symbol": price_sym}))
            year = datetime.now(timezone.utc).year
            todo_list.append(_task("search_market_news", {"query": f"{entity} latest news {year}"}))
        elif intent_type == "NEWS_QUERY" and not (tickers or sectors):
            # Broad "why is market down", "any big news" — live price anchor is mandatory
            # to prevent LLM from fabricating Nifty/Sensex values from training memory
            needs_external = True
            todo_list.append(_task("get_live_price", {"symbol": "nifty"}))
            todo_list.append(_task("get_macro_news", {}))
            todo_list.append(_task("search_market_news", {"query": "India Nifty market news"}))
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

    # Show more for search tools so the UI displays actual headlines, not truncated text
    limit   = 600 if tool_name in ("search_market_news", "get_macro_news") else 120
    summary = result[:limit].replace("\n", " ")
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

    # Build system prompt — pass intent_type so macro news is only injected for broad intents
    user_text   = _last_user_text(state)
    intent_type = intent.get("intent_type", "GENERAL") if intent else "GENERAL"
    context     = _build_chat_context(user_text, intent_type=intent_type)
    system      = _CHAT_SYSTEM_PROMPT.format(context=context)

    if intent:
        system += (
            f"\n\nCLASSIFIED INTENT: {intent.get('intent_type', 'GENERAL')}"
            f"\nFOCUS: {intent.get('focus', '')}"
            f"\nKEY ENTITIES: {intent.get('entities', {})}"
        )
    if results_context:
        system += f"\n\nRESEARCH RESULTS (use these as your primary data source):\n{results_context}"
    else:
        system += (
            "\n\nNO TOOL RESULTS: No search or data tools returned results for this query. "
            "You MUST say so explicitly. Do NOT answer from training knowledge for any "
            "news, events, or recent market moves — state that live search returned nothing."
        )

    # Inject reviewer critique when this is a re-synthesis pass
    feedback = state.get("reviewer_feedback")
    review_count = state.get("review_count") or 0
    if feedback:
        from backend.shared.config import settings as _cfg
        max_cycles = getattr(_cfg, "CHAT_MAX_REVIEW_CYCLES", 3)
        system += (
            f"\n\nREVIEWER FEEDBACK (revision {review_count} of {max_cycles}):\n"
            f"Your previous answer had specific factual issues. Fix ONLY these — do not change "
            f"anything else:\n{feedback}"
        )

    messages = [{"role": "system", "content": system}] + _to_openai_msgs(state["messages"])

    final_text = ""
    try:
        stream = await client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=600,
            stream=True,
        )

        # Stream tokens, filtering Qwen3 <think>...</think> blocks so they
        # never appear in the chat bubble.
        # Emit a one-time "thinking" event when the model enters a think block —
        # this tells the frontend the model is reasoning, not hanging.
        buf            = ""
        in_think       = False
        thinking_fired = False   # emit "thinking" event only once per response
        _T_OPEN        = "<think>"
        _T_CLOSE       = "</think>"

        async for chunk in stream:
            raw = ""
            if chunk.choices and chunk.choices[0].delta:
                raw = chunk.choices[0].delta.content or ""
            if not raw:
                continue

            buf += raw
            visible = ""

            # Flush buf, skipping anything inside <think>…</think>
            while buf:
                if in_think:
                    idx = buf.find(_T_CLOSE)
                    if idx < 0:
                        buf = ""      # still waiting for closing tag
                        break
                    buf      = buf[idx + len(_T_CLOSE):]
                    in_think = False
                else:
                    idx = buf.find(_T_OPEN)
                    if idx < 0:
                        visible += buf
                        buf = ""
                        break
                    visible += buf[:idx]
                    buf      = buf[idx + len(_T_OPEN):]
                    in_think = True
                    # Notify frontend the model entered a think block (fires once per response)
                    if not thinking_fired:
                        thinking_fired = True
                        await adispatch_custom_event("thinking", {})

            if visible:
                final_text += visible
                await adispatch_custom_event("token", {"text": visible})

    except Exception as exc:
        logger.warning("[synthesize] %s", exc)
        final_text = "I encountered an error composing the answer. Please try again."
        await adispatch_custom_event("token", {"text": final_text})

    return {
        "messages": [{"role": "assistant", "content": final_text.strip()}],
        "reviewer_feedback": None,   # reset before reviewer runs
    }


async def _reviewer_node(state: ChatState) -> dict:
    """
    Cheap factual accuracy check on the latest synthesized answer.

    Checks three concrete, verifiable criteria only:
      1. Date integrity — year/date claims in answer vs TODAY's actual date
      2. Price grounding — specific prices in answer vs what get_live_price returned
      3. Question relevance — does the answer address what was asked at all

    Returns reviewer_feedback=None (pass) or a critique string (fail).
    Does NOT run when no tools executed (GENERAL intent — nothing to ground-check).
    """
    from services.clients.llm_client import get_async_llm_client
    from backend.shared.config import settings as _cfg

    max_cycles = getattr(_cfg, "CHAT_MAX_REVIEW_CYCLES", 3)

    # --- Skip conditions ---
    # 1. Feature disabled
    if max_cycles == 0:
        return {"reviewer_feedback": None}

    # 2. Already at the review limit — accept current answer
    count = state.get("review_count") or 0
    if count >= max_cycles:
        logger.info("[reviewer] Limit reached (%d/%d) — accepting answer", count, max_cycles)
        return {"reviewer_feedback": None}

    # 3. No tool results — pure conversational answer, nothing to ground-check
    done_tasks = [t for t in (state.get("todo_list") or []) if t.get("status") == "done"]
    if not done_tasks:
        return {"reviewer_feedback": None}

    # --- Build reviewer input ---
    last_assistant = next(
        (m for m in reversed(state["messages"]) if _get_role(m) == "assistant"), None
    )
    if not last_assistant:
        return {"reviewer_feedback": None}

    answer_text = (
        last_assistant["content"] if isinstance(last_assistant, dict)
        else getattr(last_assistant, "content", "")
    )

    tool_results_text = "\n\n".join(
        f"[{t['tool']}]: {str(t.get('result', ''))[:400]}"
        for t in done_tasks
    )
    user_text = _last_user_text(state)
    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")
    entities  = json.dumps((state.get("intent") or {}).get("entities", {}))

    # Load HIGH macro items for criterion 4 — empty string if cache not populated yet
    macro_items_text = ""
    try:
        from services.background.macro_news_cache import MacroNewsCache
        from backend.shared.config import settings as _cfg
        max_rev = getattr(_cfg, "MACRO_NEWS_REVIEWER_MAX_ITEMS", 5)
        macro_items_text = MacroNewsCache().get_for_reviewer(max_items=max_rev)
    except Exception:
        pass

    # Append criterion 4 only when macro feed has actual data (avoids dead context tokens)
    macro_block = ""
    if macro_items_text:
        macro_block = (
            f"\nTRENDING MACRO ITEMS (HIGH severity, last 24h):\n{macro_items_text}"
            + _REVIEWER_CRITERION_4
        )

    user_msg = (
        f"TODAY: {today}\n\n"
        f"USER QUESTION: {user_text}\n"
        f"USER ENTITIES: {entities}\n\n"
        f"TOOL RESULTS:\n{tool_results_text}"
        f"{macro_block}\n\n"
        f"ANSWER TO REVIEW:\n{answer_text}"
    )

    try:
        client = get_async_llm_client()
        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content or ""
        review_data = _extract_json(raw)
    except Exception as exc:
        logger.warning("[reviewer] LLM call failed: %s — skipping review", exc)
        return {"reviewer_feedback": None}

    if not review_data or review_data.get("pass", True):
        logger.info("[reviewer] Cycle %d — PASS", count + 1)
        await adispatch_custom_event("review", {"cycle": count + 1, "pass": True})
        return {"reviewer_feedback": None}

    issues = review_data.get("issues", [])
    hint   = review_data.get("hint", "")
    feedback = "\n".join(f"- {i}" for i in issues)
    if hint:
        feedback += f"\nHow to fix: {hint}"

    logger.info("[reviewer] Cycle %d — FAIL: %s", count + 1, issues)
    await adispatch_custom_event("review", {"cycle": count + 1, "pass": False, "issues": issues})

    return {
        "reviewer_feedback": feedback,
        "review_count": count + 1,
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_after_executor(state: ChatState) -> str:
    """Loop back to executor while any task is still pending, then synthesize."""
    for t in (state.get("todo_list") or []):
        if t.get("status") == "pending":
            return "executor"
    return "synthesize"


def _route_after_reviewer(state: ChatState) -> str:
    """
    Pass  → END (reviewer_feedback is None)
    Fail  → synthesize (re-run with critique injected)
    Limit → END (review_count >= MAX, accept answer as-is)
    """
    from backend.shared.config import settings as _cfg
    max_cycles = getattr(_cfg, "CHAT_MAX_REVIEW_CYCLES", 3)

    feedback = state.get("reviewer_feedback")
    count    = state.get("review_count") or 0

    if feedback is None or count >= max_cycles:
        return END
    return "synthesize"


# ---------------------------------------------------------------------------
# Graph — module-level singleton (one MemorySaver per server process)
# ---------------------------------------------------------------------------

_builder = StateGraph(ChatState)
_builder.add_node("classify",   _classify_node)
_builder.add_node("planner",    _planner_node)
_builder.add_node("executor",   _executor_node)
_builder.add_node("synthesize", _synthesize_node)
_builder.add_node("reviewer",   _reviewer_node)

_builder.set_entry_point("classify")
_builder.add_edge("classify",  "planner")
_builder.add_edge("planner",   "executor")
_builder.add_conditional_edges(
    "executor",
    _route_after_executor,
    {"executor": "executor", "synthesize": "synthesize"},
)
_builder.add_edge("synthesize", "reviewer")
_builder.add_conditional_edges(
    "reviewer",
    _route_after_reviewer,
    {"synthesize": "synthesize", END: END},
)

_checkpointer = MemorySaver()
chat_graph = _builder.compile(checkpointer=_checkpointer)
