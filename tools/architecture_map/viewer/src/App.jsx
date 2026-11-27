import { Component, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { findPart, formatHash, parseHash, related, searchIndex } from './lib/select.js';
import {
  MODES, beads, clockBounds, clockRing, highlighted, moments, openingPlay, ringPoint, stepsOf,
  viewOf,
} from './lib/play.js';
import { layoutSubmodules, layoutWorld } from './lib/world.js';
import { PLANE, SURFACE, moduleColour, moduleOf } from './theme.js';
import Scene from './scene/Scene.jsx';
import Panel from './ui/Panel.jsx';
import ClockPanel from './ui/ClockPanel.jsx';
import Player from './ui/Player.jsx';
import { HelpDialog, SearchDialog } from './ui/Dialogs.jsx';
import { Labels, Legend, Tooltip, TopBar } from './ui/Chrome.jsx';

const SAVED = 'stockagent-map.audience';
const readSaved = () => {
  try { return window.localStorage.getItem(SAVED); } catch { return null; }
};
const save = (value) => {
  try { window.localStorage.setItem(SAVED, value); } catch { /* a private window: not kept */ }
};

const NO_VIEW = 'The 3D view needs WebGL, which this browser does not offer here. The legend, search '
  + 'and the panel still show every module.';

function hasWebGL() {
  try { return Boolean(document.createElement('canvas').getContext('webgl2')); } catch { return false; }
}

class SceneGuard extends Component {
  constructor(props) { super(props); this.state = { error: null }; }

  static getDerivedStateFromError(error) { return { error }; }

  render() {
    return this.state.error
      ? <p className="no-view" role="alert">{NO_VIEW} ({String(this.state.error.message)})</p>
      : this.props.children;
  }
}

function useReducedMotion() {
  const query = '(prefers-reduced-motion: reduce)';
  const [reduced, setReduced] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const change = () => setReduced(media.matches);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  return reduced;
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
  const [first] = useState(() => parseHash(window.location.hash, model));
  const [selected, setSelected] = useState(first.id);
  const [notice, setNotice] = useState(first.unknown
    ? `Nothing on the map is called “${first.unknown}”. Choose a module from the legend.` : '');
  const [audience, setAudience] = useState(first.audience
    ?? (readSaved() === 'developer' ? 'developer' : 'manager'));
  // The clock, the trace or the tour, and its step; null while the map is explored.
  const [play, setPlay] = useState(() => openingPlay(model, first, audience));
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [view, setView] = useState({ preset: 'front', focus: Boolean(first.id), turn: 0 });
  const [paused, setPaused] = useState(false);
  const reduced = useReducedMotion();
  const moving = !paused && !reduced;
  const [dialog, setDialog] = useState(null);
  const [wide, setWide] = useState(false);
  const [hover, setHover] = useState(null);
  const [pointing, setPointing] = useState(false);
  const [webgl] = useState(hasWebGL);
  const [nudge, setNudge] = useState(null);

  const rootRef = useRef(null);
  const labels = useRef(new Map());
  const heading = useRef(null);
  const opener = useRef(null);
  const wantsHeading = useRef(false);
  const primary = useRef(null);
  const wantsPlayer = useRef(false);
  const playOpener = useRef(null);
  const focusAfter = useRef(null);
  const part = findPart(model, selected);

  const steps = useMemo(() => (play ? stepsOf(model, play.mode) : []), [model, play?.mode]);
  // what the step of the mode shows: a view, a part opened up, what is lit, a job
  const stage = useMemo(() => (play ? viewOf(model, play.mode, steps[play.step]) : null),
    [model, play, steps]);
  const shown = stage ? stage.selected : selected;
  const lit = stage?.lit ?? null;

  const show = useCallback((id) => {
    setSelected(id);
    setNotice('');
    setHover(null);
    setPointing(false);
    setView((v) => ({ preset: v.preset, focus: Boolean(id), turn: v.turn + 1 }));
  }, []);

  const stopPlaying = useCallback(() => {
    setPlay(null);
    setPlaying(false);
  }, []);

  const open = useCallback((id, options = {}) => {
    if (!findPart(model, id)) return;
    if (play) opener.current = null;
    else if (!part) opener.current = document.activeElement;
    address({ id, audience }, 'pushState');
    wantsHeading.current = Boolean(options.focusPanel);
    stopPlaying();
    show(id);
  }, [audience, model, part, play, show, stopPlaying]);

  const close = useCallback(() => {
    const was = selected;
    address({ id: null, audience }, 'pushState');
    show(null);
    setWide(false);
    const back = opener.current;
    const target = back && back.isConnected && back !== document.body
      ? back : document.querySelector(`[data-module="${moduleOf(was ?? '')}"]`);
    target?.focus?.();
    opener.current = null;
  }, [audience, selected, show]);

  /** Show a mode's step in place of whatever is open. */
  const playAt = useCallback((next) => {
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

  const choosePreset = useCallback((preset) => {
    if (preset === 'clock') {
      if (play?.mode !== 'clock') enter('clock');
    } else if (play) leave(preset);
    else setView((v) => ({ preset, focus: false, turn: v.turn + 1 }));
  }, [enter, leave, play]);

  const changeAudience = useCallback((value) => {
    setAudience(value);
    save(value);
    address({ id: selected, audience: value, play }, 'replaceState');
  }, [play, selected]);

  useEffect(() => {
    // Back, Forward and hand-typed addresses. The address says what is shown, so one
    // without v=dev is the manager's view.
    const read = () => {
      const next = parseHash(window.location.hash, model);
      setAudience(next.audience ?? 'manager');
      if (next.unknown) setNotice(`Nothing on the map is called “${next.unknown}”.`);
      if (next.play) {
        if (next.play.mode !== play?.mode || next.play.step !== play?.step) playAt(next.play);
        return;
      }
      if (play) {
        keepFocus(play.mode);
        stopPlaying();
        setView((v) => ({ preset: 'front', focus: false, turn: v.turn + 1 }));
      }
      if (next.id !== selected) show(next.id);
    };
    window.addEventListener('popstate', read);
    window.addEventListener('hashchange', read);
    return () => {
      window.removeEventListener('popstate', read);
      window.removeEventListener('hashchange', read);
    };
  }, [keepFocus, model, play, playAt, selected, show, stopPlaying]);

  useEffect(() => {
    // What the page opened with may be more than its address says (the tour a manager
    // starts on, the developer view someone kept): write it there, so the two agree.
    if (play || (audience === 'developer' && first.audience === null)) {
      address({ id: first.id, audience, play }, 'replaceState');
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
  }, [dialog, selected]);

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
    document.title = part
      ? `${selected} ${(part.sub ?? part.module).name} · StockAgent architecture`
      : 'StockAgent architecture';
  }, [part, play, selected, steps]);

  useEffect(() => {
    const keys = (event) => {
      if (event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
      // an open dialog closes itself on Esc; asked of the page, because the dialog is shut
      // a moment before this component hears of it
      if (document.querySelector('dialog[open]')) return;
      if (event.target instanceof Element && event.target.closest(TYPING)) return;
      const inView = event.target === document.body
        || (event.target instanceof Element && Boolean(event.target.closest('.world')));
      if (inView && event.shiftKey && PANS[event.key]) {
        event.preventDefault();
        setNudge({ turn: 0, tilt: 0, zoom: 1, pan: PANS[event.key] });
        return;
      }
      if (inView && NUDGES[event.key]) {
        event.preventDefault();
        setNudge({ ...NUDGES[event.key] });
        return;
      }
      const preset = { 1: 'front', 2: 'top', 3: 'side', 4: 'below', 5: 'clock' }[event.key];
      if (preset) choosePreset(preset);
      else if (event.key === 'r' || event.key === 'R') choosePreset('front');
      else if (event.key === '/') { event.preventDefault(); setDialog('search'); }
      else if (event.key === '?') { event.preventDefault(); setDialog('help'); }
      else if ((event.key === 'p' || event.key === 'P') && !reduced) toggleMotion();
      else if (event.key === 'Escape' && play) leave();
      else if (event.key === 'Escape' && selected) close();
    };
    document.addEventListener('keydown', keys);
    return () => document.removeEventListener('keydown', keys);
  }, [choosePreset, close, leave, play, reduced, selected, toggleMotion]);

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
  const goal = useMemo(() => ({
    preset,
    bounds: preset === 'clock' ? day.bounds : world.bounds,
    focus: framed && parts ? { module: parts.block, subs: parts.blocks } : null,
  }), [day, framed, parts, preset, world]);
  const command = `${view.turn} ${preset} ${framed}`;

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

  const panelled = part || play?.mode === 'clock';
  return (
    <div className={`app${panelled ? ' with-panel' : ''}${part && wide ? ' wide' : ''}${
      play ? ' playing' : ''}`} ref={rootRef}
      data-app data-selected={selected ?? ''} data-preset={preset} data-audience={audience}
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
        mode={play?.mode} audience={audience} motion={moving}
        reduced={reduced} onPreset={choosePreset} onReset={() => choosePreset('front')}
        onStory={(mode) => (play?.mode === mode ? leave() : enter(mode))}
        onSearch={() => setDialog('search')} onAudience={changeAudience}
        onMotion={toggleMotion} onHelp={() => setDialog('help')} />
      <Legend model={model} selected={shown} audience={audience} onSelect={(id) => open(id)} />
      <main className={`world${pointing ? ' pointing' : ''}`} tabIndex={0}
        aria-label="3D view of the product. Arrow keys turn it; plus and minus zoom.">
        {webgl ? (
          <SceneGuard>
            <Scene world={world} goal={goal} command={command} nudge={nudge} selected={shown}
              touched={touched} lit={lit} clock={clock} parts={parts} anchors={items}
              labels={labels} rootRef={rootRef} reduced={reduced} moving={moving}
              preset={whole ? preset : null} hovered={hover?.flow.key}
              onSelect={(id) => open(id)}
              onMoment={(i) => (play?.mode === 'clock' ? go(i) : enter('clock', i))}
              onHoverFlow={setHover} onHoverBlock={setPointing} />
          </SceneGuard>
        ) : <p className="no-view" role="alert">{NO_VIEW}</p>}
        <Labels items={items.filter((i) => !i.hidden)} labels={labels}
          onSelect={(id) => open(id)} />
        {clock && webgl ? (
          <p className="ring-key">Rings, inner to outer: <strong>daily</strong>,{' '}
            <strong>weekly</strong>, <strong>monthly and yearly</strong>. 00:00 is at the back.</p>
        ) : null}
        {notice ? <p className="notice" role="status">{notice}</p> : null}
      </main>
      {play ? (
        <Player ref={primary} mode={play.mode} steps={steps} step={play.step}
          lights={highlighted(model, stage)} lightsShown={!webgl} playing={playing}
          speed={speed} onBack={() => go(play.step - 1)} onNext={() => go(play.step + 1)}
          onPlay={togglePlaying} onSpeed={setSpeed} onSeek={go} onClose={() => leave()} />
      ) : null}
      {part ? (
        <Panel ref={heading} model={model} part={part} audience={audience} wide={wide}
          onWide={() => setWide((w) => !w)} onClose={close} onSelect={(id) => open(id)} />
      ) : play?.mode === 'clock' ? (
        <ClockPanel model={model} moments={steps} step={play.step}
          names={names} audience={audience} onOpen={(id) => open(id, { focusPanel: true })}
          onMoment={go} onClose={() => leave()} />
      ) : null}
      <Tooltip hover={hover} names={names} />
      <SearchDialog open={dialog === 'search'} index={index} onClose={() => shut('search')}
        onPick={(item) => { shut('search'); open(item.id, { focusPanel: true }); }} />
      <HelpDialog open={dialog === 'help'} onClose={() => shut('help')} />
    </div>
  );
}
