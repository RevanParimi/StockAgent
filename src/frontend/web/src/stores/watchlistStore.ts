import { create } from 'zustand'
import type { TickerRow } from '@/types/api'

interface WatchlistState {
  symbols:     string[]
  tickers:     TickerRow[]         // enriched with live prices
  loading:     boolean
  lastFetched: number | null       // timestamp ms

  fetchWatchlist: () => Promise<void>
  addTicker:      (sym: string) => Promise<void>
  removeTicker:   (sym: string) => Promise<void>
}

export const useWatchlistStore = create<WatchlistState>((set, get) => ({
  symbols:     [],
  tickers:     [],
  loading:     false,
  lastFetched: null,

  fetchWatchlist: async () => {
    set({ loading: true })
    try {
      const res = await fetch('/ui/watchlist')
      if (!res.ok) return
      const d = await res.json()
      set({ symbols: d.watchlist ?? [], tickers: d.tickers ?? [], loading: false, lastFetched: Date.now() })
    } catch {
      set({ loading: false })
    }
  },

  addTicker: async (sym) => {
    const newSymbols = [...get().symbols, sym.toUpperCase()]
    try {
      const res = await fetch('/ui/watchlist', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ watchlist: newSymbols }),
      })
      if (!res.ok) return
      await get().fetchWatchlist()
    } catch {}
  },

  removeTicker: async (sym) => {
    const newSymbols = get().symbols.filter(s => s !== sym)
    try {
      const res = await fetch('/ui/watchlist', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ watchlist: newSymbols }),
      })
      if (!res.ok) return
      await get().fetchWatchlist()
    } catch {}
  },
}))
