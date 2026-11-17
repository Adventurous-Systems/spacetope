// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

/** Project the realised graph (3D coords in metres) onto the xyflow plane.
 * x -> x, y -> -y (screen down); each level gets its own panel to the right of the previous one.
 * Shafts (stairs, lifts with `serves`) are drawn once, in the panel of their first level, with edges to every
 * level they serve. Wall nodes whose two spaces share a door are marked; their edges are drawn as doors. */
const SCALE = 60; // px per metre

function wallPairs(g) {
  const neighbours = {};
  for (const [a, b] of g.edges) {
    if (g.kinds[a] === 'wall' && g.kinds[b] === 'space') (neighbours[a] ||= []).push(g.names[b]);
    if (g.kinds[b] === 'wall' && g.kinds[a] === 'space') (neighbours[b] ||= []).push(g.names[a]);
  }
  const out = {};
  for (const [w, names] of Object.entries(neighbours)) {
    const unique = [...new Set(names)];
    if (unique.length === 2) out[w] = unique.sort().join('|');
  }
  return out;
}

export function graphToFlow(detail, highlight) {
  if (!detail?.graph) return { nodes: [], edges: [] };
  const g = detail.graph;
  const cells = detail.cells || [];
  const cellsByName = Object.fromEntries(cells.map((c) => [c.name, c]));
  const floorBound = cells.filter((c) => !c.serves && c.h);
  const H = floorBound.length ? Math.min(...floorBound.map((c) => c.h)) : 3;
  const levelOfZ = (z) => Math.max(0, Math.floor((z + 1e-6) / H));
  const maxX = Math.max(...g.coords.map((c) => c[0]));
  const panel = (maxX + 4) * SCALE;
  const hl = new Set(highlight?.cells || []);
  const doorPairs = new Set((g.doors || []).map((d) => [d.a, d.b].sort().join('|')));
  const pairs = wallPairs(g);
  const nodes = g.names.map((name, i) => {
    const [x, y, z] = g.coords[i];
    if (g.kinds[i] === 'space') {
      const c = cellsByName[name] || {};
      const level = c.serves ? c.serves[0] : levelOfZ(z);
      return { id: `n${i}`, type: 'space', position: { x: x * SCALE + level * panel, y: -y * SCALE }, draggable: false,
               data: { label: name, program: c.program, dims: c.w ? `${c.w}×${c.l}×${c.h}` : '', highlight: hl.has(c.index),
                       index: c.index, serves: c.serves || null } };
    }
    const pair = pairs[i];
    const door = pair ? doorPairs.has(pair) : false;
    return { id: `n${i}`, type: 'wall', position: { x: x * SCALE + levelOfZ(z) * panel, y: -y * SCALE }, draggable: false, zIndex: 10,
             data: { title: `${door ? 'door' : 'shared wall'}${pair ? `: ${pair.replace('|', ' – ')}` : ''}`,
                     highlight: highlight?.node === i, index: i, door } };
  });
  const edges = g.edges.map(([a, b], i) => {
    const wall = g.kinds[a] === 'wall' ? a : g.kinds[b] === 'wall' ? b : null;
    let className = 'direct-edge';
    if (wall != null) className = pairs[wall] && doorPairs.has(pairs[wall]) ? 'door-edge' : 'contact-edge';
    return { id: `e${i}`, source: `n${a}`, target: `n${b}`, type: 'straight', className, data: { a, b, wall: wall != null } };
  });
  return { nodes, edges };
}

/** The two space nodes attached to a wall node (its shared face). */
export function cellsOfWall(detail, wallIndex) {
  const g = detail.graph;
  const byName = Object.fromEntries((detail.cells || []).map((c) => [c.name, c.index]));
  const cells = [];
  for (const [a, b] of g.edges) {
    if (a === wallIndex && g.kinds[b] === 'space') cells.push(byName[g.names[b]]);
    if (b === wallIndex && g.kinds[a] === 'space') cells.push(byName[g.names[a]]);
  }
  return cells.filter((c) => c != null);
}
