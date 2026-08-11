# PI "Prospect" — IPO Intelligence

**Date:** 2026-08-11
**Status:** design approved, implementation plan not yet written
**Codename:** Prospect (house style: Compass, Atlas, Lighthouse)

---

## 1. Why this exists

The IPO feature shipped with Compass Phase C is a stub that **could never have
worked**. Four independent defects, all confirmed by reading the code and the
on-disk cache:

| # | Defect | Evidence |
|---|--------|----------|
| 1 | **Subscription × is never populated.** The fetcher resolves `qibSubscriptionTimes` / `retailSubscriptionTimes` / `noOfTimesSubscribed`, but NSE's `/api/ipo-current-issue` and `/all-upcoming-issues?category=ipo` carry **no bid data at all**. The `nse` pkg wraps only three IPO endpoints, none of them bid details. | `services/data/fetchers/ipo.py:33-35`; every row in `data/market_cache/ipo.json` has `qib_x: null, retail_x: null, total_x: null` |
| 2 | **The issue window is never parsed.** `_LISTING_DATE_KEYS` looks for `listingDate`, but the current/upcoming feeds carry `issueStartDate` / `issueEndDate`. Nothing in the system knows when an issue opens or closes. | `services/data/fetchers/ipo.py:31`; `listing_date: ""` on every current/upcoming row |
| 3 | **The cache refreshes weekly.** `refresh_ipo_cache()` is called only from `run_discovery_cycle()` — the Saturday job. An issue that opens Monday and closes Wednesday is stale for a week or missed outright. | `core/discovery/__init__.py:57`; local cache stamped `2026-07-11` |
| 4 | **The weekly digest has no IPO section.** | `core/delivery/weekly.py` contains no IPO reference |

Consequences the user sees: `_ipo_lean()` returns `"data pending"` **100% of the
time** (`core/delivery/brief.py:234-248` — it has never once produced a real
lean), and closed issues keep rendering under the heading `IPOs OPEN NOW`
(`core/delivery/brief.py:679`) because state 2 is unknowable.

Fixing the plumbing is necessary but not sufficient. The user's actual ask is a
**model of how newly-listed stocks behave**, which no part of this codebase can
express today.

## 2. Decisions taken

| Decision | Choice | Consequence |
|---|---|---|
| Universe | **NSE mainboard only** | SME stays excluded (`DISCOVERY_INCLUDE_SME=false`). Global/unlisted (the SpaceX case) is **out of scope** — no NSE tape, no structured source. |
| GMP | **Yes, via Serper search extraction** | Stored with source + timestamp, always rendered as *unofficial grey-market chatter*. No aggregator HTML scraping. |
| Verdicts | **Both horizons, separately labelled** | SHORT (listing → T+5) and LONG (T+180/T+365) never collapse into one score. |
| Proof gate | **Backfill first, ship visible after** | P0 (pure bugfix) ships immediately; scored verdicts run dark until the P1 backtest produces a measured hit-rate. |

P4 (convergence tracker) **stays inside this PI** — approved 2026-08-11 after
being explicitly raised as a split candidate.

## 3. The thesis

An IPO is not a stock with less history. It is a **two-process instrument**:

- **At listing**, price = f(hype, demand, float scarcity). Sentiment-dominated.
  No tape exists, so every seasoned-equity signal this codebase owns —
  momentum, delivery %, RSI, regime — is *structurally unavailable*, not merely
  sparse.
- **After listing**, price converges toward f(business worth). Evidence-dominated.

The predictive content lives in **the gap between the two processes**. Hence two
indices, not one composite.

### Hype Index (H)

| Feature | Rationale |
|---|---|
| Retail subscription × | Direct froth measure |
| **Retail-to-QIB skew** (`retail_x / qib_x`) | Retail leading institutions is the classic distribution tell |
| GMP as % of issue price | Strongest short-term listing-pop signal in the Indian market |
| **GMP decay across the window** | A GMP that fades day-over-day while bids climb is the sharpest froth warning available |
| News-volume spike vs sector baseline | Brand visibility ≠ business quality |
| Issue size vs sector median | Mega consumer-brand issues are structurally hype-prone |
| **OFS share of issue** | Promoters cashing out vs fresh capital into the business — the single strongest Ola/Ather discriminator, and it is disclosed |

### Substance Index (S)

| Feature | Rationale |
|---|---|
| PAT trajectory, revenue CAGR (RHP, 3 disclosed years) | Is there a business |
| Valuation vs listed peers | Peer closes already available in `EodStore` |
| **Anchor-book quality** | Domestic MF/insurance = sticky; foreign hedge funds = flippers |
| QIB × | The only subscription figure `ipo_tracker.py`'s own research note credits as predictive |
| Parent / promoter track record | Ather ← Hero MotoCorp; Ola ← Ola Cabs' own record |
| Use of proceeds | Growth capex vs debt repayment vs pure OFS |

