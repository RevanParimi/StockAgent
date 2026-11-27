import { useMemo, useState } from 'react';
import { Line } from '@react-three/drei';
import { PLANE, SURFACE, moduleColour } from '../theme.js';
import { BEAD, TRACKS, ringPoint } from '../lib/play.js';

const DAY = 24 * 60;

// A click, not the end of an orbit drag.
const isClick = (event) => event.delta < 6;

function Bead({ bead, current, onPick, onHover }) {
  const [over, setOver] = useState(false);
  const colour = moduleColour(bead.job.module);
  const size = current ? BEAD * 2 : over ? BEAD * 1.4 : BEAD;
  return (
    <group position={bead.pos}>
      <mesh raycast={() => null}>
        <sphereGeometry args={[size, 16, 16]} />
        <meshStandardMaterial color={colour} emissive={colour}
          emissiveIntensity={current ? 1 : 0.55} />
      </mesh>
      {/* unseen, twice the bead: easier to point at (the slider and the list do the same) */}
      <mesh
        onClick={(e) => { e.stopPropagation(); if (isClick(e)) onPick(bead.index); }}
        onPointerOver={(e) => { e.stopPropagation(); setOver(true); onHover?.(true); }}
        onPointerOut={() => { setOver(false); onHover?.(false); }}
      >
        <sphereGeometry args={[BEAD * 2, 8, 8]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      {current ? (
        <mesh rotation={[-Math.PI / 2, 0, 0]} raycast={() => null}>
          <torusGeometry args={[size * 1.6, 0.09, 8, 48]} />
          <meshBasicMaterial color={SURFACE.focus} toneMapped={false} />
        </mesh>
      ) : null}
    </group>
  );
}

/** The day around the product: a ring for the daily jobs, one for the weekly, one for the
 *  monthly and yearly, a bead where each job runs and a hand at the time being shown. */
export default function ClockRing({ ring, beads, current, onPick, onHover }) {
  const tracks = useMemo(() => Object.keys(TRACKS).map((group) => ({
    group,
    points: Array.from({ length: 145 }, (_, i) => ringPoint(ring, (i * DAY) / 144, group)),
  })), [ring]);
  // a tick every hour on the daily ring, longer every six hours
  const ticks = useMemo(() => Array.from({ length: 24 }, (_, hour) => ({
    hour,
    points: [ringPoint(ring, hour * 60, 'daily', hour % 6 ? -0.7 : -1.6),
      ringPoint(ring, hour * 60, 'daily')],
  })), [ring]);
  const now = beads[current];
  const hand = now ? [ringPoint(ring, now.minutes, 'daily', -2.2),
    ringPoint(ring, now.minutes, 'calendar', 1.6)] : null;
  return (
    <group>
      {tracks.map((t) => (
        <Line key={t.group} points={t.points} color={PLANE.planeBase}
          lineWidth={t.group === 'daily' ? 2.5 : 1.5} transparent opacity={0.85}
          raycast={() => null} />
      ))}
      {ticks.map((t) => (
        <Line key={t.hour} points={t.points} color={SURFACE.edge} lineWidth={t.hour % 6 ? 1 : 2}
          transparent opacity={0.7} raycast={() => null} />
      ))}
      {hand ? <Line points={hand} color={SURFACE.focus} lineWidth={2.5} raycast={() => null} />
        : null}
      {beads.map((bead) => (
        <Bead key={bead.key} bead={bead} current={bead.index === current} onPick={onPick}
          onHover={onHover} />
      ))}
    </group>
  );
}
