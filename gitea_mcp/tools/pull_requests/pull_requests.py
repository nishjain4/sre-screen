"""Tools for listing, creating, updating, and merging pull requests."""

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import provided, request, require_confirmation


def register_pull_request_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def list_pull_requests(state: str | None = None, head: str | None = None, base: str | None = None, labels: str | None = None, milestone: int | None = None, sort: str | None = None, order: str | None = None, page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List pull requests by state, labels, milestone, or branch."""
        params = provided(state=state, head=head, base=base, labels=labels, milestone=milestone, sort=sort, order=order, page=page, limit=limit)
        return request(client, "GET", "/pulls", owner=owner, reponame=reponame, url=url, params=params)

    @mcp.tool()
    def create_pull_request(title: str, head: str, base: str, body: str | None = None, assignees: list[str] | None = None, reviewers: list[str] | None = None, labels: list[int] | None = None, milestone: int | None = None, draft: bool = False, allow_maintainer_edit: bool = False, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Open a pull request from a head branch to a base branch."""
        payload = {"title": title, "head": head, "base": base, "draft": draft, "allow_maintainer_edit": allow_maintainer_edit}
        payload.update(provided(body=body, assignees=assignees, reviewers=reviewers, labels=labels, milestone=milestone))
        return request(client, "POST", "/pulls", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def get_pull_request(index: int, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Return one pull request by index."""
        return request(client, "GET", f"/pulls/{index}", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def update_pull_request(index: int, title: str | None = None, body: str | None = None, state: str | None = None, base: str | None = None, assignees: list[str] | None = None, labels: list[int] | None = None, milestone: int | None = None, allow_maintainer_edit: bool | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Update pull-request title, body, state, base, or metadata."""
        payload = provided(title=title, body=body, state=state, base=base, assignees=assignees, labels=labels, milestone=milestone, allow_maintainer_edit=allow_maintainer_edit)
        if not payload:
            raise ValueError("Provide at least one pull-request field to update")
        return request(client, "PATCH", f"/pulls/{index}", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def merge_pull_request(index: int, merge_method: str = "merge", confirm: bool = False, merge_title: str | None = None, merge_message: str | None = None, delete_branch_after_merge: bool = False, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Merge using an allowed method after explicit confirmation."""
        require_confirmation(confirm, "merge this pull request")
        allowed_methods = {"merge", "rebase", "rebase-merge", "squash", "fast-forward-only"}
        if merge_method not in allowed_methods:
            raise ValueError(f"merge_method must be one of: {', '.join(sorted(allowed_methods))}")
        payload = provided(Do=merge_method, MergeTitleField=merge_title, MergeMessageField=merge_message)
        payload["delete_branch_after_merge"] = delete_branch_after_merge
        return request(client, "POST", f"/pulls/{index}/merge", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def get_pull_request_commits(index: int, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List commits included in a pull request."""
        return request(client, "GET", f"/pulls/{index}/commits", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def get_pull_request_files(index: int, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List changed files and patch metadata in a pull request."""
        return request(client, "GET", f"/pulls/{index}/files", owner=owner, reponame=reponame, url=url)