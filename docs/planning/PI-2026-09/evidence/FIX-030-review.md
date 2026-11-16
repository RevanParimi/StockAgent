# FIX-030 — fresh review receipt

**Story:** [FIX-030](../stories/FIX-030.md): a generic-graph analysis sees no automobile evidence;
a key the old Yahoo table set is re-examined; an unnamed idea stops taking a weekly re-dive. With
SA-044's routed R1 and R2 (the peer cache).

**Review context:** fresh-session review, session `stockagent-main-1c` [1c91a3], a new
conversation opened with "continue", Friday 13 Nov 2026, about 12:51–13:35 IST. `origin/main` was
`5ae2749`, the same as HEAD, so nothing had arrived from the other device. Twelve peer sessions
were idle, the implementer `stockagent-main-99` among them. No production state was read, no LLM was
called, no message was sent, and no test reached the network. Nothing was committed.

**Verdict: accepted** for the reviewed revision below. Two low findings: a docs fix done at commit
time, and a routed note. M1 stays open until Saturday's counts are read (see "M1").

## Started before Saturday's counts

The card and HANDOFF say to read Saturday 14 Nov's Discovery counts first. This review ran on
Friday, before that run. **Decision (a delegated process call):** review now.

- Only M1 depends on the counts, and the card builds M1 "only if Saturday shows it".
- The counts measure production's code (`f368f20`), which FIX-030 does not change for M1: no
  prompt is in the diff.
- The owner's deploy already waits for Saturday's run.

So M1's disposition becomes a recorded check, `FIX-030-M1` in STATE's `pending_production_checks`,
run after Saturday's run and before FIX-030 is deployed. It does not hold the rest of the story.

## Input verified

`analysis_data/fix030_review/rv_digest.py` (writes nothing tracked; a temporary index) was run at
the start and at the end:

| | Start (12:53) | End |
| --- | --- | --- |
| HEAD | `5ae2749` = the baseline | `5ae2749` |
| Manifest | `0fdb3de2…` (23 files), `kt_manifest.py verify` 0 mismatches | the same, 0 mismatches |
| Diff against HEAD, the PDF excluded | `f2199616…`, 106,231 B, equal to the receipt | the same |
| Changed outside the manifest and the bookkeeping | none | only this review's SA-026 routed note |

The end tree differs from the receipt's `67ccdf4f` only by bookkeeping written after it (STATE,
HANDOFF, the receipt), as the receipt says.

## Contract checked

The card's "Intended result" and its five hard-review questions; REVIEW.md's checks of the data
flow, missing-data policy, compatibility, persistence under concurrency, and the tests' oracles.
Code read: `mf_herding.get_sector_mf_herding`, `bundle_builder._fetch_flows_sentiment` and
`_bundle_cfg`, the generic orchestrator's `SECTOR_NAME`, `peers.lookup_profile` / `_refresh` /
`_save_profiles` / `merge_profiles` / `hidden_failure` / `_choose`, yfinance 1.3.0's
`Quote._fetch` / `_fetch_additional_info` / `_fetch_info`, `sector_naming.analysis_named` /
`analysis_named_on` / `key_decided` / `known_key` / `decide_key` / `unnamed_why` / `status`,
`deep_dive.run_deep_dives` (managed keys, the managed skip, the budget), `shelf.cap_key` /
`apply_redives` / `redive_due` / `backfill_classification` / `apply_deep_dives`,
`candidates.buy_candidates`, the watchdog's `sector_keys`, `data_health.assess_health` and
`decision_gate.is_actionable`, and the discovery run's re-dive budget (`core/discovery/__init__.py`).

## Independent adversarial examples

