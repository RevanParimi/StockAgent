# CLEAN-004 — Remove three things no decision reads: live prompt editing, the daily second AI call, the C++ indicator copy

Priority: **P2** · Scope: **owner decision** of 2026-11-15 ("removing the live prompting anyways
including UI"; "remove if it's no use") · Estimate: **3 points** · Lane: **light** (no buy, sell,
size or grade reads any of the three; the reasons are under each item)

Status lives in [STATE.json](../STATE.json), not this card. No dependency. **Order:** after
[FIX-017](FIX-017.md). (CLEAN-002, which this card used to follow, moved up on 17 Nov 2026.)
[PR-040](PR-040.md) follows this card and edits the same interface files.

**New conversation? Read first:** the evidence note
[CLEAN-003-production-counts-2026-11-15.md](../evidence/CLEAN-003-production-counts-2026-11-15.md)
(sections 3 to 6 and 8), then [CLEAN-003](CLEAN-003.md)'s decision table.

## Rules for this card (as CLEAN-001)

- **Prove unused before deleting.** For each item: every import, string reference, scheduled job,
  route, config key, test and document link, listed in the receipt.
- **One commit per item.** The full suite, `scripts/ci/check_broad_except.py` and
  `scripts/docs/check_kt_docs.py` after each.
- **Do not push or deploy.** A production setting changes only at the owner's word, in a job-free
  window. Stored production files are left where they are.
- Living documents with each item: `docs/PRODUCT_MAP.md`, `docs/TECHNICAL_DESIGN.md` (regenerate
  `docs/StockAgent-Three-Loops.pdf`), `CODEBASE.md`, KT, the testing guide.

## Item 1 — Live prompt editing (the Prompt Lab)

**What it is.** An operator screen where a prompt can be changed and saved. Saving rewrites the
prompt's file on the server and patches the running program, so the next analysis uses it. A
midnight job then pushes the changed files to GitHub, which rebuilds production.

**Why it goes.**

- It has never deployed a prompt: git history holds no commit made by it, and in production the
  GitHub push is not configured (the last run, 14 Nov, was `skipped`).
- It cannot edit the prompt the main analysis uses. Its catalogue lists only the older
  per-analyst prompts, which only the backup analysis reads. That layer is removed by
  [CLEAN-005](CLEAN-005.md).
- A record that can be audited needs prompts to change only through reviewed commits.

**What to remove.**

| Where | What |
|---|---|
| `services/api/routes/prompts.py` | the whole file (six routes under `/ui/prompts`) |
| `services/api/server.py` | the import (line 49) and `app.include_router(prompts_router, ...)` (line 479) |
| `services/scheduler/python/scheduler.py` | the job `prompt_daily_deploy` (registered near line 209) and `_prompt_deploy_job` (near line 1037) |
| `src/frontend/prototypes/` | `prompt-lab.jsx`; its `<script>` tag, `OPERATOR_SCREENS` entry, render line, nav chip and "Open prompt lab" button in `index.html`; the menu entry and comment in `home.jsx`; the cache entry in `sw.js` |
| `tests/unit/test_prompt_file_encoding.py` | delete (it tests the writer being removed) |
| `tests/unit/test_api_auth_lockdown.py` | drop the `/ui/prompts` rows only |
| Documents | `docs/PRODUCT_MAP.md` (job table, line 581, and the screen), `docs/TECHNICAL_DESIGN.md` (job table, line 2804), `CODEBASE.md` |

**Check before deleting.** Whether the watchdog's job registry or `config/milestones.yaml` names
`prompt_daily_deploy`. An edit that removes a registry entry needs the owner's approval for that
edit; do not work around a blocked edit.

**Leave alone.** `data/prompt_changes.json` and `data/prompt_deploy_status.json` on the production
volume (stop writing them; do not delete them). The model caller `prompt_enhancer` is a different
feature and stays.

## Item 2 — The daily second AI call (the control lane)

