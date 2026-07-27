# Trade Transparency + Profit Protection + Global-Stress Regime — Design

**Date:** 2026-07-27
**Status:** Approved by user (scope: all three pieces)

## Problem

1. **Display gap.** Every autopilot trade already lands in the append-only
   transactions ledger with timestamp, price, realized P&L, verdict, trigger
   codes, and a link to the advice record whose LLM narrative explains the
   decision — but the UI activity card shows only date, price, verdict code,
   and realized ₹. Users cannot see the trade *time*, the *buy price* behind a
   sell, the *P&L %*, or the *written reason* for any buy/sell.
2. **Profit round-trip.** The advisor's stop is measured against entry cost
   (`unrealised_pnl_pct <= -atr_stop_pct`). A position up 40% that slides back
   to 0% never breaches its stop; profit-taking (TRIM) only fires at
   `advisor.trim_profit_pct` (+25%) AND weakening signals. There is no
   mechanism that books profit when a winner starts giving gains back.
3. **Narrow world-event funnel.** Geopolitical/commodity shocks (war, crude)
   reach decisions only via India VIX, Nifty 5-day momentum, or overnight
   headlines (pre-open shock check). There is no direct crude-oil, USD/INR, or
   global-index input to the regime detector.

Explicit non-goals (decided during brainstorm):
- No geopolitics news-watching agent / continuous monitoring (cost, noise; the
  08:45 IST pre-open check already covers the overnight window).
- No LLM-in-the-decision-seat change — the shadow-lane experiment (ripe
  ~2026-07-31) is the evidence-based path for that.
- No feature deletions — Wave E already executed the deletion docket; the gap
  here is an unfinished loop, not bloat.

## Piece A — Trade transparency (record → display)

### Schema (additive, back-compatible)

`TransactionRecord` (src/backend/shared/schemas/portfolio.py) gains:

| field        | type            | meaning                                             |
|--------------|-----------------|-----------------------------------------------------|
| `cost_basis` | `float \| None` | SELL only: holding's `adj_avg_price` at the moment of sale; `None` on buys |
| `pnl_pct`    | `float \| None` | SELL only: realized P&L % vs `cost_basis`           |
| `reason`     | `str` (default `""`) | `AdviceRecord.narrative` copied at execution time (buys and sells) |

- Defaults keep every existing JSONL row parseable. The ledger stays
  append-only: **no backfill mutation of historical rows.**
- `_txn()` in core/portfolio/autopilot.py fills the fields. `Holding.sell()`
  does not mutate `adj_avg_price`, so capture order is not fragile, but
  `cost_basis` is still read **before** `h.sell()` for clarity. The narrative
  is generated at pipeline Step 3 (before execution, pipeline.py:101), so no
  ordering change and **no new LLM calls**. Seed/manual txns keep `reason=""`.

### API / digest

- `/portfolio/transactions` serializes the new fields automatically (pydantic).
- `build_digest()` already embeds `t.model_dump()` for trades — digest and
  email brief inherit the fields with no digest-side change. If the brief's
  trade-line formatter selects fields explicitly, extend it to include reason
  and buy→sell prices on sell lines.

### UI (src/frontend/prototypes/portfolio.jsx, LiveActivityCard/ActivityCard)

- Each trade row shows **IST time** (converted from stored UTC `ts`;
  historical rows without a meaningful time still show the date).
- SELL rows: `qty @ ₹<sell price> (bought @ ₹<buy price>)` + realized ₹ and
  P&L %. When `cost_basis` is absent (historical rows), derive
  `≈ price − realized_pnl/qty` and prefix "≈" (dividend-inclusive realized
  makes it approximate).
- BUY rows: `qty @ ₹<price>` as today.
- The `reason` sentence renders beneath the row, collapsed/expandable so the
  card stays clean; trigger codes remain in the sub-line as today.

## Piece B — Trailing profit-protection stop

### Signal

`AdvisorSignals` gains `peak_close_since_entry: float | None` (and derived
`drawdown_from_peak_pct`). Computed in `build_signals()` from the 1-year OHLCV
DataFrame already fetched per holding: max close between `holding.buy_date`
and `review_date`. No new data calls. Missing/short OHLCV (or holding older
than the 1-year window with no in-window peak above close) → `None` → rule
silently inactive (conservative, matches every other non-fatal signal read).

### Rule (advisor.decide, EXIT block)

Armed only once the position has been meaningfully in profit:

