"""Default rule-driven investigation orchestrator."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from app.llm.base import LLMError
from app.llm.offline_provider import OfflineProvider
from app.orchestration.base import Orchestrator, RunContext, register_orchestrator
from app.orchestration.evidence import Evidence
from app.orchestration.report import direct_report, heuristic_report, llm_report
from app.orchestration.router import route
from app.schemas import Entities, InvestigationPlan, PlanItem, SkillMode, StepStatus, ToolCallStatus
from app.skills.base import SkillContext, SkillResult
from app.skills.repository_query import wants_repository_overview

logger = logging.getLogger(__name__)
@register_orchestrator("native")
class NativeOrchestrator(Orchestrator):
    """Investigate with deterministic skills and use an LLM only for synthesis."""

    description = "Rule-based skill orchestration with optional AI analysis"

    async def run(self, ctx: RunContext) -> None:
        inv = ctx.inv
        intent = await ctx.start_step("intent", "Understand the request", "Identify the requested Gitea operation")
        entities = Entities()
        await ctx.finish_step(intent)

        if inv.mode == SkillMode.NONE:
            await ctx.set_plan(InvestigationPlan(summary="No diagnostic skills selected", entities=entities))
            step = await ctx.start_step("report", "Answer without diagnostic tools")
            try:
                report = await direct_report(self.deps.llm, inv)
            except LLMError as exc:
                logger.warning("direct AI answer failed; returning offline guidance: %s", exc)
                report = await direct_report(OfflineProvider(), inv)
            await ctx.set_report(report)
            await ctx.finish_step(step, findings=[report.root_cause.summary])
            return

        available = self.deps.skills.available()
        available_by_id = {skill.id: skill for skill in available}
        if inv.mode == SkillMode.SPECIFIC:
            requested = ["gitea_repository_discovery" if sid == "gitea_investigation" else sid
                         for sid in dict.fromkeys(inv.requested_skill_ids)]
            selected = [available_by_id[sid] for sid in requested if sid in available_by_id]
            reasoning = "Using the skills selected for this investigation."
        else:
            decision = await route(inv.query, available, self.deps.llm,
                                   self.deps.settings.max_auto_skills)
            selected = [available_by_id[sid] for sid in decision.skill_ids if sid in available_by_id]
            reasoning = decision.reasoning

        routing = await ctx.start_step("planning", "Identify matching skills and MCP servers", reasoning)
        await ctx.finish_step(routing, findings=[
            f"{skill.name}: " + (", ".join(sorted({
                tool.source for name in skill.tools if (tool := self.deps.tools.get(name)) is not None
            })) or "Dynamic tool selection")
            for skill in selected
        ] or ["No matching skill is available; evidence coverage will be incomplete."])
        plan = InvestigationPlan(
            summary=f"Run {len(selected)} Gitea skill(s) for this repository request",
            reasoning=reasoning,
            entities=entities,
            items=[PlanItem(skill_id=skill.id, skill_name=skill.name,
                            objective=skill.objective(entities), tools=list(skill.tools)) for skill in selected],
        )
        planning = await ctx.start_step("planning", "Plan investigation", reasoning)
        await ctx.set_plan(plan)
        await ctx.finish_step(planning, findings=[item.skill_name for item in plan.items])

        evidence = Evidence()
        shared: dict = {}
        by_phase: dict[int, list] = {}
        for skill in selected:
            by_phase.setdefault(skill.phase, []).append(skill)

        for phase in sorted(by_phase):
            phase_skills = by_phase[phase]
            results = await asyncio.gather(
                *(self._run_skill(ctx, skill, entities, shared) for skill in phase_skills),
                return_exceptions=True,
            )
            for skill, result in zip(phase_skills, results):
                if isinstance(result, SkillResult):
                    evidence.add(skill.name, result)
                elif isinstance(result, BaseException):
                    evidence.notes.append(f"[{skill.name}] Skill failed: {type(result).__name__}: {result}")
                    logger.warning("skill %s failed", skill.id, exc_info=result)
            evidence.calls = list(ctx.executor.calls)
            await ctx.set_timeline(evidence.merged_timeline())
            await ctx.checkpoint(force=True)

        coverage = await ctx.start_step("analysis", "Validate evidence coverage",
                                        "Account for successful, failed, unavailable, and simulated sources")
        evidence.calls = list(ctx.executor.calls)
        await ctx.finish_step(coverage, findings=[
            f"{sum(call.status == ToolCallStatus.SUCCESS for call in evidence.calls)} successful tool calls",
            *[f"{call.tool}: {call.error}" for call in evidence.failed_calls],
            *evidence.notes,
            *(["Simulated sources were used; production health is not verified."] if evidence.simulated else []),
        ])
        correlation = await ctx.start_step("analysis", "Correlate findings and timeline",
                                           "Order timestamped events and compare independently collected signals")
        await ctx.finish_step(correlation, findings=[
            f"{len(evidence.ranked_findings())} distinct findings; "
            f"{len(evidence.merged_timeline())} timestamped events",
            "Temporal correlation alone does not establish causation.",
        ])
        analysis = await ctx.start_step("analysis", "Analyze collected evidence")
        evidence.calls = list(ctx.executor.calls)
        report = heuristic_report(inv, evidence, [])
        if self.deps.llm.available:
            try:
                report = await llm_report(self.deps.llm, inv, evidence, report)
            except Exception as exc:  # noqa: BLE001 - preserve the deterministic report on model errors
                logger.warning("AI report generation failed; keeping rule-based report: %s", exc)
        await ctx.finish_step(analysis, findings=[report.root_cause.summary])
        remediation = await ctx.start_step("analysis", "Review remediation safety",
                                           "Separate recommendations from authorized actions and verified recovery")
        await ctx.finish_step(remediation, findings=[
            *[f"{action.risk} risk: {action.action}" for action in report.recommended_remediation],
            "Recommendations are not executed by report generation; recovery requires post-change health checks.",
        ])
        reporting = await ctx.start_step("report", "Publish evidence-backed report",
                                         "Include each tool result, failure, data source, and log analysis")
        report.tool_results = list(evidence.calls)
        await ctx.set_report(report)
        await ctx.finish_step(reporting, findings=[
            f"{len(report.tool_results)} tool results retained; conclusion: "
            f"{'conclusive' if report.conclusive else 'inconclusive'}",
        ])
        await ctx.set_timeline(evidence.merged_timeline())
        await ctx.checkpoint(force=True)

    async def _run_skill(self, ctx: RunContext, skill, entities, shared: dict) -> SkillResult:
        step = await ctx.start_step("skill", skill.name, skill.objective(entities), skill.id)

        @asynccontextmanager
        async def trace_step(title: str, description: str):
            phase = await ctx.start_step("analysis", title, description, skill.id)
            try:
                yield phase
            except asyncio.CancelledError:
                await ctx.finish_step(phase, status=StepStatus.SKIPPED, findings=["Investigation cancelled"])
                raise
            except Exception as exc:
                await ctx.finish_step(phase, status=StepStatus.FAILED, findings=[str(exc)])
                raise
            else:
                failed = [call for call in phase.tool_calls if call.status == ToolCallStatus.ERROR]
                await ctx.finish_step(
                    phase, status=StepStatus.FAILED if failed else StepStatus.COMPLETED,
                    findings=[*phase.findings,
                              *[call.error or call.summary or call.tool for call in phase.tool_calls]],
                )

        skill_ctx = SkillContext(
            investigation=ctx.inv, entities=entities, step=step, executor=ctx.executor,
            registry=self.deps.tools, llm=self.deps.llm, shared=shared,
            gitea_url=self.deps.settings.gitea_url,
            trace_step=trace_step,
        )
        timeout = getattr(self.deps.settings, "skill_timeout_seconds",
                          max(60.0, self.deps.settings.tool_timeout_seconds * 4))
        try:
            if skill.id == "gitea_pull_requests" or (
                skill.id == "gitea_repository_discovery" and wants_repository_overview(ctx.inv.query)
            ):
                # A PR may require many sequential diff batches. Individual I/O calls retain timeouts.
                result = await skill.execute(skill_ctx)
            else:
                result = await asyncio.wait_for(skill.execute(skill_ctx), timeout=timeout)
            if not isinstance(result, SkillResult):
                raise TypeError(f"skill returned {type(result).__name__}, expected SkillResult")
            await ctx.finish_step(step, findings=[finding.title for finding in result.findings])
            return result
        except asyncio.TimeoutError:
            message = f"Skill timed out after {timeout:g} seconds"
            await ctx.finish_step(step, status=StepStatus.FAILED, findings=[message])
            return SkillResult(notes=[message])
        except asyncio.CancelledError:
            await ctx.finish_step(step, status=StepStatus.SKIPPED, findings=["Investigation cancelled"])
            raise
        except Exception as exc:  # noqa: BLE001 - one failing skill must not abort its phase
            message = f"Skill failed: {type(exc).__name__}: {exc}"
            await ctx.finish_step(step, status=StepStatus.FAILED, findings=[message])
            logger.exception("skill %s failed", skill.id)
            return SkillResult(notes=[message])