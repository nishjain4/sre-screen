/** Parse an ISO timestamp. Naive timestamps (no zone) are treated as UTC. */
export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "just now", "5m ago", "2h ago", "3d ago", or a short date for older items. */
export function formatRelative(value: string | null | undefined, now: number = Date.now()): string {
  const date = parseDate(value);
  if (!date) return '—';
  const seconds = Math.round((now - date.getTime()) / 1000);
  if (seconds < 45) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() === new Date(now).getFullYear() ? undefined : 'numeric',
  });
}

/**
 * Human duration: "850ms", "34.9s", "9m 48s", "1h 5m".
 * `precise=false` drops sub-second precision ("48s").
 */
export function formatDuration(ms: number | null | undefined, precise = true): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return '—';
  if (ms < 1000) return precise ? `${Math.round(ms)}ms` : '<1s';
  const totalSeconds = ms / 1000;
  if (totalSeconds < 60) {
    if (!precise) return `${Math.floor(totalSeconds)}s`;
    const fixed = totalSeconds.toFixed(1);
    return `${fixed.endsWith('.0') ? fixed.slice(0, -2) : fixed}s`;
  }
  const whole = Math.floor(totalSeconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const seconds = whole % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m ${seconds}s`;
}

/** Elapsed ms between an ISO start and `now` (or an ISO end). */
export function elapsedMs(start: string | null | undefined, end: string | number | null | undefined): number | null {
  const startDate = parseDate(start);
  if (!startDate) return null;
  const endMs = typeof end === 'number' ? end : parseDate(end)?.getTime();
  if (endMs === undefined) return null;
  return Math.max(0, endMs - startDate.getTime());
}

/** Local wall-clock time "HH:MM:SS". */
export function formatClock(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) return '—';
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/** Full local date-time for tooltips. */
export function formatDateTime(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) return '';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/** Timestamp that may or may not be ISO (log first/last seen are free-form strings). */
export function formatMaybeTimestamp(value: string | null | undefined): string {
  if (!value) return '—';
  if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
    const formatted = formatDateTime(value);
    return formatted || value;
  }
  return value;
}

export function truncate(text: string | null | undefined, max: number): string {
  if (!text) return '';
  const clean = text.replace(/\s+/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max - 1).trimEnd()}…` : clean;
}

/** "short_term" → "Short term", "root-cause" → "Root cause". */
export function humanize(value: string | null | undefined): string {
  if (!value) return '';
  const spaced = value.replace(/[_-]+/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value);
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
