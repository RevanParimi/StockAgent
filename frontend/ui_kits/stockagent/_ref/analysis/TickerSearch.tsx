import { useState, useRef, useEffect } from 'react'
import { Search, ChevronRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { GlowButton } from '@/components/ui/GlowButton'
import { TICKERS, TICKER_NAMES } from '@/types'
import { useStore } from '@/store'
import { mockWatchlistReports } from '@/mocks/sampleReport'

interface TickerSearchProps {
  onSubmit: (ticker: string) => void
  disabled?: boolean
  initialTicker?: string
}

export function TickerSearch({ onSubmit, disabled, initialTicker }: TickerSearchProps) {
  const [query, setQuery] = useState(initialTicker ?? '')
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const analyses = useStore((s) => s.analyses)

  const filtered = TICKERS.filter(
    (t) =>
      t.toLowerCase().includes(query.toLowerCase()) ||
      TICKER_NAMES[t].toLowerCase().includes(query.toLowerCase())
  )

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  function handleSubmit() {
    const val = query.trim().toUpperCase()
    if (!val) return
    setOpen(false)
    onSubmit(val)
  }

  function selectTicker(t: string) {
    setQuery(t)
    setOpen(false)
    onSubmit(t)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted((h) => Math.min(h + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      if (highlighted >= 0 && filtered[highlighted]) {
        selectTicker(filtered[highlighted])
      } else {
        handleSubmit()
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  function getScore(ticker: string): number | null {
    return analyses[ticker]?.final_score ?? mockWatchlistReports[ticker]?.score ?? null
  }

  function getVerdict(ticker: string): string | null {
    return analyses[ticker]?.verdict ?? mockWatchlistReports[ticker]?.verdict ?? null
  }

  function verdictColor(verdict: string | null) {
    if (!verdict) return 'var(--text-muted)'
    if (verdict.includes('STRONG BUY')) return '#22c55e'
    if (verdict === 'BUY') return '#06b6d4'
    if (verdict === 'NEUTRAL') return '#f59e0b'
    return '#ef4444'
  }

  return (
    <div ref={containerRef} className="w-full max-w-2xl mx-auto">
      <div className="relative flex gap-3">
        {/* Search input */}
        <div className="relative flex-1">
          <Search
            className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            size={20}
          />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setOpen(true)
              setHighlighted(-1)
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={handleKeyDown}
            placeholder="Enter ticker or company name..."
            disabled={disabled}
            className="
              w-full pl-12 pr-4 py-4 rounded-xl
              bg-[var(--bg-card)] border border-[var(--border-color)]
              text-[var(--text-primary)] placeholder-[var(--text-muted)]
              focus:outline-none focus:border-[var(--accent-cyan)]
              focus:shadow-[0_0_20px_rgba(6,182,212,0.2)]
              transition-all duration-200 text-lg
              disabled:opacity-50
            "
          />
        </div>

        <GlowButton
          variant="cyan"
          size="lg"
          onClick={handleSubmit}
          disabled={disabled || !query.trim()}
          className="shrink-0"
        >
          Analyze
          <ChevronRight size={18} />
        </GlowButton>
      </div>

      {/* Autocomplete dropdown */}
      <AnimatePresence>
        {open && filtered.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15 }}
            className="
              absolute z-50 mt-2 w-full max-w-2xl
              bg-[var(--bg-card)] border border-[var(--border-color)]
              rounded-xl shadow-2xl overflow-hidden
            "
          >
            {filtered.map((t, i) => {
              const score = getScore(t)
              const verdict = getVerdict(t)
              return (
                <button
                  key={t}
                  className={`
                    w-full flex items-center justify-between px-4 py-3
                    text-left transition-colors duration-100 cursor-pointer
                    ${i === highlighted
                      ? 'bg-[rgba(6,182,212,0.1)] border-l-2 border-[var(--accent-cyan)]'
                      : 'hover:bg-[rgba(255,255,255,0.04)] border-l-2 border-transparent'
                    }
                    ${i < filtered.length - 1 ? 'border-b border-[var(--border-color)]' : ''}
                  `}
                  onMouseEnter={() => setHighlighted(i)}
                  onClick={() => selectTicker(t)}
                >
                  <div className="flex flex-col">
                    <span className="text-[var(--text-primary)] font-semibold font-mono">{t}</span>
                    <span className="text-[var(--text-muted)] text-sm">{TICKER_NAMES[t]}</span>
                  </div>
                  {score !== null && (
                    <div className="flex flex-col items-end gap-0.5">
                      <span
                        className="text-xs font-medium"
                        style={{ color: verdictColor(verdict) }}
                      >
                        {verdict}
                      </span>
                      <span className="text-[var(--text-muted)] text-xs font-mono">
                        {score.toFixed(2)}
                      </span>
                    </div>
                  )}
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>

      <p className="text-center text-[var(--text-muted)] text-sm mt-4">
        10 NSE/BSE automobile stocks · Free-text resolves via AI
      </p>
    </div>
  )
}
