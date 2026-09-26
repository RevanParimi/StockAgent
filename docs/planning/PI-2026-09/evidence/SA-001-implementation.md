# SA-001 — Implementation receipt

> **Accepted 2026-09-26** by a fresh-session review: [SA-001-review.md](SA-001-review.md). The findings
> are L1 (low; routed to SA-005) and I1 (info; noted on SA-028). Not yet committed or deployed. The
> "awaiting review" wording below is historical.

**Story:** [SA-001](../stories/SA-001.md) — Sanitize every chat Markdown rendering boundary
**Phase:** implementation, 2026-09-26. Status after this phase: `review_required`.
**Context:** one implementation conversation. The self-review below is **not** the fresh-session review that [REVIEW.md](../REVIEW.md) requires.
**Baseline commit:** `103f2b8171c0d6365525f9450d41091306ebf22c`. Its prototype, test and package files are identical to `994a7b6`, which the sensitivity runs below took the pre-fix files from. Not committed.
**Review input:** [SA-001-manifest.json](SA-001-manifest.json), 17 files, **review-input SHA-256 `2ded4b4381a007e51579d95e652bb448ab75f50155b6e7003d98f6b6d320058f`**.

**Carry-over box (SA-039 production checks):** checked at the start of this phase, Sat 26 Sep 06:49 IST. No check was due; the first, SA-039-P1, is due Mon 28 Sep 17:00 IST. Nothing was run or recorded.

## How to verify the input

```bash
python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-001-manifest.json
sha256sum docs/planning/PI-2026-09/evidence/SA-001-manifest.json
```

`verify` recomputes each file's git blob id and the SHA-256 of those blob bytes from the working tree;
expect `"mismatches": []`. After a commit, use `verify --rev <commit>`. The manifest excludes STATE.json,
HANDOFF.md, the routed note on [SA-028](../stories/SA-028.md), this receipt and itself, which are written after it.

Setup for the browser suite: Node on PATH, then `npm ci` and `npx playwright install chromium`.
To re-run the previously executable fixture on the pre-fix files:

```bash
d=$(mktemp -d); for f in index.html sphere.jsx icons.jsx; do
  git show 103f2b8:src/frontend/prototypes/$f > "$d/$f"; done
SA_FRONTEND_ROOT="$d" node --test tests/frontend/chat_markdown.test.mjs
# expect failures whose "a fixture executed" lists include 'img-onerror'
```

## The defect, in one example

The model quotes a news snippet: `Tata Motors <img src=x onerror="…">`. Before this change, `renderMd` in
`sphere.jsx` returned `window.marked.parse(text)`, and the bubble put that into `dangerouslySetInnerHTML`.
marked passes raw HTML through, so the browser created the image, the load failed, and the handler ran,
in the same page that keeps the bearer token in `localStorage`/`sessionStorage` (audit F01). **Reproduced
here** in Chromium on the pre-fix files: the fixture's `onerror` fired through the real `ChatOverlay`
(see "Sensitivity"). After the change, the same reply shows `<img src=x onerror="…">` as text, and
nothing runs.

## What changed

**New `src/frontend/prototypes/chat-markdown.js`** (plain script, no Babel), which defines
`window.saRenderChatMarkdown(text)`. It has two independent layers:

1. **marked shows raw HTML as text.** A `renderer.html` override escapes every raw-HTML token, inline
   or block, and keeps `<br>` as a constant. The chat prompt (`_CHAT_SYSTEM_PROMPT`) asks for Markdown
   only, so nothing intended is lost. A quoted snippet also stays readable instead of silently vanishing:
   with sanitizing alone, an unclosed `<svg>` swallowed the rest of the reply.
