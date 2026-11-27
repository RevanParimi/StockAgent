// The map's colours and limits. docs/architecture-map/DESIGN.md states the same values;
// tests/frontend/architecture_map_logic.test.mjs fails when the two disagree.

export const SURFACE = {
  bg: '#0b1020',
  panel: '#121a2e',
  raised: '#1b2540',
  node: '#18213a',
  line: '#33415f',
  edge: '#8f9bba',
  ink: '#e9eefb',
  ink2: '#b4bfd9',
  muted: '#8f9bba',
  link: '#8ecbff',
  focus: '#ffd166',
  yes: '#7ee2a8',
};

export const PLANE = {
  planeTop: '#7d6cf0',
  planeMiddle: '#3a7bd5',
  planeBase: '#6b7690',
  planeStores: '#b4832f',
  planeRing: '#8a99b3',
};

export const MODULE = {
  M1: '#53b029',
  M2: '#5e7dfa',
  M3: '#1ab2a6',
  M4: '#236fd8',
  M5: '#c43d73',
  M6: '#667900',
  M7: '#cc8c45',
  M8: '#a985e5',
  M9: '#96a022',
  M10: '#c66167',
  M11: '#935ede',
  M12: '#ad620e',
};

export const moduleOf = (id) => String(id).split('.')[0];
// Who a flow or a store names: an outside party by its own id, else the module.
export const nodeOf = (who) => (String(who).startsWith('ext.') ? String(who) : moduleOf(who));
export const moduleColour = (id) => MODULE[moduleOf(id)] ?? PLANE.planeMiddle;

export const BLOOM = { intensity: 0.7, threshold: 0.55 };
export const MOTION = { flightMs: 700, secondsPerFlow: 4.5, particlesPerFlow: 3 };
export const OPACITY = { faded: 0.12, fadedFlow: 0.08 };
