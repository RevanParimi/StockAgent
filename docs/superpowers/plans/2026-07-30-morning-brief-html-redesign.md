# Morning Brief — HTML Email Redesign + Data Engineering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send the 08:50 IST morning brief as a styled HTML email (multipart/alternative, plain-text fallback kept) and engineer the underlying data (de-dup overnight news, richer portfolio line, sharper "why it matters", less summary echo).

**Architecture:** Two pure renderers of one brief dict — the existing `render_brief_text` (unchanged; fallback + push/Inbox body) and a new `render_brief_html`. The HTML threads through `deliver()` → `send_email()` as the second MIME part, and through the dormant Atlas outbox payload so it survives the Aug cutover. All data fixes happen at build time in `build_morning_brief`. Everything degrades to today's behavior on any failure.

**Tech Stack:** Python 3 (stdlib `email.mime`, `html`, `re`), pytest, `cfg()`/config.yaml settings.

## Global Constraints

- **Never personal advice** — research-framed copy only; no buy/avoid calls, no GMP/listing-gain. (Verbatim stance from all prior brief specs.)
- **No new LLM calls** — exactly one BULK narration call per brief; HTML + de-dup are deterministic; "why it matters" / summary changes are prompt-only tweaks to the existing call.
- **Config-over-hardcode, no env= for toggles** — all new tunables go through `cfg("delivery.*")` in `config.yaml`; secrets keep env=, these do not.
- **Every delivery function is non-fatal** — logs + degrades, never raises. `render_brief_html` must never raise (caller falls back to text-only email).
- **`html_body=None` path must be byte-identical to today's plain email** — do not regress `test_email_without_attachment_unchanged`.
- **Push and in-app Inbox keep the plain-text `body`** — HTML is email-only.
- **Deploy-kill window:** do NOT push to main 16:25–17:15 IST on trading days (weekends fine).
- Full-suite fail-set baseline is **GREEN** (2292P/0F/0E as of 2026-07-29) — any new failure is a real regression.
- Email-safety for HTML: table layout (`role="presentation"`), inline `style=` on rendered elements, system-font stack (no webfonts), no external image `src`, Unicode marks only.

---

## File Structure

- `core/delivery/brief.py` — **modify.** New `render_brief_html(brief)`, `_HTML`/`_FONT` tokens, `_esc`, `_dark_css`; enhanced `_dedup_overnight` + new `_salient_tokens`; new `_portfolio_extras`, `_dedupe_notes`; `_PROMPT` copy tweak; `run_morning_brief` wiring.
- `core/delivery/channels.py` — **modify.** `send_email(..., html_body=None)` builds multipart/alternative; `deliver(..., html_body=None)` threads it (push unchanged).
- `core/delivery/outbox.py` — **modify.** `enqueue_message(..., html_body=None)` stores `html` in payload, drops the enqueue-time 1500 cap; `_send_row` applies push cap and passes html to email.
- `src/backend/shared/config/settings/base.py` — **modify.** Three new `DELIVERY_BRIEF_*` settings.
- `config.yaml` — **modify.** Three new `delivery.*` keys.
- `tests/unit/test_delivery_brief.py` — **modify.** De-dup, portfolio extras, note-dedupe, HTML render tests.
- `tests/unit/test_delivery_channels.py` — **modify.** `send_email`/`deliver` html_body tests.
- `tests/unit/test_delivery_outbox*.py` — **modify/create.** Outbox html carry-through test.

---

## Task 1: Overnight de-dup — salient-entity clustering

**Files:**
- Modify: `core/delivery/brief.py` (`_dedup_overnight`, new `_salient_tokens`, `_overnight_items` call)
- Modify: `src/backend/shared/config/settings/base.py:897-907` (add 2 settings)
- Modify: `config.yaml:435` (add 2 keys)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Produces: `_salient_tokens(headline: str, stopwords: frozenset[str]) -> set[str]`; `_dedup_overnight(items, threshold, max_items, min_shared: int = 0, stopwords: frozenset = frozenset())`.

- [ ] **Step 1: Write the failing test** (append to `tests/unit/test_delivery_brief.py`)

```python
def test_dedup_overnight_merges_salient_entities():
    # The two NRI/OCI items are one story worded differently; the rupee item is separate.
    items = [
        {"headline": "RBI measures boost rupee amid Middle East conflict.", "severity": "HIGH"},
        {"headline": "Govt raises equity limits for NRIs, OCIs to boost foreign investment.", "severity": "HIGH"},
        {"headline": "RBI increases NRI/OCI investment limits without SEBI registration.", "severity": "HIGH"},
    ]
    stop = frozenset(br.settings.DELIVERY_BRIEF_OVERNIGHT_STOPWORDS)
    out = br._dedup_overnight(items, 0.6, 5, min_shared=2, stopwords=stop)
    heads = [o["headline"] for o in out]
    assert len(out) == 2                                   # 3 -> 2
    assert any("rupee" in h.lower() for h in heads)        # rupee survives
    assert sum("nri" in h.lower() or "oci" in h.lower() for h in heads) == 1  # one NRI row


def test_dedup_overnight_min_shared_zero_is_legacy():
    # min_shared=0 disables the entity path — unrelated items are NOT merged.
    items = [
        {"headline": "Govt raises equity limits for NRIs, OCIs.", "severity": "HIGH"},
        {"headline": "RBI increases NRI/OCI investment limits without SEBI.", "severity": "HIGH"},
    ]
    out = br._dedup_overnight(items, 0.6, 5)               # legacy call, no entity merge
    assert len(out) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_brief.py::test_dedup_overnight_merges_salient_entities -v`
Expected: FAIL (`_dedup_overnight` has no `min_shared`/`stopwords` kwargs; `DELIVERY_BRIEF_OVERNIGHT_STOPWORDS` missing).

- [ ] **Step 3: Add the two settings** in `src/backend/shared/config/settings/base.py` right after line 899 (`DELIVERY_BRIEF_OVERNIGHT_MAXLEN`):

```python
DELIVERY_BRIEF_OVERNIGHT_DEDUP_MIN_SHARED: int = int(cfg("delivery.brief_overnight_dedup_min_shared_entities", fallback=2))
DELIVERY_BRIEF_OVERNIGHT_STOPWORDS: list = list(cfg("delivery.brief_overnight_stopwords", fallback=[
    "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "as", "at", "by",
    "with", "from", "up", "its", "into", "over", "without", "amid", "new", "plan",
    "move", "step", "measure", "raise", "boost", "increase", "hike", "support", "ease",
    "rbi", "govt", "government", "india", "indian", "market", "stock", "share",
    "sensex", "nifty",
]))
```

