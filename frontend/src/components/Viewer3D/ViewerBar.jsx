// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

import useAppStore from '../../stores/appStore';
import useViewerStore from '../../stores/viewerStore';
import './ViewerBar.css';

/** Opacity of the geometry, and the orbit switch: hold Space, or lock it and press Escape to leave. */
export default function ViewerBar() {
  const detail = useAppStore((s) => s.detail);
  const opacity = useViewerStore((s) => s.opacity);
  const setOpacity = useViewerStore((s) => s.setOpacity);
  const orbiting = useViewerStore((s) => s.orbiting);
  const orbitLock = useViewerStore((s) => s.orbitLock);
  const toggleOrbitLock = useViewerStore((s) => s.toggleOrbitLock);
  if (!detail) return null;
  const interactive = orbiting || orbitLock;
  return (
    <div className="viewerbar" data-testid="viewer-bar">
      <span className="viewerbar__label">3D</span>
      <input type="range" min="0.05" max="1" step="0.05" value={opacity} className="viewerbar__slider"
             onChange={(e) => setOpacity(parseFloat(e.target.value))} aria-label="geometry opacity" />
      <span className="viewerbar__value">{Math.round(opacity * 100)}%</span>
      <button className={`viewerbar__orbit ${orbitLock ? 'viewerbar__orbit--locked' : ''}`}
              onClick={toggleOrbitLock} data-testid="viewer-orbit-toggle">
        {orbitLock ? 'Orbiting' : 'Orbit'}
      </button>
      <span className={`viewerbar__hint ${interactive ? 'viewerbar__hint--active' : ''}`}>
        {orbitLock ? 'Esc to stop' : 'hold Space'}
      </span>
    </div>
  );
}
