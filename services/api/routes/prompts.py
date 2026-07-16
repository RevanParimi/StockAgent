"""
services/api/routes/prompts.py
==============================
Prompt Management API — read, edit, and deploy agent prompt files.

Endpoints
---------
GET  /ui/prompts/catalogue              — list all sectors + agent names
GET  /ui/prompts/status                 — pending count, next scheduled deploy, last deploy result
GET  /ui/prompts/pending                — list files modified since last deploy
GET  /ui/prompts/{sector}/{agent}       — read SYSTEM_PROMPT, ANALYSIS_PROMPT, CONTEXT_SEARCH_QUERIES
PUT  /ui/prompts/{sector}/{agent}       — write to disk + patch live module in memory (instant effect)
POST /ui/prompts/deploy                 — manual override: deploy now instead of waiting for midnight

Deploy flow
-----------
Saving (PUT) writes the .py file to disk AND patches the live module object so the
very next analysis call uses the new prompt without any restart.

The daily scheduler job (midnight IST) batches ALL pending files into one GitHub
push, triggering a Railway rebuild that persists the changes across restarts.

POST /ui/prompts/deploy is an emergency override — use it when a change must be
in Git immediately rather than waiting for the scheduled deploy.

Env vars required for deploy:
  GITHUB_TOKEN  — PAT with repo write scope
  GITHUB_REPO   — e.g. "username/StockAgent-main"  (owner/repo)
  GITHUB_BRANCH — default "main"
"""

from __future__ import annotations

import base64
import importlib
import importlib.util
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from services.api.auth import check_scheduler_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ui/prompts", tags=["Prompts"])

# ---------------------------------------------------------------------------
# Catalogue — all known sector → agent mappings
# ---------------------------------------------------------------------------

_CATALOGUE: dict[str, dict[str, Any]] = {
    "automobile": {
        "display": "Automobile",
        "agents": {
            "fundamentals":       "Fundamentals",
            "sales_demand":       "Sales & Demand",
            "pattern_analysis":   "Pattern Analysis",
            "raw_materials":      "Raw Materials",
            "sentiment":          "Sentiment",
            "policy_regulatory":  "Policy & Regulatory",
            "competitive_intel":  "Competitive Intel",
            "risk_macro":         "Risk & Macro",
            "valuation_catalyst": "Valuation & Catalyst",
        },
    },
    "banking_bfsi": {
        "display": "Banking BFSI",
        "agents": {
            "fundamentals":    "Fundamentals",
            "institutional":   "Institutional",
            "macro_policy":    "Macro Policy",
            "pattern_analysis":"Pattern Analysis",
            "risk":            "Risk",
            "universe_setup":  "Universe Setup",
        },
    },
    "it_sector": {
        "display": "IT Sector",
        "agents": {
            "fundamentals":        "Fundamentals",
            "transcript_nlp":      "Transcript NLP",
            "insider_smart_money": "Insider / Smart Money",
            "sentiment":           "Sentiment",
            "global_macro":        "Global Macro",
            "pattern_analysis":    "Pattern Analysis",
            "peer_benchmark":      "Peer Benchmark",
            "risk_macro":          "Risk & Macro",
        },
    },
    "renewable_energy": {
        "display": "Renewable Energy",
        "agents": {
            "fundamentals":      "Fundamentals",
            "business":          "Business",
            "valuation":         "Valuation",
            "sentiment_policy":  "Sentiment & Policy",
            "technical":         "Technical",
            "risk":              "Risk",
        },
    },
}

# Where we persist the list of files edited since the last deploy
_PENDING_PATH       = Path("data/prompt_changes.json")
# Where we persist the result of the last deploy run (scheduled or manual)
_DEPLOY_STATUS_PATH = Path("data/prompt_deploy_status.json")


# ---------------------------------------------------------------------------
# Helpers — file resolution
# ---------------------------------------------------------------------------

def _locate_prompt_file(sector: str, agent: str) -> Path:
    """
    Find the prompt .py file on disk using importlib (works in both dev and Docker).
    Docker: backend/ is at /app/backend/ (COPY src/backend/ ./backend/)
    Dev: backend/ is at src/backend/ but importlib resolves it via sys.path.
    """
    module_name = f"backend.sectors.{sector}.prompts.{agent}"
    spec = importlib.util.find_spec(module_name)
    if spec and spec.origin:
        return Path(spec.origin)
    raise FileNotFoundError(
        f"Prompt module '{module_name}' not found. "
        "Check that the sector and agent names are correct."
    )


