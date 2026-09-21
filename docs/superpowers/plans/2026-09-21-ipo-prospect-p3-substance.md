# PI "Prospect" — P3 "Substance" + Deep-Dive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder subscription-multiple lean with the two-index model the spec already defines, and give it the half it has never had — a *Substance* feature set gathered by browsing, not by arithmetic on the bid ladder. The user-facing output is a T−1 deep dive that reads like an informed critic explaining an issue, not a number anyone could read off NSE themselves.

**Architecture:** P2 built the entire **Hype** side from official NSE data — bid ladder with QIB split into FII/DomFI/MutualFund, `cutoff_share`, demand velocity across the window, OFS/fresh split, GMP (dark). Every **Substance** feature in spec §3 — PAT trajectory, revenue CAGR, valuation vs listed peers, promoter track record — has *no fetcher at all*. This plan builds that fetcher (Tavily full-page extraction → LLM structured extraction → corroboration gate), then `hype.py`/`substance.py`/`verdict.py` compute deterministically over the merged feature set. A new `ipo_deep_dive` job sweeps daily and fires only for issues closing tomorrow.

**Tech Stack:** Python 3.13, pydantic v2 schemas, APScheduler (`CronTrigger`, IST), pytest, Tavily via `services/clients/tavily_fetcher.py`, the OpenRouter client via `services/clients/llm_client.py`, `core/utils/atomic_io.py`.

**Spec:** `docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md` — **§3** (the thesis, Hype/Substance/verdict grid), **§5 P3/P5**, **§11** (verified NSE data contract). §3's feature tables are the authority for what H and S contain.

**Prior plans:** `2026-08-12-ipo-prospect-p0-p1.md`, `2026-08-13-ipo-prospect-p2-capture.md`.

---

## State of play as of 2026-09-21 (read before starting)

- **Email delivery is FIXED.** Production logged `[Errno 101] Network is unreachable` on every send from 2026-07-16 (spec `2026-08-24-three-loops-pi-design.md` §15.4, card D6). Cause was Railway disabling outbound SMTP on Hobby. Resolved by upgrading to Pro **and redeploying** — the upgrade alone does nothing to a running container. Verified 2026-09-21: a triggered brief reached the inbox. **D6 is closeable** after a day of clean logs.
- **`outbox.last_error` is deployed** (`590bc9f`). A failed send now records its own reason, so delivery diagnosis no longer requires reading container logs.
- **Email is now per-account.** `resolve_recipient()` routes each outbox row to the address of the account that owns it, falling back to `DELIVERY_EMAIL_TO`. ⚠ Known gap: a *transient* `users.db` lookup failure also falls back, which in multi-user beta could route one user's brief to the owner's inbox. Tighten before real beta users.
- **The IPO lean the user saw is a placeholder**, not a model — `brief.py` says the derived indices stay dark until P3/P5. That complaint is what this plan answers.
- **This plan is design-level for Sprints 3–5 on purpose.** See the scope note below.

## Global Constraints

- **Config over hardcode.** Every tunable goes through `cfg("...")` in `src/backend/shared/config/settings/base.py` with the value in `config.yaml`. Spec §5 P3 is explicit: **all weights via `cfg()`, no `env=`**. The sole secret carve-out is `TAVILY_API_KEY` / `SERPER_API_KEY_IPO`, read with `os.getenv` alongside the other keys.
- **The LLM never decides.** It *extracts* (web text → structured JSON) and it *narrates* (structured findings → prose). H, S and the verdict are computed in Python. A model that both researches and concludes on a financial decision produces confident hallucination; this split is the single most important constraint in this plan.
- **Never raise into delivery.** Every fetcher and brief helper catches broadly and returns a degraded value, matching `logger.warning("[x] ... (non-fatal): %s", exc)`. A dead research feed must never break a morning brief.
- **Dark-signal pattern.** A missing sub-signal is `None`, omitted from rendering, **never defaulted to zero**. This applies with extra force to browsed figures: an unknown PAT is `None`, not `0`.
- **Corroboration before belief.** Any *number* taken from the open web requires agreement between at least `ipo.research_min_sources` distinct domains, within `ipo.research_agreement_tolerance`. This is the rule `ipo_gmp.py` already established for GMP — reused, not reinvented.
- **Provenance travels with every claim.** Each extracted field carries its source URL. A field without a source is discarded, not rendered.
- **No derived value enters the ledger.** The research ledger stores captured facts and their sources. Indices are recomputed at read time. Same discipline as the P1 spine and P2 capture.
- **Research framing.** All user-visible IPO copy stays "the tool's research view — not advice". No output may read as a recommendation to apply. This is a hard line, not a style preference.
- **Verdicts ship dark.** Per spec §5 P5, the dark→visible flip is a `config.yaml` edit **backed by a measured P1 hit-rate**. Research *notes* may surface earlier (they assert only sourced facts); the *verdict* may not.
- **Commit per task**, message style `feat(ipo): ...` / `fix(ipo): ...` / `test(ipo): ...`, ending with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Test discipline.** Run the targeted tests named in each step before that step's commit. Run the full suite where a task says so (~4m).
- **Baseline: 2832 passed, 5 skipped, 0 failed** on `main` @ `590bc9f`. Any failure you see is yours.
- **Windows/OneDrive note.** Prefer append (`"a"`) over rewrite; where a rewrite is unavoidable use `.tmp` + `Path.replace()`. Git in this repo needs `windows.appendAtomically false` (already set locally).
- **Outside pytest**, scripts need `PYTHONPATH=".;src"` on Windows.

---

## Scope note: why Sprints 3–5 are specified at design level only

