# PI "Prospect" — IPO Intelligence

**Date:** 2026-08-11
**Status:** P0 + P1 implemented (plan `docs/superpowers/plans/2026-08-12-ipo-prospect-p0-p1.md`) and live on prod as of 2026-08-13. **P2 scoped 2026-08-13** (§5 P2) — plan pending. P3-P5 not started.
**Codename:** Prospect (house style: Compass, Atlas, Lighthouse)

---

## 1. Why this exists

The IPO feature shipped with Compass Phase C is a stub that **could never have
worked**. Four independent defects, all confirmed by reading the code and the
on-disk cache:

| # | Defect | Evidence |
|---|--------|----------|
| 1 | **Subscription × is never populated — through a key-name miss, not an absent source.** `/api/ipo-current-issue` *does* carry the total: `category: "Total"`, `noOfTime` (× subscribed), `noOfSharesOffered`, `noOfsharesBid`. The fetcher's `_TOTAL_SUB_KEYS` guesses `noOfTimesSubscribed` / `totalSubscriptionTimes` / `subscriptionTimes` — **none of which is `noOfTime`**. The QIB/retail *breakdown* genuinely does require a second endpoint. | `services/data/fetchers/ipo.py:33-35`; verified live 2026-08-11 (§11); every row in `data/market_cache/ipo.json` has `qib_x: null, retail_x: null, total_x: null` |
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
| GMP | **Yes, via Serper search extraction** — but **gated behind a dedicated key from P2 on** (§5 P2: measured Serper headroom is 80–300 calls/mo, not the 2,300 first assumed) | Stored with source + timestamp, always rendered as *unofficial grey-market chatter*. No aggregator HTML scraping. |
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
| Retail subscription × | Direct froth measure; available per-category (§11.2) |
| **Retail-to-QIB skew** (`retail_x / qib_x`) | Retail leading institutions is the classic distribution tell |
| **Cut-off bid share** (`totalBidAtCutOff / TOTAL_BIDS`) | Retail bidding at cut-off rather than a chosen price = price-insensitive demand. MOLBIO: 46% (§11.3). **Official, free, no GMP dependency.** |
| **Demand velocity across the window** | The price-level demand curve is timestamped and refreshed hourly (§11.3), so bid accumulation day-1→day-3 is directly measurable |
| GMP as % of issue price | Corroborating short-term pop signal — *demoted* from "strongest" now that official froth measures exist |
| **GMP decay across the window** | A GMP that fades while bids climb remains a sharp warning, but is now a cross-check on the official curve rather than the primary input |
| News-volume spike vs sector baseline | Brand visibility ≠ business quality |
| Issue size vs sector median | Mega consumer-brand issues are structurally hype-prone |
| **OFS share of issue** | ~~The single strongest Ola/Ather discriminator~~ — **MEASURED 2026-08-15, RE-MEASURED 2026-08-18 ON A LARGER SAMPLE; see §5 P2.** The intuition was that promoters cashing out is the bad sign. On 170 rows carrying both an OFS share and an outcome, OFS-heavy issues lead at 1/21/63td — but the 252td lead **disappeared** once the parse-failure rate was cut from 23% to 10%, leaving fresh-heavy marginally ahead over a full year. Treat as **unvalidated**: still one regime, still confounded by company maturity, and the horizon that matters most for the Ather thesis no longer supports either reading. P3 must not weight this feature. |

### Substance Index (S)

| Feature | Rationale |
|---|---|
| PAT trajectory, revenue CAGR (RHP, 3 disclosed years) | Is there a business |
| Valuation vs listed peers | Peer closes already available in `EodStore` |
| **Institutional composition** | The bid ladder breaks QIB into **FIIs / Domestic FIs / Mutual funds / Others** as separate line items (§11.2) — the sticky-vs-flipper split is directly observable, no RHP parsing required |
| QIB × | The only subscription figure `ipo_tracker.py`'s own research note credits as predictive |
| Parent / promoter track record | Ather ← Hero MotoCorp; Ola ← Ola Cabs' own record |
| **OFS vs fresh-issue split** | Present as free text in `issueInfo` (§11.2) — needs extraction, but no external source |

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

