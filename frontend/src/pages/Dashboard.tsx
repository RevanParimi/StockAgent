import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Clock, PlayCircle, Trophy } from 'lucide-react'
import { AppLayout } from '@/components/layout/AppLayout'
import { GlassCard } from '@/components/ui/GlassCard'
import { VerdictBadge } from '@/components/ui/VerdictBadge'
import { GlowButton } from '@/components/ui/GlowButton'
import { VerdictDonut } from '@/components/charts/VerdictDonut'
import { QuickDrawer } from '@/components/watchlist/QuickDrawer'
import { AddTickerModal } from '@/components/watchlist/AddTickerModal'
import { useWatchlist } from '@/hooks/useWatchlist'
import { useStore } from '@/store'
import { mockWatchlistReports } from '@/mocks/sampleReport'

const MOCK_SCHEDULER = {
  is_running:     true,
  next_fire_time: '2026-04-18T03:00:00Z',
  ticker_count:   5,
}

function MiniScoreBar({ score }: { score: number }) {
  const c =
    score >= 0.7 ? 'var(--buy-strong)'
    : score >= 0.5 ? 'var(--neutral-color)'
    : 'var(--sell-strong)'
  return (
    <div className="w-14 h-1.5 rounded-full bg-[var(--border-color)] overflow-hidden flex-shrink-0">
      <div className="h-full rounded-full" style={{ width: `${score * 100}%`, background: c }} />
    </div>
  )
}

