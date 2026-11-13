# FIX-030 — implementation receipt

**Story:** [FIX-030](../stories/FIX-030.md): a generic-graph analysis sees no automobile evidence;
a key the old Yahoo table set is re-examined; an unnamed idea stops taking a weekly re-dive. With
SA-044's routed R1 and R2 (the peer cache).

**Phase:** implementation, Friday 13 Nov 2026, about 08:40–10:35 IST. Session `stockagent-main-99`
[d33680], a new conversation opened with "continue". `origin/main` was `5ae2749`, the same as HEAD:
nothing had arrived from the other device. Eleven peer sessions were idle. This phase includes a
same-conversation self-review, which is not the fresh review.

**Baseline:** HEAD `5ae2749`. The tree held only the uncommitted `5ae2749` push record in STATE and
HANDOFF (bookkeeping); no code was uncommitted, so the review diff is taken against HEAD itself.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or
configured. No production state was read, no LLM was called and no message was sent. No test
reaches the network (`tests/hermetic.py`).

**Started before Saturday's counts.** The card says to read Saturday 14 Nov's discovery counts
first. This phase ran on Friday 13 Nov, before that run. Only M1 depends on those counts, and the
card makes M1 conditional on them, so M1 is not built (below). M2, L1, L2, R1 and R2 are specified
independently of them and are built. Recorded in STATE when the phase started.

## In one example

RAINBOW, a children's hospital chain, runs the generic graph. **Before:** its bundle's flows section
carried "[MF HERDING SIGNAL — generic sector …]" with the Mirae, ICICI and Nippon Nifty Auto ETFs'
momentum, and its peers were car makers (SA-044 fixed the peers on 12 Nov). **Now:** its flows
section has bulk deals and FII/DII only, and the section's reason reads "MF herding: no sector ETFs
for generic"; MARUTI's flows section still shows the three auto ETFs.

ODDCO, a hospital chain FIX-011's table filed as `pharma` on 7 Nov, is now "sector unnamed: filed as
"pharma" from Yahoo's labels before an analysis named sectors". It is not offered, the watchdog
names it, and Saturday's run re-dives it first. Its analysis's reasoned `generic` becomes its key.
MUTECO, shelved with no sector answer, is re-dived on 21 Nov and dropped on 28 Nov with "re-dive
2026-11-28: no sector key after 2 re-dives in a row (the analysis gave no sector answer)": three
analyses in all, against 13 by 6 Feb before.

## What changed

- **M2, the ETF flows (`mf_herding.get_sector_mf_herding`):** no automobile fallback. A sector
  without an ETF list (the generic graph, every non-native key, an empty string) returns `error`
  `NO_SECTOR_ETFS` ("no_sector_etfs") with no network call and no funds.
  `bundle_builder._fetch_flows_sentiment` passes the graph's sector as it is (no `or "automobile"`)
  and puts "MF herding: no sector ETFs for <sector>" in the section's reason. The four native lists
  are unchanged. The legacy `ContextBuilder` sentiment builder calls the same function, so a
  non-native sector reads no funds there either.
- **R1 (`peers.lookup_profile`):** an answer with a market cap and neither an industry nor a sector
  raises `ProfileCallFailed`, so `_refresh` counts a failed lookup and stores nothing. An entry of
  that shape already in the file (`hidden_failure`) is due again whatever its age, and the stock's
  own such entry reads "the industry of X could not be looked up", never "no industry".