- [ ] **Step 4: Add the config.yaml keys** under the delivery block after line 435 (`brief_earnings_watch_maxlen`):

```yaml
  # Overnight de-dup (2026-07-30): cluster near-duplicate stories by salient entity
  brief_overnight_dedup_min_shared_entities: 2   # >= this many shared salient entities => same story
  brief_overnight_stopwords: [the, a, an, of, for, to, in, on, and, or, as, at, by,
    with, from, up, its, into, over, without, amid, new, plan, move, step, measure,
    raise, boost, increase, hike, support, ease, rbi, govt, government, india, indian,
    market, stock, share, sensex, nifty]
```

- [ ] **Step 5: Implement `_salient_tokens` and extend `_dedup_overnight`** in `core/delivery/brief.py`. Add the helper just above `_dedup_overnight` (after `_norm_text`):

```python
def _salient_tokens(headline: str, stopwords: frozenset) -> set[str]:
    """Distinctive-entity set for near-duplicate detection: slash-split (NRI/OCI ->
    two tokens), keep alnum, drop stopwords + short non-numeric tokens, crude
    singularise trailing 's'. Generic actors/verbs (rbi, boost, raise…) live in the
    stoplist so two stories don't cluster just for sharing them."""
    s = re.sub(r"[^a-z0-9 ]", " ", (headline or "").lower().replace("/", " "))
    out: set[str] = set()
    for t in s.split():
        if t.endswith("s") and len(t) > 3:
            t = t[:-1]
        if t in stopwords or (len(t) < 3 and not t.isdigit()):
            continue
        out.add(t)
    return out
```

Then change `_dedup_overnight`'s signature and merge test:

```python
def _dedup_overnight(items: list[dict], threshold: float, max_items: int,
                     min_shared: int = 0, stopwords: frozenset = frozenset()) -> list[dict]:
    """Collapse near-duplicate stories and keep the longest headline per cluster.
    Two items merge when they share a headline prefix, Jaccard>=threshold, OR (when
    min_shared>0) share >= min_shared salient entities. First-seen order, capped."""
    kept: list[dict] = []
    kept_norm: list[str] = []
    kept_tok: list[set] = []
    kept_sal: list[set] = []
    for it in items:
        norm = _norm_text(it["headline"])
        toks = set(norm.split())
        if not toks:
            continue
        sal = _salient_tokens(it["headline"], stopwords) if min_shared else set()
        dup = None
        for i, kn in enumerate(kept_norm):
            inter = len(toks & kept_tok[i])
            union = len(toks | kept_tok[i]) or 1
            entity_hit = min_shared and len(sal & kept_sal[i]) >= min_shared
            if norm in kn or kn in norm or (inter / union) >= threshold or entity_hit:
                dup = i
                break
        if dup is None:
            kept.append(it); kept_norm.append(norm); kept_tok.append(toks); kept_sal.append(sal)
        elif len(it["headline"]) > len(kept[dup]["headline"]):
            kept[dup] = it; kept_norm[dup] = norm; kept_tok[dup] = toks; kept_sal[dup] = sal
    return kept[:max_items]
```

Update the caller `_overnight_items` (around line 258) to pass the new args:

```python
        return _dedup_overnight(
            items, settings.DELIVERY_BRIEF_OVERNIGHT_DEDUP_THRESHOLD, mi,
            min_shared=settings.DELIVERY_BRIEF_OVERNIGHT_DEDUP_MIN_SHARED,
            stopwords=frozenset(settings.DELIVERY_BRIEF_OVERNIGHT_STOPWORDS))
```

- [ ] **Step 6: Run to verify both tests pass**

Run: `python -m pytest tests/unit/test_delivery_brief.py -k dedup_overnight -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/delivery/brief.py src/backend/shared/config/settings/base.py config.yaml tests/unit/test_delivery_brief.py
git commit -m "feat(brief): salient-entity de-dup collapses near-duplicate overnight stories"
```

---

## Task 2: Richer portfolio line — best/worst/count/last-exit from the digest

**Files:**
- Modify: `core/delivery/brief.py` (new `_portfolio_extras`, call in `build_morning_brief`)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Produces: `_portfolio_extras(digest: dict) -> dict` with optional keys `holdings_count:int`, `best:{symbol,pnl_pct}`, `worst:{symbol,pnl_pct}`, `all_below_cost:bool`, `last_exit:{symbol,pnl_pct}`. `build_morning_brief` merges these into `brief["portfolio"]`.

- [ ] **Step 1: Write the failing test**

```python
def test_portfolio_extras_best_worst_and_last_exit():
    digest = {
        "holdings": [
            {"symbol": "SUZLON", "pnl_pct": -10.9},
            {"symbol": "PAYTM", "pnl_pct": -2.3},
            {"symbol": "TATAELXSI", "pnl_pct": -2.9},
        ],
        "trades": [
            {"symbol": "IDFCFIRSTB", "side": "SELL", "pnl_pct": 6.1},
        ],
    }
    x = br._portfolio_extras(digest)
    assert x["holdings_count"] == 3
    assert x["best"] == {"symbol": "PAYTM", "pnl_pct": -2.3}
    assert x["worst"] == {"symbol": "SUZLON", "pnl_pct": -10.9}
    assert x["all_below_cost"] is True
    assert x["last_exit"] == {"symbol": "IDFCFIRSTB", "pnl_pct": 6.1}


def test_portfolio_extras_empty_digest_is_blank():
    assert br._portfolio_extras({}) == {}
    assert br._portfolio_extras({"holdings": []}) == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_brief.py -k portfolio_extras -v`
Expected: FAIL (`_portfolio_extras` not defined).

- [ ] **Step 3: Implement `_portfolio_extras`** in `core/delivery/brief.py` (add after `_earnings_watch`):

```python
def _portfolio_extras(digest: dict) -> dict:
    """Best/worst holding, count, all-below-cost, and the day's last realized exit,
    computed from the digest. Every key is optional — an empty/partial digest yields
    a subset (or {}) and the renderers degrade cleanly."""
    out: dict = {}
    rows = [h for h in (digest.get("holdings") or [])
            if isinstance(h.get("pnl_pct"), (int, float))]
    if rows:
        best = max(rows, key=lambda h: h["pnl_pct"])
        worst = min(rows, key=lambda h: h["pnl_pct"])
        out["holdings_count"] = len(rows)
        out["best"] = {"symbol": best.get("symbol", ""), "pnl_pct": best["pnl_pct"]}
        out["worst"] = {"symbol": worst.get("symbol", ""), "pnl_pct": worst["pnl_pct"]}
        out["all_below_cost"] = all(h["pnl_pct"] < 0 for h in rows)
    sells = [t for t in (digest.get("trades") or [])
             if t.get("side") == "SELL" and isinstance(t.get("pnl_pct"), (int, float))]
    if sells:
        last = sells[-1]
        out["last_exit"] = {"symbol": last.get("symbol", ""), "pnl_pct": last["pnl_pct"]}
    return out
```

