# Wave C — Context & Contract Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three cheap correctness/context findings from the Lighthouse review: AUD-078 (`nsepython` never in requirements → FII/DII/bulk-deal/earnings/MF-herding context structurally empty in prod), AUD-086 (`NSE()` constructed without `download_folder` → off-market and F&O context silently empty), AUD-100 (RL Monitor page fetches five phantom `/ui/rl/*` routes masked by the SPA catch-all → permanently shows mock data as real).

**Architecture:** Two one-line data-layer fixes plus one new read-only API router. AUD-100 is fixed server-side: a new `services/api/routes/rl_monitor.py` implements the five `/ui/rl/*` routes as thin adapters over `PredictionStore`, matching the exact shapes the page's mock data already uses (so the JSX needs only a fallback-behaviour tweak, not a rewrite) — chosen over repointing the page at `/scheduler/status` because per-day predicted/actual closes exist ONLY in the feedback log, not in any existing route. The SPA catch-all then starts returning 404 for unknown API-namespace paths so this contract-drift class fails loudly forever.

**Tech Stack:** FastAPI, Pydantic stores (`PredictionStore`), pytest + TestClient, prototype React (in-browser Babel, no build step).

## Global Constraints

- Public repo: no prod host names, cash figures, or auth specifics in committed docs/code comments.
- All new `/ui/rl/*` routes are read-only GETs → NO auth gate (matches Wave B decision: only mutations are gated).
- `PredictionStore.__init__` mkdirs on construction (AUD-024 class): routes MUST validate the ticker against the managed list BEFORE constructing a store, or arbitrary URL tickers create junk dirs.
- The SPA has no URL routing (UI_SPEC.md:48 "No React Router, no URL changes") — the catch-all may 404 API namespaces but must keep serving real files and `/` → index.html.
- House test baseline: 1 known pre-existing failure (`test_find_qualifying_events_unparseable_date_skipped`), 5 skips. Do not regress anything else.
- Run tests with the project venv: `.stockai/Scripts/python.exe -m pytest …`

---

### Task 1: AUD-078 — ship `nsepython`

**Files:**
- Modify: `requirements.txt` (Data fetching block, after the `nse>=2.0.0` line)
- Test: `tests/unit/test_requirements_deps.py` (create)

**Interfaces:**
- Produces: `nsepython` importable in the Docker image → `services/data/fetchers/nse_market.py:72` and `mf_herding.py` stop taking the ImportError branch.
- Note: nsepython 2.97 requires `requests`, `pandas`, `scipy` — scipy is a new transitive dep (~40MB image growth), accepted in the LEDGER decision (adding the dep beats porting 8 call sites to the `nse` package).

- [ ] **Step 1: Write the failing test**

```python
"""AUD-078 regression: nsepython was imported by two LIVE fetchers but never
declared — dev venv had it, prod image didn't, so FII/DII/bulk-deal/earnings/
MF-herding context was silently empty in every prod prompt since first deploy."""
from pathlib import Path

REQ = Path("requirements.txt").read_text(encoding="utf-8")


def _declared(pkg: str) -> bool:
    return any(
        line.split("#")[0].strip().lower().startswith(pkg)
        for line in REQ.splitlines()
    )


def test_nsepython_declared():
    assert _declared("nsepython"), "nsepython missing from requirements.txt (AUD-078)"


def test_nse_still_declared():
    assert _declared("nse>")  # the OTHER NSE client, used by 10+ fetchers
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.stockai/Scripts/python.exe -m pytest tests/unit/test_requirements_deps.py -v`
Expected: `test_nsepython_declared` FAILS with the AUD-078 message; `test_nse_still_declared` passes.

- [ ] **Step 3: Add the dependency**

In `requirements.txt`, after the `nse>=2.0.0` line, add:

```
nsepython>=2.90           # FII/DII flows, bulk deals, earnings calendar (AUD-078; pulls scipy)
```

