// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

import { Suspense, useCallback, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { GizmoHelper, GizmoViewport, OrbitControls } from '@react-three/drei';
import useAppStore from '../../stores/appStore';
import useViewerStore from '../../stores/viewerStore';
import ComplexScene from './ComplexScene';
import { buildColours } from './colours';
import './Viewer3D.css';

/**
 * The 3D layer that sits behind the assembly graph. It is inert to the mouse until orbiting is on,
 * so panning the graph and orbiting the model never fight over the same drag.
 */
export default function Viewer3D() {
  const detail = useAppStore((s) => s.detail);
  const highlight = useAppStore((s) => s.highlight);
  const opacity = useViewerStore((s) => s.opacity);
  const orbiting = useViewerStore((s) => s.orbiting);
  const orbitLock = useViewerStore((s) => s.orbitLock);
  const interactive = orbiting || orbitLock;

  const colours = useMemo(() => buildColours(detail, highlight), [detail, highlight]);
  const onCounts = useCallback(({ cells, doors }) => {
    // test hook: how much geometry the current option put on screen
    window.__spacetope = { ...(window.__spacetope || {}), cells, doors, glb: detail?.glb_url };
  }, [detail]);

  if (!detail?.glb_url) return null;
  return (
    <div className={`viewer3d ${interactive ? 'viewer3d--interactive' : ''}`} data-testid="viewer-3d">
      <Canvas camera={{ position: [18, 14, 18], fov: 35 }}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[6, 8, 5]} intensity={1.4} />
        <directionalLight position={[-4, 2, -4]} intensity={0.5} />
        <Suspense fallback={null}>
          <ComplexScene glbUrl={detail.glb_url} graph={detail.graph} colours={colours} showGraph opacity={opacity}
                        onCounts={onCounts} />
        </Suspense>
        <OrbitControls makeDefault />
        <gridHelper args={[40, 40, '#444444', '#333333']} />
        <GizmoHelper alignment="bottom-right" margin={[60, 60]}>
          <GizmoViewport />
        </GizmoHelper>
      </Canvas>
    </div>
  );
}
