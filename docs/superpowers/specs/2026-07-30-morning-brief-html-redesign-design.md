# Morning Brief — HTML Email Redesign + Data Engineering — Design Spec

**Date:** 2026-07-30
**Author:** Claude (Opus 4.8) with Revan
**Status:** Approved (design), pending spec review
**Builds on:** [2026-07-27 brief redesign](2026-07-27-morning-brief-redesign-design.md), [2026-07-28 brief enhancements](2026-07-28-brief-enhancements-design.md)
**Touches:** `core/delivery/brief.py`, `core/delivery/channels.py`, `core/delivery/outbox.py`, `config.yaml`, `src/backend/shared/config/settings/base.py`, `tests/unit/test_delivery_brief.py`, `tests/unit/test_delivery_channels*.py`
**Mockup:** https://claude.ai/code/artifact/dca73151-ce40-4f5a-8b08-d6109eb24b33

---

## 1. Goal

Two linked upgrades to the 08:50 IST morning brief, keeping the **research-framed,
never-advice** stance and the **single BULK LLM call** cost:

1. **Styled HTML email.** The brief email currently ships as `MIMEText(body, "plain")` —
   the "notepad lines" the user sees. Send it instead as **`multipart/alternative`**: the
   existing plain text as the fallback part, plus a new **email-safe HTML** part rendered
   from the same brief dict. One shared template ⇒ every brief has identical structure,
   produced in the delivery ("mediator") layer. Clean-fintech visual style (approved).

2. **Data engineering.** Four correctness/clarity fixes to the brief *content* (they benefit
   both the HTML and text renderings, since data is shared): de-dup overnight news, richer
   portfolio line, sharper "why it matters", and less summary/bullet echo.

## 2. Non-goals

- **No new channels or hosted page.** HTML is email-only. Web-push and the in-app Inbox keep
  the plain-text `body` unchanged (push is OS-level; Inbox renders the text today). No
  "view in browser" route.
- **No new LLM calls.** HTML rendering and de-dup are deterministic; the "why it matters" and
  summary changes are prompt-only tweaks to the *existing* single narration call.
- **No personal advice / no GMP / no listing-gain** — unchanged stance.
- **No change to the brief schema or storage.** `build_morning_brief`'s dict is the single
  source; both renderers are pure functions of it.
- No webfonts. Email clients don't load `@font-face` reliably, so the template uses a
  system-font stack by design (this is the honest, faithful choice for the medium).

## 3. Architecture / plumbing

### 3.1 New renderer `render_brief_html(brief: dict) -> str` (`core/delivery/brief.py`)
- Mirrors `render_brief_text` **section-for-section** (Summary → Portfolio → Needs-attention →
  Market conditions → Overnight → Earnings → Ideas → IPOs → Lock-in), same auto-hide-when-empty
  rule, **never raises** (any failure ⇒ caller falls back to text-only email).
- Emits a **full standalone HTML document** (`<!doctype html>…</html>`) — email needs the whole
  doc, unlike Artifacts. Returns a `str`.
- **Email-safety rules (hard constraints):**
  - Table-based layout (`role="presentation"`), max-width 600px centered column.
  - **Inline `style="…"` on every element** that must render in Gmail/Outlook. A single
    `<style>` block in `<head>` carries only the `@media (prefers-color-scheme: dark)` overrides
    and `@media` width tweaks (progressive enhancement — clients that drop `<style>` still get
    the inlined light theme).
  - System-font stack; `font-variant-numeric: tabular-nums` on figures.
  - No external images (dark-mode-fragile, blocked-by-default). Unicode marks (▼ ▲ ·) only.
  - Semantic color (down `--neg`, up `--pos`, warning `--warn`) is separate from the teal accent.
  - Bulletproof footer button (padded anchor, no image).
- Colors/typography come from **module-level constants** (a small `_HTML_TOKENS` dict) so the
  palette is defined once; caps/thresholds that already exist stay in `cfg()`.

