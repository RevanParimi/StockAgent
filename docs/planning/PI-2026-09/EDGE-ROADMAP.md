# Edge roadmap — from "it invests" to "it beats a professional, and can prove it"

Written 15 Nov 2026 at the owner's request. Every card on this path links here. **If you are a new
conversation picking up one of those cards, read sections 1 to 3 and section 6 first.**

## 1. The goal and the bar

The owner judges the product by investments turning into profits, visible on the product. The
ambition: decisions more accurate than a senior professional's. Most professional fund managers
trail their index over long periods, so the measurable bar is:

> **Beat the Nifty 50 after costs, at prices that could really be had, over hundreds of graded
> calls, and be able to show it on one page.**

No design guarantees that. This path makes it measurable and gives it the best chance. The owner is
also selling the idea: a record nobody can pick apart is worth more than a clever feature.

## 2. The product in eight lines

1. **Screen** (Saturday 12:30 IST, no AI): rank NSE mainboard stocks on momentum, delivery, volume,
   deals and insider buying. `core/discovery/`
2. **Deep dive** (same run, up to 20 a week): one full analysis per candidate gives a verdict, a
   **conviction** (0 to 1), an entry band and an invalidation price. `core/discovery/deep_dive.py`
3. **Shelf**: up to 20 ideas whose conviction is 0.55 or more. `core/discovery/shelf.py`
4. **Daily review** (16:30 IST on day T): reviews the **previous** session, T−1.
   `core/intelligence/rl/workflows/daily_review.py`
5. **Advisor and autopilot**: decide HOLD, ADD, TRIM, EXIT or SWITCH for each holding, and with
   idle-cash deployment on, buy shelf ideas up to the market regime's target (80% invested in a calm
   market). Trades are booked on a **paper** portfolio at session T−1's close. `core/portfolio/`
6. **Auditor** (23:45 nightly, no AI): grades advice and shelf ideas against the Nifty at 10, 30
   and 60 sessions. `core/audit/`
7. **Scorecard** (Sunday 18:00): the week's results against the Nifty, with red flags.
   `core/portfolio/results.py`
8. **Brief, digest, alerts, chat**: what the user reads. `core/delivery/`

Words used on the cards: **idea** = a deep-dived stock; **the book** = the paper portfolio;
**excess** = a stock's return minus the Nifty's over the same sessions; **n** = how many cases a
number rests on (every number carries it); **shadow** = compute and record a new rule beside the
old one without letting it act.

## 3. Where things stood on 15 Nov 2026

- Idle-cash deployment was switched on for the owner's portfolio that morning (PR-014); its first
  run is Monday 16 Nov at 16:30. Before that the book held 2 stocks and about 81% cash.
- The evidence exit rule is to act after FIX-015 (PR-015).
- Adaptive learning is frozen (observe-only). Its rebuild is off the plan; the factor engine is
  paused.
- The queue is the planned-scope `todo` cards of [STATE.json](STATE.json), in its order.

## 4. The path

```
GOAL: beat the Nifty after costs, at real prices, on hundreds of graded calls
│
├─ 1. INVEST AND MEASURE                           running
│   ├─ Buying switched on ........................ PR-014
│   ├─ Sell on evidence .......................... FIX-015, PR-015
│   ├─ Losses by exit reason ..................... PR-013
│   └─ Missed-run alarms ......................... SA-036, SA-042, SA-035
│
├─ 2. A RECORD NOBODY CAN PICK APART               planned, after PR-013
│   ├─ Prices that could really be had ........... PR-016
│   ├─ Every deep dive graded, at the conviction
│   │  it was issued with, beside the screen ..... PR-017
│   ├─ Does conviction predict? .................. PR-018
│   ├─ Does the screen's cut choose? ............. PR-041
│   ├─ What each refusal rule cost ............... PR-019
│   ├─ A written case per position ............... PR-005
│   └─ One page that shows the record ............ PR-020
│
├─ 3. READ MORE THAN A PROFESSIONAL                waits for stage 2's first results
│   ├─ Industry lenses: search for, and tell the
│   │  analyst, what moves each industry
│   │  (planned, after PR-018) ................... PR-032
│   ├─ A fuller read of company news: a second
│   │  search beside Serper (Parallel or Exa),
│   │  recorded first, read if it helps .......... PR-043, PR-044
│   ├─ Reported financials, dated ................ PR-021
│   ├─ The full results documents ................ PR-022
│   └─ Accounting red flags ...................... PR-023
│
├─ 4. DECIDE BETTER THAN ONE ANALYST               waits for PR-017's grades
│   ├─ An independent challenge to every BUY ..... PR-024
│   ├─ Two runs must agree ....................... PR-025
│   ├─ Best model on the big decisions ........... PR-012 (already planned)
│   └─ Replay the fixed rules on past years ...... PR-026
│        └─ the factor engine plugs in here ...... SA-045 to SA-047 (paused)
│
├─ 5. MANAGE THE BOOK LIKE A FUND                  waits for 10+ holdings, 4 weeks
│   ├─ Holdings that fall together ............... PR-027
│   ├─ A loss limit for the whole book ........... PR-028
│   └─ Size by conviction, once proven ........... PR-029
│
├─ 6. LEARN, WITH PROOF                            waits for 300+ graded ideas
│   └─ Which signal earns the money .............. PR-030
│
└─ 7. REAL MONEY                                   waits for the 8-week results
    └─ A small real-money mirror, own account .... PR-031

ALONGSIDE: remove what the goal does not need .... CLEAN-004, CLEAN-005, CLEAN-003,
                                                   CLEAN-006 (paused)
```

