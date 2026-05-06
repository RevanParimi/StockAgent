import React from "react"
import { useSectorStore } from "@/stores/sectorStore"
import { useWatchlistStore } from "@/stores/watchlistStore"
import { useAnalysis } from "@/features/analysis/useAnalysis"

export default function HomePage() {
  const { bootstrapData, trending, liveData } = useSectorStore()
  const { symbols: watchlist } = useWatchlistStore()
  const { analyse, phase } = useAnalysis()

  return (
    <div style={{ minHeight: "100vh", padding: 24 }}>
      <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 8 }}>
        StockAgent — Home
      </h1>
      <p style={{ color: "#64748b", marginBottom: 24 }}>
        {liveData ? "Live data from agent analyses" : "Run your first analysis to see live data"}
      </p>
      {/* TODO: TodayPane, WatchlistPane, TrendingPane, CategoryGrid, SuggestionCards */}
      <pre style={{ fontSize: 11, background: "#f1f5f9", padding: 12, borderRadius: 8, overflow: "auto" }}>
        {JSON.stringify({ watchlist, trendingCount: trending.length }, null, 2)}
      </pre>
    </div>
  )
}
