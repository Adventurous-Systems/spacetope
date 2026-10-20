import useAppStore from '../../stores/appStore';
import './OptionsGallery.css';

const METRICS = ['adjacency', 'deviation', 'compactness', 'circulation', 'stacking', 'vertical', 'daylight'];
const LOWER_IS_BETTER = new Set(['deviation', 'circulation']);

function Bar({ metric, value }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const good = LOWER_IS_BETTER.has(metric) ? 1 - v : v;
  return (
    <div className="bar" title={`${metric}: ${value}`}>
      <span className="bar__label">{metric}</span>
      <span className="bar__track"><span className="bar__fill" style={{ width: `${v * 100}%`, background: good > 0.66 ? '#4ecdc4' : good > 0.33 ? '#fdae6b' : '#e94560' }} /></span>
      <span className="bar__value">{(value ?? 0).toFixed(2)}</span>
    </div>
  );
}

export default function OptionsGallery() {
  const options = useAppStore((s) => s.options);
  const expanded = useAppStore((s) => s.expanded);
  const required = (expanded?.contacts || []).map((c) => [c[0], c[1]].sort().join('|'));
  const unmet = (o) => {
    const have = new Set(o.signature.map((sg) => [sg[0], sg[2]].sort().join('|')));
    return required.filter((r) => !have.has(r));
  };
  const current = useAppStore((s) => s.current);
  const viewOption = useAppStore((s) => s.viewOption);
  const selectAndExport = useAppStore((s) => s.selectAndExport);
  const exported = useAppStore((s) => s.exported);
  return (
    <div className="gallery" data-testid="options-gallery">
      <h3>Options ({options.length})</h3>
      {options.map((o) => (
        <div key={o.index} className={`card ${o.index === current ? 'card--current' : ''} ${o.ok ? '' : 'card--failed'}`}
             onClick={() => viewOption(o.index)} data-testid="option-card">
          <div className="card__head">
            <span>#{o.index} {o.ok ? '' : '✗ unverified'}</span>
            <span className="card__sig">
              {o.topology_class !== undefined && o.topology_class !== null && (
                <span className="card__class" data-testid="topology-class" title="Options with the same letter are the same plan up to rotation, mirroring and swaps of identical rooms">plan {String.fromCharCode(65 + (o.topology_class % 26))} · </span>
              )}
              {o.signature.length} contacts{o.doors ? ` · ${o.doors} doors` : ''}
            </span>
          </div>
          {o.ok && METRICS.map((m) => <Bar key={m} metric={m} value={o.scores[m]} />)}
          {o.ok && o.analysis && o.analysis.busiest && (
            <div className="card__analysis" data-testid="walk-analysis">
              busiest: {o.analysis.busiest}
              {o.analysis.cut_spaces && o.analysis.cut_spaces.length > 0 ? ` · everything passes through: ${o.analysis.cut_spaces.join(', ')}` : ''}
              {o.analysis.diameter !== undefined ? ` · ${o.analysis.diameter} doors end to end` : ''}
            </div>
          )}
          {o.ok && unmet(o).length > 0 && (
            <div className="card__unmet" data-testid="unmet-contacts">unmet: {unmet(o).map((r) => r.replace('|', ' – ')).join(', ')}</div>
          )}
          {!o.ok && <div className="card__fail">{Object.entries(o.verify.checks).filter(([, c]) => !c.passed).map(([k, c]) => `${k}: ${c.detail}`).join('; ')}</div>}
        </div>
      ))}
      {current != null && options[current]?.ok && (
        <button className="primary gallery__select" onClick={selectAndExport} data-testid="select-button">
          Select option #{current} and export
        </button>
      )}
      {exported && (
        <div className="gallery__exported" data-testid="exported">
          Exported: {Object.values(exported.selected).map((p) => <div key={p}>{p}</div>)}
        </div>
      )}
    </div>
  );
}
