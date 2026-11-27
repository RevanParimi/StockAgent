// The flat map (MAP-005): the same model drawn in two dimensions, for a browser without
// WebGL and for a narrow window. Where everything stands, and what each view and choice
// emphasises. Pure functions over the model and the world, so tests run them without a
// browser. DESIGN.md says how it looks.

import { PLANE, SHARED, moduleColour, moduleOf, nodeOf } from '../theme.js';
import { codeSummary } from './galaxy.js';
import { findPart } from './select.js';
import { flowKey } from './world.js';

export const NARROW_QUERY = '(max-width: 760px)';

// Sizes in the drawing's own units. `column` is a column's width; a narrow map is two cards
// abreast. `perLine` is how many characters a line of a card holds.
export const FLAT = {
  wide: { column: 124, card: [112, 52], store: [112, 54], storeLine: 17, gap: 14, pad: 10,
    title: 22 },
  // the stores are three abreast there, so the map is not mostly storage
  narrow: { width: 360, card: [164, 52], store: [108, 54], storeLine: 14, gap: 12, pad: 10,
    title: 22 },
};

export const BANDS = {
  top: { name: 'What people see', tone: PLANE.planeTop },
  middle: { name: 'The product, flowing left to right', tone: PLANE.planeMiddle },
  base: { name: 'The base frame', tone: PLANE.planeBase },
  ring: { name: 'Watching it all', tone: PLANE.planeRing },
  stores: { name: 'Storage (the data volume)', tone: PLANE.planeStores },
  shared: { name: 'Files of no one module', tone: PLANE.planeRing },
};

/** Words into lines of at most `perLine` characters; a longer word keeps a line of its
 *  own, and what does not fit in `most` lines ends in an ellipsis. */
export function wrapWords(text, perLine, most = 3) {
  const lines = [];
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const last = lines.at(-1);
    if (last !== undefined && `${last} ${word}`.length <= perLine) {
      lines[lines.length - 1] = `${last} ${word}`;
    } else lines.push(word);
  }
  if (lines.length <= most) return lines;
  const kept = lines.slice(0, most);
  kept[most - 1] = `${kept[most - 1].slice(0, perLine - 1)}…`;
  return kept;
}

const idNumber = (id) => Number(String(id).slice(1));
const byColumn = (a, b) => a.column - b.column || idNumber(a.id) - idNumber(b.id);

function moduleCard(m, size) {
  return { id: m.id, kind: 'module', w: size[0], h: size[1], colour: moduleColour(m.id),
    select: m.id, lines: [m.id, m.short] };
}

/** The whole drawing: `{width, height, bands, cards, arrows, pipes}`. With `code` (the code
 *  galaxy) there are no outside parties, stores, flows or store lines, each card counts its
 *  files, and the shared files have a card of their own. */