- [ ] **Step 4: Wire into `build_morning_brief`.** After the `portfolio["portfolio_value"] = ...` line (~line 428), add:

```python
        portfolio.update(_portfolio_extras(digest))
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/unit/test_delivery_brief.py -k portfolio_extras -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/delivery/brief.py tests/unit/test_delivery_brief.py
git commit -m "feat(brief): enrich portfolio with best/worst/count/last-exit from digest"
```

---

## Task 3: Sharper "why it matters" + less summary echo (prompt-only + note de-dupe)

**Files:**
- Modify: `core/delivery/brief.py` (`_PROMPT`, new `_dedupe_notes`, call in `build_morning_brief`)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Produces: `_dedupe_notes(notes: list[str]) -> list[str]` — blanks a note that near-duplicates an earlier one (same-order length preserved).

- [ ] **Step 1: Write the failing test**

```python
def test_dedupe_notes_blanks_near_duplicate():
    notes = [
        "Higher NRI/OCI limits could boost equity inflows.",
        "Eased NRI/OCI limits boost equity inflows.",     # near-dup of #0
        "Rupee support curbs imported inflation.",
    ]
    out = br._dedupe_notes(notes)
    assert out[0] == notes[0]
    assert out[1] == ""                                    # duplicate blanked
    assert out[2] == notes[2]
    assert len(out) == len(notes)                          # order/length preserved
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_brief.py::test_dedupe_notes_blanks_near_duplicate -v`
Expected: FAIL (`_dedupe_notes` not defined).

- [ ] **Step 3: Implement `_dedupe_notes`** in `core/delivery/brief.py` (after `_dedup_overnight`):

```python
def _dedupe_notes(notes: list[str]) -> list[str]:
    """Blank a relevance note that near-duplicates an earlier one (Jaccard>=0.6 on
    normalized tokens) so 'why it matters' lines don't echo across items."""
    out: list[str] = []
    seen: list[set] = []
    for n in notes:
        toks = set(_norm_text(n).split())
        dup = any(toks and s and len(toks & s) / (len(toks | s) or 1) >= 0.6 for s in seen)
        out.append("" if dup else n)
        if not dup and toks:
            seen.append(toks)
    return out
```

- [ ] **Step 4: Apply it in `build_morning_brief`.** Where overnight notes are attached (~line 480), de-dupe first:

```python
    overnight_notes = _dedupe_notes(overnight_notes)
    for idx, item in enumerate(brief["overnight"]):
        if idx < len(overnight_notes) and overnight_notes[idx]:
            item["note"] = overnight_notes[idx]
```

- [ ] **Step 5: Tighten `_PROMPT`** (copy-only; no test asserts prompt text). Replace the headline + overnight_notes instructions in `_PROMPT` so the summary stays high-level and notes are distinct:

```python
_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-4 sentence morning "headline": the market regime, the single overarching
THEME of today's news, and the portfolio's posture. Do NOT enumerate or restate the
individual overnight items (they are listed separately below as bullets). Research
tone; NEVER the word "advice".

Portfolio: {portfolio}
Escalations flagged yesterday: {escalations}
Market regime: {regime}
Overnight HIGH-severity items (numbered):
{overnight}
Earnings within 3 sessions: {earnings}
New discovery-shelf ideas: {adds}

Also produce "overnight_notes": one short line (<=12 words) per overnight item, in the
SAME numbered order, each stating a DISTINCT, portfolio-relevant consequence for an
Indian-equity investor. Do not repeat wording across notes. Empty list if none.

Respond with JSON: {{"headline": "<2-4 sentences>", "overnight_notes": ["<line 1>", ...]}}"""
```

- [ ] **Step 6: Run brief tests to confirm no regression**

Run: `python -m pytest tests/unit/test_delivery_brief.py -v`
Expected: PASS (existing + new `_dedupe_notes` test).

- [ ] **Step 7: Commit**

```bash
git add core/delivery/brief.py tests/unit/test_delivery_brief.py
git commit -m "feat(brief): distinct why-it-matters notes + high-level summary (no bullet echo)"
```

---

## Task 4: `render_brief_html` — clean-fintech email-safe renderer

**Files:**
- Modify: `core/delivery/brief.py` (add `import html as _htmlmod`; `_HTML`, `_FONT`, `_esc`, `_dark_css`, `render_brief_html`)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Consumes: brief dict (incl. `portfolio` extras from Task 2, deduped `overnight` from Task 1), existing helpers `_pct`, `_fmt_date`, `_REGIME_PLAIN`, `_VERDICT_PLAIN`, `_ipo_lean`, `_ipo_demand`, `settings.DELIVERY_BRIEF_MAX_IDEAS`.
- Produces: `render_brief_html(brief: dict) -> str` — a full standalone HTML document; never raises.

- [ ] **Step 1: Write the failing test**

```python
def test_render_brief_html_full_and_safe():
    brief = {
        "date": "2026-07-30",
        "headline": "Calm NORMAL market; policy-heavy overnight tape.",
        "portfolio": {"portfolio_value": 556826.57, "total_pnl_pct": -6.81,
                      "holdings_count": 8, "all_below_cost": True,
                      "best": {"symbol": "PAYTM", "pnl_pct": -2.3},
                      "worst": {"symbol": "SUZLON", "pnl_pct": -10.9},
                      "last_exit": {"symbol": "IDFCFIRSTB", "pnl_pct": 6.1}},
        "advisor_flags": [],
        "regime": {"label": "NORMAL"},
        "overnight": [{"headline": "RBI steadies the rupee.", "severity": "HIGH",
                       "note": "Curbs imported-inflation risk."}],
        "earnings_soon": [{"symbol": "WAAREEENER", "date": "2026-07-30", "watch": ""}],
        "discovery_adds": [],
        "ipo_watch": [{"symbol": "XTRANET", "company": "Xtranet Technologies",
                       "status": "current", "issue_price": 127.0,
                       "qib_x": None, "retail_x": None, "total_x": None}],
        "lockin_flags": [{"symbol": "KISSHT", "kind": "anchor_remaining", "expiry": "2026-08-06"}],
    }
    html = br.render_brief_html(brief)
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<script" not in html.lower()                       # no scripts
    assert "http://" not in html and 'src="https://' not in html  # no external images
    assert 'style="' in html                                    # inline styles present
    for token in ("Morning Brief", "5,56,827", "PAYTM", "SUZLON", "IDFCFIRSTB",
                  "RBI steadies the rupee.", "Curbs imported-inflation risk.",
                  "WAAREEENER", "XTRANET", "KISSHT",
                  "never personal advice"):
        assert token in html


def test_render_brief_html_never_raises_on_empty():
    assert isinstance(br.render_brief_html({}), str)
    assert isinstance(br.render_brief_html({"date": "2026-07-30", "portfolio": None}), str)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_brief.py -k render_brief_html -v`
