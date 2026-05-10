# Sector Architecture — Design & Phase Roadmap

> Last updated: 2026-05-10
> Scope: How sectors are structured, routed, toggled, and analysed.

---

## Architecture Overview

```
User ticker / sector name
        │
        ▼
SectorRegistry.resolve(ticker)       ← Phase 0+1
  TICKER_SECTOR map (~200 tickers)
  + name-fragment fallback
        │
        ▼
SectorRegistry.get_handler(sector)   ← Phase 0
  enabled? ─── NO  ──→ AutomobileAgentOrchestrator  (safe degradation)
             │
             YES
             │
         tier=backend ──→ BackendOrchestratorClass   ← Tier 1
         tier=core    ──→ CoreSectorAdapter           ← Tier 2 (Phase 3)
```

---

## Two Tiers of Sector Coverage

### Tier 1 — Backend Sectors (full production pipeline)

4 sectors with domain-specific agents, context builders, prompts, and schemas.

| Sector | Key | Agents | Orchestrator |
|---|---|---|---|
| Automobile & Auto Ancillaries | `automobile` | 9 (SalesDemand, RawMaterials + 7 Universal) | AutomobileAgentOrchestrator |
| Banking & BFSI | `banking_bfsi` | 6 (UniverseSetup + 5 Universal) | BankingAgentOrchestrator |
| IT & Technology | `it_sector` | 8 (TranscriptNLP + 7 Universal) | ITAgentOrchestrator |
| Renewable Energy | `renewable_energy` | 6 (Business + 5 Universal) | RenewableAgentOrchestrator |

**Agent pipeline (all 4 sectors):**
```
resolve_ticker → input_rail → [fan-out × N agents] → run_agent (parallel) → aggregate → END
```

### Tier 2 — Core Sectors (8-pillar framework via CoreSectorAdapter)

23 sectors in `core/sectors/` with standardised 8-pillar agents. Accessible via `CoreSectorAdapter`
when toggled on. All **disabled by default** until individually validated.

8-pillar framework: `business · fundamentals · valuation · technical · macro · risk · management · earnings`

| Enabled by default | Disabled (off by default) |
|---|---|
| automobile, banking_bfsi, it_sector, renewable_energy | pharma, fmcg, metals, oilgas, capgoods, power, chemicals, defence, infra, insurance, logistics, media, realestate, retail, agrochem, hospitality, tech, telecom |

---

## Toggle System

**Config file:** `config/sector_toggles.json`

```json
{
  "pharma": { "enabled": false, "tier": "core", "display": "Pharmaceuticals & Healthcare" }
}
```

To enable a sector: set `"enabled": true` and restart the server. No code changes needed.

**Degradation contract:**
- Disabled sector → returns `AutomobileAgentOrchestrator` with a `WARNING` log
- No crash, no silent wrong analysis
- `SectorRegistry.is_enabled(sector)` returns False so calling code can warn the user

---

## UniversalAgent — Phase 2 Consolidation

Before Phase 2: 29 sector-specific agent class files (one per role per sector).  
After Phase 2: **1 universal class + 5 sector-specific** = 6 class definitions total.

```python
# Before: sector-specific class per role
class ITFundamentalsAgent(BaseAgent): ...          # one of 29 files
class BFSIFundamentalsAgent(BaseAgent): ...

# After: one universal class, prompts drive behaviour
UniversalAgent("fundamentals", it_sector.prompts.fundamentals, sector="it_sector")
UniversalAgent("fundamentals", banking_bfsi.prompts.fundamentals, sector="banking_bfsi")
```

**Sector-specific agents kept (custom data/parsing logic):**

| Agent | Sector | Why kept |
|---|---|---|
| `SalesDemandAgent` | automobile | FADA/SIAM/VAHAN data fetching |
| `RawMaterialsAgent` | automobile | Commodity price context assembly |
| `BFSIUniverseAgent` | banking_bfsi | Peer universe setup + sector config |
| `ITTranscriptNLPAgent` | it_sector | Earnings call transcript parsing |
| `REBusinessAgent` | renewable_energy | PLF/CUF/PPA operational metrics |

---

## SectorRegistry API

