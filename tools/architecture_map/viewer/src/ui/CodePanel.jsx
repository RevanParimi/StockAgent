// The code galaxy's panel: a chosen file, or the files of a module, a part or the shared
// ones. It is also the galaxy's text equivalent, with or without a 3D view.
import { forwardRef } from 'react';
import {
  clusterColour, clusterName, clusterOf, codeSummary, fileLabel, importingModules, ownerName,
} from '../lib/galaxy.js';
import { SHARED } from '../theme.js';
import { Code, GalaxyLink, Section } from './Panel.jsx';

const count = (n, one, many = `${one}s`) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

function Head({ title, name, cluster, back, wide, onWide, onClose, heading }) {
  return (
    <div className="panel-head">
      <div className="panel-title">
        <span className="swatch" style={{ background: clusterColour(cluster) }} aria-hidden="true" />
        <h2 ref={heading} tabIndex={-1} translate={name ? 'no' : undefined}>{title}</h2>
      </div>
      <div className="panel-actions">
        <button type="button" onClick={onWide} aria-pressed={wide}>Wider panel</button>
        <button type="button" onClick={onClose} aria-label="Close the panel">Close ✕</button>
      </div>
      {back ? <p className="crumb">{back}</p> : null}
    </div>
  );
}

function FileList({ graph, paths, onFile, detail }) {
  return (
    <ul className="files">
      {paths.map((path) => (
        <li key={path}>
          <GalaxyLink file={path} onGo={() => onFile(path)}>
            <span translate="no">{fileLabel(path)}</span>
          </GalaxyLink>
          <span className="sub"><Code>{path}</Code> · {detail(graph.byPath.get(path))}</span>
        </li>
      ))}
    </ul>
  );
}

const WorldButton = ({ id, onWorld }) => (
  <p className="to-world"><button type="button" onClick={() => onWorld(id)}>Show {id} in the world</button></p>
);

function FilePanel({ model, graph, path, onFile, onCode, onWorld, heading, ...head }) {
  const file = graph.byPath.get(path);
  const users = importingModules(graph, path);
  return (
    <aside className="panel" aria-label={`File ${path}`} data-panel="file" data-file={path}>
      <Head {...head} heading={heading} name title={fileLabel(path)} cluster={file.cluster}
        back={(
          <GalaxyLink id={file.cluster} onGo={() => onCode(file.cluster)}>
            ← {clusterName(model, file.cluster)}: its code
          </GalaxyLink>
        )} />
      <p className="summary"><Code>{path}</Code></p>
      <p className="facts">
        {count(file.lines, 'line')}.{' '}
        {file.owner === SHARED ? 'It is shared: it belongs to no one module.' : (
          <>Part of <GalaxyLink id={file.owner} onGo={() => onCode(file.owner)}>
            {ownerName(model, file.owner)}</GalaxyLink>.</>
        )}
      </p>
      {file.owner === SHARED ? null : <WorldButton id={file.owner} onWorld={onWorld} />}
      <Section title={`Imports (${file.imports.length})`}
        empty={file.imports.length ? null : 'It imports no other Python file of the repository.'}>
        <FileList graph={graph} paths={file.imports} onFile={onFile} detail={(f) => f.owner} />
      </Section>
      <Section title={`Imported by (${file.importedBy.length})`}
        empty={file.importedBy.length ? null
          : 'No Python file of the repository imports it by an import statement. It may be run '
            + 'directly, or loaded by name.'}>
        {users.length ? (
          <p className="facts">Files of {count(users.length, 'other module')} import
            {' '}it: {users.join(', ')}.</p>
        ) : null}
        <FileList graph={graph} paths={file.importedBy} onFile={onFile}
          detail={(f) => f.owner} />
      </Section>
    </aside>
  );
}

function Crossing({ model, rows, own, onCode, one }) {
  return (
    <ul className="rows">
      {rows.map(([cluster, n]) => (
        <li key={cluster}>
          <span className="how tabular">{count(n, one)}</span>
          <span>
            <GalaxyLink id={cluster} onGo={() => onCode(cluster)}>
              {clusterName(model, cluster)}</GalaxyLink>
            {cluster === own ? ', its other parts' : ''}
          </span>
        </li>
      ))}
    </ul>
  );
}

function GroupPanel({ model, graph, id, onFile, onCode, onWorld, heading, ...head }) {
  const cluster = clusterOf(id);
  const summary = codeSummary(graph, id);
  const title = id === SHARED ? 'Shared files' : `${ownerName(model, id)}: its code`;
  const isPart = id.includes('.');
  return (
    <aside className="panel" aria-label={`Code of ${ownerName(model, id)}`} data-panel="code"
      data-code={id}>
      <Head {...head} heading={heading} title={title} cluster={cluster}
        back={isPart ? (
          <GalaxyLink id={cluster} onGo={() => onCode(cluster)}>
            ← {clusterName(model, cluster)}: its code
          </GalaxyLink>
        ) : null} />
      <p className="summary">
        {summary.files.length
          ? `${count(summary.files.length, 'Python file')}, ${count(summary.lines, 'line')}.`
          : 'It has no Python file. Its other files are listed in its panel in the world.'}
        {id === SHARED ? ' They belong to no one module, so the world shows no block for them.' : ''}
      </p>
      {id === SHARED ? null : <WorldButton id={id} onWorld={onWorld} />}
      {summary.files.length ? (
        <>
          <Section title="What it imports from outside"
            empty={summary.imports.length ? null : 'It imports nothing outside itself.'}>
            <Crossing model={model} rows={summary.imports} own={isPart ? cluster : null}
              onCode={onCode} one="import" />
          </Section>
          <Section title="What imports it from outside"
            empty={summary.importedBy.length ? null : 'Nothing outside it imports it.'}>
            <Crossing model={model} rows={summary.importedBy} own={isPart ? cluster : null}
              onCode={onCode} one="import" />
          </Section>
          <Section title="Its files, largest first">
            <FileList graph={graph} paths={summary.files.map((f) => f.path)} onFile={onFile}
              detail={(f) => count(f.lines, 'line')} />
          </Section>
        </>
      ) : null}
    </aside>
  );
}

/** What the galaxy has chosen: a file wins over its part. */
const CodePanel = forwardRef(function CodePanel({ file, selected, ...props }, ref) {
  return file
    ? <FilePanel {...props} path={file} heading={ref} />
    : <GroupPanel {...props} key={selected} id={selected} heading={ref} />;
});

export default CodePanel;
