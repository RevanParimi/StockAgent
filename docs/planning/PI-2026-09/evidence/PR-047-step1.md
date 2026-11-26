# PR-047 receipt, step 1 — the measure for option B and the staged entry

Card [PR-047](../stories/PR-047.md), from the [B-32 read](B-32-read-2026-11-21.md) the owner asked
for on 21 Nov 2026. Profit-path step: **invest**. The owner decided that day: **option A** (buy
only when the model's own verdict is BUY too) after FIX-033, as step 2; **option B** (buy at or
below the price the analysis names) and a **staged entry** are measured first, here, and decided at
`PR-014-R1` (14 Dec).

**Lane: light** (step 1 only). Reason: the card's own lane for this step; a read-only measure that
changes nothing bought, sold, sized or graded and ships nothing in the app. Accepted as built
without a fresh-session review. **Step 2 is decision path** (`story/PR-047`, fresh-session review).

## 26 Nov 2026: the rules fixed, the read written and dry-run

Autopilot session `1126-1754-p5` (Sonnet), a `continue` on the code-server, from about 17:55 IST,
outside a push window. Base: `main` at `2c5bdda`, ten commits ahead of `origin/main` (`53461ab`).

**Nothing in production was read or changed.** Production is read only at the owner's word in the
same conversation (HANDOFF, START HERE), and the owner was away. No application code changed. The
read is `PR-047-S1` in STATE.

### Why the read waits for December, not only for the word

PR-017's dive lane holds the grades this measure reads. Its record is first written by the discovery
run of Sat 28 Nov, and the audit that night grades what has matured. Sessions counted with the
product's calendar: a 14 Nov dive reaches 10 sessions on 30 Nov, a 28 Nov dive on 11 Dec; a 24 Oct
dive reaches 30 sessions on 8 Dec, a 31 Oct dive only on 15 Dec. So a read on Sat 12 or Sun 13 Dec
has the most for `PR-014-R1`; from Tue 1 Dec it already has the 10-session figures up to 14 Nov.

### The rules, predeclared (fixed in this commit, before any read of the split)

1. **The model's own verdict of a dive:** the `verdict_shadow.jsonl` row of that stock and IST day
   whose model score is the dive's conviction, to the four decimals both keep (two for a dive seeded
   from a shelf event, which kept two), and whose band verdict agrees where known. Of several, the
   earliest (a run dives before it reviews). None: "unknown". Option A keeps BUY and STRONG BUY.
2. **The thesis:** the score history's analysis found the same way, else the shelf record's 800
   characters. The report counts which.
3. **An idea:** a dive the band rated BUY, at or above the conviction floor (0.55), that stood on the
   shelf and did not leave it that same day.
4. **The named price:** the highest price the thesis says to buy at, with ₹, Rs or INR, beside an
   instruction to buy or to wait for it. Targets, resistance, stops, invalidation, fair values, a
   fall the text only fears, a refused or "only if / unless" instruction and other people's buying do
   not count. More than 25% above or 60% below the dive's close: set aside. Every price taken is
   printed with its sentence.
5. **Overrides** correct an extraction against its sentence, never an outcome. Each is listed in the
   read's section with its sentence, and the report is shown with and without them.
6. **Option B:** the first close, from the dive lane's entry session to the horizon, at or below the
   named price and above the invalidation level (as recorded, else `entry_levels` on the dive's
   90-session window; a close at or below it is refused that day, as the product's buy check does),
   only while that dive could still be bought: within 30 days of it, up to the stock's next dive,
   before the day it left the shelf. Held to the horizon. Never bought is cash. A named price at or
   above the entry open buys as today.
7. **Staged:** half bought as today, half as B. It is halfway between them by construction, so it is
   not separate evidence.
8. **Excess:** the return less the Nifty over the auditor's whole window (cash earns zero against
   it). A bonus or split inside the window leaves the dive out of B.
