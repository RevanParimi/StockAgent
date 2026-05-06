import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useSectorStore } from '@/stores/sectorStore'
import { useWatchlistStore } from '@/stores/watchlistStore'

// Pages — lazy-loaded for performance
const HomePage       = React.lazy(() => import('@/pages/home'))
const AgentsPage     = React.lazy(() => import('@/pages/agents'))
const AnalysisPage   = React.lazy(() => import('@/pages/analysis'))
const PortfolioPage  = React.lazy(() => import('@/pages/portfolio'))
const LearnPage      = React.lazy(() => import('@/pages/learn'))

export default function App() {
  const loadBootstrap   = useSectorStore(s => s.loadBootstrap)
  const fetchWatchlist  = useWatchlistStore(s => s.fetchWatchlist)

  // Bootstrap data on mount
  useEffect(() => {
    loadBootstrap()
    fetchWatchlist()
  }, [])

  return (
    <BrowserRouter>
      <React.Suspense fallback={<div style={{ display: 'grid', placeItems: 'center', height: '100vh', fontSize: 14, color: '#64748b' }}>Loading…</div>}>
        <Routes>
          <Route path="/"          element={<HomePage />} />
          <Route path="/agents"    element={<AgentsPage />} />
          <Route path="/analysis"  element={<AnalysisPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/learn"     element={<LearnPage />} />
          <Route path="*"          element={<Navigate to="/" replace />} />
        </Routes>
      </React.Suspense>
    </BrowserRouter>
  )
}
