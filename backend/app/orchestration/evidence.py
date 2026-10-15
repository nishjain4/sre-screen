"""Evidence aggregation: rank findings, dedupe the timeline and render a budgeted context for the LLM."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.schemas import Finding, LogFinding, TimelineEvent, ToolCall, ToolCallStatus
from app.skills.base import SkillResult

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def rank(f: Finding) -> float:
    """Causal likelihood weighted by severity."""
    return f.score * (0.5 + 0.125 * _SEVERITY_RANK.get(f.severity, 0))


@dataclass
class Evidence:
    findings: list[Finding] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    log_findings: list[LogFinding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    skills_run: list[str] = field(default_factory=list)

    def add(self, skill_name: str, result: SkillResult) -> None:
        self.skills_run.append(skill_name)
        self.findings.extend(result.findings)
        self.timeline.extend(result.timeline)
        self.log_findings.extend(result.log_findings)
        self.notes.extend(f"[{skill_name}] {n}" for n in result.notes)

    def ranked_findings(self) -> list[Finding]:
        seen: set[str] = set()
        out = []
        for f in sorted(self.findings, key=rank, reverse=True):
            key = f.title.lower().strip()
            if key not in seen:
                seen.add(key)
                out.append(f)
        return out

    def merged_timeline(self, limit: int | None = None) -> list[TimelineEvent]:
        out = sorted(self.timeline, key=lambda e: e.timestamp)
        return out[-limit:] if limit is not None else out

    def merged_log_findings(self, limit: int | None = None) -> list[LogFinding]:
        level_rank = {"FATAL": 3, "ERROR": 2, "WARN": 1}
        ordered = sorted(self.log_findings, key=lambda lf: (level_rank.get(lf.level, 0), lf.count), reverse=True)
        return ordered[:limit] if limit is not None else ordered

    def data_sources(self) -> list[str]:
        modes: dict[str, set[str]] = {}
        for c in self.calls:
            if c.status == ToolCallStatus.SUCCESS:
                modes.setdefault(c.data_mode or "live", set()).add(c.tool)
        return [f"{mode}: {', '.join(sorted(tools))}" for mode, tools in sorted(modes.items())]

    @property
    def simulated(self) -> bool:
        return any(c.data_mode == "simulated" for c in self.calls)

    @property
    def failed_calls(self) -> list[ToolCall]:
        return [c for c in self.calls if c.status == ToolCallStatus.ERROR]


def render_context(ev: Evidence) -> str:
    """Render all collected evidence for report synthesis without clipping details."""
    sections: list[tuple[str, list[str]]] = []
    lines = []
    for i, f in enumerate(ev.ranked_findings(), start=1):
        extra = ""
        if f.remediation:
            extra += f"\n   remediation hints: {'; '.join(f.remediation[:3])}"
        if f.commands:
            extra += f"\n   commands: {' | '.join(f.commands[:3])}"
        lines.append(f"{i}. [{f.severity}, causal-likelihood {f.score:.2f}, {f.category}, via {f.source}] {f.title}"
                     + (f"\n   {f.detail}" if f.detail else "") + extra)
    sections.append(("## Findings (ranked)", lines or ["(no findings)"]))

    lines = [f"- {lf.count}x {lf.level} `{lf.pattern}` first {lf.first_seen or '?'} last {lf.last_seen or '?'}"
             + (f" - {lf.interpretation}" if lf.interpretation else "") + f"\n  sample: {lf.sample}"
             for lf in ev.merged_log_findings()]
    sections.append(("## Log patterns", lines or ["(no error log patterns)"]))

    lines = [f"- {e.timestamp.strftime('%Y-%m-%d %H:%M')} UTC [{e.source}] {e.title}"
             + (f" - {e.detail}" if e.detail else "") for e in ev.merged_timeline()]
    sections.append(("## Timeline", lines or ["(no timestamped events)"]))

    lines = []
    for c in ev.calls:
        status = c.summary if c.status == ToolCallStatus.SUCCESS else f"ERROR: {c.error}"
        lines.append(f"- {c.tool}({json.dumps(c.args, default=str)}) [{c.data_mode or '-'}] -> {status or ''}")
    sections.append(("## Tool calls", lines or ["(none)"]))
    if ev.notes:
        sections.append(("## Notes", [f"- {note}" for note in ev.notes]))

    out = [line for header, body in sections for line in (header, *body, "")]
    if ev.simulated:
        out.append("NOTE: some tools returned SIMULATED demo data (no live backend configured).")
    return "\n".join(out)
