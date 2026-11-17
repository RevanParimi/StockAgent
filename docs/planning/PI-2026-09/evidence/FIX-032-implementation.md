# FIX-032 — implementation receipt

**Story:** [FIX-032](../stories/FIX-032.md): a home-page watchlist save keeps what it does not
show, and a removal there leaves the daily review. Routed from FIX-028's fresh review (RV5 medium
pre-existing, RV4b low, RV6 low, I-3).

**Profit-path step:** invest. A shelf idea promoted to the watchlist is a watchlist buy candidate
(PR-004); one home-page save silently dropped it.

**Lane:** decision path. The story changes who can change an account's watchlist and which
watchlist buy candidates survive a save. So implementation and self-review stop at
`review_required`, and a fresh conversation does the hard review from [REVIEW.md](../REVIEW.md).

**Phase:** implementation, Monday 16 Nov 2026 from about 09:20 IST. Session `stockagent-main-1a`
[100a12], a new conversation opened with "continue". `origin/main` was `1913017`. `main` is
`2f0c777`, 1 ahead (docs, not pushed). PR-014 stays `in_progress`: its step 7 waits for today's
16:30 run (its `blocked_reason` names FIX-032 as the card that may proceed). Two peers were idle.
At about 09:55 one of them (`-6d`) added PR-033 and PR-034 at the owner's request; its files are
kept and are not in this story's manifest. This phase includes a same-conversation self-review,
which is not the fresh review.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or
configured. Production was not read. No LLM was called and no message was sent. No test reaches
the network (`tests/hermetic.py`).

## In one example

The owner's watchlist holds MARUTI, BACK (added through the API), NEWCO (promoted from the shelf)
and OLD (the autopilot's note of an exit). With Atlas on, as in production:

- **Before:** the home page sends its whole list with HEROMOTOCO added. The route keeps only the 16
  stocks of its own list, then removes every item not kept, so the watchlist becomes MARUTI and
  HEROMOTOCO. NEWCO is no longer offered as a watchlist buy, nothing says so, and its managed entry
  stays enabled, so it is still reviewed every weekday.
- **Now:** the home page sends `{"add": ["HEROMOTOCO"]}`. The four stay exactly as stored (source,
  reason, date). Removing MARUTI sends `{"remove": ["MARUTI"]}` and keeps the other four.

## What changed

- **The route** ([ui_data.py](../../../../services/api/routes/ui_data.py), `PUT /ui/watchlist`):
  the body takes `add` and `remove`. `add` takes stocks from the home page's own list (as before);
  `remove` takes any stock on the watchlist, since the page shows every one. The add and the
  removal run under the account's lock. Each removed stock goes to `demote_symbol` after the lock.
  The answer is the whole watchlist after the change. The older whole-list form `watchlist` only
  adds (F32-D2). With Atlas off (owner only, the global file) the same change applies. An empty
  body is a 422.
- **The page** ([home.jsx](../../../../src/frontend/prototypes/home.jsx), `WatchlistPane`): add and
  remove send only the one stock, and the page shows the list the answer carries.
- **The demotion** ([promotion.py](../../../../core/portfolio/promotion.py), `demote_symbol`): it
  asks FIX-028's question across every portfolio first. An enabled held or watchlist entry is
  disabled only when no portfolio holds the stock and no user's own watchlist lists it. The
  autopilot's note does not count. A held entry that only a watch keeps turns weekly, as
  `release_unheld` does. It returns True only when this call disabled the entry. An already
  disabled entry is not rewritten (F32-D6). The symbol is matched trimmed and upper-case.
- **The API's deletes** ([portfolio_api.py](../../../../services/api/routes/portfolio_api.py),
  `delete_holding`, `delete_watchlist`): each now calls `demote_symbol` with no check of its own
  (F32-D3).
- **Quarantine** (`promotion._portfolios_now`, `_quarantined_users`): an account folder with a
  `portfolio.json.corrupt-*` and no `portfolio.json` raises "portfolio.json quarantined and not
  restored for <user>". So `release_unheld` releases nothing that run, and the log says why ("no
  managed entry released: …"). `demote_symbol` changes nothing ("<SYM> not demoted, portfolios
  unreadable: …").
