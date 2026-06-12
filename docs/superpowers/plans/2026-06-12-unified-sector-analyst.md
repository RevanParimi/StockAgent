# Unified Sector Analyst Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the automobile sector's 9 parallel agent LLM calls with one shared data-fetch pass + one reasoning-model call, preserving FinalReport and all RL contracts byte-for-byte.

**Architecture:** New `bundle_builder` fetches all data once (3 Serper + 1 Tavily + free sources) into a labeled `SectorDataBundle`; new sector-generic `UnifiedAnalyst` makes ONE `LLM_MODEL_REASONING` call that returns all 9 dimension outputs as the existing `AgentOutput` subclasses; `BaseSectorOrchestrator` branches on `UNIFIED_ANALYST_SECTORS` (flag-off = legacy path byte-identical, total-failure = legacy fallback); existing `SignalAggregator` consumes the outputs unchanged.

**Tech Stack:** Python 3.12, pydantic v2, OpenRouter (openai SDK), pytest. Run tests with `pytest` from repo root (pyproject sets pythonpath). Module runs outside pytest need `$env:PYTHONPATH=".;src"`.

**Spec:** `docs/superpowers/specs/2026-06-12-unified-sector-analyst-design.md` — read it first.

**Hard invariants (every task):**
- Flag off (`UNIFIED_ANALYST_SECTORS=""`) → zero behavior change anywhere.
- `FinalReport.weighted_agent_scores` and `agent_outputs` keep the same 9 keys and schemas.
- `UnifiedAnalyst.run` and `build_sector_bundle` NEVER raise.
- Settings style: `NAME: type = os.getenv("NAME", "default")` in `src/backend/shared/config/settings/base.py` (see line ~636 for the bool idiom).

---

### Task 1: Settings

**Files:**
- Modify: `src/backend/shared/config/settings/base.py` (append a new section near the RL settings)
- Test: `tests/unit/test_unified_analyst_settings.py`

- [ ] **Step 1: Write the failing test**

```python
"""Settings for the unified sector analyst (automobile pipeline redesign)."""
from core.config import settings


def test_unified_analyst_settings_defaults():
    assert settings.UNIFIED_ANALYST_SECTORS == "automobile"
    assert settings.UNIFIED_ANALYST_FALLBACK_LEGACY is True
    assert settings.UNIFIED_ANALYST_MAX_TOKENS == 3500
    assert settings.UNIFIED_SECTION_MAX_CHARS == 2500
    assert settings.UNIFIED_BUNDLE_MAX_CHARS == 18000


def test_unified_sectors_helper():
    from core.config.settings import unified_analyst_sectors
    assert unified_analyst_sectors() == {"automobile"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_unified_analyst_settings.py -v`
Expected: FAIL with AttributeError (settings missing).

- [ ] **Step 3: Implement settings**

Append to `src/backend/shared/config/settings/base.py`:

```python
# ---------------------------------------------------------------------------
# Unified Sector Analyst (2026-06-12 redesign) — one data bundle + one
# reasoning-model call replaces the per-sector parallel agent fan-out.
# CSV of sector names on the unified path; "" disables it everywhere.
# ---------------------------------------------------------------------------
UNIFIED_ANALYST_SECTORS: str = os.getenv("UNIFIED_ANALYST_SECTORS", "automobile")
UNIFIED_ANALYST_FALLBACK_LEGACY: bool = os.getenv("UNIFIED_ANALYST_FALLBACK_LEGACY", "true").lower() == "true"
UNIFIED_ANALYST_MAX_TOKENS: int = int(os.getenv("UNIFIED_ANALYST_MAX_TOKENS", "3500"))
UNIFIED_SECTION_MAX_CHARS: int = int(os.getenv("UNIFIED_SECTION_MAX_CHARS", "2500"))
UNIFIED_BUNDLE_MAX_CHARS: int = int(os.getenv("UNIFIED_BUNDLE_MAX_CHARS", "18000"))


def unified_analyst_sectors() -> set[str]:
    """Parsed UNIFIED_ANALYST_SECTORS; empty set when disabled."""
    return {s.strip() for s in UNIFIED_ANALYST_SECTORS.split(",") if s.strip()}
```

Check how `core/config/settings/__init__.py` (shim) re-exports — if it uses `from backend.shared.config.settings.base import *`, the function is exported automatically; if it lists names, add both names there too.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_unified_analyst_settings.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(unified-analyst): settings + sector helper"
```

---

### Task 2: SectorDataBundle + build_sector_bundle

**Files:**
- Create: `services/data/context/bundle_builder.py`
- Test: `tests/unit/test_bundle_builder.py`

One fetch pass. Reuses EXISTING fetchers only. Every fetch wrapped so failure → section `"unavailable"`. NSE data comes from `query.nse_data` (already prefetched by the orchestrator) — never refetch.

- [ ] **Step 1: Write the failing tests**

```python
"""Bundle builder: one fetch pass for the unified analyst."""
from unittest.mock import patch

from core.schemas.pipeline import StockQuery
from services.data.context.bundle_builder import SectorDataBundle, build_sector_bundle


def _query():
    return StockQuery(ticker="MARUTI", company_name="Maruti Suzuki India",
                      nse_data={"announcements": [], "board_meetings": [], "actions": []})


