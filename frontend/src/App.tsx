import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { TopNav } from './components/TopNav';
import HistoryPage from './pages/HistoryPage';
import HomePage from './pages/HomePage';
import InvestigationPage from './pages/InvestigationPage';
import SettingsPage from './pages/SettingsPage';
import SkillsPage from './pages/SkillsPage';

function AppLayout() {
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <TopNav />
      <main id="main-content" className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

/** Remount the home page on every navigation to /sre so "New Investigation" clears the form. */
function HomeRoute() {
  const location = useLocation();
  return <HomePage key={location.key} />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/sre" replace />} />
      <Route path="/sre" element={<AppLayout />}>
        <Route index element={<HomeRoute />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="/sre/:id" element={<InvestigationPage />} />
      <Route path="*" element={<Navigate to="/sre" replace />} />
    </Routes>
  );
}
