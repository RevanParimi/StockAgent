import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Line } from '@react-three/drei';
import {
  Color, Object3D, QuadraticBezierCurve3, Quaternion, TubeGeometry, Vector3,
} from 'three';
import { MOTION, OPACITY, moduleColour, nodeOf } from '../theme.js';
import { curvePoint } from '../lib/world.js';

const UP = new Vector3(0, 1, 0);
const colourOf = (flow) => moduleColour(nodeOf(flow.from));
const curveOf = (flow) => new QuadraticBezierCurve3(...flow.points.map((p) => new Vector3(...p)));

function Tube({ flow, curve, level, onHover }) {
  const thickness = level === 'bright' ? 0.17 : 0.09;
  const geometry = useMemo(() => new TubeGeometry(curve, 40, thickness, 8, false),
    [curve, thickness]);
  const hit = useMemo(() => new TubeGeometry(curve, 20, 0.6, 5, false), [curve]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => hit.dispose(), [hit]);

  const head = useMemo(() => {
    const at = curve.getPointAt(0.84);
    const turn = new Quaternion().setFromUnitVectors(UP, curve.getTangentAt(0.84).normalize());
    return { at, turn };
  }, [curve]);

  const faded = level === 'faded';
  const opacity = faded ? OPACITY.fadedFlow : level === 'bright' ? 1 : 0.7;
  const colour = colourOf(flow);
  return (
    <group>
      {flow.ring ? (
        <Line points={curve.getPoints(40)} color={colour} lineWidth={level === 'bright' ? 3 : 1.6}
          dashed dashSize={0.55} gapSize={0.4} transparent opacity={opacity} raycast={() => null} />
      ) : (
        <mesh geometry={geometry} raycast={() => null}>
          <meshStandardMaterial color={colour} emissive={colour}
            emissiveIntensity={level === 'bright' ? 0.9 : 0.4} transparent opacity={opacity}
            depthWrite={!faded} />
        </mesh>
      )}
      <mesh position={head.at} quaternion={head.turn} raycast={() => null}>
        <coneGeometry args={[level === 'bright' ? 0.48 : 0.34, 1.05, 12]} />
        <meshStandardMaterial color={colour} emissive={colour} emissiveIntensity={0.6}
          transparent opacity={opacity} />
      </mesh>
      <mesh
        geometry={hit}
        onPointerOver={(e) => { e.stopPropagation(); onHover({ flow, x: e.clientX, y: e.clientY }); }}
        onPointerMove={(e) => { e.stopPropagation(); onHover({ flow, x: e.clientX, y: e.clientY }); }}
        onPointerOut={() => onHover(null)}
      >
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
}

/** Dots that travel along the flows, so the direction can be seen. */
function Dots({ flows, levels, moving }) {
  const mesh = useRef(null);
  const clock = useRef(0);
  const invalidate = useThree((s) => s.invalidate);
  const helper = useMemo(() => new Object3D(), []);
  const count = flows.length * MOTION.particlesPerFlow;

  useEffect(() => {
    if (!mesh.current) return;
    const colour = new Color();
    flows.forEach((flow, f) => {
      colour.set(colourOf(flow)).lerp(new Color('#ffffff'), 0.45);
      for (let i = 0; i < MOTION.particlesPerFlow; i += 1) {
        mesh.current.setColorAt(f * MOTION.particlesPerFlow + i, colour);
      }
    });
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
    invalidate();
  }, [flows, invalidate]);

  useEffect(() => { invalidate(); }, [levels, moving, invalidate]);

  useFrame((_, delta) => {
    if (!mesh.current) return;
    if (moving) clock.current += Math.min(delta, 0.1);
    flows.forEach((flow, f) => {
      const level = levels.get(flow.key);
      for (let i = 0; i < MOTION.particlesPerFlow; i += 1) {
        const u = (clock.current / MOTION.secondsPerFlow + i / MOTION.particlesPerFlow) % 1;
        helper.position.set(...curvePoint(flow.points, u));
        helper.scale.setScalar(level === 'faded' ? 0 : level === 'bright' ? 1.5 : 1);
        helper.updateMatrix();
        mesh.current.setMatrixAt(f * MOTION.particlesPerFlow + i, helper.matrix);
      }
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh key={count} ref={mesh} args={[undefined, undefined, count]} frustumCulled={false}
      raycast={() => null}>
      <sphereGeometry args={[0.15, 10, 10]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

export function Flows({ flows, selected, touched, lit, hovered, moving, preset, onHover }) {
  const curves = useMemo(() => new Map(flows.map((f) => [f.key, curveOf(f)])), [flows]);
  const levels = useMemo(() => new Map(flows.map((f) => {
    const level = hovered === f.key ? 'bright'
      : lit ? (lit.flows.has(f.key) ? 'bright' : 'faded')
        : !selected ? (preset === 'below' ? 'faded' : 'rest')
          : touched.flows.has(f.key) ? 'bright' : 'faded';
    return [f.key, level];
  })), [flows, selected, touched, lit, hovered, preset]);
  return (
    <group>
      {flows.map((f) => (
        <Tube key={f.key} flow={f} curve={curves.get(f.key)} level={levels.get(f.key)}
          onHover={onHover} />
      ))}
      <Dots flows={flows} levels={levels} moving={moving} />
    </group>
  );
}

/** The storage pipes: from each module to the stores it writes. */
const RESTING_PIPE = { top: 0.06, below: 0.85 };

export function Pipes({ pipes, selected, touched, lit, preset }) {
  return pipes.map((p) => {
    const related = lit ? lit.stores.has(p.store) && lit.modules.has(p.module)
      : selected && touched.stores.has(p.store) && touched.modules.has(p.module)
        && p.module === selected.split('.')[0];
    const opacity = lit || selected ? (related ? 0.85 : 0.05) : RESTING_PIPE[preset] ?? 0.32;
    const points = Array.from({ length: 17 }, (_, i) => curvePoint(p.points, i / 16));
    return (
      <Line key={`${p.module}>${p.store}`} points={points} color={moduleColour(p.module)}
        lineWidth={related ? 2.4 : 1.2} transparent opacity={opacity} raycast={() => null} />
    );
  });
}
