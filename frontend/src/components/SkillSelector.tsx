import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Ban, Check, ChevronDown, Puzzle, Sparkles } from 'lucide-react';
import type { SkillInfo, SkillMode } from '../api/types';
import { useDismiss, type DismissReason } from '../hooks/useUtils';
import { SkillIcon } from './Icon';
import { Spinner } from './Feedback';

interface SkillSelectorProps {
  mode: SkillMode;
  skillIds: string[];
  skills: SkillInfo[] | null;
  server: string;
  servers: string[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onChange: (mode: SkillMode, skillIds: string[]) => void;
  onServerChange: (server: string) => void;
  disabled?: boolean;
}

export function skillSelectionLabel(mode: SkillMode, skillIds: string[], skills: SkillInfo[] | null): string {
  if (mode === 'none') return 'No skills';
  if (mode === 'auto' || skillIds.length === 0) return 'Auto (AI selects skills)';
  const names = skillIds.map((id) => skills?.find((s) => s.id === id)?.name ?? id);
  return names.length <= 2 ? names.join(', ') : `${names.slice(0, 2).join(', ')} +${names.length - 2}`;
}

export function SkillSelector({
  mode,
  skillIds,
  skills,
  server,
  servers,
  loading,
  error,
  onRetry,
  onChange,
  onServerChange,
  disabled,
}: SkillSelectorProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const popoverId = useId();

  const close = useCallback((reason: DismissReason | 'select') => {
    setOpen(false);
    if (reason !== 'outside') triggerRef.current?.focus();
  }, []);

  useDismiss(containerRef, open, close);

  // Move focus into the popover when it opens.
  useEffect(() => {
    if (!open) return;
    const first = popoverRef.current?.querySelector<HTMLElement>('button, input');
    first?.focus();
  }, [open]);

  const choose = (next: 'none' | 'auto') => {
    onChange(next, []);
    close('select');
  };

  const toggleSkill = (id: string) => {
    const current = mode === 'specific' ? skillIds : [];
    const next = current.includes(id) ? current.filter((s) => s !== id) : [...current, id];
    onChange(next.length > 0 ? 'specific' : 'auto', next);
  };

  // Arrow-key navigation between options.
  const onPopoverKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    const items = Array.from(popoverRef.current?.querySelectorAll<HTMLElement>('[data-option]') ?? []);
    if (items.length === 0) return;
    event.preventDefault();
    const index = items.indexOf(document.activeElement as HTMLElement);
    const delta = event.key === 'ArrowDown' ? 1 : -1;
    const next = items[(index + delta + items.length) % items.length];
    next?.focus();
  };

  const label = skillSelectionLabel(mode, skillIds, skills);
  const serverSkills = skills?.filter((skill) => skill.mcp_servers.includes(server)) ?? [];

  return (
    <div className="skill-selector">
      <label className="skill-selector__server">
        <span className="sr-only">MCP server</span>
        <select
          aria-label="MCP server"
          value={server}
          onChange={(event) => onServerChange(event.target.value)}
          disabled={disabled || servers.length === 0}
          title="Choose an MCP server"
        >
          {servers.length === 0 && <option value="">No MCP servers available</option>}
          {servers.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
        <ChevronDown size={14} className="skill-selector__chevron" aria-hidden="true" />
      </label>

      <div className="skill-selector__skills" ref={containerRef}>
        <button
          ref={triggerRef}
          type="button"
          className={`skill-selector__trigger${open ? ' is-open' : ''}`}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? popoverId : undefined}
          onClick={() => setOpen((o) => !o)}
          disabled={disabled}
          title="Choose Auto, No skill, or skills for the selected MCP server"
        >
          <Puzzle size={16} aria-hidden="true" />
          <span className="skill-selector__label">{label}</span>
          <ChevronDown size={14} className="skill-selector__chevron" aria-hidden="true" />
        </button>

        {open && (
          <div
            ref={popoverRef}
            id={popoverId}
            className="popover skill-popover"
            role="dialog"
            aria-label="Skill selection"
            onKeyDown={onPopoverKeyDown}
          >
          <div className="skill-popover__section">
            <div className="skill-popover__heading">No skill</div>
            <button
              type="button"
              data-option
              className={`skill-option${mode === 'none' ? ' is-selected' : ''}`}
              aria-pressed={mode === 'none'}
              onClick={() => choose('none')}
            >
              <span className="skill-option__icon">
                <Ban size={16} aria-hidden="true" />
              </span>
              <span className="skill-option__text">
                <span className="skill-option__name">No skill</span>
                <span className="skill-option__desc">Ask the AI directly, no tools invoked</span>
              </span>
              {mode === 'none' && <Check size={16} className="skill-option__check" aria-hidden="true" />}
            </button>
          </div>

          <div className="skill-popover__section">
            <div className="skill-popover__heading">Auto mode</div>
            <button
              type="button"
              data-option
              className={`skill-option${mode === 'auto' ? ' is-selected' : ''}`}
              aria-pressed={mode === 'auto'}
              onClick={() => choose('auto')}
            >
              <span className="skill-option__icon skill-option__icon--accent">
                <Sparkles size={16} aria-hidden="true" />
              </span>
              <span className="skill-option__text">
                <span className="skill-option__name">Auto (AI selects skills)</span>
                <span className="skill-option__desc">AI picks the most relevant skills and tools</span>
              </span>
              {mode === 'auto' && <Check size={16} className="skill-option__check" aria-hidden="true" />}
            </button>
          </div>

          <div className="skill-popover__section skill-popover__section--list">
            <div className="skill-popover__heading">
              Specific skills
              {mode === 'specific' && skillIds.length > 0 && (
                <span className="skill-popover__count">{skillIds.length} selected</span>
              )}
            </div>
            {loading && !skills && (
              <div className="skill-popover__status">
                <Spinner size={14} /> Loading skills…
              </div>
            )}
            {error && !skills && (
              <div className="skill-popover__status skill-popover__status--error">
                Couldn&apos;t load skills.{' '}
                <button type="button" className="link-btn" onClick={onRetry}>
                  Retry
                </button>
              </div>
            )}
            {skills && serverSkills.length === 0 && (
              <div className="skill-popover__status">No skills available for this MCP server.</div>
            )}
            {serverSkills.map((skill) => {
              const checked = mode === 'specific' && skillIds.includes(skill.id);
              return (
                <label key={skill.id} className={`skill-option skill-option--check${checked ? ' is-selected' : ''}`}>
                  <input
                    type="checkbox"
                    data-option
                    checked={checked}
                    onChange={() => toggleSkill(skill.id)}
                    className="skill-option__checkbox"
                  />
                  <span className="skill-option__icon">
                    <SkillIcon name={skill.icon} size={16} />
                  </span>
                  <span className="skill-option__text">
                    <span className="skill-option__name">{skill.name}</span>
                    <span className="skill-option__desc">{skill.description}</span>
                    {skill.tools.length > 0 && (
                      <span className="skill-option__tools" title={skill.tools.join(', ')}>
                        {skill.tools.join(' · ')}
                      </span>
                    )}
                  </span>
                </label>
              );
            })}
          </div>
          </div>
        )}
      </div>
    </div>
  );
}
