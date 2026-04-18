import { useEffect, useRef, useCallback } from 'react'
import type { StreamEvent } from '@/types'

interface UseWebSocketOptions {
  url: string
  onMessage: (event: StreamEvent) => void
  onError?: (error: Event) => void
  enabled?: boolean
}

interface UseWebSocketReturn {
  connected: boolean
  disconnect: () => void
}

export function useWebSocket({
  url,
  onMessage,
  onError,
  enabled = true,
}: UseWebSocketOptions): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectCountRef = useRef(0)
  const connectedRef = useRef(false)
  const enabledRef = useRef(enabled)
  const onMessageRef = useRef(onMessage)
  const onErrorRef = useRef(onError)

  // Keep refs in sync
  enabledRef.current = enabled
  onMessageRef.current = onMessage
  onErrorRef.current = onError

  const disconnect = useCallback(() => {
    reconnectCountRef.current = 99 // Prevent reconnect
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!enabled) return

    reconnectCountRef.current = 0

    function connect() {
      if (!enabledRef.current) return
      if (reconnectCountRef.current > 3) return

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        connectedRef.current = true
        reconnectCountRef.current = 0
      }

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as StreamEvent
          onMessageRef.current(data)
        } catch {
          // Ignore malformed messages
        }
      }

      ws.onerror = (e) => {
        onErrorRef.current?.(e)
      }

      ws.onclose = () => {
        connectedRef.current = false
        wsRef.current = null
        // Reconnect with 2s backoff, up to 3 times
        if (reconnectCountRef.current < 3 && enabledRef.current) {
          reconnectCountRef.current++
          setTimeout(connect, 2000)
        }
      }
    }

    connect()

    return () => {
      reconnectCountRef.current = 99
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [url, enabled])

  return { connected: connectedRef.current, disconnect }
}
