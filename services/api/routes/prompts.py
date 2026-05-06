"""
services/api/routes/prompts.py
==============================
Prompt Management API — read, edit, and deploy agent prompt files.

Endpoints
---------
GET  /ui/prompts/catalogue              — list all sectors + agent names
GET  /ui/prompts/{sector}/{agent}       — read SYSTEM_PROMPT, ANALYSIS_PROMPT, CONTEXT_SEARCH_QUERIES
PUT  /ui/prompts/{sector}/{agent}       — write updated content to disk
POST /ui/prompts/deploy                 — push all pending changes to GitHub (triggers Railway auto-deploy)
GET  /ui/prompts/pending                — list files modified since last deploy

Deploy flow
-----------
PUT saves to disk (container-local) AND appends the path to data/prompt_changes.json.
POST /deploy reads that list, pushes each file to GitHub via the Contents API
(PUT /repos/{owner}/{repo}/contents/{path}), then clears the pending list.

Env vars required for deploy:
  GITHUB_TOKEN — PAT with repo write scope
  GITHUB_REPO  — e.g. "username/StockAgent-main"  (owner/repo, no trailing slash)
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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
_PENDING_PATH = Path("data/prompt_changes.json")


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
async def get_catalogue() -> dict:
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
async def get_pending() -> dict:
    return {"pending": _load_pending()}


@router.get("/{sector}/{agent}", summary="Read a prompt file's three sections")
async def get_prompt(sector: str, agent: str) -> dict:
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
async def put_prompt(sector: str, agent: str, body: PromptBody) -> dict:
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

    # Invalidate the module cache so the next GET returns fresh content
    sys.modules.pop(f"backend.sectors.{sector}.prompts.{agent}", None)

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


@router.post("/deploy", summary="Push pending prompt changes to GitHub (triggers Railway auto-deploy)")
async def deploy_prompts() -> DeployResult:
    """
    For each file in data/prompt_changes.json:
      1. Locate it on disk (via importlib — same path used by PUT)
      2. Push to GitHub via Contents API (creates a commit on the configured branch)
      3. Railway auto-deploys on push to main

    Requires env vars:
      GITHUB_TOKEN  — PAT with repo write scope
      GITHUB_REPO   — e.g. "username/StockAgent-main"
      GITHUB_BRANCH — default "main"
    """
    token  = os.environ.get("GITHUB_TOKEN", "").strip()
    repo   = os.environ.get("GITHUB_REPO",  "").strip()
    branch = os.environ.get("GITHUB_BRANCH", "main").strip()

    if not token:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_TOKEN env var not set — cannot push to GitHub. "
                   "Set it in Railway environment variables.",
        )
    if not repo:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_REPO env var not set (expected format: 'owner/repo'). "
                   "Set it in Railway environment variables.",
        )

    pending = _load_pending()
    if not pending:
        return DeployResult(
            deployed=[], skipped=[], errors=[],
            deployed_at=datetime.now(timezone.utc).isoformat(),
        )

    deployed: list[str] = []
    skipped:  list[str] = []
    errors:   list[str] = []
    last_sha  = ""

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for github_path in pending:
        # Derive sector/agent from path e.g. src/backend/sectors/banking_bfsi/prompts/fundamentals.py
        try:
            parts = github_path.replace("\\", "/").split("/")
            # expected: src/backend/sectors/{sector}/prompts/{agent}.py
            sector = parts[3]
            agent  = parts[5].removesuffix(".py")
        except (IndexError, ValueError):
            errors.append(f"{github_path}: cannot parse sector/agent from path")
            continue

        try:
            local_path = _locate_prompt_file(sector, agent)
        except FileNotFoundError:
            skipped.append(f"{github_path}: local file not found")
            continue

        try:
            sha = _deploy_file_to_github(
                token, repo, branch, github_path, local_path,
                commit_message=f"prompt-lab: update {sector}/{agent} prompt [{timestamp}]",
            )
            deployed.append(github_path)
            last_sha = sha
            logger.info("[prompts/deploy] Pushed %s → commit %s", github_path, sha)
        except Exception as exc:
            errors.append(f"{github_path}: {exc}")
            logger.error("[prompts/deploy] Failed to push %s: %s", github_path, exc)

    if not errors:
        _clear_pending()

    return DeployResult(
        deployed=deployed,
        skipped=skipped,
        errors=errors,
        commit_sha=last_sha,
        deployed_at=datetime.now(timezone.utc).isoformat(),
    )
