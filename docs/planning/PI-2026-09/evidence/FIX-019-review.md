# FIX-019 review receipt — why NSE lists no corporate action for 14 configured codes, and the stale ones mapped

## Fresh review: ACCEPTED (2026-10-30)

**Phase:** fresh-session review, a new conversation opened with "continue" (30 Oct, about
22:49–23:40 IST, session `stockagent-main-e0` [d1136d]). FIX-019 and its amendment 1 were
implemented in `stockagent-main-6e` [9d0264]. This conversation did not read that chat or any
earlier one. The peers `-5d`, `-f2`, `-4f`, `-8a`, `-49`, `-f0` and `-6e` were idle at the start
and before the bookkeeping (ListAgents).

**Verdict: ACCEPTED** for the reviewed revision below.

- Every acceptance criterion on the card holds, and so do FIX-018's two routed test gaps.
- The card's four hard-review questions are answered below. The answers rest on my own reads of
  NSE's public lists and on my own cases through the real close, gate, reconciler and feed code.
- No finding is critical, high or medium. One low finding (L1) is two KT sentences that overstate
  what NSE no longer answers. It is fixed by a commit-time edit, with a routed note on FIX-020's
  card. Three notes are informational (I1–I3).

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called and no message was sent. **Public NSE data was read**, read-only and with no
credentials:

- NSE's symbol-change list and equity list;
- the corporate-action lists of the card's 14 codes, under the code the app now asks for, and
  of BAYER, NIIT, BAYERCROP and NIITLTD;
- historical closes of LTM, LTIM, PVR, PVRINOX and ICICILIFE over three short windows.

Every test fakes NSE and Yahoo. Tracked files changed by this review: STATE, HANDOFF, this receipt
and the FIX-020 card (a routed-input note). The reviewer's scripts, raw answers and outputs are
in the ignored `analysis_data/fix019_review/`.

### In one example (RV2, the daily review's close for LTIM)

LTIM is LTIMindtree. NSE renamed its code LTM on 27 Feb 2026, and Yahoo moved the history to
LTM.NS. NSE's close API answers either code with the same rows. On 30 Oct it gave 26–29 Oct
under LTIM and under LTM, and 20 Feb 2026 under LTM, rows labelled with the code of the day.

- **With the record:** the review's close for 20 Feb or 29 Oct asks Yahoo for LTM.NS and NSE for
  LTM, and nothing else. With Yahoo at ₹5,000 and NSE at ₹5,010 (0.2% apart), the close is
  ₹5,000, `agree`.
