"""Example pluggable AI tool-loop orchestrator.

Replace the decision loop with a LangGraph StateGraph or CrewAI crew while keeping
the RunContext progress methods. The API, storage, and event stream remain unchanged.
"""
from __future__ import annotations

import logging

from app.llm.base import LLMError, Message
from app.orchestration.base import Orchestrator, RunContext, register_orchestrator
from app.orchestration.evidence import Evidence
from app.orchestration.native import NativeOrchestrator
from app.orchestration.report import heuristic_report, llm_report
from app.schemas import Entities, Finding, InvestigationPlan, PlanItem

logger = logging.getLogger(__name__)


@register_orchestrator("external_example")
class ExternalExampleOrchestrator(Orchestrator):
    """Small, bounded example of a model selecting and calling registered tools."""

    description = "Example model-driven tool loop (falls back to native offline)"
    max_tool_calls = 8

    async def run(self, ctx: RunContext) -> None:
        if not self.deps.llm.available:
            await NativeOrchestrator(self.deps).run(ctx)
            return

        entities = Entities()
        tools = [tool for tool in self.deps.tools.all()]
        tool_specs = [{"name": tool.name, "description": tool.description[:240],
                       "input_schema": tool.input_schema} for tool in tools]
        plan = InvestigationPlan(
            summary="Let the model select diagnostic tools",
            reasoning="The external example adapter chooses from the registered tool catalog.",
            entities=entities,
            items=[PlanItem(skill_id="external-tool-loop", skill_name="AI tool loop",
                            objective="Select read-only tools that gather relevant evidence.",
                            tools=[tool.name for tool in tools])],
        )
        planning = await ctx.start_step("planning", "Plan AI tool loop")
        await ctx.set_plan(plan)
        await ctx.finish_step(planning)

        evidence = Evidence()
        history: list[Message] = [
            Message("system", "Choose one relevant read-only tool per turn. Return JSON with keys tool, arguments, done. "
                    "Set done=true when evidence is sufficient. Never invent tool names or arguments."),
            Message("user", f"Investigation: {ctx.inv.query[:5000]}\nEntities: {entities.model_dump_json()}\n"
                    f"Available tools: {tool_specs}"),
        ]
        for index in range(self.max_tool_calls):
            try:
                choice = await self.deps.llm.complete_json(history, temperature=0)
            except LLMError as exc:
                logger.warning("tool selector failed: %s", exc)
                break
            if choice.get("done") is True:
                break
            name = choice.get("tool")
            args = choice.get("arguments")
            if not isinstance(name, str) or not self.deps.tools.has(name) or not isinstance(args, dict):
                history.append(Message("assistant", str(choice)[:1000]))
                history.append(Message("user", "Invalid tool choice; choose a registered tool and object arguments, or set done=true."))
                continue
            step = await ctx.start_step("skill", f"AI tool {index + 1}: {name}", skill_id="external-tool-loop")
            outcome = await ctx.executor.call(step, name, args)
            await ctx.finish_step(step, findings=[outcome.summary] if outcome.summary else [])
            evidence.calls.append(outcome.call)
            if outcome.ok:
                evidence.findings.append(Finding(
                    title=outcome.summary or f"Collected evidence from {name}",
                    detail=str(outcome.data)[:800], source=name, category="tool_observation", score=0.35,
                ))
            history.append(Message("assistant", str(choice)[:1000]))
            history.append(Message("user", f"Tool {name} returned {'success' if outcome.ok else 'error'}: "
                                   f"{(outcome.summary or outcome.call.error or '')[:1200]}. Continue or finish."))

        evidence.calls = list(ctx.executor.calls)
        await ctx.set_timeline(evidence.merged_timeline())
        analysis = await ctx.start_step("analysis", "Analyze tool results")
        report = heuristic_report(ctx.inv, evidence, [])
        try:
            report = await llm_report(self.deps.llm, ctx.inv, evidence, report)
        except Exception as exc:  # noqa: BLE001 - keep a usable deterministic result
            logger.warning("AI report generation failed; keeping rule-based report: %s", exc)
        await ctx.set_report(report)
        await ctx.finish_step(analysis, findings=[report.root_cause.summary])