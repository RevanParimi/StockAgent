# Sector Architecture — Design & Phase Roadmap

> Last updated: 2026-05-10 (agent optimization pass)
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

## Agent Optimization — Prompt Consolidation Pass

After Phase 2 (class-level consolidation), a second pass identified **prompt-level duplication
and internal sub_score overlaps** across the 29 agents. Four fixes applied.

### Fix 1 — Shared Technical Prompt (4 prompt files → 1 factory)

`automobile/pattern_analysis.py` · `banking_bfsi/pattern_analysis.py` ·
`it_sector/pattern_analysis.py` · `renewable_energy/technical.py`

All four scored the same five concepts under different names:

| Concept | Auto name | Banking name | IT name | RE name | **Standardised** |
|---|---|---|---|---|---|
| Price cycle position | price_cycle_position | price_cycle | price_cycle | moving_averages | **price_cycle** |
| RSI / MACD | rsi_macd_bb | momentum | momentum | rsi_signal + macd_weekly | **momentum** |
| Support / resistance | breakout_support_zone | breakout_zones | breakout_levels | accumulation_zone | **breakout_zones** |
| Vs sector index | peer_correlation | relative_strength | nifty_it_beta | — | **peer_relative_strength** |
| Volume quality | — | volume_pattern | volume_quality | volume_catalyst | **volume_confirmation** |

**Single source:** [src/backend/shared/agents/prompts/technical.py](src/backend/shared/agents/prompts/technical.py)

```python
from backend.shared.agents.prompts.technical import AUTO_TECHNICAL  # one import per sector

# Registry:
UniversalAgent("pattern_analysis", AUTO_TECHNICAL, sector="automobile")
```

Sector context injected at construction: `sector_index` (`^CNXAUTO` etc.), `peer_context`,
`seasonal_note` (auto festive season, banking rate-cycle, IT USD sensitivity, RE policy cycle).

---

### Fix 2 — Shared Institutional Flow Prompt (2 prompt files → 1 factory)

`banking_bfsi/institutional.py` and `it_sector/insider_smart_money.py` tracked identical
smart-money signals — only the FII metric differed:

| Dimension | Banking (`institutional`) | IT (`insider_smart_money`) | **Standardised** |
|---|---|---|---|
| FII signal | fii_dii_flow (cash market) | fii_futures (F&O net long) | **fii_dii_flow** |
| Promoter | promoter_holding | promoter_activity | **promoter_activity** |
| Insider | insider_trades | director_trades | **insider_activity** |
| MF | amfi_mf_flow | amfi_mf_flow ✓ identical | **mf_holding_change** |
| Large trades | bulk_block_deals | block_deals | **bulk_block_deals** |

**Single source:** [src/backend/shared/agents/prompts/institutional_flow.py](src/backend/shared/agents/prompts/institutional_flow.py)

The FII difference is parametrized: `BANKING_INSTITUTIONAL` focuses on cash-market FII
shareholding; `IT_INSTITUTIONAL` highlights FII F&O futures net positioning as a
forward-looking signal.

---

### Fix 3 — Banking Fundamentals Double-Count

`fundamentals.asset_quality` (GNPA/NPA/PCR) was **identical territory** to
`risk.asset_quality_trend` (slippage/SMA build-up). Both agents were firing LLM calls
reading the same NPA data.

**Fix:** `fundamentals` dimension 1 changed from `asset_quality` → `earnings_quality`:

| Before (fundamentals agent) | After (fundamentals agent) | Owned by |
|---|---|---|
| asset_quality — GNPA%, NPA%, PCR | *removed* | risk agent only |
| — | **earnings_quality** — NII composition, fee vs treasury income, recurring vs one-time earnings | fundamentals agent |

`risk.asset_quality_trend` remains the sole owner of NPA/slippage signals.

---

### Fix 4 — Auto Valuation Overlap

`valuation_catalyst` had two dimensions that were pure technical analysis — already
owned by `pattern_analysis`:

| Before (valuation_catalyst) | Problem | After (valuation_catalyst) |
|---|---|---|
| technical_trend — MA50/MA200 slope | duplicate of pattern_analysis | **earnings_yield_premium** — 1/PE vs 10Y G-Sec risk premium |
| support_zone_strength — support/resistance | duplicate of pattern_analysis | **catalyst_timing** — specific 60–90 day event catalysts |

`valuation_catalyst` now owns purely valuation and catalyst dimensions; `pattern_analysis`
owns all technical chart signals.

---

### Current Agent Inventory (post-optimization)

**Automobile — 9 agents**

