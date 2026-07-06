# StockAgent "Compass" — Personal Portfolio Intelligence & Discovery Layer

**Status:** DRAFT — awaiting user approval
**Date:** 2026-07-06
**Scope:** ~40-50% product expansion on the existing RL/agent foundation
**Author:** Claude (researched online 2026-07-06; sources at bottom)

---

## 1. Vision

Today StockAgent is a *reactive analyst*: it forecasts and learns on a fixed
managed universe, and answers questions when asked. Compass turns it into a
*proactive personal intelligence product*:

> The product knows what the user holds, watches those positions every trading
> day with the full RL machinery, tells the user when to HOLD / ADD / TRIM /
> EXIT / SWITCH — and independently hunts the whole market (including fresh
> listings and under-the-radar small/mid-caps) for the next positional
> opportunity, delivered as a morning brief without being asked.

Positional horizon: **weeks to a few months** (not intraday). This aligns with
the existing 30-day envelopes and with the best-evidenced return factor in
Indian equities at this horizon (see §6.1).

**The moat:** every advisory competitor in India (Univest, Tickertape,
smallcase, INDmoney) ships recommendations forward; none of them score their
own past advice and adapt. StockAgent already has the machinery to do this
(daily review, scorecard, baseline duel, weight adaptation). Compass extends
that learning loop to *advice* and *discovery* — the product gets measurably
better at advising this user every month, and can prove it.

---

## 2. Regulatory posture (decides what the product may say)

Research findings (2026):

- Offering personalised buy/sell recommendations to *others* in India requires
  SEBI registration (Research Analyst for audience-level research; Investment
  Adviser for individually-tailored advice).
- AI does not dilute accountability: commercial AI-assisted recommendations
  must be signed off by a named registered human analyst.
- Tickertape's positioning ("analytics tool, not advisor") is the standard
  unregistered posture; Univest's ("SEBI-RA backed calls") is the registered one.

**Posture for Compass:** a **single-user personal research tool** operated by
its owner for his own portfolio — no registration required. Hard rules baked
into the design so a future multi-user pivot doesn't inherit liabilities:

1. Every output is labelled research/analysis, never "advice"; confidence and
   risk bands always shown.
2. No auto-trading. Ever. The product informs; the human acts.
3. All advice text and rationale archived (advice ledger) — if the product is
   ever commercialised, this becomes the RA-compliance audit trail, and a
   registered analyst sign-off step slots between engine and delivery.

---

## 3. Architecture overview

Four new modules ride on the existing foundation (envelopes, daily review,
dossiers, ledgers, regime detector, unified analyst, scorecard/duel, telemetry):

```
                        ┌────────────────────────────────────────────┐
                        │            M4 PROACTIVE DELIVERY           │
                        │  morning brief · event alerts · weekly     │
                        │  portfolio review · PWA push / email       │
                        └──────▲──────────────▲───────────────▲──────┘
                               │              │               │
      ┌────────────────────────┴──┐  ┌────────┴─────────┐  ┌──┴───────────────┐
      │   M2 POSITION ADVISOR     │  │  M3 DISCOVERY    │  │  (existing)      │
      │ HOLD/ADD/TRIM/EXIT/SWITCH │  │  ENGINE          │  │  chat + UI       │
      │ tax-aware · event-aware   │  │ funnel + IPO     │  │                  │
      └──────▲──────────▲─────────┘  │ tracker + shelf  │  └──────────────────┘
             │          │            └───▲──────────▲───┘
   ┌─────────┴───┐  ┌───┴────────────────┴───┐  ┌───┴──────────────────────┐
   │ M1 PORTFOLIO│  │ EXISTING RL FOUNDATION │  │ NEW QUANT DATA LAYER     │
   │ CORE        │  │ envelopes · reviews ·  │  │ bhavcopy · delivery % ·  │
   │ holdings ·  │  │ dossiers · regime ·    │  │ bulk/block · corp actions│
   │ watchlist   │  │ scorecard/duel · RL    │  │ · IPO calendar (free)    │
   └─────────────┘  └────────────────────────┘  └──────────────────────────┘
```

Everything new follows the house rules: json_object + `JSON_MODE_EXTRA_BODY`,
pipeline errors are telemetry never training signal, config.yaml tunables,
volume-persisted state, flag-gated rollout.

---

## 4. M1 — Portfolio Core

### 4.1 Data model (volume: `/app/data/portfolio/`)

