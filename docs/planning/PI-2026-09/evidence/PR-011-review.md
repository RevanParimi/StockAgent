# PR-011 review receipt — promoter and insider trades, pledges, shareholding changes

## Fresh re-review of rework 1: ACCEPTED (2026-10-23)

**Phase:** fresh-session re-review, a new conversation opened with "continue" (23 Oct, about
19:23–20:00 IST, session `stockagent-main-62` [c18e9a]). The implementation was session
`stockagent-main-74`, review 1 `stockagent-main-5b`, rework 1 `stockagent-main-b1`. This
conversation is none of them and did not read them. All 18 peer sessions were idle at the start
and before the bookkeeping (ListAgents).

**Verdict: ACCEPTED** for the reviewed revision (below). F1 is resolved: each trade counts once and
only in the window of its trade day, and the feed stores a revision as a neutral, low event that
says what it is. F2, L1 and I1 are resolved. Two new **low** findings remain, both latent on NSE's
live list of 23 Oct: RR-L1 is routed to a new card, FIX-014, and RR-L2 becomes a KT limit at
commit time. One low test gap (T1: two edge cases the story file does not pin, though the code
handles them) goes into FIX-014's acceptance criteria. Nothing else was found.

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called, no message was sent and **no NSE call was made**: this review used the recorded
fixtures and the implementer's local cache of NSE's public list (ignored
`analysis_data/pr011_rework1/live_cache.json`). The tracked files this review changed are STATE,
HANDOFF, this receipt and the new card `stories/FIX-014.md`. The reviewer's scripts and outputs are
in the ignored `analysis_data/pr011_rereview/`.

### In one example (F1, recorded NSE filings)

Saturday's discovery run for the 28 days to 23 Oct (window 25 Sep–23 Oct) lists, among others:
PATINTLOG `3886` and its identical revision `3893`; HTEL `3762`, `3945` and the revision `3922`
that repeats `3945`'s four trades and adds one; NAUKRI's revision `3962` of a director's ₹68.0
crore sale traded on 18–20 Aug; and KARURVYSYA `4038`, three persons' identical sales.

