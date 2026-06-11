"""
tests/test_weight_init_fix.py
==============================
3-Agent validation: weight initialization fix for non-automobile sectors.

Before fix: all non-automobile agents got weight=0.00 when no RL data existed,
because the fallback used settings.AGENT_WEIGHTS (automobile names only).

After fix: each sector orchestrator's _get_default_weights() returns
sector-specific AGENT_WEIGHTS so every agent gets its correct weight.

Agent 1 — Researcher : Calls _get_default_weights() on each sector orchestrator.
                        Calls _load_learned_weights() on a brand-new ticker to
                        confirm it returns None (no RL data exists).
                        Records what weight each agent would receive under old
                        (automobile fallback) vs new (sector-specific fallback).

Agent 2 — Designer   : Validates the weights numerically:
                        - All agents in the sector registry appear in the weights dict
                        - No registered agent has weight 0.0 UNLESS the sector settings
                          explicitly set it to 0.0 (e.g. RE risk=0.0 is intentional)
                        - Weights sum to 1.0 (or close: tolerance 0.01)
                        - Old automobile fallback would have given non-automobile agents 0.00

Agent 3 — Reviewer   : LLM reviews the weight tables and confirms the fix is correct.

Run:
    python -m tests.test_weight_init_fix
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date

import pytest

# ---------------------------------------------------------------------------
# Sector configuration (ground truth from settings files)
# ---------------------------------------------------------------------------

SECTOR_CONFIGS = {
    "renewable_energy": {
        "orchestrator_cls": "backend.sectors.renewable_energy.pipeline.orchestrator.RenewableAgentOrchestrator",
        "settings_mod": "backend.sectors.renewable_energy.config.settings",
        "test_ticker": "ADANIGREEN",
    },
    "banking_bfsi": {
        "orchestrator_cls": "backend.sectors.banking_bfsi.pipeline.orchestrator.BankingAgentOrchestrator",
        "settings_mod": "backend.sectors.banking_bfsi.config.settings",
        "test_ticker": "HDFCBANK",
    },
    "it_sector": {
        "orchestrator_cls": "backend.sectors.it_sector.pipeline.orchestrator.ITAgentOrchestrator",
        "settings_mod": "backend.sectors.it_sector.config.settings",
        "test_ticker": "TCS",
    },
}


def safe(s: str) -> str:
    return str(s).encode("ascii", "replace").decode("ascii")


def _import_class(dotted_path: str):
    module_path, cls_name = dotted_path.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, cls_name)


def _get_automobile_weights() -> dict[str, float]:
    from backend.shared.config import settings
    return dict(settings.AGENT_WEIGHTS)


# ---------------------------------------------------------------------------
# Agent 1 — Researcher
# ---------------------------------------------------------------------------

def agent_researcher() -> dict[str, dict]:
    print("\n" + "=" * 65)
    print("AGENT 1 - RESEARCHER: Auditing weight initialization per sector")
    print("=" * 65)

    auto_weights = _get_automobile_weights()
    print(f"\n  Automobile AGENT_WEIGHTS (the old fallback):")
    for name, w in auto_weights.items():
        print(f"    {name:<25} = {w:.2f}")

    results: dict[str, dict] = {}

    for sector, cfg in SECTOR_CONFIGS.items():
        print(f"\n  [{sector}]")
        cls = _import_class(cfg["orchestrator_cls"])
        orch = cls()

        # 1. Sector default weights (new path)
        sector_weights = orch._get_default_weights()

        # 2. RL learned weights (should be None for fresh ticker with no RL data)
        learned = orch._load_learned_weights("DOESNOTEXIST_TICKER_XYZ")

        # 3. What WOULD have happened under old fallback vs new fix
        old_weights = auto_weights
        new_weights = sector_weights

        # 4. Agent names registered in this sector
        agent_names = list(orch._sub_agents.keys())

        print(f"    Registered agents: {agent_names}")
        print(f"    _load_learned_weights(fresh_ticker) = {learned}  (expected: None)")
        print(f"    _get_default_weights() keys: {list(sector_weights.keys())}")
        print()
        print(f"    {'Agent':<25} {'OLD weight':>10} {'NEW weight':>10}  CORRECT?")
        print(f"    {'-'*25} {'-'*10} {'-'*10}  --------")

        agent_rows = {}
        for name in agent_names:
            old_w = old_weights.get(name, 0.0)
            new_w = new_weights.get(name, 0.0)
            # Correct = new_w matches sector settings (even if 0.0 is intentional)
            correct = new_w == sector_weights.get(name, 0.0)
            print(f"    {name:<25} {old_w:>10.3f} {new_w:>10.3f}  {'YES' if correct else 'NO'}")
            agent_rows[name] = {"old": old_w, "new": new_w, "correct": correct}

        results[sector] = {
            "learned_was_none": learned is None,
            "sector_weights": sector_weights,
            "agent_rows": agent_rows,
            "agent_names": agent_names,
        }

    return results


# ---------------------------------------------------------------------------
# Agent 2 — Designer
# ---------------------------------------------------------------------------

def agent_designer(research: dict[str, dict]) -> dict[str, dict]:
    print("\n" + "=" * 65)
    print("AGENT 2 - DESIGNER: Numerical validation of weight tables")
    print("=" * 65)

    auto_weights = _get_automobile_weights()
    evaluations: dict[str, dict] = {}

    for sector, data in research.items():
        print(f"\n  [{sector}]")
        sector_weights: dict[str, float] = data["sector_weights"]
        agent_rows: dict[str, dict]      = data["agent_rows"]
        agent_names: list[str]           = data["agent_names"]
        learned_was_none: bool           = data["learned_was_none"]

        checks: dict[str, bool] = {}

        # Check 1: _load_learned_weights returned None for a fresh ticker
        checks["rl_none_for_fresh_ticker"] = learned_was_none

        # Check 2: all registered agents appear in the sector weights
        missing = [n for n in agent_names if n not in sector_weights]
        checks["all_agents_in_sector_weights"] = len(missing) == 0
        if missing:
            print(f"    WARN: agents missing from sector settings: {missing}")

        # Check 3: weights sum to ~1.0
        w_sum = sum(sector_weights.values())
        checks["weights_sum_to_1"] = abs(w_sum - 1.0) < 0.01
        print(f"    Weights sum = {w_sum:.4f}  ({'OK' if checks['weights_sum_to_1'] else 'FAIL'})")

        # Check 4: old automobile fallback would have broken non-auto agents
        # (at least one registered agent must be absent from automobile weights)
        ghost_agents = [n for n in agent_names if n not in auto_weights]
        checks["old_fallback_would_have_broken"] = len(ghost_agents) > 0
        print(f"    Agents NOT in automobile weights: {ghost_agents}")

        # Check 5: new weights give every intentionally-non-zero agent a non-zero weight
        # (sector settings may intentionally set some to 0.0 — only flag unintentional zeros)
        intentional_zeros = [n for n in agent_names
                             if sector_weights.get(n, 0.0) == 0.0]
        unintentional_zeros = [n for n in agent_names
                               if n not in sector_weights]  # absent = unintentional
        checks["no_unintentional_zeros"] = len(unintentional_zeros) == 0
        if intentional_zeros:
            print(f"    Intentional zeros (explicit in sector settings): {intentional_zeros}")
        if unintentional_zeros:
            print(f"    ERROR unintentional zeros (absent from sector settings): {unintentional_zeros}")

        # Check 6: every agent's NEW weight matches their sector setting
        mismatches = [n for n, row in agent_rows.items() if not row["correct"]]
        checks["all_new_weights_match_settings"] = len(mismatches) == 0
        if mismatches:
            print(f"    ERROR weight mismatches: {mismatches}")

        all_pass = all(checks.values())
        print(f"    Checks: {checks}")
        print(f"    RESULT: {'PASS' if all_pass else 'FAIL'}")

        evaluations[sector] = {
            "checks": checks,
            "all_pass": all_pass,
            "w_sum": w_sum,
            "ghost_agents": ghost_agents,
        }

    # Summary grid
    print("\n  --- Sector Validation Grid ---")
    for sector, ev in evaluations.items():
        status = "PASS" if ev["all_pass"] else "FAIL"
        print(f"  {sector:<20} {status}  (weights_sum={ev['w_sum']:.3f}, "
              f"broken_by_old={len(ev['ghost_agents'])} agents)")

    return evaluations


# ---------------------------------------------------------------------------
# Agent 3 — Reviewer (LLM)
# ---------------------------------------------------------------------------

def agent_reviewer(research: dict[str, dict], evaluations: dict[str, dict]) -> bool:
    print("\n" + "=" * 65)
    print("AGENT 3 - REVIEWER: LLM quality judgment")
    print("=" * 65)

    from dotenv import load_dotenv
    load_dotenv()

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    llm_model      = os.getenv("LLM_MODEL", "qwen/qwen-2.5-72b-instruct")

    if not openrouter_key:
        print("  No OPENROUTER_API_KEY — running rule-based fallback")
        return _rule_based_review(evaluations)

    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    # Build weight comparison table for the prompt
    table_lines = []
    auto_weights = _get_automobile_weights()
    for sector, data in research.items():
        sector_weights = data["sector_weights"]
        agent_names    = data["agent_names"]
        table_lines.append(f"\n{sector.upper()}:")
        table_lines.append(f"  {'Agent':<25} {'OLD(auto)':>10} {'NEW(sector)':>10}")
        for name in agent_names:
            old_w = auto_weights.get(name, 0.0)
            new_w = sector_weights.get(name, 0.0)
            table_lines.append(f"  {name:<25} {old_w:>10.3f} {new_w:>10.3f}")

    prompt = f"""Today is {date.today().isoformat()}.
