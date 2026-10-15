import { GitBranch, GitCommitHorizontal, GitPullRequest, Puzzle, type LucideIcon } from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
  gitea: GitBranch,
  review: GitPullRequest,
  commit: GitCommitHorizontal,
};

/** Accent tint per icon key (used for template / skill icon tiles). */
const TINTS: Record<string, string> = {
  gitea: 'green',
  review: 'red',
  commit: 'orange',
};

export function iconTint(name: string | null | undefined): string {
  return (name && TINTS[name.toLowerCase()]) || 'violet';
}

interface SkillIconProps {
  name: string | null | undefined;
  size?: number;
  className?: string;
}

/** Maps a skill/template `icon` key to a lucide icon. Emoji values are rendered as-is. */
export function SkillIcon({ name, size = 18, className }: SkillIconProps) {
  const key = (name ?? '').trim();
  const Icon = ICONS[key.toLowerCase()];
  if (Icon) return <Icon size={size} className={className} aria-hidden="true" />;
  if (key && !/^[\w-]+$/.test(key)) {
    return (
      <span className={className} style={{ fontSize: size, lineHeight: 1 }} aria-hidden="true">
        {key}
      </span>
    );
  }
  return <Puzzle size={size} className={className} aria-hidden="true" />;
}

/** Icon inside a soft tinted tile. */
export function IconTile({ name, size = 18 }: { name: string | null | undefined; size?: number }) {
  return (
    <span className={`icon-tile icon-tile--${iconTint(name)}`}>
      <SkillIcon name={name} size={size} />
    </span>
  );
}
