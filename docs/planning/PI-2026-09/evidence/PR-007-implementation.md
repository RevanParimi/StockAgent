# PR-007 receipt — plain, fact-grounded buy and sell explanations

**Status: accepted, 27 Nov 2026** (light lane, without a fresh-session review).

Autopilot `1127-1707-p1` on the code-server, Sonnet at xhigh, Fri 27 Nov 2026 from about 18:30 IST.
Nothing in production was read or changed; no model provider was called.

**Lane: light** (decided 21 Nov, STATE `review_lane`): the words are display only. The ledger's
`reason` and `note`, the advice narrative and the digest's `deployment` record are written as
before, and `advisor.py`, `autopilot.py` and `narrator.py` are not changed. No buy, sell, size or
grade reads anything new. The Opus check looked for a way this change could reach a decision,
the money arithmetic or an account's access and found none. Profit-path step: **measure** (the
owner can read why each trade happened).

Base revision `a3246ae`; committed to `main` with these records. Diff digest `a67ffe95bf241bda` (sha256,
first 16, of `git diff --binary a3246ae <commit>` over every path except STATE and HANDOFF with
their archives, BACKLOG and this receipt).

## What was built

| Path | What it does |
|---|---|
| `core/portfolio/plain_words.py` (new) | the four parts' wording, pure: the rule that fired, notes, skip reasons, the banned-word list and the checks on a model's sentence |
| `core/portfolio/explain.py` (new) | each trade's facts, the one call for a purchase, the review card, holding rows, the per-user store `explanations.jsonl` |
| `core/portfolio/pipeline.py` | rows worded with the digest; trades and the review drafted before delivery; alerts use the words; a same-day re-run keeps the day's record |
| `digest.py`, `digest_text.py`, `store.py` | `keep_day_record`, the digest text, one digest by date |
| `core/delivery/brief.py`, `weekly.py`, `ui_data.py` (chat brief) | the same words; "Not reviewed" for a row with no review |
| `portfolio_api.py` | `/portfolio/transactions` sends each trade's `plain`; `/portfolio/digest/latest` sends `plain_review` |
| `portfolio.jsx`, `digest-view.jsx`, `sw.js` v13 | four parts on a trade and the review card, the recorded text under "details", a note on the holdings table |
| `scripts/explain_trades.py` (new) | the backfill: a dry run, then `--apply` |
| `config.yaml`, `settings/base.py` | `advisor.plain_reasons` (on) and `advisor.narrate_model` (the reasoning tier) |
| `tests/unit/test_plain_reasons_pr007.py` (new), one browser test, two older tests, `conftest.py` | below |
| `tests/frontend/architecture_map_galaxy.test.mjs` | the map's brightness check no longer measures a dot a lit import line runs over (below) |
| KT section 6 ("Plain explanations") and sections 3, 4, 7, 11, 12; guide 11-Q; the map (M5.8, the store) | current design |

## Decisions (taken as recommended, CLAUDE.md section 2)

- **D1. A sale makes no model call.** The card's hard review asks whether a reason can be claimed
  that the rule did not use. The Opus check showed the model's sentence after a stop sale accepted
  as "Investors sold the stock because quarterly results missed estimates". No check can prove such a
  sentence true, so a sale quotes the case recorded at the purchase after the rule that sold it.
- **D2. The review card is code only.** This differs from the card's "one per review". Its counts and
  its stopping rule come from the record, in the shape of the card's own example. In the Opus check, a
  model sentence replaced the true counts with "Three ideas were priced above…" when it was one.
- **D3. Holding rows are templates.** No call per holding, so the token estimate stands.
- **D4. Two listed inputs are left out.** News since the last review that did not break a case (it
  would let a sale read as caused by it; the events that broke a case are named in the rule
  sentence), and the sector's move since purchase (the product keeps no sector index series). The
  Nifty's move is in a sale's "what we did".
- **D5. "Everywhere the reason appears"** is read with the 21 Nov section: the stored audit text stays;
  the screens, the Inbox digest, the brief, the weekly switch calls, the escalation alerts and the
  chat's portfolio tool show the plain words. Without them they show the audit text as before.
- **D6. A holding row whose stock traded that run takes the trade's words**, so the alert, the
  digest and the brief say the same.
- **D7. Two older tests changed** (`test_deployment_follows_money_fix025`,
  `test_sold_stock_leaves_review_fix028`): the digest text now says why in plain words. Both still
  check the stored `top_up_skipped` and `not_reviewed` fields, unchanged, and the report's date.

**Tokens.** Only purchases call the model: at most one per new position or top-up. That is below
the card's estimate of about 0.4 M tokens a month, which counted sales and the review too.
Measured use is not known until the deploy.

## Routed inputs

| Input | What the words now do |
|---|---|
| SA-050 R4 | a portfolio with no cash on record reads "over 10% of your holdings", nothing about buying |
| PR-009 L2 | a case sale names which broke: the event and its date, the verdict and its IST day, or the close and the level (and the level before a bonus or split). One fixture each |
| FIX-024 L1 | an unread market names the day and the cause, never "normal" |
| FIX-025 L2, L3 | a same-day re-run keeps the day's record, trades and row reasons; the holdings table says "No shares bought: why" |
| FIX-028 I-1 | the brief says "Not reviewed"; the table shows a stock with no daily review |
| FIX-031 R1 | the results note says the date may have been announced after the close |

