# Morning Brief Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the flat, jargon-heavy morning brief into a sectioned, plain-English, newcomer-legible plain-text brief, and fix the overnight-truncation + duplication data bugs.

**Architecture:** All work is in `core/delivery/brief.py` (pure deterministic helpers + a rewritten `render_brief_text` + build-time enrichment), plus six new `delivery.brief_*` config keys. No new LLM calls, no schema/data migration, no delivery-channel change. Research-framed throughout (never personal advice).

**Tech Stack:** Python 3.11, pytest, `cfg()`/config.yaml settings, existing `MacroNewsCache` / `ShelfStore` / `load_ipo_cache`.

## Global Constraints

- All new caps/thresholds go through `cfg()`/config.yaml — never hardcoded (config-over-hardcode rule).
- Every helper is pure and non-raising; `render_brief_text` must never raise (delivery is non-fatal).
- No new LLM calls; the single BULK narration call in `_narrate_brief` is unchanged.
- No emoji in output (email/push client safety).
- Full test suite fail-set must stay **byte-identical to the known-red baseline** (A/B via worktree) — verify in the final task.
- Never push to `main` 16:25–17:15 IST on trading days (weekend is fine).

---

### Task 1: Config keys + settings

**Files:**
- Modify: `config.yaml` (delivery block, after `outbox_retention_days`, ~line 421)
- Modify: `src/backend/shared/config/settings/base.py` (after the `DELIVERY_*` block, ~line 898)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Produces: `settings.DELIVERY_BRIEF_MAX_OVERNIGHT:int`, `DELIVERY_BRIEF_OVERNIGHT_DEDUP_THRESHOLD:float`, `DELIVERY_BRIEF_OVERNIGHT_MAXLEN:int`, `DELIVERY_BRIEF_MAX_IDEAS:int`, `DELIVERY_BRIEF_IDEA_REASON_MAXLEN:int`, `DELIVERY_BRIEF_MAX_IPOS:int`.

- [ ] **Step 1: Write the failing test**

```python
def test_brief_settings_have_defaults():
    from core.config import settings
    assert settings.DELIVERY_BRIEF_MAX_OVERNIGHT == 3
    assert settings.DELIVERY_BRIEF_OVERNIGHT_DEDUP_THRESHOLD == 0.6
    assert settings.DELIVERY_BRIEF_OVERNIGHT_MAXLEN == 240
    assert settings.DELIVERY_BRIEF_MAX_IDEAS == 5
    assert settings.DELIVERY_BRIEF_IDEA_REASON_MAXLEN == 180
    assert settings.DELIVERY_BRIEF_MAX_IPOS == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_brief.py::test_brief_settings_have_defaults -v`
Expected: FAIL (AttributeError).

- [ ] **Step 3: Add config.yaml keys** (under `delivery:`, after `outbox_retention_days: 30`)

```yaml
  # Morning-brief rendering (redesign 2026-07-27)
  brief_max_overnight: 3               # overnight items shown after dedup
  brief_overnight_dedup_threshold: 0.6 # Jaccard token-similarity = "same story"
  brief_overnight_maxlen: 240          # length safety-net trim for a headline
  brief_max_ideas: 5                   # discovery ideas shown
  brief_idea_reason_maxlen: 180        # per-idea reason line cap
  brief_max_ipos: 3                    # IPOs shown after dedup
```

- [ ] **Step 4: Add settings** (base.py, after `DELIVERY_EMAIL_TO`)

```python
# Morning-brief rendering (redesign 2026-07-27)
DELIVERY_BRIEF_MAX_OVERNIGHT: int = int(cfg("delivery.brief_max_overnight", fallback=3))
DELIVERY_BRIEF_OVERNIGHT_DEDUP_THRESHOLD: float = float(cfg("delivery.brief_overnight_dedup_threshold", fallback=0.6))
DELIVERY_BRIEF_OVERNIGHT_MAXLEN: int = int(cfg("delivery.brief_overnight_maxlen", fallback=240))
DELIVERY_BRIEF_MAX_IDEAS: int = int(cfg("delivery.brief_max_ideas", fallback=5))
DELIVERY_BRIEF_IDEA_REASON_MAXLEN: int = int(cfg("delivery.brief_idea_reason_maxlen", fallback=180))
DELIVERY_BRIEF_MAX_IPOS: int = int(cfg("delivery.brief_max_ipos", fallback=3))
```