## 5. The cards

| Card | What | Stage | On the board | Starts when |
|---|---|---|---|---|
| [PR-016](stories/PR-016.md) | Show what the book earns at prices that could really be had | 2 | planned | after PR-013 |
| [PR-017](stories/PR-017.md) | Grade every deep dive at the conviction it was issued with, beside the screen's other candidates | 2 | planned | after PR-016 |
| [PR-018](stories/PR-018.md) | Put the conviction check in front of the owner, with a rule for trusting it | 2 | planned | PR-017 done |
| [PR-041](stories/PR-041.md) | Grade the screen's cut forward before it is widened | 2 | planned | after PR-018 |
| [PR-019](stories/PR-019.md) | What each refusal rule cost | 2 | planned, blocked | `PR-014-D1` read |
| [PR-020](stories/PR-020.md) | One page that shows the record | 2 | planned, blocked | `PR-014-R1` read |
| [PR-032](stories/PR-032.md) | Industry lenses, first slice: the general path searches for, and is told, what moves each industry | 3 | planned | PR-017 done |
| [PR-043](stories/PR-043.md) | A second search beside Serper: two weeks recorded, not read | 3 | planned | done 19 Nov; the read `PR-043-W2` |
| [PR-044](stories/PR-044.md) | The deep dive reads the kept search engine's excerpts, graded before and after | 3 | planned | `PR-043-W2` passes and PR-017 done |
| [CLEAN-004](stories/CLEAN-004.md) | Remove live prompt editing, the daily second AI call, the C++ indicator copy | — | planned | after CLEAN-002 |
| [CLEAN-005](stories/CLEAN-005.md) | Remove the backup analysis and the old per-analyst layer | — | planned | CLEAN-004 done |
| [CLEAN-003](stories/CLEAN-003.md) | Remove the learning writes and the 30-day price forecast; settle the operator extras | — | planned | after PR-008 |
| [CLEAN-006](stories/CLEAN-006.md) | Merge the four sector prompts into the one path, their knowledge kept as lenses | — | paused | the rule in the card says merge at `PR-014-R2`, PR-032 done |
| [PR-021](stories/PR-021.md) | Reported financials, kept with the date each became public | 3 | paused | 100 ideas graded at 30 sessions, and `PR-014-R1` read |
| [PR-022](stories/PR-022.md) | Read the full results documents | 3 | paused | as PR-021 |
| [PR-023](stories/PR-023.md) | Accounting red-flag checks | 3 | paused | PR-021 done |
| [PR-024](stories/PR-024.md) | An independent challenge to every BUY | 4 | paused | PR-017 done and 100 ideas graded |
| [PR-025](stories/PR-025.md) | Two runs must agree | 4 | paused | PR-017 done |
| [PR-026](stories/PR-026.md) | Replay the fixed rules on past years | 4 | paused | PR-019 names a rule worth changing, or `PR-014-R2` read |
| [PR-027](stories/PR-027.md) | Holdings that fall together | 5 | paused | 10 or more holdings for 4 weeks |
| [PR-028](stories/PR-028.md) | A loss limit for the whole book | 5 | paused | as PR-027 |
| [PR-029](stories/PR-029.md) | Size by conviction, once proven | 5 | paused | PR-018's rule passes |
| [PR-030](stories/PR-030.md) | Which signal earns the money | 6 | paused | 300 ideas graded at 30 sessions |
| [PR-031](stories/PR-031.md) | A small real-money mirror on the owner's own account | 7 | paused | `PR-014-R2` read, the book ahead of the Nifty at real prices, the compliance checklist reviewed |

**How a paused card starts.** It is never picked up by "continue". At each results review
(`PR-014-R1` at 4 weeks, `PR-014-R2` at 8 weeks, then monthly) the conversation lists which start
conditions are now met and asks the owner which to promote. A promoted card's scope becomes
`planned` in STATE.

## 6. Rules for every card on this path

1. **Check what exists before building.** Section 7 lists what is already there. A card that turns
   out to be built is closed with a note, not rebuilt.
2. **A report before a rule, and shadow before acting.** First show the number. Change a buy, sell
   or size only after the number says so, at a threshold written down in advance.
3. **Issue-time honesty.** A graded call may read only what was known when it was made. A score
   revised later never replaces the score a call was made with.
4. **No number without its n.** Under 30 cases, the report says "too few to judge".
5. **"No benefit" is a valid result.** A card that shows its idea does not help is done.
6. **Paper money is called paper money** wherever a result is shown.
7. **Review lane** is named on each card (AGENTS.md step 4): changes to what is bought, sold, sized
   or graded take a fresh-session review; reports do not.

