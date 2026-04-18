import { useStore } from '@/store'

export function useWatchlist() {
  const watchlists      = useStore(s => s.watchlists)
  const activeWatchlist = useStore(s => s.activeWatchlist)
  const addWatchlist    = useStore(s => s.addWatchlist)
  const removeWatchlist = useStore(s => s.removeWatchlist)
  const renameWatchlist = useStore(s => s.renameWatchlist)
  const addTicker       = useStore(s => s.addTicker)
  const removeTicker    = useStore(s => s.removeTicker)
  const setActive       = useStore(s => s.setActiveWatchlist)

  return {
    lists:      Object.keys(watchlists),
    activeList: activeWatchlist,
    tickers:    watchlists[activeWatchlist] ?? [],
    add:        addTicker,
    remove:     removeTicker,
    create:     addWatchlist,
    rename:     renameWatchlist,
    destroy:    removeWatchlist,
    setActive,
  }
}
