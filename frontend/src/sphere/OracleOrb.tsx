/*
 * OracleOrb.tsx — Agent Ring Diagram v4
 *
 * Three rendering layers:
 *  1. SVG  — ring segments, agent dots, labels, center (static structure)
 *  2. Canvas — traveling pulse dots (60fps, zero React re-renders)
 *  3. HTML — hover card (React state, only on interaction)
 *
 * Below diagram: live event stream ticker (React state, updates every ~2s)
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import './OracleOrb.css'
import {
  AGENT_LIVE_DATA, LIVE_EVENTS,
  CATEGORY_META, type LiveEvent,
} from '@/data/agentLiveData'

export type OrbState = 'idle' | 'scanning' | 'complete' | 'caution'

interface Props {
  state?:   OrbState
  size?:    number
  verdict?: string
  score?:   number
}

/* ── SVG layout constants (in 360×360 viewBox) ── */
const CX = 180, CY = 180
const R1 = 155   // outer ring
const R2 = 105   // inner ring
const RD = 160   // agent dot position (just outside ring)
const RL = 176   // label position
const RC = 72    // center circle

/* ── Agents ── */
const AGENTS = [
  { id:'sales',       label:'Sales',      sub:'Demand',    color:'#06B6D4', angle:-90  },
  { id:'fund',        label:'Fundament.', sub:'Financials',color:'#3B82F6', angle:-45  },
  { id:'patterns',    label:'Patterns',   sub:'Technical', color:'#8B5CF6', angle:0    },
  { id:'sentiment',   label:'Sentiment',  sub:'News/Social',color:'#EC4899',angle:45   },
  { id:'macro',       label:'Macro',      sub:'& Risk',    color:'#F97316', angle:90   },
  { id:'competitive', label:'Compet.',    sub:'Intel',     color:'#14B8A6', angle:135  },
  { id:'policy',      label:'Policy',     sub:'& Reg.',    color:'#EAB308', angle:180  },
  { id:'rawmat',      label:'Raw',        sub:'Materials', color:'#EF4444', angle:225  },
] as const

/* ── 4 ring zones ── */
const ZONES = [
  { label:'DATA',     color:'#0EA5E9', start:-112.5, end:-22.5 },
  { label:'ANALYSIS', color:'#8B5CF6', start:-22.5,  end:67.5  },
  { label:'CONTEXT',  color:'#14B8A6', start:67.5,   end:157.5 },
  { label:'RISK',     color:'#F97316', start:157.5,  end:247.5 },
] as const

/* ── SVG helpers ── */
function rad(deg: number) { return deg * Math.PI / 180 }
function polar(r: number, deg: number) {
  return { x: CX + r * Math.cos(rad(deg)), y: CY + r * Math.sin(rad(deg)) }
}
function arcPath(r1: number, r2: number, a: number, b: number) {
  const s1 = polar(r1, a), e1 = polar(r1, b)
  const s2 = polar(r2, b), e2 = polar(r2, a)
  const lg = b - a > 180 ? 1 : 0
  return `M${s1.x} ${s1.y} A${r1} ${r1} 0 ${lg} 1 ${e1.x} ${e1.y}
          L${s2.x} ${s2.y} A${r2} ${r2} 0 ${lg} 0 ${e2.x} ${e2.y}Z`
}

/* ── Canvas pulse type ── */
type Pulse = { angle: number; targetAngle: number; color: string; agentId: string; alpha: number }

