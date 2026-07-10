# Compass Phase C — IPO Tracker + Proactive Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The M3 Stage-2 IPO / new-listing tracker feeding the existing weekly deep-dive funnel, the M2 SWITCH verdict, and the full M4 proactive-delivery layer (morning brief, weekly review, event alerts, index-inclusion watch) delivered over web-push (PWA/TWA) + SMTP email, with a `brief` chat tool.

**Architecture:** Three new surfaces. (1) **IPO tracker**: `services/data/fetchers/ipo.py` (nse pkg `listCurrentIPO`/`listUpcomingIPO`/`listPastIPO`, degraded-mode cache) + `core/discovery/ipo_tracker.py` (QIB-3×-retail subscription score, post-listing evidence from the EOD parquet store + bulk/block cache, 30/90/180-day lock-in calendar) producing `DiscoveryCandidate`s that merge into the existing Stage-3 deep-dive budget. (2) **SWITCH verdict**: `advisor.decide()` gains shelf context — EXIT + a ≥`advisor.switch_conviction_gap` stronger active shelf idea in an underweight sector → SWITCH. (3) **M4 delivery**: new `core/delivery/` package — channels (web-push via pywebpush + VAPID, SMTP email, both non-fatal), deduped alert engine, morning-brief builder (Mon-Fri 08:50 IST job), weekly-review builder + index-constituent diff (Sun 18:00 IST job), `/delivery/*` API, service-worker push handlers, chat `get_portfolio_brief` tool.

**Tech Stack:** Python 3.11, Pydantic v2, pandas/pyarrow (EOD store), FastAPI, APScheduler, `nse` pkg (verified: `listCurrentIPO()`, `listUpcomingIPO()`, `listPastIPO(from_date, to_date)`, `listEquityStocksByIndex(index)`), **pywebpush (new dep)** + stdlib `smtplib`, OpenRouter BULK tier via `services/clients/llm_client.py`.

**Spec:** `docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md` (§5.2 SWITCH, §6.2 IPO tracker, §7 M4, §9 rails, §10 Phase C row).

## Verified-against-code findings (read before implementing)

- `nse` pkg methods verified in the venv: `listCurrentIPO(self) -> List[Dict]`, `listUpcomingIPO(self) -> List[Dict]`, `listPastIPO(self, from_date=None, to_date=None) -> List[Dict]` (defaults to 90 days back), `listEquityStocksByIndex(self, index='NIFTY 50') -> dict`. Field names in the returned dicts vary across NSE report vintages — normalize with candidate-key tuples exactly like `services/data/fetchers/bulk_block.py::_first` does. Subscription-breakdown fields (QIB/retail ×) may be ABSENT — the subscription sub-score must be optional and the composite must renormalize over available sub-scores (same dark-signal pattern as `discovery.signal_weights`).
- `EodStore` (`services/data/stores/eod_store.py`) canonical columns: `symbol, series, date (ISO str), prev_close, open, high, low, close, volume, traded_value_cr, delivery_qty, delivery_pct`. `load_window(end, sessions)` concatenates per-day parquet files. New listings simply appear in the window — evidence signals need ≥5 sessions.
- `run_deep_dives(candidates, on, max_n=None)` (`core/discovery/deep_dive.py`) consumes `DiscoveryCandidate` and already skips managed/shelved symbols — IPO candidates convert to `DiscoveryCandidate(flags=["ipo"])` and need **no deep-dive changes** except a duplicate-symbol guard (Task 4) since a young listing could also pass the quant screen.
- `run_discovery_cycle` (`core/discovery/__init__.py`) re-exports collaborators at package level — **tests patch names on `core.discovery`**, so new collaborators (`refresh_ipo_cache`, `build_ipo_candidates`) must be imported and re-exported there too.
- `advisor.decide(signals, holding, risk_profile)` is called from `core/portfolio/pipeline.py:79` and from `tests/unit/test_portfolio_advisor.py` — new params MUST be keyword-with-defaults to stay backward compatible. `AdvisorSignals.confidence` (mean remaining envelope confidence, 0-1) is the holding-conviction proxy for the SWITCH gap; `ShelfIdea.conviction` is `FinalReport.final_score` (also 0-1).
- Escalation filters exist in TWO places — `core/portfolio/pipeline.py:91` and `core/portfolio/digest.py:38` — both currently `("TRIM", "EXIT")`; both must add `"SWITCH"`.
- `narrator.py::_TRIGGER_TEXT` maps trigger codes to fallback text — new codes without an entry degrade gracefully (code echoed), but add proper text anyway.
- Digest persistence pattern to mirror for briefs/weeklies: `PortfolioStore.save_digest`/`load_latest_digest` (`core/portfolio/store.py:174-190`) — per-user dated JSON under `data/portfolio/<user>/`, atomic `_write_json`.
- Morning-brief inputs all exist: latest digest (`PortfolioStore.load_latest_digest`), macro feed (`services/background/macro_news_cache.py::MacroNewsCache.get_high_severity(hours_back)` → list of dicts with `headline`/`severity`), sticky regime (`data/predictions/_regime_state.json` via `Path(settings.PREDICTION_DATA_DIR)`, fields incl. `label`, `calm_streak`), shelf event feed (`data/discovery/shelf_events.jsonl` — the docstring in `shelf.py` says "the add/drop feed that M4 proactive delivery consumes in Phase C"), forward earnings (`services/data/fetchers/corporate_events.py::load_events_calendar` + `next_results_event`), trading-day gate (`core.intelligence.rl.nse_calendar.is_trading_day`).
- Pre-open shock job (`scheduler.py::_preopen_shock_check_job`, 08:45 IST) already returns `{"reforecasts": [...]}` — the morning brief runs at **08:50** so those re-forecasts are visible to it; the job is also the alert hook for `preopen_reforecast`.
- The chat tool loop: `_CHAT_TOOLS` list (`services/api/routes/ui_data.py:1906`) + `_dispatch_chat_tool` (`ui_data.py:2630`) — both streaming and non-streaming paths share them. New tool = one schema entry + one dispatch branch + one sync impl function.
- Service worker (`src/frontend/prototypes/sw.js`) has NO push handlers yet; `index.html:21-29` registers it. `API_PREFIXES` in sw.js must gain `'/delivery'` or the new API responses would be cached. VAPID keys do not exist anywhere — Task 13 ships `scripts/gen_vapid_keys.py` and the ops step documents setting them in `.env`/Railway.
- LLM narration pattern to copy exactly: `core/portfolio/narrator.py` — BULK tier, `response_format={"type":"json_object"}` + `extra_body=JSON_MODE_EXTRA_BODY`, `salvage_truncated_json`, `record_llm_call`, deterministic fallback on ANY failure.
- Secrets pattern: `base.py` uses plain `os.getenv` for secrets (`OPENROUTER_API_KEY`, `SERPER_API_KEY`) — SMTP_*/VAPID_* follow that, never config.yaml.
- Anchor-investor lock-in rule (SEBI, since Feb 2022): 50% of anchor allotment unlocks at 30 days, remainder at 90 days; other pre-IPO shareholders at 6 months. Encoded as fixed offsets `(30, 90, 180)` from listing date — deterministic, no data source needed.

## Global Constraints

