# Notification Deep-Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A notification tap opens an in-app Inbox screen showing exactly the content the notification announced (brief / digest / weekly / alerts), instead of the cosmetic login screen.

**Architecture:** Hash deep-links (`/#/inbox/<tab>`) carried in the push payload `url`; sw.js v6 posts a message to an already-open app (warm tap) or `openWindow(url)` (cold tap); `index.html` gains a one-shot hash parser, a SW-message listener, and a wired "Remember me" flag so remembered sessions skip the auth screen; a new `inbox.jsx` screen renders each content type from existing endpoints, which gain a `?format=text` mode reusing the exact renderers the notifications themselves use.

**Tech Stack:** Python/FastAPI (pytest), vanilla React 18 via babel-standalone JSX prototype, service worker, Playwright (node) for e2e.

**Spec:** `docs/superpowers/specs/2026-07-24-notification-deeplinks-design.md`

## Global Constraints

- **NEVER `git push` to main between 16:25–17:15 IST on a trading day** (deploy kills the 16:30 portfolio pipeline).
- The Python suite's fail-set must be **identical before and after** (record baseline first; 2026-07-19 baseline was "285 passed / 7 skipped" — trust the fresh baseline you record, not this number).
- Frontend files are plain JSX compiled by babel-standalone in the browser — no imports/exports, no JSX build step; components are declared as global functions, React hooks aliased per-file (`const { useState: useStateInbox } = React;`).
- `window.fetch` is already wrapped (index.html) to attach `X-Scheduler-Key` — inbox code calls plain `fetch()` and gets auth for free.
- Deep-link hash grammar (single source of truth): `#/inbox` or `#/inbox/<tab>` where `<tab>` ∈ `brief|digest|weekly|alerts`; default tab `brief`.
- localStorage keys: `sa_remembered` = `'1'` (session memory). Do not touch `sa_key` (API key) or tweaks storage.
- Commit after every task with the exact message given; end every commit message body with `Co-Authored-By:` line per repo convention (see `git log`).

---

### Task 1: Senders pass deep-link URLs

**Files:**
- Modify: `core/delivery/brief.py` (the `deliver(...)` call inside `run_morning_brief`, ~line 277)
- Modify: `core/delivery/weekly.py` (the `deliver(...)` call inside `run_weekly_review`, ~line 247)
- Modify: `core/delivery/alerts.py` (the `deliver(...)` call inside `emit_alerts`, ~line 148)
- Modify: `core/portfolio/pipeline.py` (the `deliver(...)` call for the EOD digest, ~line 203)
- Test: `tests/unit/test_delivery_brief.py`, `tests/unit/test_delivery_weekly.py`, `tests/unit/test_delivery_alerts.py` (append one test each)

**Interfaces:**
- Consumes: `core.delivery.channels.deliver(title, body, url="/", user_id=None)` — already accepts `url`; **no change to channels.py**.
- Produces: push payload `data.url` values `"/#/inbox/brief"`, `"/#/inbox/weekly"`, `"/#/inbox/alerts"`, `"/#/inbox/digest"` that Tasks 3–5 route on.

Import-style note (matters for monkeypatching): `brief.py`, `weekly.py`, `alerts.py` do module-level `from core.delivery.channels import deliver` → tests patch the *using* module's attribute (`br.deliver`, `wk.deliver`, `al.deliver`). `pipeline.py` imports `deliver` *inside* the function → tests patch `channels_mod.deliver` (existing tests already do this).

- [ ] **Step 1: Record suite baseline**

Run: `python -m pytest tests/ -q 2>&1 | tail -5`
Save the summary line (pass/fail/skip counts + names of any failures) — this is the baseline every later task compares against.

- [ ] **Step 2: Write the three failing tests**

Append to `tests/unit/test_delivery_brief.py`:

```python
def test_run_brief_delivers_inbox_deeplink(tmp_path, monkeypatch):
    from core.config import settings
    captured = {}
    monkeypatch.setattr(br, "is_trading_day", lambda on: True)
    monkeypatch.setattr(br, "list_user_ids", lambda: ["u1"])
    monkeypatch.setattr(br, "build_morning_brief",
                        lambda uid, on, store=None: {"date": on.isoformat(),
                                                     "kind": "morning_brief",
                                                     "lockin_flags": []})
    monkeypatch.setattr(br, "render_brief_text", lambda b: "text")
    monkeypatch.setattr(br, "deliver",
                        lambda *a, **k: captured.update(k) or {"delivered": True})
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    br.run_morning_brief(date(2026, 7, 22))
    assert captured["url"] == "/#/inbox/brief"
```

