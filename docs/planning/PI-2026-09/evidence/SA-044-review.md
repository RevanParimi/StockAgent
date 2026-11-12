# SA-044 — fresh review receipt

**Story:** [SA-044](../stories/SA-044.md): compare valuations only with same-industry peers.

**Context:** fresh-session review, 12 Nov 2026, about 22:10–22:40 IST. Session `stockagent-main-01`
[c2f96f], a new conversation opened with "continue". It is not the implementing session
(`stockagent-main-90`). After a fetch, `origin/main` was `3489f50`, the same as HEAD: nothing had
arrived from the other device. Ten peer sessions were idle.

**Verdict: ACCEPTED** for the committed code `f368f20` (deployed since 14:35 IST on 12 Nov). Every
acceptance criterion holds. Findings: one medium (R1, a transient Yahoo error is cached as "no
industry" for 30 days) and one low (R2, two processes can overwrite each other's cache fill). Both
fail safe: the cache can lose peers, but it never names one from another industry or moves a gate.
Both are routed to [FIX-030](../stories/FIX-030.md). Nothing was committed, pushed, deployed or
configured. No production state, log or environment was read. No LLM was called and no message was
sent. One local check read Yahoo Finance's public data from this laptop (the card's hard review).

## Reviewed input

- **Code:** `f368f20`, committed before this review, as FIX-028's was. `e511f50..f368f20` changes
  exactly the manifest's 10 code, test and config files, and nothing else.
- **Digests**, verified by `analysis_data/sa044_review/rv_digest.py`, which writes nothing tracked:
  - manifest [SA-044-manifest.json](SA-044-manifest.json): SHA-256
    `24d605b08a1e155766b2fa0e206abce0afd856105a74cc0bdac786cce5af9ea8`, 13 files;
  - the implementer's diff, base tree `a3ef9c4b` to end tree `b9b9ebdb` (both still in this
    checkout), recomputed: 81,529 B, SHA-256 `c769970a27348f3d34a93c5c280db70ec993b7a715041f49246cd6beb073a6bf`,
    the same as the receipt's;
  - its code, test and config part equals `git diff e511f50 f368f20` over those paths, byte for byte
    (65,990 B, SHA-256 `e7912934036727b37e803e36c6bf376f96968ab28bc6ec21895222a6ac92d1bf`); every
    one of those blobs at HEAD equals the manifest's.
- **The docs:** the KT and the guide differ from the manifest only by the commit-time and deploy
  edits of `6a2b83a` and `3489f50` (14 lines). They were read as they stand at HEAD.

## Contract checked

The card's five criteria, its SA-002 routed input (the automobile fallback search), and FIX-011's
routed input (Yahoo's industry, not NSE's). Decision D1, confirmed by the owner, is that a stock with
no peers is judged on its own numbers. The review checked that D1 holds on every path where a peer
comparison can be missing:
- `choose_peers` never raises;
- with no peers, `_fetch_peers_valuation` only adds text;
- `get_valuation_result` appends "no peers to compare with" after the source is decided and leaves
  the status rules alone;
- a failed peer P/E keeps `ok`;
- the legacy builder changes only text.

The gate reads section statuses. From the provenance it reads only the technicals symbol
(`base_orchestrator.py:725`). So the `peers` note cannot move a gate.

## Independent adversarial examples

- **RV1: a hospital chain with no peers, traced from input to every consumer** (reviewer cases,
  `analysis_data/sa044_review/test_rv_sa044.py`). Only yfinance, the price history, Serper and NSE
  are stubbed; the profile lookup is the real one.
  - The input: APOLLOHOSP ("Medical Care Facilities") on the generic graph. The universe holds car
    makers and two drug makers.
  - The prompt section opens `peers unavailable: 0 other known symbol(s) in Yahoo industry "Medical
    Care Facilities", 3 needed …` and tells the analyst to use the company's own ratios. It names no
    car maker. No search of any kind is made.
  - The data-health row is persisted by the real `record_data_health` and read back from its JSONL:
    `sections.peers_valuation` is `ok`, and both `section_provenance.peers_valuation.peers` and its
    `reason` start "peers unavailable".
  - The gate built from that row may act. `dg.is_actionable` is the predicate both consumers use:
    `shelf.apply_redives` (shelf.py:493) and `candidates.watchlist_idea` (candidates.py:182).
  - **Control:** the same stock with its own prices missing is `fallback`, an essential section is
    unusable, and the gate abstains. So the test can tell the two cases apart.
