# Verification Layer ("the auditor") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, read-only auditor that grades every issued verdict, alert, and shelf idea against the NIFTY 50 at +10/30/60 trading days, and alerts when the system stops beating the index or the sensing stack degrades.

**Architecture:** New `core/audit/` package outside `core/intelligence/rl/`. A recorder walks the advice ledger / sent-alerts log / discovery shelf, marks prices at matured horizons, and appends rows to a new append-only `advice_outcomes.jsonl`. The source ledgers are never rewritten. All judgment lives in pure functions in `metrics.py`. No LLM anywhere.

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI, APScheduler, pytest. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-08-07-verification-layer-design.md`

**Branch:** `verification-layer` (already exists, currently at `d7f1c55`)

## Global Constraints

- **No LLM calls anywhere in `core/audit/`.** The auditor's credibility rests on being arithmetic.
- **Never write** to weights, lessons, dossiers, envelopes, portfolio, or any source ledger. The auditor's only write target is `advice_outcomes.jsonl`.
- **`correct` is defined on excess return vs `^NSEI`, never raw return.** Raw return makes every HOLD look right in a bull market.
- **Every tunable goes through `cfg("audit.<key>", fallback=...)`** with **no `env=`** — config.yaml is the sole source for non-secret toggles (user rule, 2026-07-28).
- **Every metric reports its `n`** and returns `INSUFFICIENT_DATA` below the configured minimum. Never state a rate from a handful of rows.
- **Never raise into a caller.** Grading failures are logged and counted, exactly like `emit_alerts` and `ops_alerts`. A broken auditor must not take down the pipeline it watches.
- **Verdict vocabulary** is exactly `INSUFFICIENT_DATA` | `BELOW_COIN_FLIP` | `UNPROVEN` | `BEATS_BENCHMARK`.
- **Import ban:** no module in `core/audit/` may contain a `core.intelligence.rl.agents` or `core.portfolio.advisor` import statement. (Transitive loading via `core.portfolio.pricing` is unavoidable and permitted — the ban is on the auditor's own source, enforced statically in Task 1.)
- Existing verdict enum is exactly `Verdict = Literal["HOLD", "ADD", "TRIM", "EXIT", "SWITCH"]` (`src/backend/shared/schemas/portfolio.py:16`). Do not invent verdicts.
- **No declared-but-unwritten fields.** If a field exists on `AuditOutcome`, some task in this plan populates it. This program exists because three such fields sat dead in `AdviceRecord` for months; reproducing the pattern in the fix would be indefensible. (This is why `sector_excess_pct`, present in the spec's §4.2 sketch, is **not** in the schema below — no sector→index map exists in `core/`, the only one lives in the API layer at `ui_data.py:227-234`, and a nullable field nothing writes is the anti-pattern. Spec §4.2 and §12 were amended to match.)

---

### Task 1: Package skeleton, outcome schema, append-only store, boundary guard

Establishes the package and the architectural invariant that keeps the auditor honest, before any logic exists to violate it.

**Files:**
- Create: `core/audit/__init__.py`
- Create: `src/backend/shared/schemas/audit.py`
- Create: `core/audit/store.py`
- Test: `tests/unit/audit/__init__.py`
- Test: `tests/unit/audit/test_audit_store.py`
- Test: `tests/unit/audit/test_audit_boundaries.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `AuditOutcome` pydantic model (fields listed in Step 3).
  - `AuditOutcomeStore(user_id: str | None = None, base_dir: str | None = None)` with `.append(row: AuditOutcome) -> None`, `.load_all() -> list[AuditOutcome]`, `.existing_keys() -> set[tuple[str, int]]`, `.path -> Path`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/audit/__init__.py` as an empty file, then `tests/unit/audit/test_audit_store.py`:

```python
import json

import pytest

from backend.shared.schemas.audit import AuditOutcome
from core.audit.store import AuditOutcomeStore


def _row(ref: str = "2026-07-03|MARUTI|abc123", horizon: int = 30) -> AuditOutcome:
    return AuditOutcome(
        ref=ref, lane="advice", user_id="primary", symbol="MARUTI",
        verdict="HOLD", triggers=["thesis_break"], issued_on="2026-07-03",
        horizon_td=horizon, graded_on="2026-08-14",
        entry_close=12450.0, exit_close=12890.5, return_pct=3.54,
        bench_entry=24810.2, bench_exit=25102.7, bench_pct=1.18,
        excess_pct=2.36, correct=True, graded_at="2026-08-14T02:11:04Z",
    )


