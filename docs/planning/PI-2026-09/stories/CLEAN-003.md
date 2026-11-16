# CLEAN-003 — Remove the learning writes and the 30-day price forecast; settle the operator extras

(Until the evening of 15 Nov 2026 this card was "Switch off and remove what the goal does not
need". The owner has since decided every item; what was quick to remove left for
[CLEAN-004](CLEAN-004.md) and [CLEAN-005](CLEAN-005.md), and the sector prompts for
[CLEAN-006](CLEAN-006.md). This card keeps the two large removals.)

Priority: **P2** · Scope: **owner decision** of 2026-11-15 (edge roadmap, section 8) · Estimate:
**3 points** for steps 1 and 2; each removal is sized when the owner approves it · Lane: **light**
for the inventory; a removal that touches an input a buy, sell or size reads is on the **decision
path**

Status lives in [STATE.json](../STATE.json), not this card. No dependency. **Order:** after
[PR-008](PR-008.md).

**New conversation? Read first:** [EDGE-ROADMAP.md](../EDGE-ROADMAP.md) sections 1 to 3, 6 and 8.

## Why

The owner, 15 Nov 2026: build what contributes to the end goal, "not building something as if
adding stuff because they were already there or looks good". The product grew from a sector
analyst that forecast a 30-day price path and learned from grading it. The goal is now: research,
invest, sell on evidence, prove it against the Nifty. Parts of the older idea still run every day.
Each costs model calls, scheduled jobs, code to keep correct and attention in every review.

The owner's rule (the CLEAN-001 brief, 13 Nov): these are **decisions for the owner, not
deletions**. This card measures, asks, and only then removes.

## Step 1 — measure each candidate (read-only)

**Since the evening of 15 Nov** rows 1, 4 and 6 and the C++ part of row 7 are decided and have left
this card: [CLEAN-004](CLEAN-004.md) and [CLEAN-005](CLEAN-005.md). Row 5 is not a candidate. This
card now covers rows 2, 3, the rest of 7, 8 and 9. See "The decisions" below.

