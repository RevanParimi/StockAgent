import { create } from 'zustand'
import type { Sector, BootstrapData, TrendingItem } from '@/types/api'
import { detectSector } from '@/types/api'

interface SectorState {
  activeSector:  Sector
  bootstrapData: BootstrapData | null
  trending:      TrendingItem[]
  liveData:      boolean
  fetchedAt:     string | null
  loading:       boolean

  setActiveSector:  (sector: Sector) => void
  setActiveTicker:  (ticker: string) => void   // auto-detects sector
  loadBootstrap:    () => Promise<void>
  loadTrending:     () => Promise<void>
}

export const useSectorStore = create<SectorState>((set) => ({
  activeSector:  'automobile',
  bootstrapData: null,
  trending:      [],
  liveData:      false,
  fetchedAt:     null,
  loading:       false,

  setActiveSector: (sector) => set({ activeSector: sector }),

  setActiveTicker: (ticker) => set({ activeSector: detectSector(ticker) }),

  loadBootstrap: async () => {
    set({ loading: true })
    try {
      const res = await fetch('/ui/bootstrap')
      if (!res.ok) return
      const d: BootstrapData = await res.json()
      set({
        bootstrapData: d,
        liveData:      d._liveData ?? false,
        fetchedAt:     d._fetchedAt ?? null,
        loading:       false,
      })
    } catch {
      set({ loading: false })
    }
  },

  loadTrending: async () => {
    try {
      const res = await fetch('/ui/trending')
      if (!res.ok) return
      const d = await res.json()
      set({ trending: d.trending ?? [] })
    } catch {}
  },
}))
