import { Link, NavLink, useNavigate } from 'react-router-dom';
import { BookOpen, History, Plus, Puzzle, Search, Settings, Sparkle } from 'lucide-react';
import { DOCS_URL } from '../api/client';

const navClass = ({ isActive }: { isActive: boolean }) => `topnav__tab${isActive ? ' is-active' : ''}`;

export function Brand({ to = '/sre' }: { to?: string }) {
  return (
    <Link to={to} className="brand" aria-label="Bot Svc SRE home">
      <Sparkle size={14} className="brand__mark" aria-hidden="true" fill="currentColor" />
      <span>Bot Svc SRE</span>
    </Link>
  );
}

export function TopNav() {
  const navigate = useNavigate();
  return (
    <header className="topnav">
      <div className="topnav__left">
        <Brand />
        <nav className="topnav__tabs" aria-label="Primary">
          <NavLink to="/sre" end className={navClass}>
            <Search size={16} aria-hidden="true" />
            <span>Investigations</span>
          </NavLink>
          <NavLink to="/sre/history" className={navClass}>
            <History size={16} aria-hidden="true" />
            <span>History</span>
          </NavLink>
          <NavLink to="/sre/skills" className={navClass}>
            <Puzzle size={16} aria-hidden="true" />
            <span>Skills</span>
          </NavLink>
        </nav>
      </div>
      <div className="topnav__right">
        <a className="topnav__link topnav__link--docs" href={DOCS_URL} target="_blank" rel="noreferrer noopener">
          <BookOpen size={15} aria-hidden="true" />
          <span>Documentation</span>
        </a>
        <NavLink to="/sre/settings" className={({ isActive }) => `topnav__link${isActive ? ' is-active' : ''}`}>
          <Settings size={15} aria-hidden="true" />
          <span>Settings</span>
        </NavLink>
        <button
          type="button"
          className="btn btn--outline-accent btn--sm"
          onClick={() => navigate('/sre', { state: { fresh: Date.now() } })}
        >
          <Plus size={15} aria-hidden="true" />
          <span>New Investigation</span>
        </button>
      </div>
    </header>
  );
}
