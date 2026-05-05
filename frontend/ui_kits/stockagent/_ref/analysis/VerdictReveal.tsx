import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { FinalReport } from '@/types'
import { TICKER_NAMES } from '@/types'
import { ScoreGauge } from '@/components/charts/ScoreGauge'
import { AnimatedCounter } from '@/components/ui/AnimatedCounter'
import { VerdictBadge } from '@/components/ui/VerdictBadge'

interface VerdictRevealProps {
  report: FinalReport
  elapsedSeconds: number
}

export function VerdictReveal({ report, elapsedSeconds }: VerdictRevealProps) {
  const [flipped, setFlipped] = useState(false)
  const companyName = TICKER_NAMES[report.ticker] ?? report.company_name

  // Trigger flip after a short delay
  useEffect(() => {
    const t = setTimeout(() => setFlipped(true), 400)
    return () => clearTimeout(t)
  }, [])

  const conflictCount = report.conflicts_resolved?.length ?? 0

  return (
    <div className="flex flex-col items-center gap-6">
      {/* Card flip container */}
      <div className="relative w-full max-w-md" style={{ perspective: 1200 }}>
        <motion.div
          animate={{ rotateY: flipped ? 180 : 0 }}
          transition={{ duration: 0.7, ease: [0.4, 0, 0.2, 1] }}
          style={{ transformStyle: 'preserve-3d', position: 'relative', minHeight: 320 }}
        >
          {/* Front face — "Analyzing..." */}
          <div
            style={{ backfaceVisibility: 'hidden', position: 'absolute', inset: 0 }}
            className="glass-card flex flex-col items-center justify-center gap-4 p-8"
          >
            <div className="w-12 h-12 border-4 border-[var(--accent-cyan)] border-t-transparent rounded-full animate-spin" />
            <p className="text-[var(--text-secondary)] text-lg font-medium">Analyzing...</p>
          </div>

          {/* Back face — result */}
          <div
            style={{
              backfaceVisibility: 'hidden',
              transform: 'rotateY(180deg)',
              position: 'absolute',
              inset: 0,
            }}
            className="glass-card flex flex-col items-center p-6 gap-4"
          >
            {/* Company info */}
            <div className="text-center">
              <p className="text-[var(--text-muted)] text-sm">{companyName}</p>
              <h2 className="text-2xl font-bold text-[var(--text-primary)] font-mono">
                {report.ticker}
              </h2>
              <p className="text-[var(--text-muted)] text-xs mt-1">{report.report_date}</p>
            </div>

            {/* Gauge */}
            <ScoreGauge score={report.final_score} size={200} animate={flipped} />

            {/* Animated score counter */}
            <div className="text-center">
              <AnimatedCounter
                target={report.final_score}
                duration={1500}
                decimals={2}
                trigger={flipped}
                className="text-4xl font-bold text-[var(--text-primary)]"
              />
              <p className="text-[var(--text-muted)] text-xs mt-1">composite score</p>
            </div>

            {/* Verdict badge */}
            <AnimatePresence>
              {flipped && (
                <motion.div
                  initial={{ opacity: 0, y: 12, scale: 0.9 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ delay: 0.8, duration: 0.4, ease: 'easeOut' }}
                >
                  <VerdictBadge verdict={report.verdict} size="lg" glow />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </div>

      {/* Meta line */}
      {flipped && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
          className="text-[var(--text-muted)] text-sm text-center"
        >
          Report generated in {elapsedSeconds}s · 8 agents ·{' '}
          {conflictCount === 0
            ? '0 conflicts'
            : `${conflictCount} conflict${conflictCount > 1 ? 's' : ''} resolved by LLM`}
        </motion.p>
      )}
    </div>
  )
}
