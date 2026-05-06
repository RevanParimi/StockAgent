import React from "react"
import { useSectorStore } from "@/stores/sectorStore"

export default function AgentsPage() {
  const agents = useSectorStore(s => s.bootstrapData?.AGENTS ?? [])
  return (
    <div style={{ minHeight: "100vh", padding: 24 }}>
      <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 16 }}>Your AI Agents</h1>
      {/* TODO: Pipeline visual, AgentCard grid with weight sliders */}
      <p style={{ color: "#64748b" }}>{agents.length} agents loaded</p>
    </div>
  )
}
