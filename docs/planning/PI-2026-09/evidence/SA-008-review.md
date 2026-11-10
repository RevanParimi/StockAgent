# SA-008 review receipt — quarantine unresolved securities with lifecycle records

## Fresh-session review: ACCEPTED (2026-09-30), with change 1 to follow

- **What was reviewed:** SA-008 as the [implementation receipt](SA-008-implementation.md)
  describes it: the instrument registry, the identity gate, the review's `identity` stage, the
  advisor's identity hold and the operator reconciliation tool. That includes the owner's
  TATAMOTORS decision, option (b), with TMPV tracked as its own listing.
- **Context:** a fresh-session review in a new conversation, 2026-09-30 about 06:16–06:50 IST. It
  is not the conversation that implemented SA-008. It read the story card, the receipt, the full
  diff, the consumers the diff touches and the Docker build context. It did not read the
  implementing chat.
- **SA-039:** no check was due. P3 is Thu 1 Oct 09:30.
- **Peers:** 24 other sessions. All were idle at the start and before the bookkeeping.
- **Nothing** was committed, pushed, deployed, configured or sent. No production state was read.
- **Verdict: accepted.** The quarantine, the price-basis rules and the owner's decision work as
  the receipt says. One medium finding (M1) and one low one (L1) are in the new reconciliation
  tool's `apply`. Both need a registry record with `successors`, and the shipped registry has
  none, so `apply` cannot act on them today. They go to **SA-008 change 1**, which must be
  accepted before any `successors` record or production `apply`. There are two other low
  findings (L2, L3) and one informational note (I1). There is no critical or high finding.

### Review input verified

- **Manifest:** [SA-008-manifest.json](SA-008-manifest.json). The SHA-256 of its LF bytes is
  `9a2edfb2b44b168682475c50b61fbfb91463b878f31d6d65ec2448e83a7f80fc`, as the receipt states.
  `kt_manifest.py verify` gave 37 files and 0 mismatches at the start, and again after the test
  runs.
- **Diff:** rebuilt with the reviewer's own script. It also hashes every manifest path with
  `git hash-object`, and all 37 blob ids match. It gave 36 text files, 193,456 bytes and SHA-256
  `bb7d0576b28d7b96e81379791dd7900b072e63da2212fe4b297c920efa1f0c39`, the receipt's digest.
- **Completeness:** `git status` outside `docs/planning/` lists exactly the 37 manifest paths.
  The baseline `e3bb6a3` is HEAD.

## Contract checked

**Resolution.** `resolve_identity` goes through a full provider symbol, then the registry, then
the learned cache, then `{TICKER}.NS`. Evidence resolves an identity, and nothing is needed to
quarantine one. A missing or broken registry fails closed. An invalid entry quarantines only its
own ticker. A learned mapping to another code is still fetched, but it is `unresolved`.

**Every consumer that acts or learns** goes through SA-003's one switch, `decision_gate.mode`:

| Consumer | What the review confirmed |
|---|---|
| Analysis gate | `apply_identity` runs inside the gate's `try`. An exception still abstains. It compares the technicals' `section_provenance.symbol` with the identity's symbol. That symbol comes from `FetchResult.provenance()` through the bundle builder's `_safe`. |
| Forecast | Rows and the envelope copy `report.decision_gate.identity`, on the month-start run and on re-forecasts. |
| Review | The `identity` stage runs after `forecast_row` and before the close fetch. In `enforce` it returns before any write. `month_end_validation` runs later in the same review, so it is gated too. SA-003's list of consumers covers every other learning writer. |
| Close fetch | The primary symbol, the BSE fallback and the legacy fetch all ask for the resolved instrument. `pricing.session_close` uses the same fetch, so the advice `instrument` stamp names the symbol that priced its close. |
| Advisor and autopilot | `gated_decide` holds outright with `IDENTITY`. An unresolved SWITCH destination is blocked. The autopilot's buy leg re-checks the destination. |
| Deploy | `Dockerfile` copies `config/` to `/app/config/` with `WORKDIR /app`, and no volume masks it. Production reads the shipped registry, not the fail-closed path. |

