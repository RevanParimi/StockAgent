# Compass Phase A — Portfolio Core + Advisor v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-user VIRTUAL portfolio (mock money, real NSE prices) with corp-action-adjusted P&L, auto-promotion into the managed universe (4 supported sectors), a deterministic HOLD/ADD/TRIM/EXIT advisor with ATR-scaled stops and an append-only advice ledger, and an EOD digest event-triggered on daily-review completion.

**Architecture:** New `core/portfolio/` package (store, corp-actions, promotion, advisor, narrator, digest, pipeline) + one new fetcher (`services/data/fetchers/corporate_events.py`) + one new API router (`services/api/routes/portfolio_api.py`). The advisor is pure Python over artifacts the RL foundation already writes (PredictionStore envelope/feedback/dossier); the LLM (BULK tier) only narrates. The post-review pipeline hooks into `_review_task` in `scheduler_api.py` — event-triggered, never clock-scheduled.

**Tech Stack:** Python 3.11, Pydantic v2, FastAPI, pytest, yfinance, `nse` package (NseIndiaApi), OpenRouter via `services/clients/llm_client.py`.

**Spec:** `docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md` (§4 M1, §5 M2, §10 Phase A row).

## Global Constraints

- **USER DECISION 2026-07-06: auth gate / SCHEDULER_KEY lockdown is DEFERRED** ("right now it's fine, no need to lock down" — virtual money). Routes reuse the existing optional `X-Scheduler-Key` pattern from `scheduler_api.py:_check_auth` and must NOT hard-require it.
- Virtual-first: every holding defaults `virtual: true`; entry price = real NSE close on entry date; mark-to-market on trading days only (`core.intelligence.rl.nse_calendar.is_trading_day`).
- Per-user layout from day one: `data/portfolio/<user_id>/…`. Default user id from config (`portfolio.default_user_id: "primary"`).
- **Corp-action invariant (BLOCKER-grade):** corp-action sync adjusts `adj_avg_price`/`adj_qty` BEFORE any advisor rule runs. All P&L/stop math uses `adj_avg_price`, never `avg_buy_price`.
- **Verdict precedence, non-negotiable: EXIT > TRIM > ADD > HOLD.** LTCG tax logic may soften a TRIM into a WAIT_FOR_LTCG note; it must NEVER suppress or delay an EXIT.
- Phase A promotion supports ONLY the 4 sectors in `sector_router.py` (`automobile`, `banking_bfsi`, `it_sector`, `renewable_energy`); anything else is rejected with a clear "sector not yet supported" status. Do NOT touch sector_router's fallback.
- Every `response_format={"type": "json_object"}` LLM call passes `extra_body=JSON_MODE_EXTRA_BODY` (from `services/clients/llm_client.py`).
- Pipeline errors are telemetry, never training signal: every new pipeline step is wrapped so failure logs a warning and never blocks the daily review or other holdings.
- All tunables go in `config.yaml` + `src/backend/shared/config/settings/base.py` via `cfg("section.key", env=..., fallback=...)`. Secrets never in config.yaml.
- All persistent state lives under `data/` (Railway volume). Atomic JSON writes (temp file + rename, same pattern as `PredictionStore._write_json`).
- Output copy is research/analysis, never "advice"; no auto-trading anywhere.
- New code follows the restructure layout — schemas in `src/backend/shared/schemas/`, no files in retired dirs (`agents/`, `models/`, `tools/`, …).
- Existing test baseline is 285 passing / 7 skipped — every task's final test run must not break existing tests.
- Run tests from repo root: `python -m pytest tests/unit/<file> -v` (pythonpath `[".", "src"]` comes from pyproject.toml).

---

### Task 1: Config + settings for `portfolio.*` and `advisor.*`

**Files:**
- Modify: `config.yaml` (append at end, after `unified_analyst:` block)
- Modify: `src/backend/shared/config/settings/base.py` (append at end)
- Test: `tests/unit/test_portfolio_settings.py`

**Interfaces:**
- Produces: `settings.PORTFOLIO_DATA_DIR: str`, `settings.PORTFOLIO_DEFAULT_USER_ID: str`, `settings.PORTFOLIO_MAX_MANAGED_TICKERS: int`, `settings.PORTFOLIO_WEEKLY_REVIEW_WEEKDAY: int`, `settings.ADVISOR_ENABLED: bool`, `settings.ADVISOR_NARRATE: bool`, `settings.ADVISOR_ATR_PERIOD: int`, `settings.ADVISOR_STOP_ATR_MULT: float`, `settings.ADVISOR_STOP_BUCKETS: dict[str, tuple[float, float]]`, `settings.ADVISOR_LARGE_CAP_FLOOR_CR: float`, `settings.ADVISOR_MID_CAP_FLOOR_CR: float`, `settings.ADVISOR_TRIM_PROFIT_PCT: float`, `settings.ADVISOR_REVERSION_PRIOR_ELEVATED: float`, `settings.ADVISOR_CONFIDENCE_DECLINE_THRESHOLD: float`, `settings.ADVISOR_ENVELOPE_FLAT_BAND_PCT: float`, `settings.ADVISOR_ADD_MIN_DIRECTION_ACCURACY: float`, `settings.ADVISOR_MAX_POSITION_PCT: float`, `settings.ADVISOR_SECTOR_CONCENTRATION_WARN_PCT: float`, `settings.ADVISOR_LTCG_WAIT_MIN_MONTHS: int`, `settings.ADVISOR_EARNINGS_GAP_DAYS: int`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_settings.py
"""Compass Phase A — portfolio/advisor tunables exposed via settings."""
from core.config import settings


def test_portfolio_settings_present():
    assert settings.PORTFOLIO_DATA_DIR == "data/portfolio"
    assert settings.PORTFOLIO_DEFAULT_USER_ID == "primary"
    assert settings.PORTFOLIO_MAX_MANAGED_TICKERS == 40
    assert settings.PORTFOLIO_WEEKLY_REVIEW_WEEKDAY == 4


def test_advisor_settings_present():
    assert settings.ADVISOR_ENABLED is True
    assert settings.ADVISOR_NARRATE is True
    assert settings.ADVISOR_ATR_PERIOD == 20
    assert settings.ADVISOR_STOP_ATR_MULT == 3.0
    assert settings.ADVISOR_TRIM_PROFIT_PCT == 25.0
    assert settings.ADVISOR_MAX_POSITION_PCT == 10.0
    assert settings.ADVISOR_LTCG_WAIT_MIN_MONTHS == 10
    assert settings.ADVISOR_EARNINGS_GAP_DAYS == 3
    assert settings.ADVISOR_REVERSION_PRIOR_ELEVATED == 0.20
    assert settings.ADVISOR_CONFIDENCE_DECLINE_THRESHOLD == 0.05
    assert settings.ADVISOR_ENVELOPE_FLAT_BAND_PCT == 1.0
    assert settings.ADVISOR_ADD_MIN_DIRECTION_ACCURACY == 0.60
    assert settings.ADVISOR_SECTOR_CONCENTRATION_WARN_PCT == 30.0


def test_advisor_stop_buckets_are_tuples():
    buckets = settings.ADVISOR_STOP_BUCKETS
    assert set(buckets) == {"large", "mid", "small"}
    assert buckets["large"] == (8.0, 12.0)
    assert buckets["mid"] == (12.0, 18.0)
    assert buckets["small"] == (15.0, 22.0)
    assert settings.ADVISOR_LARGE_CAP_FLOOR_CR == 65000.0
    assert settings.ADVISOR_MID_CAP_FLOOR_CR == 20000.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_settings.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'PORTFOLIO_DATA_DIR'`

- [ ] **Step 3: Append config.yaml sections**

Append to `config.yaml` (after the `unified_analyst:` block):

```yaml
# =============================================================================
# Compass Phase A — Portfolio Core + Position Advisor (spec 2026-07-06)
# =============================================================================
portfolio:
  data_dir: "data/portfolio"     # per-user roots: data/portfolio/<user_id>/
  default_user_id: "primary"     # single-user launch; per-user layout from day one
  max_managed_tickers: 40        # auto-promotion cap — guards LLM spend (~$19/mo at 40)
  weekly_review_weekday: 4       # Friday: watchlist-cadence names review this weekday only

advisor:
  enabled: true
  narrate: true                  # BULK-tier narration of verdicts (deterministic fallback on failure)
  # Volatility-scaled stops, not a flat % (spec §5.2):
  # stop_pct = clamp(stop_atr_mult × ATR(atr_period) as %, bucket floor, bucket cap)
  atr_period: 20
  stop_atr_mult: 3.0
  stop_buckets:                  # [floor_pct, cap_pct] per market-cap bucket
    large: [8.0, 12.0]
    mid:   [12.0, 18.0]
    small: [15.0, 22.0]
  large_cap_floor_cr: 65000      # ₹ crore free-float mcap thresholds for bucket resolution
  mid_cap_floor_cr: 20000
  trim_profit_pct: 25.0
  reversion_prior_elevated: 0.20 # conviction-streak reversion prior considered "elevated"
  confidence_decline_threshold: 0.05  # remaining-envelope confidence drop that counts as declining
  envelope_flat_band_pct: 1.0    # remaining-forecast drift within ±this% = FLAT
  add_min_direction_accuracy: 0.60    # last-7-entries hit rate needed for ADD
  max_position_pct: 10.0
  sector_concentration_warn_pct: 30.0
  ltcg_wait_min_months: 10       # TRIM in month 10-12 with intact thesis -> WAIT_FOR_LTCG note
  earnings_gap_days: 3           # profitable + earnings within N trading days -> protection flag
```

- [ ] **Step 4: Append settings constants**

Append to `src/backend/shared/config/settings/base.py` (at end of file):

```python
# ---------------------------------------------------------------------------
# Compass Phase A — Portfolio Core + Position Advisor (spec 2026-07-06)
# ---------------------------------------------------------------------------
PORTFOLIO_DATA_DIR: str = cfg("portfolio.data_dir", env="PORTFOLIO_DATA_DIR", fallback="data/portfolio")
PORTFOLIO_DEFAULT_USER_ID: str = cfg("portfolio.default_user_id", env="PORTFOLIO_DEFAULT_USER_ID", fallback="primary")
PORTFOLIO_MAX_MANAGED_TICKERS: int = cfg("portfolio.max_managed_tickers", env="PORTFOLIO_MAX_MANAGED_TICKERS", fallback=40)
PORTFOLIO_WEEKLY_REVIEW_WEEKDAY: int = cfg("portfolio.weekly_review_weekday", fallback=4)

ADVISOR_ENABLED: bool = bool(cfg("advisor.enabled", env="ADVISOR_ENABLED", fallback=True))
ADVISOR_NARRATE: bool = bool(cfg("advisor.narrate", fallback=True))
ADVISOR_ATR_PERIOD: int = cfg("advisor.atr_period", fallback=20)
ADVISOR_STOP_ATR_MULT: float = cfg("advisor.stop_atr_mult", fallback=3.0)
_DEFAULT_STOP_BUCKETS: dict[str, tuple[float, float]] = {
    "large": (8.0, 12.0),
    "mid":   (12.0, 18.0),
    "small": (15.0, 22.0),
}
ADVISOR_STOP_BUCKETS: dict[str, tuple[float, float]] = {
    k: tuple(v) for k, v in cfg("advisor.stop_buckets", fallback=_DEFAULT_STOP_BUCKETS).items()
}
ADVISOR_LARGE_CAP_FLOOR_CR: float = float(cfg("advisor.large_cap_floor_cr", fallback=65000))
ADVISOR_MID_CAP_FLOOR_CR: float = float(cfg("advisor.mid_cap_floor_cr", fallback=20000))
ADVISOR_TRIM_PROFIT_PCT: float = cfg("advisor.trim_profit_pct", fallback=25.0)
ADVISOR_REVERSION_PRIOR_ELEVATED: float = cfg("advisor.reversion_prior_elevated", fallback=0.20)
ADVISOR_CONFIDENCE_DECLINE_THRESHOLD: float = cfg("advisor.confidence_decline_threshold", fallback=0.05)
ADVISOR_ENVELOPE_FLAT_BAND_PCT: float = cfg("advisor.envelope_flat_band_pct", fallback=1.0)
ADVISOR_ADD_MIN_DIRECTION_ACCURACY: float = cfg("advisor.add_min_direction_accuracy", fallback=0.60)
ADVISOR_MAX_POSITION_PCT: float = cfg("advisor.max_position_pct", fallback=10.0)
ADVISOR_SECTOR_CONCENTRATION_WARN_PCT: float = cfg("advisor.sector_concentration_warn_pct", fallback=30.0)
ADVISOR_LTCG_WAIT_MIN_MONTHS: int = cfg("advisor.ltcg_wait_min_months", fallback=10)
ADVISOR_EARNINGS_GAP_DAYS: int = cfg("advisor.earnings_gap_days", fallback=3)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_settings.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add config.yaml src/backend/shared/config/settings/base.py tests/unit/test_portfolio_settings.py
git commit -m "feat(compass): portfolio + advisor tunables in config.yaml/settings (Phase A Task 1)"
```

---

### Task 2: Portfolio schemas

**Files:**
- Create: `src/backend/shared/schemas/portfolio.py`
- Test: `tests/unit/test_portfolio_schemas.py`

**Interfaces:**
- Produces (all Pydantic v2 `BaseModel`): `Verdict = Literal["HOLD","ADD","TRIM","EXIT"]`; `AppliedCorpAction(key, ex_date, kind, desc, ratio=1.0, dividend_per_share=0.0, applied_on)`; `Holding(symbol, sector, qty, avg_buy_price, adj_avg_price, adj_qty, buy_date, virtual=True, broker="", notes="", target_pct=None, max_loss_pct=None, dividends_received=0.0, applied_actions=[])`; `WatchlistItem(symbol, sector="", added, reason="", source="user")`; `Portfolio(user_id, holdings=[], watchlist=[], cash_deployable=None, risk_profile="balanced", updated_at="")`; `AdviceRecord(date, user_id, symbol, verdict, close, unrealised_pnl_pct, stop_pct, triggers=[], notes=[], confidence=0.5, narrative="", rationale_hash="", outcome_10td=None, outcome_30td=None, outcome_60td=None)`; `CorporateEvent(symbol, date, kind, desc)`
- `Holding.unrealised_pnl_pct(close: float) -> float` — includes dividends: `((close - adj_avg_price) * adj_qty + dividends_received) / (adj_avg_price * adj_qty) * 100`
- `Holding.age_days(on: date) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_schemas.py
"""Compass Phase A — portfolio schema validation and P&L math."""
from datetime import date

import pytest
from pydantic import ValidationError

from backend.shared.schemas.portfolio import (
    AdviceRecord,
    AppliedCorpAction,
    CorporateEvent,
    Holding,
    Portfolio,
    WatchlistItem,
)


def _holding(**kw) -> Holding:
    base = dict(
        symbol="MARUTI", sector="automobile", qty=10, avg_buy_price=12000.0,
        adj_avg_price=12000.0, adj_qty=10, buy_date="2026-01-05",
    )
    base.update(kw)
    return Holding(**base)


def test_holding_defaults_virtual_true():
    h = _holding()
    assert h.virtual is True
    assert h.dividends_received == 0.0
    assert h.applied_actions == []


def test_unrealised_pnl_uses_adjusted_price_and_dividends():
    # 1:1 bonus applied: adj price halved, qty doubled; +₹50 dividends received
    h = _holding(adj_avg_price=6000.0, adj_qty=20, dividends_received=50.0)
    # close 6600: price gain (6600-6000)*20 = 12000; +50 dividends; cost 120000
    assert h.unrealised_pnl_pct(6600.0) == pytest.approx((12000 + 50) / 120000 * 100)


def test_holding_age_days():
    h = _holding(buy_date="2026-01-05")
    assert h.age_days(date(2026, 7, 6)) == 182


def test_portfolio_risk_profile_validated():
    with pytest.raises(ValidationError):
        Portfolio(user_id="primary", risk_profile="yolo")