**USER DECISION 2026-07-06: virtual-first, per-user from day one.** No broker
integration at launch. Holdings are VIRTUAL positions entered by the user
(mock money, real market): entry price = actual NSE close on entry date,
P&L marked daily against real closes on trading days only (existing
nse_calendar). The product behaves exactly as if the money were real —
advice, alerts, ledger — so the system's advice quality is proven on paper
before a rupee moves. Broker sync (Kite Personal, free) becomes an optional
later upgrade that flips `virtual: false`.

```
data/portfolio/<user_id>/portfolio.json     # per-user keyed from day one
  holdings: [ { symbol, sector, qty, avg_buy_price, buy_date(s),
                virtual: true,        # mock-money position (launch default)
                adj_avg_price,        # corp-action-adjusted (splits/bonus) —
                                      # ALL P&L/stop math uses this, never raw
                broker, notes, target_pct?, max_loss_pct? } ]
  watchlist: [ { symbol, added, reason, source: user|discovery } ]
  cash_deployable: float?          # optional — enables ADD sizing
  risk_profile: conservative|balanced|aggressive   # default balanced
advice_ledger.jsonl     # append-only: every advice emitted + outcome fields
                        # outcome math includes dividends received, so
                        # HOLD/TRIM scoring isn't biased against payers
```

**Corp-action invariant (BLOCKER-grade):** a daily corp-action sync (splits,
bonuses, dividends — from the existing NSE corporate-actions fetcher) adjusts
`adj_avg_price` BEFORE any advisor rule runs. Without this, a 1:1 bonus looks
like a −50% crash and fires a false EXIT. No EXIT/stop rule ships before this
adjustment exists (Phase A dependency).

### 4.2 Ingestion (phased)

| Phase | Method | Notes |
|---|---|---|
| A | **Virtual portfolio** — user enters mock buys (symbol, qty, date) via chat/UI; entry priced at real NSE close; daily mark-to-market on trading days | zero dependencies; proves advice quality risk-free |
| A | CSV import (same schema) | bulk entry convenience |
| later (opt-in) | Kite Connect Personal API — free tier | flips positions to `virtual: false` when user goes live |
| later | CDSL CAS PDF parse | only if multi-broker needed |

### 4.3 Auto-promotion — the key mechanic

Any held or watchlisted symbol is **automatically promoted into the managed
universe**: envelope forecast on the monthly cron, daily 16:30 IST review,
dossier, ledgers — identical treatment to today's 16 tickers. Sector resolved
via the existing NSE-first symbol resolver; unknown sectors use the generic
sector graph (**Phase B build** — see reality check below, Phase A supports
the 4 existing sectors only). A cap (`portfolio.max_managed_tickers`, default 40)
guards LLM spend; beyond cap, lowest-priority watchlist names rotate out
(held > watchlist > discovery).

This single mechanic delivers the core promise: *the product does the
background work for the user's stocks, every day, without being asked.*

**Reality check (verified against code):** `sector_router.py` supports exactly
4 sectors and silently falls back to the **automobile** orchestrator + weights
for anything else — an auto-promoted pharma stock would be analyzed as a car
company. Therefore:

- **Phase A**: promotion restricted to symbols in the 4 supported sectors
  (resolver rejects others with a clear "sector not yet supported" note).
- **Phase B**: build the **generic sector graph** (sector-agnostic unified
  analyst prompt + neutral agent weights) — this is a NEW build, not existing
  plumbing — then lift the restriction.

**Cost/runtime at cap (40 tickers):** ~$0.021/ticker-day reasoning spend →
≈ **$19/month** for daily reviews alone (~5× today) plus monthly envelopes and
weekly deep-dives; the cap and a `portfolio.review_cadence` tier keep this
governed — **held names review daily; watchlist and paper names weekly**
(config-tunable). Sequential runtime at 40 names is ~80 min, so all downstream
consumers (advisor, digest) are **event-triggered on job completion, never
clock-scheduled** (see §7).

---

## 5. M2 — Position Advisor

Runs **after** the daily review cron (new step in the same singleton job) for
every held symbol. Pure-Python decision engine over signals the foundation
already computes — the LLM only *narrates* the decision (BULK tier), it does
not make it. Deterministic, testable, cheap.

### 5.1 Inputs per holding

- Envelope state: remaining-forecast drift vs entry, confidence trend,
  reforecast events (shock = attention)
- Today's review: direction accuracy streak, miss_type, regime label (sticky)
- Dossier: open risks, thesis status, upcoming events (earnings date!)
- P&L context: unrealised %, holding age, distance to 12-month LTCG boundary
- Portfolio context: sector concentration, position weight

