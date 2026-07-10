# Compass Autopilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-execute the Position Advisor's daily verdicts (ADD/TRIM/EXIT/SWITCH) on the virtual portfolio with a full transaction audit trail, value history, seed script, API, and portfolio-page P&L/activity UI.

**Architecture:** A new pure-decision executor (`core/portfolio/autopilot.py`) is called from `run_post_review_pipeline` between advice generation and digest. State lives in the existing per-user `PortfolioStore` plus two new append-only JSONL ledgers (`transactions.jsonl`, `value_history.jsonl`). The LLM never decides — the executor is deterministic over `AdviceRecord`s.

**Tech Stack:** Python 3.11 / pydantic v2 / FastAPI / pytest; React (in-browser JSX prototype, no build step).

**Spec:** `docs/superpowers/specs/2026-07-10-compass-autopilot-design.md` — read it first; every parameter below comes from there.

## Global Constraints

- Virtual money only. No broker calls, ever. LLM never decides trades.
- All quantities traded are **whole shares** (`math.floor`); fees = 0.
- Execution price = the close the advisor used (`AdviceRecord.close`, fallback `closes[symbol]`); SWITCH buy leg prices via `close_on(candidate, review_date)`.
- Guardrail defaults (config-backed): add tranche 25% of position value, trim 25% of qty, min cash floor ₹10,000, ADD cooldown 5 trading days, post-trade position weight ≤ `settings.ADVISOR_MAX_POSITION_PCT` (10%).
- Idempotency: skip run if `portfolio.last_autopilot_run == review_date`; skip any trade whose `txn_id` already exists in the ledger.
- Every pipeline step is non-fatal (log + continue), matching existing pipeline style.
- Autopilot OFF (`portfolio.autopilot=False` or `cash_deployable is None`) must leave `portfolio.json` byte-identical through a pipeline run.
- Never write under `data/rl/paper/` or any PredictionStore path (paper-lane isolation invariant).
- Follow existing file style: module docstrings citing the spec, `logger = logging.getLogger(__name__)`, tolerant JSONL readers.
- Test baseline: 1831 passed / 5 skipped (plus known pre-existing failures: 3 contract SignalAggregator + orchestrator stale mocks — do NOT fix, do NOT break further).
- Run tests with `python -m pytest` from repo root (Windows dev box; CI-equivalent).

---

### Task 1: Schemas — TransactionRecord, Portfolio cash fields, Holding.sell()

**Files:**
- Modify: `src/backend/shared/schemas/portfolio.py`
- Test: `tests/unit/test_autopilot_schemas.py` (create)

**Interfaces:**
- Produces: `TransactionRecord` (pydantic model, fields below); `Portfolio.capital_in: float`, `Portfolio.autopilot: bool`, `Portfolio.last_autopilot_run: str`; `Holding.sell(sell_qty: float, price: float) -> float` (returns realized P&L incl. pro-rata dividends, reduces `adj_qty` and `dividends_received` in place, raw `qty`/`avg_buy_price` untouched — they stay "as entered"); `WatchlistItem.source` accepts `"autopilot"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_autopilot_schemas.py
"""Compass Autopilot — schema unit tests (spec §3)."""
import pytest

from backend.shared.schemas.portfolio import (
    Holding, Portfolio, TransactionRecord, WatchlistItem,
)


def _holding(qty=10.0, price=100.0, dividends=0.0):
    return Holding(
        symbol="MARUTI", sector="automobile", qty=qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=qty, buy_date="2026-07-11",
        dividends_received=dividends,
    )


def test_transaction_record_roundtrip():
    t = TransactionRecord(
        txn_id="abc123", date="2026-07-11", ts="2026-07-11T12:00:00+00:00",
        user_id="primary", symbol="MARUTI", side="BUY", qty=5, price=100.0,
        value=500.0, cash_before=1000.0, cash_after=500.0,
        holding_qty_after=5, source="seed",
    )
    assert TransactionRecord(**t.model_dump()) == t
    assert t.realized_pnl == 0.0 and t.verdict == "" and t.triggers == []


def test_portfolio_new_fields_default_off():
    p = Portfolio(user_id="u")
    assert p.capital_in == 0.0
    assert p.autopilot is False
    assert p.last_autopilot_run == ""
    assert p.cash_deployable is None          # legacy default untouched


def test_watchlist_source_accepts_autopilot():
    w = WatchlistItem(symbol="X", added="2026-07-11", source="autopilot")
    assert w.source == "autopilot"


def test_holding_sell_partial_realizes_pro_rata_dividends():
    h = _holding(qty=10, price=100.0, dividends=50.0)
    realized = h.sell(5, 120.0)
    # (120-100)*5 + 50*0.5 = 125
    assert realized == pytest.approx(125.0)
    assert h.adj_qty == pytest.approx(5.0)
    assert h.dividends_received == pytest.approx(25.0)
    assert h.qty == 10.0                      # raw stays "as entered"


def test_holding_sell_full_and_overdraw_rejected():
    h = _holding(qty=10, price=100.0)
    assert h.sell(10, 90.0) == pytest.approx(-100.0)
    assert h.adj_qty == pytest.approx(0.0)
    h2 = _holding(qty=2, price=100.0)
    with pytest.raises(ValueError):
        h2.sell(3, 100.0)
    with pytest.raises(ValueError):
        h2.sell(0, 100.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_autopilot_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'TransactionRecord'`

- [ ] **Step 3: Implement the schema changes**

In `src/backend/shared/schemas/portfolio.py`:

Change `WatchlistItem.source` line to:
```python
    source: Literal["user", "discovery", "autopilot"] = "user"
```

Add to `Holding` (below `age_days`):
```python
    def sell(self, sell_qty: float, price: float) -> float:
        """Reduce the live (adj_*) position by sell_qty shares at price.
        Returns realized P&L incl. pro-rata dividends; moves that dividend
        slice out of dividends_received so remaining unrealised P&L doesn't
        double-count it. Raw qty/avg_buy_price stay as entered (entry
        history); adj_* is the live position (Autopilot spec §3/§4)."""
        if sell_qty <= 0 or sell_qty > self.adj_qty + 1e-9:
            raise ValueError(
                f"invalid sell qty {sell_qty} for {self.symbol} (adj_qty={self.adj_qty})"
            )
        fraction = min(1.0, sell_qty / self.adj_qty)
        realized = (price - self.adj_avg_price) * sell_qty \
            + self.dividends_received * fraction
        self.dividends_received = round(self.dividends_received * (1 - fraction), 2)
        self.adj_qty = round(self.adj_qty - sell_qty, 6)
        return round(realized, 2)
```

Add to `Portfolio` (after `cash_deployable`):
```python
    capital_in: float = 0.0                   # total mock money ever put in
    autopilot: bool = False                   # advisor-executed trading opt-in
    last_autopilot_run: str = ""              # ISO date of last executed run
```

Add after `AdviceRecord`:
```python
class TransactionRecord(BaseModel):
    """One executed virtual trade (append-only transactions.jsonl —
    Autopilot spec §3.2). The ledger is the audit authority; portfolio.json
    is derived state."""
    txn_id: str                    # sha256(user|date|symbol|side|ref)[:16]
    date: str                      # trade/review date (ISO)
    ts: str                        # UTC timestamp (ISO)
    user_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: float                     # whole shares
    price: float
    value: float                   # qty × price
    cash_before: float
    cash_after: float
    holding_qty_after: float
    realized_pnl: float = 0.0      # SELL only
    source: Literal["autopilot", "seed", "manual"] = "autopilot"
    verdict: str = ""              # originating advisor verdict, "" for seed/manual
    advice_ref: str = ""           # "<date>|<symbol>|<rationale_hash>"
    triggers: list[str] = Field(default_factory=list)
    note: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_autopilot_schemas.py -v`
Expected: 5 PASS

- [ ] **Step 5: Regression + commit**

Run: `python -m pytest tests/unit -k "portfolio or schema" -q` — no new failures.
```bash
git add src/backend/shared/schemas/portfolio.py tests/unit/test_autopilot_schemas.py
git commit -m "feat(autopilot): TransactionRecord + cash/capital fields + Holding.sell()"
```

---

### Task 2: Store — transaction & value-history ledgers, reduce_holding

**Files:**
- Modify: `core/portfolio/store.py`
- Test: `tests/unit/test_autopilot_store.py` (create)

**Interfaces:**
- Consumes: `TransactionRecord`, `Holding.sell` (Task 1).
- Produces: `PortfolioStore.append_transaction(rec: TransactionRecord) -> None`; `load_transactions(limit: int = 200) -> list[TransactionRecord]` (file order, oldest→newest of tail); `append_value_point(point: dict) -> None`; `load_value_history(limit: int = 400) -> list[dict]`; `reduce_holding(symbol: str, sell_qty: float, price: float) -> tuple[float, bool]` (realized P&L, removed?) — loads, sells, drops the holding when adj_qty ≤ 1e-9, saves.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_autopilot_store.py
"""Compass Autopilot — store ledger tests (spec §3.2/§3.3)."""
import pytest

from backend.shared.schemas.portfolio import Holding, TransactionRecord
from core.portfolio.store import PortfolioStore


def _store(tmp_path):
    return PortfolioStore(user_id="t1", base_dir=str(tmp_path))


def _txn(i=0, side="BUY"):
    return TransactionRecord(
        txn_id=f"id{i}", date="2026-07-11", ts="2026-07-11T12:00:00+00:00",
        user_id="t1", symbol="MARUTI", side=side, qty=1, price=100.0,
        value=100.0, cash_before=1000.0, cash_after=900.0, holding_qty_after=1,
    )


def test_transactions_append_and_tail_load(tmp_path):
    s = _store(tmp_path)
    assert s.load_transactions() == []
    for i in range(5):
        s.append_transaction(_txn(i))
    got = s.load_transactions(limit=3)
    assert [t.txn_id for t in got] == ["id2", "id3", "id4"]   # tail, file order


def test_transactions_tolerate_bad_lines(tmp_path):
    s = _store(tmp_path)
    s.append_transaction(_txn(1))
    (tmp_path / "t1" / "transactions.jsonl").open("a", encoding="utf-8").write("{broken\n")
    s.append_transaction(_txn(2))
    assert [t.txn_id for t in s.load_transactions()] == ["id1", "id2"]


