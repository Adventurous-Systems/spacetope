// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { PROGRAM_COLOURS } from '../Viewer3D/colours';

/** Space node: one per cell. Wall node: one per shared face (the realised wall-node graph). */
export const SpaceNode = memo(function SpaceNode({ data, selected }) {
  const colour = PROGRAM_COLOURS[data.program] || '#999';
  return (
    <div className={`space-node ${data.highlight ? 'space-node--hl' : ''} ${selected ? 'space-node--selected' : ''} ${data.serves ? 'space-node--shaft' : ''}`}
         style={{ borderColor: colour }} data-testid="space-node" data-shaft={data.serves ? 'true' : undefined}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div className="space-node__name">{data.label}</div>
      <div className="space-node__dims">{data.dims}{data.serves ? ` · levels ${data.serves[0]}–${data.serves[1]}` : ''}</div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
});

export const WallNode = memo(function WallNode({ data }) {
  return (
    <div className={`wall-node ${data.highlight ? 'wall-node--hl' : ''} ${data.door ? 'wall-node--door' : ''}`} title={data.title}
         data-testid="wall-node" data-door={data.door ? 'true' : undefined}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
});

export const nodeTypes = { space: SpaceNode, wall: WallNode };