/* ── Hover card ── */
function HoverCard({ agentId, angle, size }: { agentId: string; angle: number; size: number }) {
  const data = AGENT_LIVE_DATA[agentId]
  const agent = AGENTS.find(a => a.id === agentId)!
  if (!data || !agent) return null

  const scale = size / 360
  const dot = { x: (CX + RD * Math.cos(rad(angle))) * scale, y: (CY + RD * Math.sin(rad(angle))) * scale }

  const cardW = 200, cardH = 148
  const onRight = angle > -67.5 && angle < 67.5
  const onLeft  = angle > 112.5 || angle < -112.5
  const onTop   = angle >= -112.5 && angle <= -67.5
  let left = dot.x, top = dot.y

  if (onRight)      { left = dot.x + 16; top = dot.y - cardH / 2 }
  else if (onLeft)  { left = dot.x - cardW - 16; top = dot.y - cardH / 2 }
  else if (onTop)   { left = dot.x - cardW / 2; top = dot.y - cardH - 16 }
  else              { left = dot.x - cardW / 2; top = dot.y + 16 }

  const verdictColor = data.verdict === 'POSITIVE' ? '#059669'
    : data.verdict === 'NEGATIVE' ? '#DC2626'
    : data.verdict === 'CAUTION'  ? '#D97706' : '#475569'

  return (
    <div
      className="oracle-hover-card"
      style={{ left, top, width: cardW, borderColor: agent.color + '55' }}
    >
      {/* Header */}
      <div className="oracle-hc-header" style={{ borderBottomColor: agent.color + '33' }}>
        <span className="oracle-hc-title" style={{ color: agent.color }}>
          {agent.label} {agent.sub}
        </span>
        <span className="oracle-hc-verdict" style={{ color: verdictColor }}>
          {data.verdict}
        </span>
      </div>
      {/* Signals */}
      {data.signals.map((s, i) => (
        <div key={i} className="oracle-hc-row">
          <span className="oracle-hc-label">{s.label}</span>
          <span className={`oracle-hc-val oracle-hc-val--${s.status}`}>{s.value}</span>
        </div>
      ))}
    </div>
  )
}