- **Cost rails:** IPO candidates share the existing weekly LLM budget — total Stage-3 dives stay ≤ `discovery.deep_dive_count` (10/week); at most `discovery.ipo_max_deep_dives` (2) of those slots go to IPO names. Brief/weekly narration = ONE BULK-tier call each (≤ ~2 calls/day + 1/week); alerts are narration-free.
- Every `response_format={"type": "json_object"}` LLM call passes `extra_body=JSON_MODE_EXTRA_BODY` (from `services/clients/llm_client.py`).
- Pipeline errors are telemetry, never training signal: every fetcher, channel send, alert emit, brief/weekly build is non-fatal (log warning, degrade, continue). A delivery failure must NEVER fail the advisor pipeline, the pre-open check, or the discovery cycle.
- All tunables in `config.yaml` + `src/backend/shared/config/settings/base.py` via `cfg("section.key", env=..., fallback=...)`; **base.py fallbacks for master gates are `False`** (prod enables via yaml). Secrets (`SMTP_HOST/PORT/USER/PASSWORD`, `DELIVERY_EMAIL_TO`, `VAPID_PRIVATE_KEY/PUBLIC_KEY/CLAIM_EMAIL`) in `.env` only.
- All persistent state under `data/` (Railway volume), atomic writes (temp + rename). New stores: `data/market_cache/ipo.json`, `data/market_cache/index_constituents.json`, `data/delivery/push_subscriptions.json`, `data/delivery/alerts_sent.jsonl`, `data/portfolio/<user>/briefs/*.json`, `data/portfolio/<user>/weekly/*.json`.
- Output copy is research/analysis, never "advice" (spec §2); SME IPOs excluded by default (`discovery.include_sme: false`); lock-in expiries are FLAGS, never buy signals (spec §6.2 "flag, don't buy into them"); no auto-trading.
- Verdict precedence stays EXIT-grade for SWITCH: SWITCH is an EXIT with a replacement suggestion — tax logic must never soften it; it appears in every escalation list.
- New API routes mirror `scheduler_api._check_auth` (optional `X-Scheduler-Key`; lockdown deferred — user decision 2026-07-06).
- Test store isolation: every new store/builder accepts an optional explicit path/base-dir argument so tests use `tmp_path` (house pattern: `ShelfStore(path=...)`, `PortfolioStore(base_dir=...)`).
- Unit suite baseline on merged main: **1766 passed / 5 skipped** (+3 pre-existing `tests/contract/test_phase0_llm_migration` failures — known, not Phase C's problem). Every task's final step runs its test file AND must not break neighbours; Task 14 runs the whole suite.
- Run tests from repo root: `python -m pytest tests/unit/<file> -v` (pythonpath `[".", "src"]` from pyproject.toml).

---

### Task 1: Config + settings for `delivery.*`, `discovery.ipo_*`, `advisor.switch_conviction_gap` (+ pywebpush dep)

**Files:**
- Modify: `config.yaml` (one line inside `advisor:`, five lines inside `discovery:`, new `delivery:` block at end)
- Modify: `src/backend/shared/config/settings/base.py` (append after the discovery block, ~line 807)
- Modify: `requirements.txt`
- Test: `tests/unit/test_delivery_settings.py`

**Interfaces:**
- Produces (read by every later task): `settings.DISCOVERY_IPO_ENABLED: bool`, `DISCOVERY_IPO_LISTING_WINDOW_DAYS: int`, `DISCOVERY_IPO_MAX_DEEP_DIVES: int`, `DISCOVERY_IPO_LOCKIN_WARN_DAYS: int`, `DISCOVERY_IPO_QIB_WEIGHT: float`, `ADVISOR_SWITCH_CONVICTION_GAP: float`, `DELIVERY_ENABLED: bool`, `DELIVERY_DATA_DIR: str`, `DELIVERY_EMAIL_ENABLED: bool`, `DELIVERY_PUSH_ENABLED: bool`, `DELIVERY_INDEX_WATCH: list[str]`, `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD`, `DELIVERY_EMAIL_TO`, `VAPID_PRIVATE_KEY/VAPID_PUBLIC_KEY/VAPID_CLAIM_EMAIL`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_delivery_settings.py
"""Compass Phase C — delivery + IPO-tracker tunables exposed via settings."""
from core.config import settings


def test_ipo_settings_present():
    assert settings.DISCOVERY_IPO_ENABLED is True       # yaml true; base.py fallback False
    assert settings.DISCOVERY_IPO_LISTING_WINDOW_DAYS == 90
    assert settings.DISCOVERY_IPO_MAX_DEEP_DIVES == 2
    assert settings.DISCOVERY_IPO_LOCKIN_WARN_DAYS == 7
    assert settings.DISCOVERY_IPO_QIB_WEIGHT == 3.0


def test_ipo_budget_within_deep_dive_budget():
    assert settings.DISCOVERY_IPO_MAX_DEEP_DIVES < settings.DISCOVERY_DEEP_DIVE_COUNT


def test_switch_gap_present():
    assert settings.ADVISOR_SWITCH_CONVICTION_GAP == 0.15


def test_delivery_settings_present():
    assert settings.DELIVERY_ENABLED is True            # yaml true; base.py fallback False
    assert settings.DELIVERY_DATA_DIR == "data/delivery"
    assert settings.DELIVERY_EMAIL_ENABLED is False     # off until SMTP secrets configured
    assert settings.DELIVERY_PUSH_ENABLED is True
    assert "NIFTY 50" in settings.DELIVERY_INDEX_WATCH
    assert len(settings.DELIVERY_INDEX_WATCH) == 4


def test_delivery_secrets_are_env_only_strings():
    # Secrets default empty (they live in .env, never config.yaml)
    assert isinstance(settings.SMTP_HOST, str)
    assert isinstance(settings.SMTP_PORT, int)
    assert isinstance(settings.DELIVERY_EMAIL_TO, str)
    assert isinstance(settings.VAPID_PRIVATE_KEY, str)
    assert isinstance(settings.VAPID_PUBLIC_KEY, str)
    assert settings.VAPID_CLAIM_EMAIL  # non-empty fallback (mailto: claim needs a value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_settings.py -v`
Expected: FAIL with `AttributeError: ... no attribute 'DISCOVERY_IPO_ENABLED'`

- [ ] **Step 3: Edit config.yaml**

3a. Inside the existing `advisor:` block, after the `earnings_gap_days: 3` line, append:

```yaml
  switch_conviction_gap: 0.15    # SWITCH: shelf idea must beat holding envelope confidence by this (spec §5.2)
```

3b. Inside the existing `discovery:` block, after the `signal_weights:` mapping, append (2-space indent, same level as `enabled:`):

```yaml
  # -- Stage-2 IPO / new-listing tracker (Compass Phase C, spec §6.2) --------
  ipo_enabled: true              # base.py fallback false
  ipo_listing_window_days: 90    # listings younger than this are tracker candidates
  ipo_max_deep_dives: 2          # reserved Stage-3 slots (WITHIN deep_dive_count budget)
  ipo_lockin_warn_days: 7        # flag anchor/pre-IPO lock-in expiries within N days
  ipo_qib_weight: 3.0            # QIB subscription weighted 3x retail (spec §6.2)
```

3c. Append at the very end of config.yaml:

```yaml
# =============================================================================
# Compass Phase C — M4 proactive delivery (spec 2026-07-06 §7)
# Secrets (SMTP_*, VAPID_*, DELIVERY_EMAIL_TO) stay in .env — NEVER here.
# =============================================================================
delivery:
  enabled: true                  # master gate: scheduler Jobs 13/14 + all channel sends
  data_dir: "data/delivery"      # push_subscriptions.json, alerts_sent.jsonl
  email_enabled: false           # flip after SMTP_* secrets are set in .env / Railway
  push_enabled: true             # degrades silently until VAPID_* secrets are set
  index_watch:                   # weekly constituent diff -> inclusion/exclusion alerts
    - "NIFTY 50"
    - "NIFTY NEXT 50"
    - "NIFTY MIDCAP 150"
    - "NIFTY SMALLCAP 250"
```

- [ ] **Step 4: Edit base.py**

Append after the existing `DISCOVERY_SIGNAL_WEIGHTS` block:

```python
# ---------------------------------------------------------------------------
# Compass Phase C — IPO tracker + M4 proactive delivery (spec §6.2 / §7)
# ---------------------------------------------------------------------------
DISCOVERY_IPO_ENABLED: bool = bool(cfg("discovery.ipo_enabled", env="DISCOVERY_IPO_ENABLED", fallback=False))
DISCOVERY_IPO_LISTING_WINDOW_DAYS: int = int(cfg("discovery.ipo_listing_window_days", fallback=90))
DISCOVERY_IPO_MAX_DEEP_DIVES: int = int(cfg("discovery.ipo_max_deep_dives", fallback=2))
DISCOVERY_IPO_LOCKIN_WARN_DAYS: int = int(cfg("discovery.ipo_lockin_warn_days", fallback=7))
DISCOVERY_IPO_QIB_WEIGHT: float = float(cfg("discovery.ipo_qib_weight", fallback=3.0))

ADVISOR_SWITCH_CONVICTION_GAP: float = float(cfg("advisor.switch_conviction_gap", fallback=0.15))

DELIVERY_ENABLED: bool = bool(cfg("delivery.enabled", env="DELIVERY_ENABLED", fallback=False))
DELIVERY_DATA_DIR: str = cfg("delivery.data_dir", fallback="data/delivery")
DELIVERY_EMAIL_ENABLED: bool = bool(cfg("delivery.email_enabled", env="DELIVERY_EMAIL_ENABLED", fallback=False))
DELIVERY_PUSH_ENABLED: bool = bool(cfg("delivery.push_enabled", env="DELIVERY_PUSH_ENABLED", fallback=True))
DELIVERY_INDEX_WATCH: list[str] = list(cfg(
    "delivery.index_watch",
    fallback=["NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"],
))

# Delivery secrets — .env ONLY (never config.yaml), same pattern as OPENROUTER_API_KEY.
SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
DELIVERY_EMAIL_TO: str = os.getenv("DELIVERY_EMAIL_TO", "")
VAPID_PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY: str = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIM_EMAIL: str = os.getenv("VAPID_CLAIM_EMAIL", "admin@stockagent.app")
```

- [ ] **Step 5: Add pywebpush to requirements.txt**

After the `pyarrow>=16.0.0` line:

```text
pywebpush>=2.0.0          # M4 web-push delivery (Compass Phase C)
```

Run: `pip install pywebpush>=2.0.0`

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_delivery_settings.py tests/unit/test_discovery_settings.py tests/unit/test_portfolio_settings.py -v`
Expected: ALL PASS (neighbours unaffected)

- [ ] **Step 7: Commit**

```bash
git add config.yaml src/backend/shared/config/settings/base.py requirements.txt tests/unit/test_delivery_settings.py
git commit -m "feat(compass-c): delivery + IPO tracker + SWITCH-gap settings (Task 1)"
```

---

### Task 2: IPO / new-listing fetcher (`services/data/fetchers/ipo.py`)

**Files:**
- Create: `services/data/fetchers/ipo.py`
- Test: `tests/unit/test_ipo_fetcher.py`

**Interfaces:**
- Produces: `refresh_ipo_cache(cache_path: str | None = None) -> dict` and `load_ipo_cache(cache_path: str | None = None) -> dict`, both returning `{"fetched_at": str, "degraded": bool, "current": list[dict], "upcoming": list[dict], "past": list[dict]}` where each record is `{"symbol": str, "company": str, "series": str, "listing_date": str(ISO or ""), "issue_price": float | None, "qib_x": float | None, "retail_x": float | None, "total_x": float | None, "status": "current"|"upcoming"|"past"}`. SME records dropped unless `DISCOVERY_INCLUDE_SME`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ipo_fetcher.py
"""Compass Phase C — IPO feed fetcher: normalization + degraded mode (spec §6.2/§8)."""
import json

import services.data.fetchers.ipo as ipo_mod
from services.data.fetchers.ipo import load_ipo_cache, refresh_ipo_cache


class _FakeNSE:
    def __init__(self, past=None, current=None, upcoming=None, fail=False):
        self._past, self._current, self._upcoming = past or [], current or [], upcoming or []
        self._fail = fail

    def listPastIPO(self, from_date=None, to_date=None):
        if self._fail:
            raise RuntimeError("NSE 403")
        return self._past

    def listCurrentIPO(self):
        if self._fail:
            raise RuntimeError("NSE 403")
        return self._current

    def listUpcomingIPO(self):
        if self._fail:
            raise RuntimeError("NSE 403")
        return self._upcoming

    def exit(self):
        pass


_PAST_ROW = {
    "symbol": "NEWCO", "companyName": "NewCo Ltd", "series": "EQ",
    "listingDate": "15-Jun-2026", "issuePrice": "300 to 315",
    "qibSubscriptionTimes": "45.2", "retailSubscriptionTimes": "8.1",
    "noOfTimesSubscribed": "22.7",
}
_SME_ROW = {
    "symbol": "TINYCO", "companyName": "Tiny SME Ltd", "series": "SM",
    "listingDate": "20-Jun-2026", "issuePrice": "60",
}


def test_refresh_normalizes_and_excludes_sme(tmp_path, monkeypatch):
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(past=[_PAST_ROW, _SME_ROW],
                                         upcoming=[{"symbol": "SOON", "companyName": "Soon Ltd",
                                                    "series": "EQ", "issuePrice": "100"}]))
    result = refresh_ipo_cache(cache_path=cache)
    assert result["degraded"] is False
    past_syms = [r["symbol"] for r in result["past"]]
    assert past_syms == ["NEWCO"]                    # SME row dropped
    rec = result["past"][0]
    assert rec["listing_date"] == "2026-06-15"       # NSE date parsed to ISO
    assert rec["issue_price"] == 315.0               # upper band of "300 to 315"
    assert rec["qib_x"] == 45.2 and rec["retail_x"] == 8.1
    assert rec["status"] == "past"
    assert result["upcoming"][0]["status"] == "upcoming"


def test_degraded_mode_keeps_stale_cache(tmp_path, monkeypatch):
    cache = str(tmp_path / "ipo.json")
    (tmp_path / "ipo.json").write_text(json.dumps({
        "fetched_at": "old", "degraded": False,
        "current": [], "upcoming": [],
        "past": [{"symbol": "OLDCO", "company": "Old Co", "series": "EQ",
                  "listing_date": "2026-05-01", "issue_price": 100.0,
                  "qib_x": None, "retail_x": None, "total_x": None, "status": "past"}],
    }), encoding="utf-8")
    monkeypatch.setattr(ipo_mod, "_make_nse_client", lambda: _FakeNSE(fail=True))
    result = refresh_ipo_cache(cache_path=cache)
    assert result["degraded"] is True
    assert result["past"][0]["symbol"] == "OLDCO"    # stale kept


def test_missing_subscription_fields_are_none(tmp_path, monkeypatch):
    cache = str(tmp_path / "ipo.json")
    row = dict(_PAST_ROW)
    for k in ("qibSubscriptionTimes", "retailSubscriptionTimes", "noOfTimesSubscribed"):
        row.pop(k)
    monkeypatch.setattr(ipo_mod, "_make_nse_client", lambda: _FakeNSE(past=[row]))
    rec = refresh_ipo_cache(cache_path=cache)["past"][0]
    assert rec["qib_x"] is None and rec["retail_x"] is None and rec["total_x"] is None


def test_load_missing_cache_returns_empty_degraded(tmp_path):
    out = load_ipo_cache(cache_path=str(tmp_path / "nope.json"))
    assert out == {"fetched_at": "", "degraded": True,
                   "current": [], "upcoming": [], "past": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.data.fetchers.ipo'`

- [ ] **Step 3: Write the fetcher**

```python
# services/data/fetchers/ipo.py
"""
Compass Phase C — NSE IPO / new-listing feed (spec §6.2).

Wraps the nse pkg's listCurrentIPO / listUpcomingIPO / listPastIPO. Field
names vary across NSE report vintages, so every field is resolved through
candidate-key tuples (same defensive pattern as bulk_block.py). Subscription
breakdown (QIB / retail ×) is OPTIONAL — records without it carry None and
downstream scoring renormalizes (dark-signal pattern, spec §8).

Degraded mode: on any fetch failure the previous cache is kept and flagged
degraded — no feed is a single point of failure.
"""
from __future__ import annotations

import json
import logging
import pathlib
import re
import tempfile
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/ipo.json"
_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")
_PAST_WINDOW_DAYS = 120          # fetch a little beyond the 90d tracker window

_SYMBOL_KEYS = ("symbol", "sym", "SYMBOL")
_COMPANY_KEYS = ("companyName", "company", "issuerCompany", "COMPANY_NAME")
_SERIES_KEYS = ("series", "SERIES")
_LISTING_DATE_KEYS = ("listingDate", "listing_date", "dateOfListing", "listingDt")
_ISSUE_PRICE_KEYS = ("issuePrice", "issue_price", "finalIssuePrice", "priceBand", "issuePriceBand")
_QIB_KEYS = ("qibSubscriptionTimes", "qibTimes", "qib")
_RETAIL_KEYS = ("retailSubscriptionTimes", "riiTimes", "retail")
_TOTAL_SUB_KEYS = ("noOfTimesSubscribed", "totalSubscriptionTimes", "subscriptionTimes")
_SME_SERIES = {"SM", "ST", "SME"}


def _make_nse_client():
    """Isolated factory so tests can monkeypatch it."""
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _first(item: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _parse_date(raw: str) -> str:
    for fmt in _NSE_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _parse_price(raw: str) -> float | None:
    """'315' -> 315.0; '300 to 315' / '₹300-315' -> 315.0 (upper band)."""
    nums = re.findall(r"\d+(?:\.\d+)?", raw.replace(",", ""))
    return float(nums[-1]) if nums else None


def _parse_x(raw: str) -> float | None:
    nums = re.findall(r"\d+(?:\.\d+)?", raw.replace(",", ""))
    return float(nums[0]) if nums else None


def _normalise(rows: list, status: str) -> list[dict]:
    from core.config import settings
    out: list[dict] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        symbol = _first(item, _SYMBOL_KEYS).upper()
        if not symbol:
            continue
        series = _first(item, _SERIES_KEYS).upper()
        if series in _SME_SERIES and not settings.DISCOVERY_INCLUDE_SME:
            continue                                     # spec §6.2: SME excluded
        out.append({
            "symbol": symbol,
            "company": _first(item, _COMPANY_KEYS),
            "series": series,
            "listing_date": _parse_date(_first(item, _LISTING_DATE_KEYS)),
            "issue_price": _parse_price(_first(item, _ISSUE_PRICE_KEYS)),
            "qib_x": _parse_x(_first(item, _QIB_KEYS)),
            "retail_x": _parse_x(_first(item, _RETAIL_KEYS)),
            "total_x": _parse_x(_first(item, _TOTAL_SUB_KEYS)),
            "status": status,
        })
    return out


def load_ipo_cache(cache_path: str | None = None) -> dict:
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    if not path.exists():
        return {"fetched_at": "", "degraded": True,
                "current": [], "upcoming": [], "past": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("[ipo] cache unreadable %s: %s", path, exc)
        return {"fetched_at": "", "degraded": True,
                "current": [], "upcoming": [], "past": []}


def refresh_ipo_cache(cache_path: str | None = None) -> dict:
    """Fetch current + upcoming + past-120d IPO lists. Never raises."""
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    previous = load_ipo_cache(cache_path=str(path))

    degraded = False
    current: list[dict] = []
    upcoming: list[dict] = []
    past: list[dict] = []
    try:
        nse = _make_nse_client()
        try:
            todate = datetime.now()
            fromdate = todate - timedelta(days=_PAST_WINDOW_DAYS)
            past = _normalise(nse.listPastIPO(fromdate, todate), "past")
            current = _normalise(nse.listCurrentIPO(), "current")
            upcoming = _normalise(nse.listUpcomingIPO(), "upcoming")
        finally:
            try:
                nse.exit()
            except Exception:
                pass
    except Exception as exc:
        logger.warning("[ipo] fetch failed — keeping stale cache: %s", exc)
        degraded = True
        current = list(previous.get("current", []))
        upcoming = list(previous.get("upcoming", []))
        past = list(previous.get("past", []))

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "degraded": degraded,
        "current": current, "upcoming": upcoming, "past": past,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[ipo] cache write failed %s: %s", path, exc)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add services/data/fetchers/ipo.py tests/unit/test_ipo_fetcher.py
git commit -m "feat(compass-c): NSE IPO feed fetcher with degraded-mode cache (Task 2)"
```

---

### Task 3: IPO tracker — scoring + lock-in calendar (`core/discovery/ipo_tracker.py`)

**Files:**
- Create: `core/discovery/ipo_tracker.py`
- Modify: `src/backend/shared/schemas/discovery.py` (append `LockinEvent`)
- Test: `tests/unit/test_ipo_tracker.py`

**Interfaces:**
- Consumes: `load_ipo_cache()` (Task 2), `EodStore.load_window(end, sessions)` (columns `symbol, series, date, close, traded_value_cr, delivery_pct`), `services.data.fetchers.bulk_block.load_bulk_block` + `net_accumulation`.
- Produces: `build_ipo_candidates(on: date, window: pd.DataFrame | None = None, cache: dict | None = None) -> list[DiscoveryCandidate]` (flags include `"ipo"`; `signal_ranks` carries the sub-scores), `lockin_events(symbol: str, listing_date: date) -> list[LockinEvent]`, `upcoming_lockin_alerts(on: date, symbols: set[str] | None = None, cache: dict | None = None) -> list[LockinEvent]`. Schema: `LockinEvent(symbol, expiry: ISO str, kind: Literal["anchor_50pct","anchor_remaining","pre_ipo_6mo"])`.

- [ ] **Step 1: Append `LockinEvent` to `src/backend/shared/schemas/discovery.py`**

```python
class LockinEvent(BaseModel):
    """One IPO lock-in expiry cliff (spec §6.2: supply risk — flag, don't buy into)."""
    symbol: str
    expiry: str                            # ISO date
    kind: Literal["anchor_50pct", "anchor_remaining", "pre_ipo_6mo"]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_ipo_tracker.py
"""Compass Phase C — IPO tracker scoring, guards, lock-in calendar (spec §6.2)."""
from datetime import date

import pandas as pd

import core.discovery.ipo_tracker as it
from backend.shared.schemas.discovery import DiscoveryCandidate
from core.discovery.ipo_tracker import (
    build_ipo_candidates,
    lockin_events,
    upcoming_lockin_alerts,
)


def _no_bulk(monkeypatch):
    """Isolate from the real data/market_cache/bulk_block.json."""
    monkeypatch.setattr(it, "load_bulk_block", lambda: {"deals": []})


def _window(symbol="NEWCO", sessions=10, close=350.0, traded_cr=8.0,
            deliv_last5=55.0, deliv_prior=35.0, series="EQ"):
    rows = []
    days = pd.bdate_range(end="2026-07-03", periods=sessions)
    for i, d in enumerate(days):
        deliv = deliv_last5 if i >= sessions - 5 else deliv_prior
        rows.append({
            "symbol": symbol, "series": series, "date": d.date().isoformat(),
            "prev_close": close, "open": close, "high": close, "low": close,
            "close": close, "volume": 1_000_000,
            "traded_value_cr": traded_cr, "delivery_qty": 500_000,
            "delivery_pct": deliv,
        })
    return pd.DataFrame(rows)


def _cache(listing="2026-06-20", issue=315.0, qib=45.0, retail=8.0):
    return {"fetched_at": "x", "degraded": False, "current": [], "upcoming": [],
            "past": [{"symbol": "NEWCO", "company": "NewCo Ltd", "series": "EQ",
                      "listing_date": listing, "issue_price": issue,
                      "qib_x": qib, "retail_x": retail, "total_x": 22.0,
                      "status": "past"}]}


def test_candidate_built_with_ipo_flag_and_subscores(monkeypatch):
    _no_bulk(monkeypatch)
    cands = build_ipo_candidates(date(2026, 7, 4), window=_window(), cache=_cache())
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c, DiscoveryCandidate)
    assert c.symbol == "NEWCO" and "ipo" in c.flags
    assert 0.0 <= c.composite <= 1.0
    # +11% over issue, delivery surging, strong QIB -> healthy composite
    assert c.composite > 0.5
    assert set(c.signal_ranks) >= {"listing_evidence", "delivery_trend", "subscription"}


def test_missing_subscription_renormalizes_not_zeroes(monkeypatch):
    _no_bulk(monkeypatch)
    cache = _cache(qib=None, retail=None)
    c = build_ipo_candidates(date(2026, 7, 4), window=_window(), cache=cache)[0]
    assert "subscription_dark" in c.flags
    assert c.composite > 0.4          # evidence-only score, not dragged to 0


def test_guards_price_liquidity_sessions(monkeypatch):
    _no_bulk(monkeypatch)
    # penny price rejected
    assert build_ipo_candidates(
        date(2026, 7, 4), window=_window(close=15.0), cache=_cache(issue=14.0)) == []
    # illiquid rejected
    assert build_ipo_candidates(
        date(2026, 7, 4), window=_window(traded_cr=1.0), cache=_cache()) == []
    # too few sessions rejected
    assert build_ipo_candidates(
        date(2026, 7, 4), window=_window(sessions=3), cache=_cache()) == []


def test_old_listing_outside_window_excluded(monkeypatch):
    _no_bulk(monkeypatch)
    cands = build_ipo_candidates(
        date(2026, 7, 4), window=_window(), cache=_cache(listing="2026-01-05"))
    assert cands == []


def test_lockin_calendar_and_warn_window():
    evs = lockin_events("NEWCO", date(2026, 6, 20))
    assert [(e.kind, e.expiry) for e in evs] == [
        ("anchor_50pct", "2026-07-20"),
        ("anchor_remaining", "2026-09-18"),
        ("pre_ipo_6mo", "2026-12-17"),
    ]
    # 2026-07-14 -> anchor_50pct on 07-20 is 6 days out (warn window 7)
    alerts = upcoming_lockin_alerts(date(2026, 7, 14), cache=_cache())
    assert [a.kind for a in alerts] == ["anchor_50pct"]
    # symbol filter
    assert upcoming_lockin_alerts(date(2026, 7, 14), symbols={"OTHER"}, cache=_cache()) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.discovery.ipo_tracker'`

- [ ] **Step 4: Write the tracker**

```python
# core/discovery/ipo_tracker.py
"""
Compass Phase C — Stage-2 IPO / new-listing tracker (spec §6.2).

Research-calibrated: oversubscription != performance, so post-listing
EVIDENCE outweighs subscription froth. Sub-scores (each 0-1, renormalized
over what's available — dark-signal pattern):

  listing_evidence 0.40  last close vs issue price (fallback: first cached close)
  delivery_trend   0.20  mean delivery% last 5 sessions vs prior sessions
  bulk_accum       0.15  net same-side bulk/block accumulation > 0
  subscription     0.25  (qib_weight*qib_x + retail_x)/(qib_weight+1), capped at 50x

Guards (before scoring): >=5 sessions on the tape, close >= DISCOVERY_MIN_PRICE,
median traded value >= DISCOVERY_LIQUIDITY_FLOOR_CR, EQ series only.
Lock-in cliffs (SEBI 2022): anchor 50% at 30d, remainder at 90d, pre-IPO at
180d — flags/alerts only, never buy signals.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from core.config import settings
from backend.shared.schemas.discovery import DiscoveryCandidate, LockinEvent
from services.data.fetchers.bulk_block import load_bulk_block, net_accumulation
from services.data.fetchers.ipo import load_ipo_cache

logger = logging.getLogger(__name__)

_LOCKIN_OFFSETS: tuple[tuple[int, str], ...] = (
    (30, "anchor_50pct"),
    (90, "anchor_remaining"),
    (180, "pre_ipo_6mo"),
)
_MIN_SESSIONS = 5
_SUB_WEIGHTS = {"listing_evidence": 0.40, "delivery_trend": 0.20,
                "bulk_accum": 0.15, "subscription": 0.25}
_SUBSCRIPTION_CAP_X = 50.0


def lockin_events(symbol: str, listing_date: date) -> list[LockinEvent]:
    return [
        LockinEvent(symbol=symbol,
                    expiry=(listing_date + timedelta(days=days)).isoformat(),
                    kind=kind)
        for days, kind in _LOCKIN_OFFSETS
    ]


def _recent_listings(cache: dict, on: date) -> list[dict]:
    out = []
    for rec in cache.get("past", []):
        raw = rec.get("listing_date") or ""
        try:
            listed = date.fromisoformat(raw)
        except ValueError:
            continue
        age = (on - listed).days
        if 0 <= age <= settings.DISCOVERY_IPO_LISTING_WINDOW_DAYS:
            out.append({**rec, "_listed": listed})
    return out


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def build_ipo_candidates(
    on: date,
    window: pd.DataFrame | None = None,
    cache: dict | None = None,
) -> list[DiscoveryCandidate]:
    """Recent listings -> guarded, scored DiscoveryCandidates (flags=['ipo']).
    Never raises; empty list on any total failure."""
    try:
        cache = cache or load_ipo_cache()
        listings = _recent_listings(cache, on)
        if not listings:
            return []
        if window is None:
            from services.data.stores.eod_store import EodStore
            window = EodStore().load_window(end=on, sessions=90)
        try:
            bulk_net = net_accumulation(load_bulk_block())
        except Exception:
            bulk_net = {}

        out: list[DiscoveryCandidate] = []
        for rec in listings:
            sym = rec["symbol"]
            sw = window[(window["symbol"] == sym) & (window["series"] == "EQ")] \
                .sort_values("date")
            if len(sw) < _MIN_SESSIONS:
                continue
            close = float(sw["close"].iloc[-1])
            if close < settings.DISCOVERY_MIN_PRICE:
                continue
            if float(sw["traded_value_cr"].median()) < settings.DISCOVERY_LIQUIDITY_FLOOR_CR:
                continue

            flags = ["ipo"]
            scores: dict[str, float] = {}

            # listing evidence: % over issue price (fallback: first cached close)
            base = rec.get("issue_price") or float(sw["close"].iloc[0])
            if base and base > 0:
                ret_pct = (close / base - 1.0) * 100.0
                scores["listing_evidence"] = _clip01(0.5 + ret_pct / 50.0)

            # delivery trend: last-5 mean vs prior mean (percentage points)
            deliv = sw["delivery_pct"].dropna()
            if len(deliv) >= _MIN_SESSIONS:
                last5 = float(deliv.tail(5).mean())
                prior = float(deliv.iloc[:-5].mean()) if len(deliv) > 5 else last5
                scores["delivery_trend"] = _clip01(0.5 + (last5 - prior) / 20.0)

            # institutional adds via bulk/block net accumulation
            scores["bulk_accum"] = 1.0 if bulk_net.get(sym, 0.0) > 0 else 0.0

            # subscription: QIB weighted 3x retail (spec §6.2); optional
            qib, retail = rec.get("qib_x"), rec.get("retail_x")
            if qib is not None and retail is not None:
                w = settings.DISCOVERY_IPO_QIB_WEIGHT
                blended = (w * float(qib) + float(retail)) / (w + 1.0)
                scores["subscription"] = _clip01(blended / _SUBSCRIPTION_CAP_X)
            else:
                flags.append("subscription_dark")

            live_w = {k: _SUB_WEIGHTS[k] for k in scores}
            total_w = sum(live_w.values()) or 1.0
            composite = sum(scores[k] * live_w[k] for k in scores) / total_w

            if any(0 <= (date.fromisoformat(e.expiry) - on).days
                   <= settings.DISCOVERY_IPO_LOCKIN_WARN_DAYS
                   for e in lockin_events(sym, rec["_listed"])):
                flags.append("lockin_upcoming")

            out.append(DiscoveryCandidate(
                symbol=sym, close=close, composite=round(composite, 4),
                signal_ranks={k: round(v, 4) for k, v in scores.items()},
                flags=flags,
            ))
        return sorted(out, key=lambda c: c.composite, reverse=True)
    except Exception as exc:
        logger.warning("[ipo_tracker] build failed (non-fatal): %s", exc)
        return []


def upcoming_lockin_alerts(
    on: date, symbols: set[str] | None = None, cache: dict | None = None
) -> list[LockinEvent]:
    """Lock-in expiries within DISCOVERY_IPO_LOCKIN_WARN_DAYS of `on`, optionally
    filtered to a symbol set (held + watchlist + shelf). Never raises."""
    try:
        cache = cache or load_ipo_cache()
        alerts: list[LockinEvent] = []
        for rec in _recent_listings(cache, on) + [
            {**r, "_listed": date.fromisoformat(r["listing_date"])}
            for r in cache.get("past", [])
            if r.get("listing_date")
            and 0 <= (on - date.fromisoformat(r["listing_date"])).days <= 200
            and (on - date.fromisoformat(r["listing_date"])).days
            > settings.DISCOVERY_IPO_LISTING_WINDOW_DAYS
        ]:
            sym = rec["symbol"]
            if symbols is not None and sym not in symbols:
                continue
            for ev in lockin_events(sym, rec["_listed"]):
                days_out = (date.fromisoformat(ev.expiry) - on).days
                if 0 <= days_out <= settings.DISCOVERY_IPO_LOCKIN_WARN_DAYS:
                    alerts.append(ev)
        # dedupe (recent+older scan can overlap on window boundary)
        seen: set[tuple[str, str, str]] = set()
        unique = []
        for a in alerts:
            key = (a.symbol, a.expiry, a.kind)
            if key not in seen:
                seen.add(key)
                unique.append(a)
        return sorted(unique, key=lambda a: a.expiry)
    except Exception as exc:
        logger.warning("[ipo_tracker] lockin scan failed (non-fatal): %s", exc)
        return []
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_ipo_tracker.py -v`
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add core/discovery/ipo_tracker.py src/backend/shared/schemas/discovery.py tests/unit/test_ipo_tracker.py
git commit -m "feat(compass-c): IPO tracker — evidence-weighted scoring + lock-in calendar (Task 3)"
```

---

### Task 4: IPO stage in the weekly discovery cycle

**Files:**
- Modify: `core/discovery/__init__.py`
- Modify: `core/discovery/deep_dive.py` (duplicate-symbol guard, ~line 118)
- Test: `tests/unit/test_discovery_cycle_ipo.py`

**Interfaces:**
- Consumes: `refresh_ipo_cache` (Task 2), `build_ipo_candidates` (Task 3).
- Produces: `run_discovery_cycle()` result dict gains `"ipo_candidates": int`; IPO candidates occupy at most `DISCOVERY_IPO_MAX_DEEP_DIVES` of the existing `DISCOVERY_DEEP_DIVE_COUNT` budget (prepended to the ranked screen candidates). `core.discovery` re-exports `refresh_ipo_cache` and `build_ipo_candidates` (tests patch them THERE).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_discovery_cycle_ipo.py
"""Compass Phase C — IPO stage merged into the weekly discovery cycle."""
from datetime import date
from unittest.mock import patch

from backend.shared.schemas.discovery import DiscoveryCandidate, ScreenResult
import core.discovery as disc


def _screen(n=3):
    return ScreenResult(
        screen_date="2026-07-04", universe_size=2000, shortlist_size=80,
        candidates=[DiscoveryCandidate(symbol=f"SCR{i}", close=100.0, composite=0.9 - i * 0.1)
                    for i in range(n)],
    )


def _ipo_cands(n=2):
    return [DiscoveryCandidate(symbol=f"IPO{i}", close=300.0,
                               composite=0.8 - i * 0.1, flags=["ipo"])
            for i in range(n)]


@patch.object(disc, "run_paper_reviews", return_value={"reviewed": [], "failed": [], "skipped": []})
@patch.object(disc, "run_deep_dives", return_value=[])
@patch.object(disc, "run_screen", return_value=_screen())
@patch.object(disc, "build_ipo_candidates", return_value=_ipo_cands())
@patch.object(disc, "refresh_ipo_cache", return_value={"degraded": False})
@patch.object(disc, "refresh_bulk_block", return_value={})
@patch.object(disc, "sync_recent", return_value={})
def test_ipo_candidates_prepended_within_budget(
        m_sync, m_bulk, m_ipo_refresh, m_ipo_build, m_screen, m_dives, m_paper, monkeypatch):
    monkeypatch.setattr(disc.settings, "DISCOVERY_IPO_ENABLED", True)
    monkeypatch.setattr(disc.settings, "DISCOVERY_IPO_MAX_DEEP_DIVES", 2)
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert result["ipo_candidates"] == 2
    passed = m_dives.call_args.args[0]
    assert [c.symbol for c in passed[:2]] == ["IPO0", "IPO1"]    # prepended
    assert [c.symbol for c in passed[2:]] == ["SCR0", "SCR1", "SCR2"]


@patch.object(disc, "run_paper_reviews", return_value={"reviewed": [], "failed": [], "skipped": []})
@patch.object(disc, "run_deep_dives", return_value=[])
@patch.object(disc, "run_screen", return_value=_screen())
@patch.object(disc, "build_ipo_candidates", side_effect=RuntimeError("boom"))
@patch.object(disc, "refresh_ipo_cache", side_effect=RuntimeError("boom"))
@patch.object(disc, "refresh_bulk_block", return_value={})
@patch.object(disc, "sync_recent", return_value={})
def test_ipo_stage_failure_is_non_fatal(
        m_sync, m_bulk, m_ipo_refresh, m_ipo_build, m_screen, m_dives, m_paper, monkeypatch):
    monkeypatch.setattr(disc.settings, "DISCOVERY_IPO_ENABLED", True)
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert result["ipo_candidates"] == 0
    assert any("ipo" in e for e in result["errors"])
    assert m_dives.called                                        # cycle continued


@patch.object(disc, "run_paper_reviews", return_value={"reviewed": [], "failed": [], "skipped": []})
@patch.object(disc, "run_deep_dives", return_value=[])
@patch.object(disc, "run_screen", return_value=_screen())
@patch.object(disc, "build_ipo_candidates", return_value=_ipo_cands())
@patch.object(disc, "refresh_ipo_cache", return_value={})
@patch.object(disc, "refresh_bulk_block", return_value={})
@patch.object(disc, "sync_recent", return_value={})
def test_ipo_stage_gated_off(
        m_sync, m_bulk, m_ipo_refresh, m_ipo_build, m_screen, m_dives, m_paper, monkeypatch):
    monkeypatch.setattr(disc.settings, "DISCOVERY_IPO_ENABLED", False)
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert result["ipo_candidates"] == 0
    assert not m_ipo_build.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_discovery_cycle_ipo.py -v`
Expected: FAIL with `AttributeError: ... 'core.discovery' has no attribute 'build_ipo_candidates'`

- [ ] **Step 3: Edit `core/discovery/__init__.py`**

3a. Add to the re-exported collaborators block (after the `run_screen` import) and to `__all__`:

```python
from core.config import settings
from core.discovery.ipo_tracker import build_ipo_candidates, upcoming_lockin_alerts
from services.data.fetchers.ipo import refresh_ipo_cache
```

```python
__all__ = [
    "run_discovery_cycle", "run_deep_dives", "run_paper_reviews",
    "run_screen", "load_latest_screen", "ShelfStore",
    "sync_recent", "refresh_bulk_block",
    "refresh_ipo_cache", "build_ipo_candidates", "upcoming_lockin_alerts",
    "settings",
]
```

3b. Inside `run_discovery_cycle`, after the `refresh_bulk_block` try/except and BEFORE `screen = run_screen(on=on)`, insert:

```python
    ipo_cands: list = []
    if getattr(settings, "DISCOVERY_IPO_ENABLED", False):
        try:
            refresh_ipo_cache()
            ipo_cands = build_ipo_candidates(on=on)[
                : settings.DISCOVERY_IPO_MAX_DEEP_DIVES]
        except Exception as exc:
            logger.warning("[discovery] ipo stage failed (non-fatal): %s", exc)
            errors.append(f"ipo failed: {exc}")
            ipo_cands = []
```

3c. Change the deep-dive call to prepend IPO candidates (same total budget):

```python
    try:
        dives = run_deep_dives(ipo_cands + screen.candidates, on=on)
```

3d. Add to the result dict (after `"candidates"`):

```python
        "ipo_candidates": len(ipo_cands),
```

- [ ] **Step 4: Add the duplicate-symbol guard in `deep_dive.py`**

In `run_deep_dives`, right after the `if cand.symbol in managed or cand.symbol in shelved:` block, insert:

```python
        if any(r.symbol == cand.symbol for r in results):
            continue        # IPO candidate may also pass the quant screen
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_discovery_cycle_ipo.py tests/unit/test_discovery_deep_dive.py tests/unit/test_scheduler_discovery_job.py -v`
Expected: ALL PASS (existing cycle/dive tests unaffected)

- [ ] **Step 6: Commit**

```bash
git add core/discovery/__init__.py core/discovery/deep_dive.py tests/unit/test_discovery_cycle_ipo.py
git commit -m "feat(compass-c): IPO stage in weekly discovery cycle, shared dive budget (Task 4)"
```

---

### Task 5: SWITCH verdict (advisor + schemas + pipeline + digest + narrator)

**Files:**
- Modify: `src/backend/shared/schemas/portfolio.py` (Verdict literal, `AdviceRecord.switch_candidate`)
- Modify: `core/portfolio/advisor.py` (`decide()` params + `_best_switch_candidate` helper)
- Modify: `core/portfolio/pipeline.py` (shelf + sector-weight context; escalation tuple)
- Modify: `core/portfolio/digest.py:38` (escalation tuple)
- Modify: `core/portfolio/narrator.py` (`_TRIGGER_TEXT` entry)
- Test: `tests/unit/test_portfolio_advisor_switch.py`

**Interfaces:**
- Consumes: `ShelfIdea` (has `symbol, sector, conviction, status`), `AdvisorSignals.confidence` / `.sector`.
- Produces: `Verdict = Literal["HOLD","ADD","TRIM","EXIT","SWITCH"]`; `AdviceRecord.switch_candidate: str = ""`; `decide(signals, holding, risk_profile, shelf_ideas: list | None = None, sector_weights: dict[str, float] | None = None)` — backward compatible (old 3-arg calls behave exactly as before). Trigger code `"switch_candidate_available"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_advisor_switch.py
"""Compass Phase C — SWITCH verdict (spec §5.2): EXIT + stronger shelf idea
in an UNDERWEIGHT sector. SWITCH is an EXIT variant — precedence unchanged,
tax logic never softens it, escalation lists include it."""
from datetime import date

from backend.shared.schemas.discovery import ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.portfolio.advisor import AdvisorSignals, decide
from core.portfolio.digest import build_digest


def _holding(symbol="OLDCO", sector="automobile"):
    return Holding(symbol=symbol, sector=sector, qty=10, avg_buy_price=100.0,
                   adj_avg_price=100.0, adj_qty=10, buy_date="2026-01-15")


def _exit_signals(confidence=0.5, sector="automobile"):
    # stop breach -> EXIT fires
    return AdvisorSignals(symbol="OLDCO", sector=sector, close=80.0,
                          atr_stop_pct=12.0, unrealised_pnl_pct=-15.0,
                          holding_age_days=100, confidence=confidence)


def _idea(symbol="NEWCO", sector="pharma", conviction=0.75):
    return ShelfIdea(symbol=symbol, sector=sector, added="2026-07-01",
                     conviction=conviction)


def test_switch_fires_on_exit_with_stronger_underweight_idea():
    rec = decide(_exit_signals(confidence=0.5), _holding(), "balanced",
                 shelf_ideas=[_idea(conviction=0.75)],
                 sector_weights={"automobile": 60.0, "pharma": 10.0})
    assert rec.verdict == "SWITCH"
    assert rec.switch_candidate == "NEWCO"
    assert "switch_candidate_available" in rec.triggers
    assert "stop_breach" in rec.triggers          # underlying EXIT trigger kept


def test_no_switch_when_gap_too_small():
    rec = decide(_exit_signals(confidence=0.70), _holding(), "balanced",
                 shelf_ideas=[_idea(conviction=0.75)],       # gap 0.05 < 0.15
                 sector_weights={"automobile": 60.0, "pharma": 10.0})
    assert rec.verdict == "EXIT" and rec.switch_candidate == ""


def test_no_switch_when_candidate_sector_not_underweight():
    rec = decide(_exit_signals(), _holding(), "balanced",
                 shelf_ideas=[_idea(sector="automobile", conviction=0.9)],
                 sector_weights={"automobile": 60.0})
    assert rec.verdict == "EXIT"                  # same-sector weight not strictly lower


def test_no_switch_without_exit():
    sig = AdvisorSignals(symbol="OLDCO", sector="automobile", close=110.0,
                         atr_stop_pct=12.0, unrealised_pnl_pct=10.0,
                         holding_age_days=100, confidence=0.5)
    rec = decide(sig, _holding(), "balanced",
                 shelf_ideas=[_idea(conviction=0.95)],
                 sector_weights={"automobile": 60.0, "pharma": 10.0})
    assert rec.verdict == "HOLD"


def test_backward_compatible_three_arg_call():
    rec = decide(_exit_signals(), _holding(), "balanced")
    assert rec.verdict == "EXIT"


def test_strongest_qualifying_idea_wins_and_dropped_ignored():
    ideas = [_idea("A", "pharma", 0.70),
             _idea("B", "fmcg", 0.85),
             ShelfIdea(symbol="C", sector="metals", added="2026-07-01",
                       conviction=0.99, status="dropped")]
    rec = decide(_exit_signals(confidence=0.5), _holding(), "balanced",
                 shelf_ideas=ideas,
                 sector_weights={"automobile": 60.0, "pharma": 5.0, "fmcg": 5.0})
    assert rec.switch_candidate == "B"


def test_switch_in_digest_escalations():
    h = _holding()
    rec = AdviceRecord(date="2026-07-09", user_id="u", symbol="OLDCO",
                       verdict="SWITCH", close=80.0, unrealised_pnl_pct=-15.0,
                       stop_pct=12.0, switch_candidate="NEWCO")
    digest = build_digest("u", date(2026, 7, 9), [rec],
                          Portfolio(user_id="u", holdings=[h]), {"OLDCO": 80.0})
    assert digest["escalations"] == ["OLDCO"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_advisor_switch.py -v`
Expected: FAIL — pydantic `ValidationError` (`SWITCH` not a valid Verdict) and `TypeError: decide() got an unexpected keyword argument 'shelf_ideas'`

- [ ] **Step 3: Edit `src/backend/shared/schemas/portfolio.py`**

```python
Verdict = Literal["HOLD", "ADD", "TRIM", "EXIT", "SWITCH"]
```

In `AdviceRecord`, after `narrative: str = ""`:

```python
    switch_candidate: str = ""     # SWITCH only: the stronger shelf idea's symbol
```

- [ ] **Step 4: Edit `core/portfolio/advisor.py`**

4a. Add the helper before `decide`:

```python
def _best_switch_candidate(signals: AdvisorSignals, shelf_ideas, sector_weights: dict):
    """SWITCH (spec §5.2): EXIT already fired AND an active shelf idea beats the
    holding's mean remaining envelope confidence by >= ADVISOR_SWITCH_CONVICTION_GAP,
    in a sector strictly UNDERWEIGHT vs the exiting holding's sector. With no
    sector-weight context every idea fails the underweight check (conservative)."""
    own_weight = sector_weights.get(signals.sector, 0.0)
    best = None
    for idea in shelf_ideas or []:
        if getattr(idea, "status", "active") != "active":
            continue
        if sector_weights.get(idea.sector, 0.0) >= own_weight:
            continue
        if idea.conviction - signals.confidence < settings.ADVISOR_SWITCH_CONVICTION_GAP:
            continue
        if best is None or idea.conviction > best.conviction:
            best = idea
    return best
```

4b. Change the `decide` signature:

```python
def decide(
    signals: AdvisorSignals,
    holding: Holding,
    risk_profile: str,
    shelf_ideas: list | None = None,
    sector_weights: dict[str, float] | None = None,
) -> AdviceRecord:
```

4c. After the precedence block (`verdict = "EXIT" / ...`) and BEFORE the LTCG softening block, insert:

```python
    # -- SWITCH: EXIT + stronger shelf idea in an underweight sector (§5.2) --
    switch_candidate = ""
    if verdict == "EXIT" and shelf_ideas:
        cand = _best_switch_candidate(signals, shelf_ideas, sector_weights or {})
        if cand is not None:
            verdict = "SWITCH"
            triggers.append("switch_candidate_available")
            switch_candidate = cand.symbol
```

4d. Add to the returned `AdviceRecord(...)`:

```python
        switch_candidate=switch_candidate,
```

(The LTCG block only touches `verdict == "TRIM"`, so SWITCH — like EXIT — is never softened; no change needed there.)

- [ ] **Step 5: Edit `core/portfolio/pipeline.py`**

5a. After `if not portfolio.holdings: continue` (before Step 2), insert:

```python
        # Phase C context for SWITCH: active shelf ideas + sector weights.
        shelf_ideas: list = []
        try:
            from core.discovery.shelf import ShelfStore
            shelf_ideas = [i for i in ShelfStore().load().ideas if i.status == "active"]
        except Exception as exc:
            logger.debug("[portfolio_pipeline] shelf unavailable (non-fatal): %s", exc)
        sector_weights: dict[str, float] = {}
        try:
            total = sum(h.adj_qty * h.adj_avg_price for h in portfolio.holdings)
            if total > 0:
                for h in portfolio.holdings:
                    sector_weights[h.sector] = sector_weights.get(h.sector, 0.0) + (
                        h.adj_qty * h.adj_avg_price / total * 100.0
                    )
        except Exception:
            pass
```

5b. Change the decide call:

```python
                rec = decide(signals, holding, portfolio.risk_profile,
                             shelf_ideas=shelf_ideas, sector_weights=sector_weights)
```

5c. Change the escalations line:

```python
        escalations.extend(a.symbol for a in advice if a.verdict in ("TRIM", "EXIT", "SWITCH"))
```

- [ ] **Step 6: Edit `core/portfolio/digest.py:38`**

```python
    escalations = sorted(a.symbol for a in advice if a.verdict in ("TRIM", "EXIT", "SWITCH"))
```

- [ ] **Step 7: Edit `core/portfolio/narrator.py` `_TRIGGER_TEXT`**

```python
    "switch_candidate_available": "a stronger discovery-shelf idea in an underweight sector is available as a replacement",
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_portfolio_advisor_switch.py tests/unit/test_portfolio_advisor.py tests/unit/test_portfolio_pipeline.py tests/unit/test_portfolio_narrator.py tests/unit/test_portfolio_schemas.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add src/backend/shared/schemas/portfolio.py core/portfolio/advisor.py core/portfolio/pipeline.py core/portfolio/digest.py core/portfolio/narrator.py tests/unit/test_portfolio_advisor_switch.py
git commit -m "feat(compass-c): SWITCH verdict — EXIT + stronger underweight shelf idea (Task 5)"
```

---

### Task 6: Delivery channels — web-push + email + subscription store (`core/delivery/channels.py`)

**Files:**
- Create: `core/delivery/__init__.py`
- Create: `core/delivery/channels.py`
- Test: `tests/unit/test_delivery_channels.py`

**Interfaces:**
- Consumes: `settings.DELIVERY_*`, `SMTP_*`, `VAPID_*` (Task 1).
- Produces: `PushStore(path: str | None = None)` with `.add(subscription: dict, user_id=None) -> int`, `.remove(endpoint: str, user_id=None) -> bool`, `.list(user_id=None) -> list[dict]`; `send_email(subject: str, body: str) -> bool`; `send_push(title: str, body: str, url="/app/index.html", user_id=None, store: PushStore | None = None) -> int`; `deliver(title: str, body: str, url="/app/index.html", user_id=None) -> dict` — never raises. Module-level `webpush`/`WebPushException` names so tests monkeypatch `channels.webpush`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_delivery_channels.py
"""Compass Phase C — M4 channels: push store, email, push fan-out (spec §7)."""
import core.delivery.channels as ch
from core.delivery.channels import PushStore, deliver, send_email, send_push

_SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
_SUB2 = {"endpoint": "https://push.example/def", "keys": {"p256dh": "k", "auth": "a"}}


def test_push_store_add_dedupe_remove(tmp_path):
    store = PushStore(path=str(tmp_path / "subs.json"))
    assert store.add(_SUB) == 1
    assert store.add(_SUB) == 1                     # same endpoint deduped
    assert store.add(_SUB2) == 2
    assert len(store.list()) == 2
    assert store.remove(_SUB["endpoint"]) is True
    assert store.remove("https://push.example/nope") is False
    assert [s["endpoint"] for s in store.list()] == [_SUB2["endpoint"]]


def test_send_email_disabled_returns_false(monkeypatch):
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", False)
    assert send_email("s", "b") is False


def test_send_email_smtp_flow(monkeypatch):
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"], sent["port"] = host, port
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            sent["tls"] = True
        def login(self, user, pwd):
            sent["login"] = user
        def sendmail(self, frm, to, msg):
            sent["to"], sent["msg"] = to, msg

    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(ch.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(ch.settings, "SMTP_USER", "u@example.com")
    monkeypatch.setattr(ch.settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "me@example.com")
    monkeypatch.setattr(ch.smtplib, "SMTP", _FakeSMTP)
    assert send_email("Subject", "Body") is True
    assert sent["to"] == ["me@example.com"] and sent["tls"] and sent["login"] == "u@example.com"


def test_send_push_fans_out_and_prunes_expired(tmp_path, monkeypatch):
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add(_SUB)
    store.add(_SUB2)
    monkeypatch.setattr(ch.settings, "DELIVERY_PUSH_ENABLED", True)
    monkeypatch.setattr(ch.settings, "VAPID_PRIVATE_KEY", "priv")

    class _Resp:
        status_code = 410

    class _Gone(Exception):
        def __init__(self):
            self.response = _Resp()

    calls = []

    def _fake_webpush(subscription_info, data, vapid_private_key, vapid_claims):
        calls.append(subscription_info["endpoint"])
        if subscription_info["endpoint"] == _SUB["endpoint"]:
            raise _Gone()

    monkeypatch.setattr(ch, "webpush", _fake_webpush)
    monkeypatch.setattr(ch, "WebPushException", _Gone)
    sent = send_push("t", "b", store=store)
    assert sent == 1 and len(calls) == 2
    assert [s["endpoint"] for s in store.list()] == [_SUB2["endpoint"]]  # 410 pruned


def test_send_push_without_vapid_key_is_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(ch.settings, "VAPID_PRIVATE_KEY", "")
    assert send_push("t", "b", store=PushStore(path=str(tmp_path / "s.json"))) == 0


def test_deliver_gated_and_never_raises(monkeypatch):
    monkeypatch.setattr(ch.settings, "DELIVERY_ENABLED", False)
    assert deliver("t", "b") == {"delivered": False, "reason": "delivery_disabled"}
    monkeypatch.setattr(ch.settings, "DELIVERY_ENABLED", True)
    monkeypatch.setattr(ch, "send_push", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(ch, "send_email", lambda *a, **k: False)
    out = deliver("t", "b")
    assert out["delivered"] is False and out["push"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_channels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.delivery'`

- [ ] **Step 3: Write the package**

```python
# core/delivery/__init__.py
"""
Compass Phase C — M4 proactive delivery (spec §7): channels (web-push +
email), deduped event alerts, morning brief, weekly review, index watch.
Everything here is non-fatal by construction — a delivery failure is
telemetry, never a pipeline error.
"""
```

```python
# core/delivery/channels.py
"""
Compass Phase C — delivery channels (spec §7).

web-push: pywebpush + VAPID keys (env secrets); subscriptions persisted in
data/delivery/push_subscriptions.json per user. Expired subscriptions
(404/410) are pruned on send. The PWA service worker displays the payload;
the TWA Android app gets it free.

email: stdlib smtplib STARTTLS fallback — single user, spec §7 "trivial SMTP".

EVERY send is non-fatal. deliver() is the only entry point callers need.
"""
from __future__ import annotations

import json
import logging
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

try:                                     # module-level so tests can monkeypatch
    from pywebpush import WebPushException, webpush
except ImportError:                      # pragma: no cover — dep is in requirements
    webpush = None
    WebPushException = Exception


class PushStore:
    """data/delivery/push_subscriptions.json — {user_id: [subscription, ...]}"""

    def __init__(self, path: str | None = None) -> None:
        if path:
            self._path = Path(path)
            self._path.parent.mkdir(parents=True, exist_ok=True)
        else:
            base = Path(settings.DELIVERY_DATA_DIR)
            base.mkdir(parents=True, exist_ok=True)
            self._path = base / "push_subscriptions.json"

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("[delivery] push store unreadable %s: %s", self._path, exc)
            return {}

    def _save(self, data: dict) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def add(self, subscription: dict, user_id: str | None = None) -> int:
        uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID
        data = self._load()
        subs = data.setdefault(uid, [])
        endpoint = subscription.get("endpoint", "")
        if endpoint and not any(s.get("endpoint") == endpoint for s in subs):
            subs.append(subscription)
            self._save(data)
        return len(subs)

    def remove(self, endpoint: str, user_id: str | None = None) -> bool:
        uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID
        data = self._load()
        subs = data.get(uid, [])
        kept = [s for s in subs if s.get("endpoint") != endpoint]
        if len(kept) == len(subs):
            return False
        data[uid] = kept
        self._save(data)
        return True

    def list(self, user_id: str | None = None) -> list[dict]:
        uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID
        return list(self._load().get(uid, []))


def send_email(subject: str, body: str) -> bool:
    """SMTP STARTTLS send to DELIVERY_EMAIL_TO. False when disabled/unconfigured
    or on any failure — never raises."""
    if not (settings.DELIVERY_EMAIL_ENABLED and settings.SMTP_HOST
            and settings.DELIVERY_EMAIL_TO):
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER or "stockagent@localhost"
        msg["To"] = settings.DELIVERY_EMAIL_TO
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.sendmail(msg["From"], [settings.DELIVERY_EMAIL_TO], msg.as_string())
        return True
    except Exception as exc:
        logger.warning("[delivery] email send failed (non-fatal): %s", exc)
        return False


def send_push(
    title: str,
    body: str,
    url: str = "/app/index.html",
    user_id: str | None = None,
    store: PushStore | None = None,
) -> int:
    """Fan one notification out to every stored subscription. Returns the
    number delivered; prunes expired (404/410) subscriptions. Never raises."""
    if not (settings.DELIVERY_PUSH_ENABLED and settings.VAPID_PRIVATE_KEY
            and webpush is not None):
        return 0
    store = store or PushStore()
    payload = json.dumps({"title": title, "body": body[:1500], "url": url})
    sent = 0
    for sub in store.list(user_id):
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_CLAIM_EMAIL}"},
            )
            sent += 1
        except Exception as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (404, 410):
                store.remove(sub.get("endpoint", ""), user_id)
                logger.info("[delivery] pruned expired push subscription (%s)", code)
            else:
                logger.warning("[delivery] push send failed (non-fatal): %s", exc)
    return sent


def deliver(
    title: str, body: str, url: str = "/app/index.html", user_id: str | None = None
) -> dict:
    """Fan one message out to all configured channels. Never raises."""
    if not settings.DELIVERY_ENABLED:
        return {"delivered": False, "reason": "delivery_disabled"}
    pushed = emailed = 0
    try:
        pushed = send_push(title, body, url=url, user_id=user_id)
    except Exception as exc:
        logger.warning("[delivery] push channel failed (non-fatal): %s", exc)
    try:
        emailed = int(send_email(title, body))
    except Exception as exc:
        logger.warning("[delivery] email channel failed (non-fatal): %s", exc)
    logger.info("[delivery] %s — push=%d email=%d", title, pushed, emailed)
    return {"delivered": bool(pushed or emailed), "push": pushed, "email": emailed}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_delivery_channels.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add core/delivery/__init__.py core/delivery/channels.py tests/unit/test_delivery_channels.py
git commit -m "feat(compass-c): delivery channels — web-push + SMTP email, non-fatal (Task 6)"
```

---

### Task 7: Alert engine + wiring into advisor pipeline and discovery cycle

**Files:**
- Create: `core/delivery/alerts.py`
- Modify: `core/portfolio/pipeline.py` (Step 5: escalation alerts + digest delivery)
- Modify: `core/discovery/__init__.py` (shelf-add alerts)
- Test: `tests/unit/test_delivery_alerts.py`

**Interfaces:**
- Consumes: `channels.deliver` (Task 6).
- Produces: `AlertEvent(BaseModel)` with `date: str, kind: str, symbol: str = "", message: str, severity: Literal["info","warning","critical"] = "info"`; `emit_alerts(events: list[AlertEvent], user_id=None, title="StockAgent alerts", sent_log: str | None = None) -> dict` (dedupe key `date|kind|symbol`, appends to `data/delivery/alerts_sent.jsonl`, ONE bundled deliver per call); `load_recent_alerts(limit=50, sent_log: str | None = None) -> list[dict]`. Alert kinds used across Phase C: `advisor_exit | advisor_trim | advisor_switch | preopen_reforecast | shelf_add | lockin_expiry | index_inclusion | index_exclusion`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_delivery_alerts.py
"""Compass Phase C — deduped alert engine (spec §7 event alerts)."""
from unittest.mock import patch

import core.delivery.alerts as al
from core.delivery.alerts import AlertEvent, emit_alerts, load_recent_alerts


def _ev(kind="advisor_exit", symbol="OLDCO", msg="stop breached"):
    return AlertEvent(date="2026-07-09", kind=kind, symbol=symbol,
                      message=msg, severity="critical")


def test_emit_delivers_once_and_dedupes(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        out1 = emit_alerts([_ev()], sent_log=log)
        out2 = emit_alerts([_ev()], sent_log=log)          # same key -> deduped
    assert out1["emitted"] == 1 and out2["emitted"] == 0
    assert m.call_count == 1
    body = m.call_args.args[1]
    assert "OLDCO" in body and "stop breached" in body


def test_emit_bundles_multiple_events_into_one_send(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    events = [_ev(), _ev(kind="shelf_add", symbol="NEWCO", msg="new idea")]
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        out = emit_alerts(events, sent_log=log)
    assert out["emitted"] == 2 and m.call_count == 1


def test_empty_or_fully_duplicate_batch_skips_delivery(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        assert emit_alerts([], sent_log=log)["emitted"] == 0
    assert m.call_count == 0


def test_load_recent_alerts_tail(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}):
        emit_alerts([_ev(symbol=f"S{i}") for i in range(5)], sent_log=log)
    recent = load_recent_alerts(limit=3, sent_log=log)
    assert len(recent) == 3
    assert recent[-1]["symbol"] == "S4"


def test_emit_never_raises_on_delivery_failure(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", side_effect=RuntimeError("channel down")):
        out = emit_alerts([_ev()], sent_log=log)
    assert out["emitted"] == 1          # logged as sent; delivery failure is telemetry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_alerts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.delivery.alerts'`

- [ ] **Step 3: Write the alert engine**

```python
# core/delivery/alerts.py
"""
Compass Phase C — event alerts (spec §7): shock reforecast on a holding,
advisor escalations, shelf adds, lock-in expiry, index reconstitution.

Dedupe: one JSONL sent-log (data/delivery/alerts_sent.jsonl), key
"{date}|{kind}|{symbol}" — re-running a pipeline the same day never
re-notifies. Emission failures are telemetry, never pipeline errors.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from core.config import settings
from core.delivery.channels import deliver

logger = logging.getLogger(__name__)

_SEVERITY_TAG = {"info": "[INFO]", "warning": "[WARN]", "critical": "[ALERT]"}


class AlertEvent(BaseModel):
    date: str                              # ISO date the event refers to
    kind: str                              # advisor_exit | shelf_add | lockin_expiry | ...
    symbol: str = ""
    message: str
    severity: Literal["info", "warning", "critical"] = "info"

    def key(self) -> str:
        return f"{self.date}|{self.kind}|{self.symbol}"


def _sent_log_path(sent_log: str | None) -> Path:
    if sent_log:
        p = Path(sent_log)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    base = Path(settings.DELIVERY_DATA_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base / "alerts_sent.jsonl"


def _seen_keys(path: Path, tail: int = 2000) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-tail:]:
            try:
                rec = json.loads(line)
                keys.add(f"{rec.get('date')}|{rec.get('kind')}|{rec.get('symbol')}")
            except Exception:
                continue
    except Exception as exc:
        logger.warning("[alerts] sent-log unreadable (non-fatal): %s", exc)
    return keys


def load_recent_alerts(limit: int = 50, sent_log: str | None = None) -> list[dict]:
    path = _sent_log_path(sent_log)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def emit_alerts(
    events: list[AlertEvent],
    user_id: str | None = None,
    title: str = "StockAgent alerts",
    sent_log: str | None = None,
) -> dict:
    """Dedupe, persist, and deliver a batch as ONE bundled message. Never raises."""
    try:
        path = _sent_log_path(sent_log)
        seen = _seen_keys(path)
        new = [e for e in events if e.key() not in seen]
        # in-batch dedupe too
        uniq: list[AlertEvent] = []
        batch_keys: set[str] = set()
        for e in new:
            if e.key() not in batch_keys:
                batch_keys.add(e.key())
                uniq.append(e)
        if not uniq:
            return {"emitted": 0}
        with open(path, "a", encoding="utf-8") as fh:
            for e in uniq:
                fh.write(e.model_dump_json() + "\n")
        body = "\n".join(
            f"{_SEVERITY_TAG[e.severity]} {e.symbol + ' — ' if e.symbol else ''}{e.message}"
            for e in uniq
        )
        try:
            deliver(title, body, user_id=user_id)
        except Exception as exc:
            logger.warning("[alerts] delivery failed (non-fatal): %s", exc)
        return {"emitted": len(uniq), "kinds": sorted({e.kind for e in uniq})}
    except Exception as exc:
        logger.warning("[alerts] emit failed (non-fatal): %s", exc)
        return {"emitted": 0, "error": str(exc)}
```

- [ ] **Step 4: Wire into `core/portfolio/pipeline.py`** — after Step 4 (digest), still inside the per-user loop, insert:

```python
        # Step 5 — Phase C M4: escalation alerts + digest delivery. Non-fatal.
        try:
            from core.delivery.alerts import AlertEvent, emit_alerts
            from core.delivery.channels import deliver
            events = [
                AlertEvent(
                    date=review_date.isoformat(),
                    kind=f"advisor_{a.verdict.lower()}",
                    symbol=a.symbol,
                    message=(a.narrative or a.verdict)
                    + (f" (switch → {a.switch_candidate})" if a.switch_candidate else ""),
                    severity="critical" if a.verdict in ("EXIT", "SWITCH") else "warning",
                )
                for a in advice if a.verdict in ("TRIM", "EXIT", "SWITCH")
            ]
            if events:
                emit_alerts(events, user_id=user_id,
                            title=f"Advisor escalations — {review_date}")
            n_esc = len(events)
            deliver(
                f"EOD digest — {review_date}",
                f"{len(advice)} holdings reviewed; {n_esc} escalation(s). "
                "Open the app or ask the chat for 'brief' for details.",
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("[portfolio_pipeline] delivery failed (non-fatal): %s", exc)
```

- [ ] **Step 5: Wire shelf adds into `core/discovery/__init__.py`** — in `run_discovery_cycle`, right after the shelf try/except (before paper reviews), insert:

```python
    try:
        if shelf_summary.get("added"):
            from core.delivery.alerts import AlertEvent, emit_alerts
            conviction = {d.symbol: d.conviction for d in dives}
            emit_alerts(
                [AlertEvent(date=on.isoformat(), kind="shelf_add", symbol=sym,
                            message=f"new discovery idea (conviction "
                                    f"{conviction.get(sym, 0.0):.2f})", severity="info")
                 for sym in shelf_summary["added"]],
                title=f"Discovery shelf — {on}",
            )
    except Exception as exc:
        logger.warning("[discovery] shelf alert emit failed (non-fatal): %s", exc)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_delivery_alerts.py tests/unit/test_portfolio_pipeline.py tests/unit/test_discovery_cycle_ipo.py -v`
Expected: ALL PASS (pipeline/cycle wiring is non-fatal, existing tests unaffected)

- [ ] **Step 7: Commit**

```bash
git add core/delivery/alerts.py core/portfolio/pipeline.py core/discovery/__init__.py tests/unit/test_delivery_alerts.py
git commit -m "feat(compass-c): deduped alert engine wired into advisor + discovery (Task 7)"
```

---

### Task 8: Morning brief builder + PortfolioStore brief persistence

**Files:**
- Create: `core/delivery/brief.py`
- Modify: `core/portfolio/store.py` (add `_briefs_dir`, `save_brief`, `load_latest_brief`)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Consumes: `PortfolioStore.load_latest_digest`, `MacroNewsCache.get_high_severity(hours_back)`, `load_events_calendar`/`next_results_event`, `upcoming_lockin_alerts` + `load_ipo_cache` (Task 3/2), shelf events JSONL, `_regime_state.json`, `is_trading_day`, `channels.deliver`, `emit_alerts`.
- Produces: `build_morning_brief(user_id: str, on: date, store: PortfolioStore | None = None) -> dict` (keys: `date, user_id, kind="morning_brief", generated_at, headline, portfolio, advisor_flags, regime, overnight, earnings_soon, discovery_adds, ipo_watch, lockin_flags`); `render_brief_text(brief: dict) -> str`; `run_morning_brief(on: date | None = None) -> dict` (skips non-trading days, iterates users, saves + delivers + emits lock-in alerts). `PortfolioStore.save_brief(brief: dict) -> Path` / `load_latest_brief() -> dict | None` (mirrors digest methods, dir `briefs/`).

- [ ] **Step 1: Add brief persistence to `core/portfolio/store.py`** — after `load_latest_digest`, insert:

```python
    # ------------------------------------------------------------------
    # Briefs + weekly reviews (Compass Phase C, M4)
    # ------------------------------------------------------------------
    def _dated_dir(self, name: str) -> Path:
        d = self._dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _load_latest_dated(self, name: str) -> dict | None:
        d = self._dir / name
        if not d.exists():
            return None
        files = sorted(d.glob("*.json"))
        if not files:
            return None
        try:
            return json.loads(files[-1].read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("[PortfolioStore] failed to read %s: %s", files[-1], exc)
            return None

    def save_brief(self, brief: dict) -> Path:
        path = self._dated_dir("briefs") / f"{brief['date']}.json"
        self._write_json(path, brief)
        return path

    def load_latest_brief(self) -> dict | None:
        return self._load_latest_dated("briefs")

    def save_weekly(self, review: dict) -> Path:
        path = self._dated_dir("weekly") / f"{review['date']}.json"
        self._write_json(path, review)
        return path

    def load_latest_weekly(self) -> dict | None:
        return self._load_latest_dated("weekly")
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_delivery_brief.py
"""Compass Phase C — morning brief: assembly, rendering, run gating (spec §7)."""
from datetime import date
from unittest.mock import patch

import core.delivery.brief as br
from core.portfolio.store import PortfolioStore


def _digest():
    return {"date": "2026-07-08", "user_id": "u1", "portfolio_value": 110000.0,
            "cost_basis": 100000.0, "total_pnl_pct": 10.0,
            "holdings": [
                {"symbol": "OLDCO", "verdict": "EXIT", "close": 80.0,
                 "pnl_pct": -15.0, "reason": "stop breached", "notes": []},
                {"symbol": "GOODCO", "verdict": "HOLD", "close": 210.0,
                 "pnl_pct": 22.0, "reason": "thesis intact", "notes": []},
            ],
            "escalations": ["OLDCO"]}


def _mk_store(tmp_path, with_digest=True):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    if with_digest:
        store.save_digest(_digest())
    return store


def test_build_brief_assembles_sections(tmp_path, monkeypatch):
    store = _mk_store(tmp_path)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "Deterministic headline.")
    monkeypatch.setattr(br, "_read_regime", lambda: {"label": "RISK_OFF"})
    monkeypatch.setattr(br, "_overnight_items", lambda: [
        {"headline": "Fed shock", "severity": "HIGH"}])
    monkeypatch.setattr(br, "_shelf_events_since", lambda since: [
        {"event": "added", "symbol": "NEWCO", "detail": "conviction=0.72"}])
    monkeypatch.setattr(br, "_earnings_soon", lambda symbols, on: [
        {"symbol": "GOODCO", "date": "2026-07-10"}])
    monkeypatch.setattr(br, "_ipo_watch", lambda: [
        {"symbol": "SOON", "company": "Soon Ltd", "status": "upcoming"}])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])

    brief = br.build_morning_brief("u1", date(2026, 7, 9), store=store)
    assert brief["kind"] == "morning_brief" and brief["date"] == "2026-07-09"
    assert brief["portfolio"]["total_pnl_pct"] == 10.0
    assert brief["advisor_flags"] == [
        {"symbol": "OLDCO", "verdict": "EXIT", "reason": "stop breached", "notes": []}]
    assert brief["regime"]["label"] == "RISK_OFF"
    assert brief["overnight"][0]["headline"] == "Fed shock"
    assert brief["discovery_adds"][0]["symbol"] == "NEWCO"
    assert brief["earnings_soon"][0]["symbol"] == "GOODCO"
    assert brief["headline"] == "Deterministic headline."

    text = br.render_brief_text(brief)
    for token in ("Deterministic headline.", "OLDCO", "EXIT", "RISK_OFF", "NEWCO"):
        assert token in text


def test_build_brief_survives_missing_everything(tmp_path, monkeypatch):
    store = _mk_store(tmp_path, with_digest=False)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "h")
    brief = br.build_morning_brief("u1", date(2026, 7, 9), store=store)
    assert brief["portfolio"] is None and brief["advisor_flags"] == []
    assert isinstance(br.render_brief_text(brief), str)


def test_run_skips_non_trading_day(monkeypatch):
    monkeypatch.setattr(br, "is_trading_day", lambda d: False)
    out = br.run_morning_brief(on=date(2026, 7, 12))
    assert out == {"status": "not_trading_day"}


def test_run_builds_saves_delivers(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "is_trading_day", lambda d: True)
    monkeypatch.setattr(br, "list_user_ids", lambda: ["u1"])
    monkeypatch.setattr(br.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    _mk_store(tmp_path)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "h")
    monkeypatch.setattr(br, "upcoming_lockin_alerts",
                        lambda on, symbols=None: [])
    with patch.object(br, "deliver", return_value={"delivered": True}) as m:
        out = br.run_morning_brief(on=date(2026, 7, 9))
    assert out["status"] == "completed" and out["users"] == 1
    assert m.call_count == 1
    saved = PortfolioStore(user_id="u1", base_dir=str(tmp_path)).load_latest_brief()
    assert saved and saved["date"] == "2026-07-09"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_brief.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.delivery.brief'`

- [ ] **Step 4: Write the brief builder**

```python
# core/delivery/brief.py
"""
Compass Phase C — Morning Brief (spec §7): 08:50 IST, right after the 08:45
pre-open shock check. Deterministic assembly from existing artifacts; ONE
BULK-tier narration call for the headline (fallback text on any failure).
Research tone, never "advice" (spec §2).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

from core.config import settings
from core.delivery.alerts import AlertEvent, emit_alerts
from core.delivery.channels import deliver
from core.discovery.ipo_tracker import upcoming_lockin_alerts
from core.intelligence.rl.nse_calendar import is_trading_day
from core.portfolio.store import PortfolioStore, list_user_ids
from services.data.fetchers.corporate_events import (
    load_events_calendar,
    next_results_event,
)
from services.data.fetchers.ipo import load_ipo_cache

logger = logging.getLogger(__name__)

_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-4 sentence morning headline (research tone; NEVER the word "advice")
summarising the portfolio state and what matters today.

Portfolio: {portfolio}
Escalations flagged yesterday: {escalations}
Market regime: {regime}
Overnight HIGH-severity items: {overnight}
Earnings within 3 sessions: {earnings}
New discovery-shelf ideas: {adds}

Respond with JSON: {{"headline": "<2-4 sentences>"}}"""


# -- section collectors (each non-fatal, monkeypatchable) -------------------

def _read_regime() -> dict | None:
    try:
        path = Path(settings.PREDICTION_DATA_DIR) / "_regime_state.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return {"label": raw.get("label", "NORMAL"),
                    "calm_streak": raw.get("calm_streak", 0)}
    except Exception as exc:
        logger.warning("[brief] regime read failed (non-fatal): %s", exc)
    return None


def _overnight_items(max_items: int = 3) -> list[dict]:
    try:
        from services.background.macro_news_cache import MacroNewsCache
        items = MacroNewsCache().get_high_severity(hours_back=24)[:max_items]
        return [{"headline": i.get("headline", ""), "severity": i.get("severity", "HIGH")}
                for i in items]
    except Exception as exc:
        logger.warning("[brief] macro feed read failed (non-fatal): %s", exc)
        return []


def _shelf_events_since(since_iso: str) -> list[dict]:
    try:
        path = Path(settings.DISCOVERY_DATA_DIR) / "shelf_events.jsonl"
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines()[-200:]:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("ts", "") >= since_iso and rec.get("event") in ("added", "promoted"):
                out.append({"event": rec["event"], "symbol": rec.get("symbol", ""),
                            "detail": rec.get("detail", "")})
        return out[-5:]
    except Exception as exc:
        logger.warning("[brief] shelf events read failed (non-fatal): %s", exc)
        return []


def _earnings_soon(symbols: list[str], on: date) -> list[dict]:
    try:
        calendar = load_events_calendar()
        out = []
        for sym in symbols:
            ev = next_results_event(sym, on, calendar)
            if ev is not None and (date.fromisoformat(ev.date) - on).days <= 3:
                out.append({"symbol": sym, "date": ev.date})
        return out
    except Exception as exc:
        logger.warning("[brief] earnings scan failed (non-fatal): %s", exc)
        return []


def _ipo_watch(max_items: int = 3) -> list[dict]:
    try:
        cache = load_ipo_cache()
        rows = cache.get("current", []) + cache.get("upcoming", [])
        return [{"symbol": r.get("symbol", ""), "company": r.get("company", ""),
                 "status": r.get("status", "")} for r in rows[:max_items]]
    except Exception as exc:
        logger.warning("[brief] ipo watch failed (non-fatal): %s", exc)
        return []


def _narrate_brief(brief: dict) -> str:
    """ONE BULK call; deterministic fallback (mirror narrator.py)."""
    fallback = _fallback_headline(brief)
    started = time.time()
    try:
        from services.clients.llm_client import (
            JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call,
            salvage_truncated_json,
        )
        p = brief.get("portfolio") or {}
        resp = get_llm_client().chat.completions.create(
            model=settings.LLM_MODEL_BULK,
            messages=[{"role": "user", "content": _PROMPT.format(
                portfolio=(f"value ₹{p.get('portfolio_value', 0):,.0f} "
                           f"({p.get('total_pnl_pct', 0.0):+.1f}%)") if p else "empty",
                escalations=", ".join(f["symbol"] for f in brief["advisor_flags"]) or "none",
                regime=(brief.get("regime") or {}).get("label", "unknown"),
                overnight="; ".join(i["headline"] for i in brief["overnight"]) or "none",
                earnings=", ".join(f"{e['symbol']} {e['date']}"
                                   for e in brief["earnings_soon"]) or "none",
                adds=", ".join(a["symbol"] for a in brief["discovery_adds"]) or "none",
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
        if not isinstance(data, dict):
            data = {}
        usage = getattr(resp, "usage", None)
        record_llm_call("morning_brief", settings.LLM_MODEL_BULK,
                        getattr(usage, "prompt_tokens", 0),
                        getattr(usage, "completion_tokens", 0),
                        int((time.time() - started) * 1000), True)
        return str(data.get("headline", "")).strip() or fallback
    except Exception as exc:
        logger.warning("[brief] narration failed (non-fatal): %s", exc)
        return fallback


def _fallback_headline(brief: dict) -> str:
    p = brief.get("portfolio") or {}
    parts = []
    if p:
        parts.append(f"Portfolio ₹{p.get('portfolio_value', 0):,.0f} "
                     f"({p.get('total_pnl_pct', 0.0):+.1f}% overall).")
    esc = [f["symbol"] for f in brief.get("advisor_flags", [])]
    if esc:
        parts.append(f"Flags to review: {', '.join(esc)}.")
    regime = (brief.get("regime") or {}).get("label")
    if regime and regime != "NORMAL":
        parts.append(f"Regime: {regime}.")
    return " ".join(parts) or "No portfolio activity to report."


# -- builder + renderer + runner --------------------------------------------

def build_morning_brief(
    user_id: str, on: date, store: PortfolioStore | None = None
) -> dict:
    store = store or PortfolioStore(user_id=user_id)
    digest = store.load_latest_digest()
    portfolio = None
    advisor_flags: list[dict] = []
    held: list[str] = []
    if digest:
        portfolio = {k: digest.get(k) for k in
                     ("date", "portfolio_value", "total_pnl_pct", "escalations")}
        portfolio["portfolio_value"] = digest.get("portfolio_value", 0.0)
        held = [r["symbol"] for r in digest.get("holdings", [])]
        advisor_flags = [
            {"symbol": r["symbol"], "verdict": r["verdict"],
             "reason": r.get("reason", ""), "notes": r.get("notes", [])}
            for r in digest.get("holdings", [])
            if r.get("verdict") not in ("HOLD", "NO_DATA")
        ]

    prev = store.load_latest_brief()
    since = prev.get("generated_at", "") if prev else ""

    # Lock-in flags cover held + watchlist + active shelf names (spec §7:
    # "lock-in expiry on shelf name").
    watched: set[str] = set(held)
    try:
        watched |= {w.symbol for w in store.load().watchlist}
    except Exception:
        pass
    try:
        from core.discovery.shelf import ShelfStore
        watched |= {i.symbol for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception as exc:
        logger.debug("[brief] shelf read for lock-in scan failed (non-fatal): %s", exc)

    brief = {
        "date": on.isoformat(),
        "user_id": user_id,
        "kind": "morning_brief",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": portfolio,
        "advisor_flags": advisor_flags,
        "regime": _read_regime(),
        "overnight": _overnight_items(),
        "earnings_soon": _earnings_soon(held, on),
        "discovery_adds": _shelf_events_since(since),
        "ipo_watch": _ipo_watch(),
        "lockin_flags": [
            e.model_dump() for e in upcoming_lockin_alerts(on, symbols=watched or None)
        ],
    }
    brief["headline"] = _narrate_brief(brief)
    return brief


def render_brief_text(brief: dict) -> str:
    lines = [f"Morning brief — {brief['date']}", brief.get("headline", ""), ""]
    p = brief.get("portfolio")
    if p:
        lines.append(f"Portfolio ₹{p.get('portfolio_value', 0):,.0f} "
                     f"({p.get('total_pnl_pct', 0.0):+.1f}%)")
    for f in brief.get("advisor_flags", []):
        lines.append(f"{f['symbol']}: {f['verdict']} — {f['reason']}")
    regime = (brief.get("regime") or {}).get("label")
    if regime:
        lines.append(f"Regime: {regime}")
    for i in brief.get("overnight", []):
        lines.append(f"Overnight: {i['headline']}")
    for e in brief.get("earnings_soon", []):
        lines.append(f"Earnings soon: {e['symbol']} on {e['date']}")
    for a in brief.get("discovery_adds", []):
        lines.append(f"Shelf {a['event']}: {a['symbol']} {a.get('detail', '')}")
    for w in brief.get("ipo_watch", []):
        lines.append(f"IPO {w['status']}: {w['symbol']} {w['company']}")
    for lf in brief.get("lockin_flags", []):
        lines.append(f"Lock-in expiry: {lf['symbol']} {lf['kind']} on {lf['expiry']}")
    return "\n".join(x for x in lines if x != "").strip()


def run_morning_brief(on: date | None = None) -> dict:
    """Scheduler Job 13 / POST /delivery/run-brief entry point. Never raises."""
    on = on or date.today()
    if not is_trading_day(on):
        return {"status": "not_trading_day"}
    users = list_user_ids() or [settings.PORTFOLIO_DEFAULT_USER_ID]
    built = 0
    for user_id in users:
        try:
            store = PortfolioStore(user_id=user_id)
            brief = build_morning_brief(user_id, on, store=store)
            store.save_brief(brief)
            deliver(f"Morning brief — {on}", render_brief_text(brief), user_id=user_id)
            if brief["lockin_flags"]:
                emit_alerts(
                    [AlertEvent(date=on.isoformat(), kind="lockin_expiry",
                                symbol=lf["symbol"],
                                message=f"{lf['kind']} lock-in expires {lf['expiry']} "
                                        "— supply risk, not a signal",
                                severity="warning")
                     for lf in brief["lockin_flags"]],
                    user_id=user_id, title=f"Lock-in expiries — {on}",
                )
            built += 1
        except Exception as exc:
            logger.warning("[brief] build failed for %s (non-fatal): %s", user_id, exc)
    return {"status": "completed", "users": built, "date": on.isoformat()}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_delivery_brief.py tests/unit/test_portfolio_store.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add core/delivery/brief.py core/portfolio/store.py tests/unit/test_delivery_brief.py
git commit -m "feat(compass-c): morning brief — deterministic assembly + BULK headline (Task 8)"
```

---

### Task 9: Weekly review builder + index-inclusion watch

**Files:**
- Create: `core/delivery/weekly.py`
- Create: `core/delivery/index_watch.py`
- Test: `tests/unit/test_delivery_weekly.py`
- Test: `tests/unit/test_index_watch.py`

**Interfaces:**
- Consumes: `PortfolioStore` (+ Task 8's `save_weekly`/`load_latest_weekly`), `EodStore.load_window`, `ShelfStore`, `channels.deliver`, `alerts.emit_alerts`, nse pkg `listEquityStocksByIndex(index) -> dict` (rows under `"data"`; the index's own summary row has `symbol == index name` — filtered out).
- Produces: `build_weekly_review(user_id: str, on: date, store=None) -> dict` (keys: `date, user_id, kind="weekly_review", generated_at, headline, allocation, concentration_flags, laggards, switch_candidates, scoreboard, paper_shelf`); `render_weekly_text(review: dict) -> str`; `run_weekly_review(on=None) -> dict`; `run_index_watch(on=None, cache_path: str | None = None) -> dict` (snapshot diff → `index_inclusion`/`index_exclusion` alerts for held/watchlist/shelf symbols; first snapshot never alerts).

- [ ] **Step 1: Write the failing weekly test**

```python
# tests/unit/test_delivery_weekly.py
"""Compass Phase C — weekly review: allocation, laggards, scoreboard (spec §7)."""
from datetime import date

import pandas as pd

import core.delivery.weekly as wk
from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.portfolio.store import PortfolioStore


def _store(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    p = store.load()
    p.holdings = [
        Holding(symbol="WINCO", sector="it_sector", qty=10, avg_buy_price=100.0,
                adj_avg_price=100.0, adj_qty=10, buy_date="2026-03-02"),
        Holding(symbol="LAGCO", sector="automobile", qty=10, avg_buy_price=200.0,
                adj_avg_price=200.0, adj_qty=10, buy_date="2026-03-02"),
    ]
    store.save(p)
    # 20-day-old EXIT advice at close 100; latest close 80 -> correct call
    store.append_advice(AdviceRecord(
        date="2026-06-15", user_id="u1", symbol="LAGCO", verdict="EXIT",
        close=100.0, unrealised_pnl_pct=-10.0, stop_pct=12.0))
    return store


def _closes():
    return {"WINCO": 130.0, "LAGCO": 80.0}


def test_build_weekly_sections(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "Weekly headline.")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    review = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)

    alloc = {a["sector"]: a["weight_pct"] for a in review["allocation"]}
    assert abs(alloc["it_sector"] - 61.90) < 0.1      # 1300 / 2100 (market value)
    assert abs(alloc["automobile"] - 38.10) < 0.1     # 800 / 2100
    # both above the 30% warn threshold; allocation is sorted by weight desc
    assert review["concentration_flags"] == ["it_sector", "automobile"]
    assert review["laggards"][0]["symbol"] == "LAGCO"
    assert review["laggards"][0]["pnl_pct"] == -60.0
    sb = review["scoreboard"]
    assert sb["counts"]["EXIT"] == 1
    assert sb["checked"] == 1 and sb["correct"] == 1  # price fell after EXIT
    assert review["headline"] == "Weekly headline."
    text = wk.render_weekly_text(review)
    assert "LAGCO" in text and "Weekly headline." in text


def test_switch_candidates_only_underweight_sectors(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())

    class _Idea:
        def __init__(self, symbol, sector, conviction):
            self.symbol, self.sector, self.conviction = symbol, sector, conviction
            self.status, self.thesis = "active", "t"
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [
        _Idea("PHARMCO", "pharma", 0.8),          # 0% weight -> underweight, offered
        _Idea("ITCO", "it_sector", 0.9),          # largest sector (61.9%) -> not offered
    ])
    review = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)
    assert [c["symbol"] for c in review["switch_candidates"]] == ["PHARMCO"]


def test_run_weekly_saves_and_delivers(tmp_path, monkeypatch):
    from unittest.mock import patch
    monkeypatch.setattr(wk, "list_user_ids", lambda: ["u1"])
    monkeypatch.setattr(wk.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    with patch.object(wk, "deliver", return_value={"delivered": True}) as m:
        out = wk.run_weekly_review(on=date(2026, 7, 5))
    assert out["status"] == "completed" and m.call_count == 1
    saved = PortfolioStore(user_id="u1", base_dir=str(tmp_path)).load_latest_weekly()
    assert saved and saved["kind"] == "weekly_review"
```

- [ ] **Step 2: Write the failing index-watch test**

```python
# tests/unit/test_index_watch.py
"""Compass Phase C — index constituent diff -> inclusion/exclusion alerts."""
import json
from datetime import date
from unittest.mock import patch

import core.delivery.index_watch as iw


class _FakeNSE:
    def __init__(self, symbols_by_index):
        self._by_index = symbols_by_index

    def listEquityStocksByIndex(self, index="NIFTY 50"):
        return {"data": [{"symbol": index}] +      # index summary row (filtered)
                        [{"symbol": s} for s in self._by_index[index]]}

    def exit(self):
        pass


def test_first_snapshot_never_alerts(tmp_path, monkeypatch):
    cache = str(tmp_path / "idx.json")
    monkeypatch.setattr(iw.settings, "DELIVERY_INDEX_WATCH", ["NIFTY 50"])
    monkeypatch.setattr(iw, "_make_nse_client",
                        lambda: _FakeNSE({"NIFTY 50": ["AAA", "BBB"]}))
    monkeypatch.setattr(iw, "_watched_symbols", lambda: {"AAA"})
    with patch.object(iw, "emit_alerts") as m:
        out = iw.run_index_watch(on=date(2026, 7, 5), cache_path=cache)
    assert out["events"] == 0 and not m.called
    assert set(json.loads(open(cache).read())["NIFTY 50"]["symbols"]) == {"AAA", "BBB"}


def test_diff_alerts_only_watched_symbols(tmp_path, monkeypatch):
    cache = str(tmp_path / "idx.json")
    (tmp_path / "idx.json").write_text(json.dumps(
        {"NIFTY 50": {"fetched_at": "old", "symbols": ["AAA", "BBB"]}}), encoding="utf-8")
    monkeypatch.setattr(iw.settings, "DELIVERY_INDEX_WATCH", ["NIFTY 50"])
    monkeypatch.setattr(iw, "_make_nse_client",
                        lambda: _FakeNSE({"NIFTY 50": ["AAA", "CCC", "DDD"]}))
    monkeypatch.setattr(iw, "_watched_symbols", lambda: {"BBB", "CCC"})
    with patch.object(iw, "emit_alerts") as m:
        out = iw.run_index_watch(on=date(2026, 7, 5), cache_path=cache)
    assert out["events"] == 2                       # CCC included, BBB excluded (DDD unwatched)
    events = m.call_args.args[0]
    kinds = {(e.symbol, e.kind) for e in events}
    assert kinds == {("CCC", "index_inclusion"), ("BBB", "index_exclusion")}


def test_fetch_failure_keeps_stale_and_no_alerts(tmp_path, monkeypatch):
    cache = str(tmp_path / "idx.json")
    (tmp_path / "idx.json").write_text(json.dumps(
        {"NIFTY 50": {"fetched_at": "old", "symbols": ["AAA"]}}), encoding="utf-8")
    monkeypatch.setattr(iw.settings, "DELIVERY_INDEX_WATCH", ["NIFTY 50"])

    def _boom():
        raise RuntimeError("NSE down")
    monkeypatch.setattr(iw, "_make_nse_client", _boom)
    with patch.object(iw, "emit_alerts") as m:
        out = iw.run_index_watch(on=date(2026, 7, 5), cache_path=cache)
    assert out["events"] == 0 and "NIFTY 50" in out["degraded"] and not m.called
    assert json.loads(open(cache).read())["NIFTY 50"]["symbols"] == ["AAA"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_delivery_weekly.py tests/unit/test_index_watch.py -v`
Expected: FAIL with `ModuleNotFoundError` for both modules

- [ ] **Step 4: Write `core/delivery/index_watch.py`**

```python
# core/delivery/index_watch.py
"""
Compass Phase C — index-inclusion watch (spec §10 Phase C row).

Weekly snapshot of DELIVERY_INDEX_WATCH constituents via the nse pkg;
diff vs the previous snapshot -> inclusion/exclusion AlertEvents for
held + watchlist + shelf symbols only. First snapshot never alerts;
per-index fetch failures keep the stale snapshot (degraded mode).
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
from datetime import date, datetime, timezone

from core.config import settings
from core.delivery.alerts import AlertEvent, emit_alerts

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/index_constituents.json"


def _make_nse_client():
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _watched_symbols() -> set[str]:
    """held + watchlist + active shelf. Never raises."""
    watched: set[str] = set()
    try:
        from core.portfolio.store import PortfolioStore, list_user_ids
        for uid in list_user_ids() or [settings.PORTFOLIO_DEFAULT_USER_ID]:
            p = PortfolioStore(user_id=uid).load()
            watched |= {h.symbol for h in p.holdings}
            watched |= {w.symbol for w in p.watchlist}
    except Exception as exc:
        logger.warning("[index_watch] portfolio read failed (non-fatal): %s", exc)
    try:
        from core.discovery.shelf import ShelfStore
        watched |= {i.symbol for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception as exc:
        logger.warning("[index_watch] shelf read failed (non-fatal): %s", exc)
    return watched


def run_index_watch(on: date | None = None, cache_path: str | None = None) -> dict:
    """Snapshot + diff + alert. Never raises."""
    on = on or date.today()
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    try:
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        cache = {}

    watched = _watched_symbols()
    events: list[AlertEvent] = []
    degraded: list[str] = []

    for index in settings.DELIVERY_INDEX_WATCH:
        try:
            nse = _make_nse_client()
            try:
                raw = nse.listEquityStocksByIndex(index)
            finally:
                try:
                    nse.exit()
                except Exception:
                    pass
            symbols = sorted({
                str(r.get("symbol", "")).upper()
                for r in (raw.get("data", []) if isinstance(raw, dict) else [])
                if str(r.get("symbol", "")).strip()
                and str(r.get("symbol", "")).upper() != index.upper()
            })
            if not symbols:
                raise ValueError("empty constituent list")
            previous = set(cache.get(index, {}).get("symbols", []))
            if previous:                       # first snapshot never alerts
                for sym in sorted((set(symbols) - previous) & watched):
                    events.append(AlertEvent(
                        date=on.isoformat(), kind="index_inclusion", symbol=sym,
                        message=f"included in {index}", severity="info"))
                for sym in sorted((previous - set(symbols)) & watched):
                    events.append(AlertEvent(
                        date=on.isoformat(), kind="index_exclusion", symbol=sym,
                        message=f"excluded from {index}", severity="warning"))
            cache[index] = {"fetched_at": datetime.now(timezone.utc).isoformat(),
                            "symbols": symbols}
        except Exception as exc:
            logger.warning("[index_watch] %s failed — keeping stale (non-fatal): %s",
                           index, exc)
            degraded.append(index)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[index_watch] cache write failed (non-fatal): %s", exc)

    if events:
        emit_alerts(events, title=f"Index reconstitution — {on}")
    return {"indices": len(settings.DELIVERY_INDEX_WATCH),
            "events": len(events), "degraded": degraded}
```

- [ ] **Step 5: Write `core/delivery/weekly.py`**

```python
# core/delivery/weekly.py
"""
Compass Phase C — Weekly Review (spec §7): Sun 18:00 IST. Allocation vs risk
profile, laggard analysis, switch candidates from the shelf, advice-ledger
scoreboard ("last month: 7/9 calls right"). Deterministic assembly; ONE
BULK-tier headline call (fallback text on failure).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone

from core.config import settings
from core.delivery.channels import deliver
from core.portfolio.store import PortfolioStore, list_user_ids

logger = logging.getLogger(__name__)

_SCOREBOARD_WINDOW_DAYS = 28
_SCOREBOARD_MIN_AGE_DAYS = 5           # advice younger than this (calendar days) isn't judged
_LAGGARD_COUNT = 3
_SWITCH_CANDIDATE_COUNT = 3

_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-4 sentence weekly portfolio review headline (research tone; NEVER
the word "advice").

Allocation: {allocation}
Concentration flags: {concentration}
Laggards: {laggards}
Advice scoreboard (last 4 weeks): {scoreboard}

Respond with JSON: {{"headline": "<2-4 sentences>"}}"""


def _latest_closes(symbols: list[str], on: date) -> dict[str, float]:
    """Last close per symbol from the EOD parquet cache. {} on failure."""
    try:
        from services.data.stores.eod_store import EodStore
        window = EodStore().load_window(end=on, sessions=10)
        out: dict[str, float] = {}
        for sym in symbols:
            sw = window[window["symbol"] == sym].sort_values("date")
            if len(sw):
                out[sym] = float(sw["close"].iloc[-1])
        return out
    except Exception as exc:
        logger.warning("[weekly] closes read failed (non-fatal): %s", exc)
        return {}


def _active_shelf_ideas() -> list:
    try:
        from core.discovery.shelf import ShelfStore
        return [i for i in ShelfStore().load().ideas if i.status == "active"]
    except Exception as exc:
        logger.warning("[weekly] shelf read failed (non-fatal): %s", exc)
        return []


def _narrate_weekly(review: dict) -> str:
    fallback = _fallback_headline(review)
    started = time.time()
    try:
        from services.clients.llm_client import (
            JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call,
            salvage_truncated_json,
        )
        sb = review["scoreboard"]
        resp = get_llm_client().chat.completions.create(
            model=settings.LLM_MODEL_BULK,
            messages=[{"role": "user", "content": _PROMPT.format(
                allocation="; ".join(f"{a['sector']} {a['weight_pct']:.0f}%"
                                     for a in review["allocation"]) or "empty",
                concentration=", ".join(review["concentration_flags"]) or "none",
                laggards="; ".join(f"{l['symbol']} {l['pnl_pct']:+.1f}%"
                                   for l in review["laggards"]) or "none",
                scoreboard=f"{sb['correct']}/{sb['checked']} judged calls right; "
                           f"counts {sb['counts']}",
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
        if not isinstance(data, dict):
            data = {}
        usage = getattr(resp, "usage", None)
        record_llm_call("weekly_review", settings.LLM_MODEL_BULK,
                        getattr(usage, "prompt_tokens", 0),
                        getattr(usage, "completion_tokens", 0),
                        int((time.time() - started) * 1000), True)
        return str(data.get("headline", "")).strip() or fallback
    except Exception as exc:
        logger.warning("[weekly] narration failed (non-fatal): %s", exc)
        return fallback


def _fallback_headline(review: dict) -> str:
    sb = review["scoreboard"]
    parts = []
    if sb["checked"]:
        parts.append(f"Last 4 weeks: {sb['correct']}/{sb['checked']} judged calls right.")
    if review["concentration_flags"]:
        parts.append("Concentration above the comfort band in: "
                     + ", ".join(review["concentration_flags"]) + ".")
    return " ".join(parts) or "Weekly review generated."


def build_weekly_review(
    user_id: str, on: date, store: PortfolioStore | None = None
) -> dict:
    store = store or PortfolioStore(user_id=user_id)
    portfolio = store.load()
    symbols = [h.symbol for h in portfolio.holdings]
    closes = _latest_closes(symbols, on)

    # allocation by sector (market value; cost fallback when no close)
    values: dict[str, float] = {}
    total = 0.0
    for h in portfolio.holdings:
        v = h.adj_qty * closes.get(h.symbol, h.adj_avg_price)
        values[h.sector] = values.get(h.sector, 0.0) + v
        total += v
    allocation = sorted(
        ({"sector": s, "weight_pct": round(v / total * 100.0, 2)}
         for s, v in values.items()),
        key=lambda a: -a["weight_pct"],
    ) if total > 0 else []
    warn = settings.ADVISOR_SECTOR_CONCENTRATION_WARN_PCT
    concentration_flags = [a["sector"] for a in allocation if a["weight_pct"] > warn]

    # laggards: bottom holdings by unrealised P&L (needs a close)
    perf = [
        {"symbol": h.symbol, "sector": h.sector,
         "pnl_pct": round(h.unrealised_pnl_pct(closes[h.symbol]), 2)}
        for h in portfolio.holdings if h.symbol in closes
    ]
    laggards = sorted(perf, key=lambda r: r["pnl_pct"])[:_LAGGARD_COUNT]

    # switch candidates: active shelf ideas in UNDERWEIGHT sectors
    sector_weights = {a["sector"]: a["weight_pct"] for a in allocation}
    max_weight = max(sector_weights.values(), default=0.0)
    switch_candidates = sorted(
        ({"symbol": i.symbol, "sector": i.sector, "conviction": i.conviction}
         for i in _active_shelf_ideas()
         if i.conviction >= settings.DISCOVERY_MIN_CONVICTION
         and sector_weights.get(i.sector, 0.0) < max_weight),
        key=lambda c: -c["conviction"],
    )[:_SWITCH_CANDIDATE_COUNT]

    # advice-ledger scoreboard (deterministic; Phase D owns real outcome RL)
    counts: dict[str, int] = {}
    checked = correct = 0
    window_start = (on - timedelta(days=_SCOREBOARD_WINDOW_DAYS)).isoformat()
    for rec in store.load_advice(limit=500):
        if rec.date < window_start or rec.date > on.isoformat():
            continue
        counts[rec.verdict] = counts.get(rec.verdict, 0) + 1
        if rec.verdict in ("HOLD",):
            continue
        age_days = (on - date.fromisoformat(rec.date)).days
        if age_days < _SCOREBOARD_MIN_AGE_DAYS:
            continue
        now = closes.get(rec.symbol)
        if now is None or rec.close <= 0:
            continue
        move = now / rec.close - 1.0
        checked += 1
        if (rec.verdict in ("EXIT", "TRIM", "SWITCH") and move < 0) or \
           (rec.verdict == "ADD" and move > 0):
            correct += 1

    review = {
        "date": on.isoformat(),
        "user_id": user_id,
        "kind": "weekly_review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "allocation": allocation,
        "concentration_flags": concentration_flags,
        "risk_profile": portfolio.risk_profile,
        "laggards": laggards,
        "switch_candidates": switch_candidates,
        "scoreboard": {"counts": counts, "checked": checked, "correct": correct},
        "paper_shelf": [
            {"symbol": i.symbol, "conviction": i.conviction,
             "last_paper_review": getattr(i, "last_paper_review", "")}
            for i in _active_shelf_ideas()
        ],
    }
    review["headline"] = _narrate_weekly(review)
    return review


def render_weekly_text(review: dict) -> str:
    lines = [f"Weekly review — {review['date']}", review.get("headline", ""), ""]
    for a in review.get("allocation", []):
        flag = "  ⚠ over-concentrated" if a["sector"] in review["concentration_flags"] else ""
        lines.append(f"{a['sector']}: {a['weight_pct']:.1f}%{flag}")
    for l in review.get("laggards", []):
        lines.append(f"Laggard: {l['symbol']} {l['pnl_pct']:+.1f}%")
    for c in review.get("switch_candidates", []):
        lines.append(f"Shelf candidate ({c['sector']}): {c['symbol']} "
                     f"conviction {c['conviction']:.2f}")
    sb = review.get("scoreboard", {})
    if sb.get("checked"):
        lines.append(f"Scoreboard: {sb['correct']}/{sb['checked']} judged calls right")
    return "\n".join(x for x in lines if x != "").strip()


def run_weekly_review(on: date | None = None) -> dict:
    """Scheduler Job 14 / POST /delivery/run-weekly entry point. Never raises."""
    on = on or date.today()
    users = list_user_ids() or [settings.PORTFOLIO_DEFAULT_USER_ID]
    built = 0
    for user_id in users:
        try:
            store = PortfolioStore(user_id=user_id)
            review = build_weekly_review(user_id, on, store=store)
            store.save_weekly(review)
            deliver(f"Weekly review — {on}", render_weekly_text(review), user_id=user_id)
            built += 1
        except Exception as exc:
            logger.warning("[weekly] build failed for %s (non-fatal): %s", user_id, exc)
    return {"status": "completed", "users": built, "date": on.isoformat()}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_delivery_weekly.py tests/unit/test_index_watch.py -v`
Expected: 6 PASS

- [ ] **Step 7: Commit**

```bash
git add core/delivery/weekly.py core/delivery/index_watch.py tests/unit/test_delivery_weekly.py tests/unit/test_index_watch.py
git commit -m "feat(compass-c): weekly review + index-inclusion watch (Task 9)"
```

---

### Task 10: Scheduler Jobs 13 + 14 and pre-open reforecast alerts

**Files:**
- Modify: `services/scheduler/python/scheduler.py`
- Test: `tests/unit/test_scheduler_delivery_jobs.py`

**Interfaces:**
- Consumes: `run_morning_brief` (Task 8), `run_weekly_review` + `run_index_watch` (Task 9), `emit_alerts` (Task 7).
- Produces: job ids `morning_brief` (Mon-Fri 08:50 IST) and `weekly_review` (Sun 18:00 IST), both gated on `settings.DELIVERY_ENABLED`; `_preopen_shock_check_job` emits `preopen_reforecast` alerts.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scheduler_delivery_jobs.py
"""Compass Phase C — scheduler Jobs 13/14 registration + preopen alert hook."""
from unittest.mock import patch

from core.config import settings
from services.scheduler.python.scheduler import AutomobileScheduler


def _job_ids(sched):
    return {j.id for j in sched._scheduler.get_jobs()}


def test_delivery_jobs_registered_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True, raising=False)
    ids = _job_ids(AutomobileScheduler())
    assert "morning_brief" in ids and "weekly_review" in ids


def test_delivery_jobs_absent_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", False, raising=False)
    ids = _job_ids(AutomobileScheduler())
    assert "morning_brief" not in ids and "weekly_review" not in ids


def test_morning_brief_cron_is_0850_ist(monkeypatch):
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True, raising=False)
    sched = AutomobileScheduler()
    job = sched._scheduler.get_job("morning_brief")
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "8" and fields["minute"] == "50"
    wk = sched._scheduler.get_job("weekly_review")
    wfields = {f.name: str(f) for f in wk.trigger.fields}
    assert wfields["day_of_week"] == "sun" and wfields["hour"] == "18"


def test_preopen_job_emits_reforecast_alerts(monkeypatch):
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True, raising=False)
    sched = AutomobileScheduler()
    result = {"severity": 0.9, "direction": "risk_off",
              "flagged": ["MARUTI"], "reforecasts": ["MARUTI"]}
    with patch("core.intelligence.rl.workflows.preopen_check.run_preopen_check",
               return_value=result), \
         patch("core.delivery.alerts.emit_alerts") as m_emit:
        sched._preopen_shock_check_job()
    assert m_emit.called
    events = m_emit.call_args.args[0]
    assert events[0].kind == "preopen_reforecast" and events[0].symbol == "MARUTI"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_scheduler_delivery_jobs.py -v`
Expected: FAIL — `morning_brief` not in job ids; emit not called

- [ ] **Step 3: Register Jobs 13 + 14 in `_build_scheduler`** — after the Job 12 block, before `return scheduler`:

```python
        # ── Job 13: Morning brief (Mon-Fri 08:50 IST — right after the 08:45
        # pre-open shock check, before the 09:15 open; spec §7 M4) ───────────
        if getattr(settings, "DELIVERY_ENABLED", False):
            scheduler.add_job(
                func=self._morning_brief_job,
                trigger=CronTrigger(
                    day_of_week="mon-fri", hour=8, minute=50, timezone="Asia/Kolkata",
                ),
                id="morning_brief",
                name="Morning brief (M4 proactive delivery)",
                misfire_grace_time=1800,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Morning brief job: weekdays at 8:50 am IST")

            # ── Job 14: Weekly review + index watch (Sun 18:00 IST) ─────────
            scheduler.add_job(
                func=self._weekly_review_job,
                trigger=CronTrigger(
                    day_of_week="sun", hour=18, minute=0, timezone="Asia/Kolkata",
                ),
                id="weekly_review",
                name="Weekly portfolio review + index watch (M4)",
                misfire_grace_time=7200,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Weekly review job: Sundays at 6:00 pm IST")
        else:
            logger.info("[Scheduler] Delivery jobs disabled (DELIVERY_ENABLED=false)")
```

- [ ] **Step 4: Add the job implementations** — after `_discovery_weekly_job`:

```python
    def _morning_brief_job(self) -> None:
        """Morning brief (spec §7): run_morning_brief() never raises and skips
        non-trading days internally."""
        from core.delivery.brief import run_morning_brief

        _job_banner("Morning Brief")
        try:
            result = run_morning_brief()
            logger.info("[Scheduler] Morning brief — %s", result)
        except Exception as exc:
            logger.error("[Scheduler] Morning brief FAILED: %s", exc, exc_info=True)
        _job_banner("Morning Brief", done=True)

    def _weekly_review_job(self) -> None:
        """Weekly review + index-constituent diff (spec §7 / §10 Phase C)."""
        from core.delivery.index_watch import run_index_watch
        from core.delivery.weekly import run_weekly_review

        _job_banner("Weekly Review + Index Watch")
        try:
            idx = run_index_watch()
            logger.info("[Scheduler] Index watch — %s", idx)
        except Exception as exc:
            logger.error("[Scheduler] Index watch FAILED: %s", exc, exc_info=True)
        try:
            result = run_weekly_review()
            logger.info("[Scheduler] Weekly review — %s", result)
        except Exception as exc:
            logger.error("[Scheduler] Weekly review FAILED: %s", exc, exc_info=True)
        _job_banner("Weekly Review + Index Watch", done=True)
```

- [ ] **Step 5: Emit alerts from the pre-open job** — in `_preopen_shock_check_job`, inside the `else:` branch after the existing `logger.info(...)` call, insert:

```python
                if result.get("reforecasts"):
                    try:
                        from datetime import date as _date
                        from core.delivery.alerts import AlertEvent, emit_alerts
                        emit_alerts(
                            [AlertEvent(
                                date=_date.today().isoformat(),
                                kind="preopen_reforecast", symbol=t,
                                message=f"overnight shock re-forecast "
                                        f"(severity {result.get('severity', 0.0):.2f}, "
                                        f"{result.get('direction', 'neutral')})",
                                severity="critical")
                             for t in result["reforecasts"]],
                            title="Pre-open shock re-forecasts",
                        )
                    except Exception as exc:
                        logger.warning(
                            "[Scheduler] preopen alert emit failed (non-fatal): %s", exc)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_scheduler_delivery_jobs.py tests/unit/test_scheduler_discovery_job.py tests/unit/test_scheduler_portfolio_hook.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add services/scheduler/python/scheduler.py tests/unit/test_scheduler_delivery_jobs.py
git commit -m "feat(compass-c): scheduler Jobs 13/14 (brief, weekly) + preopen alerts (Task 10)"
```

---

### Task 11: `/delivery/*` API routes

**Files:**
- Create: `services/api/routes/delivery_api.py`
- Modify: `services/api/server.py` (import at line ~53, mount after line 399)
- Test: `tests/unit/test_delivery_api.py`

**Interfaces:**
- Consumes: `PortfolioStore.load_latest_brief`/`load_latest_weekly` (Task 8), `run_morning_brief`/`run_weekly_review` (Tasks 8/9), `load_recent_alerts` (Task 7), `PushStore` (Task 6), `settings.VAPID_PUBLIC_KEY`.
- Produces endpoints: `GET /delivery/brief/latest`, `GET /delivery/weekly/latest`, `POST /delivery/run-brief` (202), `POST /delivery/run-weekly` (202), `GET /delivery/alerts?limit=`, `GET /delivery/push/public-key`, `POST /delivery/push/subscribe`, `DELETE /delivery/push/subscribe?endpoint=`. Auth = optional `X-Scheduler-Key` (mirrors scheduler/portfolio).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_delivery_api.py
"""Compass Phase C — /delivery/* routes."""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.api.routes.delivery_api as dapi

_SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}


def _client():
    app = FastAPI()
    app.include_router(dapi.router)
    return TestClient(app)


def test_brief_latest_404_then_200(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    c = _client()
    assert c.get("/delivery/brief/latest").status_code == 404
    from core.portfolio.store import PortfolioStore
    PortfolioStore(base_dir=str(tmp_path)).save_brief(
        {"date": "2026-07-09", "kind": "morning_brief", "headline": "h"})
    resp = c.get("/delivery/brief/latest")
    assert resp.status_code == 200 and resp.json()["date"] == "2026-07-09"


def test_weekly_latest_404(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    assert _client().get("/delivery/weekly/latest").status_code == 404


def test_run_brief_202_background():
    with patch.object(dapi, "run_morning_brief") as m:
        resp = _client().post("/delivery/run-brief")
    assert resp.status_code == 202
    assert m.called                       # TestClient runs background tasks inline


def test_run_weekly_202_background():
    with patch.object(dapi, "run_weekly_review") as m:
        resp = _client().post("/delivery/run-weekly")
    assert resp.status_code == 202 and m.called


def test_alerts_tail():
    with patch.object(dapi, "load_recent_alerts",
                      return_value=[{"kind": "shelf_add"}]) as m:
        resp = _client().get("/delivery/alerts?limit=5")
    assert resp.status_code == 200 and resp.json()["alerts"] == [{"kind": "shelf_add"}]
    assert m.call_args.kwargs.get("limit") == 5 or m.call_args.args[0] == 5


def test_push_public_key(monkeypatch):
    monkeypatch.setattr(dapi.settings, "VAPID_PUBLIC_KEY", "pubkey123")
    resp = _client().get("/delivery/push/public-key")
    assert resp.json() == {"public_key": "pubkey123"}


def test_push_subscribe_and_unsubscribe(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "DELIVERY_DATA_DIR", str(tmp_path))
    c = _client()
    resp = c.post("/delivery/push/subscribe", json=_SUB)
    assert resp.status_code == 200 and resp.json()["subscriptions"] == 1
    assert c.post("/delivery/push/subscribe", json={}).status_code == 422
    resp = c.delete("/delivery/push/subscribe",
                    params={"endpoint": _SUB["endpoint"]})
    assert resp.json()["removed"] is True


def test_auth_enforced_when_key_set(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCHEDULER_KEY", "sekret")
    c = _client()
    assert c.get("/delivery/brief/latest").status_code == 403
    assert c.get("/delivery/brief/latest",
                 headers={"X-Scheduler-Key": "sekret"}).status_code in (200, 404)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.api.routes.delivery_api'`

- [ ] **Step 3: Write the router**

```python
# services/api/routes/delivery_api.py
"""
services/api/routes/delivery_api.py
====================================
Compass Phase C — M4 delivery endpoints: latest brief / weekly review,
manual triggers, alert tail, web-push subscription management.

Auth mirrors scheduler_api (optional X-Scheduler-Key; lockdown deferred —
user decision 2026-07-06).
"""
from __future__ import annotations

import logging
import os
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from core.config import settings
from core.delivery.alerts import load_recent_alerts
from core.delivery.brief import run_morning_brief
from core.delivery.channels import PushStore
from core.delivery.weekly import run_weekly_review
from core.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/delivery", tags=["Delivery"])


def _check_auth(key: str | None) -> None:
    required = os.getenv("SCHEDULER_KEY", "")
    if required and key != required:
        raise HTTPException(status_code=403,
                            detail="Invalid or missing X-Scheduler-Key header.")
    if not required:
        logger.warning("[delivery_api] SCHEDULER_KEY not set — endpoint is open.")


@router.get("/brief/latest", summary="Latest morning brief")
async def brief_latest(
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    brief = PortfolioStore(user_id=user_id).load_latest_brief()
    if brief is None:
        raise HTTPException(status_code=404, detail="No brief yet — run POST /delivery/run-brief.")
    return brief


@router.get("/weekly/latest", summary="Latest weekly review")
async def weekly_latest(
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    review = PortfolioStore(user_id=user_id).load_latest_weekly()
    if review is None:
        raise HTTPException(status_code=404, detail="No weekly review yet — run POST /delivery/run-weekly.")
    return review


@router.post("/run-brief", status_code=202, summary="Build + deliver the morning brief now")
async def run_brief_now(
    background_tasks: BackgroundTasks,
    on: str | None = Query(default=None, description="ISO date; default today"),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    target = date.fromisoformat(on) if on else None
    background_tasks.add_task(run_morning_brief, target)
    return {"status": "accepted", "monitor": "/delivery/brief/latest"}


@router.post("/run-weekly", status_code=202, summary="Build + deliver the weekly review now")
async def run_weekly_now(
    background_tasks: BackgroundTasks,
    on: str | None = Query(default=None, description="ISO date; default today"),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    target = date.fromisoformat(on) if on else None
    background_tasks.add_task(run_weekly_review, target)
    return {"status": "accepted", "monitor": "/delivery/weekly/latest"}


@router.get("/alerts", summary="Recent emitted alerts (sent-log tail)")
async def alerts_tail(
    limit: int = Query(default=50, ge=1, le=500),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    return {"alerts": load_recent_alerts(limit=limit)}


@router.get("/push/public-key", summary="VAPID application server key for the browser")
async def push_public_key() -> dict:
    # No auth: the PUBLIC key is safe to expose; the frontend needs it pre-login.
    return {"public_key": settings.VAPID_PUBLIC_KEY}


@router.post("/push/subscribe", summary="Store a web-push subscription")
async def push_subscribe(
    subscription: dict,
    user_id: str | None = Query(default=None),
) -> dict:
    if not subscription.get("endpoint"):
        raise HTTPException(status_code=422, detail="subscription.endpoint required")
    count = PushStore().add(subscription, user_id=user_id)
    return {"status": "subscribed", "subscriptions": count}


@router.delete("/push/subscribe", summary="Remove a web-push subscription")
async def push_unsubscribe(
    endpoint: str = Query(...),
    user_id: str | None = Query(default=None),
) -> dict:
    removed = PushStore().remove(endpoint, user_id=user_id)
    return {"removed": removed}
```

- [ ] **Step 4: Mount in `services/api/server.py`**

After line 52 (`from services.api.routes.discovery_api import router as discovery_router`):

```python
from services.api.routes.delivery_api import router as delivery_router
```

After line 399 (`app.include_router(discovery_router,  tags=["Discovery"])`):

```python
app.include_router(delivery_router,   tags=["Delivery"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_delivery_api.py tests/unit/test_discovery_api.py tests/unit/test_portfolio_api.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add services/api/routes/delivery_api.py services/api/server.py tests/unit/test_delivery_api.py
git commit -m "feat(compass-c): /delivery API — brief, weekly, alerts, push subscriptions (Task 11)"
```

---

### Task 12: Chat `brief` tool (`get_portfolio_brief`)

**Files:**
- Modify: `services/api/routes/ui_data.py` (`_CHAT_TOOLS` list ~line 2160, `_dispatch_chat_tool` ~line 2630, new impl function)
- Test: `tests/unit/test_chat_brief_tool.py`

**Interfaces:**
- Consumes: `PortfolioStore.load_latest_brief`/`load_latest_digest`, `render_brief_text` (Task 8).
- Produces: chat tool `get_portfolio_brief` (no params) available in BOTH the streaming and non-streaming chat loops (they share `_CHAT_TOOLS` + `_dispatch_chat_tool`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_chat_brief_tool.py
"""Compass Phase C — chat 'brief' command (spec §7: renders the latest anytime)."""
import asyncio

from core.config import settings
from core.portfolio.store import PortfolioStore
from services.api.routes.ui_data import _CHAT_TOOLS, _dispatch_chat_tool


def _dispatch(name, args):
    return asyncio.run(_dispatch_chat_tool(name, args))


def test_tool_registered():
    names = [t["function"]["name"] for t in _CHAT_TOOLS]
    assert "get_portfolio_brief" in names


def test_returns_rendered_brief(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    PortfolioStore(base_dir=str(tmp_path)).save_brief({
        "date": "2026-07-09", "kind": "morning_brief",
        "headline": "Markets calm; no flags.",
        "portfolio": {"portfolio_value": 110000.0, "total_pnl_pct": 10.0},
        "advisor_flags": [], "overnight": [], "earnings_soon": [],
        "discovery_adds": [], "ipo_watch": [], "lockin_flags": [], "regime": None,
    })
    out = _dispatch("get_portfolio_brief", {})
    assert "Markets calm; no flags." in out and "2026-07-09" in out


def test_falls_back_to_digest_then_helpful_message(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    out = _dispatch("get_portfolio_brief", {})
    assert "No brief yet" in out
    PortfolioStore(base_dir=str(tmp_path)).save_digest({
        "date": "2026-07-08", "user_id": "primary", "portfolio_value": 90000.0,
        "total_pnl_pct": -2.0,
        "holdings": [{"symbol": "OLDCO", "verdict": "EXIT", "pnl_pct": -15.0,
                      "close": 80.0, "reason": "stop", "notes": []}],
        "escalations": ["OLDCO"]})
    out = _dispatch("get_portfolio_brief", {})
    assert "OLDCO" in out and "EXIT" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_chat_brief_tool.py -v`
Expected: FAIL — `get_portfolio_brief` not in tool names

- [ ] **Step 3: Append the tool schema to `_CHAT_TOOLS`** (before the closing `]` at line ~2161):

```python
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_brief",
            "description": (
                "The latest proactive morning brief (or EOD digest) for the user's "
                "virtual portfolio: value, P&L, per-holding verdicts, escalations, "
                "regime, discovery-shelf adds, upcoming earnings and IPO lock-in flags. "
                "Use whenever the user says 'brief', 'morning brief', 'portfolio update', "
                "'my portfolio', or asks what happened to their holdings today."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
```

- [ ] **Step 4: Add the dispatch branch** in `_dispatch_chat_tool` (with the other `if name ==` branches):

```python
    if name == "get_portfolio_brief":
        return _chat_tool_portfolio_brief()
```

- [ ] **Step 5: Add the impl function** (near the other `_chat_tool_*` helpers):

```python
def _chat_tool_portfolio_brief() -> str:
    """Latest morning brief; falls back to the latest EOD digest (Compass Phase C)."""
    try:
        from core.portfolio.store import PortfolioStore
        store = PortfolioStore()
        brief = store.load_latest_brief()
        if brief:
            from core.delivery.brief import render_brief_text
            return render_brief_text(brief)[:1800]
        digest = store.load_latest_digest()
        if digest:
            lines = [
                f"EOD digest {digest['date']} — value ₹{digest.get('portfolio_value', 0):,.0f} "
                f"({digest.get('total_pnl_pct', 0.0):+.1f}%)"
            ]
            for row in digest.get("holdings", [])[:10]:
                pnl = row.get("pnl_pct")
                pnl_s = f" ({pnl:+.1f}%)" if pnl is not None else ""
                lines.append(f"{row['symbol']}: {row['verdict']}{pnl_s} — {row.get('reason', '')}")
            return "\n".join(lines)[:1800]
        return ("No brief yet — the morning-brief job hasn't produced one. "
                "Add holdings via /portfolio, then POST /delivery/run-brief.")
    except Exception as exc:
        return f"Brief unavailable: {exc}"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_chat_brief_tool.py -v`
Expected: 3 PASS

- [ ] **Step 7: Commit**

```bash
git add services/api/routes/ui_data.py tests/unit/test_chat_brief_tool.py
git commit -m "feat(compass-c): chat get_portfolio_brief tool (Task 12)"
```

---

### Task 13: Frontend push wiring — service worker + subscribe button + VAPID keygen

**Files:**
- Modify: `src/frontend/prototypes/sw.js` (VERSION bump, `/delivery` in API_PREFIXES, push handlers)
- Modify: `src/frontend/prototypes/index.html` (subscribe helper + floating enable button)
- Create: `scripts/gen_vapid_keys.py`
- Test: `tests/unit/test_vapid_keygen.py`

**Interfaces:**
- Consumes: `GET /delivery/push/public-key`, `POST /delivery/push/subscribe` (Task 11).
- Produces: push notifications rendered by the service worker (PWA + TWA); `scripts/gen_vapid_keys.py` prints `VAPID_PRIVATE_KEY=...` / `VAPID_PUBLIC_KEY=...` lines for `.env` / Railway variables.

- [ ] **Step 1: Write the failing keygen test**

```python
# tests/unit/test_vapid_keygen.py
"""Compass Phase C — VAPID keypair generator output shape."""
import re

from scripts.gen_vapid_keys import generate_vapid_keys


def test_keys_are_base64url_no_padding():
    priv, pub = generate_vapid_keys()
    assert re.fullmatch(r"[A-Za-z0-9_-]{40,50}", priv)     # 32-byte raw key
    assert re.fullmatch(r"[A-Za-z0-9_-]{80,90}", pub)      # 65-byte uncompressed point
    assert pub[0] == "B"                                    # 0x04 prefix encodes to 'B'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_vapid_keygen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.gen_vapid_keys'`
(If `scripts/` lacks `__init__.py`, the pythonpath `["." ]` import still works as a namespace package.)

- [ ] **Step 3: Write `scripts/gen_vapid_keys.py`**

```python
"""
One-time VAPID keypair generation for web-push (Compass Phase C).

Run:  python scripts/gen_vapid_keys.py
Copy the two printed lines into .env locally AND Railway service variables.
Also set VAPID_CLAIM_EMAIL=<your email> (used in the mailto: VAPID claim).
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def generate_vapid_keys() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    priv = base64.urlsafe_b64encode(
        key.private_numbers().private_value.to_bytes(32, "big")
    ).rstrip(b"=").decode()
    pub = base64.urlsafe_b64encode(
        key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    ).rstrip(b"=").decode()
    return priv, pub


if __name__ == "__main__":
    private_key, public_key = generate_vapid_keys()
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print(f"VAPID_PUBLIC_KEY={public_key}")
```

- [ ] **Step 4: Edit `src/frontend/prototypes/sw.js`**

4a. Bump the cache version (line 9): `const VERSION = 'v2';`

4b. Add `'/delivery'` to `API_PREFIXES` (live data — never cache):

```js
const API_PREFIXES = [
  '/api', '/ui', '/analyse', '/history', '/health', '/tickers',
  '/scheduler', '/prompts', '/analytics', '/ws', '/docs', '/redoc', '/openapi.json',
  '/delivery', '/portfolio', '/discovery',
];
```

4c. Append at the end of the file:

```js
/* Compass Phase C — web-push (M4 proactive delivery).
 * Payload: {"title": ..., "body": ..., "url": ...} from core/delivery/channels.py */
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; }
  catch (e) { data = { body: event.data ? event.data.text() : '' }; }
  event.waitUntil(self.registration.showNotification(data.title || 'StockAgent', {
    body: data.body || '',
    icon: '/icons/pwa-192x192.png',
    badge: '/icons/pwa-192x192.png',
    data: { url: data.url || '/' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const w of wins) { if ('focus' in w) return w.focus(); }
      return clients.openWindow(url);
    })
  );
});
```

- [ ] **Step 5: Edit `src/frontend/prototypes/index.html`** — extend the existing `<script>` block (lines 21-29) to:

```html
<script>
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js').catch(function (e) {
        console.warn('SW registration failed', e);
      });
    });
  }

  /* Compass Phase C — web-push subscribe (M4). Self-contained: shows a small
   * floating 🔔 button until a subscription exists or permission is denied. */
  function saUrlB64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    const arr = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  async function saEnablePush() {
    const reg = await navigator.serviceWorker.ready;
    const resp = await fetch('/delivery/push/public-key');
    const { public_key } = await resp.json();
    if (!public_key) { alert('Push not configured on the server yet.'); return; }
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') return;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: saUrlB64ToUint8Array(public_key),
    });
    await fetch('/delivery/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sub.toJSON()),
    });
    const btn = document.getElementById('sa-push-btn');
    if (btn) btn.remove();
  }

  window.addEventListener('load', async function () {
    try {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
      if (Notification.permission === 'denied') return;
      const reg = await navigator.serviceWorker.ready;
      const existing = await reg.pushManager.getSubscription();
      if (existing) return;
      const btn = document.createElement('button');
      btn.id = 'sa-push-btn';
      btn.textContent = '🔔 Enable alerts';
      btn.style.cssText = 'position:fixed;bottom:76px;right:16px;z-index:9999;' +
        'padding:8px 14px;border-radius:20px;border:none;background:#6366f1;' +
        'color:#fff;font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.3);cursor:pointer;';
      btn.onclick = function () { saEnablePush().catch(console.warn); };
      document.body.appendChild(btn);
    } catch (e) { console.warn('push init failed', e); }
  });
