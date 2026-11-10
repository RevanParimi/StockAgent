"""
core/intelligence/rl/workflows/review_outcomes.py
==================================================
SA-004: what one scheduled daily review actually produced.

The scheduler used to count every review that did not raise as output, so a
`no_envelope` return counted as a review done. On 2026-09-08 the job recorded
produced=20, expected=20 and pipeline_ok=true while WELCORP had no envelope
and only 19 feedback rows existed (audit F09).

Every required ticker now gets exactly one outcome:

    completed   the review wrote its feedback entry
    degraded    the review wrote its feedback entry, on an input the data gate
                would have stopped (SA-003 record mode lists those inputs)
    data_gated  the gate stopped the review before any write (enforce mode)
    skipped     a required input was missing: no envelope, no forecast row for
                the session, or no close
    failed      the review raised, returned a malformed result, or had not
                finished when the harvest budget ran out

Only completed and degraded reviews wrote feedback, so only they are output.
The rest leave the required cohort incomplete, and the zero- and
partial-output alerts see it.

A second run for the same review date (the day after a weekday holiday
reviews the same session again, AUD-051) merges with the first. A ticker's
standing outcome is the one that wrote its feedback, whichever run that was,
and its attempts add up. Completion is counted per ticker, never per attempt.

Pure functions, no I/O: the scheduler harvests, this module counts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

COMPLETED = "completed"
DEGRADED = "degraded"
DATA_GATED = "data_gated"
SKIPPED = "skipped"
FAILED = "failed"
OUTCOMES = (COMPLETED, DEGRADED, DATA_GATED, SKIPPED, FAILED)
WROTE_FEEDBACK = frozenset({COMPLETED, DEGRADED})

# Every status run_daily_review returns. A new early return must be added here
# deliberately (tests/unit/test_daily_review_outcomes_sa004.py checks the
# source); until then it counts as a malformed result, never as output.
REVIEW_COMPLETED = "completed"
REVIEW_DATA_GATED = "data_gated"
REVIEW_SKIP_STATUSES = ("no_envelope", "no_forecast_row", "no_actual_data")
REVIEW_STATUSES = (REVIEW_COMPLETED, REVIEW_DATA_GATED) + REVIEW_SKIP_STATUSES

# What run_post_review_pipeline returns when it ran as designed.
PIPELINE_STATUSES = ("completed", "disabled", "not_trading_day")
# Pipeline outcomes that leave the job healthy: it ran, or it is switched off.
_PIPELINE_HEALTHY = ("completed", "disabled")


@dataclass(frozen=True)
class ReviewOutcome:
    ticker: str
    outcome: str
    reason: str = ""


def _gate_stages(summary: dict) -> str:
    rows = summary.get("data_gate")
    if not isinstance(rows, list):
        return "data gate"
    stages = [str(r.get("stage")) for r in rows if isinstance(r, dict) and r.get("stage")]
    return "data gate: " + ", ".join(dict.fromkeys(stages)) if stages else "data gate"


def classify(ticker: str, review_date: str, summary: object,
             error: BaseException | None = None) -> ReviewOutcome:
    """The one outcome of one review attempt. Anything this cannot recognise
    fails closed: it is a failure, never output."""
    if error is not None:
        return ReviewOutcome(ticker, FAILED, f"exception: {type(error).__name__}")
    if not isinstance(summary, dict):
        return ReviewOutcome(ticker, FAILED, f"malformed: {type(summary).__name__} result")
    if summary.get("ticker") not in (None, ticker):
        return ReviewOutcome(ticker, FAILED, f"malformed: result for {summary.get('ticker')!r}")
    if summary.get("date") not in (None, review_date):
        return ReviewOutcome(ticker, FAILED, f"malformed: result dated {summary.get('date')!r}")
    status = summary.get("status")
    if status == REVIEW_COMPLETED:
        if summary.get("data_gate"):
            return ReviewOutcome(ticker, DEGRADED, _gate_stages(summary))
        return ReviewOutcome(ticker, COMPLETED)
    if status == REVIEW_DATA_GATED:
        return ReviewOutcome(ticker, DATA_GATED, _gate_stages(summary))
    if status in REVIEW_SKIP_STATUSES:
        return ReviewOutcome(ticker, SKIPPED, status)
    return ReviewOutcome(ticker, FAILED, f"malformed: status {status!r}")


def timed_out(ticker: str) -> ReviewOutcome:
    """A review still running when the harvest budget ran out. It may persist
    later (AUD-084), but this run cannot count it."""
    return ReviewOutcome(ticker, FAILED, "timeout")


def pipeline_status(result: object) -> str:
    """The post-review pipeline's own status, or `malformed`."""
    if isinstance(result, dict) and result.get("status") in PIPELINE_STATUSES:
        return str(result["status"])
    return "malformed"


