// What a selection means: the address, what it touches, the facts the panel shows, and
// search. Pure functions over the model.

import { moduleOf, nodeOf } from '../theme.js';
import { flowKey } from './world.js';

export function findPart(model, id) {
  if (!id) return null;
  const module = model.modules.find((m) => m.id === moduleOf(id));
  if (!module) return null;
  if (module.id === id) return { module, sub: null };
  const sub = module.submodules.find((s) => s.id === id);
  return sub ? { module, sub } : null;
}

/** `#m=M5.2&v=dev` to `{id, audience, unknown}`; `audience` is null when not given. */
export function parseHash(hash, model) {
  const params = new URLSearchParams(String(hash).replace(/^#/, ''));
  const asked = params.get('m');
  const id = asked && findPart(model, asked) ? asked : null;
  const view = params.get('v');
  return {
    id,
    audience: view === 'dev' ? 'developer' : view === 'mgr' ? 'manager' : null,
    unknown: asked && !id ? asked : null,
  };
}

export function formatHash({ id, audience }) {
  const parts = [];
  if (id) parts.push(`m=${encodeURIComponent(id)}`);
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

/** Each setting of a part: the repository's default and, where KT section 1 states one,
 *  the production value with its source and date. */
export function settingsFor(model, sub) {
  const switches = new Map(model.switches.map((s) => [s.key, s]));
  const production = new Map(model.production.filter((p) => p.key).map((p) => [p.key, p]));
  return (sub.config ?? []).map((key) => {
    const record = switches.get(key);
    return {
      key,
      value: record ? formatValue(record.default) : 'unknown',
      source: record?.default_source ?? '',
      env: record?.env ?? null,
      production: production.has(key)
        ? { ...production.get(key), value: formatValue(production.get(key).value) }
        : null,
    };
  });
}

export function searchIndex(model) {
  const items = [];
  // `name` is what a title is ranked by: for a module or part, the words after its ID.
  const add = (kind, id, title, detail, name = title) => items.push({
    kind, id, title, name, detail, haystack: `${id} ${title} ${detail}`.toLowerCase(),
  });
  const owner = new Map();
  for (const m of model.modules) {
    add('module', m.id, `${m.id} ${m.short}`, `${m.name}: ${m.summary}`, m.short);
    for (const s of m.submodules) {
      add('part', s.id, `${s.id} ${s.name}`, s.summary, s.name);
      for (const file of s.python_files ?? []) {
        owner.set(file, s.id);
        add('file', s.id, file, `${s.id} ${s.name}`);
      }
      for (const code of s.code ?? []) {
        add('function', s.id, code.split('::')[1] ?? code, code.split('::')[0]);
      }
      for (const key of s.config ?? []) add('setting', s.id, key, `${s.id} ${s.name}`);
    }
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