- [ ] **Step 5: Run test to verify it passes** — `python -m pytest tests/unit/test_delivery_brief.py::test_brief_settings_have_defaults -v` → PASS
- [ ] **Step 6: Commit** — `git add config.yaml src/backend/shared/config/settings/base.py tests/unit/test_delivery_brief.py && git commit -m "feat(brief): config keys for brief rendering caps/thresholds"`

---

### Task 2: Static maps + pure formatting helpers

**Files:**
- Modify: `core/delivery/brief.py` (add near top, after imports)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Produces: `_REGIME_PLAIN:dict`, `_VERDICT_PLAIN:dict`, `_pct(x)->str`, `_trim_words(text,maxlen)->str`, `_clean_headline(text,maxlen)->str`, `_first_sentence(thesis,maxlen)->str`, `_fmt_date(iso)->str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_pct_formats_conviction():
    assert br._pct(0.654) == "65%"
    assert br._pct(0.62) == "62%"
    assert br._pct(None) == "" and br._pct("x") == ""

def test_first_sentence_ignores_decimals():
    thesis = "Acme has 65% EBITDA margin and INR 547.86cr revenue. The next line."
    assert br._first_sentence(thesis, 180) == "Acme has 65% EBITDA margin and INR 547.86cr revenue."

def test_first_sentence_caps_length():
    assert br._first_sentence("word " * 60, 40).endswith("…")
    assert br._first_sentence("", 40) == ""

def test_clean_headline_trims_overlong_at_word_boundary():
    out = br._clean_headline("a " * 200, 20)
    assert len(out) <= 21 and out.endswith("…") and not out.endswith(" …")

def test_regime_and_verdict_maps():
    assert br._REGIME_PLAIN["RISK_OFF"][0] == "Cautious"
    assert set(["MACRO_CRISIS","RISK_OFF","MOMENTUM_EXTENDED","RISK_ON","OVERSOLD","NORMAL"]) <= set(br._REGIME_PLAIN)
    assert br._VERDICT_PLAIN["EXIT"] == "Consider exiting"
```

- [ ] **Step 2: Run to verify fail** — `python -m pytest tests/unit/test_delivery_brief.py -k "pct or first_sentence or clean_headline or regime_and_verdict" -v` → FAIL
- [ ] **Step 3: Implement** (top of `brief.py`, after existing imports add `import re`)

```python
_REGIME_PLAIN: dict[str, tuple[str, str]] = {
    "MACRO_CRISIS":      ("Crisis", "a volatile market and outflows together — the system is at its most defensive."),
    "RISK_OFF":          ("Cautious", "the system reads elevated risk right now and is trading defensively."),
    "MOMENTUM_EXTENDED": ("Overextended", "a strong run has left the market overbought, so mean-reversion risk is up."),
    "RISK_ON":           ("Constructive", "a calm market with inflows — the system is comfortable leaning in."),
    "OVERSOLD":          ("Oversold", "the market has sold off sharply; beaten-down names may be due a bounce."),
    "NORMAL":            ("Steady", "conditions are normal; the system is trading as usual."),
}

_VERDICT_PLAIN: dict[str, str] = {
    "EXIT": "Consider exiting", "TRIM": "Trim back", "ADD": "Add more",
    "HOLD": "Hold", "SWITCH": "Switch", "WAIT_FOR_LTCG": "Hold for tax",
}

_SENT_END = re.compile(r"[.!?]\s")


def _pct(conviction) -> str:
    """0.654 -> '65%'. Bad input -> ''."""
    try:
        return f"{round(float(conviction) * 100)}%"
    except (TypeError, ValueError):
        return ""


def _trim_words(text: str, maxlen: int) -> str:
    """Collapse whitespace; trim to <= maxlen at a word boundary + '…' if cut."""
    t = " ".join((text or "").split())
    if len(t) <= maxlen:
        return t
    return t[:maxlen].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _clean_headline(text: str, maxlen: int) -> str:
    """Length safety-net for an overnight headline (see spec §4.2)."""
    return _trim_words(text, maxlen)


def _first_sentence(thesis: str, maxlen: int) -> str:
    """First sentence of a thesis (decimal-safe), capped at maxlen. '' if empty."""
    t = " ".join((thesis or "").split())
    if not t:
        return ""
    m = _SENT_END.search(t)
    sent = t[: m.start() + 1].strip() if m else t
    return _trim_words(sent, maxlen)


def _fmt_date(iso: str) -> str:
    from datetime import date as _d
    try:
        return _d.fromisoformat(iso).strftime("%a %d %b")
    except Exception:
        return iso
```