def test_advice_record_verdict_validated():
    with pytest.raises(ValidationError):
        AdviceRecord(
            date="2026-07-06", user_id="primary", symbol="MARUTI",
            verdict="MOON", close=100.0, unrealised_pnl_pct=0.0, stop_pct=10.0,
        )


def test_watchlist_source_default_user():
    w = WatchlistItem(symbol="TCS", added="2026-07-06")
    assert w.source == "user"


def test_corporate_event_fields():
    e = CorporateEvent(symbol="INFY", date="2026-07-15", kind="results", desc="Board meeting - financial results")
    assert e.kind == "results"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.shared.schemas.portfolio'`

- [ ] **Step 3: Write the schemas module**

```python
# src/backend/shared/schemas/portfolio.py
"""
Compass Phase A — Portfolio Core schemas (spec §4.1).

Virtual-first: holdings are mock-money positions at real NSE prices.
adj_avg_price / adj_qty are corp-action-adjusted — ALL P&L and stop math
uses them, never the raw avg_buy_price (a 1:1 bonus would otherwise look
like a −50% crash and fire a false EXIT).
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["HOLD", "ADD", "TRIM", "EXIT"]


class AppliedCorpAction(BaseModel):
    """One corporate action already applied to a holding (idempotency record)."""
    key: str                       # dedupe key: "{symbol}|{ex_date}|{desc[:40]}"
    ex_date: str                   # ISO date
    kind: Literal["split", "bonus", "dividend"]
    desc: str
    ratio: float = 1.0             # qty multiplier (2.0 for 1:1 bonus, 5.0 for 10→2 split)
    dividend_per_share: float = 0.0
    applied_on: str                # ISO date the sync applied it


class Holding(BaseModel):
    symbol: str
    sector: str
    qty: float                     # as entered by the user — never mutated
    avg_buy_price: float           # as entered — never mutated
    adj_avg_price: float           # corp-action-adjusted; ALL P&L/stop math uses this
    adj_qty: float                 # corp-action-adjusted quantity
    buy_date: str                  # ISO date
    virtual: bool = True           # mock-money position (launch default)
    broker: str = ""
    notes: str = ""
    target_pct: float | None = None
    max_loss_pct: float | None = None
    dividends_received: float = 0.0     # total ₹ credited (adj_qty × dps at each ex-date)
    applied_actions: list[AppliedCorpAction] = Field(default_factory=list)

    def unrealised_pnl_pct(self, close: float) -> float:
        """P&L % vs adjusted cost, dividend-inclusive so HOLD/TRIM scoring
        isn't biased against payers (spec §4.1)."""
        cost = self.adj_avg_price * self.adj_qty
        if cost <= 0:
            return 0.0
        gain = (close - self.adj_avg_price) * self.adj_qty + self.dividends_received
        return gain / cost * 100.0

    def age_days(self, on: date) -> int:
        return (on - date.fromisoformat(self.buy_date)).days


class WatchlistItem(BaseModel):
    symbol: str
    sector: str = ""
    added: str                     # ISO date
    reason: str = ""
    source: Literal["user", "discovery"] = "user"


class Portfolio(BaseModel):
    user_id: str
    holdings: list[Holding] = Field(default_factory=list)
    watchlist: list[WatchlistItem] = Field(default_factory=list)
    cash_deployable: float | None = None      # optional — enables ADD sizing later
    risk_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"
    updated_at: str = ""


class AdviceRecord(BaseModel):
    """One advice-ledger line (append-only JSONL). Outcome fields are filled
    later by the review machinery (Phase D); ledger exists from day one so
    data accumulates immediately (spec §5.3)."""
    date: str
    user_id: str
    symbol: str
    verdict: Verdict
    close: float
    unrealised_pnl_pct: float
    stop_pct: float
    triggers: list[str] = Field(default_factory=list)   # machine-readable rule codes
    notes: list[str] = Field(default_factory=list)      # WAIT_FOR_LTCG, EARNINGS_GAP_PROTECTION, ...
    confidence: float = 0.5
    narrative: str = ""            # LLM narration (research tone, never "advice")
    rationale_hash: str = ""
    outcome_10td: float | None = None
    outcome_30td: float | None = None
    outcome_60td: float | None = None


class CorporateEvent(BaseModel):
    """Forward-looking calendar entry (board meetings / results dates).
    Feeds the advisor's earnings-gap rule (spec §5.2)."""
    symbol: str
    date: str                      # ISO date of the event
    kind: Literal["results", "meeting", "action", "other"] = "other"
    desc: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_schemas.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/schemas/portfolio.py tests/unit/test_portfolio_schemas.py
git commit -m "feat(compass): portfolio/advice/corp-action schemas (Phase A Task 2)"
```

---

### Task 3: PortfolioStore — per-user JSON store + CSV import

**Files:**
- Create: `core/portfolio/__init__.py` (empty)
- Create: `core/portfolio/store.py`
- Test: `tests/unit/test_portfolio_store.py`

**Interfaces:**
- Consumes: Task 2 schemas; `settings.PORTFOLIO_DATA_DIR`, `settings.PORTFOLIO_DEFAULT_USER_ID`
- Produces: `PortfolioStore(user_id: str | None = None, base_dir: str | None = None)` with:
  - `.load() -> Portfolio` (empty Portfolio if file missing)
  - `.save(p: Portfolio) -> None` (atomic; stamps `updated_at`)
  - `.add_holding(h: Holding) -> Portfolio` (merges same-symbol lots into weighted-avg; raises `ValueError` on qty<=0/price<=0)
  - `.remove_holding(symbol: str) -> bool`
  - `.add_watchlist(w: WatchlistItem) -> Portfolio` (dedupes by symbol)
  - `.remove_watchlist(symbol: str) -> bool`
  - `.append_advice(rec: AdviceRecord) -> None` / `.load_advice(limit: int = 200) -> list[AdviceRecord]` (JSONL `advice_ledger.jsonl`)
  - `.save_digest(digest: dict) -> Path` / `.load_latest_digest() -> dict | None` (under `digests/`)
  - `import_csv(text: str, user_id: str | None = None, base_dir: str | None = None, price_lookup=None) -> dict` module function; CSV columns `symbol,sector,qty,avg_buy_price,buy_date` (avg_buy_price may be blank → `price_lookup(symbol, buy_date)` fills it)
  - `list_user_ids(base_dir: str | None = None) -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_store.py
"""Compass Phase A — per-user portfolio store: CRUD, ledger, CSV import."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding, WatchlistItem
from core.portfolio.store import PortfolioStore, import_csv, list_user_ids


def _holding(symbol="MARUTI", qty=10, price=12000.0) -> Holding:
    return Holding(
        symbol=symbol, sector="automobile", qty=qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=qty, buy_date="2026-01-05",
    )


@pytest.fixture
def store(tmp_path):
    return PortfolioStore(user_id="testuser", base_dir=str(tmp_path))


def test_load_empty_portfolio(store):
    p = store.load()
    assert p.user_id == "testuser"
    assert p.holdings == [] and p.watchlist == []


def test_add_and_reload_holding(store, tmp_path):
    store.add_holding(_holding())
    p = PortfolioStore(user_id="testuser", base_dir=str(tmp_path)).load()
    assert len(p.holdings) == 1
    assert p.holdings[0].symbol == "MARUTI"
    assert p.updated_at != ""


def test_add_same_symbol_merges_weighted_avg(store):
    store.add_holding(_holding(qty=10, price=100.0))
    p = store.add_holding(_holding(qty=10, price=200.0))
    h = p.holdings[0]
    assert len(p.holdings) == 1
    assert h.qty == 20 and h.adj_qty == 20
    assert h.avg_buy_price == pytest.approx(150.0)
    assert h.adj_avg_price == pytest.approx(150.0)


def test_add_holding_rejects_bad_input(store):
    with pytest.raises(ValueError):
        store.add_holding(_holding(qty=0))
    with pytest.raises(ValueError):
        store.add_holding(_holding(price=-5))


def test_remove_holding(store):
    store.add_holding(_holding())
    assert store.remove_holding("MARUTI") is True
    assert store.remove_holding("MARUTI") is False
    assert store.load().holdings == []


def test_watchlist_dedupe(store):
    w = WatchlistItem(symbol="TCS", sector="it_sector", added="2026-07-06")
    store.add_watchlist(w)
    p = store.add_watchlist(w)
    assert len(p.watchlist) == 1
    assert store.remove_watchlist("TCS") is True


def test_advice_ledger_append_only(store):
    rec = AdviceRecord(
        date="2026-07-06", user_id="testuser", symbol="MARUTI",
        verdict="HOLD", close=13000.0, unrealised_pnl_pct=8.3, stop_pct=10.0,
    )
    store.append_advice(rec)
    store.append_advice(rec.model_copy(update={"date": "2026-07-07"}))
    records = store.load_advice()
    assert [r.date for r in records] == ["2026-07-06", "2026-07-07"]


def test_digest_roundtrip(store):
    assert store.load_latest_digest() is None
    store.save_digest({"date": "2026-07-06", "holdings": []})
    store.save_digest({"date": "2026-07-07", "holdings": []})
    assert store.load_latest_digest()["date"] == "2026-07-07"


def test_import_csv_with_and_without_price(tmp_path):
    csv_text = (
        "symbol,sector,qty,avg_buy_price,buy_date\n"
        "MARUTI,automobile,10,12000,2026-01-05\n"
        "TCS,it_sector,5,,2026-02-10\n"
    )
    result = import_csv(
        csv_text, user_id="testuser", base_dir=str(tmp_path),
        price_lookup=lambda sym, d: 4000.0,
    )
    assert result["imported"] == 2 and result["errors"] == []
    p = PortfolioStore(user_id="testuser", base_dir=str(tmp_path)).load()
    tcs = next(h for h in p.holdings if h.symbol == "TCS")
    assert tcs.avg_buy_price == 4000.0 and tcs.adj_avg_price == 4000.0


def test_import_csv_reports_row_errors(tmp_path):
    csv_text = (
        "symbol,sector,qty,avg_buy_price,buy_date\n"
        "MARUTI,automobile,notanumber,12000,2026-01-05\n"
    )
    result = import_csv(csv_text, user_id="testuser", base_dir=str(tmp_path))
    assert result["imported"] == 0
    assert len(result["errors"]) == 1


def test_list_user_ids(tmp_path):
    PortfolioStore(user_id="alpha", base_dir=str(tmp_path)).add_holding(_holding())
    PortfolioStore(user_id="beta", base_dir=str(tmp_path)).add_holding(_holding())
    assert sorted(list_user_ids(base_dir=str(tmp_path))) == ["alpha", "beta"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.portfolio'`

- [ ] **Step 3: Write the store**

Create empty `core/portfolio/__init__.py`, then:

```python
# core/portfolio/store.py
"""
Compass Phase A — per-user portfolio store (spec §4.1).

Layout (volume-persisted, per-user from day one):
    data/portfolio/<user_id>/portfolio.json
    data/portfolio/<user_id>/advice_ledger.jsonl      (append-only)
    data/portfolio/<user_id>/digests/<YYYY-MM-DD>.json

Atomic JSON writes (temp + rename), same pattern as PredictionStore.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings
from backend.shared.schemas.portfolio import (
    AdviceRecord,
    Holding,
    Portfolio,
    WatchlistItem,
)

logger = logging.getLogger(__name__)


class PortfolioStore:
    def __init__(self, user_id: str | None = None, base_dir: str | None = None) -> None:
        self.user_id = (user_id or settings.PORTFOLIO_DEFAULT_USER_ID).strip()
        self._dir = Path(base_dir or settings.PORTFOLIO_DATA_DIR) / self.user_id
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    def _portfolio_path(self) -> Path:
        return self._dir / "portfolio.json"

    def _ledger_path(self) -> Path:
        return self._dir / "advice_ledger.jsonl"

    def _digest_dir(self) -> Path:
        d = self._dir / "digests"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Atomic write helper
    # ------------------------------------------------------------------
    def _write_json(self, path: Path, data: dict) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    # ------------------------------------------------------------------
    # Portfolio CRUD
    # ------------------------------------------------------------------
    def load(self) -> Portfolio:
        path = self._portfolio_path()
        if not path.exists():
            return Portfolio(user_id=self.user_id)
        try:
            return Portfolio(**json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.error("[PortfolioStore] failed to read %s: %s", path, exc)
            return Portfolio(user_id=self.user_id)

    def save(self, p: Portfolio) -> None:
        p.updated_at = datetime.now(timezone.utc).isoformat()
        self._write_json(self._portfolio_path(), p.model_dump())

    def add_holding(self, h: Holding) -> Portfolio:
        if h.qty <= 0 or h.avg_buy_price <= 0:
            raise ValueError(f"qty and avg_buy_price must be positive: {h.symbol}")
        p = self.load()
        existing = next((x for x in p.holdings if x.symbol == h.symbol), None)
        if existing:
            # Merge lots: weighted average on BOTH raw and adjusted figures.
            total_qty = existing.qty + h.qty
            existing.avg_buy_price = (
                existing.avg_buy_price * existing.qty + h.avg_buy_price * h.qty
            ) / total_qty
            adj_total = existing.adj_qty + h.adj_qty
            existing.adj_avg_price = (
                existing.adj_avg_price * existing.adj_qty + h.adj_avg_price * h.adj_qty
            ) / adj_total
            existing.qty = total_qty
            existing.adj_qty = adj_total
        else:
            p.holdings.append(h)
        self.save(p)
        return p

    def remove_holding(self, symbol: str) -> bool:
        p = self.load()
        before = len(p.holdings)
        p.holdings = [h for h in p.holdings if h.symbol != symbol.upper()]
        if len(p.holdings) == before:
            return False
        self.save(p)
        return True

    def add_watchlist(self, w: WatchlistItem) -> Portfolio:
        p = self.load()
        if not any(x.symbol == w.symbol for x in p.watchlist):
            p.watchlist.append(w)
            self.save(p)
        return p

    def remove_watchlist(self, symbol: str) -> bool:
        p = self.load()
        before = len(p.watchlist)
        p.watchlist = [w for w in p.watchlist if w.symbol != symbol.upper()]
        if len(p.watchlist) == before:
            return False
        self.save(p)
        return True

    # ------------------------------------------------------------------
    # Advice ledger (append-only JSONL — spec §5.3)
    # ------------------------------------------------------------------
    def append_advice(self, rec: AdviceRecord) -> None:
        with open(self._ledger_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.model_dump(), ensure_ascii=False) + "\n")

    def load_advice(self, limit: int = 200) -> list[AdviceRecord]:
        path = self._ledger_path()
        if not path.exists():
            return []
        records: list[AdviceRecord] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(AdviceRecord(**json.loads(line)))
            except Exception as exc:
                logger.warning("[PortfolioStore] skipping bad ledger line: %s", exc)
        return records

    # ------------------------------------------------------------------
    # Digests
    # ------------------------------------------------------------------
    def save_digest(self, digest: dict) -> Path:
        path = self._digest_dir() / f"{digest['date']}.json"
        self._write_json(path, digest)
        return path

    def load_latest_digest(self) -> dict | None:
        files = sorted(self._digest_dir().glob("*.json"))
        if not files:
            return None
        try:
            return json.loads(files[-1].read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("[PortfolioStore] failed to read digest %s: %s", files[-1], exc)
            return None


# ---------------------------------------------------------------------------
# CSV import (spec §4.2): symbol,sector,qty,avg_buy_price,buy_date
# avg_buy_price may be blank -> price_lookup(symbol, buy_date) fills it
# (real NSE close on the entry date — virtual-first pricing).
# ---------------------------------------------------------------------------

def import_csv(
    text: str,
    user_id: str | None = None,
    base_dir: str | None = None,
    price_lookup=None,
) -> dict:
    store = PortfolioStore(user_id=user_id, base_dir=base_dir)
    imported, errors = 0, []
    reader = csv.DictReader(io.StringIO(text))
    for i, row in enumerate(reader, start=2):   # row 1 = header
        try:
            symbol = (row["symbol"] or "").strip().upper()
            sector = (row["sector"] or "").strip()
            qty = float(row["qty"])
            buy_date = (row["buy_date"] or "").strip()
            raw_price = (row.get("avg_buy_price") or "").strip()
            if raw_price:
                price = float(raw_price)
            elif price_lookup is not None:
                price = float(price_lookup(symbol, buy_date))
            else:
                raise ValueError("avg_buy_price blank and no price_lookup available")
            store.add_holding(Holding(
                symbol=symbol, sector=sector, qty=qty, avg_buy_price=price,
                adj_avg_price=price, adj_qty=qty, buy_date=buy_date,
            ))
            imported += 1
        except Exception as exc:
            errors.append({"row": i, "error": str(exc)})
    return {"imported": imported, "errors": errors}


def list_user_ids(base_dir: str | None = None) -> list[str]:
    root = Path(base_dir or settings.PORTFOLIO_DATA_DIR)
    if not root.exists():
        return []
    return [d.name for d in root.iterdir() if d.is_dir() and (d / "portfolio.json").exists()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_store.py -v`
