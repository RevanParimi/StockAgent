# Rules & Constraints

## Absolute Rules

1. **NO CHATBOT WINDOW** anywhere. Not on any page. Not as a floating button.
   Do not implement any chat interface.
   All stock interaction must use: QuickDrawer, VerdictReveal, or route to /analyze.

2. **Auth is mock/localStorage only.** No real backend auth needed.
   Store: `{ user: { name, email, tickers[] }, isLoggedIn }` in Zustand + localStorage.
   Accept any email/password on Sign In.

3. **Graceful fallback to mock data** when backend is not running.
   Show banner: `"Running on demo data — start backend for live analysis"`
   Never crash — always show meaningful UI.

4. **Every component must handle 3 states:**
   - Loading: `<LoadingPulse />` or `<CardSkeleton />`
   - Error: GlassCard with ⚠ + message + Retry button
   - Empty: GlassCard with helpful empty state

5. **TypeScript strict mode.** No `any` types except where absolutely unavoidable
   (e.g., dynamic Lenis import). Use `unknown` + type narrowing instead.

6. **Three.js memory management:**
   - Dispose geometries + materials on unmount
   - Wrap all Canvas scenes in `React.Suspense`
   - Lazy-load all Three.js pages/components
   - Reduce particle counts on mobile

7. **Lenis smooth scroll:** Initialize once in `App.tsx`, wire to GSAP ticker.
   Use `@studio-freight/lenis` v1.0.42.

8. **Zustand persistence:** watchlists + auth must use `zustand/middleware persist`
   with `localStorage` as the storage backend.

9. **No substitutions** to the specified tech stack.

## TypeScript Conventions
- `import type { X }` for type-only imports (required by `verbatimModuleSyntax`)
- No `const enum` (TypeScript 6 `erasableSyntaxOnly`)
- Prefix unused params with `_` if needed to suppress errors
- All event handlers properly typed (no implicit `any`)

## File Naming
- Components: PascalCase `.tsx` (e.g., `AgentCard.tsx`)
- Hooks: camelCase with `use` prefix `.ts` (e.g., `useWebSocket.ts`)
- Types: `src/types/index.ts` — single file for all shared interfaces
- Mocks: `src/mocks/sampleReport.ts`

## Import Alias
Use `@/` for all src imports:
```typescript
import { GlassCard } from '@/components/ui/GlassCard'
import { useStore } from '@/store'
import type { FinalReport } from '@/types'
```

## Styling
- Tailwind v4 utility classes first
- Inline styles only for dynamic values (e.g., cursor position, tilt degrees)
- Never use `!important`
- Dark mode only (no light mode switching)
- Custom CSS classes in `src/index.css` for reusable patterns

## Component Architecture
- Keep components small and focused
- Extract reusable pieces to `src/components/ui/`
- Page-specific components in `src/components/analysis/`, `src/components/watchlist/`, etc.
- No prop drilling beyond 2 levels — use Zustand store

## Performance
- Lazy-load all pages (already done in App.tsx)
- Lazy-load Three.js components (already done in Landing + Auth)
- Use `React.memo` on list items that don't need to re-render
- Use `useCallback` on WebSocket message handlers
