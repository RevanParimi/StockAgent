# Morning Brief Redesign — Design Spec

**Date:** 2026-07-27
**Author:** Claude (Opus 4.8) with Revan
**Status:** Approved (design), pending implementation
**Touches:** `core/delivery/brief.py`, `config.yaml`, `docs/ARCHITECTURE.md`, `tests/unit/test_delivery_brief.py`

---

## 1. Problem

The daily morning brief (delivered 08:50 IST via email + web-push + in-app Inbox) is
a flat, ungrouped list of lines that is hard to read and opaque to a newcomer. Root-caused
from the real 2026-07-24 and 2026-07-27 briefs:

| # | Problem | Root cause | Kind |
|---|---------|-----------|------|
| 1 | Flat wall of lines, no sections | `render_brief_text` concatenates lines with no grouping | presentation |
| 2 | LLM headline repeats the body verbatim (value, regime, overnight, earnings said twice) | Narrated summary + body list the same fields | presentation |
| 3 | Overnight text cut mid-word ("…Middle East con", "…strengtheni") | **Source-side**: Serper/NewsAPI hand us an already-truncated `title`; our fetcher stores it verbatim (`macro_news_fetcher.py:212`). Not recoverable — full text was never in our data | data (display) |
| 4 | Same story appears 3× (+ again in headline) | Overnight dedup is **URL-only**; different URLs for the same story all pass | data |
| 5 | IPO listed twice (e.g. LASERPOWER current + upcoming) | `_ipo_watch` concatenates `current` + `upcoming` with no symbol dedup | presentation |
| 6 | Jargon with no explanation (RISK_OFF, conviction=0.62, "Regime", "Lock-in expiry") | Assumes the reader knows the system | newcomer gap |

## 2. Goals / Non-goals

**Goals**
- Sectioned, scannable plain-text layout (renders identically in email, push, Inbox).
- Plain-English framing with the technical term kept in parentheses (`Cautious (RISK_OFF)`).
- Confidence shown as a percentage (`62%`) plus a one-line reason per idea.
- A clear purpose line for the ideas section (screen → shelf → view → paper-trade).
- Overnight items deduped by content similarity and cleaned of mid-word truncation.
- IPOs shown with live subscription demand, deduped by symbol.
- Stay strictly on the **research, never advice** side of the line (SEBI-sensitive):
  ideas show the tool's *own* verdict/confidence/reason as a research view; IPOs show
  objective demand data — neither is framed as personal advice.

**Non-goals**
- No rich HTML email / in-app card (plain text only, this pass).
- No new IPO buy-rating engine.
- No change to *what* data is collected or to the discovery/paper-lane pipeline itself.
- No change to delivery channels, scheduling, or the single LLM narration call.

## 3. The new brief format

Section order (each **auto-hidden when empty**):

```
══════════════════════════════════════════
  MORNING BRIEF · <DD Mon YYYY>
══════════════════════════════════════════

SUMMARY
  <the existing one LLM-narrated sentence(s) — the "so what">

YOUR PORTFOLIO
  ₹<value> — <up|down N%> since inception.
  <"Nothing needs your attention today." | "N holding(s) flagged — see below.">

NEEDS ATTENTION                     (only when advisor_flags non-empty)
  • <SYM>  <VERDICT in plain words> — <reason>

MARKET CONDITIONS
  <Plain word> (<REGIME_LABEL>) — <one-line gloss of what that means>

OVERNIGHT — HIGH-IMPACT NEWS        (only when items exist)
  • <deduped, clean-trimmed headline>

EARNINGS THIS WEEK   (your holdings) (only when items exist)
  • <SYM>  — <Day DD Mon>

IDEAS THE TOOL IS RESEARCHING   (its own view — not personal advice)
  The scanner flagged these; the tool rated each and is paper-testing the
  thesis. Confidence = how strongly it backs its own call.
  • <SYM>  <VERDICT> · <NN%>
      <core reason — first sentence of the idea's stored thesis>

IPOs OPEN NOW   (live demand — a data point, not a buy call)
  × = times the issue was subscribed; high QIB/overall = institutional interest.
  • <SYM>  <Company>  ·  <N.N× overall (QIB N×, retail N×) | demand data pending>

LOCK-IN EXPIRIES                    (only when flags exist)
  • <SYM> <kind> on <date> — supply risk, not a signal

──────────────────────────────────────────
Research tool — information only, never personal advice.
```

**Style rules**: no emoji (safe on every push/email client); UPPERCASE section headers;
two-space indent for body, four-space for sub-detail; technical term always in parens
after its plain-English word.

## 4. Component design (`core/delivery/brief.py`)

All new helpers are **pure, deterministic, and unit-testable**; **no new LLM calls**.

### 4.1 Static maps / constants
- `_REGIME_PLAIN: dict[str, tuple[str, str]]` — `label → (plain_word, gloss)`.
  Covers every regime the system emits: `NORMAL`, `RISK_OFF`, `RISK_ON`,
  `GLOBAL_STRESS`, `EUPHORIA`/etc. Unknown label → `(label.title(), "")` (degrade, never crash).
- `_VERDICT_PLAIN: dict[str, str]` — `EXIT → "Consider exiting"`, `TRIM → "Trim back"`,
  `ADD → "Add more"`, `HOLD → "Hold"`, `SWITCH → "Switch"`, `WAIT_FOR_LTCG → "Hold for tax"`.
  Used **only** in NEEDS ATTENTION (holding verdicts like EXIT/TRIM are opaque to newcomers).
  The ideas section shows the **raw** short verdict (`BUY`, `HOLD`) beside its `%` — `BUY` is
  self-evident and reads cleanly as `BUY · 65%`. Unknown verdict → shown raw.

