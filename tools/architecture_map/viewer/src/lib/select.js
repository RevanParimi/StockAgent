// What a selection means: the address, what it touches, the facts the panel shows, and
// search. Pure functions over the model.

import { SHARED, moduleOf, nodeOf } from '../theme.js';
import { flowKey } from './world.js';

export function findPart(model, id) {
  if (!id) return null;
  const module = model.modules.find((m) => m.id === moduleOf(id));
  if (!module) return null;
  if (module.id === id) return { module, sub: null };
  const sub = module.submodules.find((s) => s.id === id);
  return sub ? { module, sub } : null;
}

/** The times of day a job runs at: most jobs have one. */
export const timesOf = (job) => String(job.schedule.time).split(', ');

// How many steps each playable mode has in this model (lib/play.js plays them).
const STEPS = {
  clock: (model) => model.jobs.reduce((n, j) => n + timesOf(j).length, 0),
  trace: (model) => model.traces?.[0]?.steps.length ?? 0,
  tour: (model) => model.tours?.[0]?.steps.length ?? 0,
};
// `hasOwn`: an address naming `constructor` or `toString` names no mode.
const stepCount = (model, mode) => (Object.hasOwn(STEPS, mode) ? STEPS[mode](model) : 0);

/** `#m=M5.2&v=dev` or `#p=tour&s=3` to `{id, audience, play, unknown}`; `audience` is
 *  null when not given. `play` is `{mode, step}` with the step counted from 0, kept inside
 *  the mode's steps; a mode and a part together show the mode. A code galaxy address, `#g`,
 *  `#g&m=M5` or `#g&f=core/portfolio/advisor.py`, adds `code: true` and `file`; there a part
 *  may also be `shared`, and a file wins over a part. */