Append to `tests/unit/test_delivery_weekly.py` (add `from datetime import date` and `import core.delivery.weekly as wk` to that file's imports if not present — check its header first):

```python
def test_run_weekly_delivers_inbox_deeplink(tmp_path, monkeypatch):
    from core.config import settings
    captured = {}
    monkeypatch.setattr(wk, "list_user_ids", lambda: ["u1"])
    monkeypatch.setattr(wk, "build_weekly_review",
                        lambda uid, on, store=None: {"date": on.isoformat(),
                                                     "kind": "weekly_review"})
    monkeypatch.setattr(wk, "render_weekly_text", lambda r: "text")
    monkeypatch.setattr(wk, "deliver",
                        lambda *a, **k: captured.update(k) or {"delivered": True})
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    wk.run_weekly_review(date(2026, 7, 22))
    assert captured["url"] == "/#/inbox/weekly"
```

Append to `tests/unit/test_delivery_alerts.py` (its header already imports the alerts module — match the alias it uses; shown here as `al`):

```python
def test_emit_alerts_delivers_inbox_deeplink(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(al, "deliver",
                        lambda *a, **k: captured.update(k) or {"delivered": True})
    al.emit_alerts(
        [al.AlertEvent(date="2026-07-22", kind="test", symbol="X",
                       message="m", severity="warning")],
        user_id="u1", sent_log=str(tmp_path / "sent.jsonl"))
    assert captured["url"] == "/#/inbox/alerts"
```

- [ ] **Step 3: Run them — verify all three FAIL**

Run: `python -m pytest tests/unit/test_delivery_brief.py::test_run_brief_delivers_inbox_deeplink tests/unit/test_delivery_weekly.py::test_run_weekly_delivers_inbox_deeplink tests/unit/test_delivery_alerts.py::test_emit_alerts_delivers_inbox_deeplink -v`
Expected: 3 × FAIL with `KeyError: 'url'` (deliver is currently called without `url`).

- [ ] **Step 4: Make the four one-line changes**

`core/delivery/brief.py` — inside `run_morning_brief`:
```python
# before
deliver(f"Morning brief — {on}", render_brief_text(brief), user_id=user_id)
# after
deliver(f"Morning brief — {on}", render_brief_text(brief),
        url="/#/inbox/brief", user_id=user_id)
```

`core/delivery/weekly.py` — inside `run_weekly_review`:
```python
# before
deliver(f"Weekly review — {on}", render_weekly_text(review), user_id=user_id)
# after
deliver(f"Weekly review — {on}", render_weekly_text(review),
        url="/#/inbox/weekly", user_id=user_id)
```

`core/delivery/alerts.py` — inside `emit_alerts`:
```python
# before
outcome = deliver(title, body, user_id=user_id) or {}
# after
outcome = deliver(title, body, url="/#/inbox/alerts", user_id=user_id) or {}
```

`core/portfolio/pipeline.py` — the EOD digest delivery:
```python
# before
deliver(
    f"EOD digest — {review_date}",
    f"{len(advice)} holdings reviewed; {n_esc} escalation(s)"
    + (f"; {len(txns)} trade(s) executed" if txns else "")
    + ". Open the app or ask the chat for 'brief' for details.",
    user_id=user_id,
)
# after
deliver(
    f"EOD digest — {review_date}",
    f"{len(advice)} holdings reviewed; {n_esc} escalation(s)"
    + (f"; {len(txns)} trade(s) executed" if txns else "")
    + ". Open the app or ask the chat for 'brief' for details.",
    url="/#/inbox/digest",
    user_id=user_id,
)
```

- [ ] **Step 5: Extend the existing pipeline e2e test to assert the digest url**

In `tests/unit/test_portfolio_pipeline.py::test_pipeline_end_to_end`, the delivery is stubbed hermetic:
```python
monkeypatch.setattr(channels_mod, "deliver", lambda *a, **k: {"delivered": False})
```
Replace that line with a capturing stub and add the assertion at the end of the test:
```python
delivered_kwargs = {}
monkeypatch.setattr(channels_mod, "deliver",
                    lambda *a, **k: delivered_kwargs.update(k) or {"delivered": False})
```
…and as the test's final line:
```python
assert delivered_kwargs.get("url") == "/#/inbox/digest"
```
(Only the digest goes through `channels_mod.deliver` here — `alerts.py` bound its own `deliver` reference at import time, so alert deliveries don't touch this stub.)

- [ ] **Step 6: Run the three new tests + the pipeline test — all PASS**

Run: `python -m pytest tests/unit/test_delivery_brief.py tests/unit/test_delivery_weekly.py tests/unit/test_delivery_alerts.py tests/unit/test_portfolio_pipeline.py -q`
Expected: all pass (plus pre-existing results unchanged).

- [ ] **Step 7: Commit**

```bash
git add core/delivery/brief.py core/delivery/weekly.py core/delivery/alerts.py core/portfolio/pipeline.py tests/unit/test_delivery_brief.py tests/unit/test_delivery_weekly.py tests/unit/test_delivery_alerts.py tests/unit/test_portfolio_pipeline.py
git commit -m "feat(delivery): notification payloads carry /#/inbox deep-link urls"
```

---

### Task 2: `?format=text` on the three latest-content endpoints

**Files:**
- Create: `core/portfolio/digest_text.py`
- Modify: `services/api/routes/delivery_api.py` (`brief_latest`, `weekly_latest`)
- Modify: `services/api/routes/portfolio_api.py` (`get_latest_digest`)
- Test: `tests/unit/test_delivery_api.py`, `tests/unit/test_portfolio_digest_text.py` (new)

**Interfaces:**
- Consumes: `core.delivery.brief.render_brief_text(brief: dict) -> str`, `core.delivery.weekly.render_weekly_text(review: dict) -> str` (existing; only hard requirement of each is a `"date"` key).
- Produces: `GET /delivery/brief/latest?format=text` → `{"date": str, "text": str}` (same for weekly); `GET /portfolio/digest/latest?format=text` → `{"date": str, "text": str}`; `render_digest_text(digest: dict) -> str`. Task 5's Inbox consumes these.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_portfolio_digest_text.py`:

```python
"""Inbox deep-links — EOD digest text renderer."""
from core.portfolio.digest_text import render_digest_text


def _digest():
    return {"date": "2026-07-22", "portfolio_value": 110000.0,
            "total_pnl_pct": 10.0,
            "holdings": [
                {"symbol": "OLDCO", "verdict": "EXIT", "reason": "stop breached"},
                {"symbol": "GOODCO", "verdict": "HOLD", "reason": "thesis intact"},
            ],
            "escalations": ["OLDCO"]}


def test_render_digest_text_sections():
    text = render_digest_text(_digest())
    lines = text.splitlines()
    assert lines[0] == "EOD digest — 2026-07-22"
    assert any("110,000" in l for l in lines)
    assert any(l.startswith("EXIT: OLDCO") for l in lines)
    assert "Escalations: OLDCO" in lines


def test_render_digest_text_minimal():
    assert render_digest_text({"date": "2026-07-22"}) == "EOD digest — 2026-07-22"
```

Append to `tests/unit/test_delivery_api.py` (uses that file's existing `_client()` helper):

```python
def test_brief_latest_format_text(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    from core.portfolio.store import PortfolioStore
    PortfolioStore(base_dir=str(tmp_path)).save_brief(
        {"date": "2026-07-22", "kind": "morning_brief", "headline": "Calm open."})
    resp = _client().get("/delivery/brief/latest?format=text")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-07-22"
    assert body["text"].startswith("Morning brief — 2026-07-22")


def test_weekly_latest_format_text(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    from core.portfolio.store import PortfolioStore
    PortfolioStore(base_dir=str(tmp_path)).save_weekly(
        {"date": "2026-07-20", "kind": "weekly_review"})
    resp = _client().get("/delivery/weekly/latest?format=text")
    assert resp.status_code == 200
    assert resp.json()["text"].startswith("Weekly review — 2026-07-20")
```

Also append a digest `format=text` test to `tests/unit/test_delivery_api.py`'s portfolio counterpart. Find the portfolio API test file first: `grep -l "digest/latest" tests/unit/*.py`. Add there (adapting to that file's client helper; if none tests the route, add to `tests/unit/test_portfolio_digest_text.py` using a `TestClient` on `services.api.routes.portfolio_api.router` mirroring `test_delivery_api.py`'s `_client()` pattern):

```python
def test_digest_latest_format_text(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import services.api.routes.portfolio_api as papi
    from core.config import settings
    from core.portfolio.store import PortfolioStore
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    PortfolioStore(base_dir=str(tmp_path)).save_digest(_digest() | {"user_id": "default"})
    app = FastAPI(); app.include_router(papi.router)
    resp = TestClient(app).get("/portfolio/digest/latest?format=text")
    assert resp.status_code == 200
    assert resp.json()["text"].startswith("EOD digest — 2026-07-22")
```

(Note: `PortfolioStore` constructor args — existing tests use `PortfolioStore(base_dir=str(tmp_path))` and `save_digest(dict)`; keep exactly that. If `save_digest` validates `user_id`, the `| {"user_id": "default"}` covers it; drop it if unnecessary.)

- [ ] **Step 2: Run — verify FAIL**

Run: `python -m pytest tests/unit/test_portfolio_digest_text.py tests/unit/test_delivery_api.py -q`
Expected: new tests FAIL (`ModuleNotFoundError: core.portfolio.digest_text`; format=text returns full JSON without `"text"`).

- [ ] **Step 3: Implement**

Create `core/portfolio/digest_text.py`:

```python
"""EOD digest → human-readable text. Single renderer shared by the API's
?format=text mode so the Inbox shows the same content notifications describe."""
from __future__ import annotations


def render_digest_text(digest: dict) -> str:
    lines = [f"EOD digest — {digest.get('date', '')}"]
    pv = digest.get("portfolio_value")
    pnl = digest.get("total_pnl_pct")
    if pv is not None:
        row = f"Portfolio value: ₹{pv:,.0f}"
        if pnl is not None:
            row += f" ({pnl:+.1f}% total P&L)"
        lines.append(row)
    for h in digest.get("holdings", []):
        row = f"{h.get('verdict', '?')}: {h.get('symbol', '?')}"
        if h.get("reason"):
            row += f" — {h['reason']}"
        lines.append(row)
    esc = digest.get("escalations") or []
    if esc:
        lines.append("Escalations: " + ", ".join(esc))
    return "\n".join(lines)
```

`services/api/routes/delivery_api.py` — extend both latest endpoints (pattern shown for brief; weekly is identical with `load_latest_weekly` + `render_weekly_text`):

```python
@router.get("/brief/latest", summary="Latest morning brief")
async def brief_latest(
    user_id: str | None = Query(default=None),
    format: str | None = Query(default=None, description="'text' → rendered text"),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    brief = PortfolioStore(user_id=user_id).load_latest_brief()
    if brief is None:
        raise HTTPException(status_code=404, detail="No brief yet — run POST /delivery/run-brief.")
    if format == "text":
        from core.delivery.brief import render_brief_text
        return {"date": brief.get("date"), "text": render_brief_text(brief)}
    return brief
```

`services/api/routes/portfolio_api.py` — same shape:

```python
@router.get("/digest/latest", summary="Latest EOD digest")
async def get_latest_digest(
    user_id: str | None = Query(default=None),
    format: str | None = Query(default=None, description="'text' → rendered text"),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    digest = _store(user_id).load_latest_digest()
    if digest is None:
        raise HTTPException(status_code=404, detail="No digest yet — run the advisor first.")
    if format == "text":
        from core.portfolio.digest_text import render_digest_text
        return {"date": digest.get("date"), "text": render_digest_text(digest)}
    return digest
```

- [ ] **Step 4: Run — verify PASS**

Run: `python -m pytest tests/unit/test_portfolio_digest_text.py tests/unit/test_delivery_api.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/digest_text.py services/api/routes/delivery_api.py services/api/routes/portfolio_api.py tests/unit/test_portfolio_digest_text.py tests/unit/test_delivery_api.py
git commit -m "feat(api): ?format=text on brief/weekly/digest latest endpoints for the Inbox"
```

---

### Task 3: sw.js v6 — warm tap navigates via postMessage

**Files:**
- Modify: `src/frontend/prototypes/sw.js`

**Interfaces:**
- Produces: SW→page message `{type: 'sa-open', url: string}` on a warm notification tap (Task 4's listener consumes it); cold tap `openWindow(data.url)` unchanged. `'/inbox.jsx'` added to the SHELL list (file arrives in Task 5 — install's `addAll` failure is already non-blocking by design, so ordering is safe, but do Tasks 3–5 in one deploy anyway).

No JS unit framework exists — this is verified by Task 6's e2e. Keep v5's cache-failure fallbacks (`safeOpen` etc.) untouched.

- [ ] **Step 1: Bump version and SHELL**

```js
const VERSION = 'v6';
```
And add `'/inbox.jsx'` to the `SHELL` array after `'/rl-data.jsx', '/rl-monitor.jsx',`.

- [ ] **Step 2: Replace the notificationclick handler**

```js
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if ('focus' in w) {
          // Warm tap: tell the open app where to go, then bring it forward.
          w.postMessage({ type: 'sa-open', url });
          return w.focus();
        }
      }
      return clients.openWindow(url);
    })
  );
});
```

- [ ] **Step 3: Commit**

```bash
git add src/frontend/prototypes/sw.js
git commit -m "feat(sw): v6 — warm notification tap posts sa-open deep link to the app"
```

---

### Task 4: index.html routing + remembered session; auth.jsx Remember-me wiring

**Files:**
- Modify: `src/frontend/prototypes/index.html` (the `<script type="text/babel">` App block, lines ~161–270)
- Modify: `src/frontend/prototypes/auth.jsx` (`AuthScreen`)

**Interfaces:**
- Consumes: `{type:'sa-open', url}` SW messages (Task 3); hash grammar from Global Constraints.
- Produces: `onNav(screen)` navigation wrapper passed to all pages (clears `sa_remembered` on `'auth'`); `AuthScreen({onAuthed})` now calls `onAuthed(remember: boolean)`; App state `inboxTab` + screen `'inbox'` that Task 5 renders.

- [ ] **Step 1: Add the deep-link helper above `function App()`**

```jsx
// Notification deep links: '#/inbox' or '#/inbox/<brief|digest|weekly|alerts>'.
// One-shot: consumed (removed from the URL) so refresh doesn't re-trigger.
function saConsumeDeepLink() {
  const m = /^#\/inbox(?:\/(brief|digest|weekly|alerts))?$/.exec(location.hash || '');
  if (!m) return null;
  history.replaceState(null, '', location.pathname + location.search);
  return { screen: 'inbox', tab: m[1] || 'brief' };
}
```

- [ ] **Step 2: Rework App state (replace `const [screen, setScreen] = useState('auth');`)**

```jsx
const [deepLink] = useState(saConsumeDeepLink);          // lazy: runs once
const remembered = localStorage.getItem('sa_remembered') === '1';
const [screen, setScreen] = useState(
  remembered ? (deepLink ? deepLink.screen : 'home') : 'auth');
const [inboxTab, setInboxTab] = useState(deepLink ? deepLink.tab : 'brief');
// Where to land after login when the tap arrived logged-out:
const [pendingDest, setPendingDest] = useState(!remembered && deepLink ? deepLink : null);
```

- [ ] **Step 3: Add nav wrapper + auth handler (replace `const goHome = ...` / `const goAgents = ...` and keep names used below)**

```jsx
const nav = (s) => {
  if (s === 'auth') localStorage.removeItem('sa_remembered');   // sign out
  setScreen(s);
};
const goHome = () => nav('home');
const goAgents = () => nav('agents');
const onAuthed = (remember) => {
  if (remember) localStorage.setItem('sa_remembered', '1');
  if (pendingDest) {
    setInboxTab(pendingDest.tab);
    setScreen(pendingDest.screen);
    setPendingDest(null);
  } else {
    setScreen('home');
  }
};
```

- [ ] **Step 4: Add the SW message listener (new useEffect inside App)**

```jsx
// Warm notification tap: SW posts {type:'sa-open', url:'/#/inbox/<tab>'}.
useEffect(() => {
  if (!('serviceWorker' in navigator)) return;
  const onMsg = (e) => {
    const d = e.data || {};
    if (d.type !== 'sa-open') return;
    const m = /#\/inbox(?:\/(brief|digest|weekly|alerts))?$/.exec(d.url || '');
    const tab = (m && m[1]) || 'brief';
    setInboxTab(tab);
    if (localStorage.getItem('sa_remembered') === '1') setScreen('inbox');
    else { setPendingDest({ screen: 'inbox', tab }); setScreen('auth'); }
  };
  navigator.serviceWorker.addEventListener('message', onMsg);
  return () => navigator.serviceWorker.removeEventListener('message', onMsg);
}, []);
```

- [ ] **Step 5: Rewire the render tree**

- `{screen === 'auth' && <AuthScreen onAuthed={onAuthed}/>}` (was `onAuthed={goHome}`)
- Every `onNav={setScreen}` → `onNav={nav}`; every `setScreen('...')` in the NavChip row / TweaksPanel quick-jump → `nav('...')` (the Sign-out chip therefore clears the flag automatically).
- Add the screen branch (next to the others): `{screen === 'inbox' && <InboxPage onNav={nav} tab={inboxTab} setTab={setInboxTab}/>}` — component arrives in Task 5; until then this branch is unreachable in manual testing (don't navigate to it).

- [ ] **Step 6: Wire Remember-me in `auth.jsx`**

In `AuthScreen`: add state, wire the checkbox, pass the flag through:

```jsx
const [remember, setRemember] = useStateAuth(true);
const submit = (e) => { e.preventDefault(); onAuthed(remember); };
```
Checkbox (login tab): `<input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/> Remember me`
Social buttons: `<SocialBtn onClick={()=>onAuthed(remember)} .../>` (both Google and Apple).

- [ ] **Step 7: Manual smoke via local server**

Start: `python -m uvicorn services.api.server:app --host 127.0.0.1 --port 8123 --workers 1`
(If you don't want the scheduler running locally, first hold its singleton lock in another terminal: `python -c "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',59321)); s.listen(1); time.sleep(3600)"`.)
In a browser: log in with Remember me ON → close tab → reopen `http://127.0.0.1:8123/` → Expected: lands on home, no login. Open `http://127.0.0.1:8123/#/inbox/brief` → Expected: no crash; blank inbox branch is fine pre-Task-5; URL hash is consumed. Sign out → reopen → Expected: login screen again.

- [ ] **Step 8: Commit**

```bash
git add src/frontend/prototypes/index.html src/frontend/prototypes/auth.jsx
git commit -m "feat(pwa): hash deep-links, sw message routing, wired Remember-me session"
```

---

### Task 5: Inbox screen

**Files:**
- Create: `src/frontend/prototypes/inbox.jsx`
- Modify: `src/frontend/prototypes/index.html` (script tag)
- Modify: `src/frontend/prototypes/home.jsx` (`navLinks` array in `TopNav`)

**Interfaces:**
- Consumes: `GET /delivery/brief/latest?format=text`, `/portfolio/digest/latest?format=text`, `/delivery/weekly/latest?format=text` → `{date, text}`; `GET /delivery/alerts?limit=20` → `{alerts: [{date, kind, symbol, message, severity, ...}]}`; app CSS vars (`--ink-1/2/3`, `--bg-surface`, `--bg-tinted`, `--border`, `--cyan`); `Icon.Bell`, `Icon.ChevronLeft` (check `icons.jsx` for the exact back-arrow icon name — if there is no ChevronLeft, use the one Home's back buttons use, e.g. `Icon.ArrowLeft`; `grep -n "ArrowLeft\|Chevron" src/frontend/prototypes/icons.jsx`).
- Produces: global `InboxPage({onNav, tab, setTab})` component used by Task 4's screen branch.

- [ ] **Step 1: Create `src/frontend/prototypes/inbox.jsx`**

```jsx
/* Inbox — notification landing screen. Each tab renders the latest content of
 * one notification type, fetched as pre-rendered text (?format=text) so it
 * matches the push/email body exactly. */
const { useState: useStateInbox, useEffect: useEffectInbox } = React;

const INBOX_TABS = [
  { key: 'brief',  label: 'Brief',  url: '/delivery/brief/latest?format=text' },
  { key: 'digest', label: 'Digest', url: '/portfolio/digest/latest?format=text' },
  { key: 'weekly', label: 'Weekly', url: '/delivery/weekly/latest?format=text' },
  { key: 'alerts', label: 'Alerts', url: '/delivery/alerts?limit=20' },
];

const INBOX_EMPTY = {
  brief:  'No morning brief yet — it builds at 08:50 IST on trading days.',
  digest: 'No EOD digest yet — the advisor runs after 16:30 IST on trading days.',
  weekly: 'No weekly review yet — it builds on Sunday evenings.',
  alerts: 'No alerts recorded yet.',
};

const SEV_COLOR = { critical: '#dc2626', warning: '#d97706', info: 'var(--ink-3)' };

function InboxPage({ onNav, tab, setTab }) {
  const active = INBOX_TABS.some(t => t.key === tab) ? tab : 'brief';
  const [state, setState] = useStateInbox({ status: 'loading' });
  const [nonce, setNonce] = useStateInbox(0);          // retry trigger

  useEffectInbox(() => {
    let alive = true;
    setState({ status: 'loading' });
    const spec = INBOX_TABS.find(t => t.key === active);
    fetch(spec.url)
      .then(async (r) => {
        if (r.status === 404) return { status: 'empty' };
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return { status: 'ok', data: await r.json() };
      })
      .catch((e) => ({ status: 'error', message: String((e && e.message) || e) }))
      .then((s) => { if (alive) setState(s); });
    return () => { alive = false; };
  }, [active, nonce]);

  const card = {
    background: 'var(--bg-surface)', border: '1px solid var(--border)',
    borderRadius: 16, padding: '18px 16px',
  };

  const renderText = (data) => {
    const lines = String(data.text || '').split('\n').filter(l => l.trim() !== '');
    if (!lines.length) return <div style={{ color: 'var(--ink-3)' }}>{INBOX_EMPTY[active]}</div>;
    return (
      <div style={card}>
        <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--ink-1)', marginBottom: 10 }}>
          {lines[0]}
        </div>
        {lines.slice(1).map((l, i) => (
          <div key={i} style={{ fontSize: 13, color: 'var(--ink-2)', padding: '5px 0',
            borderTop: i ? '1px solid var(--border)' : 'none' }}>{l}</div>
        ))}
      </div>
    );
  };

  const renderAlerts = (data) => {
    const alerts = (data && data.alerts) || [];
    if (!alerts.length) return <div style={{ color: 'var(--ink-3)' }}>{INBOX_EMPTY.alerts}</div>;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {alerts.map((a, i) => (
          <div key={i} style={card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase',
                color: SEV_COLOR[a.severity] || 'var(--ink-3)' }}>{a.severity || 'info'}</span>
              {a.symbol ? <span style={{ fontSize: 12, fontWeight: 700,
                color: 'var(--ink-1)' }}>{a.symbol}</span> : null}
              <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--ink-3)' }}>{a.date}</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--ink-2)' }}>{a.message}</div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', padding: '18px 16px 90px' }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18 }}>
          <button onClick={() => onNav?.('home')} style={{ width: 36, height: 36, borderRadius: 10,
            border: '1px solid var(--border)', background: 'var(--bg-surface)',
            display: 'grid', placeItems: 'center', cursor: 'pointer' }}>
            <Icon.ChevronLeft size={16}/>
          </button>
          <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--ink-1)' }}>Inbox</div>
        </div>

        <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
          {INBOX_TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              flex: 1, padding: '9px 0', borderRadius: 999, fontSize: 12, fontWeight: 700,
              border: '1px solid var(--border)', cursor: 'pointer',
              background: active === t.key ? 'var(--bg-tinted)' : 'transparent',
              color: active === t.key ? 'var(--cyan)' : 'var(--ink-2)',
            }}>{t.label}</button>
          ))}
        </div>

        {state.status === 'loading' && <div style={{ color: 'var(--ink-3)' }}>Loading…</div>}
        {state.status === 'empty'   && <div style={{ ...card, color: 'var(--ink-3)' }}>{INBOX_EMPTY[active]}</div>}
        {state.status === 'error'   && (
          <div style={{ ...card, color: 'var(--ink-2)' }}>
            Couldn't load this — {state.message}.
            <button onClick={() => setNonce(n => n + 1)} style={{ marginLeft: 10, padding: '6px 14px',
              borderRadius: 999, border: '1px solid var(--border)', background: 'var(--bg-tinted)',
              color: 'var(--cyan)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>Retry</button>
          </div>
        )}
        {state.status === 'ok' && (active === 'alerts' ? renderAlerts(state.data) : renderText(state.data))}
      </div>
    </div>
  );
}
```
(If `Icon.ChevronLeft` doesn't exist, substitute the icon found in Step 0 grep.)

- [ ] **Step 2: Register the script in `index.html`**

After `<script type="text/babel" src="rl-monitor.jsx"></script>` add:
```html
<script type="text/babel" src="inbox.jsx"></script>
```

- [ ] **Step 3: Add Inbox to navigation in `home.jsx`**

In `TopNav`'s `navLinks` array add (after the Portfolio entry):
```jsx
{ screen:'inbox', label:'Inbox', icon:<Icon.Bell size={17}/> },
```
(This surfaces it in both the desktop top nav and the mobile hamburger, which map the same array.)

- [ ] **Step 4: Manual smoke**

With the local server up: log in → open `http://127.0.0.1:8123/#/inbox/alerts` in a new tab → Expected: Inbox screen, Alerts tab active, either alert rows or the empty state — never a blank page. Switch tabs; each shows content, its empty state (404), or the error card. `/#/inbox` alone lands on Brief.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/prototypes/inbox.jsx src/frontend/prototypes/index.html src/frontend/prototypes/home.jsx
git commit -m "feat(pwa): Inbox screen — notification landing with brief/digest/weekly/alerts tabs"
```

---

### Task 6: Full-suite regression + end-to-end push test

**Files:**
- No repo changes (e2e scripts live in a temp dir, not committed).

- [ ] **Step 1: Full suite — compare to Task 1 baseline**

Run: `python -m pytest tests/ -q 2>&1 | tail -5`
Expected: identical fail-set to the baseline, plus the new tests passing.

- [ ] **Step 2: e2e — real push, cold tap, warm tap (local)**

Prereqs: `pip install pywebpush` (in requirements but may be missing locally); `.env` has VAPID keys (it does); Chrome installed; `npm i playwright` in a scratch dir. Start the server with push on:
`DELIVERY_ENABLED=1 DELIVERY_PUSH_ENABLED=1 DELIVERY_EMAIL_ENABLED=0 python -m uvicorn services.api.server:app --host 127.0.0.1 --port 8123 --workers 1` (hold the 59321 singleton lock first if you want the scheduler quiet — see Task 4 Step 7).

Scratch-dir script `e2e.js` (run `node e2e.js`, then in a second terminal send the push when it prints WAITING):

```js
const { chromium } = require('playwright');
const path = require('path');
const BASE = 'http://127.0.0.1:8123';

(async () => {
  const ctx = await chromium.launchPersistentContext(path.join(__dirname, 'profile'), {
    channel: 'chrome', headless: false, viewport: { width: 420, height: 860 },
  });
  await ctx.grantPermissions(['notifications'], { origin: BASE });
  const page = await ctx.newPage();
  await page.goto(BASE + '/', { waitUntil: 'load' });
  await page.evaluate(() => navigator.serviceWorker.ready);
  console.log('subscribe:', await page.evaluate(() => window.saPush.enable()));
  // Simulate a remembered session so cold opens skip login:
  await page.evaluate(() => localStorage.setItem('sa_remembered', '1'));

  console.log('WAITING for push — now run the python send in the other terminal');
  const notif = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.ready;
    for (let i = 0; i < 90; i++) {
      const ns = await reg.getNotifications();
      if (ns.length) return { title: ns[0].title, data: ns[0].data };
      await new Promise(r => setTimeout(r, 1000));
    }
    return null;
  });
  console.log('notification:', JSON.stringify(notif));
  if (!notif || notif.data.url !== '/#/inbox/brief') { console.log('FAIL: wrong data.url'); process.exit(1); }

  // COLD tap: fresh tab at the payload url must render the Inbox, not login/blank.
  const cold = await ctx.newPage();
  await cold.goto(BASE + '/' + notif.data.url.replace(/^\//, ''), { waitUntil: 'load' });
  await cold.waitForTimeout(6000);
  const coldText = await cold.evaluate(() => document.body.innerText);
  console.log(coldText.includes('Inbox') && !coldText.includes('Welcome back')
    ? 'COLD PASS' : 'COLD FAIL:\n' + coldText.slice(0, 200));

  // WARM tap: SW posts sa-open to the already-open first page.
  const sw = ctx.serviceWorkers().find(w => w.url().includes('sw.js'));
  await sw.evaluate(async () => {
    const cs = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    cs.forEach(c => c.postMessage({ type: 'sa-open', url: '/#/inbox/alerts' }));
  });
  await page.waitForTimeout(3000);
  const warmText = await page.evaluate(() => document.body.innerText);
  console.log(warmText.includes('Inbox') ? 'WARM PASS' : 'WARM FAIL:\n' + warmText.slice(0, 200));
  await ctx.close();
})();
```

Python send (second terminal, from repo root — mirrors prod brief delivery):

```python
import os, sys
os.environ.update(DELIVERY_ENABLED="1", DELIVERY_PUSH_ENABLED="1", DELIVERY_EMAIL_ENABLED="0")
sys.path.insert(0, "."); sys.path.insert(0, "src")
from core.delivery.channels import send_push
print("sent:", send_push("Morning brief — test", "e2e body", url="/#/inbox/brief"))
```
Expected: `sent: 1`, then the node script prints `notification: {... "url":"/#/inbox/brief"}`, `COLD PASS`, `WARM PASS`.
Afterwards delete the test subscription the browser stored: `rm data/delivery/push_subscriptions.json` (it's gitignored, but it points at your test Chrome profile).

---

### Task 7: Deploy + prod verification

- [ ] **Step 1: Push (time-gated)**

Check the clock. **If 16:25–17:15 IST on a trading day, wait.** Then:
```bash
git push origin main
```

- [ ] **Step 2: Verify prod picked it up**

```bash
curl -s https://stockagent-ai.up.railway.app/sw.js | grep "const VERSION"   # expect v6
curl -s "https://stockagent-ai.up.railway.app/delivery/brief/latest?format=text" | head -c 200
```
Expected: `const VERSION = 'v6';` and a `{"date": ..., "text": "Morning brief — ..."}` payload (or a 404 detail if no brief yet — both prove the route).

- [ ] **Step 3: Phone check (the real acceptance test)**

1. Open the app once normally (fetches SW v6).
2. Log in with **Remember me** checked; confirm Notifications = On in the hamburger → Preferences.
3. Next scheduled notification (morning brief 08:50 IST weekdays, or trigger one: `curl -X POST https://stockagent-ai.up.railway.app/delivery/run-brief -H "X-Scheduler-Key: <key>"`): tap it.
Expected: app opens **directly on the Inbox brief tab showing the brief text** — no login, no blank, no bare home screen.

---

## Self-review notes (already applied)

- Spec coverage: senders (T1), text endpoints (T2), SW warm/cold (T3), routing+session (T4), Inbox UI (T5), tests/e2e (T1/T2/T6), deploy (T7). Out-of-scope items (per-ticker alert links, real auth, email deep-links) intentionally absent.
- Type consistency: message type `sa-open`, storage key `sa_remembered`, hash grammar, and `{date, text}` response shape are identical across Tasks 2–6.
- Known judgment points for the implementer: exact icon name in inbox.jsx (grep first); which test file owns the digest-route test; the alerts-module import alias in its test file. Each has an explicit grep instruction where it arises.
