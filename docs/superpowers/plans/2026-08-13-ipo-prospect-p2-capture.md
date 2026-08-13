# PI "Prospect" — P2 "Capture" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start permanently recording the per-issue demand signals that only exist while an IPO window is open, so P3 has a forward dataset to train on — and surface the observed facts in the brief so the capture is self-verifying.

**Architecture:** P0 already fetches the full category bid ladder (QIB→FII/DomFI/MutualFund) and `cutoff_share` on every open issue, then throws all of it away. P2 keeps it: a new append-only ledger (`core/ipo/signals.py`) receives one snapshot per issue per refresh pass, pure derivations (`core/ipo/velocity.py`) read that ledger, and the brief renders the observed composition. Two P0 defects that would silently destroy the capture are fixed as prerequisites. GMP is built as an independent fetcher but gated behind its own API key and ships dark — measured Serper headroom is 80–300 calls/month, not the 2,300 originally assumed.

**Tech Stack:** Python 3.13, pydantic v2 schemas, APScheduler (`CronTrigger`, IST), pytest, the `nse` package via `services/data/fetchers/nse_client.py`, `core/utils/atomic_io.py`.

**Spec:** `docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md` — **§5 P2** is the scoped phase this plan implements; **§11** is the verified NSE data contract and remains the authority for every field name below.

## Global Constraints

- **Config over hardcode.** Every tunable goes through `cfg("...")` in `src/backend/shared/config/settings/base.py` with the value in `config.yaml`. No magic numbers in logic.
- **No `env=` for non-secret toggles.** Every `cfg()` call in this plan takes **no** `env=` parameter. The **sole exception** is `SERPER_API_KEY_IPO`, which is a *secret* and is read with `os.getenv` alongside the other API keys — that is the carve-out in the no-env-for-toggles rule, not a violation of it.
- **Never raise into delivery.** Every fetcher and every brief/weekly helper catches broadly and returns an empty/degraded value, matching the existing `logger.warning("[x] ... (non-fatal): %s", exc)` pattern. A dead IPO feed must never break a morning brief.
- **Dark-signal pattern.** A missing sub-signal is `None` and is omitted from rendering — **never defaulted to zero**. Zero asserts "nobody bid", which is a different and sometimes inverted claim (see `_reject_placeholder_total` in `ipo_bids.py`).
- **No derived value enters the ledger.** `ipo_signals.jsonl` stores captured facts only. Every ratio, delta and index is computed at read time. Same discipline as the P1 spine.
- **Research framing.** All user-visible IPO copy stays "the tool's research view — not advice". No output may read as a recommendation to apply.
- **Zero new API calls.** While `ipo.gmp_enabled: false`, this phase must not add a single Serper call and must not change the number of NSE calls per refresh. Task 8 asserts this with a test.
- **Commit per task**, message style `feat(ipo): ...` / `fix(ipo): ...` / `test(ipo): ...`, ending with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Test discipline.** Run the **targeted** tests named in each step before that step's commit. Run the **full** suite (`python -m pytest tests/unit -q`) where a task explicitly says so. The full suite takes ~4m15s, which is why it is not run before every commit.
- **Baseline: 2460 passed, 5 skipped, 0 failed** on `main` @ `8275dcf`. Any failure you see is yours; do not "fix" a pre-existing one.
- **Windows/OneDrive note.** The repo lives on a OneDrive-synced path where a file being rewritten can be briefly locked. Prefer append (`"a"` mode) over rewrite; where a rewrite is unavoidable, write to `.tmp` and `Path.replace()`, the pattern already used in `IpoHistoryStore.upsert` and `refresh_ipo_cache`.
- **Outside pytest**, scripts need `PYTHONPATH=".;src"` on Windows.

---

## File Structure

**Created**

| Path | Responsibility |
|---|---|
| `core/ipo/signals.py` | `IpoSignalSnapshot` model + `IpoSignalStore` — the append-only capture ledger |
| `core/ipo/velocity.py` | Pure derivations over one symbol's snapshots. No scores. |
| `services/data/fetchers/ipo_gmp.py` | GMP via a dedicated Serper key; returns `None` and spends nothing when unkeyed |
| `services/data/fetchers/ipo_offer.py` | OFS / fresh-issue split parsed out of the `issueInfo` free text |
| `tests/unit/test_ipo_signals.py` | Ledger round-trip, dedup, corrupt-line tolerance, prune bounds |
| `tests/unit/test_ipo_velocity.py` | Delta maths, single-snapshot → `None`, out-of-order input |
| `tests/unit/test_ipo_gmp.py` | The quota gate, the ≥2-source rule, disagreement → `None` |
| `tests/unit/test_ipo_offer.py` | `issueInfo` parsing against real strings from the Task 1 spike |

**Modified**

| Path | Change |
|---|---|
| `services/data/fetchers/ipo.py` | Carry ladder fields forward (Task 3); append a snapshot per pass (Task 4) |
| `core/ipo/history.py` | `ofs_share` field + `upsert_many` (Task 9) |
| `core/delivery/brief.py` | `_ipo_demand` renders the institutional split, cut-off share, and demand delta (Task 6) |
| `core/delivery/weekly.py` | Same line in the digest (Task 6) |
| `services/scheduler/python/scheduler.py` | PM refresh slot moves to 17:45 (Task 7) |
| `core/ops/watchdog/checks.py` | New `ipo_signals_accruing` invariant (Task 10) |
| `config/milestones.yaml` | Register that invariant (Task 10) |
| `config.yaml` | `ipo.signals_enabled`, `gmp_enabled`, `gmp_min_sources`, `gmp_agreement_tolerance`, `signal_retention_days`, `refresh_minute_live`; `refresh_hour_live` 18 → 17 |
| `src/backend/shared/config/settings/base.py` | Mirroring `IPO_*` settings + `SERPER_API_KEY_IPO` |
| `scripts/ipo_backfill.py` | `--ofs` enrichment pass (Task 9) |
| `tests/unit/test_ipo_bids.py` | Positive-value assertions for `combined["total"]` and `dom_fi` (Task 2) |
| `tests/unit/test_ipo_fetcher.py` | Carry-forward regression + snapshot-append wiring (Tasks 3, 4) |
| `tests/unit/test_delivery_brief.py` | Extended `_ipo_demand` cases (Task 6) |

---

## Task 1: Spike — does `issueInfo` carry the OFS split for past symbols?

**This is a spike. Its output is an answer and a fixture, not shipped code.** It mirrors P0's Task 1, which is why the P0 build started from a known contract instead of a guess.

The question: `/api/ipo-detail?symbol=X&series=EQ` carries an `issueInfo` block. §11.2 records it as free text containing the OFS vs fresh-issue split. **Unverified for symbols that listed months ago.** If past symbols do not carry it, OFS cannot be backfilled against the P1 spine, Task 9 collapses to forward-only, and that must be reported rather than papered over.

**Files:**
- Create: `/tmp`-equivalent scratch only — nothing in the repo except the fixture in Step 4.

**Interfaces:**
- Consumes: nothing.
- Produces: a verdict (`issueInfo` present / absent / partial for past symbols) and, if present, a captured real payload saved as a test fixture for Task 9.

- [ ] **Step 1: Probe three symbols of different vintages**

NSE calls are free but throttled; `nse._req()` applies the process-wide mthrottle. Use it, never `_session.get()`.

```bash
PYTHONPATH=".;src" python -c "
import json
from services.data.fetchers.nse_client import nse_session
# One recent, one mid-window, one at the far edge of the P1 spine (2024-05).
for sym in ('MOLBIO', 'INDGN', 'IGIL'):
    with nse_session() as nse:
        try:
            body = nse._req('https://www.nseindia.com/api/ipo-detail',
                            params={'symbol': sym, 'series': 'EQ'}).json()
        except Exception as exc:
            print(sym, 'FETCH FAILED', exc); continue
    info = body.get('issueInfo')
    print('===', sym, 'issueInfo type:', type(info).__name__)
    print(json.dumps(info, indent=2)[:1500] if info else '  ABSENT')
"
```

- [ ] **Step 2: Record the verdict**

Write the answer down in the task notes before writing any parser:
- Is `issueInfo` present for all three, some, or none?
- Does it name the OFS and fresh-issue amounts, and in what units (shares? ₹ crore?)?
- Is it a dict of labelled fields or one prose string?

- [ ] **Step 3: Decide Task 9's fate, out loud**

- **Present on all three** → Task 9 proceeds as written (backfill + forward).
- **Present only on recent symbols** → Task 9 ships the parser and the forward path; the backfill is limited to whatever vintage carries it, and the plan's claim of a 206-row OFS column is **corrected in the spec**, not quietly dropped.
- **Absent everywhere** → Task 9 is cut from P2 entirely. Say so, edit spec §5 P2, and stop. Do not build a parser for a field that is not there.

- [ ] **Step 4: If present, save one real payload as a fixture**

```bash
PYTHONPATH=".;src" python -c "
import json
from services.data.fetchers.nse_client import nse_session
with nse_session() as nse:
    body = nse._req('https://www.nseindia.com/api/ipo-detail',
                    params={'symbol': 'MOLBIO', 'series': 'EQ'}).json()
open('tests/fixtures/ipo_detail_molbio.json','w',encoding='utf-8').write(
    json.dumps({'issueInfo': body.get('issueInfo')}, indent=2))
print('saved')
"
```

Only `issueInfo` is saved — the full payload is large and the ladder is already fixtured in `test_ipo_bids.py`.

- [ ] **Step 5: Commit the fixture (only if Step 4 ran)**

