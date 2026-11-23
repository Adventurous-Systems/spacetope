import { useState } from 'react';
import BriefEditor from './components/BriefEditor/BriefEditor';
import AssemblyCanvas from './components/AssemblyCanvas/AssemblyCanvas';
import OptionsGallery from './components/OptionsGallery/OptionsGallery';
import FieldCanvas from './components/FieldCanvas/FieldCanvas';
import FieldPanel from './components/FieldCanvas/FieldPanel';
import VolumeCanvas from './components/FieldCanvas/VolumeCanvas';
import VolumePanel from './components/FieldCanvas/VolumePanel';
import useAppStore from './stores/appStore';

export default function App() {
  const status = useAppStore((s) => s.status);
  const error = useAppStore((s) => s.error);
  const [mode, setMode] = useState('rooms');   // rooms: boxes from contacts; field: cells from a site and a path; volume: bodies on springs in a void
  return (
    <div className="app">
      <header className="app__header">
        <span className="app__brand">spacetope</span>
        <span className="app__mode">
          <button className={mode === 'rooms' ? 'primary' : ''} onClick={() => setMode('rooms')} data-testid="mode-rooms">rooms</button>
          <button className={mode === 'field' ? 'primary' : ''} onClick={() => setMode('field')} data-testid="mode-field">field</button>
          <button className={mode === 'volume' ? 'primary' : ''} onClick={() => setMode('volume')} data-testid="mode-volume">volume</button>
        </span>
        {mode === 'rooms' && <span className="app__status" data-testid="status">{status}{error ? ` — ${error}` : ''}</span>}
      </header>
      {mode === 'rooms' ? (
        <div className="app__body">
          <aside className="app__left"><BriefEditor /></aside>
          <main className="app__canvas"><AssemblyCanvas /></main>
          <aside className="app__right"><OptionsGallery /></aside>
        </div>
      ) : (
        <div className="app__body app__body--field">
          <main className="app__canvas">{mode === 'field' ? <FieldCanvas /> : <VolumeCanvas />}</main>
          <aside className="app__right">{mode === 'field' ? <FieldPanel /> : <VolumePanel />}</aside>
        </div>
      )}
    </div>
  );
}