def test_value_history_roundtrip(tmp_path):
    s = _store(tmp_path)
    assert s.load_value_history() == []
    s.append_value_point({"date": "2026-07-11", "total_equity": 100.0})
    s.append_value_point({"date": "2026-07-12", "total_equity": 101.0})
    hist = s.load_value_history(limit=1)
    assert hist == [{"date": "2026-07-12", "total_equity": 101.0}]


def test_reduce_holding_partial_and_full(tmp_path):
    s = _store(tmp_path)
    s.add_holding(Holding(symbol="MARUTI", sector="automobile", qty=10,
                          avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=10,
                          buy_date="2026-07-01"))
    realized, removed = s.reduce_holding("MARUTI", 4, 110.0)
    assert realized == pytest.approx(40.0) and removed is False
    assert s.load().holdings[0].adj_qty == pytest.approx(6.0)
    realized, removed = s.reduce_holding("MARUTI", 6, 90.0)
    assert realized == pytest.approx(-60.0) and removed is True
    assert s.load().holdings == []
    with pytest.raises(ValueError):
        s.reduce_holding("NOPE", 1, 100.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_autopilot_store.py -v`
Expected: FAIL — `AttributeError: ... no attribute 'append_transaction'`

- [ ] **Step 3: Implement store methods**

In `core/portfolio/store.py` — import `TransactionRecord` alongside the other schema imports; add paths next to `_ledger_path`:

```python
    def _transactions_path(self) -> Path:
        return self._dir / "transactions.jsonl"

    def _value_history_path(self) -> Path:
        return self._dir / "value_history.jsonl"
```

Add after the advice-ledger section (mirror its tolerant-reader style):

```python
    # ------------------------------------------------------------------
    # Transactions ledger (append-only JSONL — Autopilot spec §3.2)
    # ------------------------------------------------------------------
    def append_transaction(self, rec: TransactionRecord) -> None:
        with open(self._transactions_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.model_dump(), ensure_ascii=False) + "\n")

    def load_transactions(self, limit: int = 200) -> list[TransactionRecord]:
        path = self._transactions_path()
        if not path.exists():
            return []
        records: list[TransactionRecord] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(TransactionRecord(**json.loads(line)))
            except Exception as exc:
                logger.warning("[PortfolioStore] skipping bad txn line: %s", exc)
        return records

    # ------------------------------------------------------------------
    # Daily value history (append-only JSONL — Autopilot spec §3.3)
    # ------------------------------------------------------------------
    def append_value_point(self, point: dict) -> None:
        with open(self._value_history_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(point, ensure_ascii=False) + "\n")

    def load_value_history(self, limit: int = 400) -> list[dict]:
        path = self._value_history_path()
        if not path.exists():
            return []
        points: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                points.append(json.loads(line))
            except Exception as exc:
                logger.warning("[PortfolioStore] skipping bad value line: %s", exc)
        return points

    def reduce_holding(self, symbol: str, sell_qty: float, price: float) -> tuple[float, bool]:
        """Sell sell_qty shares of symbol at price. Returns (realized_pnl,
        removed). Raises ValueError for unknown symbol or overdraw."""
        p = self.load()
        h = next((x for x in p.holdings if x.symbol == symbol.upper()), None)
        if h is None:
            raise ValueError(f"no holding {symbol.upper()}")
        realized = h.sell(sell_qty, price)
        removed = h.adj_qty <= 1e-9
        if removed:
            p.holdings = [x for x in p.holdings if x.symbol != h.symbol]
        self.save(p)
        return realized, removed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_autopilot_store.py -v`
Expected: 4 PASS

- [ ] **Step 5: Regression + commit**

Run: `python -m pytest tests/unit -k "store" -q` — no new failures.
```bash
git add core/portfolio/store.py tests/unit/test_autopilot_store.py
git commit -m "feat(autopilot): transactions + value-history ledgers, reduce_holding"
```

---

### Task 3: Settings — AUTOPILOT_* config keys

**Files:**
- Modify: `src/backend/shared/config/settings/base.py` (append to the Compass block, after `DISCOVERY_HISTORY_DAYS` ~line 779)
- Test: `tests/unit/test_autopilot_settings.py` (create)

**Interfaces:**
- Produces: `settings.AUTOPILOT_ENABLED: bool` (default True), `AUTOPILOT_ADD_TRANCHE_PCT: float` (25.0), `AUTOPILOT_TRIM_PCT: float` (25.0), `AUTOPILOT_MIN_CASH_FLOOR: float` (10000.0), `AUTOPILOT_ADD_COOLDOWN_TD: int` (5).

- [ ] **Step 1: Write the failing test** (mirror `tests/unit/test_discovery_settings.py`)

```python
# tests/unit/test_autopilot_settings.py
from core.config import settings


def test_autopilot_settings_defaults():
    assert settings.AUTOPILOT_ENABLED is True
    assert settings.AUTOPILOT_ADD_TRANCHE_PCT == 25.0
    assert settings.AUTOPILOT_TRIM_PCT == 25.0
    assert settings.AUTOPILOT_MIN_CASH_FLOOR == 10000.0
    assert settings.AUTOPILOT_ADD_COOLDOWN_TD == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_autopilot_settings.py -v`
Expected: FAIL — `AttributeError: AUTOPILOT_ENABLED`

- [ ] **Step 3: Add settings** (copy the exact `cfg()` idiom used by `ADVISOR_ENABLED` for the bool — check it first; numeric ones mirror `ADVISOR_TRIM_PROFIT_PCT` / `DISCOVERY_HISTORY_DAYS`)

```python
# --- Compass Autopilot (spec docs/superpowers/specs/2026-07-10-compass-autopilot-design.md)
AUTOPILOT_ENABLED: bool = cfg("autopilot.enabled", fallback=True)
AUTOPILOT_ADD_TRANCHE_PCT: float = cfg("autopilot.add_tranche_pct", fallback=25.0)
AUTOPILOT_TRIM_PCT: float = cfg("autopilot.trim_pct", fallback=25.0)
AUTOPILOT_MIN_CASH_FLOOR: float = cfg("autopilot.min_cash_floor", fallback=10000.0)
AUTOPILOT_ADD_COOLDOWN_TD: int = int(cfg("autopilot.add_cooldown_td", fallback=5))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_autopilot_settings.py tests/unit/test_discovery_settings.py -v`
Expected: PASS (both files)

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/config/settings/base.py tests/unit/test_autopilot_settings.py
git commit -m "feat(autopilot): AUTOPILOT_* settings (config.yaml autopilot.* keys)"
```

---

### Task 4: Executor — sell side (EXIT, TRIM, watchlist move) + run gating

**Files:**
- Create: `core/portfolio/autopilot.py`
- Test: `tests/unit/test_autopilot_executor_sells.py` (create)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `execute_advice(store: PortfolioStore, portfolio: Portfolio, advice: list[AdviceRecord], closes: dict[str, float], review_date: date, sector_lookup: dict[str, str] | None = None) -> list[TransactionRecord]`; `make_txn_id(user_id, d, symbol, side, ref) -> str`. Buys/SWITCH are completed in Tasks 5–6 — this task lands the skeleton with sell handling; `_execute_buys(...)` exists as a stub returning `[]` (replaced in Task 5).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_autopilot_executor_sells.py
"""Autopilot executor — sell side (spec §4)."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.portfolio.autopilot import execute_advice, make_txn_id
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)          # a Monday (trading day)


def _store(tmp_path, holdings, cash=50000.0, autopilot=True):
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path))
    p = s.load()
    p.holdings = holdings
    p.cash_deployable = cash
    p.capital_in = 100000.0
    p.autopilot = autopilot
    s.save(p)
    return s


def _h(sym="MARUTI", qty=10.0, price=100.0):
    return Holding(symbol=sym, sector="automobile", qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date="2026-06-01")


def _advice(sym="MARUTI", verdict="HOLD", close=110.0, confidence=0.5,
            switch_candidate=""):
    return AdviceRecord(date=D.isoformat(), user_id="t1", symbol=sym,
                        verdict=verdict, close=close, unrealised_pnl_pct=10.0,
                        stop_pct=8.0, confidence=confidence,
                        switch_candidate=switch_candidate,
                        rationale_hash="feedbeef")


def test_gating_off_no_writes(tmp_path):
    s = _store(tmp_path, [_h()], autopilot=False)
    before = (tmp_path / "t1" / "portfolio.json").read_bytes()
    txns = execute_advice(s, s.load(), [_advice(verdict="EXIT")], {"MARUTI": 110.0}, D)
    assert txns == []
    assert (tmp_path / "t1" / "portfolio.json").read_bytes() == before
    assert not (tmp_path / "t1" / "transactions.jsonl").exists()


def test_exit_sells_all_credits_cash_moves_to_watchlist(tmp_path):
    s = _store(tmp_path, [_h()], cash=1000.0)
    txns = execute_advice(s, s.load(), [_advice(verdict="EXIT")], {"MARUTI": 110.0}, D)
    assert len(txns) == 1
    t = txns[0]
    assert t.side == "SELL" and t.qty == 10 and t.price == 110.0
    assert t.realized_pnl == pytest.approx(100.0)
    assert t.cash_after == pytest.approx(1000.0 + 1100.0)
    p = s.load()
    assert p.holdings == []
    assert p.cash_deployable == pytest.approx(2100.0)
    assert any(w.symbol == "MARUTI" and w.source == "autopilot" for w in p.watchlist)
    assert p.last_autopilot_run == D.isoformat()
    assert [x.txn_id for x in s.load_transactions()] == [t.txn_id]


def test_trim_sells_25pct_floored_min_1(tmp_path):
    s = _store(tmp_path, [_h(qty=10)])
    txns = execute_advice(s, s.load(), [_advice(verdict="TRIM")], {"MARUTI": 110.0}, D)
    assert txns[0].qty == 2                     # floor(10*0.25)=2
    assert s.load().holdings[0].adj_qty == pytest.approx(8.0)
    s2 = _store(tmp_path.parent / "b", [_h(qty=3)])
    txns2 = execute_advice(s2, s2.load(), [_advice(verdict="TRIM")], {"MARUTI": 110.0}, D)
    assert txns2[0].qty == 1                    # max(1, floor(0.75))


def test_trim_to_zero_when_under_one_share_would_remain(tmp_path):
    s = _store(tmp_path, [_h(qty=1)])
    txns = execute_advice(s, s.load(), [_advice(verdict="TRIM")], {"MARUTI": 110.0}, D)
    assert txns[0].qty == 1 and txns[0].note == "trim_to_zero"
    assert s.load().holdings == []


def test_idempotent_same_day_rerun_no_double_trades(tmp_path):
    s = _store(tmp_path, [_h()])
    advice = [_advice(verdict="TRIM")]
    execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    txns2 = execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    assert txns2 == []
    assert len(s.load_transactions()) == 1


def test_txn_id_dedupe_survives_missing_run_marker(tmp_path):
    s = _store(tmp_path, [_h()])
    advice = [_advice(verdict="TRIM")]
    execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    p = s.load(); p.last_autopilot_run = ""; s.save(p)   # simulate crash pre-save
    txns2 = execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    assert txns2 == []                                    # ledger id blocks replay


def test_hold_and_unknown_symbol_do_nothing(tmp_path):
    s = _store(tmp_path, [_h()])
    txns = execute_advice(
        s, s.load(),
        [_advice(verdict="HOLD"), _advice(sym="GHOST", verdict="EXIT")],
        {"MARUTI": 110.0}, D)
    assert txns == []
    assert len(s.load().holdings) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_autopilot_executor_sells.py -v`
Expected: FAIL — `ModuleNotFoundError: core.portfolio.autopilot`

- [ ] **Step 3: Implement the executor skeleton + sell side**

Create `core/portfolio/autopilot.py`:

```python
"""
Compass Autopilot — deterministic execution of advisor verdicts on the
virtual portfolio (spec docs/superpowers/specs/2026-07-10-compass-autopilot-design.md §4).