def _load_prompt_content(sector: str, agent: str) -> dict:
    """
    Import the prompt module fresh and extract SYSTEM_PROMPT, ANALYSIS_PROMPT,
    CONTEXT_SEARCH_QUERIES.  Deletes from sys.modules first so a prior PUT
    is always reflected immediately.
    """
    module_name = f"backend.sectors.{sector}.prompts.{agent}"
    sys.modules.pop(module_name, None)
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:
        raise RuntimeError(f"Failed to import {module_name}: {exc}") from exc

    return {
        "system_prompt":            getattr(mod, "SYSTEM_PROMPT",            ""),
        "analysis_prompt":          getattr(mod, "ANALYSIS_PROMPT",          ""),
        "context_search_queries":   getattr(mod, "CONTEXT_SEARCH_QUERIES",   []),
    }


def _extract_docstring(file_path: Path) -> str:
    """Pull the module-level docstring from the existing file (first triple-quoted block)."""
    try:
        text = file_path.read_text(encoding="utf-8")
        for q in ('"""', "'''"):
            if text.lstrip().startswith(q):
                end = text.find(q, len(q))
                if end != -1:
                    return text[: end + len(q)]
    except Exception:
        pass
    return ""


def _safe_triple_quote(s: str) -> str:
    """Wrap s in triple double-quotes, escaping any embedded triple-double-quotes."""
    escaped = s.replace('"""', r'\"\"\"')
    return f'"""{escaped}"""'


def _write_prompt_file(
    file_path: Path,
    docstring: str,
    system_prompt: str,
    analysis_prompt: str,
    queries: list[str],
) -> None:
    """Reconstruct and write a prompt .py file from its three logical sections."""
    parts: list[str] = []
    if docstring:
        parts.append(docstring)
    parts.append("")
    parts.append(f"SYSTEM_PROMPT = {_safe_triple_quote(system_prompt)}")
    parts.append("")
    parts.append(f"ANALYSIS_PROMPT = {_safe_triple_quote(analysis_prompt)}")
    parts.append("")
    query_lines = ["CONTEXT_SEARCH_QUERIES = ["]
    for q in queries:
        query_lines.append(f"    {repr(q)},")
    query_lines.append("]")
    parts.append("\n".join(query_lines))
    parts.append("")   # trailing newline
    file_path.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers — pending-change tracking
# ---------------------------------------------------------------------------

