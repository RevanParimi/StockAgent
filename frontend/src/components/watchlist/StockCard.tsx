import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MoreVertical, TrendingUp, Trash2 } from 'lucide-react'
import { VerdictBadge } from '@/components/ui/VerdictBadge'
import { GlowButton } from '@/components/ui/GlowButton'
import { MiniSparkline } from '@/components/charts/MiniSparkline'
import { sampleHistory } from '@/mocks/sampleReport'
import { TICKER_NAMES } from '@/types'

interface StockCardProps {
  ticker: string
  score: number
  verdict: string
  onClick?: () => void
  onRemove?: () => void
}

const AVATAR_COLORS = [
  '#3b82f6', '#8b5cf6', '#06b6d4', '#22c55e',
  '#f59e0b', '#ef4444', '#ec4899', '#14b8a6',
]

function avatarColor(ticker: string) {
  let h = 0
  for (const c of ticker) h = (h * 31 + c.charCodeAt(0)) & 0x7fffffff
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}

// Pre-built sparkline data (oldest → newest)
const BASE_SPARK = [...sampleHistory].reverse().slice(0, 20).map(r => ({ score: r.final_score }))

export function StockCard({ ticker, score, verdict, onClick, onRemove }: StockCardProps) {
  const cardRef  = useRef<HTMLDivElement>(null)
  const [tilt, setTilt]       = useState('perspective(1000px) rotateX(0deg) rotateY(0deg)')
  const [menuOpen, setMenuOpen] = useState(false)
  const navigate = useNavigate()

  const name     = TICKER_NAMES[ticker] ?? ticker
  const initials = name.split(' ').map((w: string) => w[0]).join('').slice(0, 2).toUpperCase()
  const color    = avatarColor(ticker)

  function onMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = cardRef.current?.getBoundingClientRect()
    if (!rect) return
    const x = ((e.clientY - rect.top  - rect.height / 2) / rect.height) * 8
    const y = ((e.clientX - rect.left - rect.width  / 2) / rect.width)  * -8
    setTilt(`perspective(1000px) rotateX(${x}deg) rotateY(${y}deg)`)
  }

  function onMouseLeave() {
    setTilt('perspective(1000px) rotateX(0deg) rotateY(0deg)')
    setMenuOpen(false)
  }

  function handleAnalyze(e: React.MouseEvent) {
    e.stopPropagation()
    navigate(`/analyze?ticker=${ticker}`)
  }

  function handleMenuToggle(e: React.MouseEvent) {
    e.stopPropagation()
    setMenuOpen(m => !m)
  }

  function handleRemove(e: React.MouseEvent) {
    e.stopPropagation()
    onRemove?.()
    setMenuOpen(false)
  }

  return (
    <div
      ref={cardRef}
      className="glass-card p-5 cursor-pointer relative select-none"
      style={{ transform: tilt, transition: 'transform 0.1s ease' }}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      onClick={onClick}
    >
      {/* Header row */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm flex-shrink-0"
            style={{ background: color, color: 'var(--bg-base)' }}
          >
            {initials}
          </div>
          <div className="min-w-0">
            <div className="text-[11px] text-[var(--text-muted)] font-medium truncate max-w-[120px]">{name}</div>
            <div className="font-mono font-bold text-[var(--text-primary)] text-sm tracking-wide">{ticker}</div>
          </div>
        </div>

        {/* 3-dot menu */}
        <div className="relative flex-shrink-0">
          <button
            className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            onClick={handleMenuToggle}
          >
            <MoreVertical size={16} />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-7 glass-card py-1 min-w-[150px] z-20 shadow-xl">
              <button
                onClick={handleRemove}
                className="flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-[rgba(239,68,68,0.1)] w-full text-left transition-colors"
              >
                <Trash2 size={13} /> Remove from list
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Verdict + Score */}
      <div className="flex items-center justify-between mb-3">
        <VerdictBadge verdict={verdict} size="sm" glow />
        <span className="font-mono text-2xl font-bold text-[var(--text-primary)]">
          {Math.round(score * 100)}
          <span className="text-xs text-[var(--text-muted)] ml-0.5 font-normal">/100</span>
        </span>
      </div>

      {/* Sparkline */}
      <MiniSparkline data={BASE_SPARK} verdict={verdict} height={40} />

      {/* CTA */}
      <div className="mt-4">
        <GlowButton variant="outline" size="sm" className="w-full text-xs" onClick={handleAnalyze}>
          <TrendingUp size={13} /> Analyze Now
        </GlowButton>
      </div>
    </div>
  )
}
