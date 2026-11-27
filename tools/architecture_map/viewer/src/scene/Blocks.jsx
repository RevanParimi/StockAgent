import { useMemo, useState } from 'react';
import { RoundedBox, Line } from '@react-three/drei';
import { BoxGeometry, Color, DoubleSide, EdgesGeometry } from 'three';
import { OPACITY, PLANE, SURFACE, moduleColour } from '../theme.js';

// A click, not the end of an orbit drag.
const isClick = (event) => event.delta < 6;

function Outline({ size, colour, opacity = 1 }) {
  const geometry = useMemo(() => {
    const box = new BoxGeometry(...size);
    const edges = new EdgesGeometry(box);
    box.dispose();
    return edges;
  }, [size]);
  return (
    <lineSegments geometry={geometry} raycast={() => null}>
      <lineBasicMaterial color={colour} transparent opacity={opacity} toneMapped={false} />
    </lineSegments>
  );
}

const grow = (size, by) => size.map((v) => v + by);
// Edges a step towards white, so the bloom picks them out.
const lit = (colour) => new Color(colour).lerp(new Color('#ffffff'), 0.35);

export function Block({ block, colour, state, onSelect, onHover }) {
  const [over, setOver] = useState(false);
  const faded = state === 'faded';
  const selected = state === 'selected';
  const glow = selected ? 1 : over ? 0.75 : 0.45;
  const outline = useMemo(() => grow(block.size, 0.04), [block.size]);
  const halo = useMemo(() => grow(block.size, 0.5), [block.size]);
  const bright = useMemo(() => lit(colour), [colour]);
  return (
    <group position={block.pos}>
      <RoundedBox
        args={block.size}
        radius={Math.min(0.25, block.size[1] / 3)}
        onClick={(e) => { e.stopPropagation(); if (isClick(e)) onSelect(block.id); }}
        onPointerOver={(e) => { e.stopPropagation(); setOver(true); onHover?.(true); }}
        onPointerOut={() => { setOver(false); onHover?.(false); }}
      >
        <meshStandardMaterial
          color={colour}
          emissive={colour}
          emissiveIntensity={faded ? 0.05 : glow}
          transparent
          opacity={faded ? OPACITY.faded : 0.78}
          depthWrite={!faded}
        />
      </RoundedBox>
      <Outline size={outline} colour={bright} opacity={faded ? OPACITY.faded : 1} />
      {selected ? <Outline size={halo} colour={SURFACE.focus} /> : null}
    </group>
  );
}

export function Modules({ modules, selected, touched, preset, onSelect, onHover }) {
  return modules.map((m) => {
    const state = !selected ? (preset === 'below' && m.plane === 'top' ? 'faded' : 'rest')
      : selected.split('.')[0] === m.id ? 'selected'
        : touched.modules.has(m.id) ? 'rest' : 'faded';
    return (
      <Block key={m.id} block={m} colour={moduleColour(m.id)} state={state} onSelect={onSelect}
        onHover={onHover} />
    );
  });
}

export function Parts({ parts, moduleId, selected, onSelect, onHover, moduleBlock }) {
  return parts.map((p) => (
    <group key={p.id}>
      <Line
        points={[[moduleBlock.pos[0], moduleBlock.pos[1] + 0.8, moduleBlock.pos[2]], p.pos]}
        color={moduleColour(moduleId)}
        lineWidth={1}
        transparent
        opacity={0.5}
        raycast={() => null}
      />
      <Block block={p} colour={moduleColour(moduleId)}
        state={selected === p.id ? 'selected' : 'rest'} onSelect={onSelect} onHover={onHover} />
    </group>
  ));
}

const RESTING_STORE = { top: 0.14, below: 0.7 };

export function Stores({ stores, selected, touched, preset }) {
  return stores.map((s) => {
    const opacity = !selected ? RESTING_STORE[preset] ?? 0.5
      : touched.stores.has(s.id) ? 0.95 : OPACITY.faded;
    return (
      <group key={s.id} position={s.pos}>
        <mesh>
          <boxGeometry args={s.size} />
          <meshStandardMaterial color={PLANE.planeStores} emissive={PLANE.planeStores}
            emissiveIntensity={opacity > 0.9 ? 0.55 : 0.18} transparent opacity={opacity}
            depthWrite={opacity > 0.4} />
        </mesh>
        <Outline size={s.size} colour={PLANE.planeStores} opacity={opacity} />
      </group>
    );
  });
}

export function Externals({ externals, selected, touched, preset }) {
  return externals.map((e) => {
    const faded = selected ? !touched.modules.has(e.id) : preset === 'below';
    return (
      <mesh key={e.id} position={e.pos}>
        <octahedronGeometry args={[1.05]} />
        <meshStandardMaterial color={SURFACE.ink2} emissive={SURFACE.ink2}
          emissiveIntensity={0.3} transparent opacity={faded ? OPACITY.faded : 0.85} />
      </mesh>
    );
  });
}

const PLANE_TOKEN = { top: 'planeTop', middle: 'planeMiddle', base: 'planeBase',
  stores: 'planeStores' };

export function Planes({ planes, ring }) {
  const ellipse = useMemo(() => Array.from({ length: 97 }, (_, i) => {
    const a = (i / 96) * Math.PI * 2;
    return [ring.rx * Math.cos(a), -0.9, ring.rz * Math.sin(a)];
  }), [ring.rx, ring.rz]);
  return (
    <group>
      {planes.map((p) => {
        const [x, y, z] = p.centre;
        const [w, d] = p.size;
        const colour = PLANE[PLANE_TOKEN[p.id]];
        const edge = [[x - w / 2, y, z - d / 2], [x + w / 2, y, z - d / 2],
          [x + w / 2, y, z + d / 2], [x - w / 2, y, z + d / 2], [x - w / 2, y, z - d / 2]];
        return (
          <group key={p.id}>
            <mesh position={p.centre} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null}>
              <planeGeometry args={p.size} />
              <meshBasicMaterial color={colour} transparent opacity={0.055} side={DoubleSide}
                depthWrite={false} />
            </mesh>
            <Line points={edge} color={colour} lineWidth={p.id === 'base' ? 2.5 : 1} transparent
              opacity={p.id === 'base' ? 0.75 : 0.4} raycast={() => null} />
          </group>
        );
      })}
      <Line points={ellipse} color={PLANE.planeRing} lineWidth={1.4} dashed dashSize={0.7}
        gapSize={0.5} transparent opacity={0.7} raycast={() => null} />
    </group>
  );
}
