import { useId, useState } from 'react';
import { ChevronRight, Search, Wrench } from 'lucide-react';
import type { ToolCall, ToolCallStatus } from '../api/types';
import { formatDateTime, formatDuration } from '../utils/format';
import { DataModeBadge } from './Badges';
import { JsonBlock } from './CodeBlock';
import { Spinner } from './Feedback';

const STATUS_TONE: Record<ToolCallStatus, string> = {
  running: 'blue',
  success: 'green',
  error: 'red',
};

function argsPreview(args: ToolCall['args']): string {
  const entries = Object.entries(args ?? {});
  if (entries.length === 0) return '';
  return entries
    .map(([key, value]) => `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join(', ');
}

interface ToolCallItemProps {
  call: ToolCall;
  /** "trace": description-first row (Agent Trace); "evidence": tool-first row with args/summary. */
  variant?: 'trace' | 'evidence';
  context?: string;
}

export function ToolCallItem({ call, variant = 'trace', context }: ToolCallItemProps) {
  const [open, setOpen] = useState(false);
  const detailId = useId();
  const tone = STATUS_TONE[call.status] ?? 'gray';
  const running = call.status === 'running';
  const preview = argsPreview(call.args);

  return (
    <li className={`tool-call tool-call--${variant}${open ? ' is-open' : ''}`}>
      <button
        type="button"
        className="tool-call__row"
        aria-expanded={open}
        aria-controls={detailId}
        onClick={() => setOpen((o) => !o)}
      >
        {variant === 'trace' ? (
          <Search size={16} className="tool-call__icon" aria-hidden="true" />
        ) : (
          <Wrench size={16} className="tool-call__icon" aria-hidden="true" />
        )}
        <span
          className={`dot dot--${tone}${running ? ' dot--pulse' : ''}`}
          role="img"
          aria-label={`Status: ${call.status}`}
        />
        <span className="tool-call__main">
          {variant === 'trace' ? (
            <span className="tool-call__label">{call.description || call.tool}</span>
          ) : (
            <>
              <span className="tool-call__label">
                <code className="tool-call__tool">{call.tool}</code>
                {context && <span className="tool-call__context">{context}</span>}
              </span>
              {preview && <span className="tool-call__args">{preview}</span>}
              {(call.summary || call.description) && (
                <span className="tool-call__summary">{call.summary || call.description}</span>
              )}
              {call.error && <span className="tool-call__error-inline">{call.error}</span>}
            </>
          )}
        </span>
        <span className="tool-call__meta">
          <DataModeBadge mode={call.data_mode} />
          <span className="tool-call__duration">
            {running ? <Spinner size={12} label="Running" /> : formatDuration(call.duration_ms)}
          </span>
          <ChevronRight size={14} className="tool-call__chevron" aria-hidden="true" />
        </span>
      </button>

      {open && (
        <div className="tool-call__detail" id={detailId}>
          <dl className="kv">
            <div>
              <dt>Tool</dt>
              <dd>
                <code>{call.tool}</code>
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd className={`text-${tone}`}>{call.status}</dd>
            </div>
            {call.data_mode && (
              <div>
                <dt>Data mode</dt>
                <dd>{call.data_mode}</dd>
              </div>
            )}
            <div>
              <dt>Started</dt>
              <dd>{formatDateTime(call.started_at) || '—'}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{formatDuration(call.duration_ms)}</dd>
            </div>
          </dl>
          {call.summary && (
            <div className="tool-call__section">
              <div className="tool-call__section-label">Summary</div>
              <p>{call.summary}</p>
            </div>
          )}
          {call.error && (
            <div className="tool-call__section">
              <div className="tool-call__section-label">Error</div>
              <div className="inline-error">{call.error}</div>
            </div>
          )}
          <JsonBlock label="Arguments" value={call.args} maxHeight={200} />
          {call.output !== undefined && call.output !== null ? (
            <JsonBlock label="Output" value={call.output} />
          ) : (
            !running && <div className="muted small">No output captured.</div>
          )}
        </div>
      )}
    </li>
  );
}