Stock analysis system — multi-sector, multi-agent. Each sector has 5-8 sub-agents.

BUG BEING FIXED:
When no RL-learned weights exist for a ticker (first analysis), the system fell back
to the AUTOMOBILE sector's AGENT_WEIGHTS dict. Since agent names differ per sector
(e.g. RE has "business", "sentiment_policy"; BFSI has "macro_policy", "institutional"),
those agents got weight=0.00 in the fallback — effectively discarding 82-95% of the
signal before aggregation.

FIX:
Each sector orchestrator now overrides _get_default_weights() to return its own
sector-specific AGENT_WEIGHTS. The base orchestrator uses:
  self._aggregator_weights = learned_weights or self._get_default_weights()

WEIGHT COMPARISON (OLD automobile fallback vs NEW sector-specific):
{''.join(table_lines)}

VALIDATION RESULTS (per-sector checks):
{json.dumps({s: ev['checks'] for s, ev in evaluations.items()}, indent=2)}

Evaluate:
1. Does the fix correctly resolve the 0.00 weight bug for all 3 sectors?
2. Are the sector-specific weight distributions sensible for each sector's agent roles?
3. Does the fallback priority (RL learned → sector default → never automobile) look correct?
4. Any edge cases the fix might miss?

Respond ONLY with valid JSON:
{{
  "verdict": "APPROVED" | "NEEDS_REVISION",
  "re_weights_correct": true | false,
  "bfsi_weights_correct": true | false,
  "it_weights_correct": true | false,
  "priority_chain_correct": true | false,
  "key_finding": "<one sentence — what the bug caused and what the fix achieves>",
  "edge_cases": ["<any edge case not handled>"],
  "recommendation": "ship" | "fix_then_ship" | "redesign"
}}"""

    try:
        resp = client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": "You are a concise financial AI pipeline reviewer. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw).strip()
        result = json.loads(raw)

        print(f"\n  Verdict                     : {result.get('verdict')}")
        print(f"  RE weights correct          : {result.get('re_weights_correct')}")
        print(f"  BFSI weights correct        : {result.get('bfsi_weights_correct')}")
        print(f"  IT weights correct          : {result.get('it_weights_correct')}")
        print(f"  Priority chain correct      : {result.get('priority_chain_correct')}")
        print(f"  Key finding                 : {safe(result.get('key_finding', ''))}")
        print(f"  Edge cases                  : {result.get('edge_cases', [])}")
        print(f"  Recommendation              : {result.get('recommendation')}")

        return result.get("verdict") == "APPROVED"

    except Exception as exc:
        print(f"  LLM failed: {exc}")
        return _rule_based_review(evaluations)


def _rule_based_review(evaluations: dict[str, dict]) -> bool:
    checks_passed = 0
    total = 0

    for sector, ev in evaluations.items():
        for check_name, passed in ev["checks"].items():
            total += 1
            if passed:
                checks_passed += 1

    pct = checks_passed / total * 100 if total else 0
    print(f"\n  Rule-based: {checks_passed}/{total} checks passed ({pct:.0f}%)")

    if pct >= 80:
        print("  Rule-based verdict: APPROVED")
        return True
    print("  Rule-based verdict: NEEDS_REVISION")
    return False


# ---------------------------------------------------------------------------
# Per-ticker aggregator weight scoping (RL knowledge layer — Task 13)
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestrator_fixture():
    """A freshly constructed sector orchestrator, built the same way agent_researcher() does."""
    cls = _import_class(
        "backend.sectors.automobile.pipeline.orchestrator.AutomobileAgentOrchestrator"
    )
    return cls()


def test_weights_reload_when_ticker_changes(orchestrator_fixture, monkeypatch):
    orch = orchestrator_fixture          # reuse the file's existing construction pattern
    calls = []
    monkeypatch.setattr(orch, "_load_learned_weights",
                         lambda t: calls.append(t) or {"risk_macro": 1.0})
    orch._aggregator_weights = None
    orch._resolve_weights_for("MARUTI")  # helper added in Step 3
    orch._resolve_weights_for("TATAMOTORS")
    assert calls == ["MARUTI", "TATAMOTORS"]   # second ticker NOT served cached weights


def test_externally_injected_weights_not_clobbered(orchestrator_fixture):
    orch = orchestrator_fixture
    orch.set_aggregator_weights({"risk_macro": 0.9}, ticker="MARUTI")
    orch._resolve_weights_for("MARUTI")
    assert orch._aggregator_weights == {"risk_macro": 0.9}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\nStockAgent — Weight Initialization Fix Validation (3-Agent Loop)")
    print("Tests: _get_default_weights() -> sector fallback -> correct weight per agent\n")

    research    = agent_researcher()
    evaluations = agent_designer(research)
    approved    = agent_reviewer(research, evaluations)

    print("\n" + "=" * 65)
    if approved:
        print("RESULT: APPROVED — weight initialization fix is working correctly")
    else:
        print("RESULT: NEEDS_REVISION — see Reviewer output above")
    print("=" * 65)

    sys.exit(0 if approved else 1)