### 5.2 Verdict rules (v1 — all thresholds in config.yaml)

**Verdict precedence (explicit, non-negotiable): EXIT > TRIM > ADD > HOLD.**
Tax-deferral logic may soften a TRIM into a WAIT-FOR-LTCG note; it must
**never suppress or delay an EXIT** — capital protection outranks tax
optimisation, always.

| Verdict | Core trigger (simplified) |
|---|---|
| **HOLD** | default; thesis intact, envelope within band |
| **ADD** | envelope bullish + regime supportive + position < max weight + conviction streak healthy |
| **TRIM** | profit ≥ `advisor.trim_profit_pct` (def 25%) AND (envelope confidence declining OR reversion prior elevated) — *tax-aware: if 10-12mo old and thesis intact, prefer WAIT-FOR-LTCG note over TRIM* |
| **EXIT** | thesis_break/shock reforecast against position, OR loss ≥ volatility-scaled stop (below), OR regime MACRO_CRISIS + envelope bearish |
| **SWITCH** | EXIT triggered AND discovery shelf has a ≥`advisor.switch_conviction_gap` stronger candidate in an underweight sector |

**Volatility-scaled stops, not a flat %.** A flat 12% is one bad week of noise
on a small cap and far too loose on a large-cap bank. Stop = clamp(
`advisor.stop_atr_mult` (def 3) × ATR(20d) as %, per-cap-bucket floors/caps in
config.yaml — e.g. large 8-12%, mid 12-18%, small 15-22%, tightened one notch
for `conservative` profiles). All P&L uses `adj_avg_price` (§4.1).

Evidence-based guardrails: **earnings-gap rule** (profitable position +
earnings within 3 trading days → flag profit-protection option) — requires the
**NSE corporate-events calendar fetcher** (named Phase A deliverable, feeds
forward earnings dates); simple time-based review beats complex trailing stops
(research §12), so exits are event/thesis-driven, not tick-driven.

### 5.3 Advice ledger — the learning loop

Every advice line is appended with: date, symbol, verdict, price, rationale
hash, confidence. Outcomes are filled by the existing review machinery at
+10td/+30td/+60td. Monthly scorecard gains an **advice panel**: hit rate per
verdict type, PnL of followed-vs-ignored, calibration curve. The WeightAdapter
pattern extends: persistently wrong TRIM calls raise the trim threshold, etc.
(Phase D; ledger from day one so data accumulates immediately.)

---

## 6. M3 — Discovery Engine ("stocks from nowhere")

A weekly funnel: **~2000 NSE mainboard stocks → ~40 quant candidates → ~10 LLM
deep-dives → 5-10 shelf ideas**, each with a paper envelope so the duel
machinery scores discovery quality from day one.

### 6.1 Stage 1 — quant screen (free data, zero LLM)

Weekly job (Sat, after event-ingest). Signals, each evidence-backed:

| Signal | Rationale | Source |
|---|---|---|
| 6m+12m volatility-adjusted momentum | NSE's own Midcap150 Momentum 50 methodology — the best-evidenced factor at our horizon | bhavcopy history |
| Delivery % surge vs 20d avg | delivery-backed moves = conviction, not churn | NSE delivery data (free) |
| Volume anomaly + price consolidation breakout | accumulation signature | bhavcopy |
| Repeated same-side bulk/block deals | institutional accumulation detection (buys ≫ sells over 4wks) | NSE bulk/block feed (free) |
| Promoter/insider net buying | strongest insider signal | NSE insider-trading disclosures |
| 52-wk-high proximity with RS vs sector index | momentum confirmation | computed |
| Mutual-fund monthly holding increases | institutional conviction, free from AMC disclosures | AMC portfolios (monthly) |

*(Dropped from v1: earnings-surprise scoring — it needs parsed quarterly
numbers from XBRL/PDF filings, a sub-project of its own. The corporate-events
CALENDAR (dates only) stays — the advisor's earnings-gap rule needs it. Results
parsing is a named Phase-D+ candidate.)*

Composite score = weighted rank blend (weights in config.yaml under
`discovery.*` — future RL target). Threshold gates BEFORE scoring:

- **Liquidity floor:** median daily traded value ≥ ₹5 cr (configurable) — kills
  the manipulation-prone micro/SME tail
- **Free-float mcap floor** (def ₹500 cr) — thin-float names are operator bait
- Not in ASM/GSM surveillance lists; **not BE/BZ (Trade-to-Trade) series**;
  price > ₹20; no upper-circuit streaks (operator pattern); promoter pledge < 25%

