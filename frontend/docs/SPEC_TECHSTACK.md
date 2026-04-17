# Tech Stack Specification

> Use exactly this stack — no substitutions.

## Core
| Package | Version Installed | Purpose |
|---------|-------------------|---------|
| React | 19.x | UI framework |
| TypeScript | 6.x (strict mode) | Type safety |
| Vite | 8.x | Build tool (output to `frontend/dist`) |

## Installed Package Versions (from package.json)
```json
{
  "@gsap/react": "^2.1.2",
  "@react-three/drei": "^10.7.7",
  "@react-three/fiber": "^9.6.0",
  "@studio-freight/lenis": "^1.0.42",
  "@tailwindcss/vite": "^4.2.2",
  "axios": "^1.15.0",
  "date-fns": "^4.1.0",
  "framer-motion": "^12.38.0",
  "gsap": "^3.15.0",
  "lucide-react": "^1.8.0",
  "react": "^19.2.4",
  "react-dom": "^19.2.4",
  "react-router-dom": "^7.14.1",
  "recharts": "^3.8.1",
  "tailwindcss": "^4.2.2",
  "three": "^0.184.0",
  "zustand": "^5.0.12"
}
```

## Stack Details
| Concern | Library | Notes |
|---------|---------|-------|
| 3D | @react-three/fiber + @react-three/drei + three | Lazy-loaded with React.Suspense |
| Animations | framer-motion + gsap + @gsap/react | GSAP for scroll, Framer for transitions |
| Smooth scroll | @studio-freight/lenis | Initialized in App.tsx, wired to GSAP ticker |
| Scroll effects | gsap ScrollTrigger plugin | Registered via `gsap.registerPlugin(ScrollTrigger)` |
| Styling | tailwindcss v4 + @tailwindcss/vite | Config via CSS `@theme {}` block (NO tailwind.config.js) |
| Charts | recharts (radar, line, area) + custom SVG gauge | |
| State | zustand v5 with `persist` middleware | Persists to localStorage |
| Routing | react-router-dom v7 | BrowserRouter + Routes + Route (v6-style API) |
| Icons | lucide-react | |
| HTTP | axios | |
| WebSocket | Native browser WebSocket API | Custom hook in `src/hooks/useWebSocket.ts` |
| Date | date-fns v4 | |
| Auth | Context API + Zustand + localStorage | Mock only — no real backend auth |

## Important Version Notes
- **Tailwind v4**: No `tailwind.config.js`. Config lives in `src/index.css` via `@theme {}`.
  Custom colors defined as `--color-*` become utility classes like `bg-bg-base`, `text-accent-cyan`.
- **React Router v7**: Uses same BrowserRouter/Routes/Route API as v6.
- **framer-motion v12**: `AnimatePresence`, `motion`, `Variants` — same as v11.
- **Zustand v5**: `create<T>()` with `persist` from `zustand/middleware`.

## Project Root
```
frontend/
├── index.html
├── vite.config.ts
├── tsconfig.json + tsconfig.app.json
├── package.json
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css
    ├── pages/
    ├── components/
    ├── hooks/
    ├── store/
    ├── types/
    └── mocks/
```

## Dev Server
```bash
cd frontend && npm run dev
# → http://localhost:5173
```