```python
from backend.sectors.registry import SectorRegistry

SectorRegistry.resolve("SUNPHARMA")        # → "pharma"
SectorRegistry.resolve("HDFC Bank Ltd")    # → "banking_bfsi" (name fragment)
SectorRegistry.resolve("UNKNOWN")          # → "automobile" (fallback)

SectorRegistry.get_handler("automobile")   # → AutomobileAgentOrchestrator (class)
SectorRegistry.get_handler("capgoods")     # → CoreAdapter_capgoods (class, if enabled)
SectorRegistry.get_handler("pharma")       # → AutomobileAgentOrchestrator + WARNING (disabled)

SectorRegistry.is_enabled("banking_bfsi")  # → True
SectorRegistry.is_enabled("pharma")        # → False
SectorRegistry.enabled_sectors()           # → ['automobile', 'banking_bfsi', 'it_sector', 'renewable_energy']
SectorRegistry.all_sectors()              # → list of all 27 sector dicts

# Backward-compatible shims (unchanged callers work)
from backend.sectors import detect_sector, get_orchestrator
detect_sector("TCS")                       # → "it_sector"
get_orchestrator("it_sector")             # → ITAgentOrchestrator
```

---

## CoreSectorAdapter — Phase 3

Wraps a `core/{sector}/graph.py` compiled LangGraph graph and exposes
the same `analyse_async(ticker)` interface as Tier-1 orchestrators.

```python
# Usage (done automatically by SectorRegistry when tier=core + enabled=True):
from backend.shared.pipeline.core_adapter import make_core_adapter_class

CapGoodsClass = make_core_adapter_class("capgoods")
adapter = CapGoodsClass()
report = await adapter.analyse_async("LT")
# Returns FinalReport: verdict, final_score, weighted_agent_scores, etc.
```

**Execution flow:**
```
CoreSectorAdapter.analyse_async("LT")
  → lazy-load core.sectors.capgoods.graph
  → await graph.ainvoke({"ticker": "LT"})  [120s timeout]
  → extract state["final_report"]          [primary path]
  → OR build FinalReport from agent_outputs [fallback]
```

---

## Ticker → Sector Map (Phase 1)

`TICKER_SECTOR` in `src/backend/sectors/registry.py` is the **single source of truth** for
routing ~200 tickers across all 27 sectors.

Adding a new ticker: add one line to `TICKER_SECTOR`, restart server.

```python
TICKER_SECTOR: dict[str, str] = {
    "MARUTI":    "automobile",
    "HDFCBANK":  "banking_bfsi",
    "TCS":       "it_sector",
    "SUNPHARMA": "pharma",       # disabled sector — still maps correctly
    "LT":        "capgoods",     # disabled sector — degrades to automobile
    ...
}
```

---

## Promotion Path: core → backend tier

```
1. disabled (toggle=false, tier=core)
      ↓  validate accuracy on paper trades, check 8-pillar agent quality
2. enabled + tier=core  (CoreSectorAdapter, 8-pillar generic agents)
      ↓  identify where generic prompts are insufficient
         add agents/, prompts/, schemas/, data/ under src/backend/sectors/{sector}/
3. enabled + tier=backend  (custom orchestrator, domain-specific agents)
```

No sector jumps straight to tier=backend in production. Every sector validates at the
CoreSectorAdapter level first.

---

## Sector Index Symbols (for get_sector_snapshot chat tool)

| Sector | NSE Index | Notes |
|---|---|---|
| automobile | `^CNXAUTO` | |
| banking_bfsi | `^NSEBANK` | Nifty Bank |
| it_sector | `^CNXIT` | |
| renewable_energy | `^CNXENERGY` | |
| pharma | `^CNXPHARMA` | |
| fmcg | `^CNXFMCG` | |
| metals | `^CNXMETAL` | |
| capgoods / infra | `^CNXINFRA` | shared index |
| realestate | `^CNXREALTY` | |
| oilgas | `^CNXENERGY` | proxy |
| media | `^CNXMEDIA` | |
| retail | `^CNXCONSUMP` | |
| defence | `^CNXPSUBANK` | PSU proxy |
| telecom | `^CNXPSE` | PSE proxy |

---

## Phase Roadmap

| Phase | Status | What |
|---|---|---|
| 0 | ✅ Done | Toggle registry (`sector_toggles.json` + `SectorRegistry`) |
| 1 | ✅ Done | Comprehensive ticker map (~200 tickers, all 27 sectors) |
| 2 | ✅ Done | Agent consolidation: 29 classes → 1 UniversalAgent + 5 specific |
| 3 | ✅ Done | CoreSectorAdapter: core graphs accessible via toggle |
| 4 | ✅ Done | Chat awareness: all 27 sectors in classify/planner prompts + index map |
| 5 | ⬜ Pending | Selective enablement: toggle pharma / metals / fmcg after validation |
| 6 | ⬜ Pending | Promote first core sector to tier=backend (custom agents + prompts) |
