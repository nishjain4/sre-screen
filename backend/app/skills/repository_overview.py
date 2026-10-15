"""Read-only repository playbook. All references come from remote responses."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlsplit

from app.core.executor import ToolOutcome
from app.core.gitea_scope import repository_scope
from app.core.tools import ToolError
from app.skills.base import SkillContext, SkillResult
from app.skills.gitea_pr_review import review_commit
from app.skills.source_context import read_source_context


async def investigate_repository(ctx: SkillContext) -> SkillResult:
    scope = repository_scope(ctx.investigation.query, ctx.gitea_url)
    if re.search(r"https?://", ctx.investigation.query) and not scope:
        raise ToolError("The supplied link does not identify a repository on the configured Gitea server; "
                        "the default repository was not queried.")
    repository_url = (
        f"{(ctx.gitea_url or '').rstrip('/')}/"
        f"{quote(scope['owner'], safe='')}/{quote(scope['repo'], safe='')}"
        if scope else ""
    )
    result = SkillResult()
    evidence: dict[str, ToolOutcome] = {}

    async def stage(number: int, title: str, calls: list[tuple[str, dict[str, Any]]]) -> None:
        available = []
        gaps = []
        for suffix, args in calls:
            tool = f"gitea__{suffix}"
            if ctx.has_tool(tool):
                available.append((tool, args, f"Repository stage {number}: {title}"))
            else:
                gaps.append(f"{tool}: unavailable; not assessed")
        async with ctx.phase(f"Repository stage {number}: {title}",
                             "Collect read-only evidence; retain failures and unavailable sources") as stage_ctx:
            outcomes = await stage_ctx.call_many(available)
        details = []
        for outcome in outcomes:
            suffix = outcome.call.tool.removeprefix("gitea__")
            evidence[suffix] = outcome
            if suffix == "list_commits" and outcome.ok:
                commits_data = outcome.data
                if isinstance(commits_data, dict):
                    commits_data = commits_data.get("commits")
                summary = (f"{len(commits_data)} commit(s) returned"
                           if isinstance(commits_data, list) else "Unexpected response shape")
            else:
                summary = outcome.summary if outcome.ok else f"FAILED: {outcome.call.error}"
            details.append(f"**{outcome.call.tool}**: {summary}")
        result.add(title=f"{number}. {title}", detail="\n\n".join([*details, *gaps]),
                   source="mcp:gitea", severity="info", category="repository_stage", score=0.1)
        result.notes.extend(gaps)

    def data(suffix: str) -> Any:
        outcome = evidence.get(suffix)
        return outcome.data if outcome and outcome.ok else None

    await stage(1, "Repository identity and ownership", [
        ("get_repository", {}), ("get_repository_languages", {}), ("get_repository_topics", {}),
        ("get_contributors", {"limit": 50}), ("get_contributor_stats", {}),
    ])
    metadata = data("get_repository")
    metadata = metadata if isinstance(metadata, dict) else {}
    name = metadata.get("full_name") or metadata.get("name") or "Identity not verified"
    identity = f"[{name}]({repository_url})" if repository_url else str(name)
    result.findings[-1].detail += (
        f"\n\n**Repository:** {identity}; **default branch:** "
        f"{metadata.get('default_branch') or 'unknown'}."
    )
    result.findings[-1].detail += f"\n\n**Description:** {metadata.get('description') or 'Not returned'}."
    if isinstance(metadata.get("private"), bool):
        result.findings[-1].detail += f"\n\n**Visibility:** {'private' if metadata['private'] else 'public'}."
    await stage(2, "Branches and default-branch head", [("list_branches", {"limit": 50})])
    branch = metadata.get("default_branch")
    ref = {"ref": branch} if isinstance(branch, str) and branch else {}
    await stage(3, "Recent commits", [("list_commits", {**ref, "limit": 10})])
    commits = data("list_commits")
    if isinstance(commits, dict):
        commits = commits.get("commits")
    if isinstance(commits, list):
        for commit in commits:
            if not isinstance(commit, dict):
                continue
            info = commit.get("commit")
            info = info if isinstance(info, dict) else {}
            author = info.get("author")
            author = author if isinstance(author, dict) else {}
            commit_sha = commit.get("sha")
            commit_label = str(commit_sha or "SHA not returned")
            commit_link = (
                f"[`{commit_label[:12]}`]({repository_url}/commit/{quote(commit_label, safe='')})"
                if repository_url and isinstance(commit_sha, str)
                and re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", commit_sha)
                else f"`{commit_label}`"
            )
            message = str(info.get("message") or commit.get("message") or "Message not returned")
            subject = re.sub(r"https?://\S+", "[external repository link omitted]", message.splitlines()[0])
            result.findings[-1].detail += (
                f"\n\n- {commit_link}: "
                f"{subject}"
                f" - {author.get('name') or 'Author unknown'}, {author.get('date') or 'Date unknown'}."
            )
    latest = commits[0] if isinstance(commits, list) and commits and isinstance(commits[0], dict) else {}
    sha = latest.get("sha")
    if not isinstance(sha, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", sha):
        sha = None
        result.notes.append("Latest commit SHA missing or invalid; dependent checks and revert guidance were not guessed.")
    await stage(4, "Pull requests and last observed merge", [
        ("list_pull_requests", {"state": "all", "limit": 50, "page": 1}),
    ])
    prs = data("list_pull_requests")
    if isinstance(prs, list):
        prs = list(prs)
        complete = len(prs) < 50
        for page in range(2, 11):
            if complete:
                break
            outcome = await ctx.call("gitea__list_pull_requests",
                                     {"state": "all", "limit": 50, "page": page},
                                     "Continue PR inventory to determine the latest merge")
            result.findings[-1].detail += f"\n\n**PR page {page}:** {outcome.summary}"
            if not outcome.ok or not isinstance(outcome.data, list):
                result.notes.append(f"PR inventory incomplete on page {page}: "
                                    f"{outcome.call.error or 'unexpected response shape'}")
                break
            prs.extend(outcome.data)
            complete = len(outcome.data) < 50
        merged = [pr for pr in prs if isinstance(pr, dict) and pr.get("merged_at")]
        last = max(merged, key=lambda pr: str(pr["merged_at"])) if merged else None
        result.findings[-1].detail += (
            f"\n\n**{'Last merged PR' if complete else 'Latest merge in inspected PRs'}:** "
            f"#{last.get('number')} at {last['merged_at']}"
            f" - {last.get('html_url') or 'No PR URL returned'}."
            if last else "\n\nNo merged PR was returned in the inspected page."
        )
        result.findings[-1].detail += (
            "\n\nPR inventory incomplete (up to 500 inspected): the repository-wide latest merge is unverified."
            if not complete else "\n\nScope: all PR pages returned by Gitea during this run (not an atomic snapshot)."
        )
    else:
        result.notes.append("PR inventory was unavailable or malformed; the last merged PR is unverified.")
    await stage(5, "Issues and planning", [
        ("list_issues", {"state": "all", "limit": 50}), ("list_labels", {"limit": 50}),
        ("list_milestones", {"state": "all", "limit": 50}),
    ])
    await stage(6, "CI, releases, and workflow inventory", [
        ("list_workflows", {}), ("list_workflow_runs", {"limit": 50}),
        ("list_tags", {"limit": 50}), ("list_releases", {"limit": 50}),
    ])
    await stage(7, "Latest-commit code and exact-SHA checks", [
        ("get_commit", {"ref": sha}), ("get_commit_diff", {"ref": sha}),
        ("get_commit_status", {"ref": sha}), ("list_commit_statuses", {"ref": sha}),
    ] if sha else [])
    if sha:
        status = data("get_commit_status")
        if isinstance(status, dict) and status.get("state") in {"failure", "error"}:
            result.add(evidence["get_commit_status"], title="Latest commit has failing CI",
                       detail=f"Exact SHA {sha}: CI state {status['state']}. "
                       "Failed CI is not by itself proof of a code bug or a production incident.",
                       severity="high", category="repository_risk", score=0.8)
        elif not isinstance(status, dict) or status.get("state") != "success" or not status.get("total_count"):
            result.notes.append("Passing CI checks for the exact latest SHA were not verified.")
    await stage(8, "Source structure and related-test discovery", [
        ("list_git_tree", {"ref": sha, "recursive": True}),
    ] if sha else [])
    source_context = ""
    async with ctx.phase("Repository stage 9: Source, tests, and build configuration",
                         "Read changed source and related tests at the exact reviewed SHA") as source_ctx:
        if sha:
            diff = data("get_commit_diff")
            diff = diff.get("content") if isinstance(diff, dict) else diff
            if isinstance(diff, str):
                source_context = await read_source_context(
                    source_ctx, result, diff, sha, data("list_git_tree"))
    result.add(title="9. Source, tests, and build configuration",
               detail=(f"Read exact-SHA source context for `{sha}`. "
                       "Collected available changed implementations, related tests, and build manifests. "
                       "Complete read results are retained in MCP and Diagnostic Tool Results."
                       if source_context else "Source/test context unavailable; contextual coverage is incomplete."),
               source="mcp:gitea", severity="info", category="repository_stage", score=0.1)
    if sha:
        diff_outcome = evidence.get("get_commit_diff")
        if diff_outcome:
            await review_commit(ctx, result, diff_outcome, sha, source_context=source_context)
        else:
            result.notes.append("Commit diff unavailable: code defects could not be assessed.")
    await stage(10, "Recovery review and evidence limitations", [])
    recovery = result.findings[-1]
    if sha and repository_url:
        recovery.detail = (
            f"[Review latest commit in {name}]"
            f"({repository_url}/commit/{quote(sha, safe='')}).\n\n"
        )
    else:
        recovery.detail = "No verified latest-commit link was returned; no revert URL was invented.\n\n"
    recovery.detail += (
        "No source mutation was executed. A commit link opens review. Findings are advisory; "
        "validate proposed changes with tests and CI before a separately authorized change. "
        "A repository-only investigation does not establish production state.\n\n"
        "Inventories are bounded (10 commits; up to 500 PRs; up to 50 records per other inventory), not full history. "
        "Application runtime logs were not queried by this repository playbook."
    )
    if result.notes:
        recovery.detail += "\n\n**Unverified / unavailable:**\n" + "\n".join(f"- {note}" for note in result.notes)
    return result
