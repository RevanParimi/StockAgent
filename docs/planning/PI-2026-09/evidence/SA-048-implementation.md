# SA-048 — implementation receipt

**Story:** [SA-048](../stories/SA-048.md): charge realistic trading costs and tax in paper P&L.

**Phase:** implementation, 31 Oct 2026, about 15:03–16:20 IST. Session `stockagent-main-5c`
[539204], a new conversation opened with "continue". The eleven peers (`-5d`, `-f2`, `-4f`, `-8a`,
`-49`, `-f0`, `-39`, `-e0`, `-b4`, `-6e`, `-6b`) were idle at the start and before the bookkeeping
(ListAgents). This phase includes a same-conversation self-review, which is not the fresh review.

**Baseline:** HEAD `0fdaee6`. The working tree held FIX-021, accepted and uncommitted (reviewed
manifest `086378d8`, 9 files), its review receipt, PR-012's routed note, STATE and HANDOFF with the
uncommitted FIX-019 push and deploy record. All are kept.

**Status after this phase:** `review_required`. SA-048 is not committed, pushed, deployed or
configured. No production state was read and no message was sent. The rates were checked on the
web (sources below); no test touches the network.

## In one example

ACMESOLAR, the owner's screen of 27 Sep: 509 shares bought at ₹372.88 (₹1,89,795.92) and sold at
₹446.65 (₹2,27,344.85).

- **Before:** realized +₹37,548.93 and nothing else. Cash rose by the full ₹2,27,344.85.
- **Now:** the buy pays ₹225.57 (STT ₹190, stamp ₹28.47, NSE ₹5.83, SEBI ₹0.19, GST ₹1.08) and
  the sale ₹250.85 (STT ₹227, NSE ₹6.98, SEBI ₹0.23, GST ₹1.30, DP ₹15.34), each on its own ledger
  row and out of cash. Realized P&L reads +₹37,072.51 net of costs, with +₹37,548.93 before costs
  beside it. The tax estimate for FY 2026-27 is ₹7,797.82 (20% of a ₹37,489.51 gain, STT not
  deducted, plus 4% cess), shown and not taken from cash. About ₹29,275 is left in hand (the card
  estimated ₹29,660: it deducted STT and left out the cess).

## What changed

- **`config.yaml`:** `portfolio.costs` (as_of 2026-10-31: brokerage 0% with an optional per-order
  cap, STT 0.1%, stamp 0.015% on buys, NSE 0.00307%, SEBI 0.0001%, GST 18%, DP ₹15.34 per sale)
  and `portfolio.tax` (as_of 2026-10-31: short-term 20%, long-term 12.5%, exemption ₹1,25,000 a
  year, 12 months, cess 4%), each with its source in a comment.
- **`src/backend/shared/config/settings/base.py`:** `PORTFOLIO_COSTS`, `PORTFOLIO_TAX`, with no
  fallback rates.
- **`src/backend/shared/schemas/portfolio.py`:** `TradeCosts` (each charge, `total`, `rates_as_of`,
  `estimated`) and `TransactionRecord.costs` (optional, so every old row still parses).
- **`core/portfolio/costs.py` (new):** `trade_costs` (one trade's charges, `Decimal`, STT to the
  rupee per the STT Rules, the rest to the paisa, GST on the rounded parts); `costs_of` (recorded,
  or estimated and labelled for a pre-SA-048 BUY/SELL, none for a DIV); `sale_costs` and
  `cost_summary` (realized gross / costs / net, the sold shares' share of their position's buy
  charges, charged vs estimated vs carried by open positions); `tax_estimate` (per financial year,
  FIFO dates scaled through splits, set-off rules, exemption once, cess).
- **`core/portfolio/autopilot.py`:** every SELL and BUY computes its charges, takes them from cash
  and writes them on its row; a SWITCH asks for the proceeds net of the sale's charges; both buys
  size with the charges.
- **`core/portfolio/sizing.py`:** `size_buy(..., charge=)` re-checks the cash floor and both caps
  after the buy's charges, dropping a share at a time (without `charge` it is unchanged).