```bash
git add tests/fixtures/ipo_detail_molbio.json
git commit -m "test(ipo): capture a real issueInfo payload for the OFS parser

Spike result for P2 Task 1 — see the plan for the verdict on whether past
symbols carry the OFS/fresh split.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: The capture ledger

**Files:**
- Create: `core/ipo/signals.py`
- Create: `tests/unit/test_ipo_signals.py`
- Modify: `tests/unit/test_ipo_bids.py` (add the positive-value assertions §9b flagged)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `IpoSignalSnapshot` (pydantic model) with fields `symbol: str`, `captured_at: str`, `state: str`, `issue_start: str`, `issue_end: str`, `combined: dict[str, float | None]`, `nse_only: dict[str, float | None]`, `cutoff_share: float | None`, `gmp: float | None`, `gmp_pct: float | None`, `gmp_sources: int`, `news_volume: int | None`
  - `IpoSignalStore(base_dir: str | None = None)` with `path -> Path`, `append(snap: IpoSignalSnapshot) -> bool`, `load_all() -> list[IpoSignalSnapshot]`, `load_symbol(symbol: str) -> list[IpoSignalSnapshot]`, `prune(older_than_days: int, now: datetime | None = None) -> int`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ipo_signals.py`:

```python
import json
from datetime import datetime, timedelta, timezone

from core.ipo.signals import IpoSignalSnapshot, IpoSignalStore


def _snap(symbol="MOLBIO", captured_at="2026-08-13T08:00:00+00:00", total=2.05):
    return IpoSignalSnapshot(
        symbol=symbol,
        captured_at=captured_at,
        state="open",
        issue_start="2026-08-10",
        issue_end="2026-08-13",
        combined={"qib": 1.39, "fii": 0.9, "dom_fi": 0.2,
                  "mutual_fund": 0.3, "nii": 3.6, "retail": 4.1,
                  "employee": None, "total": total},
        nse_only={"qib": 0.564, "total": 1.2},
        cutoff_share=0.4633,
    )


def test_append_then_load_round_trips(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    assert store.append(_snap()) is True
    rows = store.load_all()
    assert len(rows) == 1
    assert rows[0].symbol == "MOLBIO"
    assert rows[0].combined["dom_fi"] == 0.2
    assert rows[0].cutoff_share == 0.4633


def test_same_symbol_and_hour_is_deduped(tmp_path):
    """A manual re-run of the refresh must not double-count demand."""
    store = IpoSignalStore(base_dir=str(tmp_path))
    assert store.append(_snap(captured_at="2026-08-13T08:00:00+00:00")) is True
    assert store.append(_snap(captured_at="2026-08-13T08:41:12+00:00")) is False
    assert len(store.load_all()) == 1


def test_a_different_hour_is_a_new_snapshot(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    store.append(_snap(captured_at="2026-08-13T08:00:00+00:00"))
    assert store.append(_snap(captured_at="2026-08-13T12:15:00+00:00")) is True
    assert len(store.load_all()) == 2


def test_a_corrupt_line_never_breaks_a_read(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    store.append(_snap())
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")
    store.append(_snap(captured_at="2026-08-13T18:00:00+00:00"))
    assert len(store.load_all()) == 2


def test_load_symbol_filters_and_sorts_oldest_first(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    store.append(_snap(captured_at="2026-08-13T18:00:00+00:00"))
    store.append(_snap(captured_at="2026-08-13T08:00:00+00:00"))
    store.append(_snap(symbol="DHOOTTRANS", captured_at="2026-08-13T08:00:00+00:00"))
    rows = store.load_symbol("MOLBIO")
    assert [r.captured_at for r in rows] == [
        "2026-08-13T08:00:00+00:00", "2026-08-13T18:00:00+00:00"]


def test_prune_drops_only_rows_older_than_the_window(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    store.append(_snap(captured_at=(now - timedelta(days=500)).isoformat()))
    store.append(_snap(captured_at=(now - timedelta(days=10)).isoformat()))
    assert store.prune(older_than_days=400, now=now) == 1
    assert len(store.load_all()) == 1


def test_prune_with_a_wide_window_is_a_no_op(tmp_path):
    """Guards the one code path that can delete captured data."""
    store = IpoSignalStore(base_dir=str(tmp_path))
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    store.append(_snap(captured_at=(now - timedelta(days=10)).isoformat()))
    before = store.path.read_bytes()
    assert store.prune(older_than_days=400, now=now) == 0
    assert store.path.read_bytes() == before


def test_a_naive_timestamp_is_treated_as_utc_not_crashed_on(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    store.append(_snap(captured_at="2026-08-13T08:00:00"))
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    assert store.prune(older_than_days=400, now=now) == 0
    assert len(store.load_all()) == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/unit/test_ipo_signals.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'core.ipo.signals'`

- [ ] **Step 3: Write the implementation**

Create `core/ipo/signals.py`:

```python
"""PI Prospect P2 — the capture ledger (design §5 P2).

One row per (IPO, refresh pass) recording what NSE reported at that moment.
Perishable by nature: the bid ladder of an issue that closed last Tuesday is
not retrievable in its intermediate states, so a pass that is not captured is
gone for good.

Deliberately dumb, exactly like the P1 spine: captured facts only, no ratio,
delta or index anywhere in the file. Everything derived lives in velocity.py
and is recomputed on read, so a change to the maths never requires rewriting
history.

APPEND-ONLY, with one exception. `prune()` is the only writer that rewrites
the file, it is bounded by age, and its no-op case is asserted in the tests —
because the one way to lose this data is a rewrite path that misbehaves.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IpoSignalSnapshot(BaseModel):
    symbol: str
    captured_at: str                    # ISO-8601, UTC
    state: str = "unknown"              # core.ipo.calendar.issue_state output
    issue_start: str = ""
    issue_end: str = ""

    # Both ladders, named for what they are. `combined` is all-exchange and is
    # the figure the market quotes; `nse_only` under-reports. See spec §11.4.
    combined: dict[str, float | None] = Field(default_factory=dict)
    nse_only: dict[str, float | None] = Field(default_factory=dict)
    cutoff_share: float | None = None

    # Populated only when a dedicated Serper key exists (Task 8). None here
    # means "not collected", never "no premium".
    gmp: float | None = None
    gmp_pct: float | None = None
    gmp_sources: int = 0
    news_volume: int | None = None


def _as_utc(stamp: str) -> datetime | None:
    """Naive timestamps are read as UTC rather than rejected — an unparseable
    row must not be able to stall a prune or crash a read."""
    try:
        dt = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class IpoSignalStore:
    """JSONL at <base_dir>/ipo_signals.jsonl."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._dir = Path(base_dir or "data/ipo")
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._dir / "ipo_signals.jsonl"

    @staticmethod
    def _key(snap: IpoSignalSnapshot) -> tuple[str, str]:
        # Hour resolution: the refresh runs twice a day, so two rows inside one
        # hour means the job was re-run by hand, not that demand moved.
        return (snap.symbol, snap.captured_at[:13])

    def append(self, snap: IpoSignalSnapshot) -> bool:
        """True if written, False if an identical (symbol, hour) already exists."""
        if self._key(snap) in {self._key(r) for r in self.load_all()}:
            return False
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(snap.model_dump_json() + "\n")
        return True

    def load_all(self) -> list[IpoSignalSnapshot]:
        if not self.path.exists():
            return []
        out: list[IpoSignalSnapshot] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(IpoSignalSnapshot(**json.loads(line)))
            except Exception:
                continue            # a corrupt line must never break a read
        return out

    def load_symbol(self, symbol: str) -> list[IpoSignalSnapshot]:
        rows = [r for r in self.load_all() if r.symbol == symbol]
        return sorted(rows, key=lambda r: r.captured_at)

    def prune(self, older_than_days: int, now: datetime | None = None) -> int:
        """Drop rows older than the retention window. Returns rows removed.

        Rewrites via .tmp + replace(); a row whose timestamp will not parse is
        KEPT, because deleting data we cannot date is the worse error.
        """
        rows = self.load_all()
        if not rows:
            return 0
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=older_than_days)
        keep = [r for r in rows
                if (_as_utc(r.captured_at) or now) >= cutoff]
        removed = len(rows) - len(keep)
        if removed == 0:
            return 0
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(r.model_dump_json() + "\n" for r in keep),
                       encoding="utf-8")
        tmp.replace(self.path)
        logger.info("[ipo_signals] pruned %d row(s) older than %dd",
                    removed, older_than_days)
        return removed
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_ipo_signals.py -q`
Expected: 8 passed

- [ ] **Step 5: Close the §9b positive-case gap in the ladder tests**

`combined["total"]` is the entire P1 predictor column and is currently only ever asserted `is None`; `dom_fi` has had no consumer at all. P2 is `dom_fi`'s first consumer, so assert real values now.

Append to `tests/unit/test_ipo_bids.py`:

```python
def test_combined_total_carries_a_real_value():
    """The P1 predictor column. Previously only ever asserted `is None`, so a
    parser that silently stopped reading totals would not have been caught."""
    combined = parse_bid_ladder(_PAYLOAD)["combined"]
    assert combined["total"] is not None
    assert combined["total"] > 0


def test_dom_fi_is_parsed_as_its_own_category():
    """srNo 1(b). P2's capture ledger is its first consumer."""
    combined = parse_bid_ladder(_PAYLOAD)["combined"]
    assert "dom_fi" in combined
```

Read the existing `_PAYLOAD` fixture at the top of that file first. If its `activeCat.dataList` has no `1(b)` row, add one with a real-shaped value rather than asserting `is None` — a fixture that cannot exercise the field is the failure mode the P1 backfill review already caught once.

- [ ] **Step 6: Run the ladder tests**

