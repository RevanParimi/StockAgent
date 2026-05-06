import { create } from 'zustand'
import type { FinalReport, StreamEvent } from '@/types/api'

type Phase = 'idle' | 'running' | 'done' | 'error'

interface AgentProgress {
  [agentKey: string]: number   // score 0–1; undefined = not yet complete
}

interface AnalysisState {
  ticker:        string
  phase:         Phase
  report:        FinalReport | null
  error:         string | null
  agentProgress: AgentProgress
  elapsed:       number   // seconds
  wsRef:         WebSocket | null

  // Actions
  startAnalysis:  (ticker: string) => void
  handleEvent:    (evt: StreamEvent) => void
  cancelAnalysis: () => void
  reset:          () => void
  tickElapsed:    () => void
}

export const useAnalysisStore = create<AnalysisState>((set, get) => ({
  ticker:        '',
  phase:         'idle',
  report:        null,
  error:         null,
  agentProgress: {},
  elapsed:       0,
  wsRef:         null,

  startAnalysis: (ticker) => {
    get().cancelAnalysis()
    set({ ticker, phase: 'running', report: null, error: null, agentProgress: {}, elapsed: 0 })
    localStorage.setItem('sa_last_ticker', ticker)
  },

  handleEvent: (evt) => {
    if (evt.event === 'agent_progress') {
      set(s => ({ agentProgress: { ...s.agentProgress, [evt.agent]: evt.score } }))
    } else if (evt.event === 'complete') {
      set({ phase: 'done', report: evt.report })
    } else if (evt.event === 'error') {
      set({ phase: 'error', error: evt.detail })
    }
  },

  cancelAnalysis: () => {
    const ws = get().wsRef
    if (ws && ws.readyState === WebSocket.OPEN) ws.close(1000)
    set({ wsRef: null })
  },

  reset: () => {
    get().cancelAnalysis()
    set({ ticker: '', phase: 'idle', report: null, error: null, agentProgress: {}, elapsed: 0 })
  },

  tickElapsed: () => set(s => ({ elapsed: s.elapsed + 1 })),
}))
