import { AlertTriangle, Bot, Cpu, Server } from 'lucide-react';
import type { ReactNode } from 'react';
import { api, errorMessage } from '../api/client';
import { ModeBadge } from '../components/Badges';
import { EmptyState, ErrorBanner, SkeletonCard } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import { useDocumentTitle } from '../hooks/useUtils';

function SettingCard({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="card setting-card">
      <header className="setting-card__header">
        <span className="setting-card__icon" aria-hidden="true">
          {icon}
        </span>
        <h2>{title}</h2>
      </header>
      <dl className="kv kv--stacked">{children}</dl>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export default function SettingsPage() {
  useDocumentTitle('Settings');
  const config = useApi(api.config, []);
  const data = config.data;

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <h1>Settings</h1>
          <p className="page__subtitle">
            Read-only view of the backend configuration{data?.version ? ` · v${data.version}` : ''}. Change these via
            the backend environment.
          </p>
        </div>
      </header>

      {config.error && <ErrorBanner title="Couldn't load configuration" message={errorMessage(config.error)} onRetry={config.reload} />}

      {config.loading && !data && (
        <div className="settings-grid">
          <SkeletonCard lines={3} />
          <SkeletonCard lines={3} />
          <SkeletonCard lines={3} />
        </div>
      )}

      {data && (
        <>
          {!data.llm_configured && (
            <div className="callout callout--warning" role="status">
              <AlertTriangle size={18} aria-hidden="true" />
              <div>
                <strong>Amazon Bedrock is not configured — running with the offline heuristic analyzer</strong>
                <p>Investigations still run, but reports are produced by rule-based analysis instead of an LLM.</p>
              </div>
            </div>
          )}

          <div className="settings-grid">
            <SettingCard icon={<Bot size={18} />} title="Language model">
              <Row label="Provider">{data.llm_provider || '—'}</Row>
              <Row label="Model">
                <code>{data.llm_model || '—'}</code>
              </Row>
              <Row label="Configured">
                <span className={`badge badge--${data.llm_configured ? 'green' : 'amber'}`}>
                  {data.llm_configured ? 'Yes' : 'No'}
                </span>
              </Row>
            </SettingCard>

            <SettingCard icon={<Cpu size={18} />} title="Orchestrator">
              <Row label="Active">
                <code>{data.orchestrator}</code>
              </Row>
              <Row label="Available">
                <span className="chip-row">
                  {data.available_orchestrators.map((name) => (
                    <span key={name} className={`chip chip--mono${name === data.orchestrator ? ' chip--active' : ''}`}>
                      {name}
                    </span>
                  ))}
                </span>
              </Row>
            </SettingCard>

          </div>

          <section className="page__section" aria-labelledby="mcp-heading">
            <div className="page__section-header">
              <h2 id="mcp-heading">
                <Server size={18} aria-hidden="true" /> MCP servers
              </h2>
            </div>
            {data.mcp_servers.length === 0 ? (
              <EmptyState
                icon={<Server size={22} />}
                title="No MCP servers configured"
                description="The Gitea MCP server provides repository tools for investigations."
              />
            ) : (
              <div className="card table-card">
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Name</th>
                        <th scope="col">Transport</th>
                        <th scope="col">Status</th>
                        <th scope="col">Tools</th>
                        <th scope="col">Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.mcp_servers.map((server) => (
                        <tr key={server.name}>
                          <td>
                            <strong>{server.name}</strong>
                          </td>
                          <td>
                            <code>{server.transport}</code>
                          </td>
                          <td>
                            <ModeBadge mode={server.status} />
                          </td>
                          <td>{server.tool_count}</td>
                          <td className={server.error ? 'text-red' : 'muted'}>{server.error || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
