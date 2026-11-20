"""The owner's second judge (PR-017, owner 15 Nov 2026).

For each new deep dive, one extra call to a bare model: the same dated
evidence the dive's analysis read, and none of the product's method. It
answers BUY or SKIP with a conviction. The auditor grades it like the dive
(`core/audit/idea_lanes.py`, lane `bare`), so the report can answer: does the
product's method beat a plain model asked the same question?

- **The evidence** is the dive's own data bundle (`services/data/context/
  bundle_builder.py`), every section the analysis read except `dossier`, the
  product's memory of the stock, in the same order and under the same length
  cap. The dive's day, the stock's code, its Yahoo sector and industry and the
  close the dive read go with it.
- **None of the method**: no scoring rubric, dimensions, sector prompt,
  weights, lessons or dossier; one short instruction (`SYSTEM`).
- **The same model** as the analysis (`settings.LLM_MODEL_REASONING`), so the
  comparison is of the method, not of two models.
- **Which dives**: new ideas only (a re-dive of a shelf idea is not asked),
  in the order they were dived, at most `discovery.bare_judge_max_per_week`
  calls (20) in any 7 days, a failed call included. Nothing is backfilled: a
  model asked today could read about the weeks since.
- **The record**: `{DISCOVERY_DATA_DIR}/bare_judgements.jsonl`, append-only,
  one row per call: reference `bare:<dive date>|<symbol>`, the decision, the
  conviction, a one-line reason, the model. A call whose answer is not BUY or
  SKIP is kept with decision "" and is not graded.

Example: ABC dived on 21 Nov at 0.71 BUY. The bare model reads ABC's news,
fundamentals, technicals and peers as of 21 Nov and answers SKIP 0.40. At 30
sessions both are graded from the open of 23 Nov.

Never raises: a failed call costs its answer, never the discovery run.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from backend.shared.config.settings.loader import cfg
from core.config import settings

logger = logging.getLogger(__name__)

DECISIONS = ("BUY", "SKIP")
LEFT_OUT = ("dossier",)          # the product's memory, not evidence
WEEK_DAYS = 7

SYSTEM = (
    "You are an equity analyst. You are given dated evidence about one company "
    "listed on India's National Stock Exchange, as of the date shown. Decide one "
    "thing: should an investor buy this stock now, to beat the Nifty 50 index over "
    "the next three months (BUY), or not (SKIP)? Use only the evidence given. "
    'Answer in JSON: {"decision": "BUY" or "SKIP", "conviction": a number from 0 '
    'to 1, how sure you are that the stock beats the Nifty 50, "reason": one sentence}.'
)

USER = (
    "Company: {symbol} (NSE). Sector: {market_sector}. Industry: {industry}.\n"
    "Date: {dive_date}. Last close: Rs {close}.\n\n"
    "Evidence:\n{evidence}"
)


def bare_ref(dive_date: str, symbol: str) -> str:
    return f"bare:{dive_date}|{symbol}"


def enabled() -> bool:
    return bool(cfg("discovery.bare_judge_enabled", fallback=True))


def max_per_week() -> int:
    try:
        return max(0, int(cfg("discovery.bare_judge_max_per_week", fallback=20)))
    except (TypeError, ValueError):
        return 20


def evidence_text(bundle) -> str:
    """The bundle's sections as the analysis saw them, less `LEFT_OUT`, under
    the analysis's own cap. "" when there is no bundle."""
    if bundle is None:
        return ""
    from services.data.context.bundle_builder import SECTION_ORDER, UNAVAILABLE
    sections = getattr(bundle, "sections", None)
    if not isinstance(sections, dict) or not sections:
        return ""
    parts = [f"## {name.upper()}\n{sections.get(name, UNAVAILABLE)}"
             for name in SECTION_ORDER if name not in LEFT_OUT]
    return "\n\n".join(parts)[: int(settings.UNIFIED_BUNDLE_MAX_CHARS)]


def _path(base_dir: str | None) -> Path:
    return Path(base_dir or settings.DISCOVERY_DATA_DIR) / "bare_judgements.jsonl"


def load(base_dir: str | None = None) -> list[dict]:
    path = _path(base_dir)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("ref"):
            out.append(row)
    return out