| Agent | Sub-scores | Prompt source |
|---|---|---|
| sales_demand | fada_siam_dispatch, ev_segment_vahan, dealer_inventory, export_import, used_car_price_index | sector-specific |
| raw_materials | steel_aluminium, platinum_palladium, crude_oil_polymer, power_tariff, commodities_trend | sector-specific |
| fundamentals | revenue_ebitda_delta, margin_vs_peers, order_book_pipeline, attrition_headcount, promoter_fii_dii_flow | sector-specific |
| pattern_analysis | **price_cycle, momentum, breakout_zones, peer_relative_strength, volume_confirmation** | **shared technical** |
| sentiment | news_nlp, management_tone, twitter_reddit_sentiment, youtube_view_spikes, dealer_consumer_feedback | sector-specific |
| policy_regulatory | fame_ev_subsidy, emission_norms, union_budget_duties, pli_scheme, state_ev_incentives | sector-specific |
| competitive_intel | ev_market_share, new_model_pipeline, jv_acquisitions, adas_safety_ratings, competitive_position | sector-specific |
| risk_macro | inr_usd_crude_exposure, commodity_prices, rbi_repo_emi_impact, emission_policy_risk, global_geopolitical_risk | sector-specific |
| valuation_catalyst | pe_discount_vs_peers, **earnings_yield_premium**, mean_reversion_potential, **catalyst_timing**, recovery_signal_confidence | sector-specific (fixed) |

**Banking BFSI — 6 agents**

| Agent | Sub-scores | Prompt source |
|---|---|---|
| fundamentals | **earnings_quality**, net_interest, capital_adequacy, profitability, loan_mix | sector-specific (fixed) |
| risk | asset_quality_trend, concentration_risk, deposit_stability, regulatory_risk, cyber_fraud_risk | sector-specific |
| macro_policy | rbi_rate_cycle, system_credit, liquidity_conditions, regulatory_actions, fiscal_policy | sector-specific |
| institutional | **fii_dii_flow, promoter_activity, mf_holding_change, bulk_block_deals, insider_activity** | **shared institutional** |
| pattern_analysis | **price_cycle, momentum, breakout_zones, peer_relative_strength, volume_confirmation** | **shared technical** |
| universe_setup | index_weight, peer_positioning, market_cap_tier, corporate_actions, rebalancing_risk | sector-specific |

**IT Sector — 8 agents**

| Agent | Sub-scores | Prompt source |
|---|---|---|
| fundamentals | revenue_growth, ebit_margins, deal_wins, attrition, valuation | sector-specific |
| global_macro | us_tech_spend, fed_rate_impact, usd_inr, geopolitical, ma_activity | sector-specific |
| risk_macro | visa_risk, ai_disruption, client_concentration, fx_hedge, talent_risk | sector-specific |
| peer_benchmark | revenue_growth_rank, margin_rank, deal_momentum_rank, attrition_rank, valuation_gap | sector-specific |
| pattern_analysis | **price_cycle, momentum, breakout_zones, peer_relative_strength, volume_confirmation** | **shared technical** |
| sentiment | ai_narrative, layoff_signals, management_tone, sector_narrative, news_volume | sector-specific |
| transcript_nlp | guidance_delta, vertical_mix, geography_colour, ai_deal_count, analyst_pushback | sector-specific |
| insider_smart_money | **fii_dii_flow, promoter_activity, mf_holding_change, bulk_block_deals, insider_activity** | **shared institutional** |

**Renewable Energy — 6 agents**

| Agent | Sub-scores | Prompt source |
|---|---|---|
| fundamentals | capacity_utilisation, ebitda_quality, debt_serviceability, receivables, leverage | sector-specific |
| business | subsector_mix, ppa_quality, pipeline_cred, customer_divers, geography_spread | sector-specific |
| valuation | ev_per_mw, ev_ebitda, tariff_vs_auction, pipeline_dcf, implied_irr | sector-specific |
| sentiment_policy | mnre_auction_health, budget_allocation, policy_tailwinds, rbi_rate_impact, module_price | sector-specific |
| technical | **price_cycle, momentum, breakout_zones, peer_relative_strength, volume_confirmation** | **shared technical** |
| risk | discom_credit, curtailment_risk, ppa_protection, execution_risk, promoter_pledge | sector-specific |

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
| 2b | ✅ Done | Prompt consolidation: 4 technical → 1 shared factory; 2 institutional → 1 shared factory; fix 2 internal sub_score overlaps |
| 3 | ✅ Done | CoreSectorAdapter: core graphs accessible via toggle |
| 4 | ✅ Done | Chat awareness: all 27 sectors in classify/planner prompts + index map |
| 5 | ⬜ Pending | Selective enablement: toggle pharma / metals / fmcg after validation |
| 6 | ⬜ Pending | Promote first core sector to tier=backend (custom agents + prompts) |