- **The original defect:** `test_rv_baseline.py` and the story's regression test both fail on
  `e511f50`, naming MARUTI, TATAMOTORS, M&M, HEROMOTOCO and BAJAJ-AUTO. Both pass at HEAD.
- **RV2: every registry ticker on real Yahoo industries.** The table comes from this review's own
  live run (below). For each of the 202 registry tickers, a warm cache is checked against a
  brute-force oracle written for this review. The oracle uses a larger-over-smaller cap ratio and
  the instrument registry's identities.
  - Every peer has the stock's industry.
  - No peer is the stock itself, a duplicate listing or TATAMOTORS.
  - Every list has 0 or 3–5 names, equal to the oracle's.
  - No lookup is made. 132 tickers get peers.
- **RV3: a cold cache with the production budget** (25 lookups per build, 30 days), over the 202
  registry tickers in order:
  - lookups per build: 25 ×7, then 23, then 0. The 9th build was the first with no lookup. 198
    lookups in all;
  - every build keeps the invariant;
  - no build's list is shorter than its warm-cache list, because the stock's sector is looked up
    first. One build chose other names from the same industry.

## The card's hard review (local, Yahoo public data, not production)

`analysis_data/sa044_review/rv_live.py` ran from an empty scratch directory: 23 stocks, about
100 s. That is one stock per registry sector key (four native graphs, every generic key) and two
discovery stocks outside the registry. Every named peer's industry, and the stock's, was then
**re-fetched with a separate direct yfinance call**, not the cache: 85 lookups, **0 mismatches**.

| Stock (graph) | Result |
|---|---|
| TVSMOTORS (automobile) | Auto Manufacturers (5): EICHERMOT, BAJAJ-AUTO, M&M, MARUTI, TMPV |
| AXISBANK (banking) | Banks - Regional (5): KOTAKBANK, SBIN, PNB, ICICIBANK, BANKBARODA |
| WIPRO (IT) | Information Technology Services (5): TECHM, LTIM, HCLTECH, PERSISTENT, COFORGE |
| NHPC (renewable) | Utilities - Renewable (3): ADANIGREEN, SJVN, INOXGREEN |
| UPL, BEL, PIDILITIND, MAZDA, DABUR, INDHOTEL, SBILIFE, DELHIVERY, IOC, CIPLA, DLF, BHARTIARTL (generic) | 3–5 peers each, every one in the stock's own industry |
| ULTRACEMCO, SUNTV, HINDALCO, TRENT, DIXON, POLYCAB, CDSL (generic) | `peers unavailable` (0–2 others in the industry) |

Seven registry codes are unknown to Yahoo (ACCCEMENT, APL, BAYER, DEEPAKNITRI, MAHINDHOTEL, MTAR,
NIIT). They are cached as "no industry" with no market cap. That is the right answer for a code that
lists nothing, and it is why ULTRACEMCO has only 2 building-materials peers (ACC is filed as
ACCCEMENT; [FIX-020](../stories/FIX-020.md) corrects it).

## Findings

