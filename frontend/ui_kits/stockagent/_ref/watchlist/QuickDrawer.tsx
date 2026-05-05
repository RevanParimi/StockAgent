import { AnimatePresence, motion } from 'framer-motion'
import { X, TrendingUp, History, AlertTriangle, Lightbulb } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { VerdictBadge } from '@/components/ui/VerdictBadge'
import { GlowButton } from '@/components/ui/GlowButton'
import { TICKER_NAMES, AGENT_LABELS } from '@/types'
import { mockWatchlistReports, sampleReport } from '@/mocks/sampleReport'

interface QuickDrawerProps {
  ticker: string | null
  onClose: () => void
}

function AgentBar({ label, score }: { label: string; score: number }) {
  const color =
    score >= 0.7 ? 'var(--buy-strong)'
    : score >= 0.5 ? 'var(--neutral-color)'
    : 'var(--sell-strong)'
  return (
    <div className="flex items-center gap-3 py-[5px]">
      <span className="text-[11px] text-[var(--text-secondary)] flex-shrink-0" style={{ width: 140 }}>{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-[var(--border-color)] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${score * 100}%`, background: color }}
        />
      </div>
      <span className="font-mono text-[11px] text-[var(--text-primary)] flex-shrink-0" style={{ width: 32, textAlign: 'right' }}>
        {score.toFixed(2)}
      </span>
    </div>
  )
}

export function QuickDrawer({ ticker, onClose }: QuickDrawerProps) {
  const navigate = useNavigate()
  const summary  = ticker ? mockWatchlistReports[ticker] : null
  const name     = ticker ? (TICKER_NAMES[ticker] ?? ticker) : ''
  const agents   = sampleReport.weighted_agent_scores

  return (
    <AnimatePresence>
      {ticker && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-50"
            style={{ background: 'rgba(5,8,16,0.55)', backdropFilter: 'blur(4px)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            className="fixed right-0 top-0 bottom-0 z-50 flex flex-col overflow-hidden"
            style={{
              width: 380,
              background: 'rgba(9,14,27,0.99)',
              backdropFilter: 'blur(24px)',
              WebkitBackdropFilter: 'blur(24px)',
              borderLeft: '1px solid rgba(30,41,59,0.9)',
            }}
            initial={{ x: 400 }}
            animate={{ x: 0 }}
            exit={{ x: 400 }}
            transition={{ type: 'spring', stiffness: 280, damping: 28 }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-[var(--border-color)] flex-shrink-0">
              <div>
                <h2 className="font-bold text-[var(--text-primary)] text-base leading-tight">{name}</h2>
                <span className="font-mono text-sm text-[var(--text-muted)]">{ticker}</span>
              </div>
              <button
                className="p-2 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[rgba(255,255,255,0.05)] rounded-lg transition-all"
                onClick={onClose}
              >
                <X size={20} />
              </button>
            </div>

            {/* Scrollable body */}
            <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-6">

              {/* Score */}
              {summary && (
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[11px] text-[var(--text-muted)] mb-1 font-medium tracking-wider">OVERALL SCORE</div>
                    <div className="font-mono text-4xl font-bold text-[var(--text-primary)]">
                      {Math.round(summary.score * 100)}
                      <span className="text-sm text-[var(--text-muted)] ml-1 font-normal">/100</span>
                    </div>
                    <div className="text-[11px] text-[var(--text-muted)] mt-1">Last analyzed · today</div>
                  </div>
                  <VerdictBadge verdict={summary.verdict} size="lg" glow />
                </div>
              )}

              {/* Agent breakdown */}
              <div>
                <h3 className="text-[11px] font-semibold text-[var(--text-muted)] tracking-wider mb-3">AGENT BREAKDOWN</h3>
                <div className="flex flex-col">
                  {Object.entries(agents).map(([key, detail]) => (
                    <AgentBar key={key} label={AGENT_LABELS[key] ?? key} score={detail.raw} />
                  ))}
                </div>
              </div>

              {/* Top Insight */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Lightbulb size={13} style={{ color: 'var(--buy-strong)' }} />
                  <h3 className="text-[11px] font-semibold text-[var(--text-muted)] tracking-wider">TOP INSIGHT</h3>
                </div>
                <blockquote
                  className="text-sm text-[var(--text-secondary)] pl-3 py-1 rounded-r"
                  style={{ borderLeft: '3px solid var(--buy-strong)' }}
                >
                  {sampleReport.conviction_drivers[0]}
                </blockquote>
              </div>

              {/* Top Risk */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle size={13} style={{ color: 'var(--neutral-color)' }} />
                  <h3 className="text-[11px] font-semibold text-[var(--text-muted)] tracking-wider">TOP RISK</h3>
                </div>
                <div
                  className="text-sm text-[var(--text-secondary)] pl-3 py-1.5 rounded-r"
                  style={{
                    borderLeft: '3px solid var(--neutral-color)',
                    background: 'rgba(245,158,11,0.04)',
                  }}
                >
                  {sampleReport.top_risks[0]}
                </div>
              </div>
            </div>

            {/* Footer CTAs */}
            <div className="px-6 py-5 border-t border-[var(--border-color)] flex flex-col gap-3 flex-shrink-0">
              <GlowButton
                variant="cyan"
                size="md"
                className="w-full"
                onClick={() => { navigate(`/analyze?ticker=${ticker}`); onClose() }}
              >
                <TrendingUp size={16} /> Full Analysis →
              </GlowButton>
              <GlowButton
                variant="outline"
                size="md"
                className="w-full"
                onClick={() => { navigate(`/history?ticker=${ticker}`); onClose() }}
              >
                <History size={16} /> View History →
              </GlowButton>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
