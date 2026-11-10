# FIX-026 — fresh review, second pass

**Story:** [FIX-026](../stories/FIX-026.md). **First pass:** [FIX-026-review](FIX-026-review.md) (9 Nov, accepted).
**Implementation:** [FIX-026-implementation](FIX-026-implementation.md).

**Context:** 10 Nov 2026, about 14:30–15:30 IST, session `stockagent-main-09` [1f98f2]. This is the
conversation that wrote the first pass. The owner asked for a stricter pass after switching the model to
Opus 5.5 ("review this session", then "ya try now"). It is the same conversation, not a new one, but the
first pass's conclusions were re-checked rather than reused. Peers `-17` and `-22` were idle while the
records were written.

**Why a second pass.** The first pass did not:
- re-derive the diff digest;
- read the tests' independence;
- re-run the full suite or the mutants;
- trace a case end to end;
- check peer sessions before its bookkeeping.

Meanwhile `-17` committed FIX-026 in `c94dc17` and deployed it on 10 Nov at about 13:20 IST, before this
pass.

**Verdict: acceptance stands** for the deployed code. The pass found one medium (M1) and two lows (L1, L2),
routed to a new card, [FIX-030](../stories/FIX-030.md). None is critical or high. At the owner's word a
bench of three real analyses then measured M1 (see [Bench](#bench-of-m1-owners-word)): the model answered
the sector question every time, so M1 did not occur. The same bench found **M2, medium**: the generic
graph's data bundle carries automobile evidence, and it led the answer to `automobile` for a children's
hospital chain. M2 is routed to FIX-030 too. Saturday 14 Nov's counts are the production check for both.
No production state was read. Nothing was deployed or configured by this pass; the records were committed
and pushed at the owner's word.

## Reviewed input

- **The deployed code is the reviewed code.** Every file in the reviewed manifest
  [FIX-026-manifest.json](FIX-026-manifest.json) (`253620a2`, 25 files) has the same SHA-256 in
  `c94dc17`, except three docs files that FIX-027 also edits (the PDF, the testing guide and the
  technical design).
- **Nothing in FIX-026's code changed after `c94dc17`.** `git diff c94dc17 4d98c76` touches no FIX-026
  code. HEAD is `4d98c76`, the deployed docs commit.
- **The tests ran on the deployed revision only.** Everything ran in three detached git worktrees at
  `4d98c76` in the session scratchpad: suite, mutants and reviewer cases. The shared checkout was never
  used for a test run. Imports were checked to resolve inside each worktree.
- **A mistake in this pass, put right.** `analysis_data/fix026/digest.py` rewrites the tracked manifest.
  Run once on the shared checkout, it changed the manifest (new HEAD, FIX-027's docs edits). The original
  bytes were restored from a copy, and `git status` showed it unchanged.

## Contract re-checked

- **Orchestrators are not shared.** `get_orchestrator` builds a new instance per call
  (`sector_router.py` line 60). The per-run sector question cannot leak into a concurrent analysis.
- **The call uses plain JSON mode.** It is `response_format={"type": "json_object"}`
  (`unified_analyst.py`), not a strict schema, so the extra block is possible. See M1.
- **One road to a buy.** The SWITCH legs and the deployment read only `buy_candidates`' output
  (`core/portfolio/pipeline.py`); an exception there offers none. Promote answers 409 for an unnamed idea.
- **The story tests are independent.** Their expected values are worked by hand from the card. The
  analyst is a stub returning the model's JSON block. The real deep dive, shelf, candidate list, sizing,
  cycle, scheduler job and watchdog run underneath. The tests do not cover a legacy idea with a configured
  key and no reading; that gap is L1.

## Reviewer cases

File `analysis_data/fix026_review2/test_rv_fix026_review2.py` (ignored; run from `tests/unit/`). Every
expected value is worked by hand from the card and the configured settings: shelf 20, 3 per sector,
re-dive after 30 days, stale after 60, 20 dives a week with 2 for IPOs. **12 passed.**

| Case | Kind | What it pins |
|---|---|---|
| RV1 | finding L1 | A key FIX-011's table stored (hospital chain, "Healthcare" to `pharma`) is offered as `pharma`, not due on 14 Nov, due on 12 Dec (35 days, not 5 Dec at 28), kept after a reasoned "generic" answer; the watchdog stays satisfied throughout; only the summary's `kept` names it. |
| RV2 | finding L2 | An idea never named is due first on each of 12 Saturdays (21 Nov to 6 Feb), never rotates (84 days > 60), costs 13 calls, is never offered. |
| RV3 | disclosed limit | A bank answered `it_sector` with `yahoo_fits: true`: the banking graph runs (the guess), `it_sector` is stored, nothing is disputed, the watchdog is satisfied, it is offered as `it_sector`; only the summary's `named` line shows Yahoo's labels beside it. |
| RV4 | contract | A legacy `generic` idea re-dived on 14 Nov as `pharma` (0.72) beside P1 0.80, P2 0.75, P3 0.70: P3 is dropped with the event "sector cap: 4 ideas in pharma, weakest beyond 3 (0.70)", and the re-dive event ends ", sector generic -> pharma". |
| RV5 ×8 | contract | Near misses (`pharma.`, `"pharma"`, `pharma sector`, `pharm`, `IT sector`, `it_sector,tech`, `generic.`, `banking`) are `not_a_key` and store the unnamed placeholder. |

## Findings

| # | Sev | Where | Finding | Disposition |
|---|---|---|---|---|
| M1 | medium; **measured, did not occur (3 of 3)** | `src/backend/sectors/*/prompts/unified.py` (generic line 44; automobile and banking lines 45 and 66; IT 49 and 70; renewable energy 51 and 72) | Every graph's prompt says "no keys beyond the schema below"; the sector question asks for one more top-level block. If the model kept to the rule, every new stock outside the ticker map would be unnamed: never bought, re-dived weekly. The bench's three replies all wrote the block, with a configured key, a reason and a Yahoo view. | FIX-030 keeps only the watch: if Saturday's counts show unnamed dives with "no sector answer" dominating, allow the block in the system prompt when the question is asked. No prompt change otherwise. |
| M2 | medium, **found by the bench** (1 of 1 generic-graph stock) | `services/data/context/bundle_builder.py` `_sector_peer_tickers` (generic: `settings.TICKERS` absent, so the hard-coded MARUTI, TATAMOTORS, M&M, HEROMOTOCO, BAJAJ-AUTO); `services/data/fetchers/mf_herding.py` `get_sector_mf_herding` (no ETF list for `generic`, so automobile's) | The sector answer reads the same bundle as the analysis. A generic-graph company's bundle names automobile peers and automobile ETF flows, so the answer can be `automobile`. RAINBOW (a children's hospital chain) was answered `automobile` with `yahoo_fits: false`; it would be stored, counted in automobile's caps and be buyable, but shown as disputed in the counts line and named by the watchdog. The peers half is SA-044 (todo); the ETF half is in no story. | FIX-030 takes the ETF fallback; SA-044 (peers) runs right before it. Saturday: any non-auto company filed as `automobile` among the disputed dives promotes both ahead of FIX-028. |
| L1 | low | `core/discovery/sector_naming.py` `known_key` | A configured key on an idea with no reading is "earlier", so a key FIX-011's table stored (2–10 Nov) is never re-examined and never flagged. Against the acceptance "no fixed Yahoo-to-key table decides a stored key" for that legacy cohort. | FIX-030. |
| L2 | low | `core/discovery/shelf.py` `redive_due` | An unnamed idea re-dives every Saturday without bound and never goes stale. | FIX-030. |
| — | disclosed (first pass M-1) | `read_answer` | A valid but wrong key with `yahoo_fits: true` passes every rule (RV3). | Unchanged; Saturday's summary is the sample. |

## Commands and results

Environment: `.stockai/Scripts/python.exe` (Python 3.13), Windows. Worktrees at `4d98c76`.

- **Full suite** (`pytest tests -q -p no:cacheprovider`, hermetic): **6,255 passed / 14 skipped /
  1 xfailed / 0 failed**, rc 0, 19m02s (14:34:28–14:53:38 IST). The worktree's `git status` was empty
  before and after. The count is above the implementation's 6,203 because FIX-027's tests are in this
  revision. The main checkout collects the same 6,270. Its run by `-17` reported 6,257 passed and 12
  skipped; the 2 extra skips here are environmental, probably tests that need ignored local data a fresh
  worktree lacks (inference, not read).
- **Implementer's mutants** (`analysis_data/fix026/mutants.py`, run inside a worktree, so the shared
  checkout's files were never edited): **34 of 34 caught**, rc 0. The worktree's `git status` was empty
  before and after, so every mutated file was restored.
- **Reviewer cases:** 12 passed.
- **First pass, unchanged:** focused 292 passed, `check_broad_except` OK (148), manifest verify 0 mismatches.

## Bench of M1 (owner's word)

**Context.** 10 Nov 2026, 20:19–20:26 IST, at the owner's word ("go ahead on the medium"). File
`analysis_data/fix026_bench/bench_sector_answer.py` (ignored). The raw replies are kept beside it in
`bench_2026-11-10_2026IST.json`; they cover public market data only.

**Method.** Three analyses ran exactly as the deep dive runs them (`deep_dive.py` lines 156–163):
`market_classification`, `known_key`, `graph_guess`, the real orchestrator's
`analyse(sym, sector_question=...)`, `read_answer`, `decide_key`.
- **Code and model.** The checkout's code at `4d98c76` with the production model
  (`xiaomi/mimo-v2.6-pro`, JSON mode).
- **Where it ran.** From an empty scratch folder, so the run's relative `data/` and `logs/` writes stayed
  out of the repository.
- **The stocks.** One per prompt family, each outside the ticker map, and each routed by its live Yahoo
  labels to the intended graph.
- **Capture.** A pass-through spy on `UnifiedAnalyst._call_llm` kept each raw reply and where the prompt's
  rule sat.

| Stock | Yahoo | Graph | Rule in prompt | Block written | Answer | `yahoo_fits` | Stored (source) |
|---|---|---|---|---|---|---|---|
| RAINBOW | Healthcare / Medical Care Facilities | generic | system | yes | `automobile` | false | `automobile` (analysis) |
| NEWGEN | Technology / Software - Infrastructure | it_sector | system and user, before the question | yes | `it_sector` | true | `it_sector` (analysis) |
| CREDITACC | Financial Services / Credit Services | banking_bfsi | system and user, before the question | yes | `banking_bfsi` | true | `banking_bfsi` (analysis) |

**Run quality.** Every reply parsed, and every dimension was scored: 8 of 8, 8 of 8 and 6 of 6, with no
legacy fallback.

**Cost.** 9 LLM calls, all successful: 3 ticker resolutions, 3 analyst calls and 3 aggregations. Total
$0.021, about ₹1.9, plus each analysis's usual search-API calls.

**What it shows.**
- **M1.** The model answers the extra block despite the "no keys beyond the schema" rule, in all three
  prompt families. Three calls are a sample, not a rate; Saturday's counts are the production check.
- **M2.** RAINBOW's reply shows where `automobile` came from:
  - The reason reads "Bundle fundamentals and concall describe auto components manufacturing with auto-ETF
    flows and auto OEM peers (Maruti, M&M, Hero, Bajaj)".
  - Its business dimension calls a 22.9% margin "healthy for auto ancillary".
  - Its valuation set a P/E of 44.3 against a "peer median 21.2" of car makers.
  - Its fundamentals are RAINBOW's own (Q2 revenue ₹548 Cr, up 23%), so the company's data was right and
    only the sector evidence was automobile's.

  This affects the verdict too, not only the key: every generic-graph analysis (a discovery dive, or a
  holding under a non-native key in the daily review and monthly forecast) sees the same peers and flows.
  Its frequency is not measured.
- **Incidental.** The ticker map files AAVAS (a housing-finance lender) as `chemicals`. That is for
  [FIX-020](../stories/FIX-020.md)'s map corrections. The bench skipped AAVAS and MANAPPURAM because both
  are in the map.

## Not exercised

- The real LLM beyond the bench's three calls.
- Production state: how many legacy `generic` or table-keyed ideas the shelf holds, and how many holdings
  are `generic`.
- The story tests against the pre-FIX-026 code. They fail there at import (`sector_naming` is absent),
  which proves nothing. The mutants stand in for that check.

## Decision and follow-up state

**Acceptance stands.** STATE: FIX-026 stays `done`, production `pending_observation` (first real run
Saturday 14 Nov). New card [FIX-030](../stories/FIX-030.md), `todo`, after FIX-029, with SA-044 right
before it. Promote both ahead of FIX-028 if Saturday shows either of these:
- non-auto companies filed as `automobile` among the disputed dives (M2);
- most dives unnamed (M1).

The next phase is unchanged: FIX-027's fresh review, in a new conversation.
