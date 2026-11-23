import { create } from 'zustand';

const post = async (path, body) => {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    const err = new Error(typeof detail === 'string' ? detail : detail?.message || `${res.status}`);
    err.problems = detail?.problems || null;
    throw err;
  }
  return data;
};

/**
 * Field mode: a site, paths and a schedule; the server relaxes, tessellates and measures on every change.
 * Only the newest request counts: while one is in flight the latest wish waits, and older ones are dropped.
 */
const useFieldStore = create((set, get) => ({
  fixtures: [],
  kinds: ['voronoi', 'power', 'slice', 'grid', 'hex'],
  brief: null,
  kind: 'power',
  seed: 0,
  level: 0,
  result: null,          // the last solve: positions, cells, scores, affinity, checks
  positions: {},         // what is on screen (follows the pointer during a drag)
  pins: [],
  busy: false,
  queued: null,
  error: null,
  problems: [],
  options: [],
  optionsInfo: null,
  current: null,         // index of the option on show, or null for the live state
  generating: false,

  loadFixtures: async () => {
    try {
      const fixtures = await (await fetch('/api/field/fixtures')).json();
      set({ fixtures, kinds: fixtures[0]?.kinds || get().kinds });
    } catch (e) { set({ error: e.message }); }
  },
  loadFixture: async (name) => {
    try {
      const brief = await (await fetch(`/api/field/fixtures/${name}`)).json();
      set({ brief, result: null, positions: {}, pins: [], options: [], current: null, level: 0, error: null, problems: [] });
      get().solve({ fresh: true });
    } catch (e) { set({ error: e.message }); }
  },

  /** fresh: forget positions and relax from the seed. relax: let the rooms settle (false while a drag is under way). */
  solve: async ({ fresh = false, relax = true } = {}) => {
    const wish = { fresh, relax };
    if (get().busy) { set({ queued: wish }); return; }
    const { brief, kind, seed, positions, pins } = get();
    if (!brief) return;
    set({ busy: true, error: null, problems: [] });
    try {
      const has = !fresh && Object.keys(positions).length > 0;
      const result = await post('/api/field/solve', { brief, kind, seed, relax, positions: has ? positions : null, pins: has ? pins : [] });
      const level = Math.min(get().level, result.levels - 1);
      set({ result, level, current: null, ...(get().dragging ? {} : { positions: result.positions }) });
    } catch (e) {
      set({ error: e.message, problems: e.problems || [] });
    } finally {
      const queued = get().queued;
      set({ busy: false, queued: null });
      if (queued) get().solve(queued);
    }
  },

  setKind: (kind) => { set({ kind }); get().solve({ relax: false }); },
  setSeed: (seed) => { set({ seed, pins: [] }); get().solve({ fresh: true }); },
  setLevel: (level) => set({ level }),
  unpin: () => { set({ pins: [] }); get().solve(); },

  dragStart: () => set({ dragging: true }),
  dragRoom: (name, xy) => {
    set({ positions: { ...get().positions, [name]: xy }, pins: [...new Set([...get().pins, name])] });
    get().solve({ relax: false });
  },
  dragPath: (pi, qi, xy) => {
    const brief = get().brief;
    const paths = brief.paths.map((p, i) => (i !== pi ? p : { ...p, points: p.points.map((q, j) => (j !== qi ? q : [xy[0], xy[1], ...q.slice(2)])) }));
    set({ brief: { ...brief, paths } });
    get().solve({ relax: false });
  },
  dragEnd: () => { set({ dragging: false }); get().solve(); },

  generate: async () => {
    const { brief, seed } = get();
    if (!brief) return;
    set({ generating: true, error: null, options: [], optionsInfo: null });
    try {
      const out = await post('/api/field/options', { brief, seeds: [seed, seed + 1, seed + 2] });
      set({ options: out.options, optionsInfo: out.info });
    } catch (e) { set({ error: e.message, problems: e.problems || [] }); }
    set({ generating: false });
  },
  view: (index) => set({ current: index }),
}));

export default useFieldStore;
