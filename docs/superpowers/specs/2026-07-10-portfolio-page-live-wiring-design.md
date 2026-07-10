# Portfolio Page Live Wiring — Design

**Date:** 2026-07-10
**Status:** Approved (core scope)
**Origin:** User saw only 5 hardcoded automobile holdings on the Portfolio page and asked why the other sectors' stocks don't appear.

## Problem

The prototype Portfolio page (`src/frontend/prototypes/portfolio.jsx`) renders entirely from
mock data — `window.PORTFOLIO` in `src/frontend/prototypes/data.jsx` (5 automobile holdings,
fake P/L, fake alerts, fake activity). It predates the multi-sector rollout and is the last
major page not hydrated from the live API: the `/ui/bootstrap` loader overrides TICKERS,
WATCHLIST, MARKET_*, CATEGORIES, etc., but never PORTFOLIO. The "Add holding" button has no
click handler.

Meanwhile the real portfolio backend (Compass Phases A–C) already exists:

- `GET /portfolio` — holdings + watchlist, marked to market (`last_close`, `pnl_pct` per holding)
- `POST /portfolio/holdings` — add virtual buy, priced at real NSE close when `price` omitted;
  auto-promotes the symbol into the managed/RL list (origin `held`)
- `DELETE /portfolio/holdings/{symbol}` — remove + demote if not watchlisted
- `GET /portfolio/digest/latest` — EOD digest: per-holding advisor verdicts + one-line reasons,
  portfolio value, escalations (TRIM/EXIT/SWITCH)
- Auth: optional `X-Scheduler-Key`; prod currently runs open (auth-lockdown ticket deferred)

Holdings can belong to any sector (4 enabled: automobile, banking_bfsi, it_sector,
renewable_energy; registry maps ~200 tickers total).

## Scope decision

**Core live page** (user-selected): wire holdings, hero stats, add/remove, agent verdicts,
alerts panel, allocation. Sections with no backend source are hidden when live, not faked.
Deferred to a possible follow-up ("full parity"): portfolio value-history endpoint + range
chart, day-change, cash, advice-ledger-backed activity feed.

## Design

### Data flow (frontend)

On page mount, `portfolio.jsx` fetches:

1. `GET /portfolio` — holdings, watchlist
2. `GET /portfolio/digest/latest` — tolerate 404 (no advisor run yet)

Render states:

- **Loading:** brief skeleton — do NOT flash mock ₹ values and swap.
- **Live, holdings present:** real data everywhere (below).
- **Live, empty portfolio:** proper empty state with working "Add holding" CTA — never demo rows.
- **Fetch failed:** existing mock `window.PORTFOLIO` as fallback, with a visible "Demo data"
  pill (consistent with the `window.__apiLive` flag pattern).

### Section-by-section

| Section | Live source | Notes |
|---|---|---|
| Hero: Invested / Value / Total return / Holdings count | computed client-side from holdings (`adj_qty × adj_avg_price`, `adj_qty × last_close`) | holdings with null `last_close` render "—" and are excluded from totals |
| Hero: Cash tile, "+today" pill, range chart/sparkline | — | hidden when live (no backend source this pass) |
| Holdings table | `GET /portfolio` rows | any sector; columns: sym, qty, avg buy (`adj_avg_price`), current (`last_close`), value, P/L (`pnl_pct`) |
| "Agent take" column | digest per-holding verdict (HOLD/TRIM/EXIT/…) + reason; fallback: composite score/verdict joined from live `window.TICKERS`; else "—" | digest join by symbol |
| Row remove control | `DELETE /portfolio/holdings/{symbol}` | confirm before delete |
| Add holding modal | symbol autocomplete via `GET /ui/search`; qty; buy date (default today); optional price → `POST /portfolio/holdings` | blank price = real NSE close on buy date (backend already supports) |
| "What your agents are flagging" | digest escalations + per-holding reasons, TRIM/EXIT first | hidden if no digest |
| Allocation card | unchanged — already computes from holdings prop | works with real rows as-is |
| Recent activity | — | hidden when live (no transaction ledger exists) |
| Learnings | unchanged — already live via `/ui/learnings` | |

### Backend change (the only one)

`HoldingIn.sector` and `WatchlistIn.sector` become **optional** (both use the identical
pattern; one shared resolver helper). When omitted, the API resolves it server-side via
`SectorRegistry.resolve(symbol)` and then validates with the existing `is_valid_sector`.
Explicit `sector` in the body keeps working unchanged (backward compatible). No new endpoints.

Rationale: `/ui/search` returns `sym`/`name` but not sector; the registry already owns
ticker→sector mapping, so the frontend should not duplicate it.

### Error handling

- Per-holding mark-to-market failure: API already returns `last_close: null` — UI shows "—",
  excludes the row from hero totals, still shows qty/avg-buy.
- `POST /portfolio/holdings` 422 (bad symbol/date/price unavailable): surface API `detail`
  message in the modal.
- Digest 404: hide flagging panel + digest-based verdicts; fall back to `window.TICKERS` join.
- `/portfolio` fetch failure: mock fallback + "Demo data" pill.

### Testing

- **Backend (pytest):** sector-optional resolution on `POST /portfolio/holdings` — omitted
  sector resolves via registry; explicit sector still honored; unknown symbol falls back to
  registry default (`automobile`). Lives alongside existing portfolio API tests.
- **Frontend:** prototype is static JSX (no unit-test harness); verify end-to-end by running
  the app locally — empty state, add holding (multi-sector), table render, remove, demo
  fallback with API stopped.

### Out of scope

- Portfolio value-history endpoint + hero range chart (full-parity follow-up)
- Cash / day-change tiles
- Activity feed from advice ledger
- Auth lockdown (existing deferred ticket)
- React app (`src/frontend/web`) — prototype is the deployed UI
