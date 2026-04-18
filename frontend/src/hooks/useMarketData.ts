import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

export interface MarketIndex {
  label: string
  value: number
  change: number
  changeDirection: 'up' | 'down'
}

const MOCK_MARKET: MarketIndex[] = [
  { label: 'SENSEX',     value: 82450,  change: 1.2,  changeDirection: 'up'   },
  { label: 'NIFTY',      value: 24980,  change: 0.9,  changeDirection: 'up'   },
  { label: 'NIFTY AUTO', value: 24120,  change: 2.1,  changeDirection: 'up'   },
  { label: 'INR/USD',    value: 83.42,  change: 0.1,  changeDirection: 'down' },
]

interface UseMarketDataReturn {
  indices: MarketIndex[]
  loading: boolean
}

export function useMarketData(): UseMarketDataReturn {
  const [indices, setIndices] = useState<MarketIndex[]>(MOCK_MARKET)
  const [loading, setLoading] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function fetchData() {
    setLoading(true)
    try {
      const res = await axios.get<MarketIndex[]>(
        'http://localhost:3000/api/market',
        { timeout: 4000 }
      )
      setIndices(res.data)
    } catch {
      // Use mock if endpoint unavailable
      setIndices(MOCK_MARKET)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    timerRef.current = setInterval(fetchData, 60_000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  return { indices, loading }
}