Expected: FAIL (`render_brief_html` not defined).

- [ ] **Step 3: Add tokens + helpers** near the top of `core/delivery/brief.py` (after the existing `_VERDICT_PLAIN` block). Add `import html as _htmlmod` to the imports.

```python
# -- HTML email renderer (clean-fintech, email-safe) — redesign 2026-07-30 -----
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_HTML = {
    "page": "#e9eef3", "card": "#ffffff", "ink": "#0f172a", "body": "#334155",
    "muted": "#64748b", "hair": "#e4e9f0", "hair_soft": "#eef2f7",
    "accent": "#0f766e", "accent_deep": "#115e59", "neg": "#b91c1c", "pos": "#15803d",
    "warn": "#b45309", "hi_bg": "#fdeceb", "hi_ink": "#b91c1c",
    "pill_bg": "#ecfdf5", "pill_bd": "#a7f3d0", "pill_ink": "#0f766e", "kpi": "#f4faf9",
}


def _esc(s) -> str:
    return _htmlmod.escape("" if s is None else str(s))


def _inr(v) -> str:
    """Indian-format rupee, e.g. 556826.57 -> '5,56,827' (no decimals)."""
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return "0"
    sign, n = ("-" if n < 0 else ""), abs(n)
    s = str(n)
    if len(s) <= 3:
        return sign + s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:]); head = head[:-2]
    parts.insert(0, head)
    return sign + ",".join(parts) + "," + tail


def _dark_css() -> str:
    """Progressive-enhancement dark overrides (clients honoring <style>+media)."""
    return ("@media (prefers-color-scheme:dark){"
            ".sa-page{background:#0a0f1a!important}"
            ".sa-card{background:#111a2b!important;border-color:#233149!important}"
            ".sa-ink{color:#f1f5f9!important}.sa-body{color:#cbd5e1!important}"
            ".sa-muted{color:#94a3b8!important}"
            ".sa-kpi{background:#0e1b22!important;border-color:#233149!important}"
            ".sa-foot{background:#0e1728!important}.sa-div{border-color:#233149!important}"
            ".sa-neg{color:#f87171!important}.sa-pos{color:#4ade80!important}}")
```

- [ ] **Step 4: Implement `render_brief_html`** in `core/delivery/brief.py` (place after `render_brief_text`). It mirrors the text renderer section-for-section and is wrapped so it never raises.