def _previous_for(previous: object, review_date: str) -> dict:
    """The earlier run's per-ticker record, only when it reviewed the same
    date and carries SA-004's shape; a legacy record merges nothing."""
    if not isinstance(previous, dict) or previous.get("review_date") != review_date:
        return {}
    by_ticker = previous.get("by_ticker")
    return by_ticker if isinstance(by_ticker, dict) else {}


def summarize(
    review_date: str,
    required: list[str],
    outcomes: dict[str, ReviewOutcome],
    *,
    excluded: list[str] | None = None,
    duplicates: list[str] | None = None,
    previous: object = None,
) -> dict:
    """
    The review cohort for one review date: required work (the distinct enabled
    tickers) and attempted work (every review run for the date, across runs)
    are counted separately. `with_pipeline` adds the job-level status.

    Invariant: completed + degraded + data_gated + skipped + failed == required,
    with each required ticker counted once. A required ticker with no outcome
    counts as failed ("not harvested"), so a harvesting bug cannot shrink the
    cohort.
    """
    prior = _previous_for(previous, review_date)
    by_ticker: dict[str, dict] = {}
    this_run: Counter = Counter()
    retried: list[str] = []
    for sym in required:
        cur = outcomes.get(sym) or ReviewOutcome(sym, FAILED, "not harvested")
        this_run[cur.outcome] += 1
        before = prior.get(sym) if isinstance(prior.get(sym), dict) else None
        attempts = 1
        standing = {"outcome": cur.outcome, "reason": cur.reason}
        if before is not None:
            retried.append(sym)
            attempts += int(before.get("attempts") or 1)
            if cur.outcome not in WROTE_FEEDBACK and before.get("outcome") in WROTE_FEEDBACK:
                # The earlier run's feedback entry still stands for this date.
                standing = {"outcome": before["outcome"],
                            "reason": before.get("reason") or "", "from_earlier_run": True}
        by_ticker[sym] = {**standing, "attempts": attempts, "this_run": cur.outcome}

    counts = Counter(v["outcome"] for v in by_ticker.values())
    produced = counts[COMPLETED] + counts[DEGRADED]
    missing = {sym: f"{v['outcome']}: {v['reason']}" if v["reason"] else v["outcome"]
               for sym, v in by_ticker.items() if v["outcome"] not in WROTE_FEEDBACK}
    return {
        "review_date": review_date,
        "required": len(required),
        "attempted": sum(v["attempts"] for v in by_ticker.values()),
        **{name: counts[name] for name in OUTCOMES},
        "cohort_complete": produced == len(required),
        "missing": missing,
        "retried": retried,
        "runs": 1 + (int(previous.get("runs") or 1) if prior else 0),
        "this_run": {"attempted": len(required), **{n: this_run[n] for n in OUTCOMES}},
        "excluded": sorted(excluded or []),
        "duplicates": sorted(duplicates or []),
        "by_ticker": by_ticker,
        # Legacy fields, kept additively (AUD-090d readers): produced now means
        # a required ticker whose feedback entry exists, expected the cohort.
        "produced": produced,
        "expected": len(required),
    }


def with_pipeline(record: dict, pipeline: str) -> dict:
    """
    The job outcome: the cohort plus the post-review pipeline's status.

    status is ok only when every required ticker has its feedback entry and
    the pipeline completed (or is switched off); failed when no required
    ticker does; partial otherwise; empty when nothing was required (every
    managed ticker is disabled).

    pipeline_ok (legacy) is true only when the pipeline returned a well-formed
    `completed` AND no required review stands failed (raised, malformed or
    timed out): the 2026-09-08 record paired pipeline_ok=true with a short
    cohort. A skip or gate stop shows in status and the counts instead;
    pipeline_status says what the pipeline itself did.
    """
    required, produced = record["required"], record["produced"]
    if required == 0:
        status = "empty"
    elif produced == 0:
        status = "failed"
    elif produced < required or pipeline not in _PIPELINE_HEALTHY:
        status = "partial"
    else:
        status = "ok"
    return {"review_date": record["review_date"], "status": status, **record,
            "pipeline_status": pipeline,
            "pipeline_ok": pipeline == "completed" and record[FAILED] == 0}


def missing_detail(record: dict, limit: int = 300) -> str:
    """One line naming what is missing, grouped by why, for the alert text:
    'skipped no_envelope: WELCORP; failed timeout: INFY'."""
    groups: dict[str, list[str]] = {}
    for sym, why in (record.get("missing") or {}).items():
        groups.setdefault(why, []).append(sym)
    text = "; ".join(f"{why.replace(': ', ' ', 1)}: {', '.join(syms)}"
                     for why, syms in sorted(groups.items()))
    return text if len(text) <= limit else text[: limit - 1] + "…"
