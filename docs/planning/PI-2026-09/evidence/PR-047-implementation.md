# PR-047 — implementation receipt, step 2 (option A)

**Story:** [PR-047](../stories/PR-047.md): buy what the analysis itself would buy. Origin: [the
B-32 read](B-32-read-2026-11-21.md) (21 Nov 2026). Profit-path step: **invest** (what is bought).
Step 1, the measure for option B and the staged entry, is [its own receipt](PR-047-step1.md); its
read is `PR-047-S1`.

**Lane: decision path.** Reason: it changes what is bought at every buy door (AGENTS.md step 4).
**Status after this phase: `review_required`.** The next fresh conversation performs the hard
review from `REVIEW.md`; this phase's self-review does not count as it.

## Phase

- **Implementation**, two sessions on the code-server: autopilot `1126-1852-p6` (26 Nov, about
  18:52–19:00 IST, stopped at a usage limit after `be33dec`, the WIP that keeps the model's verdict
  on the report, the dive, the idea and the dive record) and autopilot `1126-1901-p7` (Opus, 26
  Nov, from about 22:05 IST, outside a push window), which rebased the branch on `main` and
  finished it.
- **Baseline `f06e3dc`** (`main`, 12 commits ahead of `origin/main` `53461ab`). The code is on
  **`story/PR-047`**: **`f69e2a5`** (the WIP, rebased) and **`8541b37`** (the rule, the legacy
  read, tests and docs). **Revision for review: `8541b37`.** Only a fresh review's acceptance
  merges it into `main`.
- Production: nothing read, pushed, deployed, run or sent. The records commit on `main` is
  documentation only.

## What the card said, checked against the code [code inspection]

1. **The band decides.** Confirmed: `SignalAggregator.run` logs the model's verdict to
   `verdict_shadow.jsonl`, then, with `rl.hard_bind_verdict_enabled` (on in `config.yaml`),
   replaces `report.verdict` with `verdict_from_composite(composite)`. The model's verdict was
   kept nowhere else.
2. **Every door read only that verdict.** Confirmed: `shelf.verdict_wait` (FIX-029) read
   `idea.verdict`; it is called by the shelf's add and re-dive, `buy_candidates`, a SWITCH leg
   (`_execute_buys`) and idle-cash deployment (`_deploy_check`). The watchlist door read the
   score history's `verdict` column (the bound verdict).
3. **A top-up is another matter.** `ADD` comes from the advisor's forecast path (envelope UP,
   regime, weight, accuracy), not a verdict. Left as it is; the card's buys are new positions.

## What was built [code]

1. **The model's verdict is kept** (`be33dec`, rebased as `f69e2a5`): `FinalReport.model_verdict`
   (set in `SignalAggregator.run` from the raw verdict, before the bind, bound or not; a reply
   that does not parse is the parser's NEUTRAL); `DeepDiveResult.model_verdict` (from the
   report); `ShelfIdea.model_verdict` (from the dive, refreshed by a re-dive); the dive record's
   row (`model_verdict`). The score history stores it inside `report_json`; no column or
   migration.
2. **One rule, both verdicts** (`shelf.verdict_wait`): the band, read exactly as FIX-029 read it
   (`band_verdict`: stripped, upper case), and the model's own verdict (`plain_verdict`: upper
   case, single spaces, an underscore read as a space) must each be BUY or STRONG BUY. A missing
   model verdict refuses. Words: "its deep dive's own verdict is NEUTRAL, not a BUY (the
   composite's band says BUY)"; "its deep dive kept no verdict of the model's own; waits for its
   re-dive"; for a watchlist idea "… waits for a new analysis". Deployment's outcome stays
   `verdict` ("not rated a BUY by the analysis").
3. **The watchlist door** (`candidates.watchlist_idea`): after the band check, the model's
   verdict from the stored report (`_model_verdict`); none (an analysis made before PR-047)
   refuses with "latest analysis kept no verdict of the model's own; waits for a new analysis";
   another refuses with "latest analysis's own verdict is NEUTRAL, not a BUY (the composite's band
   says BUY)". The idea it builds carries `model_verdict`, so deployment's and a SWITCH leg's own
   check passes it.
