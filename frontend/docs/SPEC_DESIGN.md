# Design System Specification

## Philosophy
**"Bloomberg Terminal meets Apple Vision Pro"**
Dark, premium, cinematic. Data feels alive. Every interaction has weight.

## Color Tokens
Defined in `src/index.css` via `@theme {}` AND as CSS custom properties in `:root`.

```css
/* Backgrounds */
--color-bg-base:     #050810   /* near-black, deep space */
--color-bg-surface:  #0c1120   /* card backgrounds */
--color-bg-elevated: #111827   /* hover states, modals */
--color-border:      #1e293b   /* subtle borders */
--color-border-glow: #334155   /* active borders */

/* Accents */
--color-accent-blue:   #3b82f6  /* primary actions, links */
--color-accent-cyan:   #06b6d4  /* highlights, active nav */
--color-accent-violet: #8b5cf6  /* premium accents */

/* Verdict colors */
--color-buy-strong:  #22c55e   /* STRONG BUY — bright green, glowing */
--color-buy:         #4ade80   /* BUY — softer green */
--color-neutral:     #f59e0b   /* NEUTRAL — amber */
--color-sell:        #f97316   /* SELL — orange */
--color-sell-strong: #ef4444   /* STRONG SELL — red, glowing */

/* Text */
--color-text-primary:   #f1f5f9
--color-text-secondary: #94a3b8
--color-text-muted:     #475569
```

## Typography
- **Headings**: Inter, font-weight 700/800
- **Body**: Inter, font-weight 400/500
- **Mono** (ticker symbols, scores): JetBrains Mono

Loaded via Google Fonts in `index.html`.

## Glassmorphism Card (`.glass-card` utility class)
```css
background: rgba(12, 17, 32, 0.7);
backdrop-filter: blur(20px);
border: 1px solid rgba(30, 41, 59, 0.8);
border-radius: 16px;
```
Usage: `<div className="glass-card p-4">` or via `<GlassCard>` component.

## Verdict Badge Glow (CSS classes)
```
.glow-strong-buy  → box-shadow: 0 0 20px rgba(34,197,94,0.4)
.glow-buy         → box-shadow: 0 0 12px rgba(74,222,128,0.3)
.glow-neutral     → box-shadow: 0 0 12px rgba(245,158,11,0.3)
.glow-sell        → box-shadow: 0 0 12px rgba(249,115,22,0.3)
.glow-strong-sell → box-shadow: 0 0 20px rgba(239,68,68,0.4)
```

## Shared UI Components (all in `src/components/ui/`)
| Component | Props | Purpose |
|-----------|-------|---------|
| `GlassCard` | `children, className, onClick, hover` | Glassmorphism card wrapper |
| `VerdictBadge` | `verdict, size(sm/md/lg), glow` | Color+glow badge for any verdict string |
| `GlowButton` | `variant(cyan/blue/violet/outline), size(sm/md/lg)` | Primary CTA with glow |
| `AnimatedCounter` | `target, duration, decimals, prefix, suffix, trigger` | Count 0→N with easing |
| `LoadingPulse` | `lines` | Skeleton shimmer loader |
| `CardSkeleton` | `className` | Full card skeleton |

## Layout Components (all in `src/components/layout/`)
| Component | Purpose |
|-----------|---------|
| `CustomCursor` | Hidden default cursor; dot + ring + canvas trail |
| `PageTransition` | Framer Motion enter/exit for all pages |
| `Sidebar` | Left nav (Phase 2) |
| `MarketBar` | Top market indices strip (Phase 2) |

## Custom Cursor Behavior
- Default cursor hidden via `cursor: none` on body
- Inner dot: 8px, white, 0ms lag
- Outer ring: 32px, border cyan, 80ms lag
- On hover over buttons/links: ring scales 2× + cyan fill
- Trail: canvas overlay, fading dots at recent cursor positions
- Mobile: restored to default (`pointer: coarse` media query)

## Animations (defined in `src/index.css`)
| Class | Effect |
|-------|--------|
| `.shimmer` | Shimmer gradient scan (skeleton loaders) |
| `.marquee-left` | Infinite left scroll (OEM marquee row 1) |
| `.marquee-right` | Infinite right scroll (OEM marquee row 2) |
| `.float` | Vertical float bob (auth demo cards) |
| `.typewriter::after` | Blinking cursor |

## Responsive Breakpoints
| Breakpoint | Width | Layout |
|------------|-------|--------|
| Mobile | < 768px | Bottom tab bar, 1-col, bottom sheet drawers |
| Tablet | 768–1024px | Icon-only sidebar (72px), 2-col dashboard |
| Desktop | > 1024px | Full sidebar (220px expanded), 3-col dashboard |
