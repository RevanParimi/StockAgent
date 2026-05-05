import { useRef, useMemo, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const PARTICLE_COUNT = 300

function Particles({ mobile = false }: { mobile?: boolean }) {
  const count = mobile ? 150 : PARTICLE_COUNT
  const pointsRef = useRef<THREE.Points>(null)
  const linesRef  = useRef<THREE.LineSegments>(null)

  const { positions, linePositions } = useMemo(() => {
    const pos = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const r = 8 + Math.random() * 4
      const theta = Math.random() * Math.PI * 2
      const phi   = Math.acos(2 * Math.random() - 1)
      pos[i * 3]     = r * Math.sin(phi) * Math.cos(theta)
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
      pos[i * 3 + 2] = r * Math.cos(phi)
    }

    // Compute lines for nearby particles
    const MAX_DIST = 3
    const lineVerts: number[] = []
    for (let i = 0; i < count; i++) {
      for (let j = i + 1; j < count; j++) {
        const dx = pos[i*3] - pos[j*3]
        const dy = pos[i*3+1] - pos[j*3+1]
        const dz = pos[i*3+2] - pos[j*3+2]
        const dist = Math.sqrt(dx*dx + dy*dy + dz*dz)
        if (dist < MAX_DIST) {
          lineVerts.push(pos[i*3], pos[i*3+1], pos[i*3+2])
          lineVerts.push(pos[j*3], pos[j*3+1], pos[j*3+2])
        }
      }
    }

    return { positions: pos, linePositions: new Float32Array(lineVerts) }
  }, [count])

  useFrame((_, delta) => {
    if (pointsRef.current) {
      pointsRef.current.rotation.y += delta * 0.03
      pointsRef.current.rotation.x += delta * 0.01
    }
    if (linesRef.current) {
      linesRef.current.rotation.y += delta * 0.03
      linesRef.current.rotation.x += delta * 0.01
    }
  })

  return (
    <>
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[positions, 3]}
          />
        </bufferGeometry>
        <pointsMaterial
          size={0.06}
          color="#06b6d4"
          transparent
          opacity={0.7}
          sizeAttenuation
        />
      </points>
      <lineSegments ref={linesRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[linePositions, 3]}
          />
        </bufferGeometry>
        <lineBasicMaterial color="#3b82f6" transparent opacity={0.15} />
      </lineSegments>
      <ambientLight intensity={0.5} />
    </>
  )
}

interface ParticleFieldProps {
  mobile?: boolean
  className?: string
}

export function ParticleField({ mobile = false, className = '' }: ParticleFieldProps) {
  return (
    <Suspense fallback={null}>
      <Canvas
        camera={{ position: [0, 0, 12], fov: 60 }}
        style={{ background: 'transparent' }}
        gl={{ antialias: true, alpha: true }}
        className={className}
      >
        <Particles mobile={mobile} />
      </Canvas>
    </Suspense>
  )
}
