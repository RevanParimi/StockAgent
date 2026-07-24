# Notification Deep-Links — Design (2026-07-24)

## Problem

Push notifications work (sw.js v5), but every tap lands on `/`, which cold-starts
the app at the cosmetic login screen. The tap carries no meaning: the user asked
"what is the purpose of the notification if it just opens the home screen?"

Facts driving the design:

- All senders call `deliver()` **without** `url` → payload url is `"/"`.
- The prototype does **no URL routing** (screen state is `useState('auth')` in
  `index.html`); "Remember me" is an unwired checkbox — every cold start shows
  the auth screen.
- The SW `notificationclick` warm branch focuses an existing window without
  navigating; the cold branch calls `openWindow(payload.url)`.
- All notification content is already retrievable:
  `/delivery/brief/latest`, `/delivery/weekly/latest`,
  `/portfolio/digest/latest`, `/delivery/alerts?limit=N`.
- No frontend view renders any of that content today.

## Decision (Approach A — approved by user 2026-07-24)

Hash deep-links + a new in-app **Inbox** screen. All four notification types
get a destination. Remembered sessions skip login. User delegated detail
decisions ("ask only if critical").

## Design

### 1. Payload URLs (backend, no schema change)

`deliver()`/`send_push()` already accept `url`. Each sender passes its
destination:

| Sender | File | url |
|---|---|---|
| Morning brief | `core/delivery/brief.py` | `/#/inbox/brief` |
| Weekly review | `core/delivery/weekly.py` | `/#/inbox/weekly` |
| EOD digest | `core/portfolio/pipeline.py` | `/#/inbox/digest` |
| Alerts | `core/delivery/alerts.py` | `/#/inbox/alerts` |

Email is untouched (it already appends the app-link footer). Hash URLs need no
server routes, are invisible to the SPA catch-all's API-namespace guard, and
don't perturb SW caching (same `/index.html` shell).

### 2. Service worker (v6)

`notificationclick`:
- **Cold** (no window): `openWindow(data.url)` — unchanged.
- **Warm** (window exists): `focus()` **and** `postMessage({type:'sa-open', url})`
  to that client, fixing the focus-without-navigate gap.

### 3. Frontend routing + auth memory (`index.html`)

- Boot: parse `location.hash`; `#/inbox/<tab>` → deep-link target
  `{screen:'inbox', tab}`. Unknown hash → home. Consume (clear) the hash after
  reading so refresh doesn't re-trigger.
- SW message listener: `sa-open` → dispatch a `sa-nav` CustomEvent; the App
  component listens and `setScreen`s accordingly (works while app is open).
- Auth memory: `localStorage['sa_remembered']`. AuthScreen sets it on login
  when "Remember me" is checked (now wired); Sign out clears it. Initial
  screen: remembered → deep-link target or home; not remembered → auth, and
  after login continue to the deep-link target instead of home.

### 4. New Inbox screen (`src/frontend/prototypes/inbox.jsx`)

One component, four tabs — Brief / Digest / Weekly / Alerts — opened on the
tab named by the deep link (default Brief):

- Fetches its tab's endpoint lazily; 404 → friendly empty state ("No digest
  yet — runs after 16:30 on trading days").
- Renders the JSON generically: date/title header + sections as styled text
  cards using the app's CSS vars (no bespoke per-field layout; content shape
  may evolve).
- Reachable without a notification: nav chip "Inbox" + hamburger entry.
- Registered in `index.html` (script tag, screen branch) and added to the SW
  SHELL list.

### 5. Error handling

- Cache/network failures already degrade (sw.js v5 semantics preserved).
- Inbox fetch failure → inline error state with retry, never a blank screen.
- Malformed/legacy payloads (`url:"/"`) behave exactly as today.

### 6. Testing

- **Python**: per-sender unit tests assert the `url` passed to `deliver`
  (monkeypatch capture), added next to each sender's existing test file.
  Suite fail-set must stay identical to baseline.
- **E2E (local, Playwright + real FCM push)**: reuse the 2026-07-24 harness —
  send a real push, assert `data.url == '/#/inbox/brief'`, cold-open the URL,
  assert the Inbox brief tab renders content (not login, not blank). Warm
  case: postMessage navigation switches an open app to Inbox.
- Deploy: bump SW `VERSION` to v6; verify prod serves v6 after push.
  **No push to main 16:25–17:15 IST (trading day).**

## Out of scope

- Per-ticker alert detail routing (alerts land on the Alerts tab tail; a
  future iteration can link each alert row to its ticker).
- Real authentication (login stays cosmetic; "remembered" is a UX flag only).
- Email deep-links beyond the existing footer link.