- **Without it** (HEAD's registry): Yahoo is asked LTIM.NS and LTIM.BO and answers nothing, so
  the close is NSE's ₹5,010 alone (`nse`).
- **A row issued before the record** (stamped LTIM.NS, basis LTIM, `default`) is still graded on
  30 Oct (RV1): grading compares only the basis, and the record keeps it. A row stamped with LTM
  as its basis would not be graded. Keeping the basis is what keeps LTIM's history usable.

LTIM is the only one of the seven tickers in an enabled sector (`config/sector_toggles.json`),
so it is the one record a scheduled forecast, review and learning step will meet.

### Review input verified

- **Manifest:** [FIX-019-manifest.json](FIX-019-manifest.json), 8 files, review input
  `9f3de76f550b29f43be861c7acc916d561740529eb114b27ec0560d89ee83c83`.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches at the start and at the end.
- **Diff:** `7fd9ac2fb81694328145c92982bb138eea95cb52bdaaf3982a1d83888f55d5b7`, 36,860 bytes,
  7 paths, against HEAD `48db226`. It was rebuilt at the start and at the end by
  `analysis_data/fix019_review/rv_digest.py`, the implementer's recipe writing into the review
  folder. Both match the receipt.
- **No drift:** no reviewed path changed during the review.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| Each mapping is the same listed security, on exchange evidence | **Holds** | My own read of NSE's `symbolchange.csv` (1,078 rows) and `EQUITY_L.csv` (2,620 rows) on 30 Oct. Each of the six rename rows (the five, and GATI → ACLGATI) gives the record's old code, new code and effective date. Each new code's equity-list ISIN equals the ISIN on NSE's notice: PVRINOX INE191H01014, UNITDSPR INE854D01024, ETERNAL INE758T01015, LTM INE214T01019, ICICILIFE INE726G01019. I matched each circular number to the attachment of the company's own "Name and Symbol Change" filing (the implementer's saved rows), with the same date and ISIN. RV5 checks every rename in the shipped registry against NSE's list, not against the YAML. |
| One basis, no join | **Holds** | `registry_bases` over all time is the ticker alone (story test). RV1: a row issued before the record is graded, and a different basis is not. PVR and LTM keep one ISIN through their mergers (INOX into PVR, Mindtree into LTI), each the transferee. |
| Asked under the new code on every date | **Holds** | RV2 (the review's close, before and after the rename), RV3 (an analysis: price history from the new code, never self-healed, the gate stays actionable with the registry's stamp), RV7 (the event feed's NSE code), and the story's grading test through `results.corp_actions_fn`. NSE's close API answers a pre-rename day under the new code (probe), so asking it on every date is supported. |
| Delisted from the first day without a session | **Holds** | NSE's notices: "suspended w.e.f. November 12, 2025 (i.e., closing hours of trading on November 11, 2025)" and "w.e.f. February 17, 2023 (… February 16, 2023)". RV6: the named last day is a trading day and resolves; the next day is `delisted`. |
| The quarantine touches only codes nobody prices | **Holds** | No Yahoo bars under GATI.NS, ACLGATI.NS or INOXLEISUR.NS (the implementer's after-check). Logistics and media are disabled. RV4: a holding across PVR's rename needs nothing, and a held INOXLEISUR would be named from 17 Feb 2023. |
| KT section 6's count | **Holds** | `count_probe.py`, through the strict reader under `nse_symbol`: 9 lists empty, each twice (AAVAS, IDEAFORGE, STARHEALTH and ETERNAL with a price; ACCCEMENT, APL, DEEPAKNITRI, MAHINDHOTEL and MTAR without one). 5 lists read rows: PVRINOX, UNITDSPR, LTM and ACLGATI 20 each, ICICILIFE 13. |
| SA-008's widened shipped-registry test | **Not relaxed** | It now expects the five renames and the two delisted codes as the only other entries, and the four former entries stay pinned by their own tests. |

### The card's hard-review questions

- **Is each mapping the same listed security, never a name match?** Yes, for all six renames,
  by the row, notice and ISIN above. No configured code is mapped on a name. My read adds one
  fact the receipt and KT miss: BAYER and NIIT were NSE codes. NSE's lists hold Bayer India Ltd
  under BAYER (ISIN INE462A01014, dividends ex 15 May 2002 and 30 May 2003) and NIIT Ltd under
  NIIT (INE161A01012, ex 23 Jan 2003). Today's BAYERCROP and NIITLTD carry other ISINs
  (INE462A01022, INE161A01038). So the decision not to map them stands: a rename record would join
  two securities' prices (L1).
- **Could an entry join two price bases?** No. Each record has one basis over all time.
  - **PVR:** the transferee of INOX Leisure's merger, with the same ISIN on every row of its
    list since 2007.
  - **LTM:** LTI's listing (21 Jul 2016), the transferee of Mindtree, with one ISIN on every row
    of its list since 2017.
  - **GATI:** gets no successor, so nothing joins Allcargo Logistics' prices.
- **Does any changed Yahoo symbol alter a live holding's price?** No.
  - Production's holdings were last read on 29 Oct (REDINGTON, WELCORP; FIX-017's probe). They
    were not re-read after the 30 Oct deploy.
  - Even a held one of the five would only gain a price, never change one. Yahoo answers nothing
    under four of the old codes. ICICIPRULI.NS and ICICILIFE.NS gave the same closes on all 12
    common days. NSE's close answers both codes with the same rows.
- **Delisted codes: dated from the first day each did not trade, changing only codes nobody
  prices?** Yes (RV6 and the contract rows above).

### Rulings on the implementer's decisions

- **F19-D1, the record's shape:** upheld. Both the dated form and `_current_symbol` asking the new
  code for every date match NSE's own behaviour (probe).
- **F19-D2, ICICIPRULI mapped now:** upheld. The identity is certain, and NSE serves the history
  under ICICILIFE (its 5–9 Oct rows, labelled ICICIPRULI). Yahoo's short ICICILIFE.NS history only
  shortens history-based analysis, a sector that is disabled; KT section 4 states it.
- **F19-D3, no mapping on a name:** upheld, with L1's correction of the facts for BAYER and NIIT.
- **F19-D4, superseded by amendment 1:** recorded at the owner's word.
- **F19-D5, T1 and T2 as new tests:** upheld. Both expected values follow the card's example by
  hand.
- **F19-D6, `_Market` reused:** upheld. The lookups it returns are the real
  `results.stock_quote_fn` and `corp_actions_fn`, and only the NSE, Yahoo and NSE-client
  boundaries are faked.
- **F19-D7, the delisted shape:** upheld (RV6).

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | low (docs, confirmed) | `docs/TECHNICAL_DESIGN.md:569-570` and `:583-586` (section 4); FIX-020's card ("not NSE codes, and never were") | (a) "Without the record, the app asked for the old code, which Yahoo and NSE no longer answer." NSE's close API still answers LTIM and PVR, with LTM's and PVRINOX's rows (`nse_history_probe_after.py`, 26–29 Oct 2026). What stopped answering is Yahoo and NSE's corporate-action list, so before the record LTIM's review close rested on NSE alone (RV2 'before'). (b) "the configured codes NSE has never listed: … BAYER … NIIT". NSE's lists hold Bayer India Ltd under BAYER and NIIT Ltd under NIIT, with 2002–2003 rows (`bayer_niit_probe.py`). The next sentence (none is in NSE's equity list or its symbol-change history) is true. Behaviour is unaffected. | **Commit-time edit** of the two KT sentences (exact text below) and the PDF. A routed-input note on [FIX-020](../stories/FIX-020.md). |
| I1 | info | `config/instruments.yaml` (GATI, INOXLEISUR) | The `delisted` segments cite NSE's notice by its title ("Suspension of Trading (ACLGATI)"), not a circular number. The registry asks for evidence only to resolve an identity. The notice texts, dates and ISINs match NSE's announcement rows. | None. |
| I2 | info | `daily_review._fetch_session_close` | For a date before 14 Oct 2026, Yahoo's ICICILIFE.NS has no bar, so a review close for ICICIPRULI on such a date would rest on NSE alone, through the BSE and one-year fallbacks. That is NSE's close of the same security. Insurance is disabled, and no ICICIPRULI forecast store exists locally. | None. KT section 4 already states the short history. |
| I3 | info | (inference) | After the deploy, LTIM's next analysis is priced from LTM.NS with a full history, and its review closes come from two agreeing sources instead of NSE alone. Nothing in production was read to confirm what LTIM's store holds. | Watch with guide 02-M after the deploy. |

