import { useEffect, useMemo, useRef, useState } from 'react';
import { search } from '../lib/select.js';

/** A native modal dialog: focus stays inside, Esc closes it, focus returns after. */
function Modal({ open, onClose, labelledBy, className, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog ref={ref} className={className} aria-labelledby={labelledBy} onClose={onClose}
      onClick={(e) => { if (e.target === ref.current) onClose(); }}>
      <div className="dialog-body">{children}</div>
    </dialog>
  );
}

const KIND_WORD = { module: 'Module', part: 'Part', store: 'Store', job: 'Job',
  setting: 'Setting', function: 'Function', file: 'File' };

export function SearchDialog({ open, index, onClose, onPick }) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const input = useRef(null);
  const results = useMemo(() => search(index, query), [index, query]);

  useEffect(() => {
    // Emptied on closing, so it opens empty: Esc in a search field that still holds
    // text clears the field and leaves the dialog open.
    if (open) input.current?.focus();
    else { setQuery(''); setActive(0); }
  }, [open]);

  const move = (to) => {
    if (!results.length) return;
    const next = (to + results.length) % results.length;
    setActive(next);
    document.getElementById(`result-${next}`)?.scrollIntoView({ block: 'nearest' });
  };

  const keys = (event) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); move(active + 1); }
    if (event.key === 'ArrowUp') { event.preventDefault(); move(active - 1); }
    if (event.key === 'Enter') {
      event.preventDefault();
      if (results[active]) onPick(results[active]);
    }
  };

  return (
    <Modal open={open} onClose={onClose} labelledBy="search-title" className="search">
      <h2 id="search-title">Search the map</h2>
      <label htmlFor="search-input">Module, part, store, job, setting, function or file</label>
      <input ref={input} id="search-input" type="search" name="map-search" value={query}
        placeholder="Try advisor or entry band…" autoComplete="off" spellCheck={false}
        role="combobox" aria-expanded={results.length > 0} aria-controls="search-results"
        aria-activedescendant={results[active] ? `result-${active}` : undefined}
        onChange={(e) => { setQuery(e.target.value); setActive(0); }} onKeyDown={keys} />
      <p className="sr-only" role="status">
        {query ? `${results.length} result${results.length === 1 ? '' : 's'}.` : ''}
      </p>
      <ul id="search-results" role="listbox" aria-label="Results">
        {results.map((item, i) => (
          <li key={`${item.kind}-${item.id}-${item.title}`} id={`result-${i}`} role="option"
            aria-selected={i === active} onMouseMove={() => setActive(i)}
            onClick={() => onPick(item)} onKeyDown={() => {}}>
            <span className="kind">{KIND_WORD[item.kind]}</span>
            <span><strong translate="no">{item.title}</strong>
              <span className="sub">{item.id} · {item.detail}</span></span>
          </li>
        ))}
      </ul>
      {query && !results.length ? <p className="empty">Nothing holds “{query}”. Try a shorter word.</p> : null}
      <button type="button" onClick={onClose}>Close</button>
    </Modal>
  );
}

const KEYS = [
  ['1', 'Front view: how a stock becomes a verdict, then a trade'],
  ['2', 'Top view: the modules and their neighbours'],
  ['3', 'Side view: what people see, what decides, what is stored'],
  ['4', 'Below view: which module writes which file'],
  ['R', 'Reset the view'],
  ['/', 'Search'],
  ['P', 'Pause or resume motion'],
  ['← → ↑ ↓', 'Turn the 3D view (when it has the focus)'],
  ['+ −', 'Zoom the 3D view (when it has the focus)'],
  ['Shift + arrows', 'Move the 3D view sideways (when it has the focus)'],
  ['Esc', 'Close the dialog, then the panel'],
  ['?', 'This list'],
];

export function HelpDialog({ open, onClose }) {
  return (
    <Modal open={open} onClose={onClose} labelledBy="help-title" className="help">
      <h2 id="help-title">Keys and mouse</h2>
      <table>
        <tbody>
          {KEYS.map(([key, what]) => (
            <tr key={key}><th scope="row"><kbd>{key}</kbd></th><td>{what}</td></tr>
          ))}
        </tbody>
      </table>
      <p>Click a block or choose a module in the legend to open it. Drag to turn the view, scroll to
        zoom, drag with the right button to move it. Point at a flow to read what travels on it; the
        panel lists the same flows.</p>
      <button type="button" onClick={onClose}>Close</button>
    </Modal>
  );
}
