# SA-050 — implementation receipt

**Story:** [SA-050](../stories/SA-050.md): one sizing rule for every autopilot buy.
**Phase:** implementation, 18 Oct 2026, about 15:25–16:35 IST. Session
stockagent-main-e7, a new conversation opened with "continue"; all 17 peers
were idle at the start. **Baseline:** `85e447b1a4e60ac8b3cd4feb530962ca2c0cc5d4`
(HEAD, clean for every payload path). **Status after this phase:**
`review_required`. Nothing was committed, pushed or deployed. No production
state was read, and no message was sent.

## In one example

The production shape of 11 Oct (product review section 11): FEDERALBNK 406 at
₹330 (₹1,33,980), WELCORP 21 at ₹2,640.40 (₹55,448.40), and ₹8,09,297 cash.

- **Before.** The advisor divided by the holdings' cost (₹1,97,934), so
  FEDERALBNK read 72.9% and WELCORP 27.1%. Both were over the 10% ADD limit,
  so neither could ADD. FEDERALBNK also carried `SECTOR_CONCENTRATION_HIGH` in
  a portfolio that was 81% cash.
- **Now.** Both are measured against total equity, ₹9,98,725.40.
  - FEDERALBNK is 13.4%: `POSITION_LARGE`, and no ADD.
  - WELCORP is 5.6%. A bullish, healthy WELCORP may ADD: its 25% tranche
    (₹13,862) buys 5 shares.
  - Banking is 13.4% of equity, so there is no sector note.

**The ₹2.27 L switch.** A ₹10 L portfolio sells a ₹2,27,000 holding for a
shelf idea priced at ₹530, inside its band of ₹500–₹540.

- **Before:** the whole proceeds bought 428 shares, 22.7% of the portfolio.
- **Now:** the position may be at most ₹1,00,000, so 188 shares (₹99,640). The
  BUY's note reads:

```text
switch from ACMESOLAR; capped by the 10% position cap: ₹1,27,360 of the ₹2,27,000 proceeds stay in cash
```

**WELCORP on 1 Sep.** It was shelved with the band ₹1,817–₹1,911, then a
SWITCH bought it at ₹2,553.60. Now that buy is skipped. The SELL says why, and
the `switch_buy_skipped` alert repeats it:

```text
exit_full; buy leg skipped: WELCORP: 33.6% above entry band (₹1,817–₹1,911); needs a fresh deep dive; ₹1,00,000 stays in cash
```

## What changed

- **New `core/portfolio/sizing.py`** (pure, about 190 lines):
  - `weights()`: each holding's and each sector's share of total equity.
    Equity is every holding at its mark (at adjusted cost without one) plus
    cash.
  - `size_buy()`: one buy's whole shares. It takes the smallest of the amount
    asked for, the position's room under `advisor.max_position_pct`, the
    sector's room under `advisor.max_sector_pct`, and cash above the floor.
    A cash buy leaves equity unchanged, so each room is `cap × equity − value`.
  - `entry_check()`: a new position is allowed at or below `entry_high` and
    above `invalidation_level`. Below `entry_low` it is allowed with a
    "cheaper than planned" note. No idea, or no band, is refused.
  - Note helpers in Indian rupee grouping.
- **Autopilot** (`core/portfolio/autopilot.py`):
  - the ADD and SWITCH buy legs both call `size_buy`;
  - a SWITCH buy calls `entry_check` against `shelf_index`, a new optional
    argument of `execute_advice`;
  - a BUY limited by a cap or the floor says so in its note;
  - every skipped SWITCH buy leg writes its reason on its SELL's note:
    unpriceable, stale close (enforce), identity (enforce), band, under one
    share after the caps, or dedupe. `switch_skip_reason()` reads it back;
  - `_portfolio_market_value` and the old ADD headroom formula are deleted.
- **Advisor** (`core/portfolio/advisor.py`):
  - `build_signals(..., marks=)` sets `position_weight_pct` and a new
    `sector_weight_pct`, both unrounded shares of total equity;
  - `decide` keeps the ADD test (position below 10%);
  - the note splits in two: `POSITION_LARGE` (position over 10%) and
    `SECTOR_CONCENTRATION_HIGH` (sector over 30%).
