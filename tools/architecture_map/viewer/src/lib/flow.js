// A logic tree from the model as a flowchart: boxes and arrows. Pure functions.
// The model's marks (tree.py): `kind` decision or end, `ends` (a decision whose result
// ends the path) and `then` (this follows the node above it, not the parent).

export const ARROW = '─►';
const SHORT_LABEL = 24;

/** Three dots standing alone are the sentence's ellipsis ("STRONG BUY … STRONG SELL");
 *  inside code (`fallback=...`) they stay as written. */
export const prose = (text) => String(text).replace(/(^|\s)\.{3}(?=\s|$)/g, '$1…');

/** One line of prose from a node's text: continuation lines joined, dot leaders made a dash. */
export function cleanText(text) {
  return prose(text)
    .replace(/\s*\n\s*/g, ' ')
    // a dot leader (one, two or four or more dots between spaces) lines TREES.md up; a chart
    // needs a dash
    .replace(/\s+(\.{1,2}|\.{4,})\s+/g, ' — ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function splitArrow(text) {
  const at = text.indexOf(ARROW);
  if (at < 0) return null;
  const before = text.slice(0, at).trim();
  const after = text.slice(at + ARROW.length).trim();
  return before && after ? { before, after } : null;
}

const isYes = (text) => /^yes\s*─►/.test(cleanText(text));

// A decision whose "yes" side stops there: what comes after it is the "no" path.
function hasEndingYes(node) {
  return Boolean(node.ends)
    || (node.children ?? []).some((c) => c.kind === 'end' && isYes(c.text));
}

// A child that is only a line of detail: no mark, no parts of its own, nothing follows
// it, and (under a decision) not a branch whose label belongs on an arrow.
function isDetail(children, i, parent) {
  const child = children[i];
  if (child.kind || child.then || (child.children ?? []).length) return false;
  if (children[i + 1]?.then) return false;
  if (parent.kind === 'decision') {
    const parts = splitArrow(cleanText(child.text));
    if (parts && parts.before.length <= SHORT_LABEL) return false;
  }
  return true;
}

/** One graph per root: `{nodes: [{id, kind, text, items}], edges: [...]}`.
 *  kind is start, step, decision, end or list (detail lines in one box, with `items`: two
 *  or more, or under a decision even one); an edge's type is "then" (the order things
 *  happen) or "part" (belongs to, or is a branch of). Under a decision every "part" arrow
 *  to a box that is not a list carries its condition. */
export function buildFlow(roots) {
  return roots.map((root, index) => {
    const nodes = [];
    const edges = [];
    const addNode = (kind, text, extra = {}) => {
      const id = `r${index}n${nodes.length}`;
      nodes.push({ id, kind, text, ...extra });
      return id;
    };
    const addEdge = (from, to, type, label = '') => {
      edges.push({ id: `${from}-${to}`, from, to, type, label });
    };

    // `incoming` says how this node is reached: {from, type, label}.
    const walk = (node, incoming, parent) => {
      const text = cleanText(node.text);
      let label = incoming?.label ?? '';
      let shown = text;
      const kind = node.kind ?? (incoming ? 'step' : 'start');
      // A branch of a decision written "label ─► result" shows the label on its arrow.
      if (incoming?.type === 'part' && parent?.kind === 'decision' && kind !== 'decision') {
        const parts = splitArrow(text);
        if (parts && parts.before.length <= SHORT_LABEL) {
          label = parts.before;
          shown = parts.after;
        }
      }
      let result = null;
      let body = shown;
      if (kind === 'decision') {
        const parts = splitArrow(shown);
        if (parts) {
          body = parts.before;
          result = parts.after;
        }
      }
      const id = addNode(kind, body);
      if (incoming) addEdge(incoming.from, id, incoming.type, label);
      if (result !== null) {
        const outcome = addNode(node.ends ? 'end' : 'step', result);
        addEdge(id, outcome, 'part', 'yes');
      }
      let previous = null;
      const children = node.children ?? [];
      for (let i = 0; i < children.length; i += 1) {
        const child = children[i];
        let run = i;
        while (run < children.length && isDetail(children, run, node)) run += 1;
        // under a decision even one line of detail gets the list box: a plain box there
        // would read as one more branch
        if (run - i >= (node.kind === 'decision' ? 1 : 2)) {
          const items = children.slice(i, run).map((c) => cleanText(c.text));
          addEdge(id, addNode('list', items.join('; '), { items }), 'part');
          previous = null;
          i = run - 1;
          continue;
        }
        if (child.then && previous) {
          const refused = previous.node.kind === 'decision'
            && (hasEndingYes(previous.node) || /^else\b/.test(cleanText(child.text)));
          previous = { node: child,
            id: walk(child, { from: previous.id, type: 'then', label: refused ? 'no' : '' }, node) };
        } else {
          previous = { node: child, id: walk(child, { from: id, type: 'part' }, node) };
        }
      }
      return id;
    };

    walk(root, null, null);
    return { nodes, edges, sequential: edges.some((e) => e.type === 'then') };
  });
}


/** The tree as nested text, for the outline beside the flowchart and screen readers. */
export function outline(nodes) {
  return nodes.map((n) => ({ text: cleanText(n.text), children: outline(n.children ?? []) }));
}
