// The three things the map plays (MAP-003): a day on the clock, one stock's life and the
// guided tour. What the steps are, what each one lights, and where the clock's ring and its
// beads stand. Pure functions over the model and the world.

import { moduleOf } from '../theme.js';
import { findPart, related, timesOf } from './select.js';
import { prose } from './flow.js';
import { LEVEL, boundsOf, flowKey } from './world.js';

export const MODES = {
  clock: { title: 'A day on the clock', stepMs: 2400 },
  trace: { title: 'One stock’s life', stepMs: 6000 },
  tour: { title: 'Guided tour', stepMs: 6000 },
};
export const SPEEDS = [1, 2, 4];
// The views a tour stop may ask for; the guard knows the same names (model/validate.py).
export const TOUR_PRESETS = ['front', 'top', 'side', 'below', 'clock', 'focus'];

const arrows = (text) => prose(String(text).replace(/\s*─►\s*/g, ' → '));
const jobsById = (model) => new Map(model.jobs.map((j) => [j.id, j]));

// -- the clock's times ------------------------------------------------------------------

const GROUP_RANK = { daily: 0, weekly: 1, calendar: 2 };
const DAY = 24 * 60;

function minutesOf(time) {
  const found = /^(\d{1,2}):(\d{2})$/.exec(time);
  return found ? Number(found[1]) * 60 + Number(found[2]) : null;
}

/** Every time a job runs, in clock order; a job that runs three times a day is there
 *  three times. Jobs sharing a time come daily first, then weekly, then monthly. */
export function moments(model) {
  const all = model.jobs.flatMap((job) => timesOf(job).map((time) => ({
    key: `${job.id}@${time}`, time, minutes: minutesOf(time), job,
  })));
  return all.sort((a, b) => (a.minutes ?? DAY) - (b.minutes ?? DAY)
    || (GROUP_RANK[a.job.schedule.group] ?? 3) - (GROUP_RANK[b.job.schedule.group] ?? 3)
    || a.job.id.localeCompare(b.job.id, 'en'));
}

/** The days a job runs on, in words. */
export const daysOf = (job) => ({ Daily: 'Every day', 'Mon–Fri': 'Monday to Friday' }[
  job.schedule.when] ?? job.schedule.when);

export const zoneOf = (job) => (job.timezone === 'Asia/Kolkata' ? 'IST' : job.timezone);

// -- steps ------------------------------------------------------------------------------

/** What plays when the page opens: the mode its address names, else, for a manager who
 *  asked for no part, the guided tour at its first stop. `parsed` is the address as
 *  parseHash read it. */
export function openingPlay(model, parsed, audience) {
  if (parsed.play) return parsed.play;
  if (parsed.id || parsed.unknown || parsed.code || audience !== 'manager') return null;
  return stepsOf(model, 'tour').length ? { mode: 'tour', step: 0 } : null;
}

export function stepsOf(model, mode) {
  if (mode === 'clock') return moments(model);
  if (mode === 'trace') return model.traces?.[0]?.steps ?? [];
  if (mode === 'tour') return model.tours?.[0]?.steps ?? [];
  return [];
}

/** The words of a step: `lead` (when, or nothing), `text`, and for the clock the job's name. */
export function captionOf(mode, step) {
  if (mode === 'clock') {
    return { lead: `${step.time} · ${daysOf(step.job)}`, name: step.job.name,
      text: arrows(step.job.does) };
  }
  if (mode === 'trace') return { lead: step.when, name: '', text: arrows(step.text) };
  return { lead: '', name: '', text: arrows(step.caption) };
}

// -- what a step lights -----------------------------------------------------------------

/** The modules, parts, stores, outside parties and flows to light for these names. */
export function lightsOf(names, flows = []) {
  const lit = { modules: new Set(), parts: new Set(), stores: new Set(), externals: new Set(),
    flows: new Set() };
  for (const name of names) {
    if (name.startsWith('ext.')) lit.externals.add(name);
    else if (name.startsWith('S.')) lit.stores.add(name);
    else {
      lit.modules.add(moduleOf(name));
      if (name.includes('.')) lit.parts.add(name);
    }
  }
  for (const key of flows) {
    const [from, to] = key.split('>');
    lit.flows.add(flowKey({ from, to }));
  }
  return lit;
}

export const jobLights = (job) => lightsOf(job.lights ?? [], job.flows ?? []);

/** A trace step lights what it names; a job it names stands for the job's part. */
export function traceLights(model, step) {
  const jobs = jobsById(model);
  return lightsOf(step.refs.map((name) => jobs.get(name)?.module ?? name), step.flows ?? []);
}

/** How the map shows a tour stop: the view, the part to open up (`focus`), what to light
 *  and, on the clock, which job. A stop without a target lights nothing and dims nothing. */