The LLM never decides; this module is a pure function over AdviceRecords.
Virtual money only — no broker calls, ever. The transactions ledger is the
audit authority; portfolio.json is derived state.

Trade ordering per run (deterministic): sells first (EXIT, SWITCH sell leg,
TRIM — symbol asc), then buys (SWITCH buy legs, then ADDs by confidence
desc, ties symbol asc). Sells free cash before buys consume it.
"""
from __future__ import annotations

import hashlib
import logging
import math
from datetime import date, datetime, timedelta, timezone

from core.config import settings
from backend.shared.schemas.portfolio import (
    AdviceRecord,
    Holding,
    Portfolio,
    TransactionRecord,
    WatchlistItem,
)
from core.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)


def make_txn_id(user_id: str, d: str, symbol: str, side: str, ref: str) -> str:
    return hashlib.sha256(f"{user_id}|{d}|{symbol}|{side}|{ref}".encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _txn(portfolio: Portfolio, rec: AdviceRecord, *, side: str, qty: float,
         price: float, cash_before: float, holding_qty_after: float,
         realized: float, note: str, symbol: str | None = None) -> TransactionRecord:
    sym = symbol or rec.symbol
    ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
    return TransactionRecord(
        txn_id=make_txn_id(portfolio.user_id, rec.date, sym, side, ref),
        date=rec.date, ts=_now_iso(), user_id=portfolio.user_id, symbol=sym,
        side=side, qty=qty, price=price, value=round(qty * price, 2),
        cash_before=round(cash_before, 2),
        cash_after=round(portfolio.cash_deployable, 2),
        holding_qty_after=holding_qty_after, realized_pnl=realized,
        source="autopilot", verdict=rec.verdict, advice_ref=ref,
        triggers=list(rec.triggers), note=note,
    )


def _find(portfolio: Portfolio, symbol: str) -> Holding | None:
    return next((h for h in portfolio.holdings if h.symbol == symbol), None)


def _execute_sells(portfolio: Portfolio, advice: list[AdviceRecord],
                   closes: dict[str, float], existing_ids: set[str],
                   ) -> tuple[list[TransactionRecord], list[tuple[float, AdviceRecord]]]:
    txns: list[TransactionRecord] = []
    switch_proceeds: list[tuple[float, AdviceRecord]] = []
    sells = sorted((a for a in advice if a.verdict in ("EXIT", "SWITCH", "TRIM")),
                   key=lambda a: a.symbol)
    for rec in sells:
        h = _find(portfolio, rec.symbol)
        if h is None or h.adj_qty <= 0:
            continue
        price = closes.get(rec.symbol) or rec.close
        note = ""
        if rec.verdict in ("EXIT", "SWITCH"):
            qty = h.adj_qty
            note = "exit_full"
        else:  # TRIM
            qty = float(max(1, math.floor(h.adj_qty * settings.AUTOPILOT_TRIM_PCT / 100.0)))
            if h.adj_qty - qty < 1.0:
                qty, note = h.adj_qty, "trim_to_zero"
        ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
        if make_txn_id(portfolio.user_id, rec.date, rec.symbol, "SELL", ref) in existing_ids:
            continue
        cash_before = portfolio.cash_deployable
        realized = h.sell(qty, price)
        portfolio.cash_deployable = round(portfolio.cash_deployable + qty * price, 2)
        if h.adj_qty <= 1e-9:
            portfolio.holdings = [x for x in portfolio.holdings if x.symbol != h.symbol]
            if rec.verdict in ("EXIT", "SWITCH") and not any(
                    w.symbol == h.symbol for w in portfolio.watchlist):
                portfolio.watchlist.append(WatchlistItem(
                    symbol=h.symbol, sector=h.sector, added=rec.date,
                    reason="autopilot_exit", source="autopilot"))
        txns.append(_txn(portfolio, rec, side="SELL", qty=qty, price=price,
                         cash_before=cash_before,
                         holding_qty_after=(h.adj_qty if h.adj_qty > 1e-9 else 0.0),
                         realized=realized, note=note))
        if rec.verdict == "SWITCH" and rec.switch_candidate:
            switch_proceeds.append((qty * price, rec))
    return txns, switch_proceeds


def _execute_buys(portfolio: Portfolio, advice: list[AdviceRecord],
                  closes: dict[str, float], existing_ids: set[str],
                  switch_proceeds: list[tuple[float, AdviceRecord]],
                  review_date: date, store: PortfolioStore,
                  sector_lookup: dict[str, str] | None) -> list[TransactionRecord]:
    return []   # Task 5 (ADD) and Task 6 (SWITCH buy leg) fill this in.


def execute_advice(store: PortfolioStore, portfolio: Portfolio,
                   advice: list[AdviceRecord], closes: dict[str, float],
                   review_date: date,
                   sector_lookup: dict[str, str] | None = None,
                   ) -> list[TransactionRecord]:
    """Execute one review-day's verdicts. Appends transactions FIRST, then
    saves the portfolio (txn_id dedupe makes a crash between the two safe)."""
    if not settings.AUTOPILOT_ENABLED or not portfolio.autopilot \
            or portfolio.cash_deployable is None:
        return []
    day = review_date.isoformat()
    if portfolio.last_autopilot_run == day:
        return []
    existing_ids = {t.txn_id for t in store.load_transactions(limit=2000)}

    sell_txns, switch_proceeds = _execute_sells(portfolio, advice, closes, existing_ids)
    existing_ids |= {t.txn_id for t in sell_txns}
    buy_txns = _execute_buys(portfolio, advice, closes, existing_ids,
                             switch_proceeds, review_date, store, sector_lookup)
    txns = sell_txns + buy_txns
    if not txns:
        # Still stamp the run marker so re-triggered pipelines skip cheaply,
        # but avoid rewriting portfolio.json when nothing happened at all.
        portfolio.last_autopilot_run = day
        store.save(portfolio)
        return []
    for t in txns:
        store.append_transaction(t)
    portfolio.last_autopilot_run = day
    store.save(portfolio)
    logger.info("[autopilot] %s executed %d trade(s) for %s",
                day, len(txns), portfolio.user_id)
    return txns
```

**Note the `test_hold_and_unknown_symbol_do_nothing` expectation:** the run marker IS stamped even for zero trades (holdings survive, ledger stays empty). The byte-identical requirement applies only when gating is off (`test_gating_off_no_writes`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_autopilot_executor_sells.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/autopilot.py tests/unit/test_autopilot_executor_sells.py
git commit -m "feat(autopilot): executor skeleton + EXIT/TRIM sell side with idempotency"
```

---

### Task 5: Executor — ADD buys (tranche, weight cap, cash floor, cooldown)

**Files:**
- Modify: `core/portfolio/autopilot.py` (replace `_execute_buys` stub body for ADD; SWITCH handled in Task 6)
- Test: `tests/unit/test_autopilot_executor_adds.py` (create)

**Interfaces:**
- Consumes: Task 4 skeleton. `_execute_buys` gains real ADD logic; signature unchanged.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_autopilot_executor_adds.py
"""Autopilot executor — ADD sizing, caps, cooldown (spec §4)."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio, TransactionRecord
from core.portfolio.autopilot import execute_advice, make_txn_id
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)


def _store(tmp_path, holdings, cash=100000.0):
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = holdings, cash, 500000.0, True
    s.save(p)
    return s


def _h(sym="MARUTI", qty=10.0, price=100.0, sector="automobile"):
    return Holding(symbol=sym, sector=sector, qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date="2026-06-01")


def _add(sym="MARUTI", close=100.0, confidence=0.6):
    return AdviceRecord(date=D.isoformat(), user_id="t1", symbol=sym, verdict="ADD",
                        close=close, unrealised_pnl_pct=5.0, stop_pct=8.0,
                        confidence=confidence, rationale_hash="c0ffee")


def test_add_buys_25pct_of_position_whole_shares(tmp_path):
    # big portfolio so the 10% weight cap doesn't bind: MARUTI is 1k of 401k
    others = [_h(sym="PADDING", qty=100.0, price=4000.0, sector="banking")]
    s = _store(tmp_path, [_h(qty=10, price=100.0)] + others, cash=100000.0)
    txns = execute_advice(s, s.load(), [_add(close=100.0)], {"MARUTI": 100.0, "PADDING": 4000.0}, D)
    assert len(txns) == 1
    t = txns[0]
    assert t.side == "BUY" and t.qty == 2        # floor(0.25*1000/100)=2
    p = s.load()
    maruti = next(h for h in p.holdings if h.symbol == "MARUTI")
    assert maruti.adj_qty == pytest.approx(12.0)
    assert maruti.adj_avg_price == pytest.approx(100.0)
    assert p.cash_deployable == pytest.approx(100000.0 - 200.0)


