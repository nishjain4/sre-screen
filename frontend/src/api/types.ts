/**
 * TypeScript mirror of backend/app/schemas.py (the API contract, see docs/API.md).
 * Datetimes are ISO-8601 strings on the wire.
 */

export type ISODateTime = string;

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type DataMode = 'live' | 'simulated' | 'mcp' | 'internal';

export type SkillMode = 'none' | 'specific' | 'auto';
export type InvestigationStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type StepStatus = 'running' | 'completed' | 'failed' | 'skipped';
export type ToolCallStatus = 'running' | 'success' | 'error';
export type StepKind = 'intent' | 'planning' | 'skill' | 'analysis' | 'report';
export type Outcome = 'conclusive' | 'inconclusive';
export type Confidence = 'high' | 'medium' | 'low';
export type Risk = 'low' | 'medium' | 'high';
export type Timeframe = 'immediate' | 'short_term' | 'long_term';

/** JSON value as returned by tools (`output: Any`). */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

// --------------------------------------------------------------------------- //
// Requests
// --------------------------------------------------------------------------- //
export interface InvestigationCreate {
  query: string;
  mode: SkillMode;
  skill_ids: string[];
  context: Record<string, string>;
  template_id: string | null;
}

export interface ChatRequest {
  message: string;
}

export interface FeedbackRequest {
  helpful: boolean;
  comment?: string | null;
}

// --------------------------------------------------------------------------- //
// Investigation building blocks
// --------------------------------------------------------------------------- //
export interface Entities {
  services: string[];
  namespaces: string[];
  databases: string[];
  hosts: string[];
  error_messages: string[];
  time_window_minutes: number;
}

export interface ToolCall {
  id: string;
  tool: string;
  args: Record<string, JsonValue>;
  status: ToolCallStatus;
  description: string | null;
  summary: string | null;
  error: string | null;
  data_mode: DataMode | null;
  output: JsonValue | undefined;
  started_at: ISODateTime;
  finished_at: ISODateTime | null;
  duration_ms: number | null;
}

export interface InvestigationStep {
  id: string;
  index: number;
  kind: StepKind;
  title: string;
  description: string;
  status: StepStatus;
  skill_id: string | null;
  tool_calls: ToolCall[];
  findings: string[];
  started_at: ISODateTime;
  finished_at: ISODateTime | null;
  duration_ms: number | null;
}

export interface PlanItem {
  skill_id: string;
  skill_name: string;
  objective: string;
  tools: string[];
}

export interface InvestigationPlan {
  summary: string;
  reasoning: string;
  entities: Entities;
  items: PlanItem[];
}

export interface TimelineEvent {
  timestamp: ISODateTime;
  source: string;
  title: string;
  detail: string | null;
  severity: Severity;
}

// --------------------------------------------------------------------------- //
// Report
// --------------------------------------------------------------------------- //
export interface RootCause {
  summary: string;
  details: string;
  confidence: Confidence;
  category: string;
}

export interface EvidenceItem {
  title: string;
  detail: string;
  source: string;
  severity: Severity;
}

export interface LogFinding {
  pattern: string;
  count: number;
  level: string;
  first_seen: string | null;
  last_seen: string | null;
  sample: string;
  interpretation: string;
}

export interface LogAnalysis {
  summary: string;
  findings: LogFinding[];
}

export interface RemediationAction {
  priority: number;
  action: string;
  rationale: string;
  command: string | null;
  risk: Risk;
  timeframe: Timeframe;
}

export interface InvestigationReport {
  title: string;
  executive_summary: string;
  conclusion_summary?: string;
  severity: Severity;
  conclusive: boolean;
  affected_services: string[];
  root_cause: RootCause;
  supporting_evidence: EvidenceItem[];
  log_analysis: LogAnalysis;
  recommended_remediation: RemediationAction[];
  next_steps: string[];
  suggested_questions: string[];
  generated_by: string;
  data_sources: string[];
  tool_results?: ToolCall[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: ISODateTime;
}

export interface Feedback {
  helpful: boolean;
  comment: string | null;
  created_at: ISODateTime;
}

export interface Investigation {
  id: string;
  title: string;
  query: string;
  mode: SkillMode;
  requested_skill_ids: string[];
  selected_skill_ids: string[];
  context: Record<string, string>;
  template_id: string | null;
  status: InvestigationStatus;
  outcome: Outcome | null;
  initiated_by: string;
  orchestrator: string;
  llm: string;
  created_at: ISODateTime;
  started_at: ISODateTime | null;
  finished_at: ISODateTime | null;
  duration_ms: number | null;
  plan: InvestigationPlan | null;
  steps: InvestigationStep[];
  timeline: TimelineEvent[];
  report: InvestigationReport | null;
  chat: ChatMessage[];
  feedback: Feedback | null;
  error: string | null;
}

export interface InvestigationSummary {
  id: string;
  title: string;
  query: string;
  mode: SkillMode;
  status: InvestigationStatus;
  outcome: string | null;
  selected_skill_ids: string[];
  severity: string | null;
  root_cause: string | null;
  initiated_by: string;
  created_at: ISODateTime;
  finished_at: ISODateTime | null;
  duration_ms: number | null;
}

export interface InvestigationList {
  items: InvestigationSummary[];
  total: number;
}

// --------------------------------------------------------------------------- //
// Catalog
// --------------------------------------------------------------------------- //
export interface SkillInfo {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  tools: string[];
  mcp_servers: string[];
  keywords: string[];
  source: 'builtin' | 'custom';
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  /** "builtin" | "mcp:<server>" */
  source: string;
  data_mode: DataMode;
  input_schema: Record<string, JsonValue>;
}

export interface TemplateInfo {
  id: string;
  title: string;
  description: string;
  category: string;
  icon: string;
  query: string;
  mode: SkillMode;
  skill_ids: string[];
}

export interface MCPServerStatus {
  name: string;
  transport: string;
  status: 'connected' | 'error' | 'disabled';
  tool_count: number;
  error: string | null;
}

export interface ServiceConfig {
  llm_provider: string;
  llm_model: string;
  llm_configured: boolean;
  orchestrator: string;
  available_orchestrators: string[];
  mcp_servers: MCPServerStatus[];
  version: string;
}

export interface HealthResponse {
  status: 'ok';
  version: string;
}

// --------------------------------------------------------------------------- //
// Server-Sent Events (GET /api/investigations/{id}/events)
// --------------------------------------------------------------------------- //
export type StatusEventData = Partial<
  Pick<
    Investigation,
    | 'status'
    | 'outcome'
    | 'title'
    | 'selected_skill_ids'
    | 'started_at'
    | 'finished_at'
    | 'duration_ms'
    | 'error'
  >
>;

export interface ToolCallEventData {
  step_id: string;
  call: ToolCall;
}

export interface DoneEventData {
  status: InvestigationStatus;
}

export type InvestigationEvent =
  | { type: 'snapshot'; data: Investigation }
  | { type: 'status'; data: StatusEventData }
  | { type: 'plan'; data: InvestigationPlan }
  | { type: 'step'; data: InvestigationStep }
  | { type: 'tool_call'; data: ToolCallEventData }
  | { type: 'timeline'; data: TimelineEvent[] }
  | { type: 'report'; data: InvestigationReport }
  | { type: 'chat'; data: ChatMessage }
  | { type: 'done'; data: DoneEventData };

export type InvestigationEventType = InvestigationEvent['type'];
