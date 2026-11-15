import useAppStore from '../../stores/appStore';
import { isHard, missed, sentence, turnedText } from './affinityText';
import './OptionsGallery.css';

const MAX_MISSED = 6;

const METRICS = ['adjacency', 'deviation', 'compactness', 'circulation', 'stacking', 'vertical', 'daylight'];
const LOWER_IS_BETTER = new Set(['deviation', 'circulation']);

function Bar({ metric, value, separate }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const good = LOWER_IS_BETTER.has(metric) ? 1 - v : v;
  return (
    <div className={`bar ${separate ? 'bar--separate' : ''}`} title={`${metric}: ${value}`}>
      <span className="bar__label">{metric}</span>
      <span className="bar__track"><span className="bar__fill" style={{ width: `${v * 100}%`, background: good > 0.66 ? '#4ecdc4' : good > 0.33 ? '#fdae6b' : '#e94560' }} /></span>
      <span className="bar__value">{(value ?? 0).toFixed(2)}</span>
    </div>
  );
}

function NorthArrow({ deg }) {
  return (
    <svg className="card__north" width="18" height="18" viewBox="-10 -10 20 20" role="img" data-testid="north-arrow" aria-label={`North, ${deg}° from up`}>
      <title>{`North, ${deg}° from up`}</title>
      <g transform={`rotate(${deg})`}>
        <path d="M0 -8 L3.5 5 L0 2.5 L-3.5 5 Z" fill="#4ecdc4" />
      </g>
    </svg>
  );
}

function Affinity({ aff, orientation }) {
  const miss = missed(aff);
  const turned = turnedText(orientation);
  const hardMiss = aff.hard.met < aff.hard.total;
  return (
    <div data-testid="affinity">
      <Bar metric="affinity" value={aff.score} separate />
      {aff.site && typeof aff.site.north === 'number' && <NorthArrow deg={aff.site.north} />}
      {turned && <div className="card__analysis" data-testid="orientation-turned">{turned}</div>}
      <div className="card__analysis" data-testid="affinity-summary">
        soft wishes met {aff.soft.met} / {aff.soft.total}
        {' · '}
        <span className={hardMiss ? 'card__unmet' : ''}>hard wishes met {aff.hard.met} / {aff.hard.total}</span>
        {aff.unmeasured > 0 ? ` · ${aff.unmeasured} not measured yet` : ''}
      </div>
      {miss.slice(0, MAX_MISSED).map((it, k) => (
        <div key={k} className={`card__wish ${isHard(it) ? 'card__unmet' : ''}`} data-testid="affinity-missed">{sentence(it, aff.site)}</div>
      ))}
      {miss.length > MAX_MISSED && <div className="card__wish" data-testid="affinity-more">+ {miss.length - MAX_MISSED} more</div>}
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
          {o.ok && o.analysis && o.analysis.affinity && <Affinity aff={o.analysis.affinity} orientation={o.analysis.orientation} />}
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
