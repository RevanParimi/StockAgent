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
  hype.py          NEW  H index over captured P2 features
  verdict.py       NEW  grid, two-horizon outputs, quadrant
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
config.yaml                              MODIFY  ipo.research_*, ipo.deep_dive_*, weights
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

### `IPO-0b` — Size-tiered demand thresholds in `_ipo_lean`

- **Chat opener:** `Work task IPO-0b from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`
- **Size:** ~1 h · **Depends on:** nothing · **Touches:** `core/delivery/brief.py`, `config.yaml`, `src/backend/shared/config/settings/base.py`

**Problem (observed in the live brief, 2026-09-21).** NSE showed `1.1602× overall (QIB 1.52996×, retail 0.722428×)` and was labelled `SOFT DEMAND`. The label is *mechanically correct* — `_ipo_lean` requires all present legs below `soft 2.0×` — but the thresholds are **scale-free**. A ₹50,000cr issue and a ₹500cr SME are judged on one rule, so a mega-issue at 1.16× (an enormous absolute rupee book) reads identically to a small issue nobody bid for.

- [ ] Add to `config.yaml` under `delivery:` — bands are `(min_issue_size_cr, soft_x, strong_total_x, strong_qib_x)`, largest first:

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

- [ ] Add `DELIVERY_BRIEF_IPO_SIZE_TIERS` in `base.py` via `cfg(...)`, **no `env=`**.
- [ ] In `_ipo_lean`, resolve the band from the issue size, then compare. Keep the existing scalar settings as the fallback band when issue size is `None` — an unknown size must not silently become "mega".
- [ ] Tests in `tests/unit/test_delivery_brief.py`:
  - `test_ipo_lean_mega_issue_not_soft_at_low_multiple` — 12,000cr @ total 1.16×, qib 1.53× ⇒ **not** `SOFT DEMAND` (the live NSE case)
  - `test_ipo_lean_small_issue_still_soft_at_same_multiple` — 300cr @ the same multiples ⇒ `SOFT DEMAND`
  - `test_ipo_lean_unknown_size_uses_fallback_band` — size `None` ⇒ today's behaviour, unchanged
- [ ] Run `python -m pytest tests/unit/test_delivery_brief.py -q` before committing.

⚠ **The band values above are judgement, not measurement.** They are chosen to make the 2026-09-21 NSE row read sensibly and nothing more. `IPO-1` produces the first evidence that could calibrate them; until then they carry the same "starting value" caveat the config comment states.

**This is deliberately a throwaway patch.** P3 deletes `_ipo_lean`. It ships because wrong output reaches users every morning until P3 lands, and P3 is several sprints out.

**Acceptance:** the NSE-shaped row no longer reads `SOFT DEMAND`; SME behaviour and the unknown-size path are unchanged; suite green.

### `IPO-0c` — Decide `SERPER_API_KEY_IPO`

- **Chat opener:** `Work task IPO-0c from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`
- **Size:** ~15 min + key provisioning · **Depends on:** nothing · **Decision task, may end in "no"**

- [ ] Read the current month's Serper counter (`data/api_usage.json` / `api_usage_events.jsonl`) and compute remaining headroom against the 2,500/month cap.
- [ ] Decide: provision a dedicated key, or leave GMP dark.
- [ ] If provisioning: set `SERPER_API_KEY_IPO`, flip `ipo.gmp_enabled: true`, confirm a reading appears carrying ≥`ipo.gmp_min_sources` distinct domains.
- [ ] Record the decision and the measured headroom in this plan.

**Why:** GMP is built, tested and dark — a Hype feature P3 wants for free. But `ipo_gmp.py` states plainly that `search_serper` calls `record_call("serper")` **regardless of which key was passed**, so enabling GMP spends from the same counter as the daily pipeline. Measure, don't assume.

**Acceptance:** either GMP readings flow with provenance, or a written, dated decision that it stays dark and `IPO-3a` omits the feature.

---

## Sprint 1 — The evidence gate (by 2026-09-30)

### `IPO-1` — Run and read the P1 backtest report

- **Chat opener:** `Work task IPO-1 from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`
- **Size:** ~half day · **Depends on:** nothing · **Gates:** Sprints 3–5

- [ ] Produce the report from `core/ipo/report.py` over the P1 spine.
- [ ] Record, per horizon (1/5/21/63/126/252 td), whether any captured feature shows measurable separation.
- [ ] Write the decision into the plan: fit weights to measured signal, or ship P3 dark-only.
- [ ] Mark `ipo_p1_backtest_review` satisfied.

