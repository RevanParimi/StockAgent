# In-App Brief Rendering, Responsive Fixes & Settings — Design

**Date:** 2026-07-31
**Status:** Approved (design), pending implementation plan
**Scope:** `src/frontend/prototypes/`, plus a small response-enrichment in `services/api/routes/delivery_api.py`

---

## 1. Problem

Three separate problems, one surface.

**1.1 The app shows the old ASCII brief.** The email brief was redesigned across Waves 1–3
(sectioned plain-English → per-idea reasons → styled HTML, `render_brief_html()` at
`core/delivery/brief.py:702`). The app never followed. `InboxPage` fetches
`?format=text` and splits the string on newlines, rendering each line as a flat row
(`src/frontend/prototypes/inbox.jsx:47-61`). The `═══` bars, `•` bullets and indented
`Why it matters:` lines — all artifacts of a fixed-width text renderer — land verbatim
in the UI.

**1.2 Several pages don't fit a phone.** Audit in §4. Root cause is that `TopNav`, which
owns *both* the mobile bottom nav and the hamburger, is rendered by only 5 of 9 screens.

**1.3 Settings barely exists.** The hamburger's "Preferences" section contains exactly one
control — a notifications toggle (`home.jsx:257`). Theme and density live in `TweaksPanel`,
which is **prototyping scaffolding**, not a product surface: it implements an
`__activate_edit_mode` host protocol (`tweaks-panel.jsx:1-40`). Consequence: no real user
can reach dark mode. Meanwhile three finished endpoints have no UI at all.

---

## 2. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Render natively from the structured JSON, not from text or embedded email HTML | The structured dict is already served; email table-HTML ignores app theme and isn't interactive |
| D2 | Brief layout = **priority feed** | An app is opened to answer "is there anything I need to do?"; sectioned/email-mirror layouts bury that below the fold |
| D3 | Wide tables = **priority columns + tap to expand** | Horizontal scroll hides `Hit`/`Miss Type` — the two columns actually scanned |
| D4 | "Needs attention" rows tap through to the holding in Portfolio | The one place the app can beat the email |
| D5 | Digest and Weekly reuse the Brief's pattern | Consistency; they have no redesigned email counterpart to mirror |
| D6 | Settings prefs persist in **localStorage** for now | Zero backend; avoids a new table colliding with the Atlas cutover (Aug 1–2) |
| D7 | Plain-English mapping stays server-side, exposed via response enrichment | `_VERDICT_PLAIN`/`_REGIME_PLAIN` get tuned; a JS copy would drift |
| D8 | Verification is fixture-driven, never live | Protects the Serper counter during the F1 blind-rate validation window |