Run: `python -m pytest tests/unit/test_ipo_bids.py -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add core/ipo/signals.py tests/unit/test_ipo_signals.py tests/unit/test_ipo_bids.py
git commit -m "feat(ipo): add the P2 capture ledger

Append-only JSONL of one snapshot per (IPO, refresh pass). Captured facts
only — every derived value is recomputed on read, so changing the maths never
means rewriting history.

prune() is the only rewrite path and its no-op case is asserted, because a
misbehaving rewrite is the one way this data can be lost.

Also closes the section 9b test gap: combined[total] and dom_fi were only ever
asserted is None, and P2 is dom_fi's first consumer.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Stop discarding the ladder (prerequisite)

**Files:**
- Modify: `services/data/fetchers/ipo.py:148-178` (`_enrich_open_issues`)
- Modify: `tests/unit/test_ipo_fetcher.py`

`refresh_ipo_cache` rebuilds every row from `_normalise` on each pass, and `_enrich_open_issues` only attaches the ladder to issues whose state is `open`. So the morning after an issue closes, its `bid_ladder`, `cutoff_share` and ladder-derived `qib_x`/`retail_x` all vanish and the brief line degrades from "40× overall (QIB 90×, retail 12×)" to bare "40× overall".

**For P2 this is a blocker, not a cosmetic bug: the final ladder of a closed issue is the single most valuable row in the entire capture ledger** — it is the completed demand picture that P3 will train on.

**Interfaces:**
- Consumes: `IpoSignalStore` is *not* used here. This task is purely the carry-forward fix.
- Produces: `_enrich_open_issues(rows, on, previous=None)` — the new third parameter is a `dict[str, dict]` of the previous cache's rows keyed by symbol.

- [ ] **Step 1: Write the failing regression test**

Append to `tests/unit/test_ipo_fetcher.py`:

```python
def test_a_closed_issue_keeps_its_final_ladder(tmp_path, monkeypatch):
    """The most valuable row in the capture ledger is a closed issue's FINAL
    ladder. Before this fix it was destroyed by the next 08:00 pass: the row is
    rebuilt from _normalise, and _enrich_open_issues only refetches OPEN issues.
    """
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod

    ladder = {"symbol": "MOLBIO",
              "combined": {"qib": 90.0, "retail": 12.0, "total": 40.0,
                           "dom_fi": 0.2, "fii": 1.0, "mutual_fund": 0.3,
                           "nii": 5.0, "employee": None},
              "nse_only": {"qib": 45.0, "total": 20.0},
              "cutoff_share": 0.46}

    previous = {"MOLBIO": {"symbol": "MOLBIO", "bid_ladder": ladder,
                           "cutoff_share": 0.46, "qib_x": 90.0,
                           "retail_x": 12.0, "total_x": 40.0,
                           "total_x_nse_only": False}}

    # Window ended yesterday => state is "closed", so no refetch happens.
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-12", "listing_date": "",
             "qib_x": None, "retail_x": None, "total_x": None,
             "total_x_nse_only": False}]

    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder",
                        lambda s: pytest.fail("a closed issue must not be refetched"))
    ipo_mod._enrich_open_issues(rows, date(2026, 8, 13), previous=previous)

    assert rows[0]["total_x"] == 40.0
    assert rows[0]["qib_x"] == 90.0
    assert rows[0]["bid_ladder"]["combined"]["dom_fi"] == 0.2
    assert rows[0]["cutoff_share"] == 0.46


def test_a_failed_refetch_keeps_the_previous_ladder(tmp_path, monkeypatch):
    """An open issue whose fetch fails must not lose yesterday's numbers."""
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod

    previous = {"MOLBIO": {"symbol": "MOLBIO", "cutoff_share": 0.46,
                           "qib_x": 90.0, "total_x": 40.0,
                           "bid_ladder": {"combined": {"total": 40.0}}}}
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-14", "listing_date": "",
             "qib_x": None, "retail_x": None, "total_x": None,
             "total_x_nse_only": False}]

    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", lambda s: None)
    ipo_mod._enrich_open_issues(rows, date(2026, 8, 13), previous=previous)

    assert rows[0]["total_x"] == 40.0
    assert rows[0]["cutoff_share"] == 0.46
```

Add `import pytest` at the top of the file if it is not already there.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py -q -k "final_ladder or failed_refetch"`
Expected: FAIL — `_enrich_open_issues() got an unexpected keyword argument 'previous'`

- [ ] **Step 3: Implement the carry-forward**

In `services/data/fetchers/ipo.py`, replace `_enrich_open_issues` with:

```python
_LADDER_FIELDS = ("bid_ladder", "cutoff_share", "qib_x", "retail_x",
                  "total_x", "total_x_nse_only")


def _carry_forward(rec: dict, previous: dict | None) -> None:
    """Restore ladder-derived fields from the previous cache, in place.

    Every pass rebuilds rows from _normalise, which knows only what the LIST
    feed carries — and the list feed has no ladder. Without this, a closed
    issue's final ladder is destroyed by the next refresh, and that row is the
    completed demand picture the capture ledger exists to keep.

    Only fills fields the new row lacks: a fresh fetch always wins.
    """
    if not previous:
        return
    prior = previous.get(rec.get("symbol", ""))
    if not isinstance(prior, dict):
        return
    for field in _LADDER_FIELDS:
        if rec.get(field) is None and prior.get(field) is not None:
            rec[field] = prior[field]


def _enrich_open_issues(rows: list[dict], on: _date,
                        previous: dict | None = None) -> None:
    """Attach the bid ladder to issues whose window is OPEN, in place.

    Only open issues get a live fetch: an upcoming one has no bids yet and a
    closed one will never change, so either would spend an NSE call to learn
    nothing. Closed issues instead inherit their last known ladder via
    _carry_forward. Bounded by IPO_MAX_LADDER_FETCHES because this runs inside
    a scheduler job.
    """
    from core.config import settings
    from core.ipo.calendar import issue_state

    if not getattr(settings, "IPO_BID_LADDER_ENABLED", True):
        for rec in rows:
            _carry_forward(rec, previous)
        return

    budget = int(getattr(settings, "IPO_MAX_LADDER_FETCHES", 10))
    for rec in rows:
        if issue_state(rec, on) != "open" or budget <= 0:
            _carry_forward(rec, previous)
            continue
        ladder = fetch_bid_ladder(rec["symbol"])
        if ladder is None:
            # Budget is spent only on a SUCCESSFUL fetch: a run of dead-endpoint
            # failures must not exhaust the cap with zero enrichment (§9b).
            _carry_forward(rec, previous)
            continue
        budget -= 1
        combined = ladder.get("combined") or {}
        rec["bid_ladder"] = ladder
        rec["cutoff_share"] = ladder.get("cutoff_share")
        for field, key in (("qib_x", "qib"), ("retail_x", "retail")):
            if combined.get(key) is not None:
                rec[field] = combined[key]
        if combined.get("total") is not None:
            rec["total_x"] = combined["total"]
            rec["total_x_nse_only"] = False
        _carry_forward(rec, previous)
```

Note this also fixes the §9b budget bug in passing — `budget -= 1` now happens only after a successful fetch.

- [ ] **Step 4: Pass `previous` at the call site**

In `refresh_ipo_cache`, change:

```python
    if not degraded:
        _enrich_open_issues(current + upcoming, on)
```

to:

```python
    if not degraded:
        prior_rows: dict[str, dict] = {}
        for bucket in ("current", "upcoming", "past"):
            for row in previous.get(bucket, []) or []:
                if isinstance(row, dict) and row.get("symbol"):
                    prior_rows.setdefault(row["symbol"], row)
        _enrich_open_issues(current + upcoming, on, previous=prior_rows)
```

- [ ] **Step 5: Run the fetcher tests**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py -q`
Expected: all pass, including the two new ones

- [ ] **Step 6: Commit**

```bash
git add services/data/fetchers/ipo.py tests/unit/test_ipo_fetcher.py
git commit -m "fix(ipo): stop destroying a closed issue's final bid ladder

Every refresh rebuilds rows from _normalise, and _enrich_open_issues only
refetches OPEN issues — so the morning after an issue closed, its ladder,
cutoff_share and ladder-derived multiples all vanished and the brief line
degraded from '40x overall (QIB 90x, retail 12x)' to bare '40x overall'.

For P2 this is a blocker: a closed issue's final ladder is the completed
demand picture the capture ledger exists to keep.

Also fixes the section 9b budget bug in passing — IPO_MAX_LADDER_FETCHES is
now spent only on a successful fetch, so a run of dead-endpoint failures can
no longer exhaust the cap with zero enrichment.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Wire capture into the refresh

**Files:**
- Modify: `services/data/fetchers/ipo.py` (`refresh_ipo_cache`)
- Modify: `config.yaml` (`ipo:` block)
- Modify: `src/backend/shared/config/settings/base.py`
- Modify: `tests/unit/test_ipo_fetcher.py`

**Interfaces:**
- Consumes: `IpoSignalStore`, `IpoSignalSnapshot` from Task 2; `issue_state` from `core/ipo/calendar.py`.
- Produces: `_capture_signals(rows: list[dict], on: date, store: IpoSignalStore | None = None) -> int` in `services/data/fetchers/ipo.py`, returning the number of snapshots written.

- [ ] **Step 1: Add the config keys**

In `config.yaml`, extend the `ipo:` block (currently at ~line 431):

```yaml
ipo:
  enabled: true
  refresh_hour: 8               # daily calendar+ladder refresh (IST)
  refresh_hour_live: 18         # second pass, after the 17:00 NSE bid update
  bid_ladder_enabled: true      # kill-switch for the per-symbol ladder fetch
  max_ladder_fetches: 10        # cap per refresh — one NSE call per open issue
  cache_max_age_hours: 48       # watchdog invariant threshold
  # ── P2 capture (design §5 P2) ──
  signals_enabled: true         # append a snapshot per issue per refresh pass
  signal_retention_days: 400    # >365 so P4 can read a full convergence year
```

In `src/backend/shared/config/settings/base.py`, after `IPO_CACHE_MAX_AGE_HOURS`:

```python
IPO_SIGNALS_ENABLED: bool = bool(cfg("ipo.signals_enabled", fallback=True))
IPO_SIGNAL_RETENTION_DAYS: int = int(cfg("ipo.signal_retention_days", fallback=400))
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/test_ipo_fetcher.py`:

```python
def test_capture_writes_one_snapshot_per_issue(tmp_path):
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod
    from core.ipo.signals import IpoSignalStore

    store = IpoSignalStore(base_dir=str(tmp_path))
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-14", "listing_date": "",
             "cutoff_share": 0.46,
             "bid_ladder": {"combined": {"total": 40.0, "qib": 90.0,
                                         "dom_fi": 0.2},
                            "nse_only": {"total": 20.0}}}]

    assert ipo_mod._capture_signals(rows, date(2026, 8, 13), store=store) == 1
    snaps = store.load_symbol("MOLBIO")
    assert len(snaps) == 1
    assert snaps[0].state == "open"
    assert snaps[0].combined["total"] == 40.0
    assert snaps[0].combined["dom_fi"] == 0.2
    assert snaps[0].cutoff_share == 0.46


def test_capture_skips_an_issue_with_no_ladder(tmp_path):
    """An upcoming issue has no bids. Writing an all-None snapshot would put a
    row in the ledger asserting a reading was taken when none was."""
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod
    from core.ipo.signals import IpoSignalStore

    store = IpoSignalStore(base_dir=str(tmp_path))
    rows = [{"symbol": "ARDEE", "issue_start": "2026-09-01",
             "issue_end": "2026-09-03", "listing_date": ""}]
    assert ipo_mod._capture_signals(rows, date(2026, 8, 13), store=store) == 0
    assert store.load_all() == []


def test_capture_is_off_when_the_flag_is_false(tmp_path, monkeypatch):
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod
    from core.config import settings
    from core.ipo.signals import IpoSignalStore

    monkeypatch.setattr(settings, "IPO_SIGNALS_ENABLED", False, raising=False)
    store = IpoSignalStore(base_dir=str(tmp_path))
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-14", "listing_date": "",
             "bid_ladder": {"combined": {"total": 40.0}}}]
    assert ipo_mod._capture_signals(rows, date(2026, 8, 13), store=store) == 0


def test_capture_never_raises_into_the_refresh(tmp_path, monkeypatch):
    """A dead ledger must not break the cache write the brief depends on."""
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod

    class Boom:
        def append(self, snap):
            raise OSError("disk gone")

    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-14", "listing_date": "",
             "bid_ladder": {"combined": {"total": 40.0}}}]
    assert ipo_mod._capture_signals(rows, date(2026, 8, 13), store=Boom()) == 0
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py -q -k capture`
Expected: FAIL — `module 'services.data.fetchers.ipo' has no attribute '_capture_signals'`

- [ ] **Step 4: Implement**

Add to `services/data/fetchers/ipo.py`:

```python
def _capture_signals(rows: list[dict], on: _date, store=None) -> int:
    """Append one capture-ledger snapshot per issue that has a ladder.

    Spends NO additional API calls: it persists what _enrich_open_issues
    already fetched and previously discarded. An issue with no ladder is
    skipped rather than written as all-None — a row in the ledger asserts a
    reading was taken, and "we looked and there were no bids yet" is not the
    same claim as "we never looked".

    Never raises: a dead ledger must not break the cache write the morning
    brief depends on.
    """
    from core.config import settings
    from core.ipo.calendar import issue_state

    if not getattr(settings, "IPO_SIGNALS_ENABLED", True):
        return 0

    written = 0
    try:
        if store is None:
            from core.ipo.signals import IpoSignalStore
            store = IpoSignalStore()
        from core.ipo.signals import IpoSignalSnapshot
        stamp = datetime.now(timezone.utc).isoformat()
        for rec in rows:
            ladder = rec.get("bid_ladder")
            if not isinstance(ladder, dict):
                continue
            snap = IpoSignalSnapshot(
                symbol=rec.get("symbol", ""),
                captured_at=stamp,
                state=issue_state(rec, on),
                issue_start=rec.get("issue_start", "") or "",
                issue_end=rec.get("issue_end", "") or "",
                combined=ladder.get("combined") or {},
                nse_only=ladder.get("nse_only") or {},
                cutoff_share=rec.get("cutoff_share"),
            )
            if store.append(snap):
                written += 1
    except Exception as exc:
        logger.warning("[ipo] signal capture failed (non-fatal): %s", exc)
        return written
    return written
```

Then, in `refresh_ipo_cache`, immediately after the `_enrich_open_issues(...)` call added in Task 3:

```python
        captured = _capture_signals(current + upcoming, on)
        if captured:
            logger.info("[ipo] captured %d signal snapshot(s)", captured)
```

- [ ] **Step 5: Add the daily prune**

Still inside `refresh_ipo_cache`, after the capture block:

```python
        try:
            from core.config import settings as _s
            from core.ipo.signals import IpoSignalStore
            IpoSignalStore().prune(
                older_than_days=int(getattr(_s, "IPO_SIGNAL_RETENTION_DAYS", 400)))
        except Exception as exc:
            logger.warning("[ipo] signal prune failed (non-fatal): %s", exc)
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py tests/unit/test_ipo_signals.py -q`
Expected: all pass

- [ ] **Step 7: Run the full suite** — this task changes a scheduler-reachable path.

Run: `python -m pytest tests/unit -q`
Expected: 2460+ passed, 5 skipped, 0 failed

- [ ] **Step 8: Commit**

```bash
git add services/data/fetchers/ipo.py config.yaml \
        src/backend/shared/config/settings/base.py tests/unit/test_ipo_fetcher.py
git commit -m "feat(ipo): capture a signal snapshot on every refresh pass

Persists the ladder that _enrich_open_issues already fetches and used to
discard. Zero additional API calls.

An issue with no ladder is skipped rather than written as all-None: a row in
the ledger asserts a reading was taken, and 'we looked and there were no bids'
is a different claim from 'we never looked'.

Capture and prune are both non-fatal — a dead ledger must not break the cache
write the morning brief depends on.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Derivations over the ledger

**Files:**
- Create: `core/ipo/velocity.py`
- Create: `tests/unit/test_ipo_velocity.py`

**Interfaces:**
- Consumes: `IpoSignalSnapshot` from Task 2.
- Produces:
  - `latest_demand(snaps: list[IpoSignalSnapshot]) -> float | None`
  - `demand_delta(snaps: list[IpoSignalSnapshot]) -> float | None`
  - `final_demand_snapshot(snaps: list[IpoSignalSnapshot]) -> IpoSignalSnapshot | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ipo_velocity.py`:

```python
from core.ipo.signals import IpoSignalSnapshot
from core.ipo.velocity import demand_delta, final_demand_snapshot, latest_demand


def _s(captured_at, total, state="open"):
    return IpoSignalSnapshot(symbol="MOLBIO", captured_at=captured_at,
                             state=state, combined={"total": total})


def test_latest_demand_reads_the_newest_snapshot():
    snaps = [_s("2026-08-11T08:00:00+00:00", 2.0),
             _s("2026-08-13T18:00:00+00:00", 12.4)]
    assert latest_demand(snaps) == 12.4


def test_latest_demand_ignores_input_order():
    snaps = [_s("2026-08-13T18:00:00+00:00", 12.4),
             _s("2026-08-11T08:00:00+00:00", 2.0)]
    assert latest_demand(snaps) == 12.4


def test_demand_delta_is_the_change_since_the_previous_reading():
    snaps = [_s("2026-08-13T08:00:00+00:00", 9.3),
             _s("2026-08-13T18:00:00+00:00", 12.4)]
    assert round(demand_delta(snaps), 4) == 3.1


def test_a_single_snapshot_has_no_delta():
    """None, never 0.0 — zero would assert demand did not move."""
    assert demand_delta([_s("2026-08-13T08:00:00+00:00", 9.3)]) is None


def test_no_snapshots_is_none_everywhere():
    assert latest_demand([]) is None
    assert demand_delta([]) is None
    assert final_demand_snapshot([]) is None


def test_snapshots_without_a_total_are_not_readings():
    snaps = [IpoSignalSnapshot(symbol="X", captured_at="2026-08-13T08:00:00+00:00",
                               combined={"total": None}),
             _s("2026-08-13T18:00:00+00:00", 12.4)]
    assert latest_demand(snaps) == 12.4
    assert demand_delta(snaps) is None


def test_final_demand_snapshot_is_the_last_one_carrying_a_total():
    last = _s("2026-08-14T08:00:00+00:00", 12.4, state="closed")
    snaps = [_s("2026-08-13T08:00:00+00:00", 9.3), last,
             IpoSignalSnapshot(symbol="MOLBIO",
                               captured_at="2026-08-15T08:00:00+00:00",
                               state="closed", combined={"total": None})]
    assert final_demand_snapshot(snaps).captured_at == last.captured_at
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_ipo_velocity.py -q`
Expected: collection error — `No module named 'core.ipo.velocity'`

- [ ] **Step 3: Implement**

Create `core/ipo/velocity.py`:

```python
"""PI Prospect P2 — derivations over the capture ledger (design §5 P2).

Pure functions, recomputed on every read. Nothing here is ever written back
into ipo_signals.jsonl: the ledger holds captured facts, and keeping the maths
outside it means a change of definition never requires rewriting history.

Every function returns None rather than 0.0 when there is nothing to measure.
A zero delta asserts demand did not move, which is a different claim from
having only one reading.
"""
from __future__ import annotations

from core.ipo.signals import IpoSignalSnapshot


def _readings(snaps: list[IpoSignalSnapshot]) -> list[IpoSignalSnapshot]:
    """Snapshots that actually carry an all-exchange total, oldest first."""
    rows = [s for s in snaps or [] if s.combined.get("total") is not None]
    return sorted(rows, key=lambda s: s.captured_at)


def latest_demand(snaps: list[IpoSignalSnapshot]) -> float | None:
    """The most recent all-exchange subscription multiple."""
    rows = _readings(snaps)
    return rows[-1].combined["total"] if rows else None