### Verdict grid

|  | Low Hype | High Hype |
|---|---|---|
| **High Substance** | *Quiet compounder* — dull listing, re-rates later → **Ather** | *Genuine star* — pops and holds (rare) |
| **Low Substance** | *Ignore* | *Froth* — pops, then de-rates → **Ola** |

### Three outputs

1. **SHORT** (listing day → 5 trading days): expected open strength + pop band.
   Driven by H, demand, float.
2. **LONG** (126 / 252 trading days ≈ 6 / 12 calendar months): what the business
   is worth. Driven by S, with **H − S as the de-rating force**.

> **Horizon notation.** All horizons in this spec are **trading days**, matching
> the existing `AuditOutcome.horizon_td` field. The canonical ladder is
> **1, 5, 21, 63, 126, 252** td (day, week, month, quarter, half-year, year).
> Calendar equivalents appear only as reader aids and are never authoritative.
3. **Convergence / entry window** (post-listing, 365d): Ather's 400% was never
   available at listing — it appeared months later once the froth cleared and
   attention left. Detecting *froth cleared, substance intact* is the most
   actionable output in the PI, and it runs entirely on bhavcopy already on disk.

## 4. Architecture

**Hybrid.** New top-level `core/ipo/` owns data and model; it **emits into the
existing discovery shelf and paper lane** so post-listing tracking and auditor
grading reuse prod-proven machinery.

Rejected: extending `core/discovery/` (IPO logic bleeds into the equity screen;
shelf rotation rules fight a 365-day horizon) and a standalone service
(rebuilds paper lane, auditor hook, alert plumbing for no gain).

```
core/ipo/
  calendar.py     # issue windows; states: upcoming|open|closed|listed|matured
  hype.py         # H index
  substance.py    # S index
  verdict.py      # two-horizon verdict + quadrant
  convergence.py  # 365d post-listing tracker, entry-window detection
  store.py        # ipo_history + ipo_verdicts
services/data/fetchers/
  ipo.py            # EXTENDED: window dates, bid details, anchor book
  ipo_gmp.py        # NEW: Serper-extracted GMP (low-trust, labelled)
  ipo_prospectus.py # NEW: RHP financial extraction
```

`core/discovery/ipo_tracker.py` narrows to feeding discovery candidates and
delegates scoring to `core/ipo/`. Every fetcher follows the existing
**dark-signal pattern**: a missing feature renormalizes the index, never raises,
never breaks the brief.

## 5. Phases

> **Plan scoping.** This spec covers the whole PI, but a single implementation
> plan must not. **The first implementation plan covers P0 + P1 only** — the
> bugfix and the measurement. P2-P5 depend on what P1 measures, so planning them
> now would be committing to weights and surfaces ahead of the evidence. Each
> later phase gets its own plan, written after the phase before it lands.

### P0 — Fix the plumbing *(independently shippable; ships in days)*

- **Task 1 is a spike**, not a build: confirm NSE's category-wise bid-details
  endpoint path and field names. See §7 risk 1 — this is load-bearing.
- Parse `issueStartDate` / `issueEndDate`; derive issue state.
- Fetch real subscription × from the bid-details endpoint.
- Move refresh from the weekly Saturday job to a **daily scheduler job**
  (twice-daily while a window is live), following the `add_job` /
  `CronTrigger(timezone="Asia/Kolkata")` pattern at
  `services/scheduler/python/scheduler.py:461-505`.
- Make the brief **state-aware**: "opens Tuesday" / "closes tomorrow —
  subscribed 4.2×" / "closed, lists Friday". Closed issues stop rendering under
  `IPOs OPEN NOW`.
- Add an IPO section to `core/delivery/weekly.py`.
- **Honest degradation**: day-0 with no bids reads "bidding hasn't started", not
  "data pending". `"data pending"` becomes reserved for genuine fetch failure.
- Cleanup in passing: `DISCOVERY_IPO_ENABLED` carries `env="DISCOVERY_IPO_ENABLED"`
  (`base.py:921`), violating the no-env-for-toggles rule. Drop the `env=`.

**Acceptance:** a live IPO window renders correct state and a non-null
subscription × in both daily and weekly briefs; a closed issue never appears as
open.

### P1 — Historical spine *(the reason this is evidence, not astrology)*

Backfill every mainboard IPO from 2024-05 to date using `listPastIPO` plus the
**550 bhavcopy sessions already on disk** (`2024-05-01` → `2026-07-15`).

Per issue, record pre-listing knowables (subscription ×, issue price, issue
size, OFS share) against realised curves at **1, 5, 21, 63, 126, 252 trading
days**, measured both vs issue price and vs `^NSEI`. Expect ~150-250 issues.
Zero API cost, fully offline, re-runnable.

**Deliverable:** a report answering *what actually predicted what in this
market* — not a model, a measurement.

