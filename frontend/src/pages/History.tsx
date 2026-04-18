import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { RefreshCw, GitCompare, ChevronDown, ChevronUp, TrendingUp, AlertTriangle } from 'lucide-react'
import { AppLayout } from '@/components/layout/AppLayout'
import { GlowButton } from '@/components/ui/GlowButton'
import { VerdictBadge } from '@/components/ui/VerdictBadge'
import { CardSkeleton } from '@/components/ui/LoadingPulse'
import { HistoryLine } from '@/components/charts/HistoryLine'
import { CompareChart } from '@/components/charts/CompareChart'
import { useHistory } from '@/hooks/useHistory'
import { TICKERS, TICKER_NAMES } from '@/types'
import { mockWatchlistReports } from '@/mocks/sampleReport'
import type { ScoreRecord } from '@/types'
import { format, parseISO } from 'date-fns'

type DayRange = 30 | 90 | 365 | 9999
const DAY_RANGES: { label: string; value: DayRange }[] = [
  { label: '30d',  value: 30   },
  { label: '90d',  value: 90   },
  { label: '1yr',  value: 365  },
  { label: 'All',  value: 9999 },
]

type SortField = 'date' | 'score' | 'change'
type SortDir = 'asc' | 'desc'

// Compute per-row change vs previous record
function withChange(records: ScoreRecord[]): (ScoreRecord & { change: number | null })[] {
  const sorted = [...records].sort(
    (a, b) => new Date(a.report_date).getTime() - new Date(b.report_date).getTime()
  )
  return sorted.map((r, i) => ({
    ...r,
    change: i === 0 ? null : r.final_score - sorted[i - 1].final_score,
  }))
}

// Multi-ticker history loader for compare mode
function useMultiHistory(tickers: string[], days: DayRange) {
  const t0 = useHistory({ ticker: tickers[0] ?? '', days, enabled: tickers.length > 0 })
  const t1 = useHistory({ ticker: tickers[1] ?? '', days, enabled: tickers.length > 1 })
  const t2 = useHistory({ ticker: tickers[2] ?? '', days, enabled: tickers.length > 2 })

  return [
    tickers[0] ? { ticker: tickers[0], records: t0.records, loading: t0.loading } : null,
    tickers[1] ? { ticker: tickers[1], records: t1.records, loading: t1.loading } : null,
    tickers[2] ? { ticker: tickers[2], records: t2.records, loading: t2.loading } : null,
  ].filter(Boolean) as { ticker: string; records: ScoreRecord[]; loading: boolean }[]
}

