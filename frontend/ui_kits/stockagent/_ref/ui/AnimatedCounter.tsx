import { useEffect, useRef, useState } from 'react'

interface AnimatedCounterProps {
  target: number
  duration?: number
  decimals?: number
  prefix?: string
  suffix?: string
  className?: string
  trigger?: boolean
}

export function AnimatedCounter({
  target,
  duration = 1500,
  decimals = 2,
  prefix = '',
  suffix = '',
  className = '',
  trigger = true,
}: AnimatedCounterProps) {
  const [current, setCurrent] = useState(0)
  const rafRef = useRef<number>(0)
  const startRef = useRef<number>(0)
  const startValRef = useRef<number>(0)

  useEffect(() => {
    if (!trigger) return
    startRef.current = performance.now()
    startValRef.current = current

    const animate = (now: number) => {
      const elapsed = now - startRef.current
      const progress = Math.min(elapsed / duration, 1)
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setCurrent(startValRef.current + (target - startValRef.current) * eased)
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      }
    }

    rafRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafRef.current)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, trigger])

  const display = current.toFixed(decimals)
  return (
    <span className={`font-mono tabular-nums ${className}`}>
      {prefix}{display}{suffix}
    </span>
  )
}
