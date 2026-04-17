import type { Verdict } from '@/types'

interface VerdictBadgeProps {
  verdict: string
  size?: 'sm' | 'md' | 'lg'
  glow?: boolean
}

const VERDICT_STYLES: Record<string, string> = {
  'STRONG BUY':  'bg-[rgba(34,197,94,0.15)] text-[var(--buy-strong)] border-[rgba(34,197,94,0.4)]',
  'BUY':         'bg-[rgba(74,222,128,0.12)] text-[var(--buy)] border-[rgba(74,222,128,0.3)]',
  'NEUTRAL':     'bg-[rgba(245,158,11,0.12)] text-[var(--neutral-color)] border-[rgba(245,158,11,0.3)]',
  'SELL':        'bg-[rgba(249,115,22,0.12)] text-[var(--sell)] border-[rgba(249,115,22,0.3)]',
  'STRONG SELL': 'bg-[rgba(239,68,68,0.15)] text-[var(--sell-strong)] border-[rgba(239,68,68,0.4)]',
}

const GLOW_CLASSES: Record<string, string> = {
  'STRONG BUY':  'glow-strong-buy',
  'BUY':         'glow-buy',
  'NEUTRAL':     'glow-neutral',
  'SELL':        'glow-sell',
  'STRONG SELL': 'glow-strong-sell',
}

const SIZE_CLASSES = {
  sm: 'text-xs px-2 py-0.5',
  md: 'text-sm px-3 py-1',
  lg: 'text-base px-4 py-1.5 font-bold',
}

export function VerdictBadge({ verdict, size = 'md', glow = false }: VerdictBadgeProps) {
  const upper = verdict.toUpperCase() as Verdict
  const style = VERDICT_STYLES[upper] ?? VERDICT_STYLES['NEUTRAL']
  const glowClass = glow ? (GLOW_CLASSES[upper] ?? '') : ''
  const sizeClass = SIZE_CLASSES[size]

  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold tracking-wide
        ${style} ${sizeClass} ${glowClass}`}
    >
      {verdict}
    </span>
  )
}