9. **The decision for B** (a recommendation; the owner decides at `PR-014-R1`): on the ideas A keeps
   whose named price is below the entry open, at 30 sessions with 15 or more, else at 10 with 15 or
   more (provisional), else too few. d = B's excess less today's. **Placebo:** the same waiting rule
   on the ideas A keeps that name no price, with a limit below their entry open by the median
   distance of the named ones. mean(d) ≤ 0 and median(d) ≤ 0: keep A alone. Both above 0, a placebo
   of 15 or more, and mean(d) above the placebo's mean: **adopt B**. Anything else: mixed.
10. **Reported, not tested:** the band against the model over 60 days of analyses (with the floor);
    what A, B and A+B would have refused among the shelf ideas standing and the new positions bought
    since 16 Nov; excess by kind at 10 and 30 sessions.

What it cannot say: a dive is a what-if on the paper lane, not a purchase (the daily limit, sector
cap, target and cash are not applied); dives of one Saturday move together, so the report prints
the number of different dive days; the price B pays is a session's close; a recomputed invalidation
level uses today's `advisor.stop_atr_mult`; reading a price out of prose can be wrong, hence rule 5.
Three small gaps, known and left (the second check, below): a dive seeded from a shelf event can
take an earlier analysis of the same day with the same two-decimal score; an idea with no sector key
named is counted though nothing buys it until a re-dive names one; where a stock has block-deal rows
the recomputed invalidation level can differ slightly from the product's.

### The files

All in `analysis_data/pr047/` (ignored, on the code-server). Where they are missing, write them
again from this receipt.

| File | sha256 (first 16) | What it does |
|---|---|---|
| `probe.py` | `5155a5323de872af` | Runs in production, read-only. Prints JSON lines: meta, the 60-day verdict counts, shelf events, one line per dive the band rated BUY (or not recorded) with its shadow rows, analyses, grades, closes and levels, the autopilot's buys since 16 Nov (the default portfolio only), a summary and an end line |
| `split.py` | `d59188ea9824b116` | Runs on the code-server; the rules above; prints the sections |
| `make_fixture.py` | `c7dd5190aedf2e9f` | A made-up, production-shaped folder |
| `dry_run.sh` | `7ebc48131bcf59ce` | The probe through the production command form from an empty folder, then the split |
| `test_split.py` | `58976c41bb4ac118` | Hand-worked cases: price sentences, matching, B's arithmetic, the rule |
| `test_probe.py` | `d3a1ccaebe3d7078` | End to end on the fixture; an audit hook over the whole read |

### The dry run

`bash analysis_data/pr047/dry_run.sh <empty folder>`, twice: with the dive record, and without it
(as production is before 28 Nov, with a corrupt memo so a product warning fires).

| Case | Expected by hand | Printed |
|---|---|---|
| Five dives; one band NEUTRAL | four printed | yes |
| Verdict counts: five band BUYs in 60 days (one a Saturday review), three model NEUTRAL; an older row outside | 5 and 3 | yes |
| Shelf ideas standing since 16 Nov | 4; A refuses 2, B 2, A+B 4 | yes |
| New buys; a top-up, a manual buy, an earlier buy, a member's buy | 3 counted (one a watchlist idea, left unmatched); 1 top-up; the member's never read | yes |
| AAA: close 100, names ₹95, entry open 100, horizon 120, Nifty +2% | today +18.0%; B buys at 94: +25.7%; staged +21.8% | yes |
| DDD's seeded dive without a record: close 400, daily range 4% | invalidation recomputed 352 (12% below) | yes |
| The read itself | no file write, folder change, writable database or network call; the symbol cache not read | yes (audit hook) |

