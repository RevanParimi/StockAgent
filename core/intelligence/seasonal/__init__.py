"""
core/intelligence/seasonal
==========================
Pre-seeded seasonal pattern knowledge for all four sectors.

Public API:
    SeasonalCalendar   — loads YAML seeds + RL lessons → SeasonalContext per date
    SeasonalValidator  — tracks RL confirmation/contradiction of seed patterns
"""

from core.intelligence.seasonal.calendar import SeasonalCalendar
from core.intelligence.seasonal.validator import SeasonalValidator, ValidationResult

__all__ = ["SeasonalCalendar", "SeasonalValidator", "ValidationResult"]