export function parseHash(hash, model) {
  const params = new URLSearchParams(String(hash).replace(/^#/, ''));
  const view = params.get('v');
  const audience = view === 'dev' ? 'developer' : view === 'mgr' ? 'manager' : null;
  const mode = params.get('p');
  if (mode !== null) {
    const count = stepCount(model, mode);
    const asked = Math.trunc(Number(params.get('s') ?? 1)) || 1;
    return { id: null, audience, unknown: count ? null : `p=${mode}`,
      play: count ? { mode, step: Math.min(count, Math.max(1, asked)) - 1 } : null };
  }
  const asked = params.get('m');
  if (params.has('g')) {
    const path = params.get('f');
    const file = path !== null && model.files.some((f) => f.path === path) ? path : null;
    const id = !file && asked && (asked === SHARED || findPart(model, asked)) ? asked : null;
    const unknown = path !== null ? (file ? null : path) : (asked && !id ? asked : null);
    return { id, audience, play: null, unknown, code: true, file };
  }
  const id = asked && findPart(model, asked) ? asked : null;
  return { id, audience, play: null, unknown: asked && !id ? asked : null };
}

export function formatHash({ id, audience, play, code, file }) {
  const parts = [];
  if (play) parts.push(`p=${play.mode}`, `s=${play.step + 1}`);
  else {
    if (code) parts.push('g');
    // a path reads better with its slashes
    if (code && file) parts.push(`f=${encodeURIComponent(file).replaceAll('%2F', '/')}`);
    else if (id) parts.push(`m=${encodeURIComponent(id)}`);
  }
  if (audience === 'developer') parts.push('v=dev');
  return parts.length ? `#${parts.join('&')}` : '';
}

const ownedBy = (who, id) => (id.includes('.') ? who === id : moduleOf(who) === id);

/** The modules, stores and flows a selection touches; everything else fades. */
export function related(model, id) {
  if (!id) return null;
  const module = moduleOf(id);
  const modules = new Set([module]);
  const flows = new Set();
  for (const f of model.flows) {
    if (nodeOf(f.from) === module || nodeOf(f.to) === module) {
      flows.add(flowKey(f));
      modules.add(nodeOf(f.from));
      modules.add(nodeOf(f.to));
    }
  }
  const stores = new Set(model.stores
    .filter((s) => [...s.writers, ...s.readers].some((who) => ownedBy(who, id)))
    .map((s) => s.id));
  return { modules, flows, stores };
}

export function storesFor(model, id) {
  return {
    writes: model.stores.filter((s) => s.writers.some((w) => ownedBy(w, id))),
    reads: model.stores.filter((s) => s.readers.some((r) => ownedBy(r, id))),
  };
}

export const jobsFor = (model, id) => model.jobs.filter((j) => ownedBy(j.module, id));
export const routesFor = (model, id) => model.routes.filter((r) => ownedBy(r.module, id));

/** Flows are drawn between modules, so a part shows its module's. */
export function flowsFor(model, id) {
  const module = moduleOf(id);
  const names = new Map([
    ...model.modules.map((m) => [m.id, `${m.id} ${m.short}`]),
    ...(model.externals ?? []).map((e) => [e.id, e.name]),
  ]);
  const named = (who) => names.get(nodeOf(who)) ?? who;
  return {
    into: model.flows.filter((f) => nodeOf(f.to) === module)
      .map((f) => ({ key: flowKey(f), other: named(f.from), otherId: nodeOf(f.from), what: f.what })),
    out: model.flows.filter((f) => nodeOf(f.from) === module)
      .map((f) => ({ key: flowKey(f), other: named(f.to), otherId: nodeOf(f.to), what: f.what })),
  };
}

export function formatValue(value) {
  if (value === null || value === undefined) return 'not set';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (Array.isArray(value)) return `[${value.map(formatValue).join(', ')}]`;
  if (typeof value === 'object') {
    return Object.entries(value).map(([k, v]) => `${k}: ${formatValue(v)}`).join(', ');
  }
  return String(value);
}

/** One setting: the repository's default and, where KT section 1 states one, the
 *  production value with its source and date. */
export function settingOf(model, key) {
  const record = model.switches.find((s) => s.key === key);
  const cited = model.production.find((p) => p.key === key);
  return {
    key,
    value: record ? formatValue(record.default) : 'unknown',
    source: record?.default_source ?? '',
    env: record?.env ?? null,
    production: cited ? { ...cited, value: formatValue(cited.value) } : null,
  };
}

/** Each setting of a part. */
export const settingsFor = (model, sub) => (sub.config ?? []).map((key) => settingOf(model, key));

export function searchIndex(model) {
  const items = [];
  // `name` is what a title is ranked by: for a module or part, the words after its ID; for
  // a file, its name without the folders. `file` is a Python file the galaxy can open.
  const add = (kind, id, title, detail, name = title, file = null) => items.push({
    kind, id, title, name, detail, haystack: `${id} ${title} ${detail}`.toLowerCase(),
    ...(file ? { file } : {}),
  });
  const python = new Set((model.files ?? []).map((f) => f.path));
  const addFile = (id, path, detail) => add('file', id, path, detail, path.split('/').at(-1),
    path);
  for (const m of model.modules) {
    add('module', m.id, `${m.id} ${m.short}`, `${m.name}: ${m.summary}`, m.short);
    for (const file of m.python_files ?? []) addFile(m.id, file, `${m.id} ${m.short}`);
    for (const s of m.submodules) {
      add('part', s.id, `${s.id} ${s.name}`, s.summary, s.name);
      for (const file of s.python_files ?? []) addFile(s.id, file, `${s.id} ${s.name}`);
      for (const code of s.code ?? []) {
        const [path, fn] = code.split('::');
        add('function', s.id, fn ?? code, path, fn ?? code, python.has(path) ? path : null);
      }
      for (const key of s.config ?? []) add('setting', s.id, key, `${s.id} ${s.name}`);
    }
  }
  for (const file of model.shared?.python_files ?? []) {
    addFile(SHARED, file, 'Shared: it belongs to no one module');
  }
  for (const store of model.stores) {
    const target = store.writers.find((w) => findPart(model, w));
    if (target) add('store', target, store.name, store.path);
  }
  for (const job of model.jobs) {
    if (findPart(model, job.module)) add('job', job.module, job.name, `${job.id}: ${job.does}`);
  }
  return items;
}

const KIND_ORDER = { module: 0, part: 1, store: 2, job: 3, setting: 4, function: 5, file: 6 };

/** The items that hold every word of the query, best first. */
export function search(index, query, limit = 20) {
  const words = String(query).toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const scored = [];
  for (const item of index) {
    if (!words.every((w) => item.haystack.includes(w))) continue;
    const title = item.title.toLowerCase();
    const name = item.name.toLowerCase();
    const id = item.id.toLowerCase();
    const first = words[0];
    const rank = id === words.join(' ') && (item.kind === 'module' || item.kind === 'part') ? 0
      : name.startsWith(first) || title.startsWith(first) ? 1
        : title.includes(first) ? 2 : 3;
    scored.push([rank, KIND_ORDER[item.kind] ?? 9, scored.length, item]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  return scored.slice(0, limit).map((entry) => entry[3]);
}