### Commands, environment and results

Windows 11, the project's `.stockai` virtual environment (Python 3.13.11), `tests/hermetic.py`
active for every test (no network, no `.env`, no checkout data). From the repository root:

- `.stockai/Scripts/python.exe analysis_data/fix019_review/rv_digest.py`: diff `7fd9ac2f…`,
  36,860 bytes, 7 paths, HEAD `48db226`; at the start and at the end.
- `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-019-manifest.json`:
  0 mismatches, `9f3de76f…`; at the start and at the end.
- `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_registry_fix019.py tests/unit/test_exit_fix018.py tests/unit/test_exit_fix016.py tests/unit/test_exit_evidence_pr009.py tests/unit/shared/test_instrument_identity_sa008.py`:
  **253 passed** (3m24s).
- `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider analysis_data/fix019_review/test_rv_fix019.py`:
  **14 passed** (RV1 ×5 rows issued before the record; RV2 ×2 the review's close before and
  after the rename; RV3 ×2 the analysis and its gate; RV4 holdings; RV5 the registry against NSE's
  own lists; RV6 ×2 the delisting days; RV7 the feed). With `RV_REGISTRY` pointed at HEAD's
  `config/instruments.yaml`, **all 14 fail**.
- `.stockai/Scripts/python.exe analysis_data/fix018_review/rv_mutants.py late_list_inclusive lasting_reason_any_kind`:
  FIX-018's two survivors against the three FIX-018 story files: **2 of 2 caught** (T1 and T2).
- The implementer's 19 registry mutants were not re-run. Their list was read against the records,
  and RV5 and RV6 cover the dates and codes independently.
- `.stockai/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`: **5,890 passed, 12
  skipped, 1 xfailed, 0 failed** (24m55s, 23:06–23:31 IST). `git status` afterwards listed only
  this review's receipt and the reviewed input: no runtime data changed.
- `scripts/ci/check_broad_except.py`: OK (151 grandfathered). `scripts/docs/check_kt_docs.py`:
  errors `[]`, PDF 61 pages, source digest `e2ec3ca6…` = the reviewed KT.
- Public reads (read-only): `nse_lists_probe.py` (NSE archives, 30 Oct 22:53 IST);
  `bayer_niit_probe.py`; `count_probe.py`; `isin_probe.py` (one ISIN on every row of
  PVRINOX's list, 2007–2026, and LTM's, 2017–2026); `nse_history_probe.py` and
  `nse_history_probe_after.py`. Raw answers are in `analysis_data/fix019_review/raw/`.