- [ ] **Step 4: Run to verify pass** → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat(brief): plain-language maps + pure formatting helpers"`

---

### Task 3: Overnight — prefer LLM summary, clean + dedup

**Files:**
- Modify: `core/delivery/brief.py` (`_overnight_items`; add `_norm_text`, `_dedup_overnight`)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Consumes: `settings.DELIVERY_BRIEF_*` (Task 1), `_clean_headline` (Task 2).
- Produces: `_dedup_overnight(items, threshold, max_items)->list`; `_overnight_items` now returns deduped `{"headline","severity"}` sourced from `summary or title`.

- [ ] **Step 1: Write the failing tests**

```python
def test_overnight_prefers_summary_over_truncated_title(monkeypatch):
    class _Fake:
        def get_high_severity(self, hours_back=24):
            return [{"title": "Rupee rallies amid Middle East con",
                     "summary": "The rupee rallied after the RBI eased rules for foreign investors.",
                     "severity": "HIGH"}]
    import services.background.macro_news_cache as mnc
    monkeypatch.setattr(mnc, "MacroNewsCache", _Fake)
    items = br._overnight_items()
    assert items[0]["headline"] == "The rupee rallied after the RBI eased rules for foreign investors."

def test_overnight_dedups_same_story(monkeypatch):
    class _Fake:
        def get_high_severity(self, hours_back=24):
            return [
                {"summary": "RBI raised equity investment limits for NRIs and OCIs.", "severity": "HIGH"},
                {"summary": "RBI raised equity investment limits for NRIs and OCIs, boosting inflows.", "severity": "HIGH"},
                {"summary": "SEBI to launch corporate bond index derivatives.", "severity": "HIGH"},
            ]
    import services.background.macro_news_cache as mnc
    monkeypatch.setattr(mnc, "MacroNewsCache", _Fake)
    items = br._overnight_items()
    heads = [i["headline"] for i in items]
    assert len(heads) == 2
    assert "RBI raised equity investment limits for NRIs and OCIs, boosting inflows." in heads  # longer kept
    assert any("SEBI" in h for h in heads)
```

- [ ] **Step 2: Run to verify fail** → FAIL
- [ ] **Step 3: Implement**

```python
def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def _dedup_overnight(items: list[dict], threshold: float, max_items: int) -> list[dict]:
    """Collapse near-duplicate stories (prefix or Jaccard>=threshold); keep the
    longest headline per cluster; return in first-seen order, capped."""
    kept: list[dict] = []
    kept_norm: list[str] = []
    kept_tok: list[set] = []
    for it in items:
        norm = _norm_text(it["headline"])
        toks = set(norm.split())
        if not toks:
            continue
        dup = None
        for i, kn in enumerate(kept_norm):
            inter = len(toks & kept_tok[i])
            union = len(toks | kept_tok[i]) or 1
            if norm in kn or kn in norm or (inter / union) >= threshold:
                dup = i
                break
        if dup is None:
            kept.append(it); kept_norm.append(norm); kept_tok.append(toks)
        elif len(it["headline"]) > len(kept[dup]["headline"]):
            kept[dup] = it; kept_norm[dup] = norm; kept_tok[dup] = toks
    return kept[:max_items]
```

Replace the body of `_overnight_items`:

```python
def _overnight_items(max_items: int | None = None) -> list[dict]:
    try:
        from services.background.macro_news_cache import MacroNewsCache
        mi = max_items if max_items is not None else settings.DELIVERY_BRIEF_MAX_OVERNIGHT
        raw = MacroNewsCache().get_high_severity(hours_back=24)
        items: list[dict] = []
        for i in raw:
            text = (i.get("summary") or i.get("title") or "").strip()
            if not text:
                continue
            items.append({
                "headline": _clean_headline(text, settings.DELIVERY_BRIEF_OVERNIGHT_MAXLEN),
                "severity": i.get("severity", "HIGH"),
            })
        return _dedup_overnight(items, settings.DELIVERY_BRIEF_OVERNIGHT_DEDUP_THRESHOLD, mi)
    except Exception as exc:
        logger.warning("[brief] macro feed read failed (non-fatal): %s", exc)
        return []
```

