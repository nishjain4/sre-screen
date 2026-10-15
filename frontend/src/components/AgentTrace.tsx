import { Check, Clock3, Compass, Link2, Loader2, MinusCircle, X } from 'lucide-react';
import type { Entities, Investigation, InvestigationPlan, InvestigationStep } from '../api/types';
import { useNow } from '../hooks/useUtils';
import { elapsedMs, formatDuration } from '../utils/format';
import { isActive, sortSteps, stepKindLabel } from '../utils/investigation';
import { EmptyState, Skeleton } from './Feedback';
import { ToolCallItem } from './ToolCallItem';

const ENTITY_GROUPS: { key: keyof Omit<Entities, 'time_window_minutes'>; label: string }[] = [
  { key: 'services', label: 'Services' },
  { key: 'namespaces', label: 'Namespaces' },
  { key: 'databases', label: 'Databases' },
  { key: 'hosts', label: 'Hosts' },
];

function PlanCard({ plan }: { plan: InvestigationPlan }) {
  const entities = plan.entities;
  const groups = ENTITY_GROUPS.filter((g) => (entities?.[g.key]?.length ?? 0) > 0);
  return (
    <section className="card plan-card" aria-labelledby="plan-heading">
      <header className="plan-card__header">
        <span className="plan-card__icon" aria-hidden="true">
          <Compass size={16} />
        </span>
        <h3 id="plan-heading">Investigation Plan</h3>
        {entities?.time_window_minutes ? (
          <span className="pill pill--gray">Window: {formatDuration(entities.time_window_minutes * 60_000, false)}</span>
        ) : null}
      </header>
      <p className="plan-card__summary">{plan.summary}</p>
      {plan.reasoning && <p className="plan-card__reasoning">{plan.reasoning}</p>}

      {groups.length > 0 && (
        <div className="plan-card__entities">
          {groups.map((g) => (
            <div key={g.key} className="entity-group">
              <span className="entity-group__label">{g.label}</span>
              {entities[g.key].map((value) => (
                <span key={value} className="chip chip--mono">
                  {value}
                </span>
              ))}
            </div>
          ))}
        </div>
      )}
      {entities?.error_messages?.length > 0 && (
        <div className="plan-card__errors">
          <span className="entity-group__label">Error signatures</span>
          <ul>
            {entities.error_messages.map((msg) => (
              <li key={msg}>
                <code>{msg}</code>
              </li>
            ))}
          </ul>
        </div>
      )}

      {plan.items.length > 0 && (
        <ol className="plan-items">
          {plan.items.map((item, i) => (
            <li key={`${item.skill_id}-${i}`} className="plan-item">
              <span className="plan-item__num">{i + 1}</span>
              <div className="plan-item__body">
                <div className="plan-item__title">
                  <strong>{item.skill_name}</strong>
                  <span className="skill-chip">{item.skill_id}</span>
                </div>
                <p className="plan-item__objective">{item.objective}</p>
                {item.tools.length > 0 && (
                  <div className="plan-item__tools">
                    {item.tools.map((tool) => (
                      <code key={tool} className="tool-chip">
                        {tool}
                      </code>
                    ))}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function StepMarker({ status }: { status: InvestigationStep['status'] }) {
  switch (status) {
    case 'running':
      return (
        <span className="step-marker step-marker--running" role="img" aria-label="Running">
          <Loader2 size={14} className="spin" aria-hidden="true" />
        </span>
      );
    case 'completed':
      return (
        <span className="step-marker step-marker--completed" role="img" aria-label="Completed">
          <Check size={13} strokeWidth={3} aria-hidden="true" />
        </span>
      );
    case 'failed':
      return (
        <span className="step-marker step-marker--failed" role="img" aria-label="Failed">
          <X size={13} strokeWidth={3} aria-hidden="true" />
        </span>
      );
    case 'skipped':
      return (
        <span className="step-marker step-marker--skipped" role="img" aria-label="Skipped">
          <MinusCircle size={13} aria-hidden="true" />
        </span>
      );
  }
}

function StepItem({ step, number, now }: { step: InvestigationStep; number: number; now: number }) {
  const running = step.status === 'running';
  const duration = running ? elapsedMs(step.started_at, now) : step.duration_ms ?? elapsedMs(step.started_at, step.finished_at);
  return (
    <li className={`stepper__item stepper__item--${step.status}`}>
      <div className="stepper__gutter">
        <StepMarker status={step.status} />
        <span className="stepper__label">Step {number}</span>
      </div>
      <article className="card step-card" aria-label={`Step ${number}: ${step.title}`}>
        <header className="step-card__header">
          <h3 className="step-card__title">{step.title}</h3>
          <span className="step-card__number">STEP {number}</span>
        </header>
        {step.description && <p className="step-card__description">{step.description}</p>}
        {step.findings.length > 0 && (
          <ul className="step-card__findings">
            {step.findings.map((finding, i) => (
              <li key={i}>{finding}</li>
            ))}
          </ul>
        )}
        {step.tool_calls.length > 0 && (
          <ul className="tool-calls" aria-label="Tool calls">
            {step.tool_calls.map((call) => (
              <ToolCallItem key={call.id} call={call} />
            ))}
          </ul>
        )}
        {running && step.tool_calls.length === 0 && (
          <div className="step-card__working">
            <Skeleton width="60%" />
            <Skeleton width="40%" />
          </div>
        )}
        <footer className="step-card__footer">
          <span className="step-card__kind">{stepKindLabel(step.kind)}</span>
          <span className="step-card__stats">
            <span>
              <Clock3 size={13} aria-hidden="true" /> Duration {duration !== null ? formatDuration(duration) : '—'}
            </span>
            <span>
              <Link2 size={13} aria-hidden="true" /> Tool Calls {step.tool_calls.length}
            </span>
          </span>
        </footer>
      </article>
    </li>
  );
}

export function AgentTrace({ investigation }: { investigation: Investigation }) {
  const active = isActive(investigation.status);
  const now = useNow(1000, active);
  const steps = sortSteps(investigation.steps);

  return (
    <div className="trace">
      {investigation.plan ? (
        <PlanCard plan={investigation.plan} />
      ) : (
        active && (
          <div className="card plan-card plan-card--pending" aria-busy="true">
            <Skeleton width="30%" height={16} />
            <Skeleton width="80%" />
            <Skeleton width="65%" />
          </div>
        )
      )}

      {steps.length === 0 ? (
        active ? (
          <EmptyState
            icon={<Loader2 size={22} className="spin" />}
            title={investigation.status === 'queued' ? 'Queued' : 'Starting investigation…'}
            description="Steps will appear here as the agent works."
          />
        ) : (
          <EmptyState title="No steps recorded" description="This investigation finished without recording any agent steps." />
        )
      ) : (
        <ol className="stepper">
          {steps.map((step, i) => (
            <StepItem key={step.id} step={step} number={i + 1} now={now} />
          ))}
        </ol>
      )}
    </div>
  );
}