For each row: which code on the profit path reads it (grep, with the lines), how many model calls
and scheduled jobs it costs a month (the LLM call log and `atlas_cost_rollup`), and how often it
ran or was used in production (counts only, at the owner's word).

| # | Candidate | What was seen on 15 Nov (code inspection) |
|---|---|---|
| 1 | The control lane | `rl.control_lane_enabled: true`; a second reasoning-tier call per reviewed stock per day (`core/intelligence/rl/agents/control_lane.py`), read by the monthly learning scorecard only |
| 2 | Learning writes in the daily review | FeedbackAgent lessons, WeightAdapter proposals, ledger propagation, lesson emphasis, month-end seasonal validation, the eval and learning-evidence reports (`core/intelligence/rl/`). Learning is observe-only, so none changes a decision |
| 3 | The 30-day price path | The monthly forecast, its daily grading, thesis reviews and re-forecasts. After [PR-015](PR-015.md) only ADD, TRIM and SWITCH read it (`core/portfolio/advisor.py`) |
| 4 | The legacy worker pool | The analysis's fallback path (`src/backend/shared/pipeline/graphs/`, `base_agent.py`, `services/data/context/builder.py`); engagements are counted in `fallback_events.py` |
| 5 | ~~The IPO intelligence lane~~ **not a candidate (owner, 15 Nov)** | The owner wants IPO buy-or-skip analysis in the morning brief. Two of its jobs (`ipo_refresh_am`, `ipo_refresh_pm`) already feed the brief's IPO facts and its demand-based lean (`core/delivery/brief.py` `_ipo_lean`). The deeper verdict (`ipo_deep_dive`, 19:00) is hidden on purpose until the watchdog milestone `ipo_verdicts_visible_gate` is judged (60 days of forward rows, or 31 Dec 2026) |
| 6 | Live prompt editing | The Prompt Lab routes (`services/api/routes/prompts.py`) and the midnight job `prompt_daily_deploy` |
| 7 | Old or duplicated inputs | `factor_regime.py` (a prior ending March 2023), the C++ indicators beside their Python copy, mutual-fund herding and seasonal patterns that cover four sectors only |
| 8 | Four native sector graphs beside the generic one | Decide from [PR-017](PR-017.md)'s split by graph, not before |
| 9 | Operator extras | The analytics OData feed, agent-weight tuning, the Tweaks panel, the Learn page |

## The owner's first answers (15 Nov 2026)

Given in conversation about 11:30 IST, before any measurement. **The evening's decisions, in the
next section, replace these where they differ.**

| # | Candidate | The owner's answer | What follows |
|---|---|---|---|
| 1 | The control lane | "I thought it is there to have a 2nd judge, and in future we can decide between these 2." | The owner is right about its purpose. It is a bare model that gets the same information and predicts each stock's next-day direction, so the product's forecast can be compared with it. It judges the **daily price forecast**, not a buy or a sell. **Keep the second judge; move it to where money is decided:** [PR-017](PR-017.md) adds a bare model's verdict on each weekly deep dive. The daily duel goes only when the price forecast goes (candidate 3) |
| 2 | Learning writes | "It comes after the 1st point." | Agreed: decided together with candidates 1 and 3 |
| 3 | The 30-day price path | "I don't think it is needed unless it adds any value." | Measure its value first (does ADD, TRIM or SWITCH do better with it?). Retire it if it adds none, after those three decisions read the written case (PR-005) |
| 4 | The legacy worker pool | Asked whether it is good or bad | Both. Good: an analysis still arrives when the main call fails. Bad: it comes from an older, cheaper method and is treated the same. Measure how often it runs; if rarely, replace it with "no analysis today" |
| 5 | The IPO lane | Wants IPO buy-or-skip analysis in the morning brief | Not a candidate. Next step for it is judging `ipo_verdicts_visible_gate` |
| 6 | Live prompt editing | Asked for an example | Saving a prompt on the Prompt Lab screen changes the very next analysis, with no test and no review; at midnight a job pushes the change to GitHub, which rebuilds production. Recommendation stands: switch it off, change prompts by reviewed commits. **The owner has not yet answered** |
| 7 | Old or duplicated inputs | Asked what they are | The factor table ending March 2023 is read only by the frozen learner's weight step (`weight_adapter.py`), so it goes with candidate 2. The C++ indicators are a second copy of the Python ones. Mutual-fund herding and seasonal patterns cover only the four original sectors, so they go with candidate 8 |
| 8 | Four native sector graphs | "Don't think it's needed... but make sure we don't lose anything good." | Agreed in principle. Before removal: PR-017's results by graph, then a list of what each sector graph knows that the generic one does not (for example monthly vehicle sales, raw-material prices, RBI policy, US demand for IT), and each item that helped is carried into the generic graph as an optional add-on (the paused SA-026, "sector lenses") |

## The decisions (15 Nov 2026, evening), after production counts

The owner asked for production logs and for "a firm remove or keep decision" on each item. One
read-only probe was run; its counts are in
[CLEAN-003-production-counts-2026-11-15.md](../evidence/CLEAN-003-production-counts-2026-11-15.md).
Rows marked **owner** are the owner's words. Rows marked **delegated** are the firm calls the owner
asked this conversation to make. **The owner approved all of them the same evening: "go ahead with
the recommendations, I like it."**

| # | Item | Decision | By | The evidence in one line | Where it happens |
|---|---|---|---|---|---|
| 1a | The daily second AI call | **Remove** | delegated | It did its job: the bare model beat the product's daily forecast by 10 to 16 points in Aug, Sep and Oct. 425 calls in 30 days. No buy or sell reads it | [CLEAN-004](CLEAN-004.md) item 2 |
| 1b | A second judge on each weekly buy idea | **Keep** | delegated | At most 20 calls a week, on the decision that spends money, where nothing has been compared yet | [PR-017](PR-017.md) lane `bare` |
| 2 | Learning writes (lessons, weight proposals, the learning reports) | **Remove** | delegated | The learner is frozen. `FeedbackAgent` alone is 465 calls and 20% of all tokens in 30 days | This card, steps 1 to 3, after the two conditions below |
| 3 | The 30-day price forecast, its daily grading and re-forecasts | **Remove** | delegated (owner: "not needed unless it adds any value") | Its direction calls were below a bare model for three months and far below "same as yesterday" | This card, after the two conditions below |
| 4 | The backup analysis and the old per-analyst layer | **Remove** | owner | Ran 21 times in about 1,360 analyses (1.5%), all in October. Model failures already alert | [CLEAN-005](CLEAN-005.md) |
| 5 | The IPO lane | **Keep** | owner | The owner wants IPO buy-or-skip in the morning brief | Judge `ipo_verdicts_visible_gate` by 31 Dec 2026 |
| 6 | Live prompt editing, with its screen | **Remove** | owner | Never deployed a prompt; cannot edit the prompt the main analysis uses | [CLEAN-004](CLEAN-004.md) item 1 |
| 7a | The C++ indicator copy | **Remove** | owner ("remove if it's no use") | Production does not have it | [CLEAN-004](CLEAN-004.md) item 3 |
| 7b | The market-factor table ending March 2023 | **Remove** | owner | Read only by the frozen learner and the backup's data builder | With item 2 and CLEAN-005 |
| 7c | The four-sector seasonal calendar | **Remove** | owner | Read by the monthly forecast, the daily review and the month-end validation | With item 3 |
| 7d | The mutual-fund lists for four sectors | **Decide with item 8** | delegated | Part of the sector paths; the call returns data | With item 8 |
| 8 | The four sector prompts of the main analysis | **Keep until the 8-week review, then merge into one path unless they have earned their place** | delegated | They cost no extra call and their data calls work (93% to 100%). Whether they pick better stocks is not measured | Rule below; [PR-032](PR-032.md) first; the merge is [CLEAN-006](CLEAN-006.md), paused |
| 9 | Operator extras (analytics feed, weight tuning, Tweaks panel, Learn page) | Not asked yet | — | — | Step 1 of this card |

**The rule for item 8, written in advance.** At `PR-014-R2` (8 weeks after the switch-on), read
PR-017's results by path. The four sector prompts stay only if BUY ideas from the sector paths beat
BUY ideas from the general path by 2 points or more of mean excess return at 30 sessions, with 30
or more ideas on each side. Otherwise they are merged into the general path by
[CLEAN-006](CLEAN-006.md), and what each sector prompt knows that the general one does not is
carried over as a lens file per sector (PR-032's format, from the adopted lenses design; SA-026).
If there are too few ideas to judge at `PR-014-R2`, look again each month; with
[PR-032](PR-032.md) done and still no proof by the third look, merge. Until then nothing about the
five prompts changes: the first weeks of the book are measured on one unchanged method.

**What the owner asked about PR-017.** It compares how ideas did against the Nifty, split four
ways: ideas the product bought, ideas it rejected, stocks the screen found but nobody researched,
and a bare model's BUYs. It also splits the product's ideas by path (sector or general). Production
logs show a call worked; only this comparison shows whether it picked better stocks.

## What items 2 and 3 are made of (starting points, 15 Nov 2026)

Code inspection, not exhaustive: step 1 proves the full list. Calls are production, last 30 days.

**Item 2, the learning writes.** Production runs them as observe-only: lessons and weight proposals
are written and nothing reads them back into a score.

| Part | Where | Cost | Known readers |
|---|---|---|---|
| `FeedbackAgent`: grades the day's forecast row and writes lessons | `core/intelligence/rl/agents/feedback_agent.py`, called by the daily review | 465 calls, 20.0% of all tokens | The lesson emphasis, which is off in observe mode. Its grading half belongs to item 3 |
| `WeightAdapter`: proposes new weights | `core/intelligence/rl/agents/weight_adapter.py` | no model call seen | In observe mode it writes `{TICKER}_weight_observations.json` only |
| The market-factor table ending March 2023 | `core/intelligence/rl/algorithms/factor_regime.py` | none | `weight_adapter.py`, `daily_review.py`, and the backup's data builder (removed by CLEAN-005) |
| Ledger propagation and lesson emphasis | `daily_review.py`; `rl.lesson_emphasis_delta`, `rl.lesson_emphasis_cap` | none | — |
| The learning reports | `core/intelligence/rl/eval/` (harness, learning evidence, the monthly scorecard and its job `scorecard_monthly`) | none seen | The owner, monthly. The scorecard also holds the control lane's history |

**One hazard to close first.** `config.yaml` still says `rl.learning_mode: adapt`. Production is
observe-only because the owner set the Railway variable `RL_LEARNING_MODE=observe` on 26 Sep 2026.
If that variable were lost, production would go back to adapting weights without anyone deciding
it. Step 3 starts by making `observe` the file's value.

**Item 3, the 30-day price forecast.**

| Part | Where | Cost | Known readers |
|---|---|---|---|
| The monthly forecast | `core/intelligence/rl/workflows/generate_forecast.py`; job `rl_monthly_forecast`; the startup self-heal | part of the 605 analysis calls | Everything below |
| Daily grading of the forecast path | `core/intelligence/rl/workflows/daily_review.py` (job `rl_daily_review`, 16:30), `review_outcomes.py` | with `FeedbackAgent` above | The legacy exit rule `thesis_break`; the monthly scorecard |
| Thesis reviews and re-forecasts | `core/intelligence/rl/agents/thesis_reviewer.py`; the caller `price_interpolator` | 359 and 86 calls | The forecast itself |
| The four-sector seasonal calendar | `core/intelligence/seasonal/`; `month_end_validation.py` | none | `generate_forecast.py`, `daily_review.py` |
| What the advisor takes from the forecast | `core/portfolio/advisor.py`: `envelope_direction`, `confidence` (mean remaining forecast confidence), `reforecast_reason`, `forecast_gate` | — | ADD, TRIM, SWITCH and the legacy exit rule |
| What the user sees of it | the forecast chart on a stock's page, lines in the digest | — | the user |

**The 16:30 daily review itself stays.** It also runs the advisor and the autopilot. Only its
forecast and learning steps go.

**Not yet placed:** `macro_reviewer` (90 calls) and `preopen_check` (20 calls). Step 1 says which
item, if either, they belong to.

## Step 2 — plan the removals of items 2 and 3

One table for the owner: what each part costs, what reads it, one plain example of what is lost by
removing it, and the order of removal. Two conditions are already known:

- candidates 2 and 3 wait until the evidence rule has acted for a month (PR-009's card: the
  thesis-review exit path is retired then);
- candidate 3 also needs ADD, TRIM and SWITCH to read the written case ([PR-005](PR-005.md)) in
  place of the price path. That is a card of its own, on the decision path.

## Step 3 — remove what the owner approved

- **First, with no behaviour change in production:** set `rl.learning_mode: observe` in
  `config.yaml`. Tests that assume `adapt` set it themselves.
- **Switch off first** (a setting), delete later. One commit per item.
- Delete only after 4 weeks switched off with nothing missed.
- Proof of non-use in the receipt, as CLEAN-001 did: every import, string reference, job, route,
  document link.
- The full suite, `check_broad_except` and `check_kt_docs` after each item.
- A production setting changes only at the owner's word, in a job-free window.

## Stays

Screen, deep dive, shelf, buy candidates, deployment, sizing, stops and evidence exits, costs,
auditor, scorecard, the company-event feed, the dossier, the regime label, brief and digest,
accounts and the two data planes, backups and the watchdog.

## Handoff

Receipt `evidence/CLEAN-003.md`: the measured table, the owner's answers, and what was switched off
or removed with its proof.
