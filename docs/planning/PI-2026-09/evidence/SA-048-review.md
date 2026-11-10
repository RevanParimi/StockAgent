# SA-048 review receipt — realistic trading costs and tax in paper P&L

## Fresh review: ACCEPTED (2026-10-31)

**Phase:** fresh-session review, a new conversation opened with "continue" (31 Oct, about
17:24–18:05 IST, session `stockagent-main-23` [ac9d57]). SA-048 was implemented in
`stockagent-main-5c` [539204]. This conversation did not read that chat or any earlier one. The
peers `-5d`, `-f2`, `-4f`, `-8a`, `-5c`, `-49`, `-f0`, `-39`, `-e0`, `-b4`, `-6e` and `-6b` were
idle at the start and before the bookkeeping (ListAgents).

**Verdict: ACCEPTED** for the reviewed revision below.

- Every acceptance criterion on the card holds. The card's three hard-review questions are
  answered below. Two rates were read in their primary documents: NSE's circular for the exchange
  charge, and the Income-tax Act 2025's sections for the tax rates.
- My own cases trace one account through a manual add, an ADD, a TRIM and an EXIT, through
  the real API and executor, to the paisa. They also check every charge against an exact-fraction
  oracle on 4,010 values, and the tax estimate against an oracle of the Act's set-off order on
  400 random ledgers.
- No finding is critical or high. One is medium:
  - **M1:** the tax estimate prices sold shares at the position's average cost, where the law
    takes each lot's own cost, oldest first. A sale that takes long-term and short-term shares
    bought at different prices can read low (₹0 where the law gives ₹4,160) or high (₹3,120 where
    it gives ₹0).
  - It is outside the card's criteria and the figure is labelled an estimate, so it is routed to
    a new card, [FIX-022](../stories/FIX-022.md). The KT and the autopilot guide get a
    commit-time sentence that says so.
- Two findings are low and go to FIX-022 as well: L1, a CSV import with a missing rate saves half
  an import; L2, a renamed position loses its buy charges and dates. Three notes are
  informational (I1–I3).

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called and no message was sent. The review read three public pages: NSE's circular PDF and
two web searches (below). Tracked files changed by this review: STATE, HANDOFF, the PI README, this
receipt and the new FIX-022 card. The reviewer's scripts and outputs are in the ignored
`analysis_data/sa048_review/`.

### In one example (RV2: one account, four trades, by hand)

₹5,00,000 cash, caps 50% / 100%, floor ₹10,000, ADD tranche 25%, TRIM 40%.

1. **Manual add:** 200 ZEN at ₹1,234.50, bought 2 Jun 2025 (₹2,46,900).
   - Charges: STT 246.9 → ₹247; stamp 37.035 → ₹37.04; NSE 7.57983 → ₹7.58; SEBI ₹0.25; GST 18%
     of 7.83 → ₹1.41. Total ₹293.28.
   - `capital_in` becomes ₹7,47,193.28 and cash does not move.
2. **ADD,** 13 Jul 2026 at ₹1,300: 50 shares (₹65,000).
   - Charges: STT ₹65; stamp ₹9.75; NSE 1.9955 → ₹2.00; SEBI 0.065 → ₹0.07; GST ₹0.37. Total
     ₹77.19. Cash ₹4,34,922.81; average cost ₹1,247.60.
   - Valued at ₹1,300, `/performance` gives unrealized ₹13,100.00 = 250 × ₹52.40. That is
     total P&L ₹12,729.53 plus the ₹370.47 charged. `on_open_positions` ₹370.47.
3. **TRIM,** 14 Jul at ₹1,400: 100 shares (₹1,40,000).
   - Charges: STT ₹140; NSE ₹4.30; SEBI ₹0.14; GST ₹0.80; DP ₹15.34. Total ₹160.58.
   - Realized ₹15,240. Its costs are ₹160.58 plus 100/250 of ₹370.47 (₹148.19) = ₹308.77, so
     net ₹14,931.23. ₹222.28 stays on the open shares; unrealized ₹22,860.00 = 150 × ₹152.40.
