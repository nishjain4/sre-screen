import { useState, type ReactNode } from 'react';
import { Bot, Database, Timer } from 'lucide-react';
import type { InvestigationReport, LogFinding, RemediationAction, Risk, Timeframe } from '../api/types';
import { formatMaybeTimestamp, formatNumber, humanize } from '../utils/format';
import { Pill, SeverityBadge, severityTone, type Tone } from './Badges';
import { CodeBlock } from './CodeBlock';
import { Markdown } from './Markdown';

function Section({ n, title, children, aside }: { n: number; title: string; children: ReactNode; aside?: ReactNode }) {
  const headingId = `report-section-${n}`;
  return (
    <section className="card report-section" aria-labelledby={headingId}>
      <header className="report-section__header">
        <span className="report-section__num" aria-hidden="true">
          {n}
        </span>
        <h2 id={headingId}>{title}</h2>
        {aside && <div className="report-section__aside">{aside}</div>}
      </header>
      <div className="report-section__body">{children}</div>
    </section>
  );
}

const CONFIDENCE_TONE: Record<string, Tone> = { high: 'green', medium: 'amber', low: 'gray' };
const RISK_TONE: Record<Risk, Tone> = { low: 'green', medium: 'amber', high: 'red' };
const TIMEFRAME_TONE: Record<Timeframe, Tone> = { immediate: 'red', short_term: 'amber', long_term: 'blue' };