**What it is.** After each day's review, a bare model is given the same closing price and market
context and predicts the stock's next-session direction. The monthly learning scorecard compares
its hit rate with the product's own daily forecast.

**Why it goes.**

- It has answered its question. In August, September and October 2026 the bare model was right
  more often than the product's forecast, by 15.9, 10.0 and 12.0 points, on about 250 to 370 calls
  a month (evidence note, section 4).
- It costs 425 model calls in 30 days, 9.7% of all calls (section 5).
- Nothing on the buy or sell path reads it: `daily_review.py` step 10 writes it, and
  `core/intelligence/rl/eval/scorecard.py` reads it.
- The owner's second judge is kept where money is decided: [PR-017](PR-017.md)'s `bare` lane asks a
  bare model for BUY or SKIP on each weekly deep dive, at most 20 calls a week.

**Two commits.**

1. **Switch off:** `rl.control_lane_enabled: false` in `config.yaml`. It takes effect in production
   with the next push the owner makes.
2. **Delete:** `core/intelligence/rl/agents/control_lane.py`; its prompt
   `core/config/prompts/shared/control_lane.py`; step 10 of
   `core/intelligence/rl/workflows/daily_review.py` (near line 1716) and the words "control lane"
   in `_GATED_REVIEW_SKIPS` and the paper-lane docstring; the settings `RL_CONTROL_LANE_ENABLED`
   and `CONTROL_LANE_MODEL` (`src/backend/shared/config/settings/base.py`, near line 770) and
   their two `config.yaml` keys; `tests/unit/intelligence/rl/test_control_lane.py`; the references
   in seven other test files and in `scripts/docs/check_kt_docs.py`
   (`git grep -n control_lane`).

**Keep.** The stored control logs (they are the evidence above), and the scorecard's "control LLM"
line reading them: past months stay readable, later months show n 0. That line leaves with the
learning reports ([CLEAN-003](CLEAN-003.md), candidate 2). `preopen_check.py` only mentions the
lane in a comment.

## Item 3 — The C++ copy of the chart indicators

**What it is.** RSI, MACD and Bollinger bands exist twice: in Python, and in a C++ module
(`stockindicators`) that `core/intelligence/algorithms/indicators/fetcher.py` uses when it is
present (`_USE_CPP`, lines 40 to 48, 136, 149, 172).

**Why it goes.** Production does not have the module (measured 15 Nov; the Dockerfile does not
build it), so production always runs the Python code. A compiled copy sits on the owner's laptop
(`core/intelligence/algorithms/indicators/stockindicators.cp313-win_amd64.pyd`, untracked), so
local tests can exercise code production never runs.

**What to remove.** `core/intelligence/algorithms/cpp/` (`CMakeLists.txt`, `build_ext.ps1`,
`src/indicators.cpp`); the `_USE_CPP` import and its three branches in `fetcher.py`; the C++ cases
in `tests/contract/test_phase1_indicators.py`; the Dockerfile's comment about the fallback. Tell
the owner the local `.pyd` can be deleted by hand (it is untracked; do not delete it for them).

**Acceptance for this item.** An indicator test that passes with and without the `.pyd` on the
machine, and gives the same numbers both times.

## Routed input — BACKLOG B-8 (owner's review, 17 Nov 2026)

[B-8](../BACKLOG.md) lists small leftovers that nothing in production imports. While this card is
open, fold in the ones that are as plainly unused as its own three items: the three benchmark
scripts, the stale ignore entries and the pasted line in `docs/README.md`. Each needs the same
proof of non-use. Leave the rest in B-8.

## Not in this card

The backup analysis and the per-analyst prompts ([CLEAN-005](CLEAN-005.md)). The learning writes,
the 30-day price forecast and the monthly learning scorecard ([CLEAN-003](CLEAN-003.md)).

## Handoff

Receipt `evidence/CLEAN-004.md`: per item, the proof of non-use, the commit, the suite result.
Accepted without a fresh-session review when the suite and the guards pass. STATE and HANDOFF
together.
