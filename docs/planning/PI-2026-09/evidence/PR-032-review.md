# PR-032 — fresh review

**Story:** [PR-032](../stories/PR-032.md): industry lenses, first slice. The general path
searches for, and is told, what moves each industry. Implementation receipt:
[PR-032-implementation.md](PR-032-implementation.md). Profit-path step: **invest**.

**Review context: fresh session.** Autopilot `1128-0031-p5` (Opus 5.5 at xhigh), on the
code-server, 28 Nov 2026 from about 00:31 IST, a new conversation opened with "continue". It took
no part in the implementation (`1127-2257-p4`) and read none of that chat. It read the card, the
receipt, the diff, the code it touches and all 25 lens files, and wrote its own cases.

**Verdict: ACCEPTED (code)** for revision `f705a86`. Merged into `main` as **`2db3347`**. Outside
`docs/planning/`, its tree is byte-identical to `f705a86`: `git diff f705a86 2db3347 -- .
':!docs/planning'` is empty. One acceptance criterion, the bench's summary, can only be met in
production: it needs this code deployed and the owner's word. So the story stays **`blocked`**
on `PR-032-B1`, as PR-041 waits on its run. `lenses.enabled` stays `false`, so the merge changes
no query, prompt, buy, sell, size or grade. Nothing was read in production, pushed, deployed, run
or sent.

## Input verified

- Baseline `eb5da62`. Revision `f705a86` on `story/PR-032` (one commit). `main` had moved only by
  the records commit `7f911ef` (planning files only), and the merge was clean.
- `git diff eb5da62 f705a86 | sha256sum` =
  `08458656b73aa2601339dce92aabe2147824e2b5dd85df361865f248d3f2ff89`, as the receipt says
  (45 files, 3,231 insertions, 43 deletions).
- `scripts/docs/kt_manifest.py verify …/PR-032-manifest.json --rev f705a86`: mismatches [],
  review-input SHA-256 `fb25ffbc…8eaf`, as recorded.
- On `2db3347`: `check_kt_docs.py` errors []; the architecture map's `check.py` "match the
  code"; the broad-except guard OK (138 grandfathered).

## Contract checked

Traced in the code at `f705a86` [code inspection]:

1. **Only the general path, and only when the setting is on.** `_lens_and_peers` returns
   (None, None) unless the sector is `"generic"` and `active_lenses()` returns a set. That name
   is the generic orchestrator's class constant. Every key without a native graph resolves to
   that class (`SectorRegistry.get_handler`): a known registry key such as a pharma ticker's,
   the daily review's analyses and the deep dive's. The four native orchestrators pass their own
   names. With the setting off, no fetcher receives a `lens` argument, `_safe` passes no keyword
   arguments, and every line runs as before. That is byte for byte by inspection and by the
   goldens.
2. **One lookup.** With the setting on, `choose_peers` runs once, before the searches, and the
   peers section receives the same `PeerChoice`. `choose_peers` keeps its own profile cache and
   lock, reads nothing another section fills, and never raises. So running it first changes
   neither its result nor the number of Yahoo calls. A failed choice (no industry) is shared
   too, so it is not retried.
3. **Wording.** A written lens supplies the company search's `news_terms`, its own
   `sector_query`, the macro search "India {drivers} economy news {Month} {Year}", and the page
   extract's `policy_query`. The default lens words the sector search from the label and uses
   `DEFAULT_MACRO_QUERY`; its company and page searches are today's. A stock with no label gets
   today's wording except the macro search (decision 4). The label is passed to the template as
   a value and is never parsed as one (RV3).
4. **The block.** `to_prompt_text` puts it in front of the sections after the length cap is
   applied, so the sections keep every character. It is at most 900 characters; the longest
   committed block is 517. Only `UnifiedAnalyst._build_prompt` reads `to_prompt_text`, and it
   passes the bundle to the prompt template as a value. The bare judge (PR-017) reads `sections`,
   not the block, and its own prompt already names the industry. After a switch-on, the
   analysis-against-bare comparison therefore counts the block on the analysis's side, which is
   the difference that comparison exists to measure.
5. **The record and the gate.** `lens` is added to the four search sections' provenance after
   the fetches, including sections that failed. `build_record` keeps each section's provenance
   as it is given. The decision gate builds the same record and reads section statuses and
   dimension counts, never provenance keys. The JSONL and the telemetry table store provenance as
   JSON. So the gate's status and reasons are the same with the setting on and off (RV1).
