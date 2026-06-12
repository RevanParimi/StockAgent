# Unified Analyst — BFSI / IT / Renewable Rollout

**Date:** 2026-06-13
**Status:** IMPLEMENTED 2026-06-13 (live-verified: HDFCBANK BUY 0.62, INFY NEUTRAL 0.494, ADANIGREEN 0.59, TATAPOWER 0.575 — all unified path, differentiated dimension scores; includes managed-ticker resolution short-circuit fixing TATAPOWER→TATAMOTORS)
**Parent spec:** `2026-06-12-unified-sector-analyst-design.md` (automobile, IMPLEMENTED)

## 1. Goal

Move the three remaining sectors onto the unified path. Per parent spec the contracts are
already sector-generic; this rollout adds sector prompt modules, a sector registry in the
analyst, and sector-awareness in the bundle builder. Legacy multi-agent paths stay as
fallback until a later cleanup.

## 2. Dimensions per sector (= existing AGENT_WEIGHTS keys, RL invariant)

| Sector | Dimensions (output keys, unchanged) |
|---|---|
| banking_bfsi (6) | fundamentals, risk, macro_policy, institutional, pattern_analysis, universe_setup |
| it_sector (8) | fundamentals, global_macro, risk_macro, peer_benchmark, pattern_analysis, sentiment, transcript_nlp, insider_smart_money |
| renewable_energy (6) | fundamentals, business, valuation, sentiment_policy, technical, risk |

Output classes: whatever class+sub_scores model the legacy `UniversalAgent` (or custom
agent) returns per dimension today — the implementer must read
`src/backend/shared/agents/universal.py` and each sector registry and replicate exactly.
Outputs keyed by sector dimension names; aggregator/FinalReport/RL are key-agnostic
(verified). Valuation extras (price_target etc.) remain automobile-only;
`extract_valuation_fields` already defaults to None when `valuation_catalyst` is absent.

## 3. Analyst generalization (`unified_analyst.py`)

Replace `_AUTOMOBILE_CLASSES` hardcoding with a sector spec registry:

```python
@dataclass(frozen=True)
class SectorSpec:
    classes: dict[str, type[AgentOutput]]   # dimension -> output class
    prompts_module: str                      # e.g. "backend.sectors.banking_bfsi.prompts.unified"
    has_valuation_extras: bool               # True only for automobile

SECTOR_SPECS: dict[str, SectorSpec] = {...4 sectors...}
DIMENSIONS = {s: list(spec.classes) for s, spec in SECTOR_SPECS.items()}
```

Parsing/salvage/never-raises logic unchanged.

## 4. Bundle builder sector-awareness

| Section | automobile | banking_bfsi | it_sector | renewable_energy |
|---|---|---|---|---|
| company_news query | results/guidance | results/NPA/NIM/deposits | results/deal wins/attrition | results/PPA/commissioning |
| sector_policy_news query | FAME/PLI/competitors | RBI policy/credit growth/regulation | US tech spend/visa/AI disruption | MNRE auctions/module prices/DISCOM |
| policy_deep_dive (1 Tavily) | policy/regulation | RBI policy impact | **earnings call transcript guidance** | **MNRE auction & policy** |
| commodities | raw-materials basket | "not_applicable" | "not_applicable" | "not_applicable" (module prices covered by news queries) |
| peers_valuation | auto peers | sector TICKERS list | sector TICKERS list | sector TICKERS list |
| macro_context cache key | automobile | bfsi alias | it alias | sector name |

Peer lists come from each sector's `config/settings.py` TICKERS. All other sections
(fundamentals, technicals, flows_sentiment, dossier) already sector-parameterized.
Tavily stays ≤1 per run for every sector (the sector-specific deep-dive query replaces
the legacy 2-3 Tavily calls in IT transcript_nlp / RE sentiment_policy — accepted
trade-off: one deep page on the highest-value target instead of three).

## 5. Prompts

One `prompts/unified.py` per sector (SYSTEM_PROMPT + ANALYSIS_PROMPT, same conventions
as automobile incl. brevity rules and doubled JSON braces), dimension definitions
distilled from the sector's legacy prompt files, sub_score names exactly from the
sector's `schemas/sub_scores.py` models.

## 6. Settings

`UNIFIED_ANALYST_SECTORS` default → `"automobile,banking_bfsi,it_sector,renewable_energy"`
after live verification. No new settings.

## 7. Validation

- Per sector: prompt-shape tests (dimensions + sub_score names + format-safety), analyst
  parse tests (class/key fidelity vs legacy registry), bundle sector tests (peer list,
  commodities n/a, deep-dive query, ≤3 Serper/≤1 Tavily), mocked e2e parity test
  (FinalReport keys == sector dimensions).
- Live (reviewer runs): one ticker per sector — HDFCBANK, INFY, TATAPOWER — unified path,
  differentiated scores. (Serper currently out of credits: news sections will degrade;
  acceptable, resilience is part of the design. Re-verify after top-up.)
- Flag-off byte-identical and automobile regression suite must stay green.

## 8. Not in scope

Deleting legacy agents/registries (after burn-in), early-exit logic, scheduler changes.
