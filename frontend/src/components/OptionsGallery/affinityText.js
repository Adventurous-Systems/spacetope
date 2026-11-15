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

const SIDE = { N: 'north', E: 'east', S: 'south', W: 'west' };
const EQUATOR = { N: 'south', S: 'north' };

// What a facade wish asks for, in words. `sun` is orientation (the equator-facing side), not hours of sun.
export function facadeWish(it, site) {
  const m = (it.source || '').match(/facade ([NESW])$/);
  const side = it.side || (m ? m[1] : null);
  if (side === 'sun') {
    const eq = site && EQUATOR[site.hemisphere];
    return `face the sun side${eq ? ` (${eq})` : ''}`;
  }
  return `have a wall facing ${side ? (SIDE[side] || side) : 'a given side'}`;
}

export function sentence(it, site) {
  const other = it.others.length > 1 ? `any of ${it.others.join(', ')}` : it.others[0];
  const wish = it.kind === 'facade' ? facadeWish(it, site) : WISH[it.kind](other, it);
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

// The symmetry `orient.best` chose (id, r90, r180, r270, mx, mx_r90, ...), in plain words; nothing for the
// identity, and an unknown name is shown as it is.
export function turnedText(orientation) {
  const name = orientation && orientation.symmetry;
  if (!name || name === 'id' || name === 'identity') return null;
  const m = String(name).match(/^(mx)?_?(?:r(90|180|270))?$/);
  const how = m ? [m[1] && 'mirrored', m[2] && `turned ${m[2]}°`].filter(Boolean).join(' and ') : name;
  return `Turned to face the site: ${how}`;
}