- **`services/api/routes/portfolio_api.py`:** manual add (capital_in += value + buy charges; the row
  carries them), manual delete (cash += value − sale charges), `/transactions` (old rows' costs
  estimated), `/performance` (`realized`, `costs`, `tax_estimate`; `realized_pnl` unchanged;
  unrealized P&L adds back charged costs so it stays the open holdings' price gain).
- **`core/portfolio/store.py`:** CSV import charges like a manual add.
- **`core/portfolio/pipeline.py`:** the trade alert says "realized ₹X before costs" and "costs ₹Y".
- **`src/frontend/prototypes/portfolio.jsx`:** "Realized P&L" shows net of costs with "+₹X before ₹Y
  of costs" (", partly estimated") under it; "Tax estimate" for the latest year with a sale; each
  trade shows "costs ₹N" or "costs ₹N (estimated)". A performance answer without `realized` shows
  the old figure.
- **Tests:** below. **Docs:** below.

## Callers checked

| Reader of the money figures | What it shows now | Checked by |
|---|---|---|
| Executor SELL/BUY (EXIT, TRIM, SWITCH, ADD) | charges on the row, out of cash | story file, executor files, SA-050 property |
| Manual add, manual delete, CSV import | add/import: charges into `capital_in`; delete: out of cash | API file (hand figures), story file, mutants |
| `/portfolio/transactions` | recorded costs, or estimated and labelled; none on a DIV | story file |
| `/portfolio/performance` | `realized_pnl` unchanged; `realized`, `costs`, `tax_estimate`; unrealized adds back charged costs | story file, API file |
| Reconciliation (`reconcile.py`) | replays `cash_after − cash_before`, so the charges are in it | portfolio reconcile file (unchanged, passes) |
| Nifty comparison (`capital_flows`) | a manual add's charges are money in | story file |
| Weekly scorecard (`closed_trades`, red flags) | before costs, as predeclared (SA48-D11) | unchanged; KT says so |
| Trade alert (`pipeline.py`) | "realized ₹X before costs; costs ₹Y" | story file (pipeline end to end), mutant |
| Brief (`brief.py`) | quotes a sale's `pnl_pct`, a percentage before costs | code inspection; unchanged |
| Portfolio screen | realized net with gross and costs; tax estimate; costs per trade | browser tests (2 new) |

## Tests

- **Story file** `tests/unit/test_trading_costs_sa048.py`, 22 passed. Every figure is worked by
  hand in the docstrings from the checked rates, which the test pins and compares with
  `config.yaml` itself.
  - Each charge on the ACMESOLAR buy and sale; a capped percentage broker (GST on brokerage); STT
    rounding of value and tax.
  - The ACMESOLAR round trip through the app: manual add, autopilot EXIT, `/performance` (gross
    37,548.93, costs 476.42, net 37,072.51 = equity − capital_in, unrealized 0, tax 7,797.82).
  - A SWITCH spending the net proceeds and paying the buy's charges; SA-050's ₹2.27 L switch
    through the real pipeline on these rates (₹250.84 and ₹118.68, the note, cash ₹3,99,990.48,
    both alerts).
  - Config carries every rate with its date; a missing rate trades nothing; a rate change never
    changes a recorded trade (old rows re-estimate, labelled); a crash after the ledger write and a
    re-run charge once, cash never twice.
  - A pre-SA-048 trade reads estimated (₹15.35), a DIV has none, the ledger is not rewritten, and
    unrealized P&L is unchanged for old ledgers.
  - Buy charges following the shares through a TRIM and a 2:1 split.
  - Tax: a mixed year (exemption once: ₹22,438), a loss year (₹0), a long-term loss beside a
    short-term gain (₹208), April-March and exactly 12 months, oldest shares first across two years
    with a split (₹156 and ₹156), no purchase on record (short-term, counted).
  - A manual add's charges as money in the Nifty flow.
  - Property: 150 seeded accounts over 2-6 sessions of random ADD/TRIM/EXIT/HOLD through the real
    executor: each row's cash arithmetic, costs ≥ 0 and = their parts, a ledger replay, equity −
    capital_in = realized + unrealized − charged, and charges on sales + charges on open positions =
    every charge.
- **Existing tests that pinned cost-free arithmetic** (the story changes it on purpose):
  - `test_autopilot_api.py` (4) and `test_autopilot_executor_sells.py` (1): expected cash and
    capital now include the charges, each worked by hand in a comment (₹1.11, ₹16.39, ₹16.39,
    ₹7.12; ₹16.38).
  - `test_autopilot_executor_adds.py` (2 changed, 1 new): the cash floor now holds after charges.
    The two tests get exactly the charges more cash (₹0.02, ₹2.37) and still buy 1 and 20 shares
    to the floor; the new test shows ₹100 above the floor no longer buys a ₹100 share.
  - `test_sizing_rule_sa050.py`: its hand-worked examples run before costs (zero rates, said in the
    file); its random-portfolio property test now runs on the configured rates and also checks
    that equity falls by exactly the run's charges and every trade's charges are positive (caps
    and floor checked after them).
  - `test_portfolio_vs_nifty_sa051.py`: its Nifty-method figures run before costs (zero rates, said
    in the fixture); the story file covers a manual add's charges in the flow.
- **Browser** `tests/frontend/no_invented_figures.test.mjs`: 2 new (realized after costs with the
  gain before them, "partly estimated", the tax estimate, a trade's costs and "(estimated)"; an old
  performance answer shows its realized P&L and no tax); file 24 of 24 passed.
- **Mutants** (`analysis_data/sa048/mutants.py`, in place, restored after each; sha256 of the 6
  code files and the story file checked after the run): **32 of 32 caught** on the final bytes.
  Charges (STT not to the rupee, stamp or DP on the wrong side, GST on STT, no brokerage cap,
  old rows free, STT deductible), allocation (all buy charges on the first sale), tax (a
  negative long-term net kept, a long-term loss offsetting a short-term gain, a short-term loss
  kept short, no or an unbounded exemption, 12 months as long, no split scaling, newest shares
  first, no cess, calendar years, a missing rate as zero), executor (sale or buy charge not from
  cash, gross SWITCH proceeds, a row without costs), sizing (no charge, floor or cap before the
  charge), API (manual add capital or delete without costs, the old unrealized formula, old rows
  not estimated), the alert without costs and CSV capital without costs. A first pass on earlier
  test bytes caught 28 of 30: a negative long-term net leaked into `long_term_exemption_used`, and
  newest-first lots gave the same year totals when both sales fell in one year. The tests were
  strengthened (and the real legal error, a long-term loss offsetting a short-term gain, added as
  its own mutant) before the second pass.
- **Neighbouring files** (35 portfolio, scorecard, sizing, Nifty, corporate-action, reconcile,
  locking and UI-guard files, and the story file): 1,000 passed.
- **Full suite:** 5,927 passed / 12 skipped / 1 xfailed / 0 failed (13m17s, 16:02–16:15 IST; the previous 5,904 plus this story's 23), on the final code and test bytes. No tracked runtime file changed (`git status`). Output: `analysis_data/sa048/full_suite.txt`.
- **Checks:** `check_broad_except` OK (151 grandfathered); `check_kt_docs`: the one expected error
  below; PDF 62 pages.

## Decisions (implementer's, recorded for the review)

- **SA48-D1, the broker:** a zero-brokerage delivery broker (Zerodha's published charges, checked
  31 Oct): brokerage 0, DP ₹15.34 per scrip sold (₹3.5 CDSL + ₹9.5 broker + GST). A percentage
  broker is one config edit (`brokerage_pct`, `brokerage_max_inr`), tested.
- **SA48-D2, rounding:** STT's value and tax to the nearest rupee (Securities Transaction Tax
  Rules 2004, rule 4); every other charge to the paisa, half up, and GST on the rounded parts, as
  contract notes show. A forum claim that stamp duty is also rounded to the rupee was not
  confirmed by a primary source, so stamp stays at the paisa.
- **SA48-D3, a manual add or CSV import:** it moves no cash, so its buy charges are fresh capital
  with its cost (`capital_in` += value + charges). Equity − capital_in then reads −charges at
  once, like a real account, and the Nifty comparison takes the charges in as money (the card
  named the manual add path; leaving them out would make realized net and total P&L disagree).
- **SA48-D4, the SWITCH asks for the net proceeds,** the cash the sale actually released.
- **SA48-D5, sizing after charges:** without it a buy sized to the cash floor ends up to ~0.12%
  of its value below the floor, and one sized to the 10% cap a few rupees over 10% of the
  charge-reduced equity. Each check is needed: the mutant `floor_before_fee` is caught by the ADD
  floor test and `cap_before_fee` by SA-050's property test on the configured rates.
- **SA48-D6, buy charges follow the shares:** a position's buy charges are pooled; a sale takes
  the share of the pool its shares are of the position (sold ÷ held before the sale, so a split
  changes nothing). Read from the ledger, not stored on the holding: no new holding field, and
  identity reconciliation and corporate actions need no change.
- **SA48-D7, tax law over the card's wording:** a long-term loss sets off only against long-term
  gains (and a short-term loss against either), as the Income-tax Act has it. So the card's "0
  when the year's net is a loss" holds except when a long-term loss exceeds a short-term gain; the
  test `test_a_long_term_loss_never_offsets_a_short_term_gain` pins that case (₹208 on a year that
  nets to −₹4,000). Loss carry-forward, surcharge and the basic-exemption shortfall are not
  modelled (stated in config, the KT and the guide). STT is not deductible (section 48); the other
  charges are. The 4% cess is included.
- **SA48-D8, the gain's cost is the ledger's `cost_basis`** (the position's adjusted average), as
  realized P&L uses; only the long/short split follows FIFO purchase dates. Indian tax uses each
  lot's own cost (FIFO), which can move gain between years when part of a multi-lot position is
  sold at different purchase prices; the total over a closed position is the same. A sale with no
  purchase on record counts as short-term (the higher rate) and is counted; one with no cost basis
  falls back to its realized P&L and is counted.
- **SA48-D9, history is not rewritten:** a pre-SA-048 row keeps no `costs`; it is estimated when
  read at today's rates, labelled `estimated`, and listed apart because it was never taken from
  cash. Unrealized P&L adds back only charged costs.
- **SA48-D10, no fallback rates:** a missing rate raises in `trade_costs`/`tax_estimate`, so a
  trade is refused rather than charged nothing (tested: nothing written).
- **SA48-D11, the weekly scorecard stays before costs:** its red-flag rules were predeclared on
  gross results (PR-002); the KT now says so beside it, and the screen's realized P&L is net.
- **SA48-D12, FIX-021's reviewed bytes are kept.** The KT, the guide and the PDF are in FIX-021's
  accepted, uncommitted manifest. Before any edit, all 9 of its files were copied to
  `analysis_data/sa048/start/` (`start.py`; `kt_manifest.py verify` of `086378d8`: 0 mismatches
  at the start). FIX-021's commit takes those three from that copy.

## Rate sources (checked 31 Oct 2026)

| Rate | Source read | Primary source |
|---|---|---|
| STT 0.1% buy and sell, delivery; Budget 2026 raised only F&O STT | broker and news summaries of Budget 2026 (Groww, ICICI Direct, Angel One) | Finance Act 2026 schedule: not read |
| STT rounding to the rupee | incometaxindia.gov.in, Securities Transaction Tax Rules 2004, rule 4 (quoted in search results) | the rule, via the search result |
| NSE 0.00307% each side from 1 Mar 2026 | zerodha.com/charges (fetched: "NSE: 0.00307%"); Angel One 0.0030699%; Upstox | NSE circular NSE/FA/73061, 27 Feb 2026: the PDF timed out twice and was not read |
| IPFT ₹0.01 per crore | zerodha.com/charges | the same circular; left out as immaterial (₹0.01 per ₹1 crore) |
| SEBI ₹10 per crore; GST 18% on brokerage + NSE + SEBI | zerodha.com/charges | SEBI fee notification: not read |
| Stamp 0.015% buy side | zerodha.com/charges ("0.015% or ₹1500 / crore on buy side") | Indian Stamp Act amendment (Finance Act 2019, from 1 Jul 2020): not read |
| DP ₹15.34 per scrip sold | zerodha.com/charges (₹3.5 CDSL + ₹9.5 Zerodha + ₹2.34 GST) | CDSL tariff: not read |
| STCG 20%, LTCG 12.5% above ₹1,25,000, >12 months | tax commentary (taxguru, Bajaj Finserv on s112A) | Finance (No. 2) Act 2024 / Income-tax Act 2025: section numbers in the 2025 Act not confirmed |

The card's hard review asks for primary sources, dated: the reviewer should read NSE/FA/73061 and
the Finance Act text. The rates are config, so a correction is one edit and a new `as_of`;
recorded trades keep the rates they were charged at.

## Docs

- **KT (`docs/TECHNICAL_DESIGN.md`):** section 6, execution (charges on the trade's row, one ID)
  and sizing (equity less costs, the SWITCH's net proceeds, every limit after the buy's charges,
  the ₹2.27 L switch example with its costs); section 7, Virtual P/L (the table's realized, costs
  and tax rows; "Trading costs and the tax estimate" with the rate table, rounding, history,
  realized net, the tax rules and the ACMESOLAR example; the screen's realized and tax stats and
  per-trade costs; the closing caveat now names spread and slippage), the report families' scorecard
  row, and in-kind arrivals (charges are money in); section 11's SA-048 bullet removed; section
  12's SA-048 row stays `Open` until the review. The PDF was rebuilt: 62 pages (was 61), no
  overflow, source `ea8702f5`.
- **`docs/AUTOPILOT_GUIDE.md`:** the SWITCH row, the sizing rule and its switch example, the
  portfolio figures (`capital_in`), a trading-costs and tax-estimate section with the ACMESOLAR
  example (replacing "What the figures leave out"), the ledger's `costs` field, the four API rows,
  and the planned list.
- **`docs/TEAM_TESTING_GUIDE.md`:** case 08-F rewritten as a runnable check with the hand figures
  and both tax edge years; case 07-F's figures now include the costs (status line says so).
- **`src/frontend/prototypes/UI_SPEC.md`:** the hero stats, the activity text and both endpoints.
- **`docs/PRODUCT_MAP.md`:** a `costs.py` row; the sizing row says "after the trade and its costs".
- **`docs/ARCHITECTURE.md`:** the planned "Portfolio economics" bullet now names only idle cash
  (SA-048 here; SA-050 and SA-051 are Done in KT section 12 and were still listed).
- **`check_kt_docs`:** exactly one error, "KT links core/portfolio/costs.py, which is absent at its
  declared revision 4aa4c837ce89". Expected: the header names a commit without the new file, and
  the commit-time header bump clears it, as with PR-006's jobs and PR-009's `exit_shadow.py`.

## Review input

- **Manifest:** [SA-048-manifest.json](SA-048-manifest.json)
  `6e473449ae38daada2bd7ce9285943ba281bbc69fcfb1f88835f0941ec1c0346` (24 files: 10 code and config files, 7 test files, the KT, the PDF and 5 other docs),
  `kt_manifest.py verify` 0 mismatches.
- **Diff:** `ed6d086b552c19e455174dc3098cd6246c34fa064d2cb086446da97153e74034` (143,587 B, 23 paths), from `analysis_data/sa048/digest.py`: every path
  against HEAD, FIX-021's docs commit on `e7e3165`; the two new files against `/dev/null`.
- **Re-recorded on 31 Oct, about 17:05 IST, after FIX-021 was committed** (at the owner's "commit
  and push"), before any review. It supersedes `3a4ea0e9` / `e867d409` (16:00 IST), whose KT,
  guide and PDF sat on FIX-021's then-uncommitted reviewed copies. Code and test bytes are the same
  in both. SA-048's KT and guide lines were put back on top of FIX-021's docs commit line for line
  (`analysis_data/sa048/compare_lines.py`: KT 98 added and 25 removed, guide 2 and 2, equal before
  and after); the PDF was rebuilt (62 pages, source `98c4d1f4`); `check_kt_docs` gives the one
  expected error, now "absent at its declared revision e7e316573f59".

## Commit (after the fresh review accepts it, only at the owner's word)

FIX-021 was committed first (`e7e3165` and its docs commit; "Review input" above). After
SA-048's acceptance: the reviewed files, then a docs commit (KT header, section 12 Done, guide
08-F and 07-F status, PDF). A push deploys it: in a job-free window, never on the 1st before the
09:00 monthly forecast.

## For the fresh review (the card's hard-review questions)

- **Rates against a primary source, dated:** table above; two primary documents were not read
  (the NSE circular timed out, the Finance Act was not fetched). No rate is hard-coded:
  `test_config_carries_every_rate_with_its_check_date` reads `config.yaml` itself, and
  `test_a_missing_rate_fails_loudly_and_trades_nothing` shows no rate means no trade.
- **A crash between the cost write and the cash write cannot charge twice:** there is no separate
  cost write; the charges are fields of the trade's row and the cash change is in the same
  portfolio save. `test_a_crash_after_the_ledger_write_never_charges_twice` fails the save after
  the append, re-runs the day, and finds one recorded charge and cash never charged.
- **Independent invariants:** the per-charge and round-trip figures are hand-worked in the test
  docstrings; the property test checks each row's cash arithmetic, a ledger replay, and equity −
  capital_in = realized + unrealized − charged with its own arithmetic.

## Rollout and rollback

Additive: new optional ledger field, new response fields, `realized_pnl` unchanged. From the
deploy on, every trade pays its charges and every P&L reads a little lower. Rows already written
read with estimated costs, labelled. Rollback is a revert; rows written meanwhile keep their
`costs` (the old code ignores the field) and their lower cash.

## Production verification (separate, after the deploy)

Guide case 08-F on the first trading day with a trade: the trade row carries `costs` with
`rates_as_of` 2026-10-31, cash moved by value ± and − costs, and the screen shows realized net,
the costs line and the tax estimate. Read-only, counts and fields only.
