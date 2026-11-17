// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

import { create } from 'zustand';

/** fetch JSON; on failure the error carries the HTTP status and any validation problems from the API. */
const api = async (path, opts) => {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    const detail = body?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || `${res.status} ${res.statusText}`;
    const err = new Error(message);
    err.status = res.status;
    err.problems = Array.isArray(detail?.problems) ? detail.problems : null;
    throw err;
  }
  return res.json();
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Brief -> expand and validate -> job -> options -> selection. One store, no framework leakage into components. */
const useAppStore = create((set, get) => ({
  fixtures: [],
  capabilities: {},
  brief: null,          // what the architect edits (compact circulation section)
  expanded: null,       // what the API expanded it into (generated corridors, shafts)
  briefId: null,
  problems: [],         // validation or generator problems that blocked generation
  warnings: [],
  generator: 'beam',
  seed: 0,
  status: 'idle',
  error: null,
  job: null,
  options: [],
  current: null,
  detail: null,
  highlight: null,
  exported: null,

  loadFixtures: async () => {
    try { set({ fixtures: await api('/api/fixtures') }); } catch (e) { set({ error: e.message }); }
    try { set({ capabilities: (await api('/api/health')).capabilities || {} }); } catch { /* optional */ }
  },
  loadFixture: async (name) => {
    set({ status: 'loading brief', error: null });
    try {
      const brief = await api(`/api/fixtures/${name}`);
      set({ brief, expanded: null, briefId: null, problems: [], warnings: [], options: [], current: null,
            detail: null, highlight: null, status: 'brief loaded', exported: null });
    } catch (e) { set({ error: e.message, status: 'error' }); }
  },
  setBrief: (brief) => set({ brief, briefId: null, expanded: null, problems: [] }),
  setGenerator: (generator) => set({ generator }),
  setSeed: (seed) => set({ seed }),

  generate: async () => {
    const { brief, generator, seed } = get();
    if (!brief) return;
    set({ status: 'checking brief', error: null, problems: [], warnings: [], options: [], current: null,
          detail: null, highlight: null, exported: null });
    let posted;
    try {
      posted = await api('/api/brief', { method: 'POST', body: JSON.stringify(brief) });
    } catch (e) {
      set({ problems: e.problems || [{ message: e.message, severity: 'error' }], status: 'brief has problems' });
      return;
    }
    set({ briefId: posted.brief_id, expanded: posted.brief, warnings: posted.warnings || [],
          status: `generating (${generator}, seed ${seed})` });
    try {
      let job = await api('/api/generate', { method: 'POST', body: JSON.stringify({ brief_id: posted.brief_id, generator, seed }) });
      while (job.status === 'running') { await sleep(500); job = await api(`/api/jobs/${job.job_id}`); }
      if (job.status !== 'done') throw new Error(job.error || job.status);
      const options = await api(`/api/options/${job.job_id}`);
      set({ job, options, status: `${job.verified}/${job.options} options verified in ${(job.t_gen + job.t_realise).toFixed(1)}s` });
      if (options.length) await get().viewOption(0);
    } catch (e) {
      if (e.problems) set({ problems: e.problems, status: 'cannot generate' });
      else set({ error: e.message, status: 'error' });
    }
  },

  viewOption: async (i) => {
    const { job } = get();
    if (!job) return;
    const token = (get().viewToken || 0) + 1;   // a slower earlier response must not overwrite a later click
    set({ current: i, highlight: null, viewToken: token });
    try {
      const detail = await api(`/api/options/${job.job_id}/${i}`);
      if (get().viewToken === token) set({ detail });
    } catch (e) { if (get().viewToken === token) set({ error: e.message }); }
  },

  setHighlight: (highlight) => set({ highlight }),

  selectAndExport: async () => {
    const { job, current } = get();
    if (!job || current == null) return;
    set({ status: 'exporting' });
    try {
      const exported = await api('/api/select', { method: 'POST', body: JSON.stringify({ job_id: job.job_id, index: current }) });
      set({ exported, status: 'exported' });
    } catch (e) { set({ error: e.message, status: 'error' }); }
  },
}));

export default useAppStore;
