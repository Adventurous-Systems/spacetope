import { useEffect, useMemo } from 'react';
import { useThree } from '@react-three/fiber';
import { Center, Line, useGLTF } from '@react-three/drei';
import * as THREE from 'three';

/**
 * The cell complex as published by the API: a GLB whose mesh nodes are named `cell_<index>` for spaces
 * and `door_<index>` for doorway faces. Cells are recoloured here from the option's dictionaries, so
 * changing a colour never needs a new download. Doors keep the colour baked into the GLB and are drawn
 * from both sides, because a doorway face has no thickness.
 */
const CELL_NODE = /^cell_(\d+)/;
const DOOR_NODE = /^door_\d+/;
const UNTAGGED = '#4a5568';
const UNTAGGED_FADE = 0.35;

function meshRole(mesh) {
  for (let node = mesh; node; node = node.parent) {
    const name = node.name || '';
    const cell = CELL_NODE.exec(name);
    if (cell) return ['cell', Number(cell[1])];
    if (DOOR_NODE.test(name)) return ['door', null];
  }
  return ['other', null];
}

export function ComplexModel({ glbUrl, cellColours, opacity = 1, onCounts }) {
  const { scene } = useGLTF(glbUrl);
  const invalidate = useThree((state) => state.invalidate);

  const model = useMemo(() => {
    const copy = scene.clone(true);
    const counts = { cells: 0, doors: 0 };
    copy.traverse((mesh) => {
      if (!mesh.isMesh) return;
      const [role, index] = meshRole(mesh);
      if (role === 'door') {
        counts.doors += 1;
        mesh.material = mesh.material.clone();
        mesh.material.side = THREE.DoubleSide;
        mesh.userData.fade = 1;
        return;
      }
      if (role === 'cell') counts.cells += 1;
      const colour = cellColours && index !== null ? cellColours[index] : null;
      if (cellColours) {
        mesh.material = new THREE.MeshStandardMaterial({ color: colour || UNTAGGED, roughness: 0.85, metalness: 0 });
        mesh.userData.fade = colour ? 1 : UNTAGGED_FADE;
      } else {
        mesh.material = mesh.material.clone();
        mesh.userData.fade = 1;
      }
    });
    if (onCounts) onCounts(counts);
    return copy;
  }, [scene, cellColours, onCounts]);

  // the opacity slider edits materials in place: no re-clone, and translucent cells stop writing depth
  // so the graph behind them stays readable. Flipping `transparent` needs a recompile: a material first
  // drawn opaque bakes OPAQUE into its shader (alpha forced to 1), and on a large GLB that first frame
  // can come before this effect runs.
  useEffect(() => {
    model.traverse((mesh) => {
      if (!mesh.isMesh) return;
      const value = (mesh.userData.fade ?? 1) * opacity;
      const transparent = value < 1;
      if (mesh.material.transparent !== transparent) mesh.material.needsUpdate = true;
      mesh.material.opacity = value;
      mesh.material.transparent = transparent;
      mesh.material.depthWrite = !transparent;
    });
    invalidate();
  }, [model, opacity, invalidate]);

  return <primitive object={model} />;
}

export function GraphLayer({ graph, nodeColours }) {
  const points = graph?.coords_yup || graph?.coords;
  if (!points?.length) return null;
  const kinds = graph.kinds || [];
  return (
    <group>
      {(graph.edges || []).map(([from, to], i) => (
        <Line key={`edge-${i}`} points={[points[from], points[to]]} color="#4ecdc4" lineWidth={2} />
      ))}
      {points.map((point, i) => (
        <mesh key={`node-${i}`} position={point}>
          <sphereGeometry args={[kinds[i] === 'wall' ? 0.12 : 0.25, 10, 10]} />
          <meshBasicMaterial color={nodeColours?.[i] || (kinds[i] === 'wall' ? '#d62728' : '#ffffff')} />
        </mesh>
      ))}
    </group>
  );
}

/** Model and graph are centred together, so graph coordinates stay aligned with the geometry. */
export default function ComplexScene({ glbUrl, graph, colours, showGraph, opacity, onCounts }) {
  return (
    <Center>
      <group>
        {glbUrl && <ComplexModel glbUrl={glbUrl} cellColours={colours?.cellColours} opacity={opacity} onCounts={onCounts} />}
        {showGraph && <GraphLayer graph={graph} nodeColours={colours?.nodeColours} />}
      </group>
    </Center>
  );
}