## Acceptance

| Criterion | Evidence |
|---|---|
| A fixture per verdict gives four parts, every number traced | stop, trailing, case broken (three), TRIM, ADD, SWITCH (both legs), HOLD through a fall; allowed figures listed by hand in each |
| An invented number or banned word is rejected, fallback clean | parametrised answers (digits, number words, "doubled", codes, stop %, two sentences, our voice, no JSON, no answer) |
| The stop is a rupee price | every contract assertion refuses a stop given as a percentage; hand-worked prices, dividends counted |
| Narration failure never blocks | pipeline with a failing store; one failing trade; model unreachable; time budget |
| One user's text never holds another's position | per-user file, a foreign row ignored, the API as another user; the model is given company facts only |
| Banned words over every template and random combinations | 270 seeded combinations with hostile facts |

The tests build the skip and stop reasons from the producing code (`sizing`, `shelf`, `autopilot`,
`deployment`), so a reworded rule fails them.

## The Opus check (xhigh, a fresh subagent)

It ran the story's tests, reproduced its findings with scratch scripts, and judged the change safe
to commit as light-lane work once findings 1 and 2 were fixed. Fixes were made after it; **it did not
read the fixed code**. The tests below ran on the fixed code.

| # | Finding | Done |
|---|---|---|
| 1 | a sale's model sentence could invent the cause | D1 |
| 2 | the review's model sentence could replace true counts; number words passed | D2; number and ratio words are now checked for purchases |
| 3 | skip reasons misread ("ASMTEC: …" read as an exchange measure; "no entry band" as "above") | reason read without the symbol and money; ordered patterns |
| 4 | a capped switch said all the money was used | says what stayed in cash |
| 5 | "a goal of 0.0%" on a closed day; one "what would change our mind" for every stop | goal only when in force; one per stopping rule |
| 6 | the level test was told as acting at once; the verdict test left out | all three tests, all after the ten sessions |
| 7 | the off switch left stored words showing | API, brief and weekly gate on it |
| 8 | reading a trade's facts created a prediction-store folder | reads the score history and shelf only |
| low | held tax trim told as "no rule met"; wrong "size" label; "US market", "tax regime", "Pvt." rejected; guide overstated; stale top-up note after a re-run; "after this sale" on advice; backfill's exit rule; `event_ids` naming; a row with no parts failing a page | fixed |
| low | a SWITCH alert no longer carries the destination's thesis | left: BACKLOG B-51 |

"Agent" stays banned in a model sentence ("its sales agents"), as the card lists it; that sentence
falls back.

## Tests

The full suite runs only through `scripts/ci/guarded_suite.py`. **It passed on the committed code:**

- **Main step:** 7,746 passed, 5 skipped, 1 expected failure (peak `anon` 1,244 MB). That is 383 more
  than the afternoon's 7,363, the story file's count.
- **Browser step:** 61 passed, 0 failed (781 s, peak `anon` 1,822 MB; 787 MB just after, 802 before).
- **Guards:** the map guard, `check_broad_except.py` and `check_kt_docs.py` report no problem.

What failed on the way:

1. First full run, 19:15 IST: the map guard (the model was one `pipeline.py` edit stale;
   regenerated) and the brightness check below.
2. Second full run, 19:38 IST: the main step passed (the figures above). In the browser step, "the
   world and the galaxy pass the focus and a search on" timed out once, waiting for the search box to
   open (line 435). It had passed in both earlier runs of that file, and its code is not changed.
3. Browser step alone, 19:57 IST, same code: 61 passed. The flake is BACKLOG B-53.

Also run: the story file (383) and 1,713 related portfolio, delivery, API and map tests; the new
browser test of the screens (a trade's four parts, "details", the review card, the table's note).

## One map test changed, and why

The three new files moved the code galaxy's layout. In the first full run, "selecting M5 lights its
files" failed: `core/discovery/sector_naming.py` fell to 67% of its brightness where under 60% is
asked. It imports and is imported by no Portfolio file. A screenshot showed lit Portfolio import
lines running over its dot. The test skipped only dots that another dot covers; it now also skips
dots a lit line crosses. The 60% rule is unchanged. A temporary copy of the test showed 7 dots
still measured, all at 39% to 44%.

## Open limitations

- On a purchase the checks prove that a number is in the facts, not that the model's sentence uses
  it truthfully (B-52).
- A backfilled trailing-stop sale names no highest price: the run's signals are not stored.
- Past reviews' cards are not backfilled: the screens show the latest review only.
- Not run: any real model; production.

## Rollout and rollback

- Visible from the first 16:30 review after the deploy (STATE `PR-007-W1`). Earlier trades show their
  recorded text until the backfill, which writes production files and runs only at the owner's word:
  dry run `python scripts/explain_trades.py --user primary` inside the container, then `--apply`.
- The owner reads the first week's reasons and records three examples here (guide 11-Q).
- Rollback: `advisor.plain_reasons: false` (the audit text shows again), or revert.