/* ── Event stream strip ── */
function EventStream({ events }: { events: LiveEvent[] }) {
  if (events.length === 0) return null
  return (
    <div className="oracle-stream">
      <span className="oracle-stream-label">Live signals</span>
      <div className="oracle-stream-items">
        {events.map((ev, i) => {
          const cat = CATEGORY_META[ev.category]
          const agent = AGENTS.find(a => a.id === ev.agentId)
          return (
            <div key={ev.id + i} className="oracle-stream-item" style={{ animationDelay: `${i * 0.06}s` }}>
              <span className="oracle-stream-icon">{ev.icon}</span>
              <span className="oracle-stream-cat" style={{ color: cat.color, background: cat.bg }}>
                {cat.label}
              </span>
              <span className="oracle-stream-text">{ev.label}</span>
              <span className="oracle-stream-val" style={{ color: agent?.color }}>
                {ev.value}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════
   MAIN COMPONENT
═══════════════════════════════════════════ */
export function OracleOrb({ state = 'idle', size = 320, verdict, score }: Props) {
  const canvasRef    = useRef<HTMLCanvasElement>(null)
  const pulsesRef    = useRef<Pulse[]>([])
  const rafRef       = useRef<number>(0)
  const spawnCounter = useRef(0)

  const [hoveredId,   setHoveredId]   = useState<string | null>(null)
  const [litAgents,   setLitAgents]   = useState<Set<string>>(new Set())
  const [streamEvents,setStreamEvents] = useState<LiveEvent[]>([])
  const [scanIdx,     setScanIdx]      = useState(-1)

  /* ── Canvas: 60fps pulse animation ── */
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    canvas.width  = size * dpr
    canvas.height = size * dpr
    const ctx = canvas.getContext('2d')!
    ctx.scale(dpr, dpr)
    const scale = size / 360

    function drawFrame() {
      ctx.clearRect(0, 0, size, size)
      const next: Pulse[] = []

      for (const p of pulsesRef.current) {
        /* Shortest-path angle diff */
        let diff = p.targetAngle - p.angle
        while (diff >  180) diff -= 360
        while (diff < -180) diff += 360

        if (Math.abs(diff) < 2.5) {
          /* Arrived — flash the agent */
          setLitAgents(prev => { const s = new Set(prev); s.add(p.agentId); return s })
          setTimeout(() => setLitAgents(prev => { const s = new Set(prev); s.delete(p.agentId); return s }), 1200)
          continue
        }

        const newAngle = p.angle + diff * 0.055
        next.push({ ...p, angle: newAngle })

        /* Draw the pulse dot on the ring */
        const pos = { x: (CX + RD * Math.cos(rad(newAngle))) * scale, y: (CY + RD * Math.sin(rad(newAngle))) * scale }

        /* Outer glow */
        const grd = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, 14)
        grd.addColorStop(0, p.color + 'CC')
        grd.addColorStop(1, p.color + '00')
        ctx.beginPath(); ctx.arc(pos.x, pos.y, 14, 0, Math.PI * 2)
        ctx.fillStyle = grd; ctx.fill()

        /* Core dot */
        ctx.beginPath(); ctx.arc(pos.x, pos.y, 5, 0, Math.PI * 2)
        ctx.fillStyle = p.color; ctx.globalAlpha = 0.95; ctx.fill()
        ctx.globalAlpha = 1
      }

      pulsesRef.current = next
      rafRef.current = requestAnimationFrame(drawFrame)
    }

    drawFrame()
    return () => cancelAnimationFrame(rafRef.current)
  }, [size])

  /* ── Spawn pulses + feed event stream ── */
  useEffect(() => {
    const spawnId = setInterval(() => {
      const ev    = LIVE_EVENTS[spawnCounter.current % LIVE_EVENTS.length]
      const agent = AGENTS.find(a => a.id === ev.agentId)
      if (!agent) { spawnCounter.current++; return }

      /* Start from ~120° offset so it visibly travels */
      const direction = spawnCounter.current % 2 === 0 ? 110 : -110
      const jitter    = (Math.random() - 0.5) * 40
      pulsesRef.current.push({
        angle:       agent.angle + direction + jitter,
        targetAngle: agent.angle,
        color:       agent.color,
        agentId:     agent.id,
        alpha:       1,
      })

      /* Add to stream (keep last 8) */
      setStreamEvents(prev => [ev, ...prev].slice(0, 8))
      spawnCounter.current++
    }, 2000)

    return () => clearInterval(spawnId)
  }, [])

  /* ── Scanning: sequential agent highlight ── */
  useEffect(() => {
    if (state !== 'scanning') { setScanIdx(-1); return }
    let i = 0
    const iv = setInterval(() => { setScanIdx(i % AGENTS.length); i++ }, 350)
    return () => clearInterval(iv)
  }, [state])

  /* ── SVG interaction callbacks ── */
  const onEnter = useCallback((id: string) => setHoveredId(id), [])
  const onLeave = useCallback(() => setHoveredId(null), [])

  /* ── Derived values ── */
  const centerFill = state === 'complete' ? '#0A2018' : state === 'scanning' ? '#12082A' : '#060D1C'
  const centerColor = state === 'complete' ? '#34D399' : state === 'scanning' ? '#C084FC'
    : state === 'caution' ? '#FBBF24' : '#93C5FD'
  const ringColor = state === 'complete' ? '#059669' : state === 'scanning' ? '#7C3AED'
    : state === 'caution' ? '#D97706' : '#2563EB'

  const dotCls = state === 'idle' ? 'oracle-dot--idle' : state === 'scanning' ? 'oracle-dot--scanning'
    : state === 'complete' ? 'oracle-dot--complete' : 'oracle-dot--caution'
  const lblCls = state === 'complete' ? 'text-emerald-600 font-semibold'
    : state === 'scanning' ? 'text-purple-500 font-medium'
    : state === 'caution'  ? 'text-amber-600 font-medium' : 'text-slate-400'

  const centerVerdict = verdict ?? (state === 'complete' ? 'BUY' : state === 'caution' ? 'MIXED' : 'ORACLE')
  const centerScore   = score != null ? Math.round(score * 100) : null

  return (
    <div className="oracle-root">

      {/* ── Diagram wrapper (SVG + Canvas overlay + Hover card) ── */}
      <div style={{ position: 'relative', width: size, height: size }}>

        {/* Layer 1: SVG ring diagram */}
        <svg viewBox="0 0 360 360" width={size} height={size}
          style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
          <defs>
            <filter id="orbGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            <filter id="orbGlowSm" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            <radialGradient id="bgGrad" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#BFDBFE" stopOpacity="0.1"/>
              <stop offset="100%" stopColor="#BFDBFE" stopOpacity="0"/>
            </radialGradient>
          </defs>

          {/* Ambient halo */}
          <circle cx={CX} cy={CY} r={175} fill="url(#bgGrad)"/>

          {/* Spinning deco rings */}
          <g className="oracle-spin-slow">
            <circle cx={CX} cy={CY} r={R1+12} fill="none" stroke="rgba(148,163,184,0.07)" strokeWidth="1" strokeDasharray="4 9"/>
          </g>
          <g className="oracle-spin-rev">
            <circle cx={CX} cy={CY} r={R2-14} fill="none" stroke="rgba(148,163,184,0.06)" strokeWidth="1" strokeDasharray="3 11"/>
          </g>

          {/* Zone arc fills */}
          {ZONES.map(z => (
            <path key={z.label} d={arcPath(R1, R2, z.start + 3, z.end - 3)}
              fill={z.color} opacity={state === 'scanning' ? 0.22 : 0.13}
              style={{ transition:'opacity 0.4s' }}/>
          ))}
          {/* Zone arc borders */}
          {ZONES.map(z => (
            <path key={z.label+'-b'} d={arcPath(R1, R2, z.start + 3, z.end - 3)}
              fill="none" stroke={z.color} strokeWidth="0.8" opacity={0.4}/>
          ))}
          {/* Zone labels */}
          {ZONES.map(z => {
            const mid = polar((R1+R2)/2, (z.start+z.end)/2)
            return (
              <text key={z.label+'-t'} x={mid.x} y={mid.y}
                textAnchor="middle" dominantBaseline="middle"
                fontSize="8.5" fontWeight="700" letterSpacing="1.5"
                fill={z.color} opacity={0.7}
                style={{ fontFamily:'Inter,system-ui,sans-serif' }}>
                {z.label}
              </text>
            )
          })}

          {/* Agent dots + labels */}
          {AGENTS.map((ag, i) => {
            const dot    = polar(RD, ag.angle)
            const lbl    = polar(RL + 9, ag.angle)
            const isLit  = litAgents.has(ag.id) || (state === 'scanning' && scanIdx === i) || state === 'complete'
            const isHov  = hoveredId === ag.id

            const anchor = ag.angle > -67.5 && ag.angle < 67.5 ? 'start'
              : (ag.angle > 112.5 || ag.angle < -112.5) ? 'end' : 'middle'

            return (
              <g key={ag.id}
                onMouseEnter={() => onEnter(ag.id)}
                onMouseLeave={onLeave}
                style={{ cursor:'pointer' }}>

                {/* Hover / lit glow ring */}
                {(isLit || isHov) && (
                  <circle cx={dot.x} cy={dot.y} r={isHov ? 20 : 15}
                    fill={ag.color} opacity={isHov ? 0.25 : 0.18} filter="url(#orbGlow)"/>
                )}

                {/* Agent dot */}
                <circle cx={dot.x} cy={dot.y} r={isHov ? 11 : 9}
                  fill={ag.color} opacity={isLit || isHov ? 1 : 0.72}
                  filter="url(#orbGlowSm)"
                  style={{ transition:'r 0.15s, opacity 0.3s' }}/>

                {/* Dot specular */}
                <circle cx={dot.x - 2.5} cy={dot.y - 2.5} r={3} fill="rgba(255,255,255,0.4)"/>

                {/* Primary label */}
                <text x={lbl.x} y={lbl.y - 5.5} textAnchor={anchor} dominantBaseline="middle"
                  fontSize="9.5" fontWeight="700"
                  fill={isLit || isHov ? ag.color : '#475569'}
                  style={{ fontFamily:'Inter,system-ui,sans-serif', transition:'fill 0.3s' }}>
                  {ag.label}
                </text>
                {/* Sub label */}
                <text x={lbl.x} y={lbl.y + 6} textAnchor={anchor} dominantBaseline="middle"
                  fontSize="7.5" fontWeight="400"
                  fill={isLit || isHov ? ag.color : '#94A3B8'} opacity={0.75}
                  style={{ fontFamily:'Inter,system-ui,sans-serif', transition:'fill 0.3s' }}>
                  {ag.sub}
                </text>
              </g>
            )
          })}

          {/* Center circle */}
          <circle cx={CX} cy={CY} r={RC+8} fill="none"
            stroke={ringColor} strokeWidth="1.5" opacity={0.4} filter="url(#orbGlow)"/>
          <circle cx={CX} cy={CY} r={RC} fill={centerFill} filter="url(#orbGlow)"/>
          <circle cx={CX} cy={CY} r={RC} fill="none"
            stroke={centerColor} strokeWidth="0.8" opacity={0.22} strokeDasharray="3 6"/>

          <text x={CX} y={CY - (centerScore ? 20 : 14)} textAnchor="middle" dominantBaseline="middle"
            fontSize="9" fontWeight="600" letterSpacing="2.5" fill="#64748B"
            style={{ fontFamily:'JetBrains Mono,monospace' }}>
            ORACLE
          </text>
          <text x={CX} y={CY + (centerScore ? 0 : 6)} textAnchor="middle" dominantBaseline="middle"
            fontSize={state === 'complete' ? 19 : 13} fontWeight="800"
            fill={centerColor} filter="url(#orbGlowSm)"
            style={{ fontFamily:'Inter,system-ui,sans-serif' }}>
            {centerVerdict}
          </text>
          {centerScore && (
            <text x={CX} y={CY + 17} textAnchor="middle" dominantBaseline="middle"
              fontSize="9" fontWeight="500" fill={centerColor} opacity={0.7}
              style={{ fontFamily:'Inter,system-ui,sans-serif' }}>
              {centerScore}% confidence
            </text>
          )}
          <text x={CX} y={CY + (centerScore ? 30 : 22)} textAnchor="middle" dominantBaseline="middle"
            fontSize="7" fill="#94A3B8"
            style={{ fontFamily:'Inter,system-ui,sans-serif' }}>
            {AGENTS.length} agents active
          </text>
        </svg>

        {/* Layer 2: Canvas for traveling pulses */}
        <canvas
          ref={canvasRef}
          style={{ position:'absolute', inset:0, width:size, height:size, pointerEvents:'none' }}
        />

        {/* Layer 3: Hover card */}
        {hoveredId && (
          <HoverCard
            agentId={hoveredId}
            angle={AGENTS.find(a => a.id === hoveredId)!.angle}
            size={size}
          />
        )}
      </div>

      {/* Status label */}
      <div className="oracle-status">
        <span className={`oracle-dot ${dotCls}`}/>
        <span className={`oracle-status-text ${lblCls}`}>
          {state === 'idle'     && 'Hover any agent to see live signals'}
          {state === 'scanning' && 'All 8 agents scanning in parallel…'}
          {state === 'complete' && 'Analysis complete — verdict ready'}
          {state === 'caution'  && 'Mixed signals — review recommended'}
        </span>
      </div>

      {/* Live event stream */}
      <EventStream events={streamEvents} />
    </div>
  )
}
