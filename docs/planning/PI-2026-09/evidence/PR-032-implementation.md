# PR-032 — implementation receipt

**Story:** [PR-032](../stories/PR-032.md): industry lenses, first slice. The general path searches
for, and is told, what moves each industry. Profit-path step: **invest** (the evidence a buy's
conviction is computed from). Design: section 4.1 of
[the lenses design](../../../superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md), in
SA-026's file shape (SA-026 stays paused).

**Lane: decision path.** Reason: once switched on it changes the inputs the conviction is computed
from (the card's own lane; AGENTS.md step 4). **Status after this phase: `review_required`.** The
next fresh conversation performs the hard review from `REVIEW.md`; this phase's self-review does
not count as it.

## Phase

- **Implementation**, autopilot `1127-2257-p4` on the code-server (Opus at xhigh), 27 Nov 2026,
  from about 22:57 IST to about 00:15 IST on 28 Nov.
- **Baseline `eb5da62`** (`main`, 7 commits ahead of `origin/main` `69e7c28`). The code is on
  **`story/PR-032`**: **`f705a86`** (one commit). **Revision for review: `f705a86`.** Only a fresh review's acceptance merges it into
  `main`. The records commit on `main` is documentation only.
- Production: nothing read, pushed, deployed, run or sent. `lenses.enabled` ships **off**, so a
  deploy of this code changes no query, prompt, buy, sell, size or grade.

## In one example

- **Today:** a cement maker on the general path searches "India stock market November 2026 sector
  news policy demand" and "India generic sector macro economy INR USD crude oil RBI November
  2026"; the prompt tells the analyst to "first infer the company's industry from the bundle".
- **With `lenses.enabled` on:** the same stock searches "India cement prices demand volumes
  capacity news November 2026" and "India coal petcoke prices housing infrastructure spending
  diesel freight costs economy news November 2026"; its company search adds "results volumes
  realisation capacity"; its page extract asks for "<company> cement volumes realisation EBITDA
  per tonne capacity expansion 2026"; and the bundle opens with "Industry: Cement (Yahoo: Building
  Materials). What usually moves this industry's profits: realisation per tonne; sales volume
  growth; power and fuel cost per tonne; capacity utilisation and new capacity; EBITDA per tonne.
  Macro items that matter: … A number the bundle does not contain stays unknown." A stock whose
  Yahoo label no lens lists (a conglomerate) searches "India Conglomerates industry demand prices
  policy news November 2026". A stock with no label keeps today's searches, except that its macro
  search no longer names the graph.

## What was built [code]

1. **Lens files** (`config/lenses/*.yaml`, 25 files, 101 Yahoo labels; format in its README):
   `id`, `display`, `industries`, `kpis`, `news_terms`, `sector_query`, `policy_query`,
   `macro_drivers`. Groups: pharma, healthcare services, specialty chemicals, agri inputs, cement,
   building products, steel, non-ferrous metals and mining, capital goods, construction and
   infrastructure, defence, consumer staples and beverages, agri commodities, textiles, consumer
   durables, retail and restaurants, real estate, hotels/travel/airlines, logistics, oil and gas,
   insurance, media, internet platforms, electronics, paper and packaging.
2. **`services/data/context/lenses.py`:** `load_lenses` checks every file (required fields and
   types, `id` equal to the file name, list lengths, no label in two lenses (case-insensitive),
   only the allowed placeholders, never the word "generic") and raises `LensError`;
   `LensSet.lens_for(label)` gives a `LensChoice` of kind `lens`, `default` or `none`, which words
   the four searches and the industry block; `checked_lenses` (memoised per process until a file
   changes) and `active_lenses` (None unless the setting is on and the files load);
   `startup_line`; `coverage` and `coverage_line` for the weekly log.
3. **`services/data/context/bundle_builder.py`:** on the generic graph with the setting on,
   `_lens_and_peers` makes the bundle's one peer choice first (the stock's Yahoo label), picks the
   lens, and hands the same choice to `_fetch_peers_valuation`. The four search fetchers take an
   optional `lens`; with none, every line runs as before. The four search sections' provenance gets
   `lens` (id, `default` or `none`). `SectorDataBundle` gains `industry_block` and `lens`;
   `to_prompt_text` puts `## INDUSTRY` above the capped sections. `_safe` passes keyword arguments
   through.
4. **Setting** `lenses.enabled: false` (`config.yaml`).
5. **Startup:** `services/api/server.py` `_log_lens_check` logs the set (INFO) or why it does not
   load (ERROR); the server still starts.
6. **Coverage line:** `run_discovery_cycle` returns `lenses` (general-path dives by lens, default
   and no label, and the industries without a lens), and the Saturday job logs
   "Discovery lenses: …".
