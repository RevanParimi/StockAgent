import { useState, useEffect } from 'react'

interface MarketItem {
  label: string
  value: number
  change: number
  up: boolean
  decimals: number
}

const MOCK_DATA: MarketItem[] = [
  { label: 'SENSEX',     value: 82450,  change: 1.2, up: true,  decimals: 0 },
  { label: 'NIFTY',      value: 24980,  change: 0.9, up: true,  decimals: 0 },
  { label: 'NIFTY AUTO', value: 24120,  change: 2.1, up: true,  decimals: 0 },
  { label: 'INR/USD',    value: 83.42,  change: 0.1, up: false, decimals: 2 },
]

function formatValue(value: number, decimals: number) {
  return decimals === 0
    ? value.toLocaleString('en-IN')
    : value.toFixed(decimals)
}

function nowIST() {
  return new Date().toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata',
  })
}

export function MarketBar() {
  const [time, setTime] = useState(nowIST)

  useEffect(() => {
    const id = setInterval(() => setTime(nowIST()), 60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 flex items-center px-4 gap-5"
      style={{
        height: 48,
        background: 'rgba(5,8,16,0.96)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderBottom: '1px solid rgba(30,41,59,0.6)',
      }}
    >
      {/* Live dot */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <span
          className="w-2 h-2 rounded-full"
          style={{
            background: 'var(--buy-strong)',
            animation: 'pulse-dot 1.5s ease-in-out infinite',
          }}
        />
        <span className="text-[11px] font-bold text-[var(--buy-strong)] tracking-widest">LIVE</span>
      </div>

      <div className="w-px h-4 bg-[var(--border-color)] flex-shrink-0" />

      {/* Ticker items */}
      <div className="flex items-center gap-5 flex-1 overflow-hidden">
        {MOCK_DATA.map(item => (
          <div key={item.label} className="flex items-center gap-1.5 flex-shrink-0">
            <span className="text-[11px] text-[var(--text-muted)] font-medium tracking-wider">
              {item.label}
            </span>
            <span className="font-mono text-[12px] font-semibold text-[var(--text-primary)]">
              {formatValue(item.value, item.decimals)}
            </span>
            <span
              className="font-mono text-[11px] font-medium"
              style={{ color: item.up ? 'var(--buy-strong)' : 'var(--sell-strong)' }}
            >
              {item.up ? '▲' : '▼'} {item.change}%
            </span>
          </div>
        ))}
      </div>

      {/* Time */}
      <div className="text-[10px] text-[var(--text-muted)] flex-shrink-0 hidden sm:block">
        {time} IST
      </div>
    </div>
  )
}
