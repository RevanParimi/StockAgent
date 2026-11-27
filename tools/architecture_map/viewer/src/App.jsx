import { Component, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { findPart, formatHash, parseHash, related, searchIndex } from './lib/select.js';
import { layoutSubmodules, layoutWorld } from './lib/world.js';
import { PLANE, SURFACE, moduleColour, moduleOf } from './theme.js';
import Scene from './scene/Scene.jsx';
import Panel from './ui/Panel.jsx';
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

const TYPING = 'input, textarea, select, [contenteditable="true"]';
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

export default function App({ model }) {
  const world = useMemo(() => layoutWorld(model), [model]);
  const index = useMemo(() => searchIndex(model), [model]);
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
  const part = findPart(model, selected);

  const show = useCallback((id) => {
    setSelected(id);
    setNotice('');
    setHover(null);
    setPointing(false);
    setView((v) => ({ preset: v.preset, focus: Boolean(id), turn: v.turn + 1 }));
  }, []);

  const open = useCallback((id, options = {}) => {
    if (!findPart(model, id)) return;
    if (!part) opener.current = document.activeElement;
    const hash = formatHash({ id, audience });
    if (hash !== window.location.hash) window.history.pushState(null, '', hash);
    wantsHeading.current = Boolean(options.focusPanel);
    show(id);
  }, [audience, model, part, show]);

  const close = useCallback(() => {
    const was = selected;
    const hash = formatHash({ id: null, audience });
    window.history.pushState(null, '', hash || window.location.href.split('#')[0]);
    show(null);
    setWide(false);
    const back = opener.current;
    const target = back && back.isConnected && back !== document.body
      ? back : document.querySelector(`[data-module="${moduleOf(was ?? '')}"]`);
    target?.focus?.();
    opener.current = null;
  }, [audience, selected, show]);

  const choosePreset = useCallback((preset) => {
    setView((v) => ({ preset, focus: false, turn: v.turn + 1 }));
  }, []);

  const changeAudience = useCallback((value) => {
    setAudience(value);
    save(value);
    const hash = formatHash({ id: selected, audience: value });
    window.history.replaceState(null, '', hash || window.location.href.split('#')[0]);
  }, [selected]);

  useEffect(() => {
    // Back, Forward and hand-typed addresses. The address says what is shown, so one
    // without v=dev is the manager's view.
    const read = () => {
      const next = parseHash(window.location.hash, model);
      setAudience(next.audience ?? 'manager');
      if (next.unknown) setNotice(`Nothing on the map is called “${next.unknown}”.`);
      if (next.id !== selected) show(next.id);
    };
    window.addEventListener('popstate', read);
    window.addEventListener('hashchange', read);
    return () => {
      window.removeEventListener('popstate', read);
      window.removeEventListener('hashchange', read);
    };
  }, [model, selected, show]);

  useEffect(() => {
    // A link without v=dev opened by someone who uses the developer view: say so in the
    // address, so that it and the page agree.
    if (audience === 'developer' && first.audience === null) {
      window.history.replaceState(null, '', formatHash({ id: first.id, audience }));
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
    document.title = part
      ? `${selected} ${(part.sub ?? part.module).name} · StockAgent architecture`
      : 'StockAgent architecture';
  }, [part, selected]);

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
      const preset = { 1: 'front', 2: 'top', 3: 'side', 4: 'below' }[event.key];
      if (preset) choosePreset(preset);
      else if (event.key === 'r' || event.key === 'R') choosePreset('front');
      else if (event.key === '/') { event.preventDefault(); setDialog('search'); }
      else if (event.key === '?') { event.preventDefault(); setDialog('help'); }
      else if ((event.key === 'p' || event.key === 'P') && !reduced) setPaused((p) => !p);
      else if (event.key === 'Escape' && selected) close();
    };
    document.addEventListener('keydown', keys);
    return () => document.removeEventListener('keydown', keys);
  }, [choosePreset, close, reduced, selected]);

  // A dialog's late "closed" event must not shut the one opened since.
  const shut = useCallback((name) => setDialog((now) => (now === name ? null : now)), []);

  const touched = useMemo(() => related(model, selected), [model, selected]);
  const parts = useMemo(() => {
    if (!selected) return null;
    const moduleId = moduleOf(selected);
    const block = world.modules.find((m) => m.id === moduleId);
    const data = model.modules.find((m) => m.id === moduleId);
    return { moduleId, block, blocks: layoutSubmodules(block, data.submodules), data };
  }, [model, selected, world]);

  const goal = useMemo(() => ({
    preset: view.preset,
    bounds: world.bounds,
    focus: view.focus && parts ? { module: parts.block, subs: parts.blocks } : null,
  }), [parts, view, world]);

  const items = useMemo(() => {
    const whole = !view.focus;
    const below = view.preset === 'below' && whole;
    // From the side the modules stand behind one another: the planes say who is on them.
    const side = view.preset === 'side' && whole;
    const stateOf = (id) => (!selected ? 'rest'
      : moduleOf(selected) === id ? 'selected' : touched.modules.has(id) ? 'rest' : 'faded');
    const list = [];
    for (const m of world.modules) {
      const info = model.modules.find((x) => x.id === m.id);
      list.push({ key: m.id, kind: 'module', id: m.id, text: info.short, select: m.id,
        colour: moduleColour(m.id), state: stateOf(m.id),
        priority: stateOf(m.id) === 'selected' ? 0 : 2,
        hidden: (side && stateOf(m.id) !== 'selected') || (below && m.plane === 'top'),
        pos: [m.pos[0], m.pos[1] + (below ? -1 : 1) * (m.size[1] / 2 + 0.25), m.pos[2]] });
    }
    for (const e of world.externals) {
      list.push({ key: e.id, kind: 'external', text: e.name, colour: SURFACE.ink2,
        state: selected && !touched.modules.has(e.id) ? 'faded' : 'rest', priority: 3,
        hidden: below,
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
        state: selected ? 'faded' : 'rest', priority: side ? 1 : 6,
        hidden: !whole || below
          || (view.preset === 'top' && (plane.id === 'base' || plane.id === 'stores')),
        // From the side the screen's left is +z: the words stand clear of the blocks.
        pos: side ? [x + w / 2, y - (plane.id === 'base' ? 1.6 : 0), z + d / 2 + 6]
          : [x - w / 2, y, z + d / 2] });
    }
    for (const s of world.stores) {
      const near = selected ? touched.stores.has(s.id) : false;
      const target = model.stores.find((x) => x.id === s.id).writers
        .find((w) => findPart(model, w));
      list.push({ key: s.id, kind: 'store', text: s.name, select: target, colour: PLANE.planeStores,
        state: selected && !near ? 'faded' : 'rest', priority: 5,
        hidden: !(near || below) || side,
        pos: [s.pos[0], s.pos[1] + (below ? -0.4 : 0.5), s.pos[2]] });
    }
    if (parts) {
      for (const p of parts.blocks) {
        const info = parts.data.submodules.find((s) => s.id === p.id);
        list.push({ key: p.id, kind: 'sub', id: p.id, text: info.name, select: p.id,
          colour: moduleColour(p.id), state: selected === p.id ? 'selected' : 'rest',
          priority: selected === p.id ? 0 : 1, hidden: !whole ? false : view.preset !== 'front',
          pos: [p.pos[0], p.pos[1] + p.size[1] / 2 + 0.15, p.pos[2]] });
      }
    }
    return list;
  }, [model, parts, selected, touched, view, world]);

  return (
    <div className={`app${part ? ' with-panel' : ''}${wide ? ' wide' : ''}`} ref={rootRef}
      data-app data-selected={selected ?? ''} data-preset={view.preset}
      data-audience={audience} data-motion={moving ? 'on' : 'off'}>
      <a className="skip" href="#modules"
        onClick={(e) => {
          // moving there by the address would read as "close what is open"
          e.preventDefault();
          document.querySelector('#modules [data-module]')?.focus();
        }}>Skip to the list of modules</a>
      <TopBar model={model} preset={view.focus ? null : view.preset} audience={audience}
        motion={moving}
        reduced={reduced} onPreset={choosePreset} onReset={() => choosePreset('front')}
        onSearch={() => setDialog('search')} onAudience={changeAudience}
        onMotion={() => setPaused((p) => !p)} onHelp={() => setDialog('help')} />
      <Legend model={model} selected={selected} audience={audience} onSelect={(id) => open(id)} />
      <main className={`world${pointing ? ' pointing' : ''}`} tabIndex={0}
        aria-label="3D view of the product. Arrow keys turn it; plus and minus zoom.">
        {webgl ? (
          <SceneGuard>
            <Scene world={world} goal={goal} command={view.turn} nudge={nudge} selected={selected}
              touched={touched} parts={parts} anchors={items} labels={labels} rootRef={rootRef}
              reduced={reduced} moving={moving} preset={view.focus ? null : view.preset}
              hovered={hover?.flow.key} onSelect={(id) => open(id)} onHoverFlow={setHover}
              onHoverBlock={setPointing} />
          </SceneGuard>
        ) : <p className="no-view" role="alert">{NO_VIEW}</p>}
        <Labels items={items.filter((i) => !i.hidden)} labels={labels}
          onSelect={(id) => open(id)} />
        {notice ? <p className="notice" role="status">{notice}</p> : null}
      </main>
      {part ? (
        <Panel ref={heading} model={model} part={part} audience={audience} wide={wide}
          onWide={() => setWide((w) => !w)} onClose={close} onSelect={(id) => open(id)} />
      ) : null}
      <Tooltip hover={hover} names={names} />
      <SearchDialog open={dialog === 'search'} index={index} onClose={() => shut('search')}
        onPick={(item) => { shut('search'); open(item.id, { focusPanel: true }); }} />
      <HelpDialog open={dialog === 'help'} onClose={() => shut('help')} />
    </div>
  );
}
