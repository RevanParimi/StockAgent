import {
  Component, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState,
} from 'react';
import { findPart, formatHash, parseHash, related, searchIndex } from './lib/select.js';
import {
  FRONT, MARGIN, codeGraph, fileLabel, galaxyLabels, galaxyLights, layoutGalaxy, ownerName, pickOf,
} from './lib/galaxy.js';
import {
  MODES, beads, clockBounds, clockRing, highlighted, moments, openingPlay, ringPoint, stepsOf,
  viewOf,
} from './lib/play.js';
import { NARROW_QUERY, flatCodeStates, flatLayout, flatStates } from './lib/flat.js';
import { layoutSubmodules, layoutWorld } from './lib/world.js';
import { PLANE, SHARED, SURFACE, moduleColour, moduleOf } from './theme.js';
import Scene from './scene/Scene.jsx';
import Panel from './ui/Panel.jsx';
import ClockPanel from './ui/ClockPanel.jsx';
import CodePanel from './ui/CodePanel.jsx';
import Player from './ui/Player.jsx';
import FlatMap from './ui/FlatMap.jsx';
import { HelpDialog, SearchDialog } from './ui/Dialogs.jsx';
import { Labels, Legend, Tooltip, TopBar } from './ui/Chrome.jsx';

const SAVED = 'stockagent-map.audience';
const readSaved = () => {
  try { return window.localStorage.getItem(SAVED); } catch { return null; }
};
const save = (value) => {
  try { window.localStorage.setItem(SAVED, value); } catch { /* a private window: not kept */ }
};

// Why the map is flat, said above it.
function flatNote({ webgl, failed, code }) {
  const same = `this is the flat map of the same model${
    code ? ', and the panels list every file' : ''}.`;
  if (!webgl) return `The 3D view needs WebGL, which this browser does not offer here: ${same}`;
  if (failed !== null) return `The 3D view failed (${failed}): ${same}`;
  return 'A narrow window: the flat map. A wider one shows the 3D view.';
}

function hasWebGL() {
  try { return Boolean(document.createElement('canvas').getContext('webgl2')); } catch { return false; }
}

/** A 3D view that fails is replaced by the flat map. */
class SceneGuard extends Component {
  constructor(props) { super(props); this.state = { failed: false }; }

  static getDerivedStateFromError() { return { failed: true }; }

  componentDidCatch(error) { this.props.onFail(String(error?.message ?? error)); }

  render() { return this.state.failed ? null : this.props.children; }
}

function useMedia(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const change = () => setMatches(media.matches);
    change();
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, [query]);
  return matches;
}

// A slider is not typing: Esc and the view keys still work while it has the focus.
const TYPING = 'input:not([type="range"]), textarea, select, [contenteditable="true"]';
const SIDE_WORD = { top: 'People see', middle: 'Decides', base: 'Runs it', stores: 'Stored' };
const STEP = Math.PI / 18;
// In the 3D view the arrows turn it and + and − zoom: the keys' way of dragging.
const NUDGES = {
  ArrowLeft: { turn: -STEP, tilt: 0, zoom: 1 },
  ArrowRight: { turn: STEP, tilt: 0, zoom: 1 },
  ArrowUp: { turn: 0, tilt: -STEP, zoom: 1 },
  ArrowDown: { turn: 0, tilt: STEP, zoom: 1 },
  '+': { turn: 0, tilt: 0, zoom: 1 / 1.15 },
  '=': { turn: 0, tilt: 0, zoom: 1 / 1.15 },
  '-': { turn: 0, tilt: 0, zoom: 1.15 },
};
// With Shift the arrows move the view sideways: the keys' way of the right-button drag.
const PANS = {
  ArrowLeft: { x: -1, y: 0 }, ArrowRight: { x: 1, y: 0 },
  ArrowUp: { x: 0, y: 1 }, ArrowDown: { x: 0, y: -1 },
};

/** Write the address of what is shown; an empty one is the page's own. */
function address(state, how) {
  const hash = formatHash(state);
  if (hash && hash === window.location.hash) return;
  window.history[how](null, '', hash || window.location.href.split('#')[0]);
}

/** On a phone the player stands before the view, elsewhere after it: the order on the
 *  screen is the order a keyboard reads. */
const inOrder = (narrow, player, view) => (narrow ? [player, view] : [view, player]);

