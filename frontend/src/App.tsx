import { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { CustomCursor } from '@/components/layout/CustomCursor'
import { PageTransition } from '@/components/layout/PageTransition'
import { Landing } from '@/pages/Landing'
import { Auth } from '@/pages/Auth'
import { useStore } from '@/store'

// Lazy-load authenticated pages (Phase 2/3/4)
const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })))
const Watchlist  = lazy(() => import('@/pages/Watchlist').then(m => ({ default: m.Watchlist })))
const Analyze    = lazy(() => import('@/pages/Analyze').then(m => ({ default: m.Analyze })))
const History    = lazy(() => import('@/pages/History').then(m => ({ default: m.History })))

gsap.registerPlugin(ScrollTrigger)

// Protected route wrapper
function Protected({ children }: { children: React.ReactNode }) {
  const isLoggedIn = useStore(s => s.isLoggedIn)
  if (!isLoggedIn) return <Navigate to="/auth" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <PageTransition>
      <Routes>
        <Route path="/"          element={<Landing />} />
        <Route path="/auth"      element={<Auth />} />
        <Route path="/dashboard" element={<Protected><Suspense fallback={<PageLoader />}><Dashboard /></Suspense></Protected>} />
        <Route path="/watchlist" element={<Protected><Suspense fallback={<PageLoader />}><Watchlist /></Suspense></Protected>} />
        <Route path="/analyze"   element={<Protected><Suspense fallback={<PageLoader />}><Analyze /></Suspense></Protected>} />
        <Route path="/history"   element={<Protected><Suspense fallback={<PageLoader />}><History /></Suspense></Protected>} />
        <Route path="*"          element={<Navigate to="/" replace />} />
      </Routes>
    </PageTransition>
  )
}

function PageLoader() {
  return (
    <div className="h-screen flex items-center justify-center bg-[var(--bg-base)]">
      <div className="flex flex-col items-center gap-4">
        <div className="w-8 h-8 rounded-lg bg-[var(--accent-cyan)] animate-pulse" />
        <span className="text-[var(--text-muted)] text-sm">Loading...</span>
      </div>
    </div>
  )
}

export default function App() {
  useEffect(() => {
    // GSAP + Lenis smooth scroll integration
    let lenis: { raf: (t: number) => void; destroy: () => void } | null = null

    async function initLenis() {
      try {
        const LenisModule = await import('@studio-freight/lenis')
        const LenisClass = LenisModule.default ?? LenisModule
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const instance = new (LenisClass as new (opts: object) => any)({ lerp: 0.08, smoothWheel: true })
        lenis = instance as { raf: (t: number) => void; destroy: () => void }
        gsap.ticker.add((t) => instance?.raf(t * 1000))
        gsap.ticker.lagSmoothing(0)
      } catch {
        // Lenis not available — fall back to native scroll
      }
    }

    initLenis()

    return () => {
      lenis?.destroy()
      gsap.ticker.remove((t) => lenis?.raf(t * 1000))
    }
  }, [])

  return (
    <BrowserRouter>
      <CustomCursor />
      <AppRoutes />
    </BrowserRouter>
  )
}