def test_add_respects_cash_floor(tmp_path):
    # padding keeps MARUTI far below the 10% weight cap so only cash binds
    holdings = [_h(qty=100, price=100.0),
                _h(sym="PADDING", qty=100.0, price=4000.0, sector="banking")]
    s = _store(tmp_path, holdings, cash=10100.0)
    # tranche = 2500 but only 100 above the 10k floor -> qty 1
    txns = execute_advice(s, s.load(), [_add(close=100.0)],
                          {"MARUTI": 100.0, "PADDING": 4000.0}, D)
    assert len(txns) == 1 and txns[0].qty == 1
    assert s.load().cash_deployable == pytest.approx(10000.0)


def test_add_skipped_when_floor_leaves_under_one_share(tmp_path):
    holdings = [_h(qty=100, price=100.0),
                _h(sym="PADDING", qty=100.0, price=4000.0, sector="banking")]
    s = _store(tmp_path, holdings, cash=10050.0)
    txns = execute_advice(s, s.load(), [_add(close=100.0)],
                          {"MARUTI": 100.0, "PADDING": 4000.0}, D)
    assert txns == []


def test_add_respects_position_weight_cap(tmp_path):
    # MARUTI 5000 of 50000 total = 10% already at ADVISOR_MAX_POSITION_PCT cap
    holdings = [_h(qty=50, price=100.0),
                _h(sym="OTHER", qty=450, price=100.0, sector="banking")]
    s = _store(tmp_path, holdings, cash=100000.0)
    txns = execute_advice(s, s.load(), [_add(close=100.0)],
                          {"MARUTI": 100.0, "OTHER": 100.0}, D)
    assert txns == []


def test_add_cooldown_blocks_repeat_within_5_trading_days(tmp_path):
    s = _store(tmp_path, [_h(qty=100, price=100.0),
                          _h(sym="PADDING", qty=100.0, price=4000.0, sector="banking")])
    prior = TransactionRecord(
        txn_id="prior1", date=date(2026, 7, 9).isoformat(),   # Thu, 2 TD before Mon 13th
        ts="2026-07-09T12:00:00+00:00", user_id="t1", symbol="MARUTI",
        side="BUY", qty=1, price=100.0, value=100.0, cash_before=0, cash_after=0,
        holding_qty_after=1, source="autopilot", verdict="ADD")
    s.append_transaction(prior)
    txns = execute_advice(s, s.load(), [_add()], {"MARUTI": 100.0, "PADDING": 4000.0}, D)
    assert txns == []


def test_buys_ordered_by_confidence_when_cash_constrained(tmp_path):
    holdings = [_h(sym="AAA", qty=100, price=100.0),
                _h(sym="BBB", qty=100, price=100.0, sector="banking"),
                _h(sym="PADDING", qty=200.0, price=4000.0, sector="pharma")]
    s = _store(tmp_path, holdings, cash=12000.0)   # only 2000 above floor
    advice = [_add(sym="AAA", confidence=0.5), _add(sym="BBB", confidence=0.9)]
    txns = execute_advice(s, s.load(), advice,
                          {"AAA": 100.0, "BBB": 100.0, "PADDING": 4000.0}, D)
    # BBB (higher confidence) fills its 20-share tranche... capped by cash to 20
    assert [t.symbol for t in txns] == ["BBB"]
    assert txns[0].qty == 20                       # floor(2000/100)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_autopilot_executor_adds.py -v`
Expected: FAIL — assertions (stub returns `[]` for all, first test asserts 1 txn)

- [ ] **Step 3: Implement ADD buys**

Replace `_execute_buys` in `core/portfolio/autopilot.py` (keep `switch_proceeds` handling as a no-op loop for now — Task 6 fills it; the `pass` there is the ONLY allowed stub):

```python
def _trading_days_between(start: date, end: date) -> int:
    from core.intelligence.rl.nse_calendar import is_trading_day
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if is_trading_day(d):
            n += 1
    return n


def _portfolio_market_value(portfolio: Portfolio, closes: dict[str, float]) -> float:
    return sum(h.adj_qty * closes.get(h.symbol, h.adj_avg_price)
               for h in portfolio.holdings)


def _last_add_date(store: PortfolioStore, symbol: str) -> date | None:
    for t in reversed(store.load_transactions(limit=2000)):
        if t.symbol == symbol and t.side == "BUY" and t.source == "autopilot":
            return date.fromisoformat(t.date)
    return None


def _buy_into_holding(portfolio: Portfolio, symbol: str, sector: str,
                      qty: float, price: float, buy_date: str) -> float:
    """Merge a buy into an existing holding (weighted adj averages) or create
    a new one. Returns the holding's post-trade adj_qty."""
    h = _find(portfolio, symbol)
    if h is None:
        portfolio.holdings.append(Holding(
            symbol=symbol, sector=sector, qty=qty, avg_buy_price=price,
            adj_avg_price=price, adj_qty=qty, buy_date=buy_date))
        return qty
    total = h.adj_qty + qty
    h.adj_avg_price = (h.adj_avg_price * h.adj_qty + price * qty) / total
    h.adj_qty = total
    # raw fields track money actually put in (entry history)
    raw_total = h.qty + qty
    h.avg_buy_price = (h.avg_buy_price * h.qty + price * qty) / raw_total
    h.qty = raw_total
    return h.adj_qty


def _execute_buys(portfolio: Portfolio, advice: list[AdviceRecord],
                  closes: dict[str, float], existing_ids: set[str],
                  switch_proceeds: list[tuple[float, AdviceRecord]],
                  review_date: date, store: PortfolioStore,
                  sector_lookup: dict[str, str] | None) -> list[TransactionRecord]:
    txns: list[TransactionRecord] = []
    floor_cash = settings.AUTOPILOT_MIN_CASH_FLOOR

    for proceeds, rec in switch_proceeds:
        pass   # Task 6: SWITCH buy leg

    adds = sorted((a for a in advice if a.verdict == "ADD"),
                  key=lambda a: (-a.confidence, a.symbol))
    cap = settings.ADVISOR_MAX_POSITION_PCT / 100.0
    for rec in adds:
        h = _find(portfolio, rec.symbol)
        if h is None:
            continue
        price = closes.get(rec.symbol) or rec.close
        if price <= 0:
            continue
        last_add = _last_add_date(store, rec.symbol)
        if last_add is not None and _trading_days_between(
                last_add, review_date) < settings.AUTOPILOT_ADD_COOLDOWN_TD:
            logger.info("[autopilot] ADD %s skipped: cooldown", rec.symbol)
            continue
        position_value = h.adj_qty * price
        tranche = position_value * settings.AUTOPILOT_ADD_TRANCHE_PCT / 100.0
        total_mv = _portfolio_market_value(portfolio, closes)
        # post-trade weight cap: (pos + X)/(total + X) <= cap
        weight_headroom = (cap * total_mv - position_value) / (1 - cap) \
            if cap < 1 else float("inf")
        budget = min(tranche, max(0.0, weight_headroom),
                     portfolio.cash_deployable - floor_cash)
        qty = float(math.floor(budget / price))
        if qty < 1:
            logger.info("[autopilot] ADD %s skipped: budget %.2f < 1 share @ %.2f",
                        rec.symbol, budget, price)
            continue
        ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
        if make_txn_id(portfolio.user_id, rec.date, rec.symbol, "BUY", ref) in existing_ids:
            continue
        cash_before = portfolio.cash_deployable
        portfolio.cash_deployable = round(portfolio.cash_deployable - qty * price, 2)
        qty_after = _buy_into_holding(portfolio, rec.symbol, h.sector, qty, price,
                                      review_date.isoformat())
        txns.append(_txn(portfolio, rec, side="BUY", qty=qty, price=price,
                         cash_before=cash_before, holding_qty_after=qty_after,
                         realized=0.0, note="add_tranche"))
    return txns
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_autopilot_executor_adds.py tests/unit/test_autopilot_executor_sells.py -v`
Expected: all PASS (sells suite must stay green)

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/autopilot.py tests/unit/test_autopilot_executor_adds.py
git commit -m "feat(autopilot): ADD buys — tranche sizing, weight cap, cash floor, cooldown"
```

---

### Task 6: Executor — SWITCH buy leg + value-history recorder

**Files:**
- Modify: `core/portfolio/autopilot.py`
- Test: `tests/unit/test_autopilot_executor_switch.py` (create)

**Interfaces:**
- Consumes: Tasks 4–5.
- Produces: SWITCH buy leg inside `_execute_buys` (replaces the `pass`); `record_value_point(store: PortfolioStore, portfolio: Portfolio, closes: dict[str, float], review_date: date) -> dict | None` (appends `{date, market_value, cash, total_equity, capital_in, day_change_pct}`; returns the point or None when skipped). Promotion of the bought symbol via `core.portfolio.promotion.promote_symbol(symbol, sector, origin="held")` (same call the API uses), wrapped non-fatal.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_autopilot_executor_switch.py
"""Autopilot executor — SWITCH two-leg + value history (spec §3.3/§4)."""
from datetime import date
from unittest.mock import patch

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.portfolio.autopilot import execute_advice, record_value_point
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)


def _store(tmp_path, holdings, cash=20000.0):
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = holdings, cash, 100000.0, True
    s.save(p)
    return s


def _h(sym="TATAMOTORS", qty=10.0, price=100.0):
    return Holding(symbol=sym, sector="automobile", qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date="2026-06-01")


def _switch(sym="TATAMOTORS", cand="LODHA", close=110.0):
    return AdviceRecord(date=D.isoformat(), user_id="t1", symbol=sym,
                        verdict="SWITCH", close=close, unrealised_pnl_pct=-9.0,
                        stop_pct=8.0, confidence=0.4, switch_candidate=cand,
                        triggers=["stop_breach", "switch_candidate_available"],
                        rationale_hash="5w17c4")


@patch("core.portfolio.autopilot.promote_symbol", return_value={"status": "ok"})
@patch("core.portfolio.autopilot.close_on", return_value=200.0)
def test_switch_sells_then_buys_candidate(mock_close, mock_promote, tmp_path):
    s = _store(tmp_path, [_h()], cash=20000.0)
    txns = execute_advice(s, s.load(), [_switch()], {"TATAMOTORS": 110.0}, D,
                          sector_lookup={"LODHA": "realty"})
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "TATAMOTORS"), ("BUY", "LODHA")]
    buy = txns[1]
    # proceeds 1100, cash 20000+1100=21100, floor 10000 -> budget min(1100, 11100)=1100 -> 5 shares
    assert buy.qty == 5 and buy.price == 200.0
    p = s.load()
    lodha = next(h for h in p.holdings if h.symbol == "LODHA")
    assert lodha.sector == "realty" and lodha.buy_date == D.isoformat()
    mock_close.assert_called_once()
    mock_promote.assert_called_once_with("LODHA", "realty", origin="held")


@patch("core.portfolio.autopilot.close_on", side_effect=Exception("no price"))
def test_switch_buy_skipped_when_candidate_unpriceable(mock_close, tmp_path):
    s = _store(tmp_path, [_h()], cash=20000.0)
    txns = execute_advice(s, s.load(), [_switch()], {"TATAMOTORS": 110.0}, D)
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "TATAMOTORS")]
    assert not any(h.symbol == "LODHA" for h in s.load().holdings)


def test_record_value_point_appends_and_computes_day_change(tmp_path):
    s = _store(tmp_path, [_h(qty=10, price=100.0)], cash=1000.0)
    s.append_value_point({"date": "2026-07-10", "market_value": 1000.0,
                          "cash": 1000.0, "total_equity": 2000.0,
                          "capital_in": 100000.0, "day_change_pct": None})
    pt = record_value_point(s, s.load(), {"TATAMOTORS": 110.0}, D)
    assert pt["market_value"] == pytest.approx(1100.0)
    assert pt["total_equity"] == pytest.approx(2100.0)
    assert pt["day_change_pct"] == pytest.approx(5.0)
    # idempotent: same day again -> None, no extra line
    assert record_value_point(s, s.load(), {"TATAMOTORS": 110.0}, D) is None
    assert len(s.load_value_history()) == 2


def test_record_value_point_skips_without_cash_accounting(tmp_path):
    s = PortfolioStore(user_id="t2", base_dir=str(tmp_path))
    p = s.load(); p.holdings = [_h()]; s.save(p)      # cash_deployable None
    assert record_value_point(s, s.load(), {"TATAMOTORS": 110.0}, D) is None
    assert s.load_value_history() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_autopilot_executor_switch.py -v`
