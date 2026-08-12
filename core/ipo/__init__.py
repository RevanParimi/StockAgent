"""PI Prospect — IPO intelligence.

An IPO is a two-process instrument: sentiment-driven at listing, evidence-driven
afterwards. This package owns both the data and (from P3) the model. It is
deliberately separate from core/discovery/, whose signals all assume a tape that
a pre-listing instrument does not have.
"""
from core.ipo.calendar import STATES, issue_state

__all__ = ["STATES", "issue_state"]
