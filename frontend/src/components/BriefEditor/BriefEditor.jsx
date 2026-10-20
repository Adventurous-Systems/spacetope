import { useEffect, useMemo } from 'react';
import useAppStore from '../../stores/appStore';
import './BriefEditor.css';

const SPACE_PROGRAMS = ['room', 'corridor', 'void'];
const DOOR_W = { room: 0.9, stair: 1.0, lift: 1.1 };
const num = (v, fallback = 0) => { const x = parseFloat(v); return Number.isFinite(x) ? x : fallback; };

/** Names the API will generate from the circulation section (mirrors spacetope.brief.generated_names). */
function generatedNames(brief) {
  const c = brief.circulation || {};
  const n = brief.levels || 1;
  const out = c.corridor ? Array.from({ length: n }, (_, k) => `corridor_${k}`) : [];
  for (const key of ['stairs', 'lifts']) for (const item of c[key] || []) if (item.name) out.push(item.name);
  return out;
}

export default function BriefEditor() {
  const fixtures = useAppStore((s) => s.fixtures);
  const loadFixtures = useAppStore((s) => s.loadFixtures);
  const loadFixture = useAppStore((s) => s.loadFixture);
  const brief = useAppStore((s) => s.brief);
  const setBrief = useAppStore((s) => s.setBrief);
  const expanded = useAppStore((s) => s.expanded);
  const problems = useAppStore((s) => s.problems);
  const warnings = useAppStore((s) => s.warnings);
  const capabilities = useAppStore((s) => s.capabilities);
  const generator = useAppStore((s) => s.generator);
  const setGenerator = useAppStore((s) => s.setGenerator);
  const seed = useAppStore((s) => s.seed);
  const setSeed = useAppStore((s) => s.setSeed);
  const generate = useAppStore((s) => s.generate);
  const status = useAppStore((s) => s.status);
  useEffect(() => { loadFixtures(); }, [loadFixtures]);

  const names = useMemo(() => (brief ? [...brief.spaces.map((s) => s.name), ...generatedNames(brief)] : []), [brief]);
  const levels = brief?.levels || 1;
  const circ = brief?.circulation || null;
  const contacts = brief?.contacts || [];
  const doors = circ?.doors || {};
  const levelOptions = Array.from({ length: levels }, (_, k) => <option key={k} value={k}>{k}</option>);
  const busy = status.startsWith('generating') || status.startsWith('checking');
  const treemapBlocked = levels > 1 && capabilities.treemap && capabilities.treemap.multi_level === false;
  const dualBlocked = levels > 1 && (!capabilities.dual || capabilities.dual.multi_level === false);

  const patch = (p) => setBrief({ ...brief, ...p });
  const setCirc = (c) => patch({ circulation: c });
  const updateSpace = (i, key, value) => patch({ spaces: brief.spaces.map((s, j) => (j === i ? { ...s, [key]: value } : s)) });
  const setLevelWish = (i, value) => patch({
    spaces: brief.spaces.map((s, j) => {
      if (j !== i) return s;
      const wishes = { ...(s.wishes || {}) };
      if (value === '') delete wishes.level; else wishes.level = parseInt(value, 10);
      return { ...s, wishes };
    }),
  });
  const addSpace = () => patch({ spaces: [...brief.spaces, { name: `space_${brief.spaces.length + 1}`, w: 4, l: 3, h: 3, program: 'room' }] });
  const removeSpace = (i) => {
    const name = brief.spaces[i].name;
    patch({ spaces: brief.spaces.filter((_, j) => j !== i), contacts: contacts.filter((c) => c[0] !== name && c[1] !== name) });
  };
  const setContacts = (cs) => patch({ contacts: cs });
  const addContact = () => setContacts([...contacts, [names[0], names[1] || names[0]]]);
  const updateContact = (i, k, v) => setContacts(contacts.map((c, j) => { if (j !== i) return c; const next = [...c]; next[k] = v; return next; }));
  const toggleDoor = (i) => setContacts(contacts.map((c, j) => (j !== i ? c : (c[2]?.door ? [c[0], c[1]] : [c[0], c[1], { door: true }]))));
  const removeContact = (i) => setContacts(contacts.filter((_, j) => j !== i));

  const shaftList = (key) => circ?.[key] || [];
  const setShafts = (key, items) => setCirc({ ...circ, [key]: items });
  const updateShaft = (key, i, field, value) => setShafts(key, shaftList(key).map((it, j) => (j === i ? { ...it, [field]: value } : it)));
  const setServes = (key, i, which, value) => setShafts(key, shaftList(key).map((it, j) => {
    if (j !== i) return it;
    const cur = it.serves ? [...it.serves] : [0, levels - 1];
    cur[which] = parseInt(value, 10);
    const next = { ...it, serves: cur };
    if (cur[0] === 0 && cur[1] === levels - 1) delete next.serves;  // default: all levels
    return next;
  }));
  const addShaft = (key) => {
    const count = shaftList(key).length;
    const base = key === 'stairs' ? { name: count ? `stair_${count + 1}` : 'stair', w: 3, l: 5 } : { name: count ? `lift_${count + 1}` : 'lift', w: 2.5, l: 2.5 };
    setShafts(key, [...shaftList(key), base]);
  };
  const removeShaft = (key, i) => setShafts(key, shaftList(key).filter((_, j) => j !== i));
  const setDoorWidth = (kind, value) => setCirc({ ...circ, doors: { ...doors, [kind]: { ...(doors[kind] || {}), w: value } } });
  const setDoorHeight = (value) => {
    const next = { ...doors };
    for (const kind of ['room', 'stair', 'lift']) next[kind] = { ...(next[kind] || {}), h: value };
    setCirc({ ...circ, doors: next });
  };

  return (
    <div className="brief" data-testid="brief-editor">
      <h3>Brief</h3>
      <div className="brief__row">
        <select onChange={(e) => e.target.value && loadFixture(e.target.value)} defaultValue="" data-testid="fixture-select">
          <option value="">load a fixture…</option>
          {fixtures.map((f) => <option key={f.name} value={f.name}>{f.name} ({f.spaces} spaces)</option>)}
        </select>
      </div>
      {brief && (
        <>
          <div className="brief__row">
            <label>name <input value={brief.name} onChange={(e) => patch({ name: e.target.value })} /></label>
            <label>levels <input type="number" min="1" style={{ width: 44 }} value={levels} data-testid="levels-input"
                                 onChange={(e) => patch({ levels: parseInt(e.target.value || '1', 10) })} /></label>
            <label>lvl h <input type="number" step="0.1" style={{ width: 50 }} value={brief.level_height ?? ''}
                                onChange={(e) => patch({ level_height: e.target.value ? num(e.target.value) : null })} /></label>
          </div>
          <div className="brief__row">
            <label>envelope w×l×h
              {['w', 'l', 'h'].map((k) => (
                <input key={k} type="number" step="0.5" style={{ width: 46 }} value={brief.envelope?.[k] ?? ''} placeholder={k}
                       onChange={(e) => {
                         const next = { ...(brief.envelope || {}) };
                         if (e.target.value === '') delete next[k]; else next[k] = num(e.target.value);
                         patch({ envelope: Object.keys(next).length ? next : null });   // empty only when all three are cleared
                       }} />
              ))}
            </label>
          </div>

          <h3>Circulation</h3>
          {!circ && (
            <button data-testid="add-circulation"
                    onClick={() => setCirc({ corridor: { w: 1.8, l: 10 }, stairs: levels > 1 ? [{ name: 'stair', w: 3, l: 5 }] : [], lifts: [] })}>
              + corridor per level, stairs and lifts
            </button>
          )}
          {circ && (
            <div className="brief__circ" data-testid="circulation">
              <div className="brief__row">
                <label>corridor w <input type="number" step="0.1" style={{ width: 44 }} value={circ.corridor?.w ?? ''}
                                         onChange={(e) => setCirc({ ...circ, corridor: { ...(circ.corridor || {}), w: num(e.target.value) } })} /></label>
                <label>l <input type="number" step="0.5" style={{ width: 44 }} value={circ.corridor?.l ?? ''}
                                onChange={(e) => setCirc({ ...circ, corridor: { ...(circ.corridor || {}), l: num(e.target.value) } })} /></label>
                <span className="brief__hint">{circ.corridor ? `corridor_0 … corridor_${levels - 1}` : 'no corridors'}</span>
              </div>
              {[['stairs', 'Stairs'], ['lifts', 'Lifts']].map(([key, label]) => (
                <div key={key}>
                  <div className="brief__sub">{label} <span className="brief__hint">one space through every level it serves</span></div>
                  {shaftList(key).map((it, i) => {
                    const serves = it.serves || [0, levels - 1];
                    return (
                      <div key={i} className="brief__row" data-testid={`${key}-row`}>
                        <input value={it.name} style={{ width: 64 }} onChange={(e) => updateShaft(key, i, 'name', e.target.value)} />
                        <label>w <input type="number" step="0.1" style={{ width: 40 }} value={it.w} onChange={(e) => updateShaft(key, i, 'w', num(e.target.value))} /></label>
                        <label>l <input type="number" step="0.1" style={{ width: 40 }} value={it.l} onChange={(e) => updateShaft(key, i, 'l', num(e.target.value))} /></label>
                        <label>levels
                          <select value={serves[0]} onChange={(e) => setServes(key, i, 0, e.target.value)} data-testid={`${key}-from-${i}`}>{levelOptions}</select>–
                          <select value={serves[1]} onChange={(e) => setServes(key, i, 1, e.target.value)} data-testid={`${key}-to-${i}`}>{levelOptions}</select>
                        </label>
                        <button onClick={() => removeShaft(key, i)} title="remove">×</button>
                      </div>
                    );
                  })}
                  <button onClick={() => addShaft(key)}>+ {key === 'stairs' ? 'stair' : 'lift'}</button>
                </div>
              ))}
              <div className="brief__sub">Doors (m)</div>
              <div className="brief__row">
                {['room', 'stair', 'lift'].map((kind) => (
                  <label key={kind}>{kind} <input type="number" step="0.05" style={{ width: 44 }} value={doors[kind]?.w ?? DOOR_W[kind]}
                                                  onChange={(e) => setDoorWidth(kind, num(e.target.value))} /></label>
                ))}
                <label>h <input type="number" step="0.05" style={{ width: 44 }} value={doors.room?.h ?? 2.1} onChange={(e) => setDoorHeight(num(e.target.value))} /></label>
                <label>jamb <input type="number" step="0.05" style={{ width: 44 }} value={doors.jamb ?? 0.1}
                                   onChange={(e) => setCirc({ ...circ, doors: { ...doors, jamb: num(e.target.value) } })} /></label>
              </div>
            </div>
          )}

          <h3>Spaces ({brief.spaces.length})</h3>
          <table className="brief__table" data-testid="spaces-table">
            <thead><tr><th>name</th><th>w</th><th>l</th><th>h</th><th>program</th><th>level</th><th /></tr></thead>
            <tbody>
              {brief.spaces.map((s, i) => (
                <tr key={i} data-testid="space-row">
                  <td><input value={s.name} onChange={(e) => updateSpace(i, 'name', e.target.value)} /></td>
                  {['w', 'l', 'h'].map((k) => (
                    <td key={k}><input type="number" step="0.1" value={s[k]} onChange={(e) => updateSpace(i, k, num(e.target.value))} /></td>
                  ))}
                  <td>
                    <select value={s.program || 'room'} onChange={(e) => updateSpace(i, 'program', e.target.value)}>
                      {[...new Set([...SPACE_PROGRAMS, s.program || 'room'])].map((p) => <option key={p}>{p}</option>)}
                    </select>
                  </td>
                  <td>
                    <select value={s.wishes?.level ?? ''} onChange={(e) => setLevelWish(i, e.target.value)}>
                      <option value="">auto</option>{levelOptions}
                    </select>
                  </td>
                  <td><button onClick={() => removeSpace(i)} title="remove">×</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={addSpace}>+ space</button>

          <h3>Required contacts ({contacts.length})</h3>
          <div className="brief__contacts">
            {contacts.map((c, i) => (
              <div key={i} className="brief__row" data-testid="contact-row">
                {[0, 1].map((k) => (
                  <select key={k} value={c[k]} onChange={(e) => updateContact(i, k, e.target.value)}>
                    {[...new Set([...names, c[k]])].map((n) => <option key={n}>{n}</option>)}
                  </select>
                ))}
                <label title="put a door in this wall"><input type="checkbox" checked={!!c[2]?.door} onChange={() => toggleDoor(i)} /> door</label>
                <button onClick={() => removeContact(i)}>×</button>
              </div>
            ))}
            <button onClick={addContact}>+ contact</button>
          </div>

          {problems.length > 0 && (
            <ul className="brief__problems" data-testid="brief-problems">
              {problems.map((p, i) => (
                <li key={i} className={`brief__problem brief__problem--${p.severity || 'error'}`} data-testid="brief-problem">{p.message}</li>
              ))}
            </ul>
          )}
          {warnings.length > 0 && (
            <ul className="brief__problems">
              {warnings.map((p, i) => <li key={i} className="brief__problem brief__problem--warning">{p.message}</li>)}
            </ul>
          )}
          {expanded && <div className="brief__hint" data-testid="expanded-count">{expanded.spaces.length} spaces after expansion</div>}

          <h3>Generate</h3>
          <div className="brief__row">
            <select value={generator} onChange={(e) => setGenerator(e.target.value)} data-testid="generator-select">
              <option value="beam">beam (fast)</option>
              <option value="cpsat">cpsat (exact)</option>
              <option value="treemap" disabled={treemapBlocked}>treemap (baseline{treemapBlocked ? ', single level only' : ''})</option>
              <option value="dual" disabled={dualBlocked}>dual (all plan topologies{dualBlocked ? ', single level only' : ''})</option>
            </select>
            <label>seed <input type="number" style={{ width: 50 }} value={seed} onChange={(e) => setSeed(parseInt(e.target.value || '0', 10))} /></label>
            <button className="primary" onClick={generate} disabled={busy} data-testid="generate-button">{busy ? 'working…' : 'Generate'}</button>
          </div>
        </>
      )}
    </div>
  );
}