Expected: 11 PASS

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/__init__.py core/portfolio/store.py tests/unit/test_portfolio_store.py
git commit -m "feat(compass): per-user PortfolioStore with advice ledger + CSV import (Phase A Task 3)"
```

---

### Task 4: Entry/mark pricing helper

**Files:**
- Create: `core/portfolio/pricing.py`
- Test: `tests/unit/test_portfolio_pricing.py`

**Interfaces:**
- Consumes: `core.intelligence.rl.workflows.daily_review._fetch_actual_close(ticker: str, target_date: date) -> float | None` (existing, NSE-cross-checked); `core.intelligence.rl.nse_calendar.is_trading_day`
- Produces:
  - `close_on(symbol: str, on: date) -> float` — actual NSE close on `on` (walks BACK to the previous trading day if `on` is a holiday/weekend); raises `PriceUnavailableError` when nothing can be fetched
  - `PriceUnavailableError(Exception)`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_pricing.py
"""Compass Phase A — entry pricing: real NSE close on trading days only."""
from datetime import date

import pytest

import core.portfolio.pricing as pricing
from core.portfolio.pricing import PriceUnavailableError, close_on


def test_close_on_trading_day(monkeypatch):
    monkeypatch.setattr(pricing, "_fetch_actual_close", lambda sym, d: 12345.0)
    monkeypatch.setattr(pricing, "is_trading_day", lambda d: True)
    assert close_on("MARUTI", date(2026, 7, 3)) == 12345.0


def test_close_on_holiday_walks_back(monkeypatch):
    calls = []

    def fake_fetch(sym, d):
        calls.append(d)
        return 100.0

    # Sunday 2026-07-05 -> walks back to Friday 2026-07-03
    monkeypatch.setattr(pricing, "_fetch_actual_close", fake_fetch)
    assert close_on("MARUTI", date(2026, 7, 5)) == 100.0
    assert calls[0] == date(2026, 7, 3)


def test_close_on_raises_when_unavailable(monkeypatch):
    monkeypatch.setattr(pricing, "_fetch_actual_close", lambda sym, d: None)
    monkeypatch.setattr(pricing, "is_trading_day", lambda d: True)
    with pytest.raises(PriceUnavailableError):
        close_on("NOSUCH", date(2026, 7, 3))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_pricing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.portfolio.pricing'`

- [ ] **Step 3: Write the pricing helper**

```python
# core/portfolio/pricing.py
"""
Compass Phase A — real-price lookups for the virtual portfolio.

Entry price = actual NSE close on the entry date; mark-to-market happens on
trading days only (spec §4.1). Reuses daily_review's NSE-cross-checked close
fetcher so the portfolio and the RL loop can never disagree about a close.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from core.intelligence.rl.nse_calendar import is_trading_day
from core.intelligence.rl.workflows.daily_review import _fetch_actual_close

logger = logging.getLogger(__name__)

_MAX_WALKBACK_DAYS = 10


class PriceUnavailableError(Exception):
    """No close could be fetched for the symbol/date."""


def close_on(symbol: str, on: date) -> float:
    """Actual NSE close for `symbol` on `on`, walking back to the most recent
    trading day when `on` is a weekend/holiday. Raises PriceUnavailableError
    when no close can be fetched within the walkback window."""
    d = on
    for _ in range(_MAX_WALKBACK_DAYS):
        if is_trading_day(d):
            close = _fetch_actual_close(symbol.upper(), d)
            if close is not None:
                return float(close)
            break   # trading day but no data -> genuine fetch failure
        d -= timedelta(days=1)
    raise PriceUnavailableError(f"No NSE close available for {symbol} on/near {on}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_pricing.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/pricing.py tests/unit/test_portfolio_pricing.py
git commit -m "feat(compass): NSE-close pricing helper for virtual entries (Phase A Task 4)"
```

---

### Task 5: Corporate-events calendar fetcher + corp-actions feed

**Files:**
- Create: `services/data/fetchers/corporate_events.py`
- Test: `tests/unit/test_corporate_events_fetcher.py`

**Interfaces:**
- Consumes: `nse` package (`NSE.actions(symbol=...)`, `NSE.boardMeetings(symbol=...)` — same usage as `services/data/fetchers/nse_announcements.py:prefetch_nse_data`); `CorporateEvent` schema (Task 2)
- Produces:
  - `fetch_corp_actions(symbol: str) -> list[dict]` — raw NSE `actions()` rows (`[]` on any failure, never raises)
  - `refresh_events_calendar(symbols: list[str], cache_path: str | None = None) -> dict` — fetches board meetings per symbol, normalises to `CorporateEvent`, writes cache JSON `{"fetched_at": iso, "degraded": [syms...], "events": {sym: [event dicts]}}`; on per-symbol failure keeps that symbol's stale cache entry and lists it in `degraded` (spec §8 degraded mode)
  - `load_events_calendar(cache_path: str | None = None) -> dict` — cached calendar (`{"events": {}, ...}` shape, empty when missing)
  - `next_results_event(symbol: str, on: date, calendar: dict) -> CorporateEvent | None` — earliest future event with `kind == "results"`
  - Default cache path: `data/market_cache/corporate_events.json`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_corporate_events_fetcher.py
"""Compass Phase A — corporate-events calendar fetcher with degraded mode."""
import json
from datetime import date

import services.data.fetchers.corporate_events as ce


class _FakeNSE:
    """Stands in for nse.NSE — returns canned boardMeetings/actions."""
    def __init__(self, download_folder=None):
        pass

    def boardMeetings(self, symbol):
        if symbol == "BROKEN":
            raise RuntimeError("NSE 403")
        return [
            {"bm_date": "15-Jul-2026", "bm_purpose": "Financial Results", "bm_symbol": symbol},
            {"bm_date": "20-Aug-2026", "bm_purpose": "Fund Raising", "bm_symbol": symbol},
        ]

    def actions(self, symbol):
        return [{"subject": "Dividend - Rs 8 Per Share", "exDate": "10-Jul-2026"}]

    def exit(self):
        pass


def _patch_nse(monkeypatch):
    monkeypatch.setattr(ce, "_make_nse_client", lambda: _FakeNSE())


def test_refresh_normalises_board_meetings(tmp_path, monkeypatch):
    _patch_nse(monkeypatch)
    cache = tmp_path / "events.json"
    result = ce.refresh_events_calendar(["INFY"], cache_path=str(cache))
    events = result["events"]["INFY"]
    assert events[0]["date"] == "2026-07-15"
    assert events[0]["kind"] == "results"
    assert events[1]["kind"] == "meeting"
    assert result["degraded"] == []
    assert json.loads(cache.read_text(encoding="utf-8"))["events"]["INFY"]


def test_refresh_degraded_keeps_stale_entry(tmp_path, monkeypatch):
    _patch_nse(monkeypatch)
    cache = tmp_path / "events.json"
    stale = {
        "fetched_at": "2026-07-01T00:00:00",
        "degraded": [],
        "events": {"BROKEN": [{"symbol": "BROKEN", "date": "2026-07-20",
                                "kind": "results", "desc": "old entry"}]},
    }
    cache.write_text(json.dumps(stale), encoding="utf-8")
    result = ce.refresh_events_calendar(["BROKEN"], cache_path=str(cache))
    assert "BROKEN" in result["degraded"]
    assert result["events"]["BROKEN"][0]["desc"] == "old entry"   # stale kept


def test_fetch_corp_actions_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("nse import failed")
    monkeypatch.setattr(ce, "_make_nse_client", boom)
    assert ce.fetch_corp_actions("MARUTI") == []


def test_next_results_event():
    calendar = {"events": {"INFY": [
        {"symbol": "INFY", "date": "2026-07-01", "kind": "results", "desc": "past"},
        {"symbol": "INFY", "date": "2026-07-15", "kind": "results", "desc": "future"},
        {"symbol": "INFY", "date": "2026-07-10", "kind": "meeting", "desc": "not results"},
    ]}}
    ev = ce.next_results_event("INFY", date(2026, 7, 6), calendar)
    assert ev is not None and ev.date == "2026-07-15"
    assert ce.next_results_event("TCS", date(2026, 7, 6), calendar) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_corporate_events_fetcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.data.fetchers.corporate_events'`

- [ ] **Step 3: Write the fetcher**

```python
# services/data/fetchers/corporate_events.py
"""
Compass Phase A — NSE corporate-events calendar (spec §5.2, §8).

Two feeds, both behind the house non-fatal pattern:
  * fetch_corp_actions(symbol)      -> raw NSE actions() rows (splits/bonus/dividend)
  * refresh_events_calendar(syms)   -> forward board-meeting dates ("results" kind
                                       feeds the advisor's earnings-gap rule)

Degraded mode: a symbol whose fetch fails keeps its stale cache entry and is
listed under "degraded" — no feed is a single point of failure.
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
import time
from datetime import date, datetime, timezone

from backend.shared.schemas.portfolio import CorporateEvent

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/corporate_events.json"
_SLEEP_BETWEEN_CALLS = 0.5   # same safe margin as nse_announcements.py

# NSE date strings look like "15-Jul-2026"
_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")

_RESULTS_KEYWORDS = ("financial results", "results", "audited", "unaudited", "quarterly")


def _make_nse_client():
    """Isolated factory so tests can monkeypatch it."""
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _parse_nse_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    for fmt in _NSE_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _first_str(item: dict, *keys: str) -> str:
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def fetch_corp_actions(symbol: str) -> list[dict]:
    """Raw NSE actions() rows for a symbol. [] on any failure — never raises."""
    try:
        nse = _make_nse_client()
    except Exception as exc:
        logger.warning("[corporate_events] NSE client unavailable: %s", exc)
        return []
    try:
        raw = nse.actions(symbol=symbol)
        items = raw if isinstance(raw, list) else raw.get("data", [])
        return items if isinstance(items, list) else []
    except Exception as exc:
        logger.warning("[corporate_events] actions() failed for %s: %s", symbol, exc)
        return []
    finally:
        try:
            nse.exit()
        except Exception:
            pass


def refresh_events_calendar(symbols: list[str], cache_path: str | None = None) -> dict:
    """Fetch forward board meetings for each symbol into the cache file.
    Failed symbols keep their previous (stale) entries and are flagged."""
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    previous = load_events_calendar(cache_path=str(path))
    events: dict[str, list[dict]] = dict(previous.get("events", {}))
    degraded: list[str] = []

    try:
        nse = _make_nse_client()
    except Exception as exc:
        logger.warning("[corporate_events] NSE client unavailable — calendar fully degraded: %s", exc)
        result = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "degraded": list(symbols),
            "events": events,
        }
        _write_cache(path, result)
        return result

    try:
        for sym in symbols:
            try:
                raw = nse.boardMeetings(symbol=sym)
                items = raw if isinstance(raw, list) else raw.get("data", [])
                sym_events: list[dict] = []
                for item in items if isinstance(items, list) else []:
                    dt = _parse_nse_date(_first_str(item, "bm_date", "date", "meetingDate"))
                    desc = _first_str(item, "bm_purpose", "purpose", "bm_desc", "desc")
                    if not dt:
                        continue
                    kind = "results" if any(k in desc.lower() for k in _RESULTS_KEYWORDS) else "meeting"
                    sym_events.append(
                        CorporateEvent(symbol=sym, date=dt, kind=kind, desc=desc).model_dump()
                    )
                events[sym] = sorted(sym_events, key=lambda e: e["date"])
            except Exception as exc:
                logger.warning(
                    "[corporate_events] boardMeetings() failed for %s — keeping stale entry: %s",
                    sym, exc,
                )
                degraded.append(sym)
            time.sleep(_SLEEP_BETWEEN_CALLS)
    finally:
        try:
            nse.exit()
        except Exception:
            pass

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "degraded": degraded,
        "events": events,
    }
    _write_cache(path, result)
    return result


def load_events_calendar(cache_path: str | None = None) -> dict:
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    if not path.exists():
        return {"fetched_at": "", "degraded": [], "events": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("[corporate_events] cache unreadable %s: %s", path, exc)
        return {"fetched_at": "", "degraded": [], "events": {}}


def next_results_event(symbol: str, on: date, calendar: dict) -> CorporateEvent | None:
    """Earliest future results-kind event for symbol, or None."""
    for raw in calendar.get("events", {}).get(symbol, []):
        try:
            ev = CorporateEvent(**raw)
        except Exception:
            continue
        if ev.kind == "results" and date.fromisoformat(ev.date) >= on:
            return ev
    return None


def _write_cache(path: pathlib.Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[corporate_events] cache write failed %s: %s", path, exc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_corporate_events_fetcher.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add services/data/fetchers/corporate_events.py tests/unit/test_corporate_events_fetcher.py
git commit -m "feat(compass): NSE corporate-events calendar fetcher with degraded mode (Phase A Task 5)"
```

---

### Task 6: Corp-action sync — adjust `adj_avg_price` before any advisor rule

**Files:**
- Create: `core/portfolio/corp_actions.py`
- Test: `tests/unit/test_portfolio_corp_actions.py`

**Interfaces:**
- Consumes: `fetch_corp_actions(symbol)` (Task 5), `Holding`/`AppliedCorpAction` (Task 2), `PortfolioStore` (Task 3)
- Produces:
  - `parse_action(row: dict) -> AppliedCorpAction | None` — parses one raw NSE actions() row (subject/desc + ex-date); returns None for unrecognised/non-financial rows
  - `apply_actions_to_holding(holding: Holding, actions: list[AppliedCorpAction], today: date) -> int` — applies each unapplied action with `buy_date < ex_date <= today`; mutates `adj_avg_price`, `adj_qty`, `dividends_received`, `applied_actions`; returns count applied; idempotent via `AppliedCorpAction.key`
  - `sync_corp_actions(store: PortfolioStore, today: date, fetch=fetch_corp_actions) -> dict` — full sync for every holding, saves portfolio, returns `{"applied": int, "symbols": [..]}`; never raises

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_corp_actions.py
"""Compass Phase A — corp-action adjustment (BLOCKER-grade invariant).

A 1:1 bonus must NOT look like a −50% crash: adj price halves, adj qty
doubles, P&L unchanged.
"""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import Holding
from core.portfolio.corp_actions import (
    apply_actions_to_holding,
    parse_action,
    sync_corp_actions,
)
from core.portfolio.store import PortfolioStore

TODAY = date(2026, 7, 6)


def _holding(price=1000.0, qty=10) -> Holding:
    return Holding(
        symbol="ACME", sector="automobile", qty=qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=qty, buy_date="2026-01-05",
    )


def test_parse_bonus():
    a = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2026"})
    assert a is not None and a.kind == "bonus" and a.ratio == 2.0


def test_parse_split():
    a = parse_action({
        "subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
        "exDate": "10-Jun-2026",
    })
    assert a is not None and a.kind == "split" and a.ratio == 5.0


def test_parse_dividend():
    a = parse_action({"subject": "Dividend - Rs 8 Per Share", "exDate": "10-Jun-2026"})
    assert a is not None and a.kind == "dividend" and a.dividend_per_share == 8.0


def test_parse_ignores_agm():
    assert parse_action({"subject": "Annual General Meeting", "exDate": "10-Jun-2026"}) is None


