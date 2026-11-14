# Profit-path architecture review — 14 Nov 2026

**Asked by the owner on 14 Nov 2026:** "be the architect and review if there needs any
improvements on design, or remove anything. I don't see any profit, neither investments. Are these
tasks good enough for our goal?"

**The goal** (owner, 6 Nov): investments turning into profits, visible on the product.

**Short answer: no.** The open tasks fix real things, but none of them turns investing on, none
measures whether the buy door lets ideas through, the exit fix waits on a gate that cannot fill, and
almost half the remaining points rebuild a learner that is switched off.

Evidence labels used below: **code** (read in the repository at `cbbee3c` plus the accepted FIX-031
tree), **production** (read-only counts already recorded, with their date), **board** (STATE.json),
**inference** (my reasoning, not measured). Nothing in production was read or changed for this
review.

## 1. What was found

### F1. Nothing can invest (code, production)

- A new position opens in two ways only: a SWITCH (sell one holding, buy one idea) or idle-cash
  deployment. Deployment is off: `autopilot.deploy_idle_cash: false` in `config.yaml`, no
  per-portfolio override.
- Production: 2 holdings and 81% cash on 27 Sep and on 11 Oct; the same 2 holdings on 29 Oct. The
  13 Nov counts probe found 16 exit-shadow rows for November's sessions, which fits 2 holdings
  (inference from a row count).
- The switch's three stated preconditions (FIX-023, FIX-024, FIX-025) were all live by 7 Nov.
- The book is paper money. The repository holds no broker or order code; costs and tax are
  simulated. A wrong buy costs a row in a paper ledger. A closed switch costs the only evidence the
  goal needs.

**Example.** ₹10 L, 19% in stocks. The stocks rise 10%: the book earns about ₹19,000. At the 80%
target the same rise earns about ₹80,000.

### F2. Nobody knows what the switch will buy (code; not measured)

An idea is bought only if it passes all of these: a BUY verdict; conviction at least 0.55; a deep
dive at most 30 days old and made before the session's close; not sold since that dive; the data
gate; a close for the session; identity; NSE's surveillance report; the entry band; above its
invalidation price; a named sector; the 10% position cap, the 30% sector cap and the cash floor; at
most 2 new positions a day; and a market regime recorded for that day.

Each check is defensible. Their joint pass rate has never been measured in production: the record of
refusals (`deployment.run_record`) is written only when the switch is on. On 12 Nov the shelf held
19 active BUY ideas (production, counts probe). How many would pass the rest is unknown.

### F3. The entry band keeps laggards and refuses winners (code, inference)

- `deep_dive.entry_levels` sets the band at 97% to 102% of the close the deep dive read.
  `sizing.entry_check` refuses any price above the top. The band stays until the next deep dive, up
  to 30 days later (`discovery.redive_after_days`).
- Discovery ranks stocks because they are rising: momentum, volume breakout near a 60-day high and
  52-week-high strength carry 55% of the signal weight.

**Example.** Two ideas are dived on Saturday at ₹100, band up to ₹102. A is ₹104 on Monday: refused
that day and every day until a re-dive. B drifts to ₹96: bought. Over weeks the book collects the
ideas that did not move.

Not measured. With the switch on, each day's digest counts "N ideas above entry band".

### F4. The rule that sells is the one found wrong, and its replacement cannot be judged (production, board)

- The acting rule sells on `thesis_break`: the daily price path missed and the review judged the
  thesis "not intact". On 11 Oct its exits looked right at 10 sessions (7 of 10) and wrong at 30
  (6 of 7 sold stocks then beat the Nifty). Winners were cut at +7.5%, losers ran to −11.9%.
- 13 Nov counts probe: since August, 988 thesis reviews, 365 judged "not intact" (37%), and 110
  re-forecasts. The price path "breaks" in over a third of its reviews.
- The evidence rule (PR-009) has run in shadow since 30 Oct: 20 rows. Its gate needs 15 matured
  disagreements at 30 sessions over at least 8 weeks, passing at two weekly looks in a row. The card
  expects 10 to 12 weeks **with 12 or more holdings**. With 2 holdings it will take far longer.
- FIX-015 (open, 1 point): the sell-on-shock trigger has never fired under either rule.

### F5. Almost half the plan rebuilds a learner that is switched off (board, production)

- SA-039 froze adaptive learning (observe-only, weights at defaults; verified in production 1 Oct).
- 18 open cards, 76 of the 157 open points, rebuild learning (14 cards, 58 points) and scoring (the
  factor engine, 4 cards, 18 points).
