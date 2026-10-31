# FIX-019 — implementation receipt

**Story:** [FIX-019](../stories/FIX-019.md): find out why NSE lists no corporate action for 14
configured codes, and map the stale ones. It also carries FIX-018's two routed test gaps (T1, T2).

**Phase:** implementation, 30 Oct 2026, about 11:00–12:05 IST. Session `stockagent-main-6e`
[9d0264], a new conversation opened with "continue". The peers `-5d`, `-f2`, `-4f`, `-8a`, `-49` and
`-f0` were idle at the start and before the bookkeeping (ListAgents). This phase includes a
same-conversation self-review, which is not the fresh review.

**Baseline:** HEAD `48db226` (FIX-018's docs commit; `53e3f0e` holds FIX-018). `main` was pushed at
09:10 IST (`d7c1411..48db226`); the deploy is not confirmed. The working tree held only session
`-f2`'s uncommitted push record in STATE and HANDOFF, which is kept.

**Status after this phase:** `review_required`. Nothing was committed, pushed, deployed or
configured. No production state was read, no model was called and no message was sent. **Public
data was read**, read-only and with no credentials:

- from NSE, the symbol-change list and the equity list, the 29 Oct bhavcopy, corporate-action lists
  and company announcements;
- from Yahoo, daily closes.

Raw answers are in the ignored folder `analysis_data/fix019/`. Every test fakes NSE and Yahoo.

## Amendment 1 — the owner's answers to Q1 and Q2 (30 Oct, about 19:47–20:20 IST)

The owner, after the phase above: "on the 2 open questions, do as per recommendation". The same
session applied it before any review. FIX-019 went back to `in_progress` for the edit and
returns to `review_required`. It is still uncommitted, and the fresh review covers both parts.
The peers stayed idle (ListAgents).

- **Q1, applied.** `config/instruments.yaml` records the two codes that no longer trade:
  - **GATI:** GATI.NS until 30 Nov 2023. Then ACLGATI.NS, `via: rename`, citing NSE/CML/59502
    (NSE's notice of 24 Nov 2023, attached to the company's "Name and Symbol Change" filing; its
    ISIN INE152B01027 is on all 20 rows of ACLGATI's list). Then `delisted` from 12 Nov 2025,
    citing NSE's "Suspension of Trading" notice of 6 Nov 2025.
  - **INOXLEISUR:** INOXLEISUR.NS until 17 Feb 2023, then `delisted`, citing NSE's notice of
    14 Feb 2023.
  - One basis each and no successors (F19-D7).
- **Q2, routed.** A new card, [FIX-020](../stories/FIX-020.md): P2, 1 point. It sits after
  FIX-017 at the end of the routed queue (routing was delegated), with a revisit trigger if the
  owner wants NIIT analysed sooner. Its first step asks the owner which company APL means. KT
  section 4 points to it as **Planned**, and section 12 has its row. FIX-019 maps none of the
  seven codes.
- **Live after-check** (`after_check.py GATI INOXLEISUR`, 19:50–19:51 IST, through the app's
  resolver and the strict reader):

  | Ticker | Identity | Yahoo symbol | NSE code | NSE rows | Yahoo bars |
  |---|---|---|---|---|---|
  | GATI | `delisted`, basis GATI | ACLGATI.NS | ACLGATI | 20 | 0 |
  | INOXLEISUR | `delisted`, basis INOXLEISUR | INOXLEISUR.NS | INOXLEISUR | 16 | 0 |

- **What it changes:**
  - Both identities are quarantined, so the gate abstains on an analysis of either. Both
    sectors, logistics and media, are disabled.
  - GATI's NSE list is now read under ACLGATI, so it is no longer empty. The KT section 6 count
    becomes 9 empty lists, 5 of them for codes without a price.
- **Docs:**
  - KT section 4: the delisted paragraph, and the never-listed paragraph with its FIX-020
    pointer;
  - the KT config-table row, section 6's count and section 12's FIX-020 row;
  - the PDF, rebuilt;
  - CODEBASE and guide case 02-M;
  - the FIX-019 card's "Owner decisions" section and a hard-review question.
- **In-place updates below:** the GATI row, the counts, INOXLEISUR's row count, F19-D4 and
  F19-D7, the changed contracts, tests, review input, the hard-review answers and the owner
  questions.

## In one example

The app's ticker LTIM is LTIMindtree. NSE changed its trading symbol to LTM on 27 Feb 2026
(circular NSE/CML/72948), with the ISIN unchanged.

- **Before:** the app asked Yahoo for LTIM.NS and NSE for LTIM. Yahoo answered nothing and NSE
  listed no corporate action. LTIM, in the enabled IT sector, had no price, and under FIX-018 a
  decision on it would be set aside for good.
- **Now:** a dated `rename` record prices LTIM from LTM.NS and asks NSE for LTM, on every date.
  The basis stays LTIM, so a forecast issued under the old code is graded against a close under
  the new one. On 30 Oct, NSE listed 20 rows under LTM (the latest an interim dividend ex 23 Oct
  2026), and Yahoo held 2,539 sessions under LTM.NS, from 21 Jul 2016.

## What the evidence shows

On 29 Oct the probe read the lists with `fetch_corp_actions`, which returns `[]` for a failed read
too. On 30 Oct (11:07–11:11 IST), the strict `read_corp_actions` read each of the 14 twice, and
NSE answered an empty list each time. All 14 are true empty answers. The candidate codes were read
at 11:13–11:15 and the follow-ups at 11:16–11:17 IST (probe scripts and raw answers in
`analysis_data/fix019/`).

| Code | NSE today | Evidence (source, reference, date) | Candidate: NSE list; Yahoo | Action |
|---|---|---|---|---|
| PVR | not in the equity list | NSE symbol-change list: PVR → PVRINOX from 12 May 2023; NSE/CML/56638, 8 May 2023, filed with "Name and Symbol Change"; same ISIN INE191H01014 in the equity list and bhavcopy | PVRINOX: 20 rows; PVRINOX.NS 5,134 sessions from 4 Jan 2006 | `rename` record |
| MCDOWELL-N | not listed | symbol-change list: → UNITDSPR from 7 Jun 2024; NSE/CML/62353, 6 Jun 2024; ISIN INE854D01024 | UNITDSPR: 20 rows; UNITDSPR.NS 6,039 sessions from 1 Jul 2002 | `rename` record |
| ZOMATO | not listed | symbol-change list: → ETERNAL from 9 Apr 2025; NSE/CML/67420, 3 Apr 2025; ISIN INE758T01015 | ETERNAL: **empty**; ETERNAL.NS 1,304 sessions from 23 Jul 2021 (the listing) | `rename` record; the list stays empty |
| LTIM | not listed | symbol-change list: LTI → LTIM 5 Dec 2022, LTIM → LTM from 27 Feb 2026; NSE/CML/72948, 23 Feb 2026; the company's filing of 27 Feb 2026; ISIN INE214T01019 | LTM: 20 rows; LTM.NS 2,539 sessions from 21 Jul 2016 | `rename` record |
| ICICIPRULI | not listed | symbol-change list: → ICICILIFE from 23 Oct 2026; NSE/CML/76967, 16 Oct 2026; the company's name-change filing of 22 Sep 2026; ISIN INE726G01019 | ICICILIFE: 13 rows (back to 2016); ICICILIFE.NS 12 sessions from 14 Oct 2026, the same closes as ICICIPRULI.NS on all 12 days to 29 Oct; ICICIPRULI.NS has no 30 Oct bar | `rename` record (F19-D2) |
| GATI | not listed | symbol-change list: → ACLGATI from 30 Nov 2023 (NSE/CML/59502); NSE notice of 6 Nov 2025: Allcargo Gati suspended from 12 Nov 2025 "on account of the Scheme of Amalgamation"; scheme effective per the company, 1 Nov 2025 | ACLGATI: not listed, not in the bhavcopy, 20 historical rows (the first an undated "Merger"), each with the notice's ISIN INE152B01027; Yahoo none | `rename` to ACLGATI, then `delisted` from 12 Nov 2025 (amendment 1, the owner's Q1) |
| AAVAS | listed (INE216P01012, since 8 Oct 2018) | — | Yahoo prices it | none: NSE lists nothing for the company |
| IDEAFORGE | listed (INE349Y01013, since 7 Jul 2023) | — | Yahoo prices it | none |
| STARHEALTH | listed (INE575P01011, since 10 Dec 2021) | — | Yahoo prices it | none |
| ACCCEMENT | never listed | not in the equity list, the bhavcopy or any of the 1,078 symbol-change rows | by name only: ACC (ACC Limited, 20 rows); Yahoo none for ACCCEMENT.NS | not mapped (F19-D3), proposed (Q2) |
| APL | never listed | as above | by name only: APLAPOLLO (APL Apollo Tubes, 17 rows) or APLLTD (Alembic Pharmaceuticals); Yahoo none | not mapped, proposed |
| DEEPAKNITRI | never listed | as above | by name only: DEEPAKNTR (Deepak Nitrite, 18 rows); Yahoo none | not mapped, proposed |
| MAHINDHOTEL | never listed | as above | by name only: MHRIL (Mahindra Holidays & Resorts, 12 rows); Yahoo none | not mapped, proposed |
| MTAR | never listed | as above | by name only: MTARTECH (MTAR Technologies, 4 rows); Yahoo none | not mapped, proposed |

**The count the KT limit now gives.** Five of the 14 now read rows: PVR, MCDOWELL-N, LTIM,
ICICIPRULI and, since amendment 1, GATI (ACLGATI's 20 historical rows). Nine lists stay empty:

- **4 with a price:** AAVAS, IDEAFORGE, STARHEALTH and ZOMATO. These are the only ones that can
  carry a decision, and so use FIX-018's cap.
- **5 without a price:** ACCCEMENT, APL, DEEPAKNITRI, MAHINDHOTEL and MTAR. None can be bought or
  graded.

**Whole configured universe.** I checked all 202 symbols under `nse_symbol` against NSE's equity
list and symbol-change list of 30 Oct. Before the records, 14 codes were not listed today:

- the 6 renamed away;
- 7 that NSE never listed, the 5 above plus BAYER and NIIT;
- INOXLEISUR.

The five records bring this to 9. Amendment 1 records two of the 9, GATI and INOXLEISUR, as
`delisted`; the 7 that NSE never listed are FIX-020's.

**Found on the way, not in the card's 14:**

- **INOXLEISUR no longer trades.** It merged into PVR Ltd, the transferee. NSE suspended trading
  from 17 Feb 2023 "on account of Scheme of Amalgamation", with a record date of 17 Feb 2023. It is
  not in the equity list and Yahoo has no price. Its NSE list holds 16 rows, the newest an undated
  "Merger" (the strict reader, 19:51 IST). Proposed with GATI (Q1), and recorded as `delisted` in
  amendment 1.
- **BAYER and NIIT are not NSE codes.** By name, Bayer CropScience trades as BAYERCROP and NIIT Ltd
  as NIITLTD. NSE's lists under BAYER and NIIT hold 2 rows each, from 2002–2003, and Yahoo has no
  price under either code. NIIT is in the enabled IT sector. Proposed with the misspelt codes (Q2).
- **AAVAS is filed in the wrong sector.** It is Aavas Financiers, a housing-finance company, but it
  sits under `chemicals` in `sectors/registry.py`. Proposed with Q2.

## What changed

- **`config/instruments.yaml`:** five dated `rename` records under one comment. Each holds the old
  code until the effective date, then the new code from it, `via: rename`, with NSE's circular as
  evidence. The basis is the ticker's own name.
- **`tests/unit/test_registry_fix019.py` (new, 10 tests):**
  - each ticker resolves on four dates, before its rename included, to the new code for Yahoo
    and NSE, `resolved`, with the ticker's basis;
  - its identity reads `listing` the day before and `rename` from the date;
  - there is no basis break across the date, and one basis over all time;
  - the rename segment cites the circular;
  - through FIX-016's market model, where NSE knows only its own codes: grading reads NSE's list
    under the new code once and grades a 1:5 split it holds (×5, return 0, the sale wrong);
  - under the suite's empty registry, the same decision has no result.
- **`tests/unit/test_exit_fix018.py` (+2):**
  - **T1:** with the card's example, a list starting on the close day (1 Sep 2026) is graded ×1,
    and one starting a session later is lasting, with its reason;
  - **T2:** a decision temporary at 10 sessions and lasting at 30 is set aside, the week passes,
    and both the stored look and the scorecard line name the lasting reason.
- **`tests/unit/shared/test_instrument_identity_sa008.py`:** the shipped-registry test expects the
  five renames as well (see Changed contracts).
- **Docs:**
  - KT section 4: what the registry records for the five renames, why codes are mapped only on
    exchange evidence, which configured codes are therefore not mapped, and Yahoo's partial
    ICICILIFE history;
  - KT section 4's config-table row;
  - KT section 6's limit: the count of empty lists, with no **Planned** pointer left;
  - the PDF, rebuilt;
  - CODEBASE's instrument-identity paragraph;
  - guide case 02-M (new) and section 02's related-PI line.

No application code changed.

## Decisions (implementer's, recorded for the review)

- **F19-D1, the record's shape.** It follows the header's example. The old code runs until the
  effective date and the new code from it, with one basis, the ticker's own name. That name is
  the basis every stored row of the ticker already carries, because the naive identity's basis is
  its symbol's root. `instruments._current_symbol` asks the new code for every date of the basis,
  since Yahoo and NSE moved the history. The dated form keeps the identity stamp honest: `listing`
  before the date, `rename` from it.
- **F19-D2, ICICIPRULI mapped now.** Yahoo's ICICILIFE.NS holds only 12 sessions, so I weighed
  the two choices:
  - **with the record:** current closes and NSE's list, but a short Yahoo history until Yahoo
    carries the rest;
  - **without it:** no price after 29 Oct, since ICICIPRULI.NS has no 30 Oct bar, and no NSE list
    at all.

  The identity is certain: an NSE circular, the notice's ISIN the same as the new code's today,
  and the same closes on all 12 common days. Insurance is a disabled sector, and production held no ICICIPRULI on 29 Oct (FIX-017's
  probe; not re-read). The short history is a KT section 4 line.
- **F19-D3, no mapping for a code NSE never listed.** Nothing but the company name ties
  ACCCEMENT, APL, DEEPAKNITRI, MAHINDHOTEL or MTAR to a security, and the card bars name matches.
  APL even has two plausible candidates. SA-008 accepted TVSMOTORS and CANARABANK as aliases on a
  stated reason alone; this card's rule is stricter, and I applied it. These codes have no price,
  so they carry no decision and use none of FIX-018's cap. Correcting them belongs in the sector
  list, not the registry: proposed (Q2).
- **F19-D4, GATI and INOXLEISUR were proposed, not changed** (the card's rule). Neither has a price
  today. A `delisted` segment would quarantine what already cannot be priced, and would state why.
  **Superseded by amendment 1:** the owner said yes, and both are recorded.
- **F19-D7 (amendment 1), the delisted records' shape.** Each `delisted` segment starts on the
  first day NSE's notice says trading stopped, not on the record date or the scheme's effective
  date: that is the first day no close exists. It carries no symbol, so the identity names the
  last code the basis traded under (ACLGATI.NS, INOXLEISUR.NS). It keeps the ticker's basis, and
  cites NSE's notice as evidence, which the registry requires only to resolve. No successor is
  recorded: production held neither on 29 Oct, and neither has a price.
- **F19-D5, T1 and T2 are new tests, not copies of RV6 and RV7.** Their expected values are worked
  from the card's example. T2 also checks the scorecard line, not only the stored look.
- **F19-D6, the grading test reuses FIX-016's `_Market`,** in which NSE answers only a code it
  lists, as it did for "ZOMATO" and "LTIM". Its negative half switches to the suite's empty
  registry and shows that the record is what makes grading read the list.

## Changed contracts

- **SA-008's `test_the_shipped_registry_is_valid`:** `set(loaded.entries)` must equal
  `FORMER_OVERRIDES | NSE_RENAMES | NSE_DELISTED` (the last since amendment 1), where it was
  `FORMER_OVERRIDES`. The module docstring names the five renames and the two delisted codes. No
  assertion is relaxed: the four former entries stay pinned by
  `test_every_former_override_is_registered_with_the_same_symbol` and `test_the_shipped_identities`.
- **Amendment 1's runtime effect on GATI and INOXLEISUR** (both in disabled sectors, logistics
  and media):
  - the identity is `delisted` from the day trading stopped, so the decision gate abstains on
    an analysis of either, through `decision_gate.mode`;
  - GATI's Yahoo symbol is ACLGATI.NS (no bars, as GATI.NS had none), and NSE is asked for
    ACLGATI, whose list holds 20 historical rows where GATI's was empty;
  - INOXLEISUR is still asked for under its own code.
- **The registry's runtime effect on the five tickers:**
  - the Yahoo symbol, the NSE close cross-check, NSE's corporate-action list and the event feed's
    NSE code are now the new code;
  - the identity stamp reads `source: registry`, `via: rename`, with the basis unchanged;
  - a registered ticker is never self-healed, so a learned mapping in production's cache for any
    of the five is no longer consulted.

## Tests

- **Amendment 1, on the final bytes:**
  - `tests/unit/test_registry_fix019.py` gained 3 tests (13 in all):
    - each delisted code is `resolved` the day before trading stopped, and `delisted` from that
      day and today, with its reason, NSE's code and one basis;
    - the gate abstains on it;
    - its segment has no successors and cites NSE's notice;
    - GATI resolves as ACLGATI.NS with `via: rename` from 30 Nov 2023, with no basis break and
      its circular.
  - Story files: 253 passed (13 + 39 + 127 + 39 + 35, 2m17s;
    `analysis_data/fix019/story_final_amend1.txt`).
  - Registry mutants: 19 of 19 caught, baseline clean (13 passed;
    `analysis_data/fix019/reg_mutants_amend1.txt`). The 8 new ones:
    - INOXLEISUR's record dropped;
    - INOXLEISUR delisted a day early, GATI a day late;
    - GATI `suspended` instead of `delisted`;
    - a new basis on GATI's delisting;
    - GATI's rename keeping the old code;
    - GATI's delisting without its notice;
    - the gate passing a delisted identity (`decision_gate.apply_identity`).
  - Full suite: 5,890 passed / 12 skipped / 1 xfailed / 0 failed (16m37s, 19:57–20:14 IST; the
    5,887 above plus the 3 new tests). No tracked runtime file changed. Output:
    `analysis_data/fix019/full_suite_amend1.txt`.
  - Checks: `check_broad_except` OK (151); `check_kt_docs` errors `[]`; PDF 61 pages, source
    `e2ec3ca6`.

  The rest of this section is the first phase's record.
- **Story files:**
  - `tests/unit/test_registry_fix019.py`: 10 passed;
  - `tests/unit/test_exit_fix018.py`: 39 passed (37 + 2);
  - SA-008's `tests/unit/shared/test_instrument_identity_sa008.py`: 35 passed;
  - with FIX-016's and PR-009's story files: 250 (10 + 39 + 127 + 39 + 35, 3m09s, on the final bytes; `analysis_data/fix019/story_final.txt`) passed.
- **FIX-018's routed survivors,** run with the reviewer's harness (`analysis_data/fix018_review/
  rv_mutants.py`) against the three FIX-018 story files: baseline clean (205 passed);
  `late_list_inclusive` caught (T1); `lasting_reason_any_kind` caught (T2). Output:
  `analysis_data/fix019/t1t2_mutants.txt`.
- **Registry and resolver mutants** (`analysis_data/fix019/reg_mutants.py`, with `reg_mutplug.py`;
  in memory, and the shipped file is never written): 11 of 11 caught, baseline clean (10 passed); output `analysis_data/fix019/reg_mutants.txt`. They cover:
  - a record dropped, a new basis, alias instead of rename, the old code kept, a late `until`, a
    late `from`, a wrong circular, the dates dropped, a different basis before the date;
  - `nse_symbol` that maps only aliases;
  - a rename that asks the old symbol.
- **Live after-check** (`analysis_data/fix019/after_check.py`, through the app's own
  `resolve_identity`, `nse_symbol` and the strict reader, 30 Oct 11:22 IST):

  | Ticker | Yahoo symbol | NSE code | NSE rows | Yahoo sessions |
  |---|---|---|---|---|
  | PVR | PVRINOX.NS | PVRINOX | 20 | 5,134 |
  | MCDOWELL-N | UNITDSPR.NS | UNITDSPR | 20 | 6,039 |
  | ZOMATO | ETERNAL.NS | ETERNAL | 0 | 1,304 |
  | LTIM | LTM.NS | LTM | 20 | 2,539 |
  | ICICIPRULI | ICICILIFE.NS | ICICILIFE | 13 | 12 |

  All five are `resolved`, with the ticker's basis.
- **Full suite:** 5,887 passed / 12 skipped / 1 xfailed / 0 failed (23m53s, 11:30–11:54 IST; the previous 5,875 plus this story's 12). A YAML comment in `config/instruments.yaml` was reworded during that run, with the records unchanged; the story files were then re-run on the final bytes (250 passed, above). No tracked runtime file changed (`git status`). Output: `analysis_data/fix019/full_suite.txt`.
- **Checks:** `check_broad_except` OK (151 grandfathered); `check_kt_docs` errors `[]`; PDF 61 pages, source `fc69c28c`.

## Review input

- **Manifest:** [FIX-019-manifest.json](FIX-019-manifest.json)
  `9f3de76f550b29f43be861c7acc916d561740529eb114b27ec0560d89ee83c83` (8 files, the same paths;
  `kt_manifest.py verify` 0 mismatches), rewritten after amendment 1.
- **Diff:** `7fd9ac2fb81694328145c92982bb138eea95cb52bdaaf3982a1d83888f55d5b7` (36,860 B, 7 paths:
  every manifest path but the PDF, against HEAD `48db226`), from `analysis_data/fix019/digest.py`.
- **Superseded:** the first phase's `97abf4b3…` and `160834f8…`.

## For the fresh review (the card's hard-review questions)

- **Is each mapping the same listed security, with exchange or company evidence, never a name
  match?** Each of the five has:
  - a row in NSE's symbol-change list;
  - an NSE circular, attached to the company's own "Name and Symbol Change" filing;
  - that notice's ISIN equal to the one NSE's equity list and the 29 Oct bhavcopy give the new
    code today (PVR INE191H01014, MCDOWELL-N INE854D01024, ZOMATO INE758T01015, LTIM
    INE214T01019, ICICIPRULI INE726G01019), and carried by every row of the new code's
    corporate-action list.

  The five codes NSE never listed are not mapped (F19-D3).
- **Could an entry join two price bases, such as a merger's successor priced as the old company?**
  - **Basis:** each record has one basis, and the test pins it over all time.
  - **PVR:** INOX Leisure merged into PVR Ltd, the transferee (INOX's filing of 12 Jan 2023).
    PVR's ISIN is the same in every row of its list back to 2007. Across the merger's record date
    of 17 Feb 2023, Yahoo's close moves from 1,711.05 to 1,655.40 (−3.3%), an ordinary day with
    no ratio step. The rename three months later changed only the name and the code.
  - **LTIM:** LTM is LTI's listing. NSE's equity list gives 21 Jul 2016 as its listing date, and
    every row of its list back to 2017 carries the same ISIN.
  - **The rest:** ZOMATO, MCDOWELL-N and ICICIPRULI are name and symbol changes only.
- **Does any changed Yahoo symbol alter a live holding's price?**
  - **Last read:** the production holdings were REDINGTON and WELCORP (FIX-017's read-only probe,
    29 Oct about 10:42 IST), none of the five. This phase read no production state.
  - **Older renames:** for four of the five, Yahoo stopped answering the old code months ago, so
    nothing could have been bought at a price under it since.
  - **ICICIPRULI:** Yahoo priced it under the old code until 29 Oct. Insurance is a disabled
    sector.
- **For the two delisted codes (amendment 1): is the quarantine dated from the first day each
  did not trade, and does it change anything but codes nobody prices?**
  - **Dates:** each `delisted` segment starts on the day NSE's notice names: "suspended w.e.f.
    November 12, 2025 (i.e., closing hours of trading on November 11, 2025)" for Allcargo Gati,
    and "w.e.f. February 17, 2023 (i.e., closing hours of trading on February 16, 2023)" for
    INOX Leisure. The tests pin `resolved` the day before and `delisted` from the day itself,
    and mutants that move either date by one day are caught.
  - **Effect:** neither code has a Yahoo price under any of its codes, and both sectors are
    disabled. The quarantine only names, on the gate, why an analysis of either cannot act.

## Owner questions

**Answered 30 Oct 2026 (about 19:45 IST):** "on the 2 open questions, do as per
recommendation". Q1 is applied in amendment 1. Q2 is routed to
[FIX-020](../stories/FIX-020.md). Asked which company APL means, the owner delegated the choice
("i trust your expertise, do as per recommendation", about 21:10 IST). It is APL Apollo Tubes
(APLAPOLLO), by its configured sector: `metals`, beside two steel-pipe makers. That decision is
recorded on FIX-020's card.

- **Q1. Record GATI and INOXLEISUR as delisted?** Example: Allcargo Gati, GATI's company, last
  traded on 11 Nov 2025; its shares were exchanged under the amalgamation. Today the app asks for
  a code nobody quotes, and the registry does not say why. **Recommendation:**
  - a `rename` segment for GATI (to ACLGATI from 30 Nov 2023, NSE/CML/59502), then a `delisted`
    segment from 12 Nov 2025;
  - for INOXLEISUR, a `delisted` segment from 17 Feb 2023;
  - no successors, since nothing is held.

  Nothing else changes, because neither has a price today.
- **Q2. Correct the configured codes NSE does not list?** Example: DEEPAKNITRI sits in the
  chemicals list. NSE trades Deepak Nitrite as DEEPAKNTR, and the app has never priced
  DEEPAKNITRI. **Recommendation:** one small card that:
  - replaces each code in `sectors/registry.py` with NSE's: DEEPAKNTR, MTARTECH, ACC, MHRIL,
    BAYERCROP and NIITLTD, where the configured name leaves no doubt;
  - asks the owner which company APL means;
  - moves AAVAS out of `chemicals`.

  NIIT is in the enabled IT sector; the others are in disabled sectors.