6. **Loading.** `load_lenses` checks fields, types, list lengths and `id` against the file name.
   It refuses a label in two lenses (case-insensitive) and any placeholder with a format spec or
   a conversion, and it checks the three query fields for "generic". A broken set logs an ERROR
   at startup and keeps today's wording. The loaded set is memoised per folder and newest file
   time. The image copies `config/` to `/app/config/` (Dockerfile `COPY config/ ./config/`,
   `WORKDIR /app`) and `pyyaml` is in `requirements.txt`, so production reads the same 25 files.
7. **Coverage.** `run_discovery_cycle` counts the week's dives whose graph is `"generic"`, by
   each dive's own Yahoo label (B-60), inside its own try. The scheduler logs one line. Nothing
   is written.
8. **Scripts.**
   - `coverage_report.py` reads `dives.jsonl`, the shelf events, the dive memo, the shelf ideas
     and the peer profiles, and writes nothing.
   - `bench.py` without `--yes` calls nothing. With `--yes` it writes only the LLM call log (the
     one side effect of `UnifiedAnalyst.run`), the Tavily month cache, the peer profile cache and
     `/tmp/pr032_bench.json`. It never calls the orchestrator's `analyse`, so it writes no score
     history, verdict-shadow, data-health, shelf or dive record row. Its composite uses
     `SignalAggregator`'s formula: each weighted score rounded to 4 places, the weights
     renormalised over the dimensions that scored. Its private calls `_resolve_ticker(exact=)`
     and `_resolve_weights_for` exist with those signatures.
   - `draft_lens.py` writes only where `--out` says.
9. **The lens files.** All 25 were read. Their labels are Yahoo industry names. None is a label
   FIX-026's table routes to a native graph, and insurance labels run on the generic graph
   (`graph_guess` keeps them out of `banking_bfsi`). The KPIs and drivers are the operating
   numbers these Indian industries are tracked on each quarter. There is no content finding.
   Whether the files cover 80% of real dives is `PR-032-C1`'s read.

## Independent adversarial examples

The reviewer's file is `analysis_data/pr032_review/test_trace_pr032_review.py` (ignored by git).
It was run from the detached worktree's `tests/unit/`, with every expected string typed by hand
from `cement.yaml` and `pharma.yaml`.

| Case | What | Result at `f705a86` |
|---|---|---|
| RV1 | ULTRACEMCO, "Building Materials", setting on, 28 Nov. The four queries match the hand-typed strings ("…latest news results volumes realisation capacity November 2026", "India cement prices demand volumes capacity news November 2026", "India coal petcoke prices housing infrastructure spending diesel freight costs economy news November 2026", "UltraTech Cement Ltd cement volumes realisation EBITDA per tonne capacity expansion 2026"). There is one peer choice, and the text opens with `## INDUSTRY`. The health row, written to a JSONL and read back through `normalize_health_row`, keeps `lens: cement` on the four search sections only. Health, live count, reasons and `essential_unusable` equal the setting-off row's. The decision gate gives the same status and reasons on and off | pass |
| RV2 | SUNPHARMA, "Drug Manufacturers - Specialty & Generic" (the label contains the word): it gets the pharma lens, no query says "generic", and the macro search is "India rupee dollar rate US drug pricing China API prices economy news November 2026" | pass |
| RV3 | The label "  Weird {month} Label  " gets the default lens. It is passed as a value, not parsed as a template ("India Weird {month} Label industry demand prices policy news November 2026"), and the block starts with it | pass |

**The reviewer's planted bugs** (chosen here, not the implementer's 19), each run against the
story's two test files:

- M1: the lens on every path;
- M2: the block inside the cap;
- M3: the peers section looking up again;
- M4: the default macro search naming the graph;
- M5: the lens recorded only on sections that succeeded;
- M6: `policy_query` placeholders left unchecked.

Each run had 1 failing test: 6 of 6 caught.

**The story's tests.** The goldens are typed literally from the code at `eb5da62`: 5 paths × 3
labels, setting on and off. The lens oracle reads the YAML with `yaml.safe_load`, not through the
module, for all 101 labels. `TestOneLookup` drives the real `choose_peers` with a counting Yahoo
stub. Every network transport is a stub.

## Findings

