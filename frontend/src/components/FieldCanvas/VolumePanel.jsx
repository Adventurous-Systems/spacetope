import useVolumeStore from '../../stores/volumeStore';
import './FieldCanvas.css';

const SCORES = [['affinity', 'wishes met'], ['share_deviation', 'share off'], ['storey_balance', 'storey off'], ['compactness', 'compact'],
  ['exposure', 'outside wall'], ['regularity', 'regular rooms']];
const LOWER = new Set(['share_deviation', 'storey_balance']);

function Bar({ k, label, value }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const good = LOWER.has(k) ? 1 - v : v;
  return (
    <div className="bar" data-testid={`vscore-${k}`}>
      <span className="bar__label">{label}</span>
      <span className="bar__track"><span className="bar__fill" style={{ width: `${v * 100}%`, background: good > 0.66 ? '#4ecdc4' : good > 0.33 ? '#fdae6b' : '#e94560' }} /></span>
      <span className="bar__value">{(value ?? 0).toFixed(2)}</span>
    </div>
  );
}

/** Right-hand side in volume mode: the readings, the storeys, the selected body's size, and the sketch. */
export default function VolumePanel() {
  const result = useVolumeStore((s) => s.result);
  const selected = useVolumeStore((s) => s.selected);
  const scales = useVolumeStore((s) => s.scales);
  const sketch = useVolumeStore((s) => s.sketch);
  const sketching = useVolumeStore((s) => s.sketching);
  const { select, inflate, shiftStorey, freeSketch } = useVolumeStore.getState();
  if (!result) return <div className="gallery" data-testid="volume-panel"><h3>Volume</h3></div>;
  const body = result.bodies.find((b) => b.name === selected);
  const cell = result.cells.find((c) => c.name === selected);
  const failed = Object.entries(result.checks).filter(([, c]) => !c.passed);
  return (
    <div className="gallery" data-testid="volume-panel">
      <h3>Readings</h3>
      <div className="card card--current">
        <div className="card__head"><span>{result.kind} · seed {result.seed}</span><span className="card__sig">{result.ok ? 'passes' : 'fails a check'}</span></div>
        {SCORES.map(([k, label]) => <Bar key={k} k={k} label={label} value={result.scores[k]} />)}
        <div className="card__analysis">every room is ×{result.fill.toFixed(2)} its asked area, so the void is full</div>
        {failed.map(([k, c]) => <div key={k} className="card__unmet">{k}: {c.detail}</div>)}
      </div>
      <h3>Storeys</h3>
      {result.storeys.slice().reverse().map((s) => (
        <div key={s.level} className="card__analysis" data-testid="storey-row">level {s.level}: asked {s.asked} m² of {s.has} m²</div>
      ))}
      <h3>Body</h3>
      {body ? (
        <div className="card" data-testid="body-card">
          <div className="card__head"><span>{body.name.replace(/_/g, ' ')}</span><span className="card__sig">level {body.level}{body.storeys > 1 ? `–${body.level + body.storeys - 1}` : ''}</span></div>
          <div className="card__analysis" data-testid="body-area">{cell ? `${cell.area} m² (asked ${cell.want})` : 'no ground'}</div>
          <label className="field__slider">size ×{(scales[body.name] || 1).toFixed(2)}
            <input type="range" min={0.5} max={2.5} step={0.05} defaultValue={scales[body.name] || 1} key={body.name}
                   onMouseUp={(e) => inflate(body.name, parseFloat(e.target.value))} onKeyUp={(e) => inflate(body.name, parseFloat(e.target.value))}
                   data-testid="body-size" />
          </label>
          <button onClick={() => shiftStorey(body.name, 1)} data-testid="body-up">storey up</button>{' '}
          <button onClick={() => shiftStorey(body.name, -1)} data-testid="body-down">storey down</button>
        </div>
      ) : <div className="card__analysis">click a body in the view, or a name below</div>}
      <div className="field__names">
        {result.bodies.map((b) => (
          <button key={b.name} className={b.name === selected ? 'primary' : ''} onClick={() => select(b.name)} data-testid="body-name">{b.name.replace(/_/g, ' ')}</button>
        ))}
      </div>
      <h3>Sketch</h3>
      <button className="primary" disabled={sketching} onClick={freeSketch} data-testid="sketch-button">{sketching ? 'building in topologic…' : 'Free cells from these bodies'}</button>
      {sketch && (
        <div className="card__analysis" data-testid="sketch-info">
          {sketch.cells_built} cells for {sketch.rooms} rooms · volume off {sketch.volume_off} · faces: {sketch.faces.level} level, {sketch.faces.upright} upright, {sketch.faces.sloping} sloping.
          A sketch: sloping walls are not scored.
        </div>
      )}
    </div>
  );
}
