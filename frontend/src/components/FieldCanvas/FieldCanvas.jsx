import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import useFieldStore from '../../stores/fieldStore';
import ComplexScene from '../Viewer3D/ComplexScene';
import { buildColours } from '../Viewer3D/colours';
import './FieldCanvas.css';

const FILL = { room: '#c8703f', corridor: '#74c2cc', stair: '#3d8f9a' };
const ring = (pts) => pts.map((p) => `${p[0]},${-p[1]}`).join(' ');

/** Plan of one level: site, cells, the path with its handles and the rooms' seeds. Everything in metres, y up. */
function Plan({ shown, live }) {
  const brief = useFieldStore((s) => s.brief);
  const level = useFieldStore((s) => s.level);
  const positions = useFieldStore((s) => s.positions);
  const pins = useFieldStore((s) => s.pins);
  const { dragStart, dragRoom, dragPath, dragEnd } = useFieldStore.getState();
  const svg = useRef(null);
  const drag = useRef(null);

  const boundary = brief?.site?.boundary || shown.ground;
  const box = useMemo(() => {
    const xs = boundary.map((p) => p[0]); const ys = boundary.map((p) => p[1]);
    const pad = 3;
    return [Math.min(...xs) - pad, -Math.max(...ys) - pad, Math.max(...xs) - Math.min(...xs) + 2 * pad, Math.max(...ys) - Math.min(...ys) + 2 * pad];
  }, [boundary]);

  const point = (e) => {
    const m = svg.current.getScreenCTM().inverse();
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m);
    return [Math.round(p.x * 100) / 100, Math.round(-p.y * 100) / 100];
  };
  const down = (what) => (e) => { if (!live) return; e.target.setPointerCapture(e.pointerId); drag.current = what; dragStart(); };
  const move = (e) => {
    const d = drag.current;
    if (!d) return;
    if (d.room) dragRoom(d.room, point(e)); else dragPath(d.path, d.point, point(e));
  };
  const up = () => { if (drag.current) { drag.current = null; dragEnd(); } };

  const here = shown.cells.filter((c) => c.levels[0] <= level && level <= c.levels[1]);
  const below = level > 0 ? shown.cells.filter((c) => c.levels[0] <= level - 1 && level - 1 <= c.levels[1]) : [];
  const where = live ? positions : shown.positions;
  return (
    <svg ref={svg} className="field__svg" viewBox={box.join(' ')} onPointerMove={move} onPointerUp={up} data-testid="field-plan">
      <polygon points={ring(boundary)} className="field__site" />
      <polygon points={ring(shown.ground)} className="field__ground" />
      {below.map((c) => <polygon key={`b${c.name}`} points={ring(c.ring)} className="field__below" />)}
      {here.map((c) => (
        <polygon key={c.name} points={ring(c.ring)} fill={FILL[c.program] || '#999'} className="field__cell" data-testid="field-cell">
          <title>{`${c.name} · ${c.area} m²${c.want ? ` (asked ${c.want})` : ''}`}</title>
        </polygon>
      ))}
      {live && (brief?.paths || []).map((p, pi) => (
        <g key={p.name}>
          <polyline points={ring(p.points)} className="field__path" />
          {p.points.map((q, qi) => (
            <circle key={qi} cx={q[0]} cy={-q[1]} r={0.9} className="field__handle" onPointerDown={down({ path: pi, point: qi })} data-testid="path-handle" />
          ))}
        </g>
      ))}
      {here.filter((c) => c.program === 'room' && where[c.name]).map((c) => (
        <g key={`s${c.name}`} transform={`translate(${where[c.name][0]}, ${-where[c.name][1]})`}>
          <circle r={0.55} className={`field__seed ${pins.includes(c.name) ? 'field__seed--pinned' : ''}`} onPointerDown={down({ room: c.name })} data-testid="room-seed" />
          <text x={0.8} y={0.35} className="field__label">{c.name.replace(/_/g, ' ')}</text>
        </g>
      ))}
    </svg>
  );
}

function Model({ option }) {
  const colours = useMemo(() => buildColours({ cells: option.catalogue }, null), [option]);
  return (
    <div className="field__model" data-testid="field-model">
      <Canvas camera={{ position: [70, 55, 70], fov: 32 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[6, 8, 5]} intensity={1.3} />
        <Suspense fallback={null}><ComplexScene glbUrl={option.glb_url} colours={colours} opacity={1} /></Suspense>
        <OrbitControls makeDefault />
      </Canvas>
    </div>
  );
}

export default function FieldCanvas() {
  const s = useFieldStore();
  const [model, setModel] = useState(false);
  useEffect(() => { s.loadFixtures(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const option = s.current != null ? s.options[s.current] : null;
  const shown = option || s.result;
  const levels = shown ? shown.levels : 1;
  return (
    <div className="field" data-testid="field-canvas">
      <div className="field__bar">
        <select value={s.brief?.name || ''} onChange={(e) => e.target.value && s.loadFixture(e.target.value)} data-testid="field-fixture">
          <option value="">field brief…</option>
          {s.fixtures.map((f) => <option key={f.name} value={f.name}>{f.name} ({f.spaces} rooms)</option>)}
        </select>
        {s.kinds.map((k) => (
          <button key={k} className={k === (option ? option.kind : s.kind) ? 'primary' : ''} disabled={!s.brief || !!option} onClick={() => s.setKind(k)} data-testid={`kind-${k}`}>{k}</button>
        ))}
        <label>seed <input type="number" value={s.seed} min={0} style={{ width: 48 }} disabled={!!option} onChange={(e) => s.setSeed(parseInt(e.target.value, 10) || 0)} /></label>
        {Array.from({ length: levels }, (_, k) => (
          <button key={k} className={k === s.level ? 'primary' : ''} onClick={() => s.setLevel(k)} data-testid={`level-${k}`}>level {k}</button>
        ))}
        {s.pins.length > 0 && !option && <button onClick={s.unpin}>release {s.pins.length} pinned</button>}
        {option && <button onClick={() => s.view(null)} data-testid="field-live">back to live</button>}
        {option?.glb_url && <button className={model ? 'primary' : ''} onClick={() => setModel(!model)} data-testid="field-3d">3D</button>}
        <span className="field__ms" data-testid="field-ms">{s.busy ? '…' : s.result && !option ? `${s.result.ms.relax + s.result.ms.tessellate + s.result.ms.measure} ms` : ''}</span>
      </div>
      {s.error && <div className="field__error" data-testid="field-error">{s.error}{s.problems.map((p, i) => <div key={i}>{p.message}</div>)}</div>}
      {shown ? (model && option?.glb_url ? <Model option={option} /> : <Plan shown={shown} live={!option} />)
        : <div className="field__empty">Choose a field brief. Drag a room or a point of the path; the plan and its scores follow.</div>}
    </div>
  );
}
