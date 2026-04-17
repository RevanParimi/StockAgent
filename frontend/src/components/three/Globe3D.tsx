import { useRef, useMemo, Suspense } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

// City coordinates [lng, lat] for 10 OEM cities
const CITIES: Array<{ name: string; lng: number; lat: number }> = [
  { name: 'MARUTI',     lng: 77.0266, lat: 28.4595 },
  { name: 'TATAMOTORS', lng: 86.1860, lat: 22.8046 },
  { name: 'M&M',        lng: 72.8777, lat: 18.9402 },
  { name: 'HEROMOTOCO', lng: 77.1025, lat: 28.7041 },
  { name: 'BAJAJ-AUTO', lng: 73.8567, lat: 18.5204 },
  { name: 'EICHERMOT',  lng: 77.5946, lat: 12.9716 },
  { name: 'TVSMOTORS',  lng: 77.8253, lat: 12.7409 },
  { name: 'ASHOKLEY',   lng: 80.2707, lat: 13.0827 },
  { name: 'ESCORTS',    lng: 77.3178, lat: 28.4082 },
  { name: 'FORCEMOT',   lng: 73.8567, lat: 18.5204 },
]

function lngLatToVec3(lng: number, lat: number, radius: number): THREE.Vector3 {
  const phi   = (90 - lat)  * (Math.PI / 180)
  const theta = (lng + 180) * (Math.PI / 180)
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
     radius * Math.cos(phi),
     radius * Math.sin(phi) * Math.sin(theta),
  )
}

function GlobeScene({ mousePos }: { mousePos: { x: number; y: number } }) {
  const groupRef = useRef<THREE.Group>(null)
  const nodesRef = useRef<THREE.Mesh[]>([])
  const { size } = useThree()

  // Build grid lines geometry
  const gridGeo = useMemo(() => {
    const points: THREE.Vector3[] = []
    for (let lat = -80; lat <= 80; lat += 20) {
      for (let lng = 0; lng < 360; lng += 5) {
        points.push(lngLatToVec3(lng,     lat, 2.02))
        points.push(lngLatToVec3(lng + 5, lat, 2.02))
      }
    }
    for (let lng = 0; lng < 360; lng += 20) {
      for (let lat = -80; lat <= 80; lat += 5) {
        points.push(lngLatToVec3(lng, lat,     2.02))
        points.push(lngLatToVec3(lng, lat + 5, 2.02))
      }
    }
    const geo = new THREE.BufferGeometry().setFromPoints(points)
    return geo
  }, [])

  useFrame((_, delta) => {
    if (!groupRef.current) return
    groupRef.current.rotation.y += delta * 0.08
    // Mouse parallax
    const targetX = (mousePos.y / size.height - 0.5) *  0.3
    const targetY = (mousePos.x / size.width  - 0.5) * -0.3
    groupRef.current.rotation.x += (targetX - groupRef.current.rotation.x) * 0.05
    // Pulse nodes
    const t = Date.now() * 0.002
    nodesRef.current.forEach((node, i) => {
      const scale = 1 + 0.4 * Math.sin(t + i * 0.7)
      node.scale.setScalar(scale)
    })
  })

  return (
    <group ref={groupRef}>
      {/* Globe sphere */}
      <mesh>
        <sphereGeometry args={[2, 64, 64]} />
        <meshStandardMaterial
          color="#0a0f1e"
          roughness={0.8}
          metalness={0.1}
        />
      </mesh>
      {/* Grid wireframe */}
      <lineSegments geometry={gridGeo}>
        <lineBasicMaterial color="#1e3a5f" transparent opacity={0.3} />
      </lineSegments>
      {/* City nodes */}
      {CITIES.map((city, i) => {
        const pos = lngLatToVec3(city.lng, city.lat, 2.08)
        return (
          <mesh
            key={city.name}
            position={pos}
            ref={(el) => { if (el) nodesRef.current[i] = el }}
          >
            <sphereGeometry args={[0.04, 8, 8]} />
            <meshStandardMaterial
              color="#06b6d4"
              emissive="#06b6d4"
              emissiveIntensity={2}
            />
          </mesh>
        )
      })}
      {/* Ambient + point light */}
      <ambientLight intensity={0.3} />
      <pointLight position={[5, 5, 5]} intensity={1.5} color="#3b82f6" />
      <pointLight position={[-5, -3, -5]} intensity={0.5} color="#8b5cf6" />
    </group>
  )
}

interface Globe3DProps {
  mousePos?: { x: number; y: number }
}

export function Globe3D({ mousePos = { x: 0, y: 0 } }: Globe3DProps) {
  return (
    <Suspense fallback={null}>
      <Canvas
        camera={{ position: [0, 0, 5], fov: 45 }}
        style={{ background: 'transparent' }}
        gl={{ antialias: true, alpha: true }}
      >
        <GlobeScene mousePos={mousePos} />
      </Canvas>
    </Suspense>
  )
}
