"""A stdio MCP server exposing repository operations through the Gitea API."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from typing import Any
from urllib.parse import quote

import httpx

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "gitea-mcp", "version": "1.0.0"}


def _field(type_: str, description: str) -> dict[str, str]:
    return {"type": type_, "description": description}


_REPO_FIELDS = {
    "owner": _field("string", "Repository owner; defaults to configured owner."),
    "repo": _field("string", "Repository name; defaults to configured repo."),
}
_ID = _field("integer", "Issue or pull request number.")
_REF = _field("string", "Branch, tag, or commit ref.")
_PATH = _field("string", "Repository file path.")
_LIMIT = _field("integer", "Maximum number of results (1-50).")


def _spec(name: str, description: str, properties: dict[str, dict[str, Any]] | None = None,
          required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {**_REPO_FIELDS, **(properties or {})},
            "required": list(required),
            "additionalProperties": False,
        },
    }


_TOOLS = [
     _spec("get_repository", "Read repository metadata, including description, default branch, and visibility."),
     _spec("list_issues", "List repository issues (pull requests are excluded).", {
         "state": _field("string", "Issue state: open, closed, or all."), "limit": _LIMIT, "page": _field("integer", "Result page."),
     }),
     _spec("get_issue", "Read one repository issue by number.", {"index": _ID}, ("index",)),
     _spec("list_pull_requests", "List repository pull requests and their review or merge state.", {
         "state": _field("string", "Pull request state: open, closed, or all."), "limit": _LIMIT, "page": _field("integer", "Result page."),
     }),
    _spec("list_commits", "List repository commits, optionally for a branch or ref.", {
        "ref": _REF, "limit": _LIMIT, "page": _field("integer", "Result page."),
    }),
     _spec("get_file", "Read a text file from the repository at an optional branch, tag, or commit ref.", {
         "path": _PATH, "ref": _REF,
     }, ("path",)),
     _spec("add_issue_comment", "Add a comment to an issue or pull request.", {
         "index": _ID, "body": _field("string", "Comment text."),
     }, ("index", "body")),
     _spec("approve_pr", "Approve a pull request.", {"index": _ID, "body": _field("string", "Optional review message.")}, ("index",)),
     _spec("comment_review", "Add an inline comment to a pull request review.", {
         "index": _ID, "review_id": _field("integer", "Review ID."), "body": _field("string", "Comment text."),
         "path": _PATH, "position": _field("integer", "Diff position for the inline comment."),
     }, ("index", "review_id", "body")),
     _spec("create_branch", "Create a branch from an existing branch or commit.", {
         "branch": _field("string", "Name for the new branch."), "old_branch": _field("string", "Existing source branch or ref."),
     }, ("branch",)),
     _spec("create_file", "Create a repository file.", {
         "path": _PATH, "content": _field("string", "UTF-8 file contents."), "message": _field("string", "Commit message."),
         "branch": _field("string", "Target branch."),
     }, ("path", "content", "message")),
     _spec("create_issue", "Create a repository issue.", {
         "title": _field("string", "Issue title."), "body": _field("string", "Issue description."),
         "labels": _field("array", "Label IDs."), "assignees": _field("array", "Assignee usernames."),
     }, ("title",)),
     _spec("create_label", "Create a repository label.", {
         "name": _field("string", "Label name."), "color": _field("string", "Hex color without #."),
         "description": _field("string", "Label description."),
     }, ("name",)),
     _spec("create_milestone", "Create a repository milestone.", {
         "title": _field("string", "Milestone title."), "description": _field("string", "Milestone description."),
         "due_on": _field("string", "Due date in ISO-8601 format."),
     }, ("title",)),
     _spec("create_pull_request", "Create a pull request.", {
         "title": _field("string", "Pull request title."), "head": _field("string", "Source branch."),
         "base": _field("string", "Target branch."), "body": _field("string", "Pull request description."),
         "draft": _field("boolean", "Whether to create as a draft."),
     }, ("title", "head", "base")),
     _spec("create_release", "Create a repository release.", {
         "tag_name": _field("string", "Release tag."), "name": _field("string", "Release title."),
         "body": _field("string", "Release notes."), "target_commitish": _field("string", "Branch or commit to tag."),
         "draft": _field("boolean", "Whether this is a draft."), "prerelease": _field("boolean", "Whether this is a prerelease."),
     }, ("tag_name",)),
     _spec("create_review", "Create a pull request review.", {
         "index": _ID, "event": _field("string", "Review event: APPROVED, REQUEST_CHANGES, or COMMENT."),
         "body": _field("string", "Review message."),
     }, ("index", "event")),
     _spec("create_webhook", "Create a repository webhook.", {
         "type": _field("string", "Webhook type, usually gitea."), "config": _field("object", "Webhook configuration."),
         "events": _field("array", "Webhook event names."), "active": _field("boolean", "Whether the webhook is active."),
     }, ("config",)),
     _spec("delete_branch", "Delete a repository branch.", {"branch": _field("string", "Branch name.")}, ("branch",)),
     _spec("delete_file", "Delete a repository file.", {
         "path": _PATH, "sha": _field("string", "Current file blob SHA."), "message": _field("string", "Commit message."),
         "branch": _field("string", "Target branch."),
     }, ("path", "sha", "message")),
     _spec("delete_release", "Delete a repository release.", {"release_id": _field("integer", "Release ID.")}, ("release_id",)),
     _spec("delete_webhook", "Delete a repository webhook.", {"hook_id": _field("integer", "Webhook ID.")}, ("hook_id",)),
     _spec("get_branch", "Read a repository branch.", {"branch": _field("string", "Branch name.")}, ("branch",)),
     _spec("get_commit", "Read commit details.", {"ref": _REF}, ("ref",)),
     _spec("get_commit_diff", "Read the unified source diff for an exact commit.", {"ref": _REF}, ("ref",)),
     _spec("get_commit_stats", "Read a commit and its file-change statistics.", {"ref": _REF}, ("ref",)),
     _spec("get_commit_status", "Read the combined status for a commit ref.", {"ref": _REF}, ("ref",)),
     _spec("get_contributor_stats", "Read repository contributor activity statistics."),
     _spec("get_contributors", "List repository contributors.", {"limit": _LIMIT, "page": _field("integer", "Result page.")}),
     _spec("get_file_content", "Read and decode a repository file.", {"path": _PATH, "ref": _REF}, ("path",)),
     _spec("get_pull_request", "Read one pull request by number.", {"index": _ID}, ("index",)),
     _spec("get_pull_request_diff", "Read the full unified diff of a pull request for code review.", {"index": _ID}, ("index",)),
     _spec("get_pull_request_commits", "List commits belonging to a pull request.", {"index": _ID}, ("index",)),
     _spec("get_pull_request_files", "List files changed by a pull request.", {"index": _ID}, ("index",)),
     _spec("get_raw_file", "Read raw repository file contents.", {"path": _PATH, "ref": _REF}, ("path",)),
     _spec("get_release", "Read a repository release by ID or tag.", {
         "release_id": _field("integer", "Release ID."), "tag": _field("string", "Release tag."),
     }),
     _spec("get_repository_languages", "Read the repository's language usage."),
     _spec("get_repository_topics", "Read repository topics."),
     _spec("list_branches", "List repository branches.", {"limit": _LIMIT, "page": _field("integer", "Result page.")}),
     _spec("list_commit_statuses", "List individual statuses for a commit ref.", {"ref": _REF}, ("ref",)),
     _spec("list_git_tree", "List files and directories in a repository tree.", {
         "ref": _field("string", "Tree SHA or branch; defaults to the repository default branch."),
         "recursive": _field("boolean", "Whether to include descendants."),
     }),
     _spec("list_issue_comments", "List comments on an issue or pull request.", {"index": _ID}, ("index",)),
     _spec("list_labels", "List repository labels.", {"limit": _LIMIT, "page": _field("integer", "Result page.")}),
     _spec("list_milestones", "List repository milestones.", {
         "state": _field("string", "Milestone state: open, closed, or all."), "limit": _LIMIT,
     }),
     _spec("list_releases", "List repository releases.", {"limit": _LIMIT, "page": _field("integer", "Result page.")}),
     _spec("list_reviews", "List reviews for a pull request.", {
         "index": _ID, "limit": _LIMIT, "page": _field("integer", "Result page."),
     }, ("index",)),
     _spec("list_tags", "List repository tags.", {"limit": _LIMIT, "page": _field("integer", "Result page.")}),
     _spec("list_webhooks", "List repository webhooks."),
     _spec("list_workflow_runs", "List repository workflow runs.", {
         "limit": _LIMIT, "page": _field("integer", "Result page."), "workflow_id": _field("string", "Optional workflow ID or filename."),
     }),
     _spec("list_workflows", "List repository workflows."),
     _spec("merge_pull_request", "Merge a pull request.", {
         "index": _ID, "merge_method": _field("string", "Merge method: merge, rebase, rebase-merge, or squash."),
         "title": _field("string", "Optional merge commit title."), "message": _field("string", "Optional merge commit message."),
     }, ("index",)),
     _spec("request_changes", "Submit a request-changes review on a pull request.", {
         "index": _ID, "body": _field("string", "Review message."),
     }, ("index", "body")),
     _spec("search_commits", "Search commits in the repository using branch, path, author, or date filters.", {
         "ref": _REF, "path": _PATH, "author": _field("string", "Commit author."),
         "since": _field("string", "Only commits after this ISO-8601 date."), "until": _field("string", "Only commits before this ISO-8601 date."),
         "limit": _LIMIT,
     }),
     _spec("search_repository", "Search Gitea repositories by query.", {
         "query": _field("string", "Repository search query."), "limit": _LIMIT,
     }, ("query",)),
     _spec("submit_review", "Submit a pull request review.", {
         "index": _ID, "event": _field("string", "Review event: APPROVED, REQUEST_CHANGES, or COMMENT."),
         "body": _field("string", "Review message."),
     }, ("index", "event")),
     _spec("trigger_workflow", "Dispatch a repository workflow.", {
         "workflow_id": _field("string", "Workflow ID or filename."), "ref": _REF,
         "inputs": _field("object", "Workflow dispatch inputs."),
     }, ("workflow_id", "ref")),
     _spec("update_file", "Update an existing repository file.", {
         "path": _PATH, "content": _field("string", "New UTF-8 file contents."), "sha": _field("string", "Current file blob SHA."),
         "message": _field("string", "Commit message."), "branch": _field("string", "Target branch."),
     }, ("path", "content", "sha", "message")),
     _spec("update_issue", "Update an issue or pull request.", {
         "index": _ID, "title": _field("string", "New issue title."), "body": _field("string", "New issue description."),
         "state": _field("string", "New state: open or closed."), "state_reason": _field("string", "Reason for closing."),
     }, ("index",)),
]


# method, endpoint, path arguments, query arguments, and JSON body arguments
_ROUTES: dict[str, tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "get_repository": ("GET", "", (), (), ()),
    "list_issues": ("GET", "/issues", (), ("state", "limit", "page"), ()),
    "get_issue": ("GET", "/issues/{index}", ("index",), (), ()),
    "list_pull_requests": ("GET", "/pulls", (), ("state", "limit", "page"), ()),
    "list_commits": ("GET", "/commits", (), ("ref", "limit", "page"), ()),
    "get_file": ("GET", "/contents/{path}", ("path",), ("ref",), ()),
    "add_issue_comment": ("POST", "/issues/{index}/comments", ("index",), (), ("body",)),
    "approve_pr": ("POST", "/pulls/{index}/reviews", ("index",), (), ("event", "body")),
    "comment_review": ("POST", "/pulls/{index}/reviews/{review_id}/comments", ("index", "review_id"), (), ("body", "path", "position")),
    "create_branch": ("POST", "/branches", (), (), ("branch", "old_branch")),
    "create_file": ("PUT", "/contents/{path}", ("path",), (), ("content", "message", "branch")),
    "create_issue": ("POST", "/issues", (), (), ("title", "body", "labels", "assignees")),
    "create_label": ("POST", "/labels", (), (), ("name", "color", "description")),
    "create_milestone": ("POST", "/milestones", (), (), ("title", "description", "due_on")),
    "create_pull_request": ("POST", "/pulls", (), (), ("title", "head", "base", "body", "draft")),
    "create_release": ("POST", "/releases", (), (), ("tag_name", "name", "body", "target_commitish", "draft", "prerelease")),
    "create_review": ("POST", "/pulls/{index}/reviews", ("index",), (), ("event", "body")),
    "create_webhook": ("POST", "/hooks", (), (), ("type", "config", "events", "active")),
    "delete_branch": ("DELETE", "/branches/{branch}", ("branch",), (), ()),
    "delete_file": ("DELETE", "/contents/{path}", ("path",), (), ("sha", "message", "branch")),
    "delete_release": ("DELETE", "/releases/{release_id}", ("release_id",), (), ()),
    "delete_webhook": ("DELETE", "/hooks/{hook_id}", ("hook_id",), (), ()),
    "get_branch": ("GET", "/branches/{branch}", ("branch",), (), ()),
    "get_commit": ("GET", "/commits/{ref}", ("ref",), (), ()),
    "get_commit_diff": ("GET", "/git/commits/{ref}.diff", ("ref",), (), ()),
    "get_commit_stats": ("GET", "/git/commits/{ref}", ("ref",), (), ()),
    "get_commit_status": ("GET", "/commits/{ref}/status", ("ref",), (), ()),
    "get_contributor_stats": ("GET", "/stats/contributors", (), (), ()),
    "get_contributors": ("GET", "/contributors", (), ("limit", "page"), ()),
    "get_file_content": ("GET", "/contents/{path}", ("path",), ("ref",), ()),
    "get_pull_request": ("GET", "/pulls/{index}", ("index",), (), ()),
    "get_pull_request_diff": ("GET", "/pulls/{index}.diff", ("index",), (), ()),
    "get_pull_request_commits": ("GET", "/pulls/{index}/commits", ("index",), (), ()),
    "get_pull_request_files": ("GET", "/pulls/{index}/files", ("index",), (), ()),
    "get_raw_file": ("GET", "/raw/{path}", ("path",), ("ref",), ()),
    "get_release": ("GET", "/releases/{release_id}", ("release_id",), (), ()),
    "get_repository_languages": ("GET", "/languages", (), (), ()),
    "get_repository_topics": ("GET", "/topics", (), (), ()),
    "list_branches": ("GET", "/branches", (), ("limit", "page"), ()),
    "list_commit_statuses": ("GET", "/commits/{ref}/statuses", ("ref",), (), ()),
    "list_git_tree": ("GET", "/git/trees/{ref}", ("ref",), ("recursive",), ()),
    "list_issue_comments": ("GET", "/issues/{index}/comments", ("index",), (), ()),
    "list_labels": ("GET", "/labels", (), ("limit", "page"), ()),
    "list_milestones": ("GET", "/milestones", (), ("state", "limit"), ()),
    "list_releases": ("GET", "/releases", (), ("limit", "page"), ()),
    "list_reviews": ("GET", "/pulls/{index}/reviews", ("index",), ("limit", "page"), ()),
    "list_tags": ("GET", "/tags", (), ("limit", "page"), ()),
    "list_webhooks": ("GET", "/hooks", (), (), ()),
    "list_workflow_runs": ("GET", "/actions/runs", (), ("limit", "page", "workflow_id"), ()),
    "list_workflows": ("GET", "/actions/workflows", (), (), ()),
    "merge_pull_request": ("POST", "/pulls/{index}/merge", ("index",), (), ("Do", "merge_method", "title", "message")),
    "request_changes": ("POST", "/pulls/{index}/reviews", ("index",), (), ("event", "body")),
    "search_commits": ("GET", "/commits", (), ("ref", "path", "author", "since", "until", "limit"), ()),
    "search_repository": ("GET", "/repos/search", (), ("query", "limit"), ()),
    "submit_review": ("POST", "/pulls/{index}/reviews", ("index",), (), ("event", "body")),
    "trigger_workflow": ("POST", "/actions/workflows/{workflow_id}/dispatches", ("workflow_id",), (), ("ref", "inputs")),
    "update_file": ("PUT", "/contents/{path}", ("path",), (), ("content", "sha", "message", "branch")),
    "update_issue": ("PATCH", "/issues/{index}", ("index",), (), ("title", "body", "state", "state_reason")),
}

if not {tool["name"] for tool in _TOOLS} <= set(_ROUTES):
    raise RuntimeError("Every exposed Gitea tool must have a REST route")


class GiteaAPI:
    def __init__(self, base_url: str, token: str = "", owner: str = "", repo: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.owner = owner
        self.repo = repo

    def _repo_path(self, arguments: dict[str, Any]) -> str:
        owner = str(arguments.get("owner") or self.owner).strip()
        repo = str(arguments.get("repo") or self.repo).strip()
        if not owner or not repo:
            raise ValueError("GITEA_OWNER and GITEA_REPO must be configured or passed as arguments")
        return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"

    async def call(self, name: str, arguments: dict[str, Any], http: httpx.AsyncClient) -> Any:
        if name not in _ROUTES:
            raise ValueError(f"unknown Gitea tool '{name}'")
        method, route, path_args, query_args, body_args = _ROUTES[name]
        repo_path = self._repo_path(arguments)
        if name == "search_repository":
            path = route
        elif name == "get_release" and not arguments.get("release_id") and arguments.get("tag"):
            path = repo_path + f"/releases/tags/{quote(str(arguments['tag']), safe='')}"
        else:
            values = {key: quote(str(arguments.get(key) or ("HEAD" if key == "ref" else "")), safe="")
                      for key in path_args}
            if "path" in values:
                values["path"] = quote(str(arguments["path"]).strip("/"), safe="/")
            path = repo_path + route.format(**values)

        params = {key: arguments[key] for key in query_args if arguments.get(key) is not None}
        if "limit" in params:
            params["limit"] = _limit(params["limit"])
        if name in {"list_issues", "list_pull_requests", "list_milestones"}:
            state = str(params.get("state", "open"))
            if state not in {"open", "closed", "all"}:
                raise ValueError("state must be open, closed, or all")
            params["state"] = state
        if name == "list_issues":
            params["type"] = "issues"
        if name in {"approve_pr", "request_changes"}:
            params_body = {"event": "APPROVED" if name == "approve_pr" else "REQUEST_CHANGES", "body": arguments.get("body", "")}
        else:
            params_body = {key: arguments[key] for key in body_args if key != "Do" and arguments.get(key) is not None}
        if name == "create_branch":
            params_body = {"new_branch_name": arguments["branch"]}
            if arguments.get("old_branch"):
                params_body["old_branch_name"] = arguments["old_branch"]
        if name in {"create_file", "update_file"}:
            params_body["content"] = base64.b64encode(str(arguments["content"]).encode("utf-8")).decode("ascii")
        if name == "create_review" or name == "submit_review":
            params_body["event"] = params_body.pop("event", "COMMENT")
        if name == "create_release":
            params_body["draft"] = bool(arguments.get("draft", False))
            params_body["prerelease"] = bool(arguments.get("prerelease", False))
        if name == "create_webhook":
            params_body["type"] = arguments.get("type", "gitea")
            params_body["events"] = arguments.get("events", [])
            params_body["active"] = bool(arguments.get("active", True))
        if name == "merge_pull_request":
            params_body["Do"] = arguments.get("merge_method", "merge")
        if name == "trigger_workflow":
            params_body["ref"] = arguments["ref"]
        response = await http.request(method, f"{self.base_url}/api/v1{path}", params=params,
                                      json=params_body if params_body else None)
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {"status": "ok", "status_code": response.status_code}
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            return {"content": response.text}
        if name in {"get_file", "get_file_content"} and isinstance(data, dict) and data.get("encoding") == "base64":
            try:
                data["decodedContent"] = base64.b64decode(data.get("content", "")).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                data["decodedContent"] = None
        return data


def _positive_int(value: Any, name: str) -> int:
    number = int(value)
    if number < 1:
        raise ValueError(f"{name} must be a positive integer")
    return number


def _limit(value: Any) -> int:
    return min(_positive_int(value, "limit"), 50)


def _text_result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=True, default=str)}],
            "structuredContent": value}


async def handle_message(message: dict[str, Any], api: GiteaAPI,
                         http: httpx.AsyncClient) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
                  "serverInfo": SERVER_INFO}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": _TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        try:
            value = await api.call(params.get("name", ""), params.get("arguments") or {}, http)
            result = _text_result(value)
        except httpx.HTTPStatusError as exc:
            detail = str(exc)
            if exc.response.status_code == 404:
                detail = (
                    "Gitea 404: resource not found or inaccessible to the token. "
                    "Verify the repository owner/name and token permissions. For a PR, use "
                    "list_pull_requests to discover its actual number; issue and PR numbers share "
                    "one sequence, so the first PR is not necessarily #1. Do not treat this as a passed review. "
                    + detail
                )
            result = {"content": [{"type": "text", "text": detail[:1600]}], "isError": True}
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            result = {"content": [{"type": "text", "text": str(exc)[:1000]}], "isError": True}
    else:
        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}
    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def _serve() -> None:
    api = GiteaAPI(os.environ.get("GITEA_URL", ""), os.environ.get("GITEA_TOKEN", ""),
                   os.environ.get("GITEA_OWNER", ""), os.environ.get("GITEA_REPO", ""))
    if not api.base_url or not api.owner or not api.repo:
        raise RuntimeError("Set GITEA_URL, GITEA_OWNER, and GITEA_REPO before starting the Gitea MCP server")
    headers = {"Accept": "application/json"}
    if api.token:
        headers["Authorization"] = f"token {api.token}"
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as http:
        while line := await asyncio.to_thread(sys.stdin.readline):
            try:
                message = json.loads(line)
                response = await handle_message(message, api, http)
            except (json.JSONDecodeError, TypeError) as exc:
                response = {"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32700, "message": str(exc)}}
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
                sys.stdout.flush()


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()