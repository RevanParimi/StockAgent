# StockAgent Design System

> **Bloomberg Terminal meets Apple Vision Pro.** Dark, premium, cinematic. Data feels alive. Every interaction has weight.

## What is StockAgent?

StockAgent is an **AI-powered multi-agent stock analysis system** for Indian equities (currently Automobile sector on NSE/BSE; Banking, IT, and Renewable sectors are being rolled in). A user types a ticker (e.g. `MARUTI`, `TATAMOTORS`), and **8 specialized LLM agents run in parallel** — each an expert in one lens:

| Agent | Lens |
|---|---|
| `sales_demand` | Monthly dispatch / volume momentum |
| `fundamentals` | Financial statements, margins, cash flow |
| `pattern_analysis` | Technicals / chart patterns / RSI / MACD |
| `raw_materials` | Steel, aluminium, rubber, crude input costs |
| `sentiment` | News and social chatter |
| `policy_regulatory` | PLI, emissions, scrappage, EV policy |
| `competitive_intel` | Peer positioning, market-share moves |
| `risk_macro` | Currency, rates, crude, geopolitics |

A **Signal Aggregator** weights each agent's 0–1 score and produces:
- A composite **`final_score`** (0.00 → 1.00)
- A **`verdict`**: `STRONG BUY` · `BUY` · `NEUTRAL` · `SELL` · `STRONG SELL`
- **Conviction drivers** (reasons to buy)
- **Top risks** (reasons to worry)
- **Conflicts resolved** (when two agents disagree, the LLM picks a side and explains)
- A free-form **investment thesis** paragraph

Results stream live to the frontend via a **WebSocket** at `/ws/stream?ticker=X`, one `agent_progress` event per agent as it finishes, then one final `complete` event with the full report.

## Products / surfaces represented

StockAgent is **one web product** with several pages. This design system recreates the **analysis + dashboard** surface — the flagship experience.

| Page | Role |
|---|---|
| **Landing** | Marketing page with Three.js globe of Indian auto hubs |
| **Auth** | Mock sign-in (localStorage only) |
| **Dashboard** | Portfolio-at-a-glance: watchlist, mood, recent analyses, scheduler |
| **Analyze** ⭐ | Flagship: ticker search → live WebSocket stream of 8 agents → verdict reveal → radar + thesis |
| **Watchlist** | Manage tracked tickers |
| **History** | Score trend charts |

The UI kit focuses on the **Analyze** flow, because that's what the prompt is asking for ("9 agent scores as animated radial gauges, verdict hero card, streams from /stream WebSocket").

> **Note on "9 agents":** the codebase today ships with **8** sector agents (the list above) plus a **Signal Aggregator** that some docs count as a 9th. The UI kit renders all 8 as individual agent cards and shows the Aggregator as the verdict card — treat the "9th" as the composite if you want nine gauges.

## Sources

