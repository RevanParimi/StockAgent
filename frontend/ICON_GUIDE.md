# Agent Icon Guide

Each agent has a placeholder SVG in `frontend/icons/{key}.svg`.
Download the icon you want, save it as the matching filename, and it loads automatically.
The UI falls back to the emoji if the file is missing or fails to load.

---

## Where to Download

| Source | Style | Free? | Format |
|---|---|---|---|
| **[Phosphor Icons](https://phosphoricons.com)** | Clean, duotone, weight variants | Yes | SVG download |
| **[Lucide](https://lucide.dev/icons)** | Minimal line icons | Yes | SVG/React |
| **[Iconify](https://icon-sets.iconify.design)** | 200k+ icons, many sets | Yes | SVG/JSON |
| **[Heroicons](https://heroicons.com)** | Tailwind-aligned, two styles | Yes | SVG copy |
| **[Tabler Icons](https://tabler.io/icons)** | Stroke icons, 5500+ | Yes | SVG download |
| **[Streamline](https://www.streamlinehq.com)** | Illustrated / premium style | Freemium | SVG |
| **[Flaticon](https://www.flaticon.com)** | Coloured, illustrated | Freemium | PNG/SVG |

**Recommended set:** Phosphor Icons (duotone, weight=regular, size 48px) — matches the design language.

---

## File Naming — save as exactly this filename

| Agent | File | Current emoji | Suggested search term |
|---|---|---|---|
| Sales & Demand | `sales_demand.svg` | 📊 | `chart-bar` · `trending-up` · `shop` |
| Fundamentals | `fundamentals.svg` | 📈 | `coins` · `currency-dollar` · `buildings` |
| Pattern Analysis | `pattern_analysis.svg` | 🔍 | `chart-line` · `waveform` · `magnifying-glass-chart` |
| Raw Materials | `raw_materials.svg` | ⚙️ | `factory` · `cube` · `cylinder` |
| Sentiment | `sentiment.svg` | 💬 | `chat-circle` · `newspaper` · `megaphone` |
| Policy & Regulatory | `policy_regulatory.svg` | 📋 | `scales` · `gavel` · `shield-check` |
| Competitive Intel | `competitive_intel.svg` | 🎯 | `target` · `trophy` · `binoculars` |
| Risk & Macro | `risk_macro.svg` | ⚠️ | `warning-circle` · `shield-warning` · `chart-pie` |
| Valuation & Catalyst | `valuation_catalyst.svg` | 💎 | `diamond` · `lightning` · `rocket-launch` |

---

## How to Download from Phosphor Icons

1. Go to [phosphoricons.com](https://phosphoricons.com)
2. Search for the icon (e.g. `chart-bar`)
3. Click the icon → select **Regular** or **Duotone** weight
4. Click **Download SVG**
5. Rename to the filename in the table above
6. Drop into `frontend/icons/`

---

## Sizing & Colour

The icons are displayed at **48 × 48 px** in agent cards and **24 × 24 px** in the pipeline view.
The SVG `fill` and `stroke` colours are overridden by CSS (`color: inherit`), so you don't need
to change the icon's colour — just the file. Monochrome/stroke icons work best.

If you download a coloured icon (Flaticon style), set its fill to `currentColor` in the SVG
or it won't respond to dark mode.

---

## Quick Test

After saving icons, open `http://localhost:8001` and go to the **Agents** page.
Each card should show the SVG instead of the emoji. If you see the emoji, check that:
- The file is in `frontend/icons/` (not a subfolder)
- The filename matches exactly (lowercase, underscores, `.svg` extension)
- The SVG is valid XML (open it in a browser tab to check)
