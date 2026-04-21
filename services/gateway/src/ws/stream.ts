import { Context } from 'hono'
import { upgradeWebSocket } from 'hono/bun'
import WebSocket from 'ws'

const PYTHON_WS_URL = (process.env.PYTHON_INTERNAL_URL ?? 'http://localhost:8001')
  .replace(/^http/, 'ws')

export const streamHandler = upgradeWebSocket((c: Context) => {
  const ticker = c.req.query('ticker') ?? ''
  let pythonWs: WebSocket | null = null

  return {
    onOpen(_event, browserWs) {
      const targetUrl = `${PYTHON_WS_URL}/ws/stream?ticker=${encodeURIComponent(ticker)}`
      pythonWs = new WebSocket(targetUrl)

      pythonWs.on('open', () => {
        console.log(`[WS] Proxy open: browser ↔ Python ${targetUrl}`)
      })

      pythonWs.on('message', (data) => {
        if (browserWs.readyState === WebSocket.OPEN) {
          browserWs.send(data.toString())
        }
      })

      pythonWs.on('close', (code, reason) => {
        browserWs.close(code, reason)
      })

      pythonWs.on('error', (err) => {
        console.error('[WS] Python side error:', err.message)
        browserWs.close(1011, 'Python WS error')
      })
    },

    onMessage(event, _browserWs) {
      if (pythonWs?.readyState === WebSocket.OPEN) {
        pythonWs.send(event.data.toString())
      }
    },

    onClose() {
      if (pythonWs && pythonWs.readyState !== WebSocket.CLOSED) {
        pythonWs.close()
      }
    },

    onError(event) {
      console.error('[WS] Browser side error:', event)
      if (pythonWs && pythonWs.readyState !== WebSocket.CLOSED) {
        pythonWs.close()
      }
    },
  }
})