- **Repository:** [RevanParimi/StockAgent](https://github.com/RevanParimi/StockAgent)
- **Primary design spec:** `frontend/docs/SPEC_DESIGN.md`
- **3D / motion spec:** `frontend/docs/SPEC_3D_EFFECTS.md`
- **Flagship page spec:** `frontend/docs/SPEC_PHASE3.md`
- **Tokens source of truth:** `frontend/src/index.css` (Tailwind v4 `@theme {}` block)
- **Component reference:** mirrored locally into `ui_kits/stockagent/_ref/`

---

## Content fundamentals

**Voice.** Crisp, clinical, money-manager. Think Bloomberg terminal headlines — data-forward, never cutesy. First person is avoided; the product states facts about tickers, not feelings about them. Numbers are always framed with their lens ("composite", "conviction", "dispatch growth") so the user knows what's being measured.

**Person.** Prefers **"Your"** to talk to the user (`Your Watchlist`, `Your portfolio at a glance`) and **the subject ticker** ("Maruti Suzuki remains the structural beneficiary…") for analysis copy. Never "we" or "our AI".

**Casing.**
- **Title Case** for card headers and section titles: *Portfolio Mood*, *Recent Analyses*, *Conviction Drivers*, *Score Leaders*.
- **UPPERCASE** for verdict badges and ticker symbols: `STRONG BUY`, `MARUTI`, `TATAMOTORS`. These never appear lowercase.
- **Sentence case** for descriptions, placeholders, tooltips: *"Verdict distribution across watchlist"*.
- **lowercase + mono** for meta/status chips: `5 tickers queued`, `47s`, `28 days`.

**Tone examples** (pulled verbatim from the product):
- Hero subhead: *"8 specialized AI agents run in parallel to produce a composite conviction score."*
- Empty state: *"No tickers yet · + Add tickers"*
- Degraded state: *"Running on demo data — start backend for live analysis"*
- Status line: *"Report generated in 47s · 8 agents · 2 conflicts resolved by LLM"*
- Thesis opener: *"Maruti Suzuki remains the structural beneficiary of India's four-wheeler penetration story, commanding 42% market share in a market growing at 8% CAGR."*

**Punctuation.** Middle-dot separators (`·`) between meta fragments — never pipes or slashes. En-dashes for ranges (`0.75–1.00`). Periods are used at the end of full sentences; **omit them** in chips, buttons, and single-clause stats.

**Numbers.**
- Composite scores → 2 decimals: `0.82`, `0.47`.
- Percentages → no decimals in UI chrome: `42% market share`, `80bps`.
- Currency → **Indian format with crore abbreviation** when appropriate: `₹38,000 Cr net cash`.
- Tickers are monospace, always.

**Emoji.** Yes — but **only** as agent-slot icons inside the `AgentCard` grid (`📊 📈 🔍 ⚙️ 💬 📋 🎯 ⚠️`). Never in marketing copy, CTAs, thesis text, or headers. This is the one place the otherwise-cold UI lets some personality in.

**Vibe words.** *cinematic · premium · data-alive · weight · conviction · glow · cold-blue · verdict.*

---

## Visual foundations

### Palette

Near-black deep-space background with **electric cyan** as the primary accent. Verdicts are the only other saturated color: **green** climbs to `STRONG BUY`, **amber** sits at `NEUTRAL`, **red** drops to `STRONG SELL`. No other colors exist in the UI.

| Token | Hex | Use |
|---|---|---|
| `--bg-base` | `#050810` | Page background — near-black with blue bias |
| `--bg-surface` | `#0c1120` | Card background under glass |
| `--bg-elevated` | `#111827` | Hover, modals, popovers |
| `--border-color` | `#1e293b` | Default card/divider border |
| `--border-glow` | `#334155` | Active / focused border |
| `--accent-cyan` | `#06b6d4` | **Primary accent** — CTAs, active nav, in-flight state |
| `--accent-blue` | `#3b82f6` | Secondary accent, gradient stops |
| `--accent-violet` | `#8b5cf6` | Premium / rare highlight |
| `--buy-strong` | `#22c55e` | STRONG BUY, score ≥ 0.75 |
| `--buy` | `#4ade80` | BUY, 0.60–0.74 |
| `--neutral-color` | `#f59e0b` | NEUTRAL, 0.45–0.59 |
| `--sell` | `#f97316` | SELL, 0.30–0.44 |
| `--sell-strong` | `#ef4444` | STRONG SELL, < 0.30 |
| `--text-primary` | `#f1f5f9` | Default foreground |
| `--text-secondary` | `#94a3b8` | Subheadings, helper text |
| `--text-muted` | `#475569` | Labels, timestamps, axis ticks |

### Typography

- **Sans (headings + body):** Inter — 400 / 500 / 700 / 800.
- **Mono (tickers, scores, timestamps, elapsed time):** JetBrains Mono — 400 / 500 / 700.
- Font rhythm is **tight and dense**: `letter-spacing: -0.01em` on headings, default elsewhere. `tabular-nums` is always on for anything numeric so digits don't jitter as they animate.
- Hero gauge score uses 48px bold; card titles are 14–16px semibold; body is 13–14px; meta chips are 10–11px.

### Cards — "glass-card"

The workhorse container. **Not** a flat dark panel — it's specifically a glassmorphism tile:
```css
background: rgba(12, 17, 32, 0.7);
backdrop-filter: blur(20px);
border: 1px solid rgba(30, 41, 59, 0.8);
border-radius: 16px;
padding: 16–20px;
```
Corner radius is **16px** for cards, **12px** for inner items (agent tiles), **999px** for pills/badges. No card has a drop-shadow by default — the shadow is reserved for **verdict glow** (see below). Sub-items inside a card use a subtle translucent fill on hover: `background: rgba(255,255,255,0.04)`.

### Glow system (reserved for verdict)

Drop-shadows are not decorative — they are **signal**. A glow on an element means "this has a verdict attached".
```
.glow-strong-buy   → box-shadow: 0 0 20px rgba(34,197,94,0.4)
.glow-buy          → box-shadow: 0 0 12px rgba(74,222,128,0.3)
.glow-neutral      → box-shadow: 0 0 12px rgba(245,158,11,0.3)
.glow-sell         → box-shadow: 0 0 12px rgba(249,115,22,0.3)
.glow-strong-sell  → box-shadow: 0 0 20px rgba(239,68,68,0.4)
```
The hero `VerdictReveal` additionally pulses. Never apply a verdict glow to neutral chrome — it breaks the signal.

### Backgrounds & imagery

- **No gradients** across content areas — the base is a flat near-black. Gradients appear only (a) inside progress bars, left→right cyan→blue, and (b) behind the Three.js globe on Landing.
- **No photography.** The product has zero photos of people, offices, or stock imagery. It is pure data UI.
- **3D Three.js decorations** are used sparingly: a slow-rotating wireframe globe with glowing city nodes on Landing; a particle field on Auth; drifting ticker text behind the hero. Always wrapped in `React.Suspense`, always disabled on mobile.
- The only "texture" is the glassmorphism blur + the custom cursor's fading dot trail (canvas overlay, alpha-multiplied each RAF frame by 0.92).

### Animation

Motion is **deliberate and restrained** — every animation has a purpose (reveal a score, signal progress, confirm a completion).

- **Easing:** `cubic-bezier(0.4, 0, 0.2, 1)` (Framer default "easeInOut") for almost everything. `easeOut` for reveals, `easeIn` for exits.
- **Durations:** 200ms for hover, 300–400ms for state changes, 700ms for the verdict card flip, 1500ms for the gauge needle sweep and composite counter.
- **Signature moves:**
  - **Card flip** on `VerdictReveal`: 180° Y-rotation, 700ms, reveals gauge + counter + badge.
  - **Gauge needle sweep** — RAF-driven `1 - Math.pow(1 - t, 3)` cubic ease-out over 1.5s, ending with drop-shadow glow in the zone color.
  - **Agent card "spring pop"** on complete — `scale: [1, 1.05, 1]` over 400ms, then the border swaps to the verdict color with its matching glow.
  - **In-flight shimmer** — a 1.2s looping bar moving `-100% → 100%` horizontally inside an analyzing agent card.
  - **Score counter** — `AnimatedCounter` with easing from 0 to target over 1.5s.
- **No bounces, no elastic, no confetti.** Everything settles cleanly.

### Hover, press, focus

- **Hover on a glass-card:** border brightens from `--border-color` to `--border-glow`; no scale change unless explicitly opted in with `hover` prop (which adds `scale(1.02)`).
- **Hover on a `GlowButton`:** brightness × 1.1 and a `0 0 24px` colored shadow appears underneath.
- **Hover on a row/list item:** background fades in to `rgba(255,255,255,0.04)`; arrow glyph appears on the right in cyan.
- **Press:** no scale-down. Buttons flash via `:active` brightness.
- **Focus-visible:** 2px solid `--accent-cyan` outline with 2px offset. Non-negotiable — visible on every interactive element.

### Transparency & blur

Glass is load-bearing. Nearly every card uses `backdrop-filter: blur(20px)` over `rgba(12,17,32,0.7)`. Because the background is essentially flat, the blur doesn't do much visually — but it guarantees modals and drawers feel weightless over the content. Semi-transparent fills (`rgba(255,255,255,0.02 / 0.04 / 0.08)`) build elevation without needing new colors.

### Custom cursor

The default cursor is **hidden** on desktop (`cursor: none` on body). It is replaced by a small white dot + a 32px cyan ring that lags ~80ms behind, plus a canvas-rendered fading dot trail. On touch devices (`pointer: coarse`) the default cursor is restored.

### Spacing / radii / scale

| Token | Value |
|---|---|
| Grid gap (card gutters) | 16px (`gap-4`) or 20px (`gap-5`) |
| Page padding | 24px (`p-6`) desktop, 16px mobile |
| Card inner padding | 16–20px |
| Radius — card | 16px |
| Radius — inner tile | 12px |
| Radius — pill / badge | 999px |
| Border width | 1px everywhere |
| Max content width | 1600px (Dashboard), 960px (Analyze) |
| Agent grid | 2 × 4 on desktop, 1 × 8 on mobile |

### Layout rules

- Page has a persistent top `MarketBar` (indices strip) and a left `Sidebar` (220px expanded / 72px icon-only). On mobile, sidebar collapses into a `BottomNav`.
- Dashboard is **3 columns**: `28% · 1fr · 28%` — watchlist | mood+recent | scheduler+leaders.
- Analyze is **single-column**, center-biased, max-width 960px. Results unlock a 55/45 two-column block below the verdict.
- Content is always on `--bg-base`; cards float above it. Never nest glass-cards inside glass-cards (use `rgba(255,255,255,0.04)` subtiles).

---

## Iconography

**Source.** `lucide-react` (v1.8.0) is the official icon library — used everywhere in the product: `Plus`, `Clock`, `PlayCircle`, `Trophy`, `RotateCcw`, `Clipboard`, `Download`, `Printer`, `Search`, `ChevronRight`, `X`, etc. Strokes are **1.5–2px**, rounded caps, line style (no fill). Sizes cluster around **13px** (inline chips), **14–16px** (buttons, row leaders), **20–24px** (section headers).

The public icon-sprite file (`frontend/public/icons.svg`) ships with the Vite starter's social icons (GitHub, X, Bluesky, Discord) and is **not** used in product chrome — safe to ignore.

**Agent slot icons.** The 8 agent cards use emoji (`📊 📈 🔍 ⚙️ 💬 📋 🎯 ⚠️`), mapped one-to-one in `AgentCard.tsx`. This is the only emoji usage in the product and is deliberate — it gives each specialist agent a distinct glanceable face.

**Unicode as icons.** `·` (middle-dot) is used as a separator in meta lines; `→` appears as a hover affordance on list rows; `✓` / `✗` appear as bullet prefixes in `ConvictionPanel` (paired with colored `CheckCircle` / `XCircle` icons). Arrows/chevrons elsewhere are always Lucide SVGs.

**Logo.** There is no dedicated "StockAgent" wordmark or logo asset in the repo. The Landing page relies on the Three.js globe as its identity moment. This design system ships a **placeholder wordmark** (`StockAgent` in Inter Bold with a cyan leading dot) in `ui_kits/stockagent/Brand.jsx` — **ask the user to provide a real mark** to replace it.

**⚠ Flagged assets.**
- `public/favicon.svg` is the Vite starter's purple lightning bolt — **not** a StockAgent mark. Discarded here.
- `public/icons.svg` is the Vite starter's social-sprite — not used in product chrome. Discarded here.
- **No logo file exists.** Placeholder supplied; please provide a real one.

---

## Fonts

Loaded from Google Fonts via `<link>` in `index.html`. This design system references them the same way (CDN).

- **Inter** — 400, 500, 700, 800 → `https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800`
- **JetBrains Mono** — 400, 500, 700 → `https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700`

Both are first-party Google Fonts in the original product — **no substitutions were made**.

---

## Index

| Path | Purpose |
|---|---|
| `README.md` | This file |
| `SKILL.md` | Claude skill manifest (cross-compatible with Agent Skills) |
| `colors_and_type.css` | Token layer — CSS variables + semantic classes |
| `assets/` | Logos, icons, brand placeholders |
| `preview/` | Static cards that populate the Design System tab |
| `ui_kits/stockagent/` | Full UI kit — Analyze page recreation |
| `ui_kits/stockagent/_ref/` | Verbatim TSX pulled from the upstream repo for reference only |

## Caveats

- No real logo was provided in the repo; a placeholder wordmark has been supplied.
- The 3D Three.js globe/particle field is documented but **not reproduced** in the UI kit — they are Landing-page chrome, not Analyze chrome, and would add heavy runtime cost to a prototype. Swap in via the reference components under `_ref/three/` if needed.
- The UI kit uses **inline React (Babel) + Tailwind CDN**, not Vite + Tailwind v4 `@theme`, so a few token names are flattened into utility-class equivalents.