_FETCHERS = "services.data.context.bundle_builder"


def _patch_all_ok():
    """Patch every external fetcher used by the bundle builder to a cheap stub."""
    return [
        patch(f"{_FETCHERS}._fetch_company_news", return_value="company news text"),
        patch(f"{_FETCHERS}._fetch_sector_policy_news", return_value="sector policy text"),
        patch(f"{_FETCHERS}._fetch_macro_context", return_value="macro text"),
        patch(f"{_FETCHERS}._fetch_policy_deep_dive", return_value="tavily text"),
        patch(f"{_FETCHERS}._fetch_fundamentals", return_value="fundamentals text"),
        patch(f"{_FETCHERS}._fetch_technicals", return_value="technicals text"),
        patch(f"{_FETCHERS}._fetch_commodities", return_value="commodities text"),
        patch(f"{_FETCHERS}._fetch_flows_sentiment", return_value="flows text"),
        patch(f"{_FETCHERS}._fetch_peers_valuation", return_value="peers text"),
        patch(f"{_FETCHERS}._fetch_dossier_digest", return_value="dossier text"),
    ]


def test_bundle_has_all_sections_and_real_data():
    patches = _patch_all_ok()
    for p in patches:
        p.start()
    try:
        bundle = build_sector_bundle(_query(), "automobile")
    finally:
        for p in patches:
            p.stop()
    assert isinstance(bundle, SectorDataBundle)
    expected = {"company_news", "sector_policy_news", "macro_context", "policy_deep_dive",
                "fundamentals", "technicals", "commodities", "flows_sentiment",
                "peers_valuation", "dossier"}
    assert set(bundle.sections) == expected
    assert bundle.has_real_data is True


def test_fetcher_failure_is_nonfatal_section_unavailable():
    patches = _patch_all_ok()
    for p in patches:
        p.start()
    try:
        with patch(f"{_FETCHERS}._fetch_company_news", side_effect=RuntimeError("boom")):
            bundle = build_sector_bundle(_query(), "automobile")
    finally:
        for p in patches:
            p.stop()
    assert bundle.sections["company_news"] == "unavailable"


def test_section_and_total_caps(monkeypatch):
    patches = _patch_all_ok()
    for p in patches:
        p.start()
    try:
        with patch(f"{_FETCHERS}._fetch_company_news", return_value="x" * 99999):
            bundle = build_sector_bundle(_query(), "automobile")
    finally:
        for p in patches:
            p.stop()
    from core.config import settings
    assert len(bundle.sections["company_news"]) <= settings.UNIFIED_SECTION_MAX_CHARS
    assert len(bundle.to_prompt_text()) <= settings.UNIFIED_BUNDLE_MAX_CHARS + 2000  # + section headers


def test_has_real_data_false_when_most_sections_dead():
    patches = _patch_all_ok()
    for p in patches:
        p.start()
    try:
        dead = {f"{_FETCHERS}._fetch_{n}": None for n in [
            "company_news", "sector_policy_news", "macro_context", "policy_deep_dive",
            "fundamentals", "technicals", "commodities", "flows_sentiment"]}
        ctxs = [patch(k, side_effect=RuntimeError("dead")) for k in dead]
        for c in ctxs:
            c.start()
        try:
            bundle = build_sector_bundle(_query(), "automobile")
        finally:
            for c in ctxs:
                c.stop()
    finally:
        for p in patches:
            p.stop()
    assert bundle.has_real_data is False  # only 2 sections live (< 3)