**Explicitly deferred** (not in scope, recorded so they aren't lost):
per-kind notification toggles (need server-side prefs the scheduler can read),
brief history, data export, change-password.

---

## 3. Phase 1 — Native Inbox rendering

### 3.1 Data source

`GET /delivery/brief/latest` **without** `format=text` already returns the full dict
(`delivery_api.py:41`). Shape, from `build_morning_brief()` (`brief.py:525-593`):

| Key | Shape | Notes |
|---|---|---|
| `headline` | `str` | LLM-narrated summary |
| `portfolio` | `{portfolio_value, total_pnl_pct, escalations, …}` | plus `_portfolio_extras()`: `holdings_count`, `best`, `worst`, `all_below_cost`, `last_exit` — **every key optional** |
| `advisor_flags` | `[{symbol, verdict, reason, notes}]` | non-HOLD/NO_DATA holdings only |
| `regime` | `{label}` or `null` | |
| `overnight` | `[{headline, note}]` | `note` = "why it matters" |
| `earnings_soon` | `[{symbol, date, watch}]` | |
| `discovery_adds` | `[{symbol, verdict, conviction, reason}]` | cap at `DELIVERY_BRIEF_MAX_IDEAS` |
| `ipo_watch` | `[{symbol, company, …}]` | lean/demand derived |
| `lockin_flags` | `[{symbol, kind, expiry}]` | |

Sibling endpoints behave the same way: `/portfolio/digest/latest` and
`/delivery/weekly/latest`.

### 3.2 Backend change (D7)

`_VERDICT_PLAIN` (`brief.py:44`) maps `EXIT→"Consider exiting"`, `TRIM→"Trim back"`,
`ADD→"Add more"`, `HOLD→"Hold"`, `SWITCH→"Switch"`, `WAIT_FOR_LTCG→"Hold for tax"`.
`_REGIME_PLAIN` (`brief.py:34`) maps `RISK_OFF→("Cautious", gloss)` and five others.

Enrich the **response only** in `brief_latest()` — stored brief dicts stay byte-identical,
so nothing downstream (RL grading, replay, the email path) is affected:

- each `advisor_flags[i]` gains `verdict_plain`
- `regime` gains `label_plain` and `gloss`

Unknown enum values fall through to the raw string, exactly as the text renderer does.

### 3.3 Components

Split `inbox.jsx` (currently one 123-line file doing fetch + three render modes) into:

```
inbox.jsx          tab shell, fetch, loading/empty/error states
brief-view.jsx     BriefView + Section + FoldSection + AttentionRow
digest-view.jsx    DigestView
weekly-view.jsx    WeeklyView
```

New files must be registered as `<script type="text/babel">` tags in `index.html`
(load order matters — they must precede `inbox.jsx`).

**Layout (D2)** — open by default:
1. Hero: date, headline, portfolio value + P&L
2. `Needs attention` — amber left-accent, count in the label, one row per flag

Folded, showing a count/summary in the collapsed header:
3. Overnight news · 4. Earnings this week · 5. Ideas being researched ·
6. Market conditions (collapsed value = the plain regime word) · 7. IPOs open now ·
8. Lock-in expiries

Footer: *"Research tool — information only, never advice."*

**Every section auto-hides when empty**, matching `render_brief_text()` behaviour.
A brief with no flags, no overnight items and no ideas renders as hero + footer.

### 3.4 Edge cases the fixture must cover

- `portfolio: null` (no digest yet) → hero shows date + headline only
- `regime: null` → section absent
- `conviction` missing on an idea → verdict chip with no percentage
- 8+ overnight items → collapsed count reads "8", expanded list scrolls
- 200-char headline → wraps, no clipping
- unknown verdict enum → raw string shown, no crash
- all sections empty → hero + footer only

---

## 4. Phase 2 — Responsive

### 4.1 Audit

| # | Page | Problem | Sev |
|---|---|---|---|
| 1 | analytics, logs, prompt-lab, inbox | No `TopNav` → no bottom nav, no hamburger; `.proto-nav` is `display:none` under 768px (`styles.css:296`) | High |
| 2 | rl-monitor | Weights grid `180px 1fr 60px 70px 60px` + `gap:16` + `padding:10px 20px` = **474px hard min**, no scroll wrapper (`rl-monitor.jsx:627`) | High |
| 3 | analytics | Inline `gridTemplateColumns:'1fr 1fr'` — CSS vars can't reach it (`analytics.jsx:472`) | High |
| 4 | logs | Fixed `width:140`/`width:180` inputs in a flex row (`logs.jsx:143`, `logs.jsx:354`) | Med |
| 5 | analytics | Two `<table>`s with no scroll wrapper (`analytics.jsx:530`, `analytics.jsx:676`) | Med |
| 6 | rl-monitor | Daily log = 9 columns at `minWidth:820`; shows 5 at 360px (`rl-monitor.jsx:252,262`) | Med |
| 7 | learn | Drawer is inline `width:560` and does **not** use `.drawer-panel`, so it misses the bottom-sheet override (`learn.jsx:235`) | Med |
| 8 | inbox | Tab row = 4 equal flex buttons; won't take a 5th | Low |
| 9 | *all* | **0 of 15 `.jsx` files use `matchMedia`** — inline-styled components structurally cannot respond to width. The one width-aware component reads `window.innerWidth` imperatively at render with no resize listener (`analytics.jsx:480`), so its chart keeps portrait width after a rotate | Arch |

Note: #6's table *is* already inside an `overflowX:'auto'` wrapper (`rl-monitor.jsx:260`) —
it is cramped, not broken. #2 is the genuine overflow.

### 4.2 Fixes

- **#1 (root cause):** make `TopNav` universal. Render it in `analytics.jsx`, `logs.jsx`,
  `prompt-lab.jsx` and `inbox.jsx`, replacing their bare back-chevron headers. This is the
  single change that fixes "a few pages aren't compatible for phone".
- **#9 (architecture):** add a `useIsMobile()` hook (`matchMedia('(max-width: 767px)')`,
  with listener + cleanup) to `data.jsx` or a new `hooks.jsx`. Components branch on it
  directly instead of accreting more `!important` overrides — `styles.css` is already
  ~200 lines of those.