- **Pipeline** (`core/portfolio/pipeline.py`):
  - fetches every holding's close first, then computes the weights and the
    SWITCH sector map from them. It divided by cost before, inside a silent
    `except Exception: pass`; that swallow is gone, and its
    `scripts/ci/broad_except_baseline.txt` entry is removed;
  - passes `marks` to the advisor and the active shelf ideas to the autopilot;
  - the `switch_buy_skipped` alert carries the SELL note's reason.
- **Narrator:** plain text for `POSITION_LARGE`; new text for
  `SECTOR_CONCENTRATION_HIGH`.
- **Weekly review** (`core/delivery/weekly.py`, `weekly-view.jsx`):
  - allocation and a new `cash_pct` are shares of total equity;
  - flags mark sectors over the sector cap, from exact shares;
  - stored figures are rounded once, to one decimal;
  - the text and the screen gain a cash line, and the headline prompt sees
    cash.
- **Config:** `advisor.max_sector_pct: 30.0` replaces
  `advisor.sector_concentration_warn_pct: 30.0` (settings
  `ADVISOR_MAX_SECTOR_PCT`).
- **Existing tests:** fixtures changed, no assertion changed.
  - Four SWITCH tests (`test_autopilot_executor_switch`,
    `test_autopilot_isolation`, SA-003's switch-leg test, SA-008's unresolved
    destination) now pass a shelf idea whose band contains the price.
    Without one, the destination is rightly refused.
  - SA-003's chain puts BIGCO in its own sector. In automobile, the sector is
    51% of equity, and the new cap, not the data gate, would stop the ADD the
    test is about.
  - `test_add_respects_position_weight_cap` puts MARUTI at 10% of equity. It
    was 10% of the holdings but 3.3% of equity.
  - `test_portfolio_settings` uses the renamed key.

## Design decisions (delegated, recorded)

- **D1. One pure module.** `sizing.py` is called by the advisor, the pipeline,
  the autopilot and the weekly review. Four separate computations are
  deleted:
  - the advisor's cost weight;
  - the pipeline's cost sector map;
  - the autopilot's holdings-only market value and its headroom formula;
  - the weekly's holdings-only allocation.

  SA-049 will reuse `size_buy` and `entry_check` for new positions.
- **D2. Config key `advisor.max_sector_pct`.** The card proposed
  `autopilot.max_sector_pct`. The sector cap sits next to
  `advisor.max_position_pct` because the advisor's note, the weekly flag and
  the autopilot's cap all read it. It replaces
  `advisor.sector_concentration_warn_pct` at the same 30, so one number cannot
  drift from another. No environment variable read the old key.
- **D3. Room is `cap × equity − value`.** The old ADD formula,
  `(pos + X) / (total + X) ≤ cap`, assumed the denominator grows with the buy.
  That holds only when cash is excluded. With cash in equity, a buy moves
  money from cash into the holding, and equity is unchanged.
  - **Example:** MARUTI is 9,000 of 1,00,000 and the tranche is 2,250. The
    room is 10,000 − 9,000 = 1,000, which buys 10 shares, and MARUTI ends at
    exactly 10%.
- **D4. Ties.** When two limits are equal, the request wins, then the
  position cap, the sector cap and the floor.
  - **Example:** ₹1,00,000 of proceeds against exactly ₹1,00,000 of position
    room gives a plain note.
- **D5. "Over" is strict.** The caps allow a weight up to and including the
  cap, so exactly 10% (or 30%) carries no note. ADD still needs a weight below
  10%, as before.
- **D6. An unpriced holding is valued at adjusted cost,** as in the value
  history.
- **D7. Where a skip is recorded.**
  - A skipped SWITCH buy leg writes its reason on the SELL's note. The ledger
    is the audit authority, and the activity list shows notes. The alert
    repeats the reason.
  - An ADD that the rule cuts to under one share has no transaction, so its
    reason is logged, like every other ADD skip today. A durable "every
    non-buy says why" record is SA-049's (see L1).
- **D8. Which buys the entry rule covers.**
  - The rule applies to the SWITCH buy, which opens a position.
  - An ADD tops up a stock already held and is not judged against an old
    shelf band.
  - A destination with no shelf idea, or with `entry_high` 0, is refused.
  - Invalidation is strict: a price equal to `invalidation_level` is refused.
