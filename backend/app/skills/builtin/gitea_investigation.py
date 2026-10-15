"""Focused skill groups for remote Gitea operations."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.tools import Tool, ToolRegistry
from app.llm.base import LLMError, Message
from app.skills.base import Skill, SkillContext, SkillResult
from app.skills.gitea_pr_review import pr_target, review_pr, wants_pr_review, warning
from app.skills.repository_overview import investigate_repository
from app.skills.repository_query import wants_repository_overview

logger = logging.getLogger(__name__)

_SYSTEM = """You are selecting operations from one focused remote Gitea tool group.
Use only the supplied tools and only for the user's requested operation. Never use local Git or
workspace data as remote evidence. Do not invent arguments or results. Mutating tools may only be
selected when the user directly instructs that mutation and every required argument is present.
Reply with JSON: {\"calls\": [{\"tool\": \"exact tool name\", \"args\": {}, \"reason\": \"short\"}]}.
Select every relevant operation in this group with supported arguments; omit unrelated operations."""

_MUTATING_TOOLS = {
    "add_issue_comment", "approve_pr", "comment_review", "create_branch", "create_file", "create_issue",
    "create_label", "create_milestone", "create_pull_request", "create_release", "create_review",
    "create_webhook", "delete_branch", "delete_file", "delete_release", "delete_webhook", "merge_pull_request",
    "request_changes", "submit_review", "trigger_workflow", "update_file", "update_issue",
}
_DIRECT_ACTION = re.compile(
    r"^\s*(?:(?:please|could you|can you|I want you to)\s+)?"
    r"(?:create|update|delete|remove|merge|approve|request changes|submit|comment|add|trigger|dispatch|close|reopen)\b",
    re.I,
)
_NUMBER = re.compile(r"\b(?:issue|pull request|pr)\s*#?(\d+)\b", re.I)
_FILE_PATH = re.compile(r"(?<![\w.-])(?:[\w.-]+/)*[\w.-]+\.[a-z0-9]{1,10}(?![\w.-])", re.I)


def _gitea_tools(registry: ToolRegistry) -> list[Tool]:
    return [tool for tool in registry.all() if tool.source == "mcp:gitea"]


class GiteaToolGroup(Skill):
    """A child skill constrained to one disjoint set of Gitea operations."""

    id = "gitea_handler"
    name = "Gitea Handler"
    description = "Route a remote Gitea request to its matching operation group."
    category = "Integrations"
    icon = "plug"
    keywords: list[str] = []
    tool_suffixes: tuple[str, ...] = ()
    tools: list[str] = []

    def available(self, registry: ToolRegistry) -> bool:
        available = {tool.name for tool in _gitea_tools(registry)}
        self.tools = [f"gitea__{suffix}" for suffix in self.tool_suffixes
                      if f"gitea__{suffix}" in available]
        return bool(self.tools)

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        return []

    async def _choose_calls(self, ctx: SkillContext, available: list[Tool]) -> list[tuple[str, dict[str, Any], str]]:
        query = ctx.investigation.query
        if ctx.llm.available:
            catalog = [{"name": tool.name, "description": tool.description[:300],
                        "input_schema": tool.input_schema} for tool in available]
            prompt = (f"Tool group: {self.name} - {self.description}\n"
                      f"Request: {query[:3000]}\n"
                      f"Available operations:\n{json.dumps(catalog)[:18000]}")
            try:
                response = await ctx.llm.complete_json(
                    [Message("system", _SYSTEM), Message("user", prompt)],
                    temperature=0,
                )
                names = {tool.name: tool for tool in available}
                calls = []
                for call in response.get("calls", []):
                    if not isinstance(call, dict) or call.get("tool") not in names:
                        continue
                    name = str(call["tool"])
                    args = call.get("args")
                    if not isinstance(args, dict):
                        continue
                    suffix = name.removeprefix("gitea__")
                    if suffix in {
                        "get_pull_request", "get_pull_request_diff", "get_pull_request_commits",
                        "get_pull_request_files", "list_reviews", "approve_pr", "request_changes",
                        "merge_pull_request", "create_review", "submit_review", "comment_review",
                    }:
                        target = pr_target(query)
                        if not target or args.get("index") != target["index"]:
                            continue
                        args = {**args, **target}
                    if suffix in _MUTATING_TOOLS:
                        if not _DIRECT_ACTION.search(query):
                            continue
                        required = names[name].input_schema.get("required", [])
                        if any(arg not in args or args[arg] in (None, "") for arg in required):
                            continue
                    calls.append((name, args, str(call.get("reason") or f"Handle {self.name.lower()} request")))
                if calls:
                    return calls
            except LLMError as exc:
                logger.warning("Gitea tool selection failed for %s; using keyword fallback: %s", self.id, exc)

        target = pr_target(query)
        return [(name, {**args, **{key: value for key, value in target.items() if key != "index"}}, reason)
                for name, args, reason in self._fallback_calls(query.lower(), {tool.name for tool in available})]

    async def execute(self, ctx: SkillContext) -> SkillResult:
        result = SkillResult()
        available = [tool for tool in _gitea_tools(ctx.registry) if tool.name in self.tools]
        calls = await self._choose_calls(ctx, available)
        if not calls:
            result.notes.append(f"No supported {self.name.lower()} operation matched this request")
            return result

        for outcome in await ctx.call_many(calls):
            self._record_outcome(result, outcome)
            await self._after_outcome(ctx, result, outcome)
        return result

    async def _after_outcome(self, ctx: SkillContext, result: SkillResult, outcome) -> None:
        pass

    @staticmethod
    def _record_outcome(result: SkillResult, outcome) -> None:
        if not outcome.ok:
            result.notes.append(f"{outcome.call.tool} failed: {outcome.call.error or 'unknown error'}")
            return
        result.add(outcome, title=f"{outcome.call.tool}: {outcome.summary[:160]}",
                   detail=json.dumps(outcome.data, default=str)[:4000], severity="info",
                   category="repository", score=0.4)


class GiteaRepositoryDiscovery(GiteaToolGroup):
    id = "gitea_repository_discovery"
    name = "Gitea Repository Discovery"
    description = "Remote repository identity, metadata, contributors, languages, and topics; not local workspace discovery."
    keywords = ["gitea", "repository", "repo", "metadata", "owner", "visibility", "default branch",
                "language", "languages", "topic", "topics", "contributor", "contributors"]
    tool_suffixes = ("get_repository", "get_repository_languages", "get_repository_topics",
                     "get_contributors", "get_contributor_stats")

    async def execute(self, ctx: SkillContext) -> SkillResult:
        if wants_repository_overview(ctx.investigation.query):
            return await investigate_repository(ctx)
        return await super().execute(ctx)

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        calls = []
        if "gitea__get_repository" in available:
            calls.append(("gitea__get_repository", {}, "Read remote repository metadata"))
        if "language" in query and "gitea__get_repository_languages" in available:
            calls.append(("gitea__get_repository_languages", {}, "Read repository languages"))
        if "topic" in query and "gitea__get_repository_topics" in available:
            calls.append(("gitea__get_repository_topics", {}, "Read repository topics"))
        if "contributor" in query and "gitea__get_contributors" in available:
            calls.append(("gitea__get_contributors", {"limit": 10}, "List repository contributors"))
        return calls


class GiteaActionsHandler(GiteaToolGroup):
    id = "gitea_actions_handler"
    name = "Gitea Actions"
    description = "Remote workflow and run inspection; dispatch only when explicitly requested with required inputs."
    keywords = ["workflow", "workflows", "github actions", "gitea actions", "action run", "workflow run",
                "dispatch workflow"]
    tool_suffixes = ("list_workflows", "list_workflow_runs", "trigger_workflow")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        if "gitea__list_workflow_runs" in available and any(word in query for word in ("run", "history", "failed")):
            return [("gitea__list_workflow_runs", {"limit": 10}, "Inspect workflow runs")]
        if "gitea__list_workflows" in available:
            return [("gitea__list_workflows", {}, "List repository workflows")]
        return []


class GiteaBranches(GiteaToolGroup):
    id = "gitea_branches"
    name = "Gitea Branches"
    description = "Remote branch inventory and branch operations; never infer branches from the local checkout."
    keywords = ["branch", "branches", "branch head", "branch inventory"]
    tool_suffixes = ("get_branch", "list_branches", "create_branch", "delete_branch")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        if "gitea__list_branches" in available:
            return [("gitea__list_branches", {"limit": 50}, "List remote branches")]
        return []


class GiteaCodeReviews(GiteaToolGroup):
    id = "gitea_code_reviews"
    name = "Gitea Code Reviews"
    description = "Remote PR review records and review actions; not pull-request inventory or local review data."
    keywords = ["code review", "reviews", "review approval", "approve", "request changes", "inline comment"]
    tool_suffixes = ("approve_pr", "comment_review", "create_review", "list_reviews", "request_changes",
                     "submit_review")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        target = pr_target(query)
        if target and "gitea__list_reviews" in available:
            return [("gitea__list_reviews", target, "List reviews for the requested PR")]
        return []


class GiteaCommitsStatus(GiteaToolGroup):
    id = "gitea_commits_status"
    name = "Gitea Commits and Status"
    description = "Remote commit history, commit details, and CI status; local Git history is not remote evidence."
    keywords = ["commit", "commits", "last commit", "latest commit", "commit details", "commit history",
                "commit status", "status checks"]
    tool_suffixes = ("get_commit", "get_commit_diff", "get_commit_stats", "get_commit_status", "list_commit_statuses", "list_commits")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        if "gitea__list_commits" not in available:
            return []
        latest = any(phrase in query for phrase in ("last commit", "latest commit", "most recent commit"))
        limit = 1 if latest else 10
        return [("gitea__list_commits", {"limit": limit}, "Read the latest remote commit" if latest
                 else "Inspect remote commit history")]

    async def execute(self, ctx: SkillContext) -> SkillResult:
        target = pr_target(ctx.investigation.query)
        if target:
            result = SkillResult()
            if not ctx.has_tool("gitea__get_pull_request"):
                result.notes.append("Cannot resolve PR head: get_pull_request is unavailable; no commit ref was guessed.")
                return result
            pr = await ctx.call("gitea__get_pull_request", target, "Resolve the PR head SHA before checking commit status")
            self._record_outcome(result, pr)
            if not pr.ok or not isinstance(pr.data, dict):
                return result
            head = pr.data.get("head")
            sha = head.get("sha") if isinstance(head, dict) else None
            if not isinstance(sha, str) or not sha.strip():
                result.notes.append("PR metadata has no head SHA; no commit ref was guessed.")
                return result
            scope = {key: value for key, value in target.items() if key != "index"}
            calls = [
                (f"gitea__{suffix}", {**scope, "ref": sha}, "Read CI status for the resolved PR head")
                for suffix in ("get_commit_status", "list_commit_statuses")
                if ctx.has_tool(f"gitea__{suffix}")
            ]
            for outcome in await ctx.call_many(calls):
                self._record_outcome(result, outcome)
            return result
        query = ctx.investigation.query.lower()
        latest = any(phrase in query for phrase in ("last commit", "latest commit", "most recent commit"))
        available = {tool.name for tool in _gitea_tools(ctx.registry) if tool.name in self.tools}
        if not latest or "gitea__list_commits" not in available:
            return await super().execute(ctx)

        result = SkillResult()
        commits = await ctx.call("gitea__list_commits", {"limit": 1}, "Read the latest remote commit")
        self._record_outcome(result, commits)
        if not commits.ok or "gitea__get_commit_stats" not in available:
            return result

        records = commits.data.get("commits", []) if isinstance(commits.data, dict) else commits.data
        if isinstance(records, dict):
            records = [records]
        sha = records[0].get("sha") if isinstance(records, list) and records and isinstance(records[0], dict) else None
        if not sha:
            return result

        stats = await ctx.call("gitea__get_commit_stats", {"ref": str(sha)},
                               f"Read changed files for commit {sha}")
        self._record_outcome(result, stats)
        return result


class GiteaFilesAndTrees(GiteaToolGroup):
    id = "gitea_files_trees"
    name = "Gitea Files and Trees"
    description = "Remote repository trees and file contents; local workspace files are not Gitea evidence."
    keywords = ["file", "files", "source", "readme", "tree", "directory", "folder", "contents"]
    tool_suffixes = ("get_file", "get_file_content", "get_raw_file", "list_git_tree", "create_file", "update_file",
                     "delete_file")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        match = _FILE_PATH.search(query)
        if match and "gitea__get_file" in available:
            return [("gitea__get_file", {"path": match.group(0)}, "Read the requested remote file")]
        if "gitea__list_git_tree" in available:
            return [("gitea__list_git_tree", {"recursive": False}, "List the remote repository tree")]
        return []


class GiteaIssuesAndComments(GiteaToolGroup):
    id = "gitea_issues_comments"
    name = "Gitea Issues and Comments"
    description = "Remote issue records and discussion; pull-request records are handled by the pull-request skill."
    keywords = ["issue", "issues", "bug", "issue comment", "issue comments", "discussion"]
    tool_suffixes = ("add_issue_comment", "create_issue", "get_issue", "list_issue_comments", "list_issues",
                     "update_issue")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        match = _NUMBER.search(query)
        if match and "gitea__get_issue" in available:
            index = int(match.group(1))
            if "comment" in query and "gitea__list_issue_comments" in available:
                return [("gitea__list_issue_comments", {"index": index}, "List issue comments")]
            return [("gitea__get_issue", {"index": index}, "Read the requested issue")]
        if "gitea__list_issues" in available:
            return [("gitea__list_issues", {"state": "all", "limit": 10}, "List repository issues")]
        return []


class GiteaLabelsAndMilestones(GiteaToolGroup):
    id = "gitea_labels_milestones"
    name = "Gitea Labels and Milestones"
    description = "Remote issue classification and planning metadata; not issue or pull-request editing."
    keywords = ["label", "labels", "milestone", "milestones"]
    tool_suffixes = ("create_label", "create_milestone", "list_labels", "list_milestones")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        if "milestone" in query and "gitea__list_milestones" in available:
            return [("gitea__list_milestones", {"state": "all", "limit": 50}, "List repository milestones")]
        if "gitea__list_labels" in available:
            return [("gitea__list_labels", {"limit": 50}, "List repository labels")]
        return []


class GiteaPullRequests(GiteaToolGroup):
    id = "gitea_pull_requests"
    name = "Gitea Pull Requests"
    description = "Remote PR inventory, code-bug review, CI checks, and explicit DO NOT MERGE warnings."
    keywords = ["pull request", "pull requests", "pr", "merge request", "pull-request diff", "review pr"]
    tool_suffixes = ("create_pull_request", "get_pull_request", "get_pull_request_diff",
                     "get_pull_request_commits", "get_pull_request_files",
                     "list_pull_requests", "merge_pull_request")

    async def _choose_calls(self, ctx: SkillContext, available: list[Tool]) -> list[tuple[str, dict[str, Any], str]]:
        if _DIRECT_ACTION.search(ctx.investigation.query):
            return await super()._choose_calls(ctx, available)
        target = pr_target(ctx.investigation.query)
        return [(name, {**args, **{key: value for key, value in target.items()
                                  if key != "index" or name != "gitea__list_pull_requests"}}, reason)
                for name, args, reason in
                self._fallback_calls(ctx.investigation.query.lower(), {tool.name for tool in available})]

    async def _after_outcome(self, ctx: SkillContext, result: SkillResult, outcome) -> None:
        if outcome.call.tool in {"gitea__get_pull_request", "gitea__create_pull_request"}:
            await review_pr(ctx, result, outcome)
        elif outcome.call.tool == "gitea__list_pull_requests" and wants_pr_review(ctx.investigation.query):
            if not outcome.ok or not isinstance(outcome.data, list) or not outcome.data:
                warning(result, "No PR could be resolved from inventory. Provide an accessible PR URL or actual number.",
                        outcome=outcome)
                return
            if len(outcome.data) != 1:
                warning(result, "Multiple PRs exist. Provide the PR URL or number to review; no PR number was guessed.",
                        outcome=outcome)
                return
            item = outcome.data[0]
            if not isinstance(item, dict) or not isinstance(item.get("number"), int):
                warning(result, "PR inventory did not include a valid PR number.", outcome=outcome)
                return
            scope = {key: value for key, value in outcome.call.args.items() if key in {"owner", "repo"}}
            pr = await ctx.call("gitea__get_pull_request", {**scope, "index": item["number"]},
                                "Read the PR number returned by Gitea")
            self._record_outcome(result, pr)
            await review_pr(ctx, result, pr)

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        target = pr_target(query)
        if target and "gitea__get_pull_request" in available:
            return [("gitea__get_pull_request", target, "Read the requested pull request")]
        if "gitea__list_pull_requests" in available:
            return [("gitea__list_pull_requests", {"state": "all", "limit": 10}, "List pull requests")]
        return []


class GiteaSearch(GiteaToolGroup):
    id = "gitea_search"
    name = "Gitea Search"
    description = "Remote repository and commit search; search results do not imply local Git or workspace evidence."
    keywords = ["search", "find commit", "find commits", "search commits", "search repository"]
    tool_suffixes = ("search_commits", "search_repository")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        if any(word in query for word in ("commit", "author", "path")) and "gitea__search_commits" in available:
            return [("gitea__search_commits", {"limit": 10}, "Search remote commits")]
        if "gitea__search_repository" in available:
            return [("gitea__search_repository", {"query": query, "limit": 10}, "Search Gitea repositories")]
        return []


class GiteaTagsAndReleases(GiteaToolGroup):
    id = "gitea_tags_releases"
    name = "Gitea Tags and Releases"
    description = "Remote version tags and release records; not deployment or workflow execution."
    keywords = ["tag", "tags", "release", "releases", "version", "changelog"]
    tool_suffixes = ("create_release", "delete_release", "get_release", "list_releases", "list_tags")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        if "release" in query and "gitea__list_releases" in available:
            return [("gitea__list_releases", {"limit": 10}, "List repository releases")]
        if "gitea__list_tags" in available:
            return [("gitea__list_tags", {"limit": 10}, "List repository tags")]
        return []


class GiteaWebhooks(GiteaToolGroup):
    id = "gitea_webhooks"
    name = "Gitea Webhooks"
    description = "Remote webhook inventory and explicitly requested webhook changes."
    keywords = ["webhook", "webhooks", "hook", "hooks"]
    tool_suffixes = ("create_webhook", "delete_webhook", "list_webhooks")

    def _fallback_calls(self, query: str, available: set[str]) -> list[tuple[str, dict[str, Any], str]]:
        if "gitea__list_webhooks" in available:
            return [("gitea__list_webhooks", {}, "List repository webhooks")]
        return []


GITEA_SKILL_CLASSES: tuple[type[GiteaToolGroup], ...] = (
    GiteaRepositoryDiscovery, GiteaActionsHandler, GiteaBranches, GiteaCodeReviews, GiteaCommitsStatus,
    GiteaFilesAndTrees, GiteaIssuesAndComments, GiteaLabelsAndMilestones, GiteaPullRequests, GiteaSearch,
    GiteaTagsAndReleases, GiteaWebhooks,
)

__all__ = ["GITEA_SKILL_CLASSES", "GiteaToolGroup", *[skill.__name__ for skill in GITEA_SKILL_CLASSES]]