| Company | Reviewed code (review 1) | Now (worked by hand) |
|---|---|---|
| NAUKRI | −68.0478416, the lowest | **0**: the trade's last day, 20 Aug, is before 25 Sep |
| PATINTLOG | +0.0142428 (counted twice) | **+0.0071214**: +₹36,62,165 − ₹35,90,951, once |
| HTEL | 0.8585 (ten trades, but only the promoter's counts) | **0.8585**: six trades; the promoter's ₹85,85,000 |
| KARURVYSYA | −0.230769 | **−0.230769**: 3 × ₹7,69,230; an original is never deduplicated |

The re-reviewer's own harness (RR1, below) reproduces each value through the real refresh, the
real cache and `sig_insider_buying`. As a feed event, NAUKRI's revision is neutral and low and its
sentence ends "It revises an earlier filing, so these trades may have been reported before and are
not read as new trading."

### Review input verified

- **Manifest:** [PR-011-manifest.json](PR-011-manifest.json), sha256 `0e1ba470…092615`, 40 files.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches, at the start and at the end.
- **Rework diff:** `145b5337a877a437f2bdb08a05e24d39350d3db67ef8c0e15c5815352a12bd89`, 138,494
  bytes, 14 paths. It was recomputed by the re-reviewer's own
  `analysis_data/pr011_rereview/rr_digest.py`, which rebuilds review 1's input in its own folder
  from HEAD plus the reviewed diff (`939890c3…`). All 32 rebuilt files match review 1's manifest
  `2b264207…`. The bytes are identical to the implementer's `rework1.diff` once the rebuild
  folder's name is normalised in the 14 diff headers that carry it.
- **Cumulative diff:** `c9f16799fb2e688d88a6f07f4d99533f18f1cab3ad76525b6684137b993a1ca8`,
  328,750 bytes, 39 paths, against HEAD `16e31b5`. Recomputed at the start and at the end.
- Outside the manifest, the working tree holds only bookkeeping (STATE, HANDOFF, the receipts and
  the manifest) and the owner's `docs/README.md` line. No review edit touched a reviewed path.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| F1, discovery: each trade once | **Holds** | `insider.py:143-168`. Filings are sorted by dissemination time. An original's trades are all added, and each revision trade replaces at most one earlier trade (`taken`). The four required fixtures give the values above, in the story's tests and in RR1. On the live cache, 12 revision trades: 9 replaced an earlier trade (8 agreeing on all five fields), 3 were new. |
| F1, discovery: the window of the trade day | **Holds** | `insider.py:167`: last day, else first, from `window_from` to `window_to`, both included (RR5 checks the edges). The list is still filtered by dissemination, so nothing disseminated after the screen day is read (RR2: on 7 Oct NAUKRI's 8 Oct filing is not listed). NATCOPHARM's live filing `3989` has a first day typed as 2016 and a last day in 2026; the last-day rule counts it correctly. |
| F1, feed: no second unqualified event | **Holds** | `disclosures.py:354-369`: a revision (NSE's list or the XBRL flag) is neutral and low, with the revision sentence in place of the 75% or "no reason" note. No reader uses `facts.market_net_inr`, which keeps the full figure: events reach readers only through `GET /events/{symbol}`. |
| Hard-review Q1: the disclosure date is "when we could have known" | **Holds** | `published_at` is still NSE's dissemination time, and the trade days are in `occurred_*`. Discovery lists by dissemination and counts by trade day, and I1 refuses a cache newer than the screen day. |
| Hard-review Q2 / F2: no more confident than the event | **Holds for sales; RR-L1 for a mixed window** | Above 75% a promoter-group sale counts nothing in discovery, as the event calls it neutral. Directors still count. A failed promoter-share read leaves the signal unavailable and named. The promoter group's purchases still count, though, so a purchase and sale in the same window scores the purchase alone (RR-L1). |
| L1, a stale pledge row | Holds | `guards.py:74-76,120`: a quarter more than 200 days before the latest session, or none, is unknown. The `date` column was already used by the guard. |
| I1 | Holds | `insider.py:284`. |
| Unavailable is never neutral | Holds | A cache without `net_inr`, an undated directional trade, or an unread promoter share each make the signal unavailable and named. A cache line from the earlier format is read again. |
| Fixtures | Faithful | The 7 new fixtures (6 list rows in one file, 6 XBRLs) match review 1's own extraction from NSE (`revision_pairs_out.json`), parsed here by `parse_pit_xml`: symbol, kind, `prevAppId`, dissemination time, and each trade's group, action, market flag, shares, value and first day, 6 of 6 filings, 0 mismatches. Names, the signatory and a director's DIN are replaced. The cache stores no name or category text (RR1). |
| Documentation | Describes the reviewed behaviour | KT sections 4 and 8, guide 02-L ("Apart from such a revision, nothing appears twice") and 06-I, and CODEBASE. `check_kt_docs` gives errors `[]`. The PDF (54 pages) is built from KT source `6e9645ae…`, the manifest's KT. |

### The re-reviewer's own cases

`analysis_data/pr011_rereview/test_rr_pr011.py` uses a separate harness: the insider module's own
seams are faked here, not the story's `FakeNse` behind the fetchers. It runs with the hermetic hooks
(`conftest.py`). **6 passed.**

- **RR1:** all six recorded revision-case filings and KARURVYSYA in one list, on 23 Oct. Expected
  values are worked by hand (table above). Promoter shares are read for KARURVYSYA and PATINTLOG
  only, the companies with an in-window promoter sale. The cache holds no name.
- **RR2 (issue time):** on 7 Oct NAUKRI's filing is not listed and no document is read. On 8 Oct
  it is read and counts 0, and it would count 0 even as an original.
- **RR3 (adversarial, RR-L2):** a revision of an August purchase of 10,000 shares replaces an
  unrelated in-window purchase of 10,000 shares made on 15 Oct. Today that loses the 15 Oct
  purchase: the net is 0, while the contract implies +₹10 lakh. The test asserts today's value.
- **RR4 (adversarial, RR-L1):** PATINTLOG's recorded pair with a supposed 78% promoter holding.
  The event is positive and low, with a net of +₹71,214. Discovery scores +0.3662165 crore, the
  purchase alone. At 58.72% it scores 0.0071214.
- **RR5:** the window's edges are the trade's last day, both ends included.
- **RR6:** a revision restating one earlier purchase and adding two identical ones gives three
  trades; a revision of two identical trades with no earlier match gives two.

### Findings

| ID | Severity | Location | Trigger | Observed | Expected | Disposition |
|---|---|---|---|---|---|---|
| F1 | (high, review 1) | — | — | Resolved: see the table above, RR1, RR2 | — | **Resolved** |
| F2 | (medium, review 1) | — | — | Resolved for sales: discovery leaves out a promoter-group sale above 75%, as the event calls it neutral | — | **Resolved**, with RR-L1 |
| L1, I1 | (low, info) | — | — | Done as asked | — | **Resolved** |
| **RR-L1** | Low (confirmed by reproduction; latent on live data) | `core/discovery/insider.py:175-177` | A company above 75% whose promoter group both bought and sold in the market in the window, for example an inter-se transfer through the market | The sales are left out and the purchases kept. PATINTLOG's pair at 78% scores +₹36.6 lakh while its event says +₹71,214 (RR4). DALBHARAT's same-day ₹17.0 crore buy and sale in one filing (live, 1 Oct) would score +17.0, the top of the signal, while its event is neutral. | No more confident than the event in either direction: above the cap, the group's net counts only when positive, `max(0, purchases − sales)` | **Follow-up: [FIX-014](../stories/FIX-014.md)** (P2, 1 point, queued after PR-012 at the end of the product track; move it ahead if guide 06-I's export shows a case). On 23 Oct, 3 companies had promoter purchases and sales (35.0%, 55.84%, 49.39%) and none of the 17 with a promoter sale was above 75%. KT section 8 limit at commit time. |
| **RR-L2** | Low (confirmed by construction; no live effect) | `core/discovery/insider.py:158-162` | A revision whose original is outside the list window, of a trade with the same action and share count as an unrelated trade in the window | The unrelated trade is replaced and stops counting (RR3). On the live cache 1 of the 9 replacements agreed only on person group and market: NAUKRI `3963`, an employee's off-market move, which changes no net. | Each trade once | **KT section 8 limit at commit time** (text below). The implementer's D16 trades this against double counting a revision that corrects both value and days, so no code change is asked. |
| T1 | Low (test gap; the code is correct) | `tests/unit/test_disclosures_pr011.py` | Re-reviewer mutants X02 (a trade on the window's last day dropped) and X03 (a revision's second identical new trade replaces the first) | Both survive the story file; RR5 and RR6 catch them | The story file pins both | **Follow-up in [FIX-014](../stories/FIX-014.md)**'s acceptance criteria (the same file) |
| I2 | Info | `core/events/disclosures.py:383` | NATCOPHARM `3989`'s first day typed as 12 Oct **2016** by the filer | An event would read "on 12 Oct 2016 to 13 Oct 2026", as the filing says. Discovery uses the last day, so it counts correctly. | — | None (the filing's own figure) |

Decisions D16–D22 are upheld. D19 holds for sales; RR-L1 refines it for a mixed window.

### Mutants

The re-reviewer's own 9 mutants (`analysis_data/pr011_rereview/rr_swap_plugin.py`, in memory,
`run_rr_mutants.py`) on the story file: **7 of 9 caught**, base 108 passed. X01 (first day
excluded), X04 (discovery reads only the XBRL's revision flag), X05 (the cap drops promoter
purchases too), X06 (no trade-day window), X07 (a large revision not low), X08 (pledge age from
the first session) and X09 (a same-day cache refused) are caught. X02 (a trade on the window's
last day dropped) and X03 (a revision's second identical new trade replaces the first) survive
it. The reviewer's own cases catch both (RR5, RR6; `run_rr_cases_under_mutants.py`), so this is
test gap T1. X02 can matter only on a weekday manual run: the weekly run is a Saturday, when no
trade is made. The implementer's 29 rework mutants were not
re-run; their record (29 of 29 caught) is in the implementation receipt.

Review 1's repro (`analysis_data/pr011_review/test_review_repro.py`, which asserts the defects):
3 of its 4 tests now fail, each on its defect line with the CONTRACT value (BUYERCO 4.5; the
revision is not positive; neutral and low). The fixture check passes.

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), with the hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe analysis_data/pr011_rereview/rr_digest.py start` (and `end`) | rework `145b5337…` after normalising the folder name, cumulative `c9f16799…`; the 32 rebuilt files match `2b264207…`; HEAD `16e31b5` |
| `scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-011-manifest.json` | 40 files, mismatches `[]` (start and end) |
| `pytest -q -p no:cacheprovider tests/unit/test_disclosures_pr011.py` + the 10 other changed test files | **386 passed** in 72.5 s |
| `pytest -q -rfEs -p no:cacheprovider -o console_output_style=count tests` (CI's command) | **5,672 passed, 12 skipped, 1 xfailed, 0 failed** in 20 min 5 s; `find data -newer suite_marker`: no file |
| `pytest analysis_data/pr011_rereview/test_rr_pr011.py` (hermetic conftest) | **6 passed** (hermetic header present) |
| `analysis_data/pr011_rereview/run_rr_mutants.py` | 7 of 9 caught; X02 and X03 survive |
| `analysis_data/pr011_rereview/run_rr_cases_under_mutants.py` | base 6 passed; X02 caught by RR5, X03 by RR6 |
| `pytest analysis_data/pr011_review/test_review_repro.py` (review 1's repro) | 3 failed (each on its defect line, CONTRACT values), 1 passed |
| `analysis_data/pr011_rereview/rr_live_matches.py` (the implementer's local live cache) | 12 revision trades (9 replaced, 3 new); 3 companies with promoter purchases and sales; 17 promoter shares, none above 75% |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | errors `[]`; PDF 54 pages; source `6e9645ae…` |

**Not exercised:** NSE itself (no call; the fixtures were compared with review 1's extraction);
production (nothing read); the implementer's 29 rework mutants (not re-run).

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Parsers turn recorded fixture payloads into the documented events, with the source's date | **Met**, revisions included |
| Promoter 52.1% → 50.6% emits one `ownership` event | Met (unchanged; story test passes) |
| An unavailable source gives "unavailable", never neutral; a deleted weight is gone from config and ranking | Met |
| The production probe's result per source is in the receipt, sanitized | Met (PR-011-P1, 8 of 8; the rework adds no endpoint) |
| Hard review: disclosure date against trade date | **Met** for originals and revisions |
| Hard review: a float-rule sale | **Met** in events and discovery (RR-L1 for a mixed window, follow-up) |
| Review 1's rework list | F1 met (fixtures, feed rule recorded as D18, KT 4 and 8, guide 02-L); F2, L1 and I1 done; evidence complete |
| Living docs and human test cases | Describe the reviewed behaviour |

### Commit-time edits (with PR-011's commit, at the owner's word)

In addition to the implementation's (KT header "Code inspected" bump, KT section 12's PR-011 row
Done, PDF rebuild, guide 02-L and 06-I status lines):

1. **KT section 8, Limits:** after the bullet "Two originals with the same trade count twice. …",
   add:
   - "- A revision's trade replaces an earlier trade with the same action and share count even when
     nothing else agrees. So a revision of an old trade can replace an unrelated trade in the
     window, which then stops counting. On 23 Oct, 9 revision trades replaced an earlier one; 8
     agreed on person group, market, value and days, and the ninth, an employee's off-market move,
     changed no net."
   - "- Above 75%, a promoter-group sale counts nothing even when the group also bought in the
     window, so a purchase and a sale through the market (an inter-se transfer, say) score as the
     purchase alone. On 23 Oct no company with both was above 75%. **Planned:** FIX-014."
2. **KT section 12:** after the FIX-013 row, add
   `| [FIX-014](planning/PI-2026-09/stories/FIX-014.md) | Above the 75% cap, a promoter wash must not score as insider buying | Open | 8 Discovery | PR-011 |`.
3. Rebuild the PDF and run `check_kt_docs`.

**Applied** with the commit at the owner's word (23 Oct about 20:10-20:25 IST): `ffa012b` holds the 40 reviewed files, and the docs commit after it makes these edits. It also puts KT section 11's feed
line in present tense and adds FIX-014 to the PI README.

### Decision and state

**ACCEPTED.** STATE: PR-011 `done`; `production_verification` stays `pending_deployment` (PR-011-P1
passed; nothing is pushed). `active_task` null. **`next_task: PR-009`**, the first planned `todo`
whose dependencies are done, in a new conversation. FIX-014 is added as `todo` (P2, depends on
PR-011), after PR-012 at the end of the product track (FIX-006 stays last, the owner’s call). **Push PR-011 only at the owner's word**, in a job-free window, with
the commit-time edits above. After the deploy: guide 02-L for five trading days, 06-I after the
first Saturday.

## Fresh review: CHANGES REQUESTED (2026-10-23)

**Phase:** fresh-session review, a new conversation opened with "continue" (23 Oct, about
16:17–16:40 IST, session `stockagent-main-5b`). PR-011 was implemented in session
`stockagent-main-74`; this conversation is not that one and did not read it. All peer sessions
were idle at the start and before the bookkeeping (ListAgents).

**Verdict: CHANGES REQUESTED.** One high finding is unresolved (F1): a *revised* insider filing
is read as a new trade. The discovery signal counts the same trades twice, or counts a months-old
trade as recent, and the feed stores a second event that does not say it is a revision. This is
the card's first hard-review question ("when we could have known") failing for revisions, shown on
NSE's live list. There is also one medium finding (F2), one low (L1) and one info item (I1). Every
other part of the contract held: originals are dated correctly, the 75% rule holds for events, an
unavailable source is never scored neutral, `mf_holding` is gone, and the pledge guard reads the
right figure.

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called and no message was sent. To measure revisions, NSE's public insider list was read 3
times from this laptop, plus 21 public insider XBRLs. The only tracked files this review changed are
STATE, HANDOFF and this receipt. The reviewer's scripts and outputs are in the ignored
`analysis_data/pr011_review/`.

### In one example (F1, live data, 23 Oct)

On **8 Oct at 17:27:52** NSE disseminated NAUKRI's insider filing `3962`, a "Revision"
(`prevAppId` 47977, an id from NSE's old insider endpoint, so the original was filed in August).
Its remark says a discrepancy was found in the pre-trade and post-trade shareholding. Its XBRL
holds one trade: a director sold 5,00,000 shares in the market for ₹68.0 crore on **18 Aug 2026**.

- **Discovery, Saturday's run (window 26 Sep–24 Oct):** NAUKRI's `insider_buying` is **−68.0**
  (₹ crore). That is the largest value in the window, so NAUKRI ranks last on this signal, for a
  trade made two months earlier and disclosed in August.
- **Feed, had NAUKRI been tracked on 8–15 Oct:** one `insider` event, negative, high, dated 8 Oct
  17:27:52: "Directors and key managers sold 5,00,000 shares worth ₹68.0 crore in the market on 18
  Aug 2026. Filed with NSE on 8 Oct 2026. The filing gives no reason for the sale." Nothing in it
  says this revises an August filing. Only `facts.revision` is true, and no reader looks at it.

A second case, PATINTLOG. Filing `3886` (Original, 1 Oct 17:11:45) and filing `3893` (Revision,
1 Oct 18:23:57, no `prevAppId`) hold the same two promoter trades on 23 Sep: 2,63,832 shares
sold for ₹35.9 lakh and 2,63,832 bought for ₹36.6 lakh. The remark says only the date of filing
was corrected. Discovery adds the +₹71,214 net twice, and the feed would store two events for one
pair of trades.

### Review input verified

- **Manifest:** [PR-011-manifest.json](PR-011-manifest.json), sha256 `2b264207…c09c09`, 33 files.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches, at the start and at the end.
- **Diff:** sha256 `939890c3065256de7c91b21eb689b693b1062942420ec6470cd857765d47eccd`, 228,612
  bytes, 32 paths. This matches the implementation receipt. It was recomputed independently by
  `analysis_data/pr011_review/rdigest.py` (same recipe, HEAD `16e31b5`), at the start and at the
  end. The implementer's `pr011.diff` was not overwritten.
- No review edit touched a reviewed path.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| Hard-review Q1: the disclosure date, not the trade, is "when we could have known" | **Holds for originals; fails for revisions (F1)** | `disclosures.py:317,382`: `published_at` is `broadcastDateTime`, and `occurred_*` are the XBRL trade days. SAST uses `timestamp`, Reg 31 `broadcastdate`, the pattern `broadcastDate`. The 10-minute rule is at `:397`. A revision gets a new `appId`, so `insider_id` (`:406`) treats it as a new filing. |
| Hard-review Q2: a float-rule sale is not labelled more confidently than the data allows | **Holds for events; not applied in discovery (F2)** | `disclosures.py:339-347`: above 75% the sale is neutral, at most medium, and names the rule. At exactly 75.0% or unknown, the sentence says "no reason". When the list fails, filings wait (`feed.py:433-438`). `insider.py:124` stores the plain net. |
| Unavailable is never neutral | Holds | Feed: a failed endpoint or document stores nothing, is named and makes the run `partial`. Discovery: `usable_insider_trades` is all or nothing. The ranking test's composites (1, .75, .5, .25) re-derived by hand equal momentum alone. A neutral 0.5 would give .875/.6875/.5/.3125. |
| `mf_holding` deleted | Holds | Absent from `config.yaml`, the `base.py` fallback, the signal slots and the tests. The weights sum to 0.95, and the screen renormalises. |
| The card's ownership fixture | Holds | 52.1 → 50.6 gives one negative, medium event dated 21 Oct 10:01:23 and occurred 30 Sep. 0.99 gives none and 1.00 one. MARUTI's real quarters give none. |
| The pledge guard | Holds; staleness is L1 | `percPromoterShares` = pledged ÷ promoter holding. It was re-checked on the market list: A2Z Infra 99.68. More than 25 rejects; zero rows, several rows or a failed call degrades. |
| The classifier cannot write disclosure categories | Holds | `classify.py` validates against `CLASSIFIER_CATEGORIES`, the original nine. |
| Boundaries and safety | Holds | Documents come only from `https://nsearchives.nseindia.com/`. A DTD or entity is refused before parsing. Insider and pledge events name no person. The ownership file name comes from `EventStore.path`. Tests use `FakeNse` behind the real fetchers, with the hermetic boundary on. The cycle tests fake the new stage, and the guard tests fake `pledge_snapshots`. No hidden real transport was found. |
| Documentation | Describes the implemented behaviour | KT sections 4, 8 and 9, CODEBASE, and guide 02-L and 06-I. `check_kt_docs` gives errors `[]`, so the PDF matches its source. Guide 02-L requires "Nothing appears twice across the ten runs", which the first revision in a held stock would break (F1). |