def demand_delta(snaps: list[IpoSignalSnapshot]) -> float | None:
    """Change in subscription × since the PREVIOUS reading.

    Deliberately not "today's change": the refresh runs twice daily, so the
    previous reading may be this morning or yesterday evening. Callers render
    this as "since last update", which is true either way.
    """
    rows = _readings(snaps)
    if len(rows) < 2:
        return None
    return rows[-1].combined["total"] - rows[-2].combined["total"]


def final_demand_snapshot(snaps: list[IpoSignalSnapshot]) -> IpoSignalSnapshot | None:
    """The last snapshot carrying a total — the completed demand picture.

    This is the row P3 will train on: everything that was knowable about
    demand at the moment the window shut.
    """
    rows = _readings(snaps)
    return rows[-1] if rows else None
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_velocity.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add core/ipo/velocity.py tests/unit/test_ipo_velocity.py
git commit -m "feat(ipo): add pure derivations over the capture ledger

latest_demand / demand_delta / final_demand_snapshot, recomputed on read so a
change of definition never means rewriting history.

Every one returns None rather than 0.0 when there is nothing to measure: a
zero delta asserts demand did not move, which is not the same claim as having
only one reading.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Surface the facts

**Files:**
- Modify: `core/delivery/brief.py:240-260` (`_ipo_demand`), `:485-494` (`_ipo_watch`)
- Modify: `core/delivery/weekly.py` — no change needed if `_ipo_demand` is the only edit; verify
- Modify: `tests/unit/test_delivery_brief.py`

Renders **observed facts only**. No index, no quadrant, no two-horizon verdict — those are P3/P5. The existing `_ipo_lean` STRONG/MODERATE/SOFT label is P0 behaviour and is **not touched**.

**Interfaces:**
- Consumes: `demand_delta` from Task 5; `IpoSignalStore` from Task 2.
- Produces: `_ipo_demand(w: dict) -> str` — unchanged signature, richer output. `_ipo_watch` rows gain `dom_fi_x`, `fii_x`, `mutual_fund_x`, `demand_delta`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_delivery_brief.py`:

```python
def test_ipo_demand_renders_the_cutoff_share():
    """Fetched, cached and threaded into every brief row since P0 — and never
    once rendered (§9b). It is an official froth measure (spec §3)."""
    line = br._ipo_demand({"total_x": 12.4, "qib_x": 28.0, "retail_x": 6.0,
                           "cutoff_share": 0.4633})
    assert line == "12.4× overall (QIB 28×, retail 6×) · 46% at cut-off"


def test_ipo_demand_renders_the_demand_delta():
    line = br._ipo_demand({"total_x": 12.4, "demand_delta": 3.1})
    assert line == "12.4× overall · +3.1× since last update"


def test_ipo_demand_renders_a_negative_delta_with_one_sign():
    """`:+g` must not produce '--0.4'. Demand can fall between passes when NSE
    revises a category."""
    line = br._ipo_demand({"total_x": 12.4, "demand_delta": -0.4})
    assert line == "12.4× overall · -0.4× since last update"


def test_ipo_demand_omits_every_absent_clause():
    """Dark-signal: absent means omitted, never zero."""
    assert br._ipo_demand({"total_x": 12.4}) == "12.4× overall"
    assert br._ipo_demand({"total_x": 12.4, "cutoff_share": None,
                           "demand_delta": None}) == "12.4× overall"


def test_ipo_demand_still_reports_pending_with_nothing_at_all():
    assert br._ipo_demand({}) == "demand data pending"


def test_ipo_demand_keeps_the_nse_only_qualifier():
    """P0 behaviour that must not regress: an NSE-only total is a WRONG
    number if shown unqualified, not merely an incomplete one."""
    assert br._ipo_demand({"total_x": 2.05, "total_x_nse_only": True}) == \
        "2.05× overall (NSE only)"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_delivery_brief.py -q -k ipo_demand`
Expected: FAIL on the cut-off and delta cases; the existing cases still pass

- [ ] **Step 3: Extend `_ipo_demand`**

Replace the tail of `_ipo_demand` in `core/delivery/brief.py` (keep everything above `return` intact):

```python
    if extra:
        parts.append("(" + ", ".join(extra) + ")")

    # P2: official froth measures. Both are captured facts, not scores — the
    # derived indices and verdicts stay dark until P3/P5.
    cutoff = w.get("cutoff_share")
    if cutoff is not None:
        parts.append(f"· {cutoff * 100:.0f}% at cut-off")
    delta = w.get("demand_delta")
    if delta is not None:
        # "since last update", not "today": the refresh runs twice daily, so
        # the previous reading may be this morning or yesterday evening.
        parts.append(f"· {delta:+g}× since last update")

    return " ".join(parts) if parts else "demand data pending"
```

- [ ] **Step 4: Feed the delta and the institutional split into the row**

In `core/delivery/brief.py`, inside `_ipo_watch`'s per-row dict, after `"cutoff_share": r.get("cutoff_share"),` add:

```python
                "dom_fi_x": (r.get("bid_ladder") or {}).get("combined", {}).get("dom_fi"),
                "fii_x": (r.get("bid_ladder") or {}).get("combined", {}).get("fii"),
                "mutual_fund_x": (r.get("bid_ladder") or {}).get("combined", {}).get("mutual_fund"),
                "demand_delta": _demand_delta_for(r.get("symbol", "")),
```

and add this helper above `_ipo_watch`:

```python
def _demand_delta_for(symbol: str) -> float | None:
    """Change in subscription × since the previous capture, or None.

    Non-fatal by construction: the ledger is a P2 addition and the brief
    predates it, so an unreadable ledger degrades this one clause rather than
    dropping the IPO section.
    """
    if not symbol:
        return None
    try:
        from core.ipo.signals import IpoSignalStore
        from core.ipo.velocity import demand_delta
        return demand_delta(IpoSignalStore().load_symbol(symbol))
    except Exception as exc:
        logger.debug("[brief] demand delta unavailable for %s: %s", symbol, exc)
        return None
```

- [ ] **Step 5: Run the brief and weekly tests**

Run: `python -m pytest tests/unit/test_delivery_brief.py tests/unit/test_delivery_weekly.py -q`
Expected: all pass. `core/delivery/weekly.py` imports `_ipo_demand` directly (`weekly.py:249`), so the digest inherits the richer line with no edit — confirm by reading that call site rather than assuming.

- [ ] **Step 6: Check the HTML renderer**

`core/delivery/brief.py:958` also calls `_ipo_demand`. Read that block and confirm the longer string does not break the HTML layout. If the line needs wrapping, wrap it there — do not shorten `_ipo_demand`, because the text and HTML parts must agree.

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest tests/unit -q`
Expected: 2460+ passed, 5 skipped, 0 failed

- [ ] **Step 8: Commit**

```bash
git add core/delivery/brief.py tests/unit/test_delivery_brief.py
git commit -m "feat(ipo): surface cut-off share and demand movement in the brief

cutoff_share has been fetched, cached and threaded into every brief row since
P0 without ever being rendered (section 9b). It is an official froth measure
(spec section 3), so it is now shown alongside the institutional split and the
change since the previous capture.

Facts only. The derived indices, quadrant and two-horizon verdicts stay dark
until P3/P5, and the existing STRONG/MODERATE/SOFT lean is untouched.

Rendered as 'since last update' rather than 'today' because the refresh runs
twice daily and the previous reading may be either.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Move the PM refresh off the weekly-review collision

**Files:**
- Modify: `config.yaml` (`ipo.refresh_hour_live`, new `ipo.refresh_minute_live`)
- Modify: `src/backend/shared/config/settings/base.py`
- Modify: `services/scheduler/python/scheduler.py:495-511`
- Modify: `tests/unit/` — whichever test module covers scheduler job registration (find it with `grep -rl "ipo_refresh" tests/`)

`ipo_refresh_pm` (18:00 IST) and `weekly_review` (Sun 18:00 IST) fire in the same minute with no ordering, so the Sunday digest is a coin flip between the fresh cache and the 08:00 one. Writes are atomic, so this is non-determinism, not corruption — but with P2 the digest also reads the capture ledger, and a digest that sometimes sees the evening snapshot and sometimes does not is not reproducible.

- [ ] **Step 1: Update config**

In `config.yaml`:

```yaml
  refresh_hour_live: 17         # second pass, after the 17:00 NSE bid update
  refresh_minute_live: 45       # 17:45 — strictly before Sunday's 18:00 weekly_review
```

In `base.py`, beside `IPO_REFRESH_HOUR_LIVE`:

```python
IPO_REFRESH_MINUTE_LIVE: int = int(cfg("ipo.refresh_minute_live", fallback=45))
```

- [ ] **Step 2: Write the failing test**

Add to the scheduler test module:

```python
def test_the_pm_ipo_refresh_lands_before_the_weekly_review():
    """Both used to fire at 18:00 Sunday with no ordering, making the digest a
    coin flip between the fresh cache and the morning one."""
    from core.config import settings
    pm_minutes = settings.IPO_REFRESH_HOUR_LIVE * 60 + settings.IPO_REFRESH_MINUTE_LIVE
    assert pm_minutes < 18 * 60
    # Still after NSE's ~17:00 bid update, or the evening pass reads stale bids.
    assert pm_minutes >= 17 * 60
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/unit -q -k "pm_ipo_refresh"`
Expected: FAIL — `AttributeError: IPO_REFRESH_MINUTE_LIVE` (before Step 1 lands) or an assertion failure at 18:00

- [ ] **Step 4: Teach the scheduler a minute**

In `services/scheduler/python/scheduler.py`, replace the registration loop:

```python
        if cfg("ipo.enabled", fallback=True):
            for slot, hour, minute in (
                ("am", int(cfg("ipo.refresh_hour", fallback=8)), 0),
                ("pm", int(cfg("ipo.refresh_hour_live", fallback=17)),
                 int(cfg("ipo.refresh_minute_live", fallback=45))),
            ):
                scheduler.add_job(
                    func=self._ipo_refresh_job,
                    trigger=CronTrigger(hour=hour, minute=minute,
                                        timezone="Asia/Kolkata"),
                    id=f"ipo_refresh_{slot}",
                    name=f"IPO calendar + bid ladder refresh ({slot})",
                    misfire_grace_time=3600,
                    coalesce=True,
                    replace_existing=True,
                )
            logger.info(
                "[Scheduler] IPO refresh: daily at %s:00 and %s:%02d IST",
                cfg("ipo.refresh_hour", fallback=8),
                cfg("ipo.refresh_hour_live", fallback=17),
                cfg("ipo.refresh_minute_live", fallback=45))