- **Housekeeping:** `deep_dive.py`'s comment at the `sold` flag (I-3).
- **Docs:** KT section 6 (the release paragraph, its example, and a new paragraph "The home page's
  watchlist save names only the change", which replaces "Not covered … Planned: FIX-032");
  AUTOPILOT_GUIDE section 12 (three bullets and the route table's watchlist row); CODEBASE (the
  `PUT /ui/watchlist` and both delete rows); UI_SPEC (`WatchlistPane`); the guide's new case 07-R,
  07-P's note and HT-07's related list; the PDF (72 pages, source `96a086c8`). Outside the
  manifest: BACKLOG (B-5, and SA-026's parked line) and SA-026's routed section (the API-delete
  finding is taken here).

## Decisions (delegated technical calls; the owner delegated routing and technical calls on 13 Oct)

- **F32-D1: the save names the change, not the whole list.** The card's first intended result says
  the items the home page "does not offer (outside `_ALL_TICKERS`, the autopilot's notes) stay as
  they are". But the page does show them. `GET /ui/watchlist` returns every watchlist symbol, FIX-010
  builds a row for one outside the list, and each row has a remove button. So read literally, that
  rule makes the remove button do nothing for BACK, and BACK comes back on reload. That contradicts
  the card's own second example ("v's removal of BACK on the home page disables it"). A whole list
  also drops an item added after the page loaded, the shelf promotion or the autopilot's 16:30 note,
  even one inside the home page's list. A change-only body fixes both. The categories route in the
  same file already takes `add` and `remove`.
- **F32-D2: the whole-list form only adds.** A page loaded before the deploy still sends it. A
  stock that list omits cannot be told apart from one that page never saw. Example: the server holds
  MARUTI, NEWCO and HEROMOTOCO; an old page saw only MARUTI; the user adds HEROMOTOCO there, and the
  page posts `[MARUTI, HEROMOTOCO]`. Reading that as a removal drops NEWCO. A first version of this
  phase read it as "one change per save" (an add removes nothing; otherwise remove the one omitted;
  refuse two). This example broke it, so it was replaced before any test was recorded.
  **Consequences:**
  - FIX-028's reviewer case RV4b, as written, posts the old form `[]` to remove BACK, and it fails:
    `assert ['BACK'] == []` (BACK stays on v's list). Run with the page's request,
    `{"remove": ["BACK"]}`, it passes. RV5 and RV6 pass as written.
  - On a page loaded before the deploy, a removal changes nothing on the server, though the old
    page hides the row until a reload. Its adds work.
- **F32-D3: the question lives in `demote_symbol`, and the routes' own checks are gone.** All three
  removals then ask it the same way, and the five test files that stub `demote_symbol` by name keep
  working. The holding delete used to skip the demotion whenever its own watchlist named the stock,
  even when the only item was the autopilot's note. That left a daily entry for a stock nobody
  holds. Now, with the user's own watch, the entry turns weekly; with only the note, it is disabled.
  This also takes the second of FIX-028's two findings parked with SA-026 ("the API's delete routes
  look only at the user's own portfolio").
- **F32-D4: a held entry that only a watch keeps turns weekly**, FIX-028's rule applied to one
  stock, rather than staying daily or being disabled.
- **F32-D5: an unrestored quarantine stops every release, not only that account's stocks** (the
  card: "like an unreadable file"). The owner already gets a critical alert at the quarantine. Cost:
  until the file is restored or the folder removed, sold stocks keep their daily review. That is why
  `FIX-032-P1` runs before the deploy (Rollout, below).
- **F32-D6: `demote_symbol` on a disabled entry** returns False and writes nothing. Before, it wrote
  `enabled: false` again and returned True. The API's `demoted` now means "this call disabled it".
- **F32-D7: a removal of a stock not on the list** changes nothing and demotes nothing.

## Tests

Every expected value is worked from the test's own fixture, never read back from the code. No test
reaches the network.

- **Story file** `tests/unit/test_watchlist_save_fix032.py`, 293 tests, all pass. Real routes run
  through FastAPI's TestClient (the signed-in user is a header), with real portfolio files and the
  real promotion over a real managed file in the test's folder. Atlas is on.
  - **The card's example** (add HEROMOTOCO, then remove MARUTI): every other item byte for byte;
    MARUTI's original entry unchanged.
  - **The whole-list form:** it adds and never removes; a page whose list is out of date drops
    nothing.
  - **What a save may name:** an add outside the list, an add already there, and a removal not on
    the list (with nobody holding or watching NEWCO, so a demotion would show); upper-case and
    trimmed symbols; an empty body (422).
  - **One user's save:** it changes only that user's list.
  - **Two invariants:**
    - 80 random lists and changes, in random spellings: no stock the request does not name is
      dropped or rewritten;
    - 40 random older pages that saw a random part of the list, with one change: nothing stored
      is dropped or rewritten.
  - **Atlas off:** the global file takes the change; a member gets 403.
  - **The removal question** through the real routes:
    - the card's second example, then u's next autopilot run;
    - another user watches the stock, another portfolio holds it, or the remover holds it: the
      entry is kept;
    - only the autopilot's note lists it: disabled;
    - original entries never change;
    - the API's watchlist delete while another user holds the stock, and after that user sells;
    - the holding delete, with the remover's own watch, with only the note, and with nothing;
    - the watch delete while the remover holds the stock.
  - **The rule against its own oracle:** 150 random states (portfolios with random holdings and
    watchlists, random sources and spellings; X's entry of every origin, enabled or not, beside two
    others). Each one checks the return value, X's entry and the other entries unchanged.
  - **Quarantine:**
    - an unrestored account holding BACK: u's exit releases nothing, and the log says why; once
      the file is restored by hand, the next run releases it;
    - a removal's demotion is stopped too;
    - a folder with only a lock file is not a quarantine.
- **The browser test**, added to `tests/frontend/no_invented_figures.test.mjs`: the real page,
  remove then add. Each request carries only `{remove: [sym]}` or `{add: [sym]}`. A stock the
  server added after the page loaded shows after the change. It passes. With the old page
  (`SA_FRONTEND_ROOT` set to `git archive HEAD`'s prototypes) it fails.
- **On the code before this story** (a detached worktree at `2f0c777`, scratchpad): 180 of the 293
  fail and 109 pass. The route cases fail on the request shape the old route refuses. The rule is
  pinned apart from that: `test_demote_symbol_against_its_rule` fails 49 of 150, and the API delete
  case fails on the old route's own request.
- **FIX-028's reviewer cases** (`analysis_data/fix032/rv/`, copies with the three strict xfail marks
  removed): RV5 and RV6 pass as written, and RV4b passes with the page's request (F32-D2). The 452
  others pass, including RV1's 300 random releases and RV2's 150 random runs. As written, RV4b
  fails, recorded above.
- **Mutants** (`analysis_data/fix032/mutants.py`, run in the scratch worktree, never the shared
  checkout; each file's sha restored and checked; run on the story file and the reviewer cases
  with RV4b's page request; `mutants_out.txt`): **20 of 20 caught** on the final bytes.
  - `demote_symbol` and the quarantine (M01–M10): it acts on a disabled entry; it ignores
    holdings; it ignores watches; it keeps a held entry daily; it reads an unreadable portfolio as
    empty; no quarantine check; a restored account still counted as quarantined; any folder
    counted; the autopilot's note counted as a watch; the symbol matched exactly.
  - The route (M11–M18, M20): an add outside the page's list; a removal of a stock not on the list
    (it would demote); the whole-list form removing what it omits (the old route); no demotion; a
    remove-only body not seen as a change; the answer is the list before the change; the
    dormant path ignoring `remove`; symbols not normalised; the dormant path keeping a stock
    named in both `add` and `remove`.
  - The holding delete's old check of its own watchlist (M19).

  A first pass of 18 on earlier bytes, before F32-D3 and the dormant-path fix, caught 18
  (`mutants_pass1_earlier_bytes.txt`).
- **Neighbouring suites:** 14 files that touch these routes, the managed list or the home page
  (auth lockdown, Atlas singletons and user instruments, the autopilot and portfolio APIs, deep
  dive, PR-004 idea supply, promotion, SA-051, FIX-010, FIX-028, SA-048, PR-002, PR-001 with the
  browser suite): 938 passed.
- **Full suite**, one run on the final code bytes (10:00–10:22 IST, 16 Nov, concurrent with the
  last mutant pass in its separate worktree): **6,749 passed / 12 skipped / 1 xfailed / 0
  failed**, return code 0, 21m59s. `git status` was the same before and after
  (`analysis_data/fix032/full_suite*.txt`, `status_*_suite.txt`). 6,749 = PR-014's 6,456 plus the
  story file's 293.
- `check_broad_except`: OK (148 grandfathered). `check_kt_docs`: `errors: []`; PDF regenerated (72
  pages, source `96a086c8`).

## Rollout (what deploying changes)

- **Production gate first: `FIX-032-P1`, before the deploy.** With FIX-032 deployed, any account
  folder in production that holds a `portfolio.json.corrupt-*` and no restored `portfolio.json`
  stops every release of a sold stock from the daily review (F32-D5). The 16 Jul 2026 incident
  (AUD-050 quarantine tests and fixture users) makes such a leftover folder possible, and nobody
  has counted. `analysis_data/fix032/prod_probe.py` is read-only and prints counts only (no
  symbols, user ids or values). It was checked on a made-up tree whose counts were worked by hand
  (`probe_fixture.py`: ok). The owner ran it after this phase (result below). The command:

  ```text
  railway ssh "cd /app && echo $(gzip -9c analysis_data/fix032/prod_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
  ```

  Pass: `quarantined_not_restored` is 0. If not, the owner restores or removes that folder before
  the deploy. The same read also counts P2, the items one home-page save would have dropped
  (RV5's exposure, never measured), and P3, old `watchlist` entries that nobody holds or watches
  (BACKLOG B-5).
- **The home page:** a save no longer drops watchlist buy candidates. A tab loaded before the
  deploy keeps the old page until it is reloaded: its removals change nothing on the server.
- **Removals** (home page, the API's two deletes): an entry is disabled only when nobody holds or
  watches the stock. A holding deleted while its owner still watches it now turns weekly instead of
  staying daily.
- No configuration or data changes. Rollback is a revert: the old route reads `watchlist` and
  ignores `add` and `remove`, so revert the page with it.

## Production probe (`FIX-032-P1`): passed

The owner's read, Monday 16 Nov about 13:50 IST, by one `railway ssh` (the command above), on
production's `1913017`, after this phase's bookkeeping. Counts only, as printed:

| Count | Value | What it means |
| --- | --- | --- |
| `quarantined_not_restored` | 0 | **P1 passes:** deploying FIX-032 does not stop the release |
| `quarantined_restored`, `portfolio_unreadable` | 0, 0 | |
| Account folders | 2: 1 with `portfolio.json`, 1 with neither | The empty one is a folder `PortfolioStore` made on first use; it stops nothing (tested) |
| Watchlist items | 21, all `autopilot` | The autopilot's notes of its sales, in one account |
| … outside the home page's list (P2) | 20, all `autopilot` | Before FIX-032 one home-page save would have dropped these 20 notes. No user-added stock and no promoted shelf idea is on any watchlist, so no buy candidate has been lost |
| Enabled `watchlist`-origin entries nobody holds or watches (P3) | 0 (no `watchlist`-origin entry at all) | BACKLOG B-5's trigger is not met |
| Managed list | manual 16 enabled + 1 disabled; held 2 enabled + 5 disabled | No held entry is enabled for a stock nobody holds: FIX-028's release works |

So today the fix is preventive: the first shelf promotion or API-added stock would have been
exposed to RV5. Nothing changes the rollout: no configuration or data change is needed.

## Hard review (the card's questions, answered)

- **Does any other route save `Portfolio.watchlist` from a partial view?** No. A search for
  `WatchlistItem(`, `add_watchlist(`, `remove_watchlist(`, `.watchlist =` and `watchlist.append`
  over `core/`, `services/` and `src/` finds these watchlist writers:
  - `PortfolioStore.add_watchlist` and `remove_watchlist`, one item each under the account's lock.
    Their callers are the API's add and delete, the shelf's promote (`shelf.py`
    `ShelfStore.promote`) and the home page.
  - The autopilot's exit note (`autopilot._execute_sells`), written to a portfolio that
    `execute_advice` reloaded under the lock (AUD-001).

  Every whole-portfolio `save` reloads under the account's lock first: autopilot, corp_actions,
  identity_reconcile, the store's own helpers, the CSV import and the API's manual add, delete
  and cash routes. The chat tools write no watchlist. Only the home page's PUT saved a whole list,
  and it is the one changed.
- **Must the home page show the autopilot's `autopilot_exit` notes?** Not decided here. What it
  shows: every symbol on the account's watchlist, the autopilot's notes and stocks outside its own
  list included, each with a remove button. A row for a stock outside the list is built from the
  score history (FIX-010), with no live price.

## Not covered / found on the way

- **Old residue:** a `watchlist` entry left enabled by a home-page removal before FIX-032 stays
  enabled. BACKLOG B-5, promoted when `FIX-032-P1` reads P3 above 0.
- **RV4b as written** fails by F32-D2 (above). The fresh review decides whether that decision
  stands.
- **The owner's dashboard routes** (`/ui/tickers/managed`) still take no lock: SA-026, parked.

## Review input

- Manifest: [FIX-032-manifest.json](FIX-032-manifest.json), SHA-256
  `7f30781e184acb287d5c806d6b8e22b4b160df539a9a10e8f32654707be2fcb5`, 13 files
  (`scripts/docs/kt_manifest.py verify`: 0 mismatches).
- Diff against HEAD `2f0c777`, the PDF excluded: SHA-256
  `bbf40aeeb3adbc7a9bcbcf5bafe7a313489df30ef18ac60f53407969d5669e5a`, 69,338 bytes, 12 paths, via
  `analysis_data/fix032/digest.py` (a temporary index; the real index is untouched). End tree
  `532ae48ac2f56673e3def4ce300d938c53991a9c`, taken before this receipt's last figures and the
  STATE/HANDOFF splice.
- Outside the manifest:
  - bookkeeping: STATE, HANDOFF, this receipt and the manifest;
  - planning notes: BACKLOG (B-5; SA-026's parked line) and SA-026's routed section;
  - the peer session `-6d`'s files: PR-033, PR-034, README, SA-041, and its lines in STATE and
    HANDOFF.
- On another device: `git diff 2f0c777` over the manifest's paths but the PDF, sorted,
  `core.autocrlf=false`, with the new test file added.
- Reviewer fixtures: `analysis_data/fix032/rv/` (ignored, this laptop): FIX-028's reviewer file
  without its three strict xfails (`test_rv_fix028_unxfailed.py`, RV4b as written) and with RV4b's
  page request (`test_rv_fix028_fix032.py`). On another device, write them from FIX-032's card and
  F32-D2.

## What a fresh review should press on

1. F32-D1 and F32-D2: is the change-only body right, and is "the whole-list form only adds" the
   right reading of the card, given RV4b?
2. F32-D5: should an unrestored quarantine stop every release, or only that account's stocks?
3. Is any reader of `demote_symbol`'s old answer (True for a disabled entry, or for a stock another
   portfolio holds) left that now gets a different meaning? The API returns it as `demoted`. A
   search of `core/`, `services/`, `src/`, `scripts/` and `tests/` finds no client that reads it
   and no test but this story's. (Atlas's `universe.py` has its own, separate demotion in
   `atlas.db`.)
4. The lock order: the route holds the account's lock for the add and remove, then calls
   `demote_symbol` (the managed list's lock) after letting go. The autopilot takes the account's
   lock, then the list's. No path takes them the other way round.
