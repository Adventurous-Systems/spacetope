import { Suspense, useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { Canvas } from '@react-three/fiber';
import { Line, OrbitControls, TransformControls } from '@react-three/drei';
import useVolumeStore from '../../stores/volumeStore';
import ComplexScene from '../Viewer3D/ComplexScene';
import './FieldCanvas.css';

// data is z-up in metres; three is y-up: (x, y, z) -> (x, z, -y), the same turn the GLB export makes
const up = (x, y, z) => [x, z, -y];
const FILL = { room: '#c8703f', corridor: '#74c2cc', stair: '#3d8f9a' };

function Cell({ cell, H, dim }) {
  const geometry = useMemo(() => {
    const shape = new THREE.Shape(cell.ring.map((p) => new THREE.Vector2(p[0], p[1])));
    return new THREE.ExtrudeGeometry(shape, { depth: (cell.levels[1] - cell.levels[0] + 1) * H, bevelEnabled: false });
  }, [cell, H]);
  const edges = useMemo(() => new THREE.EdgesGeometry(geometry), [geometry]);
  return (
    <group position={[0, cell.levels[0] * H, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <mesh geometry={geometry}><meshStandardMaterial color={FILL[cell.program] || '#999'} transparent opacity={dim ? 0.28 : 0.85} depthWrite={!dim} /></mesh>
      <lineSegments geometry={edges}><lineBasicMaterial color="#3a2a20" /></lineSegments>
    </group>
  );
}

function Body({ body, selected, pinned, onPick, onDrop }) {
  const mesh = useRef(null);
  const ball = (
    <mesh ref={mesh} position={up(body.x, body.y, body.z)} scale={[body.radius, body.half_height, body.radius]}
          onClick={(e) => { e.stopPropagation(); onPick(body.name); }}>
      <sphereGeometry args={[1, 24, 16]} />
      <meshStandardMaterial color={selected ? '#ffe066' : pinned ? '#e94560' : '#f3d9c4'} transparent opacity={0.55} depthWrite={false} />
    </mesh>
  );
  if (!selected) return ball;
  return (
    <>
      {ball}
      {mesh.current && (
        <TransformControls object={mesh.current} mode="translate" size={0.7}
                           onMouseUp={() => { const p = mesh.current.position; onDrop(body.name, [p.x, -p.z, p.y]); }} />
      )}
    </>
  );
}

function Scene() {
  const result = useVolumeStore((s) => s.result);
  const show = useVolumeStore((s) => s.show);
  const selected = useVolumeStore((s) => s.selected);
  const pins = useVolumeStore((s) => s.pins);
  const { select, moveBody } = useVolumeStore.getState();
  const H = result.level_height;
  const at = Object.fromEntries(result.bodies.map((b) => [b.name, up(b.x, b.y, b.z)]));
  return (
    <group>
      {result.storeys.map((s) => [0, 1].map((t) => (
        <Line key={`${s.level}-${t}`} points={[...s.ground, s.ground[0]].map((p) => up(p[0], p[1], (s.level + t) * H))} color="#8a8378" lineWidth={1} />
      )))}
      {show.cells && result.cells.map((c) => <Cell key={c.name} cell={c} H={H} dim={show.bodies} />)}
      {show.springs && result.springs.filter(([a, b]) => at[a] && at[b]).map(([a, b]) => (
        <Line key={`${a}|${b}`} points={[at[a], at[b]]} color="#0d5c66" lineWidth={1.5} />
      ))}
      {show.bodies && result.bodies.map((b) => (
        <Body key={b.name} body={b} selected={b.name === selected} pinned={pins.includes(b.name)} onPick={select} onDrop={moveBody} />
      ))}
    </group>
  );
}

export default function VolumeCanvas() {
  const s = useVolumeStore();
  useEffect(() => { s.loadFixtures(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { window.__volume = { bodies: s.result?.bodies?.length || 0, cells: s.result?.cells?.length || 0 }; }, [s.result]);
  // look at the middle of the void; nothing in the scene is moved, so a body's handle sits on the body
  const target = useMemo(() => {
    const g = s.result?.ground;
    if (!g) return [0, 0, 0];
    const xs = g.map((q) => q[0]); const ys = g.map((q) => q[1]);
    return [(Math.min(...xs) + Math.max(...xs)) / 2, (s.result.levels * s.result.level_height) / 2, -(Math.min(...ys) + Math.max(...ys)) / 2];
  }, [s.result?.ground, s.result?.levels, s.result?.level_height]);
  return (
    <div className="field field--dark" data-testid="volume-canvas">
      <div className="field__bar">
        <select value={s.brief?.name || ''} onChange={(e) => e.target.value && s.loadFixture(e.target.value)} data-testid="volume-fixture">
          <option value="">void brief…</option>
          {s.fixtures.map((f) => <option key={f.name} value={f.name}>{f.name} ({f.spaces} rooms)</option>)}
        </select>
        {['voronoi', 'power', 'slice', 'grid', 'hex'].map((k) => (
          <button key={k} className={k === s.kind ? 'primary' : ''} disabled={!s.brief} onClick={() => s.setKind(k)} data-testid={`vkind-${k}`}>{k}</button>
        ))}
        <label>seed <input type="number" value={s.seed} min={0} style={{ width: 48 }} onChange={(e) => s.setSeed(parseInt(e.target.value, 10) || 0)} /></label>
        {['bodies', 'cells', 'springs'].map((w) => (
          <button key={w} className={s.show[w] ? 'primary' : ''} onClick={() => s.toggle(w)} data-testid={`show-${w}`}>{w}</button>
        ))}
        {s.pins.length > 0 && <button onClick={s.unpin}>release {s.pins.length} pinned</button>}
        {s.sketch && <button onClick={s.closeSketch} data-testid="sketch-close">back to storeys</button>}
        <span className="field__ms" data-testid="volume-ms">{s.busy ? '…' : s.result ? `${s.result.ms.relax + s.result.ms.tessellate + s.result.ms.measure} ms` : ''}</span>
      </div>
      {s.error && <div className="field__error" data-testid="volume-error">{s.error}</div>}
      {s.result ? (
        <div className="field__model">
          <Canvas camera={{ position: [target[0] + 50, target[1] + 42, target[2] + 55], fov: 32 }} onPointerMissed={() => s.select(null)}>
            <ambientLight intensity={0.7} />
            <directionalLight position={[6, 10, 5]} intensity={1.2} />
            {s.sketch ? <Suspense fallback={null}><ComplexScene glbUrl={s.sketch.glb_url} opacity={0.9} /></Suspense> : <Scene />}
            <OrbitControls makeDefault target={target} />
          </Canvas>
        </div>
      ) : <div className="field__empty">Choose a void brief. Click a body to select it, drag its arrows to move it, and inflate it on the right.</div>}
    </div>
  );
}