export function flatLayout(model, world, { narrow = false, code = null } = {}) {
  const size = narrow ? FLAT.narrow : FLAT.wide;
  const modules = [...model.modules].sort(byColumn);
  const last = Math.max(...modules.map((m) => m.column));
  const columns = narrow ? 2 : last + 1;
  const width = narrow ? FLAT.narrow.width : columns * size.column + size.pad * 2;
  const cards = [];
  const bands = [];
  let top = 0;

  const cardOf = (m) => {
    const card = moduleCard(m, size.card);
    if (code) {
      const counted = codeSummary(code, m.id);
      card.lines = [m.id, m.short, countFiles(counted.files.length)];
    }
    return card;
  };
  const externals = code ? [] : world.externals.map((e) => ({ id: e.id, kind: 'external',
    w: size.card[0], h: size.card[1], colour: PLANE.planeTop, select: null,
    lines: wrapWords(e.name, 18, 2) }));

  // The x of a column's card, centred in its column.
  const columnX = (column, w) => size.pad + column * size.column + (size.column - w) / 2;
  // Cards of one width `n` abreast on a narrow map, centred.
  const abreast = (index, w, n = 2) => {
    const left = (width - w * n - size.pad * (n - 1)) / 2;
    return left + (index % n) * (w + size.pad);
  };

  /** One band: its name, then its cards, then room below. `place` gives each card its x
   *  and its row. */
  const band = (id, items, place) => {
    if (!items.length) return;
    const rows = [];
    const placed = items.map((card, index) => {
      const [x, row] = place(card, index);
      rows[row] = Math.max(rows[row] ?? 0, card.h);
      return { card, x, row };
    });
    const offsets = [];
    rows.reduce((y, h, row) => { offsets[row] = y; return y + h + size.gap; }, 0);
    const height = size.title + offsets.at(-1) + rows.at(-1) + size.gap;
    for (const { card, x, row } of placed) {
      cards.push({ ...card, x, y: top + size.title + offsets[row], band: id });
    }
    bands.push({ id, ...BANDS[id], x: 0, y: top, w: width, h: height });
    top += height + 6;
  };

  /** A wide band's places: each card in its column, those sharing one stacked. */
  const inColumns = (columnOf) => {
    const used = new Map();
    return (card) => {
      const column = columnOf(card);
      const row = used.get(column) ?? 0;
      used.set(column, row + 1);
      return [columnX(column, card.w), row];
    };
  };
  const inRows = (n) => (card, index) => [abreast(index, card.w, n), Math.floor(index / n)];
  const columnOf = new Map(modules.map((m) => [m.id, m.column]));

  for (const plane of ['top', 'middle', 'base', 'ring']) {
    // On a wide map the watchers stand beside the product, to its right.
    if (!narrow && plane === 'ring') continue;
    const wanted = narrow || plane !== 'middle' ? [plane] : ['middle', 'ring'];
    const items = modules.filter((m) => wanted.includes(m.plane)).map(cardOf);
    if (plane === 'top') {
      // outside parties take the free columns from the right
      const taken = new Set(items.map((c) => columnOf.get(c.id)));
      let column = last;
      for (const e of [...externals].reverse()) {
        while (taken.has(column) && column > 0) column -= 1;
        columnOf.set(e.id, column);
        taken.add(column);
      }
      items.push(...externals);
    }
    band(plane, items, narrow ? inRows(2) : inColumns((c) => columnOf.get(c.id)));
  }
  if (!narrow) {
    // the frame round the watchers, inside the middle band
    const ring = cards.filter((c) => model.modules.some((m) => m.id === c.id && m.plane === 'ring'));
    if (ring.length) {
      const x = Math.min(...ring.map((c) => c.x)) - 4;
      const y = Math.min(...ring.map((c) => c.y)) - 4;
      bands.push({ id: 'ring', ...BANDS.ring, frame: true, x, y,
        w: Math.max(...ring.map((c) => c.x + c.w)) + 4 - x,
        h: Math.max(...ring.map((c) => c.y + c.h)) + 4 - y });
    }
  }

  if (code) {
    const counted = codeSummary(code, SHARED);
    band('shared', [{ id: SHARED, kind: 'module', w: size.card[0], h: size.card[1],
      colour: PLANE.planeRing, select: SHARED,
      lines: ['Shared files', countFiles(counted.files.length)] }],
    (card) => [narrow ? abreast(0, card.w) : columnX(0, card.w), 0]);
  } else {
    // stores keep the world's left-to-right order, under the modules that write them
    const stores = world.stores.map((s) => {
      const writer = model.stores.find((x) => x.id === s.id).writers
        .find((w) => findPart(model, w));
      return { id: s.id, kind: 'store', w: size.store[0], h: size.store[1],
        colour: PLANE.planeStores, select: writer ?? null,
        lines: wrapWords(s.name, size.storeLine) };
    });
    const deep = Math.ceil(stores.length / columns);
    band('stores', stores, narrow ? inRows(3)
      : (card, index) => [columnX(Math.floor(index / deep), card.w), index % deep]);
  }

  const at = new Map(cards.map((c) => [c.id, c]));
  const arrows = code ? [] : model.flows.flatMap((flow, index) => {
    const from = at.get(nodeOf(flow.from));
    const to = at.get(nodeOf(flow.to));
    if (!from || !to || from === to) return [];
    const ring = [from, to].some((c) => model.modules.some((m) => m.id === c.id
      && m.plane === 'ring'));
    return [{ key: flowKey(flow), from: from.id, to: to.id, what: flow.what, ring,
      colour: from.colour, ...arrowPath(from, to, index, size) }];
  });
  const pipes = code ? [] : world.pipes.flatMap((p) => {
    const from = at.get(p.module);
    const to = at.get(p.store);
    if (!from || !to) return [];
    const [x1, y1] = [from.x + from.w / 2, from.y + from.h];
    const [x2, y2] = [to.x + to.w / 2, to.y];
    const middle = (y1 + y2) / 2;
    return [{ store: p.store, module: p.module, colour: from.colour,
      d: path([x1, y1], [x1, middle], [x2, middle], [x2, y2]) }];
  });
  return { narrow, width, height: Math.max(0, top - 6), bands, cards, arrows, pipes };
}

const countFiles = (n) => `${n} file${n === 1 ? '' : 's'}`;

const round = (v) => Math.round(v * 10) / 10;
const path = (a, b, c, d) => `M${a.map(round)} C${b.map(round)} ${c.map(round)} ${d.map(round)}`;

/** A curve from one card's edge to another's: sideways where they stand apart left to
 *  right, else up or down. `index` keeps neighbouring arrows apart, and one that runs far
 *  along a row bows over the cards between. */