**Not exercised:** production. LTIM's prediction store, the learned symbol cache and the holdings
since the 30 Oct deploy were not read. There was no browser and no model call.

### Acceptance checklist

- A table in the receipt for each code, with NSE's answer under it and under the candidate, the
  evidence and the action → **met** (14 rows and the three found on the way; my reads agree, with
  L1's BAYER/NIIT correction).
- A hermetic test for each new entry: `nse_symbol` resolves to the code whose list the fixture
  answers, and grading reads that list → **met** (five renames through the real grading lookups;
  GATI and INOXLEISUR by their own tests).
- SA-008's tests pass → **met** (35, with the widened contract named).
- The KT limit's count of empty lists → **met** (9, 4 with a price; re-read).
- The guide case that names the registry → **met** (02-M, new).
- FIX-018's routed T1 and T2 → **met** (both survivors caught).
- The story file, the changed files and the full suite → **met** (253 focused; 5,890 / 12 / 1 / 0
  in full).

**Production verification:** `pending_deployment`. FIX-019 changes the registry, tests and docs.
The commit and the push each need the owner's word, in a job-free window (safest 00:10–06:20 IST),
and never on the 1st before the 09:00 monthly forecast. After the deploy, run guide 02-M: LTIM's
analysis shows `decision_gate.identity` LTM.NS with basis LTIM and the technicals' symbol LTM.NS,
and its next review close reads `agree`.

**Commit-time edits** (with the commit, at the owner's word; none is made by this review):

- **Code commit:** exactly the 8 reviewed files. `kt_manifest.py verify FIX-019-manifest.json
  --rev HEAD` must give 0 mismatches (`9f3de76f`).
- **Docs commit**, holding:
  - the KT header (`Code inspected` = that code commit; edition = the commit's date);
  - KT section 1's production paragraph. Replace the text from "Production runs `ffa012b`" to
    "per-symbol record (sections 6 and 7)." with: "Production runs `53e3f0e` (PR-009, FIX-016
    and FIX-018), deployed at about 09:20 IST on 30 October 2026 (the deployment list showed it
    SUCCESS and `/health` answered 200). The inspected code adds FIX-019's instrument-registry
    records (section 4). It is committed but not yet deployed, and counts as running only once a
    read-only check of the deployment list and `/health` confirms that deploy." The sentence "The
    table gives the configuration …" stays;
  - **L1 (a)**, KT section 4: "Without the record, the app asked for the old code, which Yahoo
    and NSE no longer answer." → "Without the record, the app asked for the old code: Yahoo no
    longer prices it, and NSE lists no corporate action under it, although NSE's close still
    answers it with the new code's rows.";
  - **L1 (b)**, KT section 4: "So it does not map the configured codes NSE has never listed:" →
    "So it does not map the configured codes NSE does not list:", and after "so none can be
    bought or graded." add "Five were never NSE codes. BAYER and NIIT once were, for Bayer India
    and NIIT (NSE lists their rows from 2002–2003), under ISINs other than those of today's
    BAYERCROP and NIITLTD.";
  - KT section 12's FIX-019 row: `Open` → `Done`;
  - guide 02-M status: "FIX-019: implemented 2026-10-30; fresh review pending." → "FIX-019:
    accepted 2026-10-30, committed as `<code commit>`; production verification pending.";
  - guide 07-L and 09-H status (now stale since the deploy): "PR-009: accepted 2026-10-24,
    committed as `2d290d5`; production verification pending. FIX-016: accepted 2026-10-29; it
    ships with PR-009 and FIX-018. FIX-018: accepted 2026-10-29; it ships with PR-009 and
    FIX-016." → "PR-009 (`2d290d5`), FIX-016 (`aa29f69`) and FIX-018 (`53e3f0e`): accepted,
    deployed on 30 October 2026; production verification pending.";
  - guide 07-M status: "FIX-016: accepted 2026-10-29; it ships with PR-009 and FIX-018." →
    "FIX-016: accepted 2026-10-29, committed as `aa29f69`, deployed on 30 October 2026;
    production verification pending.";
  - the PDF, regenerated, with `check_kt_docs` errors `[]`;
  - the receipts and manifest, the FIX-019 and FIX-020 cards, the PI README, STATE and HANDOFF,
    with the uncommitted deploy record (STATE and HANDOFF) already in the tree.

**Decision: ACCEPTED.** STATE: FIX-019 `done`, production `pending_deployment`; `active_task`
null; `next_task` **SA-048** (implementation, in a new conversation). It is the first planned
`todo` story whose dependencies are done, in STATE order, and FIX-019's card places it next.