</script>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_vapid_keygen.py -v`
Expected: 1 PASS. Then sanity-run the generator once: `python scripts/gen_vapid_keys.py` — expect two `VAPID_*=` lines (do NOT commit the values).

- [ ] **Step 7: Commit**

```bash
git add src/frontend/prototypes/sw.js src/frontend/prototypes/index.html scripts/gen_vapid_keys.py tests/unit/test_vapid_keygen.py
git commit -m "feat(compass-c): service-worker push handlers + subscribe UI + VAPID keygen (Task 13)"
```

---

### Task 14: Docs, full suite, ops runbook

**Files:**
- Modify: `CODEBASE.md` (module map, endpoints, config tables, key files, scheduler jobs line)
- Modify: `docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md` (status header)
- Test: full unit suite

**Steps:**

- [ ] **Step 1: Update CODEBASE.md**

1a. Module map: under `core/`, after the `discovery/` entry add:

```text
│   ├── delivery/                  # Compass Phase C: M4 proactive delivery (see below)
│   │   ├── channels.py            # web-push (pywebpush+VAPID) + SMTP email; PushStore
│   │   ├── alerts.py              # AlertEvent + deduped emit (alerts_sent.jsonl)
│   │   ├── brief.py               # Morning brief builder (08:50 IST job)
│   │   ├── weekly.py              # Weekly review builder (Sun 18:00 IST job)
│   │   └── index_watch.py         # Index constituent diff -> inclusion/exclusion alerts
```

Also add under `core/discovery/`: `│   │   ├── ipo_tracker.py         # Stage-2 IPO/new-listing scoring + lock-in calendar` and under fetchers: `ipo.py`.

