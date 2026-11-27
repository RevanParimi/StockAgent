import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useThree } from '@react-three/fiber';
import { Billboard, Line } from '@react-three/drei';
import {
  AdditiveBlending, BufferAttribute, BufferGeometry, Color, DoubleSide, Object3D, Vector3,
} from 'three';
import { OPACITY, SURFACE } from '../theme.js';
import { clusterColour, dotAt, dotState, edgeState } from '../lib/galaxy.js';

// How strongly an import's line shows: lines add their light, so a faint one all but
// disappears. A chosen file's own lines are drawn apart (OwnLines).
const STRENGTH = { near: 0.34, far: 0.055, inside: 0.8, bridge: 0.3, own: 0, faded: 0.008 };

const BACKGROUND = new Color(SURFACE.bg);
const WHITE = new Color('#ffffff');

/** A dot's colour: full at rest, towards white and past it when lit (so the bloom picks it
 *  out), mixed into the background when the choice has nothing to do with it. */
function shade(cluster, state) {
  const colour = new Color(clusterColour(cluster));
  if (state === 'faded') return BACKGROUND.clone().lerp(colour, OPACITY.faded);
  if (state === 'rest') return colour;
  return colour.lerp(WHITE, 0.15).multiplyScalar(1.35);
}

/** One instance for each file: a single draw, however many files there are. */
function Dots({ galaxy, lights, rootRef }) {
  const mesh = useRef(null);
  const invalidate = useThree((s) => s.invalidate);
  useLayoutEffect(() => {
    const dots = mesh.current;
    const at = new Object3D();
    let shown = 0;
    galaxy.nodes.forEach((node, i) => {
      const state = dotState(lights, node.path);
      at.position.set(...node.pos);
      at.scale.setScalar(node.radius);
      at.updateMatrix();
      dots.setMatrixAt(i, at.matrix);
      dots.setColorAt(i, shade(node.cluster, state));
      if (state === 'lit' || state === 'chosen') shown += 1;
    });
    dots.instanceMatrix.needsUpdate = true;
    dots.instanceColor.needsUpdate = true;
    const root = rootRef.current;
    // what is drawn, for the tests: the number of dots and of lit ones
    if (root) {
      root.dataset.dots = String(dots.count);
      root.dataset.lit = String(shown);
    }
    invalidate();
    return () => {
      if (root) {
        delete root.dataset.dots;
        delete root.dataset.lit;
      }
    };
  }, [galaxy, invalidate, lights, rootRef]);
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, galaxy.nodes.length]}
      frustumCulled={false} raycast={() => null}>
      <sphereGeometry args={[1, 20, 14]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

function Imports({ galaxy, lights }) {
  const invalidate = useThree((s) => s.invalidate);
  const geometry = useMemo(() => {
    const out = new BufferGeometry();
    const places = new Float32Array(galaxy.graph.edges.length * 6);
    galaxy.graph.edges.forEach((edge, i) => {
      places.set(galaxy.byPath.get(edge.from).pos, i * 6);
      places.set(galaxy.byPath.get(edge.to).pos, i * 6 + 3);
    });
    out.setAttribute('position', new BufferAttribute(places, 3));
    out.setAttribute('color',
      new BufferAttribute(new Float32Array(galaxy.graph.edges.length * 6), 3));
    return out;
  }, [galaxy]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useLayoutEffect(() => {
    const colours = geometry.getAttribute('color');
    galaxy.graph.edges.forEach((edge, i) => {
      const strength = STRENGTH[edgeState(galaxy.graph, lights, edge)];
      [edge.from, edge.to].forEach((path, end) => {
        const c = new Color(clusterColour(galaxy.byPath.get(path).cluster))
          .multiplyScalar(strength);
        colours.setXYZ(i * 2 + end, c.r, c.g, c.b);
      });
    });
    colours.needsUpdate = true;
    invalidate();
  }, [galaxy, geometry, invalidate, lights]);
  return (
    <lineSegments geometry={geometry} frustumCulled={false} raycast={() => null}>
      <lineBasicMaterial vertexColors transparent blending={AdditiveBlending} depthWrite={false}
        toneMapped={false} />
    </lineSegments>
  );
}

/** A chosen file's own lines: solid to what it imports, dashed from what imports it. */
function OwnLines({ galaxy, file }) {
  const [out, into] = useMemo(() => {
    const record = galaxy.graph.byPath.get(file);
    const at = (path) => galaxy.byPath.get(path).pos;
    return [record.imports.flatMap((to) => [at(file), at(to)]),
      record.importedBy.flatMap((from) => [at(from), at(file)])];
  }, [file, galaxy]);
  return (
    <>
      {out.length ? (
        <Line key={`out:${file}`} segments points={out} color={SURFACE.ink} lineWidth={1.5}
          transparent opacity={0.9} raycast={() => null} />
      ) : null}
      {into.length ? (
        <Line key={`into:${file}`} segments points={into} color={SURFACE.link} lineWidth={1.5}
          dashed dashSize={0.7} gapSize={0.5} transparent opacity={0.9} raycast={() => null} />
      ) : null}
    </>
  );
}

/** A ring facing the viewer, around a dot. `above` draws it over every dot, so the chosen
 *  file is found even behind others. */
function Ring({ node, colour, gap, width, above = false }) {
  const inner = node.radius + gap;
  return (
    <Billboard position={node.pos}>
      <mesh raycast={() => null} renderOrder={above ? 10 : 0}>
        <ringGeometry args={[inner, inner + width, 48]} />
        <meshBasicMaterial color={colour} side={DoubleSide} toneMapped={false}
          transparent={above} depthTest={!above} depthWrite={!above} />
      </mesh>
    </Billboard>
  );
}

/** Pointing at a dot and clicking it, measured on the screen, so that a small dot is as
 *  easy to point at as the checklist asks and a drag that turns the view chooses nothing. */
function Picker({ galaxy, hovered, onPick, onHover }) {
  const camera = useThree((s) => s.camera);
  const gl = useThree((s) => s.gl);
  const latest = useRef(null);
  latest.current = { galaxy, hovered, onPick, onHover };
  useEffect(() => {
    const canvas = gl.domElement;
    const point = new Vector3();
    // where the button went down, and whether the pointer has left that spot since
    let down = null;
    let dragged = false;
    const away = (event) => Math.hypot(event.clientX - down[0], event.clientY - down[1]) >= 6;
    const find = (event) => {
      const box = canvas.getBoundingClientRect();
      const tan = Math.tan((camera.fov * Math.PI) / 360);
      camera.updateMatrixWorld();
      const dots = [];
      for (const node of latest.current.galaxy.nodes) {
        point.set(...node.pos).applyMatrix4(camera.matrixWorldInverse);
        const depth = -point.z;
        if (depth <= camera.near) continue;
        point.applyMatrix4(camera.projectionMatrix);
        dots.push({
          path: node.path, depth, radius: (node.radius / (depth * tan)) * (box.height / 2),
          x: ((point.x + 1) / 2) * box.width, y: ((1 - point.y) / 2) * box.height,
        });
      }
      return dotAt(dots, event.clientX - box.left, event.clientY - box.top)?.path ?? null;
    };
    /** Says what is pointed at, when that changes. */
    const tell = (path, event) => {
      if (path === latest.current.hovered) return;
      latest.current.onHover(path ? { path, x: event.clientX, y: event.clientY } : null);
    };
    const move = (event) => {
      if (down && away(event)) dragged = true;
      if (!event.buttons) tell(find(event), event);
    };
    const leave = (event) => tell(null, event);
    const pressed = (event) => {
      // a drag turns the view, and the name would stay behind
      tell(null, event);
      down = event.button === 0 ? [event.clientX, event.clientY] : null;
      dragged = false;
    };
    const released = (event) => {
      if (!down || event.button !== 0) return;
      // a drag turns the view, also one that ends where it began
      const drag = dragged || away(event);
      down = null;
      if (drag) return;
      const path = find(event);
      if (path) latest.current.onPick(path);
    };
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerleave', leave);
    canvas.addEventListener('pointerdown', pressed);
    canvas.addEventListener('pointerup', released);
    return () => {
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerleave', leave);
      canvas.removeEventListener('pointerdown', pressed);
      canvas.removeEventListener('pointerup', released);
    };
  }, [camera, gl]);
  return null;
}

export default function Galaxy({ galaxy, lights, rootRef, hovered, onPick, onHover }) {
  const chosen = lights?.file ? galaxy.byPath.get(lights.file) : null;
  return (
    <group>
      <Imports galaxy={galaxy} lights={lights} />
      <Dots galaxy={galaxy} lights={lights} rootRef={rootRef} />
      {galaxy.bridges.filter((path) => path !== lights?.file
        && (!lights || lights.files.has(path))).map((path) => (
          <Ring key={path} node={galaxy.byPath.get(path)} colour={SURFACE.ink2} gap={0.22}
            width={0.09} />
      ))}
      {chosen ? (
        <>
          <OwnLines galaxy={galaxy} file={chosen.path} />
          <Ring key={chosen.path} node={chosen} colour={SURFACE.focus} gap={0.3} width={0.3}
            above />
        </>
      ) : null}
      <Picker galaxy={galaxy} hovered={hovered} onPick={onPick} onHover={onHover} />
    </group>
  );
}
