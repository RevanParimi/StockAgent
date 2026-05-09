"""
core/sectors/renewable/registry.py
=====================================
Agent registry for the Renewable Energy sector.

8-pillar framework from sector_analysis_v4_final.html:

Agent           Weight   Pillar
──────────────  ──────   ──────────────────────────────────────────────────
fundamentals    0.22     DSCR, CUF, EBITDA/MW, LCOE, Net Debt/EBITDA
management      0.12     Promoter integrity, debt discipline, EPC RPT, execution
business        0.15     IPP vs manufacturer, PPA quality, pipeline, land/grid
macro           0.14     MNRE auctions, RBI rates, module prices, DISCOM health
risk            0.10     DISCOM payment, curtailment, tariff renego, land litigation
valuation       0.14     EV/MW, EV/EBITDA, tariff vs auction, pipeline DCF, IRR
technical       0.08     50/200 DMA, RSI, MACD, volume, support zones
earnings        0.05     DSCR project-level, interest cap, gen vs revenue, OBS
                ─────
Total           1.00

Note: 'macro' replaces the previous 'sentiment_policy' agent with a more
structured macro framework. The old 'sentiment_policy' key is preserved in
LEGACY_AGENT_ALIASES for backward compatibility.
"""

from core.sectors.renewable.business import REBusinessAgent
from core.sectors.renewable.fundamentals import REFundamentalsAgent
from core.sectors.renewable.valuation import REValuationAgent
from core.sectors.renewable.macro import REMacroAgent
from core.sectors.renewable.technical import RETechnicalAgent
from core.sectors.renewable.risk import RERiskAgent
from core.sectors.renewable.management import REManagementAgent
from core.sectors.renewable.earnings import REEarningsAgent

AGENTS: dict = {
    "fundamentals": REFundamentalsAgent(),
    "management":   REManagementAgent(),
    "business":     REBusinessAgent(),
    "macro":        REMacroAgent(),
    "risk":         RERiskAgent(),
    "valuation":    REValuationAgent(),
    "technical":    RETechnicalAgent(),
    "earnings":     REEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "fundamentals": 0.22,
    "management":   0.12,
    "business":     0.15,
    "macro":        0.14,
    "risk":         0.10,
    "valuation":    0.14,
    "technical":    0.08,
    "earnings":     0.05,
}

# Backward compatibility: old sentiment_policy key maps to macro agent
LEGACY_AGENT_ALIASES: dict[str, str] = {
    "sentiment_policy": "macro",
}