function ConclusionSection({ report }: { report: InvestigationReport }) {
  const rc = report.root_cause;
  return (
    <section className="card report-conclusion" aria-labelledby="report-conclusion-title">
      <header className="report-conclusion__header">
        <div>
          <p className="report-conclusion__eyebrow">ROOT CAUSE ANALYSIS</p>
          <h2 id="report-conclusion-title">{report.title}</h2>
        </div>
        <Pill tone={report.conclusive ? 'green' : 'amber'}>
          {report.conclusive ? 'CONCLUSION' : 'INCONCLUSIVE'}
        </Pill>
      </header>
      <div className="report-meta-row">
        <SeverityBadge severity={report.severity} prefix="Severity:" />
        <Pill tone={CONFIDENCE_TONE[rc.confidence] ?? 'gray'}>Confidence: {rc.confidence}</Pill>
        <Pill tone="violet">{humanize(rc.category)}</Pill>
      </div>
      <Markdown>{report.executive_summary}</Markdown>
      <div className="report-inline-list">
        <span className="report-inline-list__label">Affected services</span>
        {report.affected_services.map((svc) => <span key={svc} className="chip chip--mono">{svc}</span>)}
        {report.affected_services.length === 0 && <span className="muted">None identified</span>}
      </div>
      <section className="report-conclusion__subsection">
        <h3>Root Cause Analysis</h3>
        <p className="root-cause__summary">{rc.summary}</p>
        {rc.details && <Markdown>{rc.details}</Markdown>}
      </section>
      <section className="report-conclusion__subsection">
        <h3>Evidence</h3>
        {report.supporting_evidence.length === 0 ? (
          <p className="muted">No supporting evidence was recorded.</p>
        ) : (
          <ul className="evidence-list">
            {report.supporting_evidence.map((item, i) => (
              <li key={i} className="evidence-item">
                <span className={`dot dot--${severityTone(item.severity)} evidence-item__dot`} role="img"
                  aria-label={`Severity: ${item.severity}`} />
                <div className="evidence-item__body">
                  <div className="evidence-item__title">{item.title}</div>
                  {item.detail && <div className="evidence-item__detail"><Markdown>{item.detail}</Markdown></div>}
                </div>
                {item.source && <code className="tool-chip evidence-item__source">{item.source}</code>}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="report-conclusion__subsection">
        <h3>MCP and Diagnostic Tool Results</h3>
        {(report.tool_results ?? []).length === 0 ? (
          <p className="muted">No diagnostic tool calls were recorded.</p>
        ) : (report.tool_results ?? []).map((call) => (
          <details key={call.id} className="evidence-item__body">
            <summary>{call.tool} — {humanize(call.status)} — {call.data_mode ?? 'Source not verified'}</summary>
            {call.description && <p>{call.description}</p>}
            {call.summary && <p>{call.summary}</p>}
            {call.error && <p role="alert">{call.error}</p>}
            <h4>Arguments</h4>
            <CodeBlock code={JSON.stringify(call.args, null, 2)} />
            <h4>Result</h4>
            <CodeBlock code={typeof call.output === 'string' ? call.output : JSON.stringify(call.output, null, 2) ?? 'No output returned'} />
          </details>
        ))}
      </section>
      <section className="report-conclusion__subsection">
        <h3>Log Analysis</h3>
        {report.log_analysis.summary && <Markdown>{report.log_analysis.summary}</Markdown>}
        {report.log_analysis.findings.length > 0 ? (
          <ul className="log-findings">
            {report.log_analysis.findings.map((finding, i) => (
              <LogFindingCard key={`${finding.pattern}-${i}`} finding={finding} />
            ))}
          </ul>
        ) : (
          <p className="muted">No log patterns were collected.</p>
        )}
      </section>
    </section>
  );
}

function LogFindingCard({ finding }: { finding: LogFinding }) {
  const level = finding.level.toUpperCase();
  const tone: Tone = /ERR|FATAL|CRIT/.test(level) ? 'red' : /WARN/.test(level) ? 'amber' : 'gray';
  return (
    <li className="log-finding">
      <div className="log-finding__header">
        <span className={`mini-badge mini-badge--${tone}`}>{level}</span>
        <code className="log-finding__pattern">{finding.pattern}</code>
        <span className="log-finding__count" title="Occurrences">
          ×{formatNumber(finding.count)}
        </span>
      </div>
      {(finding.first_seen || finding.last_seen) && (
        <div className="log-finding__seen">
          <span>
            <Timer size={12} aria-hidden="true" /> First seen {formatMaybeTimestamp(finding.first_seen)}
          </span>
          <span>Last seen {formatMaybeTimestamp(finding.last_seen)}</span>
        </div>
      )}
      {finding.sample && <CodeBlock code={finding.sample} />}
      {finding.interpretation && <p className="log-finding__interpretation">{finding.interpretation}</p>}
    </li>
  );
}

function RemediationRow({ action }: { action: RemediationAction }) {
  return (
    <li className="remediation">
      <span className="remediation__priority" title={`Priority ${action.priority}`}>
        {action.priority}
      </span>
      <div className="remediation__body">
        <div className="remediation__header">
          <span className="remediation__action">{action.action}</span>
          <span className="remediation__pills">
            <Pill tone={RISK_TONE[action.risk] ?? 'gray'}>Risk: {action.risk}</Pill>
            <Pill tone={TIMEFRAME_TONE[action.timeframe] ?? 'gray'}>{humanize(action.timeframe)}</Pill>
          </span>
        </div>
        {action.rationale && <p className="remediation__rationale">{action.rationale}</p>}
        {action.command && <CodeBlock code={action.command} />}
      </div>
    </li>
  );
}

function RemediationSection({ report }: { report: InvestigationReport }) {
  const actions = [...report.recommended_remediation].sort((a, b) => a.priority - b.priority);
  return (
    <Section n={2} title="Recommended Remediation">
      {actions.length === 0 ? (
        <p className="muted">No remediation actions were recommended.</p>
      ) : (
        <ol className="remediation-list">
          {actions.map((action, i) => (
            <RemediationRow key={`${action.priority}-${i}`} action={action} />
          ))}
        </ol>
      )}
    </Section>
  );
}

function NextStepsSection({ report }: { report: InvestigationReport }) {
  const [done, setDone] = useState<Set<number>>(() => new Set());
  const toggle = (index: number) =>
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  return (
    <Section n={3} title="Next Investigation Steps">
      {report.next_steps.length === 0 ? (
        <p className="muted">No follow-up steps suggested.</p>
      ) : (
        <ul className="checklist">
          {report.next_steps.map((step, i) => (
            <li key={i} className={done.has(i) ? 'is-done' : undefined}>
              <label>
                <input type="checkbox" checked={done.has(i)} onChange={() => toggle(i)} />
                <span>{step}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function ReportView({ report }: { report: InvestigationReport }) {
  return (
    <div className="report">
      <ConclusionSection report={report} />
      <RemediationSection report={report} />
      <NextStepsSection report={report} />
      <Section n={4} title="Conclusion Summary"
        aside={<Pill tone={report.conclusive ? 'green' : 'amber'}>
          {report.conclusive ? 'CONCLUSION' : 'INCONCLUSIVE'}
        </Pill>}>
        <div className="report-meta-row">
          <SeverityBadge severity={report.severity} prefix="Severity:" />
          <Pill tone={CONFIDENCE_TONE[report.root_cause.confidence] ?? 'gray'}>
            Confidence: {report.root_cause.confidence}
          </Pill>
        </div>
        <Markdown>{report.conclusion_summary || report.executive_summary}</Markdown>
      </Section>
      <footer className="report__footer">
        {report.generated_by && (
          <span className="report__generated">
            <Bot size={14} aria-hidden="true" /> Generated by {report.generated_by}
          </span>
        )}
        {report.data_sources.length > 0 && (
          <span className="report__sources">
            <Database size={14} aria-hidden="true" /> Data sources
            {report.data_sources.map((src) => (
              <span key={src} className="chip">
                {src}
              </span>
            ))}
          </span>
        )}
      </footer>
    </div>
  );
}
