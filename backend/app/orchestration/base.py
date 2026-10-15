"""Orchestrator interface + plug-in registry.

An orchestrator turns an ``Investigation`` into steps, tool calls and a report. Everything
framework-specific lives behind this interface; the API, persistence and streaming only
see the ``RunContext`` methods. To plug in another framework (LangGraph, CrewAI, Semantic
Kernel, AutoGen, a hosted agent...) implement ``Orchestrator.run`` with it, report progress
through ``RunContext`` and decorate the class with ``@register_orchestrator("name")``;
then set ``ORCHESTRATOR=name``. See ``adapters/external_example.py``.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.core.executor import ToolExecutor
from app.core.tools import ToolRegistry
from app.llm.base import LLMProvider
from app.schemas import (Investigation, InvestigationPlan, InvestigationReport, InvestigationStep, StepStatus,
                         TimelineEvent, ToolCall, utcnow)
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

Publish = Callable[[str, Any], Awaitable[None]]


@dataclass
class OrchestratorDeps:
    settings: Settings
    llm: LLMProvider
    tools: ToolRegistry
    skills: SkillRegistry


def dump(model: Any) -> Any:
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else model


class RunContext:
    """Progress API handed to orchestrators: steps, tool execution, plan, timeline, report."""

    def __init__(self, inv: Investigation, deps: OrchestratorDeps, publish: Publish,
                 persist: Callable[[], Awaitable[None]]) -> None:
        self.inv = inv
        self.deps = deps
        self._publish = publish
        self._persist = persist
        self._last_persist = 0.0
        self.executor = ToolExecutor(deps.tools, timeout=deps.settings.tool_timeout_seconds,
                                     concurrency=deps.settings.tool_concurrency, on_update=self._on_call,
                                     query=inv.query, gitea_url=deps.settings.gitea_url)

    async def emit(self, event: str, data: Any) -> None:
        await self._publish(event, dump(data))

    async def _on_call(self, step: InvestigationStep, call: ToolCall) -> None:
        await self.emit("tool_call", {"step_id": step.id, "call": dump(call)})
        await self.checkpoint()

    async def checkpoint(self, force: bool = False) -> None:
        """Persist progress (throttled) so a page reload mid-run shows recent state."""
        now = time.monotonic()
        if force or now - self._last_persist > 2.0:
            self._last_persist = now
            await self._persist()

    async def start_step(self, kind: str, title: str, description: str = "", skill_id: str | None = None) -> InvestigationStep:
        step = InvestigationStep(index=len(self.inv.steps), kind=kind, title=title,  # type: ignore[arg-type]
                                 description=description, skill_id=skill_id)
        self.inv.steps.append(step)
        await self.emit("step", step)
        return step

    async def finish_step(self, step: InvestigationStep, status: StepStatus = StepStatus.COMPLETED,
                          findings: list[str] | None = None, description: str | None = None) -> None:
        step.status = status
        step.finished_at = utcnow()
        step.duration_ms = int((step.finished_at - step.started_at).total_seconds() * 1000)
        if findings is not None:
            step.findings = findings
        if description is not None:
            step.description = description
        await self.emit("step", step)
        await self.checkpoint()

    async def update_step(self, step: InvestigationStep) -> None:
        await self.emit("step", step)

    async def set_plan(self, plan: InvestigationPlan) -> None:
        self.inv.plan = plan
        self.inv.selected_skill_ids = [i.skill_id for i in plan.items]
        await self.emit("plan", plan)
        await self.emit_status()

    async def set_timeline(self, events: list[TimelineEvent]) -> None:
        self.inv.timeline = events
        await self.emit("timeline", [dump(e) for e in events])

    async def set_report(self, report: InvestigationReport) -> None:
        self.inv.report = report
        self.inv.title = report.title or self.inv.title
        self.inv.outcome = "conclusive" if report.conclusive else "inconclusive"
        await self.emit("report", report)

    async def emit_status(self) -> None:
        i = self.inv
        await self.emit("status", {"status": i.status.value, "outcome": i.outcome, "title": i.title,
                                   "selected_skill_ids": i.selected_skill_ids,
                                   "started_at": i.started_at.isoformat() if i.started_at else None,
                                   "finished_at": i.finished_at.isoformat() if i.finished_at else None,
                                   "duration_ms": i.duration_ms, "error": i.error})


class Orchestrator(ABC):
    name: str = "base"
    description: str = ""

    def __init__(self, deps: OrchestratorDeps) -> None:
        self.deps = deps

    @abstractmethod
    async def run(self, ctx: RunContext) -> None:
        """Execute the investigation; must end with ``ctx.set_report``. Exceptions mark it failed."""

    async def chat(self, inv: Investigation, message: str) -> str:
        from app.orchestration.chat import answer

        return await answer(self.deps.llm, inv, message, self.deps.settings.llm_max_context_chars)


_REGISTRY: dict[str, type[Orchestrator]] = {}


def register_orchestrator(name: str) -> Callable[[type[Orchestrator]], type[Orchestrator]]:
    def wrap(cls: type[Orchestrator]) -> type[Orchestrator]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls
    return wrap


def available_orchestrators() -> list[str]:
    _load_builtin()
    return sorted(_REGISTRY)


def create_orchestrator(name: str, deps: OrchestratorDeps) -> Orchestrator:
    _load_builtin()
    cls = _REGISTRY.get(name)
    if cls is None:
        logger.warning("unknown orchestrator %r, using 'native' (available: %s)", name, ", ".join(sorted(_REGISTRY)))
        cls = _REGISTRY["native"]
    return cls(deps)


def _load_builtin() -> None:
    # imported lazily so the modules can import this one
    from app.orchestration import native  # noqa: F401
    from app.orchestration.adapters import external_example  # noqa: F401
