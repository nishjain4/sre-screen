"""Skill abstraction.

A skill is a focused investigation playbook (e.g. "Database Investigation").
It calls tools through ``SkillContext.call`` (traced + streamed) and returns
structured ``Finding``s, timeline events and log findings. Most analysis is deterministic and the orchestrator hands the evidence
to the LLM afterwards. Gitea PR code review additionally uses a model to inspect
the remote diff, with deterministic checks for evidence and merge warnings.
"""
from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from collections.abc import AsyncIterator, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any

from app.core.executor import ToolExecutor, ToolOutcome
from app.core.tools import ToolRegistry
from app.orchestration.timeline import parse_ts
from app.llm.base import LLMProvider
from app.schemas import Entities, Finding, Investigation, InvestigationStep, LogFinding, SkillInfo, TimelineEvent


@dataclass
class SkillContext:
    investigation: Investigation
    entities: Entities
    step: InvestigationStep
    executor: ToolExecutor
    registry: ToolRegistry
    llm: LLMProvider
    shared: dict[str, Any] = field(default_factory=dict)   # cache shared by skills of one investigation
    max_targets: int = 2
    gitea_url: str | None = None
    trace_step: Callable[[str, str], AbstractAsyncContextManager[InvestigationStep]] | None = None

    @asynccontextmanager
    async def phase(self, title: str, description: str = "") -> AsyncIterator[SkillContext]:
        if self.trace_step is None:
            yield self
        else:
            async with self.trace_step(title, description) as step:
                yield replace(self, step=step)

    async def call(self, tool: str, args: dict[str, Any] | None = None, description: str | None = None) -> ToolOutcome:
        return await self.executor.call(self.step, tool, args, description)

    async def call_many(self, calls: list[tuple[str, dict[str, Any], str]]) -> list[ToolOutcome]:
        return list(await asyncio.gather(*(self.call(t, a, d) for t, a, d in calls)))

    def has_tool(self, name: str) -> bool:
        return self.registry.has(name)

    @property
    def window(self) -> int:
        return max(60, min(self.entities.time_window_minutes, 24 * 60))


@dataclass
class SkillResult:
    findings: list[Finding] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    log_findings: list[LogFinding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, outcome: ToolOutcome | None = None, **kwargs: Any) -> Finding:
        f = Finding(**kwargs)
        if outcome is not None:
            f.source = f.source or outcome.call.tool
            f.tool_call_id = outcome.call.id
        self.findings.append(f)
        return f

    def event(self, ts: Any, source: str, title: str, detail: str | None = None, severity: str = "info") -> None:
        dt = parse_ts(ts)
        if dt is not None:
            self.timeline.append(TimelineEvent(timestamp=dt, source=source, title=title, detail=detail, severity=severity))  # type: ignore[arg-type]

    def merge(self, other: "SkillResult") -> None:
        self.findings.extend(other.findings)
        self.timeline.extend(other.timeline)
        self.log_findings.extend(other.log_findings)
        self.notes.extend(other.notes)


class Skill(ABC):
    id: str
    name: str
    description: str
    category: str
    icon: str = "default"
    keywords: list[str] = []
    tools: list[str] = []
    source: str = "builtin"
    # Skills run in phases; skills of the same phase run in parallel. Later phases can use
    # what earlier skills put into ``SkillContext.shared`` (e.g. hosts that failed to resolve).
    phase: int = 0
    def objective(self, entities: Entities) -> str:
        target = ", ".join(entities.services[:2]) or "the affected workloads"
        return f"{self.description.rstrip('.')} for {target}."

    def available(self, registry: ToolRegistry) -> bool:
        return any(registry.has(t) for t in self.tools) if self.tools else True

    @abstractmethod
    async def execute(self, ctx: SkillContext) -> SkillResult: ...

    def info(self) -> SkillInfo:
        return SkillInfo(id=self.id, name=self.name, description=self.description, category=self.category,
                         icon=self.icon, tools=list(self.tools), keywords=list(self.keywords),
                         source="custom" if self.source == "custom" else "builtin")