4. **EXIT,** 15 Jul at ₹1,350: 150 shares (₹2,02,500).
   - Charges: STT 202.5 → ₹203 (half up, rule 4); NSE 6.21675 → ₹6.22; SEBI ₹0.20; GST ₹1.16;
     DP ₹15.34. Total ₹225.92. Cash ₹7,77,036.31.
5. **Result:** realized ₹30,600 gross. Costs ₹756.97 (= every charge). Net ₹29,843.03, which
   equals equity − `capital_in` (7,77,036.31 − 7,47,193.28). Unrealized ₹0.00.
6. **Tax, FY 2026-27, by the KT's method:**
   - TRIM: +₹15,196.032, all long-term (the June 2025 lot).
   - EXIT: +₹15,301.998, of which 100 shares long-term (₹10,201.332) and 50 short-term
     (₹5,100.666).
   - Long-term ₹25,397.36 is all exempt. Short-term at 20% = ₹1,020.13, plus cess ₹40.81:
     **₹1,060.94**. Every figure matched.

Lot by lot, as the law takes it (M1), the same year's short-term gain is ₹2,480.17: tax ₹496.03
plus ₹19.84 cess, ₹515.87. The KT's average-cost method reads ₹545.07 high here. The low case is
in M1.

### Review input verified

- Manifest [SA-048-manifest.json](SA-048-manifest.json) `6e473449ae38daada2bd7ce9285943ba281bbc69fcfb1f88835f0941ec1c0346`
  (24 files): `kt_manifest.py verify` 0 mismatches, at the start (17:25 IST) and the end (17:56).
- Diff `ed6d086b552c19e455174dc3098cd6246c34fa064d2cb086446da97153e74034` (143,587 B, 23
  paths, every path against HEAD `c1d5b18`; the two new files against `/dev/null`; nothing
  staged): `analysis_data/sa048_review/rv_digest.py`, the implementer's recipe in this folder,
  also checking each file's blob. The same at the start and the end.
- The working tree also holds STATE and HANDOFF with the uncommitted FIX-021 deploy record. They
  are not part of SA-048's input.

### Contract checked

- **Charges at trade time, one row, out of cash:** the executor's SELL and BUY, the manual add,
  the manual delete and the CSV import.
  - Each computes `trade_costs` and writes it on the trade's own `TransactionRecord.costs`.
  - The executor and the delete move cash by value ± and − charges in the same portfolio save.
  - The add and the import put value + charges into `capital_in`, since no cash moves (SA48-D3).
  - The executor appends the rows and then saves once, under the same txn_id dedupe as before.
- **Rates:** read from `portfolio.costs` / `portfolio.tax`. The settings fall back to `{}`, and
  `cost_rates()` raises on any missing key, so no rate is hard-coded and none is a silent zero.
  RV0 checks the configured rates against the primary figures.
- **Rounding:** STT value and tax to the rupee, half up (STT Rules 2004, rule 4). Everything else
  to the paisa, half up. GST on the rounded brokerage, exchange and SEBI parts. RV1's
  `Fraction` oracle agrees to the paisa on every part of 4,010 values × both sides, including the
  half-paisa and half-rupee boundaries (202.5 → 203, 0.065 → 0.07, 37.035 → 37.04).
- **Consumers traced:**
  - `reconcile.py` checks only the cash chain and the final cash, so charges inside
    `cash_after` pass.
  - `results.capital_flows` takes the add's charges in as money (`capital_in` delta + qty ×
    close − value).
  - `/performance` gives:
    - `realized_pnl` unchanged and equal to `realized.gross` (DIV rows carry 0);
    - unrealized = `total_pnl − realized + charged`, the open holdings' price gain (RV2 at
      three points).
  - `/transactions` estimates old rows, labelled. The screen falls back to `realized_pnl` without
    `realized`. The alert says "before costs" and "costs ₹Y".
  - The weekly scorecard stays before costs (SA48-D11).
- **Compatibility and rollback:** `costs` is optional, so old rows parse. HEAD's schema
  (`git show HEAD:…`) reads a row with `costs`, ignoring the field
  (`analysis_data/sa048_review/rollback_read.txt`), so a revert reads the new rows.
