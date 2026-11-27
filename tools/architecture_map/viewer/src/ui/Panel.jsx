import { forwardRef } from 'react';
import {
  flowsFor, formatHash, jobsFor, routesFor, settingsFor, storesFor,
} from '../lib/select.js';
import { arrows } from '../lib/flow.js';
import { moduleColour } from '../theme.js';
import Flowchart from './Flowchart.jsx';

const PartLink = ({ id, audience, onSelect, children }) => (
  <a href={formatHash({ id, audience }) || '#'}
    onClick={(e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      onSelect(id);
    }}>{children}</a>
);

export const Code = ({ children }) => <code translate="no">{children}</code>;

/** A link to a place of the code galaxy: a module, a part, the shared files or a file. */
export const GalaxyLink = ({ id, file, onGo, children }) => (
  <a href={formatHash({ id, file, code: true, audience: 'developer' })}
    onClick={(e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      onGo();
    }}>{children}</a>
);

export function Section({ title, children, empty }) {
  return (
    <section>
      <h3>{title}</h3>
      {empty ? <p className="empty">{empty}</p> : children}
    </section>
  );
}

function Stores({ model, id, developer }) {
  const { writes, reads } = storesFor(model, id);
  const row = (s, how) => (
    <li key={`${how}-${s.id}`}>
      <span className="how">{how}</span>
      <span>
        <strong>{s.name}</strong>
        <span className="sub">{s.holds}</span>
        {developer ? <Code>{s.path}</Code> : null}
      </span>
    </li>
  );
  return (
    <Section title="What it stores and reads"
      empty={!writes.length && !reads.length ? 'It keeps nothing of its own and reads no store.' : null}>
      <ul className="rows">{writes.map((s) => row(s, 'writes'))}{reads.map((s) => row(s, 'reads'))}</ul>
    </Section>
  );
}

