# SA-044 — implementation receipt

**Story:** [SA-044](../stories/SA-044.md): compare valuations only with same-industry peers.

**Phase:** implementation, 12 Nov 2026, about 12:49–14:20 IST. Session `stockagent-main-90`
[1c8a13], a new conversation opened with "continue". `origin/main` was at `581eb90`, the same as
HEAD: nothing had arrived from the other device. Eight peer sessions were idle. This phase includes
a same-conversation self-review, which is not the fresh review.

**Baseline:** HEAD `581eb90` with FIX-029's accepted, uncommitted work in the tree (its manifest
`55c54758` verified with 0 mismatches before the first edit), its review receipt, and STATE/HANDOFF.
That tree, with SA-044 marked in progress, was written as git tree `a3ef9c4b` before any SA-044 edit;
the review diff is taken against it.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or
configured. No production state was read, no LLM was called and no message was sent. No test reaches
the network (`tests/hermetic.py`). One local check read Yahoo Finance's public quote data from this
laptop (section "Local live check"); it touched no production system.

## In one example

SUNPHARMA runs the generic graph. **Before:** its peers valuation section compared its P/E with
MARUTI, TATAMOTORS, M&M, HEROMOTOCO and BAJAJ-AUTO, and when no peer P/E came back the replacement
search was "Indian automobile EV sector PE ratio …". **Now:** its Yahoo industry is "Drug
Manufacturers - Specialty & Generic"; the section opens with `peers: same Yahoo industry "Drug
Manufacturers - Specialty & Generic", nearest market cap first (5): DIVISLAB, TORNTPHARM,
ZYDUSLIFE, DRREDDY, CIPLA` (the local live check), and any replacement search names those peers and
that industry. APOLLOHOSP, a hospital chain with no other hospital among the known symbols, reads
`peers unavailable: 0 other known symbol(s) in Yahoo industry "Medical Care Facilities", 3 needed
(…)` and is told to judge its valuation on its own ratios and history.

## What changed

- **The rule (`services/data/context/peers.py`, new):** `choose_peers(ticker, sector=)` returns a
  `PeerChoice` (symbols, industry, reason; `note()` is the one-line statement). The stock's industry
  is Yahoo's (FIX-011's source). Candidates are `known_symbols()`: the registry's `TICKER_SECTOR`,
  the four native sectors' `TICKERS`/`PEER_TICKERS`, the managed tickers (`read_managed_tickers`,
  never seeds) and the active shelf ideas. A candidate whose identity (`resolve_identity`) is not
  resolved is left out (TATAMOTORS), two tickers for one provider symbol count once (TVSMOTOR,
  TVSMOTORS), and a stock whose own identity is unresolved gets none. Peers: the candidates in exactly
  the stock's industry (case-insensitive), nearest market cap first by `|ln(cap/my_cap)|`, unknown
  caps last, ties by symbol, a stock without a cap takes largest first; at most `peers.count` (5);
  fewer than `peers.minimum` (3) gives none, with the count and how many known symbols are profiled.
- **The cache:** `lookup_profile(provider_symbol)` is one yfinance `.info` call (industry, sector,
  market cap) that raises on failure. `data/peer_profiles.json` keeps each answer with its date for
  `peers.cache_days` (30). A build looks up at most `peers.max_lookups` (25) profiles that are missing
  or older: the stock first, then missing before old, the stock's registry key (or a native graph's)
  first within each. Three failures in a row stop the build's lookups; a failure is never stored.
  An old profile is used until refreshed. A thread lock serialises the fill; the file is replaced
  atomically. Once the known symbols are profiled, a build makes no lookup.
- **The bundle (`bundle_builder._fetch_peers_valuation`):** calls `choose_peers`, passes the peers
  and their industry to `get_valuation_result`, puts `note()` on the section's first line (with "No
  peer comparison: judge the valuation on the company's own ratios and history only." when there are
  none), and records it as the provenance field `peers` (new optional `FetchResult.peers`), so the
  data-health row's `section_provenance.peers_valuation.peers` carries the rule and count. With no
  peers, `reason` starts "peers unavailable: …". `_sector_peer_tickers`, `_MAX_PEERS` and the five
  `peer_tickers_module`/`peer_tickers_attr` config keys are deleted.
- **The valuation (`fetcher.get_valuation_result`, `get_valuation_context`):** new keyword
  `peer_industry`. With no peer P/E back, the search is `India NSE <industry> companies PE ratio
  peer comparison <year>` and `<first three peers> NSE PE ratio valuation <year>`; the reason says
  "Serper fallback (chosen peers)". No peers given: the reason gains "no peers to compare with". The
  status rule is unchanged (decision D1).
- **The legacy fallback (`ContextBuilder._build_valuation_catalyst`):** the automobile worker-pool
  agent used the fixed `PEER_TICKERS`; it now uses the same rule and states it. Beyond the card's
  starting points, under its first criterion ("no stock's peer list").
- **Config (`config.yaml`):** `peers: {count: 5, minimum: 3, cache_days: 30, max_lookups: 25}`.
- **Docs:** KT (`TECHNICAL_DESIGN.md`) new section 4 "Valuation peers", configuration and
  persistent-records rows, section 8's generic-bundle sentence and section 11's summary corrected
  (peers no longer car makers; the ETF flows stay FIX-030's); guide case **02-O**; PDF regenerated.

## Decision D1 (delegated technical call): the status stays the stock's own data's

The card's routed input (SA-002) suggested that `peers unavailable` should make the section
`fallback` or `empty`. Not done, for a measured reason:

- `peers_valuation` is an essential section, so `fallback` makes the gate abstain.
- Two committed consumers act on an abstaining gate **in `record` mode too**:
  `ShelfStore.apply_redives` drops a re-dived idea whose gate is not actionable
  ([shelf.py:493](../../../../core/discovery/shelf.py)), and `candidates.watchlist_idea` refuses a
  watchlist buy whose latest analysis is not actionable
  ([candidates.py:182](../../../../core/discovery/candidates.py)), both since PR-004.
- The local live check found 69 of the registry's 202 tickers in an industry with fewer than three
  known peers (APOLLOHOSP, LT, ITC among them); discovery stocks outside the registry are likelier
  still. So `fallback` would drop those ideas at their next re-dive and refuse those watchlist buys,
  for the app's thin symbol list rather than for missing data.

So the status is decided by the stock's own price history and ratios, as SA-002 and SA-010 decided
for context (peers, benchmark). The missing comparison is stated in the text, `reason` and `peers`.
A transient peer P/E failure keeps `ok` too, as before. Tests pin it
(`test_the_status_is_the_own_data_and_peers_never_make_the_gate_abstain`, mutants M18 and M18b).

**Owner decision, 12 Nov about 14:10 IST:** asked (plain example below) whether a stock with no
same-industry peers should count as missing essential data, the owner answered "ya its good on what you built, go ahead commit and push":
**no**, it is judged on its own numbers, as built. The question as asked: should it count as
missing essential data? APOLLOHOSP today: if **yes**, its Saturday re-dive drops it from the shelf
and a watchlist BUY of it is not offered, and under an enforced gate it reads INSUFFICIENT DATA; if
**no** (built), it is judged on its own ratios and history and the record says why it has no
peers. A wider known-symbol list (SA-026's lenses) shrinks the question either way.

## Tests

All runs use the `.stockai` venv (Python 3.13, pytest 9.0.3), Windows 11, hermetic.

- **Story file** `tests/unit/test_peer_choice_sa044.py`, 73 tests: the card's fixtures (SUNPHARMA
  with four pharma symbols gets exactly those; TATASTEEL with one steel symbol and an unknown
  industry get `peers unavailable`; a bank keeps bank peers; one stock per native sector);
  nearest-by-cap derived by hand for a five-symbol fixture (C 1.2×, A 2.0×, F 2.0×, B 2.5×, D 5.0×
  → C, A, F, B, D), at most five, unknown caps last, no own cap; **40 random universes** against an
  independent oracle (larger-over-smaller cap ratio, not a logarithm); known-symbol sources, an
  unreadable source; identity with the shipped registry (TATAMOTORS never a peer, never looked up;
  one listing once; an unresolved stock gets none); cache (second build no lookup, old profiles used
  then refreshed within the budget, the stock and its registry sector first, three failures stop,
  a failure between answers does not, failures never stored, unreadable file); the section (text and
  provenance state the choice; unavailable said with reason, no peer search at all; the status is
  the own data's with and without peers and with no industry, and the gate's `essential_unusable`
  stays empty; own data missing is still `fallback`; no peer P/E searches the chosen peers and their
  industry, never "automobile"); the bundle and `build_record` carry `peers`; a warm cache adds no
  call beyond the stock's and its peers' own; the legacy builder uses the rule.
- **Regression** `tests/unit/test_peer_regression_sa044.py`: SUNPHARMA through
  `_fetch_peers_valuation(…, "generic")` with only yfinance stubbed. On the baseline tree (a detached
  worktree of `a3ef9c4b`): **1 failed**, "valued against another industry: ['MARUTI',
  'TATAMOTORS', 'M&M', 'HEROMOTOCO', 'BAJAJ-AUTO']". On the final tree: passed.
- Story file plus regression on the final bytes: **74 passed** (16.9 s).
- **Changed existing tests:** `test_bundle_builder_sectors.py` `TestPeersValuation` rewritten
  (one sector per test, stubbed profiles: peers share the stock's industry; a generic stock never
  gets the automobile list); `test_unified_analyst_generic.py` asserts no sector config carries a
  peer list.
- **Neighbouring suites** (bundle builder, sectors, unified-analyst generic, data-health contract
  and record, SA-010 benchmark, orchestrator unified branch, the two e2e parity files, FIX-026
  sector naming): 0 failed after the change; the data-health files 189 passed.
- **Mutants:** 24 of 24 caught (`analysis_data/sa044/mutants.py` in a detached worktree of the final tree; output `mutants.txt`): industry match ignored, minimum 1, nearest without abs, unknown caps first, no own cap smallest first, unresolved identities kept, dedupe by app ticker, old profiles never refreshed, four failures to stop, failures not reset, no budget, no sector priority, the stock not looked up first, more than five, an unresolved stock gets peers, the lookup reads the sector, dropped shelf ideas counted, missing peer P/E makes the section `fallback` (M18), peers unavailable makes it `fallback` (M18b), the no-peers note dropped, the automobile search back, provenance `peers` dropped, no first line, the legacy builder keeps the auto list. A first run of 22 before decision D1 caught all too (`mutants_run1_before_status_decision.txt`).
- **Full suite:** run 1 on the snapshot tree `16b67b5d` (13:24–13:44 IST): 6,379 passed / 14 skipped / 1 xfailed / **1 failed**, rc 1: `test_broad_except_guard::test_real_tree_matches_its_baseline` named `_registry_key`'s silent handler (the checkout's own `check_broad_except` cannot see an untracked file). Fixed by logging it. Run 2 on the final bytes (a detached worktree, every manifest file byte-identical to this checkout), 13:44–14:05 IST: **6,380 passed / 14 skipped / 1 xfailed / 0 failed**, pytest rc 0, 21m06s (`analysis_data/sa044/full_suite.txt`; run 1 kept as `full_suite_run1.txt`). The 2 skips beyond the usual 12 are browser tests that need `node_modules`, absent in a worktree; their three files ran in this checkout: 75 passed. Against FIX-029's 6,307 passed / 12 skipped: +75 = story file 73, regression 1, and the sector peer tests 5 in place of 4.
- `check_broad_except`: OK (148) in the checkout, which scans tracked files only; in a worktree
  where the new module is tracked it named one new silent handler (`_registry_key`), now logged.
  In that worktree, on the final bytes: OK (148).
- `check_kt_docs`: `errors` holds one expected item: the KT links `services/data/context/peers.py`,
  absent at the header's declared revision `245e29e`; the commit-time header bump clears it. PDF 70
  pages, source `114c314b…`, 642,011 bytes.

## Local live check (not production)

`analysis_data/sa044/live_peers.py`, run 12 Nov from a scratch working directory with the real
`known_symbols()` (the registry and native lists only: no managed file or shelf there) and no lookup
budget; about 200 Yahoo `.info` calls in 76 s; output `analysis_data/sa044/live_peers_out.txt`.

| Stock (graph) | Result |
|---|---|
| MARUTI (automobile) | Auto Manufacturers (5): M&M, BAJAJ-AUTO, TVSMOTORS, EICHERMOT, TMPV |
| HDFCBANK (banking) | Banks - Regional (5): ICICIBANK, SBIN, KOTAKBANK, AXISBANK, PNB |
| INFY (IT) | Information Technology Services (5): HCLTECH, TCS, WIPRO, TECHM, LTIM |
| ADANIGREEN (renewable) | Utilities - Renewable (3): NHPC, SJVN, INOXGREEN |
| TATAPOWER (renewable) | Utilities - Independent Power Producers (4): JSWENERGY, TORNTPOWER, ADANIPOWER, RPOWER |
| SUNPHARMA (generic) | Drug Manufacturers - Specialty & Generic (5): DIVISLAB, TORNTPHARM, ZYDUSLIFE, DRREDDY, CIPLA |
| TATASTEEL (generic) | Steel (5): JSWSTEEL, SAIL, NMDC, WELCORP, RATNAMANI |
| APOLLOHOSP, LT, ITC (generic) | peers unavailable (0, 2 and 0 others in their industries) |

Every named peer's stored industry equals its stock's. 199 listings profiled, 7 without an
industry; 133 of the 202 registry tickers have at least three same-industry known symbols. This is
local evidence of the rule on today's data, not a production measurement, and shows no benefit.

## Rollout (what deploying changes, with the switch off)

- Every analysis's peers valuation section changes: generic-graph stocks stop citing car makers,
  native-sector stocks get nearest-cap same-industry peers (TATAPOWER's are power producers, not
  ADANIGREEN), and about a third of registry stocks read `peers unavailable`. The analyst's
  valuation scores may move; no decision rule changes and no gate status changes.
- First analyses after deploy make up to 25 extra Yahoo `.info` calls each (about 0.4 s each
  locally) until `data/peer_profiles.json` holds the known symbols, then none. The file lives on the
  volume; deleting it costs only lookups. Rollback is a revert (the file is then unused).
- Read-only checks after deploy: the data-health rows' `section_provenance.peers_valuation.peers`
  over the first daily review (how many `peers unavailable`), and the log's `[peers]` lines (failed
  lookups).

## Not covered / routed

- The generic graph's legacy fallback agent `valuation` reads `_build_valuation`, whose searches
  are renewable-energy queries ("EV per MW … renewable peer", "MNRE auction") for every generic
  stock. Not a peer list; it runs only when the unified call fails. Routed to SA-027, which retires
  that pool.
- The generic graph's ETF fund-flow line is FIX-030's.
- The known-symbol list is narrow (registry, managed, active shelf). SA-026's lenses own widening it.

## Review input

- Manifest: [SA-044-manifest.json](SA-044-manifest.json), SHA-256 `24d605b08a1e155766b2fa0e206abce0afd856105a74cc0bdac786cce5af9ea8`, 13 files (`scripts/docs/kt_manifest.py verify`: 0 mismatches).
- Diff against the baseline tree `a3ef9c4b` (HEAD `581eb90` plus FIX-029's accepted work), the PDF excluded: SHA-256 `c769970a27348f3d34a93c5c280db70ec993b7a715041f49246cd6beb073a6bf`, 81,529 bytes, 12 paths, via `analysis_data/sa044/digest.py` (a temporary index; the real index is untouched). End tree `b9b9ebdbb9c036e7ed3131022ac47fb0e1b4dca5` (taken before this receipt's last figures and the STATE/HANDOFF splice).
- Outside the manifest: STATE, HANDOFF, this receipt and the manifest (bookkeeping). FIX-029's manifest `55c54758` now reports 3 mismatches: the three files both stories edit (`TECHNICAL_DESIGN.md`, `TEAM_TESTING_GUIDE.md`, the PDF); its other files are unchanged.
- The baseline tree exists only in this checkout (a dangling object). On another device, after FIX-029 is committed, take the diff against that commit over the manifest's paths but the PDF, sorted, `core.autocrlf=false`.

## What a fresh review should press on

1. D1 is the owner's decision (12 Nov); check that the code holds it everywhere a peer comparison
   can be missing.
2. The hard review: run `choose_peers` live for one stock per production lens and check each
   name's industry (`analysis_data/sa044/live_peers.py` does it from a scratch directory).
3. The budget and stop rule on a cold production volume: the first daily review's latency and
   Yahoo's tolerance of up to 25 extra `.info` calls per analysis.
4. Whether nearest-by-ratio and "unknown caps last" are the right order, and whether exact Yahoo
   industry is too fine (TATAPOWER is not compared with ADANIGREEN).

Next: a fresh review in a new conversation (REVIEW.md).

## After the phase: committed at the owner's word (12 Nov)

In the same conversation, the owner answered D1 and asked: "ya its good on what you built, go ahead commit and push". So the work was committed
before its fresh review, as FIX-028's was:

- `e511f50`: FIX-029's code and tests (accepted by its fresh review); `f368f20`: SA-044's code,
  tests and config. At HEAD every code and test file of both manifests has 0 mismatches
  (`kt_manifest.py verify --rev`); the review input above still holds for them.
- The docs commit after them applies FIX-029's six commit-time edits (KT header at `f368f20`, edition
  2026-11-12; KT section 1; KT section 6 loses the local verdict-log sentence; KT section 12
  FIX-029 Done; guide 07-G and 07-O; the PDF) and SA-044's (the same header and section 1, guide
  02-O's status, this section and D1). So the KT, the guide and the PDF differ from this
  manifest by exactly those edits.
- The push and its deployment are recorded in STATE and HANDOFF.