def test_api_calls_made_counts():
    patches = _patch_all_ok()
    for p in patches:
        p.start()
    try:
        bundle = build_sector_bundle(_query(), "automobile")
    finally:
        for p in patches:
            p.stop()
    assert bundle.api_calls_made.get("serper", 0) <= 3
    assert bundle.api_calls_made.get("tavily", 0) <= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_bundle_builder.py -v` → FAIL (module not found)

- [ ] **Step 3: Implement `services/data/context/bundle_builder.py`**

```python
"""
services/data/context/bundle_builder.py
=======================================
One fetch pass for the Unified Sector Analyst.

Replaces the per-agent ContextBuilder fan-out (6-7 Serper + 2 Tavily per run)
with exactly: <=3 Serper searches, <=1 Tavily page, free sources (yfinance/NSE
prefetch/local indicators), and the dossier digest injected ONCE.

Every fetch is non-fatal: a failed section becomes "unavailable".
NSE data is read from query.nse_data (orchestrator prefetch) — never refetched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from core.config import settings
from core.schemas.pipeline import StockQuery

logger = logging.getLogger(__name__)

SECTION_ORDER = [
    "company_news", "sector_policy_news", "macro_context", "policy_deep_dive",
    "fundamentals", "technicals", "commodities", "flows_sentiment",
    "peers_valuation", "dossier",
]


@dataclass
class SectorDataBundle:
    sections: dict[str, str]
    has_real_data: bool
    api_calls_made: dict[str, int] = field(default_factory=dict)

    def to_prompt_text(self) -> str:
        """Labeled sections, bundle-level cap applied last."""
        parts = []
        for name in SECTION_ORDER:
            text = self.sections.get(name, "unavailable")
            parts.append(f"## {name.upper()}\n{text}")
        joined = "\n\n".join(parts)
        return joined[: settings.UNIFIED_BUNDLE_MAX_CHARS]


# ---------------------------------------------------------------------------
# Section fetchers — module-level so tests can patch them individually.
# Each returns a string; callers handle exceptions.
# ---------------------------------------------------------------------------

def _fetch_company_news(query: StockQuery, sector: str, serper_key: str) -> str:
    from services.data.fetchers.news import fetch_news_context
    today = date.today()
    queries = [
        f"{query.company_name} {query.ticker} latest news results guidance "
        f"{today.strftime('%B')} {today.year}",
    ]
    return fetch_news_context(queries, max_queries=1, api_key=serper_key)


def _fetch_sector_policy_news(query: StockQuery, sector: str, serper_key: str) -> str:
    from services.data.fetchers.news import fetch_news_context
    today = date.today()
    queries = [
        f"India {sector} sector demand policy regulation competitors news "
        f"{today.strftime('%B')} {today.year}",
    ]
    return fetch_news_context(queries, max_queries=1, api_key=serper_key)


def _fetch_macro_context(query: StockQuery, sector: str, serper_key: str) -> str:
    # Reuse the existing macro fetcher (it already has a daily cache + Serper-on-miss).
    from services.data.fetchers.macro import get_macro_context
    return get_macro_context()


def _fetch_policy_deep_dive(query: StockQuery, sector: str) -> str:
    from services.clients.tavily_fetcher import fetch_tavily_context
    return fetch_tavily_context(
        [f"{query.company_name} India {sector} policy regulation impact"],
        max_queries=1, max_results_per_query=1,
    )


def _fetch_fundamentals(query: StockQuery, sector: str) -> str:
    from services.data.fetchers.fundamentals import get_fundamentals_context
    from services.data.fetchers.nse_announcements import format_nse_context
    parts = [get_fundamentals_context(query.ticker)]
    if query.nse_data:
        parts.append(format_nse_context(query.nse_data))
    return "\n".join(p for p in parts if p)


def _fetch_technicals(query: StockQuery, sector: str) -> str:
    # Same source pattern_analysis uses today — find the indicator context helper
    # used by ContextBuilder._build_pattern_analysis and call it identically.
    from services.data.context.builder import ContextBuilder
    return ContextBuilder()._build_pattern_analysis(query)


def _fetch_commodities(query: StockQuery, sector: str) -> str:
    # Same source raw_materials uses today (daily _COMMODITY_CACHE inside).
    from services.data.fetchers.macro import get_commodity_context
    return get_commodity_context()


def _fetch_flows_sentiment(query: StockQuery, sector: str) -> str:
    # NSE bulk deals + FII/DII + MF herding, mirroring sentiment/risk_macro builders.
    from services.data.context.builder import ContextBuilder
    b = ContextBuilder()
    b._serper_key = ""   # flows path must not search
    b._sector = sector
    # Reuse the non-Serper parts via existing fetchers:
    from services.data.fetchers.nse_market import get_bulk_deals_context, get_fii_dii_context
    from services.data.fetchers.mf_herding import get_mf_herding_context
    parts = [get_bulk_deals_context(query.ticker), get_fii_dii_context(),
             get_mf_herding_context(sector)]
    return "\n".join(p for p in parts if p)


def _fetch_peers_valuation(query: StockQuery, sector: str) -> str:
    # Same peer P/E + corporate actions the valuation_catalyst builder assembles.
    from services.data.context.builder import ContextBuilder
    return ContextBuilder()._build_valuation_catalyst(query)


def _fetch_dossier_digest(query: StockQuery, sector: str) -> str:
    from backend.shared.pipeline.base_agent import BaseAgent
    digest = BaseAgent._fetch_dossier_digest(query.ticker, sector)
    return digest or ""


# NOTE: the exact helper names inside services/data/fetchers/* must be verified
# against the real modules when implementing (e.g. get_commodity_context,
# get_bulk_deals_context). If a helper doesn't exist under that name, call the
# same function the corresponding ContextBuilder._build_* method calls — the
# requirement is "same data source as the legacy agent", not a specific name.


def build_sector_bundle(query: StockQuery, sector: str) -> SectorDataBundle:
    """One fetch pass. NEVER raises."""
    serper_key = settings.get_serper_key(sector)
    api_calls: dict[str, int] = {"serper": 0, "tavily": 0}
    sections: dict[str, str] = {}

    def _safe(name: str, fn, *args) -> None:
        try:
            text = (fn(*args) or "").strip()
            sections[name] = text[: settings.UNIFIED_SECTION_MAX_CHARS] if text else "unavailable"
        except Exception as exc:  # noqa: BLE001 — section-level isolation
            logger.warning("[bundle] %s failed for %s: %s", name, query.ticker, exc)
            sections[name] = "unavailable"

    _safe("company_news", _fetch_company_news, query, sector, serper_key)
    api_calls["serper"] += 1
    _safe("sector_policy_news", _fetch_sector_policy_news, query, sector, serper_key)
    api_calls["serper"] += 1
    _safe("macro_context", _fetch_macro_context, query, sector, serper_key)
    api_calls["serper"] += 1  # upper bound; macro cache hit means 0 actual
    _safe("policy_deep_dive", _fetch_policy_deep_dive, query, sector)
    api_calls["tavily"] += 1
    _safe("fundamentals", _fetch_fundamentals, query, sector)
    _safe("technicals", _fetch_technicals, query, sector)
    _safe("commodities", _fetch_commodities, query, sector)
    _safe("flows_sentiment", _fetch_flows_sentiment, query, sector)
    _safe("peers_valuation", _fetch_peers_valuation, query, sector)
    _safe("dossier", _fetch_dossier_digest, query, sector)

    live = sum(1 for v in sections.values() if v and v != "unavailable")
    return SectorDataBundle(sections=sections, has_real_data=live >= 3,
                            api_calls_made=api_calls)
```

**Implementation note (verify, don't guess):** before finalizing, open `services/data/context/builder.py` and `services/data/fetchers/{macro,nse_market,mf_herding,fundamentals}.py` and use the REAL function names those builders call. The stubs above show intent; the test patches module-level `_fetch_*` wrappers precisely so internals can differ.

- [ ] **Step 4: Run tests** → PASS. Also run `pytest tests/unit -q` to confirm no regressions.

- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(unified-analyst): SectorDataBundle one-pass bundle builder"`

---

### Task 3: Automobile unified prompt

**Files:**
- Create: `src/backend/sectors/automobile/prompts/unified.py`
- Test: extend `tests/unit/test_unified_analyst.py` (created next task — for THIS task just a prompt-shape test)
- Test: `tests/unit/test_unified_prompt.py`

- [ ] **Step 1: Write the failing test**

```python
from backend.sectors.automobile.prompts import unified


def test_prompt_contains_all_nine_dimensions():
    for dim in ["sales_demand", "raw_materials", "fundamentals", "pattern_analysis",
                "sentiment", "policy_regulatory", "competitive_intel", "risk_macro",
                "valuation_catalyst"]:
        assert dim in unified.ANALYSIS_PROMPT


def test_prompt_lists_subscore_names():
    # spot-check a few sub_score field names that the output contract requires
    for sub in ["fada_siam_dispatch", "rsi_macd_bb", "pe_discount_vs_peers",
                "fame_ev_subsidy", "ev_market_share"]:
        assert sub in unified.ANALYSIS_PROMPT


def test_prompt_has_format_slots():
    assert "{ticker}" in unified.ANALYSIS_PROMPT
    assert "{company_name}" in unified.ANALYSIS_PROMPT
    assert "{bundle}" in unified.ANALYSIS_PROMPT
    assert "{report_date}" in unified.ANALYSIS_PROMPT
```

- [ ] **Step 2: Run** → FAIL (module missing)

- [ ] **Step 3: Implement the prompt module**

`SYSTEM_PROMPT`: senior Indian-equity automobile analyst; ground ONLY in the provided data bundle; never invent numbers; JSON only. State date/data-only rules ONCE (distill from `base_agent.py`'s `_DATA_ONLY_INSTRUCTION` + `_date_instruction` so the unified path keeps the same grounding discipline).

`ANALYSIS_PROMPT`: takes `{ticker}`, `{company_name}`, `{report_date}`, `{bundle}`. Then 9 dimension definitions distilled from the 9 existing prompt files in `src/backend/sectors/automobile/prompts/` (read each; keep what to assess + scoring anchors, 3-5 lines per dimension, and the exact 5 sub_score names from `src/backend/shared/schemas/pipeline.py:40-109`). End with the exact output JSON shape:

```json
{
  "sales_demand": {"score": 0.0, "confidence": 0.5, "summary": "", "key_positives": [], "key_risks": [],
                    "sub_scores": {"fada_siam_dispatch": 0.0, "ev_segment_vahan": 0.0, "dealer_inventory": 0.0, "export_import": 0.0, "used_car_price_index": 0.0},
                    "ticker_vs_peers": "", "bull_case_if": "", "bear_case_if": "", "what_changed": ""},
  "...": "(same shape for all 9; valuation_catalyst additionally has price_target, recovery_timeline_quarters, discount_reason, recovery_catalysts, fair_value_estimate, current_discount_pct)"
}
```

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `git commit -am "feat(unified-analyst): automobile unified prompt (9 dimensions, one call)"`

---

### Task 4: UnifiedAnalyst

**Files:**
- Create: `src/backend/shared/pipeline/unified_analyst.py`
- Test: `tests/unit/test_unified_analyst.py`

- [ ] **Step 1: Write the failing tests**

```python
import json
from unittest.mock import MagicMock, patch

from backend.shared.pipeline.unified_analyst import UnifiedAnalyst, DIMENSIONS
from core.schemas.pipeline import StockQuery, ValuationCatalystOutput
from services.data.context.bundle_builder import SectorDataBundle


def _bundle():
    return SectorDataBundle(sections={"company_news": "stub"}, has_real_data=True)


def _query():
    return StockQuery(ticker="MARUTI", company_name="Maruti Suzuki India")


def _good_payload() -> str:
    dims = {}
    for d in DIMENSIONS["automobile"]:
        dims[d] = {"score": 0.7, "confidence": 0.8, "summary": f"{d} ok",
                   "key_positives": ["p"], "key_risks": ["r"], "sub_scores": {}}
    dims["valuation_catalyst"]["price_target"] = 13500.0
    dims["valuation_catalyst"]["discount_reason"] = "peer P/E gap"
    return json.dumps(dims)


def _analyst_with_response(text: str) -> UnifiedAnalyst:
    a = UnifiedAnalyst()
    fake = MagicMock()
    fake.choices = [MagicMock()]
    fake.choices[0].message.content = text
    fake.usage = None
    a._client = MagicMock()
    a._client.chat.completions.create.return_value = fake
    return a


def test_returns_all_nine_dimensions_as_agent_outputs():
    a = _analyst_with_response(_good_payload())
    outs = a.run(_query(), _bundle(), "automobile")
    assert set(outs) == set(DIMENSIONS["automobile"])
    assert outs["sales_demand"].agent == "sales_demand"
    assert outs["sales_demand"].overall_score == 0.7
    assert isinstance(outs["valuation_catalyst"], ValuationCatalystOutput)
    assert outs["valuation_catalyst"].price_target == 13500.0
    assert a._client.chat.completions.create.call_count == 1  # ONE call


def test_missing_dimension_degrades_neutral():
    payload = json.loads(_good_payload())
    del payload["sentiment"]
    a = _analyst_with_response(json.dumps(payload))
    outs = a.run(_query(), _bundle(), "automobile")
    assert outs["sentiment"].overall_score == 0.5
    assert outs["sentiment"].error is not None


def test_missing_subscores_default_to_dimension_score():
    a = _analyst_with_response(_good_payload())
    outs = a.run(_query(), _bundle(), "automobile")
    ss = outs["sales_demand"].sub_scores
    assert ss is not None
    assert ss.fada_siam_dispatch == 0.7


def test_total_failure_returns_empty_never_raises():
    a = UnifiedAnalyst()
    a._client = MagicMock()
    a._client.chat.completions.create.side_effect = RuntimeError("LLM down")
    outs = a.run(_query(), _bundle(), "automobile")
    assert outs == {}


def test_malformed_json_returns_empty():
    a = _analyst_with_response("not json at all")
    outs = a.run(_query(), _bundle(), "automobile")
    assert outs == {}


def test_score_clamped():
    payload = json.loads(_good_payload())
    payload["fundamentals"]["score"] = 1.7
    a = _analyst_with_response(json.dumps(payload))
    outs = a.run(_query(), _bundle(), "automobile")
    assert outs["fundamentals"].overall_score == 1.0
```

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implement `src/backend/shared/pipeline/unified_analyst.py`**

```python
"""
src/backend/shared/pipeline/unified_analyst.py
==============================================
ONE reasoning-model call producing all sector dimension outputs.
Sector-generic: prompt + dimension list resolved per sector.

