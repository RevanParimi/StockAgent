"""
src/backend/shared/pipeline/no_analysis.py
==========================================
CLEAN-005: what an analysis that scored nothing is.

The one analysis call per stock (`unified_analyst.py`) can come back with no
scored dimension: the model call timed out or failed after its retries, its
answer was not readable, or it named none of the sector's dimensions. There is
no second method behind it any more. The orchestrator raises
`AnalysisUnavailable` instead of returning a report, so no caller can read a
verdict, a score, a forecast or a grade from a run that measured nothing.

What each caller does with it (KT section 4, "When the analysis fails"):

- the 16:30 review skips the stock for that session (status `no_analysis`),
  before any write;
- the monthly forecast, a re-forecast, the paper lane, the deep dive and the
  scheduler's manual run skip the stock and carry on with the others;
- the on-demand routes say that today's analysis could not be produced, with
  no verdict and no score.

The orchestrator logs the failure once and records it
(`services/data/stores/analysis_failures.py`); callers do not log it again.
"""

from __future__ import annotations

from collections.abc import Mapping

from backend.shared.schemas.pipeline import AgentOutput

# What a person reads on the on-demand routes. Plain words, no verdict, no score.
UNAVAILABLE_MESSAGE = (
    "Today's analysis of {ticker} could not be produced: the analysis model gave "
    "no usable answer. No verdict or score is shown. Please try again later."
)


class AnalysisUnavailable(RuntimeError):
    """The analysis of `ticker` scored no dimension. Carries no report."""

    def __init__(self, ticker: str, sector: str, reason: str, run_id: str = "") -> None:
        self.ticker = ticker
        self.sector = sector
        self.reason = reason
        self.run_id = run_id
        super().__init__(f"no analysis for {ticker} ({sector}): {reason}")

    def user_message(self) -> str:
        return UNAVAILABLE_MESSAGE.format(ticker=self.ticker)


def scored_nothing(outputs: Mapping[str, AgentOutput] | None) -> bool:
    """True when no dimension produced a score.

    An output with `error` set carries a neutral 0.5 that was never measured
    (the aggregator excludes it for the same reason), so a run whose every
    output is errored measured nothing, like a run with no outputs at all."""
    if not outputs:
        return True
    return all(getattr(o, "error", None) for o in outputs.values())


def why_nothing(outputs: Mapping[str, AgentOutput] | None, analyst_reason: str | None) -> str:
    """One plain line naming why the run scored nothing."""
    if not outputs:
        return analyst_reason or "the analysis returned no answer"
    errors = sorted({str(getattr(o, "error", "")) for o in outputs.values()})
    return (f"no dimension scored ({len(outputs)} of {len(outputs)} failed: "
            f"{', '.join(e[:60] for e in errors[:3])})")
