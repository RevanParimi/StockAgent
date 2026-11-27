// The frame around the world: top bar, legend, labels and tooltip.
import { formatHash } from '../lib/select.js';
import { PRESETS } from '../lib/world.js';
import { MODES, stepsOf } from '../lib/play.js';
import { clusterName, clusterOf, ownerName } from '../lib/galaxy.js';
import { SHARED, SURFACE, moduleColour, nodeOf } from '../theme.js';

export function TopBar({
  model, preset, mode, code, audience, motion, reduced, onPreset, onReset, onStory, onCode,
  onSearch, onAudience, onMotion, onHelp,
}) {
  const commit = model.stamp.commit.slice(0, 7);
  return (
    <header className="topbar">
      <div className="brand">
        <h1>StockAgent architecture</h1>
        <p className="stamp">
          Code inspected: <code translate="no">{commit}</code>
          {model.stamp.uncommitted_code ? ', plus changes not in that commit' : ''}
        </p>
      </div>
      <div className="controls" role="group" aria-label="Views">
        {Object.entries(PRESETS).map(([id, p]) => (
          <button key={id} type="button" data-view={id} onClick={() => onPreset(id)}
            aria-pressed={preset === id}
            title={code && id !== 'clock' ? 'Frame the galaxy from this side' : p.asks}>
            {p.label} <kbd aria-hidden="true">{p.key}</kbd></button>
        ))}
        <button type="button" onClick={onReset}>Reset <kbd aria-hidden="true">R</kbd></button>
        {audience === 'developer' ? (
          <button type="button" data-galaxy onClick={onCode} aria-pressed={code}
            title="Every Python file and what it imports">
            Code galaxy <kbd aria-hidden="true">G</kbd></button>
        ) : null}
      </div>
      <div className="controls" role="group" aria-label="Stories">
        {[['trace', 'Trace a stock'], ['tour', 'Tour']].map(([id, label]) => (
          stepsOf(model, id).length ? (
            <button key={id} type="button" data-story={id} aria-pressed={mode === id}
              title={MODES[id].title} onClick={() => onStory(id)}>{label}</button>
          ) : null
        ))}
      </div>
      <div className="controls">
        <button type="button" onClick={onSearch} aria-haspopup="dialog">
          Search… <kbd aria-hidden="true">/</kbd></button>
        <div className="segmented" role="group" aria-label="Audience">
          {[['manager', 'Manager'], ['developer', 'Developer']].map(([id, label]) => (
            <button key={id} type="button" aria-pressed={audience === id}
              onClick={() => onAudience(id)}>{label}</button>
          ))}
        </div>
        <button type="button" onClick={onMotion} aria-pressed={!motion} disabled={reduced}
          title={reduced ? 'Your system asks for reduced motion' : undefined}>
          Pause motion <kbd aria-hidden="true">P</kbd></button>
        <button type="button" onClick={onHelp} aria-haspopup="dialog">Help <kbd aria-hidden="true">?</kbd></button>
      </div>
    </header>
  );
}

export function Legend({ model, selected, audience, code, onSelect }) {
  const current = selected ? clusterOf(selected) : null;
  // in the galaxy the shared files are a ball of their own
  const entries = [...model.modules.map((m) => ({ id: m.id, name: m.short })),
    ...(code ? [{ id: SHARED, name: 'Shared files' }] : [])];
  return (
    <nav id="modules" className="legend" aria-label="Modules">
      <h2>Modules</h2>
      <ul>
        {entries.map(({ id, name }) => (
          <li key={id}>
            <a href={formatHash({ id, audience, code })} data-module={id}
              aria-current={current === id ? 'true' : undefined}
              onClick={(e) => {
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                e.preventDefault();
                onSelect(id);
              }}>
              <span className="swatch" aria-hidden="true"
                style={{ background: id === SHARED ? SURFACE.edge : moduleColour(id) }} />
              {id === SHARED ? null : <><span className="part-id">{id}</span>{' '}</>}{name}
            </a>
          </li>
        ))}
      </ul>
      <p className="hint">
        {code ? 'Choose a module to light its files. Press ' : 'Choose a module, or click its block. Press '}
        <kbd>/</kbd>{code ? ' to find a file by name.' : ' to search.'}
      </p>
    </nav>
  );
}

/** HTML over the 3D world: it faces the viewer and stays sharp. Positioned by Projector.
 *  The legend is the keyboard way to the same places, so these are not tab stops. */
export function Labels({ items, labels, onSelect }) {
  return (
    <div className="labels" aria-hidden="true">
      {items.map((item) => (
        /* a label whose words change is a new element, so that its size is measured again */
        <div key={`${item.key}:${item.kind}:${item.text}`} className="label-anchor"
          data-label={item.key}
          ref={(el) => {
            if (el) labels.current.set(item.key, el);
            else labels.current.delete(item.key);
          }}>
          {item.select ? (
            /* a mouse press must not leave the focus on something hidden from assistive tech */
            <button type="button" tabIndex={-1} className={`label label-${item.kind} ${item.state}`}
              style={{ '--tone': item.colour }} data-target={item.select}
              translate={item.file ? 'no' : undefined}
              onMouseDown={(e) => e.preventDefault()} onClick={() => onSelect(item.select, item)}>
              {item.id ? <span className="part-id">{item.id}</span> : null} {item.text}
            </button>
          ) : (
            <span className={`label label-${item.kind} ${item.state}`} style={{ '--tone': item.colour }}>
              {item.text}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export function Tooltip({ hover, names, model }) {
  if (!hover) return null;
  const { flow, path, x, y } = hover;
  const name = (who) => names.get(nodeOf(who)) ?? who;
  const left = Math.min(x + 14, window.innerWidth - 340);
  const file = path ? model.files.find((f) => f.path === path) : null;
  return (
    <div className="tooltip" role="tooltip" style={{ left: Math.max(8, left), top: y + 14 }}>
      {file ? (
        <>
          <strong translate="no">{file.path}</strong>
          <span>{file.lines.toLocaleString('en-US')} lines · {ownerName(model, file.owner)}</span>
        </>
      ) : flow ? (
        <>
          <strong>{name(flow.from)} → {name(flow.to)}</strong>
          <span>{flow.what}</span>
        </>
      ) : null}
    </div>
  );
}