- [ ] **Step 4: Run to verify pass** — also run the existing `test_overnight_items_read_cache_title_field` (its title-only fixtures still work via fallback) → all PASS
- [ ] **Step 5: Commit** — `git commit -am "feat(brief): overnight uses clean LLM summary + content dedup"`

---

### Task 4: IPO — subscription demand + symbol dedup

**Files:**
- Modify: `core/delivery/brief.py` (`_ipo_watch`; add `_dedup_ipos`, `_ipo_demand`)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Consumes: `settings.DELIVERY_BRIEF_MAX_IPOS`.
- Produces: `_dedup_ipos(rows,max_items)->list`, `_ipo_demand(row)->str`; `_ipo_watch` rows now carry `qib_x/retail_x/total_x/issue_price`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ipo_dedups_by_symbol(monkeypatch):
    monkeypatch.setattr(br, "load_ipo_cache", lambda: {
        "current": [{"symbol": "LSR", "company": "Laser", "status": "current", "total_x": 8.2}],
        "upcoming": [{"symbol": "LSR", "company": "Laser", "status": "upcoming"},
                     {"symbol": "KUS", "company": "Kusum", "status": "upcoming"}]})
    rows = br._ipo_watch()
    syms = [r["symbol"] for r in rows]
    assert syms == ["LSR", "KUS"]  # current LSR wins, no dup
    assert rows[0]["total_x"] == 8.2

def test_ipo_demand_string():
    assert br._ipo_demand({"total_x": 8.2, "qib_x": 12.0, "retail_x": 3.0}) == "8.2× overall (QIB 12×, retail 3×)"
    assert br._ipo_demand({}) == "demand data pending"
```

- [ ] **Step 2: Run to verify fail** → FAIL
- [ ] **Step 3: Implement**

```python
def _dedup_ipos(rows: list[dict], max_items: int) -> list[dict]:
    """Dedup by symbol; a 'current' row beats 'upcoming'/'past'. First-seen order."""
    rank = {"current": 0, "upcoming": 1, "past": 2}
    best: dict[str, dict] = {}
    seq: list[str] = []
    for r in rows:
        sym = r.get("symbol", "")
        if not sym:
            continue
        if sym not in best:
            best[sym] = r; seq.append(sym)
        elif rank.get(r.get("status", ""), 9) < rank.get(best[sym].get("status", ""), 9):
            best[sym] = r
    return [best[s] for s in seq][:max_items]


def _ipo_demand(w: dict) -> str:
    total, qib, retail = w.get("total_x"), w.get("qib_x"), w.get("retail_x")
    if total is None and qib is None and retail is None:
        return "demand data pending"
    parts: list[str] = []
    if total is not None:
        parts.append(f"{total:g}× overall")
    extra = []
    if qib is not None:
        extra.append(f"QIB {qib:g}×")
    if retail is not None:
        extra.append(f"retail {retail:g}×")
    if extra:
        parts.append("(" + ", ".join(extra) + ")")
    return " ".join(parts) if parts else "demand data pending"
```

Replace the body of `_ipo_watch`:

```python
def _ipo_watch(max_items: int | None = None) -> list[dict]:
    try:
        cache = load_ipo_cache()
        mi = max_items if max_items is not None else settings.DELIVERY_BRIEF_MAX_IPOS
        rows = cache.get("current", []) + cache.get("upcoming", [])
        out = [{
            "symbol": r.get("symbol", ""), "company": r.get("company", ""),
            "status": r.get("status", ""), "qib_x": r.get("qib_x"),
            "retail_x": r.get("retail_x"), "total_x": r.get("total_x"),
            "issue_price": r.get("issue_price"),
        } for r in rows]
        return _dedup_ipos(out, mi)
    except Exception as exc:
        logger.warning("[brief] ipo watch failed (non-fatal): %s", exc)
        return []
```

- [ ] **Step 4: Run to verify pass** → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat(brief): IPO subscription demand + symbol dedup"`

---

### Task 5: Discovery ideas — join shelf verdict/conviction/reason