- **Tax:** per financial year, April to March.
  - Long-term when sold after the same day 12 months on; exactly 12 months is short-term, and
    29 Feb plus 12 months is 28 Feb (RV3 boundary cases, against dateutil).
  - Set-off per the Act: a short-term loss offsets short-term gains, then long-term gains. A
    long-term loss offsets long-term gains only.
  - The exemption once a year, then 20% / 12.5% and a 4% cess. STT is not deductible.
  - RV3's oracle agrees on 400 random ledgers (more than 600 years). Its counters prove it
    exercised a long-term loss beside a taxed short-term gain, a short-term loss reaching
    long-term gains, and a capped exemption.
  - Law-derived properties hold on 200 ledgers × 4 extra trades: an added loss never raises the
    year's tax, an added gain never lowers it, tax ≥ 0 and 0 ≤ exemption ≤ ₹1,25,000.

### The card's hard-review questions

- **Rates against a primary source, dated (31 Oct 2026):**

  | Rate | Read | Primary? |
  |---|---|---|
  | NSE cash market | NSE/FA/73061 (27 Feb 2026), the PDF itself: ₹306.99 per crore transaction charge + ₹0.01 NSE IPFT = ₹307 each side, from 1 Mar 2026 (was ₹297 + ₹10). 0.00307% = ₹307 per crore. | yes |
  | STCG 20%, LTCG 12.5% above ₹1,25,000 | Income-tax Act 2025, s.196 and s.198, incometaxindia.gov.in pages (as search extracts) | yes, via the department's site |
  | STT 0.1% each side, delivery | secondary sources agree that Budget 2026 raised F&O STT only | no |
  | Stamp 0.015% buy; SEBI ₹10 per crore; GST 18%; DP ₹15.34; cess 4% | the implementer's broker page; not re-read | no |

  So the exchange charge and the tax rates now have primary sources. The others are standing
  rates from secondary sources, which is acceptable for an estimate whose rates are config with an
  `as_of`. I1 corrects the exchange comment's "IPFT left out".
- **No hard-coded rate:** met (above; `test_config_carries_every_rate_with_its_check_date`,
  `test_a_missing_rate_fails_loudly_and_trades_nothing`, RV0).
- **A crash between the cost write and the cash write cannot charge twice:** met. There is no
  separate cost write. The charges are fields of the trade's row, and its cash move is in the
  same save. If the save fails after the append, the ledger holds one charge and cash none. The
  re-run is skipped by the txn_id, so cash is never charged at all, let alone twice (story test,
  read against `execute_advice`). The retried manual add puts its charges into `capital_in` once
  (RV7).

### Rulings on the implementer's decisions

- **SA48-D1** (zero-brokerage broker; DP ₹15.34; a percentage broker by config): upheld.
- **SA48-D2** (STT to the rupee; stamp to the paisa): upheld. If stamp is in fact rounded to the
  rupee, the difference is at most ₹0.50 a buy.
