/**
 * useAnalysis — WebSocket analysis hook with POST fallback.
 *
 * Connects to /ws/stream?ticker=X, streams agent_progress events,
 * and fires onComplete when the full FinalReport arrives.
 * Falls back to POST /analyse if WebSocket fails.
 */

import { useCallback, useEffect, useRef } from 'react'
import { useAnalysisStore } from '@/stores/analysisStore'
import type { FinalReport, StreamEvent } from '@/types/api'

export function useAnalysis() {
  const store   = useAnalysisStore()
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Start elapsed timer when phase becomes 'running'
  useEffect(() => {
    if (store.phase === 'running') {
      timerRef.current = setInterval(() => store.tickElapsed(), 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [store.phase])

  const analyse = useCallback(async (ticker: string) => {
    store.startAnalysis(ticker)

    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    let ws: WebSocket | null = null

    const fallbackPost = async () => {
      try {
        const res = await fetch('/analyse', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ ticker }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Analysis failed' }))
          store.handleEvent({ event: 'error', detail: err.detail ?? 'Analysis failed' })
        } else {
          const report: FinalReport = await res.json()
          store.handleEvent({ event: 'complete', report })
        }
      } catch (e) {
        store.handleEvent({ event: 'error', detail: String(e) })
      }
    }

    try {
      ws = new WebSocket(`${wsProto}//${window.location.host}/ws/stream?ticker=${encodeURIComponent(ticker)}`)
      useAnalysisStore.setState({ wsRef: ws })
    } catch {
      await fallbackPost()
      return
    }

    ws.onmessage = (evt) => {
      try {
        const msg: StreamEvent = JSON.parse(evt.data)
        store.handleEvent(msg)
        if (msg.event === 'complete' || msg.event === 'error') ws?.close(1000)
      } catch {}
    }

    ws.onerror = () => {
      useAnalysisStore.setState({ wsRef: null })
      fallbackPost()
    }
  }, [])

  return {
    analyse,
    ticker:        store.ticker,
    phase:         store.phase,
    report:        store.report,
    error:         store.error,
    agentProgress: store.agentProgress,
    elapsed:       store.elapsed,
    reset:         store.reset,
  }
}
