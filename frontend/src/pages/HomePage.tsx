import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, ShieldHalf, Sparkle } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import type { SkillMode, TemplateInfo } from '../api/types';
import { StatusBadge } from '../components/Badges';
import { ErrorBanner, SkeletonCard, Spinner } from '../components/Feedback';
import { IconTile } from '../components/Icon';
import { SkillSelector } from '../components/SkillSelector';
import { useApi } from '../hooks/useApi';
import { useDocumentTitle, useNow } from '../hooks/useUtils';
import { formatRelative, truncate } from '../utils/format';

const PLACEHOLDER = [
  'e.g. Summarize this Gitea repository',
  'Review pull request #123 for bugs',
  'What changed in the latest commit?',
].join('\n');

const MIN_QUERY = 3;
const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

function groupByCategory(templates: TemplateInfo[]): [string, TemplateInfo[]][] {
  const groups = new Map<string, TemplateInfo[]>();
  for (const template of templates) {
    const key = template.category || 'other';
    const list = groups.get(key);
    if (list) list.push(template);
    else groups.set(key, [template]);
  }
  return Array.from(groups.entries());
}

function RecentInvestigations() {
  const recent = useApi((signal) => api.listInvestigations({ limit: 5 }, signal), []);
  const now = useNow(30_000);
  const items = recent.data?.items ?? [];
  if (recent.error || (!recent.loading && items.length === 0) || (recent.loading && !recent.data)) return null;
  return (
    <section className="home-section" aria-labelledby="recent-heading">
      <div className="home-section__header">
        <h2 id="recent-heading">Recent investigations</h2>
        <Link to="/sre/history" className="link-accent">
          View all <ArrowRight size={14} aria-hidden="true" />
        </Link>
      </div>
      <ul className="recent-list">
        {items.map((item) => (
          <li key={item.id}>
            <Link to={`/sre/${item.id}`} className="card recent-item">
              <StatusBadge status={item.status} outcome={item.outcome} />
              <span className="recent-item__title">{truncate(item.title || item.query, 90)}</span>
              <span className="recent-item__time">{formatRelative(item.created_at, now)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function HomePage() {
  useDocumentTitle('New investigation');
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<SkillMode>('auto');
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [server, setServer] = useState('');
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const skills = useApi(api.skills, []);
  const templates = useApi(api.templates, []);
  const servers = Array.from(new Set(skills.data?.flatMap((skill) => skill.mcp_servers) ?? [])).sort();
  const selectedServer = servers.includes(server) ? server : servers[0] ?? '';

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const trimmed = query.trim();
  const canSubmit = trimmed.length >= MIN_QUERY && !submitting && !(mode === 'specific' && skillIds.length === 0);

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const investigation = await api.createInvestigation({
        query: trimmed,
        mode,
        skill_ids: mode === 'specific' ? skillIds : [],
        context: {},
        template_id: templateId,
      });
      navigate(`/sre/${investigation.id}`);
    } catch (err) {
      setSubmitError(errorMessage(err));
      setSubmitting(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void submit();
    }
  };

  const applyTemplate = (template: TemplateInfo) => {
    const specific = template.mode === 'specific' && template.skill_ids.length > 0;
    setQuery(template.query);
    setMode(specific ? 'specific' : template.mode === 'specific' ? 'auto' : template.mode);
    setSkillIds(specific ? template.skill_ids : []);
    const templateServer = skills.data?.find((skill) => specific && template.skill_ids.includes(skill.id))?.mcp_servers[0];
    setServer(templateServer ?? selectedServer);
    setTemplateId(template.id);
    setSubmitError(null);
    const el = textareaRef.current;
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.focus({ preventScroll: true });
      // Place the caret at the end once React has applied the new value.
      requestAnimationFrame(() => el.setSelectionRange(el.value.length, el.value.length));
    }
  };

  const groups = templates.data ? groupByCategory(templates.data) : [];

  return (
    <div className="home">
      <section className="hero" aria-labelledby="hero-title">
        <span className="hero__badge" aria-hidden="true">
          <ShieldHalf size={22} />
        </span>
        <h1 id="hero-title">What can I help you investigate?</h1>
        <p className="hero__eyebrow">Bot Svc SRE — Automated Incident Intelligence</p>
        <p className="hero__subtitle">Describe the issue and specify the relevant service, host, or entity</p>
      </section>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label htmlFor="investigation-query" className="sr-only">
          Describe the issue to investigate
        </label>
        <textarea
          id="investigation-query"
          ref={textareaRef}
          className="composer__input"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            if (!event.target.value.trim()) setTemplateId(null);
          }}
          onKeyDown={onKeyDown}
          placeholder={PLACEHOLDER}
          rows={4}
          maxLength={20_000}
          disabled={submitting}
          aria-describedby="composer-hint"
        />
        <div className="composer__footer">
          <SkillSelector
            mode={mode}
            skillIds={skillIds}
            skills={skills.data}
            server={selectedServer}
            servers={servers}
            loading={skills.loading}
            error={skills.error ? errorMessage(skills.error) : null}
            onRetry={skills.reload}
            onServerChange={(nextServer) => {
              setServer(nextServer);
              const nextIds = skillIds.filter((id) =>
                skills.data?.find((skill) => skill.id === id)?.mcp_servers.includes(nextServer),
              );
              if (mode === 'specific' && nextIds.length !== skillIds.length) {
                setSkillIds(nextIds);
                setMode(nextIds.length > 0 ? 'specific' : 'auto');
              }
            }}
            onChange={(nextMode, nextIds) => {
              setMode(nextMode);
              setSkillIds(nextIds);
            }}
            disabled={submitting}
          />
          <div className="composer__actions">
            <span id="composer-hint" className="composer__hint">
              {isMac ? '⌘' : 'Ctrl'} + Enter to investigate
            </span>
            <button type="submit" className="btn btn--lavender" disabled={!canSubmit} aria-busy={submitting}>
              {submitting ? <Spinner size={14} /> : <Sparkle size={14} fill="currentColor" aria-hidden="true" />}
              {submitting ? 'Starting…' : 'Investigate'}
            </button>
          </div>
        </div>
      </form>
      {submitError && (
        <div className="composer__error">
          <ErrorBanner title="Couldn't start the investigation" message={submitError} onRetry={() => void submit()} />
        </div>
      )}

      <section className="home-section" aria-labelledby="templates-heading">
        <div className="home-section__header">
          <h2 id="templates-heading">Investigation Templates</h2>
        </div>
        {templates.loading && !templates.data && (
          <div className="template-grid">
            <SkeletonCard lines={1} />
            <SkeletonCard lines={1} />
          </div>
        )}
        {templates.error && (
          <ErrorBanner
            title="Couldn't load templates"
            message={errorMessage(templates.error)}
            onRetry={templates.reload}
          />
        )}
        {templates.data && templates.data.length === 0 && <p className="muted">No templates available.</p>}
        {groups.map(([category, items]) => (
          <div key={category} className="template-group">
            <h3 className="template-group__title">{category}</h3>
            <div className="template-grid">
              {items.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  className={`card template-card${templateId === template.id ? ' is-selected' : ''}`}
                  onClick={() => applyTemplate(template)}
                >
                  <IconTile name={template.icon} />
                  <span className="template-card__text">
                    <span className="template-card__title">{template.title}</span>
                    <span className="template-card__desc">{template.description}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </section>

      <RecentInvestigations />
    </div>
  );
}
