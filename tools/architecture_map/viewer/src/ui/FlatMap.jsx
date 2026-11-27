// The flat map: the model as one drawing, for a browser without WebGL and for a narrow
// window. Its places come from lib/flat.js; this only draws them.
import { useEffect, useRef, useState } from 'react';
import { cardLabel } from '../lib/flat.js';
import { formatHash } from '../lib/select.js';

const SMALLEST = 0.75; // the smallest the fit goes: below it the text is unreadable
const LARGEST = 1.4;
const STEP = 1.2;
const clamp = (v) => Math.min(3, Math.max(0.5, v));

const plain = (event) => !(event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0);

function Card({ model, card, state, address, onSelect }) {
  const external = card.kind === 'external';
  const text = (
    <>
      <rect className="flat-box" width={card.w} height={card.h} rx={external ? card.h / 2 : 6} />
      {external ? null : <rect className="flat-bar" width="5" height={card.h} rx="2"
        fill={card.colour} />}
      {/* one line of text for each line of the card, centred in it */}
      <text x={external ? card.w / 2 : 12} textAnchor={external ? 'middle' : 'start'}
        dominantBaseline="central">
        {card.lines.map((line, i) => (
          <tspan key={`${card.id}-${line}`} x={external ? card.w / 2 : 12}
            y={card.h / 2 + (i - (card.lines.length - 1) / 2) * 15}
            className={card.kind === 'module' && i === 0 && card.lines.length > 1
              && card.id !== 'shared' ? 'part-id' : undefined}>{line}</tspan>
        ))}
      </text>
    </>
  );
  const shared = { className: `flat-card ${card.kind} ${state}`, 'data-card': card.id,
    'data-state': state, transform: `translate(${card.x},${card.y})` };
  if (!card.select) {
    return <g {...shared} aria-label={cardLabel(model, card)} role="img">{text}</g>;
  }
  return (
    <a {...shared} href={address(card.select)} aria-label={cardLabel(model, card)}
      aria-current={state === 'selected' ? 'true' : undefined}
      onClick={(e) => {
        if (!plain(e)) return;
        e.preventDefault();
        onSelect(card.select);
      }}>
      {text}
    </a>
  );
}

/** `nudge` is the + and − keys' way of changing the size. */
export default function FlatMap({
  model, layout, states, preset, audience, code, parts, open, note, noteRole, nudge, onSelect,
}) {
  const [zoom, setZoom] = useState('fit');
  const [room, setRoom] = useState(0);
  const box = useRef(null);
  useEffect(() => {
    if (!box.current) return undefined;
    const watch = new ResizeObserver(([entry]) => setRoom(entry.contentRect.width));
    watch.observe(box.current);
    return () => watch.disconnect();
  }, []);
  const fit = room ? Math.min(LARGEST, Math.max(SMALLEST, room / layout.width)) : 1;
  const scale = zoom === 'fit' ? fit : zoom;
  // A map wider than its box shows what is chosen.
  const chosen = layout.cards.find((c) => states.cards.get(c.id) === 'selected');
  useEffect(() => {
    const view = box.current;
    if (!view || !chosen || !room) return;
    const [left, right] = [chosen.x * scale, (chosen.x + chosen.w) * scale];
    if (left < view.scrollLeft || right > view.scrollLeft + room) {
      view.scrollLeft = Math.max(0, (left + right) / 2 - room / 2);
    }
    // a new choice or size is the reason to move, not each render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosen?.id, room, scale]);
  const done = useRef(nudge);
  useEffect(() => {
    if (!nudge || done.current === nudge) return;
    done.current = nudge;
    setZoom((now) => clamp((now === 'fit' ? fit : now) * nudge.by));
  }, [fit, nudge]);

  const address = (id) => formatHash({ id, audience, code }) || '#';
  const heads = [...new Set(layout.arrows.map((a) => a.colour))];
  const cards = new Map(layout.cards.map((c) => [c.id, c]));
  return (
    <div className="flat" data-flat={layout.narrow ? 'narrow' : 'wide'} data-view-shown={preset}>
      <p className="flat-note" role={noteRole}>{note}</p>
      <div className="flat-tools" role="group" aria-label="Map size">
        <button type="button" onClick={() => setZoom(clamp(scale / STEP))}
          aria-label="Smaller">−</button>
        <button type="button" onClick={() => setZoom(clamp(scale * STEP))}
          aria-label="Larger">+</button>
        <button type="button" onClick={() => setZoom('fit')} aria-pressed={zoom === 'fit'}>Fit</button>
      </div>
      <div className="flat-scroll" ref={box} tabIndex={0} role="region"
        aria-label={code ? 'Flat map of the code: its modules and their files'
          : 'Flat map of the product'}>
        <svg width={Math.floor(layout.width * scale)} height={Math.ceil(layout.height * scale)}
          viewBox={`0 0 ${layout.width} ${layout.height}`} data-scale={scale.toFixed(2)}>
          <defs>
            {heads.map((colour) => (
              <marker key={colour} id={`flat-head-${colour.slice(1)}`} viewBox="0 0 10 10"
                refX="9" refY="5" markerWidth="7" markerHeight="7" markerUnits="userSpaceOnUse"
                orient="auto">
                <path d="M0,0 L10,5 L0,10 z" fill={colour} />
              </marker>
            ))}
          </defs>
          {layout.bands.map((b) => (
            <g key={b.id} className={`flat-band${b.frame ? ' frame' : ''}`} data-band={b.id}>
              <rect x={b.x + 1} y={b.y + 1} width={b.w - 2} height={b.h - 2} rx="8"
                stroke={b.tone} />
              {b.frame ? null : <text x={b.x + 12} y={b.y + 15}>{b.name}</text>}
              {b.frame ? <title>{b.name}</title> : null}
            </g>
          ))}
          <g aria-hidden="true">
            {layout.pipes.map((p) => {
              const level = states.pipes.get(`${p.module}>${p.store}`);
              return (
                <path key={`${p.module}>${p.store}`} className={`flat-pipe ${level}`} d={p.d}
                  stroke={p.colour} data-pipe={`${p.module}>${p.store}`} />
              );
            })}
            {layout.arrows.map((a) => {
              const level = states.arrows.get(a.key);
              const words = `${cards.get(a.from).lines.join(' ')} → ${
                cards.get(a.to).lines.join(' ')}: ${a.what}`;
              return (
                <g key={a.key} className={`flat-arrow ${level}`} data-flow={a.key}
                  data-level={level}>
                  <path d={a.d} stroke={a.colour} strokeDasharray={a.ring ? '6 4' : undefined}
                    markerEnd={`url(#flat-head-${a.colour.slice(1)})`} />
                  {/* a wider, unseen line to point at */}
                  <path d={a.d} className="flat-hit"><title>{words}</title></path>
                </g>
              );
            })}
          </g>
          {layout.cards.map((card) => (
            <Card key={card.id} model={model} card={card} state={states.cards.get(card.id)}
              address={address} onSelect={onSelect} />
          ))}
        </svg>
      </div>
      {parts ? (
        <nav className="flat-parts" aria-label={`Parts of ${parts.moduleId}`}>
          <span>Parts of {parts.moduleId}</span>
          <ul>
            {parts.data.submodules.map((s) => (
              <li key={s.id}>
                <a href={address(s.id)} aria-current={open === s.id ? 'true' : undefined}
                  data-flat-part={s.id}
                  onClick={(e) => {
                    if (!plain(e)) return;
                    e.preventDefault();
                    onSelect(s.id);
                  }}><span className="part-id">{s.id}</span> {s.name}</a>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
    </div>
  );
}