| # | Severity | Where | Finding | Disposition |
|---|---|---|---|---|
| R1 | medium | `services/data/context/peers.py` `lookup_profile` (157–168), stored by `_refresh` (244–251) | **A transient Yahoo error is cached as "no industry" for 30 days.** yfinance 1.3.0 hides HTTP errors by default (`YfConfig.debug.hide_exceptions = True`). A non-429 error on the quoteSummary endpoint, where the industry lives, is logged and swallowed. If the quote endpoint answers, `.info` comes back with a market cap and no industry. `lookup_profile` does not raise, so `_refresh` stores `industry: ""` with today's date. **Trigger** (RV4, through yfinance's real `Ticker.info` code; transport stubbed at `YfData.get_raw_json`): quoteSummary answers 500 and the quote call answers. SUNPHARMA reads `peers unavailable: Yahoo gives no industry for SUNPHARMA`. The next day Yahoo is healthy, and it still reads the same with no call made. Expected, per the docstring and the receipt ("raises when the call fails, so a failure is never cached as an answer"): no profile is stored, and a later build asks again. **Impact:** for up to `cache_days` that stock has no peer comparison, and the reason blames Yahoo's classification; or that candidate is left out of every peer list. It fails safe: no other industry's peer, and no status or gate change (D1). How often it happens in production is not measured. Its sign is a cached profile with a market cap and no industry; the probe below counts those. Locally: 0 of 200. | Follow-up in [FIX-030](../stories/FIX-030.md) (routed input added): store a profile only when Yahoo's answer carries a profile, or keep an empty-industry answer for a day rather than 30. Strict xfail `test_rv4_contract_a_failure_is_never_stored` turns green when fixed. |
| R2 | low | `peers.py` `_save_profiles` (193–201), `_LOCK` (61) | **Two processes can overwrite each other's fill.** Production runs `uvicorn … --workers 2` (Dockerfile:48). The fill is a read-modify-write under a thread lock only, and it writes a fixed `peer_profiles.tmp`. AUD-057's `atomic_write_json` (unique temp name) was written for exactly this case. With two processes filling at once, the last save drops the other's new profiles (RV5, interleaving by hand). A torn read starts empty, and its save then replaces the whole file. **Impact:** extra Yahoo lookups and, for a few builds, fewer peers. Never a wrong one. | Follow-up in FIX-030: write with `atomic_write_json`; merge the file read again inside the save, or accept the loss and say so. Strict xfail `test_rv5_two_processes_keep_both_fills`. |
| O1 | info | `services/data/fetchers/fundamentals.py:193`, `settings.PEER_TICKERS` | `get_peer_margins` still defaults to the automobile list. It has no caller (as FIX-003's review found), so no stock is affected. | Delete when peers move into lenses ([SA-026](../stories/SA-026.md)). |
| O2 | info | automobile prompts (`unified.py:82`, legacy `valuation_catalyst.py:47`) | The automobile graph's prompts name car makers as margin and P/E peers. The registry's automobile key also holds tyre and parts makers (APOLLOTYRE, BALKRISIND, BOSCHLTD, ENDURANCE), whose peers section now names their own industry. This is prompt text, not a peer list, so the card's criteria hold. | SA-026 (lens KPIs and peers). |
| O3 | info (inference) | `src/backend/sectors/registry.py:167` | MAZDA is filed under `defence`. NSE's MAZDA is Mazda Ltd, a vacuum-equipment maker (Yahoo: "Specialty Industrial Machinery"). Mazagon Dock is MAZDOCK. Not verified against the registry's intent. | Note added to FIX-020 to check. |

No critical or high finding. None of the receipt's claims about the acceptance criteria is
contradicted.

## The receipt's four press points

1. **D1 everywhere:** holds (Contract checked; RV1 and its control).
2. **Live hard review:** done independently. The implementer's own check compared the peers with
   the cache it had just built; this one re-fetched every name directly.
3. **Budget on a cold volume:** RV3. The cache fills in 8 builds, and no build's list is shorter than
   warm. Today's production latency was not read; the daily review runs sequentially with a 300 s
   per-ticker budget (`scheduler.py:880`), so 25 lookups fit. The chat tool's 45 s analysis could time
   out only while the cache is cold.
4. **Order and granularity:** nearest-by-ratio and "unknown caps last" are sound. Exact industry is
   strict: TATAPOWER is not with ADANIGREEN, and HINDALCO is alone in "Aluminum". That is the card's
   rule. A wider peer group is a product choice for SA-026's lenses. Not a defect.

## Documentation

- KT section 4 "Valuation peers", the configuration and persistent-records rows, section 8's sentence
  and guide case 02-O describe the reviewed behaviour.
- `check_kt_docs`: `errors: []` (PDF 70 pages, source `57cf600d`, header `f368f20`, no linked source
  changed since).
- KT section 4 does not repeat the docstring's "a failure is never stored", so R1 makes no KT sentence
  wrong.

## Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), hermetic suite (`tests/hermetic.py`).

- Focused: `pytest -q -p no:cacheprovider` over the story file, the regression, `test_bundle_builder_sectors.py`,
  `test_bundle_builder.py`, `test_unified_analyst_generic.py`, `test_data_health_contract.py`,
  `test_data_health_record.py`, `test_sector_benchmark_sa010.py`, `test_bank_statement_fix003.py`:
  **410 passed** (84 s).
- Reviewer cases `analysis_data/sa044_review/test_rv_sa044.py`: **6 passed, 2 strict xfailed** (R1,
  R2), 64 s. `test_rv_baseline.py`: passes at HEAD; on a detached worktree of `e511f50`, it and the
  story's regression **fail** with the five car makers (worktree removed).
- `scripts/ci/check_broad_except.py`: OK (148). `scripts/docs/check_kt_docs.py`: `errors: []`.
- Live: `rv_live.py` (above), output `analysis_data/sa044_review/rv_live_out.json` (ignored).

**Not exercised:**
- The full suite was not re-run. The implementer ran it on these bytes three times (latest 6,382
  passed / 0 failed on `3489f50`), and the code is unchanged since (digests above).
- No LLM saw the new section.
- Production was not read. R1's production frequency and the first review's latency are unknown.
- R2 was shown by interleaving by hand, not by a real two-process race.

## Production verification (separate from this acceptance)

Status stays `pending_observation`. It shows no benefit by itself.

A counts-only, read-only probe is ready: `analysis_data/sa044_review/prod_probe.py`. It prints no
tickers and no logs. It reports:
- the cache's size and dates;
- how many profiles have no industry, and how many carry R1's sign;
- the data-health rows since the deploy: chosen against `peers unavailable` and why, the section's
  statuses, and the industries chosen.

The owner runs it from Git Bash in the repository:

```
railway ssh "cd /app && echo $(gzip -9c analysis_data/sa044_review/prod_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

**Pass:** every `peers_valuation` status comes from the stock's own data (none `fallback` because of
peers). The chosen industries look like the stocks reviewed. `empty_industry_with_cap_R1_signature`
is 0, or small and named in FIX-030.

## Commit-time edits (when the owner gives the word)

1. KT section 1, the SA-044 clause: "(a valuation is compared only with same-industry peers;
   committed at the owner's word before its fresh review)" becomes "(a valuation is compared only
   with same-industry peers; its fresh review accepted it on 12 November)".
2. KT section 12, SA-044's row: `Open` becomes `Done`.
3. Guide 02-O, the status: "… deployed 12 Nov 2026; fresh review pending." becomes "… deployed 12 Nov
   2026; accepted by its fresh review 2026-11-12."
4. Regenerate the PDF; `check_kt_docs` `errors: []`.

**Applied** in the docs commit after `3489f50`, at the owner's word ("commit and push", 12 Nov,
about 22:45 IST). The PDF has 70 pages, source `28fce89c`. `check_kt_docs` gives `errors: []`.

## Decision

**Accepted:** `f368f20` for SA-044. STATE: SA-044 `done` with a `review` entry; production
`pending_observation`; `active_task` null; `next_task` FIX-030 (its implementation, in a new
conversation), which now carries R1 and R2. The switch stays off. The Saturday 14 Nov watch (disputed
dives filed `automobile`) still applies.
