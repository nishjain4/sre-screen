import { FileSearch } from 'lucide-react';
import type { Investigation } from '../api/types';
import { allToolCalls, isActive } from '../utils/investigation';
import { EmptyState } from './Feedback';
import { ToolCallItem } from './ToolCallItem';

/** Raw evidence: every tool call across all steps. */
export function EvidenceView({ investigation }: { investigation: Investigation }) {
  const calls = allToolCalls(investigation);
  if (calls.length === 0) {
    return (
      <EmptyState
        icon={<FileSearch size={22} />}
        title={isActive(investigation.status) ? 'No evidence collected yet' : 'No tool calls'}
        description={
          investigation.mode === 'none'
            ? 'This investigation ran without skills, so no tools were invoked.'
            : 'Raw tool output gathered by the agent will be listed here.'
        }
      />
    );
  }

  const counts = calls.reduce(
    (acc, { call }) => {
      acc[call.status] += 1;
      return acc;
    },
    { success: 0, error: 0, running: 0 },
  );

  return (
    <div className="evidence">
      <div className="evidence__summary">
        <span>
          <strong>{calls.length}</strong> tool calls
        </span>
        <span className="text-green">{counts.success} succeeded</span>
        {counts.error > 0 && <span className="text-red">{counts.error} failed</span>}
        {counts.running > 0 && <span className="text-blue">{counts.running} running</span>}
      </div>
      <ul className="tool-calls tool-calls--evidence card">
        {calls.map(({ call, step, stepNumber }) => (
          <ToolCallItem key={call.id} call={call} variant="evidence" context={`Step ${stepNumber} · ${step.title}`} />
        ))}
      </ul>
    </div>
  );
}
