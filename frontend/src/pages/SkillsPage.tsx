import { Puzzle, Wrench } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import type { SkillInfo, ToolInfo } from '../api/types';
import { DataModeBadge } from '../components/Badges';
import { JsonBlock } from '../components/CodeBlock';
import { EmptyState, ErrorBanner, SkeletonCard } from '../components/Feedback';
import { IconTile } from '../components/Icon';
import { useApi } from '../hooks/useApi';
import { useDocumentTitle } from '../hooks/useUtils';
import { humanize } from '../utils/format';

function SkillCard({ skill, toolByName }: { skill: SkillInfo; toolByName: Map<string, ToolInfo> }) {
  const tools = skill.tools.flatMap((name) => {
    const tool = toolByName.get(name);
    return tool ? [tool] : [];
  });

  return (
    <article className="card skill-card">
      <header className="skill-card__header">
        <IconTile name={skill.icon} size={20} />
        <div className="skill-card__heading">
          <h3>{skill.name}</h3>
          <span className="skill-card__meta">
            <code>{skill.id}</code> · {humanize(skill.category)}
          </span>
        </div>
        <span className={`mini-badge mini-badge--${skill.source === 'custom' ? 'violet' : 'gray'}`}>{skill.source}</span>
      </header>
      <p className="skill-card__desc">{skill.description}</p>
      {skill.tools.length > 0 && (
        <details className="skill-card__tool-details">
          <summary>{skill.tools.length} tools</summary>
          {tools.length > 0 && (
            <ul className="tool-list skill-card__tool-list">
              {tools.map((tool) => <ToolRow key={tool.name} tool={tool} />)}
            </ul>
          )}
        </details>
      )}
      {skill.keywords.length > 0 && <p className="skill-card__keywords">{skill.keywords.join(' · ')}</p>}
    </article>
  );
}

function groupTools(tools: ToolInfo[]): [string, ToolInfo[]][] {
  const groups = new Map<string, ToolInfo[]>();
  for (const tool of tools) {
    const key = tool.category || 'other';
    groups.set(key, [...(groups.get(key) ?? []), tool]);
  }
  return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
}

function ToolRow({ tool }: { tool: ToolInfo }) {
  const hasSchema = tool.input_schema && Object.keys(tool.input_schema).length > 0;
  return (
    <li className="tool-row">
      <div className="tool-row__main">
        <code className="tool-row__name">{tool.name}</code>
        <span className="tool-row__desc">{tool.description}</span>
      </div>
      <div className="tool-row__meta">
        <span className={`mini-badge mini-badge--${tool.source.startsWith('mcp') ? 'violet' : 'gray'}`}>{tool.source}</span>
        <DataModeBadge mode={tool.data_mode} />
      </div>
      {hasSchema && (
        <details className="tool-row__schema">
          <summary>Input schema</summary>
          <JsonBlock value={tool.input_schema} maxHeight={280} />
        </details>
      )}
    </li>
  );
}

export default function SkillsPage() {
  useDocumentTitle('Skills');
  const skills = useApi(api.skills, []);
  const tools = useApi(api.tools, []);
  const toolByName = new Map((tools.data ?? []).map((tool) => [tool.name, tool] as const));
  const skillToolNames = new Set(skills.data?.flatMap((skill) => skill.tools) ?? []);
  const unassignedTools = tools.data?.filter((tool) => !skillToolNames.has(tool.name));

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <h1>Skills</h1>
          <p className="page__subtitle">
            Skills bundle tools and domain knowledge. In Auto mode the AI picks the most relevant ones for each investigation.
          </p>
        </div>
      </header>

      {skills.error && <ErrorBanner title="Couldn't load skills" message={errorMessage(skills.error)} onRetry={skills.reload} />}
      {skills.loading && !skills.data ? (
        <div className="skill-grid">
          {Array.from({ length: 6 }, (_, i) => (
            <SkeletonCard key={i} lines={3} />
          ))}
        </div>
      ) : skills.data && skills.data.length === 0 ? (
        <EmptyState icon={<Puzzle size={22} />} title="No skills registered" />
      ) : (
        <div className="skill-grid">
          {skills.data?.map((skill) => <SkillCard key={skill.id} skill={skill} toolByName={toolByName} />)}
        </div>
      )}

      {unassignedTools && unassignedTools.length > 0 && (
        <section className="page__section" aria-labelledby="tools-heading">
          <div className="page__section-header">
            <h2 id="tools-heading">
            <Wrench size={18} aria-hidden="true" /> Tools
            </h2>
            <span className="muted">Unassigned</span>
          </div>
          {groupTools(unassignedTools).map(([category, items]) => (
            <div key={category} className="tool-group">
              <h3 className="tool-group__title">{category}</h3>
              <ul className="card tool-list">
                {items.map((tool) => (
                  <ToolRow key={tool.name} tool={tool} />
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}
      {tools.error && <ErrorBanner title="Couldn't load tools" message={errorMessage(tools.error)} onRetry={tools.reload} />}
      {tools.loading && !tools.data && <SkeletonCard lines={4} />}
    </div>
  );
}
