"""
core/sectors/banking/registry.py
===============================
Agent registry for the Banking & NBFC sector.

Pillar weights:
  business        0.08
  fundamentals    0.18
  valuation       0.07
  technical       0.09
  macro           0.15
  risk            0.22
  management      0.13
  earnings        0.08
            ─────
Total           1.00
"""

from core.sectors.banking.business import BankBusinessAgent
from core.sectors.banking.fundamentals import BankFundamentalsAgent
from core.sectors.banking.valuation import BankValuationAgent
from core.sectors.banking.technical import BankTechnicalAgent
from core.sectors.banking.macro import BankMacroAgent
from core.sectors.banking.risk import BankRiskAgent
from core.sectors.banking.management import BankManagementAgent
from core.sectors.banking.earnings import BankEarningsAgent

AGENTS: dict = {
    "business": BankBusinessAgent(),
    "fundamentals": BankFundamentalsAgent(),
    "valuation": BankValuationAgent(),
    "technical": BankTechnicalAgent(),
    "macro": BankMacroAgent(),
    "risk": BankRiskAgent(),
    "management": BankManagementAgent(),
    "earnings": BankEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.08,
    "fundamentals": 0.18,
    "valuation": 0.07,
    "technical": 0.09,
    "macro": 0.15,
    "risk": 0.22,
    "management": 0.13,
    "earnings": 0.08,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