**Files:**
- Modify: `core/delivery/brief.py` (add `_enrich_discovery_adds`; call it in `build_morning_brief`)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Consumes: `_first_sentence` (Task 2), `settings.DELIVERY_BRIEF_IDEA_REASON_MAXLEN`, `core.discovery.shelf.ShelfStore`.
- Produces: `_enrich_discovery_adds(adds)->list` — each row optionally gains `verdict/conviction/reason`. `build_morning_brief` stores enriched `discovery_adds`.

- [ ] **Step 1: Write the failing test**

```python
def test_enrich_discovery_adds_joins_shelf(monkeypatch):
    class _Idea:
        symbol, verdict, conviction = "NEWCO", "BUY", 0.62
        thesis = "Newco is a fast grower with 40% margins. More detail here."
    class _Shelf:
        def load(self): return type("S", (), {"ideas": [_Idea()]})()
    import core.discovery.shelf as sh
    monkeypatch.setattr(sh, "ShelfStore", _Shelf)
    out = br._enrich_discovery_adds([{"event": "added", "symbol": "NEWCO", "detail": ""},
                                     {"event": "added", "symbol": "GHOST", "detail": ""}])
    assert out[0]["verdict"] == "BUY" and out[0]["conviction"] == 0.62
    assert out[0]["reason"] == "Newco is a fast grower with 40% margins."
    assert "verdict" not in out[1]  # unknown symbol stays a bare row
```

- [ ] **Step 2: Run to verify fail** → FAIL
- [ ] **Step 3: Implement**

```python
def _enrich_discovery_adds(adds: list[dict]) -> list[dict]:
    """Join each discovery add to its shelf idea (verdict/conviction/reason). Non-fatal."""
    if not adds:
        return adds
    ideas: dict[str, object] = {}
    try:
        from core.discovery.shelf import ShelfStore
        for idea in ShelfStore().load().ideas:
            ideas[str(getattr(idea, "symbol", "")).upper()] = idea
    except Exception as exc:
        logger.debug("[brief] shelf read for idea enrichment failed (non-fatal): %s", exc)
    out: list[dict] = []
    for a in adds:
        row = dict(a)
        idea = ideas.get(str(a.get("symbol", "")).upper())
        if idea is not None:
            row["verdict"] = getattr(idea, "verdict", None)
            row["conviction"] = getattr(idea, "conviction", None)
            row["reason"] = _first_sentence(
                getattr(idea, "thesis", "") or "", settings.DELIVERY_BRIEF_IDEA_REASON_MAXLEN)
        out.append(row)
    return out
```

In `build_morning_brief`, change the `discovery_adds` line:

```python
        "discovery_adds": _enrich_discovery_adds(_shelf_events_since(since)),
```

- [ ] **Step 4: Run to verify pass** → PASS (also re-run existing `test_build_brief_assembles_sections`, which degrades gracefully for NEWCO)
- [ ] **Step 5: Commit** — `git commit -am "feat(brief): enrich discovery ideas with shelf verdict/conviction/reason"`

---

### Task 6: Rewrite `render_brief_text` into sectioned layout

**Files:**
- Modify: `core/delivery/brief.py` (`render_brief_text`; add `_indent`, `_ipo_demand` already added)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Consumes: all helpers from Tasks 2–5 + `settings.DELIVERY_BRIEF_MAX_IDEAS`.
- Produces: sectioned plain text per spec §3; empty sections omitted; never raises.

- [ ] **Step 1: Write the failing tests**