```

Note the `refresh_hour_live` **fallback also changes 18 → 17**. Leaving it at 18 would mean a missing config key silently restores the collision.

- [ ] **Step 5: Run the scheduler tests**

Run: `python -m pytest tests/unit -q -k "scheduler or ipo_refresh"`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add config.yaml src/backend/shared/config/settings/base.py \
        services/scheduler/python/scheduler.py tests/unit/
git commit -m "fix(ipo): move the PM refresh to 17:45, off the weekly-review slot

ipo_refresh_pm and weekly_review both fired at 18:00 Sunday with no ordering,
so the digest was a coin flip between the fresh cache and the 08:00 one. With
P2 the digest also reads the capture ledger, so a run that sometimes sees the
evening snapshot is not reproducible.

17:45 is still after NSE's ~17:00 bid update. The refresh_hour_live fallback
moves 18 -> 17 too, so a missing config key cannot silently restore the
collision.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: GMP — built, gated, dark

**Files:**
- Create: `services/data/fetchers/ipo_gmp.py`
- Create: `tests/unit/test_ipo_gmp.py`
- Modify: `config.yaml`, `src/backend/shared/config/settings/base.py`

**Measured constraint that shapes this task: Serper headroom is 80–300 calls/month, not the 2,300 the spec originally assumed** (prod counter 2026-08-13: 924 calls on day 13, ~83/day, projecting ~2,200–2,420 against a 2,500 cap). So GMP reads a **separate** key and, absent that key, must cost exactly nothing.

**Interfaces:**
- Consumes: `search_serper` from `services/data/fetchers/news.py`.
- Produces: `fetch_gmp(company: str, issue_price: float | None = None) -> dict | None` returning `{"gmp": float, "gmp_pct": float | None, "sources": int}` or `None`.

- [ ] **Step 1: Add config + the key**

`config.yaml`, in the `ipo:` block:

```yaml
  gmp_enabled: false            # stays false until SERPER_API_KEY_IPO exists
  gmp_min_sources: 2            # a lone snippet number is not a measurement
  gmp_agreement_tolerance: 0.25 # >25% spread between sources => discard
  gmp_max_age_hours: 24
```

`base.py`, beside the other API keys (~line 68):

```python
# Dedicated Serper key for PI Prospect GMP capture. A SECRET, so env= is
# correct here — the carve-out in the no-env-for-toggles rule. Kept separate
# from SERPER_API_KEY on purpose: the shared key runs at ~83 calls/day against
# a 2,500/mo cap (measured 2026-08-13), leaving no room for IPO polling.
SERPER_API_KEY_IPO: str = os.getenv("SERPER_API_KEY_IPO", "")
```

and with the other `IPO_*` settings:

```python
IPO_GMP_ENABLED: bool = bool(cfg("ipo.gmp_enabled", fallback=False))
IPO_GMP_MIN_SOURCES: int = int(cfg("ipo.gmp_min_sources", fallback=2))
IPO_GMP_AGREEMENT_TOLERANCE: float = float(cfg("ipo.gmp_agreement_tolerance", fallback=0.25))
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_ipo_gmp.py`:

```python
import pytest

import services.data.fetchers.ipo_gmp as gmp_mod
from core.config import settings


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(settings, "IPO_GMP_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "SERPER_API_KEY_IPO", "test-key", raising=False)
    monkeypatch.setattr(settings, "IPO_GMP_MIN_SOURCES", 2, raising=False)
    monkeypatch.setattr(settings, "IPO_GMP_AGREEMENT_TOLERANCE", 0.25, raising=False)


def test_no_key_means_no_value_and_NO_API_CALL(monkeypatch):
    """The quota gate. The shared Serper key runs at ~83 calls/day against a
    2500/mo cap, so an unkeyed GMP fetcher must cost exactly zero."""
    monkeypatch.setattr(settings, "SERPER_API_KEY_IPO", "", raising=False)
    calls = []
    monkeypatch.setattr(gmp_mod, "search_serper",
                        lambda *a, **k: calls.append(1) or [])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None
    assert calls == []


def test_disabled_flag_means_no_value_and_no_call(monkeypatch):
    monkeypatch.setattr(settings, "IPO_GMP_ENABLED", False, raising=False)
    calls = []
    monkeypatch.setattr(gmp_mod, "search_serper",
                        lambda *a, **k: calls.append(1) or [])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None
    assert calls == []


def test_two_agreeing_sources_yield_the_median(monkeypatch):
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "Molbio IPO GMP today is Rs 120 per share",
         "link": "https://ipowatch.example/molbio"},
        {"snippet": "grey market premium of ₹130 ahead of listing",
         "link": "https://investorgain.example/molbio"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics", issue_price=500.0)
    assert out["gmp"] == 125.0
    assert out["sources"] == 2
    assert round(out["gmp_pct"], 2) == 25.0


def test_a_single_source_is_not_a_measurement(monkeypatch):
    """Grey-market chatter from one search result is a rumour, not a reading."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "Molbio IPO GMP Rs 120", "link": "https://ipowatch.example/x"},
    ])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None


def test_two_numbers_from_the_SAME_domain_count_once(monkeypatch):
    """One aggregator echoed twice is still one source."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "GMP Rs 120", "link": "https://ipowatch.example/a"},
        {"snippet": "GMP Rs 130", "link": "https://ipowatch.example/b"},
    ])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None


def test_sources_that_disagree_wildly_are_discarded(monkeypatch):
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "GMP Rs 20", "link": "https://a.example/x"},
        {"snippet": "GMP Rs 300", "link": "https://b.example/y"},
    ])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None