Contract: run() NEVER raises. Returns {} on total failure (orchestrator then
falls back to the legacy multi-agent path when UNIFIED_ANALYST_FALLBACK_LEGACY).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date

from core.config import settings
from core.schemas.pipeline import (
    AgentOutput, CompetitiveIntelOutput, FundamentalsOutput, PatternAnalysisOutput,
    PolicyRegulatoryOutput, RawMaterialsOutput, RiskMacroOutput, SalesDemandOutput,
    SentimentOutput, StockQuery, ValuationCatalystOutput,
)
from services.data.context.bundle_builder import SectorDataBundle

logger = logging.getLogger(__name__)

# Output class per dimension. Other sectors get their own entry later.
_AUTOMOBILE_CLASSES: dict[str, type[AgentOutput]] = {
    "sales_demand": SalesDemandOutput,
    "raw_materials": RawMaterialsOutput,
    "fundamentals": FundamentalsOutput,
    "pattern_analysis": PatternAnalysisOutput,
    "sentiment": SentimentOutput,
    "policy_regulatory": PolicyRegulatoryOutput,
    "competitive_intel": CompetitiveIntelOutput,
    "risk_macro": RiskMacroOutput,
    "valuation_catalyst": ValuationCatalystOutput,
}

DIMENSIONS: dict[str, list[str]] = {"automobile": list(_AUTOMOBILE_CLASSES)}