4. **Ideas shelved before PR-047** (`shelf.py`): `shadow_rows(path)` reads `verdict_shadow.jsonl`
   once and answers the rows of an IST day and the next; `model_verdict_from_shadow` takes the
   rows of the idea's symbol whose `llm_final_score` is its conviction to 4 decimals and whose band
   is its band, and answers their model verdict only when all agree;
   `with_model_verdicts` gives copies with it filled. It **fails closed**: no row, rows that
   disagree, or a log that cannot be read leave "" and the idea is refused.
   - The daily review reads the shelf through it after `with_history_identity`
     (`core/portfolio/pipeline.py`), so from the first review after the deploy a legacy idea the
     model did not rate a BUY is refused and one it did is bought as before.
   - The weekly run calls `ShelfStore.verify_model_verdicts()` after `verify_analyses()`
     (`hygiene.model_verdicts`): a BUY is stamped on the shelf; any other verdict drops the idea
     with "its deep dive's own verdict is NEUTRAL, not a BUY (the composite's band says BUY); deep
     dive of 2026-11-14, read from the verdict-shadow log" (its dive memo entry kept: the dive was
     of the stock and its answer stands); one it cannot tell stays.
   - `redive_due` counts an idea with no model verdict as unverified, so it is re-dived before the
     stale ones.
5. **Reported:** the shelf's summary lists `not_buy_model` (band BUY, model not) beside `not_buy`;
   the deep dive's log line names `model=`.

### The 13–18 Nov buys under the new rule [inference from the B-32 read, not re-read]

