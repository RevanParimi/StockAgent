/*
 * PandaScene.tsx
 * Panda sits as a large CENTERED WATERMARK behind all page content.
 * z-index: 0 — every card/panel floats on top.
 * Opacity kept intentionally low so it reads as background art, not a puppet.
 */
import { useEffect, useRef } from 'react'
import { PandaCharacter, type PandaState } from './PandaCharacter'
import './PandaAnimations.css'

interface Props { state?: PandaState }

export function PandaScene({ state = 'idle' }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef    = useRef<number>(0)

  /* Floating blue particle dots */
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!

    type P = { x:number; y:number; r:number; dx:number; dy:number; a:number; da:number }
    const particles: P[] = []

    function resize() {
      canvas!.width  = window.innerWidth
      canvas!.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    function spawn(): P {
      return {
        x:  Math.random() * canvas!.width,
        y:  canvas!.height * 0.2 + Math.random() * canvas!.height * 0.7,
        r:  1 + Math.random() * 2.5,
        dx: (Math.random() - 0.5) * 0.35,
        dy: -(0.25 + Math.random() * 0.5),
        a:  0,
        da: 0.004 + Math.random() * 0.007,
      }
    }
    for (let i = 0; i < 32; i++) particles.push(spawn())

    function draw() {
      ctx.clearRect(0, 0, canvas!.width, canvas!.height)
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]
        p.x += p.dx; p.y += p.dy; p.a += p.da
        if (p.a > 0.55) p.da = -Math.abs(p.da)
        if (p.y < -10 || p.a < -0.05) { particles[i] = spawn(); continue }
        ctx.save()
        ctx.globalAlpha = Math.max(0, p.a)
        ctx.fillStyle = '#93C5FD'
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
      }
      rafRef.current = requestAnimationFrame(draw)
    }
    draw()
    return () => { window.removeEventListener('resize', resize); cancelAnimationFrame(rafRef.current) }
  }, [])

  return (
    /* Fixed layer — covers entire viewport, pointer-events none */
    <div
      aria-hidden="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      {/* Particle canvas */}
      <canvas
        ref={canvasRef}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      />

      {/* Soft radial halo centered where panda sits */}
      <div style={{
        position: 'absolute',
        top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 700, height: 700,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(191,219,254,0.30) 0%, rgba(239,246,255,0) 68%)',
        pointerEvents: 'none',
      }} />

      {/*
       * THE PANDA — centered, large watermark
       * opacity: 0.13 → reads as background art, not a foreground element
       * Cards placed on top will feel like they're "floating over" the panda
       */}
      <div style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -46%)',
        opacity: 0.13,
      }}>
        <PandaCharacter state={state} size={560} />
      </div>
    </div>
  )
}
