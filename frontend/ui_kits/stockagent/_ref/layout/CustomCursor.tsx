import { useEffect, useRef } from 'react'

export function CustomCursor() {
  const dotRef   = useRef<HTMLDivElement>(null)
  const ringRef  = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mouseRef = useRef({ x: 0, y: 0 })
  const ringPos  = useRef({ x: 0, y: 0 })
  const trailRef = useRef<Array<{ x: number; y: number; a: number }>>([])
  const rafRef   = useRef<number>(0)

  useEffect(() => {
    // Mobile: skip
    if (window.matchMedia('(pointer: coarse)').matches) return

    const dot  = dotRef.current!
    const ring = ringRef.current!
    const canvas = canvasRef.current!
    const ctx = canvas.getContext('2d')!

    const resize = () => {
      canvas.width  = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    const onMove = (e: MouseEvent) => {
      mouseRef.current = { x: e.clientX, y: e.clientY }
      dot.style.transform = `translate(${e.clientX - 4}px, ${e.clientY - 4}px)`
      trailRef.current.push({ x: e.clientX, y: e.clientY, a: 1 })
      if (trailRef.current.length > 20) trailRef.current.shift()
    }

    const onEnter = () => {
      ring.style.width  = '64px'
      ring.style.height = '64px'
      ring.style.background = 'rgba(6,182,212,0.1)'
    }
    const onLeave = () => {
      ring.style.width  = '32px'
      ring.style.height = '32px'
      ring.style.background = 'transparent'
    }

    document.querySelectorAll('a, button, [role="button"]').forEach((el) => {
      el.addEventListener('mouseenter', onEnter)
      el.addEventListener('mouseleave', onLeave)
    })

    const animate = () => {
      // Lag the ring
      ringPos.current.x += (mouseRef.current.x - ringPos.current.x) * 0.15
      ringPos.current.y += (mouseRef.current.y - ringPos.current.y) * 0.15
      ring.style.transform = `translate(${ringPos.current.x - 16}px, ${ringPos.current.y - 16}px)`

      // Trail canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      trailRef.current.forEach((pt, i) => {
        const radius = 2 + (i / trailRef.current.length) * 2
        ctx.beginPath()
        ctx.arc(pt.x, pt.y, radius, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(6,182,212,${pt.a * 0.3 * (i / trailRef.current.length)})`
        ctx.fill()
        pt.a *= 0.92
      })
      trailRef.current = trailRef.current.filter((p) => p.a > 0.01)

      rafRef.current = requestAnimationFrame(animate)
    }

    document.addEventListener('mousemove', onMove)
    rafRef.current = requestAnimationFrame(animate)

    return () => {
      document.removeEventListener('mousemove', onMove)
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(rafRef.current)
    }
  }, [])

  return (
    <>
      {/* Inner dot */}
      <div
        ref={dotRef}
        className="fixed top-0 left-0 w-2 h-2 rounded-full bg-white z-[9999] pointer-events-none"
        style={{ willChange: 'transform' }}
      />
      {/* Outer ring */}
      <div
        ref={ringRef}
        className="fixed top-0 left-0 w-8 h-8 rounded-full border border-[rgba(6,182,212,0.6)] z-[9998] pointer-events-none transition-[width,height,background] duration-200"
        style={{ willChange: 'transform' }}
      />
      {/* Trail canvas */}
      <canvas
        ref={canvasRef}
        className="fixed inset-0 z-[9997] pointer-events-none"
      />
    </>
  )
}
