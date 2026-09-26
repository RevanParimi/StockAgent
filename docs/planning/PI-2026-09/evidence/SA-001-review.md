# SA-001 — Fresh-session review receipt

**Story:** [SA-001](../stories/SA-001.md) — Sanitize every chat Markdown rendering boundary
**Review context:** **fresh session**, 2026-09-26, about 07:35–07:55 IST. This is a new conversation, and
the implementation conversation's self-review was not reused. Protocol: [REVIEW.md](../REVIEW.md).
**Reviewed input:** the uncommitted working tree on baseline `103f2b8171c0d6365525f9450d41091306ebf22c`,
as pinned by [SA-001-manifest.json](SA-001-manifest.json): 17 files, review-input SHA-256
`2ded4b4381a007e51579d95e652bb448ab75f50155b6e7003d98f6b6d320058f`.
**Verdict: ACCEPTED.** There is no critical, high or medium finding. One low item (L1) is routed to
SA-005, and one info item (I1) is noted on SA-028. Production verification is pending deployment.

**Carry-over box (SA-039 production checks):** checked at the start, Sat 26 Sep 07:36 IST. No check was
due; SA-039-P1 is due Mon 28 Sep 17:00 IST. Nothing was run or recorded.

## Input verification

| Check | Result |
|---|---|
| `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-001-manifest.json` (before any reviewer edit) | 17 files, **0 mismatches**, review input `2ded4b43…` |
| `sha256sum` of the manifest | `2ded4b43…`, the same as STATE and the implementation receipt |
| `git rev-parse HEAD` | `103f2b8…`, the recorded baseline; no commit since |
| `git status` | only the receipt's 16 modified and 6 new paths; `tests/frontend/` holds exactly the two manifest files |
| The same `verify` **after** this review's documentation edits | 13 files still match; 4 differ, all in status wording only: `docs/TECHNICAL_DESIGN.md`, `docs/StockAgent-Three-Loops.pdf` (rebuilt), `docs/ARCHITECTURE.md`, `docs/TEAM_TESTING_GUIDE.md`. **No code, test or package file changed.** |

## Contract checked

The card's hard-review rule: trace untrusted text from the model or tool response to every HTML sink,
challenge the sanitizer configuration, and re-run the fixture that used to execute. I redid the trace
with repo-wide searches, not the implementer's file list.

**Sources (server, `services/api/routes/ui_data.py`).** `chat_stream` sends `intent`, `tool_result`
(`summary` = the first 600 characters of the tool output), `token` and `done` events. The final answer
is `_strip_think` → `_sanitize_answer` → `_chunk_for_stream` (3-word groups). The quota `detail`, the
rate-limit text and `_mock_reply` go through the same `token` event. `_sanitize_answer` only formats
text; it is not a security control. `_session_history_append` stores plain text for later model
context. It is not rendered anywhere, so nothing is persisted as HTML.

**Sinks (client, all of `src/frontend/`).**