```python
def render_brief_html(brief: dict) -> str:
    """Styled, email-safe HTML brief (redesign 2026-07-30). Full standalone
    document; tables + inline styles + system fonts, dark via <style> media.
    Mirrors render_brief_text section-for-section; never raises."""
    H = _HTML
    try:
        return _render_brief_html_inner(brief, H)
    except Exception as exc:
        logger.warning("[brief] html render failed (non-fatal): %s", exc)
        # Minimal but valid fallback so the email still has an HTML part.
        safe = _esc(render_brief_text(brief)).replace("\n", "<br>")
        return ("<!doctype html><html><body style=\"font-family:%s;white-space:normal\">"
                "<pre style=\"font-family:%s\">%s</pre></body></html>" % (_FONT, _FONT, safe))


def _section(title: str, inner_html: str, H: dict) -> str:
    return (
        '<tr><td style="padding:20px 26px">'
        f'<div style="font:700 11.5px {_FONT};letter-spacing:.13em;text-transform:uppercase;'
        f'color:{H["accent"]};margin:0 0 12px" class="sa-ink">{_esc(title)}'
        f'<div style="height:2px;width:26px;background:{H["accent"]};border-radius:2px;'
        'margin:7px 0 0;opacity:.55"></div></div>'
        f'{inner_html}</td></tr>'
        f'<tr><td style="padding:0 26px"><div class="sa-div" '
        f'style="height:1px;background:{H["hair"]}"></div></td></tr>'
    )


def _render_brief_html_inner(brief: dict, H: dict) -> str:
    try:
        hdr = date.fromisoformat(brief.get("date", "")).strftime("%A, %d %B %Y")
    except Exception:
        hdr = brief.get("date", "")

    rows: list[str] = []

    # SUMMARY
    headline = (brief.get("headline") or "").strip()
    if headline:
        rows.append(
            '<tr><td style="padding:22px 26px">'
            f'<p class="sa-body" style="margin:0;font:400 15px/1.6 {_FONT};color:{H["body"]}">'
            f'{_esc(headline)}</p></td></tr>'
            f'<tr><td style="padding:0 26px"><div class="sa-div" style="height:1px;background:{H["hair"]}"></div></td></tr>')

    # YOUR PORTFOLIO (KPI card)
    p = brief.get("portfolio")
    if p:
        pnl = p.get("total_pnl_pct", 0.0) or 0.0
        arrow = "▲" if pnl >= 0 else "▼"
        chip_cls, chip_ink = ("sa-pos", H["pos"]) if pnl >= 0 else ("sa-neg", H["neg"])
        meta_bits = []
        if p.get("holdings_count"):
            cost = "all currently below cost" if p.get("all_below_cost") else "mixed vs cost"
            meta_bits.append(f'<b style="color:{H["body"]}">{p["holdings_count"]} holdings</b>, {cost}.')
        if p.get("best"):
            meta_bits.append(f'Best <b style="color:{H["body"]}">{_esc(p["best"]["symbol"])} {p["best"]["pnl_pct"]:+.1f}%</b>')
        if p.get("worst"):
            meta_bits.append(f'Worst <b style="color:{H["body"]}">{_esc(p["worst"]["symbol"])} {p["worst"]["pnl_pct"]:+.1f}%</b>')
        meta = (' <span style="color:%s">·</span> ' % H["hair"]).join(meta_bits)
        exit_line = ""
        if p.get("last_exit"):
            le = p["last_exit"]
            exit_line = (f'<p class="sa-muted" style="margin:12px 0 0;font:400 13px/1.5 {_FONT};color:{H["muted"]}">'
                         f'Yesterday: autopilot exited <b style="color:{H["body"]}">{_esc(le["symbol"])} {le["pnl_pct"]:+.1f}%</b> on a thesis break.</p>')
        inner = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="sa-kpi" '
            f'style="background:{H["kpi"]};border:1px solid {H["hair"]};border-radius:12px"><tr><td style="padding:18px 20px">'
            f'<div class="sa-ink" style="font:700 34px {_FONT};color:{H["ink"]};letter-spacing:-.02em">₹{_inr(p.get("portfolio_value", 0))}</div>'
            f'<div style="margin:12px 0 0"><span class="{chip_cls}" style="display:inline-block;font:600 12.5px {_FONT};'
            f'color:{chip_ink};background:{H["hi_bg"] if pnl < 0 else H["pill_bg"]};padding:4px 10px;border-radius:999px">'
            f'{arrow} {abs(pnl):.1f}% since inception</span></div>'
            + (f'<p class="sa-muted" style="margin:14px 0 0;font:400 13.5px/1.55 {_FONT};color:{H["muted"]}">{meta}</p>' if meta else "")
            + exit_line
            + '</td></tr></table>')
        rows.append(_section("Your portfolio", inner, H))

    # NEEDS ATTENTION
    flags = brief.get("advisor_flags", []) or []
    if flags:
        items = []
        for f in flags:
            verb = _VERDICT_PLAIN.get(f.get("verdict", ""), f.get("verdict", ""))
            reason = f.get("reason", "")
            items.append(
                f'<div style="padding:8px 0"><span class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">'
                f'{_esc(f["symbol"])}</span> <span style="color:{H["warn"]};font:600 13px {_FONT}">{_esc(verb)}</span>'
                + (f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:3px 0 0">{_esc(reason)}</div>' if reason else "")
                + '</div>')
        rows.append(_section("Needs attention", "".join(items), H))

    # MARKET CONDITIONS
    regime = (brief.get("regime") or {}).get("label")
    if regime:
        word, gloss = _REGIME_PLAIN.get(regime, (regime.title(), ""))
        inner = (
            f'<span style="display:inline-block;background:{H["pill_bg"]};border:1px solid {H["pill_bd"]};'
            f'color:{H["pill_ink"]};font:700 13px {_FONT};padding:6px 12px;border-radius:999px">{_esc(word)} · {_esc(regime)}</span>'
            + (f'<p class="sa-muted" style="margin:10px 0 0;font:400 13.5px/1.5 {_FONT};color:{H["muted"]}">{_esc(gloss)}</p>' if gloss else ""))
        rows.append(_section("Market conditions", inner, H))

    # OVERNIGHT (table with severity chip)
    overnight = brief.get("overnight", []) or []
    if overnight:
        trs = []
        for i in overnight:
            note = (i.get("note") or "").strip()
            why = (f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">'
                   f'<span style="color:{H["accent"]};font-weight:600">Why it matters:</span> {_esc(note)}</div>') if note else ""
            trs.append(
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px/1.45 {_FONT};color:{H["ink"]}">{_esc(i["headline"])}</div>{why}</td>'
                f'<td style="padding:12px 0 12px 12px;text-align:right;width:54px;vertical-align:top">'
                f'<span style="display:inline-block;font:700 10.5px {_FONT};letter-spacing:.06em;padding:3px 8px;'
                f'border-radius:6px;background:{H["hi_bg"]};color:{H["hi_ink"]}">{_esc(i.get("severity", "HIGH"))}</span></td></tr>')
        rows.append(_section("Overnight · high-impact news",
                             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(trs)}</table>', H))

    # EARNINGS
    earnings = brief.get("earnings_soon", []) or []
    if earnings:
        trs = []
        for e in earnings:
            watch = (e.get("watch") or "").strip()
            tail = f"watch: {watch}" if watch else "results & guidance are the next catalyst."
            trs.append(
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">{_esc(e["symbol"])}</div>'
                f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">You hold this — {_esc(tail)}</div></td>'
                f'<td style="padding:12px 0;text-align:right;white-space:nowrap;width:96px;color:{H["ink"]};font:600 14px {_FONT}" class="sa-ink">{_esc(_fmt_date(e["date"]))}</td></tr>')
        rows.append(_section("Earnings this week · your holdings",
                             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(trs)}</table>', H))

    # IDEAS
    adds = (brief.get("discovery_adds", []) or [])[: settings.DELIVERY_BRIEF_MAX_IDEAS]
    if adds:
        trs = []
        for a in adds:
            verdict, pct = a.get("verdict"), _pct(a.get("conviction"))
            tag = (f'<span style="color:{H["accent"]};font:600 12.5px {_FONT}">{_esc(verdict)}'
                   + (f' · {pct}' if pct else "") + '</span>') if verdict else ""
            reason = a.get("reason", "")
            trs.append(
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">{_esc(a["symbol"])} &nbsp;{tag}</div>'
                + (f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">{_esc(reason)}</div>' if reason else "")
                + '</td></tr>')
        rows.append(_section("Ideas the tool is researching · its own view, not advice",
                             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(trs)}</table>', H))

    # IPOs
    ipos = brief.get("ipo_watch", []) or []
    if ipos:
        trs = []
        for w in ipos:
            lean, reason = _ipo_lean(w)
            demand = _ipo_demand(w) if lean != "data pending" else "subscription not yet reported"
            price = f'₹{_inr(w.get("issue_price"))}' if w.get("issue_price") else ""
            leancol = (f'<span style="color:{H["warn"]};font-weight:600">{_esc(lean)}</span>'
                       if lean in ("data pending", "SOFT DEMAND") else
                       f'<span style="color:{H["accent"]};font-weight:600">{_esc(lean)}</span>')
            trs.append(
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">{_esc(w["symbol"])} '
                f'<span class="sa-muted" style="color:{H["muted"]};font-weight:600;font-size:12.5px">{_esc(w.get("company", ""))}</span></div>'
                f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">Lean: {leancol} — {_esc(demand)}</div></td>'
                f'<td style="padding:12px 0;text-align:right;white-space:nowrap;width:96px;color:{H["ink"]};font:600 14px {_FONT}" class="sa-ink">{price}</td></tr>')
        rows.append(_section("IPOs open now · research view, not advice",
                             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(trs)}</table>', H))

    # LOCK-IN
    lockin = brief.get("lockin_flags", []) or []
    if lockin:
        trs = []
        for lf in lockin:
            trs.append(
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">{_esc(lf["symbol"])} '
                f'<span class="sa-muted" style="color:{H["muted"]};font-weight:600;font-size:12.5px">{_esc(lf.get("kind", ""))}</span></div>'
                f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">Supply risk as shares free up — context, not a signal.</div></td>'
                f'<td style="padding:12px 0;text-align:right;white-space:nowrap;width:96px;color:{H["ink"]};font:600 14px {_FONT}" class="sa-ink">{_esc(_fmt_date(lf.get("expiry", "")))}</td></tr>')
        rows.append(_section("Lock-in expiries",
                             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(trs)}</table>', H))

    # strip the trailing divider row of the last section for a clean end
    body_rows = "".join(rows)

    button = ""
    url = (getattr(settings, "APP_PUBLIC_URL", "") or "").rstrip("/")
    if url:
        button = (f'<a href="{_esc(url)}/" style="display:inline-block;background:{H["accent_deep"]};'
                  f'color:#ffffff;text-decoration:none;font:600 14px {_FONT};padding:11px 20px;border-radius:9px">Open StockAgent →</a>')

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f'<style>{_dark_css()}</style></head>'
        f'<body class="sa-page" style="margin:0;background:{H["page"]};-webkit-text-size-adjust:100%">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="sa-page" '
        f'style="background:{H["page"]}"><tr><td align="center" style="padding:22px 12px 40px">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" class="sa-card" '
        f'style="max-width:600px;width:100%;background:{H["card"]};border:1px solid {H["hair"]};'
        'border-radius:14px;overflow:hidden">'
        # header band
        f'<tr><td style="background:{H["accent_deep"]};padding:20px 26px">'
        f'<div style="font:600 11px {_FONT};letter-spacing:.16em;text-transform:uppercase;color:#c7f2ea">StockAgent · Personal research</div>'
        f'<div style="font:700 22px {_FONT};color:#ffffff;margin:4px 0 0;letter-spacing:-.01em">Morning Brief</div>'
        f'<div style="font:500 13px {_FONT};color:#a9e5db;margin:6px 0 0">{_esc(hdr)}</div></td></tr>'
        f'{body_rows}'
        # footer
        f'<tr><td class="sa-foot" style="background:{H["hair_soft"]};padding:20px 26px 24px">'
        f'<p class="sa-muted" style="margin:0 0 14px;font:400 12px/1.5 {_FONT};color:{H["muted"]}">'
        'Research tool — information only, <b>never personal advice</b>. '
        'Figures are model estimates from your paper portfolio and public sources.</p>'
        f'{button}'
        f'<p class="sa-muted" style="margin:16px 0 0;font:400 11px {_FONT};color:{H["muted"]};letter-spacing:.04em">StockAgent · morning brief</p>'
        '</td></tr>'
        '</table></td></tr></table></body></html>')
```

