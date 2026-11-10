# FIX-026 — implementation receipt

**Story:** [FIX-026](../stories/FIX-026.md): the analysis names a new stock's sector from our list; an
empty or unknown sector is flagged (owner decision of 4 Nov 2026 on SA-049's design choice T7).

**Phase:** implementation, 9 Nov 2026, about 21:00–22:10 IST. Session `stockagent-main-22` [d97f79], a
new conversation opened with "continue". No other session was running. `origin/main` was at
`412645f`, the same as HEAD: nothing had arrived from the other device the owner moved FIX-026 to on
7 Nov. This phase includes a same-conversation self-review, which is not the fresh review.

**Baseline:** HEAD `412645f`, working tree clean. Nothing is stacked: every changed file below differs
from HEAD.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or configured.
No production state was read, no network was used, no LLM was called and no message was sent. No test
reaches the network (`tests/hermetic.py`).

## In one example

A drug maker outside the registry's ticker map; Yahoo calls it Healthcare / "Drug Manufacturers -
Specialty & Generic".

- **Before:** FIX-011's fixed table read Yahoo's "Healthcare" as `pharma`. A stock whose industry no
  table row named (a staffing firm, a textile maker) was silently `generic`, and nothing said so.
- **Now:** the deep dive's own analyst call is given our 22 keys and Yahoo's labels as evidence, and
  answers `{"key": "pharma", "reason": "Makes generic formulations.", "yahoo_fits": true}`. `pharma`
  is a configured key, so the idea is shelved as `pharma`. Both caps count it with the drug makers:
  with three `pharma` ideas on the shelf it must outrank the weakest to get in, and with SUNPHARMA
  and CIPLA at 28% of ₹10 L, a ₹1 L position of it is cut to ₹20,000 (20 shares, not 100).
- Answered "Pharmaceuticals" (not a key), the idea is shelved under the generic graph with "the
  analysis answered 'Pharmaceuticals', not one of our keys"; nothing buys it, Saturday re-dives it
  first, the week's summary lists it as invalid and the watchdog names it.

## What changed

- **`src/backend/shared/pipeline/unified_analyst.py`:** `run(..., sector_question=None)` appends the
  question to the user prompt and keeps the top-level `sector_key` block, unvalidated, in
  `_last_sector_answer`. Without a question the prompt is unchanged (test compares the bytes).
- **`src/backend/shared/pipeline/base_orchestrator.py`:** `analyse(..., *, sector_question=None)` holds
  the question for the run (per-run state, like `_last_data_health`, reset at both entry points);
  `_run_unified` passes it only when set, so every other caller and every patched analyst is called
  exactly as before; the answer comes back as `report.sector_answer`.
- **`src/backend/shared/schemas/pipeline.py`:** `FinalReport.sector_answer` (None unless asked and
  answered). **`schemas/discovery.py`:** `SectorReading` (answer, reason, `yahoo_fits`, problem,
  `yahoo_gap`, source) on `DeepDiveResult` and `ShelfIdea` (None = shelved before FIX-026).
- **New `core/discovery/sector_naming.py`:** the configured list (`config/sector_toggles.json` through
  the registry, "generic" excluded), the question's text, `read_answer` (membership, trimmed and
  lower-cased; an explicit `generic` needs a reason), `known_key` / `decide_key` (decided once),
  `graph_guess` (the graph only), `unnamed_why`, `describe`, `status`, `summarise`, `counts_line`.
- **`core/discovery/deep_dive.py`:** FIX-011's `_YAHOO_INDUSTRY_SECTOR`, `_YAHOO_SECTOR_SECTOR`,
  `sector_from_classification` and `infer_sector` are deleted. Each dive reads the managed records
  once (sectors too, enabled or not), asks the question in its one call, and stores the decided key
  with its reading; an unnamed key is logged at INFO (D9).
- **`core/discovery/shelf.py`:** the per-sector cap counts the sector key (`cap_key`), not Yahoo's
  `market_sector`; `apply_deep_dives` keeps the reading; `apply_redives` names an idea that has no
  configured key (or `generic`) and never changes a named one, recording the latest reading either
  way; `redive_due` puts an idea with no key named in the unverified group; `promote` refuses one.
