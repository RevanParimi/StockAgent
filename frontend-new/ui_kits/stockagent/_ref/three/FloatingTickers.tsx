import { useRef, useMemo, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Text } from '@react-three/drei'
import * as THREE from 'three'

const TICKERS = ['MARUTI', 'TATAMOTORS', 'M&M', 'HEROMOTOCO', 'BAJAJ-AUTO',
                 'EICHERMOT', 'TVSMOTORS', 'ASHOKLEY', 'ESCORTS', 'FORCEMOT']

interface FloatingTickerProps {
  label: string
  position: [number, number, number]
  phase: number
}

function FloatingTicker({ label, position, phase }: FloatingTickerProps) {
  const ref = useRef<THREE.Group>(null)

  useFrame(() => {
    if (!ref.current) return
    const t = Date.now() * 0.001
    ref.current.position.y = position[1] + Math.sin(t + phase) * 0.3
    ref.current.position.x = position[0] + Math.cos(t * 0.7 + phase) * 0.15
  })

  return (
    <group ref={ref} position={position}>
      <Text
        font="/fonts/JetBrainsMono-Regular.ttf"
        fontSize={0.25}
        color="#06b6d4"
        fillOpacity={0.7}
        anchorX="center"
        anchorY="middle"
      >
        {label}
      </Text>
    </group>
  )
}

function TickerScene() {
  const positions = useMemo(() =>
    TICKERS.map(() => [
      (Math.random() - 0.5) * 14,
      (Math.random() - 0.5) * 8,
      (Math.random() - 0.5) * 4,
    ] as [number, number, number]),
    []
  )

  return (
    <>
      {TICKERS.map((t, i) => (
        <FloatingTicker
          key={t}
          label={t}
          position={positions[i]}
          phase={i * 0.7}
        />
      ))}
      <ambientLight intensity={0.8} />
    </>
  )
}

export function FloatingTickers({ className = '' }: { className?: string }) {
  return (
    <Suspense fallback={null}>
      <Canvas
        camera={{ position: [0, 0, 8], fov: 60 }}
        style={{ background: 'transparent' }}
        gl={{ antialias: true, alpha: true }}
        className={className}
      >
        <TickerScene />
      </Canvas>
    </Suspense>
  )
}
