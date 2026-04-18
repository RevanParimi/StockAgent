import { useState } from 'react'
import { Plus } from 'lucide-react'
import { AppLayout } from '@/components/layout/AppLayout'
import { WatchlistManager } from '@/components/watchlist/WatchlistManager'
import { StockCard } from '@/components/watchlist/StockCard'
import { QuickDrawer } from '@/components/watchlist/QuickDrawer'
import { AddTickerModal } from '@/components/watchlist/AddTickerModal'
import { GlowButton } from '@/components/ui/GlowButton'
import { useWatchlist } from '@/hooks/useWatchlist'
import { mockWatchlistReports } from '@/mocks/sampleReport'

export function Watchlist() {
  const [drawerTicker, setDrawerTicker] = useState<string | null>(null)
  const [addModal,     setAddModal]     = useState(false)
  const { tickers, activeList, remove } = useWatchlist()

  return (
    <AppLayout>
      <div className="p-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text-primary)]">Watchlist</h1>
            <p className="text-sm text-[var(--text-muted)] mt-0.5">
              {tickers.length} stock{tickers.length !== 1 ? 's' : ''} tracked
            </p>
          </div>
          <GlowButton variant="cyan" size="sm" onClick={() => setAddModal(true)}>
            <Plus size={15} /> Add Ticker
          </GlowButton>
        </div>

        {/* Watchlist manager (create / rename / delete lists) */}
        <div className="mb-6">
          <WatchlistManager />
        </div>

        {/* Grid or empty state */}
        {tickers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-28 gap-4">
            <div className="text-5xl select-none">⭐</div>
            <h3 className="text-xl font-bold text-[var(--text-primary)]">
              {activeList} is empty
            </h3>
            <p className="text-sm text-[var(--text-muted)]">
              Add automobile stocks to track their AI analysis scores
            </p>
            <GlowButton variant="cyan" size="md" onClick={() => setAddModal(true)}>
              <Plus size={16} /> Add Your First Ticker
            </GlowButton>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {tickers.map(ticker => {
              const rep = mockWatchlistReports[ticker]
              if (!rep) return null
              return (
                <StockCard
                  key={ticker}
                  ticker={ticker}
                  score={rep.score}
                  verdict={rep.verdict}
                  onClick={() => setDrawerTicker(ticker)}
                  onRemove={() => remove(activeList, ticker)}
                />
              )
            })}
          </div>
        )}
      </div>

      <QuickDrawer ticker={drawerTicker} onClose={() => setDrawerTicker(null)} />
      <AddTickerModal open={addModal} onClose={() => setAddModal(false)} />
    </AppLayout>
  )
}
