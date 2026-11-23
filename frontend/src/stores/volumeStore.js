import { create } from 'zustand';

const post = async (path, body) => {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.problems?.map((p) => p.message).join('; ') || detail?.message || `${res.status}`);
  }
  return data;
};

/** Volume mode: bodies on springs in a void. The server floats them and cuts storey cells; only the newest request counts. */
const useVolumeStore = create((set, get) => ({
  fixtures: [],
  brief: null,
  kind: 'power',
  seed: 0,
  result: null,
  pins: [],
  scales: {},
  selected: null,
  show: { bodies: true, cells: true, springs: true },
  busy: false,
  queued: null,
  error: null,
  sketch: null,
  sketching: false,

  loadFixtures: async () => {
    try { set({ fixtures: await (await fetch('/api/volume/fixtures')).json() }); } catch (e) { set({ error: e.message }); }
  },
  loadFixture: async (name) => {
    const brief = await (await fetch(`/api/volume/fixtures/${name}`)).json();
    set({ brief, result: null, pins: [], scales: {}, selected: null, sketch: null, error: null });
    get().solve({ fresh: true });
  },
  solve: async ({ fresh = false, positions = null, relax = true } = {}) => {
    const wish = { fresh, positions, relax };
    if (get().busy) { set({ queued: wish }); return; }
    const { brief, kind, seed, result, pins, scales } = get();
    if (!brief) return;
    set({ busy: true, error: null });
    try {
      const start = fresh ? null : positions || result?.positions || null;
      const out = await post('/api/volume/solve', { brief, kind, seed, relax, positions: start, pins: start ? pins : [], scales });
      set({ result: out, sketch: null });
    } catch (e) { set({ error: e.message }); }
    const queued = get().queued;
    set({ busy: false, queued: null });
    if (queued) get().solve(queued);
  },
  setKind: (kind) => { set({ kind }); get().solve({ relax: false }); },
  setSeed: (seed) => { set({ seed, pins: [] }); get().solve({ fresh: true }); },
  select: (selected) => set({ selected }),
  toggle: (what) => set({ show: { ...get().show, [what]: !get().show[what] } }),
  /** Inflate or deflate one body; the rest answer from where they are. */
  inflate: (name, factor) => { set({ scales: { ...get().scales, [name]: factor } }); get().solve(); },
  /** A body dropped somewhere: it is pinned there and the others settle round it. */
  moveBody: (name, xyz) => {
    const positions = { ...get().result.positions, [name]: xyz };
    set({ pins: [...new Set([...get().pins, name])] });
    get().solve({ positions });
  },
  shiftStorey: (name, by) => {
    const { result } = get();
    const b = result.bodies.find((x) => x.name === name);
    get().moveBody(name, [b.x, b.y, b.z + by * result.level_height]);
  },
  unpin: () => { set({ pins: [] }); get().solve(); },
  freeSketch: async () => {
    const { brief, seed, result, scales } = get();
    if (!result) return;
    set({ sketching: true, error: null });
    try { set({ sketch: await post('/api/volume/free', { brief, seed, positions: result.positions, scales }) }); } catch (e) { set({ error: e.message }); }
    set({ sketching: false });
  },
  closeSketch: () => set({ sketch: null }),
}));

export default useVolumeStore;