Expected: FAIL — `ImportError: cannot import name 'record_value_point'`

- [ ] **Step 3: Implement SWITCH buy leg + recorder**

In `core/portfolio/autopilot.py` add imports:
```python
from core.portfolio.pricing import close_on
from core.portfolio.promotion import promote_symbol
```
(If `promote_symbol` importing at module top creates a cycle — it shouldn't, promotion has no autopilot import — keep it top-level; tests patch `core.portfolio.autopilot.promote_symbol`.)

Replace the `for proceeds, rec in switch_proceeds: pass` loop:

```python
    for proceeds, rec in switch_proceeds:
        cand = rec.switch_candidate.strip().upper()
        if not cand:
            continue
        try:
            price = close_on(cand, review_date)
        except Exception as exc:
            logger.warning("[autopilot] SWITCH buy %s skipped: unpriceable (%s)",
                           cand, exc)
            continue
        budget = min(proceeds, portfolio.cash_deployable - floor_cash)
        qty = float(math.floor(budget / price)) if price > 0 else 0.0
        if qty < 1:
            logger.info("[autopilot] SWITCH buy %s skipped: budget %.2f < 1 share",
                        cand, budget)
            continue
        ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
        if make_txn_id(portfolio.user_id, rec.date, cand, "BUY", ref) in existing_ids:
            continue
        sector = (sector_lookup or {}).get(cand, "")
        if not sector:
            try:
                from backend.sectors.registry import SectorRegistry
                sector = SectorRegistry.resolve(cand).strip().lower()
            except Exception:
                sector = "generic"
        cash_before = portfolio.cash_deployable
        portfolio.cash_deployable = round(portfolio.cash_deployable - qty * price, 2)
        qty_after = _buy_into_holding(portfolio, cand, sector, qty, price,
                                      review_date.isoformat())
        txns.append(_txn(portfolio, rec, side="BUY", qty=qty, price=price,
                         cash_before=cash_before, holding_qty_after=qty_after,
                         realized=0.0, note=f"switch from {rec.symbol}",
                         symbol=cand))
        try:
            promote_symbol(cand, sector, origin="held")
        except Exception as exc:
            logger.warning("[autopilot] promotion failed for %s (non-fatal): %s",
                           cand, exc)
```

Append at module end:

```python
def record_value_point(store: PortfolioStore, portfolio: Portfolio,
                       closes: dict[str, float], review_date: date) -> dict | None:
    """Append today's equity snapshot (spec §3.3). Skips when cash accounting
    is off or the point already exists (idempotent re-runs)."""
    if portfolio.cash_deployable is None:
        return None
    day = review_date.isoformat()
    hist = store.load_value_history(limit=1)
    if hist and hist[-1].get("date") == day:
        return None
    mv = round(_portfolio_market_value(portfolio, closes), 2)
    total = round(mv + portfolio.cash_deployable, 2)
    day_change_pct = None
    if hist and hist[-1].get("total_equity"):
        prev = hist[-1]["total_equity"]
        if prev > 0:
            day_change_pct = round((total / prev - 1) * 100, 4)
    point = {"date": day, "market_value": mv,
             "cash": round(portfolio.cash_deployable, 2), "total_equity": total,
             "capital_in": portfolio.capital_in, "day_change_pct": day_change_pct}
    store.append_value_point(point)
    return point
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_autopilot_executor_switch.py tests/unit/test_autopilot_executor_adds.py tests/unit/test_autopilot_executor_sells.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/autopilot.py tests/unit/test_autopilot_executor_switch.py
git commit -m "feat(autopilot): SWITCH buy leg with resolvability gate + daily value history"
```

---

### Task 7: Pipeline hook + digest trades + alerts

**Files:**
- Modify: `core/portfolio/pipeline.py` (between step 3 and step 4), `core/portfolio/digest.py`
- Test: `tests/unit/test_autopilot_pipeline.py` (create)

**Interfaces:**
- Consumes: `execute_advice`, `record_value_point` (Tasks 4–6), `build_digest` (existing).
- Produces: `build_digest(..., transactions: list | None = None)` — digest dict gains `"trades": [txn dicts]`; pipeline executes autopilot per user after advice, reloads post-trade portfolio for the digest, emits `AlertEvent(kind="autopilot_trade", severity="info"|"warning")` per trade, appends `"; N trade(s) executed"` to the EOD deliver body when N > 0, and records the value point (after execution, regardless of trade count).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_autopilot_pipeline.py
"""Autopilot pipeline integration — execution hook + digest trades (spec §4)."""
from datetime import date
from unittest.mock import patch

from backend.shared.schemas.portfolio import (
    AdviceRecord, Holding, Portfolio, TransactionRecord,
)
from core.portfolio.digest import build_digest

D = date(2026, 7, 13)


def _portfolio():
    return Portfolio(user_id="t1", holdings=[
        Holding(symbol="MARUTI", sector="automobile", qty=10, avg_buy_price=100.0,
                adj_avg_price=100.0, adj_qty=10, buy_date="2026-06-01")])


def _advice():
    return [AdviceRecord(date=D.isoformat(), user_id="t1", symbol="MARUTI",
                         verdict="HOLD", close=110.0, unrealised_pnl_pct=10.0,
                         stop_pct=8.0)]


def _txn():
    return TransactionRecord(
        txn_id="x1", date=D.isoformat(), ts="2026-07-13T12:00:00+00:00",
        user_id="t1", symbol="MARUTI", side="SELL", qty=2, price=110.0,
        value=220.0, cash_before=0.0, cash_after=220.0, holding_qty_after=8,
        realized_pnl=20.0, verdict="TRIM")


def test_digest_includes_trades_when_passed():
    d = build_digest("t1", D, _advice(), _portfolio(), {"MARUTI": 110.0},
                     transactions=[_txn()])
    assert len(d["trades"]) == 1
    assert d["trades"][0]["side"] == "SELL"


def test_digest_backward_compatible_without_trades():
    d = build_digest("t1", D, _advice(), _portfolio(), {"MARUTI": 110.0})
    assert d["trades"] == []


def test_pipeline_calls_executor_and_value_recorder():
    """The pipeline must call execute_advice + record_value_point per user."""
    import core.portfolio.pipeline as pl
    with patch.object(pl, "list_user_ids", return_value=["t1"]), \
         patch.object(pl, "PortfolioStore") as MockStore, \
         patch.object(pl, "sync_corp_actions"), \
         patch.object(pl, "refresh_events_calendar", return_value={}), \
         patch.object(pl, "close_on", return_value=110.0), \
         patch.object(pl, "get_price_history", side_effect=Exception("skip")), \
         patch.object(pl, "build_signals"), \
         patch.object(pl, "decide", return_value=_advice()[0]), \
         patch.object(pl, "narrate", return_value="n"), \
         patch("core.portfolio.autopilot.execute_advice", return_value=[_txn()]) as mock_exec, \
         patch("core.portfolio.autopilot.record_value_point", return_value=None) as mock_rvp, \
         patch.object(pl, "is_trading_day", return_value=True):
        store = MockStore.return_value
        store.load.return_value = _portfolio()
        result = pl.run_post_review_pipeline(D)
    assert result["status"] == "completed"
    assert mock_exec.call_count == 1
    assert mock_rvp.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_autopilot_pipeline.py -v`
Expected: FAIL — `build_digest() got an unexpected keyword argument 'transactions'`

- [ ] **Step 3: Implement**

`core/portfolio/digest.py` — extend the signature and return:
```python
def build_digest(
    user_id: str,
    review_date: date,
    advice: list[AdviceRecord],
    portfolio: Portfolio,
    closes: dict[str, float],
    transactions: list | None = None,
) -> dict:
```
and add to the returned dict (after `"escalations"`):
```python
        "trades": [t.model_dump() for t in (transactions or [])],
```

`core/portfolio/pipeline.py` — insert between step 3 (advice loop end, after `escalations.extend(...)`) and step 4 (digest):

```python
        # Step 3.5 — Compass Autopilot: execute verdicts, then snapshot equity.
        txns = []
        try:
            from core.portfolio import autopilot
            shelf_sectors = {i.symbol: i.sector for i in shelf_ideas
                             if getattr(i, "sector", "")}
            txns = autopilot.execute_advice(
                store, portfolio, advice, closes, review_date,
                sector_lookup=shelf_sectors)
            if txns:
                portfolio = store.load()          # digest sees post-trade state
                logger.info("[portfolio_pipeline] autopilot executed %d trade(s) for %s",
                            len(txns), user_id)
        except Exception as exc:
            logger.warning("[portfolio_pipeline] autopilot failed for %s (non-fatal): %s",
                           user_id, exc)
        try:
            from core.portfolio import autopilot
            autopilot.record_value_point(store, store.load(), closes, review_date)
        except Exception as exc:
            logger.warning("[portfolio_pipeline] value point failed for %s (non-fatal): %s",
                           user_id, exc)
```

Step 4 digest call becomes:
```python
            store.save_digest(build_digest(user_id, review_date, advice, portfolio,
                                           closes, transactions=txns))
```

Step 5 — extend the alert events list comprehension block: after building `events` from advice, add trade events and the delivery line:
```python
            events.extend(
                AlertEvent(
                    date=review_date.isoformat(),
                    kind="autopilot_trade",
                    symbol=t.symbol,
                    message=f"{t.side} {int(t.qty)} {t.symbol} @ ₹{t.price:,.2f}"
                            + (f" (realized ₹{t.realized_pnl:,.2f})" if t.side == "SELL" else ""),
                    severity="warning" if t.side == "SELL" else "info",
                )
                for t in txns
            )
```
and change the `deliver(...)` body line to:
```python
                f"{len(advice)} holdings reviewed; {n_esc} escalation(s)"
                + (f"; {len(txns)} trade(s) executed" if txns else "")
                + ". Open the app or ask the chat for 'brief' for details.",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_autopilot_pipeline.py -v` then the full portfolio suite: `python -m pytest tests/unit -k "portfolio or autopilot or digest" -q`
Expected: PASS; no regressions in existing pipeline/digest tests (they don't pass `transactions`, default keeps them green — if an existing digest test asserts exact dict keys, update it to include `"trades": []`).

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/pipeline.py core/portfolio/digest.py tests/unit/test_autopilot_pipeline.py
git commit -m "feat(autopilot): pipeline execution hook, digest trades section, trade alerts"
```

---

### Task 8: Seed script

**Files:**
- Create: `scripts/seed_autopilot.py`
- Test: `tests/unit/test_seed_autopilot.py` (create)

**Interfaces:**
- Consumes: `PortfolioStore`, `TransactionRecord`, `make_txn_id`, `record_value_point`; ticker list via `services.api.log_buffer.get_active_tickers_with_sector()` (list of dicts with `sym` + `sector` keys).
- Produces: `seed(user_id: str, pot: float, base_dir: str | None = None, tickers: list[dict] | None = None, price_lookup=None, on: date | None = None) -> dict` returning `{"seeded": int, "skipped": [syms], "cash": float, "capital_in": float}`; CLI `python scripts/seed_autopilot.py --user primary --pot 1000000`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_seed_autopilot.py
"""Autopilot seed script (spec §5)."""
from datetime import date

import pytest

from core.portfolio.store import PortfolioStore
from scripts.seed_autopilot import seed

D = date(2026, 7, 13)
TICKERS = [{"sym": "AAA", "sector": "automobile"},
           {"sym": "BBB", "sector": "banking"},
           {"sym": "CCC", "sector": "it"},
           {"sym": "DDD", "sector": "pharma"}]
PRICES = {"AAA": 250.0, "BBB": 100.0, "CCC": 999999.0, "DDD": 40.0}


def _lookup(sym, on):
    if sym == "CCC":
        raise RuntimeError("no price")
    return PRICES[sym]


def test_seed_equal_weight_whole_shares(tmp_path):
    res = seed("t1", 100000.0, base_dir=str(tmp_path), tickers=TICKERS,
               price_lookup=_lookup, on=D)
    # budget 25000 each: AAA 100 sh, BBB 250 sh, CCC skipped, DDD 625 sh
    assert res["seeded"] == 3 and res["skipped"] == ["CCC"]
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path))
    p = s.load()
    assert {h.symbol: h.adj_qty for h in p.holdings} == {"AAA": 100, "BBB": 250, "DDD": 625}
    assert p.capital_in == 100000.0
    assert p.autopilot is True
    spent = 100 * 250.0 + 250 * 100.0 + 625 * 40.0
    assert p.cash_deployable == pytest.approx(100000.0 - spent)
    txns = s.load_transactions()
    assert len(txns) == 3 and all(t.source == "seed" and t.side == "BUY" for t in txns)
    hist = s.load_value_history()
    assert len(hist) == 1 and hist[0]["total_equity"] == pytest.approx(100000.0)


