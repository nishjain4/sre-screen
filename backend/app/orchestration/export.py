"""Investigation export formats."""
from __future__ import annotations

import json

from app.schemas import Investigation


def export_json(inv: Investigation) -> str:
    return inv.model_dump_json(indent=2)


def export_markdown(inv: Investigation) -> str:
    report = inv.report
    lines = [f"# {inv.title}", "", f"- **Status:** {inv.status.value}",
             f"- **Started:** {inv.started_at.isoformat() if inv.started_at else 'Not started'}",
             f"- **Finished:** {inv.finished_at.isoformat() if inv.finished_at else 'In progress'}",
             f"- **Requested by:** {inv.initiated_by}", "", "## Request", "", inv.query, ""]
    if report is None:
        lines.extend(["## Result", "", inv.error or "The investigation has not produced a report yet.", ""])
    else:
        lines.extend([
            "## Executive Summary", "", report.executive_summary, "",
            "## Root Cause", "", f"**{report.root_cause.summary}** ({report.root_cause.confidence} confidence)",
            "", report.root_cause.details or "No additional details.", "",
            "## Supporting Evidence", "",
        ])
        lines.extend([f"- **{item.title}** ({item.severity}, {item.source}): {item.detail}"
                      for item in report.supporting_evidence] or ["- No supporting evidence."])
        lines.extend(["", "## Log Analysis", "", report.log_analysis.summary or "No log analysis.", ""])
        lines.extend([f"- {item.count}x `{item.pattern}` ({item.level})"
                      for item in report.log_analysis.findings] or ["- No log findings."])
        lines.extend(["", "## MCP and Diagnostic Tool Results", ""])
        for call in report.tool_results:
            lines.extend([
                f"### {call.tool} ({call.status.value}, {call.data_mode or 'unverified source'})", "",
                call.description or "", "", call.error or call.summary or "No summary returned.", "",
                "Arguments:", "", "````json", json.dumps(call.args, indent=2, default=str), "````", "",
                "Result:", "", "````json", json.dumps(call.output, indent=2, default=str), "````", "",
            ])
        lines.extend(["", "## Recommended Remediation", ""])
        lines.extend([f"{item.priority}. **{item.action}** ({item.risk} risk, {item.timeframe})"
                      + (f"\n   ```text\n   {item.command}\n   ```" if item.command else "")
                      for item in report.recommended_remediation] or ["- No remediation recommendations."])
        lines.extend(["", "## Next Steps", ""])
        lines.extend([f"- {item}" for item in report.next_steps] or ["- None specified."])
        lines.extend(["", "## Conclusion Summary", "",
                      report.conclusion_summary or report.executive_summary, ""])
        lines.extend(["", "## Timeline", ""])
        lines.extend([f"- {event.timestamp.isoformat()} **{event.source}:** {event.title}"
                      + (f" - {event.detail}" if event.detail else "")
                      for event in inv.timeline] or ["- No timestamped events."])
        lines.extend(["", "## Investigation Steps", ""])
        for step in inv.steps:
            lines.append(f"- **{step.title}** ({step.status.value})")
            lines.extend([f"  - {finding}" for finding in step.findings])
    return "\n".join(lines).rstrip() + "\n"


def export_payload(inv: Investigation, format: str) -> tuple[str, str, str]:
    """Return (body, media type, extension) for the requested export format."""
    if format == "json":
        return export_json(inv), "application/json", "json"
    if format == "markdown":
        return export_markdown(inv), "text/markdown; charset=utf-8", "md"
    raise ValueError("format must be 'markdown' or 'json'")