- **D9. Sector labels match exactly.** They are lowercase registry keys,
  validated at entry. `generic` counts as one sector (see L2).
- **D10. The SWITCH underweight test reads market shares of equity.** It
  read cost shares of the holdings. The comparison is relative, so only cost
  versus market matters.
  - **Example** (a test): ACMESOLAR bought for ₹1,00,000 is now ₹50,000, and
    PHARMACO is ₹60,000. Pharma is not underweight at market, so the advisor
    exits without buying more pharma. At cost it would have switched.
- **D11. The weekly review uses equity shares.**
  - Allocation and cash are shares of total equity.
  - Flags read exact shares.
  - Stored figures are rounded once, to one decimal. Rounding twice showed
    5.552% as "5.5%"; the browser test found it.
- **D12. Advisor weights are unrounded,** so the notes compare exactly what
  the caps compare. They were rounded to 2 decimals.
- **D13. Every pre-existing SWITCH skip path writes a reason** (unpriceable,
  stale close, identity, dedupe). So the alert is specific in every case,
  not only for the band and the caps.
- **D14. The pipeline prices every holding before advising any.** Equity
  weights need all the marks. A holding without a close is not advised, as
  before, and counts at cost in the others' weights.

## Invariant tests

`tests/unit/test_sizing_rule_sa050.py`, 30 tests (22 functions, some parametrized). Every expected figure is
worked by hand in its docstring from the fixture's numbers; nothing asks
`sizing.py` for the answer.

| Test | Pins |
|---|---|
| `test_the_227k_switch_buys_at_most_the_10pct_position` | Card acceptance 1: 188 shares, cash 4,00,360, the capped note; the old rule bought 428 |
| `test_a_buy_that_would_push_its_sector_over_the_cap_is_reduced` | Card acceptance 2: 125 shares, banking exactly 3,00,000 (30.0%) |
| `test_a_sector_buy_under_one_share_is_skipped_and_the_sell_says_why` | Under one share after the sector cap: no BUY, the SELL's note, proceeds in cash |
| `test_an_add_into_a_full_sector_is_skipped_and_logged` | ADD with position room but a full sector: no transaction, the logged reason |
| `test_the_cash_floor_is_kept`, `test_under_one_share_after_the_floor_is_skipped` | The floor binds (3 shares, cash ends at 10,000); under one share skips |
| `test_add_keeps_todays_behaviour_when_no_cap_binds` | Card acceptance 3, characterization: 25 shares, note `add_tranche` |
| `test_an_add_is_trimmed_to_the_position_cap_and_says_so` | ADD cut to exactly 10%, with its note |
| `test_oct11_weights_are_shares_of_total_equity_and_unlock_add` | Card addition: 13.4% and 5.6% (exact fractions); WELCORP ADD; FEDERALBNK HOLD with only `POSITION_LARGE` |
| `test_oct11_welcorp_add_executes_through_the_shared_rule` | WELCORP's ADD buys 5 shares |
| `test_the_welcorp_switch_34pct_above_its_band_is_not_bought` | Card addition: skipped, the reason and the ₹1,00,000 in cash on the SELL |
| `test_entry_check_against_the_band` (6 cases), `test_a_destination_without_a_band_is_refused`, `test_a_below_band_buy_says_it_was_cheaper_than_planned`, `test_a_destination_missing_from_the_shelf_is_not_bought` | The band's edges: top and bottom allowed, 0.03% above refused, below with a note, invalidation refused at and under |
| `test_property_random_portfolios_never_breach_caps_floor_or_band` | Card property tests: 300 seeded portfolios and advice days, checked with the test's own arithmetic. No bought symbol over 10%, no sector over 30%, the floor kept, every new position inside its band, and equity conserved by the run. Counters prove each case was exercised |
| `test_pipeline_switch_is_capped_end_to_end` (record and enforce) | Card integration: real advisor, pipeline and autopilot. SWITCH chosen, 188 shares, the note; `POSITION_LARGE` and `SECTOR_CONCENTRATION_HIGH` from equity weights |
| `test_pipeline_weights_use_every_holdings_close` | SMALL is 10.4% only when BIG is marked at its close (at cost it would read 9.45%) |
| `test_the_switch_underweight_test_reads_market_shares` | D10 |
| `test_the_notes_mark_weights_over_the_caps` (3 cases) | D5's boundary |
| `test_pipeline_switch_above_band_alerts_with_the_reason` | The `switch_buy_skipped` alert's exact message |
| `test_weekly_allocation_is_a_share_of_total_equity` | 13.4, 5.6, cash 81.0, nothing flagged, the text's cash line |