- **R2 (`peers._save_profiles`):** under a `filelock.FileLock` on `peer_profiles.json.lock`
  (timeout 10 s), it reads the file again, merges (`merge_profiles`: the later `as_of` wins, this
  build's on a tie, an undatable entry is older), and writes through
  `core.utils.atomic_io.atomic_write_json` (unique temporary file, `os.replace`). It returns what it
  saved, and the choice uses that. A lock timeout or write error writes nothing.
- **L1 (`sector_naming`):** `SectorReading.named_on` (new, default "") records the day the dive's
  analysis named the key. `decide_key(…, on=, named_on=)` sets it for an answer that names the key
  and carries it for a key kept as "earlier". `analysis_named` (true when the reading has `named_on`,
  or its own analysis answered that very key) replaces "any configured key" in `known_key`.
  `key_decided` (an analysis named it, the reading came from a managed record, or the ticker map
  has that key now) decides `unnamed_why`, `shelf.cap_key` and `apply_redives`' re-key. An
  undecided configured key reads 'filed as "<key>" from Yahoo's labels before an analysis named
  sectors' ('… from the ticker map, which no longer has it' when the map moved). So such an idea is
  not offered, not capped, not promotable by hand, named by the watchdog, first among Saturday's
  re-dives, and re-keyed by that analysis. `deep_dive` passes the dive date and the idea's
  `analysis_named_on`.
- **L2 (`shelf.apply_redives`):** `ShelfIdea.unnamed_redives` (new, default 0) counts re-dives in a
  row that leave the idea unnamed; one that names it resets it. At `discovery.max_unnamed_redives`
  (config 2, code fallback 2, 0 = no limit) the idea is dropped with the reason and a `dropped`
  event, not refreshed.
- **Config:** `config.yaml` `discovery.max_unnamed_redives: 2`; `base.py`
  `DISCOVERY_MAX_UNNAMED_REDIVES`.
- **Docs:** KT (`TECHNICAL_DESIGN.md`) section 3 (a configuration row; the peer-profile record's
  lock and merge), section 4 (the peer cache's failure and merge rules), section 8 (re-dive step 4:
  table keys and the unnamed bound; sector naming: `named_on`, what decides a key, the flows line;
  "nothing is silently generic"), section 11 (the automobile-ETF clause removed); section 12's row
  stays "Open" until review. CODEBASE.md (config row, shelf and sector-naming rows),
  AUTOPILOT_GUIDE.md (who is a candidate), PRODUCT_MAP.md (MF herding row), new guide case
  **06-O**, PDF regenerated (71 pages).

## Decisions (delegated technical calls; the owner delegated routing and technical calls on 13 Oct)

- **D1 (R1): a market cap with no profile is a failure; not a one-day expiry.** The card offered
  both. In SA-044's reviewer live table (200 registry listings read from Yahoo on 12 Nov,
  `analysis_data/sa044_review/rv_live_profiles.json`), no healthy answer had a cap without an
  industry; the 7 answers without an industry (codes Yahoo does not list under that symbol) had no
  cap either, and they stay cached. A one-day expiry would keep a transient error for the rest of
  the day, which is the whole 16:30 review. *Example:* SUNPHARMA during a quoteSummary outage reads
  "could not be looked up" and is asked again by the next analysis; with Yahoo back, its industry
  is stored. Cost: a listing Yahoo would really answer with a cap and no profile is asked on every
  build (none in the 200).
- **D2 (R2): merge under a file lock, not "a lost fill only costs lookups".** A fill lost to the
  other worker costs up to 25 extra Yahoo calls in the next analysis, and a torn read once restarted
  the file empty. The merge is a few lines and keeps both. *Example:* worker A saves X while worker B,
  which read the file before, saves Y: the file holds X and Y (a two-process test adds 25 profiles
  from each process at once and finds all 50).
- **D3 (M2): no other sector's funds, and the reason says so.** The line is not invented for a
  sector without a list: the bundle's text has no MF block, and the flows section's reason (in the
  data-health row) reads "MF herding: no sector ETFs for generic". Adding ETF lists for more
  sectors is SA-026's (sector lenses).
- **D4 (L1): decided = an analysis named it, a managed record held it, or the ticker map has it;
  table keys join the first re-dive group.**
  - `named_on` is needed because FIX-026's re-dives store the latest reading: without it, a key an
    analysis named and a later re-dive kept while answering otherwise could not be told from a table
    key the 14 Nov run (still FIX-026's code) keeps the same way.
  - A FIX-026-era reading that answered its own key counts as named: if Saturday's re-dive of a
    table-keyed drug maker answers `pharma`, it is decided and is not dived again a week later.
  - Such ideas join the first re-dive group rather than wait up to 30 days, because until then they
    are offered and capped under a key no analysis chose.
  - **Budget:** one analysis per table-keyed idea, once, from the week's 20 calls (re-dives take the
    budget first but never the IPO slots). At most the shelf's active ideas outside the ticker map
    (the shelf holds 20). **Measured 13 Nov** (the owner's probe, below): **7** table-keyed ideas
    of 19 active, so D4 costs 7 analyses, once, out of the 18 calls the IPO slots leave.
  - *Hard review:* a managed stock's key is never changed (`known_key` reads the managed record
    first; the managed file is not written), a ticker-map stock's idea is decided by the map, and a
    holding's sector is never touched. The one re-key a managed stock's idea can get is to its
    managed record's own key, which is where its forecasts already live. A re-keyed shelf idea's
    paper lane writes under the new key, as FIX-026 accepted for `generic`.