- [ ] **Step 4: Run tests + import check**

Run: `.stockai/Scripts/python.exe -m pytest tests/unit/test_requirements_deps.py -v` → 2 PASS.
Run: `.stockai/Scripts/python.exe -c "from nsepython import get_bulkdeals, nse_fiidii, nse_events; print('ok')"` → prints `ok` (venv already has 2.97).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/unit/test_requirements_deps.py
git commit -m "fix(data): declare nsepython — FII/DII/bulk-deal/earnings context was empty in prod (AUD-078)"
```

---

### Task 2: AUD-086 — `NSE()` constructor fixes (offmarket + F&O)

**Files:**
- Modify: `core/intelligence/rl/stores/offmarket_fetcher.py:23-29`
- Modify: `core/intelligence/fno/fetcher.py:23-30` (same defect, found during Wave C research — `FnOFetcher` also calls bare `NSE()`)
- Test: `tests/unit/test_nse_ctor_fetchers.py` (create)

**Interfaces:**
- Consumes: `nse.NSE` (BennyThadikaran client) whose `__init__` REQUIRES `download_folder`; every other caller in the repo passes `NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))` (e.g. `core/delivery/index_watch.py:27`).
- Produces: `OffMarketFetcher()._nse` / `FnOFetcher()._nse` non-None when the `nse` package is installed.

- [ ] **Step 1: Write the failing test**

```python
"""AUD-086: OffMarketFetcher and FnOFetcher called NSE() without the required
download_folder arg → constructor raised TypeError, the except branch logged
'nse package unavailable' (mislabel), and off-market + F&O context was
structurally empty (~16×/day in prod)."""
import sys
import types

import pytest


class _StrictNSE:
    """Mimics nse.NSE: download_folder is a REQUIRED positional arg."""
    def __init__(self, download_folder):
        self.download_folder = download_folder


@pytest.fixture()
def strict_nse_module(monkeypatch):
    mod = types.ModuleType("nse")
    mod.NSE = _StrictNSE
    monkeypatch.setitem(sys.modules, "nse", mod)


def test_offmarket_fetcher_constructs_client(strict_nse_module):
    from core.intelligence.rl.stores.offmarket_fetcher import OffMarketFetcher
    f = OffMarketFetcher()
    assert f._nse is not None, "NSE() ctor failed — download_folder not passed (AUD-086)"


def test_fno_fetcher_constructs_client(strict_nse_module):
    from core.intelligence.fno.fetcher import FnOFetcher
    f = FnOFetcher()
    assert f._nse is not None, "NSE() ctor failed — download_folder not passed (AUD-086)"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.stockai/Scripts/python.exe -m pytest tests/unit/test_nse_ctor_fetchers.py -v`
Expected: both FAIL — `_nse is None` (the strict ctor raises TypeError inside `__init__`'s try block).

- [ ] **Step 3: Fix both constructors**

In `core/intelligence/rl/stores/offmarket_fetcher.py`, replace the `__init__` body:

```python
from __future__ import annotations
import logging
import pathlib
import tempfile
from core.schemas.feedback import OffMarketSignals, BlockDeal, BulkDeal

logger = logging.getLogger(__name__)


class OffMarketFetcher:
    def __init__(self) -> None:
        try:
            from nse import NSE
            # download_folder is REQUIRED by the nse client (AUD-086);
            # mkdtemp matches every other NSE() call site in the repo.
            self._nse = NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))
        except Exception as exc:
            logger.warning("[OffMarketFetcher] nse package unavailable: %s", exc)
            self._nse = None
```

In `core/intelligence/fno/fetcher.py`, same change:

```python
from __future__ import annotations
import logging
import pathlib
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)


class FnOFetcher:
    def __init__(self) -> None:
        self.near_month_expiry: str | None = None
        try:
            from nse import NSE
            self._nse = NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))
        except Exception as exc:
            logger.warning("[FnOFetcher] nse package unavailable: %s", exc)
            self._nse = None