Sprint 1 (`IPO-1`) reads the P1 backtest report. Spec §5 P5 makes the dark→visible flip conditional on a **measured** hit-rate, which means P1's answer legitimately changes the shape of P3:

- **If P1 shows measurable signal** at one or more horizons → P3 weights are fitted against it and Sprint 5 can flip visible.
- **If P1 shows none** → P3 still ships (the features are real and the capture is valuable), but verdicts stay dark indefinitely and Sprint 5 surfaces *research notes only*.

Writing step-level implementation for Sprints 3–5 before that read would be inventing precision. Those sprints carry full acceptance criteria and file structure here; their step detail is added after `IPO-1`.

---

## File Structure

```
core/ipo/
  research.py      NEW  Tavily query plan + full-page fetch, per-issue cache
  extract.py       NEW  LLM structured extraction + corroboration gate
  substance.py     NEW  S index over browsed + official features
  hype.py          NEW  demand (fitted) + froth (H) over captured P2 features  ✓ IPO-3a
  verdict.py       NEW  grid, two-horizon outputs, quadrant
  verdicts.py      NEW  verdict store (IPO-3d), append-only
  deep_dive.py     NEW  orchestration: gather → research → extract → score → narrate
  signals.py       exists (P2 capture ledger)
  velocity.py      exists (P2 derivations)
  calendar.py      exists (issue-window state machine)
  history.py       exists (P1 spine)
  report.py        exists (P1 measurement)

core/config/prompts/shared/
  ipo_extract.py   NEW  extraction system prompt (JSON-only contract)
  ipo_narrate.py   NEW  narration system prompt (facts-in, prose-out)

services/scheduler/python/scheduler.py   MODIFY  register ipo_deep_dive
config/milestones.yaml                   MODIFY  register ipo_verdicts_visible_gate (Sprint 3)
config.yaml                              MODIFY  ipo.research_*, ipo.deep_dive_*, demand_*/hype_*/substance_* weights+anchors
tests/unit/ipo/                          NEW     fixtures from real captured payloads
```

---

## Sprint 0 — Unblock (do first, independent of everything else)

### `IPO-0a` — Close the lapsed `ipo_p0_live_window_check`

- **Chat opener:** `Work task IPO-0a from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`
- **Size:** ~30 min · **Depends on:** nothing

- [ ] Pick one issue that was **open** during the check window. Confirm in the retained brief/weekly output that it rendered with a real subscription × (not `data pending`) and the correct state heading.
- [ ] Cross-check the same issue's row in `data/ipo/ipo_history.jsonl` and the P2 capture ledger — a brief that rendered correctly while the ledger captured nothing is a **fail**, not a pass (that is precisely what `ipo_signals_accruing` guards).
- [ ] Record the evidence (symbol, date, observed × and state) in the milestone's satisfaction note.
- [ ] Mark `ipo_p0_live_window_check` satisfied in `config/milestones.yaml`.

**Why now:** deadline was 2026-09-15 and it has been LAPSED since, firing a `critical` watchdog alert every 7 days (see `engine.py` `_LAPSED_REPEAT_DAYS`). Live windows exist to verify against — 2026-09-21 had NSE and SONA closing and VARMORA opening 22 Sep.

**Acceptance:** the 06:30 watchdog stops emitting `critical` for this id on its next run.

⚠ Do **not** mark it satisfied on the strength of the brief alone. The brief renders from the refresh; the ledger is a separate write path. Both must show the window.

**Progress 2026-09-21 (afternoon) — not closeable today; closes on the 22 Sep brief.**

- Read `manual_confirmation` in `core/ops/watchdog/checks.py`: it stays `pending` until the
  entry is **removed** from the registry — there is no `satisfied` field. "Mark satisfied"
  below means *delete the entry*, with the evidence in the commit message (precedent:
  `f7a760f`, which closed `f2_validation` the same way).
