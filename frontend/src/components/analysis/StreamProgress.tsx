import { motion } from 'framer-motion'
import { TICKER_NAMES, AGENT_LABELS } from '@/types'
import type { AgentStreamState } from '@/types'
import { AgentCard } from './AgentCard'

const AGENT_KEYS = Object.keys(AGENT_LABELS)

interface StreamProgressProps {
  ticker: string
  agentStates: Record<string, AgentStreamState>
  completedCount: number
  elapsedSeconds: number
  isMock?: boolean
}

export function StreamProgress({
  ticker,
  agentStates,
  completedCount,
  elapsedSeconds,
  isMock = false,
}: StreamProgressProps) {
  const companyName = TICKER_NAMES[ticker] ?? ticker
  const total = AGENT_KEYS.length
  const progress = total > 0 ? (completedCount / total) * 100 : 0
  const allDone = completedCount >= total

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6">
      {/* Demo banner */}
      {isMock && (
        <div className="text-center py-2 px-4 rounded-lg bg-[rgba(245,158,11,0.1)] border border-[rgba(245,158,11,0.3)]">
          <span className="text-[#f59e0b] text-sm">
            Running on demo data — start backend for live analysis
          </span>
        </div>
      )}

      {/* Header */}
      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-xl font-bold text-[var(--text-primary)]">
              Analyzing{' '}
              <span className="text-[var(--accent-cyan)] font-mono">{ticker}</span>
            </h2>
            <p className="text-[var(--text-secondary)] text-sm mt-0.5">{companyName}</p>
          </div>
          <div className="flex items-center gap-4 text-sm text-[var(--text-muted)]">
            <span>
              <span className="text-[var(--text-primary)] font-mono font-semibold">
                {completedCount}
              </span>
              /{total} agents
            </span>
            <span className="font-mono tabular-nums text-[var(--text-secondary)]">
              {elapsedSeconds}s elapsed
            </span>
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-2 rounded-full bg-[rgba(255,255,255,0.06)] overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-[var(--accent-cyan)] to-[var(--accent-blue)]"
            initial={{ width: '0%' }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
          />
        </div>
      </div>

      {/* Agent grid — 2 columns × 4 rows */}
      <div className="grid grid-cols-2 gap-4">
        {AGENT_KEYS.map((key) => (
          <AgentCard
            key={key}
            agentKey={key}
            state={agentStates[key] ?? { state: 'pending' }}
          />
        ))}
      </div>

      {/* Generating verdict spinner */}
      {allDone && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-center gap-3 py-4 text-[var(--text-secondary)]"
        >
          <div className="w-5 h-5 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full animate-spin" />
          <span className="text-sm font-medium">Generating verdict...</span>
        </motion.div>
      )}
    </div>
  )
}
