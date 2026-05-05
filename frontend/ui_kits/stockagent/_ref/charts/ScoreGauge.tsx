import { useEffect, useRef, useState } from 'react'

interface ScoreGaugeProps {
  score: number
  size?: number
  animate?: boolean
}

// Interpolate color: red → amber → green
function scoreToColor(t: number): string {
  if (t <= 0.45) {
    // red → amber
    const ratio = t / 0.45
    const r = Math.round(239 + (245 - 239) * ratio)
    const g = Math.round(68 + (158 - 68) * ratio)
    const b = Math.round(68 + (11 - 68) * ratio)
    return `rgb(${r},${g},${b})`
  } else if (t <= 0.75) {
    // amber → cyan/teal
    const ratio = (t - 0.45) / 0.30
    const r = Math.round(245 + (6 - 245) * ratio)
    const g = Math.round(158 + (182 - 158) * ratio)
    const b = Math.round(11 + (212 - 11) * ratio)
    return `rgb(${r},${g},${b})`
  } else {
    // cyan → green
    const ratio = (t - 0.75) / 0.25
    const r = Math.round(6 + (34 - 6) * ratio)
    const g = Math.round(182 + (197 - 182) * ratio)
    const b = Math.round(212 + (94 - 212) * ratio)
    return `rgb(${r},${g},${b})`
  }
}

// Arc path for SVG semicircle
function describeArc(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const toRad = (d: number) => (d * Math.PI) / 180
  const x1 = cx + r * Math.cos(toRad(startDeg))
  const y1 = cy + r * Math.sin(toRad(startDeg))
  const x2 = cx + r * Math.cos(toRad(endDeg))
  const y2 = cy + r * Math.sin(toRad(endDeg))
  const largeArc = endDeg - startDeg > 180 ? 1 : 0
  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`
}

// Gauge goes from 180° (left) to 0° (right) on a top-half semicircle
// In SVG coords: 180° left = leftmost point, 0° = rightmost
const START_DEG = 180
const END_DEG = 0

export function ScoreGauge({ score, size = 200, animate = true }: ScoreGaugeProps) {
  const [animatedScore, setAnimatedScore] = useState(0)
  const rafRef = useRef<number>(0)
  const startRef = useRef<number>(0)

  useEffect(() => {
    if (!animate) {
      setAnimatedScore(score)
      return
    }
    const target = score
    startRef.current = performance.now()

    const run = (now: number) => {
      const elapsed = now - startRef.current
      const progress = Math.min(elapsed / 1500, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setAnimatedScore(eased * target)
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(run)
      }
    }

    rafRef.current = requestAnimationFrame(run)
    return () => cancelAnimationFrame(rafRef.current)
  }, [score, animate])

  const cx = size / 2
  const cy = size * 0.62
  const r = size * 0.38
  const trackWidth = size * 0.055
  const fillWidth = size * 0.07

  // The arc spans 180° → 0° going clockwise (SVG coord system)
  // Score 0 → needle at 180°, score 1 → needle at 0°
  const needleDeg = 180 - animatedScore * 180 // maps 0→180, 1→0 in standard angle

  // Colored fill arc: from 180° to needleDeg
  const fillEndDeg = 180 - animatedScore * 180

  // Zone tick marks at 0.30, 0.45, 0.60, 0.75
  const zoneTicks = [0.30, 0.45, 0.60, 0.75]

  const color = scoreToColor(animatedScore)

  const needleX = cx + (r - trackWidth / 2) * Math.cos((needleDeg * Math.PI) / 180)
  const needleY = cy + (r - trackWidth / 2) * Math.sin((needleDeg * Math.PI) / 180)

  return (
    <div className="flex flex-col items-center">
      <svg
        width={size}
        height={size * 0.7}
        viewBox={`0 0 ${size} ${size * 0.7}`}
        className="overflow-visible"
      >
        {/* Background track */}
        <path
          d={describeArc(cx, cy, r, START_DEG, END_DEG)}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={trackWidth}
          strokeLinecap="round"
        />

        {/* Colored fill arc */}
        {animatedScore > 0.001 && (
          <path
            d={describeArc(cx, cy, r, START_DEG, fillEndDeg)}
            fill="none"
            stroke={color}
            strokeWidth={fillWidth}
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 6px ${color}80)` }}
          />
        )}

        {/* Zone ticks */}
        {zoneTicks.map((z) => {
          const tickDeg = 180 - z * 180
          const inner = r - trackWidth * 1.2
          const outer = r + trackWidth * 0.4
          const tx1 = cx + inner * Math.cos((tickDeg * Math.PI) / 180)
          const ty1 = cy + inner * Math.sin((tickDeg * Math.PI) / 180)
          const tx2 = cx + outer * Math.cos((tickDeg * Math.PI) / 180)
          const ty2 = cy + outer * Math.sin((tickDeg * Math.PI) / 180)
          return (
            <line
              key={z}
              x1={tx1} y1={ty1}
              x2={tx2} y2={ty2}
              stroke="rgba(255,255,255,0.25)"
              strokeWidth={1.5}
            />
          )
        })}

        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={needleX}
          y2={needleY}
          stroke={color}
          strokeWidth={size * 0.015}
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 4px ${color})` }}
        />
        {/* Needle pivot */}
        <circle cx={cx} cy={cy} r={size * 0.025} fill={color} />
        <circle cx={cx} cy={cy} r={size * 0.012} fill="var(--bg-card)" />
      </svg>

      {/* Score labels */}
      <div
        className="flex justify-between w-full text-[var(--text-muted)] text-xs font-mono mt-1"
        style={{ maxWidth: r * 2 + trackWidth }}
      >
        <span>0</span>
        <span>0.25</span>
        <span>0.5</span>
        <span>0.75</span>
        <span>1.0</span>
      </div>
    </div>
  )
}
