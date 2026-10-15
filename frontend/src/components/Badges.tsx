import type { ReactNode } from 'react';
import type { DataMode, InvestigationStatus, Severity } from '../api/types';
import { humanize } from '../utils/format';
import { isSeverity } from '../utils/investigation';

export type Tone = 'green' | 'amber' | 'red' | 'blue' | 'gray' | 'violet' | 'orange';

interface StatusDescriptor {
  label: string;
  tone: Tone;
  pulse: boolean;
}

export function describeStatus(status: InvestigationStatus, outcome: string | null | undefined): StatusDescriptor {
  switch (status) {
    case 'queued':
    case 'running':
      return { label: 'Investigating…', tone: 'blue', pulse: true };
    case 'completed':
      if (outcome === 'conclusive') return { label: 'Conclusive', tone: 'green', pulse: false };
      if (outcome === 'inconclusive') return { label: 'Inconclusive', tone: 'amber', pulse: false };
      return { label: 'Completed', tone: 'green', pulse: false };
    case 'failed':
      return { label: 'Failed', tone: 'red', pulse: false };
    case 'cancelled':
      return { label: 'Cancelled', tone: 'gray', pulse: false };
  }
}

export function StatusBadge({
  status,
  outcome,
}: {
  status: InvestigationStatus;
  outcome?: string | null;
}) {
  const { label, tone, pulse } = describeStatus(status, outcome);
  return (
    <span className={`badge badge--${tone} status-badge`}>
      <span className={`dot dot--${tone}${pulse ? ' dot--pulse' : ''}`} aria-hidden="true" />
      {label}
    </span>
  );
}

const SEVERITY_TONE: Record<Severity, Tone> = {
  critical: 'red',
  high: 'orange',
  medium: 'amber',
  low: 'blue',
  info: 'gray',
};

export function severityTone(severity: string | null | undefined): Tone {
  return isSeverity(severity) ? SEVERITY_TONE[severity] : 'gray';
}

export function SeverityBadge({ severity, prefix }: { severity: string | null | undefined; prefix?: string }) {
  if (!severity) return <span className="muted">—</span>;
  return (
    <span className={`badge badge--${severityTone(severity)} badge--caps`}>
      {prefix ? `${prefix} ` : ''}
      {severity}
    </span>
  );
}

const DATA_MODE_TONE: Record<DataMode, Tone> = {
  live: 'green',
  simulated: 'amber',
  mcp: 'violet',
  internal: 'gray',
};

export function DataModeBadge({ mode }: { mode: DataMode | null | undefined }) {
  if (!mode) return null;
  const tone = DATA_MODE_TONE[mode] ?? 'gray';
  return (
    <span className={`mini-badge mini-badge--${tone}`} title={`Data mode: ${mode}`}>
      {mode}
    </span>
  );
}

/** Generic rounded pill. */
export function Pill({
  tone = 'gray',
  children,
  title,
  icon,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
  icon?: ReactNode;
}) {
  return (
    <span className={`pill pill--${tone}`} title={title}>
      {icon}
      {children}
    </span>
  );
}

/** Neutral bordered chip (e.g. "Initiated by …"). */
export function Chip({ children, icon, title, mono }: { children: ReactNode; icon?: ReactNode; title?: string; mono?: boolean }) {
  return (
    <span className={`chip${mono ? ' chip--mono' : ''}`} title={title}>
      {icon}
      {children}
    </span>
  );
}

/** Purple skill-id chip. */
export function SkillChip({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span className="skill-chip" title={title}>
      {children}
    </span>
  );
}

export function ModeBadge({ mode }: { mode: string }) {
  const tone: Tone = mode === 'live' || mode === 'connected' ? 'green' : mode === 'simulated' ? 'amber' : mode === 'error' ? 'red' : 'gray';
  return <span className={`badge badge--${tone}`}>{humanize(mode)}</span>;
}
