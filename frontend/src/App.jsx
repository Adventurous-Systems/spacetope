// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

import BriefEditor from './components/BriefEditor/BriefEditor';
import AssemblyCanvas from './components/AssemblyCanvas/AssemblyCanvas';
import OptionsGallery from './components/OptionsGallery/OptionsGallery';
import useAppStore from './stores/appStore';

export default function App() {
  const status = useAppStore((s) => s.status);
  const error = useAppStore((s) => s.error);
  return (
    <div className="app">
      <header className="app__header">
        <span className="app__brand">spacetope</span>
        <span className="app__status" data-testid="status">{status}{error ? ` — ${error}` : ''}</span>
      </header>
      <div className="app__body">
        <aside className="app__left"><BriefEditor /></aside>
        <main className="app__canvas"><AssemblyCanvas /></main>
        <aside className="app__right"><OptionsGallery /></aside>
      </div>
    </div>
  );
}
