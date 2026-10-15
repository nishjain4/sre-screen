import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Bot,
  Braces,
  ClipboardList,
  Clock,
  Copy,
  FileDown,
  FileSearch,
  FileText,
  Puzzle,
  Search,
  Share2,
  SquareX,
  User,
  Waypoints,
} from 'lucide-react';
import { api, errorMessage } from '../api/client';
import type { Investigation } from '../api/types';
import { AgentTrace } from '../components/AgentTrace';
import { Chip, SkillChip, StatusBadge } from '../components/Badges';
import { ChatPanel } from '../components/ChatPanel';
import { DropdownMenu } from '../components/DropdownMenu';
import { EmptyState, ErrorBanner, PageLoader, Spinner } from '../components/Feedback';
import { EvidenceView } from '../components/EvidenceView';
import { ReportView } from '../components/ReportView';
import { panelId, tabId, Tabs, type TabDef } from '../components/Tabs';
import { TimelineView } from '../components/TimelineView';
import { Brand } from '../components/TopNav';
import { useInvestigation, type ConnectionState } from '../hooks/useInvestigation';
import { useDocumentTitle, useFlag, useNow } from '../hooks/useUtils';
import { copyText } from '../utils/clipboard';
import { elapsedMs, formatDateTime, formatDuration, formatRelative, pluralize } from '../utils/format';
import { allToolCalls, isActive, modeLabel } from '../utils/investigation';

type TabKey = 'report' | 'trace' | 'timeline' | 'evidence';
const TAB_PREFIX = 'investigation';

// --------------------------------------------------------------------------- //
// Header
// --------------------------------------------------------------------------- //
function TimingInfo({ inv }: { inv: Investigation }) {
  const active = isActive(inv.status);
  const now = useNow(active ? 1000 : 30_000);

  if (inv.status === 'queued') {
    return <span className="detail-header__timing">Queued {formatRelative(inv.created_at, now)}</span>;
  }
  if (inv.status === 'running') {
    const elapsed = elapsedMs(inv.started_at ?? inv.created_at, now);
    return (
      <span className="detail-header__timing" aria-live="off">
        Running for <strong>{formatDuration(elapsed, false)}</strong>
      </span>
    );
  }
  const verb = inv.status === 'completed' ? 'Completed in' : inv.status === 'failed' ? 'Failed after' : 'Cancelled after';
  const duration = inv.duration_ms ?? elapsedMs(inv.started_at ?? inv.created_at, inv.finished_at);
  return (
    <>
      {duration !== null && (
        <span className="detail-header__timing">
          {verb} <strong>{formatDuration(duration, false)}</strong>
        </span>
      )}
      {inv.finished_at && (
        <span className="detail-header__timing" title={formatDateTime(inv.finished_at)}>
          Finished {formatRelative(inv.finished_at, now)}
        </span>
      )}
    </>
  );
}

function ConnectionNotice({ connection, active }: { connection: ConnectionState; active: boolean }) {
  if (!active || connection !== 'reconnecting') return null;
  return (
    <span className="connection-notice" role="status">
      <Spinner size={12} /> Reconnecting to live updates…
    </span>
  );
}