export function stopView(model, stop) {
  const none = { preset: stop.preset, selected: null, lit: null, job: null };
  if (stop.preset === 'focus') {
    return { ...none, preset: 'front', selected: findPart(model, stop.ref) ? stop.ref : null };
  }
  if (!stop.ref) return none;
  if (stop.preset === 'clock') {
    const job = jobsById(model).get(stop.ref);
    return job ? { ...none, lit: jobLights(job), job } : none;
  }
  if (stop.ref.startsWith('S.')) {
    const store = model.stores.find((s) => s.id === stop.ref);
    return { ...none, lit: lightsOf([stop.ref, ...(store?.writers ?? [])]) };
  }
  if (stop.ref.startsWith('ext.')) return { ...none, lit: lightsOf([stop.ref]) };
  // a module in a view of the whole world: it, its neighbours and the flows between them
  const touched = related(model, stop.ref);
  const lit = lightsOf([...touched.modules]);
  lit.flows = touched.flows;
  return { ...none, lit };
}

/** Everything the map needs to show one step of a mode. */
export function viewOf(model, mode, step) {
  if (mode === 'clock') {
    return { preset: 'clock', selected: null, lit: jobLights(step.job), job: step.job };
  }
  if (mode === 'trace') {
    return { preset: 'front', selected: null, lit: traceLights(model, step), job: null };
  }
  return stopView(model, step);
}

/** What a step highlights on the map, in words: for those who cannot see it. Parts are
 *  named where the step names them, else their module. */
export function highlighted(model, shown) {
  const names = new Map([
    ...model.modules.flatMap((m) => [[m.id, `${m.id} ${m.short}`],
      ...m.submodules.map((s) => [s.id, `${s.id} ${s.name}`])]),
    ...model.stores.map((s) => [s.id, s.name]),
    ...(model.externals ?? []).map((e) => [e.id, e.name]),
  ]);
  const { lit, selected } = shown;
  const ids = selected ? [selected] : !lit ? [] : [
    ...[...lit.modules].flatMap((id) => {
      const parts = [...lit.parts].filter((part) => moduleOf(part) === id);
      return parts.length ? parts : [id];
    }),
    ...lit.stores, ...lit.externals];
  return ids.map((id) => names.get(id) ?? id);
}

// -- the ring ---------------------------------------------------------------------------

export const TRACKS = {
  daily: { offset: 0, name: 'Daily' },
  weekly: { offset: 3.6, name: 'Weekly' },
  calendar: { offset: 7.2, name: 'Monthly and yearly' },
};
export const BEAD = 0.5;
const MARGIN = 3.5;

/** Three flat circles in the base frame's plane, around every module and store: a clock
 *  face with the product on it. */
export function clockRing(world) {
  const corners = [...world.modules, ...world.stores].flatMap((i) => [-1, 1].flatMap((sx) => [
    -1, 1].map((sz) => [i.pos[0] + (sx * i.size[0]) / 2, i.pos[2] + (sz * i.size[2]) / 2])));
  const middle = (values) => (Math.min(...values) + Math.max(...values)) / 2;
  const centre = [middle(corners.map((c) => c[0])), LEVEL.base - 1.2,
    middle(corners.map((c) => c[1]))];
  const reach = Math.max(...corners.map(([x, z]) => Math.hypot(x - centre[0], z - centre[2])));
  return { centre, radius: reach + MARGIN };
}

/** A point of a track: 00:00 at the back, running clockwise as seen from above. `out`
 *  moves it further from the centre. */
export function ringPoint(ring, minutes, group, out = 0) {
  const angle = (minutes / DAY) * Math.PI * 2;
  const radius = ring.radius + TRACKS[group].offset + out;
  return [ring.centre[0] + radius * Math.sin(angle), ring.centre[1],
    ring.centre[2] - radius * Math.cos(angle)];
}

/** One bead for each moment, on its track. Jobs at the same or nearly the same time would
 *  cover each other, so a later one steps outwards until it touches none. */
export function beads(ring, list) {
  const placed = [];
  list.forEach((moment, index) => {
    const minutes = moment.minutes ?? 0;
    const group = TRACKS[moment.job.schedule.group] ? moment.job.schedule.group : 'calendar';
    const touches = (pos) => placed.some((other) => Math.hypot(pos[0] - other.pos[0],
      pos[2] - other.pos[2]) < BEAD * 2.2);
    let out = 0;
    while (out < 6 && touches(ringPoint(ring, minutes, group, out))) out += BEAD * 2.4;
    placed.push({ ...moment, index, group, minutes,
      pos: ringPoint(ring, minutes, group, out) });
  });
  return placed;
}

/** The box the clock view frames: the world's blocks and the outer ring. */
export function clockBounds(world, ring) {
  const outer = Array.from({ length: 48 }, (_, i) => ringPoint(ring, (i * DAY) / 48, 'calendar', 1));
  const blocks = [...world.modules, ...world.stores].flatMap((item) => [
    item.pos.map((v, i) => v - item.size[i] / 2), item.pos.map((v, i) => v + item.size[i] / 2)]);
  return boundsOf([...outer, ...blocks]);
}
