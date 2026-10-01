# SA-003 enforce decision — 2026-10-01

- **Story:** [SA-003](../stories/SA-003.md). The owner delegated this decision to Claude on
  2026-09-27; the rules are under SA-039-P3's `then_decision` in [STATE](../STATE.json).
- **Made:** Thu 1 Oct 2026, about 10:20–10:40 IST, after [SA-039 P3](SA-039-activation-2026-09-26.md)
  passed. Live deploy `14d13162` (`2c632e2`, 30 Sep 22:26 IST); no restart since.
- **Decision: NO-GO. `decision_gate.mode` stays `record`;** the Railway variable is not set.
  Two fixes are routed: [FIX-003](../stories/FIX-003.md) (bank fundamentals) and
  [FIX-002](../stories/FIX-002.md) (scheduled tickers resolved by an LLM). The decision is
  taken again after both are deployed and a new window has been measured (below).

## In one example

YES Bank published its June-quarter results; they are on file (revenue ₹4,655.98 Cr for the
quarter ending 30 Jun 2026). A bank's income statement has no "operating income" line, so the
fundamentals fetcher fills that line with zero and marks the whole section `fallback`. The gate
treats `fallback` fundamentals as missing essential data and abstains. Under `enforce`, YES Bank
would get **no October forecast**, every October review would be skipped, and an ADD would be
blocked, although its data is fine. The same happens to IDFC First, RBL and Federal Bank, every
day. Enforcing now would switch learning off for 4 of the 20 tickers for reasons that are not
real.

## The rules, applied

**Wait conditions** (all must hold before a go):

| # | Condition | Result |
|---|---|---|
| 1 | SA-003 accepted and deployed in record mode | **Met.** Accepted 27 Sep; deploy `0106fc89` 27 Sep 09:27 IST; every later deploy kept `record` (no row in the window reads `SKIPPED`). |
| 2 | P1–P3 passed | **Met.** P3 passed today (activation record). |
| 3 | Live envelopes carry `data_gate` | **Met, by inference.** The October envelopes were made at 09:00 under SA-003 code; 6 forecasts logged an abstaining gate, so the gate was computed for the cohort. `_build_daily_forecasts` writes `data_gate` on every row from the report's gate. The stored field was not read (a volume read). |
| 4 | At least 5 scheduled review days of record-mode rows | **Not met.** 3 days: 28, 29 and 30 Sep. Today's 16:30 review is the 4th; Fri 2 Oct is an NSE holiday; Mon 5 Oct would be the 5th. |
| 5 | No other policy flag changed in the window | **Met.** No flag changed. Code deploys landed (SA-007, SA-008, SA-009) and the roster changed (TATAMOTORS disabled, TMPV added, 1 Oct 00:30), which are not policy flags. |

Condition 4 alone means WAIT. **The no-go triggers are already met, and by a structural cause**
that more review days cannot change, so the outcome is NO-GO rather than WAIT: a wait would
only re-decide on 6 Oct against the same banks.

**No-go triggers:**

- **(a) More than 20% of analyses would abstain: MET (32%).** Counted as abstaining analyses by
  distinct run id against the data-health rows, excluding the pre-gate forecast rows:

  | Window | Analyses | Abstaining | 4 banks, `fundamentals=fallback` | Others |
  |---|---|---|---|---|
  | 28 Sep review (grades 25 Sep) | 19 | 5 | 4 (YESBANK, RBLBANK twice: review and re-forecast, FEDERALBNK) | TATAMOTORS: fundamentals empty, 1/9 dimensions |
  | 29 Sep review (grades 28 Sep) | 19 | 8 | 4 (YESBANK, IDFCFIRSTB, RBLBANK, FEDERALBNK) | OLAELEC 1/9 and OLECTRA 2/9 dimensions; TATAMOTORS fundamentals empty; TVSMOTOR resolved to TVSMOTORS, fundamentals empty |
  | 30 Sep review (grades 29 Sep) | 20 | 6 | 5 (YESBANK, IDFCFIRSTB, RBLBANK twice, FEDERALBNK) | TATAMOTORS: identity (SA-008) |
  | 1 Oct 09:00 monthly forecast | 20 | 6 | 4 (YESBANK, IDFCFIRSTB, RBLBANK, FEDERALBNK) | OLECTRA 2/9 dimensions; TATAELXSI resolved to TATAMOTORS: identity |
  | **Total** | **78** | **25 (32%)** | **17 (22%)** | 8 |

  Without the two identity rows it is 23 of 78 (29%). The 4 banks alone exceed 20%.
  The pre-gate rows (`forecast_row`, status unknown: 19, 18 and 18) are excluded.