Browser test (`tests/frontend/no_invented_figures.test.mjs`): the weekly
allocation fold shows each sector and the cash share. A review stored before
the change shows no cash row. Against HEAD's `weekly-view.jsx` (copied to
`analysis_data/sa050/fe_base`) the test **fails** (no cash row), as intended.

**Mutants** (`analysis_data/sa050/sa050_mutants.py`, each a one-line reversion,
run against the story file, the ADD tests and the weekly tests):
**21 of 21 caught**, and every mutated file was restored byte for byte.

| Area | Mutants |
|---|---|
| The rule | equity without cash; no sector cap; no position cap; no floor; request ignored |
| The band | above band allowed; invalidation boundary `<`; below-band note dropped |
| Autopilot | switch skips the band check; band skip not on the SELL; cap skip not on the SELL; capped note dropped |
| Advisor | other holdings' marks ignored; `POSITION_LARGE` at the cap; sector note read from the position weight (the old bug) |
| Pipeline | marks not passed; shelf ideas not passed; alert drops the reason; SWITCH sector map at cost |
| Weekly | cash excluded; rounded twice |

## Commands and environment

Windows 11, the repository's `.stockai` venv (Python 3.13), Node with the
vendored Playwright Chromium. Hermetic boundary on (SA-005): no `.env`, no
network, no checkout data.

