import { useState } from 'react'
import { X, Search, CheckCircle2 } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { GlowButton } from '@/components/ui/GlowButton'
import { TICKERS, TICKER_NAMES } from '@/types'
import { useWatchlist } from '@/hooks/useWatchlist'

interface AddTickerModalProps {
  open: boolean
  onClose: () => void
}

const ALL_TICKERS = [...TICKERS] as string[]

export function AddTickerModal({ open, onClose }: AddTickerModalProps) {
  const [search,   setSearch]   = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const { activeList, tickers: existing, add } = useWatchlist()

  const filtered = ALL_TICKERS.filter(t =>
    !existing.includes(t) &&
    (t.toLowerCase().includes(search.toLowerCase()) ||
     (TICKER_NAMES[t] ?? '').toLowerCase().includes(search.toLowerCase()))
  )

  function toggle(ticker: string) {
    setSelected(s => s.includes(ticker) ? s.filter(t => t !== ticker) : [...s, ticker])
  }

  function handleAdd() {
    selected.forEach(t => add(activeList, t))
    setSelected([])
    setSearch('')
    onClose()
  }

  function handleClose() {
    setSelected([])
    setSearch('')
    onClose()
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-[60]"
            style={{ background: 'rgba(5,8,16,0.82)', backdropFilter: 'blur(8px)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={handleClose}
          />

          {/* Modal */}
          <div className="fixed inset-0 z-[61] flex items-center justify-center pointer-events-none px-4">
            <motion.div
              className="glass-card p-6 w-full max-w-md pointer-events-auto"
              initial={{ scale: 0.92, opacity: 0, y: 16 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.92, opacity: 0, y: 16 }}
              transition={{ type: 'spring', stiffness: 300, damping: 28 }}
              onClick={e => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h2 className="font-bold text-[var(--text-primary)]">Add Tickers</h2>
                  <p className="text-xs text-[var(--text-muted)] mt-0.5">to {activeList}</p>
                </div>
                <button
                  className="p-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[rgba(255,255,255,0.05)] rounded-lg transition-all"
                  onClick={handleClose}
                >
                  <X size={18} />
                </button>
              </div>

              {/* Search */}
              <div className="relative mb-4">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                <input
                  autoFocus
                  className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-color)] focus:border-[var(--accent-cyan)] text-[var(--text-primary)] text-sm outline-none transition-colors placeholder:text-[var(--text-muted)]"
                  placeholder="Search ticker or company..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
              </div>

              {/* Chips grid */}
              <div className="grid grid-cols-2 gap-2 mb-5 max-h-52 overflow-y-auto">
                {filtered.map(ticker => {
                  const sel = selected.includes(ticker)
                  return (
                    <button
                      key={ticker}
                      onClick={() => toggle(ticker)}
                      className={`flex items-start gap-2 p-3 rounded-xl border text-left transition-all duration-150
                        ${sel
                          ? 'border-[var(--accent-cyan)] bg-[rgba(6,182,212,0.1)]'
                          : 'border-[var(--border-color)] hover:border-[var(--border-glow)] hover:bg-[rgba(255,255,255,0.02)]'
                        }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className={`font-mono font-bold text-sm ${sel ? 'text-[var(--accent-cyan)]' : 'text-[var(--text-primary)]'}`}>
                          {ticker}
                        </div>
                        <div className="text-[10px] text-[var(--text-muted)] truncate">{TICKER_NAMES[ticker]}</div>
                      </div>
                      {sel && <CheckCircle2 size={14} className="flex-shrink-0 mt-0.5 text-[var(--accent-cyan)]" />}
                    </button>
                  )
                })}

                {filtered.length === 0 && (
                  <div className="col-span-2 text-center py-8 text-sm text-[var(--text-muted)]">
                    {existing.length >= ALL_TICKERS.length
                      ? 'All available tickers already added'
                      : 'No matching tickers'}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <GlowButton variant="outline" size="sm" className="flex-1" onClick={handleClose}>
                  Cancel
                </GlowButton>
                <GlowButton
                  variant="cyan"
                  size="sm"
                  className="flex-1"
                  disabled={selected.length === 0}
                  onClick={handleAdd}
                >
                  Add{selected.length > 0 ? ` (${selected.length})` : ''}
                </GlowButton>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  )
}