> **Load-bearing honesty constraint.** GMP archives and RHP PDFs are **not**
> retrievable retroactively at scale. P1 can therefore calibrate only the
> subscription / size / OFS skeleton. GMP and RHP-financial weights must be
> validated **forward** from launch. This is stated here so it cannot surface as
> a surprise in month three.

### P2 — Feature layer

GMP via Serper (~2,300 calls/mo headroom against the 2500 cap — the counter at
`services/data/stores/api_usage.py` already self-checks at boot), anchor book,
OFS share, RHP extraction, news-volume hype proxy. Each an independent fetcher
with its own tests and its own dark-signal fallback.

### P3 — The model

`hype.py`, `substance.py`, `verdict.py`. Two-horizon verdicts plus quadrant.
**All weights via `cfg()`/`config.yaml`, no `env=`** (config-over-hardcode and
no-env-for-toggles rules). Runs **dark**: writes to the verdict store, surfaces
nothing.

### P4 — Convergence tracker

365-day post-listing lifecycle per listing. Detects froth-cleared /
substance-intact entry windows and emits alerts through the existing
`AlertEvent` path. Absorbs the post-listing half of `ipo_tracker.py`.

### P5 — Surface + proof

Brief, weekly, chat, app rendering. **The dark→visible flip is a
`config.yaml` edit backed by a measured P1 hit-rate**, mirroring the
`hard_bind_verdict_enabled` precedent.

**Auditor integration — schema tension, resolved here.** `AuditOutcome`
(`src/backend/shared/schemas/audit.py`) declares `Lane = Literal["advice",
"alert", "shelf"]` and an `entry_close` that assumes a market close. An IPO's
entry is the **issue price**, not a close. Resolution:

- extend `Lane` with `"ipo"`;
- for IPO rows, `entry_close` carries the **issue price** and the field's
  meaning is documented at the schema, not silently overloaded;
- horizons reuse the existing `horizon_td` integer with IPO-specific values
  **1, 5, 21, 63, 126, 252** (day, week, month, quarter, half-year, year);
- benchmark fields work unchanged: `^NSEI` at listing vs at horizon.

Grading stays append-only in the existing store; source ledgers are never
rewritten.

## 6. Config surface

New `ipo:` block in `config.yaml`, mirrored in `base.py` with `cfg()` and **no
`env=`**:

```yaml
ipo:
  enabled: true
  refresh_hour: 8               # daily calendar/bid refresh (IST)
  refresh_hour_live: 18         # second pass while a window is open
  verdicts_visible: false       # P5 gate — flipped only on measured evidence
  gmp_enabled: true
  gmp_max_age_hours: 24
  hype_weights: {...}           # P3
  substance_weights: {...}      # P3
  convergence_window_days: 365  # P4
```

## 7. Risks

1. **The endpoint spike is load-bearing.** If NSE exposes no accessible bid
   data, P0's subscription fix has no source and SHORT loses its strongest
   official input; fallback is GMP + news only, materially weaker. **This is why
   it is task 1.**
2. **Sample size.** ~200 issues, of which perhaps 30 are the mega-hype cases of
   interest. Report confidence intervals and resist over-reading — precedent:
   the verification layer's 35.8% / Wilson [27.4%, 45.1%] episode, where ~90%
   window overlap made the interval far too narrow.
3. **Regulatory framing.** IPO calls are the most advice-shaped output this
   system can emit. Everything stays in the established *research view, not
   advice* frame; GMP is always labelled unofficial.
4. **Scope.** Largest PI since Compass. P0 is independently valuable and should
   ship regardless of whether P1-P5 proceed.
5. **Survivorship in the backfill.** Issues that listed and were later delisted
   or suspended must be retained, or the historical spine will overstate
   outcomes.

## 8. Non-goals

- SME issues, global markets, unlisted/pre-IPO valuation tracking (SpaceX class).
- Any allotment, application, or brokerage-integration functionality.
- Replacing `ipo_tracker.py`'s discovery-candidate role.
- Intraday listing-day price prediction.

## 9. Milestones to register

Added to `config/milestones.yaml` **in the same commit as the work that creates
them**, per the watchdog rule. Deadlines are the **last** day of the final
window.

| id | kind | fires when |
|---|---|---|
| `ipo_p0_live_window_check` | milestone | First live IPO window after P0 deploy — confirm real subscription × and correct state in the brief |
| `ipo_p1_backtest_review` | milestone | P1 backfill report ready for judgement |
| `ipo_verdicts_visible_gate` | milestone | Decide the dark→visible flip on measured evidence |
| `ipo_cache_fresh` | invariant | `ipo.json` older than 48h while `ipo.enabled` ⇒ the daily refresh job is dead |

## 10. Open questions

None blocking. Weight values for H and S are deliberately deferred to P3, where
the P1 measurement informs them — setting them now would be inventing numbers
ahead of the evidence.