**The owner's decision (b).** With the shipped registry, TATAMOTORS is `unresolved` on `TMPV.NS`,
basis TMPV. TMPV resolves as its own listing: `TMPV.NS`, basis TMPV, source `default`. The
automobile `TICKERS` default feeds only `_resolve_ticker`'s short cut and the preopen check's
default list. The preopen check skips a ticker with no envelope. The scheduler reads
`managed_tickers.json`. So deploying starts no TMPV analysis. The owner's add at rollout does.

## Independent adversarial examples

Reviewer probes, written by hand outside the repository
(`test_review_probes_sa008.py` in the session scratchpad). They ran with the repository's
hermetic conftest and a registry fixture of their own:

| # | Example (numbers written by hand) | Expected | Observed |
|---|---|---|---|
| R1 | One user holds 100 PARENT @ ₹1,000 and 50 OTHER @ ₹200. Both are demerged. One plan, one apply | A backup that restores {PARENT, OTHER} | **Fails (L1).** Both audit lines name `portfolio.json.pre-identity-20260930T005816`, which holds {OTHER, PARENTA, PARENTB}. The pre-apply file is in no backup |
| R2 | 100 PARENT. The plan is approved, and 50 are sold between apply's fresh plan and its lock | 50 PARENTA + 50 PARENTB, or a refusal | **Fails (M1).** 100 PARENTA + 100 PARENTB: ₹1,00,000 of cost booked on a holding worth ₹50,000 of cost |
| R3 | A continuing parent keeps its code. CONT 100 @ ₹400 demerges on 6 Jan 2025 into CONT (ratio 1, cost 0.9) and CONTH (0.1, 0.1) | CONT 100 @ ₹360 (₹36,000) + CONTH 10 @ ₹400 (₹4,000). Judged on the new basis after the apply. A second apply is refused | Passed |
| R4 | The registry file is missing | Every ticker `unresolved`, `heal_symbol` returns None, `^NSEI` passes through | Passed |
| R4b | One entry is invalid (an active symbol with no `via`) | Only that ticker is quarantined | Passed |
| R5 | A rename, demerger or relisting with no evidence | `unresolved`, and the reason names the evidence | Passed (3 cases) |
| R6 | The shipped registry | TATAMOTORS `unresolved` TMPV.NS/TMPV. TMPV resolved TMPV.NS/TMPV. TVSMOTORS → TVSMOTOR(.NS), CANARABANK → CANBK(.NS), `nse_symbol` TATAMOTORS → TMPV, MARUTI → MARUTI. No entry errors | Passed |

R2 simulates the interleaving in-process: a wrapper around `plan` sells after apply's fresh plan
returns. The window is real, but no concurrent process was run.

**Would the tests fail for the original defect?** The review ran its own mutations, separate
from the implementer's 22. Each puts back one pre-SA-008 behaviour at run time, and all four were
caught by the 70 SA-008 tests (unmutated: 70 passed):