function Jobs({ model, id, developer }) {
  const jobs = jobsFor(model, id);
  return (
    <Section title="Scheduled jobs" empty={!jobs.length ? 'No scheduled job runs it directly.' : null}>
      <ul className="rows">
        {jobs.map((j) => (
          <li key={j.id}>
            <span className="how tabular">{j.schedule.when} {j.schedule.time}</span>
            <span>
              <strong>{j.name}</strong>
              <span className="sub">{j.does}</span>
              {developer ? (
                <span className="sub">
                  <Code>{j.id}</Code>{' '}<Code>{j.handler}</Code>
                  {j.gates.length ? <> gated by {j.gates.map((g) => (
                    <Code key={g}>{g}</Code>))}</> : null}
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function FlowList({ model, id, audience, onSelect }) {
  const { into, out } = flowsFor(model, id);
  const row = (f, way) => (
    <li key={`${way}-${f.key}`}>
      <span className="how">{way}</span>
      <span>
        {f.otherId.startsWith('ext.')
          ? <strong>{f.other}</strong>
          : <PartLink id={f.otherId} audience={audience} onSelect={onSelect}>{f.other}</PartLink>}
        <span className="sub">{f.what}</span>
      </span>
    </li>
  );
  return (
    <Section title={id.includes('.') ? `Flows of its module, ${id.split('.')[0]}` : 'Flows in and out'}
      empty={!into.length && !out.length ? 'No flow is drawn to or from it.' : null}>
      <ul className="rows">{into.map((f) => row(f, 'from'))}{out.map((f) => row(f, 'to'))}</ul>
    </Section>
  );
}

function Settings({ model, sub }) {
  const settings = settingsFor(model, sub);
  return (
    <Section title="Settings it reads" empty={!settings.length ? 'It reads no switch the map tracks.' : null}>
      <div className="table-wrap">
        <table>
          <thead><tr><th scope="col">Setting</th><th scope="col">Repository default</th>
            <th scope="col">Production</th></tr></thead>
          <tbody>
            {settings.map((s) => (
              <tr key={s.key}>
                <th scope="row"><Code>{s.key}</Code>{s.env ? <span className="sub"><Code>{s.env}</Code></span> : null}</th>
                <td><Code>{s.value}</Code><span className="sub">{s.source}</span></td>
                <td>
                  {s.production ? (
                    <>
                      <Code>{s.production.value}</Code>
                      <span className="sub">{s.production.source}, as of {s.production.as_of}.
                        {s.production.note ? ` ${s.production.note}` : ''}</span>
                    </>
                  ) : <span className="empty">not cited in KT section 1</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function CodeAndFiles({ model, sub, onFile }) {
  const routes = routesFor(model, sub.id);
  return (
    <>
      <Section title="Where it lives" empty={!sub.files.length ? 'No file is listed.' : null}>
        <ul className="paths">{sub.python_files.map((f) => (
          <li key={f}><GalaxyLink file={f} onGo={() => onFile(f)}><Code>{f}</Code></GalaxyLink></li>
        ))}
          {sub.files.filter((f) => !f.endsWith('.py')).map((f) => <li key={f}><Code>{f}</Code></li>)}</ul>
      </Section>
      <Section title="Functions" empty={!sub.code.length ? 'No function is listed.' : null}>
        <ul className="paths">{sub.code.map((c) => <li key={c}><Code>{c}</Code></li>)}</ul>
      </Section>
      {routes.length ? (
        <Section title="API routes">
          <ul className="paths">{routes.map((r) => (
            <li key={`${r.method} ${r.path}`}><Code>{r.method} {r.path}</Code></li>
          ))}</ul>
        </Section>
      ) : null}
    </>
  );
}

const Panel = forwardRef(function Panel({
  model, part, audience, wide, onWide, onClose, onSelect, onCode, onFile,
}, ref) {
  const { module, sub } = part;
  const developer = audience === 'developer';
  const id = sub ? sub.id : module.id;
  const colour = moduleColour(module.id);
  return (
    <aside className="panel" aria-label={`Details of ${id}`} data-panel={id}>
      <div className="panel-head">
        <div className="panel-title">
          <span className="swatch" style={{ background: colour }} aria-hidden="true" />
          <h2 ref={ref} tabIndex={-1}>{id} {sub ? sub.name : module.name}</h2>
        </div>
        <div className="panel-actions">
          <button type="button" onClick={onWide} aria-pressed={wide}>Wider panel</button>
          <button type="button" onClick={onClose} aria-label="Close the panel">Close ✕</button>
        </div>
        {sub ? (
          <p className="crumb">
            <PartLink id={module.id} audience={audience} onSelect={onSelect}>
              ← {module.id} {module.short}</PartLink>
          </p>
        ) : null}
      </div>
      <p className="summary">{arrows(sub ? sub.summary : module.summary)}</p>
      {developer ? (
        <p className="to-code">
          <GalaxyLink id={id} onGo={() => onCode(id)}>Show its code in the galaxy</GalaxyLink>
        </p>
      ) : null}

      {sub ? (
        <Section title="How it decides">
          <Flowchart key={sub.id} id={sub.id} roots={sub.logic} colour={colour} />
        </Section>
      ) : null}

      <nav aria-label="Parts" className="parts">
        <h3>{sub ? 'Other parts' : 'Its parts'}</h3>
        <ul>
          {module.submodules.map((s) => (
            <li key={s.id}>
              <PartLink id={s.id} audience={audience} onSelect={onSelect}>
                <span className="part-id">{s.id}</span> {s.name}
              </PartLink>
              {!sub ? <span className="sub">{arrows(s.summary)}</span> : null}
              {sub && s.id === sub.id ? <span className="here">shown above</span> : null}
            </li>
          ))}
        </ul>
      </nav>

      {sub && developer ? (
        <>
          <Settings model={model} sub={sub} />
          <CodeAndFiles model={model} sub={sub} onFile={onFile} />
        </>
      ) : null}
      <Stores model={model} id={id} developer={developer} />
      <Jobs model={model} id={id} developer={developer} />
      <FlowList model={model} id={id} audience={audience} onSelect={onSelect} />
    </aside>
  );
});

export default Panel;