def _calls_since(rows: Iterable[dict], since: date) -> int:
    n = 0
    for r in rows:
        try:
            if date.fromisoformat(str(r.get("dive_date"))) > since:
                n += 1
        except ValueError:
            continue
    return n


def _strip_think(raw: str) -> str:
    return re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()


def _call(system: str, user: str) -> tuple[str, str]:
    """One JSON-mode call to the analysis's model, recorded in the LLM log."""
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call
    model = settings.LLM_MODEL_REASONING
    t0 = time.time()
    try:
        resp = get_llm_client().chat.completions.create(
            model=model, temperature=0.2, max_tokens=300,
            response_format={"type": "json_object"}, extra_body=JSON_MODE_EXTRA_BODY,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
    except Exception:
        record_llm_call("bare_judge", model, 0, 0, int((time.time() - t0) * 1000), False)
        raise
    usage = getattr(resp, "usage", None)
    record_llm_call("bare_judge", model, getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                    int((time.time() - t0) * 1000), True)
    return resp.choices[0].message.content or "", model


def read_answer(raw: str) -> tuple[str, float | None, str]:
    """(decision, conviction, reason) from the model's text; decision "" and
    conviction None when it is not a BUY or SKIP with a number in [0, 1]."""
    try:
        data = json.loads(_strip_think(raw))
    except ValueError:
        return "", None, ""
    if not isinstance(data, dict):
        return "", None, ""
    decision = str(data.get("decision", "")).strip().upper()
    try:
        conviction = float(data.get("conviction"))
    except (TypeError, ValueError):
        conviction = None
    if decision not in DECISIONS or conviction is None or not 0.0 <= conviction <= 1.0:
        return "", None, str(data.get("reason", ""))[:200]
    return decision, round(conviction, 4), str(data.get("reason", ""))[:200]


def judge(dives: Iterable, evidence: dict[str, object], *, on: date,
          redives: Iterable[str] = (), base_dir: str | None = None,
          call: Callable[[str, str], tuple[str, str]] | None = None) -> dict:
    """Ask the bare model about each new dive that has its evidence, within
    the weekly cap; append one row per call. Returns {asked, answered,
    skipped_cap, no_evidence}. Never raises."""
    summary = {"asked": 0, "answered": 0, "skipped_cap": 0, "no_evidence": 0}
    if not enabled():
        summary["disabled"] = True
        return summary
    call = call or _call
    try:
        done = load(base_dir)
    except OSError as exc:
        logger.warning("[bare_judge] record unreadable, no call made: %s", exc)
        return summary
    seen = {r["ref"] for r in done}
    room = max_per_week() - _calls_since(done, on - timedelta(days=WEEK_DAYS))
    skip = set(redives)
    path = _path(base_dir)
    for d in dives:
        if d.symbol in skip:
            continue
        ref = bare_ref(d.dive_date, d.symbol)
        if ref in seen:
            continue
        text = evidence_text(evidence.get(d.symbol))
        if not text:
            summary["no_evidence"] += 1
            continue
        if room <= 0:
            summary["skipped_cap"] += 1
            continue
        room -= 1
        summary["asked"] += 1
        user = USER.format(symbol=d.symbol, market_sector=d.market_sector or "unknown",
                           industry=d.industry or "unknown", dive_date=d.dive_date,
                           close=f"{float(d.close):.2f}", evidence=text)
        try:
            raw, model = call(SYSTEM, user)
            decision, conviction, reason = read_answer(raw)
        except Exception as exc:
            logger.warning("[bare_judge] %s call failed (non-fatal): %s", d.symbol, exc)
            raw, model, decision, conviction, reason = "", settings.LLM_MODEL_REASONING, "", None, ""
            reason = f"call failed: {type(exc).__name__}"
        if decision:
            summary["answered"] += 1
        row = {"ref": ref, "symbol": d.symbol, "dive_date": d.dive_date,
               "decision": decision, "conviction": conviction, "reason": reason,
               "model": model, "evidence_chars": len(text),
               "at": datetime.now(timezone.utc).isoformat()}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
            seen.add(ref)
        except OSError as exc:
            logger.warning("[bare_judge] write failed (non-fatal): %s", exc)
    return summary
