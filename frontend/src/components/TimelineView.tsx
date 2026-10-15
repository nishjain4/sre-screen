import { Clock } from 'lucide-react';
import type { TimelineEvent } from '../api/types';
import { useNow } from '../hooks/useUtils';
import { formatClock, formatDateTime, formatRelative, parseDate } from '../utils/format';
import { severityTone } from './Badges';
import { EmptyState } from './Feedback';

export function TimelineView({ events }: { events: TimelineEvent[] }) {
  const now = useNow(30_000);
  if (events.length === 0) {
    return (
      <EmptyState
        icon={<Clock size={22} />}
        title="No timeline events yet"
        description="Timestamped events collected during this Gitea investigation will appear here."
      />
    );
  }
  const sorted = [...events].sort(
    (a, b) => (parseDate(a.timestamp)?.getTime() ?? 0) - (parseDate(b.timestamp)?.getTime() ?? 0),
  );
  return (
    <ol className="timeline">
      {sorted.map((event, i) => {
        const tone = severityTone(event.severity);
        return (
          <li key={`${event.timestamp}-${i}`} className="timeline__item">
            <div className="timeline__time" title={formatDateTime(event.timestamp)}>
              <time dateTime={event.timestamp}>{formatClock(event.timestamp)}</time>
              <span className="timeline__relative">{formatRelative(event.timestamp, now)}</span>
            </div>
            <div className="timeline__rail" aria-hidden="true">
              <span className={`timeline__dot dot--${tone}`} />
            </div>
            <div className="card timeline__card">
              <div className="timeline__header">
                <span className="timeline__title">{event.title}</span>
                <span className="timeline__chips">
                  <span className={`mini-badge mini-badge--${tone}`}>{event.severity}</span>
                  <span className="chip chip--mono">{event.source}</span>
                </span>
              </div>
              {event.detail && <p className="timeline__detail">{event.detail}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