- **SA48-D3** (an add's charges into `capital_in`): upheld. A real account pays them with fresh
  money, and the Nifty comparison treats them so.
- **SA48-D4** (SWITCH asks for net proceeds): upheld.
- **SA48-D5** (floor and caps after charges): upheld. My mutants did not repeat it; the
  implementer's `floor_before_fee` / `cap_before_fee` were read against the tests.
- **SA48-D6** (buy charges pooled, shared by the fraction sold): upheld. The rename edge is L2.
- **SA48-D7** (the law over the card's wording on a long-term loss): upheld. "0 when the year's
  net is a loss" holds except where the law taxes a short-term gain beside a larger long-term
  loss, and that case is pinned by a test.
- **SA48-D8** (gain at the ledger's average cost, FIFO dates): **upheld as the shipped method
  only with M1's correction of its stated effect.** It moves gain between short- and long-term
  within a year, not only between years, and can read low.
- **SA48-D9** (history not rewritten), **SA48-D11** (scorecard before costs): upheld.
- **SA48-D10** (no fallback rates): upheld, except the CSV import (L1).
- **SA48-D12** (FIX-021's reviewed bytes kept): moot after FIX-021's commit `e7e3165`. The
  input was re-recorded on that base before this review, and I verified it.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| M1 | medium (confirmed; law: s.45(2A) of the 1961 Act, CBDT Circular 768) | `core/portfolio/costs.py:354-358` (gain at `t.cost_basis`), `:359-372` (FIFO dates only) | 200 bought 2 Jun 2025 at ₹1,500 + 50 bought 13 Jul 2026 at ₹1,000, all sold 15 Jul 2026 at ₹1,400. The estimate is **₹0**: at the average of ₹1,400 every share gains 0. Lot by lot, long −₹20,000 and short +₹20,000; a long-term loss never offsets a short-term gain, so **₹4,160**. The mirror (₹1,000 long, ₹1,500 short) reads ₹3,120 where the law gives ₹0. Reproduced by `test_rv6_m1_*`. The KT states the method; SA48-D8 understated its effect. | Routed: [FIX-022](../stories/FIX-022.md) (lot-wise cost, fallback counted). Commit-time sentence in KT section 7 and the autopilot guide (exact text below). Not a sign-off blocker: outside the card's criteria, a labelled estimate never taken from cash. A mixed sale needs a lot more than 12 months old, and the production ledger was not read to see if one exists. |
| L1 | low (confirmed) | `core/portfolio/store.py:567-576` (`import_csv`) | With `portfolio.costs.stt_pct` removed, `import_csv` of two rows raises after `store.add_holding` saved the first: TCS held, `capital_in` unchanged, no ledger row (`test_rv4_reproduction_of_l1_the_half_import`). The same missing rate leaves a manual delete untouched (`test_rv4_manual_delete_…`). Needs a missing config key; `config.yaml` carries every key and a test pins them. | Routed: FIX-022 (read the rates before the lock). RV4's strict xfail turns into a pass when fixed. |
| L2 | low (confirmed, simulated rename) | `core/portfolio/costs.py` `sale_costs`, `tax_estimate` (pool and lots keyed by symbol); `core/portfolio/identity_reconcile.py:159-176` (successor written with no ledger row) | Manual add 100 OLDCO at ₹500 (charges ₹59.38). The holding is renamed NEWCO as `_successor_holding` does, then EXITed at ₹600 (₹77.58). Realized costs read ₹77.58 (not ₹137.00). `on_open_positions` reads ₹59.38 with nothing held. The sale counts "no purchase on record" (short-term). Totals reconcile. Reproduced by `test_rv5_…`. | Routed: FIX-022. |
| I1 | info (docs, confirmed) | `config.yaml` `portfolio.costs.exchange_fee_pct` comment | The comment says "IPFT ₹0.01/crore left out". NSE/FA/73061 gives ₹306.99 + ₹0.01 IPFT = ₹307 per crore, so 0.00307% includes IPFT. The rate is right. | Routed: FIX-022 (the comment's text is on the card). Not a commit-time edit: `config.yaml` is reviewed code bytes. |
| I2 | info (inference) | `trade_costs` (DP per SELL row) | CDSL charges DP per scrip per day. A manual delete and an autopilot sale of one scrip on one day would pay ₹15.34 twice. The executor sells a symbol at most once a run. | None. |
| I3 | info (design) | `/portfolio/performance`, `/portfolio/transactions` | A missing rate makes these endpoints answer 500, not only the tax figure (SA48-D10's fail-loudly rule). `config.yaml` is tracked and pinned by a test. | None. |

### Commands, environment and results

Windows 11, the project's `.stockai` virtual environment (Python 3.13), with `tests/hermetic.py`
active for every test: no network, no `.env` and no checkout data. The reviewer's folder has its
own `conftest.py` importing the same hooks. From the repository root:

- `.stockai/Scripts/python.exe analysis_data/sa048_review/rv_digest.py` and
  `scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-048-manifest.json`:
  above, at the start and the end.
- `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_trading_costs_sa048.py tests/unit/test_autopilot_api.py tests/unit/test_autopilot_executor_adds.py tests/unit/test_autopilot_executor_sells.py tests/unit/test_sizing_rule_sa050.py tests/unit/test_portfolio_vs_nifty_sa051.py`:
  **371 passed** (1m26s): the story file and the five changed test files.
- `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider analysis_data/sa048_review/test_rv_sa048.py`:
  **16 passed, 1 xfailed** (strict, L1). RV0 primary rates; RV1 charge oracle; RV2 the account
  above; RV3 set-off oracle, monotonicity and the 12-month line (5 cases); RV4 missing rate
  (delete writes nothing; CSV xfail; the L1 reproduction); RV5 rename (L2); RV6 M1 both ways;
  RV7 retried add.
- Reviewer mutants, in memory, no file edited (`-p rv_mutplug`, `run_mutants.sh`,
  `rv_mutants.txt`): **11 of 11 caught**. They are: a long-term loss offsetting a short-term
  gain, an uncapped exemption, 12 months as long-term, no cess, STT to the paisa, GST on STT, STT
  deductible, all buy charges on the first sale, a sale's charges not taken from cash, the old
  unrealized formula, and a manual add's capital without charges.
  - The first run's tally was wrong: the script's `*failed*` also matched "xfailed". Read
    correctly, 2 survived (12 months as long-term; all charges on the first sale). The 12-month
    boundary cases and RV2's check between the TRIM and the EXIT were added, and all 11 are
    caught.
  - The implementer's 32 mutants were not re-run. Their list was read against the tests.
- `node --test tests/frontend/no_invented_figures.test.mjs`: **24 of 24 passed** (3m26s),
  including SA-048's 2.
- `.stockai/Scripts/python.exe -m pytest -q -rs -x -p no:cacheprovider` (all of `tests`):
  **5,927 passed, 12 skipped, 1 xfailed, 0 failed** (17m50s, 17:29–17:47 IST).
  - It ran beside my own pytest runs (the reviewer cases and the mutants, in their own temporary
    directories), hence the time (13m17s at implementation).
  - No run failed. `git status` before and after the suite was identical.
- `scripts/ci/check_broad_except.py`: OK (151 grandfathered). `scripts/docs/check_kt_docs.py`:
  one error, the expected one: "KT links core/portfolio/costs.py, which is absent at its
  declared revision e7e316573f59". The commit-time header bump clears it.
- PDF: 62 pages, footer source `98c4d1f499d2` = SHA-256 of the reviewed KT.
- Public reads (read-only, no credentials, 31 Oct 17:30–17:45 IST):
  - NSE's circular PDF `archives.nseindia.com/content/circulars/FA73061.pdf`, fetched and
    extracted with pypdf (`-I`, the text treated as data);
  - two web searches (Income-tax Act 2025 s.196/s.198 on incometaxindia.gov.in; Budget 2026 STT);
  - one on s.45(2A) (CBDT Circular 768).

**Not exercised:** production. An actual `identity_reconcile apply` was not run (L2 simulates its
successor). Stamp-duty rounding, the SEBI fee notification, the CDSL tariff and the Finance Act
2026's STT schedule were not read in primary text.

### Acceptance checklist

- ACMESOLAR to the paisa from the configured rates → **met** (story test; RV1's oracle on both
  values; hand check: ₹225.57 and ₹250.85).
- Cash after a trade = before ± value − costs; equity reconciles → **met** (story property over
  150 accounts; RV2 at three points through the real API).
- Realized P&L exposes `gross` and `net_of_costs`; `realized_pnl` keeps its meaning → **met**.
- The tax estimate nets short-term gains and losses, applies the exemption once, and is 0 for a
  loss year → **met**, with SA48-D7's legal exception pinned. M1 is outside this criterion and
  routed.
- Every rate from config with an as-of date; a rate change never changes a recorded cost →
  **met** (story; RV0).
- A pre-SA-048 trade reads "costs estimated", never zero → **met** (story; screen test).
- Evidence: a hand fixture per charge, a round trip, a mixed year and a loss year; the property
  test; the endpoint on a fixture ledger → **met**.
- Living docs: KT sections 6, 7 and 12, the PDF, the autopilot guide, the UI spec, the product
  map, ARCHITECTURE, and guide cases 08-F and 07-F describe the reviewed behaviour → **met**,
  plus M1's commit-time sentences.

**Production verification:** `pending_deployment`. The commit and the push each need the
owner's word, in a job-free window (safest 00:10–06:20 IST), and never on the 1st before the 09:00
monthly forecast (1 Nov is tomorrow). After the deploy, guide 08-F on the first trading day with
a trade, read-only, counts and fields only:

- the trade row carries `costs` with `rates_as_of` 2026-10-31;
- cash moved by value ± and − costs;
- the screen shows realized P&L net of costs with the costs line, and the tax estimate.

**Commit-time edits** (with the commit, at the owner's word; none is made by this review):

- **Code commit:** exactly the 24 reviewed files. `kt_manifest.py verify SA-048-manifest.json
  --rev HEAD` must give 0 mismatches (`6e473449`).
- **Docs commit**, holding:
  - the KT header (`Code inspected` = that code commit; edition = the commit's date);
  - KT section 1's production paragraph. Replace "Production runs `4aa4c83` (FIX-019), deployed
    at about 09:31 IST on 31 October 2026 (the deployment list showed it SUCCESS and `/health`
    answered 200). The inspected code adds FIX-021's reading of Google redirect links (section
    4)." with "Production runs `c1d5b18` (FIX-021, code `e7e3165`), deployed at about 17:17 IST
    on 31 October 2026 (the deployment list showed it SUCCESS and `/health` answered 200). The
    inspected code adds SA-048's trading costs and tax estimate (sections 6 and 7)." The
    sentences after it stay. If another deploy came first, name that one;
  - **M1, KT section 7,** "Trading costs and the tax estimate". After "A sale with no purchase on
    record counts as short-term, the higher rate, and is counted." add: "The shares' cost is the
    position's average, while the law takes each lot's own cost, oldest first (section 45(2A) of
    the 1961 Act). So a sale that takes long-term and short-term shares bought at different
    prices can read higher or lower than the law's figure. 200 shares bought at ₹1,500 more than
    a year earlier and 50 at ₹1,000 a month earlier, all sold at ₹1,400, read ₹0 where the law
    gives ₹4,160. **Planned:** FIX-022 takes each lot at its own cost.";
  - KT section 12: the SA-048 row `Open` → `Done`. After the FIX-021 row add
    "| [FIX-022](planning/PI-2026-09/stories/FIX-022.md) | The tax estimate at each lot's own
    cost, and SA-048's loose ends | Open | 7 Marksheets | None |";
  - **M1, `docs/AUTOPILOT_GUIDE.md`.** In "The tax estimate" paragraph, after "STT is not
    deductible; the other charges are." add: "The shares' cost is the position's average, not
    each lot's own cost as the law takes it, so a sale that mixes long-term and short-term shares
    bought at different prices can read high or low (**Planned:** FIX-022)." In section 16
    (Planned work), after the SA-049 bullet, add "- The tax estimate at each lot's own cost
    (FIX-022).";
  - guide 08-F status: "**SA-048: implemented 2026-10-31; fresh review pending.**" →
    "**SA-048: accepted 2026-10-31, committed as `<code commit>`; production verification
    pending.**". Guide 07-F: "The costs in the figures: SA-048, implemented 2026-10-31; fresh
    review pending." → "The costs in the figures: SA-048, accepted 2026-10-31, committed as
    `<code commit>`.";
  - the PDF, rebuilt; `check_kt_docs` errors `[]`;
  - this receipt, the FIX-022 card, the PI README, STATE and HANDOFF, with the uncommitted
    FIX-021 push and deploy record.

**Committed** on 1 Nov 2026 at the owner's word: code `30bf8fc` (the 24 reviewed files, `verify
--rev HEAD` 0 mismatches) and a docs commit with the edits above. Not pushed at commit time;
the push waits for a job-free window.