- [ ] **Step 5: Run to verify both tests pass**

Run: `python -m pytest tests/unit/test_delivery_brief.py -k render_brief_html -v`
Expected: PASS.

- [ ] **Step 6: Eyeball the real render** (manual sanity, no assertion): render the stored 2026-07-29 brief to a file and open it.

```bash
python -c "import json,core.delivery.brief as b; d=json.load(open('analysis_data/portfolio/primary/briefs/2026-07-29.json',encoding='utf-8')); open('scratch_brief.html','w',encoding='utf-8').write(b.render_brief_html(d)); print('wrote scratch_brief.html')"
```
Confirm it opens as a styled brief; then delete `scratch_brief.html` (do not commit it).

- [ ] **Step 7: Commit**

```bash
git add core/delivery/brief.py tests/unit/test_delivery_brief.py
git commit -m "feat(brief): render_brief_html — clean-fintech email-safe brief renderer"
```

---

## Task 5: `send_email` — multipart/alternative with optional HTML

**Files:**
- Modify: `core/delivery/channels.py` (`send_email`)
- Test: `tests/unit/test_delivery_channels.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `send_email(subject, body, attachments=None, html_body: str | None = None) -> bool`.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_delivery_channels.py`)

```python
def test_send_email_multipart_alternative_when_html(monkeypatch):
    import email as _email
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def sendmail(self, frm, to, msg): sent["msg"] = msg

    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(ch.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(ch.settings, "SMTP_USER", "u@example.com")
    monkeypatch.setattr(ch.settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "me@example.com")
    monkeypatch.setattr(ch.settings, "APP_PUBLIC_URL", "")
    monkeypatch.setattr(ch.smtplib, "SMTP", _FakeSMTP)

    assert send_email("Subj", "plain body", html_body="<b>hi</b>") is True
    parsed = _email.message_from_string(sent["msg"])
    assert parsed.get_content_type() == "multipart/alternative"
    kinds = [p.get_content_type() for p in parsed.walk()]
    assert "text/plain" in kinds and "text/html" in kinds
    # HTML must be the LAST part (preferred by clients).
    leaves = [p.get_content_type() for p in parsed.walk() if not p.is_multipart()]
    assert leaves[-1] == "text/html"


def test_send_email_html_none_is_single_part(monkeypatch):
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def sendmail(self, frm, to, msg): sent["msg"] = msg

    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(ch.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(ch.settings, "SMTP_USER", "")
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "me@example.com")
    monkeypatch.setattr(ch.settings, "APP_PUBLIC_URL", "")
    monkeypatch.setattr(ch.smtplib, "SMTP", _FakeSMTP)
    assert send_email("Subj", "plain body") is True
    assert "multipart" not in sent["msg"].lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/unit/test_delivery_channels.py -k "multipart_alternative or html_none" -v`
Expected: FAIL (`send_email` has no `html_body` kwarg / still single-part).

- [ ] **Step 3: Implement in `core/delivery/channels.py`.** Add `from email.mime.multipart import MIMEMultipart` is already imported. Change `send_email`:

```python
def send_email(subject: str, body: str, attachments: list[Path] | None = None,
               html_body: str | None = None) -> bool:
    """SMTP STARTTLS send to DELIVERY_EMAIL_TO. False when disabled/unconfigured
    or on any failure — never raises. `attachments` (AUD-088) attach file paths
    (send fails closed if any is unreadable). `html_body` (2026-07-30): when set,
    the message is multipart/alternative — plain `body` first, HTML last."""
    if not (settings.DELIVERY_EMAIL_ENABLED and settings.SMTP_HOST
            and settings.DELIVERY_EMAIL_TO):
        return False
    body = _with_app_link(body)
    try:
        alt: MIMEText | MIMEMultipart
        if html_body:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body, "plain", "utf-8"))
            alt.attach(MIMEText(html_body, "html", "utf-8"))   # last = preferred
        else:
            alt = MIMEText(body, "plain", "utf-8")
        if attachments:
            msg: MIMEText | MIMEMultipart = MIMEMultipart("mixed")
            msg.attach(alt)
            for path in attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(Path(path).read_bytes())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f'attachment; filename="{Path(path).name}"')
                msg.attach(part)
        else:
            msg = alt
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
```

- [ ] **Step 4: Run the full channels suite** (guard the attachment/plain regressions)

Run: `python -m pytest tests/unit/test_delivery_channels.py tests/unit/test_delivery_channels_attachments.py -v`
Expected: PASS (new html tests + existing attachment/plain/`_with_app_link` tests).

