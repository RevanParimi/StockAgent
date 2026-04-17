import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { FinalReport, User, WatchlistMap } from '@/types'

interface AuthSlice {
  user: User | null
  isLoggedIn: boolean
  login: (user: User) => void
  logout: () => void
}

interface WatchlistSlice {
  watchlists: WatchlistMap
  activeWatchlist: string
  addWatchlist: (name: string) => void
  removeWatchlist: (name: string) => void
  renameWatchlist: (oldName: string, newName: string) => void
  addTicker: (listName: string, ticker: string) => void
  removeTicker: (listName: string, ticker: string) => void
  setActiveWatchlist: (name: string) => void
}

interface AnalysisSlice {
  analyses: Record<string, FinalReport>
  recentTickers: string[]
  saveAnalysis: (ticker: string, report: FinalReport) => void
}

type StoreState = AuthSlice & WatchlistSlice & AnalysisSlice

export const useStore = create<StoreState>()(
  persist(
    (set, get) => ({
      // Auth
      user: null,
      isLoggedIn: false,
      login: (user) => set({ user, isLoggedIn: true }),
      logout: () => set({ user: null, isLoggedIn: false }),

      // Watchlists
      watchlists: { 'My Stocks': [] },
      activeWatchlist: 'My Stocks',
      addWatchlist: (name) =>
        set((s) => ({ watchlists: { ...s.watchlists, [name]: [] } })),
      removeWatchlist: (name) =>
        set((s) => {
          const next = { ...s.watchlists }
          delete next[name]
          const keys = Object.keys(next)
          return {
            watchlists: next,
            activeWatchlist: keys[0] ?? 'My Stocks',
          }
        }),
      renameWatchlist: (oldName, newName) =>
        set((s) => {
          const next = { ...s.watchlists }
          next[newName] = next[oldName]
          delete next[oldName]
          return {
            watchlists: next,
            activeWatchlist:
              s.activeWatchlist === oldName ? newName : s.activeWatchlist,
          }
        }),
      addTicker: (listName, ticker) =>
        set((s) => ({
          watchlists: {
            ...s.watchlists,
            [listName]: s.watchlists[listName]?.includes(ticker)
              ? s.watchlists[listName]
              : [...(s.watchlists[listName] ?? []), ticker],
          },
        })),
      removeTicker: (listName, ticker) =>
        set((s) => ({
          watchlists: {
            ...s.watchlists,
            [listName]: (s.watchlists[listName] ?? []).filter((t) => t !== ticker),
          },
        })),
      setActiveWatchlist: (name) => set({ activeWatchlist: name }),

      // Analyses
      analyses: {},
      recentTickers: [],
      saveAnalysis: (ticker, report) =>
        set((s) => ({
          analyses: { ...s.analyses, [ticker]: report },
          recentTickers: [
            ticker,
            ...s.recentTickers.filter((t) => t !== ticker),
          ].slice(0, 10),
        })),

      // Selector helpers (not stored, computed)
      getActiveList: () => {
        const { watchlists, activeWatchlist } = get()
        return watchlists[activeWatchlist] ?? []
      },
    }),
    {
      name: 'stockagent-store',
      partialize: (s) => ({
        user: s.user,
        isLoggedIn: s.isLoggedIn,
        watchlists: s.watchlists,
        activeWatchlist: s.activeWatchlist,
        analyses: s.analyses,
        recentTickers: s.recentTickers,
      }),
    }
  )
)
