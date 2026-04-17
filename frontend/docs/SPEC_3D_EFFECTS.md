# 3D & Interactive Effects Specification

## 1. Globe3D (`src/components/three/Globe3D.tsx`) ✅ BUILT
```
Location: Landing page hero (full-bleed background)

THREE.SphereGeometry(2, 64, 64)
Material: MeshStandardMaterial, color #0a0f1e, roughness 0.8

Grid overlay (LineSegments):
  - Latitude lines every 20°, longitude lines every 20°
  - Color: #1e3a5f, opacity 0.3

10 city nodes (small spheres, radius 0.04):
  Gurugram  [72.80°N 28.46°]: MARUTI
  Jamshedpur[86.19°E 22.80°]: TATAMOTORS
  Mumbai    [72.88°E 18.94°]: M&M
  Delhi     [77.10°E 28.70°]: HEROMOTOCO
  Pune      [73.86°E 18.52°]: BAJAJ-AUTO
  Bengaluru [77.59°E 12.97°]: EICHERMOT
  Hosur     [77.83°E 12.74°]: TVSMOTORS
  Chennai   [80.27°E 13.08°]: ASHOKLEY
  Faridabad [77.32°E 28.41°]: ESCORTS
  Pune      [73.86°E 18.52°]: FORCEMOT

Node material: color #06b6d4, emissive #06b6d4, emissiveIntensity 2
Pulse animation: scale sine wave 1.0→1.5→1.0 per node (staggered phase)

Auto-rotation: groupRef.rotation.y += delta * 0.08

Mouse parallax:
  targetX = (mousePos.y / height - 0.5) *  0.3
  targetY = (mousePos.x / width  - 0.5) * -0.3
  Smooth lerp: rotation += (target - rotation) * 0.05

Lighting:
  AmbientLight intensity 0.3
  PointLight [5,5,5] color #3b82f6, intensity 1.5
  PointLight [-5,-3,-5] color #8b5cf6, intensity 0.5

Props: { mousePos?: { x: number, y: number } }
Wrapped in React.Suspense + lazy import in Landing.tsx
```

## 2. ParticleField (`src/components/three/ParticleField.tsx`) ✅ BUILT
```
Location: Auth page left panel background

THREE.Points, BufferGeometry
300 particles (150 on mobile)
Positions: random on sphere of radius 8–12
Material: PointsMaterial, size 0.06, color #06b6d4, transparent opacity 0.7

Connecting lines (LineSegments):
  - Connect particles within distance 3.0
  - Color: #3b82f6, opacity 0.15

Animation: entire group rotates slowly
  rotation.y += delta * 0.03
  rotation.x += delta * 0.01

Props: { mobile?: boolean, className?: string }
Wrapped in React.Suspense + lazy import in Auth.tsx
```

## 3. FloatingTickers (`src/components/three/FloatingTickers.tsx`) ✅ BUILT
```
Location: Landing hero overlay (optional), Auth left panel

@react-three/drei <Text> component
10 ticker names at random 3D positions
Font: JetBrains Mono, color #06b6d4, fillOpacity 0.7, fontSize 0.25

Drift animation per ticker (individual):
  position.y = baseY + sin(t + phase) * 0.3
  position.x = baseX + cos(t*0.7 + phase) * 0.15

Props: { className?: string }
Wrapped in React.Suspense
```

## 4. Custom Cursor (`src/components/layout/CustomCursor.tsx`) ✅ BUILT
```
Activated: document.addEventListener('mousemove', ...)
Disabled on: window.matchMedia('(pointer: coarse)') → touch devices

Inner dot:
  - 8px × 8px, white fill, border-radius 50%
  - Lag: 0ms (moves instantly to cursor position)
  - CSS: position fixed, z-index 9999

Outer ring:
  - 32px × 32px, border 1px solid rgba(6,182,212,0.6)
  - Lag: 80ms (CSS transition: 0.15s lerp factor)
  - Expands to 64px + fill on hover over a/button/[role=button]

Trail canvas:
  - Full-page fixed canvas, z-index 9997, pointer-events none
  - Every mousemove: push {x, y, a:1.0} to trailRef
  - Each frame: draw fading dots, multiply alpha by 0.92
  - Clear and redraw each RAF frame

RAF loop: requestAnimationFrame for smooth ring lag + trail decay
Cleanup: removeEventListener + cancelAnimationFrame on unmount
```

## 5. StockCard 3D Tilt (Phase 2)
```
Component: src/components/watchlist/StockCard.tsx

onMouseMove handler:
  const rect = card.getBoundingClientRect()
  const x =  (e.clientY - rect.top  - rect.height/2) / (rect.height/2) * 8
  const y = -(e.clientX - rect.left - rect.width/2)  / (rect.width/2)  * 8
  card.style.transform = `perspective(1000px) rotateX(${x}deg) rotateY(${y}deg)`
  card.style.transition = 'transform 0.1s ease'

onMouseLeave:
  card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg)'
  card.style.transition = 'transform 0.3s ease'

Max tilt: ±8 degrees
```

## 6. GSAP ScrollTrigger Effects (Phase 1 Landing)
```
Agent cards: fromTo opacity 0→1, x ±60→0, stagger 0.05s
  scrollTrigger: { trigger: card, start: 'top 85%' }

Section headings: fromTo opacity 0→1, y 30→0
  scrollTrigger: { trigger: heading, start: 'top 80%' }

ScoreGauge in demo: trigger animation when 80% in view
  scrollTrigger: { trigger: gauge, start: 'top 80%' }

All cleanup: ScrollTrigger.getAll().forEach(t => t.kill()) on unmount
```

## 7. Agent Card Stream Animation (Phase 3)
```
When WebSocket event arrives for agent:

1. Card border transition: border-accent-cyan (pulsing) → verdict-color glow
2. Score counter: AnimatedCounter from 0 to score (0.8s duration)
3. Fill bar: Framer Motion
   initial={{ width: '0%' }}
   animate={{ width: `${score * 100}%` }}
   transition={{ duration: 0.6, ease: 'easeOut' }}
4. Card spring pop:
   variants={{ complete: { scale: [1, 1.05, 1], transition: { duration: 0.3 } } }}
5. Icon color: gray → verdict color (transition 0.3s)
```

## 8. VerdictReveal Card Flip (Phase 3)
```
CSS 3D card flip using Framer Motion:

Front face: "Analyzing..." + spinner
Back face: score gauge + verdict badge

Trigger: when report received from WebSocket

Animation:
  rotateY: 0° → 180° (front exits)
  rotateY: -180° → 0° (back enters)
  Duration: 0.6s, ease: 'easeInOut'
  backfaceVisibility: 'hidden' on both faces

After flip:
  ScoreGauge needle animates 0 → final_score over 1.5s
  AnimatedCounter counts 0.00 → final_score over 1.5s
  VerdictBadge slides up from below with framer-motion
```

## 9. Framer Motion Page Transitions
```
Defined in: src/components/layout/PageTransition.tsx ✅ BUILT

Wraps all pages in AnimatePresence mode="wait"
Per-page motion.div with variants:
  initial: { opacity: 0, y: 20 }
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } }
  exit:    { opacity: 0, y: -10, transition: { duration: 0.2, ease: 'easeIn' } }
```

## Three.js Memory Management
All Three.js components must clean up on unmount:
```typescript
useEffect(() => {
  return () => {
    geometry.dispose()
    material.dispose()
    // R3F handles renderer cleanup automatically
  }
}, [])
```
R3F (react-three-fiber) handles renderer + scene disposal automatically
when the Canvas component unmounts.
