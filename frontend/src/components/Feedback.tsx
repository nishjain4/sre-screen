import type { ReactNode } from 'react';
import { AlertCircle, Inbox, Loader2, RotateCw } from 'lucide-react';

export function Spinner({ size = 16, label, className }: { size?: number; label?: string; className?: string }) {
  return (
    <Loader2
      size={size}
      className={`spin${className ? ` ${className}` : ''}`}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      role={label ? 'status' : undefined}
    />
  );
}

export function PageLoader({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="page-loader" role="status" aria-live="polite">
      <Spinner size={22} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorBanner({
  title = 'Something went wrong',
  message,
  onRetry,
  compact,
}: {
  title?: string;
  message: ReactNode;
  onRetry?: () => void;
  compact?: boolean;
}) {
  return (
    <div className={`error-banner${compact ? ' error-banner--compact' : ''}`} role="alert">
      <AlertCircle size={18} className="error-banner__icon" aria-hidden="true" />
      <div className="error-banner__body">
        {!compact && <strong className="error-banner__title">{title}</strong>}
        <div className="error-banner__message">{message}</div>
      </div>
      {onRetry && (
        <button type="button" className="btn btn--ghost btn--sm" onClick={onRetry}>
          <RotateCw size={14} aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon" aria-hidden="true">
        {icon ?? <Inbox size={22} />}
      </div>
      <h3 className="empty-state__title">{title}</h3>
      {description && <p className="empty-state__description">{description}</p>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}

export function Skeleton({ width, height = 14, className }: { width?: number | string; height?: number | string; className?: string }) {
  return <span className={`skeleton${className ? ` ${className}` : ''}`} style={{ width, height }} aria-hidden="true" />;
}

export function SkeletonCard({ lines = 2 }: { lines?: number }) {
  return (
    <div className="card skeleton-card" aria-hidden="true">
      <Skeleton width="45%" height={16} />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} width={`${85 - i * 15}%`} />
      ))}
    </div>
  );
}