| Command (repository root) | Result |
|---|---|
| the 15 affected existing files (`test_autopilot_executor_*`, `test_autopilot_isolation`, `test_autopilot_pipeline`, `test_autopilot_wave1`, `test_decision_gate_portfolio_sa003`, `test_delivery_weekly`, `test_identity_portfolio_sa008`, `test_portfolio_pipeline`, `test_portfolio_settings`, `test_txn_transparency`, `test_portfolio_advisor`, `test_scheduler_portfolio_hook`, `test_portfolio_api`) at HEAD, before any change | 150 passed |
| the same after the code change, before the fixture updates | 8 failed, 142 passed: the 8 expected (above) |
| `PYTHONPATH="src;." .stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_sizing_rule_sa050.py` | **30 passed** |
| the story file plus the 15 files above | **180 passed** |
| `PYTHONPATH="src;." .stockai/Scripts/python.exe analysis_data/sa050/sa050_mutants.py` | **21 of 21 caught**; every mutated file restored byte for byte (`sha256sum -c`) |
| `npm run test:frontend` | **35/35** (was 34; the new weekly test) |
| the new browser test (`node --test --test-name-pattern="weekly allocation"`) with `SA_FRONTEND_ROOT` = the current prototypes with HEAD's `weekly-view.jsx` | **fails** (no cash row), as intended |
| `.stockai/Scripts/python.exe -m pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,037 passed, 12 skipped, 1 xfailed (the known PR-003 limit), 0 failed** in 9 min 52 s |
| `python scripts/ci/check_broad_except.py` | first run: 1 stale baseline entry, `pipeline.py run_post_review_pipeline #0`. That was the cost-weight block's silent `except Exception: pass`, which this story deletes. `--update` removed exactly that line; then **OK (151 grandfathered**, was 152) |
| `python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 46 pages (was 45), source `5912d699…`; errors `[]` |

Raw outputs (ignored): `analysis_data/sa050/full_suite.txt`, `mutants.log`,
`npm_frontend.txt`, `npm_frontend_head_screen.txt`, `fe_base/`, and the
helper scripts (`splice_start.py`, `update_existing_tests.py`,
`precision_tests.py`, `guide_cases.py`, `doc_edits.py`, `digest.py`,
`final_runs.sh`).

## Documentation

Each change is written as current design.

- **KT** (`docs/TECHNICAL_DESIGN.md`), section 6:
  - "Advisor precedence": ADD needs the holding below 10% of total equity.
  - "Execution and persistence": the SWITCH buy leg's three checks, and the
    skip reason on the SELL and in the alert.
  - New "Sizing every buy": the denominator, the four limits, the band, the
    two notes, the weekly view, and two worked examples (11 Oct and the
    switch).
  - "Cash deployment": its Planned pointer names SA-049 only.
  - Section 11's "Portfolio economics" drops the SA-050 bullet.
  - Section 12's SA-050 row stays `Open` until the fresh review accepts it.
  - `sizing.py` is named in code text, not linked: `check_kt_docs` requires a
    linked file to exist at the declared revision `b6d2470`. The link is a
    commit-time edit.
- **PDF** rebuilt: 46 pages (was 45), source SHA-256 `5912d699…`.
  `check_kt_docs` reports `[]`.
- **AUTOPILOT_GUIDE:**
  - section 3: position and sector weight rows, the ADD row, the SWITCH
    underweight test, the notes;
  - section 6: the ADD and SWITCH rows, the buy leg's three checks, the
    shared rule with a worked example (it replaces the old headroom formula);
  - section 7: cash deployment and its example;
  - section 13: the two cap keys (the old key removed);
  - section 14: the new test file;
  - section 16: SA-050 removed.
  - Its header (edition, inspected revision) is a commit-time edit.
- **README** (the note table and the ADD row), **CODEBASE** (the two settings
  rows, the advisor and autopilot rows, a new `sizing.py` row) and
  **PRODUCT_MAP** (a new Sizing row).
- **Human testing guide** (HT-07):
  - 07-F is rewritten as a concrete fixture with exact figures;
  - new 07-I: the band at three prices;
  - new 07-J: the 11 Oct shape, the advice and the weekly view.

  Each status line reads "SA-050: implemented, awaiting its fresh review; not
  deployed".
- No change needed:
  - ARCHITECTURE: it does not describe sizing;
  - `tests/TEST_DOCUMENTATION.md`: general;
  - the SA-049 and SA-051 cards already name SA-050's rule.

## Manifest and digest

- **Review input:** [SA-050-manifest.json](SA-050-manifest.json), 25 files. The SHA-256 of
  its LF bytes is **`d2c13ba8780cc7caf5ad0bfc652dec761d5cbe3a01a60d56f61e020c74903a13`**;
  `kt_manifest.py verify` gives 0 mismatches.
  - Code (10): `config.yaml`, `core/delivery/weekly.py`, `core/portfolio/advisor.py`,
    `core/portfolio/autopilot.py`, `core/portfolio/narrator.py`, `core/portfolio/pipeline.py`,
    `core/portfolio/sizing.py` (new), `scripts/ci/broad_except_baseline.txt`,
    `src/backend/shared/config/settings/base.py`, `src/frontend/prototypes/weekly-view.jsx`.
  - Tests (8): `tests/unit/test_sizing_rule_sa050.py` (new),
    `tests/frontend/no_invented_figures.test.mjs`, `tests/unit/test_autopilot_executor_adds.py`,
    `tests/unit/test_autopilot_executor_switch.py`, `tests/unit/test_autopilot_isolation.py`,
    `tests/unit/test_decision_gate_portfolio_sa003.py`,
    `tests/unit/test_identity_portfolio_sa008.py`, `tests/unit/test_portfolio_settings.py`.
  - Docs (7): the KT and its PDF, AUTOPILOT_GUIDE, PRODUCT_MAP, the testing guide, README,
    CODEBASE.
  - Excluded: STATE, HANDOFF, this receipt (bookkeeping), and the owner's own line in
    `docs/README.md`.
- **Diff digest:** **`c4b58a22bd29c2fa5c583f0b5f4ba8bf89bcbf3e48e8546cb0fb16ef34be64ed`**,
  118,037 bytes over 24 paths (every manifest path except the PDF), by
  `analysis_data/sa050/digest.py`. It checks that HEAD is `85e447b`, runs
  `git diff --no-color --no-ext-diff HEAD -- PATH` for the 22 modified paths and
  `git diff --no-index /dev/null PATH` for the two new files, then sorts by path and
  concatenates.

## Self-review

Same-conversation self-review; it does not replace the fresh review.

- **Found and fixed:**
  - **Rounding twice in the weekly view.** The allocation stored 2 decimals
    and the screen showed 1, so 5.552% read "5.5%". The new browser test
    caught it. Figures are now stored once at one decimal. The flags and the
    switch-candidate test read exact shares, so a sector at 30.04% is flagged
    (rounded, it read 30.0).
  - **Advisor weights were rounded before comparing with the caps.** A
    holding at 10.004% would carry no `POSITION_LARGE` while the cap treated
    it as over. They are now unrounded.
  - **Three coverage gaps,** found while designing the mutants. Each now has a
    test and a mutant:
    - nothing pinned the notes' boundary (D5);
    - nothing proved every holding's close reaches the weights;
    - nothing pinned the SWITCH underweight test reading market shares (D10).
  - **Note wording.** "capped by the 30% cap on banking leaves …" now reads
    "the 30% cap on banking leaves room for less than one share at ₹400".
- **Every buy path:** a repository-wide grep for `side="BUY"` finds four.
  - `core/portfolio/autopilot.py`: the SWITCH and ADD legs, both through
    `size_buy`.
  - `services/api/routes/portfolio_api.py`: the manual add, the user's own
    choice and out of scope by the card.
  - `scripts/seed_autopilot.py`: the operator's one-time seeding, out of
    scope (L3).
- **Equity is conserved.** Each sale and buy happens at the run's mark, so
  total equity at those marks is unchanged by a run. The property test checks
  this on all 300 portfolios, within the paisa rounding of cash.
- **Compatibility:**
  - `rationale_hash` changes on a holding whose notes change (FEDERALBNK
    loses `SECTOR_CONCENTRATION_HIGH` and gains `POSITION_LARGE`). So its
    narrative cache misses once, costing one bulk call that day;
  - stored weekly reviews have no `cash_pct` and render as before;
  - `execute_advice` keeps its signature, with one new optional argument.

## Limits and follow-ups

- **L1. An ADD the rule skips is only logged.** It has no transaction to
  carry a note. The advice still says ADD, and the logs say why. A durable
  "every non-buy says why" run record belongs to SA-049, whose card requires
  it.
- **L2. `generic` is one sector.** In October, 5 of 9 shelf ideas carried
  that label, so the 30% cap can bind early on unrelated companies:
  about three generic positions at 10%. PR-004 caps by real industry. Until
  then the cap errs toward holding cash.
- **L3. Seeding and manual adds are not capped.** That is the card's scope.
  The seed refuses a portfolio that already has holdings, and with fewer than
  10 managed tickers each seeded position starts above 10%. TRIM rules, not
  force-sales, handle an over-cap holding.
- **L4. A band can be up to 60 days old,** the shelf's stale rotation. A
  stock that ran up is skipped with "needs a fresh deep dive" until a new
  dive resets the band. PR-004's re-dives supply fresh bands.
- **L5. ADD's advice test is position-only.** An ADD into a full sector is
  advised, then skipped at execution (logged, L1). The advice carries
  `SECTOR_CONCENTRATION_HIGH` when the sector is over 30%. At exactly 30%
  there is no note, and the ADD finds no room.

## Rollout (at the owner's word)

- **Commit and push only on the owner's word,** in a job-free window: not
  08:30–09:20 or 16:25–17:15 IST. No data migration and no new production
  setting are needed. `advisor.max_sector_pct` ships in `config.yaml`.
- **What production will show,** reasoned from the 11 Oct shape. This is
  inference; the current portfolio may differ:
  - FEDERALBNK's advice carries `POSITION_LARGE`, and no longer
    `SECTOR_CONCENTRATION_HIGH`;
  - on a bullish, healthy day WELCORP may ADD, about ₹13,900 a time, at most
    once every 5 trading days, until it reaches 10% of equity;
  - a SWITCH buys at most a 10% position and only inside its band;
  - the Sunday weekly review lists the cash share.
- **First week:** read the transactions' notes and any `switch_buy_skipped`
  alert, and run guide cases 07-F, 07-I and 07-J.
- **Rollback:** revert the commit.

## Commit-time edits (after acceptance)

- KT: header (code inspected, edition), link `core/portfolio/sizing.py` in
  "Sizing every buy", section 12's SA-050 row `Done`, PDF rebuild,
  `check_kt_docs`.
- AUTOPILOT_GUIDE header: edition and inspected revision.
- The testing guide's three SA-050 status lines.

## Next

`next_task: SA-050`, its **fresh review** in a new conversation
("continue"), then SA-051.