export function Dashboard() {
  const [drawerTicker, setDrawerTicker] = useState<string | null>(null)
  const [addModal,     setAddModal]     = useState(false)
  const { tickers } = useWatchlist()
  const navigate    = useNavigate()

  const recentTickers = useStore(s => s.recentTickers)
  const analyses      = useStore(s => s.analyses)

  // Reports for current watchlist
  const watchlistReports = tickers
    .filter(t => mockWatchlistReports[t])
    .map(t => ({ ticker: t, ...mockWatchlistReports[t] }))

  // Score leaders (top 3)
  const leaders = [...watchlistReports].sort((a, b) => b.score - a.score).slice(0, 3)

  // Recent analyses — Zustand first, fallback to mock sample
  const recentItems = (
    recentTickers.length > 0
      ? recentTickers.slice(0, 5).map(t => ({
          ticker:  t,
          score:   analyses[t]?.final_score ?? mockWatchlistReports[t]?.score ?? 0,
          verdict: analyses[t]?.verdict     ?? mockWatchlistReports[t]?.verdict ?? 'NEUTRAL',
          ago:     'recently',
        }))
      : Object.keys(mockWatchlistReports).slice(0, 5).map((t, i) => ({
          ticker:  t,
          score:   mockWatchlistReports[t].score,
          verdict: mockWatchlistReports[t].verdict,
          ago:     `${(i + 1) * 12}m ago`,
        }))
  )

  const donutReports = Object.fromEntries(watchlistReports.map(r => [r.ticker, { score: r.score, verdict: r.verdict }]))

  return (
    <AppLayout>
      <div className="p-6 max-w-[1600px]">

        {/* Page header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Dashboard</h1>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">Your portfolio at a glance</p>
        </div>

        {/* 3-column layout */}
        <div className="grid gap-5" style={{ gridTemplateColumns: '28% 1fr 28%' }}>

          {/* ── Column 1: Watchlist ── */}
          <div className="flex flex-col gap-4">
            <GlassCard>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">Your Watchlist</h2>
                <button
                  className="w-6 h-6 rounded-full flex items-center justify-center transition-colors"
                  style={{ background: 'rgba(6,182,212,0.15)', color: 'var(--accent-cyan)' }}
                  onClick={() => setAddModal(true)}
                  title="Add ticker"
                >
                  <Plus size={13} />
                </button>
              </div>

              {tickers.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-sm text-[var(--text-muted)]">No tickers yet</p>
                  <button
                    className="mt-2 text-xs text-[var(--accent-cyan)] hover:underline"
                    onClick={() => setAddModal(true)}
                  >
                    + Add tickers
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-0.5">
                  {tickers.map(ticker => {
                    const rep = mockWatchlistReports[ticker]
                    if (!rep) return null
                    return (
                      <div
                        key={ticker}
                        className="flex items-center gap-2 px-2 py-2 rounded-xl hover:bg-[rgba(255,255,255,0.04)] cursor-pointer group transition-colors"
                        onClick={() => setDrawerTicker(ticker)}
                      >
                        <span className="font-mono text-xs font-bold text-[var(--text-primary)] w-[72px] truncate flex-shrink-0">
                          {ticker}
                        </span>
                        <MiniScoreBar score={rep.score} />
                        <span className="font-mono text-[11px] text-[var(--text-muted)] w-5 flex-shrink-0">
                          {Math.round(rep.score * 100)}
                        </span>
                        <VerdictBadge verdict={rep.verdict} size="sm" />
                        <span className="ml-auto text-[11px] text-[var(--accent-cyan)] opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                          →
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </GlassCard>
          </div>

          {/* ── Column 2: Mood + Recent ── */}
          <div className="flex flex-col gap-4">
            <GlassCard>
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Portfolio Mood</h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5 mb-2">Verdict distribution across watchlist</p>
              <VerdictDonut reports={donutReports} />
            </GlassCard>

            <GlassCard>
              <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Recent Analyses</h2>
              <div className="flex flex-col gap-1">
                {recentItems.map((item, i) => (
                  <div
                    key={`${item.ticker}-${i}`}
                    className="flex items-center gap-3 px-2 py-2 rounded-xl hover:bg-[rgba(255,255,255,0.04)] cursor-pointer transition-colors"
                    onClick={() => navigate(`/analyze?ticker=${item.ticker}`)}
                  >
                    <span className="font-mono text-xs font-bold text-[var(--text-primary)] w-24 truncate flex-shrink-0">
                      {item.ticker}
                    </span>
                    <VerdictBadge verdict={item.verdict} size="sm" />
                    <span className="font-mono text-xs text-[var(--text-secondary)]">
                      {Math.round(item.score * 100)}
                    </span>
                    <div className="ml-auto flex items-center gap-1 text-[10px] text-[var(--text-muted)] flex-shrink-0">
                      <Clock size={10} />
                      <span>{item.ago}</span>
                    </div>
                  </div>
                ))}
              </div>
            </GlassCard>
          </div>

          {/* ── Column 3: Scheduler + Leaders ── */}
          <div className="flex flex-col gap-4">
            <GlassCard>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">Scheduler</h2>
                <span
                  className="text-[10px] px-2 py-0.5 rounded-full font-bold tracking-wide"
                  style={
                    MOCK_SCHEDULER.is_running
                      ? { background: 'rgba(34,197,94,0.15)', color: 'var(--buy-strong)' }
                      : { background: 'rgba(245,158,11,0.15)', color: 'var(--neutral-color)' }
                  }
                >
                  {MOCK_SCHEDULER.is_running ? 'ACTIVE' : 'PAUSED'}
                </span>
              </div>

              <div className="text-[11px] text-[var(--text-muted)] mb-0.5">Next run</div>
              <div className="font-mono text-sm text-[var(--text-primary)] mb-2">Tomorrow · 8:30am IST</div>

              <span
                className="inline-flex items-center text-[11px] px-2 py-0.5 rounded-full mb-4"
                style={{ background: 'rgba(6,182,212,0.1)', color: 'var(--accent-cyan)' }}
              >
                {MOCK_SCHEDULER.ticker_count} tickers queued
              </span>

              <GlowButton
                variant="outline"
                size="sm"
                className="w-full text-xs mb-3"
              >
                <PlayCircle size={13} /> Run Now
              </GlowButton>

              <div className="flex flex-col gap-1.5">
                {(tickers.length > 0 ? tickers : Object.keys(mockWatchlistReports)).slice(0, 5).map(t => (
                  <div key={t} className="flex items-center gap-2 text-xs">
                    <span
                      className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                      style={{ background: 'var(--accent-cyan)' }}
                    />
                    <span className="font-mono text-[var(--text-secondary)]">{t}</span>
                  </div>
                ))}
              </div>
            </GlassCard>

            <GlassCard>
              <div className="flex items-center gap-2 mb-4">
                <Trophy size={14} style={{ color: 'var(--neutral-color)' }} />
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">Score Leaders</h2>
              </div>

              {leaders.length === 0 ? (
                <p className="text-xs text-[var(--text-muted)] text-center py-4">
                  Add tickers to see leaders
                </p>
              ) : (
                <div className="flex flex-col gap-3">
                  {leaders.map((item, i) => (
                    <div key={item.ticker} className="flex items-center gap-3">
                      <span className="text-xs font-bold text-[var(--text-muted)] w-4 flex-shrink-0">{i + 1}</span>
                      <span className="font-mono text-xs font-bold text-[var(--text-primary)] flex-1">{item.ticker}</span>
                      <div className="w-14 h-1.5 rounded-full bg-[var(--border-color)] overflow-hidden flex-shrink-0">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${item.score * 100}%`,
                            background: item.score >= 0.7 ? 'var(--buy-strong)' : 'var(--neutral-color)',
                          }}
                        />
                      </div>
                      <VerdictBadge verdict={item.verdict} size="sm" />
                    </div>
                  ))}
                </div>
              )}
            </GlassCard>
          </div>
        </div>
      </div>

      <QuickDrawer ticker={drawerTicker} onClose={() => setDrawerTicker(null)} />
      <AddTickerModal open={addModal} onClose={() => setAddModal(false)} />
    </AppLayout>
  )
}