| Search | Hits | Consequence |
|---|---|---|
| `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `srcdoc`, `new Function`, `eval(`, `createContextualFragment`, `DOMParser` | one: `sphere.jsx:351`, the bot bubble | the only HTML sink; it receives `'…'`, `renderMd(m.text)` or the constant cursor span |
| `href={`, `src={`, `window.open`, `location.*`, `openWindow`, `formAction`, `srcSet`, `xlinkHref` | one: `sw.js:155` `clients.openWindow(url)` | the push `url` is a server constant (`/#/inbox/<tab>` in `core/delivery/{alerts,brief,weekly}.py` and `core/portfolio/pipeline.py`). The warm-tap handler in index.html only extracts a tab name with a fixed regex. No model text reaches either. |
| `marked`, `DOMPurify` | index.html (pins and handoff), `chat-markdown.js` | `portfolio.jsx`'s `marked` is an unrelated array |
| Tool trace, intent badge, user bubble, seeds | React text nodes | escaped by React |

Both paths reach the same sink: `/ui/chat/stream` (every partial) and the blocking `/ui/chat` fallback
(`reply` and the 429 `detail`). No other file renders chat text.

**Delivery of the fix.** The Dockerfile copies all of `src/frontend/prototypes/`, and `.dockerignore`
does not exclude it. The SPA catch-all serves `chat-markdown.js` as a real file with a JavaScript
content type (`test_spa_catchall.py`). The script is referenced by a relative path, like the other
18 app scripts.

**Sanitizer configuration challenged.** I checked this against DOMPurify's attribute check, not
against the implementer's description.

- `ALLOWED_ATTR` is `href`, `title`, `align` and `start`. `title` is URI-safe by default, and
  `ADD_URI_SAFE_ATTR` adds only `align` and `start`. None of the three can run script or fetch
  anything, so skipping the URL test for them is correct. Without it, table alignment and list
  numbering would be lost.
- `href` has to pass `ALLOWED_URI_REGEXP` after DOMPurify strips whitespace. The hook then re-tests the
  **raw** value with the same pattern. So `" https://…"` or `"h\ttps://…"` loses its href: this is
  stricter, never looser.
- The hook runs after DOMPurify's attribute filter, so the `target` and `rel` it sets survive and
  replace any model-set value.
- The instance is private (`DOMPurify(window)`), so the hook cannot affect any other use.
- The text serializer escapes `<`, `>` and `&` except inside raw-text elements, and none of those is
  allowed. Appending the constant cursor span after the sanitized string therefore cannot change how
  it parses. The re-parse stability check below confirms this.
- Layer 1 (marked's `renderer.html`) escapes every raw-HTML token. Only an exact `<br>`, `<br/>` or
  `<br />` becomes a constant `<br>`. `<br onclick=…>` is escaped.
- Fail-closed: when either library is absent, throws, or `isSupported` is false, the reply is escaped
  text. When `chat-markdown.js` fails to load, `window.saMarkedLib` stays on `window`, but no code
  calls it (the grep above).

**Stale-cache transition.** `sw.js` is network-first for navigations and stale-while-revalidate for
same-origin files, and v8 purges old caches on activation. I checked both mixed states:
- new index.html with the pre-fix `sphere.jsx`: the implementer's two `stale cache:` tests;
- the pre-fix index.html with the new `sphere.jsx` (reviewer check B below).

Both show escaped text, and nothing executes.

## Re-run of the previously executable fixture

I ran the receipt's recipe myself. The pre-fix `index.html`, `sphere.jsx` and `icons.jsx` from
`103f2b8` were copied into the scratchpad and run with `SA_FRONTEND_ROOT`:

- **0 of 14 pass.**
- The streamed sink test records executions `img-split`, `img-onerror`, `img-split`, `img-split`,
  `img-onerror`. The handler fires again on every partial render.
- The blocking-fallback test records `img-onerror`.
- `img-entity` executes as well.

On the reviewed files the same suite passes **14 of 14**, and nothing executes. The tests therefore fail
for the original defect, through the real `ChatOverlay` sink in Chromium.

## Independent adversarial examples (reviewer-written; scratch tests, not committed)

**A. 20 new payloads**, none from the implementer's list. They go through the real sink, streamed in
server-sized chunks. Then every prefix goes through both the full renderer and layer 2 alone:
2,356 renders, each mounted live with the cursor span appended. They cover:
- reference-style links to `javascript:` (plain and entity-encoded);
- a title break-out inside a reference definition;
- an image inside a link;
- an HTML comment, CDATA, and a processing instruction;
- `<div>` and `<pre>` HTML blocks;
- `<textarea>`, `<title>` and `<xmp>` raw-text contexts;
- a table caption;
- an image and a `javascript:` link inside a GFM table cell;
- SVG `<set onbegin>` inside a list;
- `autofocus`/`onfocus`, and a `target="_self"` link;
- an email autolink and a `www.` autolink;
- a destination containing U+2028;
- `<plaintext>`, followed by more text.

Results:
- 0 executions, 0 dialogs, 0 `<img>`, and no request to `attacker.test`.
- Every surviving href starts with `http(s)://`: `https://ok.test/t`, `…/nested`, `https://ok.test`,
  `…/a%20b`, `http://www.example.test/w` and `https://ok.test/`. The email autolink's `mailto:`
  href is removed.
- `<plaintext>` did not swallow the following text.
- **Re-parse stability:** for every prefix, re-parsing the sanitized HTML gives back the same HTML.
  So the precondition for mutation XSS was never met.
- There was one invariant report, `href protocol null`. Its cause is the partial reference definition
  `[r3]: https://`, which renders `href="https://"` for one partial. See I1.

**B. Two targeted checks.**
- Clicking a bubble link with `href="https://"` opens only `about:blank#blocked`, with no opener, and
  the app page does not move.
- The pre-fix index.html with the new `sphere.jsx` and `chat-markdown.js`: the reply
  ``Before <img …onerror…> after [l](javascript:…)`` is shown as escaped text, with 0 executions.

**C. CDN bytes (read-only public GETs).**
- All five pinned URLs in index.html return 200, and their SHA-384 equals the SRI attribute: React,
  ReactDOM, Babel, marked 12.0.2 and DOMPurify 3.4.16.
- Both new jsDelivr URLs send `Access-Control-Allow-Origin: *` and `application/javascript`, which SRI
  with `crossorigin="anonymous"` needs.
- The old floating `marked@12` URL serves the same bytes as `marked@12.0.2`, so marked's behaviour is
  unchanged.

## Test quality

- **Independent expectations.** `__inspect` asserts what must never reach the page: tags outside
  Markdown's set, `on*` or other attributes, non-http(s) hrefs, and links without `_blank` plus
  `noopener noreferrer`. It does not read the sanitizer's configuration. Executions are observed
  directly through `__xss`. The Markdown expectations follow CommonMark/GFM (for example `ol[start]`,
  table `align`, fence text), not snapshots.
- **Real sink.** The harness takes index.html's own `<head>` and transpiles the real `icons.jsx` and
  `sphere.jsx` with the pinned Babel. It mounts `ChatOverlay` and types into its form. A
  MutationObserver checks every committed partial.
- **Mocked boundaries.**
  - Only in-page `fetch` for `/ui/chat/stream` and `/ui/chat` is replaced, with the server's SSE
    framing.
  - Every other request is routed: prototype files, CDN URLs from node_modules (SRI still enforced by
    the browser), and a landing page for `example.test`. Everything else is aborted and recorded.
  - Service workers are blocked. There is no real LLM, API, SMTP or push transport.
  - The fixtures are hostile, not optimistic: the success path is the absence of execution.
- The limits the receipt records (R5 `serverChunks` copies the server's chunking; R6 time-based
  settles) are acceptable. The every-prefix tests make chunk placement irrelevant. The pre-fix run shows
  that the 1.2 s settle catches `onerror`.

## Findings

| # | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| L1 | low (process) | `tests/unit/test_chat_markdown_boundary.py:141-153`; no `.github/workflows` | The Python run happens on a machine without Node, `npm ci` or Chromium. **Observed:** the browser test skips with a reason, and the suite passes. **Expected:** a pre-push baseline that always runs the browser suite. | A later change could weaken the sanitizer while the Python suite stays green. The static guards catch a new sink or an unpinned script, but not an executing handler. | **Routed to [SA-005](../stories/SA-005.md)** (clean test and CI baseline), with the exact commands. Until then, run `npm run test:frontend` before any push that touches `src/frontend/prototypes/`. |
| I1 | info (test harness) | `tests/frontend/chat_harness.mjs:107-110` | A reference-style definition streamed up to `[r]: https://` renders `href="https://"` for one partial, and `new URL` cannot parse it. **Observed:** `__inspect` reports `href protocol null`. The link itself is inert: a click opens `about:blank#blocked`, with no opener. During the same streaming, a reference link can briefly point at a truncated host, for one partial render. | None for users. A future fixture of this shape would fail the streamed test even though the link is safe. | No change. Noted on [SA-028](../stories/SA-028.md), where the harness will be adapted. |

I **agree with the implementer's R1–R6** (receipt, self-review table). None is a blocking item:
- **R1:** a model-written http(s) link is clickable. This is ordinary Markdown behaviour, and the link
  opens in an isolated tab.
- **R2:** images and task lists are gone. This is deliberate, because images would allow zero-click
  exfiltration.
- **R3:** there is no CSP, and tokens are in web storage. Both are routed to SA-028.
- **R4:** after a deploy, text is unformatted for one load. This is safe.
- **R5, R6:** test limitations, as above.

I found no confirmed defect. I did not reproduce any bypass.

## Documentation

- **Verified:** KT §10's chat-rendering paragraph, ARCHITECTURE's frontend row, CHAT_ARCHITECTURE's
  boundary paragraph and file rows, CODEBASE, UI_SPEC's load order and TEAM_TESTING_GUIDE 11-C
  describe the reviewed behaviour. 11-C's fixture only changes the tab title, and it has a fallback
  if the model paraphrases.
- **Changed by this review:** the status wording only, from "awaiting review" to "accepted, not yet
  deployed", in:
  - KT §1 (PI-target row, now linking this receipt), §10 and §12;
  - ARCHITECTURE;
  - 11-C.
- The PDF was rebuilt from the edited KT, and `check_kt_docs` reports 0 errors (below).
- **At commit** (unchanged from the implementation receipt): bump the KT header's `Code inspected`
  revision to the commit and link `chat-markdown.js` there. The docs check rejects links to files that
  are absent at the header revision.

## Commands and environment

Environment:
- Windows 11, Git Bash;
- Node v24.21.0, npm 11.19.0, Playwright 1.62.1, Chromium 151.0.7922.34 (headless);
- repo venv `.stockai` (Python 3.13);
- `npm ls`: exactly `@babel/standalone@7.29.0`, `dompurify@3.4.16`, `marked@12.0.2`,
  `playwright@1.62.1`, `react@18.3.1` and `react-dom@18.3.1`.

| Command | Result |
|---|---|
| `kt_manifest.py verify …/SA-001-manifest.json` | 17 files, 0 mismatches (before the review's edits) |
| `npm run test:frontend` | **14 passed**, 24.4 s |
| The same suite with `SA_FRONTEND_ROOT` set to the `103f2b8` copies of index.html, sphere.jsx and icons.jsx | **0 passed, 14 failed**; executions `img-split`, `img-onerror`, `img-entity` |
| Reviewer scratch suite A (20 payloads, streamed plus every prefix through both layers) | 2 passed, after I1 was separated as inert |
| Reviewer scratch suite B (`https://` click; pre-fix index with the new sphere) | 2 passed |
| `curl` of the five pinned CDN URLs and the old floating `marked@12`, then `openssl dgst -sha384` | 5 of 5 equal their SRI; the floating URL equals 12.0.2; both jsDelivr URLs send `ACAO: *` |
| `RL_LEARNING_MODE=adapt ./.stockai/Scripts/python.exe -m pytest tests/unit/test_chat_markdown_boundary.py tests/unit/test_spa_catchall.py -q -p no:cacheprovider` | **12 passed**, 35 s (this includes the browser suite again) |
| `python scripts/docs/build_kt_pdf.py` | 0 overflow elements; source `97372b07…` |
| `python scripts/docs/check_kt_docs.py` | before edits: 0 errors, source `bd7035dc…`. **After the review's edits: 0 errors**: 306 links, 47 PI stories, 20 PDF pages, source `97372b07…` |
| `kt_manifest.py verify …` after the edits | mismatches only in `docs/ARCHITECTURE.md`, `docs/StockAgent-Three-Loops.pdf`, `docs/TEAM_TESTING_GUIDE.md` and `docs/TECHNICAL_DESIGN.md` |

Not run:
- **the full unit suite.** No production Python changed, and the only Python changes are the two
  test files run above. The implementer's full run was 3166 passed and 5 skipped.
- `tests/integration`;
- `scripts/ui_responsive_audit.mjs`, because the overlay's layout is unchanged;
- a manual check against the running app;
- any production action.

The scratch tests and pre-fix copies are in this session's scratchpad and are not committed.
`data/nse/key_registry.json` was not touched.

## Acceptance checklist

| Criterion | Verdict | Evidence |
|---|---|---|
| A harmless img/onerror fixture cannot execute in the real browser sink | **met** | the split-fixture test on the reviewed files (0 hits) vs the pre-fix run (5 hits); reviewer suite A |
| javascript/data URLs, SVG events, malformed/nested HTML and partial chunks remain inert | **met** | the implementer's 55 fixtures at every prefix; the reviewer's 20 more at every prefix, with re-parse stability |
| Links, code fences, tables and text still render | **met** | `sink: ordinary Markdown still renders…`, `unit: safe Markdown…` |
| Links in a new tab cannot control the opener | **met** | `window.opener === null` and an empty referrer after clicking a real bubble link; the model-set `target`/`rel` is overridden |
| The browser test uses the actual render function and sink | **met** | the harness mounts the real `ChatOverlay` under index.html's `<head>` |
| Unit fixtures cover chunk boundaries, encoded protocols and safe Markdown | **met** | the every-prefix tests; `unit: encoded and obfuscated protocols…` |
| A maintained sanitizer at the final sink; no regex stripping; no reliance on the prompt | **met** | DOMPurify 3.4.16 is the last step before the sink; layer 1 escapes, it does not strip |
| Pin any added browser dependency | **met** | exact versions and SRI, checked against live CDN bytes by the reviewer |
| Inventory equivalent sinks | **met** | the reviewer's repo-wide trace above matches the receipt's inventory; the static guards keep it that way |
| Rollback never restores executable HTML | **met** | fail-closed tests; the receipt's rollback says revert to escaped text, never raw `marked.parse` |
| Documentation and human cases updated; the PDF matches its source | **met** | the Documentation section above |

## Decision and follow-up state

**ACCEPTED** for review input `2ded4b43…` on baseline `103f2b8`. SA-001's code status becomes `done`.
`production_verification` becomes `pending_deployment`.

- **Commit** at the owner's word.
  - Before committing, run `kt_manifest.py verify …/SA-001-manifest.json --rev <commit>`. Expect
    mismatches **only** in the four status-edited documentation files listed above.
  - Bump the KT header revision, and link `chat-markdown.js`, in the same or the next commit.
- **Push and deploy** only on the owner's explicit word, in a job-free window. The safest is 00:10–06:20
  IST; read IST with plain `date`. Also avoid 16:25–17:15, because this changes the served client.
- **Production verification**, after the deploy (a read-only check apart from one chat turn in an
  isolated test account):
  - open the app twice, so that sw v8 takes over;
  - run human case 11-C;
  - confirm that the network panel loads `marked@12.0.2` and `dompurify@3.4.16` with status 200 and no
    SRI error.

  Then set `production_verification` to `verified`, or to `failed`, with the date and the deploy id.
- **Follow-ups:** L1 → [SA-005](../stories/SA-005.md); I1 → a note on [SA-028](../stories/SA-028.md).
  R3 (CSP and token storage) was already routed to SA-028 by the implementation.
- **Next PI phase:** implement [SA-002](../stories/SA-002.md). It is the first planned `todo` story in
  STATE order whose dependencies are all done. It is **not started** in this conversation.