def test_seed_refuses_non_empty_portfolio(tmp_path):
    seed("t1", 100000.0, base_dir=str(tmp_path), tickers=TICKERS,
         price_lookup=_lookup, on=D)
    with pytest.raises(SystemExit):
        seed("t1", 100000.0, base_dir=str(tmp_path), tickers=TICKERS,
             price_lookup=_lookup, on=D)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_seed_autopilot.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.seed_autopilot` (if `scripts/` lacks an `__init__.py` and the import fails for that reason, add `scripts/__init__.py` — check how existing `scripts/gen_vapid_keys.py` is tested/imported first and mirror that)

- [ ] **Step 3: Implement**

```python
# scripts/seed_autopilot.py
"""
Compass Autopilot — one-time portfolio seeding (spec §5).

Seeds the managed tickers as equal-weight virtual holdings and turns
autopilot on for the user. Idempotent: refuses to run when the user already
has holdings or transactions.

Prod (Railway):  railway ssh "python scripts/seed_autopilot.py --user primary --pot 1000000"
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, ".")   # repo root when run as a script

from backend.shared.schemas.portfolio import Holding, TransactionRecord   # noqa: E402
from core.portfolio.autopilot import make_txn_id, record_value_point      # noqa: E402
from core.portfolio.pricing import close_on                               # noqa: E402
from core.portfolio.store import PortfolioStore                           # noqa: E402

logger = logging.getLogger(__name__)


def seed(user_id: str, pot: float, base_dir: str | None = None,
         tickers: list[dict] | None = None, price_lookup=None,
         on: date | None = None) -> dict:
    on = on or date.today()
    price_lookup = price_lookup or close_on
    if tickers is None:
        from services.api.log_buffer import get_active_tickers_with_sector
        tickers = get_active_tickers_with_sector()
    if not tickers:
        raise SystemExit("no managed tickers found — aborting")

    store = PortfolioStore(user_id=user_id, base_dir=base_dir)
    p = store.load()
    if p.holdings or store.load_transactions(limit=1):
        raise SystemExit(
            f"user {user_id} already has holdings/transactions — refusing to seed")

    budget = pot / len(tickers)
    day = on.isoformat()
    seeded, skipped, spent = 0, [], 0.0
    for t in tickers:
        sym = t["sym"].strip().upper()
        sector = (t.get("sector") or "generic").strip().lower()
        try:
            price = float(price_lookup(sym, on))
        except Exception as exc:
            logger.warning("[seed] %s skipped: no price (%s)", sym, exc)
            skipped.append(sym)
            continue
        qty = float(math.floor(budget / price))
        if qty < 1:
            logger.warning("[seed] %s skipped: budget %.2f < 1 share @ %.2f",
                           sym, budget, price)
            skipped.append(sym)
            continue
        p.holdings.append(Holding(
            symbol=sym, sector=sector, qty=qty, avg_buy_price=price,
            adj_avg_price=price, adj_qty=qty, buy_date=day))
        value = round(qty * price, 2)
        cash_before = round(pot - spent, 2)
        spent += value
        store.append_transaction(TransactionRecord(
            txn_id=make_txn_id(user_id, day, sym, "BUY", "seed"),
            date=day, ts=datetime.now(timezone.utc).isoformat(),
            user_id=user_id, symbol=sym, side="BUY", qty=qty, price=price,
            value=value, cash_before=cash_before,
            cash_after=round(pot - spent, 2), holding_qty_after=qty,
            source="seed", note=f"seed {len(tickers)} tickers @ ₹{budget:,.0f} each"))
        seeded += 1

    p.capital_in = float(pot)
    p.cash_deployable = round(pot - spent, 2)
    p.autopilot = True
    store.save(p)
    closes = {h.symbol: h.adj_avg_price for h in p.holdings}
    record_value_point(store, p, closes, on)
    return {"seeded": seeded, "skipped": skipped,
            "cash": p.cash_deployable, "capital_in": p.capital_in}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Seed the autopilot virtual portfolio")
    ap.add_argument("--user", default="primary")
    ap.add_argument("--pot", type=float, default=1_000_000.0)
    ap.add_argument("--base-dir", default=None)
    args = ap.parse_args()
    result = seed(args.user, args.pot, base_dir=args.base_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_seed_autopilot.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_autopilot.py tests/unit/test_seed_autopilot.py
git commit -m "feat(autopilot): idempotent equal-weight seed script"
```

---

### Task 9: API — transactions, performance, manual-trade accounting

**Files:**
- Modify: `services/api/routes/portfolio_api.py`
- Test: `tests/unit/test_autopilot_api.py` (create; mirror fixture style of `tests/unit/test_portfolio_api.py` — read it first and reuse its app/client fixture pattern)

**Interfaces:**
- Consumes: store ledgers (Task 2), `make_txn_id` (Task 4).
- Produces:
  - `GET /portfolio/transactions?limit=N` → `{"transactions": [txn dicts newest-first]}`
  - `GET /portfolio/performance` → `{cash, capital_in, market_value, total_equity, realized_pnl, unrealized_pnl, total_return_pct, day_change_pct, autopilot, history}` (`history` = value-history lines, oldest→newest; nulls when cash accounting off)
  - `POST /portfolio/holdings`: when `cash_deployable is not None`, also `capital_in += qty*price` and append a `source="manual"` BUY txn (cash unchanged — fresh money). Response unchanged plus `"transaction": txn dict | null`.
  - `DELETE /portfolio/holdings/{symbol}`: when cash accounting live, sell at `close_on(symbol, today)` (fallback: holding's `adj_avg_price` on `PriceUnavailableError`), credit cash, append `source="manual"` SELL txn; response gains `"transaction": txn dict | null`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_autopilot_api.py
"""Autopilot API routes (spec §6). Reuses the test_portfolio_api fixture style."""
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.api.routes.portfolio_api as papi
from backend.shared.schemas.portfolio import Holding, TransactionRecord
from core.portfolio.store import PortfolioStore


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "core.config.settings.PORTFOLIO_DATA_DIR", str(tmp_path), raising=False)
    # keep promotion machinery away from the real data/managed_tickers.json
    monkeypatch.setattr(papi, "promote_symbol", lambda *a, **k: {"status": "test"})
    monkeypatch.setattr(papi, "demote_symbol", lambda *a, **k: False)
    app = FastAPI()
    app.include_router(papi.router)
    return TestClient(app)


def _seed_store(tmp_path, cash=10000.0):
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    p.holdings = [Holding(symbol="MARUTI", sector="automobile", qty=10,
                          avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=10,
                          buy_date="2026-06-01")]
    p.cash_deployable, p.capital_in, p.autopilot = cash, 11000.0, True
    s.save(p)
    s.append_transaction(TransactionRecord(
        txn_id="t1", date="2026-07-13", ts=datetime.now(timezone.utc).isoformat(),
        user_id="primary", symbol="MARUTI", side="SELL", qty=2, price=110.0,
        value=220.0, cash_before=0.0, cash_after=220.0, holding_qty_after=8,
        realized_pnl=20.0, verdict="TRIM"))
    s.append_value_point({"date": "2026-07-12", "market_value": 900.0, "cash": cash,
                          "total_equity": 900.0 + cash, "capital_in": 11000.0,
                          "day_change_pct": None})
    s.append_value_point({"date": "2026-07-13", "market_value": 1000.0, "cash": cash,
                          "total_equity": 1000.0 + cash, "capital_in": 11000.0,
                          "day_change_pct": 0.91})
    return s


def test_transactions_newest_first(client, tmp_path):
    _seed_store(tmp_path)
    r = client.get("/portfolio/transactions?limit=10")
    assert r.status_code == 200
    assert r.json()["transactions"][0]["txn_id"] == "t1"


def test_performance_from_value_history(client, tmp_path):
    _seed_store(tmp_path, cash=10000.0)
    r = client.get("/portfolio/performance")
    assert r.status_code == 200
    d = r.json()
    assert d["cash"] == 10000.0
    assert d["market_value"] == 1000.0
    assert d["total_equity"] == 11000.0
    assert d["realized_pnl"] == 20.0
    assert d["unrealized_pnl"] == pytest.approx(-20.0)   # total 0 − realized 20
    assert d["day_change_pct"] == 0.91
    assert d["autopilot"] is True
    assert len(d["history"]) == 2


def test_manual_add_records_txn_and_capital(client, tmp_path):
    _seed_store(tmp_path)
    r = client.post("/portfolio/holdings", json={
        "symbol": "MARUTI", "sector": "automobile", "qty": 5,
        "buy_date": "2026-07-13", "price": 120.0})
    assert r.status_code == 200
    assert r.json()["transaction"]["source"] == "manual"
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    assert p.capital_in == pytest.approx(11000.0 + 600.0)
    assert p.cash_deployable == pytest.approx(10000.0)   # unchanged — fresh money


def test_manual_delete_sells_and_credits_cash(client, tmp_path, monkeypatch):
    _seed_store(tmp_path)
    monkeypatch.setattr(papi, "close_on", lambda sym, d: 130.0)
    r = client.delete("/portfolio/holdings/MARUTI")
    assert r.status_code == 200
    t = r.json()["transaction"]
    assert t["side"] == "SELL" and t["qty"] == 10 and t["price"] == 130.0
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    assert p.holdings == []
    assert p.cash_deployable == pytest.approx(10000.0 + 1300.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_autopilot_api.py -v`
Expected: FAIL — 404 on /portfolio/transactions (route missing). If the fixture style clashes with how `tests/unit/test_portfolio_api.py` patches the store, adopt that file's exact fixture instead — the assertions stay the same.

- [ ] **Step 3: Implement routes**

In `services/api/routes/portfolio_api.py` add imports `from datetime import date, datetime, timezone`, `from backend.shared.schemas.portfolio import Holding, TransactionRecord, WatchlistItem`, `from core.portfolio.autopilot import make_txn_id`.

New routes (place after `/digest/latest`):

```python
@router.get("/transactions", summary="Transaction audit trail (newest first)")
async def get_transactions(
    user_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    records = _store(user_id).load_transactions(limit=limit)
    return {"transactions": [r.model_dump() for r in reversed(records)]}


@router.get("/performance", summary="P&L summary + daily equity curve")
async def get_performance(
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    store = _store(user_id)
    p = store.load()
    history = store.load_value_history(limit=400)
    realized = round(sum(t.realized_pnl for t in store.load_transactions(limit=2000)), 2)
    cash = p.cash_deployable
    if history:
        last = history[-1]
        market_value, day_change_pct = last.get("market_value"), last.get("day_change_pct")
    else:
        market_value, day_change_pct = None, None
        if p.holdings:   # no history yet — live mark like GET /portfolio
            mv = 0.0
            for h in p.holdings:
                try:
                    mv += h.adj_qty * await asyncio.to_thread(close_on, h.symbol, date.today())
                except Exception:
                    mv += h.adj_qty * h.adj_avg_price
            market_value = round(mv, 2)
    total_equity = round((market_value or 0.0) + (cash or 0.0), 2) \
        if market_value is not None else None
    total_pnl = round(total_equity - p.capital_in, 2) \
        if total_equity is not None and p.capital_in > 0 else None
    return {
        "cash": cash,
        "capital_in": p.capital_in,
        "market_value": market_value,
        "total_equity": total_equity,
        "realized_pnl": realized,
        "unrealized_pnl": round(total_pnl - realized, 2) if total_pnl is not None else None,
        "total_return_pct": round(total_pnl / p.capital_in * 100, 2)
            if total_pnl is not None else None,
        "day_change_pct": day_change_pct,
        "autopilot": p.autopilot,
        "history": history,
    }
```

`add_holding` — after the successful `add_holding(holding)` call and before `promote_symbol`, insert:

```python
    txn = None
    store = _store(user_id)
    p = store.load()
    if p.cash_deployable is not None:
        value = round(holding.qty * price, 2)
        p.capital_in = round(p.capital_in + value, 2)   # fresh money in
        store.save(p)
        txn = TransactionRecord(
            txn_id=make_txn_id(p.user_id, body.buy_date, symbol, "BUY",
                               f"manual-{datetime.now(timezone.utc).isoformat()}"),
            date=body.buy_date, ts=datetime.now(timezone.utc).isoformat(),
            user_id=p.user_id, symbol=symbol, side="BUY", qty=body.qty,
            price=price, value=value, cash_before=p.cash_deployable,
            cash_after=p.cash_deployable,
            holding_qty_after=next((h.adj_qty for h in p.holdings
                                    if h.symbol == symbol), body.qty),
            source="manual", note="manual add (fresh capital)")
        store.append_transaction(txn)
```
and extend the return: `return {"holding": holding.model_dump(), "promotion": promotion, "transaction": (txn.model_dump() if txn else None)}`

`delete_holding` — replace the `store.remove_holding` block:

```python
    store = _store(user_id)
    p = store.load()
    h = next((x for x in p.holdings if x.symbol == symbol.upper()), None)
    if h is None:
        raise HTTPException(status_code=404, detail=f"No holding {symbol.upper()}")
    txn = None
    if p.cash_deployable is not None:
        try:
            price = await asyncio.to_thread(close_on, h.symbol, date.today())
        except Exception:
            price = h.adj_avg_price
        qty = h.adj_qty
        cash_before = p.cash_deployable
        realized, _removed = store.reduce_holding(h.symbol, qty, price)
        p = store.load()
        p.cash_deployable = round(p.cash_deployable + qty * price, 2)
        store.save(p)
        txn = TransactionRecord(
            txn_id=make_txn_id(p.user_id, date.today().isoformat(), h.symbol,
                               "SELL", f"manual-{datetime.now(timezone.utc).isoformat()}"),
            date=date.today().isoformat(), ts=datetime.now(timezone.utc).isoformat(),
            user_id=p.user_id, symbol=h.symbol, side="SELL", qty=qty, price=price,
            value=round(qty * price, 2), cash_before=cash_before,
            cash_after=p.cash_deployable, holding_qty_after=0.0,
            realized_pnl=realized, source="manual", note="manual delete")
        store.append_transaction(txn)
    else:
        if not store.remove_holding(symbol):
            raise HTTPException(status_code=404, detail=f"No holding {symbol.upper()}")
```
and extend the return: `return {"removed": symbol.upper(), "demoted": demoted, "transaction": (txn.model_dump() if txn else None)}`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_autopilot_api.py tests/unit/test_portfolio_api.py -v`
Expected: new tests PASS; existing portfolio API tests stay green (response shapes are additive).

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/portfolio_api.py tests/unit/test_autopilot_api.py
git commit -m "feat(autopilot): transactions + performance routes, manual-trade accounting"
```

---

### Task 10: UI — hero cash/day-change/chart, autopilot pill, live activity feed

**Files:**
- Modify: `src/frontend/prototypes/portfolio.jsx`

No unit-test runner exists for the JSX prototype — verification is manual (Step 3). Keep every existing pattern: `useStatePf` aliases, `aliveRef` guards, demo fallback untouched, `?demo=1` untouched.

- [ ] **Step 1: Extend `usePortfolioLive`** — fetch performance + transactions alongside the digest (non-fatal, same try/catch style):

Inside `load()`, after the digest fetch block, add:
```jsx
      let perf = null, txns = [];
      try {
        const pr = await fetch('/portfolio/performance');
        if (pr.ok) perf = await pr.json();
      } catch {} // performance is optional — absent until cash accounting is on
      try {
        const tr = await fetch('/portfolio/transactions?limit=500');
        if (tr.ok) txns = (await tr.json()).transactions || [];
      } catch {}
```
and include them in the live setState: `setState({ status: 'live', holdings: ..., digest, perf, txns })`. Initialise state as `{ status: 'loading', holdings: [], digest: null, perf: null, txns: [] }`.

- [ ] **Step 2: Wire the hero + activity** (anchor points given as current code):

a) In the page component, after `const alerts = ...` add:
```jsx
  const perf = isLive ? live.perf : null;
  const cashLive = perf && perf.cash != null;
  const heroValue = cashLive && perf.total_equity != null ? perf.total_equity : totalValue;
  const liveHist = (perf?.history || []).filter(pt => pt.total_equity != null);
  const showChart = isDemo || liveHist.length > 1;
  const histWindow = { '1W': 5, '1M': 22, '3M': 66, '6M': 132, '1Y': 252 }[range] || 22;
  const liveSlice = liveHist.slice(-histWindow);
  const liveChange = liveSlice.length > 1
    ? (liveSlice[liveSlice.length - 1].total_equity / liveSlice[0].total_equity - 1) * 100 : 0;
```

b) Hero `gridTemplateColumns` line becomes:
```jsx
          display:'grid', gridTemplateColumns: showChart ? 'var(--hero-cols)' : '1fr', gap:32, alignItems:'center'
```

c) Next to the `Portfolio · {isDemo ? 'Demo' : 'Live'}` eyebrow, after the demo pill, add:
```jsx
              {isLive && perf?.autopilot && (
                <span style={{ fontSize:10, fontWeight:700, padding:'3px 8px', borderRadius:999,
                  background:'rgba(34,211,238,.18)', color:'#67e8f9', letterSpacing:'.06em' }}>
                  AUTOPILOT
                </span>
              )}
```

d) Big number uses `heroValue` instead of `totalValue`. The day-change badge condition `isDemo && (...)` becomes a shared badge: keep the demo branch as is, and add a live branch keyed on `cashLive && perf.day_change_pct != null` using `perf.day_change_pct` (₹ amount omitted when null — show pct only):
```jsx
              {isLive && cashLive && perf.day_change_pct != null && (
                <span className="pf-hero-badge" style={{
                  fontSize:14, fontWeight:700, padding:'4px 10px', borderRadius:8,
                  background: perf.day_change_pct >= 0 ? 'rgba(34,197,94,.18)' : 'rgba(239,68,68,.18)',
                  color: perf.day_change_pct >= 0 ? '#86efac' : '#fca5a5'
                }}>
                  {perf.day_change_pct >= 0 ? '+' : ''}{perf.day_change_pct.toFixed(2)}% today
                </span>
              )}
```

e) Stats row: `Invested` value becomes `cashLive && perf.capital_in > 0 ? perf.capital_in : invested` (₹-formatted the same way); `Total return` uses `perf.total_return_pct ?? totalReturnPct` and `(perf.total_equity - perf.capital_in)` when live-cash, else existing math; Cash stat condition `isDemo` becomes `(isDemo || cashLive)` with value `isDemo ? demo.cash : perf.cash`; add after Cash:
```jsx
              {cashLive && perf.realized_pnl != null && (
                <Stat2 label="Realized P&L"
                  value={(perf.realized_pnl>=0?'+':'-')+'₹'+Math.abs(Math.round(perf.realized_pnl)).toLocaleString('en-IN')}/>
              )}
```

f) Chart block condition `isDemo && (...)` becomes `showChart && (...)`; inside, the label/change/points switch on `isDemo`:
```jsx
                  <div style={{ fontSize:11, color:'#94a3b8' }}>Value over {isDemo ? r.label : range}</div>
                  <div style={{ fontSize:13, fontWeight:700, color: (isDemo ? r.change : liveChange) >= 0 ? '#86efac' : '#fca5a5' }}>
                    {(isDemo ? r.change : liveChange) >= 0 ? '+' : ''}{(isDemo ? r.change : liveChange).toFixed(2)}%
                  </div>
```
and `<Sparkline values={isDemo ? r.points : liveSlice.map(pt => pt.total_equity)} height={92} color="#22d3ee"/>`.

g) Activity: replace `{isDemo && <ActivityCard items={demo.recentActivity}/>}` with:
```jsx
            {isDemo && <ActivityCard items={demo.recentActivity}/>}
            {isLive && live.txns.length > 0 && <LiveActivityCard txns={live.txns}/>}
```
and add next to `ActivityCard`:
```jsx
function LiveActivityCard({ txns }) {
  const [showAll, setShowAll] = useStatePf(false);
  const items = (showAll ? txns : txns.slice(0, 10)).map(t => ({
    kind: t.side === 'BUY' ? 'buy' : 'sell',
    sym: t.symbol, qty: t.qty, price: t.price,
    text: [t.verdict || t.source,
           t.side === 'SELL' && t.realized_pnl != null
             ? `realized ${t.realized_pnl >= 0 ? '+' : ''}₹${Math.abs(t.realized_pnl).toLocaleString('en-IN')}` : '',
           t.note].filter(Boolean).join(' · '),
    t: t.date,
  }));
  return (
    <div>
      <ActivityCard items={items}/>
      {txns.length > 10 && (
        <button onClick={()=>setShowAll(v=>!v)} style={{ marginTop:8, padding:'8px 14px',
          borderRadius:9, border:'1px solid var(--border)', background:'transparent',
          color:'var(--ink-2)', fontSize:12, fontWeight:600, cursor:'pointer' }}>
          {showAll ? 'Show recent only' : `View all ${txns.length} transactions`}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Manual verification**

1. `python -m uvicorn services.api.server:app --port 8000` from repo root.
2. Open the prototype portfolio page with `?demo=1` — pixel-identical to before (demo untouched).
3. Seed a local user: `python scripts/seed_autopilot.py --user primary --pot 1000000` (local `data/portfolio/`), reload page without `?demo=1`: hero shows total equity + Cash + Realized P&L + AUTOPILOT pill; Recent activity lists 16 seed BUYs; chart hidden (single history point) — expected.
4. `curl http://localhost:8000/portfolio/performance` and `/portfolio/transactions?limit=5` return the seeded state.
5. Delete one holding via the row × — activity gains a SELL, cash increases.
6. Restore state afterwards: delete `data/portfolio/primary/` locally (virtual test data only — confirm path before deleting).

- [ ] **Step 4: Commit**

```bash
git add src/frontend/prototypes/portfolio.jsx
git commit -m "feat(autopilot-ui): live cash/day-change/equity chart, autopilot pill, transaction activity feed"
```

---

### Task 11: Isolation invariant, config docs, full-suite gate

**Files:**
- Test: `tests/unit/test_autopilot_isolation.py` (create)
- Modify: `CODEBASE.md` (add autopilot to the core/portfolio section), `src/frontend/prototypes/UI_SPEC.md` (portfolio page: live cash/chart/activity now real), `config.yaml` if a commented `autopilot:` block helps discoverability (defaults live in settings, entry optional)

- [ ] **Step 1: Write the isolation test**

```python
# tests/unit/test_autopilot_isolation.py
"""Autopilot must never touch RL paper-lane or PredictionStore paths
(spec §8 isolation invariant, mirrors Phase B paper isolation)."""
from datetime import date
from pathlib import Path

from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.portfolio.autopilot import execute_advice
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)


def test_executor_writes_stay_inside_user_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                     # any stray relative write lands here
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path / "portfolio"))
    p = s.load()
    p.holdings = [Holding(symbol="MARUTI", sector="automobile", qty=10,
                          avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=10,
                          buy_date="2026-06-01")]
    p.cash_deployable, p.capital_in, p.autopilot = 50000.0, 100000.0, True
    s.save(p)
    advice = [AdviceRecord(date=D.isoformat(), user_id="t1", symbol="MARUTI",
                           verdict="TRIM", close=110.0, unrealised_pnl_pct=10.0,
                           stop_pct=8.0, rationale_hash="abc")]
    execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    created = {p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()}
    assert created == {"portfolio"}                 # nothing outside the user store
    assert not (tmp_path / "data").exists()         # no data/rl/paper, no predictions
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/unit/test_autopilot_isolation.py -v`
Expected: PASS immediately (executor only writes via the store). If it fails, an executor code path writes outside the store — fix the executor, never the test.

- [ ] **Step 3: Docs**

- `CODEBASE.md`: in the core/portfolio section add one line per new surface: `autopilot.py` (verdict executor), `transactions.jsonl` + `value_history.jsonl` ledgers, `scripts/seed_autopilot.py`, `/portfolio/transactions` + `/portfolio/performance` routes.
- `src/frontend/prototypes/UI_SPEC.md`: update the Portfolio page section — cash/day-change/range-chart/activity are now live-wired via `/portfolio/performance` + `/portfolio/transactions`; AUTOPILOT pill; demo mode unchanged.

- [ ] **Step 4: Full-suite gate**

Run: `python -m pytest tests/unit -q` and `python -m pytest tests/contract tests/integration -q`
Expected: unit ≥ 1831 passed + all new autopilot tests, 5 skipped; contract/integration show ONLY the known pre-existing failures (3 SignalAggregator contract + orchestrator stale mocks). Any other failure must be fixed before proceeding.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_autopilot_isolation.py CODEBASE.md src/frontend/prototypes/UI_SPEC.md
git commit -m "test(autopilot): isolation invariant + docs; full-suite gate green"
```

---

### Task 12: Post-merge ops (prod) — NOT part of the branch

After the branch merges to main and is pushed (push = Railway deploy):

- [ ] 1. Verify deploy healthy: `railway status`, spot-check `https://stockagent-ai.up.railway.app/portfolio`.
- [ ] 2. Seed prod: `railway ssh "python scripts/seed_autopilot.py --user primary --pot 1000000"` — expect JSON summary `seeded: 16, skipped: []` (any skipped symbol = price fetch failed; re-run is safe only after clearing state, so investigate instead of re-running).
- [ ] 3. `curl https://stockagent-ai.up.railway.app/portfolio/performance` — capital_in 1000000, 16 holdings' market value + cash ≈ pot.
- [ ] 4. Portfolio page shows AUTOPILOT pill, cash, 16 seed BUYs in activity.
- [ ] 5. Next trading day after the scheduler's daily review: check digest `trades` section + `/portfolio/transactions` for any executed verdicts; value_history grows one point per trading day.
