# In-App Brief Rendering, Responsive Fixes & Settings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Inbox's ASCII text rendering with native components built from the structured brief JSON, add a real Settings screen, and fix the responsive breakages that make four screens unusable on a phone.

**Architecture:** The app is a **no-build prototype** — `.jsx` files are transpiled in the browser by Babel standalone and loaded as `<script type="text/babel">` tags from `index.html`. There is no bundler, no npm package, no import/export. Components communicate by assigning to `window.*` at the bottom of each file, and load order in `index.html` is the dependency graph. Every new file must be registered there. Phase 1 renders from the structured dict already returned by `GET /delivery/brief/latest`; the only backend change is response enrichment so plain-English verdict/regime strings stay server-side.

**Tech Stack:** React 18.3.1 (UMD, browser-global), Babel standalone 7.29, FastAPI + pytest on the backend, Playwright 1.62 as a **dev-only npm devDependency** for responsive verification (see Global Constraints).

**Spec:** `docs/superpowers/specs/2026-07-31-app-brief-render-responsive-settings-design.md`

## Global Constraints

- **No build step.** No `import`/`export` in any `.jsx`. Components attach to `window` at file end; consumers read the global. New files MUST be added to `index.html` **before** the file that consumes them.
- **No new *runtime* dependencies.** No new CDN `<script>` tags in `index.html`; the app ships exactly the globals it ships today. **Dev tooling is exempt** (ruling, 2026-08-01): Task 9 adds a root `package.json` with `playwright` as a `devDependency`, because `import { chromium } from 'playwright'` cannot resolve otherwise — verified `ERR_MODULE_NOT_FOUND`, and `npx --package=playwright node` does not fix ESM resolution. `node_modules/` must be gitignored.
- **Copy rule:** the app is a research tool. Never render text that reads as personal financial advice. The Brief footer string is exactly: `Research tool — information only, never advice.`
- **Plain-English strings come from the server.** Never hardcode a verdict or regime translation in JSX — `_VERDICT_PLAIN` / `_REGIME_PLAIN` (`core/delivery/brief.py:34-47`) are the single source of truth.
- **Every brief section auto-hides when empty**, matching `render_brief_text()`.
- **Prefs persist to `localStorage` only.** No new table, no new preferences endpoint (spec D6 — avoids colliding with the Atlas cutover Aug 1–2).
- **Never run the live pipeline for verification.** No `POST /delivery/run-brief`, no Serper call (spec D8).
- **Breakpoint is 767px/768px**, matching every existing rule in `styles.css`.
- **Python suite baseline in a CLEAN checkout is 2377 passed / 2 failed / 12 skipped** (measured on this worktree, 2026-08-01). Two tests are **KNOWN-RED and pre-existing** — both pass in isolation and at file level, and fail only in a full-suite run (deterministic cross-file pollution; no random-order plugin installed). They are unrelated to this plan:
  - `tests/unit/test_delivery_api.py::test_push_subscribe_caps_store_size`
  - `tests/unit/intelligence/rl/eval/test_harness.py::TestRealDataDiscovery::test_real_eval_discovers_maruti_data`

  **The gate is "no NEW failures beyond these two"** — not 0F. Do NOT attempt to fix them; they are out of scope and logged separately. (The repo's notes describe a green 2379P/0F/0E baseline; that holds only in the primary checkout, where local untracked state masks the pollution.)
- **Do not push to `main` between 16:25 and 17:15 IST on a trading day.**

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `tests/fixtures/ui_brief_fixture.json` | Brief covering every section + the §3.4 edge cases |
| `scripts/seed_fixture_ui.py` | Writes fixture brief/digest/weekly into a data dir for local UI work |
| `package.json` | Dev-only; `playwright` devDependency so the harness's ESM import resolves |
| `scripts/ui_responsive_audit.mjs` | Playwright: overflow assertion + screenshots, 10 screens × 4 widths |
| `src/frontend/prototypes/hooks.jsx` | `useIsMobile()` — the reactive width hook the codebase lacks |
| `src/frontend/prototypes/brief-view.jsx` | `BriefView` + `BVFold` + `BVAttentionRow` |
| `src/frontend/prototypes/digest-view.jsx` | `DigestView` |
| `src/frontend/prototypes/weekly-view.jsx` | `WeeklyView` |
| `src/frontend/prototypes/settings.jsx` | `SettingsPage` |

**Modify:**

| Path | Change |
|---|---|
| `core/delivery/brief.py` | add `enrich_brief_for_api()` |
| `services/api/routes/delivery_api.py:30-41` | call it |
| `tests/unit/test_delivery_api.py` | enrichment tests |
| `src/frontend/prototypes/inbox.jsx` | delegate to the view components |
| `src/frontend/prototypes/index.html` | script tags, settings route, drop theme/density from Tweaks |
| `src/frontend/prototypes/home.jsx` | Settings nav entry, mobile search/avatar |
| `src/frontend/prototypes/analytics.jsx`, `logs.jsx`, `prompt-lab.jsx` | render `TopNav` |
| `src/frontend/prototypes/rl-monitor.jsx` | weights grid + daily log mobile treatment |
| `src/frontend/prototypes/learn.jsx:235` | adopt `.drawer-panel` |
| `src/frontend/prototypes/styles.css` | new mobile rules |

---

# PHASE 1 — Native Inbox rendering

### Task 1: Server-side plain-English enrichment

The raw brief JSON carries `"EXIT"` and `"RISK_OFF"`. Only the text/HTML renderers translate them. The app must not keep its own copy of those maps.

**Files:**
- Modify: `core/delivery/brief.py` (add function after `render_brief_text`, ~line 700)
- Modify: `services/api/routes/delivery_api.py:30-41`
- Test: `tests/unit/test_delivery_api.py`

**Interfaces:**
- Produces: `enrich_brief_for_api(brief: dict) -> dict` — returns a **new** dict; never mutates its argument. Adds `verdict_plain: str` to each `advisor_flags` entry, and `label_plain: str` + `gloss: str` to `regime`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_delivery_api.py`:

```python
def test_brief_latest_enriches_verdict_and_regime(monkeypatch, tmp_path):
    """The app renders from raw JSON, so plain-English must ride the response."""
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    from core.portfolio.store import PortfolioStore
    PortfolioStore(base_dir=str(tmp_path)).save_brief({
        "date": "2026-07-31", "kind": "morning_brief", "headline": "h",
        "advisor_flags": [{"symbol": "OLDCO", "verdict": "TRIM", "reason": "r"}],
        "regime": {"label": "RISK_OFF"},
    })
    body = _client().get("/delivery/brief/latest").json()
    assert body["advisor_flags"][0]["verdict_plain"] == "Trim back"
    assert body["advisor_flags"][0]["verdict"] == "TRIM"      # raw preserved
    assert body["regime"]["label_plain"] == "Cautious"
    assert body["regime"]["gloss"].startswith("the system reads elevated risk")


def test_brief_enrichment_tolerates_unknown_and_missing(monkeypatch, tmp_path):
    """Unknown enums fall through to the raw string; absent keys stay absent."""
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    from core.portfolio.store import PortfolioStore
    PortfolioStore(base_dir=str(tmp_path)).save_brief({
        "date": "2026-07-31", "kind": "morning_brief",
        "advisor_flags": [{"symbol": "X", "verdict": "WAT"}],
        "regime": None,
    })
    body = _client().get("/delivery/brief/latest").json()
    assert body["advisor_flags"][0]["verdict_plain"] == "WAT"
    assert body["regime"] is None


def test_enrich_does_not_mutate_stored_brief():
    """Stored briefs feed RL grading and replay — they must stay byte-identical."""
    from core.delivery.brief import enrich_brief_for_api
    original = {"advisor_flags": [{"symbol": "A", "verdict": "EXIT"}],
                "regime": {"label": "RISK_ON"}}
    enrich_brief_for_api(original)
    assert "verdict_plain" not in original["advisor_flags"][0]
    assert "label_plain" not in original["regime"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_delivery_api.py -k "enrich" -v
```

Expected: FAIL — `ImportError: cannot import name 'enrich_brief_for_api'` and `KeyError: 'verdict_plain'`.

- [ ] **Step 3: Add the function**

In `core/delivery/brief.py`, immediately after `render_brief_text()` (before `render_brief_html`):

```python
def enrich_brief_for_api(brief: dict) -> dict:
    """Add plain-English strings for JSON clients (the in-app Inbox).

    The stored brief is the source of truth for RL grading and replay, so this
    returns a shallow copy with only the derived keys added — the argument is
    never mutated. Unknown enum values fall through to the raw string, matching
    render_brief_text(). Never raises.
    """
    out = dict(brief)
    flags = brief.get("advisor_flags") or []
    if flags:
        out["advisor_flags"] = [
            {**f, "verdict_plain": _VERDICT_PLAIN.get(f.get("verdict", ""),
                                                      f.get("verdict", ""))}
            for f in flags
        ]
    regime = brief.get("regime")
    if isinstance(regime, dict) and regime.get("label"):
        word, gloss = _REGIME_PLAIN.get(regime["label"],
                                        (str(regime["label"]).title(), ""))
        out["regime"] = {**regime, "label_plain": word, "gloss": gloss}
    return out
```

- [ ] **Step 4: Wire it into the route**

In `services/api/routes/delivery_api.py`, replace the body of `brief_latest` (lines 35-41) with:

```python
    brief = PortfolioStore(user_id=user["user_id"]).load_latest_brief()
    if brief is None:
        raise HTTPException(status_code=404, detail="No brief yet — run POST /delivery/run-brief.")
    if format == "text":
        from core.delivery.brief import render_brief_text
        return {"date": brief.get("date"), "text": render_brief_text(brief)}
    from core.delivery.brief import enrich_brief_for_api
    return enrich_brief_for_api(brief)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/unit/test_delivery_api.py tests/unit/test_delivery_brief.py -v
```

Expected: PASS, including the pre-existing tests.

- [ ] **Step 6: Commit**

```bash
git add core/delivery/brief.py services/api/routes/delivery_api.py tests/unit/test_delivery_api.py
git commit -m "feat(delivery): enrich brief API response with plain-English verdict/regime

The app renders from the structured dict, which carries raw enums. Keeping
_VERDICT_PLAIN/_REGIME_PLAIN server-side and shipping the translation on the
response avoids a JS copy that would drift. Stored briefs are untouched."
```

---

### Task 2: Fixture + local seed script

Local `data/` has no brief, so there is nothing to render against. Seeding a **saved** brief exercises the real server and real route with zero LLM or Serper calls.

**Files:**
- Create: `tests/fixtures/ui_brief_fixture.json`
- Create: `scripts/seed_fixture_ui.py`

**Interfaces:**
- Produces: `python scripts/seed_fixture_ui.py --data-dir <dir>` writes a brief, digest and weekly review readable by `PortfolioStore(base_dir=<dir>)`.

- [ ] **Step 1: Create the fixture**

`tests/fixtures/ui_brief_fixture.json` — deliberately includes the §3.4 edge cases: a 200-char headline, 8 overnight items, an idea with no `conviction`, an unknown verdict enum, and an empty `ipo_watch`.

```json
{
  "date": "2026-07-31",
  "user_id": "primary",
  "kind": "morning_brief",
  "generated_at": "2026-07-31T03:20:00+00:00",
  "headline": "Two holdings need a look after an overnight selloff across autos, and the scanner has surfaced one new idea worth watching; conditions stay defensive so position sizes are running smaller than usual today.",
  "portfolio": {
    "date": "2026-07-30",
    "portfolio_value": 482300.0,
    "total_pnl_pct": 6.4,
    "escalations": ["TATAMOTORS"],
    "holdings_count": 5,
    "best": {"symbol": "M&M", "pnl_pct": 21.3},
    "worst": {"symbol": "TATAMOTORS", "pnl_pct": -8.7},
    "all_below_cost": false,
    "last_exit": {"symbol": "HEROMOTOCO", "pnl_pct": 3.1}
  },
  "advisor_flags": [
    {"symbol": "MARUTI", "verdict": "TRIM", "reason": "Thesis weakened — margin guidance cut twice.", "notes": []},
    {"symbol": "TATAMOTORS", "verdict": "EXIT", "reason": "Stop breached on the JLR demand warning.", "notes": []},
    {"symbol": "BAJAJ-AUTO", "verdict": "WAT_UNKNOWN", "reason": "Unknown enum — must fall through to the raw string.", "notes": []}
  ],
  "regime": {"label": "RISK_OFF"},
  "overnight": [
    {"headline": "Maruti Q1 operating margin misses street estimates by 140bps", "note": "You hold this; margin is the core of the thesis."},
    {"headline": "Nifty Auto slips 2.1% on weak monthly volume prints", "note": "Sector-wide — affects 4 of your holdings."},
    {"headline": "JLR flags softening demand in China for the September quarter", "note": "Direct read-through to TATAMOTORS."},
    {"headline": "Rupee weakens past 88.4 against the dollar", "note": "Import-cost pressure for OEMs without local sourcing."},
    {"headline": "Two-wheeler retail registrations up 6% month-on-month", "note": "Mildly supportive for BAJAJ-AUTO."},
    {"headline": "Crude holds above $84 for a third session", "note": "Input-cost headwind across the sector."},
    {"headline": "GST council defers the rate review on hybrids", "note": "Removes a near-term catalyst for M&M."},
    {"headline": "FII flows negative for the fifth straight session", "note": "Consistent with the defensive regime reading."}
  ],
  "earnings_soon": [
    {"symbol": "M&M", "date": "2026-08-01", "watch": "tractor volume commentary and the FES margin trajectory"}
  ],
  "discovery_adds": [
    {"symbol": "BAJAJ-AUTO", "verdict": "BUY", "conviction": 0.72, "reason": "Export recovery plus a richer premium mix."},
    {"symbol": "TVSMOTOR", "verdict": "WATCH", "reason": "No conviction score yet — the chip must render without a percentage."}
  ],
  "ipo_watch": [],
  "lockin_flags": [
    {"symbol": "NEWCO", "kind": "anchor", "expiry": "2026-08-14"}
  ]
}
```

- [ ] **Step 2: Write the seed script**

`scripts/seed_fixture_ui.py`:

```python
"""Seed a data dir with fixture brief/digest/weekly for local UI work.

Writes SAVED artefacts only — nothing is rebuilt, so no LLM or Serper call is
made (spec 2026-07-31 D8; the Serper counter is under validation). Usage:

    python scripts/seed_fixture_ui.py --data-dir .uidev-data
    PORTFOLIO_DATA_DIR=.uidev-data python -m uvicorn services.api.server:app --port 8001
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _ROOT / "tests" / "fixtures" / "ui_brief_fixture.json"

_DIGEST = {
    "date": "2026-07-30", "user_id": "primary",
    "portfolio_value": 482300.0, "cost_basis": 453200.0, "total_pnl_pct": 6.4,
    "holdings": [
        {"symbol": "MARUTI", "verdict": "TRIM", "close": 12840.0, "pnl_pct": 4.2,
         "reason": "Thesis weakened — margin guidance cut twice.", "notes": []},
        {"symbol": "TATAMOTORS", "verdict": "EXIT", "close": 642.0, "pnl_pct": -8.7,
         "reason": "Stop breached on the JLR demand warning.", "notes": []},
        {"symbol": "M&M", "verdict": "HOLD", "close": 3120.0, "pnl_pct": 21.3,
         "reason": "Thesis intact.", "notes": []},
    ],
    "escalations": ["TATAMOTORS"],
}

_WEEKLY = {
    "date": "2026-07-27", "user_id": "primary",
    "headline": "Concentration crept up in autos; one laggard is close to a switch.",
    "allocation": [{"sector": "AUTOMOBILE", "weight_pct": 64.2},
                   {"sector": "BFSI", "weight_pct": 35.8}],
    "concentration_flags": ["AUTOMOBILE"],
    "laggards": [{"symbol": "TATAMOTORS", "pnl_pct": -8.7}],
    "switch_candidates": [{"sector": "AUTOMOBILE", "symbol": "BAJAJ-AUTO", "conviction": 0.72}],
    "switch_suggestions": [{"symbol": "TATAMOTORS", "switch_candidate": "BAJAJ-AUTO"}],
    "scoreboard": {"checked": 12, "correct": 8},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".uidev-data")
    args = ap.parse_args()

    from core.portfolio.store import PortfolioStore
    store = PortfolioStore(user_id="primary", base_dir=args.data_dir)
    store.save_brief(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    store.save_digest(_DIGEST)
    store.save_weekly(_WEEKLY)
    print(f"[seed] brief + digest + weekly written under {args.data_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it and verify the route serves the fixture**

```bash
python scripts/seed_fixture_ui.py --data-dir .uidev-data
```

Expected: `[seed] brief + digest + weekly written under .uidev-data`

Then, in a second shell:

```bash
PORTFOLIO_DATA_DIR=.uidev-data python -m uvicorn services.api.server:app --port 8001
curl -s localhost:8001/delivery/brief/latest | python -m json.tool | head -20
```

Expected: the fixture JSON, with `verdict_plain` present on each flag (proves Task 1 is live).

- [ ] **Step 4: Ignore the dev data dir**

Append to `.gitignore`:

```
.uidev-data/
```

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/ui_brief_fixture.json scripts/seed_fixture_ui.py .gitignore
git commit -m "test(ui): fixture brief/digest/weekly + local seed script

Seeds SAVED artefacts so the real server and route serve them — no rebuild,
so no LLM or Serper call. Fixture covers the edge cases the UI must survive:
200-char headline, 8 overnight items, missing conviction, unknown verdict."
```

---

### Task 3: `brief-view.jsx` — the priority-feed renderer

**Files:**
- Create: `src/frontend/prototypes/brief-view.jsx`
- Modify: `src/frontend/prototypes/index.html` (script tag)

**Interfaces:**
- Consumes: `window.Icon` (from `icons.jsx`); the enriched dict from Task 1.
- Produces: `window.BriefView` — `<BriefView data={brief} onNav={fn} />`. `onNav` receives `'portfolio'` when an attention row is tapped (spec D4).

- [ ] **Step 1: Create the component**

```jsx
/* brief-view.jsx — native Brief renderer (spec 2026-07-31 §3.3).
 *
 * Priority feed: hero + "Needs attention" open; every other section folded
 * behind a tap with a count in the header. Renders from the STRUCTURED dict
 * (GET /delivery/brief/latest), never from ?format=text — the ASCII bars and
 * bullets that used to leak into the UI were text-renderer artifacts.
 *
 * Plain-English verdict/regime strings arrive pre-translated from the server
 * (enrich_brief_for_api); never translate enums here.
 */
const { useState: useStateBV } = React;

function bvINR(v) {
  if (typeof v !== 'number' || !isFinite(v)) return '—';
  return '₹' + Math.round(v).toLocaleString('en-IN');
}

function bvLongDate(iso) {
  const d = new Date(String(iso) + 'T00:00:00');
  if (isNaN(d.getTime())) return String(iso || '');
  return d.toLocaleDateString('en-IN',
    { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' });
}

function bvShortDate(iso) {
  const d = new Date(String(iso) + 'T00:00:00');
  if (isNaN(d.getTime())) return String(iso || '');
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' });
}

const BV_CARD = {
  background: 'var(--bg-surface)', border: '1px solid var(--border)',
  borderRadius: 14, marginBottom: 10,
};
const BV_LABEL = {
  font: '700 10px Inter, sans-serif', letterSpacing: '.13em',
  textTransform: 'uppercase', color: 'var(--cyan)', padding: '13px 14px 0',
};
const BV_ROW = { padding: '9px 0', borderTop: '1px solid var(--border)' };
const BV_WHY = { color: 'var(--ink-3)', fontSize: 12, marginTop: 3, lineHeight: 1.45 };

/* Verdict → chip colour. Keyed on the RAW enum (stable); the label shown is
 * always verdict_plain from the server. */
const BV_CHIP = {
  EXIT:  { background: '#fee2e2', color: '#b91c1c' },
  TRIM:  { background: '#fef3c7', color: '#b45309' },
  SWITCH:{ background: '#fef3c7', color: '#b45309' },
  ADD:   { background: '#dcfce7', color: '#15803d' },
  BUY:   { background: '#dcfce7', color: '#15803d' },
  HOLD:  { background: '#f1f5f9', color: '#475569' },
};

function BVChip({ verdict, label }) {
  const s = BV_CHIP[verdict] || { background: 'var(--bg-tinted)', color: 'var(--ink-2)' };
  return <span style={{
    display: 'inline-block', font: '700 10px Inter, sans-serif', padding: '2px 7px',
    borderRadius: 999, marginLeft: 6, verticalAlign: 1, ...s,
  }}>{label || verdict}</span>;
}

/* Collapsible section. `summary` shows in the collapsed header (a count, or the
 * regime word) so the fold is informative before you open it. */
function BVFold({ title, summary, children }) {
  const [open, setOpen] = useStateBV(false);
  return (
    <div style={BV_CARD}>
      <button onClick={() => setOpen(o => !o)} aria-expanded={open} style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        width: '100%', padding: '13px 14px', border: 'none', background: 'transparent',
        cursor: 'pointer', textAlign: 'left',
      }}>
        <span style={{ font: '700 12.5px Inter, sans-serif', color: 'var(--ink-1)' }}>{title}</span>
        <span style={{ font: '600 11px Inter, sans-serif', color: 'var(--ink-3)' }}>
          {summary} {open ? '⌃' : '⌄'}
        </span>
      </button>
      {open && <div style={{ padding: '0 14px 13px', fontSize: 12.5, color: 'var(--ink-2)' }}>
        {children}
      </div>}
    </div>
  );
}

function BVAttentionRow({ flag, onNav }) {
  return (
    <div role="button" tabIndex={0}
      onClick={() => onNav && onNav('portfolio')}
      onKeyDown={e => { if (e.key === 'Enter' && onNav) onNav('portfolio'); }}
      style={{ ...BV_ROW, cursor: onNav ? 'pointer' : 'default' }}>
      <span style={{ fontWeight: 800, color: 'var(--ink-1)', fontSize: 13 }}>{flag.symbol}</span>
      <BVChip verdict={flag.verdict} label={flag.verdict_plain}/>
      {flag.reason ? <div style={BV_WHY}>{flag.reason}
        {onNav ? <span style={{ color: 'var(--cyan)', fontWeight: 700 }}> ›</span> : null}</div> : null}
    </div>
  );
}

function BriefView({ data, onNav }) {
  const d = data || {};
  const p = d.portfolio;
  const flags = d.advisor_flags || [];
  const overnight = d.overnight || [];
  const earnings = d.earnings_soon || [];
  const ideas = d.discovery_adds || [];
  const ipos = d.ipo_watch || [];
  const lockin = d.lockin_flags || [];
  const regime = d.regime;
  const pnl = (p && typeof p.total_pnl_pct === 'number') ? p.total_pnl_pct : null;

  return (
    <div>
      {/* ── Hero: date, headline, portfolio ── */}
      <div style={BV_CARD}>
        <div style={{ padding: '16px 14px' }}>
          <div style={{ font: '700 10px Inter, sans-serif', letterSpacing: '.1em',
            textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>
            {bvLongDate(d.date)}
          </div>
          {d.headline ? <div style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--ink-1)' }}>
            {d.headline}
          </div> : null}
          {p ? (
            <div style={{ display: 'flex', gap: 18, marginTop: 14, paddingTop: 12,
              borderTop: '1px solid var(--border)', flexWrap: 'wrap' }}>
              <div>
                <div style={{ font: '800 19px/1 Inter, sans-serif', color: 'var(--ink-1)' }}>
                  {bvINR(p.portfolio_value)}
                </div>
                <div style={BV_WHY}>portfolio</div>
              </div>
              {pnl !== null ? (
                <div>
                  <div style={{ font: '800 19px/1 Inter, sans-serif',
                    color: pnl >= 0 ? '#15803d' : '#b91c1c' }}>
                    {pnl >= 0 ? '▲' : '▼'} {Math.abs(pnl).toFixed(1)}%
                  </div>
                  <div style={BV_WHY}>since inception</div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {/* ── Needs attention — open, accented ── */}
      {flags.length > 0 && (
        <div style={{ ...BV_CARD, borderLeft: '3px solid #f59e0b' }}>
          <div style={{ ...BV_LABEL, color: '#b45309' }}>Needs attention · {flags.length}</div>
          <div style={{ padding: '8px 14px 13px' }}>
            {flags.map((f, i) => <BVAttentionRow key={i} flag={f} onNav={onNav}/>)}
          </div>
        </div>
      )}

      {/* ── Folded sections — each hidden entirely when empty ── */}
      {overnight.length > 0 && (
        <BVFold title="Overnight news" summary={overnight.length}>
          {overnight.map((o, i) => (
            <div key={i} style={BV_ROW}>
              {o.headline}
              {o.note ? <div style={BV_WHY}><b>Why it matters:</b> {o.note}</div> : null}
            </div>
          ))}
        </BVFold>
      )}

      {earnings.length > 0 && (
        <BVFold title="Earnings this week" summary={earnings.length}>
          {earnings.map((e, i) => (
            <div key={i} style={BV_ROW}>
              <b style={{ color: 'var(--ink-1)' }}>{e.symbol}</b> — {bvShortDate(e.date)}
              <div style={BV_WHY}>You hold this — {e.watch
                ? 'watch: ' + e.watch
                : 'results & guidance are the next catalyst.'}</div>
            </div>
          ))}
        </BVFold>
      )}

      {ideas.length > 0 && (
        <BVFold title="Ideas being researched" summary={ideas.length}>
          <div style={{ ...BV_WHY, marginBottom: 4 }}>
            The scanner flagged these; the tool rated each and is paper-testing the thesis.
            Its own view — not personal advice.
          </div>
          {ideas.map((a, i) => (
            <div key={i} style={BV_ROW}>
              <b style={{ color: 'var(--ink-1)' }}>{a.symbol}</b>
              {a.verdict ? <BVChip verdict={a.verdict} label={
                typeof a.conviction === 'number'
                  ? a.verdict + ' · ' + Math.round(a.conviction * 100) + '%'
                  : a.verdict
              }/> : null}
              {a.reason ? <div style={BV_WHY}>{a.reason}</div> : null}
            </div>
          ))}
        </BVFold>
      )}

      {regime && regime.label && (
        <BVFold title="Market conditions" summary={regime.label_plain || regime.label}>
          <div style={BV_ROW}>
            {regime.label_plain || regime.label}
            <span style={{ color: 'var(--ink-3)', fontSize: 11 }}> ({regime.label})</span>
            {regime.gloss ? <div style={BV_WHY}>{regime.gloss}</div> : null}
          </div>
        </BVFold>
      )}

      {ipos.length > 0 && (
        <BVFold title="IPOs open now" summary={ipos.length}>
          <div style={{ ...BV_WHY, marginBottom: 4 }}>The tool's research view — not advice.</div>
          {ipos.map((w, i) => (
            <div key={i} style={BV_ROW}>
              <b style={{ color: 'var(--ink-1)' }}>{w.symbol}</b>
              {w.company ? <span style={{ color: 'var(--ink-3)' }}> · {w.company}</span> : null}
            </div>
          ))}
        </BVFold>
      )}

      {lockin.length > 0 && (
        <BVFold title="Lock-in expiries" summary={lockin.length}>
          {lockin.map((lf, i) => (
            <div key={i} style={BV_ROW}>
              <b style={{ color: 'var(--ink-1)' }}>{lf.symbol}</b> {lf.kind} on {lf.expiry}
              <div style={BV_WHY}>Supply risk, not a signal.</div>
            </div>
          ))}
        </BVFold>
      )}

      <div style={{ textAlign: 'center', fontSize: 10.5, color: 'var(--ink-3)', padding: '10px 0 4px' }}>
        Research tool — information only, never advice.
      </div>
    </div>
  );
}

/* Export every helper Task 5 reuses. The codebase's convention is explicit
 * window assignment (icons.jsx, home.jsx) — do NOT rely on top-level const/
 * function declarations leaking across <script type="text/babel"> boundaries. */
window.BriefView = BriefView;
window.BVFold = BVFold;
window.BVChip = BVChip;
window.bvINR = bvINR;
window.bvLongDate = bvLongDate;
window.bvShortDate = bvShortDate;
```

- [ ] **Step 2: Register it in `index.html`**

In `src/frontend/prototypes/index.html`, add **before** the `inbox.jsx` tag (line 187):

```html
<script type="text/babel" src="brief-view.jsx"></script>
```

- [ ] **Step 3: Verify it renders**

The Inbox still uses the old renderer at this point — verify the component in isolation from the browser console with the fixture server running (Task 2 Step 3):

```js
fetch('/delivery/brief/latest').then(r => r.json()).then(d => {
  const el = document.createElement('div');
  document.body.appendChild(el);
  ReactDOM.createRoot(el).render(React.createElement(window.BriefView, { data: d }));
});
```

Expected: hero with `₹4,82,300` and `▲ 6.4%`, "Needs attention · 3" open with MARUTI showing **Trim back** and BAJAJ-AUTO showing the raw `WAT_UNKNOWN`, six collapsed folds, no `═` characters anywhere.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/prototypes/brief-view.jsx src/frontend/prototypes/index.html
git commit -m "feat(inbox): BriefView — native priority-feed brief renderer

Renders from the structured dict instead of line-splitting ?format=text.
Summary + needs-attention open; the rest folded with counts. Sections
auto-hide when empty, matching render_brief_text."
```

---

### Task 4: Wire `BriefView` into the Inbox

**Files:**
- Modify: `src/frontend/prototypes/inbox.jsx:1-61,117`

**Interfaces:**
- Consumes: `window.BriefView` (Task 3).
- Produces: the Brief tab fetches `/delivery/brief/latest` (**no** `?format=text`).

- [ ] **Step 1: Change the Brief tab's URL and render mode**

In `inbox.jsx`, replace the `INBOX_TABS` constant (lines 6-11):

```jsx
/* `render` picks the view component; 'text' is the legacy ASCII path still used
 * by tabs not yet migrated. */
const INBOX_TABS = [
  { key: 'brief',  label: 'Brief',  url: '/delivery/brief/latest',           render: 'brief'  },
  { key: 'digest', label: 'Digest', url: '/portfolio/digest/latest?format=text', render: 'text' },
  { key: 'weekly', label: 'Weekly', url: '/delivery/weekly/latest?format=text', render: 'text' },
  { key: 'alerts', label: 'Alerts', url: '/delivery/alerts?limit=20',        render: 'alerts' },
];
```

- [ ] **Step 2: Add `onNav` passthrough and dispatch on `render`**

Replace line 117 (the render dispatch) with:

```jsx
        {state.status === 'ok' && (
          active === 'alerts' ? renderAlerts(state.data)
          : active === 'brief' ? <BriefView data={state.data} onNav={onNav}/>
          : renderText(state.data)
        )}
```

- [ ] **Step 3: Verify in the browser**

With the fixture server running, open `http://localhost:8001/` → Inbox → Brief.

Expected: the priority feed. Confirm specifically —
- no `═══` bar, no `•` bullets, no indented `Why it matters:` text lines
- tapping "Overnight news" expands 8 items
- tapping a MARUTI row navigates to Portfolio
- the Digest and Weekly tabs still render the old ASCII (not yet migrated — Task 5)

- [ ] **Step 4: Commit**

```bash
git add src/frontend/prototypes/inbox.jsx
git commit -m "feat(inbox): Brief tab renders BriefView from structured JSON

Drops ?format=text for the brief. Digest and Weekly still use the legacy
text path until the next task."
```

---

### Task 5: `digest-view.jsx` + `weekly-view.jsx`

These have no redesigned email counterpart — this is their first real design. Reuse the Brief's card/fold vocabulary (spec D5).

**Files:**
- Create: `src/frontend/prototypes/digest-view.jsx`
- Create: `src/frontend/prototypes/weekly-view.jsx`
- Modify: `src/frontend/prototypes/inbox.jsx`, `src/frontend/prototypes/index.html`

**Interfaces:**
- Consumes: `window.BVFold`, `bvINR` (globals from Task 3).
- Produces: `window.DigestView`, `window.WeeklyView` — both `<X data={dict}/>`.

Digest dict (`core/portfolio/digest_text.py:6-23`): `date`, `portfolio_value`, `total_pnl_pct`, `holdings[{symbol, verdict, reason, pnl_pct, close}]`, `escalations[str]`.
Weekly dict (`core/delivery/weekly.py:219-234`): `date`, `headline`, `allocation[{sector, weight_pct}]`, `concentration_flags[str]`, `laggards[{symbol, pnl_pct}]`, `switch_candidates[{sector, symbol, conviction}]`, `switch_suggestions[{symbol, switch_candidate}]`, `scoreboard{checked, correct}`.

- [ ] **Step 1: Create `digest-view.jsx`**

```jsx
/* digest-view.jsx — EOD digest, native (spec 2026-07-31 §3.3 / D5).
 * Reuses BriefView's card + fold vocabulary. Holdings are grouped so the ones
 * carrying a non-HOLD verdict lead. */
function DigestView({ data }) {
  const d = data || {};
  const holdings = d.holdings || [];
  const esc = d.escalations || [];
  const flagged = holdings.filter(h => h.verdict && h.verdict !== 'HOLD' && h.verdict !== 'NO_DATA');
  const steady = holdings.filter(h => !flagged.includes(h));
  const pnl = typeof d.total_pnl_pct === 'number' ? d.total_pnl_pct : null;

  const row = (h, i) => (
    <div key={i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
      <span style={{ fontWeight: 800, color: 'var(--ink-1)', fontSize: 13 }}>{h.symbol}</span>
      {h.verdict ? <BVChip verdict={h.verdict} label={h.verdict}/> : null}
      {typeof h.pnl_pct === 'number' ? (
        <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
          color: h.pnl_pct >= 0 ? '#15803d' : '#b91c1c' }}>
          {h.pnl_pct >= 0 ? '+' : ''}{h.pnl_pct.toFixed(1)}%
        </span>
      ) : null}
      {h.reason ? <div style={{ color: 'var(--ink-3)', fontSize: 12, marginTop: 3 }}>{h.reason}</div> : null}
    </div>
  );

  return (
    <div>
      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 14, marginBottom: 10, padding: '16px 14px' }}>
        <div style={{ font: '700 10px Inter, sans-serif', letterSpacing: '.1em',
          textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>
          EOD digest · {bvLongDate(d.date)}
        </div>
        <div style={{ font: '800 22px/1 Inter, sans-serif', color: 'var(--ink-1)' }}>
          {bvINR(d.portfolio_value)}
          {pnl !== null ? (
            <span style={{ fontSize: 15, marginLeft: 10, color: pnl >= 0 ? '#15803d' : '#b91c1c' }}>
              {pnl >= 0 ? '▲' : '▼'} {Math.abs(pnl).toFixed(1)}%
            </span>
          ) : null}
        </div>
        <div style={{ color: 'var(--ink-3)', fontSize: 12, marginTop: 4 }}>
          {holdings.length} holding{holdings.length === 1 ? '' : 's'} · total P&amp;L
        </div>
      </div>

      {flagged.length > 0 && (
        <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)',
          borderLeft: '3px solid #f59e0b', borderRadius: 14, marginBottom: 10 }}>
          <div style={{ font: '700 10px Inter, sans-serif', letterSpacing: '.13em',
            textTransform: 'uppercase', color: '#b45309', padding: '13px 14px 0' }}>
            Flagged · {flagged.length}
          </div>
          <div style={{ padding: '8px 14px 13px' }}>{flagged.map(row)}</div>
        </div>
      )}

      {steady.length > 0 && (
        <BVFold title="Holding steady" summary={steady.length}>{steady.map(row)}</BVFold>
      )}

      {esc.length > 0 && (
        <BVFold title="Escalations" summary={esc.length}>
          {esc.map((s, i) => (
            <div key={i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)',
              fontWeight: 700, color: 'var(--ink-1)' }}>{s}</div>
          ))}
        </BVFold>
      )}

      <div style={{ textAlign: 'center', fontSize: 10.5, color: 'var(--ink-3)', padding: '10px 0 4px' }}>
        Research tool — information only, never advice.
      </div>
    </div>
  );
}

window.DigestView = DigestView;
```

- [ ] **Step 2: Create `weekly-view.jsx`**

```jsx
/* weekly-view.jsx — weekly review, native (spec 2026-07-31 §3.3 / D5).
 * The old text renderer emitted flat "Laggard: X +1.2%" lines; this groups them. */
function WeeklyView({ data }) {
  const d = data || {};
  const alloc = d.allocation || [];
  const conc = d.concentration_flags || [];
  const laggards = d.laggards || [];
  const cands = d.switch_candidates || [];
  const sugg = d.switch_suggestions || [];
  const sb = d.scoreboard || {};

  return (
    <div>
      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 14, marginBottom: 10, padding: '16px 14px' }}>
        <div style={{ font: '700 10px Inter, sans-serif', letterSpacing: '.1em',
          textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>
          Weekly review · {bvLongDate(d.date)}
        </div>
        {d.headline ? <div style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--ink-1)' }}>
          {d.headline}</div> : null}
        {typeof sb.checked === 'number' && sb.checked > 0 ? (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
            <span style={{ font: '800 19px/1 Inter, sans-serif', color: 'var(--ink-1)' }}>
              {sb.correct}/{sb.checked}
            </span>
            <span style={{ color: 'var(--ink-3)', fontSize: 12, marginLeft: 8 }}>
              judged calls right
            </span>
          </div>
        ) : null}
      </div>

      {alloc.length > 0 && (
        <BVFold title="Sector allocation" summary={alloc.length}>
          {alloc.map((a, i) => {
            const over = conc.indexOf(a.sector) !== -1;
            return (
              <div key={i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
                <span style={{ color: 'var(--ink-1)', fontWeight: 600 }}>{a.sector}</span>
                <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
                  color: over ? '#b45309' : 'var(--ink-2)' }}>
                  {Number(a.weight_pct).toFixed(1)}%
                </span>
                {over ? <div style={{ color: '#b45309', fontSize: 11.5, marginTop: 3 }}>
                  ⚠ over-concentrated</div> : null}
              </div>
            );
          })}
        </BVFold>
      )}

      {laggards.length > 0 && (
        <BVFold title="Laggards" summary={laggards.length}>
          {laggards.map((l, i) => (
            <div key={i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
              <span style={{ fontWeight: 800, color: 'var(--ink-1)' }}>{l.symbol}</span>
              <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
                color: l.pnl_pct >= 0 ? '#15803d' : '#b91c1c' }}>
                {l.pnl_pct >= 0 ? '+' : ''}{Number(l.pnl_pct).toFixed(1)}%
              </span>
            </div>
          ))}
        </BVFold>
      )}

      {(cands.length > 0 || sugg.length > 0) && (
        <BVFold title="Switch ideas" summary={sugg.length || cands.length}>
          <div style={{ color: 'var(--ink-3)', fontSize: 12, marginBottom: 4 }}>
            The tool's own view — not personal advice.
          </div>
          {sugg.map((s, i) => (
            <div key={'s' + i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
              <b style={{ color: 'var(--ink-1)' }}>{s.symbol}</b>
              <span style={{ color: 'var(--cyan)' }}> → </span>
              <b style={{ color: 'var(--ink-1)' }}>{s.switch_candidate}</b>
            </div>
          ))}
          {cands.map((c, i) => (
            <div key={'c' + i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
              <b style={{ color: 'var(--ink-1)' }}>{c.symbol}</b>
              <span style={{ color: 'var(--ink-3)', fontSize: 11.5 }}> · {c.sector}</span>
              {typeof c.conviction === 'number' ? (
                <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
                  color: 'var(--ink-2)' }}>{Math.round(c.conviction * 100)}%</span>
              ) : null}
            </div>
          ))}
        </BVFold>
      )}

      <div style={{ textAlign: 'center', fontSize: 10.5, color: 'var(--ink-3)', padding: '10px 0 4px' }}>
        Research tool — information only, never advice.
      </div>
    </div>
  );
}

window.WeeklyView = WeeklyView;
```

- [ ] **Step 3: Register both in `index.html`**

Add after the `brief-view.jsx` tag, still before `inbox.jsx`:

```html
<script type="text/babel" src="digest-view.jsx"></script>
<script type="text/babel" src="weekly-view.jsx"></script>
```

- [ ] **Step 4: Point the tabs at the structured endpoints**

In `inbox.jsx`, update `INBOX_TABS` — drop `?format=text` from digest and weekly:

```jsx
const INBOX_TABS = [
  { key: 'brief',  label: 'Brief',  url: '/delivery/brief/latest',    render: 'brief'  },
  { key: 'digest', label: 'Digest', url: '/portfolio/digest/latest',  render: 'digest' },
  { key: 'weekly', label: 'Weekly', url: '/delivery/weekly/latest',   render: 'weekly' },
  { key: 'alerts', label: 'Alerts', url: '/delivery/alerts?limit=20', render: 'alerts' },
];
```

And extend the dispatch:

```jsx
        {state.status === 'ok' && (
          active === 'alerts' ? renderAlerts(state.data)
          : active === 'brief'  ? <BriefView  data={state.data} onNav={onNav}/>
          : active === 'digest' ? <DigestView data={state.data}/>
          : active === 'weekly' ? <WeeklyView data={state.data}/>
          : renderText(state.data)
        )}
```

- [ ] **Step 5: Delete the now-dead `renderText`**

`renderText` (lines 47-61) has no remaining caller. Delete it and the now-unused `INBOX_EMPTY` entries stay — they're still used by the empty state.

- [ ] **Step 6: Verify all four tabs**

Reload the fixture app → Inbox. Expected: Brief, Digest and Weekly all render as cards; Alerts unchanged; no ASCII anywhere. Switch tabs repeatedly — no stale content between tabs.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/prototypes/digest-view.jsx src/frontend/prototypes/weekly-view.jsx \
        src/frontend/prototypes/inbox.jsx src/frontend/prototypes/index.html
git commit -m "feat(inbox): native Digest and Weekly views; retire the ASCII path

Digest groups flagged holdings ahead of steady ones; Weekly groups the flat
'Laggard: X' lines into sections. renderText deleted — no callers left."
```

---

# PHASE 3 — Settings

### Task 6: `settings.jsx` — screen shell, appearance, notifications

**Files:**
- Create: `src/frontend/prototypes/settings.jsx`
- Modify: `src/frontend/prototypes/index.html`

**Interfaces:**
- Consumes: `window.Icon`, `window.saPush`, `window.saGetToken`.
- Produces: `window.SettingsPage` — `<SettingsPage onNav={fn} theme={str} setTheme={fn}/>`.

- [ ] **Step 1: Create the component**

```jsx
/* settings.jsx — the real Settings screen (spec 2026-07-31 §5).
 *
 * Theme moves here out of TweaksPanel, which is prototyping scaffolding
 * (__activate_edit_mode host protocol) and unreachable for a real user.
 * Preferences persist to localStorage only — no schema change (spec D6).
 */
const { useState: useStateSet, useEffect: useEffectSet } = React;

const SET_CARD = {
  background: 'var(--bg-surface)', border: '1px solid var(--border)',
  borderRadius: 13, overflow: 'hidden', marginBottom: 4,
};
const SET_GROUP = {
  font: '700 10px Inter, sans-serif', letterSpacing: '.13em', textTransform: 'uppercase',
  color: 'var(--cyan)', margin: '18px 4px 7px',
};
const SET_ROW = {
  display: 'flex', alignItems: 'center', gap: 11, padding: '13px 14px',
  borderTop: '1px solid var(--border)',
};

function SetRow({ name, desc, children, danger, onClick, first }) {
  return (
    <div onClick={onClick}
      style={{ ...SET_ROW, borderTop: first ? 'none' : SET_ROW.borderTop,
        cursor: onClick ? 'pointer' : 'default' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13,
          color: danger ? '#b91c1c' : 'var(--ink-1)' }}>{name}</div>
        {desc ? <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>{desc}</div> : null}
      </div>
      {children}
    </div>
  );
}

function SetSegment({ value, options, onChange }) {
  return (
    <div style={{ display: 'flex', background: 'var(--bg-tinted)', borderRadius: 8,
      padding: 2, flexShrink: 0 }}>
      {options.map(o => (
        <button key={o.value} onClick={() => onChange(o.value)} style={{
          font: '700 11px Inter, sans-serif', padding: '5px 11px', borderRadius: 6,
          border: 'none', cursor: 'pointer',
          background: value === o.value ? 'var(--bg-surface)' : 'transparent',
          color: value === o.value ? 'var(--ink-1)' : 'var(--ink-3)',
        }}>{o.label}</button>
      ))}
    </div>
  );
}

/* Push toggle — same state machine as the old NotifRow in home.jsx. */
function SetPushToggle() {
  const [state, setState] = useStateSet('loading');
  useEffectSet(() => {
    let alive = true;
    if (window.saPush) window.saPush.status().then(s => { if (alive) setState(s); });
    else setState('unsupported');
    return () => { alive = false; };
  }, []);
  const LABEL = { on: 'On', off: 'Off', pending: '…', loading: '…',
                  denied: 'Blocked', unsupported: 'N/A', unconfigured: 'Off' };
  const locked = ['unsupported', 'denied', 'loading', 'pending'].indexOf(state) !== -1;
  const on = state === 'on';
  const toggle = async () => {
    if (!window.saPush || locked) return;
    setState('pending');
    setState(on ? await window.saPush.disable() : await window.saPush.enable());
  };
  return (
    <button onClick={toggle} disabled={locked} style={{
      font: '700 11px Inter, sans-serif', padding: '6px 13px', borderRadius: 999,
      border: '1px solid var(--border)', cursor: locked ? 'default' : 'pointer',
      background: on ? 'var(--bg-tinted)' : 'transparent',
      color: on ? 'var(--cyan)' : 'var(--ink-3)', flexShrink: 0,
    }}>{LABEL[state] || state}</button>
  );
}

function SettingsPage({ onNav, theme, setTheme }) {
  const [user, setUser] = useStateSet(null);
  useEffectSet(() => {
    let alive = true;
    fetch('/auth/me').then(r => r.ok ? r.json() : null)
      .then(d => { if (alive && d) setUser(d.user); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', padding: '18px 16px 90px' }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <button onClick={() => onNav && onNav('home')} style={{ width: 36, height: 36,
            borderRadius: 10, border: '1px solid var(--border)', background: 'var(--bg-surface)',
            display: 'grid', placeItems: 'center', cursor: 'pointer' }}>
            <Icon.ChevronL size={16}/>
          </button>
          <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--ink-1)' }}>Settings</div>
        </div>

        <div style={SET_GROUP}>Account</div>
        <div style={SET_CARD}>
          <SetRow first name={(user && user.display_name) || 'Signed in'}
            desc={user ? user.email + ' · ' + user.role : 'loading…'}/>
          {user && user.role === 'owner' ? (
            <SetRow name="Invite a friend" desc="Create a code someone can sign up with"
              onClick={() => onNav && onNav('settings-invites')}>
              <span style={{ color: 'var(--ink-3)' }}>›</span>
            </SetRow>
          ) : null}
        </div>

        <div style={SET_GROUP}>Notifications</div>
        <div style={SET_CARD}>
          <SetRow first name="Push on this device"
            desc="Morning brief, EOD digest, weekly review and alerts">
            <SetPushToggle/>
          </SetRow>
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-3)', margin: '7px 4px 0' }}>
          Push is all-or-nothing today. Per-kind control needs a server-side preference —
          it's on the backlog.
        </div>

        <div style={SET_GROUP}>Appearance</div>
        <div style={SET_CARD}>
          <SetRow first name="Theme" desc="Applies across the app">
            <SetSegment value={theme} onChange={setTheme} options={[
              { value: 'light', label: 'Light' },
              { value: 'dark', label: 'Dark' },
            ]}/>
          </SetRow>
        </div>

        <div style={SET_GROUP}>Data &amp; privacy</div>
        <div style={SET_CARD}>
          <SetRow first danger name="Delete my account"
            desc="Erases your portfolio, chats and personal data. Cannot be undone."
            onClick={() => onNav && onNav('settings-delete')}>
            <span style={{ color: 'var(--ink-3)' }}>›</span>
          </SetRow>
        </div>

        <div style={SET_GROUP}>About</div>
        <div style={SET_CARD}>
          <SetRow first name="Version" ><span style={{ fontSize: 12,
            color: 'var(--ink-3)' }}>2.0.0</span></SetRow>
          <SetRow name="Research tool — never advice"
            desc="Information only. Not a SEBI-registered adviser."/>
        </div>
      </div>
    </div>
  );
}

window.SettingsPage = SettingsPage;
```

- [ ] **Step 2: Register in `index.html`**

Add after the `inbox.jsx` tag:

```html
<script type="text/babel" src="settings.jsx"></script>
```

- [ ] **Step 3: Route it in `App()`**

In `index.html`, add to the screen list (after the `inbox` line, ~line 297):

```jsx
    {screen === 'settings' && <SettingsPage onNav={nav} theme={tweaks.theme}
      setTheme={v => setTweak('theme', v)}/>}
```

- [ ] **Step 4: Remove theme and density from the Tweaks panel**

In `index.html`, delete the `Theme` and `Density` `<TweakSection>` blocks (lines 320-325 and 332-338). Theme now lives in Settings; density is deleted outright — it has zero references outside `tweaks-panel.jsx` (verified: `grep -rn "density" *.jsx styles.css` returns only the tweak plumbing).

Also remove `"density"` from `TWEAK_DEFAULTS` (line 195), leaving:

```jsx
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "light",
  "sphereMode": "wireframe"
}/*EDITMODE-END*/;
```

- [ ] **Step 5: Verify**

Reload the fixture app. Navigate to Settings via the Tweaks "Quick jump" temporarily (`nav('settings')` from the console: `document.querySelector('#root')` is React-managed, so use the Tweaks panel button added in Task 8 — for now verify by temporarily setting the initial screen). Expected: all five groups render; the theme segment flips the app between light and dark; the push toggle reads your real permission state.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/prototypes/settings.jsx src/frontend/prototypes/index.html
git commit -m "feat(settings): real Settings screen; theme moves out of the dev panel

TweaksPanel is prototyping scaffolding, so theme was unreachable for real
users. Density is deleted rather than migrated — zero references anywhere.
Prefs stay in localStorage; no schema change during the Atlas cutover."
```

---

### Task 7: Invites and account deletion

Both endpoints are built and have no UI: `POST/GET /auth/invites` (`auth_api.py:93,100`, owner-only) and `DELETE /auth/account` (`auth_api.py:107`).

**Files:**
- Modify: `src/frontend/prototypes/settings.jsx`

**Interfaces:**
- Produces: `SettingsPage` handles `sub` state internally — `onNav('settings-invites')` and `onNav('settings-delete')` from Task 6 become internal panel switches, not app screens.

- [ ] **Step 1: Replace the two `onNav` sub-routes with internal panels**

In `settings.jsx`, add a `sub` state at the top of `SettingsPage`:

```jsx
  const [sub, setSub] = useStateSet(null);        // null | 'invites' | 'delete'
```

Change the two rows' handlers from `onNav(...)` to `setSub('invites')` / `setSub('delete')`, and render the panel above the groups when `sub` is set:

```jsx
  if (sub === 'invites') return <SetInvites onBack={() => setSub(null)}/>;
  if (sub === 'delete')  return <SetDelete onBack={() => setSub(null)} onNav={onNav}/>;
```

Place these two lines immediately after the `useEffectSet` that loads the user.

- [ ] **Step 2: Add the invites panel**

Append to `settings.jsx`, before `window.SettingsPage = SettingsPage;`:

```jsx
function SetInvites({ onBack }) {
  const [invites, setInvites] = useStateSet(null);
  const [busy, setBusy] = useStateSet(false);
  const [err, setErr] = useStateSet('');

  const load = () => {
    fetch('/auth/invites').then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(d => setInvites(d.invites || []))
      .catch(e => setErr(String(e.message || e)));
  };
  useEffectSet(load, []);

  const create = async () => {
    setBusy(true); setErr('');
    try {
      const r = await fetch('/auth/invites', { method: 'POST' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      load();
    } catch (e) { setErr(String(e.message || e)); }
    setBusy(false);
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', padding: '18px 16px 90px' }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button onClick={onBack} style={{ width: 36, height: 36, borderRadius: 10,
            border: '1px solid var(--border)', background: 'var(--bg-surface)',
            display: 'grid', placeItems: 'center', cursor: 'pointer' }}>
            <Icon.ChevronL size={16}/>
          </button>
          <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--ink-1)' }}>Invite a friend</div>
        </div>

        <div style={{ fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 14, lineHeight: 1.5 }}>
          Signup needs an invite code. Create one and send it over — they enter it on the
          signup screen.
        </div>

        <button onClick={create} disabled={busy} style={{
          padding: '11px 18px', borderRadius: 999, border: 'none', cursor: 'pointer',
          background: 'var(--cyan)', color: '#fff', font: '700 13px Inter, sans-serif',
          opacity: busy ? .6 : 1, marginBottom: 16,
        }}>{busy ? 'Creating…' : 'Create invite code'}</button>

        {err ? <div style={{ color: '#b91c1c', fontSize: 12.5, marginBottom: 12 }}>{err}</div> : null}

        {invites === null ? <div style={{ color: 'var(--ink-3)' }}>Loading…</div>
         : invites.length === 0 ? <div style={{ color: 'var(--ink-3)', fontSize: 12.5 }}>
             No invites yet.</div>
         : (
          <div style={SET_CARD}>
            {invites.map((iv, i) => (
              <SetRow key={i} first={i === 0}
                name={<span style={{ fontFamily: '"JetBrains Mono", monospace' }}>
                  {iv.code || iv}</span>}
                desc={iv.used_by ? 'used' : 'unused'}>
                <button onClick={() => navigator.clipboard &&
                  navigator.clipboard.writeText(iv.code || iv)} style={{
                  font: '700 11px Inter, sans-serif', padding: '5px 11px', borderRadius: 999,
                  border: '1px solid var(--border)', background: 'transparent',
                  color: 'var(--cyan)', cursor: 'pointer' }}>Copy</button>
              </SetRow>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add the delete panel with typed confirmation**

Append to `settings.jsx`, before the `window.SettingsPage` assignment:

```jsx
function SetDelete({ onBack, onNav }) {
  const [typed, setTyped] = useStateSet('');
  const [busy, setBusy] = useStateSet(false);
  const [err, setErr] = useStateSet('');
  const armed = typed.trim().toUpperCase() === 'DELETE';

  const go = async () => {
    if (!armed) return;
    setBusy(true); setErr('');
    try {
      const r = await fetch('/auth/account', { method: 'DELETE' });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || ('HTTP ' + r.status));
      }
      if (window.saClearToken) window.saClearToken();
      onNav && onNav('auth');
    } catch (e) { setErr(String(e.message || e)); setBusy(false); }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', padding: '18px 16px 90px' }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button onClick={onBack} style={{ width: 36, height: 36, borderRadius: 10,
            border: '1px solid var(--border)', background: 'var(--bg-surface)',
            display: 'grid', placeItems: 'center', cursor: 'pointer' }}>
            <Icon.ChevronL size={16}/>
          </button>
          <div style={{ fontSize: 20, fontWeight: 800, color: '#b91c1c' }}>Delete my account</div>
        </div>

        <div style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55, marginBottom: 18 }}>
          This erases your portfolio, holdings history, chat history and personal data
          across every store. It cannot be undone, and the data cannot be recovered.
        </div>

        <div style={{ fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 8 }}>
          Type <b>DELETE</b> to confirm:
        </div>
        <input value={typed} onChange={e => setTyped(e.target.value)} placeholder="DELETE"
          style={{ width: '100%', maxWidth: 260, padding: '10px 12px', borderRadius: 10,
            border: '1px solid var(--border)', background: 'var(--bg-surface)',
            fontSize: 14, outline: 'none', marginBottom: 16, boxSizing: 'border-box' }}/>

        {err ? <div style={{ color: '#b91c1c', fontSize: 12.5, marginBottom: 12 }}>{err}</div> : null}

        <div>
          <button onClick={go} disabled={!armed || busy} style={{
            padding: '11px 18px', borderRadius: 999, border: 'none',
            cursor: armed && !busy ? 'pointer' : 'default',
            background: armed ? '#b91c1c' : 'var(--bg-tinted)',
            color: armed ? '#fff' : 'var(--ink-3)', font: '700 13px Inter, sans-serif',
          }}>{busy ? 'Deleting…' : 'Delete my account permanently'}</button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify**

With the fixture server running (`AUTH_REQUIRED=false` ⇒ anonymous is the owner):
- Settings → Invite a friend → **Create invite code**. Expected: a code appears in the list. Confirm server-side: `curl -s localhost:8001/auth/invites`.
- Settings → Delete my account. Expected: the button stays disabled until you type `DELETE`. **Do not press it** — the owner account is server-side blocked from self-deleting (`auth_api.py:110`), so pressing it should surface "The owner account cannot self-delete." Confirm that error renders, which proves the wiring without destroying data.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/prototypes/settings.jsx
git commit -m "feat(settings): invite-code UI and DPDP account deletion

Both endpoints were built and unreachable. Deletion requires typing DELETE;
the owner-cannot-self-delete 403 surfaces inline."
```

---

### Task 8: Settings entry points

**Files:**
- Modify: `src/frontend/prototypes/home.jsx:238-264` (mobile menu), `:344-360` (header)
- Modify: `src/frontend/prototypes/index.html` (Tweaks quick-jump)

- [ ] **Step 1: Add Settings to the mobile menu**

In `home.jsx`, in the "Secondary screens" array (lines 240-244), add Settings as the first entry:

```jsx
          {[
            { screen:'settings',   label:'Settings',   icon:<Icon.Settings size={16}/> },
            { screen:'prompt-lab', label:'Prompt Lab', icon:<Icon.Settings size={16}/> },
            { screen:'analytics',  label:'Analytics',  icon:<Icon.Trend size={16}/> },
            { screen:'logs',       label:'Logs',        icon:<Icon.Layers size={16}/> },
          ].map(l => (
```

- [ ] **Step 2: Replace the old `NotifRow` in the menu with a Settings link**

The Preferences section (lines 253-257) is now redundant — notifications live in Settings. Delete the Preferences divider, label and `<NotifRow/>`, since Settings is one tap away in the list above. Leave the `NotifRow` function definition in place for now (Task 13 removes it if unused).

- [ ] **Step 3: Make the avatar open Settings**

In `home.jsx` line 354, wrap the avatar in a button:

```jsx
          <button onClick={()=>onNav?.('settings')} title="Settings" style={{ width:36, height:36, borderRadius:'50%', background:'linear-gradient(135deg,#22d3ee,#a78bfa)', display:'grid', placeItems:'center', color:'#fff', fontWeight:700, fontSize:13, flexShrink:0, border:'none', cursor:'pointer' }}>AS</button>
```

Note: the `nav-desktop` class is deliberately dropped here — Task 13 makes the avatar visible on mobile as the Settings entry point.

- [ ] **Step 4: Add a Tweaks quick-jump button**

In `index.html`, in the "Quick jump" `TweakSection`, add:

```jsx
        <TweakButton onClick={()=>nav('settings')}>Open settings</TweakButton>
```

- [ ] **Step 5: Verify**

Reload. Expected: the avatar (top-right) opens Settings; the mobile hamburger lists Settings; the Tweaks quick-jump works.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/prototypes/home.jsx src/frontend/prototypes/index.html
git commit -m "feat(settings): reachable from the avatar, mobile menu and quick-jump

Drops the one-item Preferences block from the hamburger — notifications
now live in Settings."
```

---

# PHASE 2 — Responsive

### Task 9: `useIsMobile()` + the Playwright audit harness

The harness must exist **before** the fixes, and must **fail** on the known-broken screens — that's the test-first cycle for this phase.

**Files:**
- Create: `src/frontend/prototypes/hooks.jsx`
- Create: `scripts/ui_responsive_audit.mjs`
- Modify: `src/frontend/prototypes/index.html`

**Interfaces:**
- Produces: `window.useIsMobile()` → `boolean`, reactive to resize.
- Produces: `node scripts/ui_responsive_audit.mjs [--base URL] [--out DIR]` → exit 0 if every screen/width passes, 1 otherwise; writes PNGs to `--out`.

- [ ] **Step 1: Create the hook**

```jsx
/* hooks.jsx — shared React hooks.
 *
 * The prototype styles inline, so CSS media queries only reach elements that
 * happen to carry a className. Components that need to restructure (not just
 * restyle) below 768px use this instead of another !important override.
 */
function useIsMobile(query) {
  const q = query || '(max-width: 767px)';
  const [match, setMatch] = React.useState(
    () => typeof window !== 'undefined' && window.matchMedia
      ? window.matchMedia(q).matches : false);
  React.useEffect(() => {
    if (!window.matchMedia) return;
    const mql = window.matchMedia(q);
    const on = e => setMatch(e.matches);
    setMatch(mql.matches);
    if (mql.addEventListener) mql.addEventListener('change', on);
    else mql.addListener(on);                      // Safari < 14
    return () => {
      if (mql.removeEventListener) mql.removeEventListener('change', on);
      else mql.removeListener(on);
    };
  }, [q]);
  return match;
}

/* Reactive viewport width. analytics.jsx read window.innerWidth once at render
 * with no resize listener, so its chart kept portrait width after a rotate
 * (audit item #9). Task 12 consumes this. */
function useViewportWidth() {
  const [w, setW] = React.useState(
    () => (typeof window !== 'undefined' ? window.innerWidth : 1280));
  React.useEffect(() => {
    const on = () => setW(window.innerWidth);
    window.addEventListener('resize', on);
    on();
    return () => window.removeEventListener('resize', on);
  }, []);
  return w;
}

window.useIsMobile = useIsMobile;
window.useViewportWidth = useViewportWidth;
```

- [ ] **Step 2: Register it first in `index.html`**

It must load before any consumer. Add immediately after the `data.jsx` tag (line 173):

```html
<script type="text/babel" src="hooks.jsx"></script>
```

- [ ] **Step 2b: Make `playwright` importable** (ruling, 2026-08-01)

`import { chromium } from 'playwright'` fails with `ERR_MODULE_NOT_FOUND` in this repo — there is no `package.json` and no `node_modules`, and `npx --package=playwright node` does not fix ESM resolution (Node resolves from the *script's* location, not npx's PATH). Create a root `package.json`:

```json
{
  "name": "stockagent-devtools",
  "private": true,
  "type": "module",
  "description": "Dev-only tooling. The app itself has no build step and no runtime npm dependencies.",
  "devDependencies": {
    "playwright": "^1.62.1"
  }
}
```

Then:

```bash
npm install
npx playwright install chromium
```

Append to `.gitignore`:

```
node_modules/
```

Verify the import resolves before writing the harness:

```bash
node -e "import('playwright').then(m=>console.log('RESOLVES', typeof m.chromium)).catch(e=>{console.error('FAILS',e.code);process.exit(1)})"
```

Expected: `RESOLVES function`.

- [ ] **Step 3: Write the audit harness**

`scripts/ui_responsive_audit.mjs`:

```js
/**
 * Responsive audit — spec 2026-07-31 §6.
 *
 * Asserts no screen overflows its viewport horizontally, at four widths, and
 * writes screenshots for the human pass. The assertion is necessary but not
 * sufficient: it cannot catch a container that grows while its contents stay
 * fixed-width (that distributes badly without overflowing), so the 1280px
 * screenshots still need eyes.
 *
 * Usage:
 *   python scripts/seed_fixture_ui.py --data-dir .uidev-data
 *   PORTFOLIO_DATA_DIR=.uidev-data python -m uvicorn services.api.server:app --port 8001
 *   node scripts/ui_responsive_audit.mjs --out .uidev-data/shots
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const arg = (k, d) => {
  const i = process.argv.indexOf(k);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : d;
};
const BASE = arg('--base', 'http://localhost:8001');
const OUT = arg('--out', '.uidev-data/shots');

const WIDTHS = [360, 390, 768, 1280];
const SCREENS = ['home', 'agents', 'portfolio', 'inbox', 'learn',
                 'rl-monitor', 'analytics', 'logs', 'prompt-lab', 'settings'];

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const failures = [];

for (const width of WIDTHS) {
  const ctx = await browser.newContext({
    viewport: { width, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  for (const screen of SCREENS) {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    // The prototype does no URL routing — drive it through the Tweaks quick-jump
    // by calling the app's own nav via a synthetic hash the App() reads, falling
    // back to clicking the nav entry.
    await page.evaluate(s => { window.__auditNav && window.__auditNav(s); }, screen);
    await page.waitForTimeout(600);

    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));
    const ok = overflow.scrollWidth <= overflow.innerWidth;
    if (!ok) {
      failures.push(`${screen} @ ${width}px — scrollWidth ${overflow.scrollWidth} > ${overflow.innerWidth}`);
    }
    await page.screenshot({
      path: path.join(OUT, `${screen}-${width}${ok ? '' : '-FAIL'}.png`),
      fullPage: true });
  }
  await ctx.close();
}

await browser.close();

if (failures.length) {
  console.error(`\n✗ ${failures.length} overflow failure(s):`);
  for (const f of failures) console.error('  ' + f);
  console.error(`\nScreenshots in ${OUT}`);
  process.exit(1);
}
console.log(`✓ no horizontal overflow across ${SCREENS.length} screens × ${WIDTHS.length} widths`);
console.log(`Screenshots in ${OUT} — eyeball the 1280px set for under-distribution.`);
process.exit(0);
```

- [ ] **Step 4: Expose a nav hook for the harness**

The prototype has no URL routing, so the harness needs a way in. In `index.html`, inside `App()`, after the `nav` function is defined (~line 268), add:

```jsx
  // Test seam for scripts/ui_responsive_audit.mjs — the prototype does no URL
  // routing, so the audit harness drives navigation through this.
  useEffect(() => { window.__auditNav = nav; return () => { window.__auditNav = null; }; });
```

- [ ] **Step 5: Run the harness and confirm it FAILS**

```bash
python scripts/seed_fixture_ui.py --data-dir .uidev-data
PORTFOLIO_DATA_DIR=.uidev-data python -m uvicorn services.api.server:app --port 8001 &
node scripts/ui_responsive_audit.mjs --out .uidev-data/shots
```

Expected: **exit 1**, with failures naming `rl-monitor` at 360px and 390px (the 474px weights grid) and likely `analytics`. Record the exact failure list — it is the Phase 2 to-do.

If it reports zero failures, the harness is not driving navigation correctly — verify `window.__auditNav` exists in the browser console before proceeding.

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json .gitignore \
        src/frontend/prototypes/hooks.jsx scripts/ui_responsive_audit.mjs \
        src/frontend/prototypes/index.html
git commit -m "test(ui): responsive audit harness + useIsMobile/useViewportWidth hooks

Asserts scrollWidth<=innerWidth across 10 screens x 4 widths and writes
screenshots. Currently RED on rl-monitor — that's the Phase 2 to-do list.
useIsMobile gives inline-styled components a reactive width signal; the
codebase had zero matchMedia usage."
```

---

### Task 10: Make `TopNav` universal

Root cause of "a few pages aren't compatible for phone": `TopNav` owns both the mobile bottom nav and the hamburger, and four screens don't render it.

**Files:**
- Modify: `src/frontend/prototypes/analytics.jsx:344-355`, `logs.jsx:88-100`, `prompt-lab.jsx:275-287`, `inbox.jsx:87-94`

- [ ] **Step 1: Add `TopNav` to `analytics.jsx`**

In `AnalyticsPage`, replace the custom sticky header (the `<div>` at line ~346 containing the back button) with:

```jsx
      <TopNav active="analytics" onNav={onNav} search="" setSearch={()=>{}}/>
```

- [ ] **Step 2: Same for `logs.jsx`**

Replace the header block at line ~93 with:

```jsx
      <TopNav active="logs" onNav={onNav} search="" setSearch={()=>{}}/>
```

- [ ] **Step 3: Same for `prompt-lab.jsx`**

Replace the header block at line ~280 with:

```jsx
      <TopNav active="prompt-lab" onNav={onNav} search="" setSearch={()=>{}}/>
```

- [ ] **Step 4: Same for `inbox.jsx`**

Replace the header block (lines 87-94, the back chevron + "Inbox" title) with:

```jsx
        <TopNav active="inbox" onNav={onNav} search="" setSearch={()=>{}}/>
```

Move it **outside** the `maxWidth: 640` wrapper so the nav spans full width — place it as the first child of the outer `<div>`, and keep the page title inside the wrapper.

- [ ] **Step 5: Add bottom padding so the mobile nav doesn't cover content**

In `styles.css`, append:

```css
/* ── Bottom-nav clearance — every screen, not just the ones built with it ── */
@media (max-width: 767px) {
  .proto-screen { padding-bottom: 92px !important; }
}
```

Add `className="proto-screen"` to the outermost `<div>` of `AnalyticsPage`, `LogsPage`, `PromptLabPage` and `InboxPage`.

- [ ] **Step 6: Verify**

```bash
node scripts/ui_responsive_audit.mjs --out .uidev-data/shots
```

Expected: analytics/logs/prompt-lab/inbox now show the bottom nav at 360px in the screenshots. Overflow failures may remain on rl-monitor — that's Task 11.

Manually confirm at 360px that you can reach every screen from every screen without the back button.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/prototypes/analytics.jsx src/frontend/prototypes/logs.jsx \
        src/frontend/prototypes/prompt-lab.jsx src/frontend/prototypes/inbox.jsx \
        src/frontend/prototypes/styles.css
git commit -m "fix(mobile): TopNav on analytics/logs/prompt-lab/inbox

These four screens never rendered TopNav, which owns both the bottom nav and
the hamburger — so on a phone they had no navigation at all beyond a back
chevron, with .proto-nav hidden under 768px."
```

---

### Task 11: RL Monitor — weights grid and daily log

**Files:**
- Modify: `src/frontend/prototypes/rl-monitor.jsx:620-660` (weights grid), `:252-300` (daily log)

**Interfaces:**
- Consumes: `window.useIsMobile` (Task 9).

- [ ] **Step 1: Stack the weights grid below 768px**

At the top of the component containing the weights grid (the function wrapping line 627), add:

```jsx
  const isMobile = useIsMobile();
```

Replace the row `<div>` style at line 627 with a conditional:

```jsx
              <div key={k} style={isMobile ? {
                display:'block', padding:'12px 14px',
                borderBottom: idx < agents.length-1 ? '1px solid var(--border)' : 'none',
              } : {
                display:'grid', gridTemplateColumns:'180px 1fr 60px 70px 60px',
                alignItems:'center', gap:'0 16px',
                padding:'10px 20px',
                borderBottom: idx < agents.length-1 ? '1px solid var(--border)' : 'none',
              }}>
```

On mobile the children stack in source order — name, bar, then the three numeric cells. Wrap the three numeric cells in a flex row so they sit on one line:

```jsx
                {/* Numeric cells — inline row on mobile, grid columns on desktop */}
                <div style={isMobile
                  ? { display:'flex', gap:14, marginTop:6, fontSize:11 }
                  : { display:'contents' }}>
```

Close this wrapper after the third numeric cell.

- [ ] **Step 2: Priority columns for the daily log below 768px**

Replace the `cols` constant (line 252) with:

```jsx
  const isMobile = useIsMobile();
  const cols = isMobile
    ? ['Date','Error %','Hit']
    : ['Date','Predicted ₹','Actual ₹','Error %','Pred Dir','Actual Dir','Hit','Miss Type','Confidence'];
```

Set the table's `minWidth` conditionally:

```jsx
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13,
          minWidth: isMobile ? 0 : 820 }}>
```

- [ ] **Step 3: Add row expansion on mobile**

Add expansion state above the `rows.map`:

```jsx
  const [openRow, setOpenRow] = React.useState(null);
```

In the row `<tr>`, add `onClick={() => isMobile && setOpenRow(openRow === i ? null : i)}`. Render only the three priority cells when `isMobile`, and append an expansion row after it:

```jsx
                {isMobile && openRow === i && (
                  <tr key={i + '-exp'} style={{ background:'var(--bg-tinted)' }}>
                    <td colSpan={3} style={{ padding:'10px 14px' }}>
                      {[['Predicted', p.predicted != null ? '₹' + p.predicted : '—'],
                        ['Actual',    p.actual != null ? '₹' + p.actual : '—'],
                        ['Direction', (p.predicted_direction || '—') + ' → ' + (p.actual_direction || '—')],
                        ['Miss type', missLabel || '—'],
                        ['Confidence', p.confidence != null ? p.confidence : '—']
                      ].map(([k2, v2]) => (
                        <div key={k2} style={{ display:'flex', justifyContent:'space-between',
                          padding:'3px 0', fontSize:12 }}>
                          <span style={{ color:'var(--ink-3)' }}>{k2}</span>
                          <span style={{ color:'var(--ink-1)', fontWeight:600 }}>{v2}</span>
                        </div>
                      ))}
                    </td>
                  </tr>
                )}
```

Because a `map` callback must return a single node, wrap the `<tr>` and its expansion in a `<React.Fragment key={i}>`.

Update the "click any row" caption (line 258) to read on mobile: `Most recent first · tap a row for the full record`.

- [ ] **Step 4: Verify**

```bash
node scripts/ui_responsive_audit.mjs --out .uidev-data/shots
```

Expected: **exit 0** for `rl-monitor` at 360 and 390. At 1280px confirm all 9 columns are still present and the weights grid still uses the 5-column layout.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/prototypes/rl-monitor.jsx
git commit -m "fix(mobile): RL Monitor weights grid and daily log

The weights grid was a 474px hard minimum with no scroll container, so it
clipped on every phone. The 9-column log now shows Date/Error/Hit with tap
to expand — horizontal scroll hid Hit and Miss Type, the two scanned columns.
Desktop layout unchanged."
```

---

### Task 12: Analytics, Logs and Learn

**Files:**
- Modify: `analytics.jsx:472,480,530,676`, `logs.jsx:143,354`, `learn.jsx:235`

- [ ] **Step 1: Collapse the Analytics two-column grid**

Line 472 — replace the hardcoded grid:

```jsx
      <div style={{ display: 'grid', gridTemplateColumns: 'var(--grid-2col)', gap: 16 }}>
```

`--grid-2col` is already `1fr` below 767px (`styles.css:100`).

- [ ] **Step 2: Make the chart width reactive**

Line 480 reads `window.innerWidth` once at render with no resize listener, so it keeps portrait width after a rotate.

**Corrected approach (ruling, 2026-08-01).** An earlier draft of this step used `Math.min(880, (isMobile ? 360 : 1280) - 80)`. That is wrong: `useIsMobile()` is `max-width: 767px`, so a **768px** viewport takes the non-mobile branch and yields an 880px chart on a 768px screen — a horizontal overflow at one of the exact widths Task 9 asserts. Use the reactive width instead.

Add at the top of the component:

```jsx
  const vw = useViewportWidth();
```

And replace line 480 with:

```jsx
            <HBarChart data={barData} width={Math.max(240, Math.min(880, vw - 80))}/>
```

The `Math.max(240, …)` floor keeps the chart legible if the viewport is ever narrower than 320px. Verify at 360, 390, 768 and 1280 — all four must satisfy the Task 9 overflow assertion.

- [ ] **Step 3: Add scroll wrappers to the two Analytics tables**

Wrap both `<table>` elements (lines 530 and 676) in:

```jsx
    <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
      {/* existing <table> … */}
    </div>
```

- [ ] **Step 4: Let the Logs inputs shrink**

Line 143 — replace `width: 140` with `flex: '1 1 120px', minWidth: 0`.
Line 354 — replace `width: 180` with `flex: '1 1 140px', minWidth: 0`.

Line 364 already has `flex: 1, minWidth: 160` — change `minWidth` to `0` so it can shrink below 160px on a 360px screen.

- [ ] **Step 5: Make the Learn drawer a bottom sheet**

Line 235 — add the class so it picks up the existing mobile override at `styles.css:139-147`:

```jsx
      <aside className="drawer-panel" style={{ width:560, zIndex:55 }}>
```

Remove the inline `position:'fixed', top:0, right:0, bottom:0` — `.drawer-panel` supplies those, and the media query overrides them on mobile.

- [ ] **Step 6: Verify**

```bash
node scripts/ui_responsive_audit.mjs --out .uidev-data/shots
```

Expected: **exit 0** across all 10 screens × 4 widths.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/prototypes/analytics.jsx src/frontend/prototypes/logs.jsx \
        src/frontend/prototypes/learn.jsx
git commit -m "fix(mobile): analytics grid/tables, logs inputs, learn drawer

Analytics had an inline 1fr-1fr grid CSS vars couldn't reach and a chart
width read once from innerWidth with no resize listener. Learn's drawer was
inline-positioned so it missed the .drawer-panel bottom-sheet override."
```

---

### Task 13: Mobile search, bell and avatar

`nav-desktop` hides all three below 768px, so phone users have no search and no account affordance.

**Files:**
- Modify: `src/frontend/prototypes/home.jsx:316,350,354`, `styles.css`

- [ ] **Step 1: Move search into the mobile menu**

In `home.jsx`, inside the `.mobile-menu` block, add above the nav links (after the header at line 228):

```jsx
          <div style={{ position:'relative', marginBottom:16 }}>
            <Icon.Search size={16} style={{ position:'absolute', left:12, top:'50%',
              transform:'translateY(-50%)', color:'var(--ink-3)', pointerEvents:'none' }}/>
            <input value={search} onChange={e=>handleSearch(e.target.value)}
              placeholder="Search MARUTI, Tata Motors..." style={{
                width:'100%', padding:'11px 12px 11px 36px', border:'1px solid var(--border)',
                borderRadius:10, background:'var(--bg-base)', fontSize:14, outline:'none',
                boxSizing:'border-box' }}/>
          </div>
          {results.length > 0 && (
            <div style={{ marginBottom:12, border:'1px solid var(--border)', borderRadius:12,
              overflow:'hidden' }}>
              {results.slice(0, 5).map((r, i) => (
                <div key={i} style={{ padding:'10px 14px', fontSize:13,
                  borderTop: i ? '1px solid var(--border)' : 'none' }}>{r.symbol || r.name}</div>
              ))}
            </div>
          )}
```

- [ ] **Step 2: Show the avatar on mobile**

Task 8 already removed `nav-desktop` from the avatar. Confirm it renders at 360px; it is the Settings entry point.

- [ ] **Step 3: Keep the bell desktop-only**

The bell (line 350) duplicates the Inbox tab that already sits in the bottom nav. Leave `nav-desktop` on it — adding it to mobile would be a third route to the same screen.

- [ ] **Step 4: Verify**

At 360px: open the hamburger, type in search, confirm results appear; confirm the avatar is visible in the header and opens Settings.

```bash
node scripts/ui_responsive_audit.mjs --out .uidev-data/shots
```

Expected: exit 0.

- [ ] **Step 5: Full regression**

```bash
python -m pytest -q
```

Expected: 0 failed, 0 errors (baseline 2379 passed).

- [ ] **Step 6: Eyeball the wide screenshots**

Open every `*-1280.png` in `.uidev-data/shots`. The overflow assertion cannot catch a container that grows while its contents stay fixed-width, so check specifically for content stranded in a narrow column inside a wide empty region.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/prototypes/home.jsx
git commit -m "fix(mobile): search in the hamburger, avatar visible as Settings entry

Search, bell and avatar were all nav-desktop, so phone users had no search
and no account affordance. The bell stays desktop-only — the bottom nav
already routes to Inbox."
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §3.1 data source | 4, 5 |
| §3.2 backend enrichment | 1 |
| §3.3 components + layout | 3, 4, 5 |
| §3.4 edge cases | 2 (fixture), verified in 3 |
| §4.1 #1 nav | 10 |
| §4.1 #2 weights grid | 11 |
| §4.1 #3 analytics grid | 12 |
| §4.1 #4 logs inputs | 12 |
| §4.1 #5 analytics tables | 12 |
| §4.1 #6 daily log | 11 |
| §4.1 #7 learn drawer | 12 |
| §4.1 #8 inbox tab row | *not addressed — Low severity, no 5th tab exists* |
| §4.1 #9 useIsMobile | 9 |
| §4.3 hidden affordances | 8, 13 |
| §5 Settings | 6, 7, 8 |
| §6 verification | 2, 9, 13 |

**Known gap:** audit item #8 (inbox tab row won't take a 5th tab) is not addressed. It is Low severity and speculative — there is no fifth tab. Left deliberately.

**Type consistency:** `enrich_brief_for_api` is defined in Task 1 and consumed in Tasks 3/4 via `verdict_plain`, `label_plain`, `gloss` — names match. `useIsMobile` is defined in Task 9 and consumed in Tasks 11/12 — matches. `BVFold`, `BVChip`, `bvINR`, `bvLongDate` are defined in Task 3 and consumed in Task 5 — **all four are explicitly assigned to `window`** in Task 3 Step 1.

**Ordering constraint:** Task 5 depends on helpers from Task 3, so `digest-view.jsx` and `weekly-view.jsx` must be registered **after** `brief-view.jsx` in `index.html` — Task 5 Step 3 does this. Do not rely on top-level `const`/`function` declarations leaking across `<script type="text/babel">` boundaries; the codebase's established convention (`icons.jsx:45`, `home.jsx:1523-1526`) is explicit `window.X = X` assignment, and the plan follows it.

**Note on Task 6 Step 5:** verification there is awkward because the Settings nav entry doesn't exist until Task 8. If that proves fiddly, do Task 8 Step 4 (the Tweaks quick-jump button) early — it is a one-line change and makes Task 6 verifiable on its own.