def test_append_and_load_roundtrip(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    store.append(_row())
    rows = store.load_all()
    assert len(rows) == 1
    assert rows[0].symbol == "MARUTI" and rows[0].excess_pct == 2.36


def test_append_is_append_only(tmp_path):
    """Mirrors test_advice_ledger_append_only: a second write never rewrites
    the first line."""
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    store.append(_row(horizon=10))
    store.append(_row(horizon=30))
    lines = store.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["horizon_td"] == 10


def test_corrupt_line_is_skipped_not_fatal(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    store.append(_row())
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    assert len(store.load_all()) == 1


def test_existing_keys_reports_ref_and_horizon(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    store.append(_row(horizon=10))
    store.append(_row(horizon=30))
    assert store.existing_keys() == {
        ("2026-07-03|MARUTI|abc123", 10),
        ("2026-07-03|MARUTI|abc123", 30),
    }


def test_load_all_on_missing_file_returns_empty(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    assert store.load_all() == []


def test_rejects_invalid_user_id(tmp_path):
    with pytest.raises(ValueError):
        AuditOutcomeStore(user_id="../escape", base_dir=str(tmp_path))
```

And `tests/unit/audit/test_audit_boundaries.py`:

```python
"""The auditor must not import the components it grades.

Static source scan, not a runtime module-graph check: core.portfolio.pricing
imports daily_review, which imports feedback_agent and weight_adapter at
module level, so ANY use of close_on transitively loads the agents. That is
unavoidable without duplicating price code. The meaningful invariant is that
the auditor's own source never names them.
"""
from pathlib import Path

FORBIDDEN = ("core.intelligence.rl.agents", "core.portfolio.advisor")

AUDIT_DIR = Path(__file__).resolve().parents[3] / "core" / "audit"


def test_audit_package_exists():
    assert AUDIT_DIR.is_dir(), f"expected package at {AUDIT_DIR}"


def test_no_forbidden_imports_in_audit_sources():
    offenders = []
    for py in sorted(AUDIT_DIR.rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for banned in FORBIDDEN:
                if banned in stripped:
                    offenders.append(f"{py.name}: {stripped}")
    assert offenders == [], (
        "core/audit must not import the components it grades: " + "; ".join(offenders)
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/audit/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.shared.schemas.audit'` and the boundary test failing on the missing directory.

- [ ] **Step 3: Create the schema**

Create `src/backend/shared/schemas/audit.py`:

```python
"""Verification layer — the graded-outcome row (design 2026-08-07 section 4.2).

One row per (ref, horizon_td). Written append-only to
data/portfolio/<user_id>/advice_outcomes.jsonl. The source ledgers are never
rewritten: grading is derived data and derived data must not be able to
corrupt what the user was actually told.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Lane = Literal["advice", "alert", "shelf"]


class AuditOutcome(BaseModel):
    ref: str                       # "<issued_on>|<symbol>|<hash-or-kind>"
    lane: Lane
    user_id: str
    symbol: str
    verdict: str = ""              # "" for shelf rows — they are not calls
    triggers: list[str] = Field(default_factory=list)
    issued_on: str                 # ISO date the call was made
    horizon_td: int                # 10 | 30 | 60 trading days
    graded_on: str                 # ISO date the horizon matured

    entry_close: float
    exit_close: float
    return_pct: float              # (exit/entry - 1) * 100

    bench_entry: float
    bench_exit: float
    bench_pct: float
    excess_pct: float              # return_pct - bench_pct

    correct: bool | None           # None for shelf rows (never scored)
    graded_at: str                 # UTC ISO timestamp the grade was taken

    # Optional, present only where they apply (design section 4.2)
    switch_excess_pct: float | None = None   # SWITCH rows with a priceable candidate
    conviction: float | None = None          # shelf rows only

    def key(self) -> tuple[str, int]:
        return (self.ref, self.horizon_td)
```

- [ ] **Step 4: Create the package and store**

Create `core/audit/__init__.py`:

```python
"""Verification layer — the deterministic auditor.

Grades every issued verdict, alert and shelf idea against the NIFTY 50 at
+10/30/60 trading days. Read-only over the learning stack: no LLM, and no
writes to weights, lessons, dossiers, envelopes or the portfolio.

Design: docs/superpowers/specs/2026-08-07-verification-layer-design.md
"""
```

Create `core/audit/store.py`:

```python
"""Append-only JSONL store for graded outcome rows.

Deliberately separate from advice_ledger.jsonl. The ledger is the audit
authority for what the system told the user and its append-only property is
enforced by test_advice_ledger_append_only; a nightly grading job must not be
in the business of rewriting it.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from backend.shared.schemas.audit import AuditOutcome
from core.config import settings

logger = logging.getLogger(__name__)

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AuditOutcomeStore:
    """One file per user: data/portfolio/<user_id>/advice_outcomes.jsonl."""

    def __init__(self, user_id: str | None = None, base_dir: str | None = None) -> None:
        self.user_id = (user_id or settings.PORTFOLIO_DEFAULT_USER_ID).strip()
        if not _USER_ID_RE.fullmatch(self.user_id):
            raise ValueError(
                f"invalid user_id {self.user_id!r} — allowed: [A-Za-z0-9_-], max 64 chars"
            )
        self._dir = Path(base_dir or settings.PORTFOLIO_DATA_DIR) / self.user_id
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._dir / "advice_outcomes.jsonl"

    def append(self, row: AuditOutcome) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(row.model_dump_json() + "\n")

    def load_all(self) -> list[AuditOutcome]:
        path = self.path
        if not path.exists():
            return []
        out: list[AuditOutcome] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(AuditOutcome(**json.loads(line)))
            except Exception:
                continue     # a corrupt line must never break the report
        return out

    def existing_keys(self) -> set[tuple[str, int]]:
        """Every (ref, horizon_td) already graded — the idempotency guard."""
        return {row.key() for row in self.load_all()}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/audit/ -v`
Expected: PASS — 8 tests.

- [ ] **Step 6: Commit**

```bash
git add core/audit/__init__.py core/audit/store.py \
        src/backend/shared/schemas/audit.py tests/unit/audit/
git commit -m "feat(audit): outcome schema, append-only store, import-boundary guard"
```

---

### Task 2: Trading-day forward arithmetic and the benchmark series

`nse_calendar` can count trading days backward but not forward, and nothing anywhere fetches a NIFTY 50 close. Both are prerequisites for grading.

**Files:**
- Modify: `core/intelligence/rl/nse_calendar.py` (add `trading_days_after`, after `trading_days_ago` at line 159)
- Create: `core/audit/benchmark.py`
- Test: `tests/unit/audit/test_audit_benchmark.py`
- Test: `tests/unit/test_nse_calendar.py` (append; create if absent)

**Interfaces:**
- Consumes: `AuditOutcomeStore` (Task 1) — not directly, but same package conventions.
- Produces:
  - `nse_calendar.trading_days_after(reference: date, n: int) -> date`
  - `core.audit.benchmark.BenchmarkSeries(ticker: str | None = None)` with `.close_on(d: date) -> float` (memoised per instance) and `.pct_change(start: date, end: date) -> float`.
  - `core.audit.benchmark.BenchmarkUnavailableError`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/audit/test_audit_benchmark.py`:

```python
from datetime import date
from unittest.mock import patch

import pytest

from core.audit.benchmark import BenchmarkSeries, BenchmarkUnavailableError
from core.intelligence.rl.nse_calendar import trading_days_after


def test_trading_days_after_skips_weekend():
    # 2026-08-07 is a Friday; +1 trading day is Monday 2026-08-10.
    assert trading_days_after(date(2026, 8, 7), 1) == date(2026, 8, 10)


def test_trading_days_after_zero_returns_reference():
    assert trading_days_after(date(2026, 8, 7), 0) == date(2026, 8, 7)


def test_trading_days_after_is_inverse_of_ago():
    from core.intelligence.rl.nse_calendar import trading_days_ago
    start = date(2026, 8, 7)
    assert trading_days_ago(trading_days_after(start, 10), 10) == start


def test_benchmark_close_memoised_within_instance():
    series = BenchmarkSeries()
    with patch("core.audit.benchmark._fetch_index_close", return_value=24810.2) as m:
        assert series.close_on(date(2026, 8, 7)) == 24810.2
        assert series.close_on(date(2026, 8, 7)) == 24810.2
    assert m.call_count == 1        # second read came from the memo


def test_benchmark_pct_change():
    series = BenchmarkSeries()
    with patch("core.audit.benchmark._fetch_index_close", side_effect=[100.0, 110.0]):
        assert series.pct_change(date(2026, 7, 1), date(2026, 8, 1)) == 10.0


def test_benchmark_raises_when_unavailable():
    series = BenchmarkSeries()
    with patch("core.audit.benchmark._fetch_index_close", return_value=None):
        with pytest.raises(BenchmarkUnavailableError):
            series.close_on(date(2026, 8, 7))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/audit/test_audit_benchmark.py -v`
Expected: FAIL — `ImportError: cannot import name 'trading_days_after'`.

- [ ] **Step 3: Add the calendar helper**

In `core/intelligence/rl/nse_calendar.py`, immediately after `trading_days_ago` (which ends at line 159), add:

```python
def trading_days_after(reference: date, n: int) -> date:
    """
    Return the calendar date exactly N NSE trading days after reference.
    Skips weekends and NSE holidays. n=0 returns reference unchanged.

    The forward twin of trading_days_ago — the verification layer needs to ask
    "what date is +30 trading days from this advice?" and approximating with
    calendar days would misdate every horizon across a holiday.
    """
    if n <= 0:
        return reference
    count = 0
    d = reference
    while count < n:
        d += timedelta(days=1)
        if is_trading_day(d):
            count += 1
    return d
```

- [ ] **Step 4: Create the benchmark module**

Create `core/audit/benchmark.py`:

```python
"""NIFTY 50 close lookup for benchmark-relative grading.

Nothing else in the codebase fetches an index close for comparison — the
`^NSEI` references in regime/detector.py are momentum inputs, not benchmarks.
This is the module that closes that gap (design section 1, Gap D).

Memoised per instance: a backfill grades thousands of rows against the same
few hundred index dates, so one BenchmarkSeries per run turns N fetches into
one per distinct date.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from backend.shared.config.settings.loader import cfg
from core.intelligence.rl.nse_calendar import is_trading_day

logger = logging.getLogger(__name__)

_MAX_WALKBACK_DAYS = 10        # matches core.portfolio.pricing.close_on


class BenchmarkUnavailableError(Exception):
    """No index close could be fetched for the date, even after walkback."""


def _fetch_index_close(ticker: str, d: date) -> float | None:
    """One yfinance index close. Returns None on any failure — the caller
    decides whether that is fatal. Isolated in its own function so tests can
    patch it without touching the network."""
    try:
        import yfinance as yf
        frame = yf.download(
            ticker,
            start=d.isoformat(),
            end=(d + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=True,
        )
        if frame is None or frame.empty:
            return None
        return float(frame["Close"].iloc[0])
    except Exception as exc:
        logger.debug("[audit.benchmark] fetch failed for %s on %s: %s", ticker, d, exc)
        return None


class BenchmarkSeries:
    """Index closes with holiday walkback, memoised for the life of one run."""

    def __init__(self, ticker: str | None = None) -> None:
        self.ticker = ticker or cfg("audit.benchmark_ticker", fallback="^NSEI")
        self._memo: dict[date, float] = {}

    def close_on(self, d: date) -> float:
        if d in self._memo:
            return self._memo[d]
        cursor = d
        for _ in range(_MAX_WALKBACK_DAYS):
            if is_trading_day(cursor):
                close = _fetch_index_close(self.ticker, cursor)
                if close is not None:
                    self._memo[d] = close
                    return close
                break
            cursor -= timedelta(days=1)
        raise BenchmarkUnavailableError(
            f"no {self.ticker} close available on/near {d}"
        )

    def pct_change(self, start: date, end: date) -> float:
        first = self.close_on(start)
        last = self.close_on(end)
        if first <= 0:
            raise BenchmarkUnavailableError(f"non-positive {self.ticker} close on {start}")
        return round((last / first - 1.0) * 100.0, 4)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/audit/test_audit_benchmark.py -v`
Expected: PASS — 6 tests.

- [ ] **Step 6: Verify the calendar change broke nothing**

Run: `python -m pytest tests/unit/ -k "calendar or nse" -q`
Expected: PASS, no regressions (the change is purely additive).

- [ ] **Step 7: Commit**

```bash
git add core/intelligence/rl/nse_calendar.py core/audit/benchmark.py \
        tests/unit/audit/test_audit_benchmark.py
git commit -m "feat(audit): forward trading-day arithmetic and NIFTY 50 benchmark series"
```

---

### Task 3: The correctness rules

The load-bearing definition. Isolated in pure functions so it is exhaustively testable and so changing it later is a single, visible diff.

**Files:**
- Create: `core/audit/rules.py`
- Test: `tests/unit/audit/test_audit_rules.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `pct_change(entry: float, exit_close: float) -> float`
  - `excess(return_pct: float, bench_pct: float) -> float`
  - `is_correct(verdict: str, excess_pct: float) -> bool | None`
  - `INTENT_LONG: frozenset[str]`, `INTENT_REDUCE: frozenset[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_rules.py`:

```python
import pytest

from core.audit.rules import excess, is_correct, pct_change


@pytest.mark.parametrize("verdict", ["HOLD", "ADD"])
def test_long_intent_correct_when_beating_benchmark(verdict):
    assert is_correct(verdict, 2.5) is True
    assert is_correct(verdict, 0.0) is True      # tie counts as correct
    assert is_correct(verdict, -2.5) is False


@pytest.mark.parametrize("verdict", ["TRIM", "EXIT", "SWITCH"])
def test_reduce_intent_correct_when_underperforming(verdict):
    assert is_correct(verdict, -2.5) is True
    assert is_correct(verdict, 0.0) is False     # tie: leaving gained nothing
    assert is_correct(verdict, 2.5) is False


def test_shelf_and_unknown_verdicts_are_never_scored():
    assert is_correct("", 5.0) is None
    assert is_correct("shelf_add", 5.0) is None
    assert is_correct("WHATEVER", -5.0) is None


def test_verdict_matching_is_case_and_space_insensitive():
    assert is_correct("  hold  ", 1.0) is True
    assert is_correct("exit", -1.0) is True


def test_pct_change():
    assert pct_change(100.0, 110.0) == 10.0
    assert pct_change(100.0, 90.0) == -10.0
    assert pct_change(100.0, 100.0) == 0.0


def test_pct_change_rejects_non_positive_entry():
    with pytest.raises(ValueError):
        pct_change(0.0, 110.0)
    with pytest.raises(ValueError):
        pct_change(-5.0, 110.0)


def test_excess_is_difference_of_percentages():
    assert excess(3.54, 1.18) == 2.36
    assert excess(-1.0, 4.0) == -5.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.audit.rules'`.

- [ ] **Step 3: Write the implementation**

Create `core/audit/rules.py`:

```python
"""What "correct" means (design section 5).

Everything the auditor will ever claim rests on this file, and it is the only
part that cannot be quietly changed later without invalidating accumulated
history. Hence: pure functions, no I/O, exhaustively tested.

Correctness is defined on EXCESS return against the benchmark, never on raw
return. In a bull market raw return makes every HOLD look right; the only
question worth asking is whether following the advice beat doing nothing.
"""
from __future__ import annotations

# Verdicts whose intent is to keep or increase exposure.
INTENT_LONG = frozenset({"HOLD", "ADD"})
# Verdicts whose intent is to reduce or leave the position.
INTENT_REDUCE = frozenset({"TRIM", "EXIT", "SWITCH"})


def pct_change(entry: float, exit_close: float) -> float:
    """Percentage move from entry to exit. Raises on a non-positive entry —
    a zero or negative close is bad data, not a 0% move."""
    if entry <= 0:
        raise ValueError(f"entry close must be positive, got {entry!r}")
    return round((exit_close / entry - 1.0) * 100.0, 4)


def excess(return_pct: float, bench_pct: float) -> float:
    """Return above the benchmark, in percentage points."""
    return round(return_pct - bench_pct, 4)


def is_correct(verdict: str, excess_pct: float) -> bool | None:
    """True/False for scoreable verdicts, None for everything else.

    None is not a failure — a shelf add is a tracking decision, not a call,
    and scoring it would reintroduce exactly the "is this a buy?" confusion
    the alert wording fix removed.
    """
    v = (verdict or "").strip().upper()
    if v in INTENT_LONG:
        return excess_pct >= 0.0
    if v in INTENT_REDUCE:
        return excess_pct < 0.0
    return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_rules.py -v`
Expected: PASS — 15 tests (parametrised).

- [ ] **Step 5: Commit**

```bash
git add core/audit/rules.py tests/unit/audit/test_audit_rules.py
git commit -m "feat(audit): benchmark-relative correctness rules"
```

---

### Task 4: The recorder — advice lane

Walks the advice ledger, finds matured horizons, marks prices, appends rows. Idempotent.

**Files:**
- Create: `core/audit/outcomes.py`
- Test: `tests/unit/audit/test_audit_outcomes.py`

**Interfaces:**
- Consumes: `AuditOutcomeStore` (Task 1), `BenchmarkSeries` + `trading_days_after` (Task 2), `pct_change`/`excess`/`is_correct` (Task 3).
- Produces:
  - `grade_advice_lane(on: date, user_id: str, *, store=None, bench=None, price_fn=None, base_dir=None) -> dict` returning `{"graded": int, "skipped_unpriceable": int, "already_present": int}`.
  - `_load_advice_rows(user_id: str, base_dir: str | None) -> list[dict]`
  - `HORIZONS: tuple[int, ...]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_outcomes.py`:

```python
import json
from datetime import date

from core.audit.outcomes import grade_advice_lane
from core.audit.store import AuditOutcomeStore


class _FakeBench:
    """Deterministic benchmark: +1% over any window that starts on the issue
    date. The 2026-07-02 boundary matches the price_fn fixtures below — it has
    to fall between issue (2026-07-01) and maturity (2026-07-15), or the
    benchmark never moves and every excess collapses to the raw return."""
    def close_on(self, d):
        return 100.0 if d < date(2026, 7, 2) else 101.0

    def pct_change(self, start, end):
        return round((self.close_on(end) / self.close_on(start) - 1.0) * 100.0, 4)


def _write_ledger(tmp_path, rows):
    d = tmp_path / "primary"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "advice_ledger.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _advice(date_str="2026-07-01", verdict="HOLD", close=100.0):
    return {
        "date": date_str, "user_id": "primary", "symbol": "MARUTI",
        "verdict": verdict, "close": close, "unrealised_pnl_pct": 0.0,
        "stop_pct": 8.0, "triggers": ["thesis_break"], "notes": [],
        "confidence": 0.6, "narrative": "", "switch_candidate": "",
        "rationale_hash": "abc123",
    }


def test_grades_matured_horizon_only(tmp_path):
    _write_ledger(tmp_path, [_advice()])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    # 2026-07-15 is ~10 trading days after 2026-07-01, not yet 30 or 60.
    result = grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path),
    )
    assert result["graded"] == 1
    rows = store.load_all()
    assert [r.horizon_td for r in rows] == [10]


def test_grading_is_idempotent(tmp_path):
    _write_ledger(tmp_path, [_advice()])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    kwargs = dict(store=store, bench=_FakeBench(),
                  price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path))
    first = grade_advice_lane(date(2026, 7, 15), "primary", **kwargs)
    second = grade_advice_lane(date(2026, 7, 15), "primary", **kwargs)
    assert first["graded"] == 1
    assert second["graded"] == 0 and second["already_present"] == 1
    assert len(store.load_all()) == 1


def test_hold_beating_benchmark_is_correct(tmp_path):
    _write_ledger(tmp_path, [_advice(verdict="HOLD", close=100.0)])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path),
    )
    row = store.load_all()[0]
    assert row.return_pct == 10.0 and row.bench_pct == 1.0
    assert row.excess_pct == 9.0 and row.correct is True


def test_exit_beating_benchmark_is_incorrect(tmp_path):
    _write_ledger(tmp_path, [_advice(verdict="EXIT", close=100.0)])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path),
    )
    assert store.load_all()[0].correct is False


def test_unpriceable_symbol_is_counted_not_fatal(tmp_path):
    def _boom(sym, d):
        raise RuntimeError("delisted")

    _write_ledger(tmp_path, [_advice()])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=_boom, base_dir=str(tmp_path),
    )
    assert result["graded"] == 0 and result["skipped_unpriceable"] == 1
    assert store.load_all() == []


def test_missing_ledger_returns_zeros(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path),
    )
    assert result == {"graded": 0, "skipped_unpriceable": 0, "already_present": 0}


def test_switch_records_the_candidate_excess(tmp_path):
    """A SWITCH is graded on whether the DESTINATION beat the ORIGIN, not
    merely on whether the origin fell (design section 5)."""
    row = _advice(verdict="SWITCH", close=100.0)
    row["switch_candidate"] = "M&M"
    _write_ledger(tmp_path, [row])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    prices = {"MARUTI": 110.0, "M&M": 130.0}
    grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: prices[sym] if d > date(2026, 7, 2) else 100.0,
        base_dir=str(tmp_path),
    )
    out = store.load_all()[0]
    assert out.excess_pct == 9.0            # MARUTI: +10% vs +1% bench
    assert out.switch_excess_pct == 29.0    # M&M:    +30% vs +1% bench


def test_switch_with_unpriceable_candidate_still_grades_the_origin(tmp_path):
    row = _advice(verdict="SWITCH", close=100.0)
    row["switch_candidate"] = "DELISTED"
    _write_ledger(tmp_path, [row])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))

    def _price(sym, d):
        if sym == "DELISTED":
            raise RuntimeError("no such symbol")
        return 110.0 if d > date(2026, 7, 2) else 100.0

    result = grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=_price, base_dir=str(tmp_path),
    )
    assert result["graded"] == 1
    out = store.load_all()[0]
    assert out.switch_excess_pct is None    # absent, not fatal
    assert out.correct is False             # origin rose: leaving was wrong
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_outcomes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.audit.outcomes'`.

- [ ] **Step 3: Write the implementation**

Create `core/audit/outcomes.py`:

```python
"""The recorder: turn matured calls into graded outcome rows.

Idempotent by (ref, horizon_td) — safe to run nightly, safe to re-run over all
history. Never raises: a bad row is counted and skipped, exactly like
emit_alerts and ops_alerts, because telemetry must not take down the pipeline
it watches.

`price_fn` is injected rather than imported at module level. core.portfolio.
pricing imports daily_review, which imports the feedback agent and weight
adapter — so a module-level import would load the graded components at import
time. The default is resolved lazily inside _default_price_fn.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from backend.shared.config.settings.loader import cfg
from backend.shared.schemas.audit import AuditOutcome
from core.audit.rules import excess, is_correct, pct_change
from core.config import settings
from core.intelligence.rl.nse_calendar import trading_days_after

logger = logging.getLogger(__name__)

HORIZONS: tuple[int, ...] = (10, 30, 60)


def _horizons() -> tuple[int, ...]:
    configured = cfg("audit.horizons_td", fallback=list(HORIZONS))
    try:
        return tuple(int(h) for h in configured)
    except Exception:
        return HORIZONS


def _default_price_fn(symbol: str, on: date) -> float:
    """Lazy import — see module docstring."""
    from core.portfolio.pricing import close_on
    return close_on(symbol, on)


def _user_dir(user_id: str, base_dir: str | None) -> Path:
    return Path(base_dir or settings.PORTFOLIO_DATA_DIR) / user_id


def _load_advice_rows(user_id: str, base_dir: str | None) -> list[dict]:
    path = _user_dir(user_id, base_dir) / "advice_ledger.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _switch_excess(
    row: dict, issued: date, matured: date, bench_pct: float,
    price_fn: Callable[[str, date], float],
) -> float | None:
    """Excess return of a SWITCH's destination over the same window.

    A SWITCH says "leave X for Y". Grading only whether X fell would call a
    switch correct even when Y fell further. Returns None when there is no
    candidate or it cannot be priced — absent, never fatal, because the
    origin's grade is still valid on its own.
    """
    candidate = (row.get("switch_candidate") or "").strip()
    if not candidate:
        return None
    try:
        entry = float(price_fn(candidate, issued))
        exit_close = float(price_fn(candidate, matured))
        return excess(pct_change(entry, exit_close), bench_pct)
    except Exception:
        return None


def grade_advice_lane(
    on: date,
    user_id: str,
    *,
    store=None,
    bench=None,
    price_fn: Callable[[str, date], float] | None = None,
    base_dir: str | None = None,
) -> dict:
    """Grade every advice row whose horizon has matured on or before `on`."""
    from core.audit.benchmark import BenchmarkSeries
    from core.audit.store import AuditOutcomeStore

    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    bench = bench or BenchmarkSeries()
    price_fn = price_fn or _default_price_fn

    seen = store.existing_keys()
    graded = skipped = already = 0

    for row in _load_advice_rows(user_id, base_dir):
        try:
            issued = date.fromisoformat(row["date"])
            symbol = row["symbol"]
            entry = float(row["close"])
            ref = f"{row['date']}|{symbol}|{row.get('rationale_hash', '')}"
        except Exception:
            skipped += 1
            continue

        for horizon in _horizons():
            if (ref, horizon) in seen:
                already += 1
                continue
            matured = trading_days_after(issued, horizon)
            if matured > on:
                continue
            try:
                exit_close = float(price_fn(symbol, matured))
                ret = pct_change(entry, exit_close)
                bench_pct = bench.pct_change(issued, matured)
                exc = excess(ret, bench_pct)
                outcome = AuditOutcome(
                    ref=ref, lane="advice", user_id=user_id, symbol=symbol,
                    verdict=row.get("verdict", ""),
                    triggers=list(row.get("triggers") or []),
                    issued_on=issued.isoformat(), horizon_td=horizon,
                    graded_on=matured.isoformat(),
                    entry_close=entry, exit_close=exit_close, return_pct=ret,
                    bench_entry=bench.close_on(issued),
                    bench_exit=bench.close_on(matured),
                    bench_pct=bench_pct, excess_pct=exc,
                    correct=is_correct(row.get("verdict", ""), exc),
                    graded_at=datetime.now(timezone.utc).isoformat(),
                    switch_excess_pct=_switch_excess(
                        row, issued, matured, bench_pct, price_fn),
                )
            except Exception as exc_err:
                logger.debug("[audit] %s @%dtd unpriceable (non-fatal): %s",
                             symbol, horizon, exc_err)
                skipped += 1
                continue
            store.append(outcome)
            seen.add((ref, horizon))
            graded += 1

    return {"graded": graded, "skipped_unpriceable": skipped,
            "already_present": already}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_outcomes.py -v`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add core/audit/outcomes.py tests/unit/audit/test_audit_outcomes.py
git commit -m "feat(audit): advice-lane outcome recorder, idempotent by (ref, horizon)"
```

---

### Task 5: Alert and shelf lanes

Alerts need a stable id first — the sent-log has none, so an advisor alert and its advice row would grade as two unrelated events.

**Files:**
- Modify: `core/delivery/alerts.py` (add `advice_ref` to `AlertEvent`, ~line 34-43)
- Modify: `core/portfolio/pipeline.py:158-168` (populate `advice_ref` on advisor alerts)
- Modify: `core/audit/outcomes.py` (add `grade_alert_lane`, `grade_shelf_lane`, `grade_due`)
- Test: `tests/unit/audit/test_audit_lanes.py`
- Test: `tests/unit/test_delivery_alerts.py` (append one test)

**Interfaces:**
- Consumes: everything from Task 4.
- Produces:
  - `AlertEvent.advice_ref: str = ""` — dedupe key deliberately unchanged.
  - `grade_alert_lane(on, user_id, *, store, bench, price_fn, base_dir, sent_log=None) -> dict`
  - `grade_shelf_lane(on, user_id, *, store, bench, price_fn, base_dir, shelf_path=None) -> dict`
  - `grade_due(on: date, user_id: str | None = None, **kw) -> dict` — sums all three lanes into `{"graded", "skipped_unpriceable", "already_present", "lanes": {...}}`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/audit/test_audit_lanes.py`:

```python
import json
from datetime import date

from core.audit.outcomes import grade_alert_lane, grade_due, grade_shelf_lane
from core.audit.store import AuditOutcomeStore


class _FakeBench:
    """+1% over any window starting on the 2026-07-01 issue date. The boundary
    must fall between issue and the 2026-07-15 maturity, or the benchmark never
    moves and excess collapses to the raw return."""
    def close_on(self, d):
        return 100.0 if d < date(2026, 7, 2) else 101.0

    def pct_change(self, start, end):
        return round((self.close_on(end) / self.close_on(start) - 1.0) * 100.0, 4)


def _write(tmp_path, name, rows, sub="primary"):
    d = tmp_path / sub
    d.mkdir(parents=True, exist_ok=True)
    with open(d / name, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return d / name


def test_alert_lane_grades_only_alerts_with_advice_ref(tmp_path):
    log = _write(tmp_path, "alerts_sent.jsonl", [
        {"date": "2026-07-01", "kind": "advisor_exit", "symbol": "MARUTI",
         "message": "m", "severity": "critical", "user_id": "primary",
         "delivered": True, "advice_ref": "2026-07-01|MARUTI|abc123"},
        {"date": "2026-07-01", "kind": "job_crashed_x", "symbol": "",
         "message": "m", "severity": "critical", "user_id": "primary",
         "delivered": True},
    ])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_alert_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda s, d: 110.0, base_dir=str(tmp_path), sent_log=str(log),
    )
    assert result["graded"] == 1          # the ops alert is not a prediction
    assert store.load_all()[0].lane == "alert"


def test_shelf_lane_records_conviction_and_never_scores_correct(tmp_path):
    shelf = tmp_path / "shelf.json"
    shelf.write_text(json.dumps({"ideas": [{
        "symbol": "APOLLOTYRE", "sector": "automobile", "graph": "generic",
        "added": "2026-07-01", "conviction": 0.71, "verdict": "", "thesis": "",
        "entry_low": 0.0, "entry_high": 0.0, "invalidation_level": 0.0,
        "close_at_add": 100.0, "status": "active", "paper_cycle_id": "",
        "last_paper_review": "", "source_screen_date": "",
    }], "updated_at": ""}), encoding="utf-8")
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_shelf_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda s, d: 110.0, base_dir=str(tmp_path),
        shelf_path=str(shelf),
    )
    assert result["graded"] == 1
    row = store.load_all()[0]
    assert row.lane == "shelf" and row.conviction == 0.71
    assert row.correct is None            # a shelf add is not a call
    assert row.excess_pct == 9.0          # but the return is still recorded


def test_grade_due_sums_all_lanes(tmp_path):
    _write(tmp_path, "advice_ledger.jsonl", [{
        "date": "2026-07-01", "user_id": "primary", "symbol": "MARUTI",
        "verdict": "HOLD", "close": 100.0, "unrealised_pnl_pct": 0.0,
        "stop_pct": 8.0, "triggers": [], "notes": [], "confidence": 0.6,
        "narrative": "", "switch_candidate": "", "rationale_hash": "abc123",
    }])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_due(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda s, d: 110.0, base_dir=str(tmp_path),
        sent_log=str(tmp_path / "missing.jsonl"),
        shelf_path=str(tmp_path / "missing.json"),
    )
    assert result["graded"] == 1
    assert set(result["lanes"]) == {"advice", "alert", "shelf"}


def test_grade_due_never_raises_on_broken_lane(tmp_path):
    """A dead benchmark must degrade the run, not crash the nightly job.

    The ledger row matters: without a gradeable row the lanes return early and
    never reach the benchmark, so the test would pass without proving anything.
    sent_log/shelf_path are pinned at absent paths to keep the test off the
    real data/delivery and data/discovery files.
    """
    _write(tmp_path, "advice_ledger.jsonl", [{
        "date": "2026-07-01", "user_id": "primary", "symbol": "MARUTI",
        "verdict": "HOLD", "close": 100.0, "unrealised_pnl_pct": 0.0,
        "stop_pct": 8.0, "triggers": [], "notes": [], "confidence": 0.6,
        "narrative": "", "switch_candidate": "", "rationale_hash": "abc123",
    }])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))

    class _Boom:
        def close_on(self, d):
            raise RuntimeError("benchmark down")

        def pct_change(self, start, end):
            raise RuntimeError("benchmark down")

    result = grade_due(
        date(2026, 7, 15), "primary", store=store, bench=_Boom(),
        price_fn=lambda s, d: 110.0, base_dir=str(tmp_path),
        sent_log=str(tmp_path / "missing.jsonl"),
        shelf_path=str(tmp_path / "missing.json"),
    )
    assert result["graded"] == 0     # degraded, not crashed
    assert result["skipped_unpriceable"] == 1
    assert store.load_all() == []
```

Append to `tests/unit/test_delivery_alerts.py`:

```python
def test_alert_event_advice_ref_defaults_empty_and_not_in_dedupe_key():
    from core.delivery.alerts import AlertEvent
    plain = AlertEvent(date="2026-07-17", kind="advisor_exit", symbol="MARUTI",
                       message="m", severity="warning")
    tagged = plain.model_copy(update={"advice_ref": "2026-07-17|MARUTI|abc"})
    assert plain.advice_ref == ""
    # dedupe must be unaffected — adding provenance must not re-notify
    assert plain.key() == tagged.key()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/audit/test_audit_lanes.py tests/unit/test_delivery_alerts.py -v`
Expected: FAIL — `ImportError: cannot import name 'grade_alert_lane'` and `advice_ref` attribute error.

- [ ] **Step 3: Add `advice_ref` to AlertEvent**

In `core/delivery/alerts.py`, replace the `AlertEvent` class body:

```python
class AlertEvent(BaseModel):
    date: str                              # ISO date the event refers to
    kind: str                              # advisor_exit | shelf_add | lockin_expiry | ...
    symbol: str = ""
    message: str
    severity: Literal["info", "warning", "critical"] = "info"
    # Verification layer (2026-08-07): links an alert back to the advice row
    # that produced it, so the auditor grades them as one event. Deliberately
    # NOT part of key() — dedupe behaviour must be unchanged by provenance.
    advice_ref: str = ""

    def key(self) -> str:
        return f"{self.date}|{self.kind}|{self.symbol}"
```

- [ ] **Step 4: Populate it on advisor alerts**

In `core/portfolio/pipeline.py`, in the `AlertEvent(` construction at line 158, add the `advice_ref` argument after `symbol=a.symbol,`:

```python
                    advice_ref=f"{review_date.isoformat()}|{a.symbol}|{a.rationale_hash}",
```

- [ ] **Step 5: Add the two lanes and the aggregator**

Append to `core/audit/outcomes.py`:

```python
def _load_alert_rows(sent_log: str | None) -> list[dict]:
    if sent_log:
        path = Path(sent_log)
    else:
        path = Path(settings.DELIVERY_DATA_DIR) / "alerts_sent.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _grade_one(
    *, ref, lane, user_id, symbol, verdict, triggers, issued, entry, horizon,
    matured, store, bench, price_fn, conviction=None,
) -> bool:
    """Mark one (ref, horizon) and append it. Returns True when a row was
    written. Never raises."""
    try:
        exit_close = float(price_fn(symbol, matured))
        ret = pct_change(entry, exit_close)
        bench_pct = bench.pct_change(issued, matured)
        exc = excess(ret, bench_pct)
        store.append(AuditOutcome(
            ref=ref, lane=lane, user_id=user_id, symbol=symbol,
            verdict=verdict, triggers=list(triggers or []),
            issued_on=issued.isoformat(), horizon_td=horizon,
            graded_on=matured.isoformat(), entry_close=entry,
            exit_close=exit_close, return_pct=ret,
            bench_entry=bench.close_on(issued),
            bench_exit=bench.close_on(matured),
            bench_pct=bench_pct, excess_pct=exc,
            correct=is_correct(verdict, exc),
            graded_at=datetime.now(timezone.utc).isoformat(),
            conviction=conviction,
        ))
        return True
    except Exception as exc_err:
        logger.debug("[audit] %s %s @%dtd ungradeable (non-fatal): %s",
                     lane, symbol, horizon, exc_err)
        return False


def grade_alert_lane(
    on: date, user_id: str, *, store=None, bench=None,
    price_fn: Callable[[str, date], float] | None = None,
    base_dir: str | None = None, sent_log: str | None = None,
) -> dict:
    """Grade alerts that carry an advice_ref. Ops alerts, index-watch and
    lock-in notices are NOT predictions and are never graded."""
    from core.audit.benchmark import BenchmarkSeries
    from core.audit.store import AuditOutcomeStore

    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    bench = bench or BenchmarkSeries()
    price_fn = price_fn or _default_price_fn

    seen = store.existing_keys()
    graded = skipped = already = 0

    for row in _load_alert_rows(sent_log):
        ref = (row.get("advice_ref") or "").strip()
        if not ref or row.get("user_id", "") != user_id:
            continue
        try:
            issued = date.fromisoformat(row["date"])
            symbol = row["symbol"]
        except Exception:
            skipped += 1
            continue
        for horizon in _horizons():
            akey = (f"alert:{ref}", horizon)
            if akey in seen:
                already += 1
                continue
            matured = trading_days_after(issued, horizon)
            if matured > on:
                continue
            try:
                entry = float(price_fn(symbol, issued))
            except Exception:
                skipped += 1
                continue
            ok = _grade_one(
                ref=f"alert:{ref}", lane="alert", user_id=user_id,
                symbol=symbol, verdict="", triggers=[row.get("kind", "")],
                issued=issued, entry=entry, horizon=horizon, matured=matured,
                store=store, bench=bench, price_fn=price_fn,
            )
            if ok:
                seen.add(akey)
                graded += 1
            else:
                skipped += 1

    return {"graded": graded, "skipped_unpriceable": skipped,
            "already_present": already}


def grade_shelf_lane(
    on: date, user_id: str, *, store=None, bench=None,
    price_fn: Callable[[str, date], float] | None = None,
    base_dir: str | None = None, shelf_path: str | None = None,
) -> dict:
    """Grade shelf ideas for conviction calibration. `correct` is always None:
    a shelf add is a research candidate, not a call."""
    from core.audit.benchmark import BenchmarkSeries
    from core.audit.store import AuditOutcomeStore

    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    bench = bench or BenchmarkSeries()
    price_fn = price_fn or _default_price_fn

    path = Path(shelf_path) if shelf_path else \
        Path(settings.DISCOVERY_DATA_DIR) / "shelf.json"
    if not path.exists():
        return {"graded": 0, "skipped_unpriceable": 0, "already_present": 0}
    try:
        ideas = json.loads(path.read_text(encoding="utf-8")).get("ideas", [])
    except Exception:
        return {"graded": 0, "skipped_unpriceable": 0, "already_present": 0}

    seen = store.existing_keys()
    graded = skipped = already = 0

    for idea in ideas:
        try:
            issued = date.fromisoformat(idea["added"])
            symbol = idea["symbol"]
            entry = float(idea["close_at_add"])
            conviction = float(idea.get("conviction", 0.0))
        except Exception:
            skipped += 1
            continue
        if entry <= 0:
            skipped += 1
            continue
        ref = f"shelf:{idea['added']}|{symbol}"
        for horizon in _horizons():
            if (ref, horizon) in seen:
                already += 1
                continue
            matured = trading_days_after(issued, horizon)
            if matured > on:
                continue
            ok = _grade_one(
                ref=ref, lane="shelf", user_id=user_id, symbol=symbol,
                verdict="", triggers=[], issued=issued, entry=entry,
                horizon=horizon, matured=matured, store=store, bench=bench,
                price_fn=price_fn, conviction=conviction,
            )
            if ok:
                seen.add((ref, horizon))
                graded += 1
            else:
                skipped += 1

    return {"graded": graded, "skipped_unpriceable": skipped,
            "already_present": already}


def grade_due(on: date, user_id: str | None = None, **kw) -> dict:
    """Grade all three lanes. A failure in one lane never stops the others."""
    uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID
    lanes: dict[str, dict] = {}
    for name, fn in (("advice", grade_advice_lane),
                     ("alert", grade_alert_lane),
                     ("shelf", grade_shelf_lane)):
        allowed = {k: v for k, v in kw.items()
                   if k in _LANE_KWARGS[name] or k in _COMMON_KWARGS}
        try:
            lanes[name] = fn(on, uid, **allowed)
        except Exception as exc:
            logger.warning("[audit] %s lane failed (non-fatal): %s", name, exc)
            lanes[name] = {"graded": 0, "skipped_unpriceable": 0,
                           "already_present": 0, "error": str(exc)}
    return {
        "graded": sum(l.get("graded", 0) for l in lanes.values()),
        "skipped_unpriceable": sum(l.get("skipped_unpriceable", 0) for l in lanes.values()),
        "already_present": sum(l.get("already_present", 0) for l in lanes.values()),
        "lanes": lanes,
    }


_COMMON_KWARGS = {"store", "bench", "price_fn", "base_dir"}
_LANE_KWARGS = {"advice": set(), "alert": {"sent_log"}, "shelf": {"shelf_path"}}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/audit/ tests/unit/test_delivery_alerts.py -v`
Expected: PASS.

- [ ] **Step 7: Verify no regression in the alert and pipeline suites**

Run: `python -m pytest tests/unit/test_delivery_alerts.py tests/unit/test_alerts_wave_f.py tests/unit/test_portfolio_pipeline.py -q`
Expected: PASS. `advice_ref` is additive with a default, and `key()` is unchanged, so dedupe behaviour is identical.

- [ ] **Step 8: Commit**

```bash
git add core/audit/outcomes.py core/delivery/alerts.py core/portfolio/pipeline.py \
        tests/unit/audit/test_audit_lanes.py tests/unit/test_delivery_alerts.py
git commit -m "feat(audit): alert and shelf lanes, advice_ref linkage on alerts"
```

---

### Task 6: Aggregate metrics — hit-rate, per-trigger precision, coin-flip test

Pure functions over outcome rows. This is where every claim the auditor makes is computed.

**Files:**
- Create: `core/audit/metrics.py`
- Test: `tests/unit/audit/test_audit_metrics.py`

**Interfaces:**
- Consumes: `AuditOutcome` (Task 1).
- Produces:
  - `Rate` NamedTuple: `(n: int, value: float | None, lo: float | None, hi: float | None)`
  - `hit_rate(rows, horizon=None, verdict=None) -> Rate`
  - `per_trigger_precision(rows, horizon=None) -> dict[str, Rate]`
  - `coin_flip_p(rows, horizon=None) -> float | None`
  - `mean_excess(rows, horizon=None) -> float | None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_metrics.py`:

```python
from backend.shared.schemas.audit import AuditOutcome
from core.audit.metrics import (
    coin_flip_p, hit_rate, mean_excess, per_trigger_precision,
)


def _row(correct=True, horizon=30, verdict="HOLD", triggers=(), excess=1.0,
         lane="advice"):
    return AuditOutcome(
        ref=f"r{id(triggers)}{correct}{horizon}{excess}", lane=lane,
        user_id="primary", symbol="MARUTI", verdict=verdict,
        triggers=list(triggers), issued_on="2026-07-01", horizon_td=horizon,
        graded_on="2026-08-14", entry_close=100.0, exit_close=110.0,
        return_pct=10.0, bench_entry=100.0, bench_exit=101.0, bench_pct=1.0,
        excess_pct=excess, correct=correct, graded_at="2026-08-14T00:00:00Z",
    )


def test_hit_rate_counts_only_scored_rows():
    rows = [_row(True), _row(False), _row(None, lane="shelf", verdict="")]
    r = hit_rate(rows)
    assert r.n == 2 and r.value == 0.5


def test_hit_rate_empty_returns_none_not_zero():
    r = hit_rate([])
    assert r.n == 0 and r.value is None


def test_hit_rate_filters_by_horizon_and_verdict():
    rows = [_row(True, horizon=10), _row(False, horizon=30),
            _row(True, horizon=30, verdict="EXIT")]
    assert hit_rate(rows, horizon=30).n == 2
    assert hit_rate(rows, horizon=30, verdict="EXIT").value == 1.0


def test_hit_rate_reports_wilson_interval():
    r = hit_rate([_row(True) for _ in range(10)])
    assert r.value == 1.0
    assert r.lo is not None and r.lo < 1.0     # interval is not degenerate
    assert r.hi == 1.0


def test_per_trigger_precision_groups_by_trigger():
    rows = [
        _row(True, triggers=("thesis_break",)),
        _row(False, triggers=("thesis_break",)),
        _row(True, triggers=("stop_breach",)),
    ]
    out = per_trigger_precision(rows)
    assert out["thesis_break"].n == 2 and out["thesis_break"].value == 0.5
    assert out["stop_breach"].n == 1


def test_row_with_two_triggers_counts_under_both():
    out = per_trigger_precision([_row(True, triggers=("thesis_break", "stop_breach"))])
    assert out["thesis_break"].n == 1 and out["stop_breach"].n == 1


def test_coin_flip_p_is_one_for_a_perfect_split():
    rows = [_row(True), _row(False)]
    assert coin_flip_p(rows) == 1.0


def test_coin_flip_p_is_small_for_a_lopsided_result():
    rows = [_row(True) for _ in range(20)]
    p = coin_flip_p(rows)
    assert p is not None and p < 0.001


def test_coin_flip_p_none_without_rows():
    assert coin_flip_p([]) is None


def test_mean_excess_averages_percentage_points():
    assert mean_excess([_row(excess=2.0), _row(excess=4.0)]) == 3.0
    assert mean_excess([]) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.audit.metrics'`.

- [ ] **Step 3: Write the implementation**

Create `core/audit/metrics.py`:

```python
"""Pure metrics over graded outcome rows. Lists in, numbers out, no I/O.

Every function reports its own `n` and returns None rather than a number when
there is nothing to compute — a fresh install must read INSUFFICIENT_DATA,
never "0% hit rate".

wilson_interval and sign_test_p are reused from the Learning Evidence report
rather than reimplemented: two auditors must not disagree about what a
confidence interval is.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

from backend.shared.schemas.audit import AuditOutcome
from core.intelligence.rl.eval.learning_evidence import sign_test_p, wilson_interval


class Rate(NamedTuple):
    n: int
    value: float | None          # None when n == 0
    lo: float | None             # Wilson 95% lower bound
    hi: float | None             # Wilson 95% upper bound


_EMPTY = Rate(0, None, None, None)


def _scored(
    rows: Iterable[AuditOutcome],
    horizon: int | None = None,
    verdict: str | None = None,
) -> list[AuditOutcome]:
    """Rows that carry a real True/False. Shelf rows (correct=None) are
    excluded everywhere — they were never calls."""
    out = []
    for r in rows:
        if r.correct is None:
            continue
        if horizon is not None and r.horizon_td != horizon:
            continue
        if verdict is not None and r.verdict.strip().upper() != verdict.strip().upper():
            continue
        out.append(r)
    return out


def hit_rate(
    rows: Iterable[AuditOutcome],
    horizon: int | None = None,
    verdict: str | None = None,
) -> Rate:
    scored = _scored(rows, horizon, verdict)
    if not scored:
        return _EMPTY
    hits = sum(1 for r in scored if r.correct)
    lo, hi = wilson_interval(hits, len(scored))
    return Rate(len(scored), hits / len(scored), round(lo, 4), round(hi, 4))


def per_trigger_precision(
    rows: Iterable[AuditOutcome], horizon: int | None = None
) -> dict[str, Rate]:
    """Hit-rate grouped by advisor trigger. A row with two triggers counts
    under both — the question is "when this rule fires, how often is the call
    right?", per rule."""
    buckets: dict[str, list[AuditOutcome]] = {}
    for r in _scored(rows, horizon):
        for trigger in r.triggers:
            t = (trigger or "").strip()
            if t:
                buckets.setdefault(t, []).append(r)
    return {t: hit_rate(rs) for t, rs in sorted(buckets.items())}


def coin_flip_p(
    rows: Iterable[AuditOutcome], horizon: int | None = None
) -> float | None:
    """Exact two-sided sign test of the hit-rate against 50%."""
    scored = _scored(rows, horizon)
    if not scored:
        return None
    hits = sum(1 for r in scored if r.correct)
    return sign_test_p(hits, len(scored))


def mean_excess(
    rows: Iterable[AuditOutcome], horizon: int | None = None
) -> float | None:
    """Average excess return in percentage points. Includes shelf rows: they
    have no verdict but they do have a return."""
    vals = [r.excess_pct for r in rows
            if horizon is None or r.horizon_td == horizon]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_metrics.py -v`
Expected: PASS — 10 tests.

- [ ] **Step 5: Commit**

```bash
git add core/audit/metrics.py tests/unit/audit/test_audit_metrics.py
git commit -m "feat(audit): hit-rate, per-trigger precision and coin-flip metrics"
```

---

### Task 7: Conviction calibration and portfolio-vs-benchmark

The two metrics that answer questions nothing in the codebase has ever asked.

**Files:**
- Modify: `core/audit/metrics.py` (append)
- Test: `tests/unit/audit/test_audit_calibration.py`

**Interfaces:**
- Consumes: `Rate`, `_scored` (Task 6).
- Produces:
  - `conviction_calibration(rows, horizon=30, buckets=5) -> list[dict]` — each `{"lo": float, "hi": float, "n": int, "mean_excess": float}`
  - `calibration_spread(buckets) -> float | None`
  - `portfolio_vs_benchmark(history: list[dict], bench_pct: float) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_calibration.py`:

```python
from backend.shared.schemas.audit import AuditOutcome
from core.audit.metrics import (
    calibration_spread, conviction_calibration, portfolio_vs_benchmark,
)


def _shelf(conviction, excess, horizon=30):
    return AuditOutcome(
        ref=f"shelf:{conviction}:{excess}", lane="shelf", user_id="primary",
        symbol="X", verdict="", triggers=[], issued_on="2026-07-01",
        horizon_td=horizon, graded_on="2026-08-14", entry_close=100.0,
        exit_close=110.0, return_pct=10.0, bench_entry=100.0,
        bench_exit=101.0, bench_pct=1.0, excess_pct=excess, correct=None,
        graded_at="2026-08-14T00:00:00Z", conviction=conviction,
    )


def test_calibration_buckets_by_conviction():
    rows = [_shelf(0.1, -5.0), _shelf(0.2, -3.0), _shelf(0.9, 6.0), _shelf(0.8, 4.0)]
    buckets = conviction_calibration(rows, horizon=30, buckets=2)
    assert len(buckets) == 2
    assert buckets[0]["mean_excess"] == -4.0     # low conviction
    assert buckets[-1]["mean_excess"] == 5.0     # high conviction


def test_calibration_ignores_non_shelf_rows():
    advice = _shelf(0.5, 1.0).model_copy(update={"lane": "advice", "conviction": None})
    assert conviction_calibration([advice], horizon=30) == []


def test_calibration_empty_returns_empty_list():
    assert conviction_calibration([], horizon=30) == []


def test_spread_is_top_minus_bottom_populated_bucket():
    rows = [_shelf(0.1, -4.0), _shelf(0.9, 5.0)]
    buckets = conviction_calibration(rows, horizon=30, buckets=2)
    assert calibration_spread(buckets) == 9.0


def test_spread_none_when_fewer_than_two_populated_buckets():
    buckets = conviction_calibration([_shelf(0.9, 5.0)], horizon=30, buckets=2)
    assert calibration_spread(buckets) is None


def test_portfolio_vs_benchmark_reports_excess():
    history = [
        {"date": "2026-06-01", "market_value": 100000.0},
        {"date": "2026-08-01", "market_value": 112000.0},
    ]
    out = portfolio_vs_benchmark(history, bench_pct=5.0)
    assert out["portfolio_pct"] == 12.0
    assert out["bench_pct"] == 5.0
    assert out["excess_pct"] == 7.0


def test_portfolio_vs_benchmark_needs_two_points():
    out = portfolio_vs_benchmark([{"date": "2026-06-01", "market_value": 1.0}], 5.0)
    assert out["portfolio_pct"] is None and out["excess_pct"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_calibration.py -v`
Expected: FAIL — `ImportError: cannot import name 'conviction_calibration'`.

- [ ] **Step 3: Write the implementation**

Append to `core/audit/metrics.py`:

```python
def conviction_calibration(
    rows: Iterable[AuditOutcome], horizon: int = 30, buckets: int = 5
) -> list[dict]:
    """Shelf ideas bucketed by conviction against realized excess return.

    The question nothing has ever asked: does a 0.9-conviction idea actually
    beat a 0.4-conviction idea? A flat curve means conviction carries no
    information and the discovery floor is arbitrary.

    Buckets span [0, 1] evenly; empty buckets are omitted.
    """
    scored = [r for r in rows
              if r.lane == "shelf" and r.conviction is not None
              and r.horizon_td == horizon]
    if not scored or buckets <= 0:
        return []

    width = 1.0 / buckets
    grouped: dict[int, list[AuditOutcome]] = {}
    for r in scored:
        idx = min(int(max(0.0, min(1.0, r.conviction)) / width), buckets - 1)
        grouped.setdefault(idx, []).append(r)

    out: list[dict] = []
    for idx in sorted(grouped):
        rs = grouped[idx]
        out.append({
            "lo": round(idx * width, 4),
            "hi": round((idx + 1) * width, 4),
            "n": len(rs),
            "mean_excess": round(sum(r.excess_pct for r in rs) / len(rs), 4),
        })
    return out


def calibration_spread(buckets: list[dict]) -> float | None:
    """Top populated bucket's mean excess minus the bottom's. None below two
    populated buckets — a single bucket says nothing about ordering."""
    if len(buckets) < 2:
        return None
    return round(buckets[-1]["mean_excess"] - buckets[0]["mean_excess"], 4)


def portfolio_vs_benchmark(history: list[dict], bench_pct: float) -> dict:
    """Equity-curve return vs the index over the same span.

    `history` is value_history.jsonl rows, ascending by date, each carrying
    "market_value". Needs at least two points to describe a change.
    """
    points = [h for h in history if isinstance(h.get("market_value"), (int, float))]
    if len(points) < 2:
        return {"portfolio_pct": None, "bench_pct": bench_pct,
                "excess_pct": None, "n": len(points)}
    first = float(points[0]["market_value"])
    last = float(points[-1]["market_value"])
    if first <= 0:
        return {"portfolio_pct": None, "bench_pct": bench_pct,
                "excess_pct": None, "n": len(points)}
    portfolio_pct = round((last / first - 1.0) * 100.0, 4)
    return {
        "portfolio_pct": portfolio_pct,
        "bench_pct": bench_pct,
        "excess_pct": round(portfolio_pct - bench_pct, 4),
        "n": len(points),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_calibration.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add core/audit/metrics.py tests/unit/audit/test_audit_calibration.py
git commit -m "feat(audit): conviction calibration and portfolio-vs-benchmark metrics"
```

---

### Task 8: Report assembly and the verdict vocabulary

Turns metrics into the single verdict word and the payload every surface shares.

**Files:**
- Create: `core/audit/report.py`
- Test: `tests/unit/audit/test_audit_report.py`

**Interfaces:**
- Consumes: all of `metrics.py` (Tasks 6-7), `AuditOutcomeStore` (Task 1).
- Produces:
  - `VERDICTS: tuple[str, ...]`
  - `classify(rate, p_value, mean_excess_pct, min_n) -> str`
  - `build_report(user_id=None, *, store=None, min_n=None) -> dict`
  - `render_section(report: dict) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_report.py`:

```python
from backend.shared.schemas.audit import AuditOutcome
from core.audit.metrics import Rate
from core.audit.report import build_report, classify, render_section
from core.audit.store import AuditOutcomeStore


def _row(correct=True, horizon=60, excess=2.0, i=0):
    return AuditOutcome(
        ref=f"r{i}", lane="advice", user_id="primary", symbol="MARUTI",
        verdict="HOLD", triggers=["thesis_break"], issued_on="2026-07-01",
        horizon_td=horizon, graded_on="2026-08-14", entry_close=100.0,
        exit_close=110.0, return_pct=10.0, bench_entry=100.0,
        bench_exit=101.0, bench_pct=1.0, excess_pct=excess, correct=correct,
        graded_at="2026-08-14T00:00:00Z",
    )


def test_classify_insufficient_below_min_n():
    assert classify(Rate(5, 0.9, 0.6, 1.0), 0.01, 3.0, min_n=30) == "INSUFFICIENT_DATA"


def test_classify_below_coin_flip():
    assert classify(Rate(40, 0.30, 0.2, 0.45), 0.004, -2.0, min_n=30) == "BELOW_COIN_FLIP"


def test_classify_beats_benchmark():
    assert classify(Rate(40, 0.72, 0.6, 0.85), 0.004, 3.0, min_n=30) == "BEATS_BENCHMARK"


def test_classify_unproven_when_not_significant():
    assert classify(Rate(40, 0.55, 0.4, 0.7), 0.42, 0.4, min_n=30) == "UNPROVEN"


def test_classify_empty_is_insufficient():
    assert classify(Rate(0, None, None, None), None, None, min_n=30) == "INSUFFICIENT_DATA"


def test_build_report_on_empty_store_says_insufficient(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    report = build_report("primary", store=store)
    assert report["verdict"] == "INSUFFICIENT_DATA"
    assert report["total_rows"] == 0
    assert report["hit_rate"]["60"]["n"] == 0


def test_build_report_populates_horizons_and_triggers(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    for i in range(40):
        store.append(_row(correct=(i % 4 != 0), i=i))
    report = build_report("primary", store=store, min_n=30)
    assert report["total_rows"] == 40
    assert report["hit_rate"]["60"]["n"] == 40
    assert report["per_trigger"]["thesis_break"]["n"] == 40
    assert report["verdict"] in ("BEATS_BENCHMARK", "UNPROVEN")


def test_render_section_is_plain_text_with_the_verdict(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    text = render_section(build_report("primary", store=store))
    assert "INSUFFICIENT_DATA" in text
    assert "Advice outcomes" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.audit.report'`.

- [ ] **Step 3: Write the implementation**

Create `core/audit/report.py`:

```python
"""Report assembly — metrics into one verdict word and one shared payload.

The verdict vocabulary deliberately mirrors the Learning Evidence report's, so
two auditors never use the same word for different things.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.shared.config.settings.loader import cfg
from core.audit.metrics import (
    Rate, calibration_spread, coin_flip_p, conviction_calibration, hit_rate,
    mean_excess, per_trigger_precision,
)

logger = logging.getLogger(__name__)

VERDICTS = ("INSUFFICIENT_DATA", "BELOW_COIN_FLIP", "UNPROVEN", "BEATS_BENCHMARK")

# Two-sided significance level for the coin-flip call — matches
# learning_evidence.SIGNIFICANCE_LEVEL so the two reports agree.
SIGNIFICANCE_LEVEL = 0.10

_HORIZONS = (10, 30, 60)


def _rate_dict(r: Rate) -> dict:
    return {"n": r.n, "value": r.value, "lo": r.lo, "hi": r.hi}


def classify(
    rate: Rate, p_value: float | None, mean_excess_pct: float | None, min_n: int,
) -> str:
    """The single word. Conservative by construction: anything unclear is
    UNPROVEN, and anything thin is INSUFFICIENT_DATA."""
    if rate.n < min_n or rate.value is None or p_value is None:
        return "INSUFFICIENT_DATA"
    if p_value <= SIGNIFICANCE_LEVEL and rate.value < 0.5:
        return "BELOW_COIN_FLIP"
    if p_value <= SIGNIFICANCE_LEVEL and rate.value > 0.5 \
            and (mean_excess_pct or 0.0) > 0.0:
        return "BEATS_BENCHMARK"
    return "UNPROVEN"


def build_report(user_id: str | None = None, *, store=None, min_n: int | None = None) -> dict:
    """The payload every surface shares: nightly alerts, monthly email, API."""
    from core.audit.store import AuditOutcomeStore

    store = store or AuditOutcomeStore(user_id=user_id)
    rows = store.load_all()
    floor = int(min_n if min_n is not None else cfg("audit.min_n", fallback=30))

    headline_horizon = 60
    headline = hit_rate(rows, horizon=headline_horizon)
    p = coin_flip_p(rows, horizon=headline_horizon)
    excess_60 = mean_excess(rows, horizon=headline_horizon)
    buckets = conviction_calibration(rows, horizon=30)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": store.user_id,
        "total_rows": len(rows),
        "min_n": floor,
        "headline_horizon_td": headline_horizon,
        "verdict": classify(headline, p, excess_60, floor),
        "coin_flip_p": p,
        "hit_rate": {str(h): _rate_dict(hit_rate(rows, horizon=h)) for h in _HORIZONS},
        "mean_excess_pct": {str(h): mean_excess(rows, horizon=h) for h in _HORIZONS},
        "per_trigger": {t: _rate_dict(r)
                        for t, r in per_trigger_precision(rows, horizon=headline_horizon).items()},
        "conviction_calibration": buckets,
        "conviction_spread": calibration_spread(buckets),
    }


def render_section(report: dict) -> str:
    """Plain-text block for the monthly Learning Evidence email."""
    lines = [
        "",
        "=" * 62,
        "Advice outcomes — verification layer",
        "=" * 62,
        f"Verdict: {report['verdict']}   "
        f"(n={report['total_rows']} rows, floor={report['min_n']})",
        "",
        "Hit-rate vs NIFTY 50, by horizon:",
    ]
    for horizon in ("10", "30", "60"):
        r = report["hit_rate"].get(horizon, {})
        if not r.get("n"):
            lines.append(f"  {horizon:>3}td   no matured rows yet")
            continue
        lines.append(
            f"  {horizon:>3}td   {r['value']:.1%}  "
            f"[{r['lo']:.1%}–{r['hi']:.1%}]   n={r['n']}"
        )
    lines.append("")
    if report["per_trigger"]:
        lines.append("Per-trigger precision (60td):")
        for trigger, r in report["per_trigger"].items():
            lines.append(f"  {trigger:<24} {r['value']:.1%}  n={r['n']}")
        lines.append("")
    spread = report.get("conviction_spread")
    if spread is None:
        lines.append("Conviction calibration: not enough populated buckets yet.")
    else:
        lines.append(
            f"Conviction calibration: top-minus-bottom decile spread "
            f"{spread:+.2f}pp (flat ⇒ conviction carries no information)."
        )
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_report.py -v`
Expected: PASS — 8 tests.

- [ ] **Step 5: Commit**

```bash
git add core/audit/report.py tests/unit/audit/test_audit_report.py
git commit -m "feat(audit): report assembly and verdict classification"
```

---

### Task 9: Config keys and breach alerts

**Files:**
- Modify: `config.yaml` (new top-level `audit:` block, after `atlas:` at line 477)
- Create: `core/audit/thresholds.py`
- Test: `tests/unit/audit/test_audit_thresholds.py`

**Interfaces:**
- Consumes: `build_report` (Task 8).
- Produces: `evaluate_breaches(report: dict, *, news_blind_rate: float | None = None) -> list[dict]` and `emit_breaches(breaches: list[dict]) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_thresholds.py`:

```python
from unittest.mock import patch

import core.audit.thresholds as th


def _report(verdict="UNPROVEN", hit60=0.60, n=40, spread=3.0):
    return {
        "verdict": verdict, "min_n": 30, "total_rows": n,
        "hit_rate": {"60": {"n": n, "value": hit60, "lo": 0.4, "hi": 0.8}},
        "conviction_spread": spread,
    }


def test_low_hit_rate_breaches():
    with patch.object(th, "_cfg", side_effect=lambda k, d: {"audit.min_hit_rate_60d": 0.45}.get(k, d)):
        breaches = th.evaluate_breaches(_report(hit60=0.30))
    assert any(b["rule"] == "min_hit_rate_60d" for b in breaches)


def test_healthy_report_produces_no_breaches():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        assert th.evaluate_breaches(_report(hit60=0.62, spread=4.0)) == []


def test_thin_sample_never_breaches_hit_rate():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        breaches = th.evaluate_breaches(_report(hit60=0.10, n=5))
    assert not any(b["rule"] == "min_hit_rate_60d" for b in breaches)


def test_flat_conviction_breaches_at_info_severity():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        breaches = th.evaluate_breaches(_report(spread=0.1))
    flat = [b for b in breaches if b["rule"] == "conviction_flat_spread"]
    assert flat and flat[0]["severity"] == "info"


def test_news_blind_rate_breaches():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        breaches = th.evaluate_breaches(_report(), news_blind_rate=0.60)
    assert any(b["rule"] == "max_news_blind_rate" for b in breaches)


def test_news_blind_rate_none_is_not_a_breach():
    with patch.object(th, "_cfg", side_effect=lambda k, d: d):
        breaches = th.evaluate_breaches(_report(), news_blind_rate=None)
    assert not any(b["rule"] == "max_news_blind_rate" for b in breaches)


def test_emit_is_silenced_by_kill_switch():
    with patch.object(th, "_cfg", side_effect=lambda k, d: False if k == "audit.alerts_enabled" else d):
        with patch.object(th, "emit_alerts_broadcast") as m:
            out = th.emit_breaches([{"rule": "min_hit_rate_60d", "severity": "warning",
                                     "message": "m"}])
    assert m.call_count == 0 and out["emitted"] == 0


def test_emit_sends_one_batch():
    with patch.object(th, "_cfg", side_effect=lambda k, d: True if k == "audit.alerts_enabled" else d):
        with patch.object(th, "emit_alerts_broadcast", return_value={"emitted": 1}) as m:
            out = th.emit_breaches([{"rule": "min_hit_rate_60d", "severity": "warning",
                                     "message": "m"}])
    assert m.call_count == 1 and out["emitted"] == 1


def test_emit_nothing_when_no_breaches():
    with patch.object(th, "emit_alerts_broadcast") as m:
        assert th.emit_breaches([])["emitted"] == 0
    assert m.call_count == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_thresholds.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.audit.thresholds'`.

- [ ] **Step 3: Add the config block**

In `config.yaml`, after the `atlas:` block (which begins at line 477) and before `universe:`, insert:

```yaml
# ---------------------------------------------------------------------------
# Verification layer — the deterministic auditor (design 2026-08-07).
# Read-only: these tunables change what it REPORTS and ALERTS on, never what
# the system decides. No env= on any of them (config.yaml is the sole source).
# ---------------------------------------------------------------------------
audit:
  enabled: true                # master switch for the nightly grading job
  alerts_enabled: true         # kill-switch for breach alerts only
  benchmark_ticker: "^NSEI"    # NIFTY 50 — the benchmark `correct` is defined against
  horizons_td: [10, 30, 60]    # trading days after issue
  min_n: 30                    # below this, every verdict is INSUFFICIENT_DATA
  min_hit_rate_60d: 0.45       # 60td hit-rate floor before a warning fires
  max_bench_lag_pct: 10.0      # portfolio trailing NIFTY by more than this over 60d
  max_news_blind_rate: 0.20    # F1's blind-rate ceiling — currently log-only
  conviction_flat_spread: 1.0  # top-minus-bottom decile spread, in pp
```

- [ ] **Step 4: Write the implementation**

Create `core/audit/thresholds.py`:

```python
"""Breach rules — the Gap F fix.

ops_alerts catches jobs that produce nothing or crash. It cannot see a job that
produces FULL output that is silently wrong, which is exactly what the
2026-07-30 news-blind incident was. These rules watch for that class: the
system still running, still confident, and no longer right.

Read-only and advisory. A breach notifies a human; nothing here halts autopilot
or overrides advice.
"""
from __future__ import annotations

import logging
from datetime import date

from backend.shared.config.settings.loader import cfg
from core.delivery.alerts import AlertEvent, emit_alerts_broadcast

logger = logging.getLogger(__name__)


def _cfg(key: str, default):
    """Indirection so tests can patch one function instead of the loader."""
    return cfg(key, fallback=default)


def evaluate_breaches(
    report: dict, *, news_blind_rate: float | None = None,
) -> list[dict]:
    """Rules over a built report. Pure apart from cfg reads; never raises."""
    breaches: list[dict] = []

    min_n = int(report.get("min_n") or 30)
    hit60 = (report.get("hit_rate") or {}).get("60") or {}
    floor = float(_cfg("audit.min_hit_rate_60d", 0.45))
    if hit60.get("n", 0) >= min_n and hit60.get("value") is not None \
            and hit60["value"] < floor:
        breaches.append({
            "rule": "min_hit_rate_60d",
            "severity": "warning",
            "message": (
                f"60-trading-day hit-rate vs NIFTY is {hit60['value']:.1%} "
                f"(floor {floor:.0%}) over n={hit60['n']} graded calls."
            ),
        })

    lag_cap = float(_cfg("audit.max_bench_lag_pct", 10.0))
    lag = report.get("portfolio_excess_pct")
    if lag is not None and lag < -abs(lag_cap):
        breaches.append({
            "rule": "max_bench_lag_pct",
            "severity": "warning",
            "message": (
                f"Portfolio trails NIFTY by {abs(lag):.1f}pp over the tracked "
                f"window (cap {lag_cap:.0f}pp)."
            ),
        })

    blind_cap = float(_cfg("audit.max_news_blind_rate", 0.20))
    if news_blind_rate is not None and news_blind_rate > blind_cap:
        breaches.append({
            "rule": "max_news_blind_rate",
            "severity": "warning",
            "message": (
                f"News-blind rate is {news_blind_rate:.0%} (ceiling "
                f"{blind_cap:.0%}) — reviews are running without company news, "
                "which contaminates miss attribution."
            ),
        })

    spread_floor = float(_cfg("audit.conviction_flat_spread", 1.0))
    spread = report.get("conviction_spread")
    if spread is not None and spread < spread_floor:
        breaches.append({
            "rule": "conviction_flat_spread",
            "severity": "info",
            "message": (
                f"Conviction decile spread is {spread:+.2f}pp (floor "
                f"{spread_floor:.2f}pp) — high-conviction shelf ideas are not "
                "outperforming low-conviction ones."
            ),
        })

    return breaches


def emit_breaches(breaches: list[dict]) -> dict:
    """One bundled alert batch. Never raises."""
    if not breaches:
        return {"emitted": 0}
    if not bool(_cfg("audit.alerts_enabled", True)):
        logger.info("[audit] %d breach(es) suppressed — audit.alerts_enabled=false",
                    len(breaches))
        return {"emitted": 0, "suppressed": len(breaches)}
    try:
        today = date.today().isoformat()
        events = [
            AlertEvent(date=today, kind=f"audit_{b['rule']}", symbol="",
                       message=b["message"], severity=b["severity"])
            for b in breaches
        ]
        return emit_alerts_broadcast(events, title="StockAgent verification")
    except Exception as exc:
        logger.warning("[audit] breach emit failed (non-fatal): %s", exc)
        return {"emitted": 0, "error": str(exc)}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_thresholds.py -v`
Expected: PASS — 9 tests.

- [ ] **Step 6: Commit**

```bash
git add config.yaml core/audit/thresholds.py tests/unit/audit/test_audit_thresholds.py
git commit -m "feat(audit): breach thresholds and config keys"
```

---

### Task 10: Nightly scheduler job

**Files:**
- Modify: `services/scheduler/python/scheduler.py` (register job after `atlas_retention` at line 449; add `_audit_nightly_job` method)
- Test: `tests/unit/audit/test_audit_scheduler_job.py`

**Interfaces:**
- Consumes: `grade_due` (Task 5), `build_report` (Task 8), `evaluate_breaches`/`emit_breaches` (Task 9), `alert_job_partial_output` (existing, `core/delivery/ops_alerts.py:105`).
- Produces: `StockAgentScheduler._audit_nightly_job() -> None`, job id `audit_nightly`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_scheduler_job.py`:

```python
from unittest.mock import patch

import services.scheduler.python.scheduler as sched


def _scheduler():
    return sched.AutomobileScheduler()


def test_job_grades_then_evaluates_then_emits():
    s = _scheduler()
    with patch.object(sched, "grade_due", return_value={"graded": 3, "lanes": {}}) as g, \
         patch.object(sched, "build_audit_report", return_value={"verdict": "UNPROVEN"}) as b, \
         patch.object(sched, "evaluate_breaches", return_value=[{"rule": "r", "severity": "info", "message": "m"}]) as e, \
         patch.object(sched, "emit_breaches", return_value={"emitted": 1}) as m:
        s._audit_nightly_job()
    assert g.call_count == 1 and b.call_count == 1
    assert e.call_count == 1 and m.call_count == 1


def test_job_never_raises_when_grading_fails():
    s = _scheduler()
    with patch.object(sched, "grade_due", side_effect=RuntimeError("prices down")), \
         patch.object(sched, "emit_breaches") as m:
        s._audit_nightly_job()      # must not raise
    assert m.call_count == 0


def test_job_reports_partial_output_to_the_watchdog():
    """The auditor is itself watched: a run where prices failed must surface
    as a partial output, not as a quietly smaller report."""
    s = _scheduler()
    with patch.object(sched, "grade_due",
                      return_value={"graded": 8, "skipped_unpriceable": 4,
                                    "already_present": 0, "lanes": {}}), \
         patch.object(sched, "build_audit_report", return_value={"verdict": "UNPROVEN"}), \
         patch.object(sched, "evaluate_breaches", return_value=[]), \
         patch("core.delivery.ops_alerts.alert_job_partial_output") as w:
        s._audit_nightly_job()
    w.assert_called_once_with("audit_nightly", 8, 12)


def test_job_is_registered_in_the_scheduler_source():
    """Static check: start() needs a live event loop, so assert on the source
    the scheduler actually registers rather than standing one up."""
    import re
    from pathlib import Path
    src = Path(sched.__file__).read_text(encoding="utf-8")
    assert 'id="audit_nightly"' in src
    assert "audit.enabled" in src        # gated by the master switch
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_scheduler_job.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'grade_due'`.

- [ ] **Step 3: Add the module-level imports**

In `services/scheduler/python/scheduler.py`, near the other `core.` imports at the top of the file, add:

```python
from core.audit.outcomes import grade_due
from core.audit.report import build_report as build_audit_report
from core.audit.thresholds import emit_breaches, evaluate_breaches
```

`cfg` is **not** currently imported in this module (the file uses
`getattr(settings, "X_ENABLED", True)` elsewhere). Add it — the audit switch
must go through config.yaml per the global constraints:

```python
from backend.shared.config.settings.loader import cfg
```

Do **not** add a module-level `ops_alerts` import. Every existing watchdog call
in this file imports it lazily inside the function (lines 511, 662, 669, 1029);
the audit job follows that idiom, and its test patches at the source module
accordingly.

- [ ] **Step 4: Register the job**

In the same file, immediately after the `atlas_retention` `scheduler.add_job(...)` block (line ~449-460), add:

```python
        # ── Verification layer: nightly grading + breach check (23:45 IST) ──
        # After atlas_retention so the day's ledgers have settled. Read-only
        # over the learning stack — it can never contaminate a validation run.
        if cfg("audit.enabled", fallback=True):
            scheduler.add_job(
                func=self._audit_nightly_job,
                trigger=CronTrigger(hour=23, minute=45, timezone="Asia/Kolkata"),
                id="audit_nightly",
                name="Nightly advice-outcome grading + breach check",
                misfire_grace_time=3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Audit job: nightly at 11:45 pm IST")
        else:
            logger.info("[Scheduler] Audit job disabled (audit.enabled=false)")
```

- [ ] **Step 5: Add the job method**

Add this method to the scheduler class, next to `_scorecard_monthly_job`:

```python
    def _audit_nightly_job(self) -> None:
        """Grade matured calls, then check the breach rules.

        Never raises: the auditor must not be able to take down the scheduler
        it shares a process with.
        """
        from datetime import date as _d
        _job_banner("Audit — nightly grading")
        try:
            summary = grade_due(_d.today())
            logger.info("[Scheduler] audit graded %s row(s): %s",
                        summary.get("graded"), summary.get("lanes"))
            # The auditor is itself watched (design section 8.1). "Expected" is
            # the rows that SHOULD have graded — matured and attempted — so a
            # run where prices are failing surfaces as a partial output rather
            # than as a quietly smaller report. Rows not yet matured are not
            # counted: they are not a failure.
            from core.delivery.ops_alerts import alert_job_partial_output
            produced = int(summary.get("graded", 0))
            expected = produced + int(summary.get("skipped_unpriceable", 0))
            alert_job_partial_output("audit_nightly", produced, expected)
        except Exception as exc:
            logger.warning("[Scheduler] audit grading failed: %s", exc, exc_info=True)
            _job_banner("Audit — nightly grading", done=True)
            return

        try:
            report = build_audit_report()
            breaches = evaluate_breaches(report)
            if breaches:
                logger.warning("[Scheduler] audit breaches: %s",
                               [b["rule"] for b in breaches])
                emit_breaches(breaches)
            else:
                logger.info("[Scheduler] audit verdict %s — no breaches",
                            report.get("verdict"))
        except Exception as exc:
            logger.warning("[Scheduler] audit breach check failed: %s", exc, exc_info=True)
        _job_banner("Audit — nightly grading", done=True)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_scheduler_job.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 7: Verify the scheduler suite still passes**

Run: `python -m pytest tests/unit/ -k scheduler -q`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add services/scheduler/python/scheduler.py tests/unit/audit/test_audit_scheduler_job.py
git commit -m "feat(audit): nightly grading and breach-check scheduler job"
```

---

### Task 11: Monthly email section

**Files:**
- Modify: `services/scheduler/python/scheduler.py` (`_scorecard_monthly_job`, the Learning Evidence block at lines ~974-995)
- Test: `tests/unit/audit/test_audit_monthly_section.py`

**Interfaces:**
- Consumes: `build_audit_report`, `render_section` (Task 8).
- Produces: no new symbols — the audit section is appended to the existing email body.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_monthly_section.py`:

```python
from unittest.mock import patch

import services.scheduler.python.scheduler as sched


def test_audit_section_is_appended_to_the_learning_evidence_email():
    s = sched.StockAgentScheduler()
    sent = {}

    def _capture(subject, body):
        sent["subject"], sent["body"] = subject, body

    with patch.object(sched, "build_scorecard", return_value={}), \
         patch.object(sched, "save_scorecard", return_value="/tmp/x.json"), \
         patch("core.intelligence.rl.eval.learning_evidence.build_learning_evidence",
               return_value={"verdict": "UNPROVEN"}), \
         patch("core.intelligence.rl.eval.learning_evidence.render_report",
               return_value="LEARNING EVIDENCE BODY"), \
         patch("core.intelligence.rl.eval.learning_evidence.save_report",
               return_value=("/tmp/a.json", "/tmp/a.txt")), \
         patch("core.delivery.channels.send_email", side_effect=_capture), \
         patch.object(sched, "build_audit_report",
                      return_value={"verdict": "INSUFFICIENT_DATA", "total_rows": 0,
                                    "min_n": 30, "hit_rate": {}, "per_trigger": {},
                                    "conviction_spread": None}), \
         patch.object(sched, "render_audit_section", return_value="AUDIT SECTION"):
        s._scorecard_monthly_job()

    assert "LEARNING EVIDENCE BODY" in sent["body"]
    assert "AUDIT SECTION" in sent["body"]


def test_audit_section_failure_does_not_lose_the_learning_evidence_email():
    s = sched.StockAgentScheduler()
    sent = {}

    with patch.object(sched, "build_scorecard", return_value={}), \
         patch.object(sched, "save_scorecard", return_value="/tmp/x.json"), \
         patch("core.intelligence.rl.eval.learning_evidence.build_learning_evidence",
               return_value={"verdict": "UNPROVEN"}), \
         patch("core.intelligence.rl.eval.learning_evidence.render_report",
               return_value="LEARNING EVIDENCE BODY"), \
         patch("core.intelligence.rl.eval.learning_evidence.save_report",
               return_value=("/tmp/a.json", "/tmp/a.txt")), \
         patch("core.delivery.channels.send_email",
               side_effect=lambda subject, body: sent.update(body=body)), \
         patch.object(sched, "build_audit_report", side_effect=RuntimeError("boom")):
        s._scorecard_monthly_job()

    assert "LEARNING EVIDENCE BODY" in sent["body"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_monthly_section.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'render_audit_section'`.

- [ ] **Step 3: Add the import**

In `services/scheduler/python/scheduler.py`, extend the audit import line added in Task 10:

```python
from core.audit.report import build_report as build_audit_report
from core.audit.report import render_section as render_audit_section
```

- [ ] **Step 4: Append the section to the email body**

In `_scorecard_monthly_job`, replace the `send_email(...)` call inside the Learning Evidence `try` block with:

```python
            body = render_report(report)
            # Verification layer (2026-08-07): the money-side auditor rides the
            # same envelope — one monthly report, not two. A failure here must
            # never cost us the Learning Evidence email.
            try:
                body += render_audit_section(build_audit_report())
            except Exception as audit_exc:
                logger.warning("[Scheduler] audit section failed (non-fatal): %s",
                               audit_exc)
            send_email(
                subject=f"[StockAgent] Learning Evidence {month}: {report['verdict']}",
                body=body,
            )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_monthly_section.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 6: Commit**

```bash
git add services/scheduler/python/scheduler.py tests/unit/audit/test_audit_monthly_section.py
git commit -m "feat(audit): fold the audit section into the monthly Learning Evidence email"
```

---

### Task 12: API — summary and backfill

**Files:**
- Create: `services/api/routes/audit_api.py`
- Modify: `services/api/server.py` (import + `include_router`, near line 474)
- Test: `tests/unit/audit/test_audit_api.py`

**Interfaces:**
- Consumes: `build_report` (Task 8), `grade_due` (Task 5).
- Produces: `GET /audit/summary`, `POST /audit/backfill`, `router` exported as `audit_router`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_api.py`:

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

import services.api.routes.audit_api as aapi


def _client():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(aapi.router)
    app.dependency_overrides[aapi.get_current_user] = lambda: {"user_id": "primary"}
    app.dependency_overrides[aapi.require_owner] = lambda: {"user_id": "primary"}
    return TestClient(app)


def test_summary_on_empty_store_is_insufficient_not_zero():
    with patch.object(aapi, "build_report",
                      return_value={"verdict": "INSUFFICIENT_DATA", "total_rows": 0}):
        resp = _client().get("/audit/summary")
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "INSUFFICIENT_DATA"


def test_backfill_returns_counts_not_a_bare_200():
    with patch.object(aapi, "grade_due",
                      return_value={"graded": 12, "skipped_unpriceable": 1,
                                    "already_present": 3, "lanes": {}}):
        resp = _client().post("/audit/backfill")
    body = resp.json()
    assert resp.status_code == 200
    assert body["graded"] == 12 and body["skipped_unpriceable"] == 1
    assert body["already_present"] == 3


def test_backfill_refuses_to_run_concurrently():
    aapi._BACKFILL_RUNNING.set()
    try:
        resp = _client().post("/audit/backfill")
    finally:
        aapi._BACKFILL_RUNNING.clear()
    assert resp.status_code == 409


def test_backfill_clears_its_guard_even_on_failure():
    with patch.object(aapi, "grade_due", side_effect=RuntimeError("boom")):
        resp = _client().post("/audit/backfill")
    assert resp.status_code == 500
    assert not aapi._BACKFILL_RUNNING.is_set()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.api.routes.audit_api'`.

- [ ] **Step 3: Write the router**

Create `services/api/routes/audit_api.py`:

```python
"""
services/api/routes/audit_api.py
=================================
Verification layer REST surface (design 2026-08-07 sections 8-9).

GET  /audit/summary    Graded-outcome report: hit-rate by horizon, per-trigger
                       precision, conviction calibration, verdict.
POST /audit/backfill   Grade all matured history. Owner-only, idempotent,
                       single-flight. This is how the backfill runs on prod,
                       where the real ledger lives and `railway ssh` is not
                       available.

Read-only over the learning stack — nothing here mutates weights, lessons or
the portfolio.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from core.audit.outcomes import grade_due
from core.audit.report import build_report
from services.api.auth import get_current_user, require_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit")

# Single-flight guard: a backfill re-prices thousands of rows and two
# concurrent runs would double the price fetches for no benefit. Idempotency
# means a rejected second call loses nothing.
_BACKFILL_RUNNING = threading.Event()


@router.get("/summary", summary="Graded advice-outcome report")
async def audit_summary(user: dict = Depends(get_current_user)) -> dict:
    return await asyncio.to_thread(build_report, user["user_id"])


@router.post("/backfill", summary="Grade all matured history (owner-only)")
async def audit_backfill(user: dict = Depends(require_owner)) -> dict:
    if _BACKFILL_RUNNING.is_set():
        raise HTTPException(status_code=409, detail="a backfill is already running")
    _BACKFILL_RUNNING.set()
    try:
        result = await asyncio.to_thread(grade_due, date.today(), user["user_id"])
    except Exception as exc:
        logger.warning("[audit_api] backfill failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"backfill failed: {exc}")
    finally:
        _BACKFILL_RUNNING.clear()
    logger.info("[audit_api] backfill complete: %s", result)
    return result
```

- [ ] **Step 4: Register the router**

In `services/api/server.py`, add the import alongside the other route imports:

```python
from services.api.routes.audit_api import router as audit_router
```

and register it after `rl_monitor_router` (line ~474):

```python
app.include_router(audit_router,     tags=["Audit"])
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_api.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 6: Verify the app still boots**

Run: `python -c "from services.api.server import app; print(sorted({r.path for r in app.routes if r.path.startswith('/audit')}))"`
Expected: `['/audit/backfill', '/audit/summary']`

- [ ] **Step 7: Commit**

```bash
git add services/api/routes/audit_api.py services/api/server.py \
        tests/unit/audit/test_audit_api.py
git commit -m "feat(audit): GET /audit/summary and owner-only POST /audit/backfill"
```

---

### Task 13: CLI, deprecate the dead fields, full-suite gate

Closes the loop on the finding that started this: the three schema fields nobody ever wrote.

**Files:**
- Create: `core/audit/cli.py`
- Modify: `src/backend/shared/schemas/portfolio.py:96-115` (deprecation comment)
- Modify: `services/data/stores/atlas_store.py:172-174` (deprecation comment)
- Test: `tests/unit/audit/test_audit_cli.py`

**Interfaces:**
- Consumes: `grade_due` (Task 5), `build_report`/`render_section` (Task 8).
- Produces: `python -m core.audit.cli --backfill | --report [--user U]`, `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_cli.py`:

```python
from unittest.mock import patch

import core.audit.cli as cli


def test_report_flag_prints_the_section(capsys):
    with patch.object(cli, "build_report", return_value={"verdict": "INSUFFICIENT_DATA"}), \
         patch.object(cli, "render_section", return_value="SECTION TEXT"):
        rc = cli.main(["--report"])
    assert rc == 0
    assert "SECTION TEXT" in capsys.readouterr().out


def test_backfill_flag_prints_counts(capsys):
    with patch.object(cli, "grade_due",
                      return_value={"graded": 7, "skipped_unpriceable": 0,
                                    "already_present": 2, "lanes": {}}):
        rc = cli.main(["--backfill"])
    assert rc == 0
    assert "7" in capsys.readouterr().out


def test_no_flag_is_an_error(capsys):
    assert cli.main([]) == 2


def test_backfill_failure_returns_nonzero(capsys):
    with patch.object(cli, "grade_due", side_effect=RuntimeError("prices down")):
        assert cli.main(["--backfill"]) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.audit.cli'`.

- [ ] **Step 3: Write the CLI**

Create `core/audit/cli.py`:

```python
"""Command-line entry point for the verification layer.

    python -m core.audit.cli --report
    python -m core.audit.cli --backfill [--user primary]

On prod the backfill is normally driven through POST /audit/backfill; this CLI
exists for local runs and for a shell on the volume if one becomes available.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

from core.audit.outcomes import grade_due
from core.audit.report import build_report, render_section

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="core.audit.cli")
    parser.add_argument("--backfill", action="store_true",
                        help="grade every matured call in all history")
    parser.add_argument("--report", action="store_true",
                        help="print the current graded-outcome report")
    parser.add_argument("--user", default=None, help="user_id (default: owner)")
    args = parser.parse_args(argv)

    if not (args.backfill or args.report):
        parser.print_usage(sys.stderr)
        print("error: pass --backfill or --report", file=sys.stderr)
        return 2

    if args.backfill:
        try:
            result = grade_due(date.today(), args.user)
        except Exception as exc:
            print(f"backfill failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))

    if args.report:
        try:
            print(render_section(build_report(args.user)))
        except Exception as exc:
            print(f"report failed: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":       # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
```

- [ ] **Step 4: Deprecate the dead fields**

In `src/backend/shared/schemas/portfolio.py`, replace the `AdviceRecord` docstring and the three outcome fields:

```python
class AdviceRecord(BaseModel):
    """One advice-ledger line (append-only JSONL).

    DEPRECATED FIELDS: outcome_10td / outcome_30td / outcome_60td were added
    for a "Phase D review machinery" that was never built — nothing has ever
    written them, so every row in every ledger carries NULL. They are kept for
    ledger-parsing compatibility and MUST NOT be used as a data source.

    Graded outcomes live in data/portfolio/<user>/advice_outcomes.jsonl, keyed
    by "<date>|<symbol>|<rationale_hash>" — see core/audit/ and
    docs/superpowers/specs/2026-08-07-verification-layer-design.md. The ledger
    is deliberately never rewritten: grading is derived data and derived data
    must not be able to corrupt the record of what the user was told.
    """
```

and immediately above the three fields:

```python
    # DEPRECATED — never written by anything. See the class docstring.
    outcome_10td: float | None = None
    outcome_30td: float | None = None
    outcome_60td: float | None = None
```

In `services/data/stores/atlas_store.py`, above line 172, add:

```sql
  -- DEPRECATED: never populated. Graded outcomes live in
  -- advice_outcomes.jsonl (core/audit/). Kept so the ETL keeps parsing.
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_cli.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 6: Run the whole audit package and the touched suites**

Run: `python -m pytest tests/unit/audit/ -v`
Expected: PASS — all tasks' tests together.

Run: `python -m pytest tests/unit/test_atlas_etl.py tests/unit/test_portfolio_store.py tests/unit/test_delivery_weekly.py -q`
Expected: PASS. The deprecation edits are comments and docstrings only.

- [ ] **Step 7: Full-suite gate**

Run: `python -m pytest tests/unit/ -q`
Expected: PASS. Baseline before this branch was 2167P/0F on `tests/unit`. Any failure here is new and must be fixed before merging — do not accept a red suite.

- [ ] **Step 8: Commit**

```bash
git add core/audit/cli.py src/backend/shared/schemas/portfolio.py \
        services/data/stores/atlas_store.py tests/unit/audit/test_audit_cli.py
git commit -m "feat(audit): backfill/report CLI; deprecate the never-written outcome_*td fields"
```

---

## Post-implementation

Not tasks — the human steps that follow a green suite.

1. **Do not push during 16:25–17:15 IST on a trading day.** Standing deploy-kill rule.
2. Push `verification-layer`, deploy, confirm `/health` is 200 and the boot log shows `[Scheduler] Audit job: nightly at 11:45 pm IST`.
3. Run the backfill once against prod: `POST /audit/backfill` with the owner session. Record `graded` / `skipped_unpriceable` / `already_present`.
4. Read `GET /audit/summary`. **Expect `INSUFFICIENT_DATA` on the first run** — 60-trading-day horizons need advice issued at least 60 trading days ago, and `min_n` is 30. That is a correct answer, not a bug.
5. Watch the first nightly run for breach-alert noise. If `conviction_flat_spread` fires immediately on thin data, raise `audit.min_n` rather than muting the rule.