```python
def _full_brief():
    return {
        "date": "2026-07-27", "headline": "A cautious day.",
        "portfolio": {"portfolio_value": 620904.0, "total_pnl_pct": -5.9},
        "advisor_flags": [{"symbol": "OLDCO", "verdict": "EXIT", "reason": "stop breached"}],
        "regime": {"label": "RISK_OFF"},
        "overnight": [{"headline": "RBI eased foreign-investor rules.", "severity": "HIGH"}],
        "earnings_soon": [{"symbol": "SUZLON", "date": "2026-07-28"}],
        "discovery_adds": [{"symbol": "ACMESOLAR", "verdict": "BUY", "conviction": 0.65,
                            "reason": "One of the most efficient renewable operators."}],
        "ipo_watch": [{"symbol": "XTRANET", "company": "Xtranet", "status": "current",
                       "total_x": 8.2, "qib_x": 12.0, "retail_x": 3.0}],
        "lockin_flags": [],
    }

def test_render_full_brief_has_sections_and_glosses():
    t = br.render_brief_text(_full_brief())
    for h in ("MORNING BRIEF · 27 Jul 2026", "SUMMARY", "YOUR PORTFOLIO",
              "NEEDS ATTENTION", "MARKET CONDITIONS", "OVERNIGHT — HIGH-IMPACT NEWS",
              "EARNINGS THIS WEEK", "IDEAS THE TOOL IS RESEARCHING", "IPOs OPEN NOW"):
        assert h in t
    assert "Cautious (RISK_OFF)" in t
    assert "down 5.9% since inception" in t
    assert "OLDCO  Consider exiting — stop breached" in t
    assert "ACMESOLAR   BUY · 65%" in t
    assert "One of the most efficient renewable operators." in t
    assert "8.2× overall (QIB 12×, retail 3×)" in t
    assert "never personal advice" in t

def test_render_hides_empty_sections():
    b = _full_brief()
    b.update({"overnight": [], "earnings_soon": [], "discovery_adds": [],
              "ipo_watch": [], "advisor_flags": []})
    t = br.render_brief_text(b)
    for absent in ("OVERNIGHT", "EARNINGS THIS WEEK", "IDEAS THE TOOL", "IPOs OPEN NOW", "NEEDS ATTENTION"):
        assert absent not in t
    assert "YOUR PORTFOLIO" in t and "Nothing needs your attention today." in t
```

Also update the older `test_build_brief_assembles_sections` render assertion (line ~54): keep tokens that still appear (`RISK_OFF`, `OLDCO`, `EXIT` → now "Consider exiting"; change `"EXIT"` token check to `"Consider exiting"`). Keep `NEWCO` (rendered as a bare idea bullet).

- [ ] **Step 2: Run to verify fail** → FAIL
- [ ] **Step 3: Implement**