2. **DOMPurify 3.4.16 right before the sink**, as a private instance (`DOMPurify(window)`) so its hook
   cannot leak:
   - `ALLOWED_TAGS`: p, br, hr, strong, em, del, code, pre, blockquote, ul, ol, li, a, h1–h6, table,
     thead, tbody, tr, th, td. No img, svg, math, form, input, iframe, style or span.
   - `ALLOWED_ATTR`: href, title, align, start. `align` and `start` are added to `ADD_URI_SAFE_ATTR`.
     Otherwise DOMPurify tests every non-URI-safe attribute against the URL pattern, and table
     alignment and list numbering would be dropped.
   - `ALLOWED_URI_REGEXP: /^https?:\/\//i`, with data/ARIA attributes and unknown protocols off. No
     style, class or id is kept, which also removes DOM clobbering and UI redress through app classes.
   - An `afterSanitizeAttributes` hook re-checks each link's raw href with the same pattern. A link that
     passes gets `target="_blank" rel="noopener noreferrer nofollow"`, overriding any model-set
     target/rel. Any other href is removed.
   - **Images are dropped**, not rendered: a model-written image URL would be fetched with no click,
     which can leak data to a third party (prompt-injection exfiltration). Alt text is lost; the prompt
     never asks for images.

**Fails closed.** If marked or DOMPurify is missing (CDN down, SRI mismatch, `isSupported` false) or
throws, the text is shown escaped (`& < > " '` plus newline → `<br>`), never as raw HTML.
`renderChatMarkdown.sanitizeHtml` exposes layer 2 alone for tests.

**`sphere.jsx`:** `renderMd` delegates to `window.saRenderChatMarkdown`. If that function is absent, it
escapes the text itself; it never touches marked. The sink comment now states that every partial is
sanitized and only the constant cursor span is appended afterwards.

**`index.html`:**
- `marked@12` (floating, no SRI) → `marked@12.0.2` with `integrity` and `crossorigin`. The floating
  tag already served 12.0.2 byte for byte (checked against the CDN), so marked's behaviour does not
  change.
- An inline script right after marked moves the parser from `window.marked` to `window.saMarkedLib`
  and deletes the former. `chat-markdown.js` takes the handoff and deletes it too.
- DOMPurify `3.4.16` added with SRI.
- The inline `marked.setOptions` script is removed: options now live on a private `Marked` instance.

**Why the handoff.** The service worker serves same-origin JSX stale-while-revalidate. The first load
after a deploy can therefore run the **old** `sphere.jsx` under the new index.html. The old
`renderMd` calls `window.marked` when it exists. With marked removed from `window` before any other
script runs, that old code falls back to escaped text, even if `chat-markdown.js` itself fails to
load. The sensitivity run found that last case, and the inline handoff closed it.

**`sw.js`:** `VERSION` v7 → v8, which purges the cached pre-fix `sphere.jsx` and the unpinned
`marked@12` CDN entry on activation. `/chat-markdown.js` is added to the offline shell.

**Pins.** All five CDN scripts are now exact versions with sha384 SRI; React, ReactDOM and Babel
already were. package.json gains exact devDependencies `marked 12.0.2`, `dompurify 3.4.16`, `react`
and `react-dom 18.3.1` and `@babel/standalone 7.29.0`, so the browser test serves the same bytes. I
checked all six CDN URLs (including the old floating `marked@12`) byte for byte against the npm
tarball files. `npm audit`: 0 vulnerabilities. DOMPurify 3.4.16 was published 2026-09-23, three days
before this pin; the SRI hash stops a later CDN change from being served.

## Sink inventory (untrusted text → every HTML sink)

| Source | Path | Sink | Now |
|---|---|---|---|
| Model answer (`/ui/chat/stream` `token` events, 3-word chunks from `_chunk_for_stream`) | `ChatOverlay.send` accumulates `text` → `renderMd` | bubble `dangerouslySetInnerHTML` | sanitized on every partial render |
| Model answer (blocking `/ui/chat` `reply`) and quota `detail` (429 and SSE) | same `setMsgs` → `renderMd` | same | sanitized |
| Error, rate-limit and mock replies (server strings) | SSE `token` | same | sanitized |
| Tool results (`tool_result.summary`, up to 600 chars of news/screen text) | `ToolTracePanel` | React text node | escaped by React; no change needed |
| Intent (`intent_type`, `display_label`, `query`) | `IntentBadge` | React text; color from a fixed map | escaped; no change |
| User message | user bubble `{m.text}` | React text | escaped; no change |
| Other LLM text (brief, digest, weekly, inbox, agents pages) | JSX text | React text | inventory test: no other HTML sink |
| Push payload `url` | `sw.js` `clients.openWindow(url)` | navigation | server constants only (`/`, `/#/inbox/<tab>` in `core/delivery`); allow-listed in the inventory test |
| Email bodies (brief/alerts) | `core/delivery/*` `_esc` = `html.escape` | email client | out of chat scope; inspected, not changed |