- **D5 (L2): dropped, not moved to a monthly cadence.** At a monthly cadence an unnamed idea still
  refreshes its dive date at every passing re-dive, so it never rotates out and holds a shelf place
  for good while nothing can buy it. Dropped with the reason, it frees the place; the dive memo keeps
  it from a new dive for 30 days, and after that the screen may bring it back with a fresh count.
  *Example:* MUTECO costs 3 analyses (14, 21, 28 Nov), against 13 by 6 Feb. A re-dive that names it
  resets the count.

## M1 — not built (conditional, evidence not yet available)

The card builds M1 "only if Saturday shows it": most dives unnamed with "the analysis gave no sector
answer". Saturday 14 Nov's run had not happened when this phase ran, and FIX-026's bench saw all 3
analyses answer the question. So no prompt changed: every analysis, with or without the question,
sends the prompt FIX-026 sends. **For the fresh review:** read Saturday 14 Nov's Discovery line
`sectors=[…]` and the "Discovery sectors" lines (guide 06-M; counts and symbols only). If most dives
are unnamed with "no sector answer", M1 is due: route it as a small follow-up (the system prompt's
"no keys beyond the schema" rule allows the one extra block when the question is asked), rather
than holding the rest. If not, M1 closes as not occurring.

## Tests

Every expected value is worked out by hand in the test's docstring, never read back from the code.
No test reaches the network; the analyst is FIX-026's stub world, Yahoo's transport is stubbed at
yfinance's `YfData.get_raw_json` (yfinance 1.3.0's real `Ticker.info` runs), mfapi.in and NSE are
stubs.

- **Story file** `tests/unit/test_generic_evidence_fix030.py`, 38 tests, all pass:
  - M2 (11): no funds and no call for `generic`, `pharma`, `hospitals` and ""; the four native ETF
    lists by scheme code (hand copied); the generic flows line's reason and text; MARUTI's flows
    keep the auto ETFs; a whole `build_sector_bundle(…, "generic")` for SUNPHARMA, with the real
    peers and flows sections, names no car maker and no auto ETF anywhere in the two sections,
    their provenance or the prompt text.
  - R1 (10): the SA-044 reviewer's RV4 inverted (no store; asked again the same day; with Yahoo back
    the next day, PHARMA); a code Yahoo does not list stays cached (no call the next day); an
    entry stored before the fix is due again and reads "could not be looked up"; seven `.info`
    shapes by hand (only a cap with neither industry nor sector raises).
  - R2 (4): RV5 inverted; the merge rule by hand (later wins, tie keeps this build's, undatable is
    older); a held lock writes nothing; **two real Python processes** each saving 25 profiles at
    once keep all 50.
  - L1 (7): RV1 inverted (ODDCO not offered, watchdog names it, due on 14 Nov at 7 days old,
    becomes `generic` with source "analysis", event "sector pharma -> generic"); a FIX-026-era
    "earlier" reading with another answer is still re-examined; one that answered its own key is
    decided (offered; due at 35 days, not 28); an analysis-named key survives a disagreeing and an
    empty re-dive with `named_on` carried; a managed stock and a ticker-map stock are never
    re-keyed (the managed list unchanged; SOLDAUTO's idea takes its managed key); D4's first group
    by hand (two table keys, oldest first, of five ideas); a table key counts in no cap.
  - L2 (6): RV2 inverted (21 Nov kept with count 1, 28 Nov dropped with the exact reason, not due
    5 Dec, 3 calls; the dive memo holds it to 30 days); naming resets the count (next due 2 Jan,
    not 26 Dec); a legacy `generic` idea counts the same (reason names "Healthcare"); limit 0 keeps
    the weekly re-dive; the shipped limit is 2; a `shelf.json` from before FIX-030 loads with 0 and
    "".
- **On the baseline** (the same file in a detached worktree of `5ae2749`): 27 fail, 11 pass. The 11
  are the unchanged-behaviour guards: the four native ETF lists, MARUTI's flows line, the unlisted
  code staying cached, and the five `.info` shapes that were never failures
  (`analysis_data/fix030/story_tests_on_baseline.txt`).
- **The reviewers' own cases on this tree** (`analysis_data/fix026_review2/test_rv_fix026_review2.py`
  copied in temporarily, and `analysis_data/sa044_review/test_rv_sa044.py`): 15 pass; RV1 and RV2
  (characterisations of L1 and L2), SA-044's RV4 characterisation, and SA-044's strict xfails RV4
  contract and RV5 now fail as `XPASS(strict)`, that is, the contracts hold.