| # | Severity | Where | Finding | Disposition |
|---|---|---|---|---|
| L1 | low | `scripts/lenses/bench.py` `bench_stock` | The bench resolves the ticker but never runs `_prefetch_nse_data`, which `analyse` runs before every bundle. So the bench's bundles lack the NSE context that the fundamentals and peers sections carry in production (`bundle_builder.py` lines 410 and 532). Every arm lacks it equally, so the search comparison (the rule's first part) is unaffected. The block's effect (C − B, the rule's second part) is measured on thinner evidence than production has, where the model may lean more on the block. The error runs toward holding the block back, never toward switching it on wrongly | BACKLOG **B-62**. Trigger: before `PR-032-B1` runs. The fix is one line and a test; otherwise read C − B with this caveat. Named in the B1 row |
| N1 | nit | `config/lenses/README.md`; `lenses.py` `parse_lens` | The README says no field may say "generic", but the parser checks only `news_terms`, `sector_query` and `policy_query`. A `macro_drivers` item containing the word (say "generic drug prices") would load and put it into the macro query. The suite's `TestLensWording` checks all four queries of every committed label, so no committed file can ship with it | none |

There is no critical, high or medium finding. The reviewer agrees with the receipt's F1 to F4
(BACKLOG B-60, B-61) as written.

## Acceptance checklist

- [x] Lookup fixtures for a known label, an unlisted label and no label (`TestLookup`).
- [x] A malformed file or a label in two lenses fails at startup. It fails as an ERROR line with
  today's wording, and the server still starts (decision 3, accepted: a lens file must not stop
  the daily review, and the suite loads the same files, so CI fails first).
- [x] With the setting on, no general-path query says "generic" and each lens query holds the
  lens's words (all 101 labels; RV1, RV2).
- [x] With the setting off, every query on every path is byte for byte today's (goldens;
  inspection).
- [x] The four sector paths are unchanged with the setting on or off.
- [x] No extra network call (`TestOneLookup`; contract 2).
- [x] The block is not essential (`TestBlockIsNotASection`; RV1's gate).
- [ ] The bench summary and the rule's outcome. The bench is built and dry-run on stubs. Its run
  needs this code deployed and the owner's word (`PR-032-B1`), so the story stays `blocked` on
  it.
- [x] Living documents: KT section 4 "Industry lenses", the configuration row and the section 11
  line; testing guide 02-R; `CODEBASE.md`; the lenses design; the architecture map. The PDF is
  not rebuilt (AGENTS.md).

## Commands and results (code-server, `.stockai`, Python 3.13.5)

- Detached worktree at `f705a86`: `pytest -q tests/unit/test_lenses_pr032.py
  tests/unit/test_lens_scripts_pr032.py` gave 221 passed (8.8 s). The reviewer's file gave 3
  passed (1.6 s). With each reviewer mutant, 1 test failed.
- `coverage_report.py` on a 3-dive local fixture (`--base-dir`, `--today 2026-11-28`): general
  path 2, covered 1 (50%); the native dive was counted apart. The target is NOT met (under 30
  dives).
- Full suite through `scripts/ci/guarded_suite.py` on **`2db3347`** (`main`, the merge), 28 Nov,
  00:39–00:58 IST: the main step gave 8,069 passed / 5 skipped / 1 xfailed (6 min 28 s), the
  browser step 61 passed (13 min 10 s); 0 failed, verdict PASS. Anon memory was 800 MB at the
  start, peaked at 1,728 MB in the browser step (the guard stops at 2,400) and was 755 MB
  after; nothing was left running.
- Not exercised: production; real Serper and Tavily results under the lens wording; real Yahoo
  labels (`PR-032-C1`); the model's response to the block (`PR-032-B1`).

## Production

`production_verification`: `pending_deployment` (merged, not pushed). After the deploy:

- `PR-032-C1`, the coverage read: read-only, at the owner's word.
- `PR-032-B1`, the bench: it spends, at the owner's word; fix B-62 first.

Switching `lenses.enabled` on is the owner's word, after B1's rule says B is ready. Read
`PR-043-W2` before that (B-61).

## Decision

**ACCEPTED (code)** for `f705a86`, merged as `2db3347`. PR-032 is `blocked` on its bench
(`PR-032-B1`), the one acceptance criterion that needs production. `review_receipt` and
`reviewed_revision` are recorded. Follow-ups: B-62 (L1); none for N1. Next ready story: **MAP-006**
(light). B-53's trigger was seen at 00:31 IST and made it a story here. PR-044 (decision path)
comes after it.