- [ ] **Step 5: Commit**

```bash
git add core/delivery/channels.py tests/unit/test_delivery_channels.py
git commit -m "feat(delivery): send_email multipart/alternative with optional html_body"
```

---

## Task 6: Wire HTML end-to-end — `deliver` + `run_morning_brief` + kill-switch

**Files:**
- Modify: `core/delivery/channels.py` (`deliver`)
- Modify: `core/delivery/brief.py` (`run_morning_brief`)
- Modify: `src/backend/shared/config/settings/base.py` (1 setting)
- Modify: `config.yaml` (1 key)
- Test: `tests/unit/test_delivery_channels.py`, `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Consumes: `render_brief_html` (Task 4), `send_email(..., html_body=)` (Task 5).
- Produces: `deliver(title, body, url="/", user_id=None, kind="alert", html_body: str | None = None) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_delivery_channels.py
def test_deliver_passes_html_to_email_not_push(monkeypatch):
    monkeypatch.setattr(ch.settings, "DELIVERY_ENABLED", True)
    seen = {}
    monkeypatch.setattr(ch, "send_push", lambda title, body, **k: seen.setdefault("push", (body, k)) or 0)
    monkeypatch.setattr(ch, "send_email", lambda title, body, html_body=None: seen.setdefault("email", (body, html_body)) or 1)
    # force inline path (Atlas off)
    import services.data.stores.atlas_store as a
    monkeypatch.setattr(a, "enabled", lambda: False)
    out = ch.deliver("t", "plain", html_body="<b>h</b>", kind="brief")
    assert out["email"] == 1
    assert seen["email"] == ("plain", "<b>h</b>")     # html reached email
    assert "html_body" not in seen["push"][1]         # push never got html
```

```python
# tests/unit/test_delivery_brief.py
def test_run_brief_renders_html_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "is_trading_day", lambda d: True)
    monkeypatch.setattr(br, "active_user_ids", lambda: ["u1"])
    monkeypatch.setattr(br.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(br.settings, "PREDICTION_DATA_DIR", str(tmp_path / "predictions"))
    monkeypatch.setattr(br.settings, "DISCOVERY_DATA_DIR", str(tmp_path / "discovery"))
    monkeypatch.setattr(br.settings, "DELIVERY_BRIEF_HTML_ENABLED", True)
    _mk_store(tmp_path)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: ("h", []))
    monkeypatch.setattr(br, "_overnight_items", lambda *a, **k: [])
    monkeypatch.setattr(br, "_earnings_soon", lambda *a, **k: [])
    monkeypatch.setattr(br, "_ipo_watch", lambda *a, **k: [])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])
    captured = {}
    monkeypatch.setattr(br, "deliver", lambda title, body, **k: captured.update(k) or {"delivered": True})
    br.run_morning_brief(on=date(2026, 7, 9))
    assert captured.get("html_body", "").lstrip().lower().startswith("<!doctype html>")

    captured.clear()
    monkeypatch.setattr(br.settings, "DELIVERY_BRIEF_HTML_ENABLED", False)
    br.run_morning_brief(on=date(2026, 7, 9))
    assert captured.get("html_body") is None            # kill-switch => text only
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/unit/test_delivery_channels.py::test_deliver_passes_html_to_email_not_push tests/unit/test_delivery_brief.py::test_run_brief_renders_html_when_enabled -v`
Expected: FAIL (`deliver` has no `html_body`; `run_morning_brief` passes none; setting missing).

- [ ] **Step 3: Add the setting** in `src/backend/shared/config/settings/base.py` after line 907:

```python
DELIVERY_BRIEF_HTML_ENABLED: bool = bool(cfg("delivery.brief_html_enabled", fallback=True))
```

- [ ] **Step 4: Add the config.yaml key** under the delivery block (after `brief_earnings_watch_maxlen`):

```yaml
  brief_html_enabled: true             # send the styled HTML email part (false => text-only email; one-line revert)
```

- [ ] **Step 5: Thread `html_body` through `deliver`** in `core/delivery/channels.py`:

```python
def deliver(
    title: str, body: str, url: str = "/", user_id: str | None = None,
    kind: str = "alert", html_body: str | None = None,
) -> dict:
```

Inside, pass `html_body` to the outbox and the inline email (leave push untouched):

```python
            queued = enqueue_message(uid, title, body, url=url, kind=kind, html_body=html_body)
```
```python
    try:
        emailed = int(send_email(title, body, html_body=html_body))
    except Exception as exc:
        logger.warning("[delivery] email channel failed (non-fatal): %s", exc)
```

- [ ] **Step 6: Wire `run_morning_brief`** in `core/delivery/brief.py`. Replace the `deliver(...)` call (~line 604):

```python
            text = render_brief_text(brief)
            html_body = None
            if settings.DELIVERY_BRIEF_HTML_ENABLED:
                try:
                    html_body = render_brief_html(brief)
                except Exception as exc:      # defence in depth (renderer already guards)
                    logger.warning("[brief] html render failed, sending text-only (non-fatal): %s", exc)
            deliver(f"Morning brief — {on}", text, url="/#/inbox/brief",
                    user_id=user_id, kind="brief", html_body=html_body)
```

- [ ] **Step 7: Run to verify they pass**

Run: `python -m pytest tests/unit/test_delivery_channels.py tests/unit/test_delivery_brief.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/delivery/channels.py core/delivery/brief.py src/backend/shared/config/settings/base.py config.yaml tests/unit/test_delivery_channels.py tests/unit/test_delivery_brief.py
git commit -m "feat(delivery): wire HTML brief through deliver/run_morning_brief with kill-switch"
```

---

## Task 7: Outbox carry-through — HTML survives the Atlas cutover

**Files:**
- Modify: `core/delivery/outbox.py` (`enqueue_message`, `_send_row`)
- Test: `tests/unit/test_delivery_outbox.py` (create if absent; else append)

**Interfaces:**
- Consumes: `send_email(..., html_body=)` (Task 5).
- Produces: `enqueue_message(user_id, title, body, *, url="/", kind="alert", html_body: str | None = None) -> int`.

- [ ] **Step 1: Write the failing test.** (If `tests/unit/test_delivery_outbox.py` doesn't exist, create it with this; else append.)

```python
import json
import core.delivery.outbox as ob