def test_a_search_failure_is_none_not_a_raise(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("serper down")
    monkeypatch.setattr(gmp_mod, "search_serper", boom)
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None


def test_gmp_pct_is_absent_without_an_issue_price(monkeypatch):
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "GMP Rs 120", "link": "https://a.example/x"},
        {"snippet": "GMP Rs 130", "link": "https://b.example/y"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics", issue_price=None)
    assert out["gmp"] == 125.0
    assert out["gmp_pct"] is None
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/unit/test_ipo_gmp.py -q`
Expected: collection error — `No module named 'services.data.fetchers.ipo_gmp'`

- [ ] **Step 4: Implement**

Create `services/data/fetchers/ipo_gmp.py`:

```python
"""PI Prospect P2 — grey-market premium via a DEDICATED Serper key.

Ships dark. `ipo.gmp_enabled` is false and `SERPER_API_KEY_IPO` is unset, in
which case this module returns None and issues no request at all.

Why its own key: the shared SERPER_API_KEY runs at ~83 calls/day against a
2,500/month cap (prod counter, 2026-08-13: 924 calls on day 13 of 31,
projecting ~2,200-2,420). Real headroom is 80-300 calls/month, so IPO polling
on the shared key would compete directly with the daily pipeline. The spec's
original "~2,300 calls/mo headroom" was never measured and is wrong.

GMP is unofficial grey-market chatter scraped from search snippets, so a
single number is treated as a rumour: a reading requires agreement between at
least `ipo.gmp_min_sources` DISTINCT domains, and the spread between them must
be within `ipo.gmp_agreement_tolerance`. Callers render the result as
unofficial, always.
"""
from __future__ import annotations

import logging
import re
import statistics
from urllib.parse import urlparse

from services.data.fetchers.news import search_serper

logger = logging.getLogger(__name__)

# "Rs 120", "₹130", "Rs. 1,250" — the number is the premium per share.
_GMP_RE = re.compile(r"(?:₹|rs\.?)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
# Guards against picking up a share count or a market-cap figure.
_MAX_PLAUSIBLE_GMP = 5000.0


def _numbers_by_domain(results: list[dict]) -> dict[str, float]:
    """One number per domain — the first plausible one. An aggregator echoed
    across two result pages is one source, not two."""
    out: dict[str, float] = {}
    for item in results or []:
        domain = urlparse(str(item.get("link") or "")).netloc.lower()
        if not domain or domain in out:
            continue
        match = _GMP_RE.search(str(item.get("snippet") or ""))
        if not match:
            continue
        try:
            value = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        if 0 < value <= _MAX_PLAUSIBLE_GMP:
            out[domain] = value
    return out


def fetch_gmp(company: str, issue_price: float | None = None) -> dict | None:
    """Median GMP across agreeing sources, or None. Never raises.

    None means "not collected" — never "no premium". A GMP of zero is a real
    and meaningful reading, which is exactly why absence must not render as 0.
    """
    from core.config import settings

    if not getattr(settings, "IPO_GMP_ENABLED", False):
        return None
    key = getattr(settings, "SERPER_API_KEY_IPO", "")
    if not key:
        logger.debug("[ipo_gmp] no SERPER_API_KEY_IPO — skipping, no call made")
        return None
    if not company:
        return None

    try:
        results = search_serper(f"{company} IPO GMP grey market premium today",
                                n=6, api_key=key)
    except Exception as exc:
        logger.warning("[ipo_gmp] search failed for %s (non-fatal): %s", company, exc)
        return None

    by_domain = _numbers_by_domain(results)
    min_sources = int(getattr(settings, "IPO_GMP_MIN_SOURCES", 2))
    if len(by_domain) < min_sources:
        logger.debug("[ipo_gmp] %s: %d source(s), need %d — discarding",
                     company, len(by_domain), min_sources)
        return None

    values = sorted(by_domain.values())
    tolerance = float(getattr(settings, "IPO_GMP_AGREEMENT_TOLERANCE", 0.25))
    if values[-1] > values[0] * (1.0 + tolerance):
        logger.debug("[ipo_gmp] %s: sources disagree (%s) — discarding",
                     company, values)
        return None

    gmp = float(statistics.median(values))
    pct = (gmp / issue_price * 100.0) if issue_price else None
    return {"gmp": gmp, "gmp_pct": pct, "sources": len(by_domain)}
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_gmp.py -q`
Expected: 8 passed

- [ ] **Step 6: Prove the default config spends nothing**

Run: `python -m pytest tests/unit/test_ipo_gmp.py -q -k "no_key or disabled_flag"`
Expected: 2 passed. **These two are the quota gate.** If either ever fails, GMP is spending the shared key's budget.

- [ ] **Step 7: Commit**

```bash
git add services/data/fetchers/ipo_gmp.py tests/unit/test_ipo_gmp.py \
        config.yaml src/backend/shared/config/settings/base.py
git commit -m "feat(ipo): add the GMP fetcher, built but gated dark

Reads a dedicated SERPER_API_KEY_IPO. Unset or ipo.gmp_enabled=false => returns
None and issues no request, asserted by two tests.

The separate key exists because the shared SERPER_API_KEY runs at ~83 calls/day
against a 2500/mo cap (prod counter 2026-08-13: 924 calls on day 13), leaving
80-300 calls/mo of real headroom — not the ~2300 the spec assumed. IPO polling
on the shared key would compete with the daily pipeline.

GMP is scraped grey-market chatter, so a reading requires agreement between at
least two DISTINCT domains within a 25% spread; one number is a rumour. None
means 'not collected', never 'no premium' — a GMP of zero is a real reading.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: OFS share — extraction and backfill

> **Gated on Task 1.** If the spike found no `issueInfo` for past symbols, build only the forward path and say so. If it found nothing at all, **cut this task** and edit spec §5 P2 to record that. Do not invent a parser for a field that is not there.

**Files:**
- Create: `services/data/fetchers/ipo_offer.py`
- Create: `tests/unit/test_ipo_offer.py`
- Modify: `core/ipo/history.py` (`ofs_share` field + `upsert_many`)
- Modify: `scripts/ipo_backfill.py` (`--ofs` pass)

**Interfaces:**
- Consumes: the Task 1 fixture `tests/fixtures/ipo_detail_molbio.json`.
- Produces:
  - `parse_offer_split(issue_info: object) -> dict` returning `{"ofs_amount": float | None, "fresh_amount": float | None, "ofs_share": float | None}`
  - `IpoRecord.ofs_share: float | None`
  - `IpoHistoryStore.upsert_many(recs: list[IpoRecord]) -> int`

- [ ] **Step 1: Write the failing parser tests**

Create `tests/unit/test_ipo_offer.py`. **The `freshIssue` / `offerForSale` key names in the synthetic cases below are provisional — replace them with whatever Task 1 actually observed before writing the parser.** The first test reads the real captured fixture precisely so the parser cannot pass on invented input alone; that is the exact failure mode the P1 backfill review caught, where `test_backfill_is_idempotent` went green against a fixture shape the real feed cannot produce.

```python
import json
import pathlib

from services.data.fetchers.ipo_offer import parse_offer_split

_FIXTURE = pathlib.Path("tests/fixtures/ipo_detail_molbio.json")


def test_parses_the_real_captured_payload():
    """Guards against a parser that only works on invented input."""
    info = json.loads(_FIXTURE.read_text(encoding="utf-8"))["issueInfo"]
    out = parse_offer_split(info)
    assert out["ofs_share"] is not None
    assert 0.0 <= out["ofs_share"] <= 1.0


def test_a_pure_fresh_issue_has_an_ofs_share_of_zero():
    """Zero is a REAL reading here — no promoter is selling. Distinct from
    None, which means the split could not be read."""
    out = parse_offer_split({"freshIssue": "500.00", "offerForSale": "0.00"})
    assert out["ofs_share"] == 0.0


def test_a_pure_ofs_has_a_share_of_one():
    out = parse_offer_split({"freshIssue": "0.00", "offerForSale": "750.00"})
    assert out["ofs_share"] == 1.0


def test_unreadable_input_is_none_not_zero():
    for junk in (None, "", {}, "not a split at all", {"freshIssue": "abc"}):
        assert parse_offer_split(junk)["ofs_share"] is None


def test_a_zero_total_is_none_not_a_division_error():
    out = parse_offer_split({"freshIssue": "0", "offerForSale": "0"})
    assert out["ofs_share"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_ipo_offer.py -q`
Expected: collection error — `No module named 'services.data.fetchers.ipo_offer'`

- [ ] **Step 3: Implement the parser**

Create `services/data/fetchers/ipo_offer.py`. **Adapt the key tuples to what Task 1 actually observed** — the candidate-key pattern matches `ipo.py`, which exists because NSE field names drift across report vintages.

```python
"""PI Prospect P2 — OFS vs fresh-issue split from /api/ipo-detail issueInfo.

Spec §3 calls the OFS share "the single strongest Ola/Ather discriminator":
promoters cashing out versus fresh capital entering the business. Unlike GMP,
it is disclosed, official, and free.

Field names resolved through candidate-key tuples, the same defensive pattern
as ipo.py — NSE field names drift across report vintages.

An ofs_share of 0.0 is a REAL reading (nobody is selling down). None means the
split could not be read. Collapsing the two would turn "we could not tell"
into "the promoters kept everything", which inverts the signal.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_FRESH_KEYS = ("freshIssue", "freshIssueAmount", "fresh_issue")
_OFS_KEYS = ("offerForSale", "ofsAmount", "offer_for_sale")


def _amount(raw: object) -> float | None:
    text = str(raw or "").strip().replace(",", "")
    if not text:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    return float(nums[0]) if nums else None


def _first(info: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _amount(info.get(key))
        if value is not None:
            return value
    return None


def parse_offer_split(issue_info: object) -> dict:
    """{"ofs_amount", "fresh_amount", "ofs_share"} — any of them None."""
    blank = {"ofs_amount": None, "fresh_amount": None, "ofs_share": None}
    if not isinstance(issue_info, dict):
        return blank

    fresh = _first(issue_info, _FRESH_KEYS)
    ofs = _first(issue_info, _OFS_KEYS)
    if fresh is None or ofs is None:
        return {"ofs_amount": ofs, "fresh_amount": fresh, "ofs_share": None}

    total = fresh + ofs
    if total <= 0:
        return {"ofs_amount": ofs, "fresh_amount": fresh, "ofs_share": None}
    return {"ofs_amount": ofs, "fresh_amount": fresh,
            "ofs_share": round(ofs / total, 6)}
```

- [ ] **Step 4: Run the parser tests**

Run: `python -m pytest tests/unit/test_ipo_offer.py -q`
Expected: 5 passed

- [ ] **Step 5: Add the field and a merging bulk upsert**

In `core/ipo/history.py`, add to `IpoRecord` beside the other pre-listing knowables:

```python
    # Promoters cashing out vs fresh capital in. 0.0 is a real reading
    # (pure fresh issue); None means the split could not be read.
    ofs_share: float | None = None
```

and add to `IpoHistoryStore`:

```python
    def upsert_many(self, recs: list[IpoRecord]) -> int:
        """Replace rows for these symbols in ONE rewrite. Returns rows written.

        upsert() rewrites the whole file per row, which is O(n²) IO at ~206
        rows and the root cause of the OneDrive lock _upsert_with_retry works
        around (§9b). An enrichment pass touching every row must not do that.
        """
        rows = {r.symbol: r for r in self.load_all()}
        for rec in recs:
            rows[rec.symbol] = rec
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(r.model_dump_json() + "\n" for r in rows.values()),
                       encoding="utf-8")
        tmp.replace(self.path)
        return len(recs)
```

- [ ] **Step 6: Write the enrichment-preserves-everything test**

Append to `tests/unit/test_ipo_history.py`:

```python
def test_upsert_many_preserves_rows_it_does_not_touch(tmp_path):
    from core.ipo.history import IpoHistoryStore, IpoRecord
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="AAA", total_x=40.0, outcomes={"1": 12.3}))
    store.append(IpoRecord(symbol="BBB", total_x=2.0))

    store.upsert_many([IpoRecord(symbol="AAA", total_x=40.0,
                                 outcomes={"1": 12.3}, ofs_share=0.8)])

    rows = {r.symbol: r for r in store.load_all()}
    assert rows["AAA"].ofs_share == 0.8
    assert rows["AAA"].outcomes == {"1": 12.3}   # not wiped by the enrichment
    assert rows["BBB"].total_x == 2.0            # untouched row survives
```

This is the defect class `a578ac6` fixed: an enrichment pass that replaces whole rows silently destroys the columns it did not set.

- [ ] **Step 7: Add the `--ofs` pass to the backfill**

In `scripts/ipo_backfill.py`, add a flag that walks existing rows, fetches `/api/ipo-detail` per symbol, parses the split, and **merges onto the loaded record** rather than constructing a fresh one:

```python
def enrich_ofs(store, limit: int | None = None) -> int:
    """Fill ofs_share on rows that lack it. Read-modify-write per row so no
    existing column can be lost — the feed carries no bid data, so building a
    fresh IpoRecord here would wipe every predictor P1 measured."""
    from services.data.fetchers.ipo_offer import parse_offer_split
    from services.data.fetchers.nse_client import nse_session

    pending = [r for r in store.load_all() if r.ofs_share is None]
    if limit:
        pending = pending[:limit]
    updated = []
    for rec in pending:
        try:
            with nse_session() as nse:
                body = nse._req("https://www.nseindia.com/api/ipo-detail",
                                params={"symbol": rec.symbol, "series": "EQ"}).json()
        except Exception as exc:
            logger.warning("[ipo_backfill] ofs fetch failed for %s: %s", rec.symbol, exc)
            continue
        split = parse_offer_split(body.get("issueInfo"))
        if split["ofs_share"] is None:
            continue
        rec.ofs_share = split["ofs_share"]     # mutate the LOADED row
        updated.append(rec)
    return store.upsert_many(updated) if updated else 0
```

Wire it to `--ofs` in the CLI arg parser alongside the existing `--enrich`, and update the module docstring — §9b records that the old docstring "actively invited re-running" a command that would wipe enriched predictors.

- [ ] **Step 8: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_offer.py tests/unit/test_ipo_history.py tests/unit/test_ipo_backfill.py -q`
Expected: all pass

- [ ] **Step 9: Run the backfill for real**

```bash
PYTHONPATH=".;src" python -m scripts.ipo_backfill --ofs
```

Then read the result — this is the first evidence OFS is a real column:

```bash
PYTHONPATH=".;src" python -c "
from core.ipo.history import IpoHistoryStore
rows = IpoHistoryStore().load_all()
have = [r for r in rows if r.ofs_share is not None]
print(f'{len(have)} of {len(rows)} rows carry ofs_share')
both = [r for r in have if r.outcomes.get('1') is not None]
print(f'{len(both)} also have a listing-day outcome')
"
```

Report the counts. If fewer than ~30 rows carry both, say so plainly — the column exists but cannot yet support a bucketed comparison, and claiming otherwise would repeat the n=8 cold-bucket mistake `render_report` already refuses to make.

- [ ] **Step 10: Commit**

```bash
git add services/data/fetchers/ipo_offer.py tests/unit/test_ipo_offer.py \
        core/ipo/history.py tests/unit/test_ipo_history.py scripts/ipo_backfill.py
git commit -m "feat(ipo): extract the OFS/fresh split and backfill it

Spec section 3 calls OFS share the single strongest Ola/Ather discriminator,
and unlike GMP it is disclosed, official and free — the one P2 feature that can
be validated against the existing 206-row spine rather than only forward.

ofs_share 0.0 is a real reading (pure fresh issue); None means unreadable.
Collapsing them would turn 'we could not tell' into 'promoters kept
everything', inverting the signal.

Adds upsert_many so an enrichment pass over every row is one rewrite instead of
O(n^2), and the enrichment mutates LOADED rows so it cannot wipe columns it did
not set — the defect class fixed in a578ac6.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: Watchdog invariant — is capture actually happening?

**Files:**
- Modify: `core/ops/watchdog/checks.py`
- Modify: `config/milestones.yaml`
- Modify: `tests/unit/ops/test_watchdog_checks_more.py`

The house rule is that prod tells you when something lapses. `ipo_cache_fresh` proves the *job* runs; it cannot prove *capture* is landing. A ledger that silently stopped accruing would look identical to a quiet IPO month right up until P3 needs the data.

The check must not cry wolf: capture legitimately produces nothing when no window is open. So it fires only when an issue **was** open recently and no snapshot exists for it.

**Interfaces:**
- Consumes: `IpoSignalStore` from Task 2; the `@check` decorator and `CheckResult` already in `checks.py`.
- Produces: a `ipo_signals_accruing` check.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/ops/test_watchdog_checks_more.py`:

```python
def test_signals_accruing_is_satisfied_when_no_window_was_open(tmp_path, monkeypatch):
    """A quiet IPO month is not a fault. This check must not cry wolf."""
    import core.ops.watchdog.checks as checks
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(
        '{"fetched_at": "2026-08-13T08:00:00+00:00", "current": [], '
        '"upcoming": [], "past": []}', encoding="utf-8")
    assert checks.ipo_signals_accruing().status == "satisfied"


def test_signals_accruing_is_pending_when_an_open_issue_has_no_snapshot(tmp_path, monkeypatch):
    import core.ops.watchdog.checks as checks
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(
        '{"fetched_at": "2026-08-13T08:00:00+00:00", "current": ['
        '{"symbol": "MOLBIO", "issue_start": "2026-08-10", '
        '"issue_end": "2099-01-01", "listing_date": ""}], '
        '"upcoming": [], "past": []}', encoding="utf-8")
    (tmp_path / "ipo").mkdir(parents=True)
    result = checks.ipo_signals_accruing()
    assert result.status == "pending"
    assert "MOLBIO" in result.message
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/ops/test_watchdog_checks_more.py -q -k signals_accruing`
Expected: FAIL — `module 'core.ops.watchdog.checks' has no attribute 'ipo_signals_accruing'`

- [ ] **Step 3: Implement**

Add to `core/ops/watchdog/checks.py`, beside `ipo_cache_fresh`:

```python
@check("ipo_signals_accruing")
def ipo_signals_accruing() -> CheckResult:
    """An OPEN issue with no capture snapshot means the P2 ledger has stopped
    accruing. Silent by nature: a dead ledger and a quiet IPO month look
    identical until P3 needs the data and finds a hole in it.

    Deliberately scoped to currently-open issues so a month with no IPOs
    reports satisfied rather than crying wolf.
    """
    from datetime import date as _date

    from core.ipo.calendar import issue_state
    from core.ipo.signals import IpoSignalStore

    path = _data_dir() / "market_cache" / "ipo.json"
    if not path.exists():
        return CheckResult("satisfied", "No IPO cache yet — nothing to capture.",
                           {"path": str(path)})
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return CheckResult("pending", f"IPO cache unreadable: {exc}",
                           {"path": str(path)})

    today = _date.today()
    rows = (cache.get("current") or []) + (cache.get("upcoming") or [])
    open_symbols = [r.get("symbol", "") for r in rows
                    if isinstance(r, dict) and issue_state(r, today) == "open"]
    if not open_symbols:
        return CheckResult("satisfied", "No open IPO window — nothing to capture.",
                           {"open_issues": 0})

    store = IpoSignalStore(base_dir=str(_data_dir() / "ipo"))
    missing = [s for s in open_symbols if not store.load_symbol(s)]
    evidence = {"open_issues": len(open_symbols), "missing": missing}
    if missing:
        return CheckResult(
            "pending",
            f"IPO capture ledger has no snapshot for open issue(s): "
            f"{', '.join(missing)}. The refresh job is running but capture is "
            f"not landing — check ipo.signals_enabled and the ledger path.",
            evidence)
    return CheckResult(
        "satisfied",
        f"Capture ledger has snapshots for all {len(open_symbols)} open issue(s).",
        evidence)
```

- [ ] **Step 4: Register it**

In `config/milestones.yaml`, under `invariants:` beside `ipo_cache_fresh`:

```yaml
  - id: ipo_signals_accruing
    kind: invariant
    title: "IPO capture ledger is accruing snapshots"
    check: ipo_signals_accruing
    action: >
      An IPO window is open but the P2 capture ledger has no snapshot for it.
      The perishable demand data for this window is being lost and cannot be
      recovered later. Check ipo.signals_enabled in config.yaml and that
      data/ipo/ipo_signals.jsonl is writable on the volume.
    docs: docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md
```

- [ ] **Step 5: Run the watchdog tests**

Run: `python -m pytest tests/unit/ops -q`
Expected: all pass, including the registry test that walks every `check:` id in the yaml

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest tests/unit -q`
Expected: 2460+ passed, 5 skipped, 0 failed

- [ ] **Step 7: Commit**

```bash
git add core/ops/watchdog/checks.py config/milestones.yaml tests/unit/ops/
git commit -m "feat(ipo): add the ipo_signals_accruing watchdog invariant

ipo_cache_fresh proves the refresh JOB runs; it cannot prove capture is
landing. A ledger that silently stopped accruing looks exactly like a quiet
IPO month until P3 needs the data and finds a hole.

Scoped to currently-open issues so a month with no IPOs reports satisfied
rather than crying wolf.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Definition of done

- [ ] `python -m pytest tests/unit -q` → 2460+ passed, 5 skipped, **0 failed**
- [ ] `git grep -n 'env=' src/backend/shared/config/settings/base.py` shows **no new** `env=` on any `ipo.*` key. `SERPER_API_KEY_IPO` uses `os.getenv` alongside the other secrets, which is correct.
- [ ] With default config (`gmp_enabled: false`, no `SERPER_API_KEY_IPO`), a full refresh cycle makes **zero** Serper calls. Verify against the counter:
  ```bash
  PYTHONPATH=".;src" python -c "
  from services.data.stores.api_usage import get_usage
  before = get_usage()['serper']['calls']
  from services.data.fetchers.ipo import refresh_ipo_cache
  refresh_ipo_cache()
  print('serper delta:', get_usage()['serper']['calls'] - before)"
  ```
  Expected: `serper delta: 0`
- [ ] A second consecutive refresh in the same hour adds **no** ledger rows (dedup holds).
- [ ] Task 1's spike verdict is recorded in the spec, whatever it was.
- [ ] If Task 9 ran: the OFS coverage counts from Step 9 are reported honestly, including if they are too thin to bucket.

---

## Deliberately NOT in this plan

Per spec §5 P2: RHP PDF extraction; the named anchor-investor list; the news-volume proxy (it needs the same dedicated Serper key as GMP, so it lands when that key does); hype/substance indices; two-horizon verdicts; the quadrant; the auditor `Lane="ipo"` extension; any change to the existing STRONG/MODERATE/SOFT demand lean.

**Do not push to `main` between 16:25 and 17:15 IST on a trading day** — the standing deploy-kill rule.
