// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

import { create } from 'zustand';

/** How the 3D layer is displayed and whether it currently takes the mouse. */
const useViewerStore = create((set) => ({
  opacity: 0.55,
  orbiting: false,    // Space held
  orbitLock: false,   // toolbar toggle; Escape leaves
  setOpacity: (opacity) => set({ opacity }),
  setOrbiting: (orbiting) => set({ orbiting }),
  toggleOrbitLock: () => set((s) => ({ orbitLock: !s.orbitLock })),
}));

export default useViewerStore;
