import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { RotateCcw, Clipboard, Download, Printer } from 'lucide-react'
import { AppLayout } from '@/components/layout/AppLayout'
import { GlowButton } from '@/components/ui/GlowButton'
import { TickerSearch } from '@/components/analysis/TickerSearch'
import { StreamProgress } from '@/components/analysis/StreamProgress'
import { VerdictReveal } from '@/components/analysis/VerdictReveal'
import { AgentRadar } from '@/components/analysis/AgentRadar'
import { AgentScoreTable } from '@/components/analysis/AgentScoreTable'
import { ConvictionPanel } from '@/components/analysis/ConvictionPanel'
import { ConflictsPanel } from '@/components/analysis/ConflictsPanel'
import { ThesisCard } from '@/components/analysis/ThesisCard'
import { HistoryLine } from '@/components/charts/HistoryLine'
import { useAnalysis } from '@/hooks/useAnalysis'
import { AGENT_LABELS } from '@/types'
import { sampleHistory } from '@/mocks/sampleReport'
import axios from 'axios'
import type { ScoreRecord } from '@/types'

export function Analyze() {
  const [searchParams] = useSearchParams()
  const urlTicker = searchParams.get('ticker')

  const analysis = useAnalysis()
  const { status, ticker, agentStates, completedCount, elapsedSeconds, report, error } = analysis

  const resultsRef = useRef<HTMLDivElement>(null)
  const [history, setHistory] = useState<ScoreRecord[]>([])
  const [isMock, setIsMock] = useState(false)

  // Auto-trigger from URL param
  useEffect(() => {
    if (urlTicker && status === 'idle') {
      analysis.startAnalysis(urlTicker.toUpperCase())
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlTicker])

  // Scroll to results when complete
  useEffect(() => {
    if (status === 'complete' && resultsRef.current) {
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 600)
    }
  }, [status])

  // Detect mock mode (WS fell back)
  useEffect(() => {
    if (status === 'streaming') {
      const t = setTimeout(() => setIsMock(true), 3500)
      return () => clearTimeout(t)
    }
    setIsMock(false)
  }, [status])

  // Load history when report arrives
  useEffect(() => {
    if (!report) return
    async function loadHistory() {
      try {
        const res = await axios.get<ScoreRecord[]>(
          `http://localhost:8000/history/${report!.ticker}`
        )
        setHistory(res.data)
      } catch {
        setHistory(sampleHistory)
      }
    }
    loadHistory()
  }, [report])

  // Export helpers
  function handleCopyJson() {
    if (!report) return
    navigator.clipboard.writeText(JSON.stringify(report, null, 2))
  }

  function handleDownloadCsv() {
    if (!report) return
    const headers = ['Agent', 'Raw Score', 'Weight', 'Weighted Score']
    const rows = Object.entries(report.weighted_agent_scores).map(([key, d]) => [
      AGENT_LABELS[key] ?? key,
      d.raw.toFixed(2),
      (d.weight * 100).toFixed(0) + '%',
      d.weighted.toFixed(3),
    ])
    const csv = [headers, ...rows, ['Composite', '', '100%', report.final_score.toFixed(2)]]
      .map((r) => r.join(','))
      .join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${report.ticker}_analysis_${report.report_date}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  function handlePrint() {
    window.print()
  }

  return (
    <AppLayout>
      <div className="min-h-screen px-4 py-8 max-w-6xl mx-auto">

        {/* ── STEP 1: Search (idle state) ── */}
        <AnimatePresence mode="wait">
          {status === 'idle' && (
            <motion.div
              key="idle"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
              className="flex flex-col items-center justify-center min-h-[60vh] gap-8"
            >
              <div className="text-center space-y-3">
                <h1 className="text-4xl font-bold text-[var(--text-primary)]">
                  Analyze Any Stock
                </h1>
                <p className="text-[var(--text-muted)] text-lg max-w-lg mx-auto">
                  8 specialized AI agents run in parallel to produce a composite conviction score.
                </p>
              </div>

              <div className="relative w-full max-w-2xl">
                <TickerSearch
                  onSubmit={(t) => analysis.startAnalysis(t)}
                  disabled={status !== 'idle'}
                />
              </div>

              {/* Recent tickers hint */}
              <div className="text-[var(--text-muted)] text-sm text-center">
                Popular: MARUTI · TATAMOTORS · M&M · BAJAJ-AUTO
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── STEP 2: Streaming ── */}
        <AnimatePresence mode="wait">
          {status === 'streaming' && (
            <motion.div
              key="streaming"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.35 }}
            >
              <StreamProgress
                ticker={ticker}
                agentStates={agentStates}
                completedCount={completedCount}
                elapsedSeconds={elapsedSeconds}
                isMock={isMock}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── STEP 2 Error state ── */}
        <AnimatePresence>
          {status === 'error' && (
            <motion.div
              key="error"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center justify-center min-h-[50vh] gap-6"
            >
              <div className="glass-card p-8 max-w-md w-full text-center space-y-4">
                <div className="text-4xl">⚠️</div>
                <h2 className="text-xl font-bold text-[var(--text-primary)]">
                  Analysis Failed
                </h2>
                <p className="text-[var(--text-secondary)] text-sm">
                  {error ?? 'An unexpected error occurred.'}
                </p>
                <GlowButton
                  variant="outline"
                  onClick={() => analysis.reset()}
                  className="w-full"
                >
                  <RotateCcw size={16} />
                  Try Again
                </GlowButton>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── STEP 3: Results ── */}
        <AnimatePresence>
          {status === 'complete' && report && (
            <motion.div
              key="results"
              ref={resultsRef}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5 }}
              className="space-y-8"
            >
              {/* Demo banner if mock */}
              {isMock && (
                <div className="text-center py-2 px-4 rounded-lg bg-[rgba(245,158,11,0.1)] border border-[rgba(245,158,11,0.3)]">
                  <span className="text-[#f59e0b] text-sm">
                    Running on demo data — start backend for live analysis
                  </span>
                </div>
              )}

              {/* New analysis button */}
              <div className="flex justify-between items-center flex-wrap gap-3">
                <h1 className="text-2xl font-bold text-[var(--text-primary)]">
                  Analysis Results
                </h1>
                <GlowButton
                  variant="outline"
                  size="sm"
                  onClick={() => analysis.reset()}
                >
                  <RotateCcw size={14} />
                  New Analysis
                </GlowButton>
              </div>

              {/* Verdict reveal (centered) */}
              <VerdictReveal report={report} elapsedSeconds={elapsedSeconds} />

              {/* Two-column layout */}
              <div className="grid grid-cols-1 lg:grid-cols-[55%_45%] gap-6">
                {/* LEFT: Radar + Score table */}
                <div className="space-y-5">
                  <div className="glass-card p-5">
                    <h3 className="text-base font-semibold text-[var(--text-primary)] mb-4">
                      Agent Score Radar
                    </h3>
                    <AgentRadar report={report} />
                  </div>
                  <AgentScoreTable report={report} />
                </div>

                {/* RIGHT: Conviction + Conflicts */}
                <div className="space-y-5">
                  <ConvictionPanel
                    drivers={report.conviction_drivers}
                    risks={report.top_risks}
                  />
                  {(report.conflicts_resolved?.length ?? 0) > 0 && (
                    <ConflictsPanel conflicts={report.conflicts_resolved!} />
                  )}
                </div>
              </div>

              {/* Thesis */}
              <ThesisCard thesis={report.investment_thesis} />

              {/* History chart */}
              <HistoryLine
                ticker={report.ticker}
                records={history.length > 0 ? history : sampleHistory}
              />

              {/* Export bar */}
              <div className="flex items-center justify-center gap-3 py-6 flex-wrap print:hidden">
                <button
                  onClick={handleCopyJson}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium
                    text-[var(--text-secondary)] hover:text-[var(--text-primary)]
                    bg-[rgba(255,255,255,0.04)] hover:bg-[rgba(255,255,255,0.08)]
                    border border-[var(--border-color)] transition-all cursor-pointer"
                >
                  <Clipboard size={15} />
                  Copy JSON
                </button>
                <button
                  onClick={handleDownloadCsv}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium
                    text-[var(--text-secondary)] hover:text-[var(--text-primary)]
                    bg-[rgba(255,255,255,0.04)] hover:bg-[rgba(255,255,255,0.08)]
                    border border-[var(--border-color)] transition-all cursor-pointer"
                >
                  <Download size={15} />
                  Download CSV
                </button>
                <button
                  onClick={handlePrint}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium
                    text-[var(--text-secondary)] hover:text-[var(--text-primary)]
                    bg-[rgba(255,255,255,0.04)] hover:bg-[rgba(255,255,255,0.08)]
                    border border-[var(--border-color)] transition-all cursor-pointer"
                >
                  <Printer size={15} />
                  Print PDF
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </AppLayout>
  )
}
