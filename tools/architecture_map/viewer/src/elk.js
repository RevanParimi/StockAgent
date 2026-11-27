// Lays out a flowchart with ELK: box sizes from the measured text, then positions.
import ELK from 'elkjs/lib/elk.bundled.js';

const elk = new ELK();

export const TEXT = { font: '13px ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif',
  line: 18, maxWidth: 236, listWidth: 300, bullet: 14 };
const LABEL_FONT = '12px ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif';
const PAD = { x: 14, y: 9, point: 18 }; // `point` is the extra width of a decision's ends

let context = null;
function widthOf(text, font) {
  context ??= document.createElement('canvas').getContext('2d');
  context.font = font;
  return context.measureText(text).width;
}

/** Words into lines no wider than the box; a word longer than a line (a path) is cut. */
export function wrap(text, maxWidth, measure) {
  const lines = [];
  let line = '';
  const push = () => { if (line) lines.push(line); line = ''; };
  for (let word of String(text).split(/\s+/).filter(Boolean)) {
    if (measure(line ? `${line} ${word}` : word) <= maxWidth) {
      line = line ? `${line} ${word}` : word;
      continue;
    }
    push();
    while (measure(word) > maxWidth && word.length > 1) {
      let cut = word.length - 1;
      while (cut > 1 && measure(word.slice(0, cut)) > maxWidth) cut -= 1;
      lines.push(word.slice(0, cut));
      word = word.slice(cut);
    }
    line = word;
  }
  push();
  return lines.length ? lines : [''];
}

function sized(node) {
  const measure = (t) => widthOf(t, TEXT.font);
  if (node.kind === 'list') {
    // each item wraps on its own; `bullet` marks the first line of each
    const rows = node.items.flatMap((item) => wrap(item, TEXT.listWidth, measure)
      .map((text, i) => ({ text, first: i === 0 })));
    const textWidth = Math.max(...rows.map((r) => measure(r.text)));
    return {
      ...node, rows, lines: rows.map((r) => r.text),
      width: Math.ceil(textWidth + TEXT.bullet + PAD.x * 2),
      height: Math.ceil(rows.length * TEXT.line + (node.items.length - 1) * 4 + PAD.y * 2),
    };
  }
  const lines = wrap(node.text, TEXT.maxWidth, measure);
  const textWidth = Math.max(...lines.map(measure));
  const ends = node.kind === 'decision' ? PAD.point * 2 : node.kind === 'step' ? 0 : 8;
  return {
    ...node, lines,
    width: Math.ceil(textWidth + PAD.x * 2 + ends),
    height: Math.ceil(lines.length * TEXT.line + PAD.y * 2),
  };
}

const OPTIONS = {
  'elk.algorithm': 'layered',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
  'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
  'elk.layered.nodePlacement.favorStraightEdges': 'true',
  'elk.spacing.nodeNode': '14',
  'elk.spacing.edgeNode': '14',
  'elk.layered.spacing.nodeNodeBetweenLayers': '34',
  'elk.padding': '[top=6,left=6,bottom=6,right=6]',
};

async function layoutOne(graph) {
  const nodes = graph.nodes.map(sized);
  const labels = (edge) => (edge.label
    ? [{ id: `${edge.id}-label`, text: edge.label,
      width: Math.ceil(widthOf(edge.label, LABEL_FONT)) + 6, height: 15 }]
    : []);
  const result = await elk.layout({
    id: 'root',
    layoutOptions: { ...OPTIONS, 'elk.direction': graph.sequential ? 'DOWN' : 'RIGHT' },
    children: nodes.map((n) => ({ id: n.id, width: n.width, height: n.height })),
    edges: graph.edges.map((e) => ({ id: e.id, sources: [e.from], targets: [e.to],
      labels: labels(e) })),
  });
  const placed = new Map(result.children.map((c) => [c.id, c]));
  const byId = new Map(graph.edges.map((e) => [e.id, e]));
  return {
    width: Math.ceil(result.width),
    height: Math.ceil(result.height),
    nodes: nodes.map((n) => ({ ...n, x: placed.get(n.id).x, y: placed.get(n.id).y })),
    edges: result.edges.map((e) => {
      const section = e.sections?.[0];
      const points = section
        ? [section.startPoint, ...(section.bendPoints ?? []), section.endPoint]
        : [];
      return { ...byId.get(e.id), points, labelAt: e.labels?.[0] ?? null };
    }),
  };
}

/** Each tree laid out on its own; the viewer stacks them. */
export const layoutFlow = (graphs) => Promise.all(graphs.map(layoutOne));