// Ticker selector dropdown
function TickerDropdown({
  selected,
  onToggle,
  max,
}: {
  selected: string[]
  onToggle: (t: string) => void
  max: number
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 px-4 py-2 rounded-xl glass-card text-sm font-medium text-[var(--text-primary)] cursor-pointer"
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        {selected.length === 0 ? 'Select tickers' : selected.join(' · ')}
        <ChevronDown size={14} className="text-[var(--text-muted)]" />
      </button>
      {open && (
        <div
          className="absolute top-full mt-2 left-0 z-50 glass-card overflow-hidden shadow-2xl"
          style={{ minWidth: 220 }}
          role="listbox"
          aria-multiselectable="true"
        >
          {TICKERS.map((t) => {
            const active = selected.includes(t)
            const disabled = !active && selected.length >= max
            return (
              <button
                key={t}
                role="option"
                aria-selected={active}
                disabled={disabled}
                onClick={() => {
                  onToggle(t)
                  if (selected.length === 1 && !active) setOpen(false)
                }}
                className={`w-full flex items-center justify-between px-4 py-2.5 text-sm text-left
                  transition-colors border-b border-[rgba(255,255,255,0.04)] last:border-0
                  ${active ? 'text-[var(--accent-cyan)] bg-[rgba(6,182,212,0.08)]' : ''}
                  ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer hover:bg-[rgba(255,255,255,0.05)]'}
                `}
              >
                <div>
                  <span className="font-mono font-semibold">{t}</span>
                  <span className="text-[var(--text-muted)] text-xs ml-2">{TICKER_NAMES[t]}</span>
                </div>
                {active && <span className="text-[var(--accent-cyan)] text-xs font-bold">✓</span>}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function History() {
  const navigate = useNavigate()

  const [compareMode, setCompareMode] = useState(false)
  const [days, setDays] = useState<DayRange>(90)
  const [primaryTicker, setPrimaryTicker] = useState<string>('MARUTI')
  const [compareTickers, setCompareTickers] = useState<string[]>(['MARUTI'])
  const [sortField, setSortField] = useState<SortField>('date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 15

  // Single-mode history
  const { records, loading, error, refetch } = useHistory({
    ticker: primaryTicker,
    days,
    enabled: !compareMode,
  })

  // Compare-mode multi-history
  const multiData = useMultiHistory(compareMode ? compareTickers : [], days)

  // Toggle ticker in compare list (max 3)
  function toggleCompareTicker(t: string) {
    setCompareTickers((prev) => {
      if (prev.includes(t)) return prev.filter((x) => x !== t)
      if (prev.length >= 3) return prev
      return [...prev, t]
    })
  }

  // Single-mode: add change column + sort
  const tableRows = useMemo(() => {
    const withCh = withChange(records)
    return withCh.sort((a, b) => {
      let va: number, vb: number
      if (sortField === 'date') {
        va = new Date(a.report_date).getTime()
        vb = new Date(b.report_date).getTime()
      } else if (sortField === 'score') {
        va = a.final_score; vb = b.final_score
      } else {
        va = a.change ?? 0; vb = b.change ?? 0
      }
      return sortDir === 'desc' ? vb - va : va - vb
    })
  }, [records, sortField, sortDir])

  const paginated = tableRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(tableRows.length / PAGE_SIZE)

  function toggleSort(field: SortField) {
    if (field === sortField) setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    else { setSortField(field); setSortDir('desc') }
  }

  function SortIndicator({ field }: { field: SortField }) {
    if (sortField !== field) return <span className="opacity-30">↕</span>
    return <span className="text-[var(--accent-cyan)]">{sortDir === 'desc' ? '↓' : '↑'}</span>
  }

  return (
    <AppLayout>
      <div className="min-h-screen px-4 py-8 max-w-6xl mx-auto space-y-6">

        {/* Page header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text-primary)]">Score History</h1>
            <p className="text-[var(--text-muted)] text-sm mt-0.5">
              Track conviction scores over time across automobile stocks
            </p>
          </div>
          <button
            onClick={refetch}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm
              text-[var(--text-muted)] hover:text-[var(--text-primary)]
              glass-card transition-colors disabled:opacity-50 cursor-pointer"
            aria-label="Refresh data"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {/* Controls bar */}
        <div className="glass-card p-4 flex flex-wrap items-center gap-4">
          {/* Compare mode toggle */}
          <button
            onClick={() => {
              setCompareMode((c) => !c)
              if (!compareMode && compareTickers.length === 0) setCompareTickers(['MARUTI'])
            }}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium
              border transition-all cursor-pointer
              ${compareMode
                ? 'border-[var(--accent-violet)] text-[var(--accent-violet)] bg-[rgba(139,92,246,0.1)]'
                : 'border-[var(--border-color)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:border-[var(--border-glow)]'
              }`}
            aria-pressed={compareMode}
          >
            <GitCompare size={14} />
            {compareMode ? 'Compare On' : 'Compare'}
          </button>

          {/* Ticker selector */}
          {compareMode ? (
            <TickerDropdown
              selected={compareTickers}
              onToggle={toggleCompareTicker}
              max={3}
            />
          ) : (
            <select
              value={primaryTicker}
              onChange={(e) => { setPrimaryTicker(e.target.value); setPage(0) }}
              className="px-4 py-2 rounded-xl glass-card text-sm text-[var(--text-primary)]
                bg-transparent border border-[var(--border-color)] cursor-pointer
                focus:outline-none focus:border-[var(--accent-cyan)]"
              aria-label="Select ticker"
            >
              {TICKERS.map((t) => (
                <option key={t} value={t} style={{ background: '#0c1120' }}>
                  {t} — {TICKER_NAMES[t]}
                </option>
              ))}
            </select>
          )}

          {/* Day range buttons */}
          <div
            className="flex items-center gap-1 ml-auto"
            role="group"
            aria-label="Date range"
          >
            {DAY_RANGES.map(({ label, value }) => (
              <button
                key={value}
                onClick={() => { setDays(value); setPage(0) }}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer
                  ${days === value
                    ? 'bg-[var(--accent-cyan)] text-[var(--bg-base)]'
                    : 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[rgba(255,255,255,0.06)]'
                  }`}
                aria-pressed={days === value}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Error state */}
        {error && !loading && (
          <div className="glass-card p-6 flex items-center gap-4 text-[#f59e0b]" role="alert">
            <AlertTriangle size={20} />
            <div className="flex-1">
              <p className="font-semibold">Failed to load data</p>
              <p className="text-sm text-[var(--text-muted)]">{error}</p>
            </div>
            <GlowButton variant="outline" size="sm" onClick={refetch}>Retry</GlowButton>
          </div>
        )}

        {/* Chart section */}
        {compareMode ? (
          <div className="glass-card p-5">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
              <h2 className="text-base font-semibold text-[var(--text-primary)]">
                Comparison Chart
                {' '}
                <span className="text-[var(--text-muted)] font-normal text-sm">
                  ({compareTickers.join(' vs ')})
                </span>
              </h2>
              {/* Compare legend: current score */}
              <div className="flex items-center gap-4 flex-wrap">
                {multiData.map(({ ticker }, i) => {
                  const info = mockWatchlistReports[ticker]
                  const colors = ['#06b6d4', '#8b5cf6', '#f59e0b']
                  return (
                    <div key={ticker} className="flex items-center gap-1.5 text-xs">
                      <span
                        className="w-3 h-0.5 inline-block rounded"
                        style={{ background: colors[i] }}
                      />
                      <span className="font-mono font-semibold" style={{ color: colors[i] }}>
                        {ticker}
                      </span>
                      {info && (
                        <span className="text-[var(--text-muted)]">
                          {info.score.toFixed(2)} · {info.verdict}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
            {multiData.some((d) => d.loading) ? (
              <CardSkeleton className="h-60" />
            ) : (
              <CompareChart tickerRecords={multiData} />
            )}
          </div>
        ) : loading ? (
          <CardSkeleton className="h-80" />
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
          >
            <HistoryLine ticker={primaryTicker} records={records} />
          </motion.div>
        )}

        {/* Single-mode data table */}
        {!compareMode && (
          <div className="glass-card overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border-color)]">
              <h3 className="font-semibold text-[var(--text-primary)]">
                Score Records
                <span className="text-[var(--text-muted)] font-normal text-sm ml-2">
                  ({tableRows.length} entries)
                </span>
              </h3>
            </div>

            {loading ? (
              <div className="p-5 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="shimmer h-10 rounded-lg" />
                ))}
              </div>
            ) : tableRows.length === 0 ? (
              <div className="flex flex-col items-center py-16 text-[var(--text-muted)]">
                <TrendingUp size={32} className="mb-3 opacity-40" />
                <p className="text-sm">No records found for {primaryTicker} in this range</p>
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" aria-label="Score history table">
                    <thead>
                      <tr className="border-b border-[var(--border-color)]">
                        <th
                          className="px-5 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-secondary)] select-none"
                          onClick={() => toggleSort('date')}
                        >
                          Date <SortIndicator field="date" />
                        </th>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                          Verdict
                        </th>
                        <th
                          className="px-5 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-secondary)] select-none"
                          onClick={() => toggleSort('score')}
                        >
                          Score <SortIndicator field="score" />
                        </th>
                        <th
                          className="px-5 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-secondary)] select-none"
                          onClick={() => toggleSort('change')}
                        >
                          Change <SortIndicator field="change" />
                        </th>
                        <th className="px-5 py-3 text-right text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginated.map((row, i) => {
                        const isPositive = (row.change ?? 0) > 0
                        const isNegative = (row.change ?? 0) < 0
                        return (
                          <tr
                            key={row.id ?? i}
                            className={`border-b border-[rgba(255,255,255,0.04)] transition-colors hover:bg-[rgba(255,255,255,0.03)]
                              ${i % 2 === 0 ? '' : 'bg-[rgba(255,255,255,0.02)]'}`}
                          >
                            <td className="px-5 py-3 font-mono text-[var(--text-secondary)] text-xs">
                              {row.report_date
                                ? format(parseISO(row.report_date), 'MMM dd, yyyy')
                                : row.report_date}
                            </td>
                            <td className="px-5 py-3">
                              <VerdictBadge verdict={row.verdict} size="sm" />
                            </td>
                            <td className="px-5 py-3 font-mono font-bold text-[var(--text-primary)] tabular-nums">
                              {row.final_score.toFixed(2)}
                            </td>
                            <td className="px-5 py-3 font-mono tabular-nums text-sm">
                              {row.change === null ? (
                                <span className="text-[var(--text-muted)]">—</span>
                              ) : (
                                <span
                                  style={{
                                    color: isPositive ? '#22c55e' : isNegative ? '#ef4444' : 'var(--text-muted)',
                                  }}
                                >
                                  {isPositive ? '+' : ''}{row.change.toFixed(3)}
                                </span>
                              )}
                            </td>
                            <td className="px-5 py-3 text-right">
                              <button
                                onClick={() =>
                                  navigate(`/analyze?ticker=${primaryTicker}`)
                                }
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                                  text-[var(--text-muted)] hover:text-[var(--accent-cyan)]
                                  hover:bg-[rgba(6,182,212,0.08)] transition-colors ml-auto cursor-pointer
                                  focus-visible:outline-2 focus-visible:outline-[var(--accent-cyan)]"
                                aria-label={`View full report for ${primaryTicker} on ${row.report_date}`}
                              >
                                <TrendingUp size={12} />
                                View Report
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between px-5 py-3 border-t border-[var(--border-color)]">
                    <span className="text-xs text-[var(--text-muted)]">
                      Page {page + 1} of {totalPages}
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setPage((p) => Math.max(0, p - 1))}
                        disabled={page === 0}
                        className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)]
                          hover:bg-[rgba(255,255,255,0.06)] disabled:opacity-40 transition-colors cursor-pointer"
                        aria-label="Previous page"
                      >
                        <ChevronUp size={14} />
                      </button>
                      <button
                        onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                        disabled={page >= totalPages - 1}
                        className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)]
                          hover:bg-[rgba(255,255,255,0.06)] disabled:opacity-40 transition-colors cursor-pointer"
                        aria-label="Next page"
                      >
                        <ChevronDown size={14} />
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  )
}