- **Changed existing tests** (fixtures only, no assertion loosened):
  - `test_sector_naming_fix026.py`: the exact reading now carries `named_on="2026-11-14"`; the
    property test's independent oracle adds FIX-030's rule (a configured key offered only when its
    reading records `named_on`, answered that very key, or came from a managed record), and its
    random pool gains two "earlier" readings, one with and one without `named_on`.
  - Shelf-idea helpers that built a configured key with no reading now give it the analysis
    reading such an idea has carried since FIX-026: `test_deploy_idle_cash_sa049._idea` (not for
    `generic`), `test_regime_inputs_fix023._idea`, `test_sizing_rule_sa050._idea`,
    `test_discovery_shelf._dive`, and PR-004's stale-idea test.
  - `test_peer_choice_sa044.py`: NOCLASS (the "Yahoo gives no industry" stock) has no market cap,
    as Yahoo's real "no industry" answers have (D1); with a cap it is now a failed lookup.
- **Neighbouring suites:** 34 discovery, portfolio, peers, bundle and data-health files: 1,257
  passed and 4 failed (SA-050's `_idea` fixture, used by SA-048's pipeline test too); after that
  fixture's fix, those two files 52 passed. The story file with SA-044's two peer files: 112
  passed.
- **Mutants:** 18 of 18 caught by the story file alone (`analysis_data/fix030/mutants.py` in the
  worktree synced to the final tree; `mutants.txt`): the ETF fallback restored; the reason dropped;
  a failure stored; a sector-only answer treated as a failure; an old failure not due, or read as
  "no industry"; this build always winning the merge; no merge; `named_on` ignored; the
  answer-equals-key rule removed or made always true; `known_key` back to FIX-026's; `named_on` not
  carried; `unnamed_why` ignoring the rule; the re-key and the cap back to `key_named`; the drop
  off by one; the count never reset.
- **Full suite:** run 1 (09:35–09:57 IST): 6,419 passed / 12 skipped / 1 xfailed / **1 failed**,
  `test_discovery_shelf.py::test_promote_to_watchlist`: its `_dive` fixture had no reading, so the
  manual promote was refused (`sector_unnamed`), the intended L1 behaviour; fixed in the fixture as
  above. Run 2 on the final bytes (09:59–10:17 IST): **6,420 passed / 12 skipped / 1 xfailed / 0
  failed**, rc 0, 18m29s; `git status` the same before and after
  (`analysis_data/fix030/full_suite*.txt`, `run1_*`).
- `check_broad_except`: OK (148 grandfathered). `check_kt_docs`: `errors: []` after the PDF was
  regenerated (71 pages, source `c80021fb`; it reported only the stale PDF before).

## Production probe (run by the owner, 13 Nov, before Saturday's run)

