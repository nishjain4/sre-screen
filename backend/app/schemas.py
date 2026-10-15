"""Public API + domain models.

These models are the contract between the backend and the React frontend
(see docs/API.md). Keep them backwards compatible.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


Severity = Literal["critical", "high", "medium", "low", "info"]
DataMode = Literal["live", "simulated", "mcp", "internal"]


class SkillMode(str, Enum):
    NONE = "none"          # send the query straight to the LLM, no tools
    SPECIFIC = "specific"  # run only the skill(s) the user picked
    AUTO = "auto"          # route automatically


class InvestigationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolCallStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class InvestigationCreate(BaseModel):
    query: str = Field(..., min_length=3, max_length=20_000)
    mode: SkillMode = SkillMode.AUTO
    skill_ids: list[str] = Field(default_factory=list)
    # Optional hints that override what is extracted from the query.
    context: dict[str, str] = Field(default_factory=dict)
    template_id: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8_000)


class FeedbackRequest(BaseModel):
    helpful: bool
    comment: str | None = Field(default=None, max_length=4_000)


# --------------------------------------------------------------------------- #
# Investigation building blocks
# --------------------------------------------------------------------------- #
class Entities(BaseModel):
    services: list[str] = Field(default_factory=list)
    namespaces: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
    time_window_minutes: int = 120

    @property
    def primary_service(self) -> str | None:
        return self.services[0] if self.services else None

    @property
    def primary_namespace(self) -> str | None:
        return self.namespaces[0] if self.namespaces else None


class ToolCall(BaseModel):
    id: str = Field(default_factory=new_id)
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: ToolCallStatus = ToolCallStatus.RUNNING
    description: str | None = None
    summary: str | None = None
    error: str | None = None
    data_mode: DataMode | None = None
    output: Any = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    duration_ms: int | None = None


class InvestigationStep(BaseModel):
    id: str = Field(default_factory=new_id)
    index: int
    kind: Literal["intent", "planning", "skill", "analysis", "report"]
    title: str
    description: str = ""
    status: StepStatus = StepStatus.RUNNING
    skill_id: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    duration_ms: int | None = None


class PlanItem(BaseModel):
    skill_id: str
    skill_name: str
    objective: str
    tools: list[str] = Field(default_factory=list)


class InvestigationPlan(BaseModel):
    summary: str
    reasoning: str = ""
    entities: Entities = Field(default_factory=Entities)
    items: list[PlanItem] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    timestamp: datetime
    source: str
    title: str
    detail: str | None = None
    severity: Severity = "info"


class Finding(BaseModel):
    """Structured signal produced by a skill before the LLM sees anything."""
    title: str
    detail: str = ""
    severity: Severity = "medium"
    category: str = "general"
    source: str = ""                      # tool name
    tool_call_id: str | None = None
    remediation: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    score: float = 0.5                    # 0..1 likelihood this is causal


# --------------------------------------------------------------------------- #
# Report (the 5+1 mandatory sections)
# --------------------------------------------------------------------------- #
class RootCause(BaseModel):
    summary: str
    details: str = ""
    confidence: Literal["high", "medium", "low"] = "low"
    category: str = "unknown"


class EvidenceItem(BaseModel):
    title: str
    detail: str = ""
    source: str = ""
    severity: Severity = "info"


class LogFinding(BaseModel):
    pattern: str
    count: int = 0
    level: str = "ERROR"
    first_seen: str | None = None
    last_seen: str | None = None
    sample: str = ""
    interpretation: str = ""


class LogAnalysis(BaseModel):
    summary: str = ""
    findings: list[LogFinding] = Field(default_factory=list)


class RemediationAction(BaseModel):
    priority: int = 1
    action: str
    rationale: str = ""
    command: str | None = None
    risk: Literal["low", "medium", "high"] = "low"
    timeframe: Literal["immediate", "short_term", "long_term"] = "immediate"


class InvestigationReport(BaseModel):
    title: str
    executive_summary: str
    conclusion_summary: str = ""
    severity: Severity = "medium"
    conclusive: bool = False
    affected_services: list[str] = Field(default_factory=list)
    root_cause: RootCause
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    log_analysis: LogAnalysis = Field(default_factory=LogAnalysis)
    recommended_remediation: list[RemediationAction] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    generated_by: str = ""
    data_sources: list[str] = Field(default_factory=list)
    tool_results: list[ToolCall] = Field(default_factory=list)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=new_id)
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime = Field(default_factory=utcnow)


class Feedback(BaseModel):
    helpful: bool
    comment: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Investigation(BaseModel):
    id: str = Field(default_factory=new_id)
    title: str
    query: str
    mode: SkillMode
    requested_skill_ids: list[str] = Field(default_factory=list)
    selected_skill_ids: list[str] = Field(default_factory=list)
    context: dict[str, str] = Field(default_factory=dict)
    template_id: str | None = None
    status: InvestigationStatus = InvestigationStatus.QUEUED
    outcome: Literal["conclusive", "inconclusive"] | None = None
    initiated_by: str = "anonymous"
    orchestrator: str = ""
    llm: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    plan: InvestigationPlan | None = None
    steps: list[InvestigationStep] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    report: InvestigationReport | None = None
    chat: list[ChatMessage] = Field(default_factory=list)
    feedback: Feedback | None = None
    error: str | None = None

    def summary(self) -> "InvestigationSummary":
        return InvestigationSummary(
            id=self.id,
            title=self.title,
            query=self.query,
            mode=self.mode,
            status=self.status,
            outcome=self.outcome,
            selected_skill_ids=self.selected_skill_ids,
            severity=self.report.severity if self.report else None,
            root_cause=self.report.root_cause.summary if self.report else None,
            initiated_by=self.initiated_by,
            created_at=self.created_at,
            finished_at=self.finished_at,
            duration_ms=self.duration_ms,
        )


class InvestigationSummary(BaseModel):
    id: str
    title: str
    query: str
    mode: SkillMode
    status: InvestigationStatus
    outcome: str | None = None
    selected_skill_ids: list[str] = Field(default_factory=list)
    severity: str | None = None
    root_cause: str | None = None
    initiated_by: str = "anonymous"
    created_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None


class InvestigationList(BaseModel):
    items: list[InvestigationSummary]
    total: int


# --------------------------------------------------------------------------- #
# Catalog responses
# --------------------------------------------------------------------------- #
class SkillInfo(BaseModel):
    id: str
    name: str
    description: str
    category: str
    icon: str
    tools: list[str]
    mcp_servers: list[str] = Field(default_factory=list)
    keywords: list[str]
    source: Literal["builtin", "custom"]


class ToolInfo(BaseModel):
    name: str
    description: str
    category: str
    source: str                     # builtin | mcp:<server>
    data_mode: DataMode
    input_schema: dict[str, Any]


class TemplateInfo(BaseModel):
    id: str
    title: str
    description: str
    category: str
    icon: str
    query: str
    mode: SkillMode
    skill_ids: list[str] = Field(default_factory=list)


class MCPServerStatus(BaseModel):
    name: str
    transport: str
    status: Literal["connected", "error", "disabled"]
    tool_count: int = 0
    error: str | None = None


class ServiceConfig(BaseModel):
    llm_provider: str
    llm_model: str
    llm_configured: bool
    orchestrator: str
    available_orchestrators: list[str]
    mcp_servers: list[MCPServerStatus]
    version: str
