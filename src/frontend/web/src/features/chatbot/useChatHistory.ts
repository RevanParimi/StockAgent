/**
 * useChatHistory — manages in-session conversation state and API calls.
 * History is NOT persisted across page reloads (by design — stateless backend).
 */

import { useState, useCallback } from 'react'
import type { ChatMessage } from '@/types/api'

export interface ChatEntry {
  from:    'user' | 'bot'
  text:    string
  loading?: boolean
}

const MAX_HISTORY = 8   // last N turns sent to backend

export function useChatHistory() {
  const [messages, setMessages] = useState<ChatEntry[]>([
    { from: 'bot', text: "Hi! I'm your StockAgent assistant. Ask me about any Indian stock or agent." }
  ])

  const send = useCallback(async (text: string) => {
    if (!text.trim()) return

    // Build history from current messages (exclude loading states, cap at MAX_HISTORY)
    const history: ChatMessage[] = messages
      .filter(m => !m.loading)
      .slice(-MAX_HISTORY)
      .map(m => ({ role: m.from === 'user' ? 'user' : 'assistant', content: m.text }))

    // Optimistic UI: show user message + loading placeholder immediately
    setMessages(prev => [
      ...prev,
      { from: 'user', text },
      { from: 'bot', text: '…', loading: true },
    ])

    try {
      const res = await fetch('/ui/chat', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: text, history }),
      })
      const reply = res.ok ? (await res.json()).reply : _fallback(text)
      setMessages(prev => [...prev.slice(0, -1), { from: 'bot', text: reply }])
    } catch {
      setMessages(prev => [...prev.slice(0, -1), { from: 'bot', text: _fallback(text) }])
    }
  }, [messages])

  const clear = useCallback(() => {
    setMessages([{ from: 'bot', text: "Conversation cleared. What would you like to know?" }])
  }, [])

  return { messages, send, clear }
}

function _fallback(q: string): string {
  const ql = q.toLowerCase()
  if (ql.includes('maruti'))   return 'MARUTI is tracked by our Sales & Demand and Fundamentals agents. Run an analysis for the latest verdict.'
  if (ql.includes('tata'))     return 'TATAMOTORS is monitored for EV order book and JLR margin recovery. Run an analysis for the current score.'
  if (ql.includes('compare'))  return 'I can compare tickers — try "MARUTI vs BAJAJ-AUTO on valuation".'
  return 'Ask me about a specific ticker (e.g. MARUTI) or an agent (e.g. Sales & Demand).'
}