7. **Scripts** (`scripts/lenses/`): `draft_lens.py` (one model call from a fixed brief, checked by
   the server's parser, nothing written to `config/lenses`); `coverage_report.py` (read-only: the
   last 8 weeks' general-path dives and the share a lens covers, target 80%); `bench.py` (the
   card's A/B/C bench; plan only without `--yes`).
8. **Docs:** `docs/TECHNICAL_DESIGN.md` (section 4 "Industry lenses", the configuration row, a line
   in section 11's lenses design), `docs/TEAM_TESTING_GUIDE.md` case 02-R, `CODEBASE.md`, the
   lenses design (its first slice exists), the architecture map (M2.2's files, config and tree;
   `model.json`, `TREES.md` and `index.html` regenerated). The PDF is not rebuilt (owner's rule of
   17 Nov).

## The card's acceptance

| Criterion | Where it is shown | State |
|---|---|---|
| Lookup fixtures: a known label, an unlisted label, no label | `TestLookup` | met |
| A malformed file or a label in two lenses fails at startup | `TestChecks` (16 malformed shapes, two lenses, empty and missing folders); `TestStartup` (an ERROR line, `active_lenses` None, today's queries) | met, as "fails loud, not fatal" (decision 3) |
| On: no general-path query says "generic", each lens query holds the lens's words | `TestLensWording`, every label of every committed lens (101), the oracle read from the YAML directly | met |
| Off: every query on every path byte for byte today's | `TestTodaysWording`, golden strings typed from the code at `eb5da62`, 5 paths × 3 labels | met |
| The four sector paths unchanged on or off | the same goldens with the setting on | met |
| No extra network call per bundle; a test counts profile lookups | `TestOneLookup`: one peer choice per bundle on every path, on and off; the real choice with a counting Yahoo stub: the same lookups on and off | met |
| The block is not essential; an analysis without it is actionable | `TestBlockIsNotASection`: no status, the health row's counts and verdict the same on and off, `has_real_data` ignores it, the cap cuts the sections, not the block | met |
| The bench summary, with n for every figure, and the rule's outcome | `scripts/lenses/bench.py`, dry-run on stubs (`TestDryRun`); its rule fixed in its docstring before any data | **waits for the owner's run (`PR-032-B1`)** |
| Living documents | listed above | met (PDF not rebuilt, by rule) |

**Which industries first.** The card asks for lenses until 80% of the last 8 weeks' general-path
dives are covered, counted from stored dives. Those files are in production only, and a production
read needs the owner's word. The 25 groups were chosen from the configured sector keys
(`config/sector_toggles.json`) and Yahoo's industry list; whether they reach 80% is
`PR-032-C1`'s read (`coverage_report.py`). A label no lens lists gets the default lens, which is
today's behaviour made industry-specific, not a failure.

## Decisions I took (routine, CLAUDE.md section 2)

1. **The lens files were drafted in this conversation from `draft_lens.py`'s brief**, not by the
   script's model call: this machine has no model key. The script exists for later lenses; the
   reviewing conversation reads every file (the card's rule).
2. **The industry block sits above the bundle's length cap** (at most 900 characters; the longest
   committed block is 517), so the sections keep every character they had.
3. **A broken lens set does not stop the server.** It is an ERROR line at startup and today's
   wording in every bundle; the suite loads the same files, so a broken file fails CI before a
   deploy. Stopping the server would stop the daily review and the portfolio over a search
   wording.
4. **No label keeps today's wording except the macro search**, which takes the default lens's
   economy wording, so that no general-path query names the graph (the card's invariant).
5. **`lens` is recorded only when a lens was looked up** (setting on, generic graph). Off, and on
   the sector paths, provenance is exactly as before.
6. **Labels are matched without case or edge spaces**, as the peers step matches industries.
7. **The bench measures conviction as the composite** (the dimension scores at the stock's
   weights, computed as the aggregator does; the verdict band is bound to it), not the
   aggregator's `final_score`: that second call would write a verdict-shadow row per arm and
   double the cost. **B is C's bundle without the block**, so B and C read the same evidence and
   the block's effect is C − B on every stock. An **A2 arm** (A's bundle, a second call) reports
   run-to-run noise beside the rule, which does not read it. "No call returns fewer usable
   results" is read per search as B's mean against A's over the stocks; on-industry words are the
   lens's KPI and news words of four letters or more, less a fixed list of words every business
   story uses. All of it is written in `bench.py`'s docstring before any data.
8. **The coverage line reads each dive's own Yahoo label**, so it works with the setting off and
   names the next lens to write before anything is switched on.
9. **No label a native graph takes is in a lens** (FIX-026's routing table): such a stock never
   reaches the general path.

## Findings and limits

- **F1 (for the switch-on decision): the search shadow reads the company search.** PR-043 sends
  the bundle's company query to the other engines. With lenses on, that query becomes the lens's
  for general-path stocks, mid-trial. Read `PR-043-W2` (Fri 4 Dec) before switching on, or note
  the switch date in that read. BACKLOG B-61.
- **F2: two Yahoo reads of one label.** The coverage line reads the dive's label
  (`market_classification`, a live call); the bundle's lens reads the peers' cached profile (up to
  30 days old). A label Yahoo changed in between is counted under one lens and searched under
  another. Display only. BACKLOG B-60.
- **F3: label spellings are Yahoo's taxonomy as known, not read from production.** A misspelt
  label falls to the default lens (safe); `PR-032-C1` lists every label seen with its lens.
- **F4: the default lens words its sector search from the label itself**, so a label containing
  "Generic" would carry the word; the only such label ("Drug Manufacturers - Specialty &
  Generic") is in the pharma lens. A company whose own name contains it keeps it in its company
  search; that is the company's name, not the graph's.
- **Not shown:** that the lens searches find better evidence, or that conviction improves. That is
  the bench (`PR-032-B1`) and then PR-017's grades.

## Tests [local]

- **New:** `tests/unit/test_lenses_pr032.py` (190) and `tests/unit/test_lens_scripts_pr032.py`
  (31): 221 passed.
- **Planted bugs: 19 of 19 caught** (lens on a sector path, the macro keeping the graph's name,
  the peer choice not shared, no `lens` in provenance, the block not rendered or inside the cap, a
  duplicate label allowed, any placeholder allowed, case-sensitive labels, no-label and default
  wording unchanged, coverage counting native dives, the setting always on, the block limit made
  strict, fewer usable results ignored, B keeping the block, errored dimensions counted, the graph
  not taken from the shelf, events dated in UTC).
- **Neighbouring suites** (bundle, sectors, peers, FIX-030, PR-043, data health, FIX-026, PR-004,
  PR-037, unified analyst, decision gate): 625 passed.
- **Guards:** broad-except OK (138 grandfathered); architecture map check OK after
  `generate.py`; map page rebuilt; `check_kt_docs.py` errors [].
- **Full suite (guarded), two runs.** The first, on the tree before the commit (27 Nov,
  23:22–23:42 IST): main 8,069 passed, 5 skipped, 1 xfailed (peak anon 1,293 MB); browser 60
  passed, **1 failed**: the map's rule "from a decision every arrow to a box says what leads
  there", on this card's new M2.2 tree (an unlabelled "yes:" arrow; a bug of this phase, not
  B-53 or B-59). The tree was fixed ("yes ─► …", and the lens answers made boxes that flow on to
  the provenance step), the map regenerated and its page rebuilt; the logic tests then passed 82
  of 82. **The second, on `f705a86`** (23:50–00:10 IST): **main 8,069 passed, 5 skipped, 1
  xfailed** (peak anon 1,304 MB); **browser 61 passed** (peak anon 1,818 MB); verdict PASS.

## Commands for the owner's reads (read-only plan; the bench spends)

- `PR-032-C1`, the coverage read (read-only, about a minute):
  `railway ssh "cd /app && python -B scripts/lenses/coverage_report.py"`.
  Below 80%: the next phase writes the named industries' lenses (one drafted file each, reviewed).
- `PR-032-B1`, the bench, after a deploy that carries this code: first the plan, which calls
  nothing: `railway ssh "cd /app && python -B scripts/lenses/bench.py"`; then, at the owner's
  word, `... bench.py --yes` (about 120 Serper searches, up to 40 Tavily pages and 80 calls of the
  analysis's model for 20 stocks; it writes the raw rows to `/tmp/pr032_bench.json` in the
  container, copied to `analysis_data/pr032/`). Not 16:25–17:15 IST on a weekday or
  12:00–15:00 IST on a Saturday.
- Switching `lenses.enabled` on is the owner's word after `PR-032-B1`'s rule says B is ready.

## Changed files

45 files at `f705a86` against `eb5da62`; manifest [PR-032-manifest.json](PR-032-manifest.json) (git blob and SHA-256 per file; review-input SHA-256 `fb25ffbcf86a048738995b00701c825eb9623c5143046bcc0f78100bca7d8eaf`; `kt_manifest.py verify … --rev f705a86`: mismatches []). Diff digest: SHA-256 of `git diff eb5da62 f705a86` = `08458656b73aa2601339dce92aabe2147824e2b5dd85df361865f248d3f2ff89`.

- `CODEBASE.md`
- `config.yaml`
- `core/discovery/__init__.py`
- `docs/TEAM_TESTING_GUIDE.md`
- `docs/TECHNICAL_DESIGN.md`
- `docs/architecture-map/TREES.md`
- `docs/architecture-map/index.html`
- `docs/architecture-map/model.json`
- `docs/superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md`
- `scripts/lenses/bench.py`
- `scripts/lenses/coverage_report.py`
- `scripts/lenses/draft_lens.py`
- `services/api/server.py`
- `services/data/context/bundle_builder.py`
- `services/data/context/lenses.py`
- `services/scheduler/python/scheduler.py`
- `tests/unit/test_lens_scripts_pr032.py`
- `tests/unit/test_lenses_pr032.py`
- `tools/architecture_map/model/curated/modules/M02-data.yaml`
- `config/lenses/`: README.md and 25 lens files (agri_food, agri_inputs, building_products, capital_goods, cement, construction_infra, consumer_durables, defence, electronics, fmcg, healthcare_services, hospitality_travel, insurance, internet_platforms, logistics, media_entertainment, metals_mining, oil_gas, paper_packaging, pharma, real_estate, retail, specialty_chemicals, steel, textiles_apparel)