**Revisions measured on NSE's live list** (`analysis_data/pr011_review/revisions_probe.py`,
`revision_pairs.py`, with each XBRL parsed by PR-011's own `parse_pit_xml`/`market_net`):

| Window | Filings | Revisions | With `prevAppId` |
|---|---|---|---|
| 26 Sep–23 Oct 2026 | 308 | 6 (NAUKRI ×2, HTEL, PATINTLOG, 360ONE, SARLAPOLY) | 2 (both NAUKRI, both pointing to old-endpoint ids outside the window) |
| 1–30 Jun 2026 | 949 | 9 | 1 |

What the six revised companies' filings show:

- **Same trades twice:** PATINTLOG (identical); HTEL, where Revision `3922` (6 Oct) repeats Original
  `3945`'s four designated-person trades and adds one.
- **An old trade re-dated:** NAUKRI `3962` (18 Aug, ₹68.0 crore, director); 360ONE `3855` (31 Jul,
  designated person).
- **One sale filed three times:** SARLAPOLY has two Originals and one Revision, each a 10,000-share
  sale on 25 Sep. Only categories were extracted, so it cannot be told whether these are one
  person or two.

Revisions are about 2% of filings. Most carry no `prevAppId`, so matching on `prevAppId` alone
cannot fix this.