def test_bonus_preserves_pnl():
    h = _holding(price=1000.0, qty=10)
    bonus = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2026"})
    applied = apply_actions_to_holding(h, [bonus], TODAY)
    assert applied == 1
    assert h.adj_avg_price == pytest.approx(500.0)
    assert h.adj_qty == 20
    assert h.avg_buy_price == 1000.0 and h.qty == 10      # raw fields untouched
    # Post-bonus close ~500 => P&L ~0%, NOT -50%
    assert abs(h.unrealised_pnl_pct(500.0)) < 1e-9


def test_dividend_credits_cash():
    h = _holding(price=1000.0, qty=10)
    div = parse_action({"subject": "Dividend - Rs 8 Per Share", "exDate": "10-Jun-2026"})
    apply_actions_to_holding(h, [div], TODAY)
    assert h.dividends_received == pytest.approx(80.0)    # 10 shares × ₹8


def test_idempotent_second_apply_is_noop():
    h = _holding()
    bonus = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2026"})
    assert apply_actions_to_holding(h, [bonus], TODAY) == 1
    assert apply_actions_to_holding(h, [bonus], TODAY) == 0
    assert h.adj_qty == 20   # not 40


def test_action_before_buy_date_not_applied():
    h = _holding()   # bought 2026-01-05
    old = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2025"})
    assert apply_actions_to_holding(h, [old], TODAY) == 0


def test_future_ex_date_not_applied():
    h = _holding()
    future = parse_action({"subject": "Bonus 1:1", "exDate": "10-Aug-2026"})
    assert apply_actions_to_holding(h, [future], TODAY) == 0