```

(The per-instance mkdtemp leak joins the existing AUD-017 batch — do NOT invent a shared-dir scheme here; consistency first.)

- [ ] **Step 4: Run tests**

Run: `.stockai/Scripts/python.exe -m pytest tests/unit/test_nse_ctor_fetchers.py tests/unit -k "offmarket or fno" -v`
Expected: new tests PASS, no existing offmarket/fno test regressions.

- [ ] **Step 5: Commit**

```bash
git add core/intelligence/rl/stores/offmarket_fetcher.py core/intelligence/fno/fetcher.py tests/unit/test_nse_ctor_fetchers.py
git commit -m "fix(rl): pass required download_folder to NSE() in offmarket + fno fetchers (AUD-086)"
```

---

### Task 3: AUD-100a — real `/ui/rl/*` routes

**Files:**
- Create: `services/api/routes/rl_monitor.py`
- Modify: `services/api/server.py` (import + `app.include_router(rl_monitor_router, tags=["RL Monitor"])` alongside the other routers at :413-422)
- Test: `tests/unit/test_rl_monitor_api.py` (create)

**Interfaces:**
- Consumes: `PredictionStore(ticker, sector=…, base_dir=…)` (`core.intelligence.rl.stores.prediction_store`) with `current_cycle_id()`, `list_cycles()`, `load_envelope(cycle_id)`, `load_feedback_log(cycle_id)`, `load_weight_memory()`, `load_learning_ledger()`; `_resolve_tickers(None)` from `services.api.routes.scheduler_api` → `[{"sym","sector"}]`; `FeedbackEntry` fields `date/predicted_close/actual_close/price_error_pct/direction_correct/miss_analysis`; `PredictionEnvelope.conviction_streak` (`current_verdict/streak_days/reversion_prior`) and `daily_forecasts[].confidence`.
- Produces: five GET routes whose JSON matches the mock shapes in `rl-data.jsx` exactly (the page consumes `available`, then the fields below). Task 4 relies on: `/ui/rl/tickers` → `{"tickers":[{sym,name,color,enabled,has_envelope,has_weights}]}`; per-ticker routes return `{"available": false}` when no data.

- [ ] **Step 1: Write the failing tests**

```python
"""AUD-100: the RL Monitor page fetched five /ui/rl/* routes that never existed.
These tests pin the new adapter routes to the page's contract (mock shapes in
rl-data.jsx)."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path, tickers=None):
    import services.api.routes.rl_monitor as rlm
    monkeypatch.setattr(
        rlm, "_managed",
        lambda: tickers if tickers is not None else [{"sym": "MARUTI", "sector": "automobile"}],
    )
    monkeypatch.setattr(rlm, "_BASE_DIR_OVERRIDE", str(tmp_path), raising=False)
    app = FastAPI()
    app.include_router(rlm.router)
    return TestClient(app)


def _seed_store(tmp_path, ticker="MARUTI", sector="automobile"):
    """Write a minimal envelope + feedback log + weight memory via the real store."""
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from core.schemas.feedback import (
        ConvictionStreak, DailyFeedbackLog, DailyForecast, FeedbackEntry,
        PredictionEnvelope, WeightMemory, WeightHistoryEntry,
    )
    store = PredictionStore(ticker, sector=sector, base_dir=str(tmp_path))
    cycle = store.current_cycle_id()
    from datetime import date
    today = date.today().isoformat()
    env = PredictionEnvelope(
        ticker=ticker, sector=sector, cycle_id=cycle, generated_at=today,
        base_close=100.0, weight_version_used=2,
        daily_forecasts=[DailyForecast(day=1, date=today, predicted_close=101.0,
                                       predicted_verdict="BUY", confidence=0.7)],
        conviction_streak=ConvictionStreak(current_verdict="BUY", streak_days=3,
                                           reversion_prior=0.1),
    )
    store.save_envelope(env)
    fb = DailyFeedbackLog(ticker=ticker, cycle_id=cycle, entries=[
        FeedbackEntry(day=1, date=today, predicted_close=101.0, actual_close=102.0,
                      price_error_pct=0.99, predicted_verdict="BUY",
                      actual_direction="UP", direction_correct=True),
    ])
    store.save_feedback_log(fb)
    wm = WeightMemory(ticker=ticker, sector=sector, last_updated=today,
                      weight_version=2,
                      current_weights={"fundamentals": 0.6, "sentiment": 0.4},
                      base_weights={"fundamentals": 0.5, "sentiment": 0.5},
                      weight_history=[WeightHistoryEntry(
                          version=2, date=today, reason="test",
                          weights={"fundamentals": 0.6, "sentiment": 0.4})])
    store.save_weight_memory(wm)
    return cycle


def test_tickers_route_shape(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/tickers").json()
    assert d["tickers"], "managed list must map to tickers"
    t = d["tickers"][0]
    assert set(t) >= {"sym", "name", "color", "enabled", "has_envelope", "has_weights"}
    assert t["sym"] == "MARUTI" and t["has_envelope"] is True and t["has_weights"] is True


def test_summary_route(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/summary/MARUTI").json()
    assert d["available"] is True
    assert d["total_entries"] == 1 and d["direction_hits"] == 1
    assert d["direction_accuracy_pct"] == 100.0
    assert d["current_verdict"] == "BUY" and d["streak_days"] == 3
    assert d["weight_version"] == 2


def test_predictions_route(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/predictions/MARUTI").json()
    assert d["available"] is True and len(d["days"]) == 1
    day = d["days"][0]
    assert day["predicted"] == 101.0 and day["actual"] == 102.0
    assert day["direction_hit"] is True and day["confidence"] == 0.7


def test_weights_route(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/weights/MARUTI").json()
    assert d["available"] is True
    assert d["current_weights"]["fundamentals"] == 0.6
    assert d["weight_history"][0]["version"] == 2


def test_misses_route_empty_but_available(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/misses/MARUTI").json()
    assert d["available"] is True and d["miss_type_counts"] == {}


def test_unknown_ticker_404_and_no_dir_created(monkeypatch, tmp_path):
    """AUD-024 class: an arbitrary URL ticker must NOT construct a
    PredictionStore (which mkdirs on init)."""
    c = _client(monkeypatch, tmp_path)
    assert c.get("/ui/rl/summary/EVIL").status_code == 404
    assert not (tmp_path / "automobile" / "EVIL").exists()


def test_no_data_returns_available_false(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)  # managed, but nothing seeded
    d = c.get("/ui/rl/summary/MARUTI").json()
    assert d["available"] is False
```

(`core.schemas.feedback` is the import `prediction_store.py` itself uses; `save_envelope`/`save_feedback_log`/`save_weight_memory` verified present at prediction_store.py:188/258/352. If `WeightHistoryEntry` lives under a different name in `core.schemas.feedback`, mirror whatever `WeightMemory.weight_history` declares.)

- [ ] **Step 2: Run to verify failure**

Run: `.stockai/Scripts/python.exe -m pytest tests/unit/test_rl_monitor_api.py -v`
Expected: FAIL at import — `No module named 'services.api.routes.rl_monitor'`.

- [ ] **Step 3: Implement the router**

Create `services/api/routes/rl_monitor.py`:

```python
"""
services/api/routes/rl_monitor.py
=================================
Real backing for the RL Monitor page (AUD-100). Five read-only adapters over
PredictionStore matching the shapes rl-data.jsx already consumes. No auth:
read-only GETs, same posture as the other /ui reads (Wave B gates writes only).

Tickers are validated against the managed list BEFORE any PredictionStore is
constructed — the store mkdirs on init (AUD-024 class), so unknown symbols 404
without touching the filesystem.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ui/rl", tags=["RL Monitor"])

# Test seam: overrides PredictionStore base_dir when set (None in prod).
_BASE_DIR_OVERRIDE: str | None = None

_CHIP_COLORS = ["#0891b2", "#7c3aed", "#16a34a", "#d97706", "#dc2626",
                "#0ea5e9", "#db2777", "#65a30d", "#9333ea", "#ea580c",
                "#0d9488", "#4f46e5", "#ca8a04", "#e11d48", "#059669", "#6d28d9"]


def _managed() -> list[dict]:
    """[{'sym','sector'}] for all managed tickers (scheduler source of truth)."""
    from services.api.routes.scheduler_api import _resolve_tickers
    return _resolve_tickers(None)


def _entry_for(ticker: str) -> dict:
    sym = ticker.strip().upper()
    for e in _managed():
        if e["sym"] == sym:
            return e
    raise HTTPException(status_code=404, detail="unknown ticker")


def _store(entry: dict):
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    return PredictionStore(entry["sym"], sector=entry.get("sector", "automobile"),
                           base_dir=_BASE_DIR_OVERRIDE)


def _all_entries(store) -> list:
    entries = []
    for cycle_id in store.list_cycles():
        fb = store.load_feedback_log(cycle_id)
        if fb and fb.entries:
            entries.extend(fb.entries)
    entries.sort(key=lambda e: e.date)
    return entries


@router.get("/tickers", summary="Managed tickers with RL data flags")
async def rl_tickers() -> dict:
    out = []
    for i, e in enumerate(_managed()):
        row = {"sym": e["sym"], "name": e.get("name", e["sym"]),
               "color": _CHIP_COLORS[i % len(_CHIP_COLORS)],
               "enabled": bool(e.get("enabled", True)),
               "has_envelope": False, "has_weights": False}
        try:
            store = _store(e)
            row["has_envelope"] = store.load_envelope(store.current_cycle_id()) is not None
            wm = store.load_weight_memory()
            row["has_weights"] = bool(wm and wm.weight_version > 0)
        except Exception as exc:
            logger.debug("[rl_monitor] tickers flags failed for %s: %s", e["sym"], exc)
        out.append(row)
    return {"tickers": out}


@router.get("/summary/{ticker}", summary="RL summary card data for a ticker")
async def rl_summary(ticker: str) -> dict:
    e = _entry_for(ticker)
    store = _store(e)
    env = store.load_envelope(store.current_cycle_id())
    entries = _all_entries(store)
    if not entries and env is None:
        return {"available": False, "ticker": e["sym"]}
    wm = store.load_weight_memory()
    ledger = store.load_learning_ledger()
    hits = sum(1 for x in entries if x.direction_correct)
    total = len(entries)
    miss_counter = (ledger.miss_counter or {}) if ledger else {}
    streak = env.conviction_streak if env else None
    return {
        "available": True,
        "ticker": e["sym"],
        "cycle_id": store.current_cycle_id(),
        "direction_accuracy_pct": round(hits / total * 100, 1) if total else 0.0,
        "total_entries": total,
        "total_days": total,
        "direction_hits": hits,
        "avg_price_error_pct": round(
            sum(abs(x.price_error_pct) for x in entries) / total, 2) if total else 0.0,
        "weight_version": wm.weight_version if wm else 0,
        "lesson_count": len(ledger.lessons) if ledger else 0,
        "top_miss_factor": max(miss_counter, key=miss_counter.get) if miss_counter else "",
        "current_verdict": streak.current_verdict if streak else "",
        "streak_days": streak.streak_days if streak else 0,
        "reversion_prior": streak.reversion_prior if streak else 0.0,
    }


@router.get("/predictions/{ticker}", summary="Per-day predicted vs actual rows")
async def rl_predictions(ticker: str, limit: int = 30) -> dict:
    e = _entry_for(ticker)
    store = _store(e)
    entries = _all_entries(store)
    if not entries:
        return {"available": False, "ticker": e["sym"], "days": []}
    env = store.load_envelope(store.current_cycle_id())

    def _confidence(d: str) -> float:
        f = env.get_forecast(d) if env else None
        return f.confidence if f else 0.5

    days = [{
        "date": x.date,
        "predicted": round(x.predicted_close, 2),
        "actual": round(x.actual_close, 2),
        "error_pct": round(abs(x.price_error_pct), 2),
        "direction_hit": x.direction_correct,
        "confidence": _confidence(x.date),
        "miss_type": (str(x.miss_analysis.miss_type)
                      if x.miss_analysis and x.miss_analysis.miss_type else None),
    } for x in entries[-limit:]]
    return {"available": True, "ticker": e["sym"], "days": days}


@router.get("/weights/{ticker}", summary="Agent weight state + history")
async def rl_weights(ticker: str) -> dict:
    e = _entry_for(ticker)
    wm = _store(e).load_weight_memory()
    if not wm:
        return {"available": False, "ticker": e["sym"]}
    return {
        "available": True,
        "ticker": e["sym"],
        "base_weights": dict(wm.base_weights or {}),
        "current_weights": dict(wm.current_weights or {}),
        "weight_history": [
            {"version": h.version, "date": h.date, "reason": h.reason,
             "weights": dict(h.weights)}
            for h in sorted(wm.weight_history or [], key=lambda h: h.date)
        ],
    }


@router.get("/misses/{ticker}", summary="Miss attribution counts")
async def rl_misses(ticker: str) -> dict:
    e = _entry_for(ticker)
    store = _store(e)
    entries = _all_entries(store)
    ledger = store.load_learning_ledger()
    if not entries and not (ledger and ledger.lessons):
        return {"available": False, "ticker": e["sym"]}
    miss_type_counts: dict[str, int] = {}
    for x in entries:
        if x.miss_analysis and x.miss_analysis.miss_type:
            mt = str(x.miss_analysis.miss_type)
            miss_type_counts[mt] = miss_type_counts.get(mt, 0) + 1
    miss_counter = (ledger.miss_counter or {}) if ledger else {}
    top = dict(sorted(miss_counter.items(), key=lambda kv: -kv[1])[:5])
    return {
        "available": True,
        "ticker": e["sym"],
        "miss_type_counts": miss_type_counts,
        "top_missed_factors": top,
        "lesson_count": len(ledger.lessons) if ledger else 0,
    }
```

Register in `services/api/server.py`: import `rl_monitor_router` where the other routers are imported, and add `app.include_router(rl_monitor_router, tags=["RL Monitor"])` after the `analytics_router` line (order before the catch-all is automatic — the catch-all registers last).

- [ ] **Step 4: Run tests**

Run: `.stockai/Scripts/python.exe -m pytest tests/unit/test_rl_monitor_api.py -v`
Expected: all PASS. Fix shape drift by reading `prediction_store.py`, not by weakening asserts.

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/rl_monitor.py services/api/server.py tests/unit/test_rl_monitor_api.py
git commit -m "feat(api): real /ui/rl/* routes backing the RL Monitor page (AUD-100)"
```

---

### Task 4: AUD-100b — page stops silently showing mocks

**Files:**
- Modify: `src/frontend/prototypes/rl-data.jsx:177-212`
- Modify: `src/frontend/prototypes/rl-monitor.jsx:695-713`
- Modify: `src/frontend/prototypes/sw.js` (bump cache version, PWA convention from Wave B `v2→v3` → now `v3→v4`)

No JS test infra exists (in-browser Babel prototype) — verification is the Task 6 smoke.

- [ ] **Step 1: Make the loader authoritative when the API answers**

In `rl-data.jsx`, replace the `loadRLData` IIFE (lines ~180-192):

```javascript
(async function loadRLData() {
  try {
    const res = await fetch('/ui/rl/tickers');
    if (!res.ok) return;                    // 404/500 → keep mock demo data
    const d = await res.json();             // HTML → throws → keep mocks
    if (Array.isArray(d.tickers)) {
      window.RL_TICKERS = d.tickers;
      window.__rlApiReady = true;           // live contract answered: mocks are dead
    }
  } catch {
    // API unreachable or non-JSON — keep mock RL_TICKERS as demo data
  }
})();
```

- [ ] **Step 2: Stop the mock fallback once the API is live**

In `rl-monitor.jsx` (effect at ~695), mocks must only seed the view when the API never answered:

```javascript
  useEffectRL(() => {
    const sym = activeTicker;
    const live = window.__rlApiReady;
    setData({
      summary:     live ? null : (window.RL_SUMMARIES?.[sym]   || null),
      predictions: live ? []   : (window.RL_PREDICTIONS?.[sym] || []),
      weights:     live ? null : (window.RL_WEIGHTS?.[sym]     || null),
      misses:      live ? null : (window.RL_MISSES?.[sym]      || null),
    });
    setLoading(true);
    window.rlFetch(sym).then(fetched => {
      setData(prev => window.__rlApiReady ? {
        summary:     fetched.summary,
        predictions: fetched.predictions ?? [],
        weights:     fetched.weights,
        misses:      fetched.misses,
      } : {
        summary:     fetched.summary     ?? prev.summary,
        predictions: fetched.predictions?.length ? fetched.predictions : prev.predictions,
        weights:     fetched.weights     ?? prev.weights,
        misses:      fetched.misses      ?? prev.misses,
      });
      setLoading(false);
    });
  }, [activeTicker]);
```

(The page already has a "No RL data yet" empty-state card at ~757 — live-but-empty tickers now reach it instead of impersonating mock data.)

- [ ] **Step 3: Bump the service-worker cache version** in `sw.js` (find the `vN` cache-name constant, increment) so installed PWAs pick up the new JSX.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/prototypes/rl-data.jsx src/frontend/prototypes/rl-monitor.jsx src/frontend/prototypes/sw.js
git commit -m "fix(ui): RL Monitor uses live /ui/rl data; mocks only when API unreachable (AUD-100)"
```

---

### Task 5: AUD-100c — catch-all 404s unknown API paths

**Files:**
- Modify: `services/api/server.py:467-474` (the `spa()` catch-all)
- Test: `tests/unit/test_spa_catchall.py` (create)

**Interfaces:**
- Consumes: the full `services.api.server.app` (routers registered before the catch-all take precedence).
- Produces: unknown paths under API namespaces → HTTP 404; real files and `/` unchanged.

- [ ] **Step 1: Write the failing test**

```python
"""AUD-100c: the SPA catch-all served index.html with HTTP 200 for ANY path,
masking phantom API routes (rl-data.jsx shipped against 5 nonexistent routes
for a month). Unknown API-namespace paths must 404 loudly."""
from fastapi.testclient import TestClient

from services.api.server import app

c = TestClient(app, raise_server_exceptions=False)


def test_unknown_api_paths_404():
    for path in ("/ui/rl/nope", "/ui/nope", "/api/nope", "/scheduler/nope",
                 "/analytics/nope", "/portfolio/nope/nope", "/delivery/nope",
                 "/discovery/nope", "/history/x/y/z/nope", "/ws/nope"):
        r = c.get(path)
        assert r.status_code == 404, f"{path} -> {r.status_code} (should be 404)"
        assert "text/html" not in r.headers.get("content-type", ""), path


def test_root_and_real_files_still_served():
    assert c.get("/").status_code == 200
    assert "text/html" in c.get("/").headers["content-type"]
    assert c.get("/rl-data.jsx").status_code == 200
    assert c.get("/manifest.json").status_code == 200


def test_registered_api_routes_unaffected():
    assert c.get("/health").status_code == 200
    assert c.get("/ui/rl/tickers").status_code == 200  # Task 3 route, not catch-all
```

- [ ] **Step 2: Run to verify failure**

Run: `.stockai/Scripts/python.exe -m pytest tests/unit/test_spa_catchall.py -v`
Expected: `test_unknown_api_paths_404` FAILS (200 + text/html today); the other two PASS.

- [ ] **Step 3: Implement**

In `services/api/server.py`, inside the `if _FRONTEND_DIR is not None:` block, replace the catch-all:

```python
    # API namespaces: an unmatched path here is a broken contract, not a SPA
    # route (the prototype does no URL routing — UI_SPEC.md). Serving
    # index.html@200 for these hid 5 phantom /ui/rl/* routes for a month
    # (AUD-100) — fail loudly instead.
    _API_NAMESPACES = (
        "ui/", "api/", "scheduler/", "analytics/", "portfolio/", "discovery/",
        "delivery/", "history/", "ws/", "analyse",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path:
            candidate = (_FRONTEND_DIR / full_path).resolve()
            # Guard against path traversal outside the build dir
            if str(candidate).startswith(str(_FRONTEND_ROOT)) and candidate.is_file():
                return FileResponse(candidate)
            if full_path.startswith(_API_NAMESPACES):
                raise HTTPException(status_code=404, detail="unknown API path")
        return FileResponse(_FRONTEND_DIR / "index.html")
```

(`HTTPException` is already imported in server.py — verify, else add it.)

- [ ] **Step 4: Run tests**

Run: `.stockai/Scripts/python.exe -m pytest tests/unit/test_spa_catchall.py tests/unit/test_rl_monitor_api.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/server.py tests/unit/test_spa_catchall.py
git commit -m "fix(api): SPA catch-all 404s unknown API-namespace paths (AUD-100c)"
```

---

### Task 6: Full suite, smoke, ledger, ship

- [ ] **Step 1: Full unit suite**

Run: `.stockai/Scripts/python.exe -m pytest tests/unit 2>&1 | tail -3`
Expected: only the 1 known pre-existing failure (`test_find_qualifying_events_unparseable_date_skipped`) + 5 skips.

- [ ] **Step 2: Local smoke** — start the server (`.stockai/Scripts/python.exe -m uvicorn services.api.server:app --port 8001`), then:
  - `GET http://localhost:8001/ui/rl/tickers` → JSON with the managed tickers (local data may mark flags false — fine).
  - `GET http://localhost:8001/ui/rl/summary/<a managed sym>` → JSON with `available` true/false (never HTML).
  - `GET http://localhost:8001/ui/rl/bogus` → 404.
  - Open `http://localhost:8001/` → RL Monitor page renders (live-empty state or live data, no mock KPI numbers when API answered).

- [ ] **Step 3: LEDGER update** — mark AUD-078, AUD-086, AUD-100 → FIXED with commit hashes in `docs/audit/LEDGER.md` (Phase 6/7/8 tables) + short Wave C section (public-repo-safe wording). Note the FnOFetcher rider on AUD-086.

- [ ] **Step 4: Merge + push** (ff-merge if on a branch/worktree; push = Railway auto-deploy).

- [ ] **Step 5: Post-deploy verification (prod, read-only)**
  - `GET <prod>/ui/rl/tickers` returns the 16 managed tickers with flags.
  - `GET <prod>/ui/rl/summary/MARUTI` → `available: true` with real accuracy numbers.
  - `GET <prod>/ui/rl/nope` → 404.
  - Deploy log: no `nsepython not installed` and no `nse package unavailable` lines at the next 16:30 IST review; next morning brief shows populated `Overnight:` lines (closes the AUD-085 email observation).
  - Update memory + LEDGER status after the next trading-day watch.