export default function App({ model }) {
  const world = useMemo(() => layoutWorld(model), [model]);
  const index = useMemo(() => searchIndex(model), [model]);
  const day = useMemo(() => {
    const ring = clockRing(world);
    return { ring, beads: beads(ring, moments(model)), bounds: clockBounds(world, ring) };
  }, [model, world]);
  const names = useMemo(() => new Map([
    ...model.modules.map((m) => [m.id, `${m.id} ${m.short}`]),
    ...(model.externals ?? []).map((e) => [e.id, e.name]),
  ]), [model]);
  const graph = useMemo(() => codeGraph(model), [model]);
  const [first] = useState(() => parseHash(window.location.hash, model));
  // The world, or the code galaxy; in the galaxy a file may be chosen, and `selected` is
  // then the part, module or shared files that hold it.
  const [tab, setTab] = useState(first.code ? 'code' : 'world');
  const [file, setFile] = useState(first.file ?? null);
  const [selected, setSelected] = useState(first.file ? pickOf(graph, first.file) : first.id);
  const [notice, setNotice] = useState(first.unknown
    ? `Nothing on the map is called “${first.unknown}”. Choose a module from the legend.` : '');
  // the galaxy belongs to the developer view, so its address opens that view
  const [audience, setAudience] = useState(first.code ? 'developer' : first.audience
    ?? (readSaved() === 'developer' ? 'developer' : 'manager'));
  // The clock, the trace or the tour, and its step; null while the map is explored.
  const [play, setPlay] = useState(() => openingPlay(model, first, audience));
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [view, setView] = useState({ preset: 'front', focus: Boolean(first.id) && !first.code,
    turn: 0 });
  const [paused, setPaused] = useState(false);
  const reduced = useMedia('(prefers-reduced-motion: reduce)');
  const moving = !paused && !reduced;
  const narrow = useMedia(NARROW_QUERY);
  const [dialog, setDialog] = useState(null);
  const [wide, setWide] = useState(false);
  const [hover, setHover] = useState(null);
  const [pointing, setPointing] = useState(false);
  const [webgl] = useState(hasWebGL);
  // why the 3D view failed, once it has
  const [failed, setFailed] = useState(null);
  const flat = narrow || !webgl || failed !== null;
  const [nudge, setNudge] = useState(null);
  const [flatNudge, setFlatNudge] = useState(null);

  const rootRef = useRef(null);
  const labels = useRef(new Map());
  const heading = useRef(null);
  const opener = useRef(null);
  const wantsHeading = useRef(false);
  const primary = useRef(null);
  const wantsPlayer = useRef(false);
  const playOpener = useRef(null);
  const focusAfter = useRef(null);
  const inCode = tab === 'code';
  const part = inCode ? null : findPart(model, selected);
  // whether the galaxy has a panel: a file, or a choice of files
  const codePanel = inCode && Boolean(file || selected);
  // laid out when first shown, and kept: the same model always gives the same galaxy
  const placed = useRef(null);
  const galaxy = useMemo(() => {
    if (!inCode || flat) return null;
    placed.current ??= layoutGalaxy(model, world);
    return placed.current;
  }, [flat, inCode, model, world]);
  const codeLights = useMemo(() => (galaxy ? galaxyLights(graph, { selected, file }) : null),
    [file, galaxy, graph, selected]);

  const steps = useMemo(() => (play ? stepsOf(model, play.mode) : []), [model, play?.mode]);
  // what the step of the mode shows: a view, a part opened up, what is lit, a job
  const stage = useMemo(() => (play ? viewOf(model, play.mode, steps[play.step]) : null),
    [model, play, steps]);
  const shown = inCode ? null : stage ? stage.selected : selected;
  const lit = stage?.lit ?? null;

  /** Show a place of the world or, with `code`, of the galaxy. */
  const show = useCallback((id, { code = false, path = null } = {}) => {
    setTab(code ? 'code' : 'world');
    setFile(path);
    setSelected(id);
    setNotice('');
    setHover(null);
    setPointing(false);
    // Arriving from the other tab starts from the front. In the galaxy a choice moves no
    // camera; in the world it flies to what was chosen.
    if (code !== inCode) setView((v) => ({ preset: 'front', focus: !code && Boolean(id),
      turn: v.turn + 1 }));
    else if (!code) setView((v) => ({ preset: v.preset, focus: Boolean(id), turn: v.turn + 1 }));
  }, [inCode]);

  const stopPlaying = useCallback(() => {
    setPlay(null);
    setPlaying(false);
  }, []);

  /** Open a part or module in the tab that shows; in the galaxy that lights its files,
   *  and the shared files can be chosen too. */
  const open = useCallback((id, options = {}) => {
    if (!findPart(model, id) && !(inCode && id === SHARED)) return;
    if (play) opener.current = null;
    else if (!part && !codePanel) opener.current = document.activeElement;
    address({ id, audience, code: inCode }, 'pushState');
    wantsHeading.current = Boolean(options.focusPanel);
    stopPlaying();
    show(id, { code: inCode });
  }, [audience, codePanel, inCode, model, part, play, show, stopPlaying]);

  /** The code galaxy, from anywhere: a part's files lit, or one file chosen. */
  const openCode = useCallback(({ id = null, path = null, focusPanel = false } = {}) => {
    if (path && !graph.byPath.has(path)) return;
    const choice = path ? pickOf(graph, path) : id;
    if (play) opener.current = null;
    else if (!part && !codePanel) opener.current = document.activeElement;
    if (!inCode) setWide(false);
    setAudience('developer');
    address({ id: choice, file: path, audience: 'developer', code: true }, 'pushState');
    // what held the focus may be about to go: the new panel takes it, or the galaxy's button
    const held = Boolean(document.activeElement?.closest('.panel, .player'));
    wantsHeading.current = focusPanel || (held && Boolean(choice));
    if (held && !wantsHeading.current) document.querySelector('[data-galaxy]')?.focus();
    stopPlaying();
    show(choice, { code: true, path });
  }, [codePanel, graph, inCode, part, play, show, stopPlaying]);

  /** Back from the galaxy to the world, which shows the module of what was chosen. */
  const showWorld = useCallback(({ focusPanel = false, as = audience } = {}) => {
    const id = findPart(model, selected) ? selected : null;
    address({ id, audience: as }, 'pushState');
    wantsHeading.current = focusPanel && Boolean(id);
    // what held the focus is about to go: the galaxy's button takes it
    if (!wantsHeading.current && document.activeElement?.closest('.panel')) {
      document.querySelector('[data-galaxy]')?.focus();
    }
    opener.current = null;
    setWide(false);
    show(id);
  }, [audience, model, selected, show]);

  const close = useCallback(() => {
    const was = selected;
    address({ id: null, audience, code: inCode }, 'pushState');
    show(null, { code: inCode });
    setWide(false);
    const back = opener.current;
    const target = back && back.isConnected && back !== document.body
      ? back : document.querySelector(`[data-module="${moduleOf(was ?? '')}"]`);
    target?.focus?.();
    opener.current = null;
  }, [audience, inCode, selected, show]);

  /** Show a mode's step in place of whatever is open. */
  const playAt = useCallback((next) => {
    setTab('world');
    setFile(null);
    setSelected(null);
    setWide(false);
    setNotice('');
    setHover(null);
    setPointing(false);
    setPlaying(false);
    setPlay(next);
    setView((v) => ({ preset: v.preset, focus: false, turn: v.turn + 1 }));
  }, []);

  const enter = useCallback((mode, step = 0) => {
    if (!stepsOf(model, mode).length) return;
    const from = document.activeElement;
    if (!from?.closest('.player, .panel')) playOpener.current = from;
    const next = { mode, step };
    address({ play: next, audience }, 'pushState');
    wantsPlayer.current = true;
    playAt(next);
  }, [audience, model, playAt]);

  // Leaving a mode: focus moves only when it stands on something that is about to go.
  const keepFocus = useCallback((mode) => {
    if (!document.activeElement?.closest('.player, .panel')) return;
    const back = playOpener.current;
    focusAfter.current = back && back.isConnected && back !== document.body ? back
      : document.querySelector(mode === 'clock'
        ? '[data-view="clock"]' : `[data-story="${mode}"]`);
  }, []);

  const leave = useCallback((preset = 'front') => {
    if (!play) return;
    keepFocus(play.mode);
    playOpener.current = null;
    address({ id: null, audience }, 'pushState');
    stopPlaying();
    setHover(null);
    setView((v) => ({ preset, focus: false, turn: v.turn + 1 }));
  }, [audience, keepFocus, play, stopPlaying]);

  /** To a step of the mode that plays. A person's move ends autoplay; autoplay's does not. */
  const go = useCallback((step, { auto = false } = {}) => {
    if (!play) return;
    const to = Math.max(0, Math.min(stepsOf(model, play.mode).length - 1, step));
    const next = { mode: play.mode, step: to };
    address({ play: next, audience }, 'replaceState');
    if (!auto) setPlaying(false);
    setHover(null);
    setPlay(next);
  }, [audience, model, play]);

  const togglePlaying = useCallback(() => {
    if (playing) { setPlaying(false); return; }
    // Play on the last step starts again from the first.
    if (play.step === steps.length - 1) go(0);
    setPlaying(true);
  }, [go, play, playing, steps]);

  useEffect(() => {
    if (!playing || !play) return undefined;
    const timer = setTimeout(() => {
      const next = play.step + 1;
      if (next < steps.length) go(next, { auto: true });
      if (next >= steps.length - 1) setPlaying(false);
    }, MODES[play.mode].stepMs / speed);
    return () => clearTimeout(timer);
  }, [go, play, playing, speed, steps]);

  const toggleMotion = useCallback(() => {
    // pausing motion stops autoplay too
    if (!paused) setPlaying(false);
    setPaused(!paused);
  }, [paused]);

  /** The galaxy's button and key: in, with the open part's files lit, and out again. */
  const toggleCode = useCallback(() => {
    if (inCode) showWorld();
    else openCode({ id: findPart(model, selected) ? selected : null });
  }, [inCode, model, openCode, selected, showWorld]);

  const choosePreset = useCallback((preset) => {
    // the clock is the world's: it leaves the galaxy
    if (preset === 'clock') {
      if (play?.mode !== 'clock') enter('clock');
    } else if (play) leave(preset);
    else setView((v) => ({ preset, focus: false, turn: v.turn + 1 }));
  }, [enter, leave, play]);

  const changeAudience = useCallback((value) => {
    setAudience(value);
    save(value);
    // the manager view has no galaxy
    if (inCode && value === 'manager') showWorld({ as: value });
    else address({ id: selected, audience: value, play, code: inCode, file }, 'replaceState');
  }, [file, inCode, play, selected, showWorld]);

  useEffect(() => {
    // Back, Forward and hand-typed addresses. The address says what is shown, so one
    // without v=dev is the manager's view.
    const read = () => {
      const next = parseHash(window.location.hash, model);
      setAudience(next.code ? 'developer' : next.audience ?? 'manager');
      const unknown = () => {
        if (next.unknown) setNotice(`Nothing on the map is called “${next.unknown}”.`);
      };
      if (next.play) {
        unknown();
        if (next.play.mode !== play?.mode || next.play.step !== play?.step) playAt(next.play);
        return;
      }
      if (play) {
        keepFocus(play.mode);
        stopPlaying();
        setView((v) => ({ preset: 'front', focus: false, turn: v.turn + 1 }));
      }
      const path = next.file ?? null;
      const id = path ? pickOf(graph, path) : next.id;
      if (Boolean(next.code) !== inCode || id !== selected || path !== file) {
        // the galaxy's panels replace one another: focus that stood in one follows
        if ((next.code || inCode) && document.activeElement?.closest('.panel')) {
          wantsHeading.current = true;
        }
        show(id, { code: Boolean(next.code), path });
      }
      unknown();
    };
    window.addEventListener('popstate', read);
    window.addEventListener('hashchange', read);
    return () => {
      window.removeEventListener('popstate', read);
      window.removeEventListener('hashchange', read);
    };
  }, [file, graph, inCode, keepFocus, model, play, playAt, selected, show, stopPlaying]);

  useEffect(() => {
    // What the page opened with may be more than its address says (the tour a manager
    // starts on, the developer view someone kept): write it there, so the two agree.
    if (play || inCode || (audience === 'developer' && first.audience === null)) {
      address({ id: first.id, audience, play, code: inCode, file }, 'replaceState');
    }
    // only for the address the page was opened with
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // After the search dialog has closed and given focus back, move to what was chosen.
    if (!dialog && wantsHeading.current && heading.current) {
      heading.current.focus();
      wantsHeading.current = false;
    }
  }, [dialog, file, selected, tab]);

  useEffect(() => {
    // A mode someone opened takes the focus; one left gives it back.
    if (play && wantsPlayer.current && primary.current) {
      primary.current.focus();
      wantsPlayer.current = false;
    }
    if (!play && focusAfter.current) {
      focusAfter.current.focus();
      focusAfter.current = null;
    }
  }, [play]);

  useEffect(() => {
    if (play) {
      const what = play.mode === 'clock' ? `Clock, ${steps[play.step].time}`
        : `${MODES[play.mode].title}, ${play.step + 1} of ${steps.length}`;
      document.title = `${what} · StockAgent architecture`;
      return;
    }
    if (inCode) {
      const chosen = file ? fileLabel(file) : selected ? ownerName(model, selected) : null;
      document.title = `${chosen ? `${chosen} · ` : ''}Code galaxy · StockAgent architecture`;
      return;
    }
    document.title = part
      ? `${selected} ${(part.sub ?? part.module).name} · StockAgent architecture`
      : 'StockAgent architecture';
  }, [file, inCode, model, part, play, selected, steps]);

  useEffect(() => {
    const keys = (event) => {
      if (event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
      // an open dialog closes itself on Esc; asked of the page, because the dialog is shut
      // a moment before this component hears of it
      if (document.querySelector('dialog[open]')) return;
      if (event.target instanceof Element && event.target.closest(TYPING)) return;
      const inView = event.target === document.body
        || (event.target instanceof Element && Boolean(event.target.closest('.world')));
      // on the flat map + and − change its size, and the arrows scroll it as usual
      if (flat) {
        const by = { '+': 1.2, '=': 1.2, '-': 1 / 1.2 }[event.key];
        if (inView && by) {
          event.preventDefault();
          setFlatNudge({ by });
          return;
        }
      }
      if (!flat && inView && (PANS[event.key] && event.shiftKey || NUDGES[event.key])) setHover(null);
      if (!flat && inView && event.shiftKey && PANS[event.key]) {
        event.preventDefault();
        setNudge({ turn: 0, tilt: 0, zoom: 1, pan: PANS[event.key] });
        return;
      }
      if (!flat && inView && NUDGES[event.key]) {
        event.preventDefault();
        setNudge({ ...NUDGES[event.key] });
        return;
      }
      const preset = { 1: 'front', 2: 'top', 3: 'side', 4: 'below', 5: 'clock' }[event.key];
      if (preset) choosePreset(preset);
      else if (event.key === 'r' || event.key === 'R') choosePreset('front');
      else if (event.key === '/') { event.preventDefault(); setDialog('search'); }
      else if (event.key === '?') { event.preventDefault(); setDialog('help'); }
      else if ((event.key === 'p' || event.key === 'P') && !reduced && !flat) toggleMotion();
      else if ((event.key === 'g' || event.key === 'G') && audience === 'developer') toggleCode();
      else if (event.key === 'Escape' && play) leave();
      else if (event.key === 'Escape' && (selected || file)) close();
      else if (event.key === 'Escape' && inCode) showWorld();
    };
    document.addEventListener('keydown', keys);
    return () => document.removeEventListener('keydown', keys);
  }, [audience, choosePreset, close, file, flat, inCode, leave, play, reduced, selected,
    showWorld, toggleCode, toggleMotion]);

  // Nothing draws a first frame on the flat map: it is ready as soon as it is shown. A 3D
  // view that comes back is ready only once it has drawn again (Projector), so the mark
  // is taken off before that can happen.
  const wasFlat = useRef(false);
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    if (flat) {
      root.dataset.ready = 'true';
      root.dataset.moving = 'false';
    } else if (wasFlat.current) delete root.dataset.ready;
    wasFlat.current = flat;
  }, [flat]);

  // A dialog's late "closed" event must not shut the one opened since.
  const shut = useCallback((name) => setDialog((now) => (now === name ? null : now)), []);

  const touched = useMemo(() => related(model, shown), [model, shown]);
  const parts = useMemo(() => {
    if (!shown) return null;
    const moduleId = moduleOf(shown);
    const block = world.modules.find((m) => m.id === moduleId);
    const data = model.modules.find((m) => m.id === moduleId);
    return { moduleId, block, blocks: layoutSubmodules(block, data.submodules), data };
  }, [model, shown, world]);

  // The view the camera frames: the mode's, or the one the person chose.
  const preset = stage ? stage.preset : view.preset;
  const whole = stage ? !shown : !view.focus;
  const framed = !whole && shown ? shown : '';
  const goal = useMemo(() => (galaxy ? { preset, bounds: galaxy.bounds, focus: null,
    dir: preset === 'front' ? FRONT : undefined, margin: MARGIN } : {
    preset,
    bounds: preset === 'clock' ? day.bounds : world.bounds,
    focus: framed && parts ? { module: parts.block, subs: parts.blocks } : null,
  }), [day, framed, galaxy, parts, preset, world]);
  const command = `${view.turn} ${tab} ${preset} ${framed}`;
  const codeItems = useMemo(() => (galaxy ? galaxyLabels(model, galaxy, { selected, file }) : null),
    [file, galaxy, model, selected]);

  const clock = useMemo(() => {
    if (preset !== 'clock' || !stage) return null;
    const current = play.mode === 'clock' ? play.step
      : day.beads.findIndex((b) => b.job.id === stage.job?.id);
    return { ring: day.ring, beads: day.beads, current };
  }, [day, play, preset, stage]);

  const items = useMemo(() => {
    const below = preset === 'below' && whole;
    // From the side the modules stand behind one another: the planes say who is on them.
    const side = preset === 'side' && whole;
    // The clock is read from above: only what the job lights is named there.
    const onClock = preset === 'clock';
    const stateOf = (id) => (lit ? (lit.modules.has(id) ? 'lit' : 'faded')
      : !shown ? 'rest'
        : moduleOf(shown) === id ? 'selected' : touched.modules.has(id) ? 'rest' : 'faded');
    const list = [];
    for (const m of world.modules) {
      const info = model.modules.find((x) => x.id === m.id);
      const named = [...(lit?.parts ?? [])].filter((id) => moduleOf(id) === m.id).sort();
      const state = stateOf(m.id);
      const which = named.length > 2 ? `${named.length} parts` : named.join(', ');
      list.push({ key: m.id, kind: 'module', id: m.id, select: m.id,
        text: which ? `${info.short} · ${which}` : info.short,
        colour: moduleColour(m.id), state,
        priority: state === 'selected' || state === 'lit' ? 0 : 2,
        hidden: (side && state !== 'selected' && state !== 'lit')
          || (below && m.plane === 'top' && state !== 'lit')
          || (onClock && state !== 'lit'),
        pos: [m.pos[0], m.pos[1] + (below ? -1 : 1) * (m.size[1] / 2 + 0.25), m.pos[2]] });
    }
    for (const e of world.externals) {
      const isLit = lit?.externals.has(e.id);
      list.push({ key: e.id, kind: 'external', text: e.name, colour: SURFACE.ink2,
        state: lit ? (isLit ? 'lit' : 'faded')
          : shown && !touched.modules.has(e.id) ? 'faded' : 'rest',
        priority: isLit ? 1 : 3, hidden: (below || onClock) && !isLit,
        pos: [e.pos[0], e.pos[1] + 1.2, e.pos[2]] });
    }
    for (const plane of world.planes) {
      const members = world.modules.filter((m) => m.plane === plane.id)
        .map((m) => model.modules.find((x) => x.id === m.id).short);
      const holds = plane.id === 'stores' ? `${world.stores.length} stores` : members.join(', ');
      const [x, y, z] = plane.centre;
      const [w, d] = plane.size;
      list.push({ key: `plane-${plane.id}`, kind: side ? 'side' : 'plane',
        text: side ? `${SIDE_WORD[plane.id]}: ${holds}` : plane.name,
        colour: PLANE[{ top: 'planeTop', middle: 'planeMiddle', base: 'planeBase',
          stores: 'planeStores' }[plane.id]],
        state: shown || lit ? 'faded' : 'rest', priority: side ? 1 : 6,
        hidden: !whole || below || onClock
          || (preset === 'top' && (plane.id === 'base' || plane.id === 'stores')),
        // From the side the screen's left is +z: the words stand clear of the blocks.
        pos: side ? [x + w / 2, y - (plane.id === 'base' ? 1.6 : 0), z + d / 2 + 6]
          : [x - w / 2, y, z + d / 2] });
    }
    for (const s of world.stores) {
      const near = lit ? lit.stores.has(s.id) : shown ? touched.stores.has(s.id) : false;
      const target = model.stores.find((x) => x.id === s.id).writers
        .find((w) => findPart(model, w));
      list.push({ key: s.id, kind: 'store', text: s.name, select: target, colour: PLANE.planeStores,
        state: (shown || lit) && !near ? 'faded' : lit ? 'lit' : 'rest', priority: near ? 3 : 5,
        hidden: !(near || below) || side || onClock,
        pos: [s.pos[0], s.pos[1] + (below ? -0.4 : 0.5), s.pos[2]] });
    }
    if (parts) {
      for (const p of parts.blocks) {
        const info = parts.data.submodules.find((s) => s.id === p.id);
        list.push({ key: p.id, kind: 'sub', id: p.id, text: info.name, select: p.id,
          colour: moduleColour(p.id), state: shown === p.id ? 'selected' : 'rest',
          priority: shown === p.id ? 0 : 1, hidden: !whole ? false : preset !== 'front',
          pos: [p.pos[0], p.pos[1] + p.size[1] / 2 + 0.15, p.pos[2]] });
      }
    }
    if (clock) {
      for (const hour of [0, 6, 12, 18]) {
        list.push({ key: `hour-${hour}`, kind: 'hour', colour: SURFACE.edge, state: 'rest',
          text: `${String(hour).padStart(2, '0')}:00`, priority: 2, hidden: false,
          pos: ringPoint(clock.ring, hour * 60, 'daily', -3.4) });
      }
      const now = clock.beads[clock.current];
      if (now) {
        list.push({ key: 'job-now', kind: 'job', colour: moduleColour(now.job.module),
          state: 'lit', text: `${now.time} ${now.job.name}`, priority: -1, hidden: false,
          pos: [now.pos[0], now.pos[1] + 1.4, now.pos[2]] });
      }
    }
    return list;
  }, [clock, lit, model, parts, preset, shown, touched, whole, world]);

  const panelled = part || codePanel || play?.mode === 'clock';

  // On a phone what opens stands below the map: move to it. A mode someone starts moves to
  // its player, above the map; one the page opens with moves nothing.
  const opened = part ? selected : codePanel ? file ?? selected : null;
  const arrived = useRef(false);
  useEffect(() => {
    const first_ = !arrived.current;
    arrived.current = true;
    if (!narrow) return;
    const target = play ? (first_ ? null : '.player') : opened ? '.panel' : null;
    if (target) {
      document.querySelector(target)?.scrollIntoView({ block: 'start',
        behavior: reduced ? 'auto' : 'smooth' });
    }
    // only what opens moves the page, not each step of a mode
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [narrow, opened, play?.mode]);

  const flatMap = useMemo(() => (flat
    ? flatLayout(model, world, { narrow, code: inCode ? graph : null }) : null),
  [flat, graph, inCode, model, narrow, world]);
  const flatShow = useMemo(() => {
    if (!flatMap) return null;
    if (inCode) return flatCodeStates(flatMap, file ? pickOf(graph, file) : selected);
    return flatStates(model, flatMap, { shown, touched, lit, preset });
  }, [file, flatMap, graph, inCode, lit, model, preset, selected, shown, touched]);
  // the module whose parts the flat map lists under its drawing
  const flatParts = useMemo(() => {
    const id = inCode ? selected : shown;
    if (!id || id === SHARED) return null;
    const data = model.modules.find((m) => m.id === moduleOf(id));
    return data ? { moduleId: data.id, data } : null;
  }, [inCode, model, selected, shown]);
  const anchors = codeItems ?? items;
  const pick = (id, item) => (item?.file ? openCode({ path: item.file }) : open(id));
  // the bar that plays a mode: under the view, but on a phone above it, where it is seen
  const player = play ? (
    <Player key="player" ref={primary} mode={play.mode} steps={steps} step={play.step}
      lights={highlighted(model, stage)} lightsShown={flat} playing={playing}
      speed={speed} onBack={() => go(play.step - 1)} onNext={() => go(play.step + 1)}
      onPlay={togglePlaying} onSpeed={setSpeed} onSeek={go} onClose={() => leave()} />
  ) : null;
  return (
    <div className={`app${panelled ? ' with-panel' : ''}${(part || codePanel) && wide ? ' wide' : ''}${
      play ? ' playing' : ''}`} ref={rootRef}
      data-app data-selected={selected ?? ''} data-preset={preset} data-audience={audience}
      data-tab={tab} data-file={file ?? ''} data-view-kind={flat ? 'flat' : '3d'}
      data-motion={moving ? 'on' : 'off'} data-mode={play?.mode ?? ''}
      data-step={play ? play.step + 1 : ''} data-job={stage?.job?.id ?? ''}
      data-playing={playing ? 'true' : 'false'}>
      <a className="skip" href="#modules"
        onClick={(e) => {
          // moving there by the address would read as "close what is open"
          e.preventDefault();
          document.querySelector('#modules [data-module]')?.focus();
        }}>Skip to the list of modules</a>
      <TopBar model={model} preset={play ? (play.mode === 'clock' ? 'clock' : null)
        : view.focus ? null : view.preset}
        mode={play?.mode} code={inCode} audience={audience} motion={moving}
        reduced={reduced} flat={flat} onPreset={choosePreset}
        onReset={() => choosePreset('front')}
        onStory={(mode) => (play?.mode === mode ? leave() : enter(mode))} onCode={toggleCode}
        onSearch={() => setDialog('search')} onAudience={changeAudience}
        onMotion={toggleMotion} onHelp={() => setDialog('help')} />
      <Legend model={model} selected={inCode ? selected : shown} audience={audience} code={inCode}
        flat={flat} onSelect={(id) => open(id)} />
      {inOrder(narrow, player, (
        <main key="view" className={`world${pointing && !flat ? ' pointing' : ''}${flat ? ' flat-world' : ''}`}
          tabIndex={flat ? undefined : 0}
          aria-label={flat ? 'Flat map. Tab to a card and press Enter to open it; plus and minus change its size.'
            : inCode
              ? 'Code galaxy: a 3D view of the Python files. Arrow keys turn it; plus and minus zoom. The panels list every file.'
              : '3D view of the product. Arrow keys turn it; plus and minus zoom.'}>
          {flat ? (
            <FlatMap model={model} layout={flatMap} states={flatShow} preset={preset}
              audience={audience} code={inCode} parts={flatParts}
              open={inCode ? selected : shown} note={flatNote({ webgl, failed, code: inCode })}
              noteRole={!webgl || failed !== null ? 'alert' : 'status'} nudge={flatNudge}
              onSelect={(id) => open(id)} />
          ) : (
            <>
              <SceneGuard onFail={setFailed}>
                <Scene world={world} goal={goal} command={command} nudge={nudge} selected={shown}
                  touched={touched} lit={lit} clock={clock} parts={parts} anchors={anchors}
                  labels={labels} rootRef={rootRef} reduced={reduced} moving={moving}
                  preset={whole ? preset : null} hovered={hover?.flow?.key}
                  onSelect={(id) => open(id)}
                  onMoment={(i) => (play?.mode === 'clock' ? go(i) : enter('clock', i))}
                  onHoverFlow={setHover} onHoverBlock={setPointing} galaxy={galaxy}
                  codeLights={codeLights} hoveredFile={hover?.path ?? null}
                  onPickFile={(path) => openCode({ path })}
                  onHoverFile={(over) => { setHover(over); setPointing(Boolean(over)); }} />
              </SceneGuard>
              <Labels items={anchors.filter((i) => !i.hidden)} labels={labels} onSelect={pick} />
              {galaxy ? (
                <p className="ring-key code-key">
                  {galaxy.nodes.length} Python files. A dot is a file: its size, its lines; its colour,
                  its module. A line is an import. {file
                    ? <><strong>Solid</strong> lines: files it imports. <strong>Dashed</strong>: files
                      that import it.</>
                    : 'A ring: six or more other modules import the file.'}
                </p>
              ) : null}
              {clock ? (
                <p className="ring-key">Rings, inner to outer: <strong>daily</strong>,{' '}
                  <strong>weekly</strong>, <strong>monthly and yearly</strong>. 00:00 is at the back.</p>
              ) : null}
            </>
          )}
          {notice ? <p className="notice" role="status">{notice}</p> : null}
        </main>
      ))}
      {part ? (
        <Panel ref={heading} model={model} part={part} audience={audience} wide={wide}
          onWide={() => setWide((w) => !w)} onClose={close} onSelect={(id) => open(id)}
          onCode={(id) => openCode({ id, focusPanel: true })}
          onFile={(path) => openCode({ path, focusPanel: true })} />
      ) : codePanel ? (
        <CodePanel ref={heading} model={model} graph={graph} file={file} selected={selected}
          wide={wide} onWide={() => setWide((w) => !w)} onClose={close}
          onFile={(path) => openCode({ path, focusPanel: true })}
          onCode={(id) => openCode({ id, focusPanel: true })}
          onWorld={() => showWorld({ focusPanel: true })} />
      ) : play?.mode === 'clock' ? (
        <ClockPanel model={model} moments={steps} step={play.step}
          names={names} audience={audience} onOpen={(id) => open(id, { focusPanel: true })}
          onMoment={go} onClose={() => leave()} />
      ) : null}
      {flat ? null : <Tooltip hover={hover} names={names} model={model} />}
      <SearchDialog open={dialog === 'search'} index={index} onClose={() => shut('search')}
        onPick={(item) => {
          shut('search');
          // A file opens in the galaxy when that shows, when no part of the world holds it,
          // or when a developer picks one that no panel of the world lists (a module's own).
          if (item.file && (inCode || !findPart(model, item.id)
              || (audience === 'developer' && item.kind === 'file' && !item.id.includes('.')))) {
            openCode({ path: item.file, focusPanel: true });
          } else open(item.id, { focusPanel: true });
        }} />
      <HelpDialog open={dialog === 'help'} onClose={() => shut('help')} />
    </div>
  );
}