- **(b) A spot check of 5 abstain rows finds one whose data was fine: MET (3 of 5).** Identity
  rows were excluded, as the rules require. Each row was checked against its health line and
  the source:

  | Row | Gate reason | Health line | Source | Verdict |
  |---|---|---|---|---|
  | YESBANK, 1 Oct 09:06, forecast, run `63ddeb85` | essential fundamentals=fallback | 8 live, 1 fallback, dimensions 6/6 | local `get_financials`: newest quarter 2026-06-30, revenue present, `missing_rows ['operating_income']` | **false abstain** |
  | RBLBANK, 30 Sep 16:42, review re-run, run `2ce1b973` | essential fundamentals=fallback | dimensions 6/6, fundamentals:fallback | same structure locally (quarter 2026-06-30, revenue ₹2,577.29 Cr) | **false abstain** |
  | FEDERALBNK, 29 Sep 16:54, review re-run, run `39819493` | essential fundamentals=fallback | dimensions 6/6, fundamentals:fallback | same structure locally (quarter 2026-06-30, revenue ₹4,405.53 Cr) | **false abstain** |
  | OLECTRA, 1 Oct 09:12, forecast, run `6dcd9387` | dimensions scored 2/9 < 50% | 10 sections live, 0 failed; the aggregator dropped 7 of 9 dimensions as errored | data arrived, the analysis did not | correct abstain (a verdict on 2 of 9 dimensions is what the floor stops; why 7 agents errored is not visible at INFO and was not investigated) |
  | TVSMOTOR, 29 Sep 16:45, review re-run, run `0248cc4e` | essential fundamentals=empty | the run analysed `TVSMOTORS` | LLM resolution chose another symbol | correct abstain about what was analysed; the defect is the resolution ([FIX-002](../stories/FIX-002.md)) |

  PAYTM is in the same banking sector but is not a bank. It reports operating income, and its
  fundamentals were never unusable in the window (locally: `missing_rows []`). That isolates
  the cause to the bank statement format.

## Reported inputs (F1, F2)

- **F1: 6 of the 20 October envelopes carry an abstaining gate.** They are YESBANK, IDFCFIRSTB,
  RBLBANK, FEDERALBNK, OLECTRA and TATAELXSI. Under `enforce`, none of these 6 would have an
  October envelope. Only a restart's self-heal would retry them (SA-009 now retries every ticker
  in its own store; same-month retry is SA-036). Their reviews would return `no_envelope` and
  their ADDs would stay blocked all month.
- **F2: 0 `actual_close` rows** in the three review days. So no session close was replaced with
  an earlier bar in this window (the SA-012 case did not occur).
- **SA-008 interplay.** TATAMOTORS was disabled at 00:30:43 IST today, so `enforce` would not
  quarantine a scheduled ticker. SA-008's identity gate did catch a real error today:
  TATAELXSI's forecast was built on a TATAMOTORS analysis (below). Under `enforce` that ticker
  would have had no envelope, which is the right outcome.

## Found while measuring: a scheduled ticker analysed as another company

At 09:16:42 the IT orchestrator resolved **TATAELXSI to TATAMOTORS** ("Tata Motors Ltd"):
`_resolve_ticker` sends a scheduled ticker to an LLM when the sector's static `TICKERS` list
does not hold it. The run fetched TATAMOTORS data, much of it 404, and produced a SELL. The
forecast then saved **TATAELXSI's October envelope from that analysis**. From code, its base
close is TATAELXSI's own (`_fetch_actual_close(ticker)`), but its verdict, agent scores and
assumptions belong to the other company. The same path:

- resolved TVSMOTOR to `TVSMOTORS` on 29 Sep;
- named HAPPSTMNDS "Happy Smile Digital Ltd" today, and its news section came back empty;
- returned non-JSON on 29 Sep (the P2 note).

SA-026 recorded this risk on 29 Sep and holds the long-term fix. The narrow fix is routed as
[FIX-002](../stories/FIX-002.md), with the TATAELXSI envelope's regeneration after its deploy
(an owner-authorised production action). SA-039 `observe` keeps the stored weights unchanged
meanwhile.

## What happens next

1. **Fix first.** FIX-003 makes a bank's statement, which has no operating-income line by
   format, read as complete when its revenue and quarter are present. It keeps the zero out of
   the prompt. FIX-002 makes a scheduled ticker resolve to itself.
2. **Measure a new window.** After both are deployed: at least 5 scheduled review days, with the
   banks' and TATAELXSI's envelopes regenerated or the 1 Nov forecast made under the fix.
   Otherwise the October rows keep their abstaining gate.
3. **Decide again by the same rules.** If the rate is still above 20% without the banks (for
   example OLAELEC or OLECTRA losing most dimensions), that is a separate cause to fix first.

**Rollback:** nothing to roll back; the mode did not change.

## Sources and method

- **Railway logs, read-only.** `railway logs <deploy> -n 5000 --json`, for deploys `b3fb00dd`
  (28 Sep), `f2e23722` (29 Sep), `650bb98c` (30 Sep) and `14d13162` (1 Oct). Each gate line is
  printed by the same `record_gate_decision` call that appends the `decision_gate.jsonl` row,
  one line per row. The stage was inferred from the reason text, because the log line does not
  carry it. Data-health log lines count the analyses.
- **Not read:** `data/logs/decision_gate.jsonl`, `data_health.jsonl` and the envelopes on the
  volume, because Claude's `railway ssh` is blocked. The log lines are the measured evidence;
  the stored fields are inferred from code.
- **Local reproduction:** `get_financials` for the 4 banks and PAYTM, 1 Oct about 10:30 IST,
  public yfinance data. This was not a test and wrote nothing.
- **Scripts and raw output:** ignored `analysis_data/sa039/` (`p3_logs.py`,
  `p3_gate_reasons.py`, `p3_health_lines.py`, `review_gate_rows.py`, `olectra_errors.py`, and
  their `_2026*` outputs). They print counts, tickers, reasons and run ids only.
