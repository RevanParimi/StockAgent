# StockAgent — Start Here

A slow, owner-paced path to understanding what has been built. Read one session at a
time. Each session ends with questions; when you can answer them in your own words, move on.

Facts below are dated. For the authoritative detail, follow the links: the
[technical design (KT)](TECHNICAL_DESIGN.md) is the source of truth.

---

## 1. The product in one paragraph

StockAgent researches Indian listed stocks (NSE), forecasts them, checks its own
forecasts every trading day, and runs a **virtual ₹10 L portfolio** on real prices with
**mock money**. AI models read the evidence and write the explanations; **plain code makes
the decisions** (buy, sell, size, stops). There is no broker connection, so nothing real is
ever bought or sold. It runs on Railway as one web app with a built-in scheduler, and
emails you a morning brief and a weekly review.

## 2. The one picture: three loops

| Loop | What it does | Everyday example |
|---|---|---|
| **1. Research** | Collects prices, results, filings and news for a stock; an AI scores 6–9 dimensions (fundamentals, valuation, sentiment…); code combines them into a verdict | "MARUTI: BUY, composite 0.62, evidence actionable" |
| **2. Learning** | On the 1st of each month it writes a forecast for every tracked stock; every evening at 16:30 it compares the forecast with the real close and records what went wrong | "Predicted ₹12,400, closed ₹12,050; sentiment was too optimistic" |
| **3. Portfolio** | After the evening review, a rule cascade looks at each holding: **EXIT → TRIM → ADD → HOLD** (or SWITCH to a better idea), records the advice, and the autopilot executes it virtually | "EXIT FEDERALBNK: stop breached; buy WELCORP instead" |

Feeding the loops: **Discovery** (weekly hunt for new ideas → the "shelf") and **IPO**
tracking. Watching the loops: the **auditor** (grades past advice against the Nifty), the
**watchdog** (checks the system itself is healthy), and **backups**.

