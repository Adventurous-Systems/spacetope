// One plain sentence per missed affinity, built from the report item (see PLAN 4.10).
const WISH = {
  touch: (o) => `share a wall with ${o}`,
  near: (o, it) => `be within ${it.target} doors of ${o}`,
  apart: (o) => `stay apart from ${o}`,
  stack: (o) => `stack over or under ${o}`,
  same_level: (o) => `be on the same level as ${o}`,
  exterior: () => 'have an outside wall',
  ground: () => 'be on the ground level',
  top: () => 'be on the top level',
};
const SAY = { must: 'must', should: 'should', never: 'must not', avoid: 'should not' };
const SHOW = {
  m: (v) => `${v.toFixed(1)} m of wall`, m2: (v) => `${v.toFixed(1)} m² of wall`, share: (v) => `${v.toFixed(2)} overlap`,
  doors: (v) => `${v} doors`, levels: (v) => `${v} levels apart`, level: (v) => `level ${v}`,
};
const show = (it, v) => (v === null || v === undefined ? null : (SHOW[it.unit] || String)(v));

export const isHard = (it) => it.strength === 'must' || it.strength === 'never';

export function sentence(it) {
  const other = it.others.length > 1 ? `any of ${it.others.join(', ')}` : it.others[0];
  const side = it.source.match(/facade ([NESW])$/);
  const wish = it.kind === 'facade' ? `have a wall facing ${side ? side[1] : 'a given side'}` : WISH[it.kind](other, it);
  // a miss of 'apart' (or a hit of never/avoid) is something that exists, so report what was found
  const found = it.kind === 'apart' || it.strength === 'never' || it.strength === 'avoid';
  const got = show(it, it.value);
  let detail = '';
  if (found) detail = got ? ` — found ${got}${it.by ? ` (${it.by})` : ''}` : '';
  else if (got) detail = ` — best ${got}, needs ${show(it, it.target)}${it.by ? ` (${it.by})` : ''}`;
  else if (it.unit) detail = ' — no route';
  return `${it.a} ${SAY[it.strength]} ${wish}${detail}`;
}

export const missed = (aff) => aff.items.filter((it) => it.met === false)
  .sort((x, y) => Number(isHard(y)) - Number(isHard(x)));