export function arrowPath(from, to, index, size) {
  const centre = (c) => [c.x + c.w / 2, c.y + c.h / 2];
  const [ax, ay] = centre(from);
  const [bx, by] = centre(to);
  const dx = bx - ax;
  const dy = by - ay;
  const sideways = Math.abs(dx) / from.w > Math.abs(dy) / from.h;
  const nudge = ((index % 3) - 1) * 7;
  let start;
  let end;
  let c1;
  let c2;
  if (sideways) {
    const way = Math.sign(dx);
    start = [ax + (way * from.w) / 2, ay + nudge];
    end = [bx - (way * to.w) / 2, by + nudge];
    const reach = Math.abs(end[0] - start[0]) * 0.4;
    const column = size.column ?? from.w;
    const bow = Math.abs(dy) < from.h && Math.abs(dx) > column * 1.5
      ? -(from.h * 0.7 + (index % 3) * 6) : 0;
    c1 = [start[0] + way * reach, start[1] + bow];
    c2 = [end[0] - way * reach, end[1] + bow];
  } else {
    const way = Math.sign(dy) || 1;
    start = [ax + nudge, ay + (way * from.h) / 2];
    end = [bx + nudge, by - (way * to.h) / 2];
    const reach = Math.abs(end[1] - start[1]) * 0.4;
    c1 = [start[0], start[1] + way * reach];
    c2 = [end[0], end[1] - way * reach];
  }
  return { d: path(start, c1, c2, end), start, end };
}

/** What each card, arrow and store line shows, for a view (`preset`), a choice (`shown`, a
 *  part or module, with `touched`, what it relates to) or a playing step (`lit`). The same
 *  rules as the 3D world's. */
export function flatStates(model, layout, { shown = null, touched = null, lit = null,
  preset = 'front' } = {}) {
  const cards = new Map();
  for (const card of layout.cards) {
    let state = 'rest';
    if (card.kind === 'module') {
      if (lit) state = lit.modules.has(card.id) ? 'lit' : 'faded';
      else if (shown) {
        state = moduleOf(shown) === card.id ? 'selected'
          : touched.modules.has(card.id) ? 'rest' : 'faded';
      }
    } else if (card.kind === 'external') {
      if (lit) state = lit.externals.has(card.id) ? 'lit' : 'faded';
      else if (shown && !touched.modules.has(card.id)) state = 'faded';
    } else {
      const near = lit ? lit.stores.has(card.id) : shown ? touched.stores.has(card.id) : false;
      if (lit) state = near ? 'lit' : 'faded';
      else if (shown) state = near ? 'near' : 'faded';
      else if (preset === 'below') state = 'near';
      else if (preset === 'top') state = 'faded';
    }
    cards.set(card.id, state);
  }
  const quiet = preset === 'below' || preset === 'side';
  const arrows = new Map(layout.arrows.map((a) => {
    if (lit) return [a.key, lit.flows.has(a.key) ? 'bright' : 'faded'];
    if (shown) return [a.key, touched.flows.has(a.key) ? 'bright' : 'faded'];
    return [a.key, quiet ? 'dim' : 'rest'];
  }));
  const pipes = new Map(layout.pipes.map((p) => {
    const related = lit ? lit.stores.has(p.store) && lit.modules.has(p.module)
      : Boolean(shown) && touched.stores.has(p.store) && p.module === moduleOf(shown);
    const level = related ? 'bright' : !lit && !shown && preset === 'below' ? 'show' : 'off';
    return [`${p.module}>${p.store}`, level];
  }));
  return { cards, arrows, pipes };
}

/** The galaxy's flat cards: the chosen module's (or shared files') is selected, the
 *  others fade; with nothing chosen, all rest. */
export function flatCodeStates(layout, chosen) {
  const wanted = chosen ? (chosen === SHARED ? SHARED : moduleOf(chosen)) : null;
  return { cards: new Map(layout.cards.map((c) => [c.id,
    !wanted ? 'rest' : c.id === wanted ? 'selected' : 'faded'])),
  arrows: new Map(), pipes: new Map() };
}

/** What a card says to those who cannot see it. */
export function cardLabel(model, card) {
  if (card.id === SHARED) return `Shared files: ${card.lines.at(-1)}`;
  if (card.kind === 'store') {
    return `Store ${model.stores.find((s) => s.id === card.id).name}: opens the part that `
      + 'writes it';
  }
  const module = model.modules.find((m) => m.id === card.id);
  const counted = card.lines.length > 2 ? `, ${card.lines[2]}` : '';
  return module ? `${module.id} ${module.short}${counted}: ${module.summary}`
    : card.lines.join(' ');
}
