"""Follow-up chat about a finished (or running) investigation."""
from __future__ import annotations

import json
import re

from app.llm import prompts
from app.llm.base import LLMProvider, Message
from app.schemas import Investigation, ToolCallStatus

MAX_HISTORY = 12


def evidence_digest(inv: Investigation, budget: int) -> str:
    lines = []
    for step in inv.steps:
        if step.kind != "skill" and not step.tool_calls:
            continue
        lines.append(f"### {step.title} ({step.status.value})")
        lines += [f"- finding: {finding}" for finding in step.findings]
        for c in step.tool_calls:
            res = c.summary if c.status == ToolCallStatus.SUCCESS else f"ERROR {c.error}"
            lines.append(f"- {c.tool}({json.dumps(c.args, default=str)}) -> {res or ''}")
    lines += [f"- {e.timestamp.strftime('%H:%M')} [{e.source}] {e.title}"
              + (f" - {e.detail}" if e.detail else "") for e in inv.timeline]
    return "\n".join(lines)


def _offline_answer(inv: Investigation, question: str) -> str:
    r = inv.report
    if r is None:
        return "The investigation has not produced a report yet - ask again once it completes."
    q = question.lower()
    if re.search(r"conclusion|summari[sz]e|summary", q) and r.conclusion_summary:
        return r.conclusion_summary
    if r.root_cause.category in {"pr_blocker", "pr_incomplete"}:
        return (
            f"**{r.root_cause.summary}**\n\n{r.root_cause.details}\n\n"
            "**Recommended actions:**\n\n"
            + "\n".join(f"{a.priority}. {a.action}" for a in r.recommended_remediation)
            + "\n\n_No tests were executed by this code review. No remote review comments were posted._"
        )
    if re.search(r"fix|remediat|mitigat|resolve|what (should|do) (i|we)|command|rollback|roll back", q):
        items = [f"{a.priority}. **{a.action}**" + (f"\n   `{a.command}`" if a.command else "") for a in r.recommended_remediation]
        return "**Recommended remediation (in priority order):**\n\n" + ("\n".join(items) or "No remediation was derived.")
    if re.search(r"log|error|exception|stack", q):
        items = [f"- {lf.count}x `{lf.pattern}` ({lf.level}; first {lf.first_seen or 'unknown'}, "
             f"last {lf.last_seen or 'unknown'})"
             + (f" - {lf.interpretation}" if lf.interpretation else "")
             + (f"\n  Sample: `{lf.sample}`" if lf.sample else "")
             for lf in r.log_analysis.findings]
        return f"**Log analysis:** {r.log_analysis.summary}\n\n" + ("\n".join(items) or "No log patterns were collected.")
    if re.search(r"when|timeline|start|began|sequence", q):
        items = [f"- `{e.timestamp.strftime('%Y-%m-%d %H:%M')}` **{e.source}** - {e.title}" for e in inv.timeline[-15:]]
        return "**Timeline (UTC):**\n\n" + ("\n".join(items) or "No timestamped events were collected.")
    if re.search(r"evidence|why|how do (you|we) know|proof|sure|confiden", q):
        items = [f"- **{e.title}** ({e.source}, {e.severity})" for e in r.supporting_evidence[:8]]
        return (f"Root cause confidence is **{r.root_cause.confidence}**. Supporting evidence:\n\n" + "\n".join(items))
    if re.search(r"prevent|again|recurr|long[- ]term", q):
        items = [f"- {a.action}" for a in r.recommended_remediation if a.timeframe != "immediate"] + [f"- {s}" for s in r.next_steps]
        return "**Preventing recurrence:**\n\n" + "\n".join(items[:8])
    if re.search(r"next|investigat|else|other", q):
        return "**Next investigation steps:**\n\n" + "\n".join(f"- {s}" for s in r.next_steps)
    return (f"**Root cause ({r.root_cause.confidence} confidence):** {r.root_cause.summary}\n\n{r.root_cause.details}\n\n"
            "_The AI model is not configured (set `LLM_PROVIDER=bedrock` and configure AWS credentials), so answers are assembled from the report. "
            "Ask about remediation, logs, timeline, evidence or prevention._")


async def answer(llm: LLMProvider, inv: Investigation, question: str, budget: int) -> str:
    if re.search(r"log|error|exception|stack", question, re.I):
        return _offline_answer(inv, question)
    if not llm.available:
        return _offline_answer(inv, question)
    if inv.report and inv.report.root_cause.category in {"pr_blocker", "pr_incomplete"}:
        report = (inv.report.root_cause.details + "\n\nRecommended actions:\n"
                  + "\n".join(a.action for a in inv.report.recommended_remediation))
        if len(report) > budget // 2:
            return _offline_answer(inv, question)
    else:
        report = inv.report.model_dump_json(exclude={"suggested_questions"}) if inv.report else "(not generated yet)"
    context = prompts.CHAT_CONTEXT.format(query=inv.query[:4000], report=report[: budget // 2],
                                          evidence=evidence_digest(inv, budget // 2))
    messages = [Message("system", prompts.CHAT_SYSTEM + "\n\n" + context)]
    for m in inv.chat[-MAX_HISTORY:]:
        messages.append(Message(m.role, m.content[:4000]))
    messages.append(Message("user", question))
    return (await llm.complete(messages, temperature=0.1)).strip()
