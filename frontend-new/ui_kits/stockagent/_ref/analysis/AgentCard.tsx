import { memo } from 'react'
import { motion } from 'framer-motion'
import { AGENT_LABELS } from '@/types'
import type { AgentStreamState } from '@/types'

// Agent icons (emoji or lucide icon name)
const AGENT_ICONS: Record<string, string> = {
  sales_demand:      '📊',
  fundamentals:      '📈',
  pattern_analysis:  '🔍',
  raw_materials:     '⚙️',
  sentiment:         '💬',
  policy_regulatory: '📋',
  competitive_intel: '🎯',
  risk_macro:        '⚠️',
}

function scoreColor(score: number): string {
  if (score >= 0.70) return '#22c55e'
  if (score >= 0.45) return '#f59e0b'
  return '#ef4444'
}

function borderGlow(score: number): string {
  if (score >= 0.70) return '0 0 16px rgba(34,197,94,0.4)'
  if (score >= 0.45) return '0 0 16px rgba(245,158,11,0.4)'
  return '0 0 16px rgba(239,68,68,0.4)'
}

interface AgentCardProps {
  agentKey: string
  state: AgentStreamState
}

function AgentCardInner({ agentKey, state }: AgentCardProps) {
  const label = AGENT_LABELS[agentKey] ?? agentKey
  const icon = AGENT_ICONS[agentKey] ?? '🤖'
  const { state: status, score } = state

  return (
    <motion.div
      layout
      animate={
        status === 'complete' && score !== undefined
          ? { scale: [1, 1.05, 1], transition: { duration: 0.4, ease: 'easeOut' } }
          : {}
      }
      className={`
        relative rounded-xl p-4 border transition-all duration-300
        ${status === 'pending'
          ? 'bg-[rgba(255,255,255,0.02)] border-[var(--border-color)]'
          : status === 'analyzing'
          ? 'bg-[rgba(6,182,212,0.06)] border-[var(--accent-cyan)]'
          : 'bg-[rgba(255,255,255,0.04)] border-transparent'
        }
      `}
      style={
        status === 'complete' && score !== undefined
          ? { borderColor: scoreColor(score), boxShadow: borderGlow(score) }
          : status === 'analyzing'
          ? { boxShadow: '0 0 20px rgba(6,182,212,0.25)' }
          : {}
      }
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <span
          className={`text-2xl transition-all duration-300 ${
            status === 'analyzing' ? 'animate-pulse' : status === 'pending' ? 'grayscale opacity-50' : ''
          }`}
        >
          {icon}
        </span>
        <div className="flex-1 min-w-0">
          <p
            className={`font-semibold text-sm truncate transition-colors duration-200 ${
              status === 'pending'
                ? 'text-[var(--text-muted)]'
                : status === 'analyzing'
                ? 'text-[var(--accent-cyan)]'
                : 'text-[var(--text-primary)]'
            }`}
          >
            {label}
          </p>
        </div>
        {/* Status indicator */}
        {status === 'analyzing' && (
          <div className="w-4 h-4 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full animate-spin shrink-0" />
        )}
      </div>

      {/* Content */}
      {status === 'pending' && (
        <p className="text-[var(--text-muted)] text-xs">Waiting...</p>
      )}

      {status === 'analyzing' && (
        <div className="flex items-center gap-2">
          <div className="h-1 flex-1 rounded-full bg-[rgba(6,182,212,0.2)] overflow-hidden">
            <motion.div
              className="h-full bg-[var(--accent-cyan)] rounded-full"
              animate={{ x: ['-100%', '100%'] }}
              transition={{ duration: 1.2, repeat: Infinity, ease: 'easeInOut' }}
            />
          </div>
          <span className="text-[var(--accent-cyan)] text-xs">Running</span>
        </div>
      )}

      {status === 'complete' && score !== undefined && (
        <div>
          {/* Score number */}
          <div className="flex items-baseline gap-1 mb-2">
            <span
              className="text-2xl font-bold font-mono tabular-nums"
              style={{ color: scoreColor(score) }}
            >
              {score.toFixed(2)}
            </span>
            <span className="text-[var(--text-muted)] text-xs">/ 1.00</span>
          </div>

          {/* Fill bar */}
          <div
            className="h-1.5 rounded-full bg-[rgba(255,255,255,0.08)] overflow-hidden"
            role="progressbar"
            aria-valuenow={Math.round(score * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${label} score: ${score.toFixed(2)}`}
          >
            <motion.div
              className="h-full rounded-full"
              style={{ backgroundColor: scoreColor(score) }}
              initial={{ width: '0%' }}
              animate={{ width: `${score * 100}%` }}
              transition={{ duration: 0.8, ease: 'easeOut', delay: 0.1 }}
            />
          </div>
        </div>
      )}
    </motion.div>
  )
}

// Memoize: only re-renders when state or score changes
export const AgentCard = memo(AgentCardInner, (prev, next) =>
  prev.agentKey === next.agentKey &&
  prev.state.state === next.state.state &&
  prev.state.score === next.state.score
)