### 3.2 Thread `html_body` through delivery (`core/delivery/channels.py`)
- `send_email(subject, body, attachments=None, html_body: str | None = None)`:
  - When `html_body` is set and no attachments → build `MIMEMultipart("alternative")` with
    `MIMEText(body, "plain")` **then** `MIMEText(html_body, "html")` (order matters: last part
    is the client's preferred one).
  - When `html_body` is set **and** attachments exist → outer `MIMEMultipart("mixed")` whose
    first child is the `alternative` part, then the attachments (preserves AUD-088 behavior).
  - `html_body=None` → byte-for-byte today's plain path. `_with_app_link` still appends the
    text footer to the **plain part**; the HTML part has its own "Open StockAgent" button.
- `deliver(title, body, url, user_id, kind, html_body: str | None = None)`:
  - Passes `html_body` to `send_email`. **Push is unchanged** (`send_push` gets only `body`).
  - Outbox path: see 3.3.
- `run_morning_brief` computes `html_body = render_brief_html(brief)` **only when
  `cfg("delivery.brief_html_enabled")` is true** (§6 escape hatch), else `html_body=None`.
  The `render_brief_html` call is wrapped so a renderer failure also degrades to
  `html_body=None` (text-only email) rather than dropping the brief.

### 3.3 Outbox carry-through (`core/delivery/outbox.py`) — Atlas-safety
Atlas is dormant today, but its durable outbox would lose the HTML at the `ATLAS_ENABLED` flip
(Aug 1-2). The outbox already stores its payload **inline as JSON** in `payload_ref`
(`{title, body, url}`), so **no schema change is needed** — carry HTML in that JSON:
- `enqueue_message(..., html_body: str | None = None)` stores `payload_ref =
  {title, body, url, html}` (`html` omitted/None when absent).
- **Move the 1500-char cap out of enqueue** (`body[:1500]`): store the **full** `body`/`html` in
  the payload; apply the push cap at *send* time instead. This fixes a latent bug where the
  current enqueue would truncate an email body to 1500 chars, and lets the email row carry the
  full text + HTML. (Rows for the email channel grow to a brief's size ~10–20 KB — fine for this
  low-volume single-user table; push rows stay tiny.)
- `_send_row`: push → `send_push(title, body[:1500], …)`; email →
  `send_email(title, body, html_body=payload.get("html"))`.

### 3.4 What stays exactly the same
- `render_brief_text` — unchanged output (it is the fallback part **and** push/Inbox body).
- `build_morning_brief` schema, `_narrate_brief`'s single call, all section collectors' contracts.
- `DELIVERY_ENABLED` / `DELIVERY_EMAIL_ENABLED` gating.

## 4. HTML template design (clean fintech — approved mockup)

**Tokens (light / dark):**
| Role | Light | Dark |
|------|-------|------|
| page bg | `#e9eef3` | `#0a0f1a` |
| card | `#ffffff` | `#111a2b` |
| ink (headings) | `#0f172a` | `#f1f5f9` |
| body | `#334155` | `#cbd5e1` |
| muted | `#64748b` | `#94a3b8` |
| hairline | `#e4e9f0` | `#233149` |
| accent (teal) | `#0f766e` | `#2dd4bf` |
| accent-deep (bands/btn) | `#115e59` | `#0d9488` |
| negative | `#b91c1c` | `#f87171` |
| positive | `#15803d` | `#4ade80` |
| warning | `#b45309` | `#fbbf24` |

Neutrals carry a slight cool/slate bias toward the teal accent (chosen, not default grey).

**Structure (per the mockup):**
- **Header band** (accent-deep): eyebrow "StockAgent · Personal research", "Morning Brief", full date.
- **Summary**: one lede paragraph, high-level (regime + theme), key figures bolded.
- **Portfolio KPI card**: large `₹` value (tabular-nums), a since-inception chip colored by sign,
  a meta sub-line (holdings count · best · worst) and yesterday's realized exit.
- **Needs attention** (only when `advisor_flags`): stacked rows, plain verb + reason.
- **Market conditions**: state pill (`Steady · NORMAL`) + one-line gloss.
- **Overnight / Earnings / IPOs / Lock-in**: 2-column data tables (Story + "why"/tag | severity or figure).
- **Footer**: research-tone disclaimer + "Open StockAgent →" button + generated-at line.
- Every section auto-hides when its data is empty (same rule as text).

## 5. Data engineering (the four fixes)

### 5.1 De-dup overnight (deterministic)
The current `_dedup_overnight` uses prefix + Jaccard token overlap; it missed the two NRI/OCI
items (`"Govt raises equity limits for NRIs, OCIs…"` vs `"RBI increases NRI/OCI investment limits
without SEBI registration"`) because raw token overlap fell below threshold.
- Add **salient-token clustering**: extract a small set of *significant* tokens per headline
  (drop stopwords + generic finance words via a config stoplist; treat `NRI`/`OCI`/`SEBI` and
  numbers as high-weight entities). Two items merge when they share ≥ N salient entities OR
  Jaccard ≥ threshold (existing). Keep the richest/longest phrasing for the surviving row.
- All knobs config-driven: `delivery.brief_overnight_dedup_min_shared_entities` (default `2`),
  reuse existing `brief_overnight_dedup_threshold`. Stoplist `delivery.brief_overnight_stopwords`.
- Degrades to today's behavior if the salient set is empty.

### 5.2 Richer portfolio line (deterministic, from the digest)
`build_morning_brief` already loads the digest. Compute at build time and attach to
`brief["portfolio"]`:
- `holdings_count`, `all_below_cost` (bool), `best` = `{symbol, pnl_pct}` (max pnl_pct),
  `worst` = `{symbol, pnl_pct}` (min pnl_pct).
- `last_exit` = most recent realized SELL from `digest["trades"]` (symbol, realized pnl_pct)
  if present that day, else omitted.
- Renderers show these in the KPI card sub-line (HTML) and a `YOUR PORTFOLIO` sub-line (text).
  All fields optional ⇒ degrade cleanly when the digest lacks them.

### 5.3 Sharper "why it matters" (prompt-only, same single call)
Tighten `_PROMPT`'s `overnight_notes` instruction: each note must state **one distinct,
portfolio-relevant consequence** (Indian-equity angle), **must not repeat wording** across
items, ≤ 12 words. Add a deterministic post-filter that drops a note if it is near-duplicate of a
prior note (reuse `_norm_text` overlap) ⇒ blank rather than echo.

### 5.4 Less summary/bullet echo (prompt-only)
Tighten the headline instruction: the summary should give **regime + the day's theme + portfolio
posture**, and **must not enumerate the individual overnight items** (those appear as bullets).
2–4 sentences, research tone, unchanged fallback.

## 6. Config additions (`delivery.*`; config-over-hardcode, no env=)
| Key | Default | Meaning |
|-----|---------|---------|
| `delivery.brief_overnight_dedup_min_shared_entities` | `2` | ≥ this many shared salient entities ⇒ merge overnight items |
| `delivery.brief_overnight_stopwords` | (curated list) | tokens ignored when extracting salient entities |
| `delivery.brief_html_enabled` | `true` | master switch for the HTML email part (false ⇒ text-only email, instant revert) |

`brief_html_enabled` is the escape hatch: flip to `false` in `config.yaml` + redeploy to return
to plain-text email with zero code change. (config.yaml-only, per no-env-for-toggles.)

## 7. Testing
`tests/unit/test_delivery_brief.py`:
1. `render_brief_html` golden: full brief → contains header band, KPI value, deduped overnight
   rows, tables; **never raises** on a minimal/empty brief; empty sections absent from output.
2. HTML safety asserts: has `<!doctype html>`, `multipart`-ready string, inline `style=` on
   table cells, no `<script>`, no external `http(s)://` image `src`.
3. De-dup: the two real NRI/OCI headlines collapse to one row; unrelated rupee item survives
   (3 → 2). Regression fixture from the 2026-07-29 brief.
4. Portfolio enrichment: digest with 8 holdings → best/worst/count computed; digest with a SELL
   trade → `last_exit` present; empty digest → fields absent, no crash.
5. "why it matters" post-filter: near-duplicate notes → second blanked.

`tests/unit/test_delivery_channels*.py`:
6. `send_email` with `html_body` → message is `multipart/alternative`, has both `text/plain` and
   `text/html` parts, html part last; with attachments → `mixed` wrapping `alternative`.
7. `send_email` with `html_body=None` → byte-identical to today's plain `MIMEText`.
8. `deliver(html_body=…)` → push still receives plain `body`; outbox enqueues html when Atlas on.

Full-suite fail-set must stay green (baseline is now GREEN 2292P/0F/0E as of 2026-07-29) — any
new failure is a real regression.

## 8. Rollout / risk
- **Additive + guarded.** `html_body=None` path is byte-for-byte today's behavior; renderer
  wrapped so a failure ⇒ text-only email (brief never dropped). `brief_html_enabled=false` is a
  one-line revert.
- **Deploy-kill window:** do NOT push to main 16:25–17:15 IST on trading days. First delivered
  HTML brief = the 08:50 IST run after deploy.
- **Atlas interplay:** outbox `html_body` carry-through lands *before* the Aug 1-2 cutover so the
  HTML survives the `ATLAS_ENABLED` flip; verify in the cutover §6 checklist.
- **Client rendering:** primary target is Gmail (mobile + web, the user's client). Outlook dark
  mode is best-effort; the inlined light theme is the guaranteed floor everywhere.
- **Cost:** unchanged — one BULK narration call/brief; all new logic deterministic.
