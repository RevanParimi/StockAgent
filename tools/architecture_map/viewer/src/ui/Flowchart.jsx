import { useEffect, useMemo, useRef, useState } from 'react';
import { buildFlow, outline } from '../lib/flow.js';
import { TEXT, layoutFlow } from '../elk.js';
import { SURFACE } from '../theme.js';

const KIND_WORD = { start: 'Start', step: 'Step', decision: 'Decision', end: 'Outcome',
  list: 'Details' };
const FLOOR = 0.75; // the smallest the fit goes: below it the text is unreadable, so it scrolls

function shape(node) {
  const { width: w, height: h, kind } = node;
  if (kind === 'decision') {
    const p = Math.min(18, h / 2);
    return <polygon points={`0,${h / 2} ${p},0 ${w - p},0 ${w},${h / 2} ${w - p},${h} ${p},${h}`} />;
  }
  const radius = kind === 'step' || kind === 'list' ? 6 : h / 2;
  return <rect width={w} height={h} rx={radius} ry={radius} />;
}

function ListText({ node }) {
  let y = 9 + TEXT.line / 2;
  return (
    <text dominantBaseline="central">
      {node.rows.map((row, i) => {
        if (row.first && i > 0) y += 4;
        const at = y;
        y += TEXT.line;
        return (
          <tspan key={`${node.id}-${i}`} x={14} y={at}>
            {row.first ? '• ' : ''}
            <tspan x={14 + TEXT.bullet}>{row.text}</tspan>
          </tspan>
        );
      })}
    </text>
  );
}

function Node({ node, colour }) {
  const stroke = node.kind === 'start' ? colour : SURFACE.edge;
  const first = node.height / 2 - ((node.lines.length - 1) * TEXT.line) / 2;
  return (
    <g className={`node node-${node.kind}`} transform={`translate(${node.x},${node.y})`}
      data-kind={node.kind} data-node={node.id}>
      <title>{`${KIND_WORD[node.kind]}: ${node.text}`}</title>
      <g fill={node.kind === 'end' ? SURFACE.raised : SURFACE.node} stroke={stroke}
        strokeWidth={node.kind === 'start' ? 2 : node.kind === 'step' || node.kind === 'list' ? 1 : 1.5}
        strokeDasharray={node.kind === 'list' ? '5 3' : undefined}>
        {shape(node)}
      </g>
      {node.kind === 'list' ? <ListText node={node} /> : (
        <text textAnchor="middle" dominantBaseline="central">
          {node.lines.map((line, i) => (
            <tspan key={`${node.id}-${i}`} x={node.width / 2} y={first + i * TEXT.line}>{line}</tspan>
          ))}
        </text>
      )}
    </g>
  );
}

function Edge({ edge, marker }) {
  if (!edge.points.length) return null;
  const d = edge.points.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' ');
  const at = edge.labelAt;
  return (
    <g className={`edge edge-${edge.type}`} data-edge={edge.type} data-from={edge.from}
      data-to={edge.to} data-label={edge.label}>
      <path d={d} fill="none" stroke={SURFACE.edge}
        strokeWidth={edge.type === 'then' ? 1.5 : 1}
        strokeOpacity={edge.type === 'then' ? 1 : 0.75} markerEnd={`url(#${marker})`} />
      {edge.label && at ? (
        <>
          <rect x={at.x - 2} y={at.y - 1} width={at.width + 4} height={at.height + 2} rx="3"
            fill={SURFACE.panel} />
          <text className={edge.label === 'yes' ? 'edge-label yes' : 'edge-label'}
            x={at.x + at.width / 2} y={at.y + at.height / 2} textAnchor="middle"
            dominantBaseline="central">{edge.label}</text>
        </>
      ) : null}
    </g>
  );
}

function Outline({ items }) {
  return (
    <ul>
      {items.map((item, i) => (
        <li key={`${i}-${item.text}`}>
          {item.text}
          {item.children.length ? <Outline items={item.children} /> : null}
        </li>
      ))}
    </ul>
  );
}

