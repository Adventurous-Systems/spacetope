// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

/** Colours for the 3D scene and the graph. Programs keep one hue; a highlighted space turns yellow. */
export const PROGRAM_COLOURS = {
  room: '#6baed6',
  corridor: '#fdae6b',
  stair: '#e6550d',
  elevator: '#756bb1',
  void: '#bdbdbd',
};
export const HIGHLIGHT = '#ffe066';
export const WALL_NODE = '#d62728';
export const SPACE_NODE = '#ffffff';

/** Per-cell and per-graph-node colours for one option detail, or null when there is nothing to colour. */
export function buildColours(detail, highlight) {
  const cells = detail?.cells;
  if (!cells) return null;
  const lit = new Set(highlight?.cells || []);
  const cellColours = cells.map((cell) => (lit.has(cell.index) ? HIGHLIGHT : PROGRAM_COLOURS[cell.program] || '#999999'));
  const indexByName = new Map(cells.map((cell) => [cell.name, cell.index]));
  const kinds = detail.graph?.kinds || [];
  const nodeColours = (detail.graph?.names || []).map((name, i) => {
    if (kinds[i] === 'wall') return highlight?.node === i ? HIGHLIGHT : WALL_NODE;
    return lit.has(indexByName.get(name)) ? HIGHLIGHT : SPACE_NODE;
  });
  return { cellColours, nodeColours };
}