def test_sync_never_raises_and_saves(tmp_path):
    store = PortfolioStore(user_id="u", base_dir=str(tmp_path))
    store.add_holding(_holding())

    def fake_fetch(symbol):
        return [{"subject": "Bonus 1:1", "exDate": "10-Jun-2026"}]

    result = sync_corp_actions(store, TODAY, fetch=fake_fetch)
    assert result["applied"] == 1
    reloaded = store.load().holdings[0]
    assert reloaded.adj_qty == 20

    def boom(symbol):
        raise RuntimeError("network down")
    assert sync_corp_actions(store, TODAY, fetch=boom)["applied"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_corp_actions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.portfolio.corp_actions'`

- [ ] **Step 3: Write the corp-action sync**

```python
# core/portfolio/corp_actions.py
"""
Compass Phase A — daily corp-action sync (spec §4.1 corp-action invariant).

Adjusts adj_avg_price / adj_qty / dividends_received BEFORE any advisor rule
runs. Without this, a 1:1 bonus looks like a −50% crash and fires a false
EXIT. Raw qty/avg_buy_price are NEVER mutated. Idempotent via applied-action
keys stored on the holding.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from backend.shared.schemas.portfolio import AppliedCorpAction, Holding
from core.portfolio.store import PortfolioStore
from services.data.fetchers.corporate_events import fetch_corp_actions

logger = logging.getLogger(__name__)

_BONUS_RE = re.compile(r"bonus\s+(\d+)\s*:\s*(\d+)", re.I)
_SPLIT_RE = re.compile(
    r"from\s+r[se]\.?\s*(\d+(?:\.\d+)?).{0,40}?to\s+r[se]\.?\s*(\d+(?:\.\d+)?)", re.I
)
_DIV_RE = re.compile(r"dividend[^0-9]*(\d+(?:\.\d+)?)", re.I)

_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")


def _parse_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    for fmt in _NSE_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_action(row: dict) -> AppliedCorpAction | None:
    """Parse one raw NSE actions() row into an AppliedCorpAction.
    Returns None for unrecognised or non-financial rows (AGM/EGM/rights…)."""
    desc = ""
    for key in ("subject", "desc", "purpose"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            desc = v.strip()
            break
    ex_raw = ""
    for key in ("exDate", "ex_date", "date", "exdate"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            ex_raw = v.strip()
            break
    ex_date = _parse_date(ex_raw)
    if not desc or not ex_date:
        return None

    low = desc.lower()
    symbol = str(row.get("symbol", "")).upper()
    key = f"{symbol}|{ex_date}|{desc[:40]}"
    today_iso = date.today().isoformat()

    m = _BONUS_RE.search(low)
    if m:
        new, base = float(m.group(1)), float(m.group(2))
        if base > 0:
            return AppliedCorpAction(
                key=key, ex_date=ex_date, kind="bonus", desc=desc,
                ratio=(new + base) / base, applied_on=today_iso,
            )
    if "split" in low or "sub-division" in low:
        m = _SPLIT_RE.search(low)
        if m:
            old_fv, new_fv = float(m.group(1)), float(m.group(2))
            if new_fv > 0:
                return AppliedCorpAction(
                    key=key, ex_date=ex_date, kind="split", desc=desc,
                    ratio=old_fv / new_fv, applied_on=today_iso,
                )
    if "dividend" in low:
        m = _DIV_RE.search(low)
        if m:
            return AppliedCorpAction(
                key=key, ex_date=ex_date, kind="dividend", desc=desc,
                dividend_per_share=float(m.group(1)), applied_on=today_iso,
            )
    return None


def apply_actions_to_holding(
    holding: Holding, actions: list[AppliedCorpAction | None], today: date
) -> int:
    """Apply every unapplied action with buy_date < ex_date <= today.
    Mutates the holding in place. Returns number applied."""
    applied_keys = {a.key for a in holding.applied_actions}
    count = 0
    for action in actions:
        if action is None or action.key in applied_keys:
            continue
        ex = date.fromisoformat(action.ex_date)
        if ex <= date.fromisoformat(holding.buy_date) or ex > today:
            continue
        if action.kind in ("bonus", "split") and action.ratio > 0:
            holding.adj_avg_price = holding.adj_avg_price / action.ratio
            holding.adj_qty = holding.adj_qty * action.ratio
        elif action.kind == "dividend":
            holding.dividends_received += holding.adj_qty * action.dividend_per_share
        holding.applied_actions.append(action)
        applied_keys.add(action.key)
        count += 1
        logger.info(
            "[corp_actions] %s: applied %s (%s) ex=%s ratio=%.3f dps=%.2f",
            holding.symbol, action.kind, action.desc[:60], action.ex_date,
            action.ratio, action.dividend_per_share,
        )
    return count


def sync_corp_actions(store: PortfolioStore, today: date, fetch=fetch_corp_actions) -> dict:
    """Daily sync for every holding of one user. Non-fatal per symbol —
    pipeline errors are telemetry, never training signal."""
    portfolio = store.load()
    total, touched = 0, []
    for holding in portfolio.holdings:
        try:
            rows = fetch(holding.symbol)
            actions = [parse_action(dict(r, symbol=holding.symbol)) for r in rows]
            n = apply_actions_to_holding(holding, actions, today)
            if n:
                total += n
                touched.append(holding.symbol)
        except Exception as exc:
            logger.warning(
                "[corp_actions] sync failed for %s (non-fatal): %s", holding.symbol, exc
            )
    if total:
        store.save(portfolio)
    return {"applied": total, "symbols": touched}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_corp_actions.py -v`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/corp_actions.py tests/unit/test_portfolio_corp_actions.py
git commit -m "feat(compass): idempotent corp-action sync guarding false EXITs (Phase A Task 6)"
```

---

### Task 7: Auto-promotion into the managed universe

**Files:**
- Create: `core/portfolio/promotion.py`
- Test: `tests/unit/test_portfolio_promotion.py`

**Interfaces:**
- Consumes: `services.api.log_buffer.load_managed_tickers() / save_managed_tickers(list[dict])`; `backend.shared.data.fetchers.symbol_resolver.resolve_company_name(ticker)`; `settings.PORTFOLIO_MAX_MANAGED_TICKERS`, `settings.PORTFOLIO_WEEKLY_REVIEW_WEEKDAY`
- Produces:
  - `SUPPORTED_SECTORS: frozenset[str]` = the 4 sector_router sectors
  - `promote_symbol(symbol: str, sector: str, origin: str) -> dict` — `origin ∈ {"held","watchlist"}`; returns `{"status": "promoted"|"already_managed"|"unsupported_sector"|"cap_full", ...}`. Managed entries gain `origin` and `cadence` fields (`held→daily`, `watchlist→weekly`). Entries without `origin` (the pre-existing 16) are treated as manual and NEVER evicted. Cap eviction order: `watchlist`-origin entries first (oldest `promoted_at` first); if nothing evictable → `cap_full` (promotion refused, warning logged).
  - `demote_symbol(symbol: str) -> bool` — disables (`enabled: False`) a managed entry ONLY if it has portfolio origin (`held`/`watchlist`) — never touches manual entries
  - `due_for_review(entry: dict, review_date: date) -> bool` — daily-cadence always True; weekly-cadence only on `PORTFOLIO_WEEKLY_REVIEW_WEEKDAY`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_promotion.py
"""Compass Phase A — auto-promotion: 4 supported sectors, cap, cadence."""
from datetime import date

import pytest

import core.portfolio.promotion as promo


@pytest.fixture
def managed(monkeypatch):
    """In-memory managed_tickers list, patched over log_buffer load/save."""
    state = {"tickers": [
        {"sym": "MARUTI", "name": "Maruti Suzuki India Ltd", "sector": "automobile", "enabled": True},
    ]}
    monkeypatch.setattr(promo, "load_managed_tickers", lambda: state["tickers"])

    def fake_save(tickers):
        state["tickers"] = tickers
    monkeypatch.setattr(promo, "save_managed_tickers", fake_save)
    monkeypatch.setattr(promo, "resolve_company_name", lambda t: f"{t} Ltd")
    return state


def test_promote_new_held_symbol(managed):
    result = promo.promote_symbol("TCS", "it_sector", origin="held")
    assert result["status"] == "promoted"
    entry = next(t for t in managed["tickers"] if t["sym"] == "TCS")
    assert entry["origin"] == "held" and entry["cadence"] == "daily"
    assert entry["enabled"] is True


def test_promote_watchlist_gets_weekly_cadence(managed):
    promo.promote_symbol("INFY", "it_sector", origin="watchlist")
    entry = next(t for t in managed["tickers"] if t["sym"] == "INFY")
    assert entry["cadence"] == "weekly"


def test_promote_unsupported_sector_rejected(managed):
    result = promo.promote_symbol("SUNPHARMA", "pharma", origin="held")
    assert result["status"] == "unsupported_sector"
    assert "not yet supported" in result["detail"]
    assert all(t["sym"] != "SUNPHARMA" for t in managed["tickers"])


def test_promote_existing_symbol_noop(managed):
    result = promo.promote_symbol("MARUTI", "automobile", origin="held")
    assert result["status"] == "already_managed"


def test_cap_evicts_watchlist_first(managed, monkeypatch):
    monkeypatch.setattr(promo.settings, "PORTFOLIO_MAX_MANAGED_TICKERS", 2)
    managed["tickers"].append({
        "sym": "WIPRO", "name": "Wipro Ltd", "sector": "it_sector", "enabled": True,
        "origin": "watchlist", "cadence": "weekly", "promoted_at": "2026-06-01",
    })
    result = promo.promote_symbol("TCS", "it_sector", origin="held")
    assert result["status"] == "promoted"
    syms = [t["sym"] for t in managed["tickers"] if t.get("enabled", True)]
    assert "WIPRO" not in syms          # watchlist-origin evicted
    assert "MARUTI" in syms             # manual entry never evicted
    assert "TCS" in syms


def test_cap_full_when_nothing_evictable(managed, monkeypatch):
    monkeypatch.setattr(promo.settings, "PORTFOLIO_MAX_MANAGED_TICKERS", 1)
    result = promo.promote_symbol("TCS", "it_sector", origin="watchlist")
    assert result["status"] == "cap_full"
    assert all(t["sym"] != "TCS" for t in managed["tickers"])


def test_demote_only_touches_portfolio_origin(managed):
    promo.promote_symbol("TCS", "it_sector", origin="held")
    assert promo.demote_symbol("TCS") is True
    entry = next(t for t in managed["tickers"] if t["sym"] == "TCS")
    assert entry["enabled"] is False
    assert promo.demote_symbol("MARUTI") is False    # manual entry untouched
    assert next(t for t in managed["tickers"] if t["sym"] == "MARUTI")["enabled"] is True


def test_due_for_review_cadence():
    daily = {"sym": "TCS", "cadence": "daily"}
    weekly = {"sym": "INFY", "cadence": "weekly"}
    legacy = {"sym": "MARUTI"}                        # no cadence field = daily
    friday, monday = date(2026, 7, 10), date(2026, 7, 6)
    assert promo.due_for_review(daily, monday) is True
    assert promo.due_for_review(legacy, monday) is True
    assert promo.due_for_review(weekly, monday) is False
    assert promo.due_for_review(weekly, friday) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_promotion.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.portfolio.promotion'`

- [ ] **Step 3: Write the promotion module**

```python
# core/portfolio/promotion.py
"""
Compass Phase A — auto-promotion into the managed universe (spec §4.3).

Any held or watchlisted symbol is promoted into managed_tickers.json so the
existing crons give it envelopes, daily reviews and dossiers — identical
treatment to the original tickers.

Phase A reality check: sector_router supports exactly 4 sectors and silently
falls back to the automobile orchestrator for anything else — an auto-promoted
pharma stock would be analyzed as a car company. Promotion therefore REJECTS
unsupported sectors until the generic sector graph ships (Phase B).

Cap governance: portfolio.max_managed_tickers (default 40) guards LLM spend.
Priority held > watchlist; pre-existing manual entries are never evicted.
Cadence tiers govern review cost: held=daily, watchlist=weekly (spec §4.3).
"""
from __future__ import annotations

import logging
from datetime import date

from core.config import settings
from services.api.log_buffer import load_managed_tickers, save_managed_tickers
from backend.shared.data.fetchers.symbol_resolver import resolve_company_name

logger = logging.getLogger(__name__)

# Must mirror core/intelligence/rl/workflows/sector_router.py _ORCHESTRATORS.
SUPPORTED_SECTORS: frozenset[str] = frozenset(
    {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
)

_ORIGIN_CADENCE = {"held": "daily", "watchlist": "weekly"}
# Eviction preference under cap pressure (lower value evicted first).
_EVICTION_ORDER = {"watchlist": 0, "held": 1}


def promote_symbol(symbol: str, sector: str, origin: str) -> dict:
    symbol = symbol.strip().upper()
    sector = sector.strip().lower()
    if origin not in _ORIGIN_CADENCE:
        raise ValueError(f"origin must be one of {sorted(_ORIGIN_CADENCE)}: {origin!r}")

    if sector not in SUPPORTED_SECTORS:
        detail = (
            f"Sector '{sector}' not yet supported — Phase A promotion covers "
            f"{sorted(SUPPORTED_SECTORS)} only (generic sector graph is Phase B)."
        )
        logger.info("[promotion] %s rejected: %s", symbol, detail)
        return {"status": "unsupported_sector", "symbol": symbol, "detail": detail}

    tickers = list(load_managed_tickers())
    existing = next((t for t in tickers if t.get("sym") == symbol), None)
    if existing:
        changed = False
        if not existing.get("enabled", True):
            existing["enabled"] = True
            changed = True
        # A held position outranks a watchlist promotion of the same symbol.
        if existing.get("origin") in _ORIGIN_CADENCE and origin == "held" \
                and existing.get("origin") != "held":
            existing["origin"], existing["cadence"] = "held", "daily"
            changed = True
        if changed:
            save_managed_tickers(tickers)
        return {"status": "already_managed", "symbol": symbol}

    cap = settings.PORTFOLIO_MAX_MANAGED_TICKERS
    active = [t for t in tickers if t.get("enabled", True)]
    if len(active) >= cap:
        # Evict the lowest-priority portfolio-origin entry. Manual entries
        # (no origin field — the original universe) are never evicted.
        candidates = [
            t for t in active
            if t.get("origin") in _EVICTION_ORDER
            and _EVICTION_ORDER[t["origin"]] < _EVICTION_ORDER.get(origin, 1)
        ]
        candidates.sort(key=lambda t: (
            _EVICTION_ORDER[t["origin"]], t.get("promoted_at", "")
        ))
        if not candidates:
            logger.warning(
                "[promotion] cap %d reached and nothing evictable — %s NOT promoted",
                cap, symbol,
            )
            return {"status": "cap_full", "symbol": symbol,
                    "detail": f"managed-ticker cap {cap} reached"}
        evicted = candidates[0]
        evicted["enabled"] = False
        logger.info("[promotion] cap %d: evicted %s (origin=%s) for %s",
                    cap, evicted["sym"], evicted["origin"], symbol)

    try:
        name = resolve_company_name(symbol) or symbol
    except Exception:
        name = symbol
    tickers.append({
        "sym": symbol,
        "name": name,
        "sector": sector,
        "enabled": True,
        "origin": origin,
        "cadence": _ORIGIN_CADENCE[origin],
        "promoted_at": date.today().isoformat(),
    })
    save_managed_tickers(tickers)
    logger.info("[promotion] %s promoted (sector=%s origin=%s cadence=%s)",
                symbol, sector, origin, _ORIGIN_CADENCE[origin])
    return {"status": "promoted", "symbol": symbol, "cadence": _ORIGIN_CADENCE[origin]}


def demote_symbol(symbol: str) -> bool:
    """Disable a portfolio-origin managed entry (holding/watchlist removed).
    Manual entries — the original universe — are never touched."""
    symbol = symbol.strip().upper()
    tickers = list(load_managed_tickers())
    entry = next((t for t in tickers if t.get("sym") == symbol), None)
    if not entry or entry.get("origin") not in _ORIGIN_CADENCE:
        return False
    entry["enabled"] = False
    save_managed_tickers(tickers)
    logger.info("[promotion] %s demoted (enabled=False)", symbol)
    return True


def due_for_review(entry: dict, review_date: date) -> bool:
    """Cadence gate for the daily review job: held names review daily,
    watchlist names weekly (config portfolio.weekly_review_weekday)."""
    if entry.get("cadence", "daily") != "weekly":
        return True
    return review_date.weekday() == settings.PORTFOLIO_WEEKLY_REVIEW_WEEKDAY
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_promotion.py -v`
Expected: 9 PASS

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/promotion.py tests/unit/test_portfolio_promotion.py
git commit -m "feat(compass): auto-promotion with 4-sector gate, cap eviction, cadence tiers (Phase A Task 7)"
```

---

### Task 8: Advisor engine — signals, stops, verdict rules, ledger append

**Files:**
- Create: `core/portfolio/advisor.py`
- Test: `tests/unit/test_portfolio_advisor.py`

**Interfaces:**
- Consumes: `PredictionStore` (envelope/feedback), `compute_atr_pct` pattern (own 20d ATR here), Task 2 schemas, Task 5 `next_results_event`, settings from Task 1
- Produces:
  - `AdvisorSignals` (Pydantic model, defined here — engine-internal, not a shared schema): `symbol, sector, close, atr_stop_pct, unrealised_pnl_pct, holding_age_days, regime_label="NORMAL", thesis_intact=None (bool|None), reforecast_reason="", envelope_direction="FLAT", confidence_trend=0.0, reversion_prior=0.0, direction_accuracy_7d=None (float|None), position_weight_pct=0.0, earnings_in_days=None (int|None), confidence=0.5`
  - `atr_pct(ohlcv_df, period: int) -> float` — ATR as % of last close (0.0 on failure)
  - `compute_stop_pct(atr_pct_value: float, cap_bucket: str, risk_profile: str) -> float` — `clamp(ADVISOR_STOP_ATR_MULT × atr, floor, cap)` per bucket; `conservative` profile tightens one bucket notch (small→mid, mid→large, large stays)
  - `resolve_cap_bucket(market_cap_inr: float | None) -> str` — thresholds from `ADVISOR_LARGE_CAP_FLOOR_CR`/`ADVISOR_MID_CAP_FLOOR_CR` (₹cr → ×1e7 INR); None → `"mid"`
  - `build_signals(holding: Holding, portfolio: Portfolio, review_date: date, store: PredictionStore, calendar: dict, close: float, ohlcv_df=None, market_cap_inr: float | None = None) -> AdvisorSignals`
  - `decide(signals: AdvisorSignals, holding: Holding, risk_profile: str) -> AdviceRecord` — deterministic verdict with precedence **EXIT > TRIM > ADD > HOLD**, LTCG softening (never on EXIT), earnings-gap note
- Trigger codes emitted in `AdviceRecord.triggers`: `stop_breach`, `thesis_break`, `shock_reforecast`, `crisis_regime_bearish`, `trim_profit_confidence_decline`, `trim_profit_reversion_elevated`, `add_bullish_healthy`
- Note codes in `AdviceRecord.notes`: `WAIT_FOR_LTCG`, `EARNINGS_GAP_PROTECTION`, `SECTOR_CONCENTRATION_HIGH`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_advisor.py
"""Compass Phase A — deterministic advisor: EXIT > TRIM > ADD > HOLD."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import Holding
from core.portfolio.advisor import (
    AdvisorSignals,
    compute_stop_pct,
    decide,
    resolve_cap_bucket,
)

REVIEW_DATE = date(2026, 7, 6)


def _holding(buy_date="2026-01-05") -> Holding:
    return Holding(
        symbol="MARUTI", sector="automobile", qty=10, avg_buy_price=12000.0,
        adj_avg_price=12000.0, adj_qty=10, buy_date=buy_date,
    )


def _signals(**kw) -> AdvisorSignals:
    base = dict(
        symbol="MARUTI", sector="automobile", close=13000.0,
        atr_stop_pct=10.0, unrealised_pnl_pct=8.0, holding_age_days=180,
    )
    base.update(kw)
    return AdvisorSignals(**base)


# ── Stop scaling ────────────────────────────────────────────────────────────

def test_stop_clamped_to_bucket():
    # 3 × 5% ATR = 15% > large-cap cap 12% -> clamped
    assert compute_stop_pct(5.0, "large", "balanced") == 12.0
    # 3 × 1% = 3% < large floor 8% -> floored
    assert compute_stop_pct(1.0, "large", "balanced") == 8.0
    # mid bucket passes through inside band
    assert compute_stop_pct(5.0, "mid", "balanced") == 15.0


def test_conservative_tightens_one_notch():
    # small bucket (15-22) tightened to mid (12-18): 3×7%=21 -> capped 18
    assert compute_stop_pct(7.0, "small", "conservative") == 18.0


def test_cap_bucket_resolution():
    assert resolve_cap_bucket(70000 * 1e7) == "large"     # ₹70,000 cr
    assert resolve_cap_bucket(30000 * 1e7) == "mid"
    assert resolve_cap_bucket(5000 * 1e7) == "small"
    assert resolve_cap_bucket(None) == "mid"


# ── EXIT rules (highest precedence) ────────────────────────────────────────

def test_exit_on_stop_breach():
    rec = decide(_signals(unrealised_pnl_pct=-12.0, atr_stop_pct=10.0), _holding(), "balanced")
    assert rec.verdict == "EXIT"
    assert "stop_breach" in rec.triggers


def test_exit_on_thesis_break_against_position():
    rec = decide(
        _signals(thesis_intact=False, envelope_direction="DOWN"),
        _holding(), "balanced",
    )
    assert rec.verdict == "EXIT"
    assert "thesis_break" in rec.triggers


def test_exit_on_crisis_regime_bearish():
    rec = decide(
        _signals(regime_label="MACRO_CRISIS", envelope_direction="DOWN"),
        _holding(), "balanced",
    )
    assert rec.verdict == "EXIT"
    assert "crisis_regime_bearish" in rec.triggers


def test_exit_outranks_trim_even_with_ltcg_window():
    # 11-month-old profitable position breaching stop: EXIT, never WAIT_FOR_LTCG
    h = _holding(buy_date="2025-08-06")
    rec = decide(
        _signals(unrealised_pnl_pct=-15.0, atr_stop_pct=10.0, holding_age_days=334),
        h, "balanced",
    )
    assert rec.verdict == "EXIT"
    assert "WAIT_FOR_LTCG" not in rec.notes


# ── TRIM rules ──────────────────────────────────────────────────────────────

def test_trim_on_profit_with_confidence_decline():
    rec = decide(
        _signals(unrealised_pnl_pct=30.0, confidence_trend=-0.10),
        _holding(), "balanced",
    )
    assert rec.verdict == "TRIM"
    assert "trim_profit_confidence_decline" in rec.triggers


def test_trim_on_profit_with_elevated_reversion():
    rec = decide(
        _signals(unrealised_pnl_pct=30.0, reversion_prior=0.25),
        _holding(), "balanced",
    )
    assert rec.verdict == "TRIM"


def test_no_trim_below_profit_threshold():
    rec = decide(
        _signals(unrealised_pnl_pct=10.0, confidence_trend=-0.10),
        _holding(), "balanced",
    )
    assert rec.verdict == "HOLD"


def test_trim_softened_to_wait_for_ltcg():
    # age 320 days (~10.7 months), thesis intact -> HOLD + WAIT_FOR_LTCG note
    rec = decide(
        _signals(unrealised_pnl_pct=30.0, confidence_trend=-0.10,
                 holding_age_days=320, thesis_intact=True),
        _holding(buy_date="2025-08-20"), "balanced",
    )
    assert rec.verdict == "HOLD"
    assert "WAIT_FOR_LTCG" in rec.notes


def test_trim_not_softened_past_12_months():
    rec = decide(
        _signals(unrealised_pnl_pct=30.0, confidence_trend=-0.10,
                 holding_age_days=400, thesis_intact=True),
        _holding(buy_date="2025-06-01"), "balanced",
    )
    assert rec.verdict == "TRIM"


# ── ADD rules ───────────────────────────────────────────────────────────────

def test_add_when_bullish_and_healthy():
    rec = decide(
        _signals(envelope_direction="UP", regime_label="NORMAL",
                 direction_accuracy_7d=0.7, position_weight_pct=5.0),
        _holding(), "balanced",
    )
    assert rec.verdict == "ADD"
    assert "add_bullish_healthy" in rec.triggers


def test_no_add_when_position_at_max_weight():
    rec = decide(
        _signals(envelope_direction="UP", direction_accuracy_7d=0.7,
                 position_weight_pct=12.0),
        _holding(), "balanced",
    )
    assert rec.verdict == "HOLD"


def test_no_add_in_risk_off_regime():
    rec = decide(
        _signals(envelope_direction="UP", regime_label="RISK_OFF",
                 direction_accuracy_7d=0.7, position_weight_pct=5.0),
        _holding(), "balanced",
    )
    assert rec.verdict == "HOLD"


# ── Annotations ─────────────────────────────────────────────────────────────

def test_earnings_gap_note_on_profitable_position():
    rec = decide(
        _signals(unrealised_pnl_pct=8.0, earnings_in_days=2),
        _holding(), "balanced",
    )
    assert "EARNINGS_GAP_PROTECTION" in rec.notes


def test_no_earnings_note_when_far():
    rec = decide(
        _signals(unrealised_pnl_pct=8.0, earnings_in_days=10),
        _holding(), "balanced",
    )
    assert "EARNINGS_GAP_PROTECTION" not in rec.notes


def test_advice_record_has_hash_and_date():
    rec = decide(_signals(), _holding(), "balanced")
    assert rec.rationale_hash != ""
    assert rec.verdict == "HOLD"
    assert rec.symbol == "MARUTI"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_advisor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.portfolio.advisor'`

- [ ] **Step 3: Write the advisor engine**

```python
# core/portfolio/advisor.py
"""
Compass Phase A — Position Advisor v1 (spec §5).

Pure-Python decision engine over signals the RL foundation already computes.
The LLM only narrates (narrator.py) — it never decides.

Verdict precedence (explicit, non-negotiable): EXIT > TRIM > ADD > HOLD.
Tax-deferral may soften a TRIM into WAIT_FOR_LTCG; it must NEVER suppress or
delay an EXIT — capital protection outranks tax optimisation, always.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta

from pydantic import BaseModel

from core.config import settings
from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.intelligence.rl.stores.prediction_store import PredictionStore
from services.data.fetchers.corporate_events import next_results_event

logger = logging.getLogger(__name__)

_BUCKET_TIGHTEN = {"small": "mid", "mid": "large", "large": "large"}


class AdvisorSignals(BaseModel):
    """Deterministic inputs for one holding on one review date (spec §5.1)."""
    symbol: str
    sector: str
    close: float
    atr_stop_pct: float                    # volatility-scaled stop, already clamped
    unrealised_pnl_pct: float              # vs adj_avg_price, dividend-inclusive
    holding_age_days: int
    regime_label: str = "NORMAL"
    thesis_intact: bool | None = None      # latest ThesisReview outcome, None = never reviewed
    reforecast_reason: str = ""            # latest reforecast event reason this cycle
    envelope_direction: str = "FLAT"       # UP | DOWN | FLAT remaining-forecast drift
    confidence_trend: float = 0.0          # last remaining conf − first remaining conf
    reversion_prior: float = 0.0
    direction_accuracy_7d: float | None = None
    position_weight_pct: float = 0.0
    earnings_in_days: int | None = None    # trading-day distance to next results event
    confidence: float = 0.5                # mean remaining envelope confidence


# ---------------------------------------------------------------------------
# Stops (spec §5.2 — volatility-scaled, never a flat %)
# ---------------------------------------------------------------------------

def atr_pct(ohlcv_df, period: int) -> float:
    """ATR(period) as % of last close. 0.0 on failure (callers fall back to
    the bucket floor via compute_stop_pct's clamp)."""
    try:
        import pandas as pd
        if ohlcv_df is None or len(ohlcv_df) < period + 1:
            return 0.0
        high, low, close = ohlcv_df["High"], ohlcv_df["Low"], ohlcv_df["Close"]
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
        ).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        last = float(close.iloc[-1])
        return round(float(atr) / last * 100, 4) if last > 0 else 0.0
    except Exception as exc:
        logger.debug("[advisor] ATR computation failed: %s", exc)
        return 0.0


def resolve_cap_bucket(market_cap_inr: float | None) -> str:
    """large/mid/small from free-float mcap in INR; unknown -> mid."""
    if market_cap_inr is None or market_cap_inr <= 0:
        return "mid"
    crores = market_cap_inr / 1e7
    if crores >= settings.ADVISOR_LARGE_CAP_FLOOR_CR:
        return "large"
    if crores >= settings.ADVISOR_MID_CAP_FLOOR_CR:
        return "mid"
    return "small"


def compute_stop_pct(atr_pct_value: float, cap_bucket: str, risk_profile: str) -> float:
    """clamp(stop_atr_mult × ATR%, bucket floor, bucket cap); conservative
    profiles tighten one bucket notch."""
    bucket = cap_bucket if cap_bucket in settings.ADVISOR_STOP_BUCKETS else "mid"
    if risk_profile == "conservative":
        bucket = _BUCKET_TIGHTEN[bucket]
    floor, cap = settings.ADVISOR_STOP_BUCKETS[bucket]
    raw = settings.ADVISOR_STOP_ATR_MULT * atr_pct_value
    return round(min(max(raw, floor), cap), 2)


# ---------------------------------------------------------------------------
# Signal assembly from existing RL artifacts
# ---------------------------------------------------------------------------

def build_signals(
    holding: Holding,
    portfolio: Portfolio,
    review_date: date,
    store: PredictionStore,
    calendar: dict,
    close: float,
    ohlcv_df=None,
    market_cap_inr: float | None = None,
) -> AdvisorSignals:
    """Assemble the advisor's inputs from PredictionStore artifacts + the
    events calendar. Every sub-read is non-fatal — missing artifacts leave
    conservative defaults in place."""
    sig = AdvisorSignals(
        symbol=holding.symbol,
        sector=holding.sector,
        close=close,
        atr_stop_pct=compute_stop_pct(
            atr_pct(ohlcv_df, settings.ADVISOR_ATR_PERIOD),
            resolve_cap_bucket(market_cap_inr),
            portfolio.risk_profile,
        ),
        unrealised_pnl_pct=holding.unrealised_pnl_pct(close),
        holding_age_days=holding.age_days(review_date),
    )
    # Position weight vs portfolio market value
    try:
        total = sum(h.adj_qty * h.adj_avg_price for h in portfolio.holdings)
        if total > 0:
            sig.position_weight_pct = round(
                holding.adj_qty * holding.adj_avg_price / total * 100, 2
            )
    except Exception:
        pass
    # Envelope state
    try:
        env = store.load_envelope(store.cycle_id_for(review_date))
        if env and env.daily_forecasts:
            remaining = [f for f in env.daily_forecasts if f.date >= review_date.isoformat()]
            if remaining:
                drift_pct = (remaining[-1].predicted_close - close) / close * 100
                band = settings.ADVISOR_ENVELOPE_FLAT_BAND_PCT
                sig.envelope_direction = (
                    "UP" if drift_pct > band else "DOWN" if drift_pct < -band else "FLAT"
                )
                sig.confidence_trend = round(remaining[-1].confidence - remaining[0].confidence, 4)
                sig.confidence = round(
                    sum(f.confidence for f in remaining) / len(remaining), 4
                )
            sig.reversion_prior = env.conviction_streak.reversion_prior
            if env.reforecast_history:
                sig.reforecast_reason = env.reforecast_history[-1].reason
    except Exception as exc:
        logger.warning("[advisor] envelope read failed for %s (non-fatal): %s",
                       holding.symbol, exc)
    # Feedback log: regime, thesis, direction accuracy
    try:
        log = store.load_feedback_log(store.cycle_id_for(review_date))
        entries = log.entries if log else []
        if entries:
            sig.regime_label = entries[-1].regime_label
            last7 = entries[-7:]
            sig.direction_accuracy_7d = round(
                sum(1 for e in last7 if e.direction_correct) / len(last7), 4
            )
            for e in reversed(entries):
                if e.thesis_review is not None:
                    sig.thesis_intact = e.thesis_review.thesis_intact
                    break
    except Exception as exc:
        logger.warning("[advisor] feedback read failed for %s (non-fatal): %s",
                       holding.symbol, exc)
    # Earnings distance (trading days)
    try:
        ev = next_results_event(holding.symbol, review_date, calendar)
        if ev is not None:
            from core.intelligence.rl.nse_calendar import is_trading_day
            d, n = review_date, 0
            target = date.fromisoformat(ev.date)
            while d < target:
                d += timedelta(days=1)
                if is_trading_day(d):
                    n += 1
            sig.earnings_in_days = n
    except Exception as exc:
        logger.warning("[advisor] earnings-distance failed for %s (non-fatal): %s",
                       holding.symbol, exc)
    return sig


# ---------------------------------------------------------------------------
# Verdict engine
# ---------------------------------------------------------------------------

def decide(signals: AdvisorSignals, holding: Holding, risk_profile: str) -> AdviceRecord:
    triggers: list[str] = []
    notes: list[str] = []

    # -- EXIT (spec §5.2, highest precedence) ------------------------------
    if signals.unrealised_pnl_pct <= -signals.atr_stop_pct:
        triggers.append("stop_breach")
    if signals.thesis_intact is False and signals.envelope_direction == "DOWN":
        triggers.append("thesis_break")
    if signals.reforecast_reason in ("external_shock", "thesis_break", "preopen_shock") \
            and signals.envelope_direction == "DOWN":
        triggers.append("shock_reforecast")
    if signals.regime_label == "MACRO_CRISIS" and signals.envelope_direction == "DOWN":
        triggers.append("crisis_regime_bearish")

    exit_fired = bool(triggers)

    # -- TRIM ---------------------------------------------------------------
    trim_fired = False
    if not exit_fired and signals.unrealised_pnl_pct >= settings.ADVISOR_TRIM_PROFIT_PCT:
        if signals.confidence_trend <= -settings.ADVISOR_CONFIDENCE_DECLINE_THRESHOLD:
            triggers.append("trim_profit_confidence_decline")
            trim_fired = True
        elif signals.reversion_prior >= settings.ADVISOR_REVERSION_PRIOR_ELEVATED:
            triggers.append("trim_profit_reversion_elevated")
            trim_fired = True

    # -- ADD ----------------------------------------------------------------
    add_fired = False
    if not exit_fired and not trim_fired:
        if (
            signals.envelope_direction == "UP"
            and signals.regime_label not in ("MACRO_CRISIS", "RISK_OFF")
            and signals.position_weight_pct < settings.ADVISOR_MAX_POSITION_PCT
            and (signals.direction_accuracy_7d or 0.0) >= settings.ADVISOR_ADD_MIN_DIRECTION_ACCURACY
        ):
            triggers.append("add_bullish_healthy")
            add_fired = True

    # -- Precedence: EXIT > TRIM > ADD > HOLD -------------------------------
    if exit_fired:
        verdict = "EXIT"
    elif trim_fired:
        verdict = "TRIM"
    elif add_fired:
        verdict = "ADD"
    else:
        verdict = "HOLD"

    # -- LTCG softening: TRIM only, NEVER EXIT (spec §5.2) ------------------
    if verdict == "TRIM" and signals.thesis_intact is not False:
        months = signals.holding_age_days / 30.44
        if settings.ADVISOR_LTCG_WAIT_MIN_MONTHS <= months < 12:
            verdict = "HOLD"
            notes.append("WAIT_FOR_LTCG")

    # -- Annotations ---------------------------------------------------------
    if (
        signals.unrealised_pnl_pct > 0
        and signals.earnings_in_days is not None
        and signals.earnings_in_days <= settings.ADVISOR_EARNINGS_GAP_DAYS
    ):
        notes.append("EARNINGS_GAP_PROTECTION")
    if signals.position_weight_pct >= settings.ADVISOR_SECTOR_CONCENTRATION_WARN_PCT:
        notes.append("SECTOR_CONCENTRATION_HIGH")

    rationale = "|".join(sorted(triggers) + sorted(notes)) or "default_hold"
    return AdviceRecord(
        date=date.today().isoformat(),
        user_id="",                      # pipeline fills the user id
        symbol=signals.symbol,
        verdict=verdict,
        close=signals.close,
        unrealised_pnl_pct=round(signals.unrealised_pnl_pct, 2),
        stop_pct=signals.atr_stop_pct,
        triggers=triggers,
        notes=notes,
        confidence=signals.confidence,
        rationale_hash=hashlib.sha256(rationale.encode()).hexdigest()[:16],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_advisor.py -v`
Expected: 19 PASS

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/advisor.py tests/unit/test_portfolio_advisor.py
git commit -m "feat(compass): deterministic advisor engine — EXIT>TRIM>ADD>HOLD, ATR stops, LTCG-aware (Phase A Task 8)"
```

---

### Task 9: Narrator — BULK-tier narration with deterministic fallback

**Files:**
- Create: `core/portfolio/narrator.py`
- Test: `tests/unit/test_portfolio_narrator.py`

**Interfaces:**
- Consumes: `get_llm_client`, `JSON_MODE_EXTRA_BODY`, `salvage_truncated_json`, `record_llm_call` from `services/clients/llm_client.py`; `settings.LLM_MODEL_BULK`, `settings.ADVISOR_NARRATE`; `AdviceRecord`, `AdvisorSignals`
- Produces: `narrate(rec: AdviceRecord, signals: AdvisorSignals) -> str` — 2-3 sentence research-tone narrative; on any LLM failure (or `ADVISOR_NARRATE=False`) returns `fallback_narrative(rec)` built from trigger codes; never raises

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_narrator.py
"""Compass Phase A — narration is presentation-only, never blocks advice."""
import json

from backend.shared.schemas.portfolio import AdviceRecord
from core.portfolio.advisor import AdvisorSignals
import core.portfolio.narrator as narrator


def _rec(verdict="TRIM", triggers=None) -> AdviceRecord:
    return AdviceRecord(
        date="2026-07-06", user_id="primary", symbol="MARUTI", verdict=verdict,
        close=13000.0, unrealised_pnl_pct=28.0, stop_pct=10.0,
        triggers=triggers or ["trim_profit_confidence_decline"],
    )


def _signals() -> AdvisorSignals:
    return AdvisorSignals(
        symbol="MARUTI", sector="automobile", close=13000.0,
        atr_stop_pct=10.0, unrealised_pnl_pct=28.0, holding_age_days=180,
    )


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeClient:
    def __init__(self, content):
        usage = type("U", (), {"prompt_tokens": 100, "completion_tokens": 50})()
        resp = type("R", (), {"choices": [_FakeChoice(content)], "usage": usage})()
        create = lambda self_, **kw: resp
        completions = type("C", (), {"create": create})()
        self.chat = type("Ch", (), {"completions": completions})()


def test_narrate_happy_path(monkeypatch):
    payload = json.dumps({"narrative": "Profit is extended while envelope confidence is fading; consider booking part of the gain."})
    monkeypatch.setattr(narrator, "get_llm_client", lambda: _FakeClient(payload))
    text = narrator.narrate(_rec(), _signals())
    assert "confidence" in text


def test_narrate_falls_back_on_llm_error(monkeypatch):
    def boom():
        raise RuntimeError("openrouter down")
    monkeypatch.setattr(narrator, "get_llm_client", boom)
    text = narrator.narrate(_rec(), _signals())
    assert text == narrator.fallback_narrative(_rec())
    assert "TRIM" in text


def test_narrate_disabled_uses_fallback(monkeypatch):
    monkeypatch.setattr(narrator.settings, "ADVISOR_NARRATE", False)
    text = narrator.narrate(_rec(), _signals())
    assert text == narrator.fallback_narrative(_rec())


def test_fallback_never_says_advice():
    for verdict in ("HOLD", "ADD", "TRIM", "EXIT"):
        text = narrator.fallback_narrative(_rec(verdict=verdict))
        assert "advice" not in text.lower()   # research/analysis posture (spec §2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_narrator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.portfolio.narrator'`

- [ ] **Step 3: Write the narrator**

```python
# core/portfolio/narrator.py
"""
Compass Phase A — BULK-tier narration of advisor verdicts (spec §5).

The engine decides; the LLM only phrases. Output is labelled research/
analysis, never "advice" (spec §2). Any failure falls back to deterministic
text from the trigger codes — narration must never block the pipeline.
"""
from __future__ import annotations

import json
import logging
import time

from core.config import settings
from backend.shared.schemas.portfolio import AdviceRecord
from core.portfolio.advisor import AdvisorSignals
from services.clients.llm_client import (
    JSON_MODE_EXTRA_BODY,
    get_llm_client,
    record_llm_call,
    salvage_truncated_json,
)

logger = logging.getLogger(__name__)

_TRIGGER_TEXT = {
    "stop_breach": "the position has breached its volatility-scaled stop",
    "thesis_break": "the original thesis is assessed as broken while the forecast points down",
    "shock_reforecast": "a shock re-forecast moved against the position",
    "crisis_regime_bearish": "the regime is MACRO_CRISIS with a bearish envelope",
    "trim_profit_confidence_decline": "profit is extended while envelope confidence is declining",
    "trim_profit_reversion_elevated": "profit is extended while the reversion prior is elevated",
    "add_bullish_healthy": "the envelope is bullish, the regime supportive and recent accuracy healthy",
}

_NOTE_TEXT = {
    "WAIT_FOR_LTCG": "the position crosses the 12-month LTCG boundary soon, so the trim signal is noted rather than acted on",
    "EARNINGS_GAP_PROTECTION": "results are due within days — a profit-protection review is flagged",
    "SECTOR_CONCENTRATION_HIGH": "position weight is above the concentration comfort band",
}

_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-3 sentence research note (NOT financial advice — never use the word
"advice") explaining this deterministic verdict to the portfolio owner.

Verdict: {verdict} on {symbol} at close ₹{close}
Unrealised P&L: {pnl:+.1f}% | Stop level: {stop:.1f}% | Regime: {regime}
Rule triggers: {triggers}
Annotations: {notes}

Respond with JSON: {{"narrative": "<2-3 sentences>"}}"""


def fallback_narrative(rec: AdviceRecord) -> str:
    reasons = [_TRIGGER_TEXT.get(t, t) for t in rec.triggers]
    notes = [_NOTE_TEXT.get(n, n) for n in rec.notes]
    parts = [f"{rec.verdict} — " + ("; ".join(reasons) if reasons else "no rule fired, thesis intact")]
    if notes:
        parts.append("Also: " + "; ".join(notes) + ".")
    return " ".join(parts)


def narrate(rec: AdviceRecord, signals: AdvisorSignals) -> str:
    if not settings.ADVISOR_NARRATE:
        return fallback_narrative(rec)
    started = time.time()
    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL_BULK,
            messages=[{"role": "user", "content": _PROMPT.format(
                verdict=rec.verdict, symbol=rec.symbol, close=rec.close,
                pnl=rec.unrealised_pnl_pct, stop=rec.stop_pct,
                regime=signals.regime_label,
                triggers=", ".join(rec.triggers) or "none",
                notes=", ".join(rec.notes) or "none",
            )}],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=300,
            response_format={"type": "json_object"},
            extra_body=JSON_MODE_EXTRA_BODY,
        )
        raw = resp.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            data = salvage_truncated_json(raw)
        usage = getattr(resp, "usage", None)
        record_llm_call(
            "portfolio_narrator", settings.LLM_MODEL_BULK,
            getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0),
            int((time.time() - started) * 1000), True,
        )
        narrative = str(data.get("narrative", "")).strip()
        return narrative or fallback_narrative(rec)
    except Exception as exc:
        logger.warning("[narrator] narration failed for %s (non-fatal): %s", rec.symbol, exc)
        try:
            record_llm_call(
                "portfolio_narrator", settings.LLM_MODEL_BULK, 0, 0,
                int((time.time() - started) * 1000), False,
            )
        except Exception:
            pass
        return fallback_narrative(rec)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_narrator.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/narrator.py tests/unit/test_portfolio_narrator.py
git commit -m "feat(compass): BULK-tier verdict narration with deterministic fallback (Phase A Task 9)"
```

---

### Task 10: EOD digest + post-review pipeline orchestrator

**Files:**
- Create: `core/portfolio/digest.py`
- Create: `core/portfolio/pipeline.py`
- Test: `tests/unit/test_portfolio_pipeline.py`

**Interfaces:**
- Consumes: everything above; `list_user_ids`, `PortfolioStore`, `sync_corp_actions`, `refresh_events_calendar`, `load_events_calendar`, `build_signals`, `decide`, `narrate`, `close_on`, `is_trading_day`, `PredictionStore`
- Produces:
  - `digest.build_digest(user_id: str, review_date: date, advice: list[AdviceRecord], portfolio: Portfolio, closes: dict[str, float]) -> dict` — keys: `date, user_id, generated_at, portfolio_value, cost_basis, total_pnl_pct, holdings: [{symbol, verdict, close, pnl_pct, reason, notes}], escalations: [symbols with TRIM/EXIT verdicts]`
  - `pipeline.run_post_review_pipeline(review_date: date) -> dict` — for every user dir: (1) corp-action sync FIRST (invariant), (2) refresh events calendar for held symbols, (3) per holding: fetch close → build signals → decide → narrate → set `user_id` → append to advice ledger, (4) build+save digest. Per-holding failures are non-fatal. Skips entirely (status `not_trading_day`) when `is_trading_day(review_date)` is False or `ADVISOR_ENABLED` is False (status `disabled`). Returns `{"status": "completed", "users": int, "advice": int, "escalations": [..]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_pipeline.py
"""Compass Phase A — event-triggered post-review pipeline + EOD digest."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.portfolio.digest import build_digest
from core.portfolio.store import PortfolioStore
import core.portfolio.pipeline as pipeline

REVIEW_DATE = date(2026, 7, 6)


def _holding(symbol="MARUTI", price=12000.0, qty=10) -> Holding:
    return Holding(
        symbol=symbol, sector="automobile", qty=qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=qty, buy_date="2026-01-05",
    )


def _advice(symbol="MARUTI", verdict="HOLD") -> AdviceRecord:
    return AdviceRecord(
        date="2026-07-06", user_id="u", symbol=symbol, verdict=verdict,
        close=13000.0, unrealised_pnl_pct=8.33, stop_pct=10.0,
        narrative="Thesis intact.",
    )


def test_build_digest_totals_and_escalations():
    p = Portfolio(user_id="u", holdings=[_holding()])
    d = build_digest("u", REVIEW_DATE, [_advice(verdict="TRIM")], p, {"MARUTI": 13000.0})
    assert d["date"] == "2026-07-06"
    assert d["portfolio_value"] == pytest.approx(130000.0)
    assert d["cost_basis"] == pytest.approx(120000.0)
    assert d["total_pnl_pct"] == pytest.approx(130000.0 / 120000.0 * 100 - 100)
    assert d["escalations"] == ["MARUTI"]
    assert d["holdings"][0]["verdict"] == "TRIM"


def test_pipeline_skips_non_trading_day(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: False)
    result = pipeline.run_post_review_pipeline(REVIEW_DATE)
    assert result["status"] == "not_trading_day"


def test_pipeline_end_to_end(monkeypatch, tmp_path):
    # One user, one holding; every external surface faked.
    store = PortfolioStore(user_id="u", base_dir=str(tmp_path))
    store.add_holding(_holding())

    monkeypatch.setattr(pipeline.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: {"applied": 0, "symbols": []})
    monkeypatch.setattr(pipeline, "refresh_events_calendar", lambda syms, cache_path=None: {"events": {}})
    monkeypatch.setattr(pipeline, "load_events_calendar", lambda cache_path=None: {"events": {}})
    monkeypatch.setattr(pipeline, "close_on", lambda sym, d: 13000.0)
    monkeypatch.setattr(pipeline, "get_price_history", lambda t, years=1: None)
    monkeypatch.setattr(pipeline, "narrate", lambda rec, sig: "Thesis intact.")

    class _FakePredStore:
        def __init__(self, ticker, sector=None):
            pass
        def cycle_id_for(self, d):
            return "X_2026-07"
        def load_envelope(self, cid):
            return None
        def load_feedback_log(self, cid):
            return None
    monkeypatch.setattr(pipeline, "PredictionStore", _FakePredStore)

    result = pipeline.run_post_review_pipeline(REVIEW_DATE)
    assert result["status"] == "completed"
    assert result["users"] == 1 and result["advice"] == 1

    # Ledger got the record with the user id filled in
    records = store.load_advice()
    assert len(records) == 1 and records[0].user_id == "u"
    assert records[0].narrative == "Thesis intact."
    # Digest persisted
    digest = store.load_latest_digest()
    assert digest is not None and digest["date"] == REVIEW_DATE.isoformat()


def test_pipeline_holding_failure_is_non_fatal(monkeypatch, tmp_path):
    store = PortfolioStore(user_id="u", base_dir=str(tmp_path))
    store.add_holding(_holding(symbol="GOODSTK"))
    store.add_holding(_holding(symbol="BADSTK"))

    monkeypatch.setattr(pipeline.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: {"applied": 0, "symbols": []})
    monkeypatch.setattr(pipeline, "refresh_events_calendar", lambda syms, cache_path=None: {"events": {}})
    monkeypatch.setattr(pipeline, "load_events_calendar", lambda cache_path=None: {"events": {}})
    monkeypatch.setattr(pipeline, "get_price_history", lambda t, years=1: None)
    monkeypatch.setattr(pipeline, "narrate", lambda rec, sig: "")

    def close_or_boom(sym, d):
        if sym == "BADSTK":
            raise RuntimeError("no price")
        return 13000.0
    monkeypatch.setattr(pipeline, "close_on", close_or_boom)

    class _FakePredStore:
        def __init__(self, ticker, sector=None):
            pass
        def cycle_id_for(self, d):
            return "X_2026-07"
        def load_envelope(self, cid):
            return None
        def load_feedback_log(self, cid):
            return None
    monkeypatch.setattr(pipeline, "PredictionStore", _FakePredStore)

    result = pipeline.run_post_review_pipeline(REVIEW_DATE)
    assert result["status"] == "completed"
    assert result["advice"] == 1          # GOODSTK advised, BADSTK skipped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.portfolio.digest'`

- [ ] **Step 3: Write digest builder**

```python
# core/portfolio/digest.py
"""
Compass Phase A — EOD digest (spec §7): per-holding verdicts with one-line
reasons, P&L move, escalations. Event-triggered on review+advisor completion,
never clock-scheduled (at 40 tickers the review runs ~80 min).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from backend.shared.schemas.portfolio import AdviceRecord, Portfolio


def build_digest(
    user_id: str,
    review_date: date,
    advice: list[AdviceRecord],
    portfolio: Portfolio,
    closes: dict[str, float],
) -> dict:
    value = 0.0
    cost = 0.0
    rows = []
    by_symbol = {a.symbol: a for a in advice}
    for h in portfolio.holdings:
        close = closes.get(h.symbol)
        if close is not None:
            value += h.adj_qty * close
        cost += h.adj_qty * h.adj_avg_price
        rec = by_symbol.get(h.symbol)
        rows.append({
            "symbol": h.symbol,
            "verdict": rec.verdict if rec else "NO_DATA",
            "close": close,
            "pnl_pct": round(h.unrealised_pnl_pct(close), 2) if close is not None else None,
            "reason": rec.narrative if rec else "no advisor run for this holding today",
            "notes": rec.notes if rec else [],
        })
    escalations = sorted(a.symbol for a in advice if a.verdict in ("TRIM", "EXIT"))
    return {
        "date": review_date.isoformat(),
        "user_id": user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_value": round(value, 2),
        "cost_basis": round(cost, 2),
        "total_pnl_pct": round(value / cost * 100 - 100, 2) if cost > 0 else 0.0,
        "holdings": rows,
        "escalations": escalations,
    }
```

- [ ] **Step 4: Write the pipeline orchestrator**

```python
# core/portfolio/pipeline.py
"""
Compass Phase A — post-review portfolio pipeline (event-triggered).

Called by scheduler_api._review_task AFTER the daily reviews finish. Order is
load-bearing: corp-action sync runs FIRST so adj_avg_price is correct before
any advisor rule (spec §4.1 invariant). Every step is non-fatal per holding —
pipeline errors are telemetry, never training signal.
"""
from __future__ import annotations

import logging
from datetime import date

from core.config import settings
from core.intelligence.algorithms.indicators.fetcher import get_price_history
from core.intelligence.rl.nse_calendar import is_trading_day
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.portfolio.advisor import build_signals, decide
from core.portfolio.corp_actions import sync_corp_actions
from core.portfolio.digest import build_digest
from core.portfolio.narrator import narrate
from core.portfolio.pricing import close_on
from core.portfolio.store import PortfolioStore, list_user_ids
from services.data.fetchers.corporate_events import (
    load_events_calendar,
    refresh_events_calendar,
)

logger = logging.getLogger(__name__)


def run_post_review_pipeline(review_date: date) -> dict:
    if not settings.ADVISOR_ENABLED:
        return {"status": "disabled"}
    if not is_trading_day(review_date):
        logger.info("[portfolio_pipeline] %s is not a trading day — skipping", review_date)
        return {"status": "not_trading_day"}

    users = list_user_ids()
    total_advice, escalations = 0, []

    for user_id in users:
        store = PortfolioStore(user_id=user_id)
        # Step 1 — corp-action sync BEFORE any advisor rule (invariant).
        try:
            sync_corp_actions(store, review_date)
        except Exception as exc:
            logger.warning("[portfolio_pipeline] corp-action sync failed for %s: %s",
                           user_id, exc)
        portfolio = store.load()
        if not portfolio.holdings:
            continue

        # Step 2 — refresh forward events for held symbols (degraded-mode safe).
        symbols = [h.symbol for h in portfolio.holdings]
        try:
            calendar = refresh_events_calendar(symbols)
        except Exception as exc:
            logger.warning("[portfolio_pipeline] events refresh failed (using stale): %s", exc)
            calendar = load_events_calendar()

        # Step 3 — advise each holding.
        advice, closes = [], {}
        for holding in portfolio.holdings:
            try:
                close = close_on(holding.symbol, review_date)
                closes[holding.symbol] = close
                ohlcv = None
                try:
                    ohlcv = get_price_history(holding.symbol, years=1)
                except Exception as exc:
                    logger.debug("[portfolio_pipeline] OHLCV fetch failed for %s: %s",
                                 holding.symbol, exc)
                pred_store = PredictionStore(holding.symbol, sector=holding.sector)
                signals = build_signals(
                    holding, portfolio, review_date, pred_store, calendar, close,
                    ohlcv_df=ohlcv,
                )
                rec = decide(signals, holding, portfolio.risk_profile)
                rec.user_id = user_id
                rec.date = review_date.isoformat()
                rec.narrative = narrate(rec, signals)
                store.append_advice(rec)
                advice.append(rec)
            except Exception as exc:
                logger.warning(
                    "[portfolio_pipeline] advisor failed for %s/%s (non-fatal): %s",
                    user_id, holding.symbol, exc,
                )
        total_advice += len(advice)
        escalations.extend(a.symbol for a in advice if a.verdict in ("TRIM", "EXIT"))

        # Step 4 — digest.
        try:
            store.save_digest(build_digest(user_id, review_date, advice, portfolio, closes))
        except Exception as exc:
            logger.warning("[portfolio_pipeline] digest failed for %s: %s", user_id, exc)

    logger.info(
        "[portfolio_pipeline] complete — users=%d advice=%d escalations=%s",
        len(users), total_advice, escalations,
    )
    return {
        "status": "completed",
        "users": len(users),
        "advice": total_advice,
        "escalations": escalations,
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_pipeline.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add core/portfolio/digest.py core/portfolio/pipeline.py tests/unit/test_portfolio_pipeline.py
git commit -m "feat(compass): EOD digest + event-triggered post-review pipeline (Phase A Task 10)"
```

---

### Task 11: Portfolio API routes

**Files:**
- Create: `services/api/routes/portfolio_api.py`
- Modify: `services/api/server.py` (two lines: import at the router import block ~line 50, `include_router` at ~line 395)
- Test: `tests/unit/test_portfolio_api.py`

**Interfaces:**
- Consumes: everything above; auth mirrors `scheduler_api._check_auth` (optional `X-Scheduler-Key`, deferred lockdown)
- Produces (all under `/portfolio`, `user_id` query param defaulting to `settings.PORTFOLIO_DEFAULT_USER_ID`):
  - `GET  /portfolio` — portfolio + per-holding mark-to-market (uses `close_on` today, walk-back safe)
  - `POST /portfolio/holdings` — body `{symbol, sector, qty, buy_date, price?}`; price omitted → real NSE close on buy_date (`close_on`); 422 on unsupported sector or unavailable price; triggers `promote_symbol(origin="held")`
  - `DELETE /portfolio/holdings/{symbol}` — removes + `demote_symbol` when symbol not on watchlist
  - `POST /portfolio/watchlist` — body `{symbol, sector, reason?}`; triggers `promote_symbol(origin="watchlist")`
  - `DELETE /portfolio/watchlist/{symbol}`
  - `POST /portfolio/import-csv` — raw CSV text body; per-row errors reported, priced rows promoted
  - `GET  /portfolio/advice` — last N ledger records (query `limit`, default 50)
  - `GET  /portfolio/digest/latest`
  - `POST /portfolio/run-advisor` — manual trigger of `run_post_review_pipeline` as background task (202)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_api.py
"""Compass Phase A — portfolio REST surface (isolated app, no full server)."""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.api.routes.portfolio_api as papi
from backend.shared.schemas.portfolio import Holding
from core.portfolio.store import PortfolioStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(papi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(papi, "close_on", lambda sym, d: 12000.0)
    monkeypatch.setattr(papi, "promote_symbol",
                        lambda symbol, sector, origin: {"status": "promoted", "symbol": symbol})
    monkeypatch.setattr(papi, "demote_symbol", lambda symbol: True)
    app = FastAPI()
    app.include_router(papi.router)
    return TestClient(app)


def test_add_holding_prices_at_close(client, tmp_path):
    resp = client.post("/portfolio/holdings", json={
        "symbol": "MARUTI", "sector": "automobile", "qty": 10, "buy_date": "2026-07-01",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["holding"]["avg_buy_price"] == 12000.0
    assert body["holding"]["virtual"] is True
    assert body["promotion"]["status"] == "promoted"


def test_add_holding_unsupported_sector_422(client, monkeypatch):
    monkeypatch.setattr(
        papi, "promote_symbol",
        lambda symbol, sector, origin: {"status": "unsupported_sector",
                                         "detail": "sector not yet supported"},
    )
    resp = client.post("/portfolio/holdings", json={
        "symbol": "SUNPHARMA", "sector": "pharma", "qty": 5, "buy_date": "2026-07-01",
    })
    assert resp.status_code == 422
    assert "not yet supported" in resp.json()["detail"]


def test_get_portfolio_marks_to_market(client):
    client.post("/portfolio/holdings", json={
        "symbol": "MARUTI", "sector": "automobile", "qty": 10,
        "buy_date": "2026-07-01", "price": 10000.0,
    })
    resp = client.get("/portfolio")
    assert resp.status_code == 200
    row = resp.json()["holdings"][0]
    assert row["last_close"] == 12000.0
    assert row["pnl_pct"] == pytest.approx(20.0)


def test_delete_holding(client):
    client.post("/portfolio/holdings", json={
        "symbol": "MARUTI", "sector": "automobile", "qty": 10,
        "buy_date": "2026-07-01", "price": 10000.0,
    })
    assert client.delete("/portfolio/holdings/MARUTI").status_code == 200
    assert client.delete("/portfolio/holdings/MARUTI").status_code == 404


def test_watchlist_roundtrip(client):
    resp = client.post("/portfolio/watchlist", json={
        "symbol": "TCS", "sector": "it_sector", "reason": "quality compounder",
    })
    assert resp.status_code == 200
    assert client.get("/portfolio").json()["watchlist"][0]["symbol"] == "TCS"
    assert client.delete("/portfolio/watchlist/TCS").status_code == 200


def test_import_csv(client):
    csv_text = (
        "symbol,sector,qty,avg_buy_price,buy_date\n"
        "MARUTI,automobile,10,11000,2026-01-05\n"
    )
    resp = client.post("/portfolio/import-csv", content=csv_text,
                       headers={"Content-Type": "text/csv"})
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1


def test_advice_and_digest_empty_ok(client):
    assert client.get("/portfolio/advice").json()["records"] == []
    assert client.get("/portfolio/digest/latest").status_code == 404


def test_run_advisor_returns_202(client, monkeypatch):
    monkeypatch.setattr(papi, "run_post_review_pipeline", lambda d: {"status": "completed"})
    resp = client.post("/portfolio/run-advisor")
    assert resp.status_code == 202
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.api.routes.portfolio_api'`

- [ ] **Step 3: Write the router**

```python
# services/api/routes/portfolio_api.py
"""
services/api/routes/portfolio_api.py
=====================================
Compass Phase A — virtual portfolio + advisor REST surface.

Endpoints (user_id query param defaults to portfolio.default_user_id)
---------------------------------------------------------------------
GET    /portfolio                      Holdings + watchlist, marked to market
POST   /portfolio/holdings             Add virtual buy (priced at real NSE close)
DELETE /portfolio/holdings/{symbol}
POST   /portfolio/watchlist
DELETE /portfolio/watchlist/{symbol}
POST   /portfolio/import-csv           Raw CSV body: symbol,sector,qty,avg_buy_price,buy_date
GET    /portfolio/advice               Advice-ledger tail
GET    /portfolio/digest/latest
POST   /portfolio/run-advisor          Manual pipeline trigger (202, background)

Authentication: same optional X-Scheduler-Key pattern as scheduler_api.
USER DECISION 2026-07-06: hard lockdown deferred while portfolio is virtual.
All output is research/analysis, never "advice". No auto-trading, ever.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from pydantic import BaseModel

from core.config import settings
from backend.shared.schemas.portfolio import Holding, WatchlistItem
from core.portfolio.pipeline import run_post_review_pipeline
from core.portfolio.pricing import PriceUnavailableError, close_on
from core.portfolio.promotion import demote_symbol, promote_symbol
from core.portfolio.store import PortfolioStore, import_csv

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


def _check_auth(key: str | None) -> None:
    required = os.getenv("SCHEDULER_KEY", "")
    if required and key != required:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Scheduler-Key header.")
    if not required:
        logger.warning("[portfolio_api] SCHEDULER_KEY not set — endpoint is open "
                       "(accepted for virtual-money phase; revisit before real holdings).")


class HoldingIn(BaseModel):
    symbol: str
    sector: str
    qty: float
    buy_date: str                      # ISO date
    price: float | None = None         # omitted -> real NSE close on buy_date


class WatchlistIn(BaseModel):
    symbol: str
    sector: str
    reason: str = ""


@router.get("", summary="Portfolio with mark-to-market P&L")
async def get_portfolio(
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    store = PortfolioStore(user_id=user_id)
    p = store.load()
    holdings = []
    for h in p.holdings:
        last_close, pnl = None, None
        try:
            last_close = close_on(h.symbol, date.today())
            pnl = round(h.unrealised_pnl_pct(last_close), 2)
        except Exception as exc:
            logger.warning("[portfolio_api] mark failed for %s: %s", h.symbol, exc)
        holdings.append({**h.model_dump(), "last_close": last_close, "pnl_pct": pnl})
    return {
        "user_id": p.user_id,
        "risk_profile": p.risk_profile,
        "holdings": holdings,
        "watchlist": [w.model_dump() for w in p.watchlist],
        "disclaimer": "Research/analysis output for the portfolio owner — not investment advice.",
    }


@router.post("/holdings", summary="Add a virtual holding (mock money, real prices)")
async def add_holding(
    body: HoldingIn,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    symbol = body.symbol.strip().upper()
    promotion = promote_symbol(symbol, body.sector, origin="held")
    if promotion["status"] == "unsupported_sector":
        raise HTTPException(status_code=422, detail=promotion["detail"])
    if body.price is not None:
        price = body.price
    else:
        try:
            price = close_on(symbol, date.fromisoformat(body.buy_date))
        except PriceUnavailableError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    holding = Holding(
        symbol=symbol, sector=body.sector, qty=body.qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=body.qty, buy_date=body.buy_date,
    )
    try:
        PortfolioStore(user_id=user_id).add_holding(holding)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"holding": holding.model_dump(), "promotion": promotion}


@router.delete("/holdings/{symbol}", summary="Remove a holding")
async def delete_holding(
    symbol: str,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    store = PortfolioStore(user_id=user_id)
    if not store.remove_holding(symbol):
        raise HTTPException(status_code=404, detail=f"No holding {symbol.upper()}")
    demoted = False
    p = store.load()
    if not any(w.symbol == symbol.upper() for w in p.watchlist):
        demoted = demote_symbol(symbol)
    return {"removed": symbol.upper(), "demoted": demoted}


@router.post("/watchlist", summary="Add a watchlist symbol")
async def add_watchlist(
    body: WatchlistIn,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    symbol = body.symbol.strip().upper()
    promotion = promote_symbol(symbol, body.sector, origin="watchlist")
    if promotion["status"] == "unsupported_sector":
        raise HTTPException(status_code=422, detail=promotion["detail"])
    item = WatchlistItem(
        symbol=symbol, sector=body.sector, added=date.today().isoformat(),
        reason=body.reason, source="user",
    )
    PortfolioStore(user_id=user_id).add_watchlist(item)
    return {"watchlist_item": item.model_dump(), "promotion": promotion}


@router.delete("/watchlist/{symbol}", summary="Remove a watchlist symbol")
async def delete_watchlist(
    symbol: str,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    store = PortfolioStore(user_id=user_id)
    if not store.remove_watchlist(symbol):
        raise HTTPException(status_code=404, detail=f"No watchlist entry {symbol.upper()}")
    demoted = False
    p = store.load()
    if not any(h.symbol == symbol.upper() for h in p.holdings):
        demoted = demote_symbol(symbol)
    return {"removed": symbol.upper(), "demoted": demoted}


@router.post("/import-csv", summary="Bulk import holdings from CSV text")
async def import_csv_endpoint(
    request: Request,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    text = (await request.body()).decode("utf-8", errors="replace")
    result = import_csv(
        text, user_id=user_id,
        price_lookup=lambda sym, d: close_on(sym, date.fromisoformat(d)),
    )
    # Promote successfully imported symbols (held origin).
    p = PortfolioStore(user_id=user_id).load()
    for h in p.holdings:
        try:
            promote_symbol(h.symbol, h.sector, origin="held")
        except Exception as exc:
            logger.warning("[portfolio_api] promotion failed for %s: %s", h.symbol, exc)
    return result


@router.get("/advice", summary="Advice-ledger tail")
async def get_advice(
    user_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    records = PortfolioStore(user_id=user_id).load_advice(limit=limit)
    return {"records": [r.model_dump() for r in records]}


@router.get("/digest/latest", summary="Latest EOD digest")
async def get_latest_digest(
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    digest = PortfolioStore(user_id=user_id).load_latest_digest()
    if digest is None:
        raise HTTPException(status_code=404, detail="No digest yet — run the advisor first.")
    return digest


@router.post("/run-advisor", status_code=202, summary="Manually trigger the post-review pipeline")
async def run_advisor(
    background_tasks: BackgroundTasks,
    review_date: str | None = Query(default=None, description="ISO date; default today"),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    target = date.fromisoformat(review_date) if review_date else date.today()

    async def _task() -> None:
        result = await asyncio.to_thread(run_post_review_pipeline, target)
        logger.info("[portfolio_api] manual advisor run: %s", result)

    background_tasks.add_task(_task)
    return {"status": "accepted", "review_date": target.isoformat()}
```

- [ ] **Step 4: Register the router in server.py**

In `services/api/server.py`, add after the `analytics_router` import (~line 50):

```python
from services.api.routes.portfolio_api import router as portfolio_router
```

and after `app.include_router(analytics_router, tags=["Analytics"])` (~line 395):

```python
app.include_router(portfolio_router,  tags=["Portfolio"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_api.py -v`
Expected: 8 PASS

- [ ] **Step 6: Commit**

```bash
git add services/api/routes/portfolio_api.py services/api/server.py tests/unit/test_portfolio_api.py
git commit -m "feat(compass): portfolio REST API — holdings, watchlist, CSV, advice, digest (Phase A Task 11)"
```

---

### Task 12: Scheduler hook — advisor+digest event-triggered on review completion; cadence filter

**Files:**
- Modify: `services/api/routes/scheduler_api.py` (`_review_task` ~line 220; `_run_reviews` ~line 176)
- Test: `tests/unit/test_scheduler_portfolio_hook.py`

**Interfaces:**
- Consumes: `run_post_review_pipeline` (Task 10), `due_for_review` (Task 7)
- Produces: `_review_task` runs `run_post_review_pipeline(dates[-1])` AFTER `_run_reviews` finishes (non-fatal); `_run_reviews` skips ticker-date pairs where `due_for_review(entry, review_date)` is False with status `skipped_cadence`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scheduler_portfolio_hook.py
"""Compass Phase A — digest/advisor fire on review completion, never on clock."""
import asyncio
from datetime import date

import services.api.routes.scheduler_api as sched


def test_review_task_triggers_portfolio_pipeline(monkeypatch):
    calls = {}
    monkeypatch.setattr(sched, "_run_reviews", lambda t, d, s=False: [
        {"ticker": "MARUTI", "date": "2026-07-06", "status": "completed"},
    ])
    monkeypatch.setattr(
        sched, "run_post_review_pipeline",
        lambda review_date: calls.setdefault("date", review_date) or {"status": "completed"},
    )
    asyncio.run(sched._review_task(
        [{"sym": "MARUTI", "sector": "automobile"}], [date(2026, 7, 6)],
    ))
    assert calls["date"] == date(2026, 7, 6)


def test_review_task_survives_pipeline_failure(monkeypatch):
    monkeypatch.setattr(sched, "_run_reviews", lambda t, d, s=False: [])

    def boom(review_date):
        raise RuntimeError("pipeline exploded")
    monkeypatch.setattr(sched, "run_post_review_pipeline", boom)
    # Must not raise — reviews already succeeded, pipeline failure is telemetry.
    asyncio.run(sched._review_task(
        [{"sym": "MARUTI", "sector": "automobile"}], [date(2026, 7, 6)],
    ))


def test_run_reviews_respects_cadence(monkeypatch):
    ran = []
    # _run_reviews imports run_daily_review INSIDE the function body, so patch
    # the source module attribute — the late import picks up the patched name.
    import core.intelligence.rl.workflows.daily_review as dr
    monkeypatch.setattr(
        dr, "run_daily_review",
        lambda ticker, review_date, sector=None: ran.append(ticker) or {"status": "completed"},
    )
    monday = date(2026, 7, 6)   # weekday 0 — weekly names not due
    results = sched._run_reviews(
        [
            {"sym": "MARUTI", "sector": "automobile"},                       # legacy: daily
            {"sym": "INFY", "sector": "it_sector", "cadence": "weekly"},     # not due Monday
        ],
        [monday],
    )
    assert "MARUTI" in ran and "INFY" not in ran
    statuses = {r["ticker"]: r["status"] for r in results}
    assert statuses["INFY"] == "skipped_cadence"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_scheduler_portfolio_hook.py -v`
Expected: FAIL (`AttributeError: ... has no attribute 'run_post_review_pipeline'` and missing `skipped_cadence` handling)

- [ ] **Step 3: Modify scheduler_api.py**

Add a module-level import near the top of `services/api/routes/scheduler_api.py` (after the existing imports, ~line 33) — module-level so tests can monkeypatch it:

```python
from core.portfolio.pipeline import run_post_review_pipeline
from core.portfolio.promotion import due_for_review
```

In `_run_reviews`, add the cadence gate at the top of the inner loop (right after `ticker, sector = entry["sym"], entry.get("sector", _SECTOR)`):

```python
                if not due_for_review(entry, review_date):
                    logger.info(
                        "[scheduler_api] Skip %s %s — weekly cadence, not due today",
                        ticker, review_date,
                    )
                    results.append({
                        "ticker": ticker, "date": review_date.isoformat(),
                        "status": "skipped_cadence",
                    })
                    continue
```

Replace `_review_task` with:

```python
async def _review_task(tickers: list[dict], dates: list[date], skip_existing: bool = False) -> None:
    results = await asyncio.to_thread(_run_reviews, tickers, dates, skip_existing)
    completed = sum(1 for r in results if r.get("status") == "completed")
    logger.info(
        "[scheduler_api] Review task complete: %d completed across %d ticker-date pairs",
        completed, len(results),
    )
    # Compass Phase A: advisor + digest run EVENT-TRIGGERED on review completion
    # (never clock-scheduled — at 40 tickers the review runs ~80 min). Non-fatal:
    # a pipeline failure must never mark the reviews themselves as failed.
    try:
        summary = await asyncio.to_thread(run_post_review_pipeline, dates[-1])
        logger.info("[scheduler_api] Post-review portfolio pipeline: %s", summary)
    except Exception as exc:
        logger.error(
            "[scheduler_api] Post-review portfolio pipeline failed (non-fatal): %s",
            exc, exc_info=True,
        )
```

Also update `_resolve_tickers`'s returned entries to pass through cadence metadata — change the list comprehension in `services/api/log_buffer.py:get_active_tickers_with_sector` to:

```python
    return [
        {
            "sym": t["sym"],
            "sector": t.get("sector", "automobile"),
            "cadence": t.get("cadence", "daily"),
        }
        for t in load_managed_tickers()
        if t.get("enabled", True)
    ]
```

- [ ] **Step 4: Run the new test, then the full suite**

Run: `python -m pytest tests/unit/test_scheduler_portfolio_hook.py -v`
Expected: 3 PASS

Run: `python -m pytest tests/ -q`
Expected: everything green — 285 pre-existing passing (7 skipped) plus all new Phase A tests; 0 failures. If any pre-existing test broke, fix before committing.

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/scheduler_api.py services/api/log_buffer.py tests/unit/test_scheduler_portfolio_hook.py
git commit -m "feat(compass): advisor+digest event-triggered on review completion; weekly cadence gate (Phase A Task 12)"
```

---

### Task 13: End-to-end verification + docs

**Files:**
- Modify: `CODEBASE.md` (add `core/portfolio/` to the module map, one short paragraph in the same style as neighboring entries)

- [ ] **Step 1: Full test suite**

Run: `python -m pytest tests/ -q`
Expected: 285 pre-existing + ~80 new, all passing, 7 skipped, 0 failures.

- [ ] **Step 2: Live smoke test (local, no LLM cost beyond one BULK narration)**

```bash
python -c "
from datetime import date
from core.portfolio.store import PortfolioStore
from backend.shared.schemas.portfolio import Holding
from core.portfolio.pricing import close_on

# 1. Real entry pricing (network: yfinance + NSE cross-check)
price = close_on('MARUTI', date(2026, 7, 3))
print('MARUTI close 2026-07-03:', price)

# 2. Virtual buy
store = PortfolioStore(user_id='primary')
store.add_holding(Holding(symbol='MARUTI', sector='automobile', qty=10,
                          avg_buy_price=price, adj_avg_price=price, adj_qty=10,
                          buy_date='2026-07-03'))
print('holdings:', [h.symbol for h in store.load().holdings])

# 3. Full pipeline (corp actions -> events -> advisor -> narration -> digest)
from core.portfolio.pipeline import run_post_review_pipeline
print(run_post_review_pipeline(date(2026, 7, 3)))
print('digest:', store.load_latest_digest())
print('advice:', [ (r.symbol, r.verdict, r.narrative[:80]) for r in store.load_advice() ])
"
```

Expected: a real close price, `{"status": "completed", "users": 1, "advice": 1, ...}`, a digest dict, and one HOLD (or data-driven) advice line with narrative text. MARUTI has existing envelopes/feedback in `data/predictions/automobile/MARUTI/`, so signals should populate. If the envelope for the current month is missing locally, `build_signals` falls back to defaults and the verdict is still produced — that's the designed degradation.

- [ ] **Step 3: Verify managed-tickers promotion happened**

```bash
python -c "import json; print(json.load(open('data/managed_tickers.json')))"
```

Expected: MARUTI present (already managed → no duplicate, `already_managed` path exercised).

- [ ] **Step 4: Update CODEBASE.md**

Add to the module map (match surrounding formatting):

```markdown
- `core/portfolio/` — Compass Phase A: per-user virtual portfolio (store, corp-action
  sync, auto-promotion into managed universe, deterministic HOLD/ADD/TRIM/EXIT advisor
  with ATR-scaled stops, BULK-tier narration, EOD digest). Event-triggered from
  scheduler_api._review_task after daily reviews. Spec:
  docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md
```

- [ ] **Step 5: Commit**

```bash
git add CODEBASE.md
git commit -m "docs(compass): register core/portfolio module in CODEBASE.md (Phase A Task 13)"
```

---

## Deferred / explicitly out of Phase A scope

- **Auth gate / SCHEDULER_KEY lockdown** — USER DEFERRED 2026-07-06 (virtual money). Revisit before real holdings or multi-user.
- SWITCH verdict (needs the Discovery shelf — Phase C).
- Generic sector graph / promotion beyond 4 sectors (Phase B).
- Discovery funnel, bhavcopy market-cache layer, paper lane (Phase B).
- Morning brief, push/email delivery, weekly review (Phase C) — Phase A digest is stored + served via `GET /portfolio/digest/latest` only.
- Advice-outcome filling (+10/30/60td) and threshold adaptation (Phase D; the ledger accumulates from day one).
- Kite Personal broker sync (anytime after A, opt-in).
- Chat-command entry of holdings ("bought 10 MARUTI") — REST + CSV cover Phase A; chat wiring can ride the existing agentic chat loop later without schema changes.