def test_enqueue_message_stores_full_body_and_html(monkeypatch):
    captured = {}

    def _fake_enqueue(user_id, channel, kind, payload_ref, dedupe_key):
        captured[channel] = payload_ref
        return 1

    monkeypatch.setattr(ob, "enqueue", _fake_enqueue)
    from core.config import settings as s
    monkeypatch.setattr(s, "DELIVERY_PUSH_ENABLED", True)
    monkeypatch.setattr(s, "DELIVERY_EMAIL_ENABLED", True)

    long_body = "x" * 4000
    n = ob.enqueue_message("u1", "Subj", long_body, kind="brief", html_body="<b>hi</b>")
    assert n == 2
    email_payload = json.loads(captured["email"])
    assert email_payload["html"] == "<b>hi</b>"
    assert len(email_payload["body"]) == 4000          # full body stored (no 1500 clip)


def test_send_row_caps_push_and_passes_html_to_email(monkeypatch):
    calls = {}
    monkeypatch.setattr("core.delivery.channels.send_push",
                        lambda title, body, url="/", user_id=None: calls.setdefault("push", body) or 1)
    monkeypatch.setattr("core.delivery.channels.send_email",
                        lambda title, body, html_body=None: calls.setdefault("email", (len(body), html_body)) or True)

    payload = json.dumps({"title": "t", "body": "y" * 4000, "url": "/", "html": "<i>h</i>"})
    assert ob._send_row({"id": 1, "user_id": "u1", "channel": "push", "payload_ref": payload}) is True
    assert len(calls["push"]) == 1500                   # push capped at send time
    assert ob._send_row({"id": 2, "user_id": "u1", "channel": "email", "payload_ref": payload}) is True
    assert calls["email"] == (4000, "<i>h</i>")         # email gets full body + html
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_outbox.py -v`
Expected: FAIL (`enqueue_message` has no `html_body`; body still clipped to 1500; `_send_row` doesn't pass html).

- [ ] **Step 3: Update `enqueue_message`** in `core/delivery/outbox.py` — add the kwarg, store full body + html, drop the enqueue-time cap:

```python
def enqueue_message(user_id: str, title: str, body: str, *, url: str = "/",
                    kind: str = "alert", html_body: str | None = None) -> int:
    """Fan one logical message into the outbox as per-channel rows, mirroring
    `deliver()`'s push+email fan-out for currently-enabled channels. The full
    payload is stored inline ({title, body, url, html}); the push length cap is
    applied at *send* time so the email row keeps the full text + HTML. The
    dedupe key carries a content hash so an identical brief dedupes."""
    from core.config import settings
    payload = {"title": title, "body": body, "url": url}
    if html_body:
        payload["html"] = html_body
    payload_ref = json.dumps(payload)
    digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]
    base = f"{user_id}|{kind}|{_now().date().isoformat()}|{digest}"
    n = 0
    for channel, enabled in (("push", getattr(settings, "DELIVERY_PUSH_ENABLED", False)),
                             ("email", getattr(settings, "DELIVERY_EMAIL_ENABLED", False))):
        if enabled and enqueue(user_id, channel, kind, payload_ref,
                               f"{base}|{channel}") is not None:
            n += 1
    return n
```

- [ ] **Step 4: Update `_send_row`** — cap push at send, pass html to email:

```python
def _send_row(row) -> bool:
    """Deliver one claimed row via its channel transport. True on delivery."""
    try:
        payload = json.loads(row["payload_ref"])
    except Exception:
        payload = {}
    title, body = payload.get("title", ""), payload.get("body", "")
    url, html_body = payload.get("url", "/"), payload.get("html")
    from core.delivery.channels import send_email, send_push
    try:
        if row["channel"] == "push":
            return send_push(title, body[:1500], url=url, user_id=row["user_id"]) > 0
        if row["channel"] == "email":
            return bool(send_email(title, body, html_body=html_body))
    except Exception as exc:
        logger.warning("[outbox] send failed for row %s (non-fatal): %s",
                       row["id"], exc)
    return False
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/unit/test_delivery_outbox.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/delivery/outbox.py tests/unit/test_delivery_outbox.py
git commit -m "feat(outbox): carry html + full body in payload; cap push at send time"
```

---

## Task 8: Full-suite regression gate

**Files:** none (verification only).

- [ ] **Step 1: Run the delivery suites + a broad sweep**

Run: `python -m pytest tests/unit/test_delivery_brief.py tests/unit/test_delivery_channels.py tests/unit/test_delivery_channels_attachments.py tests/unit/test_delivery_outbox.py tests/unit/test_delivery_api.py -v`
Expected: all PASS.

- [ ] **Step 2: Run the full unit suite** to confirm the GREEN baseline holds

Run: `python -m pytest tests/unit -q`
Expected: 0 failures / 0 errors (baseline 2292P/0F/0E + the net-new tests from this plan). Any failure is a real regression — fix before proceeding.

- [ ] **Step 3: Update the brief-redesign memory** (`memory/project_brief_redesign.md`) with a "Wave 3 — HTML email" note: shipped locally, pending push/deploy, kill-switch `brief_html_enabled`, first HTML brief = first 08:50 IST run after deploy. (Do not push during the 16:25–17:15 IST deploy-kill window on trading days.)

---

## Self-Review

**Spec coverage:**
- §3.1 render_brief_html → Task 4. ✓
- §3.2 send_email multipart + deliver threading → Tasks 5, 6. ✓
- §3.3 outbox carry-through (JSON payload, cap-at-send) → Task 7. ✓
- §3.4 unchanged text/schema → preserved (render_brief_text untouched; `html_body=None` byte-identical, tested Task 5). ✓
- §4 template tokens/structure → Task 4 (matches approved mockup). ✓
- §5.1 salient de-dup → Task 1. §5.2 portfolio → Task 2. §5.3 why-it-matters + §5.4 summary → Task 3. ✓
- §6 config keys (dedup_min_shared, stopwords, html_enabled) → Tasks 1, 6. ✓
- §7 testing → each task's tests + Task 8 gate. ✓
- §8 rollout (kill-switch, degrade-on-failure, Atlas, deploy window) → Tasks 4/6/7 + Task 8 memory note. ✓

**Placeholder scan:** No TBD/TODO; every code step has full content.

**Type consistency:** `_dedup_overnight(min_shared, stopwords)` used identically in Task 1 impl + `_overnight_items`. `send_email(..., html_body=)` defined Task 5, consumed Tasks 6/7. `deliver(..., html_body=)` defined Task 6, consumed by `run_morning_brief`. `enqueue_message(..., html_body=)` defined Task 7, consumed by `deliver` (Task 6 passes it) — Task 6 edits the `enqueue_message(...)` call to include `html_body=html_body`; that call site is updated in Task 6 Step 5 and the kwarg lands in Task 7. Ordering note: Task 6's `deliver` edit adds `html_body=html_body` to the `enqueue_message(...)` call, and Task 7 adds the matching kwarg — run Task 7 before enabling Atlas; unit tests for Task 6 stub `send_email`/`enqueue` so they pass regardless of order.
