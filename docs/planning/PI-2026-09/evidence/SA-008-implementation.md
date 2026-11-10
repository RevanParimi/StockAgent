# SA-008 implementation receipt — quarantine unresolved securities with lifecycle records

- **Story:** [SA-008](../stories/SA-008.md). Audit finding F08 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md).
- **Phase:** implementation, one conversation, 2026-09-29 about 16:38–17:50 IST, amended
  2026-09-30 about 00:05–00:30 IST for the owner's TATAMOTORS decision (D2), before any review. It includes a
  same-conversation self-review, which is **not** the fresh-session review. STATE:
  `review_required`.
- **Baseline:** `e3bb6a30f519a88d6fa2fe4da0207efb98e924a0` (the pushed SA-007 change 1 KT bump,
  deploy `f2e23722`). The tree was clean apart from the uncommitted post-push STATE/HANDOFF record.
- **SA-039 check:** P2 was due at 17:00 and was run first, read-only, in this conversation. It
  passed; see the [activation record](SA-039-activation-2026-09-26.md). Its one handled traceback
  is routed to [SA-026](../stories/SA-026.md).
- **Review input:** [SA-008-manifest.json](SA-008-manifest.json). Its digest and the diff digest
  are under "Manifest and digests".

## What it does, in one example

TATAMOTORS is a production-managed ticker (weights v85, the most adapted of the 20). Before this
story, `settings.YF_SYMBOL_OVERRIDES` mapped it to `TMPV.NS` by hand, with no date and no
evidence. TMPV is the passenger-vehicle company after the 2025 demerger. The name "Tata Motors
Limited", which the news searches use, now belongs to the commercial-vehicle company. With TMPV's
data healthy, SA-003's gate said `actionable`: it checks that evidence arrived and is fresh, not
that it belongs to the company the ticker names.

| Step | Before | `record` (the checked-in mode) | `enforce` |
|---|---|---|---|
| Report | STRONG BUY, `actionable` | STRONG BUY. The gate says `abstain`, with the reason "identity unresolved: retired by the owner's decision …", and `decision_gate.identity` names symbol TMPV.NS, basis TMPV, status `unresolved`. One row in `decision_gate.jsonl` | **INSUFFICIENT DATA**; STRONG BUY kept as `withheld_verdict` |
| Month-start forecast | an envelope | the same envelope; the envelope and every row carry `instrument` | **no envelope** |
| Daily review | grades and learns | grades and learns; the summary lists stage `identity` | `data_gated` at stage `identity`, before any learning write |
| Advisor, small holding | ADD | ADD. `data_gate` names the identity and says the gated verdict is HOLD; the advice keeps `instrument` | **HOLD**, note `IDENTITY` |
| Autopilot | BUY 2 shares | BUY 2 shares | **no buy** |

Fetching is unchanged: TATAMOTORS is still priced from TMPV.NS. The same chain with a registry
that does not list TATAMOTORS stays `actionable` and buys. All five rows are tests through the
real orchestrator, bundle builder, aggregator, forecast, review, pipeline and executor, with the
shipped registry (`test_identity_chain_sa008.py`, `test_identity_review_sa008.py`).

## The contract

**The instrument registry** (`config/instruments.yaml`, new; parsed by
`src/backend/shared/data/instruments.py`, new) replaces the `YF_SYMBOL_OVERRIDES` dict, which is
deleted. For each listed ticker it holds effective-dated segments (`from` inclusive, `until`
exclusive, in order, not overlapping). Each names:

- `symbol`: the provider (Yahoo) symbol to ask in that period;
- `basis`: the price-basis id (default: the symbol's root). Prices on different bases are never
  compared. A rename keeps the basis; a demerger or relisting starts a new one;
- `status`: `active` resolves, while `unresolved`, `suspended` and `delisted` quarantine;
- for an `active` symbol that is not the ticker's own listing, `via`: `alias` (with a reason),
  or `rename`/`demerger`/`relisting` (with `evidence`: source, ref and date for each item);
- optional `successors` (ticker, ratio, cost_fraction; the fractions sum to 1, with evidence and
  a `from` date) for the operator's reconciliation.

**Evidence is required to resolve an identity, never to quarantine one.** An invalid record
quarantines only its ticker. A date no segment covers is unresolved. An unreadable, malformed or
missing registry makes every ticker unresolved (fail closed), and it is logged once.

**Resolution** (`symbol_resolver.resolve_identity(ticker, on)`), cheap and without network:

1. a full provider symbol (`X.NS`, `^NSEI`) passes through as itself;
2. the registry owns every ticker it lists;
3. the learned cache (`data/yf_symbol_cache.json`). A same-root mapping (SUZLON → SUZLON.BO) is
   resolved. A mapping to another code (a fuzzy self-heal nobody reviewed) is still fetched, as
   before, but is `unresolved`;
4. otherwise the naive `{TICKER}.NS`, resolved.

Around it:

- `resolve_yf_symbol` is the identity's symbol.
- `identity_break(ticker, since, until)` says whether two dates' prices are on different bases.
- `nse_symbol` gives the close verifier the registry's NSE code (TVSMOTORS → TVSMOTOR). Anything
  else keeps the bare ticker, the verifier's independent check.
- `heal_symbol` never heals a registered ticker, a full provider symbol, or anything while the
  registry is unusable.

**Every consumer that acts or learns** (all through SA-003's one switch, `decision_gate.mode`):

| Consumer | Checks | In `enforce`, when not resolved | Recorded where |
|---|---|---|---|
| Analysis gate (`_apply_decision_gate`: `/analyse`, chat, CLI, forecast, re-forecast, review re-run, discovery) | identity today resolved; technicals' `section_provenance.symbol` equals the identity's symbol | `abstain`, identity reasons first; verdict INSUFFICIENT DATA | `decision_gate.identity`; gate log `analysis` |
| Forecast rows and envelope | (inherit the report's gate) | no envelope (SA-003) | `DailyForecast.instrument`, `PredictionEnvelope.instrument` |
| Daily review (new stage `identity`, after `forecast_row`) | identity on the session resolved; the row's stamped basis equals the session's, or for an unstamped row no basis change between the envelope's issue date and the session | `data_gated` before any write | summary `data_gate`; gate log stage `identity` |
| Close fetch (`_fetch_session_close`) | asks the identity's symbol for that session, and the BSE fallback and legacy fetch ask for the same instrument | (selection only) | — |
| Advisor (`gated_decide`, `decide(identity_hold=)`) | holding identity resolved and basis unchanged since the buy date (or the latest reconciliation); SWITCH destination identity resolved | **HOLD** outright, note `IDENTITY` (EXIT and TRIM included); unresolved destination falls to the next or plain EXIT | `AdviceRecord.data_gate` (`identity`); every advice keeps `instrument` |
| Autopilot SWITCH buy leg | destination identity resolved | buy skipped (the sell executes) | log line |

**The reconciliation path** (`core/portfolio/identity_reconcile.py`, new; operator CLI only,
nothing scheduled):

- `plan [--on] [--out]` is read-only. It lists every holding the advisor would hold, with the
  registry's proposal: successor holdings (quantity × ratio, cost × fraction) when a single
  recorded event with `successors` lies after the basis date. Otherwise it says what must be
  recorded, or that the user already holds a successor and it is merged by hand. It ends with a
  SHA-256 digest over the day and the items, including the holding figures;
- `apply --plan --approve <digest>` refuses unless the approval is the plan's digest **and** a
  fresh plan for the same day has the same digest. It copies `portfolio.json` aside. Under the
  user's lock it replaces the old holding with its successors, each carrying an applied action
  (kind demerger/rename/relisting, `ex_date` = the new basis's first day), and logs
  `identity_reconciliations.jsonl`. A second apply is refused;
- the ledger reconciler treats a holding with an identity action as `unverifiable`, as after a
  split. It moved without a ledger row.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| An unresolved symbol cannot generate new-risk advice or contaminate learning | Met, in `enforce` (the SA-003 switch; see D1) | Chain: `test_enforce_an_unresolved_symbol_produces_no_new_risk` (report, no envelope, HOLD `IDENTITY`, no buy). Learning: `test_an_identity_gated_review_learns_nothing` (3 cases × 2 learning modes, byte-identical store, weights v41, no FeedbackAgent). Destinations: `test_an_unresolved_switch_destination_is_refused`, `test_the_autopilot_never_buys_an_unresolved_destination`. Record changes nothing: `test_record_mode_the_chain_still_buys_…`, `test_record_mode_learns_as_before_…` |
| Historical forecast/advice retains original identity and price basis | Met | Rows, envelope and advice carry `instrument`, and a later registry change does not rewrite them (`test_record_mode_the_chain_still_buys_and_every_artifact_names_the_identity`). A row is graded only on its own basis: `row_on_another_basis`, `demerger_since_issue` (gated), `rename_since_issue`, `row_on_the_sessions_basis` (graded) |
| Existing positions and corporate-action adjustments have an explicit operator-reviewed reconciliation path | Met (code; no production reconciliation was run or is needed yet) | `test_plan_is_read_only_and_conserves_cost`, `test_apply_needs_the_digest_and_refuses_a_stale_plan`, `test_apply_replaces_the_parent_with_its_successors` (backup bytes, audit line, second apply refused), `test_after_reconciliation_the_advisor_judges_the_new_basis`, `test_the_ledger_reconciler_treats_successors_as_unverifiable`, `test_the_cli_plan_then_apply` |

**The card's evidence list:**

- **Rename:** `test_rename_keeps_one_resolved_instrument`,
  `test_a_close_before_the_rename_is_asked_of_the_new_code`, and the review's
  `rename_since_issue` control.
- **Demerger with multiple successors:**
  - `test_demerger_with_two_successors_is_never_resolved_by_the_machine`: unresolved after the
    event; self-heal is never consulted even when Yahoo offers both successors, nothing is cached,
    and the symbol stays as recorded;
  - `test_a_recorded_demerger_resolves_but_starts_a_new_basis`;
  - the portfolio fixture: 100 @ ₹1,000 → PARENTA 60% / PARENTB 40%.
- **Suspension:** `test_suspension_and_resumption` (quarantined inside the window, resolved
  after, basis unbroken).
- **Provider outage and resumption:** `test_provider_outage_and_resumption_keep_the_same_instrument`,
  for a registered alias and an unlisted ticker. Every download is empty and Yahoo search offers
  another company; nothing is remapped or cached, and after the outage the same symbol answers.
- **Cached data for another instrument cannot satisfy the identity gate:**
  - `test_a_learned_mapping_to_another_code_is_unresolved`;
  - `test_price_history_for_another_symbol_abstains`;
  - end to end, `test_price_history_for_another_instrument_cannot_satisfy_the_gate`: identity
    resolved to TMPV.NS, bars fetched for TATAMOTORS.NS, and the result is abstain; its control
    is actionable;
  - `test_the_close_fallbacks_ask_for_the_resolved_instrument` (TMPV.BO, never TATAMOTORS.BO);
  - `test_an_nse_close_cached_under_another_code_is_not_served`.

**Independence of expectations.** Every expected status, symbol, basis, verdict, quantity and
amount is written by hand from the registry rules or the fixture. The fixture amounts are
₹1,00,000 → ₹60,000 + ₹40,000, and 600 vs 1,000 = −40%. The former overrides are a hand-written
dict. Nothing expected is computed by the code under test.

## Decisions for the reviewer

1. **D1 — quarantine acts through SA-003's `decision_gate.mode`, not a new flag, and ships
   `record`.** Deploying changes no outcome, as with SA-003. REVIEW.md allows one policy flag per
   observation window, and the card does not authorize enabling a policy. The cost is that
   enforcing SA-003 also quarantines TATAMOTORS and HEXAWARE. The alternatives were
   always-enforced quarantine (a production policy change on deploy) or a second flag (two
   policy decisions).
2. **D2 — TATAMOTORS and HEXAWARE ship `unresolved`, still fetched from the same code.** No
   primary exchange evidence (effective date, successors, ratio, cost split) is recorded for
   either. The registry states only what the repository said (the old override comments).
   TVSMOTORS and CANARABANK are plain aliases (the same listed security under its NSE code): a
   reason, not migration evidence.
   - **The owner's decision (29 Sep, delegated: "take whichever is recommended"): option (b).**
     The passenger-vehicle company is tracked as its own ticker, TMPV, and TATAMOTORS is
     retired, not resolved. Why (b):
     - under (a), keeping TATAMOTORS as TMPV needs exchange evidence the implementer cannot
       verify from here. It also keeps two problems: the name "Tata Motors Limited", which now
       means the commercial-vehicle company, drives its news searches while its prices are
       TMPV's; and its v85 weights were learned partly on the pre-demerger company;
     - under (c), a scheduled ticker stays dark in `enforce` and keeps costing LLM calls in
       `record`;
     - under (b), TMPV's ticker, name and prices are one company. It needs no registry record,
       and its learning starts clean. The one cost is TATAMOTORS' learned history, which is the
       contaminated part.

     TMCV is not added. That is a new holding decision, not a replacement.
   - **The amendment it needed (2026-09-30, before any review):**
     - TMPV joins the automobile `TICKERS` default. That list is also
       `_resolve_ticker`'s exact-match short cut, and without it the LLM ticker lookup, whose
       prompt lists "TATAMOTORS – Tata Motors Ltd", can rename TMPV back to TATAMOTORS. The code
       records the same kind of rename, TATAPOWER to TATAMOTORS;
     - `TICKER_SECTOR` maps TMPV to automobile. The drift guard requires this, and it also turns
       on the self-heal root check;
     - the registry's TATAMOTORS reason records the decision.

     Test: `test_the_owner_decision_tmpv_is_tracked_as_its_own_listing`. It includes the hazard
     as a control: with the old list, the LLM's "TATAMOTORS" answer is taken.
3. **D3 — the identity hold also holds EXIT and TRIM (enforce only).** This departs from SA-003's
   "risk reduction is never blocked". SA-003's rule is about missing data trapping a position.
   Here the data is present, but it is on another price basis: a demerged parent's close reads
   as a −40% loss that never happened, and a stop fired on it sells on a false signal. That is
   the same trap the corp-action invariant exists for (a bonus looking like a crash). A user can
   still sell by hand, and a suspended stock cannot be traded anyway. The alternative, letting
   EXIT through, reproduces the false stop-loss (`test_the_demerged_parent_reads_as_a_false_forty_percent_loss`).
4. **D4 — a learned mapping to another code stays fetched but is `unresolved`.** Record mode
   changes nothing, and enforce quarantines until someone records it. It affects chat analyses
   of names Yahoo self-healed to another code (ATHER → ATHERENERG-like), which read INSUFFICIENT
   DATA in enforce until registered.
5. **D5 — unstamped (pre-SA-008) rows are judged by registry continuity, not as "unknown".**
   SA-003 treated a missing gate as unverified. Identity continuity is checkable, though: the
   registry says whether the basis changed between the envelope's issue date and the session. So
   every live September row stays gradeable for unlisted tickers.
6. **D6 — selection changes in both modes, deliberately, and only in fallbacks and the NSE
   code:**
   - the BSE fallback asks for the resolved instrument's BSE code (`TMPV.BO`, not
     `TATAMOTORS.BO`);
   - the legacy fetch asks for the resolved symbol itself, which it never self-heals;
   - the NSE cross-check asks for the registry's NSE code for a registered alias or successor.
     For TATAMOTORS that is TMPV rather than TATAMOTORS, so both sources price the same security.

   The primary Yahoo symbol of every ticker is unchanged (a test pins the four former overrides).
7. **D7 — a rename keeps the basis, and every date of that basis asks the current code**, because
   the provider moves history to the new code. A future-dated segment applies only from its date.
8. **D8 — the suite reads an empty registry by default** (`tests/conftest.py`,
   `INSTRUMENT_REGISTRY_PATH` → `tests/fixtures/instruments_empty.yaml`). The SA-002/SA-003
   suites use TATAMOTORS as their *healthy* example. They keep testing data health, not the
   shipped identity decisions, and a registry edit cannot silently flip unrelated tests.
   SA-008's tests point at the shipped file or at their own fixture explicitly.
9. **D9 — reconciliation handles one event per plan, and never merges.** Two lifecycle events
   since the basis date, or a successor the user already holds, get "reconcile by hand". It
   writes no ledger row, so the successors are `unverifiable` for the ledger check, as a split's
   holding is.

## Tests: commands, environment, results

Environment: Windows 11, Python 3.13.11 (`.stockai` venv), pandas 3.0.2. The suite is hermetic
since SA-005 (`tests/hermetic.py`). The new tests also assert that SA-003's `no_network`
recorder saw no connection.

```text
.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider <files>

new SA-008 files (4)                                  -> 70 passed
  test_instrument_identity_sa008.py  35   test_identity_chain_sa008.py      7
  test_identity_review_sa008.py      12   test_identity_portfolio_sa008.py 16
directly affected existing files (12: the SA-002/SA-003 suites, session close,
  resolver, cache guard, portfolio/autopilot pipelines, data fetchers)  -> 347 passed
  (mid-implementation, before the advice stamp; the full suite below is on the final bytes)
runtime mutations (22, analysis_data/sa008/run_mutations.sh) -> 22 of 22 caught; unmutated 69 passed
  (before the D2 amendment, whose test carries its own control; the amendment touches no
  mutated function)
SA-008 files + short cut + sector-map drift + router + deep dive  -> 123 passed (after D2)
full suite: pytest -q -rfEs -p no:cacheprovider tests  -> 3981 passed, 12 skipped, 0 failed (10 min 24 s,
                    30 Sep 00:07-00:17 IST, final bytes): SA-007's 3911 plus exactly the 70 new
                    tests; data/, logs/, outputs/ unchanged. (Before the amendment: 3980 / 12 / 0.)
check_kt_docs.py -> errors [] (13 documents, 394 local links, 51 stories, 24 job IDs,
                    13 config claims; PDF 30 pages, source 1441382c…)
```

**Mutations.** `analysis_data/sa008/mutate8.py` recompiles one function from its own source with
one snippet replaced and swaps its code object during each test. No source file is edited, and a
snippet that is not found fails loudly. Each puts back one behaviour this story replaced:

| Mutation (the behaviour put back) | New tests failing |
|---|---|
| m1 every registered segment resolves | 17 |
| m2 a registered ticker is self-healed | 4 |
| m3 price history for another symbol passes the gate | 2 |
| m4 an unresolved identity does not abstain | 5 |
| m5 the review grades any identity and any basis | 10 |
| m6 the BSE fallback asks for `{TICKER}.BO` | 2 |
| m7 the advisor ignores the identity hold (false stop-loss EXIT) | 4 |
| m8 a reconciled successor is checked against the old symbol's ledger | 1 |
| m9 apply trusts a plan made before the holdings changed | 2 |
| m10 a demerger does not break the basis | 14 |
| m11 a pre-rename close asks the retired code | 2 |
| m12 NSE is asked the bare ticker for a registered alias | 1 |
| m13 the technicals section does not name its symbol | 2 |
| m14 forecast rows and envelopes are not stamped | 1 |
| m15 a migration resolves without evidence | 1 |
| m16 an unusable registry fails open | 4 |
| m17 the autopilot buys an unresolved destination | 1 |
| m18 an unresolved SWITCH destination is chosen | 1 |
| m19 a learned mapping to another company is resolved | 1 |
| m20 the pipeline never passes the holding's identity | 2 |
| m21 the analysis gate never sees identity | 7 |
| m22 advice records are not stamped | 2 |

**Existing tests changed** (the contract changed; no expectation changed):

- `test_symbol_resolver.py::test_curated_override_wins` reads the shipped registry explicitly.
  It still expects TATAMOTORS → TMPV.NS.
- `test_symbol_cache_guard.py` asserts that `_yf_info` reads the registry
  (`registry_identity`), and never the learned cache or the resolver, in place of the deleted
  dict.
- `tests/conftest.py` gains `_isolated_instrument_registry` (D8).

**Not exercised:** Linux and Python 3.11 (CI runs after a push); any production data; the
browser (no frontend file changed).

## Documentation

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - §1: status;
  - §3: a configuration row for `config/instruments.yaml`;
  - §4: "Instrument identity", with the TATAMOTORS example, and the current gap;
  - §5: rows carry `instrument`; the review's `identity` stage, with the demerger example;
  - §6: the identity hold, with the ₹1,000 → ₹600 example, advice `instrument`, and the
    reconciliation path;
  - §8: discovery;
  - §11, §12: status and the section mapping, now 3/4/5/6/8.
- **PDF** rebuilt (`check_kt_docs` errors `[]`). New files are named in code formatting, not
  linked. `check_kt_docs.py` fails on a link to a file absent at the header's `8663387`, so the
  commit that lands this story should link them and bump the header, as SA-003's did.
- `docs/ARCHITECTURE.md`: the identity paragraph and the current/planned table.
- `docs/TEAM_TESTING_GUIDE.md`: 02-D rewritten into prepared cases (TATAMOTORS in both modes, a
  recorded rename, a suspension); new 07-H (the demerged holding in both modes, then plan and
  apply).
- `CODEBASE.md`: the tree, an identity paragraph, and module rows for `instruments.py`,
  `identity_reconcile.py`, `advisor.py` and `decision_gate.py`.
- Bookkeeping, outside the manifest:
  - STATE, HANDOFF and this receipt;
  - the SA-039 activation record (P2);
  - a routed note on [SA-026](../stories/SA-026.md).

## Rollout (owner, after the fresh review, commit and push)

1. **Deploying changes no outcome.** Everything ships under `decision_gate.mode: record`. Push
   only in a job-free window (00:10–06:20 IST is safest).
2. **Verify read-only after the next scheduled cohort:**
   - TATAMOTORS' analysis rows in `decision_gate.jsonl` start with "identity unresolved";
   - its review rows name stage `identity`;
   - reports carry `decision_gate.identity`; new rows and advice carry `instrument`;
   - no other managed ticker gains an identity row. Of the 20, only TATAMOTORS is registered, so
     another row would mean a learned mapping to another code on the volume, which is worth
     looking at.
3. **Before SA-003 is enforced, if SA-008 is deployed by then:**
   - count identity rows separately. They abstain by design on healthy data, so the P3 decision's
     spot check ("an abstain row whose data was actually fine") must exclude them. They are
     recognisable by the reason prefix `identity` and the review stage `identity`;
   - run `python -m core.portfolio.identity_reconcile plan` read-only on the volume. Any user
     holding TATAMOTORS would be held with `IDENTITY` under enforce. A relabel to TMPV is an
     operator decision, not an evidenced corporate action, so the tool proposes none. Bring any
     such holding to review rather than editing it by hand.
4. **The owner's decision (29 Sep): option (b), track TMPV.** At rollout, after this story is
   reviewed, committed and deployed, the owner does the swap in the app's managed-ticker screen:
   - **Add TMPV**, sector automobile, with the name NSE lists for it (Tata Motors Passenger
     Vehicles Ltd). The name feeds its news searches. The add starts its first envelope in the
     background.
   - **Disable TATAMOTORS with the toggle. Do not remove it.** Removing runs
     `_cleanup_ticker_rl_data`, which deletes `data/predictions/automobile/TATAMOTORS`: its
     envelopes, v85 weights, feedback and dossier, the history this story keeps.
   - **Deploy first.** Before this code, TMPV is not in the exact-match list, and the LLM lookup
     can rename it to TATAMOTORS.
   - If production sets the `AUTO_TICKERS` variable, add TMPV there too, because it replaces the
     default list. Setting a variable redeploys.
   - **Read-only, after the next 16:30 review:**
     - a `=== TMPV |` review header, and no TATAMOTORS header;
     - TMPV's analysis carries no identity reason.

   Nothing here is urgent under `record`.
5. **Rollback:** revert the commit. The registry has no production state of its own.

## Open limitations

- **No real migration is recorded with primary evidence.** TATAMOTORS (retired by the owner's
  decision; TMPV is tracked instead) and HEXAWARE stay quarantined. The implementer did not
  fetch exchange circulars; the card allows quarantine when identity is unresolved.
- **Lifecycle events are not detected automatically.** The daily corp-action sync still parses
  only bonus, split and dividend. A new rename or demerger reaches the registry only when someone
  records it. Until then the old symbol goes quiet, and SA-003's data gate abstains on its empty
  or stale sections.
- **How often production would hit the identity gate is not measured.** It is expected to be
  TATAMOTORS only, and the rollout step 2 checks it.
- **LLM ticker resolution for managed tickers outside their sector's `TICKERS`** is routed to
  SA-026 (seen in P2).
- **The screens** show INSUFFICIENT DATA and the `IDENTITY` note, not the reasons (as SA-003;
  routed to SA-024).
- **Not exercised:** Linux / Python 3.11 (CI after push); any production data; the browser (no
  frontend file changed).

## Manifest and digests

- **Review input:** [SA-008-manifest.json](SA-008-manifest.json), 37 paths (35 before the D2
  amendment, which added the automobile settings and the sector map):
  - 24 code and config files (3 new: `config/instruments.yaml`,
    `src/backend/shared/data/instruments.py`, `core/portfolio/identity_reconcile.py`);
  - 8 test files (5 new: the four test files and `tests/fixtures/instruments_empty.yaml`);
  - 5 documentation files, including the PDF.

  The SHA-256 of its LF bytes is
  **`9a2edfb2b44b168682475c50b61fbfb91463b878f31d6d65ec2448e83a7f80fc`**, and
  `kt_manifest.py verify` gives 0 mismatches. The manifest lists exactly the files `git status`
  shows changed outside `docs/planning/`.
- **Excluded,** because they are written after the manifest or belong to another record:
  STATE.json, HANDOFF.md, this receipt, the SA-039 activation record (P2) and the SA-026 card.
- **Full diff** against `e3bb6a3`:
  **`bb7d0576b28d7b96e81379791dd7900b072e63da2212fe4b297c920efa1f0c39`**, 193,456 bytes over 36
  text files. The PDF is pinned by its blob, `92027bc9…`. (Before the amendment: input
  `8834efc3…`, diff `caea26da…`; superseded, never reviewed.)
- **To rebuild the diff:** take every manifest path except the PDF, sorted. For a path tracked at
  the baseline, run `git diff --no-color --no-ext-diff e3bb6a3 -- PATH`. For a new file, run
  `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`. Concatenate the bytes. The
  ignored `analysis_data/sa008/sa008_diff.py` does exactly this.
- **After the commit:** `verify --rev <commit>` compares against the commit instead.