```
if peak_close_since_entry is not None
   and peak_pnl_pct >= settings.ADVISOR_TRAIL_ARM_PCT          # arm gate
   and drawdown_from_peak_pct >= signals.atr_stop_pct:          # giveback gate
    triggers.append("trailing_stop_breach")                     # EXIT-class
```

where `peak_pnl_pct` is the peak close vs `adj_avg_price` and
`drawdown_from_peak_pct = (peak − close) / peak × 100`.

- Reusing the existing ATR-scaled stop distance as the giveback keeps the
  trail volatility-scaled — choppy stocks get proportionally more room; no new
  magic distance number.
- EXIT-class (full exit): profit protection is the same class as
  `stop_breach`. Existing precedence holds — EXIT > TRIM > ADD > HOLD, and
  LTCG softening never suppresses an EXIT.
- Config: `advisor.trail_arm_pct` via `cfg()` (fallback 10.0). Setting it to a
  very large value neutralizes the rule without a deploy.
- Narrator map gains a human template for `trailing_stop_breach` (e.g. "the
  position gave back its volatility budget from the peak, booking profit").

## Piece C — Global-stress escalation in the regime detector

### New signals (core/intelligence/regime/detector.py)

Three additional yfinance reads, each fallback-safe to neutral exactly like
`_get_vix`:

| signal            | ticker  | stress condition (config, fallbacks shown)         |
|-------------------|---------|----------------------------------------------------|
| Brent crude 5d %  | `BZ=F`  | `regime.brent_shock_pct` ≥ +8.0 (oil shock — India imports) |
| USD/INR 5d %      | `INR=X` | `regime.usdinr_stress_pct` ≥ +1.5 (rupee stress)   |
| S&P 500 last move | `^GSPC` | `regime.spx_drop_pct` ≤ −2.0 (global risk-off)     |

`RegimeSnapshot` gains the raw values as optional fields (back-compatible) and
the narrative string mentions any stress signals that fired.

### Integration — escalation notch, not a rewrite

1. Existing classification (`_classify`) runs unchanged.
2. Count breached global-stress signals. If **≥ 2** fired, escalate the label
   one severity notch: NORMAL/RISK_ON/MOMENTUM_EXTENDED/OVERSOLD → RISK_OFF;
   RISK_OFF → MACRO_CRISIS; MACRO_CRISIS stays. 0–1 signals → no change.
3. The escalated label feeds the existing sticky-regime state machine
   (state.py), which already handles severity ordering and slow de-escalation
   — no changes there.

Effect: a crude/war shock can block new buying and arm the
`crisis_regime_bearish` EXIT path a day before India VIX fully reacts. A
single noisy signal never escalates on its own. Fetch failures degrade to
today's behavior exactly.

## Error handling

Every new read follows the codebase's non-fatal pattern: try/except →
`logger.warning` → conservative default (rule inactive / signal neutral / field
None). No new failure can break the pipeline, digest, or UI render (UI guards
on field presence).

## Testing

TDD (test-first) per repo standard:

- **Schema:** old JSONL transaction rows (without new fields) still parse;
  new rows round-trip.
- **Autopilot:** `_txn` fills `cost_basis`/`pnl_pct`/`reason` on sells and
  `reason` on buys (autopilot + switch-buy paths).
- **Trailing stop matrix:** below arm gate → no trigger; armed + giveback <
  ATR stop → no trigger; armed + giveback ≥ ATR stop → EXIT with
  `trailing_stop_breach`; missing OHLCV → inactive; interaction with LTCG
  (EXIT never softened).
- **Regime escalation matrix:** 0/1/2/3 stress signals × each base label;
  fetch-failure fallback = neutral; sticky-state interaction unchanged.
- **Suite discipline:** full-suite A/B — fail-set must be byte-identical to
  the known-red baseline. Frontend: transpile check (browser smoke by user,
  per repo pattern).

## Rollout

- No feature flags needed: A is additive; B and C are config-neutralizable
  (`advisor.trail_arm_pct` huge / stress thresholds huge) without a deploy.
- Push outside the deploy-kill window (never 16:25–17:15 IST on trading days).
- **Expected first-run behavior:** the trailing stop may legitimately fire
  EXITs on positions already far off their peaks — that is the feature
  working, but worth watching on the first 16:30 IST run after deploy.
- Watch items: first post-deploy digest shows reasons on trade lines; UI card
  renders IST time + buy price; regime narrative logs the three new raw
  signals.
