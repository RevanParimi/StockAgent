import { useEffect, useRef } from 'react';
import { formatHash, settingOf } from '../lib/select.js';
import { daysOf, zoneOf } from '../lib/play.js';
import { moduleColour, nodeOf } from '../theme.js';

const Code = ({ children }) => <code translate="no">{children}</code>;

/** The switches that decide whether the scheduler registers the job at all; a gate the
 *  code reads negated is written `not <key>`. */
function Gates({ model, job }) {
  if (!job.gates.length) {
    return <p className="empty">No switch gates it: the scheduler always registers it.</p>;
  }
  return (
    <ul className="rows gates">
      {job.gates.map((gate) => {
        const off = gate.startsWith('not ');
        const setting = settingOf(model, off ? gate.slice(4) : gate);
        return (
          <li key={gate}>
            <span className="how">{off ? 'only off' : 'only on'}</span>
            <span>
              <Code>{setting.key}</Code>
              <span className="sub">Repository default <Code>{setting.value}</Code></span>
              {setting.production ? (
                <span className="sub">Production <Code>{setting.production.value}</Code>,{' '}
                  {setting.production.source}, as of {setting.production.as_of}</span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** What the clock shows beside the world: the job at this time, how it is triggered and
 *  gated, what it lights, and every time of the day as a button. */
export default function ClockPanel({
  model, moments, step, names, audience, onOpen, onMoment, onClose,
}) {
  const { job, time } = moments[step];
  const developer = audience === 'developer';
  const list = useRef(null);
  // The list follows the hand, inside itself: the page and the panel stay where they are.
  useEffect(() => {
    const box = list.current;
    const row = box?.querySelector('[aria-current="true"]');
    if (!box || !row) return;
    const top = row.offsetTop;      // from the list, which is the row's offset parent
    if (top < box.scrollTop || top + row.offsetHeight > box.scrollTop + box.clientHeight) {
      box.scrollTop = top - box.clientHeight / 2;
    }
  }, [step]);
  const name = (who) => names.get(nodeOf(who)) ?? who;
  const store = (id) => model.stores.find((s) => s.id === id)?.name ?? id;
  const parts = new Map(model.modules.flatMap((m) => [[m.id, m.short],
    ...m.submodules.map((s) => [s.id, s.name])]));
  const flows = (job.flows ?? []).map((key) => {
    const [from, to] = key.split('>');
    return { key, from, to, what: model.flows.find((f) => f.from === from && f.to === to)?.what };
  });
  return (
    <aside className="panel" aria-label="The job on the clock" data-panel="clock">
      <div className="panel-head">
        <div className="panel-title">
          <span className="swatch" style={{ background: moduleColour(job.module) }}
            aria-hidden="true" />
          <h2><span className="tabular">{time}</span> · {job.name}</h2>
        </div>
        <div className="panel-actions">
          <button type="button" onClick={onClose}>Close the clock ✕</button>
        </div>
      </div>
      <p className="summary">{job.does.replace(/\s*─►\s*/g, ' → ')}</p>

      <section>
        <h3>Trigger</h3>
        <p className="tabular">{daysOf(job)} at {job.schedule.time} {zoneOf(job)}</p>
        {developer ? (
          <p className="sub">
            <Code>{job.id}</Code>{' '}<Code>{job.handler}</Code>{' '}
            <Code>{Object.entries(job.cron).map(([k, v]) => `${k}=${v}`).join(' ')}</Code>
          </p>
        ) : null}
      </section>
      <section>
        <h3>Gate switches</h3>
        <Gates model={model} job={job} />
      </section>
      <section>
        <h3>What lights up</h3>
        <ul className="rows lights">
          {(job.lights ?? []).map((id) => (
            <li key={id}>
              <span className="how">{id.startsWith('S.') ? 'store'
                : id.startsWith('ext.') ? 'outside' : id}</span>
              <span>
                {parts.has(id) ? (
                  <a href={formatHash({ id, audience })}
                    onClick={(e) => {
                      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                      e.preventDefault();
                      onOpen(id);
                    }}>{parts.get(id)}</a>
                ) : <strong>{id.startsWith('S.') ? store(id) : name(id)}</strong>}
              </span>
            </li>
          ))}
        </ul>
        {flows.length ? (
          <ul className="rows">
            {flows.map((f) => (
              <li key={f.key}>
                <span className="how">flow</span>
                <span><strong>{name(f.from)} → {name(f.to)}</strong>
                  <span className="sub">{f.what}</span></span>
              </li>
            ))}
          </ul>
        ) : <p className="empty">Nothing flows to another module while it runs.</p>}
        <p className="empty">What a run can reach: a switch inside the job, a quiet day or nothing
          to do can stop it earlier.</p>
      </section>
      <section>
        <h3>The whole day</h3>
        <ol className="day" ref={list}>
          {moments.map((m, i) => (
            <li key={m.key}>
              <button type="button" aria-current={i === step ? 'true' : undefined}
                data-moment={m.key} onClick={() => onMoment(i)}>
                <span className="tabular">{m.time}</span>
                <span>{m.job.name}<span className="sub">{daysOf(m.job)}</span></span>
              </button>
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}