- Learning needs outcomes. There were 8 closed trades between August and 11 Oct.
- The daily forecast-and-grade loop (a 30-day price path per managed stock, graded, reviewed and
  re-forecast every day) is the largest subsystem. Today it feeds the frozen learner and the exit
  rule in F4.

### F6. The process has become the bottleneck (board)

- 2 to 14 Nov: nine cards (FIX-023 to FIX-031) on the buy door, with the door closed. Seven of the
  nine came out of the fresh review or the build of an earlier one.
- Each card is two conversations, a 15 to 20 minute full suite, mutants and receipts.
  `STATE.json` is 977 KB and `HANDOFF.md` 546 KB, and each conversation starts by reading them.
- That weight fits code that grades forecasts or moves real money. On a paper book it should be
  proportionate to the harm a defect can do.

## 2. What the design should be

The system has two halves:

1. **Forecast and learn:** predict each stock's 30-day price path, grade it daily, adapt weights.
2. **Research and invest:** screen the market weekly, deep-dive the best, buy the ideas, hold on a
   written case, sell on evidence or a stop, compare with the Nifty.

Half 1 is the larger part of the code and of the open plan, and has no evidence of producing
profit. Half 2 holds the only positive evidence so far (shelf ideas beat the Nifty 13 times in 21
at 30 sessions, 11 Oct) and is the half that is switched off.

**Direction: half 2 is the product.** Half 1 shrinks to what half 2 still reads, decided from
results, not in advance.

## 3. Recommendations

| # | Change | Kind | Needs |
|---|---|---|---|
| R1 | **Switch deployment on now**, as a dated board milestone, right after FIX-030-M1 and the deploy of FIX-030 and FIX-031 | add | owner's word (a production setting) |
| R2 | **Read the door for two weeks**: each day's refusal counts by reason. If more than a third of BUY ideas are refused "above entry band", build the band fix (top of the band scaled by the stock's own volatility, or an out-of-band BUY gets Saturday's first re-dive) | add, 1 point; the fix 2 points only if triggered | R1 |
| R3 | **Let the evidence rule act** once FIX-015 is in and the book is deployed. The old rule's verdict keeps being recorded, so the same comparison runs with the roles swapped. Roll back with one setting | owner decision | FIX-015, R1 |
| R4 | **Take the learning rebuild off the plan** (SA-012 to SA-024, SA-043: 58 points) and hold the factor engine (SA-026, SA-045 to SA-047: 18 points). Learning stays frozen as it is | remove / hold | owner decision |
| R5 | **A results review on a date**, 4 and 8 weeks after R1: share invested, holdings, book against the Nifty, closed trades by exit reason (PR-013), refusal counts. The next design changes come from that page | add | R1, PR-013 |
| R6 | **A lighter process for a paper book**: the two-conversation review only for buy, sell, size and grading logic; low, latent findings go to one backlog list with their trigger, not a card each; move HANDOFF and STATE history older than two weeks to an archive file | change to AGENTS.md | owner decision |

**On R3, the trade-off in one example.** Bought at ₹500. The old rule sells at ₹480 on a price-path
miss. The evidence rule keeps it, because no filing, SELL verdict or invalidation price says the
case broke. If it recovers to ₹560, the evidence rule earned ₹80 a share more. If it falls to its
stop at ₹440, it lost ₹40 a share more. The stop is the same under both rules. PR-013's "what
waiting cost" line shows which of the two happens more.

**Order approved by the owner on 14 Nov** (recorded in STATE the same day): FIX-032, FIX-015,
FIX-017, PR-013, PR-005, PR-007, PR-008, SA-036, SA-042, SA-035, PR-010, then the rest, the
learning block last.

## 4. Owner decisions

**The owner said yes to all four on 14 Nov 2026** (about 13:20 IST). Recorded the same day:

| Decision | Where it lives |
|---|---|
| R1 switch deployment on, with R2 (the door read) and R5 (results at 4 and 8 weeks) as its dated checks | card [PR-014](../planning/PI-2026-09/stories/PR-014.md), first in the queue |
| R3 the evidence rule acts, without waiting for PR-009's gate | card [PR-015](../planning/PI-2026-09/stories/PR-015.md), after FIX-015 and PR-014 |
| R4 the learning rebuild off the plan, the factor engine paused | STATE scope `removed` (SA-012 to SA-024, SA-043) and `paused` (SA-026, SA-045 to SA-047, SA-027) |
| R6 a lighter process | AGENTS.md (the goal, two review lanes), [BACKLOG.md](../planning/PI-2026-09/BACKLOG.md), card [CLEAN-002](../planning/PI-2026-09/stories/CLEAN-002.md) |

The planned queue went from 46 cards and 157 points to 27 cards and 72 points. Nothing in
production changed on 14 Nov: the switch stays off until PR-014's step 6.
