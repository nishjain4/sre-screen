"""Report generation.

``heuristic_report`` builds a complete report from ranked findings with no LLM (offline mode
and fallback). ``llm_report`` asks the model for the same structure and merges the result
over the heuristic one, so a partial / malformed model answer still yields a valid report.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.llm import prompts
from app.llm.base import LLMError, LLMProvider, Message
from app.orchestration.evidence import Evidence, rank, render_context
from app.schemas import (EvidenceItem, Finding, Investigation, InvestigationReport, LogAnalysis, LogFinding,
                         RemediationAction, RootCause, ToolCallStatus)
from app.skills.gitea_pr_review import wants_pr_review

logger = logging.getLogger(__name__)
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

_SYMPTOM_CATEGORIES = {"alerts", "availability", "http", "history", "timeline", "external", "change"}
_SEVERITIES = ("critical", "high", "medium", "low", "info")


def _confidence(top: Finding | None, runner_up: Finding | None) -> str:
    if top is None:
        return "low"
    margin = rank(top) - (rank(runner_up) if runner_up else 0)
    if top.score >= 0.85 and _SEVERITY_RANK.get(top.severity, 0) >= 3:
        return "high"
    if top.score >= 0.6 and (margin > 0.05 or top.score >= 0.7):
        return "medium"
    return "low"


def _risk(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("terminate", "rollback", "roll back", "undo", "restart", "failover", "fail over", "delete")):
        return "medium"
    if any(w in t for w in ("drop", "truncate", "force")):
        return "high"
    return "low"


def _remediation(ranked: list[Finding]) -> list[RemediationAction]:
    actions: list[RemediationAction] = []
    seen: set[str] = set()
    for f in ranked:
        cmds = list(f.commands)
        for i, action in enumerate(f.remediation or ([f"Fix: {f.title}"] if cmds else [])):
            key = action.lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            cmd = cmds[i] if i < len(cmds) else None
            actions.append(RemediationAction(
                priority=len(actions) + 1, action=action, rationale=f"Addresses: {f.title}", command=cmd,
                risk=_risk(action + " " + (cmd or "")),  # type: ignore[arg-type]
                timeframe="immediate" if len(actions) < 2 else "short_term" if len(actions) < 4 else "long_term"))
        if len(actions) >= 6:
            break
    return actions


def _next_steps(ev: Evidence, ranked: list[Finding], services: list[str]) -> list[str]:
    steps: list[str] = []
    for c in ev.failed_calls:
        steps.append(f"Re-run `{c.tool}` - it failed during this investigation ({c.error or ''})")
    if ranked:
        steps.append("Verify the referenced Gitea records and commit against the current repository state.")
    return list(dict.fromkeys(steps)) or ["Ask a focused question about a Gitea repository, PR, issue, commit, workflow, tag, or release."]


def _questions(root: Finding | None, services: list[str]) -> list[str]:
    qs = []
    if root:
        qs.append("Which repository evidence supports this finding?")
    qs += ["What changed in the relevant commit or pull request?",
           "Which related tests or CI checks should be reviewed?",
           "What additional Gitea evidence is needed?"]
    return qs[:3]


def _log_analysis(ev: Evidence) -> LogAnalysis:
    findings = ev.merged_log_findings()
    if not findings:
        log_calls = [call for call in ev.calls if "log" in call.tool.lower()]
        completed = [call for call in log_calls if call.status == ToolCallStatus.SUCCESS]
        failed = [call for call in log_calls if call.status == ToolCallStatus.ERROR]
        if not log_calls:
            summary = "No log sources were queried, so log health was not assessed."
        elif failed and not completed:
            summary = "Log analysis could not be completed: " + "; ".join(
                f"{call.tool}: {call.error or 'tool failed'}" for call in failed)
        elif failed:
            summary = ("No error patterns were returned by successful log queries. Some log checks failed: "
                       + "; ".join(f"{call.tool}: {call.error or 'tool failed'}" for call in failed))
        else:
            summary = ("Log sources were queried, but returned no ERROR/WARN patterns: "
                       + ", ".join(call.tool for call in completed))
        return LogAnalysis(summary=summary, findings=[])
    total = sum(lf.count for lf in findings)
    top = findings[0]
    summary = (f"{len(findings)} distinct error patterns ({total:,} occurrences). Dominant: {top.count:,}x "
               f"`{top.pattern}`" + (f" - {top.interpretation}" if top.interpretation else "") + ".")
    return LogAnalysis(summary=summary, findings=findings)


def _title(root: Finding | None, services: list[str], query: str) -> str:
    if root is None:
        return query.strip().splitlines()[0][:90]
    headline = re.sub(r"^[\w-]+:\s*", "", root.title)
    prefix = f"{services[0]}: " if services and not headline.lower().startswith(services[0]) else ""
    return (prefix + headline)[:90]


def _latest_commit_summary(inv: Investigation, ev: Evidence) -> str | None:
    query = inv.query.lower()
    if "commit" not in query or not any(phrase in query for phrase in
                                        ("last commit", "latest commit", "most recent commit")):
        return None

    finding = next((item for item in ev.findings
                    if item.source.endswith(("list_commits", "get_commit")) and item.detail), None)
    if finding is None:
        return None
    try:
        data = json.loads(finding.detail)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict):
        data = data.get("commits", [data])
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None

    commit = data[0]
    metadata = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
    author = metadata.get("author") if isinstance(metadata.get("author"), dict) else {}
    message = str(metadata.get("message") or commit.get("message") or "").strip()
    sha = str(commit.get("sha") or commit.get("id") or "").strip()
    author_value = commit.get("author")
    author_name = str(author.get("name") or
                      (author_value.get("login") if isinstance(author_value, dict) else "") or "").strip()
    author_email = str(author.get("email") or "").strip()
    created = str(author.get("date") or commit.get("created_at") or "").strip()
    repository = commit.get("repository")
    repository_name = str(repository.get("full_name") or "").strip() if isinstance(repository, dict) else ""
    url = str(commit.get("html_url") or commit.get("url") or "").strip()

    details = [f'"{message}"' if message else "Commit message unavailable"]
    if sha:
        details.append(f"SHA {sha}")
    if author_name:
        details.append(f"authored by {author_name}{f' <{author_email}>' if author_email else ''}")
    if created:
        details.append(f"created {created}")
    if repository_name:
        details.append(f"repository {repository_name}")
    if url:
        details.append(f"URL {url}")

    stats_call = next((call for call in ev.calls if call.tool.endswith("get_commit_stats") and
                       isinstance(call.output, dict)), None)
    stats_data = stats_call.output if stats_call else None
    if stats_data is None:
        stats_finding = next((item for item in ev.findings
                              if item.source.endswith("get_commit_stats") and item.detail), None)
        if stats_finding:
            try:
                stats_data = json.loads(stats_finding.detail)
            except (json.JSONDecodeError, TypeError):
                stats_data = None
    if isinstance(stats_data, dict):
        files = stats_data.get("files")
        if isinstance(files, list):
            changes = []
            for changed_file in files[:12]:
                if not isinstance(changed_file, dict):
                    continue
                path = changed_file.get("filename") or changed_file.get("name")
                if not path:
                    continue
                status = str(changed_file.get("status") or "changed")
                additions = changed_file.get("additions")
                deletions = changed_file.get("deletions")
                counts = f", +{additions}/-{deletions}" if additions is not None and deletions is not None else ""
                changes.append(f"{path} ({status}{counts})")
            details.append(f"changed {len(files)} file(s)")
            if changes:
                remaining = len(files) - min(len(files), 12)
                files_text = ", ".join(changes)
                if remaining:
                    files_text += f", and {remaining} more"
                details.append(f"files: {files_text}")
        totals = stats_data.get("stats")
        if isinstance(totals, dict) and totals.get("additions") is not None and totals.get("deletions") is not None:
            details.append(f"overall +{totals['additions']}/-{totals['deletions']} lines")
    return "Latest commit: " + "; ".join(details) + "."


def heuristic_report(inv: Investigation, ev: Evidence, services: list[str], generated_by: str = "rule-based analysis") -> InvestigationReport:
    ranked = ev.ranked_findings()
    if wants_pr_review(inv.query) and not any(
        f.category in {"pr_review", "pr_blocker", "pr_incomplete"} for f in ranked
    ):
        ranked.insert(0, Finding(
            title="DO NOT MERGE - review incomplete",
            detail="No completed code review was collected for the requested PR. "
                   "Resolve the actual repository/PR number and rerun the Gitea Pull Requests skill.",
            severity="medium", category="pr_incomplete", score=0.9,
            remediation=["Complete a review of the PR diff and its exact head-SHA checks before merging."],
        ))
    causal = [f for f in ranked if f.category not in _SYMPTOM_CATEGORIES] or ranked
    root = causal[0] if causal else None
    runner_up = causal[1] if len(causal) > 1 else None
    confidence = _confidence(root, runner_up)
    severity = max((f.severity for f in ranked), key=lambda s: _SEVERITY_RANK.get(s, 0), default="info")
    if root:
        chain = [f"- {f.title}: {f.detail}" for f in ranked if f is not root]
        details = (f"{root.detail}\n\nRelated signals:\n" + "\n".join(chain)) if chain else root.detail
        rc = RootCause(summary=root.title, details=details.strip(), confidence=confidence,  # type: ignore[arg-type]
                       category=root.category)
        summary = (f"{'Most likely' if confidence != 'low' else 'Possible'} root cause for {', '.join(services) or 'the repository request'}: "
                   f"{root.title}. {len(ranked)} findings were collected by {len(ev.skills_run)} skill(s) "
                   f"({len(ev.calls)} tool calls).")
    else:
        rc = RootCause(summary="No root cause identified from the collected evidence.",
                       details="The available evidence did not establish a root cause. "
                       + "; ".join([*ev.notes, *[f"{c.tool}: {c.error}" for c in ev.failed_calls]]),
                       confidence="low", category="unknown")
        summary = (f"No root cause could be established for {', '.join(services) or 'the request'} across "
                   f"{len(ev.calls)} tool calls. "
                   + (f"{len(ev.failed_calls)} check(s) failed; coverage is incomplete. " if ev.failed_calls else "")
                   + "Missing evidence does not establish health or rule out an incident.")
    summary = _latest_commit_summary(inv, ev) or summary
    if ev.simulated:
        summary += " Evidence comes from simulated demo data sources."
    report = InvestigationReport(
        title=_title(root, services, inv.query),
        executive_summary=summary,
        severity=severity,  # type: ignore[arg-type]
        conclusive=confidence != "low",
        affected_services=services,
        root_cause=rc,
        supporting_evidence=[EvidenceItem(title=f.title, detail=f.detail, source=f.source, severity=f.severity)
                     for f in ranked],
        log_analysis=_log_analysis(ev),
        recommended_remediation=_remediation([root, *[f for f in ranked if f is not root]] if root else ranked),
        next_steps=_next_steps(ev, ranked, services),
        suggested_questions=_questions(root, services),
        generated_by=generated_by,
        data_sources=ev.data_sources(),
        tool_results=list(ev.calls),
    )
    stages = [f for f in ev.findings if f.category == "repository_stage"]
    if stages:
        risks = [f for f in ranked if f.category in {"repository_defect", "repository_risk"}]
        gaps = [*ev.notes, *[f"{c.tool}: {c.error}" for c in ev.failed_calls]]
        report.title = "Repository deep analysis"
        risk_summary = (f"I found {len(risks)} confirmed repository risk"
                f"{'s' if len(risks) != 1 else ''}." if risks
                        else "I found no confirmed repository risks.")
        check_summary = (f"{len(ev.failed_calls)} check(s) could not be completed."
                         if ev.failed_calls else "All available checks completed.")
        report.executive_summary = (
            f"I reviewed {len(stages)} parts of the repository using {len(ev.calls)} read-only checks. "
            f"{risk_summary} {check_summary} "
            "This review cannot confirm whether production is available."
        )
        report.root_cause = RootCause(
            summary=risks[0].title if risks else "No production issue was confirmed from repository data.",
            details="\n\n".join(f"## {f.title}\n\n{f.detail}" for f in stages)
                    + ("\n\n## Risks\n\n" + "\n\n".join(f.detail for f in risks) if risks else "")
                    + ("\n\n## Evidence gaps\n\n" + "\n".join(gaps) if gaps else ""),
            confidence="low", category="repository",
        )
        report.conclusive = False
        report.next_steps = [
            "Resolve failed or unavailable checks; inventories are bounded, not complete repository history.",
            "Review the referenced commit and pull request in Gitea before acting on findings.",
            "Run relevant tests and CI checks for any proposed change.",
            "Confirm the repository state again before making a separately authorized change.",
        ]
        report.suggested_questions = [
            "Which latest-commit findings are confirmed and which checks are incomplete?",
            "Which tests cover the changed code?",
            "What additional Gitea evidence should be checked?",
        ]
    warnings = [f for f in ranked if f.category in {"pr_blocker", "pr_incomplete"}]
    if warnings:
        root = warnings[0]
        report.title = root.title
        blockers = [f for f in warnings if f.category == "pr_blocker"]
        gaps = [f for f in warnings if f.category == "pr_incomplete"]
        scope = "\n\n".join(f.detail for f in ranked if f.category == "pr_scope")
        report.executive_summary = (
            f"**{root.title}**\n\n"
            + ("\n\n".join(f.detail for f in blockers[:2]) if blockers else
               "No code defect has been confirmed. The PR is not cleared to merge because validation is incomplete.")
            + ("\n\n**Additional verified blockers:** " + "; ".join(f.title for f in blockers[2:])
               if len(blockers) > 2 else "")
            + ("\n\n**Review limitations (not confirmed code defects):**\n\n"
               + "\n\n".join(f.detail for f in gaps) if gaps else "")
        )
        report.root_cause = RootCause(
            summary=root.title,
            details=("## Why this PR is not cleared to merge\n\n"
                     + (scope + "\n\n" if scope else "")
                     + ("\n\n".join(f.detail for f in blockers) if blockers else
                        "No faulty file was confirmed by the available evidence.")
                     + ("\n\n## Review limitations - not confirmed defects\n\n"
                        + "\n\n".join(f.detail for f in gaps) if gaps else "")),
            category=root.category, confidence="high" if root.category == "pr_blocker" else "low",
        )
        report.supporting_evidence = [
            EvidenceItem(title=f.title, detail=f.detail, source=f.source, severity=f.severity)
            for f in [*warnings, *[f for f in ranked if f.category == "pr_scope"]]
        ]
        actions = list(dict.fromkeys(action for f in warnings for action in f.remediation))
        report.recommended_remediation = [
            RemediationAction(priority=i, action=action, rationale="Resolve the documented PR finding.",
                              risk="low", timeframe="immediate")
            for i, action in enumerate(actions, start=1)
        ]
        report.next_steps = [
            "Fix each verified defect and add the specified regression tests.",
            "Resolve the documented review limitations and run CI for the exact PR head.",
            "Rerun the PR review after pushing the fixes; do not merge until blockers are resolved.",
        ] if blockers else [
            "Resolve the documented evidence gaps; no faulty file has been confirmed.",
            "Rerun the Gitea Pull Requests review with the complete diff and head-SHA checks.",
        ]
        report.suggested_questions = [
            "Which file and line are faulty, and what fails?",
            "How should I fix each defect and test it?",
            "Which findings are confirmed and which are review limitations?",
        ]
        report.conclusive = not any(f.category == "pr_incomplete" for f in warnings)
    defects = [f for f in ranked if f.category == "repository_defect" or
               (f.category == "pr_blocker" and "**Faulty added code:**" in f.detail)]
    if warnings:
        verdict = "DO NOT MERGE. Resolve the documented blockers and review limitations first."
    elif stages:
        verdict = "Repository review completed; production availability and merge safety are not established."
    elif wants_pr_review(inv.query):
        verdict = "No defects found in the inspected diff. This is advisory, not approval to merge."
    else:
        verdict = ("An evidence-backed conclusion was reached." if report.conclusive else
                   "The evidence is insufficient for a conclusive diagnosis.")
    gap_count = len(ev.notes) + len(ev.failed_calls) + sum(f.category == "pr_incomplete" for f in ranked)
    coverage = f"{len(stages)} repository stages; " if stages else ""
    report.conclusion_summary = (
        f"**Conclusion:** {verdict}\n\n"
        f"**Key finding:** {report.root_cause.summary}\n\n"
        f"**Analysis coverage:** {coverage}{len(ev.calls)} tool calls "
        f"({len(ev.failed_calls)} failed); {len(defects)} source-grounded code defect(s). "
        "Source-grounded findings are advisory, not executed test results.\n\n"
        + ("**Code findings:**\n" + "\n".join(f"- {f.title}" for f in defects) + "\n\n" if defects else "")
        + (f"**Evidence limitations:** {gap_count} recorded gap(s) or failed check(s). "
           "Review the evidence limitations and tool errors above; missing evidence is not proof of health.\n\n"
           if gap_count else "")
        + "**Next action:** " + (report.next_steps[0] if report.next_steps else "Review the supporting evidence.")
        + ("\n\nNo repository tests, deployment changes, or production recovery checks were executed."
           if stages or wants_pr_review(inv.query) else "")
    )
    return report


# --------------------------------------------------------------------------- #
# LLM report
# --------------------------------------------------------------------------- #
def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sev(value: Any, default: str = "medium") -> str:
    v = str(value or "").lower()
    return v if v in _SEVERITIES else default


def merge_report(raw: dict[str, Any], base: InvestigationReport, generated_by: str) -> InvestigationReport:
    """Overlay model output on the heuristic report, field by field, dropping invalid parts."""
    data = base.model_dump()
    if isinstance(raw.get("title"), str) and raw["title"].strip():
        data["title"] = raw["title"].strip()[:200]
    if isinstance(raw.get("executive_summary"), str) and raw["executive_summary"].strip():
        data["executive_summary"] = raw["executive_summary"].strip()
    data["severity"] = _sev(raw.get("severity"), base.severity)
    if isinstance(raw.get("conclusive"), bool):
        data["conclusive"] = raw["conclusive"]
    rc = raw.get("root_cause")
    if isinstance(rc, dict) and rc.get("summary"):
        conf = str(rc.get("confidence", "")).lower()
        data["root_cause"] = {"summary": str(rc["summary"]), "details": str(rc.get("details") or ""),
                              "confidence": conf if conf in ("high", "medium", "low") else base.root_cause.confidence,
                              "category": str(rc.get("category") or base.root_cause.category)[:60]}
    evidence = []
    for e in _as_list(raw.get("supporting_evidence")):
        if isinstance(e, dict) and e.get("title"):
            evidence.append({"title": str(e["title"]), "detail": str(e.get("detail") or ""),
                             "source": str(e.get("source") or ""), "severity": _sev(e.get("severity"), "info")})
    if evidence:
        data["supporting_evidence"] = evidence
    la = raw.get("log_analysis")
    if isinstance(la, dict):
        if isinstance(la.get("summary"), str) and la["summary"].strip():
            data["log_analysis"]["summary"] = la["summary"].strip()
        llm_findings = []
        for lf in _as_list(la.get("findings")):
            if isinstance(lf, dict) and lf.get("pattern"):
                try:
                    llm_findings.append(LogFinding(**{**lf, "count": int(lf.get("count") or 0),
                                                      "pattern": str(lf["pattern"])}).model_dump())
                except (ValidationError, ValueError, TypeError):
                    continue
        # keep tool-derived log findings (exact counts) unless we had none
        if llm_findings and not data["log_analysis"]["findings"]:
            data["log_analysis"]["findings"] = llm_findings
    actions = []
    for a in _as_list(raw.get("recommended_remediation")):
        if isinstance(a, dict) and a.get("action"):
            try:
                actions.append(RemediationAction(
                    priority=int(a.get("priority") or len(actions) + 1), action=str(a["action"]),
                    rationale=str(a.get("rationale") or ""), command=(str(a["command"]) if a.get("command") else None),
                    risk=a.get("risk") if a.get("risk") in ("low", "medium", "high") else "low",
                    timeframe=a.get("timeframe") if a.get("timeframe") in ("immediate", "short_term", "long_term") else "short_term",
                ).model_dump())
            except (ValidationError, ValueError, TypeError):
                continue
    if actions:
        actions.sort(key=lambda a: a["priority"])
        for i, a in enumerate(actions, start=1):
            a["priority"] = i
        data["recommended_remediation"] = actions
    for key in ("next_steps", "suggested_questions"):
        items = [str(s) for s in _as_list(raw.get(key)) if isinstance(s, str) and s.strip()]
        if items:
            data[key] = items
    data["generated_by"] = generated_by
    if base.root_cause.category in {"pr_blocker", "pr_incomplete"}:
        for key in ("title", "executive_summary", "severity", "conclusive", "root_cause"):
            data[key] = base.model_dump()[key]
        data["supporting_evidence"] = [e.model_dump() for e in base.supporting_evidence]
        data["recommended_remediation"] = [a.model_dump() for a in base.recommended_remediation]
        data["next_steps"] = list(base.next_steps)
        data["suggested_questions"] = list(base.suggested_questions)
    return InvestigationReport.model_validate(data)


async def llm_report(llm: LLMProvider, inv: Investigation, ev: Evidence, base: InvestigationReport) -> InvestigationReport:
    if any(f.category.startswith("pr_") or f.category == "repository_stage" for f in ev.findings):
        # PR findings are already model-reviewed and source-validated; synthesis can omit evidence.
        return base.model_copy(deep=True)
    hypothesis = (f"{base.root_cause.summary} (confidence {base.root_cause.confidence}, category {base.root_cause.category})"
                  if base.supporting_evidence else "none - no findings")
    user = prompts.REPORT_USER.format(query=inv.query, mode=inv.mode.value,
                                      skills=", ".join(ev.skills_run) or "none",
                                      evidence=render_context(ev), hypothesis=hypothesis)
    raw = await llm.complete_json([Message("system", prompts.REPORT_SYSTEM), Message("user", user)],
                                  temperature=0.1)
    report = merge_report(raw, base, generated_by=llm.label)
    if report.root_cause.category not in {"pr_blocker", "pr_incomplete"}:
        report.executive_summary = _latest_commit_summary(inv, ev) or report.executive_summary
    return report


async def direct_report(llm: LLMProvider, inv: Investigation) -> InvestigationReport:
    """No-skill mode: answer from the model's knowledge only."""
    base = InvestigationReport(
        title=inv.query.strip().splitlines()[0][:90], executive_summary="", conclusive=False, severity="info",
        root_cause=RootCause(summary="Not determined - no diagnostic tools were run.", confidence="low"),
        next_steps=["Re-run in Auto mode so the bot can collect live evidence"], generated_by=llm.label,
        suggested_questions=["Which data should I collect first?", "What are the most likely causes?",
                             "How do I mitigate this quickly?"])
    if wants_pr_review(inv.query):
        base.title = "DO NOT MERGE - review incomplete"
        base.executive_summary = "DO NOT MERGE - review incomplete. No diagnostic tools were selected, so the PR diff, reviews, and head-SHA checks were not inspected."
        base.severity = "medium"
        base.root_cause = RootCause(summary=base.title, details=base.executive_summary,
                                    category="pr_incomplete", confidence="low")
        return base
    if not llm.available:
        base.executive_summary = ("No AI model is configured (set LLM_PROVIDER=bedrock and configure AWS credentials) and no skills were selected, so nothing "
                                  "could be analysed. Choose Auto mode or specific skills to run the diagnostic tools.")
        base.generated_by = "offline"
        return base
    raw = await llm.complete_json([Message("system", prompts.DIRECT_SYSTEM), Message("user", inv.query[:12000])],
                                  temperature=0.2)
    report = merge_report(raw, base, generated_by=llm.label)
    report.data_sources = ["AI model knowledge only (no tools)"]
    return report


__all__ = ["heuristic_report", "llm_report", "direct_report", "merge_report", "LLMError"]