_VALUATION_EXTRAS = ("price_target", "recovery_timeline_quarters", "discount_reason",
                     "recovery_catalysts", "fair_value_estimate", "current_discount_pct")


def _clamp(x, lo=0.0, hi=1.0, default=0.5) -> float:
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return default


def _prompts_for(sector: str):
    if sector == "automobile":
        from backend.sectors.automobile.prompts import unified
        return unified
    raise ValueError(f"unified analyst has no prompt module for sector={sector}")


class UnifiedAnalyst:
    def __init__(self) -> None:
        from services.clients.llm_client import get_llm_client  # match SignalAggregator import
        self._client = get_llm_client()

    def run(self, query: StockQuery, bundle: SectorDataBundle,
            sector: str) -> dict[str, AgentOutput]:
        """One LLM call -> all dimension outputs. NEVER raises; {} on total failure."""
        try:
            prompts = _prompts_for(sector)
            user = prompts.ANALYSIS_PROMPT.format(
                ticker=query.ticker, company_name=query.company_name,
                report_date=str(date.today()), bundle=bundle.to_prompt_text(),
            )
            raw = self._call_llm(prompts.SYSTEM_PROMPT, user)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("non-dict analyst payload")
        except Exception as exc:  # noqa: BLE001 — never-raises contract
            logger.error("[UnifiedAnalyst] %s/%s failed: %s", sector, query.ticker, exc)
            return {}

        outputs: dict[str, AgentOutput] = {}
        for dim in DIMENSIONS.get(sector, []):
            cls = _AUTOMOBILE_CLASSES[dim]
            block = data.get(dim)
            if not isinstance(block, dict):
                outputs[dim] = cls(agent=dim, ticker=query.ticker, overall_score=0.5,
                                   error="missing_in_unified_response")
                continue
            try:
                outputs[dim] = self._parse_dimension(dim, cls, block, query)
            except Exception as exc:  # noqa: BLE001 — per-dimension isolation
                logger.warning("[UnifiedAnalyst] parse %s failed: %s", dim, exc)
                outputs[dim] = cls(agent=dim, ticker=query.ticker, overall_score=0.5,
                                   error=f"parse_error: {exc}")
        return outputs

    def _parse_dimension(self, dim: str, cls: type[AgentOutput], block: dict,
                         query: StockQuery) -> AgentOutput:
        score = _clamp(block.get("score"))
        sub_model = cls.model_fields["sub_scores"].annotation  # Optional[XSubScores]
        # resolve the concrete sub-scores model from the Optional annotation
        import typing
        sub_cls = next(t for t in typing.get_args(sub_model) if t is not type(None))
        raw_subs = block.get("sub_scores") or {}
        subs = {name: _clamp(raw_subs.get(name, score), default=score)
                for name in sub_cls.model_fields}
        kwargs: dict = {
            "agent": dim, "ticker": query.ticker, "overall_score": score,
            "summary": str(block.get("summary", ""))[:1200],
            "key_positives": [str(x) for x in (block.get("key_positives") or [])][:5],
            "key_risks": [str(x) for x in (block.get("key_risks") or [])][:5],
            "data_confidence": _clamp(block.get("confidence", 0.5)),
            "ticker_vs_peers": str(block.get("ticker_vs_peers", ""))[:400],
            "bull_case_if": str(block.get("bull_case_if", ""))[:400],
            "bear_case_if": str(block.get("bear_case_if", ""))[:400],
            "what_changed": str(block.get("what_changed", ""))[:400],
            "data_freshness": "unified_analyst",
            "sub_scores": sub_cls(**subs),
        }
        if dim == "valuation_catalyst":
            for f in _VALUATION_EXTRAS:
                if block.get(f) is not None:
                    kwargs[f] = block[f]
        return cls(**kwargs)

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                resp = self._client.chat.completions.create(
                    model=settings.LLM_MODEL_REASONING,
                    temperature=0.2,
                    max_tokens=settings.UNIFIED_ANALYST_MAX_TOKENS,
                    messages=[{"role": "system", "content": system_prompt},
                              {"role": "user", "content": user_prompt}],
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content or "{}"
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(1 + attempt)
        raise RuntimeError(f"unified analyst LLM failed after retries: {last_exc}")
```

**Implementation notes:** (1) verify the real `get_llm_client` import path by checking the top of `signal_aggregator.py` and use the same; (2) the ValuationCatalystOutput extras must round-trip into the existing FinalReport field extraction; (3) add `log_llm_call(... phase="unified_analyst" ...)` mirroring SignalAggregator's telemetry block.

- [ ] **Step 4: Run** `pytest tests/unit/test_unified_analyst.py -v` → PASS
- [ ] **Step 5: Commit** `git commit -am "feat(unified-analyst): one reasoning call -> 9 AgentOutputs"`

---

### Task 5: Single valuation-extraction helper in SignalAggregator

**Files:**
- Modify: `src/backend/shared/pipeline/signal_aggregator.py` (the hardcoded pull around lines 226-235 inside `_parse`)
- Test: `tests/unit/test_signal_aggregator_valuation.py`

- [ ] **Step 1: Write the failing test**

```python
from backend.shared.pipeline.signal_aggregator import extract_valuation_fields
from core.schemas.pipeline import ValuationCatalystOutput


def test_extracts_valuation_fields():
    out = ValuationCatalystOutput(
        agent="valuation_catalyst", ticker="MARUTI", overall_score=0.6,
        price_target=13500.0, recovery_timeline_quarters=3,
        discount_reason="peer P/E gap", recovery_catalysts=["new launches"],
        current_discount_pct=12.0,
    )
    fields = extract_valuation_fields({"valuation_catalyst": out})
    assert fields["price_target"] == 13500.0
    assert fields["discount_reason"] == "peer P/E gap"


def test_missing_valuation_agent_gives_empty_defaults():
    fields = extract_valuation_fields({})
    assert fields["price_target"] is None
```

- [ ] **Step 2: Run** → FAIL (no `extract_valuation_fields`)

- [ ] **Step 3: Implement** — add a module-level `extract_valuation_fields(agent_outputs) -> dict` in `signal_aggregator.py` containing EXACTLY the logic currently inlined in `_parse` (move, don't rewrite — same keys, same defaults), and make `_parse` call it. No behavior change: the existing aggregator tests are the regression net.

- [ ] **Step 4: Run** `pytest tests/unit/test_signal_aggregator_valuation.py tests/unit -q` → PASS, no regressions
- [ ] **Step 5: Commit** `git commit -am "refactor(aggregator): single valuation-extraction helper"`

---

### Task 6: Orchestrator unified branch + legacy fallback

**Files:**
- Modify: `src/backend/shared/pipeline/base_orchestrator.py` (`analyse` ~line 186 and `analyse_async` ~line 126: replace the direct `_run_via_graph*` call with a dispatch helper)
- Test: `tests/unit/test_orchestrator_unified_branch.py`

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock, patch

import pytest

from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator
from core.schemas.pipeline import SalesDemandOutput


def _nine_outputs(ticker="MARUTI"):
    from backend.shared.pipeline.unified_analyst import _AUTOMOBILE_CLASSES
    return {d: c(agent=d, ticker=ticker, overall_score=0.6)
            for d, c in _AUTOMOBILE_CLASSES.items()}


@patch("backend.shared.pipeline.base_orchestrator.settings")
def test_flag_off_uses_legacy_worker_pool(mock_settings):
    mock_settings.UNIFIED_ANALYST_SECTORS = ""
    orch = AutomobileAgentOrchestrator()
    with patch.object(orch, "_run_via_graph", return_value=_nine_outputs()) as legacy, \
         patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst") as ua, \
         patch.object(orch, "_resolve_ticker") as rt, \
         patch.object(orch, "_prefetch_nse_data"), \
         patch.object(orch._aggregator, "run", return_value=MagicMock()):
        from core.schemas.pipeline import StockQuery
        rt.return_value = StockQuery(ticker="MARUTI", company_name="Maruti")
        orch.analyse("MARUTI")
        legacy.assert_called_once()
        ua.assert_not_called()


def test_flag_on_uses_unified_path_and_progress_callbacks():
    orch = AutomobileAgentOrchestrator()
    events = []
    with patch("backend.shared.pipeline.base_orchestrator.build_sector_bundle") as bb, \
         patch("backend.shared.pipeline.base_orchestrator.UnifiedAnalyst") as UA, \
         patch.object(orch, "_run_via_graph") as legacy, \
         patch.object(orch, "_resolve_ticker") as rt, \
         patch.object(orch, "_prefetch_nse_data"), \
         patch.object(orch._aggregator, "run", return_value=MagicMock()):
        from core.schemas.pipeline import StockQuery
        rt.return_value = StockQuery(ticker="MARUTI", company_name="Maruti")
        UA.return_value.run.return_value = _nine_outputs()
        orch.analyse("MARUTI", progress_callback=lambda n, s: events.append((n, s)))
        legacy.assert_not_called()
        UA.return_value.run.assert_called_once()
        assert len(events) == 9  # one per dimension


def test_unified_total_failure_falls_back_to_legacy():
    orch = AutomobileAgentOrchestrator()
    with patch("backend.shared.pipeline.base_orchestrator.build_sector_bundle"), \
         patch("backend.shared.pipeline.base_orchestrator.UnifiedAnalyst") as UA, \
         patch.object(orch, "_run_via_graph", return_value=_nine_outputs()) as legacy, \
         patch.object(orch, "_resolve_ticker") as rt, \
         patch.object(orch, "_prefetch_nse_data"), \
         patch.object(orch._aggregator, "run", return_value=MagicMock()):
        from core.schemas.pipeline import StockQuery
        rt.return_value = StockQuery(ticker="MARUTI", company_name="Maruti")
        UA.return_value.run.return_value = {}  # total failure
        orch.analyse("MARUTI")
        legacy.assert_called_once()
```

(If `settings` is imported as a module rather than an attribute of base_orchestrator, patch `core.config.settings.UNIFIED_ANALYST_SECTORS` with `monkeypatch.setattr` instead — match how existing orchestrator tests patch settings.)

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implement the dispatch helper**

In `base_orchestrator.py` add (and call from BOTH `analyse` and `analyse_async` in place of the direct `_run_via_graph*` calls; async path wraps the sync helper with `asyncio.to_thread` for the bundle+LLM work):

```python
def _unified_enabled(self) -> bool:
    from core.config.settings import unified_analyst_sectors
    return self.SECTOR_NAME in unified_analyst_sectors()

def _run_unified(self, query, run_id, progress_callback):
    """Unified path: one bundle + one analyst call. Returns {} to signal fallback."""
    from services.data.context.bundle_builder import build_sector_bundle
    from backend.shared.pipeline.unified_analyst import UnifiedAnalyst
    bundle = build_sector_bundle(query, self.SECTOR_NAME)
    logger.info("[%s] unified bundle: api_calls=%s real_data=%s",
                self.SECTOR_NAME, bundle.api_calls_made, bundle.has_real_data)
    outputs = UnifiedAnalyst().run(query, bundle, self.SECTOR_NAME)
    if outputs and progress_callback:
        for name, out in outputs.items():
            try:
                progress_callback(name, out.overall_score)
            except Exception:  # noqa: BLE001 — UI callback must not kill the run
                pass
    return outputs

def _run_agents(self, query, run_id, progress_callback):
    """Dispatch: unified path when enabled, legacy worker pool otherwise/fallback."""
    if self._unified_enabled():
        outputs = self._run_unified(query, run_id, progress_callback)
        if outputs:
            return outputs
        if not settings.UNIFIED_ANALYST_FALLBACK_LEGACY:
            return outputs  # empty -> aggregator neutral handling
        logger.warning("[%s] unified analyst failed -> legacy fallback", self.SECTOR_NAME)
    return self._run_via_graph(query, run_id=run_id, progress_callback=progress_callback)
```

Async: `analyse_async` calls `await asyncio.to_thread(self._run_agents, query, run_id, progress_callback)` when unified is enabled, else the existing `await self._run_via_graph_async(...)`. Keep the legacy async path untouched (flag-off byte-identical includes async).

Also import `build_sector_bundle` and `UnifiedAnalyst` lazily inside the helpers (as shown) so the flag-off path never imports the new modules.

- [ ] **Step 4: Run** `pytest tests/unit/test_orchestrator_unified_branch.py tests/unit -q` → PASS, no regressions
- [ ] **Step 5: Commit** `git commit -am "feat(unified-analyst): orchestrator branch + legacy fallback"`

---

### Task 7: End-to-end parity test (mocked LLM, no network)

**Files:**
- Test: `tests/unit/test_unified_e2e_parity.py`

- [ ] **Step 1: Write the test**

```python
"""Flag-on run with mocked LLM + fetchers must produce a FinalReport with the
same 9 weighted_agent_scores keys and schema-valid agent_outputs that the
legacy path produces — the RL/UI compatibility invariant."""
import json
from unittest.mock import MagicMock, patch

from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator
from backend.shared.pipeline.unified_analyst import DIMENSIONS

EXPECTED_KEYS = set(DIMENSIONS["automobile"])


def test_unified_finalreport_contract(monkeypatch):
    monkeypatch.setattr("core.config.settings.UNIFIED_ANALYST_SECTORS", "automobile", raising=False)
    orch = AutomobileAgentOrchestrator()

    dims = {d: {"score": 0.65, "confidence": 0.7, "summary": f"{d} fine",
                "key_positives": [], "key_risks": [], "sub_scores": {}}
            for d in EXPECTED_KEYS}
    dims["valuation_catalyst"]["price_target"] = 14000.0

    agg_json = json.dumps({
        "verdict": "BUY", "executive_summary": "ok", "investment_thesis": "ok",
        "conviction_drivers": ["d"], "top_risks": ["r"], "conflicts_resolved": [],
    })

    def fake_create(**kwargs):
        resp = MagicMock()
        resp.usage = None
        # analyst call asks for all dimensions; aggregator call asks for verdict
        text = json.dumps(dims) if "sales_demand" in str(kwargs["messages"]) else agg_json
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = text
        return resp

    with patch("services.data.context.bundle_builder.build_sector_bundle") as bb, \
         patch.object(orch, "_prefetch_nse_data"):
        from services.data.context.bundle_builder import SectorDataBundle
        bb.return_value = SectorDataBundle(sections={"company_news": "x"}, has_real_data=True)
        # patch BOTH llm clients (analyst + aggregator) to the same fake
        with patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst._call_llm") as ua_llm, \
             patch.object(orch._aggregator, "_call_llm", side_effect=lambda s, u: agg_json):
            ua_llm.return_value = json.dumps(dims)
            report = orch.analyse("MARUTI")

    assert set(report.weighted_agent_scores) == EXPECTED_KEYS
    assert set(report.agent_outputs) == EXPECTED_KEYS
    assert report.verdict in {"STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"}
    assert report.price_target == 14000.0  # valuation extras survive the pipeline
```

Adjust patch targets to reality (e.g. where the orchestrator imports `build_sector_bundle` from — patch the name in `base_orchestrator`'s namespace if imported there). Note `_resolve_ticker` is NOT mocked here — if it needs an LLM, mock it like Task 6 does.

- [ ] **Step 2: Run** → PASS (fix patch targets until green; the assertions themselves must not be weakened)
- [ ] **Step 3: Run the FULL unit suite** `pytest tests/unit -q` → everything green (baseline: 1277 passed / 5 skipped before this work)
- [ ] **Step 4: Commit** `git commit -am "test(unified-analyst): e2e FinalReport contract parity"`

---

### Task 8: Live verification (reviewer runs this — real network, real LLM)

No code. Evidence required for APPROVED:

- [ ] **Step 1: Flag-on real run**

```powershell
$env:PYTHONPATH=".;src"
python -c "from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator; r = AutomobileAgentOrchestrator().analyse('MARUTI'); print(r.verdict, r.final_score); print({k: v.raw for k, v in r.weighted_agent_scores.items()})"
```

Expected: verdict printed, ALL 9 weighted_agent_scores present with non-default scores, log line `unified bundle: api_calls={'serper': <=3, 'tavily': <=1}`, exactly ONE `phase="unified_analyst"` LLM log + one aggregation call.

- [ ] **Step 2: Flag-off real run (legacy intact)**

```powershell
$env:UNIFIED_ANALYST_SECTORS=""
python -c "<same command>"
```

Expected: legacy 9-agent run executes (9 agent LLM log lines), report valid. Unset the env var after.

- [ ] **Step 3: RL consumer check**

```powershell
python -c "from core.intelligence.rl.workflows.daily_review import _run_todays_agent_scores; print('import ok')"
pytest tests/unit -q
```

Plus run any existing daily_review unit tests; they must pass untouched.

- [ ] **Step 4: Commit any fixes**, final suite green.
