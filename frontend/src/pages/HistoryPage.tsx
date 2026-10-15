import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, History as HistoryIcon, Search, Trash2, X } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import type { InvestigationSummary } from '../api/types';
import { SeverityBadge, SkillChip, StatusBadge } from '../components/Badges';
import { EmptyState, ErrorBanner, Skeleton, Spinner } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import { useDebouncedValue, useDocumentTitle, useNow } from '../hooks/useUtils';
import { formatDateTime, formatDuration, formatRelative, truncate } from '../utils/format';

const PAGE_SIZE = 25;

function HistoryRow({
  item,
  now,
  deleting,
  onDelete,
}: {
  item: InvestigationSummary;
  now: number;
  deleting: boolean;
  onDelete: (item: InvestigationSummary) => void;
}) {
  const navigate = useNavigate();
  const href = `/sre/${item.id}`;
  return (
    <tr className="history-row" onClick={() => navigate(href)}>
      <td>
        <StatusBadge status={item.status} outcome={item.outcome} />
      </td>
      <td className="history-row__title-cell">
        <Link to={href} className="history-row__title" onClick={(e) => e.stopPropagation()}>
          {item.title || truncate(item.query, 80)}
        </Link>
        <span className="history-row__query" title={item.query}>
          {truncate(item.query, 110)}
        </span>
      </td>
      <td>
        <div className="history-row__skills">
          {item.selected_skill_ids.length === 0 ? (
            <span className="muted">{item.mode === 'none' ? 'No skill' : '—'}</span>
          ) : (
            item.selected_skill_ids.slice(0, 3).map((id) => <SkillChip key={id}>{id}</SkillChip>)
          )}
          {item.selected_skill_ids.length > 3 && <span className="muted small">+{item.selected_skill_ids.length - 3}</span>}
        </div>
      </td>
      <td>
        <SeverityBadge severity={item.severity} />
      </td>
      <td className="history-row__root" title={item.root_cause ?? undefined}>
        {item.root_cause ? truncate(item.root_cause, 120) : <span className="muted">—</span>}
      </td>
      <td className="nowrap" title={formatDateTime(item.created_at)}>
        {formatRelative(item.created_at, now)}
      </td>
      <td className="nowrap">{formatDuration(item.duration_ms, false)}</td>
      <td className="history-row__actions">
        <button
          type="button"
          className="icon-btn icon-btn--danger"
          aria-label={`Delete investigation ${item.title || item.query}`}
          title="Delete"
          disabled={deleting}
          onClick={(e) => {
            e.stopPropagation();
            onDelete(item);
          }}
        >
          {deleting ? <Spinner size={14} /> : <Trash2 size={15} aria-hidden="true" />}
        </button>
      </td>
    </tr>
  );
}

export default function HistoryPage() {
  useDocumentTitle('History');
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const page = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1);
  const [search, setSearch] = useState(q);
  const debounced = useDebouncedValue(search.trim(), 300);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const now = useNow(30_000);

  // Push the debounced search into the URL (resets to page 1).
  useEffect(() => {
    if (debounced === q) return;
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (debounced) next.set('q', debounced);
        else next.delete('q');
        next.delete('page');
        return next;
      },
      { replace: true },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  const list = useApi(
    (signal) => api.listInvestigations({ limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE, q }, signal),
    [q, page],
  );

  const total = list.data?.total ?? 0;
  const items = list.data?.items ?? [];
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const goToPage = (target: number) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (target <= 1) next.delete('page');
      else next.set('page', String(target));
      return next;
    });

  const onDelete = async (item: InvestigationSummary) => {
    const label = item.title || truncate(item.query, 60);
    if (!window.confirm(`Delete investigation "${label}"? This cannot be undone.`)) return;
    setDeletingId(item.id);
    setDeleteError(null);
    try {
      await api.deleteInvestigation(item.id);
      if (items.length === 1 && page > 1) goToPage(page - 1);
      else list.reload();
    } catch (err) {
      setDeleteError(errorMessage(err));
    } finally {
      setDeletingId(null);
    }
  };

  const firstShown = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const lastShown = Math.min(total, page * PAGE_SIZE);

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <h1>Investigation History</h1>
          <p className="page__subtitle">Browse, search and revisit past investigations.</p>
        </div>
        <div className="search-input">
          <Search size={16} aria-hidden="true" />
          <label htmlFor="history-search" className="sr-only">
            Search investigations
          </label>
          <input
            id="history-search"
            type="search"
            placeholder="Search by title, query or root cause…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {list.loading && list.data && <Spinner size={14} />}
          {search && (
            <button type="button" className="icon-btn icon-btn--plain" aria-label="Clear search" onClick={() => setSearch('')}>
              <X size={14} aria-hidden="true" />
            </button>
          )}
        </div>
      </header>

      {deleteError && <ErrorBanner title="Couldn't delete the investigation" message={deleteError} />}
      {list.error && <ErrorBanner title="Couldn't load investigations" message={errorMessage(list.error)} onRetry={list.reload} />}

      {list.loading && !list.data ? (
        <div className="card table-card" aria-busy="true">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="table-skeleton-row">
              <Skeleton width={90} height={20} />
              <Skeleton width="40%" />
              <Skeleton width="20%" />
            </div>
          ))}
        </div>
      ) : list.data && items.length === 0 ? (
        <EmptyState
          icon={<HistoryIcon size={22} />}
          title={q ? 'No matching investigations' : 'No investigations yet'}
          description={q ? `Nothing matches “${q}”. Try a different search.` : 'Investigations you start will show up here.'}
          action={
            q ? (
              <button type="button" className="btn btn--secondary" onClick={() => setSearch('')}>
                Clear search
              </button>
            ) : (
              <Link to="/sre" className="btn btn--primary">
                Start an investigation
              </Link>
            )
          }
        />
      ) : list.data ? (
        <>
          <div className="card table-card">
            <div className="table-scroll">
              <table className="table history-table">
                <thead>
                  <tr>
                    <th scope="col">Status</th>
                    <th scope="col">Investigation</th>
                    <th scope="col">Skills</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Root cause</th>
                    <th scope="col">Created</th>
                    <th scope="col">Duration</th>
                    <th scope="col">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <HistoryRow
                      key={item.id}
                      item={item}
                      now={now}
                      deleting={deletingId === item.id}
                      onDelete={(target) => void onDelete(target)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <nav className="pagination" aria-label="Pagination">
            <span className="pagination__info">
              Showing {firstShown}–{lastShown} of {total}
            </span>
            <div className="pagination__buttons">
              <button type="button" className="btn btn--secondary btn--sm" disabled={page <= 1} onClick={() => goToPage(page - 1)}>
                <ChevronLeft size={14} aria-hidden="true" /> Previous
              </button>
              <span className="pagination__page">
                Page {page} of {pageCount}
              </span>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                disabled={page >= pageCount}
                onClick={() => goToPage(page + 1)}
              >
                Next <ChevronRight size={14} aria-hidden="true" />
              </button>
            </div>
          </nav>
        </>
      ) : null}
    </div>
  );
}
