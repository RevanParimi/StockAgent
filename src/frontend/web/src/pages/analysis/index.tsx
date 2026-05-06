import React from "react"
import { useAnalysis } from "@/features/analysis/useAnalysis"
import { useAgentProgress } from "@/features/analysis/useAgentProgress"

export default function AnalysisPage() {
  const { analyse, phase, report, elapsed } = useAnalysis()
  const agents = useAgentProgress()
  return (
    <div style={{ minHeight: "100vh", padding: 24 }}>
      <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 16 }}>Analysis</h1>
      {/* TODO: VerdictReveal, AgentCard grid, StreamProgress, ThesisCard */}
      <button onClick={() => analyse("MARUTI")} style={{ padding: "10px 20px", borderRadius: 8, border: "none", background: "#0891b2", color: "#fff", cursor: "pointer" }}>
        Run MARUTI
      </button>
      <p style={{ marginTop: 12, color: "#64748b" }}>Phase: {phase} · Elapsed: {elapsed}s · Agents done: {agents.filter(a => a.done).length}/{agents.length}</p>
    </div>
  )
}