## 7. What already exists (do not build it again)

| Already there | Where | Its limit |
|---|---|---|
| Shelf ideas graded against the Nifty at 10, 30, 60 sessions | `core/audit/outcomes.py` `grade_shelf_lane` | Only ideas in `shelf.json`; conviction read at grading time, after re-dives changed it; entry at a close before the dive |
| Conviction buckets against excess return | `core/audit/metrics.py` `conviction_calibration`, `calibration_spread`; in `core/audit/report.py` | Inherits the limits above; not on the weekly scorecard |
| "How shelf ideas did" line on the scorecard | `core/portfolio/results.py` `idea_quality` | Count and median only |
| Results, con-calls and presentations read into a stock's dossier | `core/intelligence/rl/agents/event_ingestor.py` | The announcement's text and one web page; managed stocks only, so a new idea has none |
| Web browsing in every analysis, on every path: three searches (five results each, title and snippet, last month) and one page extract | `services/data/context/bundle_builder.py` `build_sector_bundle`; usable in 93% to 100% of production runs | The general path's searches do not name the stock's industry (PR-032). The page extract is cut to 600 characters |
| An adopted design for sector knowledge as data ("lenses"), 26 Sep 2026 | `docs/superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md` section 4.1; card SA-026 | Paused with the factor engine. PR-032 builds its first slice |
| Open questions on held stocks researched on the web | `core/intelligence/rl/agents/question_researcher.py` | Managed stocks only |
| A bear condition in the analysis | `unified_analyst.py` (`key_risks`, `bear_case_if` per dimension) | The same model in the same call; nothing can lower the score |
| Why SWITCH decisions went wrong | `core/audit/attribution.py`, `switch_evaluations.jsonl` | SWITCH only |
| Trading costs and a tax estimate | `core/portfolio/costs.py` | Spread, slippage and the stale booking price are not modelled |
| A replay of recorded forecasts | `core/intelligence/rl/eval/harness.py` | Measures the frozen learner, not the portfolio's rules |
| Compliance checklist (SEBI, data protection, licensing) | `docs/LEGAL_AND_COMPLIANCE.md` | A lawyer's review is still the gate before any stranger or payment |

## 8. What the goal does not need

Decided on 15 Nov 2026 after one read-only production probe
([the counts](evidence/CLEAN-003-production-counts-2026-11-15.md)). The full table, with who
decided what, is in [CLEAN-003](stories/CLEAN-003.md).

| Item | Decision | Card |
|---|---|---|
| Live prompt editing and the nightly prompt deploy, with its screen | Remove. It never deployed a prompt and cannot edit the main analysis's prompt | [CLEAN-004](stories/CLEAN-004.md) |
| The control lane: a bare model's daily next-session call beside the product's forecast | Remove. It showed the product's daily forecast losing to a bare model for three months. The second judge moves to the weekly buy idea (PR-017 lane `bare`) | [CLEAN-004](stories/CLEAN-004.md) |
| The C++ indicators beside their Python copy | Remove. Production does not have them | [CLEAN-004](stories/CLEAN-004.md) |
| The legacy worker pool (the backup analysis) and the per-analyst prompts and analysts it runs on | Remove. It ran in 1.5% of analyses; a failed analysis becomes "no analysis today" | [CLEAN-005](stories/CLEAN-005.md) |
| Learning writes in the daily review (lessons, weight proposals, ledger propagation, the learning reports) and the factor table ending March 2023 | Remove, once the evidence exit rule has acted for a month | [CLEAN-003](stories/CLEAN-003.md) |
| The 30-day price path, its daily grading and re-forecasts, and the four-sector seasonal calendar | Remove, after ADD, TRIM and SWITCH read the written case (PR-005) | [CLEAN-003](stories/CLEAN-003.md) |
| The four sector prompts of the main analysis, and the fund lists for four sectors | Keep until `PR-014-R2`, then merge into one path unless PR-017's results by path show they earn their place. The general path gets industry lenses first | [PR-032](stories/PR-032.md), then [CLEAN-006](stories/CLEAN-006.md) (paused) |

**Stays, because the path needs it:** screen, deep dive, shelf, buy candidates, deployment, sizing,
stops and evidence exits, costs, auditor, scorecard, company-event feed, dossier, regime label,
brief and digest, accounts and the two data planes, backups and the watchdog.

**Also stays, at the owner's word (15 Nov): the IPO lane.** The owner wants IPO buy-or-skip
analysis in the morning brief. The brief already shows IPO facts and a demand-based lean. The
deeper verdict is computed daily and hidden until the watchdog milestone
`ipo_verdicts_visible_gate` is judged (60 days of forward rows, or 31 Dec 2026).

**Found by the same probe: the daily price forecast has no measured skill.** In August, September
and October 2026 its next-session direction calls were right 25% to 32% of the time, a bare model's
38% to 44%, and "same as yesterday" 65% to 77%. About 30% of all model calls serve that forecast
and the frozen learner.