function ShareMenu({ inv }: { inv: Investigation }) {
  const [copied, flagCopied] = useFlag();
  const [error, setError] = useState<string | null>(null);

  const download = async (format: 'markdown' | 'json') => {
    setError(null);
    try {
      await api.downloadExport(inv.id, format);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="share-menu">
      <DropdownMenu
        icon={<Share2 size={14} aria-hidden="true" />}
        label={copied ? 'Link copied' : 'Share / Export'}
        items={[
          {
            id: 'copy',
            label: 'Copy link',
            icon: <Copy size={14} aria-hidden="true" />,
            onSelect: () => {
              void copyText(window.location.href).then((ok) => ok && flagCopied());
            },
          },
          {
            id: 'markdown',
            label: 'Download Markdown',
            icon: <FileDown size={14} aria-hidden="true" />,
            onSelect: () => void download('markdown'),
          },
          {
            id: 'json',
            label: 'Download JSON',
            icon: <Braces size={14} aria-hidden="true" />,
            onSelect: () => void download('json'),
          },
        ]}
      />
      {error && (
        <span className="inline-error share-menu__error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

function InvestigationHeader({
  inv,
  connection,
  onCancel,
}: {
  inv: Investigation;
  connection: ConnectionState;
  onCancel: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const active = isActive(inv.status);
  const skills = inv.selected_skill_ids;

  const cancel = async () => {
    setCancelling(true);
    setCancelError(null);
    try {
      await onCancel();
    } catch (err) {
      setCancelError(errorMessage(err));
    } finally {
      setCancelling(false);
    }
  };

  return (
    <header className="detail-header">
      <div className="detail-header__top">
        <button type="button" className="icon-btn icon-btn--plain" onClick={() => navigate('/sre')} aria-label="Back to investigations">
          <ArrowLeft size={18} aria-hidden="true" />
        </button>
        <Brand />
        <span className="detail-header__divider" aria-hidden="true" />
        <StatusBadge status={inv.status} outcome={inv.outcome} />
        <TimingInfo inv={inv} />
        <ConnectionNotice connection={connection} active={active} />
      </div>

      <div className="detail-header__main">
        <div className="detail-header__info">
          <h1 className="detail-header__title">{inv.title || inv.query}</h1>
          <div className="detail-header__chips">
            <Chip icon={<Search size={13} aria-hidden="true" />}>Mode: {modeLabel(inv.mode)}</Chip>
            <Chip icon={<User size={13} aria-hidden="true" />}>Initiated by {inv.initiated_by || 'anonymous'}</Chip>
            {inv.llm && <Chip icon={<Bot size={13} aria-hidden="true" />}>LLM: {inv.llm}</Chip>}
          </div>
          <div className="detail-header__skills">
            <Puzzle size={14} aria-hidden="true" />
            <span>Skills: {pluralize(skills.length, 'skill')}</span>
            {skills.map((id) => (
              <SkillChip key={id}>{id}</SkillChip>
            ))}
            {skills.length === 0 && active && inv.mode !== 'none' && <span className="muted">selecting…</span>}
          </div>
        </div>
        <div className="detail-header__actions">
          <ShareMenu inv={inv} />
          {active && (
            <button type="button" className="btn btn--danger-outline btn--sm" onClick={() => void cancel()} disabled={cancelling}>
              {cancelling ? <Spinner size={14} /> : <SquareX size={14} aria-hidden="true" />}
              Cancel
            </button>
          )}
          {cancelError && (
            <span className="inline-error" role="alert">
              {cancelError}
            </span>
          )}
        </div>
      </div>
      {active && <div className="progress-bar" role="progressbar" aria-label="Investigation in progress" />}
    </header>
  );
}

// --------------------------------------------------------------------------- //
// Main content
// --------------------------------------------------------------------------- //
function ReportTab({ inv }: { inv: Investigation }) {
  if (inv.report) return <ReportView report={inv.report} />;
  if (isActive(inv.status)) {
    return (
      <EmptyState
        icon={<Spinner size={22} />}
        title="Report in progress"
        description="The report will appear here once the agent finishes its analysis. Follow progress in the Agent Trace."
      />
    );
  }
  return (
    <EmptyState
      icon={<FileText size={22} />}
      title="No report available"
      description={
        inv.status === 'failed'
          ? 'The investigation failed before a report could be generated.'
          : inv.status === 'cancelled'
            ? 'The investigation was cancelled before a report was generated.'
            : 'This investigation did not produce a report.'
      }
    />
  );
}

function InvestigationView({
  inv,
  connection,
  actions,
}: {
  inv: Investigation;
  connection: ConnectionState;
  actions: ReturnType<typeof useInvestigation>['actions'];
}) {
  const [manualTab, setManualTab] = useState<TabKey | null>(null);
  const activeTab: TabKey = manualTab ?? (inv.report ? 'report' : 'trace');
  const toolCallCount = allToolCalls(inv).length;

  const tabs: TabDef<TabKey>[] = [
    { id: 'report', label: 'Report', icon: <ClipboardList size={15} aria-hidden="true" /> },
    { id: 'trace', label: 'Agent Trace', icon: <Waypoints size={15} aria-hidden="true" />, count: inv.steps.length },
    { id: 'timeline', label: 'Timeline', icon: <Clock size={15} aria-hidden="true" />, count: inv.timeline.length },
    { id: 'evidence', label: 'Evidence', icon: <FileSearch size={15} aria-hidden="true" />, count: toolCallCount },
  ];

  return (
    <div className="detail">
      <InvestigationHeader inv={inv} connection={connection} onCancel={actions.cancel} />
      <div className="detail__body">
        <div className="detail__chat">
          <ChatPanel investigation={inv} onSend={actions.sendChat} onFeedback={actions.submitFeedback} />
        </div>
        <main className="detail__main">
          <div className="detail__tabs">
            <Tabs tabs={tabs} active={activeTab} onChange={setManualTab} idPrefix={TAB_PREFIX} ariaLabel="Investigation views" />
          </div>
          <div className="detail__content">
            {inv.status === 'failed' && inv.error && (
              <ErrorBanner title="Investigation failed" message={inv.error} />
            )}
            <div
              role="tabpanel"
              id={panelId(TAB_PREFIX, activeTab)}
              aria-labelledby={tabId(TAB_PREFIX, activeTab)}
              tabIndex={0}
              className="detail__panel"
            >
              {activeTab === 'report' && <ReportTab inv={inv} />}
              {activeTab === 'trace' && <AgentTrace investigation={inv} />}
              {activeTab === 'timeline' && <TimelineView events={inv.timeline} />}
              {activeTab === 'evidence' && <EvidenceView investigation={inv} />}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function NotFound({ id }: { id: string }) {
  return (
    <div className="detail-fallback">
      <EmptyState
        icon={<FileSearch size={22} />}
        title="Investigation not found"
        description={
          <>
            No investigation exists with id <code>{id}</code>. It may have been deleted.
          </>
        }
        action={
          <Link to="/sre" className="btn btn--primary">
            Start a new investigation
          </Link>
        }
      />
    </div>
  );
}

export default function InvestigationPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { state, actions } = useInvestigation(id);
  const { investigation, loading, error, notFound, connection } = state;
  useDocumentTitle(investigation?.title || (notFound ? 'Not found' : 'Investigation'));

  if (notFound) return <NotFound id={id} />;
  if (!investigation) {
    if (loading) return <PageLoader label="Loading investigation…" />;
    return (
      <div className="detail-fallback">
        <ErrorBanner title="Couldn't load the investigation" message={error ?? 'Unknown error'} onRetry={actions.reload} />
        <Link to="/sre" className="link-accent">
          <ArrowLeft size={14} aria-hidden="true" /> Back to investigations
        </Link>
      </div>
    );
  }
  return <InvestigationView key={investigation.id} inv={investigation} connection={connection} actions={actions} />;
}
