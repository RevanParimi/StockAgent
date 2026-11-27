import { Canvas } from '@react-three/fiber';
import { Bloom, EffectComposer } from '@react-three/postprocessing';
import { BLOOM, SURFACE } from '../theme.js';
import { Externals, Modules, Parts, Planes, Stores } from './Blocks.jsx';
import { Flows, Pipes } from './Flows.jsx';
import CameraRig from './CameraRig.jsx';
import Projector from './Projector.jsx';

const NOTHING = { modules: new Set(), stores: new Set(), flows: new Set() };

export default function Scene({
  world, goal, command, nudge, selected, touched, parts, anchors, labels, rootRef, reduced, moving,
  preset, hovered, onSelect, onHoverFlow, onHoverBlock,
}) {
  const related = touched ?? NOTHING;
  const module = parts ? world.modules.find((m) => m.id === parts.moduleId) : null;
  return (
    <Canvas
      camera={{ fov: 40, near: 0.5, far: 1500, position: [0, 20, 90] }}
      dpr={[1, 1.75]}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      frameloop={moving ? 'always' : 'demand'}
      aria-hidden="true"
    >
      <color attach="background" args={[SURFACE.bg]} />
      <ambientLight intensity={0.85} />
      <directionalLight position={[18, 30, 24]} intensity={1.3} />
      <Planes planes={world.planes} ring={world.ring} />
      <Modules modules={world.modules} selected={selected} touched={related} preset={preset}
        onSelect={onSelect} onHover={onHoverBlock} />
      {module ? (
        <Parts parts={parts.blocks} moduleId={parts.moduleId} moduleBlock={module}
          selected={selected} onSelect={onSelect} onHover={onHoverBlock} />
      ) : null}
      <Stores stores={world.stores} selected={selected} touched={related} preset={preset} />
      <Externals externals={world.externals} selected={selected} touched={related}
        preset={preset} />
      <Flows flows={world.flows} selected={selected} touched={related} hovered={hovered}
        moving={moving} preset={preset} onHover={onHoverFlow} />
      <Pipes pipes={world.pipes} selected={selected} touched={related} preset={preset} />
      <CameraRig command={command} goal={goal} nudge={nudge} reduced={reduced} rootRef={rootRef} />
      <Projector anchors={anchors} labels={labels} rootRef={rootRef} />
      <EffectComposer multisampling={4}>
        <Bloom intensity={BLOOM.intensity} luminanceThreshold={BLOOM.threshold}
          luminanceSmoothing={0.2} mipmapBlur />
      </EffectComposer>
    </Canvas>
  );
}