- **`core/discovery/candidates.py`:** `shelf_sector` (Yahoo's stored classification through the table)
  is deleted. A fresh shelf idea not managed is offered only when its key is named ("sector unnamed:
  …; waits for a re-dive to name it"). `holding_sector`: managed record, else the item's own key when
  configured ("generic" is not), else the ticker map's, else "" — and `watchlist_idea` then refuses
  the stock.
- **`core/discovery/__init__.py`:** the cycle's result gains `sectors` (`summarise`), non-fatal.
  **`services/scheduler/python/scheduler.py`:** the Discovery line adds `sectors=[…]` counts, and a
  "Discovery sectors <kind>" line names each stock not cleanly named.
- **`core/ops/watchdog/checks.py` + `config/milestones.yaml`:** check `sector_keys`, invariant
  `sector_keys_named` (an addition; nothing deleted).
- **`services/api/routes/discovery_api.py`:** a promote of an unnamed idea answers 409 with the reason.

## Decisions (F26-D1 to D10)

| # | Decision | Why | Card |
|---|---|---|---|
| D1 | The question rides in the unified analyst's call, the dive's own; the orchestrator carries it as per-run state and `analyse` gains a keyword-only argument. | "No extra paid call." The unified analyst is the one call that reads the data bundle (the company's own description). Per-run state keeps the `_run_agents`/`_run_unified` signatures, which several test files patch or call directly. | Intended result 1 |
| D2 | The list is `config/sector_toggles.json`'s 22 keys; `generic` only as an explicit "none fits" with a reason. | It is the registry's list, the one the graph router reads. `promotion.is_valid_sector` checks format only, so it cannot be the list. | Intended result 1–2 |
| D3 | A first guess at the graph stays, for the four native graphs only (auto, IT, power and renewables industries; Yahoo's "Financial Services" outside insurance). The other 17 rows are deleted. | The call needs a graph before it answers, and a bank analysed by the banking graph reads bank-specific dimensions. The guess only routes the call and is never stored. Example: a Yahoo "regional bank" answered `insurance` ran the banking graph and is stored `insurance`. | "Decide and record that" |
| D4 | Decided once, in this order: the managed record (enabled or not), the registry's ticker map, an idea's earlier named key, then the answer. The question is asked even when the key is known. | The managed record holds the forecasts; the ticker map is our configuration (FIX-020 corrects it there). Asking anyway costs no call and records disagreements (`kept`). | Decided once |
| D5 | An idea with no key named is shelved under the generic graph with its problem recorded, never bought or promoted, and re-dived first with the unverified ideas. An idea shelved as `generic` before FIX-026 counts as unnamed. | Neither cap can be checked for a stock of unknown sector; shelving keeps its paper lane and lets the next Saturday name it, at the cost of its re-dive slot. Not shelving would lose the idea for 30 days (the dive memo). | "Decide whether such an idea may be shelved and bought" |
| D6 | The shelf's cap counts the sector key, as SA-050 does. An idea with no key, or `generic`, is not capped. | The card's hard review asks for one key; PR-004 had kept Yahoo's `market_sector` only because the key was mostly `generic`. Finer keys: "Basic Materials" held 3 ideas before, now `chemicals`, `metals` and `agrochem` hold 3 each. | Hard review 3 |
| D7 | A watchlist stock not managed takes its own key only when configured, else the ticker map's, else it is not offered. | No Yahoo table may decide a stored key, and a fixed `generic` is what the card forbids. Rare: the home page promotes a watchlist stock to managed. | Acceptance 4 |
| D8 | Watchdog check `sector_keys`: pending for an active idea or holding with no configured key or `generic`, and for an idea whose analysis disputed Yahoo's labels or had none; reminded weekly. Holdings named by symbol only. | Discovery runs weekly and a holding's key changes only by hand, so a daily repeat adds nothing; the first notice is immediate unless one went out in the last week. | Vigilant |
| D9 | The dive logs a missing key at INFO, not WARNING. | The summary and the watchdog are the loud channels; a WARNING would also open an error-backlog issue for the same fact. | — |
| D10 | When a re-dive names an idea's key, its paper lane writes under the new key from then on; the old paper envelope is left, not moved or deleted. | The card allows naming an unnamed idea no portfolio holds; its paper record is not a portfolio's forecast history. | Decided once |

## The card's hard-review questions

- **Can an answer outside the list be stored?** No. The stored key is the answer only when it is a
  configured key, trimmed and lower-cased, or a reasoned `generic`; anything else stores the generic
  graph with source `unnamed`, which nothing buys. Pinned over 3,000 random answers, each read under
  13 Yahoo label pairs (`test_property_a_stored_key_is_a_configured_key_or_generic_and_yahoo_never_decides_it`).
  A key decided before the analysis (a managed record a user typed) can be outside the list; the
  watchdog names such a holding or idea.
- **Can a valid but wrong answer (a bank named `it_sector`) pass unnoticed?** Only partly guarded. It
  is flagged when the analysis itself says Yahoo's labels do not fit (disputed: summary and watchdog),
  and the week's summary prints Yahoo's labels beside every named key for a human to read. A wrong
  answer with `yahoo_fits: true` is not caught by any rule.
- **Is a sample of real answers compared with Yahoo's labels?** Not in this phase: no LLM was called.
  The first Saturday run after the deploy is that sample (guide 06-M): its summary lists every named
  key beside Yahoo's labels.
- **Does it add a paid call or change the analysis's other outputs?** No extra call (one `create()` per
  run, tested). The dive's prompt grows by about 340 tokens (cl100k count of the question for a drug
  maker) and its answer by about 50: at the configured reasoning rates ($0.435 and $0.87 per million)
  about $0.0002 (₹0.02) a dive, about ₹1.5 a month at 20 dives a week (inference from rates, not
  measured). Parsing of the dimensions is
  unchanged (same outputs for the same JSON, tested), and every other analysis sends a byte-identical
  prompt. Whether the extra block shifts the model's dimension scores is not measured. If the
  answer is cut off by the 6,000-token limit, the block, asked for last, is lost and the idea is
  unnamed, loudly.
- **Do the shelf's cap and the sizing cap read the same key?** Yes (D6), with one pre-existing edge: a
  shelf idea whose stock became managed under another key afterwards is capped on the shelf under
  its own key and sized under the managed one (PR-004's rule).

## Found on the way

- **The configured list overlaps** (pre-existing): `power` beside `renewable_energy`, under which the
  ticker map files every power utility; the UI's alias table folds `tech` into `it_sector` while `tech`
  is a key. A new thermal utility named `power` is capped apart from NTPC. Routed to SA-026 (card
  section "Routed input — 2026-11-09"); KT section 8's limits say so.
- **The home page files a stock outside the ticker map as `generic`** (`portfolio_api._resolve_sector`),
  decided once in its managed record, and no route changes a holding's key. Routed to SA-026; the
  watchdog now names such holdings weekly.
- **SA-050's sector cap lumps every `generic` holding** under one 30%. Rarer now; stated in KT section 8.

## Rollout

- **Deploying changes production with the switch off.** On the first Saturday: each dive's prompt gains
  the question; every active idea shelved as `generic` before the deploy is unbuyable until re-dived
  and goes into the first re-dive group, so that week's budget (20, less the IPO slots) goes to them
  before new ideas; the shelf's cap moves to keys, so a key holding more than 3 active ideas drops its
  weakest with a "sector cap" event. SWITCH destinations shrink until those re-dives run. How many
  `generic` ideas production holds was not read.
- **The watchdog's new invariant may notify on its first run** (06:30 IST): legacy `generic` ideas and
  any `generic` holding. Expected, and weekly after that.
- **First looks, read-only:** after the first Saturday, the Discovery line's `sectors=[…]` counts and
  the named stocks with Yahoo's labels (the sample the card asks for; guide 06-M); then the
  watchdog's notice. Counts and symbols only.
- **No benefit is shown here.** These are contracts. Whether the keys are right is the first
  Saturday's sample.

## Tests and commands

Environment: `.stockai/Scripts/python.exe` (Python 3.13), Windows, from the repository root.

- **Story file** [`tests/unit/test_sector_naming_fix026.py`](../../../../tests/unit/test_sector_naming_fix026.py), 61 tests, figures worked by hand in docstrings, through the real `run_deep_dives`, `ShelfStore`, `buy_candidates`, `size_buy`, `run_discovery_cycle`, the scheduler job, the watchdog check and the registry loader:
  - Acceptance 1: the drug maker named `pharma` (graph, reading, the question's content, one call); both caps (shelf event "sector cap: 3 ideas in pharma; replaced by NEWDRUG (0.72 > 0.70)"; 20 shares, not 100).
  - Acceptance 2: each fail-loud case (Yahoo gap, not a key, no answer, disputed): the record, the summary entry and the watchdog's exact line; the unnamed idea shelved, not offered, re-dived first, then named and offered.
  - 19 answer shapes; `yahoo_fits` strictness; the 3,000 × 13 membership and Yahoo-independence property; no table left; the graph guess (14 label pairs, natives or generic only); guess versus answer.
  - Acceptance 3: a sold managed stock kept as `automobile` with `logistics` recorded; a disabled managed record; the ticker map; a named idea through its re-dive; a 60 × 12-week property (a named key never changes; an unnamed one only gets named).
  - The buy rule as a 2,000-shelf property stated apart from the code, with completeness; the promote refusal (409).
  - The prompt: byte-identical without the question, base + question with it, one call each, the same dimension outputs; a failed call leaves no answer; the orchestrator passes the question and returns the answer, and the next run on the same orchestrator gets none.
  - The cycle's `sectors` for five stocks; the scheduler's lines; the watchdog satisfied, and naming a legacy idea and two holdings (one in two portfolios, one line); the registry entry.
- **Reworked older tests** (behaviour changed by design): PR-004 (`test_idea_supply_pr004.py`: the stub analyst answers a sector, ideas carry readings, the cap tests count keys, backfill names labels only, watchlist sector cases, a new no-key case), FIX-011 (`test_surveillance_sector_fix011.py`: the table tests removed, the never-re-keyed tests kept, a re-dive naming a generic idea, CEATLTD needs a key), SA-049 (`_pipeline_world` registers its fixture keys as toggle rows; the generic-idea test inverted), SA-003 and the deep-dive file (fakes take the keyword).
- **Mutants** (`analysis_data/fix026/mutants.py`, in place, each restored by sha256; the story file, PR-004's, FIX-011's and the deep-dive file): 33 of 33 caught on the first pass (`mutants.log`; membership, case, reasoned generic, each source of a known key, the unnamed placeholder, the buy gate, the watchlist rules, the cap reading Yahoo's label, re-dive re-keying and never naming, the unnamed re-dive order, the promote guard, the reading kept, the graph route, the question asked, appended and its answer kept and returned, the question sticking to the next run, the watchdog's look items, holdings and generic holdings, the summary's disputed entry, Yahoo's gap, the insurance guess, Yahoo's labels in the question). After the managed key was made exact, `managed_ignored` and `known_key_ignored` re-run and a new `managed_lowercased` added: 3 of 3 (`mutants2.log`). Every mutated file was compared with its pre-run copy afterwards: identical.
- **Full suite** (`tests`, hermetic): **6,203 passed / 12 skipped / 1 xfailed / 0 failed**, pytest exit code 0, 14m07s (21:51–22:05 IST), `git status` identical before and after (`analysis_data/fix026/full_suite.txt`, `status_*_suite.txt`). One run.
- `check_broad_except`: OK (148, unchanged). `check_kt_docs`: one error, expected: "KT links core/discovery/sector_naming.py, which is absent at its declared revision b065da303cf1"; the commit-time header bump clears it. 730 local links, 51 stories, 26 job IDs checked; the PDF carries the KT's source hash.

## Documentation

- `docs/TECHNICAL_DESIGN.md` section 8: shelf upkeep, the re-dive order, the shelf's cap, "Sector key"
  (replacing "Market sector": the question, membership, decided once, the graph guess, nothing silently
  `generic`, the summary, the watchdog, the worked example), the cap example, buy candidates' sectors,
  the limits; section 12 gains FIX-026's row (Open).
- `docs/TEAM_TESTING_GUIDE.md`: 06-E's cap and 06-J's key follow the change; new 06-M.
- `docs/AUTOPILOT_GUIDE.md`: the sector a candidate carries. `CODEBASE.md`: the discovery rows, the new
  module, the orchestrator and analyst rows.
- `docs/ARCHITECTURE.md`: no change; it does not describe sector keys.
- `docs/planning/PI-2026-09/stories/SA-026.md`: the routed input.
- `docs/StockAgent-Three-Loops.pdf` regenerated: 69 pages, source `30df47f0e2a5b2d88fe28836fa3e90087c60dcfe6a2d81655559e7bdc44e5ca3`, 623,085 bytes.

**Commit-time edits still to make:** KT header (Code inspected, edition), which clears check_kt_docs'
expected error for the new linked module; section 1 (the inspected code adds FIX-026, not yet
deployed); section 12 FIX-026 Done; guide 06-M's status line; the PDF.

## Review input

- Manifest: [FIX-026-manifest.json](FIX-026-manifest.json), SHA-256 `253620a2d214f9df266695f3f8a616f4a6c9dbf3c4ade97fc1c862daf1262f5b`, 25 files
  (`scripts/docs/kt_manifest.py verify`).
- Diff against HEAD `412645f`, the PDF excluded: SHA-256 `0da6b47aac46dd1c170acfd6c7a04075db17a7a1e2a867082669dc9ee37bc5e6`, 195,461 bytes, 24 paths, via
  `analysis_data/fix026/digest.py` (a temporary index, so the new files are in the diff and the real
  index is untouched). End tree `0e1866ac0908ed7cd730066f04aec404f7caa8a3`.
- STATE, HANDOFF and this receipt are bookkeeping, outside the manifest.

## What a fresh review should press on

1. D5: is shelving an unnamed idea right, and can any path buy it (SWITCH leg, deployment, watchlist,
   a manual promote)?
2. D4's order, especially the ticker map before an idea's earlier key, and a managed key outside the
   list.
3. D3: does the graph guess decide anything stored?
4. Whether the native graphs' prompts ("no keys beyond the schema below") let the model answer the
   appended block, which only production will show.
5. The legacy `generic` ideas on the first Saturday: the budget they take and the caps they meet.

Next: a fresh review in a new conversation (REVIEW.md).