Reviewer cases: `analysis_data/fix030_review/test_rv_fix030.py` (ignored, local to this laptop;
reviewer conftest = the suite's hermetic boundary and isolation fixtures). They borrow only
infrastructure: FIX-026's stub-analyst `world` and PR-004's EOD window. They use no helper of the
story file, and every expected value comes from this file's own oracle.

- **RV1, L1 and L2 as a state machine (6 seeds × 4 starting states × 10 runs × up to 5
  Saturdays).**
  - **Starting states:** a key FIX-011's table set on 7 Nov (no reading); a legacy `generic`; a key
    a FIX-026 analysis named (no `named_on`); a FIX-026 reasoned `generic`.
  - **Each Saturday:** the analysis answers at random `pharma`, `chemicals`, `generic` with a reason,
    nothing, or "Pharmaceuticals".
  - **Path:** the real `run_deep_dives` → `apply_redives` → `shelf.json`, then `redive_due` for the
    next Saturday and `buy_candidates` for the Monday.
  - **Oracle:** written from the card: a decided key never moves, and keeps the day it was named;
    an undecided key takes a named answer and is dated that Saturday; a reasoned `generic` is
    offered but not sticky; no answer, or not a key, counts one, and the second in a row drops the
    idea.
  - **Checked each week:** whether the idea is due, its key, its status, `unnamed_redives`,
    `key_decided`, `analysis_named_on`, whether Monday offers it, and the "sector unnamed" reason.
  - **Result:** all pass. On the baseline `5ae2749` every seed fails at the original L1 defect: the
    table key is not due.
- **RV2, the probe's shelf on the first FIX-030 Saturday.** The shelf matches the probe's counts:
  19 active ideas (4 in the ticker map, 7 with table keys dived 7 Nov, 8 legacy `generic`).
  - By hand on Sat 21 Nov: 15 are due first, and the 4 map ideas are not due.
  - The budget is 20 − 2 IPO slots = 18, so 3 calls are left for the screen.
  - Monday 16 Nov offers only the 4 map ideas. A table key counts in no sector cap.
  - Passes. On the baseline it fails: only the 8 are due.
- **RV3, a table-keyed idea whose stock is managed and held** (finding R2 below). HOLDCO's idea was
  filed `chemicals` by the table; the stock is managed under `pharma`.
  - Monday offers it under `pharma` (the managed branch).
  - Over 8 Saturdays it is in the first re-dive group every week. `run_deep_dives` skips it (managed,
    not sold) without spending budget: `max_n=1` still analyses CHEMCO.
  - It is never re-keyed, its count stays 0, and the managed list is unchanged. It rotates out on
    9 Jan (60 days).
  - Passes. On the baseline it fails: a table key was never due.
- **RV4, R1 with both of Yahoo's endpoints failing**, through yfinance 1.3.0's real `Ticker.info`
  with the transport stubbed at `YfData.get_raw_json`.
  - Three cases: HTTP 500 on both, HTTP 429 on both, and a curl connection error.
  - yfinance raises in every case: with both answers hidden its `_fetch_info` reads `None`.
  - So nothing is stored, three failures stop the build, and the note reads "could not be looked up".
  - Passes, also on the baseline (an unchanged guard).
- **RV5, R1's residual (characterisation).** The profile endpoint fails and the quote answers
  **without** a market cap. The answer is stored as "no industry" for `cache_days`, like a code
  Yahoo does not list: this is D1's accepted cost (finding I1).
- **RV6, R2 as a property (150 random interleavings).** Workers read the file at random points and
  save stale snapshots in any order, while the clock only moves forward. For every symbol, the file
  ends with its latest lookup, and no newer lookup is lost. Passes. On the baseline it fails: fills
  are lost.
- **RV7, M2 over every configured key.** Of the 22 keys plus `generic` and "", only the four native
  sectors read funds. Every other key returns `no_sector_etfs` with no fund, no call and an empty
  prompt block. Passes. On the baseline it fails: `agrochem` reads the auto ETFs.
- **RV8, M2's consumer: the data gate.** A generic flows section with both NSE parts empty is
  `empty` and reads "MF herding: no sector ETFs for generic".
  - With the other sections `ok`, the data-health verdict is `degraded`, not `hollow`, and nothing
    essential is unusable: `flows_sentiment` is not essential.
  - So `is_actionable` holds, and no generic analysis moves to abstain.
  - Passes. On the baseline it fails: generic read the funds.

On the baseline, the reviewer cases give 11 failed and 4 passed. The 4 are the unchanged guards
RV4 (×3) and RV5 (`analysis_data/fix030_review/baseline_rv.txt`).

## The card's hard review

1. **Does any generic-graph bundle still name another sector's peers or ETFs?** No.
   - ETFs: RV7, and the story's whole `build_sector_bundle(…, "generic")`.
   - Peers: SA-044.
   - The generic bundle configuration has its own news wording and no commodities.
   - `_DEFAULT_BUNDLE_CFG` (automobile's) is reached only by an unregistered sector string. Every
     orchestrator passes its own `SECTOR_NAME`, and the generic graph's is `generic`.
   - The legacy `ContextBuilder` still defaults an unset sector to `automobile`. It is the
     worker-pool fallback, which the gate abstains on (no provenance). It is in the implementer's
     receipt.
2. **Do native graphs keep their own peers and ETFs?** Yes: RV7, and the story's hand-copied
   scheme codes.
3. **Does any analysis without the question send a changed prompt?** No. No prompt, question or
   graph file is in the diff (M1 is not built). M2 removes data, the MF block, from generic-graph
   bundles only.
4. **Can L1's change re-key a held or managed stock, or move a forecast history?** No.
   - `known_key` reads the managed record first: every record, enabled or not, exactly as stored.
   - `buy_candidates` offers a managed stock under its managed key.
   - RV3: a managed stock's table-keyed idea is never re-keyed, and the managed list is not written.
   - A held stock is managed. Forecasts live under the managed key.
   - Only an undecided idea's paper lane moves to its new key, as FIX-026 accepted for `generic`.
5. **Can an idea that keeps failing to be named still take a weekly slot?**
   - When its analysis answers nothing or no key: no. It is dropped at the second unnamed re-dive in
     a row (RV1, and the story's RV2 inversion).
   - Two bounded exceptions:
     - A managed, unsold stock's undecided idea is listed first every week but never analysed: R2.
     - An idea whose analysis raises yields no dive, so L2 does not count it. It is re-dived each
       Saturday, one budget slot each, until its last good dive is 60 days old. This is
       pre-existing and the same for every unverified idea (code inspection; I3).

## The implementer's questions

- **Q1, Saturday's counts:** not available. See "M1".
- **Q2, D4 and held or managed stocks:** hard review item 4.
- **Q3, a FIX-026-era reading that kept a table key while its analysis answered that same key: is
  that "an analysis named it"?** Yes. `sector_question(classified, keys)` shows Yahoo's labels and
  the configured list, never the stored key (`deep_dive.py:161-162`), so the answer is the
  analysis's own. One caveat, inference: the call runs the stored key's graph (`route =
  known[0]`). For a native table key (`it_sector`, `banking_bfsi`), that graph's prompts are
  sector-specific. The case cannot arise before the deploy: the 7 table-keyed ideas are not due
  under FIX-026 until 7 Dec, and the receipt deploys before about 12 Dec.
- **Q4, D1 on a cold production cache:** not exercised (no network). Evidence for it: the owner's
  probe (0 of 218 entries with R1's sign) and SA-044's live table (0 of 200 healthy answers had a
  cap without an industry). RV4 shows a full outage is a failure. RV5 shows the one residual shape,
  which D1 accepted.
- **Q5, D2 on Linux:** not exercised. Inference: `filelock` takes `fcntl.flock` on Linux, which
  holds on the Railway volume's local filesystem. The `peer_profiles.json.lock` file it leaves is
  empty and harmless. The two-process test ran on Windows.

## Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
| --- | --- | --- | --- | --- | --- |
| R1 | low (docs) | [docs/AGENTIC_DESIGN.md:170-171](../../../AGENTIC_DESIGN.md) | The bundle table's `peers_valuation` row says "Peers from the sector's `TICKERS`; the automobile and generic graphs use the automobile peer list" (stale since SA-044, deployed 12 Nov); the `flows_sentiment` row does not say only the four native sectors have ETF lists. | A reader of the design doc believes the generic graph still reads car makers. | Commit-time edit 4 (below). Outside FIX-030's manifest, so it does not change the reviewed input. |
| R2 | low (edge, fail-safe; pre-existing pattern widened by L1) | `core/discovery/shelf.py:578` (`redive_due`'s unverified set reads `unnamed_why`) against `core/discovery/deep_dive.py:138` (a managed, unsold stock is skipped) | An undecided idea (a table key, as RV3 shows, or an unnamed one as under FIX-026) whose stock is managed and not sold: listed first every Saturday, never analysed, never counted by L2; the watchdog names it weekly; offered meanwhile under its managed key. Expected: one rule for "decided", as `known_key` has, reading the managed record. | Watchdog noise; when more ideas are due than the budget holds, it can defer another idea's re-dive by a week. Bounded by the 60-day rotation. Never re-keys, never buys outside its managed key. How often: not measured (the probe did not count managed ideas). | Routed to [SA-026](../stories/SA-026.md) (one sector-key contract), section "Routed input — 2026-11-13 FIX-030 review". Not a switch-on precondition. |
| I1 | info | `services/data/context/peers.py` `lookup_profile` (D1) | The profile endpoint fails while the quote answers with no market cap: stored as "no industry" for 30 days (RV5). | The card accepted it ("no industry, no cap may stay cached"). The probe's 7 no-cap entries are where it would show. | None. |
| I2 | info | `core/discovery/shelf.py:662` `backfill_classification` | It skips ideas with a `cap_key`. A table-keyed idea now has none, so each Saturday until it is named it costs one Yahoo classification call, and its labels are refreshed. | 7 calls once, then none. Harmless. | None. |
| I3 | info | `core/discovery/shelf.py` `apply_redives` / `rotate_stale` | An analysis that raises yields no dive, so L2 never counts it. | Re-dived weekly until stale (60 days). Pre-existing, and the same for every unverified idea. | None. |

No finding of medium or higher severity. No acceptance criterion is unmet, except M1, which is
conditional and recorded as a check.

## M1: the Saturday check before the deploy

STATE `pending_production_checks` `FIX-030-M1`, read-only, counts and symbols only. Run it after
Saturday 14 Nov's 12:30 discovery run (from about 14:00 IST), in the first "continue" conversation
that starts after then, before anything else, and before FIX-030 is deployed:

- **Read:** the 14 Nov `[Scheduler] Discovery …` line's `sectors=[named …, generic …, unnamed …,
  invalid …, disputed …, no Yahoo …, kept …]` and its `Discovery sectors …` lines. The owner reads
  them in Railway's log view filtered on "Discovery"; no raw log goes into a tool or a file. Then the
  owner re-runs the counts-only probe `analysis_data/fix030/prod_probe.py` (command in the
  implementation receipt); `L2_unnamed_by_problem` shows the shelf's ideas by problem.
- **Rule:**
  - If most of the week's dives are unnamed with "the analysis gave no sector answer", M1 occurs.
    It is routed as a new small card (P1, 1 point, before FIX-031): the system prompt's "no keys
    beyond the schema" rule allows the one extra block when the question is asked, and analyses
    without the question keep a byte-identical prompt.
  - Otherwise M1 closes as not occurring.
  - Either way, record how many disputed dives were filed `automobile` with non-automotive Yahoo
    labels: M2's size in production on the code before this story.
- **Then:** the deploy (owner's word, job-free window).

## Commands, environment, results

Windows 11, the `.stockai` venv (Python 3.13, yfinance 1.3.0), from the repository root. Every
pytest run is hermetic (`tests/hermetic.py`).

| Command | Result |
| --- | --- |
| `.stockai/Scripts/python.exe analysis_data/fix030_review/rv_digest.py start` / `end` | Input equal at start and end (table above) |
| `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-030-manifest.json` | 23 files, 0 mismatches |
| `python -m pytest -q -p no:cacheprovider analysis_data/fix030_review` | 15 passed. The first run (with `-x`, started at the same moment as the full suite) failed `test_rv1_l1_l2_state_machine[0]` with its traceback not captured. Three later runs of all six seeds pass (18 seed-runs), and so does the final run. Not reproduced and not attributed: recorded, not smoothed over. My own RV6 model let a worker's clock run backwards once (a test bug, fixed before the passing runs). |
| The same file in a detached worktree of `5ae2749` | 11 failed / 4 passed (above); worktree removed |
| `python -m pytest -q -p no:cacheprovider tests` (`analysis_data/fix030_review/run_suite.sh`) | 6,420 passed / 12 skipped / 1 xfailed / 0 failed, pytest rc 0, 23m26s (12:59:59–13:23:41 IST). `git status` differed after only by this review's receipt and the SA-026 note, written during the run. No `data/` file was written. |
| `python scripts/ci/check_broad_except.py` | OK (148 grandfathered) |
| `python scripts/docs/check_kt_docs.py` | `errors: []`; PDF 71 pages, source `c80021fb…` = the KT's SHA-256; header `f368f20` |

**Not exercised:** a real LLM; real Yahoo, mfapi.in or NSE; `filelock` on Linux or the Railway
volume; Saturday 14 Nov's counts; a re-run of the implementer's mutants (18 of 18, story file
alone). The full-suite figures above are this review's run on the reviewed bytes.

**Documentation:** the KT (sections 3, 4, 8, 11), CODEBASE, AUTOPILOT_GUIDE, PRODUCT_MAP and guide
06-O describe the reviewed behaviour; the PDF matches its source. The one stale living doc is R1.

## Acceptance checklist

| Card item | Verdict |
| --- | --- |
| Saturday 14 Nov read first | Not yet possible: the `FIX-030-M1` check, before the deploy |
| M2, ETF flows: "no sector ETFs", never automobile's | Met (RV7, RV8, story M2 tests) |
| M2, peers (SA-044) | Met by SA-044 (accepted 12 Nov) |
| M2, native graphs keep their own | Met (RV7, story) |
| M1, only if Saturday shows it | Conditional, open: the `FIX-030-M1` check |
| L1, decided only by an analysis, the ticker map or a managed record; table keys named by the next analysis; first-group decision and budget recorded | Met (RV1, RV2, RV3; D4 records 7 analyses once) |
| L2, bounded and the choice recorded | Met (RV1; D5: dropped with the reason after 2) |
| Tests: RV1/RV2 inverted; a generic bundle with no automobile name; one hand-worked case per decision | Met (story file; the story's RV1/RV2 inversions; D1–D5 cases) |
| SA-044 R1: a failure is never stored | Met for every hidden-error shape with a cap (story, RV4); the no-cap residual is accepted (I1) |
| SA-044 R2: both fills kept | Met (RV6; story's two-process test) |

## Commit-time edits (for the owner's commit, not made in this review)

The KT and the guide are in the reviewed manifest, so these wait for the commit:

1. **KT header:** the declared revision becomes FIX-030's code commit, and the edition its date.
   `check_kt_docs` needs this once FIX-030's linked sources are committed.
2. **KT section 12:** the FIX-030 row changes from `Open` to `Done`.
3. **Guide 06-O status:** "**PI target: FIX-030: implemented 2026-11-13, review pending.**"
   becomes "**FIX-030: accepted 2026-11-13 (fresh review); production verification pending
   (deploy after Saturday 14 Nov's run and the FIX-030-M1 check).**"
4. **`docs/AGENTIC_DESIGN.md` (R1):**
   - The `flows_sentiment` row's source reads "NSE bulk deals and FII/DII flows; AMFI sector-ETF
     momentum for the four native sectors (any other sector reads none: 'no sector ETFs')".
   - The `peers_valuation` row's note reads "One rule for every graph
     (`services/data/context/peers.py`): the stock's Yahoo industry, nearest market cap first, at
     most 5, none with fewer than 3 ('peers unavailable')".
5. **PDF:** regenerated after edits 1 and 2; `check_kt_docs` gives `errors: []`.

At the deploy, record it (uncommitted, for the next docs commit): KT section 1 "Production runs …"
and guide 06-O "deployed …".

**Commit only at the owner's word.**

- First, the 23 manifest files byte-exact (`kt_manifest.py verify … --rev <commit>`: 0
  mismatches).
- Then a docs commit with:
  - both receipts and the manifest;
  - the SA-026 routed note;
  - STATE and HANDOFF, with the uncommitted `5ae2749` push record they already carry;
  - edits 1–5.
- Run the full suite before any push. Push in a job-free window after Saturday's run and the M1
  check. Deploying changes production with the switch off (the implementation receipt's Rollout
  section).

## Decision and follow-up state

- **FIX-030: accepted** (reviewed revision: the working tree over `5ae2749`, manifest `0fdb3de2`,
  diff `f2199616`). STATE: `done` with a `review` entry; production `pending_deployment`.
- **Pending check `FIX-030-M1`:** Saturday's counts, before the deploy.
- **R2** is routed to SA-026.
- `active_task` null; `next_task` **FIX-031** (its dependency FIX-027 is done). Its implementation
  runs in a new conversation. If that conversation starts after Saturday 14 Nov at about 14:00 IST,
  it runs the `FIX-030-M1` check first. The switch stays off.

## Committed (13 Nov, at the owner's word)

The owner said "ya commit" in the same conversation (about 17:00 IST). Nothing was pushed.

- **`cddc3be`, the code:** exactly the 23 reviewed files. `kt_manifest.py verify FIX-030-manifest.json --rev cddc3be`
  gives 0 mismatches. `origin/main` was still `5ae2749`, and no other session was running.
- **The docs commit after it:**
  - this receipt, the implementation receipt and the manifest;
  - the SA-026 routed note;
  - STATE and HANDOFF, with the `5ae2749` push record;
  - commit-time edits 1–5 above.
- **One edit beyond the list: KT section 1.** Once the header names the inspected code as
  `cddc3be`, "Production runs the inspected code, `f368f20`" would be false. It now reads
  "Production runs `f368f20`", and adds that FIX-030 is committed and not yet deployed.
- **PDF:** 71 pages, source `2ed30fa9…` = the KT. `check_kt_docs` gives `errors: []`, with the
  header at `cddc3be` and edition 2026-11-13.
- **Where the files differ from the manifest:** at the docs commit, the manifest's KT, guide
  and PDF differ from it by these edits only.
- **Not pushed.** `main` is 2 ahead of `origin`, and the push deploys FIX-030. It waits for
  the `FIX-030-M1` check, a full-suite run and the owner's word, in a job-free window.

## M1 checked (15 Nov): does not occur

Owner's read, Sun 15 Nov about 06:40 IST (railway ssh, analysis_data/fix030/prod_probe.py, counts only; production f368f20, after Saturday 14 Nov's 12:30 run): 20 active ideas; 12 with a decided configured key (13 Nov: 4); readings: 10 from an analysis, 2 managed, 8 none; 2 named generic by an analysis; 5 keyed by the old Yahoo table (13 Nov: 7), all last dived 7 Nov, the first re-dive group after the deploy; 1 unnamed (13 Nov: 8), with no reading, not an analysis that gave no answer. M1 does NOT occur: Saturday's analyses answered the sector question. Peer cache 229 profiles, R1 sign 0. Not read: the Discovery log line's 'disputed' count (M2's size on the code before FIX-030); FIX-030 removes that cause either way.

FIX-030 was then deployed with PR-014's push (`1913017`, 07:16 IST Sunday 15 Nov). Railway deploy 080913e7 (commit 1913017) was created at 07:16:59 IST and reached SUCCESS by 07:19:23; the previous deployment 09698fde is REMOVED; the public /health answered 200 at 07:19:24. The build reinstalled every package (requirements.txt changed). Against the last build that installed packages (7a0719d2, 7 Nov): 76 the same, 12 minor or patch bumps (fastapi 0.162.0 to 0.163.0, langgraph 1.2.20 to 1.2.22, langchain-core 1.7.6 to 1.8.0, filelock 4.2.9 to 4.2.10 among them), none added, and 82 removed: CLEAN-001's RAG stack (torch, chromadb, sentence-transformers, transformers, the CUDA wheels) and the test tools. No module under core/, services/ or src/ imports a removed package; passwords use the standard library's hashlib.scrypt.