TVSMOTOR (₹3.19 L, 16 Nov; band BUY, model NEUTRAL at its dive) would have been refused at the
shelf. The other nine had a model BUY as far as the B-32 read shows. Whether TVSMOTOR's idea still
stands on the shelf today was not read (production is read only at the owner's word); if it does,
the first review after the deploy refuses it and the next Saturday's run drops it.

## Tests [local]

New file `tests/unit/test_model_verdict_pr047.py`, 168 cases. Every expected figure is worked by
hand from the fixture's numbers.

| Invariant | What it checks |
|---|---|
| A1, every door | Over 35 (band, model) pairs: the shelf's add (and `not_buy_model`), a re-dive (refreshed or dropped), the list, deployment (66 shares at ₹1,000 of ₹10 L), a SWITCH leg, the watchlist (36 with a pre-PR-047 report). The expected set is a hand-written table of 8 pairs |
| A1, watchlist through deployment | A watchlist idea offered with the model's BUY is bought by deployment's own re-check |
| A2, only refuses | 2,000 random ideas over band spellings (`strong_buy`, `" buy "`, double spaces) and model verdicts: whatever the new rule takes, FIX-029's rule (written in the test) took |
| A3, issue time | The real aggregator: bound, the verdict is the band's BUY and `model_verdict` NEUTRAL; unbound both NEUTRAL; an unparseable reply NEUTRAL. TVSMOTOR's case through the real aggregator, `run_deep_dives`, the dive record and the shelf (refused, `not_buy_model`). The shelf file keeps it; a pre-PR-047 `shelf.json` loads with "" and is refused; the real score store's `report_json` carries NEUTRAL to the watchlist door |
| A4, legacy ideas | The dive's own row only: 11 cases (`.NS` suffix, a run crossing midnight, another stock, day, score, band; two agreeing rows; two disagreeing; none), with a half-written last line. A row the real aggregator wrote is found. An unreadable log and a missing one fail closed; an idea with its own verdict and a watchlist idea are not read. The real pipeline's first review: model NEUTRAL or no row buys nothing, BUY buys 66 as before. The weekly check drops, stamps, leaves and is idempotent; `redive_due` puts the unknown first; the real weekly cycle drops before choosing re-dives |

**Mutants:** 17 of 17 killed by this file (the rule ignoring the model; an unknown model passing;
the shadow read taking any row, ignoring the next day, the band or the score; the watchlist door
ignoring the model; the aggregator keeping the bound verdict; the re-dive, the shelf add or the
deep dive dropping the field; the daily review or the weekly run skipping the read; `redive_due`
ignoring it; the check keeping a NEUTRAL idea; no underscore reading; the band read widened).

**Older tests:** the rule fails closed, so fixtures that build an idea, a dive, a fake analysis
or a score row as a BUY now say the model's BUY too: 20 files, `model_verdict="BUY"` beside each
literal `verdict="BUY"` and in the builders (`pr004.dive`, `pr004._idea`, `pr004.record`,
`sa049._idea`, the fake analysts). No expected figure changed. Before that, 198 of the 1,442 tests
in the 41 affected files failed, every one for the missing model verdict.

Commands (code-server, `.stockai`, Python 3.13.5):

- `.stockai/bin/python -m pytest -q tests/unit/test_model_verdict_pr047.py`: 168 passed.
- The 41 files that build ideas, dives or score rows: 1,442 passed.
- Full suite through `scripts/ci/guarded_suite.py` on `8541b37`: 26 Nov, 22:24–22:33 IST, 7,163 passed /
  5 skipped / 1 xfailed in the main step and 58 passed in the browser step, 0 failed; peak anon
  2,084 MB in the browser step (the guard stops at 2,400), back to 1,350 MB after; nothing left
  running.
- `scripts/docs/check_kt_docs.py`: errors [].

## Documentation

KT (`docs/TECHNICAL_DESIGN.md`): section 3's `rl.hard_bind_verdict_enabled` row; section 4, step
6 (the model's verdict kept on the report); section 6, the buy candidates' verdict bullet (both
verdicts, the TVSMOTOR example, the legacy read, the watchlist, ADD unchanged); section 8, shelf
upkeep (`verify_model_verdicts`), the re-dive queue, the re-dive drop and the new dive
(`not_buy_model`, the dive record). `docs/AUTOPILOT_GUIDE.md` (the candidates, the executor's
check, the test table). `CODEBASE.md` (`shelf.py`, `deep_dive.py`, `dive_record.py`,
`candidates.py`). Human testing case **07-W** (`docs/TEAM_TESTING_GUIDE.md`). The PDF is not
rebuilt (AGENTS.md). KT section 12 keeps the card "Open" until its review.

## Review input

- `git diff f06e3dc 8541b37 | sha256sum` =
  `301a7715869216b414b0ed8e0367ecb1b75315d573f0e234807d790e36035fe4` (33 files, 859 insertions,
  88 deletions).
- Manifest [PR-047-manifest.json](PR-047-manifest.json): 33 files, git blob and SHA-256 per file at
  `8541b37`; review-input SHA-256 `cd10c97c6d219e1c9ed0e62dd28c600bee971ca2b4b5f5a5811d978bf0dc5913`;
  `kt_manifest.py verify … --rev 8541b37`: mismatches [].

## Open limitations, for the reviewer

1. **Shadow matching can fail to tell** (fails closed): a dive whose score and band equal another
   analysis of the same stock that day or the next with a different model verdict, or a dive run
   whose ticker in the log is another company's. Such an idea waits for its re-dive (first in the
   queue). The cost is buys delayed by up to a week, never a buy against the rule.
2. **Re-dive budget:** legacy ideas the log cannot tell take re-dive slots first. How many there
   are is not known without a production read; the weekly run reports them
   (`hygiene.model_verdicts.unverified`).
3. **The watchlist waits for a new analysis** where its latest predates PR-047; a stock in the
   daily review gets one the same evening, one on a weekly cadence within a week. No shadow read
   for it (chosen: the cost is small and the code smaller).
4. **Fewer buys.** The book was 20.8% invested on 20 Nov for lack of ideas; this rule refuses
   more. The owner chose it knowing so (card, "The decision"). How many it refuses shows in
   `not_buy_model`, the digests' `verdict` outcomes and `PR-047-W1`.
5. **The model's verdict is free text.** The prompt asks for STRONG BUY, BUY, NEUTRAL, SELL or
   STRONG SELL; case, spaces and underscores are read through, any other wording refuses.

## Production watch (after the deploy, read at the owner's word)

`PR-047-W1`: the first 16:30 review after the deploy: no idea bought whose model verdict (on the
idea, or in `verdict_shadow.jsonl` for its dive) is not a BUY; the run log's "not offered" and the
digest's `verdict` outcomes name any refused. The first Saturday after: `hygiene.model_verdicts`
(dropped, verified, unverified) and the shelf summary's `not_buy_model`.

## Choices taken in this phase (CLAUDE.md section 2)

- Rebased `story/PR-047` on `main` (local, unpushed) so the review reads one line of history.
- The band is read exactly as before and only the model's verdict is normalized, so the rule can
  only refuse (A2 and mutant 17 hold it).
- Legacy ideas: the shadow log rather than a re-dive of every idea (which would spend the week's
  budget) or a pass for unknown ones (which would buy against the rule). Unanimity, not the
  earliest row, because the live rule must fail closed; step 1's measure took the earliest.
- A legacy idea the model did not rate a BUY is dropped, as a new dive of that kind takes no slot;
  its dive memo is kept.
- The watchlist reads only the stored report (limitation 3).
