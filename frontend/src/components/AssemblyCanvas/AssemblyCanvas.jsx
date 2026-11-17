// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { ReactFlow, Controls, MiniMap, Background, BackgroundVariant, useReactFlow, useNodesInitialized } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import useAppStore from '../../stores/appStore';
import useViewerStore from '../../stores/viewerStore';
import Viewer3D from '../Viewer3D/Viewer3D';
import ViewerBar from '../Viewer3D/ViewerBar';
import { nodeTypes } from './nodes';
import { graphToFlow, cellsOfWall } from './layout';
import './AssemblyCanvas.css';

// xyflow's default minZoom (0.5) cannot fit a two-level graph (~2,600 px wide at 60 px/m) into the canvas
const MIN_ZOOM = 0.05;

/**
 * Three stacked layers: the 3D cell complex behind (z0), the assembly graph on xyflow (z1, transparent
 * once an option is loaded), and the viewer bar on top (z2). Holding Space hands pointer events to the
 * 3D layer and freezes the graph, so panning the graph and orbiting the model never fight.
 */
export default function AssemblyCanvas() {
  const detail = useAppStore((s) => s.detail);
  const highlight = useAppStore((s) => s.highlight);
  const setHighlight = useAppStore((s) => s.setHighlight);
  const orbiting = useViewerStore((s) => s.orbiting);
  const setOrbiting = useViewerStore((s) => s.setOrbiting);
  const orbitLock = useViewerStore((s) => s.orbitLock);
  const toggleOrbitLock = useViewerStore((s) => s.toggleOrbitLock);
  const navActive = orbiting || orbitLock;
  const { fitView } = useReactFlow();

  useEffect(() => {
    const onDown = (e) => {
      const tag = document.activeElement?.tagName;
      if (e.code === 'Space' && detail && !e.repeat && !['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) {
        e.preventDefault(); setOrbiting(true);
      }
      if (e.code === 'Escape' && orbitLock) toggleOrbitLock();
    };
    const onUp = (e) => { if (e.code === 'Space') setOrbiting(false); };
    window.addEventListener('keydown', onDown); window.addEventListener('keyup', onUp);
    return () => { window.removeEventListener('keydown', onDown); window.removeEventListener('keyup', onUp); };
  }, [detail, orbitLock, setOrbiting, toggleOrbitLock]);

  const { nodes, edges } = useMemo(() => graphToFlow(detail, highlight), [detail, highlight]);

  // nodes arrive after mount, so the mount-time fitView sees nothing. Re-fit once per loaded option,
  // but only after xyflow has measured the new nodes (fitView skips unmeasured nodes).
  const jobId = useAppStore((s) => s.job?.job_id);
  const layoutKey = detail ? `${jobId}:${detail.index}:${detail.graph?.order}` : '';   // a new job re-fits even at the same index
  const nodesInitialized = useNodesInitialized();
  const fittedKey = useRef('');
  useEffect(() => {
    if (!layoutKey || !nodesInitialized || fittedKey.current === layoutKey) return;
    fittedKey.current = layoutKey;
    fitView({ padding: 0.12, duration: 0, minZoom: MIN_ZOOM });
  }, [layoutKey, nodesInitialized, fitView]);

  const onNodeClick = useCallback((_e, node) => {
    if (!detail) return;
    if (node.type === 'wall') setHighlight({ node: node.data.index, cells: cellsOfWall(detail, node.data.index) });
    else setHighlight({ cells: [node.data.index] });
  }, [detail, setHighlight]);

  const onEdgeClick = useCallback((_e, edge) => {
    if (!detail) return;
    const { a, b } = edge.data;
    const wall = detail.graph.kinds[a] === 'wall' ? a : detail.graph.kinds[b] === 'wall' ? b : null;
    if (wall != null) setHighlight({ node: wall, cells: cellsOfWall(detail, wall) });
  }, [detail, setHighlight]);

  return (
    <div className="assembly-canvas" data-testid="assembly-canvas">
      <Viewer3D />
      <div className={`assembly-canvas__flow ${detail ? 'assembly-canvas__flow--transparent' : ''}`}>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView colorMode="dark" nodeOrigin={[0.5, 0.5]} minZoom={MIN_ZOOM} maxZoom={4}
                   onNodeClick={onNodeClick} onEdgeClick={onEdgeClick}
                   panOnDrag={!navActive} zoomOnScroll={!navActive} zoomOnPinch={!navActive}
                   nodesDraggable={false} nodesConnectable={false} elementsSelectable>
          <Controls />
          <MiniMap nodeColor={(n) => (n.type === 'wall' ? '#d62728' : '#4ecdc4')} maskColor="rgba(0,0,0,0.7)" />
          {!detail && <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#2a2a4a" />}
        </ReactFlow>
      </div>
      <ViewerBar />
      {!detail && <div className="assembly-canvas__empty">Load a brief and generate options.</div>}
    </div>
  );
}