### Findings

| ID | Severity | Location | Trigger | Observed | Expected | Disposition |
|---|---|---|---|---|---|---|
| **F1** | **High** (confirmed: reproduced on the real code and on live NSE data) | `core/discovery/insider.py:108,124,176`; `core/events/feed.py:444-461`; `core/events/disclosures.py:360,367,406` | A `typeOfSubmission: "Revision"` row (a new `appId`) in the window | (a) Discovery sums a revision and its original: BUYERCO's ₹4.5 crore of buying becomes 9.0 (repro); live, PATINTLOG. (b) A revision of an old trade counts as recent: −68.05 for an 18 Aug trade in the 28 days to 23 Oct (repro); live, NAUKRI −₹68.0 crore. (c) The feed stores a second event for the same trades (repro `nsepit:9001`, `nsepit:9002`), and the sentence never says "revision". | `insider.py`'s own contract: "bought and sold in the market over the last 28 days". `disclosures.py`'s contract: `published_at` is "when we could have known". So a trade counts once and in the window of its trade day, and a revision does not present an already-disclosed trade as new. | **Required in rework 1** |
| **F2** | Medium (code inspection plus the story's own values) | `core/discovery/insider.py:124` against `core/events/disclosures.py:339-345` | A promoter-group market sale while promoters hold more than 75% | The event is neutral and names the 25% rule, but discovery counts the full sale against the company. The story's values for KARURVYSYA show both: −0.230769 in discovery, neutral at 78.2% in the event test. | The ranking should not be more confident than the event. A minimum-public-shareholding sale (often a large OFS) should not put a company at the bottom of the signal. | **Recommended in rework 1** (the same function). It is the implementer's delegated call: for example, promoter-group sales do not lower the score, since the 75% test cannot run market-wide without one shareholding call per company; or the promoter share is read only for the few symbols with a negative net. Otherwise record it as an explicit follow-up with an owner. |
| **L1** | Low | `core/discovery/guards.py:109-112` | A shortlisted company whose latest NSE pledge row is old | The quarter in `pledged[1]` is ignored. On 23 Oct, 93 of NSE's 1,558 market rows predate 30 Sep 2026 (6 are from Dec 2014), and 37 of the 181 rows above 25% are older than 30 Sep 2026 (`analysis_data/pr011/raw/pledgedata_market.json`). | A row more than about two quarters old is unknown, so the symbol is degraded and neither rejected nor passed. The shortlist floors (₹5 crore a day, ₹500 crore float) make this rare. | Optional in rework 1 (one comparison and a test); otherwise a limit in KT section 8 |
| **I1** | Info (latent) | `core/discovery/insider.py:162` | `run_screen(on=<a past day>)` | The cache must not be older than 7 days, but nothing stops it being newer than `on`, so a past-day screen would rank with filings disseminated after that day. No caller does this today: the only one is `run_discovery_cycle` with today's date. | `window_to > on` means unavailable | Optional one-line guard in rework 1 |

Checked, and **not** findings:

- The first ownership run compares each stock's latest quarter even when it was filed weeks ago.
  This is correctly dated (`published_at` is the pattern's dissemination), so it is not a
  freshness error.
- The 5 MB document cap is checked after download. This applies to NSE's archive host only.

### Rework 1: what must be true at the re-review

1. **F1, required.**
   - **Discovery:** each trade counts once, and only when its trade day falls inside the window.
     Pin the live cases as recorded fixtures, with names replaced:
     - PATINTLOG `3886`/`3893`: an identical revision without `prevAppId` is counted once;
     - HTEL `3945`/`3922`: the revision repeats the original's four trades and adds one;
     - NAUKRI `3962`: a revision of an 18 Aug trade is not in a 28-day window ending 23 Oct;
     - KARURVYSYA: the three identical rows in one filing (three persons) still count three
       times.
   - **Feed:** a revision is not stored as a second, unqualified event of trades already
     disclosed. Either it is not stored when its trades match a stored event, or its sentence says
     it revises an earlier filing, and its direction and materiality do not read as new trading
     (for example neutral and low). The rule is the implementer's call; record it as a decision.
   - **Docs:** KT sections 4 and 8 and guide 02-L state the revision rule. 02-L's "nothing appears
     twice" stays true.
2. **F2, recommended:** in the same function, or record it as an explicit follow-up.
3. **L1 and I1, optional.**
4. **Evidence:** expected values worked by hand from the recorded revision rows; mutants for the
   new rule; the story file, the changed files and the full suite; `check_broad_except`,
   `check_kt_docs`, and the PDF if the KT changes. Then a regenerated manifest and a rework diff
   against this review's input, plus the cumulative diff.

Decisions D1–D15 are upheld, except that D11's all-or-nothing signal sums revisions (F1) and
D4/D5's float rule stops at the event (F2). D13 stands: PR-011-P1 passed 8 of 8 in production.

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), with the hermetic boundary on (SA-005; the
reviewer's repro folder imports the same hooks through its own `conftest.py`).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe analysis_data/pr011_review/rdigest.py "$PWD" <out>` | `939890c3…` 228,612 B, 32 paths; HEAD `16e31b5` (start and end) |
| `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-011-manifest.json` | 33 files, mismatches `[]` (start and end) |
| `pytest -q -p no:cacheprovider tests/unit/test_disclosures_pr011.py` + the 10 changed test files | **358 passed** in 114.84 s |
| `pytest -q -p no:cacheprovider analysis_data/pr011_review/test_review_repro.py` | **4 passed**. Each test asserts today's defective result, and a `CONTRACT` comment gives the expected one. |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | errors `[]` |
| `analysis_data/pr011_review/revisions_probe.py`, `revision_pairs.py` (public NSE, read-only, about 16:25–16:31 IST) | the counts above; outputs `revisions_out.json` and `revision_pairs_out.json` (ignored) |

**Not exercised:** the full suite (the implementation's 5,644-passed run covers these exact bytes,
and the re-review reruns it); the implementer's 32 mutants (not re-run); production (nothing read);
SAST and Reg 31 revisions (not looked for).

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Parsers turn recorded fixture payloads into the documented events, with the source's date | Met for originals; **not met for revisions** (F1) |
| Promoter 52.1% → 50.6% emits one `ownership` event | Met |
| An unavailable source gives "unavailable", never neutral; a deleted weight is gone from config and ranking | Met |
| The production probe's result per source is in the receipt, sanitized | Met (PR-011-P1, 8 of 8) |
| Hard review: disclosure date against trade date | Originals yes; **revisions no** (F1) |
| Hard review: a float-rule sale | Events yes; discovery no (F2) |
| Living docs and human test cases | Describe the implemented behaviour; they need the revision rule after rework |

### Decision and state

**CHANGES REQUESTED.** STATE: PR-011 `changes_requested`, `active_task` null, `next_task` PR-011
(**rework 1**, in a new conversation). Then a fresh re-review in another new conversation.
`production_verification` stays `pending_deployment`: P1 passed, and nothing is pushed. **Do not
push PR-011** until a re-review accepts it and the owner gives the word.
