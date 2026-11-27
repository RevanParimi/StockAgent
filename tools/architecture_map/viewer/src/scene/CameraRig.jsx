import { useEffect, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { Spherical, Vector3 } from 'three';
import { PRESETS, fitCamera, focusCamera } from '../lib/world.js';
import { MOTION } from '../theme.js';

const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - ((-2 * t + 2) ** 3) / 2);

/**
 * The camera. `command` says what to frame: a preset view of the whole world, or one
 * module and its parts. A drag stops a flight and leaves the view where the person put
 * it; `reduced` makes every move a jump.
 */
export default function CameraRig({ command, goal, nudge, reduced, rootRef }) {
  const camera = useThree((s) => s.camera);
  const size = useThree((s) => s.size);
  const invalidate = useThree((s) => s.invalidate);
  const controls = useRef(null);
  const flight = useRef(null);
  const moved = useRef(false);
  const started = useRef(false);

  const frame = () => {
    const aspect = size.width / Math.max(1, size.height);
    if (goal.focus) return focusCamera(goal.focus.module, goal.focus.subs, aspect);
    const { dir, fov } = PRESETS[goal.preset];
    return { ...fitCamera(goal.bounds, dir, fov, aspect), fov };
  };

  const lens = (fov) => {
    camera.fov = fov;
    camera.updateProjectionMatrix();
  };

  const go = (to, fly) => {
    const orbit = controls.current;
    if (!orbit) return;
    const end = { position: new Vector3(...to.position), target: new Vector3(...to.target),
      fov: to.fov };
    if (fly) {
      flight.current = {
        from: { position: camera.position.clone(), target: orbit.target.clone(), fov: camera.fov },
        to: end,
        elapsed: 0,
      };
      if (rootRef.current) rootRef.current.dataset.moving = 'true';
    } else {
      flight.current = null;
      lens(end.fov);
      camera.position.copy(end.position);
      orbit.target.copy(end.target);
      orbit.update();
    }
    invalidate();
  };

  useEffect(() => {
    moved.current = false;
    go(frame(), started.current && !reduced);
    started.current = true;
    // a new command is the only reason to move; `goal` changes with it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command]);

  useEffect(() => {
    // The window changed shape (the panel opening narrows it): frame the same thing
    // again, unless the person moved. A flight under way is sent to the new place.
    if (!moved.current) go(frame(), Boolean(flight.current));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.width, size.height]);

  // The keys' way of dragging: turn round the target, move nearer and further, or slide
  // the view sideways.
  useEffect(() => {
    const orbit = controls.current;
    if (!nudge || !orbit) return;
    flight.current = null;
    moved.current = true;
    const around = new Spherical().setFromVector3(camera.position.clone().sub(orbit.target));
    around.theta += nudge.turn;
    around.phi = Math.min(Math.PI - 0.02, Math.max(0.02, around.phi + nudge.tilt));
    around.radius = Math.min(600, Math.max(8, around.radius * nudge.zoom));
    camera.position.setFromSpherical(around).add(orbit.target);
    if (nudge.pan) {
      camera.updateMatrixWorld();
      const slide = new Vector3()
        .addScaledVector(new Vector3().setFromMatrixColumn(camera.matrixWorld, 0), nudge.pan.x)
        .addScaledVector(new Vector3().setFromMatrixColumn(camera.matrixWorld, 1), nudge.pan.y)
        .multiplyScalar(around.radius * 0.05);
      camera.position.add(slide);
      orbit.target.add(slide);
    }
    orbit.update();
    invalidate();
  }, [camera, invalidate, nudge]);

  useFrame((_, delta) => {
    const active = flight.current;
    const orbit = controls.current;
    if (active && orbit) {
      // a frame counts for at most 100 ms, so even a slow machine sees the way there
      active.elapsed += Math.min(delta * 1000, 100);
      const t = Math.min(1, active.elapsed / MOTION.flightMs);
      if (t >= 1) {
        camera.position.copy(active.to.position);
        orbit.target.copy(active.to.target);
        lens(active.to.fov);
        flight.current = null;
      } else {
        const k = ease(t);
        camera.position.lerpVectors(active.from.position, active.to.position, k);
        orbit.target.lerpVectors(active.from.target, active.to.target, k);
        lens(active.from.fov + (active.to.fov - active.from.fov) * k);
      }
      orbit.update();
      invalidate();
    }
    const root = rootRef.current;
    if (root) {
      const at = camera.position.toArray().map((v) => v.toFixed(1)).join(',');
      if (root.dataset.camera !== at) root.dataset.camera = at;
      const moving = flight.current ? 'true' : 'false';
      const wide = camera.fov.toFixed(0);
      if (root.dataset.fov !== wide) root.dataset.fov = wide;
      if (root.dataset.moving !== moving) root.dataset.moving = moving;
    }
  }, -2);

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping={false}
      minPolarAngle={0.02}
      maxPolarAngle={Math.PI - 0.02}
      minDistance={8}
      maxDistance={600}
      onStart={() => { moved.current = true; flight.current = null; }}
    />
  );
}