`_sanitize_answer` on the server only strips disclaimers and flattens tables; it is not a security
control, and SA-001 does not rely on it. The browser sees no CSP; that is routed to SA-028 (below).

## Acceptance criteria

| Criterion | Evidence |
|---|---|
| A harmless img/onerror fixture cannot execute in the real browser sink | `sink: a harmless img/onerror fixture split mid-tag cannot execute`. It streams `Hello <img src=x on` / `error="__xss('img-split')"` / … through the real `ChatOverlay` form and `dangerouslySetInnerHTML`, and records every committed partial with a MutationObserver. `__xss` hits `[]`, no `<img>`, the raw text is visible, and a partial state (Hello without world) did reach the sink. On the pre-fix files the same test records `img-split` and `img-onerror` executions. |
| javascript/data URLs, SVG events, malformed/nested HTML and partial streaming chunks remain inert | 37 hostile HTML fixtures (SVG onload/animate/xlink/foreignObject/script, two published DOMPurify mXSS shapes, noscript, split script, details/ontoggle, iframe srcdoc, object/embed, video source, autofocus, body, style @import, CSS url, link, base, meta refresh, onclick on a valid link, DOM clobbering by id/name, formaction, td background, a title break-out, inline and fenced code) plus 18 URL fixtures (javascript in several cases, decimal, hex and named entities, tab/newline/control characters, leading space, percent-encoded, angle-bracket and autolink forms, data: plain and base64, vbscript, protocol-relative, relative). **Every prefix** of every fixture goes through the full renderer (`unit: the full renderer…`) and through layer 2 alone (`unit: the sanitizer alone…`), and each output is also mounted live. All fixtures joined and streamed in server-sized chunks go through the real sink (`sink: hostile HTML and URLs…`). The blocking fallback path is covered too (`sink: the blocking /ui/chat fallback…`). Result: 0 executions, 0 invariant violations, 0 dialogs, 0 requests to `attacker.test`, and no navigation of the app page. |
| Links, code fences, tables and text still render | `sink: ordinary Markdown still renders…` (heading, bold, em, strikethrough, line break, ul, ol start=3, blockquote, https and autolinks, fenced code with `<b>` kept as text, inline code, a table with left/right alignment, `₹` and `< &` text) and `unit: safe Markdown maps to its expected elements` (14 cases) |
| Links opened in a new tab cannot control the opener | `sink: links open in a new tab…`: clicking a real bubble link opens a popup with `window.opener === null` and an empty `document.referrer`, and the app page URL is unchanged. `unit: the sanitizer alone…` also clicks a raw `<a target="_self" rel="opener">` after layer 2, with the same result. |
| Browser regression uses the actual render function and sink | The harness takes index.html's own `<head>` (the pinned scripts, SRI, handoff and `chat-markdown.js`), transpiles the real `icons.jsx` and `sphere.jsx` with the pinned Babel, mounts `ChatOverlay`, and types into its form. Only the chat `fetch` is replaced (SSE ReadableStream). |
| Unit fixtures cover chunk boundaries, encoded protocols and safe Markdown | The every-prefix tests (2,937 renders per layer: every prefix of all 55 fixtures), `unit: encoded and obfuscated protocols…`, and `unit: safe Markdown…` |
| Maintained sanitizer, restrictive HTML/URL policy at the final sink; no regex stripping or prompt reliance | DOMPurify at the last step before the sink; layer 1 escapes tokens, it does not strip them |
| Pin any added browser dependency | Exact versions and SRI on all CDN scripts; `test_every_cdn_script_is_pinned_to_exact_bytes` and `test_browser_harness_libraries_match_the_production_pins` (the latter hashes node_modules against the SRI) |
| Inventory equivalent sinks | Table above; `test_the_chat_bubble_is_the_only_html_sink_in_the_client`, `test_no_dynamic_url_sink_takes_model_or_tool_text`, `test_the_bubble_sink_only_receives_rendered_markdown_or_constants`, `test_only_the_boundary_module_touches_the_markdown_parser` |
| Fail closed; never restore executable HTML | Three `fail-closed:` tests (DOMPurify 404, marked bytes failing SRI, `chat-markdown.js` 404): the reply shows as escaped text and nothing executes. Two `stale cache:` tests run the verbatim pre-fix `renderMd` under the new page, with and without `chat-markdown.js`. |

