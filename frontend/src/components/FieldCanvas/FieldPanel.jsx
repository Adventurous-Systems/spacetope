import useFieldStore from '../../stores/fieldStore';
import './FieldCanvas.css';

const SCORES = [['affinity', 'wishes met'], ['area_deviation', 'area off'], ['compactness', 'compact'], ['exposure', 'outside wall'],
  ['regularity', 'regular rooms'], ['vertical', 'reach'], ['circulation', 'circulation'], ['coverage', 'ground used']];
const LOWER = new Set(['area_deviation', 'circulation', 'coverage']);

function Bar({ k, label, value }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const good = LOWER.has(k) ? 1 - v : v;
  return (
    <div className="bar" title={`${k}: ${value}`} data-testid={`score-${k}`}>
      <span className="bar__label">{label}</span>
      <span className="bar__track"><span className="bar__fill" style={{ width: `${v * 100}%`, background: good > 0.66 ? '#4ecdc4' : good > 0.33 ? '#fdae6b' : '#e94560' }} /></span>
      <span className="bar__value">{(value ?? 0).toFixed(2)}</span>
    </div>
  );
}

function Checks({ checks }) {
  return Object.entries(checks || {}).filter(([, c]) => !c.passed).map(([k, c]) => (
    <div key={k} className="card__unmet" data-testid="field-check-failed">{k}: {c.detail}</div>
  ));
}

/** Right-hand side in field mode: the live reading, then the options that each do one thing best. */
export default function FieldPanel() {
  const result = useFieldStore((s) => s.result);
  const options = useFieldStore((s) => s.options);
  const info = useFieldStore((s) => s.optionsInfo);
  const current = useFieldStore((s) => s.current);
  const generating = useFieldStore((s) => s.generating);
  const { generate, view } = useFieldStore.getState();
  const aff = result?.affinity;
  return (
    <div className="gallery" data-testid="field-panel">
      <h3>Live</h3>
      {result && (
        <div className={`card ${current == null ? 'card--current' : ''}`} onClick={() => view(null)} data-testid="field-live-card">
          <div className="card__head"><span>{result.kind} · seed {result.seed}</span><span className="card__sig">{result.ok ? 'passes' : 'fails a check'}</span></div>
          {SCORES.map(([k, label]) => <Bar key={k} k={k} label={label} value={result.scores[k]} />)}
          {aff && <div className="card__analysis">soft wishes met {aff.soft.met} / {aff.soft.total} · hard {aff.hard.met} / {aff.hard.total}</div>}
          <Checks checks={result.checks} />
        </div>
      )}
      <h3>Options</h3>
      <button className="primary" disabled={!result || generating} onClick={generate} data-testid="field-generate">
        {generating ? 'building in topologic…' : 'Best option per aspect'}
      </button>
      {info && <div className="card__analysis" data-testid="field-info">{info.candidates} candidates, {info.passed} passed, {info.chosen} chosen in {info.seconds}s</div>}
      {options.map((o) => (
        <div key={o.index} className={`card ${o.index === current ? 'card--current' : ''} ${o.ok ? '' : 'card--failed'}`} onClick={() => view(o.index)} data-testid="field-option">
          <div className="card__head"><span>{o.champion.join(' · ')}</span><span className="card__sig">{o.kind} · seed {o.seed}{o.ok ? '' : ' ✗'}</span></div>
          {SCORES.map(([k, label]) => <Bar key={k} k={k} label={label} value={o.scores[k]} />)}
          <Checks checks={{ ...o.checks, ...(o.verify?.checks || {}) }} />
        </div>
      ))}
    </div>
  );
}