Picture: [ARCHITECTURE.md → "Three connected product loops"](ARCHITECTURE.md#three-connected-product-loops).

## 3. Six distinctions that trip everyone up

1. **A BUY verdict is not a purchase.** Research says "BUY"; only the portfolio rules decide whether to buy.
2. **Advice is not a transaction.** Advice is recorded every evening; a transaction exists only if the autopilot executed it.
3. **Learning mode — `observe` vs `adapt`.** In `observe` (production today) the system *records* what it would change in its weights but changes nothing. In `adapt` it actually re-weights.
4. **Decision gate — `record` vs `enforce`.** Every analysis is labelled actionable / degraded / abstain. In `record` (production today) the label is only logged; in `enforce` an abstain blocks new buys and forecasts.
5. **Three different "judges".** The *feedback agent* (daily, forecasts vs closes), the *auditor* (nightly, advice vs Nifty), the *watchdog* (morning, is the system healthy). None of them alone proves the AI is getting smarter.
6. **The LLM explains; code decides.** If narration fails, the trade still happens with its rule code.

## 4. A day in the life (IST, weekdays)

| Time | What runs |
|---|---|
| 06:30 | Watchdog health checks (mail to you only if something is wrong) |
| 08:15 | Company events: overnight filings, insider trades, pledges, news |
| 08:45 | Pre-open shock check (big overnight news → re-forecast) |
| 08:50 | **Morning brief** emailed |
| 16:30 | **Daily review** (learning loop), then portfolio advice + autopilot |
| 18:30 | Company events again (the day's filings) |
| 23:30 / 23:45 | Backup with restore drill / auditor grades matured advice |
| Sat | Discovery funnel (new ideas → shelf), dossier research |
| Sun 18:00 | **Weekly review**: results scorecard vs Nifty |
| 1st, 09:00 | Monthly forecasts for every tracked stock |

Full list: [KT §9](TECHNICAL_DESIGN.md#9-scheduled-jobs-and-event-hooks).

## 5. Where things stand (24 Oct 2026)

- **Production:** learning mode `observe`, decision gate `record`, off-site backup not yet set up (your deferred task). Source: [KT §1](TECHNICAL_DESIGN.md#production-state-at-this-edition).
- **Results baseline (your probe, 11 Oct):** 2 holdings, 81% cash; portfolio −0.5% since 10 Jul vs Nifty −8.2% — ahead mostly *by accident of sitting in cash*. Sales: average win +7.5%, average loss −11.9%. Source: [product review §11](audit/2026-10-11-product-results-review.md#11-production-baseline-the-owners-probe-11-oct).
- **Improvement programme (PI-2026-09):** 33 of 79 stories done, 1 in progress, 45 to do. In progress: **PR-009, exit on evidence instead of a price-path miss** (needs rework after its review). Coming: idle cash put to work (SA-049), an investment case per holding (PR-005), plain fact-grounded reasons (PR-007). Live status: [STATE.json](planning/PI-2026-09/STATE.json) and [HANDOFF.md](planning/PI-2026-09/HANDOFF.md).
- **Not yet shown:** that the learning actually improves predictions. Adaptive state exists; benefit is unproven.

---

## 6. Reading path: five sessions

Each session takes 45–60 minutes.

### Session 1: What it does, for a user
- Open the live app: <https://stockagent-ai.up.railway.app/app/index.html>. Run one analysis, open the portfolio and the inbox.
- Read [README.md](../README.md): "What Is StockAgent?", "How the Verdict Is Produced", "Compass".
- Read [ARCHITECTURE.md](ARCHITECTURE.md) (short, 15 minutes).

*Check yourself:* What are the three loops? Why does a BUY not buy anything? What does the morning brief contain?

### Session 2: Research, the verdict
- [KT §2](TECHNICAL_DESIGN.md#2-product-map-and-three-loops) and [§4](TECHNICAL_DESIGN.md#4-research-input-to-recommendation): data bundle, data health, decision gate, instrument identity (the Tata Motors demerger is the worked example).

*Check yourself:* When does an analysis "abstain"? Why are TATAMOTORS and TMPV separate stocks?

### Session 3: Learning
- [KT §5](TECHNICAL_DESIGN.md#5-learning-forecast-review-and-memory), especially "Grading defect: an example everyone can follow" and "Learning mode".
- Optional depth: [RL_DESIGN.md](RL_DESIGN.md).

*Check yourself:* What is an envelope? Why did we switch production to `observe`? What would have to be true before switching back to `adapt`?

### Session 4: Portfolio and money (the part that decides your results)
- [KT §6](TECHNICAL_DESIGN.md#6-portfolio-advice-and-virtual-execution): advisor cascade, the two exit rules, sizing, cash deployment.
- [KT §7](TECHNICAL_DESIGN.md#7-profitloss-and-the-different-marksheets): how P/L and the weekly scorecard are measured.
- [Product results review](audit/2026-10-11-product-results-review.md): its "Summary for the owner" table.

*Check yourself:* Why did the portfolio end up 81% cash? Why do winners get sold early? Which stories fix each?

### Session 5: Around the edges
- [KT §8](TECHNICAL_DESIGN.md#8-discovery-and-ipo-functionality) discovery and IPO; [§10](TECHNICAL_DESIGN.md#10-delivery-interface-identity-and-operations) delivery, backups, watchdog.
- [KT §11–12](TECHNICAL_DESIGN.md#11-planned-redesign): what is planned (one engine with sector lenses, learning on a corrected target).

*Check yourself:* How do new ideas reach the portfolio? What happens if an email fails to send? What is planned vs already live?

## 7. If you want to see the code (optional)

Follow one evening, file by file:

| Step | File |
|---|---|
| Scheduler fires the 16:30 job | [services/scheduler/python/scheduler.py](../services/scheduler/python/scheduler.py) |
| Daily review compares forecast vs close | [daily_review.py](../core/intelligence/rl/workflows/daily_review.py), then [feedback_agent.py](../core/intelligence/rl/agents/feedback_agent.py) and [learning_mode.py](../core/intelligence/rl/learning_mode.py) |
| Portfolio pipeline runs after the review | [core/portfolio/pipeline.py](../core/portfolio/pipeline.py) |
| Rules decide EXIT/TRIM/ADD/HOLD | [core/portfolio/advisor.py](../core/portfolio/advisor.py) |
| Autopilot executes virtually | [core/portfolio/autopilot.py](../core/portfolio/autopilot.py) |
| AI writes the plain-English reason | [core/portfolio/narrator.py](../core/portfolio/narrator.py) |

Settings that change behaviour live in [config.yaml](../config.yaml).

## 8. What to skip

- `docs/superpowers/` and `docs/archive/`: frozen historical plans, not current truth.
- [PRODUCT_MAP.md](PRODUCT_MAP.md) §19: legacy and dead code.
- The audit ledgers and evidence receipts, unless you are checking one specific claim.
- [CODEBASE.md](../CODEBASE.md) and [AUTOPILOT_GUIDE.md](AUTOPILOT_GUIDE.md): reference books for later, not first reads.

## 9. One-page glossary

[KT §1 → Vocabulary](TECHNICAL_DESIGN.md#vocabulary) has the 13 terms you need (envelope,
dossier, price basis, idempotent…). Keep it open in a side tab.