def _load_pending() -> list[str]:
    try:
        if _PENDING_PATH.exists():
            return json.loads(_PENDING_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _add_pending(github_path: str) -> None:
    pending = _load_pending()
    if github_path not in pending:
        pending.append(github_path)
    _PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PENDING_PATH.write_text(json.dumps(pending, indent=2), encoding="utf-8")


def _clear_pending() -> None:
    _PENDING_PATH.write_text("[]", encoding="utf-8")


def _github_path_for(sector: str, agent: str) -> str:
    """Return the repo-relative path as it exists on GitHub (always src/backend/...)."""
    return f"src/backend/sectors/{sector}/prompts/{agent}.py"


# ---------------------------------------------------------------------------
# Deploy status persistence
# ---------------------------------------------------------------------------

def _load_deploy_status() -> dict:
    try:
        if _DEPLOY_STATUS_PATH.exists():
            return json.loads(_DEPLOY_STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_deploy_status(result: dict) -> None:
    _DEPLOY_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DEPLOY_STATUS_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")


def _next_midnight_ist() -> str:
    """Return ISO string of the next midnight IST (UTC+5:30)."""
    from datetime import timedelta, timezone as tz
    IST = tz(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    next_mid = (now_ist + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_mid.isoformat()


# ---------------------------------------------------------------------------
# Core deploy logic — called by the scheduler job AND the manual override endpoint
# ---------------------------------------------------------------------------

def run_scheduled_deploy(triggered_by: str = "scheduler") -> dict:
    """
    Sync function (safe to call from APScheduler background thread).

    Pushes all files in prompt_changes.json to GitHub in a single batch,
    one commit per file.  Clears the pending list only if no errors occurred.

    Returns a status dict that is also persisted to data/prompt_deploy_status.json.
    """
    token  = os.environ.get("GITHUB_TOKEN", "").strip()
    repo   = os.environ.get("GITHUB_REPO",  "").strip()
    branch = os.environ.get("GITHUB_BRANCH", "main").strip()

    timestamp = datetime.now(timezone.utc).isoformat()

    if not token or not repo:
        result = {
            "status":       "skipped",
            "reason":       "GITHUB_TOKEN or GITHUB_REPO env var not set",
            "deployed":     [],
            "errors":       [],
            "triggered_by": triggered_by,
            "deployed_at":  timestamp,
        }
        _save_deploy_status(result)
        logger.info("[prompts/deploy] Skipped — GITHUB_TOKEN/REPO not configured")
        return result

    pending = _load_pending()
    if not pending:
        result = {
            "status":       "nothing_to_deploy",
            "deployed":     [],
            "errors":       [],
            "triggered_by": triggered_by,
            "deployed_at":  timestamp,
        }
        _save_deploy_status(result)
        logger.info("[prompts/deploy] Nothing pending — skipping")
        return result

    logger.info("[prompts/deploy] Deploying %d file(s) triggered by %s", len(pending), triggered_by)

    deployed: list[str] = []
    errors:   list[str] = []
    last_sha  = ""

    ts_label = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for github_path in pending:
        try:
            parts  = github_path.replace("\\", "/").split("/")
            sector = parts[3]
            agent  = parts[5].removesuffix(".py")
            local_path = _locate_prompt_file(sector, agent)
        except Exception as exc:
            errors.append(f"{github_path}: cannot resolve local file — {exc}")
            continue

        try:
            sha = _deploy_file_to_github(
                token, repo, branch, github_path, local_path,
                commit_message=(
                    f"prompt-lab ({triggered_by}): {sector}/{agent} [{ts_label}]"
                ),
            )
            deployed.append(github_path)
            last_sha = sha
            logger.info("[prompts/deploy] Pushed %s → %s", github_path, sha[:7] if sha else "?")
        except Exception as exc:
            errors.append(f"{github_path}: {exc}")
            logger.error("[prompts/deploy] Failed %s: %s", github_path, exc)

    if not errors:
        _clear_pending()

    result = {
        "status":       "deployed" if deployed else "error",
        "deployed":     deployed,
        "errors":       errors,
        "commit_sha":   last_sha,
        "triggered_by": triggered_by,
        "deployed_at":  timestamp,
    }
    _save_deploy_status(result)
    logger.info(
        "[prompts/deploy] Done — %d deployed, %d errors",
        len(deployed), len(errors),
    )
    return result


# ---------------------------------------------------------------------------
# Helpers — GitHub REST API
# ---------------------------------------------------------------------------

def _gh_request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    """Thin urllib wrapper for GitHub API calls. Raises RuntimeError on failure."""
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "StockAgent-PromptLab/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"GitHub API {method} {url} → HTTP {exc.code}: {body_text}"
        ) from exc


def _deploy_file_to_github(
    token: str,
    repo: str,
    branch: str,
    github_path: str,
    local_path: Path,
    commit_message: str,
) -> str:
    """
    Push a single file to GitHub using the Contents API.
    Returns the new commit SHA.
    """
    api_base = f"https://api.github.com/repos/{repo}/contents/{github_path}"

    # Fetch current file SHA (needed for update; None if file is new)
    current_sha: str | None = None
    try:
        info = _gh_request("GET", f"{api_base}?ref={branch}", token)
        current_sha = info.get("sha")
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise

    content_b64 = base64.b64encode(
        local_path.read_bytes()
    ).decode("ascii")

    payload: dict[str, Any] = {
        "message": commit_message,
        "content": content_b64,
        "branch":  branch,
    }
    if current_sha:
        payload["sha"] = current_sha

    result = _gh_request("PUT", api_base, token, payload)
    return result.get("commit", {}).get("sha", "unknown")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class PromptBody(BaseModel):
    system_prompt:          str
    analysis_prompt:        str
    context_search_queries: list[str] = []


class DeployResult(BaseModel):
    deployed: list[str]
    skipped:  list[str]
    errors:   list[str]
    commit_sha: str = ""
    deployed_at: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/catalogue", summary="List all sectors and their agent names")
async def get_catalogue(x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="prompts")
    return {
        "catalogue": [
            {
                "sector":  sector,
                "display": meta["display"],
                "agents":  [
                    {"key": key, "display": display}
                    for key, display in meta["agents"].items()
                ],
            }
            for sector, meta in _CATALOGUE.items()
        ]
    }


@router.get("/pending", summary="List prompt files modified since last deploy")
async def get_pending(x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="prompts")
    return {"pending": _load_pending()}


@router.get("/status", summary="Pending count, next scheduled deploy time, last deploy result")
async def get_deploy_status(x_scheduler_key: str | None = Header(default=None)) -> dict:
    """
    Used by the Prompt Lab UI to show the deploy schedule indicator.

    Returns:
      pending_count   — number of files awaiting the next deploy
      pending         — list of pending file paths
      next_deploy_at  — ISO datetime of next midnight IST run
      last_deploy     — result dict from the most recent deploy (or null)
      scheduler_configured — true if GITHUB_TOKEN + GITHUB_REPO are set
    """
    check_scheduler_key(x_scheduler_key, context="prompts")
    return {
        "pending_count":         len(_load_pending()),
        "pending":               _load_pending(),
        "next_deploy_at":        _next_midnight_ist(),
        "last_deploy":           _load_deploy_status() or None,
        "scheduler_configured":  bool(
            os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO")
        ),
    }


@router.get("/{sector}/{agent}", summary="Read a prompt file's three sections")
async def get_prompt(sector: str, agent: str,
                     x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="prompts")
    if sector not in _CATALOGUE:
        raise HTTPException(status_code=404, detail=f"Unknown sector '{sector}'")
    if agent not in _CATALOGUE[sector]["agents"]:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{agent}' for sector '{sector}'")

    try:
        content = _load_prompt_content(sector, agent)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "sector":  sector,
        "agent":   agent,
        "display": _CATALOGUE[sector]["agents"][agent],
        **content,
    }


@router.put("/{sector}/{agent}", summary="Save updated prompt content to disk")
async def put_prompt(sector: str, agent: str, body: PromptBody,
                     x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="prompts")
    if sector not in _CATALOGUE:
        raise HTTPException(status_code=404, detail=f"Unknown sector '{sector}'")
    if agent not in _CATALOGUE[sector]["agents"]:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{agent}' for sector '{sector}'")

    try:
        file_path = _locate_prompt_file(sector, agent)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    docstring = _extract_docstring(file_path)

    try:
        _write_prompt_file(
            file_path,
            docstring,
            body.system_prompt.strip(),
            body.analysis_prompt.strip(),
            [q.strip() for q in body.context_search_queries if q.strip()],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write prompt file: {exc}")

    # Patch the live module object in-place so agent modules that already hold a
    # reference to it (via `from ... import fundamentals as P`) see the new values
    # immediately — without waiting for a Railway redeploy.
    # Also remove from sys.modules so a fresh import() rebuilds from the new file.
    module_name = f"backend.sectors.{sector}.prompts.{agent}"
    live_mod = sys.modules.get(module_name)
    if live_mod is not None:
        live_mod.SYSTEM_PROMPT          = body.system_prompt.strip()
        live_mod.ANALYSIS_PROMPT        = body.analysis_prompt.strip()
        live_mod.CONTEXT_SEARCH_QUERIES = [q.strip() for q in body.context_search_queries if q.strip()]
    sys.modules.pop(module_name, None)

    # Track as pending deploy
    _add_pending(_github_path_for(sector, agent))

    logger.info("[prompts] Saved %s/%s to %s", sector, agent, file_path)
    return {
        "status":  "saved",
        "sector":  sector,
        "agent":   agent,
        "path":    str(file_path),
        "pending": _load_pending(),
    }


@router.post("/deploy", summary="Manual override: deploy now instead of waiting for midnight")
async def deploy_prompts(x_scheduler_key: str | None = Header(default=None)) -> DeployResult:
    """
    Emergency override — pushes pending changes immediately.

    Under normal operation you don't need this: the daily scheduler job at
    midnight IST batches all pending changes automatically.  Use this only
    when a prompt fix must be in Git right now (e.g. a broken agent in prod).

    Requires GITHUB_TOKEN + GITHUB_REPO env vars set in Railway.
    """
    check_scheduler_key(x_scheduler_key, context="prompts")
    import asyncio
    result = await asyncio.to_thread(run_scheduled_deploy, "manual")
    return DeployResult(
        deployed    = result.get("deployed", []),
        skipped     = [],
        errors      = result.get("errors",   []),
        commit_sha  = result.get("commit_sha", ""),
        deployed_at = result.get("deployed_at", ""),
    )
