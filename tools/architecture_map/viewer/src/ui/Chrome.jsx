// The frame around the world: top bar, legend, labels and tooltip.
import { formatHash } from '../lib/select.js';
import { PRESETS } from '../lib/world.js';
import { moduleColour, nodeOf } from '../theme.js';

export function TopBar({
  model, preset, audience, motion, reduced, onPreset, onReset, onSearch, onAudience, onMotion,
  onHelp,
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
          <button key={id} type="button" onClick={() => onPreset(id)} aria-pressed={preset === id}
            title={p.asks}>{p.label} <kbd aria-hidden="true">{p.key}</kbd></button>
        ))}
        <button type="button" onClick={onReset}>Reset <kbd aria-hidden="true">R</kbd></button>
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

export function Legend({ model, selected, audience, onSelect }) {
  const current = selected ? selected.split('.')[0] : null;
  return (
    <nav id="modules" className="legend" aria-label="Modules">
      <h2>Modules</h2>
      <ul>
        {model.modules.map((m) => (
          <li key={m.id}>
            <a href={formatHash({ id: m.id, audience })} data-module={m.id}
              aria-current={current === m.id ? 'true' : undefined}
              onClick={(e) => {
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                e.preventDefault();
                onSelect(m.id);
              }}>
              <span className="swatch" style={{ background: moduleColour(m.id) }} aria-hidden="true" />
              <span className="part-id">{m.id}</span> {m.short}
            </a>
          </li>
        ))}
      </ul>
      <p className="hint">Choose a module, or click its block. Press <kbd>/</kbd> to search.</p>
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
              onMouseDown={(e) => e.preventDefault()} onClick={() => onSelect(item.select)}>
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

export function Tooltip({ hover, names }) {
  if (!hover) return null;
  const { flow, x, y } = hover;
  const name = (who) => names.get(nodeOf(who)) ?? who;
  const left = Math.min(x + 14, window.innerWidth - 340);
  return (
    <div className="tooltip" role="tooltip" style={{ left: Math.max(8, left), top: y + 14 }}>
      <strong>{name(flow.from)} → {name(flow.to)}</strong>
      <span>{flow.what}</span>
    </div>
  );
}