**Independence of expectations.** The page-side invariant checker (`__inspect` in `chat_harness.mjs`)
does not read the sanitizer's configuration. It asserts:
- only Markdown's own elements appear (plus the constant cursor span in the live bubble);
- no `on*` attribute, and no attribute outside href/title/align/start/target/rel;
- every href resolves (`new URL`) to `http:` or `https:`;
- every link has `target="_blank"` and `rel` with `noopener` and `noreferrer`.

Executions are observed directly: every hostile fixture calls `window.__xss('<id>')`. The expected
Markdown structure (a table's th/td text and `align`, `ol[start]`, the code-fence text) follows
CommonMark/GFM semantics, not snapshots of this renderer's output.

**Sensitivity (the tests fail for the original defect and for weakened fixes).** I ran the same suite
through `SA_FRONTEND_ROOT` against temporary copies (scratchpad script; the copies were deleted):

| Variant | Pass / fail | What the failures show |
|---|---|---|
| Pre-fix files (index.html, sphere.jsx, icons.jsx from `994a7b6`) | 0 / 14 | Executed: `img-split`, `img-onerror`, `img-entity`. Links lack target/rel. The unit tests fail because the renderer does not exist. |
| New index.html and chat-markdown.js, **pre-fix sphere.jsx** (the stale-cache load) | 11 / 3 | Nothing executes. The 3 failures are formatting only: the old `renderMd` falls back to escaped text. |
| Inline handoff removed from index.html | 12 / 2 | Both `stale cache:` tests fail: the pre-fix `renderMd` reaches the raw parser. |
| Layer 1 removed (sanitizer alone) | 11 / 3 | Nothing executes and no violation occurs. Only the three "raw HTML stays visible as text" assertions fail, so layer 2 holds on its own. |
| DOMPurify default policy | 10 / 4 | `<img src>` from Markdown images, and `class` |
| Link hook removed | 8 / 6 | Links lack `target=_blank` and `noopener noreferrer` |
| Sanitizer removed (layer 1 only) | 7 / 7 | `javascript:`, `data:` and `vbscript:` hrefs, `<img>`, and missing target/rel |

The static pytest guards were not mutation-run. By inspection they fail on the pre-fix files: the
floating `marked@12` has no SRI, and the pre-fix `renderMd` calls `window.marked`.

**Transports blocked.** The harness routes every request. It serves the prototype files from
`http://sa.test`, answers the five CDN URLs from node_modules (the browser still enforces index.html's
SRI), serves a one-line landing page for `https://example.test/*`, and aborts and records everything
else (Google Fonts, `attacker.test`). Service workers are blocked in the test context. No real chat,
LLM or API call is made.

## Commands and results

Environment:
- Windows 11, Git Bash;
- Node v24.21.0, npm 11.19.0, Playwright 1.62.1, Chromium 151.0.7922.34 (headless);
- repo venv `.stockai` (Python 3.13).

| Command | Result |
|---|---|
| `npm install --save-dev --save-exact marked@12.0.2 dompurify@3.4.16 react@18.3.1 react-dom@18.3.1 @babel/standalone@7.29.0` | added 9 packages; `npm audit`: 0 vulnerabilities |
| CDN byte check (scratchpad script: fetch each CDN URL, compare with node_modules, print sha384) | 6/6 equal; the React, ReactDOM and Babel hashes equal index.html's existing SRI |
| `node --test tests/frontend/chat_markdown.test.mjs` (or `npm run test:frontend`) | **14 passed**, about 27 s |
| `RL_LEARNING_MODE=adapt ./.stockai/Scripts/python.exe -m pytest tests/unit/test_chat_markdown_boundary.py tests/unit/test_spa_catchall.py -q -p no:cacheprovider` | **12 passed** (9 + 3; the last boundary test runs the browser suite) |
| `RL_LEARNING_MODE=adapt ./.stockai/Scripts/python.exe -m pytest tests/unit -q -p no:cacheprovider` (Node on PATH) | **3166 passed, 5 skipped** in 5 min 06 s (collected before the URL-sink test was added; that test then passed in the 12-test run above). `data/nse/key_registry.json` was not modified. |
| Sensitivity script (7 variants, above) | as tabled |
| Browser suite repeated 3 times back to back (flakiness check) | 14/14 each time (26–29 s) |
| `python scripts/docs/build_kt_pdf.py` (Node on PATH) | 0 overflow elements; source SHA-256 `bd7035dc…` |
| `python scripts/docs/check_kt_docs.py` | **0 errors**: 13 documents, 300 links, 47 PI stories, 24 job IDs, 20 PDF pages; 0 linked sources changed since `4c4728a` |
| `python scripts/docs/kt_manifest.py write …` / `verify` | 17 files, 0 mismatches, review input `2ded4b43…` |

`RL_LEARNING_MODE=adapt` is needed because the owner's local `.env` now resolves `observe`, which fails
7 lesson-emphasis tests unrelated to this story (HANDOFF; SA-005 will pin the mode).

Not run:
- `scripts/ui_responsive_audit.mjs`, which needs a seeded server; the chat overlay's layout is unchanged;
- a manual check in a real browser session against the running app;
- `tests/integration`;
- `scripts/docs/run_kt_checks.py`, whose fixed test selection ran inside the full suite;
- any production action.

The Python test wrapper skips (with a reason) when node, node_modules or Chromium is missing, so a
machine without them does not exercise the browser suite.

## Documentation

- [KT](../../../TECHNICAL_DESIGN.md): §1's PI-target row says SA-001 is implemented and awaits review.
  §10 has a new paragraph with the before/after example, both layers, fail-closed behaviour, the
  cache transition and the test command. §12's status line is updated. The header's `Code inspected`
  revision stays `4c4728a`, and `chat-markdown.js` is named in text, not linked:
  `check_kt_docs.py` rejects links to files absent at the header revision. The paragraph is labelled
  "newer than the header revision". **At commit, bump the header** and link the new file.
- The PDF is rebuilt from the edited Markdown.
- [ARCHITECTURE.md](../../../ARCHITECTURE.md): the frontend row states the boundary.
- [CHAT_ARCHITECTURE.md](../../../CHAT_ARCHITECTURE.md): a paragraph on the rendering boundary, and two
  file rows.
- [TEAM_TESTING_GUIDE.md](../../../TEAM_TESTING_GUIDE.md): human case **11-C** now has a concrete
  fixture (`onerror` that would only change the tab title), the expected results, and the fallback to
  engineering's browser test if the model paraphrases.
- CODEBASE.md: the prototypes row names `chat-markdown.js` and the browser test. UI_SPEC.md: the load
  order lists the new scripts.

## Self-review findings (same conversation, not the fresh review)

| # | Severity | Finding | Disposition |
|---|---|---|---|
| S1 | fixed | The first sensitivity run showed that a stale pre-fix `sphere.jsx`, plus a failed `chat-markdown.js` load, still reached `window.marked` and executed the fixture. | Fixed with the inline handoff in index.html; covered by the second `stale cache:` test and the "handoff removed" variant |
| S2 | fixed | Sanitizing alone let an unclosed `<svg>`/`<math>` in a reply swallow all following text (safe, but content silently vanished) | Layer 1: raw HTML is shown as text |
| R1 | low (residual, product) | Any http(s) link the model writes is clickable, so a prompt-injected phishing link is possible. It opens in a new isolated tab, and the URL is visible. | Ordinary Markdown behaviour; no route. Revisit if chat ever shows third-party links without their domain |
| R2 | low (residual, product) | Markdown images and task-list checkboxes no longer render (images dropped; `input` not allowed) | Deliberate (exfiltration); the prompt uses neither |
| R3 | info (defense in depth) | No CSP is sent, and tokens live in web storage | Routed to [SA-028](../stories/SA-028.md) (CSP needs the compiled client; token storage is an explicit decision) |
| R4 | info | For one load after deploy, a user whose old service worker cached `sphere.jsx` sees unformatted (escaped) chat text | Safe; the v8 cache purge fixes it from the next load |
| R5 | info (test) | The browser test replaces `fetch` for the chat endpoints; the server's SSE generator is not run in the browser. `serverChunks` copies `_chunk_for_stream`, and the every-prefix tests cover any chunking. | Accepted; the server side has its own Python tests |
| R6 | info | Waits are time-based (20–60 ms token gaps, 1.2 s settle for async handlers). The pre-fix run shows the settle time catches `onerror`. | See the repeat runs above |

No critical or high defect is known. The fresh reviewer should independently:
- re-trace model text to every sink, starting from `ui_data.py`'s `chat_stream`/`chat` and `sphere.jsx`;
- challenge the DOMPurify configuration, especially `ADD_URI_SAFE_ATTR` and the hook;
- re-run the pre-fix fixture: the sensitivity table's first row, or `SA_FRONTEND_ROOT` set to a copy of
  the three pre-fix files.

## Changed files

Tracked, modified (16): `CODEBASE.md`, `docs/ARCHITECTURE.md`, `docs/CHAT_ARCHITECTURE.md`,
`docs/StockAgent-Three-Loops.pdf`, `docs/TEAM_TESTING_GUIDE.md`, `docs/TECHNICAL_DESIGN.md`,
`package-lock.json`, `package.json`, `src/frontend/prototypes/UI_SPEC.md`,
`src/frontend/prototypes/index.html`, `src/frontend/prototypes/sphere.jsx`,
`src/frontend/prototypes/sw.js`, `tests/unit/test_spa_catchall.py`, plus the bookkeeping
`docs/planning/PI-2026-09/STATE.json`, `docs/planning/PI-2026-09/HANDOFF.md` and
`docs/planning/PI-2026-09/stories/SA-028.md` (routed note).

New (6): `src/frontend/prototypes/chat-markdown.js`, `tests/frontend/chat_harness.mjs`,
`tests/frontend/chat_markdown.test.mjs`, `tests/unit/test_chat_markdown_boundary.py`,
`docs/planning/PI-2026-09/evidence/SA-001-manifest.json`, and this receipt.

Written after the manifest (bookkeeping, outside the review input): STATE.json, HANDOFF.md, the SA-028
note, and this receipt. `TEAM_TESTING_GUIDE.md` is CRLF in the worktree and normalises to LF under
`.gitattributes`. node_modules is ignored.

## Rollout (not done; needs the owner)

1. The fresh-session review of this input.
2. Commit, at the owner's word. Bump the KT header revision, and link `chat-markdown.js`, in the same
   or the next commit.
3. **Deploy:** a push redeploys. Push only on the owner's explicit word, in a job-free window (safest
   00:10–06:20 IST; read IST with plain `date`). This is a behaviour change to the served client, so
   avoid the 16:25–17:15 review window too.
4. **Production verification** (after the deploy, read-only apart from one chat turn in an isolated
   test account):
   - open the app twice, so the v8 service worker takes over;
   - run human case 11-C with its non-executing fixture;
   - confirm that the network panel loads `marked@12.0.2` and `dompurify@3.4.16` with status 200 and
     no SRI error.

   Rollback: revert the commit. Never restore the raw `marked.parse` path; if the renderer must go, keep
   the escaped-text fallback.

`production_verification` stays `not_started` until an authorized deploy.