```python
def _indent(text: str, width: int = 2) -> str:
    import textwrap
    pad = " " * width
    return textwrap.fill(" ".join((text or "").split()), width=74,
                         initial_indent=pad, subsequent_indent=pad)


def render_brief_text(brief: dict) -> str:
    from datetime import date as _d
    bar = "═" * 42
    L: list[str] = []
    try:
        hdr = _d.fromisoformat(brief.get("date", "")).strftime("%d %b %Y")
    except Exception:
        hdr = brief.get("date", "")
    L += [bar, f"  MORNING BRIEF · {hdr}", bar, ""]

    headline = (brief.get("headline") or "").strip()
    if headline:
        L += ["SUMMARY", _indent(headline), ""]

    p = brief.get("portfolio")
    if p:
        pnl = p.get("total_pnl_pct", 0.0) or 0.0
        direction = "up" if pnl >= 0 else "down"
        flags = brief.get("advisor_flags", []) or []
        note = ("Nothing needs your attention today." if not flags
                else f"{len(flags)} holding(s) flagged — see below.")
        L += ["YOUR PORTFOLIO",
              f"  ₹{p.get('portfolio_value', 0):,.0f} — {direction} {abs(pnl):.1f}% since inception.",
              f"  {note}", ""]

    flags = brief.get("advisor_flags", []) or []
    if flags:
        L.append("NEEDS ATTENTION")
        for f in flags:
            verb = _VERDICT_PLAIN.get(f.get("verdict", ""), f.get("verdict", ""))
            reason = f.get("reason", "")
            L.append(f"  • {f['symbol']}  {verb}" + (f" — {reason}" if reason else ""))
        L.append("")

    regime = (brief.get("regime") or {}).get("label")
    if regime:
        word, gloss = _REGIME_PLAIN.get(regime, (regime.title(), ""))
        L += ["MARKET CONDITIONS",
              f"  {word} ({regime})" + (f" — {gloss}" if gloss else ""), ""]

    overnight = brief.get("overnight", []) or []
    if overnight:
        L.append("OVERNIGHT — HIGH-IMPACT NEWS")
        L += [f"  • {i['headline']}" for i in overnight]
        L.append("")

    earnings = brief.get("earnings_soon", []) or []
    if earnings:
        L.append("EARNINGS THIS WEEK   (your holdings)")
        L += [f"  • {e['symbol']}  — {_fmt_date(e['date'])}" for e in earnings]
        L.append("")

    adds = (brief.get("discovery_adds", []) or [])[: settings.DELIVERY_BRIEF_MAX_IDEAS]
    if adds:
        L += ["IDEAS THE TOOL IS RESEARCHING   (its own view — not personal advice)",
              "  The scanner flagged these; the tool rated each and is paper-testing the",
              "  thesis. Confidence = how strongly it backs its own call."]
        for a in adds:
            verdict, pct = a.get("verdict"), _pct(a.get("conviction"))
            head = f"  • {a['symbol']}"
            if verdict and pct:
                head += f"   {verdict} · {pct}"
            elif verdict:
                head += f"   {verdict}"
            L.append(head)
            if a.get("reason"):
                L.append(f"      {a['reason']}")
        L.append("")

    ipos = brief.get("ipo_watch", []) or []
    if ipos:
        L += ["IPOs OPEN NOW   (live demand — a data point, not a buy call)",
              "  × = times the issue was subscribed; high QIB/overall = institutional interest."]
        L += [f"  • {w['symbol']}  {w.get('company', '')}  ·  {_ipo_demand(w)}" for w in ipos]
        L.append("")

    lockin = brief.get("lockin_flags", []) or []
    if lockin:
        L.append("LOCK-IN EXPIRIES")
        L += [f"  • {lf['symbol']} {lf['kind']} on {lf['expiry']} — supply risk, not a signal"
              for lf in lockin]
        L.append("")

    L += ["─" * 42, "Research tool — information only, never personal advice."]
    return "\n".join(L).strip()
```

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/unit/test_delivery_brief.py -v` → all PASS
- [ ] **Step 5: Commit** — `git commit -am "feat(brief): sectioned plain-English render_brief_text"`

---

### Task 7: Docs update + full-suite A/B verification

**Files:**
- Modify: `docs/ARCHITECTURE.md` (§8 "Morning brief" bullet, ~line 236-239)

- [ ] **Step 1: Update ARCHITECTURE.md §8** — replace the morning-brief bullet with:

```markdown
- **Morning brief** (`core/delivery/brief.py`): a sectioned, plain-English plain-text
  brief (Summary → Portfolio → Needs-attention → Market conditions → Overnight →
  Earnings-this-week → Ideas-the-tool-is-researching → IPOs → Lock-in), each section
  auto-hidden when empty. Regime/verdict shown in plain words with the technical term in
  parens; overnight items use the clean one-sentence LLM `summary` (deduped by content,
  not URL); ideas carry the tool's own verdict + confidence% + a one-line reason from the
  idea's thesis — framed as a research view, never personal advice; IPOs show live
  subscription demand. Exactly one BULK-tier narration call for the top-line SUMMARY, with a
  deterministic fallback. Ideas explained: the scanner screens the market → a passing name
  goes on the research shelf → the tool forms a view and paper-trades it to test the thesis.
```

- [ ] **Step 2: Commit docs** — `git commit -am "docs(architecture): describe redesigned morning brief"`
- [ ] **Step 3: Run the full suite on this branch** — `python -m pytest -q 2>&1 | tail -30` → record pass/fail counts + the fail-set.
- [ ] **Step 4: A/B the fail-set** — create a temp worktree at the merge-base, run `python -m pytest -q` there, and confirm this branch's fail-set is **byte-identical** to that baseline (only the known-red set differs, no new failures introduced by this work).
- [ ] **Step 5: Report** — summarize new tests added, suite delta, and A/B result. Hold merge/push for the user (deploy timing).

---

## Self-Review

**Spec coverage:**
- §3 layout → Task 6. §4.1 maps → Task 2. §4.2 helpers → Tasks 2–4. §4.3 enrichment → Tasks 3/4/5. §4.4 render → Task 6. §5 config → Task 1. §6 tests → every task + Task 7 A/B. §7 docs → Task 7. All covered.

**Placeholder scan:** No TBD/TODO; every code + test step is concrete.

**Type consistency:** `_pct/_trim_words/_clean_headline/_first_sentence/_fmt_date/_norm_text/_dedup_overnight/_dedup_ipos/_ipo_demand/_enrich_discovery_adds/_indent` — names/signatures identical across the tasks that define and consume them. `settings.DELIVERY_BRIEF_*` names identical between Task 1 and Tasks 3/4/5/6.