/** One part's logic as flowcharts, one for each tree, with the same trees as text. */
export default function Flowchart({ id, roots, colour }) {
  const graphs = useMemo(() => buildFlow(roots), [roots]);
  const [laid, setLaid] = useState(null);
  const [failed, setFailed] = useState('');
  const [zoom, setZoom] = useState('fit');
  const [room, setRoom] = useState(520);
  const box = useRef(null);

  useEffect(() => {
    let live = true;
    setLaid(null);
    setFailed('');
    setZoom('fit');
    layoutFlow(graphs).then(
      (result) => { if (live) setLaid({ id, result }); },
      (error) => { if (live) setFailed(String(error?.message ?? error)); },
    );
    return () => { live = false; };
  }, [graphs, id]);

  useEffect(() => {
    if (!box.current) return undefined;
    const watch = new ResizeObserver(([entry]) => setRoom(entry.contentRect.width));
    watch.observe(box.current);
    return () => watch.disconnect();
  }, []);

  const widest = laid ? Math.max(...laid.result.map((g) => g.width)) : 0;
  const fit = widest ? Math.min(1, Math.max(FLOOR, room / widest)) : 1;
  const scale = zoom === 'fit' ? fit : zoom;
  const ready = Boolean(laid && laid.id === id);

  // A chart wider than the panel opens on its start, not on its left edge; once, so a
  // zoom or a resize leaves the place the reader scrolled to.
  const centred = useRef(null);
  useEffect(() => {
    if (!ready || !box.current || centred.current === laid) return;
    centred.current = laid;
    const start = laid.result[0].nodes[0];
    box.current.scrollLeft = Math.max(0, (start.x + start.width / 2) * scale - room / 2);
  }, [ready, laid, scale, room]);

  return (
    <div className="flowchart" data-flowchart={id} data-ready={ready ? 'true' : 'false'}>
      <div className="flow-tools" role="group" aria-label="Flowchart size">
        <button type="button" onClick={() => setZoom(Math.max(0.4, scale / 1.2))}
          aria-label="Smaller">−</button>
        <button type="button" onClick={() => setZoom(Math.min(2.5, scale * 1.2))}
          aria-label="Larger">+</button>
        <button type="button" onClick={() => setZoom('fit')} aria-pressed={zoom === 'fit'}>Fit</button>
        <button type="button" onClick={() => setZoom(1)} aria-pressed={zoom === 1}>100%</button>
      </div>
      <p className="sr-only" role="status">{ready ? 'Flowchart drawn.' : 'Drawing the flowchart…'}</p>
      <div className="flow-scroll" ref={box} tabIndex={0} role="region"
        aria-label={`Flowchart of ${id}`}>
        {failed ? (
          <p className="notice">The flowchart could not be drawn ({failed}). The outline below holds
            the same logic.</p>
        ) : null}
        {!ready && !failed ? <p className="loading">Drawing the flowchart…</p> : null}
        {ready ? laid.result.map((g, i) => (
          <svg key={`${id}-${i}`} width={Math.ceil(g.width * scale)}
            height={Math.ceil(g.height * scale)} viewBox={`0 0 ${g.width} ${g.height}`}
            aria-hidden="true" data-graph={i} translate="no">
            <defs>
              <marker id={`arrow-${id}-${i}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7"
                markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill={SURFACE.edge} />
              </marker>
            </defs>
            {g.edges.map((e) => <Edge key={e.id} edge={e} marker={`arrow-${id}-${i}`} />)}
            {g.nodes.map((n) => <Node key={n.id} node={n} colour={colour} />)}
          </svg>
        )) : null}
      </div>
      <details className="outline" open={Boolean(failed)}>
        <summary>Read it as an outline</summary>
        <Outline items={outline(roots)} />
      </details>
    </div>
  );
}