`analysis_data/fix030/prod_probe.py` (ignored, local to this laptop) is read-only and prints
counts only. It applies D4's rule itself, so it runs on the code production has now. It reports:
the active ideas by reading source, `L1_table_keys_first_redive_group` (D4's budget), the unnamed
ideas by problem (L2's cohort), and the peer cache's `R1_sign_empty_industry_with_cap`. Checked
locally on a made-up shelf of 6 ideas (2 table keys, 1 unnamed, 2 decided, 1 dropped): the counts
match by hand. The owner runs it from Git Bash in the repository:

```text
railway ssh "cd /app && echo $(gzip -9c analysis_data/fix030/prod_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

**Measured** (the owner ran it Friday 13 Nov at about 12:20 IST, on production's `f368f20`, before
FIX-030 and before Saturday 14 Nov's 12:30 run; counts only, kept as
`analysis_data/fix030/probe_2026-11-13.json`, ignored):

| Count | Value | What it means |
| --- | --- | --- |
| Active ideas | 19 | |
| … with a sector reading | 0 | All 19 were last analysed before FIX-026 went live (10 Nov, about 13:20); the last run was 7 Nov. |
| … decided (the ticker map has the key) | 4 | Offered before and after FIX-030. |
| … table key, no analysis named it (L1) | 7 | All last analysed 7 Nov. D4's budget: 7 analyses, once. |
| … no configured key (L2's cohort) | 8 | Already unnamed and re-dived first on today's code, so Saturday 14 Nov re-dives them: M1's test. |
| … named `generic` | 0 | |
| Peer cache profiles | 218 | |
| … no industry | 7 | All 7 have no market cap: real "no industry" answers, kept by D1. |
| … R1's sign (no industry, with a cap) | 0 | The re-lookup of entries stored before the fix touches none today. |

What it shows (inference from these counts and the code):

- The 7 table-keyed ideas were analysed 7 Nov, well inside the 30-day re-dive age, so Saturday
  14 Nov's run (FIX-026's code, which sets no key from the table) most likely leaves them as they
  are. The 7 is the most the first FIX-030 Saturday re-dives for L1. A re-dive on 14 Nov that
  answers an idea's own key lowers it.
- That first FIX-030 Saturday re-dives at most 15 ideas from today's shelf (the 7 plus any of the 8
  that Saturday 14 Nov leaves unnamed), before sold stocks and new unnamed ideas. That leaves at
  least 3 of the 18 non-IPO calls for new screen ideas that one week.
- A re-run after Saturday's run is optional: it gives the exact number for the first FIX-030
  Saturday.

## Rollout (what deploying changes, with the switch off)

- Every generic-graph analysis (a discovery dive, a holding under a non-native key in the daily
  review and the monthly forecast) loses its MF herding block; native graphs are unchanged. The
  analyst's flow scores for those stocks may move; no decision rule changes.
- The first Saturday after the deploy re-dives every table-keyed idea first (D4's budget; 7 on
  13 Nov). Until then those ideas are not offered, and the watchdog's `sector_keys_named` notice
  goes pending, naming each one (at most weekly). *Timing:* a deploy in the early hours of a
  Saturday (00:10–06:20 IST, before the 12:30 run) holds them back on no trading day; a deploy on
  Sunday 15 Nov holds them back Monday to Friday, 16–20 Nov.
- An unnamed idea's second unnamed re-dive in a row drops it. Ideas already re-dived unnamed before
  the deploy start at a count of 0.
- Cached R1-shaped peer profiles are looked up again (at most 25 per analysis), then stored only
  when Yahoo answers with a profile.
- `shelf.json` and the dive readings gain two fields with defaults; older files load unchanged
  (tested). Rollback is a revert: the old code ignores the extra fields.
- **Deploy after Saturday 14 Nov's discovery run**, so that run's counts measure M2 and M1 on the
  code the card describes; and before about Sat 12 Dec, when the first ideas FIX-026 named would come
  due for re-dives under FIX-026's code (their kept readings would carry no `named_on`; D4 still
  counts any that answered their own key).

## Not covered / found on the way

- `bundle_builder._DEFAULT_BUNDLE_CFG` is automobile's configuration, for a sector string that is
  not registered. No orchestrator passes one (each passes its own `SECTOR_NAME`, and `generic` has
  its own configuration), so it is not reachable today. Not changed; worth a line in SA-026.
- `ContextBuilder`'s sentiment builder still defaults an unset sector to `automobile`, the legacy
  automobile pool's own sector. Not a generic-graph path.
- M1 (above).

## Review input

- Manifest: [FIX-030-manifest.json](FIX-030-manifest.json), SHA-256
  `0fdb3de2869a00ab430a106eea5f18e2ea4f94f72148225a2344a51ed7e2136f`, 23 files
  (`scripts/docs/kt_manifest.py verify`: 0 mismatches).
- Diff against HEAD `5ae2749`, the PDF excluded: SHA-256
  `f21996169bd149031221d1601551cbc21569fc7c62db437cff719a725953dd09`, 106,231 bytes, 22 paths, via
  `analysis_data/fix030/digest.py` (a temporary index; the real index is untouched). End tree
  `67ccdf4f3d773fa8e5ce0ab544dc2e4d0b25e5a3`, taken before this receipt's last figures and the
  STATE/HANDOFF splice. No file outside the manifest changed but the bookkeeping.
- Outside the manifest: STATE, HANDOFF, this receipt and the manifest (bookkeeping), and the
  uncommitted `5ae2749` push record already in STATE and HANDOFF.
- On another device: `git diff 5ae2749` over the manifest's paths but the PDF, sorted,
  `core.autocrlf=false`, with the new test file added.

## What a fresh review should press on

1. Saturday 14 Nov's counts: M1 (above) and how many dives were disputed `automobile` (M2's size
   in production, on the code before this story).
2. D4: can any path re-key a held or managed stock, or move a forecast history (the card's hard
   review)? `known_key`'s order, `apply_redives`' re-key and `candidates.buy_candidates`' managed
   branch.
3. D4's FIX-026-era readings: a table key that the 14 Nov run keeps while its analysis answers the
   same key counts as named. Is that the card's "an analysis named it"?
4. D1 on a cold production cache: whether any real listing answers a cap with no profile.
5. D2 on Linux: `filelock` on the Railway volume, and the lock file it leaves beside the cache.