**Delivered:** commits `c74cfd7` `adebf34` `691c33b` `119f4a2` `6fce990` `1bcfb43` `51862a4` `bb71733` `474c864`.

- ~~Task 1 is a spike~~ **— done 2026-08-11, contract verified in §11.** The
  build starts from a known contract.
- **One-line win first:** add `noOfTime` to `_TOTAL_SUB_KEYS`. That alone
  populates total subscription × from the feed already being fetched, and is
  worth shipping ahead of everything else here.
- **Resolve NSE-only vs all-exchange (§7 risk 6) before wiring the breakdown.**
  Verify on a second live symbol against NSE's published end-of-day figure, then
  pin the chosen source in a docstring so a later reader cannot "simplify" it
  back to the wrong one.
- Parse `issueStartDate` / `issueEndDate`; derive issue state.
- Fetch the category breakdown (QIB / FII / DomFI / MF / NII / Retail /
  Employee / Total) from the verified authority.
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

**Delivered:** commits `be9d2fb` `bab1a7c` `9a38620` `2ec3a55` `8ab012a` `7ac2159` `b377286` `51183d8` `4d5d611`.

**Measurement:** Dataset: 206 NSE mainboard rows (2024-05 → 2026-08), 202 with a subscription figure, 188 with realised curves, **185 with both**. Listing-day return vs issue price, bucketed by total subscription: hot (≥10×) n=118 mean +26.36%, 85% positive; warm (2–10×) n=39 mean −0.46%, 46% positive; cold (<2×) n=28 mean −4.15%, 25% positive. At 252td the hot bucket is n=57 mean +30.11% — i.e. almost the entire year's return was already present on listing day. The cold bucket's 252td figure (n=8) is below the report's own n≥10 floor and is deliberately not quoted.

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

### P2 — Feature layer *("Prospect: capture")*

