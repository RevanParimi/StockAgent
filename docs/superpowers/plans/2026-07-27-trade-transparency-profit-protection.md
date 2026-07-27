# Trade Transparency + Profit Protection + Global-Stress Regime — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface time/buy-price/sell-price/reason on every trade end-to-end, add an ATR-scaled trailing profit-protection EXIT, and let global-stress signals (Brent, USD/INR, S&P 500) escalate the market regime.

**Architecture:** Three independent additive pieces per the approved spec
(`docs/superpowers/specs/2026-07-27-trade-transparency-profit-protection-design.md`):
(A) new optional fields on `TransactionRecord` filled at autopilot execution
and rendered in the PWA activity card; (B) a peak-close signal + one new
EXIT-class trigger in the deterministic advisor; (C) three fallback-safe
yfinance reads + a pure escalation notch inside `RegimeDetector.detect()`.
The LLM is never consulted for any of this — zero new LLM calls.

**Tech Stack:** Python 3.11 / pydantic v2 / pytest; yfinance; React JSX prototype (no build system — transpile-check only).

## Global Constraints

- All new tunables go through `cfg()` in `src/backend/shared/config/settings/base.py` with fallback defaults — never hardcode a number at a call site (user rule: config-over-hardcode).
- The transactions ledger is append-only: NEVER mutate or rewrite existing `transactions.jsonl` rows. No backfill.
- Every new external read (yfinance) must be non-fatal: try/except → `logger.warning` → conservative default, matching `RegimeDetector._get_vix`.
- New `TransactionRecord` / `RegimeSnapshot` / `AdvisorSignals` fields MUST have defaults so existing stored JSON parses unchanged.
- Suite discipline: capture the full-suite fail-set BEFORE any change (Task 0); after the final task the fail-set must be identical (known-red baseline ≈ 10 failed + 10 errors, ~2213 passed).
- Do NOT push to origin as part of this plan (user pushes on their schedule; never 16:25–17:15 IST on a trading day).
- Work on a dedicated branch `transparency-wave` (create at execution start per superpowers:using-git-worktrees).
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 0: Branch + baseline fail-set

**Files:** none modified.

- [ ] **Step 1: Create branch**

```bash
git checkout -b transparency-wave
```

- [ ] **Step 2: Capture the known-red baseline**

Run (repo root):

```bash
python -m pytest -q 2>&1 | tail -40 > "$TEMP/transparency_baseline.txt"
cat "$TEMP/transparency_baseline.txt"
```

Expected: ~2213 passed, ~10 failed, ~10 errors. Save the exact list of failed/errored test ids — Task 8 compares against it verbatim. Do not fix any pre-existing failure.

---

### Task 1: `TransactionRecord` transparency fields (schema)

**Files:**
- Modify: `src/backend/shared/schemas/portfolio.py` (class `TransactionRecord`, lines ~118–139)
- Test: `tests/unit/test_txn_transparency.py` (create)