| Mutation | Failing |
|---|---|
| The analysis gate ignores identity | 10 |
| The review grades every identity and basis | 10 |
| The advisor is never given the holding's identity | 2 |
| Unresolved registry segments resolve (the audit's F08: TATAMOTORS actionable) | 34 |

**Mocked boundaries.** The providers and the LLM are stubbed through the SA-002/SA-003 fixtures.
The chain tests assert that SA-003's `no_network` recorder saw nothing. The expected symbols,
bases, verdicts, quantities and amounts are written by hand. In the probes, atlas logged a
non-fatal foreign-key warning for the successor tickers. That is the store's documented
contract: atlas is a derived index, rebuilt nightly.

## Findings

| ID | Severity | Location | Finding | Disposition |
|---|---|---|---|---|
| M1 | Medium (confirmed, R2) | `core/portfolio/identity_reconcile.py:185-208` | `apply` compares digests on a fresh plan made **before** each user's lock. Under the lock it finds the holding by symbol but never compares its figures with the plan item's. A sale, add or corporate-action sync of that holding in the window still gets successors sized from the plan. Shares and cost are then not conserved. The backup, taken under the lock, and the audit line still allow recovery. | **SA-008 change 1:** under the lock, compare the holding with the item (`adj_qty`, `adj_avg_price`, `dividends_received`, `buy_date`, applied actions), and refuse on any difference. Add R2 as a test. |
| L1 | Low (confirmed, R1) | `identity_reconcile.py:190, 205-206` | One timestamp per `apply` names every backup. When one user has two items, the second copy overwrites the first with the half-applied portfolio. Both audit lines name that file. The KT's "copies `portfolio.json` aside" does not hold for that user. Recovery is by hand, from the audit log's `before` records. | **SA-008 change 1:** back up each user's file once, before that user's first change, and name it in every audit line. Add R1 as a test. |
| L2 | Low (code inspection; production size unmeasured) | `core/intelligence/rl/workflows/daily_review.py:189` | `_fetch_session_close` used to ask `YF_SYMBOL_OVERRIDES` or `{TICKER}.NS`. It now asks `resolve_identity`, which also reads the learned cache. So a ticker with a learned entry, such as the receipt's own SUZLON → SUZLON.BO, has its review and advisor close priced from the cached symbol. That is the symbol its forecasts were already priced from, so the change is a correction. But the receipt's D6 and "the primary Yahoo symbol of every ticker is unchanged" miss it, and it changes record-mode grading on deploy for such tickers. The local cache is empty. Production's has not been read. | **Behaviour upheld** (one instrument per run). **Rollout step 2 gains a read-only check** of the volume's `data/yf_symbol_cache.json` against the managed tickers. |
| L3 | Low (pre-existing, not introduced) | `services/data/fetchers/fundamentals.py:29` | The fundamentals fetcher's own `_nse_ticker` never used the overrides dict, and it does not use the registry. TVSMOTORS, CANARABANK, HEXAWARE and TATAMOTORS fundamentals are asked of `{TICKER}.NS`. The identity gate compares only the technicals' symbol. | **Routed to [SA-045](../stories/SA-045.md)** (deterministic factors). Its inputs include this fetcher, and a factor must be computed from the instrument the gate resolved. |
| I1 | Info | Receipt, "The contract" | "Prices on different bases are never compared" holds for grading and for holdings. The analysis's technicals still read the current symbol's whole history. After a future recorded demerger where the parent keeps its code (R3's CONT), that history spans both bases with no gate. No such record exists. | Change 1's docs state it as a limitation. Whoever records such an event reviews it then. |

The KT's section 6 now states M1 and L1, with the rule: until change 1 is accepted, record no
`successors` and run no `apply` in production.

## Decisions D1–D9

- **D1** upheld. The P3 decision must count identity rows apart from the other abstentions; HANDOFF
  already says so.
- **D2** upheld, with the owner's decision (b) checked as above (R6, the `TICKERS` consumers).
- **D3** upheld as a product decision. It applies in `enforce` only; `record` keeps EXIT and
  records what `enforce` would hold.
- **D4 and D5** upheld.
- **D6** upheld, with L2 as a fourth selection change.
- **D7 and D8** upheld.
- **D9** upheld. M1 and L1 are defects in `apply` itself, not in the one-event, no-merge policy.

## Commands, environment and results

Windows 11, Python 3.13.11 (`.stockai` venv), hermetic suite (`tests/hermetic.py`).

```text
reviewer's verify_input.py (own script)       -> manifest 9a2edfb2…, 37/37 blobs, diff bb7d0576… (193,456 B)
kt_manifest.py verify SA-008-manifest.json    -> 37 files, 0 mismatches (start, and after the test runs)
pytest -q -p no:cacheprovider <4 SA-008 files + 17 affected files: SA-002/SA-003 gate and health
  suites, session close, resolver, cache guard, close verifier, portfolio and autopilot
  pipelines, switch executor, reconciler, advisor, corp actions, discovery deep dive>
                                              -> 500 passed (41 s)
pytest -q -rfEs -p no:cacheprovider tests     -> 3981 passed, 12 skipped, 0 failed (5 min 14 s);
                                                 data/, logs/, outputs/ unchanged
reviewer mutations (4, run-time patches)      -> 4 of 4 caught (10 / 10 / 2 / 34 failing); unmutated 70 passed
reviewer probes (9 cases)                     -> 7 passed; R1 and R2 fail as findings L1 and M1
                                                 (R6 first failed on its own path: the hermetic
                                                 conftest moves the working directory)
check_kt_docs.py (before the review edits)    -> errors [] (13 documents, 394 links; PDF 30 pages,
                                                 source 1441382c…, matching the receipt)
```

**Not exercised:** Linux and Python 3.11 (CI runs after a push); any production data (the
volume's learned cache, holdings, gate logs); the browser (no frontend file changed); a real
second process during `apply` (R2 interleaves in-process).

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| An unresolved symbol cannot generate new-risk advice or contaminate learning | **Met in `enforce`** (D1). `record` ships and changes no verdict |
| Historical forecast/advice retains original identity and price basis | **Met.** Rows, envelopes and advice are stamped. A row is graded only on its own basis |
| Existing positions and corporate-action adjustments have an explicit operator-reviewed reconciliation path | **Met, with change 1** (M1, L1) required before its first use. `plan` is read-only and conserves cost (R3). `apply` needs the digest and refuses a second run |
| Fixtures: rename, demerger with multiple successors, suspension, provider outage and resumption | **Met** (the implementer's tests, and R3–R5) |
| Cached data for another instrument cannot satisfy the identity gate | **Met** for price history, closes and the NSE cross-check. Fundamentals are not covered (L3, pre-existing) |
| Documentation | **Met.** KT sections 1, 3–6, 8, 11 and 12, ARCHITECTURE, guide cases 02-D and 07-H, CODEBASE. The PDF matched its source before the review edits and was rebuilt after them |

## Review edits (documentation only)

Status wording in the KT (section 1, the section 4 heading, section 11's data-health row and
section 12), ARCHITECTURE (2 places), TEAM_TESTING_GUIDE (02-D and 07-H) and CODEBASE. The
wording now says accepted on 2026-09-30, not committed. M1 and L1 are stated in KT section 6. The
PDF was rebuilt. `kt_manifest.py verify SA-008-manifest.json` now mismatches exactly those 5
files: the KT, the PDF, ARCHITECTURE, TEAM_TESTING_GUIDE and CODEBASE. No code or test file was
changed.

## Production verification and follow-up state

- **`production_verification`: `pending_deployment`.** SA-008 is not committed. Commit and push
  need the owner's word, in a job-free window (00:10–06:20 IST is safest). The commit that lands
  it should also bump the KT header and link the new files, as the receipt says.
- **Rollout** stays as the receipt's "Rollout" section, plus:
  - **step 2 (L2):** read the volume's `data/yf_symbol_cache.json`, read-only, and list managed
    tickers with a learned entry. Their review close now comes from that symbol;
  - **no `successors` record and no production `apply`** until change 1 is accepted.
- **SA-008 change 1** (M1, L1, and the I1 limitation in the docs) is recorded in STATE. It is
  implemented in its own conversation and needs its own fresh review. It is not urgent under the
  shipped registry, and it must come before any `successors` record.
- **SA-045** gets L3 as a routed note.
- **The SA-003 enforce decision at P3 (Thu 1 Oct):** SA-008 is accepted but not deployed. If it is
  still undeployed then, its interplay does not apply: "If it is not deployed, nothing changes".
- **Next ready story** by STATE order: **SA-009**. Start it in a new conversation, after any due
  production check. P3 is Thu 1 Oct 09:30.
