import type {
  Investigation,
  InvestigationStatus,
  InvestigationStep,
  Severity,
  SkillMode,
  StepKind,
  ToolCall,
} from '../api/types';

export function isTerminal(status: InvestigationStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

export function isActive(status: InvestigationStatus): boolean {
  return status === 'queued' || status === 'running';
}

export function modeLabel(mode: SkillMode): string {
  switch (mode) {
    case 'auto':
      return 'Auto';
    case 'specific':
      return 'Specific';
    case 'none':
      return 'No skill';
  }
}

export function stepKindLabel(kind: StepKind): string {
  switch (kind) {
    case 'intent':
      return 'Intent Detection';
    case 'planning':
      return 'Planning';
    case 'skill':
      return 'Reasoning Step';
    case 'analysis':
      return 'Analysis';
    case 'report':
      return 'Report Generation';
  }
}

export function sortSteps(steps: InvestigationStep[]): InvestigationStep[] {
  return [...steps].sort((a, b) => a.index - b.index);
}

export interface ToolCallWithStep {
  call: ToolCall;
  step: InvestigationStep;
  stepNumber: number;
}

export function allToolCalls(investigation: Investigation): ToolCallWithStep[] {
  return sortSteps(investigation.steps).flatMap((step, position) =>
    step.tool_calls.map((call) => ({ call, step, stepNumber: position + 1 })),
  );
}

const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

export function isSeverity(value: string | null | undefined): value is Severity {
  return value !== null && value !== undefined && value in SEVERITY_ORDER;
}

export function compareSeverity(a: Severity, b: Severity): number {
  return SEVERITY_ORDER[a] - SEVERITY_ORDER[b];
}