### 6.2 Stage 2 — IPO / new-listing tracker

Weekly + event-driven. Research-calibrated (oversubscription ≠ performance;
~40% of 2021-25 IPOs fell below issue soon after listing):

- **QIB subscription weighted 3× retail** (informed vs froth)
- Post-listing evidence over hype: 30-90d price vs issue, delivery %,
  post-listing institutional adds (bulk deals)
- **Lock-in expiry calendar** (1m/3m/6m anchor-investor cliffs = supply risk —
  flag, don't buy into them)
- **SME platform excluded by default** (`discovery.include_sme: false`) —
  extreme oversubscription (700-2200×) + thin float = manipulation risk
- Candidates surface into the same Stage-3 deep-dive as screen hits

### 6.3 Stage 3 — LLM deep-dive + shelf

Top ~10 weekly candidates run the **unified analyst** (existing, one call per
name, BULK/REASONING tiers) + Serper news context → conviction score, entry
zone, thesis, risks, expected horizon. Top 5-10 live on the **Discovery
Shelf** with:

- a **paper envelope** (virtual position, real forecasts) — scored on the
  review machinery **in an isolated paper lane** (invariant below); shelf
  hit-rate becomes a first-class metric
- add/drop events pushed via M4; stale ideas (>60d without trigger) rotate out
- one-tap (or one-chat-command) promote-to-watchlist

**PAPER-LANE ISOLATION — design invariant, not an implementation detail.**
The real daily review propagates lessons into SHARED sector/market ledgers
and updates WeightMemory; letting junk discovery ideas write there would
poison the learning of real holdings. Therefore paper reviews run with:

1. a separate store root (`/app/data/rl/paper/…`, PredictionStore param),
2. `paper=True` mode that **hard-disables shared-ledger propagation and
   WeightAdapter writes** (per-idea local ledger only),
3. a separate scorecard panel (paper hit-rate never mixes into real metrics),
4. weekly (not daily) review cadence to bound cost.

A unit test asserting "paper review never touches sector/market ledger or
weight memory files" ships with the feature.

Discovery learns two ways: (a) screen weights re-fit quarterly against paper
outcomes; (b) dossier-style lesson notes on why ideas worked/failed feed the
prompt context of future deep-dives.

---

## 7. M4 — Proactive Delivery

| Artifact | When | Contents |
|---|---|---|
| **Morning Brief** | 08:50 IST (after pre-open check) | portfolio health line, overnight events touching holdings, today's advisor flags, regime note, discovery adds |
| **EOD Digest** | **event-triggered on review+advisor job completion** (never clock-scheduled — at 40 tickers the review runs ~80 min) | per-holding verdicts with one-line reasons, PnL move, envelope status, any TRIM/EXIT/SWITCH escalations |
| **Event alerts** | real-time-ish (existing crons) | shock reforecast on a holding, earnings-gap warning, stop-level breach, lock-in expiry on shelf name |
| **Weekly Review** | Sun 18:00 IST | allocation vs risk profile, laggard analysis, switch candidates, advice-ledger scoreboard ("last month: 7/9 HOLD calls right") |

Channels: existing PWA (web-push via service worker — TWA app gets it free),
plus email fallback (single user = trivial SMTP). Chat command `brief` renders
the latest anytime. All content generated by BULK tier from structured
advisor/discovery output — narration, not decision-making.

---

## 8. Data plan (all free)

| Data | Source | Cadence |
|---|---|---|
| EOD OHLCV + delivery % | NSE bhavcopy (python `nsefin`/direct) | daily job, volume-cached |
| Bulk/block deals | NSE report endpoints | daily |
| Insider/pledge/shareholding | NSE disclosures | weekly |
| Corporate announcements/results | existing NSE fetcher | existing |
| IPO calendar/subscription | chittorgarh/NSE scrape | weekly |
| News/deep-dive context | existing Serper/Tavily | per deep-dive |

New store: `data/market_cache/` (bhavcopy history, ~2yr rolling, parquet;
~200MB — fits the 4.9GB volume). All fetchers behind the existing non-fatal
telemetry-logged pattern.

**Fetch-fragility plan (NSE blocks datacenter IPs on its fancier endpoints):**
bhavcopy ARCHIVES (which now include delivery %) download reliably and are the
backbone. Bulk/block, insider, ASM/GSM and events-calendar endpoints get the
existing cookie-dance fetcher + explicit **degraded mode**: if a feed 403s for
N days, the screen runs archives-only (momentum/delivery/volume signals) and
the brief says which signals are dark. No feed is a single point of failure.

---

## 9. Safety rails (non-negotiable, config-gated)

0. **Auth prerequisite (Phase A, before any real holdings are stored):** set
   `SCHEDULER_KEY` in prod (endpoints are currently open) and gate ALL
   portfolio/advice routes behind a bearer token. A public Railway URL serving
   someone's holdings + buy/sell verdicts is both a privacy hole and a
   regulatory one (open access = publishing recommendations).
1. Liquidity floor + free-float floor + surveillance-list + T2T-series +
   circuit/operator filters (§6.1)
2. Position-size suggestions capped at `advisor.max_position_pct` (def 10%)
3. Sector concentration warnings at 30%
4. Every BUY idea carries an invalidation level ("thesis dead below X")
5. Confidence always displayed; advice ledger makes the product's own track
   record visible in-product — honesty by construction
6. SME IPOs excluded by default; no penny stocks (<₹20)
7. No auto-trade; no leverage/F&O suggestions in v1

---

## 10. Phasing (each phase independently shippable)

| Phase | Deliverable | Est. effort | New surface |
|---|---|---|---|
| **A — Portfolio Core + Advisor v1** | **auth gate + SCHEDULER_KEY first**; holdings (manual/CSV) with corp-action-adjusted P&L; corporate-events calendar fetcher; auto-promotion (4 supported sectors only); HOLD/ADD/TRIM/EXIT engine with ATR-scaled stops; advice ledger; digest event-triggered on review completion | ~2.5-3 wks | ~15% |
| **B — Discovery funnel + generic sector graph** | bhavcopy/market-cache layer, quant screen + all guards, **generic sector graph** (lifts the 4-sector promotion limit), shelf + isolated paper lane | ~2.5 wks | ~15% |
| **C — IPO tracker + Proactive delivery** | IPO module, morning brief, push/email, weekly review, SWITCH verdicts, index-inclusion event alerts | ~1.5 wks | ~10% |
| **D — Advice RL** | scorecard advice panel, threshold adaptation, screen-weight re-fit; (candidate: quarterly-results parsing for earnings-surprise signal) | ~1 wk (data-gated ≥6wks of ledger) | ~5% |
| — | Kite Personal sync | 2-3 days, anytime after A | — |

Total ≈ 45% expansion. A alone already delivers the felt product change
(the app watches *your* stocks and tells you things). Steady-state LLM cost
at the 40-ticker cap ≈ **$19-25/month** (reviews + envelopes + deep-dives),
governed by the cap + cadence tiers; today's spend is ~$4-5/month.

---

## 11. Open questions for the user

1. **Broker**: Zerodha? (free Personal API makes sync trivial) Which format
   can you export today?
2. **Holdings now**: how many positions roughly? (sizes the managed-universe cap)
3. **Notification channel**: PWA push, email, or both? Telegram?
4. **Risk posture default**: balanced ok? max single-position 10%?
5. **Universe**: mainboard-only confirmed? (SME excluded by default)
6. **Cash sizing**: willing to maintain `cash_deployable` so ADD/BUY ideas can
   size positions, or keep advice size-free?

---

## 12. Research sources (2026-07-06)

- SEBI IA/RA + AI accountability: mondaq.com SEBI digital compliance 2026;
  azbpartners.com IA/RA framework overhaul; business-standard.com RA/IA guidelines
- Competitor landscape: univest.in blogs (best stock advisor app 2026);
  tickertape.in; smallcase.com; tracxn Tickertape profile
- Momentum methodology: NSE Nifty Midcap150 Momentum 50 (6m+12m vol-adjusted);
  capitalmind.in NSE factor indices
- Bulk/block accumulation detection: tickertape.in market-movers;
  i-am-market.com NSE bulk/block analysis; gripinvest.in
- IPO evidence: taxguru.in IPO trends (oversubscription vs debuts);
  investorgain.com top-subscribed IPOs; chittorgarh.com listing-gain reports;
  ~40% of 2021-25 IPOs below issue soon after listing
- Exits/tax: quantifiedstrategies.com exit-strategy research (simple beats
  complex); onetradejournal.com intraday-vs-swing tax; STCG 20% <12mo /
  LTCG 12.5% >12mo (₹1.25L exempt)
- Data/API: kite.trade docs (Personal free tier holdings); pypi nsefin/bhavcopy;
  NSE report endpoints