- **#2:** stack name-above-bar under 768px; desktop grid unchanged.
- **#6 (D3):** under 768px render Date / Error % / Hit only; tapping a row expands an
  inline panel with Predicted, Actual, both directions, Miss Type, Confidence.
- **#3, #4, #5, #7:** collapse to one column / allow flex shrink / add scroll wrappers /
  adopt the `.drawer-panel` class.

### 4.3 Mobile-hidden affordances

`nav-desktop` hides the search box (`home.jsx:316`), notification bell (`home.jsx:350`)
and account avatar (`home.jsx:354`) below 768px. Phone users therefore have **no search
and no account affordance**. Search moves into the mobile menu; the avatar becomes the
Settings entry point (§5).

---

## 5. Phase 3 — Settings

New `settings.jsx`, reached from the hamburger and (on mobile) the avatar.

**Ships in this phase:**

| Group | Item | Backing |
|---|---|---|
| Account | identity display | `GET /auth/me` |
| Account | **Invite a friend** | `POST/GET /auth/invites` (`auth_api.py:93,100`) — built, owner-only, **no UI today** |
| Notifications | push on/off | existing `window.saPush` |
| Appearance | Theme light/dark | moved out of `TweaksPanel` |
| Brief | sections shown — user may hide sections they don't care about; independent of the auto-hide-when-empty rule in §3.3, which always applies first | localStorage |
| Privacy | **Delete my account** | `DELETE /auth/account` (`auth_api.py:107`) — full DPDP cascade, **no UI today** |
| About | version, research-tool disclaimer | static |

**Density is removed, not migrated.** It has zero references outside `tweaks-panel.jsx` —
a control wired to nothing.

`TweaksPanel` stays as a dev tool; theme/density entries are dropped from it.

Destructive actions (delete account) require typed confirmation.

**Prioritised backlog** (agreed, not built here): per-kind notification toggles ·
brief history (`save_brief()` writes per-date files but only `load_latest_brief()` exists,
`store.py:364,369`) · "last updated" + pull-to-refresh · data export · change password.

---

## 6. Verification

The frontend has **no test infrastructure** — JSX is Babel-transpiled in the browser and
there are no JS tests. The Python suite (baseline 2379P/0F/0E) is a regression guard here,
not a validator: Phases 2 and 3 are frontend-only, and Phase 1's sole backend change is
response enrichment.

1. **Fixtures.** `brief.fixture.json` + digest/weekly equivalents covering §3.4. Served by
   a local shim. **No LLM or Serper call is made** (D8 — the F1 blind-rate validation is
   counting Serper calls, and the F4 counter is at 2/2500).
2. **Overflow assertion.** Playwright (1.62, already available via `npx`) walks all 10
   screens at 360 / 390 / 768 / 1280 asserting
   `document.documentElement.scrollWidth <= window.innerWidth`. This mechanically catches
   audit items #2, #3, #4, #5, #7 and guards against the next fixed-width regression.
3. **Screenshots.** Same matrix, before/after, for human review.
4. **Python suite** must stay at 0F/0E.
5. New unit test for §3.2 enrichment: `verdict_plain` present and correct, unknown enum
   falls through to raw.

---

## 7. Sequencing and risk

**Phase 1 → Phase 3 → Phase 2.** Phase 2 edits the shared nav shell, which is the highest
blast radius; Phases 1 and 3 are additive.

Two calendar constraints:

- **Atlas live cutover is Aug 1–2.** Nothing here touches `atlas.db` or the ETL — D6 kept
  prefs in localStorage specifically to avoid a schema change this week — but Phase 2's
  nav edit should not land mid-cutover.
- **Never push to main 16:25–17:15 IST on trading days.** Friday Aug 1 is a trading day.

Rollback for each phase is a revert: no migrations, no flags, no stored-data changes.

---

## 8. Out of scope

Rewriting the brief's *content* or the email renderer; `src/prototypes/dist/` (the dead
React build); the C# scheduler; converting the prototype to a real bundled SPA.
