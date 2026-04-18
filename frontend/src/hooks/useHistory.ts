import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import type { ScoreRecord } from '@/types'
import { sampleHistory } from '@/mocks/sampleReport'

type DayRange = 30 | 90 | 365 | 9999

interface UseHistoryOptions {
  ticker: string
  days?: DayRange
  enabled?: boolean
}

interface UseHistoryReturn {
  records: ScoreRecord[]
  loading: boolean
  error: string | null
  refetch: () => void
}

function filterByDays(records: ScoreRecord[], days: DayRange): ScoreRecord[] {
  if (days === 9999) return records
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return records.filter((r) => new Date(r.report_date) >= cutoff)
}

export function useHistory({ ticker, days = 90, enabled = true }: UseHistoryOptions): UseHistoryReturn {
  const [allRecords, setAllRecords] = useState<ScoreRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    if (!ticker || !enabled) return
    setLoading(true)
    setError(null)
    try {
      const res = await axios.get<ScoreRecord[]>(
        `http://localhost:8000/history/${encodeURIComponent(ticker)}`,
        { timeout: 5000 }
      )
      setAllRecords(res.data)
    } catch {
      // Backend down — use mock data
      const mock = sampleHistory.map((r) => ({ ...r, ticker }))
      setAllRecords(mock)
    } finally {
      setLoading(false)
    }
  }, [ticker, enabled])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const records = filterByDays(allRecords, days)

  return { records, loading, error, refetch: fetchData }
}