**Scoped 2026-08-13.** The original one-paragraph sketch (GMP via Serper, anchor
book, OFS share, RHP extraction, news-volume proxy — "each an independent
fetcher") survives in outline, but two measurements taken while scoping changed
its shape and are recorded here so the reasoning is not lost.

#### The two findings that reshaped this phase

**1. The Serper headroom figure in the original sketch was wrong by an order of
magnitude.** It claimed "~2,300 calls/mo headroom against the 2500 cap". Prod
counter read live on 2026-08-13: **924 calls on day 13 of 31**, and the event
ledger at `data/logs/api_usage_events.jsonl` shows 179 on Aug 3 → 922 on Aug 12,
a burn of **~83 calls/day**. Projected month-end **~2,200–2,420 against a 2,500
cap** ⇒ true headroom is **80–300 calls/month**. GMP + news-volume at even two
snapshots a day across ~3 concurrent issues is ~360 calls/month and would
exhaust the cap on its own, competing directly with the daily pipeline.

**2. The most valuable perishable signals are free, already fetched, and being
thrown away.** P0's `_enrich_open_issues` fetches the full bid ladder — the
QIB→FII/DomFI/MutualFund split *and* `cutoff_share` — on every open issue, and
then discards it: the row is rebuilt from `_normalise` on the next pass, and no
consumer reads `bid_ladder` at all. `cutoff_share` reaches the brief row
(`core/delivery/brief.py:492`) and is never rendered. §3 rates cut-off share and
demand velocity as *official* froth measures that explicitly **demoted GMP** to
a corroborator. So the highest-value capture costs zero API calls.

Together these invert the build order: **capture the free official signals
first; treat GMP as an optional corroborator gated behind its own key.**

#### Decisions

| Decision | Choice | Consequence |
|---|---|---|
| Build order | **Perishable-first** | Capture starts a clock that cannot be rewound — at ~5–15 mainboard issues/month, a month of delay is ~10 windows permanently absent from the forward validation set. OFS backfill is non-perishable and can happen any time, so it goes second. |
| Serper | **GMP built, gated, dark** | Reads a dedicated `SERPER_API_KEY_IPO`. Unset ⇒ returns `None`, records no call, never touches the shared quota. P2 does not stall on a billing decision. |
| Visibility | **Facts visible, scores dark** | Observed composition renders on live windows (NSE-published facts, same class as the subscription × the brief already prints). Every derived index, quadrant and verdict stays dark for P3/P5. Rationale: fully-dark capture is unobservable, so a silently-wrong ladder accumulates garbage for weeks — the exact failure mode the P1 backfill review caught once already. |
| RHP extraction | **Deferred out of P2** | Heaviest, most brittle, not backfillable, least validatable of the five. Gets its own phase or is dropped. |
| Named anchor-investor list | **Deferred out of P2** | The ladder already yields institutional *composition* free. The named anchor book is a separate disclosure and adds "who" on top of "how much". |

#### Storage — an append-only ledger, separate from the P1 spine

`data/ipo/ipo_signals.jsonl`, one row per (symbol, capture time).

Folding snapshots into `IpoRecord` was considered and **rejected**: `upsert`
rewrites the whole file per row (already the O(n²)/OneDrive-lock problem in
§9b) and **the P1 backfill replaces whole rows**, so re-running it would erase
captured signals — precisely the defect fixed in `a578ac6`. Per-symbol files
were rejected for forcing P3 to glob. Append-only means no rewrite path exists
to wipe the ledger.

As with the P1 spine: **no derived value ever enters this file.**

#### Components

1. **`core/ipo/signals.py`** — `IpoSignalSnapshot` (symbol, captured_at, state,
   `combined`, `nse_only`, `cutoff_share`, `gmp`, `news_volume`) and
   `IpoSignalStore`: append-only JSONL, corrupt-line tolerant like
   `IpoHistoryStore.load_all`, deduped on (symbol, capture hour) so a manual
   re-run cannot double-count.
2. **`core/ipo/velocity.py`** — pure functions over one symbol's snapshots.
   `demand_velocity()` (× added since the previous snapshot and since window
   open) and `final_snapshot()` (the last row before close — the feature vector
   P3 will consume). Deltas over captured facts; no scores.
3. **`services/data/fetchers/ipo_offer.py`** — OFS/fresh split from the
   `issueInfo` free text. **Task 1 is a spike**, mirroring P0's structure:
   confirm `issueInfo` carries the split for *past* symbols. If it does not,
   OFS drops out of P2 and that is reported — no parser for a field that is not
   there.
4. **`services/data/fetchers/ipo_gmp.py`** — built, gated, dark. Requires **≥2
   agreeing sources** (median); a lone snippet number returns `None`, because
   grey-market chatter from one search result is not a measurement.
   `SERPER_API_KEY_IPO` is a **secret**, so it keeps `env=` — the carve-out in
   the no-env-for-toggles rule, not a violation of it.
5. **Wiring** — `_enrich_open_issues` appends a snapshot after each successful
   ladder fetch. **Zero additional NSE calls**: the same fetch, persisted
   instead of discarded.
6. **Watchdog** — a new `ipo_signals_accruing` invariant (§9). `ipo_cache_fresh`
   proves the refresh *job* runs; nothing proves capture *lands*, and a ledger
   that silently stopped accruing is indistinguishable from a quiet IPO month
   until P3 needs the data and finds a hole in it.

#### Two §9b prerequisites fold in, because capture is broken without them

- **The rebuild-discard bug.** Ladder fields evaporate at the next 08:00 pass.
  Unfixed, a closed issue's **final ladder — the single most valuable row in the
  ledger** — is lost the morning after it closes. Fix: carry the previous row's
  ladder forward when the issue has closed or the fetch failed.
- **The Sunday 18:00 collision.** `ipo_refresh_pm` and `weekly_review` fire in
  the same minute unordered. Move the refresh to **17:45** — still after NSE's
  ~17:00 bid update, and capture then deterministically precedes the digest that
  reads it.

#### What becomes visible

`_ipo_demand` gains the split it already holds:

```
• MILKYMIST  Milkymist Dairy  ·  closes today
    Lean: STRONG DEMAND · 12.4× overall (QIB 28×, retail 6×) · 46% at cut-off · +3.1× today
```

Every clause omitted when `None`. No index, no quadrant, no two-horizon verdict.

#### Config

`ipo.signals_enabled: true`, `ipo.gmp_enabled: false`,
`ipo.gmp_min_sources: 2`, `ipo.signal_retention_days: 400` (>365 so P4 can read
a full convergence year). All via `cfg()`, no `env=`; `SERPER_API_KEY_IPO` is
the sole `env=` and only because it is a secret.

#### Testing

Ledger append-only / dedup / corrupt-line tolerance. Velocity with a single
snapshot returning `None`, never `0`. GMP keyless ⇒ `None` **and zero
`record_call`** — the quota gate is asserted, not assumed. OFS parser against
real spike strings plus a garbage string ⇒ `None`. Closes the positive-case gap
§9b flagged: `combined["total"]` and `dom_fi` are currently only asserted
`is None`, and P2 is `dom_fi`'s first consumer. The regression that matters
most: **a closed issue keeps its final ladder across a later refresh pass.**

#### Not in P2

RHP PDF extraction; the named anchor-investor list; hype/substance indices;
verdicts; any change to the brief's existing demand lean; the auditor
`Lane="ipo"` extension (P5).

**Cost:** zero new API calls while `gmp_enabled: false`. NSE ladder fetch count
unchanged. Storage ≈ 50 KB/month.

#### First OFS measurement (2026-08-15) — the spec's own intuition is contradicted

The `--ofs` backfill ran live: **161 of 209 rows enriched, 48 failed**, leaving **144 rows with
both an OFS share and a listing-day outcome**. Mean return vs issue price, by OFS bucket:

| bucket | 1td | 21td | 63td | 252td |
|---|---|---|---|---|
| fresh-heavy (OFS ≤33%) | +14.49% (n=67) | +13.08% (n=63) | +9.66% (n=61) | +22.87% (n=22) |
| mixed (33–66%) | +14.87% (n=38) | +21.00% (n=38) | +23.64% (n=37) | +24.30% (n=18) |
| **OFS-heavy (>66%)** | **+25.51%** (n=39) | **+23.04%** (n=37) | **+27.90%** (n=36) | **+35.72%** (n=20) |

Every quoted cell clears the report's n≥10 floor. **OFS-heavy issues outperformed at every
horizon** — the opposite of §3's stated reading that promoters cashing out is the bad sign.

**This is an association, not a cause, and four things must be said with it:**

1. **The sample is biased.** The 48 parse failures skew toward worse performers — missing-OFS
   listing-day mean **+10.52%** (n=44) versus present-OFS **+17.57%** (n=144). The OFS column
   is not a representative sample of the spine.
2. **Maturity confound.** A company able to execute a large offer-for-sale is typically a
   mature, PE/VC-backed business with a track record — exactly the kind that lists well. OFS
   share may be proxying for company maturity rather than promoter conviction.
3. **One regime.** 2024-05 → 2026-08 was a strong window for Indian IPOs; every bucket is
   positive at every horizon. The ordering could invert in a different regime.
4. **Overlapping windows at 252td** (n=22/18/20) mean effective n ≪ nominal n — the same
   caveat the verification layer recorded for its `^NSEI` hit-rate.

**Consequence for P3:** OFS is now a *measured* feature rather than an assumed one, and what was
measured points the other way. P3 must not weight it on this evidence. The honest next step is
to reduce the 23% parse-failure rate and re-measure, since fixing the bias could move the result
in either direction.

#### Re-measurement (2026-08-18) — the parse-failure rate is fixed, and the 252td lead is gone

The "reduce the failure rate and re-measure" step above was carried out. All 48 unparsed rows
were re-fetched and their raw "Issue Size" text classified, which showed the 23% was **three
concrete parser bugs, not irreducible prose**:

| cause | rows | fix |
|---|---|---|
| amount stated with no `Rs.` prefix ("Fresh Issue upto 5000 million") | 17 | accept a bare `<number> <unit word>` as Rupees; a share count always says "Equity Shares" |
| unbalanced parentheses — NSE forgets the closing `)` | 6 | depth-aware strip defined for malformed input, guarded by "stripping must not remove a leg heading" |
| the abbreviation `OFS` instead of the words (NSDL) | 1 | word-bounded `\bOFS\b` in the heading regex |
| transient NSE fetch failure during the 2026-08-15 run | 3 | re-fetch |

**Result: 161 → 188 rows enriched, parse-failure rate 23.0% → 10.0%, rows with both an OFS
share and an outcome 144 → 170.** No pre-existing `ofs_share` changed and no other spine field
was touched (verified row-by-row against the pre-run copy).

**10% is the floor for this source, not a remaining bug.** All 21 stragglers were fetched
successfully and classified: 15 disclose one single total with no split at all ("Initial Public
Offer of up to 77,86,120 Equity Shares"), 4 carry no Issue Size row, and 2 (MOLBIO, DHOOTTRANS)
state both legs in mixed units but have no issue price in the spine to reconcile them — and both
of those also have no outcome, so they are inert for this measurement. None of the 21 is a parser
gap. Widening the parser until a single-total row produced a number would be fabricating the
signal, not measuring it.

Mean return vs issue price, same buckets and same n≥10 quoting floor as 2026-08-15:

| bucket | 1td | 21td | 63td | 252td |
|---|---|---|---|---|
| fresh-heavy (OFS ≤33%) | +14.13% (n=76) | +12.79% (n=72) | +11.38% (n=70) | **+34.17%** (n=25) |
| mixed (33–66%) | +14.41% (n=50) | +19.80% (n=50) | +18.49% (n=49) | +17.92% (n=23) |
| **OFS-heavy (>66%)** | **+23.58%** (n=44) | **+20.52%** (n=42) | **+22.79%** (n=41) | +32.91% (n=21) |

**What changed, and it is the finding that matters:**

1. **"OFS-heavy outperformed at EVERY horizon" is no longer true.** At 252td the ordering
   flipped: fresh-heavy +34.17% (n=25) now edges OFS-heavy +32.91% (n=21). The 2026-08-15 gap at
   that horizon was +35.72% vs +22.87% — a 12.85pp OFS-heavy lead that has become a 1.26pp
   fresh-heavy lead. A 26-row sample change should not move a real effect that far; the original
   252td cell was thin and unstable, exactly as the overlapping-windows caveat warned.
2. **The short-horizon association survived, slightly weakened.** Listing-day gap 11.02pp →
   9.45pp; OFS-heavy still leads at 1/21/63td. Demand-at-listing is where this effect lives.
3. **The selection bias persists and is now structural rather than fixable.** Rows with an OFS
   share average +16.66% on listing day (n=170) against +8.96% for those without (n=18) — a
   *wider* per-row gap than before (+17.57% vs +10.52%), on far fewer missing rows. Non-disclosure
   of the split is itself associated with worse listings, so the residual bias cannot be parsed
   away; it is a property of which issuers break the split out.

**Consequence for P3: unchanged, and the case is now stronger.** OFS must not be weighted. The
one horizon that moved is the long one — precisely where the Ather thesis ("unloved at issue, big
later") would have to appear — and it moved to "no signal" rather than to either reading. What P2
has established is that the OFS column is now 90% complete and honest, not that it predicts
anything.

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
`env=`**. The single exception is `SERPER_API_KEY_IPO`, which is a *secret* and
therefore keeps `env=` — the carve-out in the no-env-for-toggles rule.

```yaml
ipo:
  enabled: true
  refresh_hour: 8               # daily calendar/bid refresh (IST)
  refresh_hour_live: 17         # P2: was 18 — see below
  refresh_minute_live: 45       # P2: 17:45, after NSE's ~17:00 bid update and
                                #     strictly before Sunday's 18:00 weekly_review
  verdicts_visible: false       # P5 gate — flipped only on measured evidence
  signals_enabled: true         # P2: append to the capture ledger
  gmp_enabled: false            # P2: stays false until SERPER_API_KEY_IPO exists
  gmp_min_sources: 2            # P2: a lone snippet number is not a measurement
  gmp_max_age_hours: 24
  signal_retention_days: 400    # P2: >365 so P4 can read a full convergence year
  hype_weights: {...}           # P3
  substance_weights: {...}      # P3
  convergence_window_days: 365  # P4
```

**`refresh_hour_live` moves 18:00 → 17:45 in P2.** The scheduler currently pins
`minute=0` (`scheduler.py:501`), so the move needs a minute key alongside the
hour. It applies every day rather than only Sunday: 17:45 is still after NSE's
bid update, and a single daily slot is simpler than a weekday exception. The
reason is the Sunday collision — `ipo_refresh_pm` and `weekly_review` both fire
at 18:00 with no ordering, making the digest a coin flip between the fresh cache
and the morning one (§9b).

## 7. Risks

1. ~~**The endpoint spike is load-bearing.**~~ **CLOSED 2026-08-11 — resolved
   favourably.** `/api/ipo-detail?symbol=X&series=EQ` and
   `/api/ipo-active-category?symbol=X` both return 200 with a full
   category-wise bid ladder, live, through the existing primed `nse` session.
   Full verified contract in §11. The residual risk moved to risk 6.
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
6. **NSE-only vs all-exchange subscription figures disagree, inside a single
   response.** For MOLBIO on 2026-08-11, `ipo-detail.bidDetails` reported QIB
   **0.564×** while `ipo-detail.activeCat` reported QIB **1.391×**. Arithmetic
   (§11.4) indicates `bidDetails`/`demandDataNSE` are **NSE-only** and
   `activeCat` is **all-exchange combined** — the latter being what the press
   and the market quote. **A naive implementation reading the more convenient
   `bidDetails` shape would silently under-report every IPO's demand**, which is
   precisely the class of bug that produces confidently wrong verdicts. Treated
   as a hypothesis, not a finding: P0 must verify it on a second symbol against
   NSE's published end-of-day figure before either source is trusted.

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
| `ipo_signals_accruing` | invariant (P2) | An issue is **open** but the capture ledger holds no snapshot for it ⇒ perishable demand data is being lost. `ipo_cache_fresh` proves the *job* runs; it cannot prove capture *lands*. Scoped to open windows so a quiet IPO month reports satisfied rather than crying wolf. |

## 9b. Known follow-ups from P0/P1 execution

Triaged during the whole-branch review of 2026-08-13. Recorded here because the
execution workspace is scratch and these would otherwise be discarded silently.
Nothing here blocks merge; the Critical and Important findings were fixed in
`a578ac6`.

**Do before the next deploy**

- ~~**Verify `DISCOVERY_IPO_ENABLED` is unset in Railway.**~~ **✅ CLOSED
  2026-08-13 — user-verified unset in both the env file and prod**, so dropping
  the `env=` override was a no-op at runtime (`cfg()` already fell through to
  `config.yaml`'s `discovery.ipo_enabled: true`). The deploy has since happened.
  Do not re-raise.

**Worth doing soon**

- **→ absorbed into P2.** `combined["total"]` — the entire P1 predictor column —
  is only asserted `is None` in the ladder fixture. Add a positive case. Same
  for `dom_fi`, which currently has no consumer at all — P2 is its first.
- `IpoHistoryStore.upsert` rewrites the whole file per row (O(n²) IO at ~206
  rows) and is the root cause of the OneDrive lock that `_upsert_with_retry`
  works around. An `upsert_many` fixes both.
- **→ absorbed into P2 (prerequisite).** `ipo_refresh_pm` (Sun 18:00 IST) and
  `weekly_review` (Sun 18:00 IST) fire in the same minute with no ordering, so
  the digest is a coin flip between the fresh cache and the 08:00 one. Writes
  are atomic, so this is non-determinism, not corruption. Move one slot — P2
  moves the refresh to 17:45 (§6).

**Lower priority**

- `IPO_ENABLED`, `IPO_REFRESH_HOUR`, `IPO_REFRESH_HOUR_LIVE` are declared in
  `base.py` but never read — the scheduler calls `cfg("ipo.…")` directly. Read
  them or delete them.
- **→ absorbed into P2 (prerequisite; promoted from Lower priority).**
  `_enrich_open_issues` rebuilds rows from `_normalise` each run, so
  `bid_ladder` / `cutoff_share` / ladder-derived `qib_x`/`retail_x` are
  discarded at the next 08:00 pass. A closed issue's brief line degrades
  overnight from "40× overall (QIB 90×, retail 12×)" to bare "40× overall".
  **P2 promotes this to a blocker:** unfixed, the closed issue's final ladder —
  the most valuable row in the capture ledger — is lost the morning after the
  window shuts.
- **→ absorbed into P2 (surfaced).** `cutoff_share` is fetched, cached, and
  threaded into every brief row, then never rendered. Either surface it (it is
  a real froth signal — see §3) or drop the plumbing. P2 surfaces it.
- `ipo_cache_fresh` cannot see a *degraded* feed: `refresh_ipo_cache` writes
  `fetched_at` even when the fetch failed, so a week-long NSE outage still
  reports `satisfied`. Correctly scoped to "the job died" per its docstring,
  but stale content is equally silent. Fold `degraded` into the verdict or at
  least the evidence.
- The ladder-fetch budget is decremented even when `fetch_bid_ladder` fails, so
  a run of dead-endpoint failures can exhaust `IPO_MAX_LADDER_FETCHES` with
  zero successful enrichment.
- The placeholder-total guard also applies to `nse_only`. Mid-bidding, if only
  NII/Employee rows have posted, a real partial total would be nulled. No
  consumer reads `nse_only` today; revisit when one does.
- `checks.py` re-encodes the `48` default already set in
  `cfg("ipo.cache_max_age_hours", fallback=48)`.
- The watchdog check's naive-timestamp and malformed-JSON branches are verified
  by inspection only, not by a test.

## 10. Open questions

None blocking. Weight values for H and S are deliberately deferred to P3, where
the P1 measurement informs them — setting them now would be inventing numbers
ahead of the evidence.

---

## 11. Appendix — verified NSE data contract

**Spiked live against NSE on 2026-08-11** using the existing primed `nse`
session (`NSE._session`), read-only GETs. Live symbols at the time: `MILKYMIST`
(11-13 Aug), `MOLBIO` (10-12 Aug), `DHOOTTRANS` (10-12 Aug). Everything below is
observed, not inferred.

### 11.1 `/api/ipo-current-issue` — carries the total × already

```
keys: category, companyName, issueEndDate, issuePrice, issueSize,
      issueStartDate, noOfSharesOffered, noOfTime, noOfsharesBid,
      series, srNo, status, symbol
```

```json
{"symbol": "MILKYMIST", "companyName": "Milky Mist Dairy Food Limited",
 "issueStartDate": "11-Aug-2026", "issueEndDate": "13-Aug-2026",
 "issuePrice": "Rs.133 to Rs.140", "series": "EQ", "status": "Active",
 "category": "Total", "noOfTime": "0.5315724992825029"}
```

- `noOfTime` **is** the total subscription × — the key the fetcher never guessed.
- `issueStartDate` / `issueEndDate` confirm defect #2. `status: "Active"` exists.
- `issuePrice` is a **band string**; the existing `_parse_price` takes the last
  number (upper band, 140) — correct, and now documented so it is not "fixed".
- `/all-upcoming-issues?category=ipo` returns only 8 keys — **no bid data**, as
  expected for issues not yet open.

### 11.2 `/api/ipo-detail?symbol=X&series=EQ` — the rich one

Top-level: `companyName, metaInfo, bidDetails, issueInfo, activeCat,
demandGraph, demandDataNSE, demandDataBSE, demandGraphALL`.

`bidDetails` — 21 rows, full ladder with per-category × (`noOfTime`), MOLBIO:

| srNo | category | × |
|---|---|---|
| 1 | Qualified Institutional Buyers (QIBs) | 0.564 |
| 1(a) / 1(b) / 1(c) / 1(d) | FIIs / Domestic FIs / **Mutual funds** / Others | bid qty only |
| 2 | Non Institutional Investors | 3.604 |
| 2.1 / 2.2 | NII >10L / NII >2L | 3.066 / 4.679 |
| 3 | **Retail Individual Investors (RIIs)** | 2.226 |
| 3(a) / 3(b) | Cut Off / Price bids | bid qty only |
| 4 | Employees | 3.803 |
| — | **Total** | 2.051 |

`issueInfo.dataList` is `{title, value}` pairs and **contains the OFS split**:

> "Initial Public Offering comprising of **Fresh Issue** aggregating up to Rs.
> 2,000 million and **Offer for Sale** of up to 9,166,000 Equity Shares
> (including Employee reservation … and **Anchor Investor portion** of up to
> 34,87,717 Equity Shares)"

Free text — extraction required, but no external source needed.

### 11.3 Price-level demand curve — an unplanned upgrade

`demandDataNSE` (36 rows) / `demandDataBSE` (37 rows) give **cumulative bid
quantity at every price point in the band**, each row timestamped
(`11-Aug-2026 17:00:56`). `demandGraph` carries `totalBidAtCutOff` and
`TOTAL_BIDS`, and states the graph **"is updated every hour."**

Two signals fall out for free, both official:

- **Cut-off share** — MOLBIO `7,752,114 / 16,731,036` = **46%** bidding at
  cut-off, i.e. price-insensitive demand.
- **Demand velocity** — hourly refresh makes intra-window bid accumulation
  directly measurable.

This is why GMP is demoted to a corroborating signal in §3.

### 11.4 The NSE-only vs combined arithmetic (see §7 risk 6)

| figure | `bidDetails` / `demandDataNSE` | `activeCat` / `demandGraphALL` |
|---|---|---|
| MOLBIO QIB × | 0.564 | 1.391 |
| MOLBIO total bids | 16,731,036 | 25,437,636 |

`demandDataNSE.TOTAL_BIDS` (16,731,036) matches `bidDetails` Total exactly and
matches `ipo-current-issue`'s 2.0507× — so **`bidDetails` is NSE-only** and
`activeCat` is almost certainly all-exchange. Compelling, single-symbol, and
**not yet proven** — hence the P0 verification task.

### 11.5 Endpoints probed and rejected

| endpoint | result |
|---|---|
| `/api/ipo-active-category?symbol=X` | **200, works** — `{dataList, heading, symbol, updateTime}`; carries `updateTime` for freshness. First `dataList` row is a **header row whose values are column labels** — must be skipped. |
| `/api/ipo-bid-details?symbol=X` | 200 but body `missing params` — wrong parameter set; superseded, not pursued |
| `/api/public-past-issues?symbol=X` | 200, empty — needs date-range params (`listPastIPO` already wraps this) |

`series=EQ` is optional on both working endpoints; results were identical with
and without it.