- Live NSE payload fetched 2026-09-21 14:15 IST (into the scratchpad, not `data/`):
  `NSE` 17–21 Sep, total **3.817×** (QIB 7.81×, retail 1.10×, 14% at cut-off);
  `SONA` 17–21 Sep, total 1.516× (QIB 0.46×, retail 2.14×); `VARMORA` opens 22 Sep.
  Nothing is in the `closed` state today — MANIKA listed today, VEEGALAND on the 18th.
  So the **one remaining check** in the milestone text ("bidding closed — awaiting
  listing" observed *live*) has no subject until tomorrow. Rendering `_ipo_watch` over
  this real payload with `on=2026-09-22` puts VARMORA first (`closes in 2 days`), then
  NSE and SONA under `bidding closed — awaiting listing` with their × intact. That is the
  deterministic re-check, not the live observation; the milestone already had the former.
- Capture write path exercised against the same payload on a scratch ledger: 2 rows
  (NSE, SONA). Proves the code path, **not** production — the real ledger is on the Railway
  volume, which this machine cannot reach (no CLI, no token; `.env` is off-limits).
- **To close on 2026-09-22:** (1) in the 08:50 IST production brief, NSE and SONA must sit
  under `bidding closed — awaiting listing` with real × (not `data pending`) and VARMORA
  under an open heading; (2) ledger evidence — either `ipo_signals_accruing` has emitted
  **no** `pending` alert since NSE/SONA opened on the 17th (the Inbox or
  `GET /delivery/alerts`), or `railway ssh` → `grep -c '"symbol": "NSE"' data/ipo/ipo_signals.jsonl`
  ≥ 1. Then delete the entry, evidence in the commit message.

### `IPO-0b` — Size-tiered demand thresholds in `_ipo_lean`

- **Chat opener:** `Work task IPO-0b from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`
- **Size:** ~1 h · **Depends on:** nothing · **Touches:** `core/delivery/brief.py`, `config.yaml`, `src/backend/shared/config/settings/base.py`

**Problem (observed in the live brief, 2026-09-21).** NSE showed `1.1602× overall (QIB 1.52996×, retail 0.722428×)` and was labelled `SOFT DEMAND`. The label is *mechanically correct* — `_ipo_lean` requires all present legs below `soft 2.0×` — but the thresholds are **scale-free**. A ₹50,000cr issue and a ₹500cr SME are judged on one rule, so a mega-issue at 1.16× (an enormous absolute rupee book) reads identically to a small issue nobody bid for.

- [x] Add to `config.yaml` under `delivery:` — bands are `(min_issue_size_cr, soft_x, strong_total_x, strong_qib_x)`, largest first:

```yaml
  # IPO-0b: demand multiples do not mean the same thing at every issue size.
  # A mega-issue clearing 1.5x is a far larger rupee book than an SME at 30x.
  # STARTING VALUES, not measured — recalibrate against the P1 report (IPO-1).
  brief_ipo_size_tiers:
    - {min_cr: 10000, soft_x: 1.0, strong_total_x: 3.0,  strong_qib_x: 5.0}   # mega
    - {min_cr: 2000,  soft_x: 1.5, strong_total_x: 5.0,  strong_qib_x: 8.0}   # large
    - {min_cr: 500,   soft_x: 2.0, strong_total_x: 10.0, strong_qib_x: 15.0}  # mid
    - {min_cr: 0,     soft_x: 3.0, strong_total_x: 20.0, strong_qib_x: 30.0}  # small
```

- [x] Add `DELIVERY_BRIEF_IPO_SIZE_TIERS` in `base.py` via `cfg(...)`, **no `env=`**.
- [x] In `_ipo_lean`, resolve the band from the issue size, then compare. Keep the existing scalar settings as the fallback band when issue size is `None` — an unknown size must not silently become "mega".
- [x] Tests in `tests/unit/test_delivery_brief.py`:
  - `test_ipo_lean_mega_issue_not_soft_at_low_multiple` — 12,000cr @ total 1.16×, qib 1.53× ⇒ **not** `SOFT DEMAND` (the live NSE case)
  - `test_ipo_lean_small_issue_still_soft_at_same_multiple` — 300cr @ the same multiples ⇒ `SOFT DEMAND`
  - `test_ipo_lean_unknown_size_uses_fallback_band` — size `None` ⇒ today's behaviour, unchanged
- [x] Run `python -m pytest tests/unit/test_delivery_brief.py -q` before committing.

⚠ **The band values above are judgement, not measurement.** They are chosen to make the 2026-09-21 NSE row read sensibly and nothing more. `IPO-1` produces the first evidence that could calibrate them; until then they carry the same "starting value" caveat the config comment states.

**This is deliberately a throwaway patch.** P3 deletes `_ipo_lean`. It ships because wrong output reaches users every morning until P3 lands, and P3 is several sprints out.

**Acceptance:** the NSE-shaped row no longer reads `SOFT DEMAND`; SME behaviour and the unknown-size path are unchanged; suite green.

**Done 2026-09-21.** One widening beyond the listed touches, because without it the
tiers were dead code: live refresh rows carried **no issue size at all** (only the P1
backfill parsed it). The `/api/ipo-detail` body the ladder fetch already pulls carries
`issueInfo`, so `parse_issue_size_cr()` (new, `ipo_offer.py`, sharing `_leg_clauses` with
`parse_offer_split`) reads it there at zero extra calls; `parse_bid_ladder`/`fetch_bid_ladder`
take an optional `issue_price` for share-count legs; `_enrich_open_issues` sets
`issue_size_cr` and `_carry_forward` keeps it on closed rows. Measured on the live
payload: **NSE = ₹22,569 cr** (mega band) → this morning's 1.16×/1.53× reads
`MODERATE DEMAND`, its 14:41 IST book (3.93×/7.99×) reads `STRONG`; **SONA = ₹142 cr**
(small band) stays `SOFT`; VARMORA (unopened) is untouched. `tests/unit`: 2843 passed,
5 skipped; one unrelated Windows cross-process rename flake in `test_portfolio_locking`
passes alone and on a clean tree. The size lands in production on the first refresh
after deploy — the 08:00 IST job — so the 22 Sep 08:50 brief is the first one to show it.

### `IPO-0c` — Decide `SERPER_API_KEY_IPO`

- **Chat opener:** `Work task IPO-0c from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`
- **Size:** ~15 min + key provisioning · **Depends on:** nothing · **Decision task, may end in "no"**

- [ ] Read the current month's Serper counter (`data/api_usage.json` / `api_usage_events.jsonl`) and compute remaining headroom against the 2,500/month cap.
- [ ] Decide: provision a dedicated key, or leave GMP dark.
- [ ] If provisioning: set `SERPER_API_KEY_IPO`, flip `ipo.gmp_enabled: true`, confirm a reading appears carrying ≥`ipo.gmp_min_sources` distinct domains.
- [ ] Record the decision and the measured headroom in this plan.

**Why:** GMP is built, tested and dark — a Hype feature P3 wants for free. But `ipo_gmp.py` states plainly that `search_serper` calls `record_call("serper")` **regardless of which key was passed**, so enabling GMP spends from the same counter as the daily pipeline. Measure, don't assume.

**Acceptance:** either GMP readings flow with provenance, or a written, dated decision that it stays dark and `IPO-3a` omits the feature.

**Progress 2026-09-21 — blocked on the production counter; and GMP is built but NOT wired.**

- The counter (`data/logs/api_usage.json`) lives on the Railway volume. No HTTP route exposes it
  (only the watchdog reads `get_usage()`, in-process), and this machine has no Railway access. It
  needs one of: `railway ssh` → `cat data/logs/api_usage.json`; the deploy log's boot line
  `[api_usage] counter intact at boot ... serper=N/2500`; or the serper.dev dashboard's credit count.
- **Finding that changes the task:** `fetch_gmp()` has **no production caller**. Only
  `tests/unit/test_ipo_gmp.py` calls it. `core/ipo/signals.py` declares `gmp` / `gmp_pct` /
  `gmp_sources` but nothing fills them. Setting the key and flipping `ipo.gmp_enabled` would produce
  **no reading** — the third checkbox cannot pass as written. If the decision is "provision", it
  also needs a one-line call from the P2 capture path (one fetch per open issue per refresh) and a
  test that the flag off still means zero calls.
- **Volume, if wired that way:** 1 Serper call per open mainboard issue per daily refresh. 2025 had
  99 mainboard listings in the spine (~8/month), each open ~3 days → ~25 issue-days/month → **~25
  calls/month, ~1% of the 2,500 cap**; double it if the T−1 deep dive also fetches. Headroom is
  therefore about the main pipeline's own consumption, not GMP's — which is why the counter still
  has to be read before deciding.

---

## Sprint 1 — The evidence gate (by 2026-09-30)

### `IPO-1` — Run and read the P1 backtest report

- **Chat opener:** `Work task IPO-1 from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`
- **Size:** ~half day · **Depends on:** nothing · **Gates:** Sprints 3–5

- [x] Produce the report from `core/ipo/report.py` over the P1 spine.
- [x] Record, per horizon (1/5/21/63/126/252 td), whether any captured feature shows measurable separation.
- [x] Write the decision into the plan: fit weights to measured signal, or ship P3 dark-only.
- [x] Mark `ipo_p1_backtest_review` satisfied (entry removed — `manual_confirmation` has no satisfied state; precedent `f7a760f`).

**Why this gates P3:** spec §5 P5 conditions the visible flip on a measured hit-rate. Building weights first and measuring after is exactly the failure mode the P1 spine exists to prevent.

⚠ **Honesty requirement.** `report.py`'s own docstring: *"This module measures; it does not model... the honest caveats travel WITH the numbers so a reader cannot pick up the hit-rate without also picking up its limits."* One regime, modest n. A weak result is a real result.

**Acceptance:** a written, dated decision with the numbers behind it.

**Read 2026-09-21 — decision: fit the SHORT horizon to demand, ship the LONG horizon dark, never weight OFS.**

Spine: the local `data/ipo/ipo_history.jsonl` (P1 backfill of 2026-08-18; 209 rows, 188 graded,
listings 2024-05-13 → 2026-08-14). `report.py` slices only 1 td and 252 td by total ×, so the
per-horizon read below was done in a scratch script over the same rows — measurement only, no
fitting. Spearman ρ against the raw feature with a 2,000-draw permutation p; terciles are equal-n
thirds of the feature. Returns are % vs issue price; the `excess` (minus `^NSEI`) table is within
±1pp of every cell below and changes no reading, so only `outcomes` is quoted.

| feature | td | n | ρ | p | lo-tercile mean / pos | hi-tercile mean / pos |
|---|---|---|---|---|---|---|
| **qib_x** | 1 | 185 | **+0.66** | <0.001 | −3.0% / 38% | **+37.6% / 94%** |
| qib_x | 5 | 183 | +0.61 | <0.001 | −2.9% / 36% | +40.3% / 90% |
| qib_x | 21 | 179 | +0.44 | <0.001 | +1.4% / 42% | +35.9% / 82% |
| qib_x | 63 | 175 | +0.33 | <0.001 | +3.4% / 48% | +32.0% / 76% |
| qib_x | 126 | 157 | +0.33 | <0.001 | −1.5% / 38% | +35.9% / 77% |
| qib_x | 252 | 77 | +0.23 | 0.048 | +13.1% / 44% | +44.7% / 69% |
| **total_x** | 1 | 185 | **+0.64** | <0.001 | −3.1% / 33% | **+36.0% / 94%** |
| total_x | 5 | 183 | +0.58 | <0.001 | −3.1% / 34% | +39.2% / 92% |
| total_x | 21 | 179 | +0.40 | <0.001 | +1.6% / 42% | +35.3% / 80% |
| total_x | 63 | 175 | +0.28 | 0.002 | +4.1% / 48% | +34.0% / 75% |
| total_x | 126 | 157 | +0.31 | <0.001 | −2.0% / 40% | +37.4% / 75% |
| total_x | 252 | 77 | +0.14 | 0.205 | +17.2% / 52% | +39.9% / 69% |
| retail_x | 1 | 185 | +0.49 | <0.001 | +0.4% / 43% | +30.6% / 85% |
| retail_x | 5 | 183 | +0.43 | <0.001 | +0.1% / 46% | +31.0% / 80% |
| retail_x | 21 | 179 | +0.26 | <0.001 | +4.8% / 53% | +26.4% / 70% |
| retail_x | 63 | 175 | +0.16 | 0.032 | +6.4% / 57% | +26.7% / 68% |
| retail_x | 126 | 157 | +0.18 | 0.027 | +7.8% / 48% | +28.4% / 68% |
| retail_x | 252 | 77 | +0.08 | 0.493 | +15.5% / 48% | +28.2% / 62% |
| ofs_share | 1 | 170 | +0.15 | 0.064 | +14.6% / 64% | +20.6% / 72% |
| ofs_share | 5 | 168 | +0.14 | 0.063 | +16.4% / 64% | +21.5% / 70% |
| ofs_share | 21 | 164 | +0.12 | 0.137 | +14.1% / 46% | +18.9% / 69% |
| ofs_share | 63 | 160 | +0.16 | 0.043 | +11.5% / 51% | +18.8% / 69% |
| ofs_share | 126 | 142 | +0.15 | 0.075 | +12.9% / 51% | +21.0% / 67% |
| ofs_share | 252 | 69 | **−0.03** | 0.839 | +38.9% / 61% | +28.8% / 70% |

`report.py`'s own buckets, same rows: hot (≥10×) n=118 mean +26.4% / 85% positive on listing day;
warm (2–10×) n=39 −0.5% / 46%; cold (<2×) n=28 −4.2% / 25%. The hot cohort's positive rate decays
85% → 82% → 73% → 69% → 66% → 63% across 1/5/21/63/126/252 td while its mean holds near +25%: the
pop is retained on average but by an ever-thinner majority.

**What the numbers say, per feature:**

1. **Final subscription demand is a real, strong, monotone predictor of the listing-day outcome,
   and QIB × is the best single reading of it.** ρ ≈ 0.65 at 1 td, terciles separate cleanly
   (−3% → +15% → +37%; positive rate 33% → 94%), and the effect is not a two-bucket artefact — the
   middle tercile sits where it should. It decays with horizon but stays significant through 126 td
   (ρ ≈ 0.3). This is the measured hit-rate spec §5 P5 asks for: **hi-tercile demand → 94% positive
   listing-day, n=62.**
2. **At 252 td the evidence is thin and borderline.** n=77, and 62 of the 80 matured rows are 2024
   listings — one regime, one year, overlapping windows. QIB × scrapes p=0.048; total × and retail ×
   do not. Nothing here supports a LONG-horizon verdict.
3. **Retail × is the weakest demand reading** at every horizon and fades to noise by 63 td. In P3
   it is a *Hype* input (froth), not a return predictor, and the data agrees: it separates the
   listing pop less well than the institutional book does.
4. **OFS share: no signal.** ρ ≈ 0.15, p between 0.04 and 0.14 across short horizons, sign flips at
   252 td. This is the third measurement (2026-08-15, 2026-08-18, today) and the third time it has
   failed to hold. §3's UNVALIDATED marking stands; `IPO-3a`/`3b` capture and render it, never
   score it.

**The caveat that shapes P3 more than any number above.** The spine holds *final* subscription —
known at close of day 3, i.e. before listing but after the retail application window. `IPO-4a`
fires at **T−1** on day-2 evening figures, and QIBs bid overwhelmingly on the final day. So:

- A **listing-day lean issued after the book closes** (the SHORT verdict in its natural slot:
  "closed — awaiting listing") is backed by this evidence directly.
- A **T−1 apply-or-not lean** is *not* — its inputs are day-2 demand and `velocity.py`'s
  ramp, which the spine cannot see. That can only be validated forward from the P2 capture
  (`ipo_signals.jsonl`, live since 2026-08-13). Do not let the 94% figure be quoted for it.

**Decision (2026-09-21):**

- **`IPO-3a` (Hype):** weight `qib_x` ≥ `total_x` > `retail_x` for the SHORT horizon; fit to 1–5 td
  on this spine. Retail-vs-QIB skew and cut-off share enter as froth modifiers, unweighted for return
  until P2 rows mature. GMP only if `IPO-0c` wires it (see that task — it is not wired today).
- **`IPO-3b` (Substance):** builds and captures; **no weight on historical evidence** — none exists
  for PAT, revenue, valuation or promoter record, and the report says so in its own caveats.
- **`IPO-3c` (verdict):** SHORT verdict may be fitted; **LONG verdict ships dark indefinitely**
  until 252-td rows from a second regime accrue.
- **`IPO-5b`:** the visible flip is admissible for the **post-close listing-day lean only**, gated on
  a forward hit-rate from the P2 capture matching the historical one, not on this backtest alone.
  The T−1 lean stays dark; `IPO-5a` research notes ship regardless.
- OFS: captured, rendered, never scored. Unchanged.

Re-run the read when the production spine (Railway volume) is pulled — it carries ~5 weeks of
listings the local copy does not, though none can have matured past 21 td yet, so the short-horizon
reading above is what would move, and only marginally.

---

## Sprint 2 — The Substance fetcher (the browsing layer)

This is the half the spec assumes and never built.

### `IPO-2a` — `core/ipo/research.py`

- [x] Query plan per issue, derived from company name + symbol: financials/RHP, valuation vs peers, promoter/parent track record, anchor book, use of proceeds, risks & litigation.
- [x] Full-page fetch via `search_tavily` / `fetch_tavily_context`.
- [x] Per-issue cache keyed `(symbol, close_date)` so a re-run inside one window costs nothing.
- [x] Hard cap `ipo.research_max_fetches` per issue.

**Budget:** Tavily free tier is 1,000 calls/month. Mainboard IPOs run ~5–15/month and this fires **once per issue at T−1**, so even 10 fetches/issue is ~150/month worst case. This job's rarity is what lets it be far deeper than the daily pipeline.

**Acceptance:** for a known past issue, returns non-empty documents with URLs; returns `[]` (never raises) when Tavily is unconfigured or down.

**Done 2026-09-21** (`e8abda3`). Measured on the live plan: 6 fetches → 14–16 documents / 12–16 domains per issue (NSE, VARMORA, LEAP). Two rules beyond the checklist: documents are **deduped by URL across queries** so the plan itself cannot inflate a corroboration count, and an **empty result is never cached** so a Tavily outage at 19:00 cannot poison the window. Bare `NSE`-style symbols are not appended to the query (they swamp results); the legal suffix is stripped from the name.

### `IPO-2b` — `core/ipo/extract.py` — structured extraction

- **Chat opener:** `Work task IPO-2b from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`
- **Depends on:** `IPO-2a`

The schema every extracted field conforms to — a bare value is never accepted:

```python
class Sourced(BaseModel):
    """One extracted claim. `value` is None when the documents did not say."""
    value: float | str | None = None
    source_url: str | None = None      # required whenever value is not None
    as_of: str | None = None           # ISO date the figure describes

class IpoSubstance(BaseModel):
    revenue_cr:      list[Sourced] = []   # up to 3 disclosed years, oldest first
    pat_cr:          list[Sourced] = []   # same ordering as revenue_cr
    ebitda_margin:   Sourced = Sourced()
    issue_pe:        Sourced = Sourced()
    peer_pe:         list[Sourced] = []   # cap: ipo.research_max_peers
    promoter:        Sourced = Sourced()
    parent_track:    Sourced = Sourced()
    anchor_names:    list[Sourced] = []   # cap: ipo.research_max_anchors
    use_of_proceeds: list[Sourced] = []   # cap: ipo.research_max_proceeds
    red_flags:       list[Sourced] = []   # cap: ipo.research_max_flags
```

- [x] Prompt in `core/config/prompts/shared/ipo_extract.py`, `response_format={"type":"json_object"}` + `extra_body=JSON_MODE_EXTRA_BODY`.
- [x] **State the list caps in the prompt itself** so output length is bounded by construction and a fixed `max_tokens` is genuinely safe.
- [x] `salvage_truncated_json` on parse failure (the house pattern — see `narrator.py`, `feedback_agent.py`). ⚠ It cuts only at **object-valued** top-level keys; this schema's top-level values are lists and scalars, so it salvaged zero keys in testing. `salvage_partial_object()` in `extract.py` is the shape-aware fallback; the house helper is still tried first.
- [x] **Bound the output in the prompt** (cap list lengths) so a fixed `max_tokens` is genuinely safe. Do not rely on raising `max_tokens`; the dossier curator's 15% silent-truncation rate is what that approach looks like in production.
- [x] Check `finish_reason == "length"` and log truncation distinctly from malformation.

**Acceptance:** a fixture of real fetched pages yields populated fields with sources; a deliberately truncated response degrades to partial-with-provenance, never to invented numbers.

**Done 2026-09-21** (`c8e54c2`). Design decision worth keeping: extraction is **per document**, and the code stamps the document URL onto every claim — the model is never asked for a URL, so provenance holds by construction (`Sourced` refuses a value without one). Measured on 45 real pages: max completion **264 tokens** against the 900 cap. `Sourced` grew `status` (`corroborated` / `reported`), `sources` (every agreeing URL) and `label` (peer name); `IpoSubstance` grew `docs_read` / `docs_extracted` / `docs_truncated` / `dropped` so a thin result explains itself.

### `IPO-2c` — Corroboration gate

- [x] `ipo.research_min_sources` (default 2) distinct **domains** per numeric field.
- [x] `ipo.research_agreement_tolerance` (default 0.25) — wider spread discards the field.
- [x] Non-numeric fields (promoter name, anchor list) require ≥1 source and are labelled as reported, not verified.

**Why:** this is `ipo_gmp.py`'s rule — *"a single number is treated as a rumour"* — generalised. Scraped financials deserve at least the scepticism already applied to grey-market chatter.

**Acceptance:** two sources agreeing → field kept; two disagreeing beyond tolerance → field `None` with a recorded reason.

**Done 2026-09-21** (in `c8e54c2`). The NSE capture is the case this rule exists for: "NSE" is ambiguous on the open web and sources gave FY25 revenue of ₹1,039cr vs ₹16,352cr and PAT of −₹50cr vs ₹8,406cr. The gate kept **none** of it, recorded each disagreement in `dropped`, and kept the 35.4× P/E two domains agreed on. Series corroborate **per fiscal year** (FY25 / FY2025 / 2024-25 / March 2025 → `FY2025`); peers per name. Consequence for `IPO-3b`: **peer P/E will rarely corroborate** from the open web (VARMORA's four peers all came from one blog) — expect `peer_pe` to be empty more often than not, and do not let S depend on it.

### `IPO-2d` — Fixtures and tests

- [x] Capture real payloads for ≥3 issues (one recent, one mid-window, one older) into `tests/fixtures/`. → `tests/fixtures/ipo_research/`: NSE (closed 21 Sep), VARMORA (opens 22 Sep), LEAP (listed 14 Aug); dossiers **and** the recorded bulk-model responses per page.
- [x] Tests run fully offline — no network in unit tests. The replay client **raises** on any prompt not in the recording.
- [x] Full suite green — 2904 passed, 5 skipped, 0 failed (2026-09-21).

**Done 2026-09-21.** 60 tests in `tests/unit/ipo/`. Cost of the capture: 18 Tavily calls + 45 bulk-model calls, once.

---

## Sprint 3 — P3, the model (runs dark)

*Step detail written 2026-09-21, after the `IPO-1` read. Every design choice below traces to that read.*

| Task | Deliverable |
|---|---|
| `IPO-3a` | `hype.py` — retail ×, retail/QIB skew, cut-off share, demand velocity, GMP (if 0c enabled), news-volume spike, issue size vs sector median |
| `IPO-3b` | `substance.py` — PAT/revenue trajectory, valuation vs peers, **QIB composition** (FII/DomFI/MF sticky-vs-flipper), QIB ×, promoter track record |
| `IPO-3c` | `verdict.py` — the §3 grid (quiet compounder / genuine star / ignore / froth), SHORT and LONG horizons, `H − S` as the de-rating force |
| `IPO-3d` | Verdict store; writes only, surfaces nothing |
| `IPO-3e` | Register `ipo_verdicts_visible_gate` in `config/milestones.yaml` **in the same commit** (watchdog rule) |

⚠ **Spec constraint carried forward:** §3 marks **OFS share as UNVALIDATED** after re-measurement — *"P3 must not weight this feature."* Capture it, render it, do not score it.

**Shape of the model, fixed by the `IPO-1` read.** One scoring primitive for every index: each feature maps to
0–1 by a piecewise-linear curve **on a log scale** through `(p10 → 0, p50 → 0.5, p90 → 1)`, clipped; an index
is the weight-renormalised mean over the features present, ×100; an index resting on less than
`ipo.index_min_coverage` (0.5) of its weight is `None`. Anchors and weights live in `config.yaml`, each anchor
labelled **fitted** (read off the P1 spine, dated) or **UNFITTED** (no spine column exists — stated, not
disguised). Dark features stay `None`, are listed in `dark`, and never default to zero.

### `IPO-3a` — `core/ipo/hype.py`

- **Chat opener:** `Work task IPO-3a from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`
- **Size:** ~2 h · **Depends on:** `IPO-1` · **Touches:** `core/ipo/hype.py`, `config.yaml`, `base.py`, `tests/unit/test_ipo_hype.py`

- [x] Two readings, kept apart because they carry different evidence: **`demand`** (fitted, the SHORT input —
      `qib_x 0.5 ≥ total_x 0.3 > retail_x 0.2`, anchors = spine p10/p50/p90) and **`froth`** (H proper —
      `retail_x`, `retail_qib_skew`, `cutoff_share`, `gmp_pct`; no return evidence, none claimed).
- [x] Features from the **last ledger snapshot carrying a total** (`velocity.final_demand_snapshot`) plus the
      NSE cache row for issue size / OFS share. QIB composition (`fii_x`, `dom_fi_x`, `mutual_fund_x`), NII,
      `demand_delta`, `issue_size_cr`, `news_volume` and `ofs_share` are **captured, never scored** here —
      composition is a Substance feature (`IPO-3b`); OFS is UNVALIDATED; size-vs-sector-median has no sector
      for an unlisted issue and stays dark until one exists.
- [x] `retail_qib_skew` is `None` when the QIB book is `0.0` — a real reading with an undefined ratio, not infinity.
- [x] Config: `ipo.demand_weights`, `ipo.demand_anchors`, `ipo.hype_weights`, `ipo.hype_anchors`,
      `ipo.index_min_coverage`; `base.py` fallbacks are **empty** so a missing block yields a dark reading,
      not a hidden model. No `env=`.
- [x] `read_hype()` never raises; a failure returns a reading with every scored feature dark.
- [x] Tests offline: `tests/unit/test_ipo_hype.py` (18).

**Done 2026-09-21.** Fit measured on the local spine (188 graded, 185 with a book), scratch script, not committed:

| anchor | p10 | p50 | p90 | status |
|---|---|---|---|---|
| `qib_x` | 1.76 | 40.35 | 207.34 | fitted |
| `total_x` | 1.57 | 30.57 | 133.76 | fitted |
| `retail_x` | 0.96 | 8.93 | 72.49 | fitted |
| `retail_qib_skew` | 0.04 | 0.28 | 1.23 | fitted |
| `cutoff_share` | 0.10 | 0.25 | 0.50 | UNFITTED — no spine column; NSE 14%, MOLBIO 46% |
| `gmp_pct` | 0.02 | 0.15 | 0.50 | UNFITTED — never captured |

The `demand` composite over those anchors, terciles by score, `outcomes` at 1 td: **lo −3.1% / 33% positive,
mid +12.6% / 74%, hi +38.5% / 95%** (n = 61/62/62); Spearman ρ 0.66 at 1 td, 0.59 at 5 td, i.e. it reproduces
`qib_x` alone and adds nothing — which is the point: a composite that *beat* its best input on the same
sample would be overfit. `demand ≥ 70` (n=76): +35.1% / 92%; `demand ≤ 30` (n=62): −3.0% / 34%. Reproduced
with the production `config.yaml` through `read_hype()` itself, not only the scratch script. Live check: the
NSE book (3.817× / QIB 7.81× / retail 1.10× / 14% cut-off) reads **demand 17, froth 17** — a huge absolute
book, a thin multiple, no froth. The IPO-0b placeholder called that "SOFT DEMAND"; this says the same thing
with a number that has a hit-rate behind it.

### `IPO-3b` — `core/ipo/substance.py`

- **Size:** ~3 h · **Depends on:** `IPO-2b/2c` (the `IpoSubstance` shape), `IPO-3a` (the scoring primitive)

- [ ] Inputs: the corroborated `IpoSubstance` (browsed) **and** the ledger snapshot (official — QIB ×,
      QIB composition). Two provenance classes, both recorded on the reading.
- [ ] Features: `pat_trend` (sign and slope of the ≤3-year PAT series; a loss-making trajectory scores 0,
      not `None`), `revenue_cagr`, `issue_pe_vs_peers` (`issue_pe / median(peer_pe)` — **expect it dark
      most of the time**, per the IPO-2c finding; `S` must not depend on it), `qib_x`, `sticky_share`
      (`(fii + dom_fi + mutual_fund) / qib` from the ladder), `promoter_track` (categorical → 0/0.5/1 only
      when `status == "corroborated"`, else dark).
- [ ] **No fitted anchors exist** — the spine has no Substance column. Every anchor is UNFITTED and labelled
      so in `config.yaml`; weights are *equal* across present features until evidence says otherwise. The
      reading carries `fitted: False` so `verdict.py` and the narrator cannot present S with the confidence
      of `demand`.
- [ ] Same primitive: `score_index` from `hype.py`, `ipo.substance_weights`, `ipo.substance_anchors`,
      coverage gate.
- [ ] Never raises. Tests offline over `tests/fixtures/ipo_research/*_extractions.json` + synthetic ledger rows.

### `IPO-3c` — `core/ipo/verdict.py`

- **Size:** ~2 h · **Depends on:** `IPO-3a`, `IPO-3b`

- [ ] `IpoVerdict` = `{symbol, close_date, as_of, short: {lean, band, basis}, long: {lean=None, basis},
      quadrant, hype, substance, demand, dark: [...]}`.
- [ ] **SHORT** from `demand` only (the fitted reading): `≥ ipo.short_strong` → strong / `≤ ipo.short_weak`
      → weak / else mixed, thresholds default 70 / 30 with the spine hit-rates quoted in the `basis` string
      (92% / 34%). `froth` **modifies the band, not the lean** — high froth widens the stated pop band and
      adds the de-rating caution.
- [ ] **LONG ships dark**: `lean` is always `None`; `basis` records `H − S` and the quadrant so the
      reasoning is captured, but no direction is asserted. Flipping this is a `config.yaml` edit gated on
      252-td rows from a second regime — not a code change.
- [ ] **Quadrant** from `froth` × `substance` against `ipo.quadrant_high` (50): quiet compounder / genuine
      star / ignore / froth. `None` when either side is `None` — no quadrant from one axis.
- [ ] Pure function; tests cover all four quadrants, the dark cases, and that `ofs_share` never changes an output.

### `IPO-3d` — Verdict store

- [ ] `core/ipo/verdicts.py`: JSONL at `data/ipo/ipo_verdicts.jsonl`, keyed `(symbol, close_date)`,
      **append-only** (a re-fire on an extended close date is a new row, not an overwrite), `guard_lossless_rewrite`
      on any prune. Stores the verdict **and** the feature/component dicts it was computed from, so a later
      anchor change can be replayed against what was known.
- [ ] Writes only. No reader outside tests and the watchdog until `IPO-5b`.

### `IPO-3e` — Milestone

- [ ] `ipo_verdicts_visible_gate` (`manual_confirmation`) registered **in the `IPO-3d` commit**. Deadline:
      the earlier of 60 days of forward P2 rows or 2026-12-31. Action text states the gate: forward hit-rate
      from the P2 capture on the post-close listing-day lean matching the historical 92% / 34%.

---

## Sprint 4 — The scheduler job and narration

*Step detail added after `IPO-1`.*

| Task | Deliverable |
|---|---|
| `IPO-4a` | `ipo_deep_dive` — daily sweep **19:00 IST**, fires only for issues where `close_date − today == 1` |
| `IPO-4b` | Narrator — the explainer, written from structured findings **only**, deterministic fallback on LLM failure |
| `IPO-4c` | Audit integration — extend `Lane` with `"ipo"`, `entry_close` carries the **issue price** (documented at the schema, not silently overloaded), horizons 1/5/21/63/126/252 td |

⚠ **Spec drift, verified 2026-09-21.** §5 P5 quotes `Lane = Literal["advice", "alert", "shelf"]`. It is now `["advice", "alert", "shelf", "switch"]` — `switch` was added after the spec was written. The resolution is unchanged (append `"ipo"`), but do not treat the spec's list as current.

**Why 19:00 IST:** the NSE bid update lands at 17:00 and the existing live refresh runs 17:45. Running after it means the analysis sees day-2 evening subscription; running at T−1 leaves the user the entire final day to act.

**Why a daily sweep, not a per-IPO scheduled job:** close dates get extended. A dynamically scheduled job rots silently; a daily "who closes tomorrow?" query cannot. The ledger key includes `close_date`, so an extension re-fires a fresh analysis rather than being deduped away.

**Concurrency:** cap per sweep (mirroring `ipo.max_ladder_fetches`) so a day with five closings cannot exhaust the research budget in one run.

---

## Sprint 5 — Surface (gated)

| Task | Deliverable | Gate |
|---|---|---|
| `IPO-5a` | Research notes in brief/weekly — sourced facts, no verdict claim | none; safe to ship |
| `IPO-5b` | Verdict + quadrant visible | **measured P1 hit-rate only** |

`IPO-5a` ships the explainer content — what the business does, financial trajectory, valuation vs peers, who took anchor, red flags, subscription composition — all sourced. That is genuinely the informed-critic output, and it asserts nothing predictive.

`IPO-5b` asserts skill and must earn it, per spec §5 P5.

---

## Definition of done

- Sprint 0 complete; `ipo_p0_live_window_check` no longer lapsed.
- `IPO-1` decision written and dated; `ipo_p1_backtest_review` satisfied.
- A T−1 deep dive runs unattended for a real issue and produces a sourced, structured analysis.
- No browsed number reaches a user without ≥2 agreeing domains and a source URL.
- Verdicts write to their store and surface nowhere until the gate is passed.
- Full suite green; no pre-existing failure "fixed" along the way.

---

## Deliberately NOT in this plan

- **SME issues, global markets, unlisted/pre-IPO tracking** — spec §8 non-goals, unchanged.
- **Allotment, application or brokerage integration** — §8.
- **Intraday listing-day price prediction** — §8.
- **P4 convergence tracker** — separate phase; the 365-day post-listing entry-window detector is the most actionable output in the PI but runs on bhavcopy already on disk and does not depend on this work.
- **Anything in PI-2026-09 (Three Loops).** That PI has zero IPO scope (`grep -ic "ipo" STATE.json` → 0). IPO work is tracked here, under PI "Prospect". `IPO-0b` in particular is *not* a D-workstream card.
- **Replacing `ipo_tracker.py`'s discovery-candidate role** — §8.