1b. After the `core/discovery/` bullet paragraph, add:

```markdown
- `core/delivery/` — Compass Phase C: M4 proactive delivery (morning brief, weekly
  review + index watch, deduped event alerts, web-push + email channels). Jobs 13/14
  + event-triggered hooks in the advisor pipeline, pre-open check and discovery cycle.
  IPO tracker (`core/discovery/ipo_tracker.py` + `services/data/fetchers/ipo.py`)
  feeds the same Stage-3 deep-dive budget. Same spec; plan:
  docs/superpowers/plans/2026-07-09-compass-phase-c.md
```

1c. New endpoints table after the Discovery section:

```markdown
### Delivery — Compass Phase C (`/delivery/*`)

Auth mirrors the portfolio pattern (optional `X-Scheduler-Key`), except the push
endpoints (`public-key` is public by design; `subscribe` carries no secrets).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/delivery/brief/latest` | optional key | Latest morning brief (404 until one is built). |
| GET | `/delivery/weekly/latest` | optional key | Latest weekly review (404 until one is built). |
| POST | `/delivery/run-brief` | optional key | Build + deliver the morning brief now. 202, background. |
| POST | `/delivery/run-weekly` | optional key | Build + deliver the weekly review now. 202, background. |
| GET | `/delivery/alerts?limit=50` | optional key | Emitted-alert tail (deduped sent-log). |
| GET | `/delivery/push/public-key` | none | VAPID application server key for the browser. |
| POST | `/delivery/push/subscribe` | none | Store a web-push subscription (body = PushSubscription JSON). |
| DELETE | `/delivery/push/subscribe?endpoint=` | none | Remove a web-push subscription. |

Jobs: 13 `morning_brief` (Mon-Fri 08:50 IST), 14 `weekly_review` (Sun 18:00 IST) —
both gated on `delivery.enabled`. Alerts also fire event-triggered from the advisor
pipeline, the 08:45 pre-open check, and the Saturday discovery cycle.
```

1d. Config section — add after the Phase B table:

```markdown
### Delivery + IPO Tracker — Compass Phase C (`config.yaml` → `delivery.*` / `discovery.ipo_*`)

| Setting | Default | Description |
|---------|---------|-------------|
| `delivery.enabled` | `true` (base.py fallback `false`) | Master gate: Jobs 13/14 + every channel send |
| `delivery.data_dir` | `data/delivery` | `push_subscriptions.json`, `alerts_sent.jsonl` |
| `delivery.email_enabled` | `false` | Needs `SMTP_HOST/PORT/USER/PASSWORD` + `DELIVERY_EMAIL_TO` in .env |
| `delivery.push_enabled` | `true` | Needs `VAPID_PRIVATE_KEY/PUBLIC_KEY/CLAIM_EMAIL` in .env (`scripts/gen_vapid_keys.py`) |
| `delivery.index_watch` | NIFTY 50 / NEXT 50 / MIDCAP 150 / SMALLCAP 250 | Weekly constituent diff → inclusion/exclusion alerts |
| `discovery.ipo_enabled` | `true` (fallback `false`) | Stage-2 IPO tracker in the Saturday cycle |
| `discovery.ipo_listing_window_days` | `90` | Listings younger than this are candidates |
| `discovery.ipo_max_deep_dives` | `2` | Reserved Stage-3 slots (WITHIN `deep_dive_count`) |
| `discovery.ipo_lockin_warn_days` | `7` | Lock-in expiry flag window (30/90/180-day cliffs) |
| `discovery.ipo_qib_weight` | `3.0` | QIB subscription weighted 3× retail |
| `advisor.switch_conviction_gap` | `0.15` | SWITCH: shelf conviction − holding confidence floor |
```

1e. Key-file table additions:

```markdown
| `services/data/fetchers/ipo.py` | NSE IPO lists (current/upcoming/past) + degraded-mode cache |
| `core/discovery/ipo_tracker.py` | IPO candidate scoring (QIB 3×, post-listing evidence) + lock-in calendar |
| `core/delivery/channels.py` | Web-push (pywebpush + VAPID) + SMTP email; `deliver()` fan-out |
| `core/delivery/alerts.py` | Deduped alert engine (`data/delivery/alerts_sent.jsonl`) |
| `core/delivery/brief.py` | Morning brief builder/renderer/runner |
| `core/delivery/weekly.py` | Weekly review builder (allocation, laggards, scoreboard) |
| `core/delivery/index_watch.py` | Index constituent snapshot diff → alerts |
| `services/api/routes/delivery_api.py` | /delivery/* — briefs, weekly, alerts, push subscriptions |
| `scripts/gen_vapid_keys.py` | One-time VAPID keypair generation for web-push |
```

Also update the scheduler line in the key-file table to mention the morning-brief and weekly-review jobs.

- [ ] **Step 2: Update the spec status header** (line 3):

```markdown
**Status:** APPROVED — Phase A merged 2026-07-07; Phase B merged 2026-07-09; Phase C implemented (plan docs/superpowers/plans/2026-07-09-compass-phase-c.md)
```

- [ ] **Step 3: Run the FULL unit suite**

Run: `python -m pytest tests/unit -q`
Expected: baseline 1766 + ~35 new tests all passing, 5 skipped, no new failures.
Then: `python -m pytest tests/ -q --ignore=tests/contract` (integration/api layers).
Known pre-existing failures NOT to fix here: 3 in `tests/contract/test_phase0_llm_migration` (stale SignalAggregator mock target — tracked follow-up from Phase B).

- [ ] **Step 4: Commit**

```bash
git add CODEBASE.md docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md
git commit -m "docs(compass-c): register delivery + IPO tracker in CODEBASE.md; spec status -> Phase C implemented (Task 14)"
```

---

## Post-merge ops runbook (NOT part of the build — user-gated, after push to Railway)

1. `python scripts/gen_vapid_keys.py` → set `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIM_EMAIL` in Railway variables (and local `.env`).
2. (Optional email) set `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/DELIVERY_EMAIL_TO`, then flip `delivery.email_enabled: true`.
3. Still pending from Phase B: bhavcopy backfill `days_back=800` on the Railway volume (momentum dark until ≥252 sessions).
4. Open the PWA → tap "🔔 Enable alerts" → `POST /delivery/run-brief` → verify a push arrives; check `GET /delivery/alerts`.
5. First real IPO candidates + weekly review appear the following Saturday/Sunday crons.

## Execution notes

- Execute in an isolated worktree (superpowers:using-git-worktrees), branch `compass-phase-c`.
- Task order is dependency order; Tasks 2-3, 6-7 are pairwise independent of 5 (SWITCH) if parallelism is wanted, but sequential execution is fine.
- LLM calls in tests are always mocked/monkeypatched — no OpenRouter spend during the build.