**Why this gates P3:** spec §5 P5 conditions the visible flip on a measured hit-rate. Building weights first and measuring after is exactly the failure mode the P1 spine exists to prevent.

⚠ **Honesty requirement.** `report.py`'s own docstring: *"This module measures; it does not model... the honest caveats travel WITH the numbers so a reader cannot pick up the hit-rate without also picking up its limits."* One regime, modest n. A weak result is a real result.

**Acceptance:** a written, dated decision with the numbers behind it.

---

## Sprint 2 — The Substance fetcher (the browsing layer)

This is the half the spec assumes and never built.

### `IPO-2a` — `core/ipo/research.py`

- [ ] Query plan per issue, derived from company name + symbol: financials/RHP, valuation vs peers, promoter/parent track record, anchor book, use of proceeds, risks & litigation.
- [ ] Full-page fetch via `search_tavily` / `fetch_tavily_context`.
- [ ] Per-issue cache keyed `(symbol, close_date)` so a re-run inside one window costs nothing.
- [ ] Hard cap `ipo.research_max_fetches` per issue.

**Budget:** Tavily free tier is 1,000 calls/month. Mainboard IPOs run ~5–15/month and this fires **once per issue at T−1**, so even 10 fetches/issue is ~150/month worst case. This job's rarity is what lets it be far deeper than the daily pipeline.

**Acceptance:** for a known past issue, returns non-empty documents with URLs; returns `[]` (never raises) when Tavily is unconfigured or down.

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

- [ ] Prompt in `core/config/prompts/shared/ipo_extract.py`, `response_format={"type":"json_object"}` + `extra_body=JSON_MODE_EXTRA_BODY`.
- [ ] **State the list caps in the prompt itself** so output length is bounded by construction and a fixed `max_tokens` is genuinely safe.
- [ ] `salvage_truncated_json` on parse failure (the house pattern — see `narrator.py`, `feedback_agent.py`).
- [ ] **Bound the output in the prompt** (cap list lengths) so a fixed `max_tokens` is genuinely safe. Do not rely on raising `max_tokens`; the dossier curator's 15% silent-truncation rate is what that approach looks like in production.
- [ ] Check `finish_reason == "length"` and log truncation distinctly from malformation.

**Acceptance:** a fixture of real fetched pages yields populated fields with sources; a deliberately truncated response degrades to partial-with-provenance, never to invented numbers.

### `IPO-2c` — Corroboration gate

- [ ] `ipo.research_min_sources` (default 2) distinct **domains** per numeric field.
- [ ] `ipo.research_agreement_tolerance` (default 0.25) — wider spread discards the field.
- [ ] Non-numeric fields (promoter name, anchor list) require ≥1 source and are labelled as reported, not verified.

**Why:** this is `ipo_gmp.py`'s rule — *"a single number is treated as a rumour"* — generalised. Scraped financials deserve at least the scepticism already applied to grey-market chatter.

**Acceptance:** two sources agreeing → field kept; two disagreeing beyond tolerance → field `None` with a recorded reason.

### `IPO-2d` — Fixtures and tests

- [ ] Capture real payloads for ≥3 issues (one recent, one mid-window, one older) into `tests/fixtures/`.
- [ ] Tests run fully offline — no network in unit tests.
- [ ] Full suite green.

---

## Sprint 3 — P3, the model (runs dark)

*Step detail added after `IPO-1`.*

| Task | Deliverable |
|---|---|
| `IPO-3a` | `hype.py` — retail ×, retail/QIB skew, cut-off share, demand velocity, GMP (if 0c enabled), news-volume spike, issue size vs sector median |
| `IPO-3b` | `substance.py` — PAT/revenue trajectory, valuation vs peers, **QIB composition** (FII/DomFI/MF sticky-vs-flipper), QIB ×, promoter track record |
| `IPO-3c` | `verdict.py` — the §3 grid (quiet compounder / genuine star / ignore / froth), SHORT and LONG horizons, `H − S` as the de-rating force |
| `IPO-3d` | Verdict store; writes only, surfaces nothing |
| `IPO-3e` | Register `ipo_verdicts_visible_gate` in `config/milestones.yaml` **in the same commit** (watchdog rule) |

⚠ **Spec constraint carried forward:** §3 marks **OFS share as UNVALIDATED** after re-measurement — *"P3 must not weight this feature."* Capture it, render it, do not score it.

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