Extraction against the 22 real thesis texts already on the box from the 21 Nov read (10 ledger
reasons, which are the deciding dives' theses, and 12 latest analyses): on the 10, the three prices
the B-32 read names by hand (₹550, ₹54, ₹2,100) and none for the other seven; on the 12, three
more (₹3,974, ₹2,000, ₹1,558), each as its sentence says, and none for the other nine.

### The read: waiting for the owner's word

From the StockAgent folder on the code-server (`railway status`: carefree-renewal):

```text
railway ssh "cd /app && echo $(gzip -9c analysis_data/pr047/probe.py | base64 -w0) | base64 -d | python -B -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'" > analysis_data/pr047/read_<date>.txt 2> analysis_data/pr047/read_<date>.err
PYTHONPATH=.:src .stockai/bin/python analysis_data/pr047/split.py analysis_data/pr047/read_<date>.txt > analysis_data/pr047/split_<date>.txt
```

- **When:** from Tue 1 Dec; best Sat 12 or Sun 13 Dec, before `PR-014-R1`. Any time except
  16:30–17:10 IST on a weekday and Saturday 12:00–15:00 IST. The command carries about
  7,800 characters of encoded text; the output is expected at a few MB (not measured).
- **The owner's choice:** say "run the PR-047 measure" in a session on the code-server.
- **Then:** read section 6 against its sentences, write any overrides to
  `analysis_data/pr047/overrides.json`, run the split again with `--overrides`, and record both,
  labelled read, code or inference.

### The independent check (Opus, effort xhigh)

A fresh subagent reviewed the code against the product's own modules, ran its own sentences and an
audit trace, and read nothing in production. It was asked twice.

**First pass: "not yet".** Fixed, each with a test:

| Finding | Fix |
|---|---|
| High. The probe could write to production: importing the product attaches a log archive (a warning would store a row in `data/telemetry.db`), and reading the symbol cache can rewrite it. Reproduced: the new audit-hook test failed on the old probe | Logging disabled before the imports; the cache emptied; the test passes (BACKLOG B-41) |
| High. B ignored the invalidation level for every dive that kept none, which is every seeded dive | Recomputed with `entry_levels`; the report counts which, and the named prices B can never buy |
| Medium. B could buy after the product no longer would | The buying window (rule 6) |
| Medium. Refused, feared or third-party prices were read as buy prices; common wordings were missed | Rules tightened; every price taken is printed; its sentences are now tests |
| Medium. The rule mostly measured the market: waiting beats buying in any falling month | The placebo and the dive-day count (rule 9) |
| Medium-low and low. Thesis source unreported; unshelved dives counted as ideas; watchlist buys matched to an old dive; a review could stand in for a dive's analysis; one bad row could end the read | Reported, restricted, kept apart, exact matching with the earliest row, and notes instead of a crash |

**Second pass: "safe to run in production"; fit to inform 14 Dec once one line changed.** Done: a
price after a clause break is no longer taken (medium), plain instructions the stricter rules had
missed are found again, and a close below the invalidation level now refuses that day only. The
three gaps above are left: each is rare, and fixing the second needs a field no seeded dive kept.
**These last changes were not reviewed a third time;** they are covered by tests that include both
passes' sentences, and both dry runs gave the same figures.

### Choices taken in this phase

- Waited on nothing: the read is dated (above) and step 2 does not need it, since the owner decided
  option A on 21 Nov whatever step 1 shows. Step 2 is next.
- Reused PR-017's grades (entry at the next open, corporate actions handled) rather than grading
  again, as the card says "with PR-017's lanes".
- B is measured as a limit buy at the named price, without the band's lower edge, which a price far
  below the close would otherwise make unreachable; the live design of B, if adopted, must say so.
- The probe switches off the product's log archive and symbol cache during the read (BACKLOG B-41).

### Checks in this phase

- `.stockai/bin/python -m pytest -q analysis_data/pr047/`: 142 passed. Both dry runs: the figures in
  the table.
- Full suite through `scripts/ci/guarded_suite.py` on this phase's tree (26 Nov, 18:42–18:51 IST):
  6,995 passed / 5 skipped / 1 xfailed in the main step and 58 passed in the browser step, 0 failed;
  peak anon 2,178 MB in the browser step (the guard stops at 2,400); nothing left running.
- `scripts/docs/check_kt_docs.py`: errors []. `archive_done_tasks.py --check`: nothing to move.
- Changed-file manifest (tracked): this receipt (new), STATE.json, HANDOFF.md, HANDOFF-archive.md,
  BACKLOG.md. Base `2c5bdda`; records and nothing else, so no diff digest of code.