### 4.2 New pure helpers
- `_clean_headline(text: str) -> str` — strip; if the text lacks terminal punctuation
  **and** its last token looks like a truncated word (heuristic: no trailing sentence
  punctuation and length over the cap), cut back to the last complete word boundary and
  append `…`. Also caps at `brief_overnight_maxlen`. Never lengthens; never raises.
- `_dedup_overnight(items, threshold, max_items) -> list` — normalize each headline
  (lowercase, strip punctuation, collapse whitespace); cluster items where one normalized
  string is a prefix of another **or** token-set Jaccard ≥ `threshold`; keep the
  longest (most complete) headline per cluster; return newest-first, capped at `max_items`.
- `_dedup_ipos(rows, max_items) -> list` — dedup by `symbol` (a `current` row beats an
  `upcoming` one); cap at `max_items`.
- `_first_sentence(thesis: str, maxlen: int) -> str` — first sentence (split on `. `),
  trimmed to `maxlen` at a word boundary + `…`. Empty thesis → `""`.
- `_pct(conviction: float) -> str` — `0.654 → "65%"` (round half-up, no decimals).

### 4.3 Enrichment (build-time)
`discovery_adds` rows currently carry only `{event, symbol, detail}`. Enrich each by joining
`ShelfStore().load().ideas` on `symbol` to attach `verdict`, `conviction`, and
`reason = _first_sentence(idea.thesis)`. Idea not found (event older than current shelf) →
keep symbol with `verdict=None` and no reason (renders as a bare bullet). ShelfStore read is
already wrapped non-fatally elsewhere; reuse the same guard.

`_ipo_watch` → include `qib_x`, `retail_x`, `total_x`, `issue_price` from the cache rows
(already present per `services/data/fetchers/ipo.py`), then `_dedup_ipos`.

`_overnight_items` → after reading titles, run `_clean_headline` on each and
`_dedup_overnight`.

### 4.4 `render_brief_text` rewrite
Deterministic assembly of §3 from the (already-built) `brief` dict using the helpers above.
Empty sections are skipped. The header date is formatted `DD Mon YYYY`. Footer is constant.
The SUMMARY is `brief["headline"]` unchanged.

### 4.5 Unchanged
`_narrate_brief` (the single BULK narration call) and `build_morning_brief`'s overall shape,
`run_morning_brief`, delivery, lock-in alerts — all unchanged except the enrichment additions
in §4.3.

## 5. Config additions (`config.yaml` → `delivery.*`; per config-over-hardcode rule)

| Key | Default | Meaning |
|-----|---------|---------|
| `delivery.brief_max_overnight` | `3` | Max overnight items after dedup |
| `delivery.brief_overnight_dedup_threshold` | `0.6` | Jaccard token-similarity for "same story" |
| `delivery.brief_overnight_maxlen` | `240` | Clean-trim cap for a headline |
| `delivery.brief_max_ideas` | `5` | Max ideas shown |
| `delivery.brief_idea_reason_maxlen` | `180` | Cap for the per-idea reason line |
| `delivery.brief_max_ipos` | `3` | Max IPOs after dedup |

Surfaced through `core/config/settings/base.py` (`cfg(...)`) with the existing fallbacks so
prod behaves identically if `config.yaml` is silent.

## 6. Testing plan (`tests/unit/test_delivery_brief.py`)

Existing tests updated for the new render tokens; new tests:
1. **Golden render** — a fully-populated fixture `brief` dict → asserts section headers present,
   correct order, plain-English glosses, `%` formatting, footer.
2. **Overnight dedup** — three near-duplicate RBI headlines → collapses to one (the longest).
3. **Overnight clean-trim** — `"…and strengtheni"` → ends at a word boundary + `…`, no mid-word.
4. **IPO dedup + demand** — LASERPOWER current+upcoming → one row; subscription `×` rendered.
5. **Idea enrichment** — discovery add joined to a shelf idea → `BUY · 65%` + reason from thesis;
   idea missing from shelf → bare bullet, no crash.
6. **Regime gloss** — `RISK_OFF → "Cautious (RISK_OFF) — …"`; unknown label degrades.
7. **Empty auto-hide** — brief with no earnings/ideas/ipos/flags → those headers absent, still valid.
8. Existing `test_overnight_items_read_cache_title_field` and non-trading-day / delivery / deeplink
   tests continue to pass (dedup/clean applied but "Fed shock"/"RBI policy surprise" survive distinct).

Full suite must keep the **known-red baseline fail-set byte-identical** (A/B via worktree).

## 7. Docs update

`docs/ARCHITECTURE.md` §8 "Morning brief" bullet: replace the section list with the new
sectioned layout description and add the ideas-section purpose framing (screen → research
shelf → the tool forms a view → paper-trades to test the thesis). §7 already documents the
pipeline; no change needed there.

## 8. Rollout / risk

- **Reversibility**: pure presentation + read-time dedup/enrichment; no schema or data
  migration; no new external calls. Safe to ship any day (still avoid pushing to main
  16:25–17:15 IST on trading days per the deploy-kill rule).
- **Cost**: zero added LLM cost (helpers are deterministic; the one narration call is unchanged).
- **Failure mode**: every new helper degrades to empty/plain on bad input; `render_brief_text`
  never raises. A missing shelf idea or malformed thesis yields a bare bullet, not a crash.
- **Deploy watch**: first 08:50 IST brief after deploy — confirm sectioned layout, deduped
  overnight, `%` on ideas, IPO demand line.
