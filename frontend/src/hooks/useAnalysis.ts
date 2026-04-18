import { useState, useRef, useCallback, useEffect } from 'react'
import type { FinalReport, AgentStreamState, StreamEvent } from '@/types'
import { sampleReport } from '@/mocks/sampleReport'
import { useStore } from '@/store'

export type AnalysisStatus = 'idle' | 'streaming' | 'complete' | 'error'

export interface UseAnalysisReturn {
  status: AnalysisStatus
  ticker: string
  agentStates: Record<string, AgentStreamState>
  completedCount: number
  elapsedSeconds: number
  report: FinalReport | null
  error: string | null
  startAnalysis: (ticker: string) => void
  reset: () => void
}

const AGENT_KEYS = [
  'sales_demand',
  'fundamentals',
  'pattern_analysis',
  'raw_materials',
  'sentiment',
  'policy_regulatory',
  'competitive_intel',
  'risk_macro',
]

function initialAgentStates(): Record<string, AgentStreamState> {
  return Object.fromEntries(AGENT_KEYS.map((k) => [k, { state: 'pending' as const }]))
}

export function useAnalysis(): UseAnalysisReturn {
  const saveAnalysis = useStore((s) => s.saveAnalysis)

  const [status, setStatus] = useState<AnalysisStatus>('idle')
  const [ticker, setTicker] = useState('')
  const [agentStates, setAgentStates] = useState<Record<string, AgentStreamState>>(initialAgentStates())
  const [completedCount, setCompletedCount] = useState(0)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [report, setReport] = useState<FinalReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startTimeRef = useRef<number>(0)
  const reconnectCountRef = useRef(0)
  const currentTickerRef = useRef('')
  const isMockRef = useRef(false)

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const startTimer = useCallback(() => {
    startTimeRef.current = Date.now()
    timerRef.current = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTimeRef.current) / 1000))
    }, 1000)
  }, [])

  const closeWs = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const handleEvent = useCallback(
    (event: StreamEvent) => {
      if (event.event === 'agent_progress' && event.agent) {
        const agentKey = event.agent
        setAgentStates((prev) => {
          const updated = { ...prev }
          // Mark all pending agents before this one as analyzing (the current one)
          // Actually just mark this agent as analyzing first
          updated[agentKey] = { state: 'analyzing' }
          return updated
        })

        // Small delay to show "analyzing" state before "complete"
        setTimeout(() => {
          setAgentStates((prev) => {
            const updated = { ...prev }
            updated[agentKey] = { state: 'complete', score: event.score }
            return updated
          })
          setCompletedCount((c) => c + 1)
        }, 600)
      } else if (event.event === 'complete' && event.report) {
        stopTimer()
        closeWs()
        setReport(event.report)
        setStatus('complete')
        saveAnalysis(event.report.ticker, event.report)
      } else if (event.event === 'error') {
        stopTimer()
        closeWs()
        setError(event.detail ?? 'Analysis failed')
        setStatus('error')
      }
    },
    [stopTimer, closeWs, saveAnalysis]
  )

  // Mock streaming fallback
  const runMockStream = useCallback(
    (tickerName: string) => {
      isMockRef.current = true
      const mockReport: FinalReport = {
        ...sampleReport,
        ticker: tickerName,
        company_name:
          tickerName === 'MARUTI'
            ? 'Maruti Suzuki India Ltd'
            : tickerName,
      }

      const agents = Object.keys(mockReport.weighted_agent_scores)
      let idx = 0

      function revealNext() {
        if (idx >= agents.length) {
          // All agents done — emit complete
          setTimeout(() => {
            stopTimer()
            setReport(mockReport)
            setStatus('complete')
            saveAnalysis(mockReport.ticker, mockReport)
          }, 1000)
          return
        }

        const agentKey = agents[idx]
        const detail = mockReport.weighted_agent_scores[agentKey]

        setAgentStates((prev) => ({
          ...prev,
          [agentKey]: { state: 'analyzing' },
        }))

        setTimeout(() => {
          setAgentStates((prev) => ({
            ...prev,
            [agentKey]: { state: 'complete', score: detail.raw },
          }))
          setCompletedCount((c) => c + 1)
          idx++
          setTimeout(revealNext, 500)
        }, 600)
      }

      setTimeout(revealNext, 800)
    },
    [stopTimer, saveAnalysis]
  )

  const connectWs = useCallback(
    (tickerName: string) => {
      const url = `ws://localhost:8000/ws/stream?ticker=${encodeURIComponent(tickerName)}`
      reconnectCountRef.current = 0

      function tryConnect() {
        if (reconnectCountRef.current > 3) {
          // Fallback to mock
          runMockStream(tickerName)
          return
        }

        const ws = new WebSocket(url)
        wsRef.current = ws

        const timeout = setTimeout(() => {
          if (ws.readyState !== WebSocket.OPEN) {
            ws.close()
            reconnectCountRef.current = 99
            runMockStream(tickerName)
          }
        }, 3000)

        ws.onopen = () => {
          clearTimeout(timeout)
          reconnectCountRef.current = 0
        }

        ws.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data) as StreamEvent
            handleEvent(data)
          } catch {
            // ignore
          }
        }

        ws.onerror = () => {
          clearTimeout(timeout)
        }

        ws.onclose = () => {
          clearTimeout(timeout)
          wsRef.current = null
          // If status not yet complete/error → reconnect or mock
          if (reconnectCountRef.current < 3) {
            reconnectCountRef.current++
            setTimeout(tryConnect, 2000)
          } else if (reconnectCountRef.current !== 99) {
            runMockStream(tickerName)
          }
        }
      }

      tryConnect()
    },
    [handleEvent, runMockStream]
  )

  const startAnalysis = useCallback(
    (tickerName: string) => {
      // Reset state
      closeWs()
      stopTimer()
      currentTickerRef.current = tickerName
      isMockRef.current = false

      setTicker(tickerName)
      setStatus('streaming')
      setAgentStates(initialAgentStates())
      setCompletedCount(0)
      setElapsedSeconds(0)
      setReport(null)
      setError(null)

      startTimer()
      connectWs(tickerName)
    },
    [closeWs, stopTimer, startTimer, connectWs]
  )

  const reset = useCallback(() => {
    closeWs()
    stopTimer()
    reconnectCountRef.current = 99
    setStatus('idle')
    setTicker('')
    setAgentStates(initialAgentStates())
    setCompletedCount(0)
    setElapsedSeconds(0)
    setReport(null)
    setError(null)
  }, [closeWs, stopTimer])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      closeWs()
      stopTimer()
    }
  }, [closeWs, stopTimer])

  return {
    status,
    ticker,
    agentStates,
    completedCount,
    elapsedSeconds,
    report,
    error,
    startAnalysis,
    reset,
  }
}