**Interfaces:**
- Produces: `TransactionRecord.cost_basis: float | None` (SELL only: holding's `adj_avg_price` at sale, `None` on buys), `TransactionRecord.pnl_pct: float | None` (SELL only: realized P&L % vs cost), `TransactionRecord.reason: str` (advice narrative, default `""`). Tasks 2 and 7 rely on these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_txn_transparency.py`:

```python
"""Piece A (spec 2026-07-27): transparency fields on TransactionRecord and
their population by the autopilot executor."""
from backend.shared.schemas.portfolio import TransactionRecord


def _base_row(**over):
    row = dict(
        txn_id="abc123", date="2026-07-20", ts="2026-07-20T11:05:00+00:00",
        user_id="primary", symbol="SUZLON", side="SELL", qty=10.0, price=55.0,
        value=550.0, cash_before=100.0, cash_after=650.0,
        holding_qty_after=0.0, realized_pnl=50.0,
    )
    row.update(over)
    return row


def test_old_ledger_row_without_new_fields_still_parses():
    t = TransactionRecord(**_base_row())
    assert t.cost_basis is None
    assert t.pnl_pct is None
    assert t.reason == ""


def test_new_fields_round_trip():
    t = TransactionRecord(**_base_row(cost_basis=50.0, pnl_pct=10.0,
                                      reason="stop was breached"))
    dumped = t.model_dump()
    assert dumped["cost_basis"] == 50.0
    assert dumped["pnl_pct"] == 10.0
    assert dumped["reason"] == "stop was breached"
    assert TransactionRecord(**dumped) == t
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_txn_transparency.py -v`
Expected: FAIL — `cost_basis` is not a known attribute / unexpected keyword.

- [ ] **Step 3: Add the fields**

In `src/backend/shared/schemas/portfolio.py`, inside `TransactionRecord`, after `triggers`:

```python
    note: str = ""
    # Piece A transparency (spec 2026-07-27) — all optional so historical
    # ledger rows keep parsing; the ledger itself is never rewritten.
    cost_basis: float | None = None   # SELL: holding adj_avg_price at sale
    pnl_pct: float | None = None      # SELL: realized P&L % vs cost_basis
    reason: str = ""                  # advice narrative at execution time
```

(Keep the existing `note` line; the comment block sits after it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_txn_transparency.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/schemas/portfolio.py tests/unit/test_txn_transparency.py
git commit -m "feat(transparency): cost_basis/pnl_pct/reason fields on TransactionRecord

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Autopilot fills the transparency fields

**Files:**
- Modify: `core/portfolio/autopilot.py` (`_txn` ~line 50, `_execute_sells` ~line 71, `_execute_buys` ~line 165)
- Test: `tests/unit/test_txn_transparency.py` (extend)

**Interfaces:**
- Consumes: Task 1 fields.
- Produces: `_txn(..., cost_basis: float | None = None)` keyword; every SELL txn carries `cost_basis`/`pnl_pct`/`reason`; every BUY txn carries `reason` (with `cost_basis=None`). `AdviceRecord.narrative` is already populated before execution (pipeline.py:101) — seed/manual paths don't call `_txn`, so they keep `reason=""` naturally.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_txn_transparency.py`:

```python
from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.portfolio.autopilot import _execute_buys, _execute_sells


def _holding(**over):
    h = dict(symbol="SUZLON", sector="renewable_energy", qty=100.0,
             avg_buy_price=50.0, adj_avg_price=50.0, adj_qty=100.0,
             buy_date="2026-07-01")
    h.update(over)
    return Holding(**h)


def _advice(**over):
    a = dict(date="2026-07-20", user_id="primary", symbol="SUZLON",
             verdict="EXIT", close=55.0, unrealised_pnl_pct=10.0,
             stop_pct=8.0, triggers=["stop_breach"],
             narrative="The stop was breached while the forecast points down.",
             rationale_hash="deadbeef")
    a.update(over)
    return AdviceRecord(**a)


def _portfolio(holdings):
    return Portfolio(user_id="primary", holdings=holdings,
                     cash_deployable=10_000.0, capital_in=100_000.0,
                     autopilot=True)


def test_sell_txn_carries_cost_basis_pnl_pct_and_reason():
    pf = _portfolio([_holding()])
    txns, _ = _execute_sells(pf, [_advice()], {"SUZLON": 55.0}, set())
    assert len(txns) == 1
    t = txns[0]
    assert t.cost_basis == 50.0
    # realized = (55-50)*100 = 500 ; pnl_pct = 500 / (50*100) * 100 = 10.0
    assert t.pnl_pct == 10.0
    assert t.reason == "The stop was breached while the forecast points down."


def test_buy_txn_carries_reason_but_no_cost_basis(monkeypatch):
    import core.portfolio.autopilot as ap
    monkeypatch.setattr(ap, "_last_add_date", lambda store, symbol: None)
    from datetime import date
    pf = _portfolio([_holding()])
    rec = _advice(verdict="ADD", triggers=["add_bullish_healthy"],
                  narrative="Envelope bullish and regime supportive.",
                  confidence=0.9)
    txns = _execute_buys(pf, [rec], {"SUZLON": 55.0}, set(), [],
                         date(2026, 7, 20), store=None, sector_lookup=None)
    assert len(txns) == 1
    assert txns[0].reason == "Envelope bullish and regime supportive."
    assert txns[0].cost_basis is None
    assert txns[0].pnl_pct is None
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `python -m pytest tests/unit/test_txn_transparency.py -v`
Expected: the two new tests FAIL (`cost_basis` is None on the sell / `reason` empty). If `_execute_buys` errors on `store=None`, that's fine at this step — the monkeypatched `_last_add_date` in the test avoids the only store use on this path; if another store access exists, stub it the same way rather than building a real store.

- [ ] **Step 3: Implement**

In `core/portfolio/autopilot.py`:

3a. `_txn` — add the keyword and derived pnl:

```python
def _txn(portfolio: Portfolio, rec: AdviceRecord, *, side: str, qty: float,
         price: float, cash_before: float, holding_qty_after: float,
         realized: float, note: str, symbol: str | None = None,
         cost_basis: float | None = None) -> TransactionRecord:
    sym = symbol or rec.symbol
    ref = f"{rec.date}|{rec.symbol}|{rec.rationale_hash}"
    pnl_pct = None
    if side == "SELL" and cost_basis and cost_basis > 0 and qty > 0:
        pnl_pct = round(realized / (cost_basis * qty) * 100, 2)
    return TransactionRecord(
        txn_id=make_txn_id(portfolio.user_id, rec.date, sym, side, ref),
        date=rec.date, ts=_now_iso(), user_id=portfolio.user_id, symbol=sym,
        side=side, qty=qty, price=price, value=round(qty * price, 2),
        cash_before=round(cash_before, 2),
        cash_after=round(portfolio.cash_deployable, 2),
        holding_qty_after=holding_qty_after, realized_pnl=realized,
        source="autopilot", verdict=rec.verdict, advice_ref=ref,
        triggers=list(rec.triggers), note=note,
        cost_basis=cost_basis, pnl_pct=pnl_pct, reason=rec.narrative,
    )
```

3b. `_execute_sells` — capture cost before mutating the holding (`Holding.sell()` doesn't change `adj_avg_price`, but capture-before makes the intent robust). Just above `realized = h.sell(qty, price)`:

```python
        cost_basis = round(h.adj_avg_price, 4)
        cash_before = portfolio.cash_deployable
        realized = h.sell(qty, price)
```

and pass it in the `_txn` call of `_execute_sells`:

```python
        txns.append(_txn(portfolio, rec, side="SELL", qty=qty, price=price,
                         cash_before=cash_before,
                         holding_qty_after=(h.adj_qty if h.adj_qty > 1e-9 else 0.0),
                         realized=realized, note=note, cost_basis=cost_basis))
```

3c. `_execute_buys` — no signature change; both `_txn` calls (SWITCH-buy and ADD) automatically pick up `reason=rec.narrative` and default `cost_basis=None`. No edit needed beyond 3a.

- [ ] **Step 4: Run the file's tests, then the autopilot suite**

Run: `python -m pytest tests/unit/test_txn_transparency.py tests/unit/test_autopilot_executor_sells.py tests/unit/test_autopilot_pipeline.py tests/unit/test_autopilot_store.py -v`
Expected: all PASS (pre-existing autopilot tests unaffected — new fields are optional).

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/autopilot.py tests/unit/test_txn_transparency.py
git commit -m "feat(transparency): autopilot stamps cost_basis/pnl_pct/reason on trades

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Peak-close signal for the trailing stop

**Files:**
- Modify: `core/portfolio/advisor.py` (`AdvisorSignals` ~line 29, `build_signals` ~line 100; new helper below `atr_pct`)
- Modify: `src/backend/shared/config/settings/base.py` (advisor block, ~line 796)
- Test: `tests/unit/test_trailing_stop.py` (create)

**Interfaces:**
- Produces: `AdvisorSignals.peak_close_since_entry: float | None = None`; pure helper `peak_close_since(ohlcv_df, buy_date: date) -> float | None`; setting `ADVISOR_TRAIL_ARM_PCT` (`cfg("advisor.trail_arm_pct", fallback=10.0)`). Task 4 consumes all three.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_trailing_stop.py`:

```python
"""Piece B (spec 2026-07-27): peak-close signal + trailing_stop_breach rule."""
from datetime import date

import pandas as pd

from core.portfolio.advisor import peak_close_since


def _ohlcv(closes_by_day: dict[str, float]) -> pd.DataFrame:
    idx = pd.to_datetime(list(closes_by_day)).tz_localize("Asia/Kolkata")
    return pd.DataFrame({"Close": list(closes_by_day.values())}, index=idx)


def test_peak_is_max_close_on_or_after_buy_date():
    df = _ohlcv({"2026-07-01": 100.0, "2026-07-10": 140.0, "2026-07-20": 120.0})
    assert peak_close_since(df, date(2026, 7, 5)) == 140.0


def test_closes_before_buy_date_are_ignored():
    df = _ohlcv({"2026-07-01": 999.0, "2026-07-10": 140.0})
    assert peak_close_since(df, date(2026, 7, 5)) == 140.0


def test_none_when_no_data_in_window_or_no_df():
    df = _ohlcv({"2026-07-01": 100.0})
    assert peak_close_since(df, date(2026, 7, 5)) is None
    assert peak_close_since(None, date(2026, 7, 5)) is None


def test_setting_exists():
    from core.config import settings
    assert settings.ADVISOR_TRAIL_ARM_PCT == 10.0
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_trailing_stop.py -v`
Expected: FAIL — `peak_close_since` not importable.

- [ ] **Step 3: Implement**

3a. `src/backend/shared/config/settings/base.py`, next to `ADVISOR_TRIM_PROFIT_PCT` (~line 796):

```python
ADVISOR_TRAIL_ARM_PCT: float = cfg("advisor.trail_arm_pct", fallback=10.0)  # peak P&L % that arms the trailing stop
```

3b. `core/portfolio/advisor.py` — field on `AdvisorSignals` (after `confidence`):

```python
    peak_close_since_entry: float | None = None   # max close since buy_date (trailing stop)
```

3c. Pure helper (place directly below `atr_pct`):

```python
def peak_close_since(ohlcv_df, buy_date: date) -> float | None:
    """Highest close on/after buy_date from the already-fetched OHLCV frame.
    None (rule inactive) when the frame is missing or has no in-window rows —
    conservative, like every other non-fatal signal read."""
    try:
        if ohlcv_df is None or len(ohlcv_df) == 0:
            return None
        closes = [float(c) for d, c in zip(ohlcv_df.index, ohlcv_df["Close"])
                  if d.date() >= buy_date]
        return round(max(closes), 4) if closes else None
    except Exception as exc:
        logger.debug("[advisor] peak_close_since failed: %s", exc)
        return None
```

3d. In `build_signals`, after the `AdvisorSignals(...)` construction (~line 124):

```python
    sig.peak_close_since_entry = peak_close_since(
        ohlcv_df, date.fromisoformat(holding.buy_date))
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_trailing_stop.py tests/unit/test_portfolio_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/advisor.py src/backend/shared/config/settings/base.py tests/unit/test_trailing_stop.py
git commit -m "feat(trailing-stop): peak-close-since-entry signal + arm threshold setting

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `trailing_stop_breach` EXIT rule + narrator text

**Files:**
- Modify: `core/portfolio/advisor.py` (`decide`, EXIT block ~line 223)
- Modify: `core/portfolio/narrator.py` (`_TRIGGER_TEXT`, ~line 26)
- Test: `tests/unit/test_trailing_stop.py` (extend)

**Interfaces:**
- Consumes: Task 3's `peak_close_since_entry` + `ADVISOR_TRAIL_ARM_PCT`.
- Produces: trigger code string `"trailing_stop_breach"` (EXIT-class; appears in `AdviceRecord.triggers` and, via Task 2, in `TransactionRecord.triggers`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_trailing_stop.py`:

```python
from core.portfolio.advisor import AdvisorSignals, decide
from backend.shared.schemas.portfolio import Holding


def _h(**over):
    d = dict(symbol="SUZLON", sector="renewable_energy", qty=100.0,
             avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=100.0,
             buy_date="2026-01-10")
    d.update(over)
    return Holding(**d)


def _sig(**over):
    d = dict(symbol="SUZLON", sector="renewable_energy", close=100.0,
             atr_stop_pct=10.0, unrealised_pnl_pct=0.0, holding_age_days=30)
    d.update(over)
    return AdvisorSignals(**d)


def test_armed_and_giveback_breached_fires_exit():
    # peak 140 (peak_pnl +40% >= arm 10%); close 120 → drawdown 14.3% >= stop 10%
    rec = decide(_sig(close=120.0, unrealised_pnl_pct=20.0,
                      peak_close_since_entry=140.0), _h(), "balanced")
    assert rec.verdict == "EXIT"
    assert "trailing_stop_breach" in rec.triggers


def test_not_armed_below_arm_threshold():
    # peak 105 → peak_pnl +5% < arm 10% → inactive even though drawdown huge
    rec = decide(_sig(close=90.0, unrealised_pnl_pct=-10.0,
                      atr_stop_pct=25.0, peak_close_since_entry=105.0),
                 _h(), "balanced")
    assert "trailing_stop_breach" not in rec.triggers


def test_armed_but_giveback_within_budget_holds():
    # peak 140; close 133 → drawdown 5% < stop 10%
    rec = decide(_sig(close=133.0, unrealised_pnl_pct=33.0,
                      peak_close_since_entry=140.0), _h(), "balanced")
    assert "trailing_stop_breach" not in rec.triggers
    assert rec.verdict in ("HOLD", "TRIM", "ADD")


def test_missing_peak_rule_inactive():
    rec = decide(_sig(close=50.0, unrealised_pnl_pct=-50.0,
                      atr_stop_pct=60.0, peak_close_since_entry=None),
                 _h(), "balanced")
    assert "trailing_stop_breach" not in rec.triggers


def test_ltcg_never_softens_trailing_exit():
    # holding ~11 months old (inside the LTCG wait window) — EXIT must survive
    rec = decide(_sig(close=120.0, unrealised_pnl_pct=20.0,
                      peak_close_since_entry=140.0, holding_age_days=340,
                      thesis_intact=True), _h(), "balanced")
    assert rec.verdict == "EXIT"


def test_narrator_has_text_for_trigger():
    from core.portfolio.narrator import _TRIGGER_TEXT
    assert "trailing_stop_breach" in _TRIGGER_TEXT
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_trailing_stop.py -v`
Expected: the new tests FAIL (no trigger fired / key missing).

- [ ] **Step 3: Implement**

3a. `core/portfolio/advisor.py`, inside `decide()`'s EXIT block, after the `crisis_regime_bearish` check (~line 232):

```python
    peak = signals.peak_close_since_entry
    if (peak is not None and peak > 0 and holding.adj_avg_price > 0):
        peak_pnl_pct = (peak / holding.adj_avg_price - 1) * 100
        drawdown_from_peak_pct = (peak - signals.close) / peak * 100
        if (peak_pnl_pct >= settings.ADVISOR_TRAIL_ARM_PCT
                and drawdown_from_peak_pct >= signals.atr_stop_pct):
            triggers.append("trailing_stop_breach")
```

3b. `core/portfolio/narrator.py`, add to `_TRIGGER_TEXT`:

```python
    "trailing_stop_breach": "the position gave back its volatility budget from the peak, so profit is being booked",
```

- [ ] **Step 4: Run trailing + advisor tests**

Run: `python -m pytest tests/unit/test_trailing_stop.py tests/unit -k "advisor" -v`
Expected: PASS; no pre-existing advisor test regresses.

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/advisor.py core/portfolio/narrator.py tests/unit/test_trailing_stop.py
git commit -m "feat(trailing-stop): ATR-scaled trailing_stop_breach EXIT trigger

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Global-stress signals — pure logic + settings + schema

**Files:**
- Modify: `src/backend/shared/config/settings/base.py` (regime block, ~lines 324–391)
- Modify: `src/backend/shared/schemas/feedback.py` (`RegimeSnapshot`, ~line 969)
- Modify: `core/intelligence/regime/detector.py` (new pure functions)
- Test: `tests/unit/intelligence/regime/test_global_stress.py` (create)

**Interfaces:**
- Produces (Task 6 consumes): pure functions on `RegimeDetector`:
  `_global_stress_signals(brent_5d_pct, usdinr_5d_pct, spx_last_pct) -> list[str]`
  (subset of `["brent_shock", "usdinr_stress", "spx_drop"]`; `None` inputs never fire) and
  `_escalate_label(label: str, n_stress: int) -> str`.
  Settings: `REGIME_BRENT_TICKER="BZ=F"`, `REGIME_USDINR_TICKER="INR=X"`,
  `REGIME_SPX_TICKER="^GSPC"`, `REGIME_BRENT_SHOCK_PCT=8.0`,
  `REGIME_USDINR_STRESS_PCT=1.5`, `REGIME_SPX_DROP_PCT=-2.0`,
  `REGIME_GLOBAL_STRESS_MIN_SIGNALS=2`.
  Schema: `RegimeSnapshot.brent_5d_pct/usdinr_5d_pct/spx_last_pct: float | None = None`,
  `RegimeSnapshot.global_stress_signals: list[str] = []`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/intelligence/regime/test_global_stress.py`:

```python
"""Piece C (spec 2026-07-27): global-stress detection + escalation notch."""
from core.intelligence.regime.detector import RegimeDetector


def test_stress_signal_thresholds():
    f = RegimeDetector._global_stress_signals
    assert f(9.0, 0.0, 0.0) == ["brent_shock"]          # brent >= +8
    assert f(0.0, 1.6, 0.0) == ["usdinr_stress"]        # usdinr >= +1.5
    assert f(0.0, 0.0, -2.5) == ["spx_drop"]            # spx <= -2
    assert f(9.0, 1.6, -2.5) == ["brent_shock", "usdinr_stress", "spx_drop"]
    assert f(7.9, 1.4, -1.9) == []


def test_none_inputs_never_fire():
    assert RegimeDetector._global_stress_signals(None, None, None) == []
    assert RegimeDetector._global_stress_signals(None, 1.6, None) == ["usdinr_stress"]


def test_escalation_ladder():
    esc = RegimeDetector._escalate_label
    for base in ("NORMAL", "RISK_ON", "MOMENTUM_EXTENDED", "OVERSOLD"):
        assert esc(base, 2) == "RISK_OFF"
    assert esc("RISK_OFF", 2) == "MACRO_CRISIS"
    assert esc("MACRO_CRISIS", 3) == "MACRO_CRISIS"


def test_below_min_signals_never_escalates():
    for base in ("NORMAL", "RISK_OFF", "MACRO_CRISIS"):
        assert RegimeDetector._escalate_label(base, 0) == base
        assert RegimeDetector._escalate_label(base, 1) == base


def test_snapshot_schema_has_optional_stress_fields():
    from core.schemas.feedback import RegimeSnapshot
    s = RegimeSnapshot()          # old callers construct with no new args
    assert s.brent_5d_pct is None
    assert s.global_stress_signals == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/regime/test_global_stress.py -v`
Expected: FAIL — attributes don't exist.

- [ ] **Step 3: Implement**

3a. `src/backend/shared/config/settings/base.py` — in the regime threshold block (~line 331, after `RSI_OVERSOLD`):

```python
# Global-stress escalation (spec 2026-07-27): direct crude/rupee/US inputs so
# a world shock can escalate the regime before India VIX fully reacts.
REGIME_BRENT_SHOCK_PCT: float   = cfg("regime.brent_shock_pct", fallback=8.0)    # Brent 5d % ≥ this → oil shock (India imports)
REGIME_USDINR_STRESS_PCT: float = cfg("regime.usdinr_stress_pct", fallback=1.5)  # USDINR 5d % ≥ this → rupee stress
REGIME_SPX_DROP_PCT: float      = cfg("regime.spx_drop_pct", fallback=-2.0)      # S&P last session % ≤ this → global risk-off
REGIME_GLOBAL_STRESS_MIN_SIGNALS: int = cfg("regime.global_stress_min_signals", fallback=2)
```

and next to `REGIME_VIX_TICKER` (~line 389):

```python
REGIME_BRENT_TICKER: str  = "BZ=F"
REGIME_USDINR_TICKER: str = "INR=X"
REGIME_SPX_TICKER: str    = "^GSPC"
```

3b. `src/backend/shared/schemas/feedback.py` — `RegimeSnapshot`, after `as_of_date`:

```python
    # Global-stress escalation inputs (spec 2026-07-27); optional for compat
    brent_5d_pct: float | None = None
    usdinr_5d_pct: float | None = None
    spx_last_pct: float | None = None
    global_stress_signals: list[str] = Field(default_factory=list)
```

(`Field` is already imported in that module.)

3c. `core/intelligence/regime/detector.py` — two pure staticmethods on `RegimeDetector` (place after `_classify`):

```python
    @staticmethod
    def _global_stress_signals(
        brent_5d_pct: float | None,
        usdinr_5d_pct: float | None,
        spx_last_pct: float | None,
    ) -> list[str]:
        """Which global-stress conditions fired. None (fetch failed) never
        counts — a network outage must degrade to today's behavior."""
        fired: list[str] = []
        if brent_5d_pct is not None and brent_5d_pct >= settings.REGIME_BRENT_SHOCK_PCT:
            fired.append("brent_shock")
        if usdinr_5d_pct is not None and usdinr_5d_pct >= settings.REGIME_USDINR_STRESS_PCT:
            fired.append("usdinr_stress")
        if spx_last_pct is not None and spx_last_pct <= settings.REGIME_SPX_DROP_PCT:
            fired.append("spx_drop")
        return fired

    @staticmethod
    def _escalate_label(label: str, n_stress: int) -> str:
        """One severity notch when enough independent global signals agree.
        A single noisy signal never escalates on its own."""
        if n_stress < settings.REGIME_GLOBAL_STRESS_MIN_SIGNALS:
            return label
        if label == "RISK_OFF":
            return "MACRO_CRISIS"
        if label == "MACRO_CRISIS":
            return label
        return "RISK_OFF"
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/intelligence/regime/ -v`
Expected: new file PASS; `test_sticky_regime.py` untouched and green.

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/config/settings/base.py src/backend/shared/schemas/feedback.py core/intelligence/regime/detector.py tests/unit/intelligence/regime/test_global_stress.py
git commit -m "feat(regime): global-stress pure logic, settings, snapshot fields

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Wire global stress into `detect()` (fetchers + narrative)

**Files:**
- Modify: `core/intelligence/regime/detector.py` (`detect` ~line 73, fetcher section ~line 112, `_build_narrative` ~line 212)
- Test: `tests/unit/intelligence/regime/test_global_stress.py` (extend)

**Interfaces:**
- Consumes: Task 5's pure functions, settings, schema fields.
- Produces: `detect()` returns a `RegimeSnapshot` whose `regime_label` reflects escalation, with raw stress values + `global_stress_signals` populated and mentioned in `narrative`. Callers (`daily_review.py:429`, `generate_forecast.py:313`) need no change — escalation is internal, and the sticky state machine (`state.py`) consumes the label downstream unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/intelligence/regime/test_global_stress.py`:

```python
from datetime import date


def _patched_detector(monkeypatch, *, vix=17.0, fii=0.0, rsi=50.0,
                      brent=None, usdinr=None, spx=None):
    d = RegimeDetector()
    monkeypatch.setattr(RegimeDetector, "_get_vix", lambda self, a: vix)
    monkeypatch.setattr(RegimeDetector, "_get_fii_proxy", lambda self, a: fii)
    monkeypatch.setattr(RegimeDetector, "_get_sector_rsi", lambda self, s, a: rsi)
    monkeypatch.setattr(RegimeDetector, "_get_5d_pct",
                        lambda self, t: {"BZ=F": brent, "INR=X": usdinr}.get(t))
    monkeypatch.setattr(RegimeDetector, "_get_last_session_pct", lambda self, t: spx)
    return d


def test_detect_escalates_normal_to_risk_off_on_two_signals(monkeypatch):
    d = _patched_detector(monkeypatch, brent=9.0, usdinr=1.8)
    snap = d.detect(date(2026, 7, 27), "automobile")
    assert snap.regime_label == "RISK_OFF"
    assert snap.global_stress_signals == ["brent_shock", "usdinr_stress"]
    assert snap.brent_5d_pct == 9.0
    assert "brent" in snap.narrative.lower()


def test_detect_single_signal_no_escalation(monkeypatch):
    d = _patched_detector(monkeypatch, brent=9.0)
    snap = d.detect(date(2026, 7, 27), "automobile")
    assert snap.regime_label == "NORMAL"
    assert snap.global_stress_signals == ["brent_shock"]


def test_detect_fetch_failure_degrades_to_current_behavior(monkeypatch):
    d = _patched_detector(monkeypatch)          # all three None
    snap = d.detect(date(2026, 7, 27), "automobile")
    assert snap.regime_label == "NORMAL"
    assert snap.global_stress_signals == []


def test_detect_multipliers_follow_escalated_label(monkeypatch):
    from core.config import settings
    d = _patched_detector(monkeypatch, vix=23.0, fii=-1.5, brent=9.0, spx=-3.0)
    snap = d.detect(date(2026, 7, 27), "automobile")   # MACRO_CRISIS base... 
    # base label with vix 23 & fii -1.5 is MACRO_CRISIS; escalation keeps it
    assert snap.regime_label == "MACRO_CRISIS"
    assert snap.multipliers == settings.REGIME_MULTIPLIERS["MACRO_CRISIS"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/regime/test_global_stress.py -v`
Expected: new tests FAIL — `_get_5d_pct` doesn't exist.

- [ ] **Step 3: Implement**

3a. Fetchers (place after `_get_sector_rsi`, mirroring `_get_vix`'s non-fatal pattern; note these return `None` on failure, not a numeric fallback — `None` means "signal unavailable, never counts as stress"):

```python
    def _get_5d_pct(self, ticker: str) -> float | None:
        """5-session % change for a global ticker. None on any failure."""
        try:
            import yfinance as yf
            df = yf.Ticker(ticker).history(period="1mo")
            if df.empty or len(df) < 6:
                return None
            close = df["Close"]
            return round(float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100.0), 4)
        except Exception as exc:
            logger.warning("[RegimeDetector] 5d fetch failed for %s (neutral): %s",
                           ticker, exc)
            return None

    def _get_last_session_pct(self, ticker: str) -> float | None:
        """Last completed session % move. None on any failure."""
        try:
            import yfinance as yf
            df = yf.Ticker(ticker).history(period="5d")
            if df.empty or len(df) < 2:
                return None
            close = df["Close"]
            return round(float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100.0), 4)
        except Exception as exc:
            logger.warning("[RegimeDetector] last-session fetch failed for %s (neutral): %s",
                           ticker, exc)
            return None
```

3b. `detect()` — between classification and snapshot construction, replace the current `label = ...` / `multipliers = ...` / `narrative = ...` sequence with:

```python
        label = self._classify(vix, fii_proxy, sector_rsi)

        brent = self._get_5d_pct(settings.REGIME_BRENT_TICKER)
        usdinr = self._get_5d_pct(settings.REGIME_USDINR_TICKER)
        spx = self._get_last_session_pct(settings.REGIME_SPX_TICKER)
        stress = self._global_stress_signals(brent, usdinr, spx)
        escalated = self._escalate_label(label, len(stress))
        if escalated != label:
            logger.info("[RegimeDetector] global stress %s escalated %s -> %s",
                        stress, label, escalated)
        label = escalated

        multipliers = dict(settings.REGIME_MULTIPLIERS.get(
            label, settings.REGIME_MULTIPLIERS["NORMAL"]))
        narrative = self._build_narrative(label, vix, fii_proxy, sector_rsi)
        if stress:
            parts = []
            if brent is not None:
                parts.append(f"Brent 5d {brent:+.1f}%")
            if usdinr is not None:
                parts.append(f"USDINR 5d {usdinr:+.2f}%")
            if spx is not None:
                parts.append(f"S&P last {spx:+.1f}%")
            narrative += (f" Global stress [{', '.join(stress)}]: "
                          + ", ".join(parts) + ".")
```

and extend the `RegimeSnapshot(...)` construction with:

```python
            brent_5d_pct      = brent,
            usdinr_5d_pct     = usdinr,
            spx_last_pct      = spx,
            global_stress_signals = stress,
```

- [ ] **Step 4: Run regime + shock-path tests**

Run: `python -m pytest tests/unit/intelligence/regime/ tests/unit/intelligence/rl/test_regime.py tests/unit/intelligence/rl/test_shock_path.py -v`
Expected: all PASS (test_shock_path monkeypatches `detect` wholesale, unaffected).

- [ ] **Step 5: Commit**

```bash
git add core/intelligence/regime/detector.py tests/unit/intelligence/regime/test_global_stress.py
git commit -m "feat(regime): wire Brent/USDINR/SPX escalation notch into detect()

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: UI — show IST time, buy price, P&L %, and reason per trade

**Files:**
- Modify: `src/frontend/prototypes/portfolio.jsx` (`ActivityCard` ~line 564, `LiveActivityCard` ~line 599)

**Interfaces:**
- Consumes: `/portfolio/transactions` rows now carrying `cost_basis`, `pnl_pct`, `reason` (Tasks 1–2; pydantic serializes them automatically — no API change).

- [ ] **Step 1: Implement the rendering changes**

1a. Add an IST time formatter near the top of the file (beside other helpers):

```jsx
function fmtIST(ts, dateStr) {
  try {
    if (ts) {
      const d = new Date(ts);
      if (!isNaN(d)) return d.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short',
        hour: '2-digit', minute: '2-digit', hour12: false });
    }
  } catch (e) { /* fall through */ }
  return dateStr || '';
}
```

1b. Replace the `items` mapping in `LiveActivityCard` (lines ~601–609) with:

```jsx
  const items = (showAll ? txns : txns.slice(0, 10)).map(t => {
    const isSell = t.side === 'SELL';
    const buyPx = isSell
      ? (t.cost_basis != null ? t.cost_basis
         : (t.realized_pnl != null && t.qty ? t.price - t.realized_pnl / t.qty : null))
      : null;
    const approx = isSell && t.cost_basis == null && buyPx != null;
    const pnlPct = isSell
      ? (t.pnl_pct != null ? t.pnl_pct
         : (buyPx ? (t.price / buyPx - 1) * 100 : null))
      : null;
    return {
      kind: isSell ? 'sell' : 'buy',
      sym: t.symbol, qty: t.qty, price: t.price,
      buyPx, approx,
      text: [t.verdict || t.source,
             isSell && t.realized_pnl != null
               ? `realized ${t.realized_pnl >= 0 ? '+' : ''}₹${Math.abs(t.realized_pnl).toLocaleString('en-IN')}`
                 + (pnlPct != null ? ` (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%)` : '')
               : '',
             t.note].filter(Boolean).join(' · '),
      reason: t.reason || '',
      t: fmtIST(t.ts, t.date),
    };
  });
```

1c. In `ActivityCard`, extend the row body (after the `it.text` line, ~line 588) with a collapsed/expandable reason. Add at the top of `ActivityCard`:

```jsx
  const [openIdx, setOpenIdx] = useStatePf(null);
```

replace the `{it.qty && ...}` price fragment so sells show both prices:

```jsx
                  {it.qty && <span style={{ color:'var(--ink-3)', fontWeight:500 }}>
                    {' · '}{it.qty} @ ₹{it.price.toLocaleString('en-IN', {minimumFractionDigits:2})}
                    {it.buyPx != null && ` (bought @ ${it.approx ? '≈' : ''}₹${it.buyPx.toLocaleString('en-IN', {maximumFractionDigits:2})})`}
                  </span>}
```

and after the `{it.text && ...}` line add:

```jsx
                {it.reason && (
                  <div style={{ marginTop:4 }}>
                    <button onClick={()=>setOpenIdx(openIdx===i?null:i)}
                      style={{ background:'none', border:'none', padding:0, cursor:'pointer',
                               fontSize:11, fontWeight:600, color:'var(--violet)' }}>
                      {openIdx===i ? 'hide why' : 'why?'}
                    </button>
                    {openIdx===i && (
                      <div style={{ fontSize:12, color:'var(--ink-2)', marginTop:4,
                                    padding:'8px 10px', background:'var(--violet-soft)',
                                    borderRadius:8 }}>{it.reason}</div>
                    )}
                  </div>
                )}
```

(Other `ActivityCard` callers pass items without `reason`/`buyPx` — both render nothing when absent.)

- [ ] **Step 2: Transpile check (repo pattern — no browser smoke in-session)**

Run (PowerShell, repo root):

```powershell
npx --yes esbuild "src/frontend/prototypes/portfolio.jsx" --loader:.jsx=jsx --outfile="$env:TEMP\pf_transpile_check.js"
```

Expected: exit 0, no syntax errors. Delete the temp output afterwards.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/prototypes/portfolio.jsx
git commit -m "feat(transparency): activity card shows IST time, buy/sell prices, P&L% and expandable reason

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Full-suite A/B verify + merge readiness

**Files:** none modified (verification only).

- [ ] **Step 1: Run the full suite**

```bash
python -m pytest -q 2>&1 | tail -40 > "$TEMP/transparency_after.txt"
cat "$TEMP/transparency_after.txt"
```

- [ ] **Step 2: Compare fail-sets**

The failed/errored test ids in `transparency_after.txt` must be EXACTLY the Task 0 baseline set (`transparency_baseline.txt`) — same tests, no additions, no removals. Passed count should be baseline + the new tests added by Tasks 1–6. Any new failure = fix before proceeding (superpowers:systematic-debugging), never rationalize.

- [ ] **Step 3: Verify spec watch-items are wired**

Quick greps (all must hit):

```bash
grep -n "trailing_stop_breach" core/portfolio/advisor.py core/portfolio/narrator.py
grep -n "cost_basis" core/portfolio/autopilot.py
grep -n "_escalate_label" core/intelligence/regime/detector.py
grep -n "fmtIST" src/frontend/prototypes/portfolio.jsx
```

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch — merge `transparency-wave` to `main` locally. Do NOT push; the user schedules pushes (never 16:25–17:15 IST on trading days). Remind the user of the spec's rollout note: on the first 16:30 IST run after deploy, the trailing stop may legitimately fire profit-booking EXITs on positions far off their peaks.

---

## Self-review notes

- Spec coverage: A → Tasks 1, 2, 7 (digest/brief inherit via `model_dump`, verified: `core/delivery/brief.py` reads digest holdings only, so no brief change is needed); B → Tasks 3, 4; C → Tasks 5, 6; testing/rollout → Tasks 0, 8.
- Type consistency: `peak_close_since_entry: float | None`, `_global_stress_signals` returns `list[str]`, `_escalate_label(str, int) -> str` — names match across tasks.
- The `_execute_buys(store=None)` test relies on monkeypatching `_last_add_date` (the only store use on the ADD path); if implementation changes that, stub the new access rather than constructing a real store